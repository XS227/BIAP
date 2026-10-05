"""Execution boundary for BIAP Global.

Global analysis and portfolio construction must not know broker-specific order
formats. Live execution remains disabled by default; this module defines the
contract that an IBKR or country-specific broker adapter must implement after
account authorization, trading permissions and compliance checks are confirmed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Optional


class GlobalBrokerError(RuntimeError):
    pass


class LiveTradingDisabled(GlobalBrokerError):
    pass


@dataclass(frozen=True)
class BrokerOrder:
    country: str
    exchange: str
    mic_code: Optional[str]
    ticker: str
    currency: str
    side: str
    quantity: int
    limit_price: Optional[float] = None
    broker_contract_id: Optional[str] = None


@dataclass(frozen=True)
class BrokerReceipt:
    status: str
    broker: str
    submitted_at: str
    broker_order_id: Optional[str]
    order: BrokerOrder


class GlobalBroker(ABC):
    broker_id: str

    @abstractmethod
    def supports(self, order: BrokerOrder) -> bool:
        """Return whether the account/broker can route this instrument."""

    @abstractmethod
    def submit(self, order: BrokerOrder) -> BrokerReceipt:
        """Submit only after external policy/approval gates have cleared."""


class GlobalPaperBroker(GlobalBroker):
    broker_id = "global-paper"

    def supports(self, order: BrokerOrder) -> bool:
        return order.quantity > 0 and order.side.upper() in {"BUY", "SELL"}

    def submit(self, order: BrokerOrder) -> BrokerReceipt:
        if not self.supports(order):
            raise GlobalBrokerError("paper order is invalid")
        now = datetime.now(timezone.utc).isoformat()
        return BrokerReceipt(
            status="PAPER_FILLED",
            broker=self.broker_id,
            submitted_at=now,
            broker_order_id=f"paper-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}",
            order=order,
        )


class ApprovalOnlyBroker(GlobalBroker):
    """Creates an approval boundary without sending anything to a live broker."""

    broker_id = "approval-only"

    def supports(self, order: BrokerOrder) -> bool:
        return order.quantity > 0 and order.side.upper() in {"BUY", "SELL"}

    def submit(self, order: BrokerOrder) -> BrokerReceipt:
        if not self.supports(order):
            raise GlobalBrokerError("approval order is invalid")
        return BrokerReceipt(
            status="PENDING_HUMAN_APPROVAL",
            broker=self.broker_id,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            broker_order_id=None,
            order=order,
        )


class LiveBrokerBase(GlobalBroker):
    """Hard guard inherited by future IBKR/native live adapters."""

    def _require_live_enabled(self) -> None:
        if os.environ.get("BIAP_GLOBAL_LIVE_TRADING_ENABLED", "false").strip().lower() != "true":
            raise LiveTradingDisabled("BIAP Global live trading is disabled")

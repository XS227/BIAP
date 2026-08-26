"""Broker execution adapters for BIAP.

Order intents pass through execution.py's policy checks first (mode
validation, AUTO always rejected). Once cleared, submit_order_intent() hands
a `paper`-mode intent to a Broker implementation to actually produce a fill
receipt. `approval` mode never reaches a broker at all -- it stays
PENDING_APPROVAL until a human acts on it, by design.

PaperBroker is the only implementation today. A real broker adapter plugs in
here, behind the same one-method interface, once API access, compliance and
account authorization are confirmed (see PROJECT_STATUS.md roadmap item 11)
-- nothing in execution.py, risk.py or api_server.py needs to change when
that happens; only which Broker instance submit_order_intent() calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Broker(ABC):
    """Where a policy-cleared order intent goes to actually be filled."""

    @abstractmethod
    def submit(self, intent: dict) -> dict:
        """Return a receipt: intent's fields plus status/submittedAt/broker/brokerOrderId."""


class PaperBroker(Broker):
    """Simulates an immediate fill. Never contacts any real market or broker."""

    def submit(self, intent: dict) -> dict:
        return {
            **intent,
            "status": "PAPER_FILLED",
            "submittedAt": _now_iso(),
            "broker": "paper",
            "brokerOrderId": f"paper-{intent['id']}",
        }

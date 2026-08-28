"""Dormant real-broker gateway.

The official Farabi API contract is not available yet, so endpoint paths and
wire formats are deliberately not guessed. Once the broker sends its docs, map
the documented paths/auth in this file and/or environment variables. Until
then every money-moving method fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Optional

import httpx

from broker_runtime import BrokerRuntimeConfig


class BrokerNotConfigured(RuntimeError):
    pass


class BrokerProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerEndpoints:
    token: str = ""
    buying_power: str = ""
    portfolio: str = ""
    orders: str = ""
    order_status: str = ""
    cancel_order: str = ""

    @classmethod
    def from_env(cls) -> "BrokerEndpoints":
        return cls(
            token=os.getenv("BIAP_BROKER_TOKEN_PATH", "").strip(),
            buying_power=os.getenv("BIAP_BROKER_BUYING_POWER_PATH", "").strip(),
            portfolio=os.getenv("BIAP_BROKER_PORTFOLIO_PATH", "").strip(),
            orders=os.getenv("BIAP_BROKER_ORDERS_PATH", "").strip(),
            order_status=os.getenv("BIAP_BROKER_ORDER_STATUS_PATH", "").strip(),
            cancel_order=os.getenv("BIAP_BROKER_CANCEL_ORDER_PATH", "").strip(),
        )

    def public_status(self) -> dict:
        configured = {
            "token": bool(self.token),
            "buyingPower": bool(self.buying_power),
            "portfolio": bool(self.portfolio),
            "orders": bool(self.orders),
            "orderStatus": bool(self.order_status),
            "cancelOrder": bool(self.cancel_order),
        }
        return {"configured": configured, "complete": all(configured.values())}


class FarabiGateway:
    """Configurable HTTP boundary for the future official Farabi API.

    No endpoint path or payload shape is hard-coded before official docs exist.
    This lets us drop credentials/URLs into server environment variables later,
    then implement only the documented serializer/parser layer here.
    """

    def __init__(self, config: Optional[BrokerRuntimeConfig] = None):
        self.config = config or BrokerRuntimeConfig.from_env()
        self.endpoints = BrokerEndpoints.from_env()

    def readiness(self) -> dict:
        return {
            **self.config.public_status(),
            "endpoints": self.endpoints.public_status(),
        }

    def _require_base(self) -> None:
        if self.config.provider != "farabi":
            raise BrokerNotConfigured("configured broker provider is not farabi")
        if not self.config.integration_material_present():
            raise BrokerNotConfigured("broker API base URL/credentials are not configured")

    def _url(self, path: str) -> str:
        self._require_base()
        if not path:
            raise BrokerNotConfigured("required broker endpoint path is not configured")
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self, access_token: Optional[str] = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BIAP-Kiasha/1.0",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif self.config.api_key:
            # Header name may change after Farabi provides official docs.
            headers["X-API-Key"] = self.config.api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: Optional[str] = None,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        headers = self._headers(access_token)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = httpx.request(
                method,
                self._url(path),
                headers=headers,
                json=json,
                params=params,
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise BrokerProtocolError(f"broker request failed: {exc.__class__.__name__}") from exc

        if response.status_code >= 400:
            raise BrokerProtocolError(f"broker returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BrokerProtocolError("broker returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise BrokerProtocolError("broker returned unexpected response shape")
        return payload

    # The following methods intentionally stop before guessing Farabi's payload
    # shapes. Their parsers are the only parts we need to finish from the docs.
    def buying_power(self, *, access_token: Optional[str] = None) -> dict[str, Any]:
        return self._request("GET", self.endpoints.buying_power, access_token=access_token)

    def portfolio(self, *, access_token: Optional[str] = None) -> dict[str, Any]:
        return self._request("GET", self.endpoints.portfolio, access_token=access_token)

    def submit_raw_order(
        self,
        payload: dict[str, Any],
        *,
        access_token: Optional[str] = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not self.config.live_trading_enabled:
            raise BrokerNotConfigured("LIVE_TRADING_ENABLED is false")
        if self.config.environment != "production":
            # Sandbox submission is allowed only after an official sandbox
            # endpoint is configured. It still must never be mistaken for live.
            if self.config.environment != "sandbox":
                raise BrokerNotConfigured("unsupported broker environment")
        return self._request(
            "POST",
            self.endpoints.orders,
            access_token=access_token,
            json=payload,
            idempotency_key=idempotency_key,
        )

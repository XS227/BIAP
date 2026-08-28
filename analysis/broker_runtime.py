"""Runtime configuration and readiness checks for real broker integrations.

This module is intentionally provider-agnostic and fail-closed. It gives BIAP a
stable place to insert official broker API details later without ever shipping
secrets to the mobile app.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Optional


_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _enabled(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in _TRUE


@dataclass(frozen=True)
class BrokerRuntimeConfig:
    provider: str
    environment: str
    base_url: str
    client_id: str
    client_secret: str
    api_key: str
    account_id: str
    funding_url: str
    callback_url: str
    live_trading_enabled: bool

    @classmethod
    def from_env(cls) -> "BrokerRuntimeConfig":
        return cls(
            provider=_env("BIAP_BROKER_PROVIDER", "farabi").lower(),
            environment=_env("BIAP_BROKER_ENV", "sandbox").lower(),
            base_url=_env("BIAP_BROKER_BASE_URL"),
            client_id=_env("BIAP_BROKER_CLIENT_ID"),
            client_secret=_env("BIAP_BROKER_CLIENT_SECRET"),
            api_key=_env("BIAP_BROKER_API_KEY"),
            account_id=_env("BIAP_BROKER_ACCOUNT_ID"),
            funding_url=_env("BIAP_BROKER_FUNDING_URL"),
            callback_url=_env("BIAP_BROKER_CALLBACK_URL"),
            live_trading_enabled=_enabled("LIVE_TRADING_ENABLED", False),
        )

    def auth_material_present(self) -> bool:
        # We do not yet know Farabi's official auth scheme. Accept either the
        # OAuth-style pair or an API key as "material present" for readiness;
        # the provider adapter will enforce the exact scheme once docs arrive.
        return bool((self.client_id and self.client_secret) or self.api_key)

    def integration_material_present(self) -> bool:
        return bool(self.base_url and self.auth_material_present())

    def production_ready(self) -> bool:
        return bool(
            self.integration_material_present()
            and self.environment == "production"
            and self.live_trading_enabled
        )

    def public_status(self) -> dict:
        """Return safe metadata only; never expose credentials or raw secrets."""
        missing: list[str] = []
        if not self.base_url:
            missing.append("base_url")
        if not self.auth_material_present():
            missing.append("credentials")
        if not self.account_id:
            missing.append("account_linking")
        if not self.funding_url:
            missing.append("hosted_funding")

        return {
            "provider": self.provider,
            "environment": self.environment,
            "configured": self.integration_material_present(),
            "accountLinked": bool(self.account_id),
            "hostedFundingConfigured": bool(self.funding_url),
            "liveTradingEnabled": self.live_trading_enabled,
            "productionReady": self.production_ready(),
            "missing": missing,
        }


def current_broker_status() -> dict:
    return BrokerRuntimeConfig.from_env().public_status()


def safe_funding_url() -> Optional[str]:
    cfg = BrokerRuntimeConfig.from_env()
    if not cfg.funding_url:
        return None
    if not (cfg.funding_url.startswith("https://") or cfg.environment == "sandbox"):
        return None
    return cfg.funding_url

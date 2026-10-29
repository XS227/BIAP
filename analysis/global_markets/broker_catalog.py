"""Read-only broker integration catalogue, with no credentials or order submission.

An API ecosystem is not an active broker connection. Eligibility/availability
for a particular user, instrument or venue must be confirmed by the provider.
"""
from __future__ import annotations

BROKERS = (
    {
        "id": "ibkr",
        "name": "Interactive Brokers",
        "integrationStage": "PARTNER_APPROVAL_REQUIRED",
        "marketScope": "Multi-market, subject to account and exchange permissions",
        "usEquitiesOnly": False,
        "apiDocs": "https://www.interactivebrokers.com/docs/web-api/introduction",
        "onboardingDocs": "https://ibkrcampus.eu/docs/web-api/trading/getting-started/trading-access-for-third-parties",
    },
    {
        "id": "saxo",
        "name": "Saxo Bank",
        "integrationStage": "APP_ACCESS_REQUIRED",
        "marketScope": "Multi-market, subject to account and exchange permissions",
        "usEquitiesOnly": False,
        "apiDocs": "https://www.developer.saxo/openapi/learn",
        "onboardingDocs": "https://www.developer.saxo/openapi/learn/other-clients-or-partners-request-for-openapi-application-credentials-for-the-l",
    },
    {
        "id": "alpaca",
        "name": "Alpaca",
        "integrationStage": "PARTNER_APPROVAL_REQUIRED",
        "marketScope": "US-listed equities; partner brokerage requires agreement",
        "usEquitiesOnly": True,
        "apiDocs": "https://docs.alpaca.markets/us/docs/trading-api",
        "onboardingDocs": "https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api",
    },
)


def broker_readiness() -> dict:
    """Always fail closed until actual regulated partner account integration."""
    return {
        "mode": "RESEARCH_PAPER_PREVIEW",
        "brokerConnected": False,
        "paperBrokerConnected": False,
        "liveTrading": False,
        "clientFundsAccepted": False,
        "orderSubmissionEnabled": False,
        "disclaimer": (
            "These are prospective integrations, not connected brokerage accounts. "
            "BIAP does not submit, route, or execute orders for clients. "
            "Client identity, provider approval, relevant securities licences and "
            "broker-side trading permissions are required first."
        ),
        "providers": [dict(entry, connectionStatus="NOT_CONNECTED") for entry in BROKERS],
    }

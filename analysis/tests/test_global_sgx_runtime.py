from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.runtime import build_registry
from global_markets.service import _source_plan_payload
from global_markets.sgx_issuer import SGXIssuerFundamentalsProvider


def test_singapore_partial_official_provider_is_registered():
    registry = build_registry()
    provider = registry.fundamentals("SG", "SGX")

    assert isinstance(provider, PersistentFundamentalsProvider)
    assert isinstance(provider.upstream, FallbackFundamentalsProvider)
    assert isinstance(provider.upstream.primary, SGXIssuerFundamentalsProvider)


def test_singapore_source_plan_is_explicitly_partial():
    plan = _source_plan_payload("SG")

    assert plan["status"] == "partial"
    assert plan["runtimeConfigured"] is True
    assert "allow-list" in plan["runtimeNote"]

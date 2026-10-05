"""Bank (Bank of Italy Circular 262) ESEF normalization.

Fact values are copied from the issuers' FY2025 consolidated ESEF reports on
eMarket STORAGE: Intesa Sanpaolo 181345 (LEI 2W8N8UU78PMDQKZENC08) and BPER
Banca 181086 (LEI N747OI7JINV7RUUH6190). Neither tags ifrs-full:Revenue or a
plain ifrs-full:Equity total.
"""
from datetime import date

from global_markets.esef import ESEFFundamentalsProvider, concept_is_relevant

END = date(2025, 12, 31)
FY25 = "2025-01-01/2025-12-31"
FY24 = "2024-01-01/2024-12-31"
OWNERS_TOTAL = {"ifrs-full:ComponentsOfEquityAxis": "ifrs-full:EquityAttributableToOwnersOfParentMember"}


def fact(concept, value, period, **dims):
    return {
        "value": str(value),
        "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": "iso4217:EUR", **dims},
    }


def isp_facts():
    return [
        fact("ifrs-full:ProfitLoss", 9341e6, FY25),
        fact("ifrs-full:ProfitLoss", 8659e6, FY24),
        fact("ifrs-full:Assets", 959887e6, "2025-12-31"),
        fact("ifrs-full:EquityAndLiabilities", 959887e6, "2025-12-31"),
        fact("ifrs-full:FeeAndCommissionIncomeExpense", 8992e6, FY25),
        fact("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", 25117e6, FY25),
        fact("isp:GrossIncome", 30472e6, FY25),
        fact("isp:GrossIncome", 30693e6, FY24),
        fact("isp:TotalEquity", 65378e6, "2025-12-31"),
        fact("isp:TotalEquity", 65321e6, "2024-12-31"),
        # Component column of the statement of changes in equity: never a total.
        fact("isp:TotalEquity", 9341e6, "2025-12-31", **{"ifrs-full:ComponentsOfEquityAxis": "isp:ProfitLossMember"}),
        fact("ifrs-full:NoncontrollingInterests", 152e6, "2025-12-31"),
    ]


def bper_facts():
    return [
        fact("ifrs-full:ProfitLoss", 1880466e3, FY25),
        fact("ifrs-full:ProfitLoss", 1438510e3, FY24),
        fact("ifrs-full:Assets", 204649960e3, "2025-12-31"),
        fact("ifrs-full:EquityAndLiabilities", 204649960e3, "2025-12-31"),
        fact("ifrs-full:FeeAndCommissionIncomeExpense", 2381301e3, FY25),
        # BPER tags this IFRS fact with a two-year period; item 10 is annual.
        fact("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", 4873153e3, "2024-01-01/2025-12-31"),
        fact("bperbanca:InterestIncomeAndSimilarRevenues", 5180136e3, FY25),
        fact("bperbanca:GrossIncome", 6405381e3, FY25),
        fact("bperbanca:GrossIncome", 5490631e3, FY24),
        fact("bperbanca:EquityAttributableToOwnersOfParentAtEndOfPeriod", 16565045e3, "2025-12-31", **OWNERS_TOTAL),
        fact("bperbanca:EquityAttributableToOwnersOfParentAtEndOfPeriod", 2953572e3, "2025-12-31",
             **{"ifrs-full:ComponentsOfEquityAxis": "ifrs-full:IssuedCapitalMember"}),
        fact("ifrs-full:NoncontrollingInterests", 1030454e3, "2025-12-31"),
    ]


def normalize(facts):
    result = ESEFFundamentalsProvider().normalized_fields(facts, END)
    return result, result.pop("__normalization_meta__")


def test_isp_uses_issuer_total_equity_and_item_120_revenue():
    result, meta = normalize(isp_facts())
    assert result["total_equity"] == 65378e6
    assert meta["equity_method"] == "issuer_extension_total_equity"
    assert result["revenue"] == 30472e6
    assert result["revenue_prev"] == 30693e6
    assert round(result["revenue_yoy_pct"], 2) == -0.72
    assert round(result["net_margin_pct"], 2) == 30.65
    assert meta["revenue_method"] == "bank_net_interest_and_other_banking_income"


def test_bper_equity_is_owners_total_plus_minorities_and_reconciles():
    result, meta = normalize(bper_facts())
    # 16,565,045k + 1,030,454k; equals EquityAndLiabilities 204,649,960k
    # minus BPER's tagged Circular 262 liability lines (187,054,461k).
    assert result["total_equity"] == 17595499e3
    assert meta["equity_method"] == "owners_equity_plus_noncontrolling_interests"
    assert result["revenue"] == 6405381e3
    assert meta["revenue_method"] == "bank_net_interest_and_other_banking_income"


def test_bank_revenue_needs_bank_structure_and_never_overrides_ifrs_revenue():
    plain = [f for f in isp_facts() if "Interest" not in f["dimensions"]["concept"] and "FeeAndCommission" not in f["dimensions"]["concept"]]
    result, meta = normalize(plain)
    assert result["revenue"] is None and meta["revenue_method"] is None

    with_revenue = isp_facts() + [fact("ifrs-full:Revenue", 1000, FY25)]
    result, meta = normalize(with_revenue)
    assert result["revenue"] == 1000 and meta["revenue_method"] == "ifrs_revenue"


def test_direct_ifrs_equity_wins_and_component_columns_are_not_totals():
    facts = isp_facts() + [fact("ifrs-full:Equity", 65000e6, "2025-12-31")]
    result, meta = normalize(facts)
    assert result["total_equity"] == 65000e6 and meta["equity_method"] == "direct_ifrs_equity"

    # Only an owners component (issued capital) and no owners total: no equity.
    components = [f for f in bper_facts() if f["dimensions"].get("ifrs-full:ComponentsOfEquityAxis") != "ifrs-full:EquityAttributableToOwnersOfParentMember"]
    result, meta = normalize(components)
    assert result["total_equity"] is None and meta["equity_method"] is None


def test_owners_total_without_minorities_or_above_balance_sheet_is_rejected():
    no_nci = [f for f in bper_facts() if f["dimensions"]["concept"] != "ifrs-full:NoncontrollingInterests"]
    assert normalize(no_nci)[0]["total_equity"] is None

    inflated = [f for f in isp_facts() if f["dimensions"]["concept"] != "ifrs-full:EquityAndLiabilities"]
    inflated.append(fact("ifrs-full:EquityAndLiabilities", 1e9, "2025-12-31"))
    assert normalize(inflated)[0]["total_equity"] is None


def test_bank_concepts_survive_oam_package_relevance_filter():
    for concept in (
        "isp:TotalEquity", "isp:GrossIncome", "bperbanca:GrossIncome",
        "bperbanca:EquityAttributableToOwnersOfParentAtEndOfPeriod",
        "bperbanca:InterestIncomeAndSimilarRevenues", "ifrs-full:NoncontrollingInterests",
        "ifrs-full:EquityAndLiabilities", "ifrs-full:FeeAndCommissionIncomeExpense",
    ):
        assert concept_is_relevant(concept), concept
    assert not concept_is_relevant("isp:TotalEquityInstruments")


def test_old_package_parse_is_only_an_outage_fallback(tmp_path, monkeypatch):
    import pytest
    from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling, PACKAGE_SCHEMA_VERSION
    from global_markets.providers import GlobalProviderError
    from global_markets.source_cache import write_json_atomic

    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    provider = NationalOAMESEFProvider(locators=[])
    filing = OAMFiling(oam="it-emarket-storage", document_id="EMARKET-STORAGE:181345", package_url="https://example.invalid/p.xbri", landing_url="x")
    old = {"schemaVersion": 2, "documentId": filing.document_id, "entities": ["2W8N8UU78PMDQKZENC08"], "facts": []}
    write_json_atomic(provider._facts_cache_path(filing), old)

    def offline(url, target):
        raise GlobalProviderError("OAM package download failed: ConnectError")

    monkeypatch.setattr(provider, "_download", offline)
    assert provider.package_facts(filing) == old  # outage: previous parse of the same document
    assert PACKAGE_SCHEMA_VERSION == 3

    write_json_atomic(provider._facts_cache_path(filing), {**old, "schemaVersion": 1})
    with pytest.raises(GlobalProviderError):
        provider.package_facts(filing)


def test_fineco_italian_item_120_label_is_bank_revenue_but_restated_owners_total_is_not_equity():
    # FinecoBank FY2025 ESEF (filings.xbrl.org, LEI 549300L7YCATGO57ZE10)
    # tags item 120 under its statutory Italian label, and tags the FY2025
    # closing owners' total with an extra PreviouslyStated restatement member.
    facts = [
        fact("ifrs-full:ProfitLoss", 647041e3, FY25),
        fact("ifrs-full:EquityAndLiabilities", 37295901e3, "2025-12-31"),
        fact("ifrs-full:FeeAndCommissionIncomeExpense", 582228e3, FY25),
        fact("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", 544088e3, FY25),
        fact("finecobank:MargineDiIntermediazione", 1315205e3, FY25),
        fact("finecobank:MargineDiIntermediazione", 1313797e3, FY24),
        fact("finecobank:TotalEquityAttributableToOwnersOfParent", 2553324e3, "2025-12-31", **OWNERS_TOTAL,
             **{"ifrs-full:RetrospectiveApplicationAndRetrospectiveRestatementAxis": "ifrs-full:PreviouslyStatedMember"}),
        fact("ifrs-full:NoncontrollingInterests", 0, "2025-12-31"),
    ]
    result, meta = normalize(facts)
    assert result["revenue"] == 1315205e3 and result["revenue_prev"] == 1313797e3
    assert meta["revenue_method"] == "bank_net_interest_and_other_banking_income"
    assert result["total_equity"] is None and meta["equity_method"] is None
    assert concept_is_relevant("finecobank:MargineDiIntermediazione")


def test_transition_period_is_not_filled_with_prior_fiscal_year_flows():
    # Mediobanca moved its year end from 30 June to 31 December: the
    # 2025-12-31 report covers 2025-07-01..2025-12-31 (6 months). The last
    # annual P&L ends 2025-06-30 and must not be presented as FY2025-12-31.
    facts = [
        fact("ifrs-full:ProfitLoss", 513250e3, "2025-07-01/2025-12-31"),
        fact("ifrs-full:ProfitLoss", 1332501e3, "2024-07-01/2025-06-30"),
        fact("ifrs-full:CashFlowsFromUsedInOperatingActivities", 1243910e3, "2025-07-01/2025-12-31"),
        fact("ifrs-full:CashFlowsFromUsedInOperatingActivities", -1202976e3, "2024-07-01/2025-06-30"),
        fact("ifrs-full:Assets", 106006555e3, "2025-12-31"),
    ]
    result, _ = normalize(facts)
    assert result["net_income"] is None and result["net_margin_pct"] is None
    assert result["operating_cash_flow"] is None
    assert result["total_assets"] == 106006555e3
    # A regular annual report keeps current and prior-year flows.
    june = ESEFFundamentalsProvider().normalized_fields(facts, date(2025, 6, 30))
    assert june["net_income"] == 1332501e3


NCI_COLUMN = {"ifrs-full:ComponentsOfEquityAxis": "ifrs-full:NoncontrollingInterestsMember"}


def _bank_base(total):
    return [
        fact("ifrs-full:ProfitLoss", 1, FY25),
        fact("ifrs-full:EquityAndLiabilities", total, "2025-12-31"),
        fact("ifrs-full:FeeAndCommissionIncomeExpense", 1, FY25),
        fact("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod", 1, FY25),
    ]


def test_total_equity_concept_on_owners_and_nci_columns_sums_to_total():
    # Banca Mediolanum FY2025 (eMarket 179719): ext:TotalEquity per SoCE column.
    facts = _bank_base(89938260e3) + [
        fact("bmed:TotalEquity", 4494361e3, "2025-12-31", **OWNERS_TOTAL),
        fact("bmed:TotalEquity", 0, "2025-12-31", **NCI_COLUMN),
        fact("bmed:TotalEquity", 600000e3, "2025-12-31", **{"ifrs-full:ComponentsOfEquityAxis": "ifrs-full:IssuedCapitalMember"}),
    ]
    result, meta = normalize(facts)
    assert result["total_equity"] == 4494361e3
    assert meta["equity_method"] == "owners_equity_plus_noncontrolling_interests"

    # Banca Profilo FY2025 (1INFO 165506): ifrs-full:Equity on the owners
    # column plus a plain NoncontrollingInterests fact.
    facts = _bank_base(1966714e3) + [
        fact("ifrs-full:Equity", 166471e3, "2025-12-31", **OWNERS_TOTAL),
        fact("ifrs-full:NoncontrollingInterests", 0, "2025-12-31"),
    ]
    result, meta = normalize(facts)
    assert result["total_equity"] == 166471e3
    assert meta["equity_method"] == "owners_equity_plus_noncontrolling_interests"


def test_owners_column_without_any_nci_is_still_not_total_equity():
    # BFF Bank FY2025 (1INFO 167713) tags only the owners total, no NCI.
    facts = _bank_base(12278709e3) + [
        fact("bff:TotalEquityAttributableToOwnersOfParent", 888165e3, "2025-12-31", **OWNERS_TOTAL),
    ]
    result, meta = normalize(facts)
    assert result["total_equity"] is None and meta["equity_method"] is None

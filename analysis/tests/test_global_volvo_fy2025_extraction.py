"""AB Volvo FY2025 regression on facts from the official FI ESEF package.

Fixture: a subset of the inline-XBRL facts in Finansinspektionen document
FI-FINANSCENTRALEN:61749 (abvolvo-2025-12-31-1-sv.xhtml, LEI
549300HGV012CNC8JD22), filtered to the concepts the normalizer reads.
"""
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from global_markets.credit_scoring import score_legal_entity_company
from global_markets.distress import distress_agent
from global_markets.esef import ESEFFundamentalsProvider, _agent10_fields
from global_markets.models import GlobalCompany

FIXTURE = Path(__file__).parent / "fixtures" / "volvo_fy2025_esef_facts.json"


def _normalized():
    facts = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return ESEFFundamentalsProvider().normalized_fields(facts, date(2025, 12, 31))


def test_volvo_fy2025_balance_sheet_and_credit_inputs():
    result = _normalized()
    meta = result.pop("__normalization_meta__")
    assert result["reporting_currency"] == "SEK"
    assert result["revenue"] == 479_183_000_000
    assert result["revenue_prev"] == 526_816_000_000
    assert result["operating_income"] == 48_506_000_000
    assert result["net_income"] == 34_707_000_000
    assert result["total_assets"] == 648_590_000_000
    assert result["total_equity"] == 178_477_000_000
    # No ifrs-full:Liabilities tag: assets - equity of the same balance sheet;
    # equals current + non-current liabilities + current/non-current provisions.
    assert result["total_liabilities"] == 470_113_000_000
    assert result["total_liabilities"] == 250_874_000_000 + 185_309_000_000 + 15_039_000_000 + 18_891_000_000
    # Closing balance of the retained-earnings column (statement of changes in equity).
    assert result["retained_earnings"] == 179_569_000_000
    assert meta["retained_earnings_method"] == "equity_statement_retained_earnings_column"
    # D&A: intangibles 4,020 + leasing assets 9,041 + tangible 10,425 (MSEK).
    assert meta["depreciation_amortisation"] == 23_486_000_000
    assert result["ebitda"] == 48_506_000_000 + 23_486_000_000
    # Bonds (current 64,960 + non-current 82,620) + other loans (45,866 + 54,614).
    assert result["total_debt"] == 248_060_000_000
    assert meta["debt_method"].startswith("sum_of_bonds_and_loans:")
    # Investments in PP&E 18,344 against cash flow from operations 45,595.
    assert meta["capex"] == 18_344_000_000
    assert result["free_cash_flow"] == 45_595_000_000 - 18_344_000_000
    # FFO = EBITDA 71,992 - interest paid 1,458 + received 1,920 - taxes paid 11,507.
    assert meta["ffo"] == 60_947_000_000
    assert _agent10_fields(meta)["agent10_ffo"] == 60_947_000_000


def test_volvo_fy2025_agents_9_and_10_run_on_verified_inputs():
    result = _normalized()
    meta = result.pop("__normalization_meta__")
    result.pop("reporting_currency")
    company = replace(
        GlobalCompany(
            country="SE", exchange="NASDAQ_STOCKHOLM", mic_code="XSTO", currency="SEK",
            ticker="VOLV.B", name="Aktiebolaget Volvo", isin="SE0000115446",
            sector="Industrials",
        ),
        **result,
        raw_provider_fields=_agent10_fields(meta),
    )
    distress = distress_agent(company)
    assert set(distress.available_models) == {"zmijewski", "altman_z_double_prime", "interest_coverage"}
    assert distress.missing_inputs == ()
    assert distress.altman_zone == "GREY"
    assert distress.synthetic_credit_band == "AAA"
    assert distress.status == "ELEVATED_RISK"
    assert not distress.positive_block

    credit = score_legal_entity_company(company, distress)
    assert credit["strict_rating_available"] is True
    assert set(credit["factors"]) == {"debt_ebitda", "ebitda_interest", "ffo_debt", "fcf_debt", "liquidity"}
    assert set(credit["factors_missing"]) == {"industry_risk", "governance"}
    assert credit["weight_coverage"] == 0.7
    assert credit["report_only"] is True

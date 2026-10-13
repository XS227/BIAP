import json
from dataclasses import replace

from global_markets.models import GlobalCompany
from global_markets.sector_reference import (
    apply_sector_reference, classify_wikidata_industries, icb_entry, load_entries, save_entries,
)
from global_markets.sector_reference_sync import parse_euronext_icb
from global_markets.core_agents import _is_financial as core_financial
from global_markets.distress import _is_financial as distress_financial


def _co(**kw):
    base = dict(country="DE", exchange="XETRA", currency="EUR", ticker="ALV", name="ALLIANZ SE", isin="DE0008404005")
    base.update(kw)
    return GlobalCompany(**base)


def test_insurer_is_recognised_from_wikidata_industry_not_from_the_name():
    verdict = classify_wikidata_industries(["insurance", "financial services", "insurance industry"])
    assert (verdict["sector"], verdict["industry"], verdict["kind"]) == ("Financials", "Insurance", "insurance")


def test_negated_insurance_label_does_not_make_a_bank_an_insurer():
    verdict = classify_wikidata_industries(["financial service activities, except insurance and pension funding", "other monetary intermediation"])
    assert verdict["kind"] == "bank"
    verdict = classify_wikidata_industries(["financial service activities, except insurance and pension funding"])
    assert verdict["kind"] == "financial"


def test_operating_company_and_ambiguous_labels():
    assert classify_wikidata_industries(["semiconductor industry"])["sector"] == "Technology"
    assert classify_wikidata_industries(["telecommunications industry", "mobile phone industry"])["sector"] == "Telecommunications"
    assert classify_wikidata_industries(["mining", "software"]) is None  # conflicting -> unclassified, never guessed
    assert classify_wikidata_industries([]) is None


def test_reference_fills_only_an_empty_sector_and_records_provenance(tmp_path):
    entries = {"DE0008404005": {"sector": "Financials", "industry": "Insurance", "kind": "insurance", "source": "wikidata-industry",
                                "classification": "Wikidata", "url": "u", "retrievedAt": "t"}}
    filled = apply_sector_reference(_co(), entries)
    assert (filled.sector, filled.industry) == ("Financials", "Insurance")
    assert filled.raw_provider_fields["sector_source"] == "wikidata-industry"
    assert filled.raw_provider_fields["sector_provenance"]["identityCheck"] == "exact ISIN match"
    official = _co(sector="Industrials")
    assert apply_sector_reference(official, entries).sector == "Industrials"  # official value always wins
    assert apply_sector_reference(_co(isin="DE0000000000"), entries).sector is None  # no ISIN match, no fill
    assert apply_sector_reference(_co(isin=None), entries).sector is None
    assert apply_sector_reference(_co(), {"DE0008404005": {"sector": "Made Up"}}).sector is None  # vocabulary is closed


def test_sector_makes_agents_treat_insurers_as_financial_even_without_leverage_signal():
    insurer = apply_sector_reference(_co(total_assets=100.0, total_equity=50.0), {
        "DE0008404005": {"sector": "Financials", "industry": "Insurance", "kind": "insurance", "source": "s"}})
    assert core_financial(insurer) and distress_financial(insurer)
    assert not distress_financial(_co(total_assets=100.0, total_equity=50.0))  # unclassified, low leverage -> corporate model


def test_store_round_trip_and_missing_file(tmp_path):
    path = tmp_path / "sector-reference" / "entries.json"
    assert load_entries(path) == {}
    save_entries({"X": {"sector": "Energy"}}, path)
    assert load_entries(path) == {"X": {"sector": "Energy"}}


def test_euronext_icb_page_is_parsed_and_mapped_to_icb_industry():
    html = ("<div> ICB SECTORIAL CLASSIFICATION <span>Industry 55, Basic Materials</span> <span>SuperSector 5520, Chemicals</span>"
            "<span>Sector 552010, Chemicals</span> <span>Subsector 55201000, Chemicals: Diversified</span>"
            '<button class="btn" data-content="x">Help</button></div>')
    parsed = parse_euronext_icb(html)
    assert parsed["code"] == "55201000" and parsed["sector"] == "Chemicals"
    entry = icb_entry(parsed["code"], parsed["industry"], parsed["sector"], url="u", retrieved_at="t")
    assert entry["sector"] == "Basic Materials" and entry["source"] == "euronext-icb"
    bank = icb_entry("30101010", "Banks", "Banks", url="u", retrieved_at="t")
    assert bank["sector"] == "Financials" and bank["kind"] == "bank"
    assert parse_euronext_icb("") is None


def test_bme_official_sector_maps_to_icb_and_marks_banks_and_insurers():
    from global_markets.sector_reference import bme_entry
    bank = bme_entry("05", "01", "Financial Services", "Banks", retrieved_at="t")
    ins = bme_entry("05", "02", "Financial Services", "Insurance", retrieved_at="t")
    assert (bank["sector"], bank["kind"], ins["kind"]) == ("Financials", "bank", "insurance")
    assert bme_entry("01", "02", "Petrol and Power", "Electricity and Gas", retrieved_at="t")["sector"] == "Utilities"
    assert bme_entry("05", "04", "Financial Services", "SICAV", retrieved_at="t") is None  # pooled vehicle, never an operating sector
    assert bme_entry("04", "06", "Consumer Services", "Other Services", retrieved_at="t") is None  # ambiguous -> missing, not guessed

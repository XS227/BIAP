from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

from global_markets.cvm import CVMFundamentalsProvider, parse_cvm_dfp_archive
from global_markets.models import GlobalCompany
from global_markets.runtime import build_registry
from global_markets.source_cache import source_index_path


HEADERS = [
    "CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM", "GRUPO_DFP",
    "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC",
    "CD_CONTA", "DS_CONTA", "VL_CONTA", "ST_CONTA_FIXA",
]


def _csv(rows):
    def line(values):
        return ";".join(str(values.get(key, "")) for key in HEADERS)
    return (";".join(HEADERS) + "\n" + "\n".join(line(row) for row in rows) + "\n").encode("latin-1")


def _row(code, value, *, order="ÚLTIMO", name="PETRÓLEO BRASILEIRO S.A. - PETROBRAS"):
    return {
        "CNPJ_CIA": "33000167000101",
        "DT_REFER": "2025-12-31",
        "VERSAO": "1",
        "DENOM_CIA": name,
        "CD_CVM": "9512",
        "GRUPO_DFP": "DF Consolidado",
        "MOEDA": "REAL",
        "ESCALA_MOEDA": "MIL",
        "ORDEM_EXERC": order,
        "DT_INI_EXERC": "2025-01-01",
        "DT_FIM_EXERC": "2025-12-31",
        "CD_CONTA": code,
        "DS_CONTA": code,
        "VL_CONTA": value,
        "ST_CONTA_FIXA": "S",
    }


def _archive():
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("dfp_cia_aberta_DRE_con_2025.csv", _csv([
            _row("3.01", "1000,0"),
            _row("3.01", "800,0", order="PENÚLTIMO"),
            _row("3.03", "400,0"),
            _row("3.05", "250,0"),
            _row("3.11", "200,0"),
            _row("3.11", "120,0", order="PENÚLTIMO"),
        ]))
        zf.writestr("dfp_cia_aberta_BPA_con_2025.csv", _csv([
            _row("1", "5000,0"),
            _row("1.01", "2000,0"),
            _row("1.01.01", "500,0"),
        ]))
        zf.writestr("dfp_cia_aberta_BPP_con_2025.csv", _csv([
            _row("2", "5000,0"),
            _row("2.01", "1200,0"),
            _row("2.03", "2500,0"),
            _row("2.01.04", "300,0"),
            _row("2.02.01", "700,0"),
        ]))
        zf.writestr("dfp_cia_aberta_DFC_MI_con_2025.csv", _csv([
            _row("6.01", "350,0"),
        ]))
    return buf.getvalue()


def test_parse_cvm_dfp_archive_uses_fixed_accounts_and_scale():
    rows = parse_cvm_dfp_archive(_archive())
    assert len(rows) == 1
    record = rows[0]
    metrics = record["metrics"]
    assert record["scope"] == "consolidated"
    assert metrics["revenue"] == 1_000_000.0
    assert metrics["revenue_prev"] == 800_000.0
    assert metrics["revenue_yoy_pct"] == 25.0
    assert metrics["net_income"] == 200_000.0
    assert metrics["net_margin_pct"] == 20.0
    assert metrics["total_assets"] == 5_000_000.0
    assert metrics["total_equity"] == 2_500_000.0
    assert metrics["total_liabilities"] == 2_500_000.0
    assert metrics["total_debt"] == 1_000_000.0
    assert metrics["operating_cash_flow"] == 350_000.0


def test_cvm_provider_appends_official_regulatory_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    record = parse_cvm_dfp_archive(_archive())[0]
    payload = {
        "updatedAt": "2026-09-18T00:00:00+00:00",
        "companies": {record["normalizedName"]: [record]},
    }
    path = source_index_path("cvm-dfp")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    company = GlobalCompany(
        country="BR", exchange="B3", mic_code="BVMF", currency="BRL",
        ticker="PETR4", name="Petroleo Brasileiro S.A. Petrobras",
    )
    enriched = CVMFundamentalsProvider().enrich_fundamentals(company)
    assert enriched.revenue == 1_000_000.0
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.report_scope == "consolidated"
    assert enriched.raw_provider_fields["cvm_cnpj"] == "33000167000101"
    source = enriched.sources[-1]
    assert source.provider == "cvm-open-data-dfp"
    assert source.source_type == "official_regulatory_financial_statement"
    assert source.quality == 0.98


def test_runtime_registers_brazil_official_provider(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    registry = build_registry()
    provider = registry.fundamentals("BR", "B3")
    assert "cvm-open-data-dfp" in provider.provider_id

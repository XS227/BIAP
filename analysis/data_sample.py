"""
Mock CODAL + TSETMC data for one fictitious company, standing in for the
real data-collection stage until CODAL/TSETMC API access is confirmed.
Replace with real fetchers once that's resolved.
"""

SAMPLE_COMPANY = {
    "ticker": "SAMPLE1",
    "name_fa": "شرکت نمونه صنایع",
    "name_en": "Sample Industries Co. (fictitious)",

    # --- CODAL-style: disclosures / periodic reports ---
    "codal": {
        "latest_report": "Q1 1405",
        "revenue_yoy_pct": 18.4,
        "net_margin_pct": 11.2,
        "net_margin_prev_pct": 9.8,
        "guidance_note": "management flagged raw-material cost pressure for next quarter",
        "related_party_flags": 0,
        "audit_opinion": "unqualified",
    },

    # --- TSETMC-style: market data ---
    "market": {
        "price": 18420,
        "price_52w_high": 24100,
        "price_52w_low": 14300,
        "pe": 6.8,
        "sector_avg_pe": 9.1,
        "market_cap_bn": 42.5,
        "avg_volume_30d": 1_250_000,
        "volume_today": 3_400_000,
    },
}

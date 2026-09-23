from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Germany country view: the official T7 venue files include foreign cross-listings.
# The ISIN prefix is the stable issuer/security-country identity available in the
# official file; keep DE securities only for BIAP's Germany country ranking.
replace_once(
    "analysis/global_markets/official_universe.py",
    '''        if len(isin) != 12 or not isin.isalnum():\n            isin = None\n        seen.add(ticker)\n''',
    '''        if len(isin) != 12 or not isin.isalnum():\n            continue\n        if country.upper() == "DE" and not isin.startswith("DE"):\n            continue\n        seen.add(ticker)\n''',
)
replace_once(
    "analysis/global_markets/official_universe.py",
    '''                "country_of_issue": str(row.get("Country Of Issue") or "").strip() or None,\n''',
    '''                "country_of_issue": str(row.get("Country Of Issue") or "").strip() or None,\n                "domestic_scope": f"ISIN:{country.upper()}",\n''',
)
replace_once(
    "analysis/global_markets/official_universe.py",
    '''                notes="Deutsche Boerse T7 official All tradable instruments; active common stock only.",\n''',
    '''                notes="Deutsche Boerse T7 official All tradable instruments; active common stock, domestic ISIN scope only.",\n''',
)

# Australia country view: the ASX directory includes ordinary foreign-domiciled
# cross-listings. Keep AU-ISIN ordinary fully-paid securities for the country scan.
replace_once(
    "analysis/global_markets/official_universe.py",
    '''        if len(isin) != 12 or not isin.isalnum():\n            continue\n        seen.add(ticker)\n        result.append(GlobalCompany(\n            country="AU",\n''',
    '''        if len(isin) != 12 or not isin.isalnum():\n            continue\n        if not isin.startswith("AU"):\n            continue\n        seen.add(ticker)\n        result.append(GlobalCompany(\n            country="AU",\n''',
)
replace_once(
    "analysis/global_markets/official_universe.py",
    '''                "asx_security_type": security_type,\n''',
    '''                "asx_security_type": security_type,\n                "domestic_scope": "ISIN:AU",\n''',
)
replace_once(
    "analysis/global_markets/official_universe.py",
    '''                notes="ASX complete ISIN directory; ordinary fully-paid securities only.",\n''',
    '''                notes="ASX complete ISIN directory; ordinary fully-paid Australian-ISIN securities only.",\n''',
)

# Universe semantics changed from venue-only to official domestic-country scope.
# Force persistent snapshots created under the old semantics to refresh.
replace_once(
    "analysis/global_markets/cached_universe.py",
    "CACHE_SCHEMA_VERSION = 8\n",
    "CACHE_SCHEMA_VERSION = 9\n",
)

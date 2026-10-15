"""Annual IFRS facts read directly from a filed SEC XBRL instance.

SEC ``companyfacts`` can lag a filer's newest annual report: for example, it
did not expose any fact from 20-F filings tagged with the IFRS 2025 taxonomy
(TSM FY2025, filed 2026-04-16) even months after filing. The SEC submissions
index and the EDGAR archive still carry that filing and its XBRL instance.

This module converts such an instance into companyfacts-shaped rows so the
existing foreign-issuer parser applies the same concept, form, freshness and
identity rules. It is deliberately strict:

* only annual 20-F/40-F (and amendments) flagged ``isXBRL`` by SEC are read;
* the instance's entity identifier must equal the already identity-verified CIK;
* only non-dimensional contexts are used (no segment/scenario members);
* durations must be a fiscal year (350-380 days); instants are balance sheet;
* only ``ifrs-full`` concepts; nil, non-numeric and duplicate-conflicting
  facts are dropped.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
from typing import Callable, Optional
import xml.etree.ElementTree as ET

import httpx

from .providers import GlobalProviderError
from .source_cache import data_root, enforce_cache_budget, online_first, write_bytes_atomic

SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
ANNUAL_FORMS = frozenset({"20-F", "20-F/A", "40-F", "40-F/A"})
US_GAAP_ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
_US_GAAP_NS_PREFIX = "http://fasb.org/us-gaap/"
_IFRS_NS_PREFIX = "https://xbrl.ifrs.org/taxonomy/"
_IFRS_NS_PREFIX_LEGACY = "http://xbrl.ifrs.org/taxonomy/"
_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _parse_date(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(text or "").strip()[:10])
    except ValueError:
        return None


def annual_xbrl_filings(submissions: dict, forms_allowed: frozenset = ANNUAL_FORMS) -> list[dict]:
    """Annual filings of ``forms_allowed`` flagged as XBRL, newest report period first."""
    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    rows: list[dict] = []
    for index, form in enumerate(forms):
        if form not in forms_allowed:
            continue

        def col(name: str):
            values = recent.get(name) or []
            return values[index] if index < len(values) else None

        if not col("isXBRL"):
            continue
        accession = str(col("accessionNumber") or "").strip()
        report_date = str(col("reportDate") or "").strip()
        if not accession or _parse_date(report_date) is None:
            continue
        rows.append({
            "form": form,
            "accession": accession,
            "reportDate": report_date,
            "filingDate": str(col("filingDate") or "").strip(),
            "primaryDocument": str(col("primaryDocument") or "").strip(),
        })
    rows.sort(key=lambda row: (row["reportDate"], row["filingDate"]), reverse=True)
    return rows


def instance_candidates(cik: int, filing: dict, index_payload: Optional[dict]) -> list[str]:
    """EDGAR URLs of the filing's XBRL instance, extracted-iXBRL first."""
    folder = f"{SEC_ARCHIVES_BASE}/{cik}/{filing['accession'].replace('-', '')}"
    names: list[str] = []
    items = (((index_payload or {}).get("directory") or {}).get("item")) or []
    listed = [str(item.get("name") or "") for item in items if isinstance(item, dict)]
    names.extend(name for name in listed if name.endswith("_htm.xml"))
    primary = filing.get("primaryDocument") or ""
    if primary.endswith(".htm"):
        derived = primary[: -len(".htm")] + "_htm.xml"
        if derived not in names and (not listed or derived in listed):
            names.append(derived)
    return [f"{folder}/{name}" for name in names]


def parse_instance(xml_bytes: bytes, *, cik: int, form: str, filed: str, taxonomy: str = "ifrs",
                   accession: str = "") -> dict:
    """Return ``{concept: {"units": {unit: [row, ...]}}}`` for ifrs-full (or us-gaap) facts."""
    prefixes = (_US_GAAP_NS_PREFIX,) if taxonomy == "us-gaap" else (_IFRS_NS_PREFIX, _IFRS_NS_PREFIX_LEGACY)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise GlobalProviderError("SEC XBRL instance is not valid XML") from exc

    contexts: dict[str, dict] = {}
    for node in root:
        if _local(node.tag) != "context":
            continue
        entity = next((child for child in node if _local(child.tag) == "entity"), None)
        period = next((child for child in node if _local(child.tag) == "period"), None)
        if entity is None or period is None:
            continue
        if any(_local(child.tag) == "segment" for child in entity):
            continue
        if any(_local(child.tag) == "scenario" for child in node):
            continue
        identifier = next((child for child in entity if _local(child.tag) == "identifier"), None)
        try:
            if identifier is None or int(str(identifier.text or "").strip()) != int(cik):
                continue
        except ValueError:
            continue
        values = {_local(child.tag): str(child.text or "").strip() for child in period}
        if "instant" in values:
            end = _parse_date(values["instant"])
            if end is None:
                continue
            contexts[node.attrib.get("id", "")] = {"end": end.isoformat()}
            continue
        start, end = _parse_date(values.get("startDate", "")), _parse_date(values.get("endDate", ""))
        if start is None or end is None or not 350 <= (end - start).days <= 380:
            continue
        contexts[node.attrib.get("id", "")] = {"start": start.isoformat(), "end": end.isoformat()}

    units: dict[str, str] = {}
    for node in root:
        if _local(node.tag) != "unit":
            continue
        measures = [str(m.text or "").strip().split(":")[-1] for m in node.iter() if _local(m.tag) == "measure"]
        divide = next((child for child in node if _local(child.tag) == "divide"), None)
        if divide is not None and len(measures) == 2:
            units[node.attrib.get("id", "")] = f"{measures[0]}/{measures[1]}"
        elif len(measures) == 1:
            units[node.attrib.get("id", "")] = measures[0]

    seen: dict[tuple[str, str, str, Optional[str]], float] = {}
    conflicts: set[tuple[str, str, str, Optional[str]]] = set()
    for node in root:
        namespace = _namespace(node.tag)
        if not namespace.startswith(prefixes):
            continue
        if node.attrib.get(_XSI_NIL) == "true":
            continue
        context = contexts.get(node.attrib.get("contextRef", ""))
        unit = units.get(node.attrib.get("unitRef", ""))
        if context is None or not unit:
            continue
        try:
            value = float(str(node.text or "").strip())
        except ValueError:
            continue
        key = (_local(node.tag), unit, context["end"], context.get("start"))
        if key in seen and seen[key] != value:
            conflicts.add(key)
        seen[key] = value

    return _rows_from_facts(seen, conflicts, form=form, filed=filed, accession=accession)


def _rows_from_facts(seen: dict, conflicts: set, *, form: str, filed: str, accession: str) -> dict:
    # Many 20-F filers add an unaudited single-year convenience translation
    # (e.g. TWD statements with a USD column). Keep only the primary reporting
    # currency -- the one carrying most monetary facts -- so metrics are never
    # mixed across currencies.
    currency_counts: dict[str, int] = {}
    for _, unit, _, _ in seen:
        currency = unit.split("/", 1)[0]
        if len(currency) == 3 and currency.isalpha() and currency.isupper():
            currency_counts[currency] = currency_counts.get(currency, 0) + 1
    primary_currency = max(currency_counts, key=currency_counts.get) if currency_counts else None

    facts: dict[str, dict] = {}
    fy = (_parse_date(filed) or date.today()).year
    for key, value in seen.items():
        if key in conflicts:
            continue
        concept, unit, end, start = key
        currency = unit.split("/", 1)[0]
        if currency in currency_counts and currency != primary_currency:
            continue
        row = {"val": int(value) if value.is_integer() else value, "end": end, "filed": filed,
               "form": form, "fp": "FY", "fy": fy, "frame": None}
        if accession:
            row["accn"] = accession
        if start:
            row["start"] = start
        facts.setdefault(concept, {"units": {}})["units"].setdefault(unit, []).append(row)
    return facts


def parse_ixbrl_document(html: bytes, *, cik: int, form: str, filed: str, accession: str = "") -> dict:
    """us-gaap facts from a filing's inline-XBRL primary document.

    Fallback for filings whose SEC-extracted ``_htm.xml`` instance is not
    well-formed. Same rules as ``parse_instance``: entity identifier equals the
    verified CIK, no dimensional facts, fiscal-year durations (350-380 days) or
    instants, nil/non-numeric and conflicting duplicates dropped.
    """
    from .ixbrl import extract_facts

    parsed, _ = extract_facts([html.decode("utf-8", "replace")])
    seen: dict = {}
    conflicts: set = set()
    for fact in parsed:
        dims = fact.get("dimensions") or {}
        if any(key not in {"concept", "entity", "period", "unit"} for key in dims):
            continue
        concept = str(dims.get("concept") or "")
        if not concept.startswith("us-gaap:"):
            continue
        try:
            if int(str(dims.get("entity") or "").rsplit(":", 1)[-1].strip()) != int(cik):
                continue
            value = float(fact["value"])
        except (ValueError, KeyError, TypeError):
            continue
        unit = str(dims.get("unit") or "").replace("iso4217:", "").replace("xbrli:", "")
        if not unit:
            continue
        parts = str(dims.get("period") or "").split("/")
        if len(parts) == 1:
            end, start = _parse_date(parts[0]), None
            if end is None:
                continue
        elif len(parts) == 2:
            start, end = _parse_date(parts[0]), _parse_date(parts[1])
            if start is None or end is None or not 350 <= (end - start).days <= 380:
                continue
        else:
            continue
        key = (concept.split(":", 1)[1], unit, end.isoformat(), start.isoformat() if start else None)
        if key in seen and seen[key] != value:
            conflicts.add(key)
        seen[key] = value
    return _rows_from_facts(seen, conflicts, form=form, filed=filed, accession=accession)


class SECFilingInstanceReader:
    """Fetch the newest annual XBRL instance (IFRS 20-F/40-F or US-GAAP 10-K) newer than companyfacts."""

    def __init__(self, *, get_json: Callable[[str], dict], user_agent: str, timeout: float = 60.0,
                 taxonomy: str = "ifrs") -> None:
        if taxonomy not in {"ifrs", "us-gaap"}:
            raise ValueError(f"unsupported XBRL taxonomy {taxonomy!r}")
        self.taxonomy = taxonomy
        self._get_json = get_json
        self.user_agent = user_agent
        self.timeout = max(10.0, float(timeout))

    @staticmethod
    def _cache_path(url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return data_root() / "cache" / "sec-edgar-instance" / f"{digest}.xml"

    def _get_bytes(self, url: str) -> bytes:
        # EDGAR archive documents are immutable once accepted; cache forever.
        path = self._cache_path(url)
        try:
            return path.read_bytes()
        except OSError:
            pass
        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"SEC XBRL instance request failed: {type(exc).__name__}") from exc
        body = response.content
        if online_first():
            return body
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, body)
        enforce_cache_budget(path.parent, env_var="BIAP_SEC_INSTANCE_CACHE_MAX_MB", default_mb=1024, suffixes=(".xml",))
        return body

    def newer_annual_facts(self, cik: int, newer_than: Optional[str]) -> tuple[dict, Optional[dict]]:
        """ifrs-full facts of the latest annual filing whose period is newer.

        Returns ``({}, None)`` when SEC lists no newer annual XBRL filing.
        """
        submissions = self._get_json(f"{SEC_SUBMISSIONS_BASE}/CIK{cik:010d}.json")
        for filing in annual_xbrl_filings(
            submissions, US_GAAP_ANNUAL_FORMS if self.taxonomy == "us-gaap" else ANNUAL_FORMS
        ):
            if newer_than and filing["reportDate"] <= newer_than:
                break
            folder = f"{SEC_ARCHIVES_BASE}/{cik}/{filing['accession'].replace('-', '')}"
            try:
                index_payload = self._get_json(f"{folder}/index.json")
            except GlobalProviderError:
                index_payload = None
            for url in instance_candidates(cik, filing, index_payload):
                try:
                    facts = parse_instance(self._get_bytes(url), cik=cik, form=filing["form"], filed=filing["filingDate"],
                                          taxonomy=self.taxonomy, accession=filing["accession"])
                except GlobalProviderError:
                    continue
                if facts:
                    return facts, {**filing, "instanceUrl": url,
                                   "readAt": datetime.now(timezone.utc).isoformat()}
            primary = filing.get("primaryDocument") or ""
            if self.taxonomy == "us-gaap" and primary.endswith(".htm"):
                url = f"{folder}/{primary}"
                try:
                    facts = parse_ixbrl_document(self._get_bytes(url), cik=cik, form=filing["form"],
                                                 filed=filing["filingDate"], accession=filing["accession"])
                except GlobalProviderError:
                    facts = {}
                if facts:
                    return facts, {**filing, "instanceUrl": url,
                                   "readAt": datetime.now(timezone.utc).isoformat()}
        return {}, None


def merge_facts(base: dict, extra: dict) -> dict:
    """Union of companyfacts-shaped concept maps (rows are appended)."""
    merged = {concept: {"units": {unit: list(rows) for unit, rows in (body.get("units") or {}).items()}}
              for concept, body in (base or {}).items() if isinstance(body, dict)}
    for concept, body in (extra or {}).items():
        target = merged.setdefault(concept, {"units": {}})["units"]
        for unit, rows in (body.get("units") or {}).items():
            target.setdefault(unit, []).extend(rows)
    return merged

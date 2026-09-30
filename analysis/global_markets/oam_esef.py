"""Official national-OAM ESEF annual-report provider for BIAP Global.

Why this exists
---------------
BIAP's European filing path read ESEF data only through filings.xbrl.org, an
independent *index* of ESEF filings. That index has not ingested FY2025 annual
reports for several whole countries (0 filings for SE and NO at audit time),
so every issuer there resolved to a >550-day-old FY2024 filing, the stale
guard correctly rejected it, and Evidence fell back to vendor metrics:
``missing=fundamental_source`` even though the issuer had lodged its official
FY2025 ESEF report with the national officially appointed mechanism (OAM).

This provider reads the ESEF package from the OAM itself:

* SE: Finansinspektionen "Börsinformation" (finanscentralen.fi.se), Sweden's
  OAM, searched by the issuer's Swedish organisation number from GLEIF.
* NO: Oslo Børs Newsweb, Norway's OAM, category ANNUAL FINANCIAL REPORT.

Identity is never ticker-only: the issuer LEI is resolved via
ISIN -> GLEIF (or explicit LEI / exact legal name) and the downloaded inline
XBRL report must itself declare that LEI as its reporting entity. Any
mismatch is rejected. Extraction reuses the shared ESEF normalization.
Nothing is fabricated: absent concepts stay None, filing dates are only set
when the OAM publishes them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlencode

import httpx

from .cached_esef import CachedESEFFundamentalsProvider
from .esef import _CONCEPTS
from .ixbrl import annual_period_end, extract_facts
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source
from .source_cache import data_root, read_json, write_json_atomic

USER_AGENT = "BIAP-Global/1.0 official-OAM ESEF evidence (+https://setai.no)"
MAX_PACKAGE_BYTES = 300 * 1024 * 1024
LISTING_TTL_SECONDS = 6 * 3600
_WANTED_CONCEPTS = {c.lower() for concepts in _CONCEPTS.values() for c in concepts}


@dataclass(frozen=True)
class OAMFiling:
    oam: str
    document_id: str
    package_url: str
    landing_url: str
    published_at: Optional[str] = None
    label: Optional[str] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OAMLocator(ABC):
    oam: str
    country: str

    def __init__(self, http: "OAMHttp") -> None:
        self.http = http

    @abstractmethod
    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        """Return official annual ESEF package candidates, newest first."""


class OAMHttp:
    """Small HTTP helper with a disk cache for listing responses."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    @staticmethod
    def cache_dir() -> Path:
        return data_root() / "cache" / "oam-esef"

    def cached_text(self, key: str, fetch) -> str:
        path = self.cache_dir() / "listing" / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        cached = read_json(path)
        if isinstance(cached, dict) and isinstance(cached.get("text"), str):
            try:
                age = (_utc_now() - datetime.fromisoformat(cached["fetchedAt"])).total_seconds()
            except (KeyError, TypeError, ValueError):
                age = None
            if age is not None and age <= LISTING_TTL_SECONDS:
                return cached["text"]
        try:
            text = fetch()
        except (httpx.HTTPError, GlobalProviderError) as exc:
            if isinstance(cached, dict) and isinstance(cached.get("text"), str):
                return cached["text"]
            raise GlobalProviderError(f"OAM listing request failed: {type(exc).__name__}") from exc
        write_json_atomic(path, {"key": key, "fetchedAt": _utc_now().isoformat(), "text": text})
        return text


class SwedenFinanscentralenLocator(OAMLocator):
    """Finansinspektionen Börsinformation (Swedish OAM)."""

    oam = "se-fi-finanscentralen"
    country = "SE"
    base = "https://finanscentralen.fi.se/search/"

    def _org_number(self, lei: str) -> Optional[str]:
        try:
            with self.http.client() as client:
                response = client.get(f"https://api.gleif.org/api/v1/lei-records/{lei}", headers={"Accept": "application/vnd.api+json"})
            response.raise_for_status()
            entity = response.json()["data"]["attributes"]["entity"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        value = str(entity.get("registeredAs") or "").strip()
        digits = re.sub(r"\D", "", value)
        return f"{digits[:6]}-{digits[6:]}" if len(digits) == 10 else None

    def _search_html(self, org_number: Optional[str], legal_name: str) -> str:
        def fetch() -> str:
            with self.http.client() as client:
                first = client.get(self.base + "Search.aspx")
                first.raise_for_status()
                fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', first.text))
                fields.update({
                    "ctl00$main$txtCompanyName": "" if org_number else legal_name,
                    "ctl00$main$txtOrganizationNumber": org_number or "",
                    "ctl00$main$txtOrganizationShortName": "",
                    "ctl00$main$btnSearch": "Sök",
                })
                response = client.post(self.base + "Search.aspx", content=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"})
                response.raise_for_status()
                return response.text
        return self.http.cached_text(f"fi-search:{org_number or legal_name}", fetch)

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        org = self._org_number(lei)
        html = self._search_html(org, legal_name)
        # The FI page shows the selected issuer's LEI; require it to equal the
        # GLEIF-resolved LEI before trusting any listed document.
        if lei.upper() not in html.upper():
            raise GlobalProviderError(f"FI Börsinformation has no issuer page for LEI {lei}")
        start = html.find("gvwYearReports")
        end = html.find("</table>", start)
        if start < 0 or end < 0:
            raise GlobalProviderError(f"FI Börsinformation lists no annual report for LEI {lei}")
        table = html[start:end]
        filings: list[OAMFiling] = []
        for row in re.findall(r"<tr class=\"textNormal\">(.*?)</tr>", table, flags=re.S):
            year_match = re.search(r"<td>\s*(\d{4}(?:/\d{2,4})?)\s*</td>", row)
            fids = re.findall(r"GetFile\.aspx\?fid=(\d+)'>([^<]+)</a>", row)
            if not year_match or not fids:
                continue
            # Prefer English, else first listed language; both are the same
            # lodged ESEF report in different presentation languages.
            fids.sort(key=lambda item: 0 if item[1].strip().lower().startswith("engelsk") else 1)
            fid, _lang = fids[0]
            url = f"{self.base}GetFile.aspx?fid={fid}"
            filings.append(OAMFiling(
                oam=self.oam,
                document_id=f"FI-FINANSCENTRALEN:{fid}",
                package_url=url,
                landing_url=url,
                published_at=None,
                label=f"Årsredovisning {year_match.group(1)}",
            ))
        if not filings:
            raise GlobalProviderError(f"FI Börsinformation lists no annual report file for LEI {lei}")
        return filings


class NorwayNewswebLocator(OAMLocator):
    """Oslo Børs Newsweb (Norwegian OAM), ANNUAL FINANCIAL REPORT category."""

    oam = "no-oslo-newsweb"
    country = "NO"
    api = "https://api3.oslo.oslobors.no/v1/newsreader/"
    annual_category = 1001

    @staticmethod
    def _signs(company: GlobalCompany) -> list[str]:
        ticker = company.ticker.strip().upper()
        signs = [ticker]
        base = re.split(r"[.\-\s]", ticker)[0]
        if base and base not in signs:
            signs.append(base)
        return signs

    def _json(self, path: str, params: dict) -> dict:
        key = "newsweb:" + path + "?" + urlencode(sorted(params.items()))

        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.api + path, params=params, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.text

        try:
            payload = json.loads(self.http.cached_text(key, fetch))
        except ValueError as exc:
            raise GlobalProviderError("Newsweb returned invalid JSON") from exc
        return payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        today = _utc_now().date()
        messages = []
        for sign in self._signs(company):
            data = self._json("list", {
                "issuer": sign,
                "category": self.annual_category,
                "fromDate": (today - timedelta(days=800)).isoformat(),
                "toDate": today.isoformat(),
            })
            # An unknown sign returns every issuer; keep exact-sign rows only.
            rows = [m for m in data.get("messages") or [] if str(m.get("issuerSign") or "").upper() == sign]
            if rows:
                messages = rows
                break
        filings: list[OAMFiling] = []
        for message in sorted(messages, key=lambda m: str(m.get("publishedTime") or ""), reverse=True):
            if message.get("correctedByMessageId"):
                continue
            message_id = message.get("messageId")
            detail = self._json("message", {"messageId": message_id}).get("message") or {}
            for attachment in detail.get("attachments") or []:
                name = str(attachment.get("name") or "")
                if not name.lower().endswith(".zip"):
                    continue
                url = f"{self.api}attachment?messageId={message_id}&attachmentId={attachment.get('id')}"
                filings.append(OAMFiling(
                    oam=self.oam,
                    document_id=f"NEWSWEB:{message_id}:{attachment.get('id')}",
                    package_url=url,
                    landing_url=f"https://newsweb.oslobors.no/message/{message_id}",
                    published_at=str(detail.get("publishedTime") or message.get("publishedTime") or "") or None,
                    label=str(detail.get("title") or "")[:200] or None,
                ))
        if not filings:
            raise GlobalProviderError(f"Newsweb lists no annual ESEF package for {company.ticker}")
        return filings


def _report_member(archive: zipfile.ZipFile) -> Optional[str]:
    names = [n for n in archive.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")) and not n.endswith("/")]
    in_reports = [n for n in names if "/reports/" in n.lower() or n.lower().startswith("reports/")]
    pool = in_reports or names
    return max(pool, key=lambda n: archive.getinfo(n).file_size) if pool else None


class NationalOAMESEFProvider(CachedESEFFundamentalsProvider):
    """ESEF fundamentals read from the issuer's national OAM filing."""

    provider_id = "official-oam-esef-ixbrl-v1"

    def __init__(self, *, timeout: float = 60.0, locators: Optional[Iterable[OAMLocator]] = None) -> None:
        super().__init__(timeout=min(timeout, 20.0))
        self.http = OAMHttp(timeout=timeout)
        chosen = list(locators) if locators is not None else [SwedenFinanscentralenLocator(self.http), NorwayNewswebLocator(self.http)]
        self.locators = {locator.country: locator for locator in chosen}

    def supports(self, country: str) -> bool:
        return country.upper() in self.locators

    # -- package handling -------------------------------------------------
    def _facts_cache_path(self, filing: OAMFiling) -> Path:
        return OAMHttp.cache_dir() / "packages" / (hashlib.sha256(filing.document_id.encode()).hexdigest() + ".json")

    def _download(self, url: str, target: Path) -> None:
        size = 0
        try:
            with self.http.client() as client, client.stream("GET", url) as response, target.open("wb") as out:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_PACKAGE_BYTES:
                        raise GlobalProviderError("OAM ESEF package exceeds size limit")
                    out.write(chunk)
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"OAM package download failed: {type(exc).__name__}") from exc

    def package_facts(self, filing: OAMFiling) -> dict:
        """Facts of one immutable OAM document, parsed once and cached."""
        path = self._facts_cache_path(filing)
        cached = read_json(path)
        if isinstance(cached, dict) and cached.get("schemaVersion") == 1 and isinstance(cached.get("facts"), list):
            return cached
        tmp_dir = OAMHttp.cache_dir() / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".zip") as handle:
            target = Path(handle.name)
            self._download(filing.package_url, target)
            try:
                archive = zipfile.ZipFile(target)
            except zipfile.BadZipFile as exc:
                raise GlobalProviderError("OAM document is not an ESEF zip package") from exc
            with archive:
                payload = self._parse_archive(filing, archive)
        write_json_atomic(path, payload)
        return payload

    def _parse_archive(self, filing: OAMFiling, archive: zipfile.ZipFile) -> dict:
        member = _report_member(archive)
        if member is None:
            raise GlobalProviderError("OAM ESEF package contains no XHTML report")
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            facts, entities = extract_facts(iter(lambda: text.read(1 << 20), ""))
        kept = [f for f in facts if str(f["dimensions"].get("concept") or "").lower() in _WANTED_CONCEPTS]
        return {
            "schemaVersion": 1,
            "documentId": filing.document_id,
            "packageUrl": filing.package_url,
            "reportFile": member,
            "entities": sorted(entities),
            "parsedAt": _utc_now().isoformat(),
            "factCount": len(facts),
            "facts": kept,
        }

    # -- provider ------------------------------------------------------------
    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        locator = self.locators.get(company.country.upper())
        if locator is None:
            raise GlobalProviderError(f"no official OAM ESEF locator for {company.country}")
        lei, legal_name = self._resolve_lei(company)
        filings = locator.annual_filings(company, lei, legal_name)
        errors: list[str] = []
        for filing in filings[:3]:
            try:
                package = self.package_facts(filing)
            except GlobalProviderError as exc:
                errors.append(f"{filing.document_id}: {exc}")
                continue
            if lei.upper() not in {e.upper() for e in package.get("entities") or []}:
                errors.append(f"{filing.document_id}: report entity {package.get('entities')} != LEI {lei}")
                continue
            facts = package["facts"]
            period_text = annual_period_end(facts, ("ifrs-full:ProfitLoss", "ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"))
            if not period_text:
                errors.append(f"{filing.document_id}: no annual IFRS duration facts")
                continue
            period_end = date.fromisoformat(period_text)
            normalized = self.normalized_fields(facts, period_end)
            reporting_currency = normalized.pop("reporting_currency")
            retrieved = str(package.get("parsedAt") or _utc_now().isoformat())
            enriched = replace(
                company,
                name=legal_name or company.name,
                lei=lei,
                reporting_currency=reporting_currency or company.reporting_currency,
                **normalized,
                filing_period_end=period_end.isoformat(),
                filing_observed_at=filing.published_at,
                report_scope=None,
                raw_provider_fields={
                    **company.raw_provider_fields,
                    "oam": filing.oam,
                    "oam_document_id": filing.document_id,
                    "oam_package_url": filing.package_url,
                    "oam_report_file": package.get("reportFile"),
                    "oam_published_at": filing.published_at,
                    "oam_retrieved_at": retrieved,
                    "oam_entity_lei_verified": True,
                },
            )
            return append_source(enriched, SourceEvidence(
                provider=f"official-oam-{filing.oam}",
                source_type="official_regulatory_xbrl",
                source_id=filing.document_id,
                source_url=filing.landing_url,
                observed_at=filing.published_at or retrieved,
                period_end=period_end.isoformat(),
                quality=0.95,
                notes=(
                    f"Issuer ESEF annual report lodged with national OAM {filing.oam}; "
                    f"inline XBRL entity LEI={lei} verified; {filing.label or ''}".strip()
                ),
            ))
        raise GlobalProviderError("official OAM ESEF package unusable: " + "; ".join(errors)[:600])

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
* FR: AMF/DILA info-financiere.gouv.fr, France's OAM, indexed by issuer LEI.
* ES: CNMV annual financial reports, Spain's OAM, listed by issuer NIF (GLEIF).
* IT: both Consob-authorized storages (1INFO API and eMarket STORAGE),
  category 1.1 annual ESEF packages.

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
from html import unescape as html_unescape
import base64
import hashlib
import io
import json
import re
import tempfile
import threading
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from .cached_esef import CachedESEFFundamentalsProvider
from .esef import _CONCEPTS, concept_is_relevant
from .ixbrl import annual_period_end, extract_facts
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source
from .source_cache import data_root, read_json, write_json_atomic

USER_AGENT = "BIAP-Global/1.0 official-OAM ESEF evidence (+https://setai.no)"
MAX_PACKAGE_BYTES = 300 * 1024 * 1024
LISTING_TTL_SECONDS = 6 * 3600
# v3: bank equity/operating-income concepts kept (esef._CONCEPTS additions).
PACKAGE_SCHEMA_VERSION = 3
_ROME = ZoneInfo("Europe/Rome")
_WANTED_CONCEPTS = {c.lower() for concepts in _CONCEPTS.values() for c in concepts}


@dataclass(frozen=True)
class OAMFiling:
    oam: str
    document_id: str
    package_url: str
    landing_url: str
    published_at: Optional[str] = None
    label: Optional[str] = None
    # "consolidated" / "separate" when the OAM states it; None otherwise.
    scope: Optional[str] = None


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
        # IPv4 only: the production VPS has an IPv6 route on which FI's OAM
        # stalls every response until the client read timeout (measured 20-90
        # s per request vs 0.09 s over IPv4). httpx has no Happy-Eyeballs.
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
        )

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
        # The issuer page must match the GLEIF-resolved legal entity either by
        # LEI or by the Swedish organisation number GLEIF records for that LEI
        # (FI's displayed LEI is occasionally a subsidiary's). The downloaded
        # report's own inline-XBRL entity LEI remains the hard gate.
        tail = html[html.find("Organisationsnummer"):] if "Organisationsnummer" in html else ""
        match = re.search(r"(\d{6}-\d{4})", tail)
        page_org = match.group(1) if match else None
        if lei.upper() not in html.upper() and not (org and page_org == org):
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
        # Share-class tickers (ODFB, SCHA/SCHB) are filed under the issuer
        # sign; rows are still kept only on an exact issuer-sign match.
        if len(base) > 3 and base[-1] in "AB" and base[:-1] not in signs:
            signs.append(base[:-1])
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
        sign_used = messages[0]["issuerSign"] if messages else None
        # Issuers occasionally file the annual report under another
        # category (e.g. Elkem FY2025 as a non-regulatory press release).
        # Accept those only when an attachment is the LEI-named ESEF
        # package; the embedded LEI is verified on download anyway.
        for sign in ([sign_used] if sign_used else self._signs(company)):
            data = self._json("list", {
                "issuer": sign,
                "fromDate": (today - timedelta(days=500)).isoformat(),
                "toDate": today.isoformat(),
            })
            extra = [m for m in data.get("messages") or []
                     if str(m.get("issuerSign") or "").upper() == sign
                     and re.search(r"annual|årsrapport|arsrapport|integrated report", str(m.get("title") or ""), re.I)
                     and m.get("messageId") not in {x.get("messageId") for x in messages}]
            if extra:
                messages = messages + [dict(m, _lei_named_only=True) for m in extra]
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
                if message.get("_lei_named_only") and not name.upper().startswith(lei.upper()):
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


class FranceAMFInfoFinanciereLocator(OAMLocator):
    """AMF/DILA info-financiere.gouv.fr (French OAM), queried by issuer LEI.

    The OAM's open-data feed indexes every regulated-information document with
    the depositing issuer's LEI and ISIN. Annual financial reports (003000) and
    universal registration documents (300005, which embed the annual financial
    report) lodged as ESEF zip/XHTML are candidates; PDFs are never ESEF.
    """

    oam = "fr-amf-info-financiere"
    country = "FR"
    api = "https://www.info-financiere.gouv.fr/api/explore/v2.1/catalog/datasets/flux-amf-new-prod/records"
    annual_subtypes = ("003000", "300005")

    def _records(self, field: str, value: str) -> list[dict]:
        subtypes = " or ".join(f'informationdeposee_inf_stp_pri="{code}"' for code in self.annual_subtypes)
        params = {
            "where": f'{field}="{value}" and ({subtypes})',
            "order_by": "informationdeposee_inf_dat_emt desc",
            "limit": 40,
        }
        key = "amf:" + urlencode(sorted(params.items()))

        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.api, params=params, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.text

        try:
            payload = json.loads(self.http.cached_text(key, fetch))
        except ValueError as exc:
            raise GlobalProviderError("AMF info-financiere returned invalid JSON") from exc
        rows = payload.get("results") if isinstance(payload, dict) else None
        return [row for row in rows or [] if isinstance(row, dict)]

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        rows = self._records("identificationsociete_iso_cd_lei", lei.upper())
        if not rows and company.isin:
            # Older depositor records omit the LEI; the ISIN is the issuer's
            # own security identifier. The report's inline-XBRL entity LEI is
            # still verified against GLEIF before any value is used.
            rows = self._records("identificationsociete_iso_cd_isi", company.isin.upper())
        cutoff = (_utc_now().date() - timedelta(days=800)).isoformat()
        filings: list[OAMFiling] = []
        seen: set[str] = set()
        for row in rows:
            url = str(row.get("url_de_recuperation") or "").strip()
            published = str(row.get("informationdeposee_inf_dat_emt") or "") or None
            if not url.lower().endswith((".zip", ".xhtml", ".html")) or url in seen:
                continue
            if published and published[:10] < cutoff:
                continue
            seen.add(url)
            name = str(row.get("fichierdecontenu_inf_fic_nom") or url.rsplit("/", 1)[-1])
            filings.append(OAMFiling(
                oam=self.oam,
                document_id=f"AMF-INFOFI:{name}",
                package_url=url,
                landing_url=url,
                published_at=published,
                label=str(row.get("informationdeposee_inf_tit_inf") or "")[:200] or None,
            ))
        if not filings:
            raise GlobalProviderError(f"AMF info-financiere lists no ESEF annual financial report for LEI {lei}")
        return filings


class SpainCNMVLocator(OAMLocator):
    """CNMV "Informes financieros anuales" (Spanish OAM), listed per issuer NIF.

    GLEIF records the Spanish issuer's NIF as ``registeredAs``. The CNMV list
    links each period's ESEF annual financial report as consolidated and
    individual XHTML; the consolidated report is preferred (group accounts).
    """

    oam = "es-cnmv-ifa"
    country = "ES"
    listing = "https://www.cnmv.es/portal/Consultas/IFA/ListadoIFA"

    def _nif(self, lei: str) -> Optional[str]:
        try:
            with self.http.client() as client:
                response = client.get(f"https://api.gleif.org/api/v1/lei-records/{lei}", headers={"Accept": "application/vnd.api+json"})
            response.raise_for_status()
            entity = response.json()["data"]["attributes"]["entity"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        value = re.sub(r"[^A-Z0-9]", "", str(entity.get("registeredAs") or "").upper())
        if value.startswith("ES") and len(value) == 11:
            value = value[2:]
        return value if re.fullmatch(r"[A-Z]\d{7}[A-Z0-9]", value) else None

    def _nif_by_name(self, legal_name: str, isin: Optional[str]) -> Optional[str]:
        """CNMV entity search by GLEIF legal name. A candidate NIF is accepted
        only when CNMV's own ISIN register for it lists the instrument's ISIN,
        and only when exactly one candidate does."""
        if not legal_name or not isin:
            return None
        search = "https://www.cnmv.es/portal/Consultas/BusquedaPorEntidad"
        core = re.sub(r"[,\s]+(S\.?\s?A\.?(\s?U\.?)?|SOCIMI,?\s?S\.?A\.?)$", "", legal_name.strip(), flags=re.I)
        candidates: list[str] = []
        for term in dict.fromkeys([legal_name.strip(), core]):
            def fetch(term: str = term) -> str:
                with self.http.client() as client:
                    first = client.get(search)
                    first.raise_for_status()
                    fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', first.text))
                    fields.update({"ctl00$ContentPrincipal$txtBusqueda": term, "ctl00$ContentPrincipal$btnBuscar": "Buscar"})
                    response = client.post(search, content=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"})
                    response.raise_for_status()
                    return str(response.url) + "\n" + response.text

            try:
                text = self.http.cached_text(f"cnmv-entity:{term.upper()}", fetch)
            except GlobalProviderError:
                continue
            found = re.findall(r"nif=([A-Z]-?\d{7}[A-Z0-9])", text.split("\n", 1)[0], flags=re.I)
            found += re.findall(r'<option[^>]*value="([A-Z]-?\d{7}[A-Z0-9])"', text, flags=re.I)
            candidates = list(dict.fromkeys(n.upper() for n in found))
            if candidates:
                break
        verified = []
        for nif in candidates[:6]:
            def fetch_isins(nif: str = nif) -> str:
                with self.http.client() as client:
                    response = client.get("https://www.cnmv.es/portal/ancv/isin", params={"nif": nif})
                response.raise_for_status()
                return response.text

            try:
                if isin.upper() in self.http.cached_text(f"cnmv-isins:{nif}", fetch_isins).upper():
                    verified.append(nif)
            except GlobalProviderError:
                continue
        return verified[0] if len(verified) == 1 else None

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        nif = self._nif(lei) or self._nif_by_name(legal_name, company.isin)
        if not nif:
            raise GlobalProviderError(f"no CNMV NIF verifiable for LEI {lei} (GLEIF registeredAs / CNMV ISIN register)")

        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.listing, params={"id": "0", "nif": nif})
            response.raise_for_status()
            return response.text

        html = self.http.cached_text(f"cnmv-ifa:{nif}", fetch)
        start = html.find("gridInformes")
        body = html[start:html.find("</table>", start)] if start >= 0 else ""
        filings: list[OAMFiling] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S):
            cells = {k: v for k, v in re.findall(r'<td data-th="([^"]+)">(.*?)</td>', row, flags=re.S)}
            reg = re.sub(r"\D", "", cells.get("Nº Registro Oficial", ""))
            period = re.search(r"(\d{2})/(\d{2})/(\d{4})", cells.get("Fecha Estados Financieros", ""))
            published = re.search(r"(\d{2})/(\d{2})/(\d{4})", cells.get("Fecha de publicación (1)", ""))
            links = dict((kind, url) for url, kind in re.findall(r'href="([^"]+)"[^>]*>(Consolidada|Individual)</a>', cells.get("Tipo", "")))
            kind = "Consolidada" if "Consolidada" in links else "Individual" if "Individual" in links else None
            if not reg or not period or kind is None:
                continue
            url = links[kind].replace("&amp;", "&")
            filings.append(OAMFiling(
                oam=self.oam,
                document_id=f"CNMV-IFA:{reg}:{'consolidated' if kind == 'Consolidada' else 'individual'}",
                package_url=url,
                landing_url=f"{self.listing}?id=0&nif={nif}",
                published_at=(f"{published.group(3)}-{published.group(2)}-{published.group(1)}" if published else None),
                label=f"Informe financiero anual {period.group(3)}-{period.group(2)}-{period.group(1)} ({kind.lower()})",
            ))
        if not filings:
            raise GlobalProviderError(f"CNMV lists no ESEF annual financial report for NIF {nif} (LEI {lei})")
        filings.sort(key=lambda f: f.label or "", reverse=True)
        return filings


# Statutory qualifiers / status words GLEIF keeps in the legal name while both
# Italian storages register the issuer without them.
_IT_NAME_QUALIFIERS = re.compile(
    r"[\s,\-]*(?:IN\s+LIQUIDAZIONE|IN\s+AMMINISTRAZIONE\s+STRAORDINARIA|SOCIETA'?\s+BENEFIT|S\.?\s?B\.?)\s*$"
)
_IT_LEGAL_FORM = re.compile(r"\b(?:S\.?\s?P\.?\s?A\.?|SOCIETA'?\s+PER\s+AZIONI|N\.?\s?V\.?|S\.?\s?A\.?)\s*$")
# Clauses that introduce another statutory name of the same company:
# "X S.P.A. IN FORMA ABBREVIATA [ANCHE] Y", "X S.P.A. IN SIGLA Y",
# '"X" (IN FORMA ABBREVIATA "Y")', "X SPA O IN FORMA ABBREVIATA Y O Z",
# "X IN BREVE Y", "X IN VIA BREVE Y OVVERO Z", "X CON LA SIGLA Y",
# "X ABBREVIABILE IN Y E IN Z", "X (IN FORMA ESTESA Y)".
_IT_ALIAS_CLAUSE = re.compile(
    r"[\s,(]*\b(?:O\s*,?\s+|E\s+)?(?:IN\s+FORMA\s+(?:ABBREVIATA|ESTESA)|IN\s+SIGLA|IN\s+(?:VIA\s+)?BREVE|"
    r"CON\s+LA\s+SIGLA|ABBREVIABILE\s+IN|OV\s?VERO)(?:\s+ANCHE)?\s*[:,]?\s*"
)
# Italian REIT status (Societa' di Investimento Immobiliare Quotata), e.g.
# "IGD SIIQ S.P.A."; registers list the issuer without it.
_IT_SIIQ = re.compile(r"\s+SIIQ(?=\s+(?:S\.?\s?P\.?\s?A\.?|SOCIETA'?\s+PER\s+AZIONI)\s*$)")


def _it_name_core(value: str) -> str:
    # The legal form is removed only as a separate trailing word, so 'SESA'
    # stays 'SESA' (not 'SE') while 'SESA S.P.A.' / 'Sesa Spa' become 'SESA'.
    text = re.sub(r"\s+", " ", str(value or "").upper().replace("’", "'").replace("À", "A'"))
    text = text.strip(" \"“”'()")  # GLEIF may quote the whole name
    return re.sub(r"[^A-Z0-9]+", "", _IT_LEGAL_FORM.sub("", text))


def _it_clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \"“”'()").strip()


def _it_name_variants(legal_name: str) -> list[str]:
    """Register-name candidates derived only from the GLEIF legal name.

    e.g. 'DANIELI & C. OFFICINE MECCANICHE S.P.A. IN FORMA ABBREVIATA ANCHE
    "DANIELI & C. S.P.A."' -> also 'DANIELI & C. S.P.A.'; 'CIR S.P.A. -
    COMPAGNIE INDUSTRIALI RIUNITE' -> also 'CIR S.P.A.'; 'X S.P.A. IN
    LIQUIDAZIONE' / 'X S.P.A. SOCIETA' BENEFIT' -> also 'X S.P.A.'.
    """
    text = re.sub(r"\s+", " ", str(legal_name or "").upper().replace("’", "'").replace("“", '"').replace("”", '"')).strip()
    variants = [text]
    if _IT_ALIAS_CLAUSE.search(text):
        # Each listed name is a variant. A quoted name is taken whole (it may
        # contain ' E '); otherwise 'Y SPA O Z S.P.A.' / 'Y E IN Z' list two.
        for part in _IT_ALIAS_CLAUSE.split(text):
            quoted = re.findall(r'"([^"]+)"', part)
            names = quoted or re.split(r"\s*,?\s+(?:O|E\s+IN)\s+(?:ANCHE\s+)?", part)
            variants += [_it_clean_name(name) for name in names]
    for value in list(variants):
        stripped = _IT_NAME_QUALIFIERS.sub("", value).strip()
        if stripped != value:
            variants.append(stripped)
    for value in list(variants):
        stripped = _IT_SIIQ.sub("", value)
        if stripped != value:
            variants.append(stripped)
    for value in list(variants):
        head = value.split(" - ", 1)[0].strip()
        if head != value and _IT_LEGAL_FORM.search(head):
            variants.append(head)
    return [v for v in dict.fromkeys(variants) if v]


def _it_unique_register_id(
    legal_name: str, register: Iterable[tuple[str, str]], storage: str, other_names: Iterable[str] = (),
    *, register_parts: bool = False,
) -> str:
    """The one register id whose name matches any GLEIF-derived variant.

    ``other_names`` are GLEIF otherNames of the same LEI (e.g. the previous
    legal name 'MONDO TV S.P.A.' of 'MONDO TV S.P.A. ICC').
    """
    cores = {_it_name_core(v) for name in (legal_name, *other_names) for v in _it_name_variants(name)} - {""}

    def register_cores(name: str) -> set[str]:
        # 'IGD - IMMOBILIARE GRANDE DISTRIBUZIONE': acronym and long name.
        parts = [name, *name.split(" - ")] if register_parts else [name]
        return {_it_name_core(part) for part in parts}

    matches = {key for key, name in register if register_cores(name) & cores}
    if len(matches) != 1:
        raise GlobalProviderError(f"{storage} issuer identity is not uniquely resolved for {legal_name!r}")
    return next(iter(matches))


def _it_register_id(
    http: "OAMHttp", lei: str, legal_name: str, register: list[tuple[str, str]], storage: str,
) -> str:
    """Resolve on the legal name, widening only while nothing matched uniquely.

    Tiers: GLEIF legal-name variants; plus GLEIF otherNames; plus the halves
    of 'ACRONYM - LONG NAME' register entries. A name that resolves at an
    earlier tier is never widened, so later tiers cannot make an existing
    match ambiguous, and every tier still requires exactly one register id.
    """
    try:
        return _it_unique_register_id(legal_name, register, storage)
    except GlobalProviderError:
        pass
    other_names = _gleif_other_names(http, lei) if lei else []
    if other_names:
        try:
            return _it_unique_register_id(legal_name, register, storage, other_names)
        except GlobalProviderError:
            pass
    # Last resort: register entries written 'ACRONYM - LONG NAME'.
    return _it_unique_register_id(legal_name, register, storage, other_names, register_parts=True)


def _gleif_other_names(http: "OAMHttp", lei: str) -> list[str]:
    """GLEIF otherNames of this LEI; empty when GLEIF is unreachable."""
    def fetch() -> str:
        with http.client() as client:
            response = client.get(f"https://api.gleif.org/api/v1/lei-records/{lei}", headers={"Accept": "application/vnd.api+json"})
        response.raise_for_status()
        return response.text
    try:
        entity = json.loads(http.cached_text(f"gleif-record:{lei.upper()}", fetch))["data"]["attributes"]["entity"]
    except (GlobalProviderError, ValueError, KeyError, TypeError):
        return []
    return [str(row.get("name") or "") for row in entity.get("otherNames") or [] if isinstance(row, dict) and row.get("name")]


def _it_title_scope(title: str) -> Optional[str]:
    """Statement scope stated by an Italian storage title, if any.

    "Bilancio d'esercizio" / "separato" is the parent-only accounts; a group
    must never be scored on them while its consolidated report is available.
    """
    text = str(title or "").lower()
    if "consolidat" in text:
        return "consolidated"
    if re.search(r"bilancio\s+d(?:i\s+|.)esercizio|separat|resoconti dell.esercizio|parent company", text):
        return "separate"
    return None


def _it_filing_rank(filing: OAMFiling) -> tuple:
    # Newest reporting cycle first (annual reports publish in year N+1);
    # within one cycle prefer consolidated, then unstated, then parent-only.
    published = filing.published_at or ""
    scope_rank = {"consolidated": 2, None: 1}.get(filing.scope, 0)
    return (published[:4], scope_rank, published)


class Italy1InfoLocator(OAMLocator):
    """1INFO authorized Italian regulated-information storage.

    Only annual rows carrying protocolCodeXbrl are accepted by this ESEF
    adapter. PDF-only annual reports remain for a separately verified issuer
    parser and are never promoted to XBRL evidence.
    """

    oam = "it-1info"
    country = "IT"
    root = "https://www.1info.it/PORTALE1INFO"
    companies_api = root + "/API/companies/documenti"
    documents_api = root + "/API/Documenti"
    viewer = "https://www.1info.it/PdfViewer/PdfShow.aspx"

    @staticmethod
    def _name_core(value: str) -> str:
        return _it_name_core(value)

    def _issuer_id(self, legal_name: str, lei: str = "") -> int:
        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.companies_api, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.text
        try:
            rows = json.loads(self.http.cached_text("1info:companies", fetch))
        except ValueError as exc:
            raise GlobalProviderError("1INFO issuer list returned invalid JSON") from exc
        register = [
            (str(row["ndg"]), str(row.get("descrizione") or ""))
            for row in rows or [] if isinstance(row, dict) and row.get("ndg") is not None
        ]
        return int(_it_register_id(self.http, lei, legal_name, register, "1INFO"))

    @staticmethod
    def _datatable_form(ndg: int) -> dict[str, str]:
        form: dict[str, str] = {
            "draw": "1", "start": "0", "length": "60",
            "search[value]": "", "search[regex]": "false",
            "order[0][column]": "2", "order[0][dir]": "desc",
            "SearchFilter[emittente][0]": str(ndg),
            "SearchFilter[categoria][0]": "1.1",
        }
        columns = ("", "mittente", "dataStoccaggio", "oggetto", "", "")
        for index, data in enumerate(columns):
            form[f"columns[{index}][data]"] = data
            form[f"columns[{index}][name]"] = ""
            form[f"columns[{index}][searchable]"] = "true"
            form[f"columns[{index}][orderable]"] = "true"
            form[f"columns[{index}][search][value]"] = ""
            form[f"columns[{index}][search][regex]"] = "false"
        return form

    def _rows(self, ndg: int) -> list[dict]:
        form = self._datatable_form(ndg)
        def fetch() -> str:
            with self.http.client() as client:
                response = client.post(
                    self.documents_api,
                    data=form,
                    headers={
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": self.root,
                    },
                )
            response.raise_for_status()
            return response.text
        try:
            payload = json.loads(self.http.cached_text(f"1info:annual:{ndg}", fetch))
        except ValueError as exc:
            raise GlobalProviderError("1INFO annual-document API returned invalid JSON") from exc
        rows = payload.get("data") if isinstance(payload, dict) else None
        return [row for row in rows or [] if isinstance(row, dict) and row.get("ndg") == ndg]

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        ndg = self._issuer_id(legal_name, lei)
        filings: list[OAMFiling] = []
        for row in self._rows(ndg):
            protocol = str(row.get("protocolCodeXbrl") or "").strip()
            # .xbri is the ESEF report-package extension (a zip), as on eMarket.
            if not protocol or not protocol.lower().endswith((".zip", ".xbri", ".xhtml", ".html", ".htm")):
                continue
            try:
                exercise_ts = int(row.get("dataEsercizio") or 0)
                stored_ts = int(row.get("dataStoccaggio") or 0)
            except (TypeError, ValueError):
                continue
            if exercise_ts <= 0:
                continue
            exercise_year = datetime.fromtimestamp(exercise_ts, tz=timezone.utc).year
            published = datetime.fromtimestamp(stored_ts, tz=timezone.utc).isoformat() if stored_ts > 0 else None
            package_url = self.viewer + "?" + urlencode({
                "service": "",
                "type": "documenti",
                "year": exercise_year,
                "file": protocol,
                "download": 1,
            })
            label = str(row.get("oggetto") or f"Annual financial report {exercise_year}")[:220]
            filings.append(OAMFiling(
                oam=self.oam,
                document_id=f"1INFO:{protocol}",
                package_url=package_url,
                landing_url=self.root + "#documenti",
                published_at=published,
                label=label,
                scope="consolidated" if row.get("bilancio_consolidato") == 1 else _it_title_scope(label),
            ))
        if not filings:
            raise GlobalProviderError(f"1INFO lists no annual ESEF package for {legal_name} (LEI {lei})")
        filings.sort(key=lambda filing: filing.published_at or "", reverse=True)
        return filings


class ItalyEMarketStorageLocator(OAMLocator):
    """eMarket STORAGE (Teleborsa), Italy's other Consob-authorized storage.

    Issuers choose one authorized storage mechanism; Intesa Sanpaolo, ERG and
    BPER (since 2024) lodge their annual ESEF packages here, not on 1INFO.
    Rows in category 1.1 linking an ``/xbrl/`` zip/xbri are ESEF candidates;
    PDFs never are. Some issuers lodge the ESEF package under category REGEM
    (Banca IFIS FY2025, 180048/180050); ESEF exists only for annual financial
    reports, so an ``/xbrl/`` package there is a candidate too and passes the
    same LEI and annual-period gates. Issuer identity is the storage's own
    issuer register, matched uniquely on the GLEIF legal name.
    """

    oam = "it-emarket-storage"
    country = "IT"
    root = "https://www.emarketstorage.it"
    documents = root + "/it/documenti"
    annual_category = "100"  # 1.1 annual financial reports and audit reports
    regem_category = "150"  # REGEM: other regulated information (art. 65-ter)

    def _get(self, key: str, params: Optional[dict] = None) -> str:
        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.documents, params=params)
            response.raise_for_status()
            return response.text
        return self.http.cached_text(key, fetch)

    def _issuer_id(self, legal_name: str, lei: str = "") -> str:
        html = self._get("emarket:issuers")
        start = html.find('id="edit-azienda"')
        select = html[start:html.find("</select>", start)] if start >= 0 else ""
        register = [(value, html_unescape(name)) for value, name in re.findall(r'<option value="(\d+)"[^>]*>([^<]*)<', select)]
        return _it_register_id(self.http, lei, legal_name, register, "eMarket STORAGE")

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        issuer = self._issuer_id(legal_name, lei)
        listings = [(self.annual_category, self._get(f"emarket:annual:{issuer}", {"categoria": self.annual_category, "azienda": issuer}))]
        try:
            listings.append((self.regem_category, self._get(f"emarket:regem:{issuer}", {"categoria": self.regem_category, "azienda": issuer})))
        except GlobalProviderError:
            pass  # category 1.1 remains the primary listing
        filings: list[OAMFiling] = []
        seen: set[str] = set()
        blocks = [(category, block) for category, html in listings for block in re.split(r'<div class="views-row">', html)[1:]]
        for category, block in blocks:
            protocol = re.search(r'data-protocollo="(\d+)"', block)
            issuer_link = re.search(r'comunicati-finanziari\?azienda=(\d+)', block)
            link = re.search(r'href="(/sites/default/files/xbrl/[^"]+\.(?:zip|xbri|xhtml|html))"', block, flags=re.I)
            stamp = re.search(r'class="datetime">\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}):(\d{2})', block)
            title = re.search(r'class="news-title">(.*?)</div>', block, flags=re.S)
            if not protocol or not link or (issuer_link and issuer_link.group(1) != issuer) or protocol.group(1) in seen:
                continue
            seen.add(protocol.group(1))
            label = html_unescape(re.sub(r"<[^>]+>", "", title.group(1) if title else "")).strip()
            published = None
            if stamp:
                day, month, year, hour, minute = (int(v) for v in stamp.groups())
                published = datetime(year, month, day, hour, minute, tzinfo=_ROME).isoformat()
            filings.append(OAMFiling(
                oam=self.oam,
                document_id=f"EMARKET-STORAGE:{protocol.group(1)}",
                package_url=self.root + link.group(1),
                landing_url=f"{self.documents}?categoria={category}&azienda={issuer}",
                published_at=published,
                label=label[:220] or None,
                scope=_it_title_scope(label),
            ))
        if not filings:
            raise GlobalProviderError(f"eMarket STORAGE lists no annual ESEF package for {legal_name} (LEI {lei})")
        filings.sort(key=lambda filing: filing.published_at or "", reverse=True)
        return filings


# Trailing Portuguese/Spanish legal-form words, possibly stacked
# ("NOS, SGPS, S.A.", "MARTIFER - S.G.P.S. S.A.", "IMPRESA-SOCIEDADE GESTORA DE
# PARTICIPACOES SOCIAIS S.A.", "EDP RENEWABLES SOCIEDAD ANONIMA").
_PT_LEGAL_FORM = re.compile(
    r"(?:[\s,\-]+(?:S\.?\s?A\.?|S\.?\s?G\.?\s?P\.?\s?S\.?|SOCIEDADE\s+GESTORA\s+DE\s+PARTICIPACOES\s+SOCIAIS|"
    r"SOCIEDADE\s+ABERTA|SOCIEDAD\s+ANONIMA|SOCIEDADE\s+ANONIMA|S\.?\s?A\.?\s?D\.?|PLC|N\.?\s?V\.?|SE|AG|INC\.?|LTD\.?))+\s*$"
)


def _pt_name_core(value: str) -> str:
    """'NOS, SGPS, S.A.' / 'NOS SGPS SA' -> 'NOS'; accents folded."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"\s+", " ", text).strip(" \"'()")
    text = _PT_LEGAL_FORM.sub("", text)
    return re.sub(r"[^A-Z0-9]+", "", text)


def _stream_json_base64(chunks, marker: bytes, out, max_bytes: int) -> int:
    """Decode the JSON string value following ``marker`` (base64) to ``out``.

    Base64 never contains a quote or backslash, so JSON escapes ('\\/') are
    removed byte-wise and the closing quote ends the value.
    """
    state, buf, pending, written = "seek", b"", b"", 0
    for chunk in chunks:
        if state == "seek":
            buf += chunk
            at = buf.find(marker)
            if at < 0:
                buf = buf[-len(marker):]
                continue
            chunk, buf, state = buf[at + len(marker):], b"", "data"
        end = chunk.find(b'"')
        if end >= 0:
            chunk, state = chunk[:end], "done"
        data = pending + chunk.replace(b"\\", b"")
        cut = len(data) if state == "done" else len(data) - len(data) % 4
        decoded, pending = base64.b64decode(data[:cut]), data[cut:]
        written += len(decoded)
        if written > max_bytes:
            raise GlobalProviderError("OAM ESEF package exceeds size limit")
        out.write(decoded)
        if state == "done":
            return written
    raise GlobalProviderError("CMVM download response carried no file")


class PortugalCMVMLocator(OAMLocator):
    """CMVM SDI "Relatorios e Contas Anuais" (Portuguese OAM).

    The CMVM portal is an OutSystems app: issuer list, per-issuer annual
    report list and the lodged file are served by its screen-service JSON
    endpoints. Their API version hashes are read from the portal's own
    published scripts on every refresh, so a portal redeploy does not break
    the integration silently. The issuer is matched to exactly one CMVM entity
    by legal name; the embedded LEI inside the downloaded ESEF package remains
    the identity proof (checked by NationalOAMESEFProvider).
    """

    oam = "pt-cmvm-sdi"
    country = "PT"
    base = "https://www.cmvm.pt/PInstitucional/"
    view = "MainFlow.Single_SDI_StaticContent"
    csrf = "T6C+9iB49TLra4jEsMeSckDMNhQ="  # OutSystems anonymous CSRF token
    url_scheme = "cmvm-sdi:"
    _actions = {
        "entities": ("PInstitucional.SDI_StaticPages.SDI_Emitentes_RelCont_Anuais", "DataActionGetData",
                     "PInstitucional/SDI_StaticPages/SDI_Emitentes_RelCont_Anuais/DataActionGetData"),
        "reports": ("CMVM_SDI_Emitentes_CW.Relatorios.InfPeriodicasContAnuais", "DataActionGetData",
                    "CMVM_SDI_Emitentes_CW/Relatorios/InfPeriodicasContAnuais/DataActionGetData"),
        "download": ("PInstitucional.SDI_StaticPages.SDI_Emitentes_RelCont_Anuais", "InfoDiariaPeriodoDownloadZip",
                     "PInstitucional/SDI_StaticPages/SDI_Emitentes_RelCont_Anuais/ActionInfoDiariaPeriodoDownloadZip"),
    }

    def _versions(self) -> dict:
        def fetch() -> str:
            with self.http.client() as client:
                module = client.get(self.base + "moduleservices/moduleversioninfo")
                module.raise_for_status()
                result = {"module": module.json()["versionToken"]}
                for key, (script, name, path) in self._actions.items():
                    js = client.get(self.base + f"scripts/{script}.mvc.js")
                    js.raise_for_status()
                    found = re.search(r'"' + re.escape(name) + r'", "screenservices/' + re.escape(path) + r'", "([^"]+)"', js.text)
                    if not found:
                        raise GlobalProviderError(f"CMVM portal script no longer exposes {name}")
                    result[key] = found.group(1)
            return json.dumps(result)

        return json.loads(self.http.cached_text("cmvm-sdi-versions", fetch))

    def _call(self, client: httpx.Client, key: str, versions: dict, payload: dict) -> dict:
        body = {"versionInfo": {"moduleVersion": versions["module"], "apiVersion": versions[key]},
                "viewName": self.view, **payload}
        response = client.post(self.base + "screenservices/" + self._actions[key][2], json=body,
                               headers={"X-CSRFToken": self.csrf, "Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        if data.get("exception"):
            raise GlobalProviderError(f"CMVM {key} failed: {data['exception'].get('message')}")
        return data.get("data") or {}

    def _entities(self) -> list[tuple[str, str]]:
        def fetch() -> str:
            versions = self._versions()
            with self.http.client() as client:
                data = self._call(client, "entities", versions, {"screenData": {"variables": {}}})
            rows = (data.get("EntitiesList") or {}).get("List") or []
            return json.dumps([[str(r["NUM_ENT"]), str(r["NOM_ENT"])] for r in rows if r.get("NUM_ENT")])

        return [tuple(row) for row in json.loads(self.http.cached_text("cmvm-sdi-entities", fetch))]

    def _entity_id(self, legal_name: str) -> str:
        from difflib import SequenceMatcher
        core = _pt_name_core(legal_name)
        entities = self._entities()
        matches = {eid for eid, name in entities if core and _pt_name_core(name) == core}
        if not matches and len(core) >= 6:
            # CMVM register typos ("Participações Soiais"): accept one near-
            # identical name only. Identity is still proven by the package's
            # embedded LEI, which must equal the issuer's LEI.
            def full(value: str) -> str:
                text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
                return re.sub(r"[^A-Z0-9]+", "", text)

            target = full(legal_name)
            matches = {eid for eid, name in entities
                       if SequenceMatcher(None, target, full(name)).ratio() >= 0.95}
        if len(matches) != 1:
            raise GlobalProviderError(f"CMVM issuer identity is not uniquely resolved for {legal_name!r}")
        return next(iter(matches))

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        entity = self._entity_id(legal_name)

        def fetch() -> str:
            versions = self._versions()
            variables = {
                "StartIndex": 0, "MaxRecord": 50, "IsLoading": True, "Count": 0,
                "LanguageId": "1", "_languageIdInDataFetchStatus": 1,
                "EntitiesList": entity, "_entitiesListInDataFetchStatus": 1,
                "StartDate": "2019-01-01", "_startDateInDataFetchStatus": 1,
                "EndDate": _utc_now().date().isoformat(), "_endDateInDataFetchStatus": 1,
                "InfPeriodicasContAnuaisLst": {"List": []},
                "GetLanguage": {"Language": {"PortugueseId": 1, "EnglishId": 2}},
            }
            with self.http.client() as client:
                data = self._call(client, "reports", versions, {"screenData": {"variables": variables}})
            return json.dumps(((data.get("InfPeriodicasContAnuaisLst2") or {}).get("List")) or [])

        rows = json.loads(self.http.cached_text(f"cmvm-sdi-annual:{entity}", fetch))
        filings = []
        for row in rows:
            title = str(row.get("DSC_FACT") or "")
            lower = title.lower()
            # Zip lodgements are the ESEF packages (some issuers omit "ESEF"
            # from the title); explicit non-ESEF/PDF versions are skipped and
            # the package parser still rejects anything without inline XBRL.
            if not row.get("IsZip") or re.search(r"n[aã]o\s+esef|non[\s-]+esef|\bpdf\b", lower):
                continue
            scope = "consolidated" if "consolid" in lower else ("separate" if "individua" in lower else None)
            filings.append(OAMFiling(
                oam=self.oam, document_id=f"CMVM-SDI:{entity}:{row['ID']}",
                package_url=f"{self.url_scheme}{row['ID']}:{'en' if row.get('IsEN') else 'pt'}",
                landing_url=self.base + "PortalInstitucional",
                published_at=str(row.get("DATA_FACT") or "") or None, label=title, scope=scope,
            ))
        # Newest publication first; within one date prefer consolidated.
        filings.sort(key=lambda f: (f.published_at or "", {"consolidated": 2, None: 1}.get(f.scope, 0)), reverse=True)
        if not filings:
            raise GlobalProviderError(f"CMVM lists no ESEF annual financial report for entity {entity}")
        return filings

    def download(self, url: str, target: Path, max_bytes: int) -> None:
        """Stream the base64 file out of the JSON action response to disk."""
        _, ident, lang = url.split(":")
        versions = self._versions()
        body = {"versionInfo": {"moduleVersion": versions["module"], "apiVersion": versions["download"]},
                "viewName": self.view,
                "inputParameters": {"LocalLanguageId": 2 if lang == "en" else 1,
                                    "Language": {"PortugueseId": 1, "EnglishId": 2},
                                    "IsPT": lang != "en", "Id": int(ident), "Tab": "Z"}}
        marker = b'"Base64":"'
        with self.http.client() as client, client.stream(
            "POST", self.base + "screenservices/" + self._actions["download"][2], json=body,
            headers={"X-CSRFToken": self.csrf, "Accept": "application/json"},
        ) as response, target.open("wb") as out:
            response.raise_for_status()
            _stream_json_base64(response.iter_bytes(), marker, out, max_bytes)


class BelgiumSTORILocator(OAMLocator):
    """FSMA STORI (Belgian OAM): lodged annual financial reports by ISIN.

    STORI's public web API filters by ISIN and document type and returns the
    lodged ESEF package (zip) and/or the inline XBRL report (xhtml) per
    filing. The ISIN filter is the register-side identity match; the package's
    embedded LEI remains the proof checked by NationalOAMESEFProvider.
    """

    oam = "be-fsma-stori"
    country = "BE"
    api = "https://webapi.fsma.be/api/v1/en/stori"
    annual_report_type = "9813c451-9fd4-41ba-ba7d-4e0dda0d3051"  # "Annual financial report"

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        isin = (company.isin or "").upper()
        if not isin:
            raise GlobalProviderError("FSMA STORI lookup requires the instrument ISIN")

        def fetch() -> str:
            with self.http.client() as client:
                response = client.post(f"{self.api}/result", json={
                    "startRowIndex": 0, "pageSize": 50, "isinCode": isin,
                    "documentTypeId": self.annual_report_type, "isDocumentTypeGroup": False,
                })
            response.raise_for_status()
            return response.text

        payload = json.loads(self.http.cached_text(f"fsma-stori-annual:{isin}", fetch))
        items = sorted(payload.get("storiResultItems") or [], key=lambda r: str(r.get("datePublication") or ""), reverse=True)
        filings = []
        for item in items:
            docs = [d for d in item.get("mainDocuments") or [] if str(d.get("fileType")).lower() in {"zip", "xhtml"}]
            if not docs:
                continue
            # Prefer the full report package, English before other languages.
            docs.sort(key=lambda d: (str(d.get("fileType")).lower() == "zip",
                                     str(d.get("language") or "").lower() == "en"), reverse=True)
            doc = docs[0]
            filings.append(OAMFiling(
                oam=self.oam, document_id=f"FSMA-STORI:{doc['fileDataId']}",
                package_url=f"{self.api}/download?fileDataId={doc['fileDataId']}",
                landing_url="https://www.fsma.be/en/stori",
                published_at=str(item.get("datePublication") or "")[:10] or None,
                label=f"{item.get('companyName')}: {item.get('reportingTopicName')} ({doc.get('originalFileName')})",
            ))
        if not filings:
            raise GlobalProviderError(f"FSMA STORI lists no ESEF annual financial report for {isin}")
        return filings


class NetherlandsAFMLocator(OAMLocator):
    """AFM "Register financiele verslaggeving" (Dutch OAM).

    The AFM publishes the whole register as an XML export (id, filing date,
    issuer name, fiscal year, document type, file name). Annual financial
    reports lodged as ESEF (.zip/.xbri/.xhtml) are matched to exactly one
    issuer by legal name; the download link is taken from the filing's AFM
    detail page. The package's embedded LEI remains the identity proof.
    """

    oam = "nl-afm-register"
    country = "NL"
    export = "https://www.afm.nl/export.aspx?type=e8825b05-4004-4301-b736-651e8c61053d&format=xml"
    detail = "https://www.afm.nl/en/sector/registers/meldingenregisters/financiele-verslaggeving/details"
    url_scheme = "afm-register:"

    def _register(self) -> list[dict]:
        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(self.export)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            rows = []
            for item in root.findall("vermelding"):
                row = {child.tag: (child.text or "").strip() for child in item}
                if not row.get("objecttype_eng", "").lower().startswith("annual financial report"):
                    continue
                if not re.search(r"\.(zip|xbri|xhtml|html)$", row.get("filename", ""), re.I):
                    continue
                rows.append({k: row.get(k, "") for k in ("id", "datum", "uitgevende-instelling", "boekjaar", "filename")})
            return json.dumps(rows)

        return json.loads(self.http.cached_text("afm-register-annual-esef", fetch))

    @staticmethod
    def _published(value: str) -> Optional[str]:
        try:
            return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p").date().isoformat()
        except ValueError:
            return None

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        from difflib import SequenceMatcher
        rows = self._register()
        core = _pt_name_core(legal_name)
        names = {row["uitgevende-instelling"] for row in rows}
        matched = {name for name in names if core and _pt_name_core(name) == core}
        if not matched and len(core) >= 6:
            matched = {name for name in names if SequenceMatcher(None, core, _pt_name_core(name)).ratio() >= 0.95}
        if len(matched) != 1:
            raise GlobalProviderError(f"AFM register issuer identity is not uniquely resolved for {legal_name!r}")
        issuer = next(iter(matched))
        filings = [
            OAMFiling(
                oam=self.oam, document_id=f"AFM:{row['id']}", package_url=f"{self.url_scheme}{row['id']}",
                landing_url=f"{self.detail}?id={row['id']}", published_at=self._published(row["datum"]),
                label=f"{issuer} annual financial report {row['boekjaar']} ({row['filename']})",
            )
            for row in rows if row["uitgevende-instelling"] == issuer
        ]
        filings.sort(key=lambda f: f.published_at or "", reverse=True)
        if not filings:
            raise GlobalProviderError(f"AFM register lists no ESEF annual financial report for {issuer!r}")
        return filings

    def download(self, url: str, target: Path, max_bytes: int) -> None:
        ident = url[len(self.url_scheme):]
        with self.http.client() as client:
            page = client.get(self.detail, params={"id": ident})
            page.raise_for_status()
            link = re.search(r'href="(/downloadregisterfile\.aspx\?[^"]+)"', page.text)
            if not link:
                raise GlobalProviderError(f"AFM filing {ident} exposes no downloadable document")
            size = 0
            with client.stream("GET", "https://www.afm.nl" + html_unescape(link.group(1))) as response, target.open("wb") as out:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise GlobalProviderError("OAM ESEF package exceeds size limit")
                    out.write(chunk)


class UKNSMLocator(OAMLocator):
    """FCA National Storage Mechanism (UK OAM): tagged ESEF annual reports.

    The NSM search API (index ``nsm-search``) is queried by the issuer's LEI
    for "Annual Financial Report" disclosures tagged ESEF; every hit is
    re-checked client-side to carry exactly that LEI. AIM issuers are not on
    a regulated market and lodge no ESEF report.
    """

    oam = "gb-fca-nsm"
    country = "GB"
    search = "https://api.data.fca.org.uk/search?index=nsm-search"
    artefacts = "https://data.fca.org.uk/artefacts/"
    min_interval_seconds = 3.0
    cooldown_seconds = 900.0
    _lock = threading.Lock()
    _last_call = 0.0
    _blocked_until = 0.0

    def _throttle(self) -> None:
        with UKNSMLocator._lock:
            now = time.monotonic()
            if now < UKNSMLocator._blocked_until:
                raise GlobalProviderError("FCA NSM search is cooling down after a rate block")
            wait = UKNSMLocator._last_call + self.min_interval_seconds - now
            if wait > 0:
                time.sleep(wait)
            UKNSMLocator._last_call = time.monotonic()

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        lei = lei.upper()

        def fetch() -> str:
            self._throttle()
            body = {"from": 0, "size": 40, "sort": "publication_date", "sortorder": "desc",
                    "criteriaObj": {"criteria": [
                        {"name": "company_lei", "value": ["", lei, "disclose_org", "related_org"]},
                        {"name": "tag_esef", "value": ["Tagged", "Untagged"]},
                    ], "dateCriteria": None}}
            with self.http.client() as client:
                response = client.post(self.search, json=body)
            if response.status_code in (403, 429):
                # API Gateway rate block: stop calling for a while instead of
                # extending the block (the VPS shares one IP for all users).
                UKNSMLocator._blocked_until = time.monotonic() + self.cooldown_seconds
            response.raise_for_status()
            return response.text

        hits = json.loads(self.http.cached_text(f"fca-nsm-esef-v2:{lei}", fetch)).get("hits", {}).get("hits", [])
        filings = []
        untagged = 0
        for hit in hits:
            row = hit.get("_source") or {}
            if str(row.get("lei") or "").upper() != lei:
                continue
            if str(row.get("type") or "").strip().lower() != "annual financial report":
                continue
            if str(row.get("tag_esef") or "").strip().lower() != "tagged":
                untagged += 1
                continue
            link = str(row.get("download_link") or "")
            if not re.search(r"\.(zip|xhtml|html)$", link, re.I):
                continue
            filings.append(OAMFiling(
                oam=self.oam, document_id=f"FCA-NSM:{row.get('disclosure_id')}",
                package_url=self.artefacts + link,
                landing_url="https://data.fca.org.uk/#/nsm/nationalstoragemechanism",
                published_at=str(row.get("publication_date") or "")[:10] or None,
                label=f"{row.get('company')}: {row.get('headline') or 'Annual Financial Report'}",
            ))
        filings.sort(key=lambda f: f.published_at or "", reverse=True)
        if not filings and untagged:
            raise GlobalProviderError(
                f"FCA NSM annual financial reports for LEI {lei} are lodged untagged (no inline XBRL)"
            )
        if not filings:
            raise GlobalProviderError(f"FCA NSM lists no ESEF annual financial report for LEI {lei}")
        return filings


class GreeceAthensLocator(OAMLocator):
    """Euronext Athens issuer "Financial Statements ESEF" (Greek OAM).

    Euronext Athens publishes its stock and issuer directories as JSON
    (ISIN -> issuer name -> issuer code) and lists each issuer's lodged ESEF
    financial reports (iXBRL zip) on the issuer's financial-data page. The ISIN
    is the register-side identity match; the package's embedded LEI is the
    proof checked by NationalOAMESEFProvider.
    """

    oam = "gr-athens-esef"
    country = "GR"
    base = "https://athens.euronext.com"

    def _directory(self, name: str) -> list[dict]:
        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(f"{self.base}/sites/default/files/json_data_files/{name}_en.json")
            response.raise_for_status()
            return response.text

        payload = json.loads(self.http.cached_text(f"athens-{name}", fetch))
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    def _issuer_code(self, isin: str) -> str:
        stock = [r for r in self._directory("stocks") if str(r.get("ISIN") or "").upper() == isin]
        if len(stock) != 1:
            raise GlobalProviderError(f"Euronext Athens stock directory has no unique row for {isin}")
        def norm(value: object) -> str:
            return " ".join(str(value or "").split()).upper()

        # The issuer directory uses either the full or the short issuer name.
        names = [norm(stock[0].get(k)) for k in ("_issuerFullName", "Issuer") if norm(stock[0].get(k))]
        codes: set[str] = set()
        for key in names:
            codes = {str(r.get("Code")) for r in self._directory("issuers") if norm(r.get("Name")) == key}
            if codes:
                break
        if len(codes) != 1:
            raise GlobalProviderError(f"Euronext Athens issuer identity is not uniquely resolved for {isin}")
        return next(iter(codes))

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        isin = (company.isin or "").upper()
        if not isin:
            raise GlobalProviderError("Euronext Athens lookup requires the instrument ISIN")
        code = self._issuer_code(isin)
        page = f"{self.base}/en/market-data/issuers/{code}/financial-data"

        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(page, params={"term_node_tid_depth": "2"})
            response.raise_for_status()
            return response.text

        html = self.http.cached_text(f"athens-esef:{code}", fetch)
        filings = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            link = re.search(r'href="([^"]+?\.zip(?:/[0-9a-f-]+)?)"', row, re.I)
            if not link:
                continue
            title = html_unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))).strip()
            meta = re.search(r"\((\d{4}),\s*([^,)]+),\s*([^)]+)\)", title)
            if not meta or not re.search(r"annual|year statement", meta.group(2), re.I):
                continue  # half-year / interim ESEF statements are not annual reports
            stamp = re.search(r"(\d{2})-(\d{2})-(\d{4})", title)
            scope_text = meta.group(3).strip().lower()
            url = link.group(1) if link.group(1).startswith("http") else self.base + link.group(1)
            filings.append(OAMFiling(
                oam=self.oam, document_id=f"ATHENS-ESEF:{code}:{hashlib.sha1(url.encode()).hexdigest()[:16]}",
                package_url=url, landing_url=f"{page}?term_node_tid_depth=2",
                published_at=f"{stamp.group(3)}-{stamp.group(2)}-{stamp.group(1)}" if stamp else None,
                label=title.split("|")[0][:200],
                scope="consolidated" if scope_text in {"consolidated", "both"} else ("separate" if "company" in scope_text or "parent" in scope_text else None),
            ))
        # Newest fiscal year first; consolidated before others.
        filings.sort(key=lambda f: (f.published_at or "", f.scope == "consolidated"), reverse=True)
        if not filings:
            raise GlobalProviderError(f"Euronext Athens lists no ESEF annual financial report for issuer {code}")
        return filings


class DenmarkVirkLocator(OAMLocator):
    """Danish annual reports filed with the Danish Business Authority (virk.dk).

    Listed Danish issuers file their ESEF annual report (inline XBRL xhtml)
    with Erhvervsstyrelsen, which publishes it through the open
    distribution.virk.dk search index keyed by CVR number. The CVR is read
    from GLEIF (registeredAs) for the issuer's LEI; the report's embedded LEI
    is then verified like any OAM package.
    """

    oam = "dk-virk-regnskab"
    country = "DK"
    search = "http://distribution.virk.dk/offentliggoerelser/_search"

    def _cvr(self, lei: str) -> Optional[str]:
        def fetch() -> str:
            with self.http.client() as client:
                response = client.get(f"https://api.gleif.org/api/v1/lei-records/{lei}", headers={"Accept": "application/vnd.api+json"})
            response.raise_for_status()
            return response.text

        try:
            entity = json.loads(self.http.cached_text(f"gleif-record:{lei.upper()}", fetch))["data"]["attributes"]["entity"]
        except (GlobalProviderError, ValueError, KeyError, TypeError):
            return None
        value = re.sub(r"\D", "", str(entity.get("registeredAs") or ""))
        return value if len(value) == 8 and str(entity.get("jurisdiction") or "").upper().startswith("DK") else None

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        cvr = self._cvr(lei)
        if not cvr:
            raise GlobalProviderError(f"no Danish CVR number verifiable for LEI {lei} (GLEIF registeredAs)")

        def fetch() -> str:
            body = {"query": {"term": {"cvrNummer": int(cvr)}}, "size": 40,
                    "sort": [{"offentliggoerelsesTidspunkt": {"order": "desc"}}]}
            with self.http.client() as client:
                response = client.post(self.search, json=body)
            response.raise_for_status()
            return response.text

        hits = json.loads(self.http.cached_text(f"virk-regnskab:{cvr}", fetch)).get("hits", {}).get("hits", [])
        filings = []
        for hit in hits:
            row = hit.get("_source") or {}
            if str(row.get("cvrNummer")) != cvr:
                continue
            period = ((row.get("regnskab") or {}).get("regnskabsperiode") or {}).get("slutDato")
            for doc in row.get("dokumenter") or []:
                if doc.get("dokumentType") != "AARSRAPPORT" or "xhtml" not in str(doc.get("dokumentMimeType")):
                    continue
                filings.append(OAMFiling(
                    oam=self.oam, document_id=f"VIRK:{cvr}:{period}:{hit.get('_id')}",
                    package_url=str(doc.get("dokumentUrl")),
                    landing_url=f"https://datacvr.virk.dk/enhed/virksomhed/{cvr}",
                    published_at=str(row.get("offentliggoerelsesTidspunkt") or "")[:10] or None,
                    label=f"Annual report {period} filed with Erhvervsstyrelsen (CVR {cvr})",
                ))
        filings.sort(key=lambda f: f.published_at or "", reverse=True)
        if not filings:
            raise GlobalProviderError(f"virk.dk lists no ESEF annual report for CVR {cvr}")
        return filings


class NasdaqNordicNewsLocator(OAMLocator):
    """Nasdaq Nordic regulated company announcements with ESEF attachments.

    Issuers on Nasdaq Copenhagen/Iceland publish their annual financial report
    as a regulated exchange notice whose attachments include the ESEF package
    (zip). Announcements are found by issuer-name search and kept only when the
    announcing company's name matches the issuer's legal name and the category
    is "Annual Financial Report"; the package's embedded LEI is verified.
    """

    oam = "nasdaq-nordic-news"
    country = "IS"
    api = "https://api.news.eu.nasdaq.com/news/query.action"

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        from difflib import SequenceMatcher
        core = _pt_name_core(legal_name)
        term = re.sub(r"[^\w\s&-]", " ", re.sub(r"(?i)\b(hf|h\.f|a/s|as|asa|ab|oyj|plc|ltd)\b\.?", " ", legal_name)).strip()
        term = " ".join(term.split()[:3]) or company.ticker

        def fetch() -> str:
            params = {"type": "json", "showAttachments": "true", "showCompany": "true", "countResults": "false",
                      "freeText": term, "cnscategory": "Annual Financial Report",
                      "globalGroup": "exchangeNotice", "globalName": "NordicAllMarkets",
                      "displayLanguage": "en", "language": "en", "timeZone": "CET",
                      "dateMask": "yyyy-MM-dd HH:mm:ss", "limit": "60", "start": "0", "dir": "DESC"}
            with self.http.client() as client:
                response = client.get(self.api, params=params)
            response.raise_for_status()
            return response.text

        items = (json.loads(self.http.cached_text(f"nasdaq-news-afr:{term.upper()}", fetch)).get("results") or {}).get("item") or []
        filings = []
        for item in items:
            if "annual financial report" not in str(item.get("cnsCategory") or "").lower():
                continue
            name_core = _pt_name_core(str(item.get("company") or ""))
            if not core or (name_core != core and SequenceMatcher(None, name_core, core).ratio() < 0.9):
                continue
            for attachment in item.get("attachment") or []:
                if not str(attachment.get("fileName") or "").lower().endswith((".zip", ".xbri", ".xhtml")):
                    continue
                url = str(attachment.get("attachmentUrl") or "")
                if not url.startswith("https://attachment.news.eu.nasdaq.com/"):
                    continue
                filings.append(OAMFiling(
                    oam=self.oam, document_id=f"NASDAQ-NEWS:{item.get('disclosureId') or item.get('id')}:{url.rsplit('/', 1)[-1]}",
                    package_url=url, landing_url=str(item.get("messageUrl") or "https://www.nasdaqomxnordic.com/news/companynews"),
                    published_at=str(item.get("published") or "")[:10] or None,
                    label=f"{item.get('company')}: {item.get('headline')} ({attachment.get('fileName')})"[:200],
                ))
        filings.sort(key=lambda f: f.published_at or "", reverse=True)
        if not filings:
            raise GlobalProviderError(f"Nasdaq Nordic announcements list no ESEF annual report for {legal_name!r}")
        return filings


class DenmarkCombinedLocator(OAMLocator):
    """virk.dk filings plus Nasdaq Copenhagen announcements, newest first.

    Danish banks/insurers no longer appear on virk.dk for recent years, but
    publish the ESEF package with their annual-report announcement."""

    oam = "dk-combined"
    country = "DK"

    def __init__(self, http: "OAMHttp") -> None:
        super().__init__(http)
        self.parts = [DenmarkVirkLocator(http), NasdaqNordicNewsLocator(http)]

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        filings: list[OAMFiling] = []
        errors: list[str] = []
        for part in self.parts:
            try:
                filings += part.annual_filings(company, lei, legal_name)
            except GlobalProviderError as exc:
                errors.append(str(exc))
        if not filings:
            raise GlobalProviderError("; ".join(errors))
        return sorted(filings, key=lambda f: f.published_at or "", reverse=True)


class ItalySDIRLocator(OAMLocator):
    """Both Italian authorized storage mechanisms, merged and ranked.

    A candidate from either storage still has to pass the provider's embedded
    LEI and annual-period gates; this class only widens where we look.
    """

    oam = "it-sdir"
    country = "IT"

    def __init__(self, http: "OAMHttp") -> None:
        super().__init__(http)
        self.storages: list[OAMLocator] = [Italy1InfoLocator(http), ItalyEMarketStorageLocator(http)]

    def annual_filings(self, company: GlobalCompany, lei: str, legal_name: str) -> list[OAMFiling]:
        filings: list[OAMFiling] = []
        errors: list[str] = []
        for storage in self.storages:
            try:
                filings.extend(storage.annual_filings(company, lei, legal_name))
            except GlobalProviderError as exc:
                errors.append(f"{storage.oam}: {exc}")
        if not filings:
            raise GlobalProviderError("no Italian authorized storage lists an annual ESEF package: " + "; ".join(errors))
        filings.sort(key=_it_filing_rank, reverse=True)
        return filings


def _report_member(archive: zipfile.ZipFile) -> Optional[str]:
    names = [n for n in archive.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")) and not n.endswith("/")]
    in_reports = [n for n in names if "/reports/" in n.lower() or n.lower().startswith("reports/")]
    pool = in_reports or names
    return max(pool, key=lambda n: archive.getinfo(n).file_size) if pool else None


class NationalOAMESEFProvider(CachedESEFFundamentalsProvider):
    """ESEF fundamentals read from the issuer's national OAM filing."""

    provider_id = "official-oam-esef-ixbrl-v3"

    def __init__(self, *, timeout: float = 60.0, locators: Optional[Iterable[OAMLocator]] = None) -> None:
        super().__init__(timeout=min(timeout, 20.0))
        self.http = OAMHttp(timeout=timeout)
        chosen = list(locators) if locators is not None else [
            SwedenFinanscentralenLocator(self.http),
            NorwayNewswebLocator(self.http),
            FranceAMFInfoFinanciereLocator(self.http),
            SpainCNMVLocator(self.http),
            ItalySDIRLocator(self.http),
            PortugalCMVMLocator(self.http),
            BelgiumSTORILocator(self.http),
            NetherlandsAFMLocator(self.http),
            UKNSMLocator(self.http),
            GreeceAthensLocator(self.http),
            DenmarkCombinedLocator(self.http),
            NasdaqNordicNewsLocator(self.http),
        ]
        self.locators = {locator.country: locator for locator in chosen}

    def supports(self, country: str) -> bool:
        return country.upper() in self.locators

    # -- package handling -------------------------------------------------
    def _facts_cache_path(self, filing: OAMFiling) -> Path:
        return OAMHttp.cache_dir() / "packages" / (hashlib.sha256(filing.document_id.encode()).hexdigest() + ".json")

    def _download(self, url: str, target: Path) -> None:
        for locator in self.locators.values():
            scheme = getattr(locator, "url_scheme", None)
            if scheme and url.startswith(scheme):
                try:
                    locator.download(url, target, MAX_PACKAGE_BYTES)
                except httpx.HTTPError as exc:
                    raise GlobalProviderError(f"OAM package download failed: {type(exc).__name__}") from exc
                return
        size = 0
        try:
            with self.http.client() as client, client.stream("GET", url) as response, target.open("wb") as out:
                response.raise_for_status()
                first = True
                for chunk in response.iter_bytes():
                    if first and chunk:
                        first = False
                        # ESEF packages are zip files. OAMs also store PDFs for
                        # issuers outside ESEF (e.g. third-country issuers);
                        # stop immediately instead of downloading them.
                        head = chunk.lstrip().removeprefix(b"\xef\xbb\xbf").lstrip()[:1]
                        if not chunk.startswith(b"PK") and head != b"<":
                            raise GlobalProviderError("OAM document is not an ESEF report (non-ESEF filing, e.g. PDF)")
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
        usable = isinstance(cached, dict) and isinstance(cached.get("facts"), list)
        if usable and cached.get("schemaVersion") == PACKAGE_SCHEMA_VERSION:
            return cached
        tmp_dir = OAMHttp.cache_dir() / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".zip") as handle:
            target = Path(handle.name)
            try:
                self._download(filing.package_url, target)
            except GlobalProviderError:
                # An older parse of the same immutable, LEI-checked document
                # keeps fewer concepts but is still the official filing.
                if usable and cached.get("schemaVersion") == 2:
                    return cached
                raise
            if zipfile.is_zipfile(target):
                with zipfile.ZipFile(target) as archive:
                    payload = self._parse_archive(filing, archive)
            else:
                # A single-file ESEF report (XHTML lodged without a zip).
                with target.open("r", encoding="utf-8", errors="replace") as text:
                    payload = self._parse_text(filing, iter(lambda: text.read(1 << 20), ""), "report.xhtml")
        write_json_atomic(path, payload)
        return payload

    def _parse_archive(self, filing: OAMFiling, archive: zipfile.ZipFile, *, depth: int = 0) -> dict:
        member = _report_member(archive)
        if member is None and depth == 0:
            # Some issuers wrap the ESEF report package (.zip/.xbri) in an
            # outer zip. Descend exactly one level, within the size limit.
            files = [info for info in archive.infolist() if not info.is_dir()]
            nested = [
                info for info in files
                if info.filename.lower().endswith((".zip", ".xbri")) and info.file_size <= MAX_PACKAGE_BYTES
            ]
            if not nested and len(files) == 1 and files[0].file_size <= MAX_PACKAGE_BYTES:
                # A single inner member without extension (e.g. "... årsredovisning
                # 2025 XBRL"); accepted only if its content is itself a zip.
                with archive.open(files[0]) as handle:
                    if handle.read(2) == b"PK":
                        nested = files
            if len(nested) == 1:
                with archive.open(nested[0]) as handle:
                    inner_bytes = handle.read(MAX_PACKAGE_BYTES + 1)
                if len(inner_bytes) <= MAX_PACKAGE_BYTES and zipfile.is_zipfile(io.BytesIO(inner_bytes)):
                    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
                        return self._parse_archive(filing, inner, depth=1)
        if member is None:
            raise GlobalProviderError("OAM ESEF package contains no XHTML report")
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            return self._parse_text(filing, iter(lambda: text.read(1 << 20), ""), member)

    def _parse_text(self, filing: OAMFiling, chunks, member: str) -> dict:
        facts, entities = extract_facts(chunks)
        kept = [f for f in facts if concept_is_relevant(f["dimensions"].get("concept"))]
        return {
            "schemaVersion": PACKAGE_SCHEMA_VERSION,
            "documentId": filing.document_id,
            "packageUrl": filing.package_url,
            "reportFile": member,
            "entities": sorted(entities),
            "parsedAt": _utc_now().isoformat(),
            "factCount": len(facts),
            "facts": kept,
        }

    # -- provider ------------------------------------------------------------
    def locator_for(self, company: GlobalCompany) -> Optional[OAMLocator]:
        """The issuer's home-member-state OAM (ISIN country) when BIAP has a
        locator for it, else the listing country's. A Belgian issuer listed in
        Athens (e.g. Viohalco) lodges its ESEF report with FSMA, not in Greece."""
        home = (company.isin or "")[:2].upper()
        if home and home != company.country.upper() and home in self.locators:
            return self.locators[home]
        return self.locators.get(company.country.upper())

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        locator = self.locator_for(company)
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
            if not package.get("entities") and not package.get("facts"):
                errors.append(f"{filing.document_id}: official ESEF report carries no inline XBRL tags (untagged report)")
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
            normalization_meta = normalized.pop("__normalization_meta__", {})
            retrieved = str(package.get("parsedAt") or _utc_now().isoformat())
            enriched = replace(
                company,
                name=legal_name or company.name,
                lei=lei,
                reporting_currency=reporting_currency or company.reporting_currency,
                **normalized,
                filing_period_end=period_end.isoformat(),
                filing_observed_at=filing.published_at,
                report_scope=filing.scope,
                raw_provider_fields={
                    **company.raw_provider_fields,
                    "oam": filing.oam,
                    "oam_document_id": filing.document_id,
                    "oam_package_url": filing.package_url,
                    "oam_report_file": package.get("reportFile"),
                    "oam_published_at": filing.published_at,
                    "oam_retrieved_at": retrieved,
                    "oam_entity_lei_verified": True,
                    "oam_credit_extraction": normalization_meta,
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

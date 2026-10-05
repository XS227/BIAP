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
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlencode
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
        ]
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

    def _parse_archive(self, filing: OAMFiling, archive: zipfile.ZipFile) -> dict:
        member = _report_member(archive)
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

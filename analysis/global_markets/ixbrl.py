"""Minimal, dependency-free inline XBRL (iXBRL / ESEF) fact extractor.

National officially appointed mechanisms (OAMs) store the issuer's ESEF
package itself: a zip with an XHTML report whose numeric facts are tagged with
``ix:nonFraction``. This module turns those tags into the same fact shape the
xBRL-JSON path uses (``{"value", "dimensions": {concept, entity, period, unit,
...explicit dimensions}}``) so one normalization contract serves every ESEF
transport.

Only numeric facts are extracted. Values are never guessed: a fact whose
format cannot be interpreted is dropped rather than approximated. Period
boundaries are emitted as inclusive ISO dates (inline XBRL context dates are
already inclusive), which ``esef._period_parts`` reads unchanged.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Iterable, Optional

LEI_SCHEME = "http://standards.iso.org/iso/17442"


def _local(tag: str) -> str:
    return tag.rsplit(":", 1)[-1].lower()


def parse_ixbrl_number(text: str, fmt: Optional[str]) -> Optional[float]:
    """Interpret an ixt number format. Returns None when unsupported."""
    fmt_name = (fmt or "").rsplit(":", 1)[-1].lower().replace("-", "")
    raw = (text or "").strip()
    if fmt_name in {"fixedzero", "zerodash", "numdash", "fixedempty"} or (raw in {"-", "–", "—"} and "zero" in fmt_name):
        return 0.0
    if fmt_name in {"fixedzero", "zerodash"}:
        return 0.0
    if not raw:
        return None
    if fmt_name in {"numcommadecimal", "numdotcomma", "numspacecomma", "numcomma"}:
        decimal_sep = ","
    elif fmt_name in {"", "numdotdecimal", "numcommadot", "numspacedot", "numdot", "numunitdecimal", "numdotdecimalin", "numwordsen"}:
        decimal_sep = "."
    else:
        return None
    if fmt_name in {"numwordsen", "numunitdecimal"}:
        return None
    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == decimal_sep)
    if decimal_sep == ",":
        cleaned = cleaned.replace(",", ".")
    if not cleaned or cleaned == "." or cleaned.count(".") > 1:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class _IXBRLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.contexts: dict[str, dict] = {}
        self.units: dict[str, list[str]] = {}
        self.facts: list[dict] = []
        self._ctx: Optional[dict] = None
        self._unit: Optional[str] = None
        self._text_target: Optional[str] = None
        self._text: list[str] = []
        self._member_dim: Optional[str] = None
        self._fact_stack: list[dict] = []

    # -- helpers -----------------------------------------------------------
    def _begin_text(self, target: str) -> None:
        self._text_target = target
        self._text = []

    def _end_text(self) -> str:
        value = "".join(self._text).strip()
        self._text_target = None
        self._text = []
        return value

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}
        local = _local(name)
        if name.endswith(":context") and local == "context":
            self._ctx = {"id": attr.get("id", ""), "entity": None, "scheme": None, "start": None, "end": None, "instant": None, "dims": {}}
        elif self._ctx is not None and local == "identifier":
            self._ctx["scheme"] = attr.get("scheme")
            self._begin_text("identifier")
        elif self._ctx is not None and local in {"startdate", "enddate", "instant"}:
            self._begin_text(local)
        elif self._ctx is not None and local == "explicitmember":
            self._member_dim = attr.get("dimension")
            self._begin_text("member")
        elif self._ctx is not None and local == "typedmember":
            # Typed dimensions always make a fact non-headline.
            self._ctx["dims"][attr.get("dimension") or "typed"] = "typed"
        elif name.endswith(":unit") and local == "unit":
            self._unit = attr.get("id", "")
            self.units[self._unit] = []
        elif self._unit is not None and local == "measure":
            self._begin_text("measure")
        elif name == "ix:nonfraction":
            self._fact_stack.append({
                "name": attr.get("name"),
                "context": attr.get("contextref"),
                "unit": attr.get("unitref"),
                "format": attr.get("format"),
                "scale": attr.get("scale"),
                "sign": attr.get("sign"),
                "decimals": attr.get("decimals"),
                "nil": attr.get("xsi:nil", "").lower() == "true",
                "text": [],
            })

    def handle_endtag(self, tag):
        name = tag.lower()
        local = _local(name)
        if self._ctx is not None:
            if local == "identifier" and self._text_target == "identifier":
                self._ctx["entity"] = self._end_text()
            elif local in {"startdate", "enddate", "instant"} and self._text_target == local:
                self._ctx[{"startdate": "start", "enddate": "end", "instant": "instant"}[local]] = self._end_text()[:10]
            elif local == "explicitmember" and self._text_target == "member":
                self._ctx["dims"][self._member_dim or "unknown"] = self._end_text()
                self._member_dim = None
            elif local == "context" and name.endswith(":context"):
                self.contexts[self._ctx["id"]] = self._ctx
                self._ctx = None
            return
        if self._unit is not None:
            if local == "measure" and self._text_target == "measure":
                self.units[self._unit].append(self._end_text())
            elif local == "unit" and name.endswith(":unit"):
                self._unit = None
            return
        if name == "ix:nonfraction" and self._fact_stack:
            fact = self._fact_stack.pop()
            text = "".join(fact.pop("text"))
            if self._fact_stack:
                # Nested nonFraction: the inner text also belongs to the outer.
                self._fact_stack[-1]["text"].append(text)
            self._emit(fact, text)

    def handle_data(self, data):
        if self._text_target is not None:
            self._text.append(data)
        if self._fact_stack:
            self._fact_stack[-1]["text"].append(data)

    def _emit(self, fact: dict, text: str) -> None:
        if fact["nil"] or not fact["name"] or not fact["context"]:
            return
        value = parse_ixbrl_number(text, fact["format"])
        if value is None:
            return
        try:
            scale = int(fact["scale"] or 0)
        except ValueError:
            return
        value = value * (10 ** scale)
        if fact["sign"] == "-":
            value = -value
        self.facts.append({
            "name": fact["name"],
            "context": fact["context"],
            "unit": fact["unit"],
            "decimals": fact["decimals"],
            "value": value,
        })


def extract_facts(chunks: Iterable[str]) -> tuple[list[dict], set[str]]:
    """Parse iXBRL text chunks into xBRL-JSON-shaped numeric facts.

    Returns ``(facts, entity_identifiers)``. ``entity_identifiers`` lists the
    LEIs (scheme ISO 17442) used by the report's contexts, which callers must
    compare with the resolved issuer LEI before trusting the document.
    """
    parser = _IXBRLParser()
    for chunk in chunks:
        parser.feed(chunk)
    parser.close()

    facts: list[dict] = []
    entities: set[str] = set()
    for ctx in parser.contexts.values():
        if ctx.get("entity") and (ctx.get("scheme") or "").rstrip("/") == LEI_SCHEME:
            entities.add(ctx["entity"].strip().upper())
    for raw in parser.facts:
        ctx = parser.contexts.get(raw["context"])
        if not ctx:
            continue
        if ctx.get("instant"):
            period = ctx["instant"]
        elif ctx.get("start") and ctx.get("end"):
            period = f"{ctx['start']}/{ctx['end']}"
        else:
            continue
        measures = parser.units.get(raw["unit"] or "", [])
        dims = {
            "concept": raw["name"],
            "entity": f"scheme:{(ctx.get('entity') or '').strip()}",
            "period": period,
        }
        if measures:
            dims["unit"] = measures[0] if len(measures) == 1 else "/".join(measures)
        for axis, member in (ctx.get("dims") or {}).items():
            dims[axis] = member
        facts.append({"value": str(raw["value"]), "decimals": raw["decimals"], "dimensions": dims})
    return facts, entities


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def annual_period_end(facts: list[dict], concepts: tuple[str, ...]) -> Optional[str]:
    """Latest end date of a plain ~12-month duration for the given concepts."""
    from datetime import date

    wanted = {c.lower() for c in concepts}
    best: Optional[date] = None
    for fact in facts:
        dims = fact.get("dimensions") or {}
        if str(dims.get("concept") or "").lower() not in wanted:
            continue
        if any(key not in {"concept", "entity", "period", "unit"} for key in dims):
            continue
        parts = str(dims.get("period") or "").split("/")
        if len(parts) != 2 or not all(_DATE.match(p) for p in parts):
            continue
        start, end = date.fromisoformat(parts[0]), date.fromisoformat(parts[1])
        if 300 <= (end - start).days <= 400 and (best is None or end > best):
            best = end
    return best.isoformat() if best else None

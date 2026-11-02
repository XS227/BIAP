"""Two-stage validation of a SAF-T Financial 1.40 file: (1) the official Skatteetaten XSD, (2) rules the XSD cannot express.

Never logs or returns accounting values: findings carry element names and counts only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List

from lxml import etree

REF_DIR = Path(__file__).resolve().parent / "reference"
XSD_NAME = "Norwegian_SAF-T_Financial_Schema_v_1.40.xsd"
TOLERANCE = Decimal("0.005")


@dataclass
class Report:
    xsd_errors: List[str] = field(default_factory=list)
    rule_errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.xsd_errors and not self.rule_errors


_schema = None


def _load_schema():
    global _schema
    if _schema is None:
        path = REF_DIR / XSD_NAME
        if not path.exists():
            raise FileNotFoundError("official XSD missing: run `python -m accounting.saft.fetch_reference`")
        _schema = etree.XMLSchema(etree.parse(str(path)))
    return _schema


def _d(text) -> Decimal:
    try:
        return Decimal((text or "0").strip())
    except InvalidOperation:
        return Decimal("NaN")


def validate_bytes(xml: bytes) -> Report:
    rep = Report()
    try:
        doc = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except etree.XMLSyntaxError as exc:
        rep.xsd_errors.append(f"not well-formed XML: {exc.msg}")
        return rep
    schema = _load_schema()
    if not schema.validate(doc):
        # element path + XSD message only; the XSD message may quote a value, so strip anything after the first quote
        rep.xsd_errors = [f"line {e.line}: {e.message.split(chr(39))[0].strip()}" for e in list(schema.error_log)[:50]]
    _rules(doc, rep)
    return rep


def _rules(doc, rep: Report) -> None:
    ns = {"n": doc.nsmap.get(None)} if doc.nsmap.get(None) else None
    def q(path):
        return doc.xpath(path.replace("/", "/n:").lstrip("/") if ns else path, namespaces=ns) if False else None
    def find(xp_local):
        if ns:
            xp = "//" + "/".join("n:" + p for p in xp_local.split("/"))
            return doc.xpath(xp, namespaces=ns)
        return doc.xpath("//" + xp_local)
    version = find("Header/AuditFileVersion")
    if version and (version[0].text or "").strip() != "1.40":
        rep.rule_errors.append("AuditFileVersion must be 1.40")
    debits = [_d(e.text) for e in find("Transaction/Line/DebitAmount/Amount")]
    credits = [_d(e.text) for e in find("Transaction/Line/CreditAmount/Amount")]
    gl = find("GeneralLedgerEntries")
    if gl:
        def child(name):
            c = [x for x in gl[0] if etree.QName(x).localname == name]
            return c[0].text if c else None
        if abs(sum(debits, Decimal(0)) - _d(child("TotalDebit"))) > TOLERANCE:
            rep.rule_errors.append("TotalDebit does not equal the sum of the debit lines")
        if abs(sum(credits, Decimal(0)) - _d(child("TotalCredit"))) > TOLERANCE:
            rep.rule_errors.append("TotalCredit does not equal the sum of the credit lines")
        if abs(sum(debits, Decimal(0)) - sum(credits, Decimal(0))) > TOLERANCE:
            rep.rule_errors.append("ledger is not balanced (total debit != total credit)")
        n_tx = len(find("Transaction"))
        if child("NumberOfEntries") is not None and int(child("NumberOfEntries")) != n_tx:
            rep.rule_errors.append("NumberOfEntries does not equal the number of transactions")
        known = {e.text for e in find("GeneralLedgerAccounts/Account/AccountID")}
        used = {e.text for e in find("Transaction/Line/AccountID")}
        if known and used - known:
            rep.rule_errors.append(f"{len(used - known)} account(s) used in transactions are missing from MasterFiles")
        for tx in find("Transaction"):
            dsum = Decimal(0)
            for line in tx:
                if etree.QName(line).localname != "Line":
                    continue
                for part in line:
                    nm = etree.QName(part).localname
                    amt = [x for x in part if etree.QName(x).localname == "Amount"]
                    if nm == "DebitAmount" and amt:
                        dsum += _d(amt[0].text)
                    elif nm == "CreditAmount" and amt:
                        dsum -= _d(amt[0].text)
            if abs(dsum) > TOLERANCE:
                rep.rule_errors.append("a transaction is not balanced")
                break
    tax_codes = {e.text for e in find("TaxCodeDetails/StandardTaxCode")}
    for code in tax_codes:
        if code is not None and code.upper() != "NA" and not code.strip().isalnum():
            rep.rule_errors.append("invalid StandardTaxCode")
            break


def validate_file(path: str | Path) -> Report:
    return validate_bytes(Path(path).read_bytes())

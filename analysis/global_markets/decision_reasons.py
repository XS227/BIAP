"""Separate *why Agent 8 did not accept* from *what is limited about the data*.

A review caused by high-confidence agent disagreement (AAPL) is a governance
outcome; an annual filing that is 280 days old is a data limitation. The
payload used to blend both into one reasoning string, so a clean, current-gate
issuer looked like it had a stale-data problem. This module only re-labels
facts the pipeline already produced: it changes no decision, score, gate or
threshold.
"""
from __future__ import annotations

from typing import Optional

_EVIDENCE_GATE_BLOCK = "task/evidence gate is out of scope or blocked"


def _item(code: str, text: str, *, blocks: bool, detail: Optional[dict] = None) -> dict:
    out = {"code": code, "text": text, "blocksDecision": blocks}
    if detail:
        out["detail"] = detail
    return out


def split_decision_reasons(
    *,
    governance: dict,
    evidence: dict,
    distress: dict,
    fundamental_evidence: Optional[dict],
    confidence: float,
    accept_threshold: float = 0.55,
) -> dict:
    gov: list[dict] = []
    data: list[dict] = []
    accepted = bool(governance.get("accepted"))
    status = evidence.get("status")

    for text in governance.get("hard_blocks") or governance.get("hardBlocks") or ():
        if str(text) == _EVIDENCE_GATE_BLOCK:
            continue  # reported below as a data limitation with its cause
        gov.append(_item("HARD_BLOCK", str(text), blocks=True))

    contradictions = list(evidence.get("contradictions") or ())
    if contradictions:
        gov.append(_item(
            "AGENT_DISAGREEMENT",
            "High-confidence agents disagree: " + "; ".join(map(str, contradictions)),
            blocks=not accepted,
        ))
    if distress.get("status") == "ELEVATED_RISK" and not accepted:
        gov.append(_item("ELEVATED_DISTRESS", "Agent 9 reports elevated independent distress risk", blocks=True))
    if (
        not accepted
        and not contradictions
        and status != "BLOCK"
        and not any(g["code"] == "HARD_BLOCK" for g in gov)
        and confidence < accept_threshold
    ):
        gov.append(_item(
            "BELOW_ACCEPT_THRESHOLD",
            f"Calibrated confidence {confidence:.2f} is below the {accept_threshold:.2f} accept threshold",
            blocks=True,
        ))

    missing = list(evidence.get("missing_critical") or evidence.get("missingCritical") or ())
    if status == "BLOCK":
        data.append(_item(
            "EVIDENCE_BLOCK",
            "Evidence gate BLOCK: " + (", ".join(missing) if missing else "required evidence missing"),
            blocks=True, detail={"missing": missing},
        ))
    elif status == "WARN":
        data.append(_item("EVIDENCE_WARN", "Evidence gate WARN: research-grade only, not promoted to an actionable call",
                          blocks=True))

    fe = fundamental_evidence or {}
    tier = fe.get("freshnessTier")
    fresh = fe.get("freshnessDetail") or {}
    if tier == "LAST_ANNUAL_FILING":
        data.append(_item(
            "LAST_ANNUAL_FILING",
            str(fresh.get("statement") or "Latest official annual filing is not current-quarter data"),
            blocks=False,
        ))
    elif tier == "NOT_CURRENT":
        data.append(_item("NO_CURRENT_OFFICIAL_FUNDAMENTALS", str(fresh.get("statement") or
                          "No current official fundamentals"), blocks=status != "PASS"))
    elif tier == "PERIOD_UNKNOWN":
        data.append(_item("PERIOD_UNKNOWN", str(fresh.get("statement") or "Filing period end unknown"), blocks=False))
    for line in fe.get("limitations") or ():
        text = str(line)
        if text.startswith("last annual filing only") or text.startswith("no current official fundamentals"):
            continue  # already represented by the tier item above
        data.append(_item("DATA_LIMITATION", text, blocks=False))

    return {
        "governance": gov,
        "dataLimitations": data,
        "governanceDriven": any(g["blocksDecision"] for g in gov),
        "dataDriven": any(d["blocksDecision"] for d in data),
        "note": "governance = decision/agent-level reasons; dataLimitations = evidence age, coverage and source gaps. "
                "Informational limitations (blocksDecision=false) did not stop acceptance.",
    }

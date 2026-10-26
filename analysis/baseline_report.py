"""Daily honest report for the listed-company baseline: per-source counts, backlog, early-stop reason.

Delivered by SMTP using the same SMTP_* variables as account_ops_local (/etc/biap/mail.env);
recipient from BIAP_BASELINE_NOTIFY_TO. Always also printed to the journal, so a missing mail
config is visible rather than silent.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any


def build_report(codal: dict[str, Any], tindex: dict[str, Any] | None, price_sources: dict[str, int], backlog: int) -> dict[str, Any]:
    meta = codal.get("metadata") or {}
    sources = {
        "CODAL": {
            "succeeded": int(codal.get("succeeded") or 0),
            "failed": int(codal.get("failed") or 0),
            "rateLimited": int(meta.get("rateLimitedCount") or 0),
        },
        "TSETMC": {"pricesBySource": price_sources},
    }
    if tindex is not None:
        sources["TIndex"] = {k: tindex.get(k, 0) for k in ("succeeded", "failed", "rateLimited")}
    reasons = [r for r in (meta.get("stoppedEarly"), (tindex or {}).get("stoppedEarly")) if r]
    warnings = [w for w in (meta.get("newFilingCheckError"),) if w]
    return {"sources": sources, "backlogRemaining": backlog, "stoppedEarly": reasons, "warnings": warnings}


def render(report: dict[str, Any]) -> str:
    lines = ["BIAP listed-company daily baseline"]
    for name, stats in report["sources"].items():
        if name == "TSETMC":
            lines.append(f"TSETMC prices by source: {stats['pricesBySource'] or 'none fetched'}")
        else:
            lines.append(f"{name}: succeeded {stats['succeeded']}, failed {stats['failed']}, rate-limited {stats['rateLimited']}")
    lines.append(f"Never-enriched backlog remaining: {report['backlogRemaining']}")
    lines.append("Stopped early: " + ("; ".join(report["stoppedEarly"]) if report["stoppedEarly"] else "no"))
    if report.get("warnings"):
        lines.append("Warnings: " + "; ".join(report["warnings"]))
    return "\n".join(lines)


def send(report: dict[str, Any]) -> dict[str, bool]:
    text = render(report)
    print(text, flush=True)
    to, host, sender = os.environ.get("BIAP_BASELINE_NOTIFY_TO"), os.environ.get("SMTP_HOST"), os.environ.get("SMTP_FROM")
    if not (to and host and sender):
        return {"configured": False, "sent": False}
    port = int(os.environ.get("SMTP_PORT", "587"))
    secure = os.environ.get("SMTP_SECURE", "").lower() == "true" or port == 465
    msg = EmailMessage()
    msg["From"], msg["To"] = f"BIAP <{sender}>", to
    msg["Subject"] = "BIAP baseline: " + ("stopped early" if report["stoppedEarly"] else "completed with warnings" if report.get("warnings") else "completed")
    msg.set_content(text)
    try:
        ctx = ssl.create_default_context()
        user, password = os.environ.get("SMTP_USER", "").strip(), os.environ.get("SMTP_PASS", "")
        smtp = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) if secure else smtplib.SMTP(host, port, timeout=15)
        with smtp:
            if not secure:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if user or password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return {"configured": True, "sent": True}
    except (OSError, smtplib.SMTPException, ssl.SSLError):
        return {"configured": True, "sent": False}

"""BIAP ops/admin panel: server-rendered HTML mounted directly on biap-fin.

Why here and not a separate service: biap-fin (api_server.py) already has
the order/audit/risk/performance data an operator needs; a thin HTML layer
on top avoids standing up and deploying a second app for a small internal
tool. See PROJECT_STATUS.md for the decision writeup.

No template engine dependency (jinja2 isn't installed) -- HTML is built
with small helper functions below, escaping every value that could contain
user- or filing-derived text via html.escape.
"""

from __future__ import annotations

import html
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from admin_auth import COOKIE_NAME, AdminAuthRequired, admin_panel_configured, create_session_token, require_admin
from admin_store import AdminStore, bootstrap_from_env
from audit_store import AuditStore
from execution import ExecutionPolicyError, approve_order_intent, reject_order_intent
from performance_routes import AGENTS
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from risk import policy_snapshot


router = APIRouter(prefix="/admin", include_in_schema=False)

_ADMIN_STORE = AdminStore()
_AUDIT = AuditStore()
_PERFORMANCE = PerformanceStore()

bootstrap_from_env(_ADMIN_STORE)


def _page(title: str, body: str, *, username: Optional[str] = None) -> str:
    nav = ""
    if username:
        nav = f"""
        <nav>
          <a href="/admin">Dashboard</a>
          <a href="/admin/orders">Ordre</a>
          <a href="/admin/audit">Audit-logg</a>
          <span class="who">{html.escape(username)}</span>
          <a href="/admin/logout">Logg ut</a>
        </nav>
        """
    return f"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — BIAP admin</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; background: Canvas; color: CanvasText; }}
  header {{ padding: 1rem 1.5rem; border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent); display: flex; align-items: center; gap: 1.5rem; }}
  header h1 {{ font-size: 1.1rem; margin: 0; }}
  nav {{ display: flex; gap: 1rem; align-items: center; font-size: 0.9rem; }}
  nav a {{ color: inherit; text-decoration: none; opacity: 0.75; }}
  nav a:hover {{ opacity: 1; text-decoration: underline; }}
  .who {{ opacity: 0.5; }}
  main {{ padding: 1.5rem; max-width: 1100px; margin: 0 auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid color-mix(in srgb, CanvasText 10%, transparent); vertical-align: top; }}
  th {{ opacity: 0.6; font-weight: 600; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .card {{ border: 1px solid color-mix(in srgb, CanvasText 15%, transparent); border-radius: 8px; padding: 0.9rem 1.1rem; min-width: 160px; }}
  .card .n {{ font-size: 1.6rem; font-weight: 600; }}
  .card .l {{ font-size: 0.8rem; opacity: 0.6; }}
  .badge {{ padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.75rem; }}
  .badge.pending {{ background: color-mix(in srgb, orange 25%, transparent); }}
  .badge.approved, .badge.filled {{ background: color-mix(in srgb, seagreen 25%, transparent); }}
  .badge.rejected {{ background: color-mix(in srgb, crimson 25%, transparent); }}
  form.inline {{ display: inline; }}
  button {{ font-size: 0.8rem; padding: 0.25rem 0.6rem; cursor: pointer; }}
  form.login {{ max-width: 320px; margin: 3rem auto; display: flex; flex-direction: column; gap: 0.75rem; }}
  form.login input {{ padding: 0.5rem; font-size: 1rem; }}
  .err {{ color: crimson; }}
  .muted {{ opacity: 0.6; font-size: 0.85rem; }}
</style>
</head>
<body>
<header><h1>BIAP admin</h1>{nav}</header>
<main>{body}</main>
</body>
</html>"""


def _status_badge(status: str) -> str:
    cls = status.lower().replace("paper_filled", "filled").replace("pending_approval", "pending")
    return f'<span class="badge {html.escape(cls)}">{html.escape(status)}</span>'


@router.get("/login", response_class=HTMLResponse)
def login_form(error: Optional[str] = None):
    if not admin_panel_configured():
        return HTMLResponse(_page("Ikke konfigurert", "<p class='err'>BIAP_ADMIN_JWT_SECRET er ikke satt på denne serveren.</p>"), status_code=503)
    err_html = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    body = f"""
    <form class="login" method="post" action="/admin/login">
      {err_html}
      <label>Brukernavn<br><input name="username" autocomplete="username" required></label>
      <label>Passord<br><input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">Logg inn</button>
    </form>
    """
    return HTMLResponse(_page("Logg inn", body))


@router.post("/login")
def login_submit(username: str = Form(...), password: str = Form(...)):
    if not admin_panel_configured():
        return RedirectResponse("/admin/login", status_code=303)
    if not _ADMIN_STORE.verify_operator(username, password):
        return RedirectResponse("/admin/login?error=Feil+brukernavn+eller+passord", status_code=303)
    token = create_session_token(username)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="strict", secure=True, max_age=12 * 60 * 60, path="/admin"
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/admin")
    return resp


@router.get("", response_class=HTMLResponse)
def dashboard(username: str = Depends(require_admin)):
    policy = policy_snapshot()
    daily_notional = _AUDIT.submitted_notional_today()
    pending = _AUDIT.list_all_intents(status="PENDING_APPROVAL", limit=500)

    agent_rows = ""
    for agent in AGENTS:
        stats = _PERFORMANCE.agent_stats(agent)
        if stats is None:
            agent_rows += f"<tr><td>{html.escape(agent)}</td><td colspan='3' class='muted'>ingen observasjoner ennå</td></tr>"
        else:
            ready = "✓" if stats.evaluated_calls >= MIN_OBSERVED_SAMPLES else f"({stats.evaluated_calls}/{MIN_OBSERVED_SAMPLES})"
            agent_rows += (
                f"<tr><td>{html.escape(agent)}</td>"
                f"<td>{stats.evaluated_calls}</td>"
                f"<td>{stats.directional_accuracy:.0%}</td>"
                f"<td>{ready}</td></tr>"
            )

    body = f"""
    <div class="cards">
      <div class="card"><div class="n">{len(pending)}</div><div class="l">Ventende godkjenninger</div></div>
      <div class="card"><div class="n">{daily_notional:,.0f}</div><div class="l">Notional i dag (godkjent+fylt)</div></div>
      <div class="card"><div class="n">{'PÅ' if policy.get('kill_switch') else 'AV'}</div><div class="l">Kill switch</div></div>
      <div class="card"><div class="n">{policy.get('max_order_notional', '—')}</div><div class="l">Maks ordre-notional</div></div>
    </div>

    <h2>Agent-ytelse (observert)</h2>
    <table>
      <tr><th>Agent</th><th>Evaluerte kall</th><th>Retningsnøyaktighet</th><th>Trust ready</th></tr>
      {agent_rows}
    </table>

    <p class="muted">Full risk-policy og helsestatus: <a href="/risk/status">/risk/status</a> · <a href="/health">/health</a></p>
    """
    return HTMLResponse(_page("Dashboard", body, username=username))


@router.get("/orders", response_class=HTMLResponse)
def orders_list(username: str = Depends(require_admin), status: Optional[str] = Query(default=None)):
    intents = _AUDIT.list_all_intents(status=status, limit=300)
    rows = ""
    for intent in intents:
        actions = ""
        if intent.get("status") == "PENDING_APPROVAL":
            actions = (
                f'<form class="inline" method="post" action="/admin/orders/{html.escape(intent["id"])}/approve">'
                f'<button type="submit">Godkjenn</button></form> '
                f'<form class="inline" method="post" action="/admin/orders/{html.escape(intent["id"])}/reject">'
                f'<button type="submit">Avvis</button></form>'
            )
        rows += (
            "<tr>"
            f"<td><code>{html.escape(intent['id'][:8])}</code></td>"
            f"<td>{html.escape(intent.get('ownerUserId', ''))}</td>"
            f"<td>{html.escape(intent.get('code', ''))}</td>"
            f"<td>{html.escape(intent.get('side', ''))} {intent.get('quantity', '')}</td>"
            f"<td>{html.escape(intent.get('mode', ''))}</td>"
            f"<td>{_status_badge(intent.get('status', ''))}</td>"
            f"<td>{html.escape(intent.get('created_at', ''))}</td>"
            f"<td>{actions}</td>"
            "</tr>"
        )
    filter_links = " · ".join(
        f'<a href="/admin/orders{"?status=" + s if s else ""}">{s or "alle"}</a>'
        for s in [None, "PENDING_APPROVAL", "APPROVED", "REJECTED", "PAPER_FILLED"]
    )
    body = f"""
    <p class="muted">Filter: {filter_links}</p>
    <table>
      <tr><th>Id</th><th>Bruker</th><th>Kode</th><th>Side/antall</th><th>Modus</th><th>Status</th><th>Opprettet</th><th></th></tr>
      {rows or "<tr><td colspan='8' class='muted'>Ingen ordre</td></tr>"}
    </table>
    """
    return HTMLResponse(_page("Ordre", body, username=username))


def _act_on_order(intent_id: str, *, username: str, event_type: str, transition, extra: dict) -> RedirectResponse:
    found = _AUDIT.get_intent_any_owner(intent_id)
    if found is not None:
        owner_user_id, intent = found
        try:
            resolved = transition(intent)
            _AUDIT.save_intent(resolved, user_id=owner_user_id)
            _AUDIT.record_event(
                event_id=str(uuid.uuid4()),
                user_id=owner_user_id,
                intent_id=intent_id,
                event_type=event_type,
                payload={"actor": f"admin:{username}", "intent": resolved, **extra},
            )
        except ExecutionPolicyError:
            pass
    return RedirectResponse("/admin/orders", status_code=303)


@router.post("/orders/{intent_id}/approve")
def approve(intent_id: str, username: str = Depends(require_admin)):
    return _act_on_order(intent_id, username=username, event_type="ORDER_APPROVED", transition=approve_order_intent, extra={})


@router.post("/orders/{intent_id}/reject")
def reject(intent_id: str, username: str = Depends(require_admin)):
    return _act_on_order(
        intent_id,
        username=username,
        event_type="ORDER_REJECTED",
        transition=lambda intent: reject_order_intent(intent, reason="rejected via admin panel"),
        extra={"reason": "rejected via admin panel"},
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_list(username: str = Depends(require_admin)):
    events = _AUDIT.list_all_events(limit=300)
    rows = ""
    for ev in events:
        rows += (
            "<tr>"
            f"<td>{ev['seq']}</td>"
            f"<td>{html.escape(ev['eventType'])}</td>"
            f"<td>{html.escape(ev.get('ownerUserId', ''))}</td>"
            f"<td>{html.escape((ev.get('intentId') or '')[:8])}</td>"
            f"<td>{html.escape(ev['createdAt'])}</td>"
            f"<td>{html.escape(str(ev['payload'].get('actor', '')))}</td>"
            "</tr>"
        )
    body = f"""
    <table>
      <tr><th>#</th><th>Type</th><th>Bruker</th><th>Intent</th><th>Tid</th><th>Aktør</th></tr>
      {rows or "<tr><td colspan='6' class='muted'>Ingen events</td></tr>"}
    </table>
    """
    return HTMLResponse(_page("Audit-logg", body, username=username))

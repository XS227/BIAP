"""BIAP ops/admin panel: server-rendered HTML mounted directly on biap-fin.

Mounted under /admindir (not /admin) because biap.dadashi.no already serves
something else at /admin -- see PROJECT_STATUS.md's "Admin/ops panel"
section for the path-collision note.

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
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from admin_auth import COOKIE_NAME, admin_panel_configured, create_session_token, require_admin
from admin_store import AdminStore, bootstrap_from_env
from audit_store import AuditStore
from backend_admin_client import BackendAdminUnavailable, configured as backend_admin_configured, get_json as backend_admin_get
from execution import ExecutionPolicyError, approve_order_intent, reject_order_intent
from performance_routes import AGENTS
from performance_store import MIN_OBSERVED_SAMPLES, PerformanceStore
from risk import policy_snapshot


router = APIRouter(prefix="/admindir", include_in_schema=False)

_ADMIN_STORE = AdminStore()
_AUDIT = AuditStore()
_PERFORMANCE = PerformanceStore()
_RELEASE_MANIFEST = Path(__file__).with_name("mobile_release.json")
_MOBILE_APK_PATH = Path(
    os.getenv("BIAP_MOBILE_APK_PATH")
    or (Path(__file__).resolve().parent.parent / ".runtime" / "releases" / "biap-latest.apk")
)

bootstrap_from_env(_ADMIN_STORE)


def _mobile_release() -> dict:
    try:
        payload = json.loads(_RELEASE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "unknown", "versionCode": None, "releasedAt": None, "changes": []}
    changes = payload.get("changes")
    if not isinstance(changes, list):
        changes = []
    return {
        "version": str(payload.get("version") or "unknown"),
        "versionCode": payload.get("versionCode"),
        "releasedAt": payload.get("releasedAt"),
        "changes": [str(item) for item in changes],
    }


def _page(title: str, body: str, *, username: Optional[str] = None) -> str:
    nav = ""
    if username:
        nav = f"""
        <nav>
          <a href="/admindir">Dashboard</a>
          <a href="/admindir/users">Users</a>
          <a href="/admindir/installs">Installs</a>
          <a href="/admindir/activity">Activity</a>
          <a href="/admindir/orders">Ordre</a>
          <a href="/admindir/audit">Audit-logg</a>
          <span class="who">{html.escape(username)}</span>
          <a href="/admindir/logout">Logg ut</a>
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
  header {{ padding: 1rem 1.5rem; border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent); display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap; }}
  header h1 {{ font-size: 1.1rem; margin: 0; }}
  nav {{ display: flex; gap: 1rem; align-items: center; font-size: 0.9rem; flex-wrap: wrap; }}
  nav a {{ color: inherit; text-decoration: none; opacity: 0.75; }}
  nav a:hover {{ opacity: 1; text-decoration: underline; }}
  .who {{ opacity: 0.5; }}
  main {{ padding: 1.5rem; max-width: 1180px; margin: 0 auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid color-mix(in srgb, CanvasText 10%, transparent); vertical-align: top; }}
  th {{ opacity: 0.6; font-weight: 600; }}
  code {{ overflow-wrap: anywhere; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .card {{ border: 1px solid color-mix(in srgb, CanvasText 15%, transparent); border-radius: 8px; padding: 0.9rem 1.1rem; min-width: 150px; }}
  .card .n {{ font-size: 1.6rem; font-weight: 600; }}
  .card .l {{ font-size: 0.8rem; opacity: 0.6; }}
  .release {{ border: 1px solid color-mix(in srgb, seagreen 35%, CanvasText 12%); border-radius: 10px; padding: 1rem 1.1rem; margin: 0 0 1.5rem; }}
  .release h2 {{ margin-top: 0; }}
  .release ul {{ margin: 0.6rem 0 1rem; padding-inline-start: 1.3rem; }}
  .btn {{ display: inline-block; padding: 0.55rem 0.85rem; border-radius: 7px; background: seagreen; color: white; text-decoration: none; font-weight: 600; }}
  .btn:hover {{ filter: brightness(1.08); }}
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
  .ok {{ color: seagreen; }}
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


def _backend_unavailable_body(exc: Exception | None = None) -> str:
    detail = "BIAP_ADMIN_API_TOKEN er ikke satt for biap-fin." if not backend_admin_configured() else "Konto-backenden kan ikke nås akkurat nå."
    if exc:
        detail += f" <span class='muted'>{html.escape(str(exc))}</span>"
    return f"<h2>Account analytics unavailable</h2><p class='err'>{detail}</p><p class='muted'>Ingen passord, tokens eller private datasett vises i dette panelet.</p>"


def _safe(value) -> str:
    return html.escape("—" if value in (None, "") else str(value))


@router.get("/login", response_class=HTMLResponse)
def login_form(error: Optional[str] = None):
    if not admin_panel_configured():
        return HTMLResponse(_page("Ikke konfigurert", "<p class='err'>BIAP_ADMIN_JWT_SECRET er ikke satt på denne serveren.</p>"), status_code=503)
    err_html = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    body = f"""
    <form class="login" method="post" action="/admindir/login">
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
        return RedirectResponse("/admindir/login", status_code=303)
    if not _ADMIN_STORE.verify_operator(username, password):
        return RedirectResponse("/admindir/login?error=Feil+brukernavn+eller+passord", status_code=303)
    token = create_session_token(username)
    resp = RedirectResponse("/admindir", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="strict", secure=True, max_age=12 * 60 * 60, path="/admindir"
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/admindir/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/admindir")
    return resp


@router.get("/app/latest.apk")
def download_latest_apk(username: str = Depends(require_admin)):
    return RedirectResponse(
        "https://github.com/XS227/BIAP/releases/latest/download/BIAP.apk",
        status_code=302,
    )


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

    account_cards = ""
    try:
        summary = backend_admin_get("admin/ops/summary")
        account_cards = f"""
        <h2>App / konto</h2>
        <div class="cards">
          <div class="card"><div class="n">{int(summary.get('registeredUsers') or 0)}</div><div class="l">Registrerte brukere</div></div>
          <div class="card"><div class="n">{int(summary.get('approximateInstalls') or 0)}</div><div class="l">Ca. installs</div></div>
          <div class="card"><div class="n">{int(summary.get('activeUsers24h') or 0)}</div><div class="l">Aktive 24t</div></div>
          <div class="card"><div class="n">{int(summary.get('activeUsers7d') or 0)}</div><div class="l">Aktive 7d</div></div>
          <div class="card"><div class="n">{int(summary.get('activeUsers30d') or 0)}</div><div class="l">Aktive 30d</div></div>
          <div class="card"><div class="n">{int(summary.get('activeSessions') or 0)}</div><div class="l">Aktive sessions</div></div>
        </div>
        """
    except BackendAdminUnavailable:
        account_cards = "<p class='muted'>Account analytics ikke koblet til dashboard ennå. Se Users/Installs etter konfigurasjon.</p>"

    body = f"""
    <div class="cards">
      <div class="card"><div class="n">{len(pending)}</div><div class="l">Ventende godkjenninger</div></div>
      <div class="card"><div class="n">{daily_notional:,.0f}</div><div class="l">Notional i dag (godkjent+fylt)</div></div>
      <div class="card"><div class="n">{'PÅ' if policy.get('kill_switch') else 'AV'}</div><div class="l">Kill switch</div></div>
      <div class="card"><div class="n">{policy.get('max_order_notional', '—')}</div><div class="l">Maks ordre-notional</div></div>
    </div>

    {account_cards}

    <h2>Agent-ytelse (observert)</h2>
    <table>
      <tr><th>Agent</th><th>Evaluerte kall</th><th>Retningsnøyaktighet</th><th>Trust ready</th></tr>
      {agent_rows}
    </table>

    <p class="muted">Full risk-policy og helsestatus: <a href="/risk/status">/risk/status</a> · <a href="/health">/health</a></p>
    """
    return HTMLResponse(_page("Dashboard", body, username=username))


@router.get("/users", response_class=HTMLResponse)
def users_list(username: str = Depends(require_admin)):
    try:
        summary = backend_admin_get("admin/ops/summary")
        users = backend_admin_get("admin/ops/users", params={"limit": 300}).get("items") or []
    except BackendAdminUnavailable as exc:
        return HTMLResponse(_page("Users", _backend_unavailable_body(exc), username=username), status_code=503)

    release = _mobile_release()
    latest_version = release["version"]
    android_with_version = [
        user for user in users
        if str(user.get("platform") or "").lower() == "android" and user.get("app_version") not in (None, "")
    ]
    outdated_users = sum(1 for user in android_with_version if str(user.get("app_version")) != latest_version)
    notes_html = "".join(f"<li>{html.escape(note)}</li>" for note in release["changes"])
    if not notes_html:
        notes_html = "<li class='muted'>Ingen release notes registrert.</li>"
    download_html = '<a class="btn" href="/admindir/app/latest.apk">Last ned nyeste APK</a>'
    apk_status = "Stabil APK publiseres automatisk fra siste vellykkede main-build."

    rows = ""
    for user in users:
        user_id = str(user.get("id") or "")
        activity_url = f"/admindir/activity?userId={html.escape(user_id)}" if user_id else "/admindir/activity"
        rows += (
            "<tr>"
            f"<td><a href='{activity_url}'>{_safe(user.get('email'))}</a></td>"
            f"<td>{_safe(user.get('full_name'))}</td>"
            f"<td>{_safe(user.get('plan'))}</td>"
            f"<td>{_safe(user.get('created_at'))}</td>"
            f"<td>{_safe(user.get('last_login_at'))}</td>"
            f"<td>{_safe(user.get('last_seen_at'))}</td>"
            f"<td>{int(user.get('active_sessions') or 0)}</td>"
            f"<td>{_safe(user.get('platform'))} / {_safe(user.get('app_version'))}</td>"
            "</tr>"
        )

    body = f"""
    <section class="release">
      <h2>BIAP app update</h2>
      <div class="cards">
        <div class="card"><div class="n">{html.escape(latest_version)}</div><div class="l">Nyeste versjon</div></div>
        <div class="card"><div class="n">{_safe(release.get('versionCode'))}</div><div class="l">Android versionCode</div></div>
        <div class="card"><div class="n">{outdated_users}</div><div class="l">Android-brukere på eldre kjent versjon</div></div>
      </div>
      <p><strong>Endringer i denne versjonen</strong></p>
      <ul dir="rtl">{notes_html}</ul>
      <p class="muted">Publisert: {_safe(release.get('releasedAt'))} · {html.escape(apk_status)}</p>
      {download_html}
    </section>

    <div class="cards">
      <div class="card"><div class="n">{int(summary.get('registeredUsers') or 0)}</div><div class="l">Registered</div></div>
      <div class="card"><div class="n">{int(summary.get('activeUsers24h') or 0)}</div><div class="l">Active 24h</div></div>
      <div class="card"><div class="n">{int(summary.get('activeUsers7d') or 0)}</div><div class="l">Active 7d</div></div>
      <div class="card"><div class="n">{int(summary.get('activeUsers30d') or 0)}</div><div class="l">Active 30d</div></div>
      <div class="card"><div class="n">{int(summary.get('activeSessions') or 0)}</div><div class="l">Active sessions</div></div>
    </div>
    <p class="muted">Klikk på e-post for brukerens personvern-sikre activity timeline.</p>
    <table>
      <tr><th>Email</th><th>Name</th><th>Plan</th><th>Registered</th><th>Last login</th><th>Last seen</th><th>Sessions</th><th>Client</th></tr>
      {rows or "<tr><td colspan='8' class='muted'>Ingen brukere</td></tr>"}
    </table>
    """
    return HTMLResponse(_page("Users", body, username=username))


@router.get("/installs", response_class=HTMLResponse)
def installs_list(username: str = Depends(require_admin)):
    try:
        summary = backend_admin_get("admin/ops/summary")
        installs = backend_admin_get("admin/ops/installs", params={"limit": 500}).get("items") or []
    except BackendAdminUnavailable as exc:
        return HTMLResponse(_page("Installs", _backend_unavailable_body(exc), username=username), status_code=503)

    version_rows = "".join(
        f"<tr><td>{_safe(item.get('version'))}</td><td>{int(item.get('installs') or 0)}</td></tr>"
        for item in summary.get("appVersions") or []
    )
    rows = "".join(
        "<tr>"
        f"<td><code>{_safe(item.get('installation_id'))}</code></td>"
        f"<td>{_safe(item.get('user_id'))}</td>"
        f"<td>{_safe(item.get('platform'))}</td>"
        f"<td>{_safe(item.get('app_version'))}</td>"
        f"<td>{_safe(item.get('first_seen_at'))}</td>"
        f"<td>{_safe(item.get('last_seen_at'))}</td>"
        "</tr>"
        for item in installs
    )
    body = f"""
    <div class="cards"><div class="card"><div class="n">{int(summary.get('approximateInstalls') or 0)}</div><div class="l">Approx. unique installs</div></div></div>
    <p class="muted">Install-ID er app-generert og ikke device fingerprinting. Reinstall kan telle som ny install.</p>
    <h2>App versions</h2>
    <table><tr><th>Version</th><th>Installs</th></tr>{version_rows or "<tr><td colspan='2'>—</td></tr>"}</table>
    <h2>Installations</h2>
    <table><tr><th>Install ID</th><th>User</th><th>Platform</th><th>Version</th><th>First seen</th><th>Last seen</th></tr>{rows or "<tr><td colspan='6'>—</td></tr>"}</table>
    """
    return HTMLResponse(_page("Installs", body, username=username))


@router.get("/activity", response_class=HTMLResponse)
def activity_list(username: str = Depends(require_admin), userId: Optional[str] = Query(default=None)):
    try:
        events = backend_admin_get("admin/ops/activity", params={"limit": 500, "userId": userId}).get("items") or []
    except BackendAdminUnavailable as exc:
        return HTMLResponse(_page("Activity", _backend_unavailable_body(exc), username=username), status_code=503)

    rows = ""
    for event in events:
        metadata = event.get("metadata_json") or {}
        rows += (
            "<tr>"
            f"<td>{_safe(event.get('created_at'))}</td>"
            f"<td>{_safe(event.get('event_type'))}</td>"
            f"<td>{_safe(event.get('email') or event.get('user_id'))}</td>"
            f"<td>{_safe(event.get('platform'))} / {_safe(event.get('app_version'))}</td>"
            f"<td><code>{html.escape(json.dumps(metadata, ensure_ascii=False, sort_keys=True))}</code></td>"
            "</tr>"
        )
    filter_note = f"<p>Filtered user: <code>{html.escape(userId)}</code> · <a href='/admindir/activity'>vis alle</a></p>" if userId else ""
    body = f"""
    {filter_note}
    <p class="muted">Kun allow-listede produkt-events lagres. Passord, JWT/refresh tokens, API keys og rå private datasett er eksplisitt filtrert bort.</p>
    <table><tr><th>Time</th><th>Event</th><th>User</th><th>Client</th><th>Safe metadata</th></tr>{rows or "<tr><td colspan='5'>Ingen activity events ennå</td></tr>"}</table>
    """
    return HTMLResponse(_page("Activity", body, username=username))


@router.get("/orders", response_class=HTMLResponse)
def orders_list(username: str = Depends(require_admin), status: Optional[str] = Query(default=None)):
    intents = _AUDIT.list_all_intents(status=status, limit=300)
    rows = ""
    for intent in intents:
        actions = ""
        if intent.get("status") == "PENDING_APPROVAL":
            actions = (
                f'<form class="inline" method="post" action="/admindir/orders/{html.escape(intent["id"])}/approve">'
                f'<button type="submit">Godkjenn</button></form> '
                f'<form class="inline" method="post" action="/admindir/orders/{html.escape(intent["id"])}/reject">'
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
        f'<a href="/admindir/orders{"?status=" + s if s else ""}">{s or "alle"}</a>'
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
    return RedirectResponse("/admindir/orders", status_code=303)


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

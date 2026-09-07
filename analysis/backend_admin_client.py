"""Read-only client for BIAP account/admin analytics exposed by the Node backend."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class BackendAdminUnavailable(RuntimeError):
    pass


def _base() -> str:
    return os.getenv("BIAP_BACKEND_ADMIN_BASE", "https://biap.dadashi.no/api").rstrip("/")


def configured() -> bool:
    return bool(os.getenv("BIAP_ADMIN_API_TOKEN"))


def get_json(path: str, *, params: dict[str, str | int | None] | None = None, timeout: float = 6.0) -> dict[str, Any]:
    token = os.getenv("BIAP_ADMIN_API_TOKEN", "")
    if not token:
        raise BackendAdminUnavailable("BIAP_ADMIN_API_TOKEN is not configured")
    url = f"{_base()}/{path.lstrip('/')}"
    if params:
        cleaned = {key: value for key, value in params.items() if value not in (None, "")}
        if cleaned:
            url += "?" + urllib.parse.urlencode(cleaned)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "X-BIAP-Admin-Token": token, "User-Agent": "BIAP-Admin/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise BackendAdminUnavailable(str(exc)) from exc
    if not isinstance(payload, dict):
        raise BackendAdminUnavailable("backend returned a non-object response")
    return payload

"""Allow-listed read-only relay for BIAP market/CODAL upstreams.

This service exists for the migration case where the new BIAP VPS cannot reach
TSETMC/CODAL directly but the current production VPS can. It is deliberately not
a general-purpose proxy: callers select one of a fixed set of upstream aliases,
and only GET/HEAD requests are supported.

Recommended deployment is to bind this service on a private/restricted listener
and firewall it so only the new BIAP server can reach it. No credentials belong
in this repository.
"""

from __future__ import annotations

import os
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import Response

app = FastAPI(title="BIAP Data Relay", version="1.0")

UPSTREAMS = {
    "codal-search": "https://search.codal.ir",
    "codal-excel": "https://excel.codal.ir",
    "codal-www": "https://www.codal.ir",
    "tsetmc-cdn": "https://cdn.tsetmc.com",
    "tsetmc-old": "http://old.tsetmc.com",
}

_TIMEOUT = float(os.getenv("BIAP_RELAY_TIMEOUT", "25"))
_MAX_BYTES = int(os.getenv("BIAP_RELAY_MAX_BYTES", str(32 * 1024 * 1024)))

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _target_url(source: str, path: str, query: str) -> str:
    base = UPSTREAMS.get(source)
    if base is None:
        raise HTTPException(status_code=404, detail="unknown relay source")
    clean_path = path.lstrip("/")
    # The upstream host is fixed by the alias above. Reject URL-looking paths so
    # this endpoint cannot be turned into an open proxy via an absolute URL.
    if "://" in clean_path or clean_path.startswith("//"):
        raise HTTPException(status_code=400, detail="invalid relay path")

    # Starlette/FastAPI decodes percent-encoded route parameters before they
    # reach this function. Re-encode the path as a valid ASCII URL before
    # handing it to urllib; otherwise Persian search terms can trigger a
    # UnicodeEncodeError inside http.client and the relay returns a 500.
    encoded_path = urllib.parse.quote(clean_path, safe="/-._~")
    target = f"{base}/{encoded_path}"
    if query:
        target = f"{target}?{query}"
    return target


def _forward_headers(request: FastAPIRequest) -> dict[str, str]:
    accept = request.headers.get("accept") or "*/*"
    return {
        "User-Agent": "Mozilla/5.0 BIAP-Relay/1.0",
        "Accept": accept,
        "Accept-Encoding": "identity",
    }


def _response_headers(headers) -> dict[str, str]:
    allowed = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP or lower in {"content-length", "content-encoding"}:
            continue
        if lower in {"content-type", "cache-control", "etag", "last-modified", "expires"}:
            allowed[key] = value
    return allowed


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": "read-only-relay",
        "sources": sorted(UPSTREAMS),
    }


@app.api_route("/{source}/{path:path}", methods=["GET", "HEAD"])
def relay(source: str, path: str, request: FastAPIRequest) -> Response:
    target = _target_url(source, path, request.url.query)
    upstream_request = Request(
        target,
        headers=_forward_headers(request),
        method=request.method,
    )

    try:
        with urlopen(upstream_request, timeout=_TIMEOUT) as upstream:
            body = b"" if request.method == "HEAD" else upstream.read(_MAX_BYTES + 1)
            if len(body) > _MAX_BYTES:
                raise HTTPException(status_code=502, detail="upstream response exceeds relay limit")
            return Response(
                content=body,
                status_code=upstream.status,
                headers=_response_headers(upstream.headers),
                media_type=None,
            )
    except HTTPError as exc:
        try:
            body = b"" if request.method == "HEAD" else exc.read(_MAX_BYTES + 1)
        except OSError:
            body = b""
        if len(body) > _MAX_BYTES:
            body = b""
        return Response(
            content=body,
            status_code=exc.code,
            headers=_response_headers(exc.headers),
            media_type=None,
        )
    except HTTPException:
        raise
    except (URLError, TimeoutError, OSError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=502, detail=f"upstream unavailable: {exc}") from exc

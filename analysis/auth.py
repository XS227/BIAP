"""Caller-identity boundary for order/audit endpoints.

BIAP's FIN service does not issue or verify user accounts -- the existing
backend under https://biap.dadashi.no/api/auth/* already does that, and the
mobile app already sends its session token as `Authorization: Bearer <token>`
on every request (see -biap-mobile's src/lib/api.ts). This module reuses that
same header to partition order/audit data by caller instead of duplicating
auth, so no mobile-side change is required to adopt it.

This binds *ownership*, not *authentication*: the token is hashed into an
opaque user id, but its signature/expiry is never checked here since FIN has
no access to the existing backend's session-verification internals. Two
requests presenting the same bearer token are treated as the same user; a
missing token is rejected outright. The raw token is never stored -- only
its hash -- so audit records can't leak live session credentials. Wiring FIN
up to actually validate the token against the existing auth backend is
tracked as a follow-up in PROJECT_STATUS.md, not claimed as done here.
"""

import hashlib

from fastapi import Header, HTTPException


def require_user_id(authorization: str | None = Header(default=None)) -> str:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization bearer token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]

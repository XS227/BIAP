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
import os
import secrets

from fastapi import Header, HTTPException


def require_user_id(authorization: str | None = Header(default=None)) -> str:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization bearer token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def require_approver(authorization: str | None = Header(default=None)) -> None:
    """Gate order-approval transitions behind a distinct shared secret.

    There is no user/role model anywhere in BIAP yet -- require_user_id above
    only hashes a caller's own session token into an opaque ownership id, so
    it cannot distinguish "the trader who created this order" from "someone
    allowed to approve it". Introducing a real role system is a product
    decision, not something to invent unilaterally for a financial
    execution path. This is the deliberately narrow stopgap instead: a
    single operator-held secret (BIAP_APPROVER_TOKEN), separate from every
    caller's own bearer token, required to approve or reject a
    PENDING_APPROVAL order intent.

    Unconfigured means refuse everyone, not allow everyone -- APPROVAL mode
    must not silently become approvable-by-anyone just because an operator
    never set the secret.
    """
    expected = os.environ.get("BIAP_APPROVER_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="order approval is not configured")

    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="a valid approver token is required")

"""Caller-identity boundary for order/audit endpoints.

BIAP's FIN service does not issue user accounts -- the existing backend
under https://biap.dadashi.no/api/auth/* already does that
(`biap-backend/src/routes/auth.routes.js`), and the mobile app already
sends its session token as `Authorization: Bearer <token>` on every request
(see -biap-mobile's src/lib/api.ts). This module reuses that same header,
so no mobile-side change is required.

Two modes, selected by whether `BIAP_AUTH_JWT_SECRET` is configured:

- **Configured (real authentication).** The existing backend signs access
  tokens as `jwt.sign({ userId }, JWT_SECRET, { expiresIn: '15m' })`
  (HS256, confirmed from its source). Given the same shared secret, FIN can
  verify that signature and expiry itself, with no network round-trip to
  the existing backend and no direct access to its Postgres `users` table.
  A valid token yields the real `userId` claim as the ownership key,
  prefixed `jwt:` to stay visually distinct from the fallback below. Once
  this mode is on, a bad or expired token is rejected outright (401) --
  it must never silently fall back to the weaker scheme below, or anyone
  could bypass real authentication by sending garbage instead of a token.
- **Unconfigured (ownership only, no authentication).** The original
  behavior: the token is hashed into an opaque id with no signature or
  expiry check, since FIN has no way to verify it without the shared
  secret. Two requests with the same token are treated as the same caller;
  a missing token is rejected. This mode intentionally stays available
  (rather than being deleted now that JWT verification exists) for any
  environment that hasn't configured the secret -- tests, and local/dev
  setups that don't proxy the real auth backend at all.

Neither mode stores the raw token, only a hash or the verified claim, so
audit records can't leak live session credentials.
"""

import hashlib
import os
import secrets

from fastapi import Header, HTTPException
import jwt as pyjwt


def require_user_id(authorization: str | None = Header(default=None)) -> str:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization bearer token is required")

    secret = os.environ.get("BIAP_AUTH_JWT_SECRET", "")
    if secret:
        try:
            payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        except pyjwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="invalid or expired token") from exc
        user_id = payload.get("userId")
        if not user_id:
            raise HTTPException(status_code=401, detail="token is missing a userId claim")
        return f"jwt:{user_id}"

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

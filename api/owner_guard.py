"""
owner_guard.py: the API's owner-only gate.
==========================================
Writes to the legacy personal files (settings, the old season tracker) and
refreshes that spend upstream calls or LLM credits are owner-only. Only the
Next app's admin relay (web/app/api/owner/[action]/route.ts) holds the
secret, and it checks the admin account before forwarding.

Fails closed: with no secret configured, nobody gets in. CORS doesn't
protect anything here (curl ignores it), and hiding a button isn't auth.
"""

import hmac
import os

from fastapi import HTTPException, Request

HEADER = "x-chat-proxy-secret"


def require_owner(request: Request) -> None:
    secret = os.environ.get("CHAT_PROXY_SECRET", "")
    got = request.headers.get(HEADER, "")
    if not secret or not hmac.compare_digest(got.encode(), secret.encode()):
        raise HTTPException(status_code=403, detail="Owner-only.")

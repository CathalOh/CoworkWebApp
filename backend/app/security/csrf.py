"""Double-submit CSRF: token derived from the session id via HMAC; sent in a header on mutating calls."""
from __future__ import annotations

import hashlib
import hmac

from app.config import get_settings


def csrf_token_for(session_id: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), b"csrf:" + session_id.encode(), hashlib.sha256).hexdigest()


def csrf_valid(session_id: str, presented: str | None) -> bool:
    return bool(presented) and hmac.compare_digest(csrf_token_for(session_id), presented or "")

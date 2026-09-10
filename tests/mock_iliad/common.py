"""Shared helpers for the mock services: base URL, PKCE, opaque tokens, tiny HTML pages."""
from __future__ import annotations

import base64
import hashlib
import html
import os
import secrets
import time

from fastapi.responses import HTMLResponse

# Public origin advertised in discovery documents. Inside docker-compose the backend reaches this container
# as http://mock-iliad:9100 while the browser reaches it as http://localhost:9100; discovery is only ever
# fetched by the backend, so the seed row pins explicit endpoints and this default is mostly cosmetic.
BASE_URL = os.environ.get("MOCK_BASE_URL", "http://localhost:9100").rstrip("/")


def now() -> int:
    return int(time.time())


def opaque_token(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(32)


def s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def pkce_ok(verifier: str | None, challenge: str | None) -> bool:
    return bool(verifier) and bool(challenge) and secrets.compare_digest(s256(verifier), challenge)


def b64url_uint(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def page(title: str, body: str) -> HTMLResponse:
    """Minimal HTML shell for the consent / login pages (no external assets)."""
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem}"
        "label{display:block;margin:.6rem 0 .2rem}input{width:100%;padding:.4rem}"
        "button{margin-top:1rem;padding:.5rem 1rem}code{background:#eee;padding:0 .2rem}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def hidden_fields(values: dict[str, str | None]) -> str:
    return "".join(f"<input type='hidden' name='{html.escape(k)}' value='{html.escape(v)}'>"
                   for k, v in values.items() if v is not None)

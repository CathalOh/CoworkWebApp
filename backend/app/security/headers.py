"""Security headers + app CSP. The artifact preview CSP is separate (see api/artifacts.py)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

APP_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'"
)

# Artifacts render in a sandboxed srcdoc iframe with its own CSP: scripts only from self-inline + CDN allowlist,
# no network except the allowlisted CDNs. allow-scripts is never combined with allow-same-origin.
ARTIFACT_CSP = (
    "default-src 'none'; "
    "script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com data:; "
    "img-src data: blob: https:; "
    "connect-src 'none'; frame-ancestors 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/v1/artifacts/") and request.url.path.endswith("/render"):
            resp.headers["Content-Security-Policy"] = ARTIFACT_CSP
            resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            resp.headers.setdefault("Content-Security-Policy", APP_CSP)
        return resp

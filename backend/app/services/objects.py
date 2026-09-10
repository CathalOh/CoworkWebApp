"""Local object storage (swap for S3 later): content-addressed files under OBJECT_STORE_PATH."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import aiofiles

from app.config import get_settings

ALLOWED_MIME_PREFIXES = ("text/", "image/", "application/pdf", "application/json", "application/vnd.openxmlformats",
                         "application/vnd.ms-", "application/zip", "application/octet-stream", "application/x-yaml",
                         "text/csv", "application/csv", "application/xml")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
BLOCKED_EXT = {".exe", ".dll", ".sh", ".bat", ".cmd", ".ps1", ".scr", ".msi", ".com", ".jar"}


def _root() -> Path:
    p = Path(get_settings().object_store_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def validate_upload(filename: str, mime: str | None, size: int) -> str | None:
    if size > MAX_UPLOAD_BYTES:
        return "file too large"
    if Path(filename).suffix.lower() in BLOCKED_EXT:
        return "file type not allowed"
    if mime and not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        return f"mime type {mime} not allowed"
    return None


async def put(data: bytes, hint: str = "") -> str:
    digest = hashlib.sha256(data).hexdigest()
    key = f"{digest[:2]}/{digest[2:4]}/{digest}-{uuid.uuid4().hex[:8]}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    return key


async def get(key: str) -> bytes:
    path = (_root() / key).resolve()
    if _root().resolve() not in path.parents:
        raise ValueError("bad object key")
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


def path_for(key: str) -> Path:
    path = (_root() / key).resolve()
    if _root().resolve() not in path.parents:
        raise ValueError("bad object key")
    return path


async def delete(key: str) -> None:
    p = path_for(key)
    if p.exists():
        p.unlink()

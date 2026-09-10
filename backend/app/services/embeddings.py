"""Embedding provider. `hash` is a deterministic, dependency-free feature-hashing embedder for dev/tests;
`openai_compat` calls an /v1/embeddings endpoint (LiteLLM/ILIAD) for real vectors."""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from app.config import get_settings

_TOKEN = re.compile(r"[a-z0-9]+")


def hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    toks = _TOKEN.findall(text.lower())
    for i, t in enumerate(toks):
        for gram in (t, toks[i - 1] + "_" + t if i else None):
            if not gram:
                continue
            h = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


async def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.embedding_provider == "openai_compat" and s.litellm_base_url:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(s.litellm_base_url.rstrip("/") + "/v1/embeddings",
                             headers={"Authorization": f"Bearer {s.litellm_api_key}"},
                             json={"model": "text-embedding-3-small", "input": texts})
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
    return [hash_embed(t, s.embeddings_dim) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))

"""Envelope encryption for connector credentials and PII.

A per-record data-encryption key (DEK) encrypts the payload with AES-256-GCM; the DEK is wrapped by
the master key (KMS-backed in prod; a base64 env var locally). Rotation = re-wrap DEKs with the new
master key version, no payload re-encryption.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


@dataclass(frozen=True)
class Envelope:
    ciphertext: bytes
    enc_dek: bytes
    key_version: int


class MasterKeyProvider:
    """Abstracts the KMS. Local implementation keeps versioned keys in memory from env."""

    def __init__(self, keys: dict[int, bytes]):
        if not keys:
            raise ValueError("no master keys configured")
        self._keys = keys
        self.current_version = max(keys)

    @classmethod
    def from_settings(cls) -> MasterKeyProvider:
        s = get_settings()
        if s.kms_master_key_b64:
            key = base64.b64decode(s.kms_master_key_b64)
        else:
            if s.is_prod:
                raise RuntimeError("KMS_MASTER_KEY_B64 must be set in prod")
            # deterministic dev key derived from secret_key so restarts keep data readable
            key = (s.secret_key.encode() * 4)[:32]
        if len(key) != 32:
            raise ValueError("master key must be 32 bytes")
        return cls({1: key})

    def wrap(self, dek: bytes) -> tuple[bytes, int]:
        v = self.current_version
        nonce = os.urandom(12)
        return nonce + AESGCM(self._keys[v]).encrypt(nonce, dek, b"dek-v%d" % v), v

    def unwrap(self, enc_dek: bytes, version: int) -> bytes:
        key = self._keys[version]
        return AESGCM(key).decrypt(enc_dek[:12], enc_dek[12:], b"dek-v%d" % version)


_provider: MasterKeyProvider | None = None


def master_keys() -> MasterKeyProvider:
    global _provider
    if _provider is None:
        _provider = MasterKeyProvider.from_settings()
    return _provider


def encrypt(plaintext: bytes, aad: bytes = b"") -> Envelope:
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ct = nonce + AESGCM(dek).encrypt(nonce, plaintext, aad)
    enc_dek, version = master_keys().wrap(dek)
    return Envelope(ciphertext=ct, enc_dek=enc_dek, key_version=version)


def decrypt(env: Envelope, aad: bytes = b"") -> bytes:
    dek = master_keys().unwrap(env.enc_dek, env.key_version)
    return AESGCM(dek).decrypt(env.ciphertext[:12], env.ciphertext[12:], aad)


def rewrap(env: Envelope) -> Envelope:
    """Key rotation: re-wrap the DEK under the current master key version."""
    dek = master_keys().unwrap(env.enc_dek, env.key_version)
    enc_dek, version = master_keys().wrap(dek)
    return Envelope(ciphertext=env.ciphertext, enc_dek=enc_dek, key_version=version)

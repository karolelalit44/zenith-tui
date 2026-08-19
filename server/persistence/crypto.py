"""Encryption at rest for session data (Gap #10).

When ``ZENITH_ENCRYPTION_KEY`` is set, ``messages.content``/``metadata_json``
and ``sessions.metadata_json`` are Fernet-encrypted before hitting SQLite and
decrypted on read. The key may be a raw Fernet key (``Fernet.generate_key()``)
or an arbitrary passphrase (derived via PBKDF2-HMAC-SHA256). Without a key the
repositories stay plaintext and are fully backward compatible. The key itself
is never logged.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from server.config.env import optional_env

logger = logging.getLogger(__name__)

ENCRYPTION_KEY_ENV = "ZENITH_ENCRYPTION_KEY"
ENCRYPTED_PREFIX = "zenith-enc:"
_PBKDF2_SALT = b"zenith-session-encryption"
_PBKDF2_ITERATIONS = 200_000


def encryption_enabled() -> bool:
    return bool(optional_env(ENCRYPTION_KEY_ENV))


def _key_bytes(raw: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii") + b"=" * (-len(raw) % 4))
        if len(decoded) == 32:
            return raw.encode("ascii")
    except Exception:
        pass
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_PBKDF2_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw.encode("utf-8")))


@lru_cache(maxsize=1)
def _fernet() -> Fernet | None:
    raw = optional_env(ENCRYPTION_KEY_ENV)
    if not raw:
        return None
    return Fernet(_key_bytes(raw))


def encrypt_text(text: str) -> str:
    """Encrypt ``text`` for at-rest storage; no-op without a key."""
    if not text or _fernet() is None:
        return text
    return ENCRYPTED_PREFIX + _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_text(text: str) -> str:
    """Decrypt an at-rest value; plaintext and malformed values pass through."""
    if not text or not text.startswith(ENCRYPTED_PREFIX):
        return text
    fernet = _fernet()
    if fernet is None:
        logger.warning("Encrypted value found but ZENITH_ENCRYPTION_KEY is not set")
        return text
    try:
        return fernet.decrypt(text[len(ENCRYPTED_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        logger.warning("Failed to decrypt stored value (key mismatch?); returning raw")
        return text
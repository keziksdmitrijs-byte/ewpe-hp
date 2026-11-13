"""AES-128-ECB as the Gree+ cloud and the units use it."""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BLOCK = 16


def _cipher(key: bytes) -> Cipher:
    return Cipher(algorithms.AES(key), modes.ECB())


def encrypt(key: bytes, data: bytes) -> bytes:
    """PKCS#7-padded AES-128-ECB."""
    pad = BLOCK - len(data) % BLOCK
    encryptor = _cipher(key).encryptor()
    return encryptor.update(data + bytes([pad]) * pad) + encryptor.finalize()


def decrypt(key: bytes, data: bytes) -> bytes:
    decryptor = _cipher(key).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    pad = plain[-1] if plain else 0
    if 0 < pad <= BLOCK and plain.endswith(bytes([pad]) * pad):
        return plain[:-pad]
    return plain


def seal(key: str, message: dict[str, Any]) -> str:
    """A pack for a unit: its JSON (spaced as the Gree+ app writes it), encrypted with the unit's key, in base64."""
    return base64.b64encode(encrypt(key.encode(), json.dumps(message).encode())).decode()


def open_pack(key: str, pack: str) -> dict[str, Any]:
    """A pack from a unit. Some modules pad with junk instead of PKCS#7: what follows the JSON is dropped."""
    text = decrypt(key.encode(), base64.b64decode(pack)).decode(errors="ignore")
    end = text.rfind("}")
    if end < 0:
        raise ValueError("No JSON in the pack")
    return json.loads(text[: end + 1])

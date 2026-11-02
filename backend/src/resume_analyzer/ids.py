"""Analysis ids: ULIDs (26 chars, Crockford base32, time-ordered).

The sort key ``ANALYSIS#<ulid>`` sorts by creation time, so the history query can return the
newest analyses first without a separate index.
"""

from __future__ import annotations

import os
import re
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def new_ulid(now_ms: int | None = None, randomness: bytes | None = None) -> str:
    """48-bit millisecond timestamp + 80 random bits, encoded as 26 base32 characters."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    rand = os.urandom(10) if randomness is None else randomness
    value = (ms << 80) | int.from_bytes(rand, "big")
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def is_ulid(value: object) -> bool:
    return isinstance(value, str) and bool(ULID_RE.match(value))

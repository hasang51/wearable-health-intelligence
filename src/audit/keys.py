"""Redact sensitive or dynamic JSON object keys before path emission."""

from __future__ import annotations

import re
from collections import Counter

from src.audit.privacy import DYNAMIC_KEY_TOKEN

_UUID_KEY_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$",
)
_MAC_KEY_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_NUMERIC_KEY_RE = re.compile(r"^\d+(\.\d+)?$")
_IDENTIFIER_KEY_RE = re.compile(
    r"^(patient|protocol|device|mac|consent|user|email|phone|ssn|mrn)(_|$)|"
    r"(patient_name|protocol_number|device_mac|consent_image)",
    re.IGNORECASE,
)

# High-cardinality heuristic: hex-looking or very long random-looking keys.
_HEXISH_RE = re.compile(r"^[0-9A-Fa-f]{16,}$")
_HIGH_CARD_MIN_LEN = 24


def is_sensitive_or_dynamic_key(key: str) -> bool:
    """Return True when a dict key must not appear as a schema path segment."""
    if not isinstance(key, str):
        key = str(key)
    if _UUID_KEY_RE.match(key):
        return True
    if _MAC_KEY_RE.match(key):
        return True
    if _NUMERIC_KEY_RE.match(key):
        return True
    if _IDENTIFIER_KEY_RE.search(key):
        return True
    if _HEXISH_RE.match(key):
        return True
    if len(key) >= _HIGH_CARD_MIN_LEN and not re.search(r"[_\-.]", key):
        # Long unbroken token without structural separators → likely dynamic id.
        return True
    return False


def redact_key(key: str) -> str:
    if is_sensitive_or_dynamic_key(key):
        return DYNAMIC_KEY_TOKEN
    return key


def redact_path_segments(segments: list[str]) -> str:
    """Join path segments with '.' after redacting dynamic keys. '[]' marks arrays."""
    parts: list[str] = []
    for seg in segments:
        if seg == "[]":
            parts.append("[]")
        else:
            parts.append(redact_key(seg))
    return ".".join(parts)


class KeyCardinalityTracker:
    """Track distinct raw keys seen under a parent path to flag high cardinality."""

    def __init__(self, distinct_threshold: int = 20) -> None:
        self._threshold = distinct_threshold
        self._seen: dict[str, set[str]] = {}
        self._counts: Counter[str] = Counter()

    def observe(self, parent_path: str, raw_key: str) -> bool:
        """Record key; return True if this parent now looks high-cardinality."""
        bucket = self._seen.setdefault(parent_path, set())
        bucket.add(raw_key)
        self._counts[parent_path] = len(bucket)
        return len(bucket) >= self._threshold

    def should_redact(self, parent_path: str, raw_key: str) -> bool:
        if is_sensitive_or_dynamic_key(raw_key):
            return True
        bucket = self._seen.get(parent_path, set())
        return len(bucket) >= self._threshold and raw_key in bucket

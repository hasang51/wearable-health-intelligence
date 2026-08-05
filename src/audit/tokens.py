"""Token-boundary and camelCase-aware name matching."""

from __future__ import annotations

import re

_CAMEL_SPLIT_RE = re.compile(
    r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+",
)


def split_name_tokens(name: str) -> list[str]:
    """Split snake_case, kebab-case, dot paths, and camelCase into lower tokens."""
    if not name:
        return []
    # Replace common separators, keep camelCase for secondary split.
    pieces = re.split(r"[_\-.\s/]+", name)
    tokens: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if piece.isupper() and len(piece) <= 5:
            tokens.append(piece.lower())
            continue
        parts = _CAMEL_SPLIT_RE.findall(piece)
        if parts:
            tokens.extend(p.lower() for p in parts)
        else:
            tokens.append(piece.lower())
    return tokens


def tokens_match(name: str, needle: str) -> bool:
    """True if needle matches a full token sequence in name (boundary-aware)."""
    name_tokens = split_name_tokens(name)
    needle_tokens = split_name_tokens(needle)
    if not name_tokens or not needle_tokens:
        return False
    n = len(needle_tokens)
    for i in range(len(name_tokens) - n + 1):
        if name_tokens[i : i + n] == needle_tokens:
            return True
    return False


def any_token_match(name: str, needles: tuple[str, ...] | list[str]) -> bool:
    return any(tokens_match(name, n) for n in needles)


# Modality token sets (multi-token phrases listed as space/camel forms).
MODALITY_TOKENS: dict[str, tuple[str, ...]] = {
    "ppg": ("ppg", "photoplethysmography", "photoplethysmogram"),
    "accelerometer": ("accelerometer", "accel", "acc", "imu"),
    "heart_rate": ("heart_rate", "heartRate", "hr", "bpm"),
    "hrv": ("hrv", "heart_rate_variability", "rmssd", "sdnn"),
    "spo2": ("spo2", "sp_o2", "oxygen_saturation", "o2sat"),
    "ecg": ("ecg", "ekg", "electrocardiogram"),
    "temperature": ("temperature", "temp", "skin_temp"),
    "sleep": ("sleep", "sleep_stage", "sleepStage"),
    "activity": ("activity", "steps", "calories"),
    "blood_pressure": ("blood_pressure", "bloodPressure", "bp", "systolic", "diastolic"),
    "glucose": ("glucose", "cgm", "blood_glucose", "ibg"),
}

TIMESTAMP_TOKENS: tuple[str, ...] = (
    "timestamp",
    "timestamps",
    "time",
    "datetime",
    "date_time",
    "ts",
    "recorded_at",
    "sampled_at",
    "created_at",
    "updated_at",
    "start_time",
    "end_time",
    "time_ms",
    "time_s",
    "time_us",
    "epoch_ms",
    "epoch_s",
)

# Unit hints attached to timestamp field names.
TIMESTAMP_UNIT_HINTS: dict[str, str] = {
    "time_ms": "ms",
    "epoch_ms": "ms",
    "time_us": "us",
    "time_s": "s",
    "epoch_s": "s",
    "timestamp_ms": "ms",
    "timestamp_s": "s",
}


def match_modality(name: str) -> set[str]:
    """Return modality ids whose tokens appear in column/key path name."""
    hits: set[str] = set()
    # Prefer longer/more specific modalities first to reduce ambiguity notes.
    for modality, needles in MODALITY_TOKENS.items():
        if any_token_match(name, needles):
            # Special case: 'hr' must not steal 'hrv' — tokens_match already
            # requires full token equality so hrv != hr.
            hits.add(modality)
    return hits


def is_timestamp_field(name: str) -> bool:
    return any_token_match(name, TIMESTAMP_TOKENS)


def timestamp_unit_hint(name: str) -> str | None:
    tokens = split_name_tokens(name)
    joined = "_".join(tokens)
    for key, unit in TIMESTAMP_UNIT_HINTS.items():
        if tokens_match(joined, key) or tokens_match(name, key):
            return unit
    # Suffix heuristics on last token.
    if tokens:
        last = tokens[-1]
        if last in {"ms", "milliseconds"}:
            return "ms"
        if last in {"us", "microseconds"}:
            return "us"
        if last in {"s", "sec", "seconds"}:
            return "s"
    return None

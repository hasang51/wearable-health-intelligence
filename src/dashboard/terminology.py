"""Allowed and forbidden terminology for Phase 4 outputs."""

from __future__ import annotations

# Required research phrasing (documentation / UI should prefer these).
REQUIRED_PHRASES = [
    "UNVERIFIED",
    "INSUFFICIENT_CHANNEL_AGREEMENT",
    "NOT_COMPUTED",
    "plausible_candidate_signal",
    "candidate periodic frequency",
    "research-only signal plausibility",
]

# Forbidden clinical / overclaim phrases (case-insensitive substring match).
FORBIDDEN_PHRASES = [
    "diagnosed",
    "patient risk",
    "detected disease",
    "confirmed PPG",
    "confirmed ppg",
    "accurate heart rate",
    "clinical-grade",
    "clinical grade",
    "medical alert",
    "normal patient",
    "abnormal patient",
    "validated PPG",
    "validated ppg",
    "this is heart rate",
    "HRV computed",
    "SpO2 computed",
    "blood pressure estimate",
    "disease-risk",
]


def find_forbidden_phrases(text: str) -> list[str]:
    """Return list of forbidden phrases found in text (case-insensitive)."""
    if not text:
        return []
    lower = text.lower()
    found: list[str] = []
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in lower:
            found.append(phrase)
    return found


def assert_no_forbidden_terminology(text: str, *, context: str = "") -> None:
    found = find_forbidden_phrases(text)
    if found:
        loc = f" in {context}" if context else ""
        raise AssertionError(f"Forbidden terminology{loc}: {found}")

"""Privacy checks for dashboard inputs and rendered text — no CSV/private opens."""

from __future__ import annotations

import re
from pathlib import Path

from src.dashboard.terminology import assert_no_forbidden_terminology, find_forbidden_phrases

# Re-export for convenience
__all__ = [
    "assert_no_forbidden_terminology",
    "find_forbidden_phrases",
    "find_privacy_leaks",
    "assert_safe_json_path",
    "FORBIDDEN_EXTENSIONS",
]

FORBIDDEN_EXTENSIONS = frozenset({".csv", ".parquet", ".db", ".sqlite"})

_ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
)
_MAC_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
)


def find_privacy_leaks(text: str) -> list[str]:
    leaks: list[str] = []
    if _ISO_TS_RE.search(text):
        leaks.append("exact_timestamp")
    if _MAC_RE.search(text):
        leaks.append("mac_address")
    return leaks


def assert_safe_json_path(path: Path) -> Path:
    """Ensure path is an explicit JSON file — never CSV/parquet/private dirs by extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in FORBIDDEN_EXTENSIONS:
        raise ValueError(
            f"Refusing to open non-safe aggregate file type: {suffix}. "
            "Dashboard accepts JSON safe aggregates only."
        )
    if suffix != ".json":
        raise ValueError(f"Safe report path must be .json, got {suffix!r}")
    # Do not scan directories; only open the explicit file if it exists.
    if not p.is_file():
        raise FileNotFoundError(f"Safe report not found: {p}")
    name_lower = p.name.lower()
    if "private" in name_lower and "safe" not in name_lower:
        # Soft guard: private-named JSON is not a valid dashboard input convention.
        raise ValueError(
            "Refusing path that appears to be a private report. "
            "Supply safe aggregate JSON only."
        )
    return p

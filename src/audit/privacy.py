"""Privacy scrubbing for all output channels."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable


INPUT_PATH_TOKEN = "<input_path>"
DYNAMIC_KEY_TOKEN = "<dynamic_key>"

# Patterns that must never appear in any emitted channel when known from fixtures/runs.
_MAC_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
)
_UUID_RE = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b",
)
_ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
)


class PrivacyScrubber:
    """Redact known sensitive strings and structural PII patterns from text."""

    def __init__(self) -> None:
        self._literal_redactions: list[str] = []
        self._input_path: str | None = None
        self._input_name: str | None = None

    def register_input_path(self, path: str | Path) -> None:
        p = Path(path)
        self._input_path = str(path)
        self._input_name = p.name
        # Also register resolved forms if available, without walking parents for discovery.
        try:
            resolved = str(p.resolve(strict=False))
            if resolved not in self._literal_redactions:
                self._literal_redactions.append(resolved)
        except OSError:
            pass
        for candidate in (self._input_path, self._input_name):
            if candidate and candidate not in self._literal_redactions:
                self._literal_redactions.append(candidate)

    def register_literals(self, values: Iterable[str]) -> None:
        for v in values:
            if v and v not in self._literal_redactions:
                self._literal_redactions.append(v)

    def scrub(self, text: str) -> str:
        if not text:
            return text
        out = text
        path_literals = {
            x for x in (self._input_path, self._input_name) if x
        }
        # Longest literals first to avoid partial leftovers.
        for lit in sorted(self._literal_redactions, key=len, reverse=True):
            if lit and lit in out:
                replacement = (
                    INPUT_PATH_TOKEN if lit in path_literals else "<redacted>"
                )
                out = out.replace(lit, replacement)
        out = _MAC_RE.sub("<redacted_mac>", out)
        out = _UUID_RE.sub("<redacted_uuid>", out)
        out = _ISO_TS_RE.sub("<redacted_timestamp>", out)
        return out


class ScrubbingFilter(logging.Filter):
    """Logging filter that scrubs record messages in place."""

    def __init__(self, scrubber: PrivacyScrubber) -> None:
        super().__init__()
        self._scrubber = scrubber

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            scrubbed = self._scrubber.scrub(msg)
            record.msg = scrubbed
            record.args = ()
        except Exception:
            record.msg = "<redacted_log>"
            record.args = ()
        return True


class ScrubbedException(Exception):
    """Exception whose string form is always scrubbed."""

    def __init__(self, message: str, scrubber: PrivacyScrubber) -> None:
        self._scrubbed = scrubber.scrub(message)
        super().__init__(self._scrubbed)

    def __str__(self) -> str:
        return self._scrubbed


# Process-wide scrubber used by CLI/logging.
SCRUBBER = PrivacyScrubber()

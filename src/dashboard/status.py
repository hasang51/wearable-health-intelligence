"""Status sentinel — never invent missing scientific statuses."""

from __future__ import annotations

from typing import TypeAlias

NOT_AVAILABLE = "NOT_AVAILABLE"

StatusValue: TypeAlias = str


def present_or_na(value: object | None) -> StatusValue:
    """Return string value or NOT_AVAILABLE; never invent scientific statuses."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, str) and not value.strip():
        return NOT_AVAILABLE
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def is_available(value: object | None) -> bool:
    if value is None:
        return False
    if value == NOT_AVAILABLE:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True

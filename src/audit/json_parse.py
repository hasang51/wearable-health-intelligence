"""Defensive per-cell JSON classification."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class CellParseStatus(str, Enum):
    NULL = "null"
    EMPTY = "empty"
    EMPTY_ARRAY = "empty_array"
    EMPTY_OBJECT = "empty_object"
    OBJECT = "object"
    ARRAY = "array"
    SCALAR = "scalar"
    MALFORMED = "malformed"


def _is_nullish(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, float) and raw != raw:  # NaN
        return True
    return False


def parse_cell(raw: Any) -> tuple[CellParseStatus, Any | None]:
    """Classify a CSV cell without raising.

    Returns (status, parsed_value_or_None). Parsed values are only used
    transiently for structural walking — never written to reports.
    """
    if _is_nullish(raw):
        return CellParseStatus.NULL, None

    if not isinstance(raw, str):
        raw = str(raw)

    text = raw.strip()
    if text == "" or text.lower() in {"null", "none", "nan"}:
        return CellParseStatus.EMPTY, None

    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return CellParseStatus.MALFORMED, None

    if value is None:
        return CellParseStatus.NULL, None
    if isinstance(value, list):
        if len(value) == 0:
            return CellParseStatus.EMPTY_ARRAY, value
        return CellParseStatus.ARRAY, value
    if isinstance(value, dict):
        if len(value) == 0:
            return CellParseStatus.EMPTY_OBJECT, value
        return CellParseStatus.OBJECT, value
    # JSON scalar (number/bool/string)
    return CellParseStatus.SCALAR, value


def is_empty_status(status: CellParseStatus) -> bool:
    return status in {
        CellParseStatus.NULL,
        CellParseStatus.EMPTY,
        CellParseStatus.EMPTY_ARRAY,
        CellParseStatus.EMPTY_OBJECT,
    }


def is_populated_status(status: CellParseStatus) -> bool:
    return status in {
        CellParseStatus.OBJECT,
        CellParseStatus.ARRAY,
        CellParseStatus.SCALAR,
    }

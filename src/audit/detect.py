"""JSON-like column detection from non-empty cells."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from src.audit.json_parse import CellParseStatus, parse_cell
from src.audit.models import ColumnKind


def _is_non_empty_cell(raw: object) -> bool:
    if raw is None:
        return False
    text = str(raw).strip()
    return text != "" and text.lower() not in {"null", "none", "nan"}


def classify_column(
    name: str,
    cells: Sequence[object] | Iterable[object],
) -> ColumnKind:
    """Classify a column as ordinary, json_like, or mixed_malformed.

    Rules:
    - Inspect non-empty cells only.
    - Columns ending with `_json` are JSON candidates.
    - `[]` and `{}` count as JSON evidence.
    - Sparse population (1 of N) is enough for json_like if parseable.
    - Mix of successful JSON structures and malformed content → mixed_malformed.
    """
    suffix_candidate = name.lower().endswith("_json")
    json_ok = 0
    malformed = 0
    ordinaryish = 0

    for cell in cells:
        if not _is_non_empty_cell(cell):
            continue
        status, _ = parse_cell(cell)
        if status == CellParseStatus.MALFORMED:
            # Non-JSON text that isn't empty.
            text = str(cell).strip()
            if text in {"[]", "{}"}:
                json_ok += 1
            else:
                # Attempt: if it looks like JSON start but failed → malformed
                if text[:1] in {"{", "[", '"'} or suffix_candidate:
                    malformed += 1
                else:
                    ordinaryish += 1
            continue
        if status in {
            CellParseStatus.EMPTY_ARRAY,
            CellParseStatus.EMPTY_OBJECT,
            CellParseStatus.OBJECT,
            CellParseStatus.ARRAY,
        }:
            json_ok += 1
        elif status == CellParseStatus.SCALAR:
            # JSON scalars alone do not make a column json_like unless _json suffix.
            if suffix_candidate:
                json_ok += 1
            else:
                ordinaryish += 1
        else:
            ordinaryish += 1

    if suffix_candidate and (json_ok > 0 or malformed > 0):
        if malformed > 0 and json_ok > 0:
            return ColumnKind.MIXED_MALFORMED
        if malformed > 0 and json_ok == 0:
            return ColumnKind.MIXED_MALFORMED
        return ColumnKind.JSON_LIKE

    if json_ok > 0 and malformed > 0:
        return ColumnKind.MIXED_MALFORMED
    if json_ok > 0:
        return ColumnKind.JSON_LIKE
    if malformed > 0 and ordinaryish == 0:
        # All non-empty looked like JSON but failed.
        return ColumnKind.MIXED_MALFORMED
    return ColumnKind.ORDINARY


def classify_columns(
    column_values: Mapping[str, Sequence[object]],
) -> dict[str, ColumnKind]:
    return {name: classify_column(name, cells) for name, cells in column_values.items()}

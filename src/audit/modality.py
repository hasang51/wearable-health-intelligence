"""Per-session modality coverage with explicit status codes."""

from __future__ import annotations

from typing import Any

from src.audit.json_parse import CellParseStatus, is_empty_status, parse_cell
from src.audit.models import ModalityStatus, empty_modality_status_counts
from src.audit.tokens import MODALITY_TOKENS, match_modality
from src.audit.walk import WalkAccumulator


ALL_MODALITIES: tuple[str, ...] = tuple(MODALITY_TOKENS.keys())


def _paths_for_modality(paths: list[str], modality: str) -> list[str]:
    return [p for p in paths if modality in match_modality(p)]


def _columns_for_modality(columns: list[str], modality: str) -> list[str]:
    return [c for c in columns if modality in match_modality(c)]


def evaluate_modality_status(
    modality: str,
    columns: list[str],
    row: dict[str, str],
    walks_by_column: dict[str, WalkAccumulator | None],
    parse_status_by_column: dict[str, CellParseStatus],
) -> ModalityStatus:
    """Derive one modality status for a single session row."""
    relevant_cols = _columns_for_modality(columns, modality)

    # Also consider JSON paths discovered under any json column.
    path_hits: list[str] = []
    for col, acc in walks_by_column.items():
        if acc is None:
            continue
        path_hits.extend(_paths_for_modality(list(acc.key_paths.keys()), modality))
        if modality in match_modality(col):
            path_hits.append(col)

    if not relevant_cols and not path_hits:
        return ModalityStatus.COLUMN_ABSENT

    # Prefer column-level parse status when modality maps to a column name.
    statuses = [parse_status_by_column[c] for c in relevant_cols if c in parse_status_by_column]

    if relevant_cols and all(
        is_empty_status(parse_status_by_column.get(c, CellParseStatus.EMPTY))
        for c in relevant_cols
    ) and not path_hits:
        return ModalityStatus.PAYLOAD_EMPTY

    if statuses and all(s == CellParseStatus.MALFORMED for s in statuses) and not path_hits:
        return ModalityStatus.PAYLOAD_MALFORMED

    # If any relevant column malformed and none populated → malformed
    if statuses and any(s == CellParseStatus.MALFORMED for s in statuses):
        if not any(
            s in {CellParseStatus.OBJECT, CellParseStatus.ARRAY, CellParseStatus.SCALAR}
            for s in statuses
        ) and not path_hits:
            return ModalityStatus.PAYLOAD_MALFORMED

    # Structure present?
    sample_total = 0
    structure_seen = bool(path_hits) or bool(relevant_cols)
    for col in relevant_cols:
        acc = walks_by_column.get(col)
        if acc is not None:
            sample_total += acc.sample_count_estimate
            if acc.key_paths:
                structure_seen = True
        st = parse_status_by_column.get(col)
        if st in {CellParseStatus.EMPTY_ARRAY, CellParseStatus.EMPTY_OBJECT}:
            structure_seen = True
        if st in {CellParseStatus.OBJECT, CellParseStatus.ARRAY}:
            structure_seen = True

    # Path-only hits from nested keys under other columns
    for col, acc in walks_by_column.items():
        if acc is None:
            continue
        matched_paths = _paths_for_modality(list(acc.key_paths.keys()), modality)
        if matched_paths:
            structure_seen = True
            # Count samples under matched path prefixes when arrays of scalars.
            sample_total += acc.sample_count_estimate if matched_paths else 0

    if not structure_seen:
        return ModalityStatus.NOT_EVALUABLE

    if sample_total > 0:
        return ModalityStatus.SAMPLES_PRESENT

    # Empty arrays/objects or objects without sample arrays
    empty_like = False
    for col in relevant_cols:
        st = parse_status_by_column.get(col)
        if st in {
            CellParseStatus.EMPTY_ARRAY,
            CellParseStatus.EMPTY_OBJECT,
            CellParseStatus.EMPTY,
            CellParseStatus.NULL,
        }:
            empty_like = True
    if empty_like and sample_total == 0 and not path_hits:
        return ModalityStatus.PAYLOAD_EMPTY

    return ModalityStatus.STRUCTURE_PRESENT_NO_SAMPLES


def aggregate_modality_coverage(
    per_session: list[dict[str, ModalityStatus]],
) -> list[dict[str, Any]]:
    """Aggregate per-session statuses into counts per modality."""
    result: list[dict[str, Any]] = []
    for modality in ALL_MODALITIES:
        counts = empty_modality_status_counts()
        for session in per_session:
            status = session.get(modality, ModalityStatus.NOT_EVALUABLE)
            counts[status.value] = counts.get(status.value, 0) + 1
        result.append({"modality": modality, "status_counts": counts})
    return result

"""Session and upload inconsistency detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.audit.json_parse import CellParseStatus, is_empty_status, parse_cell
from src.audit.models import ColumnKind, InconsistencyRecord
from src.audit.tokens import (
    any_token_match,
    is_timestamp_field,
    match_modality,
    split_name_tokens,
    timestamp_unit_hint,
)
from src.audit.walk import WalkAccumulator


UPLOAD_SENT_TOKENS = ("sent", "chunks_sent", "sent_chunks")
UPLOAD_TOTAL_TOKENS = ("total", "chunks_total", "total_chunks")
UPLOAD_FAILED_TOKENS = ("failed", "chunks_failed", "failed_chunks")
UPLOAD_PENDING_TOKENS = ("pending", "upload_pending", "pending_upload")
DURATION_TOKENS = ("duration", "session_duration", "duration_s", "duration_ms", "duration_sec")


@dataclass
class ConsistencyContext:
    session_ordinal: int
    columns: list[str]
    row: dict[str, str]
    column_kinds: dict[str, ColumnKind]
    parse_status: dict[str, CellParseStatus]
    walks: dict[str, WalkAccumulator | None]


def _find_numeric_field(row: dict[str, str], needles: tuple[str, ...]) -> tuple[str | None, float | None]:
    for col, raw in row.items():
        if not any_token_match(col, needles):
            continue
        text = str(raw).strip()
        if not text:
            continue
        # Prefer ordinary numeric cells; also try JSON scalar.
        status, parsed = parse_cell(text)
        candidate: Any = parsed if status.name == "SCALAR" else text
        try:
            if isinstance(candidate, bool):
                continue
            return col, float(candidate)
        except (TypeError, ValueError):
            continue
    return None, None


def _parse_timestamp_value(value: Any, unit: str | None) -> float | None:
    """Return epoch seconds if unambiguously parseable with known unit; else None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if unit == "ms":
            return float(value) / 1000.0
        if unit == "us":
            return float(value) / 1_000_000.0
        if unit == "s":
            return float(value)
        # Numeric without unit → not evaluable
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # ISO-8601 only when clearly dated (has date separators).
        if "T" in text or (len(text) >= 10 and text[4:5] == "-"):
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return dt.timestamp()
            except ValueError:
                return None
        try:
            num = float(text)
        except ValueError:
            return None
        return _parse_timestamp_value(num, unit)
    return None


def _extract_timestamp_span(
    walks: dict[str, WalkAccumulator | None],
    row: dict[str, str],
) -> tuple[float | None, str]:
    """Attempt to compute sensor time span from unambiguously unit-known timestamps.

    Returns (span_seconds_or_None, detail_code_suffix).
    Never infers duration from array length.
    """
    # We only evaluate when unit_known timestamp fields exist.
    # Without storing raw values in walks, re-parse relevant cells transiently.
    unit_known_paths: list[tuple[str, bool]] = []
    for acc in walks.values():
        if acc is None:
            continue
        for path, unit_known in acc.timestamp_fields.items():
            if unit_known:
                unit_known_paths.append((path, unit_known))

    if not unit_known_paths:
        return None, "duration_not_evaluable"

    # Look for arrays named with unit-known timestamp tokens in row JSON cells.
    times: list[float] = []
    for col, raw in row.items():
        status, parsed = parse_cell(raw)
        if status not in {CellParseStatus.OBJECT, CellParseStatus.ARRAY}:
            continue
        _collect_unit_known_times(parsed, [], times)
        if len(times) >= 2:
            break

    if len(times) < 2:
        return None, "duration_not_evaluable"

    span = max(times) - min(times)
    if span < 0:
        return None, "duration_not_evaluable"
    return span, "ok"


def _collect_unit_known_times(node: Any, segments: list[str], out: list[float]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            key = str(k)
            unit = timestamp_unit_hint(key) if is_timestamp_field(key) else None
            if isinstance(v, list) and unit is not None:
                for item in v[:50]:  # bound
                    ts = _parse_timestamp_value(item, unit)
                    if ts is not None:
                        out.append(ts)
            elif isinstance(v, (int, float, str)) and unit is not None:
                ts = _parse_timestamp_value(v, unit)
                if ts is not None:
                    out.append(ts)
            else:
                _collect_unit_known_times(v, [*segments, key], out)
    elif isinstance(node, list):
        for item in node[:50]:
            _collect_unit_known_times(item, segments, out)


def check_session(ctx: ConsistencyContext) -> list[InconsistencyRecord]:
    """Return categorical inconsistency records for one session."""
    findings: list[InconsistencyRecord] = []
    ordinal = ctx.session_ordinal

    # Invalid JSON / empty physiological payloads on json-like columns.
    physio_related = False
    for col, kind in ctx.column_kinds.items():
        if kind.value not in {"json_like", "mixed_malformed"}:
            continue
        status = ctx.parse_status.get(col, CellParseStatus.EMPTY)
        modalities = match_modality(col)
        if modalities:
            physio_related = True
        if status == CellParseStatus.MALFORMED:
            findings.append(
                InconsistencyRecord(
                    code="invalid_json",
                    session_ordinal=ordinal,
                    column=col,
                    detail="invalid_json",
                )
            )
        elif is_empty_status(status) and modalities:
            findings.append(
                InconsistencyRecord(
                    code="empty_physiology",
                    session_ordinal=ordinal,
                    column=col,
                    detail="empty_physiology",
                )
            )

    # Upload chunk consistency from ordinary columns.
    sent_col, sent = _find_numeric_field(ctx.row, UPLOAD_SENT_TOKENS)
    total_col, total = _find_numeric_field(ctx.row, UPLOAD_TOTAL_TOKENS)
    failed_col, failed = _find_numeric_field(ctx.row, UPLOAD_FAILED_TOKENS)
    pending_col, pending = _find_numeric_field(ctx.row, UPLOAD_PENDING_TOKENS)

    # Also search nested upload metadata objects.
    if sent is None or total is None:
        for raw in ctx.row.values():
            st, parsed = parse_cell(raw)
            if st != CellParseStatus.OBJECT or not isinstance(parsed, dict):
                continue
            flat = {str(k): v for k, v in parsed.items()}
            # Convert to string map for reuse
            str_map = {k: "" if v is None else str(v) for k, v in flat.items()}
            if sent is None:
                sent_col, sent = _find_numeric_field(str_map, UPLOAD_SENT_TOKENS)
            if total is None:
                total_col, total = _find_numeric_field(str_map, UPLOAD_TOTAL_TOKENS)
            if failed is None:
                failed_col, failed = _find_numeric_field(str_map, UPLOAD_FAILED_TOKENS)
            if pending is None:
                pending_col, pending = _find_numeric_field(str_map, UPLOAD_PENDING_TOKENS)

    if sent is not None and total is not None and sent > total:
        findings.append(
            InconsistencyRecord(
                code="chunk_mismatch",
                session_ordinal=ordinal,
                column=sent_col or total_col,
                detail="sent_gt_total",
            )
        )
    if failed is not None and total is not None and failed > total:
        findings.append(
            InconsistencyRecord(
                code="chunk_mismatch",
                session_ordinal=ordinal,
                column=failed_col or total_col,
                detail="failed_gt_total",
            )
        )
    if sent is not None and failed is not None and total is not None:
        if sent + failed > total + 1e-9:
            findings.append(
                InconsistencyRecord(
                    code="chunk_mismatch",
                    session_ordinal=ordinal,
                    column=total_col,
                    detail="sent_plus_failed_gt_total",
                )
            )
    if pending is not None and pending > 0:
        findings.append(
            InconsistencyRecord(
                code="pending_upload",
                session_ordinal=ordinal,
                column=pending_col,
                detail="pending_upload",
            )
        )
    # Boolean-ish pending flags in column names/values
    for col, raw in ctx.row.items():
        if any_token_match(col, UPLOAD_PENDING_TOKENS):
            text = str(raw).strip().lower()
            if text in {"1", "true", "yes", "pending"}:
                findings.append(
                    InconsistencyRecord(
                        code="pending_upload",
                        session_ordinal=ordinal,
                        column=col,
                        detail="pending_upload",
                    )
                )

    # Duration consistency — only when timestamps unambiguous + unit known.
    dur_col, duration = _find_numeric_field(ctx.row, DURATION_TOKENS)
    duration_seconds: float | None = None
    if duration is not None and dur_col is not None:
        tokens = split_name_tokens(dur_col)
        if "ms" in tokens:
            duration_seconds = duration / 1000.0
        elif "us" in tokens:
            duration_seconds = duration / 1_000_000.0
        elif "s" in tokens or "sec" in tokens or "seconds" in tokens or "duration" in tokens:
            # bare "duration" treated as seconds only when explicitly unit-suffixed
            # or named duration_s; plain "duration" without unit → not_evaluable
            if any(t in {"s", "sec", "seconds"} for t in tokens) or dur_col.lower().endswith("_s"):
                duration_seconds = duration
            elif dur_col.lower() in {"duration_s", "session_duration_s"}:
                duration_seconds = duration
            else:
                duration_seconds = None

    span, span_detail = _extract_timestamp_span(ctx.walks, ctx.row)
    if duration_seconds is None or span is None:
        # Only emit not_evaluable when duration check was attempted (duration field present
        # or timestamp fields present) but could not be completed.
        has_duration_field = dur_col is not None
        has_ts = any(
            acc is not None and acc.timestamp_fields for acc in ctx.walks.values()
        )
        if has_duration_field or has_ts:
            findings.append(
                InconsistencyRecord(
                    code="duration_not_evaluable",
                    session_ordinal=ordinal,
                    column=dur_col,
                    detail="duration_not_evaluable",
                )
            )
    else:
        # Compare with generous relative tolerance; categorical only.
        if duration_seconds > 0:
            rel = abs(span - duration_seconds) / duration_seconds
            if rel > 0.25:
                findings.append(
                    InconsistencyRecord(
                        code="duration_mismatch",
                        session_ordinal=ordinal,
                        column=dur_col,
                        detail="duration_mismatch",
                    )
                )

    _ = physio_related  # reserved for future aggregate flags
    _ = span_detail
    return findings

"""Build and write private/safe audit reports to explicit paths."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.audit import __version__
from src.audit.consistency import ConsistencyContext, check_session
from src.audit.detect import classify_columns
from src.audit.json_parse import (
    CellParseStatus,
    is_empty_status,
    is_populated_status,
    parse_cell,
)
from src.audit.limits import ResourceLimits
from src.audit.modality import aggregate_modality_coverage, evaluate_modality_status
from src.audit.models import (
    ArrayLengthStats,
    ColumnKind,
    ColumnProfile,
    InconsistencyRecord,
    JsonColumnProfile,
    KeyPathProfile,
    LimitsApplied,
    ModalityCoverage,
    ModalityStatus,
    PrivateDataProfile,
    ProfileMeta,
    SafeSchemaProfile,
    TimestampFieldProfile,
)
from src.audit.privacy import SCRUBBER, ScrubbedException
from src.audit.reader import open_csv_rows
from src.audit.tokens import MODALITY_TOKENS
from src.audit.walk import WalkAccumulator, walk_value


def _merge_walk(dst: WalkAccumulator, src: WalkAccumulator) -> None:
    for path, types in src.key_paths.items():
        for t, c in types.items():
            dst.key_paths[path][t] += c
        dst.path_occurrences[path] += src.path_occurrences[path]
    dst.array_lengths.extend(src.array_lengths)
    dst.total_length_observed += src.total_length_observed
    dst.elements_structurally_inspected += src.elements_structurally_inspected
    dst.timestamp_fields.update(src.timestamp_fields)
    dst.hit_depth_limit = dst.hit_depth_limit or src.hit_depth_limit
    dst.hit_key_limit = dst.hit_key_limit or src.hit_key_limit
    dst.sample_count_estimate += src.sample_count_estimate


def _array_stats(lengths: list[int], total_obs: int, inspected: int) -> ArrayLengthStats:
    if not lengths:
        return ArrayLengthStats(
            total_length_observed=total_obs,
            elements_structurally_inspected=inspected,
        )
    return ArrayLengthStats(
        min=float(min(lengths)),
        max=float(max(lengths)),
        mean=float(sum(lengths) / len(lengths)),
        count=len(lengths),
        total_length_observed=total_obs,
        elements_structurally_inspected=inspected,
    )


def run_audit(
    input_path: str | Path,
    limits: ResourceLimits,
) -> PrivateDataProfile:
    """Stream the CSV and build a private structural profile."""
    SCRUBBER.register_input_path(input_path)
    columns, row_iter = open_csv_rows(input_path, limits)

    # First pass materialises row dicts (session-level rows; expected small N).
    # Nested payloads are still parsed per-cell under walk caps — we do not keep
    # parsed trees after each row is processed.
    rows: list[dict[str, str]] = list(row_iter)
    column_values = {c: [r.get(c, "") for r in rows] for c in columns}
    kinds = classify_columns(column_values)

    json_col_stats: dict[str, dict[str, Any]] = {
        c: {
            "populated": 0,
            "empty": 0,
            "malformed": 0,
            "top_level_types": defaultdict(int),
            "walk": WalkAccumulator(),
        }
        for c, k in kinds.items()
        if k in {ColumnKind.JSON_LIKE, ColumnKind.MIXED_MALFORMED}
    }

    ordinary_empty = defaultdict(int)
    ordinary_nonempty = defaultdict(int)
    for c, k in kinds.items():
        if k == ColumnKind.ORDINARY:
            for cell in column_values[c]:
                if str(cell).strip() == "":
                    ordinary_empty[c] += 1
                else:
                    ordinary_nonempty[c] += 1

    per_session_modalities: list[dict[str, ModalityStatus]] = []
    inconsistencies: list[InconsistencyRecord] = []

    for idx, row in enumerate(rows):
        parse_status: dict[str, CellParseStatus] = {}
        walks: dict[str, WalkAccumulator | None] = {}

        for col in columns:
            raw = row.get(col, "")
            status, parsed = parse_cell(raw)
            parse_status[col] = status

            if col in json_col_stats:
                if status == CellParseStatus.MALFORMED:
                    json_col_stats[col]["malformed"] += 1
                    json_col_stats[col]["top_level_types"]["malformed"] += 1
                    walks[col] = None
                elif is_empty_status(status):
                    json_col_stats[col]["empty"] += 1
                    json_col_stats[col]["top_level_types"][status.value] += 1
                    walks[col] = None
                elif is_populated_status(status):
                    json_col_stats[col]["populated"] += 1
                    json_col_stats[col]["top_level_types"][status.value] += 1
                    acc = walk_value(parsed, limits)
                    _merge_walk(json_col_stats[col]["walk"], acc)
                    walks[col] = acc
                else:
                    json_col_stats[col]["empty"] += 1
                    walks[col] = None
            else:
                walks[col] = None

        session_mod: dict[str, ModalityStatus] = {}
        for modality in MODALITY_TOKENS:
            session_mod[modality] = evaluate_modality_status(
                modality, columns, row, walks, parse_status
            )
        per_session_modalities.append(session_mod)

        inconsistencies.extend(
            check_session(
                ConsistencyContext(
                    session_ordinal=idx,
                    columns=columns,
                    row=row,
                    column_kinds=kinds,
                    parse_status=parse_status,
                    walks=walks,
                )
            )
        )
        # Drop parsed trees — walks retained only as merged structural stats.

    column_profiles: list[ColumnProfile] = []
    for c in columns:
        kind = kinds[c]
        if kind == ColumnKind.ORDINARY:
            column_profiles.append(
                ColumnProfile(
                    name=c,
                    kind=kind,
                    null_or_empty_count=ordinary_empty[c],
                    non_empty_count=ordinary_nonempty[c],
                )
            )
        else:
            stats = json_col_stats[c]
            empty = stats["empty"]
            nonempty = stats["populated"] + stats["malformed"]
            # Count truly empty including nullish among all rows
            nullish = sum(
                1
                for cell in column_values[c]
                if str(cell).strip() == "" or str(cell).strip().lower() in {"null", "none", "nan"}
            )
            column_profiles.append(
                ColumnProfile(
                    name=c,
                    kind=kind,
                    null_or_empty_count=nullish,
                    non_empty_count=len(rows) - nullish,
                )
            )

    json_profiles: list[JsonColumnProfile] = []
    for c, stats in json_col_stats.items():
        walk: WalkAccumulator = stats["walk"]
        key_paths = [
            KeyPathProfile(
                path=path,
                value_types=dict(types),
                occurrence_count=walk.path_occurrences[path],
            )
            for path, types in sorted(walk.key_paths.items())
        ]
        ts_fields = [
            TimestampFieldProfile(path=p, unit_known=uk)
            for p, uk in sorted(walk.timestamp_fields.items())
        ]
        json_profiles.append(
            JsonColumnProfile(
                name=c,
                populated_row_count=stats["populated"],
                empty_row_count=stats["empty"],
                malformed_row_count=stats["malformed"],
                top_level_types=dict(stats["top_level_types"]),
                array_length_stats=_array_stats(
                    walk.array_lengths,
                    walk.total_length_observed,
                    walk.elements_structurally_inspected,
                ),
                key_paths=key_paths,
                possible_timestamp_fields=ts_fields,
            )
        )

    modality_coverage = [
        ModalityCoverage(modality=m["modality"], status_counts=m["status_counts"])
        for m in aggregate_modality_coverage(per_session_modalities)
    ]

    meta = ProfileMeta(
        row_count=len(rows),
        column_count=len(columns),
        generated_at=datetime.now(timezone.utc).isoformat(),
        tool_version=__version__,
        limits_applied=LimitsApplied(**limits.as_dict()),
    )
    return PrivateDataProfile(
        meta=meta,
        columns=column_profiles,
        json_columns=json_profiles,
        modality_coverage=modality_coverage,
        inconsistencies=inconsistencies,
    )


def to_safe_profile(private: PrivateDataProfile) -> SafeSchemaProfile:
    """Derive architecture-safe subset: aggregate inconsistencies, keep redacted structure."""
    counts: dict[str, int] = defaultdict(int)
    for item in private.inconsistencies:
        counts[item.code] += 1
    return SafeSchemaProfile(
        meta=private.meta,
        columns=private.columns,
        json_columns=private.json_columns,
        modality_coverage=private.modality_coverage,
        inconsistency_counts=dict(counts),
    )


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to write report: {exc}", SCRUBBER) from None

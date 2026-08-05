"""Build one allowlisted reviewed-dashboard ``dashboard.safe.v1`` JSON."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.dashboard import SCHEMA_VERSION
from src.dashboard.adapters import (
    _adapt_legacy_phase1,
    _adapt_legacy_phase2,
    _adapt_legacy_phase3,
)
from src.dashboard.delivery.facts import SOURCE_KIND_DEMO, SOURCE_KIND_REVIEWED
from src.dashboard.loaders import (
    SafeReportLoadError,
    is_v1_schema,
    load_raw_safe_json,
)
from src.dashboard.models import SafePhase1Input, SafePhase2Input, SafePhase3Input
from src.dashboard.privacy import assert_safe_json_path, find_privacy_leaks
from src.dashboard.status import NOT_AVAILABLE
from src.delivery_export import SOURCE_LABEL
from src.delivery_export.allowlist import strip_unknown
from src.delivery_export.models import (
    ReviewedDashboardBundle,
    ReviewedModalityCoverage,
    ReviewedOverview,
    ReviewedResearchStatus,
)
from src.forensics.models import DecoderStatus
from src.reconstruction.models import ChannelCompatibilityVerdict, RateStatus

_PATH_LEAK_RE = re.compile(
    r"(?i)(?:[A-Za-z]:\\|/home/|/Users/|\\\\|reports[/\\]private|/tmp/)"
)
_SESSION_ID_KEY_RE = re.compile(r"(?i)session[_-]?id|device[_-]?id|patient")
logger = logging.getLogger("delivery_export")

SECONDARY_MODALITY_COUNT_PATHS: tuple[str, ...] = (
    "phase1.modality_coverage[ecg].samples_present",
    "phase1.modality_coverage[temperature].samples_present",
    "phase1.modality_coverage[sleep].samples_present",
    "phase1.modality_coverage[activity].samples_present",
    "phase1.modality_coverage[blood_pressure].samples_present",
)

_DETERMINISTIC_NO_SAMPLE_STATUSES = frozenset(
    {
        "column_absent",
        "payload_empty",
        "structure_present_no_samples",
    }
)


class DeliveryExportError(ValueError):
    """Fail-closed export error (malformed input, privacy, or source integrity)."""


def _validate_v1(model_cls: type, data: dict[str, Any], label: str) -> Any:
    cleaned = strip_unknown(model_cls, data)
    try:
        return model_cls.model_validate(cleaned)
    except ValidationError as exc:
        raise DeliveryExportError(f"Malformed {label} safe report: {exc}") from exc


def _load_phase1(path: Path) -> SafePhase1Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return _validate_v1(SafePhase1Input, data, "Phase 1")
    try:
        return _adapt_legacy_phase1(data)
    except Exception as exc:
        raise DeliveryExportError(f"Cannot adapt Phase 1 safe report: {exc}") from exc


def _load_phase2(path: Path) -> SafePhase2Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return _validate_v1(SafePhase2Input, data, "Phase 2")
    try:
        return _adapt_legacy_phase2(data)
    except Exception as exc:
        raise DeliveryExportError(f"Cannot adapt Phase 2 safe report: {exc}") from exc


def _load_phase3(path: Path) -> SafePhase3Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return _validate_v1(SafePhase3Input, data, "Phase 3")
    try:
        return _adapt_legacy_phase3(data)
    except Exception as exc:
        raise DeliveryExportError(f"Cannot adapt Phase 3 safe report: {exc}") from exc


def _require_enum(value: Any, enum_cls: type, field: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DeliveryExportError(
            f"Missing scientific status {field!r} — fail closed"
        )
    try:
        enum_cls(value)
    except ValueError as exc:
        raise DeliveryExportError(
            f"Malformed scientific status {field!r}={value!r} — fail closed"
        ) from exc


def assert_scientific_statuses(phase2_raw: dict[str, Any], phase3_raw: dict[str, Any]) -> None:
    """Require decoder, channel verdict, and rate_status in raw JSON (no silent defaults)."""
    if is_v1_schema(phase2_raw):
        _require_enum(phase2_raw.get("decoder_status"), DecoderStatus, "decoder_status")
    else:
        _require_enum(phase2_raw.get("selected_status"), DecoderStatus, "selected_status")

    _require_enum(phase3_raw.get("rate_status"), RateStatus, "rate_status")

    if is_v1_schema(phase3_raw):
        channel = phase3_raw.get("channel_evidence")
        verdict = channel.get("verdict") if isinstance(channel, dict) else None
        _require_enum(verdict, ChannelCompatibilityVerdict, "channel_evidence.verdict")
    else:
        channel = phase3_raw.get("channel_compatibility")
        verdict = channel.get("verdict") if isinstance(channel, dict) else None
        _require_enum(
            verdict, ChannelCompatibilityVerdict, "channel_compatibility.verdict"
        )


def assert_source_integrity(
    phase1: SafePhase1Input,
    phase2: SafePhase2Input,
    phase3: SafePhase3Input,
) -> None:
    """Reject synthetic demo aggregates and mixed source kinds."""
    kinds = {
        phase1.aggregate_source_kind,
        phase2.aggregate_source_kind,
        phase3.aggregate_source_kind,
    }
    kinds.discard(None)

    if SOURCE_KIND_DEMO in kinds:
        raise DeliveryExportError(
            "Rejecting synthetic demo aggregates — reviewed-dashboard export only"
        )
    if len(kinds) > 1:
        raise DeliveryExportError(
            f"Mixed aggregate_source_kind values are not allowed: {sorted(kinds)}"
        )
    if kinds and kinds != {SOURCE_KIND_REVIEWED}:
        raise DeliveryExportError(
            f"Unsupported aggregate_source_kind for reviewed export: {kinds!r}"
        )


def _mark_reviewed(phase: SafePhase1Input | SafePhase2Input | SafePhase3Input) -> Any:
    return phase.model_copy(
        update={
            "schema_version": SCHEMA_VERSION,
            "aggregate_source_kind": SOURCE_KIND_REVIEWED,
        }
    )


def _assert_output_path(path: Path) -> Path:
    p = Path(path)
    if p.exists() and p.is_dir():
        raise DeliveryExportError(
            f"Output must be a JSON file path, not a directory: {p}"
        )
    suffix = p.suffix.lower()
    if suffix != ".json":
        raise DeliveryExportError(f"Output path must be .json, got {suffix!r}")
    return p


def _assert_no_leaks(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False)

    leaks = find_privacy_leaks(text)
    if leaks:
        raise DeliveryExportError(f"Privacy leak in export payload: {leaks}")

    if _PATH_LEAK_RE.search(text):
        raise DeliveryExportError("Export payload contains file-path-like content")

    def _walk(obj: Any, key: str | None = None) -> None:
        if key is not None and _SESSION_ID_KEY_RE.search(key):
            raise DeliveryExportError(f"Forbidden identifying key in export: {key!r}")
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, str(k))
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, key)

    _walk(payload)


def _export_value(
    value: Any,
    source_field: str,
    missing: list[str],
) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        missing.append(source_field)
        return NOT_AVAILABLE
    return value.value if hasattr(value, "value") else value


def _column_non_empty(phase1: SafePhase1Input, name: str) -> int | None:
    column = next((item for item in phase1.columns if item.name == name), None)
    return column.non_empty_count if column is not None else None


def _modality_samples(phase1: SafePhase1Input, modality: str) -> int | None:
    """Return an explicit sample count, or deterministic zero from complete statuses.

    ``samples_present`` is authoritative when supplied. If it is omitted, zero is
    derived only when the safe aggregate accounts for every Phase 1 row using
    statuses that explicitly mean no usable field samples. Malformed,
    non-evaluable, partial, or unknown status coverage remains unavailable.
    """
    item = next(
        (entry for entry in phase1.modality_coverage if entry.modality == modality),
        None,
    )
    if item is None:
        return None

    counts = item.status_counts
    if "samples_present" in counts:
        return counts["samples_present"]

    if any(
        status not in _DETERMINISTIC_NO_SAMPLE_STATUSES or count < 0
        for status, count in counts.items()
        if count
    ):
        return None

    accounted_no_samples = sum(
        counts.get(status, 0) for status in _DETERMINISTIC_NO_SAMPLE_STATUSES
    )
    if accounted_no_samples == phase1.row_count:
        return 0
    return None


def _format_missing_source_warning(missing: list[str]) -> str:
    return "Missing source fields; exported NOT_AVAILABLE: " + ", ".join(missing)


def _write_local_export_log(output_path: Path, warnings: list[str]) -> Path:
    """Write local technical export details without input paths or private data."""
    log_path = output_path.with_suffix(".export.log")
    lines = ["delivery_export completed"]
    lines.extend(f"WARNING: {warning}" for warning in warnings)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def _build_presentation_mapping(
    phase1: SafePhase1Input,
    phase2: SafePhase2Input,
    phase3: SafePhase3Input,
) -> tuple[
    ReviewedOverview,
    ReviewedResearchStatus,
    ReviewedModalityCoverage,
    list[str],
]:
    """Map only explicit safe-report aggregates; missing sources stay unavailable."""
    missing: list[str] = []

    overview = ReviewedOverview(
        sessions=_export_value(phase2.session_count, "phase2.session_count", missing),
        packets=_export_value(phase2.packet_count, "phase2.packet_count", missing),
        malformed_packets=_export_value(
            phase2.malformed_packet_count,
            "phase2.malformed_packet_count",
            missing,
        ),
        gaps=_export_value(
            phase2.total_gap_count,
            "phase2.total_gap_count",
            missing,
        ),
        maximum_gap_ms=_export_value(
            phase2.max_gap_ms,
            "phase2.max_gap_ms",
            missing,
        ),
        upload_completed=_export_value(
            phase1.upload_completion_count,
            "phase1.upload_completion_count",
            missing,
        ),
        upload_pending=_export_value(
            phase1.upload_pending_count,
            "phase1.upload_pending_count",
            missing,
        ),
    )

    # The channel verdict comes only from the validated structured Phase 3
    # channel summary. No deprecated boolean, label conversion, or inference.
    channel_verdict = (
        phase3.channel_evidence.verdict
        if phase3.channel_evidence is not None
        else None
    )
    research_status = ReviewedResearchStatus(
        decoder_status=str(
            _export_value(phase2.decoder_status, "phase2.decoder_status", missing)
        ),
        channel_verdict=str(
            _export_value(
                channel_verdict,
                "phase3.channel_evidence.verdict",
                missing,
            )
        ),
        proprietary_rate=str(
            _export_value(phase3.rate_status, "phase3.rate_status", missing)
        ),
    )

    raw_ppg = _column_non_empty(phase1, "raw_packets_json")
    normalized_ppg = _column_non_empty(phase1, "normalized_fields")
    if normalized_ppg is None:
        normalized_ppg = _modality_samples(phase1, "ppg")

    def modality(modality_name: str) -> Any:
        return _export_value(
            _modality_samples(phase1, modality_name),
            f"phase1.modality_coverage[{modality_name}].samples_present",
            missing,
        )

    modality_coverage = ReviewedModalityCoverage(
        raw_ppg_payload_sessions=_export_value(
            raw_ppg,
            "phase1.columns[raw_packets_json].non_empty_count",
            missing,
        ),
        normalized_ppg_sessions=_export_value(
            normalized_ppg,
            "phase1.columns[normalized_fields].non_empty_count "
            "or modality_coverage[ppg].samples_present",
            missing,
        ),
        accelerometer_sessions=modality("accelerometer"),
        heart_rate_sessions=modality("heart_rate"),
        hrv_sessions=modality("hrv"),
        spo2_sessions=modality("spo2"),
        ecg_sessions=modality("ecg"),
        temperature_sessions=modality("temperature"),
        sleep_sessions=modality("sleep"),
        activity_sessions=modality("activity"),
        blood_pressure_sessions=modality("blood_pressure"),
    )
    warnings = [_format_missing_source_warning(missing)] if missing else []
    return overview, research_status, modality_coverage, warnings


def build_reviewed_dashboard_bundle(
    phase1_path: Path,
    phase2_path: Path,
    phase3_path: Path,
) -> ReviewedDashboardBundle:
    """Load three explicit safe reports and build an allowlisted bundle."""
    p1_path = assert_safe_json_path(Path(phase1_path))
    p2_path = assert_safe_json_path(Path(phase2_path))
    p3_path = assert_safe_json_path(Path(phase3_path))

    try:
        raw1 = load_raw_safe_json(p1_path)
        raw2 = load_raw_safe_json(p2_path)
        raw3 = load_raw_safe_json(p3_path)
    except (SafeReportLoadError, OSError, json.JSONDecodeError, ValueError) as exc:
        raise DeliveryExportError(str(exc)) from exc

    try:
        phase1 = _load_phase1(p1_path)
        phase2 = _load_phase2(p2_path)
        phase3 = _load_phase3(p3_path)
    except (SafeReportLoadError, DeliveryExportError):
        raise
    except Exception as exc:
        raise DeliveryExportError(f"Failed to load safe reports: {exc}") from exc

    assert_source_integrity(phase1, phase2, phase3)

    phase1 = _mark_reviewed(phase1)
    phase2 = _mark_reviewed(phase2)
    phase3 = _mark_reviewed(phase3)

    overview, research_status, modality_coverage, warnings = (
        _build_presentation_mapping(phase1, phase2, phase3)
    )

    try:
        return ReviewedDashboardBundle(
            schema_version=SCHEMA_VERSION,
            source_label=SOURCE_LABEL,
            aggregate_source_kind=SOURCE_KIND_REVIEWED,
            overview=overview,
            research_status=research_status,
            modality_coverage=modality_coverage,
            export_warnings=warnings,
            phase1=phase1,
            phase2=phase2,
            phase3=phase3,
        )
    except ValidationError as exc:
        raise DeliveryExportError(f"Invalid reviewed dashboard bundle: {exc}") from exc


def export_reviewed_dashboard_bundle(
    phase1_path: Path,
    phase2_path: Path,
    phase3_path: Path,
    output_path: Path,
) -> Path:
    """Write one allowlisted ``dashboard.safe.v1`` JSON; return the output path."""
    out = _assert_output_path(Path(output_path))
    bundle = build_reviewed_dashboard_bundle(phase1_path, phase2_path, phase3_path)
    payload = bundle.model_dump(mode="json")
    _assert_no_leaks(payload)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_local_export_log(out, bundle.export_warnings)
    for warning in bundle.export_warnings:
        logger.warning("%s", warning)
    return out

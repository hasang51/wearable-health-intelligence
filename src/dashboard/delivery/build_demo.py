"""Build demo and reviewed safe aggregate JSON (no science)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.dashboard import SCHEMA_VERSION
from src.dashboard.delivery import facts as F

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "demo"
REVIEWED_DIR = REPO_ROOT / "reports" / "delivery" / "reviewed_safe"


def _base_phase1(*, source_kind: str, overrides: dict[str, Any] | None = None) -> dict:
    data = {
        "schema_version": SCHEMA_VERSION,
        "aggregate_source_kind": source_kind,
        "row_count": F.SESSIONS,
        "column_count": len(F.COLUMNS),
        "modality_coverage": F.MODALITY_COVERAGE,
        "inconsistency_counts": F.INCONSISTENCY_COUNTS,
        "columns": F.COLUMNS,
        "upload_completion_count": F.UPLOAD_COMPLETION_COUNT,
        "upload_pending_count": F.UPLOAD_PENDING_COUNT,
        "privacy_posture": list(F.PRIVACY_POSTURE),
    }
    if overrides:
        data.update(overrides)
    return data


def _base_phase2(*, source_kind: str, overrides: dict[str, Any] | None = None) -> dict:
    data = {
        "schema_version": SCHEMA_VERSION,
        "aggregate_source_kind": source_kind,
        "session_count": F.SESSIONS,
        "packet_count": F.PACKETS,
        "malformed_packet_count": F.MALFORMED_PACKETS,
        "candidate_count": F.DECODER_CANDIDATE_COUNT,
        "nominal_payload_length": F.NOMINAL_PAYLOAD_LENGTH,
        "datatype_mode": F.DATATYPE_MODE,
        "decoder_status": F.DECODER_STATUS,
        "top_decoder_family": F.TOP_DECODER_FAMILY,
        "total_gap_count": F.GAPS_GT_THRESHOLD,
        "max_gap_ms": float(F.MAX_GAP_MS),
        "gap_threshold_ms": F.GAP_THRESHOLD_MS,
        "packets_by_session": F.PACKETS_BY_SESSION,
        "packet_interval_summary": F.PACKET_INTERVAL_SUMMARY,
        "privacy_posture": list(F.PRIVACY_POSTURE),
    }
    if overrides:
        data.update(overrides)
    return data


def _base_phase3(*, source_kind: str, overrides: dict[str, Any] | None = None) -> dict:
    data = {
        "schema_version": SCHEMA_VERSION,
        "aggregate_source_kind": source_kind,
        "top_layout": F.TOP_LAYOUT,
        "top_hypothesis": F.TOP_HYPOTHESIS,
        "hypothesis_scores": F.HYPOTHESIS_SCORES,
        "quality_label_counts": F.QUALITY_LABEL_COUNTS,
        "continuous_segment_count": F.CONTINUOUS_SEGMENTS,
        "channel_segment_count": F.CHANNEL_SEGMENTS,
        "periodicity": {
            "plausible": F.PERIODICITY_PLAUSIBLE,
            "weak": F.PERIODICITY_WEAK,
            "non_evaluable": F.PERIODICITY_NON_EVALUABLE,
        },
        "candidate_mean_periodic_frequency_hz": F.CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ,
        "candidate_frequency_note": (
            "Mean candidate periodic frequency — not interpreted as a vital sign; "
            "research-only signal plausibility"
        ),
        "channel_evidence": {
            "verdict": F.CHANNEL_VERDICT,
            "frequency_agreeing": F.FREQ_AGREEING,
            "frequency_evaluable": F.FREQ_EVALUABLE,
            "frequency_agreement_fraction": F.FREQ_AGREEING / F.FREQ_EVALUABLE,
            "median_zero_lag_correlation": F.MEDIAN_ZERO_LAG_CORR,
            "median_max_lagged_correlation": F.MEDIAN_MAX_LAGGED_CORR,
            "median_coherence": F.MEDIAN_COHERENCE,
            "median_best_lag_samples": F.MEDIAN_BEST_LAG_SAMPLES,
            "passed_criteria": [],
            "failed_criteria": F.CHANNEL_FAILED_CRITERIA,
            "thresholds_used": F.CHANNEL_THRESHOLDS,
        },
        "rate_status": F.RATE_STATUS,
        "failed_gates": F.FAILED_GATES,
        "passed_gates": F.PASSED_GATES,
        "benchmark_ran": F.BENCHMARK_RAN,
        "score_margin_note": F.SCORE_MARGIN_NOTE,
        "privacy_posture": list(F.PRIVACY_POSTURE),
    }
    if overrides:
        data.update(overrides)
    return data


def build_reviewed_payloads() -> tuple[dict, dict, dict]:
    kind = F.SOURCE_KIND_REVIEWED
    return (
        _base_phase1(source_kind=kind),
        _base_phase2(source_kind=kind),
        _base_phase3(source_kind=kind),
    )


def build_demo_payloads() -> tuple[dict, dict, dict]:
    """Synthetic demo — intentionally different upload/session values for integrity tests."""
    kind = F.SOURCE_KIND_DEMO
    # Synthetic session bars for development charts only (never used in reviewed mode).
    session_packets = [820, 815, 812, 810, 818, 822, 805, 830, 814, 815]
    session_gaps = [3, 2, 4, 1, 3, 2, 5, 2, 3, 2]
    packets_by_session = [
        {
            "session_ordinal": i + 1,
            "packet_count": session_packets[i],
            "gap_count": session_gaps[i],
        }
        for i in range(10)
    ]
    demo_p1 = _base_phase1(
        source_kind=kind,
        overrides={
            "upload_completion_count": 8,
            "upload_pending_count": 2,
            "inconsistency_counts": {
                "pending_upload": 2,
                "empty_physiology": 1,
                "chunk_mismatch": 0,
                "invalid_json": 0,
                "duration_not_evaluable": 1,
                "duration_mismatch": 0,
            },
            "columns": [
                {
                    "name": "session_meta",
                    "kind": "ordinary",
                    "null_or_empty_count": 0,
                    "non_empty_count": 10,
                },
                {
                    "name": "raw_packets_json",
                    "kind": "json_like",
                    "null_or_empty_count": 0,
                    "non_empty_count": 10,
                },
                {
                    "name": "normalized_fields",
                    "kind": "ordinary",
                    "null_or_empty_count": 3,
                    "non_empty_count": 7,
                },
            ],
            "modality_coverage": [
                {
                    "modality": "ppg",
                    "status_counts": {
                        "column_absent": 0,
                        "payload_empty": 0,
                        "payload_malformed": 0,
                        "structure_present_no_samples": 0,
                        "samples_present": 10,
                        "not_evaluable": 0,
                    },
                },
                {
                    "modality": "accelerometer",
                    "status_counts": {
                        "column_absent": 8,
                        "payload_empty": 1,
                        "payload_malformed": 0,
                        "structure_present_no_samples": 1,
                        "samples_present": 0,
                        "not_evaluable": 0,
                    },
                },
            ],
        },
    )
    demo_p2 = _base_phase2(
        source_kind=kind,
        overrides={
            "packets_by_session": packets_by_session,
            "packet_interval_summary": {
                "delta_min_ms": 48.0,
                "delta_median_ms": 52.0,
                "delta_p95_ms": 120.0,
            },
        },
    )
    demo_p3 = _base_phase3(source_kind=kind)
    return demo_p1, demo_p2, demo_p3


def _write_triple(dest: Path, payloads: tuple[dict, dict, dict]) -> tuple[Path, Path, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = (
        dest / "safe_phase1.json",
        dest / "safe_phase2.json",
        dest / "safe_phase3.json",
    )
    for path, payload in zip(paths, payloads):
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return paths


def write_demo(out_dir: Path | None = None) -> tuple[Path, Path, Path]:
    return _write_triple(out_dir or DEMO_DIR, build_demo_payloads())


def write_reviewed(out_dir: Path | None = None) -> tuple[Path, Path, Path]:
    return _write_triple(out_dir or REVIEWED_DIR, build_reviewed_payloads())


def write_all() -> None:
    for p in write_demo():
        print(p)
    for p in write_reviewed():
        print(p)


if __name__ == "__main__":
    write_all()

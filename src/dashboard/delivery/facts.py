"""Canonical reviewed project-result aggregates for delivery docs and reviewed mode.

Values are manually curated from reviewed safe Phase 1–3 reports.
They are not recomputed. No identifiers, exact timestamps, or raw samples.

Demo mode uses separate synthetic overrides in build_demo.py and must never
be merged into project-results mode.
"""

from __future__ import annotations

from typing import Any

# --- Headline corpus facts (reviewed) ---
SESSIONS = 10
PACKETS = 8161
MALFORMED_PACKETS = 0
GAPS_GT_THRESHOLD = 27
MAX_GAP_MS = 47111
GAP_THRESHOLD_MS = 1500
NOMINAL_PAYLOAD_LENGTH = 66
DATATYPE_MODE = "119"
DECODER_CANDIDATE_COUNT = 192

DECODER_STATUS = "UNVERIFIED"
TOP_DECODER_FAMILY = "int24 | CAB | C2"
TOP_LAYOUT = "INTERLEAVED_PACKET_LOCAL"
TOP_HYPOTHESIS = "H_2block_meta_per_ch:last_of_block"

HYPOTHESIS_SCORES: list[dict[str, Any]] = [
    {
        "hypothesis_id": "H_2block_meta_per_ch:last_of_block",
        "band_ratio": 0.1260,
        "usable_fraction": 0.473,
        "frequency_cv": 0.155,
    },
    {
        "hypothesis_id": "H_2x33",
        "band_ratio": 0.1148,
        "usable_fraction": 0.243,
        "frequency_cv": 0.751,
    },
    {
        "hypothesis_id": "H_2x32_plus_2global",
        "band_ratio": 0.1139,
        "usable_fraction": 0.230,
        "frequency_cv": 0.746,
    },
    {
        "hypothesis_id": "H_3x22",
        "band_ratio": 0.0804,
        "usable_fraction": 0.054,
        "frequency_cv": 0.862,
    },
]

CONTINUOUS_SEGMENTS = 37
CHANNEL_SEGMENTS = 74
PERIODICITY_PLAUSIBLE = 35
PERIODICITY_WEAK = 17
PERIODICITY_NON_EVALUABLE = 22
CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ = 1.95

QUALITY_LABEL_COUNTS: dict[str, int] = {
    "unusable": 272,
    "poor": 16696,
    "uncertain": 7160,
    "plausible_candidate_signal": 1108,
}

FREQ_AGREEING = 18
FREQ_EVALUABLE = 37
MEDIAN_ZERO_LAG_CORR = -0.008
MEDIAN_MAX_LAGGED_CORR = 0.205
MEDIAN_COHERENCE = 0.075
MEDIAN_BEST_LAG_SAMPLES = 12.0
CHANNEL_VERDICT = "INSUFFICIENT_CHANNEL_AGREEMENT"

CHANNEL_THRESHOLDS: dict[str, float | int] = {
    "min_evaluable_pairs": 10,
    "min_evaluable_fraction": 0.60,
    "compatible_min_frequency_agreement": 0.70,
    "compatible_min_median_lagged_correlation": 0.30,
    "compatible_min_median_coherence": 0.20,
    "partial_min_frequency_agreement": 0.50,
    "partial_min_median_lagged_correlation": 0.25,
    "partial_min_median_coherence": 0.10,
}

CHANNEL_FAILED_CRITERIA: list[str] = [
    "frequency_agreement_below_partial",
    "median_lagged_correlation_below_partial",
    "median_coherence_below_partial",
]

RATE_STATUS = "NOT_COMPUTED"
FAILED_GATES: list[str] = [
    "decoder_status_insufficient",
    "public_median_abs_hr_error_gate",
    "public_coverage_gate",
    "rate_estimates_unavailable",
    "channel_agreement_insufficient",
]
PASSED_GATES: list[str] = []
BENCHMARK_RAN = False

# Reviewed safe reports do not include authentic per-session packet bars.
# Do not invent session-level values for project-results mode.
PACKETS_BY_SESSION: list[dict[str, int]] = []

# Typical packet interval from reviewed safe aggregates (~995 ms).
PACKET_INTERVAL_SUMMARY: dict[str, float] = {
    "delta_min_ms": 980.0,
    "delta_median_ms": 995.0,
    "delta_p95_ms": 1020.0,
}

# Reviewed upload lifecycle: raw packets present, uploads incomplete.
UPLOAD_PENDING_COUNT = 10
UPLOAD_COMPLETION_COUNT = 0
INCONSISTENCY_COUNTS: dict[str, int] = {
    "pending_upload": 10,
    "empty_physiology": 0,
    "chunk_mismatch": 0,
    "invalid_json": 0,
    "duration_not_evaluable": 0,
    "duration_mismatch": 0,
}

MODALITY_COVERAGE: list[dict[str, Any]] = [
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
            "column_absent": 10,
            "payload_empty": 0,
            "payload_malformed": 0,
            "structure_present_no_samples": 0,
            "samples_present": 0,
            "not_evaluable": 0,
        },
    },
    {
        "modality": "heart_rate",
        "status_counts": {
            "column_absent": 10,
            "payload_empty": 0,
            "payload_malformed": 0,
            "structure_present_no_samples": 0,
            "samples_present": 0,
            "not_evaluable": 0,
        },
    },
    {
        "modality": "hrv",
        "status_counts": {
            "column_absent": 10,
            "payload_empty": 0,
            "payload_malformed": 0,
            "structure_present_no_samples": 0,
            "samples_present": 0,
            "not_evaluable": 0,
        },
    },
    {
        "modality": "spo2",
        "status_counts": {
            "column_absent": 10,
            "payload_empty": 0,
            "payload_malformed": 0,
            "structure_present_no_samples": 0,
            "samples_present": 0,
            "not_evaluable": 0,
        },
    },
]

COLUMNS: list[dict[str, Any]] = [
    {"name": "session_meta", "kind": "ordinary", "null_or_empty_count": 0, "non_empty_count": 10},
    {
        "name": "raw_packets_json",
        "kind": "json_like",
        "null_or_empty_count": 0,
        "non_empty_count": 10,
    },
    {
        "name": "normalized_fields",
        "kind": "ordinary",
        "null_or_empty_count": 10,
        "non_empty_count": 0,
    },
]

SCORE_MARGIN_NOTE = (
    "Best research candidate leads on band_ratio (0.1260 vs 0.1148) and "
    "usable_fraction (0.473 vs 0.243), with lower frequency_cv (0.155). "
    "Band-ratio margin is 0.0112. Decoder remains UNVERIFIED — best research "
    "candidate, not physiological PPG."
)

PRIVACY_POSTURE = [
    "no_raw_values",
    "no_identifiers",
    "no_exact_timestamps",
    "input_path_redacted",
    "no_physiological_claims",
    "candidate_not_validated_ppg",
    "no_default_vitals",
    "benchmark_isolated",
    "no_per_pair_channel_values",
    "dashboard_safe_aggregates_only",
]

SOURCE_KIND_REVIEWED = "reviewed_project"
SOURCE_KIND_DEMO = "synthetic_demo"


def quality_total() -> int:
    return sum(QUALITY_LABEL_COUNTS.values())

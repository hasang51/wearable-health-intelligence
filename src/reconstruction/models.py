"""Pydantic contracts for Phase 3 private and safe reports."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityLabel(str, Enum):
    UNUSABLE = "unusable"
    POOR = "poor"
    UNCERTAIN = "uncertain"
    PLAUSIBLE_CANDIDATE_SIGNAL = "plausible_candidate_signal"


class RateStatus(str, Enum):
    COMPUTED = "COMPUTED"
    NOT_COMPUTED = "NOT_COMPUTED"
    METHOD_DISAGREEMENT = "METHOD_DISAGREEMENT"


class ChannelCompatibilityVerdict(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    PARTIALLY_COMPATIBLE = "PARTIALLY_COMPATIBLE"
    INSUFFICIENT_CHANNEL_AGREEMENT = "INSUFFICIENT_CHANNEL_AGREEMENT"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ChannelCompatibilitySummary(BaseModel):
    """Safe aggregate channel-agreement evidence (no per-pair or identifying fields)."""

    verdict: ChannelCompatibilityVerdict = ChannelCompatibilityVerdict.NOT_EVALUABLE
    total_pairs: int = 0
    evaluable_pairs: int = 0
    evaluable_fraction: float = 0.0
    frequency_evaluable_pairs: int = 0
    frequency_agreeing_pairs: int = 0
    frequency_agreement_fraction: float | None = None
    median_abs_zero_lag_correlation: float | None = None
    median_max_abs_lagged_correlation: float | None = None
    median_coherence: float | None = None
    median_best_lag_samples: float | None = None
    best_lag_iqr_samples: float | None = None
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    non_evaluable_reasons: dict[str, int] = Field(default_factory=dict)
    thresholds_used: dict[str, float | int] = Field(default_factory=dict)


class ReconstructionMeta(BaseModel):
    session_count: int
    packet_count: int
    generated_at: str
    tool_version: str
    expected_payload_length: int = 66
    signedness: str = "int24"
    byte_order: str = "CAB"
    gap_rule: str = "max(1.5*median_packet_interval, 1500ms)"
    vendor_documented: bool = False


class LayoutHypothesisDoc(BaseModel):
    layout_id: str
    rule: str
    phase2_equivalent: str | None = None
    algebraic_identity_notes: dict[str, bool] = Field(default_factory=dict)


class LayoutHypothesesReport(BaseModel):
    meta: ReconstructionMeta
    layouts: list[LayoutHypothesisDoc]
    payload_length: int = 66
    evaluated_channel_counts: list[int] = Field(default_factory=list)


class PositionMetadataRecord(BaseModel):
    position: int
    features: dict[str, float] = Field(default_factory=dict)
    metadata_likelihood: float = 0.0
    decision: str = "keep"  # keep | propose_exclude
    reasons: list[str] = Field(default_factory=list)
    hypothesis_id: str | None = None
    score: float = 0.0


class MetadataPositionReport(BaseModel):
    meta: ReconstructionMeta
    positions: list[PositionMetadataRecord]
    proposed_exclusions: list[PositionMetadataRecord] = Field(default_factory=list)
    note: str = "No position is silently removed; exclusions require explicit hypothesis."


class SpectralPlausibilityReport(BaseModel):
    meta: ReconstructionMeta
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class ChannelRelationshipReport(BaseModel):
    meta: ReconstructionMeta
    pairs: list[dict[str, Any]] = Field(default_factory=list)


class RateGateReport(BaseModel):
    meta: ReconstructionMeta
    rate_status: RateStatus = RateStatus.NOT_COMPUTED
    failed_gates: list[str] = Field(default_factory=list)
    passed_gates: list[str] = Field(default_factory=list)
    candidate_pulse_rate_bpm: float | None = None
    decoder_status: str | None = None
    notes: list[str] = Field(default_factory=list)
    channel_compatibility: ChannelCompatibilitySummary | None = None
    # Deprecated: existential boolean removed; do not resurrect channels_compatible.
    channels_compatible: bool | None = Field(
        default=None,
        description="Deprecated. Removed invalid existential gate; see channel_compatibility.verdict.",
    )


class Phase3Summary(BaseModel):
    meta: ReconstructionMeta
    top_layout: str | None = None
    top_hypothesis: str | None = None
    quality_label_counts: dict[str, int] = Field(default_factory=dict)
    rate_status: RateStatus = RateStatus.NOT_COMPUTED
    channel_compatibility: ChannelCompatibilitySummary | None = None
    layouts_algebraically_identical: dict[str, bool] = Field(default_factory=dict)
    rationale_codes: list[str] = Field(default_factory=list)
    privacy_posture: list[str] = Field(
        default_factory=lambda: [
            "no_raw_values",
            "no_identifiers",
            "no_exact_timestamps",
            "input_path_redacted",
            "no_physiological_claims",
            "candidate_not_validated_ppg",
            "no_default_vitals",
            "benchmark_isolated",
            "no_per_pair_channel_values",
        ]
    )
    extra: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSummary(BaseModel):
    ran: bool = False
    seed: int = 0
    record_count: int = 0
    subject_count: int = 0
    quality_balanced_accuracy: float | None = None
    quality_precision: float | None = None
    quality_recall: float | None = None
    quality_f1: float | None = None
    hr_coverage: float | None = None
    hr_mae: float | None = None
    hr_median_abs_error: float | None = None
    hr_bias: float | None = None
    leakage_prevention: str = "subject_grouped_deterministic_split"
    notes: list[str] = Field(default_factory=list)

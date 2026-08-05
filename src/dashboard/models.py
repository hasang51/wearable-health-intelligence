"""Versioned Phase-4 safe aggregate input contracts (dashboard.safe.v1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.dashboard import SCHEMA_VERSION
from src.forensics.models import DecoderStatus
from src.reconstruction.models import ChannelCompatibilityVerdict, RateStatus

ALLOWED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacketIntervalSummary(StrictModel):
    """Aggregate interval stats only — no exact timestamps."""

    delta_min_ms: float | None = None
    delta_median_ms: float | None = None
    delta_p95_ms: float | None = None


class SessionPacketCount(StrictModel):
    session_ordinal: int
    packet_count: int
    gap_count: int = 0

    @field_validator("session_ordinal")
    @classmethod
    def _ordinal_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("session_ordinal must be >= 1")
        return v


class HypothesisScore(StrictModel):
    hypothesis_id: str
    band_ratio: float
    usable_fraction: float
    frequency_cv: float


class PeriodicityCounts(StrictModel):
    plausible: int = 0
    weak: int = 0
    non_evaluable: int = 0


class ChannelEvidenceAggregate(StrictModel):
    verdict: ChannelCompatibilityVerdict
    frequency_agreeing: int | None = None
    frequency_evaluable: int | None = None
    frequency_agreement_fraction: float | None = None
    median_zero_lag_correlation: float | None = None
    median_max_lagged_correlation: float | None = None
    median_coherence: float | None = None
    median_best_lag_samples: float | None = None
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    thresholds_used: dict[str, float | int] = Field(default_factory=dict)


class ModalityCoverageItem(StrictModel):
    modality: str
    status_counts: dict[str, int] = Field(default_factory=dict)


class ColumnAvailability(StrictModel):
    name: str
    kind: str
    null_or_empty_count: int = 0
    non_empty_count: int = 0


class SafePhase1Input(StrictModel):
    """Enriched Phase-1 safe aggregate for the dashboard."""

    schema_version: str
    row_count: int
    column_count: int
    modality_coverage: list[ModalityCoverageItem] = Field(default_factory=list)
    inconsistency_counts: dict[str, int] = Field(default_factory=dict)
    columns: list[ColumnAvailability] = Field(default_factory=list)
    upload_completion_count: int | None = None
    upload_pending_count: int | None = None
    privacy_posture: list[str] = Field(default_factory=list)
    aggregate_source_kind: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v not in ALLOWED_SCHEMA_VERSIONS:
            raise ValueError(f"Unknown or unsupported schema_version: {v!r}")
        return v


class SafePhase2Input(StrictModel):
    """Enriched Phase-2 safe aggregate for the dashboard."""

    schema_version: str
    session_count: int
    packet_count: int
    malformed_packet_count: int | None = None
    candidate_count: int
    nominal_payload_length: int = 66
    datatype_mode: str | None = None
    decoder_status: DecoderStatus
    top_decoder_family: str | None = None
    total_gap_count: int | None = None
    max_gap_ms: float | None = None
    gap_threshold_ms: int = 1500
    packets_by_session: list[SessionPacketCount] = Field(default_factory=list)
    packet_interval_summary: PacketIntervalSummary | None = None
    privacy_posture: list[str] = Field(default_factory=list)
    aggregate_source_kind: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v not in ALLOWED_SCHEMA_VERSIONS:
            raise ValueError(f"Unknown or unsupported schema_version: {v!r}")
        return v


class SafePhase3Input(StrictModel):
    """Enriched Phase-3 safe aggregate for the dashboard."""

    schema_version: str
    top_layout: str | None = None
    top_hypothesis: str | None = None
    hypothesis_scores: list[HypothesisScore] = Field(default_factory=list)
    quality_label_counts: dict[str, int] = Field(default_factory=dict)
    continuous_segment_count: int | None = None
    channel_segment_count: int | None = None
    periodicity: PeriodicityCounts | None = None
    candidate_mean_periodic_frequency_hz: float | None = None
    candidate_frequency_note: str = (
        "candidate periodic frequency — not heart rate; research-only signal plausibility"
    )
    channel_evidence: ChannelEvidenceAggregate | None = None
    rate_status: RateStatus
    failed_gates: list[str] = Field(default_factory=list)
    passed_gates: list[str] = Field(default_factory=list)
    benchmark_ran: bool = False
    score_margin_note: str | None = None
    privacy_posture: list[str] = Field(default_factory=list)
    aggregate_source_kind: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v not in ALLOWED_SCHEMA_VERSIONS:
            raise ValueError(f"Unknown or unsupported schema_version: {v!r}")
        return v

    @model_validator(mode="after")
    def _require_rate_status(self) -> SafePhase3Input:
        # Explicit presence required — RateStatus enum already rejects missing/invalid.
        if self.rate_status is None:  # pragma: no cover
            raise ValueError("rate_status must not be silently defaulted when absent")
        return self


class DashboardEvidenceBundle(StrictModel):
    """Combined validated view used by UI and delivery docs."""

    phase1: SafePhase1Input
    phase2: SafePhase2Input
    phase3: SafePhase3Input
    source_mode: str = "demo"  # demo | reviewed
    banner_text: str = ""
    reviewed_overview: dict[str, Any] | None = None
    reviewed_research_status: dict[str, str] | None = None
    reviewed_modality_coverage: dict[str, Any] | None = None
    export_warnings: list[str] = Field(default_factory=list)

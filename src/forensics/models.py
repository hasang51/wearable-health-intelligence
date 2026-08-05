"""Pydantic contracts for Phase 2 private and safe forensics reports."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecoderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    PROVISIONALLY_ACCEPTED = "PROVISIONALLY_ACCEPTED"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"


class Signedness(str, Enum):
    UINT24 = "uint24"
    INT24 = "int24"


class LayoutMode(str, Enum):
    PACKET_LOCAL = "packet_local"
    CONTINUOUS = "continuous"


class ForensicsMeta(BaseModel):
    session_count: int
    packet_count: int
    candidate_count: int
    generated_at: str
    tool_version: str
    expected_payload_length: int
    gap_threshold_ms: int
    samples_per_packet: int | None = None
    vendor_documented: bool = False


class PositionStat(BaseModel):
    position: int
    count: int = 0
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    std: float | None = None
    bit_length_min: int | None = None
    bit_length_max: int | None = None
    bit_length_mean: float | None = None
    zero_rate: float = 0.0
    saturation_rate: float = 0.0
    range_width: float | None = None


class BitForensicsSummary(BaseModel):
    value_min: int | None = None
    value_max: int | None = None
    bit_length_histogram: dict[str, int] = Field(default_factory=dict)
    leading_zero_bit_histogram: dict[str, int] = Field(default_factory=dict)
    trailing_zero_bit_histogram: dict[str, int] = Field(default_factory=dict)
    zero_rate: float = 0.0
    constant_payload_rate: float = 0.0
    saturation_rate: float = 0.0
    divisibility_by_power_of_two: dict[str, float] = Field(default_factory=dict)
    byte_frequency_abc: dict[str, list[float]] = Field(default_factory=dict)


class PacketForensicsReport(BaseModel):
    meta: ForensicsMeta
    expected_keys: list[str]
    schema_ok_count: int = 0
    schema_anomaly_count: int = 0
    datatype_histogram: dict[str, int] = Field(default_factory=dict)
    payload_length_histogram: dict[str, int] = Field(default_factory=dict)
    malformed_nested_count: int = 0
    timestamp_regression_count: int = 0
    timestamp_duplicate_count: int = 0
    position_stats: list[PositionStat] = Field(default_factory=list)
    bit_forensics: BitForensicsSummary = Field(default_factory=BitForensicsSummary)
    validation_codes: dict[str, int] = Field(default_factory=dict)


class CandidateMetrics(BaseModel):
    within_packet_deriv_mad: float = 0.0
    boundary_jump_ratio: float = 0.0
    cross_session_consistency: float = 0.0
    position_dependence: float = 0.0
    saturation_rate: float = 0.0
    flatline_rate: float = 0.0
    channel_duplication: float = 0.0
    channel_energy_balance: float = 0.0
    total_cost: float = 0.0


class DecoderCandidate(BaseModel):
    candidate_id: str
    signedness: Signedness
    byte_order: str
    channel_count: int
    layout_mode: LayoutMode
    metrics: CandidateMetrics
    rank: int
    status: DecoderStatus
    rationale_codes: list[str] = Field(default_factory=list)


class DecoderCandidatesReport(BaseModel):
    meta: ForensicsMeta
    weights: dict[str, float]
    thresholds: dict[str, float]
    candidates: list[DecoderCandidate]
    selected_candidate_id: str | None = None
    selected_status: DecoderStatus = DecoderStatus.UNVERIFIED
    selection_notes: list[str] = Field(default_factory=list)


class SessionTimebaseSummary(BaseModel):
    session_ordinal: int
    packet_count: int = 0
    gap_count: int = 0
    regression_count: int = 0
    duplicate_count: int = 0
    duration_inconsistency: bool = False
    delta_min_ms: float | None = None
    delta_median_ms: float | None = None
    delta_p95_ms: float | None = None
    nested_time_delta_corr: float | None = None
    estimated_sample_count: int = 0


class TimebaseReport(BaseModel):
    meta: ForensicsMeta
    sessions: list[SessionTimebaseSummary] = Field(default_factory=list)
    gap_class_histogram: dict[str, int] = Field(default_factory=dict)
    total_gap_count: int = 0
    total_regression_count: int = 0
    total_duplicate_count: int = 0
    duration_inconsistency_count: int = 0
    samples_per_packet_hypothesis: int | None = None
    estimated_sample_timestamp_enabled: bool = False
    total_estimated_samples: int = 0
    implied_rate_estimate_hz_unverified: float | None = None
    implied_rate_status: str = "unverified"


class PacketSpecSummary(BaseModel):
    meta: ForensicsMeta
    expected_keys: list[str]
    nominal_payload_length: int
    datatype_mode: str | None = None
    schema_anomaly_rate: float = 0.0
    malformed_nested_rate: float = 0.0
    gap_rate_sessions: float = 0.0
    selected_status: DecoderStatus = DecoderStatus.UNVERIFIED
    selected_candidate_id: str | None = None
    privacy_posture: list[str] = Field(
        default_factory=lambda: [
            "no_raw_values",
            "no_identifiers",
            "no_exact_timestamps",
            "input_path_redacted",
            "no_physiological_claims",
        ]
    )
    extra: dict[str, Any] = Field(default_factory=dict)

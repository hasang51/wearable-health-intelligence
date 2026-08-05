"""Allowlisted reviewed-dashboard bundle contract."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import Field, field_validator, model_validator

from src.dashboard import SCHEMA_VERSION
from src.dashboard.delivery.facts import SOURCE_KIND_REVIEWED
from src.dashboard.models import (
    ALLOWED_SCHEMA_VERSIONS,
    SafePhase1Input,
    SafePhase2Input,
    SafePhase3Input,
    StrictModel,
)
from src.delivery_export import SOURCE_LABEL

ReviewedValue: TypeAlias = int | float | str


class ReviewedOverview(StrictModel):
    sessions: ReviewedValue
    packets: ReviewedValue
    malformed_packets: ReviewedValue
    gaps: ReviewedValue
    maximum_gap_ms: ReviewedValue
    upload_completed: ReviewedValue
    upload_pending: ReviewedValue


class ReviewedResearchStatus(StrictModel):
    decoder_status: str
    channel_verdict: str
    proprietary_rate: str


class ReviewedModalityCoverage(StrictModel):
    raw_ppg_payload_sessions: ReviewedValue
    normalized_ppg_sessions: ReviewedValue
    accelerometer_sessions: ReviewedValue
    heart_rate_sessions: ReviewedValue
    hrv_sessions: ReviewedValue
    spo2_sessions: ReviewedValue
    ecg_sessions: ReviewedValue
    temperature_sessions: ReviewedValue
    sleep_sessions: ReviewedValue
    activity_sessions: ReviewedValue
    blood_pressure_sessions: ReviewedValue


class ReviewedDashboardBundle(StrictModel):
    """Single allowlisted ``dashboard.safe.v1`` export for reviewed delivery."""

    schema_version: str
    source_label: str
    aggregate_source_kind: str
    overview: ReviewedOverview
    research_status: ReviewedResearchStatus
    modality_coverage: ReviewedModalityCoverage
    export_warnings: list[str] = Field(default_factory=list)
    phase1: SafePhase1Input
    phase2: SafePhase2Input
    phase3: SafePhase3Input

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v not in ALLOWED_SCHEMA_VERSIONS:
            raise ValueError(f"Unknown or unsupported schema_version: {v!r}")
        return v

    @field_validator("source_label")
    @classmethod
    def _check_label(cls, v: str) -> str:
        if v != SOURCE_LABEL:
            raise ValueError(f"source_label must be exactly {SOURCE_LABEL!r}")
        return v

    @field_validator("aggregate_source_kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v != SOURCE_KIND_REVIEWED:
            raise ValueError(
                f"aggregate_source_kind must be {SOURCE_KIND_REVIEWED!r}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _phases_are_reviewed_v1(self) -> ReviewedDashboardBundle:
        for name, phase in (
            ("phase1", self.phase1),
            ("phase2", self.phase2),
            ("phase3", self.phase3),
        ):
            if phase.schema_version != SCHEMA_VERSION:
                raise ValueError(f"{name}.schema_version must be {SCHEMA_VERSION!r}")
            if phase.aggregate_source_kind != SOURCE_KIND_REVIEWED:
                raise ValueError(
                    f"{name}.aggregate_source_kind must be {SOURCE_KIND_REVIEWED!r}"
                )
        return self

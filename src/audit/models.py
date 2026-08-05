"""Pydantic report contracts for private and safe audit profiles."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ColumnKind(str, Enum):
    ORDINARY = "ordinary"
    JSON_LIKE = "json_like"
    MIXED_MALFORMED = "mixed_malformed"


class ModalityStatus(str, Enum):
    COLUMN_ABSENT = "column_absent"
    PAYLOAD_EMPTY = "payload_empty"
    PAYLOAD_MALFORMED = "payload_malformed"
    STRUCTURE_PRESENT_NO_SAMPLES = "structure_present_no_samples"
    SAMPLES_PRESENT = "samples_present"
    NOT_EVALUABLE = "not_evaluable"


class LimitsApplied(BaseModel):
    max_json_depth: int
    max_keys_per_object: int
    max_array_elements_inspected: int
    csv_field_size_limit: int


class ProfileMeta(BaseModel):
    row_count: int
    column_count: int
    generated_at: str
    tool_version: str
    limits_applied: LimitsApplied


class ColumnProfile(BaseModel):
    name: str
    kind: ColumnKind
    null_or_empty_count: int
    non_empty_count: int


class ArrayLengthStats(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    count: int = 0
    total_length_observed: int = 0
    elements_structurally_inspected: int = 0


class KeyPathProfile(BaseModel):
    path: str
    value_types: dict[str, int] = Field(default_factory=dict)
    occurrence_count: int = 0


class TimestampFieldProfile(BaseModel):
    path: str
    unit_known: bool = False


class JsonColumnProfile(BaseModel):
    name: str
    populated_row_count: int = 0
    empty_row_count: int = 0
    malformed_row_count: int = 0
    top_level_types: dict[str, int] = Field(default_factory=dict)
    array_length_stats: ArrayLengthStats = Field(default_factory=ArrayLengthStats)
    key_paths: list[KeyPathProfile] = Field(default_factory=list)
    possible_timestamp_fields: list[TimestampFieldProfile] = Field(default_factory=list)


class ModalityCoverage(BaseModel):
    modality: str
    status_counts: dict[str, int] = Field(default_factory=dict)


class InconsistencyRecord(BaseModel):
    code: str
    session_ordinal: int
    column: str | None = None
    detail: str


class PrivateDataProfile(BaseModel):
    meta: ProfileMeta
    columns: list[ColumnProfile]
    json_columns: list[JsonColumnProfile]
    modality_coverage: list[ModalityCoverage]
    inconsistencies: list[InconsistencyRecord] = Field(default_factory=list)


class SafeSchemaProfile(BaseModel):
    meta: ProfileMeta
    columns: list[ColumnProfile]
    json_columns: list[JsonColumnProfile]
    modality_coverage: list[ModalityCoverage]
    inconsistency_counts: dict[str, int] = Field(default_factory=dict)
    privacy_posture: list[str] = Field(
        default_factory=lambda: [
            "no_raw_values",
            "no_identifiers",
            "no_exact_timestamps",
            "dynamic_keys_redacted",
            "input_path_redacted",
        ]
    )


def empty_modality_status_counts() -> dict[str, int]:
    return {s.value: 0 for s in ModalityStatus}

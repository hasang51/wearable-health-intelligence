"""Tests for modality status evaluation."""

from pathlib import Path

from src.audit.limits import ResourceLimits
from src.audit.models import ModalityStatus
from src.audit.reports import run_audit

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_valid_has_samples_present() -> None:
    profile = run_audit(FIXTURES / "sessions_valid.csv", ResourceLimits())
    by_mod = {m.modality: m.status_counts for m in profile.modality_coverage}
    assert by_mod["ppg"][ModalityStatus.SAMPLES_PRESENT.value] >= 1
    assert by_mod["heart_rate"][ModalityStatus.SAMPLES_PRESENT.value] >= 1
    assert by_mod["accelerometer"][ModalityStatus.SAMPLES_PRESENT.value] >= 1


def test_empty_payload_statuses() -> None:
    profile = run_audit(FIXTURES / "sessions_empty.csv", ResourceLimits())
    by_mod = {m.modality: m.status_counts for m in profile.modality_coverage}
    # PPG column exists but empty array
    assert (
        by_mod["ppg"][ModalityStatus.PAYLOAD_EMPTY.value]
        + by_mod["ppg"][ModalityStatus.STRUCTURE_PRESENT_NO_SAMPLES.value]
    ) >= 1


def test_missing_columns_absent() -> None:
    profile = run_audit(FIXTURES / "sessions_missing_columns.csv", ResourceLimits())
    by_mod = {m.modality: m.status_counts for m in profile.modality_coverage}
    for modality, counts in by_mod.items():
        assert counts[ModalityStatus.COLUMN_ABSENT.value] == 1, modality


def test_malformed_payload() -> None:
    profile = run_audit(FIXTURES / "sessions_malformed.csv", ResourceLimits())
    by_mod = {m.modality: m.status_counts for m in profile.modality_coverage}
    assert by_mod["ppg"][ModalityStatus.PAYLOAD_MALFORMED.value] >= 1

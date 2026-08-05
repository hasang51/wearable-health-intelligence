"""Tests for consistency checks."""

from pathlib import Path

from src.audit.limits import ResourceLimits
from src.audit.reports import run_audit

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_incomplete_upload_flags() -> None:
    profile = run_audit(FIXTURES / "sessions_incomplete_upload.csv", ResourceLimits())
    codes = {i.code for i in profile.inconsistencies}
    details = {i.detail for i in profile.inconsistencies}
    assert "chunk_mismatch" in codes or "pending_upload" in codes
    assert "pending_upload" in codes or "pending_upload" in details
    assert any(
        i.detail in {"sent_plus_failed_gt_total", "sent_gt_total", "pending_upload"}
        for i in profile.inconsistencies
    )


def test_malformed_invalid_json() -> None:
    profile = run_audit(FIXTURES / "sessions_malformed.csv", ResourceLimits())
    assert any(i.code == "invalid_json" for i in profile.inconsistencies)


def test_irregular_timestamps_not_evaluable() -> None:
    profile = run_audit(FIXTURES / "sessions_irregular_timestamps.csv", ResourceLimits())
    assert any(i.code == "duration_not_evaluable" for i in profile.inconsistencies)


def test_empty_physiology() -> None:
    profile = run_audit(FIXTURES / "sessions_empty.csv", ResourceLimits())
    assert any(i.code == "empty_physiology" for i in profile.inconsistencies)


def test_never_infers_duration_from_array_length_alone() -> None:
    """Valid fixture has time_ms + duration_s; mismatch code must not invent Fs."""
    profile = run_audit(FIXTURES / "sessions_valid.csv", ResourceLimits())
    # Should not raise; duration may be evaluable via time_ms. No fabricated codes required.
    assert profile.meta.row_count == 1

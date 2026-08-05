"""Tests for packet timebase reconstruction."""

from __future__ import annotations

from pathlib import Path

from src.forensics.extract import extract_session
from src.forensics.stream import stream_sessions
from src.forensics.timebase import analyze_session_timebase, build_timebase_report
from src.forensics.models import ForensicsMeta

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_timestamp_gaps_regressions_duplicates() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_timestamp_gaps.csv"))
    extracted = extract_session(0, sessions[0][1])
    result = analyze_session_timebase(extracted, gap_threshold_ms=1500.0)
    assert result.summary.gap_count >= 1
    assert result.summary.regression_count >= 1
    assert result.summary.duplicate_count >= 1
    assert result.summary.duration_inconsistency is True


def test_estimated_sample_timestamp_only_when_explicit() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_valid_66.csv"))
    extracted = extract_session(0, sessions[0][1])

    without = analyze_session_timebase(extracted, samples_per_packet=None)
    assert without.estimated_sample_timestamp == []
    assert without.summary.estimated_sample_count == 0

    with_est = analyze_session_timebase(extracted, samples_per_packet=66)
    assert len(with_est.estimated_sample_timestamp) == 5 * 66
    # Attribute name contract
    assert hasattr(with_est, "estimated_sample_timestamp")


def test_timebase_report_aggregates() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_timestamp_gaps.csv"))
    extracted = extract_session(0, sessions[0][1])
    result = analyze_session_timebase(extracted, gap_threshold_ms=1500.0, samples_per_packet=66)
    meta = ForensicsMeta(
        session_count=1,
        packet_count=len(extracted.packets),
        candidate_count=192,
        generated_at="2020-01-01T00:00:00+00:00",
        tool_version="0.2.0",
        expected_payload_length=66,
        gap_threshold_ms=1500,
        samples_per_packet=66,
    )
    report = build_timebase_report(
        [result], meta=meta, gap_threshold_ms=1500.0, samples_per_packet=66
    )
    assert report.total_gap_count >= 1
    assert report.estimated_sample_timestamp_enabled is True
    assert report.implied_rate_status == "unverified"
    # Safe-ish: report model dump should not be required here; ensure field name exists
    assert report.total_estimated_samples == result.summary.estimated_sample_count

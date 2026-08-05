"""Tests for packet extract/validate/stream."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.audit.privacy import SCRUBBER, ScrubbedException
from src.forensics.extract import extract_session
from src.forensics.stream import stream_sessions
from src.forensics.validate import ValidationAccumulator

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extract_valid_payload_length_and_keys() -> None:
    cell = (FIXTURES / "packets_valid_66.csv").read_text(encoding="utf-8")
    # Use stream instead of parsing CSV by hand
    sessions = list(stream_sessions(FIXTURES / "packets_valid_66.csv"))
    assert len(sessions) == 2
    extracted = extract_session(0, sessions[0][1])
    assert not extracted.cell_malformed
    assert len(extracted.packets) == 5
    for pkt in extracted.packets:
        assert pkt.ppg_values is not None
        assert len(pkt.ppg_values) == 66
        assert pkt.data_type == "119"
        assert pkt.schema_ok


def test_extract_stringified_and_array_ppg() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_valid_66.csv"))
    extracted = extract_session(0, sessions[0][1])
    # Odd packets use stringify_ppg in fixture generator
    assert extracted.packets[0].ppg_values is not None
    assert extracted.packets[1].ppg_values is not None
    assert len(extracted.packets[0].ppg_values) == len(extracted.packets[1].ppg_values)


def test_malformed_nested_counted() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_malformed_nested.csv"))
    extracted = extract_session(0, sessions[0][1])
    acc = ValidationAccumulator()
    acc.update_session(extracted)
    assert acc.malformed_nested_count >= 1
    assert any(p.ppg_values is None for p in extracted.packets)


def test_payload_length_mismatch() -> None:
    sessions = list(stream_sessions(FIXTURES / "packets_length_mismatch.csv"))
    extracted = extract_session(0, sessions[0][1])
    acc = ValidationAccumulator(expected_payload_length=66)
    acc.update_session(extracted)
    assert acc.validation_codes.get("payload_length_mismatch", 0) >= 1


def test_stream_rejects_directory(tmp_path: Path) -> None:
    SCRUBBER.register_input_path(tmp_path)
    with pytest.raises(ScrubbedException):
        list(stream_sessions(tmp_path))

"""CLI e2e, scoring, decision, and streaming instrumentation tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.forensics.cli import main
from src.forensics.models import (
    DecoderCandidatesReport,
    DecoderStatus,
    PacketForensicsReport,
    PacketSpecSummary,
    TimebaseReport,
)
from src.forensics.reports import ForensicsConfig, run_forensics
from src.forensics.score import iter_candidate_specs

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_candidate_grid_size() -> None:
    assert len(iter_candidate_specs()) == 192


def test_cli_e2e_valid(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    safe_dir = tmp_path / "safe"
    code = main(
        [
            "--input",
            str(FIXTURES / "packets_valid_66.csv"),
            "--private-dir",
            str(private_dir),
            "--safe-dir",
            str(safe_dir),
            "--allow-private-snippets",
        ]
    )
    assert code == 0
    assert (private_dir / "packet_forensics.json").is_file()
    assert (private_dir / "decoder_candidates.json").is_file()
    assert (private_dir / "timebase_report.json").is_file()
    assert (safe_dir / "packet_spec_summary.json").is_file()
    assert (safe_dir / "decoder_decision.md").is_file()
    assert (private_dir / "plots" / "position_range_bars.png").is_file()
    assert (private_dir / "plots" / "byte_heatmap.png").is_file()
    assert (private_dir / "plots" / "saturation_by_position.png").is_file()
    assert (private_dir / "plots" / "candidate_score_pareto.png").is_file()
    assert (private_dir / "plots" / "top_candidate_boundary.png").is_file()
    assert (private_dir / "plots" / "timebase_gap_hist.png").is_file()

    pf = PacketForensicsReport.model_validate_json(
        (private_dir / "packet_forensics.json").read_text(encoding="utf-8")
    )
    assert pf.meta.packet_count > 0
    assert len(pf.position_stats) == 66

    dc = DecoderCandidatesReport.model_validate_json(
        (private_dir / "decoder_candidates.json").read_text(encoding="utf-8")
    )
    assert len(dc.candidates) == 192
    assert dc.selected_status in set(DecoderStatus)
    # Without vendor docs, must not be ACCEPTED by default on synthetic data
    assert dc.selected_status != DecoderStatus.ACCEPTED

    tb = TimebaseReport.model_validate_json(
        (private_dir / "timebase_report.json").read_text(encoding="utf-8")
    )
    assert tb.estimated_sample_timestamp_enabled is False

    safe = PacketSpecSummary.model_validate_json(
        (safe_dir / "packet_spec_summary.json").read_text(encoding="utf-8")
    )
    assert "no_physiological_claims" in safe.privacy_posture

    md = (safe_dir / "decoder_decision.md").read_text(encoding="utf-8")
    assert "does **not** validate" in md or "does not validate" in md.lower()


def test_cli_with_samples_per_packet(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    safe_dir = tmp_path / "safe"
    code = main(
        [
            "--input",
            str(FIXTURES / "packets_valid_66.csv"),
            "--private-dir",
            str(private_dir),
            "--safe-dir",
            str(safe_dir),
            "--samples-per-packet",
            "66",
        ]
    )
    assert code == 0
    tb = json.loads((private_dir / "timebase_report.json").read_text(encoding="utf-8"))
    assert tb["estimated_sample_timestamp_enabled"] is True
    assert tb["samples_per_packet_hypothesis"] == 66
    assert tb["total_estimated_samples"] > 0
    # Timestamp value arrays must not be dumped into the report JSON
    assert "estimated_sample_timestamp" not in tb
    blob = json.dumps(tb)
    assert "estimated_sample_timestamps" not in blob
    # No large numeric epoch arrays: report only counts/flags
    assert tb.get("sessions", [{}])[0].get("estimated_sample_count", 0) > 0
    assert "estimated_sample_timestamp" not in tb.get("sessions", [{}])[0]


def test_streaming_retains_at_most_one_session_payloads() -> None:
    result = run_forensics(
        FIXTURES / "packets_valid_66.csv",
        ForensicsConfig(),
    )
    # Each session has 5 packets; max retained should be <= packets in one session
    assert result.max_retained_payload_arrays_observed <= 5
    assert result.session_count == 2


def test_cli_rejects_directory(tmp_path: Path) -> None:
    code = main(
        [
            "--input",
            str(tmp_path),
            "--private-dir",
            str(tmp_path / "p"),
            "--safe-dir",
            str(tmp_path / "s"),
        ]
    )
    assert code == 1

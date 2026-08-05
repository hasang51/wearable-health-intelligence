"""Delivery document generation tests."""

from __future__ import annotations

from pathlib import Path

from src.dashboard.delivery import facts as F
from src.dashboard.delivery.generate import (
    architecture_mmd,
    executive_summary,
    generate_delivery,
    _word_count,
)
from src.dashboard.terminology import find_forbidden_phrases


def test_executive_summary_word_limit() -> None:
    text = executive_summary()
    assert _word_count(text) <= 900
    assert str(F.PACKETS) in text
    assert F.DECODER_STATUS in text
    assert F.CHANNEL_VERDICT in text
    assert F.RATE_STATUS in text
    assert find_forbidden_phrases(text) == []


def test_architecture_pipeline() -> None:
    mmd = architecture_mmd()
    for token in (
        "External anonymized data",
        "Secure Audit",
        "Packet Forensics",
        "Candidate Reconstruction",
        "Channel Compatibility",
        "Safe Aggregate Reports",
        "Evidence Dashboard",
        "never feeds",
    ):
        assert token in mmd


def test_generate_writes_all_files(tmp_path: Path) -> None:
    paths = generate_delivery(tmp_path)
    names = {p.name for p in paths}
    assert names == {
        "executive_summary.md",
        "technical_report.md",
        "research_limitations.md",
        "presentation_outline.md",
        "demo_script.md",
        "delivery_checklist.md",
        "architecture.mmd",
    }
    tech = (tmp_path / "technical_report.md").read_text(encoding="utf-8")
    assert "0.1260" in tech or "0.126" in tech
    assert "18/37" in tech or "18" in tech
    assert "phase1.modality_coverage[ecg].samples_present" in tech
    assert "remains `NOT_AVAILABLE`" in tech
    assert find_forbidden_phrases(tech) == []


def test_repo_delivery_artifacts_exist() -> None:
    root = Path("reports/delivery")
    assert (root / "executive_summary.md").is_file()
    assert (root / "architecture.mmd").is_file()
    assert (root / "demo_script.md").is_file()

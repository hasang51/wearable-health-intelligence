"""Adapter tests — v1 + legacy mapping and NOT_AVAILABLE handling."""

from __future__ import annotations

import json
from pathlib import Path

from src.dashboard.adapters import (
    adapt_phase1,
    adapt_phase2,
    adapt_phase3,
    load_evidence_bundle,
    status_card_values,
)
from src.dashboard.config import DEMO_DIR, DashboardConfig
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE
from src.forensics.models import DecoderStatus, ForensicsMeta, PacketSpecSummary
from src.reconstruction.models import Phase3Summary, RateStatus, ReconstructionMeta


def test_demo_bundle_status_cards() -> None:
    from src.dashboard.config import SourceMode

    bundle = load_evidence_bundle(DashboardConfig(source_mode=SourceMode.DEMO))
    cards = status_card_values(bundle)
    assert cards["decoder"] == "UNVERIFIED"
    assert cards["channel"] == "INSUFFICIENT_CHANNEL_AGREEMENT"
    assert cards["rate"] == "NOT_COMPUTED"


def test_legacy_phase2_missing_fields_are_none(tmp_path: Path) -> None:
    meta = ForensicsMeta(
        session_count=2,
        packet_count=100,
        candidate_count=192,
        generated_at="redacted",
        tool_version="0.2.0",
        expected_payload_length=66,
        gap_threshold_ms=1500,
    )
    summary = PacketSpecSummary(
        meta=meta,
        expected_keys=["dataEnd", "dataType", "dicData", "receivedAtMs"],
        nominal_payload_length=66,
        selected_status=DecoderStatus.UNVERIFIED,
    )
    path = tmp_path / "packet_spec_summary.json"
    path.write_text(json.dumps(summary.model_dump(mode="json")), encoding="utf-8")
    adapted = adapt_phase2(path)
    assert adapted.decoder_status == DecoderStatus.UNVERIFIED
    assert adapted.malformed_packet_count is None
    assert adapted.total_gap_count is None
    assert adapted.top_decoder_family is None
    assert adapted.max_gap_ms is None


def test_legacy_phase3_missing_channel_not_available(tmp_path: Path) -> None:
    meta = ReconstructionMeta(
        session_count=2,
        packet_count=100,
        generated_at="redacted",
        tool_version="0.3.0",
    )
    summary = Phase3Summary(
        meta=meta,
        top_layout="INTERLEAVED_PACKET_LOCAL",
        top_hypothesis="H_2x33",
        quality_label_counts={"poor": 10},
        rate_status=RateStatus.NOT_COMPUTED,
        channel_compatibility=None,
    )
    path = tmp_path / "phase3_summary.json"
    path.write_text(json.dumps(summary.model_dump(mode="json")), encoding="utf-8")
    adapted = adapt_phase3(path)
    assert adapted.rate_status == RateStatus.NOT_COMPUTED
    assert adapted.channel_evidence is None
    assert adapted.continuous_segment_count is None

    bundle = DashboardEvidenceBundle(
        phase1=adapt_phase1(DEMO_DIR / "safe_phase1.json"),
        phase2=adapt_phase2(DEMO_DIR / "safe_phase2.json"),
        phase3=adapted,
        source_mode="explicit",
    )
    cards = status_card_values(bundle)
    assert cards["channel"] == NOT_AVAILABLE
    assert cards["rate"] == "NOT_COMPUTED"

"""Transform and status-card consistency tests."""

from __future__ import annotations

from src.dashboard.adapters import load_evidence_bundle, status_card_values
from src.dashboard.config import DashboardConfig, SourceMode
from src.dashboard.delivery import facts as F
from src.dashboard.formatting import fmt_duration_ms, fmt_ratio
from src.dashboard.transforms import (
    assert_counts_consistent,
    hypothesis_score_frame,
    overview_metrics,
    quality_percentages,
    score_margin,
    session_label,
)


def test_quality_percentages_sum_100() -> None:
    pct = quality_percentages(F.QUALITY_LABEL_COUNTS)
    assert abs(sum(pct.values()) - 100.0) < 1e-9
    total = assert_counts_consistent(F.QUALITY_LABEL_COUNTS)
    assert total == F.quality_total()


def test_session_labels() -> None:
    assert session_label(1) == "Session 001"
    assert session_label(10) == "Session 010"


def test_overview_matches_facts_reviewed(reviewed_dashboard_config: DashboardConfig) -> None:
    bundle = load_evidence_bundle(reviewed_dashboard_config)
    m = overview_metrics(bundle)
    assert m["sessions"] == F.SESSIONS
    assert m["packets"] == F.PACKETS
    assert m["malformed_packets"] == F.MALFORMED_PACKETS
    assert int(m["gaps"]) == F.GAPS_GT_THRESHOLD
    assert float(m["max_gap_ms"]) == float(F.MAX_GAP_MS)
    assert int(m["upload_completion"]) == 0
    assert int(m["upload_pending"]) == 10


def test_status_cards_exact(reviewed_dashboard_config: DashboardConfig) -> None:
    cards = status_card_values(load_evidence_bundle(reviewed_dashboard_config))
    assert cards == {
        "decoder": "UNVERIFIED",
        "channel": "INSUFFICIENT_CHANNEL_AGREEMENT",
        "rate": "NOT_COMPUTED",
    }


def test_hypothesis_frame_and_margin(reviewed_dashboard_config: DashboardConfig) -> None:
    bundle = load_evidence_bundle(reviewed_dashboard_config)
    rows = hypothesis_score_frame(bundle.phase3.hypothesis_scores)
    assert len(rows) == 4
    margin = score_margin(bundle.phase3.hypothesis_scores)
    assert margin["top"] == F.TOP_HYPOTHESIS
    assert margin["band_ratio_margin"] == 0.0112
    assert fmt_ratio(0.0112) == "0.0112"


def test_duration_formatting() -> None:
    assert fmt_duration_ms(47111) == "47.1 s"
    assert fmt_duration_ms(995) == "995 ms"


def test_reviewed_has_no_session_bars(reviewed_dashboard_config: DashboardConfig) -> None:
    bundle = load_evidence_bundle(reviewed_dashboard_config)
    assert bundle.phase2.packets_by_session == []


def test_demo_has_synthetic_sessions() -> None:
    bundle = load_evidence_bundle(DashboardConfig(source_mode=SourceMode.DEMO))
    assert len(bundle.phase2.packets_by_session) == 10
    total = sum(s.packet_count for s in bundle.phase2.packets_by_session)
    assert total == F.PACKETS

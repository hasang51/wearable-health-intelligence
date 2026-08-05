"""Dashboard transforms — percentages and chart frames (no science)."""

from __future__ import annotations

from typing import Any

from src.dashboard.models import DashboardEvidenceBundle, HypothesisScore
from src.dashboard.status import NOT_AVAILABLE, is_available, present_or_na


def quality_percentages(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {k: 0.0 for k in counts}
    return {k: (v / total) * 100.0 for k, v in counts.items()}


def assert_counts_consistent(counts: dict[str, int], *, expected_total: int | None = None) -> int:
    total = sum(counts.values())
    if any(v < 0 for v in counts.values()):
        raise ValueError("Negative counts are invalid")
    if expected_total is not None and total != expected_total:
        raise ValueError(f"Count total {total} != expected {expected_total}")
    return total


def session_label(ordinal: int) -> str:
    return f"Session {ordinal:03d}"


def packets_by_session_frame(bundle: DashboardEvidenceBundle) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for s in bundle.phase2.packets_by_session:
        rows.append(
            {
                "session": session_label(s.session_ordinal),
                "packet_count": s.packet_count,
                "gap_count": s.gap_count,
            }
        )
    return rows


def hypothesis_score_frame(scores: list[HypothesisScore]) -> list[dict[str, Any]]:
    return [
        {
            "hypothesis": h.hypothesis_id,
            "band_ratio": h.band_ratio,
            "usable_fraction": h.usable_fraction,
            "frequency_cv": h.frequency_cv,
        }
        for h in scores
    ]


def overview_metrics(bundle: DashboardEvidenceBundle) -> dict[str, Any]:
    if bundle.reviewed_overview is not None:
        reviewed = bundle.reviewed_overview
        return {
            "sessions": reviewed.get("sessions", NOT_AVAILABLE),
            "packets": reviewed.get("packets", NOT_AVAILABLE),
            "malformed_packets": reviewed.get(
                "malformed_packets", NOT_AVAILABLE
            ),
            "gaps": reviewed.get("gaps", NOT_AVAILABLE),
            "max_gap_ms": reviewed.get("maximum_gap_ms", NOT_AVAILABLE),
            "upload_pending": reviewed.get("upload_pending", NOT_AVAILABLE),
            "upload_completion": reviewed.get(
                "upload_completed", NOT_AVAILABLE
            ),
            "modality_coverage": bundle.reviewed_modality_coverage or {},
        }

    p2 = bundle.phase2
    p1 = bundle.phase1
    malformed_display: int | str = (
        NOT_AVAILABLE if p2.malformed_packet_count is None else p2.malformed_packet_count
    )

    upload_pending = present_or_na(p1.upload_pending_count)
    if p1.upload_pending_count is None and "pending_upload" in p1.inconsistency_counts:
        upload_pending = str(p1.inconsistency_counts["pending_upload"])

    upload_complete = present_or_na(p1.upload_completion_count)

    return {
        "sessions": p2.session_count,
        "packets": p2.packet_count,
        "malformed_packets": malformed_display,
        "gaps": present_or_na(p2.total_gap_count),
        "max_gap_ms": present_or_na(p2.max_gap_ms),
        "upload_pending": upload_pending,
        "upload_completion": upload_complete,
        "modality_coverage": [
            {"modality": m.modality, "status_counts": m.status_counts}
            for m in p1.modality_coverage
        ],
    }


def score_margin(scores: list[HypothesisScore]) -> dict[str, Any]:
    if len(scores) < 2:
        return {"top": None, "second": None, "band_ratio_margin": NOT_AVAILABLE}
    ordered = sorted(scores, key=lambda h: h.band_ratio, reverse=True)
    margin = round(ordered[0].band_ratio - ordered[1].band_ratio, 4)
    return {
        "top": ordered[0].hypothesis_id,
        "second": ordered[1].hypothesis_id,
        "band_ratio_margin": margin,
    }


def periodicity_display(bundle: DashboardEvidenceBundle) -> dict[str, Any]:
    per = bundle.phase3.periodicity
    if per is None:
        return {
            "plausible": NOT_AVAILABLE,
            "weak": NOT_AVAILABLE,
            "non_evaluable": NOT_AVAILABLE,
        }
    return {
        "plausible": per.plausible,
        "weak": per.weak,
        "non_evaluable": per.non_evaluable,
    }


def format_optional(value: object | None) -> str:
    if not is_available(value):
        return NOT_AVAILABLE
    return str(value)

"""Packet-level timebase reconstruction from receivedAtMs."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.forensics.extract import SessionExtract
from src.forensics.models import SessionTimebaseSummary, TimebaseReport


def _gap_class(delta_ms: float, gap_threshold_ms: float) -> str:
    if delta_ms < 0:
        return "negative"
    if delta_ms == 0:
        return "zero"
    if delta_ms <= 500:
        return "le_500ms"
    if delta_ms <= gap_threshold_ms:
        return "le_gap_threshold"
    if delta_ms <= 5000:
        return "gap_to_5s"
    if delta_ms <= 30000:
        return "gap_to_30s"
    return "gap_gt_30s"


@dataclass
class SessionTimebaseResult:
    summary: SessionTimebaseSummary
    deltas_ms: list[float] = field(default_factory=list)
    # Private only: estimated timestamps kept out of reports by default.
    estimated_sample_timestamp: list[float] = field(default_factory=list)


def analyze_session_timebase(
    session: SessionExtract,
    *,
    gap_threshold_ms: float = 1500.0,
    samples_per_packet: int | None = None,
) -> SessionTimebaseResult:
    times: list[int] = []
    nested_times: list[float] = []
    for pkt in session.packets:
        if pkt.received_at_ms is not None:
            times.append(pkt.received_at_ms)
        if isinstance(pkt.nested_time, (int, float)) and not isinstance(pkt.nested_time, bool):
            nested_times.append(float(pkt.nested_time))

    gaps = 0
    regressions = 0
    duplicates = 0
    deltas: list[float] = []
    for i in range(1, len(times)):
        d = float(times[i] - times[i - 1])
        deltas.append(d)
        if d < 0:
            regressions += 1
        elif d == 0:
            duplicates += 1
        if d > gap_threshold_ms:
            gaps += 1

    duration_inconsistency = False
    if len(times) >= 2:
        span = float(times[-1] - times[0])
        positive_sum = float(sum(d for d in deltas if d > 0))
        # With regressions/duplicates, sum of positive deltas can diverge from span.
        if abs(positive_sum - span) > 1.0:
            duration_inconsistency = True
        # Also flag if any non-positive delta exists (span vs path disagreement).
        if regressions or duplicates:
            if abs(sum(deltas) - span) > 1.0:
                duration_inconsistency = True

    nested_corr: float | None = None
    if len(nested_times) == len(times) and len(times) >= 3:
        n_deltas = np.diff(np.asarray(nested_times, dtype=float))
        r_deltas = np.diff(np.asarray(times, dtype=float))
        if n_deltas.std() > 0 and r_deltas.std() > 0:
            nested_corr = float(np.corrcoef(n_deltas, r_deltas)[0, 1])

    estimated: list[float] = []
    if samples_per_packet is not None and samples_per_packet > 0 and len(times) >= 1:
        median_delta = float(np.median(deltas)) if deltas else 1000.0
        for i, t_i in enumerate(times):
            if i + 1 < len(times):
                span_i = float(times[i + 1] - t_i)
                if span_i <= 0:
                    span_i = median_delta
            else:
                span_i = median_delta
            n = samples_per_packet
            for j in range(n):
                # Field name contract: estimated_sample_timestamp
                estimated.append(t_i + (j + 0.5) * span_i / n)

    delta_min = float(min(deltas)) if deltas else None
    delta_median = float(np.median(deltas)) if deltas else None
    delta_p95 = float(np.percentile(deltas, 95)) if deltas else None

    summary = SessionTimebaseSummary(
        session_ordinal=session.session_ordinal,
        packet_count=len(session.packets),
        gap_count=gaps,
        regression_count=regressions,
        duplicate_count=duplicates,
        duration_inconsistency=duration_inconsistency,
        delta_min_ms=delta_min,
        delta_median_ms=delta_median,
        delta_p95_ms=delta_p95,
        nested_time_delta_corr=nested_corr,
        estimated_sample_count=len(estimated),
    )
    return SessionTimebaseResult(
        summary=summary,
        deltas_ms=deltas,
        estimated_sample_timestamp=estimated,
    )


def build_timebase_report(
    session_results: list[SessionTimebaseResult],
    *,
    meta,
    gap_threshold_ms: float,
    samples_per_packet: int | None,
) -> TimebaseReport:
    gap_hist: dict[str, int] = {}
    total_gaps = 0
    total_reg = 0
    total_dup = 0
    dur_inconsist = 0
    total_est = 0
    all_positive_deltas: list[float] = []

    for res in session_results:
        total_gaps += res.summary.gap_count
        total_reg += res.summary.regression_count
        total_dup += res.summary.duplicate_count
        if res.summary.duration_inconsistency:
            dur_inconsist += 1
        total_est += res.summary.estimated_sample_count
        for d in res.deltas_ms:
            cls = _gap_class(d, gap_threshold_ms)
            gap_hist[cls] = gap_hist.get(cls, 0) + 1
            if d > 0:
                all_positive_deltas.append(d)

    implied_rate: float | None = None
    if samples_per_packet and all_positive_deltas:
        med = float(np.median(all_positive_deltas))
        if med > 0:
            implied_rate = samples_per_packet / (med / 1000.0)

    return TimebaseReport(
        meta=meta,
        sessions=[r.summary for r in session_results],
        gap_class_histogram=gap_hist,
        total_gap_count=total_gaps,
        total_regression_count=total_reg,
        total_duplicate_count=total_dup,
        duration_inconsistency_count=dur_inconsist,
        samples_per_packet_hypothesis=samples_per_packet,
        estimated_sample_timestamp_enabled=samples_per_packet is not None,
        total_estimated_samples=total_est,
        implied_rate_estimate_hz_unverified=implied_rate,
        implied_rate_status="unverified",
    )

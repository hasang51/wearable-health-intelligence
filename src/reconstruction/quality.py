"""Research-only candidate signal-quality score with explicit reason codes."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.reconstruction.channel_rel import ChannelPairResult
from src.reconstruction.models import QualityLabel
from src.reconstruction.periodicity import PeriodicityResult
from src.reconstruction.segment import ContinuousSegment

WINDOW_S = 10.0
HOP_S = 5.0


@dataclass
class QualityWindow:
    window_id: str
    segment_id: str
    session_ordinal: int
    channel: int
    layout: str
    hypothesis_key: str
    start_idx: int
    end_idx: int
    score: float
    label: QualityLabel
    reason_codes: list[str] = field(default_factory=list)
    flatline_rate: float = 0.0
    clip_rate: float = 0.0
    band_power_ratio: float = 0.0
    acf_peak_value: float = 0.0


def _flatline_rate(x: np.ndarray, eps: float = 1e-6) -> float:
    if x.size < 2:
        return 1.0
    d = np.abs(np.diff(x.astype(np.float64)))
    return float(np.mean(d <= eps))


def _clip_rate(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    lo, hi = np.percentile(x, [0.5, 99.5])
    # Treat extreme concentration at min/max of int24-ish range as clipping
    xmin, xmax = float(np.min(x)), float(np.max(x))
    span = xmax - xmin
    if span < 1e-9:
        return 1.0
    at_edge = (x <= xmin + 0.01 * span) | (x >= xmax - 0.01 * span)
    # Only call clipping if many samples pile at edges AND span is large
    rate = float(np.mean(at_edge))
    if span < 100:
        return 0.0
    return rate if rate > 0.3 else float(np.mean((x == xmin) | (x == xmax)))


def score_window(
    values: np.ndarray,
    *,
    periodicity: PeriodicityResult | None,
    pair: ChannelPairResult | None,
    window_id: str,
    segment: ContinuousSegment,
) -> QualityWindow:
    reasons: list[str] = []
    x = np.asarray(values, dtype=np.float64)
    flat = _flatline_rate(x)
    clip = _clip_rate(x)
    score = 0.5
    band = 0.0
    acf_v = 0.0

    if flat >= 0.9:
        score = 0.05
        reasons.append("flatline")
        label = QualityLabel.UNUSABLE
    elif clip >= 0.5:
        score = 0.1
        reasons.append("clipping")
        label = QualityLabel.UNUSABLE
    else:
        if periodicity is not None:
            band = periodicity.band_power_ratio
            acf_v = periodicity.acf_peak_value
            if periodicity.usable:
                score += 0.25
                reasons.append("periodic_ok")
            if band >= 0.2:
                score += 0.1
            if periodicity.dominant_prominence >= 3.0:
                score += 0.1
                reasons.append("prominent_peak")
            if periodicity.harmonic_present:
                score += 0.05
            if not periodicity.usable:
                score -= 0.15
                reasons.append("weak_periodicity")
        if pair is not None:
            if pair.dom_freq_agreement:
                score += 0.1
                reasons.append("channel_agree")
            elif pair.dom_freq_rel_diff is not None and pair.dom_freq_rel_diff > 0.25:
                score -= 0.1
                reasons.append("channel_disagree")
            if "inverted_channels" in pair.reason_codes:
                reasons.append("inverted_channels")
                # Inversion can still be a valid optical relationship
                score += 0.02
        score = float(np.clip(score, 0.0, 1.0))
        if (
            score >= 0.7
            and band >= 0.15
            and periodicity is not None
            and periodicity.usable
            and acf_v >= 0.15
        ):
            label = QualityLabel.PLAUSIBLE_CANDIDATE_SIGNAL
            reasons.append("plausible_candidate")
        elif score >= 0.45:
            label = QualityLabel.UNCERTAIN
            reasons.append("mixed_evidence")
        else:
            label = QualityLabel.POOR
            reasons.append("low_score")

    return QualityWindow(
        window_id=window_id,
        segment_id=segment.segment_id,
        session_ordinal=segment.session_ordinal,
        channel=segment.channel,
        layout=segment.layout,
        hypothesis_key=segment.hypothesis_key,
        start_idx=0,
        end_idx=int(x.size),
        score=score,
        label=label,
        reason_codes=reasons,
        flatline_rate=flat,
        clip_rate=clip,
        band_power_ratio=band,
        acf_peak_value=acf_v,
    )


def evaluate_segment_quality(
    segment: ContinuousSegment,
    periodicity: PeriodicityResult | None = None,
    pair: ChannelPairResult | None = None,
) -> list[QualityWindow]:
    """Slide windows within a segment; never across gaps (segment already split)."""
    fs = float(segment.fs_hz) if segment.fs_hz > 0 else 1.0
    win = max(8, int(WINDOW_S * fs))
    hop = max(1, int(HOP_S * fs))
    x = segment.values
    windows: list[QualityWindow] = []
    if x.size < win:
        # Single window over whole segment
        w = score_window(
            x,
            periodicity=periodicity,
            pair=pair,
            window_id=f"{segment.segment_id}_w0",
            segment=segment,
        )
        w.start_idx = 0
        w.end_idx = int(x.size)
        windows.append(w)
        return windows

    wi = 0
    for start in range(0, max(1, x.size - win + 1), hop):
        end = min(x.size, start + win)
        w = score_window(
            x[start:end],
            periodicity=periodicity,
            pair=pair,
            window_id=f"{segment.segment_id}_w{wi}",
            segment=segment,
        )
        w.start_idx = start
        w.end_idx = end
        windows.append(w)
        wi += 1
    return windows


def label_counts(windows: list[QualityWindow]) -> dict[str, int]:
    counts = {lab.value: 0 for lab in QualityLabel}
    for w in windows:
        counts[w.label.value] = counts.get(w.label.value, 0) + 1
    return counts

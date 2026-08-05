"""Periodicity, quality labels, channel relationships."""

from __future__ import annotations

import numpy as np

from src.reconstruction.channel_rel import analyze_channel_pair
from src.reconstruction.models import QualityLabel
from src.reconstruction.periodicity import analyze_segment_periodicity
from src.reconstruction.quality import evaluate_segment_quality, score_window
from src.reconstruction.segment import ContinuousSegment


def _seg(values: np.ndarray, fs: float = 33.0, channel: int = 0) -> ContinuousSegment:
    t = np.arange(values.size, dtype=np.float64) * (1000.0 / fs)
    return ContinuousSegment(
        segment_id=f"test_ch{channel}",
        session_ordinal=0,
        channel=channel,
        values=values.astype(np.float64),
        relative_times_ms=t,
        packet_start=0,
        packet_end=10,
        layout="BLOCKED_PACKET_LOCAL",
        hypothesis_key="H_2x33:default",
        fs_hz=fs,
    )


def test_periodic_signal_plausible():
    fs = 33.0
    t = np.arange(0, 20, 1 / fs)
    # ~1.2 Hz pulse-like sinusoid
    values = (10000 * np.sin(2 * np.pi * 1.2 * t)).astype(np.float64)
    seg = _seg(values, fs=fs)
    per = analyze_segment_periodicity(seg)
    assert per.usable or per.band_power_ratio > 0.1
    windows = evaluate_segment_quality(seg, periodicity=per)
    labels = {w.label for w in windows}
    assert (
        QualityLabel.PLAUSIBLE_CANDIDATE_SIGNAL in labels
        or QualityLabel.UNCERTAIN in labels
    )


def test_noise_poor_or_uncertain():
    rng = np.random.default_rng(0)
    values = rng.normal(0, 1000, size=660)
    seg = _seg(values)
    per = analyze_segment_periodicity(seg)
    # White noise should not be marked usable periodicity.
    assert per.usable is False or per.band_power_ratio < 0.5
    windows = evaluate_segment_quality(seg, periodicity=per)
    # Majority of windows should not be top-tier plausible.
    n_plausible = sum(1 for w in windows if w.label == QualityLabel.PLAUSIBLE_CANDIDATE_SIGNAL)
    assert n_plausible <= max(1, len(windows) // 2)


def test_flatline_unusable():
    values = np.full(330, 42.0)
    seg = _seg(values)
    per = analyze_segment_periodicity(seg)
    w = score_window(
        values,
        periodicity=per,
        pair=None,
        window_id="w0",
        segment=seg,
    )
    assert w.label == QualityLabel.UNUSABLE
    assert "flatline" in w.reason_codes


def test_clipping_unusable():
    values = np.concatenate([np.full(200, 0.0), np.full(200, 1e7)])
    seg = _seg(values)
    w = score_window(values, periodicity=None, pair=None, window_id="w0", segment=seg)
    assert w.label in (QualityLabel.UNUSABLE, QualityLabel.POOR)


def test_delayed_and_inverted_channels():
    fs = 33.0
    t = np.arange(0, 15, 1 / fs)
    a = np.sin(2 * np.pi * 1.1 * t)
    b = -np.roll(a, 5)  # inverted + delayed
    seg_a = _seg(a * 1000, fs=fs, channel=0)
    seg_b = _seg(b * 1000, fs=fs, channel=1)
    pair = analyze_channel_pair(seg_a, seg_b)
    assert pair.zero_lag_corr < 0 or "inverted_channels" in pair.reason_codes or pair.max_abs_xcorr > 0.3
    assert pair.best_lag_samples != 0 or abs(pair.zero_lag_corr) > 0.2

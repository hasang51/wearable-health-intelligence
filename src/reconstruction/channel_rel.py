"""Channel relationship analysis: correlation, lag, coherence, dom-freq agreement."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from src.reconstruction.periodicity import BAND_HI_HZ, BAND_LO_HZ
from src.reconstruction.segment import ContinuousSegment


@dataclass
class ChannelPairResult:
    session_ordinal: int
    channel_a: int
    channel_b: int
    layout: str
    hypothesis_key: str
    zero_lag_corr: float = 0.0
    max_abs_xcorr: float = 0.0
    best_lag_samples: int = 0
    best_lag_ms: float = 0.0
    mean_coherence_band: float = 0.0
    dom_freq_a_hz: float | None = None
    dom_freq_b_hz: float | None = None
    dom_freq_agreement: bool = False
    dom_freq_rel_diff: float | None = None
    correlation_computed: bool = False
    coherence_computed: bool = False
    reason_codes: list[str] = field(default_factory=list)


def _align_shortest(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(a.size, b.size)
    return a[:n].astype(np.float64), b[:n].astype(np.float64)


def _dom_freq(x: np.ndarray, fs: float) -> float | None:
    if fs <= 0 or x.size < 64:
        return None
    x = x - np.median(x)
    nperseg = min(256, max(32, x.size // 4))
    freqs, psd = signal.welch(x, fs=fs, nperseg=nperseg)
    mask = (freqs >= BAND_LO_HZ) & (freqs <= BAND_HI_HZ)
    if not np.any(mask):
        return None
    return float(freqs[mask][int(np.argmax(psd[mask]))])


def analyze_channel_pair(
    seg_a: ContinuousSegment,
    seg_b: ContinuousSegment,
    *,
    max_lag_s: float = 2.0,
) -> ChannelPairResult:
    """Compare two channels from the same continuous packet range when possible."""
    result = ChannelPairResult(
        session_ordinal=seg_a.session_ordinal,
        channel_a=seg_a.channel,
        channel_b=seg_b.channel,
        layout=seg_a.layout,
        hypothesis_key=seg_a.hypothesis_key,
    )
    a, b = _align_shortest(seg_a.values, seg_b.values)
    if a.size < 8:
        result.reason_codes.append("too_short")
        return result

    fs = float(seg_a.fs_hz) if seg_a.fs_hz > 0 else float(seg_b.fs_hz)
    # Zero-lag correlation
    if np.std(a) > 1e-12 and np.std(b) > 1e-12:
        result.zero_lag_corr = float(np.corrcoef(a, b)[0, 1])
        result.correlation_computed = True
    else:
        result.reason_codes.append("zero_variance")

    # Lagged cross-correlation
    max_lag = max(1, int(max_lag_s * fs)) if fs > 0 else 1
    max_lag = min(max_lag, a.size - 1)
    a0 = a - np.mean(a)
    b0 = b - np.mean(b)
    xcorr = signal.correlate(a0, b0, mode="full")
    mid = a0.size - 1
    lo = mid - max_lag
    hi = mid + max_lag
    window = xcorr[lo : hi + 1]
    denom = np.std(a0) * np.std(b0) * a0.size + 1e-15
    window = window / denom
    peak = int(np.argmax(np.abs(window)))
    result.best_lag_samples = peak - max_lag
    result.best_lag_ms = float(result.best_lag_samples / fs * 1000.0) if fs > 0 else 0.0
    result.max_abs_xcorr = float(np.abs(window[peak]))
    if np.std(a0) > 1e-12 and np.std(b0) > 1e-12:
        result.correlation_computed = True

    # Spectral coherence in band
    if fs > 0 and a.size >= 64:
        nperseg = min(128, max(32, a.size // 4))
        freqs, coh = signal.coherence(a, b, fs=fs, nperseg=nperseg)
        mask = (freqs >= BAND_LO_HZ) & (freqs <= BAND_HI_HZ)
        if np.any(mask):
            result.mean_coherence_band = float(np.mean(coh[mask]))
            result.coherence_computed = True
        else:
            result.reason_codes.append("coherence_band_empty")
    else:
        result.reason_codes.append("coherence_unavailable")

    fa = _dom_freq(a, fs)
    fb = _dom_freq(b, fs)
    result.dom_freq_a_hz = fa
    result.dom_freq_b_hz = fb
    if fa is not None and fb is not None and fa > 0 and fb > 0:
        rel = abs(fa - fb) / ((fa + fb) / 2.0)
        result.dom_freq_rel_diff = float(rel)
        result.dom_freq_agreement = rel <= 0.10
        if result.dom_freq_agreement:
            result.reason_codes.append("dom_freq_agree")
        else:
            result.reason_codes.append("dom_freq_disagree")

    if result.zero_lag_corr < -0.5:
        result.reason_codes.append("inverted_channels")
    if abs(result.best_lag_ms) > 50 and result.max_abs_xcorr > 0.3:
        result.reason_codes.append("delayed_channels")

    return result


def match_segments_for_pairs(
    segments: list[ContinuousSegment],
) -> list[ChannelPairResult]:
    """Pair segments that share session, layout, hypothesis, and packet range."""
    by_key: dict[tuple, list[ContinuousSegment]] = {}
    for s in segments:
        key = (s.session_ordinal, s.layout, s.hypothesis_key, s.packet_start, s.packet_end)
        by_key.setdefault(key, []).append(s)
    results: list[ChannelPairResult] = []
    for group in by_key.values():
        group = sorted(group, key=lambda s: s.channel)
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                results.append(analyze_channel_pair(group[i], group[j]))
    return results

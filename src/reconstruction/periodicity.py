"""Periodic plausibility: ACF, Welch PSD, band ratio, harmonics, stability."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from src.reconstruction.segment import ContinuousSegment

BAND_LO_HZ = 0.5
BAND_HI_HZ = 5.0
MIN_SEGMENT_SAMPLES = 64
MIN_SEGMENT_SECONDS = 4.0


@dataclass
class PeriodicityResult:
    segment_id: str
    channel: int
    layout: str
    hypothesis_key: str
    fs_hz: float
    n_samples: int
    band_power_ratio: float = 0.0
    dominant_frequency_hz: float | None = None
    dominant_prominence: float = 0.0
    harmonic_present: bool = False
    acf_peak_lag_s: float | None = None
    acf_peak_value: float = 0.0
    usable: bool = False
    reason_codes: list[str] = field(default_factory=list)


def _band_mask(freqs: np.ndarray, lo: float = BAND_LO_HZ, hi: float = BAND_HI_HZ) -> np.ndarray:
    return (freqs >= lo) & (freqs <= hi)


def analyze_segment_periodicity(seg: ContinuousSegment) -> PeriodicityResult:
    """Compute periodicity metrics on a single continuous segment (no cross-gap)."""
    result = PeriodicityResult(
        segment_id=seg.segment_id,
        channel=seg.channel,
        layout=seg.layout,
        hypothesis_key=seg.hypothesis_key,
        fs_hz=seg.fs_hz,
        n_samples=int(seg.values.size),
    )
    fs = float(seg.fs_hz)
    if fs <= 0 or seg.values.size < MIN_SEGMENT_SAMPLES:
        result.reason_codes.append("segment_too_short")
        return result
    if seg.values.size / fs < MIN_SEGMENT_SECONDS:
        result.reason_codes.append("segment_duration_short")
        return result

    x = seg.values.astype(np.float64)
    x = x - np.median(x)
    mad = np.median(np.abs(x))
    if mad < 1e-12:
        result.reason_codes.append("flatline_segment")
        return result
    x = x / (1.4826 * mad)

    # Welch PSD
    nperseg = min(256, max(32, seg.values.size // 4))
    freqs, psd = signal.welch(x, fs=fs, nperseg=nperseg)
    total = float(np.sum(psd) + 1e-15)
    mask = _band_mask(freqs)
    band = float(np.sum(psd[mask]))
    result.band_power_ratio = band / total

    if np.any(mask):
        band_freqs = freqs[mask]
        band_psd = psd[mask]
        peak_i = int(np.argmax(band_psd))
        result.dominant_frequency_hz = float(band_freqs[peak_i])
        continuum = float(np.median(band_psd) + 1e-15)
        result.dominant_prominence = float(band_psd[peak_i] / continuum)
        # Harmonic ~2f
        f0 = result.dominant_frequency_hz
        if f0 and f0 > 0:
            harm = 2.0 * f0
            if BAND_LO_HZ <= harm <= BAND_HI_HZ:
                tol = 0.15 * f0
                near = np.abs(band_freqs - harm) <= tol
                if np.any(near) and float(np.max(band_psd[near])) > continuum * 1.5:
                    result.harmonic_present = True
                    result.reason_codes.append("harmonic_structure")

    # Autocorrelation
    acf = signal.correlate(x, x, mode="full")
    acf = acf[acf.size // 2 :]
    if acf[0] != 0:
        acf = acf / acf[0]
    # Search lags corresponding to 0.5–5 Hz
    lag_min = max(1, int(fs / BAND_HI_HZ))
    lag_max = min(len(acf) - 1, max(lag_min + 1, int(fs / BAND_LO_HZ)))
    if lag_max > lag_min:
        window = acf[lag_min : lag_max + 1]
        peak_rel = int(np.argmax(window))
        result.acf_peak_lag_s = float((lag_min + peak_rel) / fs)
        result.acf_peak_value = float(window[peak_rel])
        if result.acf_peak_value > 0.2:
            result.reason_codes.append("acf_peak")

    if result.band_power_ratio >= 0.15 and result.dominant_prominence >= 2.0:
        result.usable = True
        result.reason_codes.append("periodic_candidate")
    else:
        result.reason_codes.append("weak_periodicity")

    return result


def segment_stability(results: list[PeriodicityResult]) -> dict[str, float]:
    """Dominant-frequency stability across segments (CV)."""
    freqs = [
        r.dominant_frequency_hz
        for r in results
        if r.dominant_frequency_hz is not None and r.usable
    ]
    if len(freqs) < 2:
        return {"cv": 0.0, "n": float(len(freqs)), "mean_hz": float(freqs[0]) if freqs else 0.0}
    arr = np.asarray(freqs, dtype=np.float64)
    mean = float(np.mean(arr))
    cv = float(np.std(arr) / (mean + 1e-15))
    return {"cv": cv, "n": float(len(freqs)), "mean_hz": mean}


def analyze_many(segments: list[ContinuousSegment]) -> list[PeriodicityResult]:
    return [analyze_segment_periodicity(s) for s in segments]

"""Relative candidate timebase from explicit samples-per-packet hypotheses."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_GAP_MS = 1500.0


def gap_threshold_ms(median_packet_interval_ms: float) -> float:
    """Split threshold: max(1.5 * median, 1500 ms)."""
    return max(1.5 * float(median_packet_interval_ms), MIN_GAP_MS)


def median_positive_delta(timestamps_ms: list[int] | np.ndarray) -> float:
    ts = np.asarray(timestamps_ms, dtype=np.float64)
    if ts.size < 2:
        return 1000.0
    d = np.diff(ts)
    pos = d[d > 0]
    if pos.size == 0:
        return 1000.0
    return float(np.median(pos))


@dataclass
class RelativeTimebase:
    """Hypothesis-relative sample times (not device clock authority)."""

    packet_timestamps_ms: list[int]
    samples_per_packet: int
    median_interval_ms: float
    gap_threshold: float
    implied_rate_hz: float
    timebase_status: str = "hypothesis_relative"
    implied_rate_status: str = "unverified_implied_rate"

    def sample_times_ms(self) -> list[float]:
        """Relative sample timestamps for concatenated packet streams (pre-split)."""
        n_s = self.samples_per_packet
        if n_s < 1:
            return []
        dt = self.median_interval_ms / n_s
        out: list[float] = []
        for t_packet in self.packet_timestamps_ms:
            for j in range(n_s):
                out.append(float(t_packet) + j * dt)
        return out


def build_relative_timebase(
    packet_timestamps_ms: list[int],
    samples_per_packet: int,
) -> RelativeTimebase:
    med = median_positive_delta(packet_timestamps_ms)
    g = gap_threshold_ms(med)
    rate = (samples_per_packet / (med / 1000.0)) if med > 0 else 0.0
    return RelativeTimebase(
        packet_timestamps_ms=list(packet_timestamps_ms),
        samples_per_packet=samples_per_packet,
        median_interval_ms=med,
        gap_threshold=g,
        implied_rate_hz=float(rate),
    )

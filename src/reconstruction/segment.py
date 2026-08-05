"""Gap-aware segmentation; never filter or compute spectra across a gap."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.reconstruction.timebase import gap_threshold_ms, median_positive_delta


@dataclass
class ContinuousSegment:
    """One continuous segment of a candidate channel stream."""

    segment_id: str
    session_ordinal: int
    channel: int
    values: np.ndarray
    relative_times_ms: np.ndarray
    packet_start: int
    packet_end: int  # exclusive
    layout: str
    hypothesis_key: str
    fs_hz: float


@dataclass
class SessionSegments:
    session_ordinal: int
    gap_threshold_ms: float
    median_interval_ms: float
    segments: list[ContinuousSegment] = field(default_factory=list)
    gap_count: int = 0


def packet_gap_breaks(
    packet_timestamps_ms: list[int],
    *,
    threshold_ms: float | None = None,
) -> tuple[list[tuple[int, int]], float, float, int]:
    """Return packet index ranges [start, end) that are continuous.

    Also returns (median_interval, threshold, gap_count).
    """
    n = len(packet_timestamps_ms)
    if n == 0:
        return [], 1000.0, 1500.0, 0
    med = median_positive_delta(packet_timestamps_ms)
    thr = float(threshold_ms) if threshold_ms is not None else gap_threshold_ms(med)
    ranges: list[tuple[int, int]] = []
    start = 0
    gaps = 0
    for k in range(n - 1):
        delta = packet_timestamps_ms[k + 1] - packet_timestamps_ms[k]
        if delta < 0 or delta > thr:
            ranges.append((start, k + 1))
            start = k + 1
            gaps += 1
    ranges.append((start, n))
    return ranges, med, thr, gaps


def assert_no_cross_gap(operation: str, segment_count: int) -> None:
    """Guard for APIs that must not stitch segments."""
    if segment_count != 1:
        raise ValueError(
            f"{operation} refuses cross-gap processing; got {segment_count} segments"
        )


def split_channel_by_packets(
    *,
    session_ordinal: int,
    channel: int,
    packet_channel_samples: list[list[int]],
    packet_timestamps_ms: list[int],
    layout: str,
    hypothesis_key: str,
    samples_per_packet: int,
    fs_hz: float,
    threshold_ms: float | None = None,
) -> SessionSegments:
    """Split a channel stream using packet-level gaps.

    packet_channel_samples[k] = samples for this channel from packet k
    (length may vary slightly with remainder rules; relative time uses samples_per_packet
    hypothesis spacing based on actual count per packet).
    """
    ranges, med, thr, gap_count = packet_gap_breaks(
        packet_timestamps_ms, threshold_ms=threshold_ms
    )
    dt = med / max(samples_per_packet, 1)
    segments: list[ContinuousSegment] = []
    for ri, (ps, pe) in enumerate(ranges):
        vals: list[int] = []
        times: list[float] = []
        for k in range(ps, pe):
            chunk = packet_channel_samples[k]
            t0 = float(packet_timestamps_ms[k])
            for j, v in enumerate(chunk):
                vals.append(int(v))
                times.append(t0 + j * dt)
        if not vals:
            continue
        seg_id = f"s{session_ordinal}_ch{channel}_seg{ri}"
        segments.append(
            ContinuousSegment(
                segment_id=seg_id,
                session_ordinal=session_ordinal,
                channel=channel,
                values=np.asarray(vals, dtype=np.float64),
                relative_times_ms=np.asarray(times, dtype=np.float64),
                packet_start=ps,
                packet_end=pe,
                layout=layout,
                hypothesis_key=hypothesis_key,
                fs_hz=fs_hz,
            )
        )
    return SessionSegments(
        session_ordinal=session_ordinal,
        gap_threshold_ms=thr,
        median_interval_ms=med,
        segments=segments,
        gap_count=gap_count,
    )

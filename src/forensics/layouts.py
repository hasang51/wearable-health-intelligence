"""Interleaved channel layouts with packet-local and continuous phase."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

CHANNEL_COUNTS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 8, 11)


def deinterleave(
    values: Sequence[int] | np.ndarray,
    channel_count: int,
    *,
    start_phase: int = 0,
) -> tuple[list[list[int]], int]:
    """De-interleave a payload into channel_count channels.

    Round-robin from start_phase. Returns (channels, next_phase).
    Remainder samples when L % C != 0 are assigned in order; phase advances
    by L so continuous layouts preserve channel identity across packets.
    """
    if channel_count < 1:
        raise ValueError("channel_count must be >= 1")
    arr = values if isinstance(values, np.ndarray) else np.asarray(values, dtype=np.int64)
    n = int(arr.size)
    phase = start_phase % channel_count
    if n == 0:
        return [[] for _ in range(channel_count)], phase
    channels = [
        arr[np.arange((ch - phase) % channel_count, n, channel_count)].tolist()
        for ch in range(channel_count)
    ]
    return channels, (phase + n) % channel_count


def interleave(channels: Sequence[Sequence[int]]) -> list[int]:
    """Round-robin interleave channel sequences (min length determines count)."""
    if not channels:
        return []
    c = len(channels)
    lengths = [len(ch) for ch in channels]
    total = sum(lengths)
    out: list[int] = []
    idx = [0] * c
    phase = 0
    for _ in range(total):
        # Skip exhausted channels while preserving phase order.
        spun = 0
        while idx[phase] >= lengths[phase] and spun < c:
            phase = (phase + 1) % c
            spun += 1
        if spun >= c:
            break
        out.append(int(channels[phase][idx[phase]]))
        idx[phase] += 1
        phase = (phase + 1) % c
    return out


def deinterleave_session(
    packets: Sequence[Sequence[int]],
    channel_count: int,
    *,
    layout_mode: str,
) -> list[list[int]]:
    """De-interleave multiple packets under packet_local or continuous mode."""
    channels: list[list[int]] = [[] for _ in range(channel_count)]
    phase = 0
    for payload in packets:
        start = 0 if layout_mode == "packet_local" else phase
        parts, next_phase = deinterleave(payload, channel_count, start_phase=start)
        for i, part in enumerate(parts):
            channels[i].extend(part)
        if layout_mode == "continuous":
            phase = next_phase
        else:
            phase = 0
    return channels

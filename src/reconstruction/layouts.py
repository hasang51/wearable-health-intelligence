"""Explicit Phase 3 layout contracts: interleaved/blocked × packet-local/continuous."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

import numpy as np

from src.forensics.layouts import deinterleave as _phase2_deinterleave


class ExplicitLayout(str, Enum):
    INTERLEAVED_PACKET_LOCAL = "INTERLEAVED_PACKET_LOCAL"
    INTERLEAVED_CONTINUOUS = "INTERLEAVED_CONTINUOUS"
    BLOCKED_PACKET_LOCAL = "BLOCKED_PACKET_LOCAL"
    BLOCKED_CONTINUOUS = "BLOCKED_CONTINUOUS"


LAYOUT_DEFINITIONS: dict[str, dict[str, str]] = {
    ExplicitLayout.INTERLEAVED_PACKET_LOCAL.value: {
        "rule": "sample i -> channel (i % C); phase resets each packet",
        "phase2_equivalent": "packet_local",
    },
    ExplicitLayout.INTERLEAVED_CONTINUOUS.value: {
        "rule": "round-robin with phase carry (phase + L) % C across packets",
        "phase2_equivalent": "continuous",
    },
    ExplicitLayout.BLOCKED_PACKET_LOCAL.value: {
        "rule": "C contiguous blocks of floor(L/C); remainder round-robin in-packet; no phase carry",
        "phase2_equivalent": "none",
    },
    ExplicitLayout.BLOCKED_CONTINUOUS.value: {
        "rule": "blocked packing with remainder/phase carry across packets",
        "phase2_equivalent": "none",
    },
}


def layouts_algebraically_identical(payload_length: int, channel_count: int) -> dict[str, bool]:
    """When L % C == 0, local and continuous variants coincide for equal splits."""
    equal = channel_count > 0 and payload_length % channel_count == 0
    return {
        "interleaved_local_eq_continuous": equal,
        "blocked_local_eq_continuous": equal,
    }


def _blocked_split(
    values: Sequence[int] | np.ndarray,
    channel_count: int,
    *,
    start_phase: int = 0,
) -> tuple[list[list[int]], int]:
    """Split into C contiguous blocks; remainder assigned round-robin from start_phase."""
    if channel_count < 1:
        raise ValueError("channel_count must be >= 1")
    arr = values if isinstance(values, np.ndarray) else np.asarray(values, dtype=np.int64)
    n = int(arr.size)
    phase = start_phase % channel_count
    channels: list[list[int]] = [[] for _ in range(channel_count)]
    if n == 0:
        return channels, phase

    block = n // channel_count
    for c in range(channel_count):
        start = c * block
        channels[c].extend(arr[start : start + block].tolist())

    rem_start = channel_count * block
    for i, v in enumerate(arr[rem_start:].tolist()):
        ch = (phase + i) % channel_count
        channels[ch].append(int(v))
    next_phase = (phase + (n - rem_start)) % channel_count
    return channels, next_phase


def apply_layout_packet(
    values: Sequence[int] | np.ndarray,
    channel_count: int,
    layout: ExplicitLayout | str,
    *,
    start_phase: int = 0,
) -> tuple[list[list[int]], int]:
    """Apply one layout to a single packet. Returns (channels, next_phase)."""
    layout_s = ExplicitLayout(layout) if not isinstance(layout, ExplicitLayout) else layout
    if layout_s == ExplicitLayout.INTERLEAVED_PACKET_LOCAL:
        return _phase2_deinterleave(values, channel_count, start_phase=0)
    if layout_s == ExplicitLayout.INTERLEAVED_CONTINUOUS:
        return _phase2_deinterleave(values, channel_count, start_phase=start_phase)
    if layout_s == ExplicitLayout.BLOCKED_PACKET_LOCAL:
        return _blocked_split(values, channel_count, start_phase=0)
    if layout_s == ExplicitLayout.BLOCKED_CONTINUOUS:
        return _blocked_split(values, channel_count, start_phase=start_phase)
    raise ValueError(f"Unknown layout: {layout}")


def apply_layout_session(
    packets: Sequence[Sequence[int]],
    channel_count: int,
    layout: ExplicitLayout | str,
) -> list[list[int]]:
    """Apply layout across packets, respecting continuous phase when required."""
    layout_s = ExplicitLayout(layout) if not isinstance(layout, ExplicitLayout) else layout
    continuous = layout_s in (
        ExplicitLayout.INTERLEAVED_CONTINUOUS,
        ExplicitLayout.BLOCKED_CONTINUOUS,
    )
    channels: list[list[int]] = [[] for _ in range(channel_count)]
    phase = 0
    for payload in packets:
        start = phase if continuous else 0
        parts, next_phase = apply_layout_packet(
            payload, channel_count, layout_s, start_phase=start
        )
        for i, part in enumerate(parts):
            channels[i].extend(part)
        phase = next_phase if continuous else 0
    return channels


def phase2_layout_name(layout: ExplicitLayout | str) -> str | None:
    """Map Phase 3 interleaved layouts to Phase 2 names."""
    layout_s = ExplicitLayout(layout) if not isinstance(layout, ExplicitLayout) else layout
    if layout_s == ExplicitLayout.INTERLEAVED_PACKET_LOCAL:
        return "packet_local"
    if layout_s == ExplicitLayout.INTERLEAVED_CONTINUOUS:
        return "continuous"
    return None

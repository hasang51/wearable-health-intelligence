"""Tests for interleave layouts and packet-boundary phase."""

from __future__ import annotations

from src.forensics.layouts import CHANNEL_COUNTS, deinterleave, deinterleave_session, interleave


def test_interleave_round_trip_each_channel_count() -> None:
    for c in CHANNEL_COUNTS:
        channels = [[i * 100 + j for j in range(12)] for i in range(c)]
        # Trim so total length works with round-robin from equal lengths
        packed = interleave(channels)
        restored, phase = deinterleave(packed, c, start_phase=0)
        assert phase == 0  # equal lengths → phase returns to 0
        for i in range(c):
            assert restored[i] == channels[i]


def test_continuous_phase_across_packets_when_not_divisible() -> None:
    # L=5, C=3 → phase advances by 5%3=2 each packet
    c = 3
    packets = [
        list(range(0, 5)),
        list(range(10, 15)),
        list(range(20, 25)),
    ]
    continuous = deinterleave_session(packets, c, layout_mode="continuous")
    local = deinterleave_session(packets, c, layout_mode="packet_local")
    assert continuous != local

    # Manual continuous
    phase = 0
    manual: list[list[int]] = [[] for _ in range(c)]
    for payload in packets:
        parts, phase = deinterleave(payload, c, start_phase=phase)
        for i, part in enumerate(parts):
            manual[i].extend(part)
    assert continuous == manual


def test_packet_boundary_phase_differs_for_66_mod_c() -> None:
    payload_a = list(range(66))
    payload_b = list(range(100, 166))
    for c in (4, 5, 8):
        assert 66 % c != 0
        cont = deinterleave_session([payload_a, payload_b], c, layout_mode="continuous")
        loc = deinterleave_session([payload_a, payload_b], c, layout_mode="packet_local")
        assert cont != loc

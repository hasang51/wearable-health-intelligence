"""Tests for explicit Phase 3 layout contracts."""

from __future__ import annotations

from src.forensics.layouts import deinterleave_session
from src.reconstruction.layouts import (
    ExplicitLayout,
    apply_layout_packet,
    apply_layout_session,
    layouts_algebraically_identical,
    phase2_layout_name,
)


def test_interleaved_packet_local_matches_phase2():
    packets = [list(range(66)), [100 + i for i in range(66)]]
    p3 = apply_layout_session(packets, 2, ExplicitLayout.INTERLEAVED_PACKET_LOCAL)
    p2 = deinterleave_session(packets, 2, layout_mode="packet_local")
    assert p3 == p2
    assert phase2_layout_name(ExplicitLayout.INTERLEAVED_PACKET_LOCAL) == "packet_local"


def test_interleaved_continuous_matches_phase2():
    # L % C != 0 so continuous differs from local
    packets = [list(range(5)), list(range(5, 10)), list(range(10, 15))]
    p3 = apply_layout_session(packets, 2, ExplicitLayout.INTERLEAVED_CONTINUOUS)
    p2 = deinterleave_session(packets, 2, layout_mode="continuous")
    assert p3 == p2
    assert phase2_layout_name(ExplicitLayout.INTERLEAVED_CONTINUOUS) == "continuous"


def test_interleaved_identity_when_l_mod_c_zero():
    packets = [list(range(66))]
    local = apply_layout_session(packets, 2, ExplicitLayout.INTERLEAVED_PACKET_LOCAL)
    cont = apply_layout_session(packets, 2, ExplicitLayout.INTERLEAVED_CONTINUOUS)
    assert local == cont
    flags = layouts_algebraically_identical(66, 2)
    assert flags["interleaved_local_eq_continuous"] is True


def test_blocked_differs_from_interleaved():
    payload = list(range(66))
    inter, _ = apply_layout_packet(payload, 2, ExplicitLayout.INTERLEAVED_PACKET_LOCAL)
    blocked, _ = apply_layout_packet(payload, 2, ExplicitLayout.BLOCKED_PACKET_LOCAL)
    assert inter != blocked
    assert blocked[0] == list(range(33))
    assert blocked[1] == list(range(33, 66))
    assert inter[0] == list(range(0, 66, 2))
    assert inter[1] == list(range(1, 66, 2))


def test_blocked_identity_when_l_mod_c_zero():
    packets = [list(range(66)), list(range(66, 132))]
    local = apply_layout_session(packets, 2, ExplicitLayout.BLOCKED_PACKET_LOCAL)
    cont = apply_layout_session(packets, 2, ExplicitLayout.BLOCKED_CONTINUOUS)
    assert local == cont
    assert layouts_algebraically_identical(66, 2)["blocked_local_eq_continuous"] is True


def test_blocked_continuous_remainder_carry():
    # L=5, C=2 -> block=2, remainder=1; continuous carries remainder phase.
    packets = [[0, 1, 2, 3, 4], [10, 11, 12, 13, 14]]
    local = apply_layout_session(packets, 2, ExplicitLayout.BLOCKED_PACKET_LOCAL)
    cont = apply_layout_session(packets, 2, ExplicitLayout.BLOCKED_CONTINUOUS)
    assert local[0][:2] == [0, 1]
    assert local[1][:2] == [2, 3]
    assert layouts_algebraically_identical(5, 2)["blocked_local_eq_continuous"] is False
    # Continuous phase after first remainder (→ ch0) advances to ch1 for next remainder.
    assert local != cont
    assert sum(len(ch) for ch in local) == sum(len(ch) for ch in cont) == 10

"""Reconstruction grid integration: metadata exclusion and layout apply."""

from __future__ import annotations

from src.reconstruction.layouts import ExplicitLayout, apply_layout_packet
from src.reconstruction.payload import extract_signal_values, primary_hypotheses
from src.reconstruction.reconstruct import LoadedSession, reconstruct_session


def test_metadata_excluded_from_streams():
    hyps = {h.hypothesis_id: h for h in primary_hypotheses()}
    h = hyps["H_2x32_plus_2global"]
    payload = list(range(66))
    signal = extract_signal_values(payload, h)
    assert len(signal) == 64
    channels, _ = apply_layout_packet(signal, 2, ExplicitLayout.BLOCKED_PACKET_LOCAL)
    assert len(channels[0]) == 32
    assert len(channels[1]) == 32
    # Excluded endpoint values must not appear
    flat = channels[0] + channels[1]
    assert 0 not in flat
    assert 65 not in flat


def test_reconstruct_session_builds_segments():
    hyp = next(h for h in primary_hypotheses() if h.hypothesis_id == "H_2x33")
    payloads = [list(range(66)) for _ in range(5)]
    times = [i * 1000 for i in range(5)]
    session = LoadedSession(
        session_ordinal=0,
        raw_payloads=payloads,
        timestamps_ms=times,
        transformed_payloads=payloads,
    )
    cand = reconstruct_session(session, hyp, ExplicitLayout.BLOCKED_PACKET_LOCAL)
    assert cand.layout == "BLOCKED_PACKET_LOCAL"
    assert len(cand.packet_channels) == 5
    assert cand.segments
    assert cand.fs_hz > 0

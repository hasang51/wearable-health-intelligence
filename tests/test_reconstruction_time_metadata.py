"""Metadata detection, timebase, and gap segmentation tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.reconstruction.metadata import analyze_all_positions, compute_position_features
from src.reconstruction.segment import assert_no_cross_gap, packet_gap_breaks, split_channel_by_packets
from src.reconstruction.timebase import build_relative_timebase, gap_threshold_ms


def test_gap_threshold_rule():
    assert gap_threshold_ms(1000.0) == 1500.0  # 1.5*1000=1500
    assert gap_threshold_ms(800.0) == 1500.0  # max(1200, 1500)
    assert gap_threshold_ms(2000.0) == 3000.0  # 1.5*2000


def test_relative_time_reconstruction():
    ts = [0, 1000, 2000]
    tb = build_relative_timebase(ts, samples_per_packet=33)
    times = tb.sample_times_ms()
    assert len(times) == 99
    assert times[0] == 0.0
    assert abs(times[1] - (1000.0 / 33)) < 1e-9
    assert tb.timebase_status == "hypothesis_relative"
    assert tb.implied_rate_status == "unverified_implied_rate"
    assert abs(tb.implied_rate_hz - 33.0) < 1e-6


def test_gap_segmentation_splits():
    # median ~1000; threshold 1500; one big gap
    ts = [0, 1000, 2000, 2000 + 5000, 2000 + 6000]
    ranges, med, thr, gaps = packet_gap_breaks(ts)
    assert gaps == 1
    assert thr == 1500.0
    assert ranges == [(0, 3), (3, 5)]


def test_no_cross_gap_guard():
    assert_no_cross_gap("welch", 1)
    with pytest.raises(ValueError, match="cross-gap"):
        assert_no_cross_gap("welch", 2)


def test_split_channel_respects_gaps():
    ts = [0, 1000, 2000, 8000, 9000]
    # 2 samples per packet
    pcs = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
    segs = split_channel_by_packets(
        session_ordinal=0,
        channel=0,
        packet_channel_samples=pcs,
        packet_timestamps_ms=ts,
        layout="BLOCKED_PACKET_LOCAL",
        hypothesis_key="H_2x33:default",
        samples_per_packet=2,
        fs_hz=2.0,
    )
    assert segs.gap_count == 1
    assert len(segs.segments) == 2
    assert segs.segments[0].values.tolist() == [1, 2, 3, 4, 5, 6]
    assert segs.segments[1].values.tolist() == [7, 8, 9, 10]


def test_metadata_detection_counter_vs_signal():
    n = 100
    # Position 0: monotonic counter (metadata-like)
    # Position 1: smooth sinusoidal-ish signal values
    packets = []
    for k in range(n):
        row = [0] * 66
        row[0] = k  # counter
        row[1] = int(1000 + 50 * np.sin(2 * np.pi * k / 20))
        for p in range(2, 66):
            row[p] = int(2000 + 10 * np.sin(2 * np.pi * (k + p) / 15))
        packets.append(row)
    records = analyze_all_positions(packets, timestamps_ms=list(range(n)))
    assert records[0].metadata_likelihood > records[1].metadata_likelihood
    assert records[0].decision == "propose_exclude" or records[0].metadata_likelihood >= 0.45
    assert "tracks_packet_index" in records[0].reasons or "high_monotonicity" in records[0].reasons
    # Signal-like position should tend to keep
    assert records[5].decision == "keep" or records[5].metadata_likelihood < records[0].metadata_likelihood


def test_compute_position_features_unit():
    x = np.arange(50, dtype=np.float64)
    row = compute_position_features(x, packet_indices=np.arange(50, dtype=np.float64))
    assert row.features["monotonicity"] >= 0.95
    assert row.features["corr_packet_index"] >= 0.99

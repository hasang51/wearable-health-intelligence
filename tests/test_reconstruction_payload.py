"""Tests for payload hypotheses and signal extraction."""

from __future__ import annotations

from src.reconstruction.payload import (
    PAYLOAD_LENGTH,
    build_default_hypotheses,
    extract_signal_values,
    hypothesis_key,
    primary_hypotheses,
)


def test_all_hypotheses_partition_66():
    for h in build_default_hypotheses():
        h.validate(PAYLOAD_LENGTH)
        assert set(h.signal_indices) | set(h.metadata_indices) == set(range(66))
        assert not (set(h.signal_indices) & set(h.metadata_indices))


def test_h_2x33():
    hyps = {h.hypothesis_id: h for h in primary_hypotheses()}
    h = hyps["H_2x33"]
    assert h.channel_count == 2
    assert h.samples_per_packet == 66
    assert h.metadata_indices == ()
    payload = list(range(66))
    assert extract_signal_values(payload, h) == payload


def test_h_2x32_plus_2global():
    hyps = {hypothesis_key(h): h for h in build_default_hypotheses()}
    h = hyps["H_2x32_plus_2global:endpoints"]
    assert h.metadata_indices == (0, 65)
    assert h.samples_per_packet == 64
    payload = list(range(66))
    sig = extract_signal_values(payload, h)
    assert len(sig) == 64
    assert sig[0] == 1
    assert sig[-1] == 64


def test_h_2block_meta_per_ch():
    hyps = {hypothesis_key(h): h for h in build_default_hypotheses()}
    h = hyps["H_2block_meta_per_ch:last_of_block"]
    assert h.metadata_indices == (32, 65)
    assert h.samples_per_packet == 64
    payload = list(range(66))
    sig = extract_signal_values(payload, h)
    assert len(sig) == 64
    assert 32 not in set(sig)
    assert 65 not in set(sig)


def test_h_3x22():
    hyps = {h.hypothesis_id: h for h in primary_hypotheses()}
    h = hyps["H_3x22"]
    assert h.channel_count == 3
    assert h.samples_per_packet == 66


def test_primary_has_four_families():
    prim = primary_hypotheses()
    ids = {h.hypothesis_id for h in prim}
    assert ids == {"H_2x33", "H_2x32_plus_2global", "H_2block_meta_per_ch", "H_3x22"}

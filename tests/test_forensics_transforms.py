"""Tests for 24-bit transforms and byte permutations."""

from __future__ import annotations

from src.forensics.transforms import (
    PERMUTATIONS,
    permute_bytes,
    to_int24,
    to_uint24,
    transform_array_fast,
    transform_value,
)


def test_uint24_int24_boundaries() -> None:
    assert to_uint24(0) == 0
    assert to_uint24((1 << 24) + 5) == 5
    assert to_uint24((1 << 23) - 1) == (1 << 23) - 1
    assert to_uint24(1 << 23) == 1 << 23
    assert to_uint24((1 << 24) - 1) == (1 << 24) - 1

    assert to_int24(0) == 0
    assert to_int24((1 << 23) - 1) == (1 << 23) - 1
    assert to_int24(1 << 23) == -(1 << 23)
    assert to_int24((1 << 24) - 1) == -1


def test_all_six_permutations_identity_and_distinct() -> None:
    u = 0x123456
    assert permute_bytes(u, "ABC") == u
    results = {name: permute_bytes(u, name) for name in PERMUTATIONS}
    assert results["ABC"] == u
    # Not all permutations collapse for this value
    assert len(set(results.values())) == 6


def test_transform_signedness_with_permutation() -> None:
    v = 0x800000  # sign bit set
    assert transform_value(v, signedness="uint24", byte_order="ABC") == 0x800000
    assert transform_value(v, signedness="int24", byte_order="ABC") == -(1 << 23)


def test_transform_array_fast_matches_scalar() -> None:
    values = [0, 1, (1 << 23) - 1, 1 << 23, (1 << 24) - 1, 0xABCDEF]
    for signedness in ("uint24", "int24"):
        for order in PERMUTATIONS:
            fast = transform_array_fast(values, signedness=signedness, byte_order=order)
            slow = [
                transform_value(v, signedness=signedness, byte_order=order) for v in values
            ]
            assert fast.tolist() == slow

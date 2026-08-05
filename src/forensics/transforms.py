"""24-bit integer transforms and byte permutations."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

MASK24 = 0xFFFFFF
SIGN_BIT = 1 << 23

# Canonical labels: A=b0 (MSB of packed word), B=b1, C=b2 (LSB).
PERMUTATIONS: dict[str, tuple[int, int, int]] = {
    "ABC": (0, 1, 2),
    "ACB": (0, 2, 1),
    "BAC": (1, 0, 2),
    "BCA": (1, 2, 0),
    "CAB": (2, 0, 1),
    "CBA": (2, 1, 0),
}


def to_uint24(v: int) -> int:
    return int(v) & MASK24


def to_int24(v: int) -> int:
    u = int(v) & MASK24
    if u & SIGN_BIT:
        return u - (1 << 24)
    return u


def split_bytes(u: int) -> tuple[int, int, int]:
    """Pack low 24 bits as big-endian bytes (A, B, C)."""
    w = u & MASK24
    return (w >> 16) & 0xFF, (w >> 8) & 0xFF, w & 0xFF


def join_bytes(b0: int, b1: int, b2: int) -> int:
    return ((b0 & 0xFF) << 16) | ((b1 & 0xFF) << 8) | (b2 & 0xFF)


def permute_bytes(u: int, order: str) -> int:
    if order not in PERMUTATIONS:
        raise ValueError(f"Unknown byte order: {order}")
    bytes_abc = split_bytes(u)
    idx = PERMUTATIONS[order]
    return join_bytes(bytes_abc[idx[0]], bytes_abc[idx[1]], bytes_abc[idx[2]])


def transform_value(v: int, *, signedness: str, byte_order: str) -> int:
    permuted = permute_bytes(to_uint24(v), byte_order)
    if signedness == "int24":
        return to_int24(permuted)
    if signedness == "uint24":
        return to_uint24(permuted)
    raise ValueError(f"Unknown signedness: {signedness}")


def transform_array(
    values: Iterable[int],
    *,
    signedness: str,
    byte_order: str,
) -> np.ndarray:
    arr = np.fromiter((int(v) for v in values), dtype=np.int64)
    out = np.empty(arr.shape[0], dtype=np.int64)
    for i, v in enumerate(arr):
        out[i] = transform_value(int(v), signedness=signedness, byte_order=byte_order)
    return out


def transform_array_fast(
    values: np.ndarray | list[int],
    *,
    signedness: str,
    byte_order: str,
) -> np.ndarray:
    """Vectorized transform for scoring loops."""
    arr = np.asarray(values, dtype=np.int64) & MASK24
    b0 = (arr >> 16) & 0xFF
    b1 = (arr >> 8) & 0xFF
    b2 = arr & 0xFF
    parts = (b0, b1, b2)
    idx = PERMUTATIONS[byte_order]
    permuted = (parts[idx[0]] << 16) | (parts[idx[1]] << 8) | parts[idx[2]]
    if signedness == "int24":
        sign = (permuted & SIGN_BIT) != 0
        return np.where(sign, permuted - (1 << 24), permuted).astype(np.int64)
    return permuted.astype(np.int64)

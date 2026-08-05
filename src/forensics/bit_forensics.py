"""Bit/byte structure forensics over raw PPG integers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from src.forensics.models import BitForensicsSummary
from src.forensics.transforms import split_bytes

MASK24 = 0xFFFFFF


def _trailing_zeros24(u: int) -> int:
    if u == 0:
        return 24
    n = 0
    while n < 24 and (u & 1) == 0:
        u >>= 1
        n += 1
    return n


def _leading_zeros24(u: int) -> int:
    if u == 0:
        return 24
    return 24 - u.bit_length()


@dataclass
class BitForensicsAccumulator:
    expected_length: int = 66
    total_values: int = 0
    zero_count: int = 0
    sat_count: int = 0
    vmin: int | None = None
    vmax: int | None = None
    bit_length_hist: Counter[int] = field(default_factory=Counter)
    leading_hist: Counter[int] = field(default_factory=Counter)
    trailing_hist: Counter[int] = field(default_factory=Counter)
    div_counts: dict[int, int] = field(default_factory=lambda: {k: 0 for k in range(1, 9)})
    constant_payloads: int = 0
    payload_count: int = 0
    # byte freq per position index 0..expected_length-1 for A,B,C — store as counts[pos][byte]
    byte_a: list[Counter[int]] = field(init=False)
    byte_b: list[Counter[int]] = field(init=False)
    byte_c: list[Counter[int]] = field(init=False)

    def __post_init__(self) -> None:
        self.byte_a = [Counter() for _ in range(self.expected_length)]
        self.byte_b = [Counter() for _ in range(self.expected_length)]
        self.byte_c = [Counter() for _ in range(self.expected_length)]

    def update_payload(self, values: list[int]) -> None:
        self.payload_count += 1
        if values and len(set(values)) == 1:
            self.constant_payloads += 1
        for i, raw in enumerate(values):
            u = int(raw) & MASK24
            self.total_values += 1
            self.vmin = u if self.vmin is None else min(self.vmin, u)
            self.vmax = u if self.vmax is None else max(self.vmax, u)
            if u == 0:
                self.zero_count += 1
            if u == 0 or u == MASK24:
                self.sat_count += 1
            self.bit_length_hist[u.bit_length()] += 1
            self.leading_hist[_leading_zeros24(u)] += 1
            self.trailing_hist[_trailing_zeros24(u)] += 1
            for k in range(1, 9):
                if u % (1 << k) == 0:
                    self.div_counts[k] += 1
            if i < self.expected_length:
                a, b, c = split_bytes(u)
                self.byte_a[i][a] += 1
                self.byte_b[i][b] += 1
                self.byte_c[i][c] += 1

    def _byte_entropy_proxy(self, counters: list[Counter[int]]) -> list[float]:
        """Per-position normalized unique-byte fraction (aggregate, not raw values)."""
        out: list[float] = []
        for ctr in counters:
            n = sum(ctr.values())
            if n == 0:
                out.append(0.0)
            else:
                out.append(len(ctr) / 256.0)
        return out

    def to_model(self) -> BitForensicsSummary:
        n = max(self.total_values, 1)
        div_rates = {str(k): self.div_counts[k] / n for k in range(1, 9)}
        return BitForensicsSummary(
            value_min=self.vmin,
            value_max=self.vmax,
            bit_length_histogram={str(k): v for k, v in sorted(self.bit_length_hist.items())},
            leading_zero_bit_histogram={str(k): v for k, v in sorted(self.leading_hist.items())},
            trailing_zero_bit_histogram={str(k): v for k, v in sorted(self.trailing_hist.items())},
            zero_rate=self.zero_count / n if self.total_values else 0.0,
            constant_payload_rate=(
                self.constant_payloads / self.payload_count if self.payload_count else 0.0
            ),
            saturation_rate=self.sat_count / n if self.total_values else 0.0,
            divisibility_by_power_of_two=div_rates,
            byte_frequency_abc={
                "A_unique_frac": self._byte_entropy_proxy(self.byte_a),
                "B_unique_frac": self._byte_entropy_proxy(self.byte_b),
                "C_unique_frac": self._byte_entropy_proxy(self.byte_c),
            },
        )

    def byte_heatmap_matrix(self) -> np.ndarray:
        """Return (3, expected_length) matrix of unique-byte fractions for plotting."""
        a = self._byte_entropy_proxy(self.byte_a)
        b = self._byte_entropy_proxy(self.byte_b)
        c = self._byte_entropy_proxy(self.byte_c)
        return np.array([a, b, c], dtype=float)

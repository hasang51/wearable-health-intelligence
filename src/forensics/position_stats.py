"""Online position-wise statistics for fixed-length PPG payloads."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.forensics.models import PositionStat

MASK24 = 0xFFFFFF


@dataclass
class _Welford:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0
    vmin: float | None = None
    vmax: float | None = None
    bit_sum: float = 0.0
    bit_min: int | None = None
    bit_max: int | None = None
    zero_count: int = 0
    sat_count: int = 0

    def update(self, value: int) -> None:
        v = float(value)
        self.n += 1
        delta = v - self.mean
        self.mean += delta / self.n
        delta2 = v - self.mean
        self.m2 += delta * delta2
        self.vmin = v if self.vmin is None else min(self.vmin, v)
        self.vmax = v if self.vmax is None else max(self.vmax, v)
        bl = int(value).bit_length()
        self.bit_sum += bl
        self.bit_min = bl if self.bit_min is None else min(self.bit_min, bl)
        self.bit_max = bl if self.bit_max is None else max(self.bit_max, bl)
        u = int(value) & MASK24
        if u == 0:
            self.zero_count += 1
        if u == 0 or u == MASK24:
            self.sat_count += 1

    @property
    def std(self) -> float | None:
        if self.n < 2:
            return 0.0 if self.n else None
        return math.sqrt(self.m2 / (self.n - 1))


@dataclass
class PositionStatsAccumulator:
    expected_length: int = 66
    positions: list[_Welford] = field(init=False)

    def __post_init__(self) -> None:
        self.positions = [_Welford() for _ in range(self.expected_length)]

    def update_payload(self, values: list[int]) -> None:
        n = min(len(values), self.expected_length)
        for i in range(n):
            self.positions[i].update(values[i])

    def to_models(self) -> list[PositionStat]:
        out: list[PositionStat] = []
        for i, w in enumerate(self.positions):
            if w.n == 0:
                out.append(PositionStat(position=i))
                continue
            width = None
            if w.vmin is not None and w.vmax is not None:
                width = w.vmax - w.vmin
            out.append(
                PositionStat(
                    position=i,
                    count=w.n,
                    min=w.vmin,
                    max=w.vmax,
                    mean=w.mean,
                    std=w.std,
                    bit_length_min=w.bit_min,
                    bit_length_max=w.bit_max,
                    bit_length_mean=w.bit_sum / w.n,
                    zero_rate=w.zero_count / w.n,
                    saturation_rate=w.sat_count / w.n,
                    range_width=width,
                )
            )
        return out

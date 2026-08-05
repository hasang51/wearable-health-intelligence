"""Non-visual decoder candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.forensics.layouts import CHANNEL_COUNTS, deinterleave
from src.forensics.models import (
    CandidateMetrics,
    DecoderCandidate,
    DecoderStatus,
    LayoutMode,
    Signedness,
)
from src.forensics.transforms import PERMUTATIONS, transform_array_fast

WEIGHTS: dict[str, float] = {
    "within_packet_deriv_mad": 1.0,
    "boundary_jump_ratio": 1.5,
    "cross_session_consistency": 1.0,
    "position_dependence": 0.8,
    "saturation_rate": 1.2,
    "flatline_rate": 1.2,
    "channel_duplication": 1.0,
    "channel_energy_balance": 0.6,
}

THRESHOLDS: dict[str, float] = {
    "reject_saturation_rate": 0.85,
    "reject_flatline_rate": 0.90,
    "reject_boundary_jump_ratio": 50.0,
    "provisional_boundary_jump_ratio": 8.0,
    "provisional_cross_session_consistency": 0.75,
    "near_tie_epsilon": 0.05,
    "signedness_twin_epsilon": 0.02,
    "exceptional_score_gap": 0.25,
}

FLATLINE_RUN = 8
EPS = 1e-9


def candidate_id(
    signedness: str,
    byte_order: str,
    channel_count: int,
    layout_mode: str,
) -> str:
    return f"{signedness}|{byte_order}|C{channel_count}|{layout_mode}"


def iter_candidate_specs() -> list[tuple[str, str, int, str]]:
    specs: list[tuple[str, str, int, str]] = []
    for signedness in ("uint24", "int24"):
        for byte_order in PERMUTATIONS:
            for c in CHANNEL_COUNTS:
                for layout in ("packet_local", "continuous"):
                    specs.append((signedness, byte_order, c, layout))
    return specs


@dataclass
class _SessionCandStats:
    deriv_chunks: list[np.ndarray] = field(default_factory=list)
    jumps: list[float] = field(default_factory=list)
    sat: int = 0
    total: int = 0
    flat_pairs: int = 0
    flat_denom: int = 0
    channel_vars: list[float] = field(default_factory=list)
    channel_corr_max: float = 0.0
    position_means: list[float] = field(default_factory=list)
    metric_vector: list[float] = field(default_factory=list)


def _mad(values: list[float] | np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    arr = np.asarray(values, dtype=float)
    return float(np.median(np.abs(arr - np.median(arr))))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.median(np.asarray(values, dtype=float)))


def _flatline_rate(series: np.ndarray, run: int = FLATLINE_RUN) -> tuple[int, int]:
    if series.size < 2:
        return 0, 0
    equal = series[1:] == series[:-1]
    flat_pairs = int(np.sum(equal))
    # Count samples belonging to runs of length >= run
    denom = int(series.size - 1)
    return flat_pairs, denom


def _max_abs_corr(channels: list[np.ndarray]) -> float:
    usable = [ch for ch in channels if ch.size >= 3 and float(np.std(ch)) > 0]
    if len(usable) < 2:
        return 0.0
    # Align by truncating to min length for pairwise corr
    m = min(ch.size for ch in usable)
    if m < 3:
        return 0.0
    mats = [ch[:m] - np.mean(ch[:m]) for ch in usable]
    max_corr = 0.0
    for i in range(len(mats)):
        for j in range(i + 1, len(mats)):
            a, b = mats[i], mats[j]
            denom = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denom <= EPS:
                continue
            corr = abs(float(np.dot(a, b) / denom))
            if corr > max_corr:
                max_corr = corr
    return max_corr


def _score_session_candidate(
    payloads: list[list[int]],
    *,
    signedness: str,
    byte_order: str,
    channel_count: int,
    layout_mode: str,
    expected_length: int,
) -> _SessionCandStats:
    stats = _SessionCandStats()
    phase = 0
    prev_last: list[float | None] = [None] * channel_count
    channel_chunks: list[list[np.ndarray]] = [[] for _ in range(channel_count)]
    pos_sums = np.zeros(expected_length, dtype=float)
    pos_counts = np.zeros(expected_length, dtype=float)

    for payload in payloads:
        raw = np.asarray(payload, dtype=np.int64)
        transformed = transform_array_fast(raw, signedness=signedness, byte_order=byte_order)
        for i, val in enumerate(transformed):
            if i < expected_length:
                pos_sums[i] += float(val)
                pos_counts[i] += 1.0

        start = 0 if layout_mode == "packet_local" else phase
        channels, next_phase = deinterleave(
            transformed, channel_count, start_phase=start
        )
        if layout_mode == "continuous":
            phase = next_phase
        else:
            phase = 0

        for ci, ch in enumerate(channels):
            if not ch:
                continue
            arr = np.asarray(ch, dtype=float)
            channel_chunks[ci].append(arr)
            if arr.size >= 2:
                stats.deriv_chunks.append(np.abs(np.diff(arr)))
            # saturation vs uint24 extremes after transform interpretation
            if signedness == "uint24":
                sat_mask = (arr <= 0) | (arr >= MASK_SAT)
            else:
                sat_mask = (arr <= INT24_MIN) | (arr >= INT24_MAX)
            stats.sat += int(np.sum(sat_mask))
            stats.total += int(arr.size)
            fp, fd = _flatline_rate(arr)
            stats.flat_pairs += fp
            stats.flat_denom += fd

            first = float(arr[0])
            last = float(arr[-1])
            if prev_last[ci] is not None:
                stats.jumps.append(abs(first - prev_last[ci]))  # type: ignore[arg-type]
            prev_last[ci] = last

    session_derivs = (
        np.concatenate(stats.deriv_chunks) if stats.deriv_chunks else np.array([])
    )
    deriv_mad = _mad(session_derivs) if session_derivs.size else 0.0
    jump_ratios = [j / max(EPS, deriv_mad) for j in stats.jumps]
    # Store raw components for aggregation
    stats.metric_vector = [
        deriv_mad,
        _median(jump_ratios),
        (stats.sat / stats.total) if stats.total else 0.0,
        (stats.flat_pairs / stats.flat_denom) if stats.flat_denom else 0.0,
    ]

    ch_arrays = [
        np.concatenate(chunks) if chunks else np.array([], dtype=float)
        for chunks in channel_chunks
    ]
    stats.channel_vars = [float(np.var(a)) if a.size else 0.0 for a in ch_arrays]
    stats.channel_corr_max = _max_abs_corr(ch_arrays)
    means = []
    for i in range(expected_length):
        if pos_counts[i] > 0:
            means.append(float(pos_sums[i] / pos_counts[i]))
    stats.position_means = means
    # Keep jump ratios and derivs for session-level rollup
    stats.jumps = jump_ratios
    return stats


MASK_SAT = 0xFFFFFF
INT24_MIN = -(1 << 23)
INT24_MAX = (1 << 23) - 1


@dataclass
class CandidateAccumulator:
    signedness: str
    byte_order: str
    channel_count: int
    layout_mode: str
    session_stats: list[_SessionCandStats] = field(default_factory=list)

    @property
    def cid(self) -> str:
        return candidate_id(
            self.signedness, self.byte_order, self.channel_count, self.layout_mode
        )

    def add_session(self, payloads: list[list[int]], expected_length: int) -> None:
        if not payloads:
            return
        self.session_stats.append(
            _score_session_candidate(
                payloads,
                signedness=self.signedness,
                byte_order=self.byte_order,
                channel_count=self.channel_count,
                layout_mode=self.layout_mode,
                expected_length=expected_length,
            )
        )


def _cv(values: list[float]) -> float:
    if not values:
        return 0.0
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr))
    if abs(mean) <= EPS:
        return float(np.std(arr))
    return float(np.std(arr) / abs(mean))


def finalize_candidate(acc: CandidateAccumulator) -> CandidateMetrics:
    if not acc.session_stats:
        return CandidateMetrics()

    all_jumps: list[float] = []
    sat = 0
    total = 0
    flat_p = 0
    flat_d = 0
    corr_vals: list[float] = []
    energy_cvs: list[float] = []
    pos_deps: list[float] = []
    session_vectors: list[list[float]] = []

    deriv_arrays: list[np.ndarray] = []
    for s in acc.session_stats:
        if s.deriv_chunks:
            deriv_arrays.append(np.concatenate(s.deriv_chunks))
        all_jumps.extend(s.jumps)
        sat += s.sat
        total += s.total
        flat_p += s.flat_pairs
        flat_d += s.flat_denom
        corr_vals.append(s.channel_corr_max)
        energy_cvs.append(_cv(s.channel_vars))
        if s.position_means:
            pos_deps.append(float(np.var(s.position_means)))
        session_vectors.append(s.metric_vector)

    deriv_mad = (
        _mad(np.concatenate(deriv_arrays))
        if deriv_arrays
        else 0.0
    )
    # Recompute jump ratios against global deriv mad for stability
    # (session jumps already ratioed locally; use median of those)
    boundary = _median(all_jumps)

    # Cross-session consistency: IQR of first metric across sessions
    if len(session_vectors) >= 2:
        mat = np.asarray(session_vectors, dtype=float)
        iqrs = []
        for col in range(mat.shape[1]):
            q75, q25 = np.percentile(mat[:, col], [75, 25])
            iqrs.append(float(q75 - q25))
        consistency = float(np.mean(iqrs))
    else:
        consistency = 0.0

    # Normalize position dependence relative to mean abs mean
    if pos_deps:
        pos_dep = float(np.median(pos_deps))
        scale = float(np.median([abs(x) for s in acc.session_stats for x in s.position_means] or [1.0]))
        pos_dep = pos_dep / max(EPS, scale * scale)
    else:
        pos_dep = 0.0

    return CandidateMetrics(
        within_packet_deriv_mad=deriv_mad,
        boundary_jump_ratio=boundary,
        cross_session_consistency=consistency,
        position_dependence=pos_dep,
        saturation_rate=(sat / total) if total else 0.0,
        flatline_rate=(flat_p / flat_d) if flat_d else 0.0,
        channel_duplication=float(np.median(corr_vals)) if corr_vals else 0.0,
        channel_energy_balance=float(np.median(energy_cvs)) if energy_cvs else 0.0,
    )


def _rank_normalize(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    for r, i in enumerate(order):
        ranks[i] = r / max(n - 1, 1)
    return ranks


def score_all_candidates(
    accumulators: list[CandidateAccumulator],
) -> list[tuple[CandidateAccumulator, CandidateMetrics, float]]:
    metrics_list = [finalize_candidate(a) for a in accumulators]
    keys = list(WEIGHTS.keys())
    # Exclude total_cost
    metric_keys = [k for k in keys if k != "total_cost"]
    columns = {k: [float(getattr(m, k)) for m in metrics_list] for k in metric_keys}
    norm = {k: _rank_normalize(columns[k]) for k in metric_keys}

    scored: list[tuple[CandidateAccumulator, CandidateMetrics, float]] = []
    for i, (acc, metrics) in enumerate(zip(accumulators, metrics_list)):
        total = 0.0
        for k in metric_keys:
            total += WEIGHTS[k] * norm[k][i]
        metrics.total_cost = total
        scored.append((acc, metrics, total))
    scored.sort(key=lambda t: t[2])
    return scored


def build_candidate_models(
    scored: list[tuple[CandidateAccumulator, CandidateMetrics, float]],
    statuses: dict[str, tuple[DecoderStatus, list[str]]],
) -> list[DecoderCandidate]:
    out: list[DecoderCandidate] = []
    for rank, (acc, metrics, _) in enumerate(scored, start=1):
        status, codes = statuses[acc.cid]
        out.append(
            DecoderCandidate(
                candidate_id=acc.cid,
                signedness=Signedness(acc.signedness),
                byte_order=acc.byte_order,
                channel_count=acc.channel_count,
                layout_mode=LayoutMode(acc.layout_mode),
                metrics=metrics,
                rank=rank,
                status=status,
                rationale_codes=codes,
            )
        )
    return out

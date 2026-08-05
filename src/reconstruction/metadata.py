"""Position-level metadata detection with explicit scored proposals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.reconstruction.models import PositionMetadataRecord


def _mad(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    med = float(np.median(x))
    return float(np.median(np.abs(x - med)))


def _entropy(values: np.ndarray, bins: int = 32) -> float:
    if values.size == 0:
        return 0.0
    # Discrete entropy over unique value frequencies when cardinality is small.
    uniq, counts = np.unique(values, return_counts=True)
    if uniq.size <= bins:
        p = counts.astype(np.float64) / counts.sum()
    else:
        hist, _ = np.histogram(values, bins=bins)
        hist = hist[hist > 0].astype(np.float64)
        p = hist / hist.sum()
    return float(-np.sum(p * np.log2(p + 1e-15)))


def _monotonicity(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    d = np.diff(values.astype(np.float64))
    nondec = float(np.mean(d >= 0))
    noninc = float(np.mean(d <= 0))
    return max(nondec, noninc)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or b.size < 3 or a.size != b.size:
        return 0.0
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return 0.0
    return float(np.corrcoef(a.astype(np.float64), b.astype(np.float64))[0, 1])


def _bit_stability(values: np.ndarray) -> float:
    """Fraction of bits that never flip across packets (sticky bits)."""
    if values.size < 2:
        return 1.0
    u = values.astype(np.int64) & 0xFFFFFF
    # Bit flips between consecutive samples
    flips = 0
    total = 0
    for bit in range(24):
        bits = (u >> bit) & 1
        bit_flips = int(np.sum(bits[1:] != bits[:-1]))
        flips += bit_flips
        total += max(len(bits) - 1, 0)
    if total == 0:
        return 1.0
    return 1.0 - flips / total


@dataclass
class PositionFeatureRow:
    position: int
    features: dict[str, float]
    metadata_likelihood: float
    reasons: list[str]


def compute_position_features(
    position_matrix: np.ndarray,
    *,
    packet_indices: np.ndarray | None = None,
    timestamps_ms: np.ndarray | None = None,
    neighbor_left: np.ndarray | None = None,
    neighbor_right: np.ndarray | None = None,
) -> PositionFeatureRow:
    """Compute metadata-detection features for one payload position.

    position_matrix: shape (n_packets,) raw integers at this position.
    """
    x = np.asarray(position_matrix, dtype=np.float64).ravel()
    features: dict[str, float] = {}
    reasons: list[str] = []

    med = float(np.median(x)) if x.size else 0.0
    mad = _mad(x)
    q75, q25 = (float(np.percentile(x, 75)), float(np.percentile(x, 25))) if x.size else (0.0, 0.0)
    features["median"] = med
    features["mad"] = mad
    features["iqr"] = q75 - q25
    features["entropy"] = _entropy(x)
    features["unique_ratio"] = float(len(np.unique(x)) / max(x.size, 1))
    features["monotonicity"] = _monotonicity(x)

    if packet_indices is not None and packet_indices.size == x.size:
        features["corr_packet_index"] = abs(_corr(x, packet_indices.astype(np.float64)))
    else:
        features["corr_packet_index"] = 0.0

    if timestamps_ms is not None and timestamps_ms.size == x.size:
        features["corr_timestamp"] = abs(_corr(x, timestamps_ms.astype(np.float64)))
    else:
        features["corr_timestamp"] = 0.0

    if x.size >= 2:
        features["cross_packet_deriv_mad"] = _mad(np.diff(x))
    else:
        features["cross_packet_deriv_mad"] = 0.0

    ncorrs = []
    if neighbor_left is not None and neighbor_left.size == x.size:
        ncorrs.append(abs(_corr(x, neighbor_left.astype(np.float64))))
    if neighbor_right is not None and neighbor_right.size == x.size:
        ncorrs.append(abs(_corr(x, neighbor_right.astype(np.float64))))
    features["neighbor_corr"] = float(np.mean(ncorrs)) if ncorrs else 0.0
    features["bit_pattern_stability"] = _bit_stability(x.astype(np.int64))

    # Likelihood scoring (heuristic, research-only)
    score = 0.0
    if features["monotonicity"] >= 0.95:
        score += 0.25
        reasons.append("high_monotonicity")
    if features["corr_packet_index"] >= 0.8:
        score += 0.25
        reasons.append("tracks_packet_index")
    if features["corr_timestamp"] >= 0.8:
        score += 0.15
        reasons.append("tracks_timestamp")
    if features["neighbor_corr"] < 0.15 and features["unique_ratio"] > 0.5:
        score += 0.15
        reasons.append("low_neighbor_corr")
    if features["bit_pattern_stability"] >= 0.98 and features["unique_ratio"] < 0.1:
        score += 0.1
        reasons.append("stable_bit_pattern")
    if features["mad"] < 1e-6 and features["unique_ratio"] < 0.05:
        score += 0.1
        reasons.append("near_constant")
    if features["entropy"] < 1.0 and features["unique_ratio"] < 0.2:
        score += 0.05
        reasons.append("low_entropy")

    likelihood = float(min(1.0, score))
    return PositionFeatureRow(
        position=0,  # filled by caller
        features=features,
        metadata_likelihood=likelihood,
        reasons=reasons,
    )


def analyze_all_positions(
    packets: list[list[int]],
    *,
    timestamps_ms: list[int] | None = None,
    propose_threshold: float = 0.45,
    session_matrices: list[np.ndarray] | None = None,
) -> list[PositionMetadataRecord]:
    """Analyze each payload position across packets.

    packets: list of equal-length integer payloads.
    session_matrices: optional list of (n_packets_s, L) arrays for cross-session stats.
    """
    if not packets:
        return []
    mat = np.asarray(packets, dtype=np.int64)
    n_packets, length = mat.shape
    pkt_idx = np.arange(n_packets, dtype=np.float64)
    ts = (
        np.asarray(timestamps_ms, dtype=np.float64)
        if timestamps_ms is not None and len(timestamps_ms) == n_packets
        else None
    )

    # Cross-session consistency: dispersion of per-session medians
    cross_raw = np.zeros(length, dtype=np.float64)
    cross_robust = np.zeros(length, dtype=np.float64)
    if session_matrices:
        for p in range(length):
            session_meds = []
            session_mads = []
            for sm in session_matrices:
                if sm.ndim != 2 or sm.shape[1] <= p:
                    continue
                col = sm[:, p].astype(np.float64)
                session_meds.append(float(np.median(col)))
                session_mads.append(_mad(col))
            if len(session_meds) >= 2:
                cross_raw[p] = float(np.std(session_meds))
                # robust: z-score session medians by session MAD
                zs = []
                for m, md in zip(session_meds, session_mads):
                    zs.append(m / (md + 1e-9))
                cross_robust[p] = float(np.std(zs))

    records: list[PositionMetadataRecord] = []
    for p in range(length):
        left = mat[:, p - 1] if p > 0 else None
        right = mat[:, p + 1] if p + 1 < length else None
        row = compute_position_features(
            mat[:, p],
            packet_indices=pkt_idx,
            timestamps_ms=ts,
            neighbor_left=left,
            neighbor_right=right,
        )
        row.features["cross_session_consistency_raw"] = float(cross_raw[p])
        row.features["cross_session_consistency_robust"] = float(cross_robust[p])
        if cross_raw[p] > 0 and cross_robust[p] < cross_raw[p] * 0.1:
            # high raw dispersion that collapses under robust norm — structural quirk
            pass

        decision = "propose_exclude" if row.metadata_likelihood >= propose_threshold else "keep"
        if decision == "propose_exclude" and "propose_exclude" not in row.reasons:
            row.reasons.append("score_above_threshold")

        records.append(
            PositionMetadataRecord(
                position=p,
                features={k: float(v) for k, v in row.features.items()},
                metadata_likelihood=row.metadata_likelihood,
                decision=decision,
                reasons=list(row.reasons),
                score=row.metadata_likelihood,
            )
        )
    return records


def cross_session_position_stats(
    session_packets: list[list[list[int]]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Return raw and robust-normalized mean cross-session consistency across positions."""
    if len(session_packets) < 2:
        return {"mean": 0.0}, {"mean": 0.0}
    mats = [np.asarray(sp, dtype=np.int64) for sp in session_packets if sp]
    if not mats:
        return {"mean": 0.0}, {"mean": 0.0}
    length = mats[0].shape[1]
    raws = []
    robusts = []
    for p in range(length):
        meds = [float(np.median(m[:, p])) for m in mats if m.shape[1] > p]
        mads = [_mad(m[:, p].astype(np.float64)) for m in mats if m.shape[1] > p]
        if len(meds) < 2:
            continue
        raws.append(float(np.std(meds)))
        zs = [m / (md + 1e-9) for m, md in zip(meds, mads)]
        robusts.append(float(np.std(zs)))
    return (
        {"mean": float(np.mean(raws)) if raws else 0.0, "max": float(np.max(raws)) if raws else 0.0},
        {
            "mean": float(np.mean(robusts)) if robusts else 0.0,
            "max": float(np.max(robusts)) if robusts else 0.0,
        },
    )

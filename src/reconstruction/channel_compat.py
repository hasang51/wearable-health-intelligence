"""Multi-metric channel-compatibility verdict for proprietary rate gates.

Replaces the invalid existential rule (any agreeing pair => compatible).
Evaluates aggregate evidence on the selected best hypothesis only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from src.reconstruction.channel_rel import ChannelPairResult
from src.reconstruction.models import ChannelCompatibilitySummary, ChannelCompatibilityVerdict


@dataclass(frozen=True)
class ChannelCompatibilityThresholds:
    """Conservative research defaults for proprietary channel agreement."""

    min_evaluable_pairs: int = 10
    min_evaluable_fraction: float = 0.60
    compatible_min_frequency_agreement: float = 0.70
    compatible_min_median_lagged_correlation: float = 0.30
    compatible_min_median_coherence: float = 0.20
    partial_min_frequency_agreement: float = 0.50
    partial_min_median_lagged_correlation: float = 0.25
    partial_min_median_coherence: float = 0.10

    def as_dict(self) -> dict[str, float | int]:
        return dict(asdict(self))


def filter_pairs_for_selected_hypothesis(
    pairs: list[ChannelPairResult],
    *,
    layout: str | None,
    hypothesis_key: str | None,
) -> list[ChannelPairResult]:
    """Restrict channel evidence to the selected best layout/hypothesis."""
    if layout is None or hypothesis_key is None:
        return []
    return [p for p in pairs if p.layout == layout and p.hypothesis_key == hypothesis_key]


def _pair_is_evaluable(pair: ChannelPairResult) -> bool:
    return "too_short" not in pair.reason_codes


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.median(np.asarray(values, dtype=np.float64)))


def _iqr(values: list[float]) -> float | None:
    if not values:
        return None
    arr = np.asarray(values, dtype=np.float64)
    return float(np.percentile(arr, 75) - np.percentile(arr, 25))


def aggregate_channel_pair_metrics(
    pairs: list[ChannelPairResult],
) -> dict[str, Any]:
    """Aggregate safe corpus-level metrics from channel pairs (no per-pair leak)."""
    total = len(pairs)
    evaluable = [p for p in pairs if _pair_is_evaluable(p)]
    non_eval = [p for p in pairs if not _pair_is_evaluable(p)]
    reason_counts: Counter[str] = Counter()
    for p in non_eval:
        if p.reason_codes:
            for code in p.reason_codes:
                reason_counts[code] += 1
        else:
            reason_counts["unspecified"] += 1

    freq_eval = [
        p
        for p in evaluable
        if p.dom_freq_a_hz is not None and p.dom_freq_b_hz is not None
    ]
    freq_agree = [p for p in freq_eval if p.dom_freq_agreement]

    zero_lags = [abs(float(p.zero_lag_corr)) for p in evaluable if p.correlation_computed]
    lagged = [float(p.max_abs_xcorr) for p in evaluable if p.correlation_computed]
    coherences = [float(p.mean_coherence_band) for p in evaluable if p.coherence_computed]
    best_lags = [float(p.best_lag_samples) for p in evaluable if p.correlation_computed]

    freq_frac: float | None
    if freq_eval:
        freq_frac = float(len(freq_agree) / len(freq_eval))
    else:
        freq_frac = None

    return {
        "total_pairs": total,
        "evaluable_pairs": len(evaluable),
        "evaluable_fraction": float(len(evaluable) / total) if total else 0.0,
        "frequency_evaluable_pairs": len(freq_eval),
        "frequency_agreeing_pairs": len(freq_agree),
        "frequency_agreement_fraction": freq_frac,
        "median_abs_zero_lag_correlation": _median(zero_lags),
        "median_max_abs_lagged_correlation": _median(lagged),
        "median_coherence": _median(coherences),
        "median_best_lag_samples": _median(best_lags),
        "best_lag_iqr_samples": _iqr(best_lags),
        "non_evaluable_reasons": dict(sorted(reason_counts.items())),
    }


def decide_channel_compatibility(
    *,
    total_pairs: int,
    evaluable_pairs: int,
    evaluable_fraction: float,
    frequency_evaluable_pairs: int = 0,
    frequency_agreeing_pairs: int = 0,
    frequency_agreement_fraction: float | None,
    median_abs_zero_lag_correlation: float | None = None,
    median_max_abs_lagged_correlation: float | None,
    median_coherence: float | None,
    median_best_lag_samples: float | None = None,
    best_lag_iqr_samples: float | None = None,
    non_evaluable_reasons: dict[str, int] | None = None,
    thresholds: ChannelCompatibilityThresholds | None = None,
) -> ChannelCompatibilitySummary:
    """Apply multi-metric decision logic. Missing metrics never improve the verdict."""
    thr = thresholds or ChannelCompatibilityThresholds()
    passed: list[str] = []
    failed: list[str] = []

    enough_pairs = evaluable_pairs >= thr.min_evaluable_pairs
    enough_frac = evaluable_fraction >= thr.min_evaluable_fraction
    if enough_pairs:
        passed.append("min_evaluable_pairs")
    else:
        failed.append("min_evaluable_pairs")
    if enough_frac:
        passed.append("min_evaluable_fraction")
    else:
        failed.append("min_evaluable_fraction")

    if not enough_pairs or not enough_frac:
        return ChannelCompatibilitySummary(
            verdict=ChannelCompatibilityVerdict.NOT_EVALUABLE,
            total_pairs=total_pairs,
            evaluable_pairs=evaluable_pairs,
            evaluable_fraction=evaluable_fraction,
            frequency_evaluable_pairs=frequency_evaluable_pairs,
            frequency_agreeing_pairs=frequency_agreeing_pairs,
            frequency_agreement_fraction=frequency_agreement_fraction,
            median_abs_zero_lag_correlation=median_abs_zero_lag_correlation,
            median_max_abs_lagged_correlation=median_max_abs_lagged_correlation,
            median_coherence=median_coherence,
            median_best_lag_samples=median_best_lag_samples,
            best_lag_iqr_samples=best_lag_iqr_samples,
            passed_criteria=passed,
            failed_criteria=failed,
            non_evaluable_reasons=dict(non_evaluable_reasons or {}),
            thresholds_used=thr.as_dict(),
        )

    freq_ok_compat = (
        frequency_agreement_fraction is not None
        and frequency_agreement_fraction >= thr.compatible_min_frequency_agreement
    )
    lagged_ok_compat = (
        median_max_abs_lagged_correlation is not None
        and median_max_abs_lagged_correlation >= thr.compatible_min_median_lagged_correlation
    )
    coh_ok_compat = (
        median_coherence is not None
        and median_coherence >= thr.compatible_min_median_coherence
    )

    if freq_ok_compat:
        passed.append("compatible_frequency_agreement")
    else:
        failed.append("compatible_frequency_agreement")
    if lagged_ok_compat:
        passed.append("compatible_median_lagged_correlation")
    else:
        failed.append("compatible_median_lagged_correlation")
    if coh_ok_compat:
        passed.append("compatible_median_coherence")
    else:
        failed.append("compatible_median_coherence")

    if freq_ok_compat and lagged_ok_compat and coh_ok_compat:
        return ChannelCompatibilitySummary(
            verdict=ChannelCompatibilityVerdict.COMPATIBLE,
            total_pairs=total_pairs,
            evaluable_pairs=evaluable_pairs,
            evaluable_fraction=evaluable_fraction,
            frequency_evaluable_pairs=frequency_evaluable_pairs,
            frequency_agreeing_pairs=frequency_agreeing_pairs,
            frequency_agreement_fraction=frequency_agreement_fraction,
            median_abs_zero_lag_correlation=median_abs_zero_lag_correlation,
            median_max_abs_lagged_correlation=median_max_abs_lagged_correlation,
            median_coherence=median_coherence,
            median_best_lag_samples=median_best_lag_samples,
            best_lag_iqr_samples=best_lag_iqr_samples,
            passed_criteria=passed,
            failed_criteria=failed,
            non_evaluable_reasons=dict(non_evaluable_reasons or {}),
            thresholds_used=thr.as_dict(),
        )

    freq_ok_partial = (
        frequency_agreement_fraction is not None
        and frequency_agreement_fraction >= thr.partial_min_frequency_agreement
    )
    lagged_ok_partial = (
        median_max_abs_lagged_correlation is not None
        and median_max_abs_lagged_correlation >= thr.partial_min_median_lagged_correlation
    )
    coh_ok_partial = (
        median_coherence is not None
        and median_coherence >= thr.partial_min_median_coherence
    )

    if freq_ok_partial:
        passed.append("partial_frequency_agreement")
    else:
        failed.append("partial_frequency_agreement")
    if lagged_ok_partial:
        passed.append("partial_median_lagged_correlation")
    else:
        failed.append("partial_median_lagged_correlation")
    if coh_ok_partial:
        passed.append("partial_median_coherence")
    else:
        failed.append("partial_median_coherence")

    if freq_ok_partial and (lagged_ok_partial or coh_ok_partial):
        verdict = ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE
    else:
        verdict = ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT

    return ChannelCompatibilitySummary(
        verdict=verdict,
        total_pairs=total_pairs,
        evaluable_pairs=evaluable_pairs,
        evaluable_fraction=evaluable_fraction,
        frequency_evaluable_pairs=frequency_evaluable_pairs,
        frequency_agreeing_pairs=frequency_agreeing_pairs,
        frequency_agreement_fraction=frequency_agreement_fraction,
        median_abs_zero_lag_correlation=median_abs_zero_lag_correlation,
        median_max_abs_lagged_correlation=median_max_abs_lagged_correlation,
        median_coherence=median_coherence,
        median_best_lag_samples=median_best_lag_samples,
        best_lag_iqr_samples=best_lag_iqr_samples,
        passed_criteria=passed,
        failed_criteria=failed,
        non_evaluable_reasons=dict(non_evaluable_reasons or {}),
        thresholds_used=thr.as_dict(),
    )


def evaluate_channel_compatibility(
    pairs: list[ChannelPairResult],
    *,
    layout: str | None = None,
    hypothesis_key: str | None = None,
    thresholds: ChannelCompatibilityThresholds | None = None,
    filter_to_selected: bool = True,
) -> ChannelCompatibilitySummary:
    """Evaluate channel compatibility, optionally restricted to selected hypothesis."""
    thr = thresholds or ChannelCompatibilityThresholds()
    if filter_to_selected:
        selected = filter_pairs_for_selected_hypothesis(
            pairs, layout=layout, hypothesis_key=hypothesis_key
        )
    else:
        selected = list(pairs)
    metrics = aggregate_channel_pair_metrics(selected)
    return decide_channel_compatibility(thresholds=thr, **metrics)

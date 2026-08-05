"""Deterministic classification and HR error metrics for public benchmark."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ConfusionCounts:
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0


def confusion_binary(y_true: list[int] | np.ndarray, y_pred: list[int] | np.ndarray) -> ConfusionCounts:
    yt = np.asarray(y_true, dtype=int)
    yp = np.asarray(y_pred, dtype=int)
    tp = int(np.sum((yt == 1) & (yp == 1)))
    tn = int(np.sum((yt == 0) & (yp == 0)))
    fp = int(np.sum((yt == 0) & (yp == 1)))
    fn = int(np.sum((yt == 1) & (yp == 0)))
    return ConfusionCounts(tp=tp, tn=tn, fp=fp, fn=fn)


def balanced_accuracy(c: ConfusionCounts) -> float:
    tpr = c.tp / (c.tp + c.fn) if (c.tp + c.fn) else 0.0
    tnr = c.tn / (c.tn + c.fp) if (c.tn + c.fp) else 0.0
    return 0.5 * (tpr + tnr)


def precision_recall_f1(c: ConfusionCounts) -> tuple[float, float, float]:
    prec = c.tp / (c.tp + c.fp) if (c.tp + c.fp) else 0.0
    rec = c.tp / (c.tp + c.fn) if (c.tp + c.fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return float(prec), float(rec), float(f1)


@dataclass
class HRMetrics:
    coverage: float
    mae: float | None
    median_abs_error: float | None
    bias: float | None
    n_estimates: int
    n_good: int


def hr_error_metrics(
    reference_bpm: list[float] | np.ndarray,
    estimated_bpm: list[float | None] | np.ndarray,
) -> HRMetrics:
    """Coverage = fraction of good refs with a non-None estimate; errors on paired values."""
    ref = list(reference_bpm)
    est = list(estimated_bpm)
    if len(ref) != len(est):
        raise ValueError("reference and estimate length mismatch")
    n_good = len(ref)
    pairs = [(float(r), float(e)) for r, e in zip(ref, est) if e is not None and np.isfinite(e)]
    n_est = len(pairs)
    coverage = n_est / n_good if n_good else 0.0
    if not pairs:
        return HRMetrics(
            coverage=coverage,
            mae=None,
            median_abs_error=None,
            bias=None,
            n_estimates=0,
            n_good=n_good,
        )
    errs = np.asarray([e - r for r, e in pairs], dtype=np.float64)
    abs_errs = np.abs(errs)
    return HRMetrics(
        coverage=float(coverage),
        mae=float(np.mean(abs_errs)),
        median_abs_error=float(np.median(abs_errs)),
        bias=float(np.mean(errs)),
        n_estimates=n_est,
        n_good=n_good,
    )

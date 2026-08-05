"""Optional BUT PPG v2.0.0 adapter — explicit external path only; never auto-discover."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.audit.privacy import SCRUBBER, ScrubbedException
from src.reconstruction.benchmark.metrics import (
    ConfusionCounts,
    balanced_accuracy,
    confusion_binary,
    hr_error_metrics,
    precision_recall_f1,
)


@dataclass
class BUTRecord:
    record_id: str
    subject_id: str
    fs_hz: float
    signal: np.ndarray
    quality_label: int  # 1=good, 0=bad
    reference_hr_bpm: float | None = None


@dataclass
class BenchmarkResult:
    ran: bool
    seed: int = 0
    record_count: int = 0
    subject_count: int = 0
    quality_balanced_accuracy: float | None = None
    quality_precision: float | None = None
    quality_recall: float | None = None
    quality_f1: float | None = None
    hr_coverage: float | None = None
    hr_mae: float | None = None
    hr_median_abs_error: float | None = None
    hr_bias: float | None = None
    selected_record_hashes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    private_detail: dict = field(default_factory=dict)


def _assert_external_dir(path: Path, workspace_root: Path | None = None) -> None:
    if not path.exists():
        raise ScrubbedException("Benchmark directory does not exist: <redacted>", SCRUBBER)
    if not path.is_dir():
        raise ScrubbedException("Benchmark path must be a directory: <redacted>", SCRUBBER)
    if workspace_root is not None:
        try:
            path.resolve().relative_to(workspace_root.resolve())
            raise ScrubbedException(
                "Benchmark directory must be outside the repository workspace",
                SCRUBBER,
            )
        except ValueError:
            pass  # not inside workspace — ok


def load_but_manifest(root: Path) -> list[BUTRecord]:
    """Load records from a simple manifest JSON (operator-prepared BUT extract).

    Expected manifest.json:
    {
      "version": "2.0.0",
      "records": [
        {
          "record_id": "...",
          "subject_id": "...",
          "fs_hz": 125.0,
          "quality_label": 1,
          "reference_hr_bpm": 72.0,
          "signal_file": "signals/rec001.npy"
        }
      ]
    }
    """
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ScrubbedException("BUT manifest.json missing in benchmark dir", SCRUBBER)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[BUTRecord] = []
    for rec in data.get("records", []):
        sig_path = root / str(rec["signal_file"])
        if not sig_path.is_file():
            continue
        if sig_path.suffix == ".npy":
            sig = np.load(sig_path)
        else:
            sig = np.loadtxt(sig_path, dtype=np.float64)
        records.append(
            BUTRecord(
                record_id=str(rec["record_id"]),
                subject_id=str(rec["subject_id"]),
                fs_hz=float(rec["fs_hz"]),
                signal=np.asarray(sig, dtype=np.float64).ravel(),
                quality_label=int(rec["quality_label"]),
                reference_hr_bpm=(
                    float(rec["reference_hr_bpm"])
                    if rec.get("reference_hr_bpm") is not None
                    else None
                ),
            )
        )
    return records


def _simple_quality_predict(signal: np.ndarray, fs: float) -> int:
    """Deterministic research heuristic (not clinical): band-energy proxy."""
    from scipy import signal as sp

    if signal.size < 64 or fs <= 0:
        return 0
    x = signal - np.median(signal)
    mad = np.median(np.abs(x))
    if mad < 1e-12:
        return 0
    nperseg = min(256, max(32, signal.size // 4))
    freqs, psd = sp.welch(x, fs=fs, nperseg=nperseg)
    total = float(np.sum(psd) + 1e-15)
    band = float(np.sum(psd[(freqs >= 0.5) & (freqs <= 5.0)]))
    return 1 if (band / total) >= 0.15 else 0


def _simple_hr_estimate(signal: np.ndarray, fs: float) -> float | None:
    from scipy import signal as sp

    if signal.size < 64 or fs <= 0:
        return None
    x = signal - np.median(signal)
    nperseg = min(256, max(32, signal.size // 4))
    freqs, psd = sp.welch(x, fs=fs, nperseg=nperseg)
    mask = (freqs >= 0.5) & (freqs <= 5.0)
    if not np.any(mask):
        return None
    f0 = float(freqs[mask][int(np.argmax(psd[mask]))])
    return f0 * 60.0


def select_records_deterministic(
    records: list[BUTRecord],
    *,
    seed: int = 0,
) -> list[BUTRecord]:
    """Sort by record_id; optional subject-safe shuffle with fixed seed."""
    by_subj: dict[str, list[BUTRecord]] = {}
    for r in records:
        by_subj.setdefault(r.subject_id, []).append(r)
    subjects = sorted(by_subj.keys())
    rng = np.random.default_rng(seed)
    order = list(subjects)
    rng.shuffle(order)
    selected: list[BUTRecord] = []
    for sid in order:
        recs = sorted(by_subj[sid], key=lambda r: r.record_id)
        selected.extend(recs)
    return selected


def run_but_benchmark(
    benchmark_dir: str | Path,
    *,
    seed: int = 0,
    workspace_root: Path | None = None,
) -> BenchmarkResult:
    """Evaluate public quality classification and reference-HR estimation."""
    root = Path(benchmark_dir)
    SCRUBBER.register_input_path(root)
    _assert_external_dir(root, workspace_root)

    try:
        records = load_but_manifest(root)
    except ScrubbedException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to load BUT benchmark: {exc}", SCRUBBER) from None

    if not records:
        return BenchmarkResult(
            ran=True,
            seed=seed,
            notes=["no_records_loaded"],
        )

    selected = select_records_deterministic(records, seed=seed)
    y_true = [r.quality_label for r in selected]
    y_pred = [_simple_quality_predict(r.signal, r.fs_hz) for r in selected]
    conf: ConfusionCounts = confusion_binary(y_true, y_pred)
    bal = balanced_accuracy(conf)
    prec, rec, f1 = precision_recall_f1(conf)

    # HR on good-quality subset
    good = [r for r in selected if r.quality_label == 1 and r.reference_hr_bpm is not None]
    refs = [float(r.reference_hr_bpm) for r in good]  # type: ignore[arg-type]
    ests: list[float | None] = [_simple_hr_estimate(r.signal, r.fs_hz) for r in good]
    hr = hr_error_metrics(refs, ests)

    import hashlib

    hashes = [
        hashlib.sha256(r.record_id.encode("utf-8")).hexdigest()[:16] for r in selected
    ]
    subjects = {r.subject_id for r in selected}

    return BenchmarkResult(
        ran=True,
        seed=seed,
        record_count=len(selected),
        subject_count=len(subjects),
        quality_balanced_accuracy=bal,
        quality_precision=prec,
        quality_recall=rec,
        quality_f1=f1,
        hr_coverage=hr.coverage,
        hr_mae=hr.mae,
        hr_median_abs_error=hr.median_abs_error,
        hr_bias=hr.bias,
        selected_record_hashes=hashes,
        notes=[
            "but_ppg_v2_adapter",
            "isolated_from_proprietary_decoder",
            "subject_grouped_deterministic_selection",
            "fs_explicit_from_manifest",
        ],
        private_detail={
            "confusion": {"tp": conf.tp, "tn": conf.tn, "fp": conf.fp, "fn": conf.fn},
            "n_good_hr": hr.n_good,
            "n_hr_estimates": hr.n_estimates,
        },
    )

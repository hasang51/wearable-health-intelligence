"""Private diagnostic plots for Phase 3 (never emit to safe reports)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from src.reconstruction.channel_rel import ChannelPairResult
from src.reconstruction.metadata import PositionMetadataRecord
from src.reconstruction.quality import QualityWindow
from src.reconstruction.segment import ContinuousSegment


def plot_metadata_heatmap(records: list[PositionMetadataRecord], out_path: Path) -> None:
    if not records:
        return
    keys = [
        "monotonicity",
        "corr_packet_index",
        "neighbor_corr",
        "unique_ratio",
        "bit_pattern_stability",
        "metadata_likelihood",
    ]
    mat = np.zeros((len(keys), len(records)))
    for j, rec in enumerate(records):
        for i, k in enumerate(keys):
            if k == "metadata_likelihood":
                mat[i, j] = rec.metadata_likelihood
            else:
                mat[i, j] = float(rec.features.get(k, 0.0))
    fig, ax = plt.subplots(figsize=(10, 3))
    im = ax.imshow(mat, aspect="auto", interpolation="nearest")
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(keys)
    ax.set_xlabel("payload position")
    ax.set_title("Metadata position features (private)")
    fig.colorbar(im, ax=ax, fraction=0.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_gap_map(
    packet_intervals_ms: list[float],
    threshold_ms: float,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 3))
    if packet_intervals_ms:
        ax.stem(range(len(packet_intervals_ms)), packet_intervals_ms, basefmt=" ")
    ax.axhline(threshold_ms, color="C1", linestyle="--", label="gap threshold")
    ax.set_xlabel("packet index")
    ax.set_ylabel("interval (ms)")
    ax.set_title("Packet intervals (private)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_segment_psd(seg: ContinuousSegment, out_path: Path) -> None:
    from scipy import signal as sp

    if seg.values.size < 64 or seg.fs_hz <= 0:
        return
    x = seg.values - np.median(seg.values)
    freqs, psd = sp.welch(x, fs=seg.fs_hz, nperseg=min(256, seg.values.size // 2))
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.semilogy(freqs, psd + 1e-15)
    ax.axvspan(0.5, 5.0, alpha=0.15, color="C2", label="0.5-5 Hz")
    ax.set_xlabel("Hz (unverified_implied_rate)")
    ax.set_ylabel("PSD")
    ax.set_title(f"Welch PSD {seg.segment_id} (private)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_acf(seg: ContinuousSegment, out_path: Path) -> None:
    from scipy import signal as sp

    if seg.values.size < 16:
        return
    x = seg.values - np.mean(seg.values)
    acf = sp.correlate(x, x, mode="full")
    acf = acf[acf.size // 2 :]
    if acf[0] != 0:
        acf = acf / acf[0]
    lags = np.arange(len(acf)) / max(seg.fs_hz, 1e-9)
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(lags[: min(len(lags), int(5 * max(seg.fs_hz, 1)))], acf[: min(len(acf), int(5 * max(seg.fs_hz, 1)))])
    ax.set_xlabel("lag (s)")
    ax.set_ylabel("ACF")
    ax.set_title(f"ACF {seg.segment_id} (private)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_channel_lag(pair: ChannelPairResult, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar([0], [pair.max_abs_xcorr])
    ax.set_title(
        f"max |xcorr|={pair.max_abs_xcorr:.3f} lag={pair.best_lag_ms:.1f}ms (private)"
    )
    ax.set_ylabel("|xcorr|")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_quality_timeline(windows: list[QualityWindow], out_path: Path) -> None:
    if not windows:
        return
    label_map = {
        "unusable": 0,
        "poor": 1,
        "uncertain": 2,
        "plausible_candidate_signal": 3,
    }
    ys = [label_map.get(w.label.value, 1) for w in windows]
    fig, ax = plt.subplots(figsize=(8, 2.5))
    ax.step(range(len(ys)), ys, where="mid")
    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(["unusable", "poor", "uncertain", "plausible"])
    ax.set_xlabel("window ordinal")
    ax.set_title("Quality timeline (private)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_layout_snippets(
    segments: list[ContinuousSegment],
    out_path: Path,
    *,
    allow_snippets: bool,
    max_points: int = 400,
) -> None:
    if not allow_snippets or not segments:
        return
    fig, ax = plt.subplots(figsize=(8, 3))
    for seg in segments[:4]:
        x = seg.values[:max_points]
        med = np.median(x)
        mad = np.median(np.abs(x - med)) + 1e-9
        ax.plot((x - med) / mad, label=f"ch{seg.channel}")
    ax.set_title("Robust-normalized snippets (private)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def write_plots(
    out_dir: Path,
    *,
    metadata_records: list[PositionMetadataRecord],
    packet_intervals: list[float],
    gap_threshold: float,
    segments: list[ContinuousSegment],
    pairs: list[ChannelPairResult],
    windows: list[QualityWindow],
    allow_private_snippets: bool,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    p = out_dir / "metadata_heatmap.png"
    plot_metadata_heatmap(metadata_records, p)
    written.append(p.name)
    p = out_dir / "gap_map.png"
    plot_gap_map(packet_intervals, gap_threshold, p)
    written.append(p.name)
    if segments:
        longest = max(segments, key=lambda s: s.values.size)
        p = out_dir / "segment_psd.png"
        plot_segment_psd(longest, p)
        written.append(p.name)
        p = out_dir / "segment_acf.png"
        plot_acf(longest, p)
        written.append(p.name)
        p = out_dir / "layout_snippets.png"
        plot_layout_snippets(segments, p, allow_snippets=allow_private_snippets)
        written.append(p.name)
    if pairs:
        p = out_dir / "channel_lag.png"
        plot_channel_lag(pairs[0], p)
        written.append(p.name)
    p = out_dir / "quality_timeline.png"
    plot_quality_timeline(windows, p)
    written.append(p.name)
    return written

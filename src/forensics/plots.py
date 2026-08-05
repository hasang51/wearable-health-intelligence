"""Private diagnostic plots (matplotlib only)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from src.forensics.bit_forensics import BitForensicsAccumulator
from src.forensics.models import DecoderCandidate, PositionStat
from src.forensics.timebase import SessionTimebaseResult


def write_plots(
    plot_dir: Path,
    *,
    position_stats: list[PositionStat],
    bit_acc: BitForensicsAccumulator,
    candidates: list[DecoderCandidate],
    timebase_results: list[SessionTimebaseResult],
    max_plot_candidates: int = 5,
    allow_private_snippets: bool = False,
    snippet_series: list[tuple[str, np.ndarray]] | None = None,
) -> list[str]:
    """Write diagnostic PNGs. Returns list of filenames created."""
    plot_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    # position_range_bars
    fig, ax = plt.subplots(figsize=(10, 4))
    positions = [p.position for p in position_stats]
    widths = [p.range_width if p.range_width is not None else 0.0 for p in position_stats]
    ax.bar(positions, widths, color="#2f4f4f")
    ax.set_xlabel("position")
    ax.set_ylabel("range_width")
    ax.set_title("position_range_bars")
    fig.tight_layout()
    name = "position_range_bars.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    # byte_heatmap
    mat = bit_acc.byte_heatmap_matrix()
    fig, ax = plt.subplots(figsize=(10, 3))
    im = ax.imshow(mat, aspect="auto", interpolation="nearest")
    ax.set_yticks([0, 1, 2], labels=["A", "B", "C"])
    ax.set_xlabel("position")
    ax.set_title("byte_heatmap")
    fig.colorbar(im, ax=ax, fraction=0.02)
    fig.tight_layout()
    name = "byte_heatmap.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    # saturation_by_position
    fig, ax = plt.subplots(figsize=(10, 4))
    sats = [p.saturation_rate for p in position_stats]
    zeros = [p.zero_rate for p in position_stats]
    ax.plot(positions, sats, label="saturation_rate")
    ax.plot(positions, zeros, label="zero_rate")
    ax.set_xlabel("position")
    ax.set_ylabel("rate")
    ax.set_title("saturation_by_position")
    ax.legend()
    fig.tight_layout()
    name = "saturation_by_position.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    # candidate_score_pareto
    fig, ax = plt.subplots(figsize=(6, 5))
    xs = [c.metrics.boundary_jump_ratio for c in candidates]
    ys = [c.metrics.within_packet_deriv_mad for c in candidates]
    ranks = [c.rank for c in candidates]
    sc = ax.scatter(xs, ys, c=ranks, cmap="viridis", s=12)
    ax.set_xlabel("boundary_jump_ratio")
    ax.set_ylabel("within_packet_deriv_mad")
    ax.set_title("candidate_score_pareto")
    fig.colorbar(sc, ax=ax, label="candidate_rank")
    fig.tight_layout()
    name = "candidate_score_pareto.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    # top_candidate_boundary — hist of boundary jump ratios for top-K
    fig, ax = plt.subplots(figsize=(6, 4))
    top = candidates[: max(1, max_plot_candidates)]
    vals = [c.metrics.boundary_jump_ratio for c in top]
    labels = [f"r{c.rank}" for c in top]
    ax.bar(labels, vals, color="#355c7d")
    ax.set_xlabel("candidate_rank")
    ax.set_ylabel("boundary_jump_ratio")
    ax.set_title("top_candidate_boundary")
    if allow_private_snippets and snippet_series:
        # Optional demeaned scaled snippet inset — no absolute ADC annotation
        for label, series in snippet_series[:1]:
            if series.size:
                demeaned = series - np.mean(series)
                scale = np.max(np.abs(demeaned)) or 1.0
                ax_inset = ax.inset_axes([0.55, 0.55, 0.4, 0.4])
                ax_inset.plot(demeaned / scale, color="#11998e", linewidth=0.8)
                ax_inset.set_ylabel("transformed_units")
                ax_inset.set_title(label, fontsize=8)
                ax_inset.set_xticks([])
    fig.tight_layout()
    name = "top_candidate_boundary.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    # timebase_gap_hist
    all_deltas: list[float] = []
    for res in timebase_results:
        all_deltas.extend(res.deltas_ms)
    fig, ax = plt.subplots(figsize=(6, 4))
    if all_deltas:
        # Bucket relative classes without absolute timestamps
        buckets = []
        for d in all_deltas:
            if d < 0:
                buckets.append(0)
            elif d == 0:
                buckets.append(1)
            elif d <= 500:
                buckets.append(2)
            elif d <= 1500:
                buckets.append(3)
            elif d <= 5000:
                buckets.append(4)
            else:
                buckets.append(5)
        ax.hist(buckets, bins=np.arange(-0.5, 6.5, 1), color="#6c5b7b")
        ax.set_xticks(
            [0, 1, 2, 3, 4, 5],
            labels=["neg", "zero", "le500", "le1500", "le5s", "gt5s"],
        )
    ax.set_xlabel("delta_class")
    ax.set_ylabel("count")
    ax.set_title("timebase_gap_hist")
    fig.tight_layout()
    name = "timebase_gap_hist.png"
    fig.savefig(plot_dir / name)
    plt.close(fig)
    written.append(name)

    return written

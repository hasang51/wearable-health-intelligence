"""Phase 3 orchestration: reconstruct, analyze, write private/safe outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.audit.privacy import SCRUBBER
from src.reconstruction import __version__
from src.reconstruction.benchmark.adapter_but import BenchmarkResult, run_but_benchmark
from src.reconstruction.channel_compat import (
    ChannelCompatibilityThresholds,
    evaluate_channel_compatibility,
)
from src.reconstruction.channel_rel import match_segments_for_pairs
from src.reconstruction.layouts import (
    LAYOUT_DEFINITIONS,
    ExplicitLayout,
    layouts_algebraically_identical,
)
from src.reconstruction.metadata import analyze_all_positions, cross_session_position_stats
from src.reconstruction.models import (
    BenchmarkSummary,
    ChannelRelationshipReport,
    LayoutHypothesesReport,
    LayoutHypothesisDoc,
    MetadataPositionReport,
    Phase3Summary,
    RateGateReport,
    ReconstructionMeta,
    SpectralPlausibilityReport,
)
from src.reconstruction.payload import hypothesis_key, primary_hypotheses
from src.reconstruction.periodicity import analyze_many, segment_stability
from src.reconstruction.plots import write_plots
from src.reconstruction.quality import evaluate_segment_quality, label_counts
from src.reconstruction.rate_gates import RateGateInput, evaluate_rate_gates
from src.reconstruction.reconstruct import load_sessions, reconstruct_grid


@dataclass
class ReconstructionConfig:
    expected_payload_length: int = 66
    signedness: str = "int24"
    byte_order: str = "CAB"
    vendor_documented: bool = False
    allow_private_snippets: bool = False
    csv_field_size_limit: int = 10 * 1024 * 1024
    phase2_summary_path: str | None = None
    benchmark_dir: str | None = None
    benchmark_seed: int = 0
    workspace_root: Path | None = None
    max_grid_sessions: int | None = None  # None = all
    channel_thresholds: ChannelCompatibilityThresholds | None = None


@dataclass
class ReconstructionResult:
    meta: ReconstructionMeta
    layout_report: LayoutHypothesesReport
    metadata_report: MetadataPositionReport
    spectral_report: SpectralPlausibilityReport
    channel_report: ChannelRelationshipReport
    rate_report: RateGateReport
    summary: Phase3Summary
    benchmark: BenchmarkResult | None
    segment_rows: list[dict[str, Any]]
    quality_rows: list[dict[str, Any]]
    packet_intervals: list[float]
    gap_threshold: float
    segments_for_plots: list
    pairs_for_plots: list
    windows_for_plots: list
    metadata_records: list
    session_count: int
    packet_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_phase2_status(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("selected_status") or data.get("selectedStatus")
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _rank_candidates(
    spectral_entries: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Pick top layout/hypothesis by mean band_power_ratio among usable segments."""
    if not spectral_entries:
        return None, None
    best = max(spectral_entries, key=lambda e: e.get("mean_band_power_ratio", 0.0))
    return best.get("layout"), best.get("hypothesis_key")


def run_reconstruction(input_path: str | Path, config: ReconstructionConfig) -> ReconstructionResult:
    sessions = load_sessions(
        str(input_path),
        signedness=config.signedness,
        byte_order=config.byte_order,
        expected_payload_length=config.expected_payload_length,
        csv_field_size_limit=config.csv_field_size_limit,
    )
    if config.max_grid_sessions is not None:
        sessions = sessions[: config.max_grid_sessions]

    packet_count = sum(len(s.transformed_payloads) for s in sessions)
    meta = ReconstructionMeta(
        session_count=len(sessions),
        packet_count=packet_count,
        generated_at=_utc_now(),
        tool_version=__version__,
        expected_payload_length=config.expected_payload_length,
        signedness=config.signedness,
        byte_order=config.byte_order,
        vendor_documented=config.vendor_documented,
    )

    # Layout documentation
    identity = layouts_algebraically_identical(config.expected_payload_length, 2)
    layout_docs = [
        LayoutHypothesisDoc(
            layout_id=lid,
            rule=info["rule"],
            phase2_equivalent=info["phase2_equivalent"],
            algebraic_identity_notes=identity,
        )
        for lid, info in LAYOUT_DEFINITIONS.items()
    ]
    layout_report = LayoutHypothesesReport(
        meta=meta,
        layouts=layout_docs,
        payload_length=config.expected_payload_length,
        evaluated_channel_counts=[2, 3],
    )

    # Metadata analysis on raw (pre-transform) integers across all packets
    all_raw: list[list[int]] = []
    all_ts: list[int] = []
    session_mats = []
    for s in sessions:
        all_raw.extend(s.raw_payloads)
        all_ts.extend(s.timestamps_ms)
        if s.raw_payloads:
            import numpy as np

            session_mats.append(np.asarray(s.raw_payloads, dtype=np.int64))
    meta_records = analyze_all_positions(
        all_raw,
        timestamps_ms=all_ts if len(all_ts) == len(all_raw) else None,
        session_matrices=session_mats or None,
    )
    # Tag proposed exclusions with explicit hypothesis note
    for rec in meta_records:
        if rec.decision == "propose_exclude":
            rec.hypothesis_id = "detector_proposal"
            rec.reasons = list(rec.reasons) + ["explicit_score_reason_required"]

    raw_cs, robust_cs = cross_session_position_stats([s.raw_payloads for s in sessions])
    metadata_report = MetadataPositionReport(
        meta=meta,
        positions=meta_records,
        proposed_exclusions=[r for r in meta_records if r.decision == "propose_exclude"],
    )

    # Reconstruction grid
    candidates = reconstruct_grid(sessions)
    all_segments = []
    for cand in candidates:
        all_segments.extend(cand.segments)

    periodicity = analyze_many(all_segments)
    pairs = match_segments_for_pairs(all_segments)

    # Aggregate spectral by layout+hypothesis
    from collections import defaultdict

    buckets: dict[tuple[str, str], list] = defaultdict(list)
    for pr in periodicity:
        buckets[(pr.layout, pr.hypothesis_key)].append(pr)
    spectral_entries = []
    for (layout, hkey), group in buckets.items():
        stab = segment_stability(group)
        spectral_entries.append(
            {
                "layout": layout,
                "hypothesis_key": hkey,
                "n_segments": len(group),
                "mean_band_power_ratio": float(
                    sum(g.band_power_ratio for g in group) / max(len(group), 1)
                ),
                "mean_acf_peak": float(
                    sum(g.acf_peak_value for g in group) / max(len(group), 1)
                ),
                "usable_fraction": float(sum(1 for g in group if g.usable) / max(len(group), 1)),
                "dom_freq_stability": stab,
                "cross_session_consistency_raw_mean": raw_cs.get("mean", 0.0),
                "cross_session_consistency_robust_mean": robust_cs.get("mean", 0.0),
            }
        )
    spectral_report = SpectralPlausibilityReport(meta=meta, candidates=spectral_entries)

    channel_report = ChannelRelationshipReport(
        meta=meta,
        pairs=[
            {
                "session_ordinal": p.session_ordinal,
                "channel_a": p.channel_a,
                "channel_b": p.channel_b,
                "layout": p.layout,
                "hypothesis_key": p.hypothesis_key,
                "zero_lag_corr": p.zero_lag_corr,
                "max_abs_xcorr": p.max_abs_xcorr,
                "best_lag_samples": p.best_lag_samples,
                "best_lag_ms": p.best_lag_ms,
                "mean_coherence_band": p.mean_coherence_band,
                "dom_freq_agreement": p.dom_freq_agreement,
                "dom_freq_rel_diff": p.dom_freq_rel_diff,
                "correlation_computed": p.correlation_computed,
                "coherence_computed": p.coherence_computed,
                "reason_codes": p.reason_codes,
            }
            for p in pairs
        ],
    )

    # Quality windows
    per_map = {r.segment_id: r for r in periodicity}
    # Map pairs by segment packet range roughly via first matching pair per layout/hyp/session
    windows = []
    for seg in all_segments:
        pair = next(
            (
                p
                for p in pairs
                if p.session_ordinal == seg.session_ordinal
                and p.layout == seg.layout
                and p.hypothesis_key == seg.hypothesis_key
            ),
            None,
        )
        windows.extend(
            evaluate_segment_quality(seg, periodicity=per_map.get(seg.segment_id), pair=pair)
        )
    qcounts = label_counts(windows)

    top_layout, top_hyp = _rank_candidates(spectral_entries)

    # Channel compatibility: selected best hypothesis only (never pool alternatives)
    channel_thresholds = config.channel_thresholds or ChannelCompatibilityThresholds()
    channel_compat = evaluate_channel_compatibility(
        pairs,
        layout=top_layout,
        hypothesis_key=top_hyp,
        thresholds=channel_thresholds,
        filter_to_selected=True,
    )

    # Benchmark (optional)
    bench: BenchmarkResult | None = None
    if config.benchmark_dir:
        bench = run_but_benchmark(
            config.benchmark_dir,
            seed=config.benchmark_seed,
            workspace_root=config.workspace_root,
        )

    decoder_status = _read_phase2_status(config.phase2_summary_path)
    gate_inp = RateGateInput(
        decoder_status=decoder_status,
        public_good_median_abs_hr_error=(
            bench.hr_median_abs_error if bench and bench.ran else None
        ),
        public_good_coverage=bench.hr_coverage if bench and bench.ran else None,
        channel_pairs=pairs,
        periodicity=periodicity,
        selected_layout=top_layout,
        selected_hypothesis_key=top_hyp,
        channel_thresholds=channel_thresholds,
        channel_compatibility=channel_compat,
    )
    gate = evaluate_rate_gates(gate_inp)
    rate_report = RateGateReport(
        meta=meta,
        rate_status=gate.rate_status,
        failed_gates=gate.failed_gates,
        passed_gates=gate.passed_gates,
        candidate_pulse_rate_bpm=gate.candidate_pulse_rate_bpm,
        decoder_status=decoder_status,
        notes=gate.notes,
        channel_compatibility=gate.channel_compatibility or channel_compat,
        channels_compatible=None,
    )

    rationale = [
        "phase3_candidate_reconstruction_only",
        "not_validated_physiological_ppg",
        "no_default_vitals",
        "channel_compatibility_multi_metric_aggregate",
        "existential_channels_compatible_gate_removed",
    ]
    if identity.get("interleaved_local_eq_continuous"):
        rationale.append("interleaved_layouts_algebraically_identical_for_L_mod_C_0")

    summary = Phase3Summary(
        meta=meta,
        top_layout=top_layout,
        top_hypothesis=top_hyp,
        quality_label_counts=qcounts,
        rate_status=gate.rate_status,
        channel_compatibility=channel_compat,
        layouts_algebraically_identical=identity,
        rationale_codes=rationale,
        extra={
            "primary_hypotheses": [hypothesis_key(h) for h in primary_hypotheses()],
            "layouts_evaluated": [e.value for e in ExplicitLayout],
            "metadata_propose_exclude_count": len(metadata_report.proposed_exclusions),
            "cross_session_consistency_raw_mean": raw_cs.get("mean", 0.0),
            "cross_session_consistency_robust_mean": robust_cs.get("mean", 0.0),
            "benchmark_ran": bool(bench and bench.ran),
        },
    )

    segment_rows = [
        {
            "segment_id": s.segment_id,
            "session_ordinal": s.session_ordinal,
            "channel": s.channel,
            "layout": s.layout,
            "hypothesis_key": s.hypothesis_key,
            "relative_t_ms": float(t),
            "value": float(v),
            "fs_hz": s.fs_hz,
            "packet_start": s.packet_start,
            "packet_end": s.packet_end,
        }
        for s in all_segments
        for t, v in zip(s.relative_times_ms.tolist(), s.values.tolist())
    ]
    quality_rows = [
        {
            "window_id": w.window_id,
            "segment_id": w.segment_id,
            "session_ordinal": w.session_ordinal,
            "channel": w.channel,
            "layout": w.layout,
            "hypothesis_key": w.hypothesis_key,
            "start_idx": w.start_idx,
            "end_idx": w.end_idx,
            "score": w.score,
            "label": w.label.value,
            "reason_codes": json.dumps(w.reason_codes),
            "flatline_rate": w.flatline_rate,
            "clip_rate": w.clip_rate,
            "band_power_ratio": w.band_power_ratio,
            "acf_peak_value": w.acf_peak_value,
        }
        for w in windows
    ]

    # Packet intervals for plots (first session)
    packet_intervals: list[float] = []
    gap_thr = 1500.0
    if sessions and len(sessions[0].timestamps_ms) >= 2:
        ts = sessions[0].timestamps_ms
        packet_intervals = [float(ts[i + 1] - ts[i]) for i in range(len(ts) - 1)]
        from src.reconstruction.timebase import gap_threshold_ms, median_positive_delta

        gap_thr = gap_threshold_ms(median_positive_delta(ts))

    return ReconstructionResult(
        meta=meta,
        layout_report=layout_report,
        metadata_report=metadata_report,
        spectral_report=spectral_report,
        channel_report=channel_report,
        rate_report=rate_report,
        summary=summary,
        benchmark=bench,
        segment_rows=segment_rows,
        quality_rows=quality_rows,
        packet_intervals=packet_intervals,
        gap_threshold=gap_thr,
        segments_for_plots=all_segments,
        pairs_for_plots=pairs,
        windows_for_plots=windows,
        metadata_records=meta_records,
        session_count=len(sessions),
        packet_count=packet_count,
    )


def _write_json(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(model, "model_dump"):
        text = json.dumps(model.model_dump(mode="json"), indent=2)
    else:
        text = json.dumps(model, indent=2)
    path.write_text(SCRUBBER.scrub(text), encoding="utf-8")


def _decoder_refinement_md(result: ReconstructionResult) -> str:
    s = result.summary
    cc = s.channel_compatibility
    lines = [
        "# Decoder Refinement (Phase 3)",
        "",
        "Research-only candidate reconstruction. Does **not** validate physiological PPG.",
        "",
        f"- Top layout (by spectral band ratio): `{s.top_layout}`",
        f"- Top hypothesis: `{s.top_hypothesis}`",
        f"- Rate status: `{s.rate_status.value}`",
        f"- Algebraic identity (L%C==0): `{s.layouts_algebraically_identical}`",
        "",
        "## Channel compatibility (selected best hypothesis only)",
        "",
    ]
    if cc is None:
        lines.append("- Channel compatibility: not evaluated")
    else:
        lines.extend(
            [
                f"- Verdict: `{cc.verdict.value}`",
                f"- Evaluable pairs: `{cc.evaluable_pairs}` / `{cc.total_pairs}` "
                f"(fraction `{cc.evaluable_fraction:.3f}`)",
                f"- Frequency agreement: `{cc.frequency_agreeing_pairs}` / "
                f"`{cc.frequency_evaluable_pairs}` "
                f"(fraction `{cc.frequency_agreement_fraction}`)",
                f"- Median |zero-lag corr|: `{cc.median_abs_zero_lag_correlation}`",
                f"- Median max |lagged corr|: `{cc.median_max_abs_lagged_correlation}`",
                f"- Median coherence: `{cc.median_coherence}`",
                f"- Median best lag (samples): `{cc.median_best_lag_samples}`",
                f"- Best-lag IQR (samples): `{cc.best_lag_iqr_samples}`",
                f"- Failed criteria: `{cc.failed_criteria}`",
                f"- Thresholds: `{cc.thresholds_used}`",
                "",
                "The obsolete existential gate label `channels_compatible` was removed. "
                "Only `channel_agreement_compatible` may pass the proprietary rate channel gate, "
                "and only for verdict `COMPATIBLE`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Layouts",
            "",
        ]
    )
    for lay in result.layout_report.layouts:
        lines.append(f"- `{lay.layout_id}`: {lay.rule} (Phase2: {lay.phase2_equivalent})")
    lines.extend(
        [
            "",
            "## Rationale codes",
            "",
        ]
    )
    for code in s.rationale_codes:
        lines.append(f"- `{code}`")
    lines.extend(
        [
            "",
            "## Metadata",
            "",
            f"- Proposed exclusions (detector only): {len(result.metadata_report.proposed_exclusions)}",
            "- No position is silently removed; active exclusions require an explicit payload hypothesis.",
            "",
        ]
    )
    return SCRUBBER.scrub("\n".join(lines))


def _research_limitations_md(result: ReconstructionResult) -> str:
    lines = [
        "# Research Limitations (Phase 3)",
        "",
        "- Candidate streams are **not** validated PPG waveforms.",
        "- Implied sampling rates depend on unproven samples-per-packet hypotheses.",
        "- Spectral Hz axes are conditional on those hypotheses (`unverified_implied_rate`).",
        "- Quality label `plausible_candidate_signal` is research-only, not a clinical claim.",
        "- Proprietary pulse rate is gated and fail-closed; never named heart rate unless gates pass.",
        "- Decoder status is never upgraded to ACCEPTED by Phase 3 without vendor/reference evidence.",
        "- Public BUT benchmark performance does not prove proprietary decoder correctness.",
        "- NeuroKit2 (optional) is comparison-only and never decoder ground truth.",
        "- Safe reports contain no raw samples, identifiers, exact timestamps, or sensitive paths.",
        "- Safe channel evidence is aggregate-only (verdict, counts, fractions, medians, thresholds); "
        "no per-pair raw values.",
        "",
        "## Channel-compatibility gate migration",
        "",
        "- The previous existential rule (`any` pair with `dom_freq_agreement` ⇒ "
        "`channels_compatible`) was scientifically invalid: a single agreeing pair among many "
        "disagreeing pairs could unlock the proprietary channel gate.",
        "- Channel compatibility is now a structured multi-metric aggregate evaluated **only** on "
        "the selected best proprietary hypothesis (selected decoder context / layout / payload "
        "hypothesis). Alternative hypotheses cannot force a pass.",
        "- Required evidence includes evaluable-pair coverage, dominant-frequency agreement "
        "fraction, median max absolute lagged correlation, and median coherence, with "
        "conservative research thresholds. Missing metrics fail closed and never improve the "
        "verdict.",
        "- Verdicts: `COMPATIBLE`, `PARTIALLY_COMPATIBLE`, `INSUFFICIENT_CHANNEL_AGREEMENT`, "
        "`NOT_EVALUABLE`. Only `COMPATIBLE` may pass the channel rate gate "
        "(`channel_agreement_compatible`). Partial / insufficient / not-evaluable keep "
        "proprietary rate status `NOT_COMPUTED`.",
        "- This change cannot unlock proprietary pulse-rate computation by itself: public "
        "benchmark MAE/coverage, decoder status, and spectral/time agreement gates remain "
        "fail-closed.",
        "",
        "## Privacy posture",
        "",
    ]
    for p in result.summary.privacy_posture:
        lines.append(f"- `{p}`")
    return SCRUBBER.scrub("\n".join(lines))


def write_outputs(
    result: ReconstructionResult,
    private_dir: str | Path,
    safe_dir: str | Path,
    config: ReconstructionConfig,
) -> None:
    priv = Path(private_dir)
    safe = Path(safe_dir)
    priv.mkdir(parents=True, exist_ok=True)
    safe.mkdir(parents=True, exist_ok=True)

    _write_json(priv / "layout_hypotheses.json", result.layout_report)
    _write_json(priv / "metadata_position_analysis.json", result.metadata_report)
    _write_json(priv / "spectral_plausibility.json", result.spectral_report)
    _write_json(priv / "channel_relationship.json", result.channel_report)
    _write_json(priv / "rate_gate.json", result.rate_report)

    # Parquet private streams
    if result.segment_rows:
        pd.DataFrame(result.segment_rows).to_parquet(
            priv / "reconstructed_candidate_segments.parquet", index=False
        )
    else:
        pd.DataFrame(
            columns=[
                "segment_id",
                "session_ordinal",
                "channel",
                "layout",
                "hypothesis_key",
                "relative_t_ms",
                "value",
                "fs_hz",
                "packet_start",
                "packet_end",
            ]
        ).to_parquet(priv / "reconstructed_candidate_segments.parquet", index=False)

    if result.quality_rows:
        pd.DataFrame(result.quality_rows).to_parquet(
            priv / "candidate_quality_windows.parquet", index=False
        )
    else:
        pd.DataFrame(columns=["window_id", "label", "score"]).to_parquet(
            priv / "candidate_quality_windows.parquet", index=False
        )

    if result.benchmark is not None:
        bench_private = {
            "ran": result.benchmark.ran,
            "seed": result.benchmark.seed,
            "record_count": result.benchmark.record_count,
            "subject_count": result.benchmark.subject_count,
            "quality_balanced_accuracy": result.benchmark.quality_balanced_accuracy,
            "quality_precision": result.benchmark.quality_precision,
            "quality_recall": result.benchmark.quality_recall,
            "quality_f1": result.benchmark.quality_f1,
            "hr_coverage": result.benchmark.hr_coverage,
            "hr_mae": result.benchmark.hr_mae,
            "hr_median_abs_error": result.benchmark.hr_median_abs_error,
            "hr_bias": result.benchmark.hr_bias,
            "selected_record_hashes": result.benchmark.selected_record_hashes,
            "notes": result.benchmark.notes,
            "private_detail": result.benchmark.private_detail,
        }
        _write_json(priv / "benchmark_results.json", bench_private)
    else:
        _write_json(priv / "benchmark_results.json", {"ran": False, "notes": ["benchmark_not_run"]})

    plots_dir = priv / "plots"
    write_plots(
        plots_dir,
        metadata_records=result.metadata_records,
        packet_intervals=result.packet_intervals,
        gap_threshold=result.gap_threshold,
        segments=result.segments_for_plots,
        pairs=result.pairs_for_plots,
        windows=result.windows_for_plots,
        allow_private_snippets=config.allow_private_snippets,
    )

    # Safe outputs
    _write_json(safe / "phase3_summary.json", result.summary)
    (safe / "decoder_refinement.md").write_text(_decoder_refinement_md(result), encoding="utf-8")
    (safe / "research_limitations.md").write_text(
        _research_limitations_md(result), encoding="utf-8"
    )

    if result.benchmark is not None and result.benchmark.ran:
        bench_safe = BenchmarkSummary(
            ran=True,
            seed=result.benchmark.seed,
            record_count=result.benchmark.record_count,
            subject_count=result.benchmark.subject_count,
            quality_balanced_accuracy=result.benchmark.quality_balanced_accuracy,
            quality_precision=result.benchmark.quality_precision,
            quality_recall=result.benchmark.quality_recall,
            quality_f1=result.benchmark.quality_f1,
            hr_coverage=result.benchmark.hr_coverage,
            hr_mae=result.benchmark.hr_mae,
            hr_median_abs_error=result.benchmark.hr_median_abs_error,
            hr_bias=result.benchmark.hr_bias,
            notes=list(result.benchmark.notes),
        )
    else:
        bench_safe = BenchmarkSummary(ran=False, notes=["benchmark_not_run"])
    _write_json(safe / "benchmark_summary.json", bench_safe)

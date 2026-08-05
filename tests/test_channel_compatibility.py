"""Channel-compatibility multi-metric verdict and rate-gate integration."""

from __future__ import annotations

import json
from pathlib import Path

from src.reconstruction.channel_compat import (
    ChannelCompatibilityThresholds,
    decide_channel_compatibility,
    evaluate_channel_compatibility,
)
from src.reconstruction.channel_rel import ChannelPairResult
from src.reconstruction.models import ChannelCompatibilityVerdict, RateStatus
from src.reconstruction.rate_gates import RateGateInput, evaluate_rate_gates
from src.reconstruction.reports import (
    ReconstructionConfig,
    ReconstructionResult,
    _decoder_refinement_md,
    _research_limitations_md,
    write_outputs,
)
from src.reconstruction.models import (
    ChannelRelationshipReport,
    LayoutHypothesesReport,
    MetadataPositionReport,
    Phase3Summary,
    RateGateReport,
    ReconstructionMeta,
    SpectralPlausibilityReport,
)


def _pair(
    *,
    layout: str = "BEST_LAYOUT",
    hypothesis_key: str = "BEST_HYP",
    dom_freq_agreement: bool = False,
    zero_lag_corr: float = 0.0,
    max_abs_xcorr: float = 0.0,
    mean_coherence_band: float = 0.0,
    best_lag_samples: int = 0,
    correlation_computed: bool = True,
    coherence_computed: bool = True,
    reason_codes: list[str] | None = None,
    dom_freq_a_hz: float | None = 1.0,
    dom_freq_b_hz: float | None = 1.0,
    session_ordinal: int = 0,
    channel_a: int = 0,
    channel_b: int = 1,
) -> ChannelPairResult:
    if dom_freq_agreement and dom_freq_a_hz is not None and dom_freq_b_hz is not None:
        dom_freq_b_hz = dom_freq_a_hz
    elif (
        not dom_freq_agreement
        and dom_freq_a_hz is not None
        and dom_freq_b_hz is not None
        and dom_freq_a_hz == dom_freq_b_hz
    ):
        dom_freq_b_hz = dom_freq_a_hz * 1.5
    return ChannelPairResult(
        session_ordinal=session_ordinal,
        channel_a=channel_a,
        channel_b=channel_b,
        layout=layout,
        hypothesis_key=hypothesis_key,
        zero_lag_corr=zero_lag_corr,
        max_abs_xcorr=max_abs_xcorr,
        best_lag_samples=best_lag_samples,
        mean_coherence_band=mean_coherence_band,
        dom_freq_a_hz=dom_freq_a_hz,
        dom_freq_b_hz=dom_freq_b_hz,
        dom_freq_agreement=dom_freq_agreement,
        correlation_computed=correlation_computed,
        coherence_computed=coherence_computed,
        reason_codes=list(reason_codes or []),
    )


def test_a_one_agreeing_pair_among_many_is_insufficient():
    pairs = [_pair(dom_freq_agreement=False, max_abs_xcorr=0.1, mean_coherence_band=0.05) for _ in range(19)]
    pairs.append(
        _pair(
            dom_freq_agreement=True,
            max_abs_xcorr=0.9,
            mean_coherence_band=0.8,
            channel_a=0,
            channel_b=2,
        )
    )
    summary = evaluate_channel_compatibility(
        pairs,
        layout="BEST_LAYOUT",
        hypothesis_key="BEST_HYP",
    )
    assert summary.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT
    assert summary.frequency_agreeing_pairs == 1
    assert summary.frequency_evaluable_pairs == 20


def test_b_real_data_aggregates_insufficient():
    # 18/37 ≈ 0.486, median lagged 0.205, median coherence 0.075
    summary = decide_channel_compatibility(
        total_pairs=37,
        evaluable_pairs=37,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=37,
        frequency_agreeing_pairs=18,
        frequency_agreement_fraction=18 / 37,
        median_abs_zero_lag_correlation=0.008,
        median_max_abs_lagged_correlation=0.205,
        median_coherence=0.075,
        median_best_lag_samples=12.0,
        best_lag_iqr_samples=5.0,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT


def test_c_compatible_thresholds():
    summary = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=20,
        frequency_agreeing_pairs=15,
        frequency_agreement_fraction=0.75,
        median_max_abs_lagged_correlation=0.40,
        median_coherence=0.30,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.COMPATIBLE


def test_d_partially_compatible():
    summary = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=20,
        frequency_agreeing_pairs=11,
        frequency_agreement_fraction=0.55,
        median_max_abs_lagged_correlation=0.28,
        median_coherence=0.08,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE


def test_e_partial_freq_but_weak_corr_and_coherence_insufficient():
    summary = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=20,
        frequency_agreeing_pairs=11,
        frequency_agreement_fraction=0.55,
        median_max_abs_lagged_correlation=0.20,
        median_coherence=0.05,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT


def test_f_too_few_evaluable_pairs_not_evaluable():
    summary = decide_channel_compatibility(
        total_pairs=8,
        evaluable_pairs=8,
        evaluable_fraction=1.0,
        frequency_agreement_fraction=0.9,
        median_max_abs_lagged_correlation=0.5,
        median_coherence=0.4,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.NOT_EVALUABLE


def test_g_many_non_evaluable_but_enough_evaluable_uses_evaluable_data():
    pairs: list[ChannelPairResult] = []
    # Non-evaluable pairs are counted but must not force NOT_EVALUABLE when
    # enough evaluable pairs remain and evaluable_fraction meets the threshold.
    for i in range(8):
        pairs.append(
            _pair(
                reason_codes=["too_short"],
                correlation_computed=False,
                coherence_computed=False,
                dom_freq_a_hz=None,
                dom_freq_b_hz=None,
                channel_a=i,
                channel_b=i + 100,
            )
        )
    for i in range(12):
        pairs.append(
            _pair(
                dom_freq_agreement=True,
                max_abs_xcorr=0.45,
                mean_coherence_band=0.35,
                channel_a=i,
                channel_b=i + 200,
            )
        )
    summary = evaluate_channel_compatibility(
        pairs, layout="BEST_LAYOUT", hypothesis_key="BEST_HYP"
    )
    assert summary.total_pairs == 20
    assert summary.evaluable_pairs == 12
    assert summary.evaluable_fraction == 0.6
    assert summary.non_evaluable_reasons.get("too_short", 0) == 8
    assert summary.frequency_agreeing_pairs == 12
    assert summary.verdict == ChannelCompatibilityVerdict.COMPATIBLE
    assert summary.verdict != ChannelCompatibilityVerdict.NOT_EVALUABLE


def test_h_missing_coherence_cannot_reach_compatible():
    summary = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=20,
        frequency_agreeing_pairs=16,
        frequency_agreement_fraction=0.80,
        median_max_abs_lagged_correlation=0.50,
        median_coherence=None,
    )
    assert summary.verdict != ChannelCompatibilityVerdict.COMPATIBLE
    assert "compatible_median_coherence" in summary.failed_criteria


def test_i_alternative_hypothesis_agreeing_pairs_ignored():
    selected = [
        _pair(
            layout="BEST_LAYOUT",
            hypothesis_key="BEST_HYP",
            dom_freq_agreement=False,
            max_abs_xcorr=0.1,
            mean_coherence_band=0.05,
            channel_a=i,
            channel_b=i + 10,
        )
        for i in range(15)
    ]
    alternatives = [
        _pair(
            layout="OTHER_LAYOUT",
            hypothesis_key="OTHER_HYP",
            dom_freq_agreement=True,
            max_abs_xcorr=0.9,
            mean_coherence_band=0.8,
            channel_a=i,
            channel_b=i + 20,
        )
        for i in range(20)
    ]
    summary = evaluate_channel_compatibility(
        selected + alternatives,
        layout="BEST_LAYOUT",
        hypothesis_key="BEST_HYP",
    )
    assert summary.total_pairs == 15
    assert summary.frequency_agreeing_pairs == 0
    assert summary.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT


def _rate_gate_for_verdict(verdict: ChannelCompatibilityVerdict) -> object:
    metrics = {
        ChannelCompatibilityVerdict.COMPATIBLE: dict(
            frequency_agreement_fraction=0.75,
            median_max_abs_lagged_correlation=0.40,
            median_coherence=0.30,
        ),
        ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE: dict(
            frequency_agreement_fraction=0.55,
            median_max_abs_lagged_correlation=0.28,
            median_coherence=0.08,
        ),
        ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT: dict(
            frequency_agreement_fraction=18 / 37,
            median_max_abs_lagged_correlation=0.205,
            median_coherence=0.075,
        ),
        ChannelCompatibilityVerdict.NOT_EVALUABLE: dict(
            evaluable_pairs=3,
            evaluable_fraction=0.3,
            frequency_agreement_fraction=0.9,
            median_max_abs_lagged_correlation=0.5,
            median_coherence=0.4,
        ),
    }
    base = dict(
        total_pairs=37,
        evaluable_pairs=37,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=37,
        frequency_agreeing_pairs=18,
    )
    base.update(metrics[verdict])
    if verdict == ChannelCompatibilityVerdict.NOT_EVALUABLE:
        base["total_pairs"] = 10
        base["frequency_evaluable_pairs"] = 3
        base["frequency_agreeing_pairs"] = 3
    summary = decide_channel_compatibility(**base)
    assert summary.verdict == verdict
    return evaluate_rate_gates(
        RateGateInput(
            decoder_status="PROVISIONALLY_ACCEPTED",
            public_good_median_abs_hr_error=3.0,
            public_good_coverage=0.9,
            spectral_rate_bpm=70.0,
            time_domain_rate_bpm=71.0,
            channel_compatibility=summary,
            selected_layout="BEST_LAYOUT",
            selected_hypothesis_key="BEST_HYP",
        )
    )


def test_j_rate_not_computed_for_non_compatible_verdicts():
    for verdict in (
        ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE,
        ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT,
        ChannelCompatibilityVerdict.NOT_EVALUABLE,
    ):
        result = _rate_gate_for_verdict(verdict)
        assert result.rate_status == RateStatus.NOT_COMPUTED
        assert "channels_compatible" not in result.passed_gates
        assert "channel_agreement_compatible" not in result.passed_gates

    partial = _rate_gate_for_verdict(ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE)
    assert "channel_agreement_partial_only" in partial.failed_gates
    insuff = _rate_gate_for_verdict(ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT)
    assert "channel_agreement_insufficient" in insuff.failed_gates
    missing = _rate_gate_for_verdict(ChannelCompatibilityVerdict.NOT_EVALUABLE)
    assert "channel_agreement_not_evaluable" in missing.failed_gates


def test_compatible_gate_label_is_channel_agreement_compatible():
    result = _rate_gate_for_verdict(ChannelCompatibilityVerdict.COMPATIBLE)
    assert "channel_agreement_compatible" in result.passed_gates
    assert "channels_compatible" not in result.passed_gates


def test_k_safe_report_has_no_per_pair_or_privacy_leak(tmp_path: Path):
    meta = ReconstructionMeta(
        session_count=1,
        packet_count=1,
        generated_at="2026-01-01T00:00:00Z",
        tool_version="test",
    )
    cc = decide_channel_compatibility(
        total_pairs=37,
        evaluable_pairs=37,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=37,
        frequency_agreeing_pairs=18,
        frequency_agreement_fraction=18 / 37,
        median_abs_zero_lag_correlation=0.008,
        median_max_abs_lagged_correlation=0.205,
        median_coherence=0.075,
        median_best_lag_samples=12.0,
        best_lag_iqr_samples=4.0,
    )
    summary = Phase3Summary(
        meta=meta,
        top_layout="BEST_LAYOUT",
        top_hypothesis="BEST_HYP",
        rate_status=RateStatus.NOT_COMPUTED,
        channel_compatibility=cc,
        rationale_codes=["existential_channels_compatible_gate_removed"],
    )
    result = ReconstructionResult(
        meta=meta,
        layout_report=LayoutHypothesesReport(meta=meta, layouts=[]),
        metadata_report=MetadataPositionReport(meta=meta, positions=[]),
        spectral_report=SpectralPlausibilityReport(meta=meta),
        channel_report=ChannelRelationshipReport(
            meta=meta,
            pairs=[
                {
                    "session_ordinal": 0,
                    "zero_lag_corr": 0.99,
                    "raw_samples": [1, 2, 3],
                    "path": "C:/secret/patient.csv",
                }
            ],
        ),
        rate_report=RateGateReport(
            meta=meta,
            rate_status=RateStatus.NOT_COMPUTED,
            failed_gates=["channel_agreement_insufficient"],
            channel_compatibility=cc,
            channels_compatible=None,
        ),
        summary=summary,
        benchmark=None,
        segment_rows=[],
        quality_rows=[],
        packet_intervals=[],
        gap_threshold=1500.0,
        segments_for_plots=[],
        pairs_for_plots=[],
        windows_for_plots=[],
        metadata_records=[],
        session_count=1,
        packet_count=1,
    )
    priv = tmp_path / "priv"
    safe = tmp_path / "safe"
    write_outputs(result, priv, safe, ReconstructionConfig())

    safe_summary = json.loads((safe / "phase3_summary.json").read_text(encoding="utf-8"))
    assert safe_summary["rate_status"] == "NOT_COMPUTED"
    assert safe_summary["channel_compatibility"]["verdict"] == "INSUFFICIENT_CHANNEL_AGREEMENT"
    assert "pairs" not in safe_summary["channel_compatibility"]
    cc_keys = set(safe_summary["channel_compatibility"].keys())
    forbidden_pair_fields = {
        "zero_lag_corr",
        "max_abs_xcorr",
        "mean_coherence_band",
        "dom_freq_a_hz",
        "dom_freq_b_hz",
        "session_ordinal",
        "channel_a",
        "channel_b",
        "raw_samples",
    }
    assert forbidden_pair_fields.isdisjoint(cc_keys)
    blob = (safe / "phase3_summary.json").read_text(encoding="utf-8")
    blob += (safe / "decoder_refinement.md").read_text(encoding="utf-8")
    blob += (safe / "research_limitations.md").read_text(encoding="utf-8")
    assert "raw_samples" not in blob
    assert "patient.csv" not in blob
    assert "C:/secret" not in blob
    md = _decoder_refinement_md(result) + _research_limitations_md(result)
    assert "INSUFFICIENT_CHANNEL_AGREEMENT" in md
    assert "existential" in md.lower() or "channels_compatible" in md
    assert "session_ordinal" not in (safe / "phase3_summary.json").read_text(encoding="utf-8")


def test_thresholds_are_configurable():
    thr = ChannelCompatibilityThresholds(
        compatible_min_frequency_agreement=0.40,
        compatible_min_median_lagged_correlation=0.15,
        compatible_min_median_coherence=0.05,
    )
    summary = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_agreement_fraction=0.45,
        median_max_abs_lagged_correlation=0.20,
        median_coherence=0.08,
        thresholds=thr,
    )
    assert summary.verdict == ChannelCompatibilityVerdict.COMPATIBLE

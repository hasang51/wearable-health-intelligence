"""Conditional proprietary candidate pulse-rate gates."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.forensics.models import DecoderStatus
from src.reconstruction.channel_compat import (
    ChannelCompatibilityThresholds,
    evaluate_channel_compatibility,
)
from src.reconstruction.channel_rel import ChannelPairResult
from src.reconstruction.models import (
    ChannelCompatibilitySummary,
    ChannelCompatibilityVerdict,
    RateStatus,
)
from src.reconstruction.periodicity import PeriodicityResult

PROVISIONAL_STATUSES = {
    DecoderStatus.PROVISIONALLY_ACCEPTED.value,
    DecoderStatus.ACCEPTED.value,
    "PROVISIONALLY_ACCEPTED",
    "ACCEPTED",
}

# Obsolete existential gate label — must not be reintroduced.
_DEPRECATED_CHANNELS_COMPATIBLE = "channels_compatible"


@dataclass
class RateGateInput:
    decoder_status: str | None
    public_good_median_abs_hr_error: float | None = None
    public_good_coverage: float | None = None
    spectral_rate_bpm: float | None = None
    time_domain_rate_bpm: float | None = None
    channel_pairs: list[ChannelPairResult] = field(default_factory=list)
    periodicity: list[PeriodicityResult] = field(default_factory=list)
    agreement_tolerance_bpm: float = 5.0
    selected_layout: str | None = None
    selected_hypothesis_key: str | None = None
    channel_thresholds: ChannelCompatibilityThresholds | None = None
    channel_compatibility: ChannelCompatibilitySummary | None = None


@dataclass
class RateGateResult:
    rate_status: RateStatus
    failed_gates: list[str] = field(default_factory=list)
    passed_gates: list[str] = field(default_factory=list)
    candidate_pulse_rate_bpm: float | None = None
    notes: list[str] = field(default_factory=list)
    channel_compatibility: ChannelCompatibilitySummary | None = None


def _rates_from_periodicity(results: list[PeriodicityResult]) -> tuple[float | None, float | None]:
    """Spectral rate from dom-freq; time-domain from ACF peak lag."""
    spec = []
    time_r = []
    for r in results:
        if r.dominant_frequency_hz and r.dominant_frequency_hz > 0:
            spec.append(r.dominant_frequency_hz * 60.0)
        if r.acf_peak_lag_s and r.acf_peak_lag_s > 0:
            time_r.append(60.0 / r.acf_peak_lag_s)
    s = float(sum(spec) / len(spec)) if spec else None
    t = float(sum(time_r) / len(time_r)) if time_r else None
    return s, t


def _apply_channel_compatibility_gate(
    summary: ChannelCompatibilitySummary,
    failed: list[str],
    passed: list[str],
) -> None:
    """Map structured channel verdict onto fail-closed rate-gate labels."""
    if summary.verdict == ChannelCompatibilityVerdict.COMPATIBLE:
        passed.append("channel_agreement_compatible")
        return
    if summary.verdict == ChannelCompatibilityVerdict.PARTIALLY_COMPATIBLE:
        failed.append("channel_agreement_partial_only")
        return
    if summary.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT:
        failed.append("channel_agreement_insufficient")
        return
    failed.append("channel_agreement_not_evaluable")


def evaluate_rate_gates(inp: RateGateInput) -> RateGateResult:
    """Fail-closed: any missing gate => NOT_COMPUTED; method disagreement separate."""
    failed: list[str] = []
    passed: list[str] = []
    notes: list[str] = [
        "proprietary_candidate_pulse_rate_only",
        "not_heart_rate_unless_gates_pass",
        "never_upgrade_decoder_to_accepted_here",
        "channel_gate_requires_multi_metric_aggregate",
        "deprecated_gate_label_channels_compatible_removed",
    ]

    status = inp.decoder_status
    if status is None or status not in PROVISIONAL_STATUSES:
        failed.append("decoder_status_insufficient")
    else:
        passed.append("decoder_status_ok")

    if inp.public_good_median_abs_hr_error is None or inp.public_good_median_abs_hr_error > 5.0:
        failed.append("public_median_abs_hr_error_gate")
    else:
        passed.append("public_median_abs_hr_error_ok")

    if inp.public_good_coverage is None or inp.public_good_coverage < 0.80:
        failed.append("public_coverage_gate")
    else:
        passed.append("public_coverage_ok")

    spectral = inp.spectral_rate_bpm
    time_dom = inp.time_domain_rate_bpm
    if spectral is None or time_dom is None:
        s2, t2 = _rates_from_periodicity(inp.periodicity)
        spectral = spectral if spectral is not None else s2
        time_dom = time_dom if time_dom is not None else t2

    method_disagree = False
    if spectral is None or time_dom is None:
        failed.append("rate_estimates_unavailable")
    else:
        if abs(spectral - time_dom) > inp.agreement_tolerance_bpm:
            method_disagree = True
            failed.append("spectral_time_disagreement")
        else:
            passed.append("spectral_time_agree")

    if inp.channel_compatibility is not None:
        channel_summary = inp.channel_compatibility
    else:
        channel_summary = evaluate_channel_compatibility(
            inp.channel_pairs,
            layout=inp.selected_layout,
            hypothesis_key=inp.selected_hypothesis_key,
            thresholds=inp.channel_thresholds,
            filter_to_selected=True,
        )
    _apply_channel_compatibility_gate(channel_summary, failed, passed)
    assert _DEPRECATED_CHANNELS_COMPATIBLE not in passed
    assert _DEPRECATED_CHANNELS_COMPATIBLE not in failed

    if method_disagree and "decoder_status_insufficient" not in failed:
        return RateGateResult(
            rate_status=RateStatus.METHOD_DISAGREEMENT,
            failed_gates=failed,
            passed_gates=passed,
            candidate_pulse_rate_bpm=None,
            notes=notes,
            channel_compatibility=channel_summary,
        )

    if failed:
        return RateGateResult(
            rate_status=RateStatus.NOT_COMPUTED,
            failed_gates=failed,
            passed_gates=passed,
            candidate_pulse_rate_bpm=None,
            notes=notes,
            channel_compatibility=channel_summary,
        )

    rate = (float(spectral) + float(time_dom)) / 2.0
    return RateGateResult(
        rate_status=RateStatus.COMPUTED,
        failed_gates=[],
        passed_gates=passed,
        candidate_pulse_rate_bpm=rate,
        notes=notes + ["gates_passed_candidate_pulse_rate"],
        channel_compatibility=channel_summary,
    )

"""Adapt legacy Phase 1–3 safe reports or v1 inputs into a dashboard bundle."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.audit.models import SafeSchemaProfile
from src.dashboard import SCHEMA_VERSION
from src.dashboard.config import DEMO_DIR, DashboardConfig, SourceMode
from src.dashboard.loaders import (
    SafeReportLoadError,
    is_v1_schema,
    load_phase1_v1,
    load_phase2_v1,
    load_phase3_v1,
    load_raw_safe_json,
    load_reviewed_bundle,
)
from src.dashboard.models import (
    ChannelEvidenceAggregate,
    ColumnAvailability,
    DashboardEvidenceBundle,
    ModalityCoverageItem,
    SafePhase1Input,
    SafePhase2Input,
    SafePhase3Input,
)
from src.dashboard.status import NOT_AVAILABLE
from src.forensics.models import DecoderStatus, PacketSpecSummary
from src.reconstruction.models import (
    ChannelCompatibilityVerdict,
    Phase3Summary,
    RateStatus,
)

logger = logging.getLogger("dashboard")


def _adapt_legacy_phase1(data: dict[str, Any]) -> SafePhase1Input:
    profile = SafeSchemaProfile.model_validate(data)
    pending = profile.inconsistency_counts.get("pending_upload", 0)
    modalities = [
        ModalityCoverageItem(modality=m.modality, status_counts=dict(m.status_counts))
        for m in profile.modality_coverage
    ]
    columns = [
        ColumnAvailability(
            name=c.name,
            kind=c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            null_or_empty_count=c.null_or_empty_count,
            non_empty_count=c.non_empty_count,
        )
        for c in profile.columns
    ]
    return SafePhase1Input(
        schema_version="dashboard.safe.v1",
        row_count=profile.meta.row_count,
        column_count=profile.meta.column_count,
        modality_coverage=modalities,
        inconsistency_counts=dict(profile.inconsistency_counts),
        columns=columns,
        upload_completion_count=None,  # not in legacy → NOT_AVAILABLE downstream
        upload_pending_count=pending if pending else None,
        privacy_posture=list(profile.privacy_posture),
    )


def _adapt_legacy_phase2(data: dict[str, Any]) -> SafePhase2Input:
    summary = PacketSpecSummary.model_validate(data)
    # Absolute malformed count is not in legacy safe summary — do not invent it.
    return SafePhase2Input(
        schema_version="dashboard.safe.v1",
        session_count=summary.meta.session_count,
        packet_count=summary.meta.packet_count,
        malformed_packet_count=None,
        candidate_count=summary.meta.candidate_count,
        nominal_payload_length=summary.nominal_payload_length,
        datatype_mode=summary.datatype_mode,
        decoder_status=summary.selected_status,
        top_decoder_family=None,
        total_gap_count=None,
        max_gap_ms=None,
        gap_threshold_ms=summary.meta.gap_threshold_ms,
        packets_by_session=[],
        packet_interval_summary=None,
        privacy_posture=list(summary.privacy_posture),
    )


def _adapt_legacy_phase3(data: dict[str, Any]) -> SafePhase3Input:
    summary = Phase3Summary.model_validate(data)
    channel = None
    if summary.channel_compatibility is not None:
        cc = summary.channel_compatibility
        channel = ChannelEvidenceAggregate(
            verdict=cc.verdict,
            frequency_agreeing=cc.frequency_agreeing_pairs,
            frequency_evaluable=cc.frequency_evaluable_pairs,
            frequency_agreement_fraction=cc.frequency_agreement_fraction,
            median_zero_lag_correlation=cc.median_abs_zero_lag_correlation,
            median_max_lagged_correlation=cc.median_max_abs_lagged_correlation,
            median_coherence=cc.median_coherence,
            median_best_lag_samples=cc.median_best_lag_samples,
            passed_criteria=list(cc.passed_criteria),
            failed_criteria=list(cc.failed_criteria),
            thresholds_used=dict(cc.thresholds_used),
        )
    # rate_status is required on Phase3Summary — never invent if somehow missing
    rate = summary.rate_status
    if rate is None:
        raise SafeReportLoadError("Legacy Phase 3 summary missing rate_status")
    return SafePhase3Input(
        schema_version="dashboard.safe.v1",
        top_layout=summary.top_layout,
        top_hypothesis=summary.top_hypothesis,
        hypothesis_scores=[],
        quality_label_counts=dict(summary.quality_label_counts),
        continuous_segment_count=None,
        channel_segment_count=None,
        periodicity=None,
        candidate_mean_periodic_frequency_hz=None,
        channel_evidence=channel,
        rate_status=rate,
        failed_gates=[],
        passed_gates=[],
        benchmark_ran=bool(summary.extra.get("benchmark_ran", False)),
        score_margin_note=None,
        privacy_posture=list(summary.privacy_posture),
    )


def adapt_phase1(path: Path) -> SafePhase1Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return load_phase1_v1(path)
    try:
        return _adapt_legacy_phase1(data)
    except Exception as exc:
        raise SafeReportLoadError(f"Cannot adapt Phase 1 safe report: {exc}") from exc


def adapt_phase2(path: Path) -> SafePhase2Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return load_phase2_v1(path)
    try:
        return _adapt_legacy_phase2(data)
    except Exception as exc:
        raise SafeReportLoadError(f"Cannot adapt Phase 2 safe report: {exc}") from exc


def adapt_phase3(path: Path) -> SafePhase3Input:
    data = load_raw_safe_json(path)
    if is_v1_schema(data):
        return load_phase3_v1(path)
    try:
        return _adapt_legacy_phase3(data)
    except Exception as exc:
        raise SafeReportLoadError(f"Cannot adapt Phase 3 safe report: {exc}") from exc


def _load_demo_phases() -> tuple[SafePhase1Input, SafePhase2Input, SafePhase3Input]:
    """Load bundled synthetic demo aggregates only (demo mode)."""
    phase1 = adapt_phase1(DEMO_DIR / "safe_phase1.json")
    phase2 = adapt_phase2(DEMO_DIR / "safe_phase2.json")
    phase3 = adapt_phase3(DEMO_DIR / "safe_phase3.json")
    return phase1, phase2, phase3


def _assert_demo_source_integrity(
    phase1: SafePhase1Input,
    phase2: SafePhase2Input,
    phase3: SafePhase3Input,
) -> None:
    from src.dashboard.delivery.facts import SOURCE_KIND_REVIEWED

    kinds = {
        phase1.aggregate_source_kind,
        phase2.aggregate_source_kind,
        phase3.aggregate_source_kind,
    }
    kinds.discard(None)
    if SOURCE_KIND_REVIEWED in kinds:
        raise SafeReportLoadError(
            "Demo mode cannot load reviewed project aggregates"
        )


def load_evidence_bundle(config: DashboardConfig) -> DashboardEvidenceBundle:
    """Load evidence for the selected mode. Reviewed never falls back to demo."""
    if config.source_mode == SourceMode.DEMO:
        logger.info("dashboard_mode=demo")
        phase1, phase2, phase3 = _load_demo_phases()
        _assert_demo_source_integrity(phase1, phase2, phase3)
        return DashboardEvidenceBundle(
            phase1=phase1,
            phase2=phase2,
            phase3=phase3,
            source_mode=config.source_mode.value,
            banner_text=config.banner_text(),
        )

    # Reviewed mode: exact env/--safe-bundle path only. No demo loaders / defaults.
    logger.info("dashboard_mode=reviewed")
    if config.safe_bundle is None:
        logger.info("safe_bundle_validation=failed")
        raise SafeReportLoadError(
            "Reviewed mode requires WEARABLE_DASHBOARD_SAFE_BUNDLE or --safe-bundle PATH"
        )

    try:
        reviewed = load_reviewed_bundle(config.safe_bundle)
    except SafeReportLoadError:
        logger.info("safe_bundle_validation=failed")
        raise

    logger.info("safe_bundle_validation=passed")
    logger.info("schema_version=%s", reviewed.schema_version or SCHEMA_VERSION)
    return DashboardEvidenceBundle(
        phase1=reviewed.phase1,
        phase2=reviewed.phase2,
        phase3=reviewed.phase3,
        source_mode=config.source_mode.value,
        banner_text=config.banner_text(),
        reviewed_overview=reviewed.overview.model_dump(mode="json"),
        reviewed_research_status=reviewed.research_status.model_dump(mode="json"),
        reviewed_modality_coverage=reviewed.modality_coverage.model_dump(mode="json"),
        export_warnings=list(reviewed.export_warnings),
    )


def status_card_values(bundle: DashboardEvidenceBundle) -> dict[str, str]:
    """Decoder / channel / rate status strings for cards — never invent."""
    if bundle.reviewed_research_status is not None:
        return {
            "decoder": bundle.reviewed_research_status.get(
                "decoder_status", NOT_AVAILABLE
            ),
            "channel": bundle.reviewed_research_status.get(
                "channel_verdict", NOT_AVAILABLE
            ),
            "rate": bundle.reviewed_research_status.get(
                "proprietary_rate", NOT_AVAILABLE
            ),
        }

    decoder = bundle.phase2.decoder_status
    decoder_s = decoder.value if isinstance(decoder, DecoderStatus) else str(decoder)

    channel = NOT_AVAILABLE
    if bundle.phase3.channel_evidence is not None:
        v = bundle.phase3.channel_evidence.verdict
        channel = v.value if isinstance(v, ChannelCompatibilityVerdict) else str(v)

    rate = bundle.phase3.rate_status
    rate_s = rate.value if isinstance(rate, RateStatus) else str(rate)
    if not rate_s:
        rate_s = NOT_AVAILABLE

    return {
        "decoder": decoder_s or NOT_AVAILABLE,
        "channel": channel,
        "rate": rate_s,
    }

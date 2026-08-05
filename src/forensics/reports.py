"""Orchestrate Phase 2 forensics pipeline and write reports."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.audit.privacy import SCRUBBER, ScrubbedException
from src.forensics import __version__
from src.forensics.bit_forensics import BitForensicsAccumulator
from src.forensics.decide import assign_statuses, selection_summary
from src.forensics.extract import extract_session
from src.forensics.layouts import deinterleave
from src.forensics.models import (
    DecoderCandidatesReport,
    DecoderStatus,
    ForensicsMeta,
    PacketForensicsReport,
    PacketSpecSummary,
    PositionStat,
)
from src.forensics.plots import write_plots
from src.forensics.position_stats import PositionStatsAccumulator
from src.forensics.score import (
    THRESHOLDS,
    WEIGHTS,
    CandidateAccumulator,
    build_candidate_models,
    iter_candidate_specs,
    score_all_candidates,
)
from src.forensics.stream import stream_sessions
from src.forensics.timebase import (
    SessionTimebaseResult,
    analyze_session_timebase,
    build_timebase_report,
)
from src.forensics.transforms import transform_array_fast
from src.forensics.validate import ValidationAccumulator

logger = logging.getLogger("src.audit")


@dataclass
class ForensicsConfig:
    expected_payload_length: int = 66
    gap_threshold_ms: int = 1500
    samples_per_packet: int | None = None
    vendor_documented: bool = False
    max_plot_candidates: int = 5
    allow_private_snippets: bool = False
    csv_field_size_limit: int = 10 * 1024 * 1024


@dataclass
class ForensicsResult:
    packet_forensics: PacketForensicsReport
    decoder_candidates: DecoderCandidatesReport
    timebase_report: Any
    packet_spec_summary: PacketSpecSummary
    decision_markdown: str
    session_count: int
    packet_count: int
    candidate_count: int
    position_stats: list[PositionStat]
    bit_acc: BitForensicsAccumulator
    timebase_results: list[SessionTimebaseResult]
    snippet_series: list[tuple[str, np.ndarray]] | None
    max_retained_payload_arrays_observed: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to write report: {exc}", SCRUBBER) from None


def _decision_markdown(
    *,
    selected_id: str | None,
    selected_status: DecoderStatus,
    notes: list[str],
    candidate_count: int,
) -> str:
    lines = [
        "# Decoder Decision",
        "",
        f"- **Status:** `{selected_status.value}`",
        f"- **Selected candidate:** `{selected_id or 'none'}`",
        f"- **Candidates evaluated:** {candidate_count}",
        "",
        "## Limitations",
        "",
        "- Phase 2 does **not** validate that any candidate is a physiological PPG waveform.",
        "- Continuity and boundary metrics are structural only; they are not clinical evidence.",
        "- Without vendor documentation, `ACCEPTED` requires exceptional independent evidence.",
        "- No HR, HRV, SpO2, blood pressure, diagnosis, or disease risk is computed.",
        "",
        "## Rationale codes",
        "",
    ]
    for note in notes:
        lines.append(f"- `{note}`")
    lines.append("")
    return "\n".join(lines)


def _snippet_for_candidate(
    payload: list[int], selected_id: str
) -> list[tuple[str, np.ndarray]]:
    parts = selected_id.split("|")
    if len(parts) != 4:
        return []
    signedness, byte_order, cpart, _layout = parts
    channel_count = int(cpart[1:])
    transformed = transform_array_fast(
        payload, signedness=signedness, byte_order=byte_order
    )
    channels, _ = deinterleave(transformed.tolist(), channel_count, start_phase=0)
    if not channels or not channels[0]:
        return []
    return [("ch0", np.asarray(channels[0][:64], dtype=float))]


def run_forensics(input_path: str | Path, config: ForensicsConfig) -> ForensicsResult:
    SCRUBBER.register_input_path(input_path)
    logger.info("CSV reading started")

    pos_acc = PositionStatsAccumulator(expected_length=config.expected_payload_length)
    bit_acc = BitForensicsAccumulator(expected_length=config.expected_payload_length)
    val_acc = ValidationAccumulator(expected_payload_length=config.expected_payload_length)

    specs = iter_candidate_specs()
    cand_accs = [
        CandidateAccumulator(
            signedness=s, byte_order=b, channel_count=c, layout_mode=m
        )
        for s, b, c, m in specs
    ]

    session_count = 0
    packet_count = 0
    timebase_results: list[SessionTimebaseResult] = []
    snippet_payload: list[int] | None = None
    max_retained_arrays = 0
    nested_corr_positive = 0
    nested_corr_total = 0

    logger.info("Validation and extraction started")
    for ordinal, cell in stream_sessions(
        input_path, csv_field_size_limit=config.csv_field_size_limit
    ):
        session = extract_session(ordinal, cell)
        session_count += 1
        val_acc.update_session(session)
        packet_count += len(session.packets)

        payloads: list[list[int]] = []
        for pkt in session.packets:
            if pkt.ppg_values is not None:
                payloads.append(pkt.ppg_values)
                pos_acc.update_payload(pkt.ppg_values)
                bit_acc.update_payload(pkt.ppg_values)

        max_retained_arrays = max(max_retained_arrays, len(payloads))

        for acc in cand_accs:
            acc.add_session(payloads, config.expected_payload_length)

        tb = analyze_session_timebase(
            session,
            gap_threshold_ms=float(config.gap_threshold_ms),
            samples_per_packet=config.samples_per_packet,
        )
        timebase_results.append(tb)
        if tb.summary.nested_time_delta_corr is not None:
            nested_corr_total += 1
            if tb.summary.nested_time_delta_corr > 0.8:
                nested_corr_positive += 1

        if config.allow_private_snippets and payloads and snippet_payload is None:
            snippet_payload = list(payloads[0])

        del payloads

        if session_count == 1 or session_count % 2 == 0:
            logger.info(
                "Processed session %s (packets=%s total_packets=%s)",
                session_count,
                len(session.packets),
                packet_count,
            )

    logger.info(
        "CSV reading completed (sessions=%s packets=%s)",
        session_count,
        packet_count,
    )
    logger.info("Validation completed")
    logger.info("Extraction completed")

    meta = ForensicsMeta(
        session_count=session_count,
        packet_count=packet_count,
        candidate_count=len(cand_accs),
        generated_at=_now(),
        tool_version=__version__,
        expected_payload_length=config.expected_payload_length,
        gap_threshold_ms=config.gap_threshold_ms,
        samples_per_packet=config.samples_per_packet,
        vendor_documented=config.vendor_documented,
    )

    position_stats = pos_acc.to_models()
    packet_report = PacketForensicsReport(
        meta=meta,
        expected_keys=["dataEnd", "dataType", "dicData", "receivedAtMs"],
        schema_ok_count=val_acc.schema_ok_count,
        schema_anomaly_count=val_acc.schema_anomaly_count,
        datatype_histogram=dict(val_acc.datatype_histogram),
        payload_length_histogram=dict(val_acc.payload_length_histogram),
        malformed_nested_count=val_acc.malformed_nested_count,
        timestamp_regression_count=val_acc.timestamp_regression_count,
        timestamp_duplicate_count=val_acc.timestamp_duplicate_count,
        position_stats=position_stats,
        bit_forensics=bit_acc.to_model(),
        validation_codes=dict(val_acc.validation_codes),
    )

    scored = score_all_candidates(cand_accs)
    logger.info("Candidate scoring completed")
    nested_aligned = nested_corr_total > 0 and nested_corr_positive == nested_corr_total
    statuses = assign_statuses(
        scored,
        vendor_documented=config.vendor_documented,
        schema_anomaly_count=val_acc.schema_anomaly_count,
        samples_per_packet=config.samples_per_packet,
        nested_time_aligned=nested_aligned,
    )
    candidates = build_candidate_models(scored, statuses)
    selected_id, selected_status, notes = selection_summary(statuses, scored)

    decoder_report = DecoderCandidatesReport(
        meta=meta,
        weights=dict(WEIGHTS),
        thresholds=dict(THRESHOLDS),
        candidates=candidates,
        selected_candidate_id=selected_id,
        selected_status=selected_status,
        selection_notes=notes,
    )

    timebase_report = build_timebase_report(
        timebase_results,
        meta=meta,
        gap_threshold_ms=float(config.gap_threshold_ms),
        samples_per_packet=config.samples_per_packet,
    )

    datatype_mode = None
    if val_acc.datatype_histogram:
        datatype_mode = max(val_acc.datatype_histogram.items(), key=lambda kv: kv[1])[0]

    gap_sessions = sum(1 for r in timebase_results if r.summary.gap_count > 0)
    total_packets = max(packet_count, 1)
    safe = PacketSpecSummary(
        meta=meta,
        expected_keys=["dataEnd", "dataType", "dicData", "receivedAtMs"],
        nominal_payload_length=config.expected_payload_length,
        datatype_mode=datatype_mode,
        schema_anomaly_rate=val_acc.schema_anomaly_count / total_packets,
        malformed_nested_rate=val_acc.malformed_nested_count / total_packets,
        gap_rate_sessions=gap_sessions / max(session_count, 1),
        selected_status=selected_status,
        selected_candidate_id=selected_id,
        extra={"max_retained_payload_arrays_observed": max_retained_arrays},
    )

    decision_md = _decision_markdown(
        selected_id=selected_id,
        selected_status=selected_status,
        notes=notes,
        candidate_count=len(candidates),
    )

    snippet_series = None
    if config.allow_private_snippets and snippet_payload and selected_id:
        snippet_series = _snippet_for_candidate(snippet_payload, selected_id)

    return ForensicsResult(
        packet_forensics=packet_report,
        decoder_candidates=decoder_report,
        timebase_report=timebase_report,
        packet_spec_summary=safe,
        decision_markdown=decision_md,
        session_count=session_count,
        packet_count=packet_count,
        candidate_count=len(candidates),
        position_stats=position_stats,
        bit_acc=bit_acc,
        timebase_results=timebase_results,
        snippet_series=snippet_series,
        max_retained_payload_arrays_observed=max_retained_arrays,
    )


def write_outputs(
    result: ForensicsResult,
    private_dir: str | Path,
    safe_dir: str | Path,
    config: ForensicsConfig,
) -> None:
    logger.info("Reports write started")
    priv = Path(private_dir)
    safe_path = Path(safe_dir)
    priv.mkdir(parents=True, exist_ok=True)
    safe_path.mkdir(parents=True, exist_ok=True)

    write_json(priv / "packet_forensics.json", result.packet_forensics.model_dump(mode="json"))
    write_json(
        priv / "decoder_candidates.json",
        result.decoder_candidates.model_dump(mode="json"),
    )
    write_json(priv / "timebase_report.json", result.timebase_report.model_dump(mode="json"))
    write_json(
        safe_path / "packet_spec_summary.json",
        result.packet_spec_summary.model_dump(mode="json"),
    )

    decision_path = safe_path / "decoder_decision.md"
    try:
        decision_path.write_text(result.decision_markdown, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to write decision markdown: {exc}", SCRUBBER) from None

    write_plots(
        priv / "plots",
        position_stats=result.position_stats,
        bit_acc=result.bit_acc,
        candidates=result.decoder_candidates.candidates,
        timebase_results=result.timebase_results,
        max_plot_candidates=config.max_plot_candidates,
        allow_private_snippets=config.allow_private_snippets,
        snippet_series=result.snippet_series,
    )
    logger.info("Files written")

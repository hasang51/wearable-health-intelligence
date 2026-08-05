"""Reconstruct candidate channel streams under layout × payload hypotheses."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.forensics.extract import SessionExtract, extract_session
from src.forensics.stream import stream_sessions
from src.forensics.transforms import transform_array_fast
from src.reconstruction.layouts import ExplicitLayout, apply_layout_packet
from src.reconstruction.payload import (
    PayloadHypothesis,
    extract_signal_values,
    hypothesis_key,
    primary_hypotheses,
)
from src.reconstruction.segment import ContinuousSegment, SessionSegments, split_channel_by_packets
from src.reconstruction.timebase import build_relative_timebase


@dataclass
class ReconstructedCandidate:
    layout: str
    hypothesis: PayloadHypothesis
    session_ordinal: int
    packet_timestamps_ms: list[int]
    # per packet, per channel samples
    packet_channels: list[list[list[int]]]  # [packet][channel][samples]
    segments: list[ContinuousSegment] = field(default_factory=list)
    fs_hz: float = 0.0
    median_interval_ms: float = 1000.0
    gap_threshold_ms: float = 1500.0
    gap_count: int = 0


@dataclass
class LoadedSession:
    session_ordinal: int
    raw_payloads: list[list[int]]
    timestamps_ms: list[int]
    transformed_payloads: list[list[int]] = field(default_factory=list)


def load_sessions(
    input_path: str,
    *,
    signedness: str = "int24",
    byte_order: str = "CAB",
    expected_payload_length: int = 66,
    csv_field_size_limit: int = 10 * 1024 * 1024,
) -> list[LoadedSession]:
    """Stream and extract sessions; apply numeric transform to valid payloads."""
    sessions: list[LoadedSession] = []
    for ordinal, cell in stream_sessions(input_path, csv_field_size_limit=csv_field_size_limit):
        extracted: SessionExtract = extract_session(ordinal, cell)
        raws: list[list[int]] = []
        times: list[int] = []
        transformed: list[list[int]] = []
        for pkt in extracted.packets:
            if pkt.ppg_values is None or pkt.received_at_ms is None:
                continue
            if len(pkt.ppg_values) != expected_payload_length:
                continue
            raws.append(list(pkt.ppg_values))
            times.append(int(pkt.received_at_ms))
            tv = transform_array_fast(
                pkt.ppg_values, signedness=signedness, byte_order=byte_order
            )
            transformed.append(tv.tolist())
        if transformed:
            sessions.append(
                LoadedSession(
                    session_ordinal=ordinal,
                    raw_payloads=raws,
                    timestamps_ms=times,
                    transformed_payloads=transformed,
                )
            )
    return sessions


def reconstruct_session(
    session: LoadedSession,
    hypothesis: PayloadHypothesis,
    layout: ExplicitLayout | str,
) -> ReconstructedCandidate:
    """Build per-packet channel samples and gap-split segments for one session."""
    layout_s = ExplicitLayout(layout) if not isinstance(layout, ExplicitLayout) else layout
    c = hypothesis.channel_count
    packet_channels: list[list[list[int]]] = []
    phase = 0
    continuous = layout_s in (
        ExplicitLayout.INTERLEAVED_CONTINUOUS,
        ExplicitLayout.BLOCKED_CONTINUOUS,
    )

    for payload in session.transformed_payloads:
        signal = extract_signal_values(payload, hypothesis)
        start = phase if continuous else 0
        parts, next_phase = apply_layout_packet(signal, c, layout_s, start_phase=start)
        packet_channels.append(parts)
        phase = next_phase if continuous else 0

    tb = build_relative_timebase(session.timestamps_ms, hypothesis.samples_per_packet)
    all_segments: list[ContinuousSegment] = []
    gap_count = 0
    for ch in range(c):
        per_packet = [pc[ch] for pc in packet_channels]
        sess_segs: SessionSegments = split_channel_by_packets(
            session_ordinal=session.session_ordinal,
            channel=ch,
            packet_channel_samples=per_packet,
            packet_timestamps_ms=session.timestamps_ms,
            layout=layout_s.value,
            hypothesis_key=hypothesis_key(hypothesis),
            samples_per_packet=hypothesis.samples_per_packet,
            fs_hz=tb.implied_rate_hz,
            threshold_ms=tb.gap_threshold,
        )
        all_segments.extend(sess_segs.segments)
        gap_count = max(gap_count, sess_segs.gap_count)

    return ReconstructedCandidate(
        layout=layout_s.value,
        hypothesis=hypothesis,
        session_ordinal=session.session_ordinal,
        packet_timestamps_ms=list(session.timestamps_ms),
        packet_channels=packet_channels,
        segments=all_segments,
        fs_hz=tb.implied_rate_hz,
        median_interval_ms=tb.median_interval_ms,
        gap_threshold_ms=tb.gap_threshold,
        gap_count=gap_count,
    )


def reconstruct_grid(
    sessions: list[LoadedSession],
    *,
    layouts: list[ExplicitLayout] | None = None,
    hypotheses: list[PayloadHypothesis] | None = None,
) -> list[ReconstructedCandidate]:
    """Evaluate primary layout × hypothesis grid across sessions."""
    layouts = layouts or list(ExplicitLayout)
    hypotheses = hypotheses or primary_hypotheses()
    out: list[ReconstructedCandidate] = []
    for session in sessions:
        for hyp in hypotheses:
            for layout in layouts:
                out.append(reconstruct_session(session, hyp, layout))
    return out


def robust_normalize(values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=np.float64)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad < 1e-12:
        return x - med
    return (x - med) / (1.4826 * mad)

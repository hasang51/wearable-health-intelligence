"""Page 1 — Executive Overview."""

from __future__ import annotations

import streamlit as st

from src.dashboard.components.status_cards import render_status_cards
from src.dashboard.formatting import (
    fmt_duration_ms,
    fmt_int,
    modality_table_rows,
)
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE
from src.dashboard.transforms import overview_metrics

SECONDARY_MODALITY_REVIEW_NOTE = (
    "Some secondary modality counts were unavailable in the reviewed safe "
    "aggregates and are shown as NOT_AVAILABLE."
)


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Executive Overview")
    st.caption(
        "Safe aggregate evidence only. Research-only signal plausibility — "
        "no physiological claims."
    )
    if bundle.export_warnings:
        has_secondary_modality_gap = any(
            "phase1.modality_coverage[" in warning
            for warning in bundle.export_warnings
        )
        if has_secondary_modality_gap:
            st.warning(SECONDARY_MODALITY_REVIEW_NOTE)
        else:
            st.warning(
                "Some reviewed aggregate values were unavailable and are shown "
                "as NOT_AVAILABLE."
            )
        with st.expander("Technical export details", expanded=False):
            for warning in bundle.export_warnings:
                st.caption(warning)

    m = overview_metrics(bundle)
    sessions = m["sessions"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions", fmt_int(m["sessions"]))
    c2.metric("Packets", fmt_int(m["packets"]))
    c3.metric("Malformed packets", fmt_int(m["malformed_packets"]) if m["malformed_packets"] != NOT_AVAILABLE else NOT_AVAILABLE)
    c4.metric("Gaps (> threshold)", m["gaps"] if m["gaps"] != NOT_AVAILABLE else NOT_AVAILABLE)

    max_gap = m["max_gap_ms"]
    max_gap_display = (
        fmt_duration_ms(float(max_gap))
        if max_gap != NOT_AVAILABLE
        else NOT_AVAILABLE
    )
    upload_done = m["upload_completion"]
    upload_pending = m["upload_pending"]
    if upload_done != NOT_AVAILABLE and sessions:
        upload_done_disp = f"{upload_done}/{sessions}"
    else:
        upload_done_disp = str(upload_done)
    if upload_pending != NOT_AVAILABLE and sessions:
        upload_pending_disp = f"{upload_pending}/{sessions}"
    else:
        upload_pending_disp = str(upload_pending)

    c5, c6, c7 = st.columns(3)
    c5.metric("Maximum gap", max_gap_display)
    c6.metric("Upload completed", upload_done_disp)
    c7.metric("Upload pending", upload_pending_disp)

    st.subheader("Research status")
    render_status_cards(bundle)

    st.warning(
        "**Product finding — upload lifecycle:** Local raw packets were collected, "
        "while server-upload / session-completion metadata remained incomplete. "
        "Raw data exists; the upload lifecycle is incomplete."
    )

    st.subheader("Modality coverage")
    coverage = (
        bundle.reviewed_modality_coverage
        if bundle.reviewed_modality_coverage is not None
        else bundle.phase1.modality_coverage
    )
    session_count = sessions if isinstance(sessions, int) else None
    rows = modality_table_rows(coverage, session_count=session_count)
    if rows:
        st.dataframe(rows, width='stretch', hide_index=True)
    else:
        st.write(NOT_AVAILABLE)

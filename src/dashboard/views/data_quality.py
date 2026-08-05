"""Page 2 — Data and Upload Quality."""

from __future__ import annotations

import streamlit as st

from src.dashboard.components.charts import bar_chart
from src.dashboard.formatting import fmt_duration_ms, fmt_int
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE
from src.dashboard.transforms import packets_by_session_frame


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Data and Upload Quality")
    st.caption("Aggregate safe statistics only. No patient identifiers.")

    sessions = bundle.phase2.session_count
    completed = bundle.phase1.upload_completion_count
    pending = bundle.phase1.upload_pending_count

    st.subheader("Upload lifecycle")
    u1, u2 = st.columns(2)
    if completed is None:
        u1.metric("Upload completed", NOT_AVAILABLE)
    else:
        u1.metric("Upload completed", f"{completed}/{sessions}")
    if pending is None:
        u2.metric("Upload pending", NOT_AVAILABLE)
    else:
        u2.metric("Upload pending", f"{pending}/{sessions}")

    st.info(
        "**Product interpretation:** Local raw packets were collected, while "
        "upload/session completion metadata remained incomplete."
    )

    if bundle.phase1.inconsistency_counts:
        st.markdown("**Inconsistency summary**")
        st.dataframe(
            [
                {"Code": k.replace("_", " "), "Count": v}
                for k, v in sorted(bundle.phase1.inconsistency_counts.items())
                if v > 0 or k in ("pending_upload",)
            ],
            width='stretch',
            hide_index=True,
        )

    st.subheader("Packet-interval summary")
    iv = bundle.phase2.packet_interval_summary
    if iv is None:
        st.write(NOT_AVAILABLE)
    else:
        i1, i2, i3 = st.columns(3)
        i1.metric("Minimum interval", fmt_duration_ms(iv.delta_min_ms))
        i2.metric("Median interval", fmt_duration_ms(iv.delta_median_ms))
        i3.metric("P95 interval", fmt_duration_ms(iv.delta_p95_ms))

    st.subheader("Packets by session")
    rows = packets_by_session_frame(bundle)
    if rows and bundle.source_mode != "demo":
        # Project-results: only authentic session ordinals from reviewed inputs
        st.plotly_chart(
            bar_chart(rows, x="session", y="packet_count", title="Packets by session"),
            width='stretch',
        )
        st.plotly_chart(
            bar_chart(rows, x="session", y="gap_count", title="Gap counts by session"),
            width='stretch',
        )
    elif rows and bundle.source_mode == "demo":
        st.caption("Synthetic session bars (demo only).")
        st.plotly_chart(
            bar_chart(rows, x="session", y="packet_count", title="Packets by session (synthetic)"),
            width='stretch',
        )
    else:
        st.write(
            f"**Per-session packet charts:** {NOT_AVAILABLE} — "
            "reviewed safe aggregates do not include authentic session-ordinal "
            "packet counts. Corpus totals: "
            f"{fmt_int(bundle.phase2.packet_count)} packets across "
            f"{fmt_int(bundle.phase2.session_count)} sessions; "
            f"gaps = {bundle.phase2.total_gap_count if bundle.phase2.total_gap_count is not None else NOT_AVAILABLE}."
        )

    st.subheader("Raw-packet vs normalized-field availability")
    if bundle.phase1.columns:
        st.dataframe(
            [
                {
                    "Column": c.name,
                    "Kind": c.kind,
                    "Non-empty sessions": c.non_empty_count,
                    "Null / empty": c.null_or_empty_count,
                }
                for c in bundle.phase1.columns
            ],
            width='stretch',
            hide_index=True,
        )
    else:
        st.write(NOT_AVAILABLE)

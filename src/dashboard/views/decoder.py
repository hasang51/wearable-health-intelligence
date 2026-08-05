"""Page 3 — Decoder Research."""

from __future__ import annotations

import streamlit as st

from src.dashboard.components.charts import single_metric_bars
from src.dashboard.formatting import fmt_ratio, hypothesis_human_label
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE, present_or_na
from src.dashboard.transforms import score_margin


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Decoder Research")
    st.caption(
        "Best research candidate under spectral/usable metrics — "
        "not physiological PPG."
    )

    p2, p3 = bundle.phase2, bundle.phase3
    c1, c2, c3 = st.columns(3)
    c1.metric("Decoder candidates", p2.candidate_count)
    c2.metric("Top decoder family", present_or_na(p2.top_decoder_family))
    c3.metric("Decoder status", p2.decoder_status.value)

    st.markdown(f"**Best layout:** `{present_or_na(p3.top_layout)}`")
    hyp = present_or_na(p3.top_hypothesis)
    if hyp != NOT_AVAILABLE:
        st.markdown(f"**Best payload hypothesis:** {hypothesis_human_label(str(hyp))}")
        st.caption(f"Technical ID: `{hyp}`")
    else:
        st.markdown(f"**Best payload hypothesis:** {NOT_AVAILABLE}")

    st.info(
        "Best research candidate — not physiological PPG confirmation. "
        "Decoder status remains UNVERIFIED."
    )

    scores = p3.hypothesis_scores
    if not scores:
        st.write(f"Hypothesis scoreboard: {NOT_AVAILABLE}")
        return

    chart_rows = [
        {
            "label": hypothesis_human_label(h.hypothesis_id),
            "band_ratio": round(h.band_ratio, 4),
            "usable_fraction": round(h.usable_fraction, 4),
            "frequency_cv": round(h.frequency_cv, 4),
            "technical_id": h.hypothesis_id,
        }
        for h in scores
    ]

    st.subheader("Band-power ratio — higher is better")
    st.plotly_chart(
        single_metric_bars(
            chart_rows,
            label_key="label",
            value_key="band_ratio",
            title="Band-power ratio (higher is better)",
            y_title="band_ratio",
        ),
        width='stretch',
    )

    st.subheader("Usable fraction — higher is better")
    st.plotly_chart(
        single_metric_bars(
            chart_rows,
            label_key="label",
            value_key="usable_fraction",
            title="Usable fraction (higher is better)",
            y_title="usable_fraction",
        ),
        width='stretch',
    )

    st.subheader("Frequency CV — lower is better")
    st.plotly_chart(
        single_metric_bars(
            chart_rows,
            label_key="label",
            value_key="frequency_cv",
            title="Frequency coefficient of variation (lower is better)",
            y_title="frequency_cv",
        ),
        width='stretch',
    )

    st.dataframe(
        [
            {
                "Hypothesis": r["label"],
                "Technical ID": r["technical_id"],
                "band_ratio": fmt_ratio(r["band_ratio"]),
                "usable_fraction": fmt_ratio(r["usable_fraction"]),
                "frequency_cv": fmt_ratio(r["frequency_cv"]),
            }
            for r in chart_rows
        ],
        width='stretch',
        hide_index=True,
    )

    margin = score_margin(scores)
    mval = margin["band_ratio_margin"]
    if mval == NOT_AVAILABLE:
        st.write(f"Band-ratio margin (top − second): {NOT_AVAILABLE}")
    else:
        st.write(f"Band-ratio margin (top − second): **{float(mval):.4f}**")

    if p3.score_margin_note:
        st.caption(p3.score_margin_note)

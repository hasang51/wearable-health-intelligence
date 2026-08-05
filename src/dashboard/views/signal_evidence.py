"""Page 4 — Signal Evidence."""

from __future__ import annotations

import streamlit as st

from src.dashboard.components.charts import quality_pie
from src.dashboard.formatting import fmt_count_pct, fmt_pct, fmt_ratio
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE, present_or_na
from src.dashboard.transforms import quality_percentages


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Signal Evidence")
    st.caption(
        "Periodic candidate evidence is distinct from physiological validation. "
        "Quality labels measure research-only signal plausibility under an "
        "unverified decoder."
    )

    p3 = bundle.phase3
    c1, c2 = st.columns(2)
    c1.metric("Continuous segments", present_or_na(p3.continuous_segment_count))
    c2.metric("Channel-segments", present_or_na(p3.channel_segment_count))

    st.subheader("Periodicity status")
    per = p3.periodicity
    ch_total = p3.channel_segment_count
    if per is None or ch_total is None:
        st.write(NOT_AVAILABLE)
    else:
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric(
            "Plausible",
            fmt_count_pct(per.plausible, ch_total),
        )
        pc2.metric("Weak", fmt_count_pct(per.weak, ch_total))
        pc3.metric("Non-evaluable", fmt_count_pct(per.non_evaluable, ch_total))

        evaluable = per.plausible + per.weak
        if evaluable > 0:
            st.caption(
                f"Of evaluable channel-segments: "
                f"{fmt_count_pct(per.plausible, evaluable)} showed plausible "
                f"periodic candidate evidence."
            )

    st.subheader("Quality labels (window-level)")
    st.warning(
        "Window-level quality counts use overlapping windows and are "
        "**not independent observations**."
    )
    counts = p3.quality_label_counts
    if counts:
        pct = quality_percentages(counts)
        st.plotly_chart(quality_pie(counts), width='stretch')
        st.dataframe(
            [
                {
                    "Label": k,
                    "Count": v,
                    "Percent": fmt_pct(pct[k]),
                }
                for k, v in counts.items()
            ],
            width='stretch',
            hide_index=True,
        )
    else:
        st.write(NOT_AVAILABLE)

    st.subheader("Candidate frequency")
    freq = p3.candidate_mean_periodic_frequency_hz
    if freq is None:
        st.write(NOT_AVAILABLE)
    else:
        st.markdown(f"**Mean candidate periodic frequency:** {fmt_ratio(freq, decimals=2)} Hz")
        st.markdown("**Not interpreted as a vital sign.**")
    st.caption(p3.candidate_frequency_note)

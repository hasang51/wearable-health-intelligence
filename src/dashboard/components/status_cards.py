"""Neutral status cards with plain-language explanations."""

from __future__ import annotations

import streamlit as st

from src.dashboard.adapters import status_card_values
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE


_EXPLANATIONS = {
    "UNVERIFIED": "Proprietary decoder format not independently validated.",
    "INSUFFICIENT_CHANNEL_AGREEMENT": (
        "Aggregate channel evidence is below research thresholds."
    ),
    "NOT_COMPUTED": (
        "No proprietary pulse-rate estimate was produced because gates failed."
    ),
}


def render_status_cards(bundle: DashboardEvidenceBundle) -> None:
    cards = status_card_values(bundle)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Decoder status**")
        st.info(cards["decoder"])
        st.caption(_EXPLANATIONS.get(cards["decoder"], ""))
    with c2:
        st.markdown("**Channel verdict**")
        st.info(cards["channel"])
        st.caption(_EXPLANATIONS.get(cards["channel"], ""))
    with c3:
        st.markdown("**Proprietary rate**")
        st.info(cards["rate"])
        st.caption(_EXPLANATIONS.get(cards["rate"], ""))
    if NOT_AVAILABLE in cards.values():
        st.caption("NOT_AVAILABLE means the reviewed safe aggregate did not include that status.")
    else:
        st.caption(
            "Statuses are research outcomes from safe aggregates. "
            "They are not clinical alerts."
        )

"""Page 6 — Conclusions and Next Steps."""

from __future__ import annotations

import streamlit as st

from src.dashboard.adapters import status_card_values
from src.dashboard.models import DashboardEvidenceBundle


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Conclusions and Next Steps")
    cards = status_card_values(bundle)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.success("### What we verified")
        st.markdown(
            """
- Packet structure is consistent across the corpus
- Raw payloads are present (66-integer packets, dataType 119)
- Upload lifecycle is incomplete (raw present, completion metadata missing)
"""
        )
    with col2:
        st.warning("### What remains unverified")
        st.markdown(
            f"""
- Proprietary payload-to-PPG mapping ({cards['decoder']})
- Aggregate channel compatibility ({cards['channel']})
- Proprietary pulse-rate estimation ({cards['rate']})
"""
        )
    with col3:
        st.info("### Recommended next actions")
        st.markdown(
            """
- Obtain device protocol / SDK specification
- Collect synchronized reference PPG / ECG
- Add accelerometer data where available
- Correct upload and normalized-field lifecycle
"""
        )

    st.divider()

    st.subheader("Product implications")
    st.markdown(
        """
- Ship evidence views on **safe aggregates only**; keep private reconstructions offline.
- Do not surface proprietary rates while gates fail.
- Treat decoder output as research candidate streams, not product PPG.
- Prioritize upload completion and field normalization as product workstreams.
"""
    )

    st.subheader("Technical next steps")
    st.markdown(
        """
- Continue curated `dashboard.safe.v1` exports from operator-reviewed safe reports.
- Optional isolated public benchmark when cleared — never mix into proprietary ranking.
- Expand safe aggregate fields only — no silent scientific defaults.
"""
    )

    st.subheader("Clinical-validation requirements")
    st.markdown(
        """
- Independent clinical protocol, ethics review as applicable, reference devices,
  and pre-registered metrics are required before any vital-sign claim.
- This prototype does **not** provide diagnosis, HR, HRV, SpO2, blood pressure,
  or disease risk scoring output.
"""
    )

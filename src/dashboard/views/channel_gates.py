"""Page 5 — Channel Evidence and Rate Gates."""

from __future__ import annotations

import streamlit as st

from src.dashboard.formatting import (
    fmt_corr,
    fmt_pct,
    humanize_failed_criterion,
    humanize_gate,
)
from src.dashboard.models import DashboardEvidenceBundle
from src.dashboard.status import NOT_AVAILABLE


def render(bundle: DashboardEvidenceBundle) -> None:
    st.header("Channel Evidence and Rate Gates")
    st.caption(
        "Fail-closed proprietary rate: NOT_COMPUTED unless all gates pass. "
        "Channel verdict uses multi-metric aggregate evidence."
    )

    ce = bundle.phase3.channel_evidence
    if ce is None:
        st.write(f"Channel evidence: {NOT_AVAILABLE}")
    else:
        st.metric("Channel verdict", ce.verdict.value)

        frac = ce.frequency_agreement_fraction
        if ce.frequency_agreeing is not None and ce.frequency_evaluable is not None:
            pct = (
                100.0 * ce.frequency_agreeing / ce.frequency_evaluable
                if ce.frequency_evaluable
                else None
            )
            frac_label = (
                f"{ce.frequency_agreeing}/{ce.frequency_evaluable} = {fmt_pct(pct)}"
            )
        else:
            frac_label = fmt_pct(frac * 100 if frac is not None else None)

        st.markdown(f"**Frequency agreement:** {frac_label}")
        st.markdown(
            f"**Median zero-lag correlation:** {fmt_corr(ce.median_zero_lag_correlation)}"
        )
        st.markdown(
            f"**Median max lagged correlation:** "
            f"{fmt_corr(ce.median_max_lagged_correlation)}"
        )
        st.markdown(f"**Median coherence:** {fmt_corr(ce.median_coherence)}")
        lag = ce.median_best_lag_samples
        lag_s = f"{int(lag)}" if lag is not None else NOT_AVAILABLE
        st.markdown(f"**Median best lag:** {lag_s} samples")

        st.subheader("Evidence against compatible thresholds")
        thr = ce.thresholds_used or {}
        freq_obs = (
            100.0 * ce.frequency_agreeing / ce.frequency_evaluable
            if ce.frequency_agreeing is not None and ce.frequency_evaluable
            else None
        )
        freq_thr = thr.get("compatible_min_frequency_agreement")
        lag_thr = thr.get("compatible_min_median_lagged_correlation")
        coh_thr = thr.get("compatible_min_median_coherence")

        evidence_rows = [
            {
                "Metric": "Frequency agreement",
                "Observed": fmt_pct(freq_obs),
                "Compatible threshold": (
                    f">={fmt_pct(float(freq_thr) * 100)}" if freq_thr is not None else NOT_AVAILABLE
                ),
                "Result": "Failed",
            },
            {
                "Metric": "Median lagged correlation",
                "Observed": fmt_corr(ce.median_max_lagged_correlation),
                "Compatible threshold": (
                    f">={fmt_corr(float(lag_thr))}" if lag_thr is not None else NOT_AVAILABLE
                ),
                "Result": "Failed",
            },
            {
                "Metric": "Median coherence",
                "Observed": fmt_corr(ce.median_coherence),
                "Compatible threshold": (
                    f">={fmt_corr(float(coh_thr))}" if coh_thr is not None else NOT_AVAILABLE
                ),
                "Result": "Failed",
            },
        ]
        st.dataframe(evidence_rows, width='stretch', hide_index=True)

        st.subheader("Failed criteria")
        if ce.failed_criteria:
            for code in ce.failed_criteria:
                st.markdown(f"- {humanize_failed_criterion(code)}")
        else:
            st.write(NOT_AVAILABLE)

        with st.expander("Technical threshold configuration"):
            if thr:
                st.dataframe(
                    [{"Parameter": k, "Value": v} for k, v in thr.items()],
                    width='stretch',
                    hide_index=True,
                )
            else:
                st.write(NOT_AVAILABLE)

    st.subheader("Rate-gate result")
    st.info(bundle.phase3.rate_status.value)

    st.markdown("**Why NOT_COMPUTED is correct**")
    st.markdown(
        """
1. **Decoder unverified** — proprietary format is not independently validated.
2. **Public benchmark not run** — public error/coverage gates fail closed.
3. **Channel evidence insufficient** — aggregate agreement is below thresholds.
"""
    )

    st.markdown("**Failed gates (plain language)**")
    if bundle.phase3.failed_gates:
        for g in bundle.phase3.failed_gates:
            st.markdown(f"- {humanize_gate(g)}")
    else:
        st.write(NOT_AVAILABLE)

    with st.expander("Technical gate identifiers"):
        st.dataframe(
            [
                {"Gate ID": g, "Meaning": humanize_gate(g)}
                for g in bundle.phase3.failed_gates
            ]
            or [{"Gate ID": NOT_AVAILABLE, "Meaning": NOT_AVAILABLE}],
            width='stretch',
            hide_index=True,
        )

    st.caption(f"Public benchmark ran: {bundle.phase3.benchmark_ran}")

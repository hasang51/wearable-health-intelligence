"""Phase 4 Evidence Dashboard — Streamlit entrypoint.

Single-file app with sidebar navigation. View modules live under
``src/dashboard/views/`` (not Streamlit auto-discovered ``pages/``).
"""

from __future__ import annotations

import logging
import sys

import streamlit as st

from src.dashboard.adapters import load_evidence_bundle
from src.dashboard.config import (
    BANNER_DEMO,
    DashboardConfigError,
    SourceMode,
    extract_dashboard_argv,
    resolve_dashboard_mode,
)
from src.dashboard.loaders import SafeReportLoadError
from src.dashboard.views import (
    channel_gates,
    conclusions,
    data_quality,
    decoder,
    overview,
    signal_evidence,
)

PAGE_KEYS = [
    "1. Executive Overview",
    "2. Data and Upload Quality",
    "3. Decoder Research",
    "4. Signal Evidence",
    "5. Channel Evidence and Rate Gates",
    "6. Conclusions and Next Steps",
]

logger = logging.getLogger("dashboard")


def _argv_for_dashboard(argv: list[str] | None = None) -> list[str]:
    """Extract dashboard CLI args from Streamlit argv (no mode defaulting)."""
    return extract_dashboard_argv(argv)


def main(argv: list[str] | None = None) -> None:
    st.set_page_config(
        page_title="Wearable Health — Evidence Dashboard",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Wearable Health Intelligence — Evidence Dashboard")
    st.caption(
        "Phase 4 · Safe aggregates only · Offline · No clinical claims · "
        "Research-only signal plausibility"
    )

    if argv is None:
        tokens = extract_dashboard_argv(sys.argv)
    else:
        # Allow tests to pass already-extracted tokens, or full Streamlit argv.
        tokens = extract_dashboard_argv(argv) if "--" in list(argv) else list(argv)

    config = None
    try:
        config = resolve_dashboard_mode(tokens)
        bundle = load_evidence_bundle(config)
    except DashboardConfigError as exc:
        logger.error("dashboard_mode=configuration_error")
        st.error(f"Dashboard configuration error: {exc}")
        st.stop()
        return
    except SafeReportLoadError as exc:
        # Fail closed — never fall back to demo aggregates.
        if config is not None and config.source_mode == SourceMode.REVIEWED:
            st.error(f"Reviewed-bundle validation error: {exc}")
        else:
            st.error(f"Failed to load safe reports: {exc}")
        st.stop()
        return
    except Exception as exc:  # noqa: BLE001
        if config is not None and config.source_mode == SourceMode.REVIEWED:
            logger.info("safe_bundle_validation=failed")
            st.error(f"Reviewed-bundle validation error: {exc}")
        else:
            st.error(f"Failed to load safe reports: {exc}")
        st.stop()
        return

    banner = bundle.banner_text or config.banner_text()
    if config.demo or banner == BANNER_DEMO:
        st.error(banner)
    else:
        st.success(banner)

    st.sidebar.markdown(f"**{banner}**")
    st.sidebar.caption(
        "Inputs are JSON safe aggregates only. "
        "Private parquet/CSV paths are refused."
    )

    page = st.sidebar.radio("Navigate", PAGE_KEYS, key="dashboard_nav")

    if page.startswith("1."):
        overview.render(bundle)
    elif page.startswith("2."):
        data_quality.render(bundle)
    elif page.startswith("3."):
        decoder.render(bundle)
    elif page.startswith("4."):
        signal_evidence.render(bundle)
    elif page.startswith("5."):
        channel_gates.render(bundle)
    else:
        conclusions.render(bundle)


if __name__ == "__main__":
    main()

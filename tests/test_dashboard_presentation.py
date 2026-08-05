"""Presentation readiness: navigation, source integrity, reviewed aggregates."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.dashboard.adapters import load_evidence_bundle, status_card_values
from src.dashboard.app import PAGE_KEYS, _argv_for_dashboard
from src.dashboard.config import (
    BANNER_DEMO,
    BANNER_REVIEWED,
    DEMO_DIR,
    DashboardConfig,
    SourceMode,
    resolve_dashboard_mode,
)
from src.dashboard.delivery import facts as F
from src.dashboard.formatting import modality_table_rows
from src.dashboard.loaders import SafeReportLoadError, load_reviewed_bundle
from src.dashboard.terminology import find_forbidden_phrases
from src.dashboard.views.overview import SECONDARY_MODALITY_REVIEW_NOTE
from src.delivery_export import SOURCE_LABEL


def test_no_streamlit_pages_directory() -> None:
    pages = Path("src/dashboard/pages")
    assert not pages.exists(), "pages/ must not exist (avoids Streamlit auto-discovery)"


def test_views_modules_exist() -> None:
    views = Path("src/dashboard/views")
    expected = {
        "overview.py",
        "data_quality.py",
        "decoder.py",
        "signal_evidence.py",
        "channel_gates.py",
        "conclusions.py",
    }
    present = {p.name for p in views.glob("*.py") if p.name != "__init__.py"}
    assert expected <= present


def test_six_controlled_pages() -> None:
    assert len(PAGE_KEYS) == 6
    assert PAGE_KEYS[0].startswith("1.")
    assert PAGE_KEYS[5].startswith("6.")


def test_all_six_views_render_without_error(
    monkeypatch: pytest.MonkeyPatch,
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    """Call each view render with reviewed bundle (no Streamlit server)."""
    import src.dashboard.views.channel_gates as channel_gates
    import src.dashboard.views.conclusions as conclusions
    import src.dashboard.views.data_quality as data_quality
    import src.dashboard.views.decoder as decoder
    import src.dashboard.views.overview as overview
    import src.dashboard.views.signal_evidence as signal_evidence
    import streamlit as st

    bundle = load_evidence_bundle(reviewed_dashboard_config)
    calls: list[str] = []

    class _Nop:
        def __getattr__(self, name):  # noqa: ANN001
            def _fn(*args, **kwargs):  # noqa: ANN001
                calls.append(name)
                if name == "columns":
                    n = args[0] if args else 3
                    return [self] * (n if isinstance(n, int) else len(n))
                if name in ("expander",):
                    return self
                return None

            return _fn

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    nop = _Nop()
    for attr in (
        "header",
        "subheader",
        "caption",
        "markdown",
        "write",
        "metric",
        "info",
        "warning",
        "success",
        "error",
        "dataframe",
        "plotly_chart",
        "json",
        "divider",
        "columns",
        "expander",
    ):
        monkeypatch.setattr(st, attr, getattr(nop, attr))

    overview.render(bundle)
    data_quality.render(bundle)
    decoder.render(bundle)
    signal_evidence.render(bundle)
    channel_gates.render(bundle)
    conclusions.render(bundle)
    assert "header" in calls


def test_reviewed_mode_never_loads_demo_data(
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    bundle = load_evidence_bundle(reviewed_dashboard_config)
    assert bundle.source_mode == "reviewed"
    assert bundle.phase1.aggregate_source_kind == F.SOURCE_KIND_REVIEWED
    assert bundle.phase1.upload_completion_count == 0
    assert bundle.phase1.upload_pending_count == 10
    # Demo synthetic values must not appear
    assert bundle.phase1.upload_completion_count != 8
    assert bundle.phase2.packets_by_session == []


def test_demo_banner_and_reviewed_banner(
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    demo = load_evidence_bundle(DashboardConfig(source_mode=SourceMode.DEMO))
    rev = load_evidence_bundle(reviewed_dashboard_config)
    assert demo.banner_text == BANNER_DEMO
    assert rev.banner_text == BANNER_REVIEWED
    assert rev.banner_text == SOURCE_LABEL
    assert "SYNTHETIC DEMO" in demo.banner_text
    assert "Reviewed anonymized dataset" in rev.banner_text
    assert "SYNTHETIC DEMO" not in rev.banner_text


def test_source_integrity_rejects_demo_as_reviewed_bundle() -> None:
    """A synthetic demo phase JSON is not a valid ReviewedDashboardBundle."""
    with pytest.raises(SafeReportLoadError):
        load_reviewed_bundle(DEMO_DIR / "safe_phase1.json")
    cfg = DashboardConfig(
        source_mode=SourceMode.REVIEWED,
        safe_bundle=DEMO_DIR / "safe_phase1.json",
    )
    with pytest.raises(SafeReportLoadError):
        load_evidence_bundle(cfg)


def test_source_integrity_rejects_reviewed_in_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
    reviewed_bundle_path: Path,
) -> None:
    from src.dashboard import adapters
    from src.dashboard.loaders import load_reviewed_bundle as real_load

    reviewed = real_load(reviewed_bundle_path)

    def fake_demo_load():  # noqa: ANN001
        return reviewed.phase1, reviewed.phase2, reviewed.phase3

    monkeypatch.setattr(adapters, "_load_demo_phases", fake_demo_load)
    cfg = DashboardConfig(source_mode=SourceMode.DEMO)
    with pytest.raises(SafeReportLoadError, match="reviewed"):
        adapters.load_evidence_bundle(cfg)


def test_reviewed_expected_aggregates(
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    b = load_evidence_bundle(reviewed_dashboard_config)
    cards = status_card_values(b)
    assert b.phase2.session_count == 10
    assert b.phase2.packet_count == 8161
    assert b.phase2.malformed_packet_count == 0
    assert b.phase2.total_gap_count == 27
    assert b.phase2.max_gap_ms == 47111
    assert b.phase1.upload_completion_count == 0
    assert b.phase1.upload_pending_count == 10
    assert cards["decoder"] == "UNVERIFIED"
    assert cards["channel"] == "INSUFFICIENT_CHANNEL_AGREEMENT"
    assert cards["rate"] == "NOT_COMPUTED"
    assert b.phase2.candidate_count == 192
    assert b.phase2.top_decoder_family == "int24 | CAB | C2"
    assert b.phase3.top_hypothesis == "H_2block_meta_per_ch:last_of_block"
    assert b.phase3.top_layout == "INTERLEAVED_PACKET_LOCAL"
    assert b.phase3.continuous_segment_count == 37
    assert b.phase3.channel_segment_count == 74
    assert b.phase3.periodicity is not None
    assert b.phase3.periodicity.plausible == 35
    assert b.phase3.periodicity.weak == 17
    assert b.phase3.periodicity.non_evaluable == 22
    ce = b.phase3.channel_evidence
    assert ce is not None
    assert ce.frequency_agreeing == 18
    assert ce.frequency_evaluable == 37
    assert abs(ce.frequency_agreement_fraction - 18 / 37) < 1e-9
    assert ce.median_zero_lag_correlation == -0.008
    assert ce.median_max_lagged_correlation == 0.205
    assert ce.median_coherence == 0.075
    assert ce.median_best_lag_samples == 12.0
    assert b.phase3.rate_status.value == "NOT_COMPUTED"
    assert b.phase2.packet_interval_summary is not None
    assert b.phase2.packet_interval_summary.delta_median_ms == 995.0


def test_reviewed_ppg_rows_are_separate(
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    bundle = load_evidence_bundle(reviewed_dashboard_config)
    assert bundle.reviewed_modality_coverage is not None
    rows = modality_table_rows(
        bundle.reviewed_modality_coverage,
        session_count=10,
    )
    by_name = {row["Modality"]: row for row in rows}
    assert by_name["Raw optical/PPG payload"]["Sessions with samples"] == "10"
    assert by_name["Normalized PPG stream"]["Sessions with samples"] == "0"


def test_no_channels_compatible_in_views() -> None:
    for path in Path("src/dashboard/views").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "channels_compatible" not in text, f"deprecated gate in {path}"
    for path in Path("src/dashboard/components").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "channels_compatible" not in text, f"deprecated gate in {path}"
    app_text = Path("src/dashboard/app.py").read_text(encoding="utf-8")
    assert "channels_compatible" not in app_text


def test_views_avoid_raw_dict_write_patterns() -> None:
    """Primary sections should use dataframe/metric, not st.write(dict)."""
    for path in Path("src/dashboard/views").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "json":
                    pytest.fail(f"{path.name} uses st.json in primary UI")
                if name == "write" and node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, (ast.Dict, ast.List)):
                        pytest.fail(f"{path.name} writes raw dict/list via st.write")


def test_project_results_contains_no_synthetic_session_values(
    reviewed_dashboard_config: DashboardConfig,
) -> None:
    b = load_evidence_bundle(reviewed_dashboard_config)
    assert b.phase2.packets_by_session == []
    assert b.phase1.upload_completion_count == 0
    # Demo-only interval values must not appear
    assert b.phase2.packet_interval_summary is not None
    assert b.phase2.packet_interval_summary.delta_median_ms != 52.0


def test_argv_supports_safe_bundle(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    assert _argv_for_dashboard(
        ["streamlit", "run", "app.py", "--", "--safe-bundle", str(path)]
    ) == ["--safe-bundle", str(path)]
    cfg = resolve_dashboard_mode(_argv_for_dashboard(["--", "--safe-bundle", str(path)]))
    assert cfg.source_mode == SourceMode.REVIEWED
    assert cfg.safe_bundle == path


def test_streamlit_apptest_all_pages_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("streamlit")
    import sys

    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        sys,
        "argv",
        ["streamlit", "run", "src/dashboard/app.py", "--", "--demo"],
    )
    at = AppTest.from_file("src/dashboard/app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert len(at.radio) >= 1
    labels = list(at.radio[0].options)
    assert len(labels) == 6
    for key in PAGE_KEYS:
        at.radio[0].set_value(key).run()
        assert not at.exception, f"Page {key} failed: {at.exception}"


def test_demo_banner_visible_in_apptest(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("streamlit")
    import sys

    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        sys,
        "argv",
        ["streamlit", "run", "src/dashboard/app.py", "--", "--demo"],
    )
    at = AppTest.from_file("src/dashboard/app.py", default_timeout=60)
    at.run()
    assert not at.exception
    err_vals = [str(x.value) for x in at.error]
    assert any("SYNTHETIC DEMO" in v for v in err_vals)


def test_streamlit_apptest_reviewed_banner(
    reviewed_bundle_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("streamlit")
    import sys

    from streamlit.testing.v1 import AppTest

    path = str(reviewed_bundle_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["streamlit", "run", "src/dashboard/app.py", "--", "--safe-bundle", path],
    )
    at = AppTest.from_file("src/dashboard/app.py", default_timeout=60)
    at.run()
    assert not at.exception, f"AppTest exception: {at.exception}"
    success_vals = [str(x.value) for x in at.success]
    assert any(SOURCE_LABEL in v for v in success_vals)
    err_vals = [str(x.value) for x in at.error]
    assert not any("SYNTHETIC DEMO" in v for v in err_vals)
    warning_vals = [str(x.value) for x in at.warning]
    assert SECONDARY_MODALITY_REVIEW_NOTE in warning_vals
    assert not any("phase1.modality_coverage[" in v for v in warning_vals)
    assert any(x.label == "Technical export details" for x in at.expander)
    caption_vals = [str(x.value) for x in at.caption]
    assert any(
        "phase1.modality_coverage[ecg].samples_present" in v
        for v in caption_vals
    )


def test_forbidden_terms_absent_from_views() -> None:
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in Path("src/dashboard/views").glob("*.py")
    )
    assert find_forbidden_phrases(blob) == []

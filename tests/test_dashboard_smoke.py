"""Smoke tests for Streamlit dashboard import and AppTest startup."""

from __future__ import annotations

import pytest

from src.dashboard.config import SourceMode, resolve_dashboard_mode


def test_import_dashboard_modules() -> None:
    import src.dashboard.app as app_mod
    import src.dashboard.config as config_mod
    import src.dashboard.adapters as adapters_mod

    assert callable(app_mod.main)
    assert callable(config_mod.parse_dashboard_args)
    assert callable(config_mod.resolve_dashboard_mode)
    assert callable(adapters_mod.load_evidence_bundle)
    assert app_mod._argv_for_dashboard([]) == []
    assert app_mod._argv_for_dashboard(["-q", "--tb=short"]) == []
    assert app_mod._argv_for_dashboard(["--demo"]) == ["--demo"]
    assert app_mod._argv_for_dashboard(
        ["streamlit", "run", "app.py", "--", "--safe-bundle", "x.json"]
    ) == ["--safe-bundle", "x.json"]
    cfg = resolve_dashboard_mode(["--demo"])
    assert cfg.source_mode == SourceMode.DEMO


def test_streamlit_apptest_demo(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert not at.exception, f"AppTest exception: {at.exception}"
    err_vals = [str(x.value) for x in at.error]
    assert any("SYNTHETIC DEMO" in v for v in err_vals)
    info_vals = [str(x.value) for x in at.info]
    assert any("UNVERIFIED" in v for v in info_vals)
    assert any("INSUFFICIENT_CHANNEL_AGREEMENT" in v for v in info_vals)
    assert any("NOT_COMPUTED" in v for v in info_vals)

"""Dashboard launch-mode resolution and reviewed safe-bundle loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.dashboard import SCHEMA_VERSION
from src.dashboard.adapters import load_evidence_bundle, status_card_values
from src.dashboard.config import (
    BANNER_DEMO,
    BANNER_REVIEWED,
    DEMO_DIR,
    SAFE_BUNDLE_ENV,
    DashboardConfig,
    DashboardConfigError,
    SourceMode,
    extract_dashboard_argv,
    resolve_dashboard_mode,
)
from src.dashboard.loaders import SafeReportLoadError, load_reviewed_bundle
from src.delivery_export import SOURCE_LABEL


def _reviewed_config(path: Path) -> DashboardConfig:
    return DashboardConfig(source_mode=SourceMode.REVIEWED, safe_bundle=path)


@pytest.fixture(autouse=True)
def _clear_safe_bundle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate mode tests from a developer-local reviewed env var."""
    monkeypatch.delenv(SAFE_BUNDLE_ENV, raising=False)


# --- mode resolution (no Streamlit) ---


def test_safe_bundle_selects_reviewed_mode(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    cfg = resolve_dashboard_mode(["--safe-bundle", str(path)])
    assert cfg.source_mode == SourceMode.REVIEWED
    assert cfg.safe_bundle == path
    assert cfg.demo is False
    assert cfg.is_project_results is True


def test_env_safe_bundle_selects_reviewed_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "env_bundle.json"
    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(path))
    cfg = resolve_dashboard_mode([])
    assert cfg.source_mode == SourceMode.REVIEWED
    assert cfg.safe_bundle == path
    assert cfg.demo is False
    assert cfg.is_project_results is True


def test_env_safe_bundle_takes_precedence_over_cli_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "from_env.json"
    cli_path = tmp_path / "from_cli.json"
    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(env_path))
    cfg = resolve_dashboard_mode(["--safe-bundle", str(cli_path)])
    assert cfg.source_mode == SourceMode.REVIEWED
    assert cfg.safe_bundle == env_path


def test_env_and_demo_together_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bundle.json"
    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(path))
    with pytest.raises(DashboardConfigError, match="Conflicting|reviewed|--demo"):
        resolve_dashboard_mode(["--demo"])


def test_demo_selects_demo_mode() -> None:
    cfg = resolve_dashboard_mode(["--demo"])
    assert cfg.source_mode == SourceMode.DEMO
    assert cfg.safe_bundle is None
    assert cfg.demo is True


def test_both_arguments_fail() -> None:
    with pytest.raises(DashboardConfigError, match="exactly one"):
        resolve_dashboard_mode(["--demo", "--safe-bundle", "x.json"])


def test_neither_argument_fails() -> None:
    with pytest.raises(DashboardConfigError, match="exactly one|neither"):
        resolve_dashboard_mode([])


def test_extract_argv_after_double_dash(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    tokens = extract_dashboard_argv(
        ["streamlit", "run", "app.py", "--", "--safe-bundle", str(path)]
    )
    assert tokens == ["--safe-bundle", str(path)]
    cfg = resolve_dashboard_mode(tokens)
    assert cfg.source_mode == SourceMode.REVIEWED


def test_extract_argv_does_not_default_to_demo() -> None:
    assert extract_dashboard_argv(["-q", "--tb=short"]) == []
    assert extract_dashboard_argv([]) == []


def test_unknown_legacy_flags_are_ignored_not_demo() -> None:
    """Unrecognized flags (e.g. old --reviewed) must not silently become demo."""
    assert extract_dashboard_argv(["--reviewed"]) == []
    with pytest.raises(DashboardConfigError):
        resolve_dashboard_mode(extract_dashboard_argv(["--reviewed"]))


# --- reviewed bundle fail-closed ---


def test_missing_reviewed_bundle_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing_bundle.json"
    cfg = _reviewed_config(missing)
    with pytest.raises(SafeReportLoadError, match="not found|Reviewed"):
        load_evidence_bundle(cfg)


def test_invalid_reviewed_bundle_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "nope": True}), encoding="utf-8")
    with pytest.raises(SafeReportLoadError, match="validation|Reviewed"):
        load_reviewed_bundle(bad)
    with pytest.raises(SafeReportLoadError):
        load_evidence_bundle(_reviewed_config(bad))


def test_unsupported_schema_version_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad_ver.json"
    bad.write_text(
        json.dumps({"schema_version": "dashboard.safe.v999", "phase1": {}}),
        encoding="utf-8",
    )
    with pytest.raises(SafeReportLoadError, match="schema_version"):
        load_reviewed_bundle(bad)


def test_reviewed_mode_never_calls_demo_loader(
    reviewed_bundle_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.dashboard.adapters as adapters

    def boom() -> Any:
        raise AssertionError("demo loader must not be called in reviewed mode")

    monkeypatch.setattr(adapters, "_load_demo_phases", boom)
    bundle = load_evidence_bundle(_reviewed_config(reviewed_bundle_path))
    assert bundle.source_mode == "reviewed"
    assert bundle.phase1.upload_completion_count == 0


def test_env_reviewed_mode_never_calls_demo_loader(
    reviewed_bundle_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.dashboard.adapters as adapters

    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(reviewed_bundle_path))

    def boom() -> Any:
        raise AssertionError("demo loader must not be called in reviewed mode")

    monkeypatch.setattr(adapters, "_load_demo_phases", boom)
    cfg = resolve_dashboard_mode([])
    bundle = load_evidence_bundle(cfg)
    assert bundle.source_mode == "reviewed"
    assert bundle.phase1.upload_completion_count == 0
    assert bundle.phase1.upload_pending_count == 10
    assert "SYNTHETIC DEMO" not in bundle.banner_text


def test_env_reviewed_missing_bundle_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing_env_bundle.json"
    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(missing))
    cfg = resolve_dashboard_mode([])
    assert cfg.source_mode == SourceMode.REVIEWED
    with pytest.raises(SafeReportLoadError, match="not found|Reviewed"):
        load_evidence_bundle(cfg)


def test_env_reviewed_invalid_bundle_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad_env.json"
    bad.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "nope": True}),
        encoding="utf-8",
    )
    monkeypatch.setenv(SAFE_BUNDLE_ENV, str(bad))
    cfg = resolve_dashboard_mode([])
    with pytest.raises(SafeReportLoadError):
        load_evidence_bundle(cfg)


def test_reviewed_mode_never_merges_demo_defaults(reviewed_bundle_path: Path) -> None:
    data = json.loads(reviewed_bundle_path.read_text(encoding="utf-8"))
    # Drop an optional field that demo would invent if merged.
    data["phase1"]["upload_completion_count"] = None
    path = reviewed_bundle_path.parent / "no_upload_completed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    bundle = load_evidence_bundle(_reviewed_config(path))
    assert bundle.phase1.upload_completion_count is None
    # Must not pick up demo's synthetic 8
    assert bundle.phase1.upload_completion_count != 8
    assert bundle.phase1.upload_pending_count == 10


def test_reviewed_mode_banner_is_correct(reviewed_bundle_path: Path) -> None:
    cfg = _reviewed_config(reviewed_bundle_path)
    bundle = load_evidence_bundle(cfg)
    assert cfg.banner_text() == BANNER_REVIEWED
    assert bundle.banner_text == SOURCE_LABEL
    assert (
        bundle.banner_text
        == "Reviewed anonymized dataset — local safe aggregate reports"
    )


def test_synthetic_banner_absent_in_reviewed(reviewed_bundle_path: Path) -> None:
    bundle = load_evidence_bundle(_reviewed_config(reviewed_bundle_path))
    assert "SYNTHETIC DEMO" not in bundle.banner_text
    assert BANNER_DEMO not in bundle.banner_text


def test_reviewed_expected_values_render(reviewed_bundle_path: Path) -> None:
    bundle = load_evidence_bundle(_reviewed_config(reviewed_bundle_path))
    cards = status_card_values(bundle)
    assert bundle.phase2.session_count == 10
    assert bundle.phase2.packet_count == 8161
    assert bundle.phase1.upload_completion_count == 0
    assert bundle.phase1.upload_pending_count == 10
    assert cards["decoder"] == "UNVERIFIED"
    assert cards["channel"] == "INSUFFICIENT_CHANNEL_AGREEMENT"
    assert cards["rate"] == "NOT_COMPUTED"


def test_demo_banner_persists() -> None:
    bundle = load_evidence_bundle(DashboardConfig(source_mode=SourceMode.DEMO))
    assert bundle.banner_text == BANNER_DEMO
    assert "SYNTHETIC DEMO" in bundle.banner_text


def test_startup_logging_reviewed_passed(
    reviewed_bundle_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="dashboard"):
        load_evidence_bundle(_reviewed_config(reviewed_bundle_path))
    messages = "\n".join(r.message for r in caplog.records)
    assert "dashboard_mode=reviewed" in messages
    assert "safe_bundle_validation=passed" in messages
    assert f"schema_version={SCHEMA_VERSION}" in messages
    # Must not log the full input path
    assert str(reviewed_bundle_path) not in messages
    assert "C:\\" not in messages
    assert "/Users/" not in messages


def test_startup_logging_reviewed_failed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "gone.json"
    with caplog.at_level(logging.INFO, logger="dashboard"):
        with pytest.raises(SafeReportLoadError):
            load_evidence_bundle(_reviewed_config(missing))
    messages = "\n".join(r.message for r in caplog.records)
    assert "dashboard_mode=reviewed" in messages
    assert "safe_bundle_validation=failed" in messages
    assert str(missing) not in messages


def test_demo_json_rejected_as_reviewed_bundle() -> None:
    """A synthetic demo phase file is not a ReviewedDashboardBundle."""
    with pytest.raises(SafeReportLoadError):
        load_reviewed_bundle(DEMO_DIR / "safe_phase1.json")

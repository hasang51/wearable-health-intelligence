"""Tests for safe report loading and schema rejection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.config import (
    DEMO_DIR,
    SAFE_BUNDLE_ENV,
    DashboardConfig,
    DashboardConfigError,
    SourceMode,
    parse_dashboard_args,
    resolve_dashboard_mode,
)
from src.dashboard.loaders import SafeReportLoadError, load_phase1_v1, load_raw_safe_json
from src.dashboard.privacy import assert_safe_json_path


@pytest.fixture(autouse=True)
def _clear_safe_bundle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SAFE_BUNDLE_ENV, raising=False)


def test_demo_phase1_loads() -> None:
    p = DEMO_DIR / "safe_phase1.json"
    model = load_phase1_v1(p)
    assert model.schema_version == "dashboard.safe.v1"
    assert model.row_count == 10


def test_reject_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"schema_version": "dashboard.safe.v999", "row_count": 1}),
        encoding="utf-8",
    )
    with pytest.raises(SafeReportLoadError, match="schema_version"):
        load_raw_safe_json(path)


def test_reject_malformed_v1(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text(
        json.dumps({"schema_version": "dashboard.safe.v1", "row_count": "nope"}),
        encoding="utf-8",
    )
    with pytest.raises(SafeReportLoadError):
        load_phase1_v1(path)


def test_refuse_csv_path(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-safe|JSON"):
        assert_safe_json_path(csv_path)


def test_refuse_parquet_path(tmp_path: Path) -> None:
    pq = tmp_path / "x.parquet"
    pq.write_bytes(b"not-really-parquet")
    with pytest.raises(ValueError):
        assert_safe_json_path(pq)


def test_parse_demo_args() -> None:
    cfg = parse_dashboard_args(["--demo"])
    assert cfg.demo is True
    assert cfg.source_mode == SourceMode.DEMO
    assert cfg.safe_bundle is None


def test_parse_safe_bundle_args(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    cfg = parse_dashboard_args(["--safe-bundle", str(path)])
    assert cfg.is_project_results is True
    assert cfg.demo is False
    assert cfg.safe_bundle == path


def test_demo_xor_safe_bundle() -> None:
    with pytest.raises(DashboardConfigError):
        resolve_dashboard_mode(["--demo", "--safe-bundle", "a.json"])


def test_requires_exactly_one_mode() -> None:
    with pytest.raises(DashboardConfigError):
        resolve_dashboard_mode([])


def test_config_dataclass() -> None:
    cfg = DashboardConfig(source_mode=SourceMode.DEMO)
    assert cfg.safe_bundle is None
    assert cfg.demo is True

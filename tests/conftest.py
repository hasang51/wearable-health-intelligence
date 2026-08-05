"""Shared pytest fixtures and constants."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PATIENT = "SYNTH_PATIENT_ADA_LOVELACE"
PROTOCOL = "PROTO-SYNTH-9999"
MAC = "AA:BB:CC:DD:EE:FF"
CONSENT = "CONSENT_BYTES_SYNTH_DEADBEEF"
TS_EXACT = "2024-06-15T14:30:00Z"
PHYSIO_SAMPLE = "987654.321"
SENSITIVE_FILENAME = "sensitive_name_SYNTH_PATIENT_X.csv"

FORBIDDEN_LITERALS = [
    PATIENT,
    PROTOCOL,
    MAC,
    CONSENT,
    TS_EXACT,
    PHYSIO_SAMPLE,
    "SYNTH_PATIENT_X",
]

# Phase 4 clinical overclaim phrases (substring match, case-insensitive in scanners).
PHASE4_FORBIDDEN_PHRASES = [
    "diagnosed",
    "patient risk",
    "detected disease",
    "confirmed PPG",
    "accurate heart rate",
    "clinical-grade",
    "medical alert",
    "validated PPG",
    "disease-risk",
]


@pytest.fixture(autouse=True)
def _clear_dashboard_safe_bundle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep dashboard mode tests isolated from a local reviewed env var."""
    monkeypatch.delenv("WEARABLE_DASHBOARD_SAFE_BUNDLE", raising=False)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def reviewed_bundle_path(tmp_path: Path) -> Path:
    """One allowlisted reviewed dashboard.safe.v1 bundle for dashboard tests."""
    from src.dashboard.config import REVIEWED_DIR
    from src.delivery_export.export import export_reviewed_dashboard_bundle

    out = tmp_path / "dashboard_safe_v1.json"
    export_reviewed_dashboard_bundle(
        REVIEWED_DIR / "safe_phase1.json",
        REVIEWED_DIR / "safe_phase2.json",
        REVIEWED_DIR / "safe_phase3.json",
        out,
    )
    return out


@pytest.fixture
def reviewed_dashboard_config(reviewed_bundle_path: Path):
    from src.dashboard.config import DashboardConfig, SourceMode

    return DashboardConfig(
        source_mode=SourceMode.REVIEWED,
        safe_bundle=reviewed_bundle_path,
    )

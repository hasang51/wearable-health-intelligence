"""Privacy and forbidden-symbol tests for Phase 2 forensics."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.audit.logging_config import configure_logging
from src.audit.privacy import SCRUBBER
from src.forensics.cli import main
from tests.conftest import (
    CONSENT,
    FORBIDDEN_LITERALS,
    MAC,
    PATIENT,
    PHYSIO_SAMPLE,
    PROTOCOL,
    TS_EXACT,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SENSITIVE_PACKET = "packets_sensitive_name_SYNTH.csv"


def test_forensics_outputs_scrubbed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    SCRUBBER.register_literals([PATIENT, PROTOCOL, MAC, CONSENT, TS_EXACT, PHYSIO_SAMPLE])
    input_path = FIXTURES / SENSITIVE_PACKET
    private_dir = tmp_path / "private"
    safe_dir = tmp_path / "safe"

    with caplog.at_level(logging.INFO):
        configure_logging()
        code = main(
            [
                "--input",
                str(input_path),
                "--private-dir",
                str(private_dir),
                "--safe-dir",
                str(safe_dir),
            ]
        )
    assert code == 0

    channels = {
        "packet_forensics": (private_dir / "packet_forensics.json").read_text(encoding="utf-8"),
        "decoder_candidates": (private_dir / "decoder_candidates.json").read_text(
            encoding="utf-8"
        ),
        "timebase": (private_dir / "timebase_report.json").read_text(encoding="utf-8"),
        "safe_summary": (safe_dir / "packet_spec_summary.json").read_text(encoding="utf-8"),
        "decision_md": (safe_dir / "decoder_decision.md").read_text(encoding="utf-8"),
        "stdout": capsys.readouterr().out,
        "logs": "\n".join(r.getMessage() for r in caplog.records),
    }

    for name, text in channels.items():
        for lit in FORBIDDEN_LITERALS:
            assert lit not in text, f"{name} leaked {lit!r}"
        assert SENSITIVE_PACKET not in text
        assert str(input_path) not in text


def test_no_forbidden_analysis_imports() -> None:
    """Lightweight guard: forensics modules must not import spectral/ML helpers."""
    root = Path(__file__).resolve().parents[1] / "src" / "forensics"
    forbidden_substrings = [
        "import seaborn",
        "from seaborn",
        "scipy.fft",
        "numpy.fft",
        "sklearn",
        "torch",
        "tensorflow",
        "find_peaks",
        "butter(",
        "filtfilt",
        "heart_rate",
        "hrv",
        "spo2",
        "blood_pressure",
    ]
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for frag in forbidden_substrings:
            assert frag not in text, f"{path.name} contains forbidden {frag!r}"

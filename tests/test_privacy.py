"""Privacy tests across all output channels."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.audit.cli import main
from src.audit.logging_config import configure_logging
from src.audit.privacy import SCRUBBER, ScrubbedException
from tests.conftest import (
    CONSENT,
    FORBIDDEN_LITERALS,
    MAC,
    PATIENT,
    PHYSIO_SAMPLE,
    PROTOCOL,
    SENSITIVE_FILENAME,
    TS_EXACT,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _assert_clean(text: str, *, allow_physio_in_private: bool = False) -> None:
    forbidden = list(FORBIDDEN_LITERALS)
    if allow_physio_in_private:
        # Private still must not contain physio sample literals per plan.
        pass
    for lit in forbidden:
        assert lit not in text, f"Forbidden literal leaked: {lit!r}"


def test_reports_and_stdio_and_logs_are_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    SCRUBBER.register_literals([PATIENT, PROTOCOL, MAC, CONSENT, TS_EXACT, PHYSIO_SAMPLE])
    input_path = FIXTURES / SENSITIVE_FILENAME
    private_out = tmp_path / "private.json"
    safe_out = tmp_path / "safe.json"

    with caplog.at_level(logging.INFO):
        configure_logging()
        code = main(
            [
                "--input",
                str(input_path),
                "--private-output",
                str(private_out),
                "--safe-output",
                str(safe_out),
            ]
        )
    assert code == 0

    private_text = private_out.read_text(encoding="utf-8")
    safe_text = safe_out.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)

    for channel_name, text in [
        ("private", private_text),
        ("safe", safe_text),
        ("stdout", captured.out),
        ("stderr", captured.err),
        ("logs", log_text),
    ]:
        for lit in FORBIDDEN_LITERALS:
            assert lit not in text, f"{channel_name} leaked {lit!r}"
        assert SENSITIVE_FILENAME not in text
        assert "SYNTH_PATIENT_X" not in text


def test_exception_messages_scrubbed() -> None:
    SCRUBBER.register_input_path(f"C:/secret/{SENSITIVE_FILENAME}")
    SCRUBBER.register_literals([PATIENT, MAC])
    exc = ScrubbedException(
        f"Failed on {SENSITIVE_FILENAME} patient={PATIENT} mac={MAC}",
        SCRUBBER,
    )
    msg = str(exc)
    assert PATIENT not in msg
    assert MAC not in msg
    assert SENSITIVE_FILENAME not in msg


def test_forced_error_path_scrubbed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    SCRUBBER.register_literals([PATIENT])
    bad = tmp_path / SENSITIVE_FILENAME
    # Create empty-named sensitive file path that does not exist as CSV content —
    # use a missing path whose name contains the sensitive token.
    missing = tmp_path / SENSITIVE_FILENAME
    code = main(
        [
            "--input",
            str(missing),
            "--private-output",
            str(tmp_path / "p.json"),
            "--safe-output",
            str(tmp_path / "s.json"),
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert SENSITIVE_FILENAME not in combined
    assert "SYNTH_PATIENT_X" not in combined


def test_ignore_files_contain_required_patterns() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    cursorignore = (root / ".cursorignore").read_text(encoding="utf-8")
    for pattern in [
        "data/raw/**",
        "data/private/**",
        "reports/private/**",
        "*.csv",
        "*.parquet",
        "*.db",
        "*.sqlite",
        ".env*",
        "secrets/**",
    ]:
        assert pattern in gitignore
        assert pattern in cursorignore

"""CLI end-to-end tests."""

from pathlib import Path

from src.audit.cli import main
from src.audit.models import PrivateDataProfile, SafeSchemaProfile

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cli_success(tmp_path: Path) -> None:
    private_out = tmp_path / "data_profile.json"
    safe_out = tmp_path / "schema_profile.json"
    code = main(
        [
            "--input",
            str(FIXTURES / "sessions_valid.csv"),
            "--private-output",
            str(private_out),
            "--safe-output",
            str(safe_out),
        ]
    )
    assert code == 0
    assert private_out.is_file()
    assert safe_out.is_file()
    PrivateDataProfile.model_validate_json(private_out.read_text(encoding="utf-8"))
    SafeSchemaProfile.model_validate_json(safe_out.read_text(encoding="utf-8"))


def test_cli_missing_input(tmp_path: Path) -> None:
    code = main(
        [
            "--input",
            str(tmp_path / "does_not_exist.csv"),
            "--private-output",
            str(tmp_path / "p.json"),
            "--safe-output",
            str(tmp_path / "s.json"),
        ]
    )
    assert code == 1


def test_cli_rejects_directory(tmp_path: Path) -> None:
    code = main(
        [
            "--input",
            str(tmp_path),
            "--private-output",
            str(tmp_path / "p.json"),
            "--safe-output",
            str(tmp_path / "s.json"),
        ]
    )
    assert code == 1

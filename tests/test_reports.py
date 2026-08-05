"""Tests for report building and safe derivation."""

from pathlib import Path

from src.audit.limits import ResourceLimits
from src.audit.models import PrivateDataProfile, SafeSchemaProfile
from src.audit.reports import run_audit, to_safe_profile, write_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_private_and_safe_validate(tmp_path: Path) -> None:
    private = run_audit(FIXTURES / "sessions_valid.csv", ResourceLimits())
    safe = to_safe_profile(private)
    assert isinstance(private, PrivateDataProfile)
    assert isinstance(safe, SafeSchemaProfile)
    assert private.meta.limits_applied.max_json_depth == 8
    assert "no_raw_values" in safe.privacy_posture
    assert "dynamic_keys_redacted" in safe.privacy_posture

    priv_path = tmp_path / "private.json"
    safe_path = tmp_path / "safe.json"
    write_json(priv_path, private.model_dump(mode="json"))
    write_json(safe_path, safe.model_dump(mode="json"))
    assert priv_path.is_file()
    assert safe_path.is_file()

    # Safe has inconsistency counts, not per-session list
    assert isinstance(safe.inconsistency_counts, dict)


def test_sparse_fixture_json_like() -> None:
    private = run_audit(FIXTURES / "sessions_sparse_ppg.csv", ResourceLimits())
    kinds = {c.name: c.kind.value for c in private.columns}
    assert kinds["ppg_json"] == "json_like"
    jc = next(j for j in private.json_columns if j.name == "ppg_json")
    assert jc.populated_row_count == 1
    assert jc.empty_row_count >= 9


def test_missing_columns_no_crash() -> None:
    private = run_audit(FIXTURES / "sessions_missing_columns.csv", ResourceLimits())
    assert private.meta.row_count == 1
    assert private.meta.column_count == 2

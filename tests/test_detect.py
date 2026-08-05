"""Tests for JSON-like column detection."""

from src.audit.detect import classify_column
from src.audit.models import ColumnKind


def test_empty_array_and_object_are_json() -> None:
    assert classify_column("payload", ["[]", ""]) == ColumnKind.JSON_LIKE
    assert classify_column("payload", ["{}", ""]) == ColumnKind.JSON_LIKE


def test_json_suffix() -> None:
    assert classify_column("ppg_json", ["", "", ""]) == ColumnKind.ORDINARY
    assert classify_column("ppg_json", ["{broken", "", ""]) == ColumnKind.MIXED_MALFORMED
    assert classify_column("ppg_json", ['{"a":1}', "", ""]) == ColumnKind.JSON_LIKE


def test_sparse_one_of_ten() -> None:
    cells = [""] * 9 + ['{"samples": [1, 2]}']
    assert classify_column("ppg_json", cells) == ColumnKind.JSON_LIKE


def test_mixed_malformed() -> None:
    cells = ['{"ok": true}', "{not-json"]
    assert classify_column("data_json", cells) == ColumnKind.MIXED_MALFORMED


def test_ordinary_text() -> None:
    assert classify_column("patient_name", ["Ada", "Bob"]) == ColumnKind.ORDINARY


def test_ignores_empty_when_classifying() -> None:
    cells = ["", "null", "[]"]
    assert classify_column("x", cells) == ColumnKind.JSON_LIKE

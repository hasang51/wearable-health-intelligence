"""Tests for defensive JSON cell parsing."""

from src.audit.json_parse import CellParseStatus, parse_cell


def test_null_and_empty() -> None:
    assert parse_cell(None)[0] == CellParseStatus.NULL
    assert parse_cell("")[0] == CellParseStatus.EMPTY
    assert parse_cell("   ")[0] == CellParseStatus.EMPTY
    assert parse_cell("null")[0] == CellParseStatus.EMPTY


def test_empty_containers() -> None:
    assert parse_cell("[]")[0] == CellParseStatus.EMPTY_ARRAY
    assert parse_cell("{}")[0] == CellParseStatus.EMPTY_OBJECT


def test_object_and_array() -> None:
    st, val = parse_cell('{"a": 1}')
    assert st == CellParseStatus.OBJECT
    assert isinstance(val, dict)
    st, val = parse_cell("[1, 2, 3]")
    assert st == CellParseStatus.ARRAY
    assert val == [1, 2, 3]


def test_nested() -> None:
    st, val = parse_cell('{"x": [{"y": []}]}')
    assert st == CellParseStatus.OBJECT
    assert val["x"][0]["y"] == []


def test_malformed() -> None:
    assert parse_cell("{not-json")[0] == CellParseStatus.MALFORMED
    assert parse_cell("[1,2,")[0] == CellParseStatus.MALFORMED

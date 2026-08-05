"""Tests for resource limits helpers."""

from src.audit.limits import ResourceLimits


def test_defaults() -> None:
    lim = ResourceLimits()
    d = lim.as_dict()
    assert d["max_json_depth"] == 8
    assert d["max_keys_per_object"] == 200
    assert d["max_array_elements_inspected"] == 50
    assert d["csv_field_size_limit"] == 10 * 1024 * 1024


def test_override() -> None:
    lim = ResourceLimits(max_json_depth=3, max_array_elements_inspected=5)
    assert lim.max_json_depth == 3
    assert lim.max_array_elements_inspected == 5

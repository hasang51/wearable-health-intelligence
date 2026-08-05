"""Tests for bounded structure walker."""

from src.audit.limits import ResourceLimits
from src.audit.privacy import DYNAMIC_KEY_TOKEN
from src.audit.walk import walk_value


def test_walk_collects_paths_without_values() -> None:
    payload = {"samples": [1.0, 2.0, 3.0], "meta": {"sensor": "ppg"}}
    acc = walk_value(payload, ResourceLimits(max_array_elements_inspected=2))
    assert "samples" in acc.key_paths
    assert "meta.sensor" in acc.key_paths
    # Accumulator stores type histograms / lengths only — not sample value lists.
    assert not hasattr(acc, "values")
    assert acc.total_length_observed == 3
    assert acc.elements_structurally_inspected == 2
    assert acc.sample_count_estimate == 3


def test_depth_limit() -> None:
    nested: dict = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
    acc = walk_value(nested, ResourceLimits(max_json_depth=2))
    assert acc.hit_depth_limit is True


def test_key_limit() -> None:
    obj = {f"k{i}": i for i in range(10)}
    acc = walk_value(obj, ResourceLimits(max_keys_per_object=3))
    assert acc.hit_key_limit is True
    assert len([p for p in acc.key_paths if p.startswith("k")]) <= 3


def test_dynamic_key_redaction() -> None:
    payload = {
        "AA:BB:CC:DD:EE:FF": {"samples": [1]},
        "samples": [1, 2],
    }
    acc = walk_value(payload, ResourceLimits())
    assert any(DYNAMIC_KEY_TOKEN in p for p in acc.key_paths)
    assert "samples" in acc.key_paths


def test_timestamp_unit_known() -> None:
    payload = {"time_ms": [1000, 2000], "timestamp": [1, 2]}
    acc = walk_value(payload, ResourceLimits())
    assert any(p.endswith("time_ms") or p == "time_ms" for p in acc.timestamp_fields)
    # time_ms should be unit_known True
    assert acc.timestamp_fields.get("time_ms") is True
    # bare timestamp → unit unknown
    assert acc.timestamp_fields.get("timestamp") is False

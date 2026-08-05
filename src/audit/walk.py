"""Bounded recursive JSON structure walker."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.audit.keys import KeyCardinalityTracker, redact_key
from src.audit.limits import ResourceLimits
from src.audit.privacy import DYNAMIC_KEY_TOKEN
from src.audit.tokens import is_timestamp_field, timestamp_unit_hint


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


@dataclass
class WalkAccumulator:
    """Structural statistics only — never stores raw physiological values."""

    key_paths: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    path_occurrences: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    array_lengths: list[int] = field(default_factory=list)
    total_length_observed: int = 0
    elements_structurally_inspected: int = 0
    timestamp_fields: dict[str, bool] = field(default_factory=dict)
    hit_depth_limit: bool = False
    hit_key_limit: bool = False
    sample_count_estimate: int = 0


def walk_value(
    value: Any,
    limits: ResourceLimits,
    *,
    path_segments: list[str] | None = None,
    depth: int = 0,
    acc: WalkAccumulator | None = None,
    cardinality: KeyCardinalityTracker | None = None,
) -> WalkAccumulator:
    """Walk a parsed JSON value collecting redacted paths and type histograms."""
    if acc is None:
        acc = WalkAccumulator()
    if cardinality is None:
        cardinality = KeyCardinalityTracker()
    if path_segments is None:
        path_segments = []

    if depth > limits.max_json_depth:
        acc.hit_depth_limit = True
        return acc

    path = _format_path(path_segments)
    tname = _type_name(value)
    if path:
        acc.key_paths[path][tname] += 1
        acc.path_occurrences[path] += 1
        leaf = ""
        for seg in reversed(path_segments):
            if seg != "[]":
                leaf = seg
                break
        if leaf and leaf != DYNAMIC_KEY_TOKEN and is_timestamp_field(leaf):
            unit = timestamp_unit_hint(leaf)
            acc.timestamp_fields[path] = unit is not None

    if isinstance(value, dict):
        parent = path
        items = list(value.items())
        if len(items) > limits.max_keys_per_object:
            acc.hit_key_limit = True
            items = items[: limits.max_keys_per_object]
        for raw_key, child in items:
            key_str = str(raw_key)
            high_card = cardinality.observe(parent, key_str)
            if high_card or cardinality.should_redact(parent, key_str):
                safe_key = DYNAMIC_KEY_TOKEN
            else:
                safe_key = redact_key(key_str)
            walk_value(
                child,
                limits,
                path_segments=[*path_segments, safe_key],
                depth=depth + 1,
                acc=acc,
                cardinality=cardinality,
            )
        return acc

    if isinstance(value, list):
        total = len(value)
        acc.array_lengths.append(total)
        acc.total_length_observed += total
        inspect_n = min(total, limits.max_array_elements_inspected)
        acc.elements_structurally_inspected += inspect_n
        if total > 0 and inspect_n > 0:
            sample_like = all(
                isinstance(value[i], (int, float, str, bool, type(None)))
                for i in range(inspect_n)
            )
            if sample_like:
                acc.sample_count_estimate += total
        for i in range(inspect_n):
            walk_value(
                value[i],
                limits,
                path_segments=[*path_segments, "[]"],
                depth=depth + 1,
                acc=acc,
                cardinality=cardinality,
            )
        return acc

    return acc


def _format_path(segments: list[str]) -> str:
    if not segments:
        return ""
    parts: list[str] = []
    for seg in segments:
        if seg == "[]":
            if parts:
                parts[-1] = parts[-1] + "[]"
            else:
                parts.append("[]")
        else:
            parts.append(seg)
    return ".".join(parts)

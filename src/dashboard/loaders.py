"""Load and validate explicit safe aggregate JSON paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.dashboard import SCHEMA_VERSION
from src.dashboard.models import SafePhase1Input, SafePhase2Input, SafePhase3Input
from src.dashboard.privacy import assert_safe_json_path
from src.delivery_export.models import ReviewedDashboardBundle


class SafeReportLoadError(ValueError):
    """Invalid, unknown-version, or malformed safe report."""


def _read_json(path: Path) -> dict[str, Any]:
    safe = assert_safe_json_path(path)
    with safe.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SafeReportLoadError(f"Safe report root must be a JSON object: {safe}")
    return data


def _reject_unknown_version_if_present(data: dict[str, Any], path: Path) -> None:
    if "schema_version" in data:
        ver = data["schema_version"]
        if ver != SCHEMA_VERSION:
            raise SafeReportLoadError(
                f"Unknown or unsupported schema_version {ver!r} in {path.name}. "
                f"Expected {SCHEMA_VERSION!r} or a legacy Phase 1–3 safe report "
                f"(no schema_version field)."
            )


def load_raw_safe_json(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    _reject_unknown_version_if_present(data, path)
    return data


def is_v1_schema(data: dict[str, Any]) -> bool:
    return data.get("schema_version") == SCHEMA_VERSION


def load_phase1_v1(path: Path) -> SafePhase1Input:
    data = load_raw_safe_json(path)
    if not is_v1_schema(data):
        raise SafeReportLoadError(f"Not a {SCHEMA_VERSION} Phase 1 report: {path.name}")
    try:
        return SafePhase1Input.model_validate(data)
    except ValidationError as exc:
        raise SafeReportLoadError(f"Malformed Phase 1 v1 report: {exc}") from exc


def load_phase2_v1(path: Path) -> SafePhase2Input:
    data = load_raw_safe_json(path)
    if not is_v1_schema(data):
        raise SafeReportLoadError(f"Not a {SCHEMA_VERSION} Phase 2 report: {path.name}")
    try:
        return SafePhase2Input.model_validate(data)
    except ValidationError as exc:
        raise SafeReportLoadError(f"Malformed Phase 2 v1 report: {exc}") from exc


def load_phase3_v1(path: Path) -> SafePhase3Input:
    data = load_raw_safe_json(path)
    if not is_v1_schema(data):
        raise SafeReportLoadError(f"Not a {SCHEMA_VERSION} Phase 3 report: {path.name}")
    try:
        return SafePhase3Input.model_validate(data)
    except ValidationError as exc:
        raise SafeReportLoadError(f"Malformed Phase 3 v1 report: {exc}") from exc


def load_reviewed_bundle(path: Path) -> ReviewedDashboardBundle:
    """Load one allowlisted reviewed dashboard bundle. Fail closed — no demo fallback."""
    try:
        safe = assert_safe_json_path(Path(path))
    except FileNotFoundError as exc:
        raise SafeReportLoadError(
            f"Reviewed safe bundle not found: {Path(path).name}"
        ) from exc
    except ValueError as exc:
        raise SafeReportLoadError(str(exc)) from exc

    try:
        with safe.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SafeReportLoadError(
            f"Cannot read reviewed safe bundle ({safe.name}): {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SafeReportLoadError(
            f"Reviewed safe bundle root must be a JSON object: {safe.name}"
        )

    ver = data.get("schema_version")
    if ver != SCHEMA_VERSION:
        raise SafeReportLoadError(
            f"Unknown or unsupported schema_version {ver!r} in reviewed safe bundle. "
            f"Expected {SCHEMA_VERSION!r}."
        )

    try:
        return ReviewedDashboardBundle.model_validate(data)
    except ValidationError as exc:
        raise SafeReportLoadError(
            f"Reviewed-bundle validation error: {exc}"
        ) from exc

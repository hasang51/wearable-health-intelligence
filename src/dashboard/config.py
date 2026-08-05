"""Dashboard CLI / config — explicit demo or reviewed safe-bundle only."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.delivery_export import SOURCE_LABEL

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"
# Retained for delivery_export / fixture builders that still reference curated phases.
REVIEWED_DIR = (
    Path(__file__).resolve().parents[2] / "reports" / "delivery" / "reviewed_safe"
)

# Local reviewed-mode selector. When set, loads that exact safe bundle path.
SAFE_BUNDLE_ENV = "WEARABLE_DASHBOARD_SAFE_BUNDLE"

BANNER_DEMO = "SYNTHETIC DEMO - NOT PROJECT RESULTS"
BANNER_REVIEWED = SOURCE_LABEL


class SourceMode(str, Enum):
    DEMO = "demo"
    REVIEWED = "reviewed"


class DashboardConfigError(ValueError):
    """Invalid dashboard launch configuration (mode selection)."""


@dataclass(frozen=True)
class DashboardLaunchConfig:
    """Operator-supplied dashboard inputs. No directory scanning."""

    source_mode: SourceMode
    safe_bundle: Path | None = None

    @property
    def demo(self) -> bool:
        return self.source_mode == SourceMode.DEMO

    @property
    def is_project_results(self) -> bool:
        return self.source_mode == SourceMode.REVIEWED

    def banner_text(self) -> str:
        if self.source_mode == SourceMode.DEMO:
            return BANNER_DEMO
        return BANNER_REVIEWED


# Backward-compatible alias used across the package and tests.
DashboardConfig = DashboardLaunchConfig


def env_safe_bundle_path() -> Path | None:
    """Return the reviewed safe-bundle path from the environment, if set."""
    raw = os.environ.get(SAFE_BUNDLE_ENV)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return Path(stripped)


def extract_dashboard_argv(argv: list[str] | None = None) -> list[str]:
    """Extract dashboard CLI tokens from Streamlit or plain argv.

    When ``--`` is present, only tokens after it are considered. Does not
    invent a default mode — callers must pass ``--demo``, ``--safe-bundle``,
    or set ``WEARABLE_DASHBOARD_SAFE_BUNDLE``.
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:
        raw = raw[raw.index("--") + 1 :]

    out: list[str] = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--demo":
            out.append(a)
        elif a == "--safe-bundle":
            out.append(a)
            if i + 1 < len(raw) and not raw[i + 1].startswith("-"):
                out.append(raw[i + 1])
                i += 1
        i += 1
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 4 evidence dashboard. Exactly one input mode is required: "
            "--demo, --safe-bundle PATH, or WEARABLE_DASHBOARD_SAFE_BUNDLE. "
            "No raw CSV, private reports, directory scanning, or network."
        )
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Load bundled synthetic demo aggregates (development only)",
    )
    parser.add_argument(
        "--safe-bundle",
        type=Path,
        default=None,
        help=(
            "Path to one allowlisted reviewed dashboard.safe.v1 JSON bundle "
            "(ReviewedDashboardBundle). Overridden by "
            f"{SAFE_BUNDLE_ENV} when that environment variable is set."
        ),
    )
    return parser


def resolve_dashboard_mode(argv: list[str] | None = None) -> DashboardLaunchConfig:
    """Resolve launch mode from env and/or argv without starting Streamlit.

    Resolution order:

    1. If ``WEARABLE_DASHBOARD_SAFE_BUNDLE`` is set → reviewed (that exact path).
       Conflict with ``--demo`` is a configuration error.
    2. Else if ``--demo`` → demo.
    3. Else if ``--safe-bundle PATH`` → reviewed.
    4. Else → configuration error.

    Raises ``DashboardConfigError`` when both demo and reviewed selectors are
    present, or when neither is present.
    """
    tokens = list(argv) if argv is not None else extract_dashboard_argv()
    parser = build_parser()
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        raise DashboardConfigError(
            "Invalid dashboard arguments. Provide exactly one of "
            f"--demo, --safe-bundle PATH, or {SAFE_BUNDLE_ENV}."
        ) from exc

    demo = bool(args.demo)
    cli_bundle = args.safe_bundle
    env_bundle = env_safe_bundle_path()

    if env_bundle is not None and demo:
        raise DashboardConfigError(
            f"Conflicting dashboard modes: {SAFE_BUNDLE_ENV} selects reviewed "
            "mode while --demo was also supplied."
        )

    if env_bundle is not None:
        # Environment variable takes precedence for local reviewed execution.
        return DashboardLaunchConfig(
            source_mode=SourceMode.REVIEWED,
            safe_bundle=env_bundle,
        )

    has_cli_bundle = cli_bundle is not None

    if demo and has_cli_bundle:
        raise DashboardConfigError(
            "Provide exactly one of --demo or --safe-bundle PATH (both were given)."
        )
    if not demo and not has_cli_bundle:
        raise DashboardConfigError(
            "Provide exactly one of --demo, --safe-bundle PATH, or "
            f"{SAFE_BUNDLE_ENV} (neither was given)."
        )

    if demo:
        return DashboardLaunchConfig(source_mode=SourceMode.DEMO, safe_bundle=None)

    assert cli_bundle is not None  # for type checkers
    return DashboardLaunchConfig(
        source_mode=SourceMode.REVIEWED,
        safe_bundle=Path(cli_bundle),
    )


def parse_dashboard_args(argv: list[str] | None = None) -> DashboardLaunchConfig:
    """Parse dashboard CLI args (alias of :func:`resolve_dashboard_mode`)."""
    return resolve_dashboard_mode(argv)

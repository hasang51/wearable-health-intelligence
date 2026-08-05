"""CLI for local reviewed-dashboard bundle export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.delivery_export.export import DeliveryExportError, export_reviewed_dashboard_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bundle three explicit Phase 1–3 safe aggregate JSON reports into one "
            "allowlisted dashboard.safe.v1 JSON. Never reads CSV, parquet, private "
            "reports, or directories. Does not recompute Phase 1–3 science."
        )
    )
    parser.add_argument(
        "--phase1-safe",
        type=Path,
        required=True,
        help="Path to Phase 1 safe aggregate JSON (legacy or dashboard.safe.v1)",
    )
    parser.add_argument(
        "--phase2-safe",
        type=Path,
        required=True,
        help="Path to Phase 2 safe aggregate JSON (legacy or dashboard.safe.v1)",
    )
    parser.add_argument(
        "--phase3-safe",
        type=Path,
        required=True,
        help="Path to Phase 3 safe aggregate JSON (legacy or dashboard.safe.v1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the allowlisted dashboard.safe.v1 JSON bundle",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        out = export_reviewed_dashboard_bundle(
            phase1_path=args.phase1_safe,
            phase2_path=args.phase2_safe,
            phase3_path=args.phase3_safe,
            output_path=args.output,
        )
    except (DeliveryExportError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"delivery_export error: {exc}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

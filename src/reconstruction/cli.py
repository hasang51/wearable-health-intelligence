"""CLI entrypoint for Phase 3 candidate reconstruction."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from src.audit.logging_config import configure_logging
from src.audit.privacy import SCRUBBER, ScrubbedException
from src.reconstruction.reports import ReconstructionConfig, run_reconstruction, write_outputs

logger = logging.getLogger("src.audit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.reconstruction",
        description=(
            "Phase 3 candidate PPG reconstruction, decoder refinement, and "
            "signal-quality evidence. Reads only the explicit --input path. "
            "Writes private/safe artifacts only to explicit output directories."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Explicit path to the CSV file (no directory search or glob).",
    )
    parser.add_argument(
        "--private-dir",
        required=True,
        help="Explicit directory for private JSON/parquet/plots.",
    )
    parser.add_argument(
        "--safe-dir",
        required=True,
        help="Explicit directory for safe summary JSON and markdown.",
    )
    parser.add_argument("--expected-payload-length", type=int, default=66)
    parser.add_argument("--signedness", default="int24", choices=["int24", "uint24"])
    parser.add_argument(
        "--byte-order",
        default="CAB",
        choices=["ABC", "ACB", "BAC", "BCA", "CAB", "CBA"],
    )
    parser.add_argument(
        "--phase2-summary",
        default=None,
        help="Optional path to Phase 2 packet_spec_summary.json for rate gates.",
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="Optional explicit external BUT PPG root (never auto-discovered).",
    )
    parser.add_argument("--benchmark-seed", type=int, default=0)
    parser.add_argument("--vendor-documented", action="store_true")
    parser.add_argument("--allow-private-snippets", action="store_true")
    parser.add_argument("--csv-field-size-limit", type=int, default=10 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()

    SCRUBBER.register_input_path(args.input)
    if args.benchmark_dir:
        SCRUBBER.register_input_path(args.benchmark_dir)
    if args.phase2_summary:
        SCRUBBER.register_input_path(args.phase2_summary)

    # Workspace root for benchmark isolation check
    workspace_root = Path(__file__).resolve().parents[2]

    config = ReconstructionConfig(
        expected_payload_length=args.expected_payload_length,
        signedness=args.signedness,
        byte_order=args.byte_order,
        vendor_documented=args.vendor_documented,
        allow_private_snippets=args.allow_private_snippets,
        csv_field_size_limit=args.csv_field_size_limit,
        phase2_summary_path=args.phase2_summary,
        benchmark_dir=args.benchmark_dir,
        benchmark_seed=args.benchmark_seed,
        workspace_root=workspace_root,
    )

    try:
        input_path = Path(args.input)
        if input_path.exists() and input_path.is_dir():
            raise ScrubbedException("Input must be a file path, not a directory", SCRUBBER)
        if not input_path.is_file():
            raise ScrubbedException("Input is not a readable file: <input_path>", SCRUBBER)

        logger.info("Starting Phase 3 reconstruction for %s", "<input_path>")
        result = run_reconstruction(input_path, config)
        write_outputs(result, args.private_dir, args.safe_dir, config)
        print(
            SCRUBBER.scrub(
                f"phase3_complete sessions={result.session_count} "
                f"packets={result.packet_count} "
                f"rate_status={result.rate_report.rate_status.value}"
            )
        )
        return 0
    except ScrubbedException as exc:
        logger.error("%s", str(exc))
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Phase 3 reconstruction failed")
        wrapped = ScrubbedException(f"Phase 3 failed: {exc}", SCRUBBER)
        print(str(wrapped), file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entrypoint for PPG packet forensics."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from src.audit.logging_config import configure_logging
from src.audit.privacy import SCRUBBER, ScrubbedException
from src.forensics.reports import ForensicsConfig, run_forensics, write_outputs

logger = logging.getLogger("src.audit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.forensics",
        description=(
            "PPG packet forensics, decoder discovery, and timebase reconstruction. "
            "Reads only the explicit --input path. Writes private/safe artifacts only "
            "to explicit output directories (use an external secure directory for real data)."
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
        help="Explicit directory for private JSON reports and plots.",
    )
    parser.add_argument(
        "--safe-dir",
        required=True,
        help="Explicit directory for safe summary JSON and decision markdown.",
    )
    parser.add_argument("--expected-payload-length", type=int, default=66)
    parser.add_argument("--gap-threshold-ms", type=int, default=1500)
    parser.add_argument(
        "--samples-per-packet",
        type=int,
        default=None,
        help="Explicit samples-per-packet hypothesis enabling estimated_sample_timestamp.",
    )
    parser.add_argument("--max-plot-candidates", type=int, default=5)
    parser.add_argument(
        "--vendor-documented",
        action="store_true",
        help="Operator asserts vendor documentation supports decoder acceptance.",
    )
    parser.add_argument(
        "--allow-private-snippets",
        action="store_true",
        help="Allow demeaned scaled private snippet inset on boundary plot (fixtures/tests).",
    )
    parser.add_argument("--csv-field-size-limit", type=int, default=10 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()

    SCRUBBER.register_input_path(args.input)
    logger.info("CLI parsed")

    config = ForensicsConfig(
        expected_payload_length=args.expected_payload_length,
        gap_threshold_ms=args.gap_threshold_ms,
        samples_per_packet=args.samples_per_packet,
        vendor_documented=args.vendor_documented,
        max_plot_candidates=args.max_plot_candidates,
        allow_private_snippets=args.allow_private_snippets,
        csv_field_size_limit=args.csv_field_size_limit,
    )

    try:
        input_path = Path(args.input)
        if input_path.exists() and input_path.is_dir():
            raise ScrubbedException("Input must be a file path, not a directory", SCRUBBER)
        if not input_path.is_file():
            raise ScrubbedException("Input is not a readable file: <input_path>", SCRUBBER)

        logger.info("Input path validated")
        logger.info("Starting forensics for %s", "<input_path>")
        result = run_forensics(input_path, config)
        logger.info(
            "Extraction completed (sessions=%s packets=%s candidates=%s)",
            result.session_count,
            result.packet_count,
            result.candidate_count,
        )
        write_outputs(result, args.private_dir, args.safe_dir, config)

        logger.info(
            "Wrote forensics reports (sessions=%s packets=%s candidates=%s)",
            result.session_count,
            result.packet_count,
            result.candidate_count,
        )
        print(
            SCRUBBER.scrub(
                f"forensics_complete sessions={result.session_count} "
                f"packets={result.packet_count} candidates={result.candidate_count}"
            )
        )
        return 0
    except ScrubbedException as exc:
        logger.error("%s", str(exc))
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Forensics failed")
        wrapped = ScrubbedException(f"Forensics failed: {exc}", SCRUBBER)
        print(str(wrapped), file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

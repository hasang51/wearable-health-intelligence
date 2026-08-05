"""CLI entrypoint for the secure local data-audit pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.audit.limits import ResourceLimits
from src.audit.logging_config import configure_logging
from src.audit.privacy import SCRUBBER, ScrubbedException
from src.audit.reports import run_audit, to_safe_profile, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.audit",
        description=(
            "Secure local structural audit for wearable-health session CSVs. "
            "Reads only the explicit --input path. Writes reports only to "
            "explicit output paths (use an external secure directory for real data)."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Explicit path to the CSV file (no directory search or glob).",
    )
    parser.add_argument(
        "--private-output",
        required=True,
        help="Explicit path for the private data profile JSON.",
    )
    parser.add_argument(
        "--safe-output",
        required=True,
        help="Explicit path for the safe schema profile JSON.",
    )
    parser.add_argument("--max-json-depth", type=int, default=8)
    parser.add_argument("--max-keys-per-object", type=int, default=200)
    parser.add_argument("--max-array-elements-inspected", type=int, default=50)
    parser.add_argument("--csv-field-size-limit", type=int, default=10 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = configure_logging()

    SCRUBBER.register_input_path(args.input)

    limits = ResourceLimits(
        max_json_depth=args.max_json_depth,
        max_keys_per_object=args.max_keys_per_object,
        max_array_elements_inspected=args.max_array_elements_inspected,
        csv_field_size_limit=args.csv_field_size_limit,
    )

    try:
        # Open only the explicit input path — never glob or search.
        input_path = Path(args.input)
        if input_path.exists() and input_path.is_dir():
            raise ScrubbedException("Input must be a file path, not a directory", SCRUBBER)

        logger.info("Starting audit for %s", "<input_path>")
        private = run_audit(input_path, limits)
        safe = to_safe_profile(private)

        write_json(args.private_output, private.model_dump(mode="json"))
        write_json(args.safe_output, safe.model_dump(mode="json"))

        logger.info(
            "Wrote private and safe profiles (%s rows, %s columns)",
            private.meta.row_count,
            private.meta.column_count,
        )
        # stdout: counts only, scrubbed
        print(
            SCRUBBER.scrub(
                f"audit_complete rows={private.meta.row_count} columns={private.meta.column_count}"
            )
        )
        return 0
    except ScrubbedException as exc:
        msg = str(exc)
        print(SCRUBBER.scrub(msg), file=sys.stderr)
        logger.error("%s", msg)
        return 1
    except Exception as exc:  # noqa: BLE001
        msg = SCRUBBER.scrub(f"audit_failed: {exc}")
        print(msg, file=sys.stderr)
        logger.error("%s", msg)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

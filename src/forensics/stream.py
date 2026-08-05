"""Stream session rows from an explicit CSV path only."""

from __future__ import annotations

import csv
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from src.audit.privacy import SCRUBBER, ScrubbedException

logger = logging.getLogger("src.audit")

RAW_PACKETS_COLUMN = "raw_packets_json"
DEFAULT_CSV_FIELD_SIZE_LIMIT = 10 * 1024 * 1024


def stream_sessions(
    input_path: str | Path,
    *,
    csv_field_size_limit: int = DEFAULT_CSV_FIELD_SIZE_LIMIT,
) -> Iterator[tuple[int, str]]:
    """Yield (session_ordinal, raw_packets_json_cell) one row at a time.

    Opens only the explicit file path. Rejects directories. Does not glob,
    search parents, or discover alternate files.
    """
    path = Path(input_path)
    if path.exists() and path.is_dir():
        raise ScrubbedException("Input must be a file path, not a directory", SCRUBBER)
    if not path.is_file():
        raise ScrubbedException("Input is not a readable file: <input_path>", SCRUBBER)

    try:
        csv.field_size_limit(csv_field_size_limit)
    except OverflowError:
        csv.field_size_limit(sys.maxsize)

    try:
        header_df = pd.read_csv(
            path,
            dtype=str,
            nrows=0,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to read CSV header: {exc}", SCRUBBER) from None

    columns = [str(c) for c in header_df.columns.tolist()]
    if RAW_PACKETS_COLUMN not in columns:
        raise ScrubbedException(
            f"Required column missing: {RAW_PACKETS_COLUMN}",
            SCRUBBER,
        )
    logger.info("CSV header validated (columns=%s)", len(columns))

    try:
        reader = pd.read_csv(
            path,
            dtype=str,
            chunksize=1,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed to open CSV: {exc}", SCRUBBER) from None

    ordinal = 0
    retained_payload_arrays = 0  # instrumentation hook for streaming tests
    try:
        for chunk in reader:
            cell = ""
            if RAW_PACKETS_COLUMN in chunk.columns:
                val = chunk.iloc[0][RAW_PACKETS_COLUMN]
                cell = "" if val is None else str(val)
            yield ordinal, cell
            ordinal += 1
            # Explicitly do not retain prior session cells.
            retained_payload_arrays = 0
            _ = retained_payload_arrays
    except ScrubbedException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ScrubbedException(f"Failed while reading CSV rows: {exc}", SCRUBBER) from None

"""Streaming CSV reader — explicit path only, string dtypes, chunksize=1."""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from src.audit.limits import ResourceLimits
from src.audit.privacy import SCRUBBER, ScrubbedException


def open_csv_rows(
    input_path: str | Path,
    limits: ResourceLimits,
) -> tuple[list[str], Iterator[dict[str, str]]]:
    """Open an explicit CSV file path and yield one row dict at a time.

    Does not search directories, glob, follow symlinks for discovery, or
    inspect parent directories. Reads the given path only.
    """
    path = Path(input_path)
    # Do not resolve through parents for discovery; only open the given path.
    if not path.is_file():
        raise ScrubbedException(
            f"Input is not a readable file: {path}",
            SCRUBBER,
        )

    # Apply CSV field size limit (stdlib csv used by pandas engine).
    try:
        csv.field_size_limit(limits.csv_field_size_limit)
    except OverflowError:
        csv.field_size_limit(sys.maxsize)

    try:
        reader = pd.read_csv(
            path,
            dtype=str,
            chunksize=1,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 — scrub then re-raise
        raise ScrubbedException(f"Failed to open CSV: {exc}", SCRUBBER) from None

    # Peek first chunk for columns; re-open iterator cleanly.
    # pandas Text_csv with chunksize returns TextCsvReader; get fieldnames via header.
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

    def _row_iter() -> Iterator[dict[str, str]]:
        try:
            for chunk in reader:
                record: dict[str, str] = {}
                for col in columns:
                    val = chunk.iloc[0][col] if col in chunk.columns else ""
                    record[col] = "" if val is None else str(val)
                yield record
        except Exception as exc:  # noqa: BLE001
            raise ScrubbedException(f"Failed while reading CSV rows: {exc}", SCRUBBER) from None

    return columns, _row_iter()


def collect_column_samples(
    rows: list[dict[str, str]],
    columns: list[str],
) -> dict[str, list[str]]:
    """Gather per-column cell lists from already-streamed rows (for detection)."""
    out: dict[str, list[str]] = {c: [] for c in columns}
    for row in rows:
        for c in columns:
            out[c].append(row.get(c, ""))
    return out

"""Validate packet schema, dataType, payload length, and timestamp ordering."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from src.forensics.extract import ExtractedPacket, SessionExtract

EXPECTED_DATATYPE = "119"


@dataclass
class ValidationAccumulator:
    expected_payload_length: int = 66
    schema_ok_count: int = 0
    schema_anomaly_count: int = 0
    datatype_histogram: Counter[str] = field(default_factory=Counter)
    payload_length_histogram: Counter[str] = field(default_factory=Counter)
    validation_codes: Counter[str] = field(default_factory=Counter)
    malformed_nested_count: int = 0
    timestamp_regression_count: int = 0
    timestamp_duplicate_count: int = 0
    cell_malformed_count: int = 0
    cell_empty_count: int = 0

    def update_session(self, session: SessionExtract) -> None:
        if session.cell_malformed:
            self.cell_malformed_count += 1
            self.validation_codes["cell_malformed"] += 1
            return
        if session.cell_empty:
            self.cell_empty_count += 1
            self.validation_codes["cell_empty"] += 1
            return

        prev_ts: int | None = None
        for pkt in session.packets:
            self._update_packet(pkt)
            if pkt.received_at_ms is None:
                continue
            if prev_ts is not None:
                if pkt.received_at_ms < prev_ts:
                    self.timestamp_regression_count += 1
                    self.validation_codes["timestamp_regression"] += 1
                elif pkt.received_at_ms == prev_ts:
                    self.timestamp_duplicate_count += 1
                    self.validation_codes["timestamp_duplicate"] += 1
            prev_ts = pkt.received_at_ms

    def _update_packet(self, pkt: ExtractedPacket) -> None:
        for code in pkt.codes:
            self.validation_codes[code] += 1
            if code.startswith("ppg_"):
                self.malformed_nested_count += 1

        dt = pkt.data_type if pkt.data_type is not None else "<missing>"
        self.datatype_histogram[dt] += 1
        if pkt.data_type != EXPECTED_DATATYPE:
            self.validation_codes["datatype_unexpected"] += 1

        if pkt.ppg_values is None:
            self.schema_anomaly_count += 1
            self.payload_length_histogram["<missing>"] += 1
            return

        length = len(pkt.ppg_values)
        self.payload_length_histogram[str(length)] += 1
        if length != self.expected_payload_length:
            self.validation_codes["payload_length_mismatch"] += 1
            self.schema_anomaly_count += 1
        elif pkt.schema_ok and pkt.data_type == EXPECTED_DATATYPE:
            self.schema_ok_count += 1
        else:
            self.schema_anomaly_count += 1

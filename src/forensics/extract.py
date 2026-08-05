"""Extract nested PPG payloads from raw packet JSON cells."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

EXPECTED_TOP_KEYS = frozenset({"dataEnd", "dataType", "dicData", "receivedAtMs"})
EXPECTED_DIC_KEYS = frozenset({"PPG", "Time"})


@dataclass
class ExtractedPacket:
    """One packet after structural extraction (no clinical meaning)."""

    data_type: str | None
    data_end: Any
    received_at_ms: int | None
    nested_time: Any
    ppg_values: list[int] | None
    schema_ok: bool
    codes: list[str] = field(default_factory=list)


@dataclass
class SessionExtract:
    session_ordinal: int
    packets: list[ExtractedPacket]
    cell_malformed: bool = False
    cell_empty: bool = False


def _parse_ppg_payload(raw: Any) -> tuple[list[int] | None, list[str]]:
    codes: list[str] = []
    if raw is None:
        codes.append("ppg_missing")
        return None, codes
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            codes.append("ppg_json_malformed")
            return None, codes
    if not isinstance(value, list):
        codes.append("ppg_not_array")
        return None, codes
    ints: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            codes.append("ppg_non_integer")
            return None, codes
        if isinstance(item, float) and not item.is_integer():
            codes.append("ppg_non_integer")
            return None, codes
        ints.append(int(item))
    return ints, codes


def extract_packet(obj: Any) -> ExtractedPacket:
    codes: list[str] = []
    if not isinstance(obj, dict):
        return ExtractedPacket(
            data_type=None,
            data_end=None,
            received_at_ms=None,
            nested_time=None,
            ppg_values=None,
            schema_ok=False,
            codes=["packet_not_object"],
        )

    keys = set(obj.keys())
    if keys != EXPECTED_TOP_KEYS:
        missing = EXPECTED_TOP_KEYS - keys
        extra = keys - EXPECTED_TOP_KEYS
        if missing:
            codes.append("missing_top_keys")
        if extra:
            codes.append("extra_top_keys")

    data_type = obj.get("dataType")
    if data_type is not None and not isinstance(data_type, str):
        data_type = str(data_type)

    received_raw = obj.get("receivedAtMs")
    received_at_ms: int | None
    try:
        received_at_ms = int(received_raw) if received_raw is not None else None
    except (TypeError, ValueError):
        received_at_ms = None
        codes.append("received_at_invalid")

    dic = obj.get("dicData")
    nested_time: Any = None
    ppg_values: list[int] | None = None
    if not isinstance(dic, dict):
        codes.append("dicdata_missing")
    else:
        dic_keys = set(dic.keys())
        if not EXPECTED_DIC_KEYS.issubset(dic_keys):
            codes.append("dicdata_missing_keys")
        nested_time = dic.get("Time")
        ppg_values, ppg_codes = _parse_ppg_payload(dic.get("PPG"))
        codes.extend(ppg_codes)

    schema_ok = not any(
        c.startswith("packet_")
        or c.startswith("missing_")
        or c.startswith("dicdata_")
        or c.startswith("ppg_")
        or c == "received_at_invalid"
        or c == "extra_top_keys"
        for c in codes
    )
    # Allow schema_ok if only extra keys? Plan says expected keys — treat exact match preferred.
    if "extra_top_keys" in codes or "missing_top_keys" in codes:
        schema_ok = False
    if ppg_values is None:
        schema_ok = False

    return ExtractedPacket(
        data_type=data_type,
        data_end=obj.get("dataEnd"),
        received_at_ms=received_at_ms,
        nested_time=nested_time,
        ppg_values=ppg_values,
        schema_ok=schema_ok,
        codes=codes,
    )


def extract_session(session_ordinal: int, cell: str) -> SessionExtract:
    text = (cell or "").strip()
    if text == "" or text.lower() in {"null", "none", "nan"}:
        return SessionExtract(session_ordinal=session_ordinal, packets=[], cell_empty=True)

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return SessionExtract(
            session_ordinal=session_ordinal,
            packets=[],
            cell_malformed=True,
        )

    if not isinstance(parsed, list):
        return SessionExtract(
            session_ordinal=session_ordinal,
            packets=[],
            cell_malformed=True,
        )

    packets = [extract_packet(item) for item in parsed]
    return SessionExtract(session_ordinal=session_ordinal, packets=packets)

"""Generate synthetic CSV fixtures (run once during repo setup)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixtures"

PATIENT = "SYNTH_PATIENT_ADA_LOVELACE"
PROTOCOL = "PROTO-SYNTH-9999"
MAC = "AA:BB:CC:DD:EE:FF"
CONSENT = "CONSENT_BYTES_SYNTH_DEADBEEF"
TS_EXACT = "2024-06-15T14:30:00Z"
PHYSIO_SAMPLE = "987654.321"

# Distinctive synthetic ADC-like values for packet fixtures (not written to safe reports).
BASE_MS = 1_700_000_000_000


def write_csv(name: str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    print("wrote", path)


def _pack_abc(a: int, b: int, c: int) -> int:
    return ((a & 0xFF) << 16) | ((b & 0xFF) << 8) | (c & 0xFF)


def make_packet(
    *,
    received_at_ms: int,
    ppg: list[int] | str,
    nested_time: int | float | None = None,
    data_type: str = "119",
    data_end: bool = True,
    stringify_ppg: bool = False,
) -> dict:
    if nested_time is None:
        nested_time = received_at_ms
    ppg_payload: list[int] | str = json.dumps(ppg) if stringify_ppg else ppg
    return {
        "dataEnd": data_end,
        "dataType": data_type,
        "dicData": {"PPG": ppg_payload, "Time": nested_time},
        "receivedAtMs": received_at_ms,
    }


def smooth_channel(n: int, start: int, step: int) -> list[int]:
    return [start + i * step for i in range(n)]


def interleave_channels(channels: list[list[int]]) -> list[int]:
    total = sum(len(ch) for ch in channels)
    c = len(channels)
    out: list[int] = []
    idx = [0] * c
    phase = 0
    for _ in range(total):
        spun = 0
        while idx[phase] >= len(channels[phase]) and spun < c:
            phase = (phase + 1) % c
            spun += 1
        if spun >= c:
            break
        out.append(channels[phase][idx[phase]])
        idx[phase] += 1
        phase = (phase + 1) % c
    return out


def payload_66_from_c3(packet_index: int, phase_offset: int = 0) -> list[int]:
    """Build length-66 payload as continuous C=3 interleave of smooth channels."""
    # Generate enough samples for this packet given phase
    # For continuous phase across packets: each packet consumes 66 samples from stream
    # Channel streams are globally indexed.
    global_start = packet_index * 66
    # Produce 66 interleaved values starting at global sample index with phase
    channels = [
        smooth_channel(80, 1000 + 100 * ch, 3 + ch) for ch in range(3)
    ]
    # Build a long interleaved stream then slice
    long_stream = interleave_channels(
        [smooth_channel(200, 1000 + 100 * ch, 3 + ch) for ch in range(3)]
    )
    # continuous: start at global_start (phase naturally encoded in index)
    return long_stream[global_start : global_start + 66]


def write_packet_fixtures() -> None:
    cols = [
        "patient_name",
        "protocol_number",
        "device_mac",
        "consent_image_bytes",
        "raw_packets_json",
    ]

    # Valid: 2 sessions, monotonic timestamps, 66-int PPG (array + stringified forms)
    sessions_valid = []
    for s in range(2):
        packets = []
        for p in range(5):
            t = BASE_MS + s * 100_000 + p * 1000
            ppg = payload_66_from_c3(p + s * 5)
            packets.append(
                make_packet(
                    received_at_ms=t,
                    ppg=ppg,
                    nested_time=t,
                    stringify_ppg=(p % 2 == 1),
                )
            )
        sessions_valid.append(
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "raw_packets_json": json.dumps(packets),
            }
        )
    write_csv("packets_valid_66.csv", cols, sessions_valid)

    # Malformed nested PPG
    bad_packets = [
        make_packet(received_at_ms=BASE_MS, ppg=[1, 2, 3]),  # will replace
    ]
    bad_packets[0]["dicData"]["PPG"] = "{not-json"
    bad_packets.append(
        {
            "dataEnd": True,
            "dataType": "119",
            "dicData": {"PPG": ["x", "y"], "Time": BASE_MS},
            "receivedAtMs": BASE_MS + 1000,
        }
    )
    write_csv(
        "packets_malformed_nested.csv",
        cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "raw_packets_json": json.dumps(bad_packets),
            }
        ],
    )

    # Length mismatch
    short = make_packet(received_at_ms=BASE_MS, ppg=list(range(10)))
    long = make_packet(received_at_ms=BASE_MS + 1000, ppg=list(range(70)))
    write_csv(
        "packets_length_mismatch.csv",
        cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "raw_packets_json": json.dumps([short, long]),
            }
        ],
    )

    # Timestamp gaps, regression, duplicate
    gap_packets = [
        make_packet(received_at_ms=BASE_MS, ppg=payload_66_from_c3(0)),
        make_packet(received_at_ms=BASE_MS + 1000, ppg=payload_66_from_c3(1)),
        make_packet(received_at_ms=BASE_MS + 1000, ppg=payload_66_from_c3(2)),  # duplicate
        make_packet(received_at_ms=BASE_MS + 500, ppg=payload_66_from_c3(3)),  # regression
        make_packet(received_at_ms=BASE_MS + 500 + 3000, ppg=payload_66_from_c3(4)),  # gap > 1.5s
    ]
    write_csv(
        "packets_timestamp_gaps.csv",
        cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "raw_packets_json": json.dumps(gap_packets),
            }
        ],
    )

    # Phase continuity: C=3 continuous across packets, L=66 (66%3==0 so phase stays 0,
    # also include a second session note — for C=4 tests we use unit tests directly.
    # Here we still emit known C=3 stream for scoring preference.
    phase_packets = []
    for p in range(4):
        t = BASE_MS + p * 1000
        phase_packets.append(
            make_packet(received_at_ms=t, ppg=payload_66_from_c3(p), nested_time=t)
        )
    write_csv(
        "packets_phase_continuity.csv",
        cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "raw_packets_json": json.dumps(phase_packets),
            }
        ],
    )

    # Sensitive filename fixture for privacy path leakage
    sens_packets = [
        make_packet(
            received_at_ms=BASE_MS,
            ppg=[int(float(PHYSIO_SAMPLE))] + payload_66_from_c3(0)[1:],
        )
    ]
    # Embed exact ISO timestamp in an unused string field inside dicData? Keep schema;
    # put TS in patient columns and note field instead.
    sens_cols = cols + ["note_ts"]
    write_csv(
        "packets_sensitive_name_SYNTH.csv",
        sens_cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "note_ts": TS_EXACT,
                "raw_packets_json": json.dumps(sens_packets),
            }
        ],
    )


def main() -> None:
    ppg = {
        "samples": [0.1, 0.2, 0.3, float(PHYSIO_SAMPLE)],
        "time_ms": [1000, 1020, 1040, 1060],
        "meta": {"sensor": "ppg"},
    }
    acc = {
        "x": [0.0, 0.1],
        "y": [0.0, -0.1],
        "z": [1.0, 0.9],
        "time_ms": [1000, 1020],
    }
    hr = {"heartRate": [70, 72], "time_ms": [1000, 2000]}
    hrv = {"hrv": {"rmssd": [30.0]}, "values": [30.0, 31.0]}
    spo2 = {"spo2": [98, 97]}
    ecg = {"ecg": {"samples": [0.01, 0.02]}}
    temp = {"temperature": [36.5, 36.6]}
    sleep = {"sleep": {"stages": ["light", "deep"]}}
    activity = {"activity": {"steps": [100, 200]}}
    bp = {"bloodPressure": {"systolic": [120], "diastolic": [80]}}
    glucose = {"glucose": {"mg_dl": [90, 92]}}
    upload = {
        "chunks_sent": 10,
        "chunks_total": 10,
        "chunks_failed": 0,
        "pending": 0,
    }

    cols = [
        "patient_name",
        "protocol_number",
        "device_mac",
        "consent_image_bytes",
        "session_duration_s",
        "ppg_json",
        "accelerometer_json",
        "heart_rate_json",
        "hrv_json",
        "spo2_json",
        "ecg_json",
        "temperature_json",
        "sleep_json",
        "activity_json",
        "blood_pressure_json",
        "glucose_json",
        "upload_meta_json",
    ]
    write_csv(
        "sessions_valid.csv",
        cols,
        [
            {
                "patient_name": PATIENT,
                "protocol_number": PROTOCOL,
                "device_mac": MAC,
                "consent_image_bytes": CONSENT,
                "session_duration_s": "60",
                "ppg_json": json.dumps(ppg),
                "accelerometer_json": json.dumps(acc),
                "heart_rate_json": json.dumps(hr),
                "hrv_json": json.dumps(hrv),
                "spo2_json": json.dumps(spo2),
                "ecg_json": json.dumps(ecg),
                "temperature_json": json.dumps(temp),
                "sleep_json": json.dumps(sleep),
                "activity_json": json.dumps(activity),
                "blood_pressure_json": json.dumps(bp),
                "glucose_json": json.dumps(glucose),
                "upload_meta_json": json.dumps(upload),
            }
        ],
    )

    empty_row = {c: "" for c in cols}
    empty_row.update(
        {
            "patient_name": PATIENT,
            "protocol_number": PROTOCOL,
            "device_mac": MAC,
            "consent_image_bytes": CONSENT,
            "ppg_json": "[]",
            "accelerometer_json": "{}",
            "heart_rate_json": "",
            "hrv_json": "null",
            "ecg_json": "[]",
            "temperature_json": "{}",
            "activity_json": "[]",
            "glucose_json": "{}",
            "upload_meta_json": "{}",
        }
    )
    write_csv("sessions_empty.csv", cols, [empty_row])

    mal = dict(empty_row)
    mal["ppg_json"] = "{not-json"
    mal["heart_rate_json"] = '{"ok": true}'
    mal["hrv_json"] = "totally-broken"
    write_csv("sessions_malformed.csv", cols, [mal])

    inc = {
        "patient_name": PATIENT,
        "protocol_number": PROTOCOL,
        "device_mac": MAC,
        "consent_image_bytes": CONSENT,
        "chunks_sent": "8",
        "chunks_total": "10",
        "chunks_failed": "3",
        "upload_pending": "1",
        "ppg_json": json.dumps({"samples": [1.0, 2.0]}),
    }
    write_csv("sessions_incomplete_upload.csv", list(inc.keys()), [inc])

    irr_cols = [
        "patient_name",
        "protocol_number",
        "device_mac",
        "consent_image_bytes",
        "session_duration",
        "ppg_json",
    ]
    irr = {
        "patient_name": PATIENT,
        "protocol_number": PROTOCOL,
        "device_mac": MAC,
        "consent_image_bytes": CONSENT,
        "session_duration": "60",
        "ppg_json": json.dumps(
            {
                "samples": [0.1, 0.2, float(PHYSIO_SAMPLE)],
                "timestamp": [TS_EXACT, "2024-06-15T14:31:00Z"],
            }
        ),
    }
    write_csv("sessions_irregular_timestamps.csv", irr_cols, [irr])

    write_csv(
        "sessions_missing_columns.csv",
        ["session_id", "note"],
        [{"session_id": "S1", "note": "no modalities"}],
    )

    sens_cols = [
        "patient_name",
        "protocol_number",
        "device_mac",
        "consent_image_bytes",
        "ppg_json",
    ]
    sens = {
        "patient_name": PATIENT,
        "protocol_number": PROTOCOL,
        "device_mac": MAC,
        "consent_image_bytes": CONSENT,
        "ppg_json": json.dumps({"samples": [float(PHYSIO_SAMPLE)], "time_ms": [1000]}),
    }
    write_csv("sensitive_name_SYNTH_PATIENT_X.csv", sens_cols, [sens])

    sparse_cols = ["patient_name", "ppg_json", "note"]
    sparse_rows = []
    for i in range(10):
        sparse_rows.append(
            {
                "patient_name": PATIENT,
                "ppg_json": json.dumps({"samples": [1.0, 2.0]}) if i == 7 else "",
                "note": "x",
            }
        )
    write_csv("sessions_sparse_ppg.csv", sparse_cols, sparse_rows)

    write_packet_fixtures()


if __name__ == "__main__":
    main()

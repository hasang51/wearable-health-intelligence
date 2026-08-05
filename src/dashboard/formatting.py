"""Display formatting helpers for director-level presentation (no science)."""

from __future__ import annotations

from src.dashboard.status import NOT_AVAILABLE, is_available


def fmt_int(value: object | None) -> str:
    if not is_available(value):
        return NOT_AVAILABLE
    return f"{int(value):,}"


def fmt_ratio(value: float | None, *, decimals: int = 4) -> str:
    if value is None or not is_available(value):
        return NOT_AVAILABLE
    return f"{float(value):.{decimals}f}"


def fmt_corr(value: float | None, *, decimals: int = 3) -> str:
    if value is None or not is_available(value):
        return NOT_AVAILABLE
    return f"{float(value):.{decimals}f}"


def fmt_pct(value: float | None, *, decimals: int = 1) -> str:
    if value is None or not is_available(value):
        return NOT_AVAILABLE
    return f"{float(value):.{decimals}f}%"


def fmt_duration_ms(ms: float | int | None) -> str:
    """Format milliseconds; use seconds when >= 1000 ms."""
    if ms is None or not is_available(ms):
        return NOT_AVAILABLE
    v = float(ms)
    if abs(v) >= 1000.0:
        return f"{v / 1000.0:.1f} s"
    return f"{v:.0f} ms"


def fmt_count_pct(count: int, total: int, *, decimals: int = 1) -> str:
    if total <= 0:
        return f"{count} (NOT_AVAILABLE)"
    pct = 100.0 * count / total
    return f"{count}/{total} = {pct:.{decimals}f}%"


HYPOTHESIS_LABELS: dict[str, str] = {
    "H_2block_meta_per_ch:last_of_block": (
        "Two channels with one terminal field per channel block"
    ),
    "H_2x33": "Two channels with 33 values per channel",
    "H_2x32_plus_2global": "Two channels with 32 values plus two global fields",
    "H_3x22": "Three channels with 22 values per channel",
}


def hypothesis_human_label(hypothesis_id: str) -> str:
    return HYPOTHESIS_LABELS.get(hypothesis_id, hypothesis_id)


FAILED_CRITERIA_LABELS: dict[str, str] = {
    "frequency_agreement_below_partial": "Frequency agreement below partial threshold",
    "median_lagged_correlation_below_partial": (
        "Median lagged correlation below partial threshold"
    ),
    "median_coherence_below_partial": "Median coherence below partial threshold",
    "frequency_agreement_below_compatible": (
        "Frequency agreement below compatible threshold"
    ),
    "median_lagged_correlation_below_compatible": (
        "Median lagged correlation below compatible threshold"
    ),
    "median_coherence_below_compatible": "Median coherence below compatible threshold",
}


GATE_LABELS: dict[str, str] = {
    "decoder_status_insufficient": "Decoder status insufficient (not provisionally accepted)",
    "public_median_abs_hr_error_gate": "Public benchmark median absolute error gate",
    "public_coverage_gate": "Public benchmark coverage gate",
    "rate_estimates_unavailable": "Rate estimates unavailable",
    "channel_agreement_insufficient": "Channel agreement insufficient",
    "channel_agreement_partial_only": "Channel agreement only partial",
    "channel_agreement_not_evaluable": "Channel agreement not evaluable",
    "spectral_time_disagreement": "Spectral and time-domain disagreement",
}


def humanize_failed_criterion(code: str) -> str:
    return FAILED_CRITERIA_LABELS.get(code, code.replace("_", " "))


def humanize_gate(code: str) -> str:
    return GATE_LABELS.get(code, code.replace("_", " "))


MODALITY_INTERPRETATION: dict[str, str] = {
    "ppg": "Raw nested packet structure present for research decoding",
    "accelerometer": "Little or no usable accelerometer coverage in this corpus",
    "heart_rate": "No proprietary heart-rate field samples in safe aggregates",
    "hrv": "No HRV field samples in safe aggregates",
    "spo2": "No SpO2 field samples in safe aggregates",
    "ecg": "No ECG field samples in safe aggregates",
    "temperature": "No temperature field samples in safe aggregates",
    "sleep": "No sleep field samples in safe aggregates",
    "activity": "No activity field samples in safe aggregates",
    "blood_pressure": "No blood-pressure field samples in safe aggregates",
    "glucose": "No glucose field samples in safe aggregates",
}


def modality_table_rows(
    modality_coverage: list | dict,
    *,
    session_count: int | None = None,
) -> list[dict[str, str]]:
    if isinstance(modality_coverage, dict):
        fields = [
            (
                "raw_ppg_payload_sessions",
                "Raw optical/PPG payload",
                "Raw packet payload available for research decoding",
            ),
            (
                "normalized_ppg_sessions",
                "Normalized PPG stream",
                "Normalized PPG fields with samples",
            ),
            ("accelerometer_sessions", "Accelerometer", MODALITY_INTERPRETATION["accelerometer"]),
            ("heart_rate_sessions", "Heart rate", MODALITY_INTERPRETATION["heart_rate"]),
            ("hrv_sessions", "HRV", MODALITY_INTERPRETATION["hrv"]),
            ("spo2_sessions", "SpO2", MODALITY_INTERPRETATION["spo2"]),
            ("ecg_sessions", "ECG", MODALITY_INTERPRETATION["ecg"]),
            ("temperature_sessions", "Temperature", MODALITY_INTERPRETATION["temperature"]),
            ("sleep_sessions", "Sleep", MODALITY_INTERPRETATION["sleep"]),
            ("activity_sessions", "Activity", MODALITY_INTERPRETATION["activity"]),
            (
                "blood_pressure_sessions",
                "Blood pressure",
                MODALITY_INTERPRETATION["blood_pressure"],
            ),
        ]
        rows: list[dict[str, str]] = []
        for field, label, interpretation in fields:
            value = modality_coverage.get(field, NOT_AVAILABLE)
            unavailable = value == NOT_AVAILABLE
            empty = (
                NOT_AVAILABLE
                if unavailable or session_count is None
                else str(max(session_count - int(value), 0))
            )
            rows.append(
                {
                    "Modality": label,
                    "Sessions with samples": str(value),
                    "Sessions empty / unavailable": empty,
                    "Interpretation": interpretation,
                }
            )
        return rows

    rows: list[dict[str, str]] = []
    for item in modality_coverage:
        modality = item.modality if hasattr(item, "modality") else item["modality"]
        counts = (
            item.status_counts if hasattr(item, "status_counts") else item["status_counts"]
        )
        with_samples = int(counts.get("samples_present", 0))
        empty_unavailable = (
            int(counts.get("column_absent", 0))
            + int(counts.get("payload_empty", 0))
            + int(counts.get("payload_malformed", 0))
            + int(counts.get("structure_present_no_samples", 0))
            + int(counts.get("not_evaluable", 0))
        )
        rows.append(
            {
                "Modality": modality,
                "Sessions with samples": str(with_samples),
                "Sessions empty / unavailable": str(empty_unavailable),
                "Interpretation": MODALITY_INTERPRETATION.get(
                    modality, "See status counts in technical appendix"
                ),
            }
        )
    return rows

"""Tests for token-boundary and camelCase matching."""

from src.audit.tokens import (
    is_timestamp_field,
    match_modality,
    split_name_tokens,
    tokens_match,
    timestamp_unit_hint,
)


def test_split_camel_and_snake() -> None:
    assert "heart" in split_name_tokens("heartRate")
    assert "rate" in split_name_tokens("heartRate")
    assert split_name_tokens("heart_rate") == ["heart", "rate"]


def test_hr_does_not_match_hrv() -> None:
    assert tokens_match("hrv", "hr") is False
    assert "hrv" in match_modality("hrv_json")
    assert "heart_rate" not in match_modality("hrv_json")


def test_short_token_boundaries() -> None:
    assert tokens_match("accuracy", "acc") is False
    assert tokens_match("accelerometer", "acc") is False  # 'acc' alone vs full word
    # 'acc' as its own snake token should match accelerometer modality via token list
    assert "accelerometer" in match_modality("acc_json")
    assert tokens_match("timestamp", "ts") is False
    assert tokens_match("ts", "ts") is True
    assert is_timestamp_field("ts")
    assert is_timestamp_field("time_ms")
    assert is_timestamp_field("recorded_at")


def test_heart_rate_camel() -> None:
    assert "heart_rate" in match_modality("heartRate")
    assert "heart_rate" in match_modality("heart_rate_json")


def test_bp_token() -> None:
    assert "blood_pressure" in match_modality("bp_json")
    assert tokens_match("subtype", "bp") is False


def test_timestamp_unit_hint() -> None:
    assert timestamp_unit_hint("time_ms") == "ms"
    assert timestamp_unit_hint("epoch_s") == "s"
    assert timestamp_unit_hint("timestamp") is None

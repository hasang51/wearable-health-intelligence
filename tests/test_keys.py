"""Tests for key redaction."""

from src.audit.keys import is_sensitive_or_dynamic_key, redact_key
from src.audit.privacy import DYNAMIC_KEY_TOKEN


def test_uuid_mac_numeric_redacted() -> None:
    assert redact_key("550e8400-e29b-41d4-a716-446655440000") == DYNAMIC_KEY_TOKEN
    assert redact_key("AA:BB:CC:DD:EE:FF") == DYNAMIC_KEY_TOKEN
    assert redact_key("42") == DYNAMIC_KEY_TOKEN
    assert redact_key("3.14") == DYNAMIC_KEY_TOKEN


def test_identifier_like_keys() -> None:
    assert is_sensitive_or_dynamic_key("patient_name")
    assert is_sensitive_or_dynamic_key("device_mac")
    assert is_sensitive_or_dynamic_key("protocol_number")


def test_stable_structural_keys_kept() -> None:
    assert redact_key("samples") == "samples"
    assert redact_key("time_ms") == "time_ms"
    assert redact_key("meta") == "meta"


def test_long_hex_dynamic() -> None:
    assert redact_key("abcdef0123456789abcdef01") == DYNAMIC_KEY_TOKEN

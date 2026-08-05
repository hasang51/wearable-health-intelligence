"""Privacy and forbidden terminology tests for Phase 4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.config import DEMO_DIR
from src.dashboard.delivery.generate import DELIVERY_WRITERS, generate_delivery
from src.dashboard.privacy import assert_safe_json_path, find_privacy_leaks
from src.dashboard.terminology import FORBIDDEN_PHRASES, find_forbidden_phrases
from tests.conftest import FORBIDDEN_LITERALS


def _collect_dashboard_text() -> str:
    chunks: list[str] = []
    for path in DEMO_DIR.glob("safe_phase*.json"):
        chunks.append(path.read_text(encoding="utf-8"))
    views = Path("src/dashboard/views")
    for path in views.glob("*.py"):
        chunks.append(path.read_text(encoding="utf-8"))
    for name, fn in DELIVERY_WRITERS.items():
        chunks.append(fn())
    return "\n".join(chunks)


def test_demo_and_docs_no_forbidden_terminology() -> None:
    text = _collect_dashboard_text()
    found = find_forbidden_phrases(text)
    assert found == [], f"Forbidden phrases found: {found}"


def test_demo_no_fixture_literals() -> None:
    text = _collect_dashboard_text()
    for lit in FORBIDDEN_LITERALS:
        assert lit not in text, f"Leak of {lit!r}"


def test_demo_no_privacy_pattern_leaks() -> None:
    text = _collect_dashboard_text()
    assert find_privacy_leaks(text) == []


def test_generated_delivery_clean(tmp_path: Path) -> None:
    paths = generate_delivery(tmp_path)
    blob = "\n".join(p.read_text(encoding="utf-8") for p in paths)
    assert find_forbidden_phrases(blob) == []
    assert "UNVERIFIED" in blob
    assert "INSUFFICIENT_CHANNEL_AGREEMENT" in blob
    assert "NOT_COMPUTED" in blob
    assert "8161" in blob
    assert "47111" in blob


def test_never_opens_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "secret.csv"
    csv_path.write_text("id,value\nPATIENT,1\n", encoding="utf-8")
    opened: list[str] = []
    real_open = Path.open

    def tracking_open(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        opened.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    with pytest.raises(ValueError):
        assert_safe_json_path(csv_path)
    # Must not have opened the CSV
    assert not any(p.endswith("secret.csv") for p in opened)


def test_forbidden_phrase_list_nonempty() -> None:
    assert "diagnosed" in FORBIDDEN_PHRASES
    assert find_forbidden_phrases("This was diagnosed yesterday") == ["diagnosed"]

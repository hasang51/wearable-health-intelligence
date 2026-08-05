"""Tests for local reviewed-dashboard delivery_export bundle command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.config import DEMO_DIR, REVIEWED_DIR
from src.dashboard.delivery.facts import SOURCE_KIND_DEMO, SOURCE_KIND_REVIEWED
from src.dashboard.models import SafePhase1Input
from src.delivery_export import SOURCE_LABEL
from src.delivery_export.allowlist import strip_unknown
from src.delivery_export.cli import main as cli_main
from src.delivery_export.export import (
    DeliveryExportError,
    assert_scientific_statuses,
    build_reviewed_dashboard_bundle,
    export_reviewed_dashboard_bundle,
)
from src.delivery_export.models import ReviewedDashboardBundle
from src.forensics.models import DecoderStatus, ForensicsMeta, PacketSpecSummary
from src.reconstruction.models import (
    ChannelCompatibilitySummary,
    ChannelCompatibilityVerdict,
    Phase3Summary,
    RateStatus,
    ReconstructionMeta,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_export_reviewed_bundle_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "dashboard.safe.json"
    result = export_reviewed_dashboard_bundle(
        REVIEWED_DIR / "safe_phase1.json",
        REVIEWED_DIR / "safe_phase2.json",
        REVIEWED_DIR / "safe_phase3.json",
        out,
    )
    assert result == out
    data = json.loads(out.read_text(encoding="utf-8"))
    bundle = ReviewedDashboardBundle.model_validate(data)
    assert bundle.schema_version == "dashboard.safe.v1"
    assert bundle.source_label == SOURCE_LABEL
    assert bundle.aggregate_source_kind == SOURCE_KIND_REVIEWED
    assert bundle.phase2.decoder_status == DecoderStatus.UNVERIFIED
    assert bundle.phase3.rate_status == RateStatus.NOT_COMPUTED
    assert (
        bundle.phase3.channel_evidence is not None
        and bundle.phase3.channel_evidence.verdict
        == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT
    )
    assert bundle.phase2.packet_count == 8161
    assert bundle.overview.sessions == 10
    assert bundle.overview.packets == 8161
    assert bundle.overview.malformed_packets == 0
    assert bundle.overview.gaps == 27
    assert bundle.overview.maximum_gap_ms == 47111
    assert bundle.overview.upload_completed == 0
    assert bundle.overview.upload_pending == 10
    assert (
        bundle.research_status.channel_verdict
        == "INSUFFICIENT_CHANNEL_AGREEMENT"
    )
    assert bundle.modality_coverage.raw_ppg_payload_sessions == 10
    assert bundle.modality_coverage.normalized_ppg_sessions == 0
    assert bundle.modality_coverage.ecg_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.temperature_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.sleep_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.activity_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.blood_pressure_sessions == "NOT_AVAILABLE"
    log_text = out.with_suffix(".export.log").read_text(encoding="utf-8")
    assert "phase1.modality_coverage[ecg].samples_present" in log_text
    assert "session_id" not in out.read_text(encoding="utf-8").lower()


def test_secondary_modalities_map_only_authoritative_safe_statuses(
    tmp_path: Path,
) -> None:
    p1 = json.loads((REVIEWED_DIR / "safe_phase1.json").read_text(encoding="utf-8"))
    p1["modality_coverage"].extend(
        [
            {"modality": "ecg", "status_counts": {"samples_present": 3}},
            {"modality": "temperature", "status_counts": {"column_absent": 10}},
            {"modality": "sleep", "status_counts": {"payload_empty": 10}},
            {
                "modality": "activity",
                "status_counts": {"structure_present_no_samples": 10},
            },
            {
                "modality": "blood_pressure",
                "status_counts": {
                    "column_absent": 4,
                    "payload_empty": 3,
                    "structure_present_no_samples": 3,
                },
            },
        ]
    )

    bundle = build_reviewed_dashboard_bundle(
        _write(tmp_path / "p1.json", p1),
        REVIEWED_DIR / "safe_phase2.json",
        REVIEWED_DIR / "safe_phase3.json",
    )

    assert bundle.modality_coverage.ecg_sessions == 3
    assert bundle.modality_coverage.temperature_sessions == 0
    assert bundle.modality_coverage.sleep_sessions == 0
    assert bundle.modality_coverage.activity_sessions == 0
    assert bundle.modality_coverage.blood_pressure_sessions == 0


def test_secondary_modality_partial_or_non_evaluable_statuses_are_not_invented(
    tmp_path: Path,
) -> None:
    p1 = json.loads((REVIEWED_DIR / "safe_phase1.json").read_text(encoding="utf-8"))
    p1["modality_coverage"].extend(
        [
            {"modality": "ecg", "status_counts": {"column_absent": 9}},
            {
                "modality": "temperature",
                "status_counts": {"column_absent": 9, "not_evaluable": 1},
            },
        ]
    )

    bundle = build_reviewed_dashboard_bundle(
        _write(tmp_path / "p1.json", p1),
        REVIEWED_DIR / "safe_phase2.json",
        REVIEWED_DIR / "safe_phase3.json",
    )

    assert bundle.modality_coverage.ecg_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.temperature_sessions == "NOT_AVAILABLE"


def test_secondary_modality_counts_do_not_fall_back_to_raw_or_private_fields(
    tmp_path: Path,
) -> None:
    p1 = json.loads((REVIEWED_DIR / "safe_phase1.json").read_text(encoding="utf-8"))
    p1["raw_csv_modality_counts"] = {"ecg": 10}
    p1["private_report_modality_counts"] = {"temperature": 8}

    bundle = build_reviewed_dashboard_bundle(
        _write(tmp_path / "p1.json", p1),
        REVIEWED_DIR / "safe_phase2.json",
        REVIEWED_DIR / "safe_phase3.json",
    )

    assert bundle.modality_coverage.ecg_sessions == "NOT_AVAILABLE"
    assert bundle.modality_coverage.temperature_sessions == "NOT_AVAILABLE"
    dumped = json.dumps(bundle.model_dump(mode="json"))
    assert "raw_csv_modality_counts" not in dumped
    assert "private_report_modality_counts" not in dumped


def test_cli_success(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    code = cli_main(
        [
            "--phase1-safe",
            str(REVIEWED_DIR / "safe_phase1.json"),
            "--phase2-safe",
            str(REVIEWED_DIR / "safe_phase2.json"),
            "--phase3-safe",
            str(REVIEWED_DIR / "safe_phase3.json"),
            "--output",
            str(out),
        ]
    )
    assert code == 0
    assert out.is_file()


def test_reject_demo_sources(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    with pytest.raises(DeliveryExportError, match="demo"):
        export_reviewed_dashboard_bundle(
            DEMO_DIR / "safe_phase1.json",
            DEMO_DIR / "safe_phase2.json",
            DEMO_DIR / "safe_phase3.json",
            out,
        )


def test_deprecated_channel_fields_cannot_override_structured_verdict(
    tmp_path: Path,
) -> None:
    p3 = json.loads((REVIEWED_DIR / "safe_phase3.json").read_text(encoding="utf-8"))
    p3["channels_compatible"] = True
    p3["channel_verdict"] = "PARTIALLY_COMPATIBLE"
    phase3 = _write(tmp_path / "p3.json", p3)

    bundle = build_reviewed_dashboard_bundle(
        REVIEWED_DIR / "safe_phase1.json",
        REVIEWED_DIR / "safe_phase2.json",
        phase3,
    )

    assert (
        bundle.research_status.channel_verdict
        == "INSUFFICIENT_CHANNEL_AGREEMENT"
    )
    dumped = bundle.model_dump(mode="json")
    assert "channels_compatible" not in json.dumps(dumped)
    assert "channel_verdict" not in dumped["phase3"]


def test_missing_reviewed_metric_is_not_available_with_warning(
    tmp_path: Path,
) -> None:
    p2 = json.loads((REVIEWED_DIR / "safe_phase2.json").read_text(encoding="utf-8"))
    del p2["malformed_packet_count"]
    phase2 = _write(tmp_path / "p2.json", p2)

    bundle = build_reviewed_dashboard_bundle(
        REVIEWED_DIR / "safe_phase1.json",
        phase2,
        REVIEWED_DIR / "safe_phase3.json",
    )

    assert bundle.overview.malformed_packets == "NOT_AVAILABLE"
    assert any("phase2.malformed_packet_count" in w for w in bundle.export_warnings)


def test_reject_mixed_source_kinds(tmp_path: Path) -> None:
    p1 = json.loads((REVIEWED_DIR / "safe_phase1.json").read_text(encoding="utf-8"))
    p1["aggregate_source_kind"] = SOURCE_KIND_DEMO
    phase1 = _write(tmp_path / "p1.json", p1)
    out = tmp_path / "out.json"
    with pytest.raises(DeliveryExportError, match="demo|Mixed"):
        export_reviewed_dashboard_bundle(
            phase1,
            REVIEWED_DIR / "safe_phase2.json",
            REVIEWED_DIR / "safe_phase3.json",
            out,
        )


def test_strip_unknown_fields(tmp_path: Path) -> None:
    p1 = json.loads((REVIEWED_DIR / "safe_phase1.json").read_text(encoding="utf-8"))
    p2 = json.loads((REVIEWED_DIR / "safe_phase2.json").read_text(encoding="utf-8"))
    p3 = json.loads((REVIEWED_DIR / "safe_phase3.json").read_text(encoding="utf-8"))
    p1["secret_raw_trace"] = [1, 2, 3]
    p1["file_path"] = "C:\\\\Users\\\\secret\\\\data.csv"
    p2["selected_candidate_id"] = "cand-uuid-should-drop"
    p3["reconstructed_samples"] = {"ch0": [0.1, 0.2]}
    paths = (
        _write(tmp_path / "p1.json", p1),
        _write(tmp_path / "p2.json", p2),
        _write(tmp_path / "p3.json", p3),
    )
    out = tmp_path / "out.json"
    export_reviewed_dashboard_bundle(*paths, out)
    text = out.read_text(encoding="utf-8")
    assert "secret_raw_trace" not in text
    assert "file_path" not in text
    assert "selected_candidate_id" not in text
    assert "reconstructed_samples" not in text
    ReviewedDashboardBundle.model_validate(json.loads(text))


def test_allowlist_helper_drops_extras() -> None:
    raw = {
        "schema_version": "dashboard.safe.v1",
        "row_count": 1,
        "column_count": 1,
        "mystery": True,
    }
    cleaned = strip_unknown(SafePhase1Input, raw)
    assert "mystery" not in cleaned
    assert cleaned["row_count"] == 1


def test_refuse_csv_input(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    out = tmp_path / "out.json"
    with pytest.raises((DeliveryExportError, ValueError)):
        export_reviewed_dashboard_bundle(
            csv_path,
            REVIEWED_DIR / "safe_phase2.json",
            REVIEWED_DIR / "safe_phase3.json",
            out,
        )


def test_refuse_parquet_input(tmp_path: Path) -> None:
    pq = tmp_path / "x.parquet"
    pq.write_bytes(b"not-parquet")
    out = tmp_path / "out.json"
    with pytest.raises((DeliveryExportError, ValueError)):
        export_reviewed_dashboard_bundle(
            REVIEWED_DIR / "safe_phase1.json",
            pq,
            REVIEWED_DIR / "safe_phase3.json",
            out,
        )


def test_refuse_directory_input(tmp_path: Path) -> None:
    d = tmp_path / "adir"
    d.mkdir()
    out = tmp_path / "out.json"
    with pytest.raises((DeliveryExportError, ValueError, FileNotFoundError)):
        export_reviewed_dashboard_bundle(
            d,
            REVIEWED_DIR / "safe_phase2.json",
            REVIEWED_DIR / "safe_phase3.json",
            out,
        )


def test_refuse_private_named_json(tmp_path: Path) -> None:
    private = tmp_path / "private_report.json"
    private.write_text("{}", encoding="utf-8")
    out = tmp_path / "out.json"
    with pytest.raises((DeliveryExportError, ValueError), match="private"):
        export_reviewed_dashboard_bundle(
            private,
            REVIEWED_DIR / "safe_phase2.json",
            REVIEWED_DIR / "safe_phase3.json",
            out,
        )


def test_fail_closed_missing_rate_status(tmp_path: Path) -> None:
    p3 = json.loads((REVIEWED_DIR / "safe_phase3.json").read_text(encoding="utf-8"))
    del p3["rate_status"]
    path = _write(tmp_path / "p3.json", p3)
    with pytest.raises(DeliveryExportError, match="rate_status"):
        build_reviewed_dashboard_bundle(
            REVIEWED_DIR / "safe_phase1.json",
            REVIEWED_DIR / "safe_phase2.json",
            path,
        )


def test_fail_closed_missing_decoder_status(tmp_path: Path) -> None:
    p2 = json.loads((REVIEWED_DIR / "safe_phase2.json").read_text(encoding="utf-8"))
    del p2["decoder_status"]
    path = _write(tmp_path / "p2.json", p2)
    with pytest.raises(DeliveryExportError, match="decoder_status"):
        build_reviewed_dashboard_bundle(
            REVIEWED_DIR / "safe_phase1.json",
            path,
            REVIEWED_DIR / "safe_phase3.json",
        )


def test_fail_closed_missing_channel_verdict(tmp_path: Path) -> None:
    p3 = json.loads((REVIEWED_DIR / "safe_phase3.json").read_text(encoding="utf-8"))
    p3["channel_evidence"] = {"frequency_agreeing": 1}
    path = _write(tmp_path / "p3.json", p3)
    with pytest.raises(DeliveryExportError, match="verdict"):
        assert_scientific_statuses(
            json.loads((REVIEWED_DIR / "safe_phase2.json").read_text(encoding="utf-8")),
            json.loads(path.read_text(encoding="utf-8")),
        )


def test_fail_closed_malformed_rate_status(tmp_path: Path) -> None:
    p3 = json.loads((REVIEWED_DIR / "safe_phase3.json").read_text(encoding="utf-8"))
    p3["rate_status"] = "TOTALLY_FAKE"
    path = _write(tmp_path / "p3.json", p3)
    with pytest.raises(DeliveryExportError, match="rate_status|Malformed"):
        build_reviewed_dashboard_bundle(
            REVIEWED_DIR / "safe_phase1.json",
            REVIEWED_DIR / "safe_phase2.json",
            path,
        )


def test_legacy_safe_reports_export(tmp_path: Path) -> None:
    from src.audit.models import (
        ColumnKind,
        ColumnProfile,
        LimitsApplied,
        ModalityCoverage,
        ProfileMeta,
        SafeSchemaProfile,
    )

    meta1 = ProfileMeta(
        row_count=2,
        column_count=1,
        generated_at="redacted",
        tool_version="0.1.0",
        limits_applied=LimitsApplied(
            max_json_depth=8,
            max_keys_per_object=64,
            max_array_elements_inspected=100,
            csv_field_size_limit=1024,
        ),
    )
    phase1 = SafeSchemaProfile(
        meta=meta1,
        columns=[
            ColumnProfile(
                name="raw_packets_json",
                kind=ColumnKind.JSON_LIKE,
                null_or_empty_count=0,
                non_empty_count=2,
            )
        ],
        json_columns=[],
        modality_coverage=[
            ModalityCoverage(modality="ppg", status_counts={"samples_present": 2})
        ],
        inconsistency_counts={"pending_upload": 0},
    )
    meta2 = ForensicsMeta(
        session_count=2,
        packet_count=50,
        candidate_count=10,
        generated_at="redacted",
        tool_version="0.2.0",
        expected_payload_length=66,
        gap_threshold_ms=1500,
    )
    phase2 = PacketSpecSummary(
        meta=meta2,
        expected_keys=["dataEnd", "dataType", "dicData", "receivedAtMs"],
        nominal_payload_length=66,
        selected_status=DecoderStatus.UNVERIFIED,
    )
    meta3 = ReconstructionMeta(
        session_count=2,
        packet_count=50,
        generated_at="redacted",
        tool_version="0.3.0",
    )
    phase3 = Phase3Summary(
        meta=meta3,
        top_layout="INTERLEAVED_PACKET_LOCAL",
        top_hypothesis="H_2x33",
        quality_label_counts={"poor": 10},
        rate_status=RateStatus.NOT_COMPUTED,
        channel_compatibility=ChannelCompatibilitySummary(
            verdict=ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT,
            frequency_evaluable_pairs=5,
            frequency_agreeing_pairs=1,
        ),
    )
    p1 = _write(tmp_path / "legacy_p1.json", phase1.model_dump(mode="json"))
    p2 = _write(tmp_path / "legacy_p2.json", phase2.model_dump(mode="json"))
    p3 = _write(tmp_path / "legacy_p3.json", phase3.model_dump(mode="json"))
    out = tmp_path / "bundled.json"
    export_reviewed_dashboard_bundle(p1, p2, p3, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source_label"] == SOURCE_LABEL
    assert data["phase2"]["decoder_status"] == "UNVERIFIED"
    assert data["phase3"]["rate_status"] == "NOT_COMPUTED"
    assert "generated_at" not in json.dumps(data["phase1"])
    assert "generated_at" not in json.dumps(data["phase2"])


def test_cli_rejects_demo(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    code = cli_main(
        [
            "--phase1-safe",
            str(DEMO_DIR / "safe_phase1.json"),
            "--phase2-safe",
            str(DEMO_DIR / "safe_phase2.json"),
            "--phase3-safe",
            str(DEMO_DIR / "safe_phase3.json"),
            "--output",
            str(out),
        ]
    )
    assert code == 1
    assert not out.exists()


def test_output_must_be_json_file(tmp_path: Path) -> None:
    with pytest.raises(DeliveryExportError, match="\\.json"):
        export_reviewed_dashboard_bundle(
            REVIEWED_DIR / "safe_phase1.json",
            REVIEWED_DIR / "safe_phase2.json",
            REVIEWED_DIR / "safe_phase3.json",
            tmp_path / "out.txt",
        )

"""Benchmark metrics, rate gates, privacy, CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.reconstruction.benchmark.adapter_but import run_but_benchmark
from src.reconstruction.benchmark.metrics import (
    confusion_binary,
    balanced_accuracy,
    hr_error_metrics,
    precision_recall_f1,
)
from src.reconstruction.cli import main
from src.reconstruction.models import RateStatus
from src.reconstruction.rate_gates import RateGateInput, evaluate_rate_gates
from tests.conftest import FORBIDDEN_LITERALS, FIXTURES


def test_benchmark_metric_correctness():
    # Hand-computed: yt=[1,1,0,0] yp=[1,0,0,1] -> tp1 tn1 fp1 fn1
    c = confusion_binary([1, 1, 0, 0], [1, 0, 0, 1])
    assert (c.tp, c.tn, c.fp, c.fn) == (1, 1, 1, 1)
    assert abs(balanced_accuracy(c) - 0.5) < 1e-12
    prec, rec, f1 = precision_recall_f1(c)
    assert abs(prec - 0.5) < 1e-12
    assert abs(rec - 0.5) < 1e-12
    assert abs(f1 - 0.5) < 1e-12

    hr = hr_error_metrics([70.0, 80.0, 90.0], [72.0, None, 85.0])
    assert abs(hr.coverage - 2 / 3) < 1e-12
    assert abs(hr.mae - ((2 + 5) / 2)) < 1e-12
    assert abs(hr.median_abs_error - 3.5) < 1e-12
    assert abs(hr.bias - ((2 + (-5)) / 2)) < 1e-12


def test_rate_gates_fail_closed_unverified():
    result = evaluate_rate_gates(
        RateGateInput(
            decoder_status="UNVERIFIED",
            public_good_median_abs_hr_error=3.0,
            public_good_coverage=0.9,
        )
    )
    assert result.rate_status == RateStatus.NOT_COMPUTED
    assert "decoder_status_insufficient" in result.failed_gates


def test_rate_gates_method_disagreement():
    from src.reconstruction.channel_compat import decide_channel_compatibility
    from src.reconstruction.models import ChannelCompatibilityVerdict

    channel_compat = decide_channel_compatibility(
        total_pairs=20,
        evaluable_pairs=20,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=20,
        frequency_agreeing_pairs=16,
        frequency_agreement_fraction=0.80,
        median_max_abs_lagged_correlation=0.45,
        median_coherence=0.35,
    )
    assert channel_compat.verdict == ChannelCompatibilityVerdict.COMPATIBLE
    result = evaluate_rate_gates(
        RateGateInput(
            decoder_status="PROVISIONALLY_ACCEPTED",
            public_good_median_abs_hr_error=3.0,
            public_good_coverage=0.9,
            spectral_rate_bpm=60.0,
            time_domain_rate_bpm=80.0,
            channel_compatibility=channel_compat,
            selected_layout="X",
            selected_hypothesis_key="H",
        )
    )
    assert result.rate_status == RateStatus.METHOD_DISAGREEMENT
    assert "channels_compatible" not in result.passed_gates
    assert "channel_agreement_compatible" in result.passed_gates


def test_rate_gates_insufficient_channel_agreement_keeps_not_computed():
    from src.reconstruction.channel_compat import decide_channel_compatibility
    from src.reconstruction.models import ChannelCompatibilityVerdict

    channel_compat = decide_channel_compatibility(
        total_pairs=37,
        evaluable_pairs=37,
        evaluable_fraction=1.0,
        frequency_evaluable_pairs=37,
        frequency_agreeing_pairs=18,
        frequency_agreement_fraction=18 / 37,
        median_max_abs_lagged_correlation=0.205,
        median_coherence=0.075,
    )
    assert channel_compat.verdict == ChannelCompatibilityVerdict.INSUFFICIENT_CHANNEL_AGREEMENT
    result = evaluate_rate_gates(
        RateGateInput(
            decoder_status="PROVISIONALLY_ACCEPTED",
            public_good_median_abs_hr_error=3.0,
            public_good_coverage=0.9,
            spectral_rate_bpm=70.0,
            time_domain_rate_bpm=71.0,
            channel_compatibility=channel_compat,
            selected_layout="X",
            selected_hypothesis_key="H",
        )
    )
    assert result.rate_status == RateStatus.NOT_COMPUTED
    assert "channel_agreement_insufficient" in result.failed_gates
    assert "channels_compatible" not in result.passed_gates


def test_but_adapter_synthetic(tmp_path: Path):
    # Create synthetic BUT-like root outside workspace check by setting workspace_root=None
    root = tmp_path / "but"
    sig_dir = root / "signals"
    sig_dir.mkdir(parents=True)
    fs = 125.0
    t = np.arange(0, 10, 1 / fs)
    good = (np.sin(2 * np.pi * 1.2 * t) * 1000).astype(np.float64)
    bad = np.random.default_rng(1).normal(0, 1, size=good.size)
    np.save(sig_dir / "r1.npy", good)
    np.save(sig_dir / "r2.npy", bad)
    manifest = {
        "version": "2.0.0",
        "records": [
            {
                "record_id": "r1",
                "subject_id": "s1",
                "fs_hz": fs,
                "quality_label": 1,
                "reference_hr_bpm": 72.0,
                "signal_file": "signals/r1.npy",
            },
            {
                "record_id": "r2",
                "subject_id": "s2",
                "fs_hz": fs,
                "quality_label": 0,
                "reference_hr_bpm": None,
                "signal_file": "signals/r2.npy",
            },
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = run_but_benchmark(root, seed=0, workspace_root=None)
    assert result.ran
    assert result.record_count == 2
    assert result.quality_balanced_accuracy is not None


def test_cli_on_fixture(tmp_path: Path):
    priv = tmp_path / "priv"
    safe = tmp_path / "safe"
    fixture = FIXTURES / "packets_valid_66.csv"
    assert fixture.is_file()
    rc = main(
        [
            "--input",
            str(fixture),
            "--private-dir",
            str(priv),
            "--safe-dir",
            str(safe),
            "--allow-private-snippets",
        ]
    )
    assert rc == 0
    assert (priv / "layout_hypotheses.json").is_file()
    assert (priv / "metadata_position_analysis.json").is_file()
    assert (priv / "reconstructed_candidate_segments.parquet").is_file()
    assert (priv / "candidate_quality_windows.parquet").is_file()
    assert (priv / "spectral_plausibility.json").is_file()
    assert (priv / "channel_relationship.json").is_file()
    assert (priv / "rate_gate.json").is_file()
    assert (safe / "phase3_summary.json").is_file()
    assert (safe / "decoder_refinement.md").is_file()
    assert (safe / "benchmark_summary.json").is_file()
    assert (safe / "research_limitations.md").is_file()

    summary = json.loads((safe / "phase3_summary.json").read_text(encoding="utf-8"))
    assert summary["rate_status"] == "NOT_COMPUTED"
    assert "candidate_not_validated_ppg" in summary["privacy_posture"]

    # Privacy: no forbidden literals in safe outputs
    for name in (
        "phase3_summary.json",
        "decoder_refinement.md",
        "benchmark_summary.json",
        "research_limitations.md",
    ):
        text = (safe / name).read_text(encoding="utf-8")
        for lit in FORBIDDEN_LITERALS:
            assert lit not in text


def test_privacy_sensitive_fixture(tmp_path: Path):
    priv = tmp_path / "priv"
    safe = tmp_path / "safe"
    fixture = FIXTURES / "packets_sensitive_name_SYNTH.csv"
    if not fixture.is_file():
        pytest.skip("sensitive fixture missing")
    rc = main(
        [
            "--input",
            str(fixture),
            "--private-dir",
            str(priv),
            "--safe-dir",
            str(safe),
        ]
    )
    assert rc == 0
    text = (safe / "phase3_summary.json").read_text(encoding="utf-8")
    assert "SYNTH_PATIENT" not in text or "<" in text  # scrubbed or absent
    for lit in FORBIDDEN_LITERALS:
        assert lit not in text


def test_forensics_still_no_scipy_fft():
    """Phase 2 package must remain free of spectral imports."""
    import ast
    from pathlib import Path

    forensics = Path(__file__).resolve().parents[1] / "src" / "forensics"
    for path in forensics.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "scipy" not in alias.name
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("scipy")

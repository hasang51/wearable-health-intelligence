# Wearable Health Intelligence

> This repository contains source code, tests, documentation and synthetic demo
> assets only. No raw health data, private reports, real session artifacts or
> device identifiers are included.

Offline structural audit (Phase 1), PPG packet forensics (Phase 2), candidate
reconstruction / signal-quality evidence (Phase 3), and an evidence dashboard /
delivery package (Phase 4) for wearable-health session CSVs. Discovers available
modalities, packet structure, and decoder hypotheses **before** any clinical
interpretation. No diagnoses, no training, no network.

## Current research status

These are the current, verified statuses of the pipeline on the reviewed dataset.
They are **not** placeholders — they reflect the actual state of the decoder and
signal-quality evidence, and must not be read as, or converted into, a clinical
result:

| Status | Value |
|--------|-------|
| Decoder | **UNVERIFIED** — best-scoring candidate only, not confirmed physiological PPG |
| Channel verdict | **INSUFFICIENT_CHANNEL_AGREEMENT** — multi-metric channel-compatibility gate did not pass |
| Proprietary rate | **NOT_COMPUTED** — rate computation is fail-closed while the above gates do not pass |

**No HR, HRV, SpO2, diagnosis, or other clinical output is produced anywhere in
this pipeline.** No claim of physiological validity is made for any candidate
signal, rate, or channel.

## Privacy model / security rules

- Real patient CSVs must **never** enter this repository.
- Real private/safe reports must be written to an **external secure directory** supplied by the operator.
- In-repo `reports/private/` is for **synthetic tests only**.
- After manual review, the operator may copy a safe report into `reports/safe/`.
- Pipelines open **only** the explicit `--input` path (no directory search, glob, parent walk, or symlink discovery).
- Phase 4 opens **only** an explicit `--safe-bundle` JSON path (or `WEARABLE_DASHBOARD_SAFE_BUNDLE`) or the bundled `demo/` aggregates — never raw CSV, private reports, or reconstructed parquet.
- Reports, logs, stdout, and stderr never emit raw physiological sample series, identifiers, exact timestamps, or sensitive filenames.

## Setup

```bash
uv sync --group dev
```

Optional NeuroKit2 comparison adapter (never decoder ground truth):

```bash
uv sync --group dev --group neurokit
```

Requires Python `>=3.12,<3.14` (see `pyproject.toml` / `.python-version`).

## Phase 1 — Secure local data-audit

```bash
uv run python -m src.audit \
  --input "EXTERNAL_CSV_PATH" \
  --private-output "EXTERNAL_SECURE_DIR/data_profile.json" \
  --safe-output "EXTERNAL_SECURE_DIR/schema_profile.json"
```

Optional resource limits:

```bash
  --max-json-depth 8 \
  --max-keys-per-object 200 \
  --max-array-elements-inspected 50 \
  --csv-field-size-limit 10485760
```

## Phase 2 — PPG packet forensics

Streams `raw_packets_json`, validates packet schema, computes position/bit forensics, scores 192 decoder hypotheses (24-bit signedness × byte permutations × channel layouts), and reconstructs packet-level timebases. Does **not** claim physiological PPG, compute vitals, or apply filters/FFT/ML.

```bash
uv run python -m src.forensics \
  --input "EXTERNAL_CSV_PATH" \
  --private-dir "EXTERNAL_SECURE_DIR/forensics_private" \
  --safe-dir "EXTERNAL_SECURE_DIR/forensics_safe"
```

Optional:

```bash
  --expected-payload-length 66 \
  --gap-threshold-ms 1500 \
  --samples-per-packet 66 \
  --max-plot-candidates 5 \
  --vendor-documented \
  --allow-private-snippets \
  --csv-field-size-limit 10485760
```

Private outputs: `packet_forensics.json`, `decoder_candidates.json`, `timebase_report.json`, `plots/`.  
Safe outputs: `packet_spec_summary.json`, `decoder_decision.md`.

`--samples-per-packet` is required before any `estimated_sample_timestamp` values are generated (counts only appear in private JSON; timestamp values are not written to reports).

## Phase 3 — Candidate reconstruction and signal-quality evidence

Reconstructs **candidate** multi-channel streams under explicit layouts and payload hypotheses, scores metadata positions, evaluates periodicity / channel relationships, and emits research-only quality labels. Does **not** validate physiological PPG. Proprietary candidate pulse rate is fail-closed unless all conditional gates pass. Optional public BUT PPG v2.0.0 benchmark is isolated from proprietary decoder ranking.

```bash
uv run python -m src.reconstruction \
  --input "EXTERNAL_CSV_PATH" \
  --private-dir "EXTERNAL_SECURE_DIR/phase3_private" \
  --safe-dir "EXTERNAL_SECURE_DIR/phase3_safe"
```

Optional:

```bash
  --signedness int24 \
  --byte-order CAB \
  --phase2-summary "EXTERNAL_SECURE_DIR/forensics_safe/packet_spec_summary.json" \
  --benchmark-dir "EXTERNAL_BUT_PPG_ROOT" \
  --benchmark-seed 0 \
  --vendor-documented \
  --allow-private-snippets \
  --csv-field-size-limit 10485760
```

Layouts evaluated: `INTERLEAVED_PACKET_LOCAL`, `INTERLEAVED_CONTINUOUS`, `BLOCKED_PACKET_LOCAL`, `BLOCKED_CONTINUOUS`.  
Payload hypotheses: `H_2x33`, `H_2x32_plus_2global`, `H_2block_meta_per_ch`, `H_3x22`.

Gap split rule: `max(1.5 × median packet interval, 1500 ms)`. Spectra and filters never run across a gap.

Private outputs: `layout_hypotheses.json`, `metadata_position_analysis.json`, `reconstructed_candidate_segments.parquet`, `candidate_quality_windows.parquet`, `spectral_plausibility.json`, `channel_relationship.json`, `benchmark_results.json`, `rate_gate.json`, `plots/`.  
Safe outputs: `phase3_summary.json`, `decoder_refinement.md`, `benchmark_summary.json`, `research_limitations.md`.

Channel compatibility for proprietary rate gating is a **multi-metric aggregate** on the selected best layout/hypothesis only (`COMPATIBLE` / `PARTIALLY_COMPATIBLE` / `INSUFFICIENT_CHANNEL_AGREEMENT` / `NOT_EVALUABLE`). The obsolete existential `channels_compatible` gate (any agreeing pair) was removed; only `channel_agreement_compatible` may pass, and only for `COMPATIBLE`. Safe reports include aggregate channel evidence only (no per-pair values).

Quality labels: `unusable`, `poor`, `uncertain`, `plausible_candidate_signal`.

## Phase 4 — Evidence dashboard and delivery package

Consumes **only** manually supplied safe aggregate JSON, curated reviewed aggregates,
or bundled demo data. Performs **no** new signal processing. Missing scientific fields
render as `NOT_AVAILABLE`.

### Run (synthetic demo — safe default)

```bash
uv run streamlit run src/dashboard/app.py -- --demo
```

Loads only the bundled synthetic aggregates in `demo/`. Shows a persistent
banner: `SYNTHETIC DEMO - NOT PROJECT RESULTS`.

### Run (explicit safe bundle)

```bash
uv run streamlit run src/dashboard/app.py -- --safe-bundle "EXTERNAL_SECURE_DIR/dashboard_safe_v1.json"
```

or via environment variable instead of a CLI flag:

```bash
export WEARABLE_DASHBOARD_SAFE_BUNDLE="EXTERNAL_SECURE_DIR/dashboard_safe_v1.json"
uv run streamlit run src/dashboard/app.py
```

Build the safe bundle from three explicit Phase 1–3 safe-report paths (never
raw CSV, private reports, or reconstructed parquet):

```bash
uv run python -m src.delivery_export \
  --phase1-safe "EXTERNAL_SECURE_DIR/phase1_safe.json" \
  --phase2-safe "EXTERNAL_SECURE_DIR/phase2_safe.json" \
  --phase3-safe "EXTERNAL_SECURE_DIR/phase3_safe.json" \
  --output "EXTERNAL_SECURE_DIR/dashboard_safe_v1.json"
```

**Exactly one** of `--demo`, `--safe-bundle PATH`, or
`WEARABLE_DASHBOARD_SAFE_BUNDLE` is required; the dashboard fails closed with a
configuration error if none or more than one is given. There is no default
mode and no directory scanning — the dashboard can never silently load a local
real-data path.

### Input contracts

| Mode | Inputs |
|------|--------|
| Demo | `demo/safe_phase{1,2,3}.json` (bundled, `aggregate_source_kind: synthetic_demo`) |
| Safe bundle | Operator-supplied `dashboard.safe.v1` JSON (must not be the synthetic demo bundle) |

Demo and safe-bundle fields are never merged. Missing fields show `NOT_AVAILABLE`.

### Privacy guarantees (Phase 4)

- No directory scanning, network, telemetry, cloud APIs, or external LLM calls.
- Refuses `.csv` / `.parquet` / private-named paths.
- No raw values, exact timestamps, patient/session/device identifiers, or sensitive paths in UI/docs.
- Status language is neutral research terminology (`UNVERIFIED`, `INSUFFICIENT_CHANNEL_AGREEMENT`, `NOT_COMPUTED`).

### Delivery documents

```bash
uv run python -m src.dashboard.delivery --demo --out reports/delivery
```

### Delivery folder map

```
reports/delivery/
  executive_summary.md
  technical_report.md
  research_limitations.md
  presentation_outline.md
  demo_script.md
  delivery_checklist.md
  architecture.mmd
```

`reports/delivery/` is generated locally and is **git-ignored** — it is never
committed to this repository, even when built from reviewed real-project safe
aggregates. Regenerate it locally when needed.

Also: `demo/` (bundled safe aggregates), `src/dashboard/` (app + adapters).

### Screenshots (placeholder)

Add operator screenshots here after a local demo run:

1. Executive Overview — status cards
2. Decoder Research — hypothesis comparison chart
3. Channel Evidence — rate gates

_(No screenshots committed by default.)_

### Known limitations (Phase 4)

- Dashboard does not recompute Phase 1–3 science.
- Stock legacy safe JSON may omit fields needed for full charts until operators supply `dashboard.safe.v1` enriched aggregates.
- Decoder remains research-only; candidate periodic frequency is not heart rate.

## Synthetic test run

```bash
uv run pytest
```

## Agents / automation

Do **not** point these pipelines at real healthcare files. Do **not** place real CSVs under the workspace. Use only `tests/fixtures/` for automated runs. Use `demo/` only for Phase 4 UI/docs.

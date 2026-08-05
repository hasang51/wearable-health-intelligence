"""Generate reports/delivery markdown and architecture diagram from safe facts."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.dashboard.delivery import facts as F
from src.dashboard.terminology import assert_no_forbidden_terminology


def _word_count(text: str) -> int:
    return len(text.split())


def executive_summary() -> str:
    text = f"""# Executive Summary

## Problem

Wearable session exports arrive as opaque CSVs with nested packet JSON. Before any
product claim about pulse or PPG, the organization needed an offline, privacy-preserving
pipeline that audits structure, searches decoder hypotheses, and reports research-only
evidence — without emitting diagnoses, vital signs, or identifiable data into shared
repositories.

## Approach

Phases 1–3 run locally on operator-supplied paths only (no directory scanning, no
network). Phase 1 produces safe schema profiles. Phase 2 scores decoder families and
timebase gaps. Phase 3 reconstructs candidate streams under explicit layouts and payload
hypotheses, labels research quality windows, aggregates channel compatibility, and
fail-closes proprietary rate computation. Phase 4 consumes only manually supplied safe
aggregate JSON (or a bundled synthetic demo) to present an evidence dashboard and
delivery documents. Private reconstructions never feed the dashboard.

## Key findings

- **{F.SESSIONS} sessions**, **{F.PACKETS} packets** processed; **{F.MALFORMED_PACKETS}**
  malformed packets; every packet had a {F.NOMINAL_PAYLOAD_LENGTH}-integer payload and
  dataType {F.DATATYPE_MODE}.
- **{F.GAPS_GT_THRESHOLD}** timestamp gaps greater than {F.GAP_THRESHOLD_MS} ms;
  maximum gap **{F.MAX_GAP_MS} ms**.
- Decoder status: **{F.DECODER_STATUS}**. Best family: **{F.TOP_DECODER_FAMILY}**.
  Best hypothesis: **{F.TOP_HYPOTHESIS}**. Best layout: **{F.TOP_LAYOUT}**.
- Hypothesis band_ratio leaders: {F.HYPOTHESIS_SCORES[0]['band_ratio']:.4f} (best) vs
  {F.HYPOTHESIS_SCORES[1]['band_ratio']:.4f} (second); usable_fraction
  {F.HYPOTHESIS_SCORES[0]['usable_fraction']:.3f} vs
  {F.HYPOTHESIS_SCORES[1]['usable_fraction']:.3f}.
- **{F.CONTINUOUS_SEGMENTS}** continuous segments; **{F.CHANNEL_SEGMENTS}** channel-segments.
  Periodicity: plausible={F.PERIODICITY_PLAUSIBLE}, weak={F.PERIODICITY_WEAK},
  non-evaluable={F.PERIODICITY_NON_EVALUABLE}.
- Mean **candidate periodic frequency** ≈ **{F.CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ} Hz**
  (not heart rate; research-only signal plausibility).
- Quality labels: unusable={F.QUALITY_LABEL_COUNTS['unusable']},
  poor={F.QUALITY_LABEL_COUNTS['poor']},
  uncertain={F.QUALITY_LABEL_COUNTS['uncertain']},
  plausible_candidate_signal={F.QUALITY_LABEL_COUNTS['plausible_candidate_signal']}.
- Upload lifecycle: completed **{F.UPLOAD_COMPLETION_COUNT}/{F.SESSIONS}**,
  pending **{F.UPLOAD_PENDING_COUNT}/{F.SESSIONS}** — raw packets present,
  server-upload completion incomplete.
- Channel evidence: frequency agreement {F.FREQ_AGREEING}/{F.FREQ_EVALUABLE};
  median zero-lag correlation {F.MEDIAN_ZERO_LAG_CORR}; median max lagged correlation
  {F.MEDIAN_MAX_LAGGED_CORR}; median coherence {F.MEDIAN_COHERENCE}; median best lag
  {F.MEDIAN_BEST_LAG_SAMPLES} samples. Verdict: **{F.CHANNEL_VERDICT}**.
- Proprietary rate: **{F.RATE_STATUS}**. Public benchmark: not run.

## Product implications

Ship evidence views on safe aggregates only. Do not expose proprietary rates while gates
fail. Treat decoder outputs as research candidate streams. Upload completeness and field
normalization remain product priorities independent of physiology.

## Scientific limitations

Decoder remains UNVERIFIED. Channel agreement is insufficient under multi-metric gates.
No physiological PPG confirmation. No HR/HRV/SpO2/blood-pressure outputs. No disease risk scoring.
Candidate frequency must never be labeled as heart rate.

## Recommended next steps

1. Curate `dashboard.safe.v1` exports from reviewed safe reports for operator dashboards.
2. Improve upload completeness and synchronized reference capture for future studies.
3. Run isolated public benchmarks only when ethically and contractually cleared — never
   mix into proprietary decoder ranking.
4. Pursue clinical-validation protocols before any vital-sign product claim.
"""
    assert_no_forbidden_terminology(text, context="executive_summary")
    wc = _word_count(text)
    if wc > 900:
        raise ValueError(f"executive_summary exceeds 900 words ({wc})")
    return text


def technical_report() -> str:
    text = f"""# Technical Report

## Project architecture

Offline Python package (`wearable-health-intelligence` v0.4.0) with four phases:

1. **Secure Audit** (`src/audit`) — structural CSV/JSON profiling → private + safe profiles.
2. **Packet Forensics** (`src/forensics`) — schema validation, 192 decoder hypotheses, timebase gaps.
3. **Candidate Reconstruction** (`src/reconstruction`) — layouts, payload hypotheses, quality,
   channel compatibility, fail-closed rate gates; optional isolated public benchmark.
4. **Evidence Dashboard** (`src/dashboard`) — Streamlit UI + delivery docs from safe JSON only.

Private outputs branch to an operator-supplied secure directory and **must not** feed the
dashboard. See `architecture.mmd`.

## Phase 1 methodology

Streaming CSV read of an explicit `--input` path. Column kind detection, bounded JSON walks,
modality coverage counters, upload inconsistency codes. Safe profile drops per-session
inconsistency detail and retains aggregate counts only.

## Phase 2 methodology

Extract nested packets, validate keys/payload length, position/bit forensics, score
signedness × byte-order × layout candidates, reconstruct packet timebases, count gaps above
threshold. Selected status defaults to UNVERIFIED unless provisional/accepted gates apply.
No FFT/ML physiological decoding in Phase 2.

## Phase 3 methodology

Reconstruct candidate multi-channel streams under explicit layouts
(`INTERLEAVED_PACKET_LOCAL`, …) and payload hypotheses (`H_2x33`, `H_2x32_plus_2global`,
`H_2block_meta_per_ch`, `H_3x22`). Split on gap rule
`max(1.5 × median packet interval, 1500 ms)`. Score periodicity, quality windows, and
channel pairs; aggregate channel compatibility on the selected best layout/hypothesis only.
Proprietary rate is fail-closed.

## Privacy and threat model

Threats: accidental commit of PHI, path leakage, exact timestamps, raw waveforms in shared
reports. Controls: explicit paths only; scrubber for MAC/UUID/ISO timestamps; safe vs private
split; dashboard refuses CSV/parquet; demo mode uses synthetic aggregates; no network/telemetry.

## Data findings (validated aggregates)

| Metric | Value |
|--------|-------|
| Sessions | {F.SESSIONS} |
| Packets | {F.PACKETS} |
| Malformed packets | {F.MALFORMED_PACKETS} |
| Gaps > {F.GAP_THRESHOLD_MS} ms | {F.GAPS_GT_THRESHOLD} |
| Max gap (ms) | {F.MAX_GAP_MS} |
| Payload length | {F.NOMINAL_PAYLOAD_LENGTH} |
| dataType mode | {F.DATATYPE_MODE} |

## Reviewed export availability

Secondary modality session counts map only from explicit Phase 1 safe
`modality_coverage[].status_counts` aggregates. `samples_present` is used directly.
When that key is absent, zero is derived only if `column_absent`, `payload_empty`, and/or
`structure_present_no_samples` account for every Phase 1 row. Malformed, non-evaluable,
partial, unknown, or absent modality coverage remains `NOT_AVAILABLE`.

Current reviewed safe aggregates do not provide sufficient entries for these source paths:
`phase1.modality_coverage[ecg].samples_present`,
`phase1.modality_coverage[temperature].samples_present`,
`phase1.modality_coverage[sleep].samples_present`,
`phase1.modality_coverage[activity].samples_present`, and
`phase1.modality_coverage[blood_pressure].samples_present`.

## Packet forensics

Decoder candidates evaluated: {F.DECODER_CANDIDATE_COUNT}. Selected status:
**{F.DECODER_STATUS}**. Top family: **{F.TOP_DECODER_FAMILY}**.

## Decoder hypotheses (Phase 3 scoreboard)

| Hypothesis | band_ratio | usable_fraction | frequency_cv |
|------------|------------|-----------------|--------------|
| {F.HYPOTHESIS_SCORES[0]['hypothesis_id']} | {F.HYPOTHESIS_SCORES[0]['band_ratio']} | {F.HYPOTHESIS_SCORES[0]['usable_fraction']} | {F.HYPOTHESIS_SCORES[0]['frequency_cv']} |
| {F.HYPOTHESIS_SCORES[1]['hypothesis_id']} | {F.HYPOTHESIS_SCORES[1]['band_ratio']} | {F.HYPOTHESIS_SCORES[1]['usable_fraction']} | {F.HYPOTHESIS_SCORES[1]['frequency_cv']} |
| {F.HYPOTHESIS_SCORES[2]['hypothesis_id']} | {F.HYPOTHESIS_SCORES[2]['band_ratio']} | {F.HYPOTHESIS_SCORES[2]['usable_fraction']} | {F.HYPOTHESIS_SCORES[2]['frequency_cv']} |
| {F.HYPOTHESIS_SCORES[3]['hypothesis_id']} | {F.HYPOTHESIS_SCORES[3]['band_ratio']} | {F.HYPOTHESIS_SCORES[3]['usable_fraction']} | {F.HYPOTHESIS_SCORES[3]['frequency_cv']} |

Best layout: **{F.TOP_LAYOUT}**. Best hypothesis: **{F.TOP_HYPOTHESIS}**.

## Reconstruction methodology

Candidate streams are research reconstructions under stated hypotheses. Quality labels:
`unusable`, `poor`, `uncertain`, `plausible_candidate_signal`. Counts:
{F.QUALITY_LABEL_COUNTS}. Segments: continuous={F.CONTINUOUS_SEGMENTS},
channel-segments={F.CHANNEL_SEGMENTS}. Periodicity plausible/weak/non-evaluable =
{F.PERIODICITY_PLAUSIBLE}/{F.PERIODICITY_WEAK}/{F.PERIODICITY_NON_EVALUABLE}.
Mean candidate periodic frequency ≈ {F.CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ} Hz
(not heart rate).

## Channel-gate correction

Existential `channels_compatible` (any agreeing pair) was removed. Multi-metric aggregate
verdicts: COMPATIBLE / PARTIALLY_COMPATIBLE / INSUFFICIENT_CHANNEL_AGREEMENT / NOT_EVALUABLE.
Observed verdict: **{F.CHANNEL_VERDICT}**. Frequency agreement {F.FREQ_AGREEING}/{F.FREQ_EVALUABLE};
median zero-lag {F.MEDIAN_ZERO_LAG_CORR}; median lagged {F.MEDIAN_MAX_LAGGED_CORR};
median coherence {F.MEDIAN_COHERENCE}; median best lag {F.MEDIAN_BEST_LAG_SAMPLES} samples.
Failed criteria: {F.CHANNEL_FAILED_CRITERIA}.

## Rate gates

Status **{F.RATE_STATUS}**. Failed gates: {F.FAILED_GATES}. Benchmark ran: {F.BENCHMARK_RAN}.

## Test strategy

Pytest suite covers Phase 1–3 privacy, forensics, reconstruction, channel compatibility,
plus Phase 4 loaders, adapters, transforms, terminology, delivery, and Streamlit smoke.

## Reproducibility

```bash
uv sync --group dev
uv run pytest
uv run streamlit run src/dashboard/app.py -- --demo
uv run python -m src.dashboard.delivery --demo --out reports/delivery
```

Phase 1–3 scientific CLIs require operator-supplied external input/output paths.

## Limitations

No unsupported physiological claims. Decoder UNVERIFIED. Channel agreement insufficient.
Rate NOT_COMPUTED. Dashboard does not recompute science from private artifacts.
"""
    assert_no_forbidden_terminology(text, context="technical_report")
    return text


def research_limitations() -> str:
    text = f"""# Research Limitations

1. **Decoder status is UNVERIFIED.** Best family ({F.TOP_DECODER_FAMILY}) and hypothesis
   ({F.TOP_HYPOTHESIS}) are research rankings, not physiological PPG confirmation.
2. **Candidate periodic frequency** (≈ {F.CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ} Hz) is
   research-only signal plausibility and must never be labeled as heart rate.
3. **Channel verdict {F.CHANNEL_VERDICT}** under multi-metric thresholds; median coherence
   and zero-lag correlation do not support product channel fusion claims.
4. **Proprietary rate is {F.RATE_STATUS}** because gates failed (decoder status, public
   benchmark absent, channel agreement insufficient). This is correct fail-closed behavior.
5. **Public benchmark was not run** in the validated study state.
6. **No diagnosis, HR, HRV, SpO2, blood pressure, or disease risk scoring output** exists in this
   prototype.
7. Phase 4 **does not open** raw CSV, private reports, or reconstructed parquet; missing
   fields display as NOT_AVAILABLE rather than inventing statuses.
8. Demo/session ordinals (`Session 001` …) are anonymized aggregates only.
"""
    assert_no_forbidden_terminology(text, context="research_limitations")
    return text


def presentation_outline() -> str:
    text = f"""# Presentation Outline (8–9 slides)

## Slide 1 — Title
- **Key message:** Offline wearable packet R&D evidence package; no clinical claims.
- **Visual:** Product name + phase badges (Audit → Forensics → Reconstruction → Dashboard).
- **Speaker note:** Emphasize privacy and offline constraints immediately.
- Points: offline; safe aggregates; research-only; no vitals.

## Slide 2 — Problem and constraints
- **Key message:** Opaque packet JSON blocks product PPG claims until structure is proven.
- **Visual:** Redacted CSV → nested packet diagram (no real data).
- **Speaker note:** Explain explicit-path and no-network rules.
- Points: privacy; no scanning; no cloud; no LLM.

## Slide 3 — Pipeline architecture
- **Key message:** Private outputs never feed the dashboard.
- **Visual:** Mermaid/architecture.mmd flow.
- **Speaker note:** Point to external secure directory branch.
- Points: Phase 1–3; safe JSON; dashboard; private sink.

## Slide 4 — Data quality findings
- **Key message:** {F.SESSIONS} sessions, {F.PACKETS} packets, {F.MALFORMED_PACKETS} malformed;
  {F.GAPS_GT_THRESHOLD} gaps (max {F.MAX_GAP_MS} ms).
- **Visual:** Session packet bar chart (Session 001…).
- **Speaker note:** Gaps affect continuity, not vital alerts.
- Points: payload 66; dataType 119; upload pending; normalization gaps.

## Slide 5 — Decoder research
- **Key message:** Best family {F.TOP_DECODER_FAMILY}; status {F.DECODER_STATUS}.
- **Visual:** Hypothesis comparison bars (band_ratio / usable_fraction / frequency_cv).
- **Speaker note:** Modest band_ratio margin; not physiological PPG.
- Points: 192 candidates; top hypothesis; layout; limitations.

## Slide 6 — Signal evidence
- **Key message:** Periodic candidate evidence ≠ physiological validation.
- **Visual:** Quality label pie; periodicity counts.
- **Speaker note:** Say “candidate periodic frequency”, never heart rate.
- Points: segments; plausible_candidate_signal; ~{F.CANDIDATE_MEAN_PERIODIC_FREQUENCY_HZ} Hz;
  research-only signal plausibility.

## Slide 7 — Channel gates and rate
- **Key message:** Verdict {F.CHANNEL_VERDICT}; rate {F.RATE_STATUS}.
- **Visual:** Gate checklist (failed items highlighted neutrally).
- **Speaker note:** Explain fail-closed correctness.
- Points: 18/37 agreement; correlations; failed gates; benchmark not run.

## Slide 8 — Product and next steps
- **Key message:** Safe-only dashboards; clinical validation required before vitals.
- **Visual:** Next-steps swimlane (data, technical, clinical).
- **Speaker note:** No diagnosis or disease risk roadmap in this prototype.
- Points: upload quality; reference capture; isolated benchmark; IRB/protocol.

## Slide 9 — Demo (optional)
- **Key message:** Five-minute evidence walkthrough in demo mode.
- **Visual:** Live Streamlit pages 1→6.
- **Speaker note:** Fallback: show delivery markdown if UI fails.
- Points: status cards; charts; limitations; Q&A.
"""
    assert_no_forbidden_terminology(text, context="presentation_outline")
    return text


def demo_script() -> str:
    text = f"""# Five-Minute Demo Script

**Preferred live mode (project results):**
`uv run streamlit run src/dashboard/app.py -- --reviewed`

**Expected dashboard state:** `--reviewed` loaded; banner
“Source: Reviewed anonymized dataset — safe aggregate reports”;
status cards show **UNVERIFIED**, **INSUFFICIENT_CHANNEL_AGREEMENT**, **NOT_COMPUTED**;
sessions={F.SESSIONS}, packets={F.PACKETS}; upload completed 0/{F.SESSIONS},
pending {F.SESSIONS}/{F.SESSIONS}.

**Development-only demo:**
`uv run streamlit run src/dashboard/app.py -- --demo`
(shows SYNTHETIC DEMO - NOT PROJECT RESULTS)

## 0:00–0:30 — Launch
- **Click / run:** reviewed command above
- **Say:** “This dashboard reads only reviewed safe aggregates — no raw CSV, no private
  parquet, no network.”
- **Expect:** Green source banner for reviewed mode.

## 0:30–1:15 — Page 1 Executive Overview
- **Click:** `1. Executive Overview`
- **Say:** “Ten sessions, 8,161 packets, zero malformed, 27 gaps, max gap 47.1 seconds.
  Upload completed 0 of 10 — raw packets exist, upload lifecycle incomplete.
  Decoder UNVERIFIED, channel insufficient, rate NOT_COMPUTED.”
- **Expect:** Three neutral status cards with plain-language captions; modality table.

## 1:15–2:00 — Page 2 Data quality
- **Click:** `2. Data and Upload Quality`
- **Say:** “Median packet interval is about 995 milliseconds. Per-session bars are
  NOT_AVAILABLE because reviewed safe reports do not include session-ordinal packet counts.”
- **Expect:** Upload 0/10 and 10/10; interval metric cards; NOT_AVAILABLE for session charts.

## 2:00–2:45 — Page 3 Decoder research
- **Click:** `3. Decoder Research`
- **Say:** “192 candidates; best family int24 | CAB | C2; three separate charts —
  band-power ratio and usable fraction higher-is-better; frequency CV lower-is-better.
  Margin 0.0112. Best research candidate, not physiological PPG.”
- **Expect:** Three Plotly charts; human-readable hypothesis labels.

## 2:45–3:30 — Page 4 Signal evidence
- **Click:** `4. Signal Evidence`
- **Say:** “35 of 74 channel-segments plausible (47.3%). Mean candidate periodic
  frequency 1.95 Hz — not interpreted as a vital sign.”
- **Expect:** Periodicity metrics; overlapping-window warning; quality pie.

## 3:30–4:20 — Page 5 Channel and rate gates
- **Click:** `5. Channel Evidence and Rate Gates`
- **Say:** “Frequency agreement 18/37 = 48.6%; thresholds failed; NOT_COMPUTED because
  decoder unverified, public benchmark not run, and channel evidence insufficient.”
- **Expect:** Evidence table; plain-language failed criteria; collapsed technical details.

## 4:20–5:00 — Page 6 Conclusions
- **Click:** `6. Conclusions and Next Steps`
- **Say:** “What we verified, what remains unverified, and recommended next actions —
  protocol/SDK, reference PPG/ECG, accelerometer, upload lifecycle.”
- **Expect:** Three prominent top sections.

## Fallback if dashboard fails
1. Open `reports/delivery/executive_summary.md` and `technical_report.md`.
2. Walk the same six themes verbally using the tables in the technical report.
3. Show `architecture.mmd` rendered or as source.
4. State status triad aloud: UNVERIFIED / INSUFFICIENT_CHANNEL_AGREEMENT / NOT_COMPUTED.
"""
    assert_no_forbidden_terminology(text, context="demo_script")
    return text


def delivery_checklist() -> str:
    text = """# Delivery Checklist

## Code
- [ ] `src/dashboard/` package present (app, models, loaders, adapters, pages)
- [ ] Phase 1–3 scientific modules unchanged in calculations
- [ ] Package version 0.4.0; streamlit + plotly declared

## Tests
- [ ] `uv run pytest` — prior Phase 1–3 tests still pass
- [ ] Phase 4 loader / adapter / privacy / transforms / delivery / smoke tests pass

## Privacy scan
- [ ] No raw CSV/parquet opened by dashboard
- [ ] No exact timestamps, MAC/UUID, patient/session identifiers in demo or docs
- [ ] Forbidden terminology scan clean on delivery markdown and UI copy

## Safe reports
- [ ] Demo `demo/safe_phase{1,2,3}.json` validates as `dashboard.safe.v1`
- [ ] Explicit-path mode requires all three `--safe-phase*` arguments
- [ ] Missing scientific fields surface as NOT_AVAILABLE

## Dashboard
- [ ] `uv run streamlit run src/dashboard/app.py -- --demo` launches
- [ ] Status cards: UNVERIFIED, INSUFFICIENT_CHANNEL_AGREEMENT, NOT_COMPUTED
- [ ] Six pages render without private data

## Documentation
- [ ] README Phase 4 section: setup, commands, contracts, privacy, limitations
- [ ] Screenshots placeholder section present
- [ ] Delivery folder map documented

## Demo
- [ ] Five-minute script rehearsed (`reports/delivery/demo_script.md`)
- [ ] Fallback path documented if Streamlit fails

## Final limitations
- [ ] `reports/delivery/research_limitations.md` reviewed aloud
- [ ] No vital-sign or disease risk claims in any delivery artifact

## Reproducibility commands
```bash
uv sync --group dev
uv run pytest
uv run python -m src.dashboard.delivery.build_demo
uv run python -m src.dashboard.delivery --demo --out reports/delivery
uv run streamlit run src/dashboard/app.py -- --demo
```
"""
    assert_no_forbidden_terminology(text, context="delivery_checklist")
    return text


def architecture_mmd() -> str:
    text = """flowchart LR
  ExtData[External anonymized data] --> SecureAudit[Secure Audit]
  SecureAudit --> PacketForensics[Packet Forensics]
  PacketForensics --> CandidateReconstruction[Candidate Reconstruction]
  CandidateReconstruction --> ChannelCompat[Channel Compatibility]
  ChannelCompat --> SafeAgg[Safe Aggregate Reports]
  SafeAgg --> EvidenceDash[Evidence Dashboard]
  SecureAudit -.-> PrivateDir[External secure private directory]
  PacketForensics -.-> PrivateDir
  CandidateReconstruction -.-> PrivateDir
  PrivateDir -.->|never feeds| EvidenceDash
"""
    return text


DELIVERY_WRITERS = {
    "executive_summary.md": executive_summary,
    "technical_report.md": technical_report,
    "research_limitations.md": research_limitations,
    "presentation_outline.md": presentation_outline,
    "demo_script.md": demo_script,
    "delivery_checklist.md": delivery_checklist,
    "architecture.mmd": architecture_mmd,
}


def generate_delivery(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, fn in DELIVERY_WRITERS.items():
        path = out_dir / name
        path.write_text(fn().rstrip() + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 4 delivery documents")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate from canonical validated aggregate facts (demo/study facts)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/delivery"),
        help="Output directory for delivery artifacts",
    )
    args = parser.parse_args(argv)
    if not args.demo:
        parser.error("Currently only --demo fact generation is supported (safe facts module)")
    paths = generate_delivery(args.out)
    for p in paths:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

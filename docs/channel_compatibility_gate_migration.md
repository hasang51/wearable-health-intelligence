# Channel-compatibility gate migration (Phase 3)

## Why the existential rule was invalid

The previous proprietary rate gate treated channel compatibility as:

> if **any** channel pair has `dom_freq_agreement=True`, pass `channels_compatible`.

That rule was scientifically invalid:

- One agreeing pair among many disagreeing pairs could unlock the channel gate.
- Pairs were pooled across **all** payload hypotheses and layouts, so rejected
  alternatives could inflate agreement evidence for the selected best hypothesis.
- Zero-lag correlation, maximum lagged correlation, coherence, best-lag
  stability, evaluable-pair count, and agreement fraction were ignored.

## What replaced it

Channel compatibility is now a structured multi-metric aggregate evaluated
**only** on the selected best proprietary hypothesis (selected layout +
payload hypothesis). Verdicts:

| Verdict | Rate channel gate |
|---|---|
| `COMPATIBLE` | may pass as `channel_agreement_compatible` |
| `PARTIALLY_COMPATIBLE` | fail closed (`channel_agreement_partial_only`) |
| `INSUFFICIENT_CHANNEL_AGREEMENT` | fail closed (`channel_agreement_insufficient`) |
| `NOT_EVALUABLE` | fail closed (`channel_agreement_not_evaluable`) |

Safe reports expose aggregate evidence only (verdict, counts, fractions,
medians, thresholds, failed criteria). They do **not** include raw channel
samples, exact timestamps, session identifiers, input paths, or per-pair
raw values.

The obsolete boolean / gate label `channels_compatible` is removed and must
not be reintroduced. `RateGateReport.channels_compatible` remains as an
explicit deprecated nullable field set to `null`.

## Why this cannot unlock proprietary pulse-rate computation

Passing channel agreement is necessary but not sufficient. Proprietary
candidate pulse rate remains fail-closed unless **all** gates pass:

- decoder status provisional/accepted
- public benchmark median absolute HR error
- public benchmark coverage
- spectral / time-domain rate agreement
- channel verdict `COMPATIBLE`

Observed real-data aggregates with ~18/37 frequency agreement and weak
median lagged correlation / coherence evaluate to
`INSUFFICIENT_CHANNEL_AGREEMENT`, and rate status remains `NOT_COMPUTED`.

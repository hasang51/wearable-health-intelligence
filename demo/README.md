# Demo safe aggregates

Bundled **synthetic** JSON for Phase 4 `--demo` mode (development only).

- `aggregate_source_kind: "synthetic_demo"`
- Intentionally differs from reviewed project results (upload counts, session bars,
  packet intervals) so source-integrity checks can detect mixing.
- Banner in UI: `SYNTHETIC DEMO - NOT PROJECT RESULTS`

For director-level live demos use:

```bash
uv run streamlit run src/dashboard/app.py -- --reviewed
```

Regenerate:

```bash
uv run python -m src.dashboard.delivery.build_demo
```

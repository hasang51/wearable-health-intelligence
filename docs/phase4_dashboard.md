# Phase 4 — Evidence Dashboard contracts

## Schema version

Enriched inputs must declare:

```json
{ "schema_version": "dashboard.safe.v1", ... }
```

Unknown versions are rejected. Legacy Phase 1–3 safe reports (no `schema_version`) are adapted with partial field coverage; missing scientific statuses become `NOT_AVAILABLE`.

## CLI

```bash
uv run streamlit run src/dashboard/app.py -- --demo

uv run streamlit run src/dashboard/app.py -- \
  --safe-phase1 PATH \
  --safe-phase2 PATH \
  --safe-phase3 PATH
```

## Privacy

Dashboard never opens CSV/parquet/private reconstructions. No network or telemetry.

"""Local reviewed-dashboard safe aggregate bundle export.

Reads only three explicit Phase 1–3 safe JSON paths and writes one
allowlisted ``dashboard.safe.v1`` bundle. Never opens CSV, parquet,
private reports, or directories. Does not recompute Phase 1–3 science.
"""

from __future__ import annotations

SOURCE_LABEL = "Reviewed anonymized dataset — local safe aggregate reports"

__all__ = [
    "SOURCE_LABEL",
    "DeliveryExportError",
    "export_reviewed_dashboard_bundle",
]


def __getattr__(name: str):
    if name == "DeliveryExportError":
        from src.delivery_export.export import DeliveryExportError

        return DeliveryExportError
    if name == "export_reviewed_dashboard_bundle":
        from src.delivery_export.export import export_reviewed_dashboard_bundle

        return export_reviewed_dashboard_bundle
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Resource limits for defensive CSV/JSON inspection."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResourceLimits:
    """Caps applied during streaming audit."""

    max_json_depth: int = 8
    max_keys_per_object: int = 200
    max_array_elements_inspected: int = 50
    csv_field_size_limit: int = 10 * 1024 * 1024  # 10 MiB

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

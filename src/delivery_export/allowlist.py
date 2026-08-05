"""Strip unknown fields to the dashboard allowlist before Pydantic validate."""

from __future__ import annotations

from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel


def strip_unknown(model_cls: type[BaseModel], data: Any) -> Any:
    """Keep only fields declared on ``model_cls`` (recursively for nested models)."""
    if data is None:
        return None
    if not isinstance(data, dict):
        return data

    cleaned: dict[str, Any] = {}
    for name, field_info in model_cls.model_fields.items():
        if name not in data:
            continue
        cleaned[name] = _strip_value(field_info.annotation, data[name])
    return cleaned


def _strip_value(annotation: Any, value: Any) -> Any:
    if value is None:
        return None

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _strip_value(non_none[0], value)
        for candidate in non_none:
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                if isinstance(value, dict):
                    return strip_unknown(candidate, value)
        return value

    if origin is list:
        inner = args[0] if args else Any
        if isinstance(value, list):
            return [_strip_value(inner, item) for item in value]
        return value

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, dict):
            return strip_unknown(annotation, value)
        return value

    return value

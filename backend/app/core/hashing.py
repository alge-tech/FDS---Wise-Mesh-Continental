"""Canonical JSON (sorted keys, no whitespace) and SHA-256 hex, used for every stored hash."""

import dataclasses
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def _default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, frozenset | set):
        return sorted(v if isinstance(v, str | int) else _default(v) for v in value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, float):
        raise TypeError("float is not allowed in canonical JSON")
    raise TypeError(f"cannot canonicalise {type(value).__name__}")


def canonical_json(value: Any) -> str:
    def reject_floats(obj: Any) -> Any:
        if isinstance(obj, float):
            raise TypeError("float is not allowed in canonical JSON")
        if isinstance(obj, dict):
            return {str(k): reject_floats(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [reject_floats(v) for v in obj]
        return obj

    return json.dumps(
        reject_floats(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    )


def sha256_hex(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def hash_canonical(value: Any) -> str:
    return sha256_hex(canonical_json(value))

"""Canonical candle encoding shared by analytical prefix fingerprints."""

import json
from decimal import Decimal

from pocket_alpha.domain.market import Candle


def canonical(value: object) -> object:
    """Stable across storage Decimal scale, exponent and ambient arithmetic context."""
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        plain = format(value, "f")
        return plain.rstrip("0").rstrip(".") if "." in plain else plain
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    return value


def candle_bytes(candle: Candle) -> bytes:
    payload = candle.model_dump()
    for key in ("open_time", "close_time", "received_at"):
        payload[key] = payload[key].isoformat()
    return json.dumps(canonical(payload), sort_keys=True, separators=(",", ":")).encode() + b"\n"

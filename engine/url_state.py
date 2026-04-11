from __future__ import annotations

import base64
import json
import zlib

from engine.inputs import ModelInputs


def encode_model(inp: ModelInputs) -> str:
    """Compress model inputs into a URL-safe string."""
    data = json.dumps(inp.__dict__, separators=(",", ":"), default=str)
    compressed = zlib.compress(data.encode(), level=9)
    return base64.urlsafe_b64encode(compressed).decode()


def decode_model(encoded: str) -> ModelInputs:
    """Reconstruct ModelInputs from a URL-safe string."""
    compressed = base64.urlsafe_b64decode(encoded)
    data = json.loads(zlib.decompress(compressed).decode())
    for k, v in data.items():
        default = getattr(ModelInputs, k, None)
        if isinstance(default, int):
            data[k] = int(v)
        elif isinstance(default, float):
            data[k] = float(v)
        elif isinstance(default, bool):
            data[k] = bool(v)
    # Filter to only valid ModelInputs fields (forward compat)
    from dataclasses import fields as _fields
    valid = {f.name for f in _fields(ModelInputs)}
    data = {k: v for k, v in data.items() if k in valid}
    return ModelInputs(**data)


def encode_deal(before: dict, after: dict, comp: dict, eng: dict, name: str = "Shared Deal") -> str:
    """Compress a complete deal (before/after models + comp + engagement) into a URL string."""
    payload = {"name": name, "before": before, "after": after, "comp": comp, "eng": eng}
    data = json.dumps(payload, separators=(",", ":"), default=str)
    compressed = zlib.compress(data.encode(), level=9)
    return base64.urlsafe_b64encode(compressed).decode()


def decode_deal(encoded: str) -> dict:
    """Reconstruct a deal payload from a URL string. Returns dict with before/after/comp/eng/name."""
    compressed = base64.urlsafe_b64decode(encoded)
    return json.loads(zlib.decompress(compressed).decode())

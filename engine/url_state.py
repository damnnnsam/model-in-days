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
    return ModelInputs(**data)

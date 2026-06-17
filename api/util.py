"""Shared helpers for the API/runner."""
import math
import numpy as np


def json_safe(o):
    """Make engine output JSON/Firestore-safe: numpy scalars -> python, NaN/inf ->
    None, recurse through dict/list/tuple."""
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(x) for x in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    return o

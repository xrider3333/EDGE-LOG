"""Shared helpers for the API/runner."""
import base64
import gzip
import json
import math
import numpy as np


# A command reply lands in ONE Firestore document, and Firestore builds an index entry for
# every leaf of every map inside an array. 40,000 entries is the hard per-document cap, so a
# few thousand candles (six fields each, plus an overlay per bar) blows straight through it and
# the whole reply is rejected with INDEX_ENTRIES_COUNT_LIMIT_EXCEEDED - the fetch simply never
# comes back. A large reply therefore travels as ONE opaque string, which is one index entry.
PACK_OVER_BYTES = 120_000     # pack above this; well under the 40k-entry cliff
GZIP_OVER_BYTES = 600_000     # gzip above this, to stay under the 1 MiB document cap


def pack_command_result(res):
    """json_safe(), then fold a large reply into a single string field the web app unpacks."""
    safe = json_safe(res)
    if not isinstance(safe, dict):
        return safe
    try:
        blob = json.dumps(safe, separators=(",", ":"))
    except Exception:
        return safe
    if len(blob) <= PACK_OVER_BYTES:
        return safe
    out = {k: safe[k] for k in ("ok", "error") if k in safe}
    body = json.dumps({k: v for k, v in safe.items() if k not in ("ok", "error")},
                      separators=(",", ":"))
    if len(body) > GZIP_OVER_BYTES:
        out["packed_z"] = base64.b64encode(gzip.compress(body.encode("utf-8"), 6)).decode("ascii")
    else:
        out["packed"] = body
    return out


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

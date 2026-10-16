"""Run ENGUQ's own chain_exact_warm.py UNCHANGED on #491's run-time bars: ADJ_NQ_1m_ETH with the 740 bars the 10-15 07:17
ETH fill inserted (2020-02-28 +346, 2020-06-30 +394; absent from split_qa/preeth_20261015/NOADJ_NQ_1m_ETH.csv) masked out.
trace_491_fill.py showed this mask reproduces all 8 stored folds bit-exact; this lets ENGUQ's script pass its own parity
gate and print its four numbers."""
import os
import runpy
import sys

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
import augur_engine.data as D  # noqa: E402

_orig = D.load_master_arrays
BAK = pd.read_csv("C:/EdgeLog/_research_cache/split_qa/preeth_20261015/NOADJ_NQ_1m_ETH.csv", usecols=["time"],
                  dtype={"time": np.int64})["time"].to_numpy()


def patched(m, *a, **kw):
    A = _orig(m, *a, **kw)
    if (m or {}).get("filename") != "ADJ_NQ_1m_ETH.csv":
        return A
    t = pd.DatetimeIndex(A["index"]).tz_convert("UTC").asi8 // 10**9
    keep = np.isin(t, BAK)
    print("[ttm] masked %d bars inserted after #491 ran" % int((~keep).sum()))
    out = {k: (np.asarray(v)[keep] if k not in ("index", "meta", "fingerprint") else v) for k, v in A.items()}
    out["index"] = A["index"][keep]
    return out


D.load_master_arrays = patched
sys.argv = ["chain_exact_warm.py", "C:/EdgeLog/_anatomy_cache/enguq_491/run491.json"]
runpy.run_path("C:/EdgeLog/_anatomy_cache/ttm_store491/chain_exact_warm_copy.py", run_name="__main__")

"""TTM (standing verifier) - store-integrity trace for ENGU-Q run #491 (ENGUQ #113 / TTM #97 offer).

ENGUQ's bit-exact chain rebuild (C:/EdgeLog/_anatomy_cache/enguq_491/chain_exact_warm.py, today's master) reproduces folds
1, 2, 3, 7 and misses 4, 5, 6, 8. Hypothesis written BEFORE this ran: the store is right and the MASTER changed under it.
#491 finished 2026-10-14 16:26; at 2026-10-15 07:17 the NQ overnight fill (eth_fill_COMMIT_20261015.log) inserted 346 bars
into the truncated 2020-02-28 session and 394 into 2020-06-30 = 740 bars inside the optimize window. Fold bounds are BAR
INDICES (validate.py:97), so every fold from 2020 on now points at bars about half an ETH session earlier, and fold 4 holds
both filled sessions. Today's optimize arrays are 5,087,053 bars; #491's last fold ends at 5,086,313 = exactly 740 fewer.

Test (pass = ALL 8 folds bit-exact on count and net, the parity rule chain_exact_warm.py uses):
  OLD = today's ADJ_NQ_1m_ETH optimize arrays with every bar whose timestamp is NOT in the pre-fill NOADJ backup
        (split_qa/preeth_20261015/NOADJ_NQ_1m_ETH.csv, written 2026-10-15 05:46, before the 07:17 commit) removed.
  Run the engine's own slice evaluator (auto.make_slice_evaluator, warm) on the stored [train_bars, +test_bars) per fold.
  Also print the bar-index shift each stored bound has suffered, and the same folds on today's arrays (ENGUQ's read).
If OLD reproduces all 8 folds, the mismatch is the 10-15 data fill, not the validate store."""
import importlib.util
import json
import os
import sys

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ["AUGUR_TRIAL_CACHE"] = "0"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.auto import make_slice_evaluator  # noqa: E402

OUT = "C:/EdgeLog/_anatomy_cache/ttm_store491"
R = json.load(open("C:/EdgeLog/_anatomy_cache/enguq_491/run491.json", encoding="utf-8"))
V = R["validate"]
STRAT, COST = R["strategy"], float(R["cost_pts"])
WARM = int(R.get("warm_days") or V.get("windows", {}).get("warm_days") or 0)
OPT = V["windows"]["optimize"]
assert V["wf_oos"]["mode"] == "anchored"

m = find_master("NQ", "1m", "eth", R["data_source"])
NEW = load_master_arrays(m, date_from=OPT[0], date_to=OPT[1])
nb = len(NEW["index"])
t_new = pd.DatetimeIndex(NEW["index"]).tz_convert("UTC").asi8 // 10**9
bak = pd.read_csv("C:/EdgeLog/_research_cache/split_qa/preeth_20261015/NOADJ_NQ_1m_ETH.csv", usecols=["time"],
                  dtype={"time": np.int64})["time"].to_numpy()
keep = np.isin(t_new, bak)
ins = np.flatnonzero(~keep)
ins_days = pd.Series(pd.DatetimeIndex(NEW["index"][ins]).normalize().date).value_counts().sort_index()
print("today's optimize arrays %d bars; bars absent from the pre-fill backup: %d" % (nb, len(ins)))
print(" by ET date:", {str(k): int(v) for k, v in ins_days.items()})
OLD = {k: (np.asarray(v)[keep] if k not in ("index", "meta", "fingerprint") else v) for k, v in NEW.items()}
OLD["index"] = NEW["index"][keep]
print("OLD arrays %d bars" % len(OLD["index"]))
cum_ins = np.cumsum(~keep)                     # inserted bars at or before each NEW position

spec = importlib.util.spec_from_file_location("s", os.path.join("augur_strategies", STRAT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BASE = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
KNOBS = set(mod.DEFAULT_PARAMS)
folds = sorted(R["top10_results"], key=lambda x: x["fold"])
stored = {f["f"]: f for f in V["wf_oos"]["folds"]}
old_pos_in_new = np.flatnonzero(keep)          # OLD bar i sits at NEW position old_pos_in_new[i]

out = {"n_new": nb, "n_old": int(len(OLD["index"])), "inserted": int(len(ins)),
       "inserted_by_day": {str(k): int(v) for k, v in ins_days.items()}, "folds": []}
for label, ARR in (("OLD (pre-fill)", OLD), ("TODAY", NEW)):
    EV = make_slice_evaluator(STRAT, ARR, cost_pts=COST, warm_days=WARM)
    idx = pd.DatetimeIndex(ARR["index"])
    print("\n== %s: stored bounds on these arrays" % label)
    bad, n_all, net_all = [], 0, 0.0
    for f in folds:
        a = int(f["train_bars"])
        b = a + int(f["test_bars"])
        p = dict(BASE)
        p.update({k: v for k, v in f.items() if k in KNOBS})
        res = EV(a, b, p, keep_trades=True, warm=True)
        tr = (res or {}).get("trades") or []
        net = float(sum(float(t[2]) for t in tr))
        s = stored.get(f["fold"], {})
        hit = abs(net - float(s.get("net", -9e9))) < 0.15 and len(tr) == int(s.get("trades", -1))
        bad += [] if hit else [f["fold"]]
        n_all += len(tr)
        net_all += net
        shift = ""
        if label.startswith("OLD"):
            sa = int(old_pos_in_new[a]) - a
            sb = int(old_pos_in_new[min(b, len(old_pos_in_new) - 1)]) - min(b, len(old_pos_in_new) - 1)
            shift = "  today's arrays are shifted +%d bars at a, +%d at b" % (sa, sb)
        print("  fold %d [%d, %d) %s .. %s  net %.1f / %d tr | stored %.1f / %d  %s%s"
              % (f["fold"], a, b, idx[a].strftime("%Y-%m-%d %H:%M"), idx[min(b, len(idx)) - 1].strftime("%Y-%m-%d %H:%M"),
                 net, len(tr), s.get("net", float("nan")), s.get("trades", -1), "OK" if hit else "MISMATCH", shift))
        out["folds"].append({"arrays": label, "fold": f["fold"], "a": a, "b": b, "from": str(idx[a]), "to": str(idx[min(b, len(idx)) - 1]),
                             "net": round(net, 4), "trades": len(tr), "stored_net": s.get("net"), "stored_trades": s.get("trades"),
                             "ok": bool(hit)})
    whole = abs(net_all - float(V["wf_oos"]["net"])) < 1.0 and n_all == int(V["wf_oos"]["trades"])
    print("  chain %d trades net %.1f | stored %d / %.1f -> %s; folds missing: %s"
          % (n_all, net_all, V["wf_oos"]["trades"], V["wf_oos"]["net"], "BIT-EXACT" if whole and not bad else "MISMATCH", bad))
    out[label] = {"chain_trades": n_all, "chain_net": round(net_all, 4), "bit_exact": bool(whole and not bad), "bad_folds": bad}
json.dump(out, open(OUT + "/trace_491_fill.json", "w"), indent=1)

"""
IS THE OVERFIT-PROBABILITY SPIKE REAL, OR IS IT THE MEASUREMENT? (2026-09-24)

WHY. The paired 12 vs 36-month lockbox runs (RESEARCH.md item 9) showed NOISE's overfit
probability jump from 0.448 to 0.825 - across the refusal line - on the same strategy file
and the same search budget. Owner asked the right question: the two arms should be looking
at nearly the same strategy, so is the jump a property of the strategy or of the calculator?

HOW THE NUMBER IS BUILT (augur_engine/validate.py, then analytics.probability_backtest_
overfitting): take the top 24 configs of the in-sample search, re-run each over the whole
PRE-LOCKBOX window, bin every trade's net into calendar months, and hand that 24 x months
matrix to CSCV - chop the months into 10 blocks, and over all 252 ways of splitting them
half in-sample / half out, ask how often the config that looked best in-sample lands below
the median out-of-sample.

THREE THINGS DIFFER BETWEEN THE TWO ARMS, and only one of them is about the strategy:
  1. the 24 CONFIGS are different (each arm searched its own window, so it has its own
     top 24);
  2. the number of MONTHS is different (a 36-month lockbox takes 36 months out of the
     matrix, so each of the 10 blocks is about 20% shorter and its mean is noisier);
  3. the strategy's actual robustness, which is the only thing we want to measure.

THIS SCRIPT SEPARATES THEM by recomputing the number with one factor changed at a time:
  A  run A's configs, run A's months           -> should reproduce the stored number
  B  run A's configs, run B's shorter months    -> isolates the MONTH COUNT
  C  run B's configs, run B's shorter months    -> should reproduce run B's stored number
     (B -> C therefore isolates the CONFIG SET)

Nothing here opens a lockbox: every cell is scored on months at or before the EARLIER of
the two arms' tuning cut-offs, which both runs had already searched.

    python tools/pbo_probe.py --a 406 --b 405
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays        # noqa: E402
from augur_engine.engine import run_backtest                         # noqa: E402
from augur_engine.analytics import probability_backtest_overfitting  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TOP_N = 24            # the same 24 validate.py feeds the calculator
CACHE = r"C:\EdgeLog\_anatomy_cache"   # month rows land here so a re-run is instant


def run_doc(rid):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    return u.collection("runs").document(str(rid)).get().to_dict() or {}


def top_configs(doc, keys, n=TOP_N):
    """The n best in-sample configs from the saved searched cloud."""
    pts = [p for p in (doc.get("points") or []) if isinstance(p, dict)]
    pts.sort(key=lambda p: -float(p.get("pnl") or 0))
    out, seen = [], set()
    for p in pts:
        cfg = {k: p[k] for k in keys if k in p}
        if len(cfg) != len(keys):
            continue
        sig = tuple(sorted(cfg.items()))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(cfg)
        if len(out) >= n:
            break
    return out


def month_rows(cfgs, arrays, idx, strategy, cost_pts, label):
    """One dict of {(year, month): net} per config, from one backtest each."""
    rows, n = [], len(idx)
    for i, cfg in enumerate(cfgs, 1):
        try:
            bt = run_backtest(strategy, arrays=arrays, params=cfg, cost_pts=cost_pts,
                              return_trades=True)
        except Exception as e:
            print("   %s config %d failed: %s" % (label, i, type(e).__name__))
            continue
        mon = defaultdict(float)
        for t in (bt.get("trades") or []):
            ts = idx.iloc[min(int(t[0]), n - 1)]
            mon[(ts.year, ts.month)] += float(t[2])
        if mon:
            rows.append(mon)
        if i % 6 == 0:
            print("   %s %d/%d" % (label, i, len(cfgs)))
    return rows


def pbo_of(rows, upto=None):
    """CSCV overfit probability over these configs, optionally truncated to `upto`
    (a (year, month) tuple) so two cells can share an identical month range."""
    keys = sorted(set().union(*[set(m.keys()) for m in rows])) if rows else []
    if upto:
        keys = [k for k in keys if k <= upto]
    if len(rows) < 2 or len(keys) < 4:
        return None, len(keys)
    perf = [[m.get(k, 0.0) for k in keys] for m in rows]
    return probability_backtest_overfitting(perf), len(keys)


def _cache_path(a, b):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, "pbo_probe_%s_%s.json" % (a, b))


def _save(path, rA, rB):
    ser = lambda rows: [{"%d-%02d" % k: v for k, v in m.items()} for m in rows]
    json.dump({"A": ser(rA), "B": ser(rB)}, open(path, "w", encoding="utf-8"))


def _load(path):
    raw = json.load(open(path, encoding="utf-8"))
    de = lambda rows: [{(int(k[:4]), int(k[5:])): float(v) for k, v in m.items()} for m in rows]
    return de(raw["A"]), de(raw["B"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=int, required=True, help="run with the LONGER tuning window")
    ap.add_argument("--b", type=int, required=True, help="run with the SHORTER tuning window")
    ap.add_argument("--subsets", type=int, default=0,
                    help="also draw this many random 24-config subsets from the pooled "
                         "elite configs, on ONE fixed month range, to show how much of the "
                         "number is just which elites went in")
    ap.add_argument("--fresh", action="store_true", help="ignore the cached month rows")
    args = ap.parse_args()

    A, B = run_doc(args.a), run_doc(args.b)
    for rid, d in ((args.a, A), (args.b, B)):
        if not d:
            sys.exit("ABORT - run #%s not found" % rid)
    keys = sorted((A.get("best_params") or {}).keys())
    strategy = A.get("strategy")
    if strategy != B.get("strategy"):
        sys.exit("ABORT - different strategy files (%s vs %s)" % (strategy, B.get("strategy")))

    wA = ((A.get("validate") or {}).get("windows") or {}).get("optimize") or []
    wB = ((B.get("validate") or {}).get("windows") or {}).get("optimize") or []
    cut = pd.Timestamp(wB[1])
    upto = (cut.year, cut.month)
    print("strategy %s | A #%s tunes to %s | B #%s tunes to %s"
          % (strategy, args.a, wA[1], args.b, wB[1]))
    print("stored overfit probability: A %.3f | B %.3f"
          % (((A.get("validate") or {}).get("pbo") or {}).get("pbo", float("nan")),
             ((B.get("validate") or {}).get("pbo") or {}).get("pbo", float("nan"))))

    master = find_master(A.get("instrument"), A.get("timeframe"), "rth", None) \
        or find_master(A.get("instrument"), A.get("timeframe"), None, None)
    if master is None:
        sys.exit("ABORT - no master for %s %s" % (A.get("instrument"), A.get("timeframe")))
    arrays = load_master_arrays(master, date_from=A.get("date_from"), date_to=wA[1])
    idx = pd.to_datetime(pd.Series(arrays.get("index")))
    cost = float(A.get("cost_pts") or 0)
    print("bars %d, %s .. %s, cost %.3f" % (len(idx), idx.iloc[0].date(), idx.iloc[-1].date(), cost))

    cA, cB = top_configs(A, keys), top_configs(B, keys)
    shared = len(set(tuple(sorted(c.items())) for c in cA)
                 & set(tuple(sorted(c.items())) for c in cB))
    print("top-%d configs: A %d, B %d, shared %d" % (TOP_N, len(cA), len(cB), shared))

    cache = _cache_path(args.a, args.b)
    if os.path.exists(cache) and not args.fresh:
        rA, rB = _load(cache)
        print("month rows read from cache (%d + %d configs)" % (len(rA), len(rB)))
    else:
        rA = month_rows(cA, arrays, idx, strategy, cost, "A")
        rB = month_rows(cB, arrays, idx, strategy, cost, "B")
        _save(cache, rA, rB)
        print("month rows cached ->", cache)

    cells = [("A  A-configs, A-months (reproduce A)", rA, None),
             ("B  A-configs, B-months (month count only)", rA, upto),
             ("C  B-configs, B-months (reproduce B)", rB, upto)]
    print("\n%-44s %7s %8s %9s" % ("cell", "months", "overfit", "lambda avg"))
    for name, rows, up in cells:
        res, nk = pbo_of(rows, up)
        if res is None:
            print("%-44s %7d   n/a" % (name, nk))
            continue
        print("%-44s %7d %8.3f %9.3f" % (name, nk, res["pbo"], res["lambda_mean"]))

    if args.subsets:
        # HOW MUCH OF THE NUMBER IS JUST THE DRAW? Pool both arms' elite configs, hold the
        # month range fixed at the SHORTER one, and keep re-drawing 24 of them. Everything
        # that moves here is measurement, not strategy: same file, same window, same months.
        pool = rA + rB
        rnd = random.Random(42)
        vals = []
        for _ in range(int(args.subsets)):
            pick = rnd.sample(range(len(pool)), min(TOP_N, len(pool)))
            res, _nk = pbo_of([pool[i] for i in pick], upto)
            if res:
                vals.append(res["pbo"])
        if vals:
            vals.sort()
            q = lambda f: vals[min(len(vals) - 1, int(f * len(vals)))]
            print("\nSAME strategy, SAME months, only the 24 configs redrawn (%d draws from "
                  "%d pooled elites):" % (len(vals), len(pool)))
            print("   overfit probability  min %.3f  10%% %.3f  median %.3f  90%% %.3f  max %.3f"
                  % (vals[0], q(0.10), q(0.50), q(0.90), vals[-1]))
            print("   share of draws at or above the 0.5 refusal line: %.0f%%"
                  % (100.0 * sum(1 for v in vals if v >= 0.5) / len(vals)))


if __name__ == "__main__":
    main()

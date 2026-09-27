"""
OVERFIT PROBABILITY AS A BAND, FOR ONE RUN (2026-09-26, docs/DIP_ES_CASE.md 3a; RESEARCH.md 3d / item 14).

The validate's overfit probability is CSCV over the top 24 in-sample configs. When those 24 are near-tied
elites, which 24 go in moves the number more than the strategy does (RESEARCH.md 3d: 0.16..0.91 on one
NOISE strategy). This reports it as a band for ONE run:
  1. take the top --pool (default 48) distinct configs of the run's saved in-sample search (by pnl),
  2. re-run each over the run's own tuning window (validate.windows.optimize) on the run's own master,
  3. bin each config's trade net into calendar months,
  4. recompute the stored number from the top 24 (reproduction check),
  5. draw --draws (default 300) random sets of 24 of the pool (seed 42) and report the band.
Nothing reads the lockbox: every bar is at or before the tuning cut-off.
    python tools/pbo_band.py --run 432 [--pool 48] [--draws 300] [--fresh]
"""
import argparse, json, os, random, sys
from collections import defaultdict
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED if os.path.exists(os.path.join(SHARED, "serviceAccount.json")) else ROOT)
sys.path.insert(0, os.getcwd())
from augur_engine.data import find_master, load_master_arrays        # noqa: E402
from augur_engine.engine import run_backtest                         # noqa: E402
from augur_engine.analytics import probability_backtest_overfitting  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TOP_N = 24
CACHE = r"C:\EdgeLog\_anatomy_cache"


def run_doc(rid):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    return firestore.client().collection("users").document(UID).collection("runs").document(str(rid)).get().to_dict() or {}


def top_configs(doc, keys, n):
    pts = sorted([p for p in (doc.get("points") or []) if isinstance(p, dict)], key=lambda p: -float(p.get("pnl") or 0))
    out, seen = [], set()
    for p in pts:
        cfg = {k: p[k] for k in keys if k in p}
        sig = tuple(sorted(cfg.items()))
        if len(cfg) != len(keys) or sig in seen:
            continue
        seen.add(sig); out.append(cfg)
        if len(out) >= n:
            break
    return out


def pbo(rows):
    keys = sorted(set().union(*[set(m) for m in rows]))
    return probability_backtest_overfitting([[m.get(k, 0.0) for k in keys] for m in rows]), len(keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--pool", type=int, default=48)
    ap.add_argument("--draws", type=int, default=300)
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    D = run_doc(a.run)
    if not D:
        sys.exit("ABORT - run #%d not found" % a.run)
    v = D.get("validate") or {}
    keys = sorted((D.get("best_params") or {}).keys())
    strategy = D["strategy"]; win = (v.get("windows") or {}).get("optimize")
    master = find_master(D["instrument"], D["timeframe"], D.get("session") or "rth", D.get("data_source"))
    if master is None:
        sys.exit("ABORT - no master for %s %s %s" % (D["instrument"], D["timeframe"], D.get("data_source")))
    arrays = load_master_arrays(master, date_from=D.get("date_from"), date_to=win[1])
    idx = pd.to_datetime(pd.Series(arrays.get("index")))
    cost = float(D.get("cost_pts") or 0)
    stored = (v.get("pbo") or {}).get("pbo")
    print("#%d %s on %s %s (%s) | tuning window %s..%s | stored overfit probability %s"
          % (a.run, strategy, D["instrument"], D["timeframe"], D.get("data_source"), win[0], win[1], stored))
    cfgs = top_configs(D, keys, a.pool)
    os.makedirs(CACHE, exist_ok=True)
    cpath = os.path.join(CACHE, "pbo_band_%d_%d.json" % (a.run, a.pool))
    if os.path.exists(cpath) and not a.fresh:
        rows = [{(int(k[:4]), int(k[5:])): x for k, x in m.items()} for m in json.load(open(cpath))]
        print("month rows from cache (%d configs)" % len(rows))
    else:
        rows = []
        for i, cfg in enumerate(cfgs, 1):
            bt = run_backtest(strategy, arrays=arrays, params=cfg, cost_pts=cost, return_trades=True)
            mon = defaultdict(float)
            for t in (bt.get("trades") or []):
                ts = idx.iloc[min(int(t[0]), len(idx) - 1)]
                mon[(ts.year, ts.month)] += float(t[2])
            rows.append(dict(mon))
            if i % 8 == 0:
                print("   %d/%d configs" % (i, len(cfgs)), flush=True)
        json.dump([{"%d-%02d" % k: x for k, x in m.items()} for m in rows], open(cpath, "w"))
    top, nm = pbo(rows[:TOP_N])
    print("reproduction: top-24 recomputed %.3f vs stored %s (%d months, %d configs in pool)"
          % (top["pbo"], stored, nm, len(rows)))
    rnd = random.Random(42); vals = []
    for _ in range(a.draws):
        res, _n = pbo([rows[i] for i in rnd.sample(range(len(rows)), TOP_N)])
        vals.append(res["pbo"])
    vals.sort(); q = lambda f: vals[min(len(vals) - 1, int(f * len(vals)))]
    print("BAND over %d draws of 24 from the top %d: min %.3f  10%% %.3f  median %.3f  90%% %.3f  max %.3f  | at/above 0.5: %.0f%%"
          % (len(vals), len(rows), vals[0], q(0.1), q(0.5), q(0.9), vals[-1], 100.0 * sum(x >= 0.5 for x in vals) / len(vals)))
    verdict = "PASSED" if q(0.5) < 0.5 else ("FAILED" if q(0.1) >= 0.5 else "UNINFORMATIVE")
    trusted = abs(top["pbo"] - float(stored)) <= 0.05 if stored is not None else False
    print("fair bar (docs/DIP_ES_CASE.md 3b): %s%s" % (verdict, "" if trusted else "  [reproduction missed by > 0.05 - band NOT trusted]"))


if __name__ == "__main__":
    main()

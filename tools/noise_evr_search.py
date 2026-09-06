"""
noise_evr_search.py -- EV R-objective random search over NOISE_1_0's own declared ranges,
SUBJECT TO a trade-count floor (owner 2026-09-04 task: raise the FREQUENCY leg's EV R while
keeping its trade count, so the #317 pooled pair rises past every bar at once).

WHY THIS EXISTS. `tools/ryr_search.py` (reused verbatim as the sampler / engine harness) was
run maximising R / YR, which rewards trade COUNT and produced NOISE_1_2_RYR.py (EV R 0.279,
5,548 trades, R/YR 102.6 on the pre-lockbox window) -- the frequency leg of run #317's pooled
pair. Pooled R/YR is roughly additive across legs and pooled EV R lands near the BEST leg's,
so #317's pooled EV R (0.429) is pinned by the ENGU-Q edge leg; the NOISE leg's EV R 0.270 (at
79% of the pair's trades) holds the pair down. This script runs the identical machinery with
the objective flipped to EV R, under a hard floor on trade count so the search cannot just
collapse to a handful of high-quality trades (that would help pooled EV R but crater pooled
R/YR, since R/YR = EV R x trades/year).

PRE-REGISTERED PROTOCOL (owner task, 2026-09-05)
  window     2010-06-07 .. 2025-06-29 (ryr_search.py's WIN; identical to how NOISE_1_2_RYR was
             found -- the lockbox after that is never used for selection here)
  instrument NQ 5m RTH, source db_noadj_rth, cost_pts 0.533, mult 20 (NOISE_1_2_RYR's own
             leg window/costs; matches the #317 pooled pair's FREQUENCY leg exactly)
  sampling   uniform over NOISE_1_0.py's own declared [min, max] on its step (str: its
             options, bool: both), seed fixed (ryr_search.sample, unmodified)
  BUDGET     <= 250 engine evaluations (ryr_search.py's own default + this file's default)
  objective  maximise EV R = (1 - win_rate) x (PF - 1), SUBJECT TO:
               n >= N_FLOOR on the search window (default 3,750 -- scaled down from the task's
               ">= 4,000 trades over the full 2010-06-07..2026-06-30 window" by this window's
               15.06y / that window's 16.06y, so a config landing exactly on 4,000/16.06y also
               clears 3,750 over 15.06y; the full-window count is re-measured exactly for every
               reported candidate, this floor is only the search-time proxy)
               PF >= 1.25 (ryr_search.py's own floor, unchanged)
               8-slice chronological consistency >= 6/8 (unchanged)
  output     tools/r16_results/ryr_search_evr<tag>.csv (via ryr_search.py itself, run with
             its EXISTING R/YR-ranked output) + tools/_noise_evr.json (this file's own
             EV R-ranked, floor-gated summary + full-window re-measurement of the finalists)

This file does NOT re-implement the sampler or the engine call -- it imports `sample`,
`load_params`, `_init` and `one` from ryr_search.py unchanged and only replaces the ranking /
gating step, per the task's instruction to reuse the existing search tool.

Run:  python tools/noise_evr_search.py            (builds the 250-config grid, searches,
                                                     re-measures the top EV R x n_floor
                                                     survivors on the full window + lockbox
                                                     split, writes tools/_noise_evr.json)
"""
import os, sys, csv, json, time, random
import numpy as np
_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The worktree carries the code but not the (gitignored) optimizer_history.db /
# augur_uploads master registry -- augur_engine.paths derives the DB/uploads path
# from wherever the augur_engine PACKAGE itself is imported from (not cwd), so a
# worktree run must import augur_engine (and therefore run this whole script) from
# the SHARED checkout, which holds the real data. Same pattern as
# tools/continuous_lb_check.py's _DATA_REPO fallback. NOISE_1_0.py and ryr_search.py
# are unmodified in this task, so using the shared checkout's copies is byte-identical.
_SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
def _has_registry(root):
    db = os.path.join(root, "optimizer_history.db")
    return os.path.exists(db) and os.path.getsize(db) > 0

ROOT = _WORKTREE if _has_registry(_WORKTREE) else _SHARED
sys.path.insert(0, ROOT); os.chdir(ROOT)
from multiprocessing import Pool

sys.path.insert(0, os.path.join(ROOT, "tools"))
import ryr_search as RS   # reuse sample(), load_params(), _init(), one() verbatim

FN = "NOISE_1_0.py"
INST, TF, SESS, SRC = "NQ", "5m", "rth", "db_noadj_rth"
COST, MULT = 0.533, 20.0
N_CONFIGS = 250
WORKERS = 6
N_FLOOR = 3750          # search-window (15.06y) proxy for ">=4000 over the full 16.06y window"
PF_FLOOR = 1.25
FOLDS_FLOOR = 6
TAG = "evr_noise"

FULL_WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
SPLIT = "2025-06-30"


def full_window_measure(params):
    """Re-run one config on the FULL window (matching the #317 pooled-pair leg exactly) and
    slice by ENTRY time at the lockbox split -- same convention as
    tools/continuous_lb_check.py, so these numbers are directly comparable to that guard and
    to the #317 anchor. Also computes the top-10 concentration guard on the WHOLE window."""
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    import pandas as pd
    m = find_master(INST, TF, SESS, SRC)
    arr = load_master_arrays(m, **FULL_WIN)
    r = run_backtest(FN, arrays=arr, params=params, cost_pts=COST, return_trades=True)
    if not r or not r.get("trades"):
        return None
    idx = pd.DatetimeIndex(arr["index"])
    tz = idx.tz
    def _ts(s):
        t = pd.Timestamp(s)
        return t.tz_localize(tz) if (tz is not None and t.tz is None) else t
    split = _ts(SPLIT)
    trades = sorted(r["trades"], key=lambda t: t[0])
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in trades])
    pnl = np.array([float(t[2]) for t in trades])

    def stats(mask, years):
        p = pnl[mask]
        n = len(p)
        if n == 0:
            return dict(n=0, net=0, pf=None, wr=None, dd=0, mar=None, evr=None, ryr=None)
        gp = float(p[p > 0].sum()); gl = float(-p[p < 0].sum())
        pf = (gp / gl) if gl > 1e-9 else (float("inf") if gp > 0 else 0.0)
        wr = 100.0 * float((p > 0).sum()) / n
        net = float(p.sum()) * MULT
        cum = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(cum) - cum)) * MULT
        evr = (1 - wr / 100.0) * (pf - 1)
        ryr = evr * n / years if years else None
        mar = (net / years) / dd if (years and dd > 0) else None
        return dict(n=n, net=round(net), pf=round(pf, 4), wr=round(wr, 1), dd=round(dd),
                    mar=round(mar, 3) if mar is not None else None,
                    evr=round(evr, 4), ryr=round(ryr, 2) if ryr is not None else None)

    y_all = max((_ts(FULL_WIN["date_to"]) - _ts(FULL_WIN["date_from"])).days, 1) / 365.25
    y_lb = max((_ts(FULL_WIN["date_to"]) - split).days, 1) / 365.25
    lb_mask = np.asarray(ent >= split)
    sel_mask = ~lb_mask
    A = stats(np.ones(len(pnl), bool), y_all)
    L = stats(lb_mask, y_lb)

    # top-10 share on the WHOLE window (task's guard, not just selection): fraction of net
    # lost if the ten best trades are deleted, plus net excluding those ten.
    order = np.argsort(-pnl)
    top10 = order[:10] if len(pnl) > 10 else order
    rest_mask = np.ones(len(pnl), bool); rest_mask[top10] = False
    ex10 = stats(rest_mask, y_all)
    share = (1 - ex10["net"] / A["net"]) * 100.0 if A["net"] else None

    return dict(full=A, lockbox=L, ex_top10=ex10,
                top10_share_pct=round(share, 1) if share is not None else None,
                profitable_ex_top10=(ex10["net"] > 0))


def main():
    dp = RS.load_params(FN)
    rng = random.Random(27)
    grid = [{k: v["default"] for k, v in dp.items()}] + [RS.sample(dp, rng) for _ in range(N_CONFIGS - 1)]
    cfg = dict(fn=FN, inst=INST, tf=TF, session=SESS, source=SRC, cost=COST, mult=MULT)
    print(f"{FN} EV R search (floor n>={N_FLOOR}): {len(grid)} configs, {WORKERS} workers, "
          f"NQ 5m RTH db_noadj_rth, cost {COST}, window {RS.WIN}", flush=True)
    t0 = time.time()
    with Pool(processes=WORKERS, initializer=RS._init, initargs=(cfg,)) as pool:
        res = pool.map(RS.one, grid, chunksize=1)
    print(f"search done in {(time.time()-t0)/60:.1f} min", flush=True)

    rows = [dict(**{k: v for k, v in x.items() if k != "params"}, params=x["params"]) for x in res]
    out_dir = os.path.join(_WORKTREE, "tools", "r16_results")
    os.makedirs(out_dir, exist_ok=True)
    csv_rows = [dict(rank=0, **{k: v for k, v in x.items() if k != "params"}, params=str(x["params"])) for x in res]
    for i, x in enumerate(sorted(csv_rows, key=lambda z: -(z.get("evr") if z.get("evr") is not None else -99))):
        x["rank"] = i + 1
    csv_rows.sort(key=lambda z: z["rank"])
    out_csv = os.path.join(out_dir, f"ryr_search_{TAG}.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys())); w.writeheader(); w.writerows(csv_rows)

    ok = [x for x in rows if (x.get("n") or 0) >= N_FLOOR and (x.get("pf") or 0) >= PF_FLOOR
          and (x.get("folds8") or 0) >= FOLDS_FLOOR]
    ok.sort(key=lambda z: -(z.get("evr") or -99))
    print(f"\nconfigs evaluated: {len(rows)} | pass gates (PF>={PF_FLOOR}, n>={N_FLOOR}, "
          f"folds>=6/8): {len(ok)}")
    print(f"{'rk':>3} {'EVR':>5} {'R/YR':>6} {'n':>5} {'tpy':>6} {'PF':>5} {'win%':>5} {'net$':>10} {'DD$':>8} {'MAR':>5} f8")
    for i, x in enumerate(ok[:15]):
        print(f"{i+1:>3} {x['evr']:5.3f} {x['ryr']:6.1f} {x['n']:5} {x['tpy']:6.1f} {x['pf']:5.2f} "
              f"{x['win']:5.1f} {x['net']:>10,} {x['dd']:>8,} {x['mar']:5.1f} {x['folds8']}")

    top3 = ok[:3]
    print(f"\nre-measuring top {len(top3)} EV R survivors on the FULL window "
          f"({FULL_WIN['date_from']}..{FULL_WIN['date_to']}) + lockbox split {SPLIT} ...")
    finalists = []
    for x in top3:
        fw = full_window_measure(x["params"])
        finalists.append(dict(search=x, full_window=fw))
        if fw:
            print(f"  params={x['params']}")
            print(f"    FULL   n={fw['full']['n']} net=${fw['full']['net']:,} PF={fw['full']['pf']} "
                  f"EVR={fw['full']['evr']} R/YR={fw['full']['ryr']} DD=${fw['full']['dd']:,} MAR={fw['full']['mar']}")
            print(f"    LB     n={fw['lockbox']['n']} net=${fw['lockbox']['net']:,} PF={fw['lockbox']['pf']} "
                  f"EVR={fw['lockbox']['evr']}")
            print(f"    top-10 share {fw['top10_share_pct']}% ex-top10 net=${fw['ex_top10']['net']:,} "
                  f"profitable_ex_top10={fw['profitable_ex_top10']}")

    payload = dict(tag=TAG, fn=FN, inst=INST, tf=TF, sess=SESS, src=SRC, cost=COST, mult=MULT,
                   search_window=RS.WIN, full_window=FULL_WIN, split=SPLIT,
                   n_floor=N_FLOOR, pf_floor=PF_FLOOR, folds_floor=FOLDS_FLOOR,
                   n_configs=len(grid), n_passing_gates=len(ok),
                   top15=ok[:15], finalists=finalists)
    out_json = os.path.join(_WORKTREE, "tools", "_noise_evr.json")
    with open(out_json, "w") as f:
        json.dump(payload, f, indent=1, default=str)
    print("\nsaved", out_csv, "and", out_json)


if __name__ == "__main__":
    main()

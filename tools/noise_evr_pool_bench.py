"""
noise_evr_pool_bench.py -- pool each EV R-search finalist (from tools/noise_evr_search.py /
tools/_noise_evr.json) with the unchanged ENGU-Q #309 edge leg, one contract each, no leg
selection, and check the five pre-registered bars against the #317 anchor.

PRE-REGISTERED BARS (owner task, 2026-09-05, written before this file ran) -- the pooled book
must clear ALL FIVE to queue a validate:
  1. pooled EV R  > 0.429
  2. pooled R/YR  > 202.1
  3. pooled PF    > 1.526
  4. >= 400 pooled held-out trades (entries >= 2025-06-30)
  5. the NOISE candidate's OWN top-10 share < 60% and profitable excluding its top ten

#317 anchor (reproduced separately, not re-derived here): pooled n=7573, net $765,030,
PF 1.526, EV R 0.429, R/YR 202.1, drawdown $40,129, MAR 1.19, 520 held-out trades.
  FREQUENCY leg NOISE_1_2_RYR.py: n=5969, net $173,763, PF 1.315, EV R 0.270, R/YR 100.2,
    421 held-out trades, top-10 share 47%.
  EDGE leg ENGUQ_1M_ETH_ER_1_0.py @ #309 crown params: n=1604, net $591,267, PF 1.655,
    EV R 0.434, R/YR 43.4, 99 held-out trades, top-10 58%.

Same window/costs as the leg above: 2010-06-07..2026-06-30, entries, cost 0.533 x $20 for
NQ NOISE (5m RTH, db_noadj_rth) and NQ ENGU-Q (1m ETH, db_noadj_eth) both -- pooling is a
straight concatenation of point P&Ls x $20/pt (both instruments are NQ, same multiplier),
sorted by entry TIME (not index -- the two legs run on different masters with different bar
counts, so entry_idx is only comparable after mapping back to a wall-clock timestamp).

Run:  python tools/noise_evr_pool_bench.py
"""
import os, sys, json
import numpy as np
import pandas as pd

_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"


def _has_registry(root):
    db = os.path.join(root, "optimizer_history.db")
    return os.path.exists(db) and os.path.getsize(db) > 0


ROOT = _WORKTREE if _has_registry(_WORKTREE) else _SHARED
sys.path.insert(0, ROOT); os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                    # noqa: E402

WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
SPLIT = "2025-06-30"
COST, MULT = 0.533, 20.0

ENGUQ_309 = dict(
    buf_atr=0.3, tl_len=206, trail_frac=2.5, ema_len=220, atr_len=52,
    act_R=1.5, breakeven_R=3.0, limit_atr=0.55, er_len=100, stop_mult=1.3,
    regime_len=10, min_brk=1.6, vol_mult=1.1, er_th=0.0,
)

# Bar 1-4 anchor (#317) and bar 5 threshold, pre-registered.
BARS = dict(evr=0.429, ryr=202.1, pf=1.526, lb_trades=400, top10_share_max=60.0)


def get_trades_with_times(plugin, inst, tf, sess, src, params):
    m = find_master(inst, tf, sess, src)
    arr = load_master_arrays(m, **WIN)
    r = run_backtest(plugin, arrays=arr, params=dict(params), cost_pts=COST, return_trades=True)
    if not r or not r.get("trades"):
        return None, None
    idx = pd.DatetimeIndex(arr["index"])
    trades = sorted(r["trades"], key=lambda t: t[0])
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in trades])
    if ent.tz is not None:
        ent = ent.tz_convert("UTC").tz_localize(None)
    pnl = np.array([float(t[2]) * MULT for t in trades])   # dollars, this leg's own mult
    return ent, pnl


def stats(pnl_usd, years):
    n = len(pnl_usd)
    if n == 0:
        return dict(n=0, net=0, pf=None, wr=None, dd=0, mar=None, evr=None, ryr=None)
    a = np.asarray(pnl_usd, float)
    gp = float(a[a > 0].sum()); gl = float(-a[a < 0].sum())
    pf = (gp / gl) if gl > 1e-9 else (float("inf") if gp > 0 else 0.0)
    wr = 100.0 * float((a > 0).sum()) / n
    net = float(a.sum())
    cum = np.cumsum(a); dd = float(np.max(np.maximum.accumulate(cum) - cum))
    evr = (1 - wr / 100.0) * (pf - 1)
    ryr = evr * n / years if years else None
    mar = (net / years) / dd if (years and dd > 0) else None
    return dict(n=n, net=round(net), pf=round(pf, 4), wr=round(wr, 1), dd=round(dd),
                mar=round(mar, 3) if mar is not None else None,
                evr=round(evr, 4), ryr=round(ryr, 2) if ryr is not None else None)


def top10_share(ent, pnl):
    order = np.argsort(-pnl)
    top10 = order[:10] if len(pnl) > 10 else order
    rest = np.ones(len(pnl), bool); rest[top10] = False
    A = stats(pnl, 1.0)   # years irrelevant for net-only comparison
    ex10_net = float(pnl[rest].sum())
    share = (1 - ex10_net / A["net"]) * 100.0 if A["net"] else None
    return share, ex10_net


def main():
    payload = json.load(open(os.path.join(_WORKTREE, "tools", "_noise_evr.json")))
    finalists = payload["finalists"]
    ranked = sorted(finalists, key=lambda f: -(f["search"]["evr"] or -99))

    # candidate 0: the rank-37 near-miss (EV R 0.42, n=3155 on the search window) -- NOT in
    # the JSON's top-3 (that file only carried the 2 configs clearing n>=3750); added by hand
    # from the same CSV / same search run, because it is the highest-EV R survivor of the
    # PF>=1.25 / folds>=6/8 gates at n>=3000, and the whole point of this task is to test
    # whether trading EV R against trade count still pools better than #317.
    rank37 = dict(lookback=46, band_mult_long=0.75, band_mult_short=1.5, exit_mode="boundary",
                  side="Both", window="all_day", flat_eod=True, skip_holidays=True,
                  stop_mode="atr", confirm_bars=4, daytype_mode="skip_top_long",
                  daytype_lo=0.25, daytype_hi=0.85, vol_skip_pct=78.0, stop_k=3.5)

    candidates = [("rank37 (EVR .42/n3155)", rank37)] + \
                 [(f"search-gated rank (EVR {f['search']['evr']})", f["search"]["params"]) for f in ranked]

    print("=" * 100)
    print("ENGU-Q #309 edge leg (unchanged)")
    e_ent, e_pnl = get_trades_with_times("ENGUQ_1M_ETH_ER_1_0.py", "NQ", "1m", "eth",
                                          "db_noadj_eth", ENGUQ_309)
    split = pd.Timestamp(SPLIT)
    y_all = max((pd.Timestamp(WIN["date_to"]) - pd.Timestamp(WIN["date_from"])).days, 1) / 365.25
    e_all = stats(e_pnl, y_all)
    print("  FULL:", e_all)

    results = []
    for label, params in candidates:
        n_ent, n_pnl = get_trades_with_times("NOISE_1_0.py", "NQ", "5m", "rth",
                                              "db_noadj_rth", params)
        if n_ent is None:
            print(f"\n{label}: NO TRADES"); continue
        n_all = stats(n_pnl, y_all)
        share, ex10_net = top10_share(n_ent.to_numpy(), n_pnl)
        bar5 = (share is not None and share < BARS["top10_share_max"] and ex10_net > 0)

        # POOL: concatenate by entry time, one contract each, no leg selection.
        ent_all = np.concatenate([e_ent.to_numpy(), n_ent.to_numpy()])
        pnl_all = np.concatenate([e_pnl, n_pnl])
        order = np.argsort(ent_all)
        ent_all = ent_all[order]; pnl_all = pnl_all[order]
        pooled = stats(pnl_all, y_all)
        lb_mask = ent_all >= split.to_datetime64()
        pooled_lb = stats(pnl_all[lb_mask], max((pd.Timestamp(WIN["date_to"]) - split).days, 1) / 365.25)
        cum = np.cumsum(pnl_all); peak = np.maximum.accumulate(cum)

        pass1 = pooled["evr"] > BARS["evr"]
        pass2 = pooled["ryr"] > BARS["ryr"]
        pass3 = pooled["pf"] > BARS["pf"]
        pass4 = pooled_lb["n"] >= BARS["lb_trades"]
        pass5 = bar5
        all_pass = pass1 and pass2 and pass3 and pass4 and pass5

        print(f"\n{label}")
        print(f"  NOISE candidate FULL: {n_all}  top10_share={share:.1f}%  ex10_net=${ex10_net:,.0f}  profitable_ex10={ex10_net>0}")
        print(f"  POOLED FULL:  n={pooled['n']} net=${pooled['net']:,} PF={pooled['pf']} EVR={pooled['evr']} "
              f"R/YR={pooled['ryr']} DD=${pooled['dd']:,} MAR={pooled['mar']}")
        print(f"  POOLED LB:    n={pooled_lb['n']} net=${pooled_lb['net']:,} PF={pooled_lb['pf']} EVR={pooled_lb['evr']}")
        print(f"  BARS: (1)EVR>{BARS['evr']}:{pass1}  (2)R/YR>{BARS['ryr']}:{pass2}  (3)PF>{BARS['pf']}:{pass3}  "
              f"(4)LBn>={BARS['lb_trades']}:{pass4}  (5)top10<60%&profitable:{pass5}   ==> {'PASS ALL' if all_pass else 'FAIL'}")

        results.append(dict(label=label, params=params, noise_full=n_all, top10_share=share,
                             ex10_net=ex10_net, pooled_full=pooled, pooled_lb=pooled_lb,
                             pass_bars=dict(b1=pass1, b2=pass2, b3=pass3, b4=pass4, b5=pass5),
                             all_pass=all_pass))

    out = dict(enguq_309_full=e_all, bars=BARS, results=results)
    with open(os.path.join(_WORKTREE, "tools", "_noise_evr_pool.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nsaved tools/_noise_evr_pool.json")


if __name__ == "__main__":
    main()

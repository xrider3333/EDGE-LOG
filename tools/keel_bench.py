"""KEEL bench (2026-09-06): KEEL versions vs RAW vs the incumbent a-priori TILT, three periods.

   PRE  = 2010-06-07 .. 2025-06-29  (tuning-era data, where the v2..v4 choices were read)
   LB   = 2025-06-30 .. 2026-06-29  (the pinned lockbox year)
   POST = 2026-06-30 .. master end   (beyond every pinned window)
plus ORB on ES (transfer: KEEL learns ES trades from ES trades, nothing is refit from NQ).

Usage:  python tools/keel_bench.py {noise|orb|engu|orbes} [v1,v4]
Writes: tools/data/keel_bench_<leg>_<ver>.json and keel_walk_<leg>_<ver>.npz
"""
import os, sys, json, time
import numpy as np
import pandas as pd

# A git worktree has no master registry (optimizer_history.db is untracked), so anything that
# loads a master must run against the SHARED checkout. EDGELOG_REPO_ROOT lets this bench live
# in a worktree while reading the shared registry and engine; unset, behaviour is unchanged.
ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "data")
os.makedirs(OUT, exist_ok=True)
os.chdir(ROOT); sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays      # noqa: E402
from augur_engine.engine import run_backtest                       # noqa: E402
from augur_engine.analytics import sharpe_from_pnls                # noqa: E402
from augur_engine import ml_keel                                   # noqa: E402
from api import paper_gate                                         # noqa: E402

ORB_234 = {"or_bars": 2, "trade_mode": "First-candle dir", "stop_frac": 2.0,
           "atr_filter": 0.7, "vpace_filter": 0.7, "close_confirm": True,
           "breakout_buf": 0.25, "trail_bars": 0, "target_R": 5.5,
           "partial_exit_R": 0.0, "be_after_R": 1.0, "flat_eod": True, "skip_holidays": True}
ENGUQ_265 = {"ema_len": 1380, "tl_len": 170, "atr_len": 106, "buf_atr": 0.9,
             "vol_mult": 0.8, "stop_mult": 1.0, "trail_frac": 2.5, "regime_len": 0,
             "min_brk": 1.3, "breakeven_R": 1.5, "act_R": 2.5,
             "er_len": 60, "er_th": 0.25, "limit_atr": 0.0}
# The CURRENT crown (run #304, live paper leg and a leg of the adopted book #366). KEEL has
# only ever been benched and paper-traded on #243 below, which the crown replaced on
# 2026-09-06 - so this is the first time the overlay meets the configuration actually being
# traded. Same knob set, lookback 40 and vol-skip 95 instead of 44 and 90.
NOISE_304 = {"lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5,
             "exit_mode": "vwap", "side": "Both", "window": "all_day", "flat_eod": True,
             "skip_holidays": False, "stop_mode": "bandwidth", "stop_k": 1.75,
             "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
             "vol_skip_pct": 95.0}
NOISE_243 = {"lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5,
             "exit_mode": "vwap", "side": "Both", "window": "all_day", "flat_eod": True,
             "skip_holidays": False, "stop_mode": "bandwidth", "stop_k": 1.75,
             "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
             "vol_skip_pct": 90.0}
LEGS = {
    "noise": ("NOISE #243",  "NOISE_1_0.py",             NOISE_243, "NQ", "5m", "rth", "db_noadj_rth", "et", 20.0),
    "noise304": ("NOISE #304 (the LIVE crown)", "NOISE_1_0.py", NOISE_304, "NQ", "5m", "rth", "db_noadj_rth", "et", 20.0),
    "orb":   ("ORB #234",    "ORB_3_6_C2.py",            ORB_234,   "NQ", "5m", "rth", "db_noadj_rth", "rf", 20.0),
    "engu":  ("ENGU-Q #265", "ENGUQ_1M_ETH_ER25_1_0.py", ENGUQ_265, "NQ", "1m", "eth", "db_noadj_eth", "logistic", 20.0),
    "orbes": ("ORB #234 on ES", "ORB_3_6_C2.py",         ORB_234,   "ES", "5m", "rth", "db_noadj_rth", "rf", 50.0),
}
FROM, TO = "2010-06-07", None
LB_FROM, POST_FROM = "2025-06-30", "2026-06-30"


def blk(ts, pnl, t0=None, t1=None):
    m = np.ones(len(pnl), bool)
    if t0 is not None: m &= ts >= t0
    if t1 is not None: m &= ts < t1
    p = np.asarray(pnl, float)[m]
    if not len(p):
        return {"n": 0}
    cum = np.cumsum(p); peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float((cum - peak).min())
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    a = ts[m].min(); b = ts[m].max()
    yrs = max((b - a).total_seconds() / (365.25 * 86400), 1 / 12)
    losses = p[p < 0]
    return {"n": int(len(p)), "net": float(p.sum()), "pf": float(gw / gl) if gl > 0 else 99.0,
            "dd": dd, "mar": float((p.sum() / yrs) / abs(dd)) if dd < 0 else 99.0,
            "sharpe": sharpe_from_pnls(list(p), yrs) or 0.0,
            "evr": float(p.mean() / (-losses.mean())) if len(losses) else 0.0}


def yearly_delta(ts, a, b):
    """July-June years, overlay minus raw, pre-lockbox only; mean / se / t / years helped."""
    yr = np.array([t.year if t.month >= 7 else t.year - 1 for t in ts])
    d = pd.Series(np.asarray(a) - np.asarray(b)).groupby(yr).sum()
    d = d[d.index < 2025]
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan
    return {"mean": float(d.mean()), "se": float(se), "t": float(d.mean() / se) if se else np.nan,
            "helped": int((d > 0).sum()), "years": int(len(d)), "series": d.round(0).to_dict()}


def main():
    key = sys.argv[1]
    vers = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else (ml_keel.DEFAULT_VERSION,)
    label, fn, params, inst, tf, sess, src, cm, mult = LEGS[key]
    cost = 0.533 if inst == "NQ" else 0.30
    t0 = time.time()
    arr = load_master_arrays(find_master(inst, tf, sess, src), date_from=FROM, date_to=TO)
    res = run_backtest(fn, arrays=arr, params=params, cost_pts=cost, return_trades=True)
    raw = sorted(list(res.get("trades") or []), key=lambda t: int(t[0]))
    idx = pd.DatetimeIndex(arr["index"])
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    last = len(idx) - 1
    ts = pd.DatetimeIndex([idx[min(int(t[0]), last)] for t in raw])
    pnl = np.array([float(t[2]) for t in raw]) * mult
    lb, post = pd.Timestamp(LB_FROM), pd.Timestamp(POST_FROM)
    print(f"=== {label}: {len(raw)} trades to {idx[-1].date()} (backtest {time.time()-t0:.0f}s)")

    variants = {"RAW": np.ones(len(raw))}
    t1 = time.time()
    prob = paper_gate.score_trades(arr, raw, {"model": cm})
    warm = np.isnan(prob)
    til = paper_gate._tilt_weights(prob, warm, "linear")
    variants[f"TILT {cm} linear (incumbent)"] = np.minimum(til / til[ts < lb].mean(), 3.0)
    print(f"  incumbent {cm}: {time.time()-t1:.0f}s")
    feats = ml_keel.keel_features(arr)
    walks = {}
    for v in vers:
        t1 = time.time()
        kw = ml_keel.keel_walk(arr, raw, feats=feats, version=v)
        walks[v] = kw
        variants[f"KEEL {v}"] = kw["size"]
        tmn = {k: round(float(x.mean()), 3) for k, x in kw["trust_members"].items()}
        print(f"  KEEL {v}: {time.time()-t1:.0f}s, trust>0 {(kw['trust']>0).mean()*100:.0f}%, "
              f"mean trust {kw['trust'].mean():.2f}, member trust {tmn}")
    kwl = walks[vers[-1]]
    variants["  ablate: trust off"] = ml_keel.sizes_from_z(kwl["z"], np.ones(len(raw)))
    for m, zz in kwl["z_members"].items():
        if np.isfinite(zz).any():
            variants[f"  ablate: {m} only"] = ml_keel.sizes_from_z(zz, kwl["trust_members"][m])

    base = None; out = {}
    for name, s in variants.items():
        p = pnl * s
        P = blk(ts, p, None, lb); L = blk(ts, p, lb, post); Q = blk(ts, p, post, None)
        if base is None:
            base = (P, L, Q)
        def f(b, bb):
            if b.get("n", 0) == 0: return "n/a"
            return "n%4d $%9s PF %.2f DD $%8s MAR %5.2f | d$ %+8s" % (
                b["n"], f"{b['net']:,.0f}", b["pf"], f"{b['dd']:,.0f}", b["mar"], f"{b['net']-bb['net']:,.0f}")
        print("%-32s size %.3f max %.2f" % (name, s[ts < lb].mean(), s.max()))
        print("    PRE  " + f(P, base[0])); print("    LB   " + f(L, base[1])); print("    POST " + f(Q, base[2]))
        out[name] = {"pre": P, "lb": L, "post": Q}
    for v in vers:
        yd = yearly_delta(ts, pnl * walks[v]["size"], pnl)
        print("  KEEL %s year-by-year pre-LB: mean %+.0f se %.0f t %.2f helped %d/%d" % (
            v, yd["mean"], yd["se"], yd["t"], yd["helped"], yd["years"]))
        out[f"yearly_{v}"] = yd
    yd = yearly_delta(ts, pnl * variants[f"TILT {cm} linear (incumbent)"], pnl)
    print("  TILT year-by-year pre-LB: mean %+.0f se %.0f t %.2f helped %d/%d" % (
        yd["mean"], yd["se"], yd["t"], yd["helped"], yd["years"]))
    out["yearly_tilt"] = yd
    tag = vers[-1]
    np.savez(os.path.join(OUT, f"keel_walk_{key}_{tag}.npz"), pnl=pnl,
             ts=ts.values.astype("datetime64[ns]"), E=kwl["E"], XB=kwl["X"], prob=prob,
             **{f"{v}_{k}": walks[v][k] for v in walks for k in ("size", "z", "trust")},
             **{f"last_z_{m}": z for m, z in kwl["z_members"].items()},
             **{f"last_t_{m}": t for m, t in kwl["trust_members"].items()})
    json.dump(out, open(os.path.join(OUT, f"keel_bench_{key}_{tag}.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

"""
BOOK ROUND 55b - is the hourly-squeeze TILT on the NOISE leg real, or just more NOISE? (2026-09-14)

Round 55 found that none of the validated single-slot swaps clears the pre-registered bar, but that
LAYERING the hourly squeeze filter on top of the raw NOISE crown - so a trade taken in a compressed hour
carries two contracts and every other trade carries one - lifts run #379 on BOTH stretches:
selection 44.35 -> 48.03 (+8.3%), held-back year 11.02 -> 11.82 (+7.3%), drawdown slightly LOWER.

That could be three different things, and this round separates them:
  1. plain leverage on the NOISE leg          -> control: raw NOISE at weight 1.128 (same extra dollars)
                                                  and at weight 2 (the round-49 leverage row)
  2. adding size to ANY 615 NOISE trades        -> null A: 615 trades drawn at random, 300 draws
  3. adding size to ANY clustered 615 trades    -> null B: the real keep/skip mask SHIFTED around the
                                                  trade sequence by a random offset, 300 draws - keeps
                                                  the filter's run-lengths and firing rate, breaks only
                                                  its alignment with compression (the shift null the
                                                  KEEL work settled on for a CONDITION tilt)

PRE-REGISTERED: the tilt is real only if it beats at least 95 percent of BOTH nulls on selection-window
net-over-drawdown AND on the held-back year, and beats both leverage controls on both stretches.
The hourly-filter trades must first be shown to be an exact SUBSET of the raw crown's trades, or the
whole framing is wrong and the round stops.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB0 = pd.Timestamp("2025-06-30")
NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}
S = "augur_strategies/"
N_DRAWS = 300


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def trades(fn, inst, tf, sess, cost, mult, params):
    src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
    A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest(fn, arrays=A, params=(params if params is not None else defaults(fn)),
                     cost_pts=cost, return_trades=True)
    df = pd.DataFrame({"ent": [t[0] for t in r["trades"]], "ex": [t[1] for t in r["trades"]],
                       "pnl": [t[2] * mult for t in r["trades"]]})
    df["day"] = [idx[i].tz_localize(None).normalize() for i in df.ex]
    return df


def to_daily(df, w=None):
    v = df.pnl.values * (1.0 if w is None else w)
    return pd.Series(v, index=df.day.values).groupby(level=0).sum().sort_index()


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


def mar2(s):
    s = s.sort_index()
    out = []
    for sel in (s.index < LB0, s.index >= LB0):
        z = s[sel]; dd = -dd_of(z)
        out.append(float(z.sum()) / dd if dd > 0 else 99.0)
    return out


def pool(*series):
    return pd.concat(series, axis=1).sort_index().fillna(0).sum(axis=1)


if __name__ == "__main__":
    print("building legs")
    orb = to_daily(trades(S + "ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    enq = to_daily(trades(S + "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None))
    ttm = to_daily(trades(S + "TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m", "rth", 0.363, 50.0, None)) * 3.0
    raw = trades(S + "NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)
    hsq = trades(S + "NOISE_1_9_HSQ304.py", "NQ", "5m", "rth", 0.533, 20.0, None)
    rest = pool(orb, enq, ttm)

    # 0. the framing check - the filter's trades must be the crown's trades, not new ones
    key_raw = dict(zip(zip(raw.ent, raw.ex), raw.pnl))
    matched = sum(1 for e, x, p in zip(hsq.ent, hsq.ex, hsq.pnl) if (e, x) in key_raw and abs(key_raw[(e, x)] - p) < 0.01)
    print(f"\nframing check: {matched} of {len(hsq)} hourly-filter trades are identical crown trades "
          f"(same entry bar, exit bar and profit)")
    if matched < 0.98 * len(hsq):
        sys.exit("STOP: the filter is not a subset of the crown, so 'tilt' is the wrong description")
    mask = np.array([(e, x) in set(zip(hsq.ent, hsq.ex)) for e, x in zip(raw.ent, raw.ex)])
    k = int(mask.sum())

    base = mar2(pool(rest, to_daily(raw)))
    real = mar2(pool(rest, to_daily(raw), to_daily(raw[mask])))
    extra = float(raw[mask].pnl.sum()) / float(raw.pnl.sum())
    lev_same = mar2(pool(rest, to_daily(raw, 1.0 + extra)))
    lev_2 = mar2(pool(rest, to_daily(raw, 2.0)))
    print(f"\n  #379 baseline                         selection {base[0]:6.2f}   held-back {base[1]:6.2f}")
    print(f"  REAL TILT (compressed hours x2)       selection {real[0]:6.2f}   held-back {real[1]:6.2f}")
    print(f"  leverage control, same extra dollars  selection {lev_same[0]:6.2f}   held-back {lev_same[1]:6.2f}"
          f"   (NOISE at weight {1 + extra:.3f})")
    print(f"  leverage control, NOISE at weight 2   selection {lev_2[0]:6.2f}   held-back {lev_2[1]:6.2f}")

    rng = np.random.default_rng(20260914)
    nullA, nullB = [], []
    n = len(raw)
    for i in range(N_DRAWS):
        pick = np.zeros(n, bool); pick[rng.choice(n, k, replace=False)] = True
        nullA.append(mar2(pool(rest, to_daily(raw), to_daily(raw[pick]))))
        off = int(rng.integers(1, n))
        nullB.append(mar2(pool(rest, to_daily(raw), to_daily(raw[np.roll(mask, off)]))))
    nullA = np.array(nullA); nullB = np.array(nullB)

    def rank(col, arr):
        return 100.0 * float((arr[:, col] < real[col]).mean())

    print(f"\n  null A - {k} random crown trades doubled, {N_DRAWS} draws:")
    print(f"      selection median {np.median(nullA[:,0]):6.2f}  95th pct {np.percentile(nullA[:,0],95):6.2f}  "
          f"real beats {rank(0, nullA):5.1f}%")
    print(f"      held-back median {np.median(nullA[:,1]):6.2f}  95th pct {np.percentile(nullA[:,1],95):6.2f}  "
          f"real beats {rank(1, nullA):5.1f}%")
    print(f"  null B - the real mask shifted by a random offset, {N_DRAWS} draws:")
    print(f"      selection median {np.median(nullB[:,0]):6.2f}  95th pct {np.percentile(nullB[:,0],95):6.2f}  "
          f"real beats {rank(0, nullB):5.1f}%")
    print(f"      held-back median {np.median(nullB[:,1]):6.2f}  95th pct {np.percentile(nullB[:,1],95):6.2f}  "
          f"real beats {rank(1, nullB):5.1f}%")
    ok = (min(rank(0, nullA), rank(1, nullA), rank(0, nullB), rank(1, nullB)) >= 95.0
          and real[0] > max(lev_same[0], lev_2[0]) and real[1] > max(lev_same[1], lev_2[1]))
    print("\n  VERDICT:", "REAL - clears every pre-registered test" if ok else "NOT ESTABLISHED - fails at least one pre-registered test")
    pd.DataFrame(np.c_[nullA, nullB], columns=["A_sel", "A_lb", "B_sel", "B_lb"]).to_csv(
        "tools/r16_results/book55b_tilt_null.csv", index=False)
    print("saved tools/r16_results/book55b_tilt_null.csv")

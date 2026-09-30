"""
ORB order flow at the breakout - FORWARD SHADOW scorer (pre-registered 2026-09-30).
Rule: docs/PREREG_orb_orderflow_shadow_2026-09-30.md. Written before any P&L on the feature was read.

    python tools/orb_orderflow_shadow.py              score the forward trades (from 2026-10-01)
    python tools/orb_orderflow_shadow.py --describe   the capture period 2026-06-23..2026-09-30, DESCRIPTIVE ONLY

Crown #314 trades are regenerated with the engine on the house NQ 5m master; each trade's signal bar
(the 5m bar whose close triggered the entry) gets F1 = summed 10s delta, valid when >= 24 of its 30
rows carry a non-zero delta. Arm = 1.5x with the trade, 0.5x against, 1x zero/invalid; twin = 1x.
Run from the shared checkout (BACKTEST_SPEED rule 3: worktrees have no master registry).
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

TICKS = r"C:\EdgeLog\ohlc\NQ_10s.csv"
ES_TICKS = r"C:\EdgeLog\ohlc\ES_10s.csv"          # F4, reported only (addendum 2026-09-30)
FN = "augur_strategies/ORB_3_6.py"
COST, MULT = 0.533, 20.0
CAPTURE_FROM, FORWARD_FROM, FINAL_N, FINAL_DATE = "2026-06-23", "2026-10-01", 60, "2027-06-30"
MIN_ROWS = 24
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
            flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0, target_R=5.5,
            be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
LEGS = {"ORB_R6 (#314, gated)": dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75,
                                      vpace_filter=0.8),
        "ORB_257 (reported only)": dict(BASE, stop_frac=2.5, breakout_buf=0.30, atr_filter=0.5)}


def main(describe=False):
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays
    from paired_seq_stop import tstat, FIRST, EVERY, BOUND, BOUND_EX

    def seq_stop(u, m):
        # House paired stop (docs/PREREG_paired_sequential_stop_2026-09-29.md) with this test's own c:
        # at every look c is the mean arm size over the trades read SO FAR (outcome-blind), as the
        # pre-registration says - not one c from the whole sample (fixed 2026-09-30, before any forward trade).
        u, m = np.asarray(u, float), np.asarray(m, float)
        last = ("continue", len(u), 0.0)
        for n in range(FIRST, len(u) + 1, EVERY):
            x = (m[:n] - m[:n].mean()) * u[:n]
            t = tstat(x)
            if t >= BOUND and tstat(np.delete(x, int(np.argmax(x)))) >= BOUND_EX:
                return "EARLY PASS - read the final rule now", n, t
            if t <= -BOUND and tstat(np.delete(x, int(np.argmin(x)))) <= -BOUND_EX:
                return "EARLY FAIL", n, t
            last = ("continue", n, t)
        return last

    tk = pd.read_csv(TICKS, usecols=["time", "delta"])
    tk["bar"] = ((tk.time - 1) // 300) * 300                 # rows are stamped at the bar END
    agg = tk.groupby("bar").agg(f1=("delta", "sum"), nz=("delta", lambda s: int((s != 0).sum())))
    es = pd.read_csv(ES_TICKS, usecols=["time", "delta"])
    es["bar"] = ((es.time - 1) // 300) * 300
    es_agg = es.groupby("bar").agg(f4=("delta", "sum"), nz=("delta", lambda s: int((s != 0).sum())))

    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2025-06-01", date_to=None)
    idx = pd.DatetimeIndex(A["index"])
    unix = (idx.tz_convert("UTC").asi8 // 10**9)
    o5, c5 = np.asarray(A["open"], float), np.asarray(A["close"], float)
    # F3's split point: the median over the capture period of |F1| / |close-open|, from the feature alone
    cap = [(k, int(unix[k])) for k in range(len(idx))
           if pd.Timestamp(CAPTURE_FROM, tz=idx.tz) <= idx[k] < pd.Timestamp(FORWARD_FROM, tz=idx.tz)]
    f3_cap = [abs(agg.f1.get(b, 0)) / max(abs(c5[k] - o5[k]), 0.25) for k, b in cap
              if int(agg.nz.get(b, 0)) >= MIN_ROWS and agg.f1.get(b, 0) != 0]
    F3_MEDIAN = float(np.median(f3_cap)) if f3_cap else float("nan")
    lo, hi = (CAPTURE_FROM, FORWARD_FROM) if describe else (FORWARD_FROM, "2100-01-01")
    print("%s window %s .. %s | 5m master to %s | 10s capture to %s"
          % ("DESCRIPTIVE capture" if describe else "FORWARD", lo, hi, idx.max(),
             pd.to_datetime(tk.time.max(), unit="s", utc=True).tz_convert("US/Eastern")))

    for leg, params in LEGS.items():
        r = run_backtest(FN, arrays=A, params=params, cost_pts=COST, return_trades=True)
        rows = []
        for (ei, xi, pnl, side, entry) in r["trades"]:
            t = idx[ei]
            if not (pd.Timestamp(lo, tz=t.tz) <= t < pd.Timestamp(hi, tz=t.tz)):
                continue
            b = int(unix[ei])
            f1, nz = (agg.f1.get(b, 0), int(agg.nz.get(b, 0)))
            orb = [int(unix[k]) for k in range(ei, -1, -1) if idx[k].normalize() == t.normalize()][-2:]
            f2 = sum(agg.f1.get(x, 0) for x in orb)
            valid = nz >= MIN_ROWS and f1 != 0
            m = (1.5 if np.sign(f1) == side else 0.5) if valid else 1.0
            f3 = abs(f1) / max(abs(c5[ei] - o5[ei]), 0.25) if valid else np.nan
            f4, nz4 = (es_agg.f4.get(b, 0), int(es_agg.nz.get(b, 0)))
            f4_with = (np.sign(f4) == side) if (nz4 >= MIN_ROWS and f4 != 0) else np.nan
            rows.append(dict(t=t, day=t.tz_localize(None).normalize(), side=side, u=pnl * MULT, f1=f1, nz=nz,
                             valid=valid, m=m, f2_with=(np.sign(f2) == side) if f2 != 0 else np.nan,
                             f3=f3, f4_with=f4_with))
        T = pd.DataFrame(rows)
        print("\n== %s: %d trades in window, %d with valid breakout-bar delta" % (leg, len(T), int(T.valid.sum()) if len(T) else 0))
        if not len(T) or not T.valid.any():
            continue
        V = T[T.valid]
        w, a = V[V.m > 1], V[V.m < 1]
        print("  delta WITH the trade:    %3d trades, mean $%+8.1f, total $%+9.0f" % (len(w), w.u.mean() if len(w) else 0, w.u.sum()))
        print("  delta AGAINST the trade: %3d trades, mean $%+8.1f, total $%+9.0f" % (len(a), a.u.mean() if len(a) else 0, a.u.sum()))
        f2v = V.dropna(subset=["f2_with"])
        print("  secondary F2 (opening-range delta with the trade): %d with $%+.0f | %d against $%+.0f"
              % (int((f2v.f2_with == True).sum()), f2v[f2v.f2_with == True].u.sum(),
                 int((f2v.f2_with == False).sum()), f2v[f2v.f2_with == False].u.sum()))
        hi3, lo3 = V[V.f3 > F3_MEDIAN], V[V.f3 <= F3_MEDIAN]
        print("  REPORTED ONLY F3 absorption (split at capture median %.1f): high %d trades mean $%+.1f | low %d mean $%+.1f"
              % (F3_MEDIAN, len(hi3), hi3.u.mean() if len(hi3) else 0, len(lo3), lo3.u.mean() if len(lo3) else 0))
        v4 = V.dropna(subset=["f4_with"])
        w4, a4 = v4[v4.f4_with == True], v4[v4.f4_with == False]
        print("  REPORTED ONLY F4 ES delta: with %d trades mean $%+.1f | against %d mean $%+.1f | no ES delta %d"
              % (len(w4), w4.u.mean() if len(w4) else 0, len(a4), a4.u.mean() if len(a4) else 0, len(V) - len(v4)))
        c = float(V.m.mean())
        d = (V.m - c) * V.u
        arm, twin = (T.m * T.u), T.u
        print("  arm %+.0f vs twin %+.0f | paired d mean %+.1f, t %.2f (c = running mean size %.3f)"
              % (arm.sum(), twin.sum(), d.mean(), tstat(d), c))
        if describe:
            print("  (DESCRIPTIVE ONLY - the capture period can neither pass nor fail the test)")
            continue
        status, n, t = seq_stop(V.u.values, V.m.values)
        print("  PAIRED SEQUENTIAL STOP: %s at %d valid trades (t %.2f)" % (status, n, t))
        if "ORB_R6" in leg and (len(V) >= FINAL_N or pd.Timestamp.now() >= pd.Timestamp(FINAL_DATE)):
            def roc30(pnl):
                s = pd.Series(pnl.values, index=T.day).groupby(level=0).sum().sort_index()
                cum = s.cumsum(); dd = float((cum.cummax().clip(lower=0) - cum).max())
                yrs = max((s.index.max() - s.index.min()).days / 365.25, 1 / 12)
                neg = s[s < 0]
                return 30 * (s.sum() / yrs) / dd if dd > 0 else np.inf, s.mean() / np.sqrt((neg ** 2).sum() / len(s))
            (ra, sa), (rt, st) = roc30(arm), roc30(twin)
            gain = (arm - twin)
            rules = [tstat(d) >= 1.645 and d.mean() > 0, ra > rt, sa >= st, gain.sum() - gain.max() > 0]
            print("  FINAL RULE: %s  (t-test %s, ROC@$30k %.1f vs %.1f, Sortino %.2f vs %.2f, ex-top gain $%+.0f)"
                  % ("PASS" if all(rules) else "FAIL", rules[0], ra, rt, sa, st, gain.sum() - gain.max()))


if __name__ == "__main__":
    main(describe="--describe" in sys.argv)

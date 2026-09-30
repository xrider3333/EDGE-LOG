"""Order-flow round 1 (2026-09-30, owner ask via MANAGER inbox #29) - docs/PREREG_orderflow_r1_2026-09-30.md.

NEW INFORMATION: the NinjaTrader 10-second NQ/ES bars carry buy / sell volume and delta since late June 2026
(C:\\EdgeLog\\ohlc\\<SYM>_10s.csv, times = bar OPEN in UTC seconds). Too short to adopt anything; the rule below
is fixed now and scored FORWARD with the paired early stop (tools/paired_seq_stop.py).

FEATURE (read at the SIGNAL bar, never the fill): for a trade entering at 5m bar E (bar-open label = fill time),
window W = the 10s bars that CLOSE by E, starting max(09:30 ET, E - 30 min). Valid when W spans >= 5 min, holds
>= 90% of its 10s bars, and >= 80% of those carry buy+sell volume. Imbalance = sum(delta) / sum(buy + sell).
Aligned = side x imbalance.
SIZE RULE: aligned >= theta(L) -> 1.5x; aligned <= -theta(L) -> 0.5x; otherwise, or window not valid -> 1.0x.
theta(L) = median |imbalance| over every valid RTH window of the same length L (5..30 min, 5-min steps) ending on
a 5-minute mark, on capture sessions before 2026-10-01 - a property of the feature alone, no trade outcome read.

    python tools/orderflow_r1.py theta          freeze theta(L) (prints the table the prereg carries)
    python tools/orderflow_r1.py triage         backfill read on the captured sessions (informational)
Run from the shared checkout (needs the master registry) or set EDGELOG_ROOT to it.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

OHLC = r"C:\EdgeLog\ohlc"
LOOK_MIN, MIN_SPAN_MIN, BAR_COVER, DELTA_COVER = 30, 5, 0.90, 0.80
UP, DOWN = 1.5, 0.5
CUTOFF = pd.Timestamp("2026-10-01")
# Frozen 2026-09-30 by `theta` (NQ, window minutes -> median |imbalance|, 06-23..09-30 capture).
THETA = {5: 0.0331, 10: 0.0242, 15: 0.0206, 20: 0.0185, 25: 0.0174, 30: 0.0157}


def load_10s(sym):
    d = pd.read_csv(os.path.join(OHLC, f"{sym}_10s.csv")).drop_duplicates("time").sort_values("time")
    t = pd.to_datetime(d.time.to_numpy(), unit="s", utc=True).tz_convert("US/Eastern").tz_localize(None)
    return pd.DataFrame({"t": t, "delta": d.delta.to_numpy(float),
                         "flow": (d.buy_vol + d.sell_vol).to_numpy(float)}).set_index("t")


def window(of, entry):
    """(imbalance, minutes) for the 10s bars closing by `entry` (naive ET); imbalance NaN when not valid."""
    entry = pd.Timestamp(entry)
    start = max(entry.normalize() + pd.Timedelta(hours=9, minutes=30), entry - pd.Timedelta(minutes=LOOK_MIN))
    mins = (entry - start).total_seconds() / 60.0
    if mins < MIN_SPAN_MIN:
        return float("nan"), mins
    w = of.loc[start: entry - pd.Timedelta(seconds=10)]
    if len(w) < BAR_COVER * mins * 6:
        return float("nan"), mins
    has = w.flow > 0
    if has.mean() < DELTA_COVER:
        return float("nan"), mins
    return float(w.delta[has].sum() / w.flow[has].sum()), mins


def theta_key(mins):
    return int(min(LOOK_MIN, max(MIN_SPAN_MIN, 5 * round(mins / 5))))


def sizes(of, entries, sides, theta):
    m, a = np.ones(len(entries)), np.full(len(entries), np.nan)
    for i, (e, s) in enumerate(zip(entries, sides)):
        imb, mins = window(of, e)
        if np.isfinite(imb):
            a[i] = s * imb
            th = theta[theta_key(mins)]
            m[i] = UP if a[i] >= th else (DOWN if a[i] <= -th else 1.0)
    return m, a


def freeze_theta(sym="NQ"):
    of = load_10s(sym)
    of = of[of.index < CUTOFF]
    out = {}
    for L in range(5, 31, 5):
        vals = []
        for day in sorted(set(of.index.normalize())):
            if day.weekday() >= 5:
                continue
            open_ = day + pd.Timedelta(hours=9, minutes=30)
            for k in range(L // 5, 79):                      # window ends 09:30 + L .. 16:00 on 5-min marks
                e = open_ + pd.Timedelta(minutes=5 * k)
                if (e - open_).total_seconds() / 60 < L:
                    continue
                s = e - pd.Timedelta(minutes=L)
                w = of.loc[s: e - pd.Timedelta(seconds=10)]
                if len(w) < BAR_COVER * L * 6:
                    continue
                has = w.flow > 0
                if has.mean() < DELTA_COVER:
                    continue
                vals.append(abs(w.delta[has].sum() / w.flow[has].sum()))
        out[L] = round(float(np.median(vals)), 4)
        print(f"  L {L:2d} min: median |imbalance| {out[L]:.4f} over {len(vals):,} windows", flush=True)
    print("THETA =", out)
    return out


def leg_trades(name):
    """Crown / book-leg trades on the refreshed NQ 5m RTH no-adjust master: (entry ET, side, $ P&L)."""
    import keel_bag_check as B
    import keel_422_stack_check as S
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07")
    if name == "ORB314":
        fn, params = "ORB_3_6_R6.py", {'skip_holidays': True, 'breakout_buf': 0.25, 'vpace_filter': 0.8,
                                       'close_confirm': True, 'flat_eod': True, 'or_bars': 2, 'be_after_R': 0.5,
                                       'stop_frac': 2.5, 'trail_bars': 0, 'target_R': 5.0, 'partial_exit_R': 0.0,
                                       'trade_mode': 'First-candle dir', 'atr_filter': 0.75}
    else:
        fn, params = "NOISE_1_8_CT304H.py", S.P422
    r = run_backtest(B.mod(fn), arrays=A, params=params, cost_pts=B.COST, return_trades=True)
    T = sorted(r["trades"], key=lambda z: z[0])
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    ent = idx[[int(t[0]) for t in T]]
    side = np.array([1.0 if float(t[3]) > 0 else -1.0 for t in T])
    return ent, side, np.array([float(t[2]) for t in T]) * B.MULT


LEGS = {"ORB314": ("ORB314_raw", 120), "NOISE422": ("NOISE422_raw", 150)}
C, BOUND = {"ORB314": 1.1552, "NOISE422": 1.0968}, {"ORB314": 3.00, "NOISE422": 3.00}   # frozen 09-30 by `constants`


def backfill(name):
    of = load_10s("NQ")
    ent, side, pnl = leg_trades(name)
    keep = (ent >= of.index.min()) & (ent < CUTOFF)
    m, a = sizes(of, ent[keep], side[keep], THETA)
    return ent[keep], side[keep], pnl[keep], m, a


def constants(reps=4000, seed=20260930):
    """c = mean size over backfill trades with a valid window (reads the FEATURE, never the outcome);
    B = smallest of 3.0, 3.25, ... whose false-stop rate is <= 5% when sizes are drawn from those backfill
    sizes INDEPENDENTLY of outcomes drawn from the leg's walk-forward trades (the no-aim null)."""
    import paired_seq_stop as Q
    for name, (twin, nmax) in LEGS.items():
        ent, side, pnl, m, a = backfill(name)
        v = np.isfinite(a)
        c = float(m[v].mean())
        wf = pd.read_csv(os.path.join(Q.LEGS, twin + "_trades.csv"))
        u = wf.pnl_usd[wf.stage == "WF"].to_numpy(float)
        rng = np.random.default_rng(seed)
        for b in np.arange(3.0, 8.01, 0.25):
            stops = 0
            for _ in range(reps):
                d = (rng.choice(m[v], nmax) - c) * rng.choice(u, nmax)
                stops += Q.read_pair(d, np.ones(nmax), np.zeros(nmax), 0.0, b)[0] != "continue"
            if stops / reps <= 0.05:
                break
        print(f"{name}: backfill trades {len(m)}, valid window {int(v.sum())} "
              f"(1.5x {int((m[v] == UP).sum())}, 0.5x {int((m[v] == DOWN).sum())}), c = {c:.4f}, "
              f"B = {b:.2f} (false stops {100 * stops / reps:.1f}% over {nmax})", flush=True)


def triage():
    """Backfill KILL check (pre-registered): paired t <= -2.0 on a leg = its shadow is not started."""
    import paired_seq_stop as Q
    for name in LEGS:
        ent, side, pnl, m, a = backfill(name)
        v = np.isfinite(a)
        d = (m[v] - C[name]) * pnl[v]
        t = Q.tstat(d)
        up, dn, flat = m == UP, m == DOWN, v & (m == 1.0)
        print(f"{name}: valid {int(v.sum())} of {len(m)}; paired t {t:+.2f} -> "
              f"{'KILLED' if t <= -2.0 else 'start forward shadow'}; raw $ on 1.5x trades {pnl[up].sum():,.0f} "
              f"(n {int(up.sum())}), 0.5x {pnl[dn].sum():,.0f} (n {int(dn.sum())}), untilted valid "
              f"{pnl[flat].sum():,.0f} (n {int(flat.sum())}), no data {pnl[~v].sum():,.0f} (n {int((~v).sum())})")


def forward(since="2026-10-01"):
    """Forward read: trades entered on/after `since` with the paired early stop and the running final numbers."""
    import paired_seq_stop as Q
    of = load_10s("NQ")
    for name, (_, nmax) in LEGS.items():
        ent, side, pnl = leg_trades(name)
        k = (ent >= pd.Timestamp(since)) & (ent <= of.index.max())
        m, a = sizes(of, ent[k], side[k], THETA)
        v = np.isfinite(a)
        st = Q.read_pair(pnl[k][v], m[v], np.ones(int(v.sum())), C[name], BOUND[name])
        print(f"{name}: forward trades {int(k.sum())} (valid window {int(v.sum())}), raw ${pnl[k].sum():,.0f}, "
              f"sized ${(pnl[k] * m).sum():,.0f}; early stop: {st[0]} at n {st[1]}, t {st[2]:+.2f}")


if __name__ == "__main__":
    if sys.argv[1:] == ["triage"]:
        triage()
    elif sys.argv[1:] == ["forward"]:
        forward()
    elif sys.argv[1:] == ["theta"]:
        freeze_theta()
    elif sys.argv[1:] == ["constants"]:
        constants()

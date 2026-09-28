"""Fixed-rule sizing round 1 (2026-09-28, MANAGER inbox #24) - docs/PREREG_fixed_sizing_r1_2026-09-28.md.

Test A: ORB #314 with ORB.md's July execution-layer sizing (causal risk parity, time-of-day tilt, both).
Test B: TTM #458 - which part of KEEL v12 carries its walk-forward win (raw, NOISE fixed package, FOMC-only, KEEL).
Every arm is judged against its raw twin on the owner yardstick: ROC %/yr at a $30k worst drawdown (daily),
Sortino, trade minimums, lockbox without its biggest trade, and a permutation null on the arm's own sizes.

    python tools/fixed_sizing_r1.py          (~3 min; run from the shared checkout, reads the masters)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine import sizing                                       # noqa: E402
from augur_engine.analytics import sortino_from_pnls                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

LEGS = r"C:\EdgeLog\book_legs"
ORB = dict(file="ORB_3_6_R6.py", date_from="2010-06-07", date_to="2026-08-13", cost=0.533, mult=20.0,
           params={'skip_holidays': True, 'breakout_buf': 0.25, 'vpace_filter': 0.8, 'close_confirm': True,
                   'flat_eod': True, 'or_bars': 2, 'be_after_R': 0.5, 'stop_frac': 2.5, 'trail_bars': 0,
                   'target_R': 5.0, 'partial_exit_R': 0.0, 'trade_mode': 'First-candle dir', 'atr_filter': 0.75})
ORB_WF0, ORB_LB0, ORB_END = pd.Timestamp("2016-07-13"), pd.Timestamp("2025-08-13"), pd.Timestamp("2026-08-13")
EVENT = dict(K.CFG["v12"]["event"])
DOW = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
CAP = float(K.CFG["v12"]["comp"]["cap"])
NPERM, SEED, PCT = 500, 20260928, 100 * (1 - 0.05 / 3)


def naive(ix):
    ix = pd.DatetimeIndex(ix)
    return ix.tz_convert("US/Eastern").tz_localize(None) if ix.tz is not None else ix


def yard(days, pnl, a, b):
    """ROC %/yr at a $30k worst daily drawdown, Sortino, trades, net without the biggest trade."""
    m = (days >= a) & (days < b)
    q = pnl[m]
    yrs = (b - a).days / 365.25
    daily = pd.Series(q).groupby(days[m].normalize()).sum().to_numpy()
    cum = np.cumsum(daily)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()) if len(cum) else 0.0
    roc = 30.0 * (q.sum() / yrs) / dd if dd > 0 else float("nan")
    return dict(n=int(m.sum()), net=float(q.sum()), dd=dd, roc=roc,
                sortino=float(sortino_from_pnls(list(q), yrs) or 0.0),
                ex_top=float(q.sum() - q.max()) if len(q) else 0.0)


def judge(name, days, P, sizes, wf, lb, rng):
    raw = {st: yard(days, P, *ab) for st, ab in (("WF", wf), ("LB", lb))}
    out = [f"\n{name}"]
    out.append(f"  {'arm':6s} | WF ROC  Sortino  n   | LB ROC  Sortino  n  LB ex-top  | perm pct | verdict")
    for arm, k in sizes.items():
        r = {st: yard(days, P * k, *ab) for st, ab in (("WF", wf), ("LB", lb))}
        if arm == "R":
            pct, verdict = float("nan"), "twin"
        else:
            null = [yard(days, P * rng.permutation(k), *wf)["roc"] for _ in range(NPERM)]
            pct = 100.0 * float(np.mean(np.array(null) < r["WF"]["roc"]))
            fails = []
            for st in ("WF", "LB"):
                if not r[st]["roc"] > raw[st]["roc"]:
                    fails.append(f"{st} ROC")
                if not r[st]["sortino"] > raw[st]["sortino"]:
                    fails.append(f"{st} Sortino")
            if r["WF"]["n"] < 100 or r["LB"]["n"] < 50:
                fails.append("trade minimum")
            if r["LB"]["ex_top"] <= 0:
                fails.append("LB ex-top")
            if pct < PCT:
                fails.append("perm")
            verdict = "PASS" if not fails else "fail: " + ", ".join(fails)
        out.append(f"  {arm:6s} | {r['WF']['roc']:6.1f} {r['WF']['sortino']:7.2f} {r['WF']['n']:4d} | "
                   f"{r['LB']['roc']:6.1f} {r['LB']['sortino']:7.2f} {r['LB']['n']:3d} {r['LB']['ex_top']:>10,.0f} | "
                   f"{pct:7.1f} | {verdict}")
    print("\n".join(out), flush=True)


def causal_rp(risk, look=100, min_n=20, cap=3.0):
    f = np.ones(len(risk))
    for i in range(len(risk)):
        prev = risk[max(0, i - look):i]
        if len(prev) >= min_n:
            f[i] = min(float(np.median(prev)) / risk[i], cap)
    return f


def test_a(rng):
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"),
                           date_from=ORB["date_from"], date_to=ORB["date_to"])
    r = run_backtest(ORB["file"], arrays=A, params=ORB["params"], cost_pts=ORB["cost"], return_trades=True)
    T = sorted(r["trades"], key=lambda t: t[0])
    _, risk, ebar, _ = sizing.trade_features(T, A, ORB["params"]["stop_frac"], ORB["params"]["or_bars"])
    P = np.array([float(t[2]) for t in T]) * ORB["mult"]
    ref = pd.read_csv(os.path.join(LEGS, "ORB314_raw_trades.csv"))
    assert len(ref) == len(T) and abs(ref.pnl_usd.sum() - P.sum()) < 1.0, "ORB #314 trades do not reproduce"
    days = naive(pd.DatetimeIndex(A["index"])[[int(t[0]) for t in T]])
    rp = causal_rp(risk)
    tt = sizing.time_weight(ebar)
    sizes = {"R": np.ones(len(T)), "RP": rp, "TT": tt, "RPTT": np.minimum(rp * tt, 3.0)}
    judge(f"TEST A  ORB #314  ({len(T)} trades; WF {ORB_WF0.date()}..{ORB_LB0.date()} | LB ..{ORB_END.date()})",
          days, P, sizes, (ORB_WF0, ORB_LB0), (ORB_LB0, ORB_END + pd.Timedelta(days=1)), rng)


def test_b(rng):
    raw = pd.read_csv(os.path.join(LEGS, "TTM458_raw_trades.csv"))
    kl = pd.read_csv(os.path.join(LEGS, "TTM458_keel_trades.csv"))
    assert (raw.entry_time == kl.entry_time).all()
    A = load_master_arrays(find_master("ES", "30m", "rth", "db_noadj_rth"), date_from="2010-06-07")
    idx = pd.DatetimeIndex(A["index"])
    ent = pd.DatetimeIndex(pd.to_datetime(raw.entry_time, utc=True)).tz_convert(idx.tz) if idx.tz is not None \
        else naive(pd.to_datetime(raw.entry_time, utc=True))
    E = idx.get_indexer(ent)
    assert (E >= 0).all(), "TTM entries not found on the ES 30m master"
    T = [(int(e), int(e), float(p)) for e, p in zip(E, raw.pnl_usd)]
    P = raw.pnl_usd.to_numpy(float)
    days = naive(ent)
    wf = (days[(raw.stage == "WF").to_numpy()].min().normalize(), days[(raw.stage == "LB").to_numpy()].min().normalize())
    lb = (wf[1], days.max() + pd.Timedelta(days=1))
    sizes = {"R": np.ones(len(P)),
             "FX": K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=CAP, event=EVENT),
             "EV": K.compression_sizes(A, T, mult=1.0, event=EVENT),
             "K": (kl.pnl_usd / raw.pnl_usd.replace(0, np.nan)).fillna(1.0).to_numpy(float)}
    judge(f"TEST B  TTM #458  ({len(P)} trades; WF {wf[0].date()}..{wf[1].date()} | LB ..{lb[1].date()})",
          days, P, sizes, wf, lb, rng)
    print(f"  FOMC half-size fires on {(sizes['EV'] < 1).sum()} trades; compression on {(sizes['FX'] >= 1.5).sum()}")


if __name__ == "__main__":
    g = np.random.default_rng(SEED)
    test_a(g)
    test_b(g)

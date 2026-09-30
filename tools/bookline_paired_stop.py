"""Paired early-stop constants for the three forward BOOK-LINE shadows (Frontier lane; Custom ML research chat).

Each shadow line is BOOK #463 with one leg swapped, run on the same days as the adopted book:
    orb314  Q1a  ORB #314 (ORB_3_6_R6.py) in the ORB seat          (q1_cands.json, "Q1a ...")
    q4      Q4   ORB #314 + ENGU-Q gate S1 (ENGUQ_..._R62_...)       (q4_cands.json, single entry)
    orb239  Q6   ORB #239, breakeven 0.8 (ORB_3_6_BE08.py)           (q6_cands.json, single entry)
Legs/JSON live in C:\\EdgeLog\\_anatomy_cache\\bookq\\ ; the daily series are built exactly as that folder's
book_q.py builds them (book._leg_trades, closed-trade series C = _daily(trades), valued series M = _daily(_mtm_day)),
but with #463's legs taken from api.book_shadow.BOOK463_LEGS instead of Firestore.

THE STOP (per candidate vs #463), on DAILY closed-trade P&L C (the forward report books each trade on one day):
    sigma_b, sigma_s  = sample std (ddof=1) of #463's / the candidate's C over every WEEKDAY of the WF stretch
                        2016-07-01..2025-06-29 (union of both books' days, zeros included). Weekend days that
                        UTC day-stamping creates are dropped (2026-09-30 review): the forward report has one
                        row per trading day, and the 15 weekend days carrying P&L are folded into Friday.
    d_day             = s_day / sigma_s - b_day / sigma_b      (risk-normalised: better return per unit of risk,
                                                                not more size)
    looks             = report day 20, 30, 40, ... (tools/paired_seq_stop.read_pair's schedule, NMAX = 252 so the
                        last look is day 250); t = mean(d) / (sd(d) / sqrt(n)).
    EARLY PASS        t >= B and t still >= 2.0 without the single largest d
    EARLY FAIL        t <= -B and t still <= -2.0 without the single most negative d
    B                 smallest of 3.00, 3.25, ... 8.00 whose false-stop rate (either side) is <= 5% when the WF d
                        series, mean removed, is re-drawn iid with replacement 252 days at a time, 4000 draws,
                        numpy default_rng(20260930).

    python tools/bookline_paired_stop.py        rebuild the series, print the constants table + sanity checks
    from tools.bookline_paired_stop import read_forward   score forward daily series with the frozen constants

Run it from the SHARED checkout's engine (a worktree has no master registry, so find_master would return None):
this file puts EDGELOG_ROOT (default the shared checkout) first on sys.path and chdirs there.
Set AUGUR_TRIAL_CACHE=1 OMP_NUM_THREADS=1 for speed (defaults are set below if unset). Nothing here touches the
runner, Firestore, NinjaTrader or any live file.
"""
import importlib.util
import json
import os
import sys

ROOT = os.environ.setdefault("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
if sys.path[0] != ROOT:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "paired_seq_stop", os.path.join(os.path.dirname(os.path.abspath(__file__)), "paired_seq_stop.py"))
_pss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pss)
tstat, read_pair = _pss.tstat, _pss.read_pair


def false_stop(dnull, nmax, bound, reps, seed):
    """Equal-risk-adjusted-return null: the WF daily differences with their mean removed, drawn iid."""
    rng = np.random.default_rng(seed)
    one, zero = np.ones(nmax), np.zeros(nmax)
    return float(np.mean([read_pair(rng.choice(dnull, nmax), one, zero, 0.0, bound)[0] != "continue"
                          for _ in range(reps)]))

BOOKQ = r"C:\EdgeLog\_anatomy_cache\bookq"
W0, W1 = "2010-06-07", "2026-06-30"                       # the window book_q.py runs every leg over
WF0, WF1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")   # walk-forward stretch, inclusive
NMAX, REPS, SEED = 252, 4000, 20260930
B_GRID = np.arange(3.0, 8.01, 0.25)
# (name, candidates file, results file, key picker)
CANDS = (("orb314", "q1", lambda k: k.startswith("Q1a")),
         ("q4", "q4", lambda k: True),
         ("orb239", "q6", lambda k: True))

# Frozen by the first run of this file (2026-09-30) from the WF stretch; never re-derived.
FROZEN = {"orb314": {"sigma_b": 3910.94, "sigma_s": 3868.12, "B": 3.0},   # frozen 2026-09-30 (weekday fold)
          "q4": {"sigma_b": 3910.94, "sigma_s": 3751.85, "B": 3.0},
          "orb239": {"sigma_b": 3910.94, "sigma_s": 3899.75, "B": 3.0}}


def _sum_day(pairs):
    from augur_engine import book
    d, v = book._daily(pairs)
    return pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum() if len(d) else pd.Series(dtype=float)


_LEG_CACHE = {}


def leg_series(leg):
    """(closed-trade daily C, valued daily M) for ONE leg over W0..W1, exactly as book_q.py's leg()."""
    from augur_engine import book
    k = json.dumps(leg, sort_keys=True, default=str)
    if k not in _LEG_CACHE:
        tr, inf = book._leg_trades(dict(leg), W0, W1)
        m = inf.pop("_mtm_day", None) or tr
        _LEG_CACHE[k] = (_sum_day(tr), _sum_day(m))
    return _LEG_CACHE[k]


def book_series(legs):
    """(C, M) of a book: legs summed over the union of business days, zeros filled (book_q.py's score())."""
    days = pd.bdate_range(W0, W1)
    cs, ms = [], []
    for leg in legs:
        c, m = leg_series(leg)
        days = days.union(c.index).union(m.index)
        cs.append(c)
        ms.append(m)
    return sum(s.reindex(days).fillna(0.0) for s in cs), sum(s.reindex(days).fillna(0.0) for s in ms)


def _dd(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(x) else 0.0


def _so(x):
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def wf_stats(C, M):
    """WF net, ROC@$30k (book_q.py: net / yrs / 1000 * 30000 / daily-valued DD) and Sortino on M."""
    yrs = ((WF1 - WF0).days + 1) / 365.25
    net = float(C[(C.index >= WF0) & (C.index <= WF1)].sum())
    mm = M[(M.index >= WF0) & (M.index <= WF1)].values
    dd = _dd(mm)
    return {"net": net, "dd": dd, "roc30": net / yrs / 1000 * 30000 / dd, "sortino": _so(mm)}


def daily_d(b_day, s_day, sigma_b, sigma_s):
    """Risk-normalised paired difference on aligned daily P&L vectors."""
    return np.asarray(s_day, float) / sigma_s - np.asarray(b_day, float) / sigma_b


def read_forward(b_day, s_day, cand):
    """Score forward daily closed-P&L series (same day index, #463 vs candidate) with the frozen constants.
    Returns (status, n, t) from the last look, as paired_seq_stop.read_pair."""
    f = FROZEN[cand]
    d = daily_d(b_day, s_day, f["sigma_b"], f["sigma_s"])
    n = len(d)
    return read_pair(d, np.ones(n), np.zeros(n), 0.0, f["B"])


def calibrate(dwf, reps=REPS, seed=SEED, nmax=NMAX):
    """Smallest boundary on B_GRID whose false-stop rate is <= 5% under the mean-removed WF null.
    Returns (B, false_stop_rate); B is nan (rate at the top of the grid) if none qualifies."""
    dnull = dwf - dwf.mean()
    fs = None
    for b in B_GRID:
        fs = false_stop(dnull, nmax, float(b), reps, seed)
        if fs <= 0.05:
            return float(b), fs
    return float("nan"), fs


def main():
    from api.book_shadow import BOOK463_LEGS
    Cb, Mb = book_series(BOOK463_LEGS)
    sb = wf_stats(Cb, Mb)
    print(f"#463 (BOOK463_LEGS) WF: net ${sb['net']:,.0f}  DD(daily valued) ${sb['dd']:,.0f}  "
          f"ROC@$30k {sb['roc30']:.2f}  Sortino {sb['sortino']:.3f}", flush=True)
    rows, frozen, mism = [], {}, []
    for name, q, pick in CANDS:
        cands = json.load(open(os.path.join(BOOKQ, q + "_cands.json"), encoding="utf-8"))
        key = [k for k in cands if pick(k)]
        assert len(key) == 1, (q, list(cands))
        key = key[0]
        res = json.load(open(os.path.join(BOOKQ, q + "_results.json"), encoding="utf-8"))["results"]
        Cs, Ms = book_series(cands[key])
        ss = wf_stats(Cs, Ms)
        days = Cb.index.union(Cs.index)
        days = days[(days >= WF0) & (days <= WF1)]
        fri = lambda x: x.groupby(x.index - pd.to_timedelta(np.maximum(x.index.dayofweek - 4, 0), unit="D")).sum()
        b = fri(Cb.reindex(days).fillna(0.0))
        s = fri(Cs.reindex(days).fillna(0.0))
        b, s = b.values, s.reindex(b.index).fillna(0.0).values
        sigma_b, sigma_s = float(b.std(ddof=1)), float(s.std(ddof=1))
        d = daily_d(b, s, sigma_b, sigma_s)
        B, fs = calibrate(d)
        rows.append((name, key, sigma_b, sigma_s, B, fs, float(d.mean()), tstat(d), int((d != 0).sum()), len(d)))
        frozen[name] = {"sigma_b": round(sigma_b, 2), "sigma_s": round(sigma_s, 2), "B": B}
        for lab, mine, theirs in (("#463 ROC30", sb["roc30"], res["#463"]["wf"]["roc30"]),
                                  ("#463 Sortino", sb["sortino"], res["#463"]["wf"]["sortino"]),
                                  (name + " ROC30", ss["roc30"], res[key]["wf"]["roc30"]),
                                  (name + " Sortino", ss["sortino"], res[key]["wf"]["sortino"])):
            dev = 100 * (mine / theirs - 1)
            mism.append((lab, mine, theirs, dev))
            print(f"  check {lab:16s} mine {mine:9.3f}  book_q {theirs:9.3f}  diff {dev:+.3f}%"
                  + ("   <-- MISMATCH > 1%" if abs(dev) > 1 else ""), flush=True)
    print()
    print(f"{'cand':7s} {'sigma_b':>9s} {'sigma_s':>9s} {'B':>6s} {'false-stop':>10s} {'mean d':>9s} {'WF t':>7s} "
          f"{'days d!=0':>10s} {'WF days':>8s}")
    for name, key, sb_, ss_, B, fs, md, t, nz, nd in rows:
        print(f"{name:7s} {sb_:9.2f} {ss_:9.2f} {B:6.2f} {100 * fs:9.1f}% {md:+9.5f} {t:+7.2f} {nz:10d} {nd:8d}")
    print("\nFROZEN =", json.dumps(frozen))
    bad = [m for m in mism if abs(m[3]) > 1]
    print("mismatches > 1%:", bad if bad else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())

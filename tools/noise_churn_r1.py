r"""NOISE CHURN r1 - MANAGER #278 (owner 11-04: 23 round trips, 22 one bar long). Prereg: manager/prereg/PREREG_noise_churn_r1_2026-11-04.md.

#382's crown run once on PRE-WF ONLY: the master is loaded to 2016-06-29 and no later, so the WF and the lockbox cannot be read.

    python tools/noise_churn_r1.py power   -> hold four numbers + minimum detectable lift (no cell is run)
    python tools/noise_churn_r1.py parity  -> churn file with knobs off vs NOISE_1_8_CT304.py, trade for trade
    python tools/noise_churn_r1.py grid    -> every cell at cost 0.533 / 0.783 / 1.033 -> C:\EdgeLog\_anatomy_cache\noise_churn\grid.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("EDGELOG_ENGINE_ROOT") or REPO)      # a worktree has no master registry: point this at the shared checkout
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.drawdowns import four_numbers                # noqa: E402
from augur_engine.engine import run_backtest                   # noqa: E402
from augur_engine.strategies import load_strategy              # noqa: E402

RUN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\run382.json"
OUT = r"C:\EdgeLog\_anatomy_cache\noise_churn"
PRE_END = "2016-06-29"
COSTS = (0.533, 0.783, 1.033)
CELLS = [("HOLD", {}), ("cap 1", dict(max_entries=1)), ("cap 2", dict(max_entries=2)), ("cap 3", dict(max_entries=3)),
         ("confirm", dict(reentry_confirm=True)), ("buf 0.10", dict(vwap_buf_k=0.1)), ("buf 0.25", dict(vwap_buf_k=0.25)),
         ("buf 0.50", dict(vwap_buf_k=0.5))]
BOOT, BLOCK = 2000, 20


def setup():
    d = json.load(open(RUN))
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    A = load_master_arrays(m, date_from=d["date_from"], date_to=PRE_END)
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    assert idx[-1] <= pd.Timestamp(PRE_END) + pd.Timedelta(days=1), "pre-WF master runs past the WF start"
    return d, A, idx, float(d.get("multiplier") or 20.0)


def strat(name):
    return load_strategy(os.path.join(REPO, "augur_strategies", name))


def trades(s, A, cell, cost, crown):
    r = run_backtest(s, arrays=A, params=dict(crown, **cell), cost_pts=cost, return_trades=True)
    return [(int(t[0]), int(t[1]), float(t[2])) for t in r["trades"]]


def daily_of(tr, idx, mult):
    sess = pd.Index(sorted(set(idx.normalize())))
    ent = pd.DatetimeIndex([idx[t[0]].normalize() for t in tr])
    return pd.Series([t[2] * mult for t in tr], index=ent).groupby(level=0).sum().reindex(sess, fill_value=0.0)


def four(daily):
    return four_numbers(daily, years=(daily.index[-1] - daily.index[0]).days / 365.25)


def block_se(x, seed=278):
    """Standard error of the mean daily value under a moving-block bootstrap (20 sessions)."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    n, k = len(x), int(np.ceil(len(x) / BLOCK))
    st = rng.integers(0, n - BLOCK + 1, size=(BOOT, k))
    means = np.array([np.concatenate([x[a:a + BLOCK] for a in row])[:n].mean() for row in st])
    return float(means.std())


def crown_of(d):
    c = d["validate"]["champion"]
    return dict(c)


def years(daily):
    return sorted(set(daily.index.year))


def power():
    d, A, idx, mult = setup()
    hold = trades(strat("NOISE_1_8_CT304.py"), A, {}, 0.533, crown_of(d))
    dl = daily_of(hold, idx, mult)
    yrs = (dl.index[-1] - dl.index[0]).days / 365.25
    se = block_se(dl.values) * 252
    fn = four(dl)
    print("HOLD pre-WF %s..%s  trades %d (%.0f/yr)  net $%.0f" % (dl.index[0].date(), dl.index[-1].date(), len(hold), len(hold) / yrs, dl.sum()))
    print("four:", {k: fn.get(k) for k in ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode")})
    print("$/yr %.0f  SE(level) $%.0f/yr  80%%-power MDE if a cell were unrelated to hold: $%.0f/yr" % (dl.sum() / yrs, se, 2.8 * se))
    print("paired corr 0.8 / 0.95 MDE: $%.0f / $%.0f per yr" % (2.8 * se * (2 * (1 - .8)) ** .5, 2.8 * se * (2 * (1 - .95)) ** .5))


def parity():
    d, A, idx, mult = setup()
    c = crown_of(d)
    a = trades(strat("NOISE_1_8_CT304.py"), A, {}, 0.533, c)
    b = trades(strat("NOISE_1_8_CT304_CHURN.py"), A, {}, 0.533, c)
    ok = len(a) == len(b) and all(x[0] == y[0] and x[1] == y[1] and abs(x[2] - y[2]) < 1e-9 for x, y in zip(a, b))
    print("PARITY %s: #382 %d trades %.3f pts, churn off %d trades %.3f pts" % ("PASS" if ok else "FAIL", len(a), sum(t[2] for t in a), len(b), sum(t[2] for t in b)))
    return ok


def grid():
    os.makedirs(OUT, exist_ok=True)
    assert parity()
    d, A, idx, mult = setup()
    c, s = crown_of(d), strat("NOISE_1_8_CT304_CHURN.py")
    rng = np.random.default_rng(278)
    out = {}
    for cost in COSTS:
        base = None
        for name, cell in CELLS:
            tr = trades(s, A, cell, cost, c)
            dl = daily_of(tr, idx, mult)
            if base is None:
                base = dl
            fn = four(dl)
            yrs_n = (dl.index[-1] - dl.index[0]).days / 365.25
            diff = (dl - base).values
            by = pd.Series(dl - base, index=dl.index).groupby(dl.index.year).sum()
            full = [y for y in by.index if 2011 <= y <= 2015]            # the five whole calendar years
            sub = []
            for y in full:
                a, b = dl[dl.index.year == y], base[base.index.year == y]
                fa, fb = four(a), four(b)
                sub.append(dict(y=int(y), delta=float(a.sum() - b.sum()), win=bool(fa["roc30"] > fb["roc30"] and fa["sortino"] > fb["sortino"])))
            se = block_se(diff) * 252 if name != "HOLD" else 0.0
            shares = [abs(x["delta"]) for x in sub]
            lead = float(diff.sum())
            top5 = float(np.sort(diff)[::-1][:5].sum()) if lead > 0 else float(np.sort(diff)[:5].sum())
            out["%s|%s" % (cost, name)] = dict(cost=cost, cell=name, trades=len(tr), trades_yr=len(tr) / yrs_n, fills_yr=2 * len(tr) / yrs_n,
                                               net=float(dl.sum()), usd_yr=float(dl.sum() / yrs_n), delta_yr=lead / yrs_n, se_yr=se, t=(lead / yrs_n / se if se else 0.0),
                                               roc30=fn["roc30"], dd5=fn["dd5_usd"], ddpct=fn["dd_pct_peak"], sortino=fn["sortino"], one_episode=fn.get("one_episode"),
                                               years_won=sum(x["win"] for x in sub), years_up=sum(x["delta"] > 0 for x in sub), sub=sub, top5_share=(top5 / lead if lead else 0.0))
            r = out["%s|%s" % (cost, name)]
            print("%.3f %-9s tr/yr %5.0f $/yr %7.0f d %+7.0f t %+5.2f ROC %6.1f DD5 %7.0f DD%% %5.1f Sort %5.2f yrs %d/5 up %d/5" % (
                cost, name, r["trades_yr"], r["usd_yr"], r["delta_yr"], r["t"], r["roc30"], r["dd5"], r["ddpct"], r["sortino"], r["years_won"], r["years_up"]), flush=True)
    json.dump(out, open(os.path.join(OUT, "grid.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    {"power": power, "parity": parity, "grid": grid}[sys.argv[1]]()

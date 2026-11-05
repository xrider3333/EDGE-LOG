r"""NOISE CHURN r2 - MANAGER #168 (owner GO 11-04). Prereg: C:\EdgeLog\manager\prereg\PREREG_noise_churn_r2_2026-11-04.md.

    python tools/noise_churn_r2.py parity  -> knobs off vs #382, trade for trade (pre-WF)
    python tools/noise_churn_r2.py pre     -> stage 1, cells A/B/C on pre-WF, picks BEST -> pre.json
    python tools/noise_churn_r2.py wf      -> stage 2, 8 folds: cap 1, cap 2, confirm, BEST vs HOLD -> wf.json
    python tools/noise_churn_r2.py lb      -> stage 3, lockbox veto read, only after wf.json exists

Every cost other than 0.533 re-costs the same trades per contract (size x difference); the tilt folds its own 0.533.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_churn_r1 as R1                                            # noqa: E402
from noise_churn_r1 import block_se, crown_of, four, setup, strat       # noqa: E402
from augur_engine.data import find_master, load_master_arrays           # noqa: E402
from augur_engine.engine import run_backtest                            # noqa: E402

OUT = os.path.join(R1.OUT, "r2")
FILE = "NOISE_1_8_CT304_CHURN.py"
COST = 0.533
FRICTION = 1.35
CELLS = {"A entry": dict(entry_vwap=True), "B2 closes": dict(exit_closes=2), "B3 closes": dict(exit_closes=3),
         "C2 A+B2": dict(entry_vwap=True, exit_closes=2), "C3 A+B3": dict(entry_vwap=True, exit_closes=3)}
R1CELLS = {"cap 1": dict(max_entries=1), "cap 2": dict(max_entries=2), "confirm": dict(reentry_confirm=True)}


def sized(s, A, params):
    """[(entry index, exit index, pts at 0.533, size)]."""
    r = run_backtest(s, arrays=A, params=params, cost_pts=COST, return_trades=True) or {}
    T = r.get("trades") or []
    S = r.get("trade_sizes")
    S = S if isinstance(S, (list, tuple)) and len(S) == len(T) else [1.0] * len(T)
    fc = r.get("size_cost_pts")
    if fc is not None and abs(float(fc) - COST) > 1e-9:
        raise SystemExit("file folds size cost %s, run costs %s" % (fc, COST))
    return [(int(t[0]), int(t[1]), float(t[2]), float(z)) for t, z in zip(T, S)]


def daily(dates, tr, sess, mult, cost=COST):
    v = [(t[2] - t[3] * (cost - COST)) * mult for t in tr]
    if not v:
        return pd.Series(0.0, index=sess)
    return pd.Series(v, index=pd.DatetimeIndex(dates)).groupby(level=0).sum().reindex(sess, fill_value=0.0)


def row(name, d, base, n, fills_base, yrs):
    f = four(d)
    diff = (d - base).to_numpy()
    lead = float(diff.sum())
    se = block_se(diff) * 252 if lead or diff.any() else 0.0
    top5 = float(np.sort(diff)[::-1][:5].sum()) if lead > 0 else float(np.sort(diff)[:5].sum())
    return dict(cell=name, trades=n, trades_yr=n / yrs, fills_yr_removed=(fills_base - 2 * n) / yrs, usd_yr=float(d.sum() / yrs),
                delta_yr=lead / yrs, se_yr=se, t=(lead / yrs / se) if se else 0.0, top5_share=(top5 / lead) if lead else 0.0,
                roc30=f["roc30"], dd5=f["dd5_usd"], ddpct=f["dd_pct_peak"], sortino=f["sortino"], one_episode=f.get("one_episode"))


def show(r, extra=""):
    print("%-10s tr/yr %4.0f fills/yr cut %4.0f $/yr %7.0f d %+7.0f t %+5.2f top5 %5.2f ROC %6.1f DD5 %6.0f DD%% %5.1f Sort %5.2f 1ep %s %s" % (
        r["cell"], r["trades_yr"], r["fills_yr_removed"], r["usd_yr"], r["delta_yr"], r["t"], r["top5_share"], r["roc30"], r["dd5"],
        r["ddpct"], r["sortino"], r["one_episode"], extra), flush=True)


def parity():
    return R1.parity()


def pre():
    os.makedirs(OUT, exist_ok=True)
    assert parity()
    d, A, idx, mult = setup()
    c, s = crown_of(d), strat(FILE)
    sess = pd.Index(sorted(set(idx.normalize())))
    yrs = (sess[-1] - sess[0]).days / 365.25
    hold = sized(s, A, c)
    dates = lambda tr: [idx[t[0]].normalize() for t in tr]    # noqa: E731
    base = {x: daily(dates(hold), hold, sess, mult, x) for x in (COST, 0.783, 1.033, FRICTION)}
    out = {"HOLD": row("HOLD", base[COST], base[COST], len(hold), 2 * len(hold), yrs)}
    show(out["HOLD"])
    out["HOLD@1.35"] = row("HOLD@1.35", base[FRICTION], base[FRICTION], len(hold), 2 * len(hold), yrs)
    show(out["HOLD@1.35"])
    for name, cell in CELLS.items():
        tr = sized(s, A, dict(c, **cell))
        dl = daily(dates(tr), tr, sess, mult)
        r = row(name, dl, base[COST], len(tr), 2 * len(hold), yrs)
        sub = []
        for y in range(2011, 2016):
            a, b = dl[dl.index.year == y], base[COST][base[COST].index.year == y]
            fa, fb = four(a), four(b)
            sub.append(dict(y=y, delta=float(a.sum() - b.sum()), win=bool(fa["roc30"] > fb["roc30"] and fa["sortino"] > fb["sortino"])))
        r["years_won"], r["years_up"], r["sub"] = sum(x["win"] for x in sub), sum(x["delta"] > 0 for x in sub), sub
        r["ladder"] = {str(x): float((daily(dates(tr), tr, sess, mult, x) - base[x]).sum() / yrs) for x in (0.783, 1.033)}
        h = out["HOLD"]
        r["PASS"] = bool(r["roc30"] > h["roc30"] and r["sortino"] > h["sortino"] and r["years_won"] >= 3 and r["t"] >= 2
                         and r["top5_share"] < 0.5 and all(v > 0 for v in r["ladder"].values()))
        out[name] = r
        show(r, "yrs won %d/5 up %d/5 ladder %s PASS %s" % (r["years_won"], r["years_up"], {k: round(v) for k, v in r["ladder"].items()}, r["PASS"]))
        fr = row(name + "@1.35", daily(dates(tr), tr, sess, mult, FRICTION), base[FRICTION], len(tr), 2 * len(hold), yrs)
        out[name + "@1.35"] = fr
        show(fr)
    best = max(CELLS, key=lambda n: (out[n]["roc30"], out[n]["sortino"]))
    out["BEST"] = best
    print("BEST", best)
    json.dump(out, open(os.path.join(OUT, "pre.json"), "w"), indent=1, default=float)


def wf():
    best = json.load(open(os.path.join(OUT, "pre.json")))["BEST"]
    d = R1.json.load(open(R1.RUN))
    v = d["validate"]
    win = v["windows"]
    mult = float(d.get("multiplier") or 20.0)
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    A = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    did = np.asarray(A["day_id"])
    warm = int(win.get("warm_days") or 0)   # same as noise_chain_read / noise_t74_giveback
    rows = sorted([r for r in d["top10_results"] if "fold" in r], key=lambda r: int(r["fold"]))
    keys = list(v["champion"].keys())
    s = strat(FILE)
    # #382's bounds are bar indices on the pre-10-14 master; two NT splices added 60 + 69 bars (noise_t74_giveback.chain).
    ins = [(pd.Timestamp("2020-02-28"), 60), (pd.Timestamp("2020-06-30"), 69)]
    if len(idx) - (int(rows[-1]["train_bars"]) + int(rows[-1]["test_bars"])) != 129:
        raise SystemExit("bar drift is not the two known splices")

    def shift(b):
        for dd, n in ins:
            if idx[min(b, len(idx) - 1)].normalize() > dd:
                b += n
        return b

    def fold(r, cell):
        s0, s1 = shift(int(r["train_bars"])), shift(int(r["train_bars"]) + int(r["test_bars"]))
        w = s0
        if warm > 0:
            tgt = int(did[s0]) - warm
            w = 0 if tgt <= int(did[0]) else int(np.searchsorted(did, tgt, side="left"))
        sl = {k: (x[w:s1] if hasattr(x, "__len__") and not isinstance(x, (str, dict)) and len(x) == len(idx) else x) for k, x in A.items()}
        tr = sized(s, sl, dict({k: r[k] for k in keys}, **cell))
        return [(t[0] + w, t[1] + w, t[2], t[3]) for t in tr if t[0] >= s0 - w]

    hold, per, bad = [], [], 0
    for r in rows:
        tr = fold(r, {})
        net = sum(t[2] for t in tr)
        ok = len(tr) == int(r["oos_trades"]) and abs(net - float(r["oos_pnl"])) < 1e-6 * max(1.0, abs(net)) + 1e-6
        print("fold %d HOLD %d trades %.2f pts, stored %d / %.2f %s" % (r["fold"], len(tr), net, r["oos_trades"], r["oos_pnl"], "OK" if ok else "MISMATCH"), flush=True)
        bad += not ok
        hold += tr
        per.append(net)
    print("chain %d trades %.1f pts, stored %s / %s, folds off %d" % (len(hold), sum(t[2] for t in hold), v["wf_oos"]["trades"], v["wf_oos"]["net"], bad), flush=True)
    if bad and not os.environ.get("CHURN_R2_ACCEPT_DRIFT"):
        raise SystemExit("WF PARITY FAILED - nothing reported")
    w0, w1 = pd.Timestamp(v["wf_oos"]["from"]), pd.Timestamp(v["wf_oos"]["to"])
    sess = pd.Index(sorted({x.normalize() for x in idx if w0 <= x.normalize() <= w1}))
    yrs = float(v["wf_oos"]["years"])
    dates = lambda tr: [idx[t[0] - 1].normalize() for t in tr]    # noqa: E731  same booking as noise_chain_read
    base = {x: daily(dates(hold), hold, sess, mult, x) for x in (COST, FRICTION)}
    out = {"BEST": best, "HOLD": row("HOLD", base[COST], base[COST], len(hold), 2 * len(hold), yrs)}
    show(out["HOLD"])
    out["HOLD@1.35"] = row("HOLD@1.35", base[FRICTION], base[FRICTION], len(hold), 2 * len(hold), yrs)
    show(out["HOLD@1.35"])
    h = out["HOLD"]
    for name, cell in dict(R1CELLS, **{best: CELLS[best]}).items():
        tr, won = [], 0
        folds = []
        for r, hn in zip(rows, per):
            t = fold(r, cell)
            tr += t
            net = sum(x[2] for x in t)
            won += net > hn
            folds.append(round(net - hn, 1))
        rr = row(name, daily(dates(tr), tr, sess, mult), base[COST], len(tr), 2 * len(hold), yrs)
        rr["folds_won"], rr["fold_delta_pts"] = int(won), folds
        rr["HOLDS"] = bool(rr["roc30"] > h["roc30"] and rr["sortino"] > h["sortino"] and won >= 5 and rr["t"] >= 2
                           and rr["top5_share"] < 0.5 and not rr["one_episode"])
        out[name] = rr
        show(rr, "folds %d/8 %s HOLDS %s" % (won, folds, rr["HOLDS"]))
        fr = row(name + "@1.35", daily(dates(tr), tr, sess, mult, FRICTION), base[FRICTION], len(tr), 2 * len(hold), yrs)
        out[name + "@1.35"] = fr
        show(fr)
    json.dump(out, open(os.path.join(OUT, "wf.json"), "w"), indent=1, default=float)


def lb():
    best = json.load(open(os.path.join(OUT, "wf.json")))["BEST"]
    d = R1.json.load(open(R1.RUN))
    win = d["validate"]["windows"]
    mult = float(d.get("multiplier") or 20.0)
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    B = load_master_arrays(m, date_from=d["date_from"], date_to=win["lockbox"][1])
    idx = pd.DatetimeIndex(B["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    lo, hi = pd.Timestamp(win["lockbox"][0]), pd.Timestamp(win["lockbox"][1])
    sess = pd.Index(sorted({x.normalize() for x in idx if lo <= x.normalize() <= hi}))
    yrs = (hi - lo).days / 365.25
    s, c = strat(FILE), crown_of(d)

    def run(cell):
        tr = [t for t in sized(s, B, dict(c, **cell)) if lo <= idx[t[0] - 1].normalize() <= hi]
        return tr, [idx[t[0] - 1].normalize() for t in tr]
    h, hd = run({})
    base = {x: daily(hd, h, sess, mult, x) for x in (COST, FRICTION)}
    out = {"HOLD": row("HOLD", base[COST], base[COST], len(h), 2 * len(h), yrs)}
    show(out["HOLD"])
    out["HOLD@1.35"] = row("HOLD@1.35", base[FRICTION], base[FRICTION], len(h), 2 * len(h), yrs)
    show(out["HOLD@1.35"])
    for name, cell in dict(R1CELLS, **{best: CELLS[best]}).items():
        tr, dd = run(cell)
        out[name] = row(name, daily(dd, tr, sess, mult), base[COST], len(tr), 2 * len(h), yrs)
        show(out[name])
        out[name + "@1.35"] = row(name + "@1.35", daily(dd, tr, sess, mult, FRICTION), base[FRICTION], len(tr), 2 * len(h), yrs)
        show(out[name + "@1.35"])
    json.dump(out, open(os.path.join(OUT, "lb.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    {"parity": parity, "pre": pre, "wf": wf, "lb": lb}[sys.argv[1]]()

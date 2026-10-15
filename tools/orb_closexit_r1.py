"""ORB CLOSEXIT r1 (ORB lane, 2026-10-15) - does the last minute of the session pay the live QQQ ORB leg's end-of-day exits? Frozen in
docs/PREREG_orb_closexit_r1_2026-10-15.md; this harness checks that note's LF sha256 first and stops on a mismatch. WF only, lockbox unread,
read-only (stdout and --out only).

    python tools/orb_closexit_r1.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_closexit_r1_2026-10-15.md")
NOTE_SHA = "6c2421f72075cf506ef68f341252510806760d69a3649ab3993595b2adef45a7"
WF0, WF1 = "2016-07-01", "2025-06-27"
UNIT, COST = 10, 0.02


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def four(daily, np):
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    cum = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum))
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    roc = 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("inf")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    sortino = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252))
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "one_episode": d5["one_episode"],
            "dd_pct_peak_at_30k": dd_pct_peak(daily * k, start=100000.0), "sortino": round(sortino, 3), "net_per_year_10sh": round(float(v.sum()) / yrs, 2)}


def ci(x, np):
    from scipy import stats
    x = np.asarray(x, float)
    m, sd = float(x.mean()), float(x.std(ddof=1))
    hw = float(stats.t.ppf(0.975, len(x) - 1) * sd / math.sqrt(len(x)))
    return {"n": int(len(x)), "mean": round(m, 5), "sd": round(sd, 5), "ci95": [round(m - hw, 5), round(m + hw, 5)], "t": round(m / (sd / math.sqrt(len(x))), 3)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    got = lf_sha(NOTE)
    print("PIN note LF sha256 %s (frozen %s); harness LF sha256 %s" % (got, NOTE_SHA, lf_sha(os.path.abspath(__file__))), flush=True)
    if got != NOTE_SHA:
        raise SystemExit("refused: the prereg note is not the frozen one (nothing computed)")
    sys.path.insert(0, a.repo)
    os.chdir(a.repo)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import numpy as np
    import pandas as pd
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    leg = cs.CROWN_LEGS["ORB_R6"]
    T0, T1 = pd.Timestamp(WF0), pd.Timestamp(WF1)

    def et(ix):
        ix = pd.DatetimeIndex(ix)
        return ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix

    m5 = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    a5 = load_master_arrays(m5, date_to=WF1)
    r = run_backtest(leg["strategy"], arrays=a5, params=dict(leg["params"]), cost_pts=0.0, return_trades=True)
    ix5 = et(a5["index"])
    c5 = np.asarray(a5["close"], float)
    last5 = pd.Series(np.arange(len(ix5)), index=ix5).groupby(ix5.normalize()).max()
    m1 = find_master("QQQ", "1m", "rth", "alpaca_split_rth")
    a1 = load_master_arrays(m1, date_from="2016-06-01", date_to=WF1)
    q1 = pd.DataFrame({"o": np.asarray(a1["open"], float), "c": np.asarray(a1["close"], float)}, index=et(a1["index"]))
    day1 = q1.groupby(q1.index.normalize())
    first_o, last_c = day1["o"].first(), day1["c"].last()
    lastmin = pd.Series(q1.index, index=q1.index).groupby(q1.index.normalize()).max()
    mv = ((last_c - first_o).abs() / first_o)
    mv = mv[(mv.index >= T0) & (mv.index <= T1)]
    thr = float(mv.quantile(0.90))
    print("leg %s on %s; 1m %s; trend-day line |C-O|/O >= %.4f" % (leg["strategy"], m5["filename"], m1["filename"], thr), flush=True)
    trades, eod = [], []
    mism = 0
    for t in r["trades"]:
        ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        day = ix5[min(xi, len(ix5) - 1)].normalize()
        if ix5[ei].normalize() < T0 or day > T1:
            continue
        trades.append((day, pts, d, xi))
        xp = e + pts * d
        if xi == int(last5[day]) and abs(xp - c5[xi]) < 1e-6:
            lm = lastmin.get(day)
            if lm is None:
                continue
            E0, E1 = float(q1.at[lm, "c"]), float(q1.at[lm, "o"])
            k2 = lm - pd.Timedelta(minutes=4)
            E2 = float(q1.at[k2, "c"]) if k2 in q1.index else float("nan")
            if abs(E0 - xp) > 1e-6:
                mism += 1
            eod.append({"day": day, "d": d, "e0_e1": d * (E0 - E1), "e0_e2": d * (E0 - E2), "trend": bool(mv.get(day, 0.0) >= thr)})
    E = pd.DataFrame(eod)
    yrs = (T1 - T0).days / 365.25
    print("WF trades %d, EOD exits %d (%.0f%%); last-minute close != engine exit on %d" % (len(trades), len(E), 100 * len(E) / max(1, len(trades)), mism), flush=True)
    res = {"trades": len(trades), "eod": int(len(E)), "mismatch": mism}
    for col in ("e0_e1", "e0_e2"):
        x = E[col].dropna()
        c = ci(x, np)
        c["usd_per_year_10sh"] = round(c["mean"] * UNIT * len(x) / yrs, 2)
        c["trend"] = ci(E.loc[E["trend"], col].dropna(), np)
        c["other"] = ci(E.loc[~E["trend"], col].dropna(), np)
        res[col] = c
        print("%s: n %d mean $%.4f/sh (95%% %s) t %.2f -> $%.2f a year at 10 sh | trend days n %d mean $%.4f (95%% %s) | other n %d mean $%.4f (95%% %s)"
              % (col.upper(), c["n"], c["mean"], c["ci95"], c["t"], c["usd_per_year_10sh"], c["trend"]["n"], c["trend"]["mean"], c["trend"]["ci95"],
                 c["other"]["n"], c["other"]["mean"], c["other"]["ci95"]), flush=True)
    # the leg's four numbers with EOD exits booked at E0 (the backtest) and at E1 (the live executor)
    cal = pd.DatetimeIndex(sorted(set(ix5.normalize())))
    cal = cal[(cal >= T0) & (cal <= T1)]
    shift = E.groupby("day")["e0_e1"].sum()
    base = pd.Series([UNIT * (p - COST) for _d, p, _s, _x in trades], index=pd.DatetimeIndex([d for d, _p, _s, _x in trades])).groupby(level=0).sum()
    base = base.reindex(cal).fillna(0.0)
    live = base - UNIT * shift.reindex(cal).fillna(0.0)
    res["four_E0"], res["four_E1"] = four(base, np), four(live, np)
    for k in ("four_E0", "four_E1"):
        f = res[k]
        print("%s: ROC@30k %s | DD5 $%s | DD%% from peak %s | Sortino %s | net/yr $%s at 10 sh%s" % (k, f["roc30"], f["dd5_at_30k"], f["dd_pct_peak_at_30k"],
              f["sortino"], f["net_per_year_10sh"], " (one episode)" if f["one_episode"] else ""), flush=True)
    lo, hi = res["e0_e1"]["ci95"]
    verdict = ("THE LAST MINUTE PAYS THE POSITION" if lo > 0 else "EXITING EARLY IS BETTER" if hi < 0 else "NO LAST-MINUTE EFFECT")
    res["verdict"] = verdict
    print("VERDICT: %s" % verdict, flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])

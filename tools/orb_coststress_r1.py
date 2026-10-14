"""ORB COSTSTRESS r1 (ORB lane, 2026-10-14) - what trading cost the live Webull ORB leg can carry. Frozen in
docs/PREREG_orb_coststress_r1_2026-10-14.md; this harness checks that note's LF sha256 first and stops on a mismatch.

The leg exactly as the box runs it (api.cloud_signal.CROWN_LEGS["ORB_R6"]) on the QQQ 5m Alpaca master, per share at 10 shares,
cost grid per share per round trip, WF 2016-07-01..2025-06-29 only (lockbox unread); then the live execution shortfall from the
newest box_backup ledgers. Read-only: nothing is written but stdout and --out.

    python tools/orb_coststress_r1.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_coststress_r1_2026-10-14.md")
NOTE_SHA = "0d56ed9f4c86399460bd49a869f28ea57ca844d761db0cf686fd518985da8efb"
WF0, WF1 = "2016-07-01", "2025-06-29"
UNIT = 10
GRID = (0.00, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
BAR = 15.0


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def four(daily, np):
    """ROC @ $30k, DD5, DD % from peak (sized to a $30k worst drawdown, start $100k), Sortino + net/yr - on a daily $ Series"""
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    cum = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum)) if len(v) else 0.0
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    net_y = float(v.sum()) / yrs
    roc = 30.0 * net_y / dd if dd > 0 else float("inf")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    sortino = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252)) if (neg ** 2).mean() > 0 else float("inf")
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "dd5_n": d5["n"], "one_episode": d5["one_episode"],
            "dd_pct_peak_at_30k": dd_pct_peak(daily * k, start=100000.0), "sortino": round(sortino, 3),
            "net_per_year_10sh": round(net_y, 2), "worst_dd_10sh": round(dd, 2)}


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
    sys.path.insert(0, os.path.join(a.repo, "tools"))
    os.chdir(a.repo)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import numpy as np
    import pandas as pd
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    leg = cs.CROWN_LEGS["ORB_R6"]
    m = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    print("leg %s params %s; master %s (id %s)" % (leg["strategy"], leg["params"], m.get("filename"), m.get("id")), flush=True)
    arr = load_master_arrays(m, date_to=WF1)
    r = run_backtest(leg["strategy"], arrays=arr, params=dict(leg["params"]), cost_pts=0.0, return_trades=True)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    tr = [(ix[int(t[0])].normalize(), ix[min(int(t[1]), len(ix) - 1)].normalize(), float(t[2])) for t in r["trades"]]
    tr = [(e, x, p) for e, x, p in tr if e >= pd.Timestamp(WF0) and x <= pd.Timestamp(WF1)]
    cal = pd.DatetimeIndex(sorted(set(ix.normalize())))
    cal = cal[(cal >= WF0) & (cal <= WF1)]
    yrs = (cal[-1] - cal[0]).days / 365.25
    pts = np.array([p for _e, _x, p in tr])
    xd = pd.DatetimeIndex([x for _e, x, _p in tr])
    n = len(pts)
    gross = float(pts.sum()) * UNIT
    print("WF %s..%s: %d sessions, %d trades (%.1f a year), gross $%.2f at %d sh" % (cal[0].date(), cal[-1].date(), len(cal), n, n / yrs, gross, UNIT),
          flush=True)

    def daily(c):
        s = pd.Series(UNIT * (pts - c), index=xd).groupby(level=0).sum()
        return s.reindex(cal).fillna(0.0)

    cells = {}
    for c in GRID:
        d = daily(c)
        u = UNIT * (pts - c)
        f = four(d, np)
        f.update(trades_per_year=round(n / yrs, 1), pf=round(float(u[u > 0].sum() / -u[u < 0].sum()), 3) if (u < 0).any() else None)
        cells["%.2f" % c] = f
        print("cost $%.2f/sh RT: ROC@30k %s | DD5 $%s | DD%% from peak %s | Sortino %s | net/yr $%s at 10 sh | PF %s"
              % (c, f["roc30"], f["dd5_at_30k"], f["dd_pct_peak_at_30k"], f["sortino"], f["net_per_year_10sh"], f["pf"]), flush=True)
    c0 = gross / (UNIT * n)
    lo, hi = 0.0, c0
    if four(daily(0.0), np)["roc30"] <= BAR:
        c15 = None
    else:
        while hi - lo > 0.0005:
            mid = (lo + hi) / 2
            if four(daily(mid), np)["roc30"] > BAR:
                lo = mid
            else:
                hi = mid
        c15 = round((lo + hi) / 2, 3)
    print("BREAK-EVENS: c0 (WF net = 0) $%.3f/sh RT; c15 (ROC@30k = 15) %s" % (c0, "n/a" if c15 is None else "$%.3f/sh RT" % c15), flush=True)
    v1 = "cost-fragile on its own backtest (c15 < $0.05)" if (c15 is not None and c15 < 0.05) else "carries cost to c15"

    # live execution shortfall vs the engine's own ref prices
    import harm_monitor as HM
    f = HM.webull_folder(pd.Timestamp.now().normalize() + pd.Timedelta(days=1))
    live = {"folder": None}
    if f is not None:
        S = pd.read_csv(os.path.join(f[0], "cloud_signal", "signals.csv"))
        T = pd.read_csv(os.path.join(f[0], "qqq_exec", "trades.csv"))
        s = S[(S["leg"] == "ORB_R6") & S["trade_id"].notna()]
        en = s[s["event"] == "ENTRY"].drop_duplicates("trade_id", keep="last").set_index("trade_id")
        ex = s[s["event"] == "EXIT"].drop_duplicates("trade_id", keep="last").set_index("trade_id")
        e = en[["side", "ref_price"]].join(ex[["ref_price", "ref_time", "reason"]], rsuffix="_x", how="inner")
        t = T[T["trade_id"].astype(str).isin(set(e.index))].drop_duplicates("trade_id", keep="last").set_index("trade_id")
        e = e.join(t[["entry_px", "exit_px", "exit_reason"]], how="left")
        sg = np.where(e["side"].astype(str).str.lower().str.startswith("s"), -1.0, 1.0)
        e["entry_gap"] = sg * (e["entry_px"].astype(float) - e["ref_price"].astype(float))      # adverse = paid more (long) / got less (short)
        e["exit_gap"] = sg * (e["ref_price_x"].astype(float) - e["exit_px"].astype(float))      # adverse = sold lower (long) / covered higher (short)
        e["shortfall"] = e["entry_gap"] + e["exit_gap"]
        e["eod"] = e["reason"].astype(str).str.contains("eod", case=False)
        filled = e[e["entry_px"].notna() & e["exit_px"].notna()]
        x = filled["shortfall"].to_numpy(float)
        live = {"folder": os.path.basename(f[0]), "engine_trades": int(len(e)), "filled": int(len(filled)),
                "unfilled": [str(i) for i in e.index[e["entry_px"].isna()]]}
        if len(x) >= 2:
            from scipy import stats
            sd = float(x.std(ddof=1))
            hw = float(stats.t.ppf(0.975, len(x) - 1) * sd / math.sqrt(len(x)))
            live.update(n=int(len(x)), mean=round(float(x.mean()), 4), sd=round(sd, 4), ci95=[round(float(x.mean()) - hw, 4), round(float(x.mean()) + hw, 4)],
                        entry_gap_mean=round(float(filled["entry_gap"].mean()), 4), exit_gap_mean=round(float(filled["exit_gap"].mean()), 4),
                        eod_mean=round(float(filled.loc[filled["eod"], "shortfall"].mean()), 4) if filled["eod"].any() else None,
                        other_mean=round(float(filled.loc[~filled["eod"], "shortfall"].mean()), 4) if (~filled["eod"]).any() else None,
                        rows=[(str(i), round(float(a_), 4), round(float(b_), 4), bool(c_)) for i, a_, b_, c_ in
                              zip(filled.index, filled["entry_gap"], filled["exit_gap"], filled["eod"])])
            if c15 is not None:
                target = (c15 - 0.02) / 2
                live["n_for_halfwidth"] = int(math.ceil((1.96 * sd / target) ** 2)) if target > 0 else None
                if live["mean"] > c15:
                    v2 = "at the measured cost the leg is below the ROC-15 bar: flagged to MANAGER, an owner decision; nothing changes"
                elif live["ci95"][1] < c15:
                    v2 = "live cost inside the bar"
                else:
                    v2 = "undecided at %d trades" % len(x)
            else:
                v2 = "n/a (the leg is under the bar at zero cost)"
        else:
            v2 = "no live read (fewer than 2 filled trades)"
    else:
        v2 = "no box_backup folder"
    print("LIVE: %s" % json.dumps(live, default=str), flush=True)
    print("VERDICT V1: %s. V2: %s." % (v1, v2), flush=True)
    out = {"note_sha": got, "window": [WF0, WF1], "unit": UNIT, "trades": n, "years": round(yrs, 3), "gross_10sh": round(gross, 2),
           "cells": cells, "c0": round(c0, 4), "c15": c15, "live": live, "v1": v1, "v2": v2}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])

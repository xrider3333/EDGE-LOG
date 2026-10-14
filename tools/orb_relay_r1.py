"""ORB-RELAY r1 (ORB lane, 2026-10-14) - the live QQQ ORB leg on NQ's signals instead of QQQ's own. Frozen in
docs/PREREG_orb_relay_r1_2026-10-14.md; this harness checks that note's LF sha256 first and stops on a mismatch.

Rows (WF 2016-07-01..2025-06-27, lockbox unread; 10 QQQ shares, $0.02 a share a round trip):
  A AS LIVE       ORB_R6 on QQQ's own 5m bars (the engine's bar-close fills)
  B RELAY         #314 on NQ 5m bars, filled on QQQ 1m prints at the same instants
  C RELAY + LAG   as B, entry at the open of the first QQQ minute after the NQ signal bar
  D REFERENCE     NQ #314 itself per NQ contract
Read-only: nothing is written but stdout and --out.

    python tools/orb_relay_r1.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_relay_r1_2026-10-14.md")
NOTE_SHA = "0da0f8ee9cabecc0fcaf927fb5365181be444d6a0c935e6afc93deda4d0c9bcb"
WF0, WF1 = "2016-07-01", "2025-06-27"
UNIT, COST = 10, 0.02
NQ_MULT, NQ_COST = 20.0, 0.533
DRAWS, BLOCK, SEED = 2000, 20, 20261014


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def roc30(v, yrs, np):
    cum = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum)) if len(v) else 0.0
    return 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("inf"), dd


def four(daily, np):
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    roc, dd = roc30(v, yrs, np)
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    sortino = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252)) if (neg ** 2).mean() > 0 else float("inf")
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "one_episode": d5["one_episode"],
            "dd_pct_peak_at_30k": dd_pct_peak(daily * k, start=100000.0), "sortino": round(sortino, 3),
            "net_per_year": round(float(v.sum()) / yrs, 2), "worst_dd": round(dd, 2)}


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
    P = dict(leg["params"])
    T0, T1 = pd.Timestamp(WF0), pd.Timestamp(WF1)

    def et(ix):
        ix = pd.DatetimeIndex(ix)
        return ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix

    def trades_of(src_args, cost_pts=0.0):
        m = find_master(*src_args)
        arr = load_master_arrays(m, date_to=WF1)
        r = run_backtest(leg["strategy"], arrays=arr, params=dict(P), cost_pts=cost_pts, return_trades=True)
        ix = et(arr["index"])
        out = []
        for t in r["trades"]:
            ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
            if ix[ei].normalize() < T0 or ix[min(xi, len(ix) - 1)].normalize() > T1:
                continue
            out.append((ei, xi, pts, d, e))
        return m, arr, ix, out

    qm5, q5, qix5, A_tr = trades_of(("QQQ", "5m", "rth", "alpaca_split_rth"))
    nm5, n5, nix5, N_tr = trades_of(("NQ", "5m", "rth", "db_adj_rth"))
    print("A: %s %d trades on QQQ 5m %s; NQ #314: %d trades on NQ 5m %s; params %s" % (leg["strategy"], len(A_tr), qm5["filename"], len(N_tr),
                                                                                     nm5["filename"], P), flush=True)
    cal = pd.DatetimeIndex(sorted(set(qix5.normalize())))
    cal = cal[(cal >= T0) & (cal <= T1)]
    ncal = pd.DatetimeIndex(sorted(set(nix5.normalize())))
    ncal = ncal[(ncal >= T0) & (ncal <= T1)]

    def daily(rows, calendar):
        if not rows:
            return pd.Series(0.0, index=calendar)
        s = pd.Series([v for _d, v in rows], index=pd.DatetimeIndex([d for d, _v in rows])).groupby(level=0).sum()
        return s.reindex(calendar).fillna(0.0)

    A_rows = [(qix5[min(xi, len(qix5) - 1)].normalize(), UNIT * (pts - COST)) for _ei, xi, pts, _d, _e in A_tr]
    D_rows = [(nix5[min(xi, len(nix5) - 1)].normalize(), NQ_MULT * (pts - NQ_COST)) for _ei, xi, pts, _d, _e in N_tr]

    # the 1m prints for the relay
    m1n = find_master("NQ", "1m", "rth", "db_adj_rth")
    m1q = find_master("QQQ", "1m", "rth", "alpaca_split_rth")
    a1n = load_master_arrays(m1n, date_from="2016-06-01", date_to=WF1)
    a1q = load_master_arrays(m1q, date_from="2016-06-01", date_to=WF1)
    n1 = pd.DataFrame({"h": np.asarray(a1n["high"], float), "l": np.asarray(a1n["low"], float)}, index=et(a1n["index"]))
    q1 = pd.DataFrame({"o": np.asarray(a1q["open"], float), "c": np.asarray(a1q["close"], float)}, index=et(a1q["index"]))
    print("1m: NQ %s (%d rows), QQQ %s (%d rows)" % (m1n["filename"], len(n1), m1q["filename"], len(q1)), flush=True)
    nclose = np.asarray(n5["close"], float)
    day_of = nix5.normalize()
    last_of_day = pd.Series(np.arange(len(nix5)), index=nix5).groupby(day_of).max()
    one = pd.Timedelta(minutes=1)
    B_rows, C_rows, B_keys = [], [], set()
    miss, fallback, eod_n = 0, 0, 0
    for ei, xi, pts, d, e in N_tr:
        te, tx = nix5[ei], nix5[xi]
        qe_b = q1["c"].get(te + 4 * one)
        qe_c = q1["o"].get(te + 5 * one)
        lvl = e + pts * d                                        # the NQ exit price (no partials in #314)
        is_eod = xi == int(last_of_day[tx.normalize()]) and abs(lvl - nclose[xi]) < 1e-6
        if is_eod:
            qx = q1["c"].get(tx + 4 * one)
            eod_n += 1
        else:
            mins = n1.loc[tx:tx + 4 * one]
            if d > 0:
                hit = mins.index[(mins["l"] <= lvl).to_numpy()] if lvl <= e else mins.index[(mins["h"] >= lvl).to_numpy()]
            else:
                hit = mins.index[(mins["h"] >= lvl).to_numpy()] if lvl >= e else mins.index[(mins["l"] <= lvl).to_numpy()]
            if len(hit):
                qx = q1["c"].get(hit[0])
            else:
                qx = q1["c"].get(tx + 4 * one)
                fallback += 1
        if qe_b is None or qx is None or (isinstance(qe_b, float) and math.isnan(qe_b)) or (isinstance(qx, float) and math.isnan(qx)):
            miss += 1
            continue
        day = tx.normalize()
        B_rows.append((day, UNIT * (d * (float(qx) - float(qe_b)) - COST)))
        B_keys.add((te.normalize(), d))
        if qe_c is not None and not (isinstance(qe_c, float) and math.isnan(qe_c)):
            C_rows.append((day, UNIT * (d * (float(qx) - float(qe_c)) - COST)))
    A_keys = {(qix5[ei].normalize(), d) for ei, _xi, _p, d, _e in A_tr}
    overlap = len(A_keys & B_keys) / max(1, len(A_keys))
    print("relay fills: %d NQ trades, %d without a QQQ minute (dropped), %d EOD, %d stop/target exits with no NQ minute at the level (bar's last minute used)"
          % (len(N_tr), miss, eod_n, fallback), flush=True)

    rows = {"A": daily(A_rows, cal), "B": daily(B_rows, cal), "C": daily(C_rows, cal), "D": daily(D_rows, ncal)}
    tr_n = {"A": len(A_rows), "B": len(B_rows), "C": len(C_rows), "D": len(D_rows)}
    yrs = (cal[-1] - cal[0]).days / 365.25
    res = {}
    for k, s in rows.items():
        f = four(s, np)
        f["trades_per_year"] = round(tr_n[k] / yrs, 1)
        res[k] = f
        print("%s: ROC@30k %s | DD5 $%s | DD%% from peak %s | Sortino %s | net/yr $%s | %s trades/yr%s"
              % (k, f["roc30"], f["dd5_at_30k"], f["dd_pct_peak_at_30k"], f["sortino"], f["net_per_year"], f["trades_per_year"],
                 " (one episode)" if f["one_episode"] else ""), flush=True)

    # paired block bootstrap of the ROC leads on the shared QQQ calendar
    rng = np.random.default_rng(SEED)
    VA, VB, VC = (rows[k].to_numpy(float) for k in ("A", "B", "C"))
    N = len(VA)
    nb = int(math.ceil(N / BLOCK))
    lb, lc = [], []
    for _ in range(DRAWS):
        st = rng.integers(0, N - BLOCK + 1, size=nb)
        idx = (st[:, None] + np.arange(BLOCK)[None, :]).ravel()[:N]
        ra = roc30(VA[idx], yrs, np)[0]
        lb.append(roc30(VB[idx], yrs, np)[0] - ra)
        lc.append(roc30(VC[idx], yrs, np)[0] - ra)
    lead_b, lead_c = res["B"]["roc30"] - res["A"]["roc30"], res["C"]["roc30"] - res["A"]["roc30"]
    ci_b = [round(float(np.percentile(lb, 5)), 2), round(float(np.percentile(lb, 95)), 2)]
    ci_c = [round(float(np.percentile(lc, 5)), 2), round(float(np.percentile(lc, 95)), 2)]
    keep = float(VC.sum()) / float(VB.sum()) if VB.sum() != 0 else float("nan")
    print("LEADS: B - A %+.2f ROC points (90%% %s); C - A %+.2f (90%% %s); C keeps %.0f%% of B's net; overlap: B takes %.0f%% of A's trades (same day, side)"
          % (lead_b, ci_b, lead_c, ci_c, 100 * keep, 100 * overlap), flush=True)
    if lead_c >= 5.0 and ci_c[0] > 0 and keep >= 0.90:
        verdict = "RELAY RECOMMENDED (a design call for PAPER-WB + the owner; nothing changes here)"
    elif lead_c >= 5.0:
        verdict = "LEADS, NOT DISTINGUISHABLE"
    else:
        verdict = "NO CASE FOR THE RELAY"
    print("VERDICT: %s" % verdict, flush=True)
    out = {"note_sha": got, "window": [WF0, WF1], "rows": res, "lead_b": round(lead_b, 2), "ci_b": ci_b, "lead_c": round(lead_c, 2), "ci_c": ci_c,
           "c_keeps_of_b": round(keep, 4), "overlap": round(overlap, 4), "relay_missing": miss, "relay_fallback": fallback, "eod": eod_n,
           "verdict": verdict}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])

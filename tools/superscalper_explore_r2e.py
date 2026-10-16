# SUPERSCALPER r2e (prereg docs/PREREG_tv_superscalper_r2e_prewf_2026-10-16.md): does r2d's carrier (RE long) beat an always-long
# twin (same clock window on every other date) on the PRE-WF rows 2010-06 .. 2016-06, never read by this port? Step 0 = the
# QQQ-withheld control on the dev years. Reuses r2's harness (sha-checked) for the engine, master loader, stats, four numbers. OUR PORT.
#   python tools/superscalper_explore_r2e.py
import csv, hashlib, json, math, os, sys, warnings
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r2e_prewf_2026-10-16.md")
PREREG_LF_SHA = "3540734525a048f28090df27c2c73ea3c4a4ecb2de71dfba5d9ad563b755d51a"
R2 = os.path.join(SHARED, "tools", "superscalper_explore_r2.py")
R2_LF_SHA = "26a2f9aab8f83ee3b058f4d9492e906d4f5484643eb4122be6f87eff29ecf9ab"
PORTS = [os.path.join(SHARED, "augur_strategies", "MISC_SUPERSCALPER_1_0.py"),
         r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\superscalp\augur_strategies\MISC_SUPERSCALPER_1_0.py"]
PORT_LF_SHA = "b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2e.json"
DEV = {"2023": ("2023-01-01", "2023-12-31"), "2024": ("2024-01-01", "2024-12-31")}
GATES = {"2023": dict(trades=2311, net=2005.9, win=0.5690), "2024": dict(trades=2633, net=1997.4, win=0.5853)}
PRE = {"P0 2010H2": ("2010-06-06", "2010-12-31"), "P1 2011": ("2011-01-01", "2011-12-31"), "P2 2012": ("2012-01-01", "2012-12-31"),
       "P3 2013": ("2013-01-01", "2013-12-31"), "P4 2014": ("2014-01-01", "2014-12-31"), "P5 2015": ("2015-01-01", "2015-12-31"),
       "P6 2016H1": ("2016-01-01", "2016-06-30")}
PRE_YEARS = (pd.Timestamp("2016-06-30") - pd.Timestamp("2010-06-06")).days / 365.25
VALIDATE_FIRST_DAY = "2016-07-01"
COSTS = (("0.706", 0.706), ("+1 tick 0.956", 0.956))
NO_QQQ = {"time": np.zeros(0, np.int64), "open": np.zeros(0), "high": np.zeros(0), "low": np.zeros(0), "close": np.zeros(0)}
CELLS = ("RE long", "BOS long", "ALL long", "ALL short", "ALL")
SLACK = 300                                                     # twin bars must start within 5 minutes after the target time
BAR_T, BAR_PF, BAR_N = 2.0, 1.10, 100


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def switches():
    out = []
    with open(os.path.join(SHARED, "tools", "data", "rolls_NQ.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")):
                continue
            out.append(int(r["switch_sec"]))
    return np.array(sorted(out), dtype=np.int64)


def twin_changes(secs, o, et, eb, xb, days, sw):
    """the always-long twin per trade: mean open-to-open change over the same NY clock window on every OTHER date of the period."""
    n = len(secs)
    dates = pd.DatetimeIndex(days)
    out, used = np.full(len(eb), np.nan), np.zeros(len(eb), np.int64)
    for i, (a, b) in enumerate(zip(eb, xb)):
        t_e = et[a]
        clock = pd.Timedelta(hours=t_e.hour, minutes=t_e.minute, seconds=t_e.second)
        dur = int(secs[b] - secs[a])
        own = t_e.normalize().tz_localize(None)
        wall = (dates[dates != own] + clock).tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        wall = wall[~wall.isna()]
        t0 = (wall.asi8 // 10**9).astype(np.int64)
        t1 = t0 + dur
        p0, p1 = np.searchsorted(secs, t0), np.searchsorted(secs, t1)
        ok = (p0 < n) & (p1 < n)
        p0c, p1c = np.minimum(p0, n - 1), np.minimum(p1, n - 1)
        ok &= (secs[p0c] - t0 <= SLACK) & (secs[p1c] - t1 <= SLACK) & (p1c >= p0c)
        ok &= np.searchsorted(sw, secs[p0c], side="right") == np.searchsorted(sw, secs[p1c], side="right")
        if ok.any():
            out[i] = float((o[p1c[ok]] - o[p0c[ok]]).mean())
            used[i] = int(ok.sum())
    return out, used


def run(R, yr, qqq, twin=True):
    """one standalone period: r2's engine call + each trade's path, side, bars, the twin, and the all-bar drift (context)."""
    m, a = R.arrays("NQ", yr)
    es_m, es_a = R.arrays("ES", yr)                                   # the ES helper must hold this period (the port drops it silently)
    if len(es_a["close"]) < 0.9 * len(a["close"]):
        sys.exit("refused: the ES helper master holds %d bars for %s vs NQ %d" % (len(es_a["close"]), yr, len(a["close"])))
    params = dict(close_rule="any", intrabar="worst", _detail=True)
    if not qqq:
        params["_feed_qqq"] = NO_QQQ
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = R.run_bt(R.port, arrays=a, master=m, params=params, cost_pts=0.0, return_trades=True)
    bad = [str(w.message) for w in caught if "feed unavailable" in str(w.message)]
    if bad:
        sys.exit("refused: a helper feed failed to load for %s: %s" % (yr, bad))
    rows = (r or {}).get("trade_detail") or []
    idx = pd.DatetimeIndex(a["index"])
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    et = idx.tz_convert("America/New_York")
    day = pd.Series(et.normalize().tz_localize(None))
    days = pd.DatetimeIndex(sorted(day.unique()))
    o, c = np.asarray(a["open"], float), np.asarray(a["close"], float)
    secs = (idx.tz_convert("UTC").asi8 // 10**9).astype(np.int64)
    sw = switches()
    straddle = np.searchsorted(sw, secs[1:], side="right") != np.searchsorted(sw, secs[:-1], side="right")
    mu = float(np.diff(c)[~straddle].mean())
    eb = np.array([x["entry_bar"] for x in rows], np.int64)
    xb = np.array([x["exit_bar"] for x in rows], np.int64)
    df = pd.DataFrame({"pnl": [x["pnl_pts"] for x in rows], "path": [x["path"] for x in rows],
                       "side": ["long" if x["side"] > 0 else "short" for x in rows],
                       "sgn": [1.0 if x["side"] > 0 else -1.0 for x in rows], "eb": eb, "xb": xb,
                       "exit_day": [day.iloc[b] for b in xb]})
    df["mu_drift"] = df["sgn"] * mu * (df["xb"] - df["eb"])
    if twin and len(df):
        tw, used = twin_changes(secs, o, et, eb, xb, days, sw)
        df["twin"], df["twin_dates"] = tw, used
        df["d"] = df["pnl"] - df["sgn"] * df["twin"]               # cost cancels: trade and twin pay the same
    info = dict(mu=mu, bars=len(c), first=str(days[0].date()), last=str(days[-1].date()), trades=len(df))
    return df, days, info


def pick(d, cell):
    if cell == "ALL":
        return d
    p, s = cell.split(" ")
    out = d[d["side"] == s]
    return out if p == "ALL" else out[out["path"] == p]


def pf_raw(g, cost):
    """net PF from unrounded sums; None for an empty set (no trades = no PF), inf only for an all-winner set"""
    net = np.asarray(g, float) - cost
    if not len(net):
        return None
    lo = -net[net <= 0].sum()
    return float(net[net > 0].sum() / lo) if lo > 0 else float("inf")


def paired(dvals):
    d = np.asarray(dvals, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return dict(n=len(d), mean=None, sd=None, t=None)
    sd = float(d.std(ddof=1))
    return dict(n=len(d), mean=float(d.mean()), sd=sd, t=float(d.mean() / (sd / math.sqrt(len(d)))) if sd > 0 else None)


def finite(x):
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [finite(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else str(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH", flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    if lf_sha(R2) != R2_LF_SHA:
        sys.exit("refused: r2 harness is not %s" % R2_LF_SHA)
    port = next((p for p in PORTS if os.path.exists(p) and lf_sha(p) == PORT_LF_SHA), None)
    if port is None:
        sys.exit("refused: no port with LF sha %s" % PORT_LF_SHA)
    assert all(b[1] < VALIDATE_FIRST_DAY for b in PRE.values())
    sys.path.insert(0, os.path.dirname(R2))
    import superscalper_explore_r2 as X
    print("r2 harness OK; port", port, "OK; harness LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)
    R = X.Runner(port)
    es = R.fm("ES", "1m", "eth", "db_noadj_eth")
    if not es or (int(es.get("id") or 0), es.get("filename")) != (30, "NOADJ_ES_1m_ETH.csv") or \
            str(es.get("date_from"))[:10] > min(b[0] for b in PRE.values()):
        sys.exit("refused: the ES helper master is not id 30 NOADJ_ES_1m_ETH.csv covering 2010-06-06: %r" % (es,))
    print("ES helper OK: id 30 %s .. %s" % (es.get("date_from"), es.get("date_to")), flush=True)
    out = {"step0": {}, "pre": {}, "info": {}}

    def still():
        if lf_sha(port) != PORT_LF_SHA:
            sys.exit("refused: the port changed during the run - nothing written")

    def read_cells(d, days, label, years):
        rows = {}
        for cname, cost in COSTS:
            X.COST["NQ"] = cost
            rows[cname] = {}
            for cell in CELLS:
                s = pick(d, cell)
                r = X.Runner.read(R, "NQ", s[["pnl", "exit_day"]], days, "%s %s @ %s" % (label, cell, cname))
                r["trades_per_year"] = len(s) / years
                r["raw_net_per_trade"] = float((s["pnl"] - cost).mean()) if len(s) else None
                r["mu_drift_adj_net_per_trade"] = float(((s["pnl"] - cost) - s["mu_drift"]).mean()) if len(s) else None
                if "d" in s:
                    r["twin_paired"] = paired(s["d"].values)
                rows[cname][cell] = r
            X.COST["NQ"] = 0.706
        return rows

    # STEP 0 - parity with QQQ present, then the QQQ-withheld control, on the dev years
    for y, yr in DEV.items():
        d, days, info = run(R, yr, qqq=True, twin=False)
        still()
        G = GATES[y]
        tot, win = round(float((d["pnl"] - 0.706).sum()), 1), float(((d["pnl"] - 0.706) > 0).mean())
        print("PARITY GATE %s (QQQ present): %d trades, %.1f net, win %.4f (expected %d / %.1f / %.4f)" % (
            y, len(d), tot, win, G["trades"], G["net"], G["win"]), flush=True)
        if len(d) != G["trades"] or abs(tot - G["net"]) > 0.05 or abs(win - G["win"]) > 0.0005:
            sys.exit("refused: parity gate failed for %s" % y)
        d0, days0, info0 = run(R, yr, qqq=False, twin=False)
        still()
        key = lambda f: set(zip(f["eb"], f["side"], f["path"]))
        ov = len(key(d) & key(d0))
        re_ = pick(d0, "RE long")["pnl"].values
        carry = dict(trades=len(re_), pf_0706=pf_raw(re_, 0.706), pf_0956=pf_raw(re_, 0.956))
        print("\nSTEP 0 %s QQQ withheld: %d trades (with QQQ %d, same entry/side/path %d); RE long %s" % (
            y, len(d0), len(d), ov, json.dumps(finite(carry))), flush=True)
        out["step0"][y] = dict(trades_with=len(d), trades_without=len(d0), overlap=ov, re_long=carry,
                               cells=read_cells(d0, days0, "%s noQQQ" % y, 1.0))
    same_object = all(v["re_long"]["trades"] >= BAR_N and (v["re_long"]["pf_0706"] or 0) >= 1.10
                      and (v["re_long"]["pf_0956"] or 0) > 1.0 for v in out["step0"].values())
    out["same_object"] = same_object
    print("\nSTEP 0: RE long still carries both dev years with QQQ withheld (same_object):", same_object, flush=True)

    # the PRE-WF periods, QQQ withheld (not held before 2016-01-04)
    pooled, pdays = [], []
    for pname, yr in PRE.items():
        d, days, info = run(R, yr, qqq=False)
        still()
        yrs = max((pd.Timestamp(yr[1]) - pd.Timestamp(yr[0])).days + 1, 1) / 365.25
        out["info"][pname] = info
        print("\n%s %s .. %s: %d trades, all-bar drift mu %.5f pt/bar" % (pname, info["first"], info["last"], len(d), info["mu"]),
              flush=True)
        out["pre"][pname] = read_cells(d, days, pname, yrs)
        json.dump(finite(out), open(OUT + ".partial", "w"), indent=1, default=str, allow_nan=False)   # checkpoint
        pooled.append(d.assign(period=pname))
        pdays.append(days)
    P = pd.concat(pooled, ignore_index=True)
    if "d" not in P:
        P["d"] = np.nan
    PD = pdays[0]
    for x in pdays[1:]:
        PD = PD.union(x)
    print("\nPOOLED P0-P6 (%d trading days, %.2f years)" % (len(PD), PRE_YEARS), flush=True)
    out["pooled"] = read_cells(P, PD, "POOLED", PRE_YEARS)

    re_ = pick(P, "RE long")
    A = paired(re_["d"].values)
    no_twin = int((~np.isfinite(re_["d"].values)).sum())
    pf956 = pf_raw(re_["pnl"].values, 0.956)
    day_net = (re_["pnl"] - 0.956).groupby(re_["exit_day"]).sum()
    best_day = day_net.idxmax() if len(day_net) else None
    pf956_xbest = pf_raw(re_[re_["exit_day"] != best_day]["pnl"].values, 0.956) if best_day is not None else None
    tests = dict(A_twin=bool(A["t"] is not None and A["t"] >= BAR_T), B_pf=bool(pf956 is not None and pf956 >= BAR_PF),
                 C_count=bool(len(re_) / PRE_YEARS >= BAR_N), D_episode=bool(pf956_xbest is not None and pf956_xbest >= BAR_PF))
    labels = dict(A_twin="not separable from always-long drift", B_pf="below the PF bar at +1 tick", C_count="too thin",
                  D_episode="one episode")
    per_period = {p: dict(trades=int((re_["period"] == p).sum()), pf_0706=pf_raw(re_[re_["period"] == p]["pnl"].values, 0.706))
                  for p in PRE}
    out["re_long_test"] = dict(pooled_trades=len(re_), per_year=len(re_) / PRE_YEARS, paired_vs_twin=A, no_twin_trades=no_twin,
                               pf_0706=pf_raw(re_["pnl"].values, 0.706), pf_0956=pf956, best_exit_day=str(best_day),
                               pf_0956_without_best_day=pf956_xbest, per_period=per_period, tests=tests)
    if all(tests.values()):
        verdict = "RE LONG HOLDS PRE-WF" if same_object else "HOLDS FOR THE NO-QQQ VARIANT ONLY - not a candidate"
    else:
        verdict = "RE LONG FAILS PRE-WF: " + "; ".join(labels[k] for k, v in tests.items() if not v)
    out["verdict"] = verdict
    print("\nRE long test:", json.dumps(finite(out["re_long_test"])), flush=True)
    print("VERDICT:", verdict, flush=True)
    json.dump(finite(out), open(OUT, "w"), indent=1, default=str, allow_nan=False)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()

# Round 4 Stage A triage (pre-registered: tools/rocfrontier/PREREG_WKND_FOMCWK_R1.txt, sha256 c0b92c9d...1921).
# W = WKND r1 (weekend gap on the Sunday reopen), F = FOMCWK r1 (FOMC-cycle even weeks).
# PRE-LOCKBOX ONLY: every candidate array is cut to bars before 2025-06-30 before any signal is computed.
import json, os, sys
REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"; sys.path.insert(0, REPO); os.chdir(REPO)
import numpy as np, pandas as pd
from augur_engine import data

OUT = os.environ.get("EDGELOG_ROCFRONTIER_R4", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4")   # results stay outside git
LB0 = pd.Timestamp("2025-06-30", tz="US/Eastern")          # lockbox start - nothing on/after is loaded
WF0 = pd.Timestamp("2016-07-01")
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.533, "ES": 0.363}
STRESS = 0.25
NREP = 500
rng = np.random.default_rng(20260928)


def load(inst, sess, src):
    m = data.find_master(inst, "5m", sess, src)
    a = data.load_master_arrays(m, "2010-06-01", "2025-06-29")
    idx = a["index"]
    keep = np.asarray(idx < LB0)
    assert keep.sum() > 0 and idx[keep].max() < LB0
    return {k: (np.asarray(a[k])[keep] if k != "index" else idx[keep]) for k in ("open", "high", "low", "close", "day_id", "index")}


def rolls(inst):
    r = pd.read_csv(os.path.join(REPO, "tools", "data", f"rolls_{inst}.csv"))
    r = r[r["kind"] != "not_a_roll"]
    return np.sort(r["switch_sec"].astype(np.int64).to_numpy())


# ---------------------------------------------------------------- statistics (one contract, $)
def dd(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def stretch_stats(tr, daily, t0, t1):
    """tr: DataFrame(date, pnl) one row per trade (pnl in $ net of cost); daily: Series date -> $ (valued daily)."""
    t = tr[(tr["date"] >= t0) & (tr["date"] < t1)]
    d = daily[(daily.index >= t0) & (daily.index < t1)]
    yrs = (t1 - t0).days / 365.25
    n = len(t)
    net = float(t["pnl"].sum())
    gw, gl = float(t["pnl"][t["pnl"] > 0].sum()), float(-t["pnl"][t["pnl"] < 0].sum())
    ddv = dd(d.values)
    mar = (net / yrs) / ddv if ddv > 0 else float("nan")
    sd = float(t["pnl"].std(ddof=1)) if n > 1 else float("nan")
    tstat = float(t["pnl"].mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan")
    by_year = t.groupby(t["date"].dt.year)["pnl"].sum()
    big = float(t["pnl"].max()) if n else 0.0
    dsd = float(d.std(ddof=1)) if len(d) > 1 else float("nan")
    return {"n": n, "net": net, "pf": gw / gl if gl > 0 else float("inf"), "dd_daily": ddv, "mar": mar,
            "roc30": 30.0 * mar, "t": tstat, "years_pos": float((by_year > 0).mean()) if len(by_year) else 0.0,
            "net_ex_big": net - big, "sharpe": float(d.mean() / dsd * np.sqrt(252)) if dsd and dsd > 0 else float("nan")}


# ---------------------------------------------------------------- FAMILY W: weekend gap
X_TIMES = {"X1_0300": (3, 0, "open"), "X2_0925": (9, 25, "open"), "X3_1600": (16, 0, "close_before")}
KS = (0.0, 0.25, 0.5)


def wknd_events(inst):
    a = load(inst, "eth", "db_adj_eth")
    idx, o, h, l, c, did = a["index"], a["open"], a["high"], a["low"], a["close"], a["day_id"]
    tsec = (idx.asi8 // 10**9).astype(np.int64)
    # ETH day_id changes at MIDNIGHT ET, so build the 18:00 -> 17:00 ET session key ourselves: date of (t + 6h)
    did = ((idx + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8 // (86400 * 10**9)).astype(np.int64)
    sid = pd.Series(did)
    hi = pd.Series(h).groupby(sid).max(); lo = pd.Series(l).groupby(sid).min()
    rngs = (hi - lo)
    gaps = np.diff(tsec)
    firsts = np.where(gaps >= 24 * 3600)[0] + 1          # first bar of a new week
    sw = rolls(inst)
    ev = []
    for i in firsts:
        f = i - 1
        if i + 1 >= len(o):
            continue
        if idx[f].hour >= 17:                             # F must start before 17:00 ET
            continue
        s_f = did[f]
        prev = rngs.loc[:s_f]
        if len(prev) < 20:
            continue
        atr = float(prev.iloc[-20:].mean())
        if not atr > 0:
            continue
        g = (o[i] - c[f]) / atr
        exit_date = (idx[i] + pd.Timedelta(hours=7)).normalize()   # the session's trading date
        row = {"week_start": idx[i], "g": g, "entry": o[i + 1], "entry_t": int(tsec[i + 1]), "F_t": int(tsec[f] + 300)}
        for name, (hh, mm, kind) in X_TIMES.items():
            xt = exit_date + pd.Timedelta(hours=hh, minutes=mm)
            if kind == "open":
                j = int(np.searchsorted(idx.asi8, xt.value, side="left"))
                ok = j < len(o) and did[j] == did[i] and j > i + 1
                px, jt = (o[j], int(tsec[j])) if ok else (np.nan, 0)
            else:
                j = int(np.searchsorted(idx.asi8, xt.value, side="left")) - 1
                ok = j > i + 1 and did[j] == did[i]
                px, jt = (c[j], int(tsec[j] + 300)) if ok else (np.nan, 0)
            if ok and len(sw) and ((sw > row["F_t"]) & (sw <= jt)).any():
                px = np.nan                              # a true roll switch inside the hold: skip (calendar rule)
            row[name] = px
            row[name + "_date"] = exit_date
        ev.append(row)
    return pd.DataFrame(ev)


def wknd_trades(ev, inst, k, xname, direction, cost_add=0.0, dirs=None):
    e = ev[(np.abs(ev["g"]) >= k) & (ev["g"] != 0) & np.isfinite(ev[xname])]
    sgn = np.sign(e["g"].to_numpy()) * direction if dirs is None else dirs[e.index.to_numpy()]
    pts = sgn * (e[xname].to_numpy() - e["entry"].to_numpy()) - (COST[inst] + cost_add)
    return pd.DataFrame({"date": pd.to_datetime(e[xname + "_date"].dt.tz_localize(None)), "pnl": pts * MULT[inst]})


def daily_from_trades(tr):
    return tr.groupby("date")["pnl"].sum().sort_index()


# ---------------------------------------------------------------- FAMILY F: FOMC-cycle weeks
def fomc_days():
    ds = [l.strip() for l in open(os.path.join(REPO, "tools", "data", "fomc_dates.txt"), encoding="utf-8")
          if l.strip() and not l.startswith("#")]
    return pd.to_datetime(ds)


def week_of(d):
    if d < -1:
        return 7
    if d <= 3:
        return 0
    return min(7, 1 + (d - 4) // 5)


def daily_closes(inst):
    a = load(inst, "rth", "db_adj_rth")
    idx, c = a["index"], a["close"]
    s = pd.Series(c, index=idx)
    s = s[s.index.hour * 60 + s.index.minute < 16 * 60]
    dc = s.groupby(s.index.tz_localize(None).normalize()).last()
    return dc


def cycle_days(dates, shifts=None):
    """cycle day d for each trading date; shifts: optional per-cycle int shift (null)."""
    f = fomc_days()
    pos = np.searchsorted(dates.values, f.values)            # ordinal of each FOMC day (next trading day if absent)
    pos = np.unique(pos[(pos >= 0) & (pos < len(dates))])
    d = np.full(len(dates), -99, dtype=int)
    cyc = np.full(len(dates), -1, dtype=int)
    for ci, p in enumerate(pos):
        end = pos[ci + 1] - 1 if ci + 1 < len(pos) else len(dates)       # day before next FOMC is d=-1 of next
        lo = p - 1 if ci == 0 else p                                    # the day before this FOMC set below
        for t in range(max(p - 1, 0), min(end, len(dates))):
            d[t] = t - p
            cyc[t] = ci
        if ci + 1 < len(pos) and pos[ci + 1] - 1 >= 0:
            t = pos[ci + 1] - 1
            d[t] = -1
            cyc[t] = ci + 1
    if shifts is not None:
        dd_ = d.copy()
        for t in range(len(d)):
            if cyc[t] >= 0:
                dd_[t] = d[t] - shifts[cyc[t] % len(shifts)]
        d = dd_
    return d, cyc


def fomc_leg(dc, inst, weeks, cost_add=0.0, shifts=None):
    dates = dc.index
    d, cyc = cycle_days(dates, shifts)
    w = np.array([week_of(x) if x > -99 else 7 for x in d])
    inpos = np.isin(w, list(weeks)) & (d > -99)
    ret = dc.diff().fillna(0.0).to_numpy()
    daily = np.where(inpos, ret, 0.0) * MULT[inst]
    # blocks: contiguous in-position days; one round trip each, charged on the block's last day
    trades = []
    t = 0
    n = len(inpos)
    while t < n:
        if inpos[t]:
            u = t
            while u + 1 < n and inpos[u + 1]:
                u += 1
            c = (COST[inst] + cost_add) * MULT[inst]
            daily[u] -= c
            trades.append((dates[u], float(daily[t:u + 1].sum())))
            t = u + 1
        else:
            t += 1
    return pd.DataFrame(trades, columns=["date", "pnl"]), pd.Series(daily, index=dates)


def always_long(dc, inst):
    ret = dc.diff().fillna(0.0) * MULT[inst]
    ret.iloc[-1] -= COST[inst] * MULT[inst]
    return pd.DataFrame([(dc.index[-1], float(ret.sum()))], columns=["date", "pnl"]), ret


# ---------------------------------------------------------------- run
def main():
    res = {"W": {}, "F": {}, "null": {}}
    first = {}
    # ---- W
    ev = {inst: wknd_events(inst) for inst in ("NQ", "ES")}
    for inst in ev:
        ev[inst].to_csv(os.path.join(OUT, f"wknd_events_{inst}.csv"), index=False)
        first[inst] = ev[inst]["week_start"].min()
    cells = [(inst, k, x) for inst in ("NQ", "ES") for k in KS for x in X_TIMES]
    for inst, k, x in cells:
        for dname, dirn in (("cont", 1), ("fade", -1)):
            tr = wknd_trades(ev[inst], inst, k, x, dirn)
            tr_s = wknd_trades(ev[inst], inst, k, x, dirn, cost_add=STRESS)
            dl = daily_from_trades(tr)
            t0e = pd.Timestamp(first[inst].tz_localize(None).normalize())
            r = {"WF": stretch_stats(tr, dl, WF0, LB0.tz_localize(None)),
                 "EARLY": stretch_stats(tr, dl, t0e, WF0),
                 "WF_stress_net": float(tr_s[(tr_s["date"] >= WF0)]["pnl"].sum())}
            res["W"][f"{inst}|k{k}|{x}|{dname}"] = r
    # family-wide null: coin per (instrument, week), max WF t over the 18 continuation cells
    null_max = []
    for rep in range(NREP):
        coins = {inst: rng.choice([-1.0, 1.0], size=len(ev[inst])) for inst in ev}
        best = -np.inf
        for inst, k, x in cells:
            tr = wknd_trades(ev[inst], inst, k, x, 1, dirs=coins[inst])
            t = tr[tr["date"] >= WF0]["pnl"]
            if len(t) > 1 and t.std(ddof=1) > 0:
                best = max(best, float(t.mean() / (t.std(ddof=1) / np.sqrt(len(t)))))
        null_max.append(best)
    res["null"]["W_tmax"] = {"p95": float(np.percentile(null_max, 95)), "median": float(np.median(null_max))}
    # ---- F
    dcs = {inst: daily_closes(inst) for inst in ("NQ", "ES")}
    ncyc = len(fomc_days())
    for inst, dc in dcs.items():
        t0e = dc.index[0]
        for name, weeks in (("even", (0, 2, 4, 6)), ("odd", (1, 3, 5, 7)), ("week0", (0,))):
            tr, dl = fomc_leg(dc, inst, weeks)
            tr_s, _ = fomc_leg(dc, inst, weeks, cost_add=STRESS)
            res["F"][f"{inst}|{name}"] = {"WF": stretch_stats(tr, dl, WF0, LB0.tz_localize(None)),
                                          "EARLY": stretch_stats(tr, dl, t0e, WF0),
                                          "WF_stress_net": float(tr_s[tr_s["date"] >= WF0]["pnl"].sum())}
        tr, dl = always_long(dc, inst)
        wf = dl[(dl.index >= WF0)]
        yrs = (LB0.tz_localize(None) - WF0).days / 365.25
        ddv = dd(wf.values)
        res["F"][f"{inst}|always_long"] = {"WF": {"net": float(wf.sum()), "dd_daily": ddv,
                                                  "roc30": 30.0 * (float(wf.sum()) / yrs) / ddv,
                                                  "sharpe": float(wf.mean() / wf.std(ddof=1) * np.sqrt(252))}}
        sh = []
        for rep in range(NREP):
            shifts = rng.integers(0, 10, size=ncyc + 5)
            _, dl0 = fomc_leg(dc, inst, (0, 2, 4, 6), shifts=shifts)
            x = dl0[dl0.index >= WF0]
            sh.append(float(x.mean() / x.std(ddof=1) * np.sqrt(252)))
        res["null"][f"F_{inst}_sharpe"] = {"p95": float(np.percentile(sh, 95)), "median": float(np.median(sh))}
    json.dump(res, open(os.path.join(OUT, "r4_stageA.json"), "w"), indent=1, default=str)

    # ---- verdicts (pre-registered Stage A)
    def passes_common(r):
        w, e = r["WF"], r["EARLY"]
        return (w["n"] >= 100 and w["roc30"] >= 15 and w["pf"] >= 1.10 and r["WF_stress_net"] > 0
                and w["net_ex_big"] > 0 and w["years_pos"] >= 0.60 and e["net"] > 0)
    out = []
    p95 = res["null"]["W_tmax"]["p95"]
    for key, r in res["W"].items():
        w = r["WF"]
        ok = key.endswith("cont") and passes_common(r) and w["t"] >= 2.0 and w["t"] > p95
        out.append(("W", key, w["n"], w["net"], w["pf"], w["roc30"], w["t"], w["years_pos"], r["EARLY"]["net"], ok))
    for key, r in res["F"].items():
        if key.endswith("always_long"):
            continue
        w = r["WF"]
        inst = key.split("|")[0]
        ok = (key.endswith("even") and passes_common(r) and w["sharpe"] > res["null"][f"F_{inst}_sharpe"]["p95"]
              and w["roc30"] > res["F"][f"{inst}|always_long"]["WF"]["roc30"])
        out.append(("F", key, w["n"], w["net"], w["pf"], w["roc30"], w.get("sharpe"), w["years_pos"], r["EARLY"]["net"], ok))
    df = pd.DataFrame(out, columns=["fam", "cell", "wf_n", "wf_net", "wf_pf", "wf_roc30", "wf_t_or_sharpe", "wf_years_pos", "early_net", "PASS"])
    df.to_csv(os.path.join(OUT, "r4_stageA_table.csv"), index=False)
    pd.set_option("display.width", 200)
    print(df.round(3).to_string(index=False))
    print("W null max-t p95:", round(p95, 3), "median", round(res["null"]["W_tmax"]["median"], 3))
    for inst in ("NQ", "ES"):
        print(f"F {inst}: null Sharpe p95 {res['null'][f'F_{inst}_sharpe']['p95']:.3f} | always-long WF roc30 "
              f"{res['F'][f'{inst}|always_long']['WF']['roc30']:.1f} Sharpe {res['F'][f'{inst}|always_long']['WF']['sharpe']:.2f}")


if __name__ == "__main__":
    main()

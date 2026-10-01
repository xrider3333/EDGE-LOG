# Round 6 (2026-09-30): REVERT r1 - fade a failed new high / low of the day.
# Pre-registered: tools/rocfrontier/PREREG_REVERT_R1.txt (sha256 542f1701...ac84, main a42f8b74), written before
# any outcome was computed.
#   python r6_revert.py P          Part P Stage A (+ A2 if a cell passes), PRE-LOCKBOX ONLY
#   python r6_revert.py B          Part P Stage B (lockbox, once) - refuses unless A2 passed
#   python r6_revert.py F hist     Part F historical read (descriptive only, sessions before 2026-09-30)
#   python r6_revert.py F forward  Part F forward shadow: trade COUNTS until 150 pooled variant trades, then the read
# Run from anywhere; imports augur_engine from the shared checkout (EDGELOG_ROOT overrides).
import json, os, sys
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO); os.chdir(REPO)
import numpy as np, pandas as pd

OUT = os.environ.get("EDGELOG_ROCFRONTIER_R6", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r6")   # results stay outside git
CAP = os.environ.get("EDGELOG_OHLC", r"C:\EdgeLog\ohlc")
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")
LB0 = pd.Timestamp("2025-06-30", tz="US/Eastern")        # lockbox start - Part P loads nothing on/after it
WF0, LBN, LB1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-30"), pd.Timestamp("2026-06-30")
BW0 = pd.Timestamp("2010-06-07")                          # BOOK #463 window start
HIST0, FWD0 = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-10-01")   # history read starts after BOOK #463's lockbox (audit 09-30)
BOOK_FWD = os.environ.get("EDGELOG_BOOK463_FORWARD", os.path.join(os.path.dirname(OUT), "r4", "book463_forward_daily.csv"))  # F5 input: date, pnl
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.533, "ES": 0.363}
TICK, STRESS, HOLD = 0.25, 0.25, 6
W_FIRST, W_LAST = 600, 925                                # signal bar starts 10:00 .. 15:25 (minutes after midnight)
NREP, NPERM, FWD_N = 500, 2000, 150
rng = np.random.default_rng(20260930)


# ------------------------------------------------------------------ rule (shared by both parts)
def candidates(o, h, l, c, tmin):
    """Per session arrays in time order. Returns (short, long) boolean candidate masks."""
    prev_hi = np.concatenate([[np.inf], np.maximum.accumulate(h)[:-1]])
    prev_lo = np.concatenate([[-np.inf], np.minimum.accumulate(l)[:-1]])
    win = (tmin >= W_FIRST) & (tmin <= W_LAST)
    return win & (h > prev_hi) & (c < o), win & (l < prev_lo) & (c > o)


def sim(o, h, l, c, k, d):
    """One trade from signal bar k, direction d (+1 long / -1 short). Returns (exit_idx, gross points) or None."""
    n = len(o)
    if k + 1 >= n:
        return None
    stop = h[k] + TICK if d < 0 else l[k] - TICK
    e = o[k + 1]
    if (d < 0 and e >= stop) or (d > 0 and e <= stop):
        return None
    last = min(k + HOLD, n - 1)
    for j in range(k + 1, last + 1):
        if d < 0 and h[j] >= stop:
            return j, e - max(stop, o[j])
        if d > 0 and l[j] <= stop:
            return j, min(stop, o[j]) - e
    return last, d * (c[last] - e)


def session_trades(o, h, l, c, sig, mirror=False):
    """sig: list of (k, d) in time order (d = the FADE direction). Returns (leg trades, per-signal trades):
    lists of (k, d_traded, gross). The leg keeps one position at a time; mirror trades the opposite side
    (continuation control) with the stop on the other side of the signal bar."""
    leg, per, busy = [], [], -1
    for k, d in sig:
        dd_ = -d if mirror else d
        r = sim(o, h, l, c, k, dd_)
        if r is None:
            continue
        per.append((k, dd_, r[1]))
        if k >= busy:
            leg.append((k, dd_, r[1]))
            busy = r[0]
    return leg, per


# ------------------------------------------------------------------ statistics
def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stats(tr, days, yrs):
    """tr: DataFrame(date, pnl $ net); days: DatetimeIndex of the stretch's trading days (zeros included)."""
    n = len(tr)
    daily = tr.groupby("date")["pnl"].sum().reindex(days).fillna(0.0) if n else pd.Series(0.0, index=days)
    net = float(tr["pnl"].sum()) if n else 0.0
    gw = float(tr["pnl"][tr["pnl"] > 0].sum()) if n else 0.0
    gl = float(-tr["pnl"][tr["pnl"] < 0].sum()) if n else 0.0
    ddv = ddmax(daily.values)
    mar = (net / yrs) / ddv if ddv > 0 else float("nan")
    sd = float(tr["pnl"].std(ddof=1)) if n > 1 else float("nan")
    by_year = tr.groupby(tr["date"].dt.year)["pnl"].sum() if n else pd.Series(dtype=float)
    return {"n": n, "net": net, "per_trade": net / n if n else float("nan"), "win": float((tr["pnl"] > 0).mean()) if n else float("nan"),
            "pf": gw / gl if gl > 0 else float("inf"), "dd_daily": ddv, "mar": mar, "roc30": 30.0 * mar,
            "t": float(tr["pnl"].mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
            "years_pos": float((by_year > 0).mean()) if len(by_year) else 0.0,
            "net_ex_big": net - (float(tr["pnl"].max()) if n else 0.0), "sortino": so(daily.values)}


def to_df(rows, inst, cost_add=0.0):
    df = pd.DataFrame(rows, columns=["date", "k", "d", "gross"])
    df["pnl"] = (df["gross"] - COST[inst] - cost_add) * MULT[inst]
    df["inst"] = inst
    return df


# ------------------------------------------------------------------ PART P: masters, pre-lockbox
def load_master(inst, lockbox=False):
    from augur_engine import data
    m = data.find_master(inst, "5m", "rth", "db_adj_rth")
    assert m is not None, f"no ADJ RTH master for {inst}"
    a = data.load_master_arrays(m, "2010-06-01", "2026-07-01" if lockbox else "2025-06-29")
    idx = a["index"]
    keep = np.asarray(idx >= LB0) & np.asarray(idx < pd.Timestamp("2026-07-01", tz="US/Eastern")) if lockbox else np.asarray(idx < LB0)
    if not lockbox:
        assert idx[keep].max() < LB0
    df = pd.DataFrame({k: np.asarray(a[k], float)[keep] for k in ("open", "high", "low", "close")}, index=idx[keep])
    tm = df.index.hour * 60 + df.index.minute
    return df[(tm >= 570) & (tm < 960)]


def by_session(df):
    """Yields (date, o, h, l, c, tmin) per ET session date."""
    if len(df) == 0:
        return
    tm = (df.index.hour * 60 + df.index.minute).to_numpy()
    dates = df.index.tz_localize(None).normalize()
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    cut = np.flatnonzero(np.diff(dates.asi8)) + 1
    for a, b in zip(np.concatenate([[0], cut]), np.concatenate([cut, [len(df)]])):
        yield dates[a], o[a:b], h[a:b], l[a:b], c[a:b], tm[a:b]


def part_p_trades(df):
    out = {"fade": [], "cont": []}
    for day, o, h, l, c, tm in by_session(df):
        s, L = candidates(o, h, l, c, tm)
        sig = sorted([(k, -1) for k in np.flatnonzero(s)] + [(k, 1) for k in np.flatnonzero(L)])
        for name, mir in (("fade", False), ("cont", True)):
            leg, _ = session_trades(o, h, l, c, sig, mirror=mir)
            out[name] += [(day, k, d, g) for k, d, g in leg]
    return out


def part_p():
    res, trades, days = {}, {}, {}
    for inst in ("NQ", "ES"):
        df = load_master(inst)
        days[inst] = pd.DatetimeIndex(sorted(set(df.index.tz_localize(None).normalize())))
        t = part_p_trades(df)
        for name in t:
            trades[(inst, name)] = t[name]
    for (inst, name), rows in trades.items():
        dfx, dfs = to_df(rows, inst), to_df(rows, inst, STRESS)
        dfx.to_csv(os.path.join(OUT, f"P_{inst}_{name}_trades.csv"), index=False)
        d = days[inst]
        wf, ea = d[(d >= WF0) & (d < LBN)], d[d < WF0]
        res[f"{inst}|{name}"] = {"WF": stats(dfx[dfx.date >= WF0], wf, (LBN - WF0).days / 365.25),
                                 "EARLY": stats(dfx[dfx.date < WF0], ea, (WF0 - d[0]).days / 365.25),
                                 "WF_stress_net": float(dfs[dfs.date >= WF0]["pnl"].sum())}
    # family-wide null: random sign on each WF fade trade's gross points, cost re-applied, max t over the 2 cells
    gw = {inst: to_df(trades[(inst, "fade")], inst) for inst in ("NQ", "ES")}
    gw = {inst: g[g.date >= WF0]["gross"].to_numpy() for inst, g in gw.items()}
    null = []
    for _ in range(NREP):
        best = -np.inf
        for inst, g in gw.items():
            x = (rng.choice([-1.0, 1.0], size=len(g)) * g - COST[inst]) * MULT[inst]
            best = max(best, float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))))
        null.append(best)
    res["null_tmax"] = {"p95": float(np.percentile(null, 95)), "median": float(np.median(null))}
    rows, passes = [], []
    for inst in ("NQ", "ES"):
        for name in ("fade", "cont"):
            r = res[f"{inst}|{name}"]; w = r["WF"]
            ok = (name == "fade" and w["n"] >= 100 and w["roc30"] >= 15 and w["pf"] >= 1.10 and w["t"] >= 2.0
                  and w["t"] > res["null_tmax"]["p95"] and r["WF_stress_net"] > 0 and w["net_ex_big"] > 0
                  and w["years_pos"] >= 0.60 and r["EARLY"]["net"] > 0)
            rows.append((f"P-{inst}" + ("" if name == "fade" else " control (continuation)"), w["n"], w["net"], w["per_trade"],
                         w["win"], w["pf"], w["dd_daily"], w["roc30"], w["sortino"], w["t"], w["years_pos"],
                         r["WF_stress_net"], w["net_ex_big"], r["EARLY"]["net"], ok))
            if ok:
                passes.append(inst)
    tab = pd.DataFrame(rows, columns=["cell", "wf_n", "wf_net", "per_trade", "win", "pf", "dd_daily", "roc30", "sortino",
                                      "t", "years_pos", "stress_net", "net_ex_big", "early_net", "PASS"])
    tab.to_csv(os.path.join(OUT, "P_stageA_table.csv"), index=False)
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string(index=False))
    print("null max-t p95 %.3f (median %.3f)" % (res["null_tmax"]["p95"], res["null_tmax"]["median"]))
    res["stageA_pass"] = passes
    res["A2"] = stage_a2(passes, trades) if passes else None
    json.dump(res, open(os.path.join(OUT, "P_stageA.json"), "w"), indent=1, default=str)
    print("Stage A passes:", passes or "none - Part P dead; lockbox stays sealed")


def book_eval(extra, pre=True):
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    M = b["mtm"].copy()
    C = b["close"].copy()
    if extra is not None:
        e = extra.reindex(M.index.union(extra.index)).fillna(0.0)
        M = M.reindex(e.index).fillna(0.0) + e
        C = C.reindex(e.index).fillna(0.0) + e
    sel = (M.index >= BW0) & (M.index < LBN) if pre else (M.index >= LBN) & (M.index <= LB1)   # LB includes 2026-06-30 (frontier definition)
    yrs = ((LBN - BW0) if pre else (LB1 - LBN)).days / 365.25
    net = float(C[sel].sum())
    ddv = ddmax(M[sel].values)
    return {"net": net, "roc": net / yrs / 1000, "dd_daily": ddv, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values)}


def stage_a2(passes, trades):
    base = book_eval(None)
    print("BOOK #463 pre (check 60.34 / 3.153): ROC@30k %.2f Sortino %.3f" % (base["roc30"], base["sortino"]))
    if not (abs(base["roc30"] - 60.34) < 0.006 and abs(base["sortino"] - 3.153) < 0.0006):
        print("A2 NOT judged: the book file does not reproduce #463's pre numbers")
        return {"base": base, "cells": passes, "pass": False, "error": "book check mismatch"}
    leg = pd.concat([to_df(trades[(i, "fade")], i) for i in passes])
    daily = leg.groupby("date")["pnl"].sum()
    out = {"base": base, "cells": passes, "by_c": {}}
    for cc in (1, 2, 3):
        out["by_c"][cc] = book_eval(daily * cc)
    cbest = max(out["by_c"], key=lambda k: out["by_c"][k]["roc30"])
    r = out["by_c"][cbest]
    out["c"] = cbest
    out["pass"] = bool(r["roc30"] >= 63.36 and r["sortino"] >= 3.153)
    for cc, v in out["by_c"].items():
        print(f"  #463 + REVERT x{cc}: pre ROC@30k {v['roc30']:.2f} Sortino {v['sortino']:.3f} DD ${v['dd_daily']:,.0f}")
    print("A2:", "PASS at c=%d" % cbest if out["pass"] else "FAIL (needs >= 63.36 and Sortino >= 3.153)")
    return out


def part_b():
    pa = os.path.join(OUT, "P_stageA.json")
    res = json.load(open(pa)) if os.path.exists(pa) else {}
    if not (res.get("A2") or {}).get("pass"):
        print("Stage B refused: no Stage A2 pass on file - the lockbox stays sealed.")
        return
    flag = os.path.join(OUT, "P_stageB_READ.flag")
    if os.path.exists(flag):
        print("Stage B refused: the lockbox was already read once."); return
    base = book_eval(None, pre=False)
    if not (abs(base["roc30"] - 164.76) < 0.006 and abs(base["sortino"] - 4.150) < 0.0006):
        print("Stage B refused: the book file does not reproduce #463's LB numbers (lockbox NOT read)"); return
    cc, cells = int(res["A2"]["c"]), res["A2"]["cells"]
    dfs = {inst: load_master(inst, lockbox=True) for inst in cells}    # load first; a crash here leaves the lockbox unread
    open(flag, "w").write(pd.Timestamp.now().isoformat())            # the one read starts here
    legs = []
    for inst in cells:
        t = part_p_trades(dfs[inst])["fade"]
        legs.append(to_df(t, inst))
    leg = pd.concat(legs)
    daily = leg.groupby("date")["pnl"].sum() * cc
    r = book_eval(daily, pre=False)
    b = pd.read_csv(os.path.join(os.path.dirname(BOOK), "book463_trades.csv"), parse_dates=["date"])
    big = max(float(b[b.date >= LBN]["pnl"].max()), float((leg["pnl"] * cc).max()))
    ok = r["roc30"] >= 164.76 and r["sortino"] >= 4.150 and r["net"] - big > 0 and leg["pnl"].sum() > 0 and len(leg) >= 50
    print(f"Stage B: book LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} | leg LB trades {len(leg)} net ${leg['pnl'].sum()*cc:,.0f} -> {'PASS' if ok else 'FAIL'}")
    json.dump({"B": r, "leg_n": len(leg), "leg_net": float(leg['pnl'].sum() * cc), "pass": bool(ok)}, open(os.path.join(OUT, "P_stageB.json"), "w"), indent=1)


# ------------------------------------------------------------------ PART F: the 10-second capture
def load_capture(inst):
    raw = pd.read_csv(os.path.join(CAP, f"{inst}_10s.csv"))
    raw = raw.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    st = pd.to_datetime(raw["time"] - 10, unit="s", utc=True).dt.tz_convert("US/Eastern")
    tm = (st.dt.hour * 60 + st.dt.minute).to_numpy()
    raw["st"], raw["sess"] = st, st.dt.tz_localize(None).dt.normalize()
    raw["rel_jump"] = (raw["open"] / raw["close"].shift() - 1).abs()
    x = raw[(tm >= 570) & (tm < 960)].copy()
    x["bs"] = x["buy_vol"] + x["sell_vol"]
    x["hasd"] = x["bs"] > 0
    x["vb"] = x["volume"] > 0
    q = x.groupby("sess").agg(n=("time", "size"), cov=("hasd", "mean"), jump=("rel_jump", "max"))
    usable = q[(q["n"] >= 2000) & (q["cov"] >= 0.80) & (q["jump"].fillna(0) <= 0.005)].index
    x = x[x["sess"].isin(usable)]
    x["b5"] = x["st"].dt.floor("5min")
    x["vbd"] = x["vb"] & x["hasd"]
    b = x.groupby("b5").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                            d=("delta", "sum"), bs=("bs", "sum"), vb=("vb", "sum"), vbd=("vbd", "sum"))
    ok = (b["bs"] > 0) & (b["vbd"] >= 0.80 * b["vb"].clip(lower=1))
    b["ds"] = np.where(ok, b["d"] / b["bs"].where(b["bs"] > 0), np.nan)
    return b, pd.DatetimeIndex(sorted(usable))


def part_f_trades(b, d0, d1):
    """Trades on usable sessions with d0 <= date < d1. Returns dict of DataFrames: twin/var legs, twin/var per-signal."""
    out = {k: [] for k in ("twin_leg", "var_leg", "twin_sig", "var_sig")}
    sub = b[(b.index.tz_localize(None).normalize() >= d0) & (b.index.tz_localize(None).normalize() < d1)]
    for day, o, h, l, c, tm in by_session(sub):
        ds = sub["ds"].to_numpy()[(sub.index.tz_localize(None).normalize() == day)]
        s, L = candidates(o, h, l, c, tm)
        sig = sorted([(k, -1) for k in np.flatnonzero(s)] + [(k, 1) for k in np.flatnonzero(L)])
        var = [(k, d) for k, d in sig if np.isfinite(ds[k]) and ((d < 0 and ds[k] > 0) or (d > 0 and ds[k] < 0))]
        dsdef = [(k, d) for k, d in sig if np.isfinite(ds[k])]
        leg, _ = session_trades(o, h, l, c, sig)
        _, per_def = session_trades(o, h, l, c, dsdef)
        vleg, vper = session_trades(o, h, l, c, var)
        vkeys = {(k, d) for k, d in var}
        out["twin_leg"] += [(day, k, d, g) for k, d, g in leg]
        out["var_leg"] += [(day, k, d, g) for k, d, g in vleg]
        out["twin_sig"] += [(day, k, d, g) for k, d, g in per_def]           # DS-defined candidates only (F3 pool)
        out["var_sig"] += [(day, k, d, g) for k, d, g in vper]
    return out


def part_f(mode):
    today = pd.Timestamp.now(tz="US/Eastern").tz_localize(None).normalize()
    d0, d1 = (HIST0, pd.Timestamp("2026-09-30")) if mode == "hist" else (FWD0, today)
    per, legs, sessions = {}, {}, {}
    for inst in ("NQ", "ES"):
        b, usable = load_capture(inst)
        sessions[inst] = usable[(usable >= d0) & (usable < d1)]
        t = part_f_trades(b, d0, d1)
        for k, rows in t.items():
            per[(inst, k)] = to_df(rows, inst)
    nvar = sum(len(per[(i, "var_leg")]) for i in ("NQ", "ES"))
    print(f"PART F {mode}: usable sessions NQ {len(sessions['NQ'])} ES {len(sessions['ES'])} | pooled variant leg trades {nvar}"
          f" (NQ {len(per[('NQ', 'var_leg')])}, ES {len(per[('ES', 'var_leg')])}) | twin leg trades "
          f"{sum(len(per[(i, 'twin_leg')]) for i in ('NQ', 'ES'))}")
    if mode == "forward" and nvar < FWD_N:
        print(f"FORWARD SHADOW: {nvar}/{FWD_N} pooled variant trades - not read yet (counts only, by pre-registration).")
        return
    fflag = os.path.join(OUT, "F_forward_READ.flag")
    if mode == "forward" and os.path.exists(fflag):                  # read ONCE: later runs show the frozen verdict
        fr = json.load(open(os.path.join(OUT, "F_forward.json")))
        print(f"FORWARD SHADOW already read on {open(fflag).read()[:10]}: bars {fr.get('bars')} -> {'PASS' if fr.get('PASS') else 'FAIL'} (frozen)")
        return
    days = pd.DatetimeIndex(sorted(set(sessions["NQ"]) | set(sessions["ES"])))
    yrs = max((days[-1] - days[0]).days + 1, 1) / 365.25
    res = {"mode": mode, "sessions": {i: len(sessions[i]) for i in sessions}}
    for name in ("var", "twin"):
        leg = pd.concat([per[(i, f"{name}_leg")] for i in ("NQ", "ES")])
        legs[name] = leg
        res[name] = stats(leg, days, yrs)
        res[name + "_stress_net"] = float(sum(((per[(i, f"{name}_leg")]["gross"] - COST[i] - STRESS) * MULT[i]).sum() for i in ("NQ", "ES")))
        for i in ("NQ", "ES"):
            res[f"{name}_{i}"] = stats(per[(i, f"{name}_leg")], pd.DatetimeIndex(sessions[i]), yrs)
            res[f"{name}_{i}_sig_mean"] = float(per[(i, f"{name}_sig")]["pnl"].mean()) if len(per[(i, f"{name}_sig")]) else float("nan")
    # F3: within-session same-size draws from the twin's DS-defined candidates (per-signal view), pooled over markets
    pools = []
    for i in ("NQ", "ES"):
        tw, vs = per[(i, "twin_sig")], per[(i, "var_sig")]
        cnt = vs.groupby("date").size()
        for day, g in tw.groupby("date"):
            m = int(cnt.get(day, 0))
            if m:
                pools.append((g["pnl"].to_numpy(), m))
    actual = float(pd.concat([per[(i, "var_sig")] for i in ("NQ", "ES")])["pnl"].mean())
    draws = []
    for _ in range(NPERM):
        s, n = 0.0, 0
        for arr, m in pools:
            pick = rng.choice(arr, size=min(m, len(arr)), replace=False)
            s += pick.sum(); n += len(pick)
        draws.append(s / n if n else np.nan)
    res["F3"] = {"variant_sig_mean": actual, "p95": float(np.nanpercentile(draws, 95)), "pct": float(np.mean(np.array(draws) < actual))}
    v, t = res["var"], res["twin"]
    f = {"F1": bool(v["roc30"] > t["roc30"] and v["sortino"] > t["sortino"]),
         "F2": bool(v["net"] > 0 and res["var_stress_net"] > 0 and v["net_ex_big"] > 0),
         "F3": bool(actual >= res["F3"]["p95"]),
         "F4": bool(all(res[f"var_{i}_sig_mean"] > res[f"twin_{i}_sig_mean"] for i in ("NQ", "ES")))}
    f5 = None                                                         # F5: #463 + the variant (1 contract a market) on the same days
    if mode == "forward" and os.path.exists(BOOK_FWD):
        bf = pd.read_csv(BOOK_FWD, parse_dates=["date"]).set_index("date")["pnl"]
        span = pd.DatetimeIndex(sorted(set(bf.index[(bf.index >= FWD0) & (bf.index <= days[-1])]) | set(days)))
        b0 = bf.reindex(span).fillna(0.0)
        b1 = b0 + legs["var"].groupby("date")["pnl"].sum().reindex(span).fillna(0.0)
        roc = lambda x: 30.0 * (x.sum() / yrs) / ddmax(x.values) if ddmax(x.values) > 0 else float("nan")
        f5 = bool(roc(b1) > roc(b0) and so(b1.values) > so(b0.values))
        res["F5_detail"] = {"book_roc30": roc(b0), "book_sortino": so(b0.values), "with_roc30": roc(b1), "with_sortino": so(b1.values)}
    f["F5"] = f5                                                      # None = not available (reported as such)
    res["bars"] = f
    res["PASS"] = bool(all(v for k, v in f.items() if v is not None))
    for name in ("var", "twin"):
        s_ = res[name]
        print(f"  {name:4s} pooled: n {s_['n']} net ${s_['net']:,.0f} (${s_['per_trade']:,.1f}/trade, win {s_['win']:.0%}) "
              f"DD ${s_['dd_daily']:,.0f} ROC@30k {s_['roc30']:.1f} Sortino {s_['sortino']:.2f} | stress ${res[name + '_stress_net']:,.0f} | ex-biggest ${s_['net_ex_big']:,.0f}")
        for i in ("NQ", "ES"):
            q = res[f"{name}_{i}"]
            print(f"      {i}: leg n {q['n']} net ${q['net']:,.0f} | per-signal mean ${res[f'{name}_{i}_sig_mean']:,.1f}")
    print(f"  F3 tag test: variant per-signal mean ${actual:,.1f} vs draws p95 ${res['F3']['p95']:,.1f} (percentile {res['F3']['pct']:.0%})")
    print("  bars:", f, "(F5 None = #463 forward dailies not available) ->", "PASS" if res["PASS"] else "FAIL",
          "| DESCRIPTIVE ONLY - decides nothing" if mode == "hist" else "")
    for k, df in per.items():
        df.to_csv(os.path.join(OUT, f"F_{mode}_{k[0]}_{k[1]}.csv"), index=False)
    json.dump(res, open(os.path.join(OUT, f"F_{mode}.json"), "w"), indent=1, default=str)
    if mode == "forward":
        open(fflag, "w").write(pd.Timestamp.now().isoformat())       # the one forward read is done


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    a = sys.argv[1:]
    if a[:1] == ["P"]:
        part_p()
    elif a[:1] == ["B"]:
        part_b()
    elif a[:1] == ["F"] and a[1:2] in (["hist"], ["forward"]):
        part_f(a[1])
    else:
        print(__doc__ or "usage: r6_revert.py P | B | F hist | F forward")

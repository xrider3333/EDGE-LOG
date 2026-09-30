# Round 7 (2026-09-30): VOLCARRY r1 - the volatility risk premium as a new leg for BOOK #463.
# Pre-registered: tools/rocfrontier/PREREG_VOLCARRY_R1.txt, written before any of its data was fetched.
#   python r7_volcarry.py fetch --owner-ok   one-time free Yahoo daily pull (VIXY, SVXY, ^VIX, ^VIX3M) -> cache + sha256
#   python r7_volcarry.py A                  parity check, Stage A (+ A2 if a cell passes), PRE-LOCKBOX ONLY
#   python r7_volcarry.py B                  Stage B (lockbox, once) - refuses unless A2 passed
import hashlib, json, os, sys
import numpy as np, pandas as pd

OUT = os.environ.get("EDGELOG_ROCFRONTIER_R7", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r7")    # results stay outside git
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")
TICKERS = ("VIXY", "SVXY", "^VIX", "^VIX3M")
E0, WF0, LB0, LB1 = (pd.Timestamp(x) for x in ("2011-01-04", "2016-07-01", "2025-06-30", "2026-06-30"))
BW0 = pd.Timestamp("2010-06-07")                          # BOOK #463 window start
UNIT, FEE, SWITCH, STRESS = 100_000.0, 0.0095 / 252, 0.0005, 0.0015
CELLS = {"G100": 1.00, "G090": 0.90, "TWIN": None}
NREP = 500
rng = np.random.default_rng(20260930)


def fname(t):
    return os.path.join(OUT, t.replace("^", "IDX_") + ".csv")


def fetch():
    import yfinance as yf
    os.makedirs(OUT, exist_ok=True)
    sums = {}
    for t in TICKERS:
        df = yf.download(t, start="2010-12-01", end=pd.Timestamp.now().strftime("%Y-%m-%d"), interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        ix = pd.to_datetime(df.index)
        df.index = (ix.tz_convert(None) if ix.tz is not None else ix).normalize()
        df.index.name = "date"
        df.to_csv(fname(t))
        sums[t] = {"rows": len(df), "first": str(df.index[0].date()), "last": str(df.index[-1].date()),
                   "sha256": hashlib.sha256(open(fname(t), "rb").read()).hexdigest()}
        print(t, sums[t])
    json.dump(sums, open(os.path.join(OUT, "data_sha256.json"), "w"), indent=1)


def load(t0, t1):
    px = {t: pd.read_csv(fname(t), parse_dates=["date"]).set_index("date") for t in TICKERS}
    return {t: d[(d.index >= t0) & (d.index < t1)] for t, d in px.items()}


def synth(px):
    """Per VIXY day t: s_t (open t -> open t+1, -0.5x, fee) and ratio of the CBOE closes of the last day BEFORE t."""
    v = px["VIXY"]
    o = v["Open"]
    s = (-0.5 * (o.shift(-1) / o - 1.0) - FEE).dropna()          # the last day has no next open -> dropped
    vix, v3 = px["^VIX"]["Close"], px["^VIX3M"]["Close"]
    r = (vix / v3).dropna()
    prev = r.reindex(r.index.union(s.index)).ffill().shift(1)      # value known at the close before each day
    # shift(1) on the union index: for a VIXY day t it returns the ratio of the latest CBOE day < t
    ratio = prev.reindex(s.index)
    ok = ratio.notna()
    return s[ok], ratio[ok]


def leg(s, ratio, theta, switch=SWITCH):
    hold = pd.Series(1.0, index=s.index) if theta is None else (ratio < theta).astype(float)
    sw = hold.diff().abs().fillna(hold.iloc[0])
    return hold * UNIT * s - sw * UNIT * switch, hold


def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stats(p, hold, t0, t1):
    x, h = p[(p.index >= t0) & (p.index < t1)], hold[(hold.index >= t0) & (hold.index < t1)]
    yrs = (t1 - t0).days / 365.25
    net, ddv = float(x.sum()), ddmax(x.values)
    by_year = x.groupby(x.index.year).sum()
    return {"net": net, "dd_daily": ddv, "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 else float("nan"),
            "sortino": so(x.values), "years_pos": float((by_year > 0).mean()), "net_ex_best_day": net - float(x.max()),
            "held_days": int(h.sum()), "spells": int(((h.diff() == 1) | ((h.index == h.index[0]) & (h == 1))).sum()),
            "worst_day": [str(x.idxmin().date()), float(x.min())]}


def book_eval(extra, pre=True):
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    idx = b.index.union(extra.index) if extra is not None else b.index
    M, C = b["mtm"].reindex(idx).fillna(0.0), b["close"].reindex(idx).fillna(0.0)
    if extra is not None:
        e = extra.reindex(idx).fillna(0.0)
        M, C = M + e, C + e
    sel = (idx >= BW0) & (idx < LB0) if pre else (idx >= LB0) & (idx <= LB1)     # LB includes 2026-06-30 (frontier definition)
    yrs = ((LB0 - BW0) if pre else (LB1 - LB0)).days / 365.25
    net, ddv = float(C[sel].sum()), ddmax(M[sel].values)
    return {"net": net, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values), "dd_daily": ddv,
            "series": M[sel]}


def stage_a():
    px = load(pd.Timestamp("2010-12-01"), LB0)                   # PRE-LOCKBOX: nothing on/after 2025-06-30 is loaded
    assert all(d.index.max() < LB0 for d in px.values())
    s, ratio = synth(px)
    # parity: synthetic vs SVXY open-to-open after its -0.5x switch (all days, not gated)
    sv = px["SVXY"]["Open"]
    sv_r = (sv.shift(-1) / sv - 1.0).dropna()
    j = pd.concat([s + FEE, sv_r], axis=1, join="inner").dropna()
    j = j[j.index >= pd.Timestamp("2018-03-01")]
    par = float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1])
    print(f"parity: synthetic vs SVXY open-to-open, {len(j)} days since 2018-03-01, correlation {par:.4f}")
    if par < 0.98:
        print("PARITY FAILS (< 0.98) - test stops here by pre-registration.")
        json.dump({"parity": par, "stopped": True}, open(os.path.join(OUT, "stageA.json"), "w"), indent=1)
        return
    res, legs = {"parity": par}, {}
    for name, th in CELLS.items():
        p, h = leg(s, ratio, th)
        ps, _ = leg(s, ratio, th, switch=STRESS)
        legs[name] = (p, h)
        res[name] = {"WF": stats(p, h, WF0, LB0), "EARLY": stats(p, h, E0, WF0),
                     "WF_stress_net": float(ps[(ps.index >= WF0)].sum())}
    # null: circular shift of the ratio series, max WF Sortino over the gated cells
    n, null = len(ratio), []
    for _ in range(NREP):
        k = int(rng.integers(63, n - 63))
        rr = pd.Series(np.roll(ratio.values, k), index=ratio.index)
        best = -np.inf
        for name, th in CELLS.items():
            if th is not None:
                p, h = leg(s, rr, th)
                best = max(best, stats(p, h, WF0, LB0)["sortino"])
        null.append(best)
    res["null_sortino_max"] = {"p95": float(np.percentile(null, 95)), "median": float(np.median(null))}
    tw = res["TWIN"]["WF"]
    rows, passes = [], []
    for name in CELLS:
        r = res[name]; w, e = r["WF"], r["EARLY"]
        base = (w["roc30"] >= 15 and w["years_pos"] >= 0.60 and e["net"] > 0 and r["WF_stress_net"] > 0
                and w["net_ex_best_day"] > 0)
        if name == "TWIN":
            ok = base
        else:
            ok = (base and (w["spells"] >= 30 or w["held_days"] >= 250) and w["roc30"] > tw["roc30"]
                  and w["sortino"] > tw["sortino"] and w["sortino"] > res["null_sortino_max"]["p95"])
        rows.append((name, w["net"], w["dd_daily"], w["roc30"], w["sortino"], w["years_pos"], w["net_ex_best_day"],
                     r["WF_stress_net"], w["held_days"], w["spells"], w["worst_day"][0], w["worst_day"][1], e["net"], ok))
        if ok:
            passes.append(name)
    tab = pd.DataFrame(rows, columns=["cell", "wf_net", "dd_daily", "roc30", "sortino", "years_pos", "ex_best_day",
                                      "stress_net", "held_days", "spells", "worst_day", "worst_day_$", "early_net", "PASS"])
    tab.to_csv(os.path.join(OUT, "stageA_table.csv"), index=False)
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string(index=False))
    print("null max WF Sortino p95 %.3f (median %.3f)" % (res["null_sortino_max"]["p95"], res["null_sortino_max"]["median"]))
    res["stageA_pass"] = passes
    if passes:
        pick = max(passes, key=lambda c: (res[c]["WF"]["roc30"], c != "TWIN"))
        base = book_eval(None)
        print("BOOK #463 pre (check 60.34 / 3.153): ROC@30k %.2f Sortino %.3f" % (base["roc30"], base["sortino"]))
        p = legs[pick][0]
        by_u = {}
        for u in (0.5, 1.0, 2.0):
            r = book_eval(p * u)
            by_u[u] = {k: r[k] for k in ("net", "roc30", "sortino", "dd_daily")}
            print(f"  #463 + {pick} x{u}: pre ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} DD ${r['dd_daily']:,.0f}")
        ub = max(by_u, key=lambda k: by_u[k]["roc30"])
        corr = float(pd.concat([base["series"], p], axis=1, join="inner").corr().iloc[0, 1])
        ok = by_u[ub]["roc30"] >= 63.36 and by_u[ub]["sortino"] >= 3.153
        res["A2"] = {"cell": pick, "u": ub, "by_u": by_u, "corr_with_book": corr, "pass": bool(ok)}
        worst = base["series"].nsmallest(10)
        print(f"  leg-book daily correlation {corr:+.3f}; book's 10 worst days: book ${worst.sum():,.0f}, "
              f"leg x{ub} on them ${float((p * ub).reindex(worst.index).fillna(0).sum()):,.0f}")
        print("A2:", f"PASS ({pick} x{ub})" if ok else "FAIL (needs >= 63.36 and Sortino >= 3.153)")
    else:
        res["A2"] = None
        print("Stage A passes: none - VOLCARRY dead; lockbox stays sealed")
    json.dump(res, open(os.path.join(OUT, "stageA.json"), "w"), indent=1, default=str)


def stage_b():
    res = json.load(open(os.path.join(OUT, "stageA.json")))
    if not (res.get("A2") or {}).get("pass"):
        print("Stage B refused: no Stage A2 pass on file - the lockbox stays sealed.")
        return
    flag = os.path.join(OUT, "stageB_READ.flag")
    assert not os.path.exists(flag), "Stage B was already read once"
    open(flag, "w").write(pd.Timestamp.now().isoformat())
    px = load(pd.Timestamp("2025-06-01"), LB1 + pd.Timedelta(days=2))          # the 07-01 open closes day 06-30
    s, ratio = synth(px)
    keep = (s.index >= LB0) & (s.index <= LB1)
    s, ratio = s[keep], ratio[keep]
    p, _ = leg(s, ratio, CELLS[res["A2"]["cell"]])
    p = p * float(res["A2"]["u"])
    r = book_eval(p, pre=False)
    net_ex = r["net"] - float(r["series"].max())
    ok = r["roc30"] >= 164.76 and r["sortino"] >= 4.150 and net_ex > 0 and p.sum() > 0
    print(f"Stage B: book LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} | leg LB net ${p.sum():,.0f} -> {'PASS' if ok else 'FAIL'}")
    json.dump({"roc30": r["roc30"], "sortino": r["sortino"], "leg_net": float(p.sum()), "pass": bool(ok)},
              open(os.path.join(OUT, "stageB.json"), "w"), indent=1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    a = sys.argv[1:]
    if a == ["fetch", "--owner-ok"]:
        fetch()
    elif a == ["A"]:
        stage_a()
    elif a == ["B"]:
        stage_b()
    else:
        print("usage: r7_volcarry.py fetch --owner-ok | A | B   (fetch only after the owner's OK)")

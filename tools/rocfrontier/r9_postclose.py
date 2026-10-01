# Round 9 (2026-09-30): REVERT r2 - fade the cash session's last ten minutes in the quarter hour after the close (NQ, ES).
# Pre-registered: tools/rocfrontier/PREREG_REVERT_R2.txt (sha256 c658b63c...ab38, main 07d023e4), written before any return
# in the 15:50-16:15 window was computed.
#   python r9_postclose.py A    Stage A (+ A2 if a cell passes), PRE-LOCKBOX ONLY
#   python r9_postclose.py B    Stage B (book lockbox, once) - refuses unless A2 passed
import json, os, sys
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO)
import numpy as np, pandas as pd

OUT = os.environ.get("EDGELOG_ROCFRONTIER_R9", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r9")   # results stay outside git
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")
EARN = os.path.join(REPO, "tools", "data", "megacap_earnings_dates.csv")
BW0, WF0, LB0, LB1 = (pd.Timestamp(x) for x in ("2010-06-07", "2016-07-01", "2025-06-30", "2026-06-30"))
LBX, LBY = pd.Timestamp("2026-07-01"), (LB1 - LB0).days / 365.25        # LB = 06-30 .. 06-30 INCLUSIVE, frontier years
MULT, COST, STRESS = {"NQ": 20.0, "ES": 50.0}, {"NQ": 0.533, "ES": 0.363}, 0.25
KS, LOOK, MINLOOK, NREP = (0, 1, 2), 60, 40, 500
rng = np.random.default_rng(20260930)


def load(inst, t_end, t_start="2010-06-01"):
    from augur_engine import data
    m = data.find_master(inst, "1m", "eth", "db_adj_eth")
    assert m is not None, f"no ADJ 1m ETH master for {inst}"
    a = data.load_master_arrays(m, t_start, str((t_end - pd.Timedelta(days=1)).date()))
    ix = pd.DatetimeIndex(a["index"])
    keep = np.asarray(ix < t_end.tz_localize("US/Eastern"))
    df = pd.DataFrame({k: np.asarray(a[k], float)[keep] for k in ("open", "close")}, index=ix[keep])
    assert df.index.max() < t_end.tz_localize("US/Eastern")               # cut BEFORE anything is computed
    return df


def evening_earnings():
    e = pd.read_csv(EARN)
    t = pd.to_datetime(e["report_et"])
    return set(t[(t.dt.hour * 60 + t.dt.minute) >= 960].dt.normalize())


def sessions(df):
    """One row per eligible session: o1550, c1559, o1600, c1614 (all 25 bars 15:50-16:14 present, full cash session)."""
    hm = df.index.hour * 60 + df.index.minute
    day = df.index.tz_localize(None).normalize()
    g = pd.DataFrame({"day": day, "hm": hm, "o": df["open"].to_numpy(), "c": df["close"].to_numpy()})
    rth = g[(g.hm >= 570) & (g.hm < 960)].groupby("day").size()
    win = g[(g.hm >= 950) & (g.hm < 975)]
    n25 = win.groupby("day").size()
    piv = {"o1550": win[win.hm == 950].set_index("day")["o"], "c1559": win[win.hm == 959].set_index("day")["c"],
           "o1600": win[win.hm == 960].set_index("day")["o"], "c1614": win[win.hm == 974].set_index("day")["c"]}
    s = pd.DataFrame(piv).dropna()
    ok = (rth.reindex(s.index).fillna(0) >= 300) & (n25.reindex(s.index).fillna(0) == 25) & (s.index.dayofweek < 5)
    s = s[ok]
    s = s[~s.index.isin(evening_earnings())]
    s["m"] = s["c1559"] - s["o1550"]
    s["scale"] = s["m"].abs().rolling(LOOK, min_periods=MINLOOK).median().shift(1)   # previous 60 eligible sessions only
    s["fwd"] = s["c1614"] - s["o1600"]
    return s


def trades(s, inst, k, mirror=False, cost_add=0.0, sides=None):
    sel = s["scale"].notna() & (s["m"] != 0) & (s["m"].abs() >= k * s["scale"])
    x = s[sel]
    side = -np.sign(x["m"]) if sides is None else sides.reindex(x.index)
    if mirror:
        side = -side
    gross = side * x["fwd"]
    return pd.DataFrame({"date": x.index, "side": side.values, "gross": gross.values,
                         "pnl": ((gross - COST[inst] - cost_add) * MULT[inst]).values})


def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stats(tr, days, t0, t1, yrs=None):
    t = tr[(tr.date >= t0) & (tr.date < t1)]
    d = t.groupby("date")["pnl"].sum().reindex(days[(days >= t0) & (days < t1)]).fillna(0.0)
    yrs, n, net = yrs or (t1 - t0).days / 365.25, len(t), float(t["pnl"].sum())
    gw, gl, ddv = float(t.pnl[t.pnl > 0].sum()), float(-t.pnl[t.pnl < 0].sum()), ddmax(d.values)
    sd = float(t.pnl.std(ddof=1)) if n > 1 else float("nan")
    by = t.groupby(t.date.dt.year)["pnl"].sum()
    return {"n": n, "net": net, "per_trade": net / n if n else float("nan"), "pf": gw / gl if gl > 0 else float("inf"),
            "dd_daily": ddv, "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 else float("nan"), "sortino": so(d.values),
            "t": float(t.pnl.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
            "years_pos": float((by > 0).mean()) if len(by) else 0.0, "net_ex_big": net - (float(t.pnl.max()) if n else 0.0)}


def book(extra, t0, t1, yrs=None):
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    idx = b.index.union(extra.index) if extra is not None else b.index
    M, C = b["mtm"].reindex(idx).fillna(0.0), b["close"].reindex(idx).fillna(0.0)
    if extra is not None:
        e = extra.reindex(idx).fillna(0.0); M, C = M + e, C + e
    sel = (idx >= t0) & (idx < t1)
    yrs, net, ddv = yrs or (t1 - t0).days / 365.25, float(C[sel].sum()), ddmax(M[sel].values)
    return {"net": net, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values), "dd_daily": ddv}


def stage_a():
    S, days, tr = {}, {}, {}
    for inst in ("NQ", "ES"):
        S[inst] = sessions(load(inst, LB0))
        days[inst] = pd.DatetimeIndex(S[inst].index)
    res, rows, passes = {}, [], []
    for inst in ("NQ", "ES"):
        s, d = S[inst], days[inst]
        first = d[S[inst]["scale"].notna()][0]
        for k in KS:
            for mir in (False, True):
                t = trades(s, inst, k, mirror=mir)
                ts_ = trades(s, inst, k, mirror=mir, cost_add=STRESS)
                name = f"{inst}|k{k}" + ("|mirror" if mir else "")
                tr[name] = t
                r = {"WF": stats(t, d, WF0, LB0), "EARLY": stats(t, d, first, WF0), "stress_net": float(ts_[ts_.date >= WF0].pnl.sum())}
                res[name] = r
                t.to_csv(os.path.join(OUT, f"trades_{inst}_k{k}{'_mirror' if mir else ''}.csv"), index=False)
    # family-wide null: one coin per market-day shared by that market's k cells; max WF t over the 6 primary cells
    null = []
    for _ in range(NREP):
        best = -np.inf
        for inst in ("NQ", "ES"):
            s = S[inst]
            coin = pd.Series(rng.choice([-1.0, 1.0], size=len(s)), index=s.index)
            for k in KS:
                t = trades(s, inst, k, sides=coin)
                t = t[t.date >= WF0]
                if len(t) > 1 and t.pnl.std(ddof=1) > 0:
                    best = max(best, float(t.pnl.mean() / (t.pnl.std(ddof=1) / np.sqrt(len(t)))))
        null.append(best)
    p95 = float(np.percentile(null, 95))
    for name, r in res.items():
        w, e = r["WF"], r["EARLY"]
        prim = not name.endswith("mirror")
        ok = (prim and w["n"] >= 100 and w["roc30"] >= 15 and w["pf"] >= 1.10 and w["t"] >= 2.0 and w["t"] > p95
              and r["stress_net"] > 0 and w["net_ex_big"] > 0 and w["years_pos"] >= 0.60 and e["net"] > 0)
        r["PASS"] = bool(ok)
        rows.append((name, w["n"], w["net"], w["per_trade"], w["pf"], w["dd_daily"], w["roc30"], w["sortino"], w["t"],
                     w["years_pos"], r["stress_net"], w["net_ex_big"], e["n"], e["net"], ok))
        if ok:
            passes.append(name)
    tab = pd.DataFrame(rows, columns=["cell", "wf_n", "wf_net", "per_trade", "pf", "dd_daily", "roc30", "sortino", "t", "years_pos",
                                      "stress_net", "net_ex_big", "early_n", "early_net", "PASS"])
    tab.to_csv(os.path.join(OUT, "stageA_table.csv"), index=False)
    pd.set_option("display.width", 250)
    print(tab.round(3).to_string(index=False))
    print(f"null max-t p95 {p95:.3f} (median {np.median(null):.3f})")
    for name in ("NQ|k0", "ES|k0"):
        t = tr[name]; t = t[t.date >= WF0]
        top = t.reindex(t.pnl.abs().sort_values(ascending=False).index[:10])
        print(f"  {name} ten biggest WF days: " + ", ".join(f"{d:%Y-%m-%d} ${p:,.0f}" for d, p in zip(top.date, top.pnl)))
    out = {"prereg": "PREREG_REVERT_R2.txt @07d023e4", "null_p95": p95, "cells": res, "passes": passes, "A2": None}
    if passes:
        base = book(None, BW0, LB0)
        print(f"BOOK #463 pre (check 60.34 / 3.153): ROC@30k {base['roc30']:.2f} Sortino {base['sortino']:.3f}")
        if not (abs(base["roc30"] - 60.34) < 0.006 and abs(base["sortino"] - 3.153) < 0.0006):
            print("A2 NOT judged: the book file does not reproduce #463's pre numbers - fix the input first")
            out["A2"] = {"pass": False, "error": "book check mismatch", "book_pre": base}
            json.dump(out, open(os.path.join(OUT, "stageA.json"), "w"), indent=1, default=str)
            return
        pick = {}
        for p in passes:                                         # at most one cell per market: the best WF ROC
            inst = p.split("|")[0]
            if inst not in pick or res[p]["WF"]["roc30"] > res[pick[inst]]["WF"]["roc30"]:
                pick[inst] = p
        leg = pd.concat([tr[p] for p in pick.values()]).groupby("date")["pnl"].sum()
        by_c = {c: book(leg * c, BW0, LB0) for c in (1, 2, 3)}
        cb = max(by_c, key=lambda c: by_c[c]["roc30"])
        ok = by_c[cb]["roc30"] >= 63.36 and by_c[cb]["sortino"] >= 3.153
        for c, r in by_c.items():
            print(f"  #463 + {'+'.join(pick.values())} x{c}: pre ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} DD ${r['dd_daily']:,.0f}")
        out["A2"] = {"cells": list(pick.values()), "c": cb, "pass": bool(ok), "by_c": {str(k): v for k, v in by_c.items()}}
        print("A2:", f"PASS (x{cb})" if ok else "FAIL (needs >= 63.36 and Sortino >= 3.153)")
    else:
        print("Stage A passes: none - REVERT r2 dead; lockbox stays sealed")
    json.dump(out, open(os.path.join(OUT, "stageA.json"), "w"), indent=1, default=str)


def stage_b():
    pa = os.path.join(OUT, "stageA.json")
    res = json.load(open(pa)) if os.path.exists(pa) else {}
    if not (res.get("A2") or {}).get("pass"):
        print("Stage B refused: no Stage A2 pass on file - the lockbox stays sealed."); return
    flag = os.path.join(OUT, "stageB_READ.flag")
    if os.path.exists(flag):
        print("Stage B refused: the lockbox was already read once."); return
    base = book(None, LB0, LBX, yrs=LBY)                         # #463's own LB numbers are public (prereg): checked before the family's lockbox is read
    if not (abs(base["roc30"] - 164.76) < 0.006 and abs(base["sortino"] - 4.150) < 0.0006):
        print("Stage B refused: the book file does not reproduce #463's LB numbers (lockbox NOT read)"); return
    c, legs = int(res["A2"]["c"]), []
    cells = [(cell.split("|")[0], int(cell.split("|")[1][1:])) for cell in res["A2"]["cells"]]
    data = {inst: sessions(load(inst, LBX, "2025-01-01")) for inst, _ in cells}     # 60 prior sessions for the scale; loads first, nothing computed yet
    open(flag, "w").write(pd.Timestamp.now().isoformat())        # the one read starts here (a crash above leaves the lockbox unread)
    for inst, k in cells:
        s = data[inst]
        t = trades(s, inst, k)
        legs.append(t[(t.date >= LB0) & (t.date < LBX)])
    lt = pd.concat(legs)
    leg = lt.groupby("date")["pnl"].sum() * c
    r = book(leg, LB0, LBX, yrs=LBY)
    bt = pd.read_csv(os.path.join(os.path.dirname(BOOK), "book463_trades.csv"), parse_dates=["date"])
    big = max(float(bt[bt.date >= LB0]["pnl"].max()), float(lt["pnl"].max() * c) if len(lt) else 0.0)
    ok = r["roc30"] >= 164.76 and r["sortino"] >= 4.150 and r["net"] - big > 0 and leg.sum() > 0 and len(lt) >= 50
    print(f"Stage B: book LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} | leg LB {len(lt)} trades ${leg.sum():,.0f} -> {'PASS' if ok else 'FAIL'}")
    json.dump({"B": r, "leg_n": len(lt), "leg_net": float(leg.sum()), "pass": bool(ok)}, open(os.path.join(OUT, "stageB.json"), "w"), indent=1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1:2]
    {"A": stage_a, "B": stage_b}.get(cmd[0] if cmd else "", lambda: print("usage: r9_postclose.py A | B"))()

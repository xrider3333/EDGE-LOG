# Round 4b Stage A triage: EARN r1 (pre-registered: tools/rocfrontier/PREREG_EARN_R1.txt, sha256 2e3148a8...decf).
# PRE-LOCKBOX ONLY - reuses r4_triage.load (bars cut before 2025-06-30) and its statistics.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import r4_triage as T

OUT = T.OUT
REPO = T.REPO
KS = (0.0, 0.1, 0.2)
XS = {"X_0925": (9, 25, "open"), "X_1600": (16, 0, "close_before")}
rng = np.random.default_rng(20260929)


def evenings():
    e = pd.read_csv(os.path.join(REPO, "tools", "data", "megacap_earnings.csv"))
    t = pd.to_datetime(e["accepted_et"])
    t = t[(t.dt.hour == 16) & (t.dt.dayofweek < 5)]
    return sorted(set(t.dt.normalize()))


def earn_events(inst):
    a = T.load(inst, "eth", "db_adj_eth")
    idx, o, h, l, c = a["index"], a["open"], a["high"], a["low"], a["close"]
    tsec = (idx.asi8 // 10**9).astype(np.int64)
    sess = ((idx + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8 // (86400 * 10**9)).astype(np.int64)
    s_ser = pd.Series(sess)
    rngs = pd.Series(h).groupby(s_ser).max() - pd.Series(l).groupby(s_ser).min()
    sw = T.rolls(inst)
    ev = []
    for day in evenings():
        d0 = pd.Timestamp(day).tz_localize("US/Eastern")
        j0 = int(np.searchsorted(idx.asi8, (d0 + pd.Timedelta(hours=16)).value, side="left")) - 1    # 15:55 bar
        j1 = int(np.searchsorted(idx.asi8, (d0 + pd.Timedelta(hours=17)).value, side="left")) - 1    # 16:55 bar
        if j0 < 0 or j1 <= j0 or j1 + 1 >= len(o):
            continue
        sd = (d0.tz_localize(None).normalize().value // (86400 * 10**9))
        if sess[j0] != sd or sess[j1] != sd:
            continue
        prev = rngs.loc[:sd]
        if len(prev) < 20:
            continue
        atr = float(prev.iloc[-20:].mean())
        m = (c[j1] - c[j0]) / atr
        i = j1 + 1                                            # first bar of the next session (18:00 reopen)
        if sess[i] == sd:
            continue
        nxt = pd.Timestamp(sess[i] * 86400 * 10**9).tz_localize("US/Eastern")
        row = {"day": day, "m": m, "entry": o[i], "F_t": int(tsec[j1] + 300)}
        for name, (hh, mm, kind) in XS.items():
            xt = nxt + pd.Timedelta(hours=hh, minutes=mm)
            if kind == "open":
                j = int(np.searchsorted(idx.asi8, xt.value, side="left"))
                ok = j < len(o) and sess[j] == sess[i] and j > i
                px, jt = (o[j], int(tsec[j])) if ok else (np.nan, 0)
            else:
                j = int(np.searchsorted(idx.asi8, xt.value, side="left")) - 1
                ok = j > i and sess[j] == sess[i]
                px, jt = (c[j], int(tsec[j] + 300)) if ok else (np.nan, 0)
            if ok and len(sw) and ((sw > row["F_t"]) & (sw <= jt)).any():
                px = np.nan
            row[name] = px
            row[name + "_date"] = nxt.tz_localize(None)
        ev.append(row)
    return pd.DataFrame(ev)


def trades(ev, inst, k, x, direction, cost_add=0.0, dirs=None):
    e = ev[(np.abs(ev["m"]) >= k) & (ev["m"] != 0) & np.isfinite(ev[x])]
    sgn = np.sign(e["m"].to_numpy()) * direction if dirs is None else dirs[e.index.to_numpy()]
    pts = sgn * (e[x].to_numpy() - e["entry"].to_numpy()) - (T.COST[inst] + cost_add)
    return pd.DataFrame({"date": pd.to_datetime(e[x + "_date"]), "pnl": pts * T.MULT[inst]})


def main():
    ev = {inst: earn_events(inst) for inst in ("NQ", "ES")}
    for inst in ev:
        ev[inst].to_csv(os.path.join(OUT, f"earn_events_{inst}.csv"), index=False)
    cells = [(inst, k, x) for inst in ("NQ", "ES") for k in KS for x in XS]
    res, rows = {}, []
    WF0, LBn = T.WF0, T.LB0.tz_localize(None)
    for inst, k, x in cells:
        for dname, dirn in (("cont", 1), ("fade", -1)):
            tr = trades(ev[inst], inst, k, x, dirn)
            trs = trades(ev[inst], inst, k, x, dirn, cost_add=T.STRESS)
            dl = T.daily_from_trades(tr)
            r = {"WF": T.stretch_stats(tr, dl, WF0, LBn), "EARLY": T.stretch_stats(tr, dl, pd.Timestamp("2010-06-01"), WF0),
                 "WF_stress_net": float(trs[trs["date"] >= WF0]["pnl"].sum())}
            res[f"{inst}|k{k}|{x}|{dname}"] = r
    null_max = []
    for rep in range(T.NREP):
        coins = {inst: rng.choice([-1.0, 1.0], size=len(ev[inst])) for inst in ev}
        best = -np.inf
        for inst, k, x in cells:
            t = trades(ev[inst], inst, k, x, 1, dirs=coins[inst])
            t = t[t["date"] >= WF0]["pnl"]
            if len(t) > 1 and t.std(ddof=1) > 0:
                best = max(best, float(t.mean() / (t.std(ddof=1) / np.sqrt(len(t)))))
        null_max.append(best)
    p95 = float(np.percentile(null_max, 95))
    for key, r in res.items():
        w, e = r["WF"], r["EARLY"]
        ok = (key.endswith("cont") and w["n"] >= 100 and w["roc30"] >= 15 and w["pf"] >= 1.10 and r["WF_stress_net"] > 0
              and w["net_ex_big"] > 0 and w["years_pos"] >= 0.60 and e["net"] > 0 and w["t"] >= 2.0 and w["t"] > p95)
        rows.append((key, w["n"], w["net"], w["pf"], w["roc30"], w["t"], w["years_pos"], e["n"], e["net"], ok))
    json.dump({"cells": res, "null_tmax_p95": p95, "null_tmax_median": float(np.median(null_max))},
              open(os.path.join(OUT, "r4b_earn_stageA.json"), "w"), indent=1, default=str)
    df = pd.DataFrame(rows, columns=["cell", "wf_n", "wf_net", "wf_pf", "wf_roc30", "wf_t", "wf_years_pos", "early_n", "early_net", "PASS"])
    df.to_csv(os.path.join(OUT, "r4b_earn_stageA_table.csv"), index=False)
    pd.set_option("display.width", 200)
    print(df.round(3).to_string(index=False))
    print("null max-t p95", round(p95, 3), "median", round(float(np.median(null_max)), 3), "| events NQ", len(ev["NQ"]), "ES", len(ev["ES"]))


if __name__ == "__main__":
    main()

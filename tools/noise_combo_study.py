"""
NOISE combination study — 2026-08-21.

Answers ONE question the 2026-08-17 variant campaign never asked: does the BROADER
day-type filter (daytype_mode='skip_bot_all' — skip BOTH sides the day after a weak
close) combine profitably with the volatility skip (rv_mode='skip_hi')?  Every
combination the campaign ran used the NARROWER shorts-only version, and only ever at
volatility threshold 90.

Selection happens ONLY on run #231's optimize window (2010-06-07 -> 2025-02-10).
The NOISE lockbox is SPENT and is read once at the end, confirmatory only.

Source PINNED: db_noadj_rth · NQ 5m RTH · cost_pts 0.533 · multiplier 20 · 1 contract.
ES sibling: the ES 5m RTH no-adjust master, same knobs, multiplier 50, same costs.

Usage:  python tools/noise_combo_study.py           (full study)
        python tools/noise_combo_study.py --gate    (reproduction gate only)
"""
import os, sys, json

# The master-CSV registry (optimizer_history.db + augur_uploads/) lives only in the
# shared checkout, not in a git worktree. EDGELOG_DATA_ROOT lets this script run from a
# worktree against the real data; unset, it resolves to its own checkout as usual.
EDGELOG_ROOT = os.environ.get("EDGELOG_DATA_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(EDGELOG_ROOT, "tools"), EDGELOG_ROOT):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import numpy as np
from noise_variant_research import (CHAMPION, SEL_DATE_TO, FULL_DATE_TO, FEE, MULT,
                                    run_variant, metrics, load_arrays,
                                    _session_bounds, _vol_percentile, _daytype_pos)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import _apply_costs

# banked selection-window reference numbers (NOISE.md, 2026-08-17 campaign table)
BANKED = {
    "champion": (5113, 277123.31, -19482.27),
    "sbs":      (4748, 320530.0,  -18560.0),
    "sba":      (3991, 308783.01, -15933.92),
    "vs90":     (4309, 310689.59, -19040.79),
    "vs95":     (4697, 302963.0,  -19176.0),
    "vs98":     (4868, 309055.0,  -19176.0),
    "sbs_vs90": (4054, 320130.0,  -18425.0),
}

CFG = {
    "champion": dict(CHAMPION),
    "sbs":      dict(CHAMPION, daytype_mode="skip_bot_short"),
    "sba":      dict(CHAMPION, daytype_mode="skip_bot_all"),
    "vs90":     dict(CHAMPION, rv_mode="skip_hi", rv_pct=90.0),
    "vs95":     dict(CHAMPION, rv_mode="skip_hi", rv_pct=95.0),
    "vs98":     dict(CHAMPION, rv_mode="skip_hi", rv_pct=98.0),
    "sbs_vs90": dict(CHAMPION, daytype_mode="skip_bot_short", rv_mode="skip_hi", rv_pct=90.0),
}

TOL_NET = 1.0
TOL_DD = 1.0


def metrics_full(params, date_to=SEL_DATE_TO):
    arr = load_arrays(date_to)
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    return {"m": metrics(tr, arr["index"]), "trades": tr, "arr": arr}


def run_cfg(params, date_to=SEL_DATE_TO):
    return metrics_full(params, date_to)["m"]


def gate(verbose=True):
    ok = True
    for k, (en, enet, edd) in BANKED.items():
        m = run_cfg(CFG[k])
        good = (m["n"] == en and abs(m["net"] - enet) < TOL_NET
                and abs(m["dd"] - edd) < TOL_DD)
        ok = ok and good
        if verbose:
            print("  %-10s n=%-5d net=$%-11s DD=$%-10s  %s" % (
                k, m["n"], format(m["net"], ",.0f"), format(abs(m["dd"]), ",.0f"),
                "PASS" if good else "FAIL exp n=%d net=%.2f dd=%.2f" % (en, enet, edd)))
    return ok


# ------------------------------- veto-day masks ------------------------------
def veto_masks(date_to=SEL_DATE_TO):
    arr = load_arrays(date_to)
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    sb = _session_bounds(np.asarray(arr["day_id"]), len(c))
    vp = _vol_percentile(h, l, c, sb)
    dp = _daytype_pos(h, l, c, sb)
    return arr, sb, vp, dp


def overlap_report(lo=0.2, pcts=(90.0, 95.0, 98.0), date_to=SEL_DATE_TO):
    arr, sb, vp, dp = veto_masks(date_to)
    base = metrics_full(CFG["champion"], date_to)
    sess_of_bar = np.empty(len(arr["close"]), dtype=int)
    for si, (a, b) in enumerate(sb):
        sess_of_bar[a:b] = si
    tr = _apply_costs({"trades": list(base["trades"])}, FEE)["trades"]

    dt_hit = np.array([(not np.isnan(dp[si])) and dp[si] <= lo for si in range(len(sb))])
    out = []
    for p in pcts:
        vol_hit = np.array([(not np.isnan(vp[si])) and vp[si] >= p for si in range(len(sb))])
        buckets = {k: [0, 0.0, 0.0, 0] for k in ("both", "dt_only", "vol_only", "neither")}
        # [n_trades, $ all sides, $ shorts only, n_shorts]
        for (eb, xb, pnl, pos, epx) in tr:
            si = sess_of_bar[eb]
            d, w = bool(dt_hit[si]), bool(vol_hit[si])
            k = "both" if (d and w) else ("dt_only" if d else ("vol_only" if w else "neither"))
            buckets[k][0] += 1
            buckets[k][1] += pnl * MULT
            if pos < 0:
                buckets[k][2] += pnl * MULT
                buckets[k][3] += 1
        out.append({
            "pct": p, "lo": lo,
            "sessions_total": len(sb),
            "sessions_dt": int(dt_hit.sum()),
            "sessions_vol": int(vol_hit.sum()),
            "sessions_both": int((dt_hit & vol_hit).sum()),
            "sessions_dt_only": int((dt_hit & ~vol_hit).sum()),
            "sessions_vol_only": int((~dt_hit & vol_hit).sum()),
            "buckets": buckets,
        })
    return out


# ------------------------------ combination grid -----------------------------
def grid_rows():
    rows = [("champion", dict(CHAMPION))]
    for p in (90.0, 95.0, 98.0):
        rows.append(("vs%d alone" % int(p), dict(CHAMPION, rv_mode="skip_hi", rv_pct=p)))
    for lo in (0.15, 0.20, 0.25):
        for dt, tag in (("skip_bot_short", "SBS"), ("skip_bot_all", "SBA")):
            rows.append(("%s lo%.2f" % (tag, lo),
                         dict(CHAMPION, daytype_mode=dt, daytype_lo=lo)))
            for p in (90.0, 95.0, 98.0):
                rows.append(("%s lo%.2f + vs%d" % (tag, lo, int(p)),
                             dict(CHAMPION, daytype_mode=dt, daytype_lo=lo,
                                  rv_mode="skip_hi", rv_pct=p)))
    return rows


def grid(date_to=SEL_DATE_TO):
    out = []
    for label, params in grid_rows():
        m = run_cfg(params, date_to)
        out.append({"label": label, "params": params, "n": m["n"], "net": m["net"],
                    "pf": m["pf"], "dd": abs(m["dd"]), "mar": m["mar"],
                    "era_2010_17": m["era_2010_17"], "worst_year": m["worst_year"],
                    "worst_year_net": m["worst_year_net"], "pyear": m["pyear"]})
    return out


# ------------------------------- concentration -------------------------------
def concentration(params, ref_params, date_to=SEL_DATE_TO):
    a = metrics_full(params, date_to)
    b = metrics_full(ref_params, date_to)
    d_net = a["m"]["net"] - b["m"]["net"]
    yrs = sorted(set(a["m"]["pyear"]) | set(b["m"]["pyear"]))
    dy = {y: a["m"]["pyear"].get(y, 0.0) - b["m"]["pyear"].get(y, 0.0) for y in yrs}
    best_y = max(dy.items(), key=lambda kv: kv[1]) if dy else (None, 0.0)
    pos = sum(1 for v in dy.values() if v > 0)
    neg = sum(1 for v in dy.values() if v < 0)
    ta = {(t[0], t[3]) for t in a["trades"]}
    rb = _apply_costs({"trades": list(b["trades"])}, FEE)["trades"]
    removed = [t[2] * MULT for t in rb if (t[0], t[3]) not in ta]
    removed.sort()
    top10 = -sum(removed[:10])
    return {"d_net": d_net, "best_year": best_y[0], "best_year_d": best_y[1],
            "best_year_share": (best_y[1] / d_net if d_net else float("nan")),
            "n_removed": len(removed), "top10_avoided": top10,
            "top10_share": (top10 / d_net if d_net else float("nan")),
            "d_ex_top10": d_net - top10, "years_pos": pos, "years_neg": neg,
            "dy": dy}


# --------------------------------- ES transfer --------------------------------
_ES_CACHE = {}


def es_arrays(date_to=SEL_DATE_TO):
    if date_to in _ES_CACHE:
        return _ES_CACHE[date_to]
    master = find_master("ES", "5m", "rth", "db_noadj_rth")
    if master is None:
        raise SystemExit("NO ES MASTER for ES/5m/rth/db_noadj_rth")
    arr = load_master_arrays(master, date_from="2010-06-07", date_to=date_to)
    _ES_CACHE[date_to] = arr
    return arr


def es_run(params, date_to=SEL_DATE_TO):
    arr = es_arrays(date_to)
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    res = _apply_costs({"trades": list(tr)}, FEE)
    net_pts = res["total_pnl"]
    dd_pts = res["max_drawdown"]
    return {"n": res["num_trades"], "pts": net_pts, "usd": net_pts * 50.0,
            "pf": res["profit_factor"], "dd_usd": abs(dd_pts) * 50.0,
            "mar": (net_pts / abs(dd_pts)) if abs(dd_pts) > 1e-9 else float("inf")}


# --------------------------- pre-registered judging ---------------------------
LOS = [0.15, 0.20, 0.25]
PCTS = [90, 95, 98]


def judge(rows):
    """Apply the 2026-08-21 pre-registered bar. Returns {cell: verdict-dict}."""
    by = {r["label"]: r for r in rows}
    res = {}
    for tag in ("SBS", "SBA"):
        for lo in LOS:
            for p in PCTS:
                c = by["%s lo%.2f + vs%d" % (tag, lo, p)]
                a = by["%s lo%.2f" % (tag, lo)]
                b = by["vs%d alone" % p]
                occam = (c["net"] > a["net"] and c["net"] > b["net"]
                         and c["mar"] > a["mar"] and c["mar"] > b["mar"])
                res[(tag, lo, p)] = {"occam": occam, "row": c,
                                     "best_comp_net": max(a["net"], b["net"]),
                                     "best_comp_mar": max(a["mar"], b["mar"])}
    for k, v in res.items():
        tag, lo, p = k
        nb = []
        i, j = LOS.index(lo), PCTS.index(p)
        for ii in (i - 1, i + 1):
            if 0 <= ii < len(LOS):
                nb.append(("lo%.2f" % LOS[ii], res[(tag, LOS[ii], p)]["occam"]))
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(PCTS):
                nb.append(("vs%d" % PCTS[jj], res[(tag, lo, PCTS[jj])]["occam"]))
        v["neighbours"] = nb
        v["plateau"] = all(ok for _, ok in nb)
    return res


ES_CASES = [
    ("#231 champion", dict(CHAMPION)),
    ("SBS lo0.20 (run 241)", CFG["sbs"]),
    ("SBA lo0.20 (run 245)", CFG["sba"]),
    ("SBS + vs90 (run 243)", CFG["sbs_vs90"]),
    ("vs98 alone", CFG["vs98"]),
    ("SBS lo0.20 + vs98", dict(CHAMPION, daytype_mode="skip_bot_short",
                              rv_mode="skip_hi", rv_pct=98.0)),
    ("SBS lo0.25 + vs98", dict(CHAMPION, daytype_mode="skip_bot_short", daytype_lo=0.25,
                              rv_mode="skip_hi", rv_pct=98.0)),
    ("SBA lo0.20 + vs98", dict(CHAMPION, daytype_mode="skip_bot_all",
                              rv_mode="skip_hi", rv_pct=98.0)),
    ("SBA lo0.15 + vs98", dict(CHAMPION, daytype_mode="skip_bot_all", daytype_lo=0.15,
                              rv_mode="skip_hi", rv_pct=98.0)),
]


def confirmatory(params, date_to=FULL_DATE_TO):
    """One-look full-window read INCLUDING the SPENT lockbox. Never used to select."""
    import pandas as pd
    d = metrics_full(params, date_to)
    m, arr = d["m"], d["arr"]
    tz = getattr(arr["index"], "tz", None)
    cut = pd.Timestamp("2025-02-11", tz=tz) if tz is not None else pd.Timestamp("2025-02-11")
    tr = _apply_costs({"trades": list(d["trades"])}, FEE)["trades"]
    lb_n, lb = 0, 0.0
    for (eb, xb, pnl, pos, epx) in tr:
        if arr["index"][eb] >= cut:
            lb_n += 1
            lb += pnl * MULT
    return {"n": m["n"], "net": m["net"], "pf": m["pf"], "dd": abs(m["dd"]),
            "mar": m["mar"], "lb_n": lb_n, "lb_net": lb}


def main():
    print("NOISE combination study — selection window 2010-06-07 -> %s" % SEL_DATE_TO)
    print("\n[GATE] reproducing the campaign banked selection-window figures:")
    if not gate():
        print("\nGATE FAILED — refusing to proceed.")
        sys.exit(1)
    print("  GATE PASS\n")
    if "--gate" in sys.argv:
        return

    print("[GRID] selection window 2010-06-07 -> %s" % SEL_DATE_TO)
    rows = grid()
    print("%-26s %6s %12s %6s %11s %7s %11s %10s" % (
        "config", "n", "net $", "PF", "DD $", "MAR", "2010-17 $", "worst yr $"))
    for r in sorted(rows, key=lambda r: -r["net"]):
        print("%-26s %6d %12s %6.3f %11s %7.2f %11s %10s" % (
            r["label"], r["n"], format(r["net"], ",.0f"), r["pf"],
            format(r["dd"], ",.0f"), r["mar"], format(r["era_2010_17"], ",.0f"),
            format(r["worst_year_net"], ",.0f")))

    print("\n[OCCAM] combination must beat its BEST single component on net AND MAR")
    res = judge(rows)
    for (tag, lo, p), v in res.items():
        print("  %-22s net %11s vs best component %11s | MAR %6.2f vs %6.2f -> %s" % (
            "%s lo%.2f + vs%d" % (tag, lo, p), format(v["row"]["net"], ",.0f"),
            format(v["best_comp_net"], ",.0f"), v["row"]["mar"], v["best_comp_mar"],
            "CLEARS" if v["occam"] else "fails"))

    print("\n[PLATEAU] pre-declared neighbourhood lo{0.15,0.20,0.25} x pct{90,95,98}")
    survivors = []
    for (tag, lo, p), v in res.items():
        if not v["occam"]:
            continue
        print("  %-22s neighbours: %s -> PLATEAU %s" % (
            "%s lo%.2f + vs%d" % (tag, lo, p),
            ", ".join("%s=%s" % (n, "clear" if ok else "FAIL") for n, ok in v["neighbours"]),
            "PASS" if v["plateau"] else "FAIL"))
        if v["plateau"]:
            survivors.append((tag, lo, p))

    print("\n[OVERLAP] day-type veto (lo 0.20) vs volatility veto, selection window")
    ov = overlap_report()
    for o in ov:
        b = o["buckets"]
        print("  vol pct %d: sessions %d | day-type %d | vol %d | BOTH %d | day-type only %d | vol only %d"
              % (o["pct"], o["sessions_total"], o["sessions_dt"], o["sessions_vol"],
                 o["sessions_both"], o["sessions_dt_only"], o["sessions_vol_only"]))
        for k in ("both", "dt_only", "vol_only", "neither"):
            print("     %-9s champion trades %5d  all-sides $%12s  shorts %4d  shorts $%12s"
                  % (k, b[k][0], format(b[k][1], ",.0f"), b[k][3], format(b[k][2], ",.0f")))

    print("\n[CONCENTRATION] plateau survivors, improvement measured vs their best component")
    for (tag, lo, p) in survivors:
        dtm = "skip_bot_short" if tag == "SBS" else "skip_bot_all"
        cand = dict(CHAMPION, daytype_mode=dtm, daytype_lo=lo, rv_mode="skip_hi", rv_pct=float(p))
        ref = dict(CHAMPION, daytype_mode=dtm, daytype_lo=lo)
        r = concentration(cand, ref)
        print("  %-22s delta $%s | best year %s $%s (%.0f%%) | top-10 avoided $%s (%.0f%%) | "
              "delta ex-top-10 $%s | years +%d/-%d -> %s" % (
                  "%s lo%.2f + vs%d" % (tag, lo, p), format(r["d_net"], ",.0f"),
                  r["best_year"], format(r["best_year_d"], ",.0f"), 100 * r["best_year_share"],
                  format(r["top10_avoided"], ",.0f"), 100 * r["top10_share"],
                  format(r["d_ex_top10"], ",.0f"), r["years_pos"], r["years_neg"],
                  "SURVIVES" if r["d_ex_top10"] > 0 else "DISQUALIFIED"))

    print("\n[ES TRANSFER] nothing refitted, selection window, cost 0.533, multiplier 50")
    print("  NOISE promotion bar is PF >= 1.2 (the engine generic sanity check is a looser 1.0)")
    print("  %-22s %6s %10s %8s %11s %7s  %s" % ("config", "n", "net pts", "PF", "DD $", "MAR", "PF>=1.2"))
    for lab, p in ES_CASES:
        r = es_run(p)
        print("  %-22s %6d %10.1f %8.3f %11s %7.2f  %s" % (
            lab, r["n"], r["pts"], r["pf"], format(r["dd_usd"], ",.0f"), r["mar"],
            "PASS" if r["pf"] >= 1.2 else "FAIL"))

    print("\n[CONFIRMATORY ONE-LOOK] full window incl. the SPENT lockbox — never used to select")
    print("  %-22s %6s %12s %7s %11s %7s %6s %12s" % (
        "config", "n", "TOTAL net", "PF", "DD $", "MAR", "LB n", "LB slice $"))
    for lab, p in ES_CASES:
        if lab == "vs98 alone":
            continue
        r = confirmatory(p)
        print("  %-22s %6d %12s %7.3f %11s %7.2f %6d %12s" % (
            lab, r["n"], format(r["net"], ",.0f"), r["pf"], format(r["dd"], ",.0f"),
            r["mar"], r["lb_n"], format(r["lb_net"], ",.0f")))

    out = {"grid": [{k: v for k, v in r.items() if k != "params"} for r in rows],
           "overlap": ov,
           "survivors": ["%s lo%.2f + vs%d" % s for s in survivors]}
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "_noise_combo_study.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print("\nwrote %s" % p)


if __name__ == "__main__":
    main()

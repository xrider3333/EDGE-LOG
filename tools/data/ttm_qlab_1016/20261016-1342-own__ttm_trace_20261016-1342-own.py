"""TTM (house verifier) STAGE 2 - COMPARE + TRACE for Qwen Lab QL_TRENDN (20261016-1342-own).
Opened only after stage 1's output sha256 (2831ffda...) was posted to MANAGER.
 1. Arm A (plugin as run through the engine) vs the lab's numbers_pre_wf.json field by field, and vs pre_wf_trades.csv trade by trade.
 2. TTM's own rule (ttm_armb_own_rule.py, sha 08e54167... frozen before the plugin was read) re-run THE PLUGIN'S WAY
    (fill at session bar 12's open instead of the text's bar 13; every other reading unchanged) -> must equal the plugin 100%.
 3. Four numbers (house / real / stress) of each literal reading the plugin departs from (or that the text leaves open).
 4. Look-ahead: prefix-truncation test on every plugin trade (cut the data at the exit bar, and one bar before it).
Writes only ttm_trace.json into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1342-own/."""
import csv
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1342-own"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261016-1342-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = IDEA + "/plugin_v1.py.txt"
PIN_PREREG_FULL = "dbc02a2e11c364dcdcd9eb18be18067fa77e5ce9a0ff01dff43d8a56a670f2ae"
ARMB = os.path.join(OUT, "ttm_armb_own_rule.py")
ARMB_SHA_AT_BUILD = "08e541671ab34d24211fa98757edee62162ef012c76bd68b1d17cd7a2e5d24d3"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # 0.7825 pt
STRESS_COST = COST + 0.5
PARAMS = {"threshold_frac": 0.3, "stop_frac": 1.0, "trail_frac": 0.5}
TOL = {"trades": 0, "net_usd": 1.0, "roc_30k": 0.005, "dd5_usd": 1.0, "max_dd_usd": 1.0, "dd_pct_peak": 0.01,
       "sortino": 0.001, "win_rate_pct_points": 0.05}


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net_usd": float(x.sum()), "per_yr_usd": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "net_per_trade_pts": float(pts.mean() - cost)})
    return f


def line(f):
    return ("ROC@30k %.2f | DD5 $%s%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%d/yr) | $/yr %s"
            % (f["roc30"], format(round(f["dd5"]), ","), " (one episode)" if f["one_episode"] else "", f["dd_pct_peak"],
               f["sortino"], format(f["trades"], ","), round(f["trades_per_yr"]), format(round(f["per_yr_usd"]), ",")))


def three(exit_bars, pts, idxn, days):
    out = {}
    for k, c in (("house", COST), ("real", REAL_COST), ("stress_house_plus_0.5", STRESS_COST)):
        f = score(exit_bars, pts, idxn, days, c)
        f["four_numbers"] = line(f)
        out[k] = f
    return out


def main():
    assert lf_sha(PLUGIN) == PIN_PREREG_FULL, "plugin pin"
    assert lf_sha(ARMB) == ARMB_SHA_AT_BUILD, "arm B changed since it was frozen"
    spec = importlib.util.spec_from_file_location("ttm_armb_own_rule", ARMB)
    armb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(armb)

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idxn = pd.DatetimeIndex(A["index"]).tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(did)) + 1]
    ends = np.r_[starts[1:], len(c)]
    res = {"idea": "QL_TRENDN", "folder": "20261016-1342-own", "registry_id": row[0].get("id"), "fingerprint": A.get("fingerprint"),
           "bars": len(c), "sessions": len(days), "params": PARAMS}

    # ---- ARM A: plugin as run
    m = types.ModuleType("ttm_ql_trendn")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]   # entry, exit, side, entry_px, pts
    armA = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["arm_A"] = armA

    # ---- 1. lab numbers file vs arm A (house), field by field
    lab = json.load(open(IDEA + "/numbers_pre_wf.json", encoding="utf-8"))["numbers"]
    ah = armA["house"]
    lab_wr = lab["win_rate"] / 100.0 if lab["win_rate"] > 1.0 else lab["win_rate"]
    rows = [("trades", lab["trades"], ah["trades"], abs(lab["trades"] - ah["trades"]) <= TOL["trades"]),
            ("net_usd", lab["net_usd"], round(ah["net_usd"], 2), abs(lab["net_usd"] - ah["net_usd"]) <= TOL["net_usd"]),
            ("roc_30k", lab["roc_30k"], round(ah["roc30"], 4), abs(lab["roc_30k"] - ah["roc30"]) <= TOL["roc_30k"]),
            ("dd5_usd", lab["dd5_usd"], ah["dd5"], abs(lab["dd5_usd"] - ah["dd5"]) <= TOL["dd5_usd"]),
            ("max_dd_usd", lab["max_dd_usd"], round(ah["max_dd"], 2), abs(lab["max_dd_usd"] - ah["max_dd"]) <= TOL["max_dd_usd"]),
            ("dd_pct_peak", lab["dd_pct_peak"], ah["dd_pct_peak"], abs(lab["dd_pct_peak"] - ah["dd_pct_peak"]) <= TOL["dd_pct_peak"]),
            ("sortino", lab["sortino"], round(ah["sortino"], 5), abs(lab["sortino"] - ah["sortino"]) <= TOL["sortino"]),
            ("one_episode", lab["one_episode"], ah["one_episode"], lab["one_episode"] == ah["one_episode"]),
            ("win_rate", lab["win_rate"], round(100 * ah["win_rate"], 4), abs(100 * lab_wr - 100 * ah["win_rate"]) <= TOL["win_rate_pct_points"]),
            ("trades_per_year", lab["trades_per_year"], round(ah["trades_per_yr"], 2), abs(lab["trades_per_year"] - ah["trades_per_yr"]) < 0.06),
            ("years", lab["years"], round(ah["years"], 4), abs(lab["years"] - ah["years"]) < 0.001),
            ("net_pts_per_trade", lab["net_pts_per_trade"], round(ah["net_per_trade_pts"], 4), abs(lab["net_pts_per_trade"] - ah["net_per_trade_pts"]) < 0.001),
            ("sessions", lab["sessions"], len(days), lab["sessions"] == len(days)),
            ("bars", json.load(open(IDEA + "/numbers_pre_wf.json"))["bars"], len(c), json.load(open(IDEA + "/numbers_pre_wf.json"))["bars"] == len(c))]
    res["lab_vs_arm_A"] = [{"field": f, "lab": a, "mine": b, "match": bool(ok)} for f, a, b, ok in rows]
    res["lab_vs_arm_A_all_match"] = all(x["match"] for x in res["lab_vs_arm_A"])
    exact_flags = {"net_usd": abs(lab["net_usd"] - round(ah["net_usd"], 2)) < 0.005, "roc_30k": lab["roc_30k"] == round(ah["roc30"], 2),
                   "dd5": lab["dd5_usd"] == ah["dd5"], "max_dd": abs(lab["max_dd_usd"] - round(ah["max_dd"], 2)) < 0.005,
                   "dd_pct": lab["dd_pct_peak"] == ah["dd_pct_peak"], "sortino": lab["sortino"] == round(ah["sortino"], 4)}
    res["lab_vs_arm_A_exact_at_printed_precision"] = exact_flags

    # ---- 1b. lab trades CSV vs arm A, trade by trade
    L = list(csv.DictReader(open(IDEA + "/pre_wf_trades.csv", encoding="utf-8")))
    n_same = sum(1 for t, x in zip(Ta, L) if t[0] == int(x["entry_bar"]) and t[1] == int(x["exit_bar"]) and t[2] == int(x["side"])
                 and abs(t[3] - float(x["entry_price"])) < 1e-9 and abs((t[4] - COST) - float(x["pnl_points_net"])) < 1e-5)
    res["lab_csv_vs_arm_A"] = {"lab_rows": len(L), "A_trades": len(Ta), "identical_rows": n_same,
                               "entry_times": sorted(set(x["entry_time"][11:16] for x in L))}

    # ---- 2. own rule the PLUGIN'S WAY: fill at session bar 12 (the only change); plugin-only filters shown inert
    sess_len = ends - starts
    zero_rng = int(sum(1 for s in starts if h[s:s + 12].max() - l[s:s + 12].min() <= 0))
    P = armb.own_rule(o, h, l, c, did, **PARAMS, entry_pos=12, short_needs_threshold=True)
    kp = {(t[0], t[2]): t for t in P}
    ka = {(t[0], t[2]): t for t in Ta}
    both = set(kp) & set(ka)
    exact = sum(1 for k in both if kp[k][1] == ka[k][1] and abs(kp[k][3] - ka[k][3]) < 1e-9 and abs(kp[k][5] - ka[k][4]) < 1e-9)
    res["own_rule_plugin_way"] = {
        "change_vs_arm_B": "entry_pos 13 -> 12 (fill at bar 12's open, 10:30 ET); nothing else changed",
        "plugin_only_filters_inert": {"min_session_bars": int(sess_len.min()), "sessions_under_15_bars": int((sess_len < 15).sum()),
                                      "first_hour_zero_range_sessions": zero_rng},
        "trades": len(P), "A_trades": len(Ta), "same_entry_and_side": len(both), "exact_entry_exit_px_pts": exact,
        "only_A": len(set(ka) - set(kp)), "only_mine": len(set(kp) - set(ka)),
        "matches_100pct": bool(exact == len(Ta) == len(P))}

    # ---- 3. literal readings (four numbers)
    variants = {
        "slip1_literal_entry_bar13 (= arm B)": {"entry_pos": 13, "short_needs_threshold": True},
        "slip2_literal_short_no_threshold (fill bar 12 as plugin)": {"entry_pos": 12, "short_needs_threshold": False},
        "both_literal (bar 13 + short no threshold)": {"entry_pos": 13, "short_needs_threshold": False},
    }
    lit = {}
    for name, kw in variants.items():
        V = armb.own_rule(o, h, l, c, did, **PARAMS, **kw)
        lit[name] = three([t[1] for t in V], [t[5] for t in V], idxn, days)
        lit[name]["gross_pts_sum"] = float(sum(t[5] for t in V))
        lit[name]["n_long"] = sum(1 for t in V if t[2] > 0)
        lit[name]["n_short"] = sum(1 for t in V if t[2] < 0)
    res["literal_readings"] = lit
    res["arm_A_gross_pts_sum"] = float(sum(t[4] for t in Ta))
    res["arm_A_n_long"] = sum(1 for t in Ta if t[2] > 0)
    res["arm_A_n_short"] = sum(1 for t in Ta if t[2] < 0)

    # ---- 4. look-ahead, on every plugin trade. The file is run on a slice = two previous sessions + the trade's session (so it
    # sees >= 50 bars). Session LENGTH is kept in the perturbation tests, because the file's own length filters (session < 15 bars,
    # entry bar = last bar) would otherwise drop a trade for a reason that is not look-ahead.
    #  (a) FUTURE GARBAGE after the exit bar: bars x+1..session end set to a flat price 1000 pts for / against the trade -> same trade
    #  (b) ENTRY: h/l/c of the fill bar e and every bar after it set to garbage (o[e] kept) -> same entry bar, side and entry price
    #  (c) TRUNCATION one bar before the exit (only where the length filters stay inert): the trade must still be open at x-1 and
    #      go flat at that bar's close, i.e. no stop was hit before x using later bars
    sess_of = np.searchsorted(starts, np.arange(len(c)), side="right") - 1
    na = nb = nc_ok = nc = 0
    bad = []

    def run_slice(oo, hh, ll, cc, dd):
        rr = m.run_backtest(oo, hh, ll, cc, None, dd, **PARAMS, return_trades=True)
        return (rr or {}).get("trades", [])

    for (e, x, sd, ep, pts) in Ta:
        si = sess_of[e]
        a0, b = starts[max(si - 2, 0)], ends[si]
        sl = slice(a0, b)
        base = [arr[sl].copy() for arr in (o, h, l, c)]
        dd = did[sl]
        ok_a = True
        for sign in (+1, -1):
            oo, hh, ll, cc = (z.copy() for z in base)
            if x + 1 < b:
                for z in (oo, hh, ll, cc):
                    z[x + 1 - a0:] = ep + sign * sd * 1000.0
            tt = [t for t in run_slice(oo, hh, ll, cc, dd) if t[0] + a0 == e]
            ok_a &= (len(tt) == 1 and tt[0][1] + a0 == x and tt[0][3] == sd and abs(tt[0][2] - pts) < 1e-9 and tt[0][4] == ep)
        na += ok_a
        oo, hh, ll, cc = (z.copy() for z in base)
        k = e - a0
        hh[k:] = ep + 5000.0
        ll[k:] = ep - 5000.0
        cc[k:] = ep + sd * 3000.0
        oo[k + 1:] = ep - sd * 2000.0
        tt = [t for t in run_slice(oo, hh, ll, cc, dd) if t[0] + a0 == e]
        ok_b = len(tt) == 1 and tt[0][3] == sd and tt[0][4] == ep
        nb += ok_b
        if x - starts[si] >= 15 and x - 1 > e:
            nc += 1
            cut = slice(a0, x)
            tt = [t for t in run_slice(o[cut], h[cut], l[cut], c[cut], did[cut]) if t[0] + a0 == e]
            ok_c = (len(tt) == 1 and tt[0][1] + a0 == x - 1 and tt[0][3] == sd and tt[0][4] == ep
                    and abs(tt[0][2] - sd * (c[x - 1] - ep)) < 1e-9)
            nc_ok += ok_c
        else:
            ok_c = True
        if not (ok_a and ok_b and ok_c) and len(bad) < 5:
            bad.append([str(idxn[e]), bool(ok_a), bool(ok_b), bool(ok_c)])
    res["lookahead_tests"] = {"trades": len(Ta), "a_future_garbage_after_exit_same_trade": int(na),
                              "b_garbage_from_fill_bar_hlc_same_entry_side_px": int(nb),
                              "c_truncated_before_exit_tested": nc, "c_still_open_flat_at_cut": int(nc_ok),
                              "failures_first5": bad, "pass": bool(na == nb == len(Ta) and nc_ok == nc)}

    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_trace.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()

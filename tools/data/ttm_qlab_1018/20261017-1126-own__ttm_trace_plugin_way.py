"""TTM stage 2 (COMPARE + TRACE) for Qwen Lab QL_GAPFILL_NQ (20261017-1126-own).

Run AFTER stage 1 posted ttm_verify.json (sha256 fbc3557c...) to MANAGER. Reads, for the first time, the lab's
numbers_pre_wf.json and pre_wf_trades.csv, and the plugin code.

 1. arm A (plugin through the engine, house booking) vs the lab's numbers_pre_wf.json field by field, and vs
    pre_wf_trades.csv trade by trade.
 2. TRACE: TTM's arm B rule file (ttm_armb_own_rule.py, UNCHANGED, sha pinned) re-run THE PLUGIN'S WAY - on the exact
    signal arrays the engine's roll plan hands the plugin (ROLL_SIGNAL = 'difference' -> Panama back-adjusted), fills
    mapped back to raw - must match the plugin 100% trade for trade.
    The slip (plugin vs the prereg's literal words): prior_close read on difference-adjusted prices, not the raw NOADJ
    close. Literal reading = arm B on raw prices; its four numbers at house / real / stress cost.
    Plus: the same file with ROLL_SIGNAL deleted (what the engine would pick on its own), and the 'trailing' word read
    as a trailing stop (an alternative reading both arms rejected; numbers only, for the verdict check).
 3. LOOK-AHEAD: every trade re-run with the data cut right after its exit bar (must be identical); every trade re-run
    with the data cut after its entry bar AND the entry bar's high/low/close replaced (open kept) - the side and the
    stop level must not move; the stop level is checked against the prior-session-only ATR.
 4. trade rate: gap > 20 pts frequency per year.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1126-own/."""
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1126-own"
IDEA_DIR = "C:/EdgeLog/qwen_lab/ideas/20261017-1126-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
from augur_engine import rolls as R                               # noqa: E402

PLUGIN = IDEA_DIR + "/plugin_v1.py.txt"
PIN_PLUGIN = "8b1ea950f9df6f38e6af740986294b82efa74e9a4f202ec2e32e29ba9b3969c4"
ARMB = os.path.join(OUT, "ttm_armb_own_rule.py")
ARMB_SHA = "a01cf8ac80875c37bd9bb4376a6ac401773446f22fce0b39da681e0448217f7c"
STAGE1_JSON = os.path.join(OUT, "ttm_verify.json")
STAGE1_SHA = "fbc3557c6caffe05f616129dbcab3eaa285aa0b1c5b4f960771769b18189f04e"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # 0.7825 pt
STRESS_COST = COST + 0.5               # 1.033 pt
PARAMS = {"gap_min_pts": 20.0, "stop_frac": 1.5, "atr_bars": 14}


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
            "dd5_n": int(r["n"]), "one_episode": bool(r["one_episode"]),
            "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    net = pts - cost
    usd = net * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    gw, gl = float(net[net > 0].sum()), float(-net[net < 0].sum())
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "gross_per_trade_pts": float(pts.mean()), "gross_over_cost": float(pts.mean() / cost),
              "net_per_trade_pts": float(net.mean()), "net_per_trade_usd": float(usd.mean()),
              "profit_factor": gw / gl if gl > 0 else float("inf"), "cost_pts_rt": cost})
    return f


def three(exit_bars, pts, idxn, days):
    return {"house": score(exit_bars, pts, idxn, days, COST), "real": score(exit_bars, pts, idxn, days, REAL_COST),
            "stress": score(exit_bars, pts, idxn, days, STRESS_COST)}


def line(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%.1f/yr) | $/yr %s | "
            "one_episode %s" % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"],
                                format(f["trades"], ","), f["trades_per_yr"], format(round(f["per_yr_usd"]), ","),
                                f["one_episode"]))


def load_plugin(drop_roll_signal=False):
    m = types.ModuleType("ttm_ql_gapfill_nq" + ("_noroll" if drop_roll_signal else ""))
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    if drop_roll_signal:
        del m.ROLL_SIGNAL
    return m


def sessions(day_id):
    st = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    return st, np.r_[st[1:], len(day_id)]


def trailing_rule(o, h, l, c, day_id, gap_min_pts, stop_frac, atr_bars):
    """ALTERNATIVE reading only ('trailing' = a trailing stop): same entry / ATR as arm B; the stop for bar j trails the
    best high (long) / low (short) of the COMPLETED bars a..j-1 at stop_frac x ATR (never loosens); a bar opening past
    the stop books its open, else a touch books the stop; else the session's last close."""
    starts, ends = sessions(day_id)
    out = []
    for si in range(1, len(starts)):
        s, e = starts[si], ends[si]
        ps, pe = starts[si - 1], ends[si - 1]
        gap = o[s] - c[pe - 1]
        side = 1 if gap > gap_min_pts else (-1 if gap < -gap_min_pts else 0)
        if side == 0 or pe - ps < atr_bars:
            continue
        a = pe - atr_bars
        tr = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) if j - 1 >= ps else h[j] - l[j]
              for j in range(a, pe)]
        atr = float(np.mean(tr))
        ep = o[s]
        best = ep
        stop = ep - side * stop_frac * atr
        xb, xp = e - 1, c[e - 1]
        for j in range(s, e):
            if j > s:
                best = max(best, h[j - 1]) if side > 0 else min(best, l[j - 1])
                stop = (max(stop, best - stop_frac * atr) if side > 0 else min(stop, best + stop_frac * atr))
                if side * (o[j] - stop) <= 0:
                    xb, xp = j, o[j]
                    break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
        out.append((int(s), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
    return out


def main():
    res = {}
    assert lf_sha(PLUGIN) == PIN_PLUGIN, "plugin pin"
    assert lf_sha(ARMB) == ARMB_SHA, "arm B file changed"
    assert hashlib.sha256(open(STAGE1_JSON, "rb").read()).hexdigest() == STAGE1_SHA, "stage-1 output changed"
    s1 = json.load(open(STAGE1_JSON))
    spec = importlib.util.spec_from_file_location("ttm_armb_own_rule", ARMB)
    armb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(armb)

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts, ends = sessions(day_id)
    n = len(c)
    res["data"] = {"bars": n, "fingerprint": A.get("fingerprint"), "sessions": len(days), "registry_id": row[0].get("id"),
                   "min_session_bars": int((ends - starts).min()),
                   "sessions_last_bar_not_1555": int(sum(1 for e in ends if idxn[e - 1].strftime("%H:%M") != "15:55"))}

    # ---------- ARM A: plugin through the engine (exactly stage 1's call) ----------
    mod = load_plugin()
    r = run_backtest(mod, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True, roll_diff=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    armA = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    st = (r.get("_meta") or {}).get("roll_stamp") or {}
    res["engine_roll_stamp"] = {k: st.get(k) for k in ("calendar", "signal_method", "method_source", "warning")
                                if k in st}
    rva = st.get("raw_vs_adjusted")
    res["engine_raw_vs_adjusted"] = rva if not isinstance(rva, dict) else {
        k: v for k, v in rva.items() if not isinstance(v, (list, dict)) or k in ("only_raw", "only_adjusted")}
    # stage-1 consistency
    s1h = s1["A_plugin"]["house_cost"]
    res["armA_equals_stage1"] = all(abs(armA["house"][k] - s1h[k]) < 1e-9 for k in
                                   ("net_usd", "roc30", "dd5", "max_dd", "dd_pct_peak", "sortino")) \
        and armA["house"]["trades"] == s1h["trades"]

    # ---------- 1. lab numbers_pre_wf.json field by field ----------
    lab = json.load(open(IDEA_DIR + "/numbers_pre_wf.json"))
    L = lab["numbers"]
    hA = armA["house"]
    tol = [  # (lab key, mine, tolerance, scale of lab value)
        ("trades", hA["trades"], 0, 1.0), ("net_usd", hA["net_usd"], 1.0, 1.0), ("roc_30k", hA["roc30"], 0.005, 1.0),
        ("dd5_usd", hA["dd5"], 1.0, 1.0), ("max_dd_usd", hA["max_dd"], 1.0, 1.0),
        ("dd_pct_peak", hA["dd_pct_peak"], 0.01, 1.0), ("sortino", hA["sortino"], 0.001, 1.0),
        ("win_rate", hA["win_rate"] * 100.0, 0.05, 1.0),
        # extra fields the lab prints (tolerance = its printed precision)
        ("years", hA["years"], 0.0005, 1.0), ("trades_per_year", hA["trades_per_yr"], 0.05, 1.0),
        ("sessions", len(days), 0, 1.0), ("dd5_n", hA["dd5_n"], 0, 1.0),
        ("net_pts_per_trade", hA["net_per_trade_pts"], 0.00005, 1.0),
        ("net_usd_per_trade", hA["net_per_trade_usd"], 0.005, 1.0),
        ("gross_pts_per_trade", hA["gross_per_trade_pts"], 0.00005, 1.0),
        ("gross_cost_ratio", hA["gross_over_cost"], 0.0005, 1.0), ("profit_factor", hA["profit_factor"], 0.00005, 1.0),
        ("cost_pts", COST, 0, 1.0), ("mult", MULT, 0, 1.0)]
    cmp = []
    for k, mine, t, _ in tol:
        lv = L.get(k)
        ok = lv is not None and abs(float(lv) - float(mine)) <= t + 1e-12
        cmp.append({"numbers_file": "numbers_pre_wf.json", "field": k, "lab": lv, "mine": round(float(mine), 6),
                    "tol": t, "match": bool(ok)})
    cmp.append({"numbers_file": "numbers_pre_wf.json", "field": "one_episode", "lab": L.get("one_episode"),
                "mine": hA["one_episode"], "tol": "equal", "match": L.get("one_episode") == hA["one_episode"]})
    for k, mine in (("bars", n), ("fingerprint", A.get("fingerprint")), ("window", "%s..%s" % (D0, D1)),
                    ("params", PARAMS), ("promoted", False)):
        cmp.append({"numbers_file": "numbers_pre_wf.json", "field": k, "lab": lab.get(k), "mine": mine, "tol": "equal",
                    "match": lab.get(k) == mine})
    cmp.append({"numbers_file": "numbers_pre_wf.json", "field": "roll.signal_method", "lab": lab["roll"]["signal_method"],
                "mine": st.get("signal_method", "difference"), "tol": "equal",
                "match": lab["roll"]["signal_method"] == st.get("signal_method", "difference")})

    # ---------- 1b. lab pre_wf_trades.csv trade by trade ----------
    tc = pd.read_csv(IDEA_DIR + "/pre_wf_trades.csv")
    nmatch = {"rows": len(tc), "armA": len(Ta)}
    if len(tc) == len(Ta):
        eb = tc["entry_bar"].to_numpy(int) == np.array([t[0] for t in Ta])
        xb = tc["exit_bar"].to_numpy(int) == np.array([t[1] for t in Ta])
        sd = tc["side"].to_numpy(int) == np.array([t[2] for t in Ta])
        ep = np.abs(tc["entry_price"].to_numpy(float) - np.array([t[3] for t in Ta])) < 1e-9
        pn = np.abs(tc["pnl_points_net"].to_numpy(float) - (np.array([t[4] for t in Ta]) - COST)) < 1e-5
        et = np.array([str(pd.Timestamp(x).tz_localize(None)) for x in tc["entry_time"]]) == \
            np.array([str(idxn[t[0]]) for t in Ta])
        xt = np.array([str(pd.Timestamp(x).tz_localize(None)) for x in tc["exit_time"]]) == \
            np.array([str(idxn[t[1]]) for t in Ta])
        nmatch.update({"entry_bar": int(eb.sum()), "exit_bar": int(xb.sum()), "side": int(sd.sum()),
                       "entry_price_raw": int(ep.sum()), "pnl_net_eq_gross_minus_0.533": int(pn.sum()),
                       "entry_time": int(et.sum()), "exit_time": int(xt.sum()),
                       "all_fields_all_rows": bool(eb.all() and xb.all() and sd.all() and ep.all() and pn.all()
                                                   and et.all() and xt.all()),
                       "csv_net_sum_usd": float(tc["pnl_points_net"].sum() * MULT)})
    for k, v in (("rows", nmatch.get("all_fields_all_rows")),):
        cmp.append({"numbers_file": "pre_wf_trades.csv", "field": "343 rows x (entry_bar, exit_bar, side, entry_price, "
                    "pnl_points_net+0.533, entry_time, exit_time)", "lab": "%d rows" % len(tc),
                    "mine": "%d trades" % len(Ta), "tol": "exact (pnl 1e-5)", "match": bool(v)})
    cmp.append({"numbers_file": "pre_wf_trades.csv", "field": "net_usd (sum pnl_points_net x $20)",
                "lab": round(nmatch.get("csv_net_sum_usd", float("nan")), 4), "mine": round(hA["net_usd"], 4), "tol": 1.0,
                "match": abs(nmatch.get("csv_net_sum_usd", 1e9) - hA["net_usd"]) <= 1.0})
    # the lab CSV re-scored with TTM's booking (independent of arm A's trade list)
    csv_gross = tc["pnl_points_net"].to_numpy(float) + COST
    csv_sc = score(tc["exit_bar"].to_numpy(int), csv_gross, idxn, days, COST)
    # the CSV prints pnl to 6 decimals, so its re-score is held to the task's tolerances, not to 1e-6
    for k, t in (("roc30", 0.005), ("dd5", 1.0), ("max_dd", 1.0), ("dd_pct_peak", 0.01), ("sortino", 0.001)):
        cmp.append({"numbers_file": "pre_wf_trades.csv (re-scored by TTM booking)", "field": k,
                    "lab": round(csv_sc[k], 6), "mine": round(hA[k], 6), "tol": t,
                    "match": abs(csv_sc[k] - hA[k]) <= t})
    res["lab_compare"] = cmp
    res["lab_csv_trade_match"] = nmatch
    res["verdict_compare"] = "VERIFIED EXACT" if all(x["match"] for x in cmp) else "DIFFERENCE"

    # ---------- 2. TRACE: arm B rule, the plugin's way (engine's own signal arrays) ----------
    Ameta = dict(A, meta=A.get("meta") or row[0])
    plan = R.plan_for(mod, Ameta, PLUGIN, {})
    Aadj = R.apply_plan(Ameta, plan)
    oa, ha, la, ca = (np.asarray(Aadj[k], float) for k in ("open", "high", "low", "close"))
    shift = o - oa      # per-bar raw - adjusted (constant within a contract segment; no mixed bars on RTH)
    res["plugin_way_plan"] = {"kind": plan.get("kind"), "method": plan.get("method"),
                              "method_source": plan.get("method_source"), "no_fill_bars": plan.get("no_fill_bars"),
                              "shift_test": (plan.get("tests") or {}).get("shift"),
                              "distinct_shifts_in_window": int(len(np.unique(np.round(shift, 6))))}
    Bp = armb.own_rule(oa, ha, la, ca, day_id, **PARAMS)      # arm B, unchanged, on the plugin's signal arrays
    Bp_raw = [(t[0], t[1], t[2], t[3] + shift[t[0]], t[5]) for t in Bp]   # fills mapped back to raw (difference: exact)
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in Bp_raw}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9
                and abs(ka[k][4] - kb[k][4]) < 1e-9)
    res["trace_plugin_way"] = {"plugin_trades": len(Ta), "armB_plugin_way_trades": len(Bp_raw),
                               "same_entry_side": len(both), "exact_entry_exit_side_px_pts": exact,
                               "only_plugin": len(set(ka) - set(kb)), "only_armB": len(set(kb) - set(ka)),
                               "max_abs_pts_diff": float(max(abs(ka[k][4] - kb[k][4]) for k in both)) if both else None,
                               "matches_100pct": bool(exact == len(Ta) == len(Bp_raw))}
    # the plugin's own function called directly on the same adjusted arrays (outside the engine) = the engine's list
    rd = mod.run_backtest(oa, ha, la, ca, day_id=day_id, return_trades=True, **PARAMS)
    res["trace_plugin_way"]["plugin_direct_on_adjusted_eq_engine"] = bool(
        [(t[0], t[1], t[3], round(t[2], 9)) for t in rd["trades"]] == [(t[0], t[1], t[2], round(t[4], 9)) for t in Ta])

    # ---------- the slip: literal raw prior close (arm B as built) ----------
    Bl = armb.own_rule(o, h, l, c, day_id, **PARAMS)
    lit = three([t[1] for t in Bl], [t[5] for t in Bl], idxn, days)
    rows_ = R.real_switches("NQ")
    sw_t = np.array([x["switch_sec"] for x in rows_])
    only_lit = sorted(set((t[0], t[2]) for t in Bl) - set(ka))
    ep_s = R.epoch_seconds(idx)
    detail = []
    for (eb_, sd_) in only_lit:
        si = int(np.searchsorted(starts, eb_))
        pe = ends[si - 1]
        j = int(np.searchsorted(sw_t, ep_s[eb_], side="right")) - 1
        rw = rows_[j]
        tb = [t for t in Bl if t[0] == eb_][0]
        detail.append({"session": str(idxn[eb_].date()), "side": sd_, "raw_gap": round(o[eb_] - c[pe - 1], 4),
                       "adjusted_gap": round(oa[eb_] - ca[pe - 1], 4), "roll": "%s->%s" % (rw["old"], rw["new"]),
                       "switch_et": rw["switch_et"], "offset_pts": rw["offset_pts"],
                       "offset_measured_et": rw.get("offset_sec") or "", "gross_pts": round(tb[5], 4),
                       "switch_before_entry_bar": bool(rw["switch_sec"] < ep_s[eb_])})
    res["slip_roll"] = {"literal_trades": len(Bl), "only_literal": len(only_lit), "only_literal_detail": detail,
                        "four_numbers": {k: line(v) for k, v in lit.items()},
                        "gross_per_trade_pts": lit["house"]["gross_per_trade_pts"],
                        "promotes_new_bar": bool(lit["house"]["gross_per_trade_pts"] >= COST and lit["house"]["roc30"] > 0
                                                 and not lit["house"]["one_episode"]),
                        "raw": {k: {kk: lit[k][kk] for kk in ("net_usd", "roc30", "dd5", "one_episode", "dd_pct_peak",
                                                             "sortino", "trades")} for k in lit}}

    # ---------- the same file with ROLL_SIGNAL deleted: what the engine picks on its own ----------
    mod2 = load_plugin(drop_roll_signal=True)
    r2 = run_backtest(mod2, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    st2 = (r2.get("_meta") or {}).get("roll_stamp") or {}
    T2 = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r2["trades"]]
    res["undeclared_roll_signal"] = {"calendar": st2.get("calendar"), "signal_method": st2.get("signal_method"),
                                     "method_source": st2.get("method_source"), "trades": len(T2),
                                     "identical_to_armA": T2 == Ta}

    # ---------- alternative reading: 'trailing' = a trailing stop (both arms rejected it) ----------
    Bt = trailing_rule(oa, ha, la, ca, day_id, **PARAMS)
    trl = three([t[1] for t in Bt], [t[5] for t in Bt], idxn, days)
    res["alt_trailing_stop"] = {"trades": len(Bt), "four_numbers": {k: line(v) for k, v in trl.items()},
                                "gross_per_trade_pts": trl["house"]["gross_per_trade_pts"],
                                "promotes_new_bar": bool(trl["house"]["gross_per_trade_pts"] >= COST
                                                         and trl["house"]["roc30"] > 0 and not trl["house"]["one_episode"])}

    # ---------- 3. LOOK-AHEAD ----------
    def run_slice(a0, a1, ov=None):
        oo, hh, ll, cc = oa[a0:a1].copy(), ha[a0:a1].copy(), la[a0:a1].copy(), ca[a0:a1].copy()
        if ov:
            for arr, k, v in ((hh, "h", None), (ll, "l", None), (cc, "c", None)):
                if k in ov:
                    arr[-1] = ov[k]
        dd = day_id[a0:a1]
        # pad: the plugin returns None for n < 50 - prepend bars of the session two back (they only feed session 0,
        # which the plugin skips, so they change nothing it reads)
        pad = 0
        if len(cc) < 50:
            pad = 50 - len(cc) + 1
            b0 = max(a0 - pad, 0)
            pad = a0 - b0
            oo, hh, ll, cc = (np.r_[x[b0:a0], y] for x, y in ((oa, oo), (ha, hh), (la, ll), (ca, cc)))
            dd = np.r_[np.full(pad, -999999), dd]
        rr = mod.run_backtest(oo, hh, ll, cc, day_id=dd, return_trades=True, **PARAMS)
        return [(t[0] - pad + a0, t[1] - pad + a0, t[3], t[4], t[2]) for t in (rr or {}).get("trades", [])], pad

    cut_exit_same = 0
    entry_side_same = 0
    stop_same = 0
    stop_vs_prior_atr = 0
    bad = []
    adj_by_entry = {t[0]: t for t in Bp}
    for (eb_, xb_, sd_, ep_raw, pts) in Ta:
        si = int(np.searchsorted(starts, eb_))
        # slice from TWO sessions back: session 0 of the slice is skipped by the plugin, session 1 (the prior session)
        # then has a full session before it, so the plugin's TR window never indexes before the slice start
        a_prev = starts[max(si - 2, 0)]
        # (a) data cut right after the exit bar: identical trade
        tr_, _ = run_slice(a_prev, xb_ + 1)
        mine = [t for t in tr_ if t[0] == eb_]
        if mine and mine[0][1] == xb_ and mine[0][2] == sd_ and abs(mine[0][4] - pts) < 1e-9:
            cut_exit_same += 1
        else:
            bad.append(("cut_exit", str(idxn[eb_])))
        # (b) data cut right after the ENTRY bar; entry bar's high/low/close moved (open kept) to force a stop hit
        far = 10000.0
        ov = {"l": oa[eb_] - far, "h": oa[eb_], "c": oa[eb_] - far} if sd_ > 0 else \
             {"h": oa[eb_] + far, "l": oa[eb_], "c": oa[eb_] + far}
        tr2, _ = run_slice(a_prev, eb_ + 1, ov)
        m2 = [t for t in tr2 if t[0] == eb_]
        if m2 and m2[0][2] == sd_:
            entry_side_same += 1
            stop_px = oa[eb_] + m2[0][4] * sd_          # exit px on the adjusted series = the stop level
            arm_b_stop = adj_by_entry[eb_][3] - sd_ * PARAMS["stop_frac"] * armb._atr_prior(
                ha, la, ca, starts[si - 1], ends[si - 1], PARAMS["atr_bars"])
            if abs(stop_px - arm_b_stop) < 1e-9:
                stop_vs_prior_atr += 1
            # (c) same cut, the entry bar's range moved the other way (no stop hit): stop must stay where it was
            ov3 = {"l": oa[eb_] - 1e-6, "h": oa[eb_] + 1e-6, "c": oa[eb_]}
            tr3, _ = run_slice(a_prev, eb_ + 1, ov3)
            m3 = [t for t in tr3 if t[0] == eb_]
            if m3 and m3[0][2] == sd_ and m3[0][1] == eb_:
                stop_same += 1
        else:
            bad.append(("entry_cut", str(idxn[eb_])))
    res["lookahead"] = {"trades": len(Ta), "cut_after_exit_identical": cut_exit_same,
                        "cut_after_entry_hlc_moved_same_entry_and_side": entry_side_same,
                        "stop_level_eq_prior_session_atr_stop": stop_vs_prior_atr,
                        "entry_kept_with_hlc_flattened": stop_same, "failures": bad[:10],
                        "signal_reads": "o[bar0] (the fill price itself) and c[prior session last bar]; ATR = prior "
                                        "session's last 14 bars + the close before them; stop fixed at entry; exits "
                                        "test bar j's own low/high only for a resting stop (fill at stop or j's open)"}

    # ---------- 4. trade rate ----------
    gaps = []
    for si in range(1, len(starts)):
        # gap on the plugin's (adjusted) signal series; price LEVEL from the raw tape (Panama levels are not prices)
        gaps.append((idxn[starts[si]].year, oa[starts[si]] - ca[ends[si - 1] - 1], o[starts[si]]))
    g = pd.DataFrame(gaps, columns=["year", "gap", "px"])
    g["hit"] = g["gap"].abs() > 20.0
    g["gap_pct"] = 100 * g["gap"].abs() / g["px"]
    res["trade_rate"] = {"sessions_with_prior": len(g), "gap_gt_20": int(g["hit"].sum()),
                         "share": float(g["hit"].mean()),
                         "by_year": {int(y): [int(d["hit"].sum()), len(d), round(float(d["px"].median()), 1),
                                              round(float(20.0 / d["px"].median() * 100), 3),
                                              round(float(d["gap"].abs().median()), 2)]
                                     for y, d in g.groupby("year")},
                         "by_year_cols": ["trades", "sessions", "median NQ open", "20 pts as % of price",
                                          "median |gap| pts"]}

    # trades whose exit is the session's last bar in the data while that bar is not 15:55 (half-days / data holes)
    short_end = []
    for (eb_, xb_, sd_, ep_raw, pts) in Ta:
        si = int(np.searchsorted(starts, eb_, side="right")) - 1
        e = ends[si]
        if idxn[e - 1].strftime("%H:%M") != "15:55":
            short_end.append({"session": str(idxn[eb_].date()), "last_bar": idxn[e - 1].strftime("%H:%M"),
                              "bars": int(e - starts[si]), "exit_is_last_bar": bool(xb_ == e - 1),
                              "gross_pts": round(pts, 4)})
    res["trades_on_short_sessions"] = short_end
    res["four_numbers_armA"] = {k: line(v) for k, v in armA.items()}
    res["armA_detail"] = {k: {kk: v[kk] for kk in ("net_usd", "per_yr_usd", "roc30", "dd5", "max_dd", "dd_pct_peak",
                                                   "sortino", "one_episode", "trades", "trades_per_yr", "win_rate",
                                                   "gross_per_trade_pts", "net_per_trade_pts", "gross_over_cost",
                                                   "cost_pts_rt", "profit_factor")} for k, v in armA.items()}
    hA = armA["house"]
    res["promotion_new_bar"] = {"gross_pt_per_trade": hA["gross_per_trade_pts"], "house_cost_pts": COST,
                                "real_cost_pts": REAL_COST, "gross_ge_house_cost": hA["gross_per_trade_pts"] >= COST,
                                "gross_ge_real_cost": hA["gross_per_trade_pts"] >= REAL_COST,
                                "roc30_house_gt_0": hA["roc30"] > 0, "one_episode": hA["one_episode"],
                                "promotes": bool(hA["gross_per_trade_pts"] >= COST and hA["roc30"] > 0
                                                 and not hA["one_episode"]),
                                "old_bar_roc_ge_15_and_not_one_episode": bool(hA["roc30"] >= 15 and not hA["one_episode"])}

    s = json.dumps(res, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_trace_plugin_way.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()

"""TTM (house verifier) STAGE 2 - COMPARE + TRACE for the Qwen Lab's QL_VOLBREAK_NQ (folder 20261017-1607-scalper).
Written AFTER stage 1 (ttm_verify.json sha256 20871fe15ab6... posted to MANAGER as #1480); only now are the lab's
numbers_pre_wf.json, pre_wf_trades.csv and the plugin code read.
  1. arm A (the plugin through the engine, re-run here) vs the lab's numbers_pre_wf.json field by field, and vs the lab's
     pre_wf_trades.csv trade by trade; the lab's own trade list re-booked by TTM's yardstick.
  2. TRACE: TTM's frozen own_rule (stage-1 arm B, imported from ttm_verify_B_frozen_before_plugin_read.py, sha ba04f38d...)
     extended with one switch per departure ('slip'); every switch at the TEXT value must reproduce arm B exactly, every switch
     at the PLUGIN value must reproduce the plugin trade for trade (b_plugin_way_matches_100pct). Each slip is scored alone
     (text + that slip; plugin minus that slip) at house / real / stress cost.
  3. look-ahead: code facts + a perturbation test on EVERY plugin trade (bars at/after the fill, bars after the exit).
  4. how often the prereg rule fires (degeneracy diagnosis).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1607-scalper/."""
import hashlib
import importlib.util
import json
import os
import sys
import types

os.environ["AUGUR_TRIAL_CACHE"] = "0"
import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1607-scalper"
OUT_JSON = os.path.join(OUT, "ttm_trace.json")
FROZEN = os.path.join(OUT, "ttm_verify_B_frozen_before_plugin_read.py")
FROZEN_SHA = "ba04f38df707f93c42fbca45ca7c19551c45d00d9e631f4bb563c5e76f3d3ff0"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1607-scalper"
LAB_NUMBERS = IDEA + "/numbers_pre_wf.json"
LAB_TRADES = IDEA + "/pre_wf_trades.csv"

assert hashlib.sha256(open(FROZEN, "rb").read()).hexdigest() == FROZEN_SHA, "frozen arm-B file changed"
_spec = importlib.util.spec_from_file_location("ttm_frozen_b", FROZEN)
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)          # chdir REPO + engine imports; main() not run (guarded)
from augur_engine.engine import run_backtest   # noqa: E402
from augur_engine.drawdowns import dd5 as _dd5, episodes as _episodes   # noqa: E402
from augur_engine import rolls as R            # noqa: E402

HOUSE, REAL, STRESS, MULT = F.HOUSE_COST, F.REAL_COST, F.STRESS_COST, F.MULT


# ------------------------------------------------------------------------------------------------------------------------------
def atr_traced(o, h, l, c, starts, ends, atr_n=14, atr_input="close_abs", smooth="wilder", scope="session"):
    """ATR with one switch per ATR departure. TEXT = close_abs / wilder / session (delegates to the FROZEN own_atr).
    PLUGIN = true_range / sma / global: atr[i] = mean(TR[i-13..i]), TR[0] = H-L, one series over the whole load."""
    if smooth == "wilder":
        return F.own_atr(c, h, l, starts, ends, atr_n=atr_n, atr_input=atr_input, atr_scope=scope, seed_mode="closes14")
    n = len(c)
    atr = np.full(n, np.nan)
    segs = list(zip(starts, ends)) if scope == "session" else [(0, n)]
    for s, e in segs:
        if atr_input == "close_abs":
            x = np.abs(np.diff(c[s:e]))                 # x[j] belongs to bar s+1+j
            off = 1
        else:
            pc = np.r_[np.nan, c[s:e - 1]]
            hh, ll = h[s:e], l[s:e]
            x = np.where(np.isnan(pc), hh - ll, np.maximum(hh, pc) - np.minimum(ll, pc))
            off = 0
        if len(x) < atr_n:
            continue
        cs = np.cumsum(np.r_[0.0, x])
        m = (cs[atr_n:] - cs[:-atr_n]) / atr_n          # mean of x[j-13..j] for j = 13..
        atr[s + off + atr_n - 1: s + off + atr_n - 1 + len(m)] = m
    return atr


def own_rule_traced(o, h, l, c, day_id, mins, wide_k=1.2, trail_k=2.0, atr_n=14, med_n=20, morning_bars=12, k_min=14,
                    multi=False, atr_input="close_abs", smooth="wilder", scope="session", trail_atr="signal"):
    """The FROZEN own_rule (stage-1 arm B), unchanged in every step, plus the slip switches:
      S1 multi      False = 'One trade per session (first qualifying signal)' (text) | True = re-scan from the bar after each
                    exit (plugin: k = x + 1)
      S2 ATR        (close_abs, wilder, session) = 'ATR(14) computed on 5m closes (trailing, seeded with first 14 closes)' (text
                    as TTM read it blind) | (true_range, sma, global) = plugin
      S3 trail_atr  'signal' = 'trail_k x atr_k' with k the signal bar (text) | 'current' = atr[j] of the bar just closed (plugin)
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    starts, ends = F.session_bounds(day_id)
    sidx = ((mins - 570) // 5).astype(int)
    atr = atr_traced(o, h, l, c, starts, ends, atr_n=atr_n, atr_input=atr_input, smooth=smooth, scope=scope)
    mr = np.full(len(starts), np.nan)
    for d, (s, e) in enumerate(zip(starts, ends)):
        msk = sidx[s:e] < morning_bars
        if msk.any():
            mr[d] = float(np.max(h[s:e][msk]) - np.min(l[s:e][msk]))
    out, hist = [], []
    for d, (s, e) in enumerate(zip(starts, ends)):
        today = mr[d]
        pool = hist[-med_n:]
        qual = bool(np.isfinite(today) and len(pool) >= med_n and today >= wide_k * float(np.median(pool)))
        if np.isfinite(today):
            hist.append(today)
        if not qual:
            continue
        k = s + 1
        while k < e - 1:                                  # k+1 must exist inside the session
            if sidx[k] < k_min or not np.isfinite(atr[k]) or atr[k] <= 0:
                k += 1
                continue
            a = atr[k]
            side = 1 if c[k] > c[k - 1] + a else (-1 if c[k] < c[k - 1] - a else 0)
            if side == 0:
                k += 1
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * trail_k * a
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if j > ent and side * (o[j] - stop) <= 0:
                    xb, xp = j, o[j]
                    break
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    xb, xp = j, stop
                    break
                aj = a if trail_atr == "signal" else (atr[j] if np.isfinite(atr[j]) else a)
                cand = c[j] - side * trail_k * aj
                stop = max(stop, cand) if side > 0 else min(stop, cand)
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            if not multi:
                break
            k = xb + 1
    return out


TEXT = dict(multi=False, atr_input="close_abs", smooth="wilder", scope="session", trail_atr="signal")
PLUG = dict(multi=True, atr_input="true_range", smooth="sma", scope="global", trail_atr="current")


def diff_trades(X, Y):
    """X, Y lists of (entry, exit, side, entry_px, exit_px, gross). Exact = same entry, side, exit bar and gross within 1e-6."""
    kx = {(t[0], t[2]): t for t in X}
    ky = {(t[0], t[2]): t for t in Y}
    both = set(kx) & set(ky)
    exact = sum(1 for k in both if kx[k][1] == ky[k][1] and abs(kx[k][5] - ky[k][5]) < 1e-6)
    return {"n_x": len(X), "n_y": len(Y), "same_entry_side": len(both), "exact": exact, "only_x": len(set(kx) - set(ky)),
            "only_y": len(set(ky) - set(kx)), "match_100pct": bool(len(X) == len(Y) == exact)}


def label_one_episode(daily):
    """The prereg's flag (MANAGER #160a): NOT TESTABLE when DD5 is one episode / the curve never makes a new high, else the
    dd5() flag (worst > 1.3 x DD5)."""
    r = _dd5(daily)
    return "NOT TESTABLE" if r["n"] <= 1 else bool(r["one_episode"]), int(r["n"]), int(r["episodes_total"])


def daily_series(exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    return pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)


def scored(T, idxn, days, cost):
    f = F.score([t[1] for t in T], [t[5] for t in T], idxn, days, cost)
    s = daily_series([t[1] for t in T], [t[5] for t in T], idxn, days, cost)
    lab, n5, ntot = label_one_episode(s)
    usd = (np.asarray([t[5] for t in T], float) - cost) * MULT
    f.update({"one_episode_prereg_160a": lab, "dd5_n": n5, "episodes_total": ntot,
              "profit_factor": float(usd[usd > 0].sum() / -usd[usd < 0].sum()) if (usd < 0).any() else float("inf")})
    f["promoted"] = bool(f["gross_per_trade_pts"] >= HOUSE and f["roc30"] > 0 and lab is False)
    return f


def line(f, cost_name, cost):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%.0f/yr) | $/yr %s | gross %.4f pt/trade vs "
            "cost %.4f pt (%s) | one-episode %s" %
            (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], format(f["trades"], ","),
             f["trades_per_yr"], format(round(f["per_yr_usd"]), ","), f["gross_per_trade_pts"], cost, cost_name,
             f["one_episode_prereg_160a"]))


def three(T, idxn, days):
    out = {}
    for name, cst in (("house_0.783", HOUSE), ("real_0.7825", REAL), ("stress_1.283", STRESS)):
        f = scored(T, idxn, days, cst)
        out[name] = {k: f[k] for k in ("trades", "trades_per_yr", "net_usd", "per_yr_usd", "roc30", "dd5", "dd5_n", "max_dd",
                                         "one_episode", "one_episode_prereg_160a", "dd_pct_peak", "sortino", "win_rate",
                                         "gross_per_trade_pts", "net_per_trade_pts", "profit_factor", "promoted")}
        out[name]["line"] = line(f, name.split("_")[0], cst)
    return out


# ------------------------------------------------------------------------------------------------------------------------------
def main():
    res = {"stage": "2 - compare + trace (post-read)", "frozen_b_file": FROZEN, "frozen_b_sha256": FROZEN_SHA}
    pin = F.lf_sha(F.PLUGIN)
    assert pin == F.PIN_FULL_PREREG
    res["plugin_lf_sha256"] = pin
    row, A, idxn, days, o, h, l, c, day_id, mins = F.load()
    sidx = ((mins - 570) // 5).astype(int)
    starts, ends = F.session_bounds(day_id)
    res.update({"bars": int(len(c)), "sessions": int(len(days)), "window": [str(days[0].date()), str(days[-1].date())],
                "years": float((days[-1] - days[0]).days / 365.25), "registry_id": row.get("id"),
                "sessions_with_bar_holes": int(sum(1 for s, e in zip(starts, ends) if sidx[e - 1] - sidx[s] + 1 != e - s)),
                "min_session_bars": int((ends - starts).min())})
    m = types.ModuleType("ttm_ql_volbreak_nq")
    m.__file__ = F.PLUGIN
    exec(compile(open(F.PLUGIN, encoding="utf-8").read(), F.PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    TA = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float("nan"), float(t[2])) for t in r["trades"]]
    res["A_engine"] = three(TA, idxn, days)
    res["A_engine"]["entry_px_equals_raw_open"] = int(sum(1 for t in TA if abs(t[3] - o[t[0]]) < 1e-9))

    # ---- 1. lab numbers file vs arm A (house cost) -----------------------------------------------------------------------
    lab = json.load(open(LAB_NUMBERS, encoding="utf-8"))
    L = lab["numbers"]
    fa = scored(TA, idxn, days, HOUSE)
    rows = []

    def cmp(field, labv, mine, tol, conv=None):
        if conv == "pct":
            ok = abs(float(labv) - 100.0 * mine) <= tol
        elif tol is None:
            ok = labv == mine
        else:
            ok = abs(float(labv) - float(mine)) <= tol
        rows.append({"numbers_file": "numbers_pre_wf.json", "field": field, "lab": labv, "mine": mine, "match": bool(ok)})

    cmp("trades", L["trades"], fa["trades"], None)
    cmp("net_usd", L["net_usd"], round(fa["net_usd"], 2), 1.0)
    cmp("roc_30k", L["roc_30k"], round(fa["roc30"], 4), 0.005)
    cmp("dd5_usd", L["dd5_usd"], fa["dd5"], 1.0)
    cmp("max_dd_usd", L["max_dd_usd"], round(fa["max_dd"], 2), 1.0)
    cmp("dd_pct_peak", L["dd_pct_peak"], round(fa["dd_pct_peak"], 4), 0.01)
    cmp("sortino", L["sortino"], round(fa["sortino"], 6), 0.001)
    cmp("one_episode", L["one_episode"], fa["one_episode_prereg_160a"], None)
    rows.append({"numbers_file": "numbers_pre_wf.json", "field": "one_episode (raw dd5() flag, worst > 1.3 x DD5)",
                 "lab": L["one_episode"], "mine": fa["one_episode"], "match": False})
    cmp("win_rate (lab %)", L["win_rate"], round(fa["win_rate"], 6), 0.05, conv="pct")
    cmp("dd5_n", L["dd5_n"], fa["dd5_n"], None)
    cmp("trades_per_year", L["trades_per_year"], round(fa["trades_per_yr"], 3), 0.05)
    cmp("years", L["years"], round(fa["years"], 4), 0.001)
    cmp("sessions", L["sessions"], int(len(days)), None)
    cmp("gross_pts_per_trade", L["gross_pts_per_trade"], round(fa["gross_per_trade_pts"], 6), 0.0001)
    cmp("cost_pts", L["cost_pts"], HOUSE, None)
    cmp("gross_cost_ratio", L["gross_cost_ratio"], round(fa["gross_over_cost"], 6), 0.0005)
    cmp("net_pts_per_trade", L["net_pts_per_trade"], round(fa["net_per_trade_pts"], 6), 0.0001)
    cmp("net_usd_per_trade", L["net_usd_per_trade"], round(fa["net_per_trade_usd"], 4), 0.005)
    cmp("profit_factor", L["profit_factor"], round(fa["profit_factor"], 6), 0.0001)
    cmp("mult", L["mult"], MULT, None)
    cmp("bars (top level)", lab["bars"], int(len(c)), None)
    cmp("params (top level)", lab["params"], {"wide_k": 1.2, "trail_k": 2.0, "atr_period": 14}, None)
    cmp("first_signal_bar_check.earliest_session_bar", lab["first_signal_bar_check"]["earliest_session_bar"],
        int(sidx[np.array([t[0] for t in TA])].min()), None)
    cmp("promoted (top level)", lab["promoted"], fa["promoted"], None)
    res["lab_vs_arm_a"] = rows
    res["lab_vs_arm_a_all_match_except_raw_flag"] = bool(all(x["match"] for x in rows if "raw dd5" not in x["field"]))
    res["lab_cost_lines"] = {"lab_cost_pts": L["cost_pts"], "house_cost_pts": HOUSE, "real_cost_pts": REAL,
                             "real_cost_basis": "$5.65 commission / $20 + 1 tick (0.25) each side = 0.2825 + 0.5 = 0.7825 pt",
                             "stress_cost_pts": STRESS, "lab_reports_real_cost": False}

    # ---- 1b. lab trade list vs arm A, trade by trade; lab list re-booked -------------------------------------------------
    lt = pd.read_csv(LAB_TRADES)
    lt_exit = pd.to_datetime(lt["exit_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None)
    lt_entry = pd.to_datetime(lt["entry_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None)
    ok_rows = 0
    worst = 0.0
    for i, t in enumerate(TA):
        rr = lt.iloc[i]
        d = abs(float(rr["pnl_points_net"]) - (t[5] - HOUSE))
        worst = max(worst, d)
        if (int(rr["entry_bar"]) == t[0] and int(rr["exit_bar"]) == t[1] and int(rr["side"]) == t[2]
                and abs(float(rr["entry_price"]) - t[3]) < 1e-9 and d < 1e-5
                and lt_entry.iloc[i] == idxn[t[0]] and lt_exit.iloc[i] == idxn[t[1]]):
            ok_rows += 1
    # the lab stamps entry_time / exit_time with the bar's OPEN clock (the master's index); both legs land on the same ET date
    exit_at_open = int(sum(1 for i, t in enumerate(TA) if lt_exit.iloc[i] == idxn[t[1]]))
    lab_daily = pd.Series(lt["pnl_points_net"].to_numpy(float) * MULT,
                          index=pd.DatetimeIndex(lt_exit).normalize()).groupby(level=0).sum()
    off_cal = float(lab_daily[~lab_daily.index.isin(days)].sum())
    lab_daily = lab_daily.reindex(days, fill_value=0.0)
    fl = F.four(lab_daily.to_numpy(), days)
    res["lab_trades_csv_vs_arm_a"] = {"lab_rows": int(len(lt)), "arm_a_trades": len(TA), "rows_identical": ok_rows,
                                      "worst_net_pts_diff": worst, "exit_time_equals_exit_bar_open": exit_at_open,
                                      "lab_csv_rebooked_by_ttm": {k: fl[k] for k in ("net_usd", "roc30", "dd5", "max_dd",
                                                                                      "dd_pct_peak", "sortino", "one_episode")},
                                      "lab_csv_usd_off_session_calendar": off_cal}

    # ---- 2. TRACE ---------------------------------------------------------------------------------------------------------
    plan = R.plan_for(m, dict(A, meta=row) if A.get("meta") is None else A, F.PLUGIN, {})
    Adj = R.apply_plan(dict(A, meta=row) if A.get("meta") is None else A, plan)
    oa, ha, la, ca = (np.asarray(Adj[k], float) for k in ("open", "high", "low", "close"))
    B_frozen = F.own_rule(o, h, l, c, day_id, mins, wide_k=1.2, trail_k=2.0)
    B_text = own_rule_traced(o, h, l, c, day_id, mins, **TEXT)
    P_raw = own_rule_traced(o, h, l, c, day_id, mins, **PLUG)
    P_adj = own_rule_traced(oa, ha, la, ca, day_id, mins, **PLUG)
    # the plugin itself, called directly on raw arrays (no engine), as a 3rd witness
    rp = m.run_backtest(o, h, l, c, day_id=day_id, return_trades=True)
    TP = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float("nan"), float(t[2])) for t in rp["trades"]]
    res["trace"] = {
        "text_switches": TEXT, "plugin_switches": PLUG,
        "traced_TEXT_vs_frozen_armB": diff_trades(B_text, B_frozen),
        "traced_PLUGIN_raw_vs_engine_A": diff_trades(P_raw, TA),
        "traced_PLUGIN_signal_adjusted_vs_engine_A": diff_trades(P_adj, TA),
        "plugin_direct_raw_vs_engine_A": diff_trades(TP, TA),
        "roll_plan": str(plan.get("kind")),
    }
    res["b_plugin_way_matches_100pct"] = bool(res["trace"]["traced_PLUGIN_raw_vs_engine_A"]["match_100pct"]
                                              and res["trace"]["traced_PLUGIN_signal_adjusted_vs_engine_A"]["match_100pct"]
                                              and res["trace"]["traced_TEXT_vs_frozen_armB"]["match_100pct"])
    variants = {
        "B_text_literal": TEXT,
        "text+S1_multi_trade": dict(TEXT, multi=True),
        "text+S2_plugin_ATR(TR,SMA,continuous)": dict(TEXT, atr_input="true_range", smooth="sma", scope="global"),
        "text+S2a_ATR_input_true_range_only": dict(TEXT, atr_input="true_range"),
        "text+S2b_ATR_SMA_not_Wilder_only": dict(TEXT, smooth="sma"),
        "text+S2c_ATR_continuous_across_sessions_only": dict(TEXT, scope="global"),
        "text+S3_trail_current_ATR": dict(TEXT, trail_atr="current"),
        "plugin_minus_S1(one_trade_per_session)": dict(PLUG, multi=False),
        "plugin_minus_S2(text_ATR)": dict(PLUG, atr_input="close_abs", smooth="wilder", scope="session"),
        "plugin_minus_S3(trail_signal_ATR)": dict(PLUG, trail_atr="signal"),
        "plugin_way_all_slips": PLUG,
    }
    V = {}
    for name, kw in variants.items():
        T = own_rule_traced(o, h, l, c, day_id, mins, **kw)
        V[name] = {"switches": kw, "trades": len(T), "sessions_traded": len({day_id[t[0]] for t in T}),
                   "median_hold_min": float(np.median([5 * (t[1] - t[0]) + 5 for t in T])) if T else None,
                   **three(T, idxn, days)}
    res["slip_variants"] = V
    # knob sensitivity of the literal reading (house cost) - is B's +0.60 a knife edge?
    g = {}
    for wk in (1.0, 1.1, 1.2, 1.3, 1.5):
        for tk in (1.5, 2.0, 2.5, 3.0):
            T = own_rule_traced(o, h, l, c, day_id, mins, wide_k=wk, trail_k=tk, **TEXT)
            f = scored(T, idxn, days, HOUSE)
            g["wide_k=%s,trail_k=%s" % (wk, tk)] = {"trades": f["trades"], "roc30": round(f["roc30"], 3),
                                                     "gross_pt": round(f["gross_per_trade_pts"], 4),
                                                     "one_ep": f["one_episode_prereg_160a"], "promoted": f["promoted"]}
    res["literal_knob_grid_house"] = g

    # ---- 3. look-ahead: perturbation on EVERY plugin trade ----------------------------------------------------------------
    rng = np.random.default_rng(20261018)
    sess_of = np.searchsorted(starts, np.arange(len(c)), side="right") - 1
    full = {(t[0], t[2]): t for t in TP}
    n_ctrl = n_ent = n_ext = n_ext_close = n_stop_exits = 0
    bad = []
    for t in TP:
        e, x, sd = t[0], t[1], t[2]
        si = sess_of[e]
        S, E = starts[max(0, si - 20)], ends[si]
        oo, hh, ll, cc, dd = o[S:E].copy(), h[S:E].copy(), l[S:E].copy(), c[S:E].copy(), day_id[S:E]

        def run(o2, h2, l2, c2):
            rr = m.run_backtest(o2, h2, l2, c2, day_id=dd, return_trades=True)
            return {(int(z[0]) + S, int(z[3])): (int(z[1]) + S, float(z[2])) for z in (rr["trades"] if rr else [])}

        ctrl = run(oo, hh, ll, cc)
        n_ctrl += int(ctrl.get((e, sd)) == (x, t[5]) or (ctrl.get((e, sd)) is not None and ctrl[(e, sd)][0] == x
                                                         and abs(ctrl[(e, sd)][1] - t[5]) < 1e-9))
        # (a) entry: move every high/low/close from the FILL bar on, and every open after it -> same entry bar/side/price
        i0 = e - S
        o2, h2, l2, c2 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
        z = rng.normal(0, 8.0, E - S - i0)
        c2[i0:] = cc[i0:] + z
        o2[i0 + 1:] = oo[i0 + 1:] + rng.normal(0, 8.0, E - S - i0 - 1)
        h2[i0:] = np.maximum.reduce([hh[i0:] + np.abs(rng.normal(0, 4, E - S - i0)), o2[i0:], c2[i0:]])
        l2[i0:] = np.minimum.reduce([ll[i0:] - np.abs(rng.normal(0, 4, E - S - i0)), o2[i0:], c2[i0:]])
        pe = run(o2, h2, l2, c2)
        if (e, sd) in pe:
            n_ent += 1
        else:
            bad.append(["entry", str(idxn[e]), sd])
        # (b) exit: move every bar AFTER the exit bar -> same exit bar and points
        i1 = x - S + 1
        if i1 < E - S:
            o3, h3, l3, c3 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
            c3[i1:] += rng.normal(0, 8.0, E - S - i1)
            o3[i1:] += rng.normal(0, 8.0, E - S - i1)
            h3[i1:] = np.maximum.reduce([h3[i1:] + 4, o3[i1:], c3[i1:]])
            l3[i1:] = np.minimum.reduce([l3[i1:] - 4, o3[i1:], c3[i1:]])
            px = run(o3, h3, l3, c3)
        else:
            px = ctrl
        if px.get((e, sd)) is not None and px[(e, sd)][0] == x and abs(px[(e, sd)][1] - t[5]) < 1e-9:
            n_ext += 1
        else:
            bad.append(["exit", str(idxn[e]), sd])
        # (c) a STOP exit's level must not read the exit bar's own close: move close[x] inside [low, high] -> same exit
        if x != ends[si] - 1:
            n_stop_exits += 1
            c4 = cc.copy()
            j = x - S
            c4[j] = ll[j] + rng.uniform(0, 1) * (hh[j] - ll[j])
            p4 = run(oo, hh, ll, c4)
            if p4.get((e, sd)) is not None and p4[(e, sd)][0] == x and abs(p4[(e, sd)][1] - t[5]) < 1e-9:
                n_ext_close += 1
            else:
                bad.append(["stop_close", str(idxn[e]), sd])
    res["lookahead"] = {
        "code_facts": [
            "signal at bar k reads close[k], close[k-1], atr[k] = mean TR[k-13..k] (TR[i] uses high/low[i], close[i-1]): all known at "
            "bar k's close; fill = open[k+1]",
            "initial stop = entry -/+ trail_k x atr[entry_bar-1] = atr[k] (the signal bar) - known before the fill",
            "stop at bar j is checked against the level set at bar j-1's close; the trail update with close[j]/atr[j] happens AFTER "
            "bar j's check and applies from bar j+1",
            "morning range = bars a..a+11 (complete at 10:30); first signal bar k = a+14 (closes 10:45), first fill bar 15 (10:45)",
            "trailing median = morning_ranges[sess-20:sess] - today excluded; morning_ranges is precomputed for all sessions but only "
            "past entries are read",
            "difference-adjusted signal arrays change nothing (raw and adjusted give the same 1396 trades): every ATR window the "
            "plugin reads starts at or after a session's 2nd bar, so a roll gap never enters a decision",
            "no size logic (1 contract), no target",
        ],
        "perturbation_all_trades": {"trades": len(TP), "slice_control_identical": n_ctrl,
                                    "entry_unchanged_when_fill_bar_hlc_and_later_bars_move": n_ent,
                                    "exit_unchanged_when_bars_after_exit_move": n_ext,
                                    "stop_exits": n_stop_exits,
                                    "stop_exit_unchanged_when_exit_bar_close_moves": n_ext_close,
                                    "failures_first": bad[:10]},
    }

    # ---- 4. how often the prereg rule fires --------------------------------------------------------------------------------
    atr_t = atr_traced(o, h, l, c, starts, ends)
    mr = np.array([h[s:s + 12].max() - l[s:s + 12].min() for s, e in zip(starts, ends)])
    fire = {}
    for wk in (1.0, 1.2, 1.5):
        q = np.zeros(len(starts), bool)
        for d in range(20, len(starts)):
            q[d] = mr[d] >= wk * np.median(mr[d - 20:d])
        sig_bars = 0
        sess_sig = 0
        for d in np.flatnonzero(q):
            s, e = starts[d], ends[d]
            k = np.arange(s + 14, e - 1)
            hit = (c[k] > c[k - 1] + atr_t[k]) | (c[k] < c[k - 1] - atr_t[k])
            sig_bars += int(hit.sum())
            sess_sig += int(hit.any())
        fire["wide_k=%s" % wk] = {"sessions_eligible(20 prior)": int(len(starts) - 20), "qualifying_sessions": int(q.sum()),
                                  "qualifying_pct": round(100 * q.sum() / (len(starts) - 20), 2),
                                  "qualifying_sessions_with_a_signal": sess_sig,
                                  "signal_bars_on_qualifying_sessions": sig_bars,
                                  "one_trade_per_session_trades_per_yr": round(sess_sig / res["years"], 2)}
    k_all = np.array([k for s, e in zip(starts, ends) for k in range(s + 14, e - 1)])
    hit_all = (c[k_all] > c[k_all - 1] + atr_t[k_all]) | (c[k_all] < c[k_all - 1] - atr_t[k_all])
    fire["all_sessions_no_filter"] = {"bars_tested": int(len(k_all)), "signal_bars": int(hit_all.sum()),
                                      "signal_bar_pct": round(100 * hit_all.mean(), 2),
                                      "sessions_with_a_signal": int(len({day_id[k] for k in k_all[hit_all]}))}
    res["rule_fire_counts_literal"] = fire
    res["prereg_stated_trades_per_yr"] = 80.0
    res["lab_reported_trades"] = L["trades"]
    res["lab_reported_dd5_n"] = L["dd5_n"]

    s = json.dumps(res, indent=1, sort_keys=False, default=lambda v: v.item() if hasattr(v, "item") else str(v)) + "\n"
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)
    print(s)
    print("output", OUT_JSON, "sha256", hashlib.sha256(open(OUT_JSON, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()

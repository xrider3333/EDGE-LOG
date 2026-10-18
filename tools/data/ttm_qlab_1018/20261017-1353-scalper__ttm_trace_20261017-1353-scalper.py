"""TTM (house verifier): STAGE 2 - COMPARE + TRACE for the Qwen Lab's QL_LATEBREAK_NQ (20261017-1353-scalper).
Run after stage 1 (ttm_verify.json, sha256 4240af72...) was posted to MANAGER; the lab's numbers may now be read.
 1. arm A (the plugin through the engine, house cost) vs EACH lab file: numbers_pre_wf.json field by field (with the
    MANAGER tolerances), pre_wf_trades.csv trade for trade, sandbox_pre_wf_out.json trade for trade.
 2. TTM's own rule re-run THE PLUGIN'S WAY (its warm-up: session 0 never quiet-filtered, >= 5 prior sessions, median of
    up to 20 prior) must equal the plugin 100% trade for trade; the LITERAL reading (a full trailing 20) must equal arm B.
    The plugin's other guards (session < 32 bars skipped, MR <= 0 skipped) are counted to show they never bind here.
 3. look-ahead probes on the plugin: (a) truncation at 40 session boundaries - every trade before the cut unchanged;
    (b) perturbation of every bar AFTER the decision bar (fill bar's high/low/close, later bars' OHLC) in every trade
    session at once, 10 seeds - entry bar, side and entry px unchanged; (c) timing audit on every trade - entry px =
    o[e], bar e-1's close beyond the morning range, no earlier afternoon close beyond it, stop level = entry -/+ 1.5 MR.
 4. how often the prereg rule fires (the funnel), in TTM's own literal build, plus the quiet_k grid's trade counts.
 5. the four numbers (house / real / +1-tick stress) for arm A and the literal reading.
Writes only into the output folder."""
import hashlib
import json
import math
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1353-scalper"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1353-scalper"
sys.path.insert(0, REPO)
sys.path.insert(0, OUT)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
from ttm_own_rule_b import own_rule                               # noqa: E402

PLUGIN = IDEA + "/plugin_v1.py.txt"
PIN_FULL = "c3c2db5917567392a463d906dc84b45a1d0d4fc9eceb8e99ee4157fa53ac6040"
ARM_B_PRELOCK = "a1161c8a4252319c2b30842d0df6622e20dae0f706d47eb7730745b358a795f8"
STAGE1_JSON, STAGE1_SHA = OUT + "/ttm_verify.json", "4240af7276c33bdf338b878225317a40678bee7f65962b80d00339434a2d5212"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
HOUSE_COST = 0.783
REAL_COST = 0.25 * 2 + 5.65 / MULT       # $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = HOUSE_COST + 0.5           # +1 tick each side on top of house cost


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# ---------------------------------------------------------------- TTM's rule, with the warm-up as a switch
def rule(o, h, l, c, day_id, quiet_k, stop_frac, warmup="literal", lookback=20, morning_bars=12, first_signal_idx=30,
         min_prior=5, plugin_guards=False, funnel=None):
    """warmup='literal': the prereg's 'trailing 20 sessions' read as a FULL 20 prior (= arm B, R3).
    warmup='plugin': the plugin's way - session 0 of the load is never quiet-filtered ('if i >= 1'); sessions 1.. need
    >= min_prior finite prior MRs; the median is over up to `lookback` prior sessions.
    plugin_guards: also apply the plugin's 'session < 32 bars -> skip' and 'MR <= 0 -> skip' (shown not to bind).
    Everything else is arm B's R1-R9 verbatim. Returns (entry, exit, side, entry_px, exit_px, gross, stop, k)."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    day_id = np.asarray(day_id)
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    mr = np.full(len(starts), np.nan)
    mhi = np.full(len(starts), np.nan)
    mlo = np.full(len(starts), np.nan)
    for i, (s, e) in enumerate(zip(starts, ends)):
        if e - s >= morning_bars:
            mhi[i] = h[s:s + morning_bars].max()
            mlo[i] = l[s:s + morning_bars].min()
            mr[i] = mhi[i] - mlo[i]
    F = {"sessions": len(starts), "warmup_skip": 0, "no_mr": 0, "guard_short_session": 0, "guard_mr_le_0": 0,
         "quiet_fail": 0, "quiet_pass": 0, "no_afternoon_close_beyond": 0, "first_break_on_last_bar": 0,
         "trades": 0, "quiet_unfiltered_session0": 0}
    out = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if plugin_guards and e - s < 32:
            F["guard_short_session"] += 1
            continue
        if not np.isfinite(mr[i]):
            F["no_mr"] += 1
            continue
        if plugin_guards and mr[i] <= 0:
            F["guard_mr_le_0"] += 1
            continue
        if warmup == "literal":
            if i < lookback:
                F["warmup_skip"] += 1
                continue
            prior = mr[i - lookback:i]
            if not np.all(np.isfinite(prior)):
                F["warmup_skip"] += 1
                continue
            quiet = mr[i] <= quiet_k * float(np.median(prior))
        else:
            if i >= 1:
                prior = mr[max(0, i - lookback):i]
                prior = prior[np.isfinite(prior)]
                if len(prior) < min_prior:
                    F["warmup_skip"] += 1
                    continue
                quiet = not (mr[i] > quiet_k * float(np.median(prior)))
            else:
                quiet = True                      # the plugin's session 0: no filter at all
                F["quiet_unfiltered_session0"] += 1
        if not quiet:
            F["quiet_fail"] += 1
            continue
        F["quiet_pass"] += 1
        k = None
        side = 0
        for j in range(s + first_signal_idx, e):
            if c[j] > mhi[i]:
                k, side = j, 1
                break
            if c[j] < mlo[i]:
                k, side = j, -1
                break
        if k is None:
            F["no_afternoon_close_beyond"] += 1
            continue
        if k + 1 >= e:
            F["first_break_on_last_bar"] += 1
            continue
        ent = k + 1
        ep = o[ent]
        stop = ep - side * stop_frac * mr[i]
        xb, xp = e - 1, c[e - 1]
        for j in range(ent, e):
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp = j, o[j]
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
        out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep)), float(stop), int(k)))
        F["trades"] += 1
    if funnel is not None:
        funnel.update(F)
    return out


# ---------------------------------------------------------------- the house booking
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
    g = np.asarray(pts_gross, float)
    usd = (g - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum()
    assert set(s.index) <= set(days), "exit day outside the calendar"
    s = s.reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    net_pts = g - cost
    gw, gl = net_pts[net_pts > 0].sum(), -net_pts[net_pts < 0].sum()
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "cost_pts": cost, "gross_pts_per_trade": float(g.mean()), "net_pts_per_trade": float(net_pts.mean()),
              "net_usd_per_trade": float(usd.mean()), "gross_over_cost": float(g.mean() / cost) if cost else None,
              "profit_factor": float(gw / gl) if gl > 0 else None, "sessions": len(days)})
    f["promotion_mgr129"] = bool(f["gross_pts_per_trade"] >= HOUSE_COST and f["roc30"] > 0 and f["one_episode"] is False)
    f["promotion_old_roc15"] = bool(f["roc30"] >= 15 and f["one_episode"] is False)
    return f


def fmt4(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%d/yr) | $/yr %s"
            % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], format(f["trades"], ","),
               round(f["trades_per_yr"]), format(round(f["per_yr_usd"]), ",")))


def costs_block(exit_bars, gross, idxn, days):
    return {"house": score(exit_bars, gross, idxn, days, HOUSE_COST), "real": score(exit_bars, gross, idxn, days, REAL_COST),
            "stress": score(exit_bars, gross, idxn, days, STRESS_COST),
            "zero": score(exit_bars, gross, idxn, days, 0.0)}


def match_trades(P, Q):
    """P, Q: lists of (entry, exit, side, entry_px, gross). Exact trade-for-trade comparison."""
    kp = {(t[0], t[2]): t for t in P}
    kq = {(t[0], t[2]): t for t in Q}
    both = sorted(set(kp) & set(kq))
    exact = [k for k in both if kp[k][1] == kq[k][1] and abs(kp[k][3] - kq[k][3]) < 1e-9 and abs(kp[k][4] - kq[k][4]) < 1e-6]
    return {"n_P": len(P), "n_Q": len(Q), "same_entry_side": len(both), "exact": len(exact),
            "only_P": len(set(kp) - set(kq)), "only_Q": len(set(kq) - set(kp)),
            "pct_exact": 100.0 * len(exact) / max(len(P), len(Q), 1),
            "first_diffs": [[k, kp.get(k), kq.get(k)] for k in sorted(set(kp) | set(kq)) if k not in set(exact)][:5]}


def main():
    assert hashlib.sha256(open(STAGE1_JSON, "rb").read()).hexdigest() == STAGE1_SHA, "stage-1 output changed"
    assert lf_sha(PLUGIN) == PIN_FULL, "plugin pin"
    assert lf_sha(OUT + "/ttm_own_rule_b.py") == ARM_B_PRELOCK, "arm B changed after the pre-lock"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(did)) + 1]
    ends = np.r_[starts[1:], len(c)]
    sess_of_bar = np.repeat(np.arange(len(starts)), ends - starts)
    sess_len = (ends - starts)
    res = {"idea": "QL_LATEBREAK_NQ", "stage": "2 - COMPARE + TRACE", "stage1_sha256": STAGE1_SHA,
           "plugin_lf_sha256": lf_sha(PLUGIN), "trace_lf_sha256": lf_sha(os.path.abspath(__file__)),
           "bars": len(c), "fingerprint": A.get("fingerprint"), "sessions": len(starts),
           "master_first_bar": str(idx[0]), "session_length_counts": {int(k): int(v) for k, v in
                                                                      zip(*np.unique(sess_len, return_counts=True))}}

    # ---- ARM A ----
    m = types.ModuleType("ttm_ql_latebreak")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    knobs = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    XA, GA = [t[1] for t in Ta], [t[4] for t in Ta]
    armA = costs_block(XA, GA, idxn, days)
    res["A_four"] = {k: fmt4(v) for k, v in armA.items()}
    res["A_numbers"] = armA

    # ---- 1. arm A vs the lab's files ----
    lab = json.load(open(IDEA + "/numbers_pre_wf.json", encoding="utf-8"))
    L = lab["numbers"]
    H = armA["house"]
    wr_lab = L["win_rate"] / 100.0 if L["win_rate"] > 1.0 else L["win_rate"]
    rows = [  # (lab field, lab value, mine, tolerance or None for exact)
        ("trades", L["trades"], H["trades"], 0),
        ("net_usd", L["net_usd"], round(H["net_usd"], 2), 1.0),
        ("roc_30k", L["roc_30k"], round(H["roc30"], 4), 0.005),
        ("dd5_usd", L["dd5_usd"], H["dd5"], 1.0),
        ("max_dd_usd", L["max_dd_usd"], round(H["max_dd"], 2), 1.0),
        ("dd_pct_peak", L["dd_pct_peak"], H["dd_pct_peak"], 0.01),
        ("sortino", L["sortino"], round(H["sortino"], 4), 0.001),
        ("one_episode", L["one_episode"], H["one_episode"], "eq"),
        ("win_rate (lab %)", L["win_rate"], round(100 * H["win_rate"], 4), 0.05),
        ("trades_per_year", L["trades_per_year"], round(H["trades_per_yr"], 2), 0.05),
        ("years", L["years"], round(H["years"], 4), 0.001),
        ("sessions", L["sessions"], H["sessions"], 0),
        ("dd5_n", L["dd5_n"], H["dd5_n"], 0),
        ("net_pts_per_trade", L["net_pts_per_trade"], round(H["net_pts_per_trade"], 4), 0.0001),
        ("net_usd_per_trade", L["net_usd_per_trade"], round(H["net_usd_per_trade"], 2), 0.01),
        ("profit_factor", L["profit_factor"], round(H["profit_factor"], 4), 0.0001),
        ("cost_pts", L["cost_pts"], HOUSE_COST, 0),
        ("mult", L["mult"], MULT, 0),
        ("gross_pts_per_trade", L["gross_pts_per_trade"], round(H["gross_pts_per_trade"], 4), 0.0001),
        ("gross_cost_ratio", L["gross_cost_ratio"], round(H["gross_over_cost"], 4), 0.001),
        ("bars", lab["bars"], len(c), 0),
        ("fingerprint", lab["fingerprint"], A.get("fingerprint"), "eq"),
        ("params", lab["params"], knobs, "eq"),
        ("promoted", lab["promoted"], H["promotion_mgr129"], "eq"),
    ]
    cmp_rows = []
    for name, lv, mv, tol in rows:
        if tol == "eq":
            ok = lv == mv
        elif tol == 0:
            ok = lv == mv
        else:
            ok = abs(float(lv) - float(mv)) <= tol
        cmp_rows.append({"file": "numbers_pre_wf.json", "field": name, "lab": lv, "mine": mv, "tol": tol, "match": bool(ok)})
    # pre_wf_trades.csv trade for trade
    csv = pd.read_csv(IDEA + "/pre_wf_trades.csv")
    Tc = [(int(rw.entry_bar), int(rw.exit_bar), int(rw.side), float(rw.entry_price), float(rw.pnl_points_net) + HOUSE_COST)
          for rw in csv.itertuples()]
    mc = match_trades(Ta, Tc)
    times_ok = int(sum(1 for rw in csv.itertuples()
                       if pd.Timestamp(rw.entry_time).tz_localize(None) == idxn[int(rw.entry_bar)]
                       and pd.Timestamp(rw.exit_time).tz_localize(None) == idxn[int(rw.exit_bar)]))
    csvB = costs_block([t[1] for t in Tc], [t[4] for t in Tc], idxn, days)["house"]
    cmp_rows.append({"file": "pre_wf_trades.csv", "field": "trade-for-trade (entry bar, side, exit bar, entry px, "
                     "net pts + 0.783 = gross)", "lab": len(Tc), "mine": len(Ta), "exact": mc["exact"],
                     "match": mc["exact"] == len(Ta) == len(Tc)})
    cmp_rows.append({"file": "pre_wf_trades.csv", "field": "entry/exit timestamps = master bar times", "lab": times_ok,
                     "mine": len(Ta), "match": times_ok == len(Ta)})
    cmp_rows.append({"file": "pre_wf_trades.csv", "field": "four numbers re-booked from the CSV (house cost)",
                     "lab": fmt4(csvB), "mine": fmt4(H), "match": fmt4(csvB) == fmt4(H)
                     and abs(csvB["net_usd"] - H["net_usd"]) < 0.01})
    sb = json.load(open(IDEA + "/sandbox_pre_wf_out.json", encoding="utf-8"))
    Ts = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2]) + HOUSE_COST) for t in sb["trades"]]
    ms = match_trades(Ta, Ts)
    cmp_rows.append({"file": "sandbox_pre_wf_out.json", "field": "trade-for-trade", "lab": len(Ts), "mine": len(Ta),
                     "exact": ms["exact"], "match": ms["exact"] == len(Ta) == len(Ts)})
    cmp_rows.append({"file": "sandbox_pre_wf_out.json", "field": "bars / fingerprint / params", "lab":
                     [sb["bars"], sb["fingerprint"], sb["params"]], "mine": [len(c), A.get("fingerprint"), knobs],
                     "match": [sb["bars"], sb["fingerprint"], sb["params"]] == [len(c), A.get("fingerprint"), knobs]})
    res["lab_vs_arm_a"] = cmp_rows
    res["lab_vs_arm_a_all_match"] = all(x["match"] for x in cmp_rows)
    res["lab_promotion_line"] = lab.get("promotion")

    # ---- 2. TTM's rule the plugin's way vs the plugin; the literal way vs arm B ----
    Fp, Fl, Fpg = {}, {}, {}
    Pw = rule(o, h, l, c, did, knobs["quiet_k"], knobs["stop_frac"], warmup="plugin", plugin_guards=True, funnel=Fp)
    Lw = rule(o, h, l, c, did, knobs["quiet_k"], knobs["stop_frac"], warmup="literal", funnel=Fl)
    Lg = rule(o, h, l, c, did, knobs["quiet_k"], knobs["stop_frac"], warmup="literal", plugin_guards=True, funnel=Fpg)
    B = own_rule(o, h, l, c, did, quiet_k=knobs["quiet_k"], stop_frac=knobs["stop_frac"])
    tp = [(t[0], t[1], t[2], t[3], t[5]) for t in Pw]
    tl = [(t[0], t[1], t[2], t[3], t[5]) for t in Lw]
    tb = [(t[0], t[1], t[2], t[3], t[5]) for t in B]
    res["plugin_way_vs_plugin"] = match_trades(tp, Ta)
    res["b_plugin_way_matches_100pct"] = bool(res["plugin_way_vs_plugin"]["exact"] == len(Ta) == len(tp))
    res["literal_vs_armB"] = match_trades(tl, tb)
    res["literal_plus_plugin_guards_vs_literal"] = match_trades([(t[0], t[1], t[2], t[3], t[5]) for t in Lg], tl)
    res["funnel_plugin_way"] = Fp
    res["funnel_literal"] = Fl
    res["funnel_literal_with_plugin_guards"] = Fpg
    lit = costs_block([t[1] for t in Lw], [t[5] for t in Lw], idxn, days)
    res["literal_four"] = {k: fmt4(v) for k, v in lit.items()}
    res["literal_numbers"] = lit
    first20 = [t for t in Pw if sess_of_bar[t[0]] < 20]
    res["slip_warmup_trades"] = {"plugin_trades_in_first_20_sessions": len(first20),
                                 "their_gross_pts": round(float(sum(t[5] for t in first20)), 2),
                                 "their_net_usd_house": round(float(sum((t[5] - HOUSE_COST) * MULT for t in first20)), 2),
                                 "session_numbers": sorted(set(int(sess_of_bar[t[0]]) for t in first20))}

    # ---- 3. look-ahead probes on the plugin (direct call, raw arrays: first shown equal to the engine) ----
    def plug(o_, h_, l_, c_, d_):
        rr = m.run_backtest(o_, h_, l_, c_, None, day_id=d_, index=None, return_trades=True, **knobs)
        return [] if rr is None else [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in rr["trades"]]
    Td = plug(o, h, l, c, did)
    res["direct_call_vs_engine"] = match_trades(Td, Ta)
    rng = np.random.default_rng(20261018)
    cuts = sorted(rng.choice(np.arange(25, len(starts) - 1), size=40, replace=False))
    trunc_bad = 0
    trunc_checked = 0
    for ci in cuts:
        cb = int(starts[ci])
        Tt = plug(o[:cb], h[:cb], l[:cb], c[:cb], did[:cb])
        ref = [t for t in Td if t[1] < cb]
        trunc_checked += len(ref)
        mm = match_trades(Tt, ref)
        trunc_bad += (mm["only_P"] + mm["only_Q"] + (mm["same_entry_side"] - mm["exact"]))
    res["lookahead_truncation"] = {"cuts": len(cuts), "trades_checked": trunc_checked, "mismatches": trunc_bad}
    pert_bad = 0
    pert_entry_px_bad = 0
    for seed in range(10):
        g = np.random.default_rng(1000 + seed)
        o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
        for t in Td:
            e = t[0]
            b_end = int(ends[sess_of_bar[e]])
            nb = b_end - e
            shock = g.normal(0, 40.0, size=nb)
            c2[e:b_end] = c[e:b_end] + shock
            o2[e + 1:b_end] = o[e + 1:b_end] + g.normal(0, 40.0, size=nb - 1)
            h2[e:b_end] = np.maximum.reduce([h[e:b_end] + np.abs(g.normal(0, 40.0, size=nb)), o2[e:b_end], c2[e:b_end]])
            l2[e:b_end] = np.minimum.reduce([l[e:b_end] - np.abs(g.normal(0, 40.0, size=nb)), o2[e:b_end], c2[e:b_end]])
        Tq = plug(o2, h2, l2, c2, did)
        kq = {(t[0], t[2]): t for t in Tq}
        for t in Td:
            q = kq.get((t[0], t[2]))
            if q is None:
                pert_bad += 1
            elif abs(q[3] - t[3]) > 1e-9:
                pert_entry_px_bad += 1
        pert_bad += len(set(kq) - set((t[0], t[2]) for t in Td))
    res["lookahead_perturbation"] = {"seeds": 10, "trades_per_seed": len(Td),
                                     "perturbed": "fill bar high/low/close and every later bar's OHLC of every trade "
                                                  "session (noise sd 40 pt, OHLC kept consistent)",
                                     "entry_or_side_changed": pert_bad, "entry_px_changed": pert_entry_px_bad}
    # (c) timing audit on every plugin trade
    mr_s = np.array([h[s:s + 12].max() - l[s:s + 12].min() for s in starts])
    mhi_s = np.array([h[s:s + 12].max() for s in starts])
    mlo_s = np.array([l[s:s + 12].min() for s in starts])
    aud = {"entry_px_eq_open": 0, "decision_bar_close_beyond": 0, "no_earlier_afternoon_break": 0,
           "stop_level_ok_on_stopped": 0, "stopped": 0, "decision_bar_idx_ge_30": 0, "n": len(Td)}
    for t in Td:
        e, x, sd, ep, gp = t
        si = sess_of_bar[e]
        s0 = starts[si]
        k = e - 1
        aud["entry_px_eq_open"] += int(abs(o[e] - ep) < 1e-9)
        aud["decision_bar_idx_ge_30"] += int(k - s0 >= 30)
        aud["decision_bar_close_beyond"] += int((c[k] > mhi_s[si]) if sd > 0 else (c[k] < mlo_s[si]))
        aud["no_earlier_afternoon_break"] += int(not any((c[j] > mhi_s[si]) or (c[j] < mlo_s[si]) for j in range(s0 + 30, k)))
        if x != ends[si] - 1 or abs(gp - sd * (c[x] - ep)) > 1e-9:
            aud["stopped"] += 1
            stop = ep - sd * knobs["stop_frac"] * mr_s[si]
            xp = ep + sd * gp
            aud["stop_level_ok_on_stopped"] += int(abs(xp - stop) < 1e-6 or (x > e and abs(xp - o[x]) < 1e-9
                                                                              and sd * (o[x] - stop) <= 0))
    res["lookahead_timing_audit"] = aud

    # ---- 4. how often the rule fires; quiet_k grid ----
    grid = {}
    for qk in (1.0, 1.5, 2.0, 3.0, 99.0):
        ff = {}
        tt = rule(o, h, l, c, did, qk, knobs["stop_frac"], warmup="literal", funnel=ff)
        yrs = (days[-1] - days[0]).days / 365.25
        grid[str(qk)] = {"quiet_pass": ff["quiet_pass"], "trades": len(tt), "per_yr": round(len(tt) / yrs, 1),
                         "gross_pts_per_trade": round(float(np.mean([t[5] for t in tt])), 4) if tt else None}
    res["quiet_k_grid_literal"] = grid
    mr_ratio = []
    for i in range(20, len(starts)):
        mr_ratio.append(mr_s[i] / np.median(mr_s[i - 20:i]))
    mr_ratio = np.array(mr_ratio)
    res["mr_over_trailing_median"] = {"median": round(float(np.median(mr_ratio)), 3),
                                      "share_le_1.5": round(float((mr_ratio <= 1.5).mean()), 4),
                                      "share_le_1.0": round(float((mr_ratio <= 1.0).mean()), 4)}

    s = json.dumps(clean(res), indent=1, sort_keys=True, default=str)
    print(s)
    p = os.path.join(OUT, "ttm_trace.json")
    open(p, "wb").write((s + "\n").encode("utf-8"))
    print("output sha256", hashlib.sha256(open(p, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()

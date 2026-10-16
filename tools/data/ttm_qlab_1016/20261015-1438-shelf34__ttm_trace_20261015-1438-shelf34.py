"""TTM (house verifier): STAGE 2 - COMPARE + TRACE for Qwen Lab idea QL_TOM_CALENDAR_NQ (plugin v8, LF sha256 83b2429e...),
idea folder C:/EdgeLog/qwen_lab/ideas/20261015-1438-shelf34/. Written AFTER the stage-1 output (ttm_verify.json, sha256 e333f92d...)
was posted to MANAGER; the lab's numbers_pre_wf.json, sanity_r0.json and pre_wf_trades.csv are opened here for the first time.

1. COMPARE: each lab numbers block (numbers_pre_wf.json 'numbers', sanity_r0.json 'numbers' and 'stage.numbers') field by field against
   TTM arm A (plugin through the engine, house cost 0.533), and pre_wf_trades.csv trade for trade against arm A's engine trades.
2. TRACE: TTM's own rule (stage-1 arm B: buy the first bar's open, sell the last bar's close, on the last 3 sessions of each calendar
   month of the master's day_id sessions) is generalised with one switch per plugin departure from the prereg text:
     group   'month' (prereg: 'last 3 trading days of each calendar month') vs 'block21' (plugin: i // 21, 21-session blocks counted
             from the loaded window's first session)
     tail    'fixed' (last 3 of the group) vs 'plugin' (plugin's test 'pos_in_block >= block_end - tl': pos_in_block is 0..20 but
             block_end is an ABSOLUTE session index, so only the first group can qualify)
     skip1   plugin skips a session with < 2 bars ('if b - a < 2: continue'); prereg says nothing
   PLUGIN WAY = (block21, plugin, skip1) must equal the plugin 100% trade for trade (entry bar, exit bar, side, entry px, gross pts).
   LITERAL = (month, fixed, no skip) must equal stage-1 arm B. Each slip is reverted one at a time and scored with the four numbers.
   Also: the plugin text with ONLY the bug line patched, through the engine, must equal (block21, fixed, skip1).
3. LOOK-AHEAD: price-independence probe (all OHLC replaced by a random walk -> the same sessions picked); truncation probe (data cut
   at every session boundary -> trades completed before the cut unchanged), for the plugin and the patched plugin.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1438-shelf34/."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1438-shelf34"
spec = importlib.util.spec_from_file_location("ttm_v", OUT + "/ttm_verify_20261015-1438-shelf34.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)            # sets AUGUR_TRIAL_CACHE=0, sys.path, chdir; main() not run
assert os.environ.get("AUGUR_TRIAL_CACHE") == "0"

LAB_NUMBERS = V.IDEA + "/numbers_pre_wf.json"
LAB_SANITY = V.IDEA + "/sanity_r0.json"
LAB_TRADES = V.IDEA + "/pre_wf_trades.csv"
STRESS = V.COST + 0.5                 # house + 1 tick each side (reported for completeness; not a short-hold scalper)
BUG_LINE = "        if pos_in_block >= block_end - tl:\n"
FIX_LINE = "        if pos_in_block >= (block_end - block_idx * bl) - tl:\n"


def pick(sdates, group="month", tail="fixed", bl=21, tl=3):
    """Bool per master session: is it a traded session under (group, tail)?"""
    nS = len(sdates)
    if group == "month":
        ym = np.asarray(sdates.year * 12 + sdates.month)
        gid = np.r_[0, np.cumsum(ym[1:] != ym[:-1])]          # month number in session order
    else:
        gid = np.arange(nS) // bl                              # plugin: block_idx = i // bl
    gstart = pd.Series(np.arange(nS)).groupby(gid).transform("min").to_numpy()
    gend = pd.Series(np.arange(nS)).groupby(gid).transform("max").to_numpy() + 1   # absolute index one past the group's last session
    pos = np.arange(nS) - gstart                               # position in the group, 0-based
    if tail == "fixed":
        return pos >= (gend - gstart) - tl                     # last tl sessions of the group
    return pos >= gend - tl                                    # plugin's test: relative position vs ABSOLUTE end index


def rule(o, c, starts, ends, flags, skip1=False):
    """Stage-1 own_rule entry/exit on the given session flags: (entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)."""
    out = []
    for s, e, f in zip(starts, ends, flags):
        if not f or (skip1 and e - s < 2):
            continue
        ep, xp = float(o[s]), float(c[e - 1])
        out.append((int(s), int(e - 1), 1, ep, xp, xp - ep))
    return out


def load_plugin(text, name):
    m = types.ModuleType(name)
    m.__file__ = V.PLUGIN
    exec(compile(text, V.PLUGIN, "exec"), m.__dict__)
    return m


def as_key(T):
    """engine/plugin trade tuples (entry, exit, pts, side, entry_px) -> {(entry, side): (exit, entry_px, pts)}"""
    return {(int(t[0]), int(t[3])): (int(t[1]), float(t[4]), float(t[2])) for t in T}


def match(T_plugin, R):
    ka = as_key(T_plugin)
    kb = {(t[0], t[2]): (t[1], t[3], t[5]) for t in R}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][0] == kb[k][0] and abs(ka[k][1] - kb[k][1]) < 1e-9 and abs(ka[k][2] - kb[k][2]) < 1e-9)
    return {"plugin_trades": len(ka), "rule_trades": len(kb), "same_entry_side": len(both), "exact": exact,
            "match_100pct": bool(len(ka) == len(kb) == exact)}


def four_str(f, trades=None):
    t = f["trades"] if trades is None else trades
    return (f"ROC@30k {f['roc30']:.2f} | DD5 ${f['dd5']:,.0f}{' (ONE EPISODE)' if f['one_episode'] else ''} | DD% from peak "
            f"{f['dd_pct_peak']:.2f}% | Sortino {f['sortino']:.3f} | trades {t:,} ({f['trades_per_yr']:.1f}/yr) | $/yr {f['per_yr_usd']:,.0f}")


def scored(R, idxn, days):
    e, x, p = [t[0] for t in R], [t[1] for t in R], [t[5] for t in R]
    out = {}
    for nm, cost in (("house_cost", V.COST), ("real_cost", V.REAL_COST), ("stress_cost", STRESS)):
        f = V.score(e, x, p, idxn, days, cost)
        f["four"] = four_str(f)
        out[nm] = f
    return out


def main():
    res = {"stage1_output_sha256": hashlib.sha256(open(OUT + "/ttm_verify.json", "rb").read()).hexdigest()}
    assert res["stage1_output_sha256"] == "e333f92d5881f87540a8c727bfefc3bb6c4d004f1fd8c4eb3c56d3580d23c98a"
    assert V.lf_sha(V.PLUGIN) == V.PIN_FULL, "plugin pin"
    row = [x for x in V.list_masters() if x.get("filename") == V.MASTER]
    assert len(row) == 1
    A = V.load_master_arrays(row[0], date_from=V.D0, date_to=V.D1)
    idxn = pd.DatetimeIndex(A["index"]).tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01")
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts, ends = V.sessions(day_id)
    sdates = idxn[starts].normalize()
    res["one_bar_sessions"] = int(np.sum(ends - starts < 2))

    # ---- arm A: plugin as run, through the engine
    text = open(V.PLUGIN, encoding="utf-8").read()
    m = load_plugin(text, "ttm_trace_tom")
    T = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)["trades"]
    armA = scored([(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[4]) + float(t[2]), float(t[2])) for t in T], idxn, days)
    res["A_plugin"] = armA
    res["A_trades"] = [[str(idxn[int(t[0])]), str(idxn[int(t[1])]), int(t[3]), float(t[4]), float(t[2]),
                        int(np.searchsorted(starts, int(t[0]), side="right") - 1)] for t in T]

    # ---- 1. COMPARE vs every lab numbers block
    lab = json.load(open(LAB_NUMBERS))["numbers"]
    san = json.load(open(LAB_SANITY))
    H = armA["house_cost"]
    tol = [("trades", "trades", 0), ("net_usd", "net_usd", 1.0), ("roc_30k", "roc30", 0.005), ("dd5_usd", "dd5", 1.0),
           ("max_dd_usd", "max_dd", 1.0), ("dd_pct_peak", "dd_pct_peak", 0.01), ("sortino", "sortino", 0.001),
           ("one_episode", "one_episode", None), ("win_rate", "win_rate", 0.05)]
    cmp = {}
    for fname, block in (("numbers_pre_wf.json:numbers", lab), ("sanity_r0.json:numbers", san["numbers"]),
                         ("sanity_r0.json:stage.numbers", san["stage"]["numbers"])):
        rows = []
        for lk, mk, t in tol:
            lv, mv = block.get(lk), H[mk]
            if lk == "win_rate" and lv is not None and lv > 1.0:
                lv = lv / 100.0
            ok = (lv == mv) if t is None else (lv is not None and abs(float(lv) - float(mv)) <= t)
            rows.append({"field": lk, "lab": lv, "mine": mv, "match": bool(ok)})
        cmp[fname] = {"rows": rows, "all_match": all(r["match"] for r in rows)}
    res["compare"] = cmp
    labT = pd.read_csv(LAB_TRADES)
    kA = as_key(T)
    tr_ok = []
    for _, r in labT.iterrows():
        k = (int(r.entry_bar), int(r.side))
        v = kA.get(k)
        tr_ok.append(bool(v is not None and v[0] == int(r.exit_bar) and abs(v[1] - float(r.entry_price)) < 1e-9
                          and abs((v[2] - V.COST) - float(r.pnl_points_net)) < 1e-6
                          and str(idxn[int(r.entry_bar)]) == str(pd.Timestamp(r.entry_time).tz_localize(None))))
    res["compare_trades_csv"] = {"lab_rows": len(labT), "engine_trades": len(T), "rows_matching": int(sum(tr_ok)),
                                 "all_match": bool(len(labT) == len(T) == sum(tr_ok))}

    # ---- 2. TRACE
    B_stage1 = V.own_rule(o, h, l, c, day_id, sdates)
    variants = {
        "LITERAL_month_fixed": ("month", "fixed", False),
        "SLIP1_only_block21_fixed": ("block21", "fixed", False),
        "SLIP2_only_month_plugin_tail": ("month", "plugin", False),
        "SLIP1+2_block21_plugin_tail": ("block21", "plugin", False),
        "PLUGIN_WAY_block21_plugin_tail_skip1": ("block21", "plugin", True),
        "PATCHED_INTENT_block21_fixed_skip1": ("block21", "fixed", True),
    }
    R = {nm: rule(o, c, starts, ends, pick(sdates, g, t), s1) for nm, (g, t, s1) in variants.items()}
    lit = R["LITERAL_month_fixed"]
    res["literal_equals_stage1_armB"] = bool(lit == B_stage1)
    trace = {}
    keyB = {t[0] for t in lit}
    for nm, RR in R.items():
        d = {"switches": dict(zip(("group", "tail", "skip1"), variants[nm])), "trades": len(RR),
             "overlap_with_literal": len({t[0] for t in RR} & keyB),
             "vs_plugin": match(T, RR), "first_entries": [str(idxn[t[0]]) for t in RR[:6]]}
        d.update(scored(RR, idxn, days) if RR else {})
        trace[nm] = d
    res["trace"] = trace
    res["b_plugin_way_matches_100pct"] = trace["PLUGIN_WAY_block21_plugin_tail_skip1"]["vs_plugin"]["match_100pct"]

    # patched plugin (bug line only) through the engine == PATCHED_INTENT
    assert text.count(BUG_LINE) == 1
    mp = load_plugin(text.replace(BUG_LINE, FIX_LINE), "ttm_trace_tom_patched")
    Tp = V.run_backtest(mp, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)["trades"]
    res["patched_plugin_engine"] = {"trades": len(Tp), "vs_PATCHED_INTENT": match(Tp, R["PATCHED_INTENT_block21_fixed_skip1"])}

    # plugin knob corners (to show the trade count is pinned to tail_len, i.e. the contract corners could not catch the bug)
    corners = {}
    for kw in ({"block_len": 18}, {"block_len": 24}, {"tail_len": 2}, {"tail_len": 5}):
        rr = m.run_backtest(o, h, l, c, day_id=day_id, return_trades=True, **kw)
        corners[json.dumps(kw)] = 0 if rr is None else rr["num_trades"]
    res["plugin_corners_full_window"] = corners

    # ---- 3. LOOK-AHEAD probes (plugin's own function on raw arrays; == engine on the full window)
    full = m.run_backtest(o, h, l, c, day_id=day_id, return_trades=True)["trades"]
    assert [(t[0], t[1]) for t in full] == [(int(t[0]), int(t[1])) for t in T]
    rng = np.random.default_rng(20261016)
    w = 1000 + np.cumsum(rng.normal(0, 2, len(c)))
    rw = m.run_backtest(w, w + 1, w - 1, w + rng.normal(0, 0.5, len(c)), day_id=day_id, return_trades=True)["trades"]
    rwp = mp.run_backtest(w, w + 1, w - 1, w + rng.normal(0, 0.5, len(c)), day_id=day_id, return_trades=True)["trades"]
    fullp = mp.run_backtest(o, h, l, c, day_id=day_id, return_trades=True)["trades"]
    la = {"price_independence_plugin": [(t[0], t[1]) for t in rw] == [(t[0], t[1]) for t in full],
          "price_independence_patched": [(t[0], t[1]) for t in rwp] == [(t[0], t[1]) for t in fullp]}
    bad, badp, changed_cuts_p = 0, 0, []
    for k in range(25, len(starts)):
        cut = starts[k]
        a = m.run_backtest(o[:cut], h[:cut], l[:cut], c[:cut], day_id=day_id[:cut], return_trades=True)
        a = [] if a is None else a["trades"]
        if [(t[0], t[1]) for t in a] != [(t[0], t[1]) for t in full if t[1] < cut]:
            bad += 1
        b = mp.run_backtest(o[:cut], h[:cut], l[:cut], c[:cut], day_id=day_id[:cut], return_trades=True)
        b = [] if b is None else b["trades"]
        if [(t[0], t[1]) for t in b] != [(t[0], t[1]) for t in fullp if t[1] < cut]:
            badp += 1
            if len(changed_cuts_p) < 3:
                changed_cuts_p.append(str(sdates[k].date()))
    la.update({"truncation_cuts": len(starts) - 25, "truncation_plugin_mismatches": bad, "truncation_patched_mismatches": badp,
               "truncation_patched_first_mismatch_cuts": changed_cuts_p,
               "reads": "plugin reads o[first bar of session] (fill) and c[last bar of session] (exit) only; h/l/volume never used; "
                        "selection uses day_id session boundaries only"})
    res["lookahead"] = la

    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    with open(os.path.join(OUT, "ttm_trace.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s + "\n")
    summ = {"compare": {k: v["all_match"] for k, v in cmp.items()}, "trades_csv": res["compare_trades_csv"],
            "literal_equals_stage1_armB": res["literal_equals_stage1_armB"], "one_bar_sessions": res["one_bar_sessions"],
            "b_plugin_way_matches_100pct": res["b_plugin_way_matches_100pct"], "patched": res["patched_plugin_engine"],
            "corners": corners, "lookahead": la,
            "trace": {k: {"trades": v["trades"], "overlap_lit": v["overlap_with_literal"], "vs_plugin": v["vs_plugin"],
                          "house": v.get("house_cost", {}).get("four"), "real": v.get("real_cost", {}).get("four"),
                          "stress": v.get("stress_cost", {}).get("four")} for k, v in trace.items()},
            "A_house": armA["house_cost"]["four"], "A_real": armA["real_cost"]["four"], "A_stress": armA["stress_cost"]["four"],
            "A_trades": res["A_trades"]}
    print(json.dumps(summ, indent=1, default=float))
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main()

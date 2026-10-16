"""TTM (house verifier): STAGE 2 - COMPARE + TRACE for the Qwen Lab's QL_MOMDRIVE PRE-WF Stage A (idea 20261015-1221-scalper,
re-run as 20261015-1310-scalper with the same plugin).
Stage 1 (blind) output: ttm_verify.json sha256 ea3fbe262d8048cd71098e29a52b473d2b2cff924c11176ddeacc9d61dcf9afb (MANAGER #1269).
This script, written AFTER that post (the lab's numbers and the plugin code may now be read):
  1. re-runs arm A (the plugin AS RUN through the engine, pinned master by registry filename) and compares it field by field
     with BOTH lab numbers files and both pre_wf_trades.csv files;
  2. TRACE: TTM's own frozen rule (own_rule, loaded from the stage-1 frozen copy, sha-checked) is generalised with one toggle per
     point where the plugin departs from the prereg text. All toggles at TTM's reading reproduce the frozen own_rule exactly;
     all toggles at the plugin's reading reproduce the engine's plugin run 100% trade for trade on several knob settings.
     Each slip is then reverted ALONE from the plugin way to give the literal reading's four numbers;
  3. look-ahead probes on the plugin itself (close-perturbation of the exit bar, future-bar perturbation of the entry);
  4. why it barely trades: counts of the prereg's quiet filter / signal in TTM's own build, with the ATR decomposition.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1221-scalper/ (ttm_trace.json)."""
import csv
import hashlib
import inspect
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1221-scalper"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
import augur_engine.rolls as R                                    # noqa: E402

IDEAS = ["C:/EdgeLog/qwen_lab/ideas/20261015-1221-scalper", "C:/EdgeLog/qwen_lab/ideas/20261015-1310-scalper"]
PLUGIN = IDEAS[0] + "/plugin_v1.py.txt"
PIN_PLUGIN = "8ae66698585945cd3a61c0d79a58cb406202866865b4c03b045dd642929ea0fa"
FROZEN_B = OUT + "/ttm_verify_B_frozen_before_plugin_read.py"
PIN_FROZEN_B = "b1e47b05d55bf02e58d745b9088c659a1dcbfa706328d199b596c1cd2f651776"
PIN_OWN_RULE_SRC = "1795d34609d445a89dd41fa2cd56b0ef75ecc152f1c522b3e7cc48be1c4cda3a"
PIN_FINGERPRINT = "21a9952e0aba01fe84fa726066cbf2f955f539fe"
MASTER, D0, D1 = "NOADJ_NQ_2m_RTH.csv", "2010-06-07", "2016-06-30"
MULT = 20.0
COST = 0.783                            # house short-hold basis (prereg)
REAL_COST = 0.25 * 2 + 5.65 / MULT      # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5                # scalper stress: + 1 tick each side on top of the house cost

PLUGIN_WAY = dict(trail_atr="fixed_setup", best_start="entry_in_max", same_bar_close=True, entry_bar_open_fill=True,
                  last_signal="e-3", min_bars="plugin", zero_skip=True, atr_arith="window_mean")
TTM_WAY = dict(trail_atr="rolling", best_start="closes_only", same_bar_close=False, entry_bar_open_fill=False,
               last_signal="e-2", min_bars="ttm", zero_skip=False, atr_arith="cumsum")
SLIPS = {   # slip -> the toggles that carry it (reverted together to the TTM reading)
    "S1_trail_atr_fixed_at_setup_end": ["trail_atr"],
    "S2_best_close_seeded_with_entry_price": ["best_start"],
    "S3_same_bar_close_lookahead_in_stop": ["same_bar_close", "entry_bar_open_fill"],
    "S4_signal_scan_stops_at_third_last_bar": ["last_signal"],
    "S5_short_session_filter": ["min_bars"],
    "S6_zero_atr_or_range_skip": ["zero_skip"],
    "N1_atr_float_arithmetic": ["atr_arith"],
}


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def load_frozen_b():
    assert hashlib.sha256(open(FROZEN_B, "rb").read()).hexdigest() == PIN_FROZEN_B, "frozen B file changed"
    fb = types.ModuleType("ttm_frozen_b")
    fb.__file__ = FROZEN_B
    exec(compile(open(FROZEN_B, encoding="utf-8").read(), FROZEN_B, "exec"), fb.__dict__)
    src = inspect.getsource(fb.own_rule)
    assert hashlib.sha256(src.encode()).hexdigest() == PIN_OWN_RULE_SRC, "own_rule source changed"
    return fb


def atr_cumsum(h, l, c, n_atr):
    """TTM's ATR (the frozen atr14 generalised to n bars): simple mean of TRUE range over bars k-n+1..k (global, crossing
    sessions); NaN until k >= n."""
    rng = h - l
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(rng, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = rng[0]
    cs = np.r_[0.0, np.cumsum(tr)]
    out = np.full(len(c), np.nan)
    k = np.arange(n_atr, len(c))
    out[k] = (cs[k + 1] - cs[k - n_atr + 1]) / float(n_atr)
    return out, tr


def atr_window_mean(tr, i, n_atr):
    """The same ATR value computed the plugin's arithmetic way (np.mean over the window) - float rounding only."""
    if i - n_atr + 1 < 1:
        return np.nan
    return float(np.mean(tr[i - n_atr + 1:i + 1]))


def rule(o, h, l, c, day_id, ck, sb=12, ab=14, tk=2.0, counts=None, **tog):
    """TTM's frozen own_rule (stage 1, written from the prereg text before the plugin was read) with one toggle per departure.
    TTM_WAY toggles == the frozen own_rule (asserted); PLUGIN_WAY toggles == the plugin as coded (asserted against the engine).
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    t = dict(TTM_WAY)
    t.update(tog)
    n = len(c)
    atr, tr = atr_cumsum(h, l, c, ab)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    cnt = {"sessions": 0, "long_enough": 0, "atr_ok": 0, "quiet": 0, "signal": 0}
    for s, e in zip(starts, ends):
        cnt["sessions"] += 1
        if t["min_bars"] == "ttm":
            if e - s < sb + 2:                    # TTM: need the range, a signal bar and an entry bar
                continue
        elif e - s <= sb + 3:                     # plugin: sess_len <= setup_bars + 3 skipped
            continue
        cnt["long_enough"] += 1
        k_or = s + sb - 1
        a_or = atr[k_or] if t["atr_arith"] == "cumsum" else atr_window_mean(tr, k_or, ab)
        if not np.isfinite(a_or):
            continue
        rh = h[s:k_or + 1].max()
        rl = l[s:k_or + 1].min()
        if t["zero_skip"] and (a_or <= 0 or rh - rl <= 0):
            continue
        cnt["atr_ok"] += 1
        if not (rh - rl <= ck * a_or):
            continue
        cnt["quiet"] += 1
        stop_k = e - 1 if t["last_signal"] == "e-2" else e - 2
        sig, side = -1, 0
        for k in range(k_or + 1, stop_k):
            if c[k] > rh:
                sig, side = k, 1
                break
            if c[k] < rl:
                sig, side = k, -1
                break
        if sig < 0:
            continue
        cnt["signal"] += 1
        ent = sig + 1
        ep = o[ent]
        ref = ep
        xb, xp = e - 1, c[e - 1]

        def upd(ref, j):
            if t["best_start"] == "entry_in_max":
                return max(ref, c[j]) if side > 0 else min(ref, c[j])
            return c[j] if j == ent else (max(ref, c[j]) if side > 0 else min(ref, c[j]))

        for j in range(ent, e):
            if t["same_bar_close"]:
                ref = upd(ref, j)                 # plugin: bar j's close moves the stop BEFORE bar j is tested
            a = atr[j - 1] if t["trail_atr"] == "rolling" else a_or
            stop = ref - side * tk * a
            if (j > ent or t["entry_bar_open_fill"]) and side * (o[j] - stop) <= 0:
                xb, xp = j, o[j]
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
            if not t["same_bar_close"]:
                ref = upd(ref, j)
        out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
    if counts is not None:
        counts.update(cnt)
    return out


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net_usd": float(x.sum()), "per_yr": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else None, "dd5": float(r["dd5_usd"]), "dd5_n": int(r["n"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else None}


def score(exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    if len(usd) == 0:
        return {"trades": 0}
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "cost_pts": cost})
    return f


def fmt4(f):
    if not f or f.get("trades", 0) == 0:
        return "no trades"
    roc = "undefined (no drawdown)" if f["roc30"] is None else "%.2f" % f["roc30"]
    so = "undefined (no down day)" if f["sortino"] is None else "%.2f" % f["sortino"]
    return "ROC@30k %s | DD5 $%s (n=%d) | DD%% from peak %.2f%% | Sortino %s | trades %s (%.2f/yr) | $/yr %s" % (
        roc, format(round(f["dd5"]), ","), f["dd5_n"], f["dd_pct_peak"], so, format(f["trades"], ","),
        f["trades_per_yr"], format(round(f["per_yr"]), ","))


def match(Ta, Rr, o_raw, tol=1e-6):
    """Ta = engine rows (entry, exit, gross, side, entry_px_raw); Rr = rule rows (entry, exit, side, ep, xp, gross)."""
    ka = {(t[0], t[3]): t for t in Ta}
    kr = {(t[0], t[2]): t for t in Rr}
    both = sorted(set(ka) & set(kr))
    exact = [k for k in both if ka[k][1] == kr[k][1] and abs(ka[k][2] - kr[k][5]) < tol
             and abs(ka[k][4] - o_raw[kr[k][0]]) < tol]
    return {"engine_trades": len(Ta), "rule_trades": len(Rr), "same_entry_and_side": len(both),
            "same_exit_bar": sum(1 for k in both if ka[k][1] == kr[k][1]), "exact": len(exact),
            "only_engine": len(set(ka) - set(kr)), "only_rule": len(set(kr) - set(ka)),
            "match_100pct": len(exact) == len(Ta) == len(Rr)}


def main():
    res = {"stage": 2, "stage1_output_sha256": hashlib.sha256(open(OUT + "/ttm_verify.json", "rb").read()).hexdigest()}
    assert res["stage1_output_sha256"] == "ea3fbe262d8048cd71098e29a52b473d2b2cff924c11176ddeacc9d61dcf9afb"
    sha = lf_sha(PLUGIN)
    assert sha == PIN_PLUGIN and lf_sha(IDEAS[1] + "/plugin_v1.py.txt") == PIN_PLUGIN, "plugin pin"
    res["plugin_lf_sha256"] = sha
    fb = load_frozen_b()
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    assert str(A.get("fingerprint")) == PIN_FINGERPRINT, "window fingerprint != prereg"
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01")
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res.update({"registry_id": row[0].get("id"), "bars": len(c), "fingerprint": str(A.get("fingerprint")),
                "sessions": len(days), "years": (days[-1] - days[0]).days / 365.25})
    m = types.ModuleType("ttm_ql_momdrive")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)

    def engine(params):
        r = run_backtest(m, instrument="NQ", arrays=A, params=params, cost_pts=0.0, return_trades=True)
        return [(int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])) for t in ((r or {}).get("trades") or [])], r

    # ---------- 1. arm A vs the lab ----------
    Ta, r0 = engine(None)
    armA = {k: score([t[1] for t in Ta], [t[2] for t in Ta], idxn, days, cst)
            for k, cst in (("house", COST), ("real", REAL_COST), ("stress", STRESS_COST))}
    res["arm_A"] = armA
    res["arm_A_trades"] = [{"entry_bar": t[0], "exit_bar": t[1], "gross_pts": t[2], "side": t[3], "entry_px": t[4],
                            "entry_time": str(idx[t[0]]), "exit_time": str(idx[t[1]])} for t in Ta]
    res["four_numbers"] = {k: fmt4(v) for k, v in armA.items()}
    hc = armA["house"]
    fields = [("trades", "trades", lambda a, b: a == b, "exact"),
              ("net_usd", "net_usd", lambda a, b: abs(a - b) <= 1.0, "$1"),
              ("roc_30k", "roc30", lambda a, b: a is not None and b is not None and abs(a - b) <= 0.005, "0.005"),
              ("dd5_usd", "dd5", lambda a, b: abs(a - b) <= 1.0, "$1"),
              ("max_dd_usd", "max_dd", lambda a, b: abs(a - b) <= 1.0, "$1"),
              ("dd_pct_peak", "dd_pct_peak", lambda a, b: abs(a - b) <= 0.01, "0.01"),
              ("sortino", "sortino", lambda a, b: a is not None and b is not None and abs(a - b) <= 0.001, "0.001"),
              ("one_episode", "one_episode", lambda a, b: bool(a) == bool(b), "equal"),
              ("win_rate", "win_rate", lambda a, b: min(abs(a - b), abs(a / 100.0 - b)) <= 0.05, "0.05 pts")]
    cmp = []
    csvs = {}
    for d in IDEAS:
        nf = d + "/numbers_pre_wf.json"
        lab = json.load(open(nf))["numbers"]
        for lk, mk, ok, tol in fields:
            cmp.append({"numbers_file": nf, "field": lk, "lab": lab.get(lk), "mine": hc.get(mk), "tol": tol,
                        "match": bool(ok(lab.get(lk), hc.get(mk)))})
        rows = list(csv.DictReader(open(d + "/pre_wf_trades.csv")))
        csvs[d] = {"rows": len(rows), "match": len(rows) == len(Ta) and all(
            int(rw["entry_bar"]) == t[0] and int(rw["exit_bar"]) == t[1] and int(rw["side"]) == t[3]
            and abs(float(rw["entry_price"]) - t[4]) < 1e-6 and abs(float(rw["pnl_points_net"]) - (t[2] - COST)) < 1e-5
            for rw, t in zip(rows, Ta)), "lab_rows": rows}
    res["lab_vs_arm_A"] = cmp
    res["lab_trades_csv_vs_arm_A"] = csvs
    res["lab_vs_arm_A_all_match"] = all(x["match"] for x in cmp) and all(v["match"] for v in csvs.values())

    # ---------- 2. TRACE ----------
    plan = R.plan_for(m, A, PLUGIN, {})
    AA = R.apply_plan(A, plan)
    oa, ha, la, ca = (np.asarray(AA[k], float) for k in ("open", "high", "low", "close"))
    res["roll_plan"] = {"kind": str(plan.get("kind")), "method": str(plan.get("method"))}
    # (a) TTM_WAY toggles == the frozen own_rule (raw and engine arrays; default and the file's max compress_k)
    ident = {}
    for nm, arr in (("raw", (o, h, l, c)), ("engine_signal_arrays", (oa, ha, la, ca))):
        for ck in (1.0, 2.0):
            fr = fb.own_rule(*arr, day_id, ck)
            mine = rule(*arr, day_id, ck)
            ident["%s_k%.1f" % (nm, ck)] = {"trades": len(fr), "identical": fr == mine}
    res["ttm_way_equals_frozen_own_rule"] = ident
    assert all(v["identical"] for v in ident.values())
    # (b) PLUGIN_WAY toggles == the engine's plugin run, trade for trade, on a spread of knob settings
    grid = [{}, {"compress_k": 2.0}, {"compress_k": 2.0, "trail_k": 1.0}, {"compress_k": 2.0, "trail_k": 4.0},
            {"compress_k": 2.0, "setup_bars": 6}, {"compress_k": 2.0, "setup_bars": 30, "atr_bars": 28},
            {"compress_k": 2.0, "atr_bars": 7}, {"compress_k": 1.5, "setup_bars": 18, "atr_bars": 21, "trail_k": 3.0},
            {"compress_k": 1.25, "setup_bars": 6, "atr_bars": 28, "trail_k": 1.5}, {"compress_k": 0.5}]
    pw = []
    eng_cache = {}
    for p in grid:
        q = {"setup_bars": 12, "compress_k": 1.0, "trail_k": 2.0, "atr_bars": 14}
        q.update(p)
        Te, _ = engine(p if p else None)
        eng_cache[json.dumps(q, sort_keys=True)] = Te
        Rp = rule(oa, ha, la, ca, day_id, q["compress_k"], q["setup_bars"], q["atr_bars"], q["trail_k"], **PLUGIN_WAY)
        mt = match(Te, Rp, o)
        mt["params"] = q
        pw.append(mt)
    res["plugin_way_vs_engine"] = pw
    res["b_plugin_way_matches_100pct"] = all(x["match_100pct"] for x in pw)
    res["plugin_way_trades_compared"] = int(sum(x["engine_trades"] for x in pw))

    # (c) slip ladder: TTM reading -> plugin way, one slip added at a time (cumulative), and each slip reverted ALONE
    def run_cell(arr, ck, tg, tk=2.0):
        Rr = rule(*arr, day_id, ck, 12, 14, tk, **tg)
        return Rr, {k: score([t[1] for t in Rr], [t[5] for t in Rr], idxn, days, cst)
                    for k, cst in (("house", COST), ("real", REAL_COST), ("stress", STRESS_COST))}

    cells = {"default_k1.0": 1.0, "mechanics_k2.0_not_a_result": 2.0}
    ladder, alone = {}, {}
    order = ["S5_short_session_filter", "S6_zero_atr_or_range_skip", "N1_atr_float_arithmetic",
             "S4_signal_scan_stops_at_third_last_bar", "S2_best_close_seeded_with_entry_price",
             "S1_trail_atr_fixed_at_setup_end", "S3_same_bar_close_lookahead_in_stop"]
    for cname, ck in cells.items():
        TeD = eng_cache[json.dumps({"setup_bars": 12, "compress_k": ck, "trail_k": 2.0, "atr_bars": 14}, sort_keys=True)]
        steps = []
        Rr, sc = run_cell((o, h, l, c), ck, TTM_WAY)
        steps.append({"step": "B literal (TTM reading, raw NOADJ prices)", "vs_engine": match(TeD, Rr, o),
                      "house": fmt4(sc["house"]), "gross_pts": sum(t[5] for t in Rr)})
        tg = dict(TTM_WAY)
        Rr, sc = run_cell((oa, ha, la, ca), ck, tg)
        steps.append({"step": "+ S0 engine roll plan (difference-adjusted signals)", "vs_engine": match(TeD, Rr, o),
                      "house": fmt4(sc["house"]), "gross_pts": sum(t[5] for t in Rr)})
        for sl in order:
            for key in SLIPS[sl]:
                tg[key] = PLUGIN_WAY[key]
            Rr, sc = run_cell((oa, ha, la, ca), ck, tg)
            steps.append({"step": "+ " + sl, "vs_engine": match(TeD, Rr, o), "house": fmt4(sc["house"]),
                          "gross_pts": sum(t[5] for t in Rr)})
        ladder[cname] = steps
        al = {}
        Rp, scp = run_cell((oa, ha, la, ca), ck, PLUGIN_WAY)
        al["plugin_way"] = {k: fmt4(v) for k, v in scp.items()}
        al["plugin_way"]["gross_pts"] = sum(t[5] for t in Rp)
        for sl, keys in SLIPS.items():
            tg = dict(PLUGIN_WAY)
            for key in keys:
                tg[key] = TTM_WAY[key]
            Rr, sc = run_cell((oa, ha, la, ca), ck, tg)
            kp = {(t[0], t[2]): t for t in Rp}
            chg = sum(1 for t in Rr if (t[0], t[2]) not in kp or kp[(t[0], t[2])][1] != t[1]
                      or abs(kp[(t[0], t[2])][5] - t[5]) > 1e-9) + sum(1 for k in kp if k not in {(t[0], t[2]) for t in Rr})
            al[sl] = {"trades_changed_vs_plugin_way": chg, "gross_pts": sum(t[5] for t in Rr),
                      "house": fmt4(sc["house"]), "real": fmt4(sc["real"]), "stress": fmt4(sc["stress"]),
                      "house_roc30": sc["house"].get("roc30"), "house_net_usd": sc["house"].get("net_usd"),
                      "trades": [[str(idx[t[0]]), str(idx[t[1]]), t[2], round(t[5], 4)] for t in Rr] if len(Rr) <= 3 else None}
        Rb, scb = run_cell((o, h, l, c), ck, TTM_WAY)
        al["ALL_literal_B_raw"] = {"house": fmt4(scb["house"]), "real": fmt4(scb["real"]), "stress": fmt4(scb["stress"]),
                                   "gross_pts": sum(t[5] for t in Rb)}
        alone[cname] = al
    res["slip_ladder_cumulative"] = ladder
    res["slip_reverted_alone"] = alone
    # trail_k 1.0 (the file minimum) where the look-ahead bites hardest - mechanics only
    Rp1 = rule(oa, ha, la, ca, day_id, 2.0, 12, 14, 1.0, **PLUGIN_WAY)
    tg = dict(PLUGIN_WAY, same_bar_close=False, entry_bar_open_fill=False)
    Rc1 = rule(oa, ha, la, ca, day_id, 2.0, 12, 14, 1.0, **tg)
    res["lookahead_k2_trail1"] = {"trades": len(Rp1), "gross_plugin": sum(t[5] for t in Rp1),
                                  "gross_causal": sum(t[5] for t in Rc1),
                                  "exits_changed": sum(1 for a, b in zip(Rp1, Rc1) if a != b),
                                  "plugin_house": fmt4(score([t[1] for t in Rp1], [t[5] for t in Rp1], idxn, days, COST)),
                                  "causal_house": fmt4(score([t[1] for t in Rc1], [t[5] for t in Rc1], idxn, days, COST)),
                                  "entry_bar_zero_exits_plugin": sum(1 for t in Rp1 if t[1] == t[0] and abs(t[5]) < 1e-12)}

    # ---------- 3. look-ahead probes on the PLUGIN itself (direct call on the engine's signal arrays) ----------
    def plug(oo, hh, ll, cc, dd, **kw):
        r = m.run_backtest(oo, hh, ll, cc, None, dd, return_trades=True, **kw)
        return (r or {}).get("trades") or []

    probes = {}
    rng_ = np.random.default_rng(20261016)
    for pname, kw in (("k2.0_trail2.0", {"compress_k": 2.0}), ("k2.0_trail1.0", {"compress_k": 2.0, "trail_k": 1.0}),
                      ("default", {})):
        Tp = plug(oa, ha, la, ca, day_id, **kw)
        Rpc = rule(oa, ha, la, ca, day_id, kw.get("compress_k", 1.0), 12, 14, kw.get("trail_k", 2.0),
                   **dict(PLUGIN_WAY, same_bar_close=False, entry_bar_open_fill=False))
        kc = {t[0]: t for t in Rpc}
        starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
        ends = np.r_[starts[1:], len(c)]
        sess_of = np.searchsorted(starts, np.arange(len(c)), side="right") - 1
        ex_changed = ex_tested = en_changed = en_tested = causal_changed = 0
        examples = []
        for t in Tp:
            e, x, side = int(t[0]), int(t[1]), int(t[3])
            si = sess_of[e]
            a0, b0 = max(0, starts[si] - 80), ends[si]
            sl = slice(a0, b0)
            base = [u for u in plug(oa[sl], ha[sl], la[sl], ca[sl], day_id[sl], **kw) if u[0] + a0 == e]
            # (i) exit-bar close perturbation: a causal intrabar stop at bar x cannot depend on close[x]
            if x < b0 - 1 or x == e:
                ex_tested += 1
                cc = ca[sl].copy()
                cc[x - a0] = oa[x]                 # a legal close (inside the bar) = the bar's open
                pt = [u for u in plug(oa[sl], ha[sl], la[sl], cc, day_id[sl], **kw) if u[0] + a0 == e]
                if [tuple(u[:4]) for u in pt] != [tuple(u[:4]) for u in base]:
                    ex_changed += 1
                    if len(examples) < 3:
                        examples.append({"entry": str(idx[e]), "exit_bar": str(idx[x]), "base": [list(u[:4]) for u in base],
                                         "perturbed_close": [list(u[:4]) for u in pt]})
                ct = rule(oa[sl], ha[sl], la[sl], cc, day_id[sl], kw.get("compress_k", 1.0), 12, 14, kw.get("trail_k", 2.0),
                          **dict(PLUGIN_WAY, same_bar_close=False, entry_bar_open_fill=False))
                cb = rule(oa[sl], ha[sl], la[sl], ca[sl], day_id[sl], kw.get("compress_k", 1.0), 12, 14,
                          kw.get("trail_k", 2.0), **dict(PLUGIN_WAY, same_bar_close=False, entry_bar_open_fill=False))
                ct = [u for u in ct if u[0] + a0 == e]
                cb = [u for u in cb if u[0] + a0 == e]
                if cb and ct and cb[0][1] <= x - a0 and ct != cb:
                    causal_changed += 1
            # (ii) entry: shuffle every bar from the entry bar on (except the fill open) - entry must not move
            en_tested += 1
            oo, hh, ll, cc = oa[sl].copy(), ha[sl].copy(), la[sl].copy(), ca[sl].copy()
            k0 = e - a0
            shift = rng_.normal(0, 5, size=len(cc) - k0)
            cc[k0:] = cc[k0:] + shift
            hh[k0:] = np.maximum(hh[k0:] + shift, np.maximum(cc[k0:], oo[k0:]))
            ll[k0:] = np.minimum(ll[k0:] + shift, np.minimum(cc[k0:], oo[k0:]))
            hh[k0] = max(hh[k0], oo[k0])
            ll[k0] = min(ll[k0], oo[k0])
            pe = [u for u in plug(oo, hh, ll, cc, day_id[sl], **kw) if u[0] + a0 == e]
            if not pe or pe[0][3] != side or abs(pe[0][4] - base[0][4]) > 1e-9:
                en_changed += 1
        probes[pname] = {"trades": len(Tp), "exit_close_perturbation_tested": ex_tested,
                         "exit_changed_by_own_bar_close_PLUGIN": ex_changed,
                         "exit_changed_by_own_bar_close_CAUSAL_fix": causal_changed,
                         "entry_future_perturbation_tested": en_tested, "entry_changed": en_changed,
                         "examples": examples,
                         "atr_bar_before_signal_bar": True}
    res["lookahead_probes"] = probes

    # ---------- 4. why it barely trades (TTM's own build, frozen rule's definitions) ----------
    diag = {}
    for nm, arr in (("raw", (o, h, l, c)), ("engine_signal_arrays", (oa, ha, la, ca))):
        oo, hh, ll, cc = arr
        atr, tr = atr_cumsum(hh, ll, cc, 14)
        starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
        ends = np.r_[starts[1:], len(cc)]
        rows = []
        for s, e in zip(starts, ends):
            if e - s < 14 or not np.isfinite(atr[s + 11]) or s < 2:
                continue
            rh, rl = hh[s:s + 12].max(), ll[s:s + 12].min()
            rngv = rh - rl
            out3 = tr[s - 2] + tr[s - 1] + tr[s]
            in11 = tr[s + 1:s + 12]
            rows.append((rngv, atr[s + 11], out3, in11.sum(), in11.max(), abs(oo[s] - cc[s - 1]), e - s,
                         float((hh[s:s + 12] - ll[s:s + 12]).mean())))
        X = np.array(rows)
        ratio = X[:, 0] / X[:, 1]
        kgrid = [0.5, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
        bys = {}
        for k in kgrid:
            cn = {}
            Rk = rule(oo, hh, ll, cc, day_id, k, counts=cn)
            bys["k=%.2f" % k] = {"quiet_sessions": cn["quiet"], "trades": len(Rk),
                                 "trades_per_yr": len(Rk) / res["years"], "quiet_pct": 100.0 * cn["quiet"] / cn["atr_ok"]}
        k120 = None
        for k in np.arange(1.0, 8.01, 0.05):
            if len(rule(oo, hh, ll, cc, day_id, float(k))) / res["years"] >= 120:
                k120 = round(float(k), 2)
                break
        cn = {}
        rule(oo, hh, ll, cc, day_id, 1.0, counts=cn)
        quiet = ratio <= 1.0
        diag[nm] = {
            "funnel_k1.0": cn,
            "sessions_scored": len(X),
            "range_over_atr14_percentiles": {str(p): float(np.percentile(ratio, p)) for p in (0.1, 1, 5, 10, 25, 50, 75)},
            "min_ratio": float(ratio.min()),
            "ties_ratio_eq_1": int(np.sum(np.abs(X[:, 0] - X[:, 1]) < 1e-9)),
            "by_k": bys, "k_needed_for_120_trades_per_yr": k120,
            "bound_inside_TR_le_range_all_sessions": bool(np.all(X[:, 4] <= X[:, 0] + 1e-9)),
            "necessary_outside3_ge_3x_range_sessions": int(np.sum(X[:, 2] >= 3 * X[:, 0] - 1e-9)),
            "median_range_pts": float(np.median(X[:, 0])), "median_atr14_pts": float(np.median(X[:, 1])),
            "median_gap_pts": float(np.median(X[:, 5])), "median_bar_hl_in_range_pts": float(np.median(X[:, 7])),
            "median_outside3_over_range": float(np.median(X[:, 2] / X[:, 0])),
            "quiet_sessions_detail": [{"range": float(r_[0]), "atr14": float(r_[1]), "outside3_tr": float(r_[2]),
                                       "gap": float(r_[5]), "session_bars": int(r_[6])} for r_ in X[quiet]][:10],
            "session_only_bar_hl_mean_ge_range_count": int(np.sum(X[:, 7] >= X[:, 0] - 1e-9)),
        }
    res["degenerate_diagnosis"] = diag
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_trace.json"), "wb").write(b)
    print(s)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()

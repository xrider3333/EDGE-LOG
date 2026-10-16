"""TTM (house verifier) STAGE 2 - COMPARE + TRACE for Qwen Lab idea QL_GAMMA_MOM (folder 20261015-1212-shelf30).

Runs after stage 1 posted its output sha (68dc4f43...). Now unblinded:
 1. arm A (plugin through the engine, house cost) vs the lab's numbers_pre_wf.json field by field, vs pre_wf_trades.csv and
    sandbox_pre_wf_out.json trade by trade;
 2. TTM's own rule (stage-1 arm B, re-written here with one switch per plugin departure) run THE PLUGIN'S WAY (all switches on)
    must match arm A 100% trade for trade; each switch alone on the literal reading = one slip variant, scored with the four numbers;
 3. look-ahead: fill checks on every trade + a future-perturbation test (every bar from the entry bar on is scrambled, the plugin
    re-run, the trade's entry/side/price must not move);
 4. trade-count anatomy (why ~36/yr, not the prior's 60).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1212-shelf30/."""
import csv
import hashlib
import json
import os
import sys
import time
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1212-shelf30"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261015-1212-shelf30"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = IDEA + "/plugin_v1.py.txt"
PIN_FULL = "cb3017465f3309d49616364cb722b0f76509e8f5036ea416fb945b2894214ceb"   # the prereg's Hashes line
STAGE1_JSON = OUT + "/ttm_verify.json"
STAGE1_SHA = "68dc4f4333b38874db25beca757c6b8da4962393956eb78a6b3129db78e774d2"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side over house cost
RB, LB, WM, SF = 6, 20, 1.5, 1.0       # prereg: first 6 bars, trailing 20 sessions, 1.5x, stop 1.0x range


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def sessions(day_id):
    n = len(day_id)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    return starts, np.r_[starts[1:], n]


def own_rule(o, h, l, c, day_id, warmup_min=None, tie_inclusive=False, plugin_scan_end=False, plugin_len_guard=False):
    """TTM's own reading of the prereg Mechanism (stage-1 arm B) with one switch per plugin departure.
    All switches off = the literal reading (stage-1 arm B). All on = the plugin's way.
      warmup_min      None: no trade until 20 prior sessions exist (literal 'trailing 20-session median').
                      5: plugin's fallback, median over ALL prior sessions when 5 <= prior < 20.
      tie_inclusive   False: wide day needs range > 1.5 x median (literal '>'). True: plugin's 'skip if rng < wm*med' (>=).
      plugin_scan_end False: breakout scan to the session's second-to-last bar (entry on the last bar allowed).
                      True: plugin's range(a+rb, b-2): last signal bar = third-to-last bar.
      plugin_len_guard False: no session-length rule beyond 'needs 6 bars for an OR'.
                      True: plugin's sessions with <= rb bars get range 0.0 (enter later medians) and sessions with
                      <= rb+2 bars never trade; also plugin's 'skip if rng <= 0 or med <= 0'.
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts, kind)]."""
    starts, ends = sessions(day_id)
    ranges, out = [], []
    for s, e in zip(starts, ends):
        nb = e - s
        if plugin_len_guard and nb <= RB:
            ranges.append(0.0)
            continue
        if nb < RB:
            ranges.append(np.nan)
            continue
        orh = float(h[s:s + RB].max())
        orl = float(l[s:s + RB].min())
        rng = orh - orl
        prior = ranges[-LB:]
        ranges.append(rng)
        if plugin_len_guard and (nb <= RB + 2 or rng <= 0):
            continue
        need = LB if warmup_min is None else warmup_min
        if len(prior) < need or np.any(np.isnan(prior)):
            continue
        if warmup_min is not None and len(prior) < LB:
            prior = ranges[:-1]            # plugin: session_ranges[:idx] (all prior sessions)
        med = float(np.median(prior))
        if plugin_len_guard and med <= 0:
            continue
        wide = (rng >= WM * med) if tie_inclusive else (rng > WM * med)
        if not wide:
            continue
        last_sig = (e - 3) if plugin_scan_end else (e - 1)
        side, k = 0, s + RB
        while k <= last_sig:
            if c[k] > orh:
                side = 1
                break
            if c[k] < orl:
                side = -1
                break
            k += 1
        if side == 0 or k >= e - 1:        # no breakout, or breakout on the last bar (no next bar in session)
            continue
        ent = k + 1
        ep = float(o[ent])
        stop = ep - side * SF * rng
        xb, xp, kind = e - 1, float(c[e - 1]), "time"
        for j in range(ent, e):
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp, kind = j, float(o[j]), "gap"
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp, kind = j, float(stop), "stop"
                break
        out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep)), kind))
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
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "dd5_n": int(r["n"]), "one_episode": bool(r["one_episode"]),
            "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, dtype=np.int64)].normalize()).groupby(level=0).sum()
    s = s.reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    gw, gl = float(usd[usd > 0].sum()), float(-usd[usd < 0].sum())
    f.update({"cost_pts": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "profit_factor": gw / gl if gl > 0 else float("nan")})
    return f


def three(xb, pts, idxn, days):
    return {"house": score(xb, pts, idxn, days, COST), "real": score(xb, pts, idxn, days, REAL_COST),
            "stress": score(xb, pts, idxn, days, STRESS_COST)}


def fourstr(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%d/yr) | $/yr %s%s"
            % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], format(f["trades"], ","),
               round(f["trades_per_yr"]), format(round(f["per_yr"]), ","), " | ONE EPISODE" if f["one_episode"] else ""))


def keyed(tr):
    return {(t[0], t[2]): t for t in tr}


def diff(ta, tb):
    """ta, tb: lists of (entry, exit, side, entry_px, gross_pts)."""
    ka, kb = keyed(ta), keyed(tb)
    both = sorted(set(ka) & set(kb))
    exact = [k for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9 and abs(ka[k][4] - kb[k][4]) < 1e-9]
    return {"A": len(ta), "B": len(tb), "same_entry_side": len(both), "exact": len(exact),
            "only_A": sorted(set(ka) - set(kb)), "only_B": sorted(set(kb) - set(ka)),
            "match_100pct": len(ta) == len(tb) == len(exact)}


def main():
    t0 = time.time()
    res = {"idea": "QL_GAMMA_MOM", "folder": "20261015-1212-shelf30", "stage": "2 compare + trace"}
    assert hashlib.sha256(open(STAGE1_JSON, "rb").read()).hexdigest() == STAGE1_SHA, "stage-1 output changed"
    res["stage1_sha_ok"] = True
    pin = lf_sha(PLUGIN)
    assert pin == PIN_FULL, "plugin pin"
    res["plugin_lf_sha256"] = pin
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    assert days[-1] < pd.Timestamp("2016-07-01")
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res.update({"registry_id": row[0].get("id"), "fingerprint": A.get("fingerprint"), "bars": len(c), "sessions": len(days)})

    # ---- ARM A: the plugin through the engine ---------------------------------------------------------------------
    m = types.ModuleType("ttm_ql_gamma_mom")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    TA = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]  # entry, exit, side, px, gross
    sA = three([t[1] for t in TA], [t[4] for t in TA], idxn, days)
    res["arm_A"] = sA
    res["four_numbers"] = {k: fourstr(v) for k, v in sA.items()}

    # ---- 1. arm A (house) vs the lab's numbers file, field by field --------------------------------------------------
    lab = json.load(open(IDEA + "/numbers_pre_wf.json", encoding="utf-8"))
    L = lab["numbers"]
    hA = sA["house"]
    checks = [  # field, lab value, mine, tolerance
        ("trades", L["trades"], hA["trades"], 0),
        ("net_usd", L["net_usd"], round(hA["net_usd"], 4), 1.0),
        ("roc_30k", L["roc_30k"], round(hA["roc30"], 6), 0.005),
        ("dd5_usd", L["dd5_usd"], hA["dd5"], 1.0),
        ("max_dd_usd", L["max_dd_usd"], round(hA["max_dd"], 4), 1.0),
        ("dd_pct_peak", L["dd_pct_peak"], round(hA["dd_pct_peak"], 6), 0.01),
        ("sortino", L["sortino"], round(hA["sortino"], 6), 0.001),
        ("one_episode", L["one_episode"], hA["one_episode"], None),
        ("win_rate (lab %, mine x100)", L["win_rate"], round(100 * hA["win_rate"], 4), 0.05),
        ("dd5_n (extra)", L.get("dd5_n"), hA["dd5_n"], 0),
        ("years (extra)", L.get("years"), round(hA["years"], 4), 0.001),
        ("sessions (extra)", L.get("sessions"), len(days), 0),
        ("trades_per_year (extra, lab 1dp)", L.get("trades_per_year"), round(hA["trades_per_yr"], 3), 0.05),
        ("profit_factor (extra)", L.get("profit_factor"), round(hA["profit_factor"], 6), 0.001),
        ("cost_pts (extra)", lab.get("cost_pts"), COST, 0),
        ("bars (extra)", lab.get("bars"), len(c), 0),
        ("fingerprint (extra)", lab.get("fingerprint"), A.get("fingerprint"), None),
    ]
    rows = []
    for f, lv, mv, tol in checks:
        ok = (lv == mv) if tol is None else abs(float(lv) - float(mv)) <= tol + 1e-12
        rows.append({"field": f, "lab": lv, "mine": mv, "tol": tol, "match": bool(ok)})
    res["lab_vs_arm_A_numbers_pre_wf"] = rows
    res["numbers_all_match"] = all(x["match"] for x in rows)

    # trade by trade vs pre_wf_trades.csv (net pts = gross - house cost) and sandbox_pre_wf_out.json
    with open(IDEA + "/pre_wf_trades.csv", newline="", encoding="utf-8") as fh:
        C = list(csv.DictReader(fh))
    bad = []
    for i, (row_, t) in enumerate(zip(C, TA)):
        ok = (int(row_["entry_bar"]) == t[0] and int(row_["exit_bar"]) == t[1] and int(row_["side"]) == t[2]
              and abs(float(row_["entry_price"]) - t[3]) < 1e-9 and abs(float(row_["pnl_points_net"]) - (t[4] - COST)) < 1e-5
              and row_["entry_time"] == str(idx[t[0]]) and row_["exit_time"] == str(idx[t[1]]))
        if not ok:
            bad.append([i, row_, t])
    res["lab_trades_csv"] = {"rows": len(C), "arm_A": len(TA), "rows_matching": len(C) - len(bad) if len(C) == len(TA) else None,
                             "all_match": len(C) == len(TA) and not bad, "first_bad": bad[:3]}
    sb = json.load(open(IDEA + "/sandbox_pre_wf_out.json", encoding="utf-8"))
    sbt = sb["trades"]
    sbad = [i for i, (u, t) in enumerate(zip(sbt, TA))
            if not (u[0] == t[0] and u[1] == t[1] and u[3] == t[2] and abs(u[4] - t[3]) < 1e-9 and abs(u[2] - (t[4] - COST)) < 1e-5)]
    res["lab_sandbox_out"] = {"trades": len(sbt), "all_match": len(sbt) == len(TA) and not sbad, "bars": sb.get("bars"),
                              "fingerprint": sb.get("fingerprint"), "first": sb.get("first"), "last": sb.get("last")}

    # ---- 2. own rule: literal, each slip alone, the plugin's way --------------------------------------------------
    def T(tr):
        return [(t[0], t[1], t[2], t[3], t[5]) for t in tr]
    variants = {
        "B_literal": dict(),
        "B+warmup_fallback": dict(warmup_min=5),
        "B+tie_inclusive": dict(tie_inclusive=True),
        "B+scan_end_b-2": dict(plugin_scan_end=True),
        "B+session_len_guard": dict(plugin_len_guard=True),
        "PLUGIN_WAY(all four)": dict(warmup_min=5, tie_inclusive=True, plugin_scan_end=True, plugin_len_guard=True),
        "PLUGIN_WAY_minus_warmup": dict(tie_inclusive=True, plugin_scan_end=True, plugin_len_guard=True),
        "PLUGIN_WAY_minus_tie": dict(warmup_min=5, plugin_scan_end=True, plugin_len_guard=True),
    }
    V, vres = {}, {}
    for name, kw in variants.items():
        tr = own_rule(o, h, l, c, day_id, **kw)
        V[name] = tr
        d = diff(TA, T(tr))
        vres[name] = {"switches": kw, "trades": len(tr), "sum_gross_pts": float(sum(t[5] for t in tr)),
                      "vs_A": {k: v for k, v in d.items() if k not in ("only_A", "only_B")},
                      "only_A": [[str(idxn[k[0]]), k[1], keyed(TA)[k][4]] for k in d["only_A"]],
                      "only_B": [[str(idxn[k[0]]), k[1], keyed(T(tr))[k][4]] for k in d["only_B"]],
                      "scores": three([t[1] for t in tr], [t[5] for t in tr], idxn, days)}
        vres[name]["four_numbers"] = {k: fourstr(v) for k, v in vres[name]["scores"].items()}
    res["variants"] = vres
    pw = vres["PLUGIN_WAY(all four)"]["vs_A"]
    res["b_plugin_way_matches_100pct"] = bool(pw["match_100pct"])
    # stage-1 arm B reproduced?
    s1 = json.load(open(STAGE1_JSON, encoding="utf-8"))
    res["B_literal_equals_stage1_armB"] = (vres["B_literal"]["trades"] == s1["A_vs_B"]["B_trades"]
                                           and abs(vres["B_literal"]["scores"]["house"]["net_usd"]
                                                   - s1["B_own_rule"]["house_cost"]["net_usd"]) < 1e-6)

    # ---- slip anatomy: how often each switch could matter in this window ------------------------------------------
    starts, ends = sessions(day_id)
    nbars = ends - starts
    res["session_length"] = {"min": int(nbars.min()), "max": int(nbars.max()),
                             "n_le_8": int((nbars <= RB + 2).sum()), "n_lt_78": int((nbars < 78).sum()),
                             "counts_short": {int(k): int(v) for k, v in zip(*np.unique(nbars[nbars < 78], return_counts=True))}}
    rngs = np.array([h[a:a + RB].max() - l[a:a + RB].min() for a, b in zip(starts, ends)])
    first_brk_pos, wide_lit, wide_tie = [], 0, 0
    eligible = 0
    for i, (a, b) in enumerate(zip(starts, ends)):
        if i < LB:
            continue
        eligible += 1
        med = float(np.median(rngs[i - LB:i]))
        if rngs[i] > WM * med:
            wide_lit += 1
        elif rngs[i] >= WM * med:
            wide_tie += 1
            continue
        else:
            continue
        orh, orl = h[a:a + RB].max(), l[a:a + RB].min()
        pos = None
        for k in range(a + RB, b):
            if c[k] > orh or c[k] < orl:
                pos = k
                break
        first_brk_pos.append(None if pos is None else int(b - 1 - pos))   # 0 = last bar, 1 = second-to-last
    fb = [x for x in first_brk_pos if x is not None]
    res["trade_count_anatomy"] = {
        "sessions": len(days), "sessions_with_20_prior": eligible,
        "wide_days_strict": wide_lit, "wide_day_pct": round(100.0 * wide_lit / eligible, 2), "exact_ties": wide_tie,
        "wide_days_with_close_breakout": len(fb), "wide_days_no_breakout": first_brk_pos.count(None),
        "first_breakout_on_last_bar": fb.count(0), "first_breakout_on_second_to_last_bar": fb.count(1),
        "warmup_sessions_5_to_19_prior": int(LB - 5),
        "prior_trades_per_yr": 60.0, "actual_trades_per_yr": round(hA["trades_per_yr"], 2)}

    # ---- 3. look-ahead -------------------------------------------------------------------------------------------
    sess_of = np.searchsorted(starts, np.arange(len(c)), side="right") - 1
    fills = {"entry_eq_open": 0, "signal_close_beyond_OR": 0, "OR_bars_before_signal": 0, "exit_px_inside_exit_bar": 0,
             "stop_dist_eq_OR_range": 0, "stop_exits": 0, "time_exits_at_last_close": 0, "time_exits": 0, "n": len(TA)}
    for (e, x, side, px, g) in TA:
        si = sess_of[e]
        a, b = starts[si], ends[si]
        orh, orl = h[a:a + RB].max(), l[a:a + RB].min()
        k = e - 1
        fills["entry_eq_open"] += int(abs(px - o[e]) < 1e-9)
        fills["signal_close_beyond_OR"] += int((c[k] > orh) if side > 0 else (c[k] < orl))
        fills["OR_bars_before_signal"] += int(a + RB - 1 < k)
        xp = px + side * g
        fills["exit_px_inside_exit_bar"] += int(l[x] - 1e-9 <= xp <= h[x] + 1e-9)
        if x == b - 1 and abs(xp - c[b - 1]) < 1e-9:
            fills["time_exits"] += 1
            fills["time_exits_at_last_close"] += 1
        else:
            fills["stop_exits"] += 1
            stop = px - side * SF * (orh - orl)
            fills["stop_dist_eq_OR_range"] += int(abs(xp - stop) < 1e-9 or abs(xp - o[x]) < 1e-9)
    res["lookahead_fill_checks"] = fills
    # direct call on the raw arrays == engine call (so the perturbation test below sees what the engine sees)
    rd = m.run_backtest(o, h, l, c, None, day_id=day_id, return_trades=True)
    TD = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in rd["trades"]]
    res["direct_call_equals_engine"] = TD == TA
    # perturbation: scramble every bar from the entry bar on (keep the entry bar's open), re-run, the trade must stay
    rs = np.random.default_rng(20261016)
    moved, earlier_moved = [], 0
    for (e, x, side, px, g) in TA:
        o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
        n2 = len(c) - e
        base = o[e] + np.cumsum(rs.normal(0, 8, n2))
        c2[e:] = base
        o2[e + 1:] = base[:-1] + rs.normal(0, 2, n2 - 1)
        h2[e:] = np.maximum(base, np.r_[o[e], o2[e + 1:]]) + np.abs(rs.normal(0, 6, n2))
        l2[e:] = np.minimum(base, np.r_[o[e], o2[e + 1:]]) - np.abs(rs.normal(0, 6, n2))
        rp = m.run_backtest(o2, h2, l2, c2, None, day_id=day_id, return_trades=True)
        tp = {(int(t[0]), int(t[3])): float(t[4]) for t in rp["trades"]}
        if tp.get((e, side)) is None or abs(tp[(e, side)] - px) > 1e-9:
            moved.append([str(idxn[e]), side])
        before = sorted(k for k in tp if k[0] < e)
        want = sorted((t[0], t[2]) for t in TA if t[0] < e)
        earlier_moved += int(before != want)
    res["lookahead_perturbation"] = {"trades_tested": len(TA), "entry_moved": len(moved), "first_moved": moved[:5],
                                     "runs_where_earlier_entries_changed": earlier_moved}
    res["secs"] = round(time.time() - t0, 1)
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    path = os.path.join(OUT, "ttm_trace.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(s + "\n")
    print(s)
    print("output", path, "sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()

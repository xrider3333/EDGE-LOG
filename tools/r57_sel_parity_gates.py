# -*- coding: utf-8 -*-
"""ENGU-Q ROUND 57 -- ORDER OF WORK ITEM 1: THE PARITY GATES FOR THE RESEARCH SIBLING.

Contract: ENGUQ_R57_PREREG.md (a7f0811), section 7 item 1. Nothing else in the round is read
until every gate below passes. This driver reads NO hypothesis result: for the four centre cells
it only compares trade lists and features, and it prints no variant performance at all (no count,
no P&L, no win rate), so it cannot leak a selection or LB number into the gate step.

  G1  all knobs OFF at R2 settings == ENGUQ_1M_ETH_R2_1_0.py trade for trade (full window), and
      measure() on the selection stretch == the frontier table row 1 (r57_frontier.json)
  G2  all knobs OFF at R5 settings == ENGUQ_1M_ETH_R5_1_0.py trade for trade, == frontier row 9
  G3  each centre cell, compiled vs interpreted (EDGELOG_NO_FASTLOOP=1), feature memo cleared
      between the two: identical count / entry bar / exit bar / entry price / per-trade P&L
  G4  feature parity: A (ATR14 percentile vs a stride-23 local copy of
      trade_anatomy.pctile_vs_prior_days; CSV sanity median), B (daily stretch vs CSV
      ta_lvl_sma20d_atr, 1e-6), C (leg recovery vs CSV loc_pb_recovery, 1e-9), D (V / clock
      baseline vs CSV imb_vol_vs_clock20, 1e-9); plus "in-engine" identity: the helper's mask fed
      back as _mask_override reproduces the knob-on trade list exactly
  G5  tools/exec_feasibility_audit.py --config per centre cell (and the file-level static scan),
      plus hand-audit evidence: every interpreted signal bar passes its own mask, and every
      feature is unchanged when the frame is truncated at a bar (nothing after the bar is read)

Run from the SHARED checkout (master registry):
    cd C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG
    python C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\enguq57\\tools\\r57_sel_parity_gates.py [--beacon]
"""
import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import time

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.pop("EDGELOG_NO_FASTLOOP", None)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)
SEL = os.path.join(WT, "augur_strategies", "ENGUQ_1M_ETH_SEL_1_0.py")
R2 = "ENGUQ_1M_ETH_R2_1_0.py"
R5 = "ENGUQ_1M_ETH_R5_1_0.py"
CSV = r"C:\EdgeLog\_anatomy_cache\r57\r57_selection_signal_features.csv"
FRONTIER_JSON = os.path.join(HERE, "r37_results", "r57_frontier.json")
OUT_TXT = os.path.join(HERE, "r37_results", "r57_sel_parity_gates.txt")
OUT_JSON = os.path.join(HERE, "r37_results", "r57_sel_parity_gates.json")
KNOBS_OFF = dict(quiet_pct=0.0, stretch_max=0.0, rec_min=0.0, vol_clock=0.0)
CENTRES = [("H-A", "quiet_pct", 20.0), ("H-B", "stretch_max", 1.5), ("H-C", "rec_min", 0.45),
           ("H-D", "vol_clock", 1.25)]


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FR = _load_by_path("r57_frontier_harness", os.path.join(HERE, "r57_enguq_frontier.py"))
TA = _load_by_path("trade_anatomy_r57gates", os.path.join(HERE, "trade_anatomy.py"))
os.chdir(ROOT)

from augur_engine import fastloop                                       # noqa: E402
from augur_engine.data import find_master, load_master_arrays           # noqa: E402
from augur_engine.engine import run_backtest                            # noqa: E402
from augur_engine.strategies import load_strategy                       # noqa: E402
from queue_guard import resolve_params                                  # noqa: E402

OUT = []
RESULTS = []


def say(s=""):
    print(s, flush=True)
    OUT.append(s)


def gate(name, passed, **numbers):
    RESULTS.append(dict(gate=name, passed=bool(passed), **numbers))
    say("  -> %s %s" % (name, "PASS" if passed else "FAIL"))


def trades_of(r):
    return sorted((r or {}).get("trades") or [], key=lambda z: z[0])


def compare_trades(a, b, pnl_shift=0.0):
    """Exact trade-for-trade comparison; returns a dict of mismatch counts."""
    d = dict(count_a=len(a), count_b=len(b), count_equal=len(a) == len(b), entry_bar=0, exit_bar=0,
             entry_px=0, pnl=0, max_abs_pnl_diff=0.0, max_abs_px_diff=0.0)
    for x, y in zip(a, b):
        d["entry_bar"] += int(int(x[0]) != int(y[0]))
        d["exit_bar"] += int(int(x[1]) != int(y[1]))
        dp = abs(float(x[2]) - pnl_shift - float(y[2]))
        dx = abs(float(x[4]) - float(y[4]))
        d["pnl"] += int(dp > 1e-9)
        d["entry_px"] += int(dx > 1e-9)
        d["max_abs_pnl_diff"] = max(d["max_abs_pnl_diff"], dp)
        d["max_abs_px_diff"] = max(d["max_abs_px_diff"], dx)
    d["identical"] = (d["count_equal"] and d["entry_bar"] == 0 and d["exit_bar"] == 0 and d["pnl"] == 0
                      and d["entry_px"] == 0)
    return d


def sel_fields(M):
    """The selection-side measure() fields a frontier row carries (no LB field)."""
    s = M["sel"]
    return {"sel.n": s["n"], "sel.wr": s["wr"], "sel.pf": s["pf"], "sel.net": s["net"], "sel.dd": s["dd"],
            "sel.mar": s["mar"], "sel.evr": s["evr"], "sel_ex10_net": M["sel_ex10_net"], "top10": M["top10"],
            "era1.n": M["era1"]["n"], "era1.net": M["era1"]["net"], "era1.top10": M["era1"]["top10"],
            "era1.ex10": M["era1"]["ex10"], "era2.n": M["era2"]["n"], "era2.net": M["era2"]["net"],
            "era2.top10": M["era2"]["top10"], "era2.ex10": M["era2"]["ex10"], "ttz": M["ttz"],
            "evr_ex05": M["evr_ex05"], "corr_sel": M["corr_sel"], "y2018": M["y2018"], "y2022": M["y2022"],
            "hold_sel": M["hold_sel"], "med_w": M["med_w"], "med_l": M["med_l"],
            "wr_ex_scratch": M["wr_ex_scratch"]}


def match_frontier(M, row):
    bad = []
    for k, v in sel_fields(M).items():
        a, b = k.split(".") if "." in k else (k, None)
        ref = row[a][b] if b else row[a]
        if ref is None and (v is None or (isinstance(v, float) and not math.isfinite(v))):
            continue
        if ref is None or v is None or abs(float(v) - float(ref)) > 1e-6 * max(1.0, abs(float(ref))):
            bad.append((k, v, ref))
    ys = {int(k): v for k, v in row["yearly_sel"].items()}
    for y, v in M["yearly_sel"].items():
        if abs(v - ys.get(int(y), float("nan"))) > 1e-6:
            bad.append(("yearly_sel.%d" % y, v, ys.get(int(y))))
    return bad


def clear_memo():
    load_strategy(SEL)._MEMO.clear()


def run_eng(fn, params, A, slow=False):
    if slow:
        os.environ["EDGELOG_NO_FASTLOOP"] = "1"
    try:
        t = time.time()
        r = run_backtest(fn, arrays=A, params=dict(params), cost_pts=FR.COST, return_trades=True)
        return r, time.time() - t, fastloop.enabled()
    finally:
        os.environ.pop("EDGELOG_NO_FASTLOOP", None)


def pctile_vs_prior_days_stride23(x, day_id, year_days=252, min_days=60, samples_per_day=60):
    """LOCAL COPY of tools/trade_anatomy.pctile_vs_prior_days with the stride forced to 23
    (ENGUQ_R57_PREREG.md G4-A). Every other line is the original."""
    x = np.asarray(x, float)
    n = len(x)
    out = np.full(n, np.nan)
    days = np.asarray(day_id)
    if n == 0:
        return out
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    ends = np.r_[starts[1:], n]
    stride = 23                                            # forced (original: median bars/day // 60)
    day_samples = [x[s:e:stride] for s, e in zip(starts, ends)]
    for k in range(len(starts)):
        if k < min_days:
            continue
        ref = np.concatenate(day_samples[max(0, k - year_days):k])
        ref = ref[~np.isnan(ref)]
        if len(ref) < 100:
            continue
        ref.sort()
        seg = x[starts[k]:ends[k]]
        r = np.searchsorted(ref, seg, side="right") / float(len(ref)) * 100.0
        r[np.isnan(seg)] = np.nan
        out[starts[k]:ends[k]] = r
    return out


def run(step):
    t_all = time.time()
    say("=" * 118)
    say("ENGU-Q ROUND 57 -- ORDER OF WORK ITEM 1: PARITY GATES G1-G5 for ENGUQ_1M_ETH_SEL_1_0.py   (run %s)"
        % time.strftime("%Y-%m-%d %H:%M"))
    say("contract ENGUQ_R57_PREREG.md a7f0811 | tape NQ 1m ETH db_noadj_eth | window %s..%s pinned | cost %.3f x $%d"
        % (FR.WIN[0], FR.WIN[1], FR.COST, FR.MULT))
    say("SEL file: %s" % SEL)
    say("numba available: %s | AUGUR_TRIAL_CACHE=%s OMP_NUM_THREADS=%s"
        % (fastloop.HAVE_NUMBA, os.environ.get("AUGUR_TRIAL_CACHE"), os.environ.get("OMP_NUM_THREADS")))
    say("No variant performance is printed below: centre cells are compared trade list against trade list only.")
    say("=" * 118)

    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    A = load_master_arrays(m, date_from=FR.WIN[0], date_to=FR.WIN[1])
    idx = pd.DatetimeIndex(A["index"])
    n = len(idx)
    say("master %s id %s: %d bars %s .. %s" % (m.get("filename"), m.get("id"), n, idx[0], idx[-1]))
    idx_naive = idx.tz_localize(None)
    bench_sel = FR.year_bench(idx_naive, A["close"], upto=pd.Timestamp(FR.SPLIT))
    bench_all = FR.year_bench(idx_naive, A["close"])
    frontier = {r["num"]: r for r in json.load(open(FRONTIER_JSON, encoding="utf-8"))["rows"]}
    sel_mod = load_strategy(SEL)

    # ------------------------------------------------------------------ G1
    say("\nG1  all knobs OFF at R2 settings vs ENGUQ_1M_ETH_R2_1_0.py")
    P2, _s2, _h2 = resolve_params(R2, {})
    PS, srcS, _hS = resolve_params(SEL, {})
    defaults_ok = (all(PS[k] == v for k, v in P2.items()) and all(PS[k] == 0 for k in KNOBS_OFF)
                   and PS["max_hold_bars"] == 0 and set(PS) == set(P2) | set(KNOBS_OFF) | {"max_hold_bars"})
    say("  SEL DEFAULT_PARAMS resolved: %s" % json.dumps(PS, sort_keys=True))
    say("  == R2 DEFAULT_PARAMS on every R2 key, four knobs 0, max_hold_bars 0: %s" % defaults_ok)
    rR2, tR2, _ = run_eng(R2, P2, A)
    rS0, tS0, _ = run_eng(SEL, PS, A)
    T_R2, T_S0 = trades_of(rR2), trades_of(rS0)
    c1 = compare_trades(T_R2, T_S0)
    M0 = FR.measure(T_S0, A, FR.MULT, bench_sel, bench_all)
    s, w = M0["sel"], M0["whole"]
    say("  trade for trade (full window): count %d vs %d, mismatches entry %d exit %d entry px %d P&L %d (max |dP&L| %.3g)"
        % (c1["count_a"], c1["count_b"], c1["entry_bar"], c1["exit_bar"], c1["entry_px"], c1["pnl"], c1["max_abs_pnl_diff"]))
    say("  SEL control: whole n=%d net $%s | selection n=%d win %.1f%% PF %.3f net $%s DD $%s MAR %.2f EV R %.3f"
        % (w["n"], FR.f0(w["net"]), s["n"], s["wr"], s["pf"], FR.f0(s["net"]), FR.f0(s["dd"]), s["mar"], s["evr"]))
    want1 = (w["n"] == 1949 and round(w["net"]) == 613126 and s["n"] == 1831 and round(s["pf"], 3) == 1.717
             and round(s["net"]) == 524745 and round(s["dd"]) == 38687)
    say("  want whole 1,949 / $613,126; selection 1,831 / PF 1.717 / $524,745 / DD $38,687: %s" % want1)
    bad1 = match_frontier(M0, frontier[1])
    say("  every selection-side measure() field == frontier row 1 (r57_frontier.json): %s%s"
        % (not bad1, "" if not bad1 else "  MISMATCH %s" % bad1[:6]))
    # interpreted control == compiled control (probe walk; gross P&L minus cost)
    sig_probe = []
    t = time.time()
    r_int = sel_mod.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"],
                                 day_id=A["day_id"], index=A["index"], return_trades=True,
                                 _signal_index_probe=sig_probe, **PS)
    c1b = compare_trades(sorted(r_int["trades"], key=lambda z: z[0]), T_S0, pnl_shift=FR.COST)
    say("  SEL control interpreted (signal-index probe, %.0fs) vs compiled: identical %s (count equal %s, max |dP&L| %.3g)"
        % (time.time() - t, c1b["identical"], c1b["count_equal"], c1b["max_abs_pnl_diff"]))
    g1 = defaults_ok and c1["identical"] and want1 and not bad1 and c1b["identical"]
    gate("G1", g1, trades_identical_vs_R2=c1["identical"], mismatches=dict((k, c1[k]) for k in ("entry_bar", "exit_bar", "entry_px", "pnl")),
         whole_n=w["n"], whole_net=round(w["net"], 2), sel_n=s["n"], sel_win_pct=round(s["wr"], 2),
         sel_pf=round(s["pf"], 4), sel_net=round(s["net"], 2), sel_dd=round(s["dd"], 2), sel_mar=round(s["mar"], 3),
         sel_evr=round(s["evr"], 4), frontier_row1_fields_mismatched=len(bad1), defaults_equal_r2=defaults_ok,
         interpreted_equals_compiled=c1b["identical"])
    step(1)

    # ------------------------------------------------------------------ G2
    say("\nG2  all knobs OFF at R5 settings vs ENGUQ_1M_ETH_R5_1_0.py")
    P5, _s5, _h5 = resolve_params(R5, {})
    PS5 = dict(P5, **KNOBS_OFF)
    say("  R5 settings (every param explicit): %s" % json.dumps(PS5, sort_keys=True))
    r5, _, _ = run_eng(R5, P5, A)
    rS5, _, _ = run_eng(SEL, PS5, A)
    T_R5, T_S5 = trades_of(r5), trades_of(rS5)
    c2 = compare_trades(T_R5, T_S5)
    M5 = FR.measure(T_S5, A, FR.MULT, bench_sel, bench_all)
    s5, w5 = M5["sel"], M5["whole"]
    say("  trade for trade (full window): count %d vs %d, mismatches entry %d exit %d entry px %d P&L %d"
        % (c2["count_a"], c2["count_b"], c2["entry_bar"], c2["exit_bar"], c2["entry_px"], c2["pnl"]))
    say("  SEL at R5 settings: whole n=%d net $%s | selection n=%d win %.1f%% PF %.3f net $%s DD $%s"
        % (w5["n"], FR.f0(w5["net"]), s5["n"], s5["wr"], s5["pf"], FR.f0(s5["net"]), FR.f0(s5["dd"])))
    want2 = (w5["n"] == 2585 and round(w5["net"]) == 566907 and s5["n"] == 2434 and round(s5["net"]) == 466910)
    say("  want whole 2,585 / $566,907; selection 2,434 / $466,910 (prereg also: win 28.4%%, PF 1.519, DD $30,527): %s"
        % want2)
    bad2 = match_frontier(M5, frontier[9])
    say("  every selection-side measure() field == frontier row 9: %s%s" % (not bad2, "" if not bad2 else "  MISMATCH %s" % bad2[:6]))
    g2 = c2["identical"] and want2 and not bad2
    gate("G2", g2, trades_identical_vs_R5=c2["identical"], mismatches=dict((k, c2[k]) for k in ("entry_bar", "exit_bar", "entry_px", "pnl")),
         whole_n=w5["n"], whole_net=round(w5["net"], 2), sel_n=s5["n"], sel_win_pct=round(s5["wr"], 2),
         sel_pf=round(s5["pf"], 4), sel_net=round(s5["net"], 2), sel_dd=round(s5["dd"], 2),
         frontier_row9_fields_mismatched=len(bad2))
    del r5, rS5, T_R5, T_S5, rR2, T_R2
    step(2)

    # ------------------------------------------------------------------ G3
    say("\nG3  centre cells, compiled vs interpreted (EDGELOG_NO_FASTLOOP=1), full window; feature memo cleared between")
    CELL_TRADES = {}
    g3_all = True
    for hyp, knob, val in CENTRES:
        P = dict(PS, **{knob: val})
        clear_memo()
        rf, tf, en_f = run_eng(SEL, P, A)
        clear_memo()
        rs, ts, en_s = run_eng(SEL, P, A, slow=True)
        Tf, Ts = trades_of(rf), trades_of(rs)
        cc = compare_trades(Ts, Tf)
        differs = Tf != T_S0
        CELL_TRADES[hyp] = Tf
        ok = cc["identical"] and en_f and differs
        g3_all = g3_all and ok
        say("  %s %s=%g: compiled %.1fs (fastloop on=%s) | interpreted %.1fs | count equal %s, mismatches entry %d "
            "exit %d entry px %d P&L %d, max |dP&L| %.3g | trade list differs from the knob-off control: %s -> %s"
            % (hyp, knob, val, tf, en_f, ts, cc["count_equal"], cc["entry_bar"], cc["exit_bar"], cc["entry_px"],
               cc["pnl"], cc["max_abs_pnl_diff"], differs, "identical" if cc["identical"] else "DIFFERENT"))
        RESULTS.append(dict(gate="G3-%s" % hyp, passed=ok, knob=knob, value=val, count_equal=cc["count_equal"],
                            mismatches=dict((k, cc[k]) for k in ("entry_bar", "exit_bar", "entry_px", "pnl")),
                            max_abs_pnl_diff=cc["max_abs_pnl_diff"], compiled_secs=round(tf, 2),
                            interpreted_secs=round(ts, 2), differs_from_control=differs))
        del rf, rs, Ts
    gate("G3", g3_all)
    step(3)

    # ------------------------------------------------------------------ G4
    say("\nG4  feature parity (in-engine helper features; anatomy CSV %s)" % CSV)
    T = pd.read_csv(CSV)
    sig = T["signal_bar"].to_numpy(np.int64)
    split_bar = int(idx.searchsorted(pd.Timestamp(FR.SPLIT, tz=idx.tz)))
    sel_entries = [t for t in T_S0 if int(t[0]) < split_bar]
    link_ok = (len(sel_entries) == len(T) and all(int(a[0]) == int(b) and int(a[1]) == int(c_)
                                                  for a, b, c_ in zip(sel_entries, T["fill_bar"], T["exit_bar"])))
    probe_set = set(sig_probe)
    in_probe = int(sum(1 for b in sig if int(b) in probe_set))
    say("  CSV rows %d; CSV fill/exit bars == SEL control selection trades (entry, exit): %s; CSV signal bars that are "
        "signals of the SEL control's own interpreted walk: %d of %d" % (len(T), link_ok, in_probe, len(T)))
    clear_memo()
    t = time.time()
    F = sel_mod._rule_features(A["open"], A["high"], A["low"], A["close"], A["volume"], A["index"],
                               tl_len=int(PS["tl_len"]))
    say("  in-engine features built in %.1fs" % (time.time() - t))

    # in-engine identity: the helper's mask, fed back as _mask_override, reproduces the knob-on run
    tr_eng = sel_mod._true_range(np.asarray(A["high"], float), np.asarray(A["low"], float), np.asarray(A["close"], float))
    ident = {}
    for hyp, knob, val in CENTRES:
        kn = dict(KNOBS_OFF, **{knob: val})
        mask = sel_mod._rule_mask(np.asarray(A["high"], float), np.asarray(A["low"], float), np.asarray(A["close"], float),
                                  A["volume"], idx, tr_eng, int(PS["tl_len"]), kn["quiet_pct"], kn["stretch_max"],
                                  kn["rec_min"], kn["vol_clock"])
        ro, _, _ = run_eng(SEL, dict(PS, **{knob: val}, _mask_override=mask), A)
        ident[hyp] = compare_trades(trades_of(ro), CELL_TRADES[hyp])["identical"]
        say("  %s helper mask as _mask_override reproduces the %s=%g trade list exactly: %s" % (hyp, knob, val, ident[hyp]))

    def cmp_at(feat, col, tol):
        x = F[feat][sig]
        y = T[col].to_numpy(float)
        v = np.isfinite(y)
        fin_x = np.isfinite(x[v])
        d = np.abs(x[v] - y[v])
        return dict(csv_non_nan=int(v.sum()), engine_finite_on_those=int(fin_x.sum()),
                    max_abs_diff=float(np.nanmax(d)) if v.any() else float("nan"),
                    median_abs_diff=float(np.nanmedian(d)) if v.any() else float("nan"),
                    n_over_tol=int(np.sum(~(d <= tol))), csv_nan_rows=int((~v).sum()),
                    engine_nan_where_csv_nan=int(np.sum(~np.isfinite(x[~v]))))

    # G4-A
    t = time.time()
    sh = (idx + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8
    sess_ref = pd.factorize(sh)[0].astype(np.int64)
    atr14_ref = TA.calc_atr(A["high"], A["low"], A["close"], 14)
    q_ref = pctile_vs_prior_days_stride23(atr14_ref, sess_ref, 252, 60, 60)
    qa = F["q"]
    nan_eq = bool(np.array_equal(np.isnan(qa), np.isnan(q_ref)))
    fin = np.isfinite(qa) & np.isfinite(q_ref)
    qmax = float(np.max(np.abs(qa[fin] - q_ref[fin]))) if fin.any() else float("nan")
    ca = cmp_at("q", "ta_ind_atr_pctile_bar", 1.5)
    say("  G4-A local copy built in %.0fs | all %d bars: NaN pattern identical %s, finite bars %d, max |q - copy| %.3g "
        "(tol 1e-9) | vs CSV ta_ind_atr_pctile_bar on %d non-NaN signal bars: median |diff| %.3f pts (bar <= 1.5), "
        "max %.2f, engine finite on those %d"
        % (time.time() - t, n, nan_eq, int(fin.sum()), qmax, ca["csv_non_nan"], ca["median_abs_diff"],
           ca["max_abs_diff"], ca["engine_finite_on_those"]))
    g4a = nan_eq and qmax <= 1e-9 and ca["median_abs_diff"] <= 1.5 and ident["H-A"]
    RESULTS.append(dict(gate="G4-A", passed=g4a, bars=n, nan_pattern_identical=nan_eq, finite_bars=int(fin.sum()),
                        max_abs_diff_vs_local_copy=qmax, csv=ca, override_identity=ident["H-A"]))
    say("  -> G4-A %s" % ("PASS" if g4a else "FAIL"))
    del atr14_ref, q_ref, sh, sess_ref

    # G4-B
    cb = cmp_at("stretch", "ta_lvl_sma20d_atr", 1e-6)
    g4b = cb["csv_non_nan"] == 1828 and cb["engine_finite_on_those"] == cb["csv_non_nan"] and cb["max_abs_diff"] <= 1e-6 and ident["H-B"]
    say("  G4-B S[i] vs CSV ta_lvl_sma20d_atr: %d non-NaN signal bars (want 1,828), engine finite on %d, max |diff| %.3g "
        "(tol 1e-6), over tol %d | %d CSV-NaN rows (signal on a session's last bar), engine NaN on %d of them"
        % (cb["csv_non_nan"], cb["engine_finite_on_those"], cb["max_abs_diff"], cb["n_over_tol"], cb["csv_nan_rows"],
           cb["engine_nan_where_csv_nan"]))
    RESULTS.append(dict(gate="G4-B", passed=g4b, csv=cb, override_identity=ident["H-B"]))
    say("  -> G4-B %s" % ("PASS" if g4b else "FAIL"))

    # G4-C
    cc_ = cmp_at("rec", "loc_pb_recovery", 1e-9)
    g4c = cc_["csv_non_nan"] == 1831 and cc_["engine_finite_on_those"] == 1831 and cc_["max_abs_diff"] <= 1e-9 and ident["H-C"]
    say("  G4-C rec[i] vs CSV loc_pb_recovery: %d signal bars (want 1,831), engine finite on %d, max |diff| %.3g (tol 1e-9)"
        % (cc_["csv_non_nan"], cc_["engine_finite_on_those"], cc_["max_abs_diff"]))
    RESULTS.append(dict(gate="G4-C", passed=g4c, csv=cc_, override_identity=ident["H-C"]))
    say("  -> G4-C %s" % ("PASS" if g4c else "FAIL"))

    # G4-D
    cd = cmp_at("vol_vs_clock", "imb_vol_vs_clock20", 1e-9)
    g4d = cd["csv_non_nan"] == 1829 and cd["engine_finite_on_those"] == cd["csv_non_nan"] and cd["max_abs_diff"] <= 1e-9 and ident["H-D"]
    say("  G4-D V[i]/B[i] vs CSV imb_vol_vs_clock20: %d non-NaN signal bars (want 1,829), engine finite on %d, max |diff| "
        "%.3g (tol 1e-9) | %d CSV-NaN rows, engine NaN on %d of them"
        % (cd["csv_non_nan"], cd["engine_finite_on_those"], cd["max_abs_diff"], cd["csv_nan_rows"], cd["engine_nan_where_csv_nan"]))
    RESULTS.append(dict(gate="G4-D", passed=g4d, csv=cd, override_identity=ident["H-D"]))
    say("  -> G4-D %s" % ("PASS" if g4d else "FAIL"))
    g4 = g4a and g4b and g4c and g4d and link_ok and in_probe == len(T)
    gate("G4", g4, csv_link_ok=link_ok, csv_signal_bars_in_control_probe=in_probe)
    step(4)

    # ------------------------------------------------------------------ G5
    say("\nG5  execution-feasibility audit")
    tool = os.path.join(HERE, "exec_feasibility_audit.py")
    g5_cfg = True
    for hyp, knob, val in CENTRES:
        pr = subprocess.run([sys.executable, tool, "--config", os.path.basename(SEL), "--params", "%s=%r" % (knob, float(val))],
                            capture_output=True, text=True, cwd=ROOT)
        txt = (pr.stdout or "").strip().replace("\n", " | ")
        ok = pr.returncode == 0
        g5_cfg = g5_cfg and ok
        say("  %s --config %s --params %s=%s: exit %d | %s" % (hyp, os.path.basename(SEL), knob, float(val), pr.returncode, txt))
        RESULTS.append(dict(gate="G5-%s" % hyp, passed=ok, exit_code=pr.returncode, output=txt))
    pf = subprocess.run([sys.executable, tool, SEL], capture_output=True, text=True, cwd=ROOT)
    ftxt = (pf.stdout or "").strip().replace("\n", " | ")
    say("  file-level static scan: exit %d | %s" % (pf.returncode, ftxt))

    # hand audit 1: every interpreted signal bar passes its own mask
    hand1 = {}
    for hyp, knob, val in CENTRES:
        kn = dict(KNOBS_OFF, **{knob: val})
        mask = sel_mod._rule_mask(np.asarray(A["high"], float), np.asarray(A["low"], float), np.asarray(A["close"], float),
                                  A["volume"], idx, tr_eng, int(PS["tl_len"]), kn["quiet_pct"], kn["stretch_max"],
                                  kn["rec_min"], kn["vol_clock"])
        pb = []
        rr = sel_mod.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"], day_id=A["day_id"],
                                  index=A["index"], return_trades=True, _signal_index_probe=pb, **dict(PS, **kn))
        bad = int(sum(1 for i in pb if not mask[i]))
        same = compare_trades(sorted(rr["trades"], key=lambda z: z[0]), CELL_TRADES[hyp], pnl_shift=FR.COST)["identical"]
        # whether the mask rejects ANY knob-off control signal (non-vacuous); the count is a signal-level read and is
        # deliberately not printed at the gate step
        rej = bool(any(not mask[i] for i in sig_probe)) if knob != "vol_clock" else None
        hand1[hyp] = (bad == 0 and same)
        say("  hand audit %s: interpreted signal-index probe - signal bars failing their own mask: %d; probe walk == compiled "
            "cell: %s%s" % (hyp, bad, same, "" if rej is None else "; mask rejects at least one knob-off control signal: %s" % rej))
        RESULTS.append(dict(gate="G5-hand-signal-bar-%s" % hyp, passed=hand1[hyp], signal_bars_failing_mask=bad,
                            probe_walk_equals_compiled=same, control_signals_rejected_by_mask=rej))
        del rr, pb, mask

    # hand audit 2: truncation - nothing after bar k changes a feature at bar k
    cuts = [int(idx.searchsorted(pd.Timestamp(ts, tz=idx.tz))) for ts in ("2016-03-09 11:17", "2023-10-02 03:41")]
    hand2 = True
    for cut in cuts:
        sl = slice(0, cut)
        P_ = sel_mod._rule_features(A["open"][sl], A["high"][sl], A["low"][sl], A["close"][sl], A["volume"][sl],
                                    A["index"][sl], tl_len=int(PS["tl_len"]))
        res = {}
        for k in ("q", "stretch", "rec", "clock_base", "vol_vs_clock"):
            x, y = F[k][:cut], P_[k]
            same_nan = bool(np.array_equal(np.isnan(x), np.isnan(y)))
            f_ = np.isfinite(x)
            same_val = bool(np.array_equal(x[f_], y[f_]))
            res[k] = same_nan and same_val
        hand2 = hand2 and all(res.values())
        say("  hand audit truncation at bar %d (%s): features on the prefix == full-frame features on the prefix: %s"
            % (cut, idx[cut - 1], res))
        RESULTS.append(dict(gate="G5-hand-truncation-%d" % cut, passed=all(res.values()), last_bar=str(idx[cut - 1]),
                            per_feature=res))
        del P_
    g5 = g5_cfg and pf.returncode == 0 and all(hand1.values()) and hand2
    gate("G5", g5, config_mode_all_exit0=g5_cfg, file_scan_exit=pf.returncode, file_scan_output=ftxt,
         hand_signal_bar_ok=all(hand1.values()), hand_truncation_ok=hand2)
    step(5)

    all_ok = g1 and g2 and g3_all and g4 and g5
    say("\n" + "=" * 118)
    say("ITEM 1 PARITY GATES: %s   (G1 %s, G2 %s, G3 %s, G4 %s, G5 %s)   runtime %.0fs"
        % ("ALL PASS" if all_ok else "NOT ALL PASS", g1, g2, g3_all, g4, g5, time.time() - t_all))
    return all_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beacon", action="store_true")
    a = ap.parse_args()
    if a.beacon:
        from research_beacon import beacon
        with beacon("r57 ENGU-Q SEL parity gates G1-G5", total=5) as b:
            ok = run(lambda i: b.step(i))
    else:
        ok = run(lambda i: None)

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, np.integer, np.bool_)):
            return clean(o.item())
        if isinstance(o, float) and not math.isfinite(o):
            return None
        return o

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT) + "\n")
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(clean(dict(all_pass=ok, results=RESULTS)), fh, indent=1)
    print("wrote", OUT_TXT, OUT_JSON)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""ENGU-Q ROUND 57 -- ORDER OF WORK ITEMS 2 AND 3: THE R2-SETTINGS GRID, THEN THE SELECTION CLAUSES.

Contract: ENGUQ_R57_PREREG.md (a7f0811), sections 2-5 and 7. Parity gates G1-G5 passed first
(tools/r57_sel_parity_gates.py).

ITEM 2  Run the knob-off control plus the 12 grid cells (4 hypotheses x 3 non-off values) at R2
        settings on ENGUQ_1M_ETH_SEL_1_0.py: one continuous engine backtest each, every parameter
        explicit, cost 0.533, $20/pt. The moment the engine returns, trades entered on/after
        2025-06-30 00:00 ET (the LB) are DISCARDED unread (not counted, not printed, not passed on);
        only selection trades reach measure(). Every cell's full measure() row is printed and
        flushed to tools/r37_results/r57_grid.txt BEFORE any clause is applied.
ITEM 3  A0 look-ahead alarm on the four centre cells first (a trip runs the section-4 audit and
        STOPS unless --a0-audited is given), then S1-S9 and each hypothesis's section-5 extra
        clauses and kill criteria, clause by clause with measured value and threshold. S10-S12 are
        the next step and are NOT run here.

READINGS FIXED IN THIS FILE BEFORE ANY CELL RAN (recorded in prereg section 11):
  a. LB discard: measure() receives SELECTION trades only, so its 'lb' block is empty and its
     'whole' / 'corr_all' / 'hold_all' fields equal the selection read. Section 3's "whole-window
     numbers (reported)" conflicts with section 2's "LB trades are discarded ... not printed, until
     section 8"; the stricter rule wins and no whole-window number is produced. bench_all is passed
     as the selection benchmark so not even LB-year prices are read. The control's selection fields
     must still equal frontier row 1 exactly (a hard stop), proving the slice changes nothing.
  b. Thresholds are computed from the control's exact values (S1 = control win + 1.0 pt, S4 =
     0.95 x control MAR, S5a = control era share + 2.0 pts, ...); the prereg table's rounded figures
     (30.4%, 0.86, 64.1% ...) are displays of those.
  c. Four eras by entry time: A < 2014-01-01, B < 2018-01-01, C < 2022-01-01, D < 2025-06-30.
     PF and win per era on $ after cost (win = net > 0).
  d. Top-20 / top-10 retention: control's best selection trades by $ (stable sort); a variant
     SELECTION trade whose entry bar lies in [control entry bar, control exit bar].
  e. Trade-set audit: "identical" = same entry bar, exit bar and entry price; "removed" = control
     selection trade with no identical variant trade; "added" / slot refill = variant selection
     trade with no control selection trade whose ENTRY bar lies inside the variant trade's
     [entry bar, exit bar] span (the mirror of the S8 span test); "re-timed" = the rest.
  f. Gating set per hypothesis = S1-S8 at the centre (S8 min 18 for H-A), S9 on both neighbours,
     every section-5 "extra clause" that states a condition, and every section-5 kill criterion
     that can be evaluated before S10-S12. Explicitly: H-C's "reported mechanism check: the
     gap-through fill share ... must not rise" is GATING (it says must; unlike H-A's diagnostic it
     is not labelled "not a gate"); H-D's +/-40% trade-count clause is GATING. H-A's planned-risk
     floor and session-bucket shares are REPORTED ONLY (labelled so in the prereg). Neighbour cells
     are shown against S1-S8 for the record only; they veto only through S9 (and, for H-D, the
     three-cell PF-lift sign agreement).
  g. Gap-through fill (H-C) = the anatomy's definition: entry price < resting limit - 1e-9, read
     from the interpreted walk's own locals (fill probe), which must equal the compiled trades.
  h. H-D 09:30-09:35 exclusion: entry bar ET clock time 09:30 <= hh:mm <= 09:35 (inclusive),
     removed from both variant and control selection trades before PF.
  i. H-A planned-risk diagnostic: risk% = (limit - swing_low) / limit at every bar, limit =
     c - 0.55 x the file's ATR52 (NaN -> TR, as the walk), swing_low = min(l[i-206..i]); the floor
     is the value that removes round(share x N) of the control's selection SIGNALS (signal-index
     probe bars < split), share = the H-A centre mask's rejection share on those same signals; the
     run uses quiet_pct=20 with _mask_override = the risk-floor mask. Reported, never gating.
  j. H-A session buckets by the signal bar's ET clock: Asia 18:00-03:00, Europe 03:00-09:30,
     cash 09:30-16:00, other 16:00-18:00.

Run from the SHARED checkout (master registry):
    cd C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG
    python C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\enguq57\\tools\\r57_grid.py [--beacon] [--a0-audited]
One process, no pool (13 compiled cells + 3 interpreted probe walks + 1 diagnostic cell).
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
FRONTIER_JSON = os.path.join(HERE, "r37_results", "r57_frontier.json")
OUT_TXT = os.path.join(HERE, "r37_results", "r57_grid.txt")
OUT_JSON = os.path.join(HERE, "r37_results", "r57_grid.json")
CACHE_DIR = r"C:\EdgeLog\_anatomy_cache\r57"
TRADES_CACHE = os.path.join(CACHE_DIR, "r57_grid_selection_trades.json")


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FR = _load_by_path("r57_frontier_harness", os.path.join(HERE, "r57_enguq_frontier.py"))
os.chdir(ROOT)

from augur_engine import fastloop                                       # noqa: E402
from augur_engine.data import find_master, load_master_arrays           # noqa: E402
from augur_engine.engine import run_backtest                            # noqa: E402
from augur_engine.strategies import load_strategy                       # noqa: E402
from queue_guard import resolve_params                                  # noqa: E402

KNOBS_OFF = dict(quiet_pct=0.0, stretch_max=0.0, rec_min=0.0, vol_clock=0.0)
HYP = {
    "H-A": dict(name="quiet-tape stand-down", knob="quiet_pct", grid=[10.0, 20.0, 30.0], centre=20.0,
                nbrs=[10.0, 30.0], scan=dict(win=1.1, pf=0.05, net=14900.0), s8_min=18),
    "H-B": dict(name="daily stretch cap", knob="stretch_max", grid=[2.0, 1.5, 1.0], centre=1.5,
                nbrs=[2.0, 1.0], scan=dict(win=1.0, pf=0.15, net=-17600.0), s8_min=17),
    "H-C": dict(name="leg recovery floor", knob="rec_min", grid=[0.35, 0.45, 0.55], centre=0.45,
                nbrs=[0.35, 0.55], scan=dict(win=1.5, pf=0.08, net=-16900.0), s8_min=17),
    "H-D": dict(name="clock-unit volume test", knob="vol_clock", grid=[1.0, 1.25, 1.5], centre=1.25,
                nbrs=[1.0, 1.5], scan=None, s8_min=17),
}
ERAS4 = [("A", None, "2014-01-01"), ("B", "2014-01-01", "2018-01-01"), ("C", "2018-01-01", "2022-01-01"),
         ("D", "2022-01-01", None)]

OUT = []
_FH = None


def say(s=""):
    print(s, flush=True)
    OUT.append(s)
    if _FH is not None:
        _FH.write(s + "\n")
        _FH.flush()


def cell_id(hyp, val=None):
    return "CTRL" if hyp is None else "%s %s=%g" % (hyp, HYP[hyp]["knob"], val)


class _FillProbe(list):
    """The walk calls _fill_probe.append(signal_close - fill) once per limit touch; read the walk's
    own locals instead (tools/r57_enguq_anatomy.py convention)."""
    def append(self, v):
        loc = sys._getframe(1).f_locals
        list.append(self, (int(loc["i"]), int(loc["fill_j"]), float(loc["fill_price"]), float(loc["limit"])))


def fnum(v):
    """A comparable number: not None and not NaN (an infinite PF - no losing trade - still compares)."""
    return v is not None and not (isinstance(v, (float, np.floating)) and math.isnan(float(v)))


def sg0(v):
    return ("+" if v >= 0 else "-") + FR.f0(abs(v))


def pf_of(usd):
    usd = np.asarray(usd, float)
    if len(usd) == 0:
        return float("nan")
    gw = float(usd[usd > 0].sum())
    gl = float(-usd[usd < 0].sum())
    return gw / gl if gl > 0 else (float("inf") if gw > 0 else float("nan"))


def win_of(usd):
    usd = np.asarray(usd, float)
    return 100.0 * float((usd > 0).mean()) if len(usd) else float("nan")


def tarr(sel, idx):
    e = np.array([int(t[0]) for t in sel], np.int64)
    return dict(e=e, x=np.array([int(t[1]) for t in sel], np.int64),
                usd=np.array([float(t[2]) for t in sel]) * FR.MULT,
                px=np.array([float(t[4]) for t in sel]), ent=pd.DatetimeIndex(idx[e]))


def block(T, mask):
    u = T["usd"][mask]
    return dict(n=int(mask.sum()), win=win_of(u), pf=pf_of(u), net=float(u.sum()))


def retention(C, V, k):
    order = np.argsort(-C["usd"], kind="stable")[:k]
    ve = np.sort(V["e"])
    kept, missing = 0, []
    for j in order:
        a, b = int(C["e"][j]), int(C["x"][j])
        p = int(np.searchsorted(ve, a, side="left"))
        if p < len(ve) and ve[p] <= b:
            kept += 1
        else:
            missing.append(dict(entry=str(C["ent"][j]), usd=round(float(C["usd"][j]), 2)))
    return kept, missing


def trade_sets(C, V):
    ck = set(zip(C["e"].tolist(), C["x"].tolist(), np.round(C["px"], 6).tolist()))
    vk = set(zip(V["e"].tolist(), V["x"].tolist(), np.round(V["px"], 6).tolist()))
    ident_v = np.array([k in ck for k in zip(V["e"].tolist(), V["x"].tolist(), np.round(V["px"], 6).tolist())], bool)
    removed_c = np.array([k not in vk for k in zip(C["e"].tolist(), C["x"].tolist(), np.round(C["px"], 6).tolist())], bool)
    ce = np.sort(C["e"])
    p = np.searchsorted(ce, V["e"], side="left")
    pc = np.minimum(p, len(ce) - 1)
    has_ctrl_entry = (p < len(ce)) & (ce[pc] <= V["x"])
    added_v = ~has_ctrl_entry
    retimed_v = ~ident_v & ~added_v
    return ident_v, removed_c, added_v, retimed_v


def clock_excl(T):
    hm = np.asarray(T["ent"].hour, np.int64) * 60 + np.asarray(T["ent"].minute, np.int64)
    return (hm >= 570) & (hm <= 575)


def match_frontier(M, row):
    """Every selection-side measure() field vs the frontier JSON row (tools/r57_sel_parity_gates.py)."""
    s = M["sel"]
    fields = {"sel.n": s["n"], "sel.wr": s["wr"], "sel.pf": s["pf"], "sel.net": s["net"], "sel.dd": s["dd"],
              "sel.mar": s["mar"], "sel.evr": s["evr"], "sel_ex10_net": M["sel_ex10_net"], "top10": M["top10"],
              "era1.n": M["era1"]["n"], "era1.net": M["era1"]["net"], "era1.top10": M["era1"]["top10"],
              "era1.ex10": M["era1"]["ex10"], "era2.n": M["era2"]["n"], "era2.net": M["era2"]["net"],
              "era2.top10": M["era2"]["top10"], "era2.ex10": M["era2"]["ex10"], "ttz": M["ttz"],
              "evr_ex05": M["evr_ex05"], "corr_sel": M["corr_sel"], "y2018": M["y2018"], "y2022": M["y2022"],
              "hold_sel": M["hold_sel"], "med_w": M["med_w"], "med_l": M["med_l"], "wr_ex_scratch": M["wr_ex_scratch"]}
    bad = []
    for k, v in fields.items():
        a, b = k.split(".") if "." in k else (k, None)
        ref = row[a][b] if b else row[a]
        if ref is None or v is None or abs(float(v) - float(ref)) > 1e-6 * max(1.0, abs(float(ref))):
            bad.append((k, v, ref))
    ys = {int(k): v for k, v in row["yearly_sel"].items()}
    for y, v in M["yearly_sel"].items():
        if abs(v - ys.get(int(y), float("nan"))) > 1e-6:
            bad.append(("yearly_sel.%d" % y, v, ys.get(int(y))))
    return bad


def clause(cid, desc, value, op, thr, gating=True, fmt="%.4f", note=None):
    if op == ">=":
        ok = fnum(value) and fnum(thr) and value >= thr
    elif op == ">":
        ok = fnum(value) and fnum(thr) and value > thr
    elif op == "<=":
        ok = fnum(value) and fnum(thr) and value <= thr
    elif op == "<":
        ok = fnum(value) and fnum(thr) and value < thr
    elif op == "==":
        ok = value == thr
    elif op == "bool":
        ok = bool(value)
    else:
        raise ValueError(op)
    return dict(clause=cid, desc=desc, value=value, op=op, threshold=thr, passed=bool(ok), gating=gating, fmt=fmt,
                note=note)


def show_clause(c, indent="    "):
    def f(v):
        if isinstance(v, bool) or v is None:
            return str(v)
        if isinstance(v, (int, np.integer)):
            return format(int(v), ",")
        if isinstance(v, float) and not math.isfinite(v):
            return str(v)
        if isinstance(v, (float, np.floating)):
            return c["fmt"] % v
        return str(v)
    thr = "" if c["op"] == "bool" else "%s %s" % (c["op"], f(c["threshold"]))
    say("%s%-8s %-78s %14s %18s  %s%s%s" % (indent, c["clause"], c["desc"][:78], f(c["value"]), thr,
                                         "PASS" if c["passed"] else "FAIL", "" if c["gating"] else "  (reported, not gating)",
                                         ("  [%s]" % c["note"]) if c.get("note") else ""))


def run(step, a0_audited):
    t_all = time.time()
    say("=" * 150)
    say("ENGU-Q ROUND 57 -- ORDER OF WORK ITEMS 2-3: R2-SETTINGS GRID (control + 12 cells), THEN A0 AND S1-S9 + SECTION-5 "
        "EXTRAS   (run %s)" % time.strftime("%Y-%m-%d %H:%M"))
    say("contract ENGUQ_R57_PREREG.md a7f0811 | file %s | tape NQ 1m ETH db_noadj_eth | window %s..%s pinned | cost %.3f "
        "pts/RT x $%d | one continuous engine backtest per cell" % (os.path.basename(SEL), FR.WIN[0], FR.WIN[1], FR.COST,
                                                                    FR.MULT))
    say("SELECTION = entries before %s 00:00 ET. LB trades are dropped the moment the engine returns: never counted, "
        "printed or passed to measure(). S10-S12 are NOT run here." % FR.SPLIT)
    say("numba %s | AUGUR_TRIAL_CACHE=%s OMP_NUM_THREADS=%s | engine calls with return_trades=True bypass the trial cache"
        % (fastloop.HAVE_NUMBA, os.environ.get("AUGUR_TRIAL_CACHE"), os.environ.get("OMP_NUM_THREADS")))
    say("=" * 150)

    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    A = load_master_arrays(m, date_from=FR.WIN[0], date_to=FR.WIN[1])
    idx = pd.DatetimeIndex(A["index"])
    nbar = len(idx)
    split_ts = pd.Timestamp(FR.SPLIT, tz=idx.tz)
    n_split = int(idx.searchsorted(split_ts))
    say("master %s id %s: %d bars %s .. %s | first bar at/after the split: %d" % (m.get("filename"), m.get("id"), nbar,
                                                                                 idx[0], idx[-1], n_split))
    bench_sel = FR.year_bench(idx.tz_localize(None), A["close"], upto=pd.Timestamp(FR.SPLIT))
    frontier = {r["num"]: r for r in json.load(open(FRONTIER_JSON, encoding="utf-8"))["rows"]}
    sel_mod = load_strategy(SEL)

    P2, _s, _h = resolve_params(R2, {})
    PS, _s, _h = resolve_params(SEL, {})
    base_ok = (all(PS[k] == v for k, v in P2.items()) and all(PS[k] == 0 for k in KNOBS_OFF) and PS["max_hold_bars"] == 0)
    say("R2 settings, every parameter explicit: %s   (== R2 DEFAULT_PARAMS, knobs 0, max_hold_bars 0: %s)"
        % (json.dumps(PS, sort_keys=True), base_ok))
    if not base_ok:
        raise SystemExit("base params differ from the R2 defaults -- stopping")

    cells = [(None, None)] + [(h, v) for h in HYP for v in HYP[h]["grid"]]
    SELT, M, T, PARAMS = {}, {}, {}, {}
    k_step = 0

    # ================================================================== ITEM 2: run every cell
    say("\n" + "=" * 150)
    say("ITEM 2 -- RUNS")
    for hyp, val in cells:
        cid = cell_id(hyp, val)
        P = dict(PS) if hyp is None else dict(PS, **{HYP[hyp]["knob"]: float(val)})
        t = time.time()
        r = run_backtest(SEL, arrays=A, params=dict(P), cost_pts=FR.COST, return_trades=True)
        sel = [tuple(z) for z in sorted((r or {}).get("trades") or [], key=lambda z: z[0]) if int(z[0]) < n_split]
        del r                                            # LB trades discarded unread
        SELT[cid] = sel
        PARAMS[cid] = P
        M[cid] = FR.measure(sel, A, FR.MULT, bench_sel, bench_sel)
        T[cid] = tarr(sel, idx)
        say("  ran %-26s %.1fs (fastloop enabled %s)" % (cid, time.time() - t, fastloop.enabled()))
        k_step += 1
        step(k_step)

    bad = match_frontier(M["CTRL"], frontier[1])
    say("\n  CONTROL CHECK: selection-only measure() of the knob-off control == frontier row 1 on every selection field: %s%s"
        % (not bad, "" if not bad else "  MISMATCH %s" % bad[:8]))
    if bad:
        raise SystemExit("control does not reproduce frontier row 1 -- stopping before any row is read")

    # ------------------------------------------------------------------ full measure() rows
    say("\n" + "=" * 150)
    say("ITEM 2 -- EVERY CELL'S FULL measure() ROW (selection stretch; printed before any clause is applied)")
    say("  measure() was given selection trades only: its 'lb' block is empty by construction and 'whole' / corr_all / "
        "hold_all repeat the selection read, so they are not printed.")
    order = ["CTRL"] + [cell_id(h, v) for h in HYP for v in HYP[h]["grid"]]
    say("\nPANEL 1 -- MONEY")
    say("  %-26s | %5s %6s %6s %10s %9s %6s %6s %6s | %s" % ("cell", "n", "win%", "PF", "net $", "maxDD $", "MAR", "EV R",
                                                             "R/YR", "first entry .. last entry"))
    for cid in order:
        s = M[cid]["sel"]
        say("  %-26s | %5d %6.2f %6.4f %10s %9s %6.3f %6.4f %6.1f | %s .. %s"
            % (cid, s["n"], s["wr"], s["pf"], FR.f0(s["net"]), FR.f0(s["dd"]), s["mar"], s["evr"], s["ryr"],
               M[cid]["first_entry"], M[cid]["last_entry"]))
    say("\nPANEL 2 -- TAIL (E1 = entries 2010-06-07..2019-12-31, E2 = 2020-01-01..2025-06-29; top-10 share = era's 10 best "
        "/ era net)")
    say("  %-26s | %6s %9s | %5s %9s %6s %6s %9s | %5s %9s %6s %6s %9s | %4s %5s | %7s %3s | %6s %5s"
        % ("cell", "top10", "ex10 $", "E1 n", "E1 net", "E1 PF", "E1t10", "E1 ex10", "E2 n", "E2 net", "E2 PF", "E2t10",
           "E2 ex10", "TTZ", "TTZ%", "EVRx.5%", "k", "corr", "+yrs"))
    for cid in order:
        X = M[cid]
        e1, e2 = X["era1"], X["era2"]
        say("  %-26s | %5.2f%% %9s | %5d %9s %6s %6s %9s | %5d %9s %6s %6s %9s | %4d %5.2f | %7s %3d | %+6.3f %2d/%-2d"
            % (cid, X["top10"], FR.f0(X["sel_ex10_net"]), e1["n"], FR.f0(e1["net"]), FR.fx(e1["pf"], "%.4f"),
               FR.fx(e1["top10"], "%.2f"), FR.f0(e1["ex10"]), e2["n"], FR.f0(e2["net"]), FR.fx(e2["pf"], "%.4f"),
               FR.fx(e2["top10"], "%.2f"), FR.f0(e2["ex10"]), X["ttz"], X["ttz_pct"], FR.fx(X["evr_ex05"], "%.4f"),
               X["k05"], X["corr_sel"], X["pos_years"], X["n_years"]))
    say("\nPANEL 3 -- SHAPE (reported, never gating)")
    say("  %-26s | %9s %9s | %8s | %7s %7s %6s %6s | %6s %7s" % ("cell", "2018 $", "2022 $", "hold d", "med W $",
                                                                 "med L $", "W/L", "BE W/L", "scr%", "win%xs"))
    for cid in order:
        X = M[cid]
        say("  %-26s | %9s %9s | %8d | %7s %7s %6.3f %6.3f | %5.2f%% %6.2f%%"
            % (cid, FR.f0(X["y2018"]), FR.f0(X["y2022"]), X["hold_sel"], FR.f0(X["med_w"]), FR.f0(X["med_l"]),
               X["wl_ratio"], X["be_ratio"], X["scratch_pct"], X["wr_ex_scratch"]))
    years = sorted(set(y for cid in order for y in M[cid]["yearly_sel"]))
    say("\nYEARLY SELECTION NET $ by entry year (2010 = Jun-Dec, 2025 = Jan-Jun 29); corr uses NQ yearly return 2011..2025-H1")
    say("  %-26s " % "cell" + " ".join("%8d" % y for y in years))
    say("  %-26s " % "NQ yearly %" + " ".join(("%+7.1f%%" % bench_sel[y]) if y in bench_sel.index else "       -"
                                             for y in years))
    for cid in order:
        say("  %-26s " % cid + " ".join("%8s" % FR.f0(M[cid]["yearly_sel"].get(y, 0.0)) for y in years))
    say("\nRAW measure() DICT PER CELL (selection; lb / whole / corr_all / ny_all / hold_all omitted as above)")
    for cid in order:
        d = {k: v for k, v in M[cid].items() if k not in ("lb", "whole", "corr_all", "ny_all", "hold_all")}
        say("  %s: %s" % (cid, json.dumps(clean(d), sort_keys=True)))

    # ------------------------------------------------------------------ clause inputs (descriptive)
    say("\n" + "=" * 150)
    say("ITEM 2 -- PER-CELL CLAUSE INPUTS (descriptive; nothing is compared to a threshold yet)")
    C = T["CTRL"]
    X4 = {}
    for cid in order:
        V = T[cid]
        eras = {}
        for nm, lo, hi in ERAS4:
            mk = np.ones(len(V["usd"]), bool)
            if lo:
                mk &= np.asarray(V["ent"] >= pd.Timestamp(lo, tz=idx.tz))
            if hi:
                mk &= np.asarray(V["ent"] < pd.Timestamp(hi, tz=idx.tz))
            eras[nm] = block(V, mk)
        e2m = np.asarray(V["ent"] >= pd.Timestamp(FR.ERA_SPLIT, tz=idx.tz))
        r20, miss20 = retention(C, V, 20)
        r10, miss10 = retention(C, V, 10)
        ident, removed, added, retimed = trade_sets(C, V)
        ex = clock_excl(V)
        X4[cid] = dict(eras4=eras, e1=block(V, ~e2m), e2=block(V, e2m), top20_retained=r20, top20_missing=miss20,
                       top10_retained=r10, top10_missing=miss10, identical=int(ident.sum()), removed=int(removed.sum()),
                       added=int(added.sum()), added_win=win_of(V["usd"][added]), retimed=int(retimed.sum()),
                       excl0930_n=int(ex.sum()), pf_ex0930=pf_of(V["usd"][~ex]))
    top20 = np.argsort(-C["usd"], kind="stable")[:20]
    span_cross = int(np.sum(C["x"][top20] >= n_split))
    say("  control top-20 $ trades whose exit bar is at/after the split (span reaches the LB; variant LB entries are not "
        "read): %d" % span_cross)
    say("  %-26s | %s | %6s %6s | %4s %4s | %5s %5s %5s %5s %6s | %5s %7s" %
        ("cell", "era A n/win/PF/net | B | C | D".ljust(104), "E1 win", "E2 win", "t20", "t10", "ident", "remov", "added",
         "retim", "add w%", "n0930", "PFx0930"))
    for cid in order:
        Z = X4[cid]
        es = " | ".join("%4d %5.2f %6.4f %8s" % (Z["eras4"][k]["n"], Z["eras4"][k]["win"], Z["eras4"][k]["pf"],
                                                 FR.f0(Z["eras4"][k]["net"])) for k in "ABCD")
        say("  %-26s | %s | %6.2f %6.2f | %4d %4d | %5d %5d %5d %5d %6s | %5d %7.4f"
            % (cid, es.ljust(104), Z["e1"]["win"], Z["e2"]["win"], Z["top20_retained"], Z["top10_retained"],
               Z["identical"], Z["removed"], Z["added"], Z["retimed"], FR.fx(Z["added_win"], "%.2f"), Z["excl0930_n"],
               Z["pf_ex0930"]))
    say("  t20 / t10 = control's best 20 / 10 selection trades with a variant entry inside their span; ident / remov / "
        "added / retim = trade-set audit vs control (reading e); n0930 = entries 09:30-09:35 ET; PFx0930 = PF without them")

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(TRADES_CACHE, "w", encoding="utf-8") as fh:
            json.dump(dict(note="r57 grid, SELECTION trades only (entry bar, exit bar, pts after cost, qty, entry px)",
                           cells={k: [list(t) for t in v] for k, v in SELT.items()}), fh)
        say("  selection trade lists cached to %s" % TRADES_CACHE)
    except Exception as exc:                                         # pragma: no cover
        say("  (trade cache not written: %s)" % exc)

    # ================================================================== ITEM 3a: A0
    say("\n" + "=" * 150)
    say("ITEM 3 -- A0 LOOK-AHEAD ALARM on the four centre cells (trips on win lift > +3.0 pts, PF lift > +0.30, or net > "
        "110% of control)")
    S0 = M["CTRL"]["sel"]
    A0 = {}
    tripped = []
    for h in HYP:
        cid = cell_id(h, HYP[h]["centre"])
        s = M[cid]["sel"]
        wl, pl, nr = s["wr"] - S0["wr"], s["pf"] - S0["pf"], s["net"] / S0["net"]
        trip = wl > 3.0 or pl > 0.30 or nr > 1.10
        A0[h] = dict(cell=cid, win_lift=wl, pf_lift=pl, net_ratio=nr, tripped=trip)
        say("  %s %-24s win lift %+.3f pts (alarm > +3.0) | PF lift %+.4f (alarm > +0.30) | net %.2f%% of control "
            "(alarm > 110%%) -> %s" % (h, cid, wl, pl, 100 * nr, "*** TRIPPED ***" if trip else "clear"))
        if trip:
            tripped.append(h)
    if tripped:
        say("\n  A0 TRIPPED on %s -- running the section-4 audit before anything else is read" % tripped)
        a0_audit(tripped, A, idx, PS, sel_mod, SELT)
        if not a0_audited:
            say("\n  STOP (A0). Re-run with --a0-audited after reviewing the audit to continue to S1-S9.")
            return dict(status="A0_STOP", A0=A0, rows=M, inputs=X4)

    # ================================================================== ITEM 3b: S1-S9 + extras
    say("\n" + "=" * 150)
    say("ITEM 3 -- S1-S9 AND SECTION-5 EXTRAS (centre vs the knob-off control; neighbours veto through S9 only)")
    ctl, cx = M["CTRL"], X4["CTRL"]
    thr = dict(S1=S0["wr"] + 1.0, S2=S0["pf"] + 0.02, S3=0.95 * S0["net"], S4=0.95 * S0["mar"],
               S5a1=ctl["era1"]["top10"] + 2.0, S5a2=ctl["era2"]["top10"] + 2.0, S5c=ctl["ttz"] - 2,
               S5d=ctl["evr_ex05"], S7=ctl["corr_sel"] + 0.05, S9win=0.5, S9pf=S0["pf"] + 0.01, S9net=0.90 * S0["net"])
    say("  control: n %d | win %.4f%% | PF %.6f | net $%.2f | MAR %.6f | E1/E2 top-10 %.4f%% / %.4f%% | TTZ %d | EVRx.5%% "
        "%.6f | corr %+.6f | eraD net $%.2f | E1/E2 win %.4f / %.4f | E2 PF %.6f"
        % (S0["n"], S0["wr"], S0["pf"], S0["net"], S0["mar"], ctl["era1"]["top10"], ctl["era2"]["top10"], ctl["ttz"],
           ctl["evr_ex05"], ctl["corr_sel"], cx["eras4"]["D"]["net"], cx["e1"]["win"], cx["e2"]["win"], ctl["era2"]["pf"]))

    def s1_s8(cid, s8_min):
        X, Z, s = M[cid], X4[cid], M[cid]["sel"]
        out = [clause("S1", "win rate >= control + 1.0 pt", s["wr"], ">=", thr["S1"], fmt="%.4f"),
               clause("S2", "PF >= control + 0.02", s["pf"], ">=", thr["S2"], fmt="%.5f"),
               clause("S3", "net >= 95% of control ($)", s["net"], ">=", thr["S3"], fmt="%.2f"),
               clause("S4", "MAR >= 0.95 x control MAR (guard)", s["mar"], ">=", thr["S4"], fmt="%.5f"),
               clause("S5a-E1", "E1 top-10 share <= control + 2 pts (%)", X["era1"]["top10"], "<=", thr["S5a1"], fmt="%.4f"),
               clause("S5a-E2", "E2 top-10 share <= control + 2 pts (%)", X["era2"]["top10"], "<=", thr["S5a2"], fmt="%.4f"),
               clause("S5b-E1", "E1 ex-top-10 net > $0", X["era1"]["ex10"], ">", 0.0, fmt="%.2f"),
               clause("S5b-E2", "E2 ex-top-10 net > $0", X["era2"]["ex10"], ">", 0.0, fmt="%.2f"),
               clause("S5c", "trades-to-zero >= control - 2", X["ttz"], ">=", thr["S5c"]),
               clause("S5d", "proportional-tail EV R (evr_ex05) >= control's", X["evr_ex05"], ">=", thr["S5d"], fmt="%.6f")]
        lifts = {k: Z["eras4"][k]["pf"] - cx["eras4"][k]["pf"] for k in "ABCD"}
        npos = sum(1 for v in lifts.values() if v > 0)
        out.append(clause("S6a", "PF lift > 0 in >= 3 of eras A-D (count; lifts %s)"
                          % " ".join("%s%+.3f" % (k, v) for k, v in lifts.items()), npos, ">=", 3))
        out.append(clause("S6b", "E2 PF lift > 0", X["era2"]["pf"] - ctl["era2"]["pf"], ">", 0.0, fmt="%+.5f"))
        out.append(clause("S6c", "E1 win lift > 0 (pts)", Z["e1"]["win"] - cx["e1"]["win"], ">", 0.0, fmt="%+.4f"))
        out.append(clause("S6d", "E2 win lift > 0 (pts)", Z["e2"]["win"] - cx["e2"]["win"], ">", 0.0, fmt="%+.4f"))
        out.append(clause("S7a", "index corr <= control + 0.05", X["corr_sel"], "<=", thr["S7"], fmt="%+.5f"))
        out.append(clause("S7b", "2018 selection P&L >= $0", X["y2018"], ">=", 0.0, fmt="%.2f"))
        out.append(clause("S7c", "2022 selection P&L >= $0", X["y2022"], ">=", 0.0, fmt="%.2f"))
        out.append(clause("S8", "control top-20 $ trades retained (of 20)", Z["top20_retained"], ">=", s8_min))
        return out

    def s9(cid):
        s, X = M[cid]["sel"], M[cid]
        return [clause("S9-win", "%s: win lift >= +0.5 pt" % cid, s["wr"] - S0["wr"], ">=", thr["S9win"], fmt="%+.4f"),
                clause("S9-pf", "%s: PF >= control + 0.01" % cid, s["pf"], ">=", thr["S9pf"], fmt="%.5f"),
                clause("S9-net", "%s: net >= 90%% of control ($)" % cid, s["net"], ">=", thr["S9net"], fmt="%.2f"),
                clause("S9-E2pf", "%s: E2 PF lift >= 0" % cid, X["era2"]["pf"] - ctl["era2"]["pf"], ">=", 0.0, fmt="%+.5f")]

    # interpreted probe walks: control (signals + fills) and H-C centre (fills), each == compiled
    say("\n  interpreted probe walks (research instrumentation; each must equal its compiled trade list)")
    probe = {}
    for cid in ("CTRL", cell_id("H-C", HYP["H-C"]["centre"])):
        sp, fp = [], _FillProbe()
        t = time.time()
        rr = sel_mod.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"], day_id=A["day_id"],
                                  index=A["index"], return_trades=True, _signal_index_probe=sp, _fill_probe=fp,
                                  **PARAMS[cid])
        tr_i = [t_ for t_ in sorted(rr["trades"], key=lambda z: z[0]) if int(t_[0]) < n_split]
        del rr
        comp = SELT[cid]
        same = (len(tr_i) == len(comp) and all(int(a[0]) == int(b[0]) and int(a[1]) == int(b[1])
                                               and abs(float(a[4]) - float(b[4])) < 1e-9
                                               and abs(float(a[2]) - FR.COST - float(b[2])) < 1e-9
                                               for a, b in zip(tr_i, comp)))
        fills = [f for f in fp if f[1] < n_split]
        fj = np.array([f[1] for f in fills], np.int64)
        mono = bool(np.all(np.diff(fj) > 0))
        fmap = {f[1]: f for f in fills}
        lim = np.array([fmap[int(t_[0])][3] for t_ in comp])
        sigb = np.array([fmap[int(t_[0])][0] for t_ in comp], np.int64)
        gap = np.array([float(t_[4]) < lim[q] - 1e-9 for q, t_ in enumerate(comp)], bool)
        probe[cid] = dict(signals=np.array([i for i in sp if i < n_split], np.int64), gap=gap, trade_signal_bars=sigb,
                          same=same, mono=mono)
        say("    %-26s %.0fs | interpreted selection trades == compiled: %s | fill bars strictly increasing: %s | "
            "selection signals %d | gap-through fills %d of %d (%.3f%%)"
            % (cid, time.time() - t, same, mono, len(probe[cid]["signals"]), int(gap.sum()), len(gap),
               100.0 * gap.mean()))
        if not (same and mono):
            raise SystemExit("probe walk != compiled walk -- stopping")
    k_step += 1
    step(k_step)

    RES = {}
    survivors = []
    for h in HYP:
        H = HYP[h]
        cid = cell_id(h, H["centre"])
        X, Z, s = M[cid], X4[cid], M[cid]["sel"]
        say("\n" + "-" * 150)
        say("%s %s -- centre %s (neighbours %s)" % (h, H["name"].upper(), cid, ", ".join(cell_id(h, v) for v in H["nbrs"])))
        cen = s1_s8(cid, H["s8_min"])
        if h == "H-A":
            cen[-1]["desc"] = "control top-20 $ trades retained (of 20; H-A tightened to >= 18)"
        say("  SHARED BAR, centre:")
        for c in cen:
            show_clause(c)
        nb = []
        say("  S9 PLATEAU, both neighbours:")
        for v in H["nbrs"]:
            for c in s9(cell_id(h, v)):
                nb.append(c)
                show_clause(c)
        ext, kill, diag = [], [], {}
        wl = s["wr"] - S0["wr"]
        pl = s["pf"] - S0["pf"]
        eraD_ratio = Z["eras4"]["D"]["net"] / cx["eras4"]["D"]["net"]
        if h == "H-A":
            kill.append(clause("K-win", "kill: in-engine win lift >= +0.55 pt (half the scan's +1.1)", wl, ">=", 0.55,
                               fmt="%+.4f"))
            kill.append(clause("K-top10", "kill: control top-10 $ trades each keep an in-span variant entry (of 10)",
                               Z["top10_retained"], ">=", 10, note="missing: %s" % Z["top10_missing"]))
            diag = ha_diagnostics(A, idx, PS, sel_mod, probe["CTRL"], SELT, n_split, bench_sel, M, X4, T, cid)
        elif h == "H-B":
            ext.append(clause("X-eraD", "extra: era D net >= 90% of control's era D net (ratio)", eraD_ratio, ">=", 0.90,
                              fmt="%.5f", note="variant $%s vs control $%s" % (FR.f0(Z["eras4"]["D"]["net"]),
                                                                             FR.f0(cx["eras4"]["D"]["net"]))))
            wC = Z["eras4"]["C"]["win"] - cx["eras4"]["C"]["win"]
            wD = Z["eras4"]["D"]["win"] - cx["eras4"]["D"]["win"]
            ext.append(clause("X-winCD", "extra: win lift > 0 in era C or era D (C %+.3f, D %+.3f)" % (wC, wD),
                              (wC > 0) or (wD > 0), "bool", None))
        elif h == "H-C":
            gv, gc = float(probe[cid]["gap"].mean()) * 100, float(probe["CTRL"]["gap"].mean()) * 100
            ext.append(clause("X-gap", "extra: gap-through fill share must not rise (%, variant vs control)", gv, "<=", gc,
                              fmt="%.4f", note="%d of %d vs %d of %d" % (int(probe[cid]["gap"].sum()), len(probe[cid]["gap"]),
                                                                        int(probe["CTRL"]["gap"].sum()),
                                                                        len(probe["CTRL"]["gap"]))))
            kill.append(clause("K-win", "kill: in-engine win lift >= +0.75 pt (half the scan's +1.5)", wl, ">=", 0.75,
                               fmt="%+.4f"))
            kill.append(clause("K-eraD", "kill: era D net falls no more than 10% (ratio)", eraD_ratio, ">=", 0.90,
                               fmt="%.5f", note="variant $%s vs control $%s" % (FR.f0(Z["eras4"]["D"]["net"]),
                                                                              FR.f0(cx["eras4"]["D"]["net"]))))
        elif h == "H-D":
            lo, hi = int(math.ceil(0.6 * S0["n"])), int(math.floor(1.4 * S0["n"]))
            ext.append(clause("X-count", "extra: selection trade count within +/-40%% of control (%d..%d), >= low" % (lo, hi),
                              s["n"], ">=", lo))
            ext.append(clause("X-count", "extra: selection trade count within +/-40%% of control (%d..%d), <= high" % (lo, hi),
                              s["n"], "<=", hi))
            V = T[cid]
            ident, removed, added, retimed = trade_sets(C, V)
            e2v = np.asarray(V["ent"] >= pd.Timestamp(FR.ERA_SPLIT, tz=idx.tz))
            e2c = np.asarray(C["ent"] >= pd.Timestamp(FR.ERA_SPLIT, tz=idx.tz))
            aud = {}
            for nm, mv, mc in (("E1", ~e2v, ~e2c), ("E2", e2v, e2c), ("all", np.ones(len(e2v), bool), np.ones(len(e2c), bool))):
                au, ru = V["usd"][added & mv], C["usd"][removed & mc]
                aud[nm] = dict(added_n=int(len(au)), added_pf=pf_of(au), added_win=win_of(au), added_net=float(au.sum()),
                               removed_n=int(len(ru)), removed_pf=pf_of(ru), removed_win=win_of(ru),
                               removed_net=float(ru.sum()))
                say("  ADDED-vs-REMOVED %-3s added n=%d PF %.4f win %.2f%% net $%s | removed n=%d PF %.4f win %.2f%% net $%s"
                    % (nm, aud[nm]["added_n"], aud[nm]["added_pf"], aud[nm]["added_win"], FR.f0(aud[nm]["added_net"]),
                       aud[nm]["removed_n"], aud[nm]["removed_pf"], aud[nm]["removed_win"], FR.f0(aud[nm]["removed_net"])))
            say("  (re-timed variant trades, neither identical nor added: %d; identical: %d)" % (int(retimed.sum()),
                                                                                                 int(ident.sum())))
            ext.append(clause("X-addE1", "extra: added PF >= removed PF in E1", aud["E1"]["added_pf"], ">=",
                              aud["E1"]["removed_pf"]))
            ext.append(clause("X-addE2", "extra: added PF >= removed PF in E2", aud["E2"]["added_pf"], ">=",
                              aud["E2"]["removed_pf"]))
            ext.append(clause("X-addPF", "extra: added PF >= 1.0 overall", aud["all"]["added_pf"], ">=", 1.0))
            pfx_v, pfx_c = Z["pf_ex0930"], cx["pf_ex0930"]
            ext.append(clause("X-0930", "extra: PF lift > 0 without 09:30-09:35 ET entries (variant %.4f, control %.4f; "
                              "removed %d / %d)" % (pfx_v, pfx_c, Z["excl0930_n"], cx["excl0930_n"]), pfx_v - pfx_c, ">", 0.0,
                              fmt="%+.5f"))
            signs = {v: np.sign(M[cell_id(h, v)]["sel"]["pf"] - S0["pf"]) for v in H["grid"]}
            kill.append(clause("K-sign", "kill: the three non-off cells agree in the sign of PF lift (%s)"
                               % ", ".join("%g: %+.4f" % (v, M[cell_id(h, v)]["sel"]["pf"] - S0["pf"]) for v in H["grid"]),
                               len(set(signs.values())) == 1, "bool", None))
            kill.append(clause("K-top20", "kill: top-20 retention >= 17 (same as S8)", Z["top20_retained"], ">=", 17))
            kill.append(clause("K-E2pf", "kill: E2 PF lift > 0 (same as S6b)", X["era2"]["pf"] - ctl["era2"]["pf"], ">", 0.0,
                               fmt="%+.5f"))
            diag["added_vs_removed"] = aud
        if ext:
            say("  SECTION-5 EXTRA CLAUSES:")
            for c in ext:
                show_clause(c)
        if kill:
            say("  SECTION-5 KILL CRITERIA evaluable now (S10-S12 kills come next step):")
            for c in kill:
                show_clause(c)
        say("  NEIGHBOURS vs S1-S8 (record only, never gating):")
        nb_info = {}
        for v in H["nbrs"]:
            nid = cell_id(h, v)
            cl = s1_s8(nid, H["s8_min"])
            nb_info[nid] = cl
            say("    %-26s %s" % (nid, " ".join("%s:%s" % (c["clause"], "P" if c["passed"] else "F") for c in cl)))

        # scan vs file
        sv = dict(win_lift=wl, pf_lift=pl, net_lift=s["net"] - S0["net"])
        if H["scan"]:
            gapd = dict(win=wl - H["scan"]["win"], pf=pl - H["scan"]["pf"], net=(s["net"] - S0["net"]) - H["scan"]["net"])
            say("  SCAN vs FILE: in-engine win %+.3f pt / PF %+.4f / net $%s  vs scan win %+.1f / PF %+.2f / net $%s  ->  "
                "gap (engine - scan) win %+.3f / PF %+.4f / net $%s"
                % (wl, pl, sg0(s["net"] - S0["net"]), H["scan"]["win"], H["scan"]["pf"], sg0(H["scan"]["net"]),
                   gapd["win"], gapd["pf"], sg0(gapd["net"])))
        else:
            gapd = None
            say("  SCAN vs FILE: no scan prediction (the added half is invisible to a trade-list scan); in-engine win %+.3f "
                "pt / PF %+.4f / net $%s" % (wl, pl, sg0(s["net"] - S0["net"])))
        say("    trade-set audit: %d identical to control, %d control trades removed, %d re-timed, %d slot refills (no "
            "control entry in span; win %s%%)" % (Z["identical"], Z["removed"], Z["retimed"], Z["added"],
                                                  FR.fx(Z["added_win"], "%.2f")))

        gating = [c for c in cen + nb + ext + kill if c["gating"]]
        failed = [c["clause"] + ("(%s)" % c["desc"].split(":")[0] if c["clause"].startswith("S9") else "")
                  for c in gating if not c["passed"]]
        alive = not failed
        if alive:
            survivors.append(h)
        say("  VERDICT %s: %s%s" % (h, "STANDS -> S10-S12" if alive else "DEAD at selection",
                                    "" if alive else "  (failed: %s)" % ", ".join(failed)))
        RES[h] = dict(hypothesis=h, name=H["name"], centre=cid, neighbours=[cell_id(h, v) for v in H["nbrs"]],
                      a0=A0[h], centre_clauses=cen, s9=nb, extras=ext, kills=kill, neighbours_s1_s8_record=nb_info,
                      diagnostics=diag, scan_vs_file=dict(in_engine=sv, scan=H["scan"], gap=gapd,
                                                          identical=Z["identical"], removed=Z["removed"],
                                                          retimed=Z["retimed"], slot_refills=Z["added"],
                                                          slot_refill_win=Z["added_win"]),
                      failed=failed, survives=alive)
        k_step += 1
        step(k_step)

    say("\n" + "=" * 150)
    say("ITEMS 2-3 RESULT: survivors of S1-S9 + section-5 extras/kills = %s   (runtime %.0fs)"
        % (survivors if survivors else "NONE", time.time() - t_all))
    return dict(status="OK", A0=A0, rows=M, inputs=X4, thresholds=thr, results=RES, survivors=survivors)


def ha_diagnostics(A, idx, PS, sel_mod, pc, SELT, n_split, bench_sel, M, X4, T, cid_centre):
    """H-A reported diagnostics: session buckets of removed signals, and the outcome-blind planned-risk floor."""
    h = np.asarray(A["high"], float)
    l = np.asarray(A["low"], float)
    c = np.asarray(A["close"], float)
    tr = sel_mod._true_range(h, l, c)
    mask = sel_mod._rule_mask(h, l, c, A["volume"], idx, tr, int(PS["tl_len"]), 20.0, 0.0, 0.0, 0.0)
    sig = pc["signals"]
    rej = ~mask[sig]
    share = float(rej.mean())
    mins = np.asarray(idx.hour, np.int64) * 60 + np.asarray(idx.minute, np.int64)

    def bucket(bars):
        mm = mins[bars]
        b = dict(asia=int(((mm >= 1080) | (mm < 180)).sum()), europe=int(((mm >= 180) & (mm < 570)).sum()),
                 cash=int(((mm >= 570) & (mm < 960)).sum()), other=int(((mm >= 960) & (mm < 1080)).sum()))
        tot = max(1, len(bars))
        return {k: dict(n=v, pct=100.0 * v / tot) for k, v in b.items()}

    rem_b = bucket(sig[rej])
    all_b = bucket(sig)
    tsb = pc["trade_signal_bars"]
    rem_tr_b = bucket(tsb[~mask[tsb]])
    say("  H-A DIAGNOSTIC (reported, not a gate) -- removed control selection SIGNALS by session bucket: %d of %d rejected "
        "(%.3f%%)" % (int(rej.sum()), len(sig), 100 * share))
    for k in ("asia", "europe", "cash", "other"):
        say("    %-7s removed %5d (%.2f%% of removed) | all control signals %5d (%.2f%%) | removed control TRADES' signal "
            "bars %4d (%.2f%%)" % (k, rem_b[k]["n"], rem_b[k]["pct"], all_b[k]["n"], all_b[k]["pct"], rem_tr_b[k]["n"],
                                  rem_tr_b[k]["pct"]))

    al = int(PS["atr_len"])
    cs = np.cumsum(tr)
    atr = np.full(len(c), np.nan)
    atr[al - 1:] = (cs[al - 1:] - np.concatenate([[0], cs[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    tl = int(PS["tl_len"])
    swing = pd.Series(l).rolling(tl + 1, min_periods=tl + 1).min().to_numpy()
    limit = c - float(PS["limit_atr"]) * atr
    with np.errstate(invalid="ignore", divide="ignore"):
        rp = (limit - swing) / limit
    vals = rp[sig]
    fin = np.isfinite(vals)
    vs = np.sort(vals[fin])
    k = int(round(share * len(sig)))
    floor = float(vs[k]) if k < len(vs) else float("inf")
    with np.errstate(invalid="ignore"):
        mR = ~(np.isfinite(rp) & (rp < floor))
    removed_R = int((~mR[sig]).sum())
    P = dict(PS, quiet_pct=20.0, _mask_override=mR)
    r = run_backtest(SEL, arrays=A, params=P, cost_pts=FR.COST, return_trades=True)
    selR = [tuple(z) for z in sorted((r or {}).get("trades") or [], key=lambda z: z[0]) if int(z[0]) < n_split]
    del r
    MR = FR.measure(selR, A, FR.MULT, bench_sel, bench_sel)
    S0, SA, SR = M["CTRL"]["sel"], M[cid_centre]["sel"], MR["sel"]
    say("  H-A DIAGNOSTIC (reported, not a gate) -- outcome-blind planned-risk floor: risk%% < %.6f%% removes %d of %d "
        "control signals (target %d = H-A centre share)" % (100 * floor, removed_R, len(sig), k))
    say("    risk floor : n %d win %.3f%% (lift %+.3f) PF %.4f (lift %+.4f) net $%s (%.2f%% of control)"
        % (SR["n"], SR["wr"], SR["wr"] - S0["wr"], SR["pf"], SR["pf"] - S0["pf"], FR.f0(SR["net"]), 100 * SR["net"] / S0["net"]))
    say("    H-A centre : n %d win %.3f%% (lift %+.3f) PF %.4f (lift %+.4f) net $%s (%.2f%% of control)"
        % (SA["n"], SA["wr"], SA["wr"] - S0["wr"], SA["pf"], SA["pf"] - S0["pf"], FR.f0(SA["net"]), 100 * SA["net"] / S0["net"]))
    overlap = int((~mask[sig] & ~mR[sig]).sum())
    say("    overlap: %d of the %d signals H-A rejects are also rejected by the risk floor" % (overlap, int(rej.sum())))
    return dict(removed_signals_by_session=rem_b, all_control_signals_by_session=all_b,
                removed_control_trades_by_session=rem_tr_b, signals=len(sig), rejected=int(rej.sum()), share=share,
                risk_floor_pct=100 * floor, risk_floor_removed=removed_R, risk_floor_overlap=overlap,
                risk_floor_cell=dict(n=SR["n"], win=SR["wr"], pf=SR["pf"], net=SR["net"], win_lift=SR["wr"] - S0["wr"],
                                     pf_lift=SR["pf"] - S0["pf"], net_ratio=SR["net"] / S0["net"]),
                h_a_centre=dict(win_lift=SA["wr"] - S0["wr"], pf_lift=SA["pf"] - S0["pf"], net_ratio=SA["net"] / S0["net"]))


def a0_audit(tripped, A, idx, PS, sel_mod, SELT):
    """Section-4 audit for a tripped centre cell: exec_feasibility_audit --config, signal-index probe re-check,
    and recomputation of the feature from bars <= i only (truncation)."""
    tool = os.path.join(HERE, "exec_feasibility_audit.py")
    n_split = int(idx.searchsorted(pd.Timestamp(FR.SPLIT, tz=idx.tz)))
    h = np.asarray(A["high"], float)
    l = np.asarray(A["low"], float)
    c = np.asarray(A["close"], float)
    tr = sel_mod._true_range(h, l, c)
    feats = dict(quiet_pct=["q"], stretch_max=["stretch"], rec_min=["rec"], vol_clock=["clock_base", "vol_vs_clock"])
    F = sel_mod._rule_features(A["open"], A["high"], A["low"], A["close"], A["volume"], A["index"], tl_len=int(PS["tl_len"]))
    for hyp in tripped:
        knob, val = HYP[hyp]["knob"], HYP[hyp]["centre"]
        cid = cell_id(hyp, val)
        pr = subprocess.run([sys.executable, tool, "--config", os.path.basename(SEL), "--params", "%s=%r" % (knob, float(val))],
                            capture_output=True, text=True, cwd=ROOT)
        say("    %s exec_feasibility_audit --config: exit %d | %s" % (cid, pr.returncode,
                                                                     (pr.stdout or "").strip().replace("\n", " | ")))
        kn = dict(KNOBS_OFF, **{knob: val})
        mask = sel_mod._rule_mask(h, l, c, A["volume"], idx, tr, int(PS["tl_len"]), kn["quiet_pct"], kn["stretch_max"],
                                  kn["rec_min"], kn["vol_clock"])
        pb = []
        rr = sel_mod.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"], day_id=A["day_id"],
                                  index=A["index"], return_trades=True, _signal_index_probe=pb, **dict(PS, **kn))
        tr_i = [t_ for t_ in sorted(rr["trades"], key=lambda z: z[0]) if int(t_[0]) < n_split]
        same = (len(tr_i) == len(SELT[cid]) and all(int(a[0]) == int(b[0]) and int(a[1]) == int(b[1])
                                                    and abs(float(a[2]) - FR.COST - float(b[2])) < 1e-9
                                                    for a, b in zip(tr_i, SELT[cid])))
        bad = int(sum(1 for i in pb if not mask[i]))
        say("    %s signal-index probe: signal bars failing their own mask %d of %d; probe walk selection == compiled %s"
            % (cid, bad, len(pb), same))
        for ts in ("2016-03-09 11:17", "2023-10-02 03:41"):
            cut = int(idx.searchsorted(pd.Timestamp(ts, tz=idx.tz)))
            sl = slice(0, cut)
            Pf = sel_mod._rule_features(A["open"][sl], A["high"][sl], A["low"][sl], A["close"][sl], A["volume"][sl],
                                        A["index"][sl], tl_len=int(PS["tl_len"]))
            res = {}
            for k in feats[knob]:
                x, y = F[k][:cut], Pf[k]
                f_ = np.isfinite(x)
                res[k] = bool(np.array_equal(np.isnan(x), np.isnan(y)) and np.array_equal(x[f_], y[f_]))
            say("    %s truncation at bar %d (%s): feature from bars <= i equals the full-frame feature: %s"
                % (cid, cut, idx[cut - 1], res))


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return clean(o.item())
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, float) and not math.isfinite(o):
        return None if math.isnan(o) else ("inf" if o > 0 else "-inf")
    return o


def main():
    global _FH
    ap = argparse.ArgumentParser()
    ap.add_argument("--beacon", action="store_true")
    ap.add_argument("--a0-audited", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    _FH = open(OUT_TXT, "w", encoding="utf-8")
    total = 13 + 1 + 4
    try:
        if a.beacon:
            from research_beacon import beacon
            with beacon("r57 ENGU-Q grid + S1-S9 (items 2-3)", total=total) as b:
                out = run(lambda i: b.step(i), a.a0_audited)
        else:
            out = run(lambda i: None, a.a0_audited)
    finally:
        _FH.close()
        _FH = None
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(clean(out), fh, indent=1)
    print("wrote", OUT_TXT, OUT_JSON)
    sys.exit(3 if out.get("status") == "A0_STOP" else 0)


if __name__ == "__main__":
    main()

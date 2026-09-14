# -*- coding: utf-8 -*-
"""ENGU-Q ROUND 57 -- THE FRONTIER, LIKE FOR LIKE (mirrors tools/r55_noise_frontier.py for NOISE).

Owner, 2026-09-14: "run more test. try to improve the frontier ENGUQ model."

Before anything can be improved, the frontier has to be measured on ONE ruler. Every ENGU-Q
validate reported its own 75% in-sample split, its own reload-graded lockbox and (for #370 /
#377) its own instrument, so no two headline rows on the board are comparable. This replays every
frontier configuration through the engine on the house convention and prints one table.

CONVENTION (house rules, identical for every NQ row)
  tape      NQ 1-minute 24-hour (ETH) master, source db_noadj_eth (the #335 master)
  window    2010-06-07 .. 2026-06-30 PINNED (masters have a real hole 2026-07-01..08-05)
  cost      0.533 points per round turn, $20 per point, one contract
  one CONTINUOUS backtest per config; trades sliced by ENTRY time:
            selection = entries before 2025-06-30  (the validates' IS + WF optimize window;
                        no walk-forward folds are re-run here, so there is no separate WF column)
            LB        = entries from 2025-06-30    (reported, NEVER used to choose anything)
  stats     tools/queue_guard.py's own _stats (n / PF / win% / net / maxDD / MAR = (net/yrs)/DD /
            EV R = (1-win)(PF-1) / R per YR = EV R x trades per year of the stretch), so every
            number here is the same arithmetic ENGUQ.md quotes.
  params    resolved through queue_guard.resolve_params (file DEFAULT_PARAMS first, the run's own
            saved params on top) -- never the plugin signature (the {} trap).

TAIL READS (selection stretch only)
  top-10 share        (net - net without the ten best trades) / net, the guard's definition
  per-era top-10      the same inside 2010-06..2019 and 2020..2025-06 separately (whole-window
                      pooling flatters the tail -- memory enguq-384-tail-economics)
  trades-to-zero      how many best trades must be deleted before selection net <= 0
  ex-top-0.5% EV R    EV R after deleting the best 0.5% of the config's own trades (the
                      proportional read -- a fixed ten flatters high-frequency configs)
  index correlation   yearly net (by entry year) vs NQ's own year-end-to-year-end return,
                      2011..2025-H1 (2010 has no prior year-end close). The whole-window version
                      (reads the LB year) is printed separately for cross-reference only.

PARITY GATES (hard stops): the frozen #226 control must reproduce n=2,843 / $434,721.12 whole
window, and the R2 defaults must reproduce ENGUQ.md's crown table (selection n=1,830 / PF 1.714 /
$522,613; LB n=118 / PF 1.675 / $88,380). Soft gates compare every champion against the trade count
its own run doc saved (gate_validate.ungated_full, a continuous whole-window count) and flag >5%.

FOUND BY G2 ON ITS FIRST RUN (2026-09-14): ENGUQ.md's R2 table does NOT use the window it claims
("same window as the #309 table" = 2010-06-07). It reproduces exactly from 2010-06-21 (the
window memory records for that measurement). On the pinned 2010-06-07 window the R2 defaults take
ONE extra warm-up trade (entered 2010-06-10 09:16, exited 2010-06-21, +$2,131.90) and every other
trade is identical to the cent: selection n=1,831 / PF 1.717 / $524,745, LB unchanged. G2 therefore
checks both halves (exact reproduction from 2010-06-21, and a pinned-window difference made only of
pre-2010-06-21 entries); the table itself stays on the pinned house window, like #226 and #309.

Every per-trade quantity here is an OUTCOME sliced by entry time; no per-trade condition is
computed, so the signal-bar rule has nothing to act on.

Run from the SHARED checkout (it holds the master registry):
    cd C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG
    set AUGUR_TRIAL_CACHE=1
    python C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\enguq57\\tools\\r57_enguq_frontier.py
One process, no pool (13 NQ configs + 3 ES reference rows, ~1-2 minutes; R2-R5 are compiled).
"""
import json
import math
import os
import sys
import time

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402
from augur_engine.data import find_master, load_master_arrays           # noqa: E402
from augur_engine.engine import run_backtest                            # noqa: E402
from augur_engine.strategies import load_strategy, strategy_params      # noqa: E402
from queue_guard import resolve_params, _stats                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "r37_results", "r57_frontier.txt")
OUT_JSON = os.path.join(HERE, "r37_results", "r57_frontier.json")

WIN = ("2010-06-07", "2026-06-30")
SPLIT = "2025-06-30"
ERA_SPLIT = "2020-01-01"
COST, MULT = 0.533, 20.0
SCRATCH_PTS = 1.0     # |net pnl| <= 1 point ($20) = a scratch (breakeven stop-outs net -0.533)

# ------------------------------------------------------------------ the params, and where each came from
# api/paper.py ENGUQ_335 (the crown the paper leg and NinjaTrader trade) -- must equal R2's DEFAULT_PARAMS.
PAPER_ENGUQ_335 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, ema_len=220, atr_len=52, act_R=1.5,
                       breakeven_R=2.0, limit_atr=0.55, er_len=100, stop_mult=1.0, regime_len=10,
                       min_brk=1.6, vol_mult=1.1, er_th=0.0)
# api/paper.py ENGUQ_335_VC == run #335 validate.champion (both read 2026-09-14, identical).
P335C = dict(buf_atr=0.4, tl_len=238, trail_frac=4.0, ema_len=1340, atr_len=28, act_R=2.5,
             breakeven_R=1.0, limit_atr=0.1, er_len=100, stop_mult=1.2, regime_len=5, min_brk=1.4,
             vol_mult=0.0, er_th=0.0)
# runs #370 (ES @0.40, PASS) and #377 (ES @0.60, WEAK): validate.champion, IDENTICAL cell in both docs.
P370 = dict(buf_atr=0.8, tl_len=230, trail_frac=3.5, ema_len=420, atr_len=44, act_R=3.0,
            breakeven_R=1.5, limit_atr=0.1, er_len=80, stop_mult=1.1, regime_len=10, min_brk=2.4,
            vol_mult=0.5, er_th=0.15)
# runs #376 and #383 (R3, both WEAK): validate.champion, IDENTICAL cell in both docs.
P376 = dict(buf_atr=1.0, max_hold_bars=7760, tl_len=186, trail_frac=3.5, ema_len=500, atr_len=28,
            act_R=0.5, limit_atr=0.45, breakeven_R=1.0, er_len=80, stop_mult=2.0, regime_len=0,
            min_brk=1.8, vol_mult=0.2, er_th=0.15)
# run #384 (R3, 900 trials, WEAK): validate.champion.
P384 = dict(buf_atr=0.9, max_hold_bars=9600, tl_len=178, trail_frac=2.0, ema_len=580, atr_len=120,
            act_R=2.5, limit_atr=0.75, breakeven_R=0.0, er_len=80, stop_mult=0.9, regime_len=0,
            min_brk=0.0, vol_mult=0.3, er_th=0.0)
# run #380 (R4, PASS): validate.champion.
P380 = dict(buf_atr=0.25, tl_len=262, trail_frac=1.5, ema_len=580, atr_len=84, act_R=0.5,
            breakeven_R=2.0, limit_atr=0.6, er_len=20, stop_mult=1.4, regime_len=0, min_brk=2.5,
            vol_mult=0.4, er_th=0.05)
# run #381 (R5, FAIL): validate.champion AS SAVED -- er_len -30, vol_mult -2.4, er_th -0.1 are
# outside the file's declared ranges (the code treats <=0 as OFF for vol_mult and er_th).
P381 = dict(buf_atr=0.35, max_hold_bars=11040, tl_len=194, trail_frac=2.0, ema_len=560, atr_len=72,
            act_R=4.0, limit_atr=1.15, breakeven_R=1.5, er_len=-30, stop_mult=1.9, regime_len=0,
            min_brk=1.1, vol_mult=-2.4, er_th=-0.1)
# run #309 best_params == validate.champion (cached run doc) == api/paper.py ENGUQ_309.
P309 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, ema_len=220, atr_len=52, act_R=1.5,
            breakeven_R=3.0, limit_atr=0.55, er_len=100, stop_mult=1.3, regime_len=10, min_brk=1.6,
            vol_mult=1.1, er_th=0.0)
# run #265 best_params (ER25 pinned card).
P265 = dict(buf_atr=0.9, tl_len=170, trail_frac=2.5, ema_len=1380, atr_len=106, act_R=2.5,
            breakeven_R=1.5, limit_atr=0.0, er_len=60, stop_mult=1.0, regime_len=0, min_brk=1.3,
            vol_mult=0.8, er_th=0.25)
# run #226 best_params (FROZEN pinned card).
P226 = dict(buf_atr=0.9, vol_mult=0.8, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            regime_len=0, min_brk=1.3, breakeven_R=1.5, atr_len=106, act_R=2.5)

# row numbers are permanent handles
CONFIGS = [
    (1, "R2 defaults = #335 crown", "ENGUQ_1M_ETH_R2_1_0.py", {},
     "CROWN; paper ENGUQ_335 + NinjaTrader; validate #335 PASS certifies the landscape", None),
    (2, "#335 search champion", "ENGUQ_1M_ETH_R2_1_0.py", P335C,
     "validate #335's own cell; paper ENGUQ_335_VC", None),
    (3, "#370/#377 champion (ES-picked)", "ENGUQ_1M_ETH_R2_1_0.py", P370,
     "ES validates #370 PASS@0.40 / #377 WEAK@0.60, same cell; on NQ = never selected here", None),
    (4, "R3 defaults (cap 8280)", "ENGUQ_1M_ETH_R3_1_0.py", {}, "file defaults (validates searched it)", None),
    (5, "#376/#383 champion", "ENGUQ_1M_ETH_R3_1_0.py", P376, "R3 validates, WEAK x2, same cell", 2090),
    (6, "#384 champion (900 trials)", "ENGUQ_1M_ETH_R3_1_0.py", P384, "R3 validate WEAK", 4075),
    (7, "R4 defaults (limit 0.85)", "ENGUQ_1M_ETH_R4_1_0.py", {}, "file defaults", None),
    (8, "#380 champion", "ENGUQ_1M_ETH_R4_1_0.py", P380, "R4 validate PASS", 3336),
    (9, "R5 defaults (lim .85+cap 9660)", "ENGUQ_1M_ETH_R5_1_0.py", {}, "file defaults", None),
    (10, "#381 champion", "ENGUQ_1M_ETH_R5_1_0.py", P381, "R5 validate FAIL; knobs outside fence", 2550),
    (11, "#309 ex-crown control", "ENGUQ_1M_ETH_ER_1_0.py", P309, "validate PASS; paper ENGUQ_309", 1604),
    (12, "#265 ER25 (eff. gate 0.25)", "ENGUQ_1M_ETH_ER25_1_0.py", P265, "validate PASS; paper ENGUQ_ER", None),
    (13, "#226 frozen control", "ENGUQ_1M_ETH_FROZEN_1_0.py", P226, "validate PASS; old crown", 2843),
]


class Tee(object):
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")
        self.o = sys.stdout

    def write(self, s):
        self.o.write(s)
        self.f.write(s)

    def flush(self):
        self.o.flush()
        self.f.flush()


def fence_breaches(strategy_file, resolved):
    """Knobs whose value sits outside the file's declared DEFAULT_PARAMS [min, max]."""
    dp = strategy_params(load_strategy(strategy_file)) or {}
    out = []
    for k, v in resolved.items():
        m = dp.get(k)
        if not isinstance(m, dict) or "min" not in m or "max" not in m:
            continue
        try:
            if float(v) < float(m["min"]) - 1e-9 or float(v) > float(m["max"]) + 1e-9:
                out.append("%s=%s (fence %s..%s)" % (k, v, m["min"], m["max"]))
        except (TypeError, ValueError):
            pass
    return out


def year_bench(idx_naive, close, upto=None):
    """NQ's own calendar-year return, year-end close over prior year-end close (percent),
    the tools/concentration_check.py beta_block definition. `upto` truncates the series
    (exclusive) so the selection read never touches a lockbox bar."""
    px = pd.Series(np.asarray(close, float), index=idx_naive)
    if upto is not None:
        px = px[px.index < upto]
    last = px.resample("YE").last()
    b = ((last / last.shift(1) - 1.0) * 100.0).dropna()
    b.index = b.index.year
    return b


def measure(trades, A, mult, bench_sel, bench_all):
    idx = pd.DatetimeIndex(A["index"])
    tz = idx.tz

    def _ts(s):
        t = pd.Timestamp(s)
        return t.tz_localize(tz) if (tz is not None and t.tz is None) else t

    split_ts, from_ts, to_ts, era_ts = _ts(SPLIT), _ts(WIN[0]), _ts(WIN[1]), _ts(ERA_SPLIT)
    nbar = len(idx)
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in trades])
    ext = pd.DatetimeIndex([idx[min(int(t[1]), nbar - 1)] for t in trades])
    pts = np.array([float(t[2]) for t in trades])
    usd = pts * mult
    hold = np.array([(b - a).days for a, b in zip(ent, ext)])

    sel = np.asarray(ent < split_ts)
    lb = ~sel
    y_sel = max((split_ts - (ent[sel].min() if sel.any() else from_ts)).days, 1) / 365.25
    y_lb = max((to_ts - split_ts).days, 1) / 365.25
    y_all = max((to_ts - from_ts).days, 1) / 365.25
    S = _stats(list(pts[sel]), y_sel, mult)
    L = _stats(list(pts[lb]), y_lb, mult)
    W = _stats(list(pts), y_all, mult)

    sp = sorted(pts[sel])
    S10 = _stats(sp[:-10] if len(sp) > 10 else sp, y_sel, mult)
    top10 = (1 - S10["net"] / S["net"]) * 100.0 if S["net"] else float("nan")

    # proportional tail: delete the best 0.5% of the stretch's own trades
    k05 = max(1, int(round(0.005 * len(sp))))
    S05 = _stats(sp[:-k05], y_sel, mult)

    # trades-to-zero on the selection stretch
    su = np.sort(usd[sel])[::-1]
    net_sel = float(su.sum())
    if net_sel <= 0:
        ttz = 0
    else:
        rem = net_sel - np.cumsum(su)
        hit = np.nonzero(rem <= 0)[0]
        ttz = int(hit[0] + 1) if len(hit) else len(su)

    def era_block(mask):
        e = usd[mask]
        n = len(e)
        if n == 0:
            return dict(n=0, net=0.0, pf=None, top10=float("nan"), ex10=0.0)
        net = float(e.sum())
        es = np.sort(e)[::-1]
        t10 = float(es[:10].sum())
        gl = float(-e[e < 0].sum())
        return dict(n=n, net=net, pf=(float(e[e > 0].sum()) / gl if gl > 0 else None),
                    top10=(100.0 * t10 / net if net > 0 else float("nan")), ex10=net - t10)

    ent_a = np.asarray(ent)
    e1 = era_block(sel & (ent < era_ts))
    e2 = era_block(sel & (ent >= era_ts))

    # yearly net by entry year
    ser_sel = pd.Series(usd[sel], index=ent[sel].year)
    yr_sel = ser_sel.groupby(level=0).sum()
    ser_all = pd.Series(usd, index=ent.year)
    yr_all = ser_all.groupby(level=0).sum()

    def _corr(yr, bench):
        common = yr.index.intersection(bench.index)
        return float(yr[common].corr(bench[common])) if len(common) > 2 else float("nan"), len(common)

    corr_sel, ny_sel = _corr(yr_sel, bench_sel)
    corr_all, ny_all = _corr(yr_all, bench_all)

    w = usd[sel][usd[sel] > 0]
    l_ = usd[sel][usd[sel] < 0]
    med_w = float(np.median(w)) if len(w) else float("nan")
    med_l = float(np.median(l_)) if len(l_) else float("nan")
    wr = S["wr"] / 100.0 if S["wr"] is not None else float("nan")
    be_ratio = (1 - wr) / wr if wr and wr > 0 else float("nan")
    # scratches: trades that closed within 1 point of flat after cost (a breakeven stop nets -0.533)
    ps = pts[sel]
    scratch = np.abs(ps) <= SCRATCH_PTS
    n_res = int((~scratch).sum())
    scratch_pct = 100.0 * float(scratch.mean()) if len(ps) else float("nan")
    wr_ex_scratch = 100.0 * float((ps[~scratch] > 0).sum()) / n_res if n_res else float("nan")

    return dict(
        sel=S, lb=L, whole=W, sel_ex10_net=S10["net"], top10=top10, era1=e1, era2=e2,
        ttz=ttz, ttz_pct=(100.0 * ttz / S["n"] if S["n"] else float("nan")),
        evr_ex05=S05["evr"], k05=k05,
        corr_sel=corr_sel, ny_sel=ny_sel, corr_all=corr_all, ny_all=ny_all,
        y2018=float(yr_sel.get(2018, 0.0)), y2022=float(yr_sel.get(2022, 0.0)),
        pos_years=int((yr_sel > 0).sum()), n_years=int(len(yr_sel)),
        yearly_sel={int(k): float(v) for k, v in yr_sel.items()},
        hold_sel=int(hold[sel].max()) if sel.any() else 0, hold_all=int(hold.max()) if len(hold) else 0,
        med_w=med_w, med_l=med_l, wl_ratio=(med_w / abs(med_l) if med_l == med_l and med_l else float("nan")),
        be_ratio=be_ratio, scratch_pct=scratch_pct, wr_ex_scratch=wr_ex_scratch,
        first_entry=str(ent.min()), last_entry=str(ent.max()),
    )


def f0(v):
    return "-" if v is None or (isinstance(v, float) and not math.isfinite(v)) else format(int(round(v)), ",")


def fx(v, fmt):
    return "-" if v is None or (isinstance(v, float) and not math.isfinite(v)) else fmt % v


def pareto(rows, axes):
    """Non-dominated set. axes = [(key_fn, 'max'|'min')]; a NaN/None value counts as the worst."""
    def val(r, fn, sense):
        v = fn(r)
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return -float("inf") if sense == "max" else float("inf")
        return v

    out = []
    for a in rows:
        dominated = False
        for b in rows:
            if b is a:
                continue
            ge = all((val(b, fn, s) >= val(a, fn, s)) if s == "max" else (val(b, fn, s) <= val(a, fn, s))
                     for fn, s in axes)
            gt = any((val(b, fn, s) > val(a, fn, s)) if s == "max" else (val(b, fn, s) < val(a, fn, s))
                     for fn, s in axes)
            if ge and gt:
                dominated = True
                break
        if not dominated:
            out.append(a)
    return out


def main():
    t0 = time.time()
    sys.stdout = Tee(OUT_TXT)
    print("ENGU-Q ROUND 57 -- LIKE-FOR-LIKE FRONTIER TABLE   (driver tools/r57_enguq_frontier.py, run %s)"
          % time.strftime("%Y-%m-%d %H:%M"))
    print("tape NQ 1m ETH db_noadj_eth | window %s..%s pinned | cost %.3f pts/RT x $%d | one continuous run per "
          "config, entry-sliced: selection = entries < %s (validates' IS+WF optimize window, no WF folds re-run "
          "here), LB = entries >= %s" % (WIN[0], WIN[1], COST, MULT, SPLIT, SPLIT))
    print("LB columns are REPORTED ONLY; nothing below is chosen on them.\n")

    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    A = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(A["index"])
    idx_naive = idx.tz_localize(None)
    print("master %s id %s: %d bars, %s .. %s  (load %.1fs)"
          % (m.get("filename"), m.get("id"), len(idx), idx[0], idx[-1], time.time() - t0))
    split_naive = pd.Timestamp(SPLIT)
    bench_sel = year_bench(idx_naive, A["close"], upto=split_naive)
    bench_all = year_bench(idx_naive, A["close"])
    print("NQ yearly return (selection read, 2025 = H1 to the split): "
          + "  ".join("%d %+.1f%%" % (y, v) for y, v in bench_sel.items()))
    print()

    R = {}
    R1_TRADES = None
    for num, label, fn, params, status, doc_n in CONFIGS:
        t1 = time.time()
        resolved, source, has_dp = resolve_params(fn, params)
        r = run_backtest(fn, arrays=A, params=dict(resolved), cost_pts=COST, return_trades=True)
        trades = sorted(r.get("trades") or [], key=lambda z: z[0])
        if num == 1:
            R1_TRADES = trades
        M = measure(trades, A, MULT, bench_sel, bench_all)
        M.update(num=num, label=label, file=fn, status=status, doc_n=doc_n, params=resolved,
                 from_caller=sorted(k for k, v in source.items() if v == "caller"),
                 fence=fence_breaches(fn, resolved), secs=time.time() - t1)
        R[num] = M
        print("  ran %2d %-32s %6d trades  %.1fs" % (num, label, M["whole"]["n"], M["secs"]))
    print()

    # ------------------------------------------------------------------ parity gates
    print("=" * 150)
    print("PARITY")
    r13, r1, r11 = R[13], R[1], R[11]
    g1 = r13["whole"]["n"] == 2843 and abs(r13["whole"]["net"] - 434721.12) < 0.01
    print("  G1 #226 frozen control, whole window: n=%d net=$%.2f   want n=2843 net=$434,721.12   -> %s"
          % (r13["whole"]["n"], r13["whole"]["net"], "PASS" if g1 else "FAIL"))
    # G2 -- ENGUQ.md's R2 crown table says "same window as the #309 table" (2010-06-07) but was in
    # fact measured from 2010-06-21 (memory engu-q-project / edgelog-evr-tail-detector: "window
    # 2010-06-21..2026-06-30"; found by this gate 2026-09-14). So the gate is two-part and both parts
    # are hard: (i) from 2010-06-21 the R2 defaults must reproduce the ENGUQ.md numbers exactly, and
    # (ii) the pinned 2010-06-07 run used for the table must differ from it ONLY by trades entered
    # before 2010-06-21 (warm-up), every other trade identical to the cent.
    A21 = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), date_from="2010-06-21", date_to=WIN[1])
    i21 = pd.DatetimeIndex(A21["index"])
    t21 = sorted(run_backtest(r1["file"], arrays=A21, params=dict(r1["params"]), cost_pts=COST,
                              return_trades=True).get("trades") or [], key=lambda z: z[0])
    M21 = measure(t21, A21, MULT, bench_sel, bench_all)
    s, l = M21["sel"], M21["lb"]
    g2 = (s["n"] == 1830 and round(s["pf"], 3) == 1.714 and round(s["net"]) == 522613
          and l["n"] == 118 and round(l["pf"], 3) == 1.675 and round(l["net"]) == 88380)
    print("  G2 R2 defaults (#335 crown) from 2010-06-21: sel n=%d PF %.3f net $%s DD $%s EV R %.3f R/YR %.1f | LB n=%d "
          "PF %.3f net $%s DD $%s   want sel 1,830 / 1.714 / $522,613 / $38,687 / 0.505 / 61.7, LB 118 / 1.675 / $88,380 / "
          "$41,534 (ENGUQ.md)   -> %s"
          % (s["n"], s["pf"], f0(s["net"]), f0(s["dd"]), s["evr"], s["ryr"], l["n"], l["pf"], f0(l["net"]), f0(l["dd"]),
             "PASS" if g2 else "FAIL"))
    key21 = set((str(i21[int(t[0])]), str(i21[min(int(t[1]), len(i21) - 1)]), round(float(t[2]), 4)) for t in t21)
    key07 = set((str(idx[int(t[0])]), str(idx[min(int(t[1]), len(idx) - 1)]), round(float(t[2]), 4)) for t in R1_TRADES)
    only07, only21 = sorted(key07 - key21), sorted(key21 - key07)
    g2c = (not only21) and all(pd.Timestamp(x[0]) < pd.Timestamp("2010-06-21").tz_localize(idx.tz) for x in only07)
    print("  G2c pinned 2010-06-07 run vs 2010-06-21 run: %d trade(s) only in the pinned run %s, %d only in the other   "
          "-> %s (the table's row 1 = ENGUQ.md + that warm-up trade: sel n=%d PF %.3f net $%s)"
          % (len(only07), ["%s -> %s $%.2f" % (a, b, c * MULT) for a, b, c in only07], len(only21),
             "PASS" if g2c else "FAIL", r1["sel"]["n"], r1["sel"]["pf"], f0(r1["sel"]["net"])))
    g2 = g2 and g2c
    g2b = r1["params"] == {**r1["params"], **PAPER_ENGUQ_335} and all(r1["params"][k] == v for k, v in PAPER_ENGUQ_335.items())
    print("  G2b R2 file DEFAULT_PARAMS == api/paper.py ENGUQ_335 (what paper + NinjaTrader trade)   -> %s"
          % ("PASS" if g2b else "FAIL"))
    if not (g1 and g2 and g2b):
        print("\nPARITY FAILED -- nothing below would mean anything. Stopping.")
        sys.stdout.flush()
        sys.exit(1)
    s, l = r11["sel"], r11["lb"]
    g3 = (r11["whole"]["n"] == 1604 and round(r11["whole"]["net"]) == 591267 and s["n"] == 1505
          and round(s["pf"], 3) == 1.661 and l["n"] == 99 and round(l["pf"], 3) == 1.620)
    print("  G3 #309: whole n=%d $%s | sel n=%d PF %.3f | LB n=%d PF %.3f   want 1,604 / $591,267 | 1,505 / 1.661 | "
          "99 / 1.620   -> %s" % (r11["whole"]["n"], f0(r11["whole"]["net"]), s["n"], s["pf"], l["n"], l["pf"],
                                  "PASS" if g3 else "FLAG"))
    r2 = R[2]
    g4 = r2["whole"]["n"] == 1344 and r2["lb"]["n"] == 128 and round(r2["lb"]["net"]) == 49812
    print("  G4 #335 search champion: whole n=%d PF %.3f $%s | LB n=%d PF %.3f $%s DD $%s   want 1,344 / 1.82 / $541k | "
          "128 / 1.455 / $49,812 / DD $47,779   -> %s"
          % (r2["whole"]["n"], r2["whole"]["pf"], f0(r2["whole"]["net"]), r2["lb"]["n"], r2["lb"]["pf"],
             f0(r2["lb"]["net"]), f0(r2["lb"]["dd"]), "PASS" if g4 else "FLAG"))
    r6 = R[6]
    g5 = r6["whole"]["n"] == 4075 and round(r6["whole"]["net"]) == 596112
    print("  G5 #384 champion: whole n=%d $%s PF %.3f win %.1f%%   want 4,075 / $596,112 / 1.297 / 29.4%% "
          "(memory enguq-384-tail-economics)   -> %s"
          % (r6["whole"]["n"], f0(r6["whole"]["net"]), r6["whole"]["pf"], r6["whole"]["wr"], "PASS" if g5 else "FLAG"))
    r12 = R[12]
    g6 = r12["lb"]["n"] == 67 and round(r12["lb"]["pf"], 3) == 2.645
    print("  G6 #265 ER25: LB n=%d PF %.3f   want 67 / 2.645 (continuous_lb_check)   -> %s"
          % (r12["lb"]["n"], r12["lb"]["pf"], "PASS" if g6 else "FLAG"))
    r9 = R[9]
    print("  G7 R5 defaults vs its docstring: LB n=%d PF %.3f $%s (doc 151 / 1.648 / $99,997); whole-window index corr "
          "%+.3f (doc +0.273 via queue_guard --tail)" % (r9["lb"]["n"], r9["lb"]["pf"], f0(r9["lb"]["net"]), r9["corr_all"]))
    for num in sorted(R):
        M = R[num]
        if M["doc_n"]:
            d = abs(M["whole"]["n"] - M["doc_n"]) / max(M["doc_n"], 1) * 100
            print("  count %2d %-32s whole n=%5d vs run doc gate_validate.ungated_full %5d  (%.1f%%)%s"
                  % (num, M["label"], M["whole"]["n"], M["doc_n"], d, "  *** MISMATCH ***" if d > 5 else ""))
    print()

    rows = [R[k] for k in sorted(R)]

    # ------------------------------------------------------------------ panel 1: money
    print("=" * 150)
    print("PANEL 1 -- MONEY.  selection = entries 2010-06-07..2025-06-29  |  LB = entries 2025-06-30..2026-06-30 (reported only)")
    print("%3s %-32s | %5s %5s %6s %9s %8s %5s %6s %6s | %4s %5s %6s %8s %8s | %5s %9s"
          % ("#", "config", "n", "win%", "PF", "net $", "DD $", "MAR", "EV R", "R/YR",
             "LB n", "win%", "PF", "net $", "DD $", "wholen", "whole $"))
    for M in rows:
        s, l, w = M["sel"], M["lb"], M["whole"]
        print("%3d %-32s | %5d %5.1f %6.3f %9s %8s %5.2f %6.3f %6.1f | %4d %5s %6s %8s %8s | %5d %9s"
              % (M["num"], M["label"][:32], s["n"], s["wr"], s["pf"], f0(s["net"]), f0(s["dd"]), s["mar"], s["evr"],
                 s["ryr"], l["n"], fx(l["wr"], "%.1f"), fx(l["pf"], "%.3f"), f0(l["net"]), f0(l["dd"]),
                 w["n"], f0(w["net"])))
    print()

    # ------------------------------------------------------------------ panel 2: tail
    print("=" * 150)
    print("PANEL 2 -- TAIL (selection only).  top-10 = share of net in the ten best trades; per era the same inside "
          "the era; TTZ = best trades deleted before net <= 0")
    print("%3s %-32s | %6s %9s | %5s %7s %9s | %5s %7s %9s | %4s %5s | %8s | %6s %5s"
          % ("#", "config", "top10", "ex10 $", "n<20", "top10", "ex10 $", "n20+", "top10", "ex10 $",
             "TTZ", "TTZ%", "EVRx.5%", "corr", "yrs"))
    for M in rows:
        e1, e2 = M["era1"], M["era2"]

        def sh(e):
            return ("%5.0f%%" % e["top10"]) if math.isfinite(e["top10"]) else "  neg "
        print("%3d %-32s | %5.0f%% %9s | %5d %7s %9s | %5d %7s %9s | %4d %4.1f%% | %8s | %+6.2f %2d/%-2d"
              % (M["num"], M["label"][:32], M["top10"], f0(M["sel_ex10_net"]), e1["n"], sh(e1), f0(e1["ex10"]),
                 e2["n"], sh(e2), f0(e2["ex10"]), M["ttz"], M["ttz_pct"], fx(M["evr_ex05"], "%.3f"),
                 M["corr_sel"], M["pos_years"], M["n_years"]))
    print("  corr = yearly net (entry year) vs NQ's own yearly return over %d selection years 2011..2025-H1; "
          "yrs = positive years / years traded 2010-H2..2025-H1" % rows[0]["ny_sel"])
    print()

    # ------------------------------------------------------------------ panel 3: shape
    print("=" * 150)
    print("PANEL 3 -- SHAPE (selection only).  2018 = NQ %+.1f%%, 2022 = NQ %+.1f%%"
          % (bench_sel.get(2018, float("nan")), bench_sel.get(2022, float("nan"))))
    print("%3s %-32s | %9s %9s | %8s %8s | %7s %7s %6s | %6s | %5s %6s %7s | %s"
          % ("#", "config", "2018 $", "2022 $", "hold sel", "hold all", "med W $", "med L $", "W/L",
             "BE W/L", "win%", "scr%", "win%xs", "fence breaches / status"))
    for M in rows:
        print("%3d %-32s | %9s %9s | %7dd %7dd | %7s %7s %6.2f | %6.2f | %5.1f %5.1f%% %6.1f%% | %s%s"
              % (M["num"], M["label"][:32], f0(M["y2018"]), f0(M["y2022"]), M["hold_sel"], M["hold_all"],
                 f0(M["med_w"]), f0(M["med_l"]), M["wl_ratio"], M["be_ratio"], M["sel"]["wr"], M["scratch_pct"],
                 M["wr_ex_scratch"], ("FENCE: " + "; ".join(M["fence"]) + " | ") if M["fence"] else "", M["status"]))
    print("  W/L = median winner / |median loser|; BE W/L = the payoff ratio that breaks even at that win rate, "
          "(1-win)/win. W/L barely above BE = the typical trade pair makes nothing.")
    print("  win%% = share of trades that are winners (net > 0); scr%% = share closing within %.1f point of flat after "
          "cost (breakeven stop-outs); win%%xs = winners among the trades that were NOT scratches." % SCRATCH_PTS)
    print()

    # ------------------------------------------------------------------ yearly
    print("=" * 150)
    print("YEARLY SELECTION NET $ by entry year (2010 = Jun-Dec, 2025 = Jan-Jun 29)")
    years = sorted(set(y for M in rows for y in M["yearly_sel"]))
    print("%3s %-24s " % ("#", "config") + " ".join("%8d" % y for y in years))
    print("%3s %-24s " % ("", "NQ yearly %") + " ".join(("%+7.1f%%" % bench_sel[y]) if y in bench_sel.index else "       -"
                                                      for y in years))
    for M in rows:
        print("%3d %-24s " % (M["num"], M["label"][:24])
              + " ".join("%8s" % f0(M["yearly_sel"].get(y, 0.0)) for y in years))
    print()

    # ------------------------------------------------------------------ cross-reference
    print("=" * 150)
    print("CROSS-REFERENCE ONLY (reads the LB year, never used to judge): whole-window index corr "
          "(queue_guard --tail convention, %d years 2011..2026-H1)" % rows[0]["ny_all"])
    for M in rows:
        print("  %2d %-32s whole-window corr %+.3f   whole n=%d PF %.3f net $%s DD $%s"
              % (M["num"], M["label"], M["corr_all"], M["whole"]["n"], M["whole"]["pf"], f0(M["whole"]["net"]),
                 f0(M["whole"]["dd"])))
    print()

    # ------------------------------------------------------------------ Pareto
    print("=" * 150)
    print("PARETO FRONTIERS (selection-stretch reads only; the LB never enters)")

    def worst_era(M):
        a, b = M["era1"]["top10"], M["era2"]["top10"]
        if not (math.isfinite(a) and math.isfinite(b)):
            return float("nan")
        return max(a, b)

    fr = {}
    fr["a"] = pareto(rows, [(lambda M: M["sel"]["mar"], "max"), (lambda M: M["sel"]["pf"], "max")])
    fr["b"] = pareto(rows, [(worst_era, "min"), (lambda M: M["ttz"], "max"), (lambda M: M["corr_sel"], "min")])
    fr["b_pct"] = pareto(rows, [(worst_era, "min"), (lambda M: M["ttz_pct"], "max"), (lambda M: M["corr_sel"], "min")])
    fr["c"] = pareto(rows, [(lambda M: M["sel"]["wr"], "max"), (lambda M: M["sel"]["pf"], "max")])
    fr["c_xs"] = pareto(rows, [(lambda M: M["wr_ex_scratch"], "max"), (lambda M: M["sel"]["pf"], "max")])
    fr["all"] = pareto(rows, [(lambda M: M["sel"]["mar"], "max"), (lambda M: M["sel"]["pf"], "max"),
                              (worst_era, "min"), (lambda M: M["ttz"], "max"), (lambda M: M["corr_sel"], "min"),
                              (lambda M: M["sel"]["wr"], "max")])

    def show(key, title):
        print("  (%s) %s" % (key, title))
        for M in fr[key]:
            print("      %2d %-32s MAR %.2f PF %.3f | worst-era top-10 %s TTZ %d (%.1f%%) corr %+.2f | win %.1f%%"
                  % (M["num"], M["label"], M["sel"]["mar"], M["sel"]["pf"],
                     fx(worst_era(M), "%.0f%%"), M["ttz"], M["ttz_pct"], M["corr_sel"], M["sel"]["wr"]))

    show("a", "risk-adjusted money: max selection MAR, max selection PF")
    show("b", "tail independence: min worst-era top-10 share, max trades-to-zero, min index correlation")
    show("b_pct", "tail independence, proportional variant: trades-to-zero as % of trades")
    show("c", "win rate: max win%, with PF as the second axis (win% alone -> the single max)")
    top_wr = max(rows, key=lambda M: M["sel"]["wr"])
    print("      highest win%% alone: %d %s %.1f%%" % (top_wr["num"], top_wr["label"], top_wr["sel"]["wr"]))
    show("c_xs", "win rate among non-scratch trades, with PF as the second axis")
    for M in fr["c_xs"]:
        print("         %2d win%% ex-scratch %.1f%% (scratches %.1f%% of trades)" % (M["num"], M["wr_ex_scratch"],
                                                                             M["scratch_pct"]))
    show("all", "all six axes together")
    print()

    print("=" * 150)
    print("RESOLVED PARAMS PER ROW (file DEFAULT_PARAMS overlaid by the run's saved params)")
    for M in rows:
        print("  %2d %-32s [%s] %s" % (M["num"], M["label"], M["file"], json.dumps(M["params"], sort_keys=True)))
    print()

    # ------------------------------------------------------------------ ES reference block for rows 3
    print("=" * 150)
    print("REFERENCE, NOT LIKE-FOR-LIKE: row 3's cell on ITS OWN tape (ES 1m ETH db_noadj_eth, $50/pt, same window and "
          "split) -- #370 graded it at 0.40 pts/RT, #377 at 0.60")
    me = find_master("ES", "1m", "eth", "db_noadj_eth")
    AE = load_master_arrays(me, date_from=WIN[0], date_to=WIN[1])
    ie = pd.DatetimeIndex(AE["index"]).tz_localize(None)
    be_sel = year_bench(ie, AE["close"], upto=split_naive)
    be_all = year_bench(ie, AE["close"])
    es_rows = []
    for lab, fn, p, cost in (("#370/#377 champion @0.40", "ENGUQ_1M_ETH_R2_1_0.py", P370, 0.40),
                             ("#370/#377 champion @0.60", "ENGUQ_1M_ETH_R2_1_0.py", P370, 0.60),
                             ("R2 defaults on ES @0.40", "ENGUQ_1M_ETH_R2_1_0.py", {}, 0.40)):
        res, _src, _h = resolve_params(fn, p)
        r = run_backtest(fn, arrays=AE, params=dict(res), cost_pts=cost, return_trades=True)
        tr = sorted(r.get("trades") or [], key=lambda z: z[0])
        E = measure(tr, AE, 50.0, be_sel, be_all)
        es_rows.append(dict(label=lab, cost=cost, **{k: E[k] for k in ("sel", "lb", "whole", "top10", "ttz",
                                                                          "corr_sel", "era1", "era2")}))
        s, l = E["sel"], E["lb"]
        print("  %-26s sel n=%d win %.1f%% PF %.3f net $%s DD $%s MAR %.2f | top-10 %.0f%% TTZ %d corr %+.2f | "
              "LB n=%d PF %s net $%s | whole n=%d%s"
              % (lab, s["n"], s["wr"], s["pf"], f0(s["net"]), f0(s["dd"]), s["mar"], E["top10"], E["ttz"],
                 E["corr_sel"], l["n"], fx(l["pf"], "%.3f"), f0(l["net"]), E["whole"]["n"],
                 ("  (run doc ungated_full 681)" if cost == 0.40 and p else "")))
    print()
    print("done in %.0fs" % (time.time() - t0))

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, float) and not math.isfinite(o):
            return None
        if isinstance(o, (np.floating, np.integer)):
            return clean(o.item())
        return o

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(clean(dict(convention=dict(window=WIN, split=SPLIT, era_split=ERA_SPLIT, cost=COST, mult=MULT,
                                             tape="NQ 1m ETH db_noadj_eth"),
                             rows=rows, es_reference=es_rows,
                             frontier={k: [M["num"] for M in v] for k, v in fr.items()})), f, indent=1)
    sys.stdout.flush()


if __name__ == "__main__":
    main()

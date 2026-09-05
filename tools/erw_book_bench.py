"""
ENGU-Q "floor x wide exits" (ERW) -- multi-instrument POOLED BOOK bench (worktree erw-book).

QUESTION: R/YR = EV R x trades/year. The ERW config (er_th 0.25 efficiency floor stacked
on wide "let it run" exits, run #265's #226 base) found the highest EV R yet measured here
(EV R 1.10, R/YR 46 on NQ 1m ETH, but only 672 trades/16y -- starved). Pooling several
INDEPENDENT instrument legs multiplies trades/year while EV R stays per-trade, so pooling
is the obvious way to turn this into the highest R/YR single BOOK. Does it clear the bar?

INVENTORY (STEP 1): find_master(inst, "1m", "eth", "db_noadj_eth") for ES/YM/RTY/MNQ/MES/CL/GC.
Only NQ (2010-06-06..2026-09-04) and ES (2010-06-06..2026-09-04) have a 1m ETH master in this
repo. YM/RTY/MNQ/MES/CL/GC: NOT FOUND -- skipped, no cost/multiplier fabricated for them.
Costs used: NQ 0.533 pts x $20/pt; ES 0.79 pts x $50/pt (both per the campaign brief, not
invented here).

VARIANTS (both at er_th=0.25, everything else at ERW/#265 defaults):
  A) trail_frac=5.0, act_R=3.0   (run #265's NQ 1m ETH numbers: n=672, $603,701, PF 2.33,
     EV R 1.10, R/YR 46, 4/4 eras, 24 held-out trades)
  B) trail_frac=4.0, act_R=3.0   (NQ 1m ETH: n=832, $565,161, PF 2.02, EV R 0.82, R/YR 42,
     4/4 eras, 37 held-out trades)
Per-instrument CONTROL: er_th=0.0 (gate off), trail_frac=2.5, act_R=2.5 -- all other knobs
at ERW/#265 defaults (i.e. that instrument's own "#226-shape" ungated baseline).

STEP 2 -- per-leg bench, in-engine, on 2010-06-07..2026-06-30 (16 engine runs budgeted,
<=12 used: NQ{A,B,control} + ES{A,B,control} = 6 runs total). Report n, net, PF, EV R, R/YR,
eras held vs that instrument's own control, held-out (entries>=2025-06-30) trades, for every
leg on every available instrument (NQ is the reference leg, already characterized by run #265
but re-run here in-process for a byte-identical trade list to pool from).

STEP 3 -- pool: concatenate the per-leg trade lists (already priced in USD via each leg's own
cost/mult) into ONE book per variant, sorted by entry time, exactly ONE contract per leg, NO
leg selection (dropping a leg after seeing results would be hindsight and voids the read).
Report pooled n, net, dollar PF, EV R, R/YR, eras held vs the POOLED ungated control (NQ
control + ES control pooled the same way), held-out trades, and pooled max drawdown.

PRE-REGISTERED BARS for the pooled book (written BEFORE running; ALL FIVE must pass for a
variant to be PROMISING and get a BOOK job queued):
  1. pooled PF > pooled ungated-control PF
  2. pooled R/YR > 113 (current book high-water mark, run #261)
  3. pooled EV R > 0.7 (current single-strategy high-water mark, ENGU-Q RTH #149)
  4. >= 60 pooled held-out (entries >= 2025-06-30) trades
  5. held-out pooled PF > 1.3
PRIMARY is declared here, before running: Variant A (trail_frac=5.0) is PRIMARY, because it is
the higher-EV-R config (#265's own top cell) and starves harder single-instrument -- pooling
should help it more. Variant B is reported in full regardless.

Only NQ+ES are available so this is a 2-leg book (not the many-instrument book the brief
imagines) -- report that limitation plainly; a 2-leg pool can still clear R/YR>113 only if
per-leg trade density is high enough, which is exactly what this bench measures.
"""
import sys
import json
import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\erw-book"
sys.path.insert(0, REPO)
SCR = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad")

import augur_engine.paths as _paths
import augur_engine.data as _data
_SHARED_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
_paths.DB_PATH = _SHARED_ROOT + r"\optimizer_history.db"
_paths.UPLOADS = _SHARED_ROOT + r"\augur_uploads"
_data.DB_PATH = _paths.DB_PATH
_data.UPLOADS = _paths.UPLOADS
from augur_engine.data import find_master, load_master_arrays
import importlib.util
spec = importlib.util.spec_from_file_location(
    "erw", REPO + r"\augur_strategies\ENGUQ_1M_ETH_ERW_1_0.py")
erw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(erw)

DATE_FROM, DATE_TO = "2010-06-07", "2026-06-30"
LB_START = "2025-06-30"

COSTS = {"NQ": (0.533, 20), "ES": (0.79, 50)}
CANDIDATES = ["ES", "YM", "RTY", "MNQ", "MES", "CL", "GC"]

print("=" * 70)
print("STEP 1 -- INVENTORY (find_master 1m eth db_noadj_eth)")
available = ["NQ"]
for inst in CANDIDATES:
    m = find_master(inst, "1m", session="eth", source="db_noadj_eth")
    if m:
        print(f"  {inst}: FOUND  {m.get('date_from')}..{m.get('date_to')}  {m.get('filename')}")
        if inst in COSTS:
            available.append(inst)
        else:
            print(f"    -> no standing cost/multiplier for {inst} in the brief/repo docs -- SKIPPING")
    else:
        print(f"  {inst}: NOT FOUND -- skipped")
m_nq = find_master("NQ", "1m", session="eth", source="db_noadj_eth")
print(f"  NQ: FOUND  {m_nq.get('date_from')}..{m_nq.get('date_to')}  {m_nq.get('filename')} (reference)")
print("AVAILABLE LEGS:", available)

DATA = {}
for inst in available:
    master = find_master(inst, "1m", session="eth", source="db_noadj_eth")
    arr = load_master_arrays(master, date_from=DATE_FROM, date_to=DATE_TO)
    DATA[inst] = arr
    print(f"  loaded {inst}: {len(arr['close'])} bars, idx {arr['index'][0]}..{arr['index'][-1]}")

BASE = dict(er_len=60, er_th=0.25, limit_atr=0.0, tl_len=170, vol_mult=0.8, stop_mult=1.0,
            act_R=2.5, trail_frac=2.5, buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106,
            regime_len=0, breakeven_R=1.5)


def run_leg(inst, **params):
    arr = DATA[inst]
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    v = arr.get("volume")
    idx = pd.to_datetime(arr["index"])
    out = erw.run_backtest(o, h, l, c, volumes=v, return_trades=True, **params)
    if out is None or not out.get("trades"):
        return None, None
    trades = out["trades"]  # (entry_idx, exit_idx, pnl_pts, side, entry_px)
    cost, mult = COSTS[inst]
    pnl = np.array([(t[2] - cost) * mult for t in trades])
    ent = idx[[int(t[0]) for t in trades]]
    return pnl, ent


def stats(pnl, ent, ref_eras=None):
    n = len(pnl)
    if n == 0:
        return None
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    wr = len(wins) / n
    pf = wins.sum() / max(abs(losses.sum()), 1e-9)
    ev_r = (1 - wr) * (pf - 1)
    years = (ent[-1] - ent[0]).days / 365.25
    tpy = n / years if years > 0 else float("nan")
    r_yr = ev_r * tpy
    lb_ts = pd.Timestamp(LB_START)
    if getattr(ent, "tz", None) is not None and lb_ts.tzinfo is None:
        lb_ts = lb_ts.tz_localize(ent.tz)
    lb_mask = ent >= lb_ts
    lb_n = int(lb_mask.sum())
    lb_pnl = pnl[lb_mask]
    lb_net = float(lb_pnl.sum())
    lb_pf = (lb_pnl[lb_pnl > 0].sum() / max(abs(lb_pnl[lb_pnl < 0].sum()), 1e-9)) if lb_n else float("nan")
    eras = []
    for a, b in (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
                 ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")):
        ta, tb = pd.Timestamp(a), pd.Timestamp(b)
        if getattr(ent, "tz", None) is not None:
            ta = ta.tz_localize(ent.tz); tb = tb.tz_localize(ent.tz)
        m = (ent >= ta) & (ent < tb)
        dd = pnl[m]
        if len(dd) == 0:
            eras.append((a[:4], np.nan, 0))
            continue
        epf = dd[dd > 0].sum() / max(abs(dd[dd < 0].sum()), 1e-9)
        eras.append((a[:4], float(epf), int(len(dd))))
    cum = np.cumsum(pnl)
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    holds = None
    if ref_eras is not None:
        holds = sum(1 for e in eras if not np.isnan(e[1]) and e[0] in ref_eras
                    and not np.isnan(ref_eras[e[0]]) and e[1] > ref_eras[e[0]])
    return dict(n=n, net=round(float(pnl.sum()), 2), pf=round(float(pf), 3), wr=round(wr * 100, 1),
                ev_r=round(float(ev_r), 3), r_yr=round(float(r_yr), 1), maxdd=round(maxdd, 2),
                lb_n=lb_n, lb_net=round(lb_net, 2), lb_pf=round(float(lb_pf), 3) if lb_n else None,
                eras=eras, eras_held_vs_ref=holds)


# ── PARITY ANCHOR (NQ only, this is the parent's certified window) ──
print("\n" + "=" * 70)
print("PARITY 1 -- NQ all defaults (#265): expect n=1336, net $486,413.24, PF 1.597, LB n=67 $146,230.78")
pnl, ent = run_leg("NQ", **BASE)
p1 = stats(pnl, ent)
print(p1)
ok1 = (p1 and p1["n"] == 1336 and abs(p1["net"] - 486413.24) < 1.0 and abs(p1["pf"] - 1.597) < 0.005
       and p1["lb_n"] == 67 and abs(p1["lb_net"] - 146230.78) < 1.0)
print("PARITY 1:", "PASS" if ok1 else "FAIL")

print("\nPARITY 2 -- NQ er_th=0.0 (gate off): expect n=2843, net $434,721.12 (#226 parity)")
pnl2, ent2 = run_leg("NQ", **{**BASE, "er_th": 0.0})
p2 = stats(pnl2, ent2)
print(p2)
ok2 = (p2 and p2["n"] == 2843 and abs(p2["net"] - 434721.12) < 1.0)
print("PARITY 2:", "PASS" if ok2 else "FAIL")

print("\nPARITY 3 -- NQ variant A (trail_frac=5.0, act_R=3.0, er_th=0.25): "
      "expect n=672, net $603,701, PF 2.33, EV R 1.10, R/YR 46, LB n=24")
pnlA, entA = run_leg("NQ", **{**BASE, "trail_frac": 5.0, "act_R": 3.0})
p3 = stats(pnlA, entA)
print(p3)
ok3 = (p3 and p3["n"] == 672 and abs(p3["net"] - 603701) < 50 and abs(p3["pf"] - 2.33) < 0.02)
print("PARITY 3:", "PASS" if ok3 else "FAIL")

print("\nPARITY 4 -- NQ variant B (trail_frac=4.0, act_R=3.0, er_th=0.25): "
      "expect n=832, net $565,161, PF 2.02, EV R 0.82, R/YR 42, LB n=37")
pnlB, entB = run_leg("NQ", **{**BASE, "trail_frac": 4.0, "act_R": 3.0})
p4 = stats(pnlB, entB)
print(p4)
ok4 = (p4 and p4["n"] == 832 and abs(p4["net"] - 565161) < 50 and abs(p4["pf"] - 2.02) < 0.02)
print("PARITY 4:", "PASS" if ok4 else "FAIL")

PARITY_ALL = ok1 and ok2 and ok3 and ok4

VARIANTS = {
    "A_trail5_act3": dict(trail_frac=5.0, act_R=3.0, er_th=0.25),
    "B_trail4_act3": dict(trail_frac=4.0, act_R=3.0, er_th=0.25),
}
CONTROL = dict(trail_frac=2.5, act_R=2.5, er_th=0.0)

print("\n" + "=" * 70)
print("STEP 2 -- PER-LEG BENCH (PRIMARY = variant A, trail_frac=5.0)")
leg_results = {}   # inst -> {"control":stats, "A":stats, "B":stats, trades: {...}}
for inst in available:
    ctrl_pnl, ctrl_ent = run_leg(inst, **{**BASE, **CONTROL})
    ctrl_st = stats(ctrl_pnl, ctrl_ent)
    ref_eras = {e[0]: e[1] for e in ctrl_st["eras"]} if ctrl_st else {}
    row = {"control": ctrl_st, "control_trades": (ctrl_pnl, ctrl_ent)}
    for vname, vparams in VARIANTS.items():
        pnl_v, ent_v = run_leg(inst, **{**BASE, **vparams})
        st = stats(pnl_v, ent_v, ref_eras=ref_eras)
        row[vname] = st
        row[vname + "_trades"] = (pnl_v, ent_v)
    leg_results[inst] = row
    print(f"\n-- {inst} --")
    if ctrl_st:
        print(f"  control        n={ctrl_st['n']:5d} net=${ctrl_st['net']:>11,.0f} PF={ctrl_st['pf']:.3f} "
              f"EV_R={ctrl_st['ev_r']:.3f} R/YR={ctrl_st['r_yr']:.1f} LB(n={ctrl_st['lb_n']})")
    else:
        print("  control        -> None (no trades)")
    for vname in VARIANTS:
        st = row[vname]
        if st:
            print(f"  {vname:14s} n={st['n']:5d} net=${st['net']:>11,.0f} PF={st['pf']:.3f} "
                  f"EV_R={st['ev_r']:.3f} R/YR={st['r_yr']:.1f} eras_held={st['eras_held_vs_ref']}/4 "
                  f"LB(n={st['lb_n']},PF={st['lb_pf']})")
        else:
            print(f"  {vname:14s} -> None (no trades)")

# ── STEP 3 -- POOL ──
print("\n" + "=" * 70)
print("STEP 3 -- POOL (concat trade lists across available legs, sorted by entry time, "
      "1 contract/leg, no leg selection)")


def pool(trades_by_inst):
    all_pnl, all_ent = [], []
    for inst, (pnl_v, ent_v) in trades_by_inst.items():
        if pnl_v is None or len(pnl_v) == 0:
            continue
        all_pnl.append(pnl_v)
        di = pd.DatetimeIndex(ent_v)
        if di.tz is not None:
            di = di.tz_convert("UTC").tz_localize(None)
        all_ent.append(di)
    if not all_pnl:
        return None, None
    pnl_cat = np.concatenate(all_pnl)
    ent_cat = pd.DatetimeIndex(np.concatenate([e.values for e in all_ent]))
    order = np.argsort(ent_cat.values)
    return pnl_cat[order], ent_cat[order]


pooled_ctrl_pnl, pooled_ctrl_ent = pool({inst: leg_results[inst]["control_trades"] for inst in available})
pooled_ctrl_st = stats(pooled_ctrl_pnl, pooled_ctrl_ent)
pooled_ref_eras = {e[0]: e[1] for e in pooled_ctrl_st["eras"]} if pooled_ctrl_st else {}
print(f"\nPooled CONTROL ({'+'.join(available)}): n={pooled_ctrl_st['n']}, net=${pooled_ctrl_st['net']:,.0f}, "
      f"PF={pooled_ctrl_st['pf']:.3f}, EV_R={pooled_ctrl_st['ev_r']:.3f}, R/YR={pooled_ctrl_st['r_yr']:.1f}, "
      f"maxDD=${pooled_ctrl_st['maxdd']:,.0f}, LB n={pooled_ctrl_st['lb_n']}")

pooled_results = {}
for vname in VARIANTS:
    p_pnl, p_ent = pool({inst: leg_results[inst][vname + "_trades"] for inst in available})
    st = stats(p_pnl, p_ent, ref_eras=pooled_ref_eras)
    pooled_results[vname] = st
    print(f"Pooled {vname:14s} ({'+'.join(available)}): n={st['n']}, net=${st['net']:,.0f}, "
          f"PF={st['pf']:.3f}, EV_R={st['ev_r']:.3f}, R/YR={st['r_yr']:.1f}, eras_held={st['eras_held_vs_ref']}/4, "
          f"maxDD=${st['maxdd']:,.0f}, LB n={st['lb_n']}, LB PF={st['lb_pf']}")

# ── PRE-REGISTERED BARS ──
print("\n" + "=" * 70)
print("PRE-REGISTERED BARS: (1) pooled PF > pooled control PF; (2) pooled R/YR > 113; "
      "(3) pooled EV R > 0.7; (4) >=60 pooled LB trades; (5) held-out pooled PF > 1.3")
verdicts = {}
for vname, st in pooled_results.items():
    bar1 = st["pf"] > pooled_ctrl_st["pf"]
    bar2 = st["r_yr"] > 113
    bar3 = st["ev_r"] > 0.7
    bar4 = st["lb_n"] >= 60
    bar5 = (st["lb_pf"] is not None) and (st["lb_pf"] > 1.3)
    passed = bar1 and bar2 and bar3 and bar4 and bar5
    verdicts[vname] = dict(passed=passed, bar1_pf=bar1, bar2_ryr=bar2, bar3_evr=bar3,
                            bar4_lbn=bar4, bar5_lbpf=bar5)
    marker = " <== PRIMARY" if vname.startswith("A_") else ""
    print(f"{vname:14s} -> {'PROMISING' if passed else 'DEAD'} "
          f"(bar1 PF>{pooled_ctrl_st['pf']:.3f}:{bar1}, bar2 R/YR>113:{bar2}({st['r_yr']:.1f}), "
          f"bar3 EV_R>0.7:{bar3}({st['ev_r']:.3f}), bar4 LB>=60:{bar4}({st['lb_n']}), "
          f"bar5 LB_PF>1.3:{bar5}({st['lb_pf']})){marker}")

promising = [v for v, r in verdicts.items() if r["passed"]]
print("\nPROMISING variants:", promising if promising else "NONE -- queue nothing")

# ── save ──
def _ser_eras(eras):
    return [[a, (None if (isinstance(b, float) and np.isnan(b)) else b), c] for a, b, c in eras]


out_json = {
    "parity": {"p1": p1, "ok1": ok1, "p2": p2, "ok2": ok2, "p3": p3, "ok3": ok3, "p4": p4, "ok4": ok4,
               "all_pass": PARITY_ALL},
    "available_legs": available,
    "per_leg": {
        inst: {
            "control": {**leg_results[inst]["control"], "eras": _ser_eras(leg_results[inst]["control"]["eras"])}
                        if leg_results[inst]["control"] else None,
            **{vname: ({**leg_results[inst][vname], "eras": _ser_eras(leg_results[inst][vname]["eras"])}
                       if leg_results[inst][vname] else None)
               for vname in VARIANTS},
        } for inst in available
    },
    "pooled_control": {**pooled_ctrl_st, "eras": _ser_eras(pooled_ctrl_st["eras"])},
    "pooled": {vname: {**st, "eras": _ser_eras(st["eras"])} for vname, st in pooled_results.items()},
    "verdicts": verdicts,
    "promising": promising,
}
json.dump(out_json, open(SCR + r"\_erw_book.json", "w"), indent=1, default=str)
json.dump(out_json, open(REPO + r"\tools\_erw_book.json", "w"), indent=1, default=str)
print("\nSAVED", SCR + r"\_erw_book.json", "and", REPO + r"\tools\_erw_book.json")

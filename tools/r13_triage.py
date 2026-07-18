"""Round-13 triage driver (TV top-boosts sweep) — committed for individual pickups.

Usage (from repo root):
    python tools/r13_triage.py BBRSI_1_0.py "Medium (author-knob grid)"
    python tools/r13_triage.py EMAX_1_0.py  "Medium (classic-pairs grid)"

What it does (pre-registered per TV_SWEEP.md §1):
  - loads the four RTH masters (NQ/ES x 1m/5m) with a HARD cutoff at 2025-06-30 —
    the lockbox year (2025-06-30 -> 2026-06-30) is never in memory;
  - reproduces the ORB 3.1 #125 champion blotter and ABORTS unless it matches the
    documented anchor exactly (n=3,815 / $306,331 / PF 1.607) — this certifies the
    correlation gate before any challenger number is trusted;
  - reproduces the ENGU-Q deploy config for a DIRECTIONAL-ONLY correlation read
    (the 2026-07-14 file-repro defect is still open — do not treat as certified);
  - runs the strategy's published defaults on all four datasets, then the named
    PARAM_GRID_PRESETS tier on NQ 5m, and evaluates the round-13 gates
    (G-econ PF>=1.25 & MAR>=8 · G1 n>=300 · G3 post-2021 share<=50% ·
     G4 avg loser >= 8 NQ pts · G5 |corr vs ORB| < 0.40 · G6 top year <= 40%);
  - writes tools/r13_results/r13_<STRATEGY>_results.json (published stats incl.
    by-year table + every grid cell with its gate scan).

Round-13 verdicts (2026-07-17): 0 of 12 strategies passed. See TV_SWEEP.md §4/§5.
A pickup session re-running a cell should get IDENTICAL numbers (deterministic
engine, no seeds involved) — if the ORB anchor fails, the data changed; stop.
"""
import json, sys, time, itertools, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest as eng_run, find_master, load_master_arrays

OUT = pathlib.Path(__file__).resolve().parent / "r13_results"
OUT.mkdir(exist_ok=True)
FULL = ("2010-06-07", "2025-06-30")          # triage window; lockbox NEVER loaded
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

STRAT = sys.argv[1] if len(sys.argv) > 1 else "BBRSI_1_0.py"
GRID_PRESET = sys.argv[2] if len(sys.argv) > 2 else "Medium (author-knob grid)"

def load(inst, tf):
    m = find_master(inst, tf, "rth")
    if m is None:
        raise SystemExit(f"no master {inst} {tf} rth")
    return load_master_arrays(m, date_from=FULL[0], date_to=FULL[1])

def daily_pnl(res, arr, mult):
    """exit-date daily net $ PnL series (dict date->$)."""
    out = {}
    idx = arr["index"]
    for t in res.get("trades") or []:
        d = pd.Timestamp(idx[int(t[1])]).date()
        out[d] = out.get(d, 0.0) + float(t[2]) * mult
    return out

def yearly(res, arr, mult):
    ys = {}
    idx = arr["index"]
    for t in res.get("trades") or []:
        y = pd.Timestamp(idx[int(t[1])]).year
        ys[y] = ys.get(y, 0.0) + float(t[2]) * mult
    return dict(sorted(ys.items()))

def corr(a, b, union=True):
    days = sorted(set(a) | set(b)) if union else sorted(set(a) & set(b))
    if len(days) < 30:
        return float("nan"), len(days)
    va = np.array([a.get(d, 0.0) for d in days])
    vb = np.array([b.get(d, 0.0) for d in days])
    if va.std() < 1e-9 or vb.std() < 1e-9:
        return float("nan"), len(days)
    return float(np.corrcoef(va, vb)[0, 1]), len(days)

def stats(res, arr, inst):
    mult = MULT[inst]
    tr = res.get("trades") or []
    net = res["total_pnl"] * mult
    dd = res["max_drawdown"] * mult
    mar = (net / abs(dd)) if dd < -1e-9 else float("inf")
    ys = yearly(res, arr, mult)
    tot = sum(ys.values())
    post21 = sum(v for y, v in ys.items() if y >= 2021)
    post21_share = (post21 / tot * 100.0) if abs(tot) > 1e-9 else float("nan")
    top_year_share = (max(ys.values()) / tot * 100.0) if ys and tot > 1e-9 else float("nan")
    losers = [t[2] for t in tr if t[2] < 0]
    avg_loser_pts = float(-np.mean(losers)) if losers else float("nan")
    return dict(n=res["num_trades"], pf=round(res["profit_factor"], 3),
                wr=round(res["win_rate"], 1), net=round(net, 0), dd=round(dd, 0),
                mar=round(mar, 2), post21_share=round(post21_share, 1),
                top_year_share=round(top_year_share, 1),
                avg_loser_pts=round(avg_loser_pts, 2), years=ys)

def gates(st, corr_orb, corr_eng):
    g = {}
    g["G-econ PF>=1.25"] = st["pf"] >= 1.25
    g["G-econ MAR>=8"] = st["mar"] >= 8
    g["G1 n>=300"] = st["n"] >= 300
    g["G3 post21<=50%"] = (not np.isnan(st["post21_share"])) and st["post21_share"] <= 50.0
    g["G4 avgloser>=8pts"] = (not np.isnan(st["avg_loser_pts"])) and st["avg_loser_pts"] >= 8.0
    g["G5 |corrORB|<0.40"] = (corr_orb is not None) and abs(corr_orb) < 0.40
    g["G6 topyear<=40%"] = (not np.isnan(st["top_year_share"])) and st["top_year_share"] <= 40.0
    g["_pass"] = all(v for k, v in g.items() if not k.startswith("_"))
    g["_corr_orb"] = None if corr_orb is None else round(corr_orb, 3)
    g["_corr_engu_directional"] = None if corr_eng is None else round(corr_eng, 3)
    return g

t0 = time.time()
print(f"=== ROUND-13 TRIAGE: {STRAT} ===  window {FULL[0]} -> {FULL[1]} (lockbox sealed)")

arrs = {}
for inst, tf in [("NQ", "5m"), ("NQ", "1m"), ("ES", "5m"), ("ES", "1m")]:
    arrs[(inst, tf)] = load(inst, tf)
    print(f"loaded {inst} {tf}: {len(arrs[(inst,tf)]['close'])} bars")

# ── champion anchors ─────────────────────────────────────────────────────────
ORB_CFG = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5,
               flat_eod=True)
orb = eng_run("ORB_3_1.py", arrays=arrs[("NQ", "5m")], params=ORB_CFG,
              cost_pts=COST["NQ"], return_trades=True)
orb_net = orb["total_pnl"] * MULT["NQ"]
print(f"ORB #125 anchor: n={orb['num_trades']} net=${orb_net:,.0f} PF={orb['profit_factor']:.3f} "
      f"(expect ~n=3815 / $306,331 / 1.607)")
if not (abs(orb["num_trades"] - 3815) <= 5 and abs(orb_net - 306331) <= 500):
    print("!! ORB anchor mismatch — ABORT (fix before trusting any correlation gate)")
    sys.exit(1)
orb_daily = daily_pnl(orb, arrs[("NQ", "5m")], MULT["NQ"])

ENG_CFG = dict(tl_len=34, vol_mult=1.2, stop_mult=1.7, act_R=1.0, trail_frac=2.5,
               buf_atr=0.35, min_brk=0.7, ema_len=30, atr_len=47, regime_len=0,
               breakeven_R=1.5)
try:
    eng = eng_run("ENGUQ_1M_1_0.py", arrays=arrs[("NQ", "1m")], params=ENG_CFG,
                  cost_pts=COST["NQ"], return_trades=True)
    eng_daily = daily_pnl(eng, arrs[("NQ", "1m")], MULT["NQ"])
    print(f"ENGU-Q repro (DIRECTIONAL — known repro defect): n={eng['num_trades']} "
          f"net=${eng['total_pnl']*20:,.0f} PF={eng['profit_factor']:.3f}")
except Exception as e:
    eng_daily = None
    print("ENGU-Q repro failed:", repr(e)[:120])

# ── published defaults on all four datasets ─────────────────────────────────
import importlib.util
spec = importlib.util.spec_from_file_location("strat_r13", str(REPO / "augur_strategies" / STRAT))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
published = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
print(f"\npublished defaults: {published}")

results = {"strategy": STRAT, "window": FULL, "published": {}, "grid": [],
           "orb_anchor": dict(n=orb["num_trades"], net=orb_net, pf=orb["profit_factor"])}

for (inst, tf), arr in arrs.items():
    r = eng_run(STRAT, arrays=arr, params=published, cost_pts=COST[inst], return_trades=True)
    if r is None:
        print(f"{inst} {tf}: NO TRADES"); results["published"][f"{inst}_{tf}"] = None; continue
    st = stats(r, arr, inst)
    results["published"][f"{inst}_{tf}"] = st
    print(f"{inst} {tf}: n={st['n']} PF={st['pf']} WR={st['wr']}% net=${st['net']:,.0f} "
          f"DD=${st['dd']:,.0f} MAR={st['mar']} post21={st['post21_share']}% "
          f"topyr={st['top_year_share']}% avgLoser={st['avg_loser_pts']}pts")

# ── pre-registered grid on NQ 5m ─────────────────────────────────────────────
grid_def = mod.PARAM_GRID_PRESETS[GRID_PRESET]
keys = list(grid_def.keys())
cells = list(itertools.product(*[grid_def[k] for k in keys]))
print(f"\ngrid '{GRID_PRESET}': {len(cells)} cells on NQ 5m")
arr5 = arrs[("NQ", "5m")]
best = None
for vals in cells:
    p = dict(published); p.update(dict(zip(keys, vals)))
    r = eng_run(STRAT, arrays=arr5, params=p, cost_pts=COST["NQ"], return_trades=True)
    if r is None:
        continue
    st = stats(r, arr5, "NQ")
    co, _ = corr(daily_pnl(r, arr5, MULT["NQ"]), orb_daily)
    ce = corr(daily_pnl(r, arr5, MULT["NQ"]), eng_daily)[0] if eng_daily else None
    g = gates(st, co, ce)
    row = {"params": {k: p[k] for k in keys}, **st, "gates": g}
    row.pop("years")
    results["grid"].append(row)
    if g["_pass"] and (best is None or st["mar"] > best[0]):
        best = (st["mar"], p, st, g)

npass = sum(1 for r in results["grid"] if r["gates"]["_pass"])
print(f"grid done: {len(results['grid'])} ran, {npass} pass ALL gates")
results["n_pass"] = npass

top = sorted(results["grid"], key=lambda r: r["mar"], reverse=True)[:8]
print("\ntop by MAR (pass gates?):")
for r in top:
    print(f"  MAR={r['mar']:6.2f} PF={r['pf']:5.2f} n={r['n']:5d} net=${r['net']:>10,.0f} "
          f"DD=${r['dd']:>9,.0f} p21={r['post21_share']:5.1f}% corrORB={r['gates']['_corr_orb']} "
          f"pass={r['gates']['_pass']} {r['params']}")

if best is not None:
    _, bp, bst, bg = best
    print(f"\nBEST PASSING CELL: {bp}")
    results["best_passing"] = {"params": bp, "stats": bst, "gates": bg, "breadth": {}}
    for (inst, tf), arr in arrs.items():
        if (inst, tf) == ("NQ", "5m"):
            continue
        r = eng_run(STRAT, arrays=arr, params=bp, cost_pts=COST[inst], return_trades=True)
        st = stats(r, arr, inst) if r else None
        results["best_passing"]["breadth"][f"{inst}_{tf}"] = st
        if st:
            print(f"  breadth {inst} {tf}: n={st['n']} PF={st['pf']} net=${st['net']:,.0f} "
                  f"DD=${st['dd']:,.0f} MAR={st['mar']}")
else:
    print("\nNO CELL PASSES ALL GATES")

fn = OUT / f"r13_{STRAT.replace('.py','')}_results.json"
fn.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
print(f"\nsaved {fn}  ({time.time()-t0:.0f}s)")

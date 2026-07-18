"""Round-13 DEEP-TUNE (item 18): throw the real Auto-Optimize search at the top-3 TV
strategies across ALL core-4 datasets, holding the sealed lockbox.

Answers the owner's question: were these tuned with our best tooling, not just the
"as-given" params + a small grid? This uses the SAME seeded search space + sampler the
web app's 🤖 AUTO-OPTIMIZE scope uses (augur_engine.auto), over each strategy's FULL
DEFAULT_PARAMS ranges — a real 400-trial search per dataset, not a hand grid.

Lockbox HELD: every dataset loaded with date_to=2025-06-30; the 2025-06-30→2026-06-30
holdout is never in memory. No irreversible spend. (Escalation to the lockbox one-shot
is item 19 — owner sign-off, separate.)

Per (strategy × NQ/ES × 1m/5m):
  - 400 seeded samples over the full param space, each evaluated on the whole IS window
    (2010-06-07 → 2025-06-30) with house costs;
  - track BOTH the PnL-max champion (the app's Auto-Optimize criterion) and the MAR-max
    champion (our deciding metric), each realism-gated (>=5 wins & losses, trade-rate,
    PF<=6) and n>=300;
  - 75/25 in-sample/OOS re-test of the MAR champion (robustness within IS);
  - frozen 6-fold walk-forward of the MAR champion (count OOS-positive folds);
  - round-13 gate check (PF>=1.25, MAR>=8, n>=300, post-2021<=50%) on the full-IS MAR champ.

Usage:  python tools/r13_deeptune.py                 # all 3 x core-4
        python tools/r13_deeptune.py EMAX_1_0.py     # one strategy x core-4
"""
import json, sys, time, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest as eng_run, load_master_arrays, find_master
from augur_engine.strategies import load_strategy
from augur_engine.auto import _auto_space_from_params, _RandomSampler, _collapse, _is_real

OUT = pathlib.Path(__file__).resolve().parent / "r13_results"
OUT.mkdir(exist_ok=True)
IS_WINDOW = ("2010-06-07", "2025-06-30")     # lockbox (2025-06-30->2026-06-30) HELD
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}
N_TRIALS = 400
DATASETS = [("NQ", "5m"), ("NQ", "1m"), ("ES", "5m"), ("ES", "1m")]

STRATS = sys.argv[1:] or ["EMAX_1_0.py", "BBRSI_1_0.py", "PMAX_1_0.py"]


def metrics(res, mult):
    net = res["total_pnl"] * mult
    dd = res["max_drawdown"] * mult
    mar = (net / abs(dd)) if dd < -1e-9 else float("inf")
    return dict(n=res["num_trades"], pf=round(res["profit_factor"], 3),
                wr=round(res["win_rate"], 1), net=round(net), dd=round(dd),
                mar=round(mar, 2))


def yearly_post21(res, arr, mult):
    ys = {}
    idx = arr["index"]
    for t in res.get("trades") or []:
        y = pd.Timestamp(idx[int(t[1])]).year
        ys[y] = ys.get(y, 0.0) + float(t[2]) * mult
    tot = sum(ys.values())
    p21 = sum(v for y, v in ys.items() if y >= 2021)
    return round(p21 / tot * 100.0, 1) if abs(tot) > 1e-9 else float("nan")


def run_one(strat, inst, tf):
    arr = load_master_arrays(find_master(inst, tf, "rth"),
                             date_from=IS_WINDOW[0], date_to=IS_WINDOW[1])
    n = len(arr["close"])
    mult, cost = MULT[inst], COST[inst]
    mod = load_strategy(strat)
    dp = mod.DEFAULT_PARAMS
    space = _auto_space_from_params(dp)
    samp = _RandomSampler(space, seed=42)

    ksplit = int(n * 0.75)               # TRAIN = first 75%, OOS = last 25% (honest holdout WITHIN IS)
    def _slice_arr(a, b):
        return {k: (v[a:b] if hasattr(v, "__len__") and k in ("open","high","low","close","volume","day_id","index") else v)
                for k, v in arr.items()}
    train_arr = _slice_arr(0, ksplit)
    n_train = ksplit
    min_tr = max(200, int(300 * 0.75))   # scale the 300-trade floor to the train window

    # ── search: select the champion ON TRAIN ONLY (first 75%), gated ──────────
    best_pnl = None      # (net, params, m_train)
    best_mar = None      # (mar, params, m_train)
    seen, n_valid = set(), 0
    for _ in range(N_TRIALS):
        p = _collapse(samp.ask(), dp)
        sig = tuple(sorted((k, str(v)) for k, v in p.items()))
        if sig in seen:
            continue
        seen.add(sig)
        r = eng_run(strat, arrays=train_arr, params=p, cost_pts=cost, return_trades=True)
        if not r or r["num_trades"] < min_tr:
            continue
        if not _is_real(r, n_train):
            continue
        n_valid += 1
        m = metrics(r, mult)
        if best_pnl is None or m["net"] > best_pnl[0]:
            best_pnl = (m["net"], p, m)
        if (m["mar"] != float("inf")) and (best_mar is None or m["mar"] > best_mar[0]):
            best_mar = (m["mar"], p, m)

    if best_mar is None:
        return {"dataset": f"{inst}_{tf}", "n_valid": n_valid, "no_champion": True}

    _, champ_p, m_train = best_mar

    # ── evaluate the TRAIN champion on: OOS (last 25%, TRUE holdout), full IS, WF ──
    oos = eng_run(strat, arrays=_slice_arr(ksplit, n), params=champ_p, cost_pts=cost, return_trades=True)
    oos_m = metrics(oos, mult) if oos else None
    full = eng_run(strat, arrays=arr, params=champ_p, cost_pts=cost, return_trades=True)
    full_m = metrics(full, mult) if full else None
    p21 = yearly_post21(full, arr, mult) if full else float("nan")

    # frozen 6-fold walk-forward of the TRAIN champion across the full IS window
    folds, fold_pos, fold_nets = 6, 0, []
    for f in range(folds):
        a, b = int(n*f/folds), int(n*(f+1)/folds)
        fr = eng_run(strat, arrays=_slice_arr(a, b), params=champ_p, cost_pts=cost, return_trades=True)
        fn_net = round(fr["total_pnl"]*mult) if fr else 0
        fold_nets.append(fn_net)
        if fn_net > 0:
            fold_pos += 1

    # Gates judged on the HONEST OOS champion metrics (not the train-inflated ones)
    jm = oos_m or {}
    gates = {
        "OOS PF>=1.25": jm.get("pf", 0) >= 1.25,
        "OOS MAR>=8": jm.get("mar", 0) >= 8,
        "OOS n>=75": jm.get("n", 0) >= 75,
        "full post21<=50%": (not np.isnan(p21)) and p21 <= 50.0,
        "WF>=4/6": fold_pos >= 4,
    }
    return {
        "dataset": f"{inst}_{tf}", "n_valid": n_valid,
        "champion_params": champ_p,
        "train_75": m_train,            # in-sample-selected (inflated ceiling)
        "oos_25": oos_m,                # TRUE holdout within IS
        "full_is": {**full_m, "post21_share": p21} if full_m else None,
        "wf_folds_pos": f"{fold_pos}/6", "wf_fold_nets": fold_nets,
        "gates": gates, "_pass": all(gates.values()),
        "pnl_champion_train": {"params": best_pnl[1], **best_pnl[2]},
    }


def main():
  t0 = time.time()
  allres = {}
  for strat in STRATS:
    print(f"\n{'='*70}\nDEEP-TUNE {strat}  ({N_TRIALS} trials/dataset, lockbox HELD)\n{'='*70}")
    allres[strat] = {}
    for inst, tf in DATASETS:
        r = run_one(strat, inst, tf)
        allres[strat][f"{inst}_{tf}"] = r
        if r.get("no_champion"):
            print(f"  {inst} {tf}: no realism-gated champion ({r['n_valid']} valid)")
            continue
        tr, oos, full = r["train_75"], r["oos_25"], r["full_is"]
        print(f"  {inst} {tf}: TRAIN MAR={tr['mar']:.2f}/PF{tr['pf']:.2f} -> "
              f"OOS MAR={oos['mar'] if oos else 'na'}/PF{oos['pf'] if oos else 'na'}/n{oos['n'] if oos else 0} "
              f"| fullIS MAR={full['mar'] if full else 'na'} p21={full['post21_share'] if full else 'na'}% "
              f"| WF={r['wf_folds_pos']} | PASS={r['_pass']}")
        print(f"          champ: {r['champion_params']}")
    fn = OUT / ("r13_deeptune_" + "_".join(s.replace("_1_0.py","") for s in STRATS) + ".json")
    fn.write_text(json.dumps(allres, indent=1, default=str), encoding="utf-8")   # incremental after each strat
    print(f"  [saved {fn.name} after {strat}]")
  print(f"\nDONE  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

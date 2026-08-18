"""BATTERY T -- is the shallow-limit PROFIT-FACTOR gain statistically real?

This is the test the whole adoption rests on. The argument for limit 0.50 was never "it
makes more dollars" (you can always make more dollars by risking more). It was that PROFIT
FACTOR rises -- 1.332 -> 1.401 -- and profit factor is scale-invariant, so it cannot be
manufactured by taking more risk. That argument is only worth anything if the PF gain is
bigger than sampling noise.

Battery S just showed that max drawdown at this sample size is so noisy its 95% CI is
WIDER than the statistic itself ($72-83k CI on a ~$50-62k observed DD), which makes net/DD
close to a coin flip as a discriminator. So before trusting PF, measure PF's noise the
same way, on the same data. If PF turns out to be equally noisy, the adoption argument is
no stronger than the net/DD argument it replaced, and I should say so.

METHOD: paired block bootstrap over TRADE-EXIT DAYS (block = 20 trading days, 5,000
resamples, fixed seed). Every level sees the identical resampled day order, so the
comparison is paired and the difference isolates the limit depth. Trade-level PnL is kept
(not aggregated to daily net) because profit factor needs gross wins and gross losses
separately -- summing a day first would cancel a win against a loss and inflate PF.

Reported for 0.50 vs 0.00 (the certified control) and, as a robustness echo, 0.20 vs 0.00:
  - PF difference: mean, 95% CI, win rate, and whether the CI straddles zero
  - the same for LOCKBOX profit factor, computed on the untouched final year only
  - a DISCRIMINATING-POWER comparison: what fraction of resamples preserves the observed
    ordering, for PF versus net/DD, so the project knows which gate to trust in future.
"""
import sys
import json
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies.ENGUQ_1M_ETH_LIM_1_0 import run_backtest         # noqa: E402

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)
LEVELS = [0.00, 0.20, 0.50]
BLOCK, N_BOOT, SEED = 20, 5000, 42

OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15"
       r"\scratchpad\lim_pf_test.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def trades_by_day(limit_atr):
    """dict: exit-date -> array of trade dollar PnLs (trade-level, never pre-summed)."""
    res = run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                       return_trades=True, limit_atr=limit_atr, **CERT)
    tr = res["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in tr]).tz_localize(None).normalize()
    by = defaultdict(list)
    lb_by = defaultdict(list)
    lbmask = ent >= pd.Timestamp(LB_START)
    for k, pnl in enumerate(d):
        by[ext[k]].append(pnl)
        if lbmask[k]:
            lb_by[ext[k]].append(pnl)
    return ({k: np.array(vv) for k, vv in by.items()},
            {k: np.array(vv) for k, vv in lb_by.items()})


print("building trade sets ...", flush=True)
full, lbox = {}, {}
for L in LEVELS:
    full[L], lbox[L] = trades_by_day(L)
    print(f"  limit {L:.2f}: {sum(len(x) for x in full[L].values())} trades, "
          f"{sum(len(x) for x in lbox[L].values())} in lockbox", flush=True)

all_days = sorted(set().union(*[set(dd.keys()) for dd in full.values()]))
lb_days = sorted(set().union(*[set(dd.keys()) for dd in lbox.values()]))
print(f"  {len(all_days)} exit-days full, {len(lb_days)} exit-days lockbox\n", flush=True)


def pf_of(daymap, days):
    w = s = 0.0
    for dd in days:
        a = daymap.get(dd)
        if a is None:
            continue
        w += a[a > 0].sum()
        s += -a[a < 0].sum()
    return (w / s) if s > 0 else float("nan")


def netdd_of(daymap, days):
    seq = np.array([daymap.get(dd, np.zeros(0)).sum() for dd in days])
    net = float(seq.sum())
    cum = np.cumsum(seq)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    return (net / dd) if dd else float("nan")


obs = {L: dict(pf=pf_of(full[L], all_days), lb_pf=pf_of(lbox[L], lb_days),
               net_dd=netdd_of(full[L], all_days)) for L in LEVELS}
for L in LEVELS:
    print(f"observed limit {L:.2f}:  PF={obs[L]['pf']:.4f}  LB PF={obs[L]['lb_pf']:.4f}  "
          f"net/DD={obs[L]['net_dd']:.2f}")

rng = np.random.default_rng(SEED)


def boot_days(days, n_boot):
    n = len(days)
    nb = int(np.ceil(n / BLOCK))
    outs = []
    for _ in range(n_boot):
        starts = rng.integers(0, max(n - BLOCK, 1), size=nb)
        order = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]
        order = order[order < n]
        outs.append([days[j] for j in order])
    return outs


print("\nbootstrapping ...", flush=True)
samples_full = boot_days(all_days, N_BOOT)
samples_lb = boot_days(lb_days, N_BOOT)

bpf = {L: np.array([pf_of(full[L], s) for s in samples_full]) for L in LEVELS}
blb = {L: np.array([pf_of(lbox[L], s) for s in samples_lb]) for L in LEVELS}
bnd = {L: np.array([netdd_of(full[L], s) for s in samples_full]) for L in LEVELS}

res = {}
print("\n" + "=" * 76)
print("Is the PROFIT-FACTOR gain real? (paired, 5,000 block bootstraps)")
for L in (0.20, 0.50):
    for label, arrs in (("PF", bpf), ("LOCKBOX PF", blb)):
        diff = arrs[L] - arrs[0.00]
        diff = diff[~np.isnan(diff)]
        lo, hi = np.percentile(diff, [2.5, 97.5])
        frac = float((diff > 0).mean())
        straddles = bool(lo < 0 < hi)
        res[f"{label}_{L}_vs_control"] = dict(
            mean=float(diff.mean()), ci=[float(lo), float(hi)],
            frac_positive=frac, straddles_zero=straddles)
        print(f"  limit {L:.2f}  {label:11s} vs control: mean={diff.mean():+.4f}  "
              f"95% CI [{lo:+.4f}, {hi:+.4f}]  wins {frac*100:5.1f}%  "
              f"{'STRADDLES ZERO' if straddles else 'DISTINGUISHABLE'}")

print("\n" + "=" * 76)
print("Which gate discriminates? -- fraction of resamples preserving observed ordering")
print("  (observed: limit 0.50 beats control on PF, LB PF, and net dollars)")
for label, arrs in (("PF", bpf), ("LOCKBOX PF", blb), ("net/DD", bnd)):
    d = arrs[0.50] - arrs[0.00]
    d = d[~np.isnan(d)]
    frac = float((d > 0).mean())
    res[f"discrimination_{label}"] = frac
    print(f"  {label:11s}: ordering holds in {frac*100:5.1f}% of resamples")

json.dump({"observed": {str(k): v for k, v in obs.items()}, "results": res,
           "params": dict(block=BLOCK, n_boot=N_BOOT, seed=SEED)},
          open(OUT, "w"), indent=1)
print("\nSAVED ->", OUT)

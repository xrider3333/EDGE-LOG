r"""Candidate-matrix analysis (owner request 2026-09-16, "IS depth" deep dive #2, step 4).

Reads ONE build_matrix.py output (matrix_<run_id>.npz + matrix_<run_id>.json) and answers,
from that matrix ALONE (no engine calls, no market data reload):

    A1  LEARNING CURVE      -- is 15 years of tuning needed, or does it flatten sooner?
    A2  RANK PERSISTENCE    -- how long a lockbox is needed before it can RANK configs?
    A3  DESIGN BACKTEST     -- pseudo-time (tune, lockbox, future) trial of (K, L) designs
    A4  SELECTION SHRINKAGE -- how much does test/train shrink with K and with pool size?

Usage:
    python tools/wfdive/isdepth/analyze_matrix.py 299
    python tools/wfdive/isdepth/analyze_matrix.py 299 --seeds 30 --boot 1000

Output (both under _wfdive_data/isdepth/):
    analysis_<run_id>.json   -- every number below, plus methodology + sanity checks
    analysis_<run_id>.md     -- short human summary of the headline findings

------------------------------------------------------------------------------------------
DESIGN NOTES (read before trusting a number)

Core primitive: every question here reduces to "what did each candidate net inside calendar
window [t0, t1)?". The matrix stores, per config, a flat (entry_bar, entry_ns, net) trade
list from ONE warm continuous full-window backtest (build_matrix.py). This script pools ALL
configs' trades into one (ns-sorted) array once, tagged by a local config id, so ANY window's
per-config (n_trades, net, wins, losses, profit_factor) falls out of two numpy `bincount`
calls (`window_stats_batch`) -- no per-config Python loop, no re-backtesting. Windows are
assigned by ENTRY time only (hard constraint), matching augur_engine.ml_gate._sl and this
family's own validate_matrix.py.

Candidate pool: the matrix's C_total "sampler"-tagged configs (index 0..c_total-1) are ONE
continued draw of the engine's own seeded `_RandomSampler` (build_matrix.py). The run's real
per-fold search only ever saw the FIRST n_trials of them. "Pseudo-seeds" here means: subset 0
= candidates[0:n_trials] (the engine's actual seeded list); subsets 1..N-1 = uniform random
n_trials-sized subsets of the full C_total pool (numpy Generator seeded 1000+i, reproducible).
This asks "how much does it matter which n_trials-sized slice of the space the fixed seed
happened to land on", holding the space and the sampler identical to the real run.

Realism gate / min_trades: reproduces augur_engine.auto._is_real (WF_MIN_SIDE=5,
MAX_TRADE_RATE=0.015, MAX_PF=6.0) and the run's own min_trades (from the sidecar, always 30
for these runs), exactly as validate_matrix.py already verified reproduces the engine's own
fold picks 8/8 on run #299. `nbars` for the trade-rate term must be the WINDOW's own bar
count, not the full-window count (scout's explicit warning) -- this matrix does not store a
full per-bar timestamp array (only per-TRADE entry/exit bars+timestamps), so nbars for an
arbitrary calendar window is ESTIMATED as `bars_per_day * busday_count(t0, t1)`, where
`bars_per_day = n_bars_full_window / busday_count(date_from, date_to)` is calibrated once per
run from its own known full-window bar count. This slightly over-counts trading days (US
holidays are not excluded, ~3.6%/yr), which makes the rate gate marginally MORE lenient than
the engine's exact bar count -- immaterial here since every family's trade rate sits well
under the 0.015 cap (documented, not hidden).

Pick rules (train window -> one config):
    R1 argmax net,  pool = realism-gated candidates meeting min_trades, else (if none gate)
       the min_trades-only pool -- this IS the engine's own `_wf_fold_row` rule, reproduced
       bit-for-bit by validate_matrix.py already.
    R2 argmax profit factor, pool = min_trades-only (the realism gate's PF<=6 cap and
       win/loss floors are deliberately NOT applied here, so R2 is a clean "rank by PF instead
       of dollars" contrast to R1, not a second copy of the engine rule).
    R3 "median-of-top-10": pool = same as R1; take the top 10 by training net from that pool;
       for each knob take the per-knob median (numeric knobs, min-max normalized to the
       knob's own [lo,hi]) or mode (categorical/bool knobs); return whichever of the 10 is
       closest (summed per-knob distance, numeric=|delta|, categorical=0/1 mismatch) to that
       reference vector -- an actual, backtested candidate representing the plateau, not a
       synthetic point.
    Trade-floor variant: R1 is also run with a PER-YEAR-SCALED floor
       `min_trades_scaled(K) = max(30, round(30 * K / 6.0))`, K_ref=6.0y being the engine's
       own rolling walk-forward training length (WF_LOCKBOX_DEEP_DIVE.md sec. 2 Q3) that the
       flat min_trades=30 gate is already calibrated against in production -- reported as
       "R1_scaled_floor" alongside the flat-floor R1.
    ORACLE = argmax net on the TEST window itself, over every built candidate (perfect
       hindsight -- the ceiling any pick rule regrets against).
    CROWN  = the matrix's "champion" row (validate.champion, chosen using the run's REAL
       ~15yr in-sample search) replayed on each pseudo-time test/future window -- a hindsight
       reference, not a rule any origin before the run's own validation date could have run.
    DEFAULTS = the strategy file's own DEFAULT_PARAMS row.

Year arithmetic uses calendar-exact `pandas.DateOffset(years=K)` / `(months=round(12*L))` on
the tz-aware (US/Eastern) date_from/date_to Timestamps already used by build_matrix.py /
validate_matrix.py -- not a fixed 365.25-day approximation.

NO LOOK-AHEAD: every training/tune window this script builds ends at or before the window it
is scored on begins (asserted in code at construction, counted in `sanity_checks`); every
slice is by ENTRY time.

Autocorrelation / independence: origins six months apart share years of overlapping training
data and adjacent test windows can share trending regimes, so this is ONE family's evidence,
not N independent trials -- curves report block-bootstrap-by-ORIGIN 90% CIs (resampling whole
origins, never individual trades) everywhere a spread is shown, and every "n" reported is n
origins/windows, not n trades.
"""
import argparse
import json
import os
import sys
import time

WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, WORKTREE_ROOT)
TOOLS_DIR = os.path.join(WORKTREE_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from tools.wfdive import common  # noqa: E402

OUT_DIR = os.path.join(common.DATA_DIR, "isdepth")

# ── engine constants reproduced (augur_engine/auto.py _is_real; validate_matrix.py) ────
WF_MIN_SIDE = 5
MAX_TRADE_RATE = 0.015
MAX_PF = 6.0

# ── analysis constants ──────────────────────────────────────────────────────────────
KREF_YEARS_FOR_TRADE_FLOOR = 6.0     # engine's own rolling WF training length reference
LEARNING_KS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14]
COMMON_ORIGIN_K_CUTOFF = 8           # "common origin set where K<=8 all exist"
A1_TEST_LENS = [1, 2]                # years
A2_LENS = [0.5, 1, 2, 3, 4, 5]       # years
A3_K = [2, 3, 5, 8, "all"]
A3_L = [1, 2, 3]                     # years
A4_POOL_SIZES = [50, 100, 300, 1000]
A4_REF_K = 6                         # holds K fixed at the engine's own reference length
ORIGIN_STEP_MONTHS = 6
N_BOOT = 1000
CI = 0.90


# ═══════════════════════════════════════════════════════════════════════════════════
# Loading + the one shared per-window primitive
# ═══════════════════════════════════════════════════════════════════════════════════

def load_matrix(run_id):
    import numpy as np
    npz_path = os.path.join(OUT_DIR, f"matrix_{run_id}.npz")
    json_path = os.path.join(OUT_DIR, f"matrix_{run_id}.json")
    z = np.load(npz_path)
    with open(json_path, "r", encoding="utf-8") as f:
        side = json.load(f)
    return z, side


def build_pool(z, side):
    """Pool every built config's trades into one ns-sorted array, tagged by a LOCAL id:
    0..c_total-1 = the sampler candidate pool (in draw order); c_total = champion;
    c_total+1 = default. One pass, reused by every window query in this script."""
    import numpy as np
    c_total = side["c_total"]
    champ_idx = side["champion_index"]
    def_idx = side["default_index"]
    n_built = len(side["configs"])
    if n_built < side["n_configs_total"]:
        raise SystemExit(f"run #{side['run_id']}: matrix incomplete ({n_built}/"
                          f"{side['n_configs_total']} configs built) -- finish the build first")
    off = z["offsets"]
    cfg_order = list(range(c_total)) + [champ_idx, def_idx]
    ns_parts, net_parts, cfg_parts, bar_parts = [], [], [], []
    for local_id, cfg_idx in enumerate(cfg_order):
        a, b = int(off[cfg_idx]), int(off[cfg_idx + 1])
        if b <= a:
            continue
        ns_parts.append(z["entry_ns"][a:b])
        net_parts.append(z["net"][a:b])
        bar_parts.append(z["entry_bar"][a:b])
        cfg_parts.append(np.full(b - a, local_id, dtype=np.int32))
    ns = np.concatenate(ns_parts)
    net = np.concatenate(net_parts)
    cfg = np.concatenate(cfg_parts)
    bar = np.concatenate(bar_parts)
    order = np.argsort(ns, kind="mergesort")
    return {
        "ns": ns[order], "net": net[order], "cfg": cfg[order], "bar": bar[order],
        "n_pool": c_total, "champ_local": c_total, "default_local": c_total + 1,
        "n_local": c_total + 2,
    }


def window_stats_batch(pool, t0_ns, t1_ns):
    """Per-LOCAL-id (n_trades, net, wins, losses, profit_factor) for entries in [t0,t1).
    One searchsorted + a handful of bincounts -- O(trades in window), not O(n_configs)."""
    import numpy as np
    ns = pool["ns"]
    lo = int(np.searchsorted(ns, t0_ns, side="left"))
    hi = int(np.searchsorted(ns, t1_ns, side="left"))
    n_local = pool["n_local"]
    if hi <= lo:
        z = np.zeros(n_local)
        return {"n_trades": z.astype(np.int64), "net": z.copy(), "wins": z.astype(np.int64),
                "losses": z.astype(np.int64), "pf": z.copy(), "t0_ns": t0_ns, "t1_ns": t1_ns}
    cfg = pool["cfg"][lo:hi]
    net = pool["net"][lo:hi]
    n_trades = np.bincount(cfg, minlength=n_local)
    net_sum = np.bincount(cfg, weights=net, minlength=n_local)
    win_mask = net > 0
    loss_mask = net < 0
    wins = np.bincount(cfg[win_mask], minlength=n_local)
    losses = np.bincount(cfg[loss_mask], minlength=n_local)
    gross_win = np.bincount(cfg[win_mask], weights=net[win_mask], minlength=n_local)
    gross_loss = np.bincount(cfg[loss_mask], weights=-net[loss_mask], minlength=n_local)
    pf = np.where(gross_loss > 1e-9, gross_win / np.maximum(gross_loss, 1e-12),
                  np.where(gross_win > 0, np.inf, 0.0))
    return {"n_trades": n_trades, "net": net_sum, "wins": wins, "losses": losses, "pf": pf,
            "t0_ns": t0_ns, "t1_ns": t1_ns}


class NBars:
    """nbars(t0,t1) estimate for the realism gate's trade-rate term -- see module docstring."""

    def __init__(self, side):
        import numpy as np
        import pandas as pd
        d0 = pd.Timestamp(side["date_from"]).date()
        d1 = pd.Timestamp(side["date_to"]).date()
        full_days = int(np.busday_count(d0, d1))
        self.bars_per_day = side["n_bars"] / max(1, full_days)
        self.full_days = full_days

    def __call__(self, t0_ts, t1_ts):
        import numpy as np
        d0, d1 = t0_ts.date(), t1_ts.date()
        if d1 <= d0:
            return 1.0
        days = int(np.busday_count(d0, d1))
        return max(1.0, self.bars_per_day * days)


# ═══════════════════════════════════════════════════════════════════════════════════
# Calendar helpers (tz-aware, calendar-exact; ns for window_stats_batch)
# ═══════════════════════════════════════════════════════════════════════════════════

def ts(date_str):
    import pandas as pd
    return pd.Timestamp(date_str, tz="US/Eastern")


def add_years(t, years):
    import pandas as pd
    if isinstance(years, (int, float)) and float(years).is_integer():
        return t + pd.DateOffset(years=int(years))
    return t + pd.DateOffset(months=round(12 * years))


def origins_every_6mo(date_from_ts, date_to_ts):
    import pandas as pd
    return list(pd.date_range(start=date_from_ts, end=date_to_ts,
                               freq=pd.DateOffset(months=ORIGIN_STEP_MONTHS)))


# ═══════════════════════════════════════════════════════════════════════════════════
# Candidate pool bookkeeping: pseudo-seed subsets, param vectors for R3
# ═══════════════════════════════════════════════════════════════════════════════════

def seed_subset(seed_i, n_trials, c_total, seed_base=1000):
    import numpy as np
    if seed_i == 0:
        return np.arange(min(n_trials, c_total))
    rng = np.random.default_rng(seed_base + seed_i)
    return rng.choice(c_total, size=min(n_trials, c_total), replace=False)


def build_param_matrix(configs, pkeys, space):
    """Normalized (n_sampler, n_knobs) matrix for R3's per-knob median/mode distance.
    Numeric knobs -> min-max normalized to the space's own [lo,hi]; categorical/bool -> raw
    index into the space's own option list (distance handled specially, see pick_R3)."""
    import numpy as np
    n = len(configs)
    kinds = []
    mat = np.zeros((n, len(pkeys)))
    for j, k in enumerate(pkeys):
        sp = space[k]
        if sp[0] == "cat":
            opts = list(sp[1])
            kinds.append(("cat", opts))
            for i, c in enumerate(configs):
                v = c["params"].get(k)
                mat[i, j] = opts.index(v) if v in opts else -1
        else:
            lo, hi = float(sp[1]), float(sp[2])
            rng = (hi - lo) if hi > lo else 1.0
            kinds.append(("num", lo, hi))
            for i, c in enumerate(configs):
                mat[i, j] = (float(c["params"].get(k, lo)) - lo) / rng
    return mat, kinds


# ═══════════════════════════════════════════════════════════════════════════════════
# Pick rules (all operate on a `stats` dict from window_stats_batch + a candidate subset
# of LOCAL ids in [0, c_total) )
# ═══════════════════════════════════════════════════════════════════════════════════

def _gated_and_recs(stats, subset, nbars, min_trades):
    import numpy as np
    trades = stats["n_trades"][subset]
    recs = subset[trades >= min_trades]
    if recs.size == 0:
        return recs, recs
    rate = stats["n_trades"][recs] / max(nbars, 1.0)
    real = ((stats["wins"][recs] >= WF_MIN_SIDE) & (stats["losses"][recs] >= WF_MIN_SIDE)
            & (rate <= MAX_TRADE_RATE) & (stats["pf"][recs] <= MAX_PF))
    return recs, recs[real]


def pick_R1(stats, subset, nbars, min_trades):
    import numpy as np
    recs, gated = _gated_and_recs(stats, subset, nbars, min_trades)
    pool = gated if gated.size else recs
    if pool.size == 0:
        return None, 0, False
    best = pool[int(np.argmax(stats["net"][pool]))]
    return int(best), int(pool.size), bool(gated.size)


def pick_R2(stats, subset, nbars, min_trades):
    """argmax PF, pool = min_trades floor ONLY (no realism gate) -- see module docstring."""
    import numpy as np
    trades = stats["n_trades"][subset]
    recs = subset[trades >= min_trades]
    if recs.size == 0:
        return None, 0
    pf = stats["pf"][recs]
    net = stats["net"][recs]
    order = np.lexsort((-net, -pf))
    return int(recs[order[0]]), int(recs.size)


def pick_R3(stats, subset, nbars, min_trades, param_mat, kinds):
    import numpy as np
    recs, gated = _gated_and_recs(stats, subset, nbars, min_trades)
    pool = gated if gated.size else recs
    if pool.size == 0:
        return None, 0
    k = min(10, pool.size)
    top = pool[np.argsort(-stats["net"][pool])[:k]]
    rows = param_mat[top]
    ref = np.zeros(rows.shape[1])
    for j, kind in enumerate(kinds):
        if kind[0] == "num":
            ref[j] = np.median(rows[:, j])
        else:
            vals, counts = np.unique(rows[:, j], return_counts=True)
            ref[j] = vals[int(np.argmax(counts))]
    dist = np.zeros(k)
    for j, kind in enumerate(kinds):
        if kind[0] == "num":
            dist += np.abs(rows[:, j] - ref[j])
        else:
            dist += (rows[:, j] != ref[j]).astype(float)
    best = top[int(np.argmin(dist))]
    return int(best), int(pool.size)


def min_trades_scaled(K, base=30, kref=KREF_YEARS_FOR_TRADE_FLOOR):
    return max(base, round(base * (K / kref)))


# ═══════════════════════════════════════════════════════════════════════════════════
# Stats helpers
# ═══════════════════════════════════════════════════════════════════════════════════

def block_bootstrap_ci(values, n_boot=N_BOOT, ci=CI, seed=123):
    import numpy as np
    v = np.asarray([x for x in values if x is not None and not (isinstance(x, float) and np.isnan(x))],
                    dtype=float)
    n = v.size
    if n == 0:
        return {"median": None, "lo": None, "hi": None, "n": 0}
    if n == 1:
        return {"median": float(v[0]), "lo": float(v[0]), "hi": float(v[0]), "n": 1}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boots = np.median(v[idx], axis=1)
    lo = float(np.percentile(boots, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boots, (1 + ci) / 2 * 100))
    return {"median": float(np.median(v)), "lo": lo, "hi": hi, "n": int(n)}


def pf_or_none(x):
    import math
    if x is None:
        return None
    if math.isinf(x):
        return "inf"
    return float(x)


def clean(x):
    """Recursively make a structure JSON-safe: numpy scalars -> python, inf -> 'inf'."""
    import numpy as np
    import math
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        x = float(x)
    if isinstance(x, float):
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        if math.isnan(x):
            return None
        return x
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# ═══════════════════════════════════════════════════════════════════════════════════
# No-look-ahead bookkeeping
# ═══════════════════════════════════════════════════════════════════════════════════

_LOOKAHEAD_CHECKS = {"n_checked": 0, "violations": []}


def assert_no_lookahead(train_end_ns, test_start_ns, label):
    _LOOKAHEAD_CHECKS["n_checked"] += 1
    if train_end_ns > test_start_ns:
        _LOOKAHEAD_CHECKS["violations"].append(
            {"label": label, "train_end_ns": int(train_end_ns), "test_start_ns": int(test_start_ns)})


# ═══════════════════════════════════════════════════════════════════════════════════
# A1 -- learning curve
# ═══════════════════════════════════════════════════════════════════════════════════

def run_A1(pool, side, nbars_fn, param_mat, kinds, n_seeds, n_trials, c_total, min_trades_flat):
    import numpy as np
    from scipy.stats import rankdata
    date_from, date_to = ts(side["date_from"]), ts(side["date_to"])
    origins = origins_every_6mo(date_from, date_to)

    # test windows: cache by (origin_idx, test_len) -- shared across K and pick rules
    test_cache = {}
    for oi, o in enumerate(origins):
        for tl in A1_TEST_LENS:
            t1 = add_years(o, tl)
            if t1 > date_to:
                continue
            st = window_stats_batch(pool, o.value, t1.value)
            rank_pct = 100.0 * rankdata(st["net"][:c_total], method="average") / c_total
            oracle_local = int(np.argmax(st["net"][:c_total]))
            test_cache[(oi, tl)] = {
                "t0": o, "t1": t1, "stats": st, "rank_pct": rank_pct, "oracle_local": oracle_local,
                "oracle_net": float(st["net"][oracle_local]),
                "defaults_net": float(st["net"][pool["default_local"]]),
                "defaults_pf": pf_or_none(st["pf"][pool["default_local"]]),
                "crown_net": float(st["net"][pool["champ_local"]]),
                "crown_pf": pf_or_none(st["pf"][pool["champ_local"]]),
            }

    cells = []  # one row per (origin, K, test_len, rule)
    prev_pick_seed0 = {}  # (oi, tl, rule) -> params dict, tracked across K ascending

    for oi, o in enumerate(origins):
        for K in LEARNING_KS:
            t0 = add_years(o, -K)
            if t0 < date_from:
                continue
            train_stats = window_stats_batch(pool, t0.value, o.value)
            mt_flat = min_trades_flat
            mt_scaled = min_trades_scaled(K)

            for tl in A1_TEST_LENS:
                key = (oi, tl)
                if key not in test_cache:
                    continue
                tc = test_cache[key]
                assert_no_lookahead(o.value, tc["t0"].value, f"A1 origin={o.date()} K={K} tl={tl}")

                for rule_name, mt in (("R1", mt_flat), ("R1_scaled_floor", mt_scaled),
                                      ("R2", mt_flat), ("R3", mt_flat)):
                    seed_picks = []
                    for si in range(n_seeds):
                        subset = seed_subset(si, n_trials, c_total)
                        if rule_name in ("R1", "R1_scaled_floor"):
                            picked, pool_n, gated = pick_R1(train_stats, subset, nbars_fn(t0, o), mt)
                        elif rule_name == "R2":
                            picked, pool_n = pick_R2(train_stats, subset, nbars_fn(t0, o), mt)
                            gated = None
                        else:
                            picked, pool_n = pick_R3(train_stats, subset, nbars_fn(t0, o), mt,
                                                      param_mat, kinds)
                            gated = None
                        if picked is None:
                            continue
                        test_net = float(tc["stats"]["net"][picked])
                        test_pf = pf_or_none(tc["stats"]["pf"][picked])
                        test_trades = int(tc["stats"]["n_trades"][picked])
                        pct = float(tc["rank_pct"][picked])
                        oracle_net = tc["oracle_net"]
                        regret_abs = (oracle_net - test_net) / tl
                        regret_rel = (None if abs(oracle_net) < 1e-9 else
                                      100.0 * (oracle_net - test_net) / abs(oracle_net))
                        seed_picks.append({
                            "seed": si, "picked_local": picked, "train_pool_n": pool_n,
                            "train_gated": gated, "test_net_per_yr": test_net / tl,
                            "test_pf": test_pf, "test_trades": test_trades, "test_pct": pct,
                            "regret_abs_per_yr": regret_abs, "regret_rel_pct": regret_rel,
                        })
                    if not seed_picks:
                        cells.append({"origin": str(o.date()), "K": K, "test_len": tl,
                                      "rule": rule_name, "n_seeds_ok": 0})
                        continue
                    pcts = [p["test_pct"] for p in seed_picks]
                    pfs = [p["test_pf"] for p in seed_picks if isinstance(p["test_pf"], float)]
                    nets = [p["test_net_per_yr"] for p in seed_picks]
                    regrets = [p["regret_rel_pct"] for p in seed_picks if p["regret_rel_pct"] is not None]
                    seed0 = seed_picks[0]
                    pk = (oi, tl, rule_name)
                    prev_params = prev_pick_seed0.get(pk)
                    seed0_params = None
                    cfgs = side["configs"]
                    if seed0["picked_local"] < c_total:
                        seed0_params = cfgs[seed0["picked_local"]]["params"]
                    changed = (prev_params is not None and seed0_params is not None
                               and prev_params != seed0_params)
                    if seed0_params is not None:
                        prev_pick_seed0[pk] = seed0_params
                    cells.append({
                        "origin": str(o.date()), "K": K, "test_len": tl, "rule": rule_name,
                        "n_seeds_ok": len(seed_picks),
                        "seed0_picked_local": seed0["picked_local"],
                        "seed0_train_pool_n": seed0["train_pool_n"],
                        "seed0_train_gated": seed0["train_gated"],
                        "seed0_test_pct": seed0["test_pct"],
                        "seed0_test_pf": seed0["test_pf"],
                        "seed0_test_net_per_yr": seed0["test_net_per_yr"],
                        "seed0_pick_changed_vs_prev_K": changed if prev_params is not None else None,
                        "median_test_pct": float(np.median(pcts)),
                        "p10_test_pct": float(np.percentile(pcts, 10)),
                        "p90_test_pct": float(np.percentile(pcts, 90)),
                        "median_test_pf": (float(np.median(pfs)) if pfs else None),
                        "median_test_net_per_yr": float(np.median(nets)),
                        "median_regret_rel_pct": (float(np.median(regrets)) if regrets else None),
                        "defaults_test_net_per_yr": tc["defaults_net"] / tl,
                        "defaults_test_pf": tc["defaults_pf"],
                        "crown_test_net_per_yr": tc["crown_net"] / tl,
                        "crown_test_pf": tc["crown_pf"],
                        "oracle_test_net_per_yr": tc["oracle_net"] / tl,
                    })

    # ── curves: median test_pct / test_pf vs K, block-bootstrap-by-origin 90% CI ──
    curves = {}
    for variant in ("common_origin_set", "all_origins_per_K"):
        curves[variant] = {}
        for rule_name in ("R1", "R1_scaled_floor", "R2", "R3"):
            curves[variant][rule_name] = {}
            for tl in A1_TEST_LENS:
                # which origins are eligible for this variant?
                sub = [c for c in cells if c["rule"] == rule_name and c["test_len"] == tl
                       and c.get("n_seeds_ok", 0) > 0]
                if variant == "common_origin_set":
                    origins_with_all_ks = None
                    by_origin = {}
                    for c in sub:
                        by_origin.setdefault(c["origin"], set()).add(c["K"])
                    needed = set(k for k in LEARNING_KS if k <= COMMON_ORIGIN_K_CUTOFF)
                    eligible_origins = {o for o, ks in by_origin.items() if needed.issubset(ks)}
                    sub = [c for c in sub if c["origin"] in eligible_origins]
                curves[variant][rule_name][tl] = {}
                for K in LEARNING_KS:
                    ksub = [c for c in sub if c["K"] == K]
                    if variant == "common_origin_set" and K > COMMON_ORIGIN_K_CUTOFF:
                        continue
                    pct_ci = block_bootstrap_ci([c["median_test_pct"] for c in ksub])
                    pf_vals = [c["median_test_pf"] for c in ksub if c["median_test_pf"] is not None]
                    pf_ci = block_bootstrap_ci(pf_vals)
                    regret_ci = block_bootstrap_ci([c["median_regret_rel_pct"] for c in ksub
                                                     if c["median_regret_rel_pct"] is not None])
                    changed_flags = [c["seed0_pick_changed_vs_prev_K"] for c in ksub
                                     if c["seed0_pick_changed_vs_prev_K"] is not None]
                    curves[variant][rule_name][tl][K] = {
                        "n_origins": len(ksub), "test_pct": pct_ci, "test_pf": pf_ci,
                        "regret_rel_pct": regret_ci,
                        "frac_pick_changed_vs_prev_K": (float(np.mean(changed_flags))
                                                         if changed_flags else None),
                    }

    # ── narrative: where does the curve flatten? does the longest K hurt? ──
    narrative = {}
    for rule_name in ("R1", "R3"):
        for tl in A1_TEST_LENS:
            curve = curves["all_origins_per_K"][rule_name][tl]
            ks_present = sorted(k for k in LEARNING_KS if curve.get(k, {}).get("n_origins", 0) >= 3)
            flatten_k = None
            for k in ks_present:
                rest = [curve[k2]["test_pct"]["median"] for k2 in ks_present if k2 >= k
                        and curve[k2]["test_pct"]["median"] is not None]
                base = curve[k]["test_pct"]["median"]
                if base is None or len(rest) < 2:
                    continue
                if all(abs(r - base) <= 3.0 for r in rest):
                    flatten_k = k
                    break
            longest_k = ks_present[-1] if ks_present else None
            plateau_ks = [k for k in ks_present if flatten_k and k >= flatten_k and k != longest_k]
            plateau_median = (float(np.median([curve[k]["test_pct"]["median"] for k in plateau_ks]))
                               if plateau_ks else None)
            longest_val = (curve[longest_k]["test_pct"]["median"] if longest_k else None)
            long_k_hurts = (plateau_median is not None and longest_val is not None
                             and longest_val < plateau_median - 3.0)
            narrative[f"{rule_name}_testlen{tl}"] = {
                "flattens_at_K": flatten_k, "longest_K_present": longest_k,
                "plateau_median_test_pct": plateau_median,
                "longest_K_median_test_pct": longest_val,
                "longest_K_hurts": long_k_hurts,
            }

    return {"cells": cells, "curves": curves, "narrative": narrative, "n_origins_total": len(origins)}


# ═══════════════════════════════════════════════════════════════════════════════════
# A2 -- rank persistence vs window length
# ═══════════════════════════════════════════════════════════════════════════════════

def run_A2(pool, side, c_total):
    import numpy as np
    from scipy.stats import spearmanr, rankdata
    date_from, date_to = ts(side["date_from"]), ts(side["date_to"])

    out = {}
    for L in A2_LENS:
        # partition the FULL span into consecutive, non-overlapping L-year windows
        edges = [date_from]
        while True:
            nxt = add_years(edges[-1], L)
            if nxt > date_to:
                break
            edges.append(nxt)
        windows = []
        for i in range(len(edges) - 1):
            st = window_stats_batch(pool, edges[i].value, edges[i + 1].value)
            windows.append({"t0": edges[i], "t1": edges[i + 1], "stats": st})

        pair_recs = []
        for i in range(len(windows) - 1):
            A, B = windows[i], windows[i + 1]
            assert_no_lookahead(A["t1"].value, B["t0"].value, f"A2 L={L} pair {i}")
            netA, netB = A["stats"]["net"][:c_total], B["stats"]["net"][:c_total]
            pfA, pfB = A["stats"]["pf"][:c_total], B["stats"]["pf"][:c_total]
            has_trades = (A["stats"]["n_trades"][:c_total] > 0) & (B["stats"]["n_trades"][:c_total] > 0)
            if has_trades.sum() < 10:
                continue
            rho_net, _ = spearmanr(netA[has_trades], netB[has_trades])
            rho_pf, _ = spearmanr(pfA[has_trades], pfB[has_trades])

            order_A = np.argsort(-netA)
            n_top_decile = max(1, c_total // 10)
            top_decile = order_A[:n_top_decile]
            top_decile = top_decile[np.isin(top_decile, np.where(has_trades)[0])]
            best_A = order_A[0]
            rankB_pct = 100.0 * rankdata(netB, method="average") / c_total

            shortlist = order_A[:20]
            shortlist = shortlist[np.isin(shortlist, np.where(has_trades)[0])]
            rho_short_net = rho_short_pf = None
            if shortlist.size >= 5:
                rho_short_net, _ = spearmanr(netA[shortlist], netB[shortlist])
                rho_short_pf, _ = spearmanr(pfA[shortlist], pfB[shortlist])

            pair_recs.append({
                "A_start": str(A["t0"].date()), "B_start": str(B["t0"].date()),
                "n_candidates": int(has_trades.sum()),
                "rho_net": float(rho_net) if rho_net is not None else None,
                "rho_pf": float(rho_pf) if rho_pf is not None else None,
                "rho_shortlist_net": (float(rho_short_net) if rho_short_net is not None else None),
                "rho_shortlist_pf": (float(rho_short_pf) if rho_short_pf is not None else None),
                "top_decile_B_pct_mean": (float(np.mean(rankB_pct[top_decile]))
                                           if top_decile.size else None),
                "best_A_B_pct": float(rankB_pct[best_A]),
            })

        out[str(L)] = {
            "n_pairs": len(pair_recs),
            "rho_net": block_bootstrap_ci([p["rho_net"] for p in pair_recs]),
            "rho_pf": block_bootstrap_ci([p["rho_pf"] for p in pair_recs]),
            "rho_shortlist_net": block_bootstrap_ci([p["rho_shortlist_net"] for p in pair_recs
                                                      if p["rho_shortlist_net"] is not None]),
            "rho_shortlist_pf": block_bootstrap_ci([p["rho_shortlist_pf"] for p in pair_recs
                                                     if p["rho_shortlist_pf"] is not None]),
            "top_decile_B_pct": block_bootstrap_ci([p["top_decile_B_pct_mean"] for p in pair_recs]),
            "best_A_B_pct": block_bootstrap_ci([p["best_A_B_pct"] for p in pair_recs]),
            "pairs": pair_recs,
        }
    return out


# ═══════════════════════════════════════════════════════════════════════════════════
# A3 -- design backtest (pseudo-time)
# ═══════════════════════════════════════════════════════════════════════════════════

def run_A3(pool, side, nbars_fn, n_seeds, n_trials, c_total, min_trades_flat):
    import numpy as np
    from scipy.stats import spearmanr
    date_from, date_to = ts(side["date_from"]), ts(side["date_to"])
    origins = origins_every_6mo(date_from, date_to)

    def train_start(t_end, K):
        return date_from if K == "all" else add_years(t_end, -K)

    designs = {}
    per_design_t_sets = {}

    for K in A3_K:
        for L in A3_L:
            recs = []
            for t in origins:
                lb0 = add_years(t, -L)
                tr0 = train_start(lb0, K)
                if tr0 < date_from:
                    continue
                fut2 = add_years(t, 2)
                if fut2 > date_to:
                    continue
                assert_no_lookahead(lb0.value, lb0.value, f"A3 tune-end==lockbox-start K={K} L={L}")
                tune_stats = window_stats_batch(pool, tr0.value, lb0.value)
                lb_stats = window_stats_batch(pool, lb0.value, t.value)
                assert_no_lookahead(t.value, t.value, f"A3 lockbox-end==future-start K={K} L={L}")
                fut1_stats = window_stats_batch(pool, t.value, add_years(t, 1).value)
                fut2_stats = window_stats_batch(pool, t.value, fut2.value)
                retr0 = train_start(t, K)
                retune_stats = (window_stats_batch(pool, retr0.value, t.value)
                                if retr0 >= date_from else None)

                per_seed = []
                for si in range(n_seeds):
                    subset = seed_subset(si, n_trials, c_total)
                    picked, pool_n, gated = pick_R1(tune_stats, subset, nbars_fn(tr0, lb0), min_trades_flat)
                    if picked is None:
                        continue
                    lb_net = float(lb_stats["net"][picked])
                    lb_pf = lb_stats["pf"][picked]
                    lb_trades = int(lb_stats["n_trades"][picked])
                    passed = bool(lb_net > 0 and lb_pf >= 1.0 and lb_trades > 0)
                    f1_net, f2_net = float(fut1_stats["net"][picked]), float(fut2_stats["net"][picked])
                    f1_pf, f2_pf = pf_or_none(fut1_stats["pf"][picked]), pf_or_none(fut2_stats["pf"][picked])
                    rec = {"seed": si, "picked_local": picked, "lb_net": lb_net,
                           "lb_pf": pf_or_none(lb_pf), "lb_trades": lb_trades, "passed": passed,
                           "fut1_net": f1_net, "fut1_pf": f1_pf,
                           "fut2_net": f2_net, "fut2_pf": f2_pf}
                    if passed and retune_stats is not None:
                        r_picked, r_pool_n, r_gated = pick_R1(retune_stats, subset, nbars_fn(retr0, t),
                                                               min_trades_flat)
                        if r_picked is not None:
                            rec["retuned_local"] = r_picked
                            rec["retuned_fut1_net"] = float(fut1_stats["net"][r_picked])
                            rec["retuned_fut1_pf"] = pf_or_none(fut1_stats["pf"][r_picked])
                            rec["retuned_fut2_net"] = float(fut2_stats["net"][r_picked])
                            rec["retuned_fut2_pf"] = pf_or_none(fut2_stats["pf"][r_picked])
                    per_seed.append(rec)
                if per_seed:
                    recs.append({"t": str(t.date()), "per_seed": per_seed})
            designs[f"K={K}_L={L}"] = recs
            per_design_t_sets[f"K={K}_L={L}"] = {r["t"] for r in recs}

    common_t = set.intersection(*per_design_t_sets.values()) if per_design_t_sets else set()

    def summarize(recs, t_filter=None):
        seed0_rows = []
        all_rows = []
        for r in recs:
            if t_filter is not None and r["t"] not in t_filter:
                continue
            for rec in r["per_seed"]:
                all_rows.append(rec)
                if rec["seed"] == 0:
                    seed0_rows.append((r["t"], rec))
        n_t = len(set(r["t"] for r in recs if (t_filter is None or r["t"] in t_filter)))
        if not all_rows:
            return {"n_t": n_t, "n_rows": 0}
        passed = [x for x in all_rows if x["passed"]]
        failed = [x for x in all_rows if not x["passed"]]

        def p_future_pos(rows, horizon):
            key = f"fut{horizon}_net"
            vals = [1.0 if x[key] > 0 else 0.0 for x in rows]
            return (float(np.mean(vals)), len(vals)) if vals else (None, 0)

        out = {"n_t": n_t, "n_rows": len(all_rows), "pass_rate": float(np.mean([x["passed"] for x in all_rows]))}
        for h in (1, 2):
            p_pass, n_pass = p_future_pos(passed, h)
            p_fail, n_fail = p_future_pos(failed, h)
            out[f"p_future{h}y_pos_given_pass"] = {"p": p_pass, "n": n_pass}
            out[f"p_future{h}y_pos_given_fail"] = {"p": p_fail, "n": n_fail}
            fut_pf_passed = [x[f"fut{h}_pf"] for x in passed if isinstance(x[f"fut{h}_pf"], float)]
            out[f"median_future{h}y_pf_passed"] = (float(np.median(fut_pf_passed)) if fut_pf_passed else None)
            retuned_rows = [x for x in passed if f"retuned_fut{h}_net" in x]
            if retuned_rows:
                rvals = [1.0 if x[f"retuned_fut{h}_net"] > 0 else 0.0 for x in retuned_rows]
                out[f"p_future{h}y_pos_retuned_given_pass"] = {"p": float(np.mean(rvals)), "n": len(rvals)}
                rpf = [x[f"retuned_fut{h}_pf"] for x in retuned_rows if isinstance(x[f"retuned_fut{h}_pf"], float)]
                out[f"median_future{h}y_pf_retuned_passed"] = (float(np.median(rpf)) if rpf else None)
            else:
                out[f"p_future{h}y_pos_retuned_given_pass"] = {"p": None, "n": 0}
                out[f"median_future{h}y_pf_retuned_passed"] = None

        # seed-0 (real engine list) time series -> Spearman(lockbox PF, future PF)
        seed0_rows.sort(key=lambda x: x[0])
        lb_pf_series = [x[1]["lb_pf"] for x in seed0_rows if isinstance(x[1]["lb_pf"], float)]
        f1_pf_series = [x[1]["fut1_pf"] for x in seed0_rows if isinstance(x[1]["lb_pf"], float)
                        and isinstance(x[1]["fut1_pf"], float)]
        lb_pf_series2 = [x[1]["lb_pf"] for x in seed0_rows if isinstance(x[1]["lb_pf"], float)
                         and isinstance(x[1]["fut1_pf"], float)]
        rho = None
        if len(lb_pf_series2) >= 5:
            from scipy.stats import spearmanr
            rho, _ = spearmanr(lb_pf_series2, f1_pf_series)
            rho = float(rho)
        out["spearman_lockbox_pf_vs_future1y_pf_seed0"] = {"rho": rho, "n": len(lb_pf_series2)}

        # pseudo-seed spread: each seed's OWN pass rate over its own valid t's
        per_seed_pass = {}
        for x in all_rows:
            per_seed_pass.setdefault(x["seed"], []).append(x["passed"])
        seed_rates = [float(np.mean(v)) for v in per_seed_pass.values() if v]
        out["pseudo_seed_pass_rate_spread"] = {
            "median": float(np.median(seed_rates)) if seed_rates else None,
            "min": float(np.min(seed_rates)) if seed_rates else None,
            "max": float(np.max(seed_rates)) if seed_rates else None,
            "n_seeds": len(seed_rates),
        }
        return out

    result = {"common_t_set_size": len(common_t), "designs": {}}
    for key, recs in designs.items():
        result["designs"][key] = {
            "own_t_set": summarize(recs, t_filter=None),
            "common_t_set": summarize(recs, t_filter=common_t) if common_t else {"n_t": 0, "n_rows": 0},
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# A4 -- selection shrinkage
# ═══════════════════════════════════════════════════════════════════════════════════

def run_A4(pool, side, nbars_fn, a1_cells, n_seeds, n_trials, c_total, min_trades_flat):
    import numpy as np
    date_from, date_to = ts(side["date_from"]), ts(side["date_to"])
    origins = origins_every_6mo(date_from, date_to)

    # vs K: shrinkage = test_net_per_yr(R1, testlen=1) / train_net_per_yr(R1) -- reuse A1
    # training-window stats by recomputing train net for the seed-0 pick at each (origin,K).
    vs_K = {}
    for K in LEARNING_KS:
        ratios = []
        for o in origins:
            t0 = add_years(o, -K)
            if t0 < date_from:
                continue
            t1y = add_years(o, 1)
            if t1y > date_to:
                continue
            train_stats = window_stats_batch(pool, t0.value, o.value)
            test_stats = window_stats_batch(pool, o.value, t1y.value)
            subset = seed_subset(0, n_trials, c_total)
            picked, _, _ = pick_R1(train_stats, subset, nbars_fn(t0, o), min_trades_flat)
            if picked is None:
                continue
            train_net_per_yr = float(train_stats["net"][picked]) / K
            test_net_per_yr = float(test_stats["net"][picked]) / 1.0
            if abs(train_net_per_yr) < 1e-9:
                continue
            ratios.append(test_net_per_yr / train_net_per_yr)
        vs_K[str(K)] = block_bootstrap_ci(ratios)

    # vs pool size: hold K = A4_REF_K, vary the pseudo-seed subset SIZE M
    vs_pool = {}
    K = A4_REF_K
    for M in A4_POOL_SIZES:
        M_eff = min(M, c_total)
        ratios = []
        for o in origins:
            t0 = add_years(o, -K)
            if t0 < date_from:
                continue
            t1y = add_years(o, 1)
            if t1y > date_to:
                continue
            train_stats = window_stats_batch(pool, t0.value, o.value)
            test_stats = window_stats_batch(pool, o.value, t1y.value)
            for si in range(n_seeds):
                subset = seed_subset(si, M_eff, c_total, seed_base=5000)
                picked, _, _ = pick_R1(train_stats, subset, nbars_fn(t0, o), min_trades_flat)
                if picked is None:
                    continue
                train_net_per_yr = float(train_stats["net"][picked]) / K
                test_net_per_yr = float(test_stats["net"][picked]) / 1.0
                if abs(train_net_per_yr) < 1e-9:
                    continue
                ratios.append(test_net_per_yr / train_net_per_yr)
        vs_pool[str(M)] = block_bootstrap_ci(ratios)

    return {"vs_K_shrinkage_ratio_test_over_train": vs_K,
            "vs_pool_size_shrinkage_ratio_test_over_train": vs_pool,
            "note": "ratio = (test net/yr, 1y fwd window) / (train net/yr) for the R1 seed-0 pick; "
                    "1.0 = no shrinkage, <1 = optimism/overfitting in the training-window score, "
                    "computed on origins where both the K-year training window and a full 1y test "
                    "window fit inside the run's date_from/date_to."}


# ═══════════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════════

def main():
    global N_BOOT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id", type=int)
    ap.add_argument("--seeds", type=int, default=30, help="pseudo-seed subsets (default 30)")
    ap.add_argument("--boot", type=int, default=N_BOOT, help="bootstrap resamples for CIs")
    args = ap.parse_args()

    N_BOOT = args.boot

    common.low_priority()
    t_start = time.time()

    with common.cpu_lock(f"isdepth analyze_matrix #{args.run_id}"):
        z, side = load_matrix(args.run_id)
        print(f"[analyze_matrix] run #{args.run_id} {side['strategy']} {side['instrument']} "
              f"{side['timeframe']} -- {len(side['configs'])} configs, n_trials={side['n_trials']}, "
              f"c_total={side['c_total']}")

        pool = build_pool(z, side)
        print(f"[analyze_matrix] pooled {pool['ns'].size} trades across {pool['n_local']} configs "
              f"(incl. champion+default)")
        nbars_fn = NBars(side)
        param_mat, kinds = build_param_matrix(
            [c for c in side["configs"] if c["tag"] == "sampler"], side["pkeys"], side["space"])

        n_trials = side["n_trials"]
        c_total = side["c_total"]
        min_trades_flat = side["min_trades"]

        print("[analyze_matrix] A1 learning curve ...")
        t0 = time.time()
        a1 = run_A1(pool, side, nbars_fn, param_mat, kinds, args.seeds, n_trials, c_total, min_trades_flat)
        print(f"[analyze_matrix] A1 done in {time.time()-t0:.1f}s ({len(a1['cells'])} cells)")

        print("[analyze_matrix] A2 rank persistence ...")
        t0 = time.time()
        a2 = run_A2(pool, side, c_total)
        print(f"[analyze_matrix] A2 done in {time.time()-t0:.1f}s")

        print("[analyze_matrix] A3 design backtest ...")
        t0 = time.time()
        a3 = run_A3(pool, side, nbars_fn, args.seeds, n_trials, c_total, min_trades_flat)
        print(f"[analyze_matrix] A3 done in {time.time()-t0:.1f}s")

        print("[analyze_matrix] A4 selection shrinkage ...")
        t0 = time.time()
        a4 = run_A4(pool, side, nbars_fn, a1["cells"], args.seeds, n_trials, c_total, min_trades_flat)
        print(f"[analyze_matrix] A4 done in {time.time()-t0:.1f}s")

    runtime_s = time.time() - t_start

    out = {
        "run_id": args.run_id, "strategy": side["strategy"], "instrument": side["instrument"],
        "timeframe": side["timeframe"], "date_from": side["date_from"], "date_to": side["date_to"],
        "lockbox_from": side.get("lockbox_from"), "n_bars": side["n_bars"],
        "c_total": c_total, "n_trials": n_trials, "min_trades_flat": min_trades_flat,
        "pkeys": side["pkeys"], "n_pseudo_seeds": args.seeds, "n_boot": args.boot,
        "runtime_seconds": runtime_s,
        "methodology": {
            "nbars_estimate": f"bars_per_day({nbars_fn.bars_per_day:.4f}) * busday_count(t0,t1); "
                               f"calibrated from full window {nbars_fn.full_days} busdays / "
                               f"{side['n_bars']} bars",
            "kref_years_for_scaled_floor": KREF_YEARS_FOR_TRADE_FLOOR,
            "pick_rules": "see module docstring: R1=argmax net engine-like gate, "
                          "R1_scaled_floor=R1 with min_trades scaled by K/6y, "
                          "R2=argmax PF/min_trades-floor-only, R3=median-of-top-10 nearest-actual",
            "oracle": "argmax net on the test window itself, over all C_total candidates",
        },
        "sanity_checks": {
            "no_lookahead_checks": _LOOKAHEAD_CHECKS["n_checked"],
            "no_lookahead_violations": _LOOKAHEAD_CHECKS["violations"],
            "window_assignment": "entry-time only (window_stats_batch slices on entry_ns)",
        },
        "A1_learning_curve": a1,
        "A2_rank_persistence": a2,
        "A3_design_backtest": a3,
        "A4_selection_shrinkage": a4,
    }
    out = clean(out)

    out_path = os.path.join(OUT_DIR, f"analysis_{args.run_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"[analyze_matrix] wrote {out_path}")

    md_path = os.path.join(OUT_DIR, f"analysis_{args.run_id}.md")
    write_markdown(out, md_path)
    print(f"[analyze_matrix] wrote {md_path}")
    print(f"[analyze_matrix] TOTAL runtime {runtime_s:.1f}s; "
          f"lookahead violations: {len(_LOOKAHEAD_CHECKS['violations'])}")
    return 0


def write_markdown(out, path):
    lines = []
    lines.append(f"# Candidate-matrix analysis -- run #{out['run_id']} {out['strategy']} "
                 f"({out['instrument']} {out['timeframe']})")
    lines.append("")
    lines.append(f"Window {out['date_from']}..{out['date_to']}, lockbox from {out['lockbox_from']}, "
                 f"{out['c_total']} candidates ({out['n_trials']} in the run's own seeded list), "
                 f"{out['n_pseudo_seeds']} pseudo-seeds, runtime {out['runtime_seconds']:.0f}s.")
    lines.append("")
    viol = out["sanity_checks"]["no_lookahead_violations"]
    lines.append(f"No-look-ahead: {out['sanity_checks']['no_lookahead_checks']} window pairs checked, "
                 f"{len(viol)} violations.")
    lines.append("")
    lines.append("## A1 -- learning curve (is 15yr of tuning needed?)")
    for key, n in out["A1_learning_curve"]["narrative"].items():
        lines.append(f"- {key}: flattens at K={n['flattens_at_K']}, plateau median test-percentile "
                     f"{n['plateau_median_test_pct']}, longest K ({n['longest_K_present']}) median "
                     f"{n['longest_K_median_test_pct']}, longest-K-hurts={n['longest_K_hurts']}")
    lines.append("")
    lines.append("## A2 -- rank persistence vs window length")
    for L, d in out["A2_rank_persistence"].items():
        lines.append(f"- L={L}y: n_pairs={d['n_pairs']}, rho_net median={d['rho_net']['median']}, "
                     f"rho_pf median={d['rho_pf']['median']}, top-decile B-percentile median="
                     f"{d['top_decile_B_pct']['median']}, best-of-A B-percentile median="
                     f"{d['best_A_B_pct']['median']}")
    lines.append("")
    lines.append("## A3 -- design backtest (own t-set)")
    for key, d in out["A3_design_backtest"]["designs"].items():
        own = d["own_t_set"]
        if own.get("n_rows", 0) == 0:
            lines.append(f"- {key}: no feasible t")
            continue
        lines.append(f"- {key}: n_t={own['n_t']} pass_rate={own['pass_rate']:.2f} "
                     f"P(fut1y>0|pass)={own['p_future1y_pos_given_pass']['p']} "
                     f"P(fut1y>0|fail)={own['p_future1y_pos_given_fail']['p']} "
                     f"median_fut1y_PF|pass={own['median_future1y_pf_passed']}")
    lines.append("")
    lines.append("## A4 -- selection shrinkage (test/train net-per-year ratio)")
    lines.append("vs K:")
    for K, d in out["A4_selection_shrinkage"]["vs_K_shrinkage_ratio_test_over_train"].items():
        lines.append(f"- K={K}: median={d['median']} CI90=[{d['lo']},{d['hi']}] n={d['n']}")
    lines.append("vs pool size:")
    for M, d in out["A4_selection_shrinkage"]["vs_pool_size_shrinkage_ratio_test_over_train"].items():
        lines.append(f"- M={M}: median={d['median']} CI90=[{d['lo']},{d['hi']}] n={d['n']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

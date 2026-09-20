r"""Independent, adversarial re-computation of the IS-depth candidate-matrix headlines.

Reads ONLY matrix_<run_id>.npz + matrix_<run_id>.json (build_matrix.py output). Does NOT
import analyze_matrix.py (or any of its functions) -- every window query, gate, pick rule
and statistic below is re-implemented from the raw per-trade arrays.

Usage (from the worktree root):
    python tools/wfdive/isdepth/verify_isdepth.py 299
    python tools/wfdive/isdepth/verify_isdepth.py 299 304 314 307   # several, then cross-family
    python tools/wfdive/isdepth/verify_isdepth.py --cross            # aggregate existing verify_*.json

Output: _wfdive_data/isdepth/verify_<run_id>.json (checkpointed per section) and
        _wfdive_data/isdepth/verify_cross.json.

Sections
  V0  facts + integrity: unique configs, holding durations (how much a trade can straddle a
      window cut), timestamp order, bar-index <-> time map (an nbars estimate that does NOT
      use the analysis author's busday approximation).
  V1  learning curve, R1 (engine gate, argmax train net), seed-0 list AND the whole pool,
      K in {1,2,3,4,5,6,8,10,12,14,all}; ALL-origins-per-K and COMMON-origin (K<=8, K<=10)
      variants; paired within-origin comparisons (long K vs K=3), so era mixing across K
      cannot masquerade as a depth effect.
  V2  leak checks: (a) assignment by EXIT time; (b) training stats with trades still open
      at the cut removed; (c) how often the pick changes under (b).
  V3  pseudo-seed independence: distinct picks across the 30 subset "seeds" per cell.
  V4  rank persistence with a FIXED 1y future: Spearman(net over [t-L,t), net over [t,t+1))
      for L in {0.5,1,2,3,4,6}, same origin set for every L; plus a 10-finalist test that
      mirrors the real pipeline (top-10 by anchored training net, lockbox of length L ranks
      them, does that rank predict the next year?).
  V5  design backtest at ORIGIN level (seed 0): pass/fail of an L-year lockbox vs the next
      year, n = origins not seed-rows; the cost of freezing (tune ends L years earlier) vs
      the veto's value.
  V6  recency: tune on the last 3y vs the 3y before that vs 6y -- is it depth or recency?
  V7  shrinkage in UNITLESS terms (PF), by K.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DATA_DIR = os.path.join(WORKTREE_ROOT, "_wfdive_data", "isdepth")

WF_MIN_SIDE = 5
MAX_TRADE_RATE = 0.015
MAX_PF = 6.0

KS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14, "all"]
STEP_MONTHS = 6
N_SEEDS = 30
LS_RANK = [0.5, 1, 2, 3, 4, 6]
LS_DESIGN = [0.5, 1, 2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# time helpers
# ─────────────────────────────────────────────────────────────────────────────
def ts(s):
    import pandas as pd
    return pd.Timestamp(s, tz="US/Eastern")


def shift(t, years):
    import pandas as pd
    if years == "all":
        raise ValueError
    if float(years).is_integer():
        return t + pd.DateOffset(years=int(years))
    return t + pd.DateOffset(months=int(round(12 * years)))


def origins(t_from, t_to):
    import pandas as pd
    return list(pd.date_range(start=t_from, end=t_to, freq=pd.DateOffset(months=STEP_MONTHS)))


# ─────────────────────────────────────────────────────────────────────────────
# matrix
# ─────────────────────────────────────────────────────────────────────────────
class Matrix:
    def __init__(self, run_id):
        z = np.load(os.path.join(DATA_DIR, f"matrix_{run_id}.npz"))
        self.arr = {k: z[k] for k in z.files}          # materialize once (NpzFile re-inflates)
        with open(os.path.join(DATA_DIR, f"matrix_{run_id}.json"), "r", encoding="utf-8") as f:
            self.side = json.load(f)
        s = self.side
        if len(s["configs"]) < s["n_configs_total"]:
            raise SystemExit(f"matrix {run_id} incomplete: {len(s['configs'])}/{s['n_configs_total']}")
        self.run_id = run_id
        self.c_total = s["c_total"]
        self.n_trials = s["n_trials"]
        self.min_trades = s["min_trades"]
        self.champ = s["champion_index"]
        self.deflt = s["default_index"]
        self.t_from = ts(s["date_from"])
        self.t_to = ts(s["date_to"])
        self.lb_from = ts(s["lockbox_from"]) if s.get("lockbox_from") else None
        self.pkeys = s["pkeys"]
        self.params = [c["params"] for c in s["configs"]]
        off = self.arr["offsets"]
        # local ids: 0..c_total-1 sampler; c_total champion; c_total+1 default
        self.local_of = list(range(self.c_total)) + [self.champ, self.deflt]
        self.n_local = self.c_total + 2
        e_parts, x_parts, n_parts, c_parts, eb_parts = [], [], [], [], []
        for lid, ci in enumerate(self.local_of):
            a, b = int(off[ci]), int(off[ci + 1])
            if b <= a:
                continue
            e_parts.append(self.arr["entry_ns"][a:b])
            x_parts.append(self.arr["exit_ns"][a:b])
            n_parts.append(self.arr["net"][a:b])
            eb_parts.append(self.arr["entry_bar"][a:b])
            c_parts.append(np.full(b - a, lid, dtype=np.int32))
        e = np.concatenate(e_parts); x = np.concatenate(x_parts); n = np.concatenate(n_parts)
        c = np.concatenate(c_parts); eb = np.concatenate(eb_parts)
        o = np.argsort(e, kind="mergesort")
        self.E = {"key": e[o], "exit": x[o], "net": n[o], "cfg": c[o], "bar": eb[o]}
        o2 = np.argsort(x, kind="mergesort")
        self.X = {"key": x[o2], "net": n[o2], "cfg": c[o2]}
        # time -> bar map from the pooled trades themselves (dedup on entry_ns)
        uniq_ns, idx = np.unique(self.E["key"], return_index=True)
        self.map_ns = uniq_ns
        self.map_bar = self.E["bar"][idx]
        self.n_bars = s["n_bars"]

    def bar_at(self, t_ns):
        i = int(np.searchsorted(self.map_ns, t_ns, side="left"))
        if i >= len(self.map_ns):
            return self.n_bars
        return int(self.map_bar[i])

    def nbars(self, t0, t1):
        return max(1, self.bar_at(t1.value) - self.bar_at(t0.value))

    def stats(self, t0, t1, by="entry", drop_open_after=None):
        """Per-local-id (n, net, wins, losses, pf) for trades whose entry (or exit) is in
        [t0,t1). drop_open_after=ns: exclude trades whose EXIT is at/after that instant
        (i.e. trades still open at the cut) -- the strict no-leak training variant."""
        P = self.E if by == "entry" else self.X
        lo = int(np.searchsorted(P["key"], t0.value, side="left"))
        hi = int(np.searchsorted(P["key"], t1.value, side="left"))
        n_local = self.n_local
        if hi <= lo:
            zz = np.zeros(n_local)
            return {"n": zz.astype(int), "net": zz, "wins": zz.astype(int), "losses": zz.astype(int),
                    "pf": zz.copy(), "n_open_dropped": 0}
        cfg = P["cfg"][lo:hi]; net = P["net"][lo:hi]
        n_open = 0
        if drop_open_after is not None and by == "entry":
            keep = P["exit"][lo:hi] < drop_open_after
            n_open = int((~keep).sum())
            cfg = cfg[keep]; net = net[keep]
        n = np.bincount(cfg, minlength=n_local)
        s = np.bincount(cfg, weights=net, minlength=n_local)
        w = net > 0; l = net < 0
        wins = np.bincount(cfg[w], minlength=n_local)
        losses = np.bincount(cfg[l], minlength=n_local)
        gw = np.bincount(cfg[w], weights=net[w], minlength=n_local)
        gl = np.bincount(cfg[l], weights=-net[l], minlength=n_local)
        pf = np.where(gl > 1e-9, gw / np.maximum(gl, 1e-12), np.where(gw > 0, np.inf, 0.0))
        return {"n": n, "net": s, "wins": wins, "losses": losses, "pf": pf, "n_open_dropped": n_open}


# ─────────────────────────────────────────────────────────────────────────────
# pick rule (engine's _wf_fold_row: argmax train net over realism-gated candidates that
# clear min_trades, else over the min_trades-only set)
# ─────────────────────────────────────────────────────────────────────────────
def pick_r1(st, subset, nbars, min_trades):
    subset = np.asarray(subset)
    n = st["n"][subset]
    recs = subset[n >= min_trades]
    if recs.size == 0:
        return None, 0, 0
    rate = st["n"][recs] / max(1.0, nbars)
    real = (st["wins"][recs] >= WF_MIN_SIDE) & (st["losses"][recs] >= WF_MIN_SIDE) & \
           (rate <= MAX_TRADE_RATE) & (st["pf"][recs] <= MAX_PF)
    pool = recs[real] if real.any() else recs
    return int(pool[int(np.argmax(st["net"][pool]))]), int(recs.size), int(real.sum())


def seed_subset(i, n_trials, c_total):
    if i == 0:
        return np.arange(min(n_trials, c_total))
    rng = np.random.default_rng(1000 + i)
    return rng.choice(c_total, size=min(n_trials, c_total), replace=False)


def pct_rank(values, i):
    """percentile (0-100, average rank for ties) of values[i] within values."""
    from scipy.stats import rankdata
    r = rankdata(values, method="average")
    return float(100.0 * r[i] / len(values))


def med(v):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.median(v)) if v else None


def boot_ci(v, n_boot=2000, seed=7):
    """iid bootstrap over origins (origins are autocorrelated: this is optimistic)."""
    v = np.asarray([x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))], float)
    if v.size == 0:
        return {"median": None, "lo": None, "hi": None, "n": 0}
    if v.size == 1:
        return {"median": float(v[0]), "lo": float(v[0]), "hi": float(v[0]), "n": 1}
    rng = np.random.default_rng(seed)
    b = np.median(v[rng.integers(0, v.size, size=(n_boot, v.size))], axis=1)
    return {"median": float(np.median(v)), "lo": float(np.percentile(b, 5)),
            "hi": float(np.percentile(b, 95)), "n": int(v.size)}


def sign_test(diffs):
    """two-sided exact sign test on nonzero paired differences."""
    from scipy.stats import binomtest
    d = [x for x in diffs if x is not None and x != 0]
    if not d:
        return {"n_nonzero": 0, "n_pos": 0, "p": None}
    pos = sum(1 for x in d if x > 0)
    return {"n_nonzero": len(d), "n_pos": pos, "p": float(binomtest(pos, len(d), 0.5).pvalue)}


def fin(x):
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        if math.isinf(x):
            return "inf"
        if math.isnan(x):
            return None
        return x
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, dict):
        return {str(k): fin(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [fin(v) for v in x]
    return x


# ─────────────────────────────────────────────────────────────────────────────
# V0 facts
# ─────────────────────────────────────────────────────────────────────────────
def v0_facts(M):
    s = M.side
    def key(p):
        return json.dumps({k: p.get(k) for k in M.pkeys}, sort_keys=True, default=str)
    keys_all = [key(M.params[i]) for i in range(M.c_total)]
    keys_first = keys_all[:M.n_trials]
    hold_days = (M.arr["exit_ns"] - M.arr["entry_ns"]) / 1e9 / 86400.0
    years = (M.t_to - M.t_from).days / 365.25
    champ_n = int(M.arr["n_trades"][M.champ])
    # is the champion among the sampler draws?
    champ_key = key(M.params[M.champ])
    champ_in_first = champ_key in keys_first
    champ_in_pool = champ_key in keys_all
    # min_trades binding at K=1: eligibility fraction (seed-0 list) at each origin (1y train)
    elig = []
    for o in origins(M.t_from, M.t_to):
        t0 = o
        t1 = shift(o, 1)
        if t1 > M.t_to:
            break
        st = M.stats(t0, t1)
        elig.append(float((st["n"][:M.n_trials] >= M.min_trades).mean()))
    return {
        "strategy": s["strategy"], "instrument": s["instrument"], "timeframe": s["timeframe"],
        "date_from": s["date_from"], "date_to": s["date_to"], "lockbox_from": s.get("lockbox_from"),
        "years": round(years, 2), "c_total": M.c_total, "n_trials": M.n_trials, "min_trades": M.min_trades,
        "n_unique_configs_in_pool": len(set(keys_all)),
        "n_unique_configs_in_first_n_trials": len(set(keys_first)),
        "champion_in_first_n_trials": champ_in_first, "champion_in_pool": champ_in_pool,
        "champion_trades_full_window": champ_n,
        "champion_trades_per_year": round(champ_n / years, 1),
        "pooled_trades": int(M.E["key"].size),
        "hold_days_max": float(hold_days.max()), "hold_days_p99": float(np.percentile(hold_days, 99)),
        "frac_trades_held_over_1_day": float((hold_days > 1.0).mean()),
        "exit_before_entry_count": int((M.arr["exit_ns"] < M.arr["entry_ns"]).sum()),
        "entry_ns_sorted_within_config": bool(all(
            np.all(np.diff(M.arr["entry_ns"][int(M.arr["offsets"][i]):int(M.arr["offsets"][i + 1])]) >= 0)
            for i in range(0, M.n_local - 2, max(1, (M.n_local - 2) // 50)))),
        "eligibility_frac_seed0_at_K1_per_origin": {"median": med(elig), "min": (min(elig) if elig else None)},
        "bars_per_busday_from_trade_map": round(M.n_bars / max(1, np.busday_count(M.t_from.date(), M.t_to.date())), 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# V1 learning curve
# ─────────────────────────────────────────────────────────────────────────────
def v1_learning_curve(M, n_seeds=N_SEEDS):
    ors = origins(M.t_from, M.t_to)
    cells = []      # (origin_idx, K) -> dict
    test_cache = {}
    for oi, o in enumerate(ors):
        t1 = shift(o, 1)
        if t1 > M.t_to:
            continue
        st = M.stats(o, t1)
        test_cache[oi] = {"t0": o, "t1": t1, "st": st,
                          "champ_pct": pct_rank(np.append(st["net"][:M.c_total], st["net"][M.c_total]), M.c_total),
                          "default_pct": pct_rank(np.append(st["net"][:M.c_total], st["net"][M.c_total + 1]), M.c_total),
                          "oracle_net": float(st["net"][:M.c_total].max())}
    seed_subsets = [seed_subset(i, M.n_trials, M.c_total) for i in range(n_seeds)]
    full_pool = np.arange(M.c_total)
    for oi, o in enumerate(ors):
        if oi not in test_cache:
            continue
        tc = test_cache[oi]
        for K in KS:
            t0 = M.t_from if K == "all" else shift(o, -K)
            if t0 < M.t_from:
                continue
            if K == "all" and (o - M.t_from).days < 365:
                continue
            assert t0 < o <= tc["t0"]  # no look-ahead: training strictly before test
            tr = M.stats(t0, o)
            nb = M.nbars(t0, o)
            test_net = tc["st"]["net"][:M.c_total]
            row = {"oi": oi, "origin": str(o.date()), "K": K, "nbars_train": nb}
            # seed 0 (engine's own list)
            p0, n_rec, n_gated = pick_r1(tr, seed_subsets[0], nb, M.min_trades)
            if p0 is None:
                row["seed0"] = None
            else:
                row["seed0"] = {"pick": p0, "n_eligible": n_rec, "n_gated": n_gated,
                                "test_pct": pct_rank(test_net, p0),
                                "test_pf": fin(tc["st"]["pf"][p0]), "train_pf": fin(tr["pf"][p0]),
                                "test_n": int(tc["st"]["n"][p0]), "train_n": int(tr["n"][p0]),
                                "regret_rel": (None if abs(tc["oracle_net"]) < 1e-9 else
                                               float(100 * (tc["oracle_net"] - test_net[p0]) / abs(tc["oracle_net"])))}
            # 30 pseudo-seeds: median pct + distinct picks
            picks = []
            for ss in seed_subsets:
                p, _, _ = pick_r1(tr, ss, nb, M.min_trades)
                if p is not None:
                    picks.append(p)
            if picks:
                keyf = lambda p: json.dumps({k: M.params[p].get(k) for k in M.pkeys}, sort_keys=True, default=str)
                row["seeds"] = {"n_ok": len(picks), "median_test_pct": med([pct_rank(test_net, p) for p in picks]),
                                "n_distinct_picks": len(set(keyf(p) for p in picks)),
                                "frac_same_as_seed0": (float(np.mean([keyf(p) == keyf(picks[0]) for p in picks])))}
            # whole pool as the candidate list (bigger IS budget)
            pf_, _, _ = pick_r1(tr, full_pool, nb, M.min_trades)
            row["fullpool"] = None if pf_ is None else {"pick": pf_, "test_pct": pct_rank(test_net, pf_)}
            row["champ_pct"] = tc["champ_pct"]; row["default_pct"] = tc["default_pct"]
            cells.append(row)

    def curve(sel, field="seed0"):
        out = {}
        for K in KS:
            vals = []
            for c in sel:
                if c["K"] != K or c.get(field) is None:
                    continue
                v = c[field]["test_pct"] if field != "seeds" else c[field]["median_test_pct"]
                vals.append(v)
            out[str(K)] = boot_ci(vals)
        return out

    def common_set(kmax):
        need = [k for k in KS if k != "all" and k <= kmax] + ["all"]
        have = {}
        for c in cells:
            if c.get("seed0") is not None:
                have.setdefault(c["oi"], set()).add(c["K"])
        ok = {oi for oi, ks in have.items() if all(k in ks for k in need)}
        return [c for c in cells if c["oi"] in ok], sorted(ok)

    out = {"n_origins_total": len(ors), "n_cells": len(cells)}
    out["all_origins_per_K"] = {"seed0": curve(cells, "seed0"), "seeds30": curve(cells, "seeds"),
                                "fullpool": curve(cells, "fullpool")}
    for kmax in (8, 10):
        sel, ok = common_set(kmax)
        out[f"common_origins_Kle{kmax}"] = {
            "n_origins": len(ok), "first_origin": (cells[[c["oi"] for c in cells].index(ok[0])]["origin"] if ok else None),
            "seed0": curve(sel, "seed0"), "seeds30": curve(sel, "seeds"), "fullpool": curve(sel, "fullpool"),
            "champ_pct": boot_ci([c["champ_pct"] for c in sel if c["K"] == 3]),
            "default_pct": boot_ci([c["default_pct"] for c in sel if c["K"] == 3]),
        }
        # paired: K vs K=3, within origin (seed0)
        by = {}
        for c in sel:
            if c.get("seed0") is not None:
                by.setdefault(c["oi"], {})[c["K"]] = c["seed0"]["test_pct"]
        paired = {}
        for K in KS:
            if K == 3:
                continue
            d = [by[oi][K] - by[oi][3] for oi in by if K in by[oi] and 3 in by[oi]]
            paired[str(K)] = {"median_diff_pct_vs_K3": med(d), "sign_test": sign_test(d), "n": len(d)}
        out[f"common_origins_Kle{kmax}"]["paired_vs_K3_seed0"] = paired
        # within-origin Spearman(K, pct) -- does more depth monotonically help?
        from scipy.stats import spearmanr
        rhos = []
        for oi, dd in by.items():
            ks = [k for k in KS if k != "all" and k in dd]
            if len(ks) >= 4:
                r, _ = spearmanr(ks, [dd[k] for k in ks])
                if r is not None and not math.isnan(r):
                    rhos.append(float(r))
        out[f"common_origins_Kle{kmax}"]["within_origin_spearman_K_vs_pct"] = boot_ci(rhos)
    # regret (relative to oracle) by K, seed0, all origins
    out["regret_rel_pct_by_K_seed0"] = {str(K): boot_ci([c["seed0"]["regret_rel"] for c in cells
                                                          if c["K"] == K and c.get("seed0") and c["seed0"]["regret_rel"] is not None])
                                         for K in KS}
    out["test_pf_by_K_seed0"] = {str(K): boot_ci([c["seed0"]["test_pf"] for c in cells
                                                  if c["K"] == K and c.get("seed0") and isinstance(c["seed0"]["test_pf"], float)])
                                 for K in KS}
    out["cells"] = cells
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V2 leak checks
# ─────────────────────────────────────────────────────────────────────────────
def v2_leaks(M):
    ors = origins(M.t_from, M.t_to)
    sub0 = seed_subset(0, M.n_trials, M.c_total)
    rows = []
    for oi, o in enumerate(ors):
        t1 = shift(o, 1)
        if t1 > M.t_to:
            continue
        te_entry = M.stats(o, t1)
        te_exit = M.stats(o, t1, by="exit")
        for K in (2, 3, 6, "all"):
            t0 = M.t_from if K == "all" else shift(o, -K)
            if t0 < M.t_from or (K == "all" and (o - M.t_from).days < 365):
                continue
            nb = M.nbars(t0, o)
            tr_e = M.stats(t0, o)
            tr_x = M.stats(t0, o, by="exit")
            tr_s = M.stats(t0, o, drop_open_after=o.value)     # strict: drop trades open at the cut
            pe, _, _ = pick_r1(tr_e, sub0, nb, M.min_trades)
            px, _, _ = pick_r1(tr_x, sub0, nb, M.min_trades)
            ps, _, _ = pick_r1(tr_s, sub0, nb, M.min_trades)
            if pe is None or px is None or ps is None:
                continue
            rows.append({
                "origin": str(o.date()), "K": K,
                "pct_entry": pct_rank(te_entry["net"][:M.c_total], pe),
                "pct_exit_assign": pct_rank(te_exit["net"][:M.c_total], px),
                "pct_strict": pct_rank(te_entry["net"][:M.c_total], ps),
                "pick_changed_exit_vs_entry": bool(px != pe),
                "pick_changed_strict_vs_entry": bool(ps != pe),
                "n_open_at_cut_all_configs": int(tr_s["n_open_dropped"]),
                "open_at_cut_frac_of_pick": (float((tr_e["n"][pe] - tr_s["n"][pe]) / max(1, tr_e["n"][pe]))),
            })
    out = {}
    for K in (2, 3, 6, "all"):
        r = [x for x in rows if x["K"] == K]
        if not r:
            continue
        out[str(K)] = {
            "n": len(r),
            "median_pct_entry": med([x["pct_entry"] for x in r]),
            "median_pct_exit_assign": med([x["pct_exit_assign"] for x in r]),
            "median_pct_strict_no_open_trades": med([x["pct_strict"] for x in r]),
            "frac_pick_changed_exit_vs_entry": float(np.mean([x["pick_changed_exit_vs_entry"] for x in r])),
            "frac_pick_changed_strict_vs_entry": float(np.mean([x["pick_changed_strict_vs_entry"] for x in r])),
            "median_open_at_cut_frac_of_pick_trades": med([x["open_at_cut_frac_of_pick"] for x in r]),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V3 pseudo-seed independence (from V1 cells)
# ─────────────────────────────────────────────────────────────────────────────
def v3_seeds(v1):
    out = {}
    for K in KS:
        c = [x["seeds"] for x in v1["cells"] if x["K"] == K and x.get("seeds")]
        if not c:
            continue
        out[str(K)] = {"n_cells": len(c),
                       "median_distinct_picks_of_30": med([x["n_distinct_picks"] for x in c]),
                       "max_distinct_picks": max(x["n_distinct_picks"] for x in c),
                       "median_frac_seeds_same_as_seed0": med([x["frac_same_as_seed0"] for x in c])}
    # expected overlap of two random n_trials-of-c_total subsets
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V4 rank persistence with fixed 1y future + 10-finalist pipeline test
# ─────────────────────────────────────────────────────────────────────────────
def v4_rank_persistence(M):
    from scipy.stats import spearmanr, rankdata
    ors = origins(M.t_from, M.t_to)
    # common origin set: t - 6y >= t_from (largest L) and t + 1y <= t_to
    common = [o for o in ors if shift(o, -6) >= M.t_from and shift(o, 1) <= M.t_to]
    out = {"n_origins_common": len(common),
           "first_origin": str(common[0].date()) if common else None,
           "last_origin": str(common[-1].date()) if common else None}
    per_L = {}
    for L in LS_RANK:
        recs = []
        for o in common:
            A = M.stats(shift(o, -L), o)
            B = M.stats(o, shift(o, 1))
            a_net, b_net = A["net"][:M.c_total], B["net"][:M.c_total]
            a_pf, b_pf = A["pf"][:M.c_total], B["pf"][:M.c_total]
            has = (A["n"][:M.c_total] >= max(5, M.min_trades // 3)) & (B["n"][:M.c_total] > 0)
            if has.sum() < 10:
                continue
            r_net, _ = spearmanr(a_net[has], b_net[has])
            fin_pf = np.isfinite(a_pf) & np.isfinite(b_pf) & has
            r_pf, _ = spearmanr(a_pf[fin_pf], b_pf[fin_pf]) if fin_pf.sum() >= 10 else (None, None)
            bpct = 100.0 * rankdata(b_net, method="average") / M.c_total
            order = np.argsort(-a_net)
            top = [i for i in order if has[i]][: max(1, M.c_total // 10)]
            bottom = [i for i in order[::-1] if has[i]][: max(1, M.c_total // 10)]
            recs.append({"rho_net": float(r_net), "rho_pf": (float(r_pf) if r_pf is not None else None),
                         "top_decile_B_pct": float(np.mean(bpct[top])),
                         "bottom_decile_B_pct": float(np.mean(bpct[bottom])),
                         "best_A_B_pct": float(bpct[top[0]])})
        per_L[str(L)] = {
            "n": len(recs),
            "rho_net": boot_ci([r["rho_net"] for r in recs]),
            "rho_pf": boot_ci([r["rho_pf"] for r in recs]),
            "frac_rho_net_pos": (float(np.mean([r["rho_net"] > 0 for r in recs])) if recs else None),
            "top_decile_B_pct": boot_ci([r["top_decile_B_pct"] for r in recs]),
            "bottom_decile_B_pct": boot_ci([r["bottom_decile_B_pct"] for r in recs]),
            "top_minus_bottom_decile": boot_ci([r["top_decile_B_pct"] - r["bottom_decile_B_pct"] for r in recs]),
            "best_A_B_pct": boot_ci([r["best_A_B_pct"] for r in recs]),
        }
    out["by_L_fixed_1y_future"] = per_L

    # 10-finalist pipeline mirror: tune anchored on [t_from, t-L) -> top-10 UNIQUE gated configs
    # (seed-0 list), lockbox [t-L, t) ranks them, future [t, t+1y).
    sub0 = seed_subset(0, M.n_trials, M.c_total)
    fin_out = {}
    common_f = [o for o in ors if shift(o, -3) >= shift(M.t_from, 3) and shift(o, 1) <= M.t_to]
    for L in LS_DESIGN:
        recs = []
        for o in common_f:
            lb0 = shift(o, -L)
            tr = M.stats(M.t_from, lb0)
            nb = M.nbars(M.t_from, lb0)
            n = tr["n"][sub0]
            recs_ok = sub0[n >= M.min_trades]
            if recs_ok.size == 0:
                continue
            rate = tr["n"][recs_ok] / nb
            real = (tr["wins"][recs_ok] >= 5) & (tr["losses"][recs_ok] >= 5) & (rate <= MAX_TRADE_RATE) & (tr["pf"][recs_ok] <= MAX_PF)
            pool = recs_ok[real] if real.any() else recs_ok
            order = pool[np.argsort(-tr["net"][pool])]
            seen, finalists = set(), []
            for i in order:
                k = json.dumps({kk: M.params[i].get(kk) for kk in M.pkeys}, sort_keys=True, default=str)
                if k in seen:
                    continue
                seen.add(k); finalists.append(int(i))
                if len(finalists) == 10:
                    break
            if len(finalists) < 5:
                continue
            LB = M.stats(lb0, o); FU = M.stats(o, shift(o, 1))
            f = np.array(finalists)
            lb_net, fu_net = LB["net"][f], FU["net"][f]
            lb_pf, fu_pf = LB["pf"][f], FU["pf"][f]
            r, _ = spearmanr(lb_net, fu_net)
            r_is, _ = spearmanr(tr["net"][f], fu_net)          # in-sample rank vs future
            r_pf, _ = spearmanr(np.where(np.isfinite(lb_pf), lb_pf, 50), np.where(np.isfinite(fu_pf), fu_pf, 50))
            fu_rank = rankdata(-fu_net, method="average")       # 1 = best future
            lb_best = int(np.argmax(lb_net)); is_best = 0
            recs.append({"rho_lb_vs_future": float(r), "rho_is_vs_future": float(r_is),
                         "rho_lb_pf_vs_future_pf": float(r_pf),
                         "lb_best_future_rank_of_n": float(fu_rank[lb_best]) / len(f),
                         "is_best_future_rank_of_n": float(fu_rank[is_best]) / len(f),
                         "lb_best_beats_median": bool(fu_net[lb_best] > np.median(fu_net)),
                         "n_finalists": len(f)})
        fin_out[str(L)] = {
            "n_origins": len(recs),
            "rho_lockbox_vs_future_1y": boot_ci([x["rho_lb_vs_future"] for x in recs]),
            "rho_lockbox_pf_vs_future_pf": boot_ci([x["rho_lb_pf_vs_future_pf"] for x in recs]),
            "rho_insample_vs_future_1y": boot_ci([x["rho_is_vs_future"] for x in recs]),
            "frac_rho_lb_pos": (float(np.mean([x["rho_lb_vs_future"] > 0 for x in recs])) if recs else None),
            "lockbox_best_future_rank_frac(0=best)": boot_ci([x["lb_best_future_rank_of_n"] for x in recs]),
            "insample_best_future_rank_frac": boot_ci([x["is_best_future_rank_of_n"] for x in recs]),
            "p_lockbox_best_beats_finalist_median": (float(np.mean([x["lb_best_beats_median"] for x in recs])) if recs else None),
            "median_n_finalists": med([x["n_finalists"] for x in recs]),
        }
    out["ten_finalists_pipeline_mirror"] = {"n_origins_common": len(common_f), "by_L": fin_out}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V5 design backtest at ORIGIN level
# ─────────────────────────────────────────────────────────────────────────────
def v5_designs(M):
    ors = origins(M.t_from, M.t_to)
    sub0 = seed_subset(0, M.n_trials, M.c_total)
    # common origins: for every design, the tune window must have >= 3y and future 1y must fit
    common = [o for o in ors if shift(o, -3) >= shift(M.t_from, 3) and shift(o, 1) <= M.t_to]
    out = {"n_origins_common": len(common), "designs": {}}
    for K in (3, 6, "all"):
        for L in LS_DESIGN:
            recs = []
            for o in common:
                lb0 = shift(o, -L)
                tr0 = M.t_from if K == "all" else shift(lb0, -K)
                if tr0 < M.t_from:
                    continue
                tr = M.stats(tr0, lb0); nb = M.nbars(tr0, lb0)
                p, _, _ = pick_r1(tr, sub0, nb, M.min_trades)
                if p is None:
                    continue
                LB = M.stats(lb0, o); FU = M.stats(o, shift(o, 1))
                FU2 = M.stats(o, shift(o, 2)) if shift(o, 2) <= M.t_to else None
                # no-lockbox alternative: tune through t with the same K (+L years of data)
                tr_full = M.stats(tr0, o); nb2 = M.nbars(tr0, o)
                q, _, _ = pick_r1(tr_full, sub0, nb2, M.min_trades)
                fu_net = FU["net"][:M.c_total]
                passed = bool(LB["net"][p] > 0 and LB["pf"][p] >= 1.0 and LB["n"][p] > 0)
                recs.append({"origin": str(o.date()), "passed": passed,
                             "lb_pf": fin(LB["pf"][p]), "lb_n": int(LB["n"][p]),
                             "fut_pos": bool(FU["net"][p] > 0), "fut_pf": fin(FU["pf"][p]),
                             "fut_pct_frozen": pct_rank(fu_net, p),
                             "fut_pct_nolockbox": (pct_rank(fu_net, q) if q is not None else None),
                             "fut2_pos": (bool(FU2["net"][p] > 0) if FU2 is not None else None),
                             "fut_pf_nolockbox": (fin(FU["pf"][q]) if q is not None else None)})
            if not recs:
                continue
            P = [r for r in recs if r["passed"]]; F = [r for r in recs if not r["passed"]]
            from scipy.stats import spearmanr
            lbpf = [r["lb_pf"] for r in recs if isinstance(r["lb_pf"], float) and isinstance(r["fut_pf"], float)]
            fupf = [r["fut_pf"] for r in recs if isinstance(r["lb_pf"], float) and isinstance(r["fut_pf"], float)]
            rho = float(spearmanr(lbpf, fupf)[0]) if len(lbpf) >= 5 else None
            dif = [r["fut_pct_frozen"] - r["fut_pct_nolockbox"] for r in recs if r["fut_pct_nolockbox"] is not None]
            out["designs"][f"K={K}_L={L}"] = {
                "n_origins": len(recs), "pass_rate": float(np.mean([r["passed"] for r in recs])),
                "p_fut1y_pos_given_pass": (float(np.mean([r["fut_pos"] for r in P])) if P else None), "n_pass": len(P),
                "p_fut1y_pos_given_fail": (float(np.mean([r["fut_pos"] for r in F])) if F else None), "n_fail": len(F),
                "median_fut1y_pf_pass": med([r["fut_pf"] for r in P if isinstance(r["fut_pf"], float)]),
                "median_fut1y_pf_fail": med([r["fut_pf"] for r in F if isinstance(r["fut_pf"], float)]),
                "spearman_lockbox_pf_vs_future_pf": rho,
                "frozen_minus_nolockbox_future_pct": boot_ci(dif),
                "sign_test_frozen_vs_nolockbox": sign_test(dif),
                "median_fut_pct_frozen": med([r["fut_pct_frozen"] for r in recs]),
                "median_fut_pct_nolockbox": med([r["fut_pct_nolockbox"] for r in recs]),
                "p_fut2y_pos_given_pass": (float(np.mean([r["fut2_pos"] for r in P if r["fut2_pos"] is not None]))
                                           if any(r["fut2_pos"] is not None for r in P) else None),
                "p_fut2y_pos_given_fail": (float(np.mean([r["fut2_pos"] for r in F if r["fut2_pos"] is not None]))
                                           if any(r["fut2_pos"] is not None for r in F) else None),
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V6 recency vs depth
# ─────────────────────────────────────────────────────────────────────────────
def v6_recency(M):
    ors = origins(M.t_from, M.t_to)
    sub0 = seed_subset(0, M.n_trials, M.c_total)
    rows = []
    for o in ors:
        if shift(o, -6) < M.t_from or shift(o, 1) > M.t_to:
            continue
        te = M.stats(o, shift(o, 1)); tn = te["net"][:M.c_total]
        wins = {"recent3": (shift(o, -3), o), "old3": (shift(o, -6), shift(o, -3)), "last6": (shift(o, -6), o),
                "recent1": (shift(o, -1), o), "old1_of_3": (shift(o, -3), shift(o, -2))}
        r = {"origin": str(o.date())}
        for name, (a, b) in wins.items():
            st = M.stats(a, b); p, _, _ = pick_r1(st, sub0, M.nbars(a, b), M.min_trades)
            r[name] = None if p is None else pct_rank(tn, p)
        rows.append(r)
    out = {"n_origins": len(rows)}
    for name in ("recent3", "old3", "last6", "recent1", "old1_of_3"):
        out[name] = boot_ci([r[name] for r in rows])
    out["paired_recent3_minus_old3"] = sign_test([r["recent3"] - r["old3"] for r in rows if r["recent3"] is not None and r["old3"] is not None])
    out["paired_recent3_minus_last6"] = sign_test([r["recent3"] - r["last6"] for r in rows if r["recent3"] is not None and r["last6"] is not None])
    out["paired_recent1_minus_old1"] = sign_test([r["recent1"] - r["old1_of_3"] for r in rows if r["recent1"] is not None and r["old1_of_3"] is not None])
    out["median_diff_recent3_minus_old3"] = med([r["recent3"] - r["old3"] for r in rows if r["recent3"] is not None and r["old3"] is not None])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# V7 unitless shrinkage (PF) by K, seed0, from V1 cells
# ─────────────────────────────────────────────────────────────────────────────
def v7_shrinkage(v1):
    def curve(cells):
        out = {}
        for K in KS:
            r = []
            for c in cells:
                s = c.get("seed0")
                if c["K"] != K or not s or not isinstance(s["train_pf"], float) or not isinstance(s["test_pf"], float):
                    continue
                if s["train_pf"] > 1.0:
                    r.append((s["test_pf"] - 1.0) / (s["train_pf"] - 1.0))
            out[str(K)] = boot_ci(r)
        return out
    have = {}
    for c in v1["cells"]:
        if c.get("seed0") is not None:
            have.setdefault(c["oi"], set()).add(c["K"])
    need8 = [k for k in KS if k != "all" and k <= 8] + ["all"]
    ok8 = {oi for oi, ks in have.items() if all(k in ks for k in need8)}
    return {"all_origins": curve(v1["cells"]),
            "common_origins_Kle8": curve([c for c in v1["cells"] if c["oi"] in ok8])}


# ─────────────────────────────────────────────────────────────────────────────
def run_one(run_id, n_seeds):
    t0 = time.time()
    M = Matrix(run_id)
    path = os.path.join(DATA_DIR, f"verify_{run_id}.json")
    out = {"run_id": run_id, "script": "verify_isdepth.py (independent of analyze_matrix.py)"}

    def save():
        out["runtime_s"] = round(time.time() - t0, 1)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fin(out), f, indent=1, default=str)

    out["V0_facts"] = v0_facts(M); save(); print(f"[{run_id}] V0 {time.time()-t0:.0f}s", flush=True)
    v1 = v1_learning_curve(M, n_seeds); out["V1_learning_curve"] = {k: v for k, v in v1.items() if k != "cells"}
    out["V1_learning_curve"]["cells_seed0"] = [{"origin": c["origin"], "K": c["K"], "champ_pct": c["champ_pct"], "default_pct": c["default_pct"],
                                                **({"pct": c["seed0"]["test_pct"], "pf": c["seed0"]["test_pf"], "train_pf": c["seed0"]["train_pf"],
                                                    "n_eligible": c["seed0"]["n_eligible"], "n_gated": c["seed0"]["n_gated"],
                                                    "regret_rel": c["seed0"]["regret_rel"],
                                                    "seeds_distinct": (c["seeds"]["n_distinct_picks"] if c.get("seeds") else None),
                                                    "fullpool_pct": (c["fullpool"]["test_pct"] if c.get("fullpool") else None)}
                                                   if c.get("seed0") else {"pct": None})}
                                               for c in v1["cells"]]
    save(); print(f"[{run_id}] V1 {time.time()-t0:.0f}s", flush=True)
    out["V2_leaks"] = v2_leaks(M); save(); print(f"[{run_id}] V2 {time.time()-t0:.0f}s", flush=True)
    out["V3_pseudo_seeds"] = v3_seeds(v1); save()
    out["V4_rank_persistence"] = v4_rank_persistence(M); save(); print(f"[{run_id}] V4 {time.time()-t0:.0f}s", flush=True)
    out["V5_designs_origin_level"] = v5_designs(M); save(); print(f"[{run_id}] V5 {time.time()-t0:.0f}s", flush=True)
    out["V6_recency"] = v6_recency(M); save(); print(f"[{run_id}] V6 {time.time()-t0:.0f}s", flush=True)
    out["V7_pf_shrinkage_by_K"] = v7_shrinkage(v1); save()
    print(f"[{run_id}] done {time.time()-t0:.0f}s -> {path}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_ids", nargs="*", type=int)
    ap.add_argument("--seeds", type=int, default=N_SEEDS)
    args = ap.parse_args()
    try:
        sys.path.insert(0, os.path.join(WORKTREE_ROOT, "tools"))
        from wfdive import common
        common.low_priority()
    except Exception as e:
        print("low_priority unavailable:", e)
    for rid in args.run_ids:
        run_one(rid, args.seeds)


if __name__ == "__main__":
    main()

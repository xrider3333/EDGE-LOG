"""Look-alike pre-entry setups — find trades whose PRE-ENTRY price action looks nearly
identical ("copy-paste setups") and report whether those look-alike groups actually
share an outcome. No Firestore dependency here; the caller passes the payload. Kept
dependency-light like api/blotter.py and api/bars.py.

Pipeline (docs/VISUAL_TRADE_REPORT.md §2.5 governs the entry-time/side/exit-price
reconstruction this reuses via api.blotter.champion_blotter — ONE code path for that,
never re-derived here):

  1. champion_blotter() -> trade list (entry_time, side, pnl_usd) for the run's config.
  2. load_master_arrays() ONCE over the run's window (same fallback chain as api/bars.py).
  3. Slice `lookback` closes ending at (and including) each trade's entry bar.
  4. Shape-normalize each window to z-scores (mean 0, std 1) so only SHAPE matters.
  5. Pearson correlation between every pair of z-vectors == dot(zi, zj) / lookback for
     z-scored vectors — computed in row-chunks so a full NxN matrix is never held; only
     pairs >= min_corr survive, as a sparse list.
  6. Greedy agglomeration: a trade joins a group only if it correlates >= min_corr with
     the group's FIRST (leader) member — keeps groups tight instead of chaining.
  7. Per-group stats + the group's mean shape (for the browser to draw).
  8. HONESTY GATE — a permutation test per group (is this group's mean pnl unusual vs a
     random same-size draw from ALL trades?) plus a run-level "expected by chance"
     diagnostic (see _expected_by_chance's docstring for exactly what that measures and
     what it doesn't).
"""
import os
import time

import numpy as np

from api import blotter as _bl
from api.blotter import champion_blotter
from augur_engine.data import find_master, load_master_arrays


def _resolve_strategy_for_run(root, payload, log):
    """Same resolution chain as api.blotter.load_blotter_rows: filename -> label match
    -> the run's own code snapshot (payload['code'] or the local history DB) when the
    plugin file no longer exists on disk. None if nothing usable."""
    name = payload.get("strategy")
    if not name:
        return None
    strat = _bl._resolve_strategy(root, name)
    fn = strat if str(strat).endswith(".py") else str(strat) + ".py"
    if os.path.isfile(os.path.join(root, "augur_strategies", fn)):
        return strat
    rid = payload.get("run_id")
    mod = (_bl._module_from_code(root, rid, payload.get("code"), log)
           or _bl._module_from_code(root, rid, _bl._snapshot_from_db(root, rid), log))
    return mod


def _chunked_pairs(Z, min_corr, chunk=512):
    """All (i, j, corr) triples with i < j and corr >= min_corr, from an already
    z-normalized (per-row mean 0 / std 1) float32 matrix Z (N x lookback). Pearson
    correlation between z-scored rows is dot(zi, zj) / lookback, so one matmul per
    chunk of rows gets a whole (chunk x N) correlation slice without ever
    materializing the full N x N matrix. Only surviving pairs are kept -> sparse."""
    N, L = Z.shape
    Zt = Z.T
    pairs = []
    for start in range(0, N, chunk):
        end = min(start + chunk, N)
        block = (Z[start:end] @ Zt) / L   # (end-start, N) float32
        for r in range(end - start):
            gi = start + r
            tail = block[r, gi + 1:]      # only j > gi -> unique pairs, no self-corr
            if tail.size == 0:
                continue
            hits = np.nonzero(tail >= min_corr)[0]
            for h in hits:
                pairs.append((gi, gi + 1 + int(h), float(tail[h])))
    return pairs


def _greedy_groups(pairs, min_corr, min_group):
    """Sort surviving pairs by correlation descending, greedily agglomerate: a trade
    joins a group only if it correlates >= min_corr with the group's FIRST (leader)
    member (not just with whichever member introduced it) — keeps groups tight instead
    of chaining transitively through a string of pairwise-similar-but-not-mutually-
    similar trades. Returns {leader_idx: [member idx, ...]} for groups with
    >= min_group members. `pairs` indices are into whatever array they were built
    from (real Z or a permuted one for the chance-null)."""
    pairs_sorted = sorted(pairs, key=lambda p: -p[2])
    pair_corr = {}
    for i, j, c in pairs_sorted:
        pair_corr[(i, j)] = c
    assigned = {}
    leader_members = {}
    for i, j, _c in pairs_sorted:
        li = assigned.get(i)
        lj = assigned.get(j)
        if li is None and lj is None:
            assigned[i] = i
            assigned[j] = i
            leader_members[i] = [i, j]
        elif li is not None and lj is None:
            cc = pair_corr.get((li, j), pair_corr.get((j, li)))
            if li == i or (cc is not None and cc >= min_corr):
                assigned[j] = li
                leader_members[li].append(j)
        elif lj is not None and li is None:
            cc = pair_corr.get((lj, i), pair_corr.get((i, lj)))
            if lj == j or (cc is not None and cc >= min_corr):
                assigned[i] = lj
                leader_members[lj].append(i)
        # else: both already assigned (possibly to different groups) -> no merge
    return {L: m for L, m in leader_members.items() if len(m) >= min_group}


def _perm_pvalues(pnl_arr, group_sizes, group_means, n_reps=2000, seed=42):
    """Permutation test per group (HONESTY GATE, step 8): draw n_reps random samples of
    each group's size from ALL trades' pnl_usd (without replacement — matching how a
    real group is n DISTINCT trades) and report the fraction whose |mean| >= the
    group's |mean pnl|. One shared (n_reps x N) random-key matrix is drawn ONCE and
    reused (via argpartition) for every group's sample draw instead of re-drawing per
    group. Returns a list of p-values, same order as group_sizes/group_means."""
    Nall = len(pnl_arr)
    rng = np.random.default_rng(seed)
    rand_keys = rng.random((n_reps, Nall), dtype=np.float32)
    pvals = []
    for n, gmean in zip(group_sizes, group_means):
        if n <= 0:
            pvals.append(1.0)
            continue
        if n >= Nall:
            pvals.append(1.0)   # the "group" is the whole population -> nothing to compare against
            continue
        idx = np.argpartition(rand_keys, n, axis=1)[:, :n]
        samples = pnl_arr[idx]
        perm_means = samples.mean(axis=1)
        pvals.append(float(np.mean(np.abs(perm_means) >= abs(gmean))))
    return pvals


def _expected_by_chance(Z, min_corr, min_group, n_perm=20, time_budget_s=15.0, seed=7):
    """Run-level chance diagnostic (step 8's second honesty requirement).

    WHAT THIS ACTUALLY MEASURES: each permutation independently shuffles every trade's
    OWN z-vector along the time axis (numpy Generator.permuted(axis=1) — a per-row
    independent shuffle). That destroys the window's temporal SHAPE (the thing the
    clustering is looking for) while exactly preserving its mean/std (a z-scored row's
    permutation is still mean-0/std-1), so it re-runs the identical similarity +
    greedy-clustering pipeline on data that has the same per-window statistics as the
    real trades but no real temporal structure. The number of >= min_group groups that
    still survive is the false-positive rate of this exact pipeline at this exact
    min_corr/min_group/N -- i.e. how many "look-alike" groups would appear from pure
    chance alone. Reports the MEDIAN group count across however many permutations
    completed inside time_budget_s (the dominant cost is the same O(N^2/chunk)
    similarity pass as the real run, so this is genuinely n_perm times the real run's
    cost -- time-boxed on purpose, and it says exactly how many it managed rather than
    silently doing fewer and claiming n_perm)."""
    N = Z.shape[0]
    if N < min_group:
        return {"median_groups": 0, "n_permutations_run": 0, "requested": n_perm,
                "note": "fewer usable trades than min_group -- no chance baseline needed"}
    rng = np.random.default_rng(seed)
    counts = []
    t0 = time.time()
    for k in range(n_perm):
        Zp = rng.permuted(Z, axis=1)
        pairs_p = _chunked_pairs(Zp, min_corr)
        groups_p = _greedy_groups(pairs_p, min_corr, min_group)
        counts.append(len(groups_p))
        if time.time() - t0 > time_budget_s and (k + 1) < n_perm:
            break
    out = {"median_groups": float(np.median(counts)) if counts else 0,
           "n_permutations_run": len(counts), "requested": n_perm}
    if len(counts) < n_perm:
        out["note"] = (f"time-boxed at {time_budget_s:.0f}s -- ran {len(counts)}/{n_perm} "
                        f"permutations, not the full request; median is over those {len(counts)}")
    else:
        out["note"] = ("shuffles each trade's own window along time (same per-window mean/std, "
                        "temporal shape destroyed) and reruns the same pipeline -- this is the "
                        "pipeline's false-positive group count on structure-free data, not a "
                        "test of any individual group (see each group's own p_value for that)")
    return out


def find_similar_setups(root, payload, log=print) -> dict:
    """Find "copy-paste setup" trade groups: trades whose pre-entry price action is
    nearly identical in SHAPE, and whether those groups actually share an outcome.

    payload: the same shape get_bars/get_blotter take (instrument, timeframe, session,
    source, strategy, params, cost_pts, mult, date_from, date_to, run_id, code) plus
    lookback (int, default 24), min_corr (float, default 0.97), max_groups (int,
    default 12), min_group (int, default 2).

    Returns a json-safe {ok, groups, n_trades, lookback, min_corr, expected_by_chance,
    meta} dict, or {ok: False, error}.
    """
    t_start = time.time()
    instrument = payload.get("instrument")
    timeframe = payload.get("timeframe") or "5m"
    session = payload.get("session") or "rth"
    source = payload.get("source")
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    lookback = int(payload.get("lookback") or 24)
    min_corr = float(payload.get("min_corr") or 0.97)
    max_groups = int(payload.get("max_groups") or 12)
    min_group = int(payload.get("min_group") or 2)

    if not instrument or not payload.get("strategy"):
        return {"ok": False, "error": "instrument and strategy are required"}

    # ── Step 1: the trade list — ONE code path (entry_time/side/exit-px reconstruction
    #    all live in champion_blotter; nothing here re-derives any of that). ──────────
    strat = _resolve_strategy_for_run(root, payload, log)
    if strat is None:
        return {"ok": False,
                "error": f"strategy '{payload.get('strategy')}' is gone from augur_strategies "
                         f"and no code snapshot is available to rebuild it"}
    rows, bmeta = champion_blotter(
        strat, instrument, timeframe, session=session, params=payload.get("params") or {},
        cost_pts=float(payload.get("cost_pts") or 0), mult=float(payload.get("mult") or 20),
        date_from=date_from, date_to=date_to, source=source)
    if not rows:
        return {"ok": False, "error": "champion_blotter produced no trades for this config"}

    # ── Step 2: master arrays ONCE over the run's window — same fallback chain
    #    api/bars.py and champion_blotter both use, so bar positions line up exactly
    #    with the entry_time strings champion_blotter just built off THIS SAME chain. ──
    m = ((find_master(instrument, timeframe, session, source) if source else None)
         or find_master(instrument, timeframe, session) or find_master(instrument, timeframe))
    if not m:
        return {"ok": False, "error": f"no master for instrument={instrument} timeframe={timeframe}"}
    a = load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx, close = a["index"], a["close"]
    if idx is None or len(idx) == 0:
        return {"ok": False,
                "error": f"master '{m.get('name')}' has no bars in window {date_from}..{date_to}"}
    pos_by_key = {str(t)[:16]: i for i, t in enumerate(idx)}
    closef = np.asarray(close, dtype=np.float64)

    # ── Steps 3+4: per-trade lookback window, shape-normalized to z-scores. ─────────
    trade_no, entry_time_l, side_l, pnl_l, windows = [], [], [], [], []
    skip_no_bar = skip_no_hist = skip_flat = 0
    for r in rows:
        key = str(r["entry_time"])[:16]
        pos = pos_by_key.get(key)
        if pos is None:
            skip_no_bar += 1
            continue
        start = pos - lookback + 1
        if start < 0:
            skip_no_hist += 1
            continue
        w = closef[start:pos + 1]
        mean = w.mean()
        std = w.std()
        if std == 0:
            skip_flat += 1
            continue
        windows.append(((w - mean) / std).astype(np.float32))
        trade_no.append(int(r["trade_no"]))
        entry_time_l.append(r["entry_time"])
        side_l.append(r["side"])
        pnl_l.append(float(r["pnl_usd"]))

    if len(windows) < min_group:
        return {"ok": False,
                "error": f"only {len(windows)} of {len(rows)} trades had a usable "
                         f"{lookback}-bar pre-entry window -- need at least {min_group}"}

    Z = np.vstack(windows)          # (N, lookback) float32, mean0/std1 per row
    N = Z.shape[0]
    pnl_arr = np.asarray(pnl_l, dtype=np.float64)

    # ── Steps 5+6: sparse pairwise correlation, then greedy agglomeration. ──────────
    pairs = _chunked_pairs(Z, min_corr)
    raw_groups = _greedy_groups(pairs, min_corr, min_group)

    # ── Step 7: per-group stats + mean shape. ────────────────────────────────────────
    built = []
    for leader, members in raw_groups.items():
        members = sorted(members)
        n = len(members)
        sub = Z[members]
        corr_mat = (sub @ sub.T) / lookback
        iu = np.triu_indices(n, k=1)
        mean_corr = float(corr_mat[iu].mean()) if len(iu[0]) else 1.0
        mpnl = pnl_arr[members]
        built.append({
            "members": [trade_no[i] for i in members],
            "n": n,
            "mean_corr": round(mean_corr, 4),
            "mean_pnl_usd": round(float(mpnl.mean()), 2),
            "median_pnl_usd": round(float(np.median(mpnl)), 2),
            "win_rate": round(float((mpnl > 0).mean() * 100.0), 1),
            "total_pnl_usd": round(float(mpnl.sum()), 2),
            "mean_shape": [round(float(x), 4) for x in sub.mean(axis=0)],
            "entry_times": [entry_time_l[i] for i in members],
            "sides": [side_l[i] for i in members],
            "_raw_mean_pnl": float(mpnl.mean()),
        })

    # ── Step 8: HONESTY GATE — per-group permutation p-values (batched, one shared
    #    random-key draw reused across every group instead of redrawing per group). ──
    if built:
        pvals = _perm_pvalues(pnl_arr, [g["n"] for g in built],
                              [g["_raw_mean_pnl"] for g in built], n_reps=2000)
        # Benjamini-Hochberg FDR across EVERY group tested (this house's standard — a raw
        # p<0.05 verdict over dozens of groups manufactures ~1 "signal" per 20 by construction;
        # the FDR scan in the TRADE CONTEXT work uses the same correction). BH runs over all
        # groups BEFORE the max_groups cap, because the multiple-comparison burden is the
        # number of tests PERFORMED, not the number displayed.
        m_tests = len(pvals)
        order = sorted(range(m_tests), key=lambda i: pvals[i])
        qs = [1.0] * m_tests
        running = 1.0
        for rank in range(m_tests - 1, -1, -1):     # walk up from the largest p
            i = order[rank]
            running = min(running, pvals[i] * m_tests / float(rank + 1))
            qs[i] = min(1.0, running)
        for g, p, q in zip(built, pvals, qs):
            g["p_value"] = round(p, 4)
            g["q_value"] = round(q, 4)
            g["n_tested"] = int(m_tests)
            # SIGNAL only survives the FDR correction; a raw-p hit that dies under it is
            # labelled honestly rather than being quietly promoted.
            g["verdict"] = "signal" if q < 0.05 else ("chance" if p >= 0.05 else "not after FDR")
            del g["_raw_mean_pnl"]

    # Step 9: sort n desc, then |mean pnl| desc; cap.
    built.sort(key=lambda g: (-g["n"], -abs(g["mean_pnl_usd"])))
    built = built[:max_groups]

    # Run-level chance baseline (second half of the honesty gate) — time-boxed so a
    # big N never blows the read-only command's budget.
    remaining = max(5.0, 60.0 - (time.time() - t_start))
    chance = _expected_by_chance(Z, min_corr, min_group, n_perm=20,
                                 time_budget_s=min(15.0, remaining))

    n_signal = sum(1 for g in built if g["verdict"] == "signal")
    log(f"    -> similar-setups: {len(rows)} trades, {N} usable {lookback}-bar windows, "
        f"{len(raw_groups)} groups >= {min_group} members @ corr>={min_corr} "
        f"({n_signal} pass p<0.05, chance baseline median {chance['median_groups']}) "
        f"from master '{m.get('name')}' [{time.time() - t_start:.1f}s]")

    return {
        "ok": True,
        "groups": built,
        "n_trades": int(N),
        "n_blotter_trades": int(len(rows)),
        "lookback": int(lookback),
        "min_corr": float(min_corr),
        "min_group": int(min_group),
        "expected_by_chance": chance,
        "meta": {"master": m.get("name"), "source": m.get("source"),
                 "date_from": date_from, "date_to": date_to,
                 "skipped_no_bar_match": int(skip_no_bar),
                 "skipped_insufficient_history": int(skip_no_hist),
                 "skipped_flat_window": int(skip_flat),
                 "elapsed_s": round(time.time() - t_start, 2)},
    }

"""Auto-Optimize + Walk-Forward (streamlit-free) — the smart-search scopes.

A faithful port of optimizer.py's `opt_mode == "auto"` path (the 🤖 AUTO-OPTIMIZE
and 🔁 Walk-Forward scopes), extracted so the EDGELOG web frontend + job runner can
drive them without importing the Streamlit app.

Two modes, same call:
  • method="single"      — seeded random/Bayesian search maximizing total PnL on the
                           first 75% of history, then RE-TEST every surviving config on
                           the held-out last 25% (out-of-sample). The headline is
                           realism-gated (enough wins AND losses, capped trade-rate/PF)
                           so a profit-factor mirage can't win.
  • method="walkforward" — anchored folds: each fold re-optimizes on all history up to
                           its test slice, crowns a champion by NET PnL (same realism
                           gate), and tests it on the next unseen slice. One row per
                           fold → param drift + per-fold OOS visible. Headline = the
                           LAST fold's champion (most recent re-optimize).

Determinism: seeded random sampler (seed=42), no optuna dependency, so results are
reproducible across machines — matching the app's _HAS_OPTUNA=False fallback path.
"""
import inspect
import math
import random as _random

from .strategies import load_strategy, _resolve, strategy_params
from .data import find_master, load_master_arrays
from .engine import _apply_costs
from .analytics import (annualized_sr, deflated_sharpe, monte_carlo_drawdown,
                        regime_report, neighborhood, downsample_pnls, downsample_points,
                        mae_mfe, relationship_scores, pdp_plateau,
                        interaction_pairs, conditional_boundary_flags)

# Realism gates — identical to optimizer.py (WF_MIN_SIDE / MAX_TRADE_RATE / MAX_PF).
# A champion/headline config must take at least this many WINNING and LOSING trades
# (not a one-sided fluke), trade no more often than MAX_TRADE_RATE per bar, and have
# a profit factor no higher than MAX_PF (above that = overfit / fill artifact).
WF_MIN_SIDE = 5
MAX_TRADE_RATE = 0.015
MAX_PF = 6.0
OOS_SPLIT = 0.75

# AUTO-EXPAND-AND-RESAMPLE (owner request 2026-07-18: "if adjusting a knob continues
# to help, push the knob further") — the follow-through on the boundary-peak detector
# (commit 5df5a76, analytics._pdp_boundary_flags): a NUMERIC knob pinned at its
# tested-range edge and still rising gets its range WIDENED and re-sampled, instead of
# just flagged. See _auto_expand_search / _expand_range below.
#
# ITERATIVE COORDINATE-DESCENT UPGRADE (owner request #30, 2026-07-18: "once a
# plateau is found, go back and re-check whether previously-settled params are
# still plateaus, since widening one param can unlock a higher peak in another").
# commit b6261de's expander was single-pass: `active` was seeded ONLY from the
# INITIAL boundary_flags, so a param that only became edge-pinned AFTER another
# param's range widened (an "unlock") was silently dropped -- observed live on
# TTIBS, where `hold_cap` emerged mid-run and was never chased. See
# _auto_expand_search's docstring for the outer coordinate-descent loop and the
# re-emergence/no-re-add policy.
AUTO_EXPAND_SPAN_FRAC = 0.5   # each round extends the flagged edge by +50% of the
                              # ORIGINAL tested width (at least one `step`)
AUTO_EXPAND_WIDTH_CAP = 2.0   # ...but the final width (measured from the ORIGINAL
                              # bounds) may never exceed this multiple of the original
                              # width, even if still rising when the cap is hit — the
                              # fallback guard when a param declares no hard_min/hard_max

_METRIC_KEYS = ("total_pnl", "num_trades", "win_rate", "profit_factor",
                "max_drawdown", "avg_pnl", "wins", "losses")


def _auto_space_from_params(default_params: dict) -> dict:
    """DEFAULT_PARAMS -> search space: name -> ('float'|'int', lo, hi, step) | ('cat', [..])."""
    space = {}
    for name, meta in (default_params or {}).items():
        if not isinstance(meta, dict):
            continue
        typ = meta.get("type", "float")
        if typ == "bool":
            space[name] = ("cat", [True, False])
        elif typ == "str":
            opts = meta.get("options") or [meta.get("default")]
            space[name] = ("cat", list(opts))
        elif typ == "int":
            space[name] = ("int", int(meta.get("min", 0)), int(meta.get("max", 10)),
                           int(meta.get("step", 1) or 1))
        else:
            space[name] = ("float", float(meta.get("min", 0.0)),
                           float(meta.get("max", 1.0)), float(meta.get("step", 0.0) or 0.0))
    return space


class _RandomSampler:
    """Seeded random search over the space (the app's optuna-absent fallback)."""

    def __init__(self, space, seed=42):
        self.space = space
        self._rng = _random.Random(seed)

    def ask(self):
        p = {}
        for name, spec in self.space.items():
            kind = spec[0]
            if kind == "cat":
                p[name] = self._rng.choice(spec[1])
            elif kind == "int":
                _, lo, hi, step = spec
                step = max(1, int(step))
                n = (hi - lo) // step
                p[name] = lo + step * self._rng.randint(0, max(0, n))
            else:
                _, lo, hi, step = spec
                if step and step > 0:
                    n = int(round((hi - lo) / step))
                    p[name] = round(lo + step * self._rng.randint(0, max(0, n)), 6)
                else:
                    p[name] = round(self._rng.uniform(lo, hi), 6)
        return p


def _collapse(p, default_params):
    """Reset inactive conditional params (depends_on unmet) to their default."""
    pe = dict(p)
    for k, meta in (default_params or {}).items():
        if not isinstance(meta, dict):
            continue
        cond = meta.get("depends_on")
        if cond and k in pe and not all(p.get(dk) == dv for dk, dv in cond.items()):
            pe[k] = meta.get("default")
    return pe


def _is_real(r, nbars):
    """The realism gate as a predicate over a metrics dict."""
    return (int(r.get("wins", 0) or 0) >= WF_MIN_SIDE
            and int(r.get("losses", 0) or 0) >= WF_MIN_SIDE
            and (int(r.get("num_trades", 0) or 0) / max(1, nbars)) <= MAX_TRADE_RATE
            and float(r.get("profit_factor", 0) or 0) <= MAX_PF)


def _snap_to_step(value, step, kind, anchor):
    """Snap `value` onto the step-grid anchored at `anchor` (e.g. a param's ORIGINAL
    min/max), so a widened range stays aligned to the knob's declared step — hold_cap
    stays a whole number of days, ibs_entry stays a multiple of 0.05, etc. No-op when
    step is 0/None (a continuous float param)."""
    if not step:
        return value
    k = round((value - anchor) / step)
    snapped = anchor + k * step
    return int(round(snapped)) if kind == "int" else round(float(snapped), 6)


def _expand_range(lo, hi, step, kind, edge, orig_lo, orig_hi, hard_min=None, hard_max=None):
    """One AUTO-EXPAND round's outward push of a single param's range.

    Extends the FLAGGED edge outward by `expand_span = max(step, AUTO_EXPAND_SPAN_FRAC
    * (orig_hi - orig_lo))` — at least one step, else +50% of the ORIGINAL tested width
    — keeping the OTHER edge fixed at its current (possibly already-widened) value.

    HARD SAFETY BOUNDS (never crossed — the guardrail against pushing a param into a
    meaningless regime):
      - an optional per-param `hard_min`/`hard_max` (a NEW opt-in DEFAULT_PARAMS key;
        most strategies — TTIBS included — don't declare one yet, so this is None and
        only the fallback below applies);
      - else the fallback: total width measured from the ORIGINAL bounds may never
        exceed AUTO_EXPAND_WIDTH_CAP (2x) the original width. With the default
        auto_expand_max_rounds=2 and a 50%-per-round span, two un-capped rounds land
        EXACTLY on this cap (2 x 50% = +100% = 2x width) — the cap mainly guards
        oddball cases: a tiny original range where `step` forces a bigger-than-50%
        jump, or a hard bound biting before the round budget runs out.

    Returns the new (lo, hi) — unchanged (a no-op) if there is no room left to expand
    (already at a hard/fallback bound), so the caller can detect "stuck" params.
    """
    width0 = max(1e-9, orig_hi - orig_lo)
    span = max(step or 0, AUTO_EXPAND_SPAN_FRAC * width0)
    if edge == "max":
        new_hi = hi + span
        if hard_max is not None:
            new_hi = min(new_hi, hard_max)
        new_hi = min(new_hi, orig_lo + AUTO_EXPAND_WIDTH_CAP * width0)
        new_hi = max(new_hi, hi)                     # never shrink
        return lo, _snap_to_step(new_hi, step, kind, orig_lo)
    else:
        new_lo = lo - span
        if hard_min is not None:
            new_lo = max(new_lo, hard_min)
        new_lo = max(new_lo, orig_hi - AUTO_EXPAND_WIDTH_CAP * width0)
        new_lo = min(new_lo, lo)                     # never shrink
        return _snap_to_step(new_lo, step, kind, orig_hi), hi


def _emerge_suffix(emerged, cause, via=None, partner=None, slice_=None):
    """Note suffix appended to a log entry when the param was chased only because
    it EMERGED mid-run (i.e. it was not in the initial boundary_flags) -- names the
    param(s) whose expansion preceded it, per _auto_expand_search's docstring. No
    exact causal proof is attempted (that would require a counterfactual re-run) --
    this is a "here's what changed right before this showed up" breadcrumb.

    P3 (docs/SURROGATE_DISCOVERY_DESIGN.md §7): when `via == "interaction"`, this
    param wasn't unlocked by another param's WIDENING at all -- it was flagged by
    `analytics.conditional_boundary_flags` off the JOINT surface with `partner`
    (its own unconditional/marginal curve never tripped the plain 1-D detector).
    Names the pair in plain language instead of the generic "emerged" phrasing."""
    if not emerged:
        return ""
    if via == "interaction" and partner:
        level = "high" if slice_ == "high" else "low"
        return (f" (widened because the joint surface with {partner} shows the optimum "
                f"escaping this range when {partner} is {level}.)")
    who = ", ".join(cause) if cause else "another param"
    return f" (emerged mid-run after widening {who}.)"


def _auto_expand_search(records, seen, pkeys, space, dp, ev_fn, ksplit, min_trades,
                        seed, n_trials, boundary_flags, max_rounds=2,
                        max_global_rounds=6):
    """AUTO-EXPAND-AND-RESAMPLE — ITERATIVE COORDINATE-DESCENT (owner request #30,
    2026-07-18: "once a plateau is found, go back and re-check whether previously-
    settled params are still plateaus, since widening one param can unlock a higher
    peak in another"). Builds on the single-pass expander (commit b6261de): that
    version seeded `active` ONLY from the INITIAL pdp_plateau's boundary_flags, so a
    knob that only became edge-pinned AFTER another knob's range was widened (a
    joint-surface "unlock") was silently never chased (observed live: TTIBS's
    `hold_cap` emerged mid-run and was dropped by the old single-pass code).

    ALGORITHM — an outer coordinate-descent loop, `global_round` in
    [1..max_global_rounds], each round:
      a. expand every param CURRENTLY in `active` one step outward (as the
         single-pass version did — honors hard_min/hard_max + the 2x-width
         fallback cap; a param with no room left finalizes immediately as
         "capped", no resample wasted on it).
      b. resample (seed offset by `global_round`, deterministic) + merge/dedupe
         into the running record set.
      c. recompute pdp_plateau on the FULL merged surface so far -> `flagged_now`.
      d. NEW — for every param in `flagged_now` that is NOT currently active and
         has NOT already been finalized this run, ADD it to `active` (seeded from
         its ORIGINAL search-space bounds, rounds=0, marked `emerged=True`). It
         starts expanding on the NEXT global round, same as any freshly-flagged
         param.
      e. for each param that WAS active at the top of THIS round: increment its
         own per-param `rounds` counter; if it tapered (no longer flagged) or hit
         its own `max_rounds` / a hard/width cap, FINALIZE it (tapered or capped)
         and drop it from `active`.
      f. keep going while `active` is non-empty AND global_round < max_global_rounds.

    P3 -- INTERACTION-AWARE EXPANSION (docs/SURROGATE_DISCOVERY_DESIGN.md §7 P3,
    owner-approved 2026-07-19): step (d) above only ever catches a param whose
    OWN marginal curve becomes edge-pinned. That misses a real case: a knob Y
    whose marginal curve looks perfectly fine (averaged over everything else)
    can still have its true optimum escape the tested range for a SUBSET of a
    strong partner knob X's values -- the marginal just hides it. So step (d)
    is extended: after the ordinary `flagged_now` re-emergence check, ALSO fit
    `analytics.interaction_pairs` (a small RandomForestRegressor + the same
    Friedman-H-style pair-strength statistic `surrogate.py`'s bake-off already
    uses) on the merged records-so-far, and run `analytics.
    conditional_boundary_flags` on the resulting strong pairs -- for each pair
    (X, Y), restrict to the TOP/BOTTOM tercile of X's observed values and
    re-check Y's curve WITHIN that slice with the identical edge-pinned-and-
    rising rule. Any param this flags that is not already `active` or
    `finalized` joins `active` exactly like an ordinary emerged param (rounds=0,
    seeded from its ORIGINAL space bounds), but tagged `via="interaction"` +
    `partner`/`slice` so its log entry names the pair in plain language instead
    of the generic "emerged mid-run" phrasing. The ORDINARY re-emergence check
    always runs FIRST and claims a param before P3 gets a chance to (the
    `_activate` guard is "already active or finalized -> skip"), so on any
    surface where the plain 1-D detector ALSO eventually catches a param (as it
    already did pre-P3), P3 is a complete no-op for it -- P3 only ever adds
    params the 1-D detector's own marginal view was hiding. Both `interaction_
    pairs`/`conditional_boundary_flags` are wrapped in a blanket try/except
    (see their own docstrings) and degrade to doing nothing -- an interaction-
    scan failure can never stop the plain 1-D expander from running its normal
    course. NOTE: like step (d)'s ordinary emerged params, an interaction
    unlock can only ever add a param STARTING the round after some OTHER param
    was already active (the outer `while active and ...` loop itself never
    starts from a fully empty `active` -- P3 rides on top of an already-
    running expansion, it doesn't independently trigger one).

    Two separate caps, deliberately decoupled:
      `max_rounds`        — how many times a SINGLE param may be widened (its own
                             per-param counter; unchanged meaning from the
                             single-pass version, default 2).
      `max_global_rounds` — the OUTER loop's safety cap on how many coordinate-
                             descent rounds run in total, regardless of which
                             params are active in each — the guard against
                             runaway when params keep unlocking each other
                             (default 6).

    RE-EMERGENCE / NO-RE-ADD POLICY (the safe default the owner asked to pick):
    once a param is finalized — tapered OR capped — it is NEVER re-added to
    `active` again this run, even if a LATER round's pdp_plateau shows it flagged
    again. That re-flagging is a real possibility: `cur_bounds` keeps sampling a
    finalized param from its last (possibly already-widened) range every
    subsequent round (the sampler draws every space key each round, active or
    not), and enough fresh draws can occasionally tip its marginal curve back over
    the edge-pinned threshold. Chasing it again risks an oscillation — A unlocks
    B, B's expansion makes A look edge-pinned again, A's re-expansion re-unlocks
    B, forever. A permanent `finalized` set (checked before EVERY add, initial or
    emerged) rules this out by construction: since a param can only move
    active -> finalized (never back), and `active` can only gain members that
    aren't already finalized, the tracked set is strictly monotonic in
    "finalized" and the loop provably terminates by max_global_rounds even on a
    pathological always-rising joint surface. (A bounded single-controlled-reopen
    was considered as a bonus but skipped — it would break that monotonicity
    argument for a benefit that hasn't been needed in practice.)

    Params mirror run_auto's own locals at the call site: `ev_fn` is its `_ev`
    in-sample evaluator closure, `ksplit`/`min_trades` its IS-window bound and trade
    floor, `space`/`dp` the search-space + DEFAULT_PARAMS dicts, `pkeys` the ordered
    param-name list, `seed`/`n_trials` the run's own (so expansion seeds/budgets stay
    deterministic and proportional). `boundary_flags` is the INITIAL pdp_plateau's
    flag list (numeric params only — analytics._pdp_boundary_flags never flags a
    categorical/bool param).

    Returns (pp, log, merged_records, summary):
      pp             — the LAST pdp_plateau(...) computed on the merged (original +
                       every accepted expansion round's) records, or None if
                       nothing ever expanded.
      log            — the out["auto_expand"] entries (see run_auto's docstring for
                       the schema); one dict per param that EVER entered `active`
                       (initial-flag OR emerged), appended the round it finalizes
                       (tapers, hits a hard/width cap, or the whole search hits
                       max_global_rounds while it was still active). Adds
                       `emerged: bool` — True iff this param was NOT in the initial
                       `boundary_flags` (i.e. it was only chased because another
                       param's widening unlocked it); its `note` then also names
                       the param(s) being widened the round it first showed up.
                       Empty when no numeric param was ever flagged.
      merged_records — the list `pp["index"]` refers into (== the input `records`
                       unchanged when `log` is empty).
      summary        — {global_rounds_used, n_params_expanded, n_emerged,
                       n_interaction_unlocks, converged}. `n_interaction_unlocks`
                       (P3) is how many of the log entries were activated via
                       the interaction-conditional check rather than the plain
                       1-D re-emergence path (0 when no pair ever cleared the
                       strength bar, or when only ordinary re-emergence fired —
                       it's a SUBSET count of `n_emerged`, never double-counted
                       against it). `converged` is True iff the loop ended with
                       `active` empty on its own (nothing left in OUR tracked set
                       still rising) — False iff it stopped because global_round
                       hit max_global_rounds while something was still active.
                       This is about the tracked set, not a claim that the FINAL
                       pp["search_truncated"] is False — under the no-re-add
                       policy a finalized param can in principle still show up in
                       the final surface's boundary_flags; that stays visible via
                       pp["search_truncated"] rather than being papered over here.
    """
    recs = list(records)
    seen2 = set(seen)
    cur_bounds = dict(space)
    active = {}
    finalized = set()
    log = []
    n_emerged = 0
    n_interaction_unlocks = 0

    def _activate(pname, edge, emerged, cause=None, via=None, partner=None, slice_=None):
        spec = space.get(pname)
        if not spec or spec[0] not in ("int", "float"):
            return False                              # categorical/unknown — not expandable
        _, lo, hi, step = spec
        meta = dp.get(pname)
        meta = meta if isinstance(meta, dict) else {}
        active[pname] = {"kind": spec[0], "orig_lo": lo, "orig_hi": hi, "step": step,
                         "cur_lo": lo, "cur_hi": hi, "edge": edge, "rounds": 0,
                         "hard_min": meta.get("hard_min"), "hard_max": meta.get("hard_max"),
                         "emerged": emerged, "cause": list(cause or []),
                         "via": via, "partner": partner, "slice": slice_}
        return True

    def _interaction_unlocks(current_records):
        """P3 — wraps analytics.interaction_pairs/conditional_boundary_flags with
        an EXTRA guard on top of their own (never omit the "an interaction-scan
        failure must never kill a round" contract, even against a future bug in
        either function)."""
        try:
            pairs = interaction_pairs(current_records, pkeys, dp)
            if not pairs:
                return []
            return conditional_boundary_flags(current_records, pkeys, dp, pairs)
        except Exception:
            return []

    for f in (boundary_flags or []):
        _activate(f.get("param"), f["edge"], emerged=False)

    pp = None
    flagged_now = {}
    global_round = 0
    while active and global_round < max_global_rounds:
        global_round += 1
        round_pnames = list(active)                    # snapshot -- params pushed THIS round
        pushed = []
        for pname in round_pnames:
            st = active[pname]
            new_lo, new_hi = _expand_range(st["cur_lo"], st["cur_hi"], st["step"],
                                           st["kind"], st["edge"], st["orig_lo"],
                                           st["orig_hi"], st["hard_min"], st["hard_max"])
            if (new_lo, new_hi) == (st["cur_lo"], st["cur_hi"]):
                # already at a hard/fallback bound -- no point resampling
                finalized.add(pname)
                log.append({"param": pname, "orig_range": [st["orig_lo"], st["orig_hi"]],
                           "final_range": [st["cur_lo"], st["cur_hi"]], "rounds": st["rounds"],
                           "tapered": False, "emerged": st["emerged"],
                           "via": st["via"], "partner": st["partner"], "slice": st["slice"],
                           "final_peak_value": st["cur_hi"] if st["edge"] == "max" else st["cur_lo"],
                           "note": "hit a hard_min/hard_max bound with no room left to "
                                   "expand -- still rising at the bound."
                                   + _emerge_suffix(st["emerged"], st["cause"],
                                                    st["via"], st["partner"], st["slice"])})
                del active[pname]
                continue
            st["cur_lo"], st["cur_hi"] = new_lo, new_hi
            cur_bounds[pname] = (st["kind"], new_lo, new_hi, st["step"])
            pushed.append(pname)
        if not pushed:
            continue                                   # every active param was already capped

        samp = _RandomSampler(cur_bounds, seed=int(seed) + global_round)   # deterministic offset
        budget = max(1, n_trials // 2)                  # proportional cost per expansion round
        for _ in range(budget):
            pe = _collapse(samp.ask(), dp)
            m = ev_fn(0, ksplit, pe)
            if m and m.get("num_trades", 0) >= min_trades:
                sig = tuple(sorted(pe.items()))
                if sig not in seen2:                    # dedupe identical param combos
                    seen2.add(sig)
                    recs.append({**pe, **m})

        _pts = [dict({k: r.get(k) for k in pkeys},
                     pnl=round(float(r.get("total_pnl", 0) or 0), 1),
                     dd=round(abs(float(r.get("max_drawdown", 0) or 0)), 1))
                for r in recs]
        pp = pdp_plateau(_pts) or pp
        flagged_now = {f["param"]: f for f in ((pp or {}).get("boundary_flags") or [])}

        for pname in pushed:                            # finalize-check -- only params WE pushed
            st = active[pname]
            st["rounds"] += 1
            width0 = st["orig_hi"] - st["orig_lo"]
            width_now = st["cur_hi"] - st["cur_lo"]
            hit_cap = width_now >= AUTO_EXPAND_WIDTH_CAP * width0 - 1e-9
            still_flagged = pname in flagged_now and flagged_now[pname]["edge"] == st["edge"]
            if still_flagged and st["rounds"] < max_rounds and not hit_cap:
                continue                               # keep expanding this param next round
            finalized.add(pname)
            del active[pname]
            tapered = not still_flagged
            if tapered:
                note = "search widened until the curve tapered to an interior optimum."
                peak_val = (pp or {}).get("params", {}).get(pname)
            else:
                why = "hit the 2x-width safety cap" if hit_cap else "hit auto_expand_max_rounds"
                note = (f"still rising at the expanded edge ({why}) -- true optimum may "
                        f"be even further out; widen DEFAULT_PARAMS manually.")
                peak_val = flagged_now[pname]["value"]
            log.append({"param": pname, "orig_range": [st["orig_lo"], st["orig_hi"]],
                       "final_range": [st["cur_lo"], st["cur_hi"]], "rounds": st["rounds"],
                       "tapered": tapered, "emerged": st["emerged"],
                       "via": st["via"], "partner": st["partner"], "slice": st["slice"],
                       "final_peak_value": peak_val,
                       "note": note + _emerge_suffix(st["emerged"], st["cause"],
                                                     st["via"], st["partner"], st["slice"])})

        # ordinary re-emergence -- chase any param that only just showed up in
        # flagged_now, seeded from the ORIGINAL search-space bounds (not
        # `cur_bounds`, which may already carry a stale widened range for it
        # from nowhere -- an emerged param has never been touched, so its true
        # starting point is `space`).
        for pname, f in flagged_now.items():
            if pname in active or pname in finalized:
                continue                               # already tracked, or permanently retired
            if _activate(pname, f["edge"], emerged=True, cause=pushed):
                n_emerged += 1

        # P3 -- interaction-conditional re-check on the MERGED records-so-far
        # (`recs`, which by this point in the round already includes this
        # round's fresh resample). Runs AFTER the ordinary re-emergence check
        # above, so on any surface where the plain 1-D detector ALSO eventually
        # catches a param, the `_activate` "already active/finalized" guard
        # makes this a complete no-op for it -- P3 only ever adds params the
        # 1-D detector's own marginal view was hiding (see this function's
        # docstring, P3 section).
        for cf in _interaction_unlocks(recs):
            pname = cf["param"]
            if pname in active or pname in finalized:
                continue
            if _activate(pname, cf["edge"], emerged=True, cause=[cf["partner"]],
                        via="interaction", partner=cf["partner"], slice_=cf["slice"]):
                n_emerged += 1
                n_interaction_unlocks += 1

    # Loop ended -- either `active` drained naturally (converged) or global_round
    # hit the cap with something still legitimately active. Finalize any leftovers
    # so every ever-tracked param gets exactly one log entry either way.
    converged = not active
    for pname in list(active):
        st = active[pname]
        finalized.add(pname)
        peak_val = (flagged_now.get(pname) or {}).get(
            "value", st["cur_hi"] if st["edge"] == "max" else st["cur_lo"])
        note = ("hit auto_expand_max_global_rounds while still rising -- the joint "
                "search did not fully stabilize; raise auto_expand_max_global_rounds "
                "or widen DEFAULT_PARAMS manually."
                + _emerge_suffix(st["emerged"], st["cause"], st["via"], st["partner"], st["slice"]))
        log.append({"param": pname, "orig_range": [st["orig_lo"], st["orig_hi"]],
                   "final_range": [st["cur_lo"], st["cur_hi"]], "rounds": st["rounds"],
                   "tapered": False, "emerged": st["emerged"],
                   "via": st["via"], "partner": st["partner"], "slice": st["slice"],
                   "final_peak_value": peak_val, "note": note})
        del active[pname]

    summary = {"global_rounds_used": global_round, "n_params_expanded": len(log),
              "n_emerged": n_emerged, "n_interaction_unlocks": n_interaction_unlocks,
              "converged": converged}
    return pp, log, recs, summary


def run_auto(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
             master=None, arrays=None, cost_pts=0.0, min_trades=30, n_trials=200,
             top_n=10, method="single", oos=True, wf_folds=0, seed=42,
             compute_dsr=False, mc_sims=0, progress_cb=None, years=None,
             compute_regime=False, compute_neighbors=False, compute_pills=False,
             date_from=None, date_to=None, wf_mode="anchored",
             auto_expand=True, auto_expand_max_rounds=2, auto_expand_max_global_rounds=6,
             compute_surrogate=False,
             auto_steer=False, steer_seed_frac=0.4, steer_batch_frac=0.15):
    """Smart search. Returns the same shape as run_grid plus OOS columns.

    method="single" or "walkforward". Returns {mode,n_combos,n_valid,top[...],
    best_params,best,bars,master,(equity/mc/dsr)} where each top row carries
    oos_pnl/oos_trades/oos_pf (single) or fold/test_bars/oos_* (walkforward).

    auto_expand (default True, non-WF runs only): AUTO-EXPAND-AND-RESAMPLE — when the
    boundary-peak detector (analytics._pdp_boundary_flags, via plateau_pick) finds a
    NUMERIC knob pinned at its tested-range edge and still rising, widen that knob's
    range and sample more, repeating until the curve tapers to an interior peak or a
    safety cap trips (see _auto_expand_search / _expand_range). ITERATIVE coordinate-
    descent (owner request #30): every round re-checks ALL params, not just the
    initially-flagged ones — a param that only becomes edge-pinned AFTER another
    param's range is widened (an "unlock") is picked up and chased too, as
    `emerged=True`. Two caps bound the search: `auto_expand_max_rounds` (default 2)
    — how many times any ONE param may be widened — and `auto_expand_max_global_rounds`
    (default 6) — the outer loop's cap on total coordinate-descent rounds (guards
    against params unlocking each other forever). Once a param finalizes (tapers or
    caps out) it is never re-chased again this run (see _auto_expand_search's
    no-re-add policy). Fully additive + scoped to plateau_pick only — best/top/DSR/
    MC/regime/neighbors/pills always key off the ORIGINAL (unexpanded) sample.
    Set auto_expand=False to reproduce the pre-expansion behavior byte-for-byte.
    INTERACTION-AWARE EXPANSION (P3, docs/SURROGATE_DISCOVERY_DESIGN.md §7,
    owner-approved 2026-07-19): every round ALSO fits a small RandomForest +
    Friedman-H-style pair-strength scan (analytics.interaction_pairs) over the
    merged records-so-far and, for any strong pair (X, Y), checks Y's curve
    CONDITIONAL on the top/bottom tercile of X's values (analytics.
    conditional_boundary_flags) — so a knob whose own 1-D/marginal curve looks
    perfectly fine still gets widened when the JOINT surface shows its optimum
    escaping the tested range at extreme values of a strong partner knob. Such
    params carry `emerged=True` too (P3 unlocks ride the same "starts expanding
    next round" mechanics as an ordinary emerged param) plus `via="interaction"`,
    `partner`, `slice:'high'|'low'` on their log entry. The ordinary 1-D
    re-emergence check always runs first each round, so P3 is a no-op whenever
    the plain detector would have caught the param anyway — it only ever adds
    knobs the marginal view was hiding. Both P3 helpers are wrapped in their own
    try/except (never raise) — an interaction-scan failure degrades to nothing
    happening, never to a broken run.
    When it fires, `out["auto_expand"]` lists one entry per every param that ever
    entered the chase (initial-flag or emerged): {param, orig_range:[min,max],
    final_range:[min,max], rounds, tapered:bool, emerged:bool, via, partner,
    slice, final_peak_value, note} — `via`/`partner`/`slice` are None except on a
    P3 interaction unlock. `out["auto_expand_summary"]` carries
    {global_rounds_used, n_params_expanded, n_emerged, n_interaction_unlocks,
    converged:bool} — converged is True iff the joint surface fully stabilized
    (nothing left rising) before max_global_rounds; n_interaction_unlocks (P3) is
    the subset of n_emerged activated via the interaction-conditional check
    (0 when no pair ever cleared the strength bar).

    compute_surrogate (default False, non-WF runs only): opt-in MULTI-SURROGATE
    BAKE-OFF READ-OUT (#31 P1, docs/SURROGATE_DISCOVERY_DESIGN.md) — fits several
    models (quadratic response surface, Random Forest, XGBoost, Gaussian Process)
    to the SAME configs the random sampler already evaluated, cross-validates each,
    reads the best one's joint optimum + 2-way interactions, and ground-truths every
    model's proposed optimum with a real backtest on this run's own IS window. NO
    steering (P2) — the sampler above is completely untouched either way. Attaches
    `out["surrogate"]` (see augur_engine.surrogate.surrogate_bakeoff's docstring for
    the schema) or `{"error": ...}` if the bake-off itself failed — never raises.

    auto_steer (default False, non-WF runs only): P2 STEERING (#36,
    docs/SURROGATE_DISCOVERY_DESIGN.md §5/§7) — makes the ML surrogate AIM the
    search instead of only reading it out afterward (P1/`compute_surrogate` above).
    Off by default; the plain `_RandomSampler` loop above is what runs otherwise,
    byte-identical to before. When True, the single-split search loop spends its
    budget in two phases instead of one:
      1. SEED   — the first `steer_seed_frac` (default 0.4) of `n_trials`, sampled
                  and evaluated EXACTLY as the always-random path does.
      2. STEER  — repeat: fit `augur_engine.surrogate.propose_candidates` on every
                  record evaluated so far (seed + prior steered batches) and ask it
                  for a batch of `ceil(steer_batch_frac * n_trials)` (default 0.15)
                  GP-proposed configs (Upper-Confidence-Bound acquisition — exploit
                  predicted-high-PnL regions AND explore where the GP is still
                  uncertain); evaluate each with the SAME `_ev(0, ksplit, ...)` +
                  min_trades + seen-dedupe gate every random trial goes through, and
                  append to `records` just like any other point. If `propose_candidates`
                  returns nothing (too few points yet, or the GP fit itself failed —
                  wrapped in try/except so a steering failure can never kill the run),
                  that batch falls back to plain random sampling instead. Repeats
                  until `n_trials` total evaluations (seed + steered + fallback) have
                  been spent — same total trial budget as the non-steered path.
    Steered/fallback records are ORDINARY records — ranking, plateau/auto-expand,
    the surrogate P1 read-out, and every downstream analytic work on them unchanged.
    When `auto_steer` is True, `out["steering"] = {"used": True, "seed_trials": int,
    "steered_trials": int, "fallback_random": int}` is attached; absent when False.
    """
    path = _resolve(strategy) if isinstance(strategy, str) else None
    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    space = _auto_space_from_params(dp)
    if not space:
        raise ValueError("strategy exposes no tunable DEFAULT_PARAMS for auto search")
    pkeys = list(space.keys())

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V, did = arrays.get("volume"), arrays.get("day_id")
    IDX = arrays.get("index")

    fn = mod.run_backtest
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    pass_vol = V is not None and (has_kw or "volumes" in sp)
    pass_day = did is not None and (has_kw or "day_id" in sp)
    # Bar timestamps — mirror engine.run_backtest: only strategies that declare
    # `index` get it (TTIBS/REPLAY need real dates; without this they return None
    # on every trial and the whole search degenerates to 0 valid configs).
    pass_idx = IDX is not None and "index" in sp

    def _ev(a, b, params, keep_trades=False):
        """Evaluate params on the [a:b) window, slicing extras consistently.
        keep_trades=True retains the per-trade list on the result (for OOS
        distributions); otherwise trades are dropped to keep results light."""
        ex = {}
        if pass_vol:
            ex["volumes"] = V[a:b]
        if pass_day:
            ex["day_id"] = did[a:b]
        if pass_idx:
            ex["index"] = IDX[a:b]
        try:
            if cost_pts > 0:
                m = fn(O[a:b], H[a:b], L[a:b], C[a:b], return_trades=True, **ex, **params)
                if m:
                    m = _apply_costs(m, cost_pts)
                    if not keep_trades:
                        m.pop("trades", None)
                return m
            return fn(O[a:b], H[a:b], L[a:b], C[a:b], return_trades=keep_trades, **ex, **params)
        except Exception:
            return None

    n = len(C)
    oos_on = bool(oos) and n >= 200
    records = []   # each: {**params, **metrics, oos_*...}
    steer_info = None   # set only by the non-WF branch when auto_steer=True (#36)

    if method == "walkforward" and oos_on and n >= 4000:
        # ── Walk-forward: anchored (expanding IS from 0) or rolling (fixed-length
        #    IS window of `init` bars that slides forward — more regime-honest). ──
        rolling = str(wf_mode).lower() == "rolling"
        req = int(wf_folds or 0)
        n_folds = (max(2, min(8, req)) if req >= 2 else min(8, max(2, n // 3000)))
        init = int(n * 0.40)
        tsize = max(1, (n - init) // n_folds)
        n_total = n_trials * n_folds
        done = 0
        for f in range(n_folds):
            tr_end = init + f * tsize
            tr_start = max(0, tr_end - init) if rolling else 0
            te_s = tr_end
            te_e = n if f == n_folds - 1 else te_s + tsize
            samp = _RandomSampler(space, seed=seed)
            recs = []
            for _ in range(n_trials):
                pe = _collapse(samp.ask(), dp)
                m = _ev(tr_start, tr_end, pe)
                if m and m.get("num_trades", 0) >= min_trades:
                    recs.append({**pe, **m})
                done += 1
                if progress_cb and done % 10 == 0:
                    progress_cb(done, n_total)
            if not recs:
                continue
            gated = [r for r in recs if _is_real(r, tr_end - tr_start)]
            champ = max(gated or recs, key=lambda r: float(r.get("total_pnl", 0) or 0))
            pp = {k: champ[k] for k in pkeys if k in champ}
            om = _ev(te_s, te_e, pp, keep_trades=True)
            row = {k: champ.get(k) for k in pkeys}
            row.update({k: champ.get(k) for k in _METRIC_KEYS})
            row["fold"] = f + 1
            row["test_bars"] = te_e - te_s
            row["train_bars"] = tr_end - tr_start   # IS window length (for WFE)
            row["oos_pnl"] = float(om["total_pnl"]) if om else 0.0
            row["oos_trades"] = int(om["num_trades"]) if om else 0
            # OOS per-trade net PnLs + heat/reach for the report's walk-forward distribution
            # tiles (1G/1H WF scope). Best-effort — never let this break a fold.
            row["_oos_pnls"] = []
            row["_oos_mae"] = []
            row["_oos_mfe"] = []
            row["_oos_won"] = []
            try:
                _tr = (om or {}).get("trades") or []
                if _tr:
                    row["_oos_pnls"] = [round(float(t[2]) - cost_pts, 4) for t in _tr]
                    from .analytics import mae_mfe as _mmfe_wf
                    _mm = _mmfe_wf(_tr, H[te_s:te_e], L[te_s:te_e])
                    if _mm and _mm.get("mae"):
                        row["_oos_mae"] = [round(float(v), 4) for v in _mm["mae"]]
                        row["_oos_mfe"] = [round(float(v), 4) for v in _mm["mfe"]]
                        row["_oos_won"] = list(_mm.get("won") or [])
            except Exception:
                pass
            row["oos_pf"] = float(om.get("profit_factor", 0)) if om else 0.0
            row["oos_wins"] = int(om.get("wins", 0) or 0) if om else 0
            row["oos_win_rate"] = float(om.get("win_rate", 0) or 0) if om else 0.0
            records.append(row)
        if progress_cb:
            progress_cb(n_total, n_total)
        is_wf = True
    else:
        # ── Single 75/25 split (or no-OOS) ────────────────────────────────
        samp = _RandomSampler(space, seed=seed)
        ksplit = int(n * OOS_SPLIT) if oos_on else n
        seen = set()

        def _eval_one(pe):
            """Evaluate one config on the IS window; append+dedupe into
            records/seen exactly like the plain random loop always has. Shared
            by both the always-random path and the P2 steering path below so
            the two can never drift apart in gating/dedupe semantics."""
            m = _ev(0, ksplit, pe)
            if m and m.get("num_trades", 0) >= min_trades:
                sig = tuple(sorted(pe.items()))
                if sig not in seen:
                    seen.add(sig)
                    records.append({**pe, **m})

        if auto_steer:
            # P2 STEERING (#36, docs/SURROGATE_DISCOVERY_DESIGN.md §5/§7) — spend
            # the first `steer_seed_frac` of the budget exactly as random search
            # always has, then let the GP surrogate (augur_engine.surrogate.
            # propose_candidates) AIM the remaining batches via UCB acquisition,
            # falling back to random whenever it has nothing to propose. Total
            # evaluations spent == n_trials, same budget as the non-steered path.
            n_seed = max(1, min(n_trials, int(round(steer_seed_frac * n_trials))))
            batch_n = max(1, int(math.ceil(steer_batch_frac * n_trials)))
            fallback_random = 0
            done = 0
            for _ in range(n_seed):
                pe = _collapse(samp.ask(), dp)
                _eval_one(pe)
                done += 1
                if progress_cb and (done % 10 == 0 or done == n_trials):
                    progress_cb(done, n_trials)
            while done < n_trials:
                batch = min(batch_n, n_trials - done)
                proposals = []
                try:
                    from .surrogate import propose_candidates
                    proposals = propose_candidates(records, pkeys, dp, space,
                                                   n_propose=batch, seed=int(seed) + done)
                except Exception:
                    proposals = []
                if not proposals:
                    # nothing proposed (too few points yet, GP fit failed, or the
                    # pool was exhausted) — fall back to plain random for this
                    # whole batch, exactly the guardrail the design doc requires
                    # (a steering failure must never kill/shrink a run's budget).
                    fallback_random += batch
                    for _ in range(batch):
                        pe = _collapse(samp.ask(), dp)
                        _eval_one(pe)
                        done += 1
                        if progress_cb and (done % 10 == 0 or done == n_trials):
                            progress_cb(done, n_trials)
                else:
                    for pe0 in proposals:
                        pe = _collapse(dict(pe0), dp)
                        _eval_one(pe)
                        done += 1
                        if progress_cb and (done % 10 == 0 or done == n_trials):
                            progress_cb(done, n_trials)
                        if done >= n_trials:
                            break
            steer_info = {"used": True, "seed_trials": n_seed,
                         "steered_trials": max(0, n_trials - n_seed - fallback_random),
                         "fallback_random": fallback_random}
        else:
            for i in range(n_trials):
                pe = _collapse(samp.ask(), dp)
                _eval_one(pe)
                if progress_cb and (i % 10 == 0 or i + 1 == n_trials):
                    progress_cb(i + 1, n_trials)
        if oos_on:
            for rec in records:
                pp = {k: rec[k] for k in pkeys if k in rec}
                om = _ev(ksplit, n, pp)
                rec["oos_pnl"] = float(om["total_pnl"]) if om else 0.0
                rec["oos_trades"] = int(om["num_trades"]) if om else 0
                rec["oos_pf"] = float(om.get("profit_factor", 0)) if om else 0.0
                rec["oos_wins"] = int(om.get("wins", 0) or 0) if om else 0
                rec["oos_win_rate"] = float(om.get("win_rate", 0) or 0) if om else 0.0
        is_wf = False

    if not records:
        _out0 = {"mode": method, "n_combos": n_trials * (1 if not is_wf else 1),
                "n_valid": 0, "top": [], "best_params": None, "best": None,
                "bars": int(n), "master": (arrays.get("meta") or {}).get("name"),
                "no_results": True}
        if steer_info is not None:
            _out0["steering"] = steer_info
        return _out0

    # ── Rank ────────────────────────────────────────────────────────────────
    if is_wf:
        # Keep fold order; headline = last fold's champion (most recent re-optimize).
        ranked = records
        best = records[-1]
    else:
        # Realism-gated headline (enough wins AND losses, capped rate/PF) ranked
        # above the rest, then by total PnL — a few-loss PF mirage can't headline.
        ranked = sorted(records, key=lambda r: (1 if _is_real(r, n) else 0,
                                                float(r.get("total_pnl", 0) or 0)),
                        reverse=True)
        best = ranked[0]

    top = []
    for r in ranked[:top_n]:
        row = {k: r.get(k) for k in pkeys if k in r}
        row.update({k: r.get(k) for k in _METRIC_KEYS if k in r})
        for k in ("oos_pnl", "oos_trades", "oos_pf", "oos_wins", "oos_win_rate",
                  "fold", "test_bars", "train_bars",
                  "_oos_pnls", "_oos_mae", "_oos_mfe", "_oos_won"):
            if k in r:
                row[k] = r[k]
        top.append(row)

    out = {"mode": method, "n_combos": (n_trials if not is_wf else n_trials),
           "n_valid": len(records), "top": top,
           "best_params": {k: best.get(k) for k in pkeys if k in best},
           "best": {k: best.get(k) for k in _METRIC_KEYS if k in best},
           "bars": int(n), "master": (arrays.get("meta") or {}).get("name"),
           "wf": is_wf}
    if steer_info is not None:   # P2 steering (#36) — only ever set by the non-WF branch
        out["steering"] = steer_info
    if not is_wf:   # config-PnL spread + param points for distribution / scatter / heatmap
        out["dist"] = downsample_pnls([r.get("total_pnl", 0) for r in records])
        # pnl AND dd per config (dd = drawdown magnitude, engine pts) so the web's param
        # charts can plot risk metrics too (ORB.md item L); MAR derived client-side.
        _pts_full = [dict({k: r.get(k) for k in pkeys}, pnl=round(float(r.get("total_pnl", 0) or 0), 1),
                          dd=round(abs(float(r.get("max_drawdown", 0) or 0)), 1))
                     for r in records]
        out["points"] = downsample_points(_pts_full)
        _rel = relationship_scores(_pts_full)   # Pearson / MI / PPS per param vs PnL (ROADMAP #24)
        if _rel:
            out["relationship"] = _rel
        # 3C.1 PDP-plateau pick on the sampler's evaluated configs (ROADMAP #24a)
        _pp = pdp_plateau(_pts_full)
        _plateau_records = records
        if _pp:
            # AUTO-EXPAND-AND-RESAMPLE: a truncated search (edge-pinned + still rising
            # NUMERIC knob) gets its range widened and re-sampled instead of just
            # flagged. Scoped to plateau_pick alone — see _auto_expand_search's
            # docstring for why best/top/DSR/MC/etc. never see the expansion records.
            if auto_expand and _pp.get("search_truncated"):
                _epp, _elog, _erecs, _esummary = _auto_expand_search(
                    records, seen, pkeys, space, dp, _ev, ksplit, min_trades,
                    seed, n_trials, _pp["boundary_flags"],
                    max_rounds=auto_expand_max_rounds,
                    max_global_rounds=auto_expand_max_global_rounds)
                if _elog:
                    out["auto_expand"] = _elog
                    out["auto_expand_summary"] = _esummary
                    if _epp:
                        _pp = _epp
                        _plateau_records = _erecs
                        # The CHARTS must show the widened search too: rebuild the
                        # per-config points (2B/2C/2H/2I/2J) and the param-relationship
                        # scores from the merged records, so the taper past the original
                        # range is actually drawn instead of ending at the old edge.
                        # Selection outputs (best/top/DSR/MC) still never see these.
                        _pts_full = [dict({k: r.get(k) for k in pkeys},
                                          pnl=round(float(r.get("total_pnl", 0) or 0), 1),
                                          dd=round(abs(float(r.get("max_drawdown", 0) or 0)), 1))
                                     for r in _plateau_records]
                        out["points"] = downsample_points(_pts_full)
                        _rel2 = relationship_scores(_pts_full)
                        if _rel2:
                            out["relationship"] = _rel2
            _pi = _pp.pop("index")
            _prow = _plateau_records[_pi]
            _bp = {k: best.get(k) for k in pkeys if k in best}
            out["plateau_pick"] = {
                "params": {k: _prow.get(k) for k in pkeys},
                "metrics": {k: _prow.get(k) for k in _METRIC_KEYS if k in _prow},
                "score": _pp["score"], "argmax_score": _pp["argmax_score"],
                "curves": _pp["curves"],
                # boundary-peak detector (3C.1b): flags knobs whose optimum is pinned
                # at the tested-range edge and still rising → search was truncated.
                # Reflects the FINAL (post-expansion) surface when auto_expand fired.
                "boundary_flags": _pp["boundary_flags"],
                "search_truncated": _pp["search_truncated"],
                "same_as_best": bool({k: _prow.get(k) for k in pkeys} == _bp),
            }

        # Multi-surrogate bake-off READ-OUT (#31 P1, docs/SURROGATE_DISCOVERY_DESIGN.md).
        # Opt-in (default False) until reviewed. Fits the bake-off to the SAME configs
        # the search already evaluated (`_pts_full` — includes auto-expand resamples
        # when the range was widened, so the models see the full explored space) — no
        # steering (P2), the sampler itself is untouched. `ground_truth_fn` reuses the
        # exact IS evaluator every sampled point already went through (_ev(0, ksplit,
        # ...), same costs applied) — never a new/different backtest path. A surrogate
        # failure must never kill the run, hence the blanket try/except.
        if compute_surrogate:
            try:
                from .surrogate import surrogate_bakeoff

                def _surrogate_ground_truth(params):
                    return _ev(0, ksplit, params)

                _surr = surrogate_bakeoff(_pts_full, pkeys, dp,
                                         ground_truth_fn=_surrogate_ground_truth)
                if _surr is not None:
                    out["surrogate"] = _surr
            except Exception as _surr_e:
                out["surrogate"] = {"error": str(_surr_e)}

    # ── Regime report card + neighborhood robustness on the winner (opt-in) ──
    if (compute_regime or compute_neighbors) and best:
        bp0 = {k: best.get(k) for k in pkeys if k in best}

        def _eval_full(pp):
            ex = {}
            if pass_vol:
                ex["volumes"] = V
            if pass_day:
                ex["day_id"] = did
            if pass_idx:
                ex["index"] = IDX
            try:
                if cost_pts > 0:
                    m = fn(O, H, L, C, return_trades=True, **ex, **pp)
                    if m:
                        m = _apply_costs(m, cost_pts)
                    return m
                return fn(O, H, L, C, return_trades=True, **ex, **pp)
            except Exception:
                return None

        if compute_regime:
            wm = _eval_full(bp0)
            idx = arrays.get("index")
            if wm and wm.get("trades") and idx is not None:
                rr = regime_report(wm["trades"], idx, H, L, C, cost_pts=cost_pts)
                if rr:
                    out["regime"] = rr
        if compute_neighbors:
            # No discrete grid in auto search → derive ±1 candidates from each
            # numeric param's DEFAULT_PARAMS step around the winner value.
            vopts = {}
            for k in pkeys:
                meta = dp.get(k, {})
                if not isinstance(meta, dict) or meta.get("type") not in ("int", "float"):
                    continue
                bv = bp0.get(k)
                if bv is None:
                    continue
                step = meta.get("step") or (1 if meta.get("type") == "int" else 0)
                if not step:
                    continue
                lo, hi = meta.get("min"), meta.get("max")
                cand = sorted({bv,
                               (bv - step if lo is None else max(lo, bv - step)),
                               (bv + step if hi is None else min(hi, bv + step))})
                if len(cand) > 1:
                    vopts[k] = cand
            if vopts:
                nb = neighborhood(lambda pp: _eval_full(pp), bp0, vopts)
                if nb:
                    out["neighborhood"] = nb

    # ── Winner analytics (equity + MC + DSR), same as run_grid ──────────────
    if (compute_dsr or mc_sims) and best:
        if years is None:
            try:
                idx = arrays.get("index")
                years = max(0.1, (idx[-1] - idx[0]).days / 365.25)
            except Exception:
                years = 1.0
        bp = {k: best.get(k) for k in pkeys if k in best}

        def _net_pnls(pp, a=0, b=n):
            ex = {}
            if pass_vol:
                ex["volumes"] = V[a:b]
            if pass_day:
                ex["day_id"] = did[a:b]
            if pass_idx:
                ex["index"] = IDX[a:b]
            try:
                m = fn(O[a:b], H[a:b], L[a:b], C[a:b], return_trades=True, **ex, **pp)
            except Exception:
                return None
            if not m or not m.get("trades"):
                return None
            return [t[2] - cost_pts for t in m["trades"]]

        win_pnls = _net_pnls(bp)
        if win_pnls:
            cum, s = [], 0.0
            for x in win_pnls:
                s += x; cum.append(s)
            if len(cum) > 160:
                st = len(cum) / 160
                cum = [cum[int(i * st)] for i in range(160)]
            out["equity"] = {"cum": [round(float(x), 1) for x in cum],
                             "final": round(float(s), 1), "n": len(win_pnls)}
            # Winner's per-trade PnL sample (downsampled) for the trade-PnL distribution curve.
            _wd = win_pnls
            if len(_wd) > 400:
                _ds = len(_wd) / 400
                _wd = [_wd[int(i * _ds)] for i in range(400)]
            out["win_dist"] = [round(float(x), 2) for x in _wd]
            try:    # MAE/MFE (rich 5-tuple trades only; None for legacy strategies)
                _exf = {}
                if pass_vol:
                    _exf["volumes"] = V
                if pass_day:
                    _exf["day_id"] = did
                if pass_idx:
                    _exf["index"] = IDX
                _wm = fn(O, H, L, C, return_trades=True, **_exf, **bp)
                if _wm and _wm.get("trades"):
                    _mm = mae_mfe(_wm["trades"], H, L)
                    if _mm:
                        out["mae_mfe"] = _mm
            except Exception:
                pass
            if not is_wf:   # top-N equity overlay (robustness of the best configs)
                etop = []
                for r_ in ranked[:50]:   # top config equity curves for the TOP CONFIGS PNL overlay
                    pp = {k: r_.get(k) for k in pkeys if k in r_}
                    pn = _net_pnls(pp)
                    if not pn:
                        continue
                    cc, ss = [], 0.0
                    for x in pn:
                        ss += x; cc.append(ss)
                    if len(cc) > 80:
                        st2 = len(cc) / 80
                        cc = [cc[int(i * st2)] for i in range(80)]
                    etop.append({"cum": [round(float(x), 1) for x in cc]})   # map, not nested array
                out["equity_top"] = etop
                if len(win_pnls) >= 16:   # PnL across 8 chronological windows
                    N = 8; sz = len(win_pnls) // N
                    out["stress"] = [round(float(sum(win_pnls[i*sz:(len(win_pnls) if i == N-1 else (i+1)*sz)])), 1)
                                     for i in range(N)]
            if mc_sims:
                out["mc"] = monte_carlo_drawdown(win_pnls, n_sims=int(mc_sims))
            if compute_dsr:
                srs = []
                for r in ranked[:40]:
                    pp = {k: r.get(k) for k in pkeys if k in r}
                    pn = _net_pnls(pp)
                    sr = annualized_sr(pn, years) if pn else None
                    if sr:
                        srs.append(sr["sr"])
                out["dsr"] = deflated_sharpe(annualized_sr(win_pnls, years), srs,
                                             len(records), years)
    # MAE/MFE always (cheap winner backtest) so AI-loop diagnostics get it too.
    if best and "mae_mfe" not in out:
        try:
            _bp = {k: best.get(k) for k in pkeys if k in best}
            _exf = {}
            if pass_vol:
                _exf["volumes"] = V
            if pass_day:
                _exf["day_id"] = did
            if pass_idx:
                _exf["index"] = IDX
            _wm = fn(O, H, L, C, return_trades=True, **_exf, **_bp)
            if _wm and _wm.get("trades"):
                _mm = mae_mfe(_wm["trades"], H, L)
                if _mm:
                    out["mae_mfe"] = _mm
        except Exception:
            pass

    # ── Diagnostic 'pills' (opt-in) — the same informational robustness checks
    #    Auto-Validate runs, MINUS the lockbox-specific adversarial gate (Auto-Optimize
    #    has no lockbox). Attached as top-level result keys so the report renders them
    #    exactly like a validate run. Each pill self-guards; the block never fails a run. ──
    if compute_pills and best:
        try:
            from .analytics import run_pills
            _cbp = {k: best.get(k) for k in pkeys if k in best}
            _cexf = {}
            if pass_vol:
                _cexf["volumes"] = V
            if pass_day:
                _cexf["day_id"] = did
            if pass_idx:
                _cexf["index"] = IDX
            _ctrades = None
            try:
                _cwm = fn(O, H, L, C, return_trades=True, **_cexf, **_cbp)
                _ctrades = _cwm.get("trades") if _cwm else None
            except Exception:
                _ctrades = None
            _sib = {"NQ": "ES", "ES": "NQ", "MNQ": "MES", "MES": "MNQ",
                    "RTY": "M2K", "M2K": "RTY", "YM": "MYM", "MYM": "YM"}.get(
                        str(instrument or "").upper())
            _pill = run_pills(arrays, champ_trades=_ctrades, cost_pts=cost_pts,
                              instrument=instrument, timeframe=timeframe, session=session,
                              source=source, lb_start=None, sibling=_sib)
            for _pk, _pv in (_pill or {}).items():
                if _pv is not None:
                    out[_pk] = _pv
        except Exception:
            pass
    return out

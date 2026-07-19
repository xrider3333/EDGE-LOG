"""Unit tests for AUTO-EXPAND-AND-RESAMPLE (augur_engine.auto) — the owner's
"if adjusting a knob continues to help, push the knob further" request, built on top
of the boundary-peak detector (commit 5df5a76, analytics._pdp_boundary_flags).

Two layers:
  1. Pure unit tests of the factored-out arithmetic helpers (`_expand_range`,
     `_snap_to_step`) — no backtest, no sampler, hand-checkable numbers.
  2. End-to-end tests of `run_auto` driving a tiny SYNTHETIC strategy (a single
     numeric "knob" param whose PnL is a hand-picked deterministic function of the
     knob value, independent of the OHLC content) so the whole
     search -> plateau -> boundary-flag -> expand -> re-search loop is exercised
     without touching real data or strategy files, and runs in well under a second.

All run_auto calls use oos=False (forces the non-walkforward path regardless of
`method`, so `arrays` can be a handful of bars) and min_trades=1 (the fake
run_backtest always reports num_trades=50, so this just avoids depending on that
constant). seed=42 everywhere, matching the module default, for reproducibility.
"""
import types

import numpy as np
import pytest

import augur_engine.auto as auto_mod
from augur_engine.auto import (run_auto, _expand_range, _snap_to_step,
                                AUTO_EXPAND_WIDTH_CAP, AUTO_EXPAND_SPAN_FRAC)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — pure arithmetic helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_expand_range_max_edge_extends_by_half_original_width():
    # orig [0,20] width=20 -> span = max(step, 0.5*20) = 10 -> new hi = 20+10 = 30
    lo, hi = _expand_range(lo=0.0, hi=20.0, step=1.0, kind="float", edge="max",
                           orig_lo=0.0, orig_hi=20.0)
    assert (lo, hi) == (0.0, 30.0)


def test_expand_range_min_edge_extends_by_half_original_width():
    lo, hi = _expand_range(lo=0.0, hi=20.0, step=1.0, kind="float", edge="min",
                           orig_lo=0.0, orig_hi=20.0)
    assert (lo, hi) == (-10.0, 20.0)


def test_expand_range_span_is_at_least_one_step_on_a_tiny_range():
    # orig [0,1] width=1 -> 0.5*1=0.5 < step=1 -> span floors to step=1
    lo, hi = _expand_range(lo=0.0, hi=1.0, step=1.0, kind="int", edge="max",
                           orig_lo=0.0, orig_hi=1.0)
    assert (lo, hi) == (0.0, 2.0)


def test_expand_range_never_crosses_hard_max():
    lo, hi = _expand_range(lo=0.0, hi=20.0, step=1.0, kind="float", edge="max",
                           orig_lo=0.0, orig_hi=20.0, hard_max=25.0)
    assert hi == 25.0                       # would be 30 uncapped; hard_max wins


def test_expand_range_never_crosses_hard_min():
    lo, hi = _expand_range(lo=0.0, hi=20.0, step=1.0, kind="float", edge="min",
                           orig_lo=0.0, orig_hi=20.0, hard_min=-5.0)
    assert lo == -5.0                       # would be -10 uncapped; hard_min wins


def test_expand_range_fallback_cap_is_2x_original_width():
    # Simulate "already widened once": cur hi=30 (orig 20 -> +10). Next push wants
    # +10 more = 40, and the 2x-width fallback cap is EXACTLY orig_lo + 2*20 = 40.
    lo, hi = _expand_range(lo=0.0, hi=30.0, step=1.0, kind="float", edge="max",
                           orig_lo=0.0, orig_hi=20.0)
    assert hi == 40.0
    assert (hi - lo) <= AUTO_EXPAND_WIDTH_CAP * 20.0


def test_expand_range_is_a_noop_when_no_room_left():
    # hi already AT hard_max -> nothing to gain, must return the SAME bounds so the
    # caller can detect "stuck" and stop without wasting a resample round.
    lo, hi = _expand_range(lo=0.0, hi=25.0, step=1.0, kind="float", edge="max",
                           orig_lo=0.0, orig_hi=20.0, hard_max=25.0)
    assert (lo, hi) == (0.0, 25.0)


def test_expand_range_never_shrinks():
    # A pathological hard_max below the CURRENT hi must not pull the edge inward.
    lo, hi = _expand_range(lo=0.0, hi=20.0, step=1.0, kind="float", edge="max",
                           orig_lo=0.0, orig_hi=20.0, hard_max=5.0)
    assert hi == 20.0


def test_snap_to_step_aligns_to_anchor_grid():
    assert _snap_to_step(23.3, 5.0, "float", anchor=0.0) == 25.0
    assert _snap_to_step(23.3, 5.0, "int", anchor=0.0) == 25
    assert _snap_to_step(7.0, 0, "float", anchor=0.0) == 7.0   # step=0 -> no-op


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — end-to-end run_auto with a synthetic single-knob strategy
# ─────────────────────────────────────────────────────────────────────────────

N_TRIALS = 40
MIN_TRADES = 1
SEED = 42


def _make_strategy(pnl_of_knob, pmin=0.0, pmax=20.0, pstep=1.0, extra_param_meta=None):
    """A minimal fake strategy module: one numeric knob, PnL a pure function of it.
    total_pnl is entirely deterministic in `knob` (ignores the OHLC content), so the
    boundary-peak / plateau behavior is fully controlled by the test, not by noise."""
    mod = types.ModuleType("fake_synthetic_strategy")
    mod.STRATEGY_NAME = "SYNTHETIC (test only)"
    meta = {"type": "float", "min": pmin, "max": pmax, "step": pstep,
            "default": (pmin + pmax) / 2.0}
    if extra_param_meta:
        meta.update(extra_param_meta)
    mod.DEFAULT_PARAMS = {"knob": meta}

    def run_backtest(opens, highs, lows, closes, knob=None, return_trades=False, **_ignore):
        pnl = float(pnl_of_knob(knob))
        out = {"total_pnl": pnl, "num_trades": 50, "win_rate": 60.0,
               "profit_factor": 1.5, "max_drawdown": -100.0, "avg_pnl": pnl / 50.0,
               "wins": 30, "losses": 20}
        if return_trades:
            out["trades"] = []          # no MAE/MFE needed for this test
        return out

    mod.run_backtest = run_backtest
    return mod


def _make_arrays(n=60):
    """Tiny constant OHLCV — content is irrelevant since the fake strategy's PnL
    depends only on `knob`, so this just needs to be array-shaped and fast."""
    return {"open": np.full(n, 100.0), "high": np.full(n, 101.0),
            "low": np.full(n, 99.0), "close": np.full(n, 100.0),
            "volume": np.full(n, 1000.0), "day_id": (np.arange(n) // 6).astype("int64"),
            "index": None, "meta": {"name": "SYN"}}


def _run(mod, **kw):
    kw.setdefault("oos", False)
    kw.setdefault("method", "single")
    kw.setdefault("n_trials", N_TRIALS)
    kw.setdefault("min_trades", MIN_TRADES)
    kw.setdefault("seed", SEED)
    return run_auto(mod, arrays=_make_arrays(), **kw)


# (a) + (b): a knob that rises FOREVER (no ceiling) is edge-pinned every round ──────

def test_ever_rising_knob_expands_and_hits_max_rounds_capped_and_untapered():
    mod = _make_strategy(lambda k: k * 100.0)          # strictly increasing, no ceiling
    out = _run(mod, auto_expand=True, auto_expand_max_rounds=2)

    pp = out["plateau_pick"]
    assert pp["search_truncated"] is True              # still truncated — genuinely never tapers
    assert "auto_expand" in out
    log = out["auto_expand"]
    assert len(log) == 1
    entry = log[0]
    assert entry["param"] == "knob"
    orig_lo, orig_hi = entry["orig_range"]
    fin_lo, fin_hi = entry["final_range"]
    assert (orig_lo, orig_hi) == (0.0, 20.0)

    # (a) the range was actually widened, at least one round happened
    assert entry["rounds"] >= 1
    assert fin_hi > orig_hi and fin_lo == orig_lo

    # (b) gives up at max_rounds, marks untapered, and respects the 2x-width cap
    assert entry["rounds"] == 2                        # exhausted auto_expand_max_rounds=2
    assert entry["tapered"] is False
    assert (fin_hi - fin_lo) <= AUTO_EXPAND_WIDTH_CAP * (orig_hi - orig_lo) + 1e-6
    assert "still rising" in entry["note"]

    # the plateau pick itself must reflect the EXPANDED/merged surface, not the
    # original un-expanded sample (its param value should sit at the new edge).
    assert pp["params"]["knob"] == fin_hi


def test_ever_rising_knob_taper_stops_early_when_peak_lands_just_inside_round1():
    # Peak at 25 sits just OUTSIDE the original [0,20] range but INSIDE round 1's
    # widened [0,30] range -> should taper (interior optimum found) after exactly
    # 1 round, distinct from the "never tapers" case above.
    mod = _make_strategy(lambda k: 1000.0 - (k - 25.0) ** 2 * 5.0, pmin=0.0, pmax=20.0)
    out = _run(mod, auto_expand=True, auto_expand_max_rounds=2)

    log = out["auto_expand"]
    assert len(log) == 1
    entry = log[0]
    assert entry["rounds"] == 1
    assert entry["tapered"] is True
    assert entry["final_range"][1] > 20.0                # widened at least once
    assert out["plateau_pick"]["search_truncated"] is False   # fixed by expansion

    # (c) convergence: nothing left flagged when the loop stopped -> converged=True,
    # and it stopped well before the (default 6) global-round budget.
    assert entry["emerged"] is False                    # was in the initial flags, not chased-in
    summ = out["auto_expand_summary"]
    assert summ == {"global_rounds_used": 1, "n_params_expanded": 1,
                    "n_emerged": 0, "converged": True}


# (c): an interior optimum from the start triggers NO expansion ───────────────────

def test_interior_optimum_triggers_no_expansion():
    mod = _make_strategy(lambda k: 1000.0 - (k - 10.0) ** 2 * 5.0)   # peak at knob=10 (mid-range)
    out = _run(mod, auto_expand=True, auto_expand_max_rounds=2)

    pp = out["plateau_pick"]
    assert pp["boundary_flags"] == []
    assert pp["search_truncated"] is False
    assert not out.get("auto_expand")                  # empty or absent — nothing to expand
    assert pp["params"]["knob"] == 10.0                 # picked the true interior peak


# (d): auto_expand=False reproduces the pre-expansion behavior exactly ────────────

def test_auto_expand_false_is_fully_inert():
    mod = _make_strategy(lambda k: k * 100.0)           # same edge-pinned-forever knob as (a)/(b)
    out = _run(mod, auto_expand=False)

    assert "auto_expand" not in out                    # feature left no trace at all
    pp = out["plateau_pick"]
    assert pp["search_truncated"] is True               # truncation reported but NOT fixed
    assert pp["params"]["knob"] == 20.0                  # original tested max — range untouched
    assert len(pp["boundary_flags"]) == 1
    assert pp["boundary_flags"][0]["tested_max"] == 20.0

    # determinism: auto_expand=False must be byte-for-byte reproducible (no stray
    # randomness leaks in even though the feature is switched off)
    out_again = _run(mod, auto_expand=False)
    assert out_again["plateau_pick"] == pp
    assert "auto_expand" not in out_again


def test_auto_expand_true_vs_false_only_differ_when_truncated():
    # On the INTERIOR fixture (no truncation), True and False must agree exactly —
    # the feature only ever activates on a truncated search.
    mod = _make_strategy(lambda k: 1000.0 - (k - 10.0) ** 2 * 5.0)
    out_true = _run(mod, auto_expand=True)
    out_false = _run(mod, auto_expand=False)
    assert out_true["plateau_pick"] == out_false["plateau_pick"]
    assert "auto_expand" not in out_true and "auto_expand" not in out_false


# ─────────────────────────────────────────────────────────────────────────────
# hard_min/hard_max opt-in convention (NEW; no shipped strategy declares it yet)
# ─────────────────────────────────────────────────────────────────────────────

def test_hard_max_convention_stops_expansion_at_the_declared_bound():
    mod = _make_strategy(lambda k: k * 100.0, extra_param_meta={"hard_max": 25.0})
    out = _run(mod, auto_expand=True, auto_expand_max_rounds=3)

    log = out["auto_expand"]
    assert len(log) == 1
    entry = log[0]
    assert entry["final_range"][1] == 25.0              # clamped to hard_max, not the 2x cap (40)
    assert entry["tapered"] is False
    assert "hard_min/hard_max bound" in entry["note"]
    assert out["plateau_pick"]["params"]["knob"] == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# walk-forward path is untouched — auto_expand only ever applies to the non-WF pick
# ─────────────────────────────────────────────────────────────────────────────

def test_walkforward_runs_never_build_auto_expand():
    mod = _make_strategy(lambda k: k * 100.0)
    # run_auto only takes the true walk-forward branch when method="walkforward" AND
    # oos_on AND n>=4000 (see run_auto's `if method == "walkforward" and oos_on and
    # n >= 4000:`); below that it silently falls back to the single-split path, which
    # DOES build plateau_pick. So this needs a real >=4000-bar array to exercise the
    # WF branch and confirm auto_expand truly never touches it. The fake strategy's
    # PnL ignores OHLC content, so the extra bars cost nothing at runtime.
    out = run_auto(mod, arrays=_make_arrays(n=4200), method="walkforward", oos=True,
                    n_trials=N_TRIALS, min_trades=MIN_TRADES, seed=SEED,
                    auto_expand=True)
    assert out["wf"] is True                           # sanity: actually took the WF branch
    assert "plateau_pick" not in out
    assert "auto_expand" not in out


# ─────────────────────────────────────────────────────────────────────────────
# ITERATIVE COORDINATE-DESCENT (owner request #30, 2026-07-18) — every round
# re-checks ALL params, not just the ones flagged in the very first pdp_plateau
# call, so a param that only becomes edge-pinned AFTER another param's range is
# widened (an "unlock") gets chased too, instead of silently dropped (the bug
# observed live on TTIBS's `hold_cap`).
# ─────────────────────────────────────────────────────────────────────────────

def _make_strategy_2knob(pnl_of_ab, pmin=0.0, pmax=20.0, pstep=1.0):
    """Two-numeric-knob fake strategy (mirrors `_make_strategy` above, just with
    an extra param) so an INTERACTION between two knobs can be expressed."""
    mod = types.ModuleType("fake_synthetic_strategy_2knob")
    mod.STRATEGY_NAME = "SYNTHETIC 2-KNOB (test only)"
    meta = {"type": "float", "min": pmin, "max": pmax, "step": pstep,
            "default": (pmin + pmax) / 2.0}
    mod.DEFAULT_PARAMS = {"a": dict(meta), "b": dict(meta)}

    def run_backtest(opens, highs, lows, closes, a=None, b=None, return_trades=False,
                     **_ignore):
        pnl = float(pnl_of_ab(a, b))
        out = {"total_pnl": pnl, "num_trades": 50, "win_rate": 60.0,
               "profit_factor": 1.5, "max_drawdown": -100.0, "avg_pnl": pnl / 50.0,
               "wins": 30, "losses": 20}
        if return_trades:
            out["trades"] = []
        return out

    mod.run_backtest = run_backtest
    return mod


# (b) THE KEY NEW TEST — an "unlock": b's optimum is interior against a's ORIGINAL
# [0,20] range (so the OLD single-pass expander would never have touched it), but
# the joint surface has b*a interaction strong enough that once a's range widens
# past 20 and gets re-sampled, b's own marginal curve tips over into edge-pinned.
# PnL(a, b) = 5a - 0.5(b-5)^2 + 5ab -- for a<=20 the interaction term is modest next
# to the -0.5(b-5)^2 anchor (interior optimum near b=5); once a>20 (only reachable
# after a's own range is widened) the 5ab term dominates and pulls b's aggregate
# curve toward its tested-max edge. n_trials=300 (still a sub-second synthetic
# backtest -- PnL is a closed-form function, no real OHLC work) so the interaction
# signal clears noise robustly; smaller counts made this flaky against the exact
# grid the seeded sampler happens to draw.
def _unlock_pnl(a, b):
    return 5.0 * a - 0.5 * (b - 5.0) ** 2 + 5.0 * a * b


def test_interaction_unlocks_previously_interior_param_and_new_search_chases_it():
    mod = _make_strategy_2knob(_unlock_pnl)

    # (a) OLD single-pass behavior, reproduced via auto_expand=False: this is
    # EXACTLY the initial (unexpanded) boundary_flags the single-pass expander
    # would have seeded `active` from -- 'a' is edge-pinned (still rising), 'b' is
    # NOT -- so the pre-#30 code would never have chased 'b' at all.
    out_old = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                        n_trials=300, min_trades=1, seed=SEED, auto_expand=False)
    pp_old = out_old["plateau_pick"]
    old_flags = {f["param"]: f["edge"] for f in pp_old["boundary_flags"]}
    assert old_flags == {"a": "max"}                    # only 'a' -- 'b' NOT flagged initially
    assert pp_old["search_truncated"] is True

    # (b) NEW iterative coordinate-descent: run the same fixture with auto_expand
    # on. 'b' must show up in out["auto_expand"] with emerged=True -- proof the
    # new loop re-checked ALL params after widening 'a' and caught the unlock.
    out_new = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                        n_trials=300, min_trades=1, seed=SEED, auto_expand=True)
    log = out_new["auto_expand"]
    by_param = {e["param"]: e for e in log}
    assert "b" in by_param
    b_entry = by_param["b"]
    assert b_entry["emerged"] is True
    assert "emerged mid-run after widening" in b_entry["note"]
    assert "a" in b_entry["note"]                       # names the param that unlocked it

    # 'a' itself was in the INITIAL flags, not chased-in.
    assert by_param["a"]["emerged"] is False

    summ = out_new["auto_expand_summary"]
    assert summ["n_emerged"] >= 1
    assert summ["n_params_expanded"] == len(log)
    assert summ["global_rounds_used"] >= 2               # 'b' can't emerge before round 2

    # determinism: re-running with the same seed reproduces the exact same log +
    # summary (no stray randomness leaks into the iterative loop).
    out_new2 = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                         n_trials=300, min_trades=1, seed=SEED, auto_expand=True)
    assert out_new2["auto_expand"] == log
    assert out_new2["auto_expand_summary"] == summ


# (d) max_global_rounds caps a pathological always-rising synthetic, INDEPENDENT
# of the per-param cap -- set auto_expand_max_rounds huge (so it would never bind
# on its own) and auto_expand_max_global_rounds tiny, and confirm the OUTER cap is
# what stops the loop (not a taper, not the per-param round cap, not the 2x-width
# fallback -- which only trips on round 2 with the default 50%-span, one round
# later than the global cap used here).
def test_max_global_rounds_caps_runaway_search_independent_of_per_param_cap():
    mod = _make_strategy(lambda k: k * 100.0)            # never tapers, no hard bounds
    out = _run(mod, auto_expand=True, auto_expand_max_rounds=50,
               auto_expand_max_global_rounds=1)

    log = out["auto_expand"]
    assert len(log) == 1
    entry = log[0]
    assert entry["rounds"] == 1                          # only ONE round happened at all
    assert entry["tapered"] is False
    assert "auto_expand_max_global_rounds" in entry["note"]
    # NOT the width-cap or per-param-cap language (those didn't fire -- the outer
    # cap got there first):
    assert "2x-width" not in entry["note"]
    assert "hit auto_expand_max_rounds" not in entry["note"]

    summ = out["auto_expand_summary"]
    assert summ == {"global_rounds_used": 1, "n_params_expanded": 1,
                    "n_emerged": 0, "converged": False}   # hit the cap -- did NOT converge


# (e) no-re-add policy: once a param is finalized it must NEVER be re-chased, even
# if a later round's pdp_plateau claims it's flagged again -- this is the guard
# against A-unlocks-B-unlocks-A-forever oscillation. Proven deterministically by
# monkeypatching pdp_plateau itself (independent of any real sampler noise): 'a'
# is flagged only on the very first call (mimicking the initial boundary_flags),
# then EVERY subsequent call claims BOTH 'a' and 'b' are edge-pinned FOREVER --
# exactly the condition that would re-add 'a' to `active` on every later round
# without the no-re-add guard. auto_expand_max_rounds=1 so both params finalize
# quickly (capped, still "rising" per the mock) and the test proves 'a' shows up
# in the log EXACTLY once despite the mock's endless claim.
def test_no_re_add_policy_prevents_oscillation(monkeypatch):
    def _flag(pname):
        return {"param": pname, "edge": "max", "value": 20.0, "rel_slope": 0.5,
                "tested_min": 0.0, "tested_max": 20.0, "n_values": 5, "msg": "x"}

    calls = {"n": 0}

    def fake_pdp_plateau(points, pnl_key="pnl", min_points=12):
        calls["n"] += 1
        flags = [_flag("a")] if calls["n"] == 1 else [_flag("a"), _flag("b")]
        return {"index": 0, "params": {"a": 20.0, "b": 20.0}, "score": 0.0,
                "argmax_score": 0.0, "argmax_index": 0, "curves": {},
                "boundary_flags": flags, "search_truncated": True}

    monkeypatch.setattr(auto_mod, "pdp_plateau", fake_pdp_plateau)

    mod = _make_strategy_2knob(lambda a, b: 5.0 * a + 5.0 * b)
    out = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                    n_trials=N_TRIALS, min_trades=1, seed=SEED, auto_expand=True,
                    auto_expand_max_rounds=1, auto_expand_max_global_rounds=6)

    assert calls["n"] >= 3                               # the mock really was called repeatedly
    log = out["auto_expand"]
    names = [e["param"] for e in log]
    assert names.count("a") == 1                          # NOT re-chased despite endless "still flagged"
    assert names.count("b") == 1
    by_param = {e["param"]: e for e in log}
    assert by_param["a"]["emerged"] is False               # 'a' was in the initial flags
    assert by_param["b"]["emerged"] is True                # 'b' emerged after 'a' widened

    # loop terminated well inside the (generous) global-round budget, proving the
    # finalized-set guard -- not the outer cap -- is what stopped the chase.
    summ = out["auto_expand_summary"]
    assert summ["global_rounds_used"] < 6
    assert summ["converged"] is True                       # OUR tracked set drained on its own
    # ...even though the mocked surface never stopped claiming truncation --
    # exactly the documented nuance (no-re-add can leave pp["search_truncated"]
    # True while our own bookkeeping is done chasing).
    assert out["plateau_pick"]["search_truncated"] is True

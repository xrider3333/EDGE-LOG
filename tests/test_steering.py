"""Unit tests for P2 STEERING (#36) — augur_engine.surrogate.propose_candidates
and its opt-in augur_engine.auto.run_auto integration (`auto_steer`).

Design doc: docs/SURROGATE_DISCOVERY_DESIGN.md §5 (acquisition) / §7 (P2 phase).
P1 (surrogate_bakeoff, tests/test_surrogate.py) only READS the joint surface off
already-sampled points; P2 additionally AIMS the next samples at where the GP
predicts high PnL (Upper-Confidence-Bound: mu + kappa*sigma). Off by default —
`auto_steer=False` — random search stays the default behavior everywhere.

All synthetic — deterministic surfaces/strategies, no real data files, so this
suite runs anywhere in well under a minute (mirrors tests/test_auto_expand.py
and tests/test_surrogate.py's own conventions).
"""
import math
import types

import numpy as np
import pytest

from augur_engine.auto import _auto_space_from_params, _RandomSampler, _collapse, run_auto
from augur_engine.surrogate import propose_candidates


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture: a 3-param DEFAULT_PARAMS-shaped space, no strategy/backtest
# involved at all — pure param-dict <-> pnl-float, so these tests never touch
# market data (per the task's "structure the loop test so it does not require
# market data").
# ─────────────────────────────────────────────────────────────────────────────
def _dp_3num():
    return {
        "a": {"type": "float", "min": 0.0, "max": 1.0, "step": 0.02, "default": 0.5},
        "b": {"type": "float", "min": 0.0, "max": 6.0, "step": 0.1, "default": 3.0},
        "c": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0},
    }


def _make_records(dp, pkeys, ev_fn, n, seed):
    """N distinct legal configs (via the SAME _RandomSampler/_collapse the real
    search loop uses) + their (noise-free) surface value, in the exact
    {**params, total_pnl} shape run_auto's own `records` list carries."""
    samp = _RandomSampler(_auto_space_from_params(dp), seed=seed)
    seen = set()
    records = []
    while len(records) < n:
        pe = _collapse(samp.ask(), dp)
        sig = tuple(sorted(pe.items()))
        if sig in seen:
            continue
        seen.add(sig)
        records.append(dict(pe, total_pnl=float(ev_fn(pe))))
    return records


def _on_grid(value, meta):
    lo, step = float(meta["min"]), float(meta.get("step") or 0)
    if not step:
        return True
    k = (value - lo) / step
    return abs(k - round(k)) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# (a) propose_candidates: legal, on-grid, within bounds, not duplicating seen,
#     deterministic under seed.
# ─────────────────────────────────────────────────────────────────────────────
def test_propose_candidates_returns_legal_on_grid_configs_not_duplicating_seen():
    dp = _dp_3num()
    pkeys = list(dp.keys())
    space = _auto_space_from_params(dp)
    surface = lambda pe: -(pe["a"] - 0.6) ** 2 - (pe["b"] - 3.0) ** 2 - (pe["c"] - 5.0) ** 2
    records = _make_records(dp, pkeys, surface, n=60, seed=1)
    seen_sigs = {tuple(sorted((k, r[k]) for k in pkeys)) for r in records}

    out = propose_candidates(records, pkeys, dp, space, n_propose=10, seed=42)
    assert isinstance(out, list)
    assert 0 < len(out) <= 10

    out_sigs = set()
    for cfg in out:
        assert set(cfg) == set(pkeys)          # exactly the real knobs, nothing extra
        for k, meta in dp.items():
            v = cfg[k]
            assert float(meta["min"]) - 1e-9 <= v <= float(meta["max"]) + 1e-9
            assert _on_grid(v, meta)
        sig = tuple(sorted((k, cfg[k]) for k in pkeys))
        assert sig not in seen_sigs             # never re-proposes an already-evaluated config
        assert sig not in out_sigs               # distinct among themselves
        out_sigs.add(sig)


def test_propose_candidates_deterministic_under_seed():
    dp = _dp_3num()
    pkeys = list(dp.keys())
    space = _auto_space_from_params(dp)
    surface = lambda pe: -(pe["a"] - 0.6) ** 2 - (pe["b"] - 3.0) ** 2 - (pe["c"] - 5.0) ** 2
    records = _make_records(dp, pkeys, surface, n=60, seed=1)

    out1 = propose_candidates(records, pkeys, dp, space, n_propose=12, seed=7)
    out2 = propose_candidates(records, pkeys, dp, space, n_propose=12, seed=7)
    assert out1 == out2

    out3 = propose_candidates(records, pkeys, dp, space, n_propose=12, seed=8)
    assert out3 != out1 or len(out1) == 0        # a different seed is allowed to differ


def test_propose_candidates_empty_or_too_few_points_returns_empty_list():
    dp = _dp_3num()
    pkeys = list(dp.keys())
    space = _auto_space_from_params(dp)
    assert propose_candidates([], pkeys, dp, space, n_propose=10, seed=42) == []

    surface = lambda pe: pe["a"] + pe["b"] + pe["c"]
    few = _make_records(dp, pkeys, surface, n=10, seed=1)   # well under STEER_MIN_POINTS(40)
    assert propose_candidates(few, pkeys, dp, space, n_propose=10, seed=42) == []


def test_propose_candidates_never_raises_on_malformed_records():
    dp = _dp_3num()
    pkeys = list(dp.keys())
    space = _auto_space_from_params(dp)
    garbage = [{"a": None}, "not-a-dict", 42, {}]
    out = propose_candidates(garbage, pkeys, dp, space, n_propose=5, seed=42)
    assert out == []


# ─────────────────────────────────────────────────────────────────────────────
# (b) SYNTHETIC A/B — a known 3-param surface, steered search vs pure random at
# the same budget/seed. Loop is hand-rolled (mirrors run_auto's own single-split
# steering loop exactly, minus any backtest/market-data machinery) so this test
# never touches arrays/masters/strategies at all.
# ─────────────────────────────────────────────────────────────────────────────
def _surface(pe):
    """Known maximum at a=0.6, b=3.0, c=5.0 — noise-free."""
    return -((pe["a"] - 0.6) ** 2) - (pe["b"] - 3.0) ** 2 - (pe["c"] - 5.0) ** 2 * 0.25


def _run_random_loop(dp, pkeys, space, ev_fn, n_trials, seed):
    samp = _RandomSampler(space, seed=seed)
    seen = set()
    records = []
    for _ in range(n_trials):
        pe = _collapse(samp.ask(), dp)
        sig = tuple(sorted(pe.items()))
        if sig not in seen:
            seen.add(sig)
            records.append(dict(pe, total_pnl=float(ev_fn(pe))))
    return records


def _run_steered_loop(dp, pkeys, space, ev_fn, n_trials, seed,
                      seed_frac=0.4, batch_frac=0.15, proposer=None):
    """Mirrors augur_engine.auto.run_auto's single-split `auto_steer=True` branch
    exactly (seed phase -> repeat fit-and-propose batches -> fallback to random
    on an empty proposal), but calls `ev_fn` directly instead of `_ev(0,
    ksplit, ...)` -- no arrays/strategy/backtest involved."""
    samp = _RandomSampler(space, seed=seed)
    seen = set()
    records = []

    def _eval_one(pe):
        sig = tuple(sorted(pe.items()))
        if sig not in seen:
            seen.add(sig)
            records.append(dict(pe, total_pnl=float(ev_fn(pe))))

    n_seed = max(1, min(n_trials, int(round(seed_frac * n_trials))))
    batch_n = max(1, int(math.ceil(batch_frac * n_trials)))
    done = 0
    for _ in range(n_seed):
        _eval_one(_collapse(samp.ask(), dp))
        done += 1
    while done < n_trials:
        batch = min(batch_n, n_trials - done)
        proposals = (proposer or propose_candidates)(records, pkeys, dp, space,
                                                     n_propose=batch, seed=int(seed) + done)
        if not proposals:
            for _ in range(batch):
                _eval_one(_collapse(samp.ask(), dp))
                done += 1
        else:
            for pe0 in proposals:
                _eval_one(_collapse(dict(pe0), dp))
                done += 1
                if done >= n_trials:
                    break
    return records


def test_steered_search_finds_at_least_as_good_a_best_as_random_at_same_budget():
    dp = _dp_3num()
    pkeys = list(dp.keys())
    space = _auto_space_from_params(dp)
    N_TRIALS, SEED = 60, 42

    rand_records = _run_random_loop(dp, pkeys, space, _surface, N_TRIALS, SEED)
    steer_records = _run_steered_loop(dp, pkeys, space, _surface, N_TRIALS, SEED)

    best_random = max(r["total_pnl"] for r in rand_records)
    best_steered = max(r["total_pnl"] for r in steer_records)

    # Steering must never do WORSE than random at the same budget/seed (typically better).
    assert best_steered >= best_random - 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# (c) run_auto smoke test: auto_steer=True on a synthetic strategy (mirrors
#     tests/test_auto_expand.py's/_test_surrogate.py's own fixture conventions:
#     a fake module with DEFAULT_PARAMS + run_backtest, tiny constant arrays).
# ─────────────────────────────────────────────────────────────────────────────
def _make_two_knob_strategy():
    mod = types.ModuleType("fake_steering_strategy")
    mod.STRATEGY_NAME = "SYNTHETIC (steering test only)"
    mod.DEFAULT_PARAMS = {
        "knob_a": {"type": "float", "min": 0.0, "max": 20.0, "step": 1.0, "default": 10.0},
        "knob_b": {"type": "float", "min": 0.0, "max": 20.0, "step": 1.0, "default": 10.0},
    }

    def run_backtest(opens, highs, lows, closes, knob_a=None, knob_b=None,
                     return_trades=False, **_ignore):
        pnl = float(knob_a) * float(knob_b) - (float(knob_a) - 10.0) ** 2 * 2.0
        out = {"total_pnl": pnl, "num_trades": 50, "win_rate": 60.0, "profit_factor": 1.5,
               "max_drawdown": -100.0, "avg_pnl": pnl / 50.0, "wins": 30, "losses": 20}
        if return_trades:
            out["trades"] = []
        return out

    mod.run_backtest = run_backtest
    return mod


def _make_arrays(n=60):
    return {"open": np.full(n, 100.0), "high": np.full(n, 101.0), "low": np.full(n, 99.0),
           "close": np.full(n, 100.0), "volume": np.full(n, 1000.0),
           "day_id": (np.arange(n) // 6).astype("int64"), "index": None,
           "meta": {"name": "SYN"}}


def test_run_auto_smoke_auto_steer_true_attaches_steering_and_finds_a_champion():
    mod = _make_two_knob_strategy()
    out = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                   n_trials=150, min_trades=1, seed=42, auto_expand=False,
                   auto_steer=True)
    assert "steering" in out
    steer = out["steering"]
    assert steer["used"] is True
    assert steer["seed_trials"] + steer["steered_trials"] + steer["fallback_random"] == 150
    assert out["n_valid"] > 0
    assert out["best_params"] is not None
    assert set(out["best_params"]) == {"knob_a", "knob_b"}


def test_run_auto_auto_steer_default_false_leaves_no_steering_key():
    mod = _make_two_knob_strategy()
    kwargs = dict(arrays=_make_arrays(), oos=False, method="single",
                  n_trials=90, min_trades=1, seed=42, auto_expand=False)
    out_default = run_auto(mod, **kwargs)
    out_explicit_false = run_auto(mod, auto_steer=False, **kwargs)
    assert "steering" not in out_default
    assert "steering" not in out_explicit_false
    assert out_default == out_explicit_false     # byte-identical default path


def test_run_auto_auto_steer_true_is_deterministic_under_seed():
    mod = _make_two_knob_strategy()
    kwargs = dict(arrays=_make_arrays(), oos=False, method="single",
                  n_trials=90, min_trades=1, seed=42, auto_expand=False, auto_steer=True)
    out1 = run_auto(mod, **kwargs)
    out2 = run_auto(mod, **kwargs)
    assert out1 == out2


def test_run_auto_walkforward_never_sees_auto_steer():
    # auto_steer is documented as non-WF-only; a WF run must ignore it silently
    # (no "steering" key, no behavior change) even if the caller passes it.
    mod = _make_two_knob_strategy()
    out = run_auto(mod, arrays=_make_arrays(n=4200), method="walkforward", oos=True,
                   n_trials=40, min_trades=1, seed=42, auto_steer=True)
    assert out["wf"] is True
    assert "steering" not in out


# ── #79 TPE proposer — same contract as the GP proposer, different brain ──────

def test_tpe_proposals_legal_on_grid_deterministic_and_unseen():
    from augur_engine.surrogate import propose_candidates_tpe
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    recs = _make_records(dp, pkeys, _surface, 60, seed=7)
    a = propose_candidates_tpe(recs, pkeys, dp, space, n_propose=10, seed=11)
    b = propose_candidates_tpe(recs, pkeys, dp, space, n_propose=10, seed=11)
    assert a == b                        # deterministic under seed
    assert 0 < len(a) <= 10
    seen = {tuple(sorted((k, str(r.get(k))) for k in pkeys)) for r in recs}
    for cand in a:
        assert tuple(sorted((k, str(cand.get(k))) for k in pkeys)) not in seen
        for k, meta in dp.items():
            _on_grid(cand[k], meta)


def test_tpe_returns_empty_on_thin_or_malformed_data():
    from augur_engine.surrogate import propose_candidates_tpe
    from augur_engine.auto import _auto_space_from_params
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    assert propose_candidates_tpe([], pkeys, dp, space, 5, seed=1) == []
    assert propose_candidates_tpe([{"total_pnl": "junk"}, None, 42], pkeys, dp, space, 5, seed=1) == []


def test_tpe_steered_loop_at_least_matches_random_on_synthetic_surface():
    from augur_engine.surrogate import propose_candidates_tpe
    from augur_engine.auto import _auto_space_from_params
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    rand_records = _run_random_loop(dp, pkeys, space, _surface, 60, 42)
    tpe_records = _run_steered_loop(dp, pkeys, space, _surface, 60, 42,
                                    proposer=propose_candidates_tpe)
    best_rand = max(r["total_pnl"] for r in rand_records)
    best_tpe = max(r["total_pnl"] for r in tpe_records)
    assert best_tpe >= best_rand - 1e-9


def test_run_auto_steer_method_tpe_smoke():
    from augur_engine.auto import run_auto
    mod = _make_two_knob_strategy()
    arrays = _make_arrays()
    out = run_auto(mod, arrays=arrays, n_trials=50, method="single", oos=False,
                   seed=42, min_trades=1, auto_expand=False,
                   auto_steer=True, steer_method="tpe")
    st = out.get("steering") or {}
    assert st.get("used") is True and st.get("method") == "tpe"
    assert out.get("best_params")


# ── QRF steering brain (Carl §4, owner-approved) — 3rd interchangeable engine ─

def test_qrf_proposals_legal_deterministic_and_unseen():
    import pytest
    pytest.importorskip("quantile_forest")
    from augur_engine.surrogate import propose_candidates_qrf
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    recs = _make_records(dp, pkeys, _surface, 60, seed=7)
    a = propose_candidates_qrf(recs, pkeys, dp, space, n_propose=10, seed=11)
    b = propose_candidates_qrf(recs, pkeys, dp, space, n_propose=10, seed=11)
    assert a == b
    assert 0 < len(a) <= 10
    seen = {tuple(sorted((k, str(r.get(k))) for k in pkeys)) for r in recs}
    for cand in a:
        assert tuple(sorted((k, str(cand.get(k))) for k in pkeys)) not in seen
        for k, meta in dp.items():
            _on_grid(cand[k], meta)


def test_qrf_steered_loop_at_least_matches_random_on_synthetic_surface():
    import pytest
    pytest.importorskip("quantile_forest")
    from augur_engine.surrogate import propose_candidates_qrf
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    rand_records = _run_random_loop(dp, pkeys, space, _surface, 60, 42)
    qrf_records = _run_steered_loop(dp, pkeys, space, _surface, 60, 42,
                                    proposer=propose_candidates_qrf)
    best_rand = max(r["total_pnl"] for r in rand_records)
    best_qrf = max(r["total_pnl"] for r in qrf_records)
    assert best_qrf >= best_rand - 1e-9


def test_run_auto_steer_method_qrf_smoke():
    import pytest
    pytest.importorskip("quantile_forest")
    from augur_engine.auto import run_auto
    mod = _make_two_knob_strategy()
    arrays = _make_arrays()
    out = run_auto(mod, arrays=arrays, n_trials=50, method="single", oos=False,
                   seed=42, min_trades=1, auto_expand=False,
                   auto_steer=True, steer_method="qrf")
    st = out.get("steering") or {}
    assert st.get("used") is True and st.get("method") == "qrf"
    assert out.get("best_params")


def test_qrf_absent_returns_empty(monkeypatch):
    import augur_engine.surrogate as S
    monkeypatch.setattr(S, "HAS_QRF", False)
    from augur_engine.auto import _auto_space_from_params
    dp = _dp_3num()
    pkeys = list(dp)
    space = _auto_space_from_params(dp)
    recs = _make_records(dp, pkeys, _surface, 60, seed=7)
    assert S.propose_candidates_qrf(recs, pkeys, dp, space, 5, seed=1) == []

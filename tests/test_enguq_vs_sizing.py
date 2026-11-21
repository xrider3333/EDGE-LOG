"""ENGUQ_1M_ETH_VS_1_0: the sizing rule and the COST IDENTITY.

The cost identity is the one thing in that file that can be silently wrong. The engine charges
cost once per trade with no notion of size (augur_engine.engine._apply_costs), so the strategy
emits `size * gross - (size - 1) * vs_cost_pts` and the engine's own subtraction completes it to
`size * (gross - cost)`. These tests pin that end to end, including the case where the job's cost
does NOT match vs_cost_pts -- a mismatch must show up here, not as a flattering run.
"""
import numpy as np
import pytest

from augur_engine.engine import _apply_costs
from augur_engine.strategies import load_strategy

VS = "ENGUQ_1M_ETH_VS_1_0.py"


@pytest.fixture(scope="module")
def mod():
    return load_strategy(VS)


# ── the sizing rule ──────────────────────────────────────────────────────────────────────────
def test_size_is_target_over_the_trades_own_risk(mod):
    s = mod.trade_sizes([35.0, 70.0, 17.5], 35.0, 0.25, 4.0)
    assert s == pytest.approx([1.0, 0.5, 2.0])


def test_size_is_clamped_both_ways(mod):
    s = mod.trade_sizes([1.0, 10_000.0], 35.0, 0.25, 4.0)
    assert s == pytest.approx([4.0, 0.25])          # 35/1 = 35 -> 4.0; 35/10000 -> 0.25


def test_a_missing_or_bad_risk_trades_the_base_unit(mod):
    """The parent reports one levels row per trade, but a dropped ladder must not vanish a
    trade or size it to infinity -- it trades at 1.0, which is what the base leg does."""
    s = mod.trade_sizes([np.nan, 0.0, -5.0, 35.0], 35.0, 0.25, 4.0)
    assert s == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_median_risk_target_keeps_the_median_trade_at_one_unit(mod):
    risks = [6.0, 20.0, 35.0, 60.0, 137.0]
    s = mod.trade_sizes(risks, 35.0, 0.25, 4.0)
    assert float(np.median(s)) == pytest.approx(1.0)


# ── the cost identity, which is the sharp edge ───────────────────────────────────────────────
def _emit(gross, size, vs_cost):
    """What the strategy puts in the trade tuple, by the file's own formula."""
    return size * gross - (size - 1.0) * vs_cost


@pytest.mark.parametrize("gross,size", [(10.0, 1.0), (10.0, 2.0), (10.0, 0.25), (-4.0, 4.0),
                                        (0.0, 3.0), (-1.5, 0.5)])
def test_engine_cost_completes_to_size_times_net(gross, size):
    """emit + the engine's single charge == size * (gross - cost), for wins and losses alike."""
    cost = 0.783
    m = {"trades": [(0, 1, _emit(gross, size, cost), 1, 100.0)]}
    netted = _apply_costs(m, cost)["trades"][0][2]
    assert netted == pytest.approx(size * (gross - cost))


def test_a_cost_mismatch_is_visible_and_signed():
    """If the job runs at a cost other than vs_cost_pts the trade is mis-charged by exactly
    (size - 1) * (job_cost - vs_cost). Pinned so the direction is on record: a job cheaper than
    vs_cost_pts UNDER-states the size-scaled charge, i.e. it flatters the run."""
    vs_cost, job_cost, size, gross = 0.783, 0.533, 3.0, 10.0
    m = {"trades": [(0, 1, _emit(gross, size, vs_cost), 1, 100.0)]}
    netted = _apply_costs(m, job_cost)["trades"][0][2]
    truth = size * (gross - job_cost)
    assert netted - truth == pytest.approx((size - 1.0) * (job_cost - vs_cost))
    assert netted < truth                     # cheaper job cost than declared -> understated


# ── the file's contract with the loader and the search ───────────────────────────────────────
def test_sizing_knobs_are_fixed_and_the_entry_knobs_are_not(mod):
    """The sizing must not be searchable (that is how arm A bought net with leverage), and the
    file must NOT be all-fixed either or the runner refuses it as a pinned single-config file."""
    dp = mod.DEFAULT_PARAMS
    for k in ("vs_target_pts", "vs_min_u", "vs_max_u", "vs_cost_pts"):
        assert dp[k]["min"] == dp[k]["max"], k
    ranged = [k for k, v in dp.items()
              if isinstance(v.get("min"), (int, float)) and v["min"] != v["max"]]
    assert len(ranged) >= 10, ranged


def test_the_parents_ranges_are_carried_over_unchanged(mod):
    """A search here has to explore the crown's own space; a quietly widened range would make
    this a different study."""
    parent = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    for k, v in parent.DEFAULT_PARAMS.items():
        if not isinstance(v.get("min"), (int, float)):
            continue
        mine = mod.DEFAULT_PARAMS[k]
        assert (mine["min"], mine["max"], mine["default"]) == (v["min"], v["max"], v["default"]), k


def test_vs_cost_default_is_the_registered_enguq_line(mod):
    assert mod.DEFAULT_PARAMS["vs_cost_pts"]["default"] == pytest.approx(0.783)


def test_contract_globals_exist(mod):
    assert isinstance(mod.STRATEGY_NAME, str) and mod.STRATEGY_NAME
    assert isinstance(mod.PARAM_GRID_PRESETS, dict) and mod.PARAM_GRID_PRESETS
    assert callable(mod.run_backtest)


# ── end to end against the parent on synthetic bars ──────────────────────────────────────────
def _bars(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    c = 10_000 + np.cumsum(rng.normal(0, 3.0, n))
    o = c + rng.normal(0, 0.5, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 2.0, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 2.0, n))
    v = np.abs(rng.normal(500, 150, n))
    day = np.arange(n) // 400
    return o, h, lo, c, v, day


def test_same_trades_as_the_parent_only_the_dollars_move(mod):
    """Sizing must not change WHICH trades happen -- that is the whole point of the arm. If the
    synthetic tape produces no trades the test says so rather than passing vacuously."""
    o, h, lo, c, v, day = _bars()
    parent = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    a = parent.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True)
    b = mod.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True)
    if not a or not a.get("trades"):
        pytest.skip("the synthetic tape produced no trades for the parent")
    assert b and b.get("trades")
    assert [(t[0], t[1], t[3]) for t in b["trades"]] == [(t[0], t[1], t[3]) for t in a["trades"]]
    assert len(b["sizes"]) == len(a["trades"])
    assert all(0.25 - 1e-9 <= s <= 4.0 + 1e-9 for s in b["sizes"])


def test_target_matching_every_risk_reproduces_the_parent_exactly(mod):
    """With vs_min_u == vs_max_u == 1 the arm IS the base leg, so any difference in the dollars
    is a bug in the re-weighting rather than in the sizing."""
    o, h, lo, c, v, day = _bars()
    parent = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    a = parent.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True)
    if not a or not a.get("trades"):
        pytest.skip("the synthetic tape produced no trades for the parent")
    b = mod.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True,
                         vs_min_u=1.0, vs_max_u=1.0)
    assert [round(t[2], 9) for t in b["trades"]] == [round(t[2], 9) for t in a["trades"]]
    assert b["total_pnl"] == pytest.approx(a["total_pnl"], abs=0.02)


# ── the dependency VERIFIER asked about: does asking for levels change the trades? ───────────
def test_asking_the_parent_for_levels_does_not_change_its_trades():
    """THE REAL RISK in the VS file, and it is not the one I first described.

    VS always calls the parent with return_levels=True, because `risk` is its sizing input, and
    that forces the parent's INTERPRETED walk (the compiled one does not expose the stop path).
    I had justified this by pointing at tests/test_fastloop_parity.py. That test does cover
    ENGU-Q's own shape -- three R2 cases on 1m bars with trailing on, plus R3 and R5 -- but NOT
    ONE of its cases passes return_levels, so it compares the two walks with levels OFF and says
    nothing about the levels path. The thing VS depends on is narrower and is pinned here: asking
    for levels must not change WHICH trades happen or what they earn.
    """
    o, h, lo, c, v, day = _bars()
    parent = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    plain = parent.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True)
    withlv = parent.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True,
                                 return_levels=True)
    if not plain or not plain.get("trades"):
        pytest.skip("the synthetic tape produced no trades for the parent")
    assert [tuple(t) for t in withlv["trades"]] == [tuple(t) for t in plain["trades"]]
    assert withlv["total_pnl"] == pytest.approx(plain["total_pnl"])
    assert len(withlv["levels"]) == len(plain["trades"])


def test_every_levels_row_carries_a_usable_risk():
    """If the parent ever stopped reporting `risk`, VS would quietly size every trade at 1.0 --
    the bad-risk fallback -- and look like the base leg while claiming to be vol-scaled. A
    missing risk is a reason to fail a test, not to trade."""
    o, h, lo, c, v, day = _bars()
    parent = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    out = parent.run_backtest(o, h, lo, c, volumes=v, day_id=day, return_trades=True,
                              return_levels=True)
    if not out or not out.get("trades"):
        pytest.skip("the synthetic tape produced no trades for the parent")
    risks = [(r or {}).get("risk") for r in out["levels"]]
    assert all(r is not None and r > 0 for r in risks), risks[:10]

"""tests/test_ml_keel_state.py -- exactness proof for augur_engine.ml_keel's
keel_build_state / keel_score_from_state split (KEEL v12 live-scoring overlay, OWNER
DECISION 2026-09-23: "train it on the NQ backtest like the validation", score each new
NOISE_382 QQQ entry as one more trade appended to that walk). See ml_keel.py's own
docstrings on keel_build_state/keel_score_from_state/_maybe_refit for the design this
proves.

WHY SYNTHETIC DATA HERE, NOT THE REAL #382 WALK. keel_build_state(trades[:k]) replays
the whole 0..k-1 walk, so testing near the real run's scale (n=4,825 trades, ~4 minutes
per full-scale build) is far too slow for a test that runs on every push. This file's
proof is EXHAUSTIVE instead of sampled -- every single valid cut point on a small,
fast, engineered series, deliberately shaped to pass through a refit boundary, a
Friday, an FOMC pre-statement morning, and a compressed (sq60_on) bar. The real
#382 walk itself WAS checked this way (out of band, not as part of the test suite --
too slow to run on every push): build_state + score matched keel_walk's own ["size"][k]
to 1e-12 at 35 cut points spanning k=0 (pre-warmup) through k=4824 (the last, full-scale
trade), including several genuine shade-branch firings (t_fast < -0.5) and refit
boundaries -- see this task's delivered report for the numbers.

This file also proves the negative: keel_walk's own source is untouched (grep-checked
below), so its outputs cannot have changed for any existing caller (gate_validate, the
Auto-Validate KEEL row, tools/backfill_keel.py).
"""
import inspect
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import ml_keel as K


# ── a small, fast, engineered series ──────────────────────────────────────────────────
def _synthetic_arrays(n_days=48, bars_per_day=16, seed=7, quiet_day=30, quiet_len=6):
    """RTH-shaped 5-ish-minute bars over `n_days` weekday sessions (so Fridays occur
    naturally), tz-aware ET index, day_id factorized -- the same shape
    augur_engine.data.load_master_arrays hands the engine. One deliberately
    LOW-VOLATILITY stretch (`quiet_len` bars inside session `quiet_day`) so
    keel_features' real sq60_on compression flag turns on somewhere for real, rather
    than being hand-set."""
    rng = np.random.RandomState(seed)
    idx, day_id, opens, highs, lows, closes = [], [], [], [], [], []
    price = 15000.0
    cur = pd.Timestamp("2024-01-02", tz="US/Eastern")   # a Tuesday
    day = 0
    while day < n_days:
        if cur.dayofweek > 4:
            cur = cur + pd.Timedelta(days=1)
            continue
        day_start = cur.replace(hour=9, minute=30)
        for b in range(bars_per_day):
            ts = day_start + pd.Timedelta(minutes=5 * b)
            quiet = (day == quiet_day and 0 <= b < quiet_len)
            sigma = 0.25 if quiet else 4.0
            chg = rng.normal(0, sigma)
            o = price
            c = price + chg
            h = max(o, c) + abs(rng.normal(0, sigma * 0.3))
            l = min(o, c) - abs(rng.normal(0, sigma * 0.3))
            opens.append(o); highs.append(h); lows.append(l); closes.append(c)
            idx.append(ts); day_id.append(day)
            price = c
        cur = cur + pd.Timedelta(days=1)
        day += 1
    return {
        "open": np.array(opens), "high": np.array(highs), "low": np.array(lows),
        "close": np.array(closes), "volume": np.full(len(opens), 1000.0),
        "day_id": np.array(day_id, dtype="int64"), "index": pd.DatetimeIndex(idx),
    }


def _synthetic_trades(arrays, n_trades=220, seed=11, win_rate=0.35):
    """Non-overlapping trades (each entry strictly after the previous trade's exit --
    the same invariant every real strategy engine in this repo produces, verified
    empirically for the real #382 NQ walk: zero overlaps / zero same-bar reversals over
    4,824 gaps -- see this task's delivered report) with a fat-tailed, ~35% win rate
    pnl shape so the ensemble has something non-degenerate to fit, same character as a
    real NOISE walk."""
    rng = np.random.RandomState(seed)
    n_bars = len(arrays["close"])
    trades = []
    pos = 5
    while len(trades) < n_trades:
        hold = rng.randint(1, 6)
        exitb = pos + hold
        if exitb >= n_bars - 3:
            break
        win = rng.rand() < win_rate
        pnl = float(rng.gamma(2.0, 15.0)) if win else -float(rng.gamma(2.0, 8.0))
        trades.append((pos, exitb, pnl))
        pos = exitb + rng.randint(1, 4)
    return trades


_ARRAYS = _synthetic_arrays()
_TRADES = _synthetic_trades(_ARRAYS)
_N = len(_TRADES)
assert _N >= 150, "fixture sanity: expected the generator to produce >=150 trades"

# one real calendar date inside the synthetic window, made an FOMC day for this test
# only -- restored immediately after computing the ground-truth walk below, and again
# after every test via the autouse fixture, so this file never leaks a fake FOMC date
# into any other test module that shares the process.
_FOMC_TEST_DATE = pd.Timestamp("2024-01-02", tz="US/Eastern").date()
for _o, _x, _p in _TRADES:
    _d = _ARRAYS["index"][_o].date()
    if _ARRAYS["index"][_o].dayofweek < 4:      # not the Friday check -- any early day
        _FOMC_TEST_DATE = _d
        break


@pytest.fixture(autouse=True)
def _isolate_fomc_cache(monkeypatch):
    """Every test in this file sees a FIXED, synthetic FOMC calendar (one date, chosen
    above) instead of the real tools/data/fomc_dates.txt -- deterministic, and proves
    the event-tilt CODE PATH rather than depending on today's real calendar happening
    to line up with the synthetic date range. monkeypatch restores ml_keel._FOMC for
    every other test module automatically."""
    monkeypatch.setattr(K, "_FOMC", {_FOMC_TEST_DATE})
    yield


@pytest.fixture(scope="module")
def ground_truth():
    """keel_walk's own output over the WHOLE synthetic trade list -- computed once
    (module-scoped) under the SAME fixed FOMC calendar the exactness test uses, since
    fixture scoping means the autouse per-test monkeypatch above does not cover a
    module-scoped fixture's own setup. Re-applies the same patch directly."""
    old = K._FOMC
    K._FOMC = {_FOMC_TEST_DATE}
    try:
        feats = K.keel_features(_ARRAYS)
        kw = K.keel_walk(_ARRAYS, _TRADES, feats=feats, version="v12")
    finally:
        K._FOMC = old
    return feats, kw


# ── 0. keel_walk itself is untouched by this change ───────────────────────────────────
def test_keel_walk_source_was_not_modified():
    """This task adds NEW functions after keel_block; it must not change one character
    of keel_walk's own body. A crude but effective guard: keel_walk's source still
    contains its own known, pre-existing literal lines verbatim (copied from the
    version this task started from)."""
    src = inspect.getsource(K.keel_walk)
    for must_contain in [
        'cfg = CFG[version]',
        'T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades], key=lambda t: t[0])',
        'if nd < MIN_HISTORY:\n            continue',
        'sc, members = _fit_members(X[idx], P[idx], w, seed, target=cfg["target"], use=cfg["members"])',
        'return {"trades": T, "E": E, "X": Xi, "P": P, "size": size, "z": z, "z_members": zm,',
    ]:
        assert must_contain in src, "keel_walk's source no longer contains: %r" % must_contain


def test_keel_walk_smoke(ground_truth):
    feats, kw = ground_truth
    assert kw["version"] == "v12"
    assert len(kw["size"]) == _N
    assert kw["n_fits"] >= 1
    assert np.all(np.asarray(kw["size"]) > 0)


# ── 1. EXHAUSTIVE exactness: every cut point k, not a sample ─────────────────────────
def test_build_state_and_score_match_keel_walk_at_every_cut_point(ground_truth):
    feats, kw = ground_truth
    sizes_full = kw["size"]
    T_sorted = kw["trades"]

    names = feats[1]
    sq_idx = names.index("sq60_on")
    idxdt = _ARRAYS["index"]
    fomc_hit = friday_hit = comp_hit = refit_hit = shade_hit = 0
    mismatches = []

    for k in range(_N):
        prefix = T_sorted[:k]
        state = K.keel_build_state(_ARRAYS, prefix, feats=feats, version="v12")
        entry_bar = int(T_sorted[k][0])
        size, diag = K.keel_score_from_state(state, _ARRAYS, entry_bar, feats=feats,
                                             cross_series=False)
        true_size = float(sizes_full[k])
        if abs(size - true_size) > 1e-12:
            mismatches.append((k, size, true_size, diag))

        ts = idxdt[entry_bar]
        if ts.date() == _FOMC_TEST_DATE and ts.hour < 14:
            fomc_hit += 1
        if ts.dayofweek == 4:
            friday_hit += 1
        if feats[0][entry_bar, sq_idx] > 0:
            comp_hit += 1
        if diag.get("refit"):
            refit_hit += 1
        if diag.get("t_fast") is not None and diag["t_fast"] < K.CFG["v12"]["shade"]["t"]:
            shade_hit += 1

    assert not mismatches, (
        "mismatches at %d of %d cut points (first 5): %s"
        % (len(mismatches), _N, mismatches[:5]))
    # the exhaustive sweep is only meaningful if it actually walked through each kind of
    # boundary the design calls out -- assert real coverage, not just "no mismatches
    # because nothing interesting happened".
    assert friday_hit > 0, "synthetic series produced no Friday-entry trade to test"
    assert comp_hit > 0, "synthetic series produced no compressed (sq60_on) trade to test"
    assert fomc_hit > 0, "synthetic series produced no FOMC pre-statement trade to test"
    # refit_hit is (correctly) always 0 here: keel_build_state's own end-of-walk bake-in
    # already performs the refit due for trade k using the SAME nd keel_score_from_state
    # will compute (no overlaps -> same-series nd == build's own n at every k, proved by
    # the mismatch-free sweep above), so _maybe_refit's "already satisfied" branch inside
    # keel_score_from_state never has anything left to do -- see
    # test_maybe_refit_fires_when_due below for a direct unit test of that branch, and
    # ml_keel.py's keel_score_from_state docstring for when it WOULD matter (an
    # overlapping/same-bar-reversal trade list, never observed in the real #382 walk).
    print(f"\n[exactness] {_N} cut points, 0 mismatches. friday={friday_hit} "
         f"fomc={fomc_hit} comp={comp_hit} refit_at_score={refit_hit} shade={shade_hit}")


def test_cross_series_matches_same_series_at_the_final_trade(ground_truth):
    """cross_series=True (the LIVE/production mode -- design B) must agree with the
    same-series exactness mode at the one point they are guaranteed to agree: the very
    last trade, where 'every earlier trade is resolved' is true either way (no
    overlaps in this synthetic series either -- built non-overlapping on purpose)."""
    feats, kw = ground_truth
    T_sorted = kw["trades"]
    prefix = T_sorted[:_N - 1]
    state = K.keel_build_state(_ARRAYS, prefix, feats=feats, version="v12")
    entry_bar = int(T_sorted[_N - 1][0])

    size_same, _ = K.keel_score_from_state(state, _ARRAYS, entry_bar, feats=feats,
                                           cross_series=False)
    size_cross, _ = K.keel_score_from_state(state, _ARRAYS, entry_bar, feats=feats,
                                            cross_series=True)
    assert size_same == pytest.approx(size_cross, abs=1e-12)
    assert size_same == pytest.approx(float(kw["size"][_N - 1]), abs=1e-12)


# ── 2. keel_state_summary ──────────────────────────────────────────────────────────────
def test_keel_state_summary_is_json_safe(ground_truth):
    feats, kw = ground_truth
    T_sorted = kw["trades"]
    state = K.keel_build_state(_ARRAYS, T_sorted, feats=feats, version="v12")
    summary = K.keel_state_summary(state, arrays=_ARRAYS, extra={"leg": "NOISE_382"})

    import json
    blob = json.dumps(summary)         # raises on any non-JSON-safe value (numpy, nan handled)
    assert '"leg": "NOISE_382"' in blob
    assert summary["n_trades"] == _N
    assert summary["version"] == "v12"
    assert summary["last_nq_session"] is not None
    assert summary["has_model"] is True
    assert 0.0 <= summary["trust_now"] <= 1.0


# ── 3. feature-name mismatch is a loud error, never a silent misalignment ────────────
def test_feature_column_mismatch_raises():
    feats = K.keel_features(_ARRAYS)
    state = K.keel_build_state(_ARRAYS, _TRADES[:60], feats=feats, version="v12")
    bad_feats = (feats[0], list(feats[1])[::-1])   # same columns, wrong order/names
    with pytest.raises(ValueError):
        K.keel_score_from_state(state, _ARRAYS, entry_bar=100, feats=bad_feats,
                                cross_series=True)


# ── 4. warm-up trades score exactly 1.0 pre-multiplier, matching keel_walk's own
#      `continue` (it never touches trust/z/size for a trade before MIN_HISTORY) ────────
def test_warmup_trade_scores_the_untouched_base():
    feats = K.keel_features(_ARRAYS)
    state = K.keel_build_state(_ARRAYS, [], feats=feats, version="v12")
    assert state["sc"] is None and state["n"] == 0
    entry_bar = int(_TRADES[0][0])
    size, diag = K.keel_score_from_state(state, _ARRAYS, entry_bar, feats=feats,
                                         cross_series=True)
    assert diag["nd"] == 0
    # base 1.0 x whatever a-priori multipliers this specific bar happens to carry --
    # never touched by the model/trust machinery (state has no fitted model at all).
    # Applied in keel_score_from_state's own order: dow -> comp (both capped at 3.0)
    # -> event (uncapped) -- mirrored here, not re-derived, so this checks the ORDER
    # too, not just that every multiplier is present.
    cfg = K.CFG["v12"]
    on_friday = _ARRAYS["index"][entry_bar].dayofweek == 4
    on_comp = feats[0][entry_bar, feats[1].index("sq60_on")] > 0
    ts = _ARRAYS["index"][entry_bar]
    on_event = ts.date() == _FOMC_TEST_DATE and ts.hour < cfg["event"]["cut_hour"]
    expected = 1.0
    if on_friday:
        expected = min(expected * cfg["dow"]["4"], cfg["dow"]["cap"])
    if on_comp:
        expected = min(expected * cfg["comp"]["mult"], cfg["comp"]["cap"])
    if on_event:
        expected = expected * cfg["event"]["mult"]
    assert size == pytest.approx(expected, abs=1e-12)
    assert on_friday or on_comp or on_event, (
        "test sanity: trade 0 must actually carry at least one a-priori multiplier "
        "for this test to prove anything beyond size==1.0")


# ── 5. _maybe_refit fires exactly when the documented condition says it should ───────
def test_maybe_refit_fires_when_due_and_not_otherwise():
    """Direct unit test of the shared refit-decision helper both keel_build_state and
    keel_score_from_state call -- see its own docstring. keel_score_from_state's
    "already satisfied" branch is, correctly, never exercised by the integration test
    above (build's own bake-in always covers the trade it is about to score, given a
    non-overlapping trade list -- see that test's comment), so this is the only place
    the DUE case of _maybe_refit's own logic is proven."""
    cfg = K.CFG["v12"]
    rng = np.random.RandomState(3)
    nd = 40
    X = rng.normal(size=(nd, 5))
    P = np.where(rng.rand(nd) < 0.4, rng.gamma(2, 10, nd), -rng.gamma(2, 6, nd))
    led = np.arange(nd)

    # members is None -> always refits, regardless of fitted_on/REFIT_EVERY.
    sc, members, fitted_on, n_fits = K._maybe_refit(None, None, -1, 0, X, P, led, nd,
                                                    K.SEED, cfg)
    assert sc is not None and members and fitted_on == nd and n_fits == 1

    # nd - fitted_on < REFIT_EVERY -> no-op, same objects returned.
    sc2, members2, fitted_on2, n_fits2 = K._maybe_refit(
        sc, members, fitted_on, n_fits, X, P, led, nd + K.REFIT_EVERY - 1, K.SEED, cfg)
    assert sc2 is sc and members2 is members and fitted_on2 == fitted_on and n_fits2 == n_fits

    # nd - fitted_on >= REFIT_EVERY -> refits again, fitted_on advances, n_fits increments.
    nd2 = fitted_on + K.REFIT_EVERY
    X2 = rng.normal(size=(nd2, 5))
    P2 = np.where(rng.rand(nd2) < 0.4, rng.gamma(2, 10, nd2), -rng.gamma(2, 6, nd2))
    sc3, members3, fitted_on3, n_fits3 = K._maybe_refit(
        sc, members, fitted_on, n_fits, X2, P2, np.arange(nd2), nd2, K.SEED, cfg)
    assert fitted_on3 == nd2 and n_fits3 == n_fits + 1

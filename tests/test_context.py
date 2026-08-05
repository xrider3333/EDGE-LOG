"""Unit tests for augur_engine.context — the TRADE CONTEXT engine (stages 1+2).

Every test here is synthetic and fully offline (no real master CSVs, no real
network calls — `fetch_external_daily`'s own network path is only exercised
through a monkeypatched `_fetch_one`, matching the root conftest's "touches NO
real data files" contract), so the suite stays reproducible anywhere.

Covers:
  * the planted-signal test — proves the statistics actually work: a feature
    engineered to correlate with PnL ranks top / survives FDR; a pure-noise
    feature's CI spans zero and does not survive.
  * causality — a trade sees the PRIOR day's raw feature value, never its own
    day's (except gap_pct, which is deliberately unshifted).
  * the clustered bootstrap actually clusters (duplicating one day's trades
    must not artificially tighten the CI the way a naive per-trade bootstrap
    would).
  * fail-soft (external fetch raising, too few trades) and determinism.
  * the ERA-AWARE GUARD (block bootstrap + within-era consistency): a feature
    that only correlates with PnL because BOTH drift over years (no real
    within-year relationship) must get caught (survives=False,
    trend_confounded=True); a feature with a genuine, consistent within-year
    relationship must still survive; the block-bootstrap CI must be wider than
    the old day-only CI for a persistent feature; a fast/noisy feature must
    NOT get flagged "slow" (and so isn't subject to the era gate at all).
"""
import json

import numpy as np
import pandas as pd
import pytest

from augur_engine import context as ctx


def _daily_index(n, start="2020-01-06", freq="B"):
    return pd.date_range(start, periods=n, freq=freq)


def _trades_from_daily(pnls):
    """One trade per day, entry bar == exit bar == day index (matches the 1
    bar/day synthetic setup used throughout this file)."""
    return [(i, i, float(p)) for i, p in enumerate(pnls)]


# ── context_scores: the planted-signal test (proves the stats work) ────────────

def test_planted_signal_ranks_top_and_survives():
    n = 500
    dates = _daily_index(n)
    rng = np.random.default_rng(42)
    signal = rng.uniform(0, 1, size=n)          # e.g. "ATR percentile" stand-in
    noise = rng.normal(0, 1, size=n)             # unrelated feature
    pnl = 40.0 * signal + rng.normal(0, 8, size=n)   # bigger wins on high-signal days

    daily = pd.DataFrame({"signal_feat": signal, "noise_feat": noise}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=1000, seed=42)
    assert res is not None
    assert res["n_trades"] == n
    names = [f["name"] for f in res["features"]]
    assert names[0] == "signal_feat"                 # ranks top by |rho|

    sig = next(f for f in res["features"] if f["name"] == "signal_feat")
    assert sig["rho"] > 0.5
    assert sig["ci_lo"] > 0                           # CI excludes zero
    assert sig["survives"] is True

    noi = next(f for f in res["features"] if f["name"] == "noise_feat")
    assert noi["ci_lo"] < 0 < noi["ci_hi"]             # CI spans zero
    assert noi["survives"] is False


def test_fewer_than_30_trades_returns_none():
    n = 10
    dates = _daily_index(n)
    daily = pd.DataFrame({"x": np.arange(n, dtype=float)}, index=dates.date)
    trades = _trades_from_daily(list(range(n)))
    assert ctx.context_scores(trades, dates, daily, n_boot=200) is None


def test_no_daily_features_returns_none():
    dates = _daily_index(40)
    trades = _trades_from_daily(np.zeros(40))
    assert ctx.context_scores(trades, dates, None, n_boot=200) is None
    assert ctx.context_scores([], dates, pd.DataFrame(index=dates.date), n_boot=200) is None


# ── causality: build_internal_daily shifts everything +1 day EXCEPT gap_pct ────

def test_prev_ret_sees_prior_days_raw_value():
    # Engineer closes so the RAW (unshifted) daily return on day D equals D
    # (percent): close[D] = close[D-1] * (1 + D/100).
    n = 30
    closes = [100.0]
    for d in range(1, n):
        closes.append(closes[-1] * (1 + d / 100.0))
    closes = np.array(closes)
    opens = highs = lows = closes.copy()
    index = _daily_index(n)

    daily = ctx.build_internal_daily(index, opens, highs, lows, closes)
    for d in (2, 5, 12, 20):
        got = daily.iloc[d + 1]["prev_ret"]              # trade entering day d+1
        assert got == pytest.approx(d, abs=1e-6)          # sees day d's RAW return


def test_gap_pct_is_not_shifted():
    n = 20
    rng = np.random.default_rng(1)
    closes = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    opens = closes.copy()
    # Engineer a clean 5% gap up on day 10 specifically (day 10's open vs day 9's close).
    prior_close = closes[9]
    opens[10] = prior_close * 1.05
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    index = _daily_index(n)

    daily = ctx.build_internal_daily(index, opens, highs, lows, closes)
    got = daily.iloc[10]["gap_pct"]                       # NOT daily.iloc[11] -- same day
    assert got == pytest.approx(5.0, abs=1e-6)


def test_internal_features_have_expected_columns():
    n = 40
    rng = np.random.default_rng(2)
    closes = 100 + np.cumsum(rng.normal(0, 1, size=n))
    opens = closes + rng.normal(0, 0.1, size=n)
    highs = np.maximum(opens, closes) + 0.5
    lows = np.minimum(opens, closes) - 0.5
    index = _daily_index(n)
    daily = ctx.build_internal_daily(index, opens, highs, lows, closes)
    assert list(daily.columns) == list(ctx.INTERNAL_FEATURES)
    assert len(daily) == n


# ── the clustered bootstrap actually clusters ───────────────────────────────────

def test_clustered_bootstrap_does_not_collapse_on_duplicated_day():
    n = 100
    dates = _daily_index(n)
    rng = np.random.default_rng(7)
    x = rng.uniform(0, 1, size=n)
    pnl = 50.0 * x + rng.normal(0, 15, size=n)
    daily = pd.DataFrame({"x": x}, index=dates.date)
    trades = _trades_from_daily(pnl)

    base = ctx.context_scores(trades, dates, daily, n_boot=1000, seed=42)
    f_base = base["features"][0]
    w_base = f_base["ci_hi"] - f_base["ci_lo"]
    n_base = f_base["n"]

    # Duplicate day 0's single trade 20x more (same date, same feature/pnl values)
    dup_trades = list(trades) + [(0, 0, float(pnl[0]))] * 19
    dup = ctx.context_scores(dup_trades, dates, daily, n_boot=1000, seed=42)
    f_dup = dup["features"][0]
    w_dup = f_dup["ci_hi"] - f_dup["ci_lo"]
    n_dup = f_dup["n"]

    assert n_dup == n_base + 19
    naive_factor = (n_base / n_dup) ** 0.5     # what an (over-optimistic) naive per-trade
                                                # bootstrap would AT LEAST shrink by
    # clustering treats the 20 duplicate rows as ONE day's worth of information, so
    # the CI must shrink by LESS than that naive per-trade scaling would predict.
    assert (w_dup / w_base) > naive_factor


# ── fail-soft ────────────────────────────────────────────────────────────────

def _synthetic_ohlc(n, seed=3):
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0, 1, size=n))
    opens = closes + rng.normal(0, 0.2, size=n)
    highs = np.maximum(opens, closes) + 1.0
    lows = np.minimum(opens, closes) - 1.0
    return opens, highs, lows, closes


def test_build_context_survives_external_fetch_raising(monkeypatch):
    n = 60
    index = _daily_index(n)
    opens, highs, lows, closes = _synthetic_ohlc(n)
    rng = np.random.default_rng(4)
    trades = _trades_from_daily(rng.normal(0, 5, size=n))

    def _boom(*a, **kw):
        raise RuntimeError("network is down")
    monkeypatch.setattr(ctx, "fetch_external_daily", _boom)

    out = ctx.build_context(trades, index, opens, highs, lows, closes,
                            cost_pts=0.0, n_boot=200, external=True)
    assert out is not None
    assert out["external_available"] is False
    assert isinstance(out["features"], list)


def test_context_scores_external_available_flag():
    n = 60
    dates = _daily_index(n)
    rng = np.random.default_rng(5)
    x = rng.uniform(0, 1, size=n)
    pnl = 10 * x + rng.normal(0, 5, size=n)
    trades = _trades_from_daily(pnl)

    internal_only = pd.DataFrame({"gap_pct": x}, index=dates.date)
    r1 = ctx.context_scores(trades, dates, internal_only, n_boot=200)
    assert r1["external_available"] is False

    with_external = internal_only.copy()
    with_external["vix"] = rng.normal(0, 1, size=n)
    r2 = ctx.context_scores(trades, dates, with_external, n_boot=200)
    assert r2["external_available"] is True


def test_fetch_external_daily_all_tickers_fail_returns_none(monkeypatch):
    monkeypatch.setattr(ctx, "_fetch_one", lambda ticker: None)
    assert ctx.fetch_external_daily("2020-01-01", "2020-06-01") is None


def test_fetch_external_daily_merges_mocked_series(monkeypatch):
    n = 300
    idx = pd.date_range("2023-01-02", periods=n, freq="B").date
    rng = np.random.default_rng(6)
    fake = {
        "^VIX": pd.Series(15 + rng.normal(0, 2, size=n).cumsum() * 0.05, index=idx),
        "^VIX3M": pd.Series(16 + rng.normal(0, 2, size=n).cumsum() * 0.05, index=idx),
        "^TNX": pd.Series(4.0 + rng.normal(0, 0.05, size=n).cumsum() * 0.02, index=idx),
        "^IRX": pd.Series(5.0 + rng.normal(0, 0.02, size=n).cumsum() * 0.01, index=idx),
    }
    monkeypatch.setattr(ctx, "_fetch_one", lambda ticker: fake.get(ticker))

    out = ctx.fetch_external_daily("2023-01-01", "2023-12-01")
    assert out is not None
    for col in ctx.EXTERNAL_FEATURES:
        assert col in out.columns
    # shifted +1 -> the first row of every external feature is NaN (no prior close yet)
    assert out.iloc[0].isna().all()
    assert out.iloc[5].notna().any()


# ── era-aware guard: block bootstrap + within-era consistency ──────────────────

def _calendar_year_eras(dates, n_years):
    """Assign each date to an era EXACTLY the way ctx._era_ids will (calendar
    year, 0-based) -- used to build synthetic features/pnl whose era structure
    lines up with what the code under test will actually compute."""
    years = np.array([d.year for d in dates])
    uniq_years = np.unique(years)[:n_years]
    keep = np.isin(years, uniq_years)
    era = np.searchsorted(uniq_years, years[keep])
    return keep, era


def test_trend_artifact_survives_old_style_but_not_new_rule():
    """The key test: a feature that STEPS to a new level each calendar year
    (flat/noisy WITHIN a year -- like ^TNX or the yield curve sitting at one
    level for a while) and PnL that ALSO steps up era by era, for a totally
    UNRELATED reason -- no engineered within-year relationship at all. Pooled
    over the whole history the two drift together and look strongly,
    "significantly" related (q ~ 0, exactly what the old day-only pipeline
    would call a survivor) -- but the new rule must reject it once the era
    check sees there's no real relationship INSIDE any single year.
    """
    n_years = 6
    dates_full = _daily_index(n_years * 260, start="2010-01-04")
    keep, era = _calendar_year_eras(dates_full.date, n_years)
    dates = dates_full[keep]
    n = len(dates)

    seed = 5
    rng = np.random.default_rng(seed)
    feat_level = np.arange(n_years, dtype=float)
    feat = feat_level[era] + rng.normal(0, 0.3, n)          # ~flat within a year, steps across years
    pnl_level = np.arange(n_years, dtype=float) * 6.0
    pnl = pnl_level[era] + rng.normal(0, 8.0, n)            # independent noise -> no real within-year link

    daily = pd.DataFrame({"drift_feat": feat}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=300, seed=seed)
    assert res is not None
    f = res["features"][0]
    assert f["name"] == "drift_feat"

    # old-style: highly persistent AND "significant" by the (unchanged) FDR test --
    # this is exactly what the pre-fix pipeline would have called a survivor.
    assert f["slow"] is True
    assert f["q"] < ctx.FDR_Q

    # the era check catches it: no consistent within-year relationship.
    assert f["era_pass"] is False
    assert f["era_consistent"] < ctx.ERA_CONSISTENT_MIN

    # the new rule kills it, and flags WHY rather than silently dropping it.
    assert f["survives"] is False
    assert f["trend_confounded"] is True


def test_genuine_within_era_signal_survives():
    """A feature that is itself PERSISTENT (autocorr >= SLOW_AUTOCORR, so it
    IS subject to the era gate) but has a real, stable relationship to PnL
    that holds the SAME WAY inside every single year (no drift confound) must
    still survive: era_pass True, era_consistent high, survives True."""
    n = 1512                                                  # ~6 years, 1 trade/day
    dates = _daily_index(n, start="2010-01-04")
    seed = 7
    rng = np.random.default_rng(seed)
    phi = 0.97                                                # AR(1), mean-reverting, no net drift
    eps = rng.normal(0, 1.0, n)
    x = np.empty(n)
    x[0] = eps[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    pnl = 4.0 * x + rng.normal(0, 10.0, n)                    # same stable link every single day

    daily = pd.DataFrame({"persist_feat": x}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=300, seed=seed)
    assert res is not None
    f = res["features"][0]
    assert f["name"] == "persist_feat"

    assert f["slow"] is True                                  # genuinely persistent -> era gate applies
    assert f["n_eras"] >= 3
    assert f["era_consistent"] >= 0.8
    assert f["era_pass"] is True
    assert f["survives"] is True
    assert f["trend_confounded"] is False


def test_block_ci_wider_than_day_ci_for_persistent_feature():
    """The block bootstrap MUST report a wider CI than the plain day-clustered
    bootstrap for a highly persistent (slow-moving) feature -- that's the
    whole point of item 1: the day-only CI treats far-apart days as
    exchangeable and comes out falsely tight for something that drifts over
    months, the block version doesn't."""
    seed = 1
    n = 1000
    phi = 0.98
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, 1.0, n)
    x = np.empty(n)
    x[0] = eps[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    y = 2.0 * x + rng.normal(0, 8.0, n)

    rx, ry = ctx._rank(x), ctx._rank(y)
    day_code = np.arange(n)                                  # one trade per day -> day_code == index
    autocorr, persistence = ctx._autocorr_and_persistence(pd.Series(x))
    assert autocorr >= ctx.SLOW_AUTOCORR                       # confirm this really is a "slow" feature
    block_days = ctx._block_days_for(persistence)
    assert block_days > ctx.BLOCK_DAYS_MIN                      # a highly persistent series adapts upward

    lo_day, hi_day = ctx._clustered_bootstrap_ci(rx, ry, day_code, n, 1000, seed)
    lo_block, hi_block = ctx._block_bootstrap_ci(rx, ry, day_code, n, block_days, 500, seed)

    assert (hi_block - lo_block) > (hi_day - lo_day)


def test_fast_feature_not_flagged_slow():
    """A noisy, day-to-day feature (no persistence, e.g. vix_chg_5d/gap_pct-
    style) must get slow=False and is NOT subject to the era gate -- it
    survives on the plain FDR test alone, exactly like before this guard
    existed."""
    n = 400
    dates = _daily_index(n)
    seed = 3
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, size=n)                              # white noise -> ~0 autocorrelation
    pnl = 10.0 * x + rng.normal(0, 4.0, size=n)

    daily = pd.DataFrame({"fast_feat": x}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=300, seed=seed)
    assert res is not None
    f = res["features"][0]
    assert f["name"] == "fast_feat"

    assert abs(f["autocorr"]) < 0.5
    assert f["slow"] is False
    # survives regardless of era_pass, since slow=False bypasses the era gate
    assert f["survives"] == bool(f["q"] < ctx.FDR_Q)


# ── determinism ──────────────────────────────────────────────────────────────

def test_same_seed_gives_identical_output():
    n = 120
    dates = _daily_index(n)
    rng = np.random.default_rng(9)
    x = rng.uniform(0, 1, size=n)
    y = rng.normal(0, 1, size=n)
    pnl = 20 * x + rng.normal(0, 6, size=n)
    daily = pd.DataFrame({"x": x, "y": y}, index=dates.date)
    trades = _trades_from_daily(pnl)

    r1 = ctx.context_scores(trades, dates, daily, n_boot=500, seed=11)
    r2 = ctx.context_scores(trades, dates, daily, n_boot=500, seed=11)
    assert r1 == r2


def test_no_scipy_fallback_path_runs_and_is_sane(monkeypatch):
    """Forces the hand-rolled rank + permutation-p-value path (used when scipy
    is unavailable) and checks it still produces a sane, well-formed result."""
    monkeypatch.setattr(ctx, "_HAS_SCIPY", False)
    n = 80
    dates = _daily_index(n)
    rng = np.random.default_rng(13)
    x = rng.uniform(0, 1, size=n)
    pnl = 25 * x + rng.normal(0, 7, size=n)
    daily = pd.DataFrame({"x": x}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=150, seed=42)
    assert res is not None
    f = res["features"][0]
    assert f["rho"] > 0.3
    assert 0.0 <= f["p"] <= 1.0
    assert 0.0 <= f["q"] <= 1.0


# ── build_context: cost_pts netting matches regime_report's convention ─────────

def test_build_context_nets_cost_pts_before_scoring():
    n = 60
    index = _daily_index(n)
    opens, highs, lows, closes = _synthetic_ohlc(n, seed=21)
    rng = np.random.default_rng(21)
    gross_pnl = rng.normal(20, 5, size=n)                # all comfortably positive gross
    trades = _trades_from_daily(gross_pnl)

    out = ctx.build_context(trades, index, opens, highs, lows, closes,
                            cost_pts=5.0, n_boot=100, external=False)
    # every trade's pnl is well above cost_pts=5 so it stays usable either way;
    # just confirm build_context ran end to end without external data.
    assert out is not None
    assert out["external_available"] is False


# ── shadow probes (Boruta idea) + joint importance layer (LASSO + RF) ──────────

def test_probe_gate_signal_beats_probe_and_pure_noise_fails():
    """A planted strong signal must clear the shadow-probe noise floor
    (beats_probe True) and still survive; an unrelated (pure-noise) feature
    must NOT survive -- whether the block is q, CI, era, or the probe gate,
    any one of them is enough, and this test doesn't care which."""
    n = 500
    dates = _daily_index(n)
    rng = np.random.default_rng(42)
    signal = rng.uniform(0, 1, size=n)
    noise_a = rng.normal(0, 1, size=n)
    noise_b = rng.normal(0, 1, size=n)                    # extra source column so the
                                                            # 3 probes aren't all forced
                                                            # to reuse a single column
    pnl = 40.0 * signal + rng.normal(0, 8, size=n)

    daily = pd.DataFrame({"signal_feat": signal, "noise_a": noise_a, "noise_b": noise_b},
                         index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=500, seed=42)
    assert res is not None
    assert len(res["probe_rhos"]) == ctx.N_SHADOW_PROBES
    assert res["probe_max_abs_rho"] == max(abs(r) for r in res["probe_rhos"])

    sig = next(f for f in res["features"] if f["name"] == "signal_feat")
    assert sig["beats_probe"] is True
    assert sig["probe_margin"] > 0
    assert sig["survives"] is True

    noi = next(f for f in res["features"] if f["name"] == "noise_a")
    assert noi["survives"] is False


def test_probe_and_joint_determinism():
    """Same seed -> identical probe_rhos/probe_max_abs_rho AND identical
    per-feature probe/joint fields (LASSO+RF are seeded too)."""
    n = 200
    dates = _daily_index(n)
    rng = np.random.default_rng(17)
    a = rng.uniform(0, 1, size=n)
    b = rng.normal(0, 1, size=n)
    c = rng.normal(0, 1, size=n)
    pnl = 15.0 * a + rng.normal(0, 5, size=n)
    daily = pd.DataFrame({"a": a, "b": b, "c": c}, index=dates.date)
    trades = _trades_from_daily(pnl)

    r1 = ctx.context_scores(trades, dates, daily, n_boot=300, seed=13)
    r2 = ctx.context_scores(trades, dates, daily, n_boot=300, seed=13)
    assert r1 == r2
    assert r1["probe_rhos"] == r2["probe_rhos"]
    assert r1["joint"] == r2["joint"]


def test_probe_floor_positive_and_all_noise_features_never_survive():
    """With every daily feature pure noise (independent of PnL), the probe
    floor is still a real positive number (some random shuffled column always
    picks up SOME nonzero sample correlation), and nothing survives."""
    n = 400
    dates = _daily_index(n)
    rng = np.random.default_rng(23)
    pnl = rng.normal(0, 10, size=n)
    daily = pd.DataFrame({f"noise{i}": rng.normal(0, 1, size=n) for i in range(5)},
                         index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=300, seed=23)
    assert res is not None
    assert res["probe_max_abs_rho"] > 0
    assert len(res["features"]) == 5
    assert all(f["survives"] is False for f in res["features"])


def test_joint_layer_separates_collinear_pair_from_noise():
    """A collinear pair (x2 = x1 + tiny noise, both driven by the same planted
    signal) alongside independent noise features: the joint LASSO must keep at
    least one of the pair, the kept-set must be much smaller than the full
    feature set, and RF permutation importance must rank a member of the pair
    highest -- proving the joint layer (unlike the univariate rho above, where
    x1 and x2 look identically "significant") can actually attribute the
    signal to the right feature(s)."""
    n = 2000
    dates = _daily_index(n)
    seed = 3
    rng = np.random.default_rng(seed)
    x1 = rng.uniform(0, 1, size=n)
    x2 = x1 + rng.normal(0, 0.001, size=n)                # near-duplicate of x1
    noise_feats = {f"noise{i}": rng.normal(0, 1, size=n) for i in range(4)}
    pnl = 20.0 * x1 + rng.normal(0, 1.0, size=n)           # true signal lives in the pair

    daily = pd.DataFrame({"x1": x1, "x2": x2, **noise_feats}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=200, seed=seed)
    assert res is not None
    joint = res["joint"]
    assert joint is not None
    assert joint["n_used"] >= ctx.MIN_JOINT_ROWS

    feats = {f["name"]: f for f in res["features"]}
    assert len(feats) == 6
    kept = [name for name, f in feats.items() if f["lasso_kept"]]
    assert kept                                            # keeps AT LEAST one of the pair
    assert set(kept) <= {"x1", "x2"}                       # nothing spurious got kept here
    assert len(kept) < len(feats)                          # much smaller than the full set
    assert joint["probes_kept_lasso"] == 0                 # honestly reported either way

    top_rf = max(feats.values(), key=lambda f: f["rf_imp"])
    assert top_rf["name"] in ("x1", "x2")                  # RF importance leads to the signal
    for name in ("x1", "x2"):
        assert feats[name]["rf_beats_probe"] is True


def test_joint_layer_none_below_min_rows():
    """Fewer than MIN_JOINT_ROWS complete-case rows -> joint=None, and every
    per-feature joint field is explicitly None (not just missing) while the
    rest of the row (probe fields included) is populated as normal."""
    n = 60
    dates = _daily_index(n)
    rng = np.random.default_rng(5)
    x = rng.uniform(0, 1, size=n)
    pnl = 10.0 * x + rng.normal(0, 4, size=n)
    daily = pd.DataFrame({"x": x}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=200, seed=5)
    assert res is not None
    assert res["joint"] is None
    f = res["features"][0]
    assert f["lasso_coef"] is None
    assert f["lasso_kept"] is None
    assert f["rf_imp"] is None
    assert f["rf_beats_probe"] is None
    assert isinstance(f["beats_probe"], bool)              # probe gate still ran normally


def test_full_result_including_joint_is_json_safe():
    n = 400
    dates = _daily_index(n)
    rng = np.random.default_rng(31)
    x1 = rng.uniform(0, 1, size=n)
    x2 = rng.normal(0, 1, size=n)
    pnl = 20.0 * x1 + rng.normal(0, 6, size=n)
    daily = pd.DataFrame({"x1": x1, "x2": x2}, index=dates.date)
    trades = _trades_from_daily(pnl)

    res = ctx.context_scores(trades, dates, daily, n_boot=200, seed=31)
    assert res is not None
    assert res["joint"] is not None                        # exercise the joint branch too
    json.dumps(res)                                        # must not raise

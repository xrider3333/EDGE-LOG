"""api/cloud_signal.py -- the vol_prior_ranges bridge (go-live audit item 3.8,
2026-09-26). See augur_strategies/NOISE_1_0.py's own vol_prior_ranges/_vol_percentile
docstrings and tests/test_noise_vol_prior_ranges.py for the strategy-file half of this
fix; this file covers cloud_signal's own half: detecting which leg wants it, loading +
calibrating QQQ daily bars against the live 5m cache, and every fail-safe path -- ALL
against a FAKE daily frame written straight to disk, never a real network call.

GENERIC BY DESIGN, LIKE THE session_in_progress SUITE: _leg_accepts_vol_prior_ranges is
proved with synthetic stub strategies first, then re-checked against the three real
CROWN_LEGS strategy files (NOISE_382 gets it, ORB_R6/ENGUQ_335 do not -- see the module
docstring on the vol_prior_ranges bridge).
"""
import datetime as _dt
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                       # noqa: E402


@pytest.fixture(autouse=True)
def _reset_daily_calibration_log():
    """The calibration log line is deliberately once-per-ET-calendar-date (module-level
    cache) -- reset it before each test so a test asserting on the log's CONTENT is
    never at the mercy of test execution order within the same day."""
    cs._DAILY_CALIBRATION_LOG.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()


# ── _leg_accepts_vol_prior_ranges: reflection, walking the `_base` chain ─────────────────
def test_explicit_declaration_is_detected():
    mod = types.ModuleType("stub_declares_vpr")
    mod.run_backtest = lambda o, h, l, c, day_id=None, vol_prior_ranges=None, **kw: None
    assert cs._leg_accepts_vol_prior_ranges(mod) is True


def test_bare_kwargs_catchall_does_not_count_as_support_on_its_own():
    mod = types.ModuleType("stub_catchall_only")
    mod.run_backtest = lambda o, h, l, c, day_id=None, **kw: None
    assert cs._leg_accepts_vol_prior_ranges(mod) is False


def test_no_declaration_at_all_is_not_support():
    mod = types.ModuleType("stub_plain")
    mod.run_backtest = lambda o, h, l, c, day_id=None: None
    assert cs._leg_accepts_vol_prior_ranges(mod) is False


def test_wrapper_chain_is_detected_via_the_base_attribute():
    """A **kwargs-only wrapper (like NOISE_1_8_CT304.py/NOISE_1_1_NBHD.py) is detected
    through its own `_base` module attribute reaching a module that DOES declare the
    parameter -- proving the walk, not just a direct declaration."""
    bottom = types.ModuleType("stub_bottom")
    bottom.run_backtest = lambda o, h, l, c, day_id=None, vol_prior_ranges=None, **kw: None
    middle = types.ModuleType("stub_middle")
    middle.run_backtest = lambda o, h, l, c, **kw: None
    middle._base = bottom
    top = types.ModuleType("stub_top")
    top.run_backtest = lambda o, h, l, c, **kw: None
    top._base = middle
    assert cs._leg_accepts_vol_prior_ranges(top) is True


def test_unresolvable_strategy_string_is_best_effort_false():
    assert cs._leg_accepts_vol_prior_ranges("NOT_A_REAL_FILE_xyz.py") is False


def test_real_crown_legs_only_noise_382_opts_in():
    """The three real strategy files behind today's CROWN_LEGS -- NOISE_382 (via
    NOISE_1_8_CT304.py -> NOISE_1_1_NBHD.py -> NOISE_1_0.py) opts in; ORB_R6 and
    ENGUQ_335 must get NOTHING (item 4 of the go-live audit spec)."""
    assert cs._leg_accepts_vol_prior_ranges(cs.CROWN_LEGS["NOISE_382"]["strategy"]) is True
    assert cs._leg_accepts_vol_prior_ranges(cs.CROWN_LEGS["ORB_R6"]["strategy"]) is False
    # ENGUQ_335 is a shadow leg since 2026-09-28 (same cfg); the #422 shadow legs' CT304H
    # opts in exactly like NOISE_382's file
    assert cs._leg_accepts_vol_prior_ranges(cs.SHADOW_LEGS["ENGUQ_335"]["strategy"]) is False
    assert cs._leg_accepts_vol_prior_ranges(cs.SHADOW_LEGS["NOISE_422_PLAIN"]["strategy"]) is True


# ── synthetic bar builders (no network, no real bar cache) ───────────────────────────────
def _bdates(start, n):
    return list(pd.bdate_range(start, periods=n).date)


def _intraday_arrays(dates, ranges_by_date):
    """One synthetic RTH bar per session (09:30 ET), close pinned at 100.0 so
    (H-L)/C == ranges_by_date[date] exactly: H = 100*(1+r/2), L = 100*(1-r/2)."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d} 09:30:00", tz=cs.TZ) for d in dates])
    c = np.full(len(dates), 100.0)
    h = np.array([100.0 * (1.0 + ranges_by_date[d] / 2.0) for d in dates])
    l = np.array([100.0 * (1.0 - ranges_by_date[d] / 2.0) for d in dates])
    day_id = np.arange(len(dates))
    return {"open": c.copy(), "high": h, "low": l, "close": c, "day_id": day_id, "index": idx}


def _daily_epoch_df(dates, ranges_by_date):
    """Same (H-L)/C convention as _intraday_arrays, as an epoch-schema DataFrame
    (QQQ_1d.csv's own on-disk shape)."""
    times = [int(pd.Timestamp(f"{d} 00:00:00", tz=cs.TZ).tz_convert("UTC").timestamp())
            for d in dates]
    c = [100.0] * len(dates)
    h = [100.0 * (1.0 + ranges_by_date[d] / 2.0) for d in dates]
    l = [100.0 * (1.0 - ranges_by_date[d] / 2.0) for d in dates]
    return pd.DataFrame({"time": times, "open": c, "high": h, "low": l, "close": c,
                         "volume": [1.0] * len(dates)})


def _write_daily_cache(paths, df):
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df.to_csv(cs._cache_path("1d", paths), index=False)


def _stub_leg(required_lookback=10, declares=True):
    seen = {}
    if declares:
        def run_backtest(o, h, l, c, day_id=None, vol_prior_ranges=None,
                         return_trades=False, **kw):
            seen["vol_prior_ranges"] = vol_prior_ranges
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    else:
        def run_backtest(o, h, l, c, day_id=None, return_trades=False, **kw):
            seen["vol_prior_ranges"] = kw.get("vol_prior_ranges", "ABSENT")
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    mod = types.ModuleType(f"stub_leg_{required_lookback}_{declares}")
    mod.run_backtest = run_backtest
    mod.REQUIRED_LOOKBACK_SESSIONS = required_lookback
    return mod, seen


RATIO = 1.1


def _overlap_and_prior(n_overlap=25, n_prior=5, ratio=RATIO):
    """25 overlap sessions (both sources agree, off by exactly `ratio`) + 5 distinct
    prior sessions strictly before them (daily-only, what the bridge should hand
    back). Returns (overlap_dates, prior_dates, five_min_ranges, daily_ranges)."""
    prior_dates = _bdates("2026-01-05", n_prior)
    overlap_dates = _bdates("2026-02-02", n_overlap)
    five_min = {d: 0.02 for d in overlap_dates}
    daily = {d: 0.02 / ratio for d in overlap_dates}
    prior_daily = {d: 0.01 * (i + 1) for i, d in enumerate(prior_dates)}   # 0.01..0.05
    daily.update(prior_daily)
    return overlap_dates, prior_dates, five_min, daily


# ── _calibrate_daily_ranges ───────────────────────────────────────────────────────────────
def test_calibrate_daily_ranges_recovers_the_known_ratio_and_overlap_count():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    logged = []
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    assert n == len(overlap_dates) == 25
    assert ratio == pytest.approx(RATIO, abs=1e-9)
    assert any("25 overlap session" in m and "ratio" in m for m in logged)


def test_calibrate_daily_ranges_fails_safe_on_thin_overlap():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior(n_overlap=10)
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    logged = []
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    assert ratio is None and n == 10
    assert any("passing nothing" in m for m in logged)


def test_calibrate_daily_ranges_fails_safe_on_ratio_out_of_band():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior(ratio=3.0)   # way outside band
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, log=lambda m: None)
    assert ratio is None
    assert n == 25


def test_calibrate_daily_ranges_logs_once_per_call_set_not_per_leg():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    logged = []
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    calib_lines = [m for m in logged if "calibration:" in m]
    assert len(calib_lines) == 1, "second call same day must not log the calibration line again"


# ── vol_prior_ranges_for_leg: the end-to-end per-leg loader ──────────────────────────────
def test_vol_prior_ranges_for_leg_returns_calibrated_values_oldest_first(tmp_path):
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    paths = cs._paths(home=str(tmp_path / "home1"))
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()

    out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False,
                                      log=lambda m: None)
    expected = [RATIO * (0.01 * (i + 1)) for i in range(len(prior_dates))]
    assert out == pytest.approx(expected)


def test_vol_prior_ranges_for_leg_caps_at_need_plus_margin(tmp_path):
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior(n_prior=8)
    paths = cs._paths(home=str(tmp_path / "home2"))
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    # need=1 + DAILY_MARGIN_SESSIONS(=WARMUP_MARGIN_SESSIONS=10) = 11 > 8 available, so all
    # 8 come back; tighten by monkeypatching the margin down to prove the cap actually bites.
    mod, _seen = _stub_leg(required_lookback=1)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    import unittest.mock as mock
    with mock.patch.object(cs, "DAILY_MARGIN_SESSIONS", 2):
        out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False,
                                          log=lambda m: None)
    # need=1 + margin=2 = 3 -> only the LAST 3 (most recent) prior sessions
    expected = [RATIO * (0.01 * (i + 1)) for i in range(5, 8)]
    assert out == pytest.approx(expected)


def test_vol_prior_ranges_for_leg_none_when_leg_does_not_accept():
    mod, _seen = _stub_leg(required_lookback=10, declares=False)
    cfg = {"strategy": mod, "params": {}}
    # arrays/now are never read -- the function must return None right after the
    # _leg_accepts_vol_prior_ranges check, before touching either.
    out = cs.vol_prior_ranges_for_leg(cfg, {"index": pd.DatetimeIndex([])}, pd.Timestamp.now(),
                                      log=lambda m: None)
    assert out is None


def test_vol_prior_ranges_for_leg_none_when_strategy_declares_no_requirement():
    mod, _seen = _stub_leg(required_lookback=None)
    mod.REQUIRED_LOOKBACK_SESSIONS = None
    cfg = {"strategy": mod, "params": {}}
    out = cs.vol_prior_ranges_for_leg(cfg, {"index": pd.DatetimeIndex([])}, pd.Timestamp.now(),
                                      log=lambda m: None)
    assert out is None


def test_vol_prior_ranges_for_leg_none_when_daily_cache_missing(tmp_path):
    overlap_dates, _prior, five_min, _daily = _overlap_and_prior()
    paths = cs._paths(home=str(tmp_path / "home3"))   # never populated
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False,
                                      log=lambda m: None)
    assert out is None


def test_vol_prior_ranges_for_leg_none_when_calibration_fails(tmp_path):
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior(n_overlap=5)  # thin
    paths = cs._paths(home=str(tmp_path / "home4"))
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False,
                                      log=lambda m: None)
    assert out is None


def test_vol_prior_ranges_for_leg_never_raises_on_a_broken_daily_cache(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home5"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    with open(cs._cache_path("1d", paths), "w", encoding="utf-8") as f:
        f.write("not,a,valid,csv,header\nthis,is,garbage\n")
    overlap_dates, _prior, five_min, _daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    logged = []
    out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False,
                                      log=logged.append)
    assert out is None
    assert any("vol_prior_ranges unavailable" in m for m in logged)


def test_vol_prior_ranges_for_leg_never_fetches_the_network_when_fetch_is_false(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "home6"))
    called = []
    monkeypatch.setattr(cs, "fetch_and_merge_daily", lambda *a, **kw: called.append(1))
    overlap_dates, _prior, five_min, _daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False, log=lambda m: None)
    assert called == [], "fetch=False must never touch the network"


def test_real_orb_and_enguq_legs_get_nothing_from_vol_prior_ranges_for_leg(tmp_path):
    """Item 4 of the go-live audit spec: ORB_R6/ENGUQ_335 must get NOTHING, even when
    a (synthetic) daily cache is fully populated and would otherwise calibrate fine."""
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    paths = cs._paths(home=str(tmp_path / "home7"))
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    for leg_key in ("ORB_R6", "ENGUQ_335"):
        # ENGUQ_335 is a shadow leg since 2026-09-28 (same cfg)
        out = cs.vol_prior_ranges_for_leg(dict(cs.CROWN_LEGS, **cs.SHADOW_LEGS)[leg_key], arrays,
                                          now, paths=paths,
                                          fetch=False, log=lambda m: None)
        assert out is None, leg_key


# ── run_leg_trades: the actual pass-through into a leg's params ─────────────────────────
def _today_arrays_and_now():
    overlap_dates, _prior, five_min, _daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    now = pd.Timestamp(f"{overlap_dates[-1]} 10:00", tz=cs.TZ).to_pydatetime()
    return arrays, now


def test_run_leg_trades_forwards_vol_prior_ranges_when_available(tmp_path):
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    paths = cs._paths(home=str(tmp_path / "home8"))
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    now = pd.Timestamp(f"{overlap_dates[-1]} 10:00", tz=cs.TZ).to_pydatetime()
    mod, seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}

    cs.run_leg_trades(cfg, arrays, now=now, paths=paths, fetch=False)
    assert seen["vol_prior_ranges"] is not None
    assert len(seen["vol_prior_ranges"]) == len(prior_dates)


def test_run_leg_trades_omits_vol_prior_ranges_when_now_is_none():
    """No `now` (every pre-existing call site) reproduces today's behaviour exactly --
    cfg["params"] untouched, no daily-cache read attempted at all."""
    mod, seen = _stub_leg(required_lookback=10, declares=False)
    arrays, _now = _today_arrays_and_now()
    params = {}
    cfg = {"strategy": mod, "params": params}
    cs.run_leg_trades(cfg, arrays)   # now defaults to None
    assert seen["vol_prior_ranges"] == "ABSENT"
    assert cfg["params"] is params


def test_run_leg_trades_never_hands_vol_prior_ranges_to_a_strategy_that_did_not_opt_in(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home9"))
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    now = pd.Timestamp(f"{overlap_dates[-1]} 10:00", tz=cs.TZ).to_pydatetime()
    mod, seen = _stub_leg(required_lookback=10, declares=False)
    cfg = {"strategy": mod, "params": {}}
    cs.run_leg_trades(cfg, arrays, now=now, paths=paths, fetch=False)
    assert seen["vol_prior_ranges"] == "ABSENT"


def test_run_leg_trades_does_not_mutate_cfg_params_for_vol_prior_ranges(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home10"))
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates, daily))
    arrays = _intraday_arrays(overlap_dates, five_min)
    now = pd.Timestamp(f"{overlap_dates[-1]} 10:00", tz=cs.TZ).to_pydatetime()
    mod, seen = _stub_leg(required_lookback=10)
    params = {}
    cfg = {"strategy": mod, "params": params}
    cs.run_leg_trades(cfg, arrays, now=now, paths=paths, fetch=False)
    assert seen["vol_prior_ranges"] is not None
    assert params == {}
    assert cfg["params"] is params


def test_run_leg_trades_default_fetch_false_never_touches_the_network(monkeypatch):
    """Every pre-existing call site (tests, tools) omits `fetch` -- must default to
    False so none of them starts making live yfinance calls just by gaining `now`."""
    called = []
    monkeypatch.setattr(cs, "fetch_and_merge_daily", lambda *a, **kw: called.append(1))
    mod, seen = _stub_leg(required_lookback=10)
    arrays, now = _today_arrays_and_now()
    cfg = {"strategy": mod, "params": {}}
    cs.run_leg_trades(cfg, arrays, now=now)   # no paths, no fetch -- defaults
    assert called == []


def test_run_leg_trades_never_reads_the_daily_cache_when_paths_is_omitted(monkeypatch):
    """MINOR fix (go-live audit item 3.8, 2026-09-26): `now` alone (no `paths`) must
    not trigger the vol_prior_ranges bridge AT ALL -- not even a read-only,
    fetch=False read of the live DEFAULT_PATHS QQQ_1d.csv for an opted-in leg. Before
    this fix, an isolated test or tool calling run_leg_trades with `now` (e.g. to
    exercise session_in_progress) but no `paths` still silently depended on whatever
    sat in the live ohlc directory."""
    called = []
    monkeypatch.setattr(cs, "vol_prior_ranges_for_leg",
                        lambda *a, **kw: called.append(1) or None)
    mod, seen = _stub_leg(required_lookback=10)
    arrays, now = _today_arrays_and_now()
    cfg = {"strategy": mod, "params": {}}
    cs.run_leg_trades(cfg, arrays, now=now)   # no paths
    assert called == [], "vol_prior_ranges_for_leg must not run at all without explicit paths"


# ── _calibrate_daily_ranges: judged-day leak (minor fix, go-live audit item 3.8) ─────────
def test_calibrate_daily_ranges_drops_the_judged_days_own_session_from_overlap():
    """The live intraday arrays' own LAST session must not leak into its own scale
    factor: dropped from the overlap whenever `now`'s date equals or is after that
    session's date (in replay, the daily cache already holds that day's FINISHED bar
    while the intraday arrays only hold part of it)."""
    overlap_dates, _prior, five_min, daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    now = pd.Timestamp(f"{overlap_dates[-1]} 12:00", tz=cs.TZ).to_pydatetime()
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, now=now, log=lambda m: None)
    assert n == len(overlap_dates) - 1
    assert ratio == pytest.approx(RATIO, abs=1e-9)


def test_calibrate_daily_ranges_keeps_the_last_session_once_it_has_finished():
    """Once `now` is on a LATER calendar date than the arrays' own last session, that
    session is a genuinely finished bar and must stay in the overlap -- this is not a
    blanket "always drop the last session" rule."""
    overlap_dates, _prior, five_min, daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    later = overlap_dates[-1] + pd.Timedelta(days=5)
    now = pd.Timestamp(f"{later} 12:00", tz=cs.TZ).to_pydatetime()
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, now=now, log=lambda m: None)
    assert n == len(overlap_dates)


def test_calibrate_daily_ranges_now_none_is_byte_identical_to_before_the_fix():
    """`now=None` (every call site that predates this parameter) must skip the
    judged-day check entirely."""
    overlap_dates, _prior, five_min, daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    ratio, n = cs._calibrate_daily_ranges(daily_df, arrays, log=lambda m: None)
    assert n == len(overlap_dates)
    assert ratio == pytest.approx(RATIO, abs=1e-9)


# ── fail-safe logging: once per ET date per reason, not once per call (minor fix) ────────
def test_calibrate_daily_ranges_thin_overlap_reason_logs_once_not_every_call():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior(n_overlap=10)   # thin
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    logged = []
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    thin_lines = [m for m in logged if "passing nothing" in m and "required" in m]
    assert len(thin_lines) == 1, "the thin-overlap fail-safe reason must log once per ET date"


def test_calibrate_daily_ranges_ratio_out_of_band_reason_logs_once_not_every_call():
    overlap_dates, _prior, five_min, daily = _overlap_and_prior(ratio=3.0)   # outside band
    arrays = _intraday_arrays(overlap_dates, five_min)
    daily_df = _daily_epoch_df(overlap_dates, daily)
    logged = []
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    cs._calibrate_daily_ranges(daily_df, arrays, log=logged.append)
    out_of_band = [m for m in logged if "outside" in m and "passing nothing" in m]
    assert len(out_of_band) == 1


def test_missing_or_empty_daily_cache_is_logged_once_per_day_not_silently(tmp_path):
    """Item 3 of the go-live audit spec: the normal state today (no QQQ_1d.csv yet)
    used to return None with NO log at all -- now logged once a day."""
    paths = cs._paths(home=str(tmp_path / "missing_cache_log"))   # never populated
    overlap_dates, _prior, five_min, _daily = _overlap_and_prior()
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    now = pd.Timestamp("2026-03-10 12:00", tz=cs.TZ).to_pydatetime()
    logged = []
    out1 = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False, log=logged.append)
    out2 = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False, log=logged.append)
    assert out1 is None and out2 is None
    missing_lines = [m for m in logged if "QQQ_1d.csv" in m]
    assert len(missing_lines) == 1, "the missing-cache case must log once per ET date, not every call"


# ── the daily-cache refresh timing fix (CRITICAL, go-live audit item 3.8) ────────────────
# Before this fix, _maybe_refresh_daily_cache only ever fetched once `now` was at/after
# TODAY's own regular-session close (16:00:00) -- but the live loops (cloud_signal_thread,
# cmd_loop) only ever call step() while RTH_OPEN <= now <= RTH_CLOSE (also 16:00:00), so the
# two windows overlapped only at the single instant 16:00:00.000000. The fix ties the
# refresh to what the on-disk cache actually HOLDS (its newest date vs. the last COMPLETED
# session) rather than to `now`'s own time-of-day.
def _today_et_at(hour, minute):
    """`now` pinned to TODAY's real ET calendar date (so a freshly-written file's own
    real filesystem mtime falls on the same date as `now`.date()) at a fixed
    hour:minute -- used only to test the once-per-day ATTEMPT gate, which compares
    `now`'s date against the cache file's real mtime."""
    base = _dt.datetime.now(tz=cs._zi(cs.TZ))
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_maybe_refresh_daily_cache_fetches_once_when_missing_then_skips_same_day(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "refresh_missing"))
    calls = []

    def fake_fetch_yf_daily():
        calls.append(1)
        dates = pd.bdate_range(end=pd.Timestamp.now(tz=cs.TZ).normalize() - pd.Timedelta(days=1),
                               periods=30)
        idx = pd.DatetimeIndex(dates)
        return pd.DataFrame({"Open": [100.0] * 30, "High": [101.0] * 30, "Low": [99.0] * 30,
                             "Close": [100.0] * 30, "Volume": [1.0] * 30}, index=idx)

    monkeypatch.setattr(cs, "_fetch_yf_daily", fake_fetch_yf_daily)
    now1 = _today_et_at(9, 35)          # well before the close -- old code never fetched here
    cs._maybe_refresh_daily_cache(now1, paths, log=lambda m: None)
    assert len(calls) == 1, "a 09:35 tick against a missing cache must fetch once"

    now2 = _today_et_at(9, 40)          # a second tick, same day
    cs._maybe_refresh_daily_cache(now2, paths, log=lambda m: None)
    assert len(calls) == 1, "a second tick the same day must not fetch again"


def test_maybe_refresh_daily_cache_fetches_before_the_close_when_cache_is_stale(tmp_path, monkeypatch):
    """The CRITICAL fix itself: a stale cache (newest date older than the last
    completed session) must fetch even BEFORE today's own close -- the old code
    refused to fetch at all until now.time() >= 16:00."""
    paths = cs._paths(home=str(tmp_path / "refresh_stale"))
    stale_dates = _bdates("2020-01-06", 5)     # ancient -- nowhere near "the last completed session"
    _write_daily_cache(paths, _daily_epoch_df(stale_dates, {d: 0.02 for d in stale_dates}))
    # Backdate the file's mtime to yesterday so the once-per-day ATTEMPT gate does not
    # itself explain a fetch happening today.
    yesterday = _dt.datetime.now(tz=cs._zi(cs.TZ)) - _dt.timedelta(days=1)
    os.utime(cs._cache_path("1d", paths), (yesterday.timestamp(), yesterday.timestamp()))

    calls = []
    monkeypatch.setattr(cs, "_fetch_yf_daily", lambda: calls.append(1) or pd.DataFrame())
    now = _today_et_at(9, 35)          # before the close
    cs._maybe_refresh_daily_cache(now, paths, log=lambda m: None)
    assert len(calls) == 1, "a stale cache must fetch even on a pre-close tick"


def test_maybe_refresh_daily_cache_does_not_refetch_when_already_covering_the_needed_session(tmp_path, monkeypatch):
    """A cache that ALREADY holds the last completed session must not be re-fetched
    just because its mtime is not today's -- only staleness (what the spec asks for),
    not merely "not yet attempted today", should trigger a fetch."""
    paths = cs._paths(home=str(tmp_path / "refresh_sufficient"))
    now = _today_et_at(9, 35)          # before the close -- "needed" = the prior session
    needed = cs._last_completed_session_date(now)
    covering_dates = cs.market_calendar.sessions_between(needed - _dt.timedelta(days=60), needed)
    _write_daily_cache(paths, _daily_epoch_df(covering_dates, {d: 0.02 for d in covering_dates}))
    old_mtime = (_dt.datetime.now(tz=cs._zi(cs.TZ)) - _dt.timedelta(days=1)).timestamp()
    os.utime(cs._cache_path("1d", paths), (old_mtime, old_mtime))

    calls = []
    monkeypatch.setattr(cs, "_fetch_yf_daily", lambda: calls.append(1) or pd.DataFrame())
    cs._maybe_refresh_daily_cache(now, paths, log=lambda m: None)
    assert calls == [], "a cache that already covers the last completed session must not re-fetch"


def test_fetch_and_merge_daily_never_stores_todays_unfinished_row_before_the_close(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "unfinished_row"))
    now = _today_et_at(9, 35)          # before the close
    today = now.date()
    yesterday = today - _dt.timedelta(days=1)
    while not cs.market_calendar.is_session(yesterday):
        yesterday -= _dt.timedelta(days=1)
    idx = pd.DatetimeIndex([pd.Timestamp(yesterday), pd.Timestamp(today)])
    fake = pd.DataFrame({"Open": [100.0, 105.0], "High": [101.0, 999.0], "Low": [99.0, 1.0],
                         "Close": [100.0, 106.0], "Volume": [1.0, 1.0]}, index=idx)
    monkeypatch.setattr(cs, "_fetch_yf_daily", lambda: fake)
    merged = cs.fetch_and_merge_daily(paths, now=now, log=lambda m: None)
    import numpy as np
    dates = pd.to_datetime(merged["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    assert today not in set(dates), "today's own unfinished row must never be written to disk"
    assert yesterday in set(dates)


def test_fetch_and_merge_daily_keeps_todays_row_once_the_session_has_closed(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "finished_row"))
    now = _today_et_at(16, 5)           # after the close
    today = now.date()
    if not cs.market_calendar.is_session(today):
        pytest.skip("today is not a trading session on the real calendar")
    idx = pd.DatetimeIndex([pd.Timestamp(today)])
    fake = pd.DataFrame({"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5],
                         "Volume": [1.0]}, index=idx)
    monkeypatch.setattr(cs, "_fetch_yf_daily", lambda: fake)
    merged = cs.fetch_and_merge_daily(paths, now=now, log=lambda m: None)
    dates = pd.to_datetime(merged["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    assert today in set(dates), "today's own FINISHED row must be kept once the close has passed"


def test_vol_prior_ranges_for_leg_never_uses_an_unfinished_todays_row_even_if_already_cached(tmp_path):
    """Defense in depth: even if QQQ_1d.csv already holds a stray in-progress row for
    `now`'s own date (written by an older build, or any other writer), reading it
    must filter that row out before calibrating or selecting prior sessions."""
    overlap_dates, prior_dates, five_min, daily = _overlap_and_prior()
    paths = cs._paths(home=str(tmp_path / "unfinished_read"))
    now = pd.Timestamp(f"{overlap_dates[-1]} 09:35", tz=cs.TZ).to_pydatetime()   # mid-session
    today = now.date()
    bad = dict(daily)
    bad[today] = 999.0                                      # a wild, obviously-unfinished value
    _write_daily_cache(paths, _daily_epoch_df(prior_dates + overlap_dates + [today], bad))
    arrays = _intraday_arrays(overlap_dates, five_min)
    mod, _seen = _stub_leg(required_lookback=10)
    cfg = {"strategy": mod, "params": {}}
    out = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False, log=lambda m: None)
    expected = [RATIO * (0.01 * (i + 1)) for i in range(len(prior_dates))]
    assert out == pytest.approx(expected), "today's stray row must not perturb the calibration or the priors"

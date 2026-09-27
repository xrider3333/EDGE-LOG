"""augur_strategies/NOISE_1_0.py's `vol_prior_ranges` opt-in runtime kwarg (go-live
audit item 3.8, 2026-09-26 -- see that file's own comments on VOL_SKIP_REF_SESSIONS /
_vol_percentile). Covers:
  1. `_vol_percentile` is byte-identical to before this kwarg existed when
     `prior_ranges` is omitted or None (the only path a normal backtest run ever hits).
  2. `_vol_percentile` ranks correctly once a prefix of real prior sessions is handed
     in -- verified against hand-computed expected percentiles, not just "changed".
  3. The kwarg passes through the live wrapper chain NOISE_1_8_CT304.py ->
     NOISE_1_1_NBHD.py -> NOISE_1_0.py untouched, via each wrapper's own **kw /
     _BASE_ARGS-style forwarding -- proved with spy stubs, the same style
     tests/test_cloud_signal_session_in_progress.py already uses for that other
     kwarg-passthrough feature.
"""
import importlib.util as _ilu
import inspect
import os

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(ROOT, "augur_strategies")


def _load(name, alias=None):
    path = os.path.join(STRAT_DIR, name)
    spec = _ilu.spec_from_file_location(alias or name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def noise10():
    return _load("NOISE_1_0.py")


# ── _vol_percentile: default path is byte-identical ──────────────────────────────────────
def _synthetic_sessions(n_sess=6, sess_len=3):
    """n_sess sessions of sess_len bars each, strictly increasing (H-L)/C so ranks are
    unambiguous: session si has (H-L)/C = (10 + 2*si) / 95."""
    h, l, c = [], [], []
    sess_bounds = []
    a = 0
    for si in range(n_sess):
        hi = 100 + si
        lo = 90 - si
        h += [hi] * sess_len
        l += [lo] * sess_len
        c += [95.0] * sess_len
        sess_bounds.append((a, a + sess_len))
        a += sess_len
    return np.array(h, float), np.array(l, float), np.array(c, float), sess_bounds


def test_vol_percentile_default_matches_omitting_the_kwarg_entirely(noise10):
    h, l, c, sess_bounds = _synthetic_sessions()
    a = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2)
    b = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2, prior_ranges=None)
    d = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2, prior_ranges=[])
    assert np.array_equal(a, b, equal_nan=True)
    assert np.array_equal(a, d, equal_nan=True)


def test_vol_percentile_default_early_sessions_stay_nan_below_min_obs(noise10):
    h, l, c, sess_bounds = _synthetic_sessions()
    pct = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2)
    assert np.isnan(pct[0]) and np.isnan(pct[1]) and np.isnan(pct[2])
    assert pct[3] == pytest.approx(100.0)   # both prior in-array sessions are smaller
    assert pct[4] == pytest.approx(100.0)


def test_run_backtest_default_none_is_a_documented_no_op(noise10):
    """The DEFAULT_PARAMS/signature contract: vol_prior_ranges defaults to None and is
    not a DEFAULT_PARAMS knob (a search space must never sweep it)."""
    sig = inspect.signature(noise10.run_backtest)
    assert sig.parameters["vol_prior_ranges"].default is None
    assert "vol_prior_ranges" not in noise10.DEFAULT_PARAMS


# ── _vol_percentile: correct ranks with a real prefix ────────────────────────────────────
def test_vol_percentile_with_prior_ranges_matches_hand_computed_ranks(noise10):
    h, l, c, sess_bounds = _synthetic_sessions()
    prior = [0.05, 0.10, 0.50]   # oldest first, immediately before session 0
    pct = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2, prior_ranges=prior)
    # hand-derived in the exploration pass (see the module docstring): with this prefix
    # every in-array session, INCLUDING session 0, now clears min_obs.
    expected = [100.0, 200.0 / 3, 75.0, 80.0, 250.0 / 3]
    for si, exp in enumerate(expected):
        assert pct[si] == pytest.approx(exp, abs=1e-6), (si, pct[si], exp)


def test_vol_percentile_prior_ranges_respects_ref_n_window(noise10):
    """A prior_ranges prefix far longer than ref_n must not let ranking reach past
    ref_n sessions back -- the window depth is still bounded by ref_n, prior_ranges
    only lets it actually REACH that depth near the array's own start.

    10 old/BIG sessions followed by 5 recent/small ones (oldest first), so the
    session immediately before the array (the last of the 5 small ones, value 5)
    ranks differently depending on how far back the reference window can see."""
    h, l, c, sess_bounds = _synthetic_sessions(n_sess=1, sess_len=2)
    prior = [100.0] * 10 + [1.0, 2.0, 3.0, 4.0, 5.0]
    pct_narrow = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=5, min_obs=2,
                                         prior_ranges=prior)
    pct_wide = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=20, min_obs=2,
                                       prior_ranges=prior)
    # ref_n=5 sees only [100, 1, 2, 3, 4] -> 4 of 5 are smaller than 5 -> 80%.
    assert pct_narrow[0] == pytest.approx(80.0)
    # ref_n=20 sees all 14 prior entries [100]*10 + [1,2,3,4] -> 4 of 14 -> ~28.57%.
    assert pct_wide[0] == pytest.approx(400.0 / 14.0)
    assert pct_wide[0] < pct_narrow[0]


def test_vol_percentile_min_obs_counts_prior_ranges_too(noise10):
    """Judging session 0 needs a reference window strictly BEFORE the session
    immediately preceding it -- with min_obs=2 that means at least 3 prior_ranges
    entries (the 3rd is the judged one; the first 2 are its own reference window),
    not merely 2."""
    h, l, c, sess_bounds = _synthetic_sessions(n_sess=1, sess_len=2)
    pct_1 = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2,
                                    prior_ranges=[0.05])
    assert np.isnan(pct_1[0])
    pct_2 = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2,
                                    prior_ranges=[0.05, 0.10])
    assert np.isnan(pct_2[0]), "only 1 reference session available -- still short of min_obs=2"
    pct_3 = noise10._vol_percentile(h, l, c, sess_bounds, ref_n=10, min_obs=2,
                                    prior_ranges=[0.05, 0.10, 0.20])
    assert not np.isnan(pct_3[0]), "now 2 reference sessions available -- clears min_obs=2"


# ── run_backtest: vol_prior_ranges flows into _vol_percentile only when vol_skip_pct > 0 ──
def test_run_backtest_ignores_prior_ranges_when_vol_skip_pct_is_off(noise10, monkeypatch):
    calls = []
    orig = noise10._vol_percentile

    def spy(*a, **kw):
        calls.append(kw)
        return orig(*a, **kw)
    monkeypatch.setattr(noise10, "_vol_percentile", spy)

    n = 40
    o = np.linspace(100, 101, n)
    h = o + 0.5
    l = o - 0.5
    c = o + 0.1
    day_id = np.repeat(np.arange(8), 5)
    noise10.run_backtest(o, h, l, c, day_id=day_id, lookback=2,
                         vol_skip_pct=0.0, vol_prior_ranges=[0.01, 0.02])
    assert calls == [], "vol_skip_pct=0 must never even call _vol_percentile"


def test_run_backtest_forwards_prior_ranges_into_vol_percentile_when_active(noise10, monkeypatch):
    captured = {}
    orig = noise10._vol_percentile

    def spy(*a, **kw):
        captured.update(kw)
        return orig(*a, **kw)
    monkeypatch.setattr(noise10, "_vol_percentile", spy)

    n = 40
    o = np.linspace(100, 101, n)
    h = o + 0.5
    l = o - 0.5
    c = o + 0.1
    day_id = np.repeat(np.arange(8), 5)
    prior = [0.01, 0.02, 0.03]
    noise10.run_backtest(o, h, l, c, day_id=day_id, lookback=2,
                         vol_skip_pct=90.0, vol_prior_ranges=prior)
    assert captured.get("prior_ranges") == prior


# ── Wrapper pass-through: NOISE_1_1_NBHD.py -> NOISE_1_0.py ──────────────────────────────
def test_nbhd_forwards_vol_prior_ranges_to_its_base():
    nbhd = _load("NOISE_1_1_NBHD.py", "test_nbhd_vpr")
    assert "vol_prior_ranges" in nbhd._BASE_ARGS, (
        "NBHD's _BASE_ARGS is computed by inspecting NOISE_1_0.py's OWN signature -- "
        "if this fails, NOISE_1_0.py stopped declaring the kwarg by name")
    captured = {}

    def spy(*a, **kw):
        captured.update(kw)
        return None
    import types
    assert isinstance(nbhd._base, types.ModuleType)
    import unittest.mock as mock
    with mock.patch.object(nbhd._base, "run_backtest", spy):
        nbhd.run_backtest([1, 2], [1, 2], [1, 2], [1, 2], vol_prior_ranges=[0.1, 0.2])
    assert captured.get("vol_prior_ranges") == [0.1, 0.2]


# ── Wrapper pass-through: NOISE_1_8_CT304.py -> NOISE_1_1_NBHD.py ────────────────────────
def test_ct304_forwards_vol_prior_ranges_to_its_base():
    ct304 = _load("NOISE_1_8_CT304.py", "test_ct304_vpr")
    captured = {}

    def spy(*a, **kw):
        captured.update(kw)
        return {"trades": []}   # short-circuits ct304.run_backtest right after the call
    import unittest.mock as mock
    with mock.patch.object(ct304._base, "run_backtest", spy):
        out = ct304.run_backtest(
            [1.0] * 5, [1.0] * 5, [1.0] * 5, [1.0] * 5,
            day_id=np.array([0, 0, 0, 0, 0]),
            gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=1.0,
            vol_prior_ranges=[0.1, 0.2, 0.3],
        )
    assert out is None   # {"trades": []} -> no trades -> None, as documented
    assert captured.get("vol_prior_ranges") == [0.1, 0.2, 0.3]


def test_ct304_never_forwards_vol_prior_ranges_when_omitted():
    """Byte-identical/no-op check: a call with no vol_prior_ranges at all must not add
    the key to the base call (proves the passthrough is additive, not defaulting)."""
    ct304 = _load("NOISE_1_8_CT304.py", "test_ct304_vpr_absent")
    captured = {}

    def spy(*a, **kw):
        captured.update(kw)
        return {"trades": []}
    import unittest.mock as mock
    with mock.patch.object(ct304._base, "run_backtest", spy):
        ct304.run_backtest(
            [1.0] * 5, [1.0] * 5, [1.0] * 5, [1.0] * 5,
            day_id=np.array([0, 0, 0, 0, 0]),
            gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=1.0,
        )
    assert "vol_prior_ranges" not in captured

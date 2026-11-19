"""phantom_safe: the BACKTEST default stays False, the LIVE path forces True.

MANAGER ruling (A'), 2026-11-18, after the VERIFIER's read. Flipping the kwarg default was
refused: augur_engine/auto.py's make_slice_evaluator calls `fn(O[a:b], H[a:b], L[a:b], C[a:b],
...)`, so every IS trial window, every walk-forward fold and the lockbox is handed its own
TRUNCATED array -- each slice end is an array end, the guard fires there, and a stored run could
move at every fold boundary and flip a near-tied IS champion. A frozen crown must keep its
answer. The exposure the flip was meant to close -- a NEW leg, shadow arm or replay driver
silently inheriting the pre-fix fill scan -- is closed at the live path's own door instead
(api/live_safety.py), where the leg's params no longer decide it.

Coverage:
  1. The backtest default is still False in every file that takes the kwarg and in the
     compiled walk, and the kwarg is still not a tunable knob.
  2. Every CROWN_LEGS / SHADOW_LEGS / PAPER_LEGS entry on a file that takes the flag ends up
     running with True -- including a leg that declares nothing, which is the "new leg
     registered unsafe" case.
  3. The live choke points really pass it: api/cloud_signal.py's run_leg_trades hands the
     engine phantom_safe=True for an ENGU-Q leg whose params omit it, and leaves a
     non-ENGU-Q leg's params untouched.
  4. The refusal is LOUD and written once per leg, not per tick.
  5. POSITIVE CONTROL (the VERIFIER's rule): a truncated tape MUST behave differently with
     the flag on and off. If it does not, these cases prove nothing and the suite must say so
     rather than passing quietly -- the same rule the parity harness now carries, after a
     harness that could not set the flag reported "0 differ" out of seven TypeErrors.
"""
import inspect
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import live_safety as ls                             # noqa: E402
from augur_engine import fastloop                             # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_enguq_phantom_fill import (                         # noqa: E402
    FULL_ARRAYS, BAR_B_FILL, _trades_on)

KNOB_FILES = ["ENGUQ_1M_ETH_HC_1_0.py", "ENGUQ_1M_ETH_R2_1_0.py", "ENGUQ_1M_ETH_R62_1_0.py",
              "ENGUQ_1M_ETH_R65_1_0.py", "ENGUQ_1M_ETH_R66_1_0.py", "ENGUQ_RTH_1_0.py"]


def _load(f):
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "mod_" + f[:-3], os.path.join(ROOT, "augur_strategies", f))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _quiet_memo():
    ls._reset_said_for_tests()
    yield
    ls._reset_said_for_tests()


# ── 1. the backtest default is unchanged -------------------------------------------------
@pytest.mark.parametrize("f", KNOB_FILES)
def test_backtest_default_stays_off(f):
    """If this ever reads True, every stored WF/LB run's fold ends can move -- see the
    module docstring. The live path does not need it: it forces the flag itself."""
    sig = inspect.signature(_load(f).run_backtest)
    assert "phantom_safe" in sig.parameters, f + " must still accept the kwarg"
    assert sig.parameters["phantom_safe"].default is False, (
        f + ": the BACKTEST default must stay False so a sliced run (every IS window, WF "
        "fold and the lockbox) keeps its stored answer")


def test_compiled_walk_default_stays_off():
    assert inspect.signature(fastloop.engu_walk).parameters["phantom_safe"].default is False


def test_the_kwarg_is_still_not_a_tunable_knob():
    for f in KNOB_FILES:
        assert "phantom_safe" not in (getattr(_load(f), "DEFAULT_PARAMS", {}) or {}), f


# ── 2. every registered live leg ends up safe --------------------------------------------
def _registered_legs():
    from api import cloud_signal as cs
    from api import paper as pp
    out = []
    for name, reg in (("CROWN_LEGS", getattr(cs, "CROWN_LEGS", {})),
                      ("SHADOW_LEGS", getattr(cs, "SHADOW_LEGS", {})),
                      ("PAPER_LEGS", getattr(pp, "PAPER_LEGS", {}))):
        # CROWN_LEGS / SHADOW_LEGS are keyed dicts; PAPER_LEGS is a LIST of leg dicts.
        items = (reg or {}).items() if isinstance(reg, dict) else [
            ((c or {}).get("key"), c) for c in (reg or [])]
        for key, cfg in items:
            if isinstance(cfg, dict) and cfg.get("strategy"):
                out.append((name, key, cfg))
    return out


def test_every_registered_leg_on_a_phantom_safe_file_runs_safe():
    """The guarantee MANAGER asked for: not "the leg declares it" but "the leg runs it"."""
    checked = 0
    for reg, key, cfg in _registered_legs():
        if not ls.accepts_phantom_safe(cfg["strategy"]):
            continue
        checked += 1
        forced = ls.force_phantom_safe(cfg["strategy"], dict(cfg.get("params") or {}),
                                       caller="test", leg_key=key, log=lambda *_: None)
        assert forced.get("phantom_safe") is True, "%s[%s] would run unsafe" % (reg, key)
    assert checked, ("no registered leg runs a phantom_safe-aware file -- this test has gone "
                     "blind; check the registries and the reflection helper")


def test_a_new_leg_registered_without_the_flag_still_runs_safe():
    """The case the default flip was meant to cover, and the reason the params cannot be
    what decides it."""
    cfg = {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": {"limit_atr": 0.55}}
    forced = ls.force_phantom_safe(cfg["strategy"], cfg["params"], caller="test",
                                   leg_key="ENGUQ_NEW", log=lambda *_: None)
    assert forced["phantom_safe"] is True
    assert "phantom_safe" not in cfg["params"], "the caller's own dict must not be mutated"


def test_a_leg_that_declared_false_is_overridden():
    forced = ls.force_phantom_safe("ENGUQ_1M_ETH_R2_1_0.py", {"phantom_safe": False},
                                   caller="test", leg_key="X", log=lambda *_: None)
    assert forced["phantom_safe"] is True, "a declaration cannot opt a LIVE leg back into the bug"


def test_a_strategy_without_the_kwarg_is_left_alone():
    """No non-ENGU-Q leg's call may change: same object back, so nothing is even copied."""
    params = {"tilt_mult": 2.0}
    assert ls.force_phantom_safe("NOISE_1_8_CT304.py", params, caller="test") is params


def test_a_kwargs_catch_all_does_not_count_as_accepting():
    class Stub:
        __name__ = "stub"

        @staticmethod
        def run_backtest(o, h, l, c, **kwargs):
            return {}

    assert ls.accepts_phantom_safe(Stub) is False, (
        "a file that swallows the kwarg would be forced 'safe' while running exactly as "
        "before -- a forcing that cannot be verified is worse than none")


def test_an_unresolvable_strategy_never_raises():
    assert ls.accepts_phantom_safe("NO_SUCH_FILE_12345.py") is False
    p = {"a": 1}
    assert ls.force_phantom_safe("NO_SUCH_FILE_12345.py", p, caller="test") is p


# ── 3. the live choke point actually passes it -------------------------------------------
def test_cloud_signal_hands_the_engine_phantom_safe_true(monkeypatch):
    from api import cloud_signal as cs
    seen = {}

    def fake_engine(strategy, arrays=None, params=None, **kw):
        seen["strategy"] = strategy
        seen["params"] = dict(params or {})
        return {"trades": []}

    monkeypatch.setattr(cs, "engine_run_backtest", fake_engine)
    arrays = {k: v for k, v in FULL_ARRAYS.items()}
    arrays["index"] = list(range(len(FULL_ARRAYS["close"])))
    cfg = {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": {"limit_atr": 0.55},
           "timeframe": "1m"}
    cs.run_leg_trades(cfg, arrays, leg_key="ENGUQ_NEW", log=lambda *_: None)
    assert seen["params"].get("phantom_safe") is True, (
        "the live signal engine must receive the flag, not merely have a helper available")


def test_cloud_signal_leaves_a_non_enguq_leg_untouched(monkeypatch):
    from api import cloud_signal as cs
    seen = {}

    def fake_engine(strategy, arrays=None, params=None, **kw):
        seen["params"] = dict(params or {})
        return {"trades": []}

    monkeypatch.setattr(cs, "engine_run_backtest", fake_engine)
    arrays = {k: v for k, v in FULL_ARRAYS.items()}
    arrays["index"] = list(range(len(FULL_ARRAYS["close"])))
    cfg = {"strategy": "NOISE_1_8_CT304.py", "params": {"tilt_mult": 2.0}, "timeframe": "5m"}
    cs.run_leg_trades(cfg, arrays, leg_key="NOISE_382", log=lambda *_: None)
    assert "phantom_safe" not in seen["params"]


# ── 4. the refusal is loud, and said once ------------------------------------------------
def test_the_refusal_is_loud_and_written_once_per_leg():
    lines = []
    for _ in range(5):
        ls.force_phantom_safe("ENGUQ_1M_ETH_R2_1_0.py", {}, caller="test", leg_key="ENGUQ_NEW",
                              log=lines.append)
    assert len(lines) == 1, "once per leg, not once per tick"
    assert "REFUSED" in lines[0] and "phantom_safe" in lines[0] and "ENGUQ_NEW" in lines[0]


def test_a_leg_that_declares_true_says_nothing():
    lines = []
    ls.force_phantom_safe("ENGUQ_1M_ETH_R2_1_0.py", {"phantom_safe": True}, caller="test",
                          leg_key="ENGUQ_335", log=lines.append)
    assert lines == [], "a leg that declares its own safety is not a problem to announce"


# ── 5. POSITIVE CONTROL ------------------------------------------------------------------
@pytest.mark.parametrize("fastloop_off", [False, True], ids=["compiled", "interpreted"])
def test_positive_control_the_flag_changes_a_truncated_read(fastloop_off):
    """Without this, every case above could pass while the flag reached nothing. A harness
    or a suite that cannot demonstrate a difference has proved nothing about safety."""
    trunc = BAR_B_FILL + 1
    off = [t[0] for t in _trades_on(FULL_ARRAYS, trunc, phantom_safe=False,
                                    fastloop_off=fastloop_off)]
    on = [t[0] for t in _trades_on(FULL_ARRAYS, trunc, phantom_safe=True,
                                   fastloop_off=fastloop_off)]
    assert off != on, "the flag must change a truncated read, or nothing here means anything"
    assert BAR_B_FILL in off and BAR_B_FILL not in on


@pytest.mark.parametrize("fastloop_off", [False, True], ids=["compiled", "interpreted"])
def test_a_complete_tape_is_identical_both_ways(fastloop_off):
    """The other half of the control: with every bar present the guard cannot fire, which is
    why leaving the backtest default alone costs the live path nothing."""
    n = len(FULL_ARRAYS["close"])
    assert (_trades_on(FULL_ARRAYS, n, phantom_safe=False, fastloop_off=fastloop_off)
            == _trades_on(FULL_ARRAYS, n, phantom_safe=True, fastloop_off=fastloop_off))

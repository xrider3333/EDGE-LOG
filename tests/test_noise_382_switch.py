"""tests/test_noise_382_switch.py -- OWNER DECISION 2026-09-23: swap the Webull paper
book's NOISE leg from run #304 to run #382 (NOISE_1_8_CT304.py -- the #304 crown's own
core, frozen literally inside that file, plus the validated hourly-compression SIZE
tilt; params {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15},
read from the run #382 doc).

tests/test_qqq_exec_engine_source.py's own leg-definition test
(test_noise_leg_resolves_to_run_382) already covers CROWN_LEGS's shape and both
ENGINE_LEG_MAP keys -- updated alongside this file, in the same change, not repeated
here. This file covers what is genuinely NEW:

  1. The run #382 params sit inside NOISE_1_8_CT304.py's own FENCED admissible set --
     proved against the file's OWN _in_neighbourhood check, not re-derived by hand.
  2. NOISE_1_8_CT304.py actually runs -- through run_leg_trades, on the real, on-disk
     QQQ 5-minute bar cache -- and produces trades carrying a real per-trade `size`.
     test_cloud_signal_trade_size.py already covers the size-inversion MATH against a
     synthetic stub; this proves the real strategy file exercises that same contract
     end to end, on real data.
  3. THE COLD-START PROOF -- the single biggest risk of this switch. A brand-new engine
     key has empty cloud_signal state, so its first tick re-derives the strategy's WHOLE
     trade list over the full production warm-up window (60 sessions, not a reduced
     test-speed shortcut). Only ONE event -- SEED -- may come out of that first tick,
     however many real historical trades the strategy actually took; a real ENTRY/EXIT
     burst would hand a downstream executor dozens of orders for trades that already
     closed weeks ago.
  4. api/qqq_exec.py's ENGINE_LEG_MAP now deliberately maps TWO engine keys to one EXEC
     leg ("NOISE_382" live, "NOISE_304" retired-but-kept). Proves the EXEC-leg-back-to-
     engine-key reverse lookup (_engine_mark_price, via _engine_key_for_leg) resolves to
     the LIVE key -- the one cloud_signal.CROWN_LEGS actually has -- not whichever
     mapped key happens to iterate first.

Skips cleanly (does not fail) when the owner's local QQQ 5-minute bar cache is absent,
e.g. a fresh clone or a machine that is not the owner's box -- same convention as
tests/test_cloud_signal.py. That file's own HAS_REAL_CACHE also treats a cache that
EXISTS but is EMPTY as a loud failure rather than a skip (a real outage, not a missing-
environment fact); that extra guard is deliberately not duplicated here to avoid two
files disagreeing about the same on-disk file -- test_cloud_signal.py already owns it.
"""
import os
import shutil
import sys
import tempfile

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                      # noqa: E402
from api import qqq_exec as qe                      # noqa: E402
from augur_engine.strategies import load_strategy   # noqa: E402

REAL_CACHE_5M = r"C:\EdgeLog\ohlc\QQQ_5m.csv"


def _cache_state(path):
    try:
        return True, os.path.getsize(path) == 0
    except OSError:
        return False, False


_PRESENT, _EMPTY = _cache_state(REAL_CACHE_5M)
HAS_REAL_5M_CACHE = _PRESENT and not _EMPTY
_CACHE_SKIP = "no local QQQ 5m bar cache on this machine: %s" % REAL_CACHE_5M

NOISE_382_PARAMS = {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15}


# ── 1. Params inside the strategy file's own fence ───────────────────────────────────────
def test_noise_382_params_are_inside_the_fenced_admissible_set():
    """CROWN_LEGS["NOISE_382"]'s params must be exactly the run #382 doc's champion cell,
    and NOISE_1_8_CT304.py's OWN fence (_in_neighbourhood, not re-derived here) must
    accept them -- the file REFUSES (returns None), never clamps, an out-of-set config,
    so an off-by-one-step value here would silently kill every signal, not misprice one."""
    leg = cs.CROWN_LEGS["NOISE_382"]
    assert leg["strategy"] == "NOISE_1_8_CT304.py"
    assert leg["timeframe"] == "5m"
    assert leg["params"] == NOISE_382_PARAMS
    assert leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS, \
        "same warm-up as every other crown leg -- the task calls for no change here"

    mod = load_strategy("NOISE_1_8_CT304.py")
    assert mod._in_neighbourhood(leg["params"]) is True, \
        "run #382's params must sit inside the strategy file's own declared/fenced set"
    # and a config ONE step outside it really is refused, not clamped -- proves the fence
    # itself still bites, so the assertion above is meaningful and not vacuously true.
    assert mod._in_neighbourhood(dict(leg["params"], tilt_mult=1.75)) is False


def _real_bar_frame():
    df = cs.load_cached_bars("5m", cs.DEFAULT_PATHS)
    if df is None or not len(df):
        pytest.skip("real 5m cache present but unreadable/empty")
    return df


def _now_past_the_newest_bar(df):
    """An aware ET timestamp comfortably (1 hour) past the newest cached bar's own OPEN
    time, so every bar in the cache reads as CLOSED (see cs._closed_cutoff_epoch) --
    the exact newest-bar edge is not the point of either test below."""
    newest_open = pd.Timestamp(int(df["time"].max()), unit="s", tz="UTC").tz_convert(cs.TZ)
    return newest_open + pd.Timedelta(hours=1)


# ── 2. The real strategy, on the real cache, through run_leg_trades ──────────────────────
@pytest.mark.skipif(not HAS_REAL_5M_CACHE, reason=_CACHE_SKIP)
def test_noise_382_runs_through_run_leg_trades_on_real_bars_and_sizes_its_trades():
    """NOISE_1_8_CT304.py end to end: real cached QQQ 5-minute bars -> the shared engine
    wrapper -> run_leg_trades's per-trade size contract. Not a stub -- if the real file
    ever stops sizing trades (or stops trading altogether) on real data, this fails."""
    df = _real_bar_frame()
    now = _now_past_the_newest_bar(df)

    arrays = cs.closed_arrays(df, now.to_pydatetime(), "5m", cs.DEFAULT_WARMUP_SESSIONS)
    assert arrays is not None, "the real cache must yield a usable warm-up window"

    trades = cs.run_leg_trades(cs.CROWN_LEGS["NOISE_382"], arrays, leg_key="NOISE_382")
    assert trades, "NOISE_1_8_CT304.py must take at least one real trade over a 60-session window"
    for t in trades:
        assert isinstance(t["size"], float) and t["size"] > 0 and t["shares"] >= 0
        # tilt_mult=2.0 in the fenced params: every trade's size must be either the base
        # (1.0, gate off) or the tilt (2.0, gate on) -- nothing else is reachable.
        assert t["size"] == pytest.approx(1.0) or t["size"] == pytest.approx(2.0), t["size"]


# ── 3. THE COLD-START PROOF ───────────────────────────────────────────────────────────────
@pytest.mark.skipif(not HAS_REAL_5M_CACHE, reason=_CACHE_SKIP)
def test_fresh_noise_382_key_cold_starts_without_an_entry_exit_burst(tmp_path):
    """THE central risk of this switch. NOISE_382 has never existed as an engine key
    before, so state.json has no leg_state for it -- exactly the situation _diff_leg's
    COLD START rule exists for (see that function's own docstring). Replaying a FULL
    production-depth (60-session) window through the real strategy on the real cache
    must emit exactly one SEED event and nothing else, however many real historical
    trades the strategy actually took, and must never re-emit them afterwards."""
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    shutil.copy(REAL_CACHE_5M, os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"))

    legs = {"NOISE_382": cs.CROWN_LEGS["NOISE_382"]}
    assert legs["NOISE_382"]["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS, \
        "must exercise the SHIPPED config at full depth, not a reduced test shortcut"

    df = _real_bar_frame()
    now = _now_past_the_newest_bar(df)

    assert not os.path.exists(paths["state_path"]), "must start from truly empty state"
    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)

    got = [e["event"] for e in events]
    assert got == ["SEED"], (
        "a fresh engine key's first tick must emit NO ENTRY/EXIT, only SEED -- got: %r" % got)

    state = cs._load_state(paths)
    leg_state = state["legs"]["NOISE_382"]
    assert leg_state["seeded"] is True
    n_absorbed = len(leg_state["trades"])
    assert n_absorbed > 0, (
        "this proof is only meaningful if the real strategy actually took real trades "
        "over the window -- zero absorbed trades would pass trivially without proving "
        "anything; NOISE_1_8_CT304.py should be trading over 60 real sessions")
    assert ("absorbed %d historical trade" % n_absorbed) in events[0]["reason"]
    # every absorbed trade (even one still open at seed time) is already marked emitted --
    # an executor booting onto this key today must not receive any of them as new orders.
    assert all(rec.get("exit_emitted") for rec in leg_state["trades"].values())

    # idempotent: replaying the exact same tick again finds nothing new either.
    assert cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []


# ── 4. qqq_exec's reverse lookup must prefer the LIVE engine key ─────────────────────────
def test_engine_mark_price_prefers_the_live_noise_382_key_over_the_retired_one(tmp_path, monkeypatch):
    """ENGINE_LEG_MAP now maps BOTH NOISE_382 (live) and NOISE_304 (retired, kept only so
    an old ledger row / in-flight trade id still resolves) to the EXEC leg "NOISE". But
    CROWN_LEGS holds only ONE of them at a time -- NOISE_304 was REPLACED there, not kept
    alongside -- so a reverse lookup that just takes the first mapped key can land on the
    retired one, find nothing in CROWN_LEGS, and mark the live leg's price unavailable
    (which would silently zero its unrealized P&L and block EOD/breaker flattening and
    orphan-broker repair, all of which call _engine_mark_price). It must resolve to
    whichever mapped key CROWN_LEGS actually has."""
    assert "NOISE_304" not in cs.CROWN_LEGS and "NOISE_382" in cs.CROWN_LEGS
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    bars = pd.DataFrame({"time": [1_758_000_000, 1_758_000_300],
                         "open": [700.0, 701.0], "high": [700.5, 701.5],
                         "low": [699.5, 700.5], "close": [700.25, 701.4],
                         "volume": [1000.0, 1000.0]})
    bars.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)

    px, src = qe._engine_mark_price("NOISE")
    assert px == pytest.approx(701.4), (
        "must resolve via NOISE_382 (the key CROWN_LEGS actually has) -- got %r "
        "(None means it resolved to the retired NOISE_304 key and found nothing there)" % (px,))
    assert src == "engine_cache"


def test_engine_key_for_leg_falls_back_when_every_mapped_key_is_retired(monkeypatch):
    """If a leg's mapped keys were EVER all retired from CROWN_LEGS at once (not today's
    case -- NOISE_382 is live -- but the fallback exists so this can never raise), the
    lookup returns the first mapped key rather than None, so callers keep degrading the
    same way they already do for a leg missing from CROWN_LEGS entirely (cfg_leg falsy ->
    "no price available"), instead of crashing."""
    class _StubCS:
        CROWN_LEGS = {}
    monkeypatch.setattr(qe, "ENGINE_LEG_MAP", {"NOISE_382": "NOISE", "NOISE_304": "NOISE"})
    assert qe._engine_key_for_leg("NOISE", _StubCS()) == "NOISE_382"
    assert qe._engine_key_for_leg("NOPE", _StubCS()) is None

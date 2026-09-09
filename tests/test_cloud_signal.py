"""Tests for api/cloud_signal.py — the SIGNAL ENGINE (no order code) that will later
feed a Webull execution adapter. See that module's docstring for the full design.

Two kinds of coverage:
  1. A synthetic 3-bar fixture (no external data) proving the diff/idempotency
     machinery emits ENTRY then EXIT for a trivially-firing stub strategy, passed in
     via cfg["strategy"] as a loaded module object (engine.run_backtest accepts that
     directly — see augur_engine/engine.py: `mod = strategy if hasattr(strategy,
     "run_backtest") else load_strategy(strategy)`).
  2. Real-cache replay tests (skipped when the owner's local QQQ bar cache isn't
     present, e.g. a fresh clone / CI) proving a replay of the newest cached session
     is deterministic across independent runs, and that replaying the same day twice
     against the SAME state store emits zero NEW events the second time.

SPEED. cloud_signal.replay() recomputes each leg's full engine backtest at every
closed 1-minute bar boundary — by design, see that function's docstring — so cost is
O(sessions-in-window) per bar. Production default is 60 sessions; these tests pass a
much smaller `warmup_sessions` so three real-cache replays (two independent + one
idempotency rerun) stay well under this file's speed budget. This does not test
strategy fidelity at full warm-up depth (regime_len etc. want more history) — it
tests the diff/idempotency mechanics, which are warm-up-depth-independent.
"""
import os
import shutil
import zoneinfo
import datetime
import tempfile
import time
import types

import pandas as pd
import pytest

import api.cloud_signal as cs

REAL_CACHE_1M = r"C:\EdgeLog\ohlc\QQQ_1m.csv"
REAL_CACHE_5M = r"C:\EdgeLog\ohlc\QQQ_5m.csv"
def _cache_state(path):
    r"""(present, empty) for one cache file -- and the two are NOT the same condition.

    2026-09-09, and this guard has now been wrong in both directions in one day. It began as
    os.path.exists alone, so when C:\EdgeLog\ohlc\QQQ_1m.csv sat at ZERO BYTES the skipif
    sailed past and both replay tests died inside pd.read_csv with "EmptyDataError: No columns
    to parse from file" -- main red for every push in the repo behind a message naming pandas
    rather than the cache. The first fix treated empty as absent and SKIPPED. That is too quiet:
    that empty file was a real outage (a runner restart caught the writer mid-write and the cache
    stayed at 0 bytes for over an hour, starving the 1-minute leg), and it surfaced ONLY because
    these tests went red.

    So the two conditions are separated. A MISSING cache is an environment fact -- a fresh clone
    or any machine that is not the owner's box has no C:\EdgeLog -- and skips. A cache that
    EXISTS BUT IS EMPTY is an anomaly: something wrote that file and produced nothing, and that
    is worth being loud about. It fails, by name, saying what it means.
    """
    try:
        return True, os.path.getsize(path) == 0
    except OSError:
        return False, False


_CACHE_STATE = {p: _cache_state(p) for p in (REAL_CACHE_1M, REAL_CACHE_5M)}
_ABSENT = [p for p, (present, _) in _CACHE_STATE.items() if not present]
_EMPTY = [p for p, (present, empty) in _CACHE_STATE.items() if present and empty]
HAS_REAL_CACHE = not _ABSENT and not _EMPTY
_CACHE_SKIP = "no local QQQ bar cache on this machine: %s" % ", ".join(_ABSENT)


def test_no_cache_file_is_present_but_empty():
    """A bar cache that exists at zero bytes is an outage, not a missing-environment skip.

    Kept deliberately loud. Both writers of these files now rename into place
    (tests/test_qqq_cache_atomic.py pins that), so a torn write should no longer produce this
    -- which makes a hit here a NEW cause worth stopping for rather than skipping past.
    """
    assert not _EMPTY, (
        "QQQ bar cache present but EMPTY: %s. Something wrote this file and produced nothing; "
        "anything replaying off it is being starved. Do not silence this -- find the writer."
        % ", ".join(_EMPTY))


TEST_WARMUP_SESSIONS = 5   # see module docstring "SPEED"
TEST_MAX_TICKS = 60        # first 60 minutes of the session only — see "SPEED"


# FROZEN SNAPSHOT (2026-09-09). These tests read the owner's live bar cache, and since the
# parallel run started that cache is REWRITTEN every 30 seconds by api/cloud_signal's runner
# thread. Copying it per test meant two "identical" runs could be seeded from two different
# files, and the determinism test duly went red on a change that had nothing to do with it.
# Snapshot the cache exactly once per test session and seed every home from that copy.
_SNAPSHOT = {}


def _snapshot_dir():
    """Copy the live cache once, VALIDATING each copy. api/cloud_signal now writes the cache
    atomically, but this file is also touched by tools/qqq_paper.py and by hand, so the read
    side stays defensive: a copy that will not parse is retried rather than trusted."""
    if not _SNAPSHOT:
        d = tempfile.mkdtemp(prefix="qqq_cache_snapshot_")
        for src in (REAL_CACHE_1M, REAL_CACHE_5M):
            dst = os.path.join(d, os.path.basename(src))
            for attempt in range(5):
                shutil.copy(src, dst)
                try:
                    if len(pd.read_csv(dst)):
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            else:
                pytest.skip(f"could not take a stable snapshot of {src}")
        _SNAPSHOT["dir"] = d
    return _SNAPSHOT["dir"]


def _seed_home(home_dir):
    paths = cs._paths(home=str(home_dir))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    src = _snapshot_dir()
    shutil.copy(os.path.join(src, "QQQ_1m.csv"), paths["ohlc_dir"])
    shutil.copy(os.path.join(src, "QQQ_5m.csv"), paths["ohlc_dir"])
    return paths


def _newest_cached_session():
    """Newest session in the snapshot, EXCLUDING today: today's bars are still arriving, so
    replaying it races the live feed and the trade list can legitimately differ between two
    runs seconds apart. A finished session is the only stable thing to assert on."""
    df = pd.read_csv(os.path.join(_snapshot_dir(), "QQQ_1m.csv"))
    idx = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(cs.TZ)
    today = datetime.datetime.now(zoneinfo.ZoneInfo(cs.TZ)).date()
    days = sorted(d for d in set(idx.dt.date) if d < today)
    if not days:
        pytest.skip("cache holds only today's still-growing session")
    return str(days[-1])


def _event_key(e):
    """Compares an event ignoring `emitted_at` (real wall-clock time the engine
    happened to run, not part of the deterministic signal itself)."""
    return (e["leg"], e["event"], e["side"], e["ref_time"], e["ref_price"], e["shares"])


# ── 1. Synthetic 3-bar fixture: ENTRY then EXIT, no external data needed ────────────────
def _stub_module():
    """A trivial strategy: if there are >= 3 closed bars, buy the open of bar 1 and
    sell the close of bar 2, every single time it is asked. Deterministic, no
    indicators, no warm-up — exists purely to exercise the diff/idempotency logic."""
    mod = types.ModuleType("cloud_signal_stub_strategy")
    mod.STRATEGY_NAME = "STUB_ALWAYS_FIRES"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        trades = []
        if len(closes) >= 3:
            entry_px = float(opens[1])
            pnl = float(closes[2] - entry_px)
            trades.append((1, 2, pnl, 1, entry_px))
        n = len(trades)
        wins = 1 if trades and trades[0][2] > 0 else 0
        return {"trades": trades if return_trades else None, "num_trades": n,
               "total_pnl": sum(t[2] for t in trades), "win_rate": wins / n if n else 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": wins,
               "losses": n - wins}

    mod.run_backtest = run_backtest
    return mod


def _fixture_epoch_df():
    """4 bars, not 3: the stub fires entry_bar=1/exit_bar=2, and run_leg_trades treats
    a trade whose exit bar is the LAST bar in the array as `still_open` (data-end
    fallback — see run_leg_trades, same convention tools/qqq_paper.py uses) rather than
    a confirmed close. Bar 3 is padding so bar 2's exit is unambiguously in the past
    once `now` is past bar 3's close, and the EXIT event actually emits."""
    tz = cs.TZ
    base = pd.Timestamp("2026-09-08 09:30:00", tz=tz)   # a real, confirmed session day
    times = [base + pd.Timedelta(minutes=i) for i in range(4)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    return pd.DataFrame({
        "time": epoch,
        "open": [699.5, 700.5, 701.5, 702.4],
        "high": [700.2, 701.2, 702.7, 702.6],
        "low": [699.0, 700.0, 701.0, 702.2],
        "close": [700.0, 701.0, 702.5, 702.5],
        "volume": [1000.0, 1000.0, 1000.0, 1000.0],
    }), base


def test_cold_start_seeds_without_emitting(tmp_path):
    """First-ever call for a leg must ABSORB the strategy's back history, not emit it.
    Without this guard the engine's rolling recompute hands a downstream executor every
    trade in the warm-up window as a fresh ENTRY the moment it boots (the same defect
    api/qqq_exec.py fixed for NinjaTrader fills in v73.459)."""
    epoch_df, base = _fixture_epoch_df()
    paths = cs._paths(home=str(tmp_path / "cold_home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)

    legs = {"STUB": {"strategy": _stub_module(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5}}
    # A cold start that ALREADY has a firing trade in its window: the stub fires as
    # soon as 3 bars are closed, so this first call discovers a complete trade.
    now = base + pd.Timedelta(minutes=6)
    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)

    assert [e["event"] for e in events] == ["SEED"], "cold start must not emit ENTRY/EXIT"
    assert "absorbed 1 historical trade" in events[0]["reason"]
    # and the absorbed trade is never re-emitted afterwards
    assert cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []


def test_synthetic_fixture_entry_then_exit(tmp_path):
    epoch_df, base = _fixture_epoch_df()
    paths = cs._paths(home=str(tmp_path / "fixture_home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)

    # This case is about the ENTRY/EXIT diff, not about lateness. The fixture has to look at
    # the bars from several minutes out so bar 2's exit is confirmed rather than a data-end
    # guess (see _fixture_epoch_df), which would trip the late-entry horizon; the horizon
    # itself has its own case above. Say that in the config rather than leaving the two
    # rules to collide silently.
    legs = {"STUB": {"strategy": _stub_module(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5, "max_entry_age_sec": 3600}}
    # SEED FIRST on an empty history (see test_cold_start_seeds_without_emitting): at
    # base+2m30s only bars 0-1 are closed, the stub needs 3, so the cold start absorbs
    # nothing and the leg is armed. Everything after this is a genuine live signal.
    seed = cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(),
                   legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    assert "absorbed 0 historical trade" in seed[0]["reason"]

    # now = well after bar 3 (09:33, the padding bar) has closed, so bar 2's exit is
    # no longer the last bar in the array (see _fixture_epoch_df's docstring) and
    # run_leg_trades reports it as a confirmed close, not a still-open data-end guess.
    now = base + pd.Timedelta(minutes=6)

    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)

    assert len(events) == 2
    assert events[0]["event"] == "ENTRY"
    assert events[0]["leg"] == "STUB"
    assert events[0]["side"] == "long"
    assert events[0]["ref_price"] == pytest.approx(700.5)
    assert events[1]["event"] == "EXIT"
    assert events[1]["leg"] == "STUB"
    assert events[1]["ref_price"] == pytest.approx(702.5)

    # idempotent: same `now`, same state store -> nothing new
    events2 = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)
    assert events2 == []


def test_stale_entry_is_recorded_but_not_emitted(tmp_path):
    """A trade whose entry is not in TODAY's session must never emit an ENTRY. The
    rolling warm-up window is not identity-stable at its left edge, so weeks-old trades
    can re-appear as "new" (a real 2026-09-04 replay emitted 2026-07-01 entries); an
    old entry is unactionable at today's price either way."""
    epoch_df, base = _fixture_epoch_df()          # all bars are 2026-09-08
    paths = cs._paths(home=str(tmp_path / "stale_home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)

    legs = {"STUB": {"strategy": _stub_module(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5}}
    # arm the leg on an empty history so the next call is a genuine live diff
    cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(),
            legs=legs, paths=paths, fetch=False)

    # ...then look at it from the NEXT session: the stub's trade still sits in the
    # window, but its entry is yesterday's.
    next_day = base + pd.Timedelta(days=1)
    assert cs.step(now=next_day.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []
    state = cs._load_state(paths)
    assert state["legs"]["STUB"]["stale_skipped"] == 1


def test_hours_late_entry_is_recorded_but_not_emitted(tmp_path):
    """Seen live on 2026-09-09: after the 12:44 runner restart the engine re-derived the day
    and emitted an ENGU-Q ENTRY stamped 10:07 -- two and a half hours old, but still "today",
    so the date test let it through. An executor cannot take a 10:07 price at 12:44. A bar or
    so late is normal; hours late means a gap, and the trade is gone."""
    epoch_df, base = _fixture_epoch_df()          # bars at 09:30..09:33
    paths = cs._paths(home=str(tmp_path / "late_home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)

    legs = {"STUB": {"strategy": _stub_module(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5}}
    # arm the leg on an empty history so the next call is a genuine live diff
    cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(),
            legs=legs, paths=paths, fetch=False)

    # look at it 3 HOURS later, same session: the stub's entry bar is long gone
    late = base + pd.Timedelta(hours=3)
    assert cs.step(now=late.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []
    state = cs._load_state(paths)
    assert state["legs"]["STUB"]["late_skipped"] == 1
    assert state["legs"]["STUB"].get("stale_skipped", 0) == 0,         "same-day but hours old is LATE, not stale -- the two are counted apart"


# ── 2. Real-cache replay: determinism + idempotency ─────────────────────────────────────
@pytest.mark.skipif(not HAS_REAL_CACHE, reason=_CACHE_SKIP)
def test_replay_deterministic_across_independent_runs(tmp_path):
    day = _newest_cached_session()
    paths_a = _seed_home(tmp_path / "run_a")
    paths_b = _seed_home(tmp_path / "run_b")

    events_a = cs.replay(day, paths=paths_a, warmup_sessions=TEST_WARMUP_SESSIONS,
                         max_ticks=TEST_MAX_TICKS)
    events_b = cs.replay(day, paths=paths_b, warmup_sessions=TEST_WARMUP_SESSIONS,
                         max_ticks=TEST_MAX_TICKS)

    assert [_event_key(e) for e in events_a] == [_event_key(e) for e in events_b]


@pytest.mark.skipif(not HAS_REAL_CACHE, reason=_CACHE_SKIP)
def test_replay_same_day_twice_is_idempotent(tmp_path):
    day = _newest_cached_session()
    paths = _seed_home(tmp_path / "run")

    first = cs.replay(day, paths=paths, warmup_sessions=TEST_WARMUP_SESSIONS,
                      max_ticks=TEST_MAX_TICKS)
    second = cs.replay(day, paths=paths, warmup_sessions=TEST_WARMUP_SESSIONS,
                       max_ticks=TEST_MAX_TICKS)

    assert second == []
    # sanity: the ledger persisted to disk across the two calls
    assert os.path.exists(paths["state_path"])
    with open(paths["state_path"]) as f:
        import json
        state = json.load(f)
    assert set(state["legs"].keys()) == set(cs.CROWN_LEGS.keys())
    del first  # only used to keep the variable name self-documenting above

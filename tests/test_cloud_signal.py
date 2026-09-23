"""Tests for api/cloud_signal.py — the SIGNAL ENGINE (no order code) that will later
feed a Webull execution adapter. See that module's docstring for the full design.

Three kinds of coverage:
  1. A synthetic 3-bar fixture (no external data) proving the diff/idempotency
     machinery emits ENTRY then EXIT for a trivially-firing stub strategy, passed in
     via cfg["strategy"] as a loaded module object (engine.run_backtest accepts that
     directly — see augur_engine/engine.py: `mod = strategy if hasattr(strategy,
     "run_backtest") else load_strategy(strategy)`).
  2. Real-cache replay tests (skipped when the owner's local QQQ bar cache isn't
     present, e.g. a fresh clone / CI) proving a replay of the newest cached session
     is deterministic across independent runs, and that replaying the same day twice
     against the SAME state store emits zero NEW events the second time.
  3. Isolation: a replay that names no store -- library call or CLI -- never writes the
     live ledger/state, and targeting them takes an explicit --live-paths that is refused
     while a live writer is ticking (the 2026-09-14 contamination, see
     cloud_signal.isolated_paths).

SPEED. cloud_signal.replay() recomputes each leg's full engine backtest at every
closed 1-minute bar boundary — by design, see that function's docstring — so cost is
O(sessions-in-window) per bar. Production default is 60 sessions; these tests pass a
much smaller `warmup_sessions` so three real-cache replays (two independent + one
idempotency rerun) stay well under this file's speed budget. This does not test
strategy fidelity at full warm-up depth (regime_len etc. want more history) — it
tests the diff/idempotency mechanics, which are warm-up-depth-independent.
"""
import csv
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
    runs seconds apart. A finished session is the only stable thing to assert on.

    MALFORMED ROWS ARE SKIPPED, NOT FATAL (2026-09-20): the live cache is appended by more
    than one writer, and a torn write leaves a row whose `time` is not an epoch second at
    all (seen for real: 812 and 99877929688 in QQQ_1m.csv, 2026-09-18). pd.to_datetime then
    raises OutOfBoundsDatetime and every test in this file fails -- which blocks the push
    gate for changes nowhere near this module. A local data defect must not read as a code
    defect, so rows outside a sane epoch range are dropped here."""
    df = pd.read_csv(os.path.join(_snapshot_dir(), "QQQ_1m.csv"))
    secs = pd.to_numeric(df["time"], errors="coerce")
    secs = secs[(secs >= 1.0e9) & (secs <= 2.0e9)]
    if secs.empty:
        pytest.skip("cache holds no row with a usable epoch-second timestamp")
    idx = pd.to_datetime(secs, unit="s", utc=True).dt.tz_convert(cs.TZ)
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


# ── 1b. Trade id: one identity per trade, on BOTH of its rows (2026-09-14) ──────────────
# tools/qqq_failover_sim.py scenario F: EXIT rows carried no entry identity (ref_time is the
# exit bar), so api/qqq_exec.py closed whatever lot was open on the leg -- and the live ledger
# delivered the EXIT of a 2026-09-03 trade at 09:31 ET on 2026-09-14.
def test_trade_id_is_price_free_and_host_independent():
    from api import trade_id as T
    ny = zoneinfo.ZoneInfo("America/New_York")
    tid = T.make("NOISE_304", "2026-09-03T11:00:00-04:00", "long")
    assert tid == "NOISE_304-20260903T150000Z-L"
    # the same instant from a host whose bar index is UTC, or a pandas Timestamp
    assert T.make("NOISE_304", "2026-09-03T15:00:00+00:00", "long") == tid
    assert T.make("NOISE_304", "2026-09-03T15:00:00Z", "long") == tid
    assert T.make("NOISE_304", pd.Timestamp("2026-09-03 11:00", tz=cs.TZ), "long") == tid
    # a naive time only counts when the caller names its zone
    assert T.make("NOISE_304", "2026-09-03 11:00:00", "long") is None
    assert T.make("NOISE_304", "2026-09-03 11:00:00", "long", default_tz=ny) == tid
    # side is part of the identity; a malformed part gives NO id, never a different one
    assert T.make("NOISE_304", "2026-09-03T11:00:00-04:00", "short") == "NOISE_304-20260903T150000Z-S"
    assert T.make("NOISE 304", "2026-09-03T11:00:00-04:00", "long") is None
    assert T.make("NOISE_304", "not a time", "long") is None
    assert T.make("NOISE_304", "2026-09-03T11:00:00-04:00", "flat") is None
    for leg in cs.CROWN_LEGS:
        assert T.is_valid(T.make(leg, "2026-09-03T11:00:00-04:00", "long")), leg
    assert T.parse(tid)["side"] == "long" and T.parse("NOISE_304|junk") is None
    assert T.describe(tid, ny) == "NOISE_304 long entered 2026-09-03 11:00 ET"


def _stub_home(tmp_path, name, epoch_df):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    return paths


def _stub_legs():
    # max_entry_age_sec: these cases look from a few minutes out (see the synthetic fixture
    # test above); lateness has its own case.
    return {"STUB": {"strategy": _stub_module(), "timeframe": "1m", "params": {},
                     "warmup_sessions": 5, "max_entry_age_sec": 3600}}


def test_entry_and_exit_rows_carry_the_same_trade_id(tmp_path):
    import csv
    from api import trade_id as T
    epoch_df, base = _fixture_epoch_df()
    paths = _stub_home(tmp_path, "tid_home", epoch_df)
    legs = _stub_legs()
    cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(), legs=legs,
            paths=paths, fetch=False)
    entry, exit_ = cs.step(now=(base + pd.Timedelta(minutes=6)).to_pydatetime(), legs=legs,
                           paths=paths, fetch=False)
    want = T.make("STUB", base + pd.Timedelta(minutes=1), "long")   # the stub enters on bar 1
    assert (entry["event"], exit_["event"]) == ("ENTRY", "EXIT")
    assert entry["trade_id"] == exit_["trade_id"] == want, \
        "the EXIT row must name the trade it closes -- the ENTRY's id, not one built from the exit bar"

    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        header = f.readline().strip().split(",")
        f.seek(0)
        rows = list(csv.DictReader(f))
    assert header == cs.SIGNAL_COLS and header[-1] == "keel_size"
    assert [r["event"] for r in rows] == ["SEED", "ENTRY", "EXIT"]
    assert rows[0]["trade_id"] == "" and rows[1]["trade_id"] == rows[2]["trade_id"] == want


def test_repriced_entry_keeps_its_id_and_still_exits_exactly_once(tmp_path):
    """The Webull and yfinance bars for one minute can disagree by a cent, and the cache keeps
    whichever wrote last. With the entry PRICE in the key, the re-priced trade looked new: a
    second ENTRY, and the original's EXIT never came. Keyed by trade id it is one trade."""
    epoch_df, base = _fixture_epoch_df()
    paths = _stub_home(tmp_path, "reprice_home", epoch_df)
    legs = _stub_legs()
    cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(), legs=legs,
            paths=paths, fetch=False)
    # bars 0-2 closed: the stub's trade is in, its exit bar is still the last bar -> open
    first = cs.step(now=(base + pd.Timedelta(minutes=3, seconds=10)).to_pydatetime(), legs=legs,
                    paths=paths, fetch=False)
    assert [e["event"] for e in first] == ["ENTRY"]

    epoch_df.loc[1, "open"] = 700.51          # the other source's print for the entry bar
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    second = cs.step(now=(base + pd.Timedelta(minutes=6)).to_pydatetime(), legs=legs,
                     paths=paths, fetch=False)
    assert [e["event"] for e in second] == ["EXIT"], \
        "a re-priced entry must not enter again, and the trade's own EXIT must still be emitted"
    assert second[0]["trade_id"] == first[0]["trade_id"]


def test_pre_upgrade_price_keyed_memory_is_rekeyed_and_open_trade_still_exits(tmp_path):
    """state.json written before trade ids holds price-bearing keys. Without the one-time
    re-key, a trade open across the upgrade would look new, be recorded LATE with its exit
    marked done, and its real EXIT would never be emitted."""
    epoch_df, base = _fixture_epoch_df()
    paths = _stub_home(tmp_path, "upgrade_home", epoch_df)
    legs = _stub_legs()
    cs.step(now=(base + pd.Timedelta(minutes=2, seconds=30)).to_pydatetime(), legs=legs,
            paths=paths, fetch=False)
    assert [e["event"] for e in cs.step(now=(base + pd.Timedelta(minutes=3, seconds=10)).to_pydatetime(),
                                        legs=legs, paths=paths, fetch=False)] == ["ENTRY"]

    # rewrite the memory exactly as the old code left it: price-bearing keys, no key_format,
    # plus the skipped cent-off twin a bar-source flip used to leave beside the real record
    state = cs._load_state(paths)
    leg = state["legs"]["STUB"]
    (rec,) = leg["trades"].values()
    twin = dict(rec, entry_px=round(rec["entry_px"] + 0.01, 4), exit_emitted=True, skipped="late")
    leg["trades"] = {cs._legacy_entry_key("STUB", r): r for r in (rec, twin)}
    leg.pop("key_format", None)
    cs._write_state(state, paths)

    events = cs.step(now=(base + pd.Timedelta(minutes=6)).to_pydatetime(), legs=legs,
                     paths=paths, fetch=False)
    assert [e["event"] for e in events] == ["EXIT"]
    leg = cs._load_state(paths)["legs"]["STUB"]
    assert list(leg["trades"]) == [events[0]["trade_id"]], "the twin merges into the one trade id"
    assert leg["key_format"] == cs.TRADE_KEY_FORMAT
    assert cs._rekey_recorded_trades("STUB", leg) == 0, "the re-key runs once"


def _old_ledger(paths):
    import csv
    # two columns behind current SIGNAL_COLS -- a ledger from before EITHER "size" or
    # "keel_size" existed (the trade_id migration this helper feeds is about the column
    # before both of them; test_cloud_signal_trade_size.py's own
    # test_signals_csv_size_column_migrates_cleanly and this file's
    # test_keel_size_column_migrates_cleanly cover the two newer columns in isolation).
    old_cols = cs.SIGNAL_COLS[:-2]
    assert old_cols == ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares",
                        "reason", "bar_source", "trade_id"], \
        "size/keel_size must be APPENDED at the end, never inserted"
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old_cols)
        w.writeheader()
        w.writerow({"emitted_at": "2026-09-14T09:31:00-04:00", "leg": "NOISE_304", "event": "EXIT",
                    "side": "long", "ref_time": "2026-09-03T15:55:00-04:00", "ref_price": "717.61",
                    "shares": "140", "reason": "strategy_exit", "bar_source": "webull"})


def _read_ledger(paths):
    import csv
    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        header = f.readline().strip()
        f.seek(0)
        return header, list(csv.DictReader(f))


def test_old_ledger_gains_trade_id_column_rows_kept(tmp_path):
    paths = cs._paths(home=str(tmp_path / "hdr_home"))
    _old_ledger(paths)
    tid = "ORB_R6-20260914T140500Z-L"
    cs._append_signals([{"emitted_at": "2026-09-14T10:06:00-04:00", "leg": "ORB_R6", "event": "ENTRY",
                         "side": "long", "ref_time": "2026-09-14T10:05:00-04:00", "ref_price": 700.0,
                         "shares": 140, "reason": "", "bar_source": "webull", "trade_id": tid}], paths)
    header, rows = _read_ledger(paths)
    assert header == ",".join(cs.SIGNAL_COLS)
    assert [r["leg"] for r in rows] == ["NOISE_304", "ORB_R6"], "old rows are kept, in order"
    assert rows[0]["trade_id"] == "" and rows[0]["ref_price"] == "717.61"
    assert rows[1]["trade_id"] == tid
    assert not [n for n in os.listdir(paths["state_dir"]) if n.endswith(".tmp")]


def test_header_upgrade_that_cannot_swap_in_leaves_the_ledger_untouched(tmp_path, monkeypatch):
    """api/qqq_exec.py reads signals.csv every 5 s and Windows refuses a rename over a file a
    reader holds open. The upgrade must then leave the file exactly as it was -- never
    rewrite it in place, which is how a reader got a torn, short ledger -- and the rows
    appended meanwhile must still line up with the header that is on disk."""
    import csv
    paths = cs._paths(home=str(tmp_path / "held_home"))
    _old_ledger(paths)
    with open(paths["signals_path"], "rb") as f:
        before = f.read()

    def refused(src, dst):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(cs.os, "replace", refused)
    cs._migrate_signals_header(paths["signals_path"], cs.SIGNAL_COLS, _retries=2, _sleep=0.0)
    with open(paths["signals_path"], "rb") as f:
        assert f.read() == before, "a failed swap must not touch the ledger"
    assert not [n for n in os.listdir(paths["state_dir"]) if n.endswith(".tmp")]

    cs._append_signals([{"emitted_at": "2026-09-14T10:06:00-04:00", "leg": "ORB_R6", "event": "ENTRY",
                         "side": "long", "ref_time": "2026-09-14T10:05:00-04:00", "ref_price": 700.0,
                         "shares": 140, "reason": "", "bar_source": "webull",
                         "trade_id": "ORB_R6-20260914T140500Z-L"}], paths)
    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        raw = list(csv.reader(f))
    assert raw[0] == cs.SIGNAL_COLS[:-2] and all(len(r) == len(raw[0]) for r in raw), \
        "rows appended under the old header must stay aligned with it"
    assert raw[2][1:3] == ["ORB_R6", "ENTRY"]

    monkeypatch.undo()
    cs._migrate_signals_header(paths["signals_path"], cs.SIGNAL_COLS)
    header, rows = _read_ledger(paths)
    assert header == ",".join(cs.SIGNAL_COLS) and [r["leg"] for r in rows] == ["NOISE_304", "ORB_R6"]


def test_a_longer_header_from_a_newer_writer_is_never_rewritten(tmp_path):
    """The pre-2026-09-14 copy of the migration rewrote ANY differing header under its own
    columns, deleting trade_id from every row whenever an old checkout appended. This one
    only ever extends a strict prefix; a header it does not fully know is left alone and
    appended to in its own column order."""
    import csv
    paths = cs._paths(home=str(tmp_path / "newer_home"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    newer = cs.SIGNAL_COLS + ["future_col"]
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=newer)
        w.writeheader()
        w.writerow(dict({c: "" for c in newer}, leg="NOISE_304", event="EXIT",
                        trade_id="NOISE_304-20260903T150000Z-L", future_col="kept"))
    tid = "ORB_R6-20260914T140500Z-L"
    cs._append_signals([{"emitted_at": "2026-09-14T10:06:00-04:00", "leg": "ORB_R6", "event": "ENTRY",
                         "side": "long", "ref_time": "2026-09-14T10:05:00-04:00", "ref_price": 700.0,
                         "shares": 140, "reason": "", "bar_source": "webull", "trade_id": tid}], paths)
    header, rows = _read_ledger(paths)
    assert header == ",".join(newer)
    assert rows[0]["future_col"] == "kept" and rows[0]["trade_id"] == "NOISE_304-20260903T150000Z-L"
    assert rows[1]["trade_id"] == tid and rows[1]["future_col"] == ""


def test_runner_thread_upgrades_the_ledger_header_at_start(tmp_path, monkeypatch):
    """At boot, not at the first emitted signal -- which is always mid-session, with the
    shadow adapter reading the file."""
    import threading
    paths = cs._paths(home=str(tmp_path / "boot_home"))
    _old_ledger(paths)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    stop = threading.Event()
    stop.set()                               # boot, then leave the loop straight away
    cs.cloud_signal_thread(stop=stop, log=lambda *a, **k: None)
    header, rows = _read_ledger(paths)
    assert header == ",".join(cs.SIGNAL_COLS) and len(rows) == 1


def _synthetic_calendar_epoch_df(n_sessions=90, bars_per_session=3):
    """`n_sessions` consecutive BUSINESS days (pandas bdate_range — no holiday calendar,
    weekends only), `bars_per_session` 5-minute RTH bars each, starting 09:30 ET. Enough
    calendar span (90 business days ~= 126 calendar days) to expose the closed_arrays()
    buffer bug at the production warmup_sessions=60: the old `warmup_sessions + 5` = 65
    calendar day buffer holds far fewer than 60 of these business days, while 60 real
    trading sessions actually need ~84 calendar days. Bar COUNT per session is
    irrelevant to this test (it only inspects closed_arrays' day/session bookkeeping,
    never runs a strategy), so it is kept tiny for speed."""
    days = pd.bdate_range("2026-01-05", periods=n_sessions, tz="US/Eastern")
    rows = []
    for d in days:
        base = d.normalize() + pd.Timedelta(hours=9, minutes=30)
        for i in range(bars_per_session):
            t = base + pd.Timedelta(minutes=5 * i)
            rows.append({"time": int(t.tz_convert("UTC").timestamp()),
                        "open": 700.0, "high": 700.5, "low": 699.5, "close": 700.0,
                        "volume": 1000.0})
    return pd.DataFrame(rows), days[-1]


def test_closed_arrays_window_is_stable_within_one_session():
    """REGRESSION (found 2026-09-13 diagnosing "ORB never fires on QQQ"): closed_arrays()'s
    raw calendar prefilter used to be `warmup_sessions + 5` calendar days -- "generous" for
    weekends/holidays in the comment, but 60 TRADING sessions actually span ~84 calendar
    days (5/7 cadence), not 65. The undersized buffer silently fed the trailing-N-session
    filters fewer sessions than warmup_sessions asks for, and because `cutoff`/`lower_bound`
    both advance continuously with `now`, the oldest session can age out of that too-tight
    buffer PARTWAY THROUGH the very session being evaluated -- shifting every later
    session's index into the trailing reference by one, at whatever wall-clock minute the
    engine happens to be asked. Reproduced live: an ORB_3_6_R6.py entry on 2026-09-04 was
    absent from the engine's trade list at every tick through 14:05 and present from 14:06
    on, with no new bar of any kind involved -- purely the buffer dropping an old session.
    That entry aged past `max_entry_age_sec` and was silently suppressed as "late"; a
    smaller shift could instead emit a spurious ENTRY that only exists because of when the
    engine was asked. This test pins the invariant directly: for one FIXED calendar day,
    the window closed_arrays() returns must not change shape between an early-session and
    a late-session query."""
    epoch_df, target_day = _synthetic_calendar_epoch_df()
    early = target_day.normalize() + pd.Timedelta(hours=9, minutes=50)
    late = target_day.normalize() + pd.Timedelta(hours=15, minutes=55)

    a = cs.closed_arrays(epoch_df, early.to_pydatetime(), "5m", 60)
    b = cs.closed_arrays(epoch_df, late.to_pydatetime(), "5m", 60)
    assert a is not None and b is not None

    sessions_a = len(set(a["day_id"].tolist()))
    sessions_b = len(set(b["day_id"].tolist()))
    assert sessions_a == sessions_b == 60, (
        f"session count drifted within the same trading day: early={sessions_a} "
        f"late={sessions_b} (want 60/60) -- the calendar buffer is too tight and is "
        f"aging sessions out mid-day")
    assert a["index"][0] == b["index"][0], (
        "the window's oldest bar shifted within the same trading day purely because of "
        "wall-clock time -- a trailing-N-session filter must see the SAME N sessions "
        "all day, not fewer as the afternoon wears on")


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


# ── 3. Isolation: an offline run never writes the live ledger ───────────────────────────
FIXTURE_DAY = "2026-09-08"   # the day _fixture_epoch_df's bars sit on


def _tree_bytes(root):
    """{relative path: bytes} for every file under `root` -- equal before and after means
    nothing was written, appended, created or deleted there."""
    out = {}
    for d, _, names in os.walk(root):
        for name in names:
            p = os.path.join(d, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def _stamp_heartbeat(paths, age_sec):
    ts = datetime.datetime.now(zoneinfo.ZoneInfo(cs.TZ)) - datetime.timedelta(seconds=age_sec)
    with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
        f.write('{"ts": "%s", "ok": true, "note": "test"}' % ts.isoformat())


@pytest.fixture
def fake_live(tmp_path, monkeypatch):
    """A stand-in for the owner's live EDGELOG_HOME, and the reason these tests can never
    touch the real one: module-level DEFAULT_PATHS points at a tmp home holding the fixture
    bar cache and the ledger/state an ARMED parallel run leaves behind (leg already seeded,
    one SEED row). The crown legs are swapped for the stub, and the temp root isolated
    copies are made under is moved inside tmp_path so the test can see them."""
    epoch_df, _ = _fixture_epoch_df()
    live = cs._paths(home=str(tmp_path / "live_home"))
    os.makedirs(live["ohlc_dir"])
    epoch_df.to_csv(cs._cache_path("1m", live), index=False)
    cs._write_state({"legs": {"STUB": {"trades": {}, "seeded": True}},
                     "generated_at": "2026-09-08T09:00:00-04:00"}, live)
    cs._append_signals([{"emitted_at": "2026-09-08T09:00:00-04:00", "leg": "STUB",
                         "event": "SEED", "reason": "the live run's own seed"}], live)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    monkeypatch.setattr(cs, "CROWN_LEGS", {"STUB": {
        "strategy": _stub_module(), "timeframe": "1m", "params": {}, "warmup_sessions": 5,
        # about isolation, not lateness -- see test_synthetic_fixture_entry_then_exit
        "max_entry_age_sec": 3600}})
    # the CLI prints NinjaTrader's fills beside the replay; this suite has no fills file
    monkeypatch.setattr(cs, "nt_comparison", lambda day, fills_path=None: [])
    scratch_root = tmp_path / "temp_root"
    scratch_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch_root))
    return live, scratch_root


def test_default_replay_leaves_live_paths_untouched(fake_live):
    """REGRESSION (2026-09-14): `python -m api.cloud_signal --replay 2026-09-03` ran
    replay(day) -> step(paths=None) -> DEFAULT_PATHS and wrote a NOISE_304 SEED plus
    2026-09-03 ENTRY/EXIT rows into the LIVE ledger at 00:55 ET; the live engine then
    emitted that trade's EXIT at 09:31 and the QQQ shadow adapter consumed it. A replay
    that names no store must run on a copy and leave every live file byte-for-byte alone."""
    live, scratch_root = fake_live
    before = _tree_bytes(live["home"])

    events = cs.replay(FIXTURE_DAY, max_ticks=10)

    assert [e["event"] for e in events] == ["SEED", "ENTRY", "EXIT"], (
        "the replay must run COLD on a copy of the bar cache -- replaying into the live "
        "store would have skipped the SEED, because the live leg is already armed")
    assert _tree_bytes(live["home"]) == before, "a default replay wrote into the live paths"
    assert os.listdir(scratch_root) == [], "replay() must remove the copy it made for itself"


def _short_cli_sessions(monkeypatch):
    """The CLI replays all ~390 minutes (~6 s against the stub); the stub's trade is over by
    09:35. Caps the ticks only -- which store the CLI picks is still cmd_replay's own call."""
    real_replay = cs.replay
    monkeypatch.setattr(cs, "replay", lambda day, **kw: real_replay(day, max_ticks=10, **kw))


def test_cli_replay_runs_in_a_kept_isolated_copy(fake_live, monkeypatch, capsys):
    """The CLI is the entry point that actually did it. By default it replays into an
    isolated copy it KEEPS and names, so the replay's own ledger can still be read."""
    live, scratch_root = fake_live
    _short_cli_sessions(monkeypatch)
    before = _tree_bytes(live["home"])

    cs.main(["--replay", FIXTURE_DAY])

    assert _tree_bytes(live["home"]) == before, "the CLI replay wrote into the live paths"
    (copy_name,) = os.listdir(scratch_root)
    kept = cs._paths(home=str(scratch_root / copy_name))
    with open(kept["signals_path"], encoding="utf-8", newline="") as f:
        assert [r["event"] for r in csv.DictReader(f)] == ["SEED", "ENTRY", "EXIT"]
    assert copy_name in capsys.readouterr().out, "the CLI must say where the copy is"


def test_cli_live_paths_is_an_explicit_opt_in_refused_while_a_writer_ticks(fake_live, monkeypatch):
    live, scratch_root = fake_live
    _short_cli_sessions(monkeypatch)
    _stamp_heartbeat(live, age_sec=20)            # the runner thread is alive
    before = _tree_bytes(live["home"])

    with pytest.raises(SystemExit) as refused:
        cs.main(["--replay", FIXTURE_DAY, "--live-paths"])
    assert refused.value.code == 2
    assert _tree_bytes(live["home"]) == before, "a refused --live-paths must write nothing"

    _stamp_heartbeat(live, age_sec=cs.LIVE_WRITER_FRESH_SEC + 60)   # ...and now it is stopped
    cs.main(["--replay", FIXTURE_DAY, "--live-paths"])

    with open(live["signals_path"], encoding="utf-8", newline="") as f:
        rows = [r["event"] for r in csv.DictReader(f)]
    assert rows == ["SEED", "ENTRY", "EXIT"], (
        "opted in with no live writer, the replay appends to the LIVE ledger -- after the "
        "live run's own SEED, with no second SEED because it reuses the live state")
    assert os.listdir(scratch_root) == [], "--live-paths must not make a copy"


def test_offline_step_without_paths_refuses(fake_live):
    live, _ = fake_live
    before = _tree_bytes(live["home"])
    _, base = _fixture_epoch_df()
    with pytest.raises(ValueError, match="explicit `paths`"):
        cs.step(now=(base + pd.Timedelta(minutes=6)).to_pydatetime(), fetch=False)
    assert _tree_bytes(live["home"]) == before


# ── 4. Rename retry / graceful cache-write degradation (2026-09-14) ─────────────────────
# `fetch_and_merge`'s os.replace() used to be a single unretried call: a reader briefly
# holding C:\EdgeLog\ohlc\QQQ_1m.csv/QQQ_5m.csv open (this file's OWN _snapshot_dir(), a
# replay, tools/qqq_paper.py's independent sync of the same files) made Windows raise
# PermissionError [WinError 32] outright, which aborted the whole step() call and made
# cloud_signal_thread write heartbeat ok=false -- which api/qqq_exec.py's engine-mode feed
# check reads as a stale feed, blocking new Webull paper entries over a few-millisecond
# lock, not a real outage. See qp._replace_with_retry (tools/qqq_paper.py) for the shared
# retry helper's own unit tests (transient-succeeds / persistent-cleans-up-and-logs-once).
def _fake_fresh_bars():
    """A tiny, deterministic stand-in for _fetch_webull's return shape -- avoids the real
    Webull SDK / keys file / network entirely."""
    return pd.DataFrame({
        "time": [1_757_847_000, 1_757_847_060, 1_757_847_120],
        "open": [700.0, 700.5, 701.0],
        "high": [700.5, 701.0, 701.5],
        "low": [699.5, 700.0, 700.5],
        "close": [700.2, 700.8, 701.2],
        "volume": [1000.0, 1000.0, 1000.0],
    })


def test_fetch_and_merge_returns_bars_and_cache_ok_false_on_persistent_lock(tmp_path, monkeypatch):
    """The freshly fetched bars are already merged in memory before the rename is even
    attempted, so a persistently locked replace must still hand them back -- never raise
    -- with only `cache_ok` going False. The abandoned .tmp must not linger, and no cache
    file must appear where none existed before (the replace never actually landed)."""
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    monkeypatch.setattr(cs, "_fetch_webull", lambda timeframe, log=print: _fake_fresh_bars())
    monkeypatch.setattr(cs.qp.time, "sleep", lambda s: None)   # instant retries
    monkeypatch.setattr(cs.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(PermissionError(32, "locked")))

    logged = []
    merged, source, cache_ok = cs.fetch_and_merge("1m", paths, log=logged.append)

    assert source == "webull"
    assert cache_ok is False
    assert len(merged) == 3, "the in-memory merge must still happen even though the write failed"
    assert not os.path.exists(cs._cache_path("1m", paths)), (
        "a persistently failed replace must never land -- no cache file where none existed")
    assert not [n for n in os.listdir(paths["ohlc_dir"]) if n.endswith(".tmp")], (
        "the abandoned .tmp bar cache must be cleaned up, not left on disk forever")
    assert any("1m bar cache" in m for m in logged), "the failure must be logged"


def test_step_reports_cache_write_failed_in_warnings_without_raising(tmp_path, monkeypatch):
    """step() must not raise when a leg's cache rename is persistently locked, and must
    still evaluate that leg's signals off the bars fetch_and_merge already had in memory
    -- `warnings['cache_write_failed']` is how it tells the caller, instead of the caller
    only finding out via an exception (the old behaviour this fix removes)."""
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df, base = _fixture_epoch_df()

    def fake_fetch_and_merge(tf, p, log=print):
        return epoch_df, "webull", False        # cache write persistently failed

    monkeypatch.setattr(cs, "fetch_and_merge", fake_fetch_and_merge)
    legs = _stub_legs()
    warnings = {}
    now = base + pd.Timedelta(minutes=6)
    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=True, warnings=warnings)

    assert warnings.get("cache_write_failed") is True
    # first-ever call for this leg/store -- a cold start, so signals are still evaluated
    # (the engine runs, discovers the trade) but absorbed as SEED rather than emitted;
    # see test_cold_start_seeds_without_emitting. The point here is only that step() ran
    # the engine at all off the in-memory bars instead of raising.
    assert [e["event"] for e in events] == ["SEED"], (
        "signals must still be evaluated off the in-memory bars despite the cache-write failure")
    assert "absorbed 1 historical trade" in events[0]["reason"]


def test_step_warnings_untouched_when_no_caller_asks(tmp_path, monkeypatch):
    """warnings=None (every pre-2026-09-14 caller) must keep working -- step() only ever
    writes into a dict it was actually handed, never assumes one exists."""
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df, base = _fixture_epoch_df()
    monkeypatch.setattr(cs, "fetch_and_merge", lambda tf, p, log=print: (epoch_df, "webull", False))
    events = cs.step(now=(base + pd.Timedelta(minutes=6)).to_pydatetime(), legs=_stub_legs(),
                     paths=paths, fetch=True)   # no warnings= at all
    assert [e["event"] for e in events] == ["SEED"]


def test_cloud_signal_thread_writes_ok_true_heartbeat_with_cache_write_failed_note(
        fake_live, monkeypatch):
    """END TO END. Before this fix, a persistently locked OHLC-cache rename raised out of
    fetch_and_merge, step() never reached _write_state/_append_signals, and this thread's
    except-branch wrote heartbeat ok=false -- which api/qqq_exec.py's `_check_feed_engine`
    reads as a stale feed and blocks new Webull paper entries. Only the bar-cache rename
    is blocked here (by destination basename); state.json and heartbeat.json rename
    normally, so a real heartbeat is written and can be read back."""
    import threading
    live, _ = fake_live

    monkeypatch.setattr(cs, "_fetch_webull", lambda timeframe, log=print: _fake_fresh_bars())
    monkeypatch.setattr(cs.market_calendar, "is_session", lambda d: True)
    monkeypatch.setattr(cs, "RTH_OPEN", cs._dt.time(0, 0))
    monkeypatch.setattr(cs, "RTH_CLOSE", cs._dt.time(23, 59))

    real_replace = cs.os.replace
    stop = threading.Event()

    def replace_blocks_only_the_bar_cache(src, dst):
        if os.path.basename(str(dst)) == "QQQ_1m.csv":
            raise PermissionError(32, "The process cannot access the file")
        return real_replace(src, dst)

    def instant_sleep_unless_the_threads_own_end_of_loop_wait(seconds):
        # the retry helper's own backoff (small, called many times) must be instant for
        # the test to run fast; the thread's OWN end-of-loop sleep (30s/60s) is the
        # signal that one full iteration just finished -- stop there instead of sleeping.
        if seconds >= 1:
            stop.set()

    monkeypatch.setattr(cs.os, "replace", replace_blocks_only_the_bar_cache)
    monkeypatch.setattr(cs.qp.time, "sleep", instant_sleep_unless_the_threads_own_end_of_loop_wait)

    cs.cloud_signal_thread(stop=stop, log=lambda *a, **k: None)

    import json as _json
    with open(live["heartbeat_path"], encoding="utf-8") as f:
        hb = _json.load(f)
    assert hb["ok"] is True, "a cache-write failure alone must not flip the heartbeat to ok=false"
    assert hb.get("cache_write_failed") is True
    assert not [n for n in os.listdir(live["ohlc_dir"]) if n.endswith(".tmp")], (
        "the abandoned bar-cache .tmp must not be left behind")

"""tests/test_qqq_reprice.py -- WEBULL_PAPER_TODO.md item 11.

tools/qqq_reprice.py used to price every trade from yfinance 1-minute bars only. It now
prefers, in order: (a) api/webull_stream.py's own live-feed bar cache
(<EDGELOG_HOME>/ohlc_stream/QQQ_1m.csv -- the actual tape the order traded on), (b)
Webull's own REST 1-minute history (get_history_bar, read-only, key-gated), (c)
yfinance, exactly as before, as the last resort. These tests pin: the preference order,
that a higher-preference source fully covering a trade means NO lower-preference source
is ever even called, the fallback chain when the stream is missing/partial/stale, the
old reprice.csv header migrating forward for free, and that none of this ever reaches a
real network.

NETWORK SAFETY (read this before adding a test). This box has REAL, valid Webull
credentials configured at the production path (C:\\EdgeLog\\webull_keys.json) for the
owner's live paper-trading system -- confirmed while writing this file, the hard way: an
early draft of tools/qqq_reprice.py's own --selftest called run() without overriding
webull_keys_path, defaulted to that real file, and made one genuine (read-only,
get_history_bar, no order of any kind) call to Webull before the bug was caught and
fixed. tests/conftest.py's autouse live_system_guard blocks any socket connect to a
"webull"-named host and fails the test that attempted it -- a real second line of
defense -- but EVERY test below still passes an explicit webull_keys_path that
provably does not exist (never the default/None, which resolves to that real file), so
no test here ever depends on the guard to stay safe. Same discipline for the stream
cache: every test passes an explicit stream_home under tmp_path, never the default
EDGELOG_HOME, so nothing here ever reads the box's own live ohlc_stream files either.
"""
import csv
import json
import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.qqq_reprice as R

TRADE_COLS = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px", "pnl"]


# ── helpers ──────────────────────────────────────────────────────────────────────────
def _write_trades_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _one_trade(day, entry="12:30:16", exit_="15:58:05", side="long", shares="5",
               entry_px="490.00", exit_px="495.00", pnl="25.00", leg="NOISE"):
    return {"leg": leg, "entry_ts": f"{day} {entry}", "exit_ts": f"{day} {exit_}",
            "side": side, "shares": shares, "entry_px": entry_px, "exit_px": exit_px,
            "pnl": pnl}


def _write_config(path, slippage=0.01):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"slippage_per_share": slippage}, f)


def _write_stream_csv(home, minute_closes, timeframe="1m"):
    """Write a fake <home>/ohlc_stream/QQQ_<timeframe>.csv -- api/webull_stream.py's own
    on-disk schema (time = UTC epoch seconds of the bar's OPEN instant, bar-start
    stamped) -- from {naive ET datetime: close}."""
    path = R._stream_bar_path(timeframe, home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for dt, close in minute_closes.items():
            dt_aware = dt.replace(tzinfo=R._NY) if R._NY else dt
            epoch = int(dt_aware.timestamp())
            w.writerow([epoch, close, close, close, close, 100])
    return path


def _refuse(name):
    def _fn(*a, **k):
        raise AssertionError(f"{name} must not be called: a higher-preference source "
                             "already covered every trade in this run")
    return _fn


@pytest.fixture
def no_keys(tmp_path):
    """A webull_keys.json path that PROVABLY does not exist -- see this file's module
    docstring's NETWORK SAFETY section for why every test must pass this explicitly."""
    return str(tmp_path / "no_such_webull_keys.json")


@pytest.fixture
def no_stream(tmp_path):
    """A stream_home with no ohlc_stream/QQQ_1m.csv under it."""
    return str(tmp_path / "no_such_edgelog_home")


@pytest.fixture
def rig(tmp_path, no_keys):
    """Common on-disk layout: trades.csv / reprice.csv / config.json paths (nothing
    written yet) plus the always-fake webull_keys_path, bundled so every test's run()
    call reads the same way."""
    return {
        "trades_csv": str(tmp_path / "trades.csv"),
        "sidecar_csv": str(tmp_path / "reprice.csv"),
        "config_path": str(tmp_path / "config.json"),
        "webull_keys_path": no_keys,
    }


NOOP = lambda *a, **k: None


# ── (a) stream fully covers a trade -> wins, and (b)/(c) are never even called ───────
def test_stream_bars_used_when_complete_and_lower_tiers_never_called(tmp_path, rig, monkeypatch):
    day = "2026-09-24"
    stream_home = str(tmp_path / "home")
    _write_stream_csv(stream_home, {datetime(2026, 9, 24, 12, 30): 500.0,
                                     datetime(2026, 9, 24, 15, 58): 501.0})
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])

    monkeypatch.setattr(R, "fetch_webull_rest_1m", _refuse("Webull REST 1m history"))
    monkeypatch.setattr(R, "fetch_day_bars", _refuse("yfinance"))

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0

    row = R.read_sidecar(rig["sidecar_csv"])[("NOISE", f"{day} 12:30:16")]
    assert row["price_source"] == R.SOURCE_STREAM
    assert row["source"] == R.SOURCE_STREAM
    assert float(row["real_entry_px"]) == 500.0
    assert float(row["real_exit_px"]) == 501.0


# ── fallback: stream file missing entirely ───────────────────────────────────────────
def test_fallback_when_stream_file_missing(tmp_path, rig, no_stream, monkeypatch):
    day = "2026-09-24"
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])

    yf_bars = {datetime(2026, 9, 24, 12, 30): 700.0, datetime(2026, 9, 24, 15, 58): 701.0}
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: yf_bars if d == day else None)
    # webull_keys_path (rig) provably doesn't exist -- fetch_webull_rest_1m runs for
    # real here and must cleanly return {} with zero network/SDK-import attempts.

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=no_stream, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("NOISE", f"{day} 12:30:16")]
    assert row["price_source"] == R.SOURCE_YFINANCE
    assert float(row["real_entry_px"]) == 700.0


def test_skip_note_mentions_every_source_tried():
    """A priced row's own note only describes ITS winning source's nearest-bar
    fallback (see reprice_one); a fully-SKIPPED row is where every attempted source's
    reason must show up, so a human reading reprice.csv can tell why."""
    trade = _one_trade("2026-09-24")
    row = R.reprice_one(trade, [(R.SOURCE_STREAM, {}), (R.SOURCE_REST, {}),
                                (R.SOURCE_YFINANCE, {}, {"2026-09-24": "beyond 30-day window"})],
                        slippage_per_share=0.01, log=NOOP)
    assert row["_skipped"] is True
    assert R.SOURCE_STREAM in row["note"]
    assert R.SOURCE_REST in row["note"]
    assert R.SOURCE_YFINANCE in row["note"]
    assert "beyond 30-day window" in row["note"]


# ── fallback: stream file present but PARTIAL (has the day, not the minute) ──────────
def test_fallback_when_stream_partial_out_of_tolerance(tmp_path, rig, monkeypatch):
    day = "2026-09-24"
    stream_home = str(tmp_path / "home")
    # a bar exists for this day, but nowhere near either the entry or exit minute
    _write_stream_csv(stream_home, {datetime(2026, 9, 24, 10, 0): 111.0})
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])

    yf_bars = {datetime(2026, 9, 24, 12, 30): 700.0, datetime(2026, 9, 24, 15, 58): 701.0}
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: yf_bars if d == day else None)

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("NOISE", f"{day} 12:30:16")]
    assert row["price_source"] == R.SOURCE_YFINANCE


# ── fallback: stream STALE mid-session (covers entry, feed died before exit) ─────────
# The whole round trip must fall through TOGETHER -- never mix a stream-priced entry
# with a yfinance-priced exit (see module docstring's SLIPPAGE CONVENTION).
def test_fallback_when_stream_stale_mid_session_never_mixes_sources(tmp_path, rig, monkeypatch):
    day = "2026-09-24"
    stream_home = str(tmp_path / "home")
    _write_stream_csv(stream_home, {datetime(2026, 9, 24, 12, 30): 500.0})  # feed died right after
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])

    yf_bars = {datetime(2026, 9, 24, 12, 30): 700.0, datetime(2026, 9, 24, 15, 58): 701.0}
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: yf_bars if d == day else None)

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("NOISE", f"{day} 12:30:16")]
    assert row["price_source"] == R.SOURCE_YFINANCE
    assert float(row["real_entry_px"]) == 700.0   # NOT 500.0 -- never a mixed-source price


# ── Webull REST used when the stream misses but the REST tail covers it ─────────────
def test_webull_rest_used_when_stream_missing_but_rest_covers(tmp_path, rig, no_stream, monkeypatch):
    day = "2026-09-24"
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])

    rest_bars = {day: {datetime(2026, 9, 24, 12, 30): 600.0,
                        datetime(2026, 9, 24, 15, 58): 601.0}}
    monkeypatch.setattr(R, "fetch_webull_rest_1m", lambda **k: rest_bars)
    monkeypatch.setattr(R, "fetch_day_bars", _refuse("yfinance"))

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=no_stream, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("NOISE", f"{day} 12:30:16")]
    assert row["price_source"] == R.SOURCE_REST
    assert float(row["real_entry_px"]) == 600.0


def test_webull_rest_not_called_when_stream_already_covers_everything(tmp_path, rig, monkeypatch):
    """A run() with MULTIPLE trades, all covered by the stream, must not call the REST
    tier at all -- it's a single (potentially rate-limited) network call per run, only
    worth making when something is actually still uncovered."""
    day = "2026-09-24"
    stream_home = str(tmp_path / "home")
    _write_stream_csv(stream_home, {datetime(2026, 9, 24, 12, 30): 500.0,
                                     datetime(2026, 9, 24, 15, 58): 501.0,
                                     datetime(2026, 9, 24, 13, 0): 510.0,
                                     datetime(2026, 9, 24, 14, 0): 511.0})
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [
        _one_trade(day, entry="12:30:16", exit_="15:58:05"),
        _one_trade(day, entry="13:00:02", exit_="14:00:09", leg="ORB"),
    ])
    monkeypatch.setattr(R, "fetch_webull_rest_1m", _refuse("Webull REST 1m history"))
    monkeypatch.setattr(R, "fetch_day_bars", _refuse("yfinance"))

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    sidecar = R.read_sidecar(rig["sidecar_csv"])
    assert len(sidecar) == 2
    assert all(r["price_source"] == R.SOURCE_STREAM for r in sidecar.values())


# ── no-keys-configured path exercises the REAL fetch_webull_rest_1m (not monkeypatched)
# and proves it makes zero network/SDK-import attempts ───────────────────────────────
def test_webull_rest_returns_empty_with_no_keys_configured_no_monkeypatch(no_keys):
    out = R.fetch_webull_rest_1m(keys_path=no_keys, token_dir=no_keys + "_token")
    assert out == {}


def test_webull_rest_returns_empty_with_placeholder_keys(tmp_path):
    keys_path = tmp_path / "webull_keys.json"
    keys_path.write_text(json.dumps({"app_key": "PASTE_APP_KEY_HERE",
                                     "app_secret": "PASTE_APP_SECRET_HERE"}),
                         encoding="utf-8")
    out = R.fetch_webull_rest_1m(keys_path=str(keys_path), token_dir=str(tmp_path / "token"))
    assert out == {}


# ── header migration: an old reprice.csv (no price_source column) survives ──────────
def test_old_reprice_csv_header_migrates_forward(tmp_path, rig, no_stream, monkeypatch):
    day = "2026-09-24"
    old_day = "2026-08-01"
    # an OLD-format sidecar row, written by the pre-item-11 code: no price_source column
    old_fieldnames = ["leg", "entry_ts", "exit_ts", "real_entry_px", "real_exit_px",
                      "real_pnl", "slip_entry_ps", "slip_exit_ps", "repriced_at",
                      "source", "note"]
    with open(rig["sidecar_csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old_fieldnames)
        w.writeheader()
        w.writerow({"leg": "NOISE", "entry_ts": f"{old_day} 10:00:00",
                    "exit_ts": f"{old_day} 10:05:00", "real_entry_px": "400.0",
                    "real_exit_px": "401.0", "real_pnl": "5.0", "slip_entry_ps": "0.1",
                    "slip_exit_ps": "0.1", "repriced_at": f"{old_day} 16:20:00",
                    "source": "yfinance_1m", "note": ""})

    # reading the old file must not crash, and must not yet claim a price_source key
    old_read_back = R.read_sidecar(rig["sidecar_csv"])
    assert ("NOISE", f"{old_day} 10:00:00") in old_read_back
    assert old_read_back[("NOISE", f"{old_day} 10:00:00")].get("price_source") is None

    # a normal run with ONE new trade forces a rewrite under the new header
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [
        _one_trade(old_day, entry="10:00:00", exit_="10:05:00"),  # already in sidecar -> skipped
        _one_trade(day),                                          # new
    ])
    yf_bars = {datetime(2026, 9, 24, 12, 30): 700.0, datetime(2026, 9, 24, 15, 58): 701.0}
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: yf_bars if d == day else None)

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=no_stream, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0

    with open(rig["sidecar_csv"], encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = {(r["leg"], r["entry_ts"]): r for r in reader}

    assert "price_source" in header
    # the old row survived the rewrite, migrated to the new header with a blank
    # price_source (it was never re-priced, so there's nothing truthful to backfill)
    old_row = rows[("NOISE", f"{old_day} 10:00:00")]
    assert old_row["real_entry_px"] == "400.0"
    assert old_row["price_source"] == ""
    # the new row got a real price_source
    new_row = rows[("NOISE", f"{day} 12:30:16")]
    assert new_row["price_source"] == R.SOURCE_YFINANCE


# ── skip row: no source covers the trade at all ──────────────────────────────────────
def test_skip_row_when_no_source_covers_trade(tmp_path, rig, no_stream, monkeypatch):
    day = "2026-09-24"
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [_one_trade(day)])
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: None)  # Yahoo has nothing either

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=no_stream, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    sidecar = R.read_sidecar(rig["sidecar_csv"])
    # a fully-skipped trade never gets a computed row written by write_sidecar (nothing
    # in `computed`) -- confirm the run didn't crash and simply left it unpriced.
    assert ("NOISE", f"{day} 12:30:16") not in sidecar


# ── _try_source: pure unit coverage of the tolerance/day-notes behaviour ────────────
def test_try_source_reports_day_notes_reason():
    entry_ts = datetime(2026, 9, 24, 12, 30, 16)
    exit_ts = datetime(2026, 9, 24, 15, 58, 5)
    px_e, px_x, notes = R._try_source({}, entry_ts, exit_ts, "2026-09-24", "2026-09-24",
                                      day_notes={"2026-09-24": "beyond 30-day window"})
    assert px_e is None and px_x is None
    assert notes == ["beyond 30-day window"]


def test_try_source_prices_both_legs_from_one_day():
    entry_ts = datetime(2026, 9, 24, 12, 30, 16)
    exit_ts = datetime(2026, 9, 24, 15, 58, 5)
    bars_by_day = {"2026-09-24": {datetime(2026, 9, 24, 12, 30): 500.0,
                                  datetime(2026, 9, 24, 15, 58): 501.0}}
    px_e, px_x, notes = R._try_source(bars_by_day, entry_ts, exit_ts,
                                      "2026-09-24", "2026-09-24")
    assert px_e == 500.0 and px_x == 501.0


# ── overnight hold: entry and exit on DIFFERENT ET calendar days (the ENGUQ_335 leg
# trades an ETH -- extended trading hours -- config and can hold overnight; see
# api/cloud_signal.py's module docstring). Both days must be looked up independently
# in whichever source is being tried. ────────────────────────────────────────────────
def test_overnight_trade_looks_up_both_calendar_days_in_stream(tmp_path, rig, monkeypatch):
    entry_day, exit_day = "2026-09-23", "2026-09-24"
    stream_home = str(tmp_path / "home")
    _write_stream_csv(stream_home, {datetime(2026, 9, 23, 23, 50): 480.0,
                                     datetime(2026, 9, 24, 6, 5): 482.0})
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [{
        "leg": "ENGUQ", "entry_ts": f"{entry_day} 23:50:03", "exit_ts": f"{exit_day} 06:05:11",
        "side": "long", "shares": "3", "entry_px": "470.0", "exit_px": "472.0", "pnl": "6.0",
    }])
    monkeypatch.setattr(R, "fetch_webull_rest_1m", _refuse("Webull REST 1m history"))
    monkeypatch.setattr(R, "fetch_day_bars", _refuse("yfinance"))

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("ENGUQ", f"{entry_day} 23:50:03")]
    assert row["price_source"] == R.SOURCE_STREAM
    assert float(row["real_entry_px"]) == 480.0
    assert float(row["real_exit_px"]) == 482.0


def test_overnight_trade_missing_only_the_exit_day_falls_through_entirely(tmp_path, rig, monkeypatch):
    """The stream has the ENTRY day but not the day the position closed on (e.g. the
    feed was only started partway through this multi-day hold) -- the round trip must
    still fall through AS A WHOLE to the next source, not price the entry from the
    stream and the exit from yfinance."""
    entry_day, exit_day = "2026-09-23", "2026-09-24"
    stream_home = str(tmp_path / "home")
    _write_stream_csv(stream_home, {datetime(2026, 9, 23, 23, 50): 480.0})  # exit_day absent
    _write_config(rig["config_path"])
    _write_trades_csv(rig["trades_csv"], [{
        "leg": "ENGUQ", "entry_ts": f"{entry_day} 23:50:03", "exit_ts": f"{exit_day} 06:05:11",
        "side": "long", "shares": "3", "entry_px": "470.0", "exit_px": "472.0", "pnl": "6.0",
    }])
    yf_bars = {
        entry_day: {datetime(2026, 9, 23, 23, 50): 600.0},
        exit_day: {datetime(2026, 9, 24, 6, 5): 602.0},
    }
    monkeypatch.setattr(R, "fetch_day_bars", lambda d, log=print: yf_bars.get(d))

    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=stream_home, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    row = R.read_sidecar(rig["sidecar_csv"])[("ENGUQ", f"{entry_day} 23:50:03")]
    assert row["price_source"] == R.SOURCE_YFINANCE
    assert float(row["real_entry_px"]) == 600.0   # NOT 480.0 -- never a mixed-source price


# ── no network anywhere in this file: yfinance is never left to run for real ────────
def test_module_never_calls_real_yfinance_without_monkeypatch(tmp_path, rig, no_stream):
    """Sanity check on the test suite itself: with nothing monkeypatched and no
    trades needing yfinance (there ARE no trades at all here), fetch_day_bars must
    simply never be invoked -- the empty-trades short circuit in run()."""
    _write_config(rig["config_path"])
    # trades.csv doesn't even exist -- read_trades returns [] and run() exits at the
    # very first check, long before any source is ever consulted.
    rc = R.run(rig["trades_csv"], rig["sidecar_csv"], rig["config_path"], apply=True,
               stream_home=no_stream, webull_keys_path=rig["webull_keys_path"], log=NOOP)
    assert rc == 0
    assert not os.path.exists(rig["sidecar_csv"])

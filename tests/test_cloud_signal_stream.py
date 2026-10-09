"""Tests for api/cloud_signal_stream.py -- WEBULL_PAPER_TODO.md item 10 ("fire orders at
the bar close from the live price feed"), consumer side. api/webull_stream.py's own
tests (tests/test_webull_stream.py) cover the PRODUCER (the atomic hand-off file, the
grace period, never publishing the first bar after a (re)connect); everything here is
what api/cloud_signal.py does with what it reads.

Every test uses its own tmp_path home via api.cloud_signal._paths(home=...) -- never the
real EDGELOG_HOME (tests/conftest.py's live-system guard blocks that regardless) -- and
a trivial deterministic strategy module, exactly like tests/test_cloud_signal.py's own
_stub_module pattern, so a "decision" here is never re-implemented: it always comes from
calling the SAME api.cloud_signal.closed_arrays / run_leg_trades / _diff_leg the real
step() uses.
"""
import csv
import os
import types

import pandas as pd
import pytest

from api import cloud_signal as cs
from api import cloud_signal_stream as css
from api import webull_stream as _wstream

LEG_KEY = "LEGA"
THRESHOLD = 705.0
SEED_CLOSES = [700.0, 701.0, 702.0, 703.0]   # 4 bars, all <= THRESHOLD -> no trade at seed


# ── fixtures / helpers ────────────────────────────────────────────────────────────────────
def _threshold_stub(threshold=THRESHOLD):
    """Fires ONE entry (bar[-2]'s open -> bar[-1]'s close, long) whenever the NEWEST
    bar's close is above `threshold`, else nothing. Deterministic and driven entirely by
    the newest bar's OHLC, so a stream bar and a REST bar that disagree on just that
    value can be made to disagree on the DECISION too -- exactly what design constraint
    2 ("it compares OHLC... if they would produce the SAME signal decision") needs."""
    mod = types.ModuleType(f"cloud_signal_stream_threshold_stub_{threshold}")
    mod.STRATEGY_NAME = "THRESHOLD_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        trades = []
        n = len(closes)
        if n >= 2 and float(closes[n - 1]) > threshold:
            entry_px = float(opens[n - 2])
            pnl = float(closes[n - 1] - entry_px)
            trades.append((n - 2, n - 1, pnl, 1, entry_px))
        cnt = len(trades)
        wins = 1 if trades and trades[0][2] > 0 else 0
        return {"trades": trades if return_trades else None, "num_trades": cnt,
               "total_pnl": sum(t[2] for t in trades), "win_rate": wins / cnt if cnt else 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": wins,
               "losses": cnt - wins}

    mod.run_backtest = run_backtest
    return mod


def _leg_cfg(threshold=THRESHOLD):
    return {"strategy": _threshold_stub(threshold), "timeframe": "5m", "params": {},
           "warmup_sessions": 5}


def _legs():
    return {LEG_KEY: _leg_cfg()}


def _5m_bars(closes, base=None):
    base = base or pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)   # a real weekday session
    n = len(closes)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(n)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    opens = [c - 0.5 for c in closes]
    df = pd.DataFrame({"time": epoch, "open": opens,
                       "high": [max(o, c) + 0.2 for o, c in zip(opens, closes)],
                       "low": [min(o, c) - 0.2 for o, c in zip(opens, closes)],
                       "close": closes, "volume": [1000.0] * n})
    return df, epoch, base


def _make_paths(tmp_path, name):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    return paths


def _seed_leg(paths, leg_key=LEG_KEY):
    cs._write_state({"legs": {leg_key: {"trades": {}, "seeded": True}},
                     "generated_at": "2026-09-08T09:00:00-04:00"}, paths)


def _setup(tmp_path, name="home"):
    """A fresh isolated home, seeded (no history absorption needed), with a 4-bar REST
    cache -- the NEXT (5th) bar's epoch is returned, not yet in that cache, standing in
    for 'REST has not settled this bar yet'."""
    paths = _make_paths(tmp_path, name)
    _seed_leg(paths)
    df, epoch, base = _5m_bars(SEED_CLOSES)
    df.to_csv(cs._cache_path("5m", paths), index=False)
    bar4_epoch = epoch[-1] + 300
    return paths, base, bar4_epoch


def _append_rest_bar(paths, bar_epoch, close):
    path = cs._cache_path("5m", paths)
    df = pd.read_csv(path)
    row = {"time": bar_epoch, "open": close - 0.5, "high": close + 0.2, "low": close - 0.7,
          "close": close, "volume": 1000.0}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(path, index=False)


def _write_handoff(paths, bar_epoch, close, bars_since_connect=3, fresh=True, connected=True):
    bar = {"time": bar_epoch, "open": close - 0.5, "high": close + 0.2, "low": close - 0.7,
          "close": close, "volume": 500.0}
    extra = {"connected": connected, "fresh": fresh, "bars_since_connect": bars_since_connect,
            "reconnects": 0, "published_epoch": bar_epoch + 300 + 1.5}
    return _wstream.write_closed_bar_handoff(bar, timeframe="5m", home=paths["home"], extra=extra)


def _now_after(base, bar4_epoch_offset_minutes=25, extra_seconds=5):
    return (base + pd.Timedelta(minutes=bar4_epoch_offset_minutes, seconds=extra_seconds)).to_pydatetime()


# ── pure helpers ──────────────────────────────────────────────────────────────────────────
def test_in_handoff_window_boundaries():
    boundary = pd.Timestamp("2026-09-08 09:35:00", tz=cs.TZ).to_pydatetime()
    assert css.in_handoff_window(boundary) is True
    assert css.in_handoff_window(boundary + pd.Timedelta(seconds=59)) is True
    assert css.in_handoff_window(boundary + pd.Timedelta(seconds=61)) is False
    assert css.in_handoff_window(boundary + pd.Timedelta(seconds=299)) is False


def _valid_payload(bar_epoch=1000, close=710.0):
    return {"time": bar_epoch, "open": close - 1, "high": close + 1, "low": close - 2,
           "close": close, "volume": 100.0, "connected": True, "fresh": True,
           "bars_since_connect": 3}


def test_stream_bar_is_usable_gates_everything_design_constraint_4_lists():
    now = pd.Timestamp("2026-09-08 09:35:05", tz=cs.TZ).to_pydatetime()
    assert css.stream_bar_is_usable(None, now) == (False, "no handoff payload published yet")
    assert css.stream_bar_is_usable(dict(_valid_payload(), connected=False), now)[0] is False
    assert css.stream_bar_is_usable(dict(_valid_payload(), fresh=False), now)[0] is False, (
        "a stale stream (health().fresh False) must never fire")
    assert css.stream_bar_is_usable(dict(_valid_payload(), bars_since_connect=1), now)[0] is False
    assert css.stream_bar_is_usable(dict(_valid_payload(), volume=0), now)[0] is False
    assert css.stream_bar_is_usable(dict(_valid_payload(), close=float("nan")), now)[0] is False
    weekend = pd.Timestamp("2026-09-05 10:00:00", tz=cs.TZ).to_pydatetime()   # a Saturday
    assert css.stream_bar_is_usable(_valid_payload(), weekend)[0] is False
    after_hours = pd.Timestamp("2026-09-08 17:00:00", tz=cs.TZ).to_pydatetime()
    assert css.stream_bar_is_usable(_valid_payload(), after_hours)[0] is False
    assert css.stream_bar_is_usable(_valid_payload(), now) == (True, "ok")


def test_load_stream_config_defaults_off_and_is_never_fatal(tmp_path):
    paths = _make_paths(tmp_path, "cfg_home")
    assert css.load_stream_config(paths) == {"bar_close_from_stream": False}
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(css._stream_config_path(paths), "w", encoding="utf-8") as f:
        f.write('{"bar_close_from_stream": true}')
    assert css.load_stream_config(paths) == {"bar_close_from_stream": True}
    with open(css._stream_config_path(paths), "w", encoding="utf-8") as f:
        f.write("not json")
    assert css.load_stream_config(paths, log=lambda *_: None) == {"bar_close_from_stream": False}


def test_compare_decisions_match_and_mismatch():
    ev = [{"event": "ENTRY", "side": "long", "ref_time": "t", "ref_price": 1, "shares": 1,
          "trade_id": "x", "size": 1.0, "keel_size": ""}]
    match, _ = css.compare_decisions(ev, list(ev))
    assert match is True
    mismatch, detail = css.compare_decisions(ev, [])
    assert mismatch is False and "stream=" in detail and "rest=" in detail


def test_augment_with_stream_bar_overrides_same_epoch_row():
    rest_df = pd.DataFrame({"time": [100, 400], "open": [1, 2], "high": [1, 2],
                            "low": [1, 2], "close": [1, 2], "volume": [10, 20]})
    bar = {"time": 400, "open": 9, "high": 9, "low": 9, "close": 9, "volume": 99}
    out = css._augment_with_stream_bar(rest_df, bar)
    assert list(out["time"]) == [100, 400]
    row = out[out["time"] == 400].iloc[0]
    assert row["close"] == 9 and row["volume"] == 99


def test_augment_with_stream_bar_handles_empty_rest_df():
    bar = {"time": 400, "open": 9, "high": 9, "low": 9, "close": 9, "volume": 99}
    out = css._augment_with_stream_bar(None, bar)
    assert list(out["time"]) == [400]


# ── shadow mode (design constraint 3 -- the main deliverable) ──────────────────────────────
def test_handoff_window_shadow_records_without_mutating_real_state(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)   # > THRESHOLD -> stream decision = ENTRY
    now = _now_after(base)
    logs = []

    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": False}, logs.append)

    assert css.already_shadowed(paths, LEG_KEY, bar4_epoch)
    rec = css._load_shadow(paths)[LEG_KEY][str(bar4_epoch)]
    assert rec["committed_live"] is False
    assert [e["event"] for e in rec["events"]] == ["ENTRY"]

    state = cs._load_state(paths)
    assert state["legs"][LEG_KEY].get("last_bar_epoch") != bar4_epoch, "flag off must never advance real state"
    assert state["legs"][LEG_KEY]["trades"] == {}
    assert not os.path.exists(paths["signals_path"]), "flag off must never append a real signal row"
    assert any("shadow: LEGA stream decision" in m for m in logs)


def test_handoff_window_dry_run_frame_includes_backfill_history(tmp_path, monkeypatch):
    """cloud_signal_review finding (major): _handle_handoff_window used to build its
    dry-run frame from cs.load_cached_bars alone, so once the Alpaca backfill lands
    (tools/backfill_qqq_5m_alpaca.py) the stream path would rank/decide against a
    SHORTER history than the REST path (cs.historical_bars via step()). Both must see
    the same bars, so this asserts the older backfill rows reach cs.closed_arrays."""
    paths, base, bar4_epoch = _setup(tmp_path, "backfill_home")
    # bars strictly OLDER than the 4-bar REST cache written by _setup, one week earlier
    # so they land in a distinct, unambiguous day bucket.
    backfill_df, backfill_epoch, _ = _5m_bars([690.0, 691.0], base=base - pd.Timedelta(days=7))
    backfill_df.to_csv(cs._backfill_path("5m", paths), index=False)
    _write_handoff(paths, bar4_epoch, close=710.0)

    seen_times = {}
    real_closed_arrays = cs.closed_arrays

    def _spy(df, *a, **kw):
        seen_times["times"] = set(df["time"].tolist())
        return real_closed_arrays(df, *a, **kw)

    monkeypatch.setattr(cs, "closed_arrays", _spy)

    now = _now_after(base)
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": False}, lambda *_: None)

    assert set(backfill_epoch).issubset(seen_times["times"]), (
        "the stream dry-run frame must include the older backfill rows, same as REST's "
        "cs.historical_bars")


def test_resolve_against_rest_logs_match_and_clears_shadow(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)
    now = _now_after(base)
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": False}, lambda *_: None)
    assert css.already_shadowed(paths, LEG_KEY, bar4_epoch)

    _append_rest_bar(paths, bar4_epoch, close=710.0)      # REST agrees with the stream
    now2 = now + pd.Timedelta(seconds=30)
    logs = []
    css._resolve_pending_against_rest(now2, _legs(), paths, logs.append)

    assert not css.already_shadowed(paths, LEG_KEY, bar4_epoch), "a resolved comparison must be cleared"
    assert any("shadow MATCH" in m for m in logs)
    assert not any("DISAGREEMENT" in m for m in logs)
    assert css._is_disagreement_tripped(paths, LEG_KEY, now2.date().isoformat()) is False


def test_resolve_against_rest_logs_disagreement_event_when_ohlc_differ(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)        # stream: above threshold -> ENTRY
    now = _now_after(base)
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": False}, lambda *_: None)

    _append_rest_bar(paths, bar4_epoch, close=690.0)      # REST: below threshold -> no trade
    now2 = now + pd.Timedelta(seconds=30)
    logs = []
    css._resolve_pending_against_rest(now2, _legs(), paths, logs.append)

    assert any("STREAM/REST DISAGREEMENT" in m and "LEGA" in m for m in logs)
    assert css._is_disagreement_tripped(paths, LEG_KEY, now2.date().isoformat()) is False, (
        "nothing was ever fired live off this bar, so there is nothing to guard against re-firing")


# ── the owner switch (design constraint 2) ──────────────────────────────────────────────────
def test_handoff_window_commits_live_when_flag_on_and_records_bar_source_stream(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)
    now = _now_after(base)
    logs = []

    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": True}, logs.append)

    state = cs._load_state(paths)
    assert state["legs"][LEG_KEY]["last_bar_epoch"] == bar4_epoch
    assert len(state["legs"][LEG_KEY]["trades"]) == 1

    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["event"] for r in rows] == ["ENTRY"]
    assert rows[0]["bar_source"] == "stream"
    assert rows[0]["leg"] == LEG_KEY

    assert css._load_shadow(paths)[LEG_KEY][str(bar4_epoch)]["committed_live"] is True
    assert any("LIVE from the stream" in m for m in logs)


def test_disagreement_after_a_live_commit_trips_latch_and_blocks_future_live_commits(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)
    now = _now_after(base)
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": True}, lambda *_: None)

    _append_rest_bar(paths, bar4_epoch, close=690.0)   # REST disagrees with the fired decision
    now2 = now + pd.Timedelta(seconds=30)
    css._resolve_pending_against_rest(now2, _legs(), paths, lambda *_: None)
    today = now2.date().isoformat()
    assert css._is_disagreement_tripped(paths, LEG_KEY, today) is True

    # a LATER bar must still be shadow-logged, but must NOT fire live -- "report the
    # disagreement rate instead" / never invent further live action off a tripped leg.
    bar5_epoch = bar4_epoch + 300
    _write_handoff(paths, bar5_epoch, close=720.0)
    now3 = now + pd.Timedelta(minutes=5, seconds=5)
    logs3 = []
    css._handle_handoff_window(now3, _legs(), paths, {"bar_close_from_stream": True}, logs3.append)

    state = cs._load_state(paths)
    assert state["legs"][LEG_KEY]["last_bar_epoch"] == bar4_epoch, "must not advance past the tripped leg"
    assert css.already_shadowed(paths, LEG_KEY, bar5_epoch), "shadow logging must continue regardless"
    assert any("not fired live" in m for m in logs3)


# ── ref_price tolerance (2026-09-28, seen live: NOISE_382 @ 1790604600) ───────────────────
def _ev(ref_price, **kw):
    ev = {"event": "ENTRY", "side": "short", "ref_time": "2026-09-28T10:15:00-04:00",
          "ref_price": ref_price, "shares": 2.0, "trade_id": "NOISE_382|x|short",
          "size": 2.0, "keel_size": 1.0}
    ev.update(kw)
    return ev


def test_compare_decisions_treats_a_sub_half_cent_ref_price_gap_as_the_same_decision():
    """The live case: stream 735.66 vs REST 735.6599 for the SAME entry used to read as a
    DISAGREEMENT. It is a match now, and the detail still names both prices."""
    match, detail = css.compare_decisions([_ev(735.66)], [_ev(735.6599)])
    assert match is True, detail
    assert "735.66" in detail and "735.6599" in detail


def test_compare_decisions_half_a_cent_is_in_whatever_the_float_arithmetic_says():
    """Exactly half a cent apart is a match however the subtraction rounds in binary:
    735.70 - 735.695 computes just UNDER 0.005 (passed before only by that luck), and
    730.19 - 730.185 just OVER it (a false DISAGREEMENT before REF_PRICE_EPS). The live
    pair 735.66 vs 735.6599 stays a match; a hair over half a cent stays a mismatch."""
    assert abs(735.70 - 735.695) < css.REF_PRICE_TOLERANCE < abs(730.19 - 730.185)
    for stream, rest in ((735.70, 735.695), (735.695, 735.70), (730.19, 730.185),
                         (735.66, 735.6599)):
        match, detail = css.compare_decisions([_ev(stream)], [_ev(rest)])
        assert match is True, (stream, rest, detail)
    assert css.compare_decisions([_ev(735.70)], [_ev(735.6949)])[0] is False
    assert css.compare_decisions([_ev(735.66)], [_ev(735.6549)])[0] is False
    assert css._prices_close("735.70", "735.695") is True


def test_compare_decisions_still_flags_real_price_and_field_differences():
    assert css.compare_decisions([_ev(735.66)], [_ev(735.65)])[0] is False, "a full cent is real"
    assert css.compare_decisions([_ev(735.66)], [_ev(735.6599, side="long")])[0] is False
    assert css.compare_decisions([_ev(735.66)], [_ev(735.6599, size=3.0)])[0] is False
    assert css.compare_decisions([_ev(735.66)], [_ev(735.6599, trade_id="other")])[0] is False
    assert css.compare_decisions([_ev(735.66)], [])[0] is False
    assert css.compare_decisions([_ev("")], [_ev("")])[0] is True


def _close_priced_legs(threshold=THRESHOLD):
    """Like _legs(), but the entry is priced at the NEWEST bar's close (what the
    decide_at_close probe does live), so a stream/REST close difference reaches ref_price."""
    mod = types.ModuleType("cloud_signal_stream_close_priced_stub")
    mod.STRATEGY_NAME = "CLOSE_PRICED_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(closes)
        trades = [(n - 1, n - 1, 0.0, 1, float(closes[n - 1]))] if n and closes[n - 1] > threshold else []
        return {"trades": trades if return_trades else None, "num_trades": len(trades),
               "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
               "avg_pnl": 0, "wins": 0, "losses": len(trades)}

    mod.run_backtest = run_backtest
    return {LEG_KEY: {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5}}


def test_sub_half_cent_close_gap_after_a_live_commit_is_a_match_and_keeps_the_latch_open(tmp_path):
    """End to end through the real resolve path: the stream fires live at 710.0, REST's
    bar says 709.9999 (and a different volume). Before the tolerance this logged a
    DISAGREEMENT and tripped the day's latch; now it is a MATCH that shows both prices
    and the ohlc diff, and the latch stays open."""
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)
    now = _now_after(base)
    css._handle_handoff_window(now, _close_priced_legs(), paths, {"bar_close_from_stream": True},
                               lambda *_: None)
    committed = css._load_shadow(paths)[LEG_KEY][str(bar4_epoch)]
    assert committed["committed_live"] is True
    assert [e["ref_price"] for e in committed["events"]] == [pytest.approx(710.0)]

    _append_rest_bar(paths, bar4_epoch, close=709.9999)
    now2 = now + pd.Timedelta(seconds=30)
    logs = []
    css._resolve_pending_against_rest(now2, _close_priced_legs(), paths, logs.append)

    assert not any("DISAGREEMENT" in m for m in logs), logs
    match_lines = [m for m in logs if "shadow MATCH" in m]
    assert match_lines and "709.9999" in match_lines[0] and "ohlc_diff" in match_lines[0]
    assert "'volume': -500.0" in match_lines[0], "the volume gap stays visible"
    assert css._is_disagreement_tripped(paths, LEG_KEY, now2.date().isoformat()) is False


def test_stale_stream_never_fires_live_or_shadows(tmp_path):
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0, fresh=False)
    now = _now_after(base)

    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": True}, lambda *_: None)

    assert not css.already_shadowed(paths, LEG_KEY, bar4_epoch)
    state = cs._load_state(paths)
    assert state["legs"][LEG_KEY].get("last_bar_epoch") != bar4_epoch
    assert not os.path.exists(paths["signals_path"])


# ── flag off means orders are unchanged (integration, via the real entry point) ────────────
def test_flag_off_produces_identical_signals_to_calling_step_directly(tmp_path):
    paths_a, base, bar4_epoch = _setup(tmp_path, "home_a")
    _append_rest_bar(paths_a, bar4_epoch, close=710.0)
    now = _now_after(base)
    events_a = cs.step(now=now, legs=_legs(), paths=paths_a, fetch=False)

    paths_b, base_b, bar4_epoch_b = _setup(tmp_path, "home_b")
    assert bar4_epoch_b == bar4_epoch
    _append_rest_bar(paths_b, bar4_epoch, close=710.0)
    _write_handoff(paths_b, bar4_epoch, close=710.0)     # a usable stream bar IS present
    events_b = css.run_stream_aware_step(now=now, legs=_legs(), paths=paths_b, fetch=False,
                                         warnings={})

    strip = lambda evs: [{k: v for k, v in e.items() if k != "emitted_at"} for e in evs]
    assert strip(events_a) == strip(events_b)

    state_a, state_b = cs._load_state(paths_a), cs._load_state(paths_b)
    assert state_a["legs"][LEG_KEY]["trades"] == state_b["legs"][LEG_KEY]["trades"]
    assert state_a["legs"][LEG_KEY].get("last_bar_epoch") == state_b["legs"][LEG_KEY].get("last_bar_epoch")


def test_run_stream_aware_step_always_calls_the_real_step_even_if_extras_blow_up(tmp_path, monkeypatch):
    paths, base, bar4_epoch = _setup(tmp_path)
    _append_rest_bar(paths, bar4_epoch, close=710.0)
    now = _now_after(base)
    monkeypatch.setattr(css, "_handle_handoff_window",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    logs = []

    events = css.run_stream_aware_step(now=now, legs=_legs(), paths=paths, fetch=False,
                                       warnings={}, log=logs.append)

    assert [e["event"] for e in events] == ["ENTRY"], "a bug in the new extras must never block the real step()"
    assert any("stream extras failed" in m for m in logs)


def test_a_levels_row_is_never_committed_from_the_stream(tmp_path, monkeypatch):
    """RESTING LEVELS (2026-09-29 review): a stream decision that carries a LEVELS row (a
    breakeven move of a resting stop) is shadow-recorded but never fired live, even with
    the owner switch on -- REST step() decides that bar."""
    paths, base, bar4_epoch = _setup(tmp_path)
    _write_handoff(paths, bar4_epoch, close=710.0)
    real = css._dry_run_decision

    def with_levels(*a, **k):
        events, mutated = real(*a, **k)
        return (events or []) + [{"event": "LEVELS", "side": "long", "ref_time": "t",
                                  "ref_price": 700.0, "trade_id": "x", "stop_px": 700.0,
                                  "target_px": 720.0}], mutated
    monkeypatch.setattr(css, "_dry_run_decision", with_levels)
    logs = []
    css._handle_handoff_window(_now_after(base), _legs(), paths,
                               {"bar_close_from_stream": True}, logs.append)
    state = cs._load_state(paths)
    assert state["legs"][LEG_KEY].get("last_bar_epoch") != bar4_epoch
    assert not os.path.exists(paths["signals_path"])
    assert css._load_shadow(paths)[LEG_KEY][str(bar4_epoch)]["committed_live"] is False
    assert any("carries a LEVELS row -- not fired live" in m for m in logs)


# ── "not taken: the market is closed" -- ONE line per trade through the stream path ───────
# (review 2026-10-09). _diff_leg logs one plain line for a live leg's new entry first seen
# after its session closed, including one from the PREVIOUS session first seen at the next
# morning's first hand-off. The stream path runs _diff_leg on throwaway copies (the dry run,
# then the REST what-if) before step() runs on the real state: each copy used to log the line
# too. Now a dry run's line is dropped -- unless that decision is COMMITTED, when it is the
# leg's real one (step() never sees the trade as new again).
PREV_DAY = pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)      # Tuesday
NEXT_OPEN = pd.Timestamp("2026-09-09 09:30:00", tz=cs.TZ)     # Wednesday's first 5m bar
NOT_TAKEN = "not taken: the market is closed"
WANT_LINE = ("[cloud-signal] LEGA long signal at 15:55 ET on 2026-09-08 (LEGA) not taken: the "
             "market is closed -- the strategy's entry was first seen at 09:35:05 ET on "
             "2026-09-09, after that session's 16:00 close. No order.")


def _prev_session_setup(tmp_path):
    """Tuesday's full session in the REST cache (every close under THRESHOLD, so no trade),
    a seeded leg, and Wednesday's 09:30 bar on the stream above THRESHOLD: the stub's entry
    is then Tuesday's 15:55 bar -- a previous-session entry first seen Wednesday 09:35."""
    paths = _make_paths(tmp_path, "home")
    _seed_leg(paths)
    df, epoch, _ = _5m_bars([700.0] * 78, base=PREV_DAY)
    df.to_csv(cs._cache_path("5m", paths), index=False)
    bar_epoch = int(NEXT_OPEN.tz_convert("UTC").timestamp())
    _write_handoff(paths, bar_epoch, close=710.0)
    now = (NEXT_OPEN + pd.Timedelta(minutes=5, seconds=5)).to_pydatetime()
    return paths, bar_epoch, now


def test_a_dry_run_never_logs_not_taken_and_step_logs_it_once(tmp_path, capsys):
    paths, bar_epoch, now = _prev_session_setup(tmp_path)
    logs = []
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": False},
                               logs.append)
    assert css._load_shadow(paths)[LEG_KEY][str(bar_epoch)]["events"] == []
    _append_rest_bar(paths, bar_epoch, close=710.0)
    later = now + pd.Timedelta(seconds=30)
    css._resolve_pending_against_rest(later, _legs(), paths, logs.append)
    assert [m for m in logs if NOT_TAKEN in m] == [], "no line from a throwaway copy"
    capsys.readouterr()
    assert cs.step(now=later, legs=_legs(), paths=paths, fetch=False) == []
    out = capsys.readouterr().out
    assert out.count(NOT_TAKEN) == 1, out
    assert WANT_LINE.replace("09:35:05", "09:35:35") in out
    cs.step(now=later + pd.Timedelta(minutes=1), legs=_legs(), paths=paths, fetch=False)
    assert NOT_TAKEN not in capsys.readouterr().out


def test_a_committed_stream_decision_logs_not_taken_once_and_step_does_not_repeat_it(
        tmp_path, capsys):
    paths, bar_epoch, now = _prev_session_setup(tmp_path)
    logs = []
    css._handle_handoff_window(now, _legs(), paths, {"bar_close_from_stream": True},
                               logs.append)
    assert css._load_shadow(paths)[LEG_KEY][str(bar_epoch)]["committed_live"] is True
    assert [m for m in logs if NOT_TAKEN in m] == [WANT_LINE]
    _append_rest_bar(paths, bar_epoch, close=710.0)
    later = now + pd.Timedelta(seconds=30)
    css._resolve_pending_against_rest(later, _legs(), paths, logs.append)
    capsys.readouterr()
    cs.step(now=later, legs=_legs(), paths=paths, fetch=False)
    assert NOT_TAKEN not in capsys.readouterr().out
    assert [m for m in logs if NOT_TAKEN in m] == [WANT_LINE]

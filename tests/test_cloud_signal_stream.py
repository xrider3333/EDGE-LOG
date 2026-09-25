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

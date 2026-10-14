"""api/cloud_signal.py -- LATE SKIPS ARE NEVER SILENT (owner 2026-10-14 via MANAGER #162/#163:
"make sure it does not happen again").

THE INCIDENT. The live ORB_R6 leg dropped five trades 09-21..09-25: today's still-building
session read as a half day (augur_strategies/ORB_3_6.py's 70%-of-median length test) until
~14:05, so each morning entry first appeared hours after its bar, past max_entry_age_sec, and
_diff_leg recorded it as "late" -- counted in state.json's late_skipped and NOTHING else: no
log line, no phone note. The root cause was fixed 09-26 (session_in_progress, pinned in
tests/test_cloud_signal_session_in_progress.py); this file pins the alarm, so the next "late"
drop -- whatever causes it -- is seen the same day:

  1. every late skip writes ONE log line naming the leg, the bar time, the side, the age and the
     freshness limit ("NOT TAKEN - late");
  2. a LIVE leg's FIRST late skip of the ET day sends ONE high plain phone note per leg
     (leg_state["late_alert"] + _engine_note's repeat rule); the next late skip that day does
     not; the next day pushes again;
  3. a SHADOW leg logs the line only, never a push; nor does a fetch=False tick (replay, the
     stream's dry runs) or a host that is not the cloud box (the PC runner) -- _push_allowed;
  4. step() passes its own store, so the note's repeat-rule file is that store's;
  5. the stream path's COMMIT pages for a late skip its fetch=False dry run recorded.

No network: the push is a stub, every store is under tmp_path.
"""
import json
import os
import types

import pandas as pd
import pytest

import api.cloud_signal as cs
from api import ntfy_push


LEG = "ORB_R6"
LIVE_CFG = {"strategy": "stub", "timeframe": "5m", "params": {}}
SHADOW_CFG = dict(LIVE_CFG, shadow=True)
QUIET = lambda *a, **k: None   # noqa: E731


def _now(day, hh, mm, ss=0):
    return pd.Timestamp(f"{day} {hh:02d}:{mm:02d}:{ss:02d}", tz=cs.TZ).to_pydatetime()


def _trade(entry_iso, side="long", entry_px=600.0):
    return {"entry_time": entry_iso, "side": side, "entry_px": entry_px, "shares": 166,
            "still_open": True, "exit_time": None, "exit_px": None}


def _seeded():
    return {"trades": {}, "seeded": True, "key_format": cs.TRADE_KEY_FORMAT}


@pytest.fixture
def pushes(monkeypatch):
    """The engine's background push, recorded instead of sent; this host is the cloud box."""
    sent = []

    def fake_push(msg, title, priority="high", paths=None, log=print):
        sent.append({"title": title, "message": msg, "priority": priority, "paths": paths})
        return "background"

    monkeypatch.setattr(cs, "_engine_push_background", fake_push)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    return sent


def _store(tmp_path, name="home"):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["state_dir"], exist_ok=True)
    return paths


def test_late_skip_is_logged_and_pushed_once_per_day(tmp_path, pushes):
    paths = _store(tmp_path)
    ls = _seeded()
    logs = []

    # 1. an entry first seen 20 minutes after its bar, limit 15 minutes
    ev = cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], ls, _now("2026-10-14", 10, 20),
                      max_entry_age_sec=900, bar_source="webull", cfg=LIVE_CFG, fetch=True,
                      log=logs.append, paths=paths)
    assert ev == [] and ls["late_skipped"] == 1
    assert logs == [
        "[cloud-signal] ORB_R6 NOT TAKEN - late: ORB long entry at the 10:00 ET bar on 2026-10-14 "
        "was first seen at 10:20:00 ET, 1200s (20.0 min) old -- past the 900s (15.0 min) "
        "freshness limit (max_entry_age_sec). No order."]
    assert len(pushes) == 1
    note = {"title": pushes[0]["title"], "message": pushes[0]["message"],
            "priority": pushes[0]["priority"]}
    assert ntfy_push.lint(note) == []
    assert note["title"] == "ORB: trade not taken" and note["priority"] == "high"
    assert note["message"].startswith("Trading: AFFECTED - ORB did not take its buy signal from ")
    assert "20 minutes" in note["message"]
    assert pushes[0]["paths"] == paths                       # step()'s own store, not the live one
    assert ls["late_alert"]["last_pushed_date"] == "2026-10-14"

    # 2. a second late trade the SAME day: its own line, no second push
    cs._diff_leg(LEG, [_trade("2026-10-14T11:00:00-04:00", side="short")], ls,
                 _now("2026-10-14", 11, 20), max_entry_age_sec=900, cfg=LIVE_CFG, fetch=True,
                 log=logs.append, paths=paths)
    assert ls["late_skipped"] == 2 and len(logs) == 2
    assert "ORB_R6 NOT TAKEN - late: ORB short entry at the 11:00 ET bar" in logs[1]
    assert len(pushes) == 1, "one phone note per leg per day"

    # ... and a restart the same day (state.json reloaded) still holds it
    cs._write_state({"legs": {LEG: ls}}, paths)
    ls = cs._load_state(paths)["legs"][LEG]
    cs._diff_leg(LEG, [_trade("2026-10-14T12:00:00-04:00")], ls, _now("2026-10-14", 12, 30),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=True, log=logs.append, paths=paths)
    assert ls["late_skipped"] == 3 and len(logs) == 3 and len(pushes) == 1

    # 3. the next day pushes again
    cs._diff_leg(LEG, [_trade("2026-10-15T10:00:00-04:00")], ls, _now("2026-10-15", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=True, log=logs.append, paths=paths)
    assert ls["late_skipped"] == 4 and len(logs) == 4
    assert len(pushes) == 2 and ls["late_alert"]["last_pushed_date"] == "2026-10-15"


def test_a_fresh_entry_is_emitted_with_no_line_and_no_push(tmp_path, pushes):
    ls = _seeded()
    logs = []
    ev = cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], ls, _now("2026-10-14", 10, 10),
                      max_entry_age_sec=900, cfg=LIVE_CFG, fetch=True, log=logs.append,
                      paths=_store(tmp_path))
    assert [e["event"] for e in ev] == ["ENTRY"]
    assert logs == [] and pushes == [] and "late_skipped" not in ls


def test_a_shadow_leg_logs_the_late_line_but_never_pushes(tmp_path, pushes):
    ls = _seeded()
    logs = []
    cs._diff_leg("NOISE_422_PLAIN", [_trade("2026-10-14T10:00:00-04:00")], ls,
                 _now("2026-10-14", 10, 20), max_entry_age_sec=900, cfg=SHADOW_CFG, fetch=True,
                 log=logs.append, paths=_store(tmp_path))
    assert ls["late_skipped"] == 1
    assert len(logs) == 1 and "NOISE_422_PLAIN NOT TAKEN - late" in logs[0]
    assert logs[0].endswith("Shadow leg: no order either way.")
    assert pushes == [] and "late_alert" not in ls


def test_no_push_off_a_live_fetching_tick_on_the_box(tmp_path, pushes, monkeypatch):
    """A replay or the stream's dry run (fetch=False), and the PC runner (not the cloud box):
    the line, never the phone."""
    logs = []
    ls = _seeded()
    cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], ls, _now("2026-10-14", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=False, log=logs.append,
                 paths=_store(tmp_path, "a"))
    monkeypatch.delenv("EDGELOG_HOST_ROLE")
    ls2 = _seeded()
    cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], ls2, _now("2026-10-14", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=True, log=logs.append,
                 paths=_store(tmp_path, "b"))
    assert len(logs) == 2 and all("NOT TAKEN - late" in m for m in logs)
    assert pushes == []
    assert ls["late_skipped"] == 1 and ls2["late_skipped"] == 1


def test_a_dropped_not_taken_channel_drops_the_line_too(tmp_path, pushes):
    """The stream's dry runs pass not_taken_log=False (a throwaway copy's line would repeat
    step()'s); a collecting callable gets it instead of `log`."""
    logs, collected = [], []
    cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], _seeded(), _now("2026-10-14", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=False, log=logs.append,
                 not_taken_log=False)
    cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], _seeded(), _now("2026-10-14", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=False, log=logs.append,
                 not_taken_log=collected.append)
    assert logs == [] and len(collected) == 1 and "NOT TAKEN - late" in collected[0]


# ── step(): the live path end to end (fetch=True, the fetch itself faked off disk) ─────────
def _two_bar_entry_stub():
    """Enters at the LAST session's 09:35 bar whenever that bar is in the window."""
    mod = types.ModuleType("late_skip_stub")
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        last_day = index[-1].date()
        out = []
        for i, ts in enumerate(index):
            if ts.date() == last_day and ts.strftime("%H:%M") == "09:35":
                out.append((i, len(closes) - 1, 0.0, 1, float(closes[i])))
        return {"trades": out if return_trades else None, "num_trades": len(out),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


def _bars(days, last_until):
    rows = []
    for d in days:
        start = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        stop = pd.Timestamp(f"{d} {last_until}", tz=cs.TZ) if d == days[-1] else \
            pd.Timestamp(f"{d} 16:00", tz=cs.TZ)
        t = start
        while t < stop:
            rows.append((int(t.tz_convert("UTC").timestamp()), 600.0, 600.5, 599.5, 600.0, 1000.0))
            t += pd.Timedelta(minutes=5)
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def test_step_logs_and_pushes_a_late_skip_into_its_own_store(tmp_path, pushes, monkeypatch, capsys):
    """The first fetching tick after a gap (a restart, a feed outage -- or 09-21's half-day
    misread) finds today's 09:35 entry 25 minutes old: never emitted, never silent."""
    paths = _store(tmp_path)
    legs = {LEG: {"strategy": _two_bar_entry_stub(), "timeframe": "5m", "params": {},
                  "warmup_sessions": 5}}
    days = ["2026-10-12", "2026-10-13", "2026-10-14"]
    # seed on 10-13 after the close, so the leg is armed before today's session
    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print: (_bars(days[:2], "16:00"), "webull", True))
    assert [e["event"] for e in cs.step(now=_now("2026-10-13", 16, 30), legs=legs, paths=paths,
                                        fetch=True)] == ["SEED"]
    capsys.readouterr()
    # 10:05:10 today: bars through the 10:00 bar have closed; the 09:35 entry is 30 min old
    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print: (_bars(days, "10:05"), "webull", True))
    ev = cs.step(now=_now("2026-10-14", 10, 5, 10), legs=legs, paths=paths, fetch=True)
    assert ev == []
    st = cs._load_state(paths)["legs"][LEG]
    assert st["late_skipped"] == 1 and st["late_alert"]["last_pushed_date"] == "2026-10-14"
    out = capsys.readouterr().out
    assert out.count("NOT TAKEN - late") == 1 and "09:35 ET bar on 2026-10-14" in out
    assert len(pushes) == 1 and pushes[0]["paths"] == paths
    # the repeat rule's own record lives in THIS store, not the live one
    with open(os.path.join(paths["state_dir"], cs.PHONE_DEDUPE_FILE), encoding="utf-8") as f:
        assert "late_skip:ORB_R6" in json.load(f)


# ── the stream path's commit (api/cloud_signal_stream._handle_handoff_window) ──────────────
def test_a_stream_commit_pages_for_the_late_skip_its_dry_run_recorded(tmp_path, pushes):
    paths = _store(tmp_path)
    baseline = _seeded()
    mutated = _seeded()
    logs = []
    # the dry run: fetch=False -> the line is collected, nothing is pushed
    cs._diff_leg(LEG, [_trade("2026-10-14T10:00:00-04:00")], mutated, _now("2026-10-14", 10, 20),
                 max_entry_age_sec=900, cfg=LIVE_CFG, fetch=False, log=QUIET,
                 not_taken_log=logs.append)
    assert pushes == [] and len(logs) == 1
    # the commit
    assert cs._push_committed_late_skips(LEG, LIVE_CFG, baseline, mutated,
                                         _now("2026-10-14", 10, 20), paths=paths, log=QUIET) is True
    assert len(pushes) == 1 and mutated["late_alert"]["last_pushed_date"] == "2026-10-14"
    # nothing new against the committed state -> no push; a shadow cfg never pages
    assert cs._push_committed_late_skips(LEG, LIVE_CFG, mutated, mutated,
                                         _now("2026-10-14", 10, 21), paths=paths) is False
    assert cs._push_committed_late_skips(LEG, SHADOW_CFG, baseline, _seeded(),
                                         _now("2026-10-14", 10, 21), paths=paths) is False
    assert len(pushes) == 1

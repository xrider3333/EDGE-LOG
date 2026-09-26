"""Unit tests for the shadow loader's contract guard (ROLL_AUDIT 4.5.5, 6.6 item 15),
including the 2026-09-26 review-finding fixes:

  1. api/paper.py's contract-continuity guard on the NT capture tail
     (_capture_tail_contract_check, wired into run_shadow) -- now compares only the MOST
     RECENT shared bars (not a median over the whole overlap), and uses a looser
     no-overlap threshold across a session break than within one session.
  (The September-roll trade MARKS live in api/paper.py's ROLL_ARTIFACTS list, shipped
  separately in 2e2cd47; this file tests only the contract guard.)

Everything here is synthetic (no real master, no real 10s file, no Firestore, no
network) -- find_master / load_master_arrays / _load_fresh_ticks / run_backtest are
monkeypatched directly on the `paper` module, same technique tests/test_webull_paper_
smoke.py uses for OrderAdapter._build_client. Never touches C:\\EdgeLog (conftest's
live-system guard would fail the test if it tried).
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import paper  # noqa: E402


def _et(s):
    return pd.Timestamp(s, tz="US/Eastern")


def _bars(times_et, opens, closes):
    """A resampled-bars DataFrame + its bars_et index, the shape _capture_tail_contract_
    check receives from run_shadow (post _resample + _filter_rth, pre 'keep' cut)."""
    n = len(times_et)
    df = pd.DataFrame({
        "time": [int(t.timestamp()) for t in times_et],
        "open": opens, "high": [max(o, c) + 0.1 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.1 for o, c in zip(opens, closes)], "close": closes,
        "volume": [1] * n,
    })
    return df, pd.DatetimeIndex(times_et)


def _master(times_et, closes):
    return {
        "index": pd.DatetimeIndex(times_et),
        "open": np.asarray(closes, float), "high": np.asarray(closes, float),
        "low": np.asarray(closes, float), "close": np.asarray(closes, float),
        "volume": np.asarray([10] * len(closes), float),
    }


# ── 1. _capture_tail_contract_check (synthetic frames) ──────────────────────────────

def test_same_contract_overlap_ok():
    """Overlapping bar, close within a few points of the master -- tail is fine."""
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    bars, bars_et = _bars([_et("2024-01-03 09:35"), _et("2024-01-03 09:40")],
                          opens=[100.4, 100.6], closes=[100.6, 101.0])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is True, reason


def test_different_contract_overlap_refused():
    """Same overlapping bar, but +300 points off -- a different-contract tail."""
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    bars, bars_et = _bars([_et("2024-01-03 09:35"), _et("2024-01-03 09:40")],
                          opens=[400.4, 400.6], closes=[400.6, 401.0])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is False
    assert "different contract" in reason


def test_no_overlap_small_gap_ok():
    """No shared timestamps; the first fresh bar opens close to the master's last close,
    same session (same ET calendar date)."""
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    bars, bars_et = _bars([_et("2024-01-03 09:40"), _et("2024-01-03 09:45")],
                          opens=[101.0, 101.2], closes=[101.2, 101.4])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is True, reason


def test_no_overlap_large_gap_refused():
    """No shared timestamps, same session; the first fresh bar opens far from the
    master's last close -- above a normal bar move, well below a real roll offset
    (~293 NQ points)."""
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    bars, bars_et = _bars([_et("2024-01-03 09:40"), _et("2024-01-03 09:45")],
                          opens=[400.5, 400.6], closes=[400.6, 401.0])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is False
    assert "different contract" in reason


def test_no_overlap_cross_session_gap_uses_looser_threshold():
    """Review finding (minor): a no-overlap gap measured ACROSS a session break (e.g.
    yesterday's RTH close vs. today's RTH open) is often > 50 NQ points on an ordinary
    overnight move. That must not be refused at the same-session threshold, but a gap
    beyond the looser cross-session threshold (still far under a ~293-pt roll) is."""
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 15:55")], [100.0, 100.5])
    # +100 pts overnight: beats the same-session 50-pt threshold, well inside the
    # cross-session 150-pt one.
    bars, bars_et = _bars([_et("2024-01-04 09:30")], opens=[200.5], closes=[200.5])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is True, reason
    assert "session break" in reason

    # +200 pts overnight clears even the looser cross-session threshold.
    bars2, bars_et2 = _bars([_et("2024-01-04 09:30")], opens=[300.5], closes=[300.5])
    ok2, reason2 = paper._capture_tail_contract_check(master, bars2, bars_et2, "NQ")
    assert ok2 is False
    assert "different contract" in reason2


def test_es_uses_its_own_tighter_threshold():
    master = _master([_et("2024-01-03 09:30")], [4500.0])
    bars, bars_et = _bars([_et("2024-01-03 09:30")], opens=[4502.0], closes=[4502.0])
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "ES")
    assert ok is False, reason  # +2 pts beats ES's 1.5 pt overlap threshold
    bars2, bars_et2 = _bars([_et("2024-01-03 09:30")], opens=[4500.5], closes=[4500.5])
    ok2, reason2 = paper._capture_tail_contract_check(master, bars2, bars_et2, "ES")
    assert ok2 is True, reason2  # +0.5 pts is inside it


def test_empty_master_or_empty_bars_is_ok():
    empty_master = _master([], [])
    bars, bars_et = _bars([_et("2024-01-03 09:40")], opens=[100.0], closes=[100.0])
    ok, reason = paper._capture_tail_contract_check(empty_master, bars, bars_et, "NQ")
    assert ok is True

    master = _master([_et("2024-01-03 09:30")], [100.0])
    empty_bars, empty_et = _bars([], [], [])
    ok2, reason2 = paper._capture_tail_contract_check(master, empty_bars, empty_et, "NQ")
    assert ok2 is True


# ── 1b. recent-bars-only median (review finding, major) ─────────────────────────────
# The 09-15 incident's shape: ~20 days of RTH bars where master and capture AGREE, then
# only the LAST day disagrees by a splice-sized offset. A median over every shared bar
# reads that as "median gap 0.00 pts, ok" and appends the fake drop; the fix restricts the
# comparison to the shared bars in the master's own final session.

def _multi_day_bars(n_days, start="2024-01-02", per_day_offset=None):
    """n_days of one RTH-ish bar per day at 09:30, closes rising by 0.5/day from 100.0.
    `per_day_offset` is an optional {day_index: pts} map added to that day's CAPTURE close
    only (day_index 0 = first day, n_days-1 = last day)."""
    days = pd.bdate_range(start, periods=n_days)
    times = [pd.Timestamp(d, tz="US/Eastern") + pd.Timedelta(hours=9, minutes=30)
             for d in days]
    master_closes = [100.0 + 0.5 * i for i in range(n_days)]
    per_day_offset = per_day_offset or {}
    cap_closes = [master_closes[i] + per_day_offset.get(i, 0.0) for i in range(n_days)]
    master = _master(times, master_closes)
    bars, bars_et = _bars(times, opens=cap_closes, closes=cap_closes)
    return master, bars, bars_et


def test_long_agreeing_history_plus_recent_mismatch_is_refused():
    """(a) 20 days agreeing, only the LAST (most recent / master's final session) day off
    by a splice-sized +295 -- must be refused, not washed out by the 19 agreeing days."""
    n = 20
    master, bars, bars_et = _multi_day_bars(n, per_day_offset={n - 1: 295.0})
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is False, reason
    assert "different contract" in reason


def test_long_mismatched_old_history_plus_recent_agreement_is_accepted():
    """(b) The reverse: the OLDEST shared day is off by +295 (e.g. a capture back-loaded
    onto the new contract while the master is still on the old one for its older bars),
    but every recent day -- including the master's final session -- agrees. Must be
    accepted: an average over the whole overlap would wrongly refuse this tail for weeks."""
    n = 20
    master, bars, bars_et = _multi_day_bars(n, per_day_offset={0: 295.0})
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is True, reason


def test_recent_window_falls_back_when_final_session_has_no_overlap():
    """If the master's own final session has no shared bar at all (e.g. the capture is
    missing that one session), fall back to the last N shared timestamps rather than
    refusing to compare anything."""
    days = pd.bdate_range("2024-01-02", periods=10)
    master_times = [pd.Timestamp(d, tz="US/Eastern") + pd.Timedelta(hours=9, minutes=30)
                    for d in days]
    master_closes = [100.0 + i for i in range(10)]
    master = _master(master_times, master_closes)
    # capture shares every day except the master's LAST session, and agrees everywhere.
    cap_times = master_times[:-1]
    cap_closes = master_closes[:-1]
    bars, bars_et = _bars(cap_times, opens=cap_closes, closes=cap_closes)
    ok, reason = paper._capture_tail_contract_check(master, bars, bars_et, "NQ")
    assert ok is True, reason
    assert "shared bar(s)" in reason


# ── 4. run_shadow wiring: the guard actually gates what gets appended ───────────────

def _leg(key="TESTLEG", instrument="NQ", timeframe="5m"):
    return {"key": key, "strategy": "DUMMY.py", "instrument": instrument,
            "timeframe": timeframe, "session": "rth", "params": {}, "cost_pts": 0.0,
            "mult": 20.0}


def _patch_common(monkeypatch, master_arrays, ticks_df):
    monkeypatch.setattr(paper, "find_master", lambda *a, **k: {"filename": "dummy.csv"})
    monkeypatch.setattr(paper, "load_master_arrays", lambda *a, **k: dict(master_arrays))
    monkeypatch.setattr(paper, "_load_fresh_ticks", lambda *a, **k: (ticks_df, "fake_path"))
    monkeypatch.setattr(paper, "run_backtest", lambda *a, **k: {"trades": []})


def _ticks_row(bar_start_et, close):
    """One 10s-style row whose END timestamp is the bar's close (NT's own convention;
    see _resample's stamp='end' docstring), landing in the 5-minute bucket starting at
    bar_start_et."""
    end_t = int((bar_start_et + pd.Timedelta(minutes=5)).timestamp())
    return {"time": end_t, "open": close, "high": close, "low": close, "close": close,
            "volume": 1}


def test_run_shadow_refuses_different_contract_tail(monkeypatch):
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    ticks_df = pd.DataFrame([
        _ticks_row(_et("2024-01-03 09:35"), 400.5),   # overlaps master's last bar, +300 off
        _ticks_row(_et("2024-01-03 09:40"), 400.6),
    ])
    _patch_common(monkeypatch, master, ticks_df)
    r = paper.run_shadow(_leg(), dt.date(2024, 1, 3))
    assert r["bars_appended"] == 0
    assert any("capture tail refused" in w for w in r["warnings"])


def test_run_shadow_appends_same_contract_tail(monkeypatch):
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    ticks_df = pd.DataFrame([
        _ticks_row(_et("2024-01-03 09:35"), 100.6),   # overlaps, well within threshold
        _ticks_row(_et("2024-01-03 09:40"), 101.0),   # the fresh bar to append
    ])
    _patch_common(monkeypatch, master, ticks_df)
    r = paper.run_shadow(_leg(), dt.date(2024, 1, 3))
    assert not any("capture tail refused" in w for w in r["warnings"])
    assert r["bars_appended"] == 1


def test_run_shadow_no_overlap_case(monkeypatch):
    master = _master([_et("2024-01-03 09:30"), _et("2024-01-03 09:35")], [100.0, 100.5])
    ticks_df = pd.DataFrame([
        _ticks_row(_et("2024-01-03 09:40"), 101.0),   # first bar strictly after master
    ])
    _patch_common(monkeypatch, master, ticks_df)
    r = paper.run_shadow(_leg(), dt.date(2024, 1, 3))
    assert not any("capture tail refused" in w for w in r["warnings"])
    assert r["bars_appended"] == 1

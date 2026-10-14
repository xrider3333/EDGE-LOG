"""EOD audit guards G5 + G8 (2026-10-14, MANAGER #155, owner: "I want NO more EOD issues").

G5: a normal day's session.flat_by is clamped to 15:59 -- a config of "16:00" (the 2026-09-17/18
    setting that fired the flatten after the bell, when Webull refused every market sell) can no
    longer reach the bell. Half days keep their own clamp (12:57).
G8: without the America/New_York zone the executor used to fall back to UTC silently (the 15:59
    flatten would fire at 11:59 ET); it now refuses. DST: the flatten minute, the flatten deadline
    and the after-close guard sit at 15:59 / 15:59:50 / 16:00:00 New York time on the first
    trading day after each clock change.
"""
import datetime
import os
import sys
from zoneinfo import ZoneInfo

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import qqq_exec as qe  # noqa: E402
from test_qqq_exec_exit_safety import _tick_cfg, _tick_paths  # noqa: E402

NY = ZoneInfo("America/New_York")
QUIET = lambda *a, **k: None  # noqa: E731


def _cfg_with_flat_by(v):
    cfg = _tick_cfg()
    cfg["session"] = dict(cfg["session"], flat_by=v)
    return cfg


# ── G5 ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("configured", ["16:00", "16:05"])
def test_a_flat_by_at_or_after_the_close_is_clamped_to_1559_on_a_normal_day(tmp_path, monkeypatch,
                                                                            configured):
    _tick_paths(tmp_path, monkeypatch)
    now = datetime.datetime(2026, 10, 13, 10, 0, 0)          # an ordinary Tuesday
    cfg, state, _doc = qe.tick(cfg=_cfg_with_flat_by(configured), state={"legs": {}}, now=now,
                               log=QUIET)
    assert cfg["session"]["flat_by"] == "15:59"
    assert state.get("flat_by_clamp_logged_date") == "2026-10-13"
    assert any("flat_by_clamped" in str(e) for e in (state.get("events") or [])) or \
        state.get("flat_by_clamp_logged_date")
    assert qe._past_flat_by(datetime.datetime(2026, 10, 13, 15, 59, 1), cfg["session"])


def test_a_flat_by_inside_the_session_is_left_alone(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    now = datetime.datetime(2026, 10, 13, 10, 0, 0)
    cfg, state, _doc = qe.tick(cfg=_cfg_with_flat_by("15:59"), state={"legs": {}}, now=now,
                               log=QUIET)
    assert cfg["session"]["flat_by"] == "15:59" and not state.get("flat_by_clamp_logged_date")


def test_a_half_day_keeps_its_own_clamp_even_with_a_1600_config(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    now = datetime.datetime(2026, 11, 27, 10, 0, 0)
    cfg, _state, _doc = qe.tick(cfg=_cfg_with_flat_by("16:00"), state={"legs": {}}, now=now,
                                log=QUIET)
    assert cfg["session"]["flat_by"] == "12:57"


# ── G8 ──────────────────────────────────────────────────────────────────────────────────────────
def test_no_new_york_zone_refuses_instead_of_running_on_utc(monkeypatch):
    monkeypatch.setattr(qe, "_NY", None)
    with pytest.raises(RuntimeError, match="New_York"):
        qe._now_et()


def test_now_et_is_new_york_time():
    assert qe._now_et().tzinfo is not None and qe._now_et().utcoffset() in (
        datetime.timedelta(hours=-4), datetime.timedelta(hours=-5))


@pytest.mark.parametrize("day", [datetime.date(2026, 11, 2),     # first trading day of EST
                                 datetime.date(2026, 3, 9)])      # first trading day of EDT
def test_the_eod_times_hold_new_york_time_across_the_clock_change(day):
    at = lambda h, m, s=0: datetime.datetime(day.year, day.month, day.day, h, m, s, tzinfo=NY)  # noqa: E731
    sess = {"flat_by": "15:59"}
    assert not qe._past_flat_by(at(15, 58, 59), sess) and qe._past_flat_by(at(15, 59, 0), sess)
    assert qe._session_flatten_deadline(at(12, 0)) == at(16, 0) - datetime.timedelta(
        seconds=qe.SESSION_FLATTEN_DEADLINE_MARGIN_SEC)
    assert not qe._market_closed_for_orders(at(15, 59, 59))
    assert qe._market_closed_for_orders(at(16, 0, 0))
    # the same instants in UTC still read as New York times once converted
    utc = at(16, 0, 0).astimezone(datetime.timezone.utc)
    assert qe._market_closed_for_orders(utc.astimezone(NY))

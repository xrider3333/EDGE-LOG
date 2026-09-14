"""The 10-second NQ feed watchdog in api/nt_heartbeat.py.

THE BUG IT EXISTS FOR (2026-09-09). NinjaTrader was healthy all session -- bridge up, all
three strategies Realtime, fills.csv fresh, the nt_heartbeat dead-man's switch green --
while its 10-second chart export had been dead since 08:39:40 ET. Nothing noticed, because
every existing watcher asks a different question: nt_recover.ps1 asks about STRATEGY state,
the bridge asks whether NinjaTrader is running, and nt_heartbeat asked whether the bridge is
still publishing. A chart indicator that silently stops writing answers "yes" to all three.

The consequence is not cosmetic: with no live NQ price the NQ paper-trading board cannot
mark an open lot, so an end-of-day flatten prices the exit at the ENTRY price and writes a
fabricated round trip into the forward record the go-live decision rests on.

`evaluate_tick_feed` is pure, so the real outage can simply be replayed here.

FALSE-ALARM FIX (2026-09-14). The alert used to also blame "the QQQ shadow" unconditionally,
but api/qqq_exec.py's default signal_source is "engine" since v73.770, which never reads
this feed -- so that clause was live-verified false on 2026-09-14 (the shadow's own state
showed feed_stale=false, cursor advancing, no refusals) while the export really was dead.
The tests below cover the two modes: engine (no QQQ mention) vs ninjatrader (mention kept).
"""
import datetime
import zoneinfo

from api import nt_heartbeat as h

NY = zoneinfo.ZoneInfo("America/New_York")


def _et(h_, m, s=0, day=9):
    return datetime.datetime(2026, 9, 9 if day == 9 else day, h_, m, s, tzinfo=NY)


def test_live_feed_is_ok():
    now = _et(10, 25)
    fresh = (now - datetime.timedelta(seconds=10)).timestamp()
    r = h.evaluate_tick_feed(fresh, now, True)
    assert r["state"] == "ok"
    assert r["alerted"] is False


def test_the_real_2026_09_09_outage_is_caught():
    # last live bar 08:39:40, looked at 10:25 -- the exact shape of the real failure
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True)
    assert r["state"] == "stale"
    assert r["age_minutes"] > 100
    assert "chart export has stopped" in r["message"]
    assert r["alerted"] is False, "first sight of an outage must be free to page"


def test_alert_latches_so_one_outage_pages_once():
    dead = _et(8, 39, 40).timestamp()
    first = h.evaluate_tick_feed(dead, _et(10, 25), True)
    # publish() sets alerted=True after paging; the next cycle must carry that forward
    second = h.evaluate_tick_feed(dead, _et(10, 30), True, dict(first, alerted=True))
    assert second["state"] == "stale"
    assert second["alerted"] is True


def test_resumed_feed_clears_the_latch():
    now = _et(11, 30)
    fresh = (now - datetime.timedelta(seconds=20)).timestamp()
    r = h.evaluate_tick_feed(fresh, now, True, {"alerted": True, "state": "stale"})
    assert r["state"] == "ok"
    assert r["alerted"] is False, "a self-healed feed must not stay latched"


def test_quiet_outside_regular_hours_and_on_non_session_days():
    dead = _et(8, 39, 40).timestamp()
    # 03:00 on a session day: NQ trades, but nothing here mirrors it -- do not page
    assert h.evaluate_tick_feed(dead, _et(3, 0), True)["state"] == "idle"
    # 16:00 exactly is already outside the watched window
    assert h.evaluate_tick_feed(dead, _et(16, 0), True)["state"] == "idle"
    # a holiday/weekend, in-hours: still idle
    assert h.evaluate_tick_feed(dead, _et(10, 25), False)["state"] == "idle"


def test_missing_file_is_reported_not_swallowed():
    r = h.evaluate_tick_feed(None, _et(10, 25), True)
    assert r["state"] == "missing"
    assert "no 10s NQ feed file" in r["message"]


def test_reader_never_raises_on_a_bad_path():
    assert h.newest_tick_bar_epoch((r"C:\nope\does_not_exist.csv",)) is None


def test_reader_skips_a_header_or_torn_final_line(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    p.write_text("time,open,high,low,close,volume\n1788957580,1,2,3,4,5\nnot-a-number,\n",
                 encoding="utf-8")
    assert h.newest_tick_bar_epoch((str(p),)) == 1788957580.0


# ── QQQ shadow wording -- engine vs ninjatrader (2026-09-14 false-alarm fix) ────────────
# The real incident: signal_source defaults to "engine" since v73.770 and never reads this
# feed, so the alert must not blame it in that mode -- but must keep blaming it in the old
# "ninjatrader" mode, where the shadow genuinely still reads this file (NQ:QQQ ratio pricing,
# see api/qqq_exec.py's resolve_price/_last_nq_close). Covers both the "stale" and "missing"
# states, since both page (see publish()'s `state in ("stale", "missing")` check).

def test_engine_mode_stale_omits_qqq_wording():
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True, qqq_signal_source="engine")
    assert r["state"] == "stale"
    assert "chart export has stopped" in r["message"]
    assert "QQQ" not in r["message"]


def test_engine_mode_missing_omits_qqq_wording():
    r = h.evaluate_tick_feed(None, _et(10, 25), True, qqq_signal_source="engine")
    assert r["state"] == "missing"
    assert "QQQ" not in r["message"]


def test_unresolved_signal_source_defaults_to_no_qqq_wording():
    """The safe default: if the caller could not resolve the shadow's config at all
    (qqq_signal_source left at None), the message must NOT claim the QQQ shadow is
    affected -- the false alarm this exists to prevent, not a coin flip."""
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True)
    assert "QQQ" not in r["message"]


def test_ninjatrader_mode_stale_keeps_qqq_wording():
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True, qqq_signal_source="ninjatrader")
    assert r["state"] == "stale"
    assert "chart export has stopped" in r["message"]
    assert "QQQ shadow" in r["message"]
    assert "refusing new entries" in r["message"]


def test_ninjatrader_mode_missing_keeps_qqq_wording():
    r = h.evaluate_tick_feed(None, _et(10, 25), True, qqq_signal_source="ninjatrader")
    assert r["state"] == "missing"
    assert "QQQ shadow" in r["message"]


def test_qqq_wording_is_case_insensitive_and_ignores_whitespace():
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True, qqq_signal_source=" NinjaTrader ")
    assert "QQQ shadow" in r["message"]


def test_non_paging_states_are_unaffected_by_signal_source():
    now = _et(10, 25)
    fresh = (now - datetime.timedelta(seconds=10)).timestamp()
    ok_engine = h.evaluate_tick_feed(fresh, now, True, qqq_signal_source="engine")
    ok_nt = h.evaluate_tick_feed(fresh, now, True, qqq_signal_source="ninjatrader")
    assert ok_engine["message"] == ok_nt["message"] == f"10s NQ feed live ({ok_engine['age_minutes']:.1f} min old)"
    idle = h.evaluate_tick_feed(None, _et(3, 0), True, qqq_signal_source="ninjatrader")
    assert idle["state"] == "idle" and "QQQ" not in idle["message"]


# ── _qqq_signal_source() -- read-only config peek, reusing qqq_exec.load_config ────────

def test_qqq_signal_source_missing_config_defaults_to_engine_without_writing_anything(tmp_path, monkeypatch):
    from api import qqq_exec as qe
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    monkeypatch.setattr(qe, "CONFIG_PATH", str(cfg_path))
    src, err = h._qqq_signal_source()
    assert src == "engine"
    assert err is None
    assert not cfg_path.exists(), "must stay read-only -- must never create config.json itself"


def test_qqq_signal_source_reads_ninjatrader_from_existing_config(tmp_path, monkeypatch):
    import json
    from api import qqq_exec as qe
    out_dir = tmp_path / "qqq_exec"
    out_dir.mkdir()
    cfg_path = out_dir / "config.json"
    cfg_path.write_text(json.dumps({"signal_source": "ninjatrader"}), encoding="utf-8")
    monkeypatch.setattr(qe, "CONFIG_PATH", str(cfg_path))
    src, err = h._qqq_signal_source()
    assert src == "ninjatrader"
    assert err is None


def test_qqq_signal_source_reads_engine_from_existing_config(tmp_path, monkeypatch):
    import json
    from api import qqq_exec as qe
    out_dir = tmp_path / "qqq_exec"
    out_dir.mkdir()
    cfg_path = out_dir / "config.json"
    cfg_path.write_text(json.dumps({"signal_source": "engine", "mode": "SHADOW"}), encoding="utf-8")
    monkeypatch.setattr(qe, "CONFIG_PATH", str(cfg_path))
    src, err = h._qqq_signal_source()
    assert src == "engine"
    assert err is None


def test_qqq_signal_source_never_raises_when_qqq_exec_unimportable(monkeypatch):
    import sys
    import api as api_pkg
    # `from api import qqq_exec` only re-imports the submodule when the PACKAGE object
    # has no such attribute yet -- since some earlier test already imported it, "api"
    # already carries a live "qqq_exec" attribute, so sys.modules alone is not enough to
    # force a fresh failure; both must be cleared.
    monkeypatch.delattr(api_pkg, "qqq_exec", raising=False)
    monkeypatch.setitem(sys.modules, "api.qqq_exec", None)
    src, err = h._qqq_signal_source()
    assert src is None
    assert err

r"""STALE KEEL NEVER SIZES (2026-10-11, owner via MANAGER #125: "live KEEL must behave like its
adopting backtest"). api/cloud_signal.KEEL_MAX_STALE_SESSIONS is 1 (was 5): a learned KEEL leg
(live NOISE_382, KEEL v12) sizes on its model only when the state was rebuilt after the previous
session; one missed nightly rebuild and the entry sizes on v12's fixed tilts alone (KEEL
FIXED-TILT FALLBACK -- a Friday entry 1.5x, never 1.0), with a stale reason. After a half day
the builder drops that short session, so the state before it stays current (the box monitor's
keel_expected rule). The box monitor (tools/webull_freshness.py) pages a missed rebuild ONCE:
keel:<leg> is the HIGH fallback note the evening it is missed (keel_fallback:<leg> is folded
into it), nothing more while the episode is open -- not the pre-open gate, not the engine's own
fallback push (before or after a restart). A missed NQ upload is that one push (nq_master, now
HIGH); a shadow leg stays quiet.

Synthetic bars and a tiny real fitted state (tests/test_cloud_signal_keel.py fixtures), a
temp box home (tests/test_webull_freshness.Home) -- no NQ master, no network, no live file.
"""
import datetime as dt
import json
import os
import sys

import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for p in (ROOT, THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import api.cloud_signal as cs  # noqa: E402
import tools.webull_freshness as wf  # noqa: E402
from api import noise_forward as nf  # noqa: E402
from api import ntfy_push  # noqa: E402
from test_cloud_signal_keel import _arrays, _fitted_state, _write_state  # noqa: E402
from test_webull_freshness import Home, et  # noqa: E402

QUIET = lambda *a, **k: None  # noqa: E731
FIXED = {"version": "v12", "mode": "fixed"}
BAR = 10
LIVE_KEEL = "keel:NOISE_382_v12"
ONE_HIGH_NOTE = {
    "title": "QQQ book: CHECK NOW", "priority": "high",
    "message": "Trading: AFFECTED - NOISE trades on the fixed size tilts only until its sizing "
               "model is rebuilt.\n"
               "The KEEL sizing model was not rebuilt after the close.\n"
               "Do: ask Claude (PAPER-WB chat)."}


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _learned(tmp_path, base, data_through):
    """Bars from `base`, a real state fitted on them, its summary trained through
    `data_through` -> (keel_cfg, arrays)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    arrays = _arrays(base=base)
    state, _ = _fitted_state(arrays)
    return _write_state(tmp_path, state, last_nq_session=data_through,
                        data_through=data_through), arrays


# == the engine: one missed rebuild sizes on the fixed tilts ====================================
def test_one_missed_rebuild_sizes_a_friday_entry_on_the_fixed_tilts_not_the_old_model(tmp_path):
    friday = pd.Timestamp("2026-09-11 09:30:00", tz=cs.TZ)
    assert friday.dayofweek == 4
    entry = friday + pd.Timedelta(minutes=5 * BAR)
    # trained through Thursday (the normal case after the 18:30 ET rebuild): n_stale 1, the model
    cfg, arrays = _learned(tmp_path / "thu", friday, "2026-09-10")
    want, fdiag = cs._keel_fixed_size_for_entry(FIXED, arrays, BAR)
    assert isinstance(fdiag, dict) and want >= 1.5, "a Friday bar carries the 1.5x tilt"
    size, diag = cs._keel_size_for_entry(cfg, arrays, BAR, entry, log=QUIET)
    assert isinstance(diag, dict), f"the model sized it: {diag!r}"
    assert cs._keel_fallback_reason(cfg, entry) is None
    # trained through Wednesday -- Thursday's rebuild was missed: n_stale 2, fixed tilts only
    cfg, arrays = _learned(tmp_path / "wed", friday, "2026-09-09")
    size, why = cs._keel_size_for_entry(cfg, arrays, BAR, entry, log=QUIET)
    assert size == want != 1.0, "the backtest never drops the fixed tilts"
    assert isinstance(why, str) and why == (
        f"keel state stale: 2 session(s) since 2026-09-09; {cs.KEEL_FIXED_FALLBACK_NOTE} "
        f"({want:g}x)")
    assert cs._keel_fallback_is_real(why) and cs._keel_fell_back_to_fixed(why)
    # the step-time freshness read and the NOISE forward log name the same fallback
    assert cs._keel_fallback_reason(cfg, entry) == "keel state stale: 2 session(s) since 2026-09-09"
    assert nf.keel_fallback(cfg, entry.isoformat(), want, fixed_size=want) == \
        "keel state stale: 2 session(s) since 2026-09-09"
    extras = cs._keel_entry_extras(cfg, arrays, BAR, why, log=QUIET)
    assert extras["keel_branch"] == cs.KEEL_BRANCH_FALLBACK_FIXED
    assert cs.KEEL_MAX_STALE_SESSIONS == cs.KEEL_PUSH_STALE_SESSIONS == 1


def test_after_a_half_day_the_state_before_it_is_current(tmp_path):
    """Fri 2026-11-27 closes at 13:00 and the builder drops it: Monday's entry on a state trained
    through Wed 11-25 is the normal case (the model sizes it); one through Tue 11-24 missed a
    rebuild (fixed tilts)."""
    monday = pd.Timestamp("2026-11-30 09:30:00", tz=cs.TZ)
    entry = monday + pd.Timedelta(minutes=5 * BAR)
    assert wf.keel_expected(dt.date(2026, 11, 27)) == dt.date(2026, 11, 25)
    cfg, arrays = _learned(tmp_path / "wed", monday, "2026-11-25")
    size, diag = cs._keel_size_for_entry(cfg, arrays, BAR, entry, log=QUIET)
    assert isinstance(diag, dict), f"the model sized it: {diag!r}"
    assert cs._keel_fallback_reason(cfg, entry) is None
    cfg, arrays = _learned(tmp_path / "tue", monday, "2026-11-24")
    size, why = cs._keel_size_for_entry(cfg, arrays, BAR, entry, log=QUIET)
    assert isinstance(why, str)
    assert why.startswith("keel state stale: 3 session(s) since 2026-11-24")
    assert cs._keel_fell_back_to_fixed(why)


# == the box monitor: one push per stale episode =================================================
def _evening(h, t, keel_through):
    """Evening of session day `t`: that day's close done and settled, NQ landed, KEEL as given."""
    h.set_now(t)
    h.exec_state()
    h.cs_state()
    h.advance(t)
    h.bars(t)
    h.keel(through=keel_through)


def _keel_pushes(h):
    return [p for p in h.pushes if "KEEL" in p["message"] or "fixed size tilts" in p["message"]]


def test_a_missed_rebuild_pages_once_high_and_the_engine_stays_silent(tmp_path, monkeypatch):
    """Mon 10-05: the NQ data landed but KEEL was not rebuilt. 19:05 ET: ONE high note (the
    fallback), no keel_fallback episode. Then nothing more while it is open: later runs, Tuesday's
    pre-open gate, the engine's step-time and scoring-time fallback pushes on Tuesday (also after
    a restart of the engine: its own stamps lost), Tuesday evening still not rebuilt. Wednesday's
    rebuild ends it with one low OK."""
    h = Home(tmp_path, et(2026, 10, 5, 19, 5))
    h.keel(through="2026-10-02")
    out = h.run()
    assert h.pushes == [ONE_HIGH_NOTE] and ntfy_push.lint(h.pushes[0]) == []
    opened = {r["key"]: r for r in out["opened"]}
    assert not opened[LIVE_KEEL].get("quiet")
    assert out["status"]["verdicts"][LIVE_KEEL]["severity"] == wf.HIGH
    assert not [k for k in opened if k.startswith("keel_fallback:")]
    assert "keel_fallback:NOISE_382_v12" not in {
        k for k, v in out["status"]["verdicts"].items() if v["ok"] is False}

    for t in (et(2026, 10, 5, 19, 7), et(2026, 10, 5, 21, 0), et(2026, 10, 6, 8, 30),
              et(2026, 10, 6, 9, 15)):
        h.advance(t)
        h.run()
    assert h.pushes == [ONE_HIGH_NOTE], "the pre-open gate does not buzz again"

    # Tuesday in the session: the engine sees the same old model (2 sessions) -- the monitor's
    # open keel:<leg> episode owns the page, before and after a restart
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push",
                        lambda msg, title, log=print: (sent.append(msg), True)[1])
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=h.root))
    tue = pd.Timestamp("2026-10-06 10:00:00", tz=cs.TZ)
    cfg, arrays = _learned(tmp_path / "keel", tue.normalize() + pd.Timedelta(hours=9, minutes=30),
                           "2026-10-02")
    for _restart in range(2):
        monkeypatch.setattr(cs, "_KEEL_STATE_CACHE", {})
        state, leg_alert = {}, {}
        cs._maybe_push_keel_fallback("NOISE_382", cfg, tue, state, log=QUIET)
        assert state["keel_alerts"]["NOISE_382"]["last_pushed_date"] == "2026-10-06"
        size, why = cs._keel_size_for_entry(cfg, arrays, BAR, tue, log=QUIET)
        assert why.startswith("keel state stale: 2 session(s) since 2026-10-02")
        assert cs._keel_fallback_push_once("NOISE_382", why, "2026-10-06", [leg_alert],
                                           log=QUIET) is False
        assert leg_alert["last_pushed_date"] == "2026-10-06"
    assert sent == [], "the monitor already paged this episode"

    _evening(h, et(2026, 10, 6, 19, 5), "2026-10-02")             # still not rebuilt
    h.run()
    assert h.pushes == [ONE_HIGH_NOTE]
    _evening(h, et(2026, 10, 7, 19, 6), "2026-10-07")             # rebuilt
    out = h.run()
    assert LIVE_KEEL in {r["key"] for r in out["recovered"]}
    assert [p["title"] for p in h.pushes] == ["QQQ book: CHECK NOW", "QQQ book: OK"]
    assert h.pushes[1]["priority"] == "low"


def test_a_missed_nq_upload_is_the_one_high_push_and_the_keel_legs_fold_into_it(tmp_path,
                                                                                monkeypatch):
    """The PC's upload never lands: 18:00 ET nq_master is the ONE push, now HIGH (the next session
    sizes on the fixed tilts only unless the upload lands); 19:05 the KEEL legs open QUIET; the
    engine's push stays silent on Tuesday while that nq_master episode is open."""
    fri = dt.date(2026, 10, 2)
    h = Home(tmp_path, et(2026, 10, 5, 18, 0))
    h.bars(h.now, nq_day=fri)
    h.keel(through="2026-10-02")
    h.run()
    assert h.pushes == [{
        "title": "QQQ book: CHECK NOW", "priority": "high",
        "message": "Trading: AFFECTED - NOISE trades on the fixed size tilts only until the "
                   "upload lands and its sizing model is rebuilt.\n"
                   "The PC's after-close NQ data upload did not reach the cloud box.\n"
                   "Do: run the upload on the PC before 15:30, or ask Claude (PAPER-WB chat)."}]
    h.advance(et(2026, 10, 5, 19, 5))
    out = h.run()
    keel_opened = [r for r in out["opened"] if r["key"].startswith("keel:")]
    assert {r["key"] for r in keel_opened} >= {LIVE_KEEL} and all(r["quiet"] for r in keel_opened)
    assert len(h.pushes) == 1, "the KEEL legs fold into the NQ note"
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push",
                        lambda msg, title, log=print: (sent.append(msg), True)[1])
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=h.root))
    assert cs._monitor_owns_keel_stale("NOISE_382")
    cs._keel_fallback_push_once("NOISE_382", "keel state stale: 2 session(s) since 2026-10-02",
                                "2026-10-06", [{}], log=QUIET)
    assert sent == []
    # once the NQ episode closed, a QUIET keel episode no longer speaks for the phone
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        ms = json.load(f)
    ms["alerts"].pop("nq_master")
    with open(h.paths["monitor_state"], "w", encoding="utf-8") as f:
        json.dump(ms, f)
    assert not cs._monitor_owns_keel_stale("NOISE_382")


def test_an_open_keel_fallback_record_is_kept_while_the_model_is_too_old(tmp_path):
    """keel_fallback:<leg> no longer opens (keel:<leg> carries the fallback), but a record left
    open -- by the monitor before this change, deployed mid-episode -- is neither closed with a
    false "OK" while the model is still too old to use (here one missed rebuild: Tue evening,
    trained through Fri), nor pushed again; it closes (one low OK) once the model is rebuilt."""
    h = Home(tmp_path, et(2026, 10, 6, 19, 5))
    h.keel(through="2026-10-02")
    old = {"key": "keel_fallback:NOISE_382_v12", "group": "evening", "open": True, "bad_runs": 9,
           "severity": "HIGH", "title": "KEEL TOO OLD (NOISE_382_v12)", "detail": "x",
           "opened_epoch": 0.0, "last_bad_epoch": h.now.timestamp(), "hold_sec": 0.0,
           "plain": wf._plain("The KEEL sizing model is 5 sessions old, too old to use from the "
                              "next session.", affects="NOISE trades on the fixed size tilts "
                              "only, without its sizing model", priority="high")}
    os.makedirs(os.path.dirname(h.paths["monitor_state"]), exist_ok=True)
    with open(h.paths["monitor_state"], "w", encoding="utf-8") as f:
        json.dump({"alerts": {"keel_fallback:NOISE_382_v12": old,
                              LIVE_KEEL: dict(old, key=LIVE_KEEL)}}, f)
    out = h.run()
    assert h.pushes == [] and out["recovered"] == []
    assert {a["key"] for a in h.status()["open_alerts"]} >= {"keel_fallback:NOISE_382_v12"}
    _evening(h, et(2026, 10, 7, 19, 6), "2026-10-07")
    out = h.run()
    assert {r["key"] for r in out["recovered"]} >= {"keel_fallback:NOISE_382_v12", LIVE_KEEL}
    assert [p["title"] for p in h.pushes] == ["QQQ book: OK"]


def test_a_shadow_legs_missed_rebuild_stays_quiet(tmp_path):
    """DIP_424K (no orders) misses a rebuild: one quiet, MEDIUM keel:<leg> episode that says its
    would-be trades size on the fixed tilts only -- no push, no keel_fallback episode."""
    h = Home(tmp_path, et(2026, 10, 5, 19, 5))
    h.keel(through="2026-10-05")                                  # the live legs were rebuilt
    with open(os.path.join(h.paths["keel_dir"], "DIP_424K_v12_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump({"data_through": "2026-10-02", "leg": "DIP_424K", "leg_live": False}, f)
    out = h.run()
    assert h.pushes == []
    opened = {r["key"]: r for r in out["opened"]}
    assert set(opened) == {"keel:DIP_424K_v12"}
    rec = opened["keel:DIP_424K_v12"]
    assert rec["quiet"] is True and rec["severity"] == wf.MEDIUM
    assert rec["plain"]["problem"] == (
        "The DIP #424 shadow leg's KEEL model was not rebuilt after the close (shadow leg, no "
        "orders: its would-be trades size on the fixed tilts only).")

"""tests/test_dip424_live_engine.py -- DIP #424 at a FIXED 1.245x becomes a LIVE leg (OWNER GO
2026-10-10, MANAGER #115): the ENGINE side. api/cloud_signal.py CROWN_LEGS["DIP_424"] -- the
shadow DIP_424F's cfg minus "shadow" and minus its const KEEL block (the 1.245 is inside
api/qqq_exec.py's 6 shares per lot), live_since 2026-10-13, a 25-minute entry age -- beside the
two no-order shadow legs DIP_424K / DIP_424F, which stay. The executor side (the seven one-lot
exec legs DIP_RSI .. DIP_GAPDN, broker ids, rails) is tested in its own files.

Every case runs on tests/test_dip424_shadow.py's synthetic QQQ-shaped fixtures in a temp home, the
live step as cloud_signal_thread runs it (fetch=True, the fetch faked to read the on-disk cache
back) and then run_shadow_step on the same tick.

COVERS
  1. Config: the live cfg is DIP_424F's minus shadow/keel plus live_since + 25 min; appended after
     NOISE_382; the same params as both shadow DIP legs (one memo key).
  2. Seed at 09:30 (series through the previous session, the box's first step after a Monday
     evening deploy): SEED only, "no earlier state, starts flat"; the day's seven entries emit at
     09:35:05 with ids DIP_424-<UTC>-L-<SLOT>, row for row the shadow DIP_424F's (size 1.0, no
     KEEL); EXITs pair by id; the EOD settle step adds nothing; no row crosses stores.
  3. Late seed (series not ready at 09:30): the 09:35 SEED swallows the day -- no ENTRY, no EXIT
     for an absorbed position, a slot trades again once its position is gone -- while DIP_424F
     carries the same positions as seeded would-be trades.
  4. A cold start holding positions (walk fixture): the live SEED names the open slots and emits
     nothing; afterwards the live leg's ENTRY/EXIT rows are exactly DIP_424F's minus its carries,
     and no absorbed slot enters again before its absorbed position exits.
  5. The 25-minute entry age: first seen 09:54:55 -> emitted; 09:55:06 -> late (no ENTRY, its EXIT
     suppressed), while the shadow legs (390 min) still log it.
  6. The memo: ONE seven-engine-run probe per session for the live leg and both shadow legs (7, not
     21), none on the session's later bars; the live step's in-memory fetch frame and the cache it
     wrote give the same memo key.
  7. The stream path never decides a DIP leg (classic step() still does).
  8. A live key handed to the shadow step is dropped there: never a DIP_424 row or state in the
     shadow store, whatever dict the caller passes.
  9. The shipped live_since (2026-10-13) is a date gate: before it the live leg does nothing at all
     (cases 2-8 move it to the fixtures' first session).
  10. A live DIP leg whose daily series is not ready (or whose runner fails) pages once a day from
      09:40 and says so in step()'s warnings; a shadow leg never pages.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import api.cloud_signal as cs                       # noqa: E402
from api import cloud_signal_stream as css          # noqa: E402
from api import dip_live as DL                      # noqa: E402
from api import trade_id as T                       # noqa: E402
import test_dip424_shadow as S                      # noqa: E402  (the synthetic DIP fixtures)

QUIET = lambda *a, **k: None   # noqa: E731
LIVE = "DIP_424"
SHADOW = ("DIP_424K", "DIP_424F")
MECHS = S.MECHS
D_CRASH, D_ENTRY, D_X1, D_X2 = S.D_CRASH, S.D_ENTRY, S.D_X1, S.D_X2
at = S.at


@pytest.fixture(autouse=True)
def _fresh_memo():
    DL._PROBE_MEMO.clear()
    yield
    DL._PROBE_MEMO.clear()


@pytest.fixture
def offline(monkeypatch):
    """The live step runs with fetch=True as on the box, its fetch reading the on-disk cache back
    (a fetch that merged nothing new); every real network path raises; no noise forward log."""
    calls = []

    def fake_fetch(tf, paths=None, log=print):
        calls.append(tf)
        return cs.historical_bars(tf, paths), "webull", True

    def boom(*a, **k):
        raise AssertionError("network touched")
    monkeypatch.setattr(cs, "fetch_and_merge", fake_fetch)
    monkeypatch.setattr(cs, "_fetch_webull", boom)
    monkeypatch.setattr(cs.qp, "_fetch_yf", boom)
    monkeypatch.setattr(cs, "_fetch_yf_daily", boom)
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: False)
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
    return calls


# The synthetic fixture calendars end 2026-10-08, before the shipped live_since (2026-10-13), and
# live_since is also a date gate (the leg does nothing before it -- see test 9): every other case
# runs the shipped live cfg with its live_since moved to the fixtures' first session.
FIX_LIVE_SINCE = min(S.WALK_DAYS[0], S.CRASH_DAYS[0]).isoformat()


def _legs(home):
    """(live, shadow): the SHIPPED live DIP leg (live_since moved to FIX_LIVE_SINCE), and the
    shipped shadow pair (DIP_424K's KEEL pointed at `home`, where it has no state -> 1.0, never a
    push)."""
    return {LIVE: dict(cs.CROWN_LEGS[LIVE], live_since=FIX_LIVE_SINCE)}, S._dip_legs(home)


def _tick(paths, now, live, shadow, post_close=False):
    """One cloud_signal_thread fetch tick: the live step, then the shadow step."""
    lv = cs.step(now=now, legs=live, paths=paths, fetch=True, post_close=post_close)
    sh = cs.run_shadow_step(now=now, fetch=True, live_legs=live, shadow_legs=shadow,
                            live_paths=paths, log=QUIET, post_close=post_close)
    return lv, sh


def _of(events, leg):
    return [e for e in events if e["leg"] == leg]


def _state(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _shape(e):
    """An event as the executor reads it, minus the leg (in the id too) and the size."""
    p = T.parse(e["trade_id"]) if e.get("trade_id") else None
    return (e["event"], e["side"], e["ref_time"], e["ref_price"], e["shares"],
            (p["slot"], p["entry_utc"]) if p else None)


def _ledger_legs(path):
    return {r["leg"] for r in S._rows(path)}


# ── 1. config ──────────────────────────────────────────────────────────────────────────────
def test_live_leg_is_dip_424f_without_shadow_or_keel_plus_live_since_and_25_minutes():
    live = cs.CROWN_LEGS[LIVE]
    f = cs.SHADOW_LEGS["DIP_424F"]
    assert list(cs.CROWN_LEGS) == ["ORB_R6", "NOISE_382", LIVE], \
        "appended after NOISE_382 (its daily-cache refresh runs first on a live tick)"
    assert LIVE not in cs.SHADOW_LEGS and not set(SHADOW) & set(cs.CROWN_LEGS)
    want = {k: v for k, v in f.items() if k not in ("shadow", "keel", "max_entry_age_sec")}
    want.update(live_since="2026-10-12", max_entry_age_sec=25 * 60)
    assert live == want
    assert cs.DIP_424_LIVE_SINCE == "2026-10-12" and cs.DIP_LIVE_MAX_ENTRY_AGE_SEC == 1500
    assert live["runner"] == cs.DIP_RUNNER and live["timeframe"] == "5m"
    assert cs.leg_warmup_sessions(live) == cs.DIP_5M_ALL_SESSIONS
    for flag in ("shadow", "keel", "eod_flat", "decide_at_close", "resting_levels"):
        assert flag not in live, flag
    # the very same params (and strategy) as both shadow legs -> one probe memo key
    for key in SHADOW:
        assert cs.SHADOW_LEGS[key]["params"] == live["params"] == dict(cs.DIP_424_PARAMS, asset="ETF")
        assert cs.SHADOW_LEGS[key]["strategy"] == live["strategy"] == DL.STRATEGY
    # the shadows keep their whole-session age, the live leg's is 25 min
    assert f["max_entry_age_sec"] == 390 * 60 > live["max_entry_age_sec"]
    # gated like every live leg (it has no KEEL, so nothing in the engine ever pages for it)
    assert cs._push_allowed(live, True) == cs._push_allowed({}, True)
    assert cs.keel_mode(live.get("keel")) is None


# ── 2. the seed at 09:30, the day's entries at 09:35 ──────────────────────────────────────
def test_seed_at_0930_absorbs_the_past_and_the_day_s_seven_entries_emit_at_0935(tmp_path, offline):
    """The box's first step after a Monday-evening deploy is the next session's 09:30:0x: the
    daily series still ends at the previous session, so the SEED absorbs only positions entered up
    to it -- and the day's own entries, decided at that close, emit at the 09:30 bar's close."""
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live, shadow = _legs(paths["home"])
    sp = cs.shadow_paths(paths)
    lv, sh = _tick(paths, at(D_ENTRY, 9, 30, 5), live, shadow)
    assert [e["event"] for e in lv] == ["SEED"]
    assert lv[0]["reason"].startswith("cold start: absorbed ")
    assert "open_at_seed=none" in lv[0]["reason"] and "open_slots" not in lv[0]["reason"]
    assert f"live_since={FIX_LIVE_SINCE} (no earlier state, starts flat)" in lv[0]["reason"]
    assert sorted(e["leg"] for e in sh) == sorted(SHADOW) and {e["event"] for e in sh} == {"SEED"}
    ls = _state(paths["state_path"])["legs"][LIVE]
    assert ls["seeded"] is True and ls["live_since"] == FIX_LIVE_SINCE
    assert ls["live_since_reset"]["had_state"] is False
    assert not [k for k in ls["trades"] if k.startswith(f"{LIVE}-") and D_ENTRY.strftime("%Y%m%d") in k], \
        "the day's entries are NOT absorbed (their entry bar is after the series' last row)"
    # 09:34:59 changes nothing (today's 09:30 bar is not closed); 09:35:05: seven ENTRY rows
    assert _tick(paths, at(D_ENTRY, 9, 34, 59), live, shadow) == ([], [])
    lv, sh = _tick(paths, at(D_ENTRY, 9, 35, 5), live, shadow)
    when = f"{D_ENTRY.isoformat()}T09:30:00-04:00"
    assert [e["event"] for e in lv] == ["ENTRY"] * 7
    assert [e["trade_id"] for e in lv] == [T.make(LIVE, when, "long", slot=m) for m in MECHS]
    assert lv[0]["trade_id"] == f"{LIVE}-{D_ENTRY.strftime('%Y%m%d')}T133000Z-L-RSI"
    assert lv[5]["trade_id"].endswith("-L-STREAK"), "the engine id carries the FULL slot name"
    assert all(e["size"] == 1.0 and e["keel_size"] == "" for e in lv), \
        "no KEEL block: the 1.245 lives in the executor's 6 shares, never in the row"
    assert all(e["bar_source"] == "webull" and e["reason"].startswith("slot=") for e in lv)
    f = _of(sh, "DIP_424F")
    assert [_shape(e) for e in lv] == [_shape(e) for e in f], "row for row the shadow DIP_424F's"
    assert all(e["size"] == 1.245 for e in f) and len(_of(sh, "DIP_424K")) == 7
    # the EOD settle step after the bell adds nothing (no new trade; DIP exits are 09:30 fills)
    assert _tick(paths, at(D_ENTRY, 16, 0, 35), live, shadow, post_close=True) == ([], [])
    # D_X1: STREAK out at the open; D_X2: GAPDN out, STREAK back in on a new id
    lv1, sh1 = _tick(paths, at(D_X1, 9, 35, 5), live, shadow)
    assert [(e["event"], e["trade_id"]) for e in lv1] == [("EXIT", T.make(LIVE, when, "long", slot="STREAK"))]
    assert "eod_settle" not in lv1[0]["reason"] and lv1[0]["size"] == 1.0
    assert [_shape(e) for e in lv1] == [_shape(e) for e in _of(sh1, "DIP_424F")]
    lv2, sh2 = _tick(paths, at(D_X2, 9, 35, 5), live, shadow)
    assert sorted((e["event"], T.parse(e["trade_id"])["slot"]) for e in lv2) == \
        [("ENTRY", "STREAK"), ("EXIT", "GAPDN")]
    assert sorted(map(_shape, lv2)) == sorted(map(_shape, _of(sh2, "DIP_424F")))
    # NO ROW CROSSES STORES: the live ledger/state hold DIP_424 only, the shadow ones never it
    rows = S._rows(paths["signals_path"])
    assert _ledger_legs(paths["signals_path"]) == {LIVE}
    assert all(T.parse(r["trade_id"])["leg"] == LIVE for r in rows if r["event"] != "SEED")
    assert _ledger_legs(sp["signals_path"]) == set(SHADOW)
    assert set(_state(paths["state_path"])["legs"]) == {LIVE}
    assert set(_state(sp["state_path"])["legs"]) == set(SHADOW)
    assert not os.path.exists(paths["heartbeat_path"]), "the shadow run never writes the live heartbeat"


# ── 3. a late seed swallows the day (fail safe) ───────────────────────────────────────────
def test_a_seed_that_slides_to_0935_swallows_the_day_while_the_shadow_carries_it(tmp_path, offline):
    """The series is NOT ready at 09:30 (here: no QQQ_1d.csv yet), so the first SEED comes with the
    09:35 bar -- the day's seven entries are absorbed, not bought: DIP sits the day out. Each slot
    stays flat until its absorbed position exits (no EXIT row for it either), then trades again.
    The shadow DIP_424F carries the same seven positions as seeded would-be trades."""
    paths = S.write_home(tmp_path, S.CRASH, 30, no_1d=True)
    live, shadow = _legs(paths["home"])
    assert _tick(paths, at(D_ENTRY, 9, 30, 5), live, shadow) == ([], [])
    st = _state(paths["state_path"])["legs"][LIVE]
    assert not st.get("seeded") and st["live_since"] == FIX_LIVE_SINCE, "stamped, not seeded"
    S.write_1d(paths, S.CRASH)
    lv, sh = _tick(paths, at(D_ENTRY, 9, 35, 5), live, shadow)
    assert [e["event"] for e in lv] == ["SEED"]
    assert f"open_slots={','.join(MECHS)} (absorbed: each slot sits out until its position exits)" \
        in lv[0]["reason"]
    f = _of(sh, "DIP_424F")
    assert [e["event"] for e in f] == ["SEED"] + ["ENTRY"] * 7
    assert f"open_slots={','.join(MECHS)}; shadow leg: carried" in f[0]["reason"]
    assert all(e["reason"].startswith(cs.SEEDED_REASON_TAG) for e in f[1:])
    ls = _state(paths["state_path"])["legs"][LIVE]
    when = f"{D_ENTRY.isoformat()}T09:30:00-04:00"
    for m in MECHS:
        rec = ls["trades"][T.make(LIVE, when, "long", slot=m)]
        assert rec["seeded"] is True and rec["exit_emitted"] is True and rec["slot"] == m
    # D_X1: STREAK's absorbed position exits -> no live EXIT; the shadow's carried one does
    lv1, sh1 = _tick(paths, at(D_X1, 9, 35, 5), live, shadow)
    assert lv1 == []
    assert [(e["event"], T.parse(e["trade_id"])["slot"]) for e in _of(sh1, "DIP_424F")] == [("EXIT", "STREAK")]
    # D_X2: GAPDN's exits silently too, and STREAK -- flat again -- trades: a live ENTRY
    lv2, sh2 = _tick(paths, at(D_X2, 9, 35, 5), live, shadow)
    assert [(e["event"], T.parse(e["trade_id"])["slot"]) for e in lv2] == [("ENTRY", "STREAK")]
    assert lv2[0]["trade_id"] == T.make(LIVE, f"{D_X2.isoformat()}T09:30:00-04:00", "long", slot="STREAK")
    assert sorted((e["event"], T.parse(e["trade_id"])["slot"]) for e in _of(sh2, "DIP_424F")) == \
        [("ENTRY", "STREAK"), ("EXIT", "GAPDN")]
    assert {r["event"] for r in S._rows(paths["signals_path"])} == {"SEED", "ENTRY"}
    assert _ledger_legs(paths["signals_path"]) == {LIVE}
    assert _ledger_legs(cs.shadow_paths(paths)["signals_path"]) == set(SHADOW)


# ── 4. a cold start holding positions ─────────────────────────────────────────────────────
def test_live_cold_start_absorbs_open_slots_and_then_trades_exactly_like_dip_424f(tmp_path, offline):
    i = S._seed_day_with_open_positions()
    day = S.WALK_DAYS[i]
    paths = S.write_home(tmp_path, S.WALK, 45)
    live, shadow = _legs(paths["home"])
    open_now = [g for g in DL.dip_positions(S.series_from(S.WALK, i), S.LIVE_PARAMS) if g[2] is None]
    DL._PROBE_MEMO.clear()
    lv, sh = _tick(paths, at(day, 12, 0, 5), live, shadow)
    assert [e["event"] for e in lv] == ["SEED"], "the live SEED emits nothing"
    slots = [g[0] for g in open_now]
    assert len(slots) >= 2 and f"open_slots={','.join(slots)} (absorbed" in lv[0]["reason"]
    f = _of(sh, "DIP_424F")
    carried = [e for e in f if e["event"] == "ENTRY"]
    assert [T.parse(e["trade_id"])["slot"] for e in carried] == slots, "the shadow carries them"
    live_ev, f_ev = [], []
    for d in S.WALK_DAYS[i + 1:]:
        a, b = _tick(paths, at(d, 9, 35, 5), live, shadow)
        live_ev += a
        f_ev += _of(b, "DIP_424F")
    carried_ids = {e["trade_id"] for e in carried}
    f_exit_of_carry = {T.parse(e["trade_id"])["slot"]: pd.Timestamp(e["ref_time"])
                       for e in f_ev if e["event"] == "EXIT" and e["trade_id"] in carried_ids}
    assert f_exit_of_carry, "at least one absorbed position closes inside the fixture"
    # the live rows are DIP_424F's rows minus its carries' exits -- same trades, same prices
    f_new = [e for e in f_ev if e["trade_id"] not in carried_ids]
    assert sorted(map(_shape, live_ev)) == sorted(map(_shape, f_new))
    assert live_ev, "the live leg trades after the seed"
    # never an EXIT for an absorbed position; every live EXIT closes a live ENTRY
    live_entries = {e["trade_id"] for e in live_ev if e["event"] == "ENTRY"}
    assert {e["trade_id"] for e in live_ev if e["event"] == "EXIT"} <= live_entries
    # an absorbed slot sits out until its absorbed position has exited
    for e in live_ev:
        slot = T.parse(e["trade_id"])["slot"]
        if e["event"] == "ENTRY" and slot in slots:
            assert slot in f_exit_of_carry and pd.Timestamp(e["ref_time"]) >= f_exit_of_carry[slot], \
                (slot, e["ref_time"])
    st = _state(paths["state_path"])["legs"][LIVE]
    for g in open_now:
        rec = st["trades"][T.make(LIVE, f"{S.WALK_DAYS[g[1]].isoformat()}T09:30:00-04:00", "long", slot=g[0])]
        assert rec["seeded"] and rec["exit_emitted"] and "seeded_open" not in rec


# ── 5. the 25-minute entry age ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("hh, mm, ss, emitted", [(9, 54, 55, True), (9, 55, 6, False)])
def test_a_live_entry_first_seen_25_minutes_after_its_0930_bar_is_late(tmp_path, offline, hh, mm, ss,
                                                                        emitted):
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live, shadow = _legs(paths["home"])
    _tick(paths, at(D_CRASH, 17, 0), live, shadow)                     # the SEED, flat
    lv, sh = _tick(paths, at(D_ENTRY, hh, mm, ss), live, shadow)
    assert len(_of(sh, "DIP_424F")) == 7, "the shadow legs keep the whole session"
    ls = _state(paths["state_path"])["legs"][LIVE]
    if emitted:
        assert [e["event"] for e in lv] == ["ENTRY"] * 7 and "late_skipped" not in ls
        return
    assert lv == [] and ls["late_skipped"] == 7
    assert all(r["skipped"] == "late" and r["exit_emitted"] for k, r in ls["trades"].items()
               if D_ENTRY.strftime("%Y%m%d") in k)
    # ... and its EXIT is suppressed with it the next morning (the executor never bought it)
    lv1, sh1 = _tick(paths, at(D_X1, 9, 35, 5), live, shadow)
    assert lv1 == [] and [e["event"] for e in _of(sh1, "DIP_424F")] == ["EXIT"]


# ── 6. the memo ────────────────────────────────────────────────────────────────────────────
def test_one_probe_serves_the_live_leg_and_both_shadow_legs(tmp_path, offline, monkeypatch):
    """Seven engine runs a session for all three DIP legs (one per mechanism), not 21: the live
    step computes the probe, both shadow legs hit its memo; the session's later bars cost none."""
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live, shadow = _legs(paths["home"])
    calls = []
    real = cs.engine_run_backtest
    monkeypatch.setattr(cs, "engine_run_backtest", lambda *a, **k: calls.append(1) or real(*a, **k))
    monkeypatch.setattr(DL, "PROBE_STATS", {"runs": 0, "hits": 0})
    seen = []
    real_pos = DL.dip_positions
    monkeypatch.setattr(DL, "dip_positions",
                        lambda series, params, strategy=DL.STRATEGY: seen.append(1) or real_pos(
                            series, params, strategy=strategy))
    per_tick = []
    for now in (at(D_ENTRY, 9, 30, 5), at(D_ENTRY, 9, 35, 5), at(D_ENTRY, 12, 0, 5),
                at(D_X1, 9, 35, 5)):
        n0, s0 = len(calls), len(seen)
        lv, sh = _tick(paths, now, live, shadow)
        per_tick.append((len(calls) - n0, len(seen) - s0))
    # every new session's first tick: 3 legs asked, 7 runs (the first leg), 2 memo hits
    assert per_tick == [(7, 3), (7, 3), (0, 3), (7, 3)], per_tick
    assert DL.PROBE_STATS == {"runs": 21, "hits": 9}, DL.PROBE_STATS


def test_the_live_fetch_frame_and_the_cache_it_wrote_give_one_memo_key(tmp_path, monkeypatch):
    """On the box the live step decides off fetch_and_merge's IN-MEMORY frame and the shadow step,
    moments later, off the CSV that call wrote: both must build the same daily series (else the
    shadow legs would rerun the probe). Through the real fetch_and_merge, with a Webull reply
    holding the new session's bars at full float precision."""
    paths = S.write_home(tmp_path, S.CRASH[:S.CRASH_AT + 1], 30)
    S.write_1d(paths, S.CRASH)
    fresh = S.session_bars(*S.CRASH[S.CRASH_AT + 1])          # D_ENTRY's bars, raw np floats
    monkeypatch.setattr(cs, "_fetch_webull", lambda tf, count=None, log=print: fresh.copy())
    monkeypatch.setattr(cs, "_wall_epoch", lambda: 10 ** 10)    # every row settled
    mem, src, ok = cs.fetch_and_merge("5m", paths, log=QUIET)
    assert src == "webull" and ok
    disk = cs.historical_bars("5m", paths)
    now = at(D_ENTRY, 9, 35, 5)
    params = dict(cs.CROWN_LEGS[LIVE]["params"])
    keys = []
    for frame in (mem, disk):
        arrays = cs.closed_arrays(frame, now, "5m", cs.leg_warmup_sessions(cs.CROWN_LEGS[LIVE]))
        series, why = DL.build_daily_series(arrays, now, paths, params, log=QUIET)
        assert why is None and series["dates"][-1] == D_ENTRY
        keys.append(DL._memo_key(DL.STRATEGY, params, series))
    assert keys[0] == keys[1]
    assert keys[0] == DL._memo_key(DL.STRATEGY, dict(cs.SHADOW_LEGS["DIP_424F"]["params"]), series)


# ── 7. the stream path ─────────────────────────────────────────────────────────────────────
def test_the_stream_path_never_decides_a_dip_leg_but_step_still_does(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(css, "_handle_handoff_window",
                        lambda now, five, paths, cfg, log: seen.setdefault("window", set(five)))
    monkeypatch.setattr(css, "_resolve_pending_against_rest",
                        lambda now, five, paths, log: seen.setdefault("pending", set(five)))
    monkeypatch.setattr(cs, "step", lambda **k: seen.setdefault("step", set(k.get("legs"))) and [])
    now = pd.Timestamp("2026-10-13 09:35:01", tz=cs.TZ).to_pydatetime()      # inside the window
    assert css.in_handoff_window(now)
    css.run_stream_aware_step(now=now, fetch=False, paths=cs._paths(home=str(tmp_path)), log=QUIET)
    assert seen["window"] == seen["pending"] == {"ORB_R6", "NOISE_382"}
    assert seen["step"] == set(cs.CROWN_LEGS) and LIVE in seen["step"]
    # any DIP runner leg, whatever its key, is left out
    other = {"X": dict(cs.SHADOW_LEGS["DIP_424F"]), "Y": dict(cs.CROWN_LEGS["ORB_R6"])}
    seen.clear()
    css.run_stream_aware_step(now=now, legs=other, fetch=False,
                              paths=cs._paths(home=str(tmp_path)), log=QUIET)
    assert seen["window"] == {"Y"} and seen["step"] == {"X", "Y"}


# ── 8. a live key never reaches the shadow store ──────────────────────────────────────────
def test_a_live_key_handed_to_the_shadow_step_is_never_stepped_there(tmp_path, offline, monkeypatch):
    """DIP_424 slipped into the dict the shadow step is handed: dropped (one log line a day), so
    no DIP_424 row or state ever lands in the shadow store; the shadow pair runs as always."""
    monkeypatch.setattr(cs, "_DAILY_CALIBRATION_LOG", {})
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live, shadow = _legs(paths["home"])
    bad = dict(shadow, **live)
    logs = []
    for now in (at(D_CRASH, 17, 0), at(D_ENTRY, 9, 35, 5)):
        cs.step(now=now, legs=live, paths=paths, fetch=True)
        cs.run_shadow_step(now=now, fetch=True, live_legs=live, shadow_legs=bad, live_paths=paths,
                           log=logs.append)
    sp = cs.shadow_paths(paths)
    assert _ledger_legs(sp["signals_path"]) == set(SHADOW)
    assert set(_state(sp["state_path"])["legs"]) == set(SHADOW)
    assert len([m for m in logs if "DIP_424 is a LIVE leg key" in m]) == 1, logs
    assert _ledger_legs(paths["signals_path"]) == {LIVE}
    assert len([r for r in S._rows(paths["signals_path"]) if r["event"] == "ENTRY"]) == 7
    # the shipped dicts never clash, so the default shadow step drops nothing
    assert not set(cs.SHADOW_LEGS) & set(cs.CROWN_LEGS)


# ── 9. the shipped live_since is a date gate ──────────────────────────────────────────────
def test_the_shipped_live_leg_does_nothing_before_2026_10_13(tmp_path, offline):
    """FIXER 10-10: a deploy that lands before the GO date (a weekend, Monday 10-12 before 09:25)
    must not seed DIP_424 at Monday's 09:30 and send real DIP orders a session early. Before its
    live_since the shipped leg emits nothing and writes no state at all (no stamp, no SEED, no
    last_bar_epoch), while the shadow pair runs as always; its cold start then lands on its first
    step from 2026-10-13, as the SEED TIME notes describe."""
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live = {LIVE: dict(cs.CROWN_LEGS[LIVE])}
    assert live[LIVE]["live_since"] == "2026-10-12" > D_X2.isoformat()
    shadow = S._dip_legs(paths["home"])
    for now in (at(D_CRASH, 17, 0), at(D_ENTRY, 9, 30, 5), at(D_ENTRY, 9, 35, 5),
                at(D_X1, 9, 35, 5)):
        lv, sh = _tick(paths, now, live, shadow)
        assert lv == []
    assert LIVE not in _state(paths["state_path"]).get("legs", {})
    assert not os.path.exists(paths["signals_path"]) or _ledger_legs(paths["signals_path"]) == set()
    assert _ledger_legs(cs.shadow_paths(paths)["signals_path"]) == set(SHADOW)
    import datetime as _d
    assert cs._before_live_since(live[LIVE], _d.datetime(2026, 10, 9, 15, 59, tzinfo=cs._zi(cs.TZ)))
    assert not cs._before_live_since(live[LIVE], _d.datetime(2026, 10, 12, 10, 45, 5,
                                                                tzinfo=cs._zi(cs.TZ)))


# ── 10. a live DIP leg that is not ready is never silent ──────────────────────────────────
def test_a_live_dip_leg_that_is_not_ready_pages_once_a_day_and_a_shadow_leg_never(
        tmp_path, offline, monkeypatch):
    """FIXER 10-10: the live leg holds real shares overnight and its exits come only from its
    runner -- a daily series that stays not ready (a hole, a calibration failure, a QQQ_1d.csv
    too short) or a runner that raises used to leave one log line a day and nothing else. Now
    step()'s warnings name it every time, and from 09:40 one high phone note a day goes out (only
    on a live fetch tick on the box, like every engine page); a shadow leg never pages. (A
    MISSING or EMPTY QQQ_1d.csv is the box monitor's page and only recorded here -- QQQ_1d
    MISSING: ONE PAGER, tests/test_cloud_signal_qqq_1d_one_pager.py.)"""
    from api import ntfy_push
    paths = S.write_home(tmp_path, S.CRASH, 30,                      # QQQ_1d present, 200 rows:
                         keep_1d={t[0] for t in S.CRASH[-200:]})     # too short (needs 430)
    live, shadow = _legs(paths["home"])
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    monkeypatch.setattr(cs, "_LIVE_NOT_READY_NOTED", {})
    pushes = []
    monkeypatch.setattr(cs, "_engine_push_background",
                        lambda msg, title, priority="high", paths=None, log=print:
                        pushes.append({"title": title, "message": msg, "priority": priority})
                        or "background")
    w = {}
    assert cs.step(now=at(D_ENTRY, 9, 35, 5), legs=live, paths=paths, fetch=True, warnings=w) == []
    assert w["legs_not_ready"][LIVE]["reason"] == "short" and pushes == [], "not before 09:40"
    for mm in (40, 45, 50):
        w = {}
        assert cs.step(now=at(D_ENTRY, 9, mm, 5), legs=live, paths=paths, fetch=True,
                       warnings=w) == []
        assert w["legs_not_ready"][LIVE]["reason"] == "short"
    (p,) = pushes
    assert p["title"] == "DIP #424: not trading" and p["priority"] == "high"
    assert ntfy_push.lint(p) == [] and "AFFECTED" in p["message"]
    assert p["message"].split("\n")[:2] == [
        "Trading: AFFECTED - DIP #424 takes no new trades and sends no exit for its held shares.",
        "Its daily QQQ price history is too short."]
    # a shadow leg in the same state never pages, even on a fetching step
    sp = cs.shadow_paths(paths)
    w = {}
    assert cs.step(now=at(D_ENTRY, 9, 55, 5), legs=shadow, paths=sp, fetch=True, warnings=w) == []
    assert "legs_not_ready" not in w and len(pushes) == 1
    # a replay / offline step (fetch=False) never pages either
    monkeypatch.setattr(cs, "_LIVE_NOT_READY_NOTED", {})
    cs.step(now=at(D_ENTRY, 10, 0, 5), legs=live, paths=paths, fetch=False)
    assert len(pushes) == 1
    # ready again: the live leg seeds as before
    S.write_1d(paths, S.CRASH)
    lv = cs.step(now=at(D_ENTRY, 10, 5, 5), legs=live, paths=paths, fetch=True)
    assert [e["event"] for e in lv] == ["SEED"] and len(pushes) == 1


def test_a_live_dip_runner_that_raises_is_named_in_the_warnings(tmp_path, offline, monkeypatch):
    paths = S.write_home(tmp_path, S.CRASH, 30)
    live, _shadow = _legs(paths["home"])

    def boom(*a, **k):
        raise RuntimeError("probe broke")
    monkeypatch.setattr(DL, "dip_positions", boom)
    w = {}
    assert cs.step(now=at(D_ENTRY, 9, 45, 5), legs=live, paths=paths, fetch=True, warnings=w) == []
    assert w["legs_not_ready"][LIVE]["reason"] == "error"
    assert "probe broke" in w["legs_not_ready"][LIVE]["text"]

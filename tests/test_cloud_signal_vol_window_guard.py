"""api/cloud_signal.py -- the VOL WINDOW GUARD (MANAGER GO 2026-10-25).

NOISE_382's vol skip (augur_strategies/NOISE_1_0.py _vol_percentile, vol_skip_pct 95) ranks the
judged session against the REQUIRED_LOOKBACK_SESSIONS (252) sessions before it; the box's 5m
cache holds ~94, so the vol_prior_ranges daily bridge tops it up. When the bridge passes nothing
the skip silently ranks on the short 5m window (~3.6% of sessions flip on full history). The
guard, pinned here:

  1. run_leg_trades stashes what the bridge already decided (no second bridge run), and step()
     publishes it AFTER the rows in warnings["vol_window"]: bridge OK -> a full window, no page;
     every way the bridge can pass nothing (QQQ_1d.csv missing, no finished day, no valid / thin
     overlap, a ratio out of band, nothing older than the 5m window, an error) or a daily file
     too short -> short, with the reason;
  2. a short window sends ONE default plain phone note per LIVE leg per ET session day (from
     09:40 until the close, never on the EOD SETTLE step, only on a live fetching tick on the
     box), worded "Trading: AFFECTED" -- never for a shadow leg, never twice the same day (a
     restart included; one phone_dedupe.json write, the in-process memo holds the rest), again
     the next session day; under the skip's own floor (NOISE_1_0 VOL_SKIP_LOOKBACK_SESSIONS, 60
     -- where _vol_percentile is NaN) the note says the check is OFF, not what it ranks on;
  3. a broken guard logs and the step carries on; signals.csv, state.json and the
     vol_prior_ranges each engine call is handed are the same with and without the guard;
  4. the live thread puts the status on its heartbeat, run_shadow_step on the shadow heartbeat
     (tools/webull_freshness.py reads both -- tests/test_webull_freshness_vol_window.py).

No network: every fetch is a stub, the push is a recorder, every store is under tmp_path. The
synthetic bars and stub strategy are tests/test_cloud_signal_stream_parity.py's.
"""
import importlib.util
import json
import os
import threading

import pandas as pd
import pytest

from api import cloud_signal as cs
from api import cloud_signal_stream as css
from api import ntfy_push

_spec = importlib.util.spec_from_file_location(
    "stream_parity_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_cloud_signal_stream_parity.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

DAY = P.DAY                        # 2026-09-08, a Tuesday: the session being traded
DAY2 = "2026-09-09"                # the next session day
LIVE, SHADOW = "NOISE_382", "NOISE_422_PLAIN"
NEED = 252
N_SESSIONS = 95                    # 94 through DAY (= the box's ~94) + DAY2


def _quiet(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def _fresh_memos(monkeypatch):
    """The guard's in-process memos and the bridge's once-a-day log latch, empty per test."""
    monkeypatch.setattr(cs, "_VOL_WINDOW_STASH", {})
    monkeypatch.setattr(cs, "_VOL_WINDOW_NOTED", {})
    cs._DAILY_CALIBRATION_LOG.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()


@pytest.fixture
def box(monkeypatch):
    """The cloud box, offline: a fetch reads the on-disk cache back, every real network path
    raises, and the engine's background push is recorded instead of sent."""
    def boom(*a, **k):
        raise AssertionError("network touched")

    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print: (cs.historical_bars(tf, paths), "webull", True))
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_fetch_webull", boom)
    monkeypatch.setattr(cs.qp, "_fetch_yf", boom)
    monkeypatch.setattr(cs, "_fetch_yf_daily", boom)
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    sent = []

    def fake_push(msg, title, priority="high", paths=None, log=print):
        sent.append({"title": title, "message": msg, "priority": priority, "paths": paths})
        return "background"

    monkeypatch.setattr(cs, "_engine_push_background", fake_push)
    return sent


def _df5():
    return P._5m_frame(P._sessions(N_SESSIONS, last=DAY2), bars_per_day=12)


def _home(tmp_path, name="home", daily="ok", df5=None):
    """A store with 95 5m sessions through DAY2 and a QQQ_1d.csv per `daily`: "ok" (170 daily-only
    sessions before the 5m window -> a full 252), None (no file), or a DataFrame."""
    df5 = _df5() if df5 is None else df5
    if isinstance(daily, str) and daily == "ok":
        daily = P._daily_frame(df5, n_prior=170, exclude=DAY2)
    return P._home(tmp_path, df5, name, daily=daily)


def _legs(decisions=None, shadow=False):
    legs = {LIVE: P._cfg(P._stub(decisions, lookback=NEED, vpr=True), warmup_sessions=5)}
    if shadow:
        legs[SHADOW] = P._cfg(P._stub(decisions, lookback=NEED, vpr=True), warmup_sessions=5,
                              shadow=True)
    return legs


def _at(hhmm, day=DAY):
    """step()'s `now` just after the bar starting at hhmm closed (the stream helper's)."""
    return P._eff(hhmm, day)


def _step(paths, legs, hhmm, day=DAY, fetch=True):
    w = {}
    events = cs.step(now=_at(hhmm, day), legs=legs, paths=paths, fetch=fetch, warnings=w)
    return events, w


# -- 1. what the guard publishes ------------------------------------------------------------
def test_bridge_ok_publishes_a_full_window_and_never_pages(tmp_path, box):
    paths = _home(tmp_path)
    legs = _legs()
    for hhmm in ("09:30", "09:35", "09:40"):
        _events, w = _step(paths, legs, hhmm)
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["day"] == DAY and e["need"] == NEED and e["have"] == NEED
    assert e["depth_5m"] == 92 and e["bridged"] == 170
    assert e["short"] is False and e["reason_key"] == "ok" and e["reason"] == "ok"
    assert e["shadow"] is False and e["pushed"] is None
    assert box == []
    assert not os.path.exists(os.path.join(paths["state_dir"], cs.PHONE_DEDUPE_FILE))


def _drop_prior(daily, df5):
    first = pd.to_datetime(df5["time"].min(), unit="s", utc=True).tz_convert(cs.TZ).date()
    d = pd.to_datetime(daily["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    return daily[d >= first].reset_index(drop=True)


def _thin(daily, df5):
    """Every daily-only prior session, but only the 10 overlap sessions right before DAY."""
    first = pd.to_datetime(df5["time"].min(), unit="s", utc=True).tz_convert(cs.TZ).date()
    d = pd.to_datetime(daily["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    overlap = sorted(x for x in d if first <= x < pd.Timestamp(DAY).date())
    keep = (d < first) | d.isin(overlap[-10:])
    return daily[keep].reset_index(drop=True)


def _scaled(daily, k=3.0):
    """Every daily (H-L)/C k times wider: 5m/daily ratio 1/k, outside [0.8, 1.25]."""
    out = daily.copy()
    r = (out["high"] - out["low"]) / out["close"]
    out["high"] = out["close"] * (1 + k * r / 2)
    out["low"] = out["close"] * (1 - k * r / 2)
    return out


def _from_today(daily):
    d = pd.to_datetime(daily["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    return daily[d >= pd.Timestamp(DAY).date()].reset_index(drop=True)


@pytest.mark.parametrize("case, reason_key, bridged", [
    ("missing", "missing_cache", 0),
    ("no_finished", "no_finished", 0),
    ("thin", "thin_overlap", 0),
    ("ratio", "ratio_out_of_band", 0),
    ("no_prior", "no_prior_daily", 0),
    ("short_depth", "short_depth", 100),
    ("error", "error", 0),
])
def test_every_way_the_bridge_passes_nothing_reads_short(tmp_path, box, monkeypatch, case,
                                                         reason_key, bridged):
    df5 = _df5()
    full = P._daily_frame(df5, n_prior=170, exclude=DAY2)
    daily = {"missing": None, "no_finished": _from_today(full), "thin": _thin(full, df5),
             "ratio": _scaled(full), "no_prior": _drop_prior(full, df5),
             "short_depth": P._daily_frame(df5, n_prior=100, exclude=DAY2),
             "error": full}[case]
    if case == "error":
        def broken(_df):
            raise ValueError("garbled daily file")
        monkeypatch.setattr(cs, "_daily_ranges_by_date", broken)
    paths = _home(tmp_path, case, daily=daily, df5=df5)
    _events, w = _step(paths, _legs(), "09:30", fetch=False)
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["short"] is True and e["reason_key"] == reason_key, e
    assert e["bridged"] == bridged and e["depth_5m"] == 92
    assert e["have"] == 92 + bridged and e["need"] == NEED
    assert e["reason"] == cs._VOL_WINDOW_WORDS[reason_key]
    assert box == [], "a fetch=False step never pages"


def test_a_leg_that_does_not_use_the_bridge_publishes_nothing(tmp_path, box):
    paths = _home(tmp_path, daily=None)
    legs = {"ORB_STUB": P._cfg(P._stub(lookback=NEED), warmup_sessions=5)}   # no vol_prior_ranges
    _events, w = _step(paths, legs, "09:40")
    assert cs.VOL_WINDOW_KEY not in w and box == [] and cs._VOL_WINDOW_STASH == {}


def test_the_stream_dry_run_stashes_the_window_too(tmp_path, box):
    """With bar_close_from_stream on, step() never re-runs the engine for a committed bar -- so
    the status is captured in run_leg_trades, which the stream's dry run reaches too."""
    paths = _home(tmp_path, daily=None)
    cfg = _legs()[LIVE]
    df = cs.historical_bars("5m", paths)
    css._dry_run_decision(LIVE, cfg, df, _at("10:00"), {"trades": {}}, "stream", _quiet,
                          paths=paths)
    rec = cs._VOL_WINDOW_STASH[LIVE]
    assert rec["reason_key"] == "missing_cache" and rec["day"] == DAY and rec["depth_5m"] == 92


# -- 2. the phone note -----------------------------------------------------------------------
def test_missing_daily_bars_page_once_a_day_for_the_live_leg_only(tmp_path, box, monkeypatch):
    paths = _home(tmp_path, daily=None)
    legs = _legs(shadow=True)
    dedupe_io = []                                 # phone_dedupe.json read+writes (_engine_note)
    real_update = cs._phone_update

    def counted(*a, **k):
        dedupe_io.append(1)
        return real_update(*a, **k)

    monkeypatch.setattr(cs, "_phone_update", counted)

    _events, w = _step(paths, legs, "09:30")                       # 09:35 -- before 09:40
    assert w[cs.VOL_WINDOW_KEY][LIVE]["short"] is True and box == [], "not before 09:40"

    _events, w = _step(paths, legs, "09:35")                       # 09:40
    (p,) = box
    note = {k: p[k] for k in ("title", "message", "priority")}
    assert ntfy_push.lint(note) == []
    assert note["title"] == "NOISE: vol-skip check short" and note["priority"] == "default"
    assert note["message"] == (
        "Trading: AFFECTED - NOISE may trade, or skip, today unlike the backtest "
        "(signals still run).\n"
        "NOISE's vol-skip check is short today: daily bars missing - the skip ranks on 92 "
        "sessions, not 252.\n"
        "Do: ask Claude (PAPER-WB chat) to check the daily QQQ bars today.")
    assert p["paths"] == paths                                     # step()'s own store
    assert w[cs.VOL_WINDOW_KEY][LIVE]["pushed"] == DAY
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["off"] is False and e["min_obs"] == 60                # 92 sessions: ranks, not off
    sh = w[cs.VOL_WINDOW_KEY][SHADOW]
    assert sh["short"] is True and sh["shadow"] is True and sh["pushed"] is None

    for hhmm in ("09:40", "10:15"):                                # the same day: no second note
        _events, w = _step(paths, legs, hhmm)
    assert len(box) == 1
    # the in-process memo, not only the repeat rule, holds it: no phone_dedupe.json write per
    # tick after the page, and the heartbeat keeps saying the note went out
    assert len(dedupe_io) == 1, f"{len(dedupe_io)} phone_dedupe.json read+writes in one morning"
    assert w[cs.VOL_WINDOW_KEY][LIVE]["pushed"] == DAY
    cs._VOL_WINDOW_NOTED.clear()                                   # a restart the same day
    _step(paths, legs, "10:20")
    assert len(box) == 1, "the repeat rule (phone_dedupe.json) holds it across a restart"

    _step(paths, legs, "09:30", day=DAY2)
    _step(paths, legs, "09:40", day=DAY2)                          # the next session day
    assert len(box) == 2 and "ranks on 93 sessions, not 252" in box[1]["message"]


def test_no_page_off_the_box_or_on_an_offline_step(tmp_path, box, monkeypatch):
    paths = _home(tmp_path, daily=None)
    legs = _legs()
    _step(paths, legs, "09:45", fetch=False)                       # a replay / stream dry run
    assert box == []
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "pc")                  # the PC runner
    _step(paths, legs, "09:50")
    assert box == []
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    _step(paths, legs, "09:55")
    assert len(box) == 1


def test_a_shadow_leg_never_pages_even_on_a_fetching_step(tmp_path, box):
    paths = _home(tmp_path, daily=None)
    shadow_only = {SHADOW: _legs(shadow=True)[SHADOW]}
    _events, w = _step(cs.shadow_paths(paths), shadow_only, "09:45")
    assert w[cs.VOL_WINDOW_KEY][SHADOW]["short"] is True and box == []


def test_the_bridge_back_clears_the_status_without_a_second_page(tmp_path, box):
    df5 = _df5()
    paths = _home(tmp_path, daily=None, df5=df5)
    legs = _legs()
    _step(paths, legs, "09:40")
    assert len(box) == 1
    P._daily_frame(df5, n_prior=170, exclude=DAY2).to_csv(cs._cache_path("1d", paths), index=False)
    _events, w = _step(paths, legs, "09:45")                       # the next new bar
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["short"] is False and e["have"] == NEED and len(box) == 1


@pytest.mark.parametrize("off", [False, True])
@pytest.mark.parametrize("key", sorted(cs._VOL_WINDOW_WORDS))
def test_every_reason_reads_as_a_clean_phone_note(key, off):
    e = {"reason": cs._VOL_WINDOW_WORDS[key], "have": 48 if off else 92, "need": 252,
         "min_obs": 60, "off": off}
    note = cs._vol_window_note(LIVE, e)
    assert ntfy_push.lint(note) == [], (key, note)
    assert note["message"].startswith("Trading: AFFECTED - NOISE may trade")
    assert note["priority"] == "default"


def test_no_page_after_the_close_but_the_status_still_publishes(tmp_path, box, monkeypatch):
    """The EOD SETTLE step (post_close) and any tick at or after the bell leave no NOISE
    decision today: the status is published, the note is not sent. The post_close flag holds
    it on its own too (a calendar that cannot name today's close)."""
    legs = _legs()
    after = P._eff("15:55") + cs._dt.timedelta(minutes=3)          # 16:0x, the settle tick
    real_close = cs._at_or_after_session_close
    for name, post_close, close_known in (("settle", True, True), ("late", False, True),
                                          ("settle_no_close", True, False)):
        cs._VOL_WINDOW_NOTED.clear()
        monkeypatch.setattr(cs, "_at_or_after_session_close",
                            real_close if close_known else (lambda now: False))
        paths = _home(tmp_path, name, daily=None)
        w = {}
        cs.step(now=after, legs=legs, paths=paths, fetch=True, warnings=w, post_close=post_close)
        assert w[cs.VOL_WINDOW_KEY][LIVE]["short"] is True, name
        assert w[cs.VOL_WINDOW_KEY][LIVE]["pushed"] is None and box == [], name
    monkeypatch.setattr(cs, "_at_or_after_session_close", real_close)
    cs._VOL_WINDOW_NOTED.clear()
    paths = _home(tmp_path, "inside", daily=None)
    _step(paths, legs, "15:45")                                    # 15:50: still in the session
    assert len(box) == 1


# -- the skip's own floor: under min_obs it is OFF, not short ----------------------------------
def test_the_floor_is_noise_1_0s_own_and_is_found_down_the_base_chain():
    from augur_strategies import NOISE_1_0
    assert cs.VOL_SKIP_MIN_OBS_DEFAULT == NOISE_1_0.VOL_SKIP_LOOKBACK_SESSIONS == 60
    # the live leg's wrapper (NOISE_1_8_CT304 -> NOISE_1_1_NBHD -> NOISE_1_0) re-exports only
    # REQUIRED_LOOKBACK_SESSIONS: the floor is read off the bottom of the chain
    assert cs.vol_skip_min_obs(cs.CROWN_LEGS[LIVE]["strategy"]) == 60
    base = P._stub(lookback=NEED, vpr=True)
    base.VOL_SKIP_LOOKBACK_SESSIONS = 40
    top = P._stub(lookback=NEED, vpr=True)
    top._base = base
    assert cs.vol_skip_min_obs(top) == 40
    assert cs.vol_skip_min_obs(P._stub(lookback=NEED, vpr=True)) == 60   # declares nothing
    assert cs.vol_skip_min_obs("NO_SUCH_STRATEGY.py") == 60             # never raises


@pytest.mark.parametrize("n_sess", [61, 62, 63])
def test_off_is_exactly_where_noise_1_0_returns_nan(n_sess):
    """The guard's `off` against the real _vol_percentile on a 5m-only window of n sessions:
    the judged (last) session's percentile is NaN (the skip never fires) iff the entry says off."""
    import numpy as np
    from augur_strategies import NOISE_1_0
    bars = 3
    rng = np.random.default_rng(n_sess)
    c = 500.0 * (1 + rng.normal(0, 0.002, n_sess * bars)).cumprod()
    h, lo = c * 1.001, c * 0.999
    bounds = [(i * bars, (i + 1) * bars) for i in range(n_sess)]
    pct = NOISE_1_0._vol_percentile(h, lo, c, bounds)
    days = cs.market_calendar.sessions_between(pd.Timestamp("2026-01-02").date(),
                                               pd.Timestamp("2026-12-31").date())[:n_sess]
    arrays = {"day_id": np.repeat(np.arange(n_sess), bars),
              "index": [pd.Timestamp(f"{d} 09:30", tz=cs.TZ) for d in days for _ in range(bars)]}
    cs._stash_vol_window(LIVE, arrays, _at("10:00"), 0,
                         {"required": NEED, "key": "missing_cache", "text": "x"},
                         strategy=cs.CROWN_LEGS[LIVE]["strategy"])
    e = cs._vol_window_entry(LIVE, cs._VOL_WINDOW_STASH[LIVE], {})
    assert e["have"] == e["depth_5m"] == n_sess - 2 and e["short"] is True
    assert e["off"] is bool(np.isnan(pct[-1])), (n_sess, pct[-1])


@pytest.mark.parametrize("case", ["missing", "thin"])
def test_under_the_floor_the_note_says_the_check_is_off(tmp_path, box, case):
    """A 5m cache rebuilt short with no daily file, or a complete daily file whose overlap
    with a ~20-session 5m window is under 20 (thin_overlap): under 60 sessions the skip is
    OFF -- the note says so, never "ranks on 18 sessions"."""
    n = {"missing": 50, "thin": 21}[case]
    df5 = P._5m_frame(P._sessions(n, last=DAY2), bars_per_day=12)
    daily = None if case == "missing" else P._daily_frame(df5, n_prior=300, exclude=DAY2)
    paths = _home(tmp_path, case, daily=daily, df5=df5)
    _events, w = _step(paths, _legs(), "09:35")
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    have = n - 1 - 2                                   # the sessions through DAY, minus two
    assert e["reason_key"] == {"missing": "missing_cache", "thin": "thin_overlap"}[case], e
    assert e["have"] == have and e["off"] is True and e["min_obs"] == 60
    (p,) = box
    assert p["title"] == "NOISE: vol-skip check off" and p["priority"] == "default"
    assert p["message"].split("\n")[:2] == [
        "Trading: AFFECTED - NOISE may trade a day the backtest skips (signals still run).",
        f"NOISE's vol-skip check is off today: {cs._VOL_WINDOW_WORDS[e['reason_key']]} - it has "
        f"{have} sessions and needs 60 to work."]
    assert ntfy_push.lint({k: p[k] for k in ("title", "message", "priority")}) == []


# -- 3. never changes a signal ----------------------------------------------------------------
def _guard_off(monkeypatch):
    monkeypatch.setattr(cs, "_stash_vol_window", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_note_vol_window", lambda *a, **k: None)


def _walk(paths, legs, hhmms=None):
    out = []
    for hhmm in hhmms or P._hhmms("09:30", "10:25"):
        events, _w = _step(paths, legs, hhmm)
        out.append(P._strip(events))
    return out


def _stub_legs(decisions):
    """_legs() with a handle on the stub, whose .calls record what each engine call was handed."""
    stub = P._stub(decisions, lookback=NEED, vpr=True)
    return stub, {LIVE: P._cfg(stub, warmup_sessions=5)}


def _ledger_without_emitted_at(paths):
    """signals.csv with its emitted_at column (the WALL clock, not `now`) blanked."""
    with open(paths["signals_path"], encoding="utf-8") as f:
        lines = f.read().splitlines()
    head = lines[0].split(",")
    assert head[0] == "emitted_at"
    return [lines[0]] + ["," + ln.split(",", 1)[1] for ln in lines[1:]]


@pytest.mark.parametrize("daily", ["ok", None])
def test_signals_and_state_are_identical_with_and_without_the_guard(tmp_path, box, monkeypatch,
                                                                    daily):
    decisions = {f"{DAY} 09:45": "long", f"{DAY} 10:05": "exit"}
    on = _home(tmp_path, "on", daily=daily)
    stub_on, legs_on = _stub_legs(decisions)
    events_on = _walk(on, legs_on)
    if daily is None:
        assert len(box) == 1                                       # the guard really ran
    _guard_off(monkeypatch)
    off = _home(tmp_path, "off", daily=daily)
    stub_off, legs_off = _stub_legs(decisions)
    events_off = _walk(off, legs_off)
    # the engine's INPUT too: the stub ignores vol_prior_ranges, so the rows alone could not
    # show a guard that rewrote the list the engine is handed
    vpr_on, vpr_off = [c["vpr"] for c in stub_on.calls], [c["vpr"] for c in stub_off.calls]
    assert vpr_on and vpr_on == vpr_off
    if daily == "ok":
        assert all(isinstance(v, list) and len(v) == 170 for v in vpr_on)
    else:
        assert all(v is None for v in vpr_on)
    assert events_on == events_off
    assert any(e["event"] == "ENTRY" for evs in events_on for e in evs)
    assert _ledger_without_emitted_at(on) == _ledger_without_emitted_at(off)
    with open(on["state_path"], "rb") as f_on, open(off["state_path"], "rb") as f_off:
        assert f_on.read() == f_off.read(), "state.json byte-identical"


def test_a_broken_guard_logs_and_the_step_carries_on(tmp_path, box, monkeypatch, capsys):
    decisions = {f"{DAY} 09:45": "long", f"{DAY} 10:05": "exit"}
    ref = _home(tmp_path, "ref", daily=None)
    events_ref = _walk(ref, _legs(decisions))

    class Broken(dict):
        def __setitem__(self, k, v):
            raise RuntimeError("stash broke")

    def boom(*a, **k):
        raise RuntimeError("entry broke")

    monkeypatch.setattr(cs, "_VOL_WINDOW_STASH", Broken())
    monkeypatch.setattr(cs, "_VOL_WINDOW_NOTED", {})
    monkeypatch.setattr(cs, "_vol_window_entry", boom)
    box.clear()
    broken = _home(tmp_path, "broken", daily=None)
    events = _walk(broken, _legs(decisions))
    assert events == events_ref
    assert _ledger_without_emitted_at(broken) == _ledger_without_emitted_at(ref)
    out = capsys.readouterr().out
    assert "vol window record failed (RuntimeError: stash broke)" in out
    assert box == []

    # the publish half failing on its own (a stash that works, an entry that cannot be built)
    monkeypatch.setattr(cs, "_VOL_WINDOW_STASH", {})
    monkeypatch.setattr(cs, "_VOL_WINDOW_NOTED", {})
    again = _home(tmp_path, "again", daily=None)
    legs, w = _legs(decisions), {}
    events = [P._strip(cs.step(now=_at(hhmm), legs=legs, paths=again, fetch=True, warnings=w))
              for hhmm in ("09:30", "09:35", "09:40")]
    assert events == events_ref[:3] and box == []
    assert cs.VOL_WINDOW_KEY not in w
    out = capsys.readouterr().out
    assert "vol window note failed (RuntimeError: entry broke)" in out
    assert "vol window status failed (RuntimeError: entry broke)" in out


# -- 4. the heartbeats --------------------------------------------------------------------------
def test_the_shadow_heartbeat_carries_the_shadow_legs_status(tmp_path, box):
    paths = _home(tmp_path, daily=None)
    shadow_legs = {SHADOW: _legs(shadow=True)[SHADOW]}
    cs.run_shadow_step(now=_at("09:45"), fetch=False, live_legs={}, shadow_legs=shadow_legs,
                       live_paths=paths, log=_quiet)
    with open(cs.shadow_paths(paths)["heartbeat_path"], encoding="utf-8") as f:
        hb = json.load(f)
    e = hb[cs.VOL_WINDOW_KEY][SHADOW]
    assert e["short"] is True and e["shadow"] is True and e["reason_key"] == "missing_cache"
    assert hb["ok"] is True and box == []


def test_the_live_thread_puts_the_status_on_its_heartbeat(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "live"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "CROWN_LEGS", {})
    monkeypatch.setattr(cs, "SHADOW_LEGS", {})
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: False)
    monkeypatch.setattr(cs.market_calendar, "is_session", lambda d: True)
    monkeypatch.setattr(cs.market_calendar, "session_close_et", lambda d: "16:00")
    monkeypatch.setattr(cs, "RTH_OPEN", cs._dt.time(0, 0))
    monkeypatch.setattr(cs, "RTH_CLOSE", cs._dt.time(23, 59, 59))
    entry = {"day": DAY, "need": NEED, "have": 92, "short": True, "reason_key": "missing_cache"}

    def fake_step(now=None, legs=None, paths=None, fetch=True, warnings=None, **kw):
        warnings[cs.VOL_WINDOW_KEY] = {LIVE: entry}
        return []

    stop = threading.Event()
    monkeypatch.setattr(cs, "step", fake_step)
    monkeypatch.setattr(cs._time, "sleep", lambda s: stop.set())   # one loop, then stop
    cs._engine_thread_run(stop=stop, log=_quiet)
    with open(paths["heartbeat_path"], encoding="utf-8") as f:
        hb = json.load(f)
    assert hb["ok"] is True and hb[cs.VOL_WINDOW_KEY] == {LIVE: entry}

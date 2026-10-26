r"""QQQ_1d STALE: TRUE IMPACT (MANAGER GO 2026-10-25) -- what a QQQ_1d.csv that HAS rows but lacks
the newest sessions really does, proved on the box's real bars.

The box monitor's stale qqq_1d note (tools/webull_freshness.py, the 09:40 session check and the
pre-open gate's out-of-date miss) used to say "NOISE trades on a price history that is a day
short". The engine's code says otherwise, and this file pins what it does instead:

  1. NOISE_382 (api/cloud_signal vol_prior_ranges_for_leg): the daily bars it adds to its vol
     skip are the sessions BEFORE the 5m window -- the very same dates with the file one or two
     sessions short -- each times ONE scale (the median 5m/daily range ratio over the sessions
     both files hold, which loses the lacking ones). So the short file's list is the full one's
     times one factor; on the box's bars (a sweep of the 72 sessions 07-10..10-20, one and two
     short; 10-20 and 09-09 are pinned below) that factor moved under 1e-4, the skip never
     flipped and NOISE's and DIP's trades never changed. The rank
     itself CAN move: 09-09 with two sessions short, yesterday's rank 22.6 -> 22.2 (one bridged
     session crossed it) -- far from the 95 line, the same trades. A skip changes only when that
     rank sits right at the line, which the code cannot rule out: the monitor's note stays loud.
  2. DIP_424 (api/dip_live build_daily_series): every row comes from the 5m cache when that
     session is whole there, so with the lacking sessions whole the daily series -- every price,
     every source -- and the trades are the same.
  3. a lacking session only PART-way in the 5m cache: DIP's row is that partial session instead
     of the official daily bar. Real case: 10-15 cut after its 15:45 high, judged 10-16 -- the
     full file keeps the STREAK lot open, the short file EXITS it at the 10-16 open.
  4. a lacking session NOT in the 5m cache: DIP is not ready ("prev_missing": no entry, no exit),
     and that note pages (the file has rows -- it is not the record-only missing/empty cause).
  5. the monitor's words (qqq_1d_stale) name the case the engine is in, on the same files.
  6. the one quiet case's premise: today's rank reads the daily bars unless the 5m window holds
     253+ sessions before today, and the window counts the sessions really in the cache (a hole
     shortens it) -- so the monitor says "not affected" only off its counted list.

Fixture: tests/fixtures/qqq_1d_stale/ -- the box's own QQQ_5m.csv (94 whole sessions 2026-06-08 ..
10-20) and QQQ_1d.csv (2021-09-27 .. 10-19), as of 2026-10-20 evening. No network, no live file:
every store is under tmp_path, nothing is fetched (fetch=False).
"""
import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

from api import cloud_signal as cs
from api import dip_live as DL
from augur_strategies import NOISE_1_0 as N0
import tools.webull_freshness as wf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "qqq_1d_stale")
TZ = cs._zi(cs.TZ)
MON, FRI, THU = dt.date(2026, 10, 19), dt.date(2026, 10, 16), dt.date(2026, 10, 15)

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def _quiet(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def _fresh_memos(monkeypatch):
    for name in ("_VOL_WINDOW_STASH", "_VOL_WINDOW_NOTED", "_LIVE_NOT_READY_NOTED",
                 "_QQQ_1D_RECORDED"):
        monkeypatch.setattr(cs, name, {})
    cs._DAILY_CALIBRATION_LOG.clear()
    DL._PROBE_MEMO.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()
    DL._PROBE_MEMO.clear()


_BARS = {}


def _bars():
    if not _BARS:
        f5 = pd.read_csv(os.path.join(FIX, "QQQ_5m_20260608_20261020.csv.gz"))
        d1 = pd.read_csv(os.path.join(FIX, "QQQ_1d_20210927_20261019.csv.gz"))
        _BARS.update(
            f5=f5, d1=d1,
            t5=pd.to_datetime(f5["time"], unit="s", utc=True).dt.tz_convert(cs.TZ),
            d1_day=pd.to_datetime(d1["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date)
    return _BARS


def _at(day, hh=10, mm=0):
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)


def _home(tmp_path, name, daily_through, five=None):
    """A home whose QQQ_5m.csv is `five` (default: the whole fixture) and whose QQQ_1d.csv is the
    fixture's rows dated on or before `daily_through`."""
    b = _bars()
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    (b["f5"] if five is None else five).to_csv(cs._cache_path("5m", paths), index=False)
    b["d1"][b["d1_day"] <= daily_through].to_csv(cs._cache_path("1d", paths), index=False)
    return paths


def _arrays(cfg, paths, now):
    return cs.closed_arrays(cs.historical_bars("5m", paths), now, "5m", cs.leg_warmup_sessions(cfg))


def _noise(paths, now):
    """NOISE_382 as step() runs it (no fetch): the daily list its vol skip is handed, the scale,
    the overlap, today's rank of yesterday's range, and its trades."""
    cfg = cs.CROWN_LEGS["NOISE_382"]
    arrays = _arrays(cfg, paths, now)
    why = {}
    prior = cs.vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=False, log=_quiet,
                                        why_out=why)
    daily = cs._drop_unfinished_session_rows(cs.load_cached_bars("1d", paths), now, log=_quiet)
    ratio, overlap = cs._calibrate_daily_ranges(daily, arrays, now=now, log=_quiet)
    did = np.asarray(arrays["day_id"])
    starts = np.r_[0, np.flatnonzero(did[1:] != did[:-1]) + 1]
    bounds = list(zip(starts, np.r_[starts[1:], len(did)]))
    pct = N0._vol_percentile(np.asarray(arrays["high"], float), np.asarray(arrays["low"], float),
                             np.asarray(arrays["close"], float), bounds, prior_ranges=prior)
    trades, _ = cs.leg_decision_trades(cfg, arrays, "NOISE_382", "5m", now, paths, False,
                                       log=_quiet)
    first = arrays["index"][0].date()
    return {"why": why.get("key"), "prior": np.asarray(prior, float), "ratio": ratio,
            "overlap": overlap, "pct": float(pct[-1]), "first": first,
            "trades": [(t["entry_time"], t["side"], round(float(t["size"]), 9), t["exit_time"],
                        t["entry_px"], t["exit_px"]) for t in trades or ()]}


def _dip(paths, now):
    """DIP_424 as step() runs it: its daily series (or why not) and its trades (memo cleared, so
    a same-series answer is computed again, not looked up)."""
    cfg = cs.CROWN_LEGS["DIP_424"]
    arrays = _arrays(cfg, paths, now)
    series, err = DL.build_daily_series(arrays, now, paths, dict(cs.DIP_424_PARAMS), log=_quiet)
    DL._PROBE_MEMO.clear()
    why = {}
    trades, _ = cs.leg_decision_trades(cfg, arrays, "DIP_424", "5m", now, paths, False,
                                       log=_quiet, why_out=why)
    return {"series": series, "err": err, "why": why.get("key"),
            "trades": None if trades is None else sorted(
                (t["slot"], t["entry_time"], t["exit_time"], t["shares"], t["entry_px"],
                 t["exit_px"], t["size"]) for t in trades)}


def _same_series(a, b):
    assert a["dates"] == b["dates"] and a["source"] == b["source"]
    for k in ("open", "high", "low", "close", "volume"):
        assert np.array_equal(a["arrays"][k], b["arrays"][k]), k


def _monitor(paths, today):
    """tools/webull_freshness.qqq_1d_stale on the same files (collect's own reads)."""
    class R:
        returncode, stdout, stderr = 0, "", ""
    snap = wf.collect(wf.default_paths(paths["home"]), lambda *a, **k: R)
    return wf.qqq_1d_stale(snap, today)


# -- 1 + 2. one and two sessions short, the 5m cache whole: the 10-20 open ---------------------
def test_a_short_file_hands_noise_the_same_dates_at_one_scale_and_dip_the_same_series(tmp_path):
    now = _at(dt.date(2026, 10, 20))
    full = _home(tmp_path, "full", MON)
    n_full, d_full = _noise(full, now), _dip(full, now)
    assert n_full["why"] == "ok" and n_full["overlap"] == 93
    assert d_full["err"] is None and d_full["trades"]
    for short_by, through in ((1, FRI), (2, THU)):
        short = _home(tmp_path, f"short{short_by}", through)
        n = _noise(short, now)
        assert n["why"] == "ok" and n["overlap"] == n_full["overlap"] - short_by
        # the same daily dates (all before the 5m window), each times one factor
        assert len(n["prior"]) == len(n_full["prior"])
        factor = n["ratio"] / n_full["ratio"]
        assert n["prior"] == pytest.approx(n_full["prior"] * factor, rel=1e-12, abs=0)
        assert abs(factor - 1.0) < 1e-4
        assert n["pct"] == n_full["pct"] and n["trades"] == n_full["trades"]
        d = _dip(short, now)
        assert d["err"] is None
        _same_series(d["series"], d_full["series"])
        assert d["trades"] == d_full["trades"]
        # the monitor names this case: DIP untouched, NOISE only at the line
        m = _monitor(short, now.date())
        assert m["affects"] == wf.NOISE_AT_THE_LINE
        assert "DIP #424 unchanged" in m["dev"]


def test_the_rank_can_move_one_place_far_from_the_skip_line(tmp_path):
    """09-09, two sessions short (09-04 and 09-08): one bridged session crosses yesterday's range
    -- the rank moves 22.6 -> 22.2, the skip (95) and every NOISE trade stay. This is why the
    note cannot say "no change": at the line, the same move would flip the skip."""
    now = _at(dt.date(2026, 9, 9))
    full = _noise(_home(tmp_path, "full", dt.date(2026, 9, 8)), now)
    short = _noise(_home(tmp_path, "short2", dt.date(2026, 9, 3)), now)
    assert full["pct"] == pytest.approx(100.0 * 57 / 252)
    assert short["pct"] == pytest.approx(100.0 * 56 / 252)
    assert full["pct"] < 95.0 and short["pct"] < 95.0
    assert short["prior"] == pytest.approx(full["prior"] * short["ratio"] / full["ratio"],
                                           rel=1e-12, abs=0)
    assert short["trades"] == full["trades"]


# -- 3. a lacking session only part-way in the 5m cache ----------------------------------------
def test_a_partial_lacking_session_changes_a_dip_trade(tmp_path):
    """10-15 cut after its 15:45 high bar, judged at the 10-16 open: the full file gives DIP the
    official 10-15 daily bar; the short file gives it the partial session -- and the STREAK lot
    that stays open on the full file EXITS at the 10-16 open on the short one."""
    b = _bars()
    on_thu = b["t5"].dt.date == THU
    high_bar = b["f5"].loc[b["f5"][on_thu]["high"].idxmax(), "time"]
    five = b["f5"][~(on_thu & (b["f5"]["time"] > high_bar))]
    assert b["t5"][b["f5"]["time"] == high_bar].dt.strftime("%H:%M").item() == "15:45"
    now = _at(FRI)
    full = _home(tmp_path, "full", THU, five)
    short = _home(tmp_path, "short", dt.date(2026, 10, 14), five)
    d_full, d_short = _dip(full, now), _dip(short, now)
    src_full = dict(zip(d_full["series"]["dates"], d_full["series"]["source"]))
    src_short = dict(zip(d_short["series"]["dates"], d_short["series"]["source"]))
    assert src_full[THU] == "1d" and src_short[THU] == "5m_partial"
    decided = lambda d: {t[:3] for t in d["trades"]}                # noqa: E731 (slot, in, out)
    assert decided(d_full) - decided(d_short) == {("STREAK", "2026-10-13T09:30:00-04:00", None)}
    assert decided(d_short) - decided(d_full) == {
        ("STREAK", "2026-10-13T09:30:00-04:00", "2026-10-16T09:30:00-04:00")}
    # and the 10-15 open itself is the 5m bar's, not the official one: the CAP entry's price
    px = lambda d: {t[0]: t[4] for t in d["trades"] if t[1] == "2026-10-15T09:30:00-04:00"}  # noqa
    assert px(d_full)["CAP"] == 718.55 and px(d_short)["CAP"] == 718.77
    m = _monitor(short, FRI)
    assert m["affects"] == ("DIP #424 decides on only part of Thursday's prices, and "
                            + wf.NOISE_AT_THE_LINE)
    assert "PARTIAL 5m session for 2026-10-15" in m["dev"]


# -- 4. a lacking session not in the 5m cache at all -------------------------------------------
def test_a_lacking_session_missing_from_the_5m_cache_stops_dip_and_its_note_pages(tmp_path):
    b = _bars()
    five = b["f5"][b["t5"].dt.date != MON]
    now = _at(dt.date(2026, 10, 20))
    full = _dip(_home(tmp_path, "full", MON, five), now)
    short_paths = _home(tmp_path, "short", FRI, five)
    short = _dip(short_paths, now)
    assert full["err"] is None and full["trades"]                  # the daily bar fills it
    assert short["series"] is None and short["err"][0] == "prev_missing"
    assert short["trades"] is None and short["why"] == "prev_missing"
    # not the record-only cause (the file has rows): the not-ready note pages
    assert cs.qqq_1d_missing_or_empty(short_paths) is None
    assert cs._qqq_1d_is_the_cause("not_ready", "prev_missing", "x", short_paths) is None
    m = _monitor(short_paths, now.date())
    assert m["affects"] == "DIP #424 takes no new trades and sends no exit for its held shares"
    assert "NOT READY (2026-10-19 in neither file" in m["dev"]


# -- 5. the monitor's whole-session test is DIP's ----------------------------------------------
def test_the_monitors_whole_session_test_is_dips(tmp_path):
    b = _bars()
    on_thu = b["t5"].dt.date == THU
    hm = b["t5"].dt.strftime("%H:%M")
    cut = b["f5"][~(on_thu & (hm > "15:45"))]                       # ends early
    late = b["f5"][~(on_thu & ((hm > "15:45") | (hm < "09:40")))]   # and starts late
    for five in (b["f5"], cut, late):
        paths = _home(tmp_path, f"w{len(five)}", dt.date(2026, 6, 5), five)
        spans = wf.five_min_day_spans(wf.default_paths(paths["home"]), dt.date(2026, 6, 5))
        sessions = DL.five_min_sessions(_arrays(cs.CROWN_LEGS["DIP_424"], paths,
                                                _at(dt.date(2026, 10, 21))))
        assert set(spans) == set(sessions)
        assert {d: wf.five_min_whole(s, d) for d, s in spans.items()} == \
            {d: s["complete"] for d, s in sessions.items()}
        assert wf.five_min_whole(spans[THU], THU) is (five is b["f5"])


# -- 6. "not affected" rests on the 5m window's REAL session count -----------------------------
def test_todays_rank_reads_the_daily_bars_until_the_window_holds_253_sessions_before_today():
    """NOISE_1_0 _vol_percentile ranks yesterday among the 252 sessions before it (ext[j-252:j]):
    with k sessions before today in the 5m window, the daily bars are read unless k - 1 >= 252
    (the monitor's VOL_SKIP_SESSIONS test) -- every daily range changed moves today's rank at
    k = 252 and never at 253 or more."""
    rng = np.random.default_rng(7)
    for k, moves in ((250, True), (252, True), (253, False), (261, False)):
        n = k + 1                                                    # + today's session
        hi, lo, cl = 1.0 + rng.random(n), np.zeros(n), np.ones(n)
        bounds = [(i, i + 1) for i in range(n)]
        low = N0._vol_percentile(hi, lo, cl, bounds, prior_ranges=np.zeros(300))
        high = N0._vol_percentile(hi, lo, cl, bounds, prior_ranges=np.full(300, 1e9))
        assert bool(low[-1] != high[-1]) is moves, k
    assert wf.VOL_SKIP_SESSIONS == N0.VOL_SKIP_REF_SESSIONS == N0.REQUIRED_LOOKBACK_SESSIONS


def test_the_engines_window_counts_the_sessions_really_in_the_5m_cache(tmp_path):
    """Holes in the 5m history shorten NOISE's window by exactly the sessions missing -- the
    engine counts sessions held, not the calendar from the first row -- and the monitor's full
    list (five_min_session_days, read before it says "not affected") counts the same ones."""
    b = _bars()
    days = sorted(set(b["t5"].dt.date))
    holes = days[10:16]
    five = b["f5"][~b["t5"].dt.date.isin(holes)]
    paths = _home(tmp_path, "holes", MON, five)
    arrays = _arrays(cs.CROWN_LEGS["NOISE_382"], paths, _at(dt.date(2026, 10, 21)))
    assert len(set(np.asarray(arrays["day_id"]).tolist())) == len(days) - 6 == 88
    assert wf.five_min_session_days(wf.default_paths(paths["home"])) == \
        sorted(set(days) - set(holes))


def test_the_monitors_numbers_are_the_engines():
    assert wf.DAILY_MIN_OVERLAP == cs.DAILY_MIN_OVERLAP_SESSIONS == cs.DIP_CAL_MIN_OVERLAP
    assert wf.SESSION_OPEN == (cs.RTH_OPEN.hour, cs.RTH_OPEN.minute)
    assert cs.TIMEFRAME_SECONDS["5m"] == 300            # five_min_whole's "+ 5"

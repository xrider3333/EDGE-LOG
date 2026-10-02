"""Tests for tools/backfill_qqq_5m_alpaca.py (WEBULL go-live "alpaca" task, 2026-09-26).

No real Alpaca key exists yet (owner GO, key not added), so every HTTP call here goes
through a fake Alpaca response layer, and every box/ssh/scp call is either avoided
entirely (pure functions) or injected as a fake via run()'s own parameters. No test
opens a socket or an ssh connection -- see run()'s docstring for the injectable
boundaries (http_get, box_cache_df, ssh_fn, scp_fn).
"""
import datetime
import importlib.util
import os

import pandas as pd
import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_TOOLS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bf = _load_tool("backfill_qqq_5m_alpaca")


# ── key lookup ───────────────────────────────────────────────────────────────────────────
# This file used to own a copy of the lookup, with its own order (the out-of-repo secrets
# file ahead of the environment) and its own path constants. There is now ONE lookup,
# augur_engine/alpaca_keys.py, and tests/test_alpaca_keys.py covers the order, the BOM, the
# corrupt file and the registry fallback once. What is still this file's business is that it
# delegates rather than re-deriving, and that a missing key stops the run cleanly.
def test_load_keys_delegates_to_the_one_shared_lookup(monkeypatch):
    from augur_engine import alpaca_keys
    monkeypatch.setattr(alpaca_keys, "load_keys", lambda: ("SHARED_KEY", "SHARED_SECRET"))
    assert bf.load_keys() == ("SHARED_KEY", "SHARED_SECRET")


def test_no_second_lookup_is_left_behind_in_this_tool():
    """A leftover local copy is how the orders drifted apart in the first place."""
    src = open(os.path.join(_TOOLS, "backfill_qqq_5m_alpaca.py"), encoding="utf-8").read()
    body = src[src.index("def load_keys"):]
    body = body[:body.index(chr(10) + "def ")]
    assert "os.environ" not in body and "json.load" not in body, (
        "load_keys must call the shared module, not resolve anything itself")
    assert "alpaca_keys.load_keys()" in body


def test_load_keys_returns_none_when_nothing_is_configured():
    """conftest's _isolate_alpaca_keys fixture is what makes this safe to assert on a
    machine that HAS a real key in its user environment. `not any(...)` rather than
    `== (None, None)` so a failure here can never print the key it found."""
    assert not any(bf.load_keys()), "nothing configured must resolve to nothing"


# ── session window ───────────────────────────────────────────────────────────────────────
def test_last_full_session_before_close_returns_the_prior_session():
    # Tuesday 2026-09-22 at 10:00 ET -- session in progress, not yet closed
    now = datetime.datetime(2026, 9, 22, 10, 0, tzinfo=bf._ET)
    assert bf.last_full_session(now) == datetime.date(2026, 9, 21)  # the Monday before


def test_last_full_session_after_close_returns_todays_session():
    now = datetime.datetime(2026, 9, 22, 16, 30, tzinfo=bf._ET)
    assert bf.last_full_session(now) == datetime.date(2026, 9, 22)


def test_last_full_session_on_a_weekend_steps_back_to_friday():
    now = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=bf._ET)  # a Saturday
    assert bf.last_full_session(now) == datetime.date(2026, 9, 25)


def test_last_full_session_respects_a_half_day_close():
    # day after Thanksgiving 2026-11-27 closes at 13:00 ET
    now = datetime.datetime(2026, 11, 27, 13, 30, tzinfo=bf._ET)
    assert bf.last_full_session(now) == datetime.date(2026, 11, 27)
    now_before_close = datetime.datetime(2026, 11, 27, 12, 0, tzinfo=bf._ET)
    assert bf.last_full_session(now_before_close) == datetime.date(2026, 11, 25)


def test_sessions_ending_returns_n_sessions_oldest_first_skipping_weekends():
    end = datetime.date(2026, 9, 22)  # Tuesday
    out = bf.sessions_ending(end, 5)
    assert out == [datetime.date(2026, 9, 16), datetime.date(2026, 9, 17),
                  datetime.date(2026, 9, 18), datetime.date(2026, 9, 21),
                  datetime.date(2026, 9, 22)]


def test_sessions_ending_skips_a_holiday():
    # Labor Day 2026-09-07 (Monday) is not a session
    end = datetime.date(2026, 9, 8)
    out = bf.sessions_ending(end, 3)
    assert datetime.date(2026, 9, 7) not in out
    assert out[-1] == datetime.date(2026, 9, 8)


# ── RTH filter / half days ───────────────────────────────────────────────────────────────
def _epoch(y, m, d, hh, mm):
    import zoneinfo
    et = datetime.datetime(y, m, d, hh, mm, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    return int(et.timestamp())


def test_rth_filter_keeps_only_0930_to_1600_et():
    df = pd.DataFrame({
        "time": [_epoch(2026, 9, 22, 9, 0), _epoch(2026, 9, 22, 9, 30),
                _epoch(2026, 9, 22, 15, 55), _epoch(2026, 9, 22, 16, 0),
                _epoch(2026, 9, 22, 20, 0)],
        "open": [1, 2, 3, 4, 5], "high": [1, 2, 3, 4, 5], "low": [1, 2, 3, 4, 5],
        "close": [1, 2, 3, 4, 5], "volume": [1, 1, 1, 1, 1],
    })
    out = bf.rth_filter(df)
    assert list(out["open"]) == [2, 3]


def test_rth_filter_on_a_half_day_naturally_keeps_fewer_bars_but_the_session_still_counts():
    # day after Thanksgiving: Alpaca would simply have no bars after 13:00 on this day --
    # simulate that directly (no bars past 13:00), rth_filter's ceiling is a harmless no-op.
    df = pd.DataFrame({
        "time": [_epoch(2026, 11, 27, 9, 30), _epoch(2026, 11, 27, 12, 55)],
        "open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2], "volume": [1, 1],
    })
    out = bf.rth_filter(df)
    assert len(out) == 2
    assert bf.distinct_session_dates(out) == [datetime.date(2026, 11, 27)]


def test_rth_filter_drops_after_hours_bars_alpaca_actually_returns_on_a_half_day():
    # Alpaca's bars endpoint DOES return extended-hours bars, and after-hours trading
    # runs from 13:00 on a half day -- unlike the naive "Alpaca just has no bars past an
    # early close" test above, this exercises real 13:00-15:55 after-hours bars that a
    # fixed 16:00 ceiling would wrongly admit. Only the 09:30-12:55 regular bars survive.
    day = datetime.date(2026, 11, 27)   # day after Thanksgiving, 13:00 ET half-day close
    df = pd.DataFrame({
        "time": [_epoch(2026, 11, 27, 9, 30), _epoch(2026, 11, 27, 12, 55),
                _epoch(2026, 11, 27, 13, 0), _epoch(2026, 11, 27, 14, 30),
                _epoch(2026, 11, 27, 15, 55)],
        "open": [1, 2, 3, 4, 5], "high": [1, 2, 3, 4, 5], "low": [1, 2, 3, 4, 5],
        "close": [1, 2, 3, 4, 5], "volume": [1, 1, 1, 1, 1],
    })
    out = bf.rth_filter(df)
    assert list(out["open"]) == [1, 2]
    assert bf.distinct_session_dates(out) == [day]


def test_rth_filter_keeps_full_1600_close_on_a_normal_day_alongside_a_half_day():
    # a normal day's 15:55 bar (well past a half day's 13:00 close) must still survive
    # when both kinds of day are present in the same frame -- the close bound is per-bar
    # (by that bar's own ET date), not a single global cutoff.
    df = pd.DataFrame({
        "time": [_epoch(2026, 11, 27, 14, 30),   # half day: after close, dropped
                _epoch(2026, 11, 30, 15, 55)],   # normal Monday: before close, kept
        "open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2], "volume": [1, 1],
    })
    out = bf.rth_filter(df)
    assert list(out["open"]) == [2]


def test_rth_filter_handles_an_empty_frame():
    empty = pd.DataFrame(columns=bf.COLUMNS)
    out = bf.rth_filter(empty)
    assert len(out) == 0


# ── fetch: paging over a fake Alpaca HTTP layer ─────────────────────────────────────────
class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _bar(t, o=100.0, h=101.0, l=99.0, c=100.5, v=1000):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_fetch_5m_bars_produces_the_exact_box_cache_schema():
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params)
        return _FakeResp(200, {"bars": {"QQQ": [
            _bar("2026-09-21T13:30:00Z", 100, 101, 99, 100.5, 1000),
            _bar("2026-09-21T13:35:00Z", 100.5, 102, 100, 101.5, 900),
        ]}})

    df = bf.fetch_5m_bars("k", "s", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                          http_get=fake_get)
    assert list(df.columns) == bf.COLUMNS
    assert list(df["time"]) == [1789997400, 1789997700]
    assert calls[0]["symbols"] == "QQQ"
    assert calls[0]["feed"] == "sip"
    assert calls[0]["adjustment"] == "split"


def test_fetch_5m_bars_pages_via_next_page_token():
    pages = [
        {"bars": {"QQQ": [_bar("2026-09-21T13:30:00Z")]}, "next_page_token": "tok2"},
        {"bars": {"QQQ": [_bar("2026-09-21T13:35:00Z")]}},
    ]
    call_count = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        i = call_count["n"]
        call_count["n"] += 1
        if i == 0:
            assert "page_token" not in params
        else:
            assert params["page_token"] == "tok2"
        return _FakeResp(200, pages[i])

    df = bf.fetch_5m_bars("k", "s", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                          http_get=fake_get)
    assert len(df) == 2
    assert call_count["n"] == 2


def test_fetch_5m_bars_raises_systemexit_on_auth_failure():
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp(401, text="unauthorized")

    with pytest.raises(SystemExit) as exc:
        bf.fetch_5m_bars("bad", "bad", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                         http_get=fake_get)
    assert "AUTH FAILED" in str(exc.value)


def test_fetch_5m_bars_403_with_subscription_body_gets_its_own_message_not_auth_failed():
    # a free-plan recency 403 must not be reported as "check your key" -- that sends the
    # owner chasing a key rotation for a plan limitation instead.
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp(403, text='{"message": "subscription does not permit querying '
                                   'recent SIP data"}')

    with pytest.raises(SystemExit) as exc:
        bf.fetch_5m_bars("k", "s", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                         http_get=fake_get)
    msg = str(exc.value)
    assert "AUTH FAILED" not in msg
    assert "subscription" in msg.lower() or "recent" in msg.lower()


def test_fetch_5m_bars_403_without_subscription_body_still_reads_as_auth_failed():
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp(403, text="forbidden")

    with pytest.raises(SystemExit) as exc:
        bf.fetch_5m_bars("bad", "bad", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                         http_get=fake_get)
    assert "AUTH FAILED" in str(exc.value)


# ── end_iso free-plan recency clamp ──────────────────────────────────────────────────────
def test_end_iso_for_is_untouched_for_an_end_date_well_in_the_past():
    now = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=bf._ET)
    end_iso = bf._end_iso_for(datetime.date(2026, 9, 22), now)
    assert end_iso == "2026-09-23T00:00:00Z"


def test_end_iso_for_clamps_to_now_minus_delay_for_the_current_evening():
    # asking for TODAY's session at 20:05 ET, before the naive midnight-UTC bound (20:00
    # ET) would even be reached, must clamp to now - FREE_SIP_DELAY, not ask for data
    # that is still inside Alpaca's free-plan recency window.
    now = datetime.datetime(2026, 9, 22, 20, 5, tzinfo=bf._ET)
    end_iso = bf._end_iso_for(datetime.date(2026, 9, 22), now)
    expected = (now.astimezone(datetime.timezone.utc) - bf.FREE_SIP_DELAY)
    assert end_iso == expected.strftime("%Y-%m-%dT%H:%M:%SZ")
    naive = "2026-09-23T00:00:00Z"
    assert end_iso < naive, "the clamp must move the bound EARLIER than the naive midnight-UTC one"


def test_fetch_5m_bars_empty_result_returns_empty_frame_with_right_columns():
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp(200, {"bars": {"QQQ": []}})

    df = bf.fetch_5m_bars("k", "s", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z",
                          http_get=fake_get)
    assert list(df.columns) == bf.COLUMNS
    assert len(df) == 0


# ── cross-check ──────────────────────────────────────────────────────────────────────────
def _df(times, prices):
    return pd.DataFrame({
        "time": times, "open": prices, "high": prices, "low": prices, "close": prices,
        "volume": [1000.0] * len(times),
    })


def test_cross_check_passes_when_overlap_matches_within_tolerance():
    times = [1000, 1300, 1600]
    new = _df(times, [100.00, 100.01, 100.02])
    box = _df(times, [100.00, 100.00, 100.03])   # all diffs <= 2 cents
    r = bf.cross_check(new, box)
    assert r["ok"] is True
    assert r["n_compared"] == 3
    assert r["n_over_tol"] == 0


def test_cross_check_fails_when_too_many_bars_disagree():
    times = list(range(0, 1000, 1))[:100]
    times = [t * 100 for t in range(100)]
    new = _df(times, [100.0] * 100)
    box_prices = [100.0] * 90 + [110.0] * 10   # 10% of bars off by $10
    box = _df(times, box_prices)
    r = bf.cross_check(new, box)
    assert r["ok"] is False
    assert r["n_over_tol"] == 10
    assert "10/100" in r["reason"]


def test_cross_check_refuses_when_there_is_no_overlap_at_all():
    new = _df([1000, 1300], [100.0, 100.0])
    box = _df([9000, 9300], [100.0, 100.0])
    r = bf.cross_check(new, box)
    assert r["ok"] is False
    assert r["n_compared"] == 0
    assert "cannot verify" in r["reason"]


def test_cross_check_refuses_when_box_df_is_none():
    new = _df([1000], [100.0])
    r = bf.cross_check(new, None)
    assert r["ok"] is False


def test_cross_check_notes_a_likely_adjustment_mismatch():
    times = [t * 100 for t in range(50)]
    new = _df(times, [200.0] * 50)   # exactly 2x the box's prices
    box = _df(times, [100.0] * 50)
    r = bf.cross_check(new, box)
    assert r["ok"] is False
    assert "adjustment mismatch" in r["reason"]


def test_cross_check_reports_which_columns_carry_the_over_tolerance_bars():
    # high/low off by a lot (vendor high/low noise), open/close matching exactly -- the
    # lead should be able to tell this apart from a real open/close mismatch.
    times = [0, 100, 200]
    new = pd.DataFrame({"time": times, "open": [100.0] * 3, "high": [100.5] * 3,
                        "low": [99.0] * 3, "close": [100.0] * 3, "volume": [1000.0] * 3})
    box = pd.DataFrame({"time": times, "open": [100.0] * 3, "high": [100.0] * 3,
                        "low": [99.5] * 3, "close": [100.0] * 3, "volume": [1000.0] * 3})
    r = bf.cross_check(new, box, tolerance=0.02, max_bad_fraction=0.0)
    assert r["ok"] is False
    assert r["col_over_tol"]["open"] == 0 and r["col_over_tol"]["close"] == 0
    assert r["col_over_tol"]["high"] == 3 and r["col_over_tol"]["low"] == 3
    assert "high=3" in r["reason"] and "low=3" in r["reason"]
    assert "open=" not in r["reason"], "a zero-count column should not clutter the reason"


def test_cross_check_honours_a_wider_tolerance_and_max_bad_fraction():
    times = [t * 100 for t in range(20)]
    new = _df(times, [100.10] * 20)   # 10 cents off from the box on every bar
    box = _df(times, [100.00] * 20)
    default_check = bf.cross_check(new, box)
    assert default_check["ok"] is False   # the default 2-cent tolerance rejects this
    widened = bf.cross_check(new, box, tolerance=0.15, max_bad_fraction=0.0)
    assert widened["ok"] is True          # a 15-cent tolerance accepts the same data
    tightened = bf.cross_check(new, box, tolerance=0.02, max_bad_fraction=1.0)
    assert tightened["ok"] is True        # or accepting up to 100% of bars over tolerance


# ── write_local ──────────────────────────────────────────────────────────────────────────
def test_write_local_writes_exact_columns_and_is_atomic(tmp_path):
    out = tmp_path / "sub" / "backfill.csv"
    df = _df([1000, 1300], [100.0, 101.0])
    bf.write_local(df, str(out))
    assert out.exists()
    assert not (tmp_path / "sub" / "backfill.csv.tmp").exists()
    reread = pd.read_csv(out)
    assert list(reread.columns) == bf.COLUMNS
    assert list(reread["time"]) == [1000, 1300]


# ── run(): the orchestration, fully faked ──────────────────────────────────────────────
def _stub_alpaca(bars_by_call=None, single_bars=None):
    """A fake http_get that always returns `single_bars` (a list of Alpaca bar dicts) in
    one page, for any request."""
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResp(200, {"bars": {"QQQ": single_bars or []}})
    return fake_get


def _rth_bar_dicts(day, n):
    """n RTH 5-minute bars starting 09:30 ET on `day` (a date), as Alpaca bar dicts."""
    import zoneinfo
    et = zoneinfo.ZoneInfo("America/New_York")
    out = []
    start = datetime.datetime(day.year, day.month, day.day, 9, 30, tzinfo=et)
    for k in range(n):
        t = start + datetime.timedelta(minutes=5 * k)
        out.append(_bar(t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    return out


class _Args:
    def __init__(self, **kw):
        self.sessions = kw.get("sessions", 5)
        self.end = kw.get("end")
        self.out = kw.get("out")
        self.feed = kw.get("feed", "sip")
        self.adjustment = kw.get("adjustment", "split")
        self.apply = kw.get("apply", False)
        self.check = kw.get("check", False)
        self.tolerance = kw.get("tolerance", bf.CROSS_CHECK_TOLERANCE)
        self.max_bad_fraction = kw.get("max_bad_fraction", bf.CROSS_CHECK_MAX_BAD_FRACTION)


def test_run_refuses_when_no_key_is_configured(tmp_path):
    args = _Args(out=str(tmp_path / "out.csv"))
    rc = bf.run(args, key_secret=(None, None), log=lambda *a: None)
    assert rc == 1
    assert not (tmp_path / "out.csv").exists()


def test_run_check_mode_never_writes_a_file(tmp_path):
    args = _Args(check=True)
    fake_get = _stub_alpaca(single_bars=_rth_bar_dicts(datetime.date(2026, 9, 21), 3))
    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, log=lambda *a: None)
    assert rc == 0


def test_run_writes_local_file_without_apply_even_when_cross_check_fails(tmp_path):
    out = tmp_path / "out.csv"
    args = _Args(sessions=3, end="2026-09-22", out=str(out))
    bars = []
    for day in (datetime.date(2026, 9, 18), datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)):
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    box_df = None  # no overlap available -> cross-check must fail, but --apply was never asked for

    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
               log=lambda *a: None)
    assert rc == 0
    assert out.exists()


def test_run_refuses_apply_when_cross_check_fails(tmp_path):
    out = tmp_path / "out.csv"
    days = [datetime.date(2026, 9, 18), datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)]
    bars = []
    for day in days:
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    args = _Args(sessions=3, end="2026-09-22", out=str(out), apply=True)

    scp_calls = []
    ssh_calls = []
    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=None,
               now_et=datetime.datetime(2026, 9, 23, 3, 0, tzinfo=bf._ET),
               ssh_fn=lambda cmd, timeout=60: ssh_calls.append(cmd),
               scp_fn=lambda a, b, timeout=120: scp_calls.append((a, b)),
               log=lambda *a: None)
    assert rc == 1
    assert scp_calls == [] and ssh_calls == [], "a failed cross-check must never reach the transport"


def test_run_applies_when_cross_check_passes_and_outside_the_protected_window(tmp_path):
    out = tmp_path / "out.csv"
    days = [datetime.date(2026, 9, 18), datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)]
    bars = []
    for day in days:
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    args = _Args(sessions=3, end="2026-09-22", out=str(out), apply=True)

    # box cache holds the SAME bars (perfect overlap, zero diff) for the last session only
    fetched = bf.fetch_5m_bars("k", "s", "x", "y", http_get=fake_get)
    fetched = bf.rth_filter(fetched)
    box_df = fetched.copy()

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    scp_calls, ssh_calls = [], []

    def fake_scp(a, b, timeout=120):
        scp_calls.append((a, b))
        return _Result()

    def fake_ssh(cmd, timeout=60):
        ssh_calls.append(cmd)
        return _Result()

    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
               now_et=datetime.datetime(2026, 9, 23, 3, 0, tzinfo=bf._ET),  # 03:00 ET, outside the window
               ssh_fn=fake_ssh, scp_fn=fake_scp, log=lambda *a: None)
    assert rc == 0
    assert len(scp_calls) == 1
    assert scp_calls[0][1] == bf.REMOTE_BACKFILL_5M + ".tmp"
    assert any("mv " in c for c in ssh_calls)


def test_run_refuses_apply_inside_the_protected_window(tmp_path):
    out = tmp_path / "out.csv"
    days = [datetime.date(2026, 9, 18), datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)]
    bars = []
    for day in days:
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    args = _Args(sessions=3, end="2026-09-22", out=str(out), apply=True)

    fetched = bf.rth_filter(bf.fetch_5m_bars("k", "s", "x", "y", http_get=fake_get))
    box_df = fetched.copy()

    scp_calls, ssh_calls = [], []
    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
               now_et=datetime.datetime(2026, 9, 22, 10, 0, tzinfo=bf._ET),  # mid-session Tuesday
               ssh_fn=lambda cmd, timeout=60: ssh_calls.append(cmd),
               scp_fn=lambda a, b, timeout=120: scp_calls.append((a, b)),
               log=lambda *a: None)
    assert rc == 1
    assert scp_calls == [] and ssh_calls == []


def test_run_apply_honours_a_widened_tolerance_flag(tmp_path):
    """The lead's escape hatch for a Yahoo/Webull-sourced box cache that plausibly
    disagrees with SIP by more than the hardcoded 2-cent/1% defaults: --tolerance and
    --max-bad-fraction, not a code edit."""
    out = tmp_path / "out.csv"
    days = [datetime.date(2026, 9, 18), datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)]
    bars = []
    for day in days:
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    args = _Args(sessions=3, end="2026-09-22", out=str(out), apply=True)

    fetched = bf.rth_filter(bf.fetch_5m_bars("k", "s", "x", "y", http_get=fake_get))
    box_df = fetched.copy()
    box_df["close"] = box_df["close"] + 0.10   # 10 cents off every bar

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    scp_calls = []
    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
               now_et=datetime.datetime(2026, 9, 23, 3, 0, tzinfo=bf._ET),
               ssh_fn=lambda cmd, timeout=60: _Result(),
               scp_fn=lambda a, b, timeout=120: (scp_calls.append((a, b)), _Result())[1],
               log=lambda *a: None)
    assert rc == 1, "the default 2-cent tolerance must still refuse this"
    assert scp_calls == []

    args2 = _Args(sessions=3, end="2026-09-22", out=str(out), apply=True, tolerance=0.15)
    scp_calls2 = []
    rc2 = bf.run(args2, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
                now_et=datetime.datetime(2026, 9, 23, 3, 0, tzinfo=bf._ET),
                ssh_fn=lambda cmd, timeout=60: _Result(),
                scp_fn=lambda a, b, timeout=120: (scp_calls2.append((a, b)), _Result())[1],
                log=lambda *a: None)
    assert rc2 == 0, "a widened --tolerance must let the same data pass and apply"
    assert len(scp_calls2) == 1


def test_run_refuses_apply_when_fewer_sessions_than_requested_were_fetched(tmp_path):
    out = tmp_path / "out.csv"
    # only 2 sessions of bars even though --sessions asks for 5
    bars = []
    for day in (datetime.date(2026, 9, 21), datetime.date(2026, 9, 22)):
        bars.extend(_rth_bar_dicts(day, 2))
    fake_get = _stub_alpaca(single_bars=bars)
    args = _Args(sessions=5, end="2026-09-22", out=str(out), apply=True)

    fetched = bf.rth_filter(bf.fetch_5m_bars("k", "s", "x", "y", http_get=fake_get))
    box_df = fetched.copy()   # a perfect cross-check, so ONLY the session-count gate can refuse

    scp_calls = []
    rc = bf.run(args, key_secret=("k", "s"), http_get=fake_get, box_cache_df=box_df,
               now_et=datetime.datetime(2026, 9, 23, 3, 0, tzinfo=bf._ET),
               ssh_fn=lambda cmd, timeout=60: None,
               scp_fn=lambda a, b, timeout=120: scp_calls.append((a, b)),
               log=lambda *a: None)
    assert rc == 1
    assert scp_calls == []


def test_apply_upload_is_atomic_tmp_then_mv(tmp_path):
    calls = {}

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_scp(local, remote, timeout=120):
        calls["scp"] = (local, remote)
        return _R()

    def fake_ssh(cmd, timeout=60):
        calls["ssh"] = cmd
        return _R()

    local = str(tmp_path / "backfill.csv")
    open(local, "w").close()
    ok, msg = bf.apply_upload(local, ssh_fn=fake_ssh, scp_fn=fake_scp)
    assert ok is True
    assert calls["scp"] == (local, bf.REMOTE_BACKFILL_5M + ".tmp")
    assert "mv " in calls["ssh"] and bf.REMOTE_BACKFILL_5M in calls["ssh"]


def test_apply_upload_fails_cleanly_when_scp_fails(tmp_path):
    class _R:
        def __init__(self, rc):
            self.returncode = rc
            self.stdout = ""
            self.stderr = "connection refused"

    ok, msg = bf.apply_upload(str(tmp_path / "x.csv"),
                              ssh_fn=lambda cmd, timeout=60: _R(0),
                              scp_fn=lambda a, b, timeout=120: _R(1))
    assert ok is False
    assert "scp upload failed" in msg


# ── protected window ──────────────────────────────────────────────────────────────────────
def test_in_protected_window_true_mid_session():
    now = datetime.datetime(2026, 9, 22, 12, 0, tzinfo=bf._ET)
    assert bf.in_protected_window(now) is True


def test_in_protected_window_false_outside_hours():
    now = datetime.datetime(2026, 9, 22, 20, 0, tzinfo=bf._ET)
    assert bf.in_protected_window(now) is False


def test_in_protected_window_false_on_a_weekend_even_at_noon():
    now = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=bf._ET)
    assert bf.in_protected_window(now) is False

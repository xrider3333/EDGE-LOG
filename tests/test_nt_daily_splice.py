"""tools/nt_daily_splice.py: today's NQ day session from NinjaTrader into the NQ RTH no-adjust masters (MANAGER #68 D).

Synthetic data in a temp registry. Pins: today is written whole from NT whether the master is missing it or holds
Yahoo-style bars for it (opens/closes on the other side of the bar boundary), yesterday is the level anchor, other
sources (tv) are never touched, no anchor = refused, and the file wait gives up at its deadline.
"""
import importlib.util
import os
import sqlite3

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("_nt_daily", os.path.join(ROOT, "tools", "nt_daily_splice.py"))
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)
S = D.S

DAYS = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]        # Mon..Thu; the last is "today"
COLS = ["id", "name", "filename", "instrument", "timeframe", "source", "rows", "date_from", "date_to",
        "is_master", "provenance"]


def _minutes(seed=21):
    rows, rng, px = [], np.random.default_rng(seed), 25000.0
    for d in DAYS:
        t0 = pd.Timestamp(f"{d} 09:30", tz="US/Eastern")
        for i in range(390):
            o = px
            px = round((px + rng.integers(-6, 7) * 0.25) * 4) / 4
            rows.append(dict(time=int((t0 + pd.Timedelta(minutes=i)).timestamp()), open=o, high=max(o, px) + 0.5,
                             low=min(o, px) - 0.5, close=px, volume=int(rng.integers(200, 2000))))
    return pd.DataFrame(rows)


def _yahooish(m, day):
    out = m.copy()
    a, b = (S._epoch(x) for x in S.session_window(day, "rth"))
    sel = out.index[(out["time"] >= a) & (out["time"] < b)][::2]
    out.loc[sel, "close"] = np.minimum(out.loc[sel, "high"], out.loc[sel, "close"] + 0.5)
    return out


def _setup(tmp_path, today_state="yahoo"):
    """Registry: NQ 1m + 5m RTH no-adjust (with a source column) and a tv 5m. NT daily file: yesterday + today."""
    full = _minutes()
    a_today = S._epoch(S.session_window(DAYS[-1], "rth")[0])
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    whole = {}
    for mid, (fn, tf, src) in enumerate([("NOADJ_NQ_1m_RTH.csv", 1, "db_noadj_rth"),
                                         ("NOADJ_NQ_5m_RTH.csv", 5, "db_noadj_rth"),
                                         ("tv_NQ_5m.csv", 5, "tv")], start=1):
        w = pd.concat([S.derive(full, tf, "rth", d) for d in DAYS], ignore_index=True)
        w["source"] = "existing"
        whole[fn] = w
        m = _yahooish(w, DAYS[-1]) if today_state == "yahoo" else w[w["time"] < a_today]
        m.to_csv(up / fn, index=False)
        con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                    (mid, fn, fn, "NQ", f"{tf}m", src, len(m), DAYS[0], DAYS[-1], 1, '{"source": "%s"}' % src))
    con.commit(); con.close()
    nt = full[full["time"] >= S._epoch(S.session_window(DAYS[-2], "rth")[0])].copy()
    nt["time"] = nt["time"] + 60                                     # NinjaTrader stamps the bar END
    ntp = tmp_path / "NQ_daily_20261015.csv"
    nt.to_csv(ntp, index=False)
    return str(db), str(up), str(ntp), whole


@pytest.mark.parametrize("today_state", ["yahoo", "missing"])
def test_today_is_written_whole_from_nt_and_tv_is_left_alone(tmp_path, today_state):
    db, up, ntp, whole = _setup(tmp_path, today_state)
    tv_before = pd.read_csv(os.path.join(up, "tv_NQ_5m.csv"))
    written, refused = D.run(DAYS[-1], commit=True, path=ntp, db=db, uploads=up, log=lambda *_: None)
    assert sorted(written) == [1, 2] and refused == []
    for fn in ("NOADJ_NQ_1m_RTH.csv", "NOADJ_NQ_5m_RTH.csv"):
        got = pd.read_csv(os.path.join(up, fn))
        assert len(got) == len(whole[fn])
        assert np.allclose(got[["time", "open", "high", "low", "close", "volume"]].values,
                           whole[fn][["time", "open", "high", "low", "close", "volume"]].values)
        a = S._epoch(S.session_window(DAYS[-1], "rth")[0])
        assert (got.loc[got["time"] >= a, "source"] == "nt_hist_splice").all()   # the restate guard keys on this
    assert pd.read_csv(os.path.join(up, "tv_NQ_5m.csv")).equals(tv_before)
    assert D._filenames([1, 2], db=db) == ["NOADJ_NQ_1m_RTH.csv", "NOADJ_NQ_5m_RTH.csv"]


def test_a_dry_run_writes_nothing(tmp_path):
    db, up, ntp, whole = _setup(tmp_path)
    before = pd.read_csv(os.path.join(up, "NOADJ_NQ_5m_RTH.csv"))
    written, refused = D.run(DAYS[-1], commit=False, path=ntp, db=db, uploads=up, log=lambda *_: None)
    assert written == [] and refused == []
    assert pd.read_csv(os.path.join(up, "NOADJ_NQ_5m_RTH.csv")).equals(before)


def test_without_yesterday_in_the_file_there_is_no_anchor(tmp_path):
    db, up, ntp, whole = _setup(tmp_path)
    nt = pd.read_csv(ntp)
    nt[nt["time"] > S._epoch(S.session_window(DAYS[-1], "rth")[0])].to_csv(ntp, index=False)
    with pytest.raises(S.Refused, match="no session before"):
        D.run(DAYS[-1], commit=False, path=ntp, db=db, uploads=up, log=lambda *_: None)


def test_the_file_wait_returns_once_the_file_is_still_and_gives_up_at_the_deadline(tmp_path):
    p = tmp_path / "NQ_daily_20261015.csv"
    t = {"now": pd.Timestamp("2026-10-15 16:20", tz="US/Eastern").timestamp()}
    calls = []

    def sleep(s):
        calls.append(s)
        t["now"] += s
        if len(calls) == 2:
            p.write_text("time,open,high,low,close,volume\n1,1,1,1,1,1\n")

    assert D._wait_for_file(str(p), "17:15", clock=lambda: t["now"], sleep=sleep) is True
    missing = tmp_path / "never.csv"
    t["now"] = pd.Timestamp("2026-10-15 17:10", tz="US/Eastern").timestamp()
    assert D._wait_for_file(str(missing), "17:15", clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s)) is False


TG = ["2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"]     # Tue, Wed, Thanksgiving (to 13:00), Fri (to 13:15)


def _tg_setup(tmp_path, today):
    """NQ 1m + 5m RTH no-adjust masters through the day before `today` (plus Yahoo bars for the early close); the NT
    daily file holds the session before `today` and `today` (#108: Thanksgiving is a CME holiday session, 09:30-13:00)."""
    ends = {"2026-11-26": 210, "2026-11-27": 225}
    rows, rng, px = [], np.random.default_rng(5), 25000.0
    for d in TG:
        t0 = pd.Timestamp(f"{d} 09:30", tz="US/Eastern")
        for i in range(ends.get(d, 390)):
            o = px
            px = round((px + rng.integers(-6, 7) * 0.25) * 4) / 4
            rows.append(dict(time=int((t0 + pd.Timedelta(minutes=i)).timestamp()), open=o, high=max(o, px) + 0.5,
                             low=min(o, px) - 0.5, close=px, volume=int(rng.integers(200, 2000))))
    full = pd.DataFrame(rows)
    i = TG.index(today)
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    whole = {}
    for mid, (fn, tf) in enumerate([("NOADJ_NQ_1m_RTH.csv", 1), ("NOADJ_NQ_5m_RTH.csv", 5)], start=1):
        whole[fn] = pd.concat([S.derive(full, tf, "rth", d) for d in TG[:i + 1]], ignore_index=True)
        if today == "2026-11-27":                                    # the master holds Yahoo bars for the early close
            m = _yahooish(whole[fn], today)
        else:                                                        # the master is missing the holiday
            m = whole[fn][whole[fn]["time"] < S._epoch(S.session_window(today, "rth")[0])]
        m.to_csv(up / fn, index=False)
        con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                    (mid, fn, fn, "NQ", f"{tf}m", "db_noadj_rth", len(m), TG[0], today, 1, '{}'))
    con.commit(); con.close()
    nt = full[(full["time"] >= S._epoch(S.session_window(TG[i - 1], "rth")[0]))
              & (full["time"] < S._epoch(S.session_window(today, "rth")[1]))].copy()
    nt["time"] = nt["time"] + 60                                     # NinjaTrader stamps the bar END
    ntp = tmp_path / ("NQ_daily_%s.csv" % today.replace("-", ""))
    nt.to_csv(ntp, index=False)
    return str(db), str(up), str(ntp), whole


@pytest.mark.parametrize("today,bars", [("2026-11-26", {1: 210, 5: 42}), ("2026-11-27", {1: 225, 5: 45})])
def test_a_holiday_session_is_written_and_then_anchors_the_next_day(tmp_path, today, bars):
    """#108: Thanksgiving's 13:00 ET session is written like any day (it used to be skipped as a short session), and
    the next day's run anchors on it as a HELD session (it used to read as truncated and refuse the master). The
    13:15 ET early close the day after (Yahoo bars in the master) is replaced up to where the master ends."""
    db, up, ntp, whole = _tg_setup(tmp_path, today)
    written, refused = D.run(today, commit=True, path=ntp, db=db, uploads=up, log=lambda *_: None)
    assert sorted(written) == [1, 2] and refused == []
    for fn, tf in (("NOADJ_NQ_1m_RTH.csv", 1), ("NOADJ_NQ_5m_RTH.csv", 5)):
        got = pd.read_csv(os.path.join(up, fn))
        a, b = (S._epoch(x) for x in S.session_window(today, "rth"))
        assert ((got["time"] >= a) & (got["time"] < b)).sum() == bars[tf]
        assert np.allclose(got[["time", "open", "high", "low", "close", "volume"]].values,
                           whole[fn][["time", "open", "high", "low", "close", "volume"]].values)


def test_a_weekend_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "LOG", str(tmp_path / "daily.log"))
    assert D.main(["--date", "2026-10-17"]) == 0
    assert "weekend" in (tmp_path / "daily.log").read_text()

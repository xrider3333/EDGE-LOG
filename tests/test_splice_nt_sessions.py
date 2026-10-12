"""tools/splice_nt_sessions.py: filling a truncated ES/NQ session from NinjaTrader 1-minute history.

Synthetic data only, in a temp registry and temp uploads folder. Pins what makes the splice safe: a truncated
session comes back EXACTLY as the house resample rule would have built it (1m and 5m, and a TradingView-style
master carrying a constant back-adjustment), and the splice REFUSES rather than guesses when the NT minutes
disagree with the bars the master already holds, or when the master has no bar at all that day.
(The same proof on real data - every ES and NQ master of Feb 2020, truncated and re-spliced - is in the TBIS
lane's split_qa folder and matched to the bar.)
"""
import importlib.util
import os
import sqlite3

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("_splice", os.path.join(ROOT, "tools", "splice_nt_sessions.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

DAYS = ["2020-02-25", "2020-02-26"]          # Tue, Wed; the second is the 'hole'
COLS = ["id", "name", "filename", "instrument", "timeframe", "source", "rows", "date_from", "date_to",
        "is_master", "provenance"]


def _rth_minutes():
    rows = []
    rng = np.random.default_rng(7)
    px = 3000.0
    for d in DAYS:
        t0 = pd.Timestamp(f"{d} 09:30", tz="US/Eastern")
        for i in range(390):
            o = px
            px = round((px + rng.integers(-4, 5) * 0.25) * 4) / 4
            rows.append(dict(time=int((t0 + pd.Timedelta(minutes=i)).timestamp()), open=o, high=max(o, px) + 0.25,
                             low=min(o, px) - 0.25, close=px, volume=int(rng.integers(100, 900))))
    return pd.DataFrame(rows)


def _build(tmp_path, offset_tv=100.0):
    full = _rth_minutes()
    m5 = pd.concat([sp.derive(full, 5, "rth", d) for d in DAYS], ignore_index=True)
    tv = m5.copy()
    for c in ("open", "high", "low", "close"):
        tv[c] = tv[c] + offset_tv
    cut = int(pd.Timestamp(f"{DAYS[1]} 10:59", tz="US/Eastern").timestamp())
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    originals = {}
    for mid, (fn, frame, tf, src) in enumerate([("NOADJ_ES_1m_RTH.csv", full, "1m", "db_noadj_rth"),
                                                ("NOADJ_ES_5m_RTH.csv", m5, "5m", "db_noadj_rth"),
                                                ("tv_ES_5m.csv", tv, "5m", "tv")], start=1):
        originals[fn] = frame.copy()
        trunc = frame[frame["time"] < cut]
        trunc.to_csv(up / fn, index=False)
        con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                    (mid, fn, fn, "ES", tf, src, len(trunc), DAYS[0], DAYS[1], 1, '{"source": "%s"}' % src))
    con.commit(); con.close()
    hole = full[full["time"] >= int(pd.Timestamp(f"{DAYS[1]} 09:30", tz="US/Eastern").timestamp())].copy()
    hole["time"] = hole["time"] + 60                                  # NinjaTrader stamps the bar END
    ntp = tmp_path / "ES_nt.csv"
    return str(db), str(up), originals, hole, ntp


def test_a_truncated_session_comes_back_exactly(tmp_path):
    db, up, originals, hole, ntp = _build(tmp_path)
    hole.to_csv(ntp, index=False)
    res = sp.run("ES", DAYS[1], str(ntp), commit=True, db=db, uploads=up, log=lambda *_: None)
    assert [r[2] for r in res] == ["spliced"] * 3
    for fn, orig in originals.items():
        got = pd.read_csv(os.path.join(up, fn))
        assert len(got) == len(orig)
        assert np.allclose(got[["time", "open", "high", "low", "close"]].values,
                           orig[["time", "open", "high", "low", "close"]].values)
    con = sqlite3.connect(db)
    rows, prov = con.execute("select rows, provenance from csv_files where filename='NOADJ_ES_5m_RTH.csv'").fetchone()
    assert rows == len(originals["NOADJ_ES_5m_RTH.csv"]) and '"splices"' in prov and "nt_sha256" in prov


def test_a_dry_run_writes_nothing(tmp_path):
    db, up, originals, hole, ntp = _build(tmp_path)
    hole.to_csv(ntp, index=False)
    before = {fn: open(os.path.join(up, fn)).read() for fn in originals}
    res = sp.run("ES", DAYS[1], str(ntp), commit=False, db=db, uploads=up, log=lambda *_: None)
    assert [r[2] for r in res] == ["planned"] * 3
    assert all(open(os.path.join(up, fn)).read() == before[fn] for fn in originals)


def test_nt_minutes_at_a_different_level_are_refused(tmp_path):
    db, up, originals, hole, ntp = _build(tmp_path)
    for c in ("open", "high", "low", "close"):
        hole[c] = hole[c] + 1.0                                       # 4 ticks off: wrong contract or bad feed
    hole.to_csv(ntp, index=False)
    res = sp.run("ES", DAYS[1], str(ntp), commit=True, db=db, uploads=up, log=lambda *_: None)
    assert all(r[2] == "refused" for r in res)
    assert all("level offset" in r[3] for r in res)


def test_a_day_the_master_never_held_is_not_guessed(tmp_path):
    db, up, originals, hole, ntp = _build(tmp_path)
    hole.to_csv(ntp, index=False)
    p = os.path.join(up, "NOADJ_ES_5m_RTH.csv")
    m = pd.read_csv(p)
    d1 = int(pd.Timestamp(f"{DAYS[1]} 00:00", tz="US/Eastern").timestamp())
    m[m["time"] < d1].to_csv(p, index=False)
    res = {r[1]: r for r in sp.run("ES", DAYS[1], str(ntp), commit=False, db=db, uploads=up, log=lambda *_: None)}
    assert res["NOADJ_ES_5m_RTH.csv"][2] == "refused" and "no bar at all" in res["NOADJ_ES_5m_RTH.csv"][3]


def test_the_nt_file_is_read_as_bar_end(tmp_path):
    p = tmp_path / "nt.csv"
    pd.DataFrame({"time": [1582727400 + 60], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
                  "volume": [5]}).to_csv(p, index=False)
    assert int(sp.load_nt(str(p))["time"].iloc[0]) == 1582727400


def test_a_pull_one_minute_short_of_the_close_is_refused(tmp_path):
    """The real 2020-02-28 pulls ended at the bar ending 15:59 ET: the closing minute was missing."""
    db, up, originals, hole, ntp = _build(tmp_path)
    hole.iloc[:-1].to_csv(ntp, index=False)                           # drop the 15:59-16:00 minute
    res = sp.run("ES", DAYS[1], str(ntp), commit=True, db=db, uploads=up, log=lambda *_: None)
    assert all(r[2] == "refused" and "short of the session's last minute" in r[3] for r in res)


def test_a_long_bar_cut_in_its_first_hour_is_checked_on_its_open():
    """The real 2020-06-30 cut at 10:10 ET leaves the 60m master one PARTIAL 09:30 bar and no complete one;
    its open is final, so the level is checked there - and a feed at another level is still refused."""
    full = _rth_minutes()
    m60 = pd.concat([sp.derive(full, 60, "rth", d) for d in DAYS], ignore_index=True)
    day0 = int(pd.Timestamp(f"{DAYS[1]} 09:30", tz="US/Eastern").timestamp())
    cut = int(pd.Timestamp(f"{DAYS[1]} 10:10", tz="US/Eastern").timestamp())
    part = sp.derive(full[full["time"] < cut], 60, "rth", DAYS[1])
    trunc = pd.concat([m60[m60["time"] < day0], part], ignore_index=True)
    new, rep = sp.splice_plan(trunc, full, 60, "rth", DAYS[1], 0.0)
    assert rep["overlap_bars"] == 1 and rep["level_offset"] == 0.0
    assert np.allclose(new[["time", "open", "high", "low", "close"]].values,
                       m60[["time", "open", "high", "low", "close"]].values)
    shifted = full.copy()
    shifted[["open", "high", "low", "close"]] += 1.0
    with pytest.raises(sp.Refused, match="level offset"):
        sp.splice_plan(trunc, shifted, 60, "rth", DAYS[1], 0.0)


def test_a_one_tick_opening_print_does_not_move_the_day():
    """NQ 60m 2020-06-30: the master's partial 09:30 bar opened one tick above NT's first minute (an opening print
    on the other side of the minute). The splice accepts it (within a tick) but writes the day at the master's own
    reference offset, not at the one-print measurement."""
    full = _rth_minutes()
    m60 = pd.concat([sp.derive(full, 60, "rth", d) for d in DAYS], ignore_index=True)
    day0 = int(pd.Timestamp(f"{DAYS[1]} 09:30", tz="US/Eastern").timestamp())
    cut = int(pd.Timestamp(f"{DAYS[1]} 10:10", tz="US/Eastern").timestamp())
    part = sp.derive(full[full["time"] < cut], 60, "rth", DAYS[1])
    part.loc[0, "open"] += 0.25
    part.loc[0, "high"] = max(part.loc[0, "high"], part.loc[0, "open"])
    trunc = pd.concat([m60[m60["time"] < day0], part], ignore_index=True)
    new, rep = sp.splice_plan(trunc, full, 60, "rth", DAYS[1], 0.0)
    assert rep["level_offset"] == 0.25
    later = new[new["time"] > day0]
    assert np.allclose(later[["open", "high", "low", "close"]].values,
                       m60[m60["time"] > day0][["open", "high", "low", "close"]].values)


def test_registry_connections_wait_for_the_runners_locks(tmp_path):
    db = tmp_path / "r.db"
    con = sp._connect(str(db))
    assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 120000
    con.close()

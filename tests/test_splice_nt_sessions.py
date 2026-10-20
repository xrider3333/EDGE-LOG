"""tools/splice_nt_sessions.py: filling a truncated ES/NQ session from NinjaTrader 1-minute history.

Synthetic data only, in a temp registry and temp uploads folder. Pins what makes the splice safe: a truncated
session comes back EXACTLY as the house resample rule would have built it (1m and 5m, and a TradingView-style
master carrying a constant back-adjustment), and the splice REFUSES rather than guesses when the NT minutes
disagree with the bars the master already holds, or when the master has no bar at all that day.
(The same proof on real data - every ES and NQ master of Feb 2020, truncated and re-spliced - is in the TBIS
lane's split_qa folder and matched to the bar.)
"""
import importlib.util
import json
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


# ----------------------------------------------------------------------------- window fills (10-14)
WDAYS = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]     # Mon-Thu: held, truncated, missing, held


def _minutes(days, seed=11):
    rows, rng, px = [], np.random.default_rng(seed), 20000.0
    for d in days:
        t0 = pd.Timestamp(f"{d} 09:30", tz="US/Eastern")
        for i in range(390):
            o = px
            px = round((px + rng.integers(-6, 7) * 0.25) * 4) / 4
            rows.append(dict(time=int((t0 + pd.Timedelta(minutes=i)).timestamp()), open=o, high=max(o, px) + 0.5,
                             low=min(o, px) - 0.5, close=px, volume=int(rng.integers(200, 2000))))
    return pd.DataFrame(rows)


def _window_master(tf):
    full = _minutes(WDAYS)
    m = pd.concat([sp.derive(full, tf, "rth", d) for d in WDAYS], ignore_index=True)
    cut = int(pd.Timestamp(f"{WDAYS[1]} 10:58", tz="US/Eastern").timestamp())
    d2 = sp.session_window(WDAYS[2], "rth")
    keep = ~((m["time"] >= cut) & (m["time"] < sp._epoch(sp.session_window(WDAYS[1], "rth")[1])))
    keep &= ~((m["time"] >= sp._epoch(d2[0])) & (m["time"] < sp._epoch(d2[1])))
    return full, m, m[keep].reset_index(drop=True)


@pytest.mark.parametrize("tf", [1, 5, 60])
def test_a_window_fills_a_missing_day_and_a_truncated_one_exactly(tf):
    full, whole, holed = _window_master(tf)
    new, rep = sp.fill_plan(holed, full, tf, "rth", WDAYS[0], WDAYS[-1], 0.0)
    assert rep["sessions"] == {"held": 2, "truncated": 1, "missing": 1, "replaced": 0}
    assert rep["sessions_written"] == [WDAYS[1], WDAYS[2]]
    assert len(new) == len(whole)
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


def test_a_window_at_another_level_is_refused_even_with_no_truncated_day():
    full, whole, holed = _window_master(5)
    shifted = full.copy()
    shifted[["open", "high", "low", "close"]] += 1.0
    with pytest.raises(sp.Refused, match="level offset"):
        sp.fill_plan(holed, shifted, 5, "rth", WDAYS[0], WDAYS[-1], 0.0)


def test_a_missing_day_needs_the_whole_session_in_nt():
    full, whole, holed = _window_master(1)
    d2 = sp.session_window(WDAYS[2], "rth")
    late = full[~((full["time"] >= sp._epoch(d2[0])) & (full["time"] < sp._epoch(d2[0]) + 600))]   # 09:30-09:39 gone
    with pytest.raises(sp.Refused, match="not the whole session"):
        sp.fill_plan(holed, late, 1, "rth", WDAYS[0], WDAYS[-1], 0.0)


def _edge_prints(full, share=0.3, seed=3):
    """Move a trade across the minute boundary on `share` of minutes: this minute's close and the next one's open
    shift, its high/low and volume do not (what NQ 2020-02-28 looks like between Databento and NinjaTrader)."""
    rng = np.random.default_rng(seed)
    nt = full.copy()
    idx = rng.choice(len(nt) - 1, int(share * len(nt)), replace=False)
    for i in idx:
        lo, hi = nt.at[i, "low"], nt.at[i, "high"]
        nt.at[i, "close"] = min(hi, max(lo, nt.at[i, "close"] + 0.75))
        lo2, hi2 = nt.at[i + 1, "low"], nt.at[i + 1, "high"]
        nt.at[i + 1, "open"] = min(hi2, max(lo2, nt.at[i + 1, "open"] - 0.75))
    return nt


def test_hlv_accepts_minute_edge_prints_the_close_rule_refuses_and_counts_them():
    full, whole, holed = _window_master(1)
    nt = _edge_prints(full)
    with pytest.raises(sp.Refused, match="agree within one tick"):
        sp.fill_plan(holed, nt, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="close")
    new, rep = sp.fill_plan(holed, nt, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv")
    assert rep["rule"] == "hlv" and rep["agree"] == 1.0 and rep["volume_within_5pct"] == 1.0
    assert rep["open_close_differ"] > 0 and rep["max_open_close_diff"] == 0.75
    assert len(new) == len(whole)


def test_hlv_refuses_a_different_range_or_volume():
    full, whole, holed = _window_master(1)
    wide = full.copy()
    wide.loc[wide.index % 10 == 0, "high"] += 1.0        # ranges disagree on 10% of minutes: a different tape
    with pytest.raises(sp.Refused, match="high/low within one tick"):
        sp.fill_plan(holed, wide, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv")
    thin = full.copy()
    thin["volume"] = (thin["volume"] * 0.5).astype(int)  # half the volume: another contract or a thin feed
    with pytest.raises(sp.Refused, match="volume within 5%"):
        sp.fill_plan(holed, thin, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv")
    new, _ = sp.fill_plan(holed, thin, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv", check_volume=False)
    assert len(new) == len(whole)                        # a TradingView master is not volume-checked


def test_run_window_records_the_acceptance_in_the_provenance(tmp_path):
    full = _minutes(WDAYS)
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    m1 = full.copy()
    d2 = sp.session_window(WDAYS[2], "rth")
    holed = m1[~((m1["time"] >= sp._epoch(d2[0])) & (m1["time"] < sp._epoch(d2[1])))]
    holed.to_csv(up / "NOADJ_NQ_1m_RTH.csv", index=False)
    con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                (1, "NQ 1m RTH", "NOADJ_NQ_1m_RTH.csv", "NQ", "1m", "db_noadj_rth", len(holed), WDAYS[0], WDAYS[-1],
                 1, '{"source": "db_noadj_rth"}'))
    con.commit(); con.close()
    nt = _edge_prints(full).copy()
    nt["time"] = nt["time"] + 60                         # NinjaTrader stamps the bar END
    ntp = tmp_path / "nt.csv"
    nt.to_csv(ntp, index=False)
    res = sp.run_window("NQ", WDAYS[1], WDAYS[-1], str(ntp), commit=True, accept="hlv", db=str(db), uploads=str(up),
                        log=lambda *_: None)
    assert [r[2] for r in res] == ["spliced"]
    con = sqlite3.connect(db)
    rows, prov = con.execute("select rows, provenance from csv_files where id=1").fetchone()
    p = json.loads(prov)["splices"][-1]
    assert rows == len(full) and p["window"] == [WDAYS[1], WDAYS[-1]] and p["sessions_written"] == [WDAYS[2]]
    assert p["acceptance"]["rule"] == "hlv" and p["acceptance"]["open_close_differ"] > 0 and p["nt_sha256"]


def test_a_short_session_is_skipped_not_written_and_a_pull_a_minute_short_is_still_refused():
    """A missing NORMAL day (not a CME holiday session) whose NT minutes end at 13:00 ET is a short session the
    calendar does not list: skipped, never written (CME holiday sessions are written: see the #108 tests below). A
    missing day whose NT minutes stop one minute before the close is a bad pull and refuses the master."""
    full, whole, holed = _window_master(1)
    d2a, d2b = (sp._epoch(x) for x in sp.session_window(WDAYS[2], "rth"))
    early = full[~((full["time"] >= d2a + 210 * 60) & (full["time"] < d2b))]      # the missing day ends 13:00
    new, rep = sp.fill_plan(holed, early, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [WDAYS[1]] and rep["sessions_skipped"][0].startswith(WDAYS[2])
    assert not ((new["time"] >= d2a) & (new["time"] < d2b)).any()
    short = full[~((full["time"] >= d2b - 60) & (full["time"] < d2b))]            # the 15:59 minute missing
    with pytest.raises(sp.Refused, match="not the whole session"):
        sp.fill_plan(holed, short, 1, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv")


# ----------------------------------------------------------------------------- stub-bar repair (MANAGER #65, 10-14)
def _et(d, hhmm):
    return int(pd.Timestamp(f"{d} {hhmm}", tz="US/Eastern").timestamp())


def _stubbed(tf, day=WDAYS[1]):
    """A complete master with the bar holding 10:50 ET turned into a 2026-06-30-style stub: a fraction of its volume
    and (above 1m) a low that misses the real one."""
    full = _minutes(WDAYS)
    whole = pd.concat([sp.derive(full, tf, "rth", d) for d in WDAYS], ignore_index=True)
    a, b = (sp._epoch(x) for x in sp.session_window(day, "rth"))
    t = max(int(x) for x in whole["time"] if a <= x <= _et(day, "10:50"))
    stub = whole.copy()
    i = stub.index[stub["time"] == t][0]
    stub.at[i, "volume"] = 0 if tf == 1 else int(stub.at[i, "volume"]) // 5
    if tf > 1:
        stub.at[i, "low"] = stub.at[i, "low"] + 2.0
    return full, whole, stub, t


@pytest.mark.parametrize("tf", [1, 2, 5, 15, 60])
def test_a_stub_bar_is_rewritten_exactly_and_nothing_else(tf):
    full, whole, stub, t = _stubbed(tf)
    new, rep = sp.repair_plan(stub, full, tf, "rth", WDAYS[1], (_et(WDAYS[1], "10:45"), _et(WDAYS[1], "10:55")), 0.0)
    assert rep["bars_repaired"] == 1 and rep["repairs"][0]["time"] == t
    assert rep["repairs"][0]["after"][4] == int(whole.loc[whole["time"] == t, "volume"].iloc[0])
    assert len(new) == len(stub)
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


def test_bars_that_agree_are_left_alone_and_a_tv_master_keeps_its_offset():
    full, whole, stub, t = _stubbed(5)
    new, rep = sp.repair_plan(stub, full, 5, "rth", WDAYS[1], (_et(WDAYS[1], "12:00"), _et(WDAYS[1], "12:10")), 0.0)
    assert rep["bars_repaired"] == 0 and rep["window_bars"] == 2 and new.equals(stub)
    tv = stub.copy()
    tv[["open", "high", "low", "close"]] += 100.0
    new, rep = sp.repair_plan(tv, full, 5, "rth", WDAYS[1], (_et(WDAYS[1], "10:45"), _et(WDAYS[1], "10:55")), 100.0)
    fixed = new.loc[new["time"] == t].iloc[0]
    want = whole.loc[whole["time"] == t].iloc[0]
    assert rep["bars_repaired"] == 1 and fixed["low"] == want["low"] + 100.0 and fixed["volume"] == want["volume"]


def test_a_repair_refuses_another_level_another_tape_or_too_many_bars():
    full, whole, stub, t = _stubbed(5)
    win = (_et(WDAYS[1], "10:45"), _et(WDAYS[1], "10:55"))
    shifted = full.copy()
    shifted[["open", "high", "low", "close"]] += 1.0
    with pytest.raises(sp.Refused, match="level offset"):
        sp.repair_plan(stub, shifted, 5, "rth", WDAYS[1], win, 0.0)
    thin = full.copy()
    thin["volume"] = (thin["volume"] * 0.5).astype(int)
    with pytest.raises(sp.Refused, match="volume within 5%"):
        sp.repair_plan(stub, thin, 5, "rth", WDAYS[1], win, 0.0)
    many = whole.copy()
    hour = (many["time"] >= _et(WDAYS[1], "10:00")) & (many["time"] < _et(WDAYS[1], "10:20"))
    many.loc[hour, "volume"] = 1                                   # four bars in the window disagree
    with pytest.raises(sp.Refused, match="not a stub"):
        sp.repair_plan(many, full, 5, "rth", WDAYS[1], (_et(WDAYS[1], "10:00"), _et(WDAYS[1], "10:20")), 0.0)


def test_a_repair_needs_every_minute_behind_the_bar_and_a_held_session():
    full, whole, stub, t = _stubbed(5)
    win = (_et(WDAYS[1], "10:45"), _et(WDAYS[1], "10:55"))
    gap = full[full["time"] != _et(WDAYS[1], "10:52")]
    with pytest.raises(sp.Refused, match="every minute behind the 10:50 ET bar"):
        sp.repair_plan(stub, gap, 5, "rth", WDAYS[1], win, 0.0)
    a, b = (sp._epoch(x) for x in sp.session_window(WDAYS[1], "rth"))
    with pytest.raises(sp.Refused, match="a fill, not a repair"):
        sp.repair_plan(stub[(stub["time"] < a) | (stub["time"] >= b)], full, 5, "rth", WDAYS[1], win, 0.0)


def test_run_repair_writes_the_bar_and_records_before_and_after(tmp_path):
    full, whole, stub, t = _stubbed(1)
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    stub.to_csv(up / "NOADJ_NQ_1m_RTH.csv", index=False)
    con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                (1, "NQ 1m RTH", "NOADJ_NQ_1m_RTH.csv", "NQ", "1m", "db_noadj_rth", len(stub), WDAYS[0], WDAYS[-1],
                 1, '{"source": "db_noadj_rth"}'))
    con.commit(); con.close()
    nt = full.copy()
    nt["time"] = nt["time"] + 60                                    # NinjaTrader stamps the bar END
    ntp = tmp_path / "nt.csv"
    nt.to_csv(ntp, index=False)
    dry = sp.run_repair("NQ", WDAYS[1], ("10:45", "10:55"), str(ntp), db=str(db), uploads=str(up), log=lambda *_: None)
    assert [r[2] for r in dry] == ["planned"] and pd.read_csv(up / "NOADJ_NQ_1m_RTH.csv").equals(stub)
    res = sp.run_repair("NQ", WDAYS[1], ("10:45", "10:55"), str(ntp), commit=True, db=str(db), uploads=str(up),
                        log=lambda *_: None)
    assert [r[2] for r in res] == ["repaired"]
    out = pd.read_csv(up / "NOADJ_NQ_1m_RTH.csv")
    assert len(out) == len(stub) and out.equals(whole.reset_index(drop=True))
    con = sqlite3.connect(db)
    rows, prov = con.execute("select rows, provenance from csv_files where id=1").fetchone()
    p = json.loads(prov)
    assert rows == len(stub) and "splices" not in p
    e = p["repairs"][-1]
    assert e["window"] == ["10:45", "10:55"] and e["repairs"][0]["before"][4] == 0 and e["nt_sha256"]
    assert e["repairs"][0]["after"][4] == int(whole.loc[whole["time"] == t, "volume"].iloc[0])


# ----------------------------------------------------------------------------- replace held sessions (MANAGER #67, 10-14)
def _yahooish(m, days, seed=5):
    """Yahoo NQ=F since 10-05: same highs, lows and volume as NT, opens/closes on the other side of the bar boundary."""
    out = m.copy()
    rng = np.random.default_rng(seed)
    for d in days:
        a, b = (sp._epoch(x) for x in sp.session_window(d, "rth"))
        idx = out.index[(out["time"] >= a) & (out["time"] < b)]
        pick = rng.choice(idx, len(idx) // 2, replace=False)
        out.loc[pick, "close"] = np.minimum(out.loc[pick, "high"], out.loc[pick, "close"] + 0.5)
        out.loc[pick, "open"] = np.maximum(out.loc[pick, "low"], out.loc[pick, "open"] - 0.25)
    return out


@pytest.mark.parametrize("tf", [1, 5, 60])
def test_replace_from_rewrites_held_sessions_whole_and_anchors_on_the_rest(tf):
    full = _minutes(WDAYS)
    whole = pd.concat([sp.derive(full, tf, "rth", d) for d in WDAYS], ignore_index=True)
    held = _yahooish(whole, WDAYS[2:])
    assert not np.allclose(held[["open", "close"]].values, whole[["open", "close"]].values)
    new, rep = sp.fill_plan(held, full, tf, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv", replace_from=WDAYS[2])
    assert rep["sessions"] == {"held": 2, "truncated": 0, "missing": 0, "replaced": 2}
    assert rep["sessions_written"] == WDAYS[2:] and rep["bars_added"] == 0 and rep["replace_from"] == WDAYS[2]
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


def test_replacing_a_session_needs_nt_through_everything_the_master_holds():
    full = _minutes(WDAYS)
    whole = pd.concat([sp.derive(full, 5, "rth", d) for d in WDAYS], ignore_index=True)
    a, b = (sp._epoch(x) for x in sp.session_window(WDAYS[3], "rth"))
    short = full[~((full["time"] >= b - 3600) & (full["time"] < b))]          # NT stops at 15:00 on a full day
    with pytest.raises(sp.Refused, match="replacing a session needs NT minutes"):
        sp.fill_plan(_yahooish(whole, WDAYS[2:]), short, 5, "rth", WDAYS[0], WDAYS[-1], 0.0, accept="hlv",
                     replace_from=WDAYS[2])
    # an early close: the master and NT both end at 13:00 -> replaced up to the master's last bar
    early_nt = full[~((full["time"] >= a + 210 * 60) & (full["time"] < b))]
    early_m = whole[~((whole["time"] >= a + 210 * 60) & (whole["time"] < b))]
    new, rep = sp.fill_plan(_yahooish(early_m, WDAYS[2:]), early_nt, 5, "rth", WDAYS[0], WDAYS[-1], 0.0,
                            accept="hlv", replace_from=WDAYS[2])
    assert rep["sessions"]["replaced"] == 2 and len(new) == len(early_m)
    assert np.allclose(new[["open", "close"]].values, early_m[["open", "close"]].values)


def test_run_window_replace_writes_with_no_new_rows_and_leaves_other_sources_alone(tmp_path):
    full = _minutes(WDAYS)
    up = tmp_path / "up"; up.mkdir()
    db = tmp_path / "reg.db"
    con = sqlite3.connect(db)
    con.execute(f"create table csv_files ({', '.join(COLS)})")
    m1 = _yahooish(full, WDAYS[2:])
    m1.to_csv(up / "NOADJ_NQ_1m_RTH.csv", index=False)
    m1.to_csv(up / "tv_NQ_1m.csv", index=False)
    for mid, fn, src in ((1, "NOADJ_NQ_1m_RTH.csv", "db_noadj_rth"), (2, "tv_NQ_1m.csv", "tv")):
        con.execute(f"insert into csv_files values ({','.join('?' * len(COLS))})",
                    (mid, fn, fn, "NQ", "1m", src, len(m1), WDAYS[0], WDAYS[-1], 1, '{"source": "%s"}' % src))
    con.commit(); con.close()
    nt = full.copy()
    nt["time"] = nt["time"] + 60                                    # NinjaTrader stamps the bar END
    ntp = tmp_path / "nt.csv"
    nt.to_csv(ntp, index=False)
    res = sp.run_window("NQ", WDAYS[1], WDAYS[-1], str(ntp), commit=True, accept="hlv", db=str(db), uploads=str(up),
                        log=lambda *_: None, sources=("db_noadj_rth",), replace_from=WDAYS[2])
    assert [(r[0], r[2]) for r in res] == [(1, "spliced")]
    out = pd.read_csv(up / "NOADJ_NQ_1m_RTH.csv")
    assert len(out) == len(full) and np.allclose(out[["open", "close"]].values, full[["open", "close"]].values)
    assert np.allclose(pd.read_csv(up / "tv_NQ_1m.csv")[["close"]].values, m1[["close"]].values)
    con = sqlite3.connect(db)
    e = json.loads(con.execute("select provenance from csv_files where id=1").fetchone()[0])["splices"][-1]
    assert e["replace_from"] == WDAYS[2] and e["sessions"]["replaced"] == 2 and e["sessions_written"] == WDAYS[2:]
    assert e["rows_added"] == 0


# ----------------------------------------------------------------------------- CME holiday short sessions (#108, 10-19)
def _span_minutes(spans, seed=17, px=21000.0):
    """1m bars (start-stamped) over explicit ET [start, end) spans, e.g. ("2026-07-02 18:00", "2026-07-03 13:00")."""
    rows, rng = [], np.random.default_rng(seed)
    for s, e in spans:
        t0, t1 = pd.Timestamp(s, tz="US/Eastern"), pd.Timestamp(e, tz="US/Eastern")
        for t in range(int(t0.timestamp()), int(t1.timestamp()), 60):
            o = px
            px = round((px + rng.integers(-6, 7) * 0.25) * 4) / 4
            rows.append(dict(time=t, open=o, high=max(o, px) + 0.5, low=min(o, px) - 0.5, close=px,
                             volume=int(rng.integers(200, 2000))))
    return pd.DataFrame(rows)


def _hm(ts):
    return ts.strftime("%Y-%m-%d %H:%M")


def test_the_holiday_calendar_is_the_cme_rule():
    assert [d.isoformat() for d in sp.holiday_sessions(2026)] == [
        "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26"]
    h21 = [d.isoformat() for d in sp.holiday_sessions(2021)]
    assert "2021-07-05" in h21 and not any(d.startswith("2021-06") for d in h21)     # Juneteenth only from 2022
    assert "2022-06-20" in [d.isoformat() for d in sp.holiday_sessions(2022)]        # a Sunday 19th -> Monday
    for closed in ("2026-01-01", "2026-04-03", "2026-12-25", "2021-12-24", "2022-12-26", "2023-01-02"):
        assert not sp.is_holiday_session(closed)                                   # CME closed: no session at all
    for early in ("2026-11-27", "2026-12-24", "2025-07-03", "2024-12-24"):
        assert not sp.is_holiday_session(early)                                    # NYSE open, early close
    # every NYSE holiday is either a CME closure or a CME holiday short session, and every holiday session is an NYSE
    # holiday (api/market_calendar.py and augur_engine/session_calendar.py, 2010-2030)
    spec_mc = importlib.util.spec_from_file_location("_mc", os.path.join(ROOT, "api", "market_calendar.py"))
    mc = importlib.util.module_from_spec(spec_mc)
    spec_mc.loader.exec_module(mc)
    from augur_engine.session_calendar import closed_days
    for y in range(2010, 2031):
        nyse = set(mc.holiday_dates(y))
        hol = set(sp.holiday_sessions(y))
        assert hol <= nyse, y
        assert nyse - hol <= set(closed_days(y)), (y, sorted(nyse - hol - set(closed_days(y))))


def test_a_holiday_session_ends_at_1300_et_in_rth_and_eth():
    a, b = sp.session_window("2026-07-03", "rth")
    assert (_hm(a), _hm(b)) == ("2026-07-03 09:30", "2026-07-03 13:00")
    a, b = sp.session_window("2026-07-03", "eth")
    assert (_hm(a), _hm(b)) == ("2026-07-02 18:00", "2026-07-03 13:00")
    a, b = sp.session_window("2026-09-07", "eth")                                   # Labor Day: Sunday 18:00 open
    assert (_hm(a), _hm(b)) == ("2026-09-06 18:00", "2026-09-07 13:00")
    # the CME's old 10:30 CT holiday halt: the masters hold 2010-07-05..2012-09-03 to 11:30 ET (5m: 24 bars)
    assert _hm(sp.session_window("2012-09-03", "rth")[1]) == "2012-09-03 11:30"
    assert _hm(sp.session_window("2011-01-17", "eth")[1]) == "2011-01-17 11:30"
    assert _hm(sp.session_window("2014-05-26", "rth")[1]) == "2014-05-26 13:00"
    # everything else is unchanged: a normal day, an early close with the NYSE open
    for d in ("2026-07-06", "2026-11-27", "2026-12-24"):
        assert _hm(sp.session_window(d, "rth")[1]) == f"{d} 16:00"
        assert _hm(sp.session_window(d, "eth")[1]) == f"{d} 17:00"


@pytest.mark.parametrize("tf,n,last", [(1, 210, "12:59"), (2, 105, "12:58"), (5, 42, "12:55"), (15, 14, "12:45"),
                                       (30, 7, "12:30"), (60, 4, "12:30")])
def test_a_holiday_rth_session_derives_42_five_minute_bars(tf, n, last):
    nt = _span_minutes([("2026-07-03 09:30", "2026-07-03 13:15")])                 # a stray quarter-hour after the halt
    got = sp.derive(nt, tf, "rth", "2026-07-03")
    assert len(got) == n and sp._hhmm(got["time"].iloc[0]) == "09:30" and sp._hhmm(got["time"].iloc[-1]) == last


HDAYS = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]     # Wed, Thu, Fri = Independence Day (observed), Mon


def _holiday_rth():
    spans = [(f"{d} 09:30", f"{d} {'13:00' if d == '2026-07-03' else '16:00'}") for d in HDAYS]
    return _span_minutes(spans)


@pytest.mark.parametrize("tf", [1, 2, 5, 60])
def test_a_missing_holiday_session_that_nt_holds_whole_is_written(tf):
    full = _holiday_rth()
    whole = pd.concat([sp.derive(full, tf, "rth", d) for d in HDAYS], ignore_index=True)
    a, b = (sp._epoch(x) for x in sp.session_window("2026-07-03", "rth"))
    holed = whole[(whole["time"] < a) | (whole["time"] >= b)].reset_index(drop=True)
    new, rep = sp.fill_plan(holed, full, tf, "rth", HDAYS[0], HDAYS[-1], 0.0, accept="hlv")
    assert rep["sessions"] == {"held": 3, "truncated": 0, "missing": 1, "replaced": 0}
    assert rep["sessions_written"] == ["2026-07-03"] and rep["holiday_sessions_written"] == ["2026-07-03"]
    assert rep["sessions_skipped"] == [] and rep["bars_added"] == {1: 210, 2: 105, 5: 42, 60: 4}[tf]
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


@pytest.mark.parametrize("tf", [1, 5])
def test_a_truncated_holiday_eth_session_is_completed(tf):
    """2026-06-19 in the 1m ETH masters / 07-03 in the 5m ones: the master holds only the evening before (18:00-23:58)."""
    spans = [("2026-07-01 18:00", "2026-07-02 17:00"), ("2026-07-02 18:00", "2026-07-03 13:00"),
             ("2026-07-05 18:00", "2026-07-06 17:00")]
    full = _span_minutes(spans)
    days = ["2026-07-02", "2026-07-03", "2026-07-06"]
    whole = pd.concat([sp.derive(full, tf, "eth", d) for d in days], ignore_index=True)
    assert len(sp.derive(full, tf, "eth", "2026-07-03")) == {1: 1140, 5: 228}[tf]
    cut = _et("2026-07-02", "23:59") if tf == 1 else _et("2026-07-03", "00:00")
    b = sp._epoch(sp.session_window("2026-07-03", "eth")[1])
    m = whole[(whole["time"] < cut) | (whole["time"] >= b)].reset_index(drop=True)
    new, rep = sp.fill_plan(m, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"] == {"held": 2, "truncated": 1, "missing": 0, "replaced": 0}
    assert rep["sessions_written"] == ["2026-07-03"] and rep["holiday_sessions_written"] == ["2026-07-03"]
    assert len(new) == len(whole) and rep["bars_added"] == {1: 1140 - 359, 5: 228 - 72}[tf]
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


def test_a_non_holiday_early_ending_session_is_still_skipped_or_refused():
    """Thanksgiving week: Thursday (a holiday session) is written; Friday's 13:15 early close (NYSE open, not a holiday
    session) is skipped when missing; a truncated normal day whose NT minutes stop at 12:59 is still refused."""
    days = ["2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"]
    ends = {"2026-11-26": "13:00", "2026-11-27": "13:15"}
    full = _span_minutes([(f"{d} 09:30", f"{d} {ends.get(d, '16:00')}") for d in days])
    m = pd.concat([sp.derive(full, 5, "rth", d) for d in days[:2]], ignore_index=True)
    new, rep = sp.fill_plan(m, full, 5, "rth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == ["2026-11-26"] and rep["sessions"]["missing"] == 1
    assert len(rep["sessions_skipped"]) == 1 and rep["sessions_skipped"][0].startswith("2026-11-27 (short session")
    a, b = (sp._epoch(x) for x in sp.session_window("2026-11-27", "rth"))
    assert not ((new["time"] >= a) & (new["time"] < b)).any() and rep["bars_added"] == 42
    # a normal day the master holds truncated at 10:58, NT stopping at 12:59: a bad pull, refused
    short = full[~((full["time"] >= _et(days[1], "13:00")) & (full["time"] < _et(days[1], "16:00")))]
    trunc = m[~((m["time"] >= _et(days[1], "10:55")) & (m["time"] < _et(days[1], "16:00")))]
    with pytest.raises(sp.Refused, match="short of the session's last minute"):
        sp.fill_plan(trunc, short, 5, "rth", days[0], days[-1], 0.0, accept="hlv")


def test_eth_sessions_follow_the_cme_daily_close_eras():
    """The masters' last ETH minute (review 10-19): through 2012-11-16 17:29 Mon-Thu and 16:14 Fri, 2012-11-19 ..
    2015-09-18 17:14 (Fridays too), since 2015-09-21 16:59. RTH is 16:00 throughout."""
    for d, end in (("2011-03-08", "17:30"), ("2012-11-15", "17:30"), ("2011-03-11", "16:15"), ("2012-11-16", "16:15"),
                   ("2012-11-19", "17:15"), ("2012-11-30", "17:15"), ("2014-06-12", "17:15"), ("2015-09-18", "17:15"),
                   ("2015-09-21", "17:00"), ("2026-07-10", "17:00")):
        assert _hm(sp.session_window(d, "eth")[1]) == f"{d} {end}", d
        assert _hm(sp.session_window(d, "rth")[1]) == f"{d} 16:00", d
    assert _hm(sp.session_window("2011-01-17", "eth")[1]) == "2011-01-17 11:30"     # a holiday keeps its own halt
    days = ["2014-06-11", "2014-06-12", "2014-06-13"]
    full = _span_minutes([(f"{pd.Timestamp(d) - pd.Timedelta(days=1):%Y-%m-%d} 18:00", f"{d} 17:15") for d in days])
    assert sp._hhmm(sp.derive(full, 5, "eth", days[1])["time"].iloc[-1]) == "17:10"
    whole = pd.concat([sp.derive(full, 5, "eth", d) for d in days], ignore_index=True)
    a, b = (sp._epoch(x) for x in sp.session_window(days[1], "eth"))
    holed = whole[(whole["time"] < a) | (whole["time"] >= b)]
    new, rep = sp.fill_plan(holed, full, 5, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [days[1]] and len(new) == len(whole)
    # the 2014 NT probe pulls stop at 16:59 (today's 17:00 template): a missing 2014 session from them is refused
    no_tail = full[~((full["time"] >= _et(days[1], "17:00")) & (full["time"] < b))]
    with pytest.raises(sp.Refused, match="not the whole session"):
        sp.fill_plan(holed, no_tail, 5, "eth", days[0], days[-1], 0.0, accept="hlv")


def _eth_spans(days, ends):
    return [(f"{pd.Timestamp(d) - pd.Timedelta(days=1):%Y-%m-%d} 18:00", f"{d} {ends(d)}") for d in days]


@pytest.mark.parametrize("tf", [1, 5])
def test_a_2011_week_held_to_1729_and_friday_to_1614_is_held_not_truncated(tf):
    """Review 10-19: the 17:15 window cut 2010-2012 Mon-Thu sessions mid-trading (the masters hold 17:15-17:29) and
    put Fridays an hour past their 16:15 close, so a perfect pull refused ('the master stops at 17:10'). Under the
    era windows every session is HELD, and a missing Wednesday is written whole to 17:29."""
    days = ["2011-03-07", "2011-03-08", "2011-03-09", "2011-03-10", "2011-03-11"]
    full = _span_minutes(_eth_spans(days, lambda d: "16:15" if pd.Timestamp(d).weekday() == 4 else "17:30"))
    whole = pd.concat([sp.derive(full, tf, "eth", d) for d in days], ignore_index=True)
    assert sp._hhmm(sp.derive(full, tf, "eth", days[1])["time"].iloc[-1]) == ("17:29" if tf == 1 else "17:25")
    assert sp._hhmm(sp.derive(full, tf, "eth", days[4])["time"].iloc[-1]) == ("16:14" if tf == 1 else "16:10")
    new, rep = sp.fill_plan(whole, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"]["held"] == 5 and rep["sessions_written"] == [] and rep["bars_added"] == 0
    a, b = (sp._epoch(x) for x in sp.session_window(days[2], "eth"))
    holed = whole[(whole["time"] < a) | (whole["time"] >= b)]
    new, rep = sp.fill_plan(holed, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [days[2]] and rep["sessions"]["held"] == 4
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


@pytest.mark.parametrize("tf", [1, 5])
def test_a_thin_tail_both_sources_lack_is_held_but_a_master_bar_cut_short_still_refuses(tf):
    """Review 10-19: NQ 2010-07-08 has no print after 17:21 in the master or a pull. Both stop at the same bar short
    of the 17:30 close: HELD, nothing written (it refused 're-pull'). A master whose last bar differs from NT's, a
    master that stops a bar earlier than NT, a tail more than THIN_TAIL_MIN short, or an RTH session still refuses."""
    days = ["2011-03-07", "2011-03-08", "2011-03-09"]
    full = _span_minutes(_eth_spans(days, lambda d: "17:30"))
    full = full[~((full["time"] >= _et(days[1], "17:24")) & (full["time"] < _et(days[1], "17:30")))]  # last 17:23
    whole = pd.concat([sp.derive(full, tf, "eth", d) for d in days], ignore_index=True)
    assert sp._hhmm(whole[whole["time"] < _et(days[1], "17:30")]["time"].max()) == ("17:23" if tf == 1 else "17:20")
    new, rep = sp.fill_plan(whole, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"]["held"] == 3 and rep["sessions_written"] == [] and rep["bars_added"] == 0
    bad = whole.copy()                                           # the master's last bar is not NT's: cut short
    bad.loc[bad["time"] == _et(days[1], "17:23" if tf == 1 else "17:20"), "volume"] //= 2
    with pytest.raises(sp.Refused, match="short of the session's last minute"):
        sp.fill_plan(bad, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    early = whole[~((whole["time"] >= _et(days[1], "17:15")) & (whole["time"] < _et(days[1], "17:30")))]
    with pytest.raises(sp.Refused, match="short of the session's last minute"):   # the master stops before NT does
        sp.fill_plan(early, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    gap = full[~((full["time"] >= _et(days[1], "17:15")) & (full["time"] < _et(days[1], "17:30")))]
    m = pd.concat([sp.derive(gap, tf, "eth", d) for d in days], ignore_index=True)
    with pytest.raises(sp.Refused, match="short of the session's last minute"):  # 17:14: more than 10 minutes short
        sp.fill_plan(m, gap, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    rth = _span_minutes([(f"{d} 09:30", f"{d} 16:00") for d in days])          # RTH: the 16:00 close always trades
    rth = rth[~((rth["time"] >= _et(days[1], "15:54")) & (rth["time"] < _et(days[1], "16:00")))]  # last 15:53
    m = pd.concat([sp.derive(rth, tf, "rth", d) for d in days], ignore_index=True)
    with pytest.raises(sp.Refused, match="short of the session's last minute"):
        sp.fill_plan(m, rth, tf, "rth", days[0], days[-1], 0.0, accept="hlv")


@pytest.mark.parametrize("tf", [1, 5])
def test_an_eth_special_closure_night_the_master_holds_is_neither_an_anchor_nor_a_refusal(tf):
    """2025-01-09 (Carter funeral): the ETH masters hold the 18:00-09:29 night before the closure and NT stops there
    too. Review 10-19: it read as TRUNCATED and refused the whole master ('re-pull'); now it is skipped whatever the
    master holds, and the missing 01-08 around it is still written."""
    days = ["2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"]
    full = _span_minutes(_eth_spans(days, lambda d: "09:30" if d == "2025-01-09" else "17:00"))
    whole = pd.concat([sp.derive(full, tf, "eth", d) for d in days], ignore_index=True)
    a, b = (sp._epoch(x) for x in sp.session_window(days[1], "eth"))
    holed = whole[(whole["time"] < a) | (whole["time"] >= b)]
    new, rep = sp.fill_plan(holed, full, tf, "eth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [days[1]] and rep["sessions"] == {"held": 2, "truncated": 0, "missing": 1,
                                                                         "replaced": 0}
    assert rep["sessions_skipped"] == ["2025-01-09 (no regular CME session: a special closure / Good Friday overnight, "
                                       "left as the master holds it)"]
    assert np.allclose(new[["time", "open", "high", "low", "close", "volume"]].values,
                       whole[["time", "open", "high", "low", "close", "volume"]].values)


def test_a_thin_2m_holiday_whose_last_pair_starts_at_1257_is_held():
    """Review 10-19: NQ 2020-01-20 (MLK) has no 12:25 minute, so the 2m rows pair onto odd minutes after it and the
    master's last pair starts 12:57 (its trailing single 12:59 minute left out). That is HELD - an anchor, nothing
    rewritten - not a truncation that appends a one-minute 12:59 '2m' bar."""
    days = ["2020-01-16", "2020-01-17", "2020-01-20", "2020-01-21"]                # Thu, Fri, MLK, Tue
    full = _span_minutes([(f"{d} 09:30", f"{d} {'13:00' if d == '2020-01-20' else '16:00'}") for d in days])
    full = full[full["time"] != _et("2020-01-20", "12:25")].reset_index(drop=True)
    der = sp.derive(full, 2, "rth", "2020-01-20")
    assert [sp._hhmm(t) for t in der["time"].iloc[-2:]] == ["12:57", "12:59"]
    m = pd.concat([sp.derive(full, 2, "rth", d) for d in days], ignore_index=True)
    m = m[m["time"] != _et("2020-01-20", "12:59")].reset_index(drop=True)
    new, rep = sp.fill_plan(m, full, 2, "rth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"]["held"] == 4 and rep["sessions_written"] == [] and rep["bars_added"] == 0
    assert (new["time"].values == m["time"].values).all()
    # a 2m master that really stops early on the holiday is still TRUNCATED and completed
    cut = m[~((m["time"] >= _et("2020-01-20", "11:59")) & (m["time"] < _et("2020-01-20", "13:00")))]
    new, rep = sp.fill_plan(cut, full, 2, "rth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"]["truncated"] == 1 and rep["sessions_written"] == ["2020-01-20"]
    # NQ 2011-05-30 (Memorial Day, 11:30 halt, 95 of 120 minutes): pairs far off the grid, last pair 11:25-11:26 and a
    # single 11:29 minute the master leaves out - HELD by NT's own pairing, nothing appended
    days = ["2011-05-26", "2011-05-27", "2011-05-30", "2011-05-31"]
    full = _span_minutes([(f"{d} 09:30", f"{d} {'11:30' if d == '2011-05-30' else '16:00'}") for d in days])
    full = full[~full["time"].isin([_et("2011-05-30", hm) for hm in ("10:00", "11:27", "11:28")])].reset_index(drop=True)
    der = sp.derive(full, 2, "rth", "2011-05-30")
    assert [sp._hhmm(t) for t in der["time"].iloc[-2:]] == ["11:25", "11:29"]
    m = pd.concat([sp.derive(full, 2, "rth", d) for d in days], ignore_index=True)
    m = m[m["time"] != _et("2011-05-30", "11:29")].reset_index(drop=True)
    new, rep = sp.fill_plan(m, full, 2, "rth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions"]["held"] == 4 and rep["sessions_written"] == [] and rep["bars_added"] == 0


def test_no_full_reference_session_refuses_the_master_instead_of_exiting():
    """Review 10-19: NQ's thin 2014 overnights (856-1317 minutes) have no 1300-minute reference session; that used to
    raise SystemExit, which run_window does not catch, so the whole run aborted instead of refusing one master."""
    thin = _span_minutes(_eth_spans(["2014-06-10", "2014-06-11"], lambda d: "08:00"))
    with pytest.raises(sp.Refused, match="no full reference session"):
        sp.reference_date(thin, "2014-06-12", "eth")


def test_an_nyse_special_closure_is_never_an_rth_session():
    """2025-01-09 (President Carter's funeral): NYSE closed, no CME equity-index RTH session - never written, even if
    an NT file held whole-looking minutes that day. Same for the other special closures and for Good Friday. (ETH:
    the CME traded the night before - see the ETH special-closure test.)"""
    for d in ("2012-10-29", "2012-10-30", "2018-12-05", "2025-01-09"):
        assert not sp.is_holiday_session(d)
        assert _hm(sp.session_window(d, "rth")[1]) == f"{d} 16:00"
    days = ["2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"]
    full = _span_minutes([(f"{d} 09:30", f"{d} 16:00") for d in days])
    m = pd.concat([sp.derive(full, 5, "rth", d) for d in days if d != "2025-01-09"], ignore_index=True)
    new, rep = sp.fill_plan(m, full, 5, "rth", days[0], days[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [] and rep["bars_added"] == 0 and len(new) == len(m)
    assert rep["sessions_skipped"] == ["2025-01-09 (no regular CME session: the equity-index tape is closed)"]
    gf = ["2026-04-01", "2026-04-02", "2026-04-03"]                                 # Good Friday 2026-04-03
    full = _span_minutes([(f"{d} 09:30", f"{d} 16:00") for d in gf])
    m = pd.concat([sp.derive(full, 5, "rth", d) for d in gf[:2]], ignore_index=True)
    new, rep = sp.fill_plan(m, full, 5, "rth", gf[0], gf[-1], 0.0, accept="hlv")
    assert rep["sessions_written"] == [] and rep["sessions_skipped"][0].startswith("2026-04-03 (no regular CME session")

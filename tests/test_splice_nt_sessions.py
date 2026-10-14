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
    assert rep["sessions"] == {"held": 2, "truncated": 1, "missing": 1}
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
    """2026-07-03: NYSE closed, CME traded to 13:00 ET; the house masters hold no bars that day, so the fill skips
    it. A missing day whose NT minutes stop one minute before the close is a bad pull and refuses the master."""
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

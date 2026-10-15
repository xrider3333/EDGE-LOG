# splice_nt_sessions.py - fill whole-session holes in the ES/NQ no-adjust masters from NinjaTrader 1-minute history.
#
# WHY (TBIS data QA, MANAGER #44/#49, 2026-10-10). The Databento source stops early on two real sessions,
# 2020-02-28 (last bar 10:58 ET) and 2020-06-30 (10:10 ET), in every ES and NQ master - 1m to 60m, RTH and ETH,
# no-adjust, TradingView and roll-corrected alike - which leaves four daily returns undefined. Nothing in the
# house can rebuild them; PAPER-NT8's EdgeLogHistFetch add-on pulls the missing minutes from NinjaTrader.
#
# WHAT IT DOES, per hole date and root (ES / NQ):
#   1. Reads the NT file: 1-minute bars stamped at bar END (unix UTC). Converts to bar START, the house convention.
#   2. For every registered no-adjust and TradingView master of that root (1m..60m, RTH or ETH) it re-derives bars
#      at the master's timeframe from the NT minutes, with the house rule (tools/refresh_resampled_masters.py):
#      GRID buckets anchored at the session open (09:30 ET RTH, 18:00 ET ETH), labelled by the earliest actual
#      minute; ROW-COUNT pairs for 2m.
#   3. ACCEPTANCE before touching anything, per master: (a) the same rule applied to the house 1m no-adjust master
#      on a full reference session must reproduce that master's own bars exactly (prices; volume too unless the
#      master is a TradingView export) - otherwise the rule is not this master's rule and the master is refused;
#      (b) on the hole day, every bar the master already has that lies wholly before the truncation must agree
#      with the NT-derived bar to within one tick after a CONSTANT level offset (0 for no-adjust; the
#      back-adjustment for a TradingView master). Any refusal names the master and the reason.
#   4. Splice: keep the master's own bars before the truncated bucket, add the NT-derived bars from there to the
#      session end (shifted by that offset), write through the master-write guard (atomic, refuses to lose rows),
#      update the registry row count, and record the splice (NT file sha256, rows added) in the provenance JSON.
# The roll-corrected ADJ/FADJ twins are NOT touched here: rebuild them afterwards with
# tools/build_adjusted_masters.py, then re-run the TTM #459 parity (355 trades, $72,716 on ADJ ES 30m).
#
# WINDOWS (10-14): --from/--to fills every session in a date range that a master is MISSING outright (the July 2026
# 1m hole) as well as truncated ones, with the held sessions in the window as the level check (fill_plan).
# --accept hlv (owner call 10-14) accepts on high/low/volume agreement and records the open/close minute-edge
# differences in the provenance instead of refusing on them.
#
# STUB REPAIR (10-14, MANAGER #65): --date D --repair HH:MM-HH:MM rewrites, in a COMPLETE session, only the bars that
# overlap those ET minutes and disagree with NT (high/low beyond a tick, volume beyond 5%), at most 3 per master, after
# the session's other bars pass the hlv agreement at the master's own level. Before/after go in the provenance.
#
# Run (dry run is the default; nothing is written without --commit):
#   python tools/splice_nt_sessions.py --root ES --date 2020-02-28 --nt C:\EdgeLog\nt_hist\out\ES_0320_1m_20200228.csv
#   python tools/splice_nt_sessions.py --root ES --from 2026-06-30 --to 2026-08-06 --accept hlv --nt <ESU6 file>
#   python tools/splice_nt_sessions.py --root NQ --date 2026-06-30 --repair 10:45-10:55 --nt <NQU6 file>
#   python tools/splice_nt_sessions.py ... --commit
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.master_write import write_master_csv  # noqa: E402

ET = "US/Eastern"
TICK = 0.25
SPLICE_SOURCES = ("db_noadj_rth", "db_noadj_eth", "tv")
TF_MIN = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


# ----------------------------------------------------------------------------- time helpers
def to_et(sec):
    return pd.to_datetime(pd.Series(sec), unit="s", utc=True).dt.tz_convert(ET)


def session_window(date, session):
    """[start, end) of the session that trades on `date` (ET). ETH opens 18:00 ET the evening before."""
    d = pd.Timestamp(date, tz=ET)
    if session == "rth":
        return d + pd.Timedelta(hours=9, minutes=30), d + pd.Timedelta(hours=16)
    return d - pd.Timedelta(hours=6), d + pd.Timedelta(hours=17)


def _epoch(ts):
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp())


# ----------------------------------------------------------------------------- the NT file
def load_nt(path, period_s=60):
    """NinjaTrader HistFetch output -> start-stamped 1m frame (time, open, high, low, close, volume)."""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    need = ("time", "open", "high", "low", "close", "volume")
    missing = [c for c in need if c not in cols]
    if missing:
        raise ValueError(f"{os.path.basename(path)}: missing columns {missing}")
    out = pd.DataFrame({c: df[cols[c]] for c in need})
    out["time"] = out["time"].astype("int64") - period_s          # bar END -> bar START
    return out.sort_values("time").drop_duplicates("time").reset_index(drop=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- the house resample rule
def derive(m1, tf, session, date):
    """Bars at `tf` minutes for one session, from start-stamped 1m bars `m1` (house rule)."""
    s0, s1 = session_window(date, session)
    et = to_et(m1["time"].values)
    keep = ((et >= s0) & (et < s1)).values
    x = m1[keep].copy()
    if x.empty:
        return x
    if tf == 1:
        return x.reset_index(drop=True)
    et = to_et(x["time"].values)
    if tf == 2:                                                   # ROW-COUNT: consecutive pairs from session start
        key = np.arange(len(x)) // 2
    else:                                                         # GRID anchored at the session open
        key = ((et - s0).dt.total_seconds() // (tf * 60)).astype(int).values
    g = x.groupby(key, sort=True)
    return pd.DataFrame({"time": g["time"].first().values, "open": g["open"].first().values,
                         "high": g["high"].max().values, "low": g["low"].min().values,
                         "close": g["close"].last().values, "volume": g["volume"].sum().values})


def _rows_in(df, date, session):
    s0, s1 = session_window(date, session)
    et = to_et(df["time"].values)
    return df[((et >= s0) & (et < s1)).values]


# ----------------------------------------------------------------------------- acceptance + splice
class Refused(Exception):
    pass


def acceptance_reference(master, parent_1m, tf, session, ref_date, check_volume):
    """The rule must reproduce the master's own bars on a full reference session (from the house 1m parent)."""
    want = _rows_in(master, ref_date, session).reset_index(drop=True)
    got = derive(parent_1m, tf, session, ref_date).reset_index(drop=True)
    if len(want) == 0 or len(want) != len(got) or not (want["time"].values == got["time"].values).all():
        raise Refused(f"reference {ref_date}: {len(want)} master bars vs {len(got)} derived - the rule does not "
                      f"reproduce this master's bar times")
    off = (want["close"] - got["close"]).round(6)
    if off.nunique() != 1:
        raise Refused(f"reference {ref_date}: level offset is not constant ({off.min()}..{off.max()})")
    o = float(off.iloc[0])
    for c in ("open", "high", "low"):
        if not np.allclose(want[c] - got[c], o, atol=1e-6):
            raise Refused(f"reference {ref_date}: {c} does not match the rule")
    if check_volume and not (want["volume"].values == got["volume"].values).all():
        raise Refused(f"reference {ref_date}: volume does not match the rule")
    return o


def splice_plan(master, nt_1m, tf, session, date, ref_offset):
    """New master frame with the hole day completed, plus a report. Raises Refused on any disagreement."""
    have = _rows_in(master, date, session)
    if have.empty:
        raise Refused(f"{date}: the master has no bar at all that session - not a truncation, will not guess")
    derived = derive(nt_1m, tf, session, date)
    if derived.empty:
        raise Refused(f"{date}: the NT file has no minutes in this session")
    last_have = int(have["time"].max())
    # COMPLETENESS (10-12): the NT minutes must run from at/before the master's last bar to the session's LAST
    # minute. A pull whose end is one minute short loses exactly the closing minute - the 16:00 close - and a
    # resample would then build a wrong last bar without any other check noticing.
    s0, s1 = session_window(date, session)
    nt_in = nt_1m[(nt_1m["time"] >= _epoch(s0)) & (nt_1m["time"] < _epoch(s1))]
    if int(nt_in["time"].max()) < _epoch(s1) - 60:
        raise Refused(f"{date}: the NT minutes stop at {str(to_et([int(nt_in['time'].max())]).iloc[0])[11:16]} ET, "
                      f"short of the session's last minute ({str(s1 - pd.Timedelta(minutes=1))[11:16]}) - re-pull")
    if int(nt_in["time"].min()) > last_have:
        raise Refused(f"{date}: the NT minutes start after the master's last bar - nothing to check the level on")
    # The master's last bar on the day was built from a truncated source, so it may be partial: every bucket from
    # the one holding the master's last bar onward is replaced; everything before it must agree with NT.
    cut = last_have
    before = derived[derived["time"] < cut].merge(have[have["time"] < cut], on="time", suffixes=("_nt", "_m"))
    if len(before) >= 1:
        off = before["close_m"] - before["close_nt"]
    else:
        # A long bar (60m) cut in its first hour has no complete bar before it. Its OPEN is still final - it is
        # the bucket's first minute, which the truncated source did hold - so the level is checked on that one price.
        before = derived[derived["time"] == cut].merge(have[have["time"] == cut], on="time", suffixes=("_nt", "_m"))
        if len(before) < 1:
            raise Refused(f"{date}: no overlapping bar before the truncation to check the NT level against")
        off = before["open_m"] - before["open_nt"]
    level = float(off.median())
    if abs(level - ref_offset) > TICK + 1e-9:
        raise Refused(f"{date}: NT level offset {level:+.2f} differs from the master's own {ref_offset:+.2f}")
    agree = (off - level).abs() <= TICK + 1e-9
    if agree.mean() < 0.9:
        raise Refused(f"{date}: only {agree.mean():.0%} of {len(before)} overlapping bars agree within one tick")
    add = derived[derived["time"] >= cut].copy()
    if "source" in master.columns:                                # the masters' row-provenance column
        add["source"] = "nt_hist_splice"
    # The master's OWN offset (exact, from the reference session) - not the measured one, which on a one-bar
    # overlap is a single print and can sit a tick away (NQ 60m 2020-06-30 measured +0.25).
    for c in ("open", "high", "low", "close"):
        add[c] = add[c] + ref_offset
    s1 = _epoch(session_window(date, session)[1])
    replace = ((master["time"] >= cut) & (master["time"] < s1)).values
    stray = master[replace & ~master["time"].isin(add["time"]).values]
    if len(stray):
        raise Refused(f"{date}: {len(stray)} master bar(s) after the truncation are not in the NT data")
    new = pd.concat([master[~replace], add[list(master.columns)]], ignore_index=True)
    new = new.sort_values("time").reset_index(drop=True)
    if new["time"].duplicated().any():
        raise Refused(f"{date}: splice would duplicate a timestamp")
    rep = dict(overlap_bars=len(before), overlap_agree=float(agree.mean()), max_overlap_diff=float((off - level).abs().max()),
               level_offset=level, replaced_from=str(to_et([cut]).iloc[0])[:16], bars_added=len(new) - len(master),
               bars_written_for_day=len(add))
    return new, rep


# ----------------------------------------------------------------------------- window fills + acceptance rules
# Owner call 10-14 (MANAGER #59): fill NQ 2020-02-28 and the July 2026 1m hole, accepting on high/low/volume
# agreement. Two feeds that put a print on the other side of a minute boundary disagree on that minute's open
# and close, never on its range or its traded size (NQ 2020-02-28: highs and lows identical on 88 of 88 minutes,
# opens/closes apart on 16 by up to 2 points). Those open/close differences are counted and recorded in the
# provenance - not used to refuse. Measured 10-14 on every overlap (NQ Feb, ES/NQ July, RTH and ETH): highs/lows
# within a tick on 99.1-100% of bars, volume within 5% on 98.5-100%.
ACCEPT_RULES = ("close", "hlv")
HLV_MIN_HL = 0.98      # share of overlap bars whose high AND low sit within one tick of the level
HLV_MIN_VOL = 0.95     # share whose volume is within VOL_TOL (not checked for a TradingView master)
VOL_TOL = 0.05
# A MISSING session that NT holds from the open but that ends this many minutes or more before the regular close is a
# short session (an early close, or CME trading through an NYSE holiday) - skipped and reported, never written. The
# house masters hold none for 2026-07-03 (NYSE closed, CME short session to 13:00). A pull that stops a minute or
# two short of the close is a bad pull, not a short session, and is still refused.
SHORT_SESSION_MIN = 30


def _hhmm(sec):
    return str(to_et([int(sec)]).iloc[0])[11:16]


def agreement(both, accept="close", check_volume=True):
    """(level, stats, ok, why) on overlapping bars: `both` has the master's columns as *_m and NT's as *_nt.

    close (the original rule): closes within one tick of one constant level on 90% of bars.
    hlv: highs and lows within one tick on HLV_MIN_HL of bars and volume within VOL_TOL on HLV_MIN_VOL."""
    if accept == "close":
        off = both["close_m"] - both["close_nt"]
        level = float(off.median())
        agree = (off - level).abs() <= TICK + 1e-9
        stats = dict(rule="close", overlap_bars=len(both), agree=round(float(agree.mean()), 4),
                     max_diff=float((off - level).abs().max()))
        return level, stats, agree.mean() >= 0.9, \
            f"only {agree.mean():.0%} of {len(both)} overlapping bars agree within one tick"
    dh, dl = both["high_m"] - both["high_nt"], both["low_m"] - both["low_nt"]
    level = float(pd.concat([dh, dl]).median())
    hl = ((dh - level).abs() <= TICK + 1e-9) & ((dl - level).abs() <= TICK + 1e-9)
    vol = (both["volume_m"] - both["volume_nt"]).abs() / both["volume_m"].clip(lower=1) <= VOL_TOL
    do = (both["open_m"] - both["open_nt"] - level).abs()
    dc = (both["close_m"] - both["close_nt"] - level).abs()
    stats = dict(rule="hlv", overlap_bars=len(both), agree=round(float(hl.mean()), 4),
                 max_diff=float(max((dh - level).abs().max(), (dl - level).abs().max())),
                 volume_within_5pct=round(float(vol.mean()), 4) if check_volume else None,
                 open_close_differ=int(((do > TICK + 1e-9) | (dc > TICK + 1e-9)).sum()),
                 max_open_close_diff=float(max(do.max(), dc.max())))
    ok = hl.mean() >= HLV_MIN_HL and (not check_volume or vol.mean() >= HLV_MIN_VOL)
    why = (f"high/low within one tick on {hl.mean():.1%} of {len(both)} overlapping bars (need {HLV_MIN_HL:.0%})"
           + (f", volume within 5% on {vol.mean():.1%} (need {HLV_MIN_VOL:.0%})" if check_volume else ""))
    return level, stats, ok, why


def nt_sessions(nt_1m, session, d0, d1):
    """Weekdays in [d0, d1] on which the NT file has minutes inside the session."""
    out = []
    for d in pd.bdate_range(d0, d1).strftime("%Y-%m-%d"):
        a, b = (_epoch(x) for x in session_window(d, session))
        if ((nt_1m["time"] >= a) & (nt_1m["time"] < b)).any():
            out.append(d)
    return out


def _last_bucket(a, b, tf):
    """Start of the session's last bar at `tf` minutes (grid from the open; 2m rows pair from the open)."""
    step = tf * 60
    return a + ((b - 60 - a) // step) * step


def fill_plan(master, nt_1m, tf, session, d0, d1, ref_offset, accept="close", check_volume=True, replace_from=None):
    """New master frame with every session in [d0, d1] that the master is MISSING or holds TRUNCATED rebuilt from NT.

    Each NT session is HELD (the master reaches its last bar: an anchor, nothing written), TRUNCATED (the master
    stops early: its bars before the cut are anchors, the cut bucket onward is written) or MISSING (no master bar:
    the whole session is written). The level is measured on every anchor bar in the window together, so a run of
    missing days is pinned by the held sessions around it. A written session must be whole in NT - from its first
    minute (MISSING) or from before the cut (TRUNCATED) to its last minute - or the master is refused.

    replace_from (MANAGER #67, 10-14): every session on or after that date that the master HOLDS is REPLACED -
    rewritten whole from NT, whatever the master holds (Yahoo bars whose opens/closes sit on the other side of the
    bar boundary). Those sessions are never part of the level check; the sessions before replace_from are. NT must
    hold the session from its first minute through everything the master holds (an early close ends early)."""
    sessions = nt_sessions(nt_1m, session, d0, d1)
    if not sessions:
        raise Refused(f"{d0}..{d1}: the NT file has no minutes in any {session.upper()} session")
    pool, writes, counts, cut_bars, skipped = [], [], {"held": 0, "truncated": 0, "missing": 0, "replaced": 0}, [], []
    for d in sessions:
        a, b = (_epoch(x) for x in session_window(d, session))
        nt_in = nt_1m[(nt_1m["time"] >= a) & (nt_1m["time"] < b)]
        first, last = int(nt_in["time"].min()), int(nt_in["time"].max())
        whole_end = last >= b - 60
        der = derive(nt_1m, tf, session, d)
        if not whole_end and tf > 1:
            der = der.iloc[:-1]                        # the bucket holding NT's last minute may be short
        have = master[(master["time"] >= a) & (master["time"] < b)]
        if have.empty:
            if first <= a and last < b - SHORT_SESSION_MIN * 60:
                skipped.append(f"{d} (short session {_hhmm(first)}..{_hhmm(last + 60)} ET)")
                continue
            if not whole_end or first > a:
                raise Refused(f"{d}: the master has no bar that session and the NT minutes run {_hhmm(first)}.."
                              f"{_hhmm(last)} ET, not the whole session - re-pull")
            writes.append((d, a, b, der)); counts["missing"] += 1
            continue
        last_have = int(have["time"].max())
        if replace_from and d >= replace_from:         # REPLACED: written whole from NT, never an anchor
            need = b - 60 if last_have >= _last_bucket(a, b, tf) else last_have
            if first > a or last < need:
                raise Refused(f"{d}: replacing a session needs NT minutes from the open through {_hhmm(need)} ET; "
                              f"they run {_hhmm(first)}..{_hhmm(last)} ET - re-pull")
            full = derive(nt_1m, tf, session, d)         # untrimmed: an early close ends where the master does
            writes.append((d, a, b, full if whole_end else full[full["time"] <= last_have])); counts["replaced"] += 1
            continue
        if last_have >= _last_bucket(a, b, tf):        # HELD: an anchor only
            pool.append(der.merge(have, on="time", suffixes=("_nt", "_m"))); counts["held"] += 1
            continue
        if not whole_end:
            raise Refused(f"{d}: the master stops at {_hhmm(last_have)} ET and the NT minutes stop at {_hhmm(last)} ET, "
                          f"short of the session's last minute - re-pull")
        if first > last_have:
            raise Refused(f"{d}: the NT minutes start after the master's last bar - nothing to check the level on")
        pool.append(der[der["time"] < last_have].merge(have[have["time"] < last_have], on="time",
                                                       suffixes=("_nt", "_m")))
        cut_bars.append(der[der["time"] == last_have].merge(have[have["time"] == last_have], on="time",
                                                            suffixes=("_nt", "_m")))
        writes.append((d, last_have, b, der[der["time"] >= last_have])); counts["truncated"] += 1
    both = pd.concat(pool, ignore_index=True) if pool else pd.DataFrame()
    if both.empty:
        # A 60m master cut in its first hour, alone in the window: the partial bar's OPEN is final (its first minute
        # was in the truncated source), so the level is checked on that one price and the closes rule applies.
        both = pd.concat(cut_bars, ignore_index=True) if cut_bars else pd.DataFrame()
        if both.empty:
            raise Refused(f"{d0}..{d1}: no bar the master already holds overlaps the NT minutes - nothing to check "
                          f"the level on")
        both = both.assign(close_m=both["open_m"], close_nt=both["open_nt"])
        accept = "close"
    level, stats, ok, why = agreement(both, accept, check_volume)
    if abs(level - ref_offset) > TICK + 1e-9:
        raise Refused(f"{d0}..{d1}: NT level offset {level:+.2f} differs from the master's own {ref_offset:+.2f}")
    if not ok:
        raise Refused(f"{d0}..{d1}: {why}")
    new, added = master, []
    for d, start, end, rows in writes:
        add = rows.copy()
        if "source" in master.columns:
            add["source"] = "nt_hist_splice"
        for c in ("open", "high", "low", "close"):
            add[c] = add[c] + ref_offset              # the master's own exact offset, not the measured one
        replace = ((new["time"] >= start) & (new["time"] < end)).values
        stray = new[replace & ~new["time"].isin(add["time"]).values]
        if len(stray):
            raise Refused(f"{d}: {len(stray)} master bar(s) after the cut are not in the NT data")
        new = pd.concat([new[~replace], add[list(master.columns)]], ignore_index=True)
        added.append(d)
    new = new.sort_values("time").reset_index(drop=True)
    if new["time"].duplicated().any():
        raise Refused(f"{d0}..{d1}: the fill would duplicate a timestamp")
    rep = dict(stats, level_offset=level, sessions=counts, sessions_written=added, sessions_skipped=skipped,
               bars_added=len(new) - len(master), replace_from=replace_from)
    return new, rep


# ----------------------------------------------------------------------------- stub-bar repair
# MANAGER #65 (10-14). The source behind 2026-06-30 stopped mid-morning (NQ 10:49, ES 10:44 ET) and the rest of the
# day came from another feed, so the bar holding the cut is a STUB: NQ 5m 10:50 traded 999 of 5,309 contracts and
# misses the 30310.50 low, the NQ 1m 10:50 minute has volume 0, and the 30m/60m bars around them run short on volume.
# The session is complete, so this is not a fill. --repair rewrites only the bars that overlap the named minutes AND
# disagree with NT, after every other bar of the session that NT holds whole has passed the hlv agreement at the
# master's own level.
REPAIR_MAX_BARS = 3    # per master: more than this is a different feed or a different defect, not a stub


def _bucket(t, tf, a, b):
    """[start, end) of the minutes behind the bar labelled `t`: the grid bucket from the session open (2m: the row pair,
    assumed whole)."""
    step = tf * 60
    if tf in (1, 2):
        return t, min(t + step, b)
    s = a + ((t - a) // step) * step
    return s, min(s + step, b)


def repair_plan(master, nt_1m, tf, session, date, minutes, ref_offset, check_volume=True):
    """Master frame with the stub bars of `date` overlapping `minutes` ([m0, m1) epoch seconds) rewritten from NT.

    A bar is rewritten only when NT holds every minute behind it and it disagrees with the NT bar: high or low more
    than a tick from the master's offset, or (when checked) volume more than VOL_TOL from NT's. Row count unchanged."""
    a, b = (_epoch(x) for x in session_window(date, session))
    m0, m1 = minutes
    have = master[(master["time"] >= a) & (master["time"] < b)]
    if have.empty:
        raise Refused(f"{date}: the master has no bar that session - that is a fill, not a repair")
    der = derive(nt_1m, tf, session, date)
    if der.empty:
        raise Refused(f"{date}: the NT file has no minutes in this session")
    nt_t = set(nt_1m["time"].astype("int64").tolist())
    whole = [all(s + 60 * k in nt_t for k in range((e - s) // 60))
             for s, e in (_bucket(int(t), tf, a, b) for t in der["time"])]
    der = der[np.array(whole, bool)].reset_index(drop=True)
    near_m = np.array([s < m1 and e > m0 for s, e in (_bucket(int(t), tf, a, b) for t in have["time"])], bool)
    unseen = sorted(set(have["time"][near_m].astype("int64")) - set(der["time"].astype("int64")))
    if unseen:
        raise Refused(f"{date}: NT does not hold every minute behind the {_hhmm(unseen[0])} ET bar - cannot check it")
    both = der.merge(have, on="time", suffixes=("_nt", "_m"))
    near = both["time"].isin(have["time"][near_m]).values
    rest = both[~near]
    if len(rest) < 2:
        raise Refused(f"{date}: fewer than two other bars to check the NT level on")
    level, stats, ok, why = agreement(rest, "hlv", check_volume)
    if abs(level - ref_offset) > TICK + 1e-9:
        raise Refused(f"{date}: NT level offset {level:+.2f} differs from the master's own {ref_offset:+.2f}")
    if not ok:
        raise Refused(f"{date}: {why}")
    off_h = (both["high_m"] - both["high_nt"] - ref_offset).abs() > TICK + 1e-9
    off_l = (both["low_m"] - both["low_nt"] - ref_offset).abs() > TICK + 1e-9
    off_v = (both["volume_m"] - both["volume_nt"]).abs() > VOL_TOL * both["volume_nt"].clip(lower=1)
    bad = both[near & (off_h | off_l | (off_v if check_volume else False)).values]
    if len(bad) > REPAIR_MAX_BARS:
        raise Refused(f"{date}: {len(bad)} bars in the window disagree with NT (at most {REPAIR_MAX_BARS}) - "
                      f"not a stub")
    new = master.copy()
    fixes = []
    for r in bad.itertuples(index=False):
        i = new.index[new["time"] == r.time][0]
        before = [float(new.at[i, c]) for c in ("open", "high", "low", "close")] + [int(new.at[i, "volume"])]
        for c in ("open", "high", "low", "close"):
            new.at[i, c] = getattr(r, f"{c}_nt") + ref_offset     # the master's own exact offset
        new.at[i, "volume"] = getattr(r, "volume_nt")
        if "source" in new.columns:
            new.at[i, "source"] = "nt_hist_repair"
        fixes.append(dict(time=int(r.time), et=_hhmm(r.time), before=before,
                          after=[float(new.at[i, c]) for c in ("open", "high", "low", "close")]
                          + [int(new.at[i, "volume"])]))
    rep = dict(stats, level_offset=level, window_bars=int(near.sum()), bars_repaired=len(fixes), repairs=fixes)
    return new, rep


# ----------------------------------------------------------------------------- registry + run
def _connect(db):
    # The runner processes poll this sqlite file continuously; a plain connect gives up on their short locks
    # ("database is locked" after the master file was already written, 10-12). Wait for them instead.
    con = sqlite3.connect(db, timeout=120)
    con.execute("PRAGMA busy_timeout = 120000")
    return con


def targets(db, root, date):
    con = _connect(db)
    rows = con.execute("select id, name, filename, timeframe, source, rows, provenance from csv_files "
                       "where is_master=1 and instrument=? and date_from<=? and date_to>=?", (root, date, date)).fetchall()
    con.close()
    return [r for r in rows if r[4] in SPLICE_SOURCES and r[3] in TF_MIN]


def parent_1m(db, root, session):
    con = _connect(db)
    r = con.execute("select filename from csv_files where is_master=1 and instrument=? and timeframe='1m' and source=?",
                    (root, f"db_noadj_{session}")).fetchone()
    con.close()
    if not r:
        raise SystemExit(f"no {root} 1m db_noadj_{session} master registered")
    return r[0]


def reference_date(parent, date, session):
    """The last full session before `date` in the 1m parent."""
    et = to_et(parent["time"].values)
    d = et.dt.strftime("%Y-%m-%d")
    days = sorted(set(d[(et < pd.Timestamp(date, tz=ET)).values]))
    for day in reversed(days[-10:]):
        n = len(_rows_in(parent, day, session))
        if (session == "rth" and n == 390) or (session == "eth" and n >= 1300):
            return day
    raise SystemExit("no full reference session in the 10 days before the hole")


def record_splice(con, mid, provenance, entry, rows, key="splices"):
    try:
        p = json.loads(provenance or "{}")
        if not isinstance(p, dict):
            raise ValueError
    except ValueError:
        p = None
    if p is not None:
        p.setdefault(key, []).append(entry)
        con.execute("update csv_files set rows=?, provenance=? where id=?", (rows, json.dumps(p), mid))
    else:
        con.execute("update csv_files set rows=? where id=?", (rows, mid))


def run(root, date, nt_path, commit=False, db=None, uploads=None, log=print):
    db = db or os.path.join(ROOT, "optimizer_history.db")
    uploads = uploads or os.path.join(ROOT, "augur_uploads")
    nt = load_nt(nt_path)
    nt_sha = sha256(nt_path)
    parents = {}
    results = []
    for mid, name, fn, tf_s, src, nrows, prov in targets(db, root, date):
        session = "eth" if src.endswith("_eth") or "ETH" in name else "rth"
        tf = TF_MIN[tf_s]
        if session not in parents:
            pf = parent_1m(db, root, session)
            parents[session] = pd.read_csv(os.path.join(uploads, pf))
        par = parents[session]
        path = os.path.join(uploads, fn)
        m = pd.read_csv(path)
        try:
            ref = reference_date(par, date, session)
            off = acceptance_reference(m, par, tf, session, ref, check_volume=(src != "tv"))
            new, rep = splice_plan(m, nt, tf, session, date, off)
        except Refused as e:
            log(f"REFUSED  #{mid} {name}: {e}")
            results.append((mid, name, "refused", str(e)))
            continue
        log(f"{'SPLICE ' if commit else 'DRY-RUN'}  #{mid} {name}: +{rep['bars_added']} bars (day rebuilt from "
            f"{rep['replaced_from']}), overlap {rep['overlap_bars']} bars, {rep['overlap_agree']:.0%} within a tick, "
            f"max diff {rep['max_overlap_diff']:.2f}, level {rep['level_offset']:+.2f} (ref {ref})")
        if commit and rep["bars_added"] > 0:
            write_master_csv(new, path, known_rows=nrows)
            con = _connect(db)
            record_splice(con, mid, prov, dict(date=date, nt_file=os.path.basename(nt_path), nt_sha256=nt_sha,
                                                rows_added=rep["bars_added"], at=datetime.now(timezone.utc).isoformat()[:19],
                                                by="tools/splice_nt_sessions.py"), len(new))
            con.commit(); con.close()
        results.append((mid, name, "spliced" if commit else "planned", rep))
    return results


def run_window(root, d0, d1, nt_path, commit=False, accept="close", db=None, uploads=None, log=print,
               sources=None, replace_from=None):
    """fill_plan for every no-adjust / TradingView master of `root` that covers d0: missing and truncated sessions in
    [d0, d1] are rebuilt from the NT file; held sessions are the level check. One provenance entry per master.
    sources: only masters of these registry sources (default SPLICE_SOURCES). replace_from: see fill_plan."""
    if accept not in ACCEPT_RULES:
        raise ValueError(f"accept must be one of {ACCEPT_RULES}")
    db = db or os.path.join(ROOT, "optimizer_history.db")
    uploads = uploads or os.path.join(ROOT, "augur_uploads")
    nt = load_nt(nt_path)
    nt_sha = sha256(nt_path)
    parents, results = {}, []
    for mid, name, fn, tf_s, src, nrows, prov in targets(db, root, d0):
        if sources and src not in sources:
            continue
        session = "eth" if src.endswith("_eth") or "ETH" in name else "rth"
        tf = TF_MIN[tf_s]
        if session not in parents:
            parents[session] = pd.read_csv(os.path.join(uploads, parent_1m(db, root, session)))
        par = parents[session]
        path = os.path.join(uploads, fn)
        m = pd.read_csv(path)
        try:
            ref = reference_date(par, d0, session)
            off = acceptance_reference(m, par, tf, session, ref, check_volume=(src != "tv"))
            new, rep = fill_plan(m, nt, tf, session, d0, d1, off, accept, check_volume=(src != "tv"),
                                 replace_from=replace_from)
        except Refused as e:
            log(f"REFUSED  #{mid} {name}: {e}")
            results.append((mid, name, "refused", str(e)))
            continue
        s = rep["sessions"]
        extra = (f", volume within 5% {rep['volume_within_5pct']:.1%}" if rep.get("volume_within_5pct") is not None else "") \
            + (f", open/close apart on {rep['open_close_differ']} bars (max {rep['max_open_close_diff']:.2f})"
               if rep["rule"] == "hlv" else "")
        log(f"{'SPLICE ' if commit else 'DRY-RUN'}  #{mid} {name}: +{rep['bars_added']} bars; sessions written "
            f"{len(rep['sessions_written'])} ({s['missing']} missing, {s['truncated']} truncated, {s['replaced']} replaced), "
            f"{s['held']} held"
            f"{'; skipped ' + ', '.join(rep['sessions_skipped']) if rep['sessions_skipped'] else ''}; "
            f"overlap {rep['overlap_bars']} bars, {rep['rule']} agree {rep['agree']:.1%}{extra}, level "
            f"{rep['level_offset']:+.2f} (ref {ref})")
        if commit and rep["sessions_written"]:
            write_master_csv(new, path, known_rows=nrows)
            entry = dict(window=[d0, d1], sessions_written=rep["sessions_written"],
                         sessions=rep["sessions"], replace_from=replace_from,
                         sessions_skipped=rep["sessions_skipped"], nt_file=os.path.basename(nt_path),
                         nt_sha256=nt_sha, rows_added=rep["bars_added"], level_offset=rep["level_offset"],
                         acceptance={k: rep[k] for k in ("rule", "overlap_bars", "agree", "max_diff",
                                                         "volume_within_5pct", "open_close_differ",
                                                         "max_open_close_diff") if k in rep},
                         at=datetime.now(timezone.utc).isoformat()[:19], by="tools/splice_nt_sessions.py")
            con = _connect(db)
            record_splice(con, mid, prov, entry, len(new))
            con.commit(); con.close()
        results.append((mid, name, "spliced" if commit else "planned", rep))
    return results


def run_repair(root, date, window, nt_path, commit=False, db=None, uploads=None, log=print):
    """repair_plan for every no-adjust / TradingView master of `root` holding `date`; `window` = ("HH:MM", "HH:MM") ET.
    One provenance entry per repaired master, under "repairs", with every bar's before and after."""
    db = db or os.path.join(ROOT, "optimizer_history.db")
    uploads = uploads or os.path.join(ROOT, "augur_uploads")
    m0, m1 = (_epoch(pd.Timestamp(f"{date} {w}", tz=ET)) for w in window)
    if m1 <= m0:
        raise ValueError(f"empty repair window {window[0]}-{window[1]}")
    nt = load_nt(nt_path)
    nt_sha = sha256(nt_path)
    parents, results = {}, []
    for mid, name, fn, tf_s, src, nrows, prov in targets(db, root, date):
        session = "eth" if src.endswith("_eth") or "ETH" in name else "rth"
        tf = TF_MIN[tf_s]
        if session not in parents:
            parents[session] = pd.read_csv(os.path.join(uploads, parent_1m(db, root, session)))
        par = parents[session]
        path = os.path.join(uploads, fn)
        m = pd.read_csv(path)
        try:
            ref = reference_date(par, date, session)
            off = acceptance_reference(m, par, tf, session, ref, check_volume=(src != "tv"))
            new, rep = repair_plan(m, nt, tf, session, date, (m0, m1), off, check_volume=(src != "tv"))
        except Refused as e:
            log(f"REFUSED  #{mid} {name}: {e}")
            results.append((mid, name, "refused", str(e)))
            continue
        bars = "; ".join(f"{f['et']} {f['before']} -> {f['after']}" for f in rep["repairs"]) or "none disagree"
        log(f"{'REPAIR ' if commit else 'DRY-RUN'}  #{mid} {name}: {rep['bars_repaired']} of {rep['window_bars']} "
            f"window bar(s) rewritten ({bars}); rest of session hlv agree {rep['agree']:.1%}"
            + (f", volume within 5% {rep['volume_within_5pct']:.1%}" if rep.get("volume_within_5pct") is not None else "")
            + f", level {rep['level_offset']:+.2f} (ref {ref})")
        if commit and rep["bars_repaired"] > 0:
            write_master_csv(new, path, known_rows=nrows)
            entry = dict(date=date, window=list(window), repairs=rep["repairs"], nt_file=os.path.basename(nt_path),
                         nt_sha256=nt_sha, level_offset=rep["level_offset"],
                         acceptance={k: rep[k] for k in ("rule", "overlap_bars", "agree", "max_diff",
                                                         "volume_within_5pct", "open_close_differ") if k in rep},
                         at=datetime.now(timezone.utc).isoformat()[:19], by="tools/splice_nt_sessions.py --repair")
            con = _connect(db)
            record_splice(con, mid, prov, entry, len(new), key="repairs")
            con.commit(); con.close()
        results.append((mid, name, ("repaired" if rep["bars_repaired"] else "clean") if commit else "planned", rep))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fill truncated or missing ES/NQ sessions from NinjaTrader 1-minute history.")
    ap.add_argument("--root", required=True, choices=("ES", "NQ"))
    ap.add_argument("--date", help="one truncated session's trade date, YYYY-MM-DD (same as --from D --to D)")
    ap.add_argument("--from", dest="d0", help="first trade date of a window to fill, YYYY-MM-DD")
    ap.add_argument("--to", dest="d1", help="last trade date of the window, YYYY-MM-DD")
    ap.add_argument("--nt", required=True, help="EdgeLogHistFetch output (1m, END-stamped unix UTC)")
    ap.add_argument("--accept", default="close", choices=ACCEPT_RULES,
                    help="close: closes within a tick (default); hlv: highs/lows within a tick + volume within 5%%, "
                         "open/close minute-edge differences recorded, not refused (owner call 10-14)")
    ap.add_argument("--repair", metavar="HH:MM-HH:MM",
                    help="with --date: rewrite the stub bars overlapping these ET minutes from NT (complete sessions only)")
    ap.add_argument("--replace-from", metavar="YYYY-MM-DD",
                    help="with --from/--to: rewrite every session the master HOLDS from this date on, whole, from NT "
                         "(Yahoo bars -> NT bars); the sessions before it are the level check")
    ap.add_argument("--sources", help="comma list of registry sources to touch (default: no-adjust RTH/ETH + tv)")
    ap.add_argument("--commit", action="store_true", help="write; the default is a dry run")
    a = ap.parse_args(argv)
    if a.repair:
        if not a.date:
            ap.error("--repair needs --date")
        res = run_repair(a.root, a.date, tuple(a.repair.split("-")), a.nt, a.commit)
        bad = [r for r in res if r[2] == "refused"]
        print(f"{len(res) - len(bad)} master(s) {'checked/repaired' if a.commit else 'ready'}, {len(bad)} refused."
              + ("" if a.commit else " Dry run - nothing written. Re-run with --commit, then tools/build_adjusted_masters.py."))
        return 1 if bad else 0
    d0, d1 = (a.date, a.date) if a.date else (a.d0, a.d1)
    if not (d0 and d1):
        ap.error("give --date, or --from and --to")
    res = run_window(a.root, d0, d1, a.nt, a.commit, a.accept,
                     sources=tuple(a.sources.split(",")) if a.sources else None, replace_from=a.replace_from)
    bad = [r for r in res if r[2] == "refused"]
    print(f"{len(res) - len(bad)} master(s) {'spliced' if a.commit else 'ready'}, {len(bad)} refused."
          + ("" if a.commit else " Dry run - nothing written. Re-run with --commit, then tools/build_adjusted_masters.py."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

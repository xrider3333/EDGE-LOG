"""Build the pinned side panel for augur_strategies/MISC_NIGHTPERSIST_1_0.py (opus hunt strategy 83, NIGHTPERSIST-120,
cell 83d).

Same inputs, same parsing as the hunt loader C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S83/s83_lib.py load():
  * names = the union of universe_pit100.json (C:/EdgeLog/_anatomy_cache/opus_hunt1109, built by s23_universe.py: each
    year's top 100 by PRIOR-year median dollar volume) keys 2017 .. 2026, SPY excluded, sorted (the hunt read keys
    2017 .. 2025 only = 186 names; the 13 names first listed in 2026 are added at their alphabetical place, which
    leaves the relative column order - the rank tie-break - of the hunt's 186 names unchanged);
  * C:/EdgeLog/alpaca_cache/siporb/daily_split.parquet (symbol, date, o, c) and daily_raw.parquet (symbol, date, c),
    symbol- and date-filtered on read (2016-01-01 .. 2026-06-30), pivot_table'd, cast to float32 (the hunt's order:
    pivot -> reindex(sessions) -> float32; the plugin casts back to float64 exactly as the hunt did);
  * sessions = dates on which >= 50 of the names print in the split file (the hunt's NYSE session rule);
  * SPY from C:/EdgeLog/alpaca_cache/tbis_r3/SPY.csv.gz 10-minute bars (bar START, epoch s UTC -> America/New_York):
    spy_open = the 09:30 bar's open; spy_close = the 15:50 bar's close on a full day, the 12:50 bar's close on a
    half day, the last RTH bar's close on a full day without a 15:50 bar; FULL = not on the frozen NYSE early-close
    list AND SPY has its 15:50 bar. The hunt's list, extended through 2026-06 with 2025-07-03, 2025-11-28 and
    2025-12-24 (the extension tools/misc_aucrev_panel.py and tools/misc_pairz_panel.py use);
  * member = a session-by-name matrix from the universe keys 2017 .. 2026 (2016 rows: nobody).
The panel runs to 2026-06-30 so the engine's 12-month lockbox has prices. THIS SCRIPT COMPUTES NO RETURN, PNL OR
STRATEGY STATISTIC. Besides shapes and the sha256 to pin in the plugin it prints a data QA: the session list against
the hunt's own 186-name rule (<= 2025-06-30), print-presence agreement between the daily open and the daily closes on
member days, SPY clock flags after 2025-06-30, and every day on which a name's split-adjustment factor (split close /
raw close of the SAME day) moves by more than 1 pct from the session before, plus every same-day open-factor vs
close-factor disagreement - names, dates and factor ratios only.

    python tools/misc_nightpersist_panel.py     (writes C:/EdgeLog/alpaca_cache/nightpersist_panel/nightpersist_panel_v1.npz)
Memory: 199 names x ~2,640 sessions x 3 float32 fields + flags ~ 7 MB; the parquet reads are symbol-filtered.
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

NY = "America/New_York"
HUNT = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/"
DAILY = "C:/EdgeLog/alpaca_cache/siporb/daily_%s.parquet"
SPY_FILE = "C:/EdgeLog/alpaca_cache/tbis_r3/SPY.csv.gz"
OUT = "C:/EdgeLog/alpaca_cache/nightpersist_panel/nightpersist_panel_v1.npz"
START = pd.Timestamp("2016-01-01")
CUT_DAY = pd.Timestamp("2026-06-30")
SEAL = pd.Timestamp("2025-06-30")
YEARS = [str(y) for y in range(2017, 2027)]
HUNT_YEARS = [str(y) for y in range(2017, 2026)]
# The hunt's frozen NYSE early-close list (s83_lib.HALF), extended through 2026-06 (2025-07-03, 2025-11-28,
# 2025-12-24; no early close in 2026-01 .. 2026-06).
HALF = pd.to_datetime([
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03",
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"])


def _spy(sess):
    """The hunt's SPY block (s83_lib.load), cut at 2026-06-30 instead of 2025-06-30."""
    x = pd.read_csv(SPY_FILE, usecols=["time", "open", "close"])
    tt = pd.to_datetime(x.time, unit="s", utc=True).dt.tz_convert(NY)
    x["d"] = tt.dt.normalize().dt.tz_localize(None).values
    x["m"] = (tt.dt.hour * 60 + tt.dt.minute).values
    x = x[x.d <= CUT_DAY]
    assert x.d.max() <= CUT_DAY
    so = x[x.m == 570].drop_duplicates("d").set_index("d")["open"].reindex(sess)
    c1550 = x[x.m == 950].drop_duplicates("d").set_index("d")["close"].reindex(sess)
    c1250 = x[x.m == 770].drop_duplicates("d").set_index("d")["close"].reindex(sess)
    ishalf = pd.Series(sess.isin(HALF), index=sess)
    sc = c1550.where(~ishalf, c1250)
    rth = x[(x.m >= 570) & (x.m <= 950)].sort_values("time").groupby("d")["close"].last().reindex(sess)
    nofb = (~ishalf) & c1550.isna()
    sc = sc.where(~nofb, rth)
    full = (~ishalf) & c1550.notna()
    return so, sc, full, ishalf, nofb


def main():
    U = json.load(open(HUNT + "universe_pit100.json"))
    assert all(y in U and len(U[y]) == 100 for y in YEARS), "universe_pit100.json lacks a year key"
    U = {y: [s for s in U[y] if s != "SPY"] for y in YEARS}
    names = sorted(set(sum(U.values(), [])))
    hunt_names = sorted(set(sum([U[y] for y in HUNT_YEARS], [])))
    flt = [("symbol", "in", names), ("date", ">=", START), ("date", "<=", CUT_DAY)]
    t = pq.read_table(DAILY % "split", columns=["symbol", "date", "o", "c"], filters=flt).to_pandas()
    r = pq.read_table(DAILY % "raw", columns=["symbol", "date", "o", "c"], filters=flt).to_pandas()
    for x in (t, r):
        x["date"] = pd.to_datetime(x.date)
        assert x.date.max() <= CUT_DAY
    cnt = t.groupby("date").symbol.nunique()
    sess = cnt.index[cnt >= 50].sort_values()
    # the hunt's own rule on its own names and window: the session list must be the same rows
    th = t[t.symbol.isin(hunt_names) & (t.date <= SEAL)]
    ch = th.groupby("date").symbol.nunique()
    sess_h = ch.index[ch >= 50].sort_values()
    same = sess[sess <= SEAL].equals(sess_h)
    dup = {k: int(x.duplicated(["symbol", "date"]).sum()) for k, x in (("split", t), ("raw", r))}
    O = t.pivot_table(index="date", columns="symbol", values="o").reindex(sess).astype("float32")
    C = t.pivot_table(index="date", columns="symbol", values="c").reindex(sess).astype("float32")
    R = r.pivot_table(index="date", columns="symbol", values="c").reindex(sess).astype("float32")
    RO = r.pivot_table(index="date", columns="symbol", values="o").reindex(sess).astype("float32")   # QA only
    del t, r, th
    missing = [s for s in names if s not in C.columns]
    O, C, R, RO = (z.reindex(columns=names) for z in (O, C, R, RO))
    member = pd.DataFrame(False, index=sess, columns=names)
    for y in YEARS:
        rows = sess.year == int(y)
        if rows.any():
            member.loc[rows, U[y]] = True
    so, sc, full, ishalf, nofb = _spy(sess)
    print("sessions %d (%s .. %s); <= 2025-06-30: %d, identical to the hunt's 186-name rule: %s; duplicate "
          "(symbol, date) rows %s; names %d (hunt 186 + 2026 newcomers %d), no daily rows: %s" % (
              len(sess), sess[0].date(), sess[-1].date(), int((sess <= SEAL).sum()), same, dup, len(names),
              len(names) - len(hunt_names), missing))
    print("SPY clock: full %d, half-day rows %d, full day without a 15:50 bar (last RTH bar used for the close) %s, "
          "no 09:30 bar %s" % (int(full.sum()), int(ishalf.sum()), [str(d.date()) for d in sess[nofb.values]],
                                [str(d.date()) for d in sess[so.isna().values]]))
    lb = sess > SEAL
    print("  after 2025-06-30: sessions %d, not FULL %s" % (
        int(lb.sum()), [str(d.date()) for d in sess[lb & ~full.values]]))

    # ---- QA (no return is computed: print presence, and same-day ratios of two price series)
    for lab, rows in (("<= 2025-06-30", ~lb), ("lockbox 2025-07-01 .. 2026-06-30", lb)):
        mem = member.values[rows]
        o_ok = O.notna().values[rows]
        cr_ok = (C.notna() & R.notna()).values[rows]
        print("presence on member days, %s: member-days %d | open print but no close print %d | close prints but no "
              "open print %d | neither %d" % (lab, int(mem.sum()), int((mem & o_ok & ~cr_ok).sum()),
                                               int((mem & ~o_ok & cr_ok).sum()), int((mem & ~o_ok & ~cr_ok).sum())))
    fc = (C.astype(float) / R.astype(float))
    fo = (O.astype(float) / RO.astype(float))
    jump = fc / fc.shift(1)                                   # split-adjustment factor change, consecutive sessions
    big = (np.abs(np.log(jump)) > np.log(1.01)) & jump.notna()
    oc = (np.abs(np.log(fo / fc)) > np.log(1.01)) & (fo / fc).notna()
    mem2 = member | member.shift(1, fill_value=False)         # a member on the day or on the session before (held into it)
    for lab, rows in (("<= 2025-06-30", ~lb), ("lockbox 2025-07-01 .. 2026-06-30", lb)):
        b = big[rows]
        m2 = mem2[rows]
        ev = [(s, str(d.date()), round(float(jump.loc[d, s]), 4), bool(m2.loc[d, s]))
              for s in names for d in b.index[b[s].values]]
        print("QA split-factor changes (split close / raw close moves > 1 pct session to session), %s: %d -> %s" % (
            lab, len(ev), ev if len(ev) <= 60 else ev[:60] + ["..."]))
        o2 = oc[rows]
        ev2 = [(s, str(d.date()), round(float(fo.loc[d, s] / fc.loc[d, s]), 4))
               for s in names for d in o2.index[o2[s].values]]
        print("QA same-day open factor vs close factor disagreement > 1 pct, %s: %d -> %s" % (
            lab, len(ev2), ev2 if len(ev2) <= 40 else ev2[:40] + ["..."]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in sess], dtype="int64"),
             names=np.array(names), o=O.values.astype("float32"), c=C.values.astype("float32"),
             r=R.values.astype("float32"), member=member.values.astype(bool),
             full=np.asarray(full, bool), half=np.asarray(ishalf, bool),
             spy_open=so.values.astype(np.float64), spy_close=sc.values.astype(np.float64))
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    yrs = {y: int(member[sess.year == int(y)].any(axis=0).sum()) for y in YEARS}
    print("members with daily rows by year %s" % yrs)
    print("%s  prices %s  sessions %s .. %s  sha256 %s" % (OUT, C.shape, sess[0].date(), sess[-1].date(), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())

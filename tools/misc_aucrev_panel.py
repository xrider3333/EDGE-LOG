"""Build the pinned side panel for augur_strategies/MISC_AUCREV_1_0.py (opus hunt strategy 85, AUCREV10, cell 85a).

Same inputs, same parsing as the hunt builder C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S85/s85_build.py:
  * 10-minute SIP split-adjusted bars C:/EdgeLog/alpaca_cache/tbis_r3/<SYM>.csv.gz and eodrev_u100/<SYM>.csv.gz
    (eodrev_u100 wins a name found in both, as in the hunt; no name is in both today). time = bar START, epoch s UTC
    -> America/New_York. Read as float64 and cast to float32 (the hunt's order); duplicate (day, minute) rows -> the
    first kept. Only the bars starting 15:30, 15:40 and 15:50 are kept (close 15:30 = the 15:40 price, close 15:40 =
    the 15:50 price, open / close 15:50 = the entry print / the 16:00 bar close);
  * sessions = dates on which SPY (tbis_r3) has a regular bar (starts 09:30 .. 15:50) from 2016-01-04;
    FULL = SPY has a 15:50 bar AND the day is not on the frozen NYSE early-close list (the hunt's list, extended to
    2026-06 with 2025-07-03, 2025-11-28, 2025-12-24 - the same extension as tools/misc_pairz_panel.py);
  * the bar fields are stored RAW (post-close prints on half days kept: the hunt's beta reads them); the plugin
    blanks half-day rows for trading exactly as the hunt's F frames do;
  * daily close c from C:/EdgeLog/alpaca_cache/siporb/daily_split.parquet (official close, split-adjusted) and
    daily_raw.parquet (raw close: the price floor and the cent cost only), symbol-filtered on read;
  * universe = universe_pit100.json (C:/EdgeLog/_anatomy_cache/opus_hunt1109, built by s23_universe.py: each year's
    top 100 by PRIOR-year median dollar volume) keys 2017 .. 2026 -> a session-by-name member matrix;
  * listing = siporb/assets.csv 'exchange' (CURRENT listing, frozen; not point-in-time - the hunt's input).
The panel runs to 2026-06-30 (bars starting before 2026-07-01 00:00 ET; daily rows <= 2026-06-30) so the engine's
12-month lockbox has prices. THIS SCRIPT COMPUTES NO RETURN, PNL OR STRATEGY STATISTIC. Besides shapes and the
sha256 to pin in the plugin it prints a data-consistency QA: split-like (>= 1.5x) disagreements between the
10-minute bars and the daily split-adjusted closes, and split-like session-to-session jumps in the 10-minute
15:50 closes - counts, names and dates only.

    python tools/misc_aucrev_panel.py            (writes C:/EdgeLog/alpaca_cache/aucrev_panel/aucrev_panel_v1.npz)
Memory: ~200 names x ~2,640 sessions x 4 fields x float32 + 2 daily float64 fields ~ 20 MB; one CSV parsed at a time.
"""
import glob
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

NY = "America/New_York"
HUNT = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/"
DIRS = ("C:/EdgeLog/alpaca_cache/tbis_r3/", "C:/EdgeLog/alpaca_cache/eodrev_u100/")
DAILY = "C:/EdgeLog/alpaca_cache/siporb/daily_%s.parquet"
ASSETS = "C:/EdgeLog/alpaca_cache/siporb/assets.csv"
OUT = "C:/EdgeLog/alpaca_cache/aucrev_panel/aucrev_panel_v1.npz"
START = pd.Timestamp("2016-01-01", tz=NY)
CUT = pd.Timestamp("2026-07-01", tz=NY)          # bars starting before this; sessions through 2026-06-30
CUT_DAY = pd.Timestamp("2026-06-30")
YEARS = [str(y) for y in range(2017, 2027)]
KEEP = (930, 940, 950)                           # bar starts 15:30, 15:40, 15:50
# The hunt's frozen NYSE early-close list (s85_build.EARLY), extended through 2026-06 (2025-07-03, 2025-11-28,
# 2025-12-24; no early close in 2026-01 .. 2026-06).
EARLY = pd.to_datetime([
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03",
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"])


def _load(f, spy=False):
    """The hunt's load(): float64 parse -> float32, cut at START / CUT, keep the 15:30 / 15:40 / 15:50 bars."""
    x = pd.read_csv(f, usecols=["time", "open", "close"])
    t = pd.to_datetime(x.time, unit="s", utc=True).dt.tz_convert(NY)
    k = ((t >= START) & (t < CUT)).values
    x = x[k]
    t = t[k]
    assert len(t) == 0 or t.max() < CUT
    m = (t.dt.hour * 60 + t.dt.minute).values
    d = t.dt.normalize().dt.tz_localize(None).values
    sess = None
    if spy:
        reg = (m >= 570) & (m <= 950)
        last = pd.DataFrame({"d": d[reg], "m": m[reg]}).groupby("d").m.max()
        v = pd.read_csv(f, usecols=["volume"]).volume.values[k]
        sess = pd.DataFrame({"last": last,
                             "v1300": pd.Series(v[m == 780], index=d[m == 780]).groupby(level=0).sum(),
                             "v1250": pd.Series(v[m == 770], index=d[m == 770]).groupby(level=0).sum()})
    k2 = np.isin(m, KEEP)
    y = pd.DataFrame({"d": d[k2], "m": m[k2], "open": x.open.values[k2].astype("float32"),
                      "close": x.close.values[k2].astype("float32")})
    y = y.drop_duplicates(["d", "m"])
    return y, sess


def main():
    U = json.load(open(HUNT + "universe_pit100.json"))
    assert all(y in U and len(U[y]) == 100 for y in YEARS), "universe_pit100.json lacks a year key"
    allu = sorted(set(s for y in YEARS for s in U[y]) - {"SPY"})
    files = {}
    for D in DIRS:
        for f in sorted(glob.glob(D + "*.csv.gz")):
            files[os.path.basename(f)[:-7].replace("_", ".")] = f
    missing = [s for s in allu if s not in files]
    names = [s for s in allu if s in files]
    spy, last = _load(files["SPY"], spy=True)
    P = {}
    for i, s in enumerate(names):
        P[s], _ = _load(files[s])
        if i % 50 == 0:
            print("loaded", i, s, flush=True)
    P["SPY"] = spy
    sessions = pd.DatetimeIndex(sorted(last.index))
    assert sessions.max() <= CUT_DAY
    ratio = (last.v1300 / last.v1250).reindex(sessions)
    susp = sessions[(ratio < 0.25).values | ratio.isna().values]
    early = sessions[sessions.isin(EARLY)]
    full = ~sessions.isin(EARLY) & (last["last"].reindex(sessions) >= 950).values
    print("sessions %d (%s .. %s), full %d, early (list) %d, no SPY 15:50 bar and not on the list: %s" % (
        len(sessions), sessions[0].date(), sessions[-1].date(), int(full.sum()), len(early),
        [str(d.date()) for d in sessions[~full & ~sessions.isin(EARLY)]]))
    print("SPY 13:00/12:50 volume collapse (half-day check) after 2025-06-30:",
          [str(d.date()) for d in susp if d > pd.Timestamp("2025-06-30")],
          "| list days after 2025-06-30:", [str(d.date()) for d in early if d > pd.Timestamp("2025-06-30")])

    cols = names + ["SPY"]

    def px(col, m):
        return pd.DataFrame({s: x[x.m == m].set_index("d")[col] for s, x in P.items()}).reindex(
            sessions).reindex(columns=cols).astype("float32")

    FR = {"c30": px("close", 930), "c40": px("close", 940), "o55": px("open", 950), "c55": px("close", 950)}
    del P
    dl = {}
    for kind in ("split", "raw"):
        t = pq.read_table(DAILY % kind, columns=["symbol", "date", "c"],
                          filters=[("symbol", "in", names), ("date", "<=", CUT_DAY)]).to_pandas()
        t["date"] = pd.to_datetime(t.date)
        assert t.date.max() <= CUT_DAY
        dl[kind] = t.pivot_table(index="date", columns="symbol", values="c").reindex(sessions).reindex(columns=names)
        del t
    A = pd.read_csv(ASSETS).drop_duplicates("symbol").set_index("symbol")["exchange"]
    listing = {s: A.get(s, None) for s in names}
    unknown = [s for s in names if listing[s] not in ("NASDAQ", "NYSE")]
    nasdaq = np.array([listing[s] == "NASDAQ" for s in names], bool)
    member = pd.DataFrame(False, index=sessions, columns=names)
    for y in YEARS:
        r = sessions.year == int(y)
        if r.any():
            member.loc[r, [s for s in U[y] if s in names and s != "SPY"]] = True

    # ---- data-consistency QA (no return is computed: split-like ratios between two price sources, counts only)
    c55 = FR["c55"][names].astype(float)
    q = (dl["split"] / c55).where(member.values)
    bad = (np.abs(np.log(q)) > np.log(1.5)) & member.values
    jump = (c55 / c55.shift(1)).where(member.values)
    jb = (np.abs(np.log(jump)) > np.log(1.8)) & member.values
    print("QA split-like (>= 1.5x) disagreement, daily split close vs 10m 15:50 close, member name-days:",
          int(bad.values.sum()), {s: (str(bad.index[bad[s].values].min().date()), str(bad.index[bad[s].values].max().date()),
                                      int(bad[s].sum())) for s in names if bad[s].any()})
    print("QA split-like (>= 1.8x) session-to-session jumps in the 10m 15:50 close, member name-days:",
          {s: [str(d.date()) for d in jb.index[jb[s].values]] for s in names if jb[s].any()})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in sessions], dtype="int64"),
             names=np.array(cols), early=np.asarray(sessions.isin(EARLY), bool), full=np.asarray(full, bool),
             c30=FR["c30"].values, c40=FR["c40"].values, o55=FR["o55"].values, c55=FR["c55"].values,
             split=dl["split"].values.astype(np.float64), raw=dl["raw"].values.astype(np.float64),
             member=member.values, nasdaq=nasdaq)
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    yrs = {y: int(member[sessions.year == int(y)].any(axis=0).sum()) for y in YEARS}
    print("names %d (NASDAQ %d, NYSE %d, unknown %s), missing bar files %s, members with a bar file by year %s" % (
        len(names), int(nasdaq.sum()), sum(listing[s] == "NYSE" for s in names), unknown, missing, yrs))
    print("%s  bars %s  daily %s  sessions %s .. %s  sha256 %s" % (
        OUT, FR["c55"].shape, dl["split"].shape, sessions[0].date(), sessions[-1].date(), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())

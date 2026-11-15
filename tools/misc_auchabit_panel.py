"""Build the pinned side panel for augur_strategies/MISC_AUCHABIT_1_0.py (opus hunt strategy 86, AUCTION-HABIT).

Same inputs, same parsing as the hunt's panel build C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S86/s86_build.py:
  * 10-minute SIP split-adjusted bars C:/EdgeLog/alpaca_cache/tbis_r3/<SYM>.csv.gz and eodrev_u100/<SYM>.csv.gz
    (eodrev_u100 overrides tbis_r3 when a name is in both - the s25 / s86 precedence; none is today). time = bar
    START, epoch s UTC -> America/New_York. Only the bar that starts 15:50 is kept: its open (O50) and close (C50),
    parsed as float64 and stored float32 (= the harness); duplicate (day, minute) rows -> the first one kept;
  * daily close c from C:/EdgeLog/alpaca_cache/siporb/daily_split.parquet (the official close, split-adjusted) and
    daily_raw.parquet (the raw close: price floor and cent cost only), pivot_table mean, stored float32 (= the harness);
  * names = every symbol of the point-in-time top-100 lists 2017 .. 2026 (tools/data/eodrev_universe_pit100.json, a
    byte copy of the hunt's universe_pit100.json: each calendar year's top 100 by the PRIOR year's median daily dollar
    volume, >= 200 sessions, median price >= $10 - s23_universe.py), SPY excluded; member[d, i] = name i is in the list
    of year(d). 2016 has no list (no 2015 data), so nothing is a member before 2017-01-03;
  * rows = every trading day 2016-01-04 .. 2026-06-30 (the union of the daily-file dates and the dates with any 15:50
    bar; half days included - the price floor reads the previous TRADING day's raw close);
    FULL = SPY has a 10-minute bar starting 15:50 AND the day is not a NYSE 13:00 early close (the harness's frozen
    list - every one of those days carries a SPY 15:50 bar from after-hours prints - extended through 2026-06 with
    2025-07-03, 2025-11-28 and 2025-12-24, the PAIRZ panel's list).
The panel runs to 2026-06-30 (bars starting before 2026-07-01 00:00 ET; daily rows <= 2026-06-30) so the engine's
12-month lockbox has prices. THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC - it stores arrays and prints shapes,
date coverage, the source folder per name and the sha256 to pin in the plugin. The npz is written with fixed zip
timestamps, so a rebuild from unchanged inputs reproduces the same sha256.

    python tools/misc_auchabit_panel.py      (writes C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_v1.npz)
    python tools/misc_auchabit_panel.py --out <path>     (a rebuild elsewhere, e.g. to check it reproduces the pin)
Memory: one name's CSV is parsed at a time (~0.1 GB peak); the panel is ~2,640 rows x 199 names x 4 float32 arrays.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numpy.lib import format as npformat

NY = "America/New_York"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ("C:/EdgeLog/alpaca_cache/tbis_r3/", "C:/EdgeLog/alpaca_cache/eodrev_u100/")   # later folder wins (= s86_build)
DAILY = "C:/EdgeLog/alpaca_cache/siporb/daily_%s.parquet"
UNIVERSE = os.path.join(REPO, "tools", "data", "eodrev_universe_pit100.json")
HUNT_UNIVERSE = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/universe_pit100.json"
OUT = "C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_v1.npz"
START = pd.Timestamp("2016-01-01", tz=NY)
CUT = pd.Timestamp("2026-07-01", tz=NY)            # bars starting before 2026-07-01 00:00 ET
CUT_DAY = pd.Timestamp("2026-06-30")
FIRST_ROW = pd.Timestamp("2016-01-04")
YEARS = [str(y) for y in range(2017, 2027)]
# The harness's frozen early-close list (s86_lib.EARLY), extended through 2026-06 by the same rule
# (day after Thanksgiving; Jul 3 / Dec 24 when a Mon-Thu session). 2026-07-03 is a holiday, not a half day.
EARLY = pd.to_datetime([
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03",
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"])
MIN50 = 950                                        # 15:50 ET, minutes after midnight


def _files():
    out = {}
    for d in DIRS:
        for f in sorted(glob.glob(d + "*.csv.gz")):
            out[os.path.basename(f)[:-7].replace("_", ".")] = f
    return out


def _bar50(f):
    """(day -> O50, day -> C50) of one name: the 10-minute bar that starts 15:50 ET, s86_build.load() exactly."""
    x = pd.read_csv(f, usecols=["time", "open", "close"])
    t = pd.to_datetime(x.time, unit="s", utc=True).dt.tz_convert(NY)
    k = ((t >= START) & (t < CUT)).values
    x = x[k]
    t = t[k]
    assert len(t) == 0 or t.max() < CUT
    m = (t.dt.hour * 60 + t.dt.minute).values
    d = t.dt.normalize().dt.tz_localize(None).values
    k2 = m == MIN50
    y = pd.DataFrame({"d": d[k2], "open": x.open.values[k2].astype("float32"),
                      "close": x.close.values[k2].astype("float32")})
    y = y.drop_duplicates(["d"]).set_index("d")         # one minute kept -> (d, m) duplicates = d duplicates
    return y["open"], y["close"]


def _save_npz(path, arrays):
    """np.savez layout (stored, zip64) with FIXED member timestamps, so the file's sha256 depends on the data only."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for key, val in arrays.items():
            zi = zipfile.ZipInfo(key + ".npy", date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            with zf.open(zi, "w", force_zip64=True) as fh:
                npformat.write_array(fh, np.ascontiguousarray(val), allow_pickle=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    out = ap.parse_args().out
    with open(UNIVERSE, "rb") as fh:
        ub = fh.read()
    if os.path.exists(HUNT_UNIVERSE):
        with open(HUNT_UNIVERSE, "rb") as fh:
            assert fh.read() == ub, "tools/data/eodrev_universe_pit100.json is not the hunt's universe_pit100.json"
    U = json.loads(ub.decode("utf-8"))
    assert all(len(U[y]) == 100 for y in YEARS)
    files = _files()
    names = sorted(set(s for y in YEARS for s in U[y][:100]) - {"SPY"})
    missing = [s for s in names if s not in files]
    if missing:
        sys.exit("no 10-minute file for %s - nothing written" % missing)
    if "SPY" not in files:
        sys.exit("no SPY 10-minute file (the FULL-session clock) - nothing written")
    o50, c50 = {}, {}
    for i, s in enumerate(names + ["SPY"]):
        o50[s], c50[s] = _bar50(files[s])
        if i % 40 == 0:
            print("parsed %d / %d (%s)" % (i, len(names) + 1, s), flush=True)
    O = pd.DataFrame(o50).sort_index().astype("float32")
    C = pd.DataFrame(c50).sort_index().astype("float32")
    dl = {}
    for kind in ("split", "raw"):
        t = pq.read_table(DAILY % kind, columns=["symbol", "date", "c"],
                          filters=[("symbol", "in", names), ("date", "<=", CUT_DAY)]).to_pandas()
        t["date"] = pd.to_datetime(t.date)
        assert t.date.max() <= CUT_DAY
        dl[kind] = t.pivot_table(index="date", columns="symbol", values="c").astype("float32")
    rows = dl["split"].index.union(dl["raw"].index).union(O.index)
    rows = rows[(rows >= FIRST_ROW) & (rows <= CUT_DAY)]
    spy50 = O["SPY"].reindex(rows)
    early = rows.isin(EARLY)
    full = (spy50.notna().values & ~early)
    member = np.zeros((len(rows), len(names)), bool)
    col = {s: j for j, s in enumerate(names)}
    for y in YEARS:
        r = rows.year == int(y)
        member[np.ix_(r, [col[s] for s in U[y][:100] if s in col])] = True
    arrays = {
        "dates": np.array([int(d.strftime("%Y%m%d")) for d in rows], dtype="int64"),
        "names": np.array(names),
        "full": full,
        "o50": O.reindex(index=rows, columns=names).values.astype("float32"),
        "c50": C.reindex(index=rows, columns=names).values.astype("float32"),
        "dc": dl["split"].reindex(index=rows, columns=names).values.astype("float32"),
        "raw": dl["raw"].reindex(index=rows, columns=names).values.astype("float32"),
        "member": member,
    }
    _save_npz(out, arrays)
    with open(out, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    src = {}
    for s in names:
        src.setdefault(os.path.basename(os.path.dirname(files[s])), []).append(s)
    print("sources: %s" % {k: len(v) for k, v in src.items()})
    print("rows %d (%s .. %s), FULL sessions %d, early-close days removed %d (with a SPY 15:50 bar: %d), "
          "days with no SPY 15:50 bar %d" % (len(rows), rows[0].date(), rows[-1].date(), int(full.sum()),
                                             int(early.sum()), int((early & spy50.notna().values).sum()),
                                             int(spy50.isna().sum())))
    print("names %d (%d with a list year 2026 only); members per row by year: %s" % (
        len(names), len(set(U["2026"]) - set(s for y in YEARS[:-1] for s in U[y])),
        {y: int(member[rows.year == int(y)].sum(axis=1).max()) for y in YEARS}))
    last = {k: str(pd.Timestamp(str(arrays["dates"][np.flatnonzero(np.isfinite(arrays[k]).any(axis=1))[-1]])).date())
            for k in ("o50", "c50", "dc", "raw")}
    print("last row with any value: %s; names with an O50 on the last FULL row: %d" % (
        last, int(np.isfinite(arrays["o50"][np.flatnonzero(full)[-1]]).sum())))
    print("%s  o50/c50/dc/raw %s  sha256 %s" % (out, arrays["o50"].shape, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())

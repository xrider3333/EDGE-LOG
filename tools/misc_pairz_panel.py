"""Build the pinned side panel for augur_strategies/MISC_PAIRZ_1_0.py (opus hunt strategy 76, PAIRZ-INTRA).

Same inputs, same parsing as the hunt harness C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S76/s76_lib.py load():
  * 10-minute bars C:/EdgeLog/alpaca_cache/tbis_r3/<SYM>.csv.gz, falling back to eodrev_u100/<SYM>.csv.gz
    (time = bar START, epoch s UTC -> America/New_York), RTH bars 09:30 .. 15:50 only, open / close float32,
    duplicate (day, minute) rows -> the first one kept (= the harness);
  * daily close c from C:/EdgeLog/alpaca_cache/siporb/daily_raw.parquet and daily_split.parquet;
  * sessions = SPY 10m RTH dates from 2016-01-04; FULL = SPY has a 15:50 bar AND the day is not on the frozen
    NYSE early-close list (the harness list, extended to 2026-06 with 2025-07-03, 2025-11-28, 2025-12-24).
The panel runs to 2026-06-30 (bars starting before 2026-06-30 16:00 ET; daily rows <= 2026-06-30) so the engine's
12-month lockbox has prices. THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC - it only stores arrays and prints
shapes, the source folder per name and the sha256 to pin in the plugin.

    python tools/misc_pairz_panel.py            (writes C:/EdgeLog/alpaca_cache/pairz_panel/pairz_panel_v1.npz)
Memory: 61 names x ~2,640 sessions x 39 bars x 2 x float32 ~ 50 MB; one name's CSV is parsed at a time.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

NY = "America/New_York"
D1 = "C:/EdgeLog/alpaca_cache/tbis_r3/"
D2 = "C:/EdgeLog/alpaca_cache/eodrev_u100/"
DAILY = "C:/EdgeLog/alpaca_cache/siporb/daily_%s.parquet"
OUT = "C:/EdgeLog/alpaca_cache/pairz_panel/pairz_panel_v1.npz"
CUT_TS = pd.Timestamp("2026-06-30 16:00", tz=NY)
CUT_DAY = pd.Timestamp("2026-06-30")
PAIRS = [("MA", "V"), ("KO", "PEP"), ("HD", "LOW"), ("JPM", "BAC"), ("JPM", "C"), ("BAC", "C"), ("BAC", "WFC"),
         ("JPM", "WFC"), ("C", "WFC"), ("XOM", "CVX"), ("CVX", "COP"), ("XOM", "COP"), ("COP", "EOG"), ("MPC", "VLO"),
         ("SLB", "HAL"), ("NVDA", "AMD"), ("MSFT", "ORCL"), ("MRK", "PFE"), ("VZ", "T"), ("UNH", "CI"), ("UNH", "HUM"),
         ("GS", "MS"), ("WMT", "COST"), ("UPS", "FDX"), ("AMAT", "LRCX"), ("LRCX", "KLAC"), ("TXN", "ADI"),
         ("CSX", "UNP"), ("MO", "PM"), ("DAL", "UAL"), ("CAT", "DE"), ("TMO", "DHR"), ("PG", "KO"), ("JNJ", "PFE"),
         ("MCD", "SBUX"), ("AXP", "MA"), ("MS", "SCHW"), ("MET", "AIG"), ("USB", "WFC")]
NAMES = sorted(set(sum(map(list, PAIRS), [])))
# The harness's frozen early-close list (s76_lib.EARLY), extended through 2026-06 by the same rule
# (day after Thanksgiving; Jul 3 / Dec 24 when a Mon-Thu session).
EARLY = pd.to_datetime([
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03",
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"])
MINS = list(range(570, 951, 10))    # 09:30 .. 15:50, 39 bars


def _read(sym):
    f = D1 + sym.replace(".", "_") + ".csv.gz"
    if not os.path.exists(f):
        f = D2 + sym.replace(".", "_") + ".csv.gz"
    x = pd.read_csv(f, usecols=["time", "open", "close"], dtype={"open": "float32", "close": "float32"})
    x = x[x.time < int(CUT_TS.value // 10**9)]
    t = pd.to_datetime(x.time, unit="s", utc=True).dt.tz_convert(NY)
    m = (t.dt.hour * 60 + t.dt.minute).values
    x = x.assign(d=t.dt.normalize().dt.tz_localize(None).values, m=m)
    return x[(x.m >= 570) & (x.m <= 950)], os.path.basename(os.path.dirname(f))


def main():
    spy, _ = _read("SPY")
    days = pd.DatetimeIndex(sorted(spy.d.unique()))
    days = days[days >= pd.Timestamp("2016-01-04")]
    s1550 = set(spy[spy.m == 950].d)
    early = set(EARLY)
    full = np.array([(d in s1550) and (d not in early) for d in days], bool)
    print("sessions %d (%s .. %s), full %d, no SPY 15:50 bar: %s" % (
        len(days), days[0].date(), days[-1].date(), full.sum(), [str(d.date()) for d in days if d not in s1550]))
    O = np.full((len(days), len(NAMES), len(MINS)), np.nan, np.float32)
    C = np.full_like(O, np.nan)
    src = {}
    for i, s in enumerate(NAMES):
        x, src[s] = _read(s)
        x = x.drop_duplicates(["d", "m"])
        O[:, i, :] = x.pivot(index="d", columns="m", values="open").reindex(index=days, columns=MINS).values
        C[:, i, :] = x.pivot(index="d", columns="m", values="close").reindex(index=days, columns=MINS).values
        del x
    print("sources:", {k: sorted(s for s in src if src[s] == k) for k in set(src.values())})
    dl = {}
    for kind in ("raw", "split"):
        t = pq.read_table(DAILY % kind, columns=["symbol", "date", "c"],
                          filters=[("symbol", "in", NAMES), ("date", "<=", CUT_DAY)]).to_pandas()
        t["date"] = pd.to_datetime(t.date)
        assert t.date.max() <= CUT_DAY
        dl[kind] = t.pivot_table(index="date", columns="symbol", values="c").reindex(days).reindex(
            columns=NAMES).values.astype(np.float64)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in days], dtype="int64"),
             names=np.array(NAMES), full=full, O=O, C=C, raw=dl["raw"], split=dl["split"])
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    print("%s  O/C %s  raw/split %s  sha256 %s" % (OUT, O.shape, dl["raw"].shape, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())

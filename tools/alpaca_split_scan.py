# alpaca_split_scan.py - scan every Alpaca research cache for splits the feed left unadjusted.
#
# WHY (TBIS data QA, 2026-10-04): Alpaca's adjustment=split left GE's 1-for-8 reverse split of
# 2021-08-02 unadjusted, and a 10-minute strategy booked it as a fake +$139k trade. The loader's
# write guard (upsert_master) refuses such a master, but research caches written straight from
# fetch_bars never reach it - TBIS r3, TTM r20c and the ROC-frontier harnesses all live there.
# This tool runs the SAME test (split_like_gaps in tools/import_alpaca_stocks.py: regular-session
# close to next regular-session open, within 2% of a whole n:1 or 1:n ratio) over every cache file,
# with the volume test ON by default (a scan wants precision: siporb 369 price flags -> 64).
#
# Alpaca re-adjusts history at query time, so a cache is a photograph of the vendor on the day it
# was pulled: flags are written to a DATED file, and the fix for a flagged symbol is a RE-PULL,
# not a patch (ELwA, 2026-10-05).
#
# Schemas it reads (anything else is listed as skipped, never guessed):
#   per-symbol intraday  time (epoch s) + open/close[/volume]   e.g. tbis_r3/GE.csv.gz, ttm_r20c/GE_30m_split_rth.csv
#   per-symbol daily     date + open/close[/volume]             e.g. etf_daily/GLD_1Day_split.csv
#   multi-symbol         symbol + (time|t|date) + open/close or o/c[/v]   e.g. siporb/daily_split.parquet
# Files with 'raw' in the name are unadjusted BY DESIGN and skipped unless --include-raw.
#
# Run:
#   python tools/alpaca_split_scan.py                       # every cache under C:\EdgeLog\alpaca_cache
#   python tools/alpaca_split_scan.py --root C:\EdgeLog\alpaca_cache\tbis_r3
#   python tools/alpaca_split_scan.py --price-only          # the strict write-guard test, no volume check
import argparse
import importlib.util
import os
import sys
import time
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = r"C:\EdgeLog\alpaca_cache"
DEFAULT_OUT = r"C:\EdgeLog\_research_cache\split_qa"
SUFFIXES = (".csv", ".csv.gz", ".parquet")


def _loader():
    spec = importlib.util.spec_from_file_location("_alpaca_stocks_scan", os.path.join(HERE, "import_alpaca_stocks.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _read(path):
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)


def _symbol_from_name(path):
    base = os.path.basename(path)
    for suf in SUFFIXES:
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    return base.split("_")[0]


def _restamp_daily(t):
    """Daily bars stamped at one clock time outside the regular session (Alpaca 1D masters sit at
    00:00 ET) would give split_like_gaps NO session at all - and no flags, silently. Re-stamp each
    such row at 12:00 ET of its own date so its open and close are that day's session."""
    if len(t) < 2:
        return t
    et = pd.to_datetime(t, unit="s", utc=True).dt.tz_convert("US/Eastern")
    tod = et.dt.hour * 60 + et.dt.minute
    if tod.nunique() == 1 and not (570 <= int(tod.iloc[0]) < 960):
        noon = et.dt.normalize() + pd.Timedelta(hours=12)
        return (noon.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    return t


def _frame(df):
    """Normalise one symbol's rows to the loader's frame: time (epoch s), open, close[, volume].

    A DAILY row (a date, no clock time) is stamped at 12:00 ET so the loader's regular-session
    window treats it as one session whose open and close are that row's own."""
    cols = {c.lower(): c for c in df.columns}
    o = cols.get("open") or cols.get("o")
    c = cols.get("close") or cols.get("c")
    v = cols.get("volume") or cols.get("v")
    if not (o and c):
        return None
    if "time" in cols and pd.api.types.is_numeric_dtype(df[cols["time"]]):
        t = df[cols["time"]].astype("int64")
    elif "t" in cols or "time" in cols:
        ts = pd.to_datetime(df[cols.get("t") or cols["time"]], utc=True)
        t = (ts - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    elif "date" in cols:
        noon = pd.to_datetime(df[cols["date"]]).dt.normalize() + pd.Timedelta(hours=12)
        ts = noon.dt.tz_localize("US/Eastern")
        t = (ts - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    else:
        return None
    t = _restamp_daily(pd.Series(t.values))
    out = pd.DataFrame({"time": t.values, "open": df[o].astype(float).values, "close": df[c].astype(float).values})
    if v:
        out["volume"] = df[v].astype(float).values
    return out.dropna(subset=["open", "close"])


def scan_file(path, split_like_gaps, require_volume=True):
    """[(symbol, day, ratio, nearest, name)] for one file; raises ValueError on an unreadable schema."""
    df = _read(path)
    cols = {c.lower(): c for c in df.columns}
    out = []
    if "symbol" in cols:
        for sym, g in df.groupby(cols["symbol"]):
            f = _frame(g)
            if f is None:
                raise ValueError("no open/close/time columns")
            out += [(sym,) + hit for hit in split_like_gaps(f, require_volume=require_volume)]
    else:
        f = _frame(df)
        if f is None:
            raise ValueError("no open/close/time columns")
        sym = _symbol_from_name(path)
        out += [(sym,) + hit for hit in split_like_gaps(f, require_volume=require_volume)]
    return out


def scan(root, include_raw=False, require_volume=True, verbose=False):
    split_like_gaps = _loader().split_like_gaps
    flags, skipped, scanned = [], [], 0
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(dirpath, name)
            if not name.endswith(SUFFIXES):
                continue
            if "raw" in name.lower() and not include_raw:
                skipped.append((path, "raw by design"))
                continue
            t0 = time.time()
            try:
                hits = scan_file(path, split_like_gaps, require_volume)
            except Exception as e:                         # an unknown schema is reported, never guessed
                skipped.append((path, str(e)[:80]))
                continue
            scanned += 1
            rel = os.path.relpath(path, root)
            if verbose:
                print(f"  {rel}: {len(hits)} flags, {time.time() - t0:.1f}s", flush=True)
            flags += [(rel, sym, day, round(ratio, 4), nm) for sym, day, ratio, _near, nm in hits]
    return flags, skipped, scanned


def library_files():
    """Alpaca SPLIT-adjusted masters registered in the library, via the engine's read-only registry
    API (augur_engine.data.list_masters). This tool never writes a master - only its own flags report.
    Run --library from the shared checkout: a worktree has no registry, so the list comes back empty."""
    root = os.path.dirname(HERE)
    if root not in sys.path:
        sys.path.insert(0, root)
    from augur_engine.data import list_masters
    from augur_engine.paths import UPLOADS
    return [(os.path.join(UPLOADS, m["filename"]), m["instrument"]) for m in list_masters()
            if str(m.get("source") or "").startswith("alpaca_split")]


def scan_library(require_volume=True):
    split_like_gaps = _loader().split_like_gaps
    flags, skipped = [], []
    for path, sym in library_files():
        try:
            f = _frame(_read(path))
            hits = split_like_gaps(f, require_volume=require_volume) if f is not None else None
        except Exception as e:
            skipped.append((path, str(e)[:80])); continue
        if hits is None:
            skipped.append((path, "no open/close/time columns")); continue
        flags += [("library\\" + os.path.basename(path), sym, day, round(ratio, 4), nm) for day, ratio, _n, nm in hits]
    return flags, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--include-raw", action="store_true", help="also scan files named *raw* (unadjusted by design)")
    ap.add_argument("--price-only", action="store_true", help="drop the volume test (the strict write-guard rule)")
    ap.add_argument("--verbose", action="store_true", help="print each scanned file with its flag count and time")
    ap.add_argument("--library", action="store_true", help="scan the Alpaca split-adjusted LIBRARY masters instead of --root")
    a = ap.parse_args(argv)
    if a.library:
        flags, skipped = scan_library(not a.price_only)
        scanned = len(library_files()) - len(skipped)
    else:
        flags, skipped, scanned = scan(a.root, a.include_raw, not a.price_only, a.verbose)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f"split_scan_{'library_' if a.library else ''}{date.today():%Y%m%d}.csv")
    pd.DataFrame(flags, columns=["file", "symbol", "day", "ratio", "split"]).to_csv(out, index=False)
    print(f"scanned {scanned} files, skipped {len(skipped)}, {len(flags)} split-like gaps "
          f"({'price only' if a.price_only else 'price + volume'}) -> {out}")
    for rel, sym, day, ratio, nm in flags:
        print(f"  {rel}  {sym}  {day}  x{ratio}  ({nm})")
    for path, why in skipped:
        if why != "raw by design":
            print(f"  skipped {path}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

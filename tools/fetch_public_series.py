# -*- coding: utf-8 -*-
"""SMALL PUBLIC DAILY SERIES - CBOE volatility indices + the US Treasury daily yield curve (TV, public-data scout, MANAGER #62).

SOURCES (public, no key; docs/PUBLIC_DATA_CATALOG.md rows 8 and 11):
  CBOE   https://cdn.cboe.com/api/global/us_indices/daily_prices/<INDEX>_History.csv   VIX, VIX3M, VVIX, SKEW
  UST    https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<YEAR>/all
         ?type=daily_treasury_yield_curve&field_tdr_date_value=<YEAR>&page&_format=csv              one file per year, 1990-2025
PHOTOGRAPH RULE: every response saved byte for byte under C:\\EdgeLog\\_research_cache\\public_series\\ with URL / time / bytes /
sha256 in public_series_provenance.json; a second fetch REFUSES to overwrite (a fresh pull = a new folder via --into).
LOCKBOX: the raw CBOE files run to the fetch day; the DERIVED files stop at 2025-06-29, so no harness reading them can see the
sealed year. CBOE publishes index closes after the session (US/Central 15:15 cash close for VIX) - a consumer trading on a
day's close must act no earlier than the next session.

DERIVED: cboe_vol_daily.csv  (date, VIX_open/high/low/close, VIX3M_..., VVIX, SKEW)   ust_yield_curve_daily.csv (date, 1 Mo .. 30 Yr)

    python tools/fetch_public_series.py            # fetch what is not saved yet + build
    python tools/fetch_public_series.py --build    # rebuild the derived files from the saved photographs only
"""
import argparse, datetime, glob, hashlib, io, json, os, sys, time, urllib.request

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\public_series"
CUT = "2025-06-29"                          # last walk-forward day; the lockbox (2025-06-30 ..) never reaches a derived file
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/%s_History.csv"
INDICES = ("VIX", "VIX3M", "VVIX", "SKEW")
UST = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/%d/all"
       "?type=daily_treasury_yield_curve&field_tdr_date_value=%d&page&_format=csv")
YEARS = range(1990, 2026)


def fetch(url, dst, prov):
    if os.path.exists(dst):
        return False                                       # already photographed: never refetched
    time.sleep(0.5)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(raw)
    prov[os.path.relpath(dst, RAW)] = dict(url=url, fetched_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                          bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return True


def do_fetch():
    pf = os.path.join(RAW, "public_series_provenance.json")
    prov = json.load(open(pf)) if os.path.exists(pf) else {}
    for ix in INDICES:
        if fetch(CBOE % ix, os.path.join(RAW, "cboe", "%s_History.csv" % ix), prov):
            print("  CBOE %s" % ix, flush=True)
    for y in YEARS:
        if fetch(UST % (y, y), os.path.join(RAW, "ust", "yield_curve_%d.csv" % y), prov):
            print("  UST %d" % y, flush=True)
        os.makedirs(RAW, exist_ok=True)
        json.dump(prov, open(pf, "w"), indent=1)


def build():
    out = None
    for ix in INDICES:
        d = pd.read_csv(os.path.join(RAW, "cboe", "%s_History.csv" % ix))
        d.columns = [c.strip().upper() for c in d.columns]
        d["date"] = pd.to_datetime(d["DATE"], format="mixed")
        keep = [c for c in ("OPEN", "HIGH", "LOW", "CLOSE") if c in d] or [c for c in d if c not in ("DATE", "date")]
        d = d.set_index("date")[keep].apply(pd.to_numeric, errors="coerce")
        d.columns = ["%s_%s" % (ix, c.lower()) if len(keep) > 1 else ix for c in keep]
        out = d if out is None else out.join(d, how="outer")
    out = out[out.index <= CUT].sort_index()
    out.to_csv(os.path.join(RAW, "cboe_vol_daily.csv"), index_label="date", date_format="%Y-%m-%d")
    print("cboe_vol_daily: %d days %s .. %s, columns %s" % (len(out), out.index.min().date(), out.index.max().date(), list(out.columns)))
    frames = []
    for fn in sorted(glob.glob(os.path.join(RAW, "ust", "yield_curve_*.csv"))):
        frames.append(pd.read_csv(fn))
    U = pd.concat(frames, ignore_index=True)
    U["date"] = pd.to_datetime(U["Date"], format="mixed")
    U = U.drop(columns="Date").drop_duplicates("date").set_index("date").sort_index()
    U = U[U.index <= CUT]
    U.to_csv(os.path.join(RAW, "ust_yield_curve_daily.csv"), index_label="date", date_format="%Y-%m-%d")
    print("ust_yield_curve_daily: %d days %s .. %s, tenors %s" % (len(U), U.index.min().date(), U.index.max().date(), list(U.columns)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); a = ap.parse_args()
    if not a.build:
        do_fetch()
    build()

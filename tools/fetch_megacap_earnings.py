# -*- coding: utf-8 -*-
"""Mega-cap earnings release calendar, 2010 on, from the SEC's own filing index (NOISE round 60).

WHY: the KEEL study (2026-09-09) listed the earnings calendar as the next NEW-INFORMATION input after FOMC and
the BLS releases. None of the ten calendars in tools/data covers it. A price-gap proxy is not acceptable - the
first-Friday proxy for payrolls invented an effect - so the dates come from the filings themselves.

SOURCE: data.sec.gov submissions index. Every earnings release is furnished on a Form 8-K carrying Item 2.02
("Results of Operations and Financial Condition"), and the index stamps each filing's EDGAR acceptance time.
The 8-K is filed within minutes of the press release, so the acceptance time says whether the numbers landed
before the open or after the close.

REACTION SESSION: the first NQ regular session that starts after the acceptance time. Accepted after 16:00 ET
(or on a weekend / holiday) -> the next session; accepted before 09:30 ET -> the same day's session; accepted
between 09:30 and 16:00 -> that same session (rare, flagged).

Seven companies, fixed before any data was read: Apple, Microsoft, NVIDIA, Amazon, Alphabet (Google Inc before
the 2015 reorganisation), Meta (from its 2012 listing), Tesla.

  python tools/fetch_megacap_earnings.py        # writes tools/data/megacap_earnings.csv (needs `git add -f`)

The request carries a neutral contact string, never the owner's address. Public data, ~20 GETs, 0.3 s apart.
"""
import csv
import json
import os
import time
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "data", "megacap_earnings.csv")
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
COMPANIES = [("AAPL", "0000320193"), ("MSFT", "0000789019"), ("NVDA", "0001045810"), ("AMZN", "0001018724"),
             ("GOOGL", "0001652044"), ("GOOGL", "0001288776"), ("META", "0001326801"), ("TSLA", "0001318605")]
START = pd.Timestamp("2010-01-01", tz="UTC")


def get(url):
    time.sleep(0.3)
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))


def filings(cik):
    d = get("https://data.sec.gov/submissions/CIK%s.json" % cik)
    blocks = [d["filings"]["recent"]] + [get("https://data.sec.gov/submissions/" + f["name"])
                                         for f in d["filings"].get("files", [])]
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in ("8-K", "8-K/A") and "2.02" in (b["items"][i] or ""):
                yield form, b["acceptanceDateTime"][i], b["items"][i]


def main():
    rows = []
    for tk, cik in COMPANIES:
        n = 0
        for form, acc, items in filings(cik):
            t = pd.Timestamp(acc)
            t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
            if t < START or form == "8-K/A":
                continue
            et = t.tz_convert("America/New_York")
            rows.append(dict(ticker=tk, accepted_et=et.strftime("%Y-%m-%d %H:%M"), items=items))
            n += 1
        print("%-5s CIK %s  %d releases since 2010" % (tk, cik, n))
    # one row per (ticker, calendar day): a same-day duplicate filing is one release
    df = pd.DataFrame(rows).drop_duplicates(["ticker", "accepted_et"])
    # Tesla furnishes its quarterly DELIVERY report under Item 2.02 as well. Those are not earnings: until 2022
    # they also carry Item 7.01, and from 2023 they land in the first week of the quarter. Dropped by that rule,
    # which leaves exactly four Tesla releases a year (three in its 2010 listing year and 2011).
    mo = df["accepted_et"].str[5:7].astype(int)
    dd = df["accepted_et"].str[8:10].astype(int)
    delivery = (df["ticker"] == "TSLA") & (df["items"].str.contains("7.01") | (mo.isin([1, 4, 7, 10]) & (dd <= 7)))
    print("dropped %d Tesla delivery reports" % int(delivery.sum()))
    df = df[~delivery]
    df["day"] = df["accepted_et"].str[:10]
    df = df.sort_values("accepted_et").drop_duplicates(["ticker", "day"]).drop(columns="day")
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "accepted_et", "items"])
        w.writeheader()
        w.writerows(df.to_dict("records"))
    per = df.assign(y=df["accepted_et"].str[:4]).groupby(["ticker", "y"]).size()
    odd = per[(per > 5) | (per < 3)]
    print("wrote %d releases -> %s" % (len(df), OUT))
    if len(odd):
        print("years with an unusual release count (check before trusting):")
        print(odd.to_string())


if __name__ == "__main__":
    main()

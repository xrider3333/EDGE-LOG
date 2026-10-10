# -*- coding: utf-8 -*-
"""BVC QA r1 (TV; docs/PREREG_tv_bvcqa_2026-10-10.md, witness branch prereg/tv-bvcqa-1010 @ 1a1f87bc): does a price-only buy/sell
split (bulk volume classification, Easley, Lopez de Prado & O'Hara 2012) reproduce NinjaTrader's real 10-second delta?
Data QA only - reads nothing but C:\\EdgeLog\\ohlc\\NQ_10s.csv and ES_10s.csv; no P&L, no strategy, no lockbox.

THE STATISTIC: pooled Pearson r(BVC, D) over every kept NQ 1-minute bar; PASS r >= 0.60, else FAIL (fixed in the prereg).
Reading of the prereg's bar rule (literal): a bar holding any rt = 0 row or fewer than its full 10s rows is dropped ENTIRELY, so
"the previous bar of the same session" is the previous KEPT bar (gaps are counted and printed).

    python tools/tv_bvcqa_r1.py
"""
import hashlib, os, sys

import numpy as np, pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_bvcqa_2026-10-10.md")
PREREG_LF_SHA = "d743889972717976542825d6f914e2cdea78f8def3a40213df5c2590eaa43cbc"
FILES = {"NQ": r"C:\EdgeLog\ohlc\NQ_10s.csv", "ES": r"C:\EdgeLog\ohlc\ES_10s.csv"}
DROP = {"2026-10-08": "MANAGER: 10-08 feed flap", "2026-10-09": "MANAGER: 10-09 08:03 chart freeze"}
FULL = 2340                                     # 390 RTH minutes x 6 rows
BAR_PASS = 0.60


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def load(mk):
    df = pd.read_csv(FILES[mk])
    n0 = len(df); df = df.drop_duplicates("time", keep="first")
    t = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("America/New_York") - pd.Timedelta(seconds=1)   # END-stamped
    df = df.assign(t=t, day=t.dt.strftime("%Y-%m-%d"), hm=t.dt.hour * 60 + t.dt.minute)
    df = df[(df["hm"] >= 570) & (df["hm"] < 960) & (df["t"].dt.dayofweek < 5)]                                      # RTH 09:30-16:00
    return df, n0 - len(df.drop_duplicates("time"))


def sessions(df):
    g = df.groupby("day").agg(rows=("time", "size"), rt=("rt", "mean"))
    keep, dropped = [], []
    for d, r in g.iterrows():
        if d in DROP:
            dropped.append((d, DROP[d]))
        elif r["rows"] < 0.95 * FULL:
            dropped.append((d, "RTH rows %d of %d" % (r["rows"], FULL)))
        elif r["rt"] < 0.95:
            dropped.append((d, "live (rt=1) share %.2f" % r["rt"]))
        else:
            keep.append(d)
    return keep, dropped


def bars(df, keep, minutes):
    x = df[df["day"].isin(keep)].copy()
    x["bar"] = x["t"].dt.floor("%dmin" % minutes)
    b = x.sort_values("time").groupby("bar").agg(day=("day", "first"), o=("open", "first"), c=("close", "last"), v=("volume", "sum"),
                                                  D=("delta", "sum"), n=("time", "size"), rtmin=("rt", "min"))
    full = b["n"] == 6 * minutes
    dropped = int((~full | (b["rtmin"] < 1)).sum())
    b = b[full & (b["rtmin"] >= 1)].copy()
    prev_c = b.groupby("day")["c"].shift(1)
    b["dP"] = np.where(prev_c.isna(), b["c"] - b["o"], b["c"] - prev_c)
    step = b.index.to_series().groupby(b["day"]).diff()
    gaps = int((step > pd.Timedelta(minutes=minutes)).sum())
    b["sig"] = b["dP"].shift(1).rolling(60, min_periods=30).std()
    b = b[b["sig"] > 0].copy()
    b["bvc"] = b["v"] * (2 * norm.cdf(b["dP"] / b["sig"]) - 1)
    b["tick"] = b["v"] * np.sign(b["dP"])
    return b, dropped, gaps


def r(a, b):
    return float(np.corrcoef(a, b)[0, 1])


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256 %s (pinned %s) - %s" % (got, PREREG_LF_SHA, "OK" if got == PREREG_LF_SHA else "MISMATCH"))
    if got != PREREG_LF_SHA:
        sys.exit("refused: the prereg is not the pinned one")
    print("script LF sha256 %s" % lf_sha(os.path.abspath(__file__)))
    out = {}
    for mk in ("NQ", "ES"):
        df, dup = load(mk)
        keep, dropped = sessions(df)
        print("\n%s: %d duplicate time rows dropped; %d RTH sessions seen, %d KEPT (%s .. %s), %d dropped:" % (
            mk, dup, len(keep) + len(dropped), len(keep), keep[0] if keep else "-", keep[-1] if keep else "-", len(dropped)))
        for d, why in dropped:
            print("   dropped %s  %s" % (d, why))
        for m in (1, 5):
            b, nd, gaps = bars(df, keep, m)
            per = b.groupby("day").apply(lambda g: r(g["bvc"], g["D"]) if len(g) > 10 else np.nan).dropna()
            rb, rt_, rp = r(b["bvc"], b["D"]), r(b["tick"], b["D"]), r(b["dP"], b["D"])
            out[(mk, m)] = rb
            print("  %s %d-min: %d bars used (%d dropped: incomplete / backfill rows; %d prev-bar gaps)" % (mk, m, len(b), nd, gaps))
            print("     r(BVC, D) %.3f  [1 - r^2 = %.2f unexplained] | median per-session r %.3f (IQR %.3f..%.3f, %d sessions)"
                  % (rb, 1 - rb ** 2, per.median(), per.quantile(.25), per.quantile(.75), len(per)))
            print("     twins: r(V x sign dP, D) %.3f | r(dP alone, D) %.3f" % (rt_, rp))
    rr = out[("NQ", 1)]
    print("\nTHE STATISTIC: pooled r(BVC, D), NQ 1-minute = %.3f -> %s (bar r >= %.2f, prereg)" % (rr, "PASS" if rr >= BAR_PASS else "FAIL", BAR_PASS))


if __name__ == "__main__":
    main()

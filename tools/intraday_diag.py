"""
intraday_diag.py -- WHERE does the index return actually live?

A measurement study (NOT a strategy) on the 16yr 1-minute continuous ES/NQ.
Decomposes total close-to-close return into:
  * OVERNIGHT  (prior RTH close -> today's RTH open ; the ETH session + gap)
  * RTH        (today's RTH open -> today's RTH close)
and then slices the RTH session into 30-minute buckets to see which part of the
cash session carries (or bleeds) return. Everything in 1-contract dollars.

RTH = 09:30-16:00 ET.  ES=$50/pt, NQ=$20/pt.

Run:  python tools/intraday_diag.py
"""
import os
import numpy as np
import pandas as pd

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS = os.path.join(ROOT, "augur_uploads")
FILES   = {"ES": ("ES_continuous_1m.csv", 50), "NQ": ("NQ_continuous_1m.csv", 20)}


def load(fname):
    df = pd.read_csv(os.path.join(UPLOADS, fname))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["dt"]   = dt
    df["date"] = dt.dt.date
    df["min"]  = dt.dt.hour * 60 + dt.dt.minute
    return df.sort_values("time").reset_index(drop=True)


def session_table(df):
    """Per-date RTH open/close + 30-min bucket closes."""
    rth = df[(df["min"] >= 570) & (df["min"] < 960)].copy()
    g   = rth.groupby("date")
    first = g.first()
    last  = g.last()
    out = pd.DataFrame({
        "rth_open":  first["open"].values,
        "rth_close": last["close"].values,
    }, index=first.index)
    return rth, out


def main():
    for inst, (fname, mult) in FILES.items():
        df = load(fname)
        rth, st = session_table(df)
        st = st.sort_index()

        prior_close = st["rth_close"].shift(1)
        overnight = (st["rth_open"] - prior_close).dropna()           # close[D-1] -> open[D]
        rth_ret   = (st["rth_close"] - st["rth_open"])                # open[D]   -> close[D]
        c2c       = (st["rth_close"] - prior_close).dropna()          # close[D-1]-> close[D]
        ndays     = len(overnight)

        def stats(s):
            s = s.dropna()
            usd = s * mult
            wr  = 100.0 * (s > 0).mean()
            # sharpe of daily $ (annualized ~252)
            shp = (usd.mean() / usd.std() * np.sqrt(252)) if usd.std() > 0 else 0.0
            return usd.sum(), usd.mean(), wr, shp

        print("=" * 72)
        print("  %s  --  %d sessions  %s -> %s  ($%d/pt)" % (
            inst, ndays, st.index.min(), st.index.max(), mult))
        print("=" * 72)
        print("  %-22s %12s %10s %7s %8s" % ("segment", "total $", "$/day", "win%", "ann.Sharpe"))
        for name, s in [("OVERNIGHT (close->open)", overnight),
                        ("RTH (open->close)",       rth_ret),
                        ("BUY & HOLD (close->close)", c2c)]:
            tot, avg, wr, shp = stats(s)
            print("  %-22s %12s %10.1f %6.0f%% %8.2f" % (
                name, "${:+,.0f}".format(tot), avg, wr, shp))

        # ---- RTH split into 30-min buckets -------------------------------------
        print("  " + "-" * 68)
        print("  RTH by 30-min bucket (open->close of each bucket, 1 contract):")
        print("  %-14s %12s %10s %7s" % ("bucket ET", "total $", "$/day", "win%"))
        buckets = [(570, 600, "09:30-10:00"), (600, 630, "10:00-10:30"),
                   (630, 690, "10:30-11:30"), (690, 750, "11:30-12:30"),
                   (750, 810, "12:30-13:30"), (810, 870, "13:30-14:30"),
                   (870, 930, "14:30-15:30"), (930, 960, "15:30-16:00")]
        for lo, hi, lbl in buckets:
            b = df[(df["min"] >= lo) & (df["min"] < hi)]
            gg = b.groupby("date")
            seg = (gg["close"].last() - gg["open"].first()).dropna()
            usd = seg * mult
            print("  %-14s %12s %10.2f %6.0f%%" % (
                lbl, "${:+,.0f}".format(usd.sum()), usd.mean(), 100.0 * (seg > 0).mean()))
        print()


if __name__ == "__main__":
    main()

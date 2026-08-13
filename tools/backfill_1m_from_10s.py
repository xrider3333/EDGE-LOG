# backfill_1m_from_10s.py — build 1-minute bars by aggregating the NinjaTrader
# 10-second capture, and EXTEND the matching nt_noadj_<session> 1m master with them.
#
# WHY THIS EXISTS (2026-08-13). The 1m non-adjusted masters had a hole:
# NOADJ_NQ_1m_ETH ended 2026-06-30, and tools/refresh_noadj_yahoo.py can only reach
# back 7 days, so topping up on 2026-08-12 appended a fresh tail from ~08-06 and left
# 07-01..08-05 permanently missing. That hole is exactly the window TradingView serves
# 1m bars for, which is why the ENGU-Q reconcile had zero overlap to work with.
#
# The NT 10s capture (source nt_noadj_eth) covers 2026-06-23..2026-08-12 continuously,
# so the 1m bars for the hole already exist in our own data — one aggregation away.
#
# Same feed in, same feed out: this only ever writes into the nt_noadj_<session> 1m
# master, never into the db_noadj_* series. No source mixing inside one file.
#
# Additive + idempotent, like refresh_noadj_yahoo.py: existing rows win on overlap.
#
# Run:  python tools/backfill_1m_from_10s.py [--session eth] [--inst NQ] [--dry-run]
import argparse
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
UP = os.path.join(ROOT, "augur_uploads")
DB = os.path.join(ROOT, "optimizer_history.db")

# Order-flow columns the 10s capture carries. They sum over the minute; the plain
# OHLCV columns do not, so they are handled separately below.
FLOW_SUM = ["volume", "delta", "buy_vol", "sell_vol", "tick_count"]


def _master(conn, inst, tf, source):
    df = pd.read_sql(
        "SELECT * FROM csv_files WHERE is_master=1 AND instrument=? "
        "AND timeframe=? AND source=?", conn, params=(inst, tf, source))
    return None if df.empty else df.iloc[0].to_dict()


def aggregate(df10):
    """10s OHLCV(+order flow) -> 1m. Bar stamped at the START of its minute, which is
    what the rest of the library assumes (a 09:30:00 bar covers 09:30:00-09:30:59)."""
    d = df10.copy()
    d["min"] = (d["time"] // 60) * 60
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for c in FLOW_SUM:
        if c in d.columns:
            agg[c] = "sum"
    out = d.groupby("min").agg(agg).reset_index().rename(columns={"min": "time"})
    # A minute assembled from fewer than 6 ten-second bars is a partial minute (feed
    # gap, or the edge of the capture). Keep it — dropping it would punch a new hole —
    # but the count is reported so a thin stretch is visible rather than silent.
    out["_n"] = d.groupby("min").size().values
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inst", default="NQ")
    ap.add_argument("--session", default="eth")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    src = f"nt_noadj_{args.session.lower()}"

    conn = sqlite3.connect(DB)
    try:
        m10 = _master(conn, args.inst, "10s", src)
        m1m = _master(conn, args.inst, "1m", src)
    finally:
        conn.close()
    if m10 is None:
        sys.exit(f"No {args.inst} 10s master tagged {src} — nothing to aggregate.")
    if m1m is None:
        sys.exit(f"No {args.inst} 1m master tagged {src} — run tools/import_nt_ohlc.py first.")

    p10 = os.path.join(UP, m10["filename"])
    p1m = os.path.join(UP, m1m["filename"])
    d10 = pd.read_csv(p10)
    d1m = pd.read_csv(p1m)

    built = aggregate(d10)
    thin = int((built["_n"] < 6).sum())
    built = built.drop(columns=["_n"])
    built = built[[c for c in d1m.columns if c in built.columns]]

    have = set(d1m["time"].astype("int64"))
    fresh = built[~built["time"].astype("int64").isin(have)]
    merged = pd.concat([d1m, fresh], ignore_index=True).sort_values("time")
    merged = merged.drop_duplicates(subset="time", keep="first").reset_index(drop=True)

    def _span(df):
        t = pd.to_datetime(df["time"], unit="s")
        return f"{t.min():%Y-%m-%d} .. {t.max():%Y-%m-%d}"

    print(f"10s master  : {m10['filename']}  {len(d10):,} rows  {_span(d10)}")
    print(f"1m  master  : {m1m['filename']}  {len(d1m):,} rows  {_span(d1m)}")
    print(f"aggregated  : {len(built):,} 1m bars ({thin:,} assembled from <6 ten-sec bars)")
    print(f"new bars    : {len(fresh):,}")
    if len(fresh):
        print(f"  covering  : {_span(fresh)}")
    print(f"result      : {len(merged):,} rows  {_span(merged)}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return
    if not len(fresh):
        print("\nNothing new — master already covers the 10s span.")
        return
    merged.to_csv(p1m, index=False)
    print(f"\nWrote {p1m}")


if __name__ == "__main__":
    main()

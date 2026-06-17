# stitch_noadj.py — build NON-ADJUSTED continuous ES/NQ masters from the same
# Databento raw files as stitch_databento.py, but SKIP the Panama back-adjust.
#
# Why: a non-adjusted continuous (raw front-month, with a price JUMP at each roll
# living overnight between sessions) pairs 1:1 with TradingView's NQ1!/ES1! when
# TV's "Back-adjustment" is OFF — both are raw front-month. Use these for a deeper
# trade-for-trade cross-check against TV across OLDER history (not just the recent
# raw segment). For INTRADAY-flat strategies (ORB) the edges are identical to the
# adjusted masters (point deltas are convention-invariant); for OVERNIGHT/swing
# strategies these are WRONG (fake roll-gap P&L) — keep using the adjusted masters
# there. That's why these land in augur_uploads/ with a NOADJ_ name and are NOT
# dropped in augur_watch/ (so they never auto-merge into the adjusted masters).
#
# Run:  python tools/stitch_noadj.py
import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stitch_databento as S          # reuse loaders/roll/resample helpers

OUT = S.UPLOADS                        # augur_uploads/ — manual-import location


def _rth_filter_1m(tv1m):
    """Keep 09:30-16:00 ET weekday cash session of a 1m TV frame (last bar 15:55)."""
    d = tv1m.copy()
    idx = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = idx.dt.hour * 60 + idx.dt.minute
    keep = (mins >= 9 * 60 + 30) & (mins < 16 * 60) & (idx.dt.dayofweek < 5)
    return d[keep.values].reset_index(drop=True)


def process_noadj(root):
    print(f"\n=== {root} (NON-ADJUSTED) ===")
    df = S._load_root(root)
    if df is None:
        print(f"  [{root}] no files found — skipping"); return
    active = S._active_by_day(df)
    df["active"] = df["day"].map(active)
    cont = df[df["cid"] == df["active"]].copy().sort_values("ts_event").reset_index(drop=True)
    print(f"  [{root}] continuous: {len(cont):,} bars  "
          f"{pd.to_datetime(cont['sec'].iloc[0], unit='s').date()} -> "
          f"{pd.to_datetime(cont['sec'].iloc[-1], unit='s').date()}  (NO back-adjust)")

    tv1     = S._to_tv(cont)               # full 1m = 1m ETH
    tv1_rth = _rth_filter_1m(tv1)
    tv5_eth = S._resample_5m(tv1, rth=False)
    tv5_rth = S._resample_5m(tv1, rth=True)

    os.makedirs(OUT, exist_ok=True)
    outs = {
        f"NOADJ_{root}_1m_ETH.csv":  tv1,
        f"NOADJ_{root}_1m_RTH.csv":  tv1_rth,
        f"NOADJ_{root}_5m_ETH.csv":  tv5_eth,
        f"NOADJ_{root}_5m_RTH.csv":  tv5_rth,
    }
    for fn, frame in outs.items():
        p = os.path.join(OUT, fn)
        frame.to_csv(p, index=False)
        mb = os.path.getsize(p) / 1e6
        print(f"  [{root}] wrote {fn:<22} {len(frame):>9,} bars  ({mb:,.1f} MB)")


def main():
    if not os.path.isdir(S.RAW_DIR):
        print(f"!! {S.RAW_DIR} not found"); sys.exit(1)
    for r in S.ROOTS:
        process_noadj(r)
    print("\nDone. Non-adjusted files are in augur_uploads/ (NOADJ_*). They are NOT "
          "in augur_watch, so they will not auto-merge into your adjusted masters. "
          "Import via the Library CSV tab if you want them selectable in-app, or point "
          "tools/xcheck_orb.py at them for an older-history cross-check vs TV (B-ADJ off).")


if __name__ == "__main__":
    main()

# diag_10s_stamp.py — is the NinjaTrader 10s export stamped at bar START or bar END,
# and do the consumers of api/paper.py::_resample rebuild the right bars from it?
#
# Rebuilds N-minute bars from the live 10s file three ways and scores each against the
# Databento masters (open/high/low/close must agree to the tick on the same bar time):
#   as-called   what `paper._resample(ticks, tf)` returns today — what api/bars.py (candle
#               window), api/gate_live.py (LIVE ML gate bouncer) and the paper tail get
#   start-stamp bucket = (time // sec) * sec           (10s stamp read as bar START)
#   end-stamp   bucket = ((time - 1) // sec) * sec     (10s stamp read as bar END)
# plus api/bars.py::_fresh_tail itself, the one consumer callable without a leg/cache.
#
# --backfill: same question for tools/backfill_1m_from_10s.py — the NQ 1m master it
# extended (source nt_noadj_eth) is compared with a start-stamped and an end-stamped
# aggregation of the 10s master, and with the Databento 1m master where they overlap.
#
# Run from any checkout; --data-root points the master registry at another checkout
# (the worktrees carry no optimizer_history.db / augur_uploads):
#   python tools/diag_10s_stamp.py --data-root "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
#   python tools/diag_10s_stamp.py --backfill --data-root ...
import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TOL = 0.25   # one ES/NQ tick


def _point_data_at(root):
    import augur_engine.data as D
    D.UPLOADS = os.path.join(root, "augur_uploads")
    D.DB_PATH = os.path.join(root, "optimizer_history.db")
    import augur_engine.paths as P
    P.UPLOADS, P.DB_PATH = D.UPLOADS, D.DB_PATH


def _unix(idx):
    """tz-aware DatetimeIndex -> int64 unix seconds (resolution-safe)."""
    utc = pd.DatetimeIndex(idx).tz_convert("UTC")
    return ((utc - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64")


def _master_df(inst, tf, session, date_from):
    from augur_engine.data import find_master, load_master_arrays
    m = find_master(inst, tf, session)
    if m is None:
        return None, None
    a = load_master_arrays(m, date_from=date_from)
    df = pd.DataFrame({"time": _unix(a["index"]),
                       "open": a["open"], "high": a["high"], "low": a["low"], "close": a["close"]})
    return m, df


def _score(bars, master):
    j = master.merge(bars, on="time", suffixes=("_m", "_b"))
    out = {"bars": len(bars), "matched": len(j)}
    for c in ("open", "high", "low", "close"):
        out[c] = int(((j[c + "_m"] - j[c + "_b"]).abs() > TOL).sum())
    return out


def _bucket(ticks, tf_min, shift):
    sec = tf_min * 60
    t = ticks["time"] - shift
    key = (t // sec) * sec
    g = ticks.groupby(key.values, sort=True)
    return pd.DataFrame({"time": g["open"].first().index.values,
                         "open": g["open"].first().values, "high": g["high"].max().values,
                         "low": g["low"].min().values, "close": g["close"].last().values,
                         "volume": g["volume"].sum().values})


def consumers(insts, date_from):
    from api import paper
    from api import bars as barsmod
    rows = []
    for inst in insts:
        ticks, path = paper._load_fresh_ticks(inst)
        if ticks is None:
            print(f"{inst}: no 10s file at {path}")
            continue
        ticks = ticks[ticks["time"] >= int(pd.Timestamp(date_from, tz="US/Eastern").timestamp())]
        for tf_min, session in ((5, "rth"), (1, "rth"), (1, "eth")):
            m, master = _master_df(inst, f"{tf_min}m", session, date_from)
            if master is None:
                continue
            variants = {
                "as-called (paper._resample)": paper._resample(ticks, tf_min),
                "start-stamp (time//sec)": _bucket(ticks, tf_min, 0),
                "end-stamp ((time-1)//sec)": _bucket(ticks, tf_min, 1),
            }
            if inst == "NQ":   # _fresh_tail reads the NQ file only (see api/bars.py)
                ft = barsmod._fresh_tail(f"{tf_min}m", session,
                                         pd.Timestamp(date_from, tz="US/Eastern"), lambda *_: None)
                if ft is not None:
                    variants["api/bars._fresh_tail"] = ft
            for name, b in variants.items():
                if session == "rth" and not name.startswith("api/bars"):
                    b, _ = paper._filter_rth(b, "rth")
                s = _score(b, master)
                rows.append({"inst": inst, "tf": f"{tf_min}m {session}", "master": m["filename"],
                             "method": name, **s})
    df = pd.DataFrame(rows)
    print(f"\n10s -> N-minute rebuild vs Databento masters, from {date_from} "
          f"(mismatch = |diff| > {TOL})\n")
    print(df.to_string(index=False))
    return df


def backfill(date_from):
    from augur_engine.data import find_master, UPLOADS
    from tools import backfill_1m_from_10s as B
    m10 = find_master("NQ", "10s", "eth", source="nt_noadj_eth")
    mnt = find_master("NQ", "1m", "eth", source="nt_noadj_eth")
    if m10 is None or mnt is None:
        print("backfill: no nt_noadj_eth 10s / 1m master registered")
        return
    d10 = pd.read_csv(os.path.join(UPLOADS, m10["filename"]))
    nt = pd.read_csv(os.path.join(UPLOADS, mnt["filename"]))
    nt = nt[["time", "open", "high", "low", "close"]].astype({"time": "int64"})
    span = lambda d: f"{pd.to_datetime(d['time'].min(), unit='s'):%Y-%m-%d} .. {pd.to_datetime(d['time'].max(), unit='s'):%Y-%m-%d}"
    print(f"\nnt_noadj_eth NQ 1m master {mnt['filename']}: {len(nt):,} rows {span(nt)}")
    print(f"nt_noadj_eth NQ 10s master {m10['filename']}: {len(d10):,} rows {span(d10)}")
    start = _bucket(d10, 1, 0)
    end = _bucket(d10, 1, 1)
    tool = B.aggregate(d10).drop(columns=["_n"])
    rows = []
    for name, b in (("start-stamp aggregate", start), ("end-stamp aggregate", end),
                    ("tools/backfill aggregate() as shipped", tool)):
        rows.append({"vs nt 1m master": name, **_score(b, nt)})
    print("\nWhich aggregation wrote the nt 1m master?")
    print(pd.DataFrame(rows).to_string(index=False))

    _, db = _master_df("NQ", "1m", "eth", "2026-06-01")
    rows = []
    for name, b in (("nt 1m master (as written)", nt), ("start-stamp aggregate", start),
                    ("end-stamp aggregate", end)):
        rows.append({"vs Databento 1m ETH": name, **_score(b, db)})
    print("\nAgainst the Databento 1m ETH master where they overlap (the July hole has no truth):")
    print(pd.DataFrame(rows).to_string(index=False))

    j = nt.merge(end, on="time", suffixes=("_m", "_b"))
    diff = ((j[["open_m", "high_m", "low_m", "close_m"]].values
             != j[["open_b", "high_b", "low_b", "close_b"]].values).any(axis=1))
    hole = (j["time"] >= int(pd.Timestamp("2026-07-01", tz="US/Eastern").timestamp())) & \
           (j["time"] < int(pd.Timestamp("2026-08-06", tz="US/Eastern").timestamp()))
    print(f"\nRows of the nt 1m master that an end-stamp rebuild would CHANGE: {int(diff.sum()):,} "
          f"of {len(j):,} ({int((diff & hole).sum()):,} inside the 07-01..08-05 hole)")
    newer = end[end["time"] > nt["time"].max()]
    print(f"Rows a plain re-run would APPEND (existing rows win): {len(newer):,} "
          f"({span(newer) if len(newer) else '-'})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--inst", default="NQ,ES")
    ap.add_argument("--from", dest="date_from", default="2026-07-01")
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    if a.data_root:
        _point_data_at(a.data_root)
    if a.backfill:
        backfill(a.date_from)
    else:
        consumers([s.strip().upper() for s in a.inst.split(",") if s.strip()], a.date_from)

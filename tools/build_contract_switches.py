"""Contract-switch ground truth for the Databento ZN / RTY / YM masters (MANAGER 11-18, for rolls.py).

Writes tools/data/contract_switches_<ROOT>.csv in the same columns as the NQ / ES files, which
tools/build_roll_table.py then turns into tools/data/rolls_<ROOT>.csv.

WHERE THE SWITCHES COME FROM. The masters (NOADJ_<ROOT>_1m_ETH.csv) were built front-month per UTC day:
augur_uploads/ROLLS_<ROOT>.csv lists the first UTC day each contract is used. So the master switches
contract at the first master bar on that UTC day. The OFFSET is measured on the raw per-contract 1m
Databento file: NEW close minus OLD close at the last minute before the switch where BOTH contracts
printed a bar (both trade on a roll day, so it is measurable). Same sign convention as NQ / ES:
positive = deferred contract dearer.

HOLE DAYS (2014-10-03, 2020-02-27, 2020-02-28, 2020-06-30) are masked: if the switch bar or the offset
minute falls on one, the row is still written but its source is 'databento_raw_hole' so the roll
table marks it estimated instead of exact. No switch is dropped.

    python tools/build_contract_switches.py --raw C:/EdgeLog/databento/GLBX-.../glbx-...ohlcv-1m.csv.zst \
        --uploads augur_uploads RTY ZN YM
"""
import argparse
import csv
import io
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tools", "data")
HOLE_DAYS = {"2014-10-03", "2020-02-27", "2020-02-28", "2020-06-30"}
COLS = ["root", "switch_sec", "switch_et", "utc_day", "old", "new", "master_idx_1m_eth", "master_jump",
        "prev_bar_et", "contract_offset", "source"]
LOOKBACK_MIN = 3 * 24 * 60   # look this far back for a minute where both contracts printed


def load_raw(path, roots):
    """Outright contracts of the given roots: DataFrame(sec, symbol, close)."""
    import zstandard
    want = tuple(roots)
    parts = []
    with open(path, "rb") as fh:
        rd = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(fh), encoding="utf-8")
        for ch in pd.read_csv(rd, usecols=["ts_event", "close", "symbol"], chunksize=2_000_000):
            s = ch["symbol"].astype(str)
            ok = s.str.match(r"^(%s)[FGHJKMNQUVXZ]\d{1,2}$" % "|".join(want))
            ch = ch[ok]
            if len(ch):
                parts.append(pd.DataFrame({"sec": pd.to_datetime(ch["ts_event"], utc=True).astype("int64") // 10**9,
                                           "symbol": ch["symbol"].astype(str).values,
                                           "close": ch["close"].astype(float).values}))
    return pd.concat(parts, ignore_index=True)


def et(sec):
    return pd.Timestamp(int(sec), unit="s", tz="UTC").tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M")


def build(root, raw, uploads):
    rolls = pd.read_csv(os.path.join(uploads, "ROLLS_%s.csv" % root))
    m = pd.read_csv(os.path.join(uploads, "NOADJ_%s_1m_ETH.csv" % root), usecols=["time", "close"])
    mt = m["time"].to_numpy()
    r = raw[raw["symbol"].str.startswith(root)]
    by = {s: g.set_index("sec")["close"] for s, g in r.groupby("symbol")}
    out = []
    for i in range(1, len(rolls)):
        old, new = rolls.symbol[i - 1], rolls.symbol[i]
        day0 = int(pd.Timestamp(rolls.first_day_utc[i], tz="UTC").timestamp())
        k = int(np.searchsorted(mt, day0))
        if k >= len(mt) or k == 0:
            continue
        sw = int(mt[k])
        a, b = by.get(old), by.get(new)
        both = a.index.intersection(b.index) if a is not None and b is not None else pd.Index([])
        both = both[(both < sw) & (both >= sw - LOOKBACK_MIN * 60)]
        if len(both):
            ps = int(both.max())
            off = float(b[ps] - a[ps])
            prev = et(ps)
        else:
            off, prev = float("nan"), ""
        hole = (et(sw)[:10] in HOLE_DAYS) or (prev[:10] in HOLE_DAYS) or not len(both)
        out.append(dict(root=root, switch_sec=sw, switch_et=et(sw), utc_day=rolls.first_day_utc[i], old=old, new=new,
                        master_idx_1m_eth=k, master_jump=round(float(m.close[k] - m.close[k - 1]), 6), prev_bar_et=prev,
                        contract_offset=round(off, 6), source="databento_raw_hole" if hole else "databento_raw"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--uploads", default=os.path.join(ROOT, "augur_uploads"))
    ap.add_argument("--out", default=DATA)
    ap.add_argument("roots", nargs="+")
    a = ap.parse_args()
    raw = load_raw(a.raw, a.roots)
    print("raw outright rows", len(raw))
    for root in a.roots:
        rows = build(root, raw, a.uploads)
        p = os.path.join(a.out, "contract_switches_%s.csv" % root)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
        nh = sum(1 for x in rows if x["source"] != "databento_raw")
        print("%s: %d switches, %d flagged (hole day or no shared minute) -> %s" % (root, len(rows), nh, p))


if __name__ == "__main__":
    sys.exit(main())

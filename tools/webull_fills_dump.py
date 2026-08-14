"""Dump raw Webull fills + the round-trips built from them.

Diagnostic for "my trade isn't showing": separates "the broker never gave it to us"
from "we got the fills but couldn't pair them into a round-trip" (open position,
partial fill, or a symbol whose buys/sells straddle the window edge).

    python -m tools.webull_fills_dump --days 7
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import webull_sync as W  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default=W.DEFAULT_KEYS)
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()

    keys = W.load_keys(a.keys)
    if not keys:
        print("no keys configured")
        return

    start = (datetime.now() - timedelta(days=a.days)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"window {start} .. {end} (end exclusive-safe)\n")

    fills = W.fetch_fills(keys, start, end, log=lambda *_: None)
    print(f"RAW FILLS ({len(fills)}):")
    for f in fills:
        print("   ", {k: f.get(k) for k in
                      ("date", "time", "symbol", "action", "qty", "price", "orderId")
                      if k in f} or f)

    trades = W.build_trades(fills)
    print(f"\nROUND-TRIPS BUILT ({len(trades)}):")
    for t in trades:
        print(f"    {t.get('date')}  {t.get('symbol'):<6} "
              f"{float(t.get('entry') or 0):>8.2f} -> {float(t.get('exit') or 0):>8.2f}  "
              f"{float(t.get('pnl') or 0):>9.2f}")

    paired = sum(int(t.get("size") or 0) for t in trades)
    print(f"\nfills={len(fills)}  round-trips={len(trades)}  "
          f"(unpaired fills usually = an OPEN position or a partial)")
    print(f"paired size total = {paired}")


if __name__ == "__main__":
    main()

"""Dump the UNPARSED Webull order payloads for a symbol.

For settling "the broker says X, the journal says Y" — shows the exact fields the
API returned (filled price to full precision, fees, commission) before our parser
touches them.

    python -m tools.webull_raw_orders --symbol XHG --days 9
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import webull_sync as W  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default=W.DEFAULT_KEYS)
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--days", type=int, default=9)
    a = ap.parse_args()

    keys = W.load_keys(a.keys)
    if not keys:
        print("no keys configured")
        return

    start = (datetime.now() - timedelta(days=a.days)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    raw = []
    quiet = lambda *_a, **_k: None  # noqa: E731
    orders = W._fetch_raw_orders(keys, start, end, log=quiet) \
        if hasattr(W, "_fetch_raw_orders") else None
    if orders is None:
        print("no raw hook on this build — falling back to parsed fills")
        for f in W.fetch_fills(keys, start, end, log=quiet):
            if not a.symbol or f["symbol"] == a.symbol.upper():
                print(json.dumps(f, default=str, indent=2))
        return

    for o in orders:
        sym = str(W._field(o, "symbol", "ticker", default="")).upper()
        if a.symbol and sym != a.symbol.upper():
            continue
        raw.append(o)

    print(f"{len(raw)} raw order(s) for {a.symbol or 'ALL'} in {start}..{end}\n")
    for o in raw:
        print(json.dumps(o, default=str, indent=2, sort_keys=True))
        print("-" * 60)


if __name__ == "__main__":
    main()

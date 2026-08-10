"""Standalone smoke test for api/paper.py — no Firestore, no runner.

Monkeypatches PAPER_START to ~30 days ago so run_shadow has a realistic amount of
history to actually emit trades against the master + fresh-tail data, then calls
run_shadow() for each crowned leg directly and prints a per-leg summary.

Run: python3.13.exe tools/paper_smoke.py
Exits 0 on success (both legs ran without an exception-class warning), 1 otherwise.
"""
import sys
import pathlib
import datetime as dt

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402
from api import paper  # noqa: E402


def main():
    # Use a PAPER_START far enough back that the fixed masters (which stop wherever
    # they were last refreshed) plus the live 10s tail plausibly cover trades, without
    # requiring the smoke test to be run on the real PAPER_START day.
    today = dt.date.today()
    fake_start = (today - dt.timedelta(days=30)).isoformat()
    paper.PAPER_START = fake_start
    print(f"[smoke] PAPER_START monkeypatched to {fake_start}")
    print(f"[smoke] today (used for warm-up window + staleness check): {today}")

    ok = True
    for leg in paper.PAPER_LEGS:
        print(f"\n[smoke] === leg {leg['key']} ({leg['strategy']}, "
              f"{leg['instrument']} {leg['timeframe']} {leg['session']}) ===")
        r = paper.run_shadow(leg, today)
        trades = r["trades"]
        n = len(trades)
        total_pnl = sum(t["pnl_usd"] for t in trades)
        first_iso = trades[0]["entry_dt"].isoformat() if n else None
        last_iso = trades[-1]["entry_dt"].isoformat() if n else None

        print(f"  trades: {n}")
        print(f"  total pnl_usd: {total_pnl:,.2f}")
        print(f"  first entry: {first_iso}")
        print(f"  last entry: {last_iso}")
        print(f"  bars_appended: {r['bars_appended']}")
        print(f"  data_fresh_thru: {r['data_fresh_thru']} "
              f"({pd.Timestamp(r['data_fresh_thru'], unit='s', tz='UTC').tz_convert('US/Eastern') if r['data_fresh_thru'] else 'n/a'})")
        print(f"  warnings: {r['warnings'] or '(none)'}")

        for w in r["warnings"]:
            if w.startswith("exception"):
                ok = False
                print(f"  [smoke] FAIL: {w}")

    print(f"\n[smoke] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

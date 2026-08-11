"""Bar-by-bar trace of what ORB #125 does in a session, and WHEN it knows it.

Built to answer: "why can't NinjaTrader just run what the backtester runs?"

For each recent RTH session it prints the opening range, then every bar that touches a
range edge, showing:
    touch time  -> the moment a resting stop order would fill (INTRABAR)
    bar close   -> the moment that bar's volume becomes known
    vol vs gate -> the test the engine applies to decide whether to take that touch

If a row says TAKEN, the engine bought at the level at the touch time but used the
volume figure that only existed at the bar close. That ordering is the whole issue.

Run:  python3.13.exe tools/orb_session_trace.py [--sessions 3] [--csv out.csv]
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402

OR_BARS = 1
STOP_FRAC = 0.75
VOL_FILTER = 1.25
MULT = 20.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=3)
    ap.add_argument("--csv", default="")
    a = ap.parse_args()

    master = find_master("NQ", "5m", "rth")
    arr = load_master_arrays(master, date_from=None, date_to=None)
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    v, did, idx = arr["volume"], arr["day_id"], arr["index"]

    bounds, s, n = [], 0, len(c)
    while s < n:
        e = s
        while e < n and did[e] == did[s]:
            e += 1
        bounds.append((s, e)); s = e
    bounds = bounds[-a.sessions:]

    rows = []
    for (s, e) in bounds:
        m = e - s
        so, sh, sl, sc = o[s:e], h[s:e], l[s:e], c[s:e]
        sv = v[s:e]
        or_hi = sh[:OR_BARS].max(); or_lo = sl[:OR_BARS].min()
        rng = or_hi - or_lo
        day = idx[s].date()
        print()
        print("=" * 100)
        print(f"SESSION {day}   bars={m}   opening range (first {OR_BARS} bar): "
              f"{or_lo:,.2f} - {or_hi:,.2f}  (width {rng:,.2f})")
        print(f"  a LONG stop rests at {or_hi:,.2f}, a SHORT stop at {or_lo:,.2f}")
        print("-" * 100)
        print(f"{'bar close (ET)':<18}{'side':<7}{'fill @':>10}{'bar vol':>10}"
              f"{'gate (1.25x)':>14}{'verdict':>28}")
        print("-" * 100)
        taken = False
        for k in range(OR_BARS, m):
            up = sh[k] >= or_hi
            dn = sl[k] <= or_lo
            if not (up or dn):
                continue
            mv = sv[:k].mean() if k > 0 else 0.0
            gate = VOL_FILTER * mv
            passes = mv > 0 and sv[k] >= gate
            side = "LONG" if up else "SHORT"
            fill = or_hi if up else or_lo
            if so[k] > or_hi and up:
                fill = so[k]
            if so[k] < or_lo and dn:
                fill = so[k]
            if taken:
                verdict = "(already in a trade)"
            elif passes:
                verdict = "TAKEN  <- needs the bar's volume"
                taken = True
            else:
                verdict = "skipped (thin)"
            print(f"{str(idx[s + k])[:19]:<18}{side:<7}{fill:>10,.2f}{sv[k]:>10,.0f}"
                  f"{gate:>14,.0f}{verdict:>28}")
            rows.append(dict(session=str(day), bar_close=str(idx[s + k])[:19], side=side,
                             fill=round(float(fill), 2), bar_volume=int(sv[k]),
                             gate=int(gate), passed=bool(passes), taken=verdict))
        if not taken:
            print("  -> engine took NO trade this session")
        else:
            print("  -> engine took exactly ONE trade this session")

    print()
    print("=" * 100)
    print("Every 'skipped (thin)' row is a touch a resting stop order WOULD have filled in real")
    print("time. The engine declines them using the bar's finished volume - a number that does")
    print("not exist until minutes after the fill. That is the gap, and no platform can close it.")
    if a.csv:
        import csv as _csv
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"\nwrote {len(rows)} rows -> {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

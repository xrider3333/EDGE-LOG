# reconcile_nt_dump.py — compare a NinjaTrader self-dumped blotter against the AUGUR engine.
#
# WHY THIS EXISTS (2026-08-13). Reconciling NinjaTrader by hand meant: configure the
# Strategy Analyzer, run, switch the Display dropdown to Trades, right-click, Export, and
# hand over the file. That loop produced the WRONG FILE twice in one morning - once the
# wrong strategy, once the wrong timeframe - and in both cases nothing looked wrong until
# the CSV was parsed. The Strategy Analyzer grid export carries no record of what was run.
#
# So the strategies now write their own blotter on State.Terminated (see
# tools/nt/EdgeLogNOISE.cs, DumpBlotter) into C:\EdgeLog\nt_backtest, with the run's real
# configuration in the header. This reader asserts on that header instead of trusting that
# the right thing was selected in the UI.
#
# TWO TIMESTAMP OFFSETS have to be undone before anything lines up:
#   1. Timezone. NinjaTrader displays in the PC's local zone - Arizona here, which does not
#      observe DST, so the offset to Eastern is 3h in summer and 2h in winter and a single
#      constant will not do. The dump writes UTC, which removes this entirely.
#   2. Bar stamping. NinjaTrader stamps a bar at its CLOSE; the AUGUR engine (and
#      TradingView) stamp at its OPEN. So an NT fill on the 09:45 bar is the engine's 09:40
#      bar. --bar-min (default 5) subtracts one bar width.
#
# Run:  python tools/reconcile_nt_dump.py --strategy NOISE_1_0.py --inst NQ --tf 5m
#           --session RTH --from 2025-08-18 --to 2026-07-16 --params "stop_mode=bandwidth,stop_k=1.0"
#       (--dump defaults to the newest file in C:\EdgeLog\nt_backtest)
import argparse
import glob
import os
import sys
from collections import Counter

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.reconcile import (  # noqa: E402
    Trade, edgelog_blotter, match, MULT,
)

DUMP_DIR = os.environ.get("EDGELOG_NT_BACKTEST", r"C:\EdgeLog\nt_backtest")


def read_dump(path, bar_min):
    """Parse a self-dumped blotter -> (list[Trade], header dict).

    Entry/exit times come back as naive US/Eastern, shifted back by one bar width so they
    sit on the same stamp convention the engine uses."""
    header = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            k, _, v = line[1:].strip().partition("=")
            header[k.strip()] = v.strip()
    df = pd.read_csv(path, comment="#")

    def to_et(col):
        t = pd.to_datetime(df[col], utc=True).dt.tz_convert("America/New_York")
        return t.dt.tz_localize(None) - pd.Timedelta(minutes=bar_min)

    ent, ext = to_et("entry_utc"), to_et("exit_utc")
    trades = [
        Trade(entry_dt=ent[i], exit_dt=ext[i], side=int(df["side"][i]),
              qty=float(df["qty"][i]), entry_px=float(df["entry_px"][i]),
              exit_px=float(df["exit_px"][i]), pnl_usd=float(df["pnl_usd"][i]),
              raw={"exit_name": df["exit_name"][i]})
        for i in range(len(df))
    ]
    return trades, header


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", default="auto", help="blotter CSV, or 'auto' = newest in the dump dir")
    ap.add_argument("--strategy", default="NOISE_1_0.py")
    ap.add_argument("--inst", default="NQ")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--session", default="RTH")
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--params", default="")
    ap.add_argument("--cost-pts", type=float, default=0.283)
    ap.add_argument("--bar-min", type=int, default=5,
                    help="bar width in minutes; NT stamps at close, the engine at open")
    ap.add_argument("--tol-min", type=int, default=2)
    a = ap.parse_args()

    path = a.dump
    if path == "auto":
        cand = sorted(glob.glob(os.path.join(DUMP_DIR, "*.csv")), key=os.path.getmtime)
        if not cand:
            sys.exit(f"No blotter in {DUMP_DIR}. Run the strategy in the Strategy Analyzer first.")
        path = cand[-1]

    b, hdr = read_dump(path, a.bar_min)
    print(f"NT dump   : {os.path.basename(path)}  ({len(b)} trades)")
    for k in ("strategy", "instrument", "bars", "trading_hours"):
        print(f"  {k:14s}= {hdr.get(k, '?')}")
    print(f"  params        = {hdr.get('lookback', '?')}")

    params = {}
    for kv in filter(None, a.params.split(",")):
        k, _, v = kv.partition("=")
        try:
            v = float(v) if "." in v else int(v)
        except ValueError:
            pass
        params[k.strip()] = v

    mult = MULT.get(a.inst.upper(), 1)
    eng, meta = edgelog_blotter(a.strategy, a.inst, a.tf, a.session, params,
                                date_from=a.date_from, date_to=a.date_to,
                                cost_pts=a.cost_pts, mult=mult)
    print(f"\nEDGELOG   : {a.strategy} on {a.inst} {a.tf} {a.session} | "
          f"master {meta['master']} ({len(eng)} trades)")

    lo = min(t.entry_dt for t in eng) if eng else None
    hi = max(t.entry_dt for t in eng) if eng else None
    if lo is not None:
        b = [t for t in b if lo <= t.entry_dt <= hi]

    pairs, ua, ub = match(eng, b, 0, a.tol_min)
    ident = [(x, y) for x, y, _ in pairs if x.exit_dt == y.exit_dt]
    print(f"\n  matched            {len(pairs)}")
    print(f"  exit bar identical {len(ident)}   PnL gap ${sum(y.pnl_usd - x.pnl_usd for x, y in ident):,.0f}")
    print(f"  unmatched engine   {len(ua)}  (${sum(t.pnl_usd for t in ua):,.0f})")
    print(f"  unmatched NT       {len(ub)}  (${sum(t.pnl_usd for t in ub):,.0f})")
    print(f"  total  engine ${sum(t.pnl_usd for t in eng):,.0f} | NT ${sum(t.pnl_usd for t in b):,.0f}")

    if pairs:
        # A steadily DECAYING price gap is the fingerprint of a back-adjusted continuous
        # contract: every prior contract is shifted by the accumulated roll gaps, and the
        # shift shrinks as you approach the front month. Our masters are non-adjusted, so
        # anything but ~0 here means NinjaTrader's merge policy needs changing.
        d = sorted((x.entry_dt, y.entry_px - x.entry_px) for x, y, _ in pairs)
        first = [v for _, v in d[:max(1, len(d) // 5)]]
        last = [v for _, v in d[-max(1, len(d) // 5):]]
        print(f"\n  entry-price gap NT-engine: first fifth {sum(first)/len(first):+.1f} pts, "
              f"last fifth {sum(last)/len(last):+.1f} pts")
        if abs(sum(first) / len(first)) > 5:
            print("  -> NON-ZERO AND DECAYING = back-adjusted contract. Set NQ's Merge Policy")
            print("     to 'Merge Non Back Adjusted' (Tools > Instruments) and re-run.")

    if ub:
        print("\n  unmatched NT by entry hour:",
              sorted(Counter(t.entry_dt.strftime("%H") for t in ub).items()))
    if ua:
        print("  unmatched engine by entry hour:",
              sorted(Counter(t.entry_dt.strftime("%H") for t in ua).items()))


if __name__ == "__main__":
    main()

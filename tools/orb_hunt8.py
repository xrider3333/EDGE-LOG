"""
ORB HUNT ROUND 8 (2026-09-05) - owner: "keep hunting."

The base is now the ROUND-7 candidate, not the crown: run #314's exit plus the prior-day
LONG filter that round 7 rescued off ORB.md's shelf, with the stop at 3.0x.

    or_bars 2 / first-candle dir / close-confirm / buffer 0.25 / stop 3.0x / target 5.0R
    breakeven 0.5R / vol-regime 0.75 / volume-pace 0.80
    daytype_mode skip_band_long, band 0.60-0.85

THE QUESTION THIS ROUND ASKS, and it is a different question from rounds 5-7. Every round
so far has made ORB trade LESS: #234 took 2,607 trades, #314 takes 2,299, the round-7
candidate takes 2,010, and the longest drought has gone from 13 calendar days to 28. That
is the one honest complaint against the whole direction of travel - a strategy nobody can
sit through is not tradeable however good its drawdown looks.

But rounds 5-7 tightened the two VOLATILITY filters as a blunt way of avoiding bad trades,
and round 7 then removed a specific, named, losing population directly. If the prior-day
filter is doing the real work, the blunt instrument may no longer be earning its keep - so
this round tries to give the trades BACK by loosening the filters, and asks whether the
risk gains survive.

    A `loosen`   the two filters re-opened (vol-regime 0.0-0.80, volume-pace 0.60-0.85) on
                 top of the prior-day filter. Success = MORE trades and a SHORTER drought
                 without losing the round-7 risk numbers.
    B `context`  the OTHER prior-day modes the knob already offers, now that the band-long
                 one is proven: skip_bot_short, skip_top_long and the thresholds behind
                 them, alone and stacked with the band.
    C `finer`    a finer partial / trail grid than round 7's coarse pass, which found the
                 family alive again on this exit after being dead on #234's.

PRE-REGISTERED GATE - written before running, and CARRIED UNCHANGED from round 7 so the bar
cannot drift: a cell is adopt-worthy only if all four hold against the ROUND-7 BASE.

    1. annualised MAR on the FULL window        >  base
    2. annualised MAR on the LAST 5 YEARS       >  base
    3. sliced lockbox net                       >= base
    4. worst rolling 12 months                  >= base

Sweep A additionally reports TRADES and the longest drought, because for that sweep the
whole point is whether the tradeability cost can be bought back. A cell that clears the
gate AND trades more is the thing this round is looking for; one that clears while trading
even less is just more of what rounds 5-7 already did.

EV R is printed and cannot make a cell adopt-worthy - it is gameable across the breakeven
(tools/orb_pick.py), which is why the breakeven is not swept anywhere in this file.

    python tools/orb_hunt8.py [loosen|context|finer|all]
"""
import os
import sys
import itertools

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END                      # noqa: E402
from tools.orb_hunt3 import robustness                                # noqa: E402
from tools.orb_hunt7 import bars, slice_stats, COST, MULT, FIVE_Y     # noqa: E402

# the round-7 candidate, ORB_3_8_R7.py's defaults
BASE_CFG = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
                partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
                breakout_buf=0.25, stop_frac=3.0, target_R=5.0, be_after_R=0.5,
                atr_filter=0.75, vpace_filter=0.8,
                daytype_mode="skip_band_long", daytype_band_lo=0.6, daytype_band_hi=0.85)

STRATEGY = "ORB_3_8.py"
BASE = None


def measure(over):
    b = bars()
    r = strat(STRATEGY).run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(BASE_CFG, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    ie = pd.Timestamp(IS_END, tz=idx.tz)
    tr, lb = [], 0.0
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d > le:
            continue
        v = (t[2] - COST) * MULT
        tr.append((d.tz_localize(None), v))
        if d > ie:
            lb += v
    full = slice_stats(tr)
    five = slice_stats(tr, FIVE_Y)
    if not full or not five:
        return None
    dts = [d for d, _ in tr]
    gaps = [(dts[i + 1] - dts[i]).days for i in range(len(dts) - 1)]
    return dict(full=full, five=five, lb=lb,
                maxgap=max(gaps) if gaps else 0,
                p95gap=int(np.percentile(gaps, 95)) if gaps else 0)


def gate(m):
    legs = dict(mar_full=m["full"]["mar"] > BASE["full"]["mar"],
                mar_5y=m["five"]["mar"] > BASE["five"]["mar"],
                lockbox=m["lb"] >= BASE["lb"],
                worst=m["full"]["worst"] >= BASE["full"]["worst"])
    return legs, all(legs.values())


HDR = ("%-32s %6s %6s %6s | %8s %6s | %10s %8s %6s %6s | %9s %9s %s"
       % ("config", "trd", "gap", "p95", "DD$ 5y", "MAR5", "net$ full", "DD$ full",
          "MARf", "EVRf", "lockbox", "worst12", "gate"))


def line(label, m, flag=""):
    f, v = m["full"], m["five"]
    print("%-32s %6d %6d %6d | %8s %6.2f | %10s %8s %6.2f %6.3f | %9s %9s %s"
          % (label[:32], f["n"], m["maxgap"], m["p95gap"], f"{v['dd']:,.0f}", v["mar"],
             f"{f['net']:,.0f}", f"{f['dd']:,.0f}", f["mar"], f["evr"],
             f"{m['lb']:,.0f}", f"{f['worst']:,.0f}", flag))


def sweep(name, cells):
    print("\n" + "=" * 140)
    print("%s   (%d cells)" % (name, len(cells)))
    print("=" * 140)
    print(HDR)
    print("-" * 140)
    line("BASE round-7 candidate", BASE, "<- the bar")
    print("-" * 140)
    hits = []
    for label, over in cells:
        try:
            m = measure(over)
        except Exception as e:
            print("%-32s ERROR %s: %s" % (label[:32], type(e).__name__, e))
            continue
        if not m:
            continue
        legs, ok = gate(m)
        tag = "".join(k[0].upper() if v else "." for k, v in legs.items())
        if ok:
            tag += "  <== CLEARS"
            if m["full"]["n"] > BASE["full"]["n"]:
                tag += " +%d TRADES" % (m["full"]["n"] - BASE["full"]["n"])
        line(label, m, tag)
        if ok:
            hits.append((label, over, m))
    print("-" * 140)
    print("cleared: %d of %d" % (len(hits), len(cells)))
    return hits


def cells_loosen():
    out = []
    for a, v in itertools.product([0.0, 0.40, 0.55, 0.65, 0.70, 0.75],
                                  [0.60, 0.65, 0.70, 0.75, 0.80, 0.85]):
        out.append(("atr %.2f vpace %.2f" % (a, v), dict(atr_filter=a, vpace_filter=v)))
    return out


def cells_context():
    out = []
    for mode in ("skip_bot_short", "skip_top_long", "skip_bot_all", "skip_top_all"):
        for lo, hi in [(0.15, 0.85), (0.20, 0.80), (0.25, 0.75), (0.30, 0.70)]:
            out.append(("%s %.2f/%.2f (no band)" % (mode.replace("skip_", ""), lo, hi),
                        dict(daytype_mode=mode, daytype_lo=lo, daytype_hi=hi)))
    return out


def cells_finer():
    out = []
    for pe in [0.0, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        for tb in [0, 2, 3, 4, 6]:
            out.append(("partial %.1f trail %d" % (pe, tb),
                        dict(partial_exit_R=pe, trail_bars=tb)))
    return out


SWEEPS = {"loosen": cells_loosen, "context": cells_context, "finer": cells_finer}


def main():
    global BASE
    BASE = measure({})
    print("ORB ROUND 8 - can the trades come back?")
    print("  base: the round-7 candidate (crown #314 exit + prior-day long filter + stop 3.0)")
    print("  base reads: %d trades, longest drought %d days, 5y MAR %.2f, full MAR %.2f, "
          "lockbox $%s, worst12 $%s"
          % (BASE["full"]["n"], BASE["maxgap"], BASE["five"]["mar"], BASE["full"]["mar"],
             f"{BASE['lb']:,.0f}", f"{BASE['full']['worst']:,.0f}"))
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    todo = list(SWEEPS) if what == "all" else [what]
    total = []
    for s in todo:
        total += sweep(s.upper(), SWEEPS[s]())
    print("\n" + "=" * 140)
    print("ROUND 8: %d cell(s) cleared all four legs." % len(total))
    more = [h for h in total if h[2]["full"]["n"] > BASE["full"]["n"]]
    print("of those, %d ALSO trade more than the base (the thing this round was after):" % len(more))
    for label, over, m in more:
        print("   %-30s %+d trades, drought %d -> %d days, %s"
              % (label, m["full"]["n"] - BASE["full"]["n"], BASE["maxgap"], m["maxgap"], over))
    print("=" * 140)


if __name__ == "__main__":
    main()

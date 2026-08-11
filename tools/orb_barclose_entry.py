"""Owner's proposal, measured: make ORB wait for the bar to CLOSE.

The question: "if NinjaTrader waited until the candle closed and applied the volume
filter there, wouldn't it match EdgeLog?"

It would match on WHICH bars get taken -- same touch test, same volume gate, and at the
close that bar's volume is honestly known. What it cannot match is the FILL PRICE. The
engine fills at the range EDGE (a resting order, filled mid-candle); waiting for the close
means entering wherever price ended up, which on a breakout bar is further away.

So this isolates the two effects:

  A  engine #125          trigger on touch | gate on full-bar volume | fill at the EDGE
  E  bar-close entry      trigger on touch | gate on full-bar volume | fill at the CLOSE

Same trades, different fill. Whatever gap appears between A and E is the value of the
edge fill -- the part that needs the future to exist.

Run:  python3.13.exe tools/orb_barclose_entry.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402

OR_BARS, STOP_FRAC, VOL_FILTER = 1, 0.75, 1.25
MULT, COST_PTS = 20.0, 0.533
BASE = dict(or_bars=OR_BARS, trade_mode="Both", stop_frac=STOP_FRAC,
            vol_filter=VOL_FILTER, breakout_buf=0.0, target_R=0.0, flat_eod=True)


def sessions(day_id):
    out, a, n = [], 0, len(day_id)
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        out.append((a, b)); a = b
    return out


def sim(o, h, l, c, v, day_id, fill_at_close):
    """One trade per session. fill_at_close=False reproduces the engine (fill at the
    range edge); True is the owner's bar-close-entry proposal."""
    pnl = []
    for (s, e) in sessions(day_id):
        m = e - s
        if m <= OR_BARS + 1:
            continue
        so, sh, sl, sc = o[s:e], h[s:e], l[s:e], c[s:e]
        sv = v[s:e]
        or_hi, or_lo = sh[:OR_BARS].max(), sl[:OR_BARS].min()
        rng = or_hi - or_lo
        if rng <= 0:
            continue
        pos, entry, stop = 0, 0.0, 0.0
        for k in range(OR_BARS, m):
            if pos == 0:
                up, dn = sh[k] >= or_hi, sl[k] <= or_lo
                if not (up or dn):
                    continue
                mv = sv[:k].mean() if k > 0 else 0.0
                if VOL_FILTER > 0 and not (mv > 0 and sv[k] >= VOL_FILTER * mv):
                    continue
                if fill_at_close:
                    entry = sc[k]
                else:
                    entry = (so[k] if so[k] > or_hi else or_hi) if up else \
                            (so[k] if so[k] < or_lo else or_lo)
                pos = 1 if up else -1
                stop = entry - pos * STOP_FRAC * rng
                continue
            if pos > 0 and sl[k] <= stop:
                ex = so[k] if so[k] < stop else stop
                pnl.append(ex - entry); pos = 0; break
            if pos < 0 and sh[k] >= stop:
                ex = so[k] if so[k] > stop else stop
                pnl.append(entry - ex); pos = 0; break
        if pos != 0:
            pnl.append((sc[-1] - entry) if pos > 0 else (entry - sc[-1]))
    return np.array(pnl, float)


def stats(p, years, label):
    if not len(p):
        print(f"{label:<38}{'no trades':>10}")
        return
    net = float((p - COST_PTS).sum()) * MULT
    w, lo = p[p > 0], p[p < 0]
    pf = float(w.sum()) / max(abs(float(lo.sum())), 1e-9)
    cum = np.cumsum((p - COST_PTS) * MULT)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    mar = (net / years) / dd if dd else 0.0
    print(f"{label:<38}{len(p):>8,}{net:>12,.0f}{net/years:>10,.0f}{pf:>7.2f}{dd:>11,.0f}{mar:>7.2f}")


def main():
    master = find_master("NQ", "5m", "rth")
    arr = load_master_arrays(master, date_from=None, date_to=None)
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    v, did, idx = arr["volume"], arr["day_id"], arr["index"]
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    print(f"NQ 5m RTH  {idx[0].date()} -> {idx[-1].date()}  ({years:.1f}y)")
    print()
    print(f"{'variant':<38}{'trades':>8}{'net $':>12}{'$/yr':>10}{'PF':>7}{'maxDD $':>11}{'MAR':>7}")
    print("-" * 93)
    eng = run_backtest("ORB_3_0.py", arrays=arr, params=BASE, cost_pts=COST_PTS)
    print(f"{'engine #125 (reference)':<38}{eng['num_trades']:>8,}"
          f"{eng['total_pnl'] * MULT:>12,.0f}{eng['total_pnl'] * MULT / years:>10,.0f}"
          f"{eng['profit_factor']:>7.2f}{abs(eng['max_drawdown']) * MULT:>11,.0f}"
          f"{((eng['total_pnl'] * MULT) / years) / max(abs(eng['max_drawdown']) * MULT, 1e-9):>7.2f}")
    stats(sim(o, h, l, c, v, did, False), years, "A  my rebuild, fill at EDGE")
    stats(sim(o, h, l, c, v, did, True), years, "E  wait for close, fill at CLOSE")
    print()
    print("A should track the engine closely (same rules) -- that validates the rebuild.")
    print("E is A with ONLY the fill price changed to something reachable in real time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

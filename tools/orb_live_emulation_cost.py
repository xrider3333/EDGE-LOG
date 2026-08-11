"""What does ORB's volume filter COST to run live?

The engine checks a breakout bar's FINISHED volume before deciding to enter. That is
information nobody has while the bar is still forming, so the NinjaScript port
(tools/nt/EdgeLogORB30.cs) can only enter on the stop, wait for the bar to close, and
eject if the bar turns out thin -- then re-arm.

This script replays BOTH rule-sets over the same bars and prices the difference:

  ENGINE : skip thin breakout bars entirely (look-ahead, costless)   -> augur_strategies/ORB_3_0.py
  PORT   : enter, discover thin at the close, exit at that close, re-arm (live-legal)

Output: trades, net $, and the total/av per-session cost of the ejections.

Run:  python3.13.exe tools/orb_live_emulation_cost.py [--years 5]
"""
import argparse
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402

# ORB #125 (the crowned config the runner shadow-trades) -- see api/paper.py
ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, flat_eod=True)
MULT = 20.0          # NQ $/point
COST_PTS = 0.533     # round-turn commission+slippage in points


def _sessions(day_id):
    out, a, n = [], 0, len(day_id)
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        out.append((a, b))
        a = b
    return out


def port_sim(o, h, l, c, v, day_id, p):
    """Replay the NinjaScript port's rules: enter on the stop, eject at the bar close
    if that bar was thin, re-arm. One REAL trade per session (ejections don't count)."""
    or_bars = int(p["or_bars"]); stop_frac = float(p["stop_frac"])
    volf = float(p["vol_filter"]); buf = float(p["breakout_buf"])
    real, ejects = [], []

    for (s, e) in _sessions(day_id):
        m = e - s
        if m <= or_bars + 1:
            continue
        so, sh, sl, sc = o[s:e], h[s:e], l[s:e], c[s:e]
        sv = v[s:e] if v is not None else None
        or_hi = sh[:or_bars].max(); or_lo = sl[:or_bars].min()
        rng = or_hi - or_lo
        if rng <= 0:
            continue
        up_lvl = or_hi + buf * rng
        dn_lvl = or_lo - buf * rng

        pos = 0; entry = 0.0; stop = 0.0; done = False
        k = or_bars
        while k < m and not done:
            if pos == 0:
                # A resting stop entry can only EXIST on the correct side of the market:
                # a buy-stop must sit ABOVE price, a sell-stop BELOW. After an ejection,
                # price is usually already through the level, so the order cannot be
                # re-placed until price comes back. Without this NT-realistic constraint
                # the sim re-fires every bar and wildly over-counts ejections.
                prev_close = sc[k - 1]
                can_arm_up = prev_close < up_lvl
                can_arm_dn = prev_close > dn_lvl
                up = can_arm_up and sh[k] >= up_lvl
                dn = can_arm_dn and sl[k] <= dn_lvl
                if not (up or dn):
                    k += 1
                    continue
                if up:
                    entry = so[k] if so[k] > up_lvl else up_lvl
                    pos = 1
                else:
                    entry = so[k] if so[k] < dn_lvl else dn_lvl
                    pos = -1
                # ---- the live-only step: was this bar thin? judged at ITS close ----
                thin = False
                if volf > 0 and sv is not None and k > 0:
                    mv = sv[:k].mean()
                    thin = mv > 0 and sv[k] < volf * mv
                if thin:
                    ex = sc[k]                       # eject at that bar's close
                    ejects.append((ex - entry) * pos)
                    pos = 0
                    k += 1                            # re-arm from the next bar
                    continue
                stop = entry - pos * stop_frac * rng
                k += 1
                continue
            # in a real position -- stop, else ride to session close
            if pos > 0:
                if sl[k] <= stop:
                    ex = so[k] if so[k] < stop else stop
                    real.append(ex - entry); pos = 0; done = True
            else:
                if sh[k] >= stop:
                    ex = so[k] if so[k] > stop else stop
                    real.append(entry - ex); pos = 0; done = True
            k += 1
        if pos != 0:
            real.append((sc[-1] - entry) if pos > 0 else (entry - sc[-1]))
    return np.array(real, float), np.array(ejects, float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=0, help="0 = full master history")
    a = ap.parse_args()

    master = find_master("NQ", "5m", "rth")
    if master is None:
        print("no NQ 5m rth master found"); return 1
    date_from = None
    if a.years > 0:
        import pandas as pd
        date_from = (pd.Timestamp.today() - pd.Timedelta(days=int(a.years * 365))).strftime("%Y-%m-%d")
    arr = load_master_arrays(master, date_from=date_from, date_to=None)
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    v, did = arr.get("volume"), arr["day_id"]
    idx = arr["index"]
    print(f"master: {master.get('name', master)}")
    print(f"window: {idx[0].date()} -> {idx[-1].date()}   bars={len(c):,}  sessions={len(set(did)):,}")

    eng = run_backtest("ORB_3_0.py", arrays=arr, params=ORB_125,
                       cost_pts=COST_PTS, return_trades=True)
    real, ejects = port_sim(o, h, l, c, v, did, ORB_125)

    eng_net = eng["total_pnl"] * MULT
    eng_n = eng["num_trades"]
    real_net = float((real - COST_PTS).sum()) * MULT if len(real) else 0.0
    ej_net = float((ejects - COST_PTS).sum()) * MULT if len(ejects) else 0.0
    port_net = real_net + ej_net
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)

    print()
    print("                        trades        net $        $/yr")
    print(f"  ENGINE (look-ahead) {eng_n:8,}  {eng_net:11,.0f}  {eng_net/years:10,.0f}")
    print(f"  PORT  real trades   {len(real):8,}  {real_net:11,.0f}  {real_net/years:10,.0f}")
    print(f"  PORT  ejections     {len(ejects):8,}  {ej_net:11,.0f}  {ej_net/years:10,.0f}")
    print(f"  PORT  total         {len(real)+len(ejects):8,}  {port_net:11,.0f}  {port_net/years:10,.0f}")
    print()
    drag = port_net - eng_net
    print(f"  LIVE DRAG vs engine: {drag:,.0f}  ({drag/years:,.0f}/yr, "
          f"{100*drag/abs(eng_net) if eng_net else 0:.1f}% of engine net)")
    if len(ejects):
        pts = ejects
        print(f"  ejections: {len(ejects):,} over {years:.1f}y = {len(ejects)/years:.0f}/yr "
              f"({100.0*len(ejects)/max(len(ejects)+len(real),1):.0f}% of all fills)")
        print(f"  per ejection: mean {pts.mean()*MULT:,.0f}$  median {np.median(pts)*MULT:,.0f}$  "
              f"worst {pts.min()*MULT:,.0f}$  best {pts.max()*MULT:,.0f}$")
        print(f"  ejection win rate: {100.0*(pts > 0).mean():.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

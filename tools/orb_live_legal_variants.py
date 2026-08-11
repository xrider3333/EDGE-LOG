"""Which ORB variants can actually be TRADED live, and what do they earn?

Context: ORB #125 filters breakouts on the breakout bar's FINISHED volume while entering
on a resting stop INTRABAR. Those two things cannot both be true in real time -- you can
not know a bar's volume until it closes, by which point the stop has already filled.
tools/orb_live_emulation_cost.py prices the naive workaround (enter, then eject if thin)
and it is fatal: ~97% of fills become ejections, each paying a round turn.

So compare the rules that ARE live-legal:

  A #125 as validated   stop entry intrabar + volume filter   NOT LIVE-LEGAL (look-ahead)
  B vol filter OFF      stop entry intrabar, no filter        live-legal
  C close-confirmed     decide AT the bar close, where that   live-legal, zero gap
                        bar's volume is legitimately known

C is the interesting one: moving the decision to the bar close makes the volume filter
honest, because the bar is over. Entry price becomes that close instead of the level.

Run:  python3.13.exe tools/orb_live_legal_variants.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402

MULT = 20.0
COST_PTS = 0.533
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
            breakout_buf=0.0, target_R=0.0, flat_eod=True)

VARIANTS = [
    ("A  #125 as validated      (NOT live-legal)", dict(BASE)),
    ("B  volume filter OFF      (live-legal)", dict(BASE, vol_filter=0.0)),
    ("C  close-confirmed + vol  (live-legal)", dict(BASE, close_confirm=True)),
    ("D  close-confirmed, no vol(live-legal)", dict(BASE, close_confirm=True, vol_filter=0.0)),
]


def main():
    master = find_master("NQ", "5m", "rth")
    arr = load_master_arrays(master, date_from=None, date_to=None)
    idx = arr["index"]
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    print(f"master: {master.get('name', master)}")
    print(f"window: {idx[0].date()} -> {idx[-1].date()}  ({years:.1f}y, {len(arr['close']):,} bars)")
    print()
    print(f"{'variant':<44}{'trades':>8}{'net $':>12}{'$/yr':>10}{'PF':>7}{'maxDD $':>11}{'MAR':>7}")
    print("-" * 99)
    for label, p in VARIANTS:
        r = run_backtest("ORB_3_0.py", arrays=arr, params=p, cost_pts=COST_PTS)
        if not r:
            print(f"{label:<44}{'no trades':>8}")
            continue
        net = r["total_pnl"] * MULT
        dd = abs(r["max_drawdown"]) * MULT
        mar = (net / years) / dd if dd else 0.0
        print(f"{label:<44}{r['num_trades']:>8,}{net:>12,.0f}{net/years:>10,.0f}"
              f"{r['profit_factor']:>7.2f}{dd:>11,.0f}{mar:>7.2f}")
    print()
    print("A is the crowned config but cannot be executed as written.")
    print("C keeps the volume filter and makes it honest by deciding at the bar close.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

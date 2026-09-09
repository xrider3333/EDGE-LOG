"""WAS THE EDGE REALLY WEAKER BEFORE 2018, OR DOES THE DOLLAR TAPE JUST MAKE IT LOOK SO?

tools/r3_leader_stress.py found that all three ENGU-Q configs read about twice as good after
mid-2018 as before (leader PF 1.252 -> 1.568, MAR 0.74 -> 1.89). I flagged there that the
~10x DOLLAR gap is mostly the index level (Nasdaq ~2,000 in 2011 vs ~20,000 in 2025) and
said PF and MAR are scale-free. PF is only PARTLY scale-free: it is a ratio of dollar sums,
so inside a half the later, larger-dollar trades dominate both sums. This test removes the
price level properly and asks the question again.

THE NORMALISATION: every trade's P&L is divided by its own entry price, giving a percent
move per trade. That is scale-free by construction - a 1% winner in 2011 counts exactly as
much as a 1% winner in 2025 - so any remaining gap between the halves is a real change in
the edge, not in the tape's price level.

REPORTED, per half and per three-year block, for all three configs:
  * trades, win rate, and mean percent P&L per trade (the expectancy that matters here)
  * profit factor computed on PERCENT trades, not dollars
  * the same in dollars beside it, so the size of the illusion is visible

No pass/fail bar: this is a diagnosis of a result already in hand, and inventing a
threshold after seeing the numbers is the hindsight this project keeps catching itself on.

RESULT, 2026-09-09 - AND IT WALKS BACK PART OF THE STRESS DRIVER'S CLAIM.
Mean entry price was 3,870 in the first half against 14,408 in the second, so the dollar tape
really was doing most of the work: the ~10x dollar gap between halves shrinks, once every
trade is measured as a percent of its own entry price, to

    leader   per-trade 0.0492% -> 0.1292% = 2.63x   PF% 1.262 -> 1.562 = 1.24x
    R3       per-trade 0.0607% -> 0.1303% = 2.15x   PF% 1.294 -> 1.528 = 1.18x
    R2 live  per-trade 0.0998% -> 0.2017% = 2.02x   PF% 1.456 -> 1.768 = 1.21x

tools/r3_leader_stress.py said the scale-free reads "still say the edge was about twice as
good after 2018". That is right for per-trade expectancy and WRONG for profit factor, where
the honest number is about a quarter better, not twice. The regime caveat is real but milder
than that driver's docstring implies; read this file's numbers, not that sentence.

NO DEAD STRETCH. Every three-year block is profitable for all three configs; the weakest is
2013-2015 (PF% 1.16-1.30). What actually changed after 2018 is the WIN RATE - leader 29.8% ->
35.3%, and the leader gains the most of the three. That is also why the leader wins on MAR
while the uncapped R2 still wins on profit factor: the leader takes ~50% more trades at a
smaller edge each.
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
MULT, COST = 20.0, 0.533
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"
SPLIT = pd.Timestamp("2018-06-30")

BASE = dict(buf_atr=0.3, tl_len=206, limit_atr=0.55, atr_len=52, act_R=1.5,
            ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
            min_brk=1.6, vol_mult=1.1, er_th=0.0)
CASES = [
    ("LEADER cap 9660 trail 2.0 be 1.5",
     dict(BASE, max_hold_bars=9660, trail_frac=2.0, breakeven_R=1.5)),
    ("R3     cap 8280 trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=8280, trail_frac=2.5, breakeven_R=2.0)),
    ("R2live no cap   trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=0, trail_frac=2.5, breakeven_R=2.0)),
]


def block(pct, usd):
    if len(pct) < 20:
        return None
    w = pct[pct > 0]
    l = pct[pct < 0]
    pf_pct = float(w.sum() / max(-l.sum(), 1e-12))
    wu, lu = usd[usd > 0], usd[usd < 0]
    return dict(n=int(len(pct)), win=float((pct > 0).mean() * 100),
                mean_pct=float(pct.mean() * 100), pf_pct=pf_pct,
                pf_usd=float(wu.sum() / max(-lu.sum(), 1e-9)),
                net_usd=float(usd.sum()))


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    out = {}

    for label, p in CASES:
        r = run_backtest(STRAT, arrays=arr, params=dict(p), cost_pts=COST,
                         return_trades=True)
        tr = (r or {}).get("trades") or []
        ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
        usd = np.array([t[2] * MULT for t in tr], float)
        entry_px = np.array([float(t[4]) for t in tr], float)
        pct = np.array([t[2] for t in tr], float) / entry_px      # percent move per trade

        print("=" * 104)
        print("%s   n=%d   mean entry price %.0f (first half) / %.0f (second half)"
              % (label, len(tr), entry_px[ent < SPLIT].mean(), entry_px[ent >= SPLIT].mean()))
        print("  %-14s %6s %7s %11s %9s %9s %12s"
              % ("stretch", "n", "win %", "mean % / tr", "PF %", "PF $", "net $"))
        rows = {}
        for name, m in (("1st half", ent < SPLIT), ("2nd half", ent >= SPLIT)):
            b = block(pct[m], usd[m])
            rows[name] = b
            print("  %-14s %6d %6.1f%% %10.4f%% %9.3f %9.3f %12s"
                  % (name, b["n"], b["win"], b["mean_pct"], b["pf_pct"], b["pf_usd"],
                     format(b["net_usd"], ",.0f")))
        print("  %-14s %6s %7s %10.2fx %8.2fx %8.2fx"
              % ("2nd / 1st", "", "",
                 rows["2nd half"]["mean_pct"] / rows["1st half"]["mean_pct"],
                 rows["2nd half"]["pf_pct"] / rows["1st half"]["pf_pct"],
                 rows["2nd half"]["pf_usd"] / rows["1st half"]["pf_usd"]))

        print("  three-year blocks (percent-normalised, so directly comparable):")
        yrs = ent.year.values
        for lo in range(2010, 2027, 3):
            m = (yrs >= lo) & (yrs < lo + 3)
            b = block(pct[m], usd[m])
            if b is None:
                continue
            rows["%d-%d" % (lo, min(lo + 2, 2026))] = b
            print("    %d-%d  n=%4d  win %4.1f%%  mean %+.4f%% / trade  PF%% %.3f  net $%s"
                  % (lo, min(lo + 2, 2026), b["n"], b["win"], b["mean_pct"], b["pf_pct"],
                     format(b["net_usd"], ",.0f")))
        out[label] = rows

    json.dump(out, io.open(os.path.join(SCR, "_scalefree.json"), "w"), indent=1,
              default=float)
    print("\nSAVED")


if __name__ == "__main__":
    main()

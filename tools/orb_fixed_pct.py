"""ORB — what the champion looks like sized as a FIXED PERCENT of a compounding account.

Every ORB number in the docs is "1 contract, forever" — the honest, scale-free way to measure an
edge. Published ORB results are almost always "% of equity, risked and compounded". Those are not
the same measurement, and the gap between them is arithmetic, not edge. This prints both, plus the
middle case, so the difference can be attributed:

    flat            1 contract on every trade                      (what ORB.md reports today)
    risk-parity     constant DOLLAR risk per trade, NOT compounded  (isolates the sizing rule)
    fixed-%         constant PERCENT of running equity, compounded  (adds compounding)

Sizing rule for the latter two: contracts = risk_budget / (initial_stop_distance x $20). That is
the standard "risk X% per trade" rule — already validated on ORB as risk-parity (ORB.md §4.7).

Realism:
  • size rounds DOWN to 0.1 contracts (MNQ micros are 1/10 of NQ) with a 0.1 floor.
  • size is capped by day-trade margin at MARGIN $/contract (ORB is flat at the close).
  • fees scale with size ($5.66 + 0.25pt slippage per contract, same as everywhere else).
  • drawdown is measured on the equity PATH in percent, which is the number that matters once
    you compound — a 30% drawdown at 2x size is a 60% drawdown, and 100% is the end of the account.

Usage:  python tools/orb_fixed_pct.py [start_equity]
"""
import sys, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.sizing import trade_features

MULT = 20.0
FEE = 5.66 / MULT + 0.25
MARGIN = 5000.0           # conservative day-trade margin per NQ contract
LOT = 0.1                 # micros
STRAT = "ORB_3_0_ENS.py"
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
           breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12, flat_eod=True)
PCTS = (0.25, 0.5, 1.0, 2.0)
START = float(sys.argv[1]) if len(sys.argv) > 1 else 100_000.0


def _dd_pct(eq):
    """Deepest peak-to-trough fall of the equity path, in percent of the peak."""
    peak = np.maximum.accumulate(eq)
    return float((1.0 - eq / peak).max() * 100.0)


def _cagr(eq0, eq1, years):
    if eq1 <= 0 or years <= 0:
        return float("nan")
    return ((eq1 / eq0) ** (1.0 / years) - 1.0) * 100.0


def _size(budget_usd, risk_pts):
    """Contracts that put `budget_usd` at risk given the trade's initial stop distance."""
    raw = budget_usd / max(risk_pts * MULT, 1e-9)
    return max(LOT, np.floor(raw / LOT) * LOT)


def run_path(pnl, risk, *, mode, pct, start):
    """Walk the trade list, sizing each trade, returning the equity path (and whether it blew up)."""
    eq = start
    out = np.empty(len(pnl)); sizes = np.empty(len(pnl))
    blown = False
    for i in range(len(pnl)):
        if mode == "flat":
            s = 1.0
        else:
            budget = (eq if mode == "fixed" else start) * pct / 100.0
            s = _size(budget, risk[i])
            s = min(s, max(LOT, np.floor((eq / MARGIN) / LOT) * LOT))
        sizes[i] = s
        eq += s * (pnl[i] - FEE) * MULT
        if eq <= 0:
            blown = True
            eq = 0.0
            out[i:] = 0.0; sizes[i:] = 0.0
            break
        out[i] = eq
    return out, sizes, blown


def main():
    m = find_master("NQ", "5m", "rth")
    arrays = load_master_arrays(m)
    res = run_backtest(STRAT, instrument="NQ", timeframe="5m", session="rth",
                       params=CFG, cost_pts=0.0, return_trades=True)
    T = sorted(res["trades"], key=lambda t: int(t[0]))
    idx = np.asarray(arrays["index"]); nb = len(idx)
    ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])
    pnl, risk, _e, _s = trade_features(T, arrays, CFG["stop_frac"], CFG["or_bars"])
    years = (ts[-1] - ts[0]) / np.timedelta64(365, "D")

    print(f"=== ORB champion sized as a fixed % of equity — NQ 5m RTH ({STRAT}) ===")
    print(f"{len(T)} trades  ·  {str(ts[0])[:10]} → {str(ts[-1])[:10]}  ({years:.1f} years)  ·  "
          f"start ${START:,.0f}  ·  margin ${MARGIN:,.0f}/contract  ·  micro lots {LOT}")

    hdr = (f"\n{'sizing':<22}{'end equity':>14}{'total %':>11}{'CAGR %':>9}"
           f"{'maxDD %':>9}{'MAR':>7}{'avg sz':>8}{'max sz':>8}")
    print(hdr); print("-" * len(hdr))

    eq, sz, _ = run_path(pnl, risk, mode="flat", pct=0, start=START)
    base_dd = _dd_pct(eq)
    print(f"{'flat 1 contract':<22}{eq[-1]:>14,.0f}{(eq[-1]/START-1)*100:>11,.0f}"
          f"{_cagr(START, eq[-1], years):>9.1f}{base_dd:>9.1f}"
          f"{_cagr(START, eq[-1], years)/max(base_dd,1e-9):>7.2f}{1.0:>8.1f}{1.0:>8.1f}")

    for mode, lab in (("static", "risk-parity"), ("fixed", "fixed-%")):
        for p in PCTS:
            eq, sz, blown = run_path(pnl, risk, mode=mode, pct=p, start=START)
            if blown:
                print(f"{lab + f' {p}%':<22}{'ACCOUNT BLEW UP':>14}")
                continue
            d = _dd_pct(eq); c = _cagr(START, eq[-1], years)
            print(f"{lab + f' {p}%':<22}{eq[-1]:>14,.0f}{(eq[-1]/START-1)*100:>11,.0f}"
                  f"{c:>9.1f}{d:>9.1f}{c/max(d,1e-9):>7.2f}{sz.mean():>8.1f}{sz.max():>8.1f}")

    print("\nSame trades in every row. Only the size rule changes.")
    print("MAR here = CAGR ÷ max drawdown %, the compounding-world version of the usual net ÷ $DD.")


if __name__ == "__main__":
    main()

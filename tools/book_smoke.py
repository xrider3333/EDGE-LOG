"""Smoke test for the BOOK job type — runs the baseline book through augur_engine.run_book
and checks it against the offline t5_runboard.py figures it must reproduce.

Baseline book (the owner's current deployed pair, RUNBOARD row 1):
    ORB 3.1 @ stop 0.75 / trail 5   +   ENGU-Q 1m @ the certified NQ_DEPLOY_PARAMS_149
    window 2010-06-07 -> 2026-06-30, NQ, 1 contract each, 0.533 pts/round-trip
Offline reference: FULL net ~$838,161 · PF ~1.477 · DD ~$60,098 · 6,112 trades.

Run:  python tools/book_smoke.py
"""
import sys
import pathlib
import importlib.util

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from augur_engine import run_book   # noqa: E402

_s = importlib.util.spec_from_file_location("enguq", REPO / "augur_strategies" / "ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)
ENG_149 = _m.NQ_DEPLOY_PARAMS_149

ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, partial_exit_R=0.0, trail_bars=5, flat_eod=True)

LEGS = [
    {"strategy": "ORB_3_1.py", "params": ORB_125, "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "cost_pts": 0.533, "mult": 20},
    {"strategy": "ENGUQ_1M_1_0.py", "params": ENG_149, "instrument": "NQ",
     "timeframe": "1m", "session": "rth", "cost_pts": 0.533, "mult": 20},
]

REF = {"net": 838161, "pf": 1.477, "dd": 60098, "n": 6112}


def main():
    r = run_book(LEGS, date_from="2010-06-07", date_to="2026-06-30",
                 lockbox_months=12, slices=8,
                 progress_cb=lambda d, t: None)
    b = r["book"]
    w, lb = b["whole"], b["lockbox"]

    print("LEGS")
    for l in b["legs"]:
        print(f"  {l['strategy']:<22} {l['instrument']} {l['timeframe']}  "
              f"{l['trades']:>5} trades  ${l['net']:>12,.0f}  master={l['master']}")

    print("\nBOOK (whole window, both legs pooled)")
    print(f"  net        ${w['total_pnl']:>12,.0f}   (offline ref ${REF['net']:,})")
    print(f"  PF          {w['profit_factor']:>12.3f}   (offline ref {REF['pf']})")
    print(f"  max DD     ${w['max_drawdown']:>12,.0f}   (offline ref ${REF['dd']:,})")
    print(f"  trades      {w['num_trades']:>12,}   (offline ref {REF['n']:,})")
    print(f"  win rate    {w['win_rate']:>12.1f}%")
    print(f"  8-slice     {b['slices_held']}/{b['slices_n']} profitable")

    if lb:
        print(f"\nLOCKBOX (from {b['lockbox_from']})")
        print(f"  net        ${lb['total_pnl']:>12,.0f}   PF {lb['profit_factor']:.2f}   "
              f"{lb['num_trades']} trades   DD ${lb['max_drawdown']:,.0f}")
    print(f"\nverdict {r['validate']['verdict']} · curve {len(r['equity'])} pts · "
          f"lockbox door at index {r['validate']['lb_idx']}")

    dn = abs(w["total_pnl"] - REF["net"]) / REF["net"]
    dt = abs(w["num_trades"] - REF["n"]) / REF["n"]
    ok = dn < 0.02 and dt < 0.02
    print(f"\n{'PASS' if ok else 'FAIL'} — net off by {dn*100:.2f}%, trades off by {dt*100:.2f}% "
          f"(tolerance 2%)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Calibrate (and sanity-check) a PAPER hybrid leg's frozen `size_norm` divisor.

WHY. api/paper_gate.py's hybrid mode sizes each surviving trade by its gate score. The
backtest that crowned the gate normalised those sizes by the mean weight over its
PRE-LOCKBOX survivors, so the row carried the same average size as the ungated baseline.
A forward test cannot recompute that mean without averaging over its own future, so the
divisor is frozen: measured once here, against the source run's own window and lockbox
boundary, then pinned in the leg config in api/paper.py.

This is the script that produced those pinned numbers. Re-run it if a leg's base params,
gate model, or cut-off ever change -- the divisor is specific to all three.

Usage:
  python3.13.exe tools/paper_gate_calibrate.py --leg ORB_H
  python3.13.exe tools/paper_gate_calibrate.py --leg NOISE_H
  python3.13.exe tools/paper_gate_calibrate.py --all
"""
import argparse
import json
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np                                        # noqa: E402
import pandas as pd                                       # noqa: E402

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                    # noqa: E402
from api import paper_gate                                      # noqa: E402


def calibrate(name, spec, verbose=True):
    """One leg. `spec` mirrors an api/paper.py leg dict plus a `calibration` block."""
    cal = spec["calibration"]
    t0 = time.time()
    master = find_master(spec["instrument"], spec["timeframe"], spec.get("session", "rth"))
    if master is None:
        return {"leg": name, "error": "no master"}
    arrays = load_master_arrays(master, date_from=cal["date_from"], date_to=cal["date_to"])
    idx = arrays["index"]
    if verbose:
        print(f"[{name}] master bars {len(idx)}  {idx[0]} .. {idx[-1]}")

    res = run_backtest(spec["strategy"], arrays=arrays, params=spec["params"],
                       cost_pts=spec["cost_pts"], return_trades=True)
    trades = (res or {}).get("trades") or []
    if verbose:
        print(f"[{name}] base backtest: {len(trades)} trades, "
              f"pnl {res.get('total_pnl'):,.1f} pts, pf {res.get('profit_factor'):.3f} "
              f"({time.time() - t0:.1f}s)")
    if not trades:
        return {"leg": name, "error": "base backtest produced no trades"}

    # The bar index the source run's lockbox begins at — the divisor must be measured on
    # PRE-lockbox trades only, exactly as gate_validate measured its own.
    lb = pd.Timestamp(cal["lockbox_from"])
    if lb.tzinfo is None and getattr(idx, "tz", None) is not None:
        lb = lb.tz_localize(idx.tz)
    lb_idx = int(idx.searchsorted(lb))

    t1 = time.time()
    norm, detail = paper_gate.calibrate_size_norm(arrays, trades, spec["gate"],
                                                  upto_index=lb_idx)
    out = {"leg": name, "model": spec["gate"]["model"], "mode": spec["gate"]["mode"],
           "threshold": spec["gate"]["threshold"], "source_run": spec["gate"].get("source_run"),
           "lockbox_from": cal["lockbox_from"], "lockbox_bar_index": lb_idx,
           "size_norm": (round(norm, 6) if norm else None),
           "gate_seconds": round(time.time() - t1, 1),
           "total_seconds": round(time.time() - t0, 1), **detail}
    if verbose:
        print(f"[{name}] " + json.dumps(out, indent=2, default=str))
    return out


# ── the legs this repo actually pins ──────────────────────────────────────────────
# Params + gate settings are duplicated here ON PURPOSE rather than imported from
# api/paper.py: this script is what DERIVES the number that goes into that file, so
# importing it would make the calibration depend on the value it is meant to produce.
_NQ_COST = 0.533

SPECS = {
    # Run #234 (ORB-42), the crown since 2026-08-21. Its crowned gate is rf@0.45 (same rule
    # as #230) and the rf hybrid HELD the lockbox (PF 1.569 vs 1.453 ungated).
    "ORB_H": {
        "strategy": "ORB_3_6_C2.py", "instrument": "NQ", "timeframe": "5m",
        "session": "rth", "cost_pts": _NQ_COST,
        "params": dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0,
                       atr_filter=0.7, vpace_filter=0.7, close_confirm=True,
                       breakout_buf=0.25, trail_bars=0, target_R=5.5,
                       partial_exit_R=0.0, be_after_R=1.0, flat_eod=True,
                       skip_holidays=True),
        "gate": {"mode": "hybrid", "model": "rf", "threshold": 0.45, "source_run": 234},
        "calibration": {"date_from": "2010-06-07", "date_to": "2026-08-13",
                        "lockbox_from": "2025-08-13"},
    },
    # Run #225 (NOISE-6). NOTE the cut-off is the run's CROWNED cut-off (logistic@0.55)
    # but the model is `tree` — see api/paper.py's NOISE_H block for why that pairing is
    # a forward TEST and not a crown.
    "NOISE_H": {
        "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
        "session": "rth", "cost_pts": _NQ_COST,
        "params": dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                       exit_mode="vwap", side="Both", window="all_day",
                       flat_eod=True, skip_holidays=False,
                       stop_mode="bandwidth", stop_k=1.75),
        "gate": {"mode": "hybrid", "model": "tree", "threshold": 0.55, "source_run": 225},
        "calibration": {"date_from": "2010-06-07", "date_to": "2026-08-12",
                        "lockbox_from": "2025-02-11"},
    },
    # Owner's pick (2026-08-16), and better grounded than NOISE_H -- see api/paper.py.
    # Same base config and floor, rf instead of tree.
    "NOISE_H_RF": {
        "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
        "session": "rth", "cost_pts": _NQ_COST,
        "params": dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                       exit_mode="vwap", side="Both", window="all_day",
                       flat_eod=True, skip_holidays=False,
                       stop_mode="bandwidth", stop_k=1.75),
        "gate": {"mode": "hybrid", "model": "rf", "threshold": 0.55, "source_run": 231},
        "calibration": {"date_from": "2010-06-07", "date_to": "2026-08-12",
                        "lockbox_from": "2025-02-11"},
    },
    # Run #265 (ENGU-Q-28), owner-adopted to paper 2026-08-21. Crowned gate logistic@0.55.
    # The overlay did NOT beat ungated on the held-out year, so this leg is a forward TEST;
    # see api/paper.py ENGUQ_ER_GATE. Calibrated 2026-08-21: size_norm 1.697185,
    # recycle_factor 1.877809 (712 of 1337 trades kept).
    "ENGUQ_ER_H": {
        "strategy": "ENGUQ_1M_ETH_ER25_1_0.py", "instrument": "NQ", "timeframe": "1m",
        "session": "eth", "cost_pts": _NQ_COST,
        "params": dict(er_len=60, er_th=0.25, limit_atr=0.0, tl_len=170, vol_mult=0.8,
                       stop_mult=1.0, act_R=2.5, trail_frac=2.5, buf_atr=0.9, min_brk=1.3,
                       ema_len=1380, atr_len=106, regime_len=0, breakeven_R=1.5),
        "gate": {"mode": "hybrid", "model": "logistic", "threshold": 0.55, "source_run": 265},
        "calibration": {"date_from": "2010-06-07", "date_to": "2026-06-30",
                        "lockbox_from": "2025-06-30"},
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", choices=sorted(SPECS))
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    names = sorted(SPECS) if (a.all or not a.leg) else [a.leg]
    results = [calibrate(n, SPECS[n]) for n in names]
    print("\n=== PIN THESE IN api/paper.py ===")
    for r in results:
        print(f"  {r['leg']}: size_norm = {r.get('size_norm')}   "
              f"(survivors in span {r.get('n_survivors_in_span')}, "
              f"max size after norm {r.get('max_size_after_norm')}, "
              f"gate {r.get('gate_seconds')}s)")
    return 0 if all(r.get("size_norm") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
WARM-START PARITY CHECK (2026-09-20, RESEARCH.md item 7)

The engine now warms every SCORED out-of-sample stretch: a walk-forward fold's test leg,
Stage A's 25% split and the lockbox run from `warm_days` trading sessions before the
stretch opens, keeping only the trades that ENTER inside it (augur_engine/auto.py,
make_slice_evaluator's `warm=True` path).

tools/wf_coldstart_audit.py measured the same idea by hand in 2026-09-15, warming from
bar 0 and filtering `t[0] >= te_s`. This script puts the two side by side per fold, so
the engine path is checked against an INDEPENDENT implementation rather than against
itself, and shows what the 300-session cap costs versus warming over all history.

Expected reading:
  • an intraday leg (the opening-range control) barely moves at all, cold or warm;
  • a long-trend daily leg recovers most of its fold trades;
  • engine-warm equals audit-warm wherever 300 sessions covers the look-back, and comes
    in slightly under it where the strategy wants more history than that.

  python tools/warm_start_parity.py [--legs orb,noise,qqq_rsi2,...] [--folds 8]
"""
import argparse
import datetime as dt
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays           # noqa: E402
from augur_engine.auto import make_slice_evaluator, WARM_DAYS           # noqa: E402

NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1,
               "daytype_mode": "skip_bot_short", "band_mult_long": 0.75,
               "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}

# Same rows as tools/wf_coldstart_audit.py, so the two are directly comparable.
LEGS = {
    "qqq_rsi2": ("QQQ RSI2 (trend 250)", 358, "ETFDIP_RSI2_1_0.py", "QQQ", "1d", "rth",
                 "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
                 {"rsi_thr_short": 95, "rsi_len": 2, "rsi_thr": 30, "allow_shorts": False,
                  "trend_len": 250, "rsi_exit": 7, "cost_bps": 2.0, "notional": 100000}),
    "qqq_dbl": ("QQQ N-day low (trend 225)", 356, "ETFDIP_DBL7_1_0.py", "QQQ", "1d", "rth",
                "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
                {"dbl_n": 7, "trend_len": 225, "cost_bps": 2.0, "notional": 100000}),
    "gld_dbl": ("GLD N-day low (trend 125)", 354, "ETFDIP_DBL7_1_0.py", "GLD", "1d", "rth",
                "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
                {"dbl_n": 6, "trend_len": 125, "cost_bps": 2.0, "notional": 100000}),
    "nqdip10": ("NQDIP 1.0 (trend 100)", 307, "NQDIP_1_0.py", "NQ", "5m", "rth",
                "db_noadj_rth", 0.0, "2010-06-07", "2026-08-24", 12,
                {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5,
                 "cost_pts_rt": 0.783, "trend_len": 100, "rsi_exit": 9, "cost_bps": 2.0,
                 "notional": 100000, "use_pb": True, "cap_hold": 5, "use_rsi": True,
                 "cap_q": 0.3, "rsi_thr": 30, "dbl_n": 10, "use_cap": True, "use_dbl": True}),
    "orb": ("CONTROL ORB crown #234", 234, "ORB_3_6_C2.py", "NQ", "5m", "rth",
            "db_noadj_rth", 0.533, "2010-06-07", "2026-08-13", 12, "defaults"),
    "noise": ("CONTROL NOISE crown #304", 304, "NOISE_1_1_NBHD.py", "NQ", "5m", "rth",
              "db_noadj_rth", 0.533, "2010-06-07", "2026-08-12", 12, NOISE_CROWN),
}


def defaults(fn):
    import importlib.util as ilu
    sp = ilu.spec_from_file_location("m", "augur_strategies/" + fn)
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def check(key, n_folds=8, warm_days=WARM_DAYS):
    label, run, fn, inst, tf, sess, src, cost, d0, d1, lbm, params = LEGS[key]
    if params == "defaults":
        params = defaults(fn)
    hi = dt.date.fromisoformat(d1)
    opt_to = (hi - dt.timedelta(days=int(lbm * 30.44)) - dt.timedelta(days=1)).isoformat()
    master = find_master(inst, tf, sess, src) or find_master(inst, tf, None, src)
    if master is None:
        print(f"{label}: no master for {inst} {tf} {sess} {src} — skipped")
        return None
    A = load_master_arrays(master, date_from=d0, date_to=opt_to)
    n = len(A["close"])
    path = "augur_strategies/" + fn
    ev_cold = make_slice_evaluator(path, A, cost)
    ev_warm = make_slice_evaluator(path, A, cost, warm_days=warm_days)
    init = int(n * 0.40)
    tsize = max(1, (n - init) // n_folds)
    rows = []
    for f in range(n_folds):
        te_s = init + f * tsize
        te_e = n if f == n_folds - 1 else te_s + tsize
        cold = ev_cold(te_s, te_e, params, keep_trades=True) or {}
        audit = ev_cold(0, te_e, params, keep_trades=True) or {}       # the 09-15 method
        eng = ev_warm(te_s, te_e, params, keep_trades=True, warm=True) or {}
        ct = cold.get("trades") or []
        at = [t for t in (audit.get("trades") or []) if int(t[0]) >= te_s]
        et = eng.get("trades") or []
        rows.append(dict(fold=f + 1,
                         cold_n=len(ct), audit_n=len(at), engine_n=len(et),
                         cold_pnl=float(sum(t[2] for t in ct)),
                         audit_pnl=float(sum(t[2] for t in at)),
                         engine_pnl=float(eng.get("total_pnl", 0.0) or 0.0)))
    R = pd.DataFrame(rows)
    cn, an, en = int(R.cold_n.sum()), int(R.audit_n.sum()), int(R.engine_n.sum())
    cp, ap, ep = R.cold_pnl.sum(), R.audit_pnl.sum(), R.engine_pnl.sum()
    print(f"\n{label}  (run #{run}; optimize window to {opt_to}; {n:,} bars, "
          f"{n_folds} folds, warm {warm_days} sessions)")
    print(R.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
    print(f"  cold {cn} trades / {cp:,.0f}")
    print(f"  audit-warm (all history) {an} trades / {ap:,.0f}")
    print(f"  ENGINE-warm ({warm_days} sessions) {en} trades / {ep:,.0f}")
    if an:
        print(f"  trades the cold start lost: {100 * (1 - cn / an):.0f}%   "
              f"engine vs audit: {100 * (en / an - 1):+.1f}% trades, "
              f"{ep - ap:+,.0f} pnl")
    return dict(leg=key, label=label, run=run, cold_trades=cn, audit_trades=an,
                engine_trades=en, cold_pnl=round(cp), audit_pnl=round(ap),
                engine_pnl=round(ep))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", default="qqq_rsi2,gld_dbl,orb,noise")
    ap.add_argument("--folds", type=int, default=8)
    ap.add_argument("--warm-days", type=int, default=WARM_DAYS)
    a = ap.parse_args()
    out = [r for r in (check(k.strip(), a.folds, a.warm_days)
                       for k in a.legs.split(",") if k.strip() in LEGS) if r]
    if out:
        print("\n\nSUMMARY\n" + pd.DataFrame(out).to_string(index=False))

"""
WALK-FORWARD COLD-START AUDIT (2026-09-15)

FINDING THAT PROMPTED THIS: every walk-forward TEST fold in Auto-Validate is evaluated on a cold slice -
make_slice_evaluator passes O[a:b], H[a:b], ... so the strategy sees only that fold's bars and must warm
up its indicators inside the fold (augur_engine/auto.py, ev()). The held-back year is also a cold restart
(validate.py Stage C, date_from=lb_from). A strategy whose indicators need hundreds of bars - a 200-day
trend filter on daily bars - loses most of every test fold, so walk-forward efficiency and folds-held are
pushed down for reasons that have nothing to do with its edge.

Every daily long-trend strategy validated so far FAILED on walk-forward efficiency (0.06-0.47) while the
intraday legs sit at 2.6-4.6. This measures how much of that is the cold start.

METHOD, per run: take the run's OWN crowned config (fixed - no re-optimising, so only the warm-up
differs), rebuild the validate's exact fold grid on its optimize window (init = 40% of bars, eight equal
test folds), and for each test fold compare
    COLD = the strategy run on the fold's bars only (what the validate does), and
    WARM = the strategy run on all bars up to the fold's end, keeping only trades that ENTER inside the fold
           (causal: nothing after the fold end is visible; the history before it is only warm-up).
Controls: the opening-range crown #234 and the NOISE crown #304, whose warm-ups are short.
"""
import os, sys, datetime as dt
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.auto import make_slice_evaluator


NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}
RUNS = [
    # (label, run, file, instrument, tf, session, source, cost, date_from, date_to, lockbox_months, params)
    ("NQDIP 1.0  (trend 100)", 307, "NQDIP_1_0.py", "NQ", "5m", "rth", "db_noadj_rth", 0.0, "2010-06-07", "2026-08-24", 12,
     {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5, "cost_pts_rt": 0.783, "trend_len": 100, "rsi_exit": 9,
      "cost_bps": 2.0, "notional": 100000, "use_pb": True, "cap_hold": 5, "use_rsi": True, "cap_q": 0.3, "rsi_thr": 30,
      "dbl_n": 10, "use_cap": True, "use_dbl": True}),
    ("NQDIP 1.1  (trend 250)", 315, "NQDIP_1_1.py", "NQ", "5m", "rth", "db_noadj_rth", 0.0, "2010-06-07", "2026-08-24", 12,
     None),                                                   # params read from the run doc below
    ("QQQ N-day low (trend 225)", 356, "ETFDIP_DBL7_1_0.py", "QQQ", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"dbl_n": 7, "trend_len": 225, "cost_bps": 2.0, "notional": 100000}),
    ("QQQ RSI2 (trend 250)", 358, "ETFDIP_RSI2_1_0.py", "QQQ", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"rsi_thr_short": 95, "rsi_len": 2, "rsi_thr": 30, "allow_shorts": False, "trend_len": 250, "rsi_exit": 7,
      "cost_bps": 2.0, "notional": 100000}),
    ("QQQ pullback (trend 250)", 359, "ETFDIP_PB20_1_0.py", "QQQ", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"pb_ema": 5, "trend_len": 250, "pb_hold": 19, "cost_bps": 2.0, "notional": 100000}),
    ("IWM RSI2 (trend 100)", 357, "ETFDIP_RSI2_1_0.py", "IWM", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"rsi_thr_short": 95, "rsi_len": 2, "rsi_thr": 25, "allow_shorts": True, "trend_len": 100, "rsi_exit": 6,
      "cost_bps": 2.0, "notional": 100000}),
    ("TLT N-day low (trend 125)", 355, "ETFDIP_DBL7_1_0.py", "TLT", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"dbl_n": 5, "trend_len": 125, "cost_bps": 2.0, "notional": 100000}),
    ("GLD N-day low (trend 125)", 354, "ETFDIP_DBL7_1_0.py", "GLD", "1d", "rth", "yahoo_adj", 0.0, "2009-06-01", "2026-06-30", 12,
     {"dbl_n": 6, "trend_len": 125, "cost_bps": 2.0, "notional": 100000}),
    ("CONTROL ORB crown #234", 234, "ORB_3_6_C2.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, "2010-06-07", "2026-08-13", 12,
     "defaults"),
    ("CONTROL NOISE crown #304", 304, "NOISE_1_1_NBHD.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, "2010-06-07", "2026-08-12", 12,
     NOISE_CROWN),
]


def run_doc_params(run):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    return (u.collection("runs").document(str(run)).get().to_dict() or {}).get("best_params") or {}


def defaults(fn):
    import importlib.util as ilu
    sp = ilu.spec_from_file_location("m", "augur_strategies/" + fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


if __name__ == "__main__":
    summary = []
    for label, run, fn, inst, tf, sess, src, cost, d0, d1, lbm, params in RUNS:
        if params is None:
            params = run_doc_params(run)
        elif params == "defaults":
            params = defaults(fn)
        hi = dt.date.fromisoformat(d1)
        opt_to = (hi - dt.timedelta(days=int(lbm * 30.44)) - dt.timedelta(days=1)).isoformat()
        master = find_master(inst, tf, sess, src) or find_master(inst, tf, None, src)
        A = load_master_arrays(master, date_from=d0, date_to=opt_to)
        n = len(A["close"])
        ev = make_slice_evaluator("augur_strategies/" + fn, A, cost)
        init = int(n * 0.40); tsize = max(1, (n - init) // 8)
        rows = []
        for f in range(8):
            te_s = init + f * tsize
            te_e = n if f == 7 else te_s + tsize
            cold = ev(te_s, te_e, params, keep_trades=True) or {}
            warm_all = ev(0, te_e, params, keep_trades=True) or {}
            ct = cold.get("trades") or []
            wt = [t for t in (warm_all.get("trades") or []) if int(t[0]) >= te_s]
            # both paths: trade pnl already net of cost_pts when cost > 0 (the evaluator applies it)
            rows.append(dict(fold=f + 1, cold_n=len(ct), warm_n=len(wt),
                             cold_pnl=float(sum(t[2] for t in ct)), warm_pnl=float(sum(t[2] for t in wt))))
        R = pd.DataFrame(rows)
        cn, wn = int(R.cold_n.sum()), int(R.warm_n.sum())
        cp, wp = R.cold_pnl.sum(), R.warm_pnl.sum()
        held_c = int((R.cold_pnl > 0).sum()); held_w = int((R.warm_pnl > 0).sum())
        idx = pd.DatetimeIndex(A["index"])
        span = f"{idx[init].date()}..{idx[n-1].date()}, test fold ~{tsize} bars"
        print(f"\n{label}  (run #{run}; optimize window to {opt_to}; {span})")
        print(R.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
        print(f"  TOTAL  cold {cn} trades / {cp:,.0f}   warm {wn} trades / {wp:,.0f}   "
              f"trades lost to cold start {100*(1-cn/wn) if wn else 0:.0f}%   folds positive cold {held_c}/8 warm {held_w}/8")
        summary.append(dict(label=label, run=run, cold_trades=cn, warm_trades=wn,
                            lost_pct=round(100 * (1 - cn / wn), 1) if wn else None,
                            cold_pnl=round(cp), warm_pnl=round(wp), folds_pos_cold=held_c, folds_pos_warm=held_w))
    S = pd.DataFrame(summary)
    print("\n\nSUMMARY\n" + S.to_string(index=False))
    os.makedirs("tools/r16_results", exist_ok=True)
    S.to_csv("tools/r16_results/wf_coldstart_audit.csv", index=False)
    print("saved tools/r16_results/wf_coldstart_audit.csv")

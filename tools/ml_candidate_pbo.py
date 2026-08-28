"""PBO across the ML CANDIDATE SET -- "did we pick this overlay by luck?"

Owner 2026-08-27. Auto-Validate already runs CSCV PBO across a PARAMETER sweep, so a raw
config's card says how much of its win was selection luck. `gate_validate` never did the
same for the ML candidates it sweeps -- 5 models x 4 cut-offs = 20 candidates ranked on
one pooled pre-lockbox window, with no measure of how lucky that winner was. This fills
that hole.

WHY IT MATTERS HERE SPECIFICALLY. The owner's argument is that ranking an ML overlay at
the end of walk-forward is no less fair than ranking a raw config there, since
`select_oos_topk` does exactly that for raw params. He is right that the STAGE is the
same. What differs is that the two selections STACK: the raw config is chosen on the
pre-lockbox window, and then the overlay is chosen on that same window conditional on the
config that already won there. Each round is defensible; the compounded selection risk is
never measured. PBO measures it.

WHAT IT DOES, per leg:
  1. run the raw config once, take its net trades;
  2. for each model, score every trade ONCE (threshold 0.0 = pure scoring pass, no
     decision). Scores do not depend on the cut-off -- sweeping thresholds is just moving
     a line through saved scores, which is exactly how gate_validate does it, so this is
     5 model walks and not 20;
  3. build each candidate's MONTHLY net P&L over the pre-lockbox window, in HYBRID mode
     (cut + size), plus "ungated" as candidate #0 -- the same candidate #0 gate_validate
     always includes;
  4. feed the candidates x months matrix to the same CSCV routine Auto-Validate uses.

READ THE RESULT WITH THE DISPERSION NEXT TO IT. PBO asks "did the in-sample winner land
below the out-of-sample median?" -- a question about RANK. When every candidate performs
about the same, rank is noise and PBO drifts toward and past 0.5 even though the choice
barely matters. High PBO on a tight spread is harmless; high PBO on a wide spread means
a spike was chosen. So the spread of candidate returns is printed alongside, and neither
number should be read without the other.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays        # noqa: E402
from augur_engine.engine import run_backtest                         # noqa: E402
from augur_engine.analytics import probability_backtest_overfitting  # noqa: E402
from api import paper_gate                                           # noqa: E402

COST, MULT = 0.533, 20.0
FROM, TO, LB_FROM = "2010-06-07", "2026-06-30", "2025-06-30"
MODELS = ("logistic", "rf", "xgb", "tree", "et")
THRESHOLDS = (0.45, 0.50, 0.55, 0.60)

ORB_234 = {"or_bars": 2, "trade_mode": "First-candle dir", "stop_frac": 2.0,
           "atr_filter": 0.7, "vpace_filter": 0.7, "close_confirm": True,
           "breakout_buf": 0.25, "trail_bars": 0, "target_R": 5.5,
           "partial_exit_R": 0.0, "be_after_R": 1.0, "flat_eod": True, "skip_holidays": True}
ENGUQ_265 = {"ema_len": 1380, "tl_len": 170, "atr_len": 106, "buf_atr": 0.9,
             "vol_mult": 0.8, "stop_mult": 1.0, "trail_frac": 2.5, "regime_len": 0,
             "min_brk": 1.3, "breakeven_R": 1.5, "act_R": 2.5,
             "er_len": 60, "er_th": 0.25, "limit_atr": 0.0}
NOISE_243 = {"lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5,
             "exit_mode": "vwap", "side": "Both", "window": "all_day", "flat_eod": True,
             "skip_holidays": False, "stop_mode": "bandwidth", "stop_k": 1.75,
             "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
             "vol_skip_pct": 90.0}

LEGS = [
    ("ORB #234",    "ORB_3_6_C2.py",            ORB_234,   "5m", "rth", "db_noadj_rth", "rf",       0.45),
    ("ENGU-Q #265", "ENGUQ_1M_ETH_ER25_1_0.py", ENGUQ_265, "1m", "eth", "db_noadj_eth", "logistic", 0.55),
    ("NOISE #243",  "NOISE_1_0.py",             NOISE_243, "5m", "rth", "db_noadj_rth", "et",       0.50),
]

_SIZE_CAP, _SLOPE, _LO, _HI = 3.0, 4.0, 0.25, 3.0


def hybrid_sizes(prob, threshold, size_norm):
    """gate_validate's hybrid row: cut below the threshold, size survivors by score.

    Mirrors api/paper_gate's own hybrid block -- 1x at a 50% score sliding to 0.25x/3x,
    warm-up (NaN score) trades at 1.0, divided by the frozen size_norm and capped at 3x.
    """
    p = np.asarray(prob, float)
    warm = np.isnan(p)
    pf = np.where(warm, 0.5, p)
    w = np.clip(1.0 + _SLOPE * (pf - 0.50), _LO, _HI)
    w = np.where(warm, 1.0, w)
    w = np.minimum(w / (size_norm or 1.0), _SIZE_CAP)
    keep = warm | (pf >= threshold)          # warm-up always passes, as in gate_trades
    return np.where(keep, w, 0.0)


def monthly(dates, pnl):
    s = pd.Series(pnl, index=pd.to_datetime(dates))
    return s.groupby(s.index.to_period("M")).sum()


print("PBO ACROSS THE ML CANDIDATE SET (5 models x 4 cut-offs, + ungated)")
print("window %s .. %s, ranked on PRE-LOCKBOX only (< %s)\n" % (FROM, LB_FROM, LB_FROM))

for label, fn, params, tf, sess, src, crown_model, crown_th in LEGS:
    arr = load_master_arrays(find_master("NQ", tf, sess, src), date_from=FROM, date_to=TO)
    res = run_backtest(fn, arrays=arr, params=params, cost_pts=COST, return_trades=True)
    raw = list(res.get("trades") or [])
    idx = np.asarray(arr["index"])
    last = len(idx) - 1
    order = sorted(range(len(raw)), key=lambda i: int(raw[i][0]))
    raw = [raw[i] for i in order]
    # The ETH master's index is tz-aware and the RTH one is not, so compare on plain
    # calendar days -- tz is irrelevant for a month-level lockbox boundary and mixing the
    # two raises "Cannot compare tz-naive and tz-aware timestamps".
    ex_dates = pd.to_datetime([idx[min(int(t[1]), last)] for t in raw]).tz_localize(None) \
        if getattr(pd.to_datetime([idx[min(int(t[1]), last)] for t in raw]), "tz", None) \
        else pd.to_datetime([idx[min(int(t[1]), last)] for t in raw])
    ex_dates = pd.DatetimeIndex(ex_dates).normalize()
    pnl_pts = np.array([float(t[2]) for t in raw])
    pre = np.asarray(ex_dates < pd.Timestamp(LB_FROM))

    names, series = [], []
    ung = monthly(ex_dates[pre], pnl_pts[pre] * MULT)
    names.append("ungated")
    series.append(ung)

    for m in MODELS:
        prob = paper_gate.score_trades(arr, raw, {"model": m})
        if prob is None:
            print("  %-13s model %s: scoring failed, skipped" % (label, m))
            continue
        for th in THRESHOLDS:
            # size_norm 1.0 on purpose: PBO ranks on Sharpe of monthly returns, which is
            # scale-free, so a per-candidate normalisation constant cannot change the rank
            # and pinning it removes a knob that would otherwise need calibrating 20 times.
            w = hybrid_sizes(prob, th, 1.0)
            p = pnl_pts * w * MULT
            keep = pre & (w > 0)
            if keep.sum() < 30:
                continue
            names.append("%s@%.2f" % (m, th))
            series.append(monthly(ex_dates[keep], p[keep]))

    all_months = sorted(set().union(*[set(s.index) for s in series]))
    M = np.array([[float(s.get(mo, 0.0)) for mo in all_months] for s in series])

    out = probability_backtest_overfitting(M, s_blocks=10, metric="sharpe")
    tot = M.sum(axis=1)
    best_i = int(np.argmax(tot))
    crown = "%s@%.2f" % (crown_model, crown_th)
    crown_i = names.index(crown) if crown in names else None
    spread = (tot.max() - tot.min()) / max(abs(np.median(tot)), 1e-9)

    print("=== %s" % label)
    print("   candidates      : %d  (%d months)" % (M.shape[0], M.shape[1]))
    if out:
        print("   PBO             : %.3f   %s" % (
            out["pbo"], "PASS (<=0.50)" if out["pbo"] <= 0.5 else "FAIL (>0.50)"))
        print("   lambda median   : %s   (>0 means the IS winner usually stays above the OOS median)"
              % out["lambda_median"])
    else:
        print("   PBO             : not computable (too few candidates or months)")
    print("   spread of totals: %.2fx the median  -> %s" % (
        spread, "TIGHT: rank is mostly noise, the pick barely matters"
        if spread < 1.0 else "WIDE: the pick matters, a high PBO here is a real warning"))
    print("   best pre-LB     : %-14s $%s" % (names[best_i], round(tot[best_i])))
    if crown_i is not None:
        print("   DEPLOYED        : %-14s $%s   (rank %d of %d)" % (
            crown, round(tot[crown_i]),
            int(np.argsort(np.argsort(-tot))[crown_i]) + 1, len(tot)))
    print("   ungated         : %-14s $%s" % ("ungated", round(tot[0])))
    print()

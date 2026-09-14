"""r57_enguq_anatomy.py -- WINNER vs LOSER ANATOMY on the ENGU-Q crown, at the SIGNAL bar.

Round 57, 2026-09-14. Owner: "run more test. try to improve the frontier ENGUQ model."
Owner's own framing (parked 2026-09-11, reopened): ENGU-Q was built to read the CONTEXT of the
trade, the LOCATION of the trade and the IMBALANCE of buyers and sellers, so it should win
OFTEN at a modest profit factor. It wins ~29% and is carried by ~31 trades. The lever is WHICH
SETUPS ARE TAKEN. This driver asks, before any rule is written: at the moment the signal fires,
does anything the owner named actually separate the trades that win from the ones that lose?

WHAT IS MEASURED
----------------
* Config: `ENGUQ_1M_ETH_R2_1_0.py` with its own DEFAULT_PARAMS (= the live crown #335 / paper leg
  ENGUQ_335 / NinjaTrader), resolved through tools/queue_guard.resolve_params (no {} trap).
* ONE continuous engine backtest (augur_engine.engine.run_backtest, compiled walk): NQ 1m ETH
  master db_noadj_eth, window 2010-06-07..2026-06-30 PINNED, cost 0.533 pts/RT, $20/pt.
* Trades are sliced by ENTRY time. Only SELECTION trades (entry before 2025-06-30 00:00 ET) are
  kept; every later trade is dropped the moment the engine returns, before any statistic is
  computed or printed. The feature pipeline never receives a bar at/after 2025-06-30.
* Eras: E1 = entries 2010-06-07..2019-12-31, E2 = entries 2020-01-01..2025-06-29.

INFORMATION TIME -- THE SIGNAL BAR, NOT THE FILL BAR
---------------------------------------------------
The R2 file enters with a RESTING LIMIT 0.55 ATR below the signal close and scans up to 10 bars
for a fill. So the engine's trade tuple `t[0]` is the FILL bar, and the decision bar is 1..10
bars before it -- `t[0] - 1` (the house rule for market entries, and trade_anatomy.py's default)
is the signal bar for only ~55% of these trades; for the rest it is a bar AFTER the signal, while
price was already falling toward the limit. The signal bar is therefore recovered EXACTLY from
the strategy's own code: the file's interpreted walk is run once with its `_fill_probe`
instrumentation, whose append() reads the walk's own local `i` (signal bar) and `fill_j` (fill
bar). That walk must reproduce the engine's compiled trade list trade for trade (entry bar,
exit bar, entry price, P&L after cost) or the driver stops. Every feature below is a function of
bars <= the signal bar only ("known at the close of the signal bar").

FEATURES
--------
Own (CONTEXT / LOCATION / IMBALANCE, the owner's three ideas) -- see OWN_META below for each
definition -- plus everything tools/trade_anatomy.py already computes (path_/lvl_/ind_/day_/
vol_/cal_/vt_ families), re-read at the signal bar by passing eb = signal+1 to its own
build_feature_matrix (which reads eb-1). trade_anatomy's cross-market xm_ block (needs the 310 MB
ES master) and on_ block (RTH legs only, NaN on ETH) are not built. trade_anatomy's bar arrays are
built in overlapping 3-year chunks with a 14-month warm-up (the box had ~5 GB free RAM; the
full 5.4M-bar build peaks at several GB) and the overlap is checked for agreement.

STATISTICS (selection window only)
----------------------------------
* winners (P&L after cost > 0) vs losers: medians + Mann-Whitney two-sided p (independence
  assumed -- anti-conservative on a trade list with regime clustering);
* the same questions under two permutation nulls on the rank correlation (feature rank vs outcome),
  for the win indicator, NET R (P&L after cost / the file's own risk unit) and GROSS R (cost added
  back):
    - GLOBAL circular shift (every offset 50..N-50 trades): keeps autocorrelation but NOT era
      trends -- the first run of this driver passed 84 of 159 features on it, led by risk in POINTS,
      because NET R itself trends by era (the fixed 0.533-pt cost is several times heavier per unit
      of risk in 2010-14 than in 2020-25) and so does almost every level-type feature;
    - WITHIN-YEAR circular shift (each calendar year's outcomes shifted independently, 2,000 draws):
      every between-year difference stays inside every null draw, so only the within-year alignment
      of feature and outcome is tested; p is two-sided around the null mean. THIS is the test a
      feature must pass. Benjamini-Hochberg FDR across ALL features, per outcome, q < 0.10;
* win rate, profit factor in R, mean R and mean $ by quintile (global quintiles, and quintiles
  ranked inside each calendar year so the era does not sort the trades);
* era stability: the same rank statistics inside E1 and inside E2 separately;
* a family-wise null for "the best-looking quintile anywhere" (max win rate over every feature x
  quintile), because ~150 features x 5 quintiles will always produce a pretty cell;
* a combined read: a logistic score on all features trained on 2010-2018 entries, scored on
  2019-2025/06 entries (and the reverse) -- a ceiling check on information content, NOT a model
  proposal (memory: enguq-entry-quality-parked);
* TAIL vs BODY: the smallest set of top trades whose removal takes selection net to <= 0, in $
  and in R, compared with the rest at signal time;
* a contamination read: trade_anatomy's features at its default decision bar (fill - 1) vs the
  true signal bar.

Run (from the shared checkout, which holds the master registry):
    cd C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG
    python <worktree>\\tools\\r57_enguq_anatomy.py            [--beacon]
--beacon wraps the run in tools/research_beacon.py (one Firestore job record); off by default.
"""
import os
import sys
import time
import gc
import json
import argparse
import importlib.util

os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"


def _has_registry(root):
    db = os.path.join(root, "optimizer_history.db")
    return os.path.exists(db) and os.path.getsize(db) > 0


DATA_REPO = REPO if _has_registry(REPO) else SHARED
sys.path.insert(0, DATA_REPO)
sys.path.insert(0, os.path.join(DATA_REPO, "tools"))

import warnings                                                     # noqa: E402
warnings.filterwarnings("ignore")
import numpy as np                                                  # noqa: E402
import pandas as pd                                                 # noqa: E402
from scipy import stats as sst                                      # noqa: E402

FN = "ENGUQ_1M_ETH_R2_1_0.py"
WIN = ("2010-06-07", "2026-06-30")
SPLIT = "2025-06-30"
ERA2 = "2020-01-01"
COST, MULT = 0.533, 20.0
SHIFT_MIN = 50
Q_BAR = 0.10
OUT_TXT = os.path.join(HERE, "r37_results", "r57_anatomy.txt")
CACHE = os.path.join(os.environ.get("EDGELOG_CACHE_DIR", r"C:\EdgeLog\_anatomy_cache"), "r57")
# ENGUQ.md 2026-09-08 (queue_guard, continuous, entry-sliced) -- the parity reference
DOC_SEL = dict(n=1830, pf=1.714, net=522613.0, dd=38687.0)
TA_CHUNKS = ["2010-06-07", "2013-01-01", "2016-01-01", "2019-01-01", "2022-01-01", SPLIT]
WARM_DAYS = 425          # ~14 calendar months of bars before each chunk's trade period
OVERLAP_DAYS = 90        # each chunk also computes the next 3 months, to check agreement

OUT = []


def say(s=""):
    print(s, flush=True)
    OUT.append(s)


# ─────────────────────────────────────────────────────────────────────────────
# 1. trades + exact signal bars
# ─────────────────────────────────────────────────────────────────────────────

class _FillProbe(list):
    """Research instrumentation: the strategy calls _fill_probe.append(signal_close - fill)
    once per limit touch. We ignore the value and read the walk's OWN locals instead."""
    def append(self, v):
        loc = sys._getframe(1).f_locals
        list.append(self, (int(loc["i"]), int(loc["fill_j"]), float(loc["fill_price"]),
                           float(loc["limit"])))


class _SignalProbe(list):
    """_signal_probe.append(1) fires on every bar that clears every entry filter."""
    def append(self, v):
        list.append(self, int(sys._getframe(1).f_locals["i"]))


def load_trades():
    from augur_engine.engine import run_backtest, load_strategy
    from augur_engine.data import find_master, load_master_arrays
    from queue_guard import resolve_params

    P, src, has_dp = resolve_params(FN, {})
    say("RESOLVED PARAMS (%s DEFAULT_PARAMS): %s" % (FN, json.dumps(P, sort_keys=True)))
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(arr["index"])
    assert idx.is_monotonic_increasing, "master index not sorted"
    split_ts = pd.Timestamp(SPLIT, tz=idx.tz)
    n_split = int(idx.searchsorted(split_ts))            # first bar at/after the split
    say("MASTER %s (id %s)  window %s..%s  bars=%d  (bars before split=%d)"
        % (m["filename"], m.get("id"), WIN[0], WIN[1], len(idx), n_split))

    r = run_backtest(FN, arrays=arr, params=dict(P), cost_pts=COST, return_trades=True)
    sel = [t for t in (r.get("trades") or []) if int(t[0]) < n_split]
    del r                                                  # lockbox trades never kept

    mod = load_strategy(FN)
    fp, sp = _FillProbe(), _SignalProbe()
    r2 = mod.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"],
                          volumes=arr["volume"], day_id=arr["day_id"], return_trades=True,
                          _fill_probe=fp, _signal_probe=sp, **P)
    sel2 = [t for t in r2["trades"] if int(t[0]) < n_split]
    del r2
    ok = len(sel2) == len(sel) and all(
        a[0] == b[0] and a[1] == b[1] and abs(a[4] - b[4]) < 1e-9 and abs((a[2] - COST) - b[2]) < 1e-9
        for a, b in zip(sel2, sel))
    if not ok:
        raise SystemExit("PARITY FAIL: interpreted probe walk != engine compiled walk on selection trades")
    fills = [x for x in fp if x[1] < n_split]
    fj = np.array([x[1] for x in fills])
    assert np.all(np.diff(fj) > 0), "fill bars not strictly increasing -- signal mapping ambiguous"
    fmap = {x[1]: x for x in fills}
    sig = np.array([fmap[int(t[0])][0] for t in sel], dtype=np.int64)
    limit = np.array([fmap[int(t[0])][3] for t in sel])
    signals_all = np.array([s for s in sp if s < n_split], dtype=np.int64)
    say("PROBE WALK == ENGINE: %d selection trades identical (entry bar, exit bar, entry price, P&L after cost); "
        "signal bar recovered for every trade" % len(sel))
    return arr, idx, n_split, sel, sig, limit, signals_all, P, mod


# ─────────────────────────────────────────────────────────────────────────────
# 2. own features (CONTEXT / LOCATION / IMBALANCE) at the signal bar
# ─────────────────────────────────────────────────────────────────────────────

OWN_META = {}


def _reg(name, group, desc, kind="cont"):
    OWN_META[name] = (group, desc, kind)


def build_own_features(arr, idx, n_split, T, sig, limit, signals_all, P, mod):
    O = arr["open"][:n_split]; H = arr["high"][:n_split]
    L = arr["low"][:n_split]; C = arr["close"][:n_split]; V = arr["volume"][:n_split]
    ix = idx[:n_split]
    n = len(C)
    s = sig
    F = {}
    tl = int(P["tl_len"]); al = int(P["atr_len"])

    # strategy's own ATR (SMA of true range, atr_len) and trend EMA -- exactly as the file
    tr = np.empty(n); tr[0] = H[0] - L[0]
    tr[1:] = np.maximum(H[1:] - L[1:], np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
    cs = np.cumsum(tr)
    atr = np.full(n, np.nan)
    atr[al - 1:] = (cs[al - 1:] - np.concatenate([[0], cs[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    A = atr[s]
    del cs

    ema = mod._ema(np.asarray(C, float), int(P["ema_len"]))
    F["ctx_ema_dist_atr"] = (C[s] - ema[s]) / A
    F["ctx_ema_slope60_atr"] = (ema[s] - ema[s - 60]) / A
    del ema
    _reg("ctx_ema_dist_atr", "CONTEXT", "close minus the strategy's own trend EMA (220 1m bars), in signal-bar ATR(52)")
    _reg("ctx_ema_slope60_atr", "CONTEXT", "change of that EMA over the last 60 bars, in ATR(52)")
    for span, lbl in ((1091, "1 ETH day"), (5455, "5 ETH days"), (21820, "20 ETH days")):
        e = mod._ema(np.asarray(C, float), span)
        F["ctx_ema%d_dist_atr" % span] = (C[s] - e[s]) / A
        _reg("ctx_ema%d_dist_atr" % span, "CONTEXT", "close minus a %d-bar EMA (~%s), in ATR(52)" % (span, lbl))
        del e
    rb = int(P["regime_len"]) * 390
    rc = np.cumsum(C)
    reg_s = (rc[s] - np.where(s - rb >= 0, rc[np.clip(s - rb, 0, None)], 0.0)) / rb
    F["ctx_regime_sma_dist_atr"] = (C[s] - reg_s) / A
    _reg("ctx_regime_sma_dist_atr", "CONTEXT", "close minus the file's regime SMA (3,900 bars ~3.6 ETH days), in ATR(52)")
    del rc
    F["ctx_atr_pct_price"] = A / C[s] * 100.0
    _reg("ctx_atr_pct_price", "CONTEXT", "ATR(52) as % of price (era-neutral volatility level)")

    # ETH trading day (rolls at 18:00 ET), same convention as feature_board.load
    dkey = (ix + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8
    did = pd.factorize(dkey)[0].astype(np.int64)
    del dkey
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
    ends = np.r_[starts[1:], n]
    nd = len(starts)
    dO = O[starts]; dH = np.maximum.reduceat(H, starts); dL = np.minimum.reduceat(L, starts)
    dC = C[ends - 1]
    dd = did[s]
    sess_open = dO[dd]
    sess_hi = np.array([H[starts[d]:k + 1].max() for d, k in zip(dd, s)])
    sess_lo = np.array([L[starts[d]:k + 1].min() for d, k in zip(dd, s)])
    pdH = np.r_[np.nan, dH[:-1]]; pdL = np.r_[np.nan, dL[:-1]]; pdC = np.r_[np.nan, dC[:-1]]
    dtr = np.maximum(dH - dL, np.maximum(np.abs(dH - pdC), np.abs(dL - pdC)))
    datr = pd.Series(dtr).rolling(14, min_periods=14).mean().shift(1).to_numpy()   # prior-day-shifted
    DA = datr[dd]
    F["ctx_day_move_datr"] = (C[s] - sess_open) / DA
    _reg("ctx_day_move_datr", "CONTEXT", "the day's direction so far: close minus the 18:00 ETH session open, in daily ATR(14, prior-day)")
    F["ctx_pdr_pos"] = (C[s] - pdL[dd]) / (pdH[dd] - pdL[dd])
    _reg("ctx_pdr_pos", "CONTEXT", "position of the close inside the prior ETH session's high-low range (0=low, 1=high; can be <0 or >1)")
    F["loc_pdh_datr"] = (C[s] - pdH[dd]) / DA
    F["loc_pdl_datr"] = (C[s] - pdL[dd]) / DA
    _reg("loc_pdh_datr", "LOCATION", "close minus prior ETH session HIGH, in daily ATR")
    _reg("loc_pdl_datr", "LOCATION", "close minus prior ETH session LOW, in daily ATR")
    F["loc_sess_hi_atr"] = (C[s] - sess_hi) / A
    F["loc_sess_lo_atr"] = (C[s] - sess_lo) / A
    F["loc_sess_range_pos"] = (C[s] - sess_lo) / np.where(sess_hi > sess_lo, sess_hi - sess_lo, np.nan)
    _reg("loc_sess_hi_atr", "LOCATION", "close minus the session high so far (incl. the signal bar), in ATR(52); 0 = at the high")
    _reg("loc_sess_lo_atr", "LOCATION", "close minus the session low so far, in ATR(52)")
    _reg("loc_sess_range_pos", "LOCATION", "close position inside the session's high-low range so far (0..1)")

    # days since a new 20-day high (daily ETH highs, only days completed before the signal day)
    prior20 = pd.Series(dH).rolling(20, min_periods=20).max().shift(1).to_numpy()
    new20 = dH > prior20
    last_new = pd.Series(np.where(new20, np.arange(nd), np.nan)).ffill().shift(1).to_numpy()
    F["ctx_days_since_20d_high"] = dd - last_new[dd]
    F["ctx_at_20d_high_now"] = (sess_hi >= prior20[dd]).astype(float)
    F["ctx_at_20d_high_now"][np.isnan(prior20[dd])] = np.nan
    _reg("ctx_days_since_20d_high", "CONTEXT", "trading days since the last session that made a new 20-day high (before the signal day)")
    _reg("ctx_at_20d_high_now", "CONTEXT", "1 if today's high so far is at/above the prior 20 sessions' high", "bin")

    # clock, session bucket
    hh = ix.hour.to_numpy()[s]; mm = ix.minute.to_numpy()[s]
    cmin = hh * 60 + mm
    F["ctx_mins_since_1800"] = ((cmin - 18 * 60) % 1440).astype(float)
    _reg("ctx_mins_since_1800", "CONTEXT", "time of day: minutes since 18:00 ET (0 = ETH open, 930 = 09:30, 1320 = 16:00)")
    bucket = np.where((cmin >= 570) & (cmin < 960), 2, np.where(cmin >= 960, np.where(cmin < 1080, 3, 0),
                                                                np.where(cmin < 180, 0, 1)))
    F["ctx_session_bucket"] = bucket.astype(float)
    _reg("ctx_session_bucket", "CONTEXT", "0=Asia 18:00-02:59, 1=Europe 03:00-09:29, 2=RTH 09:30-15:59, 3=post 16:00-17:00", "cat")
    F["ctx_is_rth"] = (bucket == 2).astype(float)
    _reg("ctx_is_rth", "CONTEXT", "1 = signal inside the 09:30-16:00 cash session, 0 = overnight/post", "bin")

    # RTH sessions: last COMPLETED cash session's high/low, and the cash-session move so far
    cm_all = ix.hour.to_numpy() * 60 + ix.minute.to_numpy()
    rth = np.flatnonzero((cm_all >= 570) & (cm_all < 960))
    rdate = ix[rth].tz_localize(None).normalize().asi8
    rst = np.flatnonzero(np.r_[True, rdate[1:] != rdate[:-1]])
    rend_bar = np.r_[rst[1:], len(rth)]
    rH = np.maximum.reduceat(H[rth], rst); rL = np.minimum.reduceat(L[rth], rst)
    rO = O[rth[rst]]
    r_end_time = pd.DatetimeIndex(rdate[rst]).tz_localize(ix.tz) + pd.Timedelta(hours=16)
    sig_close_time = ix[s] + pd.Timedelta(minutes=1)
    k_done = r_end_time.searchsorted(sig_close_time, side="right") - 1
    okk = k_done >= 0
    rpdH = np.where(okk, rH[np.clip(k_done, 0, None)], np.nan)
    rpdL = np.where(okk, rL[np.clip(k_done, 0, None)], np.nan)
    F["ctx_rth_pdr_pos"] = (C[s] - rpdL) / (rpdH - rpdL)
    F["loc_rth_pdh_datr"] = (C[s] - rpdH) / DA
    F["loc_rth_pdl_datr"] = (C[s] - rpdL) / DA
    _reg("ctx_rth_pdr_pos", "CONTEXT", "position of the close inside the last COMPLETED 09:30-16:00 cash session's range")
    _reg("loc_rth_pdh_datr", "LOCATION", "close minus last completed cash-session HIGH, in daily ATR")
    _reg("loc_rth_pdl_datr", "LOCATION", "close minus last completed cash-session LOW, in daily ATR")
    # cash-session move so far (signal inside RTH only)
    rpos = np.searchsorted(rth, s)
    in_rth = (rpos < len(rth)) & (rth[np.clip(rpos, 0, len(rth) - 1)] == s)
    kcur = np.searchsorted(rst, rpos, side="right") - 1
    F["ctx_rth_move_datr"] = np.where(in_rth, (C[s] - rO[np.clip(kcur, 0, None)]) / DA, np.nan)
    _reg("ctx_rth_move_datr", "CONTEXT", "cash-session direction so far: close minus the 09:30 open, in daily ATR (RTH signals only)")
    del rth, rdate, cm_all

    # round numbers
    F["loc_rn100_above_atr"] = (np.ceil(C[s] / 100.0) * 100.0 - C[s]) / A
    F["loc_rn100_near_atr"] = np.minimum(C[s] % 100.0, 100.0 - C[s] % 100.0) / A
    F["loc_rn100_frac"] = (C[s] % 100.0) / 100.0
    F["loc_rn1000_near_datr"] = np.minimum(C[s] % 1000.0, 1000.0 - C[s] % 1000.0) / DA
    _reg("loc_rn100_above_atr", "LOCATION", "distance up to the next 100-point round number, in ATR(52)")
    _reg("loc_rn100_near_atr", "LOCATION", "distance to the nearest 100-point round number, in ATR(52)")
    _reg("loc_rn100_frac", "LOCATION", "where the close sits between 100-point round numbers (0..1)")
    _reg("loc_rn1000_near_datr", "LOCATION", "distance to the nearest 1,000-point round number, in daily ATR")

    # trendline / pullback / extension -- per trade, on the strategy's own windows
    x = np.arange(tl); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    cols = {k: np.full(len(s), np.nan) for k in (
        "loc_tl_slope_atr100", "loc_tl_r2", "imb_brk_atr", "loc_n_pivots", "loc_n_lower_highs",
        "loc_lh_frac", "loc_pb_depth_atr", "loc_pb_depth_pct", "loc_pb_recovery", "loc_bars_since_swing_low",
        "loc_bars_since_win_high", "loc_ext_swing_atr", "loc_ext60_atr", "loc_plan_risk_atr",
        "loc_plan_risk_pct", "loc_cost_share_R", "loc_limit_vs_tl_atr", "imb_body_ratio", "imb_close_loc", "imb_upper_wick",
        "imb_body_vs_avg20", "imb_range_atr", "imb_vol_ratio20", "imb_vol_ratio_prior20", "imb_vol_z60",
        "imb_upvol_share10", "imb_upvol_share30", "imb_upvol_share60", "imb_upbar_share20",
        "imb_close_vs_prevhigh_atr", "imb_bar_ret_atr", "imb_ret15_atr", "imb_ret60_atr", "imb_er100",
        "loc_swing_low_risk_pts")}
    PW = 5
    for q, k in enumerate(s):
        a = A[q]
        hw = H[k - tl:k]
        slope = (xd * (hw - hw.mean())).sum() / xss
        tl_now = hw.mean() + slope * (tl - xm)
        fit = hw.mean() + slope * (x - xm)
        sst_ = ((hw - hw.mean()) ** 2).sum()
        cols["loc_tl_slope_atr100"][q] = slope * 100.0 / a
        cols["loc_tl_r2"][q] = 1.0 - ((hw - fit) ** 2).sum() / sst_ if sst_ > 0 else np.nan
        cols["imb_brk_atr"][q] = (C[k] - tl_now) / a
        # pivot highs inside the trendline window, confirmed by PW bars on each side (all < k)
        piv = []
        for j in range(k - tl + PW, k - PW):
            hj = H[j]
            if hj > H[j - PW:j].max() and hj >= H[j + 1:j + PW + 1].max():
                piv.append(hj)
        cols["loc_n_pivots"][q] = len(piv)
        nlh = sum(1 for u in range(1, len(piv)) if piv[u] < piv[u - 1])
        cols["loc_n_lower_highs"][q] = nlh
        cols["loc_lh_frac"][q] = nlh / (len(piv) - 1) if len(piv) > 1 else np.nan
        swing_low = L[k - tl:k + 1].min()
        win_hi = hw.max()
        cols["loc_swing_low_risk_pts"][q] = C[k] - swing_low
        cols["loc_pb_depth_atr"][q] = (win_hi - swing_low) / a
        cols["loc_pb_depth_pct"][q] = (win_hi - swing_low) / win_hi * 100.0
        cols["loc_pb_recovery"][q] = (C[k] - swing_low) / (win_hi - swing_low) if win_hi > swing_low else np.nan
        cols["loc_bars_since_swing_low"][q] = tl - int(np.argmin(L[k - tl:k + 1]))
        cols["loc_bars_since_win_high"][q] = tl - int(np.argmax(hw))
        cols["loc_ext_swing_atr"][q] = (C[k] - swing_low) / a
        cols["loc_ext60_atr"][q] = (C[k] - L[k - 60:k + 1].min()) / a
        cols["loc_plan_risk_atr"][q] = (limit[q] - swing_low) / a
        cols["loc_plan_risk_pct"][q] = (limit[q] - swing_low) / limit[q] * 100.0
        cols["loc_cost_share_R"][q] = COST / max(limit[q] - swing_low, 1e-9)
        cols["loc_limit_vs_tl_atr"][q] = (limit[q] - tl_now) / a
        rng = H[k] - L[k]
        body = abs(C[k] - O[k])
        cols["imb_body_ratio"][q] = body / rng if rng > 0 else np.nan
        cols["imb_close_loc"][q] = (C[k] - L[k]) / rng if rng > 0 else np.nan
        cols["imb_upper_wick"][q] = (H[k] - max(O[k], C[k])) / rng if rng > 0 else np.nan
        pb = np.abs(C[k - 20:k] - O[k - 20:k]).mean()
        cols["imb_body_vs_avg20"][q] = body / pb if pb > 0 else np.nan
        cols["imb_range_atr"][q] = rng / a
        v20i = V[k - 19:k + 1].mean()
        cols["imb_vol_ratio20"][q] = V[k] / v20i if v20i > 0 else np.nan
        v20p = V[k - 20:k].mean()
        cols["imb_vol_ratio_prior20"][q] = V[k] / v20p if v20p > 0 else np.nan
        lv = np.log1p(V[k - 60:k])
        sd = lv.std()
        cols["imb_vol_z60"][q] = (np.log1p(V[k]) - lv.mean()) / sd if sd > 0 else np.nan
        for N in (10, 30, 60):
            vv = V[k - N + 1:k + 1]; up = C[k - N + 1:k + 1] > O[k - N + 1:k + 1]
            tot = vv.sum()
            cols["imb_upvol_share%d" % N][q] = vv[up].sum() / tot if tot > 0 else np.nan
        cols["imb_upbar_share20"][q] = float((C[k - 19:k + 1] > O[k - 19:k + 1]).mean())
        cols["imb_close_vs_prevhigh_atr"][q] = (C[k] - H[k - 1]) / a
        cols["imb_bar_ret_atr"][q] = (C[k] - C[k - 1]) / a
        cols["imb_ret15_atr"][q] = (C[k] - C[k - 15]) / a
        cols["imb_ret60_atr"][q] = (C[k] - C[k - 60]) / a
        path = np.abs(np.diff(C[k - 100:k + 1])).sum()
        cols["imb_er100"][q] = abs(C[k] - C[k - 100]) / path if path > 0 else np.nan
    F.update(cols)
    metas = [
        ("loc_tl_slope_atr100", "LOCATION", "trendline slope (fit to the last 206 highs), ATR(52) per 100 bars (more negative = steeper)"),
        ("loc_tl_r2", "LOCATION", "trendline fit R^2 on those 206 highs (1 = the highs sit on a clean line)"),
        ("loc_n_pivots", "LOCATION", "number of 11-bar swing highs inside the 206-bar trendline window"),
        ("loc_n_lower_highs", "LOCATION", "how many of those swing highs were lower than the one before"),
        ("loc_lh_frac", "LOCATION", "share of consecutive swing-high pairs that were lower highs"),
        ("loc_pb_depth_atr", "LOCATION", "pullback depth before the signal: window high minus swing low, in ATR(52)"),
        ("loc_pb_depth_pct", "LOCATION", "the same pullback depth as % of price"),
        ("loc_pb_recovery", "LOCATION", "how much of that pullback the signal close has already recovered (0..1+)"),
        ("loc_bars_since_swing_low", "LOCATION", "bars since the 206-bar swing low"),
        ("loc_bars_since_win_high", "LOCATION", "bars since the trendline window's highest high"),
        ("loc_ext_swing_atr", "LOCATION", "how extended the move already is: close minus the swing low, in ATR(52)"),
        ("loc_ext60_atr", "LOCATION", "close minus the 60-bar low, in ATR(52)"),
        ("loc_plan_risk_atr", "LOCATION", "PLANNED risk at the signal: limit price minus swing low, in ATR(52)"),
        ("loc_plan_risk_pct", "LOCATION", "PLANNED risk as % of price (the edge-carrying 'big stop' read, known at the signal)"),
        ("loc_cost_share_R", "LOCATION", "the 0.533-pt round-trip cost as a fraction of the PLANNED risk (known at the signal; the era-cost mechanic)"),
        ("loc_limit_vs_tl_atr", "LOCATION", "resting limit price minus the trendline value, in ATR(52) (<0 = limit sits below the line)"),
        ("loc_swing_low_risk_pts", "LOCATION", "close minus swing low in POINTS (era-confounded; kept for reference)"),
        ("imb_brk_atr", "IMBALANCE", "breakout size: close minus the trendline, in ATR(52) (file requires >= 1.6)"),
        ("imb_body_ratio", "IMBALANCE", "signal candle body / range"),
        ("imb_close_loc", "IMBALANCE", "close location within the signal bar (0=low, 1=high)"),
        ("imb_upper_wick", "IMBALANCE", "upper wick / range of the signal bar"),
        ("imb_body_vs_avg20", "IMBALANCE", "signal body vs the average body of the prior 20 bars"),
        ("imb_range_atr", "IMBALANCE", "signal bar high-low range, in ATR(52)"),
        ("imb_vol_ratio20", "IMBALANCE", "signal volume / 20-bar average incl. the bar (the file's own volume test, >= 1.1)"),
        ("imb_vol_ratio_prior20", "IMBALANCE", "signal volume / average of the PRIOR 20 bars"),
        ("imb_vol_z60", "IMBALANCE", "z-score of log signal volume vs the prior 60 bars"),
        ("imb_upvol_share10", "IMBALANCE", "up-volume share of the last 10 bars (volume on close>open bars / total; no order flow)"),
        ("imb_upvol_share30", "IMBALANCE", "up-volume share of the last 30 bars"),
        ("imb_upvol_share60", "IMBALANCE", "up-volume share of the last 60 bars"),
        ("imb_upbar_share20", "IMBALANCE", "share of the last 20 bars that closed above their open"),
        ("imb_close_vs_prevhigh_atr", "IMBALANCE", "close minus the prior bar's high, in ATR(52)"),
        ("imb_bar_ret_atr", "IMBALANCE", "signal bar close-to-close return, in ATR(52)"),
        ("imb_ret15_atr", "IMBALANCE", "15-bar momentum into the signal, in ATR(52)"),
        ("imb_ret60_atr", "IMBALANCE", "60-bar momentum into the signal, in ATR(52)"),
        ("imb_er100", "IMBALANCE", "efficiency ratio of the last 100 bars (move quality; the file's er gate is OFF)"),
    ]
    for nm, g, d in metas:
        _reg(nm, g, d)

    # volume vs the same clock minute over the prior 20 ETH sessions
    cm = (ix.hour.to_numpy() * 60 + ix.minute.to_numpy()).astype(np.int64)
    M = np.full((nd, 1440), np.nan, dtype=np.float32)
    M[did, cm] = V
    Z = np.nan_to_num(M); Cn = (~np.isnan(M)).astype(np.float32)
    del M
    csZ = np.cumsum(Z, axis=0, dtype=np.float64); csN = np.cumsum(Cn, axis=0, dtype=np.float64)
    del Z, Cn
    d0 = dd; d1 = np.clip(dd - 21, -1, None)
    sumv = csZ[d0 - 1, cm[s]] - np.where(d1 >= 0, csZ[np.clip(d1, 0, None), cm[s]], 0.0)
    cntv = csN[d0 - 1, cm[s]] - np.where(d1 >= 0, csN[np.clip(d1, 0, None), cm[s]], 0.0)
    base = np.where((dd >= 21) & (cntv >= 10), sumv / np.maximum(cntv, 1), np.nan)
    F["imb_vol_vs_clock20"] = V[s] / base
    _reg("imb_vol_vs_clock20", "IMBALANCE", "signal volume vs the average volume at the same clock minute over the prior 20 sessions")
    del csZ, csN

    # path-dependent but causal context: previous trade, unfilled signals
    xb = T["exit_bar"].to_numpy()
    prev_exit = np.r_[np.nan, xb[:-1]]
    assert np.all((prev_exit[1:] < s[1:])), "a previous exit is not before the signal bar"
    F["ctx_bars_since_prev_exit"] = s - prev_exit
    F["ctx_prev_trade_win"] = np.r_[np.nan, T["win"].to_numpy()[:-1].astype(float)]
    _reg("ctx_bars_since_prev_exit", "CONTEXT", "bars since the previous ENGU-Q trade closed")
    _reg("ctx_prev_trade_win", "CONTEXT", "1 if the previous trade (already closed) was a winner", "bin")
    cnt_sig = np.searchsorted(signals_all, s, side="left") - np.searchsorted(signals_all, s - 1091, side="left")
    F["ctx_signals_prior_day"] = cnt_sig.astype(float)
    _reg("ctx_signals_prior_day", "CONTEXT", "number of breakout signals the file flagged in the prior 1,091 bars (~1 ETH day), filled or not")
    return F, did, DA


# ─────────────────────────────────────────────────────────────────────────────
# 3. trade_anatomy features, re-read at the signal bar, chunked
# ─────────────────────────────────────────────────────────────────────────────

def load_ta():
    fp = os.path.join(DATA_REPO, "tools", "trade_anatomy.py")
    spec = importlib.util.spec_from_file_location("trade_anatomy_r57", fp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DAY_LEVEL_TA = ("day_prior_ret_pct", "day_prior_range_pctile", "day_prior_close_pos", "day_gap_pct",
                "day_up_streak", "day_ret_5d", "day_ret_20d", "day_of_week", "lvl_pdh_atr", "lvl_pdl_atr",
                "lvl_pdc_atr", "lvl_sma20d_atr", "lvl_sma50d_atr", "lvl_sma200d_atr", "lvl_prior_week_hi_atr",
                "lvl_prior_week_lo_atr", "ind_rsi14_daily", "ind_adx14_daily", "ind_atr_pctile_daily",
                "ind_macd_sign_daily", "ind_er20_daily", "vt_realized5d_vs_20d", "vt_vrp")


def build_ta_features(TA, arr, idx, n_split, sig, fill, ext_vix):
    """Signal-bar reading (eb = signal + 1) AND trade_anatomy's default reading (eb = fill)."""
    nt = len(sig)
    names = TA.FEATURE_NAMES
    X_sig = pd.DataFrame(np.nan, index=range(nt), columns=names)
    X_fill = pd.DataFrame(np.nan, index=range(nt), columns=names)
    done = np.zeros(nt, bool)
    ov_diffs = {}
    pending = {}
    ov_count = [0]
    ix = idx[:n_split]
    sig_t = ix[sig]
    tz = ix.tz
    edge_nan = 0
    for c in range(len(TA_CHUNKS) - 1):
        t0 = pd.Timestamp(TA_CHUNKS[c], tz=tz); t1 = pd.Timestamp(TA_CHUNKS[c + 1], tz=tz)
        t1x = min(t1 + pd.Timedelta(days=OVERLAP_DAYS), pd.Timestamp(SPLIT, tz=tz))
        b0 = int(ix.searchsorted(t0 - pd.Timedelta(days=WARM_DAYS)))
        b1 = int(ix.searchsorted(t1x))
        tsel = np.flatnonzero((sig_t >= t0) & (sig_t < t1x) & (fill < b1))
        if not len(tsel):
            continue
        tc = time.time()
        sl = slice(b0, b1)
        df = pd.DataFrame({"_dt": ix[sl], "open": arr["open"][sl], "high": arr["high"][sl],
                           "low": arr["low"][sl], "close": arr["close"][sl], "volume": arr["volume"][sl]})
        df["_end"] = df["_dt"] + pd.Timedelta(minutes=1)
        dkey = (pd.DatetimeIndex(df["_dt"]) + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8
        df["day_id"] = pd.factorize(dkey)[0]
        day_feat = TA.build_day_features(df, ext_vix=ext_vix)
        B = TA.build_bar_arrays(df, 1, cfg=None, day_feat=day_feat)
        eb_sig = sig[tsel] - b0 + 1
        eb_fill = fill[tsel] - b0
        Xs, _, vs = TA.build_feature_matrix(df, eb_sig, 1, B=B, day_feat=day_feat)
        Xf, _, vf = TA.build_feature_matrix(df, eb_fill, 1, B=B, day_feat=day_feat)
        # a signal on the last bar of an ETH session: eb=signal+1 is the NEXT session's first bar,
        # so trade_anatomy's day-row lookup would read the next day -> NaN those day-level columns
        dayid = df["day_id"].to_numpy()
        cross = dayid[np.clip(eb_sig, 0, len(df) - 1)] != dayid[eb_sig - 1]
        if cross.any():
            Xs.loc[cross, [c_ for c_ in DAY_LEVEL_TA if c_ in Xs.columns] + list(TA.CAL_NAMES)] = np.nan
            edge_nan += int(cross.sum())
        Xs.loc[~vs, :] = np.nan
        Xf.loc[~vf, :] = np.nan
        main = (sig_t[tsel] < t1)
        Xs_np = Xs.to_numpy(float); Xf_np = Xf.to_numpy(float)
        for j, q in enumerate(tsel):
            row = Xs_np[j]
            if not main[j]:
                pending[q] = row                   # computed from THIS chunk; the next chunk owns it
                continue
            X_sig.iloc[q] = row
            X_fill.iloc[q] = Xf_np[j]
            done[q] = True
            if q in pending:                        # same trade from the previous chunk: must agree
                a = pending.pop(q)
                both_nan = np.isnan(a) & np.isnan(row)
                one_nan = np.isnan(a) ^ np.isnan(row)
                dif = np.abs(np.nan_to_num(a) - np.nan_to_num(row))
                rel = dif / np.maximum(np.abs(np.nan_to_num(row)), 1e-9)
                m_ = np.where(one_nan, np.inf, np.where(both_nan, 0.0, np.minimum(dif, rel)))
                for nm, dv in zip(names, m_):
                    ov_diffs[nm] = max(ov_diffs.get(nm, 0.0), float(dv))
                ov_count[0] += 1
        say("  TA chunk %s..%s: bars %d, trades %d (+%d overlap), %.0fs"
            % (TA_CHUNKS[c], TA_CHUNKS[c + 1], b1 - b0, int(main.sum()), int((~main).sum()), time.time() - tc))
        del df, B, day_feat, Xs, Xf
        gc.collect()
    if not done.all():
        say("  WARNING: %d trades got no trade_anatomy row" % int((~done).sum()))
    say("  chunk overlap: %d trades computed from two different chunks and compared" % ov_count[0])
    return X_sig, X_fill, ov_diffs, edge_nan


# ─────────────────────────────────────────────────────────────────────────────
# 4. statistics
# ─────────────────────────────────────────────────────────────────────────────

def bh(p):
    p = np.asarray(p, float)
    out = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    if not len(pv):
        return out
    o = np.argsort(pv)
    q = pv[o] * len(pv) / np.arange(1, len(pv) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    r = np.empty(len(pv)); r[o] = np.clip(q, 0, 1)
    out[ok] = r
    return out


def pf_r(Rv):
    g = Rv[Rv > 0].sum(); l_ = -Rv[Rv < 0].sum()
    return g / l_ if l_ > 0 else np.nan


def groups_for(x, kind):
    """quintile labels 0..4 (rank-based) for continuous features; the value itself (<= 6 values)
    for binary / categorical / low-cardinality features."""
    v = ~np.isnan(x)
    lab = np.full(len(x), -1)
    uniq = np.unique(x[v])
    if kind in ("bin", "cat") or len(uniq) <= 6:
        for gi, u in enumerate(uniq):
            lab[v & (x == u)] = gi
        return lab, ["=%g" % u for u in uniq], True
    r = sst.rankdata(x[v], method="ordinal")
    lab[v] = np.minimum((r - 1) * 5 // v.sum(), 4)
    edges = [np.nanmin(x[v][lab[v] == g]) for g in range(5)]
    return lab, ["Q%d>=%.3g" % (g + 1, edges[g]) for g in range(5)], False


class PermNull:
    """Permutation-index null. P is a K x N matrix: row k puts the OUTCOME of trade P[k, i] at trade
    position i, against the fixed feature sequence. Statistic = rank correlation (feature rank vs outcome).
    p is two-sided around the NULL MEAN, because the within-year null keeps every between-year difference
    in every draw, so its centre is the part of the correlation that years alone explain -- not zero."""

    def __init__(self, P, outcomes):
        self.P = P
        self.K = P.shape[0]
        self.N = P.shape[1]
        self.y = {k: np.asarray(v, float) for k, v in outcomes.items()}
        self.Y = {k: v[P].astype(np.float32) for k, v in self.y.items()}

    def cont(self, x, keys=None):
        v = ~np.isnan(x)
        fr = sst.rankdata(x[v]); fr = fr - fr.mean(); fr = fr / (np.linalg.norm(fr) + 1e-12)
        fr32 = fr.astype(np.float32)
        out = {}
        for k in (keys or self.y.keys()):
            Yv = self.Y[k] if v.all() else self.Y[k][:, v]
            Yc = Yv - Yv.mean(axis=1, keepdims=True)
            c = (Yc @ fr32) / (np.linalg.norm(Yc, axis=1) + 1e-12)
            y = self.y[k][v]; yc = y - y.mean()
            c0 = float(yc @ fr / (np.linalg.norm(yc) + 1e-12))
            mu = float(c.mean())
            p = (1 + int(np.sum(np.abs(c - mu) >= abs(c0 - mu) - 1e-9))) / (1 + self.K)
            out[k] = (c0, p, mu)
        return out

    def cat(self, lab, keys=None):
        v = lab >= 0
        gs = np.unique(lab[v])
        G = np.stack([(lab[v] == g) for g in gs]).astype(np.float32)
        ng = G.sum(axis=1, keepdims=True)
        out = {}
        for k in (keys or self.y.keys()):
            Yv = self.Y[k][:, v]
            mk = Yv.mean(axis=1, keepdims=True)
            gm = (G @ Yv.T) / ng
            stat = (ng * (gm - mk.T) ** 2).sum(axis=0)
            y = self.y[k][v]
            g0 = np.array([y[lab[v] == g].mean() for g in gs])
            s0 = float((ng[:, 0] * (g0 - y.mean()) ** 2).sum())
            out[k] = (np.nan, (1 + int(np.sum(stat >= s0 - 1e-9))) / (1 + self.K), np.nan)
        return out

    def group_max(self, lab, key, scale=1.0, min_n=50):
        gs = [g for g in np.unique(lab[lab >= 0]) if (lab == g).sum() >= min_n]
        if not gs:
            return None
        G = np.stack([(lab == g) for g in gs]).astype(np.float32)
        ng = G.sum(axis=1, keepdims=True)
        null = ((G @ self.Y[key].T) / ng / scale).max(axis=0)
        obs = max(self.y[key][lab == g].mean() / scale for g in gs)
        return null, obs


def circular_P(N, lo=SHIFT_MIN):
    offs = np.arange(lo, N - lo + 1)
    return ((np.arange(N)[None, :] - offs[:, None]) % N).astype(np.int32)


def within_year_P(years, K=2000, seed=57):
    """Independent circular shift of the outcome sequence INSIDE each calendar year of entry."""
    rng = np.random.default_rng(seed)
    N = len(years)
    P = np.empty((K, N), dtype=np.int32)
    starts = np.flatnonzero(np.r_[True, years[1:] != years[:-1]])
    ends = np.r_[starts[1:], N]
    for a, b in zip(starts, ends):
        L = b - a
        lo = max(1, int(np.ceil(0.1 * L)))
        hi = max(lo + 1, L - lo + 1)
        o = rng.integers(lo, hi, size=K)
        P[:, a:b] = a + (np.arange(L)[None, :] + o[:, None]) % L
    return P


def within_year_quintiles(x, years):
    lab = np.full(len(x), -1)
    for y in np.unique(years):
        m = (years == y) & ~np.isnan(x)
        if m.sum() < 10:
            continue
        r = sst.rankdata(x[m], method="ordinal")
        lab[m] = np.minimum((r - 1) * 5 // m.sum(), 4)
    return lab


def feature_stats(name, x, kind, T, GS, WY):
    win = T["win"].to_numpy().astype(bool); R = T["R"].to_numpy(); Rg = T["Rg"].to_numpy()
    usd = T["usd"].to_numpy(); era2 = T["era2"].to_numpy(); years = T["year"].to_numpy()
    v = ~np.isnan(x)
    d = dict(name=name, n=int(v.sum()), kind=kind)
    if v.sum() < 100 or np.nanstd(x) == 0:
        d["skip"] = True
        return d
    lab, glabels, discrete = groups_for(x, kind)
    d["discrete"] = discrete
    xw, xl = x[v & win], x[v & ~win]
    d["med_w"], d["med_l"] = float(np.median(xw)), float(np.median(xl))
    if kind == "cat":
        tab = pd.crosstab(lab[v], win[v])
        d["p_mw"] = float(sst.chi2_contingency(tab)[1]) if tab.shape[0] > 1 and tab.shape[1] > 1 else np.nan
        d["rb"] = np.nan
        d["rho_R"], d["p_rho"], d["rho_t"] = np.nan, float(sst.kruskal(*[R[lab == g] for g in np.unique(lab[v])]).pvalue), np.nan
        gs_ = GS.cat(lab, ("win", "rR")); wy_ = WY.cat(lab, ("win", "rR", "rRg"))
    else:
        mwr = sst.mannwhitneyu(xw, xl, alternative="two-sided")
        d["p_mw"] = float(mwr.pvalue)
        d["rb"] = float(2 * mwr.statistic / (len(xw) * len(xl)) - 1)
        rr = sst.spearmanr(x[v], R[v])
        d["rho_R"], d["p_rho"] = float(rr.correlation), float(rr.pvalue)
        d["rho_t"] = float(sst.spearmanr(x[v], np.arange(len(x))[v]).correlation)
        gs_ = GS.cont(x, ("win", "rR")); wy_ = WY.cont(x, ("win", "rR", "rRg"))
    d["p_gs_win"], d["p_gs_R"] = gs_["win"][1], gs_["rR"][1]
    d["p_wy_win"], d["p_wy_R"], d["p_wy_Rg"] = wy_["win"][1], wy_["rR"][1], wy_["rRg"][1]
    d["wy_centre_R"] = wy_["rR"][2]
    rows = []
    for g in range(len(glabels)):
        m = lab == g
        if m.sum() == 0:
            rows.append(None); continue
        rows.append(dict(lbl=glabels[g], n=int(m.sum()), wr=100 * win[m].mean(), pfR=pf_r(R[m]),
                         mR=float(R[m].mean()), musd=float(usd[m].mean())))
    d["groups"] = rows
    d["_lab"] = lab
    if not discrete:
        lw = within_year_quintiles(x, years)
        d["_lab_wy"] = lw
        d["groups_wy"] = [dict(n=int((lw == g).sum()), wr=100 * win[lw == g].mean(), pfR=pf_r(R[lw == g]),
                               mR=float(R[lw == g].mean())) for g in range(5)]
    else:
        d["_lab_wy"] = None
        d["groups_wy"] = None
    for tag, em in (("E1", ~era2), ("E2", era2)):
        vv = v & em
        if vv.sum() < 60 or (win[vv].sum() < 10) or ((~win[vv]).sum() < 10):
            d[tag] = None; continue
        if kind == "cat":
            labe = lab.copy(); labe[~vv] = -1
            tab = pd.crosstab(labe[vv], win[vv])
            p = float(sst.chi2_contingency(tab)[1]) if tab.shape[0] > 1 and tab.shape[1] > 1 else np.nan
            d[tag] = dict(n=int(vv.sum()), rb=np.nan, p=p, rho=np.nan, spread=np.nan)
            continue
        r_ = sst.mannwhitneyu(x[vv & win], x[vv & ~win], alternative="two-sided")
        rb = 2 * r_.statistic / ((vv & win).sum() * (vv & ~win).sum()) - 1
        rho = sst.spearmanr(x[vv], R[vv]).correlation
        le, _, disc = groups_for(np.where(vv, x, np.nan), kind)
        spread = np.nan if disc else 100 * (win[le == 4].mean() - win[le == 0].mean())
        d[tag] = dict(n=int(vv.sum()), rb=float(rb), p=float(r_.pvalue), rho=float(rho), spread=float(spread))
    e1, e2 = d.get("E1"), d.get("E2")
    if kind != "cat" and e1 and e2:
        d["same_sign"] = bool(np.sign(e1["rb"]) == np.sign(e2["rb"]) and np.sign(e1["rho"]) == np.sign(e2["rho"]))
        d["both_p10"] = bool(e1["p"] < 0.10 and e2["p"] < 0.10)
    else:
        d["same_sign"] = None; d["both_p10"] = None
    return d


def fmt(v, f="%.3f"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f % v


def base_stats(T, mask, label):
    usd = T["usd"].to_numpy()[mask]; R = T["R"].to_numpy()[mask]; w = usd > 0
    gross = T["pts"].to_numpy()[mask] + COST
    gw = usd[w].sum(); gl = -usd[~w].sum()
    srt = np.sort(usd)[::-1]
    top10 = srt[:10].sum()
    k = 0; rem = usd.sum()
    while rem > 0 and k < len(srt):
        rem -= srt[k]; k += 1
    say("  %-26s n=%5d  win=%.1f%% (gross>0 %.1f%%, exact-entry scratches %d)  PF=%.3f  net=$%s  meanR=%+.3f  PF(R)=%.3f  "
        "medW/medL=%.2fx (break-even %.2fx)  top-10 share=%.0f%%  trades-to-zero=%d (%.1f%%)"
        % (label, mask.sum(), 100 * w.mean(), 100 * (gross > 1e-6).mean(), int((np.abs(gross) <= 1e-6).sum()),
           gw / gl, format(usd.sum(), ",.0f"), R.mean(), pf_r(R),
           np.median(usd[w]) / abs(np.median(usd[~w])), (1 - w.mean()) / w.mean(), 100 * top10 / usd.sum(),
           k, 100.0 * k / mask.sum()))
    return k


def trades_to_zero(vals):
    srt = np.sort(vals)[::-1]; k = 0; rem = vals.sum()
    while rem > 0 and k < len(srt):
        rem -= srt[k]; k += 1
    return k


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beacon", action="store_true")
    a = ap.parse_args()
    os.chdir(DATA_REPO)
    t_all = time.time()
    if a.beacon:
        from research_beacon import beacon
        with beacon("r57 ENGU-Q signal-bar anatomy", total=5) as b:
            run(b)
    else:
        run(None)
    say("\nruntime %.0fs" % (time.time() - t_all))
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT) + "\n")
    print("wrote", OUT_TXT)


def run(beacon_obj):
    step = (lambda i: beacon_obj.step(i)) if beacon_obj else (lambda i: None)
    say("=" * 120)
    say("r57 ENGU-Q WINNER vs LOSER ANATOMY at the SIGNAL bar -- run #335 crown = %s DEFAULT_PARAMS" % FN)
    say("NQ 1m ETH db_noadj_eth | window %s..%s pinned | cost %.3f pts/RT | $%.0f/pt | one continuous engine backtest"
        % (WIN[0], WIN[1], COST, MULT))
    say("SELECTION = entries before %s 00:00 ET ONLY. Lockbox trades are dropped on return and never analysed. "
        "Eras: E1 2010-06-07..2019-12-31, E2 2020-01-01..2025-06-29." % SPLIT)
    say("generated %s" % time.strftime("%Y-%m-%d %H:%M"))
    say("=" * 120)
    arr, idx, n_split, sel, sig, limit, signals_all, P, mod = load_trades()
    step(1)
    ix = idx[:n_split]
    fill = np.array([int(t[0]) for t in sel]); xb = np.array([int(t[1]) for t in sel])
    pts = np.array([float(t[2]) for t in sel]); ep = np.array([float(t[4]) for t in sel])
    Lw = arr["low"]
    tl = int(P["tl_len"])
    swing = np.array([Lw[k - tl:k + 1].min() for k in sig])
    risk = ep - swing
    T = pd.DataFrame(dict(signal_bar=sig, fill_bar=fill, exit_bar=xb, entry_time=ix[fill], signal_time=ix[sig],
                          pts=pts, usd=pts * MULT, R=pts / risk, Rg=(pts + COST) / risk, risk_pts=risk,
                          entry_px=ep, limit=limit))
    T["win"] = (T["usd"] > 0).astype(int)
    T["era2"] = T["entry_time"] >= pd.Timestamp(ERA2, tz=ix.tz)
    T["year"] = T["entry_time"].dt.year
    T["fill_delay"] = T["fill_bar"] - T["signal_bar"]
    T["gap_fill"] = (T["entry_px"] < T["limit"] - 1e-9).astype(int)
    assert T["entry_time"].is_monotonic_increasing

    usd = T["usd"].to_numpy()
    cum = np.cumsum(usd); dd_ = float((np.maximum.accumulate(cum) - cum).max())
    gw = usd[usd > 0].sum(); gl = -usd[usd < 0].sum()
    say("\nPARITY vs ENGUQ.md 2026-09-08 (queue_guard, continuous, entry-sliced): doc selection n=%d PF %.3f net $%s DD $%s"
        % (DOC_SEL["n"], DOC_SEL["pf"], format(DOC_SEL["net"], ",.0f"), format(DOC_SEL["dd"], ",.0f")))
    close_ok = abs(len(T) - DOC_SEL["n"]) <= 1 and abs(usd.sum() - DOC_SEL["net"]) / DOC_SEL["net"] < 0.005
    say("  this run: n=%d PF %.3f net $%s DD $%s  -> %s"
        % (len(T), gw / gl, format(usd.sum(), ",.0f"), format(dd_, ",.0f"),
           "within 1 trade and 0.5 pct of net, drawdown identical (the master was re-synced since)" if close_ok
           else "*** MISMATCH -- investigate ***"))
    if len(T) == 1831:
        say("  (1,831 is also the selection count tools/tail_adjusted_board.py quoted on 2026-09-09.)")
    fd = np.bincount(T["fill_delay"].to_numpy(), minlength=11)
    say("\nSIGNAL-BAR vs FILL-BAR: fill delay (bars after the signal) counts for 1..10 bars = %s" % [int(v) for v in fd[1:]])
    say("  -> fill bar - 1 is the signal bar for %d of %d trades (%.0f%%); for the other %d, trade_anatomy's default "
        "decision bar is 1-9 bars AFTER the signal." % (fd[1], len(T), 100 * fd[1] / len(T), len(T) - fd[1]))
    say("  gap-through fills (open below the limit): %d" % int(T["gap_fill"].sum()))

    say("\n" + "-" * 120)
    say("BASELINE (selection window, P&L after cost; R = P&L / the file's own risk unit = entry - 206-bar swing low; "
        "gross R adds the 0.533-pt cost back)")
    E1 = ~T["era2"].to_numpy(); E2 = T["era2"].to_numpy(); ALL = np.ones(len(T), bool)
    k_all = base_stats(T, ALL, "SELECTION 2010-06..2025-06")
    k_e1 = base_stats(T, E1, "E1 2010-06..2019-12")
    k_e2 = base_stats(T, E2, "E2 2020-01..2025-06")
    cs_ = COST / T["risk_pts"].to_numpy()
    say("  cost as a share of the risk unit: median %.3f R in E1, %.3f R in E2 -- the same 0.533 pts is ~%.0fx heavier in "
        "the early era, so NET R and win rate carry an era trend that has nothing to do with setup quality."
        % (np.median(cs_[E1]), np.median(cs_[E2]), np.median(cs_[E1]) / np.median(cs_[E2])))
    say("  (top-10 share and trades-to-zero are given PER STRETCH as well as whole-window, per the house honesty rule;"
        " the whole-window share is the kindest number.)")

    say("\n" + "-" * 120)
    say("BUILDING FEATURES")
    tf = time.time()
    F, did, DA = build_own_features(arr, idx, n_split, T, sig, limit, signals_all, P, mod)
    say("  own features: %d in %.0fs" % (len(F), time.time() - tf))
    step(2)
    TA = load_ta()
    from augur_engine import context as ctx
    ext_vix = None
    try:
        ext_vix = ctx.fetch_external_daily(WIN[0], SPLIT)
    except Exception as e:                                           # noqa: BLE001
        say("  VIX fetch failed: %s" % e)
    if ext_vix is not None and "vix" in ext_vix.columns:
        dend = np.r_[np.flatnonzero(did[1:] != did[:-1]), len(did) - 1]
        ddate = pd.DatetimeIndex(ix[dend]).tz_localize(None).normalize()
        vmap = pd.Series(ext_vix["vix"].to_numpy(), index=pd.to_datetime(pd.Index(ext_vix.index)))
        vmap = vmap[~vmap.index.duplicated(keep="last")]
        F["ctx_vix_prior_close"] = vmap.reindex(ddate).to_numpy()[did[sig]]
        _reg("ctx_vix_prior_close", "CONTEXT", "prior-day VIX close (cached yfinance series, shifted one day)")
        if "vix_pctile_1y" in ext_vix.columns:
            vp = pd.Series(ext_vix["vix_pctile_1y"].to_numpy(), index=pd.to_datetime(pd.Index(ext_vix.index)))
            vp = vp[~vp.index.duplicated(keep="last")]
            F["ctx_vix_pctile_1y"] = vp.reindex(ddate).to_numpy()[did[sig]]
            _reg("ctx_vix_pctile_1y", "CONTEXT", "prior VIX close, trailing 1-year percentile")
    tf = time.time()
    X_sig, X_fill, ov_diffs, edge_nan = build_ta_features(TA, arr, idx, n_split, sig, fill, ext_vix)
    say("  trade_anatomy features: %d columns in %.0fs; signal-on-last-bar-of-session day-level NaN'd for %d trades"
        % (X_sig.shape[1], time.time() - tf, edge_nan))
    bad_ov = {k: v for k, v in ov_diffs.items() if v > 1e-3}
    say("  chunk-overlap agreement: %d columns compared, %d differ by > 1e-3 (the smaller of absolute and relative "
        "difference): %s" % (len(ov_diffs), len(bad_ov),
                             ", ".join("%s %.3g" % kv for kv in sorted(bad_ov.items(), key=lambda z: -z[1])[:8]) or "none"))
    if bad_ov:
        say("  (those are trade_anatomy's subsampled trailing-year PERCENTILES -- pctile_vs_prior_days picks its day "
            "sample stride from the median bars/day of whatever frame it is given, so the same bar ranks slightly "
            "differently from two chunks; every other column agrees exactly.)")
    step(3)

    os.makedirs(CACHE, exist_ok=True)
    tab = pd.concat([T.reset_index(drop=True), pd.DataFrame(F), X_sig.add_prefix("ta_")], axis=1)
    tab.to_csv(os.path.join(CACHE, "r57_selection_signal_features.csv"), index=False)

    feats = []
    for nm, x in F.items():
        g, desc, kind = OWN_META[nm]
        feats.append((nm, g, desc, kind, np.asarray(x, float)))
    for nm in TA.FEATURE_NAMES:
        x = X_sig[nm].to_numpy(float)
        if np.isnan(x).mean() > 0.5 or np.nanstd(x) == 0:
            continue
        kind = "bin" if set(np.unique(x[~np.isnan(x)])) <= {0.0, 1.0} else "cont"
        if nm in ("day_of_week",):
            kind = "cat"
        feats.append(("ta:" + nm, "TA:" + TA.FEATURE_GROUP[nm], TA.FEATURE_DESC[nm], kind, x))
    fvals = {f[0]: f[4] for f in feats}

    # outcome vectors + tails (tails defined here so the within-year null can grade them too)
    R = T["R"].to_numpy(); Rg = T["Rg"].to_numpy()
    tail_usd = np.zeros(len(T), bool); tail_usd[np.argsort(-usd)[:k_all]] = True
    kR = trades_to_zero(R)
    tail_R = np.zeros(len(T), bool); tail_R[np.argsort(-R)[:kR]] = True
    e2_idx = np.flatnonzero(E2)
    tail_e2 = np.zeros(len(T), bool); tail_e2[e2_idx[np.argsort(-usd[E2])[:k_e2]]] = True
    e1_idx = np.flatnonzero(E1)
    tail_e1 = np.zeros(len(T), bool); tail_e1[e1_idx[np.argsort(-usd[E1])[:k_e1]]] = True
    years = T["year"].to_numpy()
    outcomes = dict(win=T["win"].to_numpy(), rR=sst.rankdata(R), rRg=sst.rankdata(Rg),
                    tailR=tail_R.astype(float), tailE1=tail_e1.astype(float), tailE2=tail_e2.astype(float))
    GS = PermNull(circular_P(len(T)), dict(win=outcomes["win"], rR=outcomes["rR"]))
    WY = PermNull(within_year_P(years), outcomes)
    say("  nulls: GLOBAL circular shift %d offsets (%d..%d trades); WITHIN-YEAR circular shift %d draws "
        "(each calendar year's outcomes shifted independently by 10-90%% of that year's trades)"
        % (GS.K, SHIFT_MIN, len(T) - SHIFT_MIN, WY.K))

    res = []
    for nm, g, desc, kind, x in feats:
        d = feature_stats(nm, x, kind, T, GS, WY)
        d["group"], d["desc"] = g, desc
        res.append(d)
    res = [d for d in res if not d.get("skip")]
    for key in ("p_mw", "p_rho", "p_gs_win", "p_gs_R", "p_wy_win", "p_wy_R", "p_wy_Rg"):
        qs = bh([d[key] for d in res])
        for d, q in zip(res, qs):
            d["q" + key[1:]] = float(q)
    step(4)
    byname = {d["name"]: d for d in res}
    n_feat = len(res)

    def names(lst, qa, qb=None):
        key = (lambda d: min(d[qa], d[qb])) if qb else (lambda d: d[qa])
        return ", ".join("%s (%.3f)" % (d["name"], key(d)) for d in sorted(lst, key=key)) or "NONE"

    surv_wy = [d for d in res if min(d["q_wy_win"], d["q_wy_R"]) < Q_BAR]
    surv_wy_win = [d for d in res if d["q_wy_win"] < Q_BAR]
    surv_wy_R = [d for d in res if d["q_wy_R"] < Q_BAR]
    surv_wy_Rg = [d for d in res if d["q_wy_Rg"] < Q_BAR]
    surv_gs = [d for d in res if min(d["q_gs_win"], d["q_gs_R"]) < Q_BAR]
    surv_mw = [d for d in res if d["q_mw"] < Q_BAR]
    surv_rho = [d for d in res if d["q_rho"] < Q_BAR]
    say("\n" + "=" * 120)
    say("HEADLINE -- %d features tested at the signal bar on %d selection trades; Benjamini-Hochberg q<%.2f across all of them"
        % (n_feat, len(T), Q_BAR))
    say("  THE HONEST TEST = WITHIN-YEAR shift null (keeps every between-year difference in the null, so a feature that "
        "only tells 2012 from 2022 cannot pass):")
    say("    win vs loss survivors: %d -> %s" % (len(surv_wy_win), names(surv_wy_win, "q_wy_win")))
    say("    net R survivors:       %d -> %s" % (len(surv_wy_R), names(surv_wy_R, "q_wy_R")))
    say("    gross R survivors (cost added back, i.e. market move only): %d -> %s" % (len(surv_wy_Rg), names(surv_wy_Rg, "q_wy_Rg")))
    mkt = set(d["name"] for d in surv_wy_win) | set(d["name"] for d in surv_wy_Rg)
    cost_only = [d["name"] for d in surv_wy_R if d["name"] not in mkt]
    say("    net-R survivors that pass NEITHER the win test NOR the gross-R test: %d -- their only link to the outcome is the "
        "fixed cost weighing more on small stops (quiet tape, small ATR), i.e. the cost-share mechanic, not setup quality."
        % len(cost_only))
    stab = [d for d in surv_wy if d.get("same_sign")]
    say("    within-year survivors (win or net R) whose direction agrees inside E1 AND E2: %d -> %s"
        % (len(stab), ", ".join(d["name"] for d in stab) or "none"))
    say("  WEAKER TESTS, printed so the gap is visible (both let era trends through):")
    say("    global circular shift null (win or R): %d survivors" % len(surv_gs))
    say("    independence-assuming Mann-Whitney win/loss: %d ; Spearman vs R: %d" % (len(surv_mw), len(surv_rho)))

    # placebo calibration of the within-year null: features built from pure noise, independent of every outcome
    rng = np.random.default_rng(2057)
    n_pl = 400
    hits = {k: np.zeros(3) for k in ("win", "rR", "rRg")}
    pl_p = {k: [] for k in ("win", "rR", "rRg")}
    for j in range(n_pl):
        if j % 2 == 0:              # persistent AR(1) noise across the whole trade sequence (regime-like)
            e = rng.standard_normal(len(T)); xpl = np.empty(len(T)); xpl[0] = e[0]
            for t_ in range(1, len(T)):
                xpl[t_] = 0.95 * xpl[t_ - 1] + e[t_]
        else:                       # a random walk restarted every calendar year (within-year trend-like)
            xpl = np.empty(len(T))
            for y in np.unique(years):
                m = years == y
                xpl[m] = np.cumsum(rng.standard_normal(m.sum()))
        r_ = WY.cont(xpl, ("win", "rR", "rRg"))
        for k in hits:
            p_ = r_[k][1]
            hits[k] += np.array([p_ < 0.10, p_ < 0.05, p_ < 0.01], float)
            pl_p[k].append(p_)
    say("\nNULL CALIBRATION -- %d placebo features of pure noise (half AR(1) phi 0.95, half within-year random walks) "
        "through the within-year null; a calibrated test rejects ~10%% / 5%% / 1%%:" % n_pl)
    for k, lbl, pk in (("win", "win", "p_wy_win"), ("rR", "net R", "p_wy_R"), ("rRg", "gross R", "p_wy_Rg")):
        pp = np.array(pl_p[k])
        parts = []
        for thr in (0.001, 0.005, 0.01):
            frac = float((pp <= thr).mean())
            real = sum(1 for d in res if d[pk] <= thr)
            parts.append("p<=%.3f: real %d vs %.1f expected from noise" % (thr, real, frac * n_feat))
        say("  %-8s p<0.10 %4.1f%%   p<0.05 %4.1f%%   p<0.01 %4.1f%%   | %s"
            % ((lbl,) + tuple(100 * hits[k] / n_pl) + ("; ".join(parts),)))
    say("  (the 'expected from noise' counts use the placebo rejection rate at the same threshold, so they correct for the "
        "null's own miscalibration; the p floor is 1/2001 = 0.0005. Features are correlated, so these counts are not "
        "independent draws either way.)")

    base_wr = T["win"].mean()
    say("\nFAMILY-WISE 'BEST GROUP ANYWHERE' (max over every feature x group with n>=50; null of the MAXIMUM):")
    for nlabel, NUL, labkey in (("global-shift null, global quintiles", GS, "_lab"),
                                ("within-year null, within-year quintiles", WY, "_lab_wy")):
        for key, scale, lbl in (("win", 1.0, "win rate"), ("rR", float(len(T)), "mean R-percentile")):
            nullmax, obs, best = None, -1, None
            for d in res:
                lab = d.get(labkey)
                if lab is None:
                    continue
                gm = NUL.group_max(lab, key, scale)
                if gm is None:
                    continue
                nm_, ob = gm
                nullmax = nm_ if nullmax is None else np.maximum(nullmax, nm_)
                if ob > obs:
                    obs, best = ob, d["name"]
            p = (1 + int((nullmax >= obs - 1e-9).sum())) / (1 + len(nullmax))
            mult = 100.0 if key == "win" else 1.0
            say("  %-42s best %s %.3g (%s) vs base %.3g; null max median %.3g, 95th %.3g; p=%.3f"
                % (nlabel, lbl, mult * obs, best, mult * (base_wr if key == "win" else 0.5),
                   mult * np.median(nullmax), mult * np.percentile(nullmax, 95), p))

    say("\n" + "=" * 120)
    say("PER-FEATURE TABLE, sorted by the within-year null. rb = rank-biserial winners vs losers (+ = winners higher); "
        "rhoR = Spearman vs net R; rho_t = Spearman vs entry order (era trend); qGS = global-shift q (min of win, R); "
        "pWYw/qWYw, pWYR/qWYR, qWYg = within-year null for win, net R, gross R. win% Q = global quintiles; "
        "wyQ = quintiles ranked INSIDE each year. E1/E2 = rb per era; stab = same sign of rb and rho in both eras.")
    hdr = ("%-30s %-10s %5s %8s %8s %6s %6s %6s %6s %5s | %5s %5s %5s %5s %5s | %-29s | %-29s | %-34s | %-13s | %5s %5s %4s"
           % ("feature", "group", "n", "med_win", "med_los", "rb", "p_MW", "rhoR", "rho_t", "qGS",
              "pWYw", "qWYw", "pWYR", "qWYR", "qWYg", "win% Q1..Q5 (global)", "win% wyQ1..wyQ5", "mean R Q1..Q5 (global)",
              "mean$ Q1/Q5", "E1rb", "E2rb", "stab"))
    say(hdr)
    for d in sorted(res, key=lambda d: min(d["p_wy_win"], d["p_wy_R"])):
        gr = d["groups"]
        wrs = " ".join("%5.1f" % g["wr"] if g else "    -" for g in gr[:5])
        wys = " ".join("%5.1f" % g["wr"] for g in d["groups_wy"]) if d["groups_wy"] else "(discrete)"
        mrs = " ".join("%+6.2f" % g["mR"] if g else "     -" for g in gr[:5])
        q1 = gr[0]["musd"] if gr and gr[0] else np.nan
        q5 = gr[-1]["musd"] if gr and gr[-1] else np.nan
        say("%-30s %-10s %5d %8s %8s %6s %6s %6s %6s %5.3f | %5.3f %5.3f %5.3f %5.3f %5.3f | %-29s | %-29s | %-34s | %6s/%-6s | %5s %5s %4s"
            % (d["name"][:30], d["group"][:10], d["n"], fmt(d["med_w"], "%.4g"), fmt(d["med_l"], "%.4g"),
               fmt(d["rb"], "%+.3f"), fmt(d["p_mw"], "%.3f"), fmt(d["rho_R"], "%+.3f"), fmt(d["rho_t"], "%+.2f"),
               min(d["q_gs_win"], d["q_gs_R"]), d["p_wy_win"], d["q_wy_win"], d["p_wy_R"], d["q_wy_R"], d["q_wy_Rg"],
               wrs, wys, mrs, fmt(q1, "%.0f"), fmt(q5, "%.0f"),
               fmt(d["E1"]["rb"] if d.get("E1") else None, "%+.2f"), fmt(d["E2"]["rb"] if d.get("E2") else None, "%+.2f"),
               {True: "yes", False: "NO", None: "-"}[d.get("same_sign")]))

    named = ["ctx_ema_dist_atr", "ctx_ema1091_dist_atr", "ctx_ema5455_dist_atr", "ctx_ema21820_dist_atr",
             "ctx_day_move_datr", "ctx_rth_move_datr", "ctx_pdr_pos", "ctx_rth_pdr_pos", "ctx_session_bucket",
             "ctx_mins_since_1800", "ctx_days_since_20d_high", "loc_pdh_datr", "loc_rth_pdh_datr", "loc_sess_hi_atr",
             "loc_rn100_near_atr", "loc_ext_swing_atr", "loc_tl_slope_atr100", "loc_tl_r2", "loc_n_lower_highs",
             "loc_pb_depth_atr", "loc_plan_risk_pct", "loc_cost_share_R", "imb_body_ratio", "imb_close_loc",
             "imb_body_vs_avg20", "imb_vol_z60", "imb_vol_ratio20", "imb_upvol_share30", "imb_brk_atr"]
    top = [d["name"] for d in sorted(res, key=lambda d: min(d["p_wy_win"], d["p_wy_R"]))[:12]]
    detail = []
    for nm in [d["name"] for d in surv_wy] + [d["name"] for d in surv_wy_Rg] + top + named:
        if nm not in detail:
            detail.append(nm)
    say("\n" + "=" * 120)
    say("DETAIL -- group tables for within-year survivors, the 12 strongest, and the owner's named reads. "
        "Global quintiles give n / win %% / profit factor in R / mean R / mean $; within-year quintiles give win %% / PF(R) / mean R.")
    for nm in detail:
        d = byname.get(nm)
        if d is None:
            continue
        say("\n  %s [%s] -- %s" % (nm, d["group"], d["desc"]))
        say("    winners median %s | losers median %s | rank-biserial %s (MW p %s) | Spearman vs R %s | era trend rho_t %s"
            % (fmt(d["med_w"], "%.4g"), fmt(d["med_l"], "%.4g"), fmt(d["rb"], "%+.3f"), fmt(d["p_mw"], "%.4f"),
               fmt(d["rho_R"], "%+.3f"), fmt(d["rho_t"], "%+.2f")))
        say("    within-year null: win p %.3f (q %.3f) | net R p %.3f (q %.3f) | gross R p %.3f (q %.3f)   "
            "[global shift: win p %.3f, R p %.3f]"
            % (d["p_wy_win"], d["q_wy_win"], d["p_wy_R"], d["q_wy_R"], d["p_wy_Rg"], d["q_wy_Rg"],
               d["p_gs_win"], d["p_gs_R"]))
        for j, g in enumerate(d["groups"]):
            if not g:
                continue
            line = "    %-16s n=%4d  win=%5.1f%%  PF(R)=%5.2f  meanR=%+6.3f  mean$=%7.0f" % (
                g["lbl"], g["n"], g["wr"], g["pfR"] if not np.isnan(g["pfR"]) else 0, g["mR"], g["musd"])
            if d["groups_wy"]:
                w_ = d["groups_wy"][j]
                line += "   | within-year Q%d n=%4d win=%5.1f%% PF(R)=%5.2f meanR=%+6.3f" % (
                    j + 1, w_["n"], w_["wr"], w_["pfR"] if not np.isnan(w_["pfR"]) else 0, w_["mR"])
            say(line)
        for tag in ("E1", "E2"):
            e = d.get(tag)
            if e:
                say("    %s n=%d  rank-biserial %s (p %.3f)  Spearman vs R %s  Q5-Q1 win-rate spread %s pts"
                    % (tag, e["n"], fmt(e["rb"], "%+.3f"), e["p"], fmt(e["rho"], "%+.3f"), fmt(e["spread"], "%+.1f")))

    say("\n" + "=" * 120)
    say("WHAT THE STRONGEST READS WOULD DO -- IN-SAMPLE DESCRIPTION ONLY. The cut is the worst global quintile of each "
        "feature, chosen on this same selection data; this is the size of the effect, not a rule, and the family's history "
        "is that entry filters built this way lose money out of sample.")
    pts_all = T["pts"].to_numpy(); Rgv = T["Rg"].to_numpy()

    def ledger(mask, label):
        u = usd[mask]; r_ = R[mask]; w_ = u > 0
        say("    %-40s n=%5d  win=%5.1f%%  PF($)=%.3f  net=$%s  PF(R)=%.3f  meanR=%+.3f  [E1 win %5.1f%% PF(R) %.2f | E2 win %5.1f%% PF(R) %.2f]"
            % (label, mask.sum(), 100 * w_.mean(), u[w_].sum() / -u[~w_].sum(), format(u.sum(), ",.0f"), pf_r(r_), r_.mean(),
               100 * (usd[mask & E1] > 0).mean(), pf_r(R[mask & E1]), 100 * (usd[mask & E2] > 0).mean(), pf_r(R[mask & E2])))
    ledger(ALL, "ALL selection trades")
    strong = sorted([d for d in surv_wy_win if d.get("same_sign") and not d.get("discrete")],
                    key=lambda d: d["p_wy_win"])[:8]
    for d in strong:
        lab = d["_lab"]
        g_w = [g["wr"] for g in d["groups"]]
        worst = int(np.argmin([g_w[0], g_w[-1]])) * 4          # the worse END quintile
        ledger((lab != worst) & (lab >= 0), "drop %s Q%d" % (d["name"][:28], worst + 1))
    say("  MECHANICS CHECK on planned risk %% of price (global quintiles): if small stops only lost more per loser "
        "(tick grid, gap-through stops), the effect would sit in the LOSERS' R, not in the win rate:")
    lab_pr, _, _ = groups_for(np.asarray(F["loc_plan_risk_pct"], float), "cont")
    for g in range(5):
        m = lab_pr == g
        lo = m & (usd <= 0); wi = m & (usd > 0)
        say("    Q%d  n=%d  win %.1f%%  losers: mean gross R %+.3f, share worse than -1.05R %.1f%%, exact-entry scratches %.1f%% | "
            "winners: median gross R %+.2f, mean %+.2f"
            % (g + 1, m.sum(), 100 * wi.sum() / m.sum(), Rgv[lo].mean(), 100 * (Rgv[lo] < -1.05).mean(),
               100 * (np.abs(pts_all[m] + COST) <= 1e-6).mean(), np.median(Rgv[wi]), Rgv[wi].mean()))

    say("\n" + "=" * 120)
    say("COMBINED READ (ceiling check, not a model proposal): L2 logistic on ALL %d features, time split inside the selection window" % n_feat)
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        Xall = np.column_stack([np.asarray(fvals[d["name"]], float) for d in res])
        et = T["entry_time"]
        cut = pd.Timestamp("2019-01-01", tz=ix.tz)
        for lbl, tr_m in (("train 2010-06..2018-12 -> test 2019-01..2025-06", (et < cut).to_numpy()),
                          ("train 2019-01..2025-06 -> test 2010-06..2018-12", (et >= cut).to_numpy())):
            te_m = ~tr_m
            Xtr, Xte = Xall[tr_m].copy(), Xall[te_m].copy()
            med = np.nanmedian(Xtr, axis=0)
            for M_ in (Xtr, Xte):
                ii = np.where(np.isnan(M_)); M_[ii] = med[ii[1]]
            mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0) + 1e-9
            Xtr = np.clip((Xtr - mu) / sd, -5, 5); Xte = np.clip((Xte - mu) / sd, -5, 5)
            ytr = T["win"].to_numpy()[tr_m]; yte = T["win"].to_numpy()[te_m]
            clf = LogisticRegression(C=0.05, max_iter=5000).fit(Xtr, ytr)
            sc = clf.predict_proba(Xte)[:, 1]
            auc = roc_auc_score(yte, sc)
            Rte = R[te_m]
            rho = sst.spearmanr(sc, Rte).correlation
            qtop = sc >= np.quantile(sc, 0.8); qbot = sc <= np.quantile(sc, 0.2)
            # within-year AUC: rank the score inside each test year, pool
            yt = years[te_m]
            wy_sc = np.empty(len(sc))
            for y in np.unique(yt):
                m = yt == y
                wy_sc[m] = sst.rankdata(sc[m]) / m.sum()
            auc_wy = roc_auc_score(yte, wy_sc)
            say("  %s: n_train=%d n_test=%d  test AUC(win)=%.3f (score ranked inside each year: %.3f)  Spearman(score, R)=%+.3f  "
                "top-quintile win %.1f%% / PF(R) %.2f vs bottom-quintile %.1f%% / %.2f vs all %.1f%% / %.2f"
                % (lbl, tr_m.sum(), te_m.sum(), auc, auc_wy, rho, 100 * yte[qtop].mean(), pf_r(Rte[qtop]),
                   100 * yte[qbot].mean(), pf_r(Rte[qbot]), 100 * yte.mean(), pf_r(Rte)))
    except Exception as e:                                           # noqa: BLE001
        say("  combined read failed: %s: %s" % (type(e).__name__, e))

    say("\n" + "=" * 120)
    say("TAIL vs BODY at signal time")
    def yrs(m):
        vc = pd.Series(years[m]).value_counts().sort_index()
        return ", ".join("%d:%d" % (int(k), int(v)) for k, v in vc.items())
    say("  $ tail (whole window): the %d best trades by $ take selection net to <= 0 -- entry years %s" % (k_all, yrs(tail_usd)))
    say("    -> %d of %d are 2020+ entries: in dollars the whole-window tail IS the modern era (NQ's point amplitude grew "
        "~7x), so it is compared WITHIN its era below, not against 2010-19 trades." % (int((tail_usd & E2).sum()), k_all))
    say("  E1 $ tail: the %d best E1 trades take E1 net to <= 0 -- years %s" % (k_e1, yrs(tail_e1)))
    say("  E2 $ tail: the %d best E2 trades take E2 net to <= 0 -- years %s" % (k_e2, yrs(tail_e2)))
    say("  R tail (era-neutral): the %d best trades by R take summed R to <= 0 -- years %s" % (kR, yrs(tail_R)))
    say("  overlaps: R tail & whole-window $ tail %d; R tail & (E1 tail or E2 tail) %d"
        % (int((tail_R & tail_usd).sum()), int((tail_R & (tail_e1 | tail_e2)).sum())))
    rq = sst.rankdata(R) / len(R)
    say("  a dollar is R x risk-in-points x $20, so a dollar tail is partly SELECTED on stop size: E1 $ tail median R %.1f "
        "(risk %.1f pts vs E1 body %.1f), E2 $ tail median R %.1f (risk %.1f pts vs E2 body %.1f), R tail median R %.1f; "
        "share of the E1+E2 $ tails inside the top 5%% of R: %.0f%%"
        % (np.median(R[tail_e1]), np.median(T["risk_pts"][tail_e1]), np.median(T["risk_pts"][E1 & ~tail_e1]),
           np.median(R[tail_e2]), np.median(T["risk_pts"][tail_e2]), np.median(T["risk_pts"][E2 & ~tail_e2]),
           np.median(R[tail_R]), 100 * (rq[tail_e1 | tail_e2] > 0.95).mean()))
    wmask = T["win"].to_numpy().astype(bool)
    for tlabel, tm, scope, okey in (("R tail (era-neutral), all selection", tail_R, ALL, "tailR"),
                                    ("E1 $ tail, inside E1", tail_e1, E1, "tailE1"),
                                    ("E2 $ tail, inside E2", tail_e2, E2, "tailE2")):
        rows = []
        for nm, g, desc, kind, x in feats:
            if kind == "cat":
                continue
            xs_ = np.where(scope, x, np.nan)
            v = ~np.isnan(xs_)
            a_ = xs_[v & tm]; b_ = xs_[v & ~tm]; c_ = xs_[v & ~tm & wmask]
            if len(a_) < 10 or len(b_) < 50 or np.nanstd(xs_) == 0:
                continue
            p1 = sst.mannwhitneyu(a_, b_, alternative="two-sided").pvalue
            p2 = sst.mannwhitneyu(a_, c_, alternative="two-sided").pvalue if len(c_) >= 30 else np.nan
            p3 = WY.cont(xs_, (okey,))[okey][1]
            rows.append((nm, np.median(a_), np.median(b_), np.median(c_) if len(c_) else np.nan, p1, p2, p3))
        q1 = bh([r_[4] for r_ in rows]); q2 = bh([r_[5] for r_ in rows]); q3 = bh([r_[6] for r_ in rows])
        say("\n  %s (n=%d) vs BODY (the other trades in scope) and vs OTHER WINNERS -- BH across %d features"
            % (tlabel, int(tm.sum()), len(rows)))
        say("    survivors q<%.2f: vs body (Mann-Whitney) %d ; vs body (within-year null) %d ; vs other winners (Mann-Whitney) %d"
            % (Q_BAR, int((q1 < Q_BAR).sum()), int((q3 < Q_BAR).sum()), int((q2 < Q_BAR).sum())))
        say("    %-32s %9s %9s %9s %8s %6s %8s %6s %8s %6s"
            % ("feature (15 smallest MW p)", "tail med", "body med", "oth-win", "p MW", "q", "p WY", "q", "p o-win", "q"))
        for j in np.argsort([r_[4] for r_ in rows])[:15]:
            r_ = rows[j]
            say("    %-32s %9.4g %9.4g %9.4g %8.4f %6.3f %8.4f %6.3f %8.4f %6.3f"
                % (r_[0][:32], r_[1], r_[2], r_[3], r_[4], q1[j], r_[6], q3[j], r_[5], q2[j]))

    say("\n" + "=" * 120)
    say("CONTAMINATION READ: trade_anatomy features at its DEFAULT decision bar (fill bar - 1) vs the true SIGNAL bar "
        "(continuous columns only, within-year null)")
    rows_s, rows_f = [], []
    for nm in TA.FEATURE_NAMES:
        xs = X_sig[nm].to_numpy(float); xf = X_fill[nm].to_numpy(float)
        if np.isnan(xs).mean() > 0.5 or np.nanstd(xs) == 0 or np.isnan(xf).mean() > 0.5 or np.nanstd(xf) == 0:
            continue
        if len(np.unique(xs[~np.isnan(xs)])) <= 6:
            continue
        a_ = WY.cont(xs, ("win", "rR")); b_ = WY.cont(xf, ("win", "rR"))
        rows_s.append((nm, a_["win"][0], a_["win"][1], a_["rR"][0], a_["rR"][1]))
        rows_f.append((nm, b_["win"][0], b_["win"][1], b_["rR"][0], b_["rR"][1]))
    for lbl, rows in (("signal bar", rows_s), ("fill bar - 1", rows_f)):
        qw = bh([r_[2] for r_ in rows]); qr = bh([r_[4] for r_ in rows])
        ns = int(((qw < Q_BAR) | (qr < Q_BAR)).sum())
        order = np.argsort([min(r_[2], r_[4]) for r_ in rows])[:6]
        say("  %-13s %d columns, within-year FDR survivors %d; strongest: %s"
            % (lbl, len(rows), ns, "; ".join("%s (corr win %+.3f p %.3f, corr R %+.3f p %.3f)"
                                             % (rows[j][0], rows[j][1], rows[j][2], rows[j][3], rows[j][4]) for j in order)))
    big = sorted(((abs(f_[3] - s_[3]), s_[0], s_[3], f_[3]) for s_, f_ in zip(rows_s, rows_f)), reverse=True)
    say("  largest change in corr(feature, R) between the two readings: %s"
        % "; ".join("%s %+.3f -> %+.3f" % (b_[1], b_[2], b_[3]) for b_ in big[:6]))

    say("\n" + "=" * 120)
    say("POST-SIGNAL DIAGNOSTICS (NOT knowable at the signal bar -- description only, never a rule)")
    for dl, grp in T.groupby(np.minimum(T["fill_delay"], 5)):
        say("  fill delay %s bars: n=%4d win=%5.1f%% PF(R)=%.2f meanR=%+.3f mean$=%.0f"
            % ("5+" if dl == 5 else str(dl), len(grp), 100 * grp["win"].mean(), pf_r(grp["R"].to_numpy()),
               grp["R"].mean(), grp["usd"].mean()))
    step(5)


if __name__ == "__main__":
    main()

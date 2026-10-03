"""BOOK round 62 V3 - a learned risk forecast in place of V2's trailing 20-day volatility (FRONTIER lane, 2026-10-02).
Pre-run review fixes 2026-10-03 (save before the tail, provenance, read-once; no spec change).

Owner ask (2026-10-02): "continue to push the frontier models of edgelog and beat them. might have to use an ML".
Pre-registration: docs/PREREG_frontier_v3_riskml_2026-10-02.txt. The registered run REFUSES unless that file's canonical (LF)
sha256 equals PREREG_SHA below (the hash committed with it), so a changed spec has to be a new file.

What it does, in order (it stops at the first thing that fails):
  0. Runs #463's four job legs (api/book_shadow.BOOK463_LEGS) on their pinned masters, keeps every trade's own valued-daily
     increments at size 1, and rebuilds #463's valued-daily book from them.
  1. PARITY: that rebuild must equal api/book_shadow.book463_valued_daily to the cent ON THE SAME DAY INDEX, the V2 multipliers
     built here must equal api/book_shadow.vt_multipliers on that series, and #463 must read the references
     tools/rocfrontier/r10_spread.py reproduces (WF 93.81 / LB 155.54 %/yr at a $30k drawdown, Sortino 3.816 / 4.150,
     drawdowns $44,849 / $49,855, LB without its biggest trade $167,144; BOOK.md 10r prints them rounded).
  2. STEP 1 (IS only): walk-forward forecasts of the next 5 index days of book risk - NAIVE (V2's information), RIDGE, GBM -
     scored on what the sizing rule actually uses: each forecast relative to its own trailing-year median, against realised
     risk relative to its own trailing-year median. RIDGE (pre-specified; GBM is scored and reported but can never be
     swapped in) must beat NAIVE by >= 5% and a one-sided Diebold-Mariano test (rectangular kernel, 4 lags,
     Harvey-Leybourne-Newbold correction, t(n-1), p < 0.05). A fail ends the round: WF / LB book numbers are NOT computed.
  3. STEP 2: re-sizes every trade by m(its ET entry date) for V2 and V3, scores WF and LB on the owner yardstick, runs the
     delay and the aim checks, prints the RUNBOARD-style table, the sensitivity rows (report only) and the verdict.
Outputs: <out>/v3_result.json and <out>/v3_daily_multipliers.csv (the series a forward shadow line would read), written as
soon as the registered evaluation ends - before the optional --tail-to pass, which then rewrites the JSON with its INFO row.
v3_result.json records the prereg and harness hashes and the git HEAD. READ ONCE: a registered run refuses, before any engine
build, when <out>/v3_result.json already holds the result table (the lockbox was printed); move that file aside deliberately.

Run from the SHARED checkout (the master registry lives there), CPU only:
    set AUGUR_TRIAL_CACHE=1 & set OMP_NUM_THREADS=1
    python tools/frontier_v3_riskml.py                         # the registered run
    python tools/frontier_v3_riskml.py --tail-to 2026-10-01    # + the fresh 2026-07-01.. tail as an INFO row
Self-test without any master (synthetic data, checks causality and the arithmetic): python tools/frontier_v3_riskml.py --selftest
Nothing here places an order or changes a strategy file; the only Firestore write is the research beacon's progress record
(tools/research_beacon.py, so the run shows on the dials), and the run continues without it if the beacon cannot start.
"""
import argparse
import contextlib
import hashlib
import json
import math
import os
import sys
import time

_HERE = os.path.abspath(__file__)                 # captured before the chdir below (the harness hash in the provenance)
if "--selftest" not in sys.argv:
    ROOT = os.environ.setdefault("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    if sys.path[0] != ROOT:
        sys.path.insert(0, ROOT)
    os.chdir(ROOT)
else:                                     # self-test: the repo this file sits in, so api.book_shadow is the real one
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _here not in sys.path:
        sys.path.insert(0, _here)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

# ---- registered constants (PREREG_frontier_v3_riskml_2026-10-02.txt) - never change these after the prereg is committed ----
W0, W1 = "2010-06-07", "2026-06-30"
IS1 = pd.Timestamp("2016-06-30")
WF0, WF1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
LB0, LB1 = pd.Timestamp("2025-06-30"), pd.Timestamp("2026-06-30")
TAIL0 = pd.Timestamp("2026-07-01")
HORIZON, REF_WIN, LO, HI = 5, 250, 0.5, 2.0
MIN_TRAIN, REFIT = 500, 63
MSE_EDGE, DM_P = 0.95, 0.05
PRIMARY = "ridge"                                  # pre-specified; GBM is a reported challenger only
MAX_STALE_BDAYS = 1                              # a feature older than this many missing business days is blanked
NSHUF, SEED = 1000, 20261002
NQ_MKT = ("NQ", "5m", "rth", "db_adj_rth")       # the ORB leg's master
ES_MKT = ("ES", "30m", "rth", "db_adj_rth")      # the TTM leg's master
PREREG = os.path.join("docs", "PREREG_frontier_v3_riskml_2026-10-02.txt")
PREREG_SHA = "41b4bb910819938c59dd75e818d66d12e9b399519e1c6dba9837c7a21406bbb8"   # canonical (LF) sha256 of the pre-registration as committed
# #463 on the 10-01 convention, as tools/rocfrontier/r10_spread.py reproduces it (BOOK.md 10r prints these rounded)
REF463 = {"WF": {"roc30": 93.81, "sortino": 3.816, "dd": 44849.0}, "LB": {"roc30": 155.54, "sortino": 4.150, "dd": 49855.0}}
REF_TOL = {"roc30": 0.006, "sortino": 0.0006, "dd": 1.0}
REF463_LB_WO_BIGGEST, WO_BIGGEST_TOL = 167144.0, 150.0     # BOOK.md 10r
REF_R62_OLD = {"463": {"WF": 92.7}, "V2": {"WF": 116.1, "LB": 259.3}}   # BOOK.md 10o, old ROC convention, soft check
EPISODES = (("2020 crash", "2020-02-15", "2020-04-30"), ("June 2026 ENGU-Q", "2026-06-01", "2026-06-30"))
FEATURES = ("b1", "b5", "b20", "b60", "nq1", "nq5", "nq22", "es1", "es5", "nqtrend20")
NAIVE_FEATURES = ("b20",)
KINDS = ("naive", "ridge", "gbm")


# ============================================================ engine layer (needs the shared checkout's masters)
def _legs463():
    from api.book_shadow import BOOK463_LEGS
    return [dict(l) for l in BOOK463_LEGS]


def run_leg(leg, d0, d1):
    """One leg, exactly as augur_engine.book._leg_trades runs it, but every trade's valued-daily increments kept apart.

    Two day stamps per trade: the book's UTC-truncated stamp (every series and stretch uses it, as every book run does) and
    the ET calendar date of the fill bar (the SIZE key; see Book)."""
    from augur_engine import book
    from augur_engine.engine import run_backtest
    m = book.find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    if m is None or str(m.get("source")) != leg["source"]:
        raise SystemExit(f"PARITY STOP: no pinned master for {leg['strategy']} ({leg['source']}) - refusing any fallback")
    if leg.get("gate"):
        raise SystemExit("PARITY STOP: a #463 leg carries a gate block; this driver sizes ungated legs only")
    arr = book.load_master_arrays(m, date_from=d0, date_to=d1)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {},
                       cost_pts=float(leg.get("cost_pts", 0) or 0), return_trades=True)
    if not isinstance(res, dict):
        raise SystemExit(f"PARITY STOP: {leg['strategy']} returned no result on {leg['source']} {d0}..{d1}")
    trades = list(res.get("trades") or [])
    mult, weight = book._leg_mult(leg), float(leg.get("weight", 1) or 1)
    pm, usd_units, _note = book._plugin_marks(leg, arr, [(t, 1.0) for t in trades])
    days_idx = np.asarray(arr["index"], dtype="datetime64[D]")
    di = pd.DatetimeIndex(arr["index"])
    et_idx = (np.asarray(di.tz_localize(None).normalize().values, dtype="datetime64[D]") if di.tz is not None else days_idx)
    last = len(days_idx) - 1
    tr_entry, tr_et, tr_exit, tr_usd, inc_tid, inc_day, inc_usd = [], [], [], [], [], [], []
    for t in trades:
        try:
            e = min(max(int(t[0]), 0), last)
            x = min(int(t[1]), last)
            usd = float(t[2]) * mult * weight
        except Exception:
            continue                                   # the engine drops the same trades
        incs, _mk, _um = book._mtm_increments(days_idx, arr.get("close"), [(t, 1.0)], mult, weight,
                                              plugin_marks=pm, usd_units=usd_units)
        k = len(tr_usd)
        tr_entry.append(days_idx[e])
        tr_et.append(et_idx[e])
        tr_exit.append(days_idx[x])
        tr_usd.append(usd)
        for d, v in incs:
            inc_tid.append(k)
            inc_day.append(d)
            inc_usd.append(v)
    return {"strategy": leg["strategy"], "tr_entry": np.array(tr_entry, dtype="datetime64[D]"),
            "tr_entry_et": np.array(tr_et, dtype="datetime64[D]"),
            "tr_exit": np.array(tr_exit, dtype="datetime64[D]"), "tr_usd": np.array(tr_usd, float),
            "inc_tid": np.array(inc_tid, int), "inc_day": np.array(inc_day, dtype="datetime64[D]"),
            "inc_usd": np.array(inc_usd, float), "days_present": np.unique(et_idx)}


def market_daily(spec, d0, d1):
    """Per day stamp (UTC-truncated, as the book): high-low range in points and last close of the RTH session."""
    from augur_engine import book
    inst, tf, sess, src = spec
    m = book.find_master(inst, tf, sess, src)
    if m is None or str(m.get("source")) != src:
        raise SystemExit(f"PARITY STOP: no {inst} {tf} {sess} {src} master for the market features")
    arr = book.load_master_arrays(m, date_from=d0, date_to=d1)
    return daily_from_bars(np.asarray(arr["index"], dtype="datetime64[D]"), arr["high"], arr["low"], arr["close"])


def daily_from_bars(days, high, low, close):
    df = pd.DataFrame({"d": days, "h": np.asarray(high, float), "l": np.asarray(low, float), "c": np.asarray(close, float)})
    g = df.groupby("d", sort=True).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    g.index = pd.DatetimeIndex(np.asarray(g.index, dtype="datetime64[D]").astype("datetime64[ns]"))
    return pd.DataFrame({"rng": (g["h"] - g["l"]).clip(lower=0.25), "close": g["c"]})


# ============================================================ book assembly (pure numpy from here on)
class Book:
    """All legs' trades in one table; every per-trade size vector s maps to a valued-daily series by one bincount.

    SIZE KEY. A trade is sized by m at position p = the number of index days strictly before the ET calendar date of its fill.
    Index days are the book's UTC-truncated stamps, so every row before ET date X ended by 20:00 ET (19:00 in winter) on X-1,
    before any fill dated X. A Sunday-evening ENGU-Q fill is dated Sunday and reads rows through UTC Saturday. A forward line
    must use the same key: m at the first index row dated on or after the fill's ET date - never a report day's multiplier
    (the nightly report books money on the EXIT day, and a Monday multiplier reads the UTC-Sunday row)."""

    def __init__(self, legruns, d0, d1):
        days = pd.DatetimeIndex(pd.bdate_range(d0, d1))
        for r in legruns:
            days = days.union(pd.DatetimeIndex(np.unique(r["inc_day"]).astype("datetime64[ns]")))
        self.index = days.unique().sort_values()
        assert self.index.is_unique and self.index.is_monotonic_increasing
        iv = self.index.values
        off = 0
        ent, et, ex, usd, it, ip, iu = [], [], [], [], [], [], []
        for r in legruns:
            ent.append(r["tr_entry"]); et.append(r.get("tr_entry_et", r["tr_entry"])); ex.append(r["tr_exit"])
            usd.append(r["tr_usd"])
            it.append(r["inc_tid"] + off)
            ip.append(np.searchsorted(iv, r["inc_day"].astype("datetime64[ns]")))
            iu.append(r["inc_usd"])
            off += len(r["tr_usd"])
        cat = lambda a, dt=None: np.concatenate(a) if a else np.array([], dtype=dt)
        to_idx = lambda a: pd.DatetimeIndex(cat(a, "datetime64[D]").astype("datetime64[ns]"))
        self.tr_entry, self.tr_key, self.tr_exit = to_idx(ent), to_idx(et), to_idx(ex)
        self.tr_usd = cat(usd, float)
        self.tr_pos = np.searchsorted(iv, self.tr_key.values, side="left")
        self.inc_tid, self.inc_pos, self.inc_usd = cat(it, int), cat(ip, int), cat(iu, float)
        self.N = len(self.index)
        self.legs = [r["strategy"] for r in legruns]
        assert (self.tr_key <= self.tr_entry).all(), "an ET entry date after its UTC stamp"

    def series(self, s):
        """Valued-daily book P&L for per-trade sizes s (len = trades)."""
        return np.bincount(self.inc_pos, weights=self.inc_usd * s[self.inc_tid], minlength=self.N)

    def sizes(self, m_by_pos):
        return np.asarray(m_by_pos, float)[np.minimum(self.tr_pos, self.N - 1)]


# ============================================================ multipliers
def _vt_fallback(S):
    vol = S.shift(1).rolling(20, min_periods=20).std()
    ref = vol.shift(1).rolling(250, min_periods=125).median()
    return (ref / vol).clip(0.5, 2.0).round(1).fillna(1.0)


def v2_multipliers(M, index):
    """V2 exactly as the nightly VT line computes it (api/book_shadow.vt_multipliers), on the book's own index."""
    try:
        from api.book_shadow import vt_multipliers
    except Exception:
        vt_multipliers = _vt_fallback
    return vt_multipliers(pd.Series(M, index=index)).to_numpy(float)


def ratio_multipliers(S, ref_win=REF_WIN, lo=LO, hi=HI):
    """V2's scale-free rule with a forecast S in place of vol20: m(p) = clip(median S over the ref_win positions before p / S(p))."""
    s = pd.Series(np.asarray(S, float))
    ref = s.shift(1).rolling(ref_win, min_periods=ref_win // 2).median()
    return (ref / s).clip(lo, hi).round(1).fillna(1.0).to_numpy(float)


def forecast_dollars(F):
    """Log forecast -> dollar RMS, floored at $1 (a forecast that small is clipped to the 2.0 cap anyway)."""
    S = np.maximum(np.expm1(F), 1.0)
    S[~np.isfinite(F)] = np.nan
    return S


# ============================================================ features, target, walk-forward forecaster
def book_features(M):
    s = pd.Series(np.asarray(M, float))
    sq = s * s
    rms = lambda w: np.log1p(np.sqrt(sq.rolling(w, min_periods=w).mean())).shift(1)
    return pd.DataFrame({"b1": np.log1p(s.abs()).shift(1), "b5": rms(5), "b20": rms(20), "b60": rms(60)})


def market_features(index, nq, es, stats=None):
    """Row p uses only market days strictly before index[p], and only if that day is at most MAX_STALE_BDAYS business days
    behind the previous business day (a stalled master blanks the feature instead of carrying it forward).
    Scale-free of the back-adjustment: ranges are within-day differences and the trend is a 20-day point change in units of
    the 22-day mean range. A new roll (a constant shift of all history) leaves them unchanged; a re-estimated offset inside the
    window shifts only the bars before it and moves the trend for the ~20 market days after it (ranges are untouched)."""
    def prep(mk):
        lr = np.log(mk["rng"])
        trend = (mk["close"] - mk["close"].shift(20)) / mk["rng"].rolling(22, min_periods=22).mean()
        return pd.DataFrame({"r1": lr, "r5": lr.rolling(5, min_periods=5).mean(), "r22": lr.rolling(22, min_periods=22).mean(),
                             "trend20": trend}, index=mk.index)
    out = pd.DataFrame(index=range(len(index)))
    d = np.asarray(index.values, dtype="datetime64[D]")
    for name, mk, cols in (("nq", nq, (("nq1", "r1"), ("nq5", "r5"), ("nq22", "r22"), ("nqtrend20", "trend20"))),
                           ("es", es, (("es1", "r1"), ("es5", "r5")))):
        f = prep(mk)
        row = np.searchsorted(f.index.values, index.values, side="left") - 1
        ok = row >= 0
        mday = np.asarray(f.index.values, dtype="datetime64[D]")
        gap = np.full(len(index), 10 ** 6)
        gap[ok] = np.busday_count(mday[row[ok]] + 1, d[ok])      # business days missing in (market day, index day - 1]
        ok &= gap <= MAX_STALE_BDAYS
        if stats is not None:
            stats[name + "_stale_rows"] = int(((row >= 0) & ~ok).sum())
        for col, src in cols:
            v = np.full(len(index), np.nan)
            v[ok] = f[src].to_numpy()[row[ok]]
            out[col] = v
    return out


def target(M, h):
    """y(p) = log(1 + RMS of M over positions p..p+h-1); NaN where the window runs past the end.

    Known limitation (pre-run review 2026-10-03, left as registered): the reversed rolling mean is an online sum run from the
    END of the series, so y(q) carries floating-point error (~1e-7 in log units) from later rows. No information leaks - the
    value is mathematically the same - but forecasts are not bit-identical when the window is extended (tail, nightly line)."""
    sq = pd.Series(np.asarray(M, float) ** 2)
    fwd = sq[::-1].rolling(h, min_periods=h).mean()[::-1]
    return np.log1p(np.sqrt(fwd.to_numpy()))


def make_model(kind, seed=0):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if kind in ("naive", "ridge"):
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if kind == "gbm":
        return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_depth=3, min_samples_leaf=40,
                                             l2_regularization=1.0, early_stopping=False, random_state=seed)
    raise ValueError(kind)


def first_refit(X, y, h, min_train=MIN_TRAIN):
    """Earliest refit position at which min_train rows have their whole target known (q + h <= r), or None."""
    trainable = np.isfinite(np.asarray(X, float)).all(axis=1) & np.isfinite(np.asarray(y, float))
    cum = np.cumsum(trainable)
    return int(np.argmax(cum >= min_train)) + h if (cum >= min_train).any() else None


def walk_forward(X, y, kind, h, r_start, refit=REFIT, seed=0, embargo=None):
    """Expanding-window forecasts. A refit at position r trains on rows q with q + h <= r (whole target known before r) and
    forecasts positions r .. r+refit-1. `embargo` exists only so the self-test can prove a weaker one is caught."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    N = len(y)
    F = np.full(N, np.nan)
    if r_start is None:
        return F, []
    okx = np.isfinite(X).all(axis=1)
    trainable = okx & np.isfinite(y)
    pos = np.arange(N)
    emb = h if embargo is None else embargo
    r, refits = int(r_start), []
    while r < N:
        tr = trainable & (pos + emb <= r)
        if embargo is None:
            assert (pos[tr] + h - 1 < r).all(), "a training target reaches the refit position"
        mdl = make_model(kind, seed)
        mdl.fit(X[tr], y[tr])
        hi = min(r + refit, N)
        sel = np.arange(r, hi)[okx[r:hi]]
        if len(sel):
            F[sel] = mdl.predict(X[sel])
        refits.append(r)
        r = hi
    return F, refits


def feature_frame(M, mkt_feats):
    return pd.concat([book_features(M), mkt_feats.reset_index(drop=True)], axis=1)


def forecasts(M, mkt_feats, h, kinds=KINDS, min_train=MIN_TRAIN, refit=REFIT, embargo=None):
    """Walk-forward forecasts for each model, ALL refit on one schedule (the latest of their individual first refits)."""
    feats = feature_frame(M, mkt_feats)
    y = target(M, h)
    Xs = {k: feats[list(NAIVE_FEATURES if k == "naive" else FEATURES)].to_numpy(float) for k in KINDS}
    starts = [first_refit(Xs[k], y, h, min_train) for k in KINDS]
    r0 = None if any(s is None for s in starts) else max(starts)
    out, refits = {}, []
    for k in kinds:
        out[k], refits = walk_forward(Xs[k], y, k, h, r0, refit=refit, embargo=embargo)
    return out, y, refits


def relative_errors(F, y, h, ref_win=REF_WIN):
    """What the sizing rule uses: log(S / median S of the prior ref_win positions) for the forecast, against
    log(R / median R of the ref_win positions whose targets were known before p) for the realised 5-day RMS R.
    Any slow level bias in S cancels here exactly as it cancels in m = REF / S, and both sides are clipped at +-log 2, the
    0.5-2.0 band the rule can act on, so quiet holiday weeks cannot dominate the score."""
    S = pd.Series(forecast_dollars(F))
    rel_f = np.log(S / S.shift(1).rolling(ref_win, min_periods=ref_win // 2).median()).to_numpy()
    R = pd.Series(np.maximum(np.expm1(np.asarray(y, float)), 1.0))
    R[~np.isfinite(np.asarray(y, float))] = np.nan
    rel_y = np.log(R / R.shift(h).rolling(ref_win, min_periods=ref_win // 2).median()).to_numpy()
    c = math.log(HI)
    return np.clip(rel_f, -c, c) - np.clip(rel_y, -c, c)


def dm_test(e_base, e_model, h=HORIZON):
    """One-sided Diebold-Mariano on squared errors, H1 = the model's loss is lower. Rectangular kernel with h-1 lags (the
    overlap of h-day targets), Bartlett if that variance is not positive, Harvey-Leybourne-Newbold small-sample factor,
    p from Student t with n-1 df. Returns (statistic, p)."""
    d = np.asarray(e_base, float) ** 2 - np.asarray(e_model, float) ** 2
    n = len(d)
    if n < 30:
        return float("nan"), float("nan")
    dc = d - d.mean()
    gam = [float(dc[k:] @ dc[:n - k]) / n for k in range(h)]
    v = gam[0] + 2.0 * sum(gam[1:])
    if v <= 0:
        v = gam[0] + 2.0 * sum((1.0 - k / h) * gam[k] for k in range(1, h))
    if v <= 0:
        return float("nan"), float("nan")
    stat = d.mean() / math.sqrt(v / n) * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    try:
        from scipy.stats import t as _t
        p = float(_t.sf(stat, n - 1))
    except Exception:
        p = 0.5 * math.erfc(stat / math.sqrt(2.0))
    return float(stat), p


def step1(index, F, y, h, is_end=IS1):
    """IS-only forecast gate on relative errors. Positions whose whole target lies inside IS and every model is scored."""
    last_is = int(np.searchsorted(index.values, np.datetime64(is_end), side="right")) - 1
    E = {k: relative_errors(F[k], y, h) for k in F}
    p = np.arange(len(y))
    sel = p + h - 1 <= last_is
    for k in E:
        sel &= np.isfinite(E[k])
    mse = {k: float(np.mean(E[k][sel] ** 2)) if sel.any() else float("nan") for k in E}
    chosen = PRIMARY
    stat, pval = dm_test(E["naive"][sel], E[chosen][sel], h)
    ratio = mse[chosen] / mse["naive"] if mse["naive"] > 0 else float("nan")
    g_stat, g_p = dm_test(E["naive"][sel], E["gbm"][sel], h) if "gbm" in E else (float("nan"), float("nan"))
    ok = bool(np.isfinite(ratio) and ratio <= MSE_EDGE and np.isfinite(pval) and pval < DM_P)
    return {"n": int(sel.sum()), "mse": mse, "chosen": chosen, "ratio": ratio, "dm_stat": stat, "dm_p": pval, "pass": ok,
            "gbm_info": {"ratio": mse.get("gbm", float("nan")) / mse["naive"] if mse["naive"] > 0 else float("nan"),
                         "dm_stat": g_stat, "dm_p": g_p},
            "from": str(index[p[sel][0]].date()) if sel.any() else None,
            "to": str(index[p[sel][-1]].date()) if sel.any() else None}


def forecast_skill(index, F, y, h, a, b):
    """Diagnostic only: relative-error MSE per model inside [a, b] (targets wholly inside)."""
    k_in = (index >= a) & (index <= b)
    last = np.flatnonzero(k_in)
    if not len(last):
        return {}
    E = {k: relative_errors(F[k], y, h) for k in F}
    p = np.arange(len(y))
    sel = k_in & (p + h - 1 <= last[-1])
    for k in E:
        sel &= np.isfinite(E[k])
    return {k: float(np.mean(E[k][sel] ** 2)) for k in E} if sel.any() else {}


# ============================================================ scoring (the owner yardstick, BOOK.md 10r convention)
def _dd(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(x) else 0.0


def _so(x):
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stretch(bk, M, s, a, b):
    k = (bk.index >= a) & (bk.index <= b)
    x = M[k]
    dates = bk.index[k]
    net = float(x.sum())
    yrs = max((dates[-1] - dates[0]).days, 1) / 365.25 if len(dates) else float("nan")
    dd = _dd(x)
    ex = (bk.tr_exit >= a) & (bk.tr_exit <= b)
    usd = bk.tr_usd * s
    closed = float(usd[ex].sum())
    old_yrs = ((b - a).days + 1) / 365.25
    ent = (bk.tr_key >= a) & (bk.tr_key <= b)
    return {"net": net, "dd": dd, "roc30": net / yrs / 1000.0 * 30000.0 / dd if dd > 0 else float("nan"),
            "roc30_old": closed / old_yrs / 1000.0 * 30000.0 / dd if dd > 0 else float("nan"),
            "sortino": _so(x), "trades": int(ex.sum()),
            "wo_biggest": net - float(usd[ex].max()) if ex.any() else float("nan"),
            "avg_size": float(np.mean(s[ent])) if ent.any() else float("nan")}


def window_dd(bk, M, a, b):
    k = (bk.index >= pd.Timestamp(a)) & (bk.index <= pd.Timestamp(b))
    return _dd(M[k])


def per_year(bk, M, y0=2011, y1=2025):
    out = {}
    for y in range(y0, y1 + 1):
        k = (bk.index >= pd.Timestamp(f"{y}-01-01")) & (bk.index <= pd.Timestamp(f"{y}-12-31"))
        x = M[k]
        out[y] = float(x.sum()) / max(_dd(x), 1.0)
    return out


def aim_pct(bk, m_by_pos, a, b, actual, how, n=NSHUF, seed=SEED):
    """Percentile of `actual` (ROC at $30k in [a, b]) among n re-timings of the daily multipliers inside the stretch.
    how = "shift": circular shifts (keeps the multipliers' persistence - the registered AIM null);
          "shuffle": independent day shuffles (reported only)."""
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero((bk.index >= a) & (bk.index <= b))
    if len(pos) < 3:
        return float("nan")
    base = np.asarray(m_by_pos, float)
    null = np.empty(n)
    for i in range(n):
        m = base.copy()
        m[pos] = np.roll(base[pos], int(rng.integers(1, len(pos)))) if how == "shift" else rng.permutation(base[pos])
        s = bk.sizes(m)
        null[i] = stretch(bk, bk.series(s), s, a, b)["roc30"]
    return float(100.0 * np.mean(null < actual))


# ============================================================ the run
def evaluate(bk, mkt, verbose=True, min_train=MIN_TRAIN, refit=REFIT, windows=None, ref_check=True):
    w = windows or {"IS1": IS1, "WF0": WF0, "WF1": WF1, "LB0": LB0, "LB1": LB1}
    say = print if verbose else (lambda *a, **k: None)
    res = {"legs": bk.legs, "trades": int(len(bk.tr_usd)), "index_days": bk.N}
    ones = np.ones(len(bk.tr_usd))
    M1 = bk.series(ones)

    # --- PARITY (numbers): #463 on the registered yardstick
    base = {st: stretch(bk, M1, ones, w[st + "0"], w[st + "1"]) for st in ("WF", "LB")}
    res["parity_463"] = base
    say("PARITY #463: WF %.2f / LB %.2f %%/yr at $30k, Sortino %.3f / %.3f, DD $%s / $%s, LB without biggest $%s" % (
        base["WF"]["roc30"], base["LB"]["roc30"], base["WF"]["sortino"], base["LB"]["sortino"],
        f"{base['WF']['dd']:,.0f}", f"{base['LB']['dd']:,.0f}", f"{base['LB']['wo_biggest']:,.0f}"))
    if ref_check:
        bad = [f"{st} {k} {base[st][k]:.4f} vs {REF463[st][k]}" for st in ("WF", "LB") for k in ("roc30", "sortino", "dd")
               if not abs(base[st][k] - REF463[st][k]) <= REF_TOL[k]]
        if not abs(base["LB"]["wo_biggest"] - REF463_LB_WO_BIGGEST) <= WO_BIGGEST_TOL:
            bad.append(f"LB without biggest {base['LB']['wo_biggest']:.0f} vs {REF463_LB_WO_BIGGEST:.0f}")
        if bad:
            res["verdict"] = "PARITY STOP"
            res["parity_misses"] = bad
            say("PARITY STOP - #463 does not reproduce BOOK.md 10r: " + "; ".join(bad))
            return res

    m2 = v2_multipliers(M1, bk.index)

    # --- STEP 1: the forecast gate, IS only
    F, y, _ = forecasts(M1, mkt, HORIZON, min_train=min_train, refit=refit)
    s1 = step1(bk.index, F, y, HORIZON, w["IS1"])
    res["step1"] = s1
    say("STEP 1 (IS %s..%s, %d forecasts, relative errors): MSE naive %.4f  ridge %.4f  gbm %.4f -> RIDGE at %.3f x naive, "
        "DM %.2f p %.4f -> %s   (GBM, reported only: %.3f x naive, p %.4f)" % (
            s1["from"], s1["to"], s1["n"], s1["mse"]["naive"], s1["mse"]["ridge"], s1["mse"]["gbm"], s1["ratio"],
            s1["dm_stat"], s1["dm_p"], "PASS" if s1["pass"] else "FAIL", s1["gbm_info"]["ratio"], s1["gbm_info"]["dm_p"]))
    if not s1["pass"]:
        res["verdict"] = "FAIL at STEP 1 - the learned forecast does not beat V2's own information on IS; WF/LB not read"
        say("VERDICT: " + res["verdict"])
        return res

    chosen = s1["chosen"]
    res["forecast_skill"] = {st: forecast_skill(bk.index, F, y, HORIZON, w[st + "0"], w[st + "1"]) for st in ("WF", "LB")}
    say("  forecast skill (relative MSE, diagnostic): " + " | ".join(
        "%s naive %.4f %s %.4f" % (st, v.get("naive", float("nan")), chosen, v.get(chosen, float("nan")))
        for st, v in res["forecast_skill"].items()))
    S = forecast_dollars(F[chosen])
    m3 = ratio_multipliers(S)
    m3_delay = ratio_multipliers(np.r_[np.nan, S[:-1]])
    res["_series"] = {"S": S, "m2": m2, "m3": m3}

    arms = {"#463": np.ones(bk.N), "V2": m2, "V3": m3, "V3 delay": m3_delay}
    for h in (1, 20):                                    # sensitivity rows (report only)
        Fh, _, _ = forecasts(M1, mkt, h, kinds=(chosen,), min_train=min_train, refit=refit)
        arms[f"sens: horizon {h}"] = ratio_multipliers(forecast_dollars(Fh[chosen]))
    arms["sens: GBM forecast"] = ratio_multipliers(forecast_dollars(F["gbm"]))
    arms["sens: REF 500"] = ratio_multipliers(S, ref_win=500)
    arms["sens: caps 0.5-1.5"] = ratio_multipliers(S, hi=1.5)

    table = {}
    for name, m in arms.items():
        s = bk.sizes(m)
        Mx = bk.series(s)
        table[name] = {st: stretch(bk, Mx, s, w[st + "0"], w[st + "1"]) for st in ("WF", "LB")}
        table[name]["years"] = per_year(bk, Mx)
        table[name]["episodes"] = {e: window_dd(bk, Mx, a, b) for e, a, b in EPISODES}
    res["table"] = table
    res["no_forecast_share"] = {st: float(np.mean(~np.isfinite(S[(bk.index >= w[st + "0"]) & (bk.index <= w[st + "1"])])))
                                for st in ("WF", "LB")}

    if ref_check:
        say("  round 62 old-convention check (soft; 10o keyed V2 by UTC stamp, so small differences are expected): "
            "#463 WF %.1f (10o: %.1f) | V2 WF %.1f / LB %.1f (10o: %.1f / %.1f)" % (
            table["#463"]["WF"]["roc30_old"], REF_R62_OLD["463"]["WF"], table["V2"]["WF"]["roc30_old"],
            table["V2"]["LB"]["roc30_old"], REF_R62_OLD["V2"]["WF"], REF_R62_OLD["V2"]["LB"]))

    # --- the bar
    V3, B, V2 = table["V3"], table["#463"], table["V2"]
    beats = lambda A, Z: all(A[st]["roc30"] > Z[st]["roc30"] and A[st]["sortino"] > Z[st]["sortino"] for st in ("WF", "LB"))
    aim = {(st, how): aim_pct(bk, m3, w[st + "0"], w[st + "1"], V3[st]["roc30"], how)
           for st in ("WF", "LB") for how in ("shift", "shuffle")}
    clauses = {
        "1 beats #463 (ROC and Sortino, WF and LB)": beats(V3, B),
        "2 beats V2 (ROC and Sortino, WF and LB)": beats(V3, V2),
        "3 trades >= 100 WF / 50 LB and LB > 0 without its biggest trade":
            V3["WF"]["trades"] >= 100 and V3["LB"]["trades"] >= 50 and V3["LB"]["wo_biggest"] > 0,
        "4 one day staler still beats #463 on ROC (WF and LB)":
            all(table["V3 delay"][st]["roc30"] > B[st]["roc30"] for st in ("WF", "LB")),
        "5 WF aim: above the 95th pct of circular shifts of its own sizes": aim[("WF", "shift")] > 95.0,
    }
    res["aim_pct"] = {f"{st} {how}": v for (st, how), v in aim.items()}
    res["clauses"] = clauses
    res["pass"] = all(clauses.values())

    yrs_vs = lambda Z: sum(1 for y_ in V3["years"] if V3["years"][y_] > table[Z]["years"][y_])
    res["years_won"] = {"vs #463": yrs_vs("#463"), "vs V2": yrs_vs("V2"), "of": len(V3["years"])}

    say("")
    say("%-22s %8s %7s %10s %8s %7s %10s %6s %6s" % ("arm", "WF ROC", "WF So", "WF DD", "LB ROC", "LB So", "LB DD",
                                                    "WF sz", "LB sz"))
    for name, r in table.items():
        say("%-22s %8.1f %7.2f %10s %8.1f %7.2f %10s %6.2f %6.2f" % (
            name, r["WF"]["roc30"], r["WF"]["sortino"], f"${r['WF']['dd']:,.0f}", r["LB"]["roc30"], r["LB"]["sortino"],
            f"${r['LB']['dd']:,.0f}", r["WF"]["avg_size"], r["LB"]["avg_size"]))
    say("")
    say("episodes (drawdown inside each): " + " | ".join(
        "%s: #463 $%s, V2 $%s, V3 $%s" % (e, f"{B['episodes'][e]:,.0f}", f"{V2['episodes'][e]:,.0f}",
                                            f"{V3['episodes'][e]:,.0f}") for e, _, _ in EPISODES))
    say("years 2011-2025 with better net/drawdown: V3 vs #463 %d/%d, V3 vs V2 %d/%d" % (
        res["years_won"]["vs #463"], res["years_won"]["of"], res["years_won"]["vs V2"], res["years_won"]["of"]))
    say("aim percentile of V3's ROC at $30k: WF shift %.1f (registered) / shuffle %.1f | LB shift %.1f / shuffle %.1f (reported)" % (
        aim[("WF", "shift")], aim[("WF", "shuffle")], aim[("LB", "shift")], aim[("LB", "shuffle")]))
    for c, ok in clauses.items():
        say(("  PASS  " if ok else "  FAIL  ") + c)
    res["verdict"] = ("PASS - earns a forward shadow line beside VT (book_shadow_v3); owner decides"
                      if res["pass"] else "FAIL - V2 stays the only volatility line")
    say("VERDICT: " + res["verdict"])
    return res


def _beacon(title):
    try:
        tools = os.path.join(os.getcwd(), "tools")
        if tools not in sys.path:
            sys.path.append(tools)                 # appended, so nothing in tools/ can shadow the engine's packages
        from research_beacon import beacon
        return beacon(title, total=3)
    except Exception:
        return contextlib.nullcontext(None)


def build(d0, d1, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    t0 = time.time()
    legruns = []
    for leg in _legs463():
        legruns.append(run_leg(leg, d0, d1))
        say("  leg %-28s trades %5d   (%.0fs)" % (leg["strategy"], len(legruns[-1]["tr_usd"]), time.time() - t0))
    bk = Book(legruns, d0, d1)
    warm = (pd.Timestamp(d0) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    nq, es = market_daily(NQ_MKT, warm, d1), market_daily(ES_MKT, warm, d1)
    stats = {}
    mkt = market_features(bk.index, nq, es, stats)
    say("  market features: rows blanked as stale - NQ %d, ES %d (of %d)" % (stats["nq_stale_rows"], stats["es_stale_rows"], bk.N))
    coverage = {r["strategy"]: r["days_present"] for r in legruns}
    coverage["NQ features"] = np.asarray(nq.index.values, dtype="datetime64[D]")
    coverage["ES features"] = np.asarray(es.index.values, dtype="datetime64[D]")
    return bk, mkt, coverage


def engine_parity(bk, d0, d1):
    """The rebuild at size 1 must equal the production VT signal's own series to the cent, on the SAME day index, and V2
    here must equal vt_multipliers on that series. Returns (index equal, max $ diff, max multiplier diff)."""
    from api.book_shadow import book463_valued_daily, vt_multipliers
    ref = book463_valued_daily(d0, d1)
    mine = pd.Series(bk.series(np.ones(len(bk.tr_usd))), index=bk.index)
    same = bool(np.array_equal(np.asarray(mine.index.values, dtype="datetime64[D]"),
                               np.asarray(ref.index.values, dtype="datetime64[D]")))
    if not same:
        return False, float("nan"), float("nan")
    diff = float(np.max(np.abs(mine.to_numpy() - ref.to_numpy()))) if len(ref) else float("nan")
    m2diff = float(np.max(np.abs(v2_multipliers(mine.to_numpy(), mine.index) - vt_multipliers(ref).to_numpy())))
    return same, diff, m2diff


def tail_gaps(coverage, a, b):
    """Business days inside [a, b] with no bars, per leg / feature master (holidays included - read with care)."""
    days = np.asarray(pd.bdate_range(a, b).values, dtype="datetime64[D]")
    return {k: [str(d) for d in np.setdiff1d(days, v)] for k, v in coverage.items()}


def sha_lf(path):
    """sha256 of a text file with CRLF -> LF (the canonical pre-registration hash, as tools/rocfrontier/r10_spread.py)."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


RESULT_JSON, MULT_CSV = "v3_result.json", "v3_daily_multipliers.csv"


def _git_head(path):
    """Best-effort {dir, ref, commit} of the git checkout holding `path`, read from .git directly (no git process); None
    when unknown. Handles a worktree (.git is a file pointing at its gitdir) and packed refs."""
    try:
        d = os.path.abspath(path if os.path.isdir(path) else os.path.dirname(path))
        while not os.path.exists(os.path.join(d, ".git")):
            up = os.path.dirname(d)
            if up == d:
                return None
            d = up
        g = os.path.join(d, ".git")
        if os.path.isfile(g):
            with open(g) as f:
                line = f.read().strip()
            if not line.startswith("gitdir:"):
                return None
            g = line.split(":", 1)[1].strip()
            g = g if os.path.isabs(g) else os.path.normpath(os.path.join(d, g))
        with open(os.path.join(g, "HEAD")) as f:
            head = f.read().strip()
        if not head.startswith("ref:"):
            return {"dir": d, "ref": None, "commit": head}
        ref = head.split(":", 1)[1].strip()
        bases = [g]
        if os.path.exists(os.path.join(g, "commondir")):
            with open(os.path.join(g, "commondir")) as f:
                c = f.read().strip()
            bases.append(c if os.path.isabs(c) else os.path.normpath(os.path.join(g, c)))
        for base in bases:
            p = os.path.join(base, *ref.split("/"))
            if os.path.exists(p):
                with open(p) as f:
                    return {"dir": d, "ref": ref, "commit": f.read().strip()}
        for base in bases:
            p = os.path.join(base, "packed-refs")
            if os.path.exists(p):
                with open(p) as f:
                    for row in f:
                        parts = row.strip().split(" ")
                        if len(parts) == 2 and parts[1] == ref:
                            return {"dir": d, "ref": ref, "commit": parts[0]}
        return {"dir": d, "ref": ref, "commit": None}
    except Exception:
        return None


def _provenance():
    """What this registered run ran on: the prereg and harness hashes (canonical LF) and the git HEAD, best effort."""
    here = _HERE
    root, mine = _git_head(os.getcwd()), _git_head(here)
    prov = {"prereg_file": PREREG, "prereg_sha256_lf": sha_lf(PREREG), "harness_file": here,
            "harness_sha256_lf": sha_lf(here), "git_head": root}
    if mine is not None and (root is None or mine.get("dir") != root.get("dir")):
        prov["git_head_harness"] = mine             # the harness was launched from another checkout than the engine's
    return prov


def _refuse_if_read(out):
    """READ ONCE: a registered run refuses, before any engine build, when <out>/v3_result.json already holds the result
    table - the lockbox was printed by an earlier run. A STEP 1 fail or a parity stop leaves no table, so it does not block."""
    p = os.path.join(out, RESULT_JSON)
    if not os.path.exists(p):
        return
    try:
        with open(p) as f:
            prior = json.load(f)
    except Exception as e:
        raise SystemExit("REFUSED (read once): %s exists but cannot be read (%s: %s); it may hold an already printed lockbox. "
                         "Inspect it and move it aside deliberately before a new registered run." % (p, type(e).__name__, e))
    if isinstance(prior, dict) and "table" in prior:
        raise SystemExit("REFUSED (read once): %s already holds the V3 result table - the lockbox was already printed by an "
                         "earlier registered run (verdict: %s). Move that file aside deliberately before running again."
                         % (p, prior.get("verdict")))


def _save(out, bk, res):
    """The daily multipliers (when STEP 2 ran) and the result JSON; the JSON goes through a temp file so it is never half written."""
    ser = res.get("_series")
    if ser is not None:
        # lookup rule for a forward line: a fill on ET date X takes the first row whose index_day >= X
        pd.DataFrame({"index_day": bk.index.strftime("%Y-%m-%d"), "S_forecast": ser["S"], "m_V2": ser["m2"],
                      "m_V3": ser["m3"]}).to_csv(os.path.join(out, MULT_CSV), index=False)
    p = os.path.join(out, RESULT_JSON)
    with open(p + ".tmp", "w") as f:
        json.dump(_jsonable(res), f, indent=1)
    os.replace(p + ".tmp", p)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=None)
    ap.add_argument("--tail-to", default=None, help="also report 2026-07-01..DATE as an INFO row (second engine pass)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (os.path.exists(PREREG) and sha_lf(PREREG) == PREREG_SHA):
        print("REFUSED: %s is missing or differs from the committed pre-registration - a changed spec is a new file" % PREREG)
        return 3
    out = a.out or (os.path.join(r"C:\EdgeLog\_anatomy_cache", "frontier_v3") if os.path.isdir(r"C:\EdgeLog")
                    else os.path.join(os.getcwd(), "_frontier_v3_out"))
    _refuse_if_read(out)                            # before any engine build
    prov = _provenance()
    os.makedirs(out, exist_ok=True)
    with _beacon("FRONTIER V3 learned risk forecast") as b:
        print("V3 - learned risk forecast vs V2 on #463 (prereg docs/PREREG_frontier_v3_riskml_2026-10-02.txt)")
        print("  prereg sha256 (LF) %s | harness sha256 (LF) %s | git HEAD %s" % (
            prov["prereg_sha256_lf"][:12], prov["harness_sha256_lf"][:12], (prov.get("git_head") or {}).get("commit")))
        bk, mkt, _cov = build(W0, W1)
        if b is not None:
            b.step(1)
        same, diff, m2diff = engine_parity(bk, W0, W1)
        print("PARITY series: same day index %s; max |rebuild - book463_valued_daily| = $%.4f; max |V2 here - vt_multipliers| = %.3f"
              % (same, diff, m2diff))
        if not (same and diff <= 0.005 and m2diff <= 1e-9):
            print("PARITY STOP - the rebuild does not equal the production VT series; nothing else is read")
            return 2
        res = evaluate(bk, mkt)
        res.update(prov)
        _save(out, bk, res)                         # the registered result is on disk before anything optional runs
        print("wrote " + out)
        if b is not None:
            b.step(2)
        if a.tail_to and res.get("step1", {}).get("pass"):
            bt, mt, cov = build(W0, a.tail_to, verbose=False)
            gaps = tail_gaps(cov, TAIL0, pd.Timestamp(a.tail_to))
            rt = evaluate(bt, mt, verbose=False, ref_check=False,
                          windows={"IS1": IS1, "WF0": WF0, "WF1": WF1, "LB0": TAIL0, "LB1": pd.Timestamp(a.tail_to)})
            res["tail_info"] = {k: {"net": v["LB"]["net"], "dd": v["LB"]["dd"]} for k, v in (rt.get("table") or {}).items()
                                if k in ("#463", "V2", "V3")}
            res["tail_gaps"] = gaps
            res["tail_no_forecast_share"] = (rt.get("no_forecast_share") or {}).get("LB")
            print("TAIL %s..%s (INFO ONLY, not part of the bar): " % (TAIL0.date(), a.tail_to) + " | ".join(
                "%s net $%s DD $%s" % (k, f"{v['net']:,.0f}", f"{v['dd']:,.0f}") for k, v in res["tail_info"].items()))
            print("  tail rows where V3 had no forecast (m forced to 1): %.0f%%" % (100.0 * (res["tail_no_forecast_share"] or 0.0)))
            for k, v in gaps.items():
                print("  tail data: %-28s %d business days with no bars%s" % (
                    k, len(v), ("  <- CHECK before reading the tail: " + ", ".join(v[:6])) if len(v) > 3 else ""))
            _save(out, bk, res)                     # rewrite with the tail INFO row (the registered fields are unchanged)
            print("rewrote %s with the tail INFO row" % os.path.join(out, RESULT_JSON))
        if b is not None:
            b.step(3)
    return 2 if res.get("verdict") == "PARITY STOP" else 0


# ============================================================ selftest (synthetic data; no masters needed)
def _synthetic(seed=7, d0="2010-06-07", d1="2026-06-30", n_legs=8):
    """A fake book whose risk follows a GARCH-like market: enough structure to exercise every path."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(d0, d1)
    n = len(days)
    h = np.empty(n)
    h[0] = 1.0
    r = np.empty(n)
    for i in range(n):
        if i:
            h[i] = 0.05 + 0.90 * h[i - 1] + 0.08 * r[i - 1] ** 2
        r[i] = math.sqrt(h[i]) * rng.standard_normal()
    scale = np.linspace(1.0, 8.0, n)                       # dollar risk grows with the index level
    rng_pts = 60.0 * np.sqrt(h) * scale * np.exp(0.2 * rng.standard_normal(n))
    close = 2000.0 * np.exp(np.cumsum(0.0003 + 0.01 * r))
    mkt = pd.DataFrame({"rng": rng_pts, "close": close}, index=days)
    legruns = []
    for j in range(n_legs):
        e_pos = np.sort(rng.choice(n - 3, size=int(n * 0.6), replace=False))
        hold = rng.integers(0, 3 if j < n_legs - 1 else 15, size=len(e_pos))
        x_pos = np.minimum(e_pos + hold, n - 1)
        usd = (0.08 + rng.standard_normal(len(e_pos))) * 400.0 * np.sqrt(h[e_pos]) * scale[e_pos]
        inc_tid, inc_day, inc_usd = [], [], []
        for k, (e, x, u) in enumerate(zip(e_pos, x_pos, usd)):
            span = np.arange(e, x + 1)
            w = rng.dirichlet(np.ones(len(span))) if len(span) > 1 else np.ones(1)
            parts = u * w
            parts[-1] = u - parts[:-1].sum()
            inc_tid += [k] * len(span)
            inc_day += list(days.values[span].astype("datetime64[D]"))
            inc_usd += list(parts)
        ent = days.values[e_pos].astype("datetime64[D]")
        legruns.append({"strategy": f"SYN_{j}", "tr_entry": ent, "tr_entry_et": ent,
                        "tr_exit": days.values[x_pos].astype("datetime64[D]"), "tr_usd": usd,
                        "inc_tid": np.array(inc_tid), "inc_day": np.array(inc_day, dtype="datetime64[D]"),
                        "inc_usd": np.array(inc_usd), "days_present": np.asarray(days.values, dtype="datetime64[D]")})
    return legruns, mkt


def _same(a, b):
    return np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(a[~np.isnan(a)], b[~np.isnan(b)])


def selftest():
    import warnings
    warnings.simplefilter("ignore")
    print("SELFTEST (synthetic data, registered windows; the numbers mean nothing about the real book)")
    legruns, mkt = _synthetic()
    bk = Book(legruns, W0, W1)
    es_mk = mkt.assign(rng=mkt["rng"] * 0.4)
    feats = market_features(bk.index, mkt, es_mk)
    ones = np.ones(len(bk.tr_usd))
    M1 = bk.series(ones)
    # 1. the bincount book equals the plain pooled sum of increments
    pooled = pd.Series(np.concatenate([r["inc_usd"] for r in legruns]),
                       index=pd.DatetimeIndex(np.concatenate([r["inc_day"] for r in legruns]).astype("datetime64[ns]")))
    pooled = pooled.groupby(level=0).sum().reindex(bk.index).fillna(0.0)
    assert np.allclose(pooled.to_numpy(), M1, atol=1e-6), "book series != pooled increments"
    # 2. per-trade sizes scale increments linearly (what the engine's _mtm_increments does with `size`)
    s = np.random.default_rng(1).uniform(0.5, 2.0, len(ones))
    assert abs(bk.series(s).sum() - float((bk.tr_usd * s).sum())) < 1e-4, "sized increments do not sum to sized trades"
    # 3. V2 here == the nightly line (the real api.book_shadow when importable)
    try:
        import api.book_shadow  # noqa: F401
        src = "api.book_shadow.vt_multipliers"
    except Exception:
        src = "inline copy (api not importable here)"
    assert np.array_equal(v2_multipliers(M1, bk.index), _vt_fallback(pd.Series(M1, index=bk.index)).to_numpy()), "V2 drift"
    print("  V2 multipliers equal the nightly formula (" + src + ") - OK")
    # 4. CAUSALITY: scramble everything from position T on; nothing at or before T may move. T is set at several points,
    #    including right after a refit, where a training target that reaches past the refit would be caught.
    F, y, refits = forecasts(M1, feats, HORIZON)
    r_mid = refits[len(refits) // 2]
    for T in (r_mid, r_mid + 1, r_mid + HORIZON - 1, int(np.searchsorted(bk.index.values, np.datetime64("2019-03-15")))):
        M2 = M1.copy()
        M2[T:] = np.random.default_rng(T).standard_normal(bk.N - T) * 1e5
        late = mkt.index >= bk.index[T]
        mk2 = mkt.copy()
        mk2.loc[late, "rng"] = np.random.default_rng(T + 1).uniform(1, 500, late.sum())
        mk2.loc[late, "close"] = np.random.default_rng(T + 2).uniform(100, 9000, late.sum())
        F2, _, _ = forecasts(M2, market_features(bk.index, mk2, mk2.assign(rng=mk2["rng"] * 0.4)), HORIZON)
        for k in F:
            assert _same(F[k][:T + 1], F2[k][:T + 1]), f"LOOK-AHEAD in {k} forecasts (T={T})"
            assert np.array_equal(ratio_multipliers(forecast_dollars(F[k]))[:T + 1],
                                  ratio_multipliers(forecast_dollars(F2[k]))[:T + 1]), f"LOOK-AHEAD in {k} sizes (T={T})"
        assert np.array_equal(v2_multipliers(M1, bk.index)[:T + 1], v2_multipliers(M2, bk.index)[:T + 1]), "LOOK-AHEAD in V2"
    print("  causality: forecasts and sizes unchanged up to each scramble point (incl. right after a refit) - OK")
    # 5. the same scramble DOES catch a weakened embargo (training rows whose target reaches past the refit)
    T = r_mid + 1
    M2 = M1.copy()
    M2[T:] = np.random.default_rng(T).standard_normal(bk.N - T) * 1e5
    Fw, _, _ = forecasts(M1, feats, HORIZON, kinds=("ridge",), embargo=1)
    Fw2, _, _ = forecasts(M2, feats, HORIZON, kinds=("ridge",), embargo=1)
    assert not _same(Fw["ridge"][:T + 1], Fw2["ridge"][:T + 1]), "the causality test cannot see a weak embargo"
    print("  a deliberately weakened embargo IS caught by the same test - OK")
    # 6. one refit schedule for every model, and the first refit has MIN_TRAIN rows behind it
    assert refits and refits[0] >= MIN_TRAIN, "first refit before MIN_TRAIN rows"
    # 7. GBM is deterministic across seeds with these settings (no seed-fragile pass, the round-58 failure)
    Xf = feature_frame(M1, feats)[list(FEATURES)].to_numpy()
    g0, _ = walk_forward(Xf, y, "gbm", HORIZON, refits[0], seed=0)
    g9, _ = walk_forward(Xf, y, "gbm", HORIZON, refits[0], seed=9)
    assert _same(g0, g9), "GBM depends on its seed"
    # 8. DM sanity: identical errors -> no evidence; a clearly better model -> tiny p
    e = np.random.default_rng(2).standard_normal(2000)
    assert not dm_test(e, e)[1] < DM_P and dm_test(e, 0.5 * e)[1] < 1e-6, "DM test broken"
    # 9. relative errors ignore a constant level bias (it cancels in m = REF / S)
    E0 = relative_errors(F["ridge"], y, HORIZON)
    E1 = relative_errors(F["ridge"] + 0.7, y, HORIZON)
    k = np.isfinite(E0) & np.isfinite(E1)
    assert np.mean(np.abs(E0[k] - E1[k])) < 0.05, "relative errors still see a level bias"
    # 10. a stale feature master blanks features instead of carrying them forward
    gap = mkt.drop(mkt.index[(mkt.index >= "2015-03-02") & (mkt.index <= "2015-03-13")])
    fs = market_features(bk.index, gap, es_mk)
    k = (bk.index >= "2015-03-05") & (bk.index <= "2015-03-13")
    assert fs.loc[k, "nq1"].isna().all() and fs.loc[k, "es1"].notna().all(), "stale features not blanked"
    # 11. the full evaluate path end to end (no reference check: synthetic)
    res = evaluate(bk, feats, verbose=True, ref_check=False)
    assert "table" in res and "verdict" in res, "the synthetic book no longer reaches STEP 2 - the self-test lost its coverage"

    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

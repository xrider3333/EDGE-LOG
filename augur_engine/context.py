"""TRADE CONTEXT (stages 1+2) — augur_engine/context.py

Answers "which market features plausibly explain trade performance?": enrich each
backtest trade with what the market was doing at ENTRY (prior-day-close features,
strictly causal — a trade entering on day D only ever sees information knowable
before day D's session opens), then score feature -> per-trade-PnL relationships
with Spearman/Pearson + a block-bootstrap CI + Benjamini-Hochberg FDR + an
ERA-AWARE consistency guard for slow-drifting features. The result is the
JSON-safe `result["context"]` block (wired into optimize.py/auto.py next to
`analytics.regime_report`) the web can later render as a bar panel, the same
way `analytics.relationship_scores` feeds the existing PARAM RELATIONSHIP panel.

Four pieces, same "never break a backtest" discipline as analytics.py:
  * build_internal_daily — daily features from the run's OWN bar arrays (no
    network). Every feature is shifted +1 day EXCEPT gap_pct (see its docstring).
  * fetch_external_daily — ^VIX/^VIX3M/^TNX/^IRX daily features from yfinance,
    CSV-cached in augur_uploads/_context/, fail-soft on ANY network hiccup.
  * context_scores       — the stats core: join trades -> entry-day features,
    Spearman rho (primary) + Pearson r, a 95% CI from a MOVING-BLOCK bootstrap
    (contiguous runs of trading days, not independent days — day-clustering
    alone still lets a feature that drifts over YEARS look falsely tight/
    significant, since two slow-drifting series correlate whether or not one
    causes the other), BH-FDR across features, and an ERA-AWARE guard: a
    "slow" (persistent, autocorr>=0.95) feature only `survives` when its
    relationship to PnL also holds WITHIN each era (calendar year), not just
    across the whole history — see context_scores' docstring for the full
    field list (rho_within/n_eras/era_consistent/era_pass/autocorr/slow/
    trend_confounded). A plain `_clustered_bootstrap_ci` (day-only) is still
    available for comparison/tests. Two more layers, both informational/gating
    on TOP of everything above (never replacing it):
      - SHADOW PROBES (hand-rolled Boruta idea): K=3 fake features built by
        shuffling real feature columns across days (same marginal distribution,
        destroyed date alignment -> a pure noise floor). A real feature must
        beat the strongest probe's |rho| to `survive` at all — catches a
        feature that clears FDR/CI/era only because the bar itself was low
        for this dataset. See `_build_probe_daily`/`_score_probes`.
      - JOINT IMPORTANCE (LASSO + RF permutation importance, sklearn): all the
        above is univariate (one feature at a time); this fits ALL features
        (+ the 3 probes, for a noise floor inside the joint model too)
        together on the complete-case matrix, so a pair of collinear features
        that both "survive" alone can be told apart — which one the joint
        model actually leans on. Pure information, reported per feature
        (`lasso_coef/lasso_kept/rf_imp/rf_beats_probe`) and does NOT gate
        `survives`. See `_joint_importance`.
  * build_context        — the one-call wiring helper optimize.py/auto.py use:
    ties the three together and NEVER raises (returns None on any failure).
"""
import os
import warnings

import numpy as np
import pandas as pd

from .paths import UPLOADS

try:
    from scipy.stats import rankdata as _rankdata, spearmanr as _spearmanr
    _HAS_SCIPY = True
except Exception:                                    # pragma: no cover - scipy is a
    _rankdata = None                                  # confirmed dep in this repo;
    _spearmanr = None                                 # kept as a real fallback anyway.
    _HAS_SCIPY = False

CACHE_DIR = os.path.join(UPLOADS, "_context")
CACHE_STALE_DAYS = 3          # re-pull a ticker only when its cache is older than this
MIN_TRADES = 30                # context_scores returns None below this many usable trades
MIN_FEATURE_TRADES = 10        # a feature with fewer non-NaN observations is not scored
MIN_FEATURE_DAYS = 2           # a feature needs >=2 distinct entry days to bootstrap-CI
FDR_Q = 0.10                   # survives = Benjamini-Hochberg q-value < this

# ── era-aware guard (BACKTESTING_STACK / context.py revamp) ────────────────────
# Slow macro features (tnx, curve, and to a lesser degree vix/atr20_pctile) drift
# over YEARS; strategy performance also varies by era. Two things that both
# drift over a decade correlate whether or not one causes the other, and the
# day-clustered bootstrap above only fixes SAME-DAY clustering -- it says
# nothing about multi-year serial autocorrelation, so a persistent feature's CI
# comes out falsely tight and its q falsely small. These constants back the
# block bootstrap (wider, honest CI) and the within-era consistency check
# (does the relationship actually hold INSIDE each era, or only ACROSS eras --
# i.e. is it real or pure drift) that together gate `survives` for slow features.
BLOCK_DAYS_MIN = 21            # ~1 trading month -- floor block length (moving-block bootstrap)
BLOCK_DAYS_MAX = 126           # ~6 months -- ceiling so the bootstrap stays computable
DEFAULT_BLOCK_N_BOOT = 500     # block draws are costlier than day draws (each covers a whole
                                # block, not one row-weight lookup); 500 keeps runtime sane --
                                # see context_scores docstring for the tradeoff.
SLOW_AUTOCORR = 0.95           # lag-1 autocorr of the DAILY feature series >= this -> "slow"
                                # (persistent) -> gated by era_pass. tnx/curve/vix LEVELS trip
                                # this; day-to-day features (vix_chg_5d, gap_pct, prev_ret) don't.
ERA_MIN_TRADES = 30            # an era needs >= this many usable trades to count toward n_eras
ERA_MIN_ERAS = 3               # era_pass needs at least this many usable eras
ERA_CONSISTENT_MIN = 0.6       # >=60% of usable eras must share the overall rho's sign
ERA_T_MIN = 2.0                # |t| of the per-era rhos vs 0 (mean / SE across eras).
                               # The REAL era test: a sign fraction alone is close to a
                               # coin flip (11-of-17 eras sharing a sign is p~0.33, i.e.
                               # no evidence), so a pooled correlation built from tiny
                               # per-era rhos that scatter around zero — the signature of
                               # a multi-year drift artifact — must also fail this.

# ── shadow probes (hand-rolled Boruta idea) ─────────────────────────────────────
# K fake "features" per call, each a shuffled copy of a real feature column (same
# values, permuted across days -> same marginal distribution, zero true relationship
# to any trade). Their max |rho| is the noise floor a real feature must beat to
# `survive` — catches "significant" relationships that only cleared FDR/CI/era
# because the bar was low for THIS dataset, not because the feature is special.
N_SHADOW_PROBES = 3            # fixed K — see context_scores docstring
PROBE_SEED_STRIDE = 9973       # spaces out each probe's sub-seed from the caller's
                                # `seed` so 3 probes built from the SAME source column
                                # (fewer than N_SHADOW_PROBES real columns available)
                                # still get 3 independent permutations, deterministically.

# ── joint importance layer (LASSO + RF permutation) ─────────────────────────────
MIN_JOINT_ROWS = 100            # fewer complete-case rows (ALL scored features + all
                                # probes non-NaN) than this -> joint=None, too little
                                # data for a stable multivariate fit.
LASSO_KEPT_EPS = 1e-10          # |coef| above this counts as "kept" (LassoCV can leave
                                # a coefficient at a tiny non-zero float, not exactly 0.0).

EXTERNAL_TICKERS = {"^VIX": "vix", "^VIX3M": "vix3m", "^TNX": "tnx", "^IRX": "irx"}
EXTERNAL_FEATURES = ("vix", "vix_pctile_1y", "vix_chg_5d", "vix_term",
                     "tnx", "tnx_chg_20d", "curve")
INTERNAL_FEATURES = ("rsi14", "macd_hist", "atr20_pctile", "er20", "gap_pct",
                     "prev_ret", "range_pctile", "up_streak")


# ─────────────────────────────────────────────────────────────────────────────
# build_internal_daily — features from the run's own bars, no network
# ─────────────────────────────────────────────────────────────────────────────

def _rolling_pctile(s, window=252, min_periods=None):
    """Trailing percentile RANK (0-100) of the last value in each window — purely
    causal (only ever looks backward from the row it's computed at). NaNs inside
    the window are ignored for the comparison (a leading NaN run from an inner
    rolling feature like ATR20 must not silently bias the rank)."""
    if min_periods is None:
        min_periods = max(20, int(window) // 4)

    def _pct(x):
        last = x[-1]
        if np.isnan(last):
            return np.nan
        valid = x[~np.isnan(x)]
        if len(valid) < 2:
            return np.nan
        return float((valid < last).mean() * 100.0)

    return s.rolling(int(window), min_periods=int(min_periods)).apply(_pct, raw=True)


def build_internal_daily(index, opens, highs, lows, closes):
    """Daily features derived from the run's OWN bar arrays, resampled to one row
    per calendar day (open=first, high=max, low=min, close=last of that day's
    bars). Every feature is SHIFTED +1 day — a trade entering on day D sees day
    D-1's value — EXCEPT `gap_pct`, which is already causal as defined: today's
    OPEN vs YESTERDAY's close is known the instant the session opens, before any
    trade can fill, so shifting it again would show a trade day D-2's gap instead
    of its own.

    rsi14         : 14-day RSI of daily closes (SMA-smoothed gain/loss, 100 when
                    the window has zero losses, 50 when it's dead flat).
    macd_hist     : 12/26/9 EMA MACD histogram, normalized by close (unitless).
    atr20_pctile  : rolling-252 percentile rank of a 20-day true-range average.
    er20          : efficiency ratio |20d net move| / sum |daily moves| in [0,1].
    gap_pct       : today's open vs prior close, % — NOT shifted (see above).
    prev_ret      : prior trading day's close-to-close return, %.
    range_pctile  : rolling-252 percentile rank of the daily high-low range.
    up_streak     : signed consecutive up/down-day count (+3 = 3 up days running).

    Returns a DataFrame indexed by `datetime.date`, columns = INTERNAL_FEATURES.
    """
    eix = pd.to_datetime(pd.Series(index))
    dts = eix.dt.date.values
    O = np.asarray(opens, float); H = np.asarray(highs, float)
    L = np.asarray(lows, float); C = np.asarray(closes, float)
    n = min(len(dts), len(O), len(H), len(L), len(C))
    df = pd.DataFrame({"d": dts[:n], "o": O[:n], "h": H[:n], "l": L[:n], "c": C[:n]})
    day = df.groupby("d", sort=True).agg(o=("o", "first"), h=("h", "max"),
                                         l=("l", "min"), c=("c", "last"))
    pc = day["c"].shift(1)

    # gap_pct — KNOWN at entry (today's open vs yesterday's close); no shift.
    gap_pct = ((day["o"] - pc) / pc.replace(0.0, np.nan)) * 100.0

    # RSI14 (daily closes, SMA-smoothed gain/loss — simple & deterministic).
    delta = day["c"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi14 = 100.0 - 100.0 / (1.0 + rs)
    rsi14 = rsi14.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi14 = rsi14.mask((avg_loss == 0) & (avg_gain == 0), 50.0)

    # MACD histogram (12/26/9 EMA), normalized by close so it's comparable
    # across instruments/price levels.
    ema12 = day["c"].ewm(span=12, adjust=False).mean()
    ema26 = day["c"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9, adjust=False).mean()
    macd_hist = (macd - macd_sig) / day["c"].replace(0.0, np.nan)

    # ATR20 (Wilder true range, SMA-smoothed) + its rolling-252 percentile rank.
    tr = np.maximum(day["h"] - day["l"],
                    np.maximum((day["h"] - pc).abs(), (day["l"] - pc).abs()))
    atr20 = tr.rolling(20, min_periods=20).mean()
    atr20_pctile = _rolling_pctile(atr20, window=252)

    # Efficiency ratio (Kaufman-style, 20d) — same construction as
    # analytics.regime_report's er20 (trend vs chop).
    dmv = day["c"].diff()
    er20 = (day["c"].diff(20).abs() / dmv.abs().rolling(20, min_periods=20).sum()).clip(0, 1)

    day_ret = day["c"].pct_change() * 100.0            # raw, pre-shift day-over-day return
    range_pctile = _rolling_pctile(day["h"] - day["l"], window=252)

    # up_streak — stateful signed run count; NaN until the first real day-over-day
    # return exists (day 0 has no prior close to compare against).
    streak = np.full(len(day), np.nan)
    cur = 0.0
    for i, r in enumerate(day_ret.to_numpy()):
        if np.isnan(r):
            continue
        if r > 0:
            cur = cur + 1 if cur > 0 else 1.0
        elif r < 0:
            cur = cur - 1 if cur < 0 else -1.0
        else:
            cur = 0.0
        streak[i] = cur
    up_streak = pd.Series(streak, index=day.index)

    raw = pd.DataFrame({"rsi14": rsi14, "macd_hist": macd_hist,
                        "atr20_pctile": atr20_pctile, "er20": er20,
                        "prev_ret": day_ret, "range_pctile": range_pctile,
                        "up_streak": up_streak})
    out = raw.shift(1)                                  # causal: trade on D sees D-1's row
    out["gap_pct"] = gap_pct                             # already causal — see docstring
    return out[list(INTERNAL_FEATURES)]


# ─────────────────────────────────────────────────────────────────────────────
# fetch_external_daily — ^VIX/^VIX3M/^TNX/^IRX via yfinance, CSV-cached
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(ticker):
    safe = ticker.replace("^", "_").replace("=", "_")
    return os.path.join(CACHE_DIR, f"{safe}.csv")


def _load_cache(ticker):
    p = _cache_path(ticker)
    if not os.path.exists(p):
        return None
    try:
        df = pd.read_csv(p)
        s = pd.Series(df["close"].astype(float).to_numpy(),
                      index=pd.to_datetime(df["date"]).dt.date)
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception:
        return None


def _save_cache(ticker, s):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        out = pd.DataFrame({"date": [str(d) for d in s.index], "close": s.to_numpy()})
        out.to_csv(_cache_path(ticker), index=False)
    except Exception:
        pass                                            # a cache-write failure is never fatal


def _fetch_one(ticker):
    """One ticker's daily-close Series (index = datetime.date). Refreshes from
    yfinance ONLY when the on-disk cache is missing or its last date is more than
    CACHE_STALE_DAYS calendar days old — and even then only keeps the fetch if it
    actually returns rows. On ANY failure (network, parse, whatever) this falls
    back to whatever cache already existed (possibly None). Never raises."""
    cached = _load_cache(ticker)
    stale = True
    if cached is not None and len(cached):
        last = pd.Timestamp(max(cached.index))
        stale = (pd.Timestamp.now().normalize() - last).days > CACHE_STALE_DAYS
    if cached is None or stale:
        try:
            import yfinance as yf
            raw = yf.download(ticker, start="2005-01-01", progress=False, auto_adjust=False)
            col = raw["Close"] if "Close" in raw else raw.iloc[:, 0]
            if hasattr(col, "columns"):                 # yfinance >=1.x returns a frame
                col = col.iloc[:, 0]
            col = col.dropna()
            if len(col):
                s = pd.Series(col.to_numpy(), index=pd.to_datetime(col.index).date).sort_index()
                if cached is not None and len(cached):
                    merged = pd.concat([cached, s])
                    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                else:
                    merged = s
                _save_cache(ticker, merged)
                cached = merged
        except Exception:
            pass                                        # keep whatever cache we had (maybe None)
    return cached


def fetch_external_daily(start, end):
    """VIX/VIX3M/TNX/IRX-derived daily features, ALL shifted +1 day (prior close
    decides today, causal). `start`/`end` are advisory only — the rolling features
    need trailing history so the cache is never hard-clipped to the window; the
    caller's join on trade entry-date naturally keeps only the matching rows.

    vix           : ^VIX prior close.
    vix_pctile_1y : rolling-252 percentile rank of ^VIX.
    vix_chg_5d    : ^VIX 5-day % change.
    vix_term      : ^VIX3M - ^VIX (negative = backwardation).
    tnx           : ^TNX (10y yield) prior close.
    tnx_chg_20d   : ^TNX 20-day point change.
    curve         : ^TNX - ^IRX (10y-3mo curve).

    Returns a DataFrame indexed by date, or None when NO ticker has any data at
    all (missing cache AND a failed fetch for every one of them) — a backtest
    must NEVER fail because Yahoo is down.
    """
    try:
        series = {}
        for ticker, name in EXTERNAL_TICKERS.items():
            s = _fetch_one(ticker)
            if s is not None and len(s):
                series[name] = s
        if not series:
            return None
        df = pd.DataFrame(series).sort_index()
        raw = pd.DataFrame(index=df.index)
        if "vix" in df:
            raw["vix"] = df["vix"]
            raw["vix_pctile_1y"] = _rolling_pctile(df["vix"], window=252)
            raw["vix_chg_5d"] = df["vix"].pct_change(5) * 100.0
        if "vix" in df and "vix3m" in df:
            raw["vix_term"] = df["vix3m"] - df["vix"]
        if "tnx" in df:
            raw["tnx"] = df["tnx"]
            raw["tnx_chg_20d"] = df["tnx"].diff(20)
        if "tnx" in df and "irx" in df:
            raw["curve"] = df["tnx"] - df["irx"]
        if raw.empty or not len(raw.columns):
            return None
        return raw.shift(1)                              # causal: prior close -> today
    except Exception:
        return None                                       # never let a data hiccup propagate


# ─────────────────────────────────────────────────────────────────────────────
# context_scores — the stats core
# ─────────────────────────────────────────────────────────────────────────────

def _rank(x):
    if _HAS_SCIPY:
        return _rankdata(x).astype(float)
    return pd.Series(x).rank().to_numpy(float)


def _pearson(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    dx = x - x.mean(); dy = y - y.mean()
    den = float(np.sqrt((dx * dx).sum() * (dy * dy).sum()))
    return float((dx * dy).sum() / den) if den > 1e-12 else 0.0


def _bh_fdr(pvals):
    """Benjamini-Hochberg step-up FDR -> q-values (adjusted p-values), same order
    as the input. Hand-rolled (no statsmodels dependency)."""
    p = np.asarray(pvals, float)
    n = len(p)
    if n == 0:
        return np.array([])
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]              # enforce monotonicity
    q = np.clip(q, 0.0, 1.0)
    out = np.empty(n)
    out[order] = q
    return out


def _perm_pvalue(x, y, rho_obs, days, n_perm=1000, seed=42):
    """Permutation p-value used only when scipy is unavailable: reshuffles PnL
    DAY-BLOCKS (each day's whole block of trades moves together, keeping the
    within-day cluster structure intact — the same clustering principle as the
    bootstrap CI) rather than individual trades. Two-sided: fraction of
    permutations whose |rho| >= the observed |rho|."""
    rng = np.random.default_rng(int(seed))
    uniq_days, day_code = np.unique(days, return_inverse=True)
    nD = len(uniq_days)
    positions = [np.where(day_code == c)[0] for c in range(nD)]
    y = np.asarray(y, float)
    rx = _rank(x)
    m = 0
    for _ in range(int(n_perm)):
        perm = rng.permutation(nD)
        yb = np.empty(len(y))
        for c in range(nD):
            src = positions[perm[c]]; dst = positions[c]
            yb[dst] = y[src] if len(src) == len(dst) else y[src][rng.integers(0, len(src), len(dst))]
        rb = _pearson(rx, _rank(yb))
        if abs(rb) >= abs(rho_obs):
            m += 1
    return (m + 1) / (int(n_perm) + 1)


def _pvalue(x, y, rho_obs, days, seed=42):
    if _HAS_SCIPY:
        try:
            _, p = _spearmanr(x, y)
            if p is not None and np.isfinite(p):
                return float(p), "scipy"
        except Exception:
            pass
    return _perm_pvalue(x, y, rho_obs, days, seed=seed), "permutation"


def _clustered_bootstrap_ci(rx, ry, day_code, n_days, n_boot, seed):
    """95% percentile CI for Spearman rho from a bootstrap that resamples ENTRY
    DAYS (not individual trades) with replacement. Fully vectorized: instead of
    materializing n_boot duplicated trade arrays, it computes each draw's
    per-row WEIGHT (how many times that row's day was picked) and applies a
    weighted-Pearson formula to the (already-ranked) rx/ry — mathematically the
    same as re-ranking-and-correlating an expanded duplicate array, since
    duplicating existing points changes their WEIGHT, not their relative order.
    """
    rng = np.random.default_rng(int(seed))
    n_boot = int(n_boot); n_days = int(n_days)
    samp = rng.integers(0, n_days, size=(n_boot, n_days))
    mult = np.zeros((n_boot, n_days), dtype=np.int32)
    rows = np.repeat(np.arange(n_boot), n_days)
    np.add.at(mult, (rows, samp.ravel()), 1)
    W = mult[:, day_code].astype(float)                    # (n_boot, n_obs)
    sw = W.sum(axis=1, keepdims=True)
    sw_safe = np.where(sw > 0, sw, 1.0)
    mx = (W * rx).sum(axis=1, keepdims=True) / sw_safe
    my = (W * ry).sum(axis=1, keepdims=True) / sw_safe
    dx = rx[None, :] - mx; dy = ry[None, :] - my
    cov = (W * dx * dy).sum(axis=1)
    vx = (W * dx * dx).sum(axis=1); vy = (W * dy * dy).sum(axis=1)
    den = np.sqrt(np.clip(vx * vy, 0, None))
    rho_boot = np.divide(cov, den, out=np.zeros_like(cov), where=den > 1e-12)
    lo, hi = np.percentile(rho_boot, [2.5, 97.5])
    return float(lo), float(hi)


def _block_bootstrap_ci(rx, ry, day_code, n_days, block_days, n_boot, seed):
    """95% percentile CI for Spearman rho from a MOVING-BLOCK bootstrap: each
    draw resamples CONTIGUOUS BLOCKS of `block_days` consecutive trading days
    (circular -- a block starting near the end wraps around to the start, the
    standard fix so every day gets equal coverage) instead of independent
    single days. `_clustered_bootstrap_ci` above only protects against SAME-DAY
    clustering (trades sharing a day share the same context row); it treats
    each day as an otherwise-independent draw, which understates uncertainty
    for a feature that drifts over months/years (see module docstring). This
    is the fix: a bootstrap draw that grabs one 21-126 trading-day block at a
    time only ever contributes CONSECUTIVE days, so slow multi-day/week/month
    persistence in the underlying feature (and in whatever it happens to be
    correlated with) shows up as genuinely wider uncertainty instead of being
    averaged away by treating far-apart days as exchangeable.

    Same vectorized weighted-rank trick as the day version: rather than
    materializing n_boot duplicated trade arrays, this computes each draw's
    per-DAY multiplicity (how many times that day was covered by one of the
    draw's resampled blocks), broadcasts it to a per-ROW weight via day_code,
    and applies the same weighted-Pearson-on-ranks formula.
    """
    rng = np.random.default_rng(int(seed))
    n_boot = int(n_boot); n_days = int(n_days)
    block_days = int(max(1, min(int(block_days), n_days)))
    n_blocks = int(np.ceil(n_days / block_days))
    starts = rng.integers(0, n_days, size=(n_boot, n_blocks))
    offsets = np.arange(block_days)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n_days       # circular wrap
    idx = idx.reshape(n_boot, n_blocks * block_days)[:, :n_days]        # trim to n_days/draw
    mult = np.zeros((n_boot, n_days), dtype=np.int32)
    rows = np.repeat(np.arange(n_boot), n_days)
    np.add.at(mult, (rows, idx.ravel()), 1)
    W = mult[:, day_code].astype(float)                    # (n_boot, n_obs)
    sw = W.sum(axis=1, keepdims=True)
    sw_safe = np.where(sw > 0, sw, 1.0)
    mx = (W * rx).sum(axis=1, keepdims=True) / sw_safe
    my = (W * ry).sum(axis=1, keepdims=True) / sw_safe
    dx = rx[None, :] - mx; dy = ry[None, :] - my
    cov = (W * dx * dy).sum(axis=1)
    vx = (W * dx * dx).sum(axis=1); vy = (W * dy * dy).sum(axis=1)
    den = np.sqrt(np.clip(vx * vy, 0, None))
    rho_boot = np.divide(cov, den, out=np.zeros_like(cov), where=den > 1e-12)
    lo, hi = np.percentile(rho_boot, [2.5, 97.5])
    return float(lo), float(hi)


def _autocorr_and_persistence(daily_series):
    """Lag-1 autocorrelation of a DAILY feature series (the feature's own full
    history -- NOT the trade-joined subset; persistence is a property of the
    feature itself, independent of when trades happened to fire) + a rough
    persistence length in trading days, via the AR(1) correlation-time closed
    form `1/(1-ac1)`, clipped to [1, BLOCK_DAYS_MAX]. Fewer than 30 usable
    (non-NaN) points -> (0.0, BLOCK_DAYS_MIN): too little history to call it
    slow, defaults to the minimum block length. Never raises (NaN/undefined
    autocorr, e.g. a constant series, also falls back to 0.0)."""
    s = pd.Series(daily_series).dropna()
    if len(s) < 30:
        return 0.0, float(BLOCK_DAYS_MIN)
    try:
        ac1 = s.autocorr(lag=1)
    except Exception:
        ac1 = None
    if ac1 is None or not np.isfinite(ac1):
        ac1 = 0.0
    ac1 = float(ac1)
    ac1_capped = min(ac1, 0.999)                            # guard 1/(1-ac1) blow-up near 1
    persistence = 1.0 / (1.0 - ac1_capped) if ac1_capped < 0.999 else float(BLOCK_DAYS_MAX)
    persistence = float(np.clip(persistence, 1.0, BLOCK_DAYS_MAX))
    return ac1, persistence


def _block_days_for(persistence_days):
    """Adaptive block length: `max(BLOCK_DAYS_MIN, round(persistence))`, capped
    at BLOCK_DAYS_MAX so the bootstrap stays computable even for a near-random-
    walk feature."""
    return int(min(max(BLOCK_DAYS_MIN, round(persistence_days)), BLOCK_DAYS_MAX))


def _era_ids(dates):
    """Assign each row (by its `datetime.date`) to an ERA: calendar YEAR when
    the sample spans >= 3 distinct years, else ~equal thirds by chronological
    order (a short backtest window with <3 calendar years still gets a usable
    era split). Returns (era_id array (int, 0-based), n_era_labels)."""
    dates = np.asarray(dates)
    years = np.array([d.year for d in dates])
    uniq_years = np.unique(years)
    if len(uniq_years) >= 3:
        y2e = {y: i for i, y in enumerate(uniq_years)}
        era = np.array([y2e[y] for y in years], dtype=int)
        return era, int(len(uniq_years))
    order = np.argsort(dates, kind="stable")
    n = len(dates)
    ranks = np.empty(n, dtype=int)
    ranks[order] = np.arange(n)
    era = np.minimum((ranks * 3) // max(n, 1), 2).astype(int)
    return era, 3


def _within_era_consistency(x, y, dates, rho_overall):
    """Split (x, y) by ERA (see _era_ids) and compute Spearman rho INSIDE each
    era with >= ERA_MIN_TRADES usable rows. A relationship that is real WITHIN
    eras survives this; one that only exists ACROSS eras (pure multi-year
    drift -- both series independently trending, no actual within-year link)
    fails it -- that's the artifact this whole guard exists to catch.

    Returns (rho_within, n_eras, era_consistent, era_pass, era_t):
      rho_within     : mean of the per-era rhos, EQUAL WEIGHT per era (so one
                       fat era can't dominate the average).
      n_eras         : count of eras with >= ERA_MIN_TRADES usable rows.
      era_consistent : fraction of those eras whose rho shares rho_overall's sign.
      era_t          : one-sample t statistic of the per-era rhos against 0
                       (mean / standard error ACROSS eras). This is the real
                       test and the sign-fraction is only a readability aid:
                       a sign fraction is nearly a coin flip at these counts
                       (11 of 17 eras sharing a sign is p~0.33 — no evidence at
                       all), whereas the t statistic asks the question that
                       matters — is the WITHIN-era effect consistently non-zero
                       relative to how much it scatters from era to era.
      era_pass       : n_eras >= ERA_MIN_ERAS AND |era_t| >= ERA_T_MIN AND
                       era_consistent >= ERA_CONSISTENT_MIN AND
                       sign(rho_within) == sign(rho_overall) (and rho_overall != 0).
    """
    era, _n_labels = _era_ids(dates)
    overall_sign = float(np.sign(rho_overall))
    era_rhos = []
    same_sign = 0
    for e in np.unique(era):
        m = era == e
        if int(m.sum()) < ERA_MIN_TRADES:
            continue
        xe, ye = x[m], y[m]
        if np.ptp(xe) <= 0 or np.ptp(ye) <= 0:
            continue                                        # degenerate inside this era
        re = _pearson(_rank(xe), _rank(ye))
        era_rhos.append(re)
        if overall_sign != 0 and np.sign(re) == overall_sign:
            same_sign += 1

    n_eras = len(era_rhos)
    if n_eras == 0:
        return 0.0, 0, 0.0, False, 0.0
    rho_within = float(np.mean(era_rhos))
    era_consistent = float(same_sign / n_eras)
    # t statistic of the per-era rhos vs 0 — mean over the standard error ACROSS
    # eras. A drift artifact produces tiny per-era rhos that scatter around zero,
    # so the mean is small relative to that scatter and t stays near 0 no matter
    # how many trades the pooled correlation had.
    if n_eras >= 2:
        sd = float(np.std(era_rhos, ddof=1))
        se = sd / np.sqrt(n_eras) if sd > 1e-12 else 0.0
        era_t = float(rho_within / se) if se > 1e-12 else 0.0
    else:
        era_t = 0.0
    era_pass = bool(overall_sign != 0 and n_eras >= ERA_MIN_ERAS
                    and abs(era_t) >= ERA_T_MIN
                    and era_consistent >= ERA_CONSISTENT_MIN
                    and np.sign(rho_within) == overall_sign)
    return rho_within, n_eras, era_consistent, era_pass, era_t


# ─────────────────────────────────────────────────────────────────────────────
# shadow probes (hand-rolled Boruta idea) — a noise floor real features must beat
# ─────────────────────────────────────────────────────────────────────────────

def _pick_probe_source_columns(daily_features, k):
    """The `k` column names to build shadow probes from: real feature columns
    ranked by non-NaN coverage over their OWN full daily series (most complete
    first, ties broken by original column order). Repeats columns (cycling the
    ranked list) when fewer than `k` distinct columns exist -- each repeat still
    gets its own independent shuffle in `_build_probe_daily`, so this degrades
    gracefully instead of requiring >=k real features to exist."""
    cols = list(daily_features.columns)
    if not cols:
        return []
    coverage = [int(daily_features[c].notna().sum()) for c in cols]
    order = sorted(range(len(cols)), key=lambda i: (-coverage[i], i))
    chosen = []
    j = 0
    while len(chosen) < k:
        chosen.append(cols[order[j % len(order)]])
        j += 1
    return chosen


def _build_probe_daily(daily_features, seed):
    """N_SHADOW_PROBES fake daily "features": each is a real feature column's
    VALUES shuffled across days (`np.random.default_rng` seeded off `seed`, a
    distinct sub-seed per probe via PROBE_SEED_STRIDE so same-seed calls are
    reproducible and multiple probes drawn from the same source column still
    differ). Shuffling preserves the column's marginal distribution exactly
    (same values, same NaN count) while destroying which date each value
    belongs to -- so a probe has, by construction, no real relationship to any
    trade's PnL. Returns (probe_df, probe_names); probe_df shares
    daily_features' index so it joins to trades exactly like a real feature.
    """
    src_cols = _pick_probe_source_columns(daily_features, N_SHADOW_PROBES)
    if not src_cols:
        return pd.DataFrame(index=daily_features.index), []
    data, names = {}, []
    for i, col in enumerate(src_cols):
        rng = np.random.default_rng(int(seed) + PROBE_SEED_STRIDE * (i + 1))
        vals = daily_features[col].to_numpy(copy=True)
        perm = rng.permutation(len(vals))
        pname = f"__probe{i}__"
        data[pname] = vals[perm]
        names.append(pname)
    return pd.DataFrame(data, index=daily_features.index), names


def _score_probes(joined, probe_names):
    """Each probe's Spearman rho vs PnL -- SAME join (already done by the
    caller, `joined` carries the probe columns alongside the real ones) and
    SAME rank-Pearson rho formula as a real feature. Deliberately skips the
    rest of a real feature's pipeline (CI/p/q/era) -- only the rho is needed
    for the noise floor, and those extra steps would ~double this function's
    runtime for no benefit. A probe that fails the same degenerate/too-few-
    trades checks a real feature would fail falls back to rho=0.0 (a neutral
    "carries no signal" default) rather than being dropped, so there are
    always exactly N_SHADOW_PROBES rhos to report and max over."""
    rhos = []
    for pname in probe_names:
        sub = joined[["pnl", pname]].dropna(subset=[pname])
        x = sub[pname].to_numpy(float)
        y = sub["pnl"].to_numpy(float)
        if len(x) < MIN_FEATURE_TRADES or np.ptp(x) <= 0 or np.ptp(y) <= 0:
            rhos.append(0.0)
            continue
        rhos.append(float(_pearson(_rank(x), _rank(y))))
    return rhos


# ─────────────────────────────────────────────────────────────────────────────
# joint importance layer (LASSO + RF permutation importance) — sklearn, info only
# ─────────────────────────────────────────────────────────────────────────────

def _rank_scale_01(values):
    """Rank-transform to [0, 1]: min value -> 0.0, max -> 1.0, ties get the
    average-rank treatment (same `_rank` used everywhere else in this module).
    Puts every feature -- a VIX level, a [0,1] efficiency ratio, a signed
    streak count -- on the same scale so LASSO/RF coefficients & importances
    are comparable across features instead of dominated by raw units."""
    r = _rank(values)
    n = len(r)
    if n <= 1:
        return np.zeros(n)
    return (r - 1.0) / (n - 1.0)


def _joint_importance(joined, scored_names, probe_names, seed=42):
    """Joint multivariate importance: fits LASSO + a random forest on ALL
    scored real features TOGETHER (+ the probes, for a noise floor inside the
    joint model too), on the COMPLETE-CASE matrix (every row -- trade --
    non-NaN across every one of those columns). Pure INFORMATION layer: never
    feeds back into `survives`. Univariate rho (above) can't tell two
    collinear features apart -- both "explain" PnL alone -- this can, because
    a linear/tree model fit on both at once has to choose how to split credit
    between them.

    X = each column RANK-transformed to [0,1] (see _rank_scale_01). y = raw
    per-trade PnL (unscaled -- fine, X's uniform scaling is what makes
    cross-feature coefficients/importances comparable).
      lasso_coef / lasso_kept : sklearn.linear_model.LassoCV(cv=5,
        random_state=seed) coefficient per feature; "kept" = |coef| >
        LASSO_KEPT_EPS (LassoCV rarely lands exactly on 0.0 for a dropped
        feature).
      rf_imp / rf_beats_probe : mean permutation importance (10 repeats) of a
        RandomForestRegressor(n_estimators=200, max_depth=5,
        random_state=seed, n_jobs=-1) fit on the same X/y; "beats_probe" =
        rf_imp > the max rf_imp among the 3 probe columns (the RF's OWN noise
        floor, distinct from the univariate probe_max_abs_rho above).

    Returns (meta_dict, per_feature_dict) where per_feature_dict maps real
    feature name -> {lasso_coef, lasso_kept, rf_imp, rf_beats_probe}, or
    (None, {}) when there are fewer than MIN_JOINT_ROWS complete rows, sklearn
    can't be imported, or the fit raises for any reason -- this NEVER raises
    out to the caller, matching this module's "never break a backtest" rule.
    """
    cols = list(scored_names) + list(probe_names)
    if not cols:
        return None, {}
    cc = joined.dropna(subset=cols)
    n_used = int(len(cc))
    if n_used < MIN_JOINT_ROWS:
        return None, {}
    try:
        from sklearn.linear_model import LassoCV
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.inspection import permutation_importance
    except Exception:
        return None, {}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            X = np.column_stack([_rank_scale_01(cc[c].to_numpy(float)) for c in cols])
            y = cc["pnl"].to_numpy(float)

            lasso = LassoCV(cv=5, random_state=int(seed), max_iter=5000).fit(X, y)
            lasso_coef = {c: float(v) for c, v in zip(cols, lasso.coef_)}

            rf = RandomForestRegressor(n_estimators=200, max_depth=5,
                                       random_state=int(seed), n_jobs=-1).fit(X, y)
            # permutation_importance calls rf.predict() ~n_repeats*n_features times;
            # a 200-tree/depth-5 predict on a few thousand rows is trivially fast
            # single-threaded, but predict() inherits the estimator's n_jobs, and on
            # Windows each of those calls re-spins a whole loky process pool (measured
            # ~1s+ of pure pool teardown/startup PER CALL -- see this function's
            # docstring runtime note) instead of reusing one. n_jobs=-1 stays on the
            # FIT (one bagged-ensemble build, genuinely worth parallelizing) and is
            # dropped to 1 only for the predict-heavy permutation loop.
            rf.n_jobs = 1
            perm = permutation_importance(rf, X, y, n_repeats=10, random_state=int(seed))
            rf_imp = {c: float(v) for c, v in zip(cols, perm.importances_mean)}
    except Exception:
        return None, {}

    rf_probe_floor = max((rf_imp[p] for p in probe_names), default=0.0)
    probes_kept_lasso = int(sum(1 for p in probe_names
                                if abs(lasso_coef.get(p, 0.0)) > LASSO_KEPT_EPS))

    per_feature = {}
    for c in scored_names:
        coef = lasso_coef.get(c, 0.0)
        imp = rf_imp.get(c, 0.0)
        per_feature[c] = {
            "lasso_coef": round(coef, 6),
            "lasso_kept": bool(abs(coef) > LASSO_KEPT_EPS),
            "rf_imp": round(imp, 6),
            "rf_beats_probe": bool(imp > rf_probe_floor),
        }

    meta = {
        "n_used": n_used,
        "rf_probe_floor": round(float(rf_probe_floor), 6),
        "probes_kept_lasso": probes_kept_lasso,
        "lasso_alpha": round(float(lasso.alpha_), 6),
    }
    return meta, per_feature


def context_scores(trades, index, daily_features, n_boot=DEFAULT_BLOCK_N_BOOT, seed=42):
    """The stats core: join each trade's ENTRY bar -> entry date -> that date's
    row in `daily_features` (already prior-day-shifted — see build_internal_daily
    / fetch_external_daily), then score every feature's relationship to
    per-trade PnL.

    trades         : (entry_i, exit_i, pnl[, side, entry_px]) tuples — same shape
                     `analytics.regime_report` takes. `pnl` (t[2]) is scored AS
                     GIVEN — context_scores does not itself subtract any cost
                     (see build_context, which nets cost_pts before calling in).
    index          : the run's bar-level index (same one `daily_features` was
                     built from) — used only to map entry_i -> entry date.
    daily_features : DataFrame indexed by date, columns = feature name -> value.

    Per feature: Spearman rho (primary, rank-robust) + Pearson r; a 95% CI from
    a MOVING-BLOCK bootstrap (see _block_bootstrap_ci) that resamples
    contiguous blocks of consecutive trading days -- clustered by entry day
    like before, but ALSO robust to multi-day/week/month persistence, which a
    plain day-clustered bootstrap (still available as _clustered_bootstrap_ci)
    does not protect against; Benjamini-Hochberg FDR across every scored
    feature (q < FDR_Q). A feature is dropped (not scored) when fewer than
    MIN_FEATURE_TRADES trades have a non-NaN value for it, or fewer than
    MIN_FEATURE_DAYS distinct entry days, or it has zero variation.

    ERA-AWARE GUARD (the point of this module's revamp): slow macro features
    (tnx, curve, vix levels, ...) drift over YEARS, and strategy performance
    varies by era too -- two things that both drift over a decade correlate
    whether or not one causes the other, so a raw whole-history q-value can
    "survive" on pure drift. Per feature this also computes:
      autocorr       : lag-1 autocorrelation of the feature's own daily series.
      slow           : bool, autocorr >= SLOW_AUTOCORR -- a persistent/macro-
                       drifting feature, subject to the era gate below.
      rho_within     : mean of the per-CALENDAR-YEAR-era Spearman rhos (equal
                       weight per era; falls back to ~thirds if <3 years).
      n_eras         : eras with >= ERA_MIN_TRADES usable trades.
      era_consistent : fraction of those eras whose rho shares the overall
                       rho's sign.
      era_pass       : n_eras >= ERA_MIN_ERAS AND era_consistent >=
                       ERA_CONSISTENT_MIN AND sign(rho_within) == sign(rho).
    SHADOW PROBES (see _build_probe_daily/_score_probes): N_SHADOW_PROBES=3 fake
    features, each a real feature column shuffled across days (same marginal
    distribution, zero true relationship to any trade). Every real feature adds:
      probe_margin   : round(|rho| - probe_max_abs_rho, 4) -- how far above (or
                       below, if negative) the noise floor this feature's |rho|
                       sits.
      beats_probe    : bool, |rho| > probe_max_abs_rho.
    `survives` now ALSO requires beats_probe -- a feature that only cleared
    FDR/CI/era because the bar happened to be low for this dataset gets caught
    here. `trend_confounded`'s meaning is unchanged (probes don't feed it).

    JOINT IMPORTANCE (see _joint_importance): an INFORMATION-ONLY layer (never
    gates `survives`) that fits LASSO + a random forest on every scored feature
    (+ the 3 probes) TOGETHER on the complete-case matrix, so two collinear
    features that both look good univariately can be told apart. Every real
    feature adds (None for all four when the joint layer was skipped):
      lasso_coef     : LassoCV(cv=5, random_state=seed) coefficient.
      lasso_kept     : bool, |lasso_coef| > LASSO_KEPT_EPS.
      rf_imp         : mean permutation importance (10 repeats) from a
                       RandomForestRegressor(200 trees, depth 5, random_state=seed).
      rf_beats_probe : bool, rf_imp > the max rf_imp among the 3 probes.

    Returns {"features": [{name, rho, r, ci_lo, ci_hi, n, p, q, survives,
    rho_within, n_eras, era_consistent, era_pass, autocorr, slow,
    trend_confounded, probe_margin, beats_probe, lasso_coef, lasso_kept,
    rf_imp, rf_beats_probe}, ...] sorted by |rho| desc, "n_trades", "n_days",
    "external_available", "probe_max_abs_rho" (max |rho| among the 3 probes),
    "probe_rhos" (the 3 individual probe rhos), "joint" (the _joint_importance
    meta dict -- n_used/rf_probe_floor/probes_kept_lasso/lasso_alpha -- or None
    when skipped: <MIN_JOINT_ROWS complete rows or sklearn unavailable)} —
    every value a native python type (JSON-safe) — or None when fewer than
    MIN_TRADES trades joined to a valid entry-date row.
    """
    if not trades or daily_features is None or not len(daily_features):
        return None
    eix = pd.to_datetime(pd.Series(index))
    dts = eix.dt.date.values
    nb = len(dts)
    feat_index = set(daily_features.index)
    rows = []
    for t in trades:
        eb = int(t[0]); pnl = float(t[2])
        if eb < 0 or eb >= nb:
            continue
        d = dts[eb]
        if d not in feat_index:
            continue
        rows.append((d, pnl))
    if len(rows) < MIN_TRADES:
        return None

    base = pd.DataFrame(rows, columns=["date", "pnl"])
    probe_df, probe_names = _build_probe_daily(daily_features, seed)
    daily_all = daily_features.join(probe_df) if len(probe_df.columns) else daily_features
    joined = base.join(daily_all, on="date")
    n_trades = int(len(joined))
    n_days = int(joined["date"].nunique())
    ext_available = any(c in joined.columns and joined[c].notna().any()
                        for c in EXTERNAL_FEATURES)

    probe_rhos = _score_probes(joined, probe_names)
    probe_max_abs_rho = max((abs(r) for r in probe_rhos), default=0.0)

    # feat_cols is drawn from daily_features (not daily_all) -- probes are
    # NEVER treated as scoreable "real" features, matching the module contract.
    feat_cols = [c for c in daily_features.columns if c in joined.columns]
    out_rows, pvals = [], []
    for col in feat_cols:
        sub = joined[["date", "pnl", col]].dropna(subset=[col])
        n = len(sub)
        if n < MIN_FEATURE_TRADES:
            continue
        x = sub[col].to_numpy(float)
        y = sub["pnl"].to_numpy(float)
        days = sub["date"].to_numpy()
        if np.ptp(x) <= 0 or np.ptp(y) <= 0:
            continue                                       # degenerate -- no variation
        uniq_days, day_code = np.unique(days, return_inverse=True)
        if len(uniq_days) < MIN_FEATURE_DAYS:
            continue

        rx, ry = _rank(x), _rank(y)
        rho = _pearson(rx, ry)
        r = _pearson(x, y)
        p, _method = _pvalue(x, y, rho, days, seed=seed)

        # persistence / slow-feature flag -- from the feature's OWN full daily
        # series (build_internal_daily/fetch_external_daily's column), not the
        # trade-joined subset: drift is a property of the feature, independent
        # of when trades happened to fire.
        autocorr, persistence_days = _autocorr_and_persistence(daily_features[col])
        slow = bool(autocorr >= SLOW_AUTOCORR)
        block_days = _block_days_for(persistence_days)
        ci_lo, ci_hi = _block_bootstrap_ci(rx, ry, day_code, len(uniq_days),
                                           block_days, n_boot, seed)

        rho_within, n_eras, era_consistent, era_pass, era_t = _within_era_consistency(
            x, y, days, rho)

        # shadow-probe margin -- how far this feature's |rho| sits above (or
        # below) the noise floor set by the 3 shuffled probes.
        abs_rho = abs(float(rho))
        probe_margin = round(abs_rho - probe_max_abs_rho, 4)
        beats_probe = bool(abs_rho > probe_max_abs_rho)

        out_rows.append({"name": col, "rho": round(float(rho), 4),
                         "r": round(float(r), 4), "ci_lo": round(ci_lo, 4),
                         "ci_hi": round(ci_hi, 4), "n": int(n),
                         "p": round(float(p), 4),
                         "rho_within": round(rho_within, 4),
                         "n_eras": int(n_eras),
                         "era_consistent": round(era_consistent, 4),
                         "era_pass": bool(era_pass),
                         "era_t": round(float(era_t), 3),
                         "autocorr": round(float(autocorr), 4),
                         "slow": bool(slow),
                         "probe_margin": probe_margin,
                         "beats_probe": beats_probe})
        pvals.append(float(p))

    if not out_rows:
        return {"features": [], "n_trades": n_trades, "n_days": n_days,
                "external_available": bool(ext_available),
                "probe_max_abs_rho": round(float(probe_max_abs_rho), 4),
                "probe_rhos": [round(float(r), 4) for r in probe_rhos],
                "joint": None}

    qvals = _bh_fdr(pvals)
    for row, q in zip(out_rows, qvals):
        row["q"] = round(float(q), 4)
        # `q` comes from the NAIVE (day-level) p-value pipeline, which treats
        # neighbouring days as independent — overconfident for a persistent
        # feature. So it is NOT the survival test on its own: a feature must ALSO
        # have a block-bootstrap CI (the honest one, computed from month-scale
        # blocks above) that excludes zero. Keeping the naive q is what lets
        # `trend_confounded` say "this LOOKED significant the naive way and then
        # failed the honest checks" — the flag would never fire if the naive
        # number were thrown away.
        q_survives = bool(q < FDR_Q)
        ci_excludes_zero = bool((row["ci_lo"] > 0 and row["ci_hi"] > 0)
                                or (row["ci_lo"] < 0 and row["ci_hi"] < 0))
        era_ok = bool(row["era_pass"] if row["slow"] else True)
        row["ci_excludes_zero"] = ci_excludes_zero
        # `beats_probe` (shadow-probe gate) is ANDed in on top of the existing
        # q/CI/era conditions -- tightens survival, never loosens it: a row
        # that was already going to fail stays failed either way (AND with an
        # extra term can't flip False -> True). `trend_confounded`'s formula
        # is intentionally untouched -- probes are a separate, additive gate.
        row["survives"] = bool(q_survives and ci_excludes_zero and era_ok
                               and row["beats_probe"])
        row["trend_confounded"] = bool(row["slow"] and q_survives
                                       and not (ci_excludes_zero and era_ok))

    # joint importance layer (LASSO + RF permutation) -- see _joint_importance;
    # computed once over every scored real feature + the 3 probes together.
    # Belt-and-suspenders try/except even though _joint_importance already
    # catches internally: this module's rule is NEVER raise out of
    # context_scores, no matter what.
    scored_names = [row["name"] for row in out_rows]
    try:
        joint_meta, joint_per_feature = _joint_importance(joined, scored_names,
                                                           probe_names, seed=seed)
    except Exception:
        joint_meta, joint_per_feature = None, {}
    for row in out_rows:
        jf = joint_per_feature.get(row["name"])
        if jf:
            row.update(jf)
        else:
            row["lasso_coef"] = None
            row["lasso_kept"] = None
            row["rf_imp"] = None
            row["rf_beats_probe"] = None

    out_rows.sort(key=lambda row: abs(row["rho"]), reverse=True)
    return {"features": out_rows, "n_trades": n_trades, "n_days": n_days,
            "external_available": bool(ext_available),
            "probe_max_abs_rho": round(float(probe_max_abs_rho), 4),
            "probe_rhos": [round(float(r), 4) for r in probe_rhos],
            "joint": joint_meta}


# ─────────────────────────────────────────────────────────────────────────────
# build_context — one-call wiring helper (optimize.py / auto.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_context(trades, index, opens, highs, lows, closes, cost_pts=0.0,
                  n_boot=DEFAULT_BLOCK_N_BOOT, seed=42, external=True):
    """Wiring helper: builds the internal (+ external, best-effort) daily feature
    frame and scores it against `trades`. NEVER raises — any failure (bad data,
    network hiccup, too few trades) returns None so a backtest can never break
    because of this feature, same discipline as `analytics.regime_report` being
    wrapped in try/except at its call sites.

    `cost_pts` matches `regime_report`'s own convention: each trade's pnl (t[2])
    is treated as GROSS and `pnl - cost_pts` is what actually gets scored.

    `n_boot` now drives the MOVING-BLOCK bootstrap in context_scores (see its
    docstring) -- default dropped from the old day-bootstrap's 1000 to 500
    (DEFAULT_BLOCK_N_BOOT): each block draw is costlier than a single-day draw
    (it covers a whole 21-126 trading-day block, not one row-weight lookup),
    and 500 draws is already plenty for a stable 95% percentile estimate.
    """
    try:
        if not trades or index is None or len(index) == 0:
            return None
        net_trades = [(t[0], t[1], float(t[2]) - float(cost_pts)) + tuple(t[3:])
                      for t in trades]
        daily = build_internal_daily(index, opens, highs, lows, closes)
        if external:
            try:
                eix = pd.to_datetime(pd.Series(index))
                ext = fetch_external_daily(str(eix.min().date()), str(eix.max().date()))
            except Exception:
                ext = None
            if ext is not None and len(ext):
                daily = daily.join(ext, how="left")
        return context_scores(net_trades, index, daily, n_boot=n_boot, seed=seed)
    except Exception:
        return None

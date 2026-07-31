"""TRADE CONTEXT (stages 1+2) — augur_engine/context.py

Answers "which market features plausibly explain trade performance?": enrich each
backtest trade with what the market was doing at ENTRY (prior-day-close features,
strictly causal — a trade entering on day D only ever sees information knowable
before day D's session opens), then score feature -> per-trade-PnL relationships
with Spearman/Pearson + a clustered-bootstrap CI + Benjamini-Hochberg FDR. The
result is the JSON-safe `result["context"]` block (wired into optimize.py/auto.py
next to `analytics.regime_report`) the web can later render as a bar panel, the
same way `analytics.relationship_scores` feeds the existing PARAM RELATIONSHIP
panel.

Four pieces, same "never break a backtest" discipline as analytics.py:
  * build_internal_daily — daily features from the run's OWN bar arrays (no
    network). Every feature is shifted +1 day EXCEPT gap_pct (see its docstring).
  * fetch_external_daily — ^VIX/^VIX3M/^TNX/^IRX daily features from yfinance,
    CSV-cached in augur_uploads/_context/, fail-soft on ANY network hiccup.
  * context_scores       — the stats core: join trades -> entry-day features,
    Spearman rho (primary) + Pearson r, a 95% CI from a bootstrap CLUSTERED by
    entry day (trades on the same day share the same context row — a naive
    per-trade bootstrap would be falsely tight), and BH-FDR across features.
  * build_context        — the one-call wiring helper optimize.py/auto.py use:
    ties the three together and NEVER raises (returns None on any failure).
"""
import os

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


def context_scores(trades, index, daily_features, n_boot=1000, seed=42):
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
    a bootstrap CLUSTERED by entry day (trades sharing a day share the SAME
    context row, so resampling individual trades would be falsely tight);
    Benjamini-Hochberg FDR across every scored feature (q < FDR_Q -> `survives`).
    A feature is dropped (not scored) when fewer than MIN_FEATURE_TRADES trades
    have a non-NaN value for it, or fewer than MIN_FEATURE_DAYS distinct entry
    days, or it has zero variation.

    Returns {"features": [{name, rho, r, ci_lo, ci_hi, n, p, q, survives}, ...]
    sorted by |rho| desc, "n_trades", "n_days", "external_available"} — every
    value a native python type (JSON-safe) — or None when fewer than MIN_TRADES
    trades joined to a valid entry-date row.
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
    joined = base.join(daily_features, on="date")
    n_trades = int(len(joined))
    n_days = int(joined["date"].nunique())
    ext_available = any(c in joined.columns and joined[c].notna().any()
                        for c in EXTERNAL_FEATURES)

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
        ci_lo, ci_hi = _clustered_bootstrap_ci(rx, ry, day_code, len(uniq_days),
                                               n_boot, seed)

        out_rows.append({"name": col, "rho": round(float(rho), 4),
                         "r": round(float(r), 4), "ci_lo": round(ci_lo, 4),
                         "ci_hi": round(ci_hi, 4), "n": int(n),
                         "p": round(float(p), 4)})
        pvals.append(float(p))

    if not out_rows:
        return {"features": [], "n_trades": n_trades, "n_days": n_days,
                "external_available": bool(ext_available)}

    qvals = _bh_fdr(pvals)
    for row, q in zip(out_rows, qvals):
        row["q"] = round(float(q), 4)
        row["survives"] = bool(q < FDR_Q)

    out_rows.sort(key=lambda row: abs(row["rho"]), reverse=True)
    return {"features": out_rows, "n_trades": n_trades, "n_days": n_days,
            "external_available": bool(ext_available)}


# ─────────────────────────────────────────────────────────────────────────────
# build_context — one-call wiring helper (optimize.py / auto.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_context(trades, index, opens, highs, lows, closes, cost_pts=0.0,
                  n_boot=1000, seed=42, external=True):
    """Wiring helper: builds the internal (+ external, best-effort) daily feature
    frame and scores it against `trades`. NEVER raises — any failure (bad data,
    network hiccup, too few trades) returns None so a backtest can never break
    because of this feature, same discipline as `analytics.regime_report` being
    wrapped in try/except at its call sites.

    `cost_pts` matches `regime_report`'s own convention: each trade's pnl (t[2])
    is treated as GROSS and `pnl - cost_pts` is what actually gets scored.
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

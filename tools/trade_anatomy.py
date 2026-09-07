"""
tools/trade_anatomy.py — PER-TRADE MARKET ANATOMY (exploratory half of research;
tools/feature_board.py is the confirmatory half).

For a crowned strategy leg, this builds one row per trade describing what the market
looked like structurally and dynamically in the bars right before the trade fired —
so a human can eyeball winners vs losers and hypothesise NEW entry conditions. It does
NOT test any promotion rule; everything here is a single-leg, single-peek exploration
that must still clear tools/feature_board.py-style cross-family validation and a fenced
Auto-Validate before anything gets adopted.

DISCOVERY WINDOW (hard rule): only the first 60% of a leg's PRE-LOCKBOX span, by
CALENDAR DATE (not trade count), is mined. The remaining 40% pre-lockbox trades are
HOLDOUT, touched exactly once (the pre-registered skip-rule check in RULE MINING).
Lockbox trades (the leg's last N months, per its own Firestore doc) are EXCLUDED
ENTIRELY — never loaded into the feature frame at all.

CAUSALITY: every feature is read at the DECISION bar = entry_bar - 1. Nothing at or
after the entry bar is ever touched while building a feature. Distances are expressed
in ATR units: a 14-bar ATR of the leg's own bar size for anything at bar/60-minute
scale, and a 14-DAY daily ATR for anything at daily scale (SMA20/50/200-day distance,
prior-week high/low distance) — see the lvl_/ind_ blocks in build_feature_matrix() below
for exactly which ATR series backs each column.

REUSE: this file deliberately does NOT re-implement the leg loader. `run_strategy_full`
below is `feature_board.run_strategy` with the same dispatch (feature_board._mod /
feature_board._resolve_kwargs, unchanged) minus its 3-tuple truncation — build_leg's own
cached dict never keeps the exit bar / side / entry price, which this file needs for
hold_bars / MFE / MAE / side, so the strategy is run through feature_board.load +
feature_board.resolve_leg_config directly instead of through build_leg (skips
feature_board's own — unused here — causal feature matrix + macro fetch, which is most
of build_leg's several-minutes cost; the strategy replay itself is ~1-2s per leg).
Everything else that IS reusable is reused verbatim: feature_board.load,
feature_board.resolve_leg_config, feature_board.hourly_compression,
feature_board.LEGS, feature_board._lockbox_from_date, feature_board's LIFT primitives
(_lift_threshold_spec / _lift_masks / _lift_r / _lift_perm_pvalue), and
augur_engine.context._bh_fdr / _rolling_pctile.

Usage:
  python tools/trade_anatomy.py --leg NOISE_243 --leg ORB_314   # default = these two
"""
import os
import sys
import json
import time
import inspect
import argparse
import datetime
import importlib.util as _ilu
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
DOCS_ROOT = os.path.join(ROOT, "docs", "anatomy")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import context as ctx    # noqa: E402  (reused stats primitives)

DISCOVERY_FRAC = 0.6
OR_MINUTES = 30
YEAR_DAYS = 252
LIFT_N_PERM = 1000
LIFT_BLOCK_DAYS = 21
SEED = 42


def _load_feature_board():
    fp = os.path.join(ROOT, "tools", "feature_board.py")
    spec = _ilu.spec_from_file_location("feature_board_reuse", fp)
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FB = _load_feature_board()


# ─────────────────────────────────────────────────────────────────────────────
# leg replay — same dispatch as feature_board.run_strategy, kept as the FULL
# 5-tuple (entry_bar, exit_bar, pnl_points, side, entry_price) instead of the
# 3-tuple feature_board truncates to (it only needs entry_bar + pnl there).
# ─────────────────────────────────────────────────────────────────────────────

def run_strategy_full(fn, df, best_params):
    path = os.path.join(FB.ROOT, "augur_strategies", fn)
    if not os.path.exists(path):
        path = os.path.join(FB.SHARED, "augur_strategies", fn)
    m = FB._mod(path, fn.replace(".py", "_anat"))
    kw, defaults = FB._resolve_kwargs(m, best_params)
    sp = inspect.signature(m.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    if not hk:
        kw = {k: v for k, v in kw.items() if k in sp}
    ex = {}
    if "volumes" in sp or hk:
        ex["volumes"] = df["volume"].values if "volume" in df else None
    if "day_id" in sp or hk:
        ex["day_id"] = df["day_id"].values
    if "index" in sp or hk:
        ex["index"] = df["_dt"]
    try:
        r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                           df["close"].values, return_trades=True, **ex, **kw)
    except TypeError:
        r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                           df["close"].values, return_trades=True, **ex, **defaults)
    if not r or not r.get("trades"):
        return None
    out = []
    for t in r["trades"]:
        eb, xb, pnl = int(t[0]), int(t[1]), float(t[2])
        side = int(t[3]) if len(t) > 3 else 0
        entry_px = float(t[4]) if len(t) > 4 else np.nan
        out.append((eb, xb, pnl, side, entry_px))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# small causal indicator primitives (all backward-looking pandas rolling/ewm —
# a value at row i is a function of rows <= i only)
# ─────────────────────────────────────────────────────────────────────────────

def calc_atr(h, l, c, period=14):
    h, l, c = pd.Series(h, dtype=float), pd.Series(l, dtype=float), pd.Series(c, dtype=float)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean().to_numpy()


def calc_rsi(c, period=14):
    c = pd.Series(c, dtype=float)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return rsi.to_numpy()


def calc_adx(h, l, c, period=14):
    h, l, c = pd.Series(h, dtype=float), pd.Series(l, dtype=float), pd.Series(c, dtype=float)
    up = h.diff()
    down = -l.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0))
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0))
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.rolling(period, min_periods=period).mean() / atr.replace(0.0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(period, min_periods=period).mean() / atr.replace(0.0, np.nan)
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    return dx.rolling(period, min_periods=period).mean().to_numpy()


def calc_ema(c, span):
    return pd.Series(c, dtype=float).ewm(span=span, adjust=False).mean().to_numpy()


def calc_macd_hist(c, fast=12, slow=26, signal=9):
    c = pd.Series(c, dtype=float)
    ema_f = c.ewm(span=fast, adjust=False).mean()
    ema_s = c.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    return (macd - sig).to_numpy()


def calc_efficiency_ratio(c, period=20):
    c = pd.Series(c, dtype=float)
    net = c.diff(period).abs()
    path = c.diff().abs().rolling(period, min_periods=period).sum()
    return (net / path.replace(0.0, np.nan)).clip(0, 1).to_numpy()


def calc_bb_width(c, period=20, k=2.0):
    c = pd.Series(c, dtype=float)
    sma = c.rolling(period, min_periods=period).mean()
    std = c.rolling(period, min_periods=period).std()
    return ((2.0 * k * std) / sma.replace(0.0, np.nan)).to_numpy()


def rolling_pctile(x, window, min_periods=None):
    return ctx._rolling_pctile(pd.Series(x, dtype=float), window=window, min_periods=min_periods).to_numpy()


# ─────────────────────────────────────────────────────────────────────────────
# higher-timeframe (60-minute) causal construction — verbatim pattern from
# feature_board.hourly_compression, generalized to return the OHLC bars
# themselves (not just the squeeze flag) plus a causal-map helper so any
# per-htf-bar series can be joined back onto df's own bar index.
# ─────────────────────────────────────────────────────────────────────────────

def build_htf_bars(df, tf_min):
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"].astype(str) + "_" + (off // int(tf_min)).astype(str).str.zfill(4)
    g = df.groupby(key, sort=True)
    o, h, l, c = g["open"].first().values, g["high"].max().values, g["low"].min().values, g["close"].last().values
    end = g["_end"].last().values
    order = np.argsort(end)
    return pd.DataFrame({"open": o[order], "high": h[order], "low": l[order],
                         "close": c[order], "end": end[order]})


def causal_map(df_end, htf_end, series_values, warm=0):
    """Map a per-htf-bar series onto df's bar index: df bar i sees the LATEST
    htf bar that had already CLOSED as of df's own bar close (df_end[i])."""
    series_values = np.asarray(series_values)
    j = np.searchsorted(htf_end, df_end, side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(series_values) - 1)
    return np.where(ok, series_values[jj], np.nan)


# ─────────────────────────────────────────────────────────────────────────────
# whole-dataframe bar-level + 60m-mapped + session/OR/VWAP/volume arrays,
# computed ONCE per leg (vectorized), then indexed per-trade at the decision bar
# ─────────────────────────────────────────────────────────────────────────────

def build_bar_arrays(df, tf_min):
    n = len(df)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    has_vol = "volume" in df.columns
    volume = df["volume"].to_numpy(float) if has_vol else None

    B = {}
    B["close"], B["open"], B["high"], B["low"] = close, open_, high, low
    B["ret"] = np.diff(close, prepend=np.nan)
    B["atr_bar"] = calc_atr(high, low, close, 14)
    B["rsi_bar"] = calc_rsi(close, 14)
    B["adx_bar"] = calc_adx(high, low, close, 14)
    B["ema20_bar"] = calc_ema(close, 20)
    B["ema50_bar"] = calc_ema(close, 50)
    B["ema200_bar"] = calc_ema(close, 200)
    B["macd_bar"] = calc_macd_hist(close)
    B["er20_bar"] = calc_efficiency_ratio(close, 20)
    bbw_bar = calc_bb_width(close, 20, 2.0)

    bars_per_day = max(1, int(round(df.groupby("day_id").size().median())))
    win_bar_yr = max(60, bars_per_day * YEAR_DAYS)
    B["atr_pctile_bar"] = rolling_pctile(B["atr_bar"], win_bar_yr, min_periods=max(60, win_bar_yr // 4))
    B["bbw_pctile_bar"] = rolling_pctile(bbw_bar, win_bar_yr, min_periods=max(60, win_bar_yr // 4))

    # ── rolling path-shape stats (vectorized over the whole df once) ──
    hi_s, lo_s, cl_s = pd.Series(high), pd.Series(low), pd.Series(close)
    for w in (10, 20, 60):
        hw = hi_s.rolling(w, min_periods=w).max()
        lw = lo_s.rolling(w, min_periods=w).min()
        B[f"closepos{w}"] = ((cl_s - lw) / (hw - lw).replace(0.0, np.nan)).to_numpy()
    for w in (5, 10, 20):
        hw = hi_s.rolling(w, min_periods=w).max()
        lw = lo_s.rolling(w, min_periods=w).min()
        B[f"range{w}_atr"] = ((hw - lw)).to_numpy()   # divided by decision-bar ATR at assembly time
    up = (cl_s > pd.Series(open_)).astype(float)
    for w in (5, 10):
        B[f"upcount{w}"] = up.rolling(w, min_periods=w).sum().to_numpy()
    B["bars_since_hi20"] = hi_s.rolling(20, min_periods=20).apply(
        lambda x: float(len(x) - 1 - np.argmax(x)), raw=True).to_numpy()
    B["bars_since_lo20"] = lo_s.rolling(20, min_periods=20).apply(
        lambda x: float(len(x) - 1 - np.argmin(x)), raw=True).to_numpy()
    body = (cl_s - pd.Series(open_)).abs()
    rng = (hi_s - lo_s).replace(0.0, np.nan)
    B["body_ratio"] = (body / rng).to_numpy()
    B["upper_wick"] = ((hi_s - pd.concat([pd.Series(open_), cl_s], axis=1).max(axis=1)) / rng).to_numpy()
    B["lower_wick"] = ((pd.concat([pd.Series(open_), cl_s], axis=1).min(axis=1) - lo_s) / rng).to_numpy()

    # ── 60-minute higher-timeframe indicators, causally mapped back onto df ──
    htf = build_htf_bars(df, 60)
    warm60 = 20 * 2 + 5
    ho, hh, hl, hc = htf["open"].to_numpy(), htf["high"].to_numpy(), htf["low"].to_numpy(), htf["close"].to_numpy()
    n_days = max(1, df["day_id"].nunique())
    bars_per_day_60 = max(1, len(htf) / n_days)
    win_60_yr = max(30, int(round(bars_per_day_60 * YEAR_DAYS)))
    # NOTE: use .values (not .to_numpy()) for tz-aware datetime columns -- pandas
    # normalizes tz-aware .values to naive-UTC datetime64[ns] consistently on both
    # sides, matching feature_board.hourly_compression's own working pattern;
    # .to_numpy() instead returns tz-aware Timestamp OBJECTS, which searchsorted
    # cannot compare against the naive array on the other side.
    htf_end = htf["end"].values
    df_end = df["_end"].values
    B["rsi_60m"] = causal_map(df_end, htf_end, calc_rsi(hc, 14), warm60)
    B["adx_60m"] = causal_map(df_end, htf_end, calc_adx(hh, hl, hc, 14), warm60)
    B["ema20_60m"] = causal_map(df_end, htf_end, calc_ema(hc, 20), warm60)
    B["ema50_60m"] = causal_map(df_end, htf_end, calc_ema(hc, 50), warm60)
    B["macd_60m"] = causal_map(df_end, htf_end, calc_macd_hist(hc), warm60)
    B["er20_60m"] = causal_map(df_end, htf_end, calc_efficiency_ratio(hc, 20), warm60)
    atr_60 = calc_atr(hh, hl, hc, 14)
    bbw_60 = calc_bb_width(hc, 20, 2.0)
    B["atr_pctile_60m"] = causal_map(df_end, htf_end,
                                     rolling_pctile(atr_60, win_60_yr, min_periods=max(30, win_60_yr // 4)), warm60)
    B["bbw_pctile_60m"] = causal_map(df_end, htf_end,
                                     rolling_pctile(bbw_60, win_60_yr, min_periods=max(30, win_60_yr // 4)), warm60)

    comp = FB.hourly_compression(df)
    B["compressed_60m"] = comp.astype(float)

    # ── session/opening-range/VWAP/volume, all per-bar (day-local) ──
    B["session_open"] = df.groupby("day_id")["open"].transform("first").to_numpy()
    sess_open_time = df.groupby("day_id")["_dt"].transform("first")
    B["mins_since_open"] = ((df["_dt"] - sess_open_time).dt.total_seconds() / 60.0).to_numpy()
    bar_of_day = df.groupby("day_id").cumcount().to_numpy()
    B["bar_of_day"] = bar_of_day
    num_or_bars = max(1, OR_MINUTES // int(tf_min))
    or_mask = bar_of_day < num_or_bars
    or_hi_day = df.loc[or_mask].groupby("day_id")["high"].max()
    or_lo_day = df.loc[or_mask].groupby("day_id")["low"].min()
    or_hi = df["day_id"].map(or_hi_day).to_numpy()
    or_lo = df["day_id"].map(or_lo_day).to_numpy()
    or_ready = bar_of_day >= num_or_bars
    B["or_hi"] = np.where(or_ready, or_hi, np.nan)
    B["or_lo"] = np.where(or_ready, or_lo, np.nan)

    if has_vol:
        tp = (high + low + close) / 3.0
        pv = pd.Series(tp * volume)
        cum_pv = pv.groupby(df["day_id"].to_numpy()).cumsum()
        cum_vol = pd.Series(volume).groupby(df["day_id"].to_numpy()).cumsum()
        B["vwap"] = (cum_pv / cum_vol.replace(0.0, np.nan)).to_numpy()
        B["volume"] = volume
        B["vol_avg20"] = pd.Series(volume).rolling(20, min_periods=5).mean().to_numpy()
        # cumulative session volume vs the 20-prior-session average at the same bar-of-day
        piv = pd.DataFrame({"day_id": df["day_id"].to_numpy(), "bar_of_day": bar_of_day,
                            "cumvol": cum_vol.to_numpy()}).pivot_table(
            index="day_id", columns="bar_of_day", values="cumvol", aggfunc="last")
        piv_avg20 = piv.rolling(20, min_periods=5).mean().shift(1)
        avg_long = piv_avg20.stack(future_stack=True).rename("cumvol_avg20").reset_index()
        m = pd.DataFrame({"day_id": df["day_id"].to_numpy(), "bar_of_day": bar_of_day}).merge(
            avg_long, on=["day_id", "bar_of_day"], how="left")
        B["cumvol"] = cum_vol.to_numpy()
        B["cumvol_avg20"] = m["cumvol_avg20"].to_numpy()
    else:
        B["vwap"] = np.full(n, np.nan)
        B["volume"] = None
    B["has_vol"] = has_vol
    return B


# ─────────────────────────────────────────────────────────────────────────────
# day-level table — prior-day-shifted (a trade entering day D sees day D-1's
# row), except day_gap_pct / session_open which are D's own, known-at-open
# values. Mirrors the shift convention of feature_board.build_structure_daily
# and augur_engine.context.build_internal_daily, applied to this file's own
# column set.
# ─────────────────────────────────────────────────────────────────────────────

def build_day_features(df):
    g = df.groupby("day_id")
    date_of_day = g["_dt"].first().dt.date
    day = pd.DataFrame({"date": date_of_day.to_numpy(),
                        "o": g["open"].first().to_numpy(), "h": g["high"].max().to_numpy(),
                        "l": g["low"].min().to_numpy(), "c": g["close"].last().to_numpy()})
    day = day.sort_values("date").reset_index(drop=True).set_index("date")

    pc, ph, pl = day["c"].shift(1), day["h"].shift(1), day["l"].shift(1)
    tr = pd.concat([day["h"] - day["l"], (day["h"] - pc).abs(), (day["l"] - pc).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()

    rsi14 = pd.Series(calc_rsi(day["c"].to_numpy(), 14), index=day.index)
    adx14 = pd.Series(calc_adx(day["h"].to_numpy(), day["l"].to_numpy(), day["c"].to_numpy(), 14), index=day.index)
    macd_sign = pd.Series(np.sign(calc_macd_hist(day["c"].to_numpy())), index=day.index)
    er20 = pd.Series(calc_efficiency_ratio(day["c"].to_numpy(), 20), index=day.index)
    atr_pctile = pd.Series(rolling_pctile(atr14.to_numpy(), YEAR_DAYS, min_periods=60), index=day.index)

    sma20, sma50, sma200 = (day["c"].rolling(w, min_periods=w).mean() for w in (20, 50, 200))
    day_ret = day["c"].pct_change() * 100.0
    gap_pct = ((day["o"] - pc) / pc.replace(0.0, np.nan)) * 100.0
    range_today = day["h"] - day["l"]
    range_pctile = pd.Series(rolling_pctile(range_today.to_numpy(), YEAR_DAYS, min_periods=60), index=day.index)
    close_pos_own = (day["c"] - day["l"]) / (day["h"] - day["l"]).replace(0.0, np.nan)

    streak = np.full(len(day), np.nan)
    cur = 0.0
    for i, r in enumerate(day_ret.to_numpy()):
        if np.isnan(r):
            continue
        cur = (cur + 1 if cur > 0 else 1.0) if r > 0 else ((cur - 1 if cur < 0 else -1.0) if r < 0 else 0.0)
        streak[i] = cur
    up_streak = pd.Series(streak, index=day.index)
    ret5 = day["c"].pct_change(5) * 100.0
    ret20 = day["c"].pct_change(20) * 100.0

    diso = pd.to_datetime(day.index)
    iso = diso.isocalendar()
    wk = iso["year"].astype(str).to_numpy() + "-" + iso["week"].astype(str).str.zfill(2).to_numpy()
    wtab = pd.DataFrame({"h": day["h"].to_numpy(), "l": day["l"].to_numpy(), "wk": wk}, index=day.index)
    wagg = wtab.groupby("wk", sort=True).agg(wh=("h", "max"), wl=("l", "min"))
    wagg_prior = wagg.shift(1)
    prior_wk = wagg_prior.reindex(wk)
    prior_wk.index = day.index

    out = pd.DataFrame({
        "rsi14_daily": rsi14.shift(1), "adx14_daily": adx14.shift(1),
        "atr_pctile_daily": atr_pctile.shift(1), "macd_sign_daily": macd_sign.shift(1),
        "er20_daily": er20.shift(1), "sma20d": sma20.shift(1), "sma50d": sma50.shift(1),
        "sma200d": sma200.shift(1), "atr14_daily": atr14.shift(1),
        "prior_day_high": ph, "prior_day_low": pl, "prior_day_close": pc,
        "prior_week_hi": prior_wk["wh"], "prior_week_lo": prior_wk["wl"],
        "day_prior_ret_pct": day_ret.shift(1), "day_prior_range_pctile": range_pctile.shift(1),
        "day_prior_close_pos": close_pos_own.shift(1), "day_up_streak": up_streak.shift(1),
        "day_ret_5d": ret5.shift(1), "day_ret_20d": ret20.shift(1),
        "day_gap_pct": gap_pct, "session_open": day["o"],
    }, index=day.index)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE_META — name -> (group, one-sentence description). Order defines
# column order in the CSV / feature matrix.
# ─────────────────────────────────────────────────────────────────────────────

def _feature_meta():
    m = []
    for k in range(1, 13):
        m.append((f"path_r{k}", "path", f"Single-bar return {k} bar(s) before the decision bar, in ATR units."))
    for k, lbl in ((1, "the decision bar"), (2, "one bar earlier"), (3, "two bars earlier")):
        m.append((f"path_body_r{k}", "path", f"Candle body as a share of its own high-low range, {lbl}."))
    m.append(("path_upper_wick", "path", "Upper wick as a share of the decision bar's own high-low range."))
    m.append(("path_lower_wick", "path", "Lower wick as a share of the decision bar's own high-low range."))
    m.append(("path_upcount5", "path", "How many of the last 5 bars closed above their own open."))
    m.append(("path_upcount10", "path", "How many of the last 10 bars closed above their own open."))
    for w in (5, 10, 20):
        m.append((f"path_range{w}_atr", "path", f"High-low range of the last {w} bars, in ATR units."))
    for w in (10, 20, 60):
        m.append((f"path_closepos{w}", "path",
                  f"Where the decision bar's close sits inside the last {w}-bar high-low range (0=low..1=high)."))
    m.append(("path_bars_since_hi20", "path", "Bars since the highest high of the last 20 bars."))
    m.append(("path_bars_since_lo20", "path", "Bars since the lowest low of the last 20 bars."))
    for N in (12, 24, 60):
        m.append((f"path_with{N}_atr", "path",
                  f"How far price had already moved in the trade's direction over the previous {N} bars, "
                  "in ATR units."))

    m.append(("lvl_pdh_atr", "lvl", "Distance from the prior session's high, in ATR units."))
    m.append(("lvl_pdl_atr", "lvl", "Distance from the prior session's low, in ATR units."))
    m.append(("lvl_pdc_atr", "lvl", "Distance from the prior session's close, in ATR units."))
    m.append(("lvl_session_open_atr", "lvl", "Distance from today's own session open, in ATR units."))
    m.append(("lvl_orb_hi_atr", "lvl",
              "Distance from the first-30-minute opening-range high, in ATR units (NaN before it completes)."))
    m.append(("lvl_orb_lo_atr", "lvl",
              "Distance from the first-30-minute opening-range low, in ATR units (NaN before it completes)."))
    m.append(("lvl_vwap_atr", "lvl", "Distance from today's session-cumulative VWAP, in ATR units."))
    for w in (20, 50, 200):
        m.append((f"lvl_ema{w}_atr", "lvl", f"Distance from the {w}-period EMA on the leg's own bar size, in ATR units."))
    for w in (20, 50):
        m.append((f"lvl_ema{w}_60m_atr", "lvl", f"Distance from the {w}-period EMA on completed 60-minute bars, in ATR units."))
    for w in (20, 50, 200):
        m.append((f"lvl_sma{w}d_atr", "lvl", f"Distance from the {w}-day daily SMA, in daily-ATR units (prior-day-shifted)."))
    m.append(("lvl_prior_week_hi_atr", "lvl", "Distance from the prior calendar week's high, in daily-ATR units."))
    m.append(("lvl_prior_week_lo_atr", "lvl", "Distance from the prior calendar week's low, in daily-ATR units."))

    for scale, lbl in (("bar", "the leg's own bar size"), ("60m", "completed 60-minute bars"), ("daily", "daily bars (prior-day-shifted)")):
        m.append((f"ind_rsi14_{scale}", "ind", f"14-period RSI on {lbl}."))
    for scale, lbl in (("bar", "the leg's own bar size"), ("60m", "completed 60-minute bars"), ("daily", "daily bars (prior-day-shifted)")):
        m.append((f"ind_adx14_{scale}", "ind", f"14-period ADX (trend strength) on {lbl}."))
    for scale, lbl in (("bar", "the leg's own bar size"), ("60m", "completed 60-minute bars"), ("daily", "daily bars (prior-day-shifted)")):
        m.append((f"ind_atr_pctile_{scale}", "ind", f"Trailing 1-year percentile rank of 14-period ATR on {lbl}."))
    for scale, lbl in (("bar", "the leg's own bar size"), ("60m", "completed 60-minute bars")):
        m.append((f"ind_bbw_pctile_{scale}", "ind", f"Trailing 1-year percentile rank of Bollinger-band width on {lbl}."))
    for scale, lbl in (("bar", "the leg's own bar size"), ("60m", "completed 60-minute bars"), ("daily", "daily bars (prior-day-shifted)")):
        m.append((f"ind_macd_sign_{scale}", "ind", f"Sign of the MACD histogram (+1/-1/0) on {lbl}."))
    for scale, lbl in (("bar", "the leg's own bar size"), ("daily", "daily bars (prior-day-shifted)")):
        m.append((f"ind_er20_{scale}", "ind", f"20-period efficiency ratio (trend vs chop, 0..1) on {lbl}."))
    m.append(("ind_compressed_60m", "ind", "Whether the 60-minute chart was in a volatility squeeze (coiled) just before entry."))

    m.append(("day_prior_ret_pct", "day", "Prior day's close-to-close return, percent."))
    m.append(("day_prior_range_pctile", "day", "Prior day's high-low range, trailing 1-year percentile rank."))
    m.append(("day_prior_close_pos", "day", "Prior day's close position inside its own high-low range (0..1)."))
    m.append(("day_gap_pct", "day", "Today's open vs yesterday's close, percent."))
    m.append(("day_up_streak", "day", "Consecutive up/down day count through the prior day (signed)."))
    m.append(("day_ret_5d", "day", "Prior day's trailing 5-day return, percent."))
    m.append(("day_ret_20d", "day", "Prior day's trailing 20-day return, percent."))
    m.append(("day_of_week", "day", "Day of week the trade entered (Monday=0..Friday=4)."))
    m.append(("day_minutes_since_open", "day", "Minutes from session open to the decision bar."))
    m.append(("day_hour", "day", "Hour of day (ET) of the decision bar."))

    m.append(("vol_last_vs_avg20", "vol", "Decision bar's volume vs its own trailing-20-bar average."))
    m.append(("vol_cum_vs_avg20", "vol",
              "Session-to-date cumulative volume vs the average cumulative volume at the same minute over the prior 20 sessions."))
    return m


FEATURE_META = _feature_meta()
FEATURE_NAMES = [x[0] for x in FEATURE_META]
FEATURE_GROUP = {x[0]: x[1] for x in FEATURE_META}
FEATURE_DESC = {x[0]: x[2] for x in FEATURE_META}

TR_COLS = ["tr_side", "tr_net_usd", "tr_pnl_r", "tr_win", "tr_mfe_r", "tr_mae_r", "tr_hold_bars",
          "tr_entry_time", "tr_exit_time", "tr_entry_bar", "tr_exit_bar", "tr_set"]


# ─────────────────────────────────────────────────────────────────────────────
# build_feature_matrix — the causal core. Pure function of (df, eb array); no
# knowledge of exit bar / pnl / side is needed or used. Exposed standalone so
# tests can drive it directly on synthetic bars for the causality check.
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_matrix(df, eb, tf_min, B=None, day_feat=None, side=None):
    if B is None:
        B = build_bar_arrays(df, tf_min)
    if day_feat is None:
        day_feat = build_day_features(df)
    n = len(df)
    eb = np.asarray(eb, dtype=int)
    if side is None:
        side = np.ones(len(eb), dtype=int)
    else:
        side = np.asarray(side, dtype=int)
    db = eb - 1
    valid = db >= 60                                    # need 60 bars of path history
    entry_date = pd.DatetimeIndex(df["_dt"]).date[np.clip(eb, 0, n - 1)]
    day_row = day_feat.reindex(entry_date).reset_index(drop=True)

    rows = {name: np.full(len(eb), np.nan) for name in FEATURE_NAMES}
    close, high, low = B["close"], B["high"], B["low"]

    for i in range(len(eb)):
        if not valid[i]:
            continue
        d = db[i]
        atr = B["atr_bar"][d]
        c0 = close[d]
        # path_
        for k in range(1, 13):
            rows[f"path_r{k}"][i] = B["ret"][d - k + 1] / atr if atr else np.nan
        for k in (1, 2, 3):
            rows[f"path_body_r{k}"][i] = B["body_ratio"][d - (k - 1)]
        rows["path_upper_wick"][i] = B["upper_wick"][d]
        rows["path_lower_wick"][i] = B["lower_wick"][d]
        rows["path_upcount5"][i] = B["upcount5"][d]
        rows["path_upcount10"][i] = B["upcount10"][d]
        for w in (5, 10, 20):
            rows[f"path_range{w}_atr"][i] = B[f"range{w}_atr"][d] / atr if atr else np.nan
        for w in (10, 20, 60):
            rows[f"path_closepos{w}"][i] = B[f"closepos{w}"][d]
        rows["path_bars_since_hi20"][i] = B["bars_since_hi20"][d]
        rows["path_bars_since_lo20"][i] = B["bars_since_lo20"][d]
        sgn = 1.0 if side[i] >= 0 else -1.0
        for N in (12, 24, 60):
            if d - N >= 0 and atr:
                rows[f"path_with{N}_atr"][i] = sgn * (c0 - close[d - N]) / atr

        # lvl_
        dr = day_row.iloc[i]
        rows["lvl_pdh_atr"][i] = (c0 - dr["prior_day_high"]) / atr if atr else np.nan
        rows["lvl_pdl_atr"][i] = (c0 - dr["prior_day_low"]) / atr if atr else np.nan
        rows["lvl_pdc_atr"][i] = (c0 - dr["prior_day_close"]) / atr if atr else np.nan
        rows["lvl_session_open_atr"][i] = (c0 - B["session_open"][d]) / atr if atr else np.nan
        rows["lvl_orb_hi_atr"][i] = (c0 - B["or_hi"][d]) / atr if atr else np.nan
        rows["lvl_orb_lo_atr"][i] = (c0 - B["or_lo"][d]) / atr if atr else np.nan
        rows["lvl_vwap_atr"][i] = (c0 - B["vwap"][d]) / atr if atr else np.nan
        for w in (20, 50, 200):
            rows[f"lvl_ema{w}_atr"][i] = (c0 - B[f"ema{w}_bar"][d]) / atr if atr else np.nan
        for w in (20, 50):
            rows[f"lvl_ema{w}_60m_atr"][i] = (c0 - B[f"ema{w}_60m"][d]) / atr if atr else np.nan
        datr = dr["atr14_daily"]
        for w in (20, 50, 200):
            rows[f"lvl_sma{w}d_atr"][i] = (c0 - dr[f"sma{w}d"]) / datr if datr else np.nan
        rows["lvl_prior_week_hi_atr"][i] = (c0 - dr["prior_week_hi"]) / datr if datr else np.nan
        rows["lvl_prior_week_lo_atr"][i] = (c0 - dr["prior_week_lo"]) / datr if datr else np.nan

        # ind_
        rows["ind_rsi14_bar"][i] = B["rsi_bar"][d]
        rows["ind_rsi14_60m"][i] = B["rsi_60m"][d]
        rows["ind_rsi14_daily"][i] = dr["rsi14_daily"]
        rows["ind_adx14_bar"][i] = B["adx_bar"][d]
        rows["ind_adx14_60m"][i] = B["adx_60m"][d]
        rows["ind_adx14_daily"][i] = dr["adx14_daily"]
        rows["ind_atr_pctile_bar"][i] = B["atr_pctile_bar"][d]
        rows["ind_atr_pctile_60m"][i] = B["atr_pctile_60m"][d]
        rows["ind_atr_pctile_daily"][i] = dr["atr_pctile_daily"]
        rows["ind_bbw_pctile_bar"][i] = B["bbw_pctile_bar"][d]
        rows["ind_bbw_pctile_60m"][i] = B["bbw_pctile_60m"][d]
        rows["ind_macd_sign_bar"][i] = np.sign(B["macd_bar"][d])
        rows["ind_macd_sign_60m"][i] = np.sign(B["macd_60m"][d]) if not np.isnan(B["macd_60m"][d]) else np.nan
        rows["ind_macd_sign_daily"][i] = dr["macd_sign_daily"]
        rows["ind_er20_bar"][i] = B["er20_bar"][d]
        rows["ind_er20_daily"][i] = dr["er20_daily"]
        rows["ind_compressed_60m"][i] = B["compressed_60m"][d]

        # day_
        rows["day_prior_ret_pct"][i] = dr["day_prior_ret_pct"]
        rows["day_prior_range_pctile"][i] = dr["day_prior_range_pctile"]
        rows["day_prior_close_pos"][i] = dr["day_prior_close_pos"]
        rows["day_gap_pct"][i] = dr["day_gap_pct"]
        rows["day_up_streak"][i] = dr["day_up_streak"]
        rows["day_ret_5d"][i] = dr["day_ret_5d"]
        rows["day_ret_20d"][i] = dr["day_ret_20d"]
        rows["day_of_week"][i] = pd.Timestamp(entry_date[i]).weekday()
        rows["day_minutes_since_open"][i] = B["mins_since_open"][d]
        rows["day_hour"][i] = df["_dt"].iloc[d].hour

        # vol_
        if B["has_vol"]:
            va = B["vol_avg20"][d]
            rows["vol_last_vs_avg20"][i] = B["volume"][d] / va if va else np.nan
            cva = B["cumvol_avg20"][d]
            rows["vol_cum_vs_avg20"][i] = B["cumvol"][d] / cva if cva else np.nan

    X = pd.DataFrame(rows)
    return X, entry_date, valid


# ─────────────────────────────────────────────────────────────────────────────
# discovery / holdout / lockbox split
# ─────────────────────────────────────────────────────────────────────────────

def split_sets(entry_date, date_from, lockbox_from, frac=DISCOVERY_FRAC):
    """entry_date: array-like of datetime.date. date_from/lockbox_from: date-like
    (str or datetime.date) marking the leg's pre-lockbox calendar span. Returns
    (labels array of 'discovery'/'holdout'/'lockbox', boundary_date)."""
    d0 = pd.Timestamp(date_from).date()
    d1 = pd.Timestamp(lockbox_from).date() if not isinstance(lockbox_from, datetime.date) else lockbox_from
    span_days = (d1 - d0).days
    boundary = d0 + datetime.timedelta(days=int(round(span_days * frac)))
    ed = np.asarray(entry_date)
    labels = np.where(ed >= d1, "lockbox", np.where(ed < boundary, "discovery", "holdout"))
    return labels, boundary


# ─────────────────────────────────────────────────────────────────────────────
# build the full per-trade table for one leg
# ─────────────────────────────────────────────────────────────────────────────

def build_trade_table(leg_key, verbose=True):
    leg = [l for l in FB.LEGS if l["key"] == leg_key][0]
    cfg = FB.resolve_leg_config(leg)
    tf_min = int(str(cfg["timeframe"]).rstrip("m"))
    if verbose:
        print(f"[{leg_key}] {cfg['instrument']} {cfg['timeframe']} {cfg['session']} "
              f"{cfg['date_from']}..{cfg['date_to']}")
    df = FB.load(cfg["instrument"], cfg["timeframe"], cfg["session"], cfg["date_from"], cfg["date_to"])
    t0 = time.time()
    trades = run_strategy_full(leg["file"], df, cfg["best_params"])
    if verbose:
        print(f"[{leg_key}] {len(trades)} trades replayed in {time.time()-t0:.1f}s")
    lockbox_from = FB._lockbox_from_date(cfg)

    eb = np.array([t[0] for t in trades], dtype=int)
    xb = np.array([t[1] for t in trades], dtype=int)
    pnl_pts = np.array([t[2] for t in trades], dtype=float)
    side = np.array([t[3] for t in trades], dtype=int)
    entry_px = np.array([t[4] for t in trades], dtype=float)
    usd = (pnl_pts - cfg["cost_pts"]) * cfg["mult"]

    entry_date_all = pd.DatetimeIndex(df["_dt"]).date[eb]
    labels, boundary = split_sets(entry_date_all, cfg["date_from"], lockbox_from)

    # lockbox trades are EXCLUDED ENTIRELY — dropped before any feature is built.
    keep = labels != "lockbox"
    n_lockbox = int((~keep).sum())
    eb, xb, pnl_pts, side, entry_px, usd = eb[keep], xb[keep], pnl_pts[keep], side[keep], entry_px[keep], usd[keep]
    labels_kept = labels[keep]

    B = build_bar_arrays(df, tf_min)
    day_feat = build_day_features(df)
    X, entry_date, valid = build_feature_matrix(df, eb, tf_min, B=B, day_feat=day_feat, side=side)
    X = X.loc[valid].reset_index(drop=True)
    eb, xb, pnl_pts, side, entry_px, usd = eb[valid], xb[valid], pnl_pts[valid], side[valid], entry_px[valid], usd[valid]
    labels_kept = labels_kept[valid]
    entry_date = np.asarray(entry_date)[valid]

    # R unit: discovery-only mean absolute LOSING trade in $ (never let holdout leak in)
    disc_mask = labels_kept == "discovery"
    disc_losers = usd[disc_mask][usd[disc_mask] < 0]
    r_unit = float(np.mean(np.abs(disc_losers))) if len(disc_losers) else 1.0
    if not np.isfinite(r_unit) or r_unit <= 0:
        r_unit = 1.0

    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    mfe_pts = np.full(len(eb), np.nan)
    mae_pts = np.full(len(eb), np.nan)
    for i in range(len(eb)):
        a, b = eb[i], xb[i]
        if b < a:
            a, b = b, a
        seg_hi, seg_lo = high[a:b + 1], low[a:b + 1]
        if len(seg_hi) == 0:
            continue
        if side[i] > 0:
            mfe_pts[i] = seg_hi.max() - entry_px[i]
            mae_pts[i] = entry_px[i] - seg_lo.min()
        else:
            mfe_pts[i] = entry_px[i] - seg_lo.min()
            mae_pts[i] = seg_hi.max() - entry_px[i]

    hold_bars = xb - eb
    entry_time = df["_dt"].to_numpy()[eb]
    exit_time = df["_dt"].to_numpy()[np.clip(xb, 0, len(df) - 1)]

    tr = pd.DataFrame({
        "tr_side": np.where(side > 0, "long", "short"),
        "tr_net_usd": usd,
        "tr_pnl_r": usd / r_unit,
        "tr_win": (usd > 0).astype(int),
        "tr_mfe_r": (mfe_pts * cfg["mult"]) / r_unit,
        "tr_mae_r": (mae_pts * cfg["mult"]) / r_unit,
        "tr_hold_bars": hold_bars,
        "tr_entry_time": entry_time,
        "tr_exit_time": exit_time,
        "tr_entry_bar": eb,
        "tr_exit_bar": xb,
        "tr_set": labels_kept,
    })
    full = pd.concat([tr.reset_index(drop=True), X.reset_index(drop=True)], axis=1)
    full.insert(0, "leg", leg_key)
    full["tr_entry_date"] = entry_date

    meta = dict(leg=leg_key, cfg=cfg, boundary=boundary, lockbox_from=str(lockbox_from),
               n_total_replayed=int(len(trades)), n_lockbox_excluded=n_lockbox,
               n_pre_lockbox=int(keep.sum()), n_dropped_no_history=int((~valid).sum()),
               r_unit=r_unit, n_discovery=int((labels_kept == "discovery").sum()),
               n_holdout=int((labels_kept == "holdout").sum()))
    return full, meta, df, B, day_feat




# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS 1 — winner anatomy: for each feature, its own mean among the
# trades that became top-decile winners vs bottom-decile losers (by pnl_R),
# plus the standard feature_board-style LIFT (mean pnl_R in the feature's own
# top third minus bottom third), permutation-tested. Discovery set only.
# Reuses feature_board's LIFT primitives verbatim (module docstring REUSE).
# ─────────────────────────────────────────────────────────────────────────────

def winner_anatomy(Xd, pnl_r, entry_date, min_group=10):
    pnl_r = np.asarray(pnl_r, float)
    top_thr = np.nanpercentile(pnl_r, 90)
    bot_thr = np.nanpercentile(pnl_r, 10)
    top_mask = pnl_r >= top_thr
    bot_mask = pnl_r <= bot_thr

    uniq_dates, day_code = np.unique(np.asarray(entry_date), return_inverse=True)
    n_days = len(uniq_dates)

    rows = []
    for nm in Xd.columns:
        x = Xd[nm].to_numpy(float)
        if np.count_nonzero(~np.isnan(x)) < min_group:
            continue
        mean_top = float(np.nanmean(x[top_mask])) if top_mask.any() else np.nan
        mean_bot = float(np.nanmean(x[bot_mask])) if bot_mask.any() else np.nan
        mean_all = float(np.nanmean(x))
        std_all = float(np.nanstd(x))
        std_diff = (mean_top - mean_bot) / std_all if std_all > 0 else np.nan

        spec = FB._lift_threshold_spec(x)
        lift, lift_p = None, None
        if spec[0] != "degenerate":
            hi_mask, lo_mask = FB._lift_masks(x, spec)
            if hi_mask.sum() >= min_group and lo_mask.sum() >= min_group:
                lift = FB._lift_r(pnl_r, hi_mask, lo_mask)
                lift_p = FB._lift_perm_pvalue(x, pnl_r, spec, lift, day_code, n_days,
                                              group_kind="bar", n_perm=LIFT_N_PERM, seed=SEED,
                                              block_perm_days=LIFT_BLOCK_DAYS)
        rows.append(dict(feature=nm, group=FEATURE_GROUP.get(nm, "?"), mean_top_decile=mean_top,
                         mean_bottom_decile=mean_bot, mean_all=mean_all, std_diff=std_diff,
                         lift=lift, lift_p=lift_p))

    pvals = [r["lift_p"] for r in rows if r["lift_p"] is not None]
    names = [r["feature"] for r in rows if r["lift_p"] is not None]
    qmap = dict(zip(names, ctx._bh_fdr(pvals))) if pvals else {}
    for r in rows:
        r["lift_q"] = qmap.get(r["feature"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS 2a — shallow decision tree over pnl_R, leaves read out as rules
# ─────────────────────────────────────────────────────────────────────────────

def fit_rule_tree(Xd, pnl_r, usd, max_depth=3, min_leaf_frac=0.05, seed=SEED):
    from sklearn.tree import DecisionTreeRegressor
    n = len(pnl_r)
    min_leaf = max(5, int(round(min_leaf_frac * n)))
    Xv = Xd.to_numpy(float)
    model = DecisionTreeRegressor(max_depth=max_depth, min_samples_leaf=min_leaf, random_state=seed)
    model.fit(Xv, np.asarray(pnl_r, float))
    leaf_id = model.apply(Xv)
    tree_ = model.tree_
    feat_names = list(Xd.columns)

    rules_per_leaf = {}

    def recurse(node, conds):
        if tree_.feature[node] != -2:
            nm = feat_names[tree_.feature[node]]
            thr = tree_.threshold[node]
            recurse(tree_.children_left[node], conds + [f"{nm} <= {thr:.3f}"])
            recurse(tree_.children_right[node], conds + [f"{nm} > {thr:.3f}"])
        else:
            rules_per_leaf[node] = list(conds)

    recurse(0, [])
    out = []
    for leaf, conds in rules_per_leaf.items():
        m = leaf_id == leaf
        cnt = int(m.sum())
        if cnt == 0:
            continue
        r = np.asarray(pnl_r, float)[m]
        u = np.asarray(usd, float)[m]
        wins, losses = r[r > 0].sum(), -r[r <= 0].sum()
        pf = float(wins / losses) if losses > 0 else float("inf")
        out.append(dict(rule=" AND ".join(conds) if conds else "(root -- tree found no useful split)",
                        n=cnt, mean_r=float(np.mean(r)), pf=pf, share=cnt / n, net_usd=float(u.sum())))
    out.sort(key=lambda d: -d["n"])
    return out, model


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS 2b — single-condition skip rules, mined on DISCOVERY, evaluated
# once (pre-registered) on HOLDOUT
# ─────────────────────────────────────────────────────────────────────────────

SKIP_PCTILES = (10, 20, 30, 70, 80, 90)


def mine_skip_rules(Xd, usd, entry_date, min_keep_frac=0.6, min_valid=30):
    n = len(usd)
    usd = np.asarray(usd, float)
    order = np.argsort(np.asarray(entry_date))
    candidates = []
    for nm in Xd.columns:
        x = Xd[nm].to_numpy(float)
        valid = ~np.isnan(x)
        if valid.sum() < min_valid:
            continue
        xv = x[valid]
        for p in SKIP_PCTILES:
            t = float(np.percentile(xv, p))
            for direction, keep_valid in (("skip_below", xv >= t), ("skip_above", xv < t)):
                keep = np.ones(n, dtype=bool)
                keep[valid] = keep_valid
                n_kept = int(keep.sum())
                if n_kept < min_keep_frac * n or n_kept == 0:
                    continue
                u_kept = usd[keep]
                net_per_trade = float(u_kept.sum() / n_kept)
                keep_chrono = order[keep[order]]
                eq = np.cumsum(usd[keep_chrono])
                peak = np.maximum.accumulate(eq) if len(eq) else eq
                maxdd = float((peak - eq).max()) if len(eq) else 0.0
                mar = float(u_kept.sum() / maxdd) if maxdd > 0 else np.nan
                candidates.append(dict(feature=nm, direction=direction, pctile=p, threshold=t,
                                       n_kept=n_kept, n_total=n, net_per_trade=net_per_trade,
                                       mar_proxy=mar, net_total=float(u_kept.sum())))
    return candidates


def rule_mask(Xset, rule):
    """Boolean KEEP mask for a skip/tercile rule (NaN feature values are always kept --
    the rule can't be evaluated for them, so it doesn't apply)."""
    x = Xset[rule["feature"]].to_numpy(float)
    valid = ~np.isnan(x)
    if rule["direction"] == "skip_below":
        keep_valid = x[valid] >= rule["threshold"]
    else:
        keep_valid = x[valid] < rule["threshold"]
    keep = np.ones(len(x), dtype=bool)
    keep[valid] = keep_valid
    return keep


def eval_rule(Xset, usd_set, rule):
    usd_set = np.asarray(usd_set, float)
    keep = rule_mask(Xset, rule)
    n_kept = int(keep.sum())
    npt = float(usd_set[keep].sum() / n_kept) if n_kept else float("nan")
    return n_kept, npt


def rule_english(rule):
    verb = "Skip trades where" if rule["direction"] == "skip_below" else "Skip trades where"
    cmp_ = "<" if rule["direction"] == "skip_below" else ">"
    tag = f" [{rule['kind']}]" if rule.get("kind") == "tercile" else ""
    return f"{verb} {rule['feature']} {cmp_} {rule['threshold']:.3f} (p{rule['pctile']}){tag}"


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS 2c — rule ledger by TOTAL MONEY, not per-trade averages. A skip rule
# that raises net-per-trade on discovery can still lose total dollars (fewer
# trades kept, even if each one looks better on average) -- and that trap can
# flip sign again between discovery and holdout. This section re-scores the
# same rules on totals: net $, PF, drawdown $, MAR, and a 2x-size-TILT variant
# that keeps every trade instead of dropping the skipped ones.
# ─────────────────────────────────────────────────────────────────────────────

TERCILE_FEATURE = "path_with24_atr"
TERCILE_PCTILE = 100.0 / 3.0 * 2.0     # keep the top third


def build_tercile_rule(Xd, feature=TERCILE_FEATURE, pctile=TERCILE_PCTILE, min_valid=30):
    """Tercile rule fixed on DISCOVERY: keep (upweight) the top third of `feature`.
    Same dict shape as a mined skip rule (direction='skip_below' keeps x >= threshold)."""
    x = Xd[feature].to_numpy(float)
    valid = ~np.isnan(x)
    if valid.sum() < min_valid:
        return None
    t = float(np.percentile(x[valid], pctile))
    return dict(feature=feature, direction="skip_below", pctile=round(pctile, 1), threshold=t,
               kind="tercile")


def _pf(usd):
    usd = np.asarray(usd, float)
    wins = usd[usd > 0].sum()
    losses = -usd[usd <= 0].sum()
    return float(wins / losses) if losses > 0 else float("inf")


def _equity_dd(usd_chrono):
    usd_chrono = np.asarray(usd_chrono, float)
    if len(usd_chrono) == 0:
        return 0.0
    eq = np.cumsum(usd_chrono)
    peak = np.maximum.accumulate(eq)
    return float((peak - eq).max())


def _mar_annualized(net_total, years, dd):
    if not years or years <= 0 or not dd or dd <= 0:
        return float("nan")
    return float((net_total / years) / dd)


def _safe_gt(a, b):
    return (a == a) and (b == b) and (a > b)     # NaN-safe a > b


def money_ledger_row(rule, Xset, usd, entry_date, years_span, tilt_mult=2.0):
    """Total-money stats for one rule on one window (discovery or holdout)."""
    usd = np.asarray(usd, float)
    entry_date = np.asarray(entry_date)
    n = len(usd)
    keep = rule_mask(Xset, rule)
    n_kept = int(keep.sum())
    kept_pct = 100.0 * n_kept / n if n else float("nan")

    net_rule = float(usd[keep].sum())
    net_base = float(usd.sum())
    pct_change = 100.0 * (net_rule - net_base) / abs(net_base) if net_base else float("nan")

    pf_rule = _pf(usd[keep])
    dd_rule = _equity_dd(usd[keep])           # kept trades stay in their original chronological order
    mar_rule = _mar_annualized(net_rule, years_span, dd_rule)

    base_dd = _equity_dd(usd)
    base_pf = _pf(usd)
    base_mar = _mar_annualized(net_base, years_span, base_dd)

    # years in which the SKIPPED trades lost money (i.e. the skip helped), as k/n over
    # years that actually had a skipped trade
    skipped_usd = usd[~keep]
    if n and len(skipped_usd):
        skipped_years = np.array([d.year for d in entry_date[~keep]])
        uniq_yrs = np.unique(skipped_years)
        helped = sum(1 for y in uniq_yrs if skipped_usd[skipped_years == y].sum() < 0)
        yrs_helped = f"{helped}/{len(uniq_yrs)}"
    else:
        yrs_helped = "0/0"

    # same rule as a 2x SIZE TILT: every trade stays in, kept trades sized 2x
    tilt_usd = np.where(keep, usd * tilt_mult, usd)
    tilt_net = float(tilt_usd.sum())
    tilt_dd = _equity_dd(tilt_usd)
    tilt_mar = _mar_annualized(tilt_net, years_span, tilt_dd)

    return dict(n=n, n_kept=n_kept, kept_pct=kept_pct, net_rule=net_rule, net_base=net_base,
               pct_change=pct_change, pf=pf_rule, dd=dd_rule, mar=mar_rule,
               base_pf=base_pf, base_dd=base_dd, base_mar=base_mar, yrs_helped=yrs_helped,
               tilt_net=tilt_net, tilt_dd=tilt_dd, tilt_mar=tilt_mar)


def _rule_improves(row):
    """Total money AND risk-adjusted return both beat doing nothing."""
    return row["pct_change"] > 0 and _safe_gt(row["mar"], row["base_mar"])


TILT_MAR_MARGIN = 1.10   # tilt MAR must beat base MAR by 10% - sizing up 70% of trades is near-uniform leverage and nudges MAR by chance
TILT_MAX_KEPT = 0.50     # a conviction tilt sizes up a MINORITY of trades; above half it is just more leverage


def _tilt_improves(row):
    """The 2x size-tilt form (nothing dropped) beats doing nothing on risk-adjusted return,
    by a margin, on a minority of trades."""
    kept = row.get("kept_frac")
    if kept is None:
        kept = (row.get("kept_pct") or 0) / 100.0
    return (kept <= TILT_MAX_KEPT and row.get("tilt_net", 0) > row.get("net_base", 0)
            and _safe_gt(row.get("tilt_mar"), (row["base_mar"] or 0) * TILT_MAR_MARGIN))


def classify_verdict(disc_row, hold_row):
    d_ok = _rule_improves(disc_row)
    h_ok = _rule_improves(hold_row)
    if d_ok and h_ok:
        return "carries"
    # the filter form fails, but sizing UP the kept trades (dropping nothing) lifts MAR in
    # BOTH windows - the honest reading of a condition that ranks trades without being a
    # reason to skip any of them
    if _tilt_improves(disc_row) and _tilt_improves(hold_row):
        return "carries as tilt"
    if d_ok and not h_ok:
        return "regime artifact"
    return "no"


def build_money_ledger(rules, Xd, usd_d, ed_d, years_d, Xh, usd_h, ed_h, years_h):
    ledger = []
    for rule in rules:
        if rule is None:
            continue
        rd = money_ledger_row(rule, Xd, usd_d, ed_d, years_d)
        rh = money_ledger_row(rule, Xh, usd_h, ed_h, years_h)
        verdict = classify_verdict(rd, rh)
        ledger.append(dict(rule=rule, disc=rd, hold=rh, verdict=verdict))
    return ledger


# ─────────────────────────────────────────────────────────────────────────────
# CHARTS — small, dark-neutral candlestick snapshots + one path-overlay chart
# ─────────────────────────────────────────────────────────────────────────────

_DARK_BG = "#1b1e23"
_DARK_FG = "#c9ccd1"
_DARK_GRID = "#3a3f47"
_GREEN = "#4caf50"
_RED = "#e0605c"


def compute_norm_paths(B, eb, length=60):
    db = np.asarray(eb, int) - 1
    close, atr = B["close"], B["atr_bar"]
    out = np.full((len(db), length), np.nan)
    for i, d in enumerate(db):
        a = atr[d] if 0 <= d < len(atr) else np.nan
        if not a or np.isnan(a) or d - length + 1 < 0:
            continue
        seg = close[d - length + 1:d + 1]
        out[i, :] = (seg - close[d]) / a
    return out


def plot_trade_chart(df, B, day_feat, row, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    eb, xb = int(row["tr_entry_bar"]), int(row["tr_exit_bar"])
    lo_i, hi_i = max(0, eb - 60), min(len(df) - 1, eb + 20)
    seg = df.iloc[lo_i:hi_i + 1]
    o, h, l, c = (seg[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = len(seg)

    fig, ax = plt.subplots(figsize=(640 / 90, 360 / 90), dpi=90)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    up = c >= o
    for i in range(n):
        col = _GREEN if up[i] else _RED
        ax.plot([i, i], [l[i], h[i]], color=col, linewidth=0.6, zorder=2)
        y0, hgt = min(o[i], c[i]), max(abs(c[i] - o[i]), (h.max() - l.min()) * 0.001)
        ax.add_patch(Rectangle((i - 0.32, y0), 0.64, hgt, facecolor=col, edgecolor=col, linewidth=0.2, zorder=2))

    ema20 = B["ema20_bar"][lo_i:hi_i + 1]
    ax.plot(np.arange(n), ema20, color="#5aa7ff", linewidth=0.9, label="EMA20", zorder=3)
    if B["has_vol"]:
        vwap = B["vwap"][lo_i:hi_i + 1]
        ax.plot(np.arange(n), vwap, color="#e8b84b", linewidth=0.8, linestyle="--", label="VWAP", zorder=3)

    edate = pd.Timestamp(df["_dt"].iloc[eb]).date()
    if edate in day_feat.index:
        dr = day_feat.loc[edate]
        for lvl, col in ((dr.get("prior_day_high"), "#9098a3"), (dr.get("prior_day_low"), "#9098a3"),
                        (dr.get("prior_day_close"), "#6f7783")):
            if pd.notna(lvl):
                ax.axhline(lvl, color=col, linewidth=0.5, linestyle=":", zorder=1)

    ei, xi = eb - lo_i, min(max(xb - lo_i, 0), n - 1)
    if 0 <= ei < n:
        ax.scatter([ei], [c[ei]], marker="^", color="#ffffff", s=22, zorder=5, edgecolors="none")
    ax.scatter([xi], [c[xi]], marker="v", color="#ffd54f", s=22, zorder=5, edgecolors="none")

    ax.set_xticks([])
    ax.tick_params(colors=_DARK_FG, labelsize=6)
    for spine in ax.spines.values():
        spine.set_color(_DARK_GRID)
    ax.grid(color=_DARK_GRID, linewidth=0.3, alpha=0.4)
    ax.legend(fontsize=5, facecolor=_DARK_BG, labelcolor=_DARK_FG, edgecolor=_DARK_GRID, loc="upper left")
    title = (f"{row['tr_entry_date']}  {row['tr_side']}  R={row['tr_pnl_r']:+.2f}  "
            f"hold={int(row['tr_hold_bars'])}b")
    ax.set_title(title, color=_DARK_FG, fontsize=7)
    fig.tight_layout(pad=0.4)
    fig.savefig(out_path, dpi=90, facecolor=fig.get_facecolor())
    plt.close(fig)


def plot_path_overlay(paths_dict, out_path, leg_key):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    offsets = np.arange(-(next(iter(paths_dict.values())).shape[1]) + 1, 1)
    colors = {"top_decile_winners": _GREEN, "bottom_decile_losers": _RED, "all_discovery": "#9aa0a6"}
    fig, ax = plt.subplots(figsize=(760 / 100, 420 / 100), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    for label, arr in paths_dict.items():
        med = np.nanmedian(arr, axis=0)
        q25 = np.nanpercentile(arr, 25, axis=0)
        q75 = np.nanpercentile(arr, 75, axis=0)
        col = colors.get(label, "#ffffff")
        ax.plot(offsets, med, color=col, linewidth=1.3, label=label.replace("_", " "))
        ax.fill_between(offsets, q25, q75, color=col, alpha=0.12)
    ax.axhline(0, color=_DARK_GRID, linewidth=0.6)
    ax.axvline(0, color=_DARK_GRID, linewidth=0.6, linestyle=":")
    ax.set_xlabel("bars before decision (0 = decision bar)", color=_DARK_FG, fontsize=8)
    ax.set_ylabel("close - decision close, in ATR", color=_DARK_FG, fontsize=8)
    ax.tick_params(colors=_DARK_FG, labelsize=7)
    for spine in ax.spines.values():
        spine.set_color(_DARK_GRID)
    ax.grid(color=_DARK_GRID, linewidth=0.3, alpha=0.4)
    ax.legend(fontsize=7, facecolor=_DARK_BG, labelcolor=_DARK_FG, edgecolor=_DARK_GRID)
    ax.set_title(f"{leg_key} — median price path into the trade (discovery set)", color=_DARK_FG, fontsize=9)
    fig.tight_layout(pad=0.6)
    fig.savefig(out_path, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# outputs
# ─────────────────────────────────────────────────────────────────────────────

def write_features_json(out_dir, leg_key):
    doc = {nm: dict(group=FEATURE_GROUP[nm], desc=FEATURE_DESC[nm]) for nm in FEATURE_NAMES}
    fp = os.path.join(out_dir, f"{leg_key}_features.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    return fp


def _fmt(v, nd=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if isinstance(v, float) and np.isinf(v):
        return "inf"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def write_md(leg_key, meta, winner_rows, tree_leaves, skip_top_net, skip_top_mar,
            holdout_rows, money_ledger, out_dir):
    apos = chr(39)
    L = []
    L.append(f"# {leg_key} -- trade anatomy")
    L.append("")
    cfg = meta["cfg"]
    L.append("Discovery window (hard rule): first 60% of the pre-lockbox calendar span, by date.")
    L.append(f"- Pre-lockbox span: {cfg['date_from']} .. {meta['lockbox_from']} (lockbox excluded entirely).")
    L.append(f"- Discovery: {cfg['date_from']} .. {meta['boundary']}  (n={meta['n_discovery']})")
    L.append(f"- Holdout: {meta['boundary']} .. {meta['lockbox_from']}  (n={meta['n_holdout']})")
    L.append(f"- Lockbox excluded: n={meta['n_lockbox_excluded']} (the split is by calendar date, not "
             "trade count, so discovery/holdout are not exactly 60/40 of trades).")
    L.append(f"- R unit (1R): ${meta['r_unit']:,.0f} -- discovery-only mean absolute losing trade.")
    L.append("")

    L.append("## 2c. Rules judged by total money, not averages")
    L.append("")
    L.append("Every rule below was mined on discovery net PER TRADE (an average) -- the same ranking "
             "used in sections 1 and 2. This table re-scores the top-10 of those rules, plus a fixed "
             "tercile rule on the new " + apos + "already moving with the trade" + apos + " feature "
             "(keep/upweight the top third of path_with24_atr, threshold fixed on discovery), by TOTAL "
             "money: net $ kept vs base, PF, drawdown $, MAR, how many calendar years the skipped trades "
             "would have LOST money (skip helped), and the same rule run as a 2x SIZE TILT on the kept "
             "trades instead of a filter (nothing dropped, kept trades just sized bigger). Discovery (D) "
             "and holdout (H) are shown side by side as D / H in each cell.")
    L.append("")
    L.append("| rule | kept % (D/H) | net $ rule (D/H) | net $ base (D/H) | % change (D/H) | "
             "PF (D/H) | max DD $ (D/H) | MAR (D/H) | base MAR (D/H) | skip-helped yrs (D/H) | "
             "tilt net/DD/MAR (D) | tilt net/DD/MAR (H) | verdict |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in money_ledger:
        rule, rd, rh = row["rule"], row["disc"], row["hold"]
        L.append(
            f"| {rule_english(rule)} "
            f"| {rd['kept_pct']:.0f}% / {rh['kept_pct']:.0f}% "
            f"| ${rd['net_rule']:,.0f} / ${rh['net_rule']:,.0f} "
            f"| ${rd['net_base']:,.0f} / ${rh['net_base']:,.0f} "
            f"| {_fmt(rd['pct_change'], 1)}% / {_fmt(rh['pct_change'], 1)}% "
            f"| {_fmt(rd['pf'])} / {_fmt(rh['pf'])} "
            f"| ${rd['dd']:,.0f} / ${rh['dd']:,.0f} "
            f"| {_fmt(rd['mar'])} / {_fmt(rh['mar'])} "
            f"| {_fmt(rd['base_mar'])} / {_fmt(rh['base_mar'])} "
            f"| {rd['yrs_helped']} / {rh['yrs_helped']} "
            f"| ${rd['tilt_net']:,.0f} / ${rd['tilt_dd']:,.0f} / {_fmt(rd['tilt_mar'])} "
            f"| ${rh['tilt_net']:,.0f} / ${rh['tilt_dd']:,.0f} / {_fmt(rh['tilt_mar'])} "
            f"| {row['verdict']} |")
    L.append("")
    n_carries = sum(1 for r in money_ledger if r["verdict"] == "carries")
    n_regime = sum(1 for r in money_ledger if r["verdict"] == "regime artifact")
    n_no = sum(1 for r in money_ledger if r["verdict"] == "no")
    n_tilt = sum(1 for r in money_ledger if r["verdict"] == "carries as tilt")
    L.append(f"Of {len(money_ledger)} rules re-scored by total money: {n_carries} carry as a FILTER (total $ AND MAR "
             f"improve on both discovery and holdout), {n_tilt} carry only as a 2x SIZE TILT (nothing dropped; the tilt "
             f"covers at most half the trades and lifts MAR by at least {int((TILT_MAR_MARGIN-1)*100)}% in BOTH windows), "
             f"{n_regime} are regime artifacts (they help discovery and hurt holdout -- a rule that only worked because of "
             f"when it was found), and {n_no} never clear the bar even in discovery. A rule ranking well by net-$-per-trade in "
             "sections 1/2 below is NOT the same claim as ranking well here: per-trade averages rise whenever a filter removes "
             "a block of merely-okay trades, even though the total dollars those trades would have added are gone -- that is "
             "exactly the trap this section exists to catch. The 2x tilt columns show the alternative that keeps every trade "
             "instead of dropping any: when a rule carries as a tilt, sizing up on conviction beats skipping outright.")
    L.append("")

    L.append("## 1. Winner anatomy (PER-TRADE AVERAGES, discovery only -- can mislead; see section 2c "
             "for the total-money read)")
    L.append("")
    L.append("What the market looked like, feature by feature, ahead of trades that became top-decile "
             "winners (top 10% by pnl_R) vs bottom-decile losers (bottom 10%), plus LIFT: mean pnl_R in "
             "the feature" + apos + "s OWN top third of trades minus its bottom third, permutation-tested "
             "(1000 draws, values shuffled within ~21-trading-day blocks) and BH-FDR corrected across "
             "features.")
    L.append("")
    L.append("Top 20 by absolute lift:")
    L.append("")
    L.append("| feature | group | top-decile mean | bottom-decile mean | lift (R) | q |")
    L.append("|---|---|---|---|---|---|")
    ranked = [r for r in winner_rows if r["lift"] is not None]
    ranked.sort(key=lambda r: -abs(r["lift"]))
    for r in ranked[:20]:
        L.append(f"| {r['feature']} | {r['group']} | {_fmt(r['mean_top_decile'])} | "
                 f"{_fmt(r['mean_bottom_decile'])} | {_fmt(r['lift'])} | {_fmt(r['lift_q'], 4)} |")
    L.append("")
    L.append("Top 5 by top-vs-bottom-decile standardized difference:")
    L.append("")
    L.append("| feature | group | top-decile mean | bottom-decile mean | all mean | std diff |")
    L.append("|---|---|---|---|---|---|")
    by_std = sorted(winner_rows, key=lambda r: -abs(r["std_diff"]) if r["std_diff"] == r["std_diff"] else 0)
    for r in by_std[:5]:
        L.append(f"| {r['feature']} | {r['group']} | {_fmt(r['mean_top_decile'])} | "
                 f"{_fmt(r['mean_bottom_decile'])} | {_fmt(r['mean_all'])} | {_fmt(r['std_diff'])} |")
    L.append("")

    L.append("## 2. Rule mining (PER-TRADE AVERAGES, discovery only, one pre-registered holdout peek "
             "-- can mislead; see section 2c for the total-money read)")
    L.append("")
    L.append("(a) Shallow decision tree (depth 3, min 5% of discovery trades per leaf, target = pnl_R):")
    L.append("")
    L.append("| rule | n | mean R | PF | share | net $ |")
    L.append("|---|---|---|---|---|---|")
    for lf in tree_leaves:
        L.append(f"| {lf['rule']} | {lf['n']} | {_fmt(lf['mean_r'])} | {_fmt(lf['pf'])} | "
                 f"{lf['share']*100:.1f}% | ${lf['net_usd']:,.0f} |")
    L.append("")
    L.append("(b) Single-condition skip rules (feature thresholds at the 10/20/30/70/80/90th "
             "percentiles, both directions, must keep at least 60% of discovery trades):")
    L.append("")
    L.append("Top 10 by remaining net $ per trade:")
    L.append("")
    L.append("| rule | trades kept | net $/trade | MAR proxy |")
    L.append("|---|---|---|---|")
    for r in skip_top_net:
        L.append(f"| {rule_english(r)} | {r['n_kept']}/{r['n_total']} | ${r['net_per_trade']:,.1f} | "
                 f"{_fmt(r['mar_proxy'])} |")
    L.append("")
    L.append("Top 10 by remaining MAR proxy (net $ / max drawdown $ of the kept sequence):")
    L.append("")
    L.append("| rule | trades kept | net $/trade | MAR proxy |")
    L.append("|---|---|---|---|")
    for r in skip_top_mar:
        L.append(f"| {rule_english(r)} | {r['n_kept']}/{r['n_total']} | ${r['net_per_trade']:,.1f} | "
                 f"{_fmt(r['mar_proxy'])} |")
    L.append("")
    L.append("Pre-registered holdout check -- the SAME top-10-by-net-per-trade rules (same feature, "
             "same threshold, learned on discovery only) applied ONCE to the never-touched holdout set:")
    L.append("")
    L.append("| rule | disc net/trade (rule) | disc net/trade (base) | disc kept | hold net/trade (rule) "
             "| hold net/trade (base) | hold kept |")
    L.append("|---|---|---|---|---|---|---|")
    for r in holdout_rows:
        L.append(f"| {rule_english(r['rule'])} | ${r['disc_rule']:,.1f} | ${r['disc_base']:,.1f} | "
                 f"{r['disc_n']} | ${r['hold_rule']:,.1f} | ${r['hold_base']:,.1f} | {r['hold_n']} |")
    L.append("")
    L.append("This is a single peek at holdout, not a validation. Any rule that looks good here still "
             "has to clear a fenced Auto-Validate plus walk-forward and lockbox checks before it means "
             "anything.")
    L.append("")

    L.append("## 3. Charts")
    L.append("")
    L.append(f"- {leg_key}/win_01..16.png, {leg_key}/loss_01..16.png -- 60 bars before / 20 after "
             "entry, EMA20 + VWAP overlay, prior-day H/L/C dashed, entry (up marker) / exit (down "
             "marker), for the 16 largest discovery winners and losers by pnl_R.")
    L.append(f"- {leg_key}_path_overlay.png -- median normalized close path (ATR units, 0 at the "
             "decision bar) over the 60 bars before entry: top-decile winners vs bottom-decile losers "
             "vs all discovery trades, with interquartile shading.")
    L.append("")

    L.append("## Caveats")
    L.append("")
    L.append("- Discovery-only, single-leg. Nothing here has been checked against another strategy "
             "family -- that is feature_board.py" + apos + "s job, not this file" + apos + "s.")
    L.append("- Multiple comparisons: the lift table is BH-FDR corrected across features; the "
             "standardized-difference ranking, the tree, and the skip-rule search are NOT -- treat them "
             "as leads to test, not findings.")
    L.append("- Thin tails: top/bottom-decile means and the tree" + apos + "s deepest leaves can be a "
             "handful of trades; one outlier trade can move them a lot.")
    L.append("- The holdout check is one look. Re-running this file and re-peeking at holdout with a "
             "different rule set defeats the point of holding it out at all.")
    L.append("- Everything here must still pass a fenced Auto-Validate and the walk-forward / lockbox "
             "gauntlet before any rule is adopted into a live strategy.")

    md = "\n".join(L) + "\n"
    fp = os.path.join(out_dir, f"{leg_key}.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(md)
    return fp, len(L)


# ─────────────────────────────────────────────────────────────────────────────
# main — one leg end to end
# ─────────────────────────────────────────────────────────────────────────────

def run_leg(leg_key):
    t_all = time.time()
    print(f"\n===== {leg_key} =====")
    full, meta, df, B, day_feat = build_trade_table(leg_key)

    out_dir = DOCS_ROOT
    os.makedirs(out_dir, exist_ok=True)
    chart_dir = os.path.join(out_dir, leg_key)
    os.makedirs(chart_dir, exist_ok=True)

    csv_fp = os.path.join(out_dir, f"{leg_key}_trades.csv")
    full.to_csv(csv_fp, index=False)
    print(f"[{leg_key}] wrote {csv_fp}  rows={len(full)}")

    write_features_json(out_dir, leg_key)

    disc = full[full["tr_set"] == "discovery"].reset_index(drop=True)
    hold = full[full["tr_set"] == "holdout"].reset_index(drop=True)
    print(f"[{leg_key}] discovery n={len(disc)}  holdout n={len(hold)}  "
         f"boundary={meta['boundary']}  lockbox_from={meta['lockbox_from']}")

    Xd = disc[FEATURE_NAMES]
    pnl_r_d = disc["tr_pnl_r"].to_numpy(float)
    usd_d = disc["tr_net_usd"].to_numpy(float)
    entry_date_d = disc["tr_entry_date"].to_numpy()

    print(f"[{leg_key}] winner anatomy (permutation, ~1000 draws x {len(FEATURE_NAMES)} features)...")
    t0 = time.time()
    winner_rows = winner_anatomy(Xd, pnl_r_d, entry_date_d)
    print(f"[{leg_key}] winner anatomy done in {time.time()-t0:.1f}s")

    print(f"[{leg_key}] rule mining...")
    tree_leaves, tree_model = fit_rule_tree(Xd, pnl_r_d, usd_d)
    skip_candidates = mine_skip_rules(Xd, usd_d, entry_date_d)
    skip_top_net = sorted(skip_candidates, key=lambda d: -d["net_per_trade"])[:10]
    skip_top_mar = sorted(skip_candidates,
                          key=lambda d: -(d["mar_proxy"] if d["mar_proxy"] == d["mar_proxy"] else -1e18))[:10]

    Xh = hold[FEATURE_NAMES]
    usd_h = hold["tr_net_usd"].to_numpy(float)
    entry_date_h = hold["tr_entry_date"].to_numpy()
    base_disc = float(usd_d.sum() / len(usd_d)) if len(usd_d) else float("nan")
    base_hold = float(usd_h.sum() / len(usd_h)) if len(usd_h) else float("nan")
    holdout_rows = []
    for r in skip_top_net:
        n_d, npt_d = eval_rule(Xd, usd_d, r)
        n_h, npt_h = eval_rule(Xh, usd_h, r)
        holdout_rows.append(dict(rule=r, disc_rule=npt_d, disc_base=base_disc, disc_n=n_d,
                                 hold_rule=npt_h, hold_base=base_hold, hold_n=n_h))

    print(f"[{leg_key}] rule ledger by total money...")
    years_d = (pd.Timestamp(meta["boundary"]) - pd.Timestamp(meta["cfg"]["date_from"])).days / 365.25
    years_h = (pd.Timestamp(meta["lockbox_from"]) - pd.Timestamp(meta["boundary"])).days / 365.25
    tercile_rule = build_tercile_rule(Xd)
    ledger_rules = list(skip_top_net) + [tercile_rule]
    money_ledger = build_money_ledger(ledger_rules, Xd, usd_d, entry_date_d, years_d,
                                      Xh, usd_h, entry_date_h, years_h)

    print(f"[{leg_key}] charts...")
    ranked_disc = disc.sort_values("tr_pnl_r", ascending=False).reset_index(drop=True)
    winners16 = ranked_disc.head(16)
    losers16 = ranked_disc.tail(16).iloc[::-1].reset_index(drop=True)
    for i in range(len(winners16)):
        plot_trade_chart(df, B, day_feat, winners16.iloc[i], os.path.join(chart_dir, f"win_{i+1:02d}.png"))
    for i in range(len(losers16)):
        plot_trade_chart(df, B, day_feat, losers16.iloc[i], os.path.join(chart_dir, f"loss_{i+1:02d}.png"))

    eb_disc = disc["tr_entry_bar"].to_numpy(int)
    paths = compute_norm_paths(B, eb_disc, length=60)
    top_mask = pnl_r_d >= np.nanpercentile(pnl_r_d, 90)
    bot_mask = pnl_r_d <= np.nanpercentile(pnl_r_d, 10)
    overlay_fp = os.path.join(out_dir, f"{leg_key}_path_overlay.png")
    plot_path_overlay({"top_decile_winners": paths[top_mask], "bottom_decile_losers": paths[bot_mask],
                       "all_discovery": paths}, overlay_fp, leg_key)

    md_fp, n_lines = write_md(leg_key, meta, winner_rows, tree_leaves, skip_top_net, skip_top_mar,
                              holdout_rows, money_ledger, out_dir)
    print(f"[{leg_key}] wrote {md_fp} ({n_lines} lines)")
    print(f"[{leg_key}] leg total time {time.time()-t_all:.1f}s")

    return dict(leg=leg_key, meta=meta, winner_rows=winner_rows, tree_leaves=tree_leaves,
               skip_top_net=skip_top_net, holdout_rows=holdout_rows, money_ledger=money_ledger)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", action="append", default=None,
                    help="leg key from feature_board.LEGS (repeatable). Default: NOISE_243, ORB_314.")
    a = ap.parse_args()
    legs = a.leg if a.leg else ["NOISE_243", "ORB_314"]
    os.makedirs(DOCS_ROOT, exist_ok=True)
    results = []
    for leg_key in legs:
        results.append(run_leg(leg_key))
    return results


if __name__ == "__main__":
    main()

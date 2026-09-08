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

# legs resolved at runtime from --run/--job, keyed the same way as FB.LEGS entries
# so build_trade_table's lookup doesn't care where a leg came from.
_EXTRA_LEGS = {}


# ─────────────────────────────────────────────────────────────────────────────
# POINT AT A PAST RUN — leg_from_run(rid) builds the same leg/cfg dict shape
# build_trade_table already consumes from feature_board.LEGS + resolve_leg_config,
# but sourced from a completed run doc (users/<uid>/runs/<rid>) instead of a
# hard-coded LEGS entry. See api/runner.py's Runner._persist_run (~line 1055-1190)
# for the exact fields a run doc carries; api/runner.py:_next_run_id (~line 920) /
# sync_runs (~line 795) for how `rid` becomes that doc's id. A run doc does NOT
# carry `session` directly (unlike a backtests/<docid> job doc, which does) — it is
# inferred from `data_source` / `source_name` (e.g. "db_noadj_rth" / "NQ 5m RTH -
# no-adj"), same convention as the NOADJ_<inst>_<tf>_<session>.csv master filenames
# feature_board.load() reads. Every assumption made because a field was missing is
# printed loudly instead of silently guessed.
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_named_doc(collection, doc_id):
    """One Firestore .get() from users/<uid>/<collection>/<doc_id>, then a local JSON
    cache (tools/_featboard_cache/docs/, shared with feature_board.py's own doc cache)
    so repeat runs of this script never touch Firestore again. Returns None if the
    doc does not exist."""
    os.makedirs(FB.DOC_CACHE_DIR, exist_ok=True)
    cache_fp = os.path.join(FB.DOC_CACHE_DIR, f"{collection}_{doc_id}.json")
    if os.path.exists(cache_fp):
        with open(cache_fp, encoding="utf-8") as f:
            return json.load(f)
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred_path = "serviceAccount.json"
    if not os.path.exists(cred_path):
        cred_path = os.path.join(FB.SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    db = firestore.client()
    try:
        snap = db.collection("users").document(FB.UID).collection(collection).document(str(doc_id)).get()
    except Exception as e:                     # google.api_core ResourceExhausted / 429 and friends
        if "ResourceExhausted" in type(e).__name__ or "Quota" in str(e) or "429" in str(e):
            have = sorted(os.listdir(FB.DOC_CACHE_DIR)) if os.path.isdir(FB.DOC_CACHE_DIR) else []
            raise SystemExit(
                f"Firestore READ QUOTA EXHAUSTED (Spark plan, 50k reads/day; resets at midnight Pacific). "
                f"Cannot fetch {collection}/{doc_id}. Cached docs available offline in {FB.DOC_CACHE_DIR}: "
                f"{', '.join(have) or 'none'}. Re-run after the reset, or point --run at a cached one.")
        raise
    if not snap.exists:
        return None
    d = snap.to_dict()

    def _default(o):
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        return str(o)

    with open(cache_fp, "w", encoding="utf-8") as f:
        json.dump(d, f, default=_default, indent=1)
    return d


def _infer_session(d):
    """session -> (value, how). A `runs/<rid>` doc has no `session` field (see module
    note above); fall back to parsing it out of data_source / source_name, which both
    carry the RTH/ETH tag the master file itself is keyed on. Default RTH as a last
    resort — always reported to the caller so it can be printed, never silent."""
    s = d.get("session")
    if s:
        return str(s).upper(), "doc"
    for key in ("data_source", "source_name", "source"):
        v = str(d.get(key) or "").upper()
        if "ETH" in v:
            return "ETH", f"inferred from {key}={d.get(key)!r}"
        if "RTH" in v:
            return "RTH", f"inferred from {key}={d.get(key)!r}"
    return "RTH", "no session hint on the doc at all -- defaulted"


def _leg_dict_from_run_doc(rid, d):
    """Pure field-mapping core of leg_from_run — no network, so tests can drive it
    directly on a fake doc dict. Builds the same leg/cfg shape build_trade_table
    already consumes (leg["file"]/["key"] + cfg via leg["_resolved_cfg"])."""
    strategy_file = d.get("strategy") or ""
    if not strategy_file:
        raise SystemExit(f"run #{rid}: doc has no 'strategy' field -- can't tell which file to replay")
    strat_path = os.path.join(FB.ROOT, "augur_strategies", strategy_file)
    if not os.path.exists(strat_path):
        strat_path = os.path.join(FB.SHARED, "augur_strategies", strategy_file)
    if not os.path.exists(strat_path):
        raise SystemExit(f"run #{rid}: strategy file '{strategy_file}' not found in augur_strategies/ "
                         f"(checked {FB.ROOT} and {FB.SHARED}) -- can't replay this run")

    session, session_how = _infer_session(d)
    instrument = d.get("instrument")
    timeframe = d.get("timeframe")
    cost_pts = float(d.get("cost_pts") or 0.0)
    mult_raw = d.get("multiplier")
    if mult_raw is None:
        mult_raw = d.get("mult")
    mult = float(mult_raw) if mult_raw else 1.0
    date_from, date_to = d.get("date_from"), d.get("date_to")
    best_params = d.get("best_params") or {}
    gv = d.get("gate_validate") or {}
    lockbox_from = gv.get("lockbox_from")
    lockbox_months = d.get("lockbox_months")

    assumed = []
    if not instrument or not timeframe or not date_from or not date_to:
        assumed.append("instrument/timeframe/date window incomplete on the run doc -- results below may "
                       "be wrong")
    if session_how != "doc":
        assumed.append(f"session={session} ({session_how})")
    if not best_params:
        assumed.append("best_params empty on the doc -- falling back to the strategy file's own "
                       "DEFAULT_PARAMS")
    if not lockbox_from and not lockbox_months:
        lockbox_months = 12
        assumed.append("lockbox_months missing on the doc -- assuming 12 (the site's own default)")
    if assumed:
        print(f"[RUN_{rid}] ASSUMED: " + "; ".join(assumed))

    parity_expected = {}
    for blk_name, out_name in (("ungated_full", "full"), ("ungated_pre", "pre"),
                               ("ungated_lockbox", "lockbox")):
        blk = gv.get(blk_name)
        if isinstance(blk, dict) and blk:
            parity_expected[out_name] = dict(n=blk.get("num_trades"), net_pts=blk.get("total_pnl"),
                                             pf=blk.get("profit_factor"))

    cfg = dict(instrument=instrument, timeframe=timeframe, session=session, source=d.get("data_source"),
               cost_pts=cost_pts, mult=mult, date_from=date_from, date_to=date_to,
               lockbox_months=lockbox_months, lockbox_from=lockbox_from, best_params=best_params,
               parity_source=f"run#{rid}", parity_expected=parity_expected)

    family = os.path.splitext(strategy_file)[0].split("_")[0]
    return dict(key=f"RUN_{rid}", family=family, label=f"#{rid} {strategy_file}", file=strategy_file,
               run=rid, doc=None, _resolved_cfg=cfg)


def leg_from_run(rid):
    """Build a leg from users/<uid>/runs/<rid> — a completed run, the same run number
    shown on the site (e.g. #314). See the module note above for the doc fields relied
    on and their fallbacks."""
    d = _fetch_named_doc("runs", str(rid))
    if d is None:
        raise SystemExit(f"run #{rid}: no such document in Firestore users/{FB.UID}/runs")
    return _leg_dict_from_run_doc(rid, d)


def leg_from_job(doc_id):
    """Build a leg from a backtests/<doc_id> job doc directly (the same shape
    feature_board.resolve_leg_config already reads via leg['doc'] — reused verbatim,
    only the strategy filename + family are pulled here for the leg's own label)."""
    d = FB._fetch_doc(doc_id)          # cached; a 2nd read inside resolve_leg_config is free
    strategy_file = d.get("strategy") or ""
    if not strategy_file:
        raise SystemExit(f"job {doc_id}: doc has no 'strategy' field -- can't tell which file to replay")
    strat_path = os.path.join(FB.ROOT, "augur_strategies", strategy_file)
    if not os.path.exists(strat_path):
        strat_path = os.path.join(FB.SHARED, "augur_strategies", strategy_file)
    if not os.path.exists(strat_path):
        raise SystemExit(f"job {doc_id}: strategy file '{strategy_file}' not found in augur_strategies/ "
                         f"(checked {FB.ROOT} and {FB.SHARED}) -- can't replay this job")
    family = os.path.splitext(strategy_file)[0].split("_")[0]
    return dict(key=f"JOB_{doc_id}", family=family, label=f"job {doc_id} ({strategy_file})",
               file=strategy_file, run=d.get("run_id"), doc=doc_id)


def _find_leg(leg_key):
    leg = _EXTRA_LEGS.get(leg_key)
    if leg is not None:
        return leg
    matches = [l for l in FB.LEGS if l["key"] == leg_key]
    if not matches:
        raise SystemExit(f"unknown leg '{leg_key}' -- not in feature_board.LEGS and not registered via "
                         "--run/--job this session. Use --list to see the hard-coded leg keys.")
    return matches[0]


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


def pctile_vs_prior_days(x, day_id, year_days=252, min_days=60, samples_per_day=60):
    """Trailing-year percentile rank (0-100) of a BAR-level series, causal and fast.

    The reference distribution is rebuilt once per trading day from the prior `year_days`
    days (never today), subsampled to ~`samples_per_day` values per day, and every bar of
    the day is ranked against it with a binary search. Equivalent in spirit to a rolling
    rank over a one-year window of bars, but O(n log) instead of O(n * window) - the
    rolling form is fine on 5-minute bars and never finishes on 1-minute bars (5.6M rows,
    350k-bar windows)."""
    x = np.asarray(x, float)
    n = len(x)
    out = np.full(n, np.nan)
    days = np.asarray(day_id)
    if n == 0:
        return out
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    ends = np.r_[starts[1:], n]
    bpd = max(1, int(np.median(ends - starts)))
    stride = max(1, bpd // max(1, samples_per_day))
    day_samples = [x[s:e:stride] for s, e in zip(starts, ends)]
    for k in range(len(starts)):
        if k < min_days:
            continue
        ref = np.concatenate(day_samples[max(0, k - year_days):k])
        ref = ref[~np.isnan(ref)]
        if len(ref) < 100:
            continue
        ref.sort()
        seg = x[starts[k]:ends[k]]
        r = np.searchsorted(ref, seg, side="right") / float(len(ref)) * 100.0
        r[np.isnan(seg)] = np.nan
        out[starts[k]:ends[k]] = r
    return out


def bars_since_extreme(a, w, kind):
    """Bars since the window's max (kind='max') or min (kind='min') over the last `w` bars,
    inclusive of the current bar; ties resolve to the OLDEST bar (numpy argmax semantics).
    Vectorized: w shifted passes instead of a Python callback per row."""
    a = np.asarray(a, float)
    n = len(a)
    best = np.full(n, np.nan)
    idx = np.full(n, np.nan)
    for j in range(w):
        sh = np.full(n, np.nan)
        sh[j:] = a[:n - j]
        ok = ~np.isnan(sh)
        if j == 0:
            best = np.where(ok, sh, np.nan)
            idx = np.where(ok, 0.0, np.nan)
            continue
        better = ok & (np.isnan(best) | ((sh >= best) if kind == "max" else (sh <= best)))
        best = np.where(better, sh, best)
        idx = np.where(better, float(j), idx)
    if w > 1:
        idx[:w - 1] = np.nan
    return idx


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
    _dayid = df["day_id"].to_numpy()
    B["atr_pctile_bar"] = pctile_vs_prior_days(B["atr_bar"], _dayid, YEAR_DAYS)
    B["bbw_pctile_bar"] = pctile_vs_prior_days(bbw_bar, _dayid, YEAR_DAYS)

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
    B["bars_since_hi20"] = bars_since_extreme(high, 20, "max")
    B["bars_since_lo20"] = bars_since_extreme(low, 20, "min")
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
    leg = _find_leg(leg_key)
    cfg = leg.get("_resolved_cfg") or FB.resolve_leg_config(leg)
    tf_min = int(str(cfg["timeframe"]).rstrip("m"))
    if verbose:
        print(f"[{leg_key}] {cfg['instrument']} {cfg['timeframe']} {cfg['session']} "
              f"{cfg['date_from']}..{cfg['date_to']}  source={cfg.get('parity_source')}")
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

    # ── parity check against the source doc's own ungated_full (loud, non-fatal:
    # proceed either way, but flag it hard so a mismatch is never mistaken for a
    # clean replay) — same 2%-relative-tolerance rule feature_board.py's own leg
    # parity table uses, applied here to the FULL (pre-exclusion) trade list. ──
    expected = (cfg.get("parity_expected") or {}).get("full")
    full_net = float(usd.sum())
    parity = dict(source=cfg.get("parity_source"), got_n=int(len(trades)), got_net=round(full_net, 2),
                 expected_n=None, expected_net=None, ok=None)
    if expected and expected.get("net_pts") is not None:
        exp_net = float(expected["net_pts"]) * cfg["mult"]
        parity["expected_n"] = expected.get("n")
        parity["expected_net"] = round(exp_net, 2)
        parity["ok"] = bool(exp_net != 0 and abs(full_net - exp_net) / abs(exp_net) <= 0.02)
    tag = "PASS" if parity["ok"] else ("FAIL" if parity["ok"] is False else "n/a (no parity target on this doc)")
    print(f"[{leg_key}] PARITY {tag}  got n={parity['got_n']} net=${full_net:,.0f}  "
         f"expected n={parity['expected_n']} net="
         f"{'n/a' if parity['expected_net'] is None else '$' + format(parity['expected_net'], ',.0f')}")
    if parity["ok"] is False:
        print(f"[{leg_key}] *** PARITY FAIL *** local replay does not match the doc's own ungated_full "
             "within 2% -- proceeding anyway (below), but treat every number in this report as suspect "
             "until this is understood (stale synced params? a different data revision? a cost/mult "
             "mismatch?).")

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
               n_holdout=int((labels_kept == "holdout").sum()), parity=parity)
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
# ANALYSIS 2d — holdout-only tercile lift, ONE fixed tercile per feature (top
# third minus bottom third of that feature's own DISCOVERY distribution), so a
# feature's discovery-vs-holdout sign agreement can be read directly, on the
# same threshold, without going through feature_board's LIFT threshold picker
# (which is not guaranteed to be a tercile). Feeds the cross-run COMPARE mode.
# ─────────────────────────────────────────────────────────────────────────────

TERCILE_LO_PCTILE = 100.0 / 3.0
TERCILE_HI_PCTILE = 100.0 / 3.0 * 2.0


def compute_tercile_lift_holdout(Xd, pnl_r_d, Xh, pnl_r_h, min_group=10):
    """For every feature in Xd: fix top/bottom tercile thresholds on discovery, then
    report the discovery lift AND the holdout lift on those SAME thresholds (mean pnl_R
    in the top third minus the bottom third), plus whether their signs agree. Returns a
    list of dicts, one per feature, in Xd.columns order."""
    pnl_r_d = np.asarray(pnl_r_d, float)
    pnl_r_h = np.asarray(pnl_r_h, float)
    rows = []
    for nm in Xd.columns:
        xd = Xd[nm].to_numpy(float)
        xh = Xh[nm].to_numpy(float) if nm in Xh.columns else np.full(len(pnl_r_h), np.nan)
        valid_d = ~np.isnan(xd)
        if valid_d.sum() < min_group:
            rows.append(dict(feature=nm, threshold_top=None, threshold_bot=None,
                             disc_lift=None, hold_lift=None, same_sign=None))
            continue
        top_thr = float(np.nanpercentile(xd, TERCILE_HI_PCTILE))
        bot_thr = float(np.nanpercentile(xd, TERCILE_LO_PCTILE))

        d_hi, d_lo = xd >= top_thr, xd <= bot_thr
        disc_lift = None
        if d_hi.sum() >= min_group and d_lo.sum() >= min_group:
            disc_lift = float(np.nanmean(pnl_r_d[d_hi]) - np.nanmean(pnl_r_d[d_lo]))

        h_hi, h_lo = xh >= top_thr, xh <= bot_thr
        hold_lift = None
        if np.nansum(h_hi) >= min_group and np.nansum(h_lo) >= min_group:
            hold_lift = float(np.nanmean(pnl_r_h[h_hi]) - np.nanmean(pnl_r_h[h_lo]))

        same_sign = None
        if disc_lift is not None and hold_lift is not None and disc_lift != 0:
            same_sign = bool(np.sign(disc_lift) == np.sign(hold_lift))

        rows.append(dict(feature=nm, threshold_top=top_thr, threshold_bot=bot_thr,
                         disc_lift=disc_lift, hold_lift=hold_lift, same_sign=same_sign))
    return rows


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

def howto_lines():
    """The 'HOW TO POINT IT AT A PAST RUN' blurb, shared verbatim by every generated
    md's header and docs/anatomy/README.md."""
    return [
        "## How to point this at a past run",
        "",
        "- `python tools/trade_anatomy.py --run 314` replays run #314's own crowned parameters on its own "
        "window and costs (repeatable: `--run 314 --run 309`). `--job <backtests-doc-id>` points at a job "
        "doc directly. `--leg <KEY>` runs one of the hard-coded legs in feature_board.LEGS; `--list` "
        "prints those keys plus this usage line.",
        "- DISCOVERY / HOLDOUT is a hard split by calendar date, not trade count: only the first 60% of "
        "the leg's pre-lockbox span is mined below. The remaining 40% (holdout) is touched exactly once, "
        "as a single pre-registered check. Lockbox trades (the leg's own last N months) are never loaded "
        "here at all.",
        "- Nothing on this page is a finding by itself. A rule only means something once it clears the "
        "TOTAL-MONEY ledger in section 2c (not the per-trade averages in sections 1/2 -- that section "
        "explains the trap) AND has passed a fenced Auto-Validate with walk-forward and lockbox checks. "
        "Never adopt a rule straight from this report.",
        "",
    ]


def write_features_json(out_dir, leg_key):
    doc = {nm: dict(group=FEATURE_GROUP[nm], desc=FEATURE_DESC[nm]) for nm in FEATURE_NAMES}
    fp = os.path.join(out_dir, f"{leg_key}_features.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    return fp


# ─────────────────────────────────────────────────────────────────────────────
# machine-readable per-run summary — the input the --compare mode reads.
# Floats round to 4dp; NaN/inf -> null (json.dump would otherwise emit the
# non-standard "NaN"/"Infinity" tokens).
# ─────────────────────────────────────────────────────────────────────────────

def _jsonify(v):
    if isinstance(v, dict):
        return {k: _jsonify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonify(x) for x in v]
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, float):
        return round(v, 4) if np.isfinite(v) else None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (datetime.date, datetime.datetime, pd.Timestamp)):
        return v.isoformat()
    return v


def write_summary_json(leg_key, leg_info, meta, winner_rows, money_ledger, tercile_rows, out_dir):
    """docs/anatomy/<leg_key>_summary.json -- everything --compare needs to read this leg without
    re-running it: leg identity/window, every feature's winner-anatomy lift (not just the report's
    top 20), every section-2c ledger row, and the holdout-only tercile lift per feature."""
    cfg = meta["cfg"]
    leg_meta = dict(
        key=leg_key, label=leg_info.get("label"), family=leg_info.get("family"),
        file=leg_info.get("file"), run=leg_info.get("run"),
        instrument=cfg.get("instrument"), timeframe=cfg.get("timeframe"), session=cfg.get("session"),
        date_from=cfg.get("date_from"), date_to=cfg.get("date_to"),
        discovery_from=cfg.get("date_from"), discovery_to=meta["boundary"],
        holdout_from=meta["boundary"], holdout_to=meta["lockbox_from"],
        lockbox_from=meta["lockbox_from"], n_discovery=meta["n_discovery"], n_holdout=meta["n_holdout"],
        n_lockbox_excluded=meta["n_lockbox_excluded"], r_unit=meta["r_unit"], parity=meta.get("parity"),
    )
    winner_out = [dict(feature=r["feature"], group=r["group"], lift_r=r["lift"], lift_q=r["lift_q"],
                       top_dec_mean=r["mean_top_decile"], bot_dec_mean=r["mean_bottom_decile"],
                       std_diff=r["std_diff"]) for r in winner_rows]
    ledger_out = []
    for row in money_ledger:
        rule, rd, rh = row["rule"], row["disc"], row["hold"]
        ledger_out.append(dict(
            rule_text=rule_english(rule), feature=rule["feature"], direction=rule["direction"],
            threshold=rule["threshold"], pctile=rule.get("pctile"), kind=rule.get("kind", "skip"),
            kept_pct_d=rd["kept_pct"], kept_pct_h=rh["kept_pct"],
            net_rule_d=rd["net_rule"], net_base_d=rd["net_base"],
            net_rule_h=rh["net_rule"], net_base_h=rh["net_base"],
            pct_d=rd["pct_change"], pct_h=rh["pct_change"],
            mar_d=rd["mar"], base_mar_d=rd["base_mar"], mar_h=rh["mar"], base_mar_h=rh["base_mar"],
            tilt_mar_d=rd["tilt_mar"], tilt_mar_h=rh["tilt_mar"],
            skip_helped_d=rd["yrs_helped"], skip_helped_h=rh["yrs_helped"], verdict=row["verdict"]))
    doc = _jsonify(dict(leg=leg_meta, winner_anatomy=winner_out, ledger=ledger_out,
                        tercile_lift_holdout=tercile_rows))
    fp = os.path.join(out_dir, f"{leg_key}_summary.json")
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
    L.extend(howto_lines())
    cfg = meta["cfg"]
    p = meta.get("parity") or {}
    if p.get("ok") is not None:
        p_tag = "PASS" if p["ok"] else "FAIL"
        L.append(f"Parity vs the source doc's own ungated_full ({p.get('source')}): **{p_tag}** -- "
                 f"got n={p.get('got_n')} net=${p.get('got_net'):,.0f}, expected n={p.get('expected_n')} "
                 f"net=${p.get('expected_net'):,.0f}."
                 + ("" if p["ok"] else " Proceeding anyway per the loud-note rule -- treat every number "
                    "below as suspect until this mismatch is understood."))
        L.append("")
    elif p:
        L.append(f"Parity vs the source doc's own ungated_full: n/a ({p.get('source')} -- no parity "
                 "target on this doc).")
        L.append("")
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

    tercile_rows = compute_tercile_lift_holdout(Xd, pnl_r_d, Xh, hold["tr_pnl_r"].to_numpy(float))
    leg_info = _find_leg(leg_key)
    summ_fp = write_summary_json(leg_key, leg_info, meta, winner_rows, money_ledger, tercile_rows, out_dir)
    print(f"[{leg_key}] wrote {summ_fp}")

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
               skip_top_net=skip_top_net, holdout_rows=holdout_rows, money_ledger=money_ledger,
               tercile_lift_holdout=tercile_rows)


# ─────────────────────────────────────────────────────────────────────────────
# --from-csv — rebuild sections 1/2/2c + the summary JSON from an existing
# <KEY>_trades.csv (as written by run_leg above) with no Firestore and no price
# data reload. Section 3 (charts) needs the bar-level OHLC this mode doesn't
# have, so it is skipped. date_from/boundary/lockbox_from aren't columns on the
# CSV, so they are re-derived from the trade dates themselves -- loudly flagged,
# same convention as the run-doc-field ASSUMED notes above.
# ─────────────────────────────────────────────────────────────────────────────

def build_trade_table_from_csv(csv_path, leg_key=None):
    df = pd.read_csv(csv_path)
    if "tr_entry_date" not in df.columns:
        raise SystemExit(f"--from-csv {csv_path}: no tr_entry_date column -- not a trade_anatomy trades CSV")
    entry_date = pd.to_datetime(df["tr_entry_date"]).dt.date
    df["tr_entry_date"] = entry_date
    missing_feats = [c for c in FEATURE_NAMES if c not in df.columns]
    if missing_feats:
        head = ", ".join(missing_feats[:5]) + ("..." if len(missing_feats) > 5 else "")
        raise SystemExit(f"--from-csv {csv_path}: missing feature column(s) {head} -- not a "
                         "trade_anatomy trades CSV")
    for req in ("tr_set", "tr_pnl_r", "tr_net_usd"):
        if req not in df.columns:
            raise SystemExit(f"--from-csv {csv_path}: missing '{req}' column -- not a trade_anatomy "
                             "trades CSV")

    key = leg_key or (str(df["leg"].iloc[0]) if "leg" in df.columns and len(df)
                      else os.path.splitext(os.path.basename(csv_path))[0].replace("_trades", ""))

    disc = df[df["tr_set"] == "discovery"]
    hold = df[df["tr_set"] == "holdout"]
    all_dates = np.asarray(entry_date)
    date_from = min(all_dates) if len(all_dates) else None
    date_to = max(all_dates) if len(all_dates) else None
    boundary = min(hold["tr_entry_date"]) if len(hold) else date_to
    lockbox_from = (date_to + datetime.timedelta(days=1)) if date_to is not None else None
    print(f"[--from-csv {key}] ASSUMED: date_from/boundary/lockbox_from are not columns on the CSV -- "
         "re-derived from the trade dates themselves (date_from = earliest trade, boundary = earliest "
         "holdout trade, lockbox_from = latest trade + 1 day). r_unit re-derived as the median "
         "net_usd/pnl_R ratio. Section 3 (charts) is skipped -- no bar-level OHLC in a trades CSV.")

    ratio = (disc["tr_net_usd"] / disc["tr_pnl_r"].replace(0, np.nan)).dropna()
    r_unit = float(ratio.median()) if len(ratio) else 1.0
    if not np.isfinite(r_unit) or r_unit <= 0:
        r_unit = 1.0

    cfg = dict(instrument="?", timeframe="?", session="?", date_from=str(date_from), date_to=str(date_to),
              best_params={}, parity_source=f"from-csv:{csv_path}", parity_expected={})
    meta = dict(leg=key, cfg=cfg, boundary=boundary, lockbox_from=str(lockbox_from),
               n_total_replayed=len(df), n_lockbox_excluded=0, n_pre_lockbox=len(df),
               n_dropped_no_history=0, r_unit=r_unit, n_discovery=int(len(disc)), n_holdout=int(len(hold)),
               parity=dict(source=cfg["parity_source"], got_n=len(df), got_net=None,
                          expected_n=None, expected_net=None, ok=None))
    return df, meta


def run_leg_from_csv(csv_path, leg_key=None):
    print(f"\n===== --from-csv {csv_path} =====")
    full, meta = build_trade_table_from_csv(csv_path, leg_key)
    key = meta["leg"]
    out_dir = DOCS_ROOT
    os.makedirs(out_dir, exist_ok=True)

    disc = full[full["tr_set"] == "discovery"].reset_index(drop=True)
    hold = full[full["tr_set"] == "holdout"].reset_index(drop=True)
    print(f"[{key}] discovery n={len(disc)}  holdout n={len(hold)}  boundary={meta['boundary']}  "
         f"lockbox_from={meta['lockbox_from']}")

    Xd = disc[FEATURE_NAMES]
    pnl_r_d = disc["tr_pnl_r"].to_numpy(float)
    usd_d = disc["tr_net_usd"].to_numpy(float)
    entry_date_d = disc["tr_entry_date"].to_numpy()

    winner_rows = winner_anatomy(Xd, pnl_r_d, entry_date_d)
    tree_leaves, _ = fit_rule_tree(Xd, pnl_r_d, usd_d)
    skip_candidates = mine_skip_rules(Xd, usd_d, entry_date_d)
    skip_top_net = sorted(skip_candidates, key=lambda d: -d["net_per_trade"])[:10]
    skip_top_mar = sorted(skip_candidates,
                          key=lambda d: -(d["mar_proxy"] if d["mar_proxy"] == d["mar_proxy"] else -1e18))[:10]

    Xh = hold[FEATURE_NAMES]
    pnl_r_h = hold["tr_pnl_r"].to_numpy(float)
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

    years_d = max((pd.Timestamp(meta["boundary"]) - pd.Timestamp(meta["cfg"]["date_from"])).days / 365.25, 1e-6)
    years_h = max((pd.Timestamp(meta["lockbox_from"]) - pd.Timestamp(meta["boundary"])).days / 365.25, 1e-6)
    tercile_rule = build_tercile_rule(Xd)
    ledger_rules = list(skip_top_net) + [tercile_rule]
    money_ledger = build_money_ledger(ledger_rules, Xd, usd_d, entry_date_d, years_d,
                                      Xh, usd_h, entry_date_h, years_h)
    tercile_rows = compute_tercile_lift_holdout(Xd, pnl_r_d, Xh, pnl_r_h)

    md_fp, n_lines = write_md(key, meta, winner_rows, tree_leaves, skip_top_net, skip_top_mar,
                              holdout_rows, money_ledger, out_dir)
    print(f"[{key}] wrote {md_fp} ({n_lines} lines)")

    leg_info = dict(key=key, label=f"--from-csv {os.path.basename(csv_path)}",
                    family=key.split("_")[0], file=None, run=None)
    summ_fp = write_summary_json(key, leg_info, meta, winner_rows, money_ledger, tercile_rows, out_dir)
    print(f"[{key}] wrote {summ_fp}")

    return dict(leg=key, meta=meta, winner_rows=winner_rows, tree_leaves=tree_leaves,
               skip_top_net=skip_top_net, holdout_rows=holdout_rows, money_ledger=money_ledger,
               tercile_lift_holdout=tercile_rows)


# ─────────────────────────────────────────────────────────────────────────────
# --compare — read N legs' *_summary.json and write ONE cross-run answer:
# which pre-entry conditions repeat, with the same sign, across the discovery
# AND the once-touched holdout of multiple runs. Never re-runs anything.
# ─────────────────────────────────────────────────────────────────────────────

def load_summary(key):
    fp = os.path.join(DOCS_ROOT, f"{key}_summary.json")
    if not os.path.exists(fp):
        raise SystemExit(f"--compare: missing summary JSON for '{key}' at {fp} -- run "
                         f"'python tools/trade_anatomy.py --leg {key}' (or --run/--job/--from-csv) "
                         "first so it gets written.")
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def _sign(x):
    if x is None or (isinstance(x, float) and x != x):
        return None
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def build_replication_table(summaries, keys):
    """One row per FEATURE_META feature: each run's discovery-lift sign/q and holdout-tercile-lift
    sign, a replication SCORE = count of runs where (discovery q<0.10) AND (holdout sign agrees), and
    the mean |discovery lift| across runs that had one. Sorted by score desc, then mean |lift| desc."""
    rows = []
    for nm in FEATURE_NAMES:
        per_run = {}
        rep_score = 0
        abs_lifts = []
        for k in keys:
            s = summaries[k]
            wa = {r["feature"]: r for r in s.get("winner_anatomy", [])}
            tl = {r["feature"]: r for r in s.get("tercile_lift_holdout", [])}
            w, t = wa.get(nm), tl.get(nm)
            lift_r = w.get("lift_r") if w else None
            lift_q = w.get("lift_q") if w else None
            hold_lift = t.get("hold_lift") if t else None
            sign_d, sign_h = _sign(lift_r), _sign(hold_lift)
            sig = lift_q is not None and lift_q < 0.10
            agree = sign_d is not None and sign_h is not None and sign_d != 0 and sign_d == sign_h
            if sig and agree:
                rep_score += 1
            if lift_r is not None:
                abs_lifts.append(abs(lift_r))
            per_run[k] = dict(lift_r=lift_r, lift_q=lift_q, hold_lift=hold_lift,
                              sign_d=sign_d, sign_h=sign_h, sig=sig, agree=agree)
        rows.append(dict(feature=nm, group=FEATURE_GROUP.get(nm, "?"), per_run=per_run,
                         rep_score=rep_score, mean_abs_lift=float(np.mean(abs_lifts)) if abs_lifts else 0.0))
    rows.sort(key=lambda r: (-r["rep_score"], -r["mean_abs_lift"]))
    return rows


def consistent_conditions(rep_rows, keys, min_runs=3):
    """A feature is CONSISTENT (for a sign) if >= min_runs runs have BOTH a discovery lift of that
    sign AND a holdout tercile lift of that same sign -- runs where holdout disagrees are simply not
    part of that count; they don't disqualify the runs that do agree."""
    out = []
    for r in rep_rows:
        per_run = r["per_run"]
        for sign in (1, -1):
            confirmed = [k for k in keys if per_run[k]["sign_d"] == sign and per_run[k]["sign_h"] == sign]
            if len(confirmed) >= min_runs:
                out.append(dict(feature=r["feature"], group=r["group"], sign=sign, runs=confirmed,
                                detail={k: per_run[k] for k in confirmed}))
    return out


def _canonical_rule_text(feature, direction, pctile, kind):
    cmp_ = "<" if direction == "skip_below" else ">"
    tag = " [tercile]" if kind == "tercile" else ""
    pc = "?" if pctile is None else pctile
    return f"Skip trades where {feature} {cmp_} p{pc}{tag} (threshold fit per-run on its own discovery set)"


def ledger_rollup(summaries, keys, min_runs=2, robust_min=3):
    """Group each run's section-2c ledger rows by RULE RECIPE (feature + direction + percentile +
    kind), not the literal formatted threshold -- thresholds are fit per-run on that run's own
    discovery distribution, so the same recipe almost never lands on the same numeric threshold twice.
    ROBUST = carries (either the filter or the size-tilt form) in >= robust_min runs and is a regime
    artifact in none."""
    by_rule = {}
    for k in keys:
        for row in summaries[k].get("ledger", []):
            key_tup = (row["feature"], row["direction"], row.get("pctile"), row.get("kind", "skip"))
            by_rule.setdefault(key_tup, {})[k] = dict(verdict=row["verdict"], rule_text=row["rule_text"],
                                                       threshold=row["threshold"])
    out = []
    for (feature, direction, pctile, kind), per_run in by_rule.items():
        if len(per_run) < min_runs:
            continue
        n_carries = sum(1 for v in per_run.values() if v["verdict"] == "carries")
        n_tilt = sum(1 for v in per_run.values() if v["verdict"] == "carries as tilt")
        n_regime = sum(1 for v in per_run.values() if v["verdict"] == "regime artifact")
        robust = (n_carries + n_tilt) >= robust_min and n_regime == 0
        out.append(dict(rule_text=_canonical_rule_text(feature, direction, pctile, kind),
                        feature=feature, direction=direction, pctile=pctile, kind=kind,
                        per_run={k: v["verdict"] for k, v in per_run.items()}, per_run_detail=per_run,
                        n_carries=n_carries, n_tilt=n_tilt, n_regime=n_regime, robust=robust))
    out.sort(key=lambda r: (-r["robust"], -(r["n_carries"] + r["n_tilt"]), r["n_regime"]))
    return out


def write_compare_md(keys, label, rep_rows, consistent, rollup, out_dir):
    apos = chr(39)
    L = [f"# COMPARE {label} -- cross-run replication", ""]
    L.append(f"Runs compared ({len(keys)}): " + ", ".join(f"`{k}`" for k in keys) + ".")
    L.append("")
    L.append("This reads each run's own `<KEY>_summary.json` (never re-runs anything) and asks one "
             "question: which pre-entry conditions repeat, with the same sign, in discovery AND in "
             "that run's own once-touched holdout, across multiple runs.")
    L.append("")

    L.append("## a. Replication table")
    L.append("")
    L.append(f"Discovery lift sign per run (up-arrow positive / down-arrow negative), **bold** when that "
             f"run's discovery lift_q < 0.10, plus a checkmark when the SAME run's holdout tercile lift "
             f"(fixed threshold, from `tercile_lift_holdout`) has the same sign. Sorted by replication "
             f"score (count of runs where q<0.10 AND holdout agrees), then mean |discovery lift|.")
    L.append("")
    L.append("| feature | group | " + " | ".join(keys) + " | rep score |")
    L.append("|---|---|" + "---|" * len(keys) + "---|")
    for r in rep_rows:
        cells = []
        for k in keys:
            pr = r["per_run"][k]
            sd = pr["sign_d"]
            if sd is None:
                cells.append("n/a")
                continue
            arrow = "▲" if sd > 0 else ("▼" if sd < 0 else "=")
            txt = f"**{arrow}**" if pr["sig"] else arrow
            if pr["agree"]:
                txt += "✓"
            cells.append(txt)
        L.append(f"| {r['feature']} | {r['group']} | " + " | ".join(cells) + f" | {r['rep_score']} |")
    L.append("")

    L.append("## b. Consistent conditions")
    L.append("")
    L.append("Features with the SAME discovery-lift sign in >= 3 runs, where the holdout tercile lift "
             "agrees in every one of those runs. This is the answer to read first.")
    L.append("")
    if not consistent:
        L.append("None. No feature clears same-sign discovery + full holdout agreement in 3 or more of "
                 f"the {len(keys)} runs compared.")
    else:
        for c in consistent:
            direction_word = "higher" if c["sign"] > 0 else "lower"
            L.append(f"- **{c['feature']}** ({c['group']}) -- {direction_word} values precede better "
                     f"trades, confirmed on {len(c['runs'])} runs' own holdout: " + "; ".join(
                         f"{k} disc={_fmt(c['detail'][k]['lift_r'])} (q={_fmt(c['detail'][k]['lift_q'], 4)}) "
                         f"hold={_fmt(c['detail'][k]['hold_lift'])}" for k in c["runs"]))
    L.append("")

    L.append("## c. Ledger roll-up")
    L.append("")
    L.append("Every section-2c rule RECIPE (feature + direction + percentile) mined in >= 2 runs, with "
             "its verdict per run (thresholds are fit per-run on that run's own discovery set, so the "
             "numeric threshold is not compared, only the recipe and the verdict). ROBUST = carries "
             f"(filter or size-tilt) in >= 3 runs and is a regime artifact in none.")
    L.append("")
    L.append("| rule | " + " | ".join(keys) + " | carries | tilt | regime | ROBUST |")
    L.append("|---|" + "---|" * len(keys) + "---|---|---|---|")
    for r in rollup:
        cells = [r["per_run"].get(k, "n/a") for k in keys]
        L.append(f"| {r['rule_text']} | " + " | ".join(cells) +
                 f" | {r['n_carries']} | {r['n_tilt']} | {r['n_regime']} | "
                 f"{'YES' if r['robust'] else 'no'} |")
    if not rollup:
        L.append("| (no rule recipe appears in 2 or more runs' ledgers) | " + " | ".join(["-"] * len(keys)) +
                 " | - | - | - | - |")
    L.append("")

    L.append("## d. Summary")
    L.append("")
    n_robust = sum(1 for r in rollup if r["robust"])
    if consistent:
        feats = ", ".join(sorted({c["feature"] for c in consistent}))
        L.append(f"{len({c['feature'] for c in consistent})} pre-entry condition(s) repeat with the "
                 f"same sign across >= 3 of the {len(keys)} runs compared AND hold their sign on each "
                 f"of those runs' own untouched holdout set: {feats}.")
    else:
        L.append(f"No pre-entry condition repeats with the same discovery sign across >= 3 of the "
                 f"{len(keys)} runs compared with full holdout agreement.")
    if n_robust:
        L.append(f"{n_robust} section-2c rule recipe(s) are ROBUST across runs (carry, as a filter or a "
                 "size tilt, in >= 3 runs, never a regime artifact).")
    else:
        L.append("No section-2c rule recipe clears the ROBUST bar (>= 3 runs carrying, zero regime "
                 "artifacts).")
    L.append("")
    L.append(f"Standing caveat: this is still discovery-only mining with one pre-registered holdout peek "
             f"per run, pooled across runs -- it is a replication READ, not a validation. Nothing above "
             f"is adoptable without a fenced Auto-Validate (walk-forward + lockbox) on whatever "
             f"condition{apos}s or rules survive this comparison.")

    md = "\n".join(L) + "\n"
    fp = os.path.join(out_dir, f"COMPARE_{label}.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(md)
    return fp


def compare_legs(keys, label):
    summaries = {k: load_summary(k) for k in keys}
    rep_rows = build_replication_table(summaries, keys)
    consistent = consistent_conditions(rep_rows, keys)
    rollup = ledger_rollup(summaries, keys)

    out_dir = DOCS_ROOT
    os.makedirs(out_dir, exist_ok=True)
    md_fp = write_compare_md(keys, label, rep_rows, consistent, rollup, out_dir)
    json_doc = _jsonify(dict(keys=keys, label=label, replication_table=rep_rows,
                             consistent_conditions=consistent, ledger_rollup=rollup))
    json_fp = os.path.join(out_dir, f"COMPARE_{label}.json")
    with open(json_fp, "w", encoding="utf-8") as f:
        json.dump(json_doc, f, indent=1)
    print(f"[compare {label}] wrote {md_fp}")
    print(f"[compare {label}] wrote {json_fp}")
    return dict(md=md_fp, json=json_fp, rep_rows=rep_rows, consistent=consistent, rollup=rollup)


def write_readme():
    os.makedirs(DOCS_ROOT, exist_ok=True)
    fp = os.path.join(DOCS_ROOT, "README.md")
    lines = ["# docs/anatomy", ""] + howto_lines()
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", action="append", default=None,
                    help="leg key from feature_board.LEGS (repeatable). Default: NOISE_243, ORB_314.")
    ap.add_argument("--run", action="append", default=None, type=int,
                    help="point at a past run by its run number (repeatable), e.g. --run 314 --run 309. "
                        "Reads users/<uid>/runs/<rid> in Firestore, replays the crowned params on the "
                        "run's own window/costs, and parity-checks against gate_validate.ungated_full.")
    ap.add_argument("--job", action="append", default=None,
                    help="point at a backtests/<docid> job doc directly (repeatable).")
    ap.add_argument("--from-csv", action="append", default=None, metavar="PATH",
                    help="rebuild sections 1/2/2c + the summary JSON from an existing <KEY>_trades.csv "
                        "(repeatable) -- no Firestore, no price-data reload. Charts (section 3) are "
                        "skipped in this mode.")
    ap.add_argument("--compare", nargs="+", default=None, metavar="KEY",
                    help="read docs/anatomy/<KEY>_summary.json for each KEY (repeatable, >=2) and write "
                        "COMPARE_<label>.md/.json instead of running any leg.")
    ap.add_argument("--compare-label", default="COMPARE",
                    help="output name suffix for --compare: writes COMPARE_<label>.md/.json. "
                        "Default: COMPARE.")
    ap.add_argument("--list", action="store_true",
                    help="print the hard-coded legs (feature_board.LEGS) and the usage line, then exit.")
    a = ap.parse_args()

    if a.list:
        print("Usage:")
        print("  python tools/trade_anatomy.py --leg NOISE_243 --leg ORB_314   # default = these two")
        print("  python tools/trade_anatomy.py --run 314 --run 309             # point at a past run by number")
        print("  python tools/trade_anatomy.py --job <backtests-doc-id>        # point at a job doc directly")
        print("  python tools/trade_anatomy.py --from-csv docs/anatomy/NOISE_243_trades.csv   # no Firestore")
        print("  python tools/trade_anatomy.py --compare RUN_309 RUN_226 --compare-label ENGUQ")
        print()
        print("Hard-coded legs (feature_board.LEGS):")
        for l in FB.LEGS:
            print(f"  {l['key']:<12} family={l['family']:<8} file={l['file']:<28} {l['label']}")
        return []

    if a.compare:
        os.makedirs(DOCS_ROOT, exist_ok=True)
        compare_legs(list(a.compare), a.compare_label)
        return []

    leg_keys = list(a.leg) if a.leg else []
    for rid in (a.run or []):
        leg = leg_from_run(rid)
        _EXTRA_LEGS[leg["key"]] = leg
        leg_keys.append(leg["key"])
    for doc_id in (a.job or []):
        leg = leg_from_job(doc_id)
        _EXTRA_LEGS[leg["key"]] = leg
        leg_keys.append(leg["key"])
    csv_paths = list(a.from_csv) if a.from_csv else []
    if not leg_keys and not csv_paths:
        leg_keys = ["NOISE_243", "ORB_314"]

    os.makedirs(DOCS_ROOT, exist_ok=True)
    write_readme()
    results = []
    for leg_key in leg_keys:
        results.append(run_leg(leg_key))
    for csv_path in csv_paths:
        results.append(run_leg_from_csv(csv_path))
    return results


if __name__ == "__main__":
    main()

"""tools/qqq_paper.py — QQQ paper-trading signal engine.

Ports the three crowned NQ strategies to QQQ SHARES using free Yahoo Finance
intraday data (yfinance). Signals + a paper blotter ONLY: no Alpaca, no
Webull, no order placement, nothing here ever touches a broker or real money.

THE THREE LEGS (params imported directly from api/paper.py — the same source
of truth the NQ shadow-paper runner uses — so this tool can never silently
drift from the crowned NQ config):

  ORB_234    augur_strategies/ORB_3_6_C2.py (base ORB_3_6.py), 5m RTH.
             params = api.paper.ORB_234. Gate: api.paper.ORB_GATE (hybrid
             rf@0.45), model C:\\EdgeLog\\gate_models\\ORB_H.pkl.

  ENGUQ_149  augur_strategies/ENGUQ_1M_1_0.py, NQ_DEPLOY_PARAMS_149 — the RTH
             variant (api.paper.ENGUQ_149). QQQ trades RTH, so the ETH clock-
             scaled #226/ER25 config does NOT apply here; this is a deliberate
             choice, not an oversight (see module docstring further down).
             1m RTH, breakeven_R=1.5, + the 2% gap-skip deployment rule
             (GAP_PCT_RULE, mirrors tools/paper_forward.py). Gate:
             api.paper.ENGUQ_ER_GATE (logistic@0.55), model
             C:\\EdgeLog\\gate_models\\ENGUQ_ER_H.pkl — applied as a
             risk-reducer, WITH a flagged domain-shift caveat (see
             GATE FEASIBILITY below).

  NOISE_243  augur_strategies/NOISE_1_0.py, api.paper.NOISE_243_SBS_V90
             params. Registered in api/paper.py's own LEGS list as
             timeframe="5m", session="rth" (NOT 1m — the strategy's bar
             size/session is whatever api/paper.py says it is, and that is
             5m RTH). RAW / UNGATED, matching api/paper.py's own leg
             registration (NOISE_SBS_V90 carries no "gate" key there;
             NOISE_SBS_V90_H is a separate, explicitly-not-crowned forward
             test leg, not this one).

KNOB SCALING NQ -> QQQ (read every knob in all three strategy files before
writing this): a knob transfers UNCHANGED when it is expressed as a fraction/
multiple of something computed from the instrument's OWN price series (an
opening-range width, an ATR, a risk distance, a sigma/band-excursion) or as a
bar count / percentile / boolean. It needs POINT-RATIO rescaling only if it is
a flat absolute price distance in NQ points. Classification, argued from the
actual run_backtest() source (not from a knob's default value, which can look
point-like without being one):

  ORB_234 (ORB_3_6.py):
    or_bars, trail_bars                  bar counts                    unchanged
    trade_mode, close_confirm,
      flat_eod, skip_holidays            categorical / bool            unchanged
    stop_frac                            x opening-range width         unchanged
    breakout_buf                         x opening-range width         unchanged
                                            (reads like NQ points at 0.25 but
                                             the source multiplies it by `rng`,
                                             the OR width, not a flat constant)
    be_after_R, target_R, partial_exit_R x initial risk (R-multiple)   unchanged
    atr_filter                           x trailing median session range unchanged
    vpace_filter                         x trailing volume-prefix norm  unchanged
    -> NOTHING to rescale. Zero absolute-point knobs.

  ENGUQ_149 (ENGUQ_1M_1_0.py):
    tl_len, ema_len, atr_len             bar counts                    unchanged
    regime_len                           days (0 = off here)           unchanged
    buf_atr, min_brk                     x ATR                         unchanged
    vol_mult                             x 20-bar volume average       unchanged
    stop_mult, act_R, trail_frac,
      breakeven_R                        x initial risk (R-multiple)   unchanged
    -> NOTHING to rescale. Structural (non-knob) caveat: the strategy file
       hardcodes a minimum-risk floor `risk < max(0.25, 0.5): skip trade`
       as an absolute $0.50 price distance — not a parameter, so it is left
       exactly as written (the plugin file stays the single source of signal
       truth) but it is proportionally more binding on a ~$700 QQQ share
       (where a 48-bar swing low is often well under $0.50 away) than on a
       ~$25,000 NQ point. Flagged here; watch ENGUQ_149's trade count for
       under-signaling relative to its NQ frequency.

  NOISE_243 (NOISE_1_0.py / NOISE_1_1_SBS_V90.py):
    lookback, confirm_bars               bar counts                    unchanged
    band_mult_long, band_mult_short      x sigma (return-based)        unchanged
    stop_k                               x band-excursion IN THIS
                                            INSTRUMENT'S OWN price units
                                            (stop_mode="bandwidth")      unchanged
    daytype_lo, daytype_hi               percentile 0-1                unchanged
    vol_skip_pct                         percentile 0-100               unchanged
    exit_mode, side, window,
      flat_eod, skip_holidays,
      daytype_mode, stop_mode            categorical / bool             unchanged
    -> NOTHING to rescale.

  CONCLUSION: across all three legs, every numeric knob is already relative
  to the instrument's own price/volume/volatility series. No NQ/QQQ price
  ratio is applied anywhere in this file. (For the record, latest NQ close in
  C:\\EdgeLog\\ohlc\\NQ_1m.csv is ~29,588 vs QQQ ~$700 at the time this was
  written — a ~42:1 ratio — kept here only as a reference figure, never used
  as a multiplier.)

GATE FEASIBILITY
  augur_engine.ml_gate.entry_features_causal produces 12 features, and EVERY
  one is scale-free by construction: mom_5/mom_20/dist_pdh_atr/dist_pdl_atr/
  dist_pdc_atr are ATR-normalised distances, atr_norm/atr_ratio/range_pos/
  trend_20 are ratios or a correlation coefficient, touch_count is a bar
  count, tod_sin/tod_cos/dow are clock features. None depend on the
  instrument's absolute price level, so BOTH pretrained gates are applied in
  full — mirroring api/gate_live.py's decide(): predict_proba, threshold
  cut, and for hybrid mode a size multiplier
  w = clip(1 + 4*(prob-0.50), 0.25, 3.0) / size_norm. The book-level
  `recycle_factor` is deliberately NOT applied — it exists to re-spend
  capital a multi-leg LIVE book freed up elsewhere and has no meaning for a
  single standalone QQQ paper leg.

  ORB_H.pkl was trained on the exact strategy+session this tool runs
  (ORB_3_6_C2.py, RTH 5m) — a clean transfer, applied with no caveat beyond
  the instrument change itself.

  ENGUQ_ER_H.pkl was trained on ENGUQ_1M_ETH_ER25_1_0.py over the 24-HOUR ETH
  tape (see api/paper.py ENGUQ_ER_GATE / LEGS). Its tod_sin/tod_cos clock
  features therefore saw a full 24h cycle in training, but THIS leg (RTH
  #149, per the task's explicit instruction) only ever produces rows inside
  09:30-16:00 ET — a narrow arc of that cycle — and the underlying strategy
  and session are also different from what the model was fit on. The gate is
  still applied (its features remain well-formed and in-range on RTH data,
  and skipping a working artifact on a hunch would be its own unjustified
  judgment call) but this is a genuine domain-shift caveat: read ENGUQ_149's
  gated numbers with materially more skepticism than ORB's, and treat this
  leg's gate as exploratory, not evidence-backed, until it accumulates its
  own forward record.

  NOISE_243 carries no gate at all, matching its RAW registration in
  api/paper.py.

ECONOMICS
  Shares, not futures contracts/points. NOTIONAL_PER_LEG dollars / entry
  price -> shares (floored, >=0). Commission $0. Slippage $0.01/share per
  SIDE (entry AND exit, i.e. $0.02/share round trip).
    pnl_usd = pnl_price_units * shares - 0.02 * shares

DATA
  yfinance QQQ, prepost=False (RTH only, matches every leg's session=rth).
  1m bars: yfinance only serves ~30 days of history and ~7 days per single
  request, so the 1m fetch is chunked into <=7-day windows and stitched.
  5m bars: yfinance serves ~60 days in one request. Bars are cached to
  C:\\EdgeLog\\ohlc\\QQQ_1m.csv / QQQ_5m.csv in the SAME schema as the NQ
  masters this repo already uses (`time` = unix epoch SECONDS, UTC) and
  refreshed incrementally — merged with whatever is already cached, deduped
  on `time`, so a --sync only ever pays for the fresh tail. US/Eastern is
  used everywhere internally for RTH filtering and day_id session
  boundaries, matching augur_engine/data.py's load_master_arrays convention.

CLI
  python tools/qqq_paper.py --sync     refresh data, replay all available
                                        history, write blotter.csv + state.json
  python tools/qqq_paper.py --status   print current state + last 5 trades
                                        per leg (no network / no data pull)

Exit cleanly (message on stderr, exit code 1) when yfinance returns nothing
usable (market data unavailable / rate-limited / holiday with zero bars).
"""
import argparse
import datetime as _dt
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.engine import run_backtest as engine_run_backtest         # noqa: E402
from augur_engine.ml_gate import entry_features_causal                     # noqa: E402
from api.paper import (ORB_234, ORB_GATE, ENGUQ_149, ENGUQ_ER_GATE,        # noqa: E402
                       NOISE_243_SBS_V90)

# ── Config ───────────────────────────────────────────────────────────────────
TICKER = "QQQ"
NOTIONAL_PER_LEG = 100_000.0     # fixed notional per leg; shares = floor(notional/entry_px)
SLIPPAGE_PER_SHARE = 0.01        # $/share PER SIDE (entry and exit each pay this)
COMMISSION_PER_SHARE = 0.0

# The date (ET) the Webull paper forward test actually began. Every replayed
# session BEFORE this date is a REPLAY: the engine re-runs each leg over ~30-60
# days of Yahoo history so the owner can see how the configs would have done —
# nothing was watched happen and nothing was ever going to be an order. Every
# session ON OR AFTER this date is the live forward test: rows the owner set
# out to place in Webull paper as they occur. Owner asked (2026-09-01) "why
# does ORB have trades, we set this up a day or two ago" — the blotter mixing
# the two looked like real fills that predated the setup. LIVE_FROM makes the
# boundary a fact carried in the data (state.json + the Firestore doc), not a
# hardcoded count anywhere downstream.
LIVE_FROM = "2026-09-02"

CACHE_DIR = r"C:\EdgeLog\ohlc"
OUT_DIR = r"C:\EdgeLog\qqq_paper"
BLOTTER_PATH = os.path.join(OUT_DIR, "blotter.csv")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
GATE_DIR = r"C:\EdgeLog\gate_models"

# ENGUQ deployment rule (mirrors tools/paper_forward.py GAP_PCT_RULE): skip
# entries on a session that opened >2% away (either direction) from the prior
# RTH close.
GAP_PCT_RULE = 0.02

TZ = "US/Eastern"
RTH_OPEN = _dt.time(9, 30)
RTH_CLOSE = _dt.time(16, 0)

LEGS = {
    "ORB_234": {
        "strategy": "ORB_3_6_C2.py",
        "timeframe": "5m",
        "params": dict(ORB_234),
        "gate": dict(ORB_GATE, pkl="ORB_H.pkl"),
        "gap_skip": False,
    },
    "ENGUQ_149": {
        "strategy": "ENGUQ_1M_1_0.py",
        "timeframe": "1m",
        "params": dict(ENGUQ_149),
        "gate": dict(ENGUQ_ER_GATE, pkl="ENGUQ_ER_H.pkl"),
        "gap_skip": True,
    },
    "NOISE_243": {
        "strategy": "NOISE_1_0.py",
        "timeframe": "5m",
        "params": dict(NOISE_243_SBS_V90),
        "gate": None,
        "gap_skip": False,
    },
}


# ── Data: fetch + cache ───────────────────────────────────────────────────────
def _cache_path(timeframe):
    return os.path.join(CACHE_DIR, f"QQQ_{timeframe}.csv")


def _fetch_yf(timeframe):
    """Pull fresh QQQ bars from yfinance, RTH only. 1m is chunked into <=7-day
    windows (yfinance's per-request cap) covering the ~30 days it retains;
    5m is pulled in one 60-day request. Returns a DataFrame indexed by a
    tz-aware (US/Eastern) DatetimeIndex with Open/High/Low/Close/Volume, or
    an empty DataFrame if yfinance has nothing (network issue, rate limit,
    or genuinely no data)."""
    import yfinance as yf
    tkr = yf.Ticker(TICKER)
    if timeframe == "1m":
        end = pd.Timestamp.now(tz=TZ)
        start_floor = end - pd.Timedelta(days=29)
        frames = []
        cur_end = end
        while cur_end > start_floor:
            cur_start = max(start_floor, cur_end - pd.Timedelta(days=7))
            try:
                df = tkr.history(start=cur_start, end=cur_end, interval="1m",
                                 prepost=False, auto_adjust=False)
            except Exception as e:
                print(f"  [warn] yfinance 1m chunk {cur_start.date()}..{cur_end.date()} "
                     f"failed: {e}", file=sys.stderr)
                df = pd.DataFrame()
            if len(df):
                frames.append(df)
            cur_end = cur_start
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames)
        out = out[~out.index.duplicated(keep="last")].sort_index()
        return out
    elif timeframe == "5m":
        try:
            df = tkr.history(period="60d", interval="5m", prepost=False, auto_adjust=False)
        except Exception as e:
            print(f"  [warn] yfinance 5m fetch failed: {e}", file=sys.stderr)
            df = pd.DataFrame()
        return df
    else:
        raise ValueError(timeframe)


def _to_epoch_frame(df):
    if df is None or not len(df):
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(TZ)
    epoch = idx.tz_convert("UTC").astype("int64") // 10 ** 9
    return pd.DataFrame({
        "time": epoch.astype("int64"),
        "open": df["Open"].astype(float).values,
        "high": df["High"].astype(float).values,
        "low": df["Low"].astype(float).values,
        "close": df["Close"].astype(float).values,
        "volume": df["Volume"].astype(float).values,
    })


def sync_bars(timeframe):
    """Fetch fresh bars, merge into the on-disk cache (dedupe on `time`,
    newest wins), save, and return the merged epoch-schema DataFrame."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(timeframe)
    old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(
        columns=["time", "open", "high", "low", "close", "volume"])
    fresh_df = _fetch_yf(timeframe)
    fresh = _to_epoch_frame(fresh_df)
    print(f"  QQQ {timeframe}: fetched {len(fresh)} fresh bars from yfinance "
         f"({fresh_df.index.min()}..{fresh_df.index.max()})" if len(fresh)
         else f"  QQQ {timeframe}: fetched 0 fresh bars from yfinance")
    merged = pd.concat([old, fresh], ignore_index=True)
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time")
    merged.to_csv(path, index=False)
    print(f"  QQQ {timeframe}: cache now {len(merged)} bars -> {path}")
    return merged


def load_cached_bars(timeframe):
    path = _cache_path(timeframe)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


# ── Arrays (same shape as augur_engine.data.load_master_arrays) ───────────────
def build_arrays(epoch_df):
    """epoch_df: DataFrame with time(unix s, UTC)/open/high/low/close/volume ->
    dict(open,high,low,close,volume,day_id,index) filtered to RTH, US/Eastern,
    matching augur_engine.data.load_master_arrays' shape exactly so every
    strategy plugin and entry_features_causal can be handed this unchanged."""
    if epoch_df is None or not len(epoch_df):
        return None
    dt_idx = pd.to_datetime(epoch_df["time"], unit="s", utc=True).dt.tz_convert(TZ)
    df = epoch_df.copy()
    df.index = dt_idx
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    t = df.index.time
    mask = (t >= RTH_OPEN) & (t < RTH_CLOSE) & (df.index.dayofweek < 5)
    df = df[mask]
    if not len(df):
        return None
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    return {
        "open": df["open"].to_numpy(dtype=float),
        "high": df["high"].to_numpy(dtype=float),
        "low": df["low"].to_numpy(dtype=float),
        "close": df["close"].to_numpy(dtype=float),
        "volume": df["volume"].to_numpy(dtype=float),
        "day_id": day_id,
        "index": df.index,
    }


# ── Gap-skip (ENGUQ deployment rule) ──────────────────────────────────────────
def session_gap_flags(arrays):
    """day_id -> is_gap (RTH open vs prior RTH close, |%| > GAP_PCT_RULE)."""
    day_id, opens, closes = arrays["day_id"], arrays["open"], arrays["close"]
    n = len(day_id)
    sessions = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        sessions.append((a, b))
        a = b
    out = {}
    prev_close = None
    for (a, b) in sessions:
        did = int(day_id[a])
        gap_pct = None
        if prev_close is not None and prev_close != 0:
            gap_pct = (float(opens[a]) - prev_close) / prev_close
        out[did] = dict(gap_pct=gap_pct,
                        is_gap=bool(gap_pct is not None and abs(gap_pct) > GAP_PCT_RULE))
        prev_close = float(closes[b - 1])
    return out


# ── ML gate ────────────────────────────────────────────────────────────────────
def load_gate_artifact(pkl_name):
    import joblib
    path = os.path.join(GATE_DIR, pkl_name)
    if not os.path.exists(path):
        return None, f"artifact not found: {path}"
    try:
        art = joblib.load(path)
    except Exception as e:
        return None, f"failed to load {path}: {e}"
    return art, None


def score_gate(art, feat_row, threshold, mode):
    """Returns (take, size_mult, prob)."""
    prob = float(art["pipe"].predict_proba(feat_row.reshape(1, -1))[0, 1])
    mode = str(mode or "cut").lower()
    take = True if mode == "tilt" else not (prob < threshold)
    if mode == "hybrid" and take:
        w = float(np.clip(1.0 + 4.0 * (prob - 0.50), 0.25, 3.0))
        size_mult = float(min(w / float(art.get("size_norm") or 1.0), 3.0))
    else:
        size_mult = 1.0
    return take, size_mult, prob


# ── Strategy execution + economics ────────────────────────────────────────────
def run_leg(key, cfg, arrays):
    """Runs the plugin's own run_backtest via the shared engine wrapper (the
    strategy plugin file remains the single source of signal truth), then
    applies gap-skip / ML gate / share economics on top of its raw trade
    list. Returns (rows, meta) — rows is a list of blotter dicts, meta has
    diagnostic info for --status / troubleshooting."""
    res = engine_run_backtest(cfg["strategy"], arrays=arrays, params=cfg["params"],
                              cost_pts=0.0, return_trades=True)
    meta = {"raw_trades": 0, "gap_skipped": 0, "gate_skipped": 0, "gate_note": None,
           "still_open": False}
    if not res or not res.get("trades"):
        return [], meta
    trades = sorted(res["trades"], key=lambda t: t[0])
    meta["raw_trades"] = len(trades)
    n_bars = len(arrays["close"])

    gaps = session_gap_flags(arrays) if cfg["gap_skip"] else None

    gate_art = None
    gate_cfg = cfg.get("gate")
    F = names = None
    if gate_cfg:
        gate_art, err = load_gate_artifact(gate_cfg["pkl"])
        if err:
            meta["gate_note"] = f"GATE UNAVAILABLE ({err}) — running leg UNGATED"
            print(f"  [warn] {key}: {meta['gate_note']}", file=sys.stderr)
            gate_art = None
        else:
            F, names = entry_features_causal(arrays)
            if list(names) != list(gate_art.get("feature_names") or names):
                meta["gate_note"] = "feature names changed vs artifact — running UNGATED"
                print(f"  [warn] {key}: {meta['gate_note']}", file=sys.stderr)
                gate_art = None

    rows = []
    idx = arrays["index"]
    day_id = arrays["day_id"]
    for (entry_bar, exit_bar, pnl_pts, side, entry_px) in trades:
        entry_bar = int(entry_bar); exit_bar = int(exit_bar)
        if gaps is not None:
            did = int(day_id[entry_bar])
            if gaps.get(did, {}).get("is_gap"):
                meta["gap_skipped"] += 1
                continue

        prob = None
        gate_take = True
        size_mult = 1.0
        if gate_art is not None:
            row = F[min(entry_bar, len(F) - 1)]
            gate_take, size_mult, prob = score_gate(
                gate_art, row, gate_cfg["threshold"], gate_cfg["mode"])
            if not gate_take:
                meta["gate_skipped"] += 1
                continue

        entry_px = float(entry_px)
        # pnl_pts is already signed correctly by the strategy (long: exit-entry,
        # short: entry-exit), so exit_px = entry_px + pnl_pts*side recovers it exactly.
        exit_px = entry_px + pnl_pts * side
        shares = int(math.floor((NOTIONAL_PER_LEG * size_mult) / entry_px)) if entry_px > 0 else 0
        shares = max(shares, 0)
        gross = pnl_pts * shares
        costs = shares * (2 * SLIPPAGE_PER_SHARE + 2 * COMMISSION_PER_SHARE)
        pnl_usd = gross - costs

        still_open_at_end = (exit_bar >= n_bars - 1)
        if still_open_at_end:
            meta["still_open"] = True

        rows.append({
            "leg": key,
            "entry_time": idx[entry_bar].isoformat(),
            "exit_time": idx[min(exit_bar, n_bars - 1)].isoformat(),
            "side": "long" if side > 0 else "short",
            "shares": shares,
            "entry_px": round(entry_px, 4),
            "exit_px": round(exit_px, 4),
            "pnl_per_share": round(pnl_pts, 4),
            "gross_pnl_usd": round(gross, 2),
            "costs_usd": round(costs, 2),
            "pnl_usd": round(pnl_usd, 2),
            "gate_prob": round(prob, 4) if prob is not None else "",
            "gate_size_mult": round(size_mult, 3) if gate_art is not None else "",
            "still_open_at_data_end": still_open_at_end,
        })
    return rows, meta


# ── State (current position / today's levels / gate readiness) ────────────────
def leg_state(key, cfg, arrays, rows, meta):
    idx = arrays["index"]
    last_ts = idx[-1].isoformat() if len(idx) else None
    st = {
        "asof": last_ts,
        "bars_loaded": int(len(idx)),
        "raw_trades": meta["raw_trades"],
        "gap_skipped": meta["gap_skipped"],
        "gate_skipped": meta["gate_skipped"],
        "gate_note": meta["gate_note"],
        "closed_trades": len(rows),
        "position": "flat",
    }
    if rows:
        last = rows[-1]
        if last["still_open_at_data_end"]:
            st["position"] = "open (marked at last available bar — data-end fallback, not a real fill)"
            st["open_trade"] = {k: last[k] for k in
                                ("entry_time", "side", "shares", "entry_px")}
        else:
            st["position"] = "flat"

    # today's ORB levels, if the opening range has completed
    if key == "ORB_234" and len(idx):
        today = idx[-1].date()
        day_id = arrays["day_id"]
        today_mask = np.array([d.date() == today for d in idx])
        if today_mask.any():
            a = int(np.argmax(today_mask))
            b = int(len(idx) - 1)
            or_bars = int(cfg["params"]["or_bars"])
            n_today = b - a + 1
            if n_today > or_bars:
                h = arrays["high"][a:a + or_bars]; l = arrays["low"][a:a + or_bars]
                o0 = arrays["open"][a]; c_or = arrays["close"][a + or_bars - 1]
                or_hi = float(h.max()); or_lo = float(l.min()); rng = or_hi - or_lo
                buf = cfg["params"]["breakout_buf"] * rng
                or_dir = 1 if c_or >= o0 else -1
                st["today_orb"] = {
                    "session_date": str(today), "or_high": round(or_hi, 4),
                    "or_low": round(or_lo, 4), "range_width": round(rng, 4),
                    "breakout_up_level": round(or_hi + buf, 4),
                    "breakout_down_level": round(or_lo - buf, 4),
                    "first_candle_dir": "long" if or_dir > 0 else "short",
                    "note": "trade_mode=First-candle dir: only the breakout matching "
                            "first_candle_dir is eligible",
                }
            else:
                st["today_orb"] = {"session_date": str(today),
                                   "note": f"opening range not complete yet "
                                           f"({n_today}/{or_bars} bars)"}

    # gate readiness: score the gate on the most recent completed bar
    gate_cfg = cfg.get("gate")
    if gate_cfg and not meta["gate_note"]:
        art, err = load_gate_artifact(gate_cfg["pkl"])
        if art is not None:
            F, names = entry_features_causal(arrays)
            take, size_mult, prob = score_gate(art, F[-1], gate_cfg["threshold"], gate_cfg["mode"])
            st["gate"] = {"model": gate_cfg["model"], "threshold": gate_cfg["threshold"],
                         "last_bar_prob": round(prob, 4),
                         "would_allow_next_entry": take,
                         "size_mult_if_taken": round(size_mult, 3)}
    return st


# ── Blotter I/O ────────────────────────────────────────────────────────────────
BLOTTER_COLS = ["leg", "entry_time", "exit_time", "side", "shares", "entry_px", "exit_px",
               "pnl_per_share", "gross_pnl_usd", "costs_usd", "pnl_usd", "gate_prob",
               "gate_size_mult", "still_open_at_data_end"]


def write_blotter(all_rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.DataFrame(all_rows, columns=BLOTTER_COLS)
    df = df.sort_values(["entry_time", "leg"])
    df.to_csv(BLOTTER_PATH, index=False)
    return df


def write_state(state):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ── CLI ────────────────────────────────────────────────────────────────────────
def cmd_sync():
    print(f"QQQ paper engine -- sync starting ({_dt.datetime.now().isoformat(timespec='seconds')})")
    tf_needed = sorted({cfg["timeframe"] for cfg in LEGS.values()})
    bars_by_tf = {}
    for tf in tf_needed:
        merged = sync_bars(tf)
        arrays = build_arrays(merged)
        if arrays is None or len(arrays["close"]) < 20:
            print(f"MARKET DATA UNAVAILABLE for QQQ {tf}: yfinance returned no usable RTH "
                 f"bars (market closed with an empty cache, holiday, or a data outage). "
                 f"Nothing to replay for legs on this timeframe.", file=sys.stderr)
            bars_by_tf[tf] = None
        else:
            bars_by_tf[tf] = arrays

    if all(v is None for v in bars_by_tf.values()):
        print("No QQQ intraday data available at all — exiting.", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    state = {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "notional_per_leg": NOTIONAL_PER_LEG,
            "slippage_per_share": SLIPPAGE_PER_SHARE,
            "live_from": LIVE_FROM,
            "legs": {}}
    for key, cfg in LEGS.items():
        arrays = bars_by_tf.get(cfg["timeframe"])
        if arrays is None:
            state["legs"][key] = {"error": f"no {cfg['timeframe']} data available"}
            print(f"{key}: SKIPPED (no {cfg['timeframe']} data)")
            continue
        rows, meta = run_leg(key, cfg, arrays)
        all_rows.extend(rows)
        st = leg_state(key, cfg, arrays, rows, meta)
        state["legs"][key] = st
        total_pnl = sum(r["pnl_usd"] for r in rows)
        gate_txt = f", gate skipped {meta['gate_skipped']}" if cfg["gate"] else ""
        gap_txt = f", gap-skipped {meta['gap_skipped']}" if cfg["gap_skip"] else ""
        print(f"{key}: {meta['raw_trades']} raw trades -> {len(rows)} kept{gap_txt}{gate_txt}, "
             f"total P&L ${total_pnl:,.2f}")
        if meta["raw_trades"] > 0 and len(rows) == 0:
            print(f"  [investigate] {key} produced signals but ZERO kept trades — "
                 f"check gap-skip/gate thresholds above.", file=sys.stderr)

    df = write_blotter(all_rows)
    write_state(state)
    print(f"\nWrote {len(df)} blotter rows -> {BLOTTER_PATH}")
    print(f"Wrote state -> {STATE_PATH}")


def cmd_status():
    if not os.path.exists(STATE_PATH):
        print("No state.json yet — run --sync first.", file=sys.stderr)
        sys.exit(1)
    with open(STATE_PATH) as f:
        state = json.load(f)
    blotter = pd.read_csv(BLOTTER_PATH) if os.path.exists(BLOTTER_PATH) else pd.DataFrame()

    print(f"QQQ paper engine -- status as of sync {state.get('generated_at')}")
    print(f"Notional/leg: ${state.get('notional_per_leg', 0):,.0f}   "
         f"Slippage: ${state.get('slippage_per_share', 0):.2f}/share/side\n")
    for key, st in state.get("legs", {}).items():
        print(f"-- {key} " + "-" * (60 - len(key)))
        if "error" in st:
            print(f"  ERROR: {st['error']}")
            continue
        print(f"  as of: {st.get('asof')}   bars loaded: {st.get('bars_loaded')}")
        print(f"  raw signals: {st.get('raw_trades')}   gap-skipped: {st.get('gap_skipped')}   "
             f"gate-skipped: {st.get('gate_skipped')}   closed trades: {st.get('closed_trades')}")
        if st.get("gate_note"):
            print(f"  GATE WARNING: {st['gate_note']}")
        print(f"  position: {st.get('position')}")
        if st.get("open_trade"):
            print(f"    open trade: {st['open_trade']}")
        if st.get("today_orb"):
            print(f"  today's ORB levels: {st['today_orb']}")
        if st.get("gate"):
            g = st["gate"]
            print(f"  gate ({g['model']}@{g['threshold']}): last-bar prob={g['last_bar_prob']}, "
                 f"would allow next entry={g['would_allow_next_entry']}, "
                 f"size mult={g['size_mult_if_taken']}")
        if len(blotter):
            leg_tr = blotter[blotter["leg"] == key].sort_values("entry_time")
            if len(leg_tr):
                total = leg_tr["pnl_usd"].sum()
                print(f"  total P&L over replay window: ${total:,.2f} ({len(leg_tr)} trades)")
                print("  last 5 trades:")
                for _, r in leg_tr.tail(5).iterrows():
                    print(f"    {r['entry_time']}  {r['side']:>5}  {int(r['shares'])}sh "
                         f"@ {r['entry_px']:.2f} -> {r['exit_px']:.2f}   "
                         f"P&L ${r['pnl_usd']:,.2f}"
                         + (f"   gate_p={r['gate_prob']}" if r['gate_prob'] not in ("", None) and not pd.isna(r['gate_prob']) else ""))
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", action="store_true", help="refresh data + replay + write blotter/state")
    ap.add_argument("--status", action="store_true", help="print current state + last trades")
    args = ap.parse_args()
    if not args.sync and not args.status:
        ap.print_help()
        sys.exit(1)
    if args.sync:
        cmd_sync()
    if args.status:
        cmd_status()


if __name__ == "__main__":
    main()

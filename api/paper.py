"""Shadow paper trading — the always-on runner re-runs the two crowned strategies on
each day's fresh intraday data and logs the trades the engine WOULD have taken.

Nothing here ever touches real money or a broker; this is a pure "would-have-traded"
shadow log written to Firestore (users/{uid}/paper_trades + users/{uid}/paper_reports)
plus a per-uid state doc (users/{uid}/meta/paper_state) that gates the once-a-day run.

Data flow per leg:
  1. Load the leg's master CSV (augur_uploads/*.csv) via find_master/load_master_arrays,
     sliced from ~150 calendar days before "today" (warm-up headroom for ema_len=390 on
     1m ENGU-Q) up to whatever the master already has.
  2. Read the NinjaTrader AddOn's live 10s CSV (C:\\EdgeLog\\ohlc_addon\\NQ_10s.csv,
     fallback C:\\EdgeLog\\ohlc\\NQ_10s.csv), resample to the leg's timeframe, filter to
     RTH (09:30-16:00 America/New_York), and keep only bars strictly AFTER the master's
     last bar — i.e. only the fresh tail the master doesn't have yet.
  3. Append that tail to the loaded arrays IN MEMORY (the master file on disk is never
     touched) and hand the combined arrays to run_backtest(..., return_trades=True).
  4. Trades with an entry date on/after PAPER_START are the "paper" trades; anything
     from the warm-up history before that is discarded.

Everything here is exception-proof by design (try/except around every stage) — a data
hiccup must never take down the runner's watch loop.
"""
import os
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from .util import json_safe

# ── crowned legs ─────────────────────────────────────────────────────────────────
# First trading day shadow trades are logged for. Anything with an entry before this
# (e.g. the warm-up history the engine needs to even start emitting signals) is dropped.
PAPER_START = "2026-08-11"

# NQ contract multiplier ($/point) — same value augur_engine/book.py's _MULT table and
# tools/t5_runboard.py / tools/book_smoke.py use for NQ.
_NQ_MULT = 20.0
# NQ round-trip cost in POINTS — same value tools/t5_runboard.py's leg_trades() and
# tools/book_smoke.py use for both the ORB and ENGU-Q NQ legs (commission+slippage,
# see ORB.md: "cost_pts = 0.533 (NQ, mult 20)").
_NQ_COST_PTS = 0.533

# ORB leg params: ORB_125 is defined inline in tools/t5_runboard.py (line ~26), a
# top-level research SCRIPT that runs full 16yr backtests as a side effect of being
# imported — not safe to import from. Copied here verbatim instead (source: tools/
# t5_runboard.py ORB_125) MINUS partial_exit_R/trail_bars: t5_runboard.py actually
# runs this dict against ORB_3_1.py (the richer partial/trailing-stop version), but
# this leg is pinned to ORB_3_0.py — the deliberately-stripped "5 knob" deployable
# (see that file's own docstring) whose run_backtest() has no partial_exit_R or
# trail_bars parameter at all (TypeError if passed); the other knobs are identical.
ORB_125 = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
               breakout_buf=0.0, target_R=0.0, flat_eod=True)

# ENGU-Q leg params: NQ_DEPLOY_PARAMS_149 is a clean module-level constant in
# augur_strategies/ENGUQ_1M_1_0.py — import it directly.
from augur_strategies import ENGUQ_1M_1_0 as _enguq  # noqa: E402
ENGUQ_149 = dict(_enguq.NQ_DEPLOY_PARAMS_149)

# NOISE leg params: the validated config (see NOISE_1_0.py docstring) + the
# researched bandwidth stop. NOISE is execution-CLEAN (close signal -> next-open
# fill), so unlike ORB its shadow numbers are live-achievable.
NOISE_FROZEN = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                    exit_mode="vwap", side="Both", window="all_day",
                    flat_eod=True, skip_holidays=False,
                    stop_mode="bandwidth", stop_k=1.0)

# PROVENANCE — where each leg's config actually came from (owner 2026-08-15: "i dont
# know which config or past run it got it from"). This is the AUTHORITATIVE record; it
# is written into every daily report's legs block so the board can show it, and it is
# what tools/nt_config_reconcile.py's mapping is checked against.
#
# Keep it honest: `run` is the Past-Runs number the params came from, or None when the
# config was never crowned by a run (NOISE's stop came out of a hand-run sweep, not an
# auto-validate). `caveat` is the one thing you would want to know before trusting the
# leg's numbers -- leave it None rather than inventing reassurance.
LEG_SOURCE = {
    "ORB": {
        "run": 125, "run_label": "#125 (ORB-family)", "strategy_file": "ORB_3_0.py",
        "picked": "2026-07",
        "note": "The NO-TRAIL ORB_3_0 cut of run #125, not #125's crowned variant "
                "(the crown is ORB_3_1 with trail_bars=5). Both are carried in the repo; "
                "api/paper.py and tools/t5_runboard.py both use this one.",
        "caveat": "Run #125's volume filter is LOOK-AHEAD (2026-08-11 audit): it gates an "
                  "intrabar stop-entry on the breakout bar's FINISHED volume. These shadow "
                  "numbers are NOT live-achievable. The live candidate is the NT-side ORB V2.",
    },
    "ENGUQ": {
        "run": 149, "run_label": "#149 (ENGU-Q)", "strategy_file": "ENGUQ_1M_1_0.py",
        "picked": "2026-07-14",
        "note": "NQ_DEPLOY_PARAMS_149 imported directly from the strategy file, plus the "
                "later breakeven_R=1.5 addition. Pine port reconciled against TradingView "
                "2026-07-14 (84.5% of matched trades exact).",
        "caveat": None,
    },
    "NOISE": {
        "run": None, "run_label": "no crowned run", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-08",
        "note": "Round-12 frozen defaults (lookback 14, symmetric 1.5 bands, vwap exit) plus "
                "the bandwidth stop k=1.0 that won the 25-variant exit sweep. Assembled by "
                "hand from research, never crowned by an auto-validate run.",
        "caveat": "Auto-validate #225 (NOISE-6) later crowned a DIFFERENT config -- lookback 44, "
                  "asymmetric 0.75/1.5 bands, stop_k 1.75 -- on a fresh 18-month lockbox. This "
                  "leg is not that config. See NOISE.md.",
    },
}

PAPER_LEGS = [
    # ORB: the engine's touch-entry volume filter is LOOK-AHEAD (2026-08-11 audit,
    # see PAPER_TRADING.md) — these shadow numbers are NOT live-achievable. Kept as
    # a flagged reference line; the live candidate is the NT-side ORB V2 chase.
    {"key": "ORB", "strategy": "ORB_3_0.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": ORB_125, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "flags": ["lookahead-engine"], "source": LEG_SOURCE["ORB"]},
    {"key": "ENGUQ", "strategy": "ENGUQ_1M_1_0.py", "instrument": "NQ", "timeframe": "1m",
     "session": "rth", "params": ENGUQ_149, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "source": LEG_SOURCE["ENGUQ"]},
    {"key": "NOISE", "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": NOISE_FROZEN, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "source": LEG_SOURCE["NOISE"]},
]

# ── Layer 1: the NT demo account whose fills we mirror into the daily report ────
PAPER_LIVE_ACCOUNT = "DEMO7240108"

# Are the NinjaScript strategies actually enabled on charts? While this is False the
# Layer 3 reconcile does not treat "the engine signalled and the demo did not trade" as
# a divergence, because that is exactly what is expected.
#
# TRUE since 2026-08-13. PAPER_TRADING.md said the strategies were not enabled; the fills
# say otherwise. DEMO7240108 has been trading NQ on exact 5-minute boundaries with zero
# commission and sequential order ids since 2026-08-11 - machine-generated, on the 5m
# chart, which is NOISE. Nobody updated the doc when the chart was enabled, which is
# precisely the kind of drift this reconcile exists to catch.
NT_STRATEGIES_ENABLED = True
_FILLS_CSV = r"C:\EdgeLog\fills.csv"
_INST_MULT = {"NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0}

# ── fresh 10s tick source ────────────────────────────────────────────────────────
_ADDON_10S = r"C:\EdgeLog\ohlc_addon\NQ_10s.csv"
_FALLBACK_10S = r"C:\EdgeLog\ohlc\NQ_10s.csv"

_WARMUP_DAYS = 150          # calendar days before "today" (ema_len=390 on 1m headroom)
_STALE_MINUTES = 30         # 10s file is "stale" if its last bar is this far before close
_CHECK_INTERVAL_S = 60.0    # internal throttle for maybe_run_eod


def _log(msg):
    print(f"[paper] {msg}")


# ── fresh-tail builder ───────────────────────────────────────────────────────────
def _ticks_path():
    return _ADDON_10S if os.path.exists(_ADDON_10S) else _FALLBACK_10S


def _load_fresh_ticks():
    """Read the live 10s OHLC+delta CSV. Returns (DataFrame|None, path)."""
    path = _ticks_path()
    if not os.path.exists(path):
        return None, path
    try:
        df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close", "volume"])
    except Exception as e:
        _log(f"failed reading {path}: {type(e).__name__}: {e}")
        return None, path
    if df.empty:
        return None, path
    df["time"] = df["time"].astype("int64")
    return df, path


def _resample(df, tf_minutes):
    """10s rows -> OHLCV bars of tf_minutes, bar time = bar-start unix. Bars with no
    rows are simply absent (groupby only emits buckets that have data)."""
    sec = int(tf_minutes) * 60
    key = (df["time"] // sec) * sec
    g = df.groupby(key, sort=True)
    out = pd.DataFrame({
        "time": g["open"].first().index.values,
        "open": g["open"].first().values,
        "high": g["high"].max().values,
        "low": g["low"].min().values,
        "close": g["close"].last().values,
        "volume": g["volume"].sum().values,
    })
    return out


def _filter_rth(bars):
    """Keep only bars whose bar-start falls in 09:30-16:00 America/New_York.
    Returns (filtered bars DataFrame, tz-aware US/Eastern Timestamp Series aligned to it)."""
    et = pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    tod = et.dt.hour * 60 + et.dt.minute
    mask = (tod >= 9 * 60 + 30) & (tod < 16 * 60)
    return bars[mask].reset_index(drop=True), et[mask].reset_index(drop=True)


def _append_fresh(arrays, bars):
    """Append fresh bars (DataFrame: time/open/high/low/close/volume) to a loaded
    master `arrays` dict, IN MEMORY ONLY. Returns (new arrays dict, n bars appended)."""
    if bars is None or bars.empty:
        return arrays, 0
    new_index = pd.DatetimeIndex(
        pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert("US/Eastern"))
    combined_index = arrays["index"].append(new_index)
    o = np.concatenate([np.asarray(arrays["open"], float), bars["open"].values.astype(float)])
    h = np.concatenate([np.asarray(arrays["high"], float), bars["high"].values.astype(float)])
    l = np.concatenate([np.asarray(arrays["low"], float), bars["low"].values.astype(float)])
    c = np.concatenate([np.asarray(arrays["close"], float), bars["close"].values.astype(float)])
    v_old = arrays.get("volume")
    if v_old is not None:
        v = np.concatenate([np.asarray(v_old, float), bars["volume"].values.astype(float)])
    else:
        v = None
    day_id = pd.factorize(pd.Series(combined_index).dt.date)[0].astype("int64")
    out = dict(arrays)
    out.update(open=o, high=h, low=l, close=c, volume=v, day_id=day_id, index=combined_index)
    return out, len(bars)


# ── trade conversion (mirrors augur_engine/reconcile.py edgelog_blotter) ─────────
def _extract_trades(leg, arrays, res):
    """raw trade tuples (entry_bar, exit_bar, pnl_pts, side, entry_px) -> plain dicts."""
    mult = float(leg.get("mult") or 20.0)
    idx = arrays["index"]
    O = arrays["open"]
    out = []
    for t in ((res or {}).get("trades") or []):
        eb, xb, pnl_pts = int(t[0]), int(t[1]), float(t[2])
        side = int(t[3]) if len(t) >= 4 else 0
        entry_px = float(t[4]) if len(t) >= 5 else float(O[eb])
        exit_px = (entry_px + side * pnl_pts) if side else None
        entry_dt = pd.Timestamp(idx[eb])
        exit_dt = pd.Timestamp(idx[xb])
        out.append({
            "leg": leg["key"], "strategy": leg["strategy"], "side": side,
            "entry_dt": entry_dt, "exit_dt": exit_dt,
            "entry_px": entry_px, "exit_px": exit_px,
            "pnl_pts": pnl_pts, "pnl_usd": pnl_pts * mult,
        })
    return out


# ── per-leg shadow run ────────────────────────────────────────────────────────────
def run_shadow(leg, today):
    """Re-run one crowned leg on master + fresh-tail data. Never raises.

    today: a date (or anything pandas.Timestamp can parse) — the trading day this
    shadow run is being produced for; only used to size the warm-up window and the
    staleness check (today's 16:00 ET close).

    Returns {trades:[...], bars_appended:int, data_fresh_thru:int|None, warnings:[...]}.
    `trades` only includes trades whose entry date is >= PAPER_START.
    """
    warnings = []
    trades_out = []
    bars_appended = 0
    data_fresh_thru = None
    try:
        today_d = pd.Timestamp(today).date()

        master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
        if master is None:
            warnings.append(
                f"no master for {leg['instrument']} {leg['timeframe']} {leg.get('session')}")
            return {"trades": [], "bars_appended": 0, "data_fresh_thru": None,
                   "warnings": warnings}

        date_from = (pd.Timestamp(today_d) - pd.Timedelta(days=_WARMUP_DAYS)).strftime("%Y-%m-%d")
        arrays = load_master_arrays(master, date_from=date_from, date_to=None)

        ticks_df, ticks_path = _load_fresh_ticks()
        if ticks_df is None:
            warnings.append(f"10s data file missing/empty: {ticks_path}")
        else:
            last_tick_unix = int(ticks_df["time"].iloc[-1])
            data_fresh_thru = last_tick_unix
            close_et = pd.Timestamp(f"{today_d} 16:00:00", tz="US/Eastern")
            last_tick_et = pd.Timestamp(last_tick_unix, unit="s", tz="UTC").tz_convert("US/Eastern")
            if last_tick_et < close_et - pd.Timedelta(minutes=_STALE_MINUTES):
                warnings.append(
                    f"10s data looks stale: last bar {last_tick_et} "
                    f"(more than {_STALE_MINUTES}m before {close_et} close)")

            tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
            bars = _resample(ticks_df, tf_min)
            bars, bars_et = _filter_rth(bars)
            last_master_time = arrays["index"][-1] if len(arrays["index"]) else None
            if last_master_time is not None and len(bars):
                keep = (bars_et > last_master_time).values
                bars = bars[keep].reset_index(drop=True)
            if len(bars):
                arrays, bars_appended = _append_fresh(arrays, bars)

        if bars_appended == 0:
            warnings.append("zero fresh bars appended")

        res = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                           cost_pts=leg.get("cost_pts", 0.0), return_trades=True)
        trades = _extract_trades(leg, arrays, res)
        paper_start = pd.Timestamp(PAPER_START).date()
        trades_out = [t for t in trades if t["entry_dt"].date() >= paper_start]
    except Exception as e:
        msg = f"exception in run_shadow({leg.get('key')}): {type(e).__name__}: {e}"
        warnings.append(msg)
        _log(msg)

    return {"trades": trades_out, "bars_appended": bars_appended,
           "data_fresh_thru": data_fresh_thru, "warnings": warnings}


# ── Layer 1: today's demo-account fills, mirrored into the daily report ──────────
def collect_live_fills(target_date):
    """Read C:\\EdgeLog\\fills.csv and return the PAPER demo account's fills for
    target_date, plus a best-effort day-net. Attribution to individual strategies
    is deliberately NOT attempted here (fills carry no strategy name — that's the
    reconcile layer's job, by time+price). Never raises."""
    out = {"account": PAPER_LIVE_ACCOUNT, "n_fills": 0, "fills": [],
           "day_net_usd": None, "flat_eod": True, "warnings": []}
    try:
        if not os.path.exists(_FILLS_CSV):
            out["warnings"].append("fills.csv missing")
            return out
        date_s = target_date.isoformat()
        pos = {}      # instrument root -> signed qty
        cash = {}     # instrument root -> signed cash flow in points*qty*mult
        with open(_FILLS_CSV, encoding="utf-8-sig") as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 9 or parts[2] != PAPER_LIVE_ACCOUNT:
                    continue
                if not parts[1].startswith(date_s):
                    continue
                inst = parts[3]
                root = inst.split(" ")[0].upper()
                action = parts[4].upper()
                try:
                    qty = float(parts[5]); px = float(parts[6])
                except ValueError:
                    continue
                side = 1 if action.startswith("BUY") else -1
                mult = _INST_MULT.get(root, 1.0)
                pos[root] = pos.get(root, 0.0) + side * qty
                cash[root] = cash.get(root, 0.0) - side * qty * px * mult
                out["fills"].append({"time": parts[1], "instrument": inst,
                                     "action": action, "qty": qty, "price": px})
        out["n_fills"] = len(out["fills"])
        open_roots = [r for r, q in pos.items() if abs(q) > 1e-9]
        out["flat_eod"] = not open_roots
        if out["n_fills"]:
            if open_roots:
                out["warnings"].append(
                    "position still open in " + ",".join(open_roots)
                    + " - day net excludes it")
                out["day_net_usd"] = sum(v for r, v in cash.items() if r not in open_roots)
            else:
                out["day_net_usd"] = sum(cash.values())
    except Exception as e:
        out["warnings"].append(f"live-fills read failed: {type(e).__name__}: {e}")
    return out


# ── once-a-day EOD driver ─────────────────────────────────────────────────────────
_last_check_ts = 0.0


def _last_completed_trading_day(et_now, force=False):
    """The most recent trading day whose EOD (16:10 ET) has passed. With force=True,
    returns today's date regardless of time-of-day (manual/smoke-test trigger)."""
    d = et_now.date()
    if force:
        return d
    if et_now.weekday() < 5 and (et_now.hour, et_now.minute) >= (16, 10):
        candidate = d
    else:
        candidate = d - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _et_now():
    try:
        from zoneinfo import ZoneInfo
        return pd.Timestamp.now(tz=ZoneInfo("America/New_York"))
    except Exception:
        return pd.Timestamp.now(tz="US/Eastern")


def maybe_run_eod(q, *, force=False, dry_run=False):
    """Cheap, throttled, exception-proof hook for the runner's watch loop. Actually
    runs the shadow legs at most once per trading day, after 16:10 ET, skipping
    weekends — plus a startup catch-up if the last run is older than the most recent
    completed trading day. No-ops in well under 1ms outside its 60s check window."""
    global _last_check_ts
    now_wall = time.time()
    if not force and (now_wall - _last_check_ts) < _CHECK_INTERVAL_S:
        return None
    _last_check_ts = now_wall
    try:
        return _run_eod_check(q, force=force, dry_run=dry_run)
    except Exception as e:
        _log(f"maybe_run_eod error: {type(e).__name__}: {e}")
        return None


def _run_eod_check(q, *, force=False, dry_run=False):
    et_now = _et_now()
    # No weekday/time-of-day early return here: _last_completed_trading_day already
    # excludes today until 16:10 ET has passed, and the per-uid last_run_date guard
    # below makes the call a no-op when that day was run. This is what lets a Monday-
    # morning restart still catch up a Friday the PC was off for at Friday's close.
    target_date = _last_completed_trading_day(et_now, force=force)
    target_date_s = target_date.isoformat()

    reports = {}
    for uid in list(getattr(q, "allow", None) or []):
        try:
            already_ran = False
            if not force and not dry_run:
                state = _get_state(q.db, uid)
                last_run = (state or {}).get("last_run_date")
                if last_run and str(last_run) >= target_date_s:
                    already_ran = True
            if already_ran:
                continue

            report = _run_one_uid(q, uid, target_date, dry_run=dry_run)
            reports[uid] = report

            if not dry_run:
                _set_state(q.db, uid, {"last_run_date": target_date_s,
                                       "paper_start": PAPER_START})
        except Exception as e:
            _log(f"uid {uid} skipped: {type(e).__name__}: {e}")
    return {"date": target_date_s, "reports": reports}


def _get_state(db, uid):
    try:
        doc = db.collection("users").document(uid).collection("meta").document("paper_state").get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def _set_state(db, uid, patch):
    try:
        db.collection("users").document(uid).collection("meta").document("paper_state").set(
            patch, merge=True)
    except Exception as e:
        _log(f"state write failed for uid: {type(e).__name__}: {e}")


def _run_one_uid(q, uid, target_date, *, dry_run=False):
    """Run both legs for one uid, upsert trades + write the daily report doc.
    Returns the report dict (also written to Firestore unless dry_run)."""
    leg_reports = {}
    total_pnl = 0.0
    batch = None
    pending = 0
    firestore = None
    if not dry_run:
        from firebase_admin import firestore as _fs
        firestore = _fs
        batch = q.db.batch()

    for leg in PAPER_LEGS:
        r = run_shadow(leg, target_date)
        trade_ids = []
        todays_trades = []      # the trade dicts behind trade_ids, for Layer 3
        leg_pnl = 0.0
        for t in r["trades"]:
            entry_unix = int(t["entry_dt"].timestamp())
            exit_unix = int(t["exit_dt"].timestamp())
            doc_id = f"pt_{leg['key']}_{entry_unix}"
            # run_shadow re-scans the WHOLE window since PAPER_START every day, so this
            # loop sees every trade ever, not just today's. Two consequences, both handled
            # here (bug found 2026-08-12: ORB's single Aug-11 trade was being re-reported
            # as a fresh signal each day, and every trade carried the RUN's date, which
            # collapsed the cumulative curve onto one x-point):
            #   • the trade doc is stamped with the TRADE's own date (upsert is idempotent
            #     on doc_id, so re-scanning simply refreshes it), and
            #   • the daily report counts only trades that actually happened THAT day.
            t_date = t["entry_dt"].date()
            is_today = (t_date == target_date)
            if is_today:
                trade_ids.append(doc_id)
                todays_trades.append({
                    "side": t["side"], "entryIso": t["entry_dt"].isoformat(),
                    "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                    "pnl_usd": t["pnl_usd"],
                })
                leg_pnl += t["pnl_usd"]
            if not dry_run:
                doc = json_safe({
                    "leg": leg["key"], "strategy": leg["strategy"],
                    "side": t["side"], "entryTime": entry_unix, "exitTime": exit_unix,
                    "entryIso": t["entry_dt"].isoformat(), "exitIso": t["exit_dt"].isoformat(),
                    "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                    "pnl_pts": t["pnl_pts"], "pnl_usd": t["pnl_usd"],
                    "layer": "shadow", "run_date": t_date.isoformat(),
                    "flags": leg.get("flags") or [],
                })
                doc["createdAt"] = firestore.SERVER_TIMESTAMP
                batch.set(q.db.collection("users").document(uid)
                         .collection("paper_trades").document(doc_id), doc, merge=True)
                pending += 1
                if pending >= 400:
                    batch.commit(); batch = q.db.batch(); pending = 0

        leg_reports[leg["key"]] = {
            # n_signals / pnl_usd are THIS DAY only; n_since_start is the running total
            # so the cumulative view is still available without conflating the two.
            "n_signals": len(trade_ids), "n_since_start": len(r["trades"]),
            "trade_ids": trade_ids, "pnl_usd": leg_pnl,
            # Layer 3 reads this and strips it before the doc is written - it is the
            # same data as trade_ids, just resolved, and Firestore does not need both.
            "_trades": todays_trades,
            "bars_appended": r["bars_appended"], "data_fresh_thru": r["data_fresh_thru"],
            "warnings": r["warnings"], "flags": leg.get("flags") or [],
            # Provenance travels WITH the numbers (owner 2026-08-15: "i dont know which
            # config or past run it got it from"). Writing both the source block and the
            # exact params means a report is self-describing forever -- you can read an
            # old report and know precisely which config produced it, even after this
            # file has moved on to a different one.
            "source": leg.get("source") or {},
            "params": dict(leg.get("params") or {}),
            "strategy_file": leg["strategy"], "timeframe": leg.get("timeframe"),
        }
        total_pnl += leg_pnl
        if r["warnings"]:
            for w in r["warnings"]:
                _log(f"uid={uid} leg={leg['key']} {w}")

    if not dry_run and pending:
        batch.commit()

    # blend stays the owner's 1:1 ORB+ENGU-Q baseline — NOISE is reported as its own
    # leg but does NOT join the blend until the owner adds it to the book.
    blend_pnl = sum(leg_reports[k]["pnl_usd"] for k in ("ORB", "ENGUQ") if k in leg_reports)
    report = {
        "legs": leg_reports,
        "blend": {"pnl_usd": blend_pnl},
        "live": collect_live_fills(target_date),   # Layer 1: NT demo fills, unattributed
        "status": "runner_done",
        "run_date": target_date.isoformat(),
    }
    # Layer 3: three-way reconcile (api/paper_reconcile.py). live_expected reflects
    # whether the NinjaScript strategies are actually enabled on charts - while they are
    # not, "shadow signal with no live fill" is the designed state, and reporting it as a
    # divergence every single day is how a status field becomes wallpaper.
    try:
        from . import paper_reconcile
        report["reconcile"] = paper_reconcile.run(
            target_date, report, live_expected=NT_STRATEGIES_ENABLED)
        _v = report["reconcile"].get("verdict") or {}
        for _p in (_v.get("problems") or []):
            _log(f"uid={uid} RECONCILE {target_date.isoformat()}: {_p}")
    except Exception as e:
        report["reconcile"] = {"ok": None, "error": f"{type(e).__name__}: {e}"}

    # _trades was only ever a hand-off to the reconcile; it is redundant with trade_ids
    # and would bloat every report doc against the 1 MiB cap.
    for _blk in report["legs"].values():
        _blk.pop("_trades", None)

    if not dry_run:
        report_doc = json_safe(dict(report))
        report_doc["generatedAt"] = firestore.SERVER_TIMESTAMP
        q.db.collection("users").document(uid).collection("paper_reports").document(
            target_date.isoformat()).set(report_doc, merge=True)
        _leg_summary = ", ".join(f"{k}:{v['n_signals']}" for k, v in leg_reports.items())
        _log(f"uid={uid} {target_date.isoformat()}: blend ${total_pnl:,.0f} ({_leg_summary})")

    return report

"""ETF dip book #332 — SHADOW-ONLY paper leg (leg key ETFBOOK_332).

WHAT THIS IS
------------
Run #332 (BOOK-13) put the ROUND-25 weak-edge book through the house BOOK scorer and it
PASSED (whole n=1,676 / $832,313 / PF 1.72 / DD $73,194, 8 of 8 slices, lockbox 137
trades +$85,335 at PF 1.67). BACKTESTING_STACK.md's recorded next step was "ETF-only
sub-book numbers (without NQDIP) and a paper leg via the QQQ shadow adapter, owner call".
This module is that paper leg: the SEVEN ETF legs of run #332 (the ETF-only sub-book, no
NQDIP — that leg is NQ futures and belongs to the futures account), re-run every evening
on freshly-appended daily bars, with the position set diffed day over day so the board
records what the book WOULD have done.

*** NO ORDER IS EVER PLACED, SIMULATED, OR PREPARED BY THIS MODULE. ***
There is no broker client, no order object, and no credential read anywhere in this file.
It reads market DATA (yfinance daily bars) and writes a shadow LEDGER. The only writes are
(a) appending completed daily bars to the frozen 1d master CSVs and (b) paper-ledger rows
through api/paper.py's own helpers. tests/test_etf_book_shadow.py greps this file for the
forbidden call names and fails if any appears. Adding a live path is a deliberate change to
a DIFFERENT module, not a flag flip in this one -- the same rule api/qqq_exec.py states.

ACCOUNT TAG
-----------
`ACCOUNT = "STOCKS-SHADOW"`, `MODE = "SHADOW"` -- the stocks-account twin of the QQQ
shadow adapter (api/qqq_exec.py, whose config carries mode "SHADOW" and whose only
non-shadow value is refused). BOOKMARKS B1 and the #332 stack entry both call this a
STOCKS-account book; it never touches the NinjaTrader futures demo.

DATA PATH (once per evening)
----------------------------
  1. `update_masters(now)` pulls GLD/TLT/IWM/QQQ daily bars from yfinance (auto_adjust=True
     OHLC verbatim + raw volume, exactly tools/build_etf_masters.py's convention) and
     APPENDS only bars the master does not already have, each stamped 09:30 ET of its own
     calendar day. History is NEVER rewritten -- Yahoo re-scales a total-return series on
     every dividend, so a rewrite would silently move fifteen years of prices under a
     ledger that has already been published. The one exception, which is not a rewrite: a
     PARTIAL bar for today (a master built during the session) is replaced by the day's
     final bar. Whenever Yahoo's close for the master's last *settled* date differs from
     the stored close by more than 0.1% the divergence is logged -- that is the dividend
     re-scaling showing up, and it means the frozen history and the live series have
     drifted apart.
  2. `run_book()` re-runs the seven legs on the updated masters.
  3. `scan_leg()` establishes each leg's closed trades, its position at the close, and the
     day's ENTER/EXIT signals -- both of which fill at TOMORROW's open, which is what the
     plugins themselves do (a signal is read on a close and filled at the next day's open).
  4. `diff_positions(yesterday, today)` says what actually FILLED at today's open.

HOW THE POSITION SET IS OBTAINED (read this before changing it)
---------------------------------------------------------------
The ETFDIP plugins only emit a trade when it CLOSES, so an open position is invisible in
their output. Rather than transcribe three trading rules a second time (a copy that can
drift), this module PROBES the plugin: it appends two synthetic bars to the array, one
probe with an absurdly HIGH close and one with an absurdly LOW close, and re-runs the
plugin unchanged. Every ETFDIP exit is monotone in the close -- a long exits on a new
N-day closing high / a close back above a short SMA / a close above the signal day's prior
high, a short exits on a close back below a short SMA -- so the high probe forces any open
LONG to close and the low probe forces any open SHORT to close. The forced trade's ENTRY
fields are real (they come from real bars); only its exit is synthetic and is discarded.
Indicators are causal, so the synthetic tail cannot change any real bar's signal.

This is verified, not asserted: `tests/test_etf_book_shadow.py` checks the probe's position
set on three cells at a spread of historical dates against ground truth taken from one
full-history run (the trades whose entry_bar <= d < exit_bar), and the same check over the
full 2009-2025 window matched 87 of 87 cell-date pairs when the module was written.

Bar-index vocabulary, since three different "todays" are easy to confuse (n = number of
real bars, so the last real bar is index n-1):
  entry_bar <  n            position was already filled; it is open now
  entry_bar == n            ENTRY SIGNAL on today's close -> fills at tomorrow's open
  exit_bar  == n            EXIT SIGNAL on today's close  -> fills at tomorrow's open
  exit_bar  == n+1          no exit signal today; the synthetic bar forced it (still open)

SIZING AND COSTS -- identical to r25 and to the #332 job
--------------------------------------------------------
$100,000 notional per ETF trade, shares = notional / next-open price, and the round trip
costs 2 bps of notional = the $20 flat r25 charged. All three live INSIDE the plugin
(`notional`, `cost_bps`), so the job carries cost_pts 0 and mult 1 and the PnL the plugin
returns is already DOLLARS. Multiplying it again is the bug that stored 20x headlines on
runs #258/#261/#262/#263.

CADENCE AND WIRING
------------------
Registered in api/paper.py's PAPER_LEGS with `"runner": "etf_book"`, which makes
api.paper.run_shadow delegate to `run_shadow_leg` here -- so every ledger write (trade
upsert, stale-trade prune, daily report block) goes through paper.py's own `_emit` /
`_prune` helpers and the PAPER tab renders this leg exactly like the others.

Two moments touch it each evening, both idempotent and both calling ONE function:
  * api/runner.py's watch loop calls `api.paper.maybe_run_eod(q)` shortly after 16:10 ET.
    That is BEFORE this module will accept today's daily bar (see MIN_ET_FOR_TODAY), so
    that pass renders the leg from the master as it stands and logs "today's bar deferred".
  * the same watch loop then calls `maybe_nightly_update(q)` here, guarded to fire once per
    trading day at/after 16:15 ET. That is the once-per-evening step: it appends today's
    bar, re-runs the seven legs, diffs the position set and writes this leg's rows and its
    block of the day's paper report -- nothing else on the board is recomputed.

A day missed entirely (PC off, Yahoo down) costs nothing: the append is keyed on bar
timestamps and the ledger is upserted by document id, so the next evening's run catches up.

CLI
---
  python -m api.etf_book_shadow --dry-run --asof 2025-06-25   # master data only, no writes
  python -m api.etf_book_shadow --status
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.paths import UPLOADS

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:                                     # pragma: no cover
    _NY = None

# ── identity ─────────────────────────────────────────────────────────────────────
LEG_KEY = "ETFBOOK_332"
LABEL = "ETF dip book #332 (shadow)"
ACCOUNT = "STOCKS-SHADOW"          # the stocks-account twin of api/qqq_exec.py's SHADOW
MODE = "SHADOW"                    # this module accepts no other value, anywhere
SOURCE_RUN = 332
# The ET date this leg went on the board. Everything before it is a backtest re-run and
# api/paper.py stamps it backfill=True -- the house rule from LEG_LIVE_FROM.
LIVE_FROM = "2026-09-09"

# ── data ─────────────────────────────────────────────────────────────────────────
TICKERS = ["GLD", "TLT", "IWM", "QQQ"]
TIMEFRAME, SESSION, MASTER_SOURCE = "1d", "rth", "yahoo_adj"
# Fixed, not rolling: a rolling warm-up start would move the trade set under a ledger that
# has already been published. 2009-06-01 is r25's own warm window (tools/queue_etf_book.py
# --warm), which lets the 200-day trend filter be warm before the book's 2010 start.
HISTORY_FROM = "2009-06-01"
# Yahoo's daily row updates through the session and only settles at the 16:00 ET close.
# 16:15 is the margin BACKTESTING/the owner asked for; api.paper's own EOD pass fires at
# 16:10, which is why that pass defers today's bar to the hook below rather than appending
# a bar that might still be moving.
MIN_ET_FOR_TODAY = (16, 15)
# How far Yahoo's close for an already-settled date may drift from the frozen master
# before it is logged. A total-return series is re-scaled on every dividend, so drift is
# expected -- it just must never be silent.
DRIFT_LOG_FRAC = 0.001

# ── sizing / costs (all of it lives inside the plugin; job carries cost_pts 0, mult 1) ──
NOTIONAL = 100000
COST_BPS = 2.0                     # 2 bps of $100k = r25's $20 flat round trip
COST_USD_ROUND_TRIP = NOTIONAL * COST_BPS / 10000.0

# ── the seven legs run #332 selected ─────────────────────────────────────────────
# NOT hand-copied: r25's pre-registered inclusion rule (PF >= 1.40, net > 0, n >= 100 over
# 2010-06-07..2025-06-29) selected exactly these, and tools/queue_etf_book.py --etf-only
# prints them. `cell` names the r25 cell; `extra` is the only param that differs from the
# plugin's own DEFAULT_PARAMS, which is where notional / cost_bps / the rule knobs come
# from -- so this table can never drift from the file the validate ran.
BOOK_CELLS = [
    ("GLD", "DBL7L", "ETFDIP_DBL7_1_0.py", {}),
    ("TLT", "DBL7L", "ETFDIP_DBL7_1_0.py", {}),
    ("IWM", "RSI2B", "ETFDIP_RSI2_1_0.py", {"allow_shorts": True}),
    ("QQQ", "DBL7L", "ETFDIP_DBL7_1_0.py", {}),
    ("QQQ", "RSI2L", "ETFDIP_RSI2_1_0.py", {"allow_shorts": False}),
    ("QQQ", "RSI2B", "ETFDIP_RSI2_1_0.py", {"allow_shorts": True}),
    ("QQQ", "PB20L", "ETFDIP_PB20_1_0.py", {}),
]

# ── records ──────────────────────────────────────────────────────────────────────
# Same shape as api/qqq_exec.py's OUT_DIR: an owner-readable directory holding the
# adapter's memory across restarts. Overridable so tests never touch the real one.
OUT_DIR = os.environ.get("EDGELOG_ETFBOOK_DIR", r"C:\EdgeLog\etf_book_shadow")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
SIGNALS_CSV = os.path.join(OUT_DIR, "signals.csv")

# The seven legs pool into ONE paper leg key, and every 1d bar is stamped 09:30 ET, so two
# legs entering on the same day would collide on api/paper.py's doc id (pt_<key>_<entry
# unix>). Each sub-leg therefore carries a fixed one-second offset -- deterministic, stable
# across runs, and invisible in the board's HH:MM read of the entry time.
_SUBLEG_OFFSET_S = 1


def _log(msg):
    print(f"[etfbook] {msg}")


def _et_now():
    try:
        return pd.Timestamp.now(tz=_NY) if _NY is not None else pd.Timestamp.now(tz="US/Eastern")
    except Exception:                                 # pragma: no cover
        return pd.Timestamp.now(tz="US/Eastern")


# ── leg table ────────────────────────────────────────────────────────────────────
_PARAM_CACHE = {}


def _plugin_defaults(filename):
    """DEFAULT_PARAMS of an augur_strategies plugin, as a plain {name: default} dict."""
    if filename in _PARAM_CACHE:
        return dict(_PARAM_CACHE[filename])
    import importlib.util
    from augur_engine.paths import STRAT_DIR
    path = os.path.join(STRAT_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    _PARAM_CACHE[filename] = dict(d)
    return d


def book_legs():
    """The seven legs, with the exact parameters tools/queue_etf_book.py emits."""
    out = []
    for i, (tk, cell, plugin, extra) in enumerate(BOOK_CELLS):
        params = _plugin_defaults(plugin)
        params.update(extra)
        out.append({"sub": f"{tk}/{cell}", "ticker": tk, "cell": cell,
                    "strategy": plugin, "params": params,
                    "offset_s": i * _SUBLEG_OFFSET_S})
    return out


# ── master maintenance ───────────────────────────────────────────────────────────
def _master_path(ticker):
    row = find_master(ticker, TIMEFRAME, SESSION, MASTER_SOURCE)
    if not row:
        return None, None
    return row, os.path.join(UPLOADS, row["filename"])


def _stamp(day):
    """A calendar date -> the epoch second that day's bar carries (09:30 ET)."""
    ts = pd.Timestamp(day).normalize() + pd.Timedelta(hours=9, minutes=30)
    ts = ts.tz_localize("US/Eastern").tz_convert("UTC")
    return int((ts - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1))


def _yahoo_daily(ticker, start):
    """Daily bars from `start` (inclusive) to now. OHLC = auto_adjust=True verbatim,
    volume = raw unadjusted -- tools/build_etf_masters.py's exact convention. READ ONLY."""
    import yfinance as yf
    end = str(date.today() + timedelta(days=2))
    raw = yf.download(ticker, start=start, end=end, interval="1d",
                      auto_adjust=False, progress=False, actions=False)
    adj = yf.download(ticker, start=start, end=end, interval="1d",
                      auto_adjust=True, progress=False, actions=False)
    for df in (raw, adj):
        if isinstance(getattr(df, "columns", None), pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    if adj is None or not len(adj):
        return None
    a = adj[["Open", "High", "Low", "Close"]].dropna()
    vol = raw["Volume"].reindex(a.index).fillna(0.0) if (raw is not None and "Volume" in raw) \
        else pd.Series(0.0, index=a.index)
    return pd.DataFrame({
        "day": [pd.Timestamp(x).date() for x in a.index],
        "open": a["Open"].values.astype(float), "high": a["High"].values.astype(float),
        "low": a["Low"].values.astype(float), "close": a["Close"].values.astype(float),
        "volume": vol.values.astype(float),
    })


def update_master(ticker, now=None, dry_run=False):
    """Append completed daily bars to one frozen 1d master. Never rewrites history.

    Returns {ticker, appended, replaced, last_day, warnings, drift}. Exception-proof:
    a data hiccup must never take down the runner's watch loop.
    """
    now = now or _et_now()
    res = {"ticker": ticker, "appended": 0, "replaced": 0, "last_day": None,
           "warnings": [], "drift": None}
    try:
        row, path = _master_path(ticker)
        if not row or not os.path.exists(path):
            res["warnings"].append(f"{ticker}: no 1d master registered")
            return res
        df = pd.read_csv(path)
        if not len(df):
            res["warnings"].append(f"{ticker}: master is empty")
            return res
        df = df.sort_values("time").reset_index(drop=True)
        last_unix = int(df["time"].iloc[-1])
        last_day = pd.Timestamp(last_unix, unit="s", tz="UTC").tz_convert("US/Eastern").date()
        res["last_day"] = last_day.isoformat()

        today_et = now.date()
        # today's bar is only trusted once the close has settled
        accept_today = (now.hour, now.minute) >= MIN_ET_FOR_TODAY

        pull = _yahoo_daily(ticker, start=str(last_day - timedelta(days=10)))
        if pull is None or not len(pull):
            res["warnings"].append(f"{ticker}: yfinance returned no rows")
            return res
        # Only say a bar was deferred when one actually was -- overnight and at the weekend
        # there is no row for today, and a warning that fires every quiet minute is how a
        # warning field becomes wallpaper.
        if not accept_today and (pull["day"] == now.date()).any():
            res["warnings"].append(
                f"{ticker}: today's bar deferred (ET {now.strftime('%H:%M')} is before "
                f"{MIN_ET_FOR_TODAY[0]:02d}:{MIN_ET_FOR_TODAY[1]:02d}; Yahoo's daily row "
                "is still moving)")

        # DRIFT CHECK, and the discriminator that makes it actionable. Two very different
        # things make Yahoo disagree with the frozen master on a date it already holds:
        #   (a) a DIVIDEND RE-SCALE. A total-return series is re-scaled on every
        #       distribution, so EVERY bar moves by the same ratio. Correcting one bar
        #       would fabricate a gap that never traded, so history is left alone and the
        #       divergence is logged.
        #   (b) a PARTIAL LAST BAR. The master was built during a session, so its final row
        #       is an unfinished day and only THAT row is wrong.
        # Comparing the ratio on the last few settled bars separates them: constant ratio =
        # re-scale, last bar alone = partial.
        settled = pull[pull["day"] < today_et]
        by_day = {r["day"]: r for _, r in settled.iterrows()}
        tail = df.tail(6)
        ratios = []
        for _, brow in tail.iterrows():          # brow, not row: `row` is the registry row
            d = pd.Timestamp(int(brow["time"]), unit="s", tz="UTC").tz_convert("US/Eastern").date()
            if d in by_day and float(brow["close"]) > 0:
                ratios.append((d, float(by_day[d]["close"]) / float(brow["close"])))
        stale_last = False
        if ratios:
            d_last, r_last = ratios[-1]
            res["drift"] = round(abs(r_last - 1.0), 6)
            older = [r for _, r in ratios[:-1]]
            if abs(r_last - 1.0) > DRIFT_LOG_FRAC:
                rescale = bool(older) and all(abs(r - r_last) <= DRIFT_LOG_FRAC for r in older)
                if rescale:
                    msg = (f"{ticker}: DIVIDEND RE-SCALE -- Yahoo's whole series sits "
                           f"{(r_last - 1.0) * 100:+.3f}% from the frozen master (same ratio "
                           f"on {len(ratios)} bars). History is NOT rewritten; the frozen "
                           "tape and the live series have drifted apart, so this leg's "
                           "numbers are only reproducible against THIS master.")
                else:
                    stale_last = d_last == last_day
                    msg = (f"{ticker}: the master's LAST bar ({d_last}) is "
                           f"{(r_last - 1.0) * 100:+.3f}% from Yahoo's settled close while "
                           f"the bars before it agree -- an unfinished bar written during "
                           f"the session"
                           + (", replacing it with the settled bar." if stale_last else "."))
                res["warnings"].append(msg)
                _log(msg)

        rows = []
        replace_last = False
        for _, r in pull.iterrows():
            d = r["day"]
            if d > today_et:
                continue
            if d == today_et and not accept_today:
                continue
            stamp = _stamp(d)
            if stamp > last_unix:
                rows.append((stamp, r))
            elif stamp == last_unix and (stale_last or (d == today_et and accept_today)):
                # NOT a rewrite of history: the master's FINAL row was written during a
                # session, so it is an unfinished bar. Replace it with the settled bar --
                # bounded to that one row, only when the date matches, and only when the
                # discriminator above ruled out a dividend re-scale. If it did not actually
                # MOVE, do nothing, so a second run the same evening is a literal no-op on
                # disk rather than a rewrite that happens to be identical.
                stored = df.iloc[-1]
                same = all(abs(float(stored[k]) - float(r[k])) <= 1e-9
                           for k in ("open", "high", "low", "close"))
                if same:
                    continue
                replace_last = True
                rows.append((stamp, r))

        if not rows:
            return res
        if dry_run:
            res["appended"] = len(rows) - (1 if replace_last else 0)
            res["replaced"] = 1 if replace_last else 0
            return res

        keep = df[df["time"] < last_unix] if replace_last else df
        add = pd.DataFrame([{"time": s, "open": float(r["open"]), "high": float(r["high"]),
                             "low": float(r["low"]), "close": float(r["close"]),
                             "volume": float(r["volume"])} for s, r in rows])
        out = pd.concat([keep, add], ignore_index=True)
        out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
        tmp = path + ".tmp"
        out.to_csv(tmp, index=False)
        os.replace(tmp, path)
        res["appended"] = len(rows) - (1 if replace_last else 0)
        res["replaced"] = 1 if replace_last else 0
        res["last_day"] = str(rows[-1][1]["day"])
        _log(f"{ticker}: +{res['appended']} bar(s)"
             + (", last partial bar replaced" if replace_last else "")
             + f" -> {res['last_day']}")
    except Exception as e:
        res["warnings"].append(f"{ticker}: {type(e).__name__}: {e}")
        _log(f"update_master({ticker}) failed: {type(e).__name__}: {e}")
    return res


def update_masters(now=None, dry_run=False):
    return [update_master(tk, now=now, dry_run=dry_run) for tk in TICKERS]


# ── the position probe (see the module docstring) ────────────────────────────────
def _probe_arrays(arrays, high):
    """A copy of `arrays` with two synthetic bars whose close is absurdly high/low."""
    a = dict(arrays)
    px = float(np.asarray(arrays["close"], float)[-1])
    val = px * 1000.0 if high else px / 1000.0
    for k in ("open", "high", "low", "close"):
        a[k] = np.concatenate([np.asarray(arrays[k], float), np.full(2, val)])
    if arrays.get("volume") is not None:
        a["volume"] = np.concatenate([np.asarray(arrays["volume"], float), np.zeros(2)])
    if arrays.get("day_id") is not None:
        d = np.asarray(arrays["day_id"])
        a["day_id"] = np.concatenate([d, d[-1] + 1 + np.arange(2)])
    last = pd.Timestamp(arrays["index"][-1])
    a["index"] = list(arrays["index"]) + [last + pd.Timedelta(days=i + 1) for i in range(2)]
    return a


def scan_leg(leg, arrays):
    """One sub-leg's closed trades, open position and today's signals.

    Trade tuples out of the ETFDIP plugins are
    (entry_bar, exit_bar, pnl_DOLLARS, side, entry_px, exit_px).
    """
    n = len(np.asarray(arrays["close"], float))
    idx = arrays["index"]

    base = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                        cost_pts=0.0, return_trades=True)
    closed = list((base or {}).get("trades") or [])

    found = {}
    for high in (True, False):
        pr = run_backtest(leg["strategy"], arrays=_probe_arrays(arrays, high),
                          params=leg["params"], cost_pts=0.0, return_trades=True)
        for t in list((pr or {}).get("trades") or []):
            eb, xb = int(t[0]), int(t[1])
            if eb <= n and xb >= n:
                found[(eb, int(t[3]))] = t

    positions, signals = [], []
    for (eb, side), t in sorted(found.items()):
        xb = int(t[1])
        entry_px = float(t[4])
        shares = int(NOTIONAL // entry_px) if entry_px > 0 else 0
        if eb == n:
            # signalled on today's close; the fill is tomorrow's open, which does not exist
            # yet -- entry_px here is the plugin's own read of it, so it is NOT reported as
            # a price. Shares are sized on the fill, so they are unknown too.
            signals.append({"sub": leg["sub"], "ticker": leg["ticker"], "cell": leg["cell"],
                            "action": "ENTER", "side": side,
                            "fill": "next open", "notional": NOTIONAL})
            continue
        pos = {"sub": leg["sub"], "ticker": leg["ticker"], "cell": leg["cell"],
               "side": side, "entry_bar": eb, "shares": shares,
               "entry_px": round(entry_px, 4),
               "entry_date": pd.Timestamp(idx[eb]).date().isoformat(),
               "mark_px": round(float(np.asarray(arrays["close"], float)[n - 1]), 4)}
        pos["open_pnl_usd"] = round(side * (pos["mark_px"] - entry_px) * shares
                                    - COST_USD_ROUND_TRIP, 2)
        pos["exiting"] = bool(xb == n)
        positions.append(pos)
        if xb == n:
            signals.append({"sub": leg["sub"], "ticker": leg["ticker"], "cell": leg["cell"],
                            "action": "EXIT", "side": side, "shares": shares,
                            "entry_date": pos["entry_date"], "fill": "next open"})

    trades = []
    for t in closed:
        eb, xb = int(t[0]), int(t[1])
        entry_px, exit_px = float(t[4]), float(t[5]) if len(t) > 5 else None
        shares = int(NOTIONAL // entry_px) if entry_px > 0 else 0
        trades.append({
            "leg": LEG_KEY, "sub": leg["sub"], "ticker": leg["ticker"], "cell": leg["cell"],
            "strategy": leg["strategy"], "side": int(t[3]),
            "entry_dt": pd.Timestamp(idx[eb]) + pd.Timedelta(seconds=leg["offset_s"]),
            "exit_dt": pd.Timestamp(idx[xb]) + pd.Timedelta(seconds=leg["offset_s"]),
            "entry_px": entry_px, "exit_px": exit_px,
            "size": float(shares),
            # pnl_pts is the ONE-SHARE move so a row still reconciles against a chart;
            # pnl_usd is the plugin's own dollars (already sized and already costed), which
            # is why the paper leg carries mult 1 and cost_pts 0.
            "pnl_pts": (exit_px - entry_px) * int(t[3]) if exit_px is not None else 0.0,
            "pnl_usd": float(t[2]),
        })
    return {"trades": trades, "positions": positions, "signals": signals, "n_bars": n}


def diff_positions(prev, cur):
    """What FILLED at today's open: positions that appeared, and positions that vanished.

    Keyed on (sub, entry_date, side) -- stable, because only an open position's exit moves
    as new bars arrive. `prev`/`cur` are lists of the dicts scan_leg returns.
    """
    def key(p):
        return (p["sub"], p["entry_date"], int(p["side"]))
    a = {key(p): p for p in (prev or [])}
    b = {key(p): p for p in (cur or [])}
    opened = [b[k] for k in sorted(b.keys() - a.keys())]
    closed = [a[k] for k in sorted(a.keys() - b.keys())]
    return {"opened": opened, "closed": closed}


# ── state (idempotency) ──────────────────────────────────────────────────────────
def _read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _write_state(patch):
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        st = _read_state()
        st.update(patch)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=2, default=str)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        _log(f"state write failed: {type(e).__name__}: {e}")
    return None


def _append_signals_csv(run_date, signals):
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        new = not os.path.exists(SIGNALS_CSV)
        with open(SIGNALS_CSV, "a", encoding="utf-8", newline="") as fh:
            if new:
                fh.write("run_date,sub,action,side,fill,shares\n")
            for s in signals:
                fh.write("%s,%s,%s,%d,%s,%s\n" % (
                    run_date, s["sub"], s["action"], int(s["side"]),
                    s.get("fill", ""), s.get("shares", "")))
    except Exception as e:
        _log(f"signals.csv append failed: {type(e).__name__}: {e}")


# ── the once-per-evening step ────────────────────────────────────────────────────
def run_book(asof=None):
    """Re-run the seven legs on the masters as they stand. Pure compute -- this function
    touches neither the network nor the disk; pulling and appending is nightly_update's job.

    asof: cut the master at this date (the dry-run / replay path). None = whatever the
    master holds.
    """
    legs = book_legs()
    per_leg, trades, positions, signals, warnings = {}, [], [], [], []
    arrays_by_tk = {}
    for tk in TICKERS:
        row, _ = _master_path(tk)
        if not row:
            warnings.append(f"no 1d master for {tk}")
            continue
        try:
            arrays_by_tk[tk] = load_master_arrays(row, date_from=HISTORY_FROM,
                                                  date_to=(str(asof) if asof else None))
        except Exception as e:
            warnings.append(f"{tk}: load failed: {type(e).__name__}: {e}")

    last_bar = None
    for leg in legs:
        arr = arrays_by_tk.get(leg["ticker"])
        if arr is None:
            warnings.append(f"{leg['sub']}: skipped, no data")
            continue
        try:
            r = scan_leg(leg, arr)
        except Exception as e:
            warnings.append(f"{leg['sub']}: {type(e).__name__}: {e}")
            continue
        per_leg[leg["sub"]] = {"n_trades": len(r["trades"]),
                               "n_open": len(r["positions"]),
                               "n_signals": len(r["signals"])}
        trades.extend(r["trades"])
        positions.extend(r["positions"])
        signals.extend(r["signals"])
        bar = pd.Timestamp(arr["index"][-1])
        last_bar = bar if last_bar is None else max(last_bar, bar)

    trades.sort(key=lambda t: (t["exit_dt"], t["entry_dt"]))
    return {"legs": per_leg, "trades": trades, "positions": positions,
            "signals": signals, "warnings": warnings,
            "asof": (str(asof) if asof else (last_bar.date().isoformat() if last_bar is not None else None)),
            "last_bar": last_bar, "open_pnl_usd": round(sum(p["open_pnl_usd"] for p in positions), 2)}


def nightly_update(now=None, dry_run=False, asof=None, force=False):
    """Pull -> append -> re-run -> diff. The once-per-evening step. Never raises.

    Idempotent: the master append is keyed on bar timestamps (a second call on the same
    evening appends nothing), and the recompute is deterministic, so a second call on the
    same evening produces the identical payload and writes no new state. NO ORDER IS EVER
    PLACED HERE -- the output is a record of what the book WOULD have done.
    """
    now = now or _et_now()
    out = {"mode": MODE, "account": ACCOUNT, "leg": LEG_KEY, "source_run": SOURCE_RUN,
           "run_at": now.isoformat(), "masters": [], "bars_appended": 0,
           "warnings": [], "repeat": False}
    try:
        st = _read_state()
        run_date = None

        if not dry_run and asof is None:
            ms = update_masters(now=now, dry_run=False)
            out["masters"] = ms
            out["bars_appended"] = sum(m["appended"] for m in ms)
            for m in ms:
                out["warnings"].extend(m["warnings"])

        book = run_book(asof=asof)
        out["warnings"].extend(book["warnings"])
        run_date = book["asof"]
        out["run_date"] = run_date
        out["legs"] = book["legs"]
        out["positions"] = book["positions"]
        out["signals"] = book["signals"]
        out["open_pnl_usd"] = book["open_pnl_usd"]
        out["trades"] = book["trades"]

        prev = st.get("positions") if st.get("run_date") != run_date else st.get("prev_positions")
        out["filled"] = diff_positions(prev or [], book["positions"])
        out["repeat"] = bool(st.get("run_date") == run_date and not force)

        if not dry_run:
            if not out["repeat"]:
                _append_signals_csv(run_date, book["signals"])
            _write_state({"run_date": run_date, "positions": book["positions"],
                          "prev_positions": (prev or []),
                          "signals": book["signals"],
                          "last_run_at": now.isoformat(),
                          "open_pnl_usd": book["open_pnl_usd"],
                          "mode": MODE, "account": ACCOUNT})
    except Exception as e:
        msg = f"nightly_update failed: {type(e).__name__}: {e}"
        out["warnings"].append(msg)
        _log(msg)
    return out


def status():
    """What the leg currently holds and when it last ran. Reads state + masters only."""
    st = _read_state()
    masters = {}
    for tk in TICKERS:
        row, _ = _master_path(tk)
        masters[tk] = (row or {}).get("date_to")
    return {"leg": LEG_KEY, "label": LABEL, "mode": MODE, "account": ACCOUNT,
            "source_run": SOURCE_RUN, "live_from": LIVE_FROM,
            "n_legs": len(BOOK_CELLS), "notional_per_trade": NOTIONAL,
            "cost_round_trip_usd": COST_USD_ROUND_TRIP,
            "run_date": st.get("run_date"), "last_run_at": st.get("last_run_at"),
            "open_positions": len(st.get("positions") or []),
            "open_pnl_usd": st.get("open_pnl_usd"),
            "last_signals": st.get("signals") or [],
            "masters_thru": masters, "state_path": STATE_PATH}


# ── api/paper.py integration ─────────────────────────────────────────────────────
def run_shadow_leg(leg, today):          # noqa: ARG001 -- run_shadow's signature
    """api.paper.run_shadow's contract, for the ETFBOOK_332 leg. Never raises.

    `leg` and `today` are part of run_shadow's signature and deliberately unused: this leg
    carries its own leg table and its own notion of the trading day (the last bar the
    masters hold), and taking the caller's would let the two drift apart silently.

    Everything downstream of this -- trade upsert, stale-trade prune, the daily report
    block, the PAPER tab -- is api/paper.py's own code. This only supplies the trades.
    """
    warnings, trades, bars = [], [], 0
    fresh_thru = None
    ran_ok = False
    try:
        from .paper import PAPER_START
        r = nightly_update(now=_et_now())
        warnings.extend(r.get("warnings") or [])
        bars = int(r.get("bars_appended") or 0)
        # The board only ever shows trades from PAPER_START on -- the same cut every other
        # leg makes in run_shadow. Without it the book's whole 2009-onwards history would
        # land in the ledger (1,140 rows on the first run) and be drawn as paper evidence.
        start = pd.Timestamp(PAPER_START).date()
        trades = [t for t in (r.get("trades") or []) if t["entry_dt"].date() >= start]
        lb = None
        for m in (r.get("masters") or []):
            if m.get("last_day"):
                lb = max(lb or m["last_day"], m["last_day"])
        if lb:
            fresh_thru = _stamp(pd.Timestamp(lb).date())
        # ran_ok gates api/paper.py's PRUNE, which deletes ledger rows the leg no longer
        # produces. It may only be True when every sub-leg actually scanned -- a partial
        # book (one master failed to load) must never be allowed to delete the rows the
        # missing legs own.
        ran_ok = len(r.get("legs") or {}) == len(BOOK_CELLS)
    except Exception as e:
        warnings.append(f"exception in run_shadow_leg({LEG_KEY}): {type(e).__name__}: {e}")
    return {"trades": trades, "ungated_trades": [], "gate": None,
            "bars_appended": bars, "data_fresh_thru": fresh_thru,
            "warnings": warnings, "ran_ok": ran_ok}


_last_hook_date = None


def maybe_nightly_update(q):
    """Guarded once-per-trading-day hook for api/runner.py's watch loop.

    Fires at/after 16:15 ET on a weekday, at most once per ET date per process (and the
    on-disk state makes a restart in the same evening a no-op too). Runs the pull/append/
    re-run/diff and then asks api.paper to rewrite THIS leg's rows and report block --
    nothing else on the paper board is recomputed. Exception-proof.
    """
    global _last_hook_date
    try:
        now = _et_now()
        if now.weekday() >= 5:
            return None
        if (now.hour, now.minute) < MIN_ET_FOR_TODAY:
            return None
        today_s = now.date().isoformat()
        if _last_hook_date == today_s:
            return None
        _last_hook_date = today_s
        res = nightly_update(now=now)
        _log(f"{today_s}: +{res.get('bars_appended', 0)} bars, "
             f"{len(res.get('signals') or [])} signal(s), "
             f"{len(res.get('positions') or [])} open, "
             f"open PnL ${res.get('open_pnl_usd', 0):,.0f}")
        try:
            from . import paper as _paper
            _paper.rerun_legs(q, [LEG_KEY], now.date())
        except Exception as e:
            _log(f"paper rerun skipped: {type(e).__name__}: {e}")
        return res
    except Exception as e:
        _log(f"maybe_nightly_update error: {type(e).__name__}: {e}")
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────────
def _print_dry_run(asof):
    r = nightly_update(dry_run=True, asof=asof)
    d = r.get("run_date")
    print(f"ETF DIP BOOK #332 -- SHADOW ({MODE}, account {ACCOUNT}) -- as of {d}")
    print("  master data only; NOTHING was pulled, appended or written.")
    print(f"  {len(BOOK_CELLS)} legs, ${NOTIONAL:,} notional per trade, "
          f"${COST_USD_ROUND_TRIP:,.0f} round trip\n")
    sig = r.get("signals") or []
    print(f"  SIGNALS ON {d} CLOSE -> fill at the NEXT open ({len(sig)}):")
    if not sig:
        print("    (none)")
    for s in sig:
        print("    %-12s %-6s %-5s  %s" % (
            s["sub"], s["action"], "LONG" if s["side"] > 0 else "SHORT", s["fill"]))
    pos = r.get("positions") or []
    print(f"\n  OPEN AT THAT CLOSE ({len(pos)}), open PnL ${r.get('open_pnl_usd', 0):,.0f}:")
    if not pos:
        print("    (flat)")
    for p in pos:
        print("    %-12s %-5s %6d sh @ %9.2f  entered %s  mark %9.2f  open $%9.2f%s" % (
            p["sub"], "LONG" if p["side"] > 0 else "SHORT", p["shares"], p["entry_px"],
            p["entry_date"], p["mark_px"], p["open_pnl_usd"],
            "  [EXITING]" if p["exiting"] else ""))
    tr = [t for t in (r.get("trades") or []) if str(t["exit_dt"].date()) == str(d)]
    print(f"\n  ROUND TRIPS CLOSING ON {d} ({len(tr)}):")
    if not tr:
        print("    (none)")
    for t in tr:
        print("    %-12s %-5s %6.0f sh  %9.2f -> %9.2f   $%9.2f" % (
            t["sub"], "LONG" if t["side"] > 0 else "SHORT", t["size"],
            t["entry_px"], t["exit_px"], t["pnl_usd"]))
    for w in (r.get("warnings") or []):
        print(f"  WARN {w}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ETF dip book #332 shadow leg (never trades)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what the leg would have recorded; no pull, no writes")
    ap.add_argument("--asof", default=None, help="cut the master at this date (YYYY-MM-DD)")
    ap.add_argument("--status", action="store_true", help="print status() as JSON")
    a = ap.parse_args(argv)
    if a.status:
        print(json.dumps(status(), indent=2, default=str))
        return 0
    if a.dry_run:
        return _print_dry_run(a.asof)
    ap.error("this module never trades; run it with --dry-run or --status")


if __name__ == "__main__":
    sys.exit(main())

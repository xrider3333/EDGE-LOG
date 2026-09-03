"""QQQ SHADOW execution adapter -- Stage 1 of "trade the crowned NQ strategies as QQQ
shares on Webull".

SHADOW ONLY. No order is ever sent anywhere, to any broker, by this module. There is
no Webull *order* code in this file at all -- only a market-DATA quote lookup (read-only)
and a `mode` config field that accepts exactly "SHADOW" and refuses (logged, no-op)
anything else. Adding a LIVE path is a deliberate future change to a DIFFERENT module,
not a flag flip in this one.

SIGNAL SOURCE. This never re-implements fill parsing. It reuses api.nt_sync.parse_fills
(the same CSV reader the real-money journal sync uses) to read C:\\EdgeLog\\fills.csv --
the file the NinjaScript AddOn appends to on every live fill from the three strategies
already running on real-time data in NinjaTrader (EdgeLogORB..., EdgeLogENGUQ1m,
EdgeLogNOISE). This module mirrors those fills into paper QQQ SHARE lots; it never
computes its own trading signal.

LEG ATTRIBUTION. A fill's `SignalName` column is the entry tag NinjaTrader stamped on
the order ("ORB", "ENGUQ", "NOISE" -- case-insensitive substring match, see
_leg_from_signal). Exit fills carry a generic tag ("Close", "EOD", ...) with no leg
name, so exits are attributed by POSITION: each (account, instrument) group is tracked
FIFO exactly like api.nt_sync.build_trades (same adding/reducing logic), and the leg
resolved on the fill that opened the position rides along for every fill that reduces
it, until it returns flat. A reducing fill on a group with no open leg (unrecognized
opening signal, e.g. legacy fills written before SignalName existed) is skipped with a
WARN -- never guessed at.

PRICING. Three-way fallback per fill, recorded as `px_source`:
  1. webull_quote -- official Webull OpenAPI QQQ snapshot, ONLY if its own timestamp is
     under 60s old (older = the account's data plan is delayed/refused; treated as
     unavailable, never trusted silently stale).
  2. nq_ratio -- NQ fill price / a QQQ:NQ ratio calibrated at 09:30 ET each day from
     yfinance's QQQ 1m close and the NQ price at the same minute (from
     C:\\EdgeLog\\ohlc_addon\\NQ_10s.csv, falling back to C:\\EdgeLog\\ohlc\\NQ_10s.csv),
     re-calibrated every 30 minutes.
  3. none -- if neither source can price the fill, it is logged and skipped rather than
     recorded with a fabricated price.

RAILS (identical logic shadow and, eventually, live):
  (a) shares > max_shares_per_leg -> refuse the lot (WARN, no lot opened).
  (b) daily shadow loss (realized + open marks) beyond daily_loss_limit_usd -> close
      every open lot, set breaker_tripped for the rest of the (ET) trading day, ignore
      further entries.
  (c) entries only inside [session.open, session.last_entry] ET; at session.flat_by,
      every open lot is closed and tagged "EOD".
  (d) kill file present -> no new lots; close every open lot, tagged "KILL".
  (e) feed staleness (NinjaTrader AddOn heartbeat older than 90s, via
      api.nt_sync._addon_heartbeat) blocks new entries and pushes at most one ntfy
      alert per 30 minutes while it persists.

RECORDS: C:\\EdgeLog\\qqq_exec\\orders.csv (every shadow order), \\trades.csv (every
closed round-trip), \\state.json (cursor + open lots + rail state -- this IS the
adapter's memory across ticks/restarts), \\config.json (owner-editable, reloaded every
tick). Firestore doc users/{uid}/meta/qqq_exec mirrors the current state for the web
SHADOW EXECUTION panel.

CLI: `python -m api.qqq_exec --once [--uid UID]` runs a single tick and exits -- used by
`api/runner.py`'s watch loop (own thread, ticking every ~5s during the session, exactly
like the nt-bridge watchdog thread) and by hand for verification.
"""
import argparse
import csv
import json
import os
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import nt_sync

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- zoneinfo ships with 3.9+, this repo runs 3.13
    _NY = None

# -- paths -----------------------------------------------------------------------
OUT_DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", r"C:\EdgeLog\qqq_exec")
CONFIG_PATH = os.path.join(OUT_DIR, "config.json")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
ORDERS_CSV = os.path.join(OUT_DIR, "orders.csv")
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
DEFAULT_FILLS = nt_sync.DEFAULT_FILLS
NQ_10S_PRIMARY = r"C:\EdgeLog\ohlc_addon\NQ_10s.csv"
NQ_10S_FALLBACK = r"C:\EdgeLog\ohlc\NQ_10s.csv"
WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")

LEGS = ("ORB", "ENGUQ", "NOISE")
TICK_SEC = 5.0
FEED_STALE_SEC = 90.0
FEED_ALERT_COOLDOWN_SEC = 30 * 60
QUOTE_MAX_AGE_SEC = 60.0
CALIB_REFRESH_SEC = 30 * 60
ORDERS_KEEP = 100
TRADES_KEEP = 200

DEFAULT_CONFIG = {
    "mode": "SHADOW",
    "shares": {"ORB": 5, "ENGUQ": 5, "NOISE": 5},
    "max_shares_per_leg": 10,
    "daily_loss_limit_usd": 150,
    "session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:58"},
    "kill_file": r"C:\EdgeLog\qqq_exec\KILL",
    "slippage_per_share": 0.01,
}


# -- small time helpers ------------------------------------------------------------
def _now_et():
    return datetime.now(_NY) if _NY else datetime.utcnow()


def _hhmm(s):
    h, m = str(s).split(":")
    return int(h), int(m)


def _et_hhmm(dt):
    return dt.hour, dt.minute


def _is_weekday(dt):
    return dt.weekday() < 5


def _in_market_window(dt):
    """09:25-16:05 ET Mon-Fri -- the tick-loop's active window (broader than the
    entry window so EOD-flatten / breaker / heartbeat logic all still run)."""
    if not _is_weekday(dt):
        return False
    return (9, 25) <= _et_hhmm(dt) <= (16, 5)


def _in_entry_window(dt, sess):
    o = _hhmm(sess.get("open", "09:31"))
    le = _hhmm(sess.get("last_entry", "15:55"))
    return _is_weekday(dt) and o <= _et_hhmm(dt) <= le


def _past_flat_by(dt, sess):
    fb = _hhmm(sess.get("flat_by", "15:58"))
    return _et_hhmm(dt) >= fb


# -- config / state I/O -------------------------------------------------------------
def load_config(path=None, log=print):
    """Reloaded every tick so the owner can edit rails live. Creates the file with
    defaults if missing. A `mode` other than "SHADOW" is refused (logged) and the
    adapter falls back to SHADOW rather than doing nothing silently -- there is no
    other mode this build knows how to run.

    `path` defaults to None rather than the module constant CONFIG_PATH directly:
    a caller (the smoke test) that reassigns qqq_exec.CONFIG_PATH to a temp dir must
    have that take effect here too, and a default bound at def-time to the ORIGINAL
    constant would silently ignore it -- read the current module global instead."""
    path = path if path is not None else CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        log(f"[qqq-exec] wrote default config -> {path}")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        log(f"[qqq-exec] config read failed ({type(e).__name__}: {e}) -- using defaults")
        cfg = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    mode = str(merged.get("mode") or "").strip().upper()
    if mode != "SHADOW":
        log(f"[qqq-exec] REFUSED mode={merged.get('mode')!r} -- this build only runs "
            f"SHADOW (no live-order code exists). Forcing SHADOW.")
        merged["mode"] = "SHADOW"
    return merged


def _default_state():
    return {
        "processed_ids": [],       # capped list of fill exec_ids already handled
        "group_leg": {},           # "account|instrument" -> leg currently open there
        "legs": {},                # leg -> open lot dict, or absent when flat
        "realized_pnl_today": 0.0,
        "trading_day": None,       # ET date string the realized/breaker figures belong to
        "breaker_tripped": False,
        "flat_by_done_date": None,
        "kill_done": False,
        "last_feed_alert": 0.0,
        "feed_stale": False,
        "calib": None,             # {"ratio","source","at"}
        "last_publish": 0.0,
        "last_doc_hash": None,
    }


def load_state(path=None):
    path = path if path is not None else STATE_PATH
    if not os.path.exists(path):
        return _default_state()
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return _default_state()
    base = _default_state()
    base.update(st or {})
    return base


def save_state(state, path=None):
    path = path if path is not None else STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, path)


def _roll_day(state, today):
    if state.get("trading_day") != today:
        state["trading_day"] = today
        state["realized_pnl_today"] = 0.0
        state["breaker_tripped"] = False
        state["flat_by_done_date"] = None
        state["kill_done"] = False


# -- ntfy push (best-effort, non-fatal -- same shape as api.nt_drawdown_alert) ------
def _notify(msg, title, log=print):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log(f"[qqq-exec] NTFY_TOPIC unset, push skipped: {title}: {msg}")
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), method="POST",
            headers={"Title": title, "Priority": "default"})
        urllib.request.urlopen(req, timeout=4)
    except Exception as e:
        log(f"[qqq-exec] ntfy push failed: {type(e).__name__}: {e}")


# -- leg attribution -----------------------------------------------------------------
def _leg_from_signal(sig):
    s = str(sig or "").upper()
    for leg in LEGS:
        if leg in s:
            return leg
    return None


def _group_key(account, instrument):
    return f"{account}|{instrument}"


# -- CSV writers ---------------------------------------------------------------------
def _append_csv(path, cols, row, keep):
    """Append one row; keep the file trimmed to the last `keep` data rows so it never
    grows without bound. Cheap: rewritten only when the cap is exceeded."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if is_new:
            w.writeheader()
        w.writerow(row)
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) > keep:
            rows = rows[-keep:]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
    except Exception:
        pass


ORDER_COLS = ["ts_et", "leg", "action", "side", "shares", "nq_px", "qqq_px",
              "px_source", "reason"]
TRADE_COLS = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px",
              "pnl", "nq_pnl_points", "exit_reason"]


def _record_order(leg, action, side, shares, nq_px, qqq_px, px_source, reason, log=print):
    row = {"ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "leg": leg, "action": action,
           "side": side, "shares": shares,
           "nq_px": round(nq_px, 4) if nq_px is not None else "",
           "qqq_px": round(qqq_px, 4) if qqq_px is not None else "",
           "px_source": px_source or "", "reason": reason or ""}
    _append_csv(ORDERS_CSV, ORDER_COLS, row, ORDERS_KEEP)
    log(f"[qqq-exec] {action} {leg} {side} {shares}sh @ {qqq_px} "
        f"({px_source}) -- {reason}")


def _record_trade(lot, exit_px, exit_reason):
    entry_px = lot["entry_px"]
    side_mult = 1 if lot["side"] == "long" else -1
    pnl = round((exit_px - entry_px) * side_mult * lot["shares_total"], 2)
    nq_pts = None
    if lot.get("nq_entry_px") is not None and lot.get("last_nq_px") is not None:
        nq_pts = round((lot["last_nq_px"] - lot["nq_entry_px"]) * side_mult, 4)
    row = {"leg": lot["leg"], "entry_ts": lot["entry_ts"],
           "exit_ts": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "side": lot["side"],
           "shares": lot["shares_total"], "entry_px": round(entry_px, 4),
           "exit_px": round(exit_px, 4), "pnl": pnl,
           "nq_pnl_points": nq_pts if nq_pts is not None else "",
           "exit_reason": exit_reason}
    _append_csv(TRADES_CSV, TRADE_COLS, row, TRADES_KEEP)
    return pnl


# -- pricing ---------------------------------------------------------------------------
def default_webull_quote(symbol="QQQ", log=print):
    """Try the official Webull OpenAPI market-data snapshot. Returns (price, age_secs)
    or None on any failure/unavailability (missing SDK, missing keys, no subscription,
    a quote timestamp too old to trust). Never raises -- read-only, no order call of
    any kind exists anywhere in this module."""
    try:
        if not os.path.exists(WEBULL_KEYS):
            return None
        with open(WEBULL_KEYS, encoding="utf-8") as f:
            keys = json.load(f)
        ak = (keys.get("app_key") or "").strip()
        sk = (keys.get("app_secret") or "").strip()
        if not ak or not sk or ak.startswith("PASTE_"):
            return None
        from webull.core.client import ApiClient
        from webull.data.quotes.market_data import MarketData
        from webull.data.common.category import Category
        api = ApiClient(ak, sk, (keys.get("region") or "us").strip().lower(),
                        token_check_duration_seconds=10, token_check_interval_seconds=3,
                        connect_timeout=8, timeout=15)
        md = MarketData(api)
        for cat in (Category.US_ETF, Category.US_STOCK):
            try:
                resp = md.get_snapshot([symbol], cat)
            except Exception:
                resp = None
            if not resp:
                continue
            item = resp[0] if isinstance(resp, list) else resp
            price = (getattr(item, "close", None) or getattr(item, "price", None)
                     or getattr(item, "last_price", None))
            ts = (getattr(item, "trade_time", None) or getattr(item, "timestamp", None)
                  or getattr(item, "mktradetime", None))
            if price is None:
                continue
            age = None
            try:
                tsf = float(ts)
                if tsf > 1e12:
                    tsf /= 1000.0
                age = max(0.0, time.time() - tsf)
            except Exception:
                age = None
            if age is not None and age > QUOTE_MAX_AGE_SEC:
                log(f"[qqq-exec] webull quote too old ({age:.0f}s) -- treating as unavailable")
                return None
            return float(price), age
        return None
    except Exception as e:
        log(f"[qqq-exec] webull quote unavailable: {type(e).__name__}: {e}")
        return None


def _last_nq_close(before_ts=None):
    """Latest NQ 10s close at/just before `before_ts` (unix seconds), from the addon
    file with fallback to the legacy one. Returns (price, ts) or (None, None)."""
    for path in (NQ_10S_PRIMARY, NQ_10S_FALLBACK):
        if not os.path.exists(path):
            continue
        try:
            best = None
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        t = float(row["time"])
                        c = float(row["close"])
                    except Exception:
                        continue
                    if before_ts is not None and t > before_ts:
                        continue
                    if best is None or t > best[1]:
                        best = (c, t)
            if best is not None:
                return best
        except Exception:
            continue
    return None, None


def default_ratio_calibration(log=print):
    """QQQ:NQ ratio at 09:30 ET today, from yfinance's last QQQ 1m close and the NQ
    close at the same minute in the 10s master. Returns {"ratio","source","at"} or
    None. Best-effort only -- a failed calibration falls back to whatever ratio the
    caller already has cached."""
    try:
        import yfinance as yf
        now = _now_et()
        anchor = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now < anchor:
            anchor -= timedelta(days=1)
        tkr = yf.Ticker("QQQ")
        df = tkr.history(start=anchor - timedelta(minutes=5), end=anchor + timedelta(minutes=10),
                         interval="1m", prepost=False, auto_adjust=False)
        if df is None or not len(df):
            return None
        idx = df.index
        anchor_cmp = anchor.astimezone(idx.tz) if idx.tz else anchor
        after = df[idx >= anchor_cmp]
        row = after.iloc[0] if len(after) else df.iloc[-1]
        qqq_px = float(row["Close"])
        bar_ts = row.name
        bar_epoch = bar_ts.timestamp() if hasattr(bar_ts, "timestamp") else time.time()
        nq_px, nq_ts = _last_nq_close(before_ts=bar_epoch + 65)
        if nq_px is None or qqq_px <= 0:
            return None
        ratio = nq_px / qqq_px
        return {"ratio": ratio, "source": "yfinance+NQ_10s",
                "at": _now_et().strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        log(f"[qqq-exec] ratio calibration failed: {type(e).__name__}: {e}")
        return None


def _maybe_calibrate(state, ratio_fn, log=print):
    calib = state.get("calib")
    stale = calib is None
    if calib and calib.get("at"):
        try:
            at = datetime.strptime(calib["at"], "%Y-%m-%d %H:%M:%S")
            stale = (datetime.now() - at).total_seconds() > CALIB_REFRESH_SEC
        except Exception:
            stale = True
    if stale:
        fresh = ratio_fn(log=log)
        if fresh:
            state["calib"] = fresh
            log(f"[qqq-exec] ratio calibrated: {fresh['ratio']:.3f} ({fresh['source']})")
        elif calib is None:
            log("[qqq-exec] no ratio calibration available yet -- nq_ratio pricing "
                "unavailable until one succeeds")
    return state.get("calib")


def resolve_price(cfg, state, nq_px, quote_fn, ratio_fn, log=print):
    """(qqq_px, source) for one fill/mark, or (None, None) if nothing can price it."""
    q = quote_fn(log=log) if quote_fn else None
    if q is not None:
        price, _age = q
        return float(price), "webull_quote"
    calib = _maybe_calibrate(state, ratio_fn, log=log)
    if calib and calib.get("ratio"):
        return float(nq_px) / float(calib["ratio"]), "nq_ratio"
    return None, None


def _apply_slippage(px, side, entering, slip):
    """slippage always moves the fill AGAINST us: worse price on entry, worse on exit."""
    buying = (side == "long") == entering  # buying to open long, or buying to cover short
    return px + slip if buying else px - slip


# -- lot lifecycle ---------------------------------------------------------------------
def _open_lot(state, cfg, leg, side, nq_qty, nq_px, qqq_px_raw, slip, log=print):
    shares = int(cfg["shares"].get(leg, 0))
    max_shares = int(cfg.get("max_shares_per_leg", shares))
    if shares > max_shares:
        _record_order(leg, "ENTER", side, shares, nq_px, None, None,
                      f"REFUSED shares {shares} > max_shares_per_leg {max_shares}", log)
        return
    if shares <= 0:
        return
    fill_px = _apply_slippage(qqq_px_raw, side, True, slip)
    state["legs"][leg] = {
        "leg": leg, "side": side, "shares_total": shares, "shares_remaining": shares,
        "nq_qty_total": nq_qty, "nq_qty_remaining": nq_qty,
        "entry_px": fill_px, "nq_entry_px": nq_px, "last_nq_px": nq_px,
        "entry_ts": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _record_order(leg, "ENTER", side, shares, nq_px, fill_px, state["_px_source"],
                 "signal entry", log)
    _notify(f"QQQ SHADOW {leg} {side} {shares} @ {fill_px:.2f}", "EDGELOG QQQ SHADOW", log)


def _reduce_lot(state, cfg, leg, nq_qty_closed, nq_px, qqq_px_raw, slip, reason, log=print):
    lot = state["legs"].get(leg)
    if not lot:
        log(f"[qqq-exec] WARN exit fill for {leg} with no open shadow lot -- skipped")
        return None
    lot["last_nq_px"] = nq_px
    frac = min(1.0, nq_qty_closed / lot["nq_qty_total"]) if lot["nq_qty_total"] else 1.0
    shares_close = round(lot["shares_total"] * frac)
    shares_close = min(shares_close, lot["shares_remaining"])
    lot["nq_qty_remaining"] = max(0, lot["nq_qty_remaining"] - nq_qty_closed)
    if lot["nq_qty_remaining"] <= 0:
        shares_close = lot["shares_remaining"]  # close any rounding dust on the final leg
    if shares_close <= 0:
        return None
    fill_px = _apply_slippage(qqq_px_raw, lot["side"], False, slip)
    lot["shares_remaining"] -= shares_close
    _record_order(leg, "EXIT", lot["side"], shares_close, nq_px, fill_px,
                 state["_px_source"], reason, log)
    _notify(f"QQQ SHADOW {leg} {reason.lower()} {shares_close} @ {fill_px:.2f}",
           "EDGELOG QQQ SHADOW", log)
    pnl = None
    if lot["shares_remaining"] <= 0:
        # close the round-trip on the full lot's entry (weighted avg exit unnecessary
        # for a single-entry lot -- see module docstring: entries are treated single-shot)
        pnl = _record_trade(lot, fill_px, reason)
        state["realized_pnl_today"] = round(state.get("realized_pnl_today", 0.0) + pnl, 2)
        del state["legs"][leg]
    return pnl


def _close_all(state, cfg, reason, quote_fn, ratio_fn, log=print):
    for leg in list(state["legs"].keys()):
        lot = state["legs"][leg]
        qqq_px, src = resolve_price(cfg, state, lot.get("last_nq_px") or lot["nq_entry_px"],
                                    quote_fn, ratio_fn, log=log)
        state["_px_source"] = src
        if qqq_px is None:
            log(f"[qqq-exec] cannot price {leg} for {reason} close -- no quote/ratio "
                f"available, lot left open")
            continue
        _reduce_lot(state, cfg, leg, lot["nq_qty_remaining"], lot.get("last_nq_px"),
                   qqq_px, cfg.get("slippage_per_share", 0.0), reason, log=log)


# -- fill routing ------------------------------------------------------------------------
def _route_fills(state, cfg, fills, quote_fn, ratio_fn, entries_blocked, log=print):
    """Walk NEW fills in file order, updating per-group position and opening/reducing
    shadow lots. Mirrors api.nt_sync.build_trades' adding/reducing FIFO logic.

    `entries_blocked` covers the reasons that depend on the ADAPTER'S current state
    (breaker tripped / feed stale / kill file) rather than the fill's own time --
    those apply to every fill regardless of when it happened. The session-window
    check (open/last_entry) is evaluated against the FILL'S OWN timestamp
    (f["dt"], NY-local per fills.csv), which is what a real 5s-tick adapter is
    equivalent to: by the time a fill shows up in the file it IS "now"."""
    groups = {}
    for f in fills:
        groups.setdefault((f["account"], f["instrument"]), []).append(f)
    for (account, instrument), grp in groups.items():
        grp.sort(key=lambda f: (f["dt"], f["_i"]))
        gk = _group_key(account, instrument)
        for f in grp:
            delta = f["qty"] if f["action"] == "BUY" else -f["qty"]
            side_of_fill = "long" if f["action"] == "BUY" else "short"
            leg_open = state["group_leg"].get(gk)
            opening = leg_open is None
            if opening:
                leg = _leg_from_signal(f.get("signal"))
                if leg is None:
                    log(f"[qqq-exec] WARN unattributable opening fill on {gk} "
                        f"(signal={f.get('signal')!r}) -- skipped")
                    continue
                if leg in state["legs"]:
                    log(f"[qqq-exec] WARN {leg} already has an open shadow lot -- "
                        f"second entry on {gk} ignored")
                    state["group_leg"][gk] = leg  # still track so exits route correctly
                    continue
                in_window = _in_entry_window(f["dt"], cfg["session"])
                if entries_blocked or not in_window:
                    reason = ("REFUSED -- outside entry window" if not in_window
                              else "REFUSED -- breaker/feed/kill blocked")
                    _record_order(leg, "ENTER", side_of_fill, cfg["shares"].get(leg, 0),
                                 f["price"], None, None, reason, log)
                    state["group_leg"][gk] = leg
                    continue
                qqq_px, src = resolve_price(cfg, state, f["price"], quote_fn, ratio_fn, log=log)
                state["_px_source"] = src
                if qqq_px is None:
                    log(f"[qqq-exec] cannot price {leg} entry -- no quote/ratio available, "
                        f"fill skipped")
                    continue
                _open_lot(state, cfg, leg, side_of_fill, abs(delta), f["price"], qqq_px,
                         cfg.get("slippage_per_share", 0.0), log=log)
                state["group_leg"][gk] = leg
            else:
                leg = leg_open
                qqq_px, src = resolve_price(cfg, state, f["price"], quote_fn, ratio_fn, log=log)
                state["_px_source"] = src
                if qqq_px is None:
                    log(f"[qqq-exec] cannot price {leg} exit -- no quote/ratio available, "
                        f"fill skipped (lot stays open)")
                    continue
                reason = "signal exit" if str(f.get("signal") or "").strip() else "close"
                _reduce_lot(state, cfg, leg, abs(delta), f["price"], qqq_px,
                           cfg.get("slippage_per_share", 0.0), reason, log=log)
                if leg not in state["legs"]:
                    state["group_leg"].pop(gk, None)


# -- mark-to-market + breaker ------------------------------------------------------------
def _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=print):
    unrl = 0.0
    for leg, lot in state["legs"].items():
        qqq_px, src = resolve_price(cfg, state, lot.get("last_nq_px") or lot["nq_entry_px"],
                                    quote_fn, ratio_fn, log=log)
        if qqq_px is None:
            continue
        side_mult = 1 if lot["side"] == "long" else -1
        unrl += (qqq_px - lot["entry_px"]) * side_mult * lot["shares_remaining"]
    total = state.get("realized_pnl_today", 0.0) + unrl
    limit = float(cfg.get("daily_loss_limit_usd", 0) or 0)
    if limit and total <= -abs(limit) and not state.get("breaker_tripped"):
        log(f"[qqq-exec] BREAKER TRIPPED: today's shadow P&L {total:.2f} <= "
            f"-{limit:.2f} -- closing all lots")
        _close_all(state, cfg, "BREAKER", quote_fn, ratio_fn, log=log)
        state["breaker_tripped"] = True
        _notify(f"QQQ SHADOW breaker tripped: {total:.2f} (limit -{limit:.2f})",
               "EDGELOG QQQ SHADOW BREAKER", log)
    return unrl


# -- feed staleness ------------------------------------------------------------------------
def _check_feed(state, fills_path, log=print):
    age, _version, _accts = nt_sync._addon_heartbeat(fills_path)
    stale = age is None or age > FEED_STALE_SEC
    was = state.get("feed_stale", False)
    state["feed_stale"] = stale
    if stale and (time.time() - float(state.get("last_feed_alert", 0) or 0)
                 > FEED_ALERT_COOLDOWN_SEC):
        _notify(f"NinjaTrader fill feed stale ({('%.0fs' % age) if age is not None else 'no heartbeat'}) "
               f"-- QQQ SHADOW is not opening new lots", "EDGELOG QQQ SHADOW: feed stale", log)
        state["last_feed_alert"] = time.time()
    elif not stale and was:
        log("[qqq-exec] feed heartbeat recovered")
    return stale


# -- Firestore publish ----------------------------------------------------------------------
def _build_doc(cfg, state, feed_stale, unrealized):
    orders = trades = []
    try:
        with open(ORDERS_CSV, encoding="utf-8", newline="") as f:
            orders = list(csv.DictReader(f))[-100:]
    except Exception:
        orders = []
    try:
        with open(TRADES_CSV, encoding="utf-8", newline="") as f:
            trades = list(csv.DictReader(f))[-100:]
    except Exception:
        trades = []
    positions = {}
    for leg, lot in state.get("legs", {}).items():
        positions[leg] = {"side": lot["side"], "shares": lot["shares_remaining"],
                          "entry_px": lot["entry_px"], "entry_ts": lot["entry_ts"]}
    return {
        "mode": cfg.get("mode"), "updated_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "feed_stale": bool(feed_stale), "breaker_tripped": bool(state.get("breaker_tripped")),
        "kill": bool(state.get("kill_done")), "calib": state.get("calib"),
        "positions": positions,
        "today": {"orders": orders, "trades": trades,
                  "realized_pnl": state.get("realized_pnl_today", 0.0),
                  "unrealized_pnl": round(unrealized, 2)},
        "rails": {"shares": cfg.get("shares"), "max_shares_per_leg": cfg.get("max_shares_per_leg"),
                  "daily_loss_limit_usd": cfg.get("daily_loss_limit_usd"),
                  "session": cfg.get("session"), "slippage_per_share": cfg.get("slippage_per_share")},
    }


def _publish(db, uid, doc, state, force=False, log=print):
    payload = json.dumps(doc, sort_keys=True, default=str)
    h = str(hash(payload))
    now = time.time()
    if not force and h == state.get("last_doc_hash") and now - state.get("last_publish", 0) < 60:
        return
    try:
        db.collection("users").document(uid).collection("meta").document("qqq_exec").set(doc)
        state["last_doc_hash"] = h
        state["last_publish"] = now
    except Exception as e:
        log(f"[qqq-exec] Firestore publish failed: {type(e).__name__}: {e}")


# -- one tick --------------------------------------------------------------------------------
def tick(*, fills_path=DEFAULT_FILLS, now=None, quote_fn=default_webull_quote,
         ratio_fn=default_ratio_calibration, cfg=None, state=None, force_calib=False,
         log=print):
    """Run one adapter pass. Returns (cfg, state, doc) for callers/tests. Loads/saves
    config+state from disk unless the caller supplies them (tests inject fixed state).

    `force_calib`: attempt the ratio calibration even outside the market window. The
    live thread leaves this False (outside 09:25-16:05 ET it must stay a cheap no-op,
    not a yfinance call every TICK_SEC all night) but `--once` verification runs pass
    True so a dry run away from market hours still demonstrates/exercises pricing."""
    cfg = cfg if cfg is not None else load_config(log=log)
    state = state if state is not None else load_state()
    nowdt = now or _now_et()
    today = nowdt.strftime("%Y-%m-%d")
    _roll_day(state, today)
    state["_px_source"] = None

    kill_present = os.path.exists(cfg.get("kill_file") or "")
    if kill_present and not state.get("kill_done"):
        log("[qqq-exec] KILL file present -- closing all shadow lots")
        _close_all(state, cfg, "KILL", quote_fn, ratio_fn, log=log)
        state["kill_done"] = True
        _notify("QQQ SHADOW: kill file present, all lots closed", "EDGELOG QQQ SHADOW KILL", log)
    elif not kill_present and state.get("kill_done"):
        state["kill_done"] = False
        log("[qqq-exec] kill file cleared")

    active = _in_market_window(nowdt)
    feed_stale = _check_feed(state, fills_path, log=log) if active else state.get("feed_stale", False)

    if (active or force_calib) and not kill_present:
        _maybe_calibrate(state, ratio_fn, log=log)

    if active and not kill_present:
        fills = nt_sync.parse_fills(fills_path)
        base_ok = lambda inst: nt_sync.get_base(inst) in ("NQ", "MNQ")
        processed = set(state.get("processed_ids") or [])
        new_fills = [f for f in fills if base_ok(f["instrument"]) and f["exec_id"] not in processed]
        new_fills.sort(key=lambda f: (f["dt"], f["_i"]))

        entries_blocked = (state.get("breaker_tripped") or feed_stale or kill_present)
        if new_fills:
            _route_fills(state, cfg, new_fills, quote_fn, ratio_fn, entries_blocked, log=log)
            for f in new_fills:
                processed.add(f["exec_id"])
            # cap the processed-id memory so state.json stays small
            state["processed_ids"] = list(processed)[-5000:]

        if _past_flat_by(nowdt, cfg["session"]) and state.get("flat_by_done_date") != today:
            if state.get("legs"):
                log("[qqq-exec] past flat_by -- closing remaining open lots")
                _close_all(state, cfg, "EOD", quote_fn, ratio_fn, log=log)
            state["flat_by_done_date"] = today

    unrealized = 0.0
    if not kill_present:
        unrealized = _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=log)

    doc = _build_doc(cfg, state, feed_stale, unrealized)
    save_state(state)
    return cfg, state, doc


def run_once(uid=None, fills_path=DEFAULT_FILLS, db=None, log=print):
    cfg, state, doc = tick(fills_path=fills_path, force_calib=True, log=log)
    log(f"[qqq-exec] tick complete: mode={cfg.get('mode')} feed_stale={doc['feed_stale']} "
        f"breaker={doc['breaker_tripped']} positions={list(doc['positions'].keys())} "
        f"realized={doc['today']['realized_pnl']} unrealized={doc['today']['unrealized_pnl']} "
        f"calib={doc.get('calib')}")
    if db is not None and uid:
        _publish(db, uid, doc, state, force=True, log=log)
        log(f"[qqq-exec] published users/{uid}/meta/qqq_exec")
    return doc


# -- runner thread hook (mirrors api.runner._bridge_watchdog_thread) ---------------------
def qqq_exec_thread(db, uids, stop=None, log=print):
    """Own thread, ticking every TICK_SEC -- never blocks the runner's main loop and
    never takes it down. Publishes to every allow-listed uid each tick that changed,
    at least once a minute regardless (see _publish's force/throttle logic)."""
    state = load_state()
    while stop is None or not stop.is_set():
        try:
            cfg = load_config(log=log)
            cfg2, state, doc = tick(cfg=cfg, state=state, log=log)
            for uid in uids:
                _publish(db, uid, doc, state, log=log)
            save_state(state)
        except Exception as e:
            log(f"[qqq-exec] tick failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        (stop.wait(TICK_SEC) if stop is not None else time.sleep(TICK_SEC))


# -- CLI ---------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run a single tick and exit")
    ap.add_argument("--uid", default=None, help="publish to users/{uid}/meta/qqq_exec")
    ap.add_argument("--fills", default=DEFAULT_FILLS)
    ap.add_argument("--cred", default=None, help="Firestore service-account json "
                                                  "(needed with --uid)")
    a = ap.parse_args()
    if not a.once:
        ap.print_help()
        return
    db = None
    if a.uid:
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                cred = credentials.Certificate(a.cred) if a.cred else credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
            db = firestore.client()
        except Exception as e:
            print(f"[qqq-exec] Firestore unavailable ({type(e).__name__}: {e}) -- "
                 f"running --once without publish")
    run_once(uid=a.uid, fills_path=a.fills, db=db)


if __name__ == "__main__":
    main()

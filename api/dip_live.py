"""api/dip_live.py -- DIP #424 ("KEEL DIP": run #424 = augur_strategies/NQDIP_1_1.py at its
validate champion) live on QQQ for the two NO-ORDER shadow legs DIP_424K (KEEL v12 learned)
and DIP_424F (constant size 1.245) -- api/cloud_signal.py SHADOW_LEGS, MANAGER #108 GO,
2026-10-09. Both legs write only to <state_dir>/shadow/signals.csv; nothing here can reach
an order.

THE STRATEGY FILE RUNS UNCHANGED. NQDIP_1_1.py is a registered research file (its LF sha256
is pinned by tests/test_dip424_shadow.py): every live adaptation lives in this module and
wraps the file, never edits it.

WHY NOT run_leg_trades. cloud_signal's generic runner unpacks five-field trades
(entry_bar, exit_bar, pnl_pts, side, entry_px) and rebuilds the exit price as
entry + pnl_pts * side. NQDIP_1_1.py returns SIX fields with the P&L in DOLLARS (PNL_UNITS
"usd", its own constant-notional size and costs) and the exit price as the sixth -- the
five-field unpack raises on it, and the rebuild would turn dollars into a price. Its trades
also appear only once they EXIT (a position still open when the data ends is dropped), and
up to seven mechanisms fill at the same session open. So a DIP leg is dispatched here
(cfg["runner"] == DIP_RUNNER, see cloud_signal.leg_decision_trades) and never reaches
run_leg_trades.

1. THE DAILY SERIES (build_daily_series). The file decides on the daily close and fills at
   the next session's open; it aggregates whatever master it gets to one bar per session
   and needs trend_len + 30 = 430 sessions before it trades at all (NQDIP_1_1.py:246 --
   it returns None below that, silently). The box's QQQ_5m.csv holds ~86 sessions, its
   QQQ_1d.csv ~1,265 daily rows (yfinance, 5 years). Per date:
     - a COMPLETE 5m session (first bar 09:30, last bar 5 minutes before
       market_calendar.session_close_et: 15:55, or 12:55 on a half day): open = first
       bar's open, high = max, low = min, close = last bar's close -- exactly the file's
       own aggregation of an RTH master (dc = close of the last RTH bar, NQDIP_1_1.py:250);
     - else the QQQ_1d row (official open/high/low/close; only ever feeds sessions older
       than the 5m cache: the 400-day trend average and the EMA/RSI/ATR warm-up);
     - else a PARTIAL 5m session (logged once a day per date).
   TODAY joins only once its 09:30 bar is in the 5m arrays (a bar the cache holds today
   but no 09:30 bar -> not ready, the REST tail normally fills it on a later fetch); before
   that the series simply ends at the previous session. QQQ_1d rows are read with
   _drop_unfinished_session_rows and dated by the ET date of their stamp (yfinance stamps
   00:00 ET -- never through build_arrays, whose RTH filter would drop every one); every
   row is used, with no rolling trim: fetch_and_merge_daily merges and never drops, so the
   series start is fixed and an old trade is never re-minted by a moving left edge. The 5m
   arrays are every cached session (warmup_sessions = DIP_5M_ALL_SESSIONS) so a date's
   source switches from QQQ_1d to 5m once, when its session first completes in the cache,
   and never back.
   ADJUSTMENT: QQQ_1d is yfinance auto_adjust=False (split-adjusted, no dividends); the 5m
   cache is Webull raw / yfinance auto_adjust=False / the Alpaca backfill (split-adjusted).
   QQQ has not split since 2000, so the scales agree; the CALIBRATION guard (median
   |5m close / 1d close - 1| and the same for opens over >= DIP_CAL_MIN_OVERLAP complete
   overlap sessions, each <= DIP_CAL_TOL, and EVERY overlap session's close and open within
   DIP_CAL_MAX_DAY -- the median alone forgets a split once most of the overlap is after it;
   checked whenever the series MIXES the two files) refuses the series if a split or an
   adjusted file ever breaks that. So does a SPLIT-SIZE GAP: any session opening outside
   DIP_SPLIT_GAP x the previous session's close (a split inside the raw 5m cache, caught
   whether or not QQQ_1d.csv can see it). Known small difference: raw QQQ gaps down on ex-dividend
   mornings (NQ does not) -- with gap_atr 0.0 GAPDN fires on any open at or below the
   prior close, so a few extra GAPDN signals a year are possible.
   NOT READY (None -> no diff and no SEED this tick, logged once per ET day per reason):
   fewer than trend_len + 30 sessions, the previous session missing from both sources,
   today's 09:30 bar missing, the calibration failing, or a HOLE: any session between the
   series' first and last date (market_calendar's sessions, minus UNSCHEDULED_CLOSURES) that
   is in neither file. The file indexes sessions by ROW, so a dropped session would shift
   every later row -- the 400-day trend average, ATR20, dbl_n, the time-only holds and the
   "decided at the <date> close" text -- with nothing looking wrong.

2. OPEN POSITIONS: THE PROBE (dip_positions). The file reports a trade only when it exits.
   So the series is run once per mechanism (one use_* flag on; the union is the all-on run
   exactly -- the seven loops are independent) with P = max(pb_hold, cap_hold, ibs_hold,
   streak_hold, gap_hold) + 2 PAD sessions appended whose open = high = low = close = the
   last real close x 1000 (volume 0). Every open position is forced out inside the pads
   (RSI/DBL/PB/STREAK/GAPDN on the first absurd close; CAP and IBS only by time -- with
   ibs_exit 1.0 the IBS exit can never fire, and a flat pad has IBS 0.5 -- hence P, not 2).
   With L the last REAL session: a trade with entry bar > L was signalled on the last real
   close and has not filled yet (skipped); exit bar > L means still open. Closed trades are
   the plain run's own (decisions at d <= L - 1 never see a pad). The engine is the shared
   wrapper, unchanged file, asset="ETF" (every setting is scale-free; "auto" would pick NQ
   micro costs and roll seams on intraday data). Long-only, so only the high probe is
   needed (api/etf_book_shadow.py _probe_arrays is the precedent).
   MEMO: nothing a trade with entry bar <= L shows depends on bar L's high/low/close (a
   decision at L fills inside the pads), so the result is memoized on (strategy, params,
   opens 0..L, highs/lows/closes 0..L-1, dates) -- both legs share one computation, and a
   session's later 5m bars cost nothing. A FAILED probe (DipTradeShapeError or any other
   exception) is memoized the same way and re-raised on a hit: the same inputs fail the same
   way, and rerunning all seven engine passes for every leg on every bar costs seconds a bar
   on the 1-CPU box. The next session's 09:30 bar is a new key, so it is retried then (or on
   a restart).

3. TRADE DICTS (trade_dicts): one per (mechanism, trade), the shape run_leg_trades returns
   plus "slot" (the mechanism -> api/trade_id.py's per-slot id, so seven trades on one bar
   are seven ids), "entry_note" / "exit_note" (the ledger reason) -- see trade_dicts. ENTRY
   = that session's 09:30 bar time at its open (the backtest fill); the live engine first
   sees the bar at its close (09:35:05), and says so in the reason. Only trades still open,
   or closed within the last DIP_DIFF_SESSIONS sessions, are handed to _diff_leg (else the
   SEED would absorb ~2.4 years of trades into state.json).
"""
import datetime as _dt
import hashlib
import json
import math

import numpy as np
import pandas as pd

from api import market_calendar

STRATEGY = "NQDIP_1_1.py"

# the hold knobs that bound how long a time-only exit can take (see 2. OPEN POSITIONS)
HOLD_KEYS = ("pb_hold", "cap_hold", "ibs_hold", "streak_hold", "gap_hold")
PROBE_PAD_EXTRA = 2

# Exchange closures market_calendar's rule table does not model (national days of mourning,
# 9/11, Hurricane Sandy): no file has a row for them, so they are never a HOLE. A future one
# reads as a hole (not ready, logged once a day) until it is added here.
UNSCHEDULED_CLOSURES = frozenset(_dt.date.fromisoformat(s) for s in (
    "2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14", "2004-06-11", "2007-01-02",
    "2012-10-29", "2012-10-30", "2018-12-05", "2025-01-09"))

_PROBE_MEMO = {}            # memo key -> tuple of positions, or a _ProbeFailed (see dip_positions)
_PROBE_MEMO_KEEP = 4
PROBE_STATS = {"runs": 0, "hits": 0}   # engine runs / memo hits -- read by the tests


def _cs():
    from api import cloud_signal as cs
    return cs


class DipTradeShapeError(Exception):
    """A probe trade that does not look like NQDIP_1_1.py's own 6-field long trade filled
    at a session open -- the whole call fails closed (no trades this tick)."""


class _ProbeFailed:
    """A memoized probe failure (see the module docstring, 2: MEMO)."""
    __slots__ = ("exc",)

    def __init__(self, exc):
        self.exc = exc


def _quiet(*_a, **_k):
    return None


def _et(now):
    cs = _cs()
    tz = cs._zi(cs.TZ)
    return now.astimezone(tz) if now.tzinfo is not None else now.replace(tzinfo=tz)


def _prev_session(d):
    p = d - _dt.timedelta(days=1)
    while not market_calendar.is_session(p):
        p -= _dt.timedelta(days=1)
    return p


def _close_minutes(d):
    hh, mm = (int(x) for x in market_calendar.session_close_et(d).split(":"))
    return hh * 60 + mm


# ── 1. the daily series ────────────────────────────────────────────────────────────────────
def five_min_sessions(arrays):
    """{date: session} for every session in the 5m `arrays` (cloud_signal.closed_arrays'
    shape): open (first bar's), high (max), low (min), close (last bar's), volume (sum),
    first_bar (its index into `arrays`), starts_at_open (first bar starts 09:30) and
    complete (also: last bar starts 5 minutes before the session close)."""
    if arrays is None or arrays.get("close") is None or not len(arrays["close"]):
        return {}
    cs = _cs()
    c = np.asarray(arrays["close"], float)
    n = len(c)
    o = np.asarray(arrays["open"], float)
    h = np.asarray(arrays["high"], float)
    lo = np.asarray(arrays["low"], float)
    v = arrays.get("volume")
    v = np.zeros(n) if v is None else np.nan_to_num(np.asarray(v, float))
    did = np.asarray(arrays["day_id"])
    idx = arrays["index"]
    starts = np.r_[0, np.flatnonzero(did[1:] != did[:-1]) + 1].astype(int)
    ends = np.r_[starts[1:], n].astype(int)
    hi = np.maximum.reduceat(h, starts)
    lw = np.minimum.reduceat(lo, starts)
    vol = np.add.reduceat(v, starts)
    open_min = cs.RTH_OPEN.hour * 60 + cs.RTH_OPEN.minute
    step_min = cs.TIMEFRAME_SECONDS["5m"] // 60
    out = {}
    for j, (a, b) in enumerate(zip(starts, ends)):
        first, last = idx[a], idx[b - 1]
        d = first.date()
        starts_at_open = first.hour * 60 + first.minute == open_min
        complete = bool(starts_at_open
                        and last.hour * 60 + last.minute + step_min == _close_minutes(d))
        out[d] = {"open": float(o[a]), "high": float(hi[j]), "low": float(lw[j]),
                  "close": float(c[b - 1]), "volume": float(vol[j]), "first_bar": int(a),
                  "starts_at_open": bool(starts_at_open), "complete": complete}
    return out


def daily_rows(paths, now, log=print):
    """{date: (open, high, low, close, volume)} from <ohlc_dir>/QQQ_1d.csv: finished sessions
    only (_drop_unfinished_session_rows), dated by the ET date of the row's stamp, the LAST
    row of a date kept, a row with a NaN or non-positive price dropped. {} when the file is
    missing or empty."""
    cs = _cs()
    df = cs.load_cached_bars("1d", paths)
    if df is None or not len(df):
        return {}
    df = cs._drop_unfinished_session_rows(df, now, log=log)
    if df is None or not len(df):
        return {}
    df = df.sort_values("time", kind="stable")
    dates = pd.to_datetime(df["time"].astype("int64"), unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    vols = df["volume"] if "volume" in df.columns else pd.Series(0.0, index=df.index)
    out = {}
    for d, o, h, lo, c, v in zip(dates, df["open"], df["high"], df["low"], df["close"], vols):
        try:
            px = (float(o), float(h), float(lo), float(c))
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(x) and x > 0 for x in px):
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            vf = 0.0
        out[d] = px + (vf if math.isfinite(vf) else 0.0,)
    return out


def missing_sessions(dates):
    """Sorted sessions between dates[0] and dates[-1] (market_calendar, minus
    UNSCHEDULED_CLOSURES) that are not in `dates` -- the series' HOLES."""
    if not dates:
        return []
    have = set(dates)
    return [d for d in market_calendar.sessions_between(dates[0], dates[-1])
            if d not in have and d not in UNSCHEDULED_CLOSURES]


def _session_open_index(dates):
    """Each date's 09:30 ET as one tz-aware DatetimeIndex (same isoformat as build_arrays')."""
    cs = _cs()
    base = pd.to_datetime([d.isoformat() for d in dates])
    return pd.DatetimeIndex(base + pd.Timedelta(hours=cs.RTH_OPEN.hour, minutes=cs.RTH_OPEN.minute)) \
        .tz_localize(cs.TZ)


def build_daily_series(arrays, now, paths, params, log=print):
    """(series, None) or (None, (reason_key, text)) -- see the module docstring, 1.
    `series`: {"arrays": the file's input (open/high/low/close/volume float64, day_id =
    arange(D), index = each session's 09:30 ET), "dates", "source" (per row: "5m", "1d" or
    "5m_partial"), "first_bar" ({date: 5m index of that session's 09:30 bar}), "L" (the last
    real session's index), "today" (True when row L is today's partial session), "overlap",
    "cal" ((median close diff, median open diff) or None), "n_5m", "n_1d"}. Never raises
    on missing data; logs a partial-5m date once a day."""
    cs = _cs()
    now = _et(now)
    today = now.date()
    five = five_min_sessions(arrays)
    daily = daily_rows(paths, now, log=log)
    t5 = five.get(today)
    if t5 is not None and not t5["starts_at_open"] and not (today in daily):
        return None, ("today_open", f"today's 09:30 bar is not in the 5m cache yet (its first "
                                    f"cached bar is later) -- waiting for it")
    dates = sorted(set(five) | set(daily))
    rows, sources = [], []
    for d in dates:
        s5, s1 = five.get(d), daily.get(d)
        if s5 is not None and s5["complete"]:
            rows.append((s5["open"], s5["high"], s5["low"], s5["close"], s5["volume"]))
            sources.append("5m")
        elif s1 is not None:
            rows.append(s1)
            sources.append("1d")
        else:
            rows.append((s5["open"], s5["high"], s5["low"], s5["close"], s5["volume"]))
            sources.append("5m_partial")
            if d != today:
                cs._log_fail_safe_once(
                    f"dip_partial:{d.isoformat()}",
                    f"[cloud-signal] DIP daily series: {d.isoformat()} has only a partial 5m "
                    f"session and no QQQ_1d row -- using the partial session", log)
    prev = _prev_session(today)
    if prev not in set(dates):
        return None, ("prev_missing", f"the previous session {prev.isoformat()} is in neither the "
                                      f"5m cache nor QQQ_1d.csv")
    holes = missing_sessions(dates)
    if holes:
        shown = ", ".join(d.isoformat() for d in holes[:5])
        more = f" (+{len(holes) - 5} more)" if len(holes) > 5 else ""
        return None, ("hole", f"session(s) {shown}{more} are in neither the 5m cache nor "
                              f"QQQ_1d.csv -- every later row would shift (trend average, ATR, "
                              f"holds, dates)")
    need = int(params.get("trend_len", 200)) + 30
    if len(dates) < need:
        return None, ("short", f"{len(dates)} daily session(s) (5m cache {len(five)}, QQQ_1d "
                               f"{len(daily)} row(s)); NQDIP_1_1.py needs >= {need}")
    overlap = [d for d in dates
               if d != today and d in daily and d in five and five[d]["complete"]]
    cal = worst = None
    if overlap:
        c_days = [abs(five[d]["close"] / daily[d][3] - 1.0) for d in overlap]
        o_days = [abs(five[d]["open"] / daily[d][0] - 1.0) for d in overlap]
        cal = (float(np.median(c_days)), float(np.median(o_days)))
        worst = max(zip(np.maximum(c_days, o_days), overlap))     # (|ratio - 1|, its date)
    if "1d" in sources and any(s != "1d" for s in sources):     # the two files are MIXED
        if len(overlap) < cs.DIP_CAL_MIN_OVERLAP:
            return None, ("cal_thin", f"only {len(overlap)} complete 5m session(s) also in QQQ_1d.csv "
                                      f"(< {cs.DIP_CAL_MIN_OVERLAP}) to check the two files' scales")
        if cal[0] > cs.DIP_CAL_TOL or cal[1] > cs.DIP_CAL_TOL:
            return None, ("cal_fail", f"QQQ_1d.csv does not match the 5m cache: median |close "
                                      f"ratio - 1| {cal[0] * 1e4:.1f} bp, |open ratio - 1| "
                                      f"{cal[1] * 1e4:.1f} bp over {len(overlap)} sessions "
                                      f"(tolerance {cs.DIP_CAL_TOL * 1e4:.1f} bp) -- a split "
                                      f"or an adjusted file?")
        if worst[0] > cs.DIP_CAL_MAX_DAY:
            return None, ("cal_split", f"QQQ_1d.csv does not match the 5m cache on "
                                       f"{worst[1].isoformat()}: |5m / 1d - 1| "
                                       f"{worst[0] * 1e4:.0f} bp, per-session bound "
                                       f"{cs.DIP_CAL_MAX_DAY * 1e4:.0f} bp (median "
                                       f"{max(cal) * 1e4:.1f} bp over {len(overlap)} sessions) "
                                       f"-- a split one file has and the other has not?")
    arr = np.asarray(rows, float)
    lo_gap, hi_gap = cs.DIP_SPLIT_GAP
    gap = arr[1:, 0] / arr[:-1, 3]
    jumps = np.flatnonzero((gap < lo_gap) | (gap > hi_gap))
    if len(jumps):
        i = int(jumps[-1]) + 1
        return None, ("cal_split", f"{dates[i].isoformat()} opens at {gap[i - 1]:.3f}x the "
                                   f"{dates[i - 1].isoformat()} close ({sources[i - 1]} -> "
                                   f"{sources[i]}; {len(jumps)} such gap(s)), outside "
                                   f"{lo_gap}..{hi_gap} -- a split in the raw data?")
    series_arrays = {"open": arr[:, 0].copy(), "high": arr[:, 1].copy(), "low": arr[:, 2].copy(),
                     "close": arr[:, 3].copy(), "volume": arr[:, 4].copy(),
                     "day_id": np.arange(len(dates), dtype="int64"),
                     "index": _session_open_index(dates)}
    first_bar = {d: s["first_bar"] for d, s in five.items() if s["starts_at_open"]}
    return {"arrays": series_arrays, "dates": dates, "source": sources, "first_bar": first_bar,
            "L": len(dates) - 1, "today": dates[-1] == today, "overlap": len(overlap),
            "cal": cal, "n_5m": len(five), "n_1d": len(daily)}, None


# ── 2. open positions: the probe ───────────────────────────────────────────────────────────
def probe_pads(params):
    """P = the longest time-only hold + PROBE_PAD_EXTRA (32 for #424: pb_hold 30)."""
    return max(int(params.get(k, 0) or 0) for k in HOLD_KEYS) + PROBE_PAD_EXTRA


def probe_arrays(series_arrays, pads):
    """`series_arrays` plus `pads` sessions at the last close x 1000 (o = h = l = c, volume 0,
    day_id continuing, index + 1 day each)."""
    a = series_arrays
    px = float(np.asarray(a["close"], float)[-1]) * 1000.0
    out = {k: np.concatenate([np.asarray(a[k], float), np.full(pads, px)])
           for k in ("open", "high", "low", "close")}
    out["volume"] = np.concatenate([np.asarray(a["volume"], float), np.zeros(pads)])
    out["day_id"] = np.arange(len(a["close"]) + pads, dtype="int64")
    last = a["index"][-1]
    out["index"] = a["index"].append(pd.DatetimeIndex([last + pd.Timedelta(days=i + 1)
                                                      for i in range(pads)]))
    return out


def _mechs(params):
    """[(mechanism, use_flag)] in the file's own order, the ones `params` switches on."""
    cs = _cs()
    return [(m, f) for m, f in cs.DIP_MECHS if bool(params.get(f, True))]


def _memo_key(strategy, params, series):
    a, L = series["arrays"], series["L"]
    h = hashlib.sha1()
    h.update(str(strategy).encode())
    h.update(json.dumps({k: params[k] for k in sorted(params)}, sort_keys=True, default=str).encode())
    h.update(np.ascontiguousarray(a["open"][:L + 1], dtype=float).tobytes())
    for k in ("high", "low", "close"):
        h.update(np.ascontiguousarray(a[k][:L], dtype=float).tobytes())
    h.update(",".join(d.isoformat() for d in series["dates"]).encode())
    return h.hexdigest()


def dip_positions(series, params, strategy=STRATEGY):
    """Every trade of every switched-on mechanism with entry bar <= L, as
    (mechanism, entry_bar, exit_bar or None while open, entry_px, exit_px or None) in
    series row indices, sorted by entry bar then the file's mechanism order. Memoized, a
    failure too (see the module docstring, 2). Raises DipTradeShapeError on a trade that is
    not the file's own long, filled at a session open."""
    key = _memo_key(strategy, params, series)
    hit = _PROBE_MEMO.get(key)
    if hit is not None:
        PROBE_STATS["hits"] += 1
        if isinstance(hit, _ProbeFailed):
            raise hit.exc.with_traceback(None)
        return list(hit)
    try:
        out = _probe(series, params, strategy)
    except Exception as e:
        _memo_put(key, _ProbeFailed(e))
        raise
    _memo_put(key, tuple(out))
    return out


def _memo_put(key, value):
    if len(_PROBE_MEMO) >= _PROBE_MEMO_KEEP:
        _PROBE_MEMO.pop(next(iter(_PROBE_MEMO)))
    _PROBE_MEMO[key] = value


def _probe(series, params, strategy):
    """dip_positions' computation, unmemoized: one engine pass per switched-on mechanism."""
    cs = _cs()
    a, L = series["arrays"], series["L"]
    opens = np.asarray(a["open"], float)
    probe = probe_arrays(a, probe_pads(params))
    mechs = _mechs(params)
    order = {m: i for i, (m, _f) in enumerate(cs.DIP_MECHS)}
    out = []
    for mech, flag in mechs:
        p = dict(params, asset="ETF")
        for _m, f in cs.DIP_MECHS:
            p[f] = (f == flag)
        res = cs.engine_run_backtest(strategy, arrays=probe, params=p, cost_pts=0.0,
                                     return_trades=True)
        PROBE_STATS["runs"] += 1
        for t in (res or {}).get("trades") or []:
            if len(t) < 6:
                raise DipTradeShapeError(f"{mech}: a {len(t)}-field trade (the file returns 6)")
            eb, xb = int(t[0]), int(t[1])
            if eb > L:
                continue          # signalled on the last real close: fills at a pad, not yet
            if int(t[3]) != 1 or float(t[4]) != float(opens[eb]):
                raise DipTradeShapeError(
                    f"{mech}: trade at row {eb} is side {t[3]} at {t[4]!r}, not a long filled "
                    f"at that session's open {float(opens[eb])!r}")
            if xb > L:
                out.append((mech, eb, None, float(t[4]), None))
            else:
                out.append((mech, eb, xb, float(t[4]), float(t[5])))
    out.sort(key=lambda r: (r[1], order.get(r[0], 99)))
    return out


# ── 3. trade dicts ─────────────────────────────────────────────────────────────────────────
def trade_dicts(positions, series, now, keep_sessions=None):
    """cloud_signal trade dicts for `positions` (dip_positions), one per (mechanism, trade):
      side "long"; entry_time / exit_time = the entry / exit session's 09:30 ET (the
      backtest fills at that open); entry_px = the file's own t[4] (that open), exit_px its
      t[5], both to 4 dp; exit_* None and still_open True while open; shares =
      floor(NOTIONAL_PER_LEG / entry_px) (run_leg_trades' rule); size 1.0 (the leg's KEEL
      block sizes it in _diff_leg); entry_bar = the 5m index of the entry session's 09:30
      bar (KEEL's feature row), None for a session older than the 5m cache (only ever a
      position carried at the seed, where KEEL is never scored); slot = the mechanism;
      entry_note / exit_note = the ledger reason.
    Only trades still open or closed within the last `keep_sessions` sessions
    (DIP_DIFF_SESSIONS) are returned -- every trade entered inside that window is among
    them -- sorted by entry time, then the file's mechanism order."""
    cs = _cs()
    keep = int(cs.DIP_DIFF_SESSIONS if keep_sessions is None else keep_sessions)
    now = _et(now)
    L, dates = series["L"], series["dates"]
    idx = series["arrays"]["index"]
    first_bar = series["first_bar"]
    seen = now.strftime("%H:%M")
    out = []
    for mech, eb, xb, epx, xpx in positions:
        if xb is not None and xb < L - keep + 1:
            continue
        d_in = dates[eb]
        shares = int(math.floor(cs.NOTIONAL_PER_LEG / epx)) if epx > 0 else 0
        decided = dates[eb - 1].isoformat() if eb >= 1 else "?"
        t = {
            "side": "long",
            "entry_time": idx[eb].isoformat(),
            "entry_px": round(epx, 4),
            "shares": max(shares, 0),
            "exit_time": None if xb is None else idx[xb].isoformat(),
            "exit_px": None if xb is None else round(xpx, 4),
            "still_open": xb is None,
            "size": 1.0,
            "entry_bar": first_bar.get(d_in),
            "slot": mech,
            "entry_note": (f"slot={mech}; decided at the {decided} close; filled at the "
                           f"{d_in.isoformat()} 09:30 open (the backtest fill, ref_price = that "
                           f"open); first seen {seen} ET (a session is first seen at its 09:30 "
                           f"bar's close, 09:35)"),
        }
        if xb is not None:
            t["exit_note"] = (f"slot={mech}; decided at the {dates[xb - 1].isoformat()} close, "
                              f"filled at the {dates[xb].isoformat()} 09:30 open")
        out.append(t)
    order = {m: i for i, (m, _f) in enumerate(cs.DIP_MECHS)}
    out.sort(key=lambda t: (t["entry_time"], order.get(t["slot"], 99)))
    return out


def run_dip_leg_trades(cfg, arrays, leg_key=None, now=None, paths=None, log=print):
    """A DIP leg's trade dicts for this tick (see the module docstring), or None when the
    daily series is not ready or the call failed -- step() then skips the leg's diff (no
    SEED either) and retries on the next new bar. Every reason is logged once per ET day.
    Never raises."""
    cs = _cs()
    label = cs._leg_label(cfg, leg_key)
    try:
        now = _et(now or _dt.datetime.now(tz=cs._zi(cs.TZ)))
        paths = paths or cs.DEFAULT_PATHS
        params = dict(cfg.get("params") or {})
        strategy = cfg.get("strategy") or STRATEGY
        series, why = build_daily_series(arrays, now, paths, params, log=log)
        if series is None:
            key, text = why
            cs._log_fail_safe_once(
                f"dip:{label}:{key}",
                f"[cloud-signal] {label}: DIP daily series not ready -- {text}; no trades this "
                f"tick (no diff, no SEED; retried on the next bar)", log)
            return None
        positions = dip_positions(series, params, strategy=strategy)
        return trade_dicts(positions, series, now)
    except Exception as e:
        cs._log_fail_safe_once(
            f"dip:{label}:error:{type(e).__name__}",
            f"[cloud-signal] {label}: DIP runner failed ({type(e).__name__}: {e}) -- no trades "
            f"this tick (no diff, no SEED)", log)
        return None


def history_line(key, cfg, paths, now=None):
    """log_history_windows' one line for a DIP leg: the daily series' length and sources, and
    whether it is ready. Never raises."""
    cs = _cs()
    try:
        now = _et(now or _dt.datetime.now(tz=cs._zi(cs.TZ)))
        params = dict(cfg.get("params") or {})
        need = int(params.get("trend_len", 200)) + 30
        epoch = cs.historical_bars(cfg.get("timeframe", "5m"), paths)
        arrays = None
        if epoch is not None and len(epoch):
            arrays = cs.closed_arrays(epoch, now, cfg.get("timeframe", "5m"),
                                      cs.leg_warmup_sessions(cfg))
        series, why = build_daily_series(arrays, now, paths, params, log=_quiet)
        if series is None:
            return (f"[cloud-signal] history window {key}: DIP daily series NOT READY -- {why[1]} "
                    f"(needs >= {need} daily sessions: QQQ_1d.csv for history plus the 5m "
                    f"cache's sessions)")
        src = series["source"]
        cal = series["cal"]
        return (f"[cloud-signal] history window {key}: DIP daily series {len(src)} session(s) "
                f"({src.count('5m')} from 5m, {src.count('1d')} from QQQ_1d.csv, "
                f"{src.count('5m_partial')} partial 5m; {series['dates'][0].isoformat()}.."
                f"{series['dates'][-1].isoformat()}) -- READY (needs >= {need})"
                + (f"; calibration over {series['overlap']} session(s): close "
                   f"{cal[0] * 1e4:.1f} bp, open {cal[1] * 1e4:.1f} bp" if cal else ""))
    except Exception as e:
        return (f"[cloud-signal] history window {key}: DIP daily series unknown "
                f"({type(e).__name__}: {e})")

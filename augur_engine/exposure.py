"""Run exposure: how much of the time a run is in the market, and its constant-exposure buy-and-hold twin.

WHY (MANAGER #41 phase 2, DISC's recipe #42). RSIDIV #163 looked great but was a leveraged buy-and-hold: in the market
96% of the sessions, 3.65 lots on average, 0.84x what a constant-exposure buy-and-hold of NQ would have made. The board
has to flag that kind of run and the run report has to show its buy-and-hold twin. The web cannot compute it (it needs
every trade and a price series), so tools/run_exposure.py computes it here and writes one small table the web reads.

This module is PURE: it takes the blotter rows and a series of session closes and returns plain numbers. No Firestore,
no files, no master registry. The reference implementation is C:/EdgeLog/_anatomy_cache/rsidiv_audit/twin_163.py.

THE RECIPE
- session close = the last bar close of each session (the caller passes one close per session; if it passes several
  stamps on the same date, the LAST one wins, as twin_163.py's groupby(...).last() does);
- lots[session] = lots held AT THAT SESSION'S CLOSE. A trade counts on every session from its entry session up to,
  NOT including, its exit session, so a trade entered and exited on the same session counts on none (an intraday run
  reads ~0 and is never flagged). One blotter row = one lot: the blotter has no size column;
- in market % = share of the sessions with lots > 0; mean lots (all) = mean over ALL sessions, zeros included; mean lots
  (in market) = mean over the sessions with lots > 0; max lots = the largest;
- median hold = median over trades of the number of sessions from the entry session to the exit session;
- twin points = mean lots (all) x (close on the last session - close on the first). NO cost on the twin;
- strategy points = the sum of the rows' pnl_pts (engine points, the cost is already in them);
  ratio = strategy / twin, null with a plain reason when the twin is not a positive number.

TIME ZONES. api/blotter.py writes entry_time / exit_time as the master's own exchange-local (America/New_York) clock,
with no offset ("2024-01-02 09:35"). A string that carries an offset or a Z ("2010-06-15 10:00:00-04:00", the RSIDIV
audit's trades_full.csv; "2024-01-04T01:30:00Z") is an instant: it is converted to America/New_York, then normalised
to its date. A bare string is already New York time and is NOT shifted (twin_163.py's utc=True would read it as UTC,
which only works there because every one of those stamps carries an offset). So 2024-01-04T01:30:00Z is 20:30 on Jan 3
in New York and belongs to the Jan 3 session.

SESSIONS WITH AN EVENING START. For an ETH futures run a trade entered at 18:30 belongs to the NEXT trading day (the CME
trade date). Pass roll_hour=18 and every stamp at or after 18:00 New York counts toward the next date, so an
overnight-only trade (18:30 to 09:45 the next morning) is a same-session trade and counts on no close. The default
(None) is the plain calendar date, which is right for RTH data.
"""
import math
import re

import numpy as np
import pandas as pd

NY = "America/New_York"

# a time of day followed by an offset or Z: the stamp is an instant, not a New York wall-clock reading. Requiring the
# time part keeps a bare date ("2024-01-02", which ends in "-02") from reading as a -02:00 offset.
_TZ_TAIL = re.compile(r"\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}:?\d{2})\s*$", re.I)


def _num(x, nd):
    """A JSON-safe float rounded to nd places, or None for NaN / inf / None."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def session_dates(values, roll_hour=None):
    """Session dates (numpy datetime64[D], NaT where a stamp cannot be read) for blotter time stamps.

    Offset-bearing strings and tz-aware datetimes are converted to America/New_York first; bare strings and naive
    datetimes are taken as New York wall-clock time already (see the module docstring). roll_hour (an int 0-23, e.g.
    18 for an ETH futures run) pushes every stamp at or after that hour to the next date."""
    n = len(values)
    naive = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    aware_i, aware_s, bare_i, bare_s = [], [], [], []
    for i, v in enumerate(values):
        if v is None or (isinstance(v, float) and v != v):
            continue
        if isinstance(v, str):
            s = v.strip()
            if not s:
                continue
            if _TZ_TAIL.search(s):
                aware_i.append(i)
                aware_s.append(s)
            else:
                bare_i.append(i)
                bare_s.append(s)
            continue
        try:
            t = pd.Timestamp(v)
        except (TypeError, ValueError):
            continue
        if pd.isna(t):
            continue
        if t.tzinfo is not None:
            t = t.tz_convert(NY).tz_localize(None)
        naive[i] = np.datetime64(t.to_datetime64(), "ns")
    if aware_s:
        ts = pd.to_datetime(aware_s, utc=True, errors="coerce", format="ISO8601")
        ts = ts.tz_convert(NY).tz_localize(None)
        naive[aware_i] = np.asarray(ts.values, dtype="datetime64[ns]")
    if bare_s:
        ts = pd.to_datetime(bare_s, errors="coerce", format="ISO8601")
        naive[bare_i] = np.asarray(ts.values, dtype="datetime64[ns]")
    idx = pd.DatetimeIndex(naive)
    if roll_hour is not None:
        idx = idx + pd.Timedelta(hours=24 - int(roll_hour))
    return idx.normalize().values.astype("datetime64[D]")


def _clean_closes(closes):
    """(days datetime64[D] ascending and unique, closes float array) from a date-indexed series, a {date: close}
    dict or a list of (date, close) pairs. Several stamps on one date collapse to the LAST one; NaN closes drop out."""
    if isinstance(closes, pd.Series):
        s = closes
    elif isinstance(closes, dict):
        s = pd.Series(list(closes.values()), index=list(closes.keys()))
    else:
        pairs = list(closes)
        s = pd.Series([p[1] for p in pairs], index=[p[0] for p in pairs])
    if len(s) == 0:
        raise ValueError("no session closes")
    idx = pd.DatetimeIndex(pd.to_datetime(s.index))
    if idx.tz is not None:
        idx = idx.tz_convert(NY).tz_localize(None)
    df = pd.DataFrame({"d": idx.normalize(), "t": idx, "c": pd.to_numeric(np.asarray(s.values), errors="coerce")})
    df = df.dropna()
    if df.empty:
        raise ValueError("no session closes")
    # a stable sort by the full stamp keeps "the last bar of the day" the last one even if the caller's order was off
    df = df.sort_values("t", kind="stable")
    last = df.groupby("d", sort=True)["c"].last()
    return last.index.values.astype("datetime64[D]"), last.values.astype(float)


def _prepare(rows, closes, roll_hour=None):
    """Everything exposure() and twin_curve() share: the clean session series, lots per session and per-trade arrays."""
    days, px = _clean_closes(closes)
    N = len(days)
    ent, ext, pnl = [], [], []
    for r in rows:
        g = r.get if hasattr(r, "get") else (lambda k, d=None, _r=r: getattr(_r, k, d))
        ent.append(g("entry_time"))
        ext.append(g("exit_time"))
        try:
            pnl.append(float(g("pnl_pts")))
        except (TypeError, ValueError):
            pnl.append(float("nan"))
    ed = session_dates(ent, roll_hour)
    xd = session_dates(ext, roll_hour)
    pnl = np.asarray(pnl, float)
    ok = ~np.isnat(ed) & ~np.isnat(xd) & np.isfinite(pnl)
    n_skipped = int((~ok).sum())
    ed, xd, pnl = ed[ok], xd[ok], pnl[ok]
    # first session on or after the date: the trade counts on sessions [pe, pxx) = entry date <= session < exit date
    pe = np.searchsorted(days, ed, side="left")
    pxx = np.maximum(np.searchsorted(days, xd, side="left"), pe)   # an exit before its entry holds nothing
    diff = np.zeros(N + 1, dtype=np.int64)
    np.add.at(diff, pe, 1)
    np.add.at(diff, pxx, -1)
    lots = np.cumsum(diff)[:N]
    inwin = (ed >= days[0]) & (ed <= days[-1])
    return {"days": days, "px": px, "N": N, "lots": lots, "pe": pe, "px_exit": pxx, "pnl": pnl,
            "inwin": inwin, "n_skipped": n_skipped}


def _d(day):
    return str(np.datetime_as_string(day, unit="D"))


def exposure(rows, closes, roll_hour=None):
    """The exposure table for one run as a JSON-safe dict.

    rows   = blotter dicts with entry_time, exit_time, pnl_pts (one row = one lot);
    closes = one close per session, date-indexed (a pandas Series, a {date: close} dict or (date, close) pairs).

    Keys: in_mkt_pct, lots_mean_all, lots_mean_in, lots_max, hold_med_sessions, n_trades, strat_pts, twin_pts, ratio,
    ratio_why (only when ratio is null), sessions, first, last; plus n_outside (trades that entered outside the
    sessions given - left out of n_trades / strat_pts / median hold) and n_skipped (rows with an unreadable time or
    pnl), each present only when it is not zero. The window is the closes' own first..last session: the caller slices
    the price series to the run's window."""
    P = _prepare(rows, closes, roll_hour)
    days, px, lots, N = P["days"], P["px"], P["lots"], P["N"]
    inw = P["inwin"]
    held = lots > 0
    lots_mean_all = float(lots.mean())
    lots_mean_in = float(lots[held].mean()) if held.any() else 0.0
    n_trades = int(inw.sum())
    strat = float(P["pnl"][inw].sum())
    hold = (P["px_exit"] - P["pe"])[inw]
    twin = lots_mean_all * float(px[-1] - px[0])
    ratio, why = None, None
    if N < 2:
        why = "fewer than 2 sessions - the twin has no price change to earn"
    elif lots_mean_all == 0.0:
        why = "flat at every session close - the twin holds nothing"
    elif twin < 0:
        why = "the twin lost points (the price fell over the window), so the ratio would flip sign"
    elif twin < 1e-6:
        why = "the twin earned about nothing (the price ended where it started)"
    else:
        ratio = strat / twin
    out = {
        "in_mkt_pct": _num(100.0 * float(held.mean()), 2),
        "lots_mean_all": _num(lots_mean_all, 4),
        "lots_mean_in": _num(lots_mean_in, 4),
        "lots_max": int(lots.max()),
        "hold_med_sessions": _num(np.median(hold), 1) if n_trades else None,
        "n_trades": n_trades,
        "strat_pts": _num(strat, 2),
        "twin_pts": _num(twin, 2),
        "ratio": _num(ratio, 4),
    }
    if ratio is None:
        out["ratio_why"] = why
    out.update({"sessions": int(N), "first": _d(days[0]), "last": _d(days[-1])})
    n_out = int(len(inw) - n_trades)
    if n_out:
        out["n_outside"] = n_out
    if P["n_skipped"]:
        out["n_skipped"] = int(P["n_skipped"])
    return out


def twin_curve(rows, closes, n=120, roll_hour=None):
    """The report's dashed line: a list of [YYYY-MM-DD, twin_pts_cum, strat_pts_cum], at most n points, always with the
    first and the last session.

    twin_cum(t) = mean lots (all) x (close_t - close_first); strat_cum(t) = the running sum of pnl_pts over the trades
    that exit on or before session t (the same trades exposure() counts, so the last point equals twin_pts and
    strat_pts)."""
    P = _prepare(rows, closes, roll_hour)
    days, px, lots, N = P["days"], P["px"], P["lots"], P["N"]
    mean_all = float(lots.mean())
    twin_cum = mean_all * (px - px[0])
    inw = P["inwin"]
    delta = np.zeros(N)
    np.add.at(delta, np.minimum(P["px_exit"][inw], N - 1), P["pnl"][inw])
    strat_cum = np.cumsum(delta)
    n = max(int(n), 2)
    pick = np.arange(N) if N <= n else np.unique(np.round(np.linspace(0, N - 1, n)).astype(int))
    return [[_d(days[i]), _num(twin_cum[i], 2), _num(strat_cum[i], 2)] for i in pick]

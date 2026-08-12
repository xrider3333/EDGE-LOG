"""Per-trade session candles — serve one trade's OHLCV bars + a VWAP overlay for the
web's candle modal (docs/VISUAL_TRADE_REPORT.md §3, Phase A). No Firestore dependency
here; the caller passes the payload. Kept dependency-light like api/blotter.py."""
import pandas as pd

from augur_engine.data import find_master, load_master_arrays


def _session_date(ts):
    """A pandas Timestamp/str -> date() for grouping bars into sessions."""
    return pd.Timestamp(ts).date()


def _bar_key(ts):
    """Normalize any timestamp-ish value to the 'YYYY-MM-DD HH:MM' comparison key."""
    return str(ts)[:16]


def _nearest_at_or_before(bars, ts):
    """Exact match on the first 16 chars of `ts` against each bar's `t`; else the
    nearest bar at-or-before it. `bars` must already be time-ascending. None if `ts`
    is falsy or every bar is after it."""
    if not ts:
        return None
    key = _bar_key(ts)
    for i, b in enumerate(bars):
        if b["t"] == key:
            return i
    best = None
    for i, b in enumerate(bars):
        if b["t"] <= key:
            best = i
        else:
            break
    return best


def _fresh_tail(timeframe, session, last_master_ts, log):
    """Bars the master does not have yet, resampled from the live 10s feed.

    The masters currently end 2026-07-16 while PAPER trades start 2026-08-11, so a
    paper trade has NO bars in any master. api/paper.py already solves this for the
    shadow engine — reuse its exact 10s loader/resampler/RTH filter so the candles a
    paper trade draws are built from the same bars the shadow run used. Returns a
    DataFrame (time/open/high/low/close/volume) of bars strictly AFTER
    `last_master_ts`, or None when there is no feed or nothing newer.
    """
    try:
        from api import paper as _paper
    except Exception as e:                                    # pragma: no cover
        log(f"    -> fresh tail unavailable ({type(e).__name__}: {e})")
        return None
    ticks, path = _paper._load_fresh_ticks()
    if ticks is None:
        log(f"    -> no live 10s feed at {path}")
        return None
    try:
        tf_min = int(str(timeframe).rstrip("m") or 5)
    except Exception:
        tf_min = 5
    bars = _paper._resample(ticks, tf_min)
    if session == "rth":
        bars, _et = _paper._filter_rth(bars)
    if bars is None or bars.empty:
        return None
    et = pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    bars = bars[et > pd.Timestamp(last_master_ts)].reset_index(drop=True)
    if bars.empty:
        return None
    log(f"    -> fresh tail: {len(bars)} {timeframe} bars past the master, from {path}")
    return bars


def load_session_bars(root, payload, log=print) -> dict:
    """Serve one trade's session candles to the web (get_bars runner command).

    payload: instrument, timeframe (default '5m'), session (default 'rth'), source
    (optional master pin), entry_time / exit_time ('YYYY-MM-DD HH:MM'-shaped strings),
    pad_sessions (int, default 1 — how many whole sessions of context to include on
    each side of the trade's own session), include_fresh (bool — append bars the
    master does not have yet from the live 10s feed; the PAPER tab needs this because
    paper trades are newer than any master).

    Resolution mirrors api/blotter.py's champion_blotter fallback chain: a source-pinned
    master first, then the plain instrument+timeframe+session match, then
    instrument+timeframe alone. Returns a json-safe
    {ok, bars, overlays: {vwap}, entry_idx, exit_idx, meta} dict, or {ok: False, error}.
    """
    instrument = payload.get("instrument")
    timeframe = payload.get("timeframe") or "5m"
    session = payload.get("session") or "rth"
    source = payload.get("source")
    entry_time = payload.get("entry_time")
    exit_time = payload.get("exit_time")
    pad_sessions = int(payload.get("pad_sessions") or 1)

    if not instrument or not entry_time:
        return {"ok": False, "error": "instrument and entry_time are required"}

    m = ((find_master(instrument, timeframe, session, source) if source else None)
         or find_master(instrument, timeframe, session) or find_master(instrument, timeframe))
    if not m:
        return {"ok": False, "error": f"no master for instrument={instrument} timeframe={timeframe}"}

    trade_date_str = str(entry_time)[:10]
    try:
        trade_date = _session_date(trade_date_str)
    except Exception:
        return {"ok": False, "error": f"could not parse entry_time date: {entry_time!r}"}

    # Pad by whole CALENDAR days (not sessions) so weekends/holidays can't starve the
    # session padding — pad_sessions+5 calendar days each side is comfortably enough
    # trading days for any pad_sessions in normal use.
    pad_days = pad_sessions + 5
    date_from = (pd.Timestamp(trade_date) - pd.Timedelta(days=pad_days)).strftime("%Y-%m-%d")
    date_to = (pd.Timestamp(trade_date) + pd.Timedelta(days=pad_days)).strftime("%Y-%m-%d")

    a = load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx = a["index"]

    n_fresh = 0
    if payload.get("include_fresh"):
        # the whole master decides where the tail starts, not the windowed slice
        full_last = load_master_arrays(m)["index"][-1]
        tail = _fresh_tail(timeframe, session, full_last, log)
        if tail is not None:
            tail_et = pd.to_datetime(tail["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
            keep = ((tail_et >= pd.Timestamp(date_from).tz_localize("US/Eastern")) &
                    (tail_et < (pd.Timestamp(date_to) + pd.Timedelta(days=1)).tz_localize("US/Eastern")))
            tail = tail[keep.values].reset_index(drop=True)
            if not tail.empty:
                if idx is None or len(idx) == 0:      # window is entirely past the master
                    a = {"index": pd.DatetimeIndex([], tz="US/Eastern"),
                         "open": [], "high": [], "low": [], "close": [], "volume": []}
                from api import paper as _paper
                a, n_fresh = _paper._append_fresh(a, tail)
                idx = a["index"]

    if idx is None or len(idx) == 0:
        return {"ok": False,
                "error": f"master '{m.get('name')}' has no bars in the padded window "
                         f"{date_from}..{date_to} around {trade_date_str}"
                         + ("" if payload.get("include_fresh") else
                            " (this trade may be newer than the master — the PAPER tab "
                            "asks for the live tail as well)")}

    o, h, l, c = a["open"], a["high"], a["low"], a["close"]
    v = a.get("volume")

    bar_dates = [_session_date(x) for x in idx]
    # Distinct session dates in the order they first appear — the arrays are time-
    # ascending, so this IS ascending chronological order.
    distinct_dates = list(dict.fromkeys(bar_dates))

    if trade_date not in distinct_dates:
        return {"ok": False,
                "error": f"trade date {trade_date_str} not found in master '{m.get('name')}' "
                         f"(padded window {date_from}..{date_to})"}

    center_i = distinct_dates.index(trade_date)
    lo_i = max(0, center_i - pad_sessions)
    hi_i = min(len(distinct_dates) - 1, center_i + pad_sessions)
    kept_dates = distinct_dates[lo_i:hi_i + 1]
    kept_set = set(kept_dates)

    # Group kept bar positions by session date (still time-ascending within + across
    # sessions, since kept_dates and each session's own bars are both ascending).
    by_session = {}
    for pos, d in enumerate(bar_dates):
        if d in kept_set:
            by_session.setdefault(d, []).append(pos)

    bars = []
    vwaps = []
    for d in kept_dates:
        positions = by_session.get(d, [])
        session_vol_total = sum(float(v[p]) for p in positions) if v is not None else 0.0
        no_vol = (v is None) or session_vol_total <= 0
        cum_pv = cum_v = 0.0
        for p in positions:
            bars.append({
                "t": _bar_key(idx[p]),
                "o": round(float(o[p]), 2),
                "h": round(float(h[p]), 2),
                "l": round(float(l[p]), 2),
                "c": round(float(c[p]), 2),
                "v": (int(v[p]) if v is not None else 0.0),
            })
            if no_vol:
                vwaps.append(None)
            else:
                vol = float(v[p])
                typ = (float(h[p]) + float(l[p]) + float(c[p])) / 3.0
                cum_pv += typ * vol
                cum_v += vol
                vwaps.append(round(cum_pv / cum_v, 2) if cum_v > 0 else None)

    entry_idx = _nearest_at_or_before(bars, entry_time)
    exit_idx = _nearest_at_or_before(bars, exit_time) if exit_time else None

    sessions_str = [d.strftime("%Y-%m-%d") for d in kept_dates]
    log(f"    -> bars served: {len(bars)} bars over sessions "
        f"{sessions_str[0]}..{sessions_str[-1]} from master '{m.get('name')}'")

    return {
        "ok": True,
        "bars": bars,
        "overlays": {"vwap": vwaps},
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
        "meta": {"master": m.get("name"), "source": m.get("source"),
                 "sessions": sessions_str, "n": len(bars), "n_fresh": n_fresh},
    }

"""BOOK-LEVEL SIZING - size every trade of a book by a multiplier read from the book's own past.

WHY (2026-10-03, frontier RISK r1). Book round 62's V2 rule - size each trade by how calm the
book's last 20 days were against its own trailing year - is the only structural change that has
beaten the adopted book #463 in BOTH stretches (BOOK.md 10o: WF 116.1 vs 92.7, LB 259.3 vs 164.8
%/yr at a $30k drawdown). It could not become a real, persisted run, because run_book had no way
to size a trade from the BOOK's state: a leg's `weight` is a constant and its `gate` block only
sees that leg. It has lived as a local harness figure and a nightly paper shadow (VT) instead.
This module is that missing feature. It is OFF unless a book job carries a `book_sizing` block,
and with no block run_book is bit-identical to before (tests/test_book_sizing.py).

HOW (two passes, nothing re-run):
  1. every leg runs exactly as it always has, UNSIZED; its trades are kept with the state needed
     to re-price them (book._leg_trades(..., keep_state=True));
  2. the unsized book's VALUED-DAILY P&L (book.mtm's series - V2 reads that one, not the at-close
     curve: 58b's dial on the at-close curve failed for exactly that reason, BOOK_ROUND58_ML 58b)
     gives one multiplier per day from days STRICTLY BEFORE it; every trade is then re-priced at
     the multiplier of its ENTRY day - its closed dollars, its session-day stamp and every daily
     mark - through the same formulas run_book already uses, so a trade's marks still sum to its
     closed dollars to the cent.

The entry day is the book's own day stamp of the fill bar (book._leg_trades: the US/Eastern
index truncated in UTC), the same clock the valued-daily series is indexed on, so "strictly
before the entry day" means the same thing on both sides.

Modes:
  vt   m(D) = clip(REF(D) / vol(D), lo, hi) rounded to `decimals`, where vol(D) = std of the book's
       unsized valued-daily P&L over the `lookback` index days before D and REF(D) = median of vol
       over the `ref` index days before that (min periods ref // 2). Defaults are round 62's V2,
       which is also the live VT shadow (api/book_shadow.py): 20 / 250 / 0.5 / 2.0 / 1 decimal.
       The index is every business day of the window plus every day that carries P&L or an entry
       (book_shadow's convention), zeros where nothing happened.

Options (all optional):
  legs     which legs are re-sized: a list of leg positions (0-based) and/or strategy file names.
           Default: every leg. Unselected legs run exactly as unsized.
  signal   "book" (default): the volatility is read on the WHOLE unsized book;
           "selected": only on the selected legs' unsized valued-daily P&L.
  stretches  [{"name", "from", "to"}]: the owner's yardstick (ROC %/yr at a $30k valued-daily
           drawdown, Sortino; house convention BOOK.md 10r) per named stretch, sized and unsized,
           so a persisted run reads WF / IS / LB directly. Each needs a name and tz-naive dates with
           from <= to, checked before any leg runs.

Refusals: a leg whose daily valuation failed, whose multi-day trades went unmarked, or that ran
on another master than the one it pins makes the block raise (signal_guard) - the signal would
otherwise quietly become the at-close curve, the reading round 58's dial failed on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VT_DEFAULTS = {"lookback": 20, "ref": 250, "lo": 0.5, "hi": 2.0, "decimals": 1}
MODES = ("vt",)


def check_config(cfg):
    """Validate a `book_sizing` block and return it with defaults filled in. Raises ValueError on
    anything it does not understand - a sizing block that silently ran UNSIZED would report the raw
    book under the sized book's name."""
    if not isinstance(cfg, dict):
        raise ValueError("book_sizing must be an object like {\"mode\": \"vt\"}, got %r" % (cfg,))
    mode = str(cfg.get("mode") or "").lower()
    if mode not in MODES:
        raise ValueError("book_sizing mode %r is not one of %s" % (cfg.get("mode"), ", ".join(MODES)))
    out = {"mode": mode}
    for k, v in VT_DEFAULTS.items():
        x = cfg.get(k, v)
        out[k] = int(x) if k in ("lookback", "ref", "decimals") else float(x)
    if out["lookback"] < 2 or out["ref"] < 2:
        raise ValueError("book_sizing lookback and ref must be >= 2")
    if not (0 < out["lo"] <= out["hi"]):
        raise ValueError("book_sizing needs 0 < lo <= hi")
    # The multiplier is clipped, then rounded (the live shadow's order). That keeps every value inside [lo, hi] only
    # when lo and hi sit on the rounding grid - decimals 0 would round a 0.5 floor to 0.0 (half to even) and size
    # trades to nothing (review 2026-10-03).
    if out["decimals"] < 1:
        raise ValueError("book_sizing decimals must be >= 1")
    for k in ("lo", "hi"):
        if round(out[k], out["decimals"]) != out[k]:
            raise ValueError("book_sizing %s=%s is not on the %d-decimal grid it is rounded to" % (k, out[k], out["decimals"]))
    sig = str(cfg.get("signal") or "book").lower()
    if sig not in ("book", "selected"):
        raise ValueError("book_sizing signal must be 'book' or 'selected'")
    out["signal"] = sig
    legs = cfg.get("legs")
    if legs is not None and not isinstance(legs, (list, tuple)):
        raise ValueError("book_sizing legs must be a list of leg positions or strategy names")
    if legs is not None and len(legs) == 0:
        raise ValueError("book_sizing legs is empty - nothing would be sized, and the raw book would run under a sized label")
    out["legs"] = list(legs) if legs is not None else None
    st = cfg.get("stretches")
    if st is not None:
        if not isinstance(st, (list, tuple)) or not all(isinstance(x, dict) and x.get("from") and x.get("to") for x in st):
            raise ValueError("book_sizing stretches must be a list of {\"name\", \"from\", \"to\"}")
        # Stretches are read only after every leg has run, so a bad one used to cost the whole book before it showed
        # (pre-run review round 2, 2026-10-03): each needs a name, two tz-naive dates (the book's day index is naive -
        # an aware bound raises mid-report) and from <= to (a reversed pair reads as an empty stretch, not an error).
        for i, x in enumerate(st):
            nm = x.get("name")
            if not isinstance(nm, str) or not nm.strip():
                raise ValueError("book_sizing stretch %d needs a non-empty string name, got %r" % (i, nm))
            ts = {}
            for k in ("from", "to"):
                v = x[k]
                if isinstance(v, (bool, int, float, np.number)):      # pd.Timestamp reads a number as ns since 1970
                    raise ValueError("book_sizing stretch %r %s=%r is a number, not a date" % (nm, k, v))
                try:
                    t = pd.Timestamp(v)
                except (ValueError, TypeError, OverflowError) as e:
                    raise ValueError("book_sizing stretch %r %s=%r is not a date (%s)" % (nm, k, v, e))
                if pd.isna(t):
                    raise ValueError("book_sizing stretch %r %s=%r is not a date" % (nm, k, v))
                if t.tz is not None:
                    raise ValueError("book_sizing stretch %r %s=%r carries a time zone - give a plain date, the book's "
                                     "day index is tz-naive" % (nm, k, v))
                ts[k] = t
            if ts["from"] > ts["to"]:
                raise ValueError("book_sizing stretch %r runs backwards: from %s is after to %s" % (nm, x["from"], x["to"]))
        names = [x["name"].strip() for x in st]
        if len(set(names)) != len(names):                             # readers look a stretch up by name and take the first
            raise ValueError("book_sizing stretch names must be unique, got %r" % names)
        st = [{"name": str(x.get("name") or ""), "from": str(x["from"]), "to": str(x["to"])} for x in st]
    out["stretches"] = st
    unknown = sorted(set(cfg) - set(out) - set(VT_DEFAULTS))
    if unknown:
        raise ValueError("book_sizing has unknown key(s): %s" % ", ".join(unknown))
    return out


def _vt_parts(M, lookback, ref):
    vol = M.shift(1).rolling(lookback, min_periods=lookback).std()
    rf = vol.shift(1).rolling(ref, min_periods=ref // 2).median()
    return vol, rf


def vt_multipliers(M, lookback=20, ref=250, lo=0.5, hi=2.0, decimals=1):
    """Round 62 V2 on a valued-daily book series indexed by day; the value at D uses only days before D.
    Same arithmetic as api/book_shadow.vt_multipliers (the live VT shadow) - a test holds them equal."""
    vol, rf = _vt_parts(M, lookback, ref)
    m = (rf / vol).clip(lo, hi)
    if decimals is not None:
        m = m.round(int(decimals))
    return m.fillna(1.0)


def warmup_rows(M, lookback=20, ref=250):
    """Rows at the start where V2 has no reference yet and so sizes at 1.0."""
    vol, rf = _vt_parts(M, lookback, ref)
    ok = (rf / vol).notna().to_numpy()
    return int(np.argmax(ok)) if ok.any() else len(M)


def selected_legs(cfg, legs):
    """Positions of the legs the block re-sizes."""
    want = cfg.get("legs")
    if want is None:
        return list(range(len(legs)))
    names = [str(l.get("strategy") or "") for l in legs]
    out = []
    for w in want:
        if isinstance(w, (int, np.integer)) and not isinstance(w, bool):
            if not 0 <= int(w) < len(legs):
                raise ValueError("book_sizing leg position %d is out of range (book has %d legs)" % (w, len(legs)))
            out.append(int(w))
        else:
            hits = [i for i, n in enumerate(names) if n == str(w)]
            if not hits:
                raise ValueError("book_sizing names leg %r, which is not in this book" % (w,))
            out.extend(hits)
    return sorted(set(out))


def entry_day(state, t):
    """The book's day stamp of a trade's fill bar (same clock as its exit / mark stamps)."""
    e = min(max(int(t[0]), 0), state["last"])
    return state["days_idx"][e]


def daily_series(incs, index_days=None):
    """[(day, $)] -> pandas Series summed by day, optionally reindexed (fill 0) on index_days."""
    if incs:
        d = pd.to_datetime(np.array([x[0] for x in incs], dtype="datetime64[D]"))
        s = pd.Series(np.array([x[1] for x in incs], dtype=float), index=d).groupby(level=0).sum()
    else:
        s = pd.Series(dtype=float)
    if index_days is not None:
        s = s.reindex(index_days).fillna(0.0)
    return s


def _day(x):
    """A window bound as a naive calendar day; a tz-aware one is read on the US/Eastern clock the masters use."""
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("US/Eastern").tz_localize(None)
    return t.normalize()


def book_index(incs_lists, date_from=None, date_to=None):
    """Business days of the window plus every day that carries P&L - exactly the index
    api/book_shadow.book463_valued_daily and tools/rocfrontier/r4_book463.py build. Entry days are
    NOT added: an extra zero row would move every 20-row window after it (see multiplier_on)."""
    days = []
    for incs in incs_lists:
        days.extend(x[0] for x in incs)
    have = pd.to_datetime(np.array(days, dtype="datetime64[D]")) if days else pd.DatetimeIndex([])
    lo = _day(date_from) if date_from else (have.min() if len(have) else None)
    hi = _day(date_to) if date_to else (have.max() if len(have) else None)
    base = pd.bdate_range(lo, hi) if lo is not None and hi is not None else pd.DatetimeIndex([])
    return base.union(pd.DatetimeIndex(have.unique()) if len(have) else pd.DatetimeIndex([])).sort_values()


def multipliers(cfg, unsized_mtm_lists, date_from=None, date_to=None):
    """(day-indexed multiplier Series on the book index, the unsized signal Series it was read from)."""
    idx = book_index(unsized_mtm_lists, date_from, date_to)
    M = sum((daily_series(incs, idx) for incs in unsized_mtm_lists), pd.Series(0.0, index=idx))
    m = vt_multipliers(M, cfg["lookback"], cfg["ref"], cfg["lo"], cfg["hi"], cfg["decimals"])
    return m, M


def multiplier_on(m, M, cfg, day):
    """The multiplier for a trade entering on `day`, from the rows strictly before it.

    A day on the index reads m there. A day OFF the index (an entry stamped on a day that carries no
    P&L and is not a business day - e.g. a Sunday-evening 24h fill) is what the live shadow computes
    by inserting that day with $0 (book_shadow.vt_multiplier_for): its window is every index row before
    it, which is exactly the window of the NEXT index row, so it reads that row's value. Past the last
    row it is computed directly the same way."""
    d = pd.Timestamp(day)
    if d in m.index:
        return float(m.loc[d])
    k = int(m.index.searchsorted(d, side="right"))
    if k < len(m):
        return float(m.iloc[k])
    M2 = pd.concat([M, pd.Series([0.0], index=pd.DatetimeIndex([d]))])
    return float(vt_multipliers(M2, cfg["lookback"], cfg["ref"], cfg["lo"], cfg["hi"], cfg["decimals"]).iloc[-1])


def resize(state, factor_of_trade):
    """Re-price one leg's trades at size x factor_of_trade(t). Returns (closed, session_day, mtm, sizes)
    through book's own formulas (the same _closed_series and _mtm_increments the unsized leg used)."""
    from . import book as _b
    sized = [(t, float(s) * float(factor_of_trade(t))) for t, s in state["sized"]]
    out, out_sess = _b._closed_series(sized, state["days_idx"], state["sess_idx"], state["last"],
                                      state["mult"], state["weight"])
    if state.get("mtm_failed"):
        mtm = list(out)
    else:
        mtm, _mk, _um = _b._mtm_increments(state["days_idx"], state["close"], sized, state["mult"],
                                           state["weight"], plugin_marks=state["plugin_marks"],
                                           usd_units=state["usd_units"])
    return out, out_sess, mtm, [f for _, f in sized]


def signal_guard(legs, leg_info, positions):
    """Refuse a signal the engine would otherwise degrade without a word. V2 reads the VALUED-DAILY
    series; a leg whose daily valuation failed, or whose multi-day trades went unmarked, falls back to
    exit-day dollars - the at-close reading that book round 58's dial failed on (BOOK_ROUND58_ML 58b).
    A leg that ran on another master than the one it pins is not the book the job names
    (api/book_shadow.book463_valued_daily refuses both for the live VT line, the same way)."""
    for k in positions:
        info, leg = leg_info[k], legs[k]
        name = info.get("strategy") or leg.get("strategy")
        if info.get("mtm_error"):
            raise ValueError("book_sizing: leg %s daily valuation failed (%s) - the signal would be the "
                             "at-close curve" % (name, info["mtm_error"]))
        if int(info.get("mtm_unmarked") or 0):
            raise ValueError("book_sizing: leg %s has %d multi-day trade(s) it could not value daily"
                             % (name, int(info["mtm_unmarked"])))
        if leg.get("source") and info.get("source") != leg.get("source"):
            raise ValueError("book_sizing: leg %s ran on source %r, the job pins %r"
                             % (name, info.get("source"), leg.get("source")))


def stretch_reading(daily, lo, hi):
    """The owner's yardstick on one stretch of a day-indexed valued-daily series (house convention
    2026-10-01, BOOK.md 10r): net over the rows in [lo, hi], drawdown from a peak that starts at 0,
    years = (last row - first row) / 365.25, ROC %/yr at a $30k drawdown = 30 x (net / years) / DD,
    Sortino = mean / sqrt(mean(min(x, 0)^2)) x sqrt(252) over every row."""
    z = daily[(daily.index >= pd.Timestamp(lo)) & (daily.index <= pd.Timestamp(hi))]
    if len(z) < 2:
        return None
    x = z.to_numpy(float)
    c = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c).max())
    yrs = (z.index[-1] - z.index[0]).days / 365.25
    dn = float(np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)))
    net = float(x.sum())
    return {"from": str(z.index[0].date()), "to": str(z.index[-1].date()), "net": round(net, 2),
            "max_drawdown": round(dd, 2),
            "roc_30k": round(30.0 * (net / yrs) / dd, 3) if dd > 0 and yrs > 0 else None,
            "sortino": round(float(x.mean() / dn * np.sqrt(252)), 4) if dn > 0 else None}


def apply(cfg, legs, leg_info, per_leg_mtm, date_from=None, date_to=None):
    """Re-size a book's legs. `leg_info[i]["_state"]` must hold each leg's re-pricing state and
    `per_leg_mtm[i]` its UNSIZED valued-daily increments. Returns (rebuilt, report) where rebuilt[i]
    is (closed, session_day, mtm) for a re-sized leg and None for an unselected one.
    cfg["stretches"] = [{"name", "from", "to"}] adds the yardstick per stretch, sized and unsized."""
    stretches = cfg.get("stretches")
    sel = selected_legs(cfg, legs)
    states = [i.get("_state") for i in leg_info]
    for k in sel:
        if states[k] is None:
            raise ValueError("book_sizing: leg %d has no re-pricing state" % k)
    sig = sel if cfg["signal"] == "selected" else list(range(len(legs)))
    signal_guard(legs, leg_info, sorted(set(sig) | set(sel)))
    m, M = multipliers(cfg, [per_leg_mtm[k] for k in sig], date_from, date_to)
    if len(m) and not (m.to_numpy(float) > 0).all():
        raise ValueError("book_sizing produced a non-positive multiplier")
    cache = {}

    def m_of(day):
        if day not in cache:
            cache[day] = multiplier_on(m, M, cfg, pd.Timestamp(day))
        return cache[day]

    rebuilt, report_legs, all_f = [], [], []
    for i, info in enumerate(leg_info):
        st = states[i]
        if i not in sel or st is None:
            rebuilt.append(None)
            continue
        out, out_sess, mtm, sizes = resize(st, lambda t, _st=st: m_of(entry_day(_st, t)))
        fac = [m_of(entry_day(st, t)) for t, _ in st["sized"]]
        all_f.extend(fac)
        rebuilt.append((out, out_sess, mtm))
        report_legs.append({"leg": i, "strategy": info.get("strategy"), "source": info.get("source"),
                            "trades": len(fac), "avg_multiplier": round(float(np.mean(fac)), 4) if fac else None,
                            "trades_up": int(sum(1 for f in fac if f > 1.0)),
                            "trades_down": int(sum(1 for f in fac if f < 1.0))})
    vals = m.to_numpy(float)
    warm = warmup_rows(M, cfg["lookback"], cfg["ref"])
    report = {"mode": cfg["mode"], "lookback": cfg["lookback"], "ref": cfg["ref"], "lo": cfg["lo"],
              "hi": cfg["hi"], "decimals": cfg["decimals"], "signal": cfg["signal"],
              "legs_sized": report_legs,
              "avg_multiplier_trades": round(float(np.mean(all_f)), 4) if all_f else None,
              "avg_multiplier_days": round(float(np.mean(vals)), 4) if len(vals) else None,
              "days_at_lo": int(np.sum(np.isclose(vals, cfg["lo"]))),
              "days_at_hi": int(np.sum(np.isclose(vals, cfg["hi"]))),
              "first_day": str(m.index[0].date()) if len(m) else None,
              "last_day": str(m.index[-1].date()) if len(m) else None,
              "first_sized_day": str(m.index[warm].date()) if warm < len(m) else None,
              "warmup_rows_at_1": int(warm),
              "rule": ("m(D) = clip(median of vol%d over the %d rows before / vol%d, %s, %s), rounded to %d "
                       "decimal(s), 1.0 until both exist; vol%d = std of the UNSIZED book's valued-daily P&L "
                       "over the %d rows strictly before D (rows = business days + days with P&L); each trade "
                       "sized at its entry day (the book's UTC-truncated stamp of the fill bar)"
                       % (cfg["lookback"], cfg["ref"], cfg["lookback"], cfg["lo"], cfg["hi"], cfg["decimals"],
                          cfg["lookback"], cfg["lookback"]))}
    if stretches:
        idx = book_index(per_leg_mtm, date_from, date_to)      # every leg's days, even when the signal reads a subset
        sized_lists = [rebuilt[k][2] if rebuilt[k] is not None else per_leg_mtm[k] for k in range(len(legs))]
        S = sum((daily_series(x, idx) for x in sized_lists), pd.Series(0.0, index=idx))
        R = sum((daily_series(x, idx) for x in per_leg_mtm), pd.Series(0.0, index=idx))
        report["stretches"] = [{"name": str(s.get("name") or "%s..%s" % (s["from"], s["to"])),
                                "sized": stretch_reading(S, s["from"], s["to"]),
                                "raw_twin": stretch_reading(R, s["from"], s["to"])} for s in stretches]
    return rebuilt, report

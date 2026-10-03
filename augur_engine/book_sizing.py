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
    sig = str(cfg.get("signal") or "book").lower()
    if sig not in ("book", "selected"):
        raise ValueError("book_sizing signal must be 'book' or 'selected'")
    out["signal"] = sig
    legs = cfg.get("legs")
    if legs is not None and not isinstance(legs, (list, tuple)):
        raise ValueError("book_sizing legs must be a list of leg positions or strategy names")
    out["legs"] = list(legs) if legs is not None else None
    unknown = sorted(set(cfg) - set(out) - set(VT_DEFAULTS))
    if unknown:
        raise ValueError("book_sizing has unknown key(s): %s" % ", ".join(unknown))
    return out


def vt_multipliers(M, lookback=20, ref=250, lo=0.5, hi=2.0, decimals=1):
    """Round 62 V2 on a valued-daily book series indexed by day; the value at D uses only days before D.
    Same arithmetic as api/book_shadow.vt_multipliers (the live VT shadow) - a test holds them equal."""
    vol = M.shift(1).rolling(lookback, min_periods=lookback).std()
    rf = vol.shift(1).rolling(ref, min_periods=ref // 2).median()
    m = (rf / vol).clip(lo, hi)
    if decimals is not None:
        m = m.round(int(decimals))
    return m.fillna(1.0)


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


def book_index(incs_lists, entry_days, date_from=None, date_to=None):
    """Business days of the window plus every day with P&L or an entry (book_shadow's index)."""
    days = []
    for incs in incs_lists:
        days.extend(x[0] for x in incs)
    days.extend(entry_days)
    have = pd.to_datetime(np.array(days, dtype="datetime64[D]")) if days else pd.DatetimeIndex([])
    lo = pd.Timestamp(date_from) if date_from else (have.min() if len(have) else None)
    hi = pd.Timestamp(date_to) if date_to else (have.max() if len(have) else None)
    base = pd.bdate_range(lo, hi) if lo is not None and hi is not None else pd.DatetimeIndex([])
    return base.union(pd.DatetimeIndex(have.unique()) if len(have) else pd.DatetimeIndex([])).sort_values()


def multipliers(cfg, unsized_mtm_lists, entry_days, date_from=None, date_to=None):
    """(day-indexed multiplier Series, the unsized signal Series it was read from)."""
    idx = book_index(unsized_mtm_lists, entry_days, date_from, date_to)
    M = sum((daily_series(incs, idx) for incs in unsized_mtm_lists), pd.Series(0.0, index=idx))
    m = vt_multipliers(M, cfg["lookback"], cfg["ref"], cfg["lo"], cfg["hi"], cfg["decimals"])
    return m, M


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


def apply(cfg, legs, leg_info, per_leg_mtm, date_from=None, date_to=None):
    """Re-size a book's legs. `leg_info[i]["_state"]` must hold each leg's re-pricing state and
    `per_leg_mtm[i]` its UNSIZED valued-daily increments. Returns (rebuilt, report) where rebuilt[i]
    is (closed, session_day, mtm) for leg i - unselected legs are returned unchanged."""
    sel = selected_legs(cfg, legs)
    states = [i.get("_state") for i in leg_info]
    for k in sel:
        if states[k] is None:
            raise ValueError("book_sizing: leg %d has no re-pricing state" % k)
    entries = []
    for k in sel:
        st = states[k]
        entries.extend(entry_day(st, t) for t, _ in st["sized"])
    sig_lists = [per_leg_mtm[k] for k in (sel if cfg["signal"] == "selected" else range(len(legs)))]
    m, M = multipliers(cfg, sig_lists, entries, date_from, date_to)
    m_by_day = {np.datetime64(d.date(), "D"): float(v) for d, v in m.items()}

    rebuilt, report_legs = [], []
    all_f = []
    for i, info in enumerate(leg_info):
        st = states[i]
        if i not in sel or st is None:
            rebuilt.append(None)
            continue
        out, out_sess, mtm, sizes = resize(st, lambda t, _st=st: m_by_day.get(entry_day(_st, t), 1.0))
        fac = [m_by_day.get(entry_day(st, t), 1.0) for t, _ in st["sized"]]
        all_f.extend(fac)
        rebuilt.append((out, out_sess, mtm))
        report_legs.append({"leg": i, "strategy": info.get("strategy"), "trades": len(fac),
                            "avg_multiplier": round(float(np.mean(fac)), 4) if fac else None})
    vals = m.to_numpy(float)
    report = {"mode": cfg["mode"], "lookback": cfg["lookback"], "ref": cfg["ref"], "lo": cfg["lo"],
              "hi": cfg["hi"], "decimals": cfg["decimals"], "signal": cfg["signal"],
              "legs_sized": report_legs,
              "avg_multiplier_trades": round(float(np.mean(all_f)), 4) if all_f else None,
              "avg_multiplier_days": round(float(np.mean(vals)), 4) if len(vals) else None,
              "days_at_lo": int(np.sum(np.isclose(vals, cfg["lo"]))),
              "days_at_hi": int(np.sum(np.isclose(vals, cfg["hi"]))),
              "first_day": str(m.index[0].date()) if len(m) else None,
              "last_day": str(m.index[-1].date()) if len(m) else None,
              "rule": ("m(D) = clip(median of vol%d over the %d days before / vol%d, %s, %s), rounded to %d "
                       "decimal(s); vol%d = std of the UNSIZED book's valued-daily P&L over the %d days "
                       "strictly before D; each trade sized at its entry day"
                       % (cfg["lookback"], cfg["ref"], cfg["lookback"], cfg["lo"], cfg["hi"], cfg["decimals"],
                          cfg["lookback"], cfg["lookback"]))}
    return rebuilt, report

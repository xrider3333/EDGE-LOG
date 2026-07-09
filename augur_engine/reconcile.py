"""Blotter reconciliation core — EDGELOG engine vs TradingView / NinjaTrader.

Streamlit-free, importable by the runner, the tests, and the tools/reconcile.py CLI.
Turns an engine run into a normalized blotter and diffs it, trade-for-trade, against a
TradingView "List of Trades" CSV or a NinjaTrader Strategy Analyzer export:
  • tolerant CSV parsing (fuzzy headers; TV's two-rows-per-trade + NT's semicolon/currency),
  • automatic tz/DST offset detection (an ET-vs-UTC shift is not read as "all mismatched"),
  • one-to-one entry-time matching,
  • a diagnosis engine that names the systematic cause of a gap (fees, ETH-vs-RTH extras,
    contract-roll price offset, 1-bar entry shift, side flips).

`run_reconcile(...)` is the high-level entry the runner calls: it takes the strategy/window
+ the exported CSV *text* and returns a JSON-safe result dict (summary + diagnosis + rows).
See tools/reconcile.py for the CLI and ORB.md §7-8 for the failure-mode rap sheet.
"""
import io
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# Point multipliers ($ per point per contract) — mirror optimizer.INSTRUMENTS.
MULT = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "RTY": 50, "M2K": 5,
        "YM": 5, "MYM": 0.5, "CL": 1000, "MCL": 100, "GC": 100, "MGC": 10}

# Candidate whole-hour offsets (minutes) to try when aligning the two blotters. Covers
# ET<->UTC (±240 EDT / ±300 EST), a 1-hour DST slip (±60), and exchange/CT shifts (±120).
CAND_OFFSETS_MIN = [0, 60, -60, 120, -120, 180, -180, 240, -240, 300, -300, 360, -360]


# ── Normalized trade schema (entry_dt/exit_dt are tz-NAIVE wall clocks) ──────────
@dataclass
class Trade:
    entry_dt: Optional[pd.Timestamp]
    exit_dt: Optional[pd.Timestamp]
    side: int = 0          # +1 long, -1 short, 0 unknown
    qty: float = 1.0
    entry_px: Optional[float] = None
    exit_px: Optional[float] = None
    pnl_usd: Optional[float] = None
    raw: dict = field(default_factory=dict)


def _num(x):
    """Parse a messy numeric cell: '$1,234.50', '(50.00)'→-50, '1.2%'→1.2, '—'→None."""
    if x is None:
        return None
    if isinstance(x, (int, float, np.floating, np.integer)):
        return None if (isinstance(x, float) and np.isnan(x)) else float(x)
    s = str(x).strip()
    if s in ("", "—", "-", "n/a", "N/A", "nan", "NaN", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "").replace("−", "-").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _to_dt(x):
    """Flexible datetime parse → tz-naive Timestamp (drops any tz to a wall clock)."""
    ts = pd.to_datetime(x, errors="coerce")
    if ts is None or (isinstance(ts, float) and np.isnan(ts)) or pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None or getattr(ts, "tz", None) is not None:
        ts = ts.tz_localize(None)
    return ts


def _find_col(cols, *needles, avoid=()):
    """First column whose lowered header contains ALL `needles` and none of `avoid`."""
    low = {c: str(c).lower() for c in cols}
    for c in cols:
        h = low[c]
        if all(n in h for n in needles) and not any(a in h for a in avoid):
            return c
    return None


def _find_pnl(cols):
    """The net-$ PnL column: TV 'Net PnL USD', older TV 'Profit USD', NT 'Profit'.
    Prefer the USD/$ variant; never the % or cumulative column."""
    for needle in ("pnl", "p&l", "profit"):
        c = _find_col(cols, needle, "usd", avoid=("%", "cum")) or _find_col(cols, needle, "$", avoid=("%", "cum"))
        if c:
            return c
    for needle in ("pnl", "p&l", "profit"):
        c = _find_col(cols, needle, avoid=("%", "cum"))
        if c:
            return c
    return None


def _df_from_text(text):
    """Parse CSV text (delimiter sniffed) → DataFrame, stripping a leading BOM."""
    if text and text[:1] == "﻿":
        text = text[1:]
    return pd.read_csv(io.StringIO(text), sep=None, engine="python")


# ── Source parsers (DataFrame → trades) ─────────────────────────────────────────
def parse_tv_df(df, mult=1):
    """TradingView 'List of Trades' → (list[Trade], meta). Two rows/trade (Entry + Exit)
    share a Trade #; PnL is on the exit row. Columns matched by fuzzy header lookup."""
    cols = list(df.columns)
    c_num = _find_col(cols, "trade") or cols[0]
    c_type = _find_col(cols, "type")
    c_dt = _find_col(cols, "date") or _find_col(cols, "time")
    c_px = _find_col(cols, "price")
    c_qty = (_find_col(cols, "position", "size") or _find_col(cols, "contract")
             or _find_col(cols, "qty") or _find_col(cols, "quantity"))
    c_pnl = _find_pnl(cols)
    if c_type is None or c_dt is None:
        raise ValueError(f"TV parse: could not find Type/Date columns in {cols}")
    groups = {}
    for _, row in df.iterrows():
        tnum = row.get(c_num)
        typ = str(row.get(c_type, "")).lower()
        rec = dict(dt=_to_dt(row.get(c_dt)), px=_num(row.get(c_px)) if c_px else None,
                   qty=_num(row.get(c_qty)) if c_qty else None,
                   pnl=_num(row.get(c_pnl)) if c_pnl else None)
        g = groups.setdefault(tnum, {})
        if "entry" in typ:
            g["entry"] = rec
            g["side"] = 1 if "long" in typ else (-1 if "short" in typ else 0)
        elif "exit" in typ:
            g["exit"] = rec
    trades = []
    for tnum, g in groups.items():
        en, ex = g.get("entry"), g.get("exit")
        if not en:
            continue
        trades.append(Trade(entry_dt=en.get("dt"), exit_dt=(ex or {}).get("dt"),
                            side=g.get("side", 0), qty=(en.get("qty") or 1.0),
                            entry_px=en.get("px"), exit_px=(ex or {}).get("px"),
                            pnl_usd=(ex or {}).get("pnl"), raw={"trade_no": tnum}))
    trades = [t for t in trades if t.entry_dt is not None]
    trades.sort(key=lambda t: t.entry_dt)
    return trades, {"source": "TradingView", "num_trades": len(trades),
                    "cols": {"pnl": c_pnl, "price": c_px, "qty": c_qty}}


def parse_nt_df(df, mult=1):
    """NinjaTrader Strategy Analyzer trades → (list[Trade], meta). One row/trade."""
    cols = list(df.columns)
    c_side = _find_col(cols, "market", "pos") or _find_col(cols, "position") or _find_col(cols, "direction")
    c_qty = _find_col(cols, "quantity") or _find_col(cols, "qty")
    c_epx = _find_col(cols, "entry", "price")
    c_xpx = _find_col(cols, "exit", "price")
    c_edt = _find_col(cols, "entry", "time") or _find_col(cols, "entry", "date")
    c_xdt = _find_col(cols, "exit", "time") or _find_col(cols, "exit", "date")
    c_pnl = _find_pnl(cols)
    if c_edt is None:
        raise ValueError(f"NT parse: could not find an Entry time column in {cols}")
    trades = []
    for _, row in df.iterrows():
        sd = str(row.get(c_side, "")).lower() if c_side else ""
        side = 1 if "long" in sd else (-1 if "short" in sd else 0)
        trades.append(Trade(
            entry_dt=_to_dt(row.get(c_edt)),
            exit_dt=_to_dt(row.get(c_xdt)) if c_xdt else None,
            side=side, qty=(_num(row.get(c_qty)) if c_qty else 1.0) or 1.0,
            entry_px=_num(row.get(c_epx)) if c_epx else None,
            exit_px=_num(row.get(c_xpx)) if c_xpx else None,
            pnl_usd=_num(row.get(c_pnl)) if c_pnl else None, raw={}))
    trades = [t for t in trades if t.entry_dt is not None]
    trades.sort(key=lambda t: t.entry_dt)
    return trades, {"source": "NinjaTrader", "num_trades": len(trades),
                    "cols": {"side": c_side, "pnl": c_pnl, "entry_time": c_edt}}


def parse_tv_text(text, mult=1):
    return parse_tv_df(_df_from_text(text), mult)


def parse_nt_text(text, mult=1):
    return parse_nt_df(_df_from_text(text), mult)


# ── Windowing, offset detection, matching ───────────────────────────────────────
def clip_window(trades, date_from=None, date_to=None):
    """Keep only trades whose ENTRY falls in [date_from, date_to] (date_to inclusive)."""
    if not (date_from or date_to):
        return trades
    lo = pd.Timestamp(date_from) if date_from else None
    hi = (pd.Timestamp(date_to) + pd.Timedelta(days=1)) if date_to else None
    out = []
    for t in trades:
        e = t.entry_dt
        if e is None:
            continue
        if lo is not None and e < lo:
            continue
        if hi is not None and e >= hi:
            continue
        out.append(t)
    return out


def _coverage(a, b, offset_min, tol_min):
    off = pd.Timedelta(minutes=offset_min)
    tol = pd.Timedelta(minutes=tol_min)
    bt = [t.entry_dt for t in b]
    return sum(1 for ta in a if any(abs(ta.entry_dt + off - tb) <= tol for tb in bt))


def best_offset(a, b, tol_min):
    """Whole-hour offset (minutes, applied to side A) that aligns the most trades; also
    tries the empirical median nearest-neighbour delta to catch odd offsets."""
    if not a or not b:
        return 0
    cands = list(CAND_OFFSETS_MIN)
    bt = [t.entry_dt for t in b]
    deltas = [min((tb - ta.entry_dt for tb in bt), key=lambda x: abs(x)).total_seconds() / 60.0
              for ta in a]
    if deltas:
        med = int(round(float(np.median(deltas))))
        if med not in cands:
            cands.append(med)
    scored = sorted(((_coverage(a, b, off, tol_min), -abs(off), off) for off in cands), reverse=True)
    return scored[0][2]


def match(a, b, offset_min, tol_min):
    """Greedy one-to-one match on entry time (a shifted by offset). Closest pairs first.
    Returns (matched:[(ta, tb, dt_min)], unmatched_a, unmatched_b)."""
    off = pd.Timedelta(minutes=offset_min)
    tol = pd.Timedelta(minutes=tol_min)
    pairs = []
    for i, ta in enumerate(a):
        ea = ta.entry_dt + off
        for j, tb in enumerate(b):
            d = abs(ea - tb.entry_dt)
            if d <= tol:
                pairs.append((d, i, j))
    pairs.sort(key=lambda x: x[0])
    used_a, used_b, matched = set(), set(), []
    for d, i, j in pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i); used_b.add(j)
        dt_min = ((a[i].entry_dt + off) - b[j].entry_dt).total_seconds() / 60.0
        matched.append((a[i], b[j], dt_min))
    unmatched_a = [ta for i, ta in enumerate(a) if i not in used_a]
    unmatched_b = [tb for j, tb in enumerate(b) if j not in used_b]
    matched.sort(key=lambda m: m[0].entry_dt)
    return matched, unmatched_a, unmatched_b


def _rth_flag(ts):
    """True if a timestamp is INSIDE the RTH cash session (09:30–16:00 ET wall clock)."""
    if ts is None:
        return None
    t = ts.time()
    return (t >= pd.Timestamp("09:30").time()) and (t <= pd.Timestamp("16:00").time())


# ── Diagnosis ───────────────────────────────────────────────────────────────────
def diagnose(matched, unmatched_a, unmatched_b, offset_min, a_label, b_label, tol_min):
    out = []
    n_m = len(matched)
    if offset_min:
        h = offset_min / 60.0
        out.append(("TIMEZONE", f"{a_label} entry times are {b_label} {'+' if offset_min>0 else '-'}"
                    f"{abs(h):g}h. Auto-aligned before matching (a whole-hour tz/DST shift, "
                    f"not a logic gap)."))
    if n_m:
        dts = np.array([m[2] for m in matched])
        med_dt = float(np.median(dts))
        if abs(med_dt) >= 0.5 and np.std(dts) < max(1.0, tol_min * 0.3):
            out.append(("ENTRY-BAR", f"Every matched entry is {med_dt:+.1f} min apart (tight cluster) "
                        f"→ a fixed one-bar entry-convention difference (e.g. fill at next bar's open), "
                        f"not random noise."))
    flips = [(m[0], m[1]) for m in matched if m[0].side and m[1].side and m[0].side != m[1].side]
    if flips:
        out.append(("SIDE-FLIP", f"{len(flips)} matched trades disagree on direction (long vs short) "
                    f"→ knife-edge opening-range boundary: a 1-tick data difference flips the break."))
    pnl_pairs = [(m[0].pnl_usd, m[1].pnl_usd) for m in matched
                 if m[0].pnl_usd is not None and m[1].pnl_usd is not None]
    if pnl_pairs:
        d = np.array([x - y for x, y in pnl_pairs])
        md, sd = float(np.median(d)), float(np.std(d))
        if abs(md) >= 1.0 and sd < max(3.0, abs(md) * 0.5):
            near_fee = ""
            for fee in (5.66, 5.0, 4.0, 2.83, 2.0):
                if abs(abs(md) - fee) < 0.75:
                    near_fee = f" ≈ ${fee}/trade — consistent with commission+slippage applied on one side only"
                    break
            out.append(("FEES", f"{a_label} nets {md:+.2f} $/trade vs {b_label} (tight, σ=${sd:.2f}){near_fee}. "
                        f"Run the EDGELOG side with the platform's per-round-turn cost to close it."))
        elif abs(md) >= 1.0:
            out.append(("PNL-SCATTER", f"Per-trade PnL differs by {md:+.2f} $/trade on average but scatters "
                        f"(σ=${sd:.2f}) → not a flat fee; look at fill prices / stop-fill assumptions."))
    px_pairs = [(m[0].entry_px, m[1].entry_px) for m in matched
                if m[0].entry_px is not None and m[1].entry_px is not None]
    if px_pairs:
        d = np.array([x - y for x, y in px_pairs])
        md, sd = float(np.median(d)), float(np.std(d))
        if abs(md) >= 1.0 and sd < max(2.0, abs(md) * 0.4):
            out.append(("PRICE-OFFSET", f"Entry prices sit a constant {md:+.2f} pts apart (σ={sd:.2f}) → the two "
                        f"feeds are on different contracts / back-adjustment (continuous vs a dated contract). "
                        f"Pick a window mid-cycle, away from a quarterly roll."))
    for extras, who, other in ((unmatched_a, a_label, b_label), (unmatched_b, b_label, a_label)):
        if not extras:
            continue
        eth = [t for t in extras if _rth_flag(t.entry_dt) is False]
        msg = f"{len(extras)} trade(s) in {who} have no match in {other}."
        if eth and len(eth) >= max(1, len(extras) // 2):
            msg += (f" {len(eth)} of them are OUTSIDE 09:30–16:00 ET → {who} is including "
                    f"extended-hours (ETH) bars; the other side is RTH-only.")
        out.append(("UNMATCHED", msg))
    if not out and n_m:
        out.append(("CLEAN", "No systematic offset found — the two blotters agree within tolerance."))
    return out


# ── Structured result (JSON-safe) ───────────────────────────────────────────────
def _sum_pnl(trades):
    v = [t.pnl_usd for t in trades if t.pnl_usd is not None]
    return float(sum(v)) if v else None


def _fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M") if ts is not None else None


def build_result(a, a_meta, b, b_meta, offset_min, tol_min):
    """Diff two blotters → a JSON-safe dict (summary + diagnosis + per-trade rows)."""
    matched, un_a, un_b = match(a, b, offset_min, tol_min)
    a_label, b_label = a_meta.get("source", "A"), b_meta.get("source", "B")
    dts = [m[2] for m in matched]
    dpnls = [m[0].pnl_usd - m[1].pnl_usd for m in matched
             if m[0].pnl_usd is not None and m[1].pnl_usd is not None]
    tot_a, tot_b = _sum_pnl(a), _sum_pnl(b)
    rows = []
    for k, (ta, tb, dt) in enumerate(matched, 1):
        dpnl = (ta.pnl_usd - tb.pnl_usd) if (ta.pnl_usd is not None and tb.pnl_usd is not None) else None
        dpx = (ta.entry_px - tb.entry_px) if (ta.entry_px is not None and tb.entry_px is not None) else None
        rows.append({"n": k, "entry": _fmt(ta.entry_dt),
                     "side": ("L" if ta.side > 0 else "S" if ta.side < 0 else "?"),
                     "flip": bool(ta.side and tb.side and ta.side != tb.side),
                     "a_pnl": ta.pnl_usd, "b_pnl": tb.pnl_usd,
                     "dpnl": dpnl, "dt_min": dt, "dpx": dpx})
    def _un(lst):
        return [{"entry": _fmt(t.entry_dt), "side": int(t.side), "pnl": t.pnl_usd} for t in lst[:60]]
    return {
        "a_source": a_label, "b_source": b_label,
        "summary": {
            "a_trades": len(a), "b_trades": len(b), "matched": len(matched),
            "unmatched_a": len(un_a), "unmatched_b": len(un_b),
            "total_a": tot_a, "total_b": tot_b,
            "total_delta": (tot_a - tot_b) if (tot_a is not None and tot_b is not None) else None,
            "offset_min": int(offset_min),
            "median_dt_min": float(np.median(dts)) if dts else None,
            "median_dpnl": float(np.median(dpnls)) if dpnls else None,
        },
        "diagnosis": [{"tag": t, "msg": m} for t, m in
                      diagnose(matched, un_a, un_b, offset_min, a_label, b_label, tol_min)],
        # cap the row detail so a multi-thousand-trade run can't blow Firestore's 1 MB doc
        # limit; the summary counts above stay exact.
        "matched": rows[:500], "matched_total": len(rows),
        "unmatched_a": _un(un_a), "unmatched_b": _un(un_b),
        "meta": {"a": a_meta, "b": b_meta, "tol_min": tol_min},
    }


# ── EDGELOG blotter + high-level entry point ────────────────────────────────────
def edgelog_blotter(strategy, instrument, timeframe, session, params, *,
                    date_from=None, date_to=None, cost_pts=0.0, mult=None):
    """Run the EDGELOG engine and return (list[Trade], meta)."""
    from .data import find_master, load_master_arrays
    from .engine import run_backtest
    mult = mult if mult is not None else MULT.get(str(instrument).upper(), 1)
    master = find_master(instrument, timeframe, session)
    if master is None:
        raise ValueError(f"No master CSV for {instrument} {timeframe} {session}.")
    arr = load_master_arrays(master, date_from=date_from, date_to=date_to)
    res = run_backtest(strategy, arrays=arr, params=params, cost_pts=cost_pts, return_trades=True)
    idx, O = arr["index"], arr["open"]
    trades = []
    for t in ((res or {}).get("trades") or []):
        eb, xb, pnl_pts = int(t[0]), int(t[1]), float(t[2])
        side = int(t[3]) if len(t) >= 4 else 0
        entry_px = float(t[4]) if len(t) >= 5 else float(O[eb])
        exit_px = (entry_px + side * pnl_pts) if side else None
        trades.append(Trade(entry_dt=pd.Timestamp(idx[eb]).tz_localize(None),
                            exit_dt=pd.Timestamp(idx[xb]).tz_localize(None),
                            side=side, qty=1.0, entry_px=entry_px, exit_px=exit_px,
                            pnl_usd=pnl_pts * mult,
                            raw={"entry_bar": eb, "exit_bar": xb, "pnl_pts": pnl_pts}))
    meta = {"source": "EDGELOG", "strategy": str(strategy), "instrument": instrument,
            "timeframe": timeframe, "session": session, "mult": mult,
            "master": master["filename"], "bars": int(len(arr["close"])),
            "num_trades": (res or {}).get("num_trades"), "cost_pts": cost_pts,
            "window": (str(idx[0]), str(idx[-1])) if len(idx) else (None, None)}
    return trades, meta


def run_reconcile(strategy, *, instrument, timeframe="5m", session="rth", params=None,
                  date_from=None, date_to=None, cost_pts=0.0, tv_text=None, nt_text=None,
                  tol_min=10.0, mult=None):
    """High-level entry for the runner: run the engine, parse the pasted TV/NT export
    text, and return a JSON-safe result per platform. Windows both sides to date_from/to."""
    mult = mult if mult is not None else MULT.get(str(instrument).upper(), 1)
    a, a_meta = edgelog_blotter(strategy, instrument, timeframe, session, params or {},
                                date_from=date_from, date_to=date_to, cost_pts=cost_pts, mult=mult)
    out = {"edgelog": {"num_trades": len(a), "master": a_meta.get("master"),
                       "window": a_meta.get("window")}, "platforms": {}}
    for key, text, parser in (("tradingview", tv_text, parse_tv_text),
                              ("ninjatrader", nt_text, parse_nt_text)):
        if not text or not str(text).strip():
            continue
        b, b_meta = parser(text, mult)
        b = clip_window(b, date_from, date_to)
        b_meta["num_trades"] = len(b)
        off = best_offset(a, b, tol_min)
        out["platforms"][key] = build_result(a, a_meta, b, b_meta, off, tol_min)
    return out

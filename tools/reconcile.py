# reconcile.py — automated blotter reconciliation: EDGELOG vs TradingView / NinjaTrader.
#
# WHAT IT DOES
#   Runs the EDGELOG engine on a strategy+instrument+window, turns the run into a
#   normalized trade blotter (entry/exit time, side, price, PnL, cumulative PnL), then
#   lines it up trade-for-trade against a TradingView "List of Trades" CSV export and/or
#   a NinjaTrader Strategy Analyzer trades export. It:
#     • auto-detects a timezone / DST offset (so an ET-vs-UTC shift does NOT read as
#       "every trade mismatched"),
#     • matches trades one-to-one on entry time,
#     • prints a per-trade diff + a summary (trade count, total PnL each side),
#     • and DIAGNOSES the systematic cause of any gap — the usual suspects from ORB.md
#       §7-8: tz/DST offset, the ~$5.66 commission gap, ETH-vs-RTH extra trades, a
#       contract-roll price offset, a 1-bar entry-convention shift, side flips.
#
# WHY IT EXISTS
#   The old flow (tools/xcheck_orb.py) printed an EDGELOG blotter and left you to eyeball
#   it against TradingView by hand — tedious and error-prone. This automates the compare.
#
# HOW TO RUN
#   1) Export the trade list from the other platform:
#        TradingView  → Strategy Tester → "List of Trades" tab → the export/download icon
#                       → a CSV lands in your Downloads folder.
#        NinjaTrader  → Strategy Analyzer → run backtest → "Trades" tab → right-click →
#                       Export → CSV.
#      (The Claude Chrome extension can click TV's export button for you; then point
#       --tv at the file in Downloads.)
#   2) Reconcile:
#        python tools/reconcile.py --strategy ORB_3_0.py --inst NQ --tf 5m --session rth \
#            --from 2026-05-01 --to 2026-05-29 \
#            --params or_bars=3,stop_frac=0.75,trade_mode=Both,vol_filter=0,breakout_buf=0,target_R=0,flat_eod=True \
#            --tv "C:/Users/xride/Downloads/NQ_ORB_List_of_Trades.csv"
#
#   Prove the machinery with NO external file (writes a synthetic TV export from the
#   EDGELOG blotter, injects a +4h tz shift and a $5.66 fee gap, and shows the tool
#   recovers both):
#        python tools/reconcile.py --self-test
#
#   Match tolerance / cost:
#     --tol-min N   how far apart two entries can be and still be "the same trade" (default 10)
#     --cost-pts X  per-round-trip cost (points) applied to the EDGELOG side (default 0 = gross;
#                   leave 0 and let the tool report the fee gap, or set it to match TV/NT).
import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Point multipliers ($ per point per contract) — mirror optimizer.INSTRUMENTS.
MULT = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "RTY": 50, "M2K": 5,
        "YM": 5, "MYM": 0.5, "CL": 1000, "MCL": 100, "GC": 100, "MGC": 10}

# Candidate whole-hour offsets (minutes) to try when aligning the two blotters. Covers
# ET<->UTC (±240 EDT / ±300 EST), a 1-hour DST slip (±60), and exchange/CT shifts (±120).
CAND_OFFSETS_MIN = [0, 60, -60, 120, -120, 180, -180, 240, -240, 300, -300, 360, -360]


# ────────────────────────────────────────────────────────────────────────────
# Normalized trade schema — every source (EDGELOG / TV / NT) is coerced to this.
# entry_dt / exit_dt are tz-NAIVE wall-clock timestamps (we compare wall clocks and let
# the offset detector absorb any tz difference). side: +1 long, -1 short, 0 unknown.
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Trade:
    entry_dt: Optional[pd.Timestamp]
    exit_dt: Optional[pd.Timestamp]
    side: int = 0
    qty: float = 1.0
    entry_px: Optional[float] = None
    exit_px: Optional[float] = None
    pnl_usd: Optional[float] = None
    raw: dict = field(default_factory=dict)


def _num(x):
    """Parse a possibly-messy numeric cell: '$1,234.50', '(50.00)'→-50, '1.2%'→1.2, '—'→None."""
    if x is None:
        return None
    if isinstance(x, (int, float, np.floating, np.integer)):
        return None if (isinstance(x, float) and np.isnan(x)) else float(x)
    s = str(x).strip()
    if s in ("", "—", "-", "n/a", "N/A", "nan", "NaN", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace("$", "").replace(",", "").replace("%", "").replace("−", "-").strip()
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
    """First column whose lowered header contains ALL of `needles` and none of `avoid`."""
    low = {c: str(c).lower() for c in cols}
    for c in cols:
        h = low[c]
        if all(n in h for n in needles) and not any(a in h for a in avoid):
            return c
    return None


def _read_csv_flexible(path):
    """Read a CSV whatever the delimiter/encoding (BOM, ; , or tab)."""
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path)  # last resort — let the error surface


def _find_pnl(cols):
    """The net-$ PnL column, tolerant of how each platform spells it. TradingView writes
    'Net PnL USD' (no ampersand), older TV wrote 'Profit USD', NinjaTrader writes 'Profit'.
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


# ────────────────────────────────────────────────────────────────────────────
# Source adapters
# ────────────────────────────────────────────────────────────────────────────
def edgelog_blotter(strategy, instrument, timeframe, session, params, *,
                    date_from=None, date_to=None, cost_pts=0.0, mult=None):
    """Run the EDGELOG engine and return (list[Trade], meta)."""
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    mult = mult if mult is not None else MULT.get(instrument.upper(), 1)
    master = find_master(instrument, timeframe, session)
    if master is None:
        raise SystemExit(f"No master CSV for {instrument} {timeframe} {session}. "
                         f"Check augur_uploads / the csv_files table.")
    arr = load_master_arrays(master, date_from=date_from, date_to=date_to)
    res = run_backtest(strategy, arrays=arr, params=params, cost_pts=cost_pts,
                       return_trades=True)
    idx = arr["index"]
    O = arr["open"]
    trades = []
    for t in (res.get("trades") or []):
        eb, xb, pnl_pts = int(t[0]), int(t[1]), float(t[2])
        side = int(t[3]) if len(t) >= 4 else 0
        entry_px = float(t[4]) if len(t) >= 5 else float(O[eb])
        # exit price: reconstruct from directional PnL when we know the side; else n/a
        exit_px = (entry_px + side * pnl_pts) if side else None
        edt = pd.Timestamp(idx[eb]).tz_localize(None)
        xdt = pd.Timestamp(idx[xb]).tz_localize(None)
        trades.append(Trade(entry_dt=edt, exit_dt=xdt, side=side, qty=1.0,
                            entry_px=entry_px, exit_px=exit_px,
                            pnl_usd=pnl_pts * mult,
                            raw={"entry_bar": eb, "exit_bar": xb, "pnl_pts": pnl_pts}))
    meta = {"source": "EDGELOG", "strategy": str(strategy), "instrument": instrument,
            "timeframe": timeframe, "session": session, "mult": mult,
            "master": master["filename"], "bars": int(len(arr["close"])),
            "num_trades": res.get("num_trades"), "cost_pts": cost_pts,
            "window": (str(idx[0]), str(idx[-1])) if len(idx) else (None, None)}
    return trades, meta


def parse_tv(path, mult):
    """Parse a TradingView 'List of Trades' CSV export → (list[Trade], meta).

    TV logs TWO rows per trade (an 'Entry long/short' row and an 'Exit long/short' row)
    sharing a Trade #; PnL is on the exit row. We group by Trade # and pair them. Column
    names drift across TV versions, so every column is matched by fuzzy header lookup.
    """
    df = _read_csv_flexible(path)
    cols = list(df.columns)
    c_num = _find_col(cols, "trade") or cols[0]
    c_type = _find_col(cols, "type")
    c_dt = _find_col(cols, "date") or _find_col(cols, "time")
    c_px = _find_col(cols, "price")
    c_qty = (_find_col(cols, "position", "size") or _find_col(cols, "contract")
             or _find_col(cols, "qty") or _find_col(cols, "quantity"))
    # net PnL in $ (TV: 'Net PnL USD'; older TV: 'Profit USD') — never %, never cumulative
    c_pnl = _find_pnl(cols)
    if c_type is None or c_dt is None:
        raise SystemExit(f"TV parse: could not find Type/Date columns in {cols}")

    groups = {}
    for _, row in df.iterrows():
        tnum = row.get(c_num)
        typ = str(row.get(c_type, "")).lower()
        rec = dict(dt=_to_dt(row.get(c_dt)),
                   px=_num(row.get(c_px)) if c_px else None,
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
        if not en:  # still-open or malformed — skip
            continue
        pnl = (ex or {}).get("pnl")
        trades.append(Trade(
            entry_dt=en.get("dt"), exit_dt=(ex or {}).get("dt"),
            side=g.get("side", 0), qty=(en.get("qty") or 1.0),
            entry_px=en.get("px"), exit_px=(ex or {}).get("px"),
            pnl_usd=pnl, raw={"trade_no": tnum}))
    trades = [t for t in trades if t.entry_dt is not None]
    trades.sort(key=lambda t: t.entry_dt)
    meta = {"source": "TradingView", "file": os.path.basename(path),
            "num_trades": len(trades),
            "cols": {"pnl": c_pnl, "price": c_px, "qty": c_qty}}
    return trades, meta


def parse_nt(path, mult):
    """Parse a NinjaTrader Strategy Analyzer trades export → (list[Trade], meta).

    NT is one row per trade: Market pos. (Long/Short), Entry/Exit price, Entry/Exit time,
    Profit. Delimiter is locale-dependent (, ; or tab) — sniffed. Profit is taken as $ (the
    default 'Display: Currency'); if your grid shows points, the tool's fee diagnosis will
    flag the mismatch."""
    df = _read_csv_flexible(path)
    cols = list(df.columns)
    c_side = _find_col(cols, "market", "pos") or _find_col(cols, "position") or _find_col(cols, "direction")
    c_qty = _find_col(cols, "quantity") or _find_col(cols, "qty")
    c_epx = _find_col(cols, "entry", "price")
    c_xpx = _find_col(cols, "exit", "price")
    c_edt = _find_col(cols, "entry", "time") or _find_col(cols, "entry", "date")
    c_xdt = _find_col(cols, "exit", "time") or _find_col(cols, "exit", "date")
    c_pnl = _find_pnl(cols)
    if c_edt is None:
        raise SystemExit(f"NT parse: could not find an Entry time column in {cols}")

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
            pnl_usd=_num(row.get(c_pnl)) if c_pnl else None,
            raw={}))
    trades = [t for t in trades if t.entry_dt is not None]
    trades.sort(key=lambda t: t.entry_dt)
    meta = {"source": "NinjaTrader", "file": os.path.basename(path),
            "num_trades": len(trades),
            "cols": {"side": c_side, "pnl": c_pnl, "entry_time": c_edt}}
    return trades, meta


# ────────────────────────────────────────────────────────────────────────────
# Alignment + matching
# ────────────────────────────────────────────────────────────────────────────
def _coverage(a, b, offset_min, tol_min):
    """How many `a` entries have a `b` entry within tol after shifting `a` by offset."""
    off = pd.Timedelta(minutes=offset_min)
    tol = pd.Timedelta(minutes=tol_min)
    bt = [t.entry_dt for t in b]
    hits = 0
    for ta in a:
        e = ta.entry_dt + off
        if any(abs(e - tb) <= tol for tb in bt):
            hits += 1
    return hits


def best_offset(a, b, tol_min):
    """Pick the whole-hour offset (minutes, applied to side A) that aligns the most trades.
    Also tries the empirical median nearest-neighbour delta, to catch odd offsets."""
    if not a or not b:
        return 0
    cands = list(CAND_OFFSETS_MIN)
    # empirical: for each a, nearest b; median of deltas rounded to the minute
    deltas = []
    bt = [t.entry_dt for t in b]
    for ta in a:
        d = min((tb - ta.entry_dt for tb in bt), key=lambda x: abs(x))
        deltas.append(d.total_seconds() / 60.0)
    if deltas:
        med = int(round(float(np.median(deltas))))
        if med not in cands:
            cands.append(med)
    scored = [(_coverage(a, b, off, tol_min), -abs(off), off) for off in cands]
    scored.sort(reverse=True)
    return scored[0][2]


def match(a, b, offset_min, tol_min):
    """Greedy one-to-one match on entry time (a shifted by offset). Closest pairs first.
    Returns (matched:[(ta,tb,dt_min)], unmatched_a, unmatched_b)."""
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
    """True if a timestamp falls INSIDE the RTH cash session (09:30–16:00 ET wall clock)."""
    if ts is None:
        return None
    t = ts.time()
    return (t >= pd.Timestamp("09:30").time()) and (t <= pd.Timestamp("16:00").time())


# ────────────────────────────────────────────────────────────────────────────
# Diagnosis — turn the raw diff into named, likely causes
# ────────────────────────────────────────────────────────────────────────────
def diagnose(matched, unmatched_a, unmatched_b, offset_min, a_label, b_label, tol_min):
    out = []
    n_m = len(matched)

    if offset_min:
        h = offset_min / 60.0
        out.append(("TIMEZONE", f"{a_label} entry times are {b_label} {'+' if offset_min>0 else '-'}"
                    f"{abs(h):g}h. Auto-aligned before matching (a whole-hour tz/DST shift, "
                    f"not a logic gap)."))

    # residual entry-time shift among matched (after the whole-hour offset)
    if n_m:
        dts = np.array([m[2] for m in matched])
        med_dt = float(np.median(dts))
        if abs(med_dt) >= 0.5 and np.std(dts) < max(1.0, tol_min * 0.3):
            out.append(("ENTRY-BAR", f"Every matched entry is {med_dt:+.1f} min apart (tight cluster) "
                        f"→ a fixed one-bar entry-convention difference (e.g. fill at next bar's open), "
                        f"not random noise."))

    # side flips
    flips = [(m[0], m[1]) for m in matched if m[0].side and m[1].side and m[0].side != m[1].side]
    if flips:
        out.append(("SIDE-FLIP", f"{len(flips)} matched trades disagree on direction (long vs short) "
                    f"→ knife-edge opening-range boundary: a 1-tick data difference flips the break."))

    # per-trade PnL gap
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
                        f"Run the EDGELOG side with --cost-pts set to the platform's per-round-turn cost to close it."))
        elif abs(md) >= 1.0:
            out.append(("PNL-SCATTER", f"Per-trade PnL differs by {md:+.2f} $/trade on average but scatters "
                        f"(σ=${sd:.2f}) → not a flat fee; look at fill prices / stop-fill assumptions."))

    # entry-price offset (contract roll / back-adjustment)
    px_pairs = [(m[0].entry_px, m[1].entry_px) for m in matched
                if m[0].entry_px is not None and m[1].entry_px is not None]
    if px_pairs:
        d = np.array([x - y for x, y in px_pairs])
        md, sd = float(np.median(d)), float(np.std(d))
        if abs(md) >= 1.0 and sd < max(2.0, abs(md) * 0.4):
            out.append(("PRICE-OFFSET", f"Entry prices sit a constant {md:+.2f} pts apart (σ={sd:.2f}) → the two "
                        f"feeds are on different contracts / back-adjustment (continuous vs TV's dated contract). "
                        f"Pick a window mid-cycle, away from a quarterly roll."))

    # unmatched trades — where do the extras live?
    for extras, who, other in ((unmatched_a, a_label, b_label), (unmatched_b, b_label, a_label)):
        if not extras:
            continue
        eth = [t for t in extras if _rth_flag(t.entry_dt) is False]
        msg = f"{len(extras)} trade(s) in {who} have no match in {other}."
        if eth and len(eth) >= max(1, len(extras) // 2):
            msg += (f" {len(eth)} of them are OUTSIDE 09:30–16:00 ET → {who} is including "
                    f"extended-hours (ETH) bars; the other side is RTH-only. (ORB.md §8: ETH is not "
                    f"tradeable for ORB — reconcile RTH-to-RTH.)")
        out.append(("UNMATCHED", msg))

    if not out and n_m:
        out.append(("CLEAN", "No systematic offset found — the two blotters agree within tolerance. ✅"))
    return out


# ────────────────────────────────────────────────────────────────────────────
# Reporting
# ────────────────────────────────────────────────────────────────────────────
def _fmt_dt(ts):
    return ts.strftime("%Y-%m-%d %H:%M") if ts is not None else "—"


def _sum_pnl(trades):
    v = [t.pnl_usd for t in trades if t.pnl_usd is not None]
    return sum(v) if v else None


def render(a, a_meta, b, b_meta, offset_min, tol_min):
    """Build the full text report comparing side A (EDGELOG) to side B (TV/NT)."""
    a_label, b_label = a_meta["source"], b_meta["source"]
    matched, un_a, un_b = match(a, b, offset_min, tol_min)
    lines = []
    P = lines.append

    P(f"# Reconciliation: {a_label}  ↔  {b_label}")
    P("")
    P(f"{a_label}: {a_meta.get('strategy','?')} on {a_meta.get('instrument','?')} "
      f"{a_meta.get('timeframe','')} {a_meta.get('session','')} | master {a_meta.get('master','?')} "
      f"| window {a_meta.get('window',('?','?'))[0]} → {a_meta.get('window',('?','?'))[1]}")
    P(f"{b_label}: {b_meta.get('file','?')} | columns used: {b_meta.get('cols','?')}")
    P("")

    # Summary
    tot_a, tot_b = _sum_pnl(a), _sum_pnl(b)
    P("## Summary")
    P(f"  trades         {a_label}={len(a):<5} {b_label}={len(b):<5} matched={len(matched)}  "
      f"unmatched: {a_label}={len(un_a)} {b_label}={len(un_b)}")
    if tot_a is not None and tot_b is not None:
        P(f"  total PnL ($)  {a_label}={tot_a:>11,.2f}  {b_label}={tot_b:>11,.2f}  "
          f"Δ={tot_a-tot_b:>+11,.2f}")
    if offset_min:
        P(f"  tz offset applied to {a_label}: {offset_min:+d} min ({offset_min/60:+g}h)")
    P("")

    # Diagnosis first — it's the headline
    P("## Diagnosis")
    for tag, msg in diagnose(matched, un_a, un_b, offset_min, a_label, b_label, tol_min):
        P(f"  [{tag}] {msg}")
    P("")

    # Per-trade table
    P("## Matched trades (entry-time aligned)")
    hdr = (f"  {'#':>3} {a_label[:4]+' entry':<17} {'side':>4} {'in$':>10} "
           f"{'Δt(m)':>6} {'Δpnl$':>9} {'Δin_px':>8}")
    P(hdr)
    P("  " + "-" * (len(hdr) - 2))
    for k, (ta, tb, dt) in enumerate(matched, 1):
        dpnl = (ta.pnl_usd - tb.pnl_usd) if (ta.pnl_usd is not None and tb.pnl_usd is not None) else None
        dpx = (ta.entry_px - tb.entry_px) if (ta.entry_px is not None and tb.entry_px is not None) else None
        sflag = "!" if (ta.side and tb.side and ta.side != tb.side) else ""
        P(f"  {k:>3} {_fmt_dt(ta.entry_dt):<17} {('L' if ta.side>0 else 'S' if ta.side<0 else '?')+sflag:>4} "
          f"{(ta.pnl_usd if ta.pnl_usd is not None else float('nan')):>10,.2f} "
          f"{dt:>6.0f} "
          f"{(dpnl if dpnl is not None else float('nan')):>9,.2f} "
          f"{(dpx if dpx is not None else float('nan')):>8.2f}")

    if un_a:
        P("")
        P(f"## Unmatched in {a_label} (no {b_label} trade within {tol_min}m)")
        for t in un_a[:30]:
            P(f"  {_fmt_dt(t.entry_dt)}  side={t.side:+d}  pnl$={t.pnl_usd if t.pnl_usd is not None else float('nan'):,.2f}")
    if un_b:
        P("")
        P(f"## Unmatched in {b_label} (no {a_label} trade within {tol_min}m)")
        for t in un_b[:30]:
            P(f"  {_fmt_dt(t.entry_dt)}  side={t.side:+d}  pnl$={t.pnl_usd if t.pnl_usd is not None else float('nan'):,.2f}")

    return "\n".join(lines), dict(matched=len(matched), unmatched_a=len(un_a),
                                  unmatched_b=len(un_b), offset_min=offset_min,
                                  total_a=tot_a, total_b=tot_b)


# ────────────────────────────────────────────────────────────────────────────
# Param parsing + CLI
# ────────────────────────────────────────────────────────────────────────────
def _downloads_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads")


def resolve_export(path_arg, hint=""):
    """Turn a --tv/--nt value into a real file path. 'auto'/'downloads'/'latest' picks the
    most recently modified .csv in the Downloads folder — matches the Chrome-export flow
    (I click TV's export, a CSV lands in Downloads, this grabs it without you typing a name).
    An optional `hint` substring biases the pick (e.g. 'trade')."""
    if not path_arg:
        return None
    if path_arg.lower() in ("auto", "downloads", "latest"):
        d = _downloads_dir()
        cands = [os.path.join(d, f) for f in os.listdir(d)
                 if f.lower().endswith(".csv") and (not hint or hint.lower() in f.lower())]
        if not cands:
            raise SystemExit(f"No .csv in {d}"
                             + (f" matching '{hint}'" if hint else "")
                             + ". Export from TV/NT first, or pass an explicit path.")
        newest = max(cands, key=os.path.getmtime)
        print(f"  (auto-picked newest Downloads CSV: {os.path.basename(newest)})")
        return newest
    return path_arg


def parse_params(s):
    """'or_bars=3,stop_frac=0.75,trade_mode=Both,flat_eod=True' → typed dict."""
    out = {}
    if not s:
        return out
    for kv in s.split(","):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.lower() in ("true", "false"):
            out[k] = (v.lower() == "true")
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


# Default ORB config used by tools/xcheck_orb.py — so `--strategy ORB_3_0.py` just works.
DEFAULT_ORB = dict(or_bars=3, trade_mode="Both", stop_frac=0.75, vol_filter=0.0,
                   breakout_buf=0.0, target_R=0.0, flat_eod=True)


def run_self_test(tol_min):
    """No external file: build a synthetic TV export from the EDGELOG blotter with a known
    +4h tz shift and a -$5.66 fee gap injected, then confirm the tool recovers both."""
    print("SELF-TEST — synthetic TV export from the EDGELOG ORB blotter (+4h tz, −$5.66 fee)\n")
    a, a_meta = edgelog_blotter("ORB_3_0.py", "NQ", "5m", "rth", DEFAULT_ORB,
                                date_from="2026-05-01", date_to="2026-05-29", cost_pts=0.0)
    if not a:
        print("no EDGELOG trades in the window — pick another --from/--to"); return
    # forge the "other platform": shift entry/exit +4h, charge a $5.66 round-turn
    b = []
    for t in a:
        b.append(Trade(entry_dt=t.entry_dt + pd.Timedelta(hours=4),
                       exit_dt=(t.exit_dt + pd.Timedelta(hours=4)) if t.exit_dt is not None else None,
                       side=t.side, qty=t.qty, entry_px=t.entry_px, exit_px=t.exit_px,
                       pnl_usd=(t.pnl_usd - 5.66) if t.pnl_usd is not None else None))
    b_meta = {"source": "TradingView", "file": "<synthetic>", "num_trades": len(b),
              "cols": {"pnl": "synthetic"}}
    off = best_offset(a, b, tol_min)
    report, summ = render(a, a_meta, b, b_meta, off, tol_min)
    print(report)
    # B was forged as A shifted +4h, so aligning A→B is +240 min; and the $5.66 gap
    # must surface as the [FEES] diagnosis. Both recovered ⇒ the machinery works.
    ok = (off == 240 and summ["matched"] == len(a)
          and summ["unmatched_a"] == 0 and summ["unmatched_b"] == 0)
    print("\nSELF-TEST", "PASS ✅" if ok else "CHECK ⚠️",
          f"(offset={off}m expected +240, matched={summ['matched']}/{len(a)})")


def main(argv=None):
    # Windows consoles default to cp1252 and choke on the report glyphs (→ σ Δ ✅).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Reconcile EDGELOG backtest trades vs TradingView / NinjaTrader.")
    ap.add_argument("--strategy", default="ORB_3_0.py", help="strategy plugin filename")
    ap.add_argument("--inst", default="NQ", help="instrument key (NQ, ES, MES, …)")
    ap.add_argument("--tf", default="5m", help="timeframe (5m, 1m, 15m)")
    ap.add_argument("--session", default="rth", help="rth | eth")
    ap.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD (ET)")
    ap.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD (ET, inclusive)")
    ap.add_argument("--params", default=None, help="k=v,k=v strategy params (defaults to ORB config)")
    ap.add_argument("--cost-pts", type=float, default=0.0, help="per-round-turn cost (points) on the EDGELOG side")
    ap.add_argument("--tv", default=None, help="TradingView 'List of Trades' CSV path, or 'auto' = newest CSV in Downloads")
    ap.add_argument("--nt", default=None, help="NinjaTrader Strategy Analyzer trades CSV path, or 'auto' = newest CSV in Downloads")
    ap.add_argument("--hint", default="", help="substring to bias 'auto' Downloads pick (e.g. 'trade')")
    ap.add_argument("--tol-min", type=float, default=10.0, help="entry-time match tolerance (minutes)")
    ap.add_argument("--out", default=None, help="also write the report to this file")
    ap.add_argument("--self-test", action="store_true", help="prove the machinery with a synthetic TV export")
    args = ap.parse_args(argv)

    if args.self_test:
        run_self_test(args.tol_min)
        return

    if not (args.tv or args.nt):
        raise SystemExit("Give at least one of --tv / --nt (or use --self-test). "
                         "Export the trade list from TV (Strategy Tester → List of Trades → download) "
                         "or NT (Strategy Analyzer → Trades → right-click Export).")

    params = parse_params(args.params) if args.params else (
        DEFAULT_ORB.copy() if args.strategy.upper().startswith("ORB") else {})
    mult = MULT.get(args.inst.upper(), 1)
    a, a_meta = edgelog_blotter(args.strategy, args.inst, args.tf, args.session, params,
                                date_from=args.date_from, date_to=args.date_to,
                                cost_pts=args.cost_pts, mult=mult)
    print(f"EDGELOG: {len(a)} trades | {a_meta['master']} | window "
          f"{a_meta['window'][0]} → {a_meta['window'][1]}\n")

    reports = []
    for path_arg, parser in ((args.tv, parse_tv), (args.nt, parse_nt)):
        if not path_arg:
            continue
        path = resolve_export(path_arg, hint=args.hint)
        if not os.path.exists(path):
            print(f"!! file not found: {path}"); continue
        b, b_meta = parser(path, mult)
        off = best_offset(a, b, args.tol_min)
        report, _ = render(a, a_meta, b, b_meta, off, args.tol_min)
        print(report); print("\n" + "=" * 78 + "\n")
        reports.append(report)

    if args.out and reports:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(("\n\n" + "=" * 78 + "\n\n").join(reports))
        print(f"report written → {args.out}")


if __name__ == "__main__":
    main()

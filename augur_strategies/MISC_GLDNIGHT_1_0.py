# AUGUR-SOURCE: claude-review
"""MISC GLDNIGHT 1.0 - long GLD ($100,000) from the official close to the next session's official open, weeknights only.

Provenance: OPUS-HUNT futures, strategies 158 / 160 (GLD-NIGHT, "gold beta, night-only"), verdict cell 160a "official
prints" (C:/EdgeLog/_anatomy_cache/opus_hunt1109/db_masters/r20_run.py with r19_lib.py / r18_lib.py, output
r20_160_out.txt). Defaults = cell 160a with whole shares (see Sizing). Mechanism (hunt): gold's return is earned
outside New York cash hours (the London fixes and the Asian session), so holding GLD only overnight keeps most of the
gold drift for about a third of the clock and no intraday buying power.
WHAT THIS IS, PLAINLY:
  * A GOLD-BETA SEAT, not an edge on a signal. It is long GLD every weeknight, so it FAILS the hunt's random-day
    placebo bar BY CONSTRUCTION (there is no "other day" to draw: it trades them all) and it failed the hunt's kill
    bar (placebo False, correlation with the book +0.05, not <= 0). It makes money when gold rises and loses when
    gold falls.
  * 2016-18 AND 2021-22 ARE FLAT TO DOWN (160a by calendar year, $k: 2016 -1.3, 2017 +3.2, 2018 +3.6, 2019 +7.9,
    2020 +21.8, 2021 -6.4, 2022 -1.3, 2023 +8.1, 2024 +22.1, 2025 H1 +7.4); the top year is 34 pct of the net.
  * COST: at the pinned 1 cent a share round trip (+ 0.3 bp a side) cost is $12.49 of a $49.3 gross a trade. The
    net keeps 82 pct at 2 cents a share and 65 pct at 3 cents (hunt cells 160b, bar prices: $5,909 and $4,641 a
    year against $7,176).
  * MARGIN: $100k of GLD held 4 nights a week = about $50k of overnight stock margin; nothing intraday. Financing
    that $50k at 6 pct a year costs $8.33 a night (hunt cell 160d) and is NOT charged here.
  * NOT A BLIND READ. The hunt read WF 2016-07-01 .. 2025-06-30 (and earlier revisions of the same idea on the
    same years): 1,767 trades (196 a year), net about +$7,230 a year, max DD $16,766, 7 of 9 July-June folds up.
    `nights` = weeknights WAS CHOSEN AFTER SEEING THE FOLDS: every night made $8,003 a year with 5 of 9 folds up
    and a larger drawdown, and weekend / holiday nights alone made about $515 a year with 3 of 9 folds up (both
    read on 5m bar prices, cells "160 every night" / "160 weekend"). The 2025-07 .. 2026-06 lockbox was never read
    by the hunt or by the build of this file. This file exists so the engine's Auto-Validate can judge the seat.

-- The rule (defaults = cell 160a) -------------------------------------------------------------------------------
1. A night = two consecutive GLD sessions D-1 and D. `nights` picks which nights trade, from the CALENDAR GAP
   between the two session dates only: weeknights = exactly 1 calendar day apart (Mon->Tue .. Thu->Fri; the
   default); weekend_only = 3 or more days apart (Fri->Mon and holiday weekends, the hunt's "gap >= 3"); every_night
   = every pair of consecutive sessions (the two above plus the 2-day gaps around a mid-week holiday, 27 in
   2016-01 .. 2026-06).
2. BUY at D-1's official close (an MOC fill; 13:00 on a half day), SELL at D's official open (an MOO fill).
3. Every night is its own trade, charged a full round trip; nothing is netted.
TRADE <-> SESSIONS (every trade holds across ONE night). Its entry bar is D-1's last 5m bar in the job's bars (the
bar whose close is the closing print) and its exit bar is D's 09:30 bar (the bar whose open is the opening print);
its P&L lands on D. The engine files a trade under the stretch its ENTRY bar is in, so it belongs to D-1's stretch;
mark_open_trades values it at 0 at that entry bar (bought at that close; costs land on the exit day). A trade needs
D-1's last bar and D's 09:30 bar inside the bars: a walk-forward slice that ends at D-1, or starts at or after D's
open, takes no trade for that night - a slice edge never closes a trade early or opens it late (at most one trade
lost per slice edge; a job that starts 2016-07-01 has no 2016-06-30 -> 07-01 night, the hunt's first).
THE EXIT PRINT NEVER SELECTS THE ENTRY: which nights trade comes from the session calendar only; the entry bar is
found from D-1's own bars; shares from D-1's raw close. D's official open is read for the P&L only. The one fact
about D used before that is whether D's 09:30 bar is inside the job's bars - a clock fact (bar times), never a
price. tests/test_misc_gldnight.py scrambles everything known only after the entry print and checks that no trade
moves, and that broken variants (shares from D's open; a night skipped when D opens down; exit at the 09:35 bar)
are caught.

INFORMATION TIMES (every input known at or before its print):
  * the session calendar (holidays, half days) is the exchange's, published years ahead; it fixes D-1, D, the gap
    between them (so whether tonight is a weeknight) and D-1's closing time;
  * entry: D-1's official close (an MOC order, entered before the close). Shares = floor(N / D-1's raw close) -
    the closing print itself, the hunt's sizing price (live sizing would read a pre-close price; ~0 effect);
  * exit: D's official open (an MOO order). Nothing about D decides anything.

-- Data ----------------------------------------------------------------------------------------------------------
THE JOB'S MASTER = GLD 5m RTH, source alpaca_split_rth (engine master id 79, master_90ca117d.csv, 2016-01-04 ..
2026-06-30, 2,637 sessions; GLD never split and pays no distribution, so split-adjusted = traded prices): THE BAR
CLOCK ONLY - no master price is read. Prices come from the pinned side panel (sha256 checked)
    C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_v1.npz   (built by tools/misc_gldnight_panel.py)
= the session calendar 2016-01-04 .. 2026-06-30 (GLD_1Day_raw.csv, the 5m master and the sibling's gldmacro panel
agree on every date), `open` / `close` = C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv opens and closes (the
hunt's prints, cell 160a), `raw` = the same closes (the share-count and cost price), `first_min` / `last_min` = the
minute of each session's first / last 5m bar in the master (09:30 on every session; 15:55, 12:55 on the 21 half
days, 15:25 on 2019-08-12) and `gap` = calendar days to the previous session.
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
Known data limits (the hunt's own; tools/misc_gldnight_panel.py prints them):
  * the alpaca raw close is off the official close on 2020-03-12 (+179 bp) and 2020-03-16 (-288 bp) against the
    yahoo daily close. Both are ENTRY prints of weeknight trades (the nights into 2020-03-13 and 2020-03-17), so
    those two trades are mispriced by about -$1.8k and +$2.9k (they roughly offset; tools/misc_gldnight_parity.py
    prints the WF total with the yahoo closes swapped in). 161 other closes differ by 1 to 10 bp;
  * the raw open differs from the 5m master's 09:30 bar open on 183 sessions, by 8.9 bp at most.

-- Sizing and costs (INSIDE the plugin: job cost_pts 0, mult 1) ---------------------------------------------------
N = `notional` ($100,000) a trade. px = D-1's raw close, shares = floor(N / px), gross = shares x px x (open(D) /
close(D-1) - 1) on the official prints. Cost = 2 x (`cents_share` cents x shares + `fee_bps` bp x px x shares) = 2 x
(0.5 c a share + 0.3 bp), both sides charged on the entry notional (the hunt's formula; about $12.5 a trade). Net =
gross - cost, DOLLARS in the trade tuple's field 2; side +1; entry / exit prices = the official close and open.
THE HUNT USED FRACTIONAL SHARES (N / px); this file buys WHOLE shares, so every trade is the hunt's trade scaled by
shares x px / N (0.9969 .. 1.0, 0.9992 on average). tools/misc_gldnight_parity.py, WF 2016-07-01 .. 2025-06-30, bars
from 2016-06-30: fractional replica = the hunt's print (1,767 trades, $65,041.40, $7,230 a year, max DD $16,766, 7 of
9 folds); this file 1,767 trades, $64,978.98, $7,223 a year, max DD $16,755, 7 of 9 folds; the gap of -$62.42 (-0.10
pct) is the whole-share floor, trade for trade, to 1e-12. On the official prints every night makes $7,862 a year (5
of 9 folds) and weekend nights $189 a year (3 of 9) - the hunt's $8,003 / $515 were read on 5m bar prices.

-- Auto-Validate ranges -------------------------------------------------------------------------------------------
OPEN: nights (3: weeknights, every_night, weekend_only) = 3 grid points - the whole honest space. The rule has no
other choice the hunt left open: one entry print, one exit print, no filter. No knob was added to pad the grid, so
an Auto-Validate asked for 900 trials evaluates 3 configs and its section 2 surfaces will be thin. PINNED (min = max
= hard bounds): notional, cents_share, fee_bps. No numeric knob is open, so nothing can auto-expand.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC GLDNIGHT 1.0 · long GLD close to next open, weeknights (opus hunt 160a)'
DESCRIPTION = ("Buy $100,000 of GLD at the official close and sell it at the next session's official open, on "
               "weeknights only (sessions exactly one calendar day apart): gold beta, night-only. Runs on the GLD 5m "
               "master (the bar clock only); the official opens and closes come from a pinned side panel. Costs "
               "inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "GLD", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_v1.npz"
PANEL_SHA256 = "274eff68f1269ac46d19a3f3ebe54f79aba582284209609e78d8e6cee6de632a"   # built 2026-11-18, 2,637 sessions
PANEL_KEYS = ("dates", "open", "close", "raw", "first_min", "last_min", "gap")

NIGHT_MODES = ("weeknights", "every_night", "weekend_only")

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "hard_min": 100000, "hard_max": 100000, "step": 1,
                 "type": "int", "label": "Dollars a trade",
                 "tooltip": "Fixed: shares = floor($100,000 / the prior raw close), the hunt's size in whole shares."},
    "cents_share": {"default": 0.5, "min": 0.5, "max": 0.5, "hard_min": 0.5, "hard_max": 0.5, "step": 0.5,
                    "type": "float", "label": "Cost (cents a share a side)",
                    "tooltip": "Fixed: half a cent a share on the entry and again on the exit (the hunt's $0.005)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "hard_min": 0.3, "hard_max": 0.3, "step": 0.1,
                "type": "float", "label": "Fees (bp a side)",
                "tooltip": "Fixed: 0.3 bp of the entry notional on the entry and again on the exit (the hunt's)."},
    "nights": {"default": "weeknights", "type": "str", "options": list(NIGHT_MODES),
               "label": "Which nights",
               "tooltip": "weeknights = sessions exactly one calendar day apart (cell 160a; chosen after seeing the "
                          "hunt's folds). every_night = every pair of consecutive sessions. weekend_only = sessions "
                          "three or more days apart (Friday close to Monday open, holiday weekends)."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 160a)": {"nights": ["weeknights"]},
    "Medium (weeknights, every night, weekends only)": {"nights": list(NIGHT_MODES)},
}

PNL_UNITS = "usd"

_OPEN_MIN = 570          # 09:30 ET, minute of day: the first RTH 5m bar
_LAST_SLOT = 955         # 15:55 ET: the last RTH 5m bar of a full session
_CACHE = {}              # per-process: the panel and the bar clock (night rows live in the panel's memo)


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_GLDNIGHT_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _derive({k: z[k] for k in PANEL_KEYS})
    _CACHE["panel"] = p
    return p


def _derive(p):
    """Typed copies of the panel arrays plus an empty memo (a panel cut at an earlier date derives the same rows)."""
    out = {k: np.asarray(p[k], np.float64) for k in ("open", "close", "raw")}
    out.update({k: np.asarray(p[k], np.int64) for k in ("dates", "first_min", "last_min", "gap")})
    out["memo"] = {}
    return out


def _clock(index):
    """ET calendar date (yyyymmdd) and minute of day of every bar. The engine hands slices of one master, so the
    largest index seen is converted once and later slices of it are cut from that copy."""
    idx = pd.DatetimeIndex(index)
    ns = idx.asi8
    tz = str(idx.tz)
    c = _CACHE.get("clock")
    n = len(ns)
    if c is not None and c[0] == tz and n:
        a = int(np.searchsorted(c[1], ns[0]))
        if a + n <= len(c[1]) and np.array_equal(c[1][a:a + n], ns):
            return c[2][a:a + n], c[3][a:a + n]
    loc = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    date = (loc.year * 10000 + loc.month * 100 + loc.day).to_numpy().astype(np.int64)
    minute = (loc.hour * 60 + loc.minute).to_numpy().astype(np.int64)
    if (c is None or n > len(c[1])) and n and bool(np.all(ns[1:] > ns[:-1])):
        _CACHE["clock"] = (tz, ns.copy(), date, minute)
    return date, minute


def _sessions(date, minute):
    """Sessions of the bars: (first bar, end bar (exclusive), yyyymmdd, first minute, last minute, RTH flag). A session
    is RTH when every bar starts inside 09:30 .. 15:55 ET; anything else (the contract test's 24-hour tape, an ETH
    feed) is never traded."""
    n = len(date)
    cut = np.flatnonzero(date[1:] != date[:-1]) + 1
    starts = np.concatenate([[0], cut]).astype(np.int64)
    ends = np.concatenate([cut, [n]]).astype(np.int64)
    lo = np.minimum.reduceat(minute, starts)
    hi = np.maximum.reduceat(minute, starts)
    return starts, ends, date[starts], minute[starts], minute[ends - 1], (lo >= _OPEN_MIN) & (hi <= _LAST_SLOT)


def _night_rows(p, nights):
    """Panel rows of the exit sessions D of the selected nights. Decided by the calendar gap between D-1 and D only
    (the exchange calendar, known in advance) - never by a price."""
    key = ("rows", nights)
    if key not in p["memo"]:
        gap = p["gap"]
        if nights == "weeknights":
            k = gap == 1
        elif nights == "weekend_only":
            k = gap >= 3
        else:
            k = gap >= 1
        k = np.array(k, bool)
        k[0] = False                                    # the first panel session has no D-1
        p["memo"][key] = np.flatnonzero(k)
    return p["memo"][key]


def _entry_terms(p, i):
    """(entry print, sizing price) of the night into panel row i: D-1's official close and D-1's raw close, both
    known at D-1's closing print (the entry)."""
    return float(p["close"][i - 1]), float(p["raw"][i - 1])


def _exit_bar(starts, jD):
    """The exit bar: session D's first bar (09:30), whose open is the opening print."""
    return int(starts[jD])


def _cfg_ok(nights):
    return isinstance(nights, str) and nights in NIGHT_MODES


def _trades(p, index, opens, closes, notional=100000, cents_share=0.5, fee_bps=0.3, nights="weeknights"):
    """Every trade of one config on these bars: a list of dicts (bars, dates, prices, shares, gross, cost, net).
    `opens` / `closes` (the job's bar prices) are NOT read: the bars are the clock, the panel holds the prints."""
    if not _cfg_ok(nights):
        return []
    date, minute = _clock(index)
    if len(date) < 2:
        return []
    starts, ends, sdate, fmin, lmin, rth = _sessions(date, minute)
    if len(sdate) > 1 and not bool(np.all(sdate[1:] > sdate[:-1])):
        return []                                       # bars out of time order: never guess at sessions
    N = float(notional)
    cps = round(float(cents_share) / 100.0, 12)          # dollars a share a side
    fee = round(float(fee_bps) * 1e-4, 12)               # fraction of the entry notional a side
    dates = p["dates"]
    rows = _night_rows(p, nights)
    if not len(rows):
        return []
    lo, hi = int(sdate[0]), int(sdate[-1])
    rows = rows[(dates[rows] > lo) & (dates[rows] <= hi)]   # D inside the bars' date span, D-1 not before it
    out = []
    for i in rows:
        i = int(i)
        dD = int(dates[i])
        jD = int(np.searchsorted(sdate, dD))
        if jD >= len(sdate) or int(sdate[jD]) != dD or not rth[jD]:
            continue                                    # D is not an RTH session of these bars
        if int(fmin[jD]) != _OPEN_MIN or int(p["first_min"][i]) != _OPEN_MIN:
            continue                                    # no 09:30 bar in these bars: no opening print to sell
        jP = jD - 1
        if jP < 0 or int(sdate[jP]) != int(dates[i - 1]) or not rth[jP]:
            continue                                    # D-1 = the panel's previous session, and it must be in the bars
        if int(lmin[jP]) < int(p["last_min"][i - 1]):
            continue                                    # the bars stop inside D-1: its closing bar is not there
        e = int(ends[jP] - 1)                           # D-1's last bar: the entry is its closing print
        x = _exit_bar(starts, jD)                       # D's 09:30 bar: the exit is its opening print
        c0, px = _entry_terms(p, i)
        o1 = float(p["open"][i])                        # D's official open: the P&L only
        if not (np.isfinite(c0) and np.isfinite(o1) and np.isfinite(px) and c0 > 0 and o1 > 0 and px > 0):
            continue
        sh = float(np.floor(N / px))
        if sh < 1:
            continue
        gross = sh * px * (o1 / c0 - 1.0)
        cost = 2.0 * (cps * sh + fee * px * sh)
        out.append({"e": e, "x": x, "D": dD, "entry_day": int(dates[i - 1]), "row": i, "px": px, "shares": sh,
                    "p_in": c0, "p_out": o1, "gap": int(p["gap"][i]), "gross": gross, "cost": cost,
                    "net": gross - cost})
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, cents_share: float = 0.5, fee_bps: float = 0.3,
                 nights: str = "weeknights",
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if not _cfg_ok(nights):
        return None
    date, minute = _clock(index)
    if not bool(_sessions(date, minute)[5].any()):
        return None                                     # no RTH session in these bars: the panel is never opened
    p = _panel()
    if p is None:
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    rows = _trades(p, index, opens, closes, notional=notional, cents_share=cents_share, fee_bps=fee_bps,
                   nights=nights)
    trades = [(r["e"], r["x"], float(r["net"]), 1, float(r["p_in"]), float(r["p_out"])) for r in rows]
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    pnl = np.array([t[2] for t in trades], float)
    w = pnl[pnl > 0]
    ls = pnl[pnl < 0]
    gw = float(w.sum())
    gl = float(-ls.sum())
    cum = np.cumsum(pnl)
    out = {"total_pnl": float(pnl.sum()), "num_trades": int(len(pnl)),
           "win_rate": float(100.0 * len(w) / len(pnl)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(pnl.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None, **params):
    """Every trade is held through ONE session close - its entry bar, D-1's last bar - where it is worth exactly 0
    (bought at that very close; costs land on the exit day with the rest of its P&L). One [(bar, usd), ...] list per
    trade, in trade order. A trade whose exit bar is not after its entry bar, or sits on the entry bar's own date
    (never produced by this file), gets no mark."""
    date = None
    if index is not None and len(index) == len(closes):
        date, _ = _clock(index)
    out = []
    for t in trades or []:
        e, x = int(t[0]), int(t[1])
        if x <= e:
            out.append([])
        elif date is not None and 0 <= e < len(date) and 0 <= x < len(date) and date[e] == date[x]:
            out.append([])
        else:
            out.append([(e, 0.0)])
    return out

"""
NQDIP 1.4 — NQDIP 1.2 (true rolls) plus ONE new knob: a catastrophe stop (2026-09-27).

WHY: the Frontier book test (BOOK.md 10j, runs #439/#440) failed DIP on ES as a book seat on drawdown, and
the damage is the Feb-Mar 2020 crash, where a no-stop dip buyer keeps averaging into a falling market.
Round 18b once measured stops as strictly harmful to this hold-for-days edge, but ROLL_AUDIT.md lists that
finding as wrong (its harness mis-handled rolls), so the question is open again.
RULE: stop = entry open - stop_atr x ATR20 (the mean daily range of the 20 sessions before entry), on the
roll-adjusted series, fixed at entry. Checked every session held, entry day included: an open at or below
the stop exits at that open (gap-honest); otherwise the first 5-minute bar whose low reaches it exits at
the stop. stop_atr = 0 switches it off and reproduces NQDIP 1.2 exactly. Everything else is 1.2.
The original header follows.

NQDIP 1.2 — NQDIP 1.0's rules, unchanged, with TRUE contract-roll handling (2026-09-26).

WHY: ROLL_AUDIT.md 3.6. NQDIP 1.0 found rolls with the day-level house detector (20 of 65 NQ,
17 of 65 ES switches) and then dropped the WHOLE overnight gap of every flagged night, so real
gaps vanished (Covid 2020-03-09 ES -208.5 pts, 2020-03-16 NQ -560.5 pts) and DIP drawdowns read
23-29% too small. 1.2 back-adjusts at the exact switch BAR from tools/data/rolls_*.csv
(the maintained roll table): only the contract offset leaves the P&L, every real gap stays in,
entries and exits on roll days are allowed (1.x skipped them), and each switch a position is held
across still costs 0.25 pt. Signals read the adjusted series (all shift-invariant); size reads the
real traded price. On a daily ETF master nothing changes. The original header follows.

NQDIP 1.0 — the Nasdaq dip-buying BOOK as one strategy (four mechanisms, long-only).

Provenance: the autonomous MISC hunt's walk-forward phase (rounds 25-26, 2026-08-25,
STUDIES rows 1027-1051 and 1141-1158, BOOKMARKS.md B11-B13). Out-of-sample only,
per-fold re-tuned, the eight-leg Nasdaq book (this file on QQQ + this file on NQ)
scored n=1250 / $706,799 / PF 1.95 / MAR 10.11 / 12-of-14 years, corr 0.04 to the
live champion book, and lifted the champion book's MAR 8.31 -> 11.20 when stacked.
This file exists so the app's Auto-Validate can search the same space with full
discovery (WF folds, sealed lockbox, PBO/DSR, surfaces) and put every detail on a
run card.

── What it trades ────────────────────────────────────────────────────────────────
Daily bars are aggregated from whatever master is loaded via `day_id` (an intraday
RTH master collapses to one bar per session; a daily master is already one bar per
day). Four independent mechanisms run side by side, each with its own position slot
(so up to 4 units can be on at once), all LONG-ONLY behind a trend filter
(day close > SMA(trend_len) of daily closes):
  RSI  : RSI(rsi_len) of daily closes < rsi_thr        -> exit when close > SMA(rsi_exit)
  DBL  : today's close is the lowest close of the last dbl_n days -> exit on an
         dbl_n-day closing high
  PB   : the day's low touches EMA(pb_ema) while yesterday closed above it
         -> exit on a close above the entry-day's prior high, or after pb_hold days
  CAP  : a down day whose range >= cap_mult x ATR20 and which closes in the bottom
         cap_q of its range (no trend filter: capitulation is bought regardless)
         -> exit after cap_hold days
Every signal is evaluated on the day's CLOSE and filled at the NEXT day's OPEN;
every exit signal is evaluated on a close and filled at the next open. No stop:
the round-18b/22 studies measured stops as strictly harmful to this hold-for-days
edge; the gap risk is real and is in the numbers.

── Sizing and costs (INSIDE the plugin — set the job's cost_pts to 0) ──────────────
`asset` selects the model (auto-detected: one bar per session = ETF, else NQ;
not a searchable knob, so Auto-Validate never sweeps it):
  "NQ" : contracts = notional / (entry price x 20), rounded to whole MNQ micros
         (MNQ = $2/pt, so contracts_mnq = round(notional / (price x 2))); cost =
         cost_pts_rt (0.783 = overnight NQ round trip) x $2 x micros, plus 0.25 pt
         per quarterly roll crossed. Roll seams come from the house calendar-anchored
         detector (copied verbatim from ONDRIFT_1_0.py / GAPFADE_1_0.py); a seam
         night's jump is excluded from PnL because it is the contract stitch.
  "ETF": shares = notional / entry price; cost = cost_bps of notional per round trip.
PnL is returned in DOLLARS (the plugin contract allows SHARES*(EXIT-ENTRY)+FEE), so
the job must use mult = 1. Constant-notional sizing is the point: a 1-contract NQ
book has a notional that grew 5x over 2010-2025 and its drawdown lands in the last
years; at constant notional the same legs score MAR 6-10 instead of 3-4.

── Auto-Validate ranges ─────────────────────────────────────────────────────────────
The ranged knobs are the ones the walk-forward phase actually re-tuned (trend
length, RSI threshold/exit, N-day low, pullback EMA/hold, capitulation size/hold).
Sizing/cost knobs are fixed (min = max) so the search space is about the edge, not
the leverage. Requires day_id AND index (roll seams, dates).
"""
import inspect as _inspect

import numpy as np
import pandas as pd

STRATEGY_NAME = 'NQDIP 1.4 · Nasdaq dip book (4 long-only dip mechanisms, true rolls, crash stop)'
DESCRIPTION = ("Four dip-buying mechanisms (2-day RSI, N-day low, pullback to a short EMA, "
               "capitulation day) traded side by side, long-only behind a trend filter, "
               "hold-for-days, no stop. Constant-notional sizing in whole MNQ micros (NQ) "
               "or shares (ETF); costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Notional per trade ($)", "tooltip": "Fixed. Each mechanism sizes to this exposure."},
    "cost_pts_rt": {"default": 0.783, "min": 0.783, "max": 0.783, "step": 0.001, "type": "float",
                    "label": "NQ round-trip cost (pts)", "tooltip": "Fixed: overnight NQ RT (commission + 0.5 pt Globex slip)."},
    "cost_bps": {"default": 2.0, "min": 2.0, "max": 2.0, "step": 0.5, "type": "float",
                 "label": "ETF round-trip cost (bps)", "tooltip": "Fixed: 2 basis points of notional per round trip."},
    "trend_len": {"default": 200, "min": 100, "max": 300, "step": 50, "type": "int",
                  "label": "Trend filter SMA (days)", "tooltip": "Longs only when the close is above this SMA of daily closes. WF drifted 150-300."},
    "rsi_len": {"default": 2, "min": 2, "max": 5, "step": 1, "type": "int", "label": "RSI length (days)",
                "tooltip": "Connors-style short RSI."},
    "rsi_thr": {"default": 10, "min": 5, "max": 30, "step": 5, "type": "int", "label": "RSI buy below",
                "tooltip": "Oversold trigger."},
    "rsi_exit": {"default": 5, "min": 3, "max": 10, "step": 1, "type": "int", "label": "RSI exit SMA (days)",
                 "tooltip": "Exit when the close is back above this short SMA."},
    "dbl_n": {"default": 7, "min": 3, "max": 15, "step": 1, "type": "int", "label": "N-day low / high",
              "tooltip": "Buy the lowest close of N days, sell the highest close of N days. WF drifted 4-15."},
    "pb_ema": {"default": 20, "min": 5, "max": 50, "step": 5, "type": "int", "label": "Pullback EMA (days)",
               "tooltip": "Buy the first touch of this EMA while yesterday closed above it."},
    "pb_hold": {"default": 10, "min": 3, "max": 20, "step": 1, "type": "int", "label": "Pullback max hold (days)"},
    "cap_mult": {"default": 1.5, "min": 1.0, "max": 2.5, "step": 0.25, "type": "float",
                 "label": "Capitulation range (x ATR20)", "tooltip": "Day range must be at least this many ATR20s."},
    "cap_q": {"default": 0.25, "min": 0.15, "max": 0.4, "step": 0.05, "type": "float",
              "label": "Capitulation close quantile", "tooltip": "Close must sit in the bottom fraction of the day's range."},
    "cap_hold": {"default": 5, "min": 1, "max": 8, "step": 1, "type": "int", "label": "Capitulation hold (days)"},
    "stop_atr": {"default": 0.0, "min": 0.0, "max": 8.0, "step": 1.0, "type": "float",
                 "label": "Crash stop (x ATR20 below entry, 0 = off)",
                 "tooltip": "Exit when price falls this many average daily ranges below the entry. 0 = no stop (NQDIP 1.2)."},
    "use_rsi": {"default": True, "type": "bool", "label": "Run the RSI leg"},
    "use_dbl": {"default": True, "type": "bool", "label": "Run the N-day-low leg"},
    "use_pb": {"default": True, "type": "bool", "label": "Run the pullback leg"},
    "use_cap": {"default": True, "type": "bool", "label": "Run the capitulation leg"},
}

PARAM_GRID_PRESETS = {
    "Short  (WF-phase defaults)": {"trend_len": [200], "rsi_len": [2], "rsi_thr": [10], "rsi_exit": [5],
                                   "dbl_n": [7], "pb_ema": [20], "pb_hold": [10],
                                   "cap_mult": [1.5], "cap_q": [0.25], "cap_hold": [5]},
    "Medium (the WF drift range)": {"trend_len": [150, 200, 250, 300], "rsi_len": [2, 3], "rsi_thr": [10, 20, 30],
                                    "rsi_exit": [5], "dbl_n": [6, 7, 10, 15], "pb_ema": [5, 20], "pb_hold": [10],
                                    "cap_mult": [1.25, 1.5], "cap_q": [0.2, 0.25], "cap_hold": [4, 5]},
}


def _session_bounds(day_id, n):
    bounds = []; a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b)); a = b
    return bounds


def _third_weekday(year, month, weekday=2):
    """Date of the 3rd occurrence of `weekday` (0=Mon..6=Sun) in (year, month).
    weekday=2 -> 3rd Wednesday (the standard quarterly futures-roll reference)."""
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


from augur_engine.rolls import seam_days as detect_roll_seams  # the ONE audited seam calendar (tools/data/rolls_<ROOT>.csv); engine roll guard 2026-10-08 - this file's own day-level copy is retired (ROLL_AUDIT 09-25, MANAGER #54)


# ── TRUE ROLLS (NQDIP 1.2 / 1.3, 2026-09-26) ───────────────────────────────────────────
# ROLL_AUDIT.md 3.6: the day-level house detector above caught 20 of 65 NQ and 17 of 65 ES
# switches, and 1.0/1.1 then dropped the WHOLE overnight gap on every flagged night - real
# move included (ES 2020-03-09 -208.5 pts, NQ 2020-03-16 -560.5 pts disappeared). Here the
# switch comes from the committed ground-truth table tools/data/rolls_<ROOT>.csv
# (2026-10-02: the maintained table - exact Databento rows, then each later roll measured the evening
# it happens by tools/roll_watch.py; it replaced contract_switches_<ROOT>.csv + hard-coded 2026 rows,
# with identical values for every switch before 2026-09-14). Every bar BEFORE a switch is shifted by that switch's offset
# (Panama back-adjustment at bar level), so a held position books only the real move: the
# offset - and only the offset - leaves the P&L, wherever the switch falls (between sessions
# or, like 2026-09-14 11:30 ET, inside one). An in-bar splice rebuilds its bar as
# O' = O + offset, C unchanged, H = max(H', O', C), L = min(L', O', C) (audit 6.2).
# Every signal (SMA, RSI, EMA, N-day low, ATR, IBS, gaps) is shift-invariant, so it reads the
# adjusted series; SIZE reads the real traded price. detect_roll_seams stays in the file for
# reference only and is no longer called.
# yearly average price, used ONLY to tell an NQ master from an ES one (the engine does not pass
# the instrument); NQ has traded 1.6x-4x ES every year, so the geometric mean splits them.
_LEVELS = {2010: (1140, 1900), 2011: (1270, 2250), 2012: (1380, 2650), 2013: (1640, 3050),
           2014: (1930, 3850), 2015: (2060, 4400), 2016: (2090, 4600), 2017: (2440, 5900),
           2018: (2740, 6950), 2019: (2910, 7800), 2020: (3200, 10200), 2021: (4260, 14500),
           2022: (4100, 12500), 2023: (4300, 14000), 2024: (5400, 18900), 2025: (6000, 21000),
           2026: (6800, 25000)}
_SWITCH_CACHE = {}


def _switches(root):
    """[(utc_epoch_sec, offset_pts, in_bar), ...] for NQ or ES, sorted - read from the MAINTAINED roll table
    tools/data/rolls_<ROOT>.csv (exact Databento rows to 2026-03, then rows measured or estimated by
    tools/roll_watch.py the evening a roll happens; explicit not_a_roll rows are skipped)."""
    if root in _SWITCH_CACHE:
        return _SWITCH_CACHE[root]
    import csv, os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tools", "data", "rolls_%s.csv" % root)
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")) or r.get("offset_pts") in ("", None):
                continue
            out.append((int(r["switch_sec"]), float(r["offset_pts"]), r.get("kind") == "in_bar"))
    _SWITCH_CACHE[root] = sorted(out)
    return _SWITCH_CACHE[root]


def _root_of(idx, c):
    votes = 0
    for k in np.linspace(0, len(c) - 1, 25).astype(int):
        es, nq = _LEVELS.get(int(idx[k].year), _LEVELS[min(max(int(idx[k].year), 2010), 2026)])
        votes += 1 if c[k] > (es * nq) ** 0.5 else -1
    return "NQ" if votes > 0 else "ES"


def roll_adjust(o, h, l, c, index, root="auto"):
    """Back-adjusted copies of o/h/l/c and the switch bars [(bar, offset), ...]."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York")
    sec = (idx.tz_convert("UTC").asi8 // 10**9)
    if root == "auto":
        root = _root_of(idx, c)
    step = int(np.median(np.diff(sec[: min(len(sec), 500)]))) if len(sec) > 1 else 60
    adj = np.zeros(len(c)); events = []
    oa, ha, la = o.copy(), h.copy(), l.copy()
    for s, off, inbar in _switches(root):
        if s <= sec[0] or s > sec[-1] + step:
            continue
        if inbar:                                   # the bar whose span contains the switch
            b = int(np.searchsorted(sec, s, side="right")) - 1
            if b < 0 or s >= sec[b] + step:
                b = int(np.searchsorted(sec, s, side="left"))
        else:                                       # first bar starting at or after it
            b = int(np.searchsorted(sec, s, side="left"))
        if b >= len(c):
            continue
        adj[:b] += off
        if inbar and sec[b] < s:
            oa[b] = o[b] + off                      # before the splice: old contract
            ha[b] = max(h[b], oa[b], c[b]); la[b] = min(l[b], oa[b], c[b])
        events.append((b, off))
    oa = oa + adj; ha = ha + adj; la = la + adj; ca = c + adj
    return oa, ha, la, ca, sorted(events)


def _wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    if len(x) <= per:
        return np.full_like(x, 50.0)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def _sma(x, L):
    k = np.concatenate([[0.0], np.cumsum(x)]); s = np.full(len(x), np.nan)
    for d in range(L - 1, len(x)):
        s[d] = (k[d + 1] - k[d + 1 - L]) / L
    return s


def _ema(x, L):
    e = np.full(len(x), np.nan)
    if len(x) < L:
        return e
    e[L - 1] = x[:L].mean(); kk = 2.0 / (L + 1)
    for d in range(L, len(x)):
        e[d] = e[d - 1] + kk * (x[d] - e[d - 1])
    return e


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    asset: str = "auto", notional: int = 100000, cost_pts_rt: float = 0.783, cost_bps: float = 2.0,
    trend_len: int = 200, rsi_len: int = 2, rsi_thr: int = 10, rsi_exit: int = 5,
    dbl_n: int = 7, pb_ema: int = 20, pb_hold: int = 10,
    cap_mult: float = 1.5, cap_q: float = 0.25, cap_hold: int = 5,
    use_rsi: bool = True, use_dbl: bool = True, use_pb: bool = True, use_cap: bool = True,
    stop_atr: float = 0.0,
    return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50 or day_id is None or index is None or len(day_id) != n:
        return None
    bounds = _session_bounds(np.asarray(day_id), n)
    D = len(bounds)
    if asset == "auto":
        # a daily master has exactly one bar per session -> ETF model; an intraday
        # futures master has many bars per session -> NQ/MNQ model.
        asset = "ETF" if n == D else "NQ"
    trend_len, rsi_len, rsi_thr, rsi_exit = int(trend_len), int(rsi_len), int(rsi_thr), int(rsi_exit)
    dbl_n, pb_ema, pb_hold, cap_hold = int(dbl_n), int(pb_ema), int(pb_hold), int(cap_hold)
    if D < trend_len + 30:
        return None
    idx = pd.DatetimeIndex(index)
    do_raw = np.array([o[a] for a, b in bounds])           # the price actually traded
    if asset == "NQ":
        c_raw0 = c
        o, h, l, c, rolls = roll_adjust(o, h, l, c, idx, _ignore.get("roll_root", "auto"))
        shift = c - c_raw0                                  # adjusted minus traded price, per bar
    else:
        rolls = []
        shift = np.zeros(n)
    roll_bars = np.array([b for b, _ in rolls], dtype=np.int64)
    do = np.array([o[a] for a, b in bounds]); dh = np.array([h[a:b].max() for a, b in bounds])
    dl = np.array([l[a:b].min() for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
    open_bar = np.array([a for a, b in bounds]); close_bar = np.array([b - 1 for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]

    trend = _sma(dc, trend_len)
    rsi = _wilder_rsi(dc, rsi_len); rsi_x = _sma(dc, rsi_exit)
    ema = _ema(dc, pb_ema)
    atr20 = np.full(D, np.nan)
    for d in range(20, D):
        atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()

    def size(entry_px):
        if asset == "NQ":
            k = max(1, int(round(float(notional) / (entry_px * 2.0))))     # whole MNQ micros
            return k * 2.0, cost_pts_rt * 2.0 * k                          # $/pt, $ cost per RT
        sh = float(notional) / entry_px
        return sh, float(notional) * cost_bps / 10000.0

    def chain_to(de, xbar, xadj, entry_px):
        """long entered at day de's open, exited at bar xbar at ADJUSTED price xadj."""
        dollars_per_pt, cost = size(entry_px)
        crossed = int(((roll_bars > open_bar[de]) & (roll_bars <= xbar)).sum())
        return (xadj - do[de]) * dollars_per_pt - cost - 0.25 * dollars_per_pt * crossed

    def chain(de, dx, entry_px):
        """dollar PnL for a long entered at day de's open (real price entry_px), exited at
        day dx's open: the move on the adjusted series, so every real gap is in and every
        contract offset is out; 0.25 pt per switch crossed while held."""
        dollars_per_pt, cost = size(entry_px)
        crossed = int(((roll_bars > open_bar[de]) & (roll_bars <= open_bar[dx])).sum())
        cost += 0.25 * dollars_per_pt * crossed
        return (do[dx] - do[de]) * dollars_per_pt - cost

    legs = [("RSI", use_rsi), ("DBL", use_dbl), ("PB", use_pb), ("CAP", use_cap)]
    trade_log = []
    for mech, on in legs:
        if not on:
            continue
        pos = 0; de = 0; d = max(trend_len, 30); stop_lvl = np.nan
        while d < D - 1:
            if _stop_event is not None and _stop_event.is_set():
                return None
            if pos == 0:
                s = False
                if mech == "RSI":
                    s = dc[d] > trend[d] and rsi[d] < rsi_thr
                elif mech == "DBL":
                    s = d >= dbl_n and dc[d] > trend[d] and dc[d] == dc[d - dbl_n + 1:d + 1].min()
                elif mech == "PB":
                    s = dc[d] > trend[d] and dl[d] <= ema[d] and dc[d - 1] > ema[d - 1]
                else:
                    rng = dh[d] - dl[d]
                    s = (dc[d] < do[d] and rng > 0 and not np.isnan(atr20[d]) and rng >= cap_mult * atr20[d]
                         and (dc[d] - dl[d]) / rng <= cap_q)
                if s:
                    pos, de = 1, d + 1
                    stop_lvl = (do[de] - stop_atr * atr20[de]) if stop_atr > 0 else np.nan
                    d += 1; continue
            else:
                if stop_atr > 0 and not np.isnan(stop_lvl):
                    hit = None
                    if do[d] <= stop_lvl:
                        hit = (int(open_bar[d]), float(do[d]))
                    elif dl[d] <= stop_lvl:
                        a_, b_ = bounds[d]
                        k_ = a_ + int(np.argmax(l[a_:b_] <= stop_lvl))
                        hit = (k_, float(o[k_]) if o[k_] <= stop_lvl else float(stop_lvl))
                    if hit is not None:
                        xb, xadj = hit
                        entry_px = float(do_raw[de])
                        trade_log.append((int(open_bar[de]), xb, float(chain_to(de, xb, xadj, entry_px)), 1,
                                          entry_px, float(xadj - shift[xb])))
                        pos = 0; d += 1; continue
                ex = False
                if mech == "RSI":
                    ex = dc[d] > rsi_x[d]
                elif mech == "DBL":
                    ex = dc[d] == dc[d - dbl_n + 1:d + 1].max()
                elif mech == "PB":
                    ex = (dc[d] > dh[de - 1]) or (d - de >= pb_hold)
                else:
                    ex = (d - de >= cap_hold)
                if d >= de and ex:
                    entry_px = float(do_raw[de]); exit_px = float(do_raw[d + 1])
                    pnl = chain(de, d + 1, entry_px)
                    # always keep the full log: the equity curve (and so the drawdown)
                    # must be built in EXIT-time order across the four legs, never in
                    # per-mechanism order.
                    trade_log.append((int(open_bar[de]), int(open_bar[d + 1]), float(pnl), 1,
                                      entry_px, exit_px))
                    pos = 0
            d += 1
    if not trade_log:
        return None
    trade_log.sort(key=lambda t: (t[1], t[0]))          # realization (exit) order
    pnls = np.array([t[2] for t in trade_log], float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ── OPEN-TRADE VALUES FOR A BOOK (2026-09-25) ─────────────────────────────────────────
# t[2] is DOLLARS at this file's own size and a book runs the file at mult 1, so the book's
# generic open-trade mark - side x (close - entry) x mult - valued an open position at $1 a
# point; and chain() leaves each quarterly roll gap out of the P&L, which a close-minus-entry
# mark cannot know. This hook values the position exactly as chain() prices it: size() - whole
# MNQ micros at $2/pt on an intraday master, shares for the notional on a daily one - and the
# contract offset of every switch crossed so far left out (true rolls, 1.2/1.3). See augur_engine/book.py _plugin_marks.
PNL_UNITS = "usd"


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Each trade's open value in dollars at the close of every session it is held through,
    before the session it exits in: one [(bar, usd), ...] list per trade, in trade order (None
    for a trade whose bars are not session opens). Costs, including the per-roll charge, are
    left out - they land on the exit day with the rest of the closed P&L."""
    p = {k: v.default for k, v in _inspect.signature(run_backtest).parameters.items()
         if v.default is not _inspect.Parameter.empty}
    p.update(params)
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    n = len(c)
    if day_id is None or index is None or len(day_id) != n:
        return None
    bounds = _session_bounds(np.asarray(day_id), n)
    asset = p["asset"]
    if asset == "auto":
        asset = "ETF" if n == len(bounds) else "NQ"
    idx = pd.DatetimeIndex(index)
    if asset == "NQ":
        h = np.asarray(highs, float); l = np.asarray(lows, float)
        o, _h, _l, c, _r = roll_adjust(o, h, l, c, idx, p.get("roll_root", "auto"))
    do = np.array([o[a] for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
    sess = {int(a): j for j, (a, b) in enumerate(bounds)}
    bar_sess = np.empty(n, dtype=np.int64)
    for j, (a, b) in enumerate(bounds):
        bar_sess[a:b] = j
    notional = float(p["notional"])
    out = []
    for t in trades:
        de = sess.get(int(t[0]))
        dx = int(bar_sess[int(t[1])]) if 0 <= int(t[1]) < n else None   # a stop exits mid-session
        if de is None or dx is None:
            out.append(None)
            continue
        side, ep = float(t[3]), float(t[4])
        dpp = max(1, int(round(notional / (ep * 2.0)))) * 2.0 if asset == "NQ" else notional / ep
        marks = []
        for j in range(de, dx):                 # adjusted move since the entry open
            marks.append((int(bounds[j][1] - 1), side * (float(dc[j]) - float(do[de])) * dpp))
        out.append(marks)
    return out

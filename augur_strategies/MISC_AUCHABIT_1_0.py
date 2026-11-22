# AUGUR-SOURCE: claude-review
"""MISC AUCHABIT 1.0 - closing-auction habit on the point-in-time top 100: at the 15:50 print buy the 5 names whose
15:50 -> official-close excess return has been highest over the last 60 sessions and short the 5 lowest, exit MOC.

Provenance: OPUS-HUNT round 8 (strategy-23 siblings), strategy 86 AUCTION-HABIT r1, cell 86a
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S86: PREREG.md, RESULTS.md, s86_lib.py, s86_build.py, s86_run.py,
trades_86a.csv, series.pkl '86a'). Defaults = cell 86a exactly (habit 60 sessions, k 5, $40 floor, both legs).
Mechanism (prereg): same-clock periodicity (Heston-Korajczyk-Sadka) in the closing-auction window - recurring by-name
closing flow (index / ETF / fund rebalancing, recurring MOC imbalances) makes a name's 15:50 -> close excess return
persist across sessions.
Parity (tools/misc_auchabit_parity.py, 2017-04-01 .. 2025-06-30): 20,540 of 20,540 picks (day, name, side) with the
same fill return, 2,054 of 2,054 sessions through the engine, net $46,591.79 = the hunt's to the cent (max day
difference $0.00); cell 86c (weekday_habit ON, period_len 20) 20,410 of 20,410 picks, 2,041 of 2,041 sessions.

NOT A BLIND READ. The hunt read 86a once on 2017-04 .. 2025-06 (2017-04 .. 2020-12 had been seen by the proposer;
2021-01 .. 2025-06 judged once): FAIL under the old strict bars (Route A: 2023-25H1 net t 0.63 < 2; Route B: book
lift vs #463 +12.2 ROC inside the no-edge band, -5.3 ROC vs #463 + strategy 23). It passes the owner's loose screen
(11-14: 249 trades a year, +$5.2k a year at $100k a side, leg max DD $5.5k; warnings "one episode", control pct 85),
and the walk-forward basket S127 picked strategy 86 in 7 of 7 test folds (127a, trailing t >= 1: 86d in fold 2, 86a
in folds 3-8; 127c, t >= 2: 86a in 6 of 7). The engine's 12-month lockbox (2025-07 .. 2026-06) was never read by the
hunt and was not read building this file.

OVERLAP WITH PICK6 (strategy 23, MISC_EODREV_1_2). Same universe, same exit print, and 86a's 15:50 -> close window lies
inside 23's 15:30 -> close hold and inside 23's own habit input. Daily net of 86a vs PICK6 (s25 'U100-k5 X composite',
1 cent, $100k a side), 2017-04-01 .. 2025-06-30, zero on no-trade days: correlation 0.168 (0.168 on the 2,048 days both
trade; 2017-04 .. 2020-12 0.136, 2021-01 .. 2025-06 0.185). Hunt: the habit score's mean daily rank correlation with
23's composite is 0.42; 86a holds 2.17 of 23's 10 names a day on the same side; with 23's picks removed (cell 86b) the
2023-25 edge is gone. Read any book add against "#463 + 23", not #463 alone.

-- The rule -----------------------------------------------------------------------------
FULL session d = SPY has a 10-minute bar starting 15:50 ET on d and d is not a NYSE 13:00 early close (frozen list;
every early close carries a SPY 15:50 bar from after-hours prints). Rolling windows run on FULL sessions only.
Universe U(d): names in the point-in-time top-100 list of year(d), raw close of the previous TRADING day (half days
count) >= `min_price`, and a 15:50 bar on d (its open O50 is the entry print).
R(i,d) = official close(i,d) / O50(i,d) - 1 for every name on every FULL session with both prints (member or not);
R := missing if |R| > 5% or if the official close is > 8% off the 15:50 bar's close (the s25 data-mismatch guard).
XA(i,d) = R(i,d) - the mean R of that day's U(d) names (XA kept for every name with R).
HABIT S(i,d) = mean XA(i,.) over the `period_len` FULL sessions before d (at least 75 pct of them present);
`weekday_habit` ON = over the previous `period_len` FULL sessions on d's weekday (hunt cell 86c = ON with 20).
Session d trades when >= 4 x `k` names of U(d) have S (20 at k 5 = the prereg). Long the `k` highest S, short the `k`
lowest (ties: the alphabetically first symbol ranks first). Entry at O50, exit = MOC sent with the entry, filled at
the official close. `legs`: 0 = both (86a), 1 = the long leg only, 2 = the short leg only. A picked name whose R is
missing (the two guards above, or no official close) is dropped that day, not replaced.

INFORMATION TIMES (all known at the 15:50 entry print):
  * S averages XA of sessions before d only (shifted one FULL session) - day d's own R is the FILL, never an input;
  * XA's cross-sectional mean on a past day uses that day's closes, known by that close;
  * the price floor reads the previous trading day's RAW close; membership is the year's list, fixed in advance
    (built from the prior year's dollar volume);
  * a name enters the ranking when it has a 15:50 print. The prereg's universe also required the day's official close
    to exist - known only after the close, so the plugin drops that clause (0 such name-days in 2017-2025H1: 86a's
    picks are unchanged). A pick with no official close simply has no fill.
  * NOT an information-time rule, kept from the hunt for parity: the |R| > 5% and 8% mismatch guards read the day's
    close and drop the pick from the P&L. They touched 2 picks of 86a (2020-03-16 LRCX, 2020-03-18 DIS; keeping their
    true fills adds $97) and none after 2020.

-- Data ---------------------------------------------------------------------------------
THE MASTER IS ONLY THE CLOCK (SPY 5m RTH, alpaca_split_rth): the trade sits on the master's 15:50 bar (entry) and the
session's last bar (the 16:00 close). Prices come from the pinned side panel
    C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_v1.npz   (built by tools/misc_auchabit_panel.py)
= the hunt's exact inputs (tbis_r3 / eodrev_u100 10-minute SIP split-adjusted bars: the 15:50 bar's open and close;
siporb daily split close = the official close, daily raw close = floor and cent cost only), 199 names = the
2017-2026 point-in-time top-100 lists, 2016-01-04 .. 2026-06-30. 2016 has no list, so XA starts 2017-01-03 and the
first trade is 2017-03-09 (45 of 60 sessions; the hunt counts trades from 2017-04-01). On 2016-01-04 .. 2025-06-30 the
panel is bit-identical to the hunt's panel.pkl. No panel on the machine (CI, the box) -> the file returns None (no
trades), never a guess.

-- Sizing and costs (INSIDE the plugin - job cost_pts 0, mult 1) --------------------------
`notional` dollars a side, notional / k a name ($20,000 at k 5); a dropped pick is not re-sized.
PnL a name = side x notional / k x R. Cost a name = notional / k x (`spread_cents` / 100 / previous raw close +
2 x `fee_bps` x 1e-4): one cent a share at the 15:50 entry, the MOC exit pays no spread, 0.3 bp a crossing (the
prereg's PRIMARY cost). Borrow 0 (megacaps). PnL is DOLLARS in the trade tuple's field 2; ONE trade a session = the
whole basket.

-- Auto-Validate ranges -------------------------------------------------------------------
period_len 20..120 step 20 (6), k 3..10 (8), min_price 0..80 step 20 (5), weekday_habit (2), legs 0..2 (3) are OPEN:
1,440 combos, 86a on-grid; auto-expand fences: period_len 10..250, k 1..15, min_price 0..200, legs 0..2.
notional, spread_cents and fee_bps are pinned. No weight knob: the rule has no composite and names are equal dollars.
Not knobs: the 86b "ex-23" exclusion (another strategy's picks, not this rule's knob) and the 86d O50 -> 15:50-bar-close
twin (an artefact check: the bar's close is the closing-cross print in this SIP data, so as an exit it would duplicate
86a with no order type behind it).
"""
import hashlib
import io
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC AUCHABIT 1.0 · closing-auction habit on the point-in-time top 100 (opus hunt 86a)'
DESCRIPTION = ("At the 15:50 print buy the k names of the year's top-100 stocks whose 15:50-to-official-close return "
               "(less the day's average) has been highest over the last 60 sessions and short the k lowest, $20k a "
               "name; every position leaves at the closing auction. The SPY 5m master is the clock only; prices come "
               "from a pinned side panel. Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "SPY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_v1.npz"
PANEL_SHA256 = "e7de7ff79afa137f14d0a989a45d10e693e2b6d9ec8bacb8b95bb81e05a2b6e1"

# AS-IF EXTENSION (2026-11-21, the book as-if series only - tools/book_asif_series.py). UNSET (the default, the runner,
# every validate) = the pinned panel alone, exactly as run #526 read it. SET to a side panel of the same layout and
# every session AFTER the pinned panel's last date is scored on that panel, computed on its own rows only (no splice: a
# split-basis change between the two builds never enters a return). Everything up to the pinned end still comes from the
# pinned, sha-checked panel. A set path that does not exist raises - never a silent fall-back. Never set it on the
# runner or for a validate.
PANEL_EXT_ENV = "MISC_AUCHABIT_1_0_PANEL_EXT"

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Dollars a side",
                 "tooltip": "Fixed. Longs and shorts each total this many dollars, notional / k a name ($20,000 at k 5)."},
    "spread_cents": {"default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
                     "label": "Entry cost (cents a share)",
                     "tooltip": "Fixed: one cent a share at the 15:50 entry (at yesterday's raw close). The closing auction is charged no spread."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "step": 0.1, "type": "float",
                "label": "Fees (bp a crossing)", "tooltip": "Fixed: 0.3 bp of a name's notional at the entry and again at the exit."},
    "period_len": {"hard_min": 10, "hard_max": 250, "default": 60, "min": 20, "max": 120, "step": 20, "type": "int",
                   "label": "Habit window (sessions)",
                   "tooltip": "Full sessions averaged for each name's 15:50-to-close habit (75% must be present). Ends the session before."},
    "k": {"hard_min": 1, "hard_max": 15, "default": 5, "min": 3, "max": 10, "step": 1, "type": "int",
          "label": "Names a side", "tooltip": "Buy the k highest habits, short the k lowest. A session needs 4 x k ranked names."},
    "min_price": {"hard_min": 0, "hard_max": 200, "default": 40, "min": 0, "max": 80, "step": 20, "type": "int",
                  "label": "Price floor ($)",
                  "tooltip": "Only names whose previous raw close is at least this. Keeps the one-cent cost small."},
    "weekday_habit": {"default": False, "type": "bool", "label": "Same-weekday habit",
                      "tooltip": "ON = average the habit over the previous sessions on the same weekday only (hunt cell 86c = ON with 20)."},
    "legs": {"hard_min": 0, "hard_max": 2, "default": 0, "min": 0, "max": 2, "step": 1, "type": "int",
             "label": "Legs (0 both, 1 long, 2 short)",
             "tooltip": "0 = long the k highest and short the k lowest (86a); 1 = the long leg only; 2 = the short leg only."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 86a)": {"period_len": [60], "k": [5], "min_price": [40], "weekday_habit": [False],
                                   "legs": [0]},
    "Medium (the hunt's cells + neighbours)": {"period_len": [20, 40, 60, 120], "k": [3, 5, 10],
                                               "min_price": [20, 40, 60], "weekday_habit": [False, True],
                                               "legs": [0, 1, 2]},
}

PNL_UNITS = "usd"

_MIS = 0.08                  # |official close / 15:50 bar close - 1| above this = a data mismatch (s25 guard)
_BIG = 0.05                  # |R| above this = no fill (hunt rule)
_CACHE = {}                  # per-process: the panel (its own XA and daily-PnL caches live inside it)


def _prepare(dates, names, full, o50, c50, dc, raw, member):
    """Everything that does not depend on a parameter, on the FULL-session rows (the hunt's s86_lib.setup())."""
    dates = np.asarray(dates, np.int64)
    full = np.asarray(full, bool)
    rawf = np.asarray(raw, np.float64)
    prev_raw = np.full_like(rawf, np.nan)
    prev_raw[1:] = rawf[:-1]                     # the previous TRADING day's raw close (half days are rows too)
    f = np.flatnonzero(full)
    o = np.asarray(o50, np.float64)[f]
    c = np.asarray(c50, np.float64)[f]
    d = np.asarray(dc, np.float64)[f]
    with np.errstate(divide="ignore", invalid="ignore"):
        r0 = d / o - 1.0                          # 15:50 bar open -> official close: day d's FILL
        mis = np.abs(d / c - 1.0) > _MIS          # NaN -> False (no 15:50 close = no mismatch test)
        big = np.abs(r0) > _BIG
    R = np.where(mis | big, np.nan, r0)
    fd = dates[f]
    wd = pd.to_datetime(pd.Series(fd).astype(str), format="%Y%m%d").dt.dayofweek.to_numpy()
    cols = list(names)
    return {"dates": fd, "names": cols, "wd": wd,
            "R": pd.DataFrame(R, columns=cols).copy(),
            "rp": np.asarray(prev_raw[f], np.float64),
            "o50ok": np.isfinite(o),
            "member": np.asarray(member, bool)[f],
            "xa": {}, "day": {}}


def _read_panel(path=None, pinned=True):
    """The pinned panel's arrays, or None when the file is not on this machine (sha-checked). `path` + `pinned=False`
    = the as-if extension panel (PANEL_EXT_ENV), not sha-checked."""
    if path is None:
        path = PANEL_PATH
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        raw = fh.read()
    if pinned and hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
        raise RuntimeError("MISC_AUCHABIT_1_0: side panel %s is not the pinned build" % path)
    z = np.load(io.BytesIO(raw), allow_pickle=False)          # the bytes that were hashed are the bytes loaded
    a = {key: z[key] for key in ("dates", "full", "o50", "c50", "dc", "raw", "member")}
    a["names"] = [str(x) for x in z["names"]]
    return a


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    a = _read_panel()
    p = None if a is None else _prepare(**a)
    _CACHE["panel"] = p
    return p


def _ext():
    """The prepared as-if extension panel, or None when PANEL_EXT_ENV is unset (the default)."""
    path = (os.environ.get(PANEL_EXT_ENV) or "").strip()
    if not path:
        return None
    key = ("ext", os.path.abspath(path))
    if key not in _CACHE:
        a = _read_panel(path, pinned=False)
        if a is None:
            raise RuntimeError("MISC_AUCHABIT_1_0: %s names %s, which does not exist" % (PANEL_EXT_ENV, path))
        _CACHE[key] = _prepare(**a)
    return _CACHE[key]


def _elig(p, min_price):
    """U(d): member of year(d)'s list, previous raw close >= floor, a 15:50 print today. Known at 15:50."""
    with np.errstate(invalid="ignore"):
        return p["member"] & (p["rp"] >= float(min_price)) & p["o50ok"]


def _xa(p, min_price):
    key = float(min_price)
    if key not in p["xa"]:
        R = p["R"]
        el = pd.DataFrame(_elig(p, min_price), columns=R.columns)
        m = R.where(el).mean(axis=1)              # that day's U(d) mean (members only), every name keeps its XA
        p["xa"][key] = R.sub(m, axis=0)
    return p["xa"][key]


def _habit(p, L, min_price, weekday):
    """S(i,d): mean XA over the L FULL sessions (or the L same-weekday FULL sessions) BEFORE d."""
    X = _xa(p, min_price)
    L = int(L)
    mp = int(L * 0.75)
    if not weekday:
        return X.rolling(L, min_periods=mp).mean().shift(1).to_numpy()
    out = np.full(X.shape, np.nan)
    for g in range(5):
        r = p["wd"] == g
        out[r] = X.loc[r].rolling(L, min_periods=mp).mean().shift(1).to_numpy()
    return out


def _picks(p, period_len, k, min_price, weekday_habit):
    """[(FULL-row index, long column indices, short column indices)] of every session that ranks >= 4 x k names.
    Reads only S (sessions before d) and U(d) (known at 15:50) - never day d's closes."""
    k = int(k)
    S = np.where(_elig(p, min_price), _habit(p, period_len, min_price, weekday_habit), np.nan)
    out = []
    for i in range(len(S)):
        idx = np.flatnonzero(np.isfinite(S[i]))
        if len(idx) < 4 * k:
            continue
        v = S[i, idx]
        hi = idx[np.argsort(-v, kind="stable")[:k]]      # highest S -> long; ties -> the earlier (alphabetical) name
        lo = idx[np.argsort(v, kind="stable")[:k]]       # lowest S -> short
        out.append((i, hi, lo))
    return out


def _daily(p, notional, spread_cents, fee_bps, period_len, k, min_price, weekday_habit, legs):
    """(dates int64 yyyymmdd, net $) of every FULL session the config trades."""
    key = (float(notional), float(spread_cents), float(fee_bps), int(period_len), int(k), float(min_price),
           bool(weekday_habit), int(legs))
    if key in p["day"]:
        return p["day"][key]
    Rv = p["R"].to_numpy()
    rp = p["rp"]
    N = float(notional) / int(k)                 # dollars a name
    cents = float(spread_cents) / 100.0
    bp = 2 * float(fee_bps) * 1e-4               # entry + exit fees
    use_l, use_s = int(legs) in (0, 1), int(legs) in (0, 2)
    rows, nets = [], []
    for i, hi, lo in _picks(p, period_len, k, min_price, weekday_habit):
        gl = gs = cl = cs = 0.0
        if use_l:
            rl = Rv[i, hi]
            gl = N * np.nansum(rl)                      # a pick with no R (guards / no close) is dropped, not replaced
            cl = np.sum(cents / rp[i, hi[np.isfinite(rl)]] + bp)
        if use_s:
            rs = Rv[i, lo]
            gs = -N * np.nansum(rs)
            cs = np.sum(cents / rp[i, lo[np.isfinite(rs)]] + bp)
        rows.append(i)
        nets.append(gl + gs - N * (cl + cs))
    out = (p["dates"][np.asarray(rows, np.int64)], np.asarray(nets, np.float64))
    p["day"][key] = out
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, spread_cents: float = 1.0, fee_bps: float = 0.3,
                 period_len: int = 60, k: int = 5, min_price: int = 40, weekday_habit: bool = False,
                 legs: int = 0, return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None:
        return None
    p = _panel()
    if p is None:
        return None
    o = np.asarray(opens, float)
    c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    dd, net = _daily(p, notional, spread_cents, fee_bps, period_len, k, min_price, weekday_habit, legs)
    x = _ext()
    if x is not None:                                # as-if only: sessions after the pinned panel's last date
        xd, xn = _daily(x, notional, spread_cents, fee_bps, period_len, k, min_price, weekday_habit, legs)
        keep = xd > int(p["dates"][-1])
        dd, net = np.concatenate([dd, xd[keep]]), np.concatenate([net, xn[keep]])
    trades = []
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [n]])
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        j = int(np.searchsorted(dd, date[a]))
        if j >= len(dd) or dd[j] != date[a]:
            continue
        m = minute[a:b]
        e = np.flatnonzero(m == 950)                 # the bar that opens 15:50 ET: the entry print
        if len(e) == 0 or m[-1] < 955 or (b - 1) <= a + int(e[0]):
            continue                                  # no 15:50 bar, or the session's close is not in the bars yet
        eb = a + int(e[0])
        xb = b - 1                                    # the session's last bar: its close is the 16:00 close
        trades.append((int(eb), int(xb), float(net[j]), 1, float(o[eb]), float(c[xb])))
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


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Every basket enters at the 15:50 print and leaves at that SAME session's closing auction, so no trade is ever
    held through a session close: one empty mark list per trade."""
    return [[] for _ in (trades or [])]

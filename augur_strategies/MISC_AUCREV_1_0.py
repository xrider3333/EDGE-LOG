# AUGUR-SOURCE: claude-review
"""MISC AUCREV 1.0 - 15:50 auction-window reversal on the point-in-time top 100 (Nasdaq-listed names), $100k a
side, in at the 15:50 print, out at the official close of the SAME session.

Provenance: OPUS-HUNT round 8 (strategy-23 sibling round, lens sib-auction), strategy 85 (AUCREV10 r1), verdict
cell 85a (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S85: PREREG.md, RESULTS.md, s85_lib.py, s85_build.py,
s85_run.py, daily_85a.csv, series.pkl['85a']). Defaults = cell 85a exactly. Sibling of strategy 23 (PICK6,
MISC_EODREV_1_2.py): different clock and window, but the window sits INSIDE 23's 15:30 -> close hold, so the same
name on the same side doubles 23 (the hunt measured 30% of 85a's name-trades on 23's k5 side, daily corr 0.32).
NOT A BLIND READ: the proposer's scan spent 2017-04..2020-12 (DISC) on this exact signal, and the hunt read cell
85a once on 2021-01..2025-06 (CONF). Verdict under the old strict bars: DEAD - a fail, no route earned (Route A
missed two of five lines: H1 / H2 net t 0.08 / -1.52 and CONF at double cost -$71k; CONF net at BASE cost -$8.5k;
gross decays from 5.8 bp a day in 2017-20 to 1.2 bp in 2023-25 against ~2.7 bp of cost). It passes the owner's
loose screen (owner_screen_1114: 248 trades a year, $2.0k a year; warnings t 4.1/-1.1, loses at 2x cost, one
episode, control pct 60), and the walk-forward basket S127 picked strategy 85 in 7 of 7 folds (cell 85a in 6, 85c
in the first). The engine's 2025-07..2026-06 lockbox was never read by the hunt. This file exists so the engine's
Auto-Validate can judge it.

-- The rule -----------------------------------------------------------------------------
Session t is traded only when it is FULL (not on the frozen NYSE half-day list, SPY has its 15:50 bar). Name i is
eligible on t when
  * it is a member of year(t)'s point-in-time top 100 (top 100 by the PRIOR year's median dollar volume,
    universe_pit100.json, SPY excluded),
  * its listing is Nasdaq (`nasdaq_only`; the CURRENT siporb assets.csv exchange, frozen - not point-in-time),
  * its raw close of t-1 is >= `min_price`,
  * its 15:40 bar of t (and its 15:30 bar when `freeze_1540`) and its 15:50 bar of t-1 exist (t-1 = the previous
    session; the day after a half day has no usable t-1 15:50 bar -> no trade; no forward fill anywhere).
  beta_i  = OLS slope of i's 15:50-close-to-15:50-close return on SPY's over `beta_len` sessions (at least two
            thirds of them and >= 20) ending t-1, clipped 0.3 .. 2.5, 1.0 while undefined (`beta_adjust` off ->
            1.0 for every name). The hunt's s25 convention: returns on the full session list (a return across a
            half day spans two sessions; half-day post-close prints included).
  r_i     = close of i's 15:40 bar (the 15:50:00 price) / i's t-1 15:50-bar close - 1;
            `freeze_1540` on = the close of the 15:30 bar (the 15:40:00 price) instead - the hunt's bounce guard 85d.
  resid_i = r_i - beta_i x r_SPY (SPY on the same clock).
When at least `min_names` names have a resid: BUY the `k` lowest resid (pushed down hardest against the market),
SHORT the `k` highest, equal dollars a name, at the OPEN of the 15:50 bar; ties by symbol (pandas rank 'first' on
alphabetical columns). `legs` 1 / 2 keep only the long / the short side. EXIT: the official closing print of the
SAME session (an MOC order sent with the entry; fill = the daily split-adjusted close). Flat every night: a trade
belongs to session t alone and nothing is held overnight.
DATA HYGIENE, applied AFTER the pick and never a substitute: a picked name whose 15:50 bar or official close is
missing, or whose official close is more than 8% off its own 15:50-bar close (a bad or misadjusted print, the
hunt's s25 mismatch filter), is dropped from that day's side and its slot is NOT refilled. (The hunt applied the
filter before ranking; moved here so no post-entry print can choose a name. Same picks on 2017-04..2025-06.)

INFORMATION TIMES (all known at 15:50:00 ET, before the entry print):
  * membership = a calendar-year list built from the prior year's data; listing = a frozen table;
  * the price floor and the cent cost read the raw close of t-1;
  * beta's rolling window ends t-1 (shift 1) and reads 15:50-bar closes of sessions <= t-1 only;
  * r_i reads the 15:40 bar (15:40-15:50, closed at 15:50:00) or the 15:30 bar, and t-1's 15:50-bar close;
  * the day's count (>= `min_names`) and both ranks read only the above.
The 15:50-bar open (the fill), the 15:50-bar close of t, the official close of t (the exit) and the raw close of t
are read only for the PnL and the post-pick hygiene drop; tests/test_misc_aucrev.py scrambles them (and drops every
later session) and checks that no pick moves.

-- Data ---------------------------------------------------------------------------------
THE MASTER IS ONLY THE CLOCK (SPY 5m RTH, alpaca_split_rth): a trade enters on the clock's 15:50 bar and exits on
its 15:55 bar (the 16:00 close), both of the same session; a day whose bars do not run to a final 15:55 bar (a half
day, a gap, a non-RTH feed) gives no trade. Prices come from the pinned side panel
    C:/EdgeLog/alpaca_cache/aucrev_panel/aucrev_panel_v1.npz   (built by tools/misc_aucrev_panel.py)
with the harness's exact inputs (tbis_r3 / eodrev_u100 10-minute SIP split-adjusted bars at 15:30 / 15:40 / 15:50,
siporb daily split / raw closes, universe_pit100.json 2017 .. 2026, siporb assets.csv listing), 2016-01-04 ..
2026-06-30; identical to the hunt's panel.pkl on 2016-01-04 .. 2025-06-30. Members start 2017-01-03 (the
universe's first year); 2016 rows only feed beta. No panel on the machine (CI, the box) -> the file returns None
(no trades), never a guess.
Known limits, all the hunt's own: the listing is today's, so names that moved NYSE -> Nasdaq inside the window
(PEP 2017, HON 2021, LIN 2023, WMT 2024, per the hunt's notes) count as Nasdaq throughout; the rule has no
corporate-action guard, so a spin-off or distribution left unadjusted by the split feed reads as a move (RTX
2020-04-03, AABA 2019-09-24 in the hunt window; HON 2026-06-29, whose split-adjusted series halves that day, in
the lockbox).

-- Sizing and costs (INSIDE the plugin - job cost_pts 0, mult 1) --------------------------
`notional` dollars a side, equal dollars a name ($20k at k 5). PnL = notional x (mean long return - mean short
return). Cost a name = `spread_cents` / raw close(t-1) at the entry (NYSE names pay it again at the exit when
`nasdaq_only` is off: an NYSE MOC after 15:50 is not guaranteed - the hunt's cell 85c) + `fee_bps` at the entry +
`fee_bps` at the exit (the closing auction is charged no spread), averaged over the side's names and x notional,
exactly the hunt's BASE cost (0.01 / raw + 0.6 bp). Borrow 0 (megacaps), dividends not modelled (intraday). PnL is
DOLLARS in the trade tuple's field 2; ONE trade a session = the whole basket.

-- Auto-Validate ranges -------------------------------------------------------------------
OPEN: k 3 .. 10, beta_len 20 .. 140 step 20 (searched only with beta_adjust on), min_price 0 .. 80 step 20,
beta_adjust, freeze_1540 (the prereg's 15:40 freeze, cell 85d), nasdaq_only (off = the prereg's all-listings
cell 85c with NYSE at the house cost), legs (0 both, 1 long only, 2 short only); cell 85a on the grid.
PINNED: notional, spread_cents, fee_bps, min_names. Grid 8 x 7 x 5 x 2 x 2 x 2 x 3 = 6,720 combinations
(3,840 distinct: beta_len collapses to its default when beta_adjust is off).
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC AUCREV 1.0 · 15:50 auction-window reversal, point-in-time top-100 Nasdaq names (opus hunt 85a)'
DESCRIPTION = ("At 15:50 ET rank the year's top-100 Nasdaq-listed stocks on the day's move (yesterday's 15:50 close "
               "to the 15:50 price) less beta x SPY's; buy the 5 pushed down hardest and short the 5 pushed up "
               "hardest ($100k a side) at the 15:50 print, exit at the official close the same day. The SPY 5m "
               "master is the clock only; stock prices come from a pinned side panel. Costs inside the plugin -> "
               "job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "SPY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/aucrev_panel/aucrev_panel_v1.npz"
PANEL_SHA256 = "f62d5b843f15fa6e86fa61de4f90ca60920e12ab92635b88cfd297b89143a325"

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "hard_min": 100000, "hard_max": 100000,
                 "label": "Dollars a side",
                 "tooltip": "Fixed. Longs and shorts each total this many dollars, equal per name."},
    "spread_cents": {"default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
                     "hard_min": 1.0, "hard_max": 1.0,
                     "label": "Entry cost (cents a share)",
                     "tooltip": "Fixed: one cent a share at the 15:50 entry print. The closing auction pays no spread "
                                "(NYSE names pay it again when Nasdaq-only is off)."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "step": 0.1, "type": "float",
                "hard_min": 0.3, "hard_max": 0.3,
                "label": "Fees (bp a print)", "tooltip": "Fixed: 0.3 bp of notional at the entry and 0.3 bp at the exit."},
    "min_names": {"default": 20, "min": 20, "max": 20, "step": 1, "type": "int",
                  "hard_min": 20, "hard_max": 20,
                  "label": "Names needed to trade",
                  "tooltip": "Fixed: a session trades only when at least this many names are eligible (the hunt's rule)."},
    "k": {"default": 5, "min": 3, "max": 10, "step": 1, "type": "int", "hard_min": 1, "hard_max": 10,
          "label": "Names a side", "tooltip": "Buy the k lowest residual moves, short the k highest."},
    "beta_len": {"default": 60, "min": 20, "max": 140, "step": 20, "type": "int", "hard_min": 20, "hard_max": 250,
                 "depends_on": {"beta_adjust": True},
                 "label": "Beta window (sessions)",
                 "tooltip": "Trailing sessions of 15:50-to-15:50 returns for each name's beta to SPY; ends the session before."},
    "min_price": {"default": 40, "min": 0, "max": 80, "step": 20, "type": "int", "hard_min": 0, "hard_max": 200,
                  "label": "Price floor ($)",
                  "tooltip": "Only names whose prior raw close is at least this. Keeps the one-cent cost small."},
    "beta_adjust": {"default": True, "type": "bool", "label": "Residual on beta x SPY",
                    "tooltip": "ON = the day's move minus beta x SPY's. OFF = minus SPY's move (beta 1)."},
    "freeze_1540": {"default": False, "type": "bool", "label": "Signal frozen at 15:40",
                    "tooltip": "ON = rank on the 15:40 price (the hunt's bounce guard, cell 85d); the entry stays the 15:50 print."},
    "nasdaq_only": {"default": True, "type": "bool", "label": "Nasdaq-listed names only",
                    "tooltip": "ON = cell 85a. OFF = every listing (cell 85c); NYSE names then pay the cent again at the exit."},
    "legs": {"default": 0, "min": 0, "max": 2, "step": 1, "type": "int", "hard_min": 0, "hard_max": 2,
             "label": "Legs (0 both, 1 long, 2 short)",
             "tooltip": "0 = long the k lowest and short the k highest (cell 85a); 1 = the long side only; 2 = the short side only."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 85a)": {"min_names": [20], "k": [5], "beta_len": [60], "min_price": [40],
                                   "beta_adjust": [True], "freeze_1540": [False], "nasdaq_only": [True], "legs": [0]},
    "Medium (the hunt's cells + neighbours)": {"k": [3, 5, 7, 10], "beta_len": [40, 60, 120], "min_price": [0, 40, 80],
                                               "beta_adjust": [True], "freeze_1540": [False, True],
                                               "nasdaq_only": [True, False], "legs": [0, 1, 2]},
}

PNL_UNITS = "usd"

_MAX_BASIS = 0.08          # hygiene: official close vs the name's own 15:50-bar close
_CACHE = {}                # per-process: the panel (its betas and daily nets by config live in the panel's own cache)


def _frames(z):
    """Panel arrays -> the hunt's frames (float64; half-day rows blanked in the traded bar fields)."""
    days = pd.Index(np.asarray(z["dates"]).astype("int64"))
    cols = [str(x) for x in z["names"]]
    if cols[-1] != "SPY":
        raise RuntimeError("MISC_AUCREV_1_0: side panel's last column must be SPY")
    names = cols[:-1]
    early = np.asarray(z["early"], bool)
    bars = {}
    for key in ("c30", "c40", "o55", "c55"):
        x = pd.DataFrame(np.asarray(z[key]), index=days, columns=cols).astype(float)
        if key == "c55":
            bars["c55_all"] = x.copy()          # half-day post-close prints kept: beta only (the hunt's FR frame)
        x.loc[early] = np.nan                   # half-day prints are never traded (the hunt's F frames)
        bars[key] = x
    split = pd.DataFrame(np.asarray(z["split"], float), index=days, columns=names)
    raw = pd.DataFrame(np.asarray(z["raw"], float), index=days, columns=names)
    member = pd.DataFrame(np.asarray(z["member"], bool), index=days, columns=names)
    nas = np.asarray(z["nasdaq"], bool)
    full = np.asarray(z["full"], bool)
    base = bars["c55"].shift(1)                 # t-1 15:50-bar close (NaN after a half day: no fallback)
    with np.errstate(divide="ignore", invalid="ignore"):
        o55, c55 = bars["o55"][names], bars["c55"][names]
        p = {"cache": {}, "days": days, "names": names, "nas": nas, "c55_all": bars["c55_all"],
             "r1540": bars["c40"] / base - 1.0,           # known 15:50:00 (names + SPY)
             "r1530": bars["c30"] / base - 1.0,           # known 15:40:00
             "has30": bars["c30"][names].notna(),
             "rp": raw.shift(1),                          # raw close of t-1
             # pre-entry eligibility without the knobs: member, full session, 15:40 bar of t, 15:50 bar of t-1,
             # and SPY's same two prints (SPY's own 15:50 bar of t is what makes the session FULL)
             "pre": (member & full[:, None] & bars["c40"][names].notna() & base[names].notna()
                     & (bars["c40"]["SPY"].notna() & base["SPY"].notna()).to_numpy()[:, None]),
             # the fill: 15:50-bar open -> official close of the same session
             "ret": split / o55 - 1.0,
             # post-entry hygiene (read only after the pick): prints exist, official close within 8% of the bar close
             "okx": o55.notna() & c55.notna() & split.notna() & ~((split / c55 - 1.0).abs() > _MAX_BASIS)}
    return p


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_AUCREV_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _frames({key: z[key] for key in z.files})
    _CACHE["panel"] = p
    return p


def _beta(p, w):
    """The hunt's (s25) beta: rolling OLS slope on SPY over w sessions ending t-1, clipped, 1.0 while undefined."""
    key = ("beta", int(w))
    if key not in p["cache"]:
        w = int(w)
        c10 = p["c55_all"]
        pc = c10.shift(1)
        dr = c10 / pc - 1.0
        m = dr["SPY"]
        nm = p["names"]
        mp = max(20, int(w * 2 / 3))
        cov = (dr[nm].mul(m, axis=0).rolling(w, min_periods=mp).mean()
               - dr[nm].rolling(w, min_periods=mp).mean().mul(m.rolling(w, min_periods=mp).mean(), axis=0))
        p["cache"][key] = cov.div(m.rolling(w, min_periods=mp).var(), axis=0).shift(1).clip(0.3, 2.5).fillna(1.0)
    return p["cache"][key]


def _picks(p, k, beta_len, min_price, beta_adjust, freeze_1540, nasdaq_only, min_names):
    """(long mask, short mask, eligible count) from information known by 15:50:00 ET of each session."""
    nm = p["names"]
    r = p["r1530"] if freeze_1540 else p["r1540"]
    if beta_adjust:
        resid = r[nm] - _beta(p, beta_len).mul(r["SPY"], axis=0)
    else:
        resid = r[nm].sub(r["SPY"], axis=0)
    elig = p["pre"] & (p["rp"] >= float(min_price))
    if freeze_1540:
        elig = elig & p["has30"]
    if nasdaq_only:
        elig = elig & p["nas"][None, :]
    s = resid.where(elig)
    n = s.notna().sum(axis=1)
    ra = s.rank(axis=1, ascending=True, method="first")
    rd = s.rank(axis=1, ascending=False, method="first")
    day = (n >= int(min_names)).to_numpy()[:, None]
    return (ra <= int(k)) & day, (rd <= int(k)) & day, n


def _daily(p, notional, spread_cents, fee_bps, min_names, k, beta_len, min_price, beta_adjust, freeze_1540,
           nasdaq_only, legs):
    """(yyyymmdd array, net $ array) of the traded sessions for one config, over every panel session."""
    key = ("day", float(notional), float(spread_cents), float(fee_bps), int(min_names), int(k), int(beta_len),
           float(min_price), bool(beta_adjust), bool(freeze_1540), bool(nasdaq_only), int(legs))
    if key not in p["cache"]:
        L, S, _ = _picks(p, k, beta_len, min_price, beta_adjust, freeze_1540, nasdaq_only, min_names)
        L = L & p["okx"]                                  # hygiene drop after the pick, never refilled
        S = S & p["okx"]
        ret = p["ret"]
        cents = np.where(p["nas"], 1.0, 2.0) * (float(spread_cents) / 100.0)
        fee = round(2.0 * float(fee_bps) * 1e-4, 12)
        with np.errstate(divide="ignore", invalid="ignore"):
            cost = pd.DataFrame(cents[None, :] / p["rp"].to_numpy(), index=ret.index, columns=ret.columns) + fee
        gL = ret.where(L).mean(axis=1)
        gS = ret.where(S).mean(axis=1)
        cL = cost.where(L).mean(axis=1)
        cS = cost.where(S).mean(axis=1)
        if int(legs) == 1:
            g, c, day = gL, cL, L.any(axis=1)
        elif int(legs) == 2:
            g, c, day = -gS, cS, S.any(axis=1)
        else:
            g, c, day = gL - gS, cL + cS, L.any(axis=1) & S.any(axis=1)
        N = float(notional)
        net = g[day] * N - c[day] * N
        net = net[np.isfinite(net.to_numpy())]
        p["cache"][key] = (net.index.to_numpy().astype("int64"), net.to_numpy().astype(float))
    return p["cache"][key]


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, spread_cents: float = 1.0, fee_bps: float = 0.3, min_names: int = 20,
                 k: int = 5, beta_len: int = 60, min_price: int = 40, beta_adjust: bool = True,
                 freeze_1540: bool = False, nasdaq_only: bool = True, legs: int = 0,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None:
        return None
    o = np.asarray(opens, float)
    c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy().astype("int64")
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [n]])
    sess = []                                         # (day, entry bar = 15:50, exit bar = the day's 15:55 bar)
    for a, b in zip(starts, ends):
        m = minute[a:b]
        e = np.flatnonzero(m == 950)
        if len(e) == 0 or m[-1] != 955:                 # an RTH day that runs to its 16:00 close, or no trade
            continue
        sess.append((int(date[a]), a + int(e[0]), b - 1))
    if not sess:
        return None
    p = _panel()
    if p is None:
        return None
    if not beta_adjust:                               # beta_len is idle without the beta: one cache entry
        beta_len = DEFAULT_PARAMS["beta_len"]["default"]
    dd, net = _daily(p, notional, spread_cents, fee_bps, min_names, k, beta_len, min_price, beta_adjust,
                     freeze_1540, nasdaq_only, legs)
    trades = []
    for d, eb, xb in sess:
        if _stop_event is not None and _stop_event.is_set():
            return None
        j = int(np.searchsorted(dd, d))
        if j >= len(dd) or dd[j] != d:
            continue
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
    """Every basket enters at the 15:50 print and leaves at that SAME session's official close, so no trade is
    ever held through a session close: one empty mark list per trade."""
    return [[] for _ in (trades or [])]

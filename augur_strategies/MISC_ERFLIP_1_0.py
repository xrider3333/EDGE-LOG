"""MISC ERFLIP 1.0 - three-state tape vote decides follow or fade of the morning move (NQ, 12:00 -> 15:55).

# AUGUR-SOURCE: claude-review

Provenance: OPUS-HUNT futures round 2, strategy 44 cell 44d "V-NQ" (ERFLIP + TAPEVOTE)
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S44: PREREG.md, RESULTS.md, s44_lib.py, s44_eval.py,
series.pkl key 44d). Hunt verdict FAIL (Route B missed: P(lift) 0.904, 5 of 8 folds); it is one of the three
legs of the S55 small-legs basket. NOT A BLIND READ: clock, windows, cut and both signs were picked on
2010-06..2016-06 by the proposer, and 2016-07..2025-06 has been read once by the hunt. This file exists so
the engine's Auto-Validate can judge it on its own walk-forward chain and the sealed year.

-- The rule (defaults = 44d) ------------------------------------------------------------
Table rows = FULL regular sessions (first bar 09:30, last 15:55, all 78 five-minute bars; the four 2020
circuit-breaker days 2020-03-09/12/16/18 count when first 09:30 and last 15:55). Per table row, on prices:
  r5  = log returns of the 5m closes (the first = ln(09:30 close / 09:30 open)), r30 = r5 summed by clock
        half-hour, ss5 = sum r5^2, ss30 = sum r30^2, er = |ln(15:55 close / 09:30 open)| / sum |r5|.
States for day t, from the table rows strictly before t:
  S1 = sum ss30 / sum ss5 over the last 20 rows (variance ratio); S2 = mean er over the last 5 rows
  (path efficiency); S3 = sqrt(mean ss5, last 5) / sqrt(mean ss5, last 60) (vol ratio).
RANK of a state = share of its previous `rank_len` - 1 values strictly below today's value. No trade
until `rank_len` + 120 table rows precede the day (370 at the default 250).
vote = #(rank > 1 - cut) - #(rank < cut) over S1, S2, S3, cut = `cut_pct` / 100 (33 = the hunt's thirds:
on a full 249-value window rank < 0.33 and rank < 1/3 select the same values, so do > 0.67 and > 2/3).
M = close of the bar before the entry bar - open of the 09:30 bar. vote >= `vote_need`: FADE (-sign M);
vote <= -`vote_need`: FOLLOW (+sign M); else, or M = 0, no trade.
Entry = open of the bar `entry_min` minutes after 09:30 (150 = 12:00). Exit = open of the bar
`exit_before` minutes before 16:00 (5 = the 15:55 bar). Exit bar missing: close of the last bar before it.
One trade a day at most, flat every night, no stop, no target.

Trade-day eligibility (decided at the entry print): the day is a scheduled FULL session on the published
calendar (a CME equity-index RTH session that is not a CME holiday short session and not an NYSE 13:00
early close: day after Thanksgiving, Dec 24 on a weekday that is not the observed Christmas, July 3 when
July 4 is Tue-Fri), and every 5m bar from 09:30 through the entry bar is on the tape. The calendar is a
copy of augur_engine/session_calendar.py (10-19) kept inside this file: the plugin gate allows only
is_exchange_session from it, and the holiday / early-close sets are needed too.

INFORMATION TIMES: every state reads only table rows of EARLIER sessions (known at the prior 16:00 close);
M reads bars that closed before the entry bar opens; the table-row test of a day is used only for later
days. Nothing reads the entry bar's close or any later bar to decide a trade.

-- Data and roll treatment -------------------------------------------------------------
Run on the UNADJUSTED NQ 5m RTH master (db_noadj_rth) with ROLL_SIGNAL = "ratio": the states are log
returns inside one session and M is used for its sign only, so a ratio adjustment leaves every decision
exactly as on raw prices (the hunt read its states on db_noadj_rth), and the engine re-prices fills to raw
contract prices (no contract switch falls inside 09:30-16:00, so the P&L equals the hunt's adjusted
points). On a difference-adjusted master the log returns would read shifted levels, and the engine's roll
guard refuses that.

-- Costs ----------------------------------------------------------------------------------
PnL is NQ points in the trade tuple; the job charges the house round trip (cost_pts 0.533, mult 20).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC ERFLIP 1.0 · tape-vote follow / fade of the morning move (NQ 12:00 -> 15:55)'
DESCRIPTION = ("At 12:00 ET, three ranked states of the previous sessions (variance ratio, path efficiency, "
               "vol ratio) vote: two say 'one-way week' -> fade the 09:30-12:00 move, two say 'round-trip "
               "week' -> follow it. Exit 15:55. One trade a day, flat every night.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth"}
ROLL_SIGNAL = "ratio"

DEFAULT_PARAMS = {
    "entry_min": {"hard_min": 30, "hard_max": 300, "default": 150, "min": 90, "max": 210, "step": 30, "type": "int",
                  "label": "Entry (minutes after 09:30)",
                  "tooltip": "Decide and enter at the open of the bar this many minutes after 09:30 ET (150 = 12:00)."},
    "exit_before": {"hard_min": 5, "hard_max": 120, "default": 5, "min": 5, "max": 65, "step": 15, "type": "int",
                    "label": "Exit (minutes before 16:00)",
                    "tooltip": "Exit at the open of the bar this many minutes before 16:00 ET (5 = the 15:55 bar)."},
    "cut_pct": {"hard_min": 10, "hard_max": 49, "default": 33, "min": 25, "max": 41, "step": 2, "type": "int",
                "label": "Rank cut (percent)",
                "tooltip": "A state votes 'fade' when its rank is above 100 - cut percent, 'follow' when below cut percent."},
    "vote_need": {"hard_min": 1, "hard_max": 3, "default": 2, "min": 1, "max": 3, "step": 1, "type": "int",
                  "label": "Net votes needed",
                  "tooltip": "Trade only when fade votes minus follow votes reach this many (either way)."},
    "rank_len": {"hard_min": 150, "hard_max": 300, "default": 250, "min": 200, "max": 300, "step": 50, "type": "int",
                 "label": "Rank window (sessions)",
                 "tooltip": "Each state is ranked against its previous rank_len - 1 values; trading starts after rank_len + 120 full sessions."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 44d)": {"entry_min": [150], "exit_before": [5], "cut_pct": [33], "vote_need": [2],
                                   "rank_len": [250]},
    "Medium (neighbours)": {"entry_min": [90, 120, 150, 180, 210], "exit_before": [5, 20, 35, 50, 65],
                            "cut_pct": [25, 29, 33, 37, 41], "vote_need": [1, 2, 3], "rank_len": [200, 250, 300]},
}

PNL_UNITS = "points"

_RTH0 = 186          # slot of the bar stamped 09:30 (slot = ((minute of day - 1080) mod 1440) // 5)
_NRTH = 78           # 09:30 .. 15:55
_CB_DAYS = ("2020-03-09", "2020-03-12", "2020-03-16", "2020-03-18")    # market-wide halts: table rows if first 09:30, last 15:55
_SPECIAL = ("2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14", "2004-06-11", "2007-01-02", "2012-10-29",
            "2012-10-30", "2018-12-05", "2025-01-09")


# ------------------------------------------------------------------------------------------- calendar (copy)
def _dn(y, m, d):
    return int((pd.Timestamp(year=int(y), month=int(m), day=int(d)) - pd.Timestamp(1970, 1, 1)).days)


def _wd(dn):
    return (int(dn) + 3) % 7                   # 1970-01-01 was a Thursday; Monday = 0


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return _dn(year, month, day)


def _observed(dn):
    w = _wd(dn)
    return dn - 1 if w == 5 else (dn + 1 if w == 6 else dn)


def _nth_wd(year, month, weekday, n):
    d = _dn(year, month, 1)
    return d + (weekday - _wd(d)) % 7 + 7 * (n - 1)


def _last_wd(year, month, weekday):
    d = (_dn(year + 1, 1, 1) if month == 12 else _dn(year, month + 1, 1)) - 1
    return d - (_wd(d) - weekday) % 7


def _not_full_days(years):
    """Day numbers of the given years that are NOT scheduled full RTH sessions on a weekday: CME closures,
    CME holiday short sessions and NYSE 13:00 early closes (copy of session_calendar + s44_lib.nyse_early_close)."""
    out = set()
    for y in years:
        y = int(y)
        shut = set(_dn(int(s[:4]), int(s[5:7]), int(s[8:])) for s in _SPECIAL if int(s[:4]) == y)
        ny = _dn(y, 1, 1)
        if _wd(ny) == 6:
            shut.add(ny + 1)
        elif _wd(ny) < 5:
            shut.add(ny)
        shut.add(_easter(y) - 2)
        xmas = _observed(_dn(y, 12, 25))
        shut.add(xmas)
        hol = {_nth_wd(y, 1, 0, 3), _nth_wd(y, 2, 0, 3), _last_wd(y, 5, 0), _observed(_dn(y, 7, 4)),
               _nth_wd(y, 9, 0, 1), _nth_wd(y, 11, 3, 4)}
        if y >= 2022:
            hol.add(_observed(_dn(y, 6, 19)))
        early = {_nth_wd(y, 11, 3, 4) + 1}
        d24 = _dn(y, 12, 24)
        if _wd(d24) < 5 and d24 not in shut:
            early.add(d24)
        if _wd(_dn(y, 7, 4)) in (1, 2, 3, 4):
            early.add(_dn(y, 7, 3))
        out |= shut | hol | early
    return out


def _sched_full(days):
    days = np.asarray(days, dtype=np.int64)
    if not len(days):
        return np.zeros(0, bool)
    yrs = sorted(set(int(y) for y in (pd.Timestamp(1970, 1, 1) + pd.to_timedelta(days, unit="D")).year))
    bad = np.asarray(sorted(_not_full_days(yrs)), dtype=np.int64)
    wd = (days + 3) % 7
    return (wd < 5) & ~np.isin(days, bad)


# ------------------------------------------------------------------------------------------- tape -> session grid
def _grid(opens, closes, index, n):
    """Session rows x 78 RTH slots. Session date = (bar start ET + 6 h).date. Returns None off a 5m tape."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    v = idx.asi8
    d = np.diff(v[: min(n, 3000)]) // 60_000_000_000
    d = d[(d > 0) & (d < 120)]
    if not len(d) or int(np.median(d)) != 5:
        return None
    mins = (idx.hour * 60 + idx.minute).to_numpy()
    sday = ((v + 6 * 3_600_000_000_000) // 86_400_000_000_000).astype(np.int64)
    rs = mins - 570
    keep = (rs >= 0) & (rs < 390) & (rs % 5 == 0)
    bars = np.flatnonzero(keep)
    days, inv = np.unique(sday[bars], return_inverse=True)
    col = rs[bars] // 5
    ns = len(days)
    B = np.full((ns, _NRTH), -1, dtype=np.int64)
    B[inv, col] = bars
    O = np.full((ns, _NRTH), np.nan)
    C = np.full((ns, _NRTH), np.nan)
    O[inv, col] = np.asarray(opens, float)[bars]
    C[inv, col] = np.asarray(closes, float)[bars]
    return days, B, O, C


def _ranks(sx, L, warm):
    r = np.full(len(sx), np.nan)
    for k in range(int(warm), len(sx)):
        if np.isnan(sx[k]):
            continue
        w = sx[max(0, k - (L - 1)):k]
        bad = np.isnan(w)
        if bad.any() and (~bad).sum() + 1 < 120:
            continue
        r[k] = float((w < sx[k]).mean())
    return r


def _vote_state(days, B, O, C, rank_len):
    """Per session row: vote (nan = no vote) from the table rows strictly before it."""
    ns = len(days)
    pres = B >= 0
    n = pres.sum(axis=1)
    clean = pres[:, 0] & pres[:, -1]
    cb = np.isin(days, np.asarray([_dn(int(s[:4]), int(s[5:7]), int(s[8:])) for s in _CB_DAYS], dtype=np.int64))
    table = clean & ((n == _NRTH) | cb)
    ti = np.flatnonzero(table)
    nt = len(ti)
    ss5 = np.full(nt, np.nan); ss30 = np.full(nt, np.nan); er = np.full(nt, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        full = n[ti] == _NRTH
        fi = ti[full]
        if len(fi):
            lp = np.log(np.concatenate([O[fi, :1], C[fi]], axis=1))
            r5 = np.diff(lp, axis=1)
            r30 = r5.reshape(len(fi), 13, 6).sum(axis=2)
            ss5[full] = (r5 ** 2).sum(axis=1)
            ss30[full] = (r30 ** 2).sum(axis=1)
            er[full] = np.abs(np.log(C[fi, -1] / O[fi, 0])) / np.abs(r5).sum(axis=1)
        for j in np.flatnonzero(~full):
            i = ti[j]
            cols = np.flatnonzero(pres[i])
            r5 = np.diff(np.log(np.concatenate([[O[i, 0]], C[i, cols]])))
            r30 = np.bincount(cols // 6, weights=r5, minlength=13)
            ss5[j] = float((r5 ** 2).sum()); ss30[j] = float((r30 ** 2).sum())
            er[j] = float(abs(np.log(C[i, -1] / O[i, 0])) / np.abs(r5).sum())
    c5 = np.r_[0.0, np.cumsum(ss5)]; c30 = np.r_[0.0, np.cumsum(ss30)]; ce = np.r_[0.0, np.cumsum(er)]
    k = np.arange(nt + 1)

    def win(c, N):
        o = np.full(nt + 1, np.nan)
        m = k >= N
        o[m] = c[k[m]] - c[k[m] - N]
        return o
    with np.errstate(divide="ignore", invalid="ignore"):
        s1 = win(c30, 20) / win(c5, 20)
        s2 = win(ce, 5) / 5.0
        s3 = np.sqrt(win(c5, 5) / 5.0) / np.sqrt(win(c5, 60) / 60.0)
    L = int(rank_len)
    warm = L + 120
    R = np.vstack([_ranks(s1, L, warm), _ranks(s2, L, warm), _ranks(s3, L, warm)])
    kk = np.concatenate([[0], np.cumsum(table)[:-1]]) if ns else np.zeros(0, np.int64)
    return R[:, kk]


def erflip_trades(days, B, O, C, entry_min=150, exit_before=5, cut_pct=33, vote_need=2, rank_len=250):
    """Trade tuples (entry bar, exit bar, points, side, entry price, exit price) of the ERFLIP vote leg."""
    e = int(entry_min) // 5
    x = _NRTH - int(exit_before) // 5
    if e < 1 or x <= e or x > _NRTH - 1 or len(days) == 0:
        return []
    R = _vote_state(days, B, O, C, rank_len)
    cut = float(cut_pct) / 100.0
    allr = ~np.isnan(R).any(axis=0)
    with np.errstate(invalid="ignore"):
        vote = (R > 1.0 - cut).sum(axis=0) - (R < cut).sum(axis=0)
    pres = B >= 0
    ok = _sched_full(days) & pres[:, : e + 1].all(axis=1) & allr
    M = C[:, e - 1] - O[:, 0]
    sg = np.sign(np.nan_to_num(M))
    need = int(vote_need)
    side = np.where(vote >= need, -sg, np.where(vote <= -need, sg, 0.0))
    side[~ok] = 0.0
    out = []
    for i in np.flatnonzero(side != 0):
        eb = int(B[i, e]); ep = float(O[i, e])
        if pres[i, x]:
            xb = int(B[i, x]); xp = float(O[i, x])
        else:
            cols = np.flatnonzero(pres[i, e:x]) + e
            xb = int(B[i, cols[-1]]); xp = float(C[i, cols[-1]])
        s = int(side[i])
        out.append((eb, xb, float(s * (xp - ep)), s, ep, xp))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 entry_min: int = 150, exit_before: int = 5, cut_pct: int = 33, vote_need: int = 2,
                 rank_len: int = 250, return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 500 or index is None or len(index) != n:
        return None
    g = _grid(opens, closes, index, n)
    if g is None:
        return None
    days, B, O, C = g
    trades = erflip_trades(days, B, O, C, entry_min, exit_before, cut_pct, vote_need, rank_len)
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; ls = p[p < 0]
    gw = float(w.sum()); gl = float(-ls.sum())
    cum = np.cumsum(p); peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float(min(0.0, (cum - peak).min())),
           "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Every trade enters after 09:30 and leaves the same session: no trade is held through a close."""
    return [[] for _ in (trades or [])]

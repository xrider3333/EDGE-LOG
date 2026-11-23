"""MISC SMALLLEGS 1.1 - MISC_SMALLLEGS_1_0 (cell 55a, RUN #524) + ONE fixed rule: stand aside on calm days (prior VIX close < 15).

# AUGUR-SOURCE: claude-review

SECOND-LANE READ: Book (OPUS-HUNT), 2026-11-23, on c60e0a86 - OK, no look-ahead (session date = (ET+6h).date, last VIX row
strictly before it, 7-day stale guard; on kept days 1_1 == 1_0 by construction). plugin_gate --stamp refuses this file
(claude-review files are not gated), so the read is recorded here. Tests: tests/test_misc_smalllegs_1_1.py = 7; the earlier
'70 passed' was the wider run (1_1 + SMALLLEGS 1_0 + ERFLIP + roll-detector lint + book as-if units).

-- What 1.1 adds (the ONLY change vs 1.0) ----------------------------------------------
Skip the whole trade day - all three legs - when the PRIOR session's CBOE VIX close is below `vix_max` (15).
`vix_max` is FIXED at 15 in every search set (min = max = default = 15, a single value, not tuned); 0 disables
the rule (then 1.1 = 1.0 trade for trade).
  NOT A BLIND READ. The cut 15 was picked AFTER looking at VIX buckets of the stitched 55a series in
  C:/EdgeLog/_anatomy_cache/frontier_b180/b180_gate_out.txt (stitched 55a ROC 38.0 -> 46.3 with the cut; random
  stand-aside control 97.7th percentile). Treat any validate as a confirmation of a chosen rule, with that
  selection caveat. This is NOT CALMTAPE (Q29, a long-on-calm index leg, closed): here an existing leg stands
  aside on calm days.
  VIX source: C:/EdgeLog/_research_cache/public_series/cboe/VIX_History.csv (CBOE's own file, DATE MM/DD/YYYY,
  CLOSE; 1990-01-02 .. 2026-10-02 as pinned), sha256
  6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a. The plugin refuses a file whose bytes differ.
  House rules (MANAGER #126 / CALMTAPE r1): the VIX close of a day D settles 16:15 ET on D, so trade day T
  reads the latest VIX row dated BEFORE T (never T itself); VIX rows dated on a CME-holiday session (US
  holidays on which CME runs a short session and NYSE is shut - 23 such rows, 2022-05-30 on) are DROPPED before
  the read; rows after the last bar's session date are dropped on load (lockbox-honest). Missing prior VIX (no
  row, the last usable row older than 7 calendar days,) -> the day trades
  as 1.0 (no skip); those trade days are counted in the result ('vix_missing_days'), the skipped trade days in
  'vix_skip_days'. NEEDS THE VIX SIDE FILE (absent or wrong sha = the run RAISES): the desktop runner holds NQ / ES masters only - run on the Razer.

-- Below: the 1.0 docstring, unchanged ----------------------------------------------------
MISC SMALLLEGS 1.0 - three small NQ day legs traded together: PREFADE 09:30-10:00 + ERFLIP 12:00-15:55 + LATE30 15:00-15:30.

Provenance: OPUS-HUNT futures round 2, strategy 55 cell 55a, the SMALL-LEGS BASKET
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S55: PREREG.md, RESULTS.md, s55_run.py, series.pkl key 55a)
= hunt cells 30a (S30 PREFADE) + 36d (S36 LATE30) + 44d (S44 ERFLIP), one NQ contract each, summed by day.
Hunt verdict FAIL (selection-adjusted control 90.4th percentile at one contract, 5 of 8 folds). NOT A BLIND
READ: the three legs were picked because their 2016-25 numbers were the best of 23 hunt ideas. This file
exists so the engine's Auto-Validate can judge the basket on its walk-forward chain and the sealed year.

ONE TRADE TUPLE PER LEG TRADE. The engine charges cost_pts on every tuple and books a same-day trade whole on
its exit day, so the per-day sum of the tuples is the basket's daily P&L at one contract a leg, with one
house cost per leg-trade - exactly how S55 built 55a. ERFLIP (12:00-15:55) and LATE30 (15:00-15:30) can be
open together (two contracts for 30 minutes); every tuple is independent and none is held overnight.

-- Leg 1: PREFADE (hunt 30a; defaults = k 2.0, out 10:00) -------------------------------
Session = CME trading day (bar start ET + 6 h). S = last close at or before the 09:25 bar - last close at or
before the 08:25 bar (the pre-open hour, ETH bars). M = median |S| over the 60 session rows before today
(rows whose S counts: 09:30 bar present, >= 20 of the 24 bars 07:30..09:25, and the session was complete:
>= 76 of 78 RTH bars with the 15:55 bar - all known at that earlier close), at least 30 values.
Today: 09:30 bar present, >= 20 of 24 pre-open bars, today is not a scheduled short session, |S| >=
`prefade_k` x M, S != 0 -> FADE: S > 0 sell, S < 0 buy at the 09:30 open; exit = close of the 09:55 bar
(missing: last close of a bar from 09:30 on before it).
  vs the hunt: the hunt kept a trade day only if the day turned out complete (>= 76 RTH bars, known 16:00)
  OR its last bar did not look like a scheduled short session (class U, traded); this file decides the same
  thing at 09:30 from the published calendar (CME holiday short sessions and NYSE 13:00 early closes are out).
  NEEDS ETH BARS: on an RTH-only tape the pre-open hour is missing and this leg never trades.

-- Leg 2: LATE30 (hunt 36d; the logic of augur_strategies/MISC_LATE30_1_0.py, copied) ------
At 15:00: R = high - low of the bars 09:30..14:59, ADR = mean full-session range of the previous 20 FULL
sessions; R >= `late_range_mult` x ADR and the last close before 15:00 in the top 20% of R -> buy, bottom
20% -> sell, at the 15:00 open; exit at the 15:30 open. Today must have its 09:30 bar and >= 64 of the 66
bars before 15:00. (The hunt read 1m noadj bars; LATE30 1.0 is its 5m engine form, RUN #510.)

-- Leg 3: ERFLIP (hunt 44d; the logic of augur_strategies/MISC_ERFLIP_1_0.py, copied) ------
Three ranked states of the previous full sessions (20-row variance ratio, 5-row path efficiency, 5/60-row
vol ratio; ranks over 250 values; no trade before 370 full sessions) vote; net vote >= 2 'one-way' ->
fade the 09:30-11:55 move, <= -2 -> follow it; entry 12:00 open, exit 15:55 open. Rank cut
`erflip_cut_pct` (33 = thirds). Trade day must be a scheduled full session with every bar 09:30..12:00.

`use_prefade` / `use_late30` / `use_erflip` switch a leg off (all on = the hunt cell 55a).

INFORMATION TIMES: every decision reads bars that closed before its entry bar opens, plus completed
earlier sessions; the published calendar is known in advance. No input reads the entry bar or later.

-- Data and roll treatment -------------------------------------------------------------
Run on the UNADJUSTED NQ 5m ETH master (db_noadj_eth; PREFADE needs the 07:30-09:25 bars) with ROLL_SIGNAL
= "ratio". ERFLIP reads log returns inside a session (a difference adjustment would change them, and the
roll guard refuses a level / percent file on a difference-adjusted master); PREFADE (|S| / median |S|) and
LATE30 (range / average range, position inside the range) are ratios too, so a ratio adjustment leaves
ERFLIP exactly as on raw prices and moves PREFADE / LATE30 only where a 60- or 20-session look-back
straddles a contract switch (the older segment's points are scaled by about 1 +/- 0.5%). Fills and P&L
are re-priced by the engine to raw contract prices; no contract switch falls inside 07:30-16:00 ET.

-- Costs ----------------------------------------------------------------------------------
PnL is NQ points per tuple; the job charges the house round trip per tuple (cost_pts 0.533, mult 20).
"""
import hashlib
import io
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC SMALLLEGS 1.1 · VIX>=15 days only · NQ basket: pre-open fade + 12:00 tape vote + 15:00 late continuation'
DESCRIPTION = ("Three small NQ day-session legs at one contract each: fade a big 08:30-09:30 move at the 09:30 "
               "open (out 10:00), the 12:00 three-state follow / fade vote (out 15:55), and the 15:00 wide-day "
               "continuation (out 15:30). One tuple per leg trade; flat every night. 1.1: the whole day stands aside "
               "when the prior session's VIX close is below 15.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "eth", "source": "db_noadj_eth"}
ROLL_SIGNAL = "ratio"

DEFAULT_PARAMS = {
    "prefade_k": {"hard_min": 1.0, "hard_max": 4.0, "default": 2.0, "min": 1.5, "max": 3.0, "step": 0.25,
                  "type": "float", "label": "PREFADE: move vs typical (x)",
                  "tooltip": "Fade the 08:30-09:30 move only when it is at least this many times its 60-session median size."},
    "late_range_mult": {"hard_min": 0.5, "hard_max": 2.0, "default": 1.0, "min": 0.75, "max": 1.5, "step": 0.25,
                        "type": "float", "label": "LATE30: range so far vs average (x)",
                        "tooltip": "Trade the 15:00 continuation only if the 09:30-15:00 range is at least this many times the 20-session average range."},
    "erflip_cut_pct": {"hard_min": 10, "hard_max": 49, "default": 33, "min": 25, "max": 41, "step": 2, "type": "int",
                       "label": "ERFLIP: rank cut (percent)",
                       "tooltip": "A state votes 'fade' above 100 - cut percent and 'follow' below cut percent of its 250-session rank."},
    "use_prefade": {"default": True, "type": "bool", "label": "Leg on: PREFADE 09:30-10:00",
                    "tooltip": "Trade the pre-open fade leg."},
    "use_late30": {"default": True, "type": "bool", "label": "Leg on: LATE30 15:00-15:30",
                   "tooltip": "Trade the late wide-day continuation leg."},
    "use_erflip": {"default": True, "type": "bool", "label": "Leg on: ERFLIP 12:00-15:55",
                   "tooltip": "Trade the tape-vote follow / fade leg."},
    "vix_max": {"hard_min": 0, "hard_max": 40, "default": 15, "min": 15, "max": 15, "step": 1, "type": "int",
                "label": "Stand aside: prior VIX close below",
                "tooltip": "Skip the whole day (all three legs) when the prior session's CBOE VIX close is below this. "
                           "Fixed at 15 (not searched); 0 = off."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 55a)": {"prefade_k": [2.0], "late_range_mult": [1.0], "erflip_cut_pct": [33],
                                   "use_prefade": [True], "use_late30": [True], "use_erflip": [True], "vix_max": [15]},
    "Medium (neighbours, all legs on)": {"prefade_k": [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0],
                                         "late_range_mult": [0.75, 1.0, 1.25, 1.5],
                                         "erflip_cut_pct": [25, 29, 33, 37, 41],
                                         "use_prefade": [True], "use_late30": [True], "use_erflip": [True], "vix_max": [15]},
    "Long   (neighbours x legs on / off)": {"prefade_k": [1.5, 2.0, 2.5, 3.0], "late_range_mult": [0.75, 1.0, 1.25, 1.5],
                                            "erflip_cut_pct": [29, 33, 37], "use_prefade": [True, False],
                                            "use_late30": [True, False], "use_erflip": [True, False], "vix_max": [15]},
}

PNL_UNITS = "points"

_NS = 288            # 5m slots of a CME day, slot 0 = the bar stamped 18:00 ET
_RTH0 = 186          # 09:30
_NRTH = 78           # 09:30 .. 15:55
_S0730, _S0825, _S0925, _S0955 = 162, 173, 185, 191
_CB_DAYS = ("2020-03-09", "2020-03-12", "2020-03-16", "2020-03-18")    # market-wide halts: ERFLIP table rows if first 09:30, last 15:55
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


def _short_days(years):
    """Day numbers of the CME holiday short sessions and NYSE 13:00 early closes of the given years."""
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
        shut.add(_observed(_dn(y, 12, 25)))
        hol = {_nth_wd(y, 1, 0, 3), _nth_wd(y, 2, 0, 3), _last_wd(y, 5, 0), _observed(_dn(y, 7, 4)),
               _nth_wd(y, 9, 0, 1), _nth_wd(y, 11, 3, 4)}
        if y >= 2022:
            hol.add(_observed(_dn(y, 6, 19)))
        hol -= shut
        early = {_nth_wd(y, 11, 3, 4) + 1}
        d24 = _dn(y, 12, 24)
        if _wd(d24) < 5 and d24 not in shut:
            early.add(d24)
        if _wd(_dn(y, 7, 4)) in (1, 2, 3, 4):
            early.add(_dn(y, 7, 3))
        out |= hol | early
    return out


def _is_short(days):
    days = np.asarray(days, dtype=np.int64)
    if not len(days):
        return np.zeros(0, bool)
    yrs = sorted(set(int(y) for y in (pd.Timestamp(1970, 1, 1) + pd.to_timedelta(days, unit="D")).year))
    return np.isin(days, np.asarray(sorted(_short_days(yrs)), dtype=np.int64))


# ------------------------------------------------------------------------------------------- tape -> session grid
def _grid(opens, highs, lows, closes, index, n):
    """Session rows x 288 slots (slot 0 = 18:00 ET). Session date = (bar start ET + 6 h).date. None off a 5m tape."""
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
    keep = mins % 5 == 0
    bars = np.flatnonzero(keep)
    days, inv = np.unique(sday[bars], return_inverse=True)
    col = ((mins[bars] - 1080) % 1440) // 5
    ns = len(days)
    B = np.full((ns, _NS), -1, dtype=np.int64)
    B[inv, col] = bars
    G = {"B": B}
    for k, a in (("O", opens), ("H", highs), ("L", lows), ("C", closes)):
        x = np.full((ns, _NS), np.nan)
        x[inv, col] = np.asarray(a, float)[bars]
        G[k] = x
    return days, G


# ------------------------------------------------------------------------------------------- leg 1: PREFADE (30a)
def prefade_trades(days, G, k=2.0, lookback=60, min_obs=30):
    B, O, C = G["B"], G["O"], G["C"]
    ns = len(days)
    if ns == 0:
        return []
    pres = B >= 0
    el_a = pres[:, _RTH0]
    el_b = pres[:, _S0730:_RTH0].sum(axis=1) >= 20
    el_c = (pres[:, _RTH0:_RTH0 + _NRTH].sum(axis=1) >= 76) & pres[:, _RTH0 + _NRTH - 1]
    cols = np.arange(_NS)[None, :]
    last = np.maximum.accumulate(np.where(pres, cols, -1), axis=1)
    rows = np.arange(ns)[:, None]
    cf = np.where(last >= 0, C[rows, np.maximum(last, 0)], np.nan)
    sig = cf[:, _S0925] - cf[:, _S0825]
    S_hist = np.where(el_a & el_b & el_c, sig, np.nan)
    M = pd.Series(np.abs(S_hist)).rolling(int(lookback), min_periods=int(min_obs)).median().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        go = el_a & el_b & ~_is_short(days) & np.isfinite(M) & np.isfinite(sig) & (sig != 0) & (np.abs(sig) >= float(k) * M)
    out = []
    for i in np.flatnonzero(go):
        seg = np.flatnonzero(pres[i, _RTH0:_S0955 + 1]) + _RTH0
        xs = int(seg[-1])
        eb = int(B[i, _RTH0]); ep = float(O[i, _RTH0])
        xb = int(B[i, xs]); xp = float(C[i, xs])
        s = -int(np.sign(sig[i]))
        out.append((eb, xb, float(s * (xp - ep)), s, ep, xp))
    return out


# ------------------------------------------------------------------------------------------- leg 2: LATE30 (36d)
def late30_trades(days, G, range_mult=1.0, zone_pct=20, adr_len=20, exit_min=30):
    B = G["B"][:, _RTH0:_RTH0 + _NRTH]
    O = G["O"][:, _RTH0:_RTH0 + _NRTH]
    H = G["H"][:, _RTH0:_RTH0 + _NRTH]
    L = G["L"][:, _RTH0:_RTH0 + _NRTH]
    C = G["C"][:, _RTH0:_RTH0 + _NRTH]
    ns = len(days)
    if ns == 0:
        return []
    pres = B >= 0
    anyr = pres.any(axis=1)
    n = pres.sum(axis=1)
    first = np.argmax(pres, axis=1)
    lastc = _NRTH - 1 - np.argmax(pres[:, ::-1], axis=1)
    full = anyr & (first == 0) & (lastc == _NRTH - 1) & (n >= _NRTH - 2)
    with np.errstate(all="ignore"):
        rng_full = np.where(pres, H, -np.inf).max(axis=1) - np.where(pres, L, np.inf).min(axis=1)
    fr = rng_full[full]
    cs = np.r_[0.0, np.cumsum(fr)]
    cnt = np.concatenate([[0], np.cumsum(full)[:-1]])
    A = int(adr_len)
    adr = np.where(cnt >= A, (cs[cnt] - cs[np.maximum(cnt - A, 0)]) / max(A, 1), np.nan)
    e = 66                       # 15:00
    x = e + int(exit_min) // 5
    if x > _NRTH - 1:
        return []
    pre = pres[:, :e]
    npre = pre.sum(axis=1)
    lastpre = e - 1 - np.argmax(pre[:, ::-1], axis=1)
    with np.errstate(all="ignore"):
        hi = np.where(pre, H[:, :e], -np.inf).max(axis=1)
        lo = np.where(pre, L[:, :e], np.inf).min(axis=1)
        none = ~pre.any(axis=1)
        hi[none] = np.nan
        lo[none] = np.nan
        rng = hi - lo
        lastpx = C[np.arange(ns), lastpre]
        pos = (lastpx - lo) / rng
        zone = float(zone_pct) / 100.0
        go = (anyr & (first == 0) & (npre >= e - 2) & pres[:, e] & pres[:, x] & np.isfinite(adr) & (adr > 0)
              & (rng > 0) & (rng >= float(range_mult) * adr))
        side = np.where(pos >= 1.0 - zone, 1, np.where(pos <= zone, -1, 0))
    out = []
    for i in np.flatnonzero(go & (side != 0)):
        s = int(side[i])
        eb = int(B[i, e]); xb = int(B[i, x]); ep = float(O[i, e]); xp = float(O[i, x])
        out.append((eb, xb, float(s * (xp - ep)), s, ep, xp))
    return out


# ------------------------------------------------------------------------------------------- leg 3: ERFLIP (44d)
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
                 prefade_k: float = 2.0, late_range_mult: float = 1.0, erflip_cut_pct: int = 33,
                 use_prefade: bool = True, use_late30: bool = True, use_erflip: bool = True,
                 vix_max: int = 15, return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 500 or index is None or len(index) != n:
        return None
    g = _grid(opens, highs, lows, closes, index, n)
    if g is None:
        return None
    days, G = g
    trades = []
    if use_prefade:
        trades += prefade_trades(days, G, k=prefade_k)
    if _stop_event is not None and _stop_event.is_set():
        return None
    if use_late30:
        trades += late30_trades(days, G, range_mult=late_range_mult)
    if use_erflip:
        rs = slice(_RTH0, _RTH0 + _NRTH)
        trades += erflip_trades(days, G["B"][:, rs], G["O"][:, rs], G["C"][:, rs], cut_pct=erflip_cut_pct)
    skip_n = miss_n = 0
    if vix_max and float(vix_max) > 0 and trades:
        skip, miss = _vix_skip_rows(days, float(vix_max))
        row = np.full(n, -1, dtype=np.int64)
        Bf = G["B"]
        rr, cc = np.nonzero(Bf >= 0)
        row[Bf[rr, cc]] = rr
        trow = {t[0]: int(row[t[0]]) for t in trades}
        used = set(r for r in trow.values() if r >= 0)
        skip_n = int(sum(1 for r in used if skip[r]))
        miss_n = int(sum(1 for r in used if miss[r]))
        trades = [t for t in trades if not (trow[t[0]] >= 0 and skip[trow[t[0]]])]
    trades.sort(key=lambda t: (t[0], t[1]))
    out = _score(trades, return_trades)
    if out is not None:
        out["vix_skip_days"] = skip_n           # trade days (1.0 would trade) that 1.1 stood aside on
        out["vix_missing_days"] = miss_n        # trade days with no usable prior VIX -> traded as 1.0
    return out


# ------------------------------------------------------------------------------------------- 1.1: prior-VIX stand-aside
_VIX_PATH = "C:/EdgeLog/_research_cache/public_series/cboe/VIX_History.csv"
_VIX_SHA = "6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a"
_VIX_STALE = 7                                  # calendar days: an older last row = missing
_VIX_MEMO = {}


def _cme_holiday_days(years):
    """US holidays on which CME runs a short session and NYSE is shut (the house 'CME-holiday session')."""
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
        shut.add(_observed(_dn(y, 12, 25)))
        hol = {_nth_wd(y, 1, 0, 3), _nth_wd(y, 2, 0, 3), _last_wd(y, 5, 0), _observed(_dn(y, 7, 4)),
               _nth_wd(y, 9, 0, 1), _nth_wd(y, 11, 3, 4)}
        if y >= 2022:
            hol.add(_observed(_dn(y, 6, 19)))
        if y < 1998:
            hol.discard(_nth_wd(y, 1, 0, 3))    # NYSE opened on MLK day until 1998: a real VIX day
        out |= hol - shut
    return out


def _load_vix(last_day, path=None, sha=None):
    """(day numbers, closes) of the pinned CBOE file, rows after `last_day` and CME-holiday rows dropped.
    RAISES when the file is not on this machine (MANAGER 11-23: a silent fall-back to 1.0 is a false result)."""
    path = path or _VIX_PATH
    sha = sha or _VIX_SHA
    if not os.path.exists(path):
        raise FileNotFoundError("MISC_SMALLLEGS_1_1: VIX file %s is not on this machine - refusing to run as 1.0" % path)
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size, int(last_day))
    hit = _VIX_MEMO.get(key)
    if hit is not None:
        return hit
    with open(path, "rb") as fh:
        blob = fh.read()
    dig = hashlib.sha256(blob).hexdigest()
    if dig != sha:
        raise ValueError("MISC_SMALLLEGS_1_1: refused %s - sha256 %s is not the pinned %s" % (path, dig, sha))
    df = pd.read_csv(io.BytesIO(blob), usecols=["DATE", "CLOSE"], dtype={"DATE": str})
    d = pd.to_datetime(df["DATE"], format="%m/%d/%Y").to_numpy().astype("datetime64[D]").astype(np.int64)
    v = pd.to_numeric(df["CLOSE"], errors="coerce").to_numpy(np.float64)
    keep = (d <= int(last_day)) & np.isfinite(v)
    d, v = d[keep], v[keep]
    if len(d):
        y0 = int(pd.Timestamp(int(d.min()), unit="D").year)
        y1 = int(pd.Timestamp(int(d.max()), unit="D").year)
        hol = np.asarray(sorted(_cme_holiday_days(range(y0, y1 + 1))), dtype=np.int64)
        k2 = ~np.isin(d, hol)
        d, v = d[k2], v[k2]
    o = np.argsort(d, kind="stable")
    out = (d[o], v[o])
    if len(_VIX_MEMO) >= 4:
        _VIX_MEMO.pop(next(iter(_VIX_MEMO)))
    _VIX_MEMO[key] = out
    return out


def _vix_skip_rows(days, vix_max, vix=None):
    """Per session row: (skip, missing). Prior VIX = the latest kept VIX row dated strictly before the session
    date (its close settled 16:15 ET the day before, before the session's first decision bar)."""
    days = np.asarray(days, dtype=np.int64)
    if not len(days):
        return np.zeros(0, bool), np.zeros(0, bool)
    vd, vv = vix if vix is not None else _load_vix(int(days.max()))
    if not len(vd):
        return np.zeros(len(days), bool), np.ones(len(days), bool)
    j = np.searchsorted(vd, days, side="left") - 1
    ok = j >= 0
    jj = np.maximum(j, 0)
    ok &= (days - vd[jj]) <= _VIX_STALE
    prior = np.where(ok, vv[jj], np.nan)
    with np.errstate(invalid="ignore"):
        skip = ok & (prior < float(vix_max))
    return skip, ~ok


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
    """Every leg enters and leaves inside one session: no trade is held through a close."""
    return [[] for _ in (trades or [])]

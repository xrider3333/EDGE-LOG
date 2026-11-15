# AUGUR-SOURCE: claude-review
"""MISC NIGHTPERSIST 1.0 - overnight-return persistence on the point-in-time top 100: long the 10 names whose long-run
average night return (demeaned against the night's eligible names) is highest, short the 10 lowest, $100k a side, in
at the official close (MOC), out at the next session's official open (MOO). HELD OVERNIGHT, one night per trade.

Provenance: OPUS-HUNT round 7 (cross-sectional stocks, lens xs-overnight-intraday), strategy 83 (NIGHTPERSIST-120),
cell 83d (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S83: PREREG.md, RESULTS.md, s83_lib.py, s83_run.py,
trades_83d.csv, series.pkl['83d']). Defaults = cell 83d exactly. Mechanism: night-time clientele (Lou, Polk,
Skouras) - some stocks have recurring overnight buyers, so a stock's long-run average overnight return predicts its
next overnight return across stocks. Not strategy 23 (PICK6): daily corr of the net series -0.036 (hunt), but both
trade ~every session.
NOT A BLIND READ: the proposer's DISC map (2017-04..2020-12) chose the windows and the residual type, so DISC is
SEEN, and the hunt read cell 83d ONCE on 2021-01..2025-06 (CONF). Verdict under the old strict bars: FAIL (Route B
missed): CONF-1 / CONF-2 net t 0.56 / 0.36, CONF +$21.55 a night (gross / cost 1.47x) but -$27.1k at double cost;
2017-04..2025-06 net $31.59 a night over 2,020 nights, t 1.47, 4 of 9 years positive, ROC@30k 7.33, DD% 19.3; ONE
EPISODE (seen DISC total $39.7k -> $18.6k with Feb-Apr 2020 zeroed). It passes the owner's loose screen
(owner_screen_1114: 250 trades a year, $7.1k a year, leg max DD $31.7k) with warnings t 1.7 / 0.6, loses at 2x cost,
one episode, leg DD > 3 years' net; the walk-forward basket S127 kept strategy 83 among its persistent picks (127c,
picked in >= 5 of 7 folds). The engine's 2025-07..2026-06 lockbox was never read by the hunt. This file exists so
the engine's Auto-Validate can judge it. WITH THE CORPORATE-ACTION GUARD (below) the same 2,020 nights book $56,671.83
($28.06 a night), not the hunt's $63,806.16: the hunt's total held a fake +$7,023 RTX night (2020-04-02, inside the
Feb-Apr 2020 episode).

-- The rule -----------------------------------------------------------------------------
Sessions = the panel's NYSE sessions (dates on which >= 50 universe names print). Session t is TRADED only when it is
FULL (not on the frozen NYSE half-day list, SPY has its 15:50 bar) and the next session t+1 exists.
  n_i(s)  = o_split(s) / c_split(s-1) - 1, the night INTO session s (s-1 = the previous session); invalid when a print
            is missing or |n| > 25 pct.
  83d (beta_resid off): e_i(s) = n_i(s) - the mean of n over night s's eligible names (members of year(s), raw close
            of s-1 >= `min_price`, valid n). S_i(t) = mean of the valid e_i(s), s = t-L+1 .. t (L = `lookback`;
            the night INTO t's open is the window's last term), needing >= 80 pct of L valid (96 of 120).
  beta_resid on (83a / 83b): S_i(t) = mean over the valid s in the window of n_i(s) - beta_i(t) x n_SPY(s), with
            n_SPY(s) = SPY's 09:30 open of s / its last RTH close of s-1 - 1 and beta_i(t) = OLS slope of i's
            close-to-close return (|r| <= 25 pct) on SPY's over the 60 sessions ending t-1 (>= 40 valid, clipped
            0.3 .. 2.5, 1.0 while undefined). `tug` on (83c, beta_resid only): minus the same mean of the residual
            DAY return (c_split / o_split - 1 less beta x SPY's, |d| <= 25 pct) over t-L .. t-1, both windows >= 80
            pct valid.
Name i is eligible on t when it is a member of year(t)'s point-in-time top 100 (top 100 by the PRIOR year's median
dollar volume, universe_pit100.json, SPY excluded), its raw close of t-1 is >= `min_price`, S_i(t) exists and it
printed an open on t (it is trading today). A session with fewer than `min_names` eligible names is skipped.
ENTRY (MOC at the official close of t, order in before the 15:50 cutoff): long the `k` highest S, short the `k`
lowest, ties by symbol (pandas rank 'first' on alphabetical columns), notional / k dollars a name; `legs` 1 / 2 keep
only the long / the short side. EXIT: MOO at the official open of t+1 (the daily split-adjusted open; assumed the
official opening print, not proven per name - the hunt's disclosure). Name return = o_split(t+1) / c_split(t) - 1.
A picked name whose exit open is missing books 0 and still pays its cost (the hunt's rule; one name-night,
2019-11-21, in the hunt window). DATA HYGIENE, applied AFTER the pick and never a substitute: a picked name with no
close print on t (raw or split) is dropped from that night's side and its slot is NOT refilled. (The hunt required
the close prints before ranking; on member days the open print and the close prints are present on exactly the same
name-days 2016-2026 (panel QA), so the picks are the hunt's.)
CORPORATE-ACTION NIGHT GUARD (not in the prereg; MANAGER 11-14, MISC_PAIRZ_1_0's break rule): a picked name-night
t -> t+1 is VOIDED - no PnL, no cost, slot NOT refilled - when the name's raw close / split close ratio moves by more
than 0.5 pct from t to t+1 (a split, a spin-off or a vendor re-adjustment lands on that night; a missing ratio is no
break - the missing-exit rule above covers a name with no prints on t+1). Applied after the pick like the hygiene
above: it reads the closes of t and t+1, so it can void a name but never choose one. Why: the split-adjusted night
across such a step can be fake - HON 2026-06-29 (lockbox): the split-adjusted series is 2x raw before that day, so its
06-26 close (464.42) -> 06-29 open (240.65) reads a -48 pct night while raw moved -1.9 pct (MANAGER's figures). In
the hunt window (83d, exits 2017-05-22 .. 2025-06-30) the guard voids 9 name-nights the hunt booked at +$7,134.33
net: RTX 2020-04-02 short +$7,023.00 (the UTX -> RTX merger and Carrier / Otis spin-off step, x0.5: the split-adjusted
night reads -70 pct) and 8 ordinary forward-split nights (TSLA 2020-08-28 and 2022-08-24, NVDA 2021-07-19 and
2024-06-07, SHOP 2022-06-28, AVGO 2024-07-12, SMCI 2024-09-30, LRCX 2024-10-02; +$111.33 together - real nights the
rule voids too). Every other night equals the hunt to 1e-6 (tools/misc_nightpersist_parity.py lists the voids and
checks the rest). The SIGNAL history is NOT changed: taking the same nights out of it would move the picks on 49 of
2,020 WF sessions (83d; 39 of 2,115 for 83a) - beyond the voided nights - so the signal keeps the hunt's history; the
25 pct cap already drops the large fake nights (HON's -48 pct, RTX's -70 pct) from it.

TRADE-TO-SESSION MAPPING (the position is HELD OVERNIGHT): ONE trade per ENTRY session t = the whole basket. Entry
bar = the clock's last bar of t (the 15:55 5-minute bar; its close is the 16:00 close = the MOC print); exit bar = the
clock's FIRST bar of its next session (the 09:30 bar; its open = the MOO print). The trade exists only when that next
clock session IS the panel's t+1 (a gap in either -> no trade, never a two-night hold). Field 2 = the night's net
dollars. The engine books the trade on its exit day t+1 - the hunt's series is indexed by exit day too - and its
lockbox keeps the trades that ENTER inside it. mark_open_trades values each basket at the close of t (the one
session close it is open across) at minus the entry half of its cost.

INFORMATION TIMES (all known by 09:30 ET of t, before the MOC order):
  * membership = a calendar-year list built from the prior year's data; FULL = the frozen early-close list and SPY's
    bar; the next session = the exchange calendar;
  * the price floor reads the raw close of t-1; the demeaning set of night s reads year(s), the raw close of s-1 and
    the opens of s;
  * S_i(t)'s last term is the night into t's OPEN (09:30 of t); beta's window ends t-1 (shift 1); the TUG day window
    ends t-1; SPY's night return reads its 09:30 open;
  * "printed an open on t" reads the 09:30 open; the day's count (>= `min_names`) and both ranks read only the above.
The official close of t (split and raw: the fill, the share count, the cent cost), SPY's close of t and every print
of t+1 or later (the exit open; the closes of t+1 for the corporate-action guard) are read only for the PnL and the
post-pick drops; tests/test_misc_nightpersist.py scrambles them and checks that no pick moves, and shows the check
catches a variant that peeks at the holding night.

-- Data ---------------------------------------------------------------------------------
THE MASTER IS ONLY THE CLOCK (SPY 5m RTH, alpaca_split_rth: 2,637 sessions 2016-01-04 .. 2026-06-30, as many as
the panel; tools/misc_nightpersist_parity.py checks the dates match through 2025-06-30; half days end 12:55 and
2019-08-12 ends 15:30, so neither has an entry bar). Prices come from the pinned side panel
    C:/EdgeLog/alpaca_cache/nightpersist_panel/nightpersist_panel_v1.npz   (built by tools/misc_nightpersist_panel.py)
with the hunt's exact inputs (siporb daily split o / c and raw c as float32, universe_pit100.json keys 2017 .. 2026,
tbis_r3 SPY 10-minute bars for SPY's 09:30 open, its last RTH close and the 15:50 bar), 2016-01-04 .. 2026-06-30;
identical to the hunt's loader on 2016-01-04 .. 2025-06-30 (the 13 names first listed in 2026 sit in their
alphabetical columns and are never members before 2026). Members start 2017-01-03 (the universe's first year), so the
demeaned 83d signal has its first full window in May 2017 (first entry 2017-05-19); 2016 rows feed beta and the
beta-residual signal. No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
Known limits: the signal history keeps every corporate-action night under the 25 pct cap, as the hunt did (split /
raw factor steps in the hunt window: RTX 2020-04-03 x0.5, DD 2019-04-02 / 06-03, DHR 2016-07-05, MET 2017-08-07, HON
2018-10, DELL 2021-11-02 and the ordinary splits; in the lockbox HON 2026-06-29 and DD 2026-06-24 (not a member) plus
the splits NFLX, NOW, BKNG, CVNA, KLAC) - only the HELD nights are guarded (above); dividends are not credited
(ex-dividend nights read as losses on longs, gains on shorts).

-- Deviations from the prereg (cell 83d) ------------------------------------------------
  * the corporate-action night guard (above; the HON 2026-06-29 case);
  * t's close prints are checked AFTER the pick (the hunt required them before ranking) - the same picks, since the
    open print and the close prints exist on the same member name-days;
  * k is a knob at a FIXED notional a side (notional / k a name: $10k at k 10, the hunt's size);
  * min_price is also the demeaning set's floor (the prereg fixes $40 for both - the default);
  * the frozen half-day list runs on through 2026-06 (2025-07-03, 2025-11-28, 2025-12-24) and the universe key 2026
    is read (the hunt stopped at 2025-06-30);
  * tug exists only with beta_resid on (the prereg's 83c); legs 1 / 2 and the ranges are engine search knobs.

-- Sizing and costs (INSIDE the plugin - job cost_pts 0, mult 1) --------------------------
`notional` dollars a side, notional / k a name ($10k at k 10). Name cost a night = 2 x `spread_cents` / raw close of t
(one cent a share in, one out, shares = dollars / raw close) + 2 x `fee_bps`, on every picked name every night: the
hunt's 0.02 / c_raw(t) + 0.6 bp. Borrow 0 (megacap shorts, the hunt's statement). PnL is DOLLARS in the trade tuple's
field 2 (PNL_UNITS 'usd'); ONE trade a session = the whole basket.

-- Auto-Validate ranges -------------------------------------------------------------------
OPEN: lookback 60 .. 250 step 10, k 4 .. 16 step 2, min_price 0 .. 80 step 20, beta_resid, tug (searched only with
beta_resid on), legs (0 both, 1 long only, 2 short only). The prereg's four cells are on the grid: 83d (lookback 120,
demeaned - the default), 83a (120, beta_resid), 83b (250, beta_resid), 83c (60, beta_resid, tug). PINNED: notional,
spread_cents, fee_bps, min_names; the 25 pct validity cap, the 80 pct window share and beta's 60 / 40 sessions are
the prereg's constants. Grid 20 x 7 x 5 x 2 x 2 x 3 = 8,400 combinations (6,300 distinct: tug collapses to off
without beta_resid).
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC NIGHTPERSIST 1.0 · overnight-return persistence, point-in-time top-100, MOC -> next open (opus hunt 83d)'
DESCRIPTION = ("At the close, rank the year's top-100 stocks (raw price >= $40) on their average overnight return "
               "over the last 120 nights, each night demeaned against the other names; buy the 10 highest and short "
               "the 10 lowest ($100k a side) at the official close and exit at the next session's official open. "
               "Held overnight. The SPY 5m master is the clock only; stock prices come from a pinned side panel. "
               "Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "SPY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/nightpersist_panel/nightpersist_panel_v1.npz"
PANEL_SHA256 = "60b9b893f7c9c97448d9ae768200ca12c653eb166dfd831ac3377a5f196f1ffa"

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "hard_min": 100000, "hard_max": 100000,
                 "label": "Dollars a side",
                 "tooltip": "Fixed. Longs and shorts each total this many dollars, equal per name."},
    "spread_cents": {"default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
                     "hard_min": 1.0, "hard_max": 1.0,
                     "label": "Cost (cents a share a side)",
                     "tooltip": "Fixed: one cent a share at the closing print and one at the next open."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "step": 0.1, "type": "float",
                "hard_min": 0.3, "hard_max": 0.3,
                "label": "Fees (bp a print)", "tooltip": "Fixed: 0.3 bp of notional at the entry and 0.3 bp at the exit."},
    "min_names": {"default": 40, "min": 40, "max": 40, "step": 1, "type": "int",
                  "hard_min": 40, "hard_max": 40,
                  "label": "Names needed to trade",
                  "tooltip": "Fixed: a session trades only when at least this many names are eligible (the hunt's rule)."},
    "lookback": {"default": 120, "min": 60, "max": 250, "step": 10, "type": "int", "hard_min": 20, "hard_max": 300,
                 "label": "Night window (sessions)",
                 "tooltip": "Average each name's overnight return over this many nights, ending with the night into "
                            "today's open; 80 pct of them must be valid."},
    "k": {"default": 10, "min": 4, "max": 16, "step": 2, "type": "int", "hard_min": 1, "hard_max": 20,
          "label": "Names a side", "tooltip": "Buy the k highest averages, short the k lowest."},
    "min_price": {"default": 40, "min": 0, "max": 80, "step": 20, "type": "int", "hard_min": 0, "hard_max": 200,
                  "label": "Price floor ($)",
                  "tooltip": "Only names whose prior raw close is at least this (also the demeaning set's floor). "
                             "Keeps the one-cent cost small."},
    "beta_resid": {"default": False, "type": "bool", "label": "Residual on beta x SPY",
                   "tooltip": "OFF = each night minus the night's average over the eligible names (cell 83d). "
                              "ON = each night minus beta x SPY's night (cells 83a / 83b)."},
    "tug": {"default": False, "type": "bool", "depends_on": {"beta_resid": True},
            "label": "Night minus day (TUG)",
            "tooltip": "ON = the average residual night minus the average residual day over the window ending "
                       "yesterday (cell 83c). Only with the beta residual."},
    "legs": {"default": 0, "min": 0, "max": 2, "step": 1, "type": "int", "hard_min": 0, "hard_max": 2,
             "label": "Legs (0 both, 1 long, 2 short)",
             "tooltip": "0 = long the k highest and short the k lowest (cell 83d); 1 = the long side only; "
                        "2 = the short side only."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 83d)": {"min_names": [40], "lookback": [120], "k": [10], "min_price": [40],
                                   "beta_resid": [False], "tug": [False], "legs": [0]},
    "Medium (the hunt's cells + neighbours)": {"lookback": [60, 90, 120, 160, 200, 250], "k": [6, 10, 14],
                                               "min_price": [0, 40, 80], "beta_resid": [False, True],
                                               "tug": [False, True], "legs": [0, 1, 2]},
}

PNL_UNITS = "usd"

_MAX_ABS = 0.25            # a night / day / close-to-close return beyond this is invalid (the prereg)
_CA_MOVE = 0.005           # corporate-action break: raw / split close ratio moves more than this from t to t+1
_BETA_LEN = 60             # beta: 60 sessions ending t-1, >= 40 valid, clipped 0.3 .. 2.5, 1.0 while undefined
_BETA_MIN = 40
_DAILY_MAX = 2048          # cap on cached per-config nightly nets (each ~32 KB)
_CACHE = {}                # per-process: the panel (its frames and per-config nights live in the panel's own cache)


def _ca_breaks(R, C):
    """True where the held night t -> t+1 crosses a corporate-action step: the raw / split close ratio moves by more
    than _CA_MOVE from t to t+1 (MISC_PAIRZ_1_0's break rule). A missing ratio is no break (the missing-exit rule
    covers a name with no prints on t+1). Reads the closes of t and t+1: used only AFTER the pick."""
    f = (R / C).to_numpy()
    f_next = np.full_like(f, np.nan)
    f_next[:-1] = f[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        brk = np.abs(f_next / f - 1.0) > _CA_MOVE
    return pd.DataFrame(brk, index=R.index, columns=R.columns)


def _frames(z):
    """Panel arrays -> the hunt's frames (float32 prices cast to float64, as s83_lib.load did)."""
    days = pd.Index(np.asarray(z["dates"]).astype("int64"))
    names = [str(x) for x in z["names"]]

    def fr(key):
        return pd.DataFrame(np.asarray(z[key]).astype(np.float64), index=days, columns=names)

    O, C, R = fr("o"), fr("c"), fr("r")
    member = pd.DataFrame(np.asarray(z["member"], bool), index=days, columns=names)
    full = np.asarray(z["full"], bool)
    nd = len(days)
    nxt = np.zeros(nd, dtype="int64")                 # the next session's date (0 = none in the panel)
    nxt[:-1] = np.asarray(days)[1:]
    o_np = O.to_numpy()
    exit_open = np.full_like(o_np, np.nan)            # the EXIT print: o_split of the next session (PnL only)
    exit_open[:-1] = o_np[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        hold = pd.DataFrame(exit_open, index=days, columns=names) / C - 1.0
    p = {"cache": {}, "days": days, "names": names, "O": O, "C": C, "R": R, "member": member,
         "so": pd.Series(np.asarray(z["spy_open"], np.float64), index=days),
         "sc": pd.Series(np.asarray(z["spy_close"], np.float64), index=days),
         "nxt": nxt,
         "rp": R.shift(1),                            # raw close of t-1 (floor, demeaning set)
         "opened": O.notna(),                         # the name printed an open on t (known 09:30)
         "dayok": full & (nxt > 0),                   # FULL session t with a next session
         # read only after the pick: the close prints of t exist (fill, shares, cost), the night crosses no
         # corporate-action step, and the night's return
         "closed": C.notna() & R.notna(),
         "ca_break": _ca_breaks(R, C),
         "hold": hold}
    return p


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_NIGHTPERSIST_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        p = _frames({key: z[key] for key in z.files})
    _CACHE["panel"] = p
    return p


def _base(p):
    """The hunt's build(): night / day returns (25 pct cap), SPY's night / day, beta (s83_lib.build)."""
    cc = p["cache"]
    if "N" not in cc:
        O, C, so, sc = p["O"], p["C"], p["so"], p["sc"]
        with np.errstate(divide="ignore", invalid="ignore"):
            N = O / C.shift(1) - 1.0
            Dd = C / O - 1.0
            rc = C / C.shift(1) - 1.0
        cc["N"] = N.where(N.abs() <= _MAX_ABS)
        cc["Dd"] = Dd.where(Dd.abs() <= _MAX_ABS)
        cc["nS"] = so / sc.shift(1) - 1.0
        cc["dS"] = sc / so - 1.0
        rc = rc.where(rc.abs() <= _MAX_ABS)
        rm = sc / sc.shift(1) - 1.0
        v = rc.notna() & rm.notna().to_numpy()[:, None]
        X = rc.where(v).fillna(0)
        Y = pd.DataFrame(np.where(v, rm.to_numpy()[:, None], 0.0), index=rc.index, columns=rc.columns)
        w = _BETA_LEN
        n = v.astype(float).rolling(w).sum()
        sx = X.rolling(w).sum()
        sy = Y.rolling(w).sum()
        sxy = (X * Y).rolling(w).sum()
        syy = (Y * Y).rolling(w).sum()
        cov = sxy / n - (sx / n) * (sy / n)
        var = syy / n - (sy / n) ** 2
        cc["beta"] = (cov / var).where(n >= _BETA_MIN).shift(1).clip(0.3, 2.5).fillna(1.0)
    return cc


def _roll_resid(V, mS, beta, L, shift=0):
    """mean over the valid s in the window of V_i(s) - beta_i(t) x mS(s); returns (mean, count) (s83_lib)."""
    v2 = V.notna() & mS.notna().to_numpy()[:, None]
    sv = V.where(v2).fillna(0).rolling(L).sum()
    sm = pd.DataFrame(np.where(v2, np.nan_to_num(mS.to_numpy())[:, None], 0.0), index=V.index,
                      columns=V.columns).rolling(L).sum()
    cnt = v2.astype(float).rolling(L).sum()
    if shift:
        sv, sm, cnt = sv.shift(shift), sm.shift(shift), cnt.shift(shift)
    return sv / cnt - beta * (sm / cnt), cnt


def _demeaned(p, min_price):
    """e_i(s) = n_i(s) - the mean of n over night s's eligible names (member of year(s), raw close of s-1 >= floor,
    valid n). Every column gets e (members or not), as in s83_lib.signals; only members are ever traded."""
    key = ("e", float(min_price))
    cc = p["cache"]
    if key not in cc:
        N = _base(p)["N"]
        el = p["member"] & (p["rp"] >= float(min_price)) & N.notna()
        cc[key] = N.sub(N.where(el).mean(axis=1), axis=0)
    return cc[key]


def _signal(p, lookback, min_price, beta_resid, tug):
    """S_i(t), known by 09:30 of t (higher = long)."""
    L = int(lookback)
    minc = (4 * L + 4) // 5                           # 80 pct of the window: 96 of 120, 200 of 250, 48 of 60
    if not beta_resid:
        e = _demeaned(p, min_price)
        ce = e.notna().astype(float).rolling(L).sum()
        return (e.fillna(0).rolling(L).sum() / ce).where(ce >= minc)
    b = _base(p)
    sn, cn = _roll_resid(b["N"], b["nS"], b["beta"], L)
    if not tug:
        return sn.where(cn >= minc)
    sd, cd = _roll_resid(b["Dd"], b["dS"], b["beta"], L, shift=1)
    return (sn - sd).where((cn >= minc) & (cd >= minc))


def _picks(p, lookback, k, min_price, beta_resid, tug, min_names):
    """(long mask, short mask, eligible count) from information known by 09:30 ET of each session."""
    S = _signal(p, lookback, min_price, beta_resid, tug)
    elig = (p["member"] & (p["rp"] >= float(min_price)) & S.notna() & p["opened"]
            & p["dayok"][:, None])
    ne = elig.sum(axis=1)
    elig = elig & (ne >= int(min_names)).to_numpy()[:, None]
    s = S.where(elig)
    n = s.notna().sum(axis=1)
    rk = s.rank(axis=1, ascending=False, method="first")
    day = (n >= int(min_names)).to_numpy()[:, None]
    longs = (rk <= int(k)) & day
    shorts = (rk > (n.to_numpy()[:, None] - int(k))) & s.notna() & day
    return longs, shorts, n


def _book(p, notional, spread_cents, fee_bps, min_names, lookback, k, min_price, beta_resid, tug, legs):
    """One row per traded ENTRY session t (index yyyymmdd): exit day, gross / cost by side, counts, net $."""
    Lg, Sh, n = _picks(p, lookback, k, min_price, beta_resid, tug, min_names)
    Lg = Lg & p["closed"]                             # hygiene drop after the pick, never refilled
    Sh = Sh & p["closed"]
    void = (Lg | Sh) & p["ca_break"]                  # corporate-action night: no PnL, no cost, never refilled
    Lg = Lg & ~p["ca_break"]
    Sh = Sh & ~p["ca_break"]
    H = p["hold"]
    Hz = H.fillna(0.0)                                # a missing exit open books 0 (cost still paid)
    cents = 2.0 * float(spread_cents) / 100.0
    fee = round(2.0 * float(fee_bps) * 1e-4, 12)
    with np.errstate(divide="ignore", invalid="ignore"):
        cst = cents / p["R"] + fee
    nn = float(notional) / int(k)
    res = pd.DataFrame({"gl": nn * Hz.where(Lg).sum(axis=1), "gs": -nn * Hz.where(Sh).sum(axis=1),
                        "cl": nn * cst.where(Lg).sum(axis=1), "cs": nn * cst.where(Sh).sum(axis=1),
                        "nl": Lg.sum(axis=1), "ns": Sh.sum(axis=1), "void": void.sum(axis=1),
                        "miss": (H.isna() & (Lg | Sh)).sum(axis=1), "n": n})
    res["exit"] = p["nxt"]
    if int(legs) == 1:
        res["g"], res["c"], act = res.gl, res.cl, res.nl > 0
    elif int(legs) == 2:
        res["g"], res["c"], act = res.gs, res.cs, res.ns > 0
    else:
        res["g"], res["c"], act = res.gl + res.gs, res.cl + res.cs, (res.nl > 0) & (res.ns > 0)
    res["net"] = res.g - res.c
    res = res[act & (n >= int(min_names)) & np.isfinite(res.net)]
    return res


def _knobs(params):
    """DEFAULT_PARAMS defaults overlaid with `params` (unknown keys ignored); tug is idle without beta_resid."""
    kn = {k: v["default"] for k, v in DEFAULT_PARAMS.items()}
    kn.update({k: v for k, v in (params or {}).items() if k in kn})
    if not kn["beta_resid"]:
        kn["tug"] = False
    return kn


def _daily(p, **kn):
    """(entry yyyymmdd, exit yyyymmdd, net $) arrays of the traded nights for one config, over every panel session."""
    key = ("day",) + tuple(kn[k] for k in DEFAULT_PARAMS)
    cc = p["cache"]
    if key not in cc:
        if sum(1 for x in cc if x[0] == "day") >= _DAILY_MAX:
            for x in [x for x in cc if x[0] == "day"]:
                del cc[x]
        res = _book(p, **kn)
        cc[key] = (res.index.to_numpy().astype("int64"), res["exit"].to_numpy().astype("int64"),
                   res["net"].to_numpy().astype(float))
    return cc[key]


def _clock_nights(index, n):
    """[(entry day, exit day, entry bar, exit bar)] from the clock: the entry day's last bar is the 15:55 bar and
    the next clock session's first bar is the 09:30 bar."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy().astype("int64")
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [n]])
    out = []
    for a, b, a2 in zip(starts[:-1], ends[:-1], starts[1:]):
        if minute[b - 1] == 955 and minute[a2] == 570:
            out.append((int(date[a]), int(date[a2]), int(b - 1), int(a2)))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, spread_cents: float = 1.0, fee_bps: float = 0.3, min_names: int = 40,
                 lookback: int = 120, k: int = 10, min_price: int = 40, beta_resid: bool = False,
                 tug: bool = False, legs: int = 0,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None:
        return None
    o = np.asarray(opens, float)
    c = np.asarray(closes, float)
    nights = _clock_nights(index, n)
    if not nights:                                    # no RTH close -> next-open pair on this tape: never open the panel
        return None
    p = _panel()
    if p is None:
        return None
    kn = _knobs({"notional": notional, "spread_cents": spread_cents, "fee_bps": fee_bps, "min_names": min_names,
                 "lookback": lookback, "k": k, "min_price": min_price, "beta_resid": beta_resid, "tug": tug,
                 "legs": legs})
    dd, xd, net = _daily(p, **kn)
    trades = []
    for d, d2, eb, xb in nights:
        if _stop_event is not None and _stop_event.is_set():
            return None
        j = int(np.searchsorted(dd, d))
        if j >= len(dd) or dd[j] != d or xd[j] != d2:  # not traded, or the clock's next session is not the panel's
            continue
        trades.append((eb, xb, float(net[j]), 1, float(c[eb]), float(o[xb])))
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
    """Every basket is filled at the official close of t and leaves at the official open of t+1, so it is open
    across exactly ONE session close - its entry bar's. Its value there = minus the entry half of its cost (the
    MOC fill IS that closing print): [(entry bar, -entry cost)] a trade, in the dollars of t[2]. The remainder
    (gross and the exit half) lands on the exit day. No panel / no index -> no marks (booked at close)."""
    trades = list(trades or [])
    if not trades:
        return []
    p = _panel() if index is not None else None
    if p is None:
        return [[] for _ in trades]
    kn = _knobs(params)
    res = _book(p, **kn)
    half = 0.5 * res["c"]
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    out = []
    for t in trades:
        e = int(t[0])
        d = int(idx[e].year * 10000 + idx[e].month * 100 + idx[e].day)
        out.append([(e, -float(half[d]))] if d in half.index else [])
    return out

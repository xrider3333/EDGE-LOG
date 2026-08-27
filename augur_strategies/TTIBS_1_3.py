"""
FIRST MEASUREMENT (2026-08-27, supervisor-reproduced independently). NQ 5m
db_noadj_rth, 0.533 pts/RT, $20/pt, at the inherited champion params (trigger ibs /
ibs_entry 0.4 / ibs_exit / hold_cap 8 / no ma200):

  variant                     pre-lockbox 2010..2025-07        LOCKBOX 2025-07..2026-07
  1.1 honest next_open        $342,862  PF 1.61  net/DD 7.20   -$37,870  PF 0.74
  1.3 late  cut_bars=1        $377,973  PF 1.61  net/DD 8.19   +$40,404  PF 1.33
  1.3 late  cut_bars=2        $390,268  PF 1.62  net/DD 10.44  +$30,904  PF 1.25
  1.3 late  cut_bars=3        $307,771  PF 1.48  net/DD 7.27   +$62,242  PF 1.51
  1.3 late  cut_bars=6        $259,639  PF 1.39  net/DD 3.73   +$38,892  PF 1.29
  (the untradeable TTIBS 1.0 close fill, for scale: $392,423 / 8.32 pre, +$26,865 LB)

READ: the pre-lockbox pick - made WITHOUT reference to the lockbox - is cut_bars=2, the
best net AND best net/DD of the four. Its lockbox is +$30,904 / PF 1.25, versus the
honest next-open fork's -$37,870 / PF 0.74 on the same window. All four cut values are
positive in the lockbox, so the DIRECTION is robust even though the level is not.
Deciding ~10 minutes before the close and filling one bar later recovers essentially all
of the look-ahead's value LEGITIMATELY, which says the signal was real and the honest
next-open fill was simply too late: the reversion happens overnight, and entering at the
next open hands that move away.

HONEST CAVEATS - do not treat this as validated:
  1. These params were crowned by searches that were selecting the look-ahead fill, so
     they are contaminated priors. A full Auto-Validate must re-search the space.
  2. The lockbox has now been read FOUR times on this variant (one per cut_bars). Only
     the cut_bars=2 figure is a pre-registered read; the other three are "seen".
  3. Lockbox net/DD is weak in absolute terms (0.67-1.38) on 39-42 trades.
  4. One parameter point per cut value, no gates run yet.

TTIBS 1.3 — LATE-SAME-DAY entry fork of TTIBS 1.1 (LONG ONLY).

HYPOTHESIS (2026-08-27): TTIBS 1.0's look-ahead ("close" fill mode) fills at the
signal day's own close using IBS computed from that same close — untradeable, but
worth a fortune ($26,865/PF 1.23 look-ahead vs -$37,870/PF 0.74 honest next_open,
same 38 trades, sealed last-12-months). The question this file answers: is that
value coming from a REAL signal that the honest fill just executes too late (a full
overnight gap after the close prints), or is it pure fill-price theft?

The test: decide LATE IN THE SAME SESSION instead of at the close. At bar
`cut_bars` before the session's last bar you already know most of the day's range —
IBS-so-far is close to the final IBS — and, critically, you can ACTUALLY TRADE this:
decide on bar k, fill on bar k+1's open. Fully causal, no look-ahead. If this
recovers most of the look-ahead's value, the signal is real and the honest fork was
just late. If it doesn't, the look-ahead was fill-price theft, not signal, and this
family stays closed.

`cut_bars` (new param, default 1, range [1,24], hard range [1,24]) counts back from
the session's LAST bar: cut_bars=1 decides on the second-to-last 5m bar, fills at the
final bar's open. cut_bars=0 is DELIBERATELY NOT ALLOWED — deciding on the final bar
and filling at it (or worse, at its own close) is exactly the look-ahead this family
was caught on in TTIBS 1.0/1.1's docstrings. min=1 closes that door structurally, not
just by convention.

`entry_when` (new param, replaces `fill_mode`) selects between:
  - "next_open"      : reproduces TTIBS 1.1 EXACTLY, byte-for-byte (same trades, same
                        pnl) — the honest baseline, kept for direct comparison.
  - "late_same_day"   : the hypothesis under test (default).

LATE-SAME-DAY mechanics, per session t with bounds (a, b) = _session_bounds()[t]
(bars a..b-1 belong to session t):
  - decision bar k = b - 1 - cut_bars. If k <= a (session too short for this many
    bars-before-close), the day is skipped — no signal test, no trade.
  - Partial-session aggregates are built THROUGH bar k only (never past it):
        ph = h[a:k+1].max();  pl = l[a:k+1].min();  pc = c[k]
        partial_ibs = (pc - pl) / (ph - pl), or 0.5 if the partial range is ~0.
  - Triggers use these PARTIAL values wherever TTIBS 1.1 used the full-day
    day_close[t]/ibs[t]:
        ibs     : partial_ibs < ibs_entry
        mon1pct : weekday[t]==Mon AND pc <= day_close[t-1] * (1 - mon_drop)
        mon_ibs : weekday[t]==Mon AND pc < day_close[t-1] AND partial_ibs < 0.5
  - ma200 regime gate: TTIBS 1.1's sma200[t] is a trailing 200-session SMA INCLUSIVE
    of today's day_close[t] — using it here would silently look ahead (today's own
    FINAL close feeding a same-day decision). So for late_same_day the gate is
    recomputed from the prior 200 COMPLETED sessions only: pc > mean(day_close[t-200
    : t]) (t-200..t-1, i.e. today excluded). Needs t >= 200.
  - Fill: entry_price = o[k+1] (next bar's open, strictly after the decision bar),
    entry_bar = k+1. k+1 <= b-1 is guaranteed since cut_bars >= 1, so the fill bar is
    always still inside session t itself — no next-session lookup needed for entry.
  - Roll-seam guard: the entry's session t still checked against blocked_fill_days,
    same as every other mode.
  - Exit scan is UNCHANGED: starts at the NEXT session (first_check = t+1) and reuses
    the existing daily exit_mode / hold_cap / roll-seam force-exit / end-of-data DROP
    logic verbatim — only the ENTRY side is new.

Everything else — trigger/ibs_entry/exit_mode/hold_cap ranges, the roll-seam guard
(detect_roll_seams, unchanged), MAE calc, trade-tuple shape, metrics dict, PNL
convention (points only, cost_pts applied downstream by the engine) — is untouched
from TTIBS 1.1. See TTIBS_1_1.py's own docstring for the roll-seam / end-of-data
background; not repeated here.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'TTIBS 1.3 · IBS mean reversion, LATE SAME-DAY entry (long)'
DESCRIPTION = ("Tests whether TTIBS's look-ahead close-fill value is a real signal or "
               "fill-price theft: decide `cut_bars` before the session's close (partial "
               "IBS through that bar), fill at the NEXT bar's open — still same-session, "
               "fully causal. entry_when='next_open' reproduces TTIBS 1.1 exactly "
               "(no look-ahead either way); entry_when='late_same_day' is the hypothesis "
               "under test. cut_bars=0 is deliberately not offered (min=1) - that would "
               "be the TTIBS 1.0 look-ahead again. Same triggers/exits/hold-cap/ma200/"
               "roll-seam guard as TTIBS 1.1. NQ daily RTH built from 5m bars.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}   # daily bars built from 5m RTH
_AUGUR_PARENT = "TTIBS_1_1"   # forked from the honest-fill fork; adds late-same-day entry

DEFAULT_PARAMS = {
    "trigger": {
        "default": "ibs", "type": "str",
        "options": ["mon1pct", "mon_ibs", "ibs"],
        "label": "Entry trigger",
        "tooltip": "mon1pct = Monday selloff >= mon_drop vs prior close (classic "
                   "Turnaround Tuesday). mon_ibs = Monday, down day, AND IBS<0.5. "
                   "ibs = any day with IBS < ibs_entry (no day-of-week gate). Under "
                   "entry_when=late_same_day these are tested on PARTIAL (through the "
                   "decision bar) values, not the final day's.",
    },
    "mon_drop": {
        "default": 0.01, "min": 0.0, "max": 0.05, "step": 0.0025, "type": "float",
        "hard_min": 0.0, "hard_max": 0.10,
        "label": "Monday drop threshold (fraction)",
        "tooltip": "Only used by trigger=mon1pct: today's close (or partial close, see "
                   "entry_when) must be <= prior close x (1 - mon_drop). 0.01 = a 1% "
                   "Monday selloff.",
        "depends_on": {"trigger": "mon1pct"},
    },
    "ibs_entry": {
        "default": 0.20, "min": 0.05, "max": 0.40, "step": 0.05, "type": "float",
        "hard_min": 0.0, "hard_max": 0.5,
        "label": "IBS entry threshold",
        "tooltip": "Only used by trigger=ibs: enter when IBS = (close-low)/(high-low) "
                   "is below this. Lower = closer to the day's low = deeper weakness. "
                   "Under entry_when=late_same_day, IBS is computed through the "
                   "decision bar only (partial IBS), not the final day's IBS.",
        "depends_on": {"trigger": "ibs"},
    },
    "entry_when": {
        "default": "late_same_day", "type": "str",
        "options": ["late_same_day", "next_open"],
        "label": "Entry timing",
        "tooltip": "next_open = fill at the NEXT session's real 09:30 open, decided at "
                   "today's own close (reproduces TTIBS 1.1 exactly). late_same_day = "
                   "decide cut_bars before TODAY's session close, using partial-session "
                   "IBS/close, and fill at the very next 5m bar's open (still inside "
                   "today's session) - fully causal, the hypothesis this fork tests.",
    },
    "cut_bars": {
        "default": 1, "min": 1, "max": 12, "step": 1, "type": "int",
        "hard_min": 1, "hard_max": 24,
        "label": "Decide N bars before the close",
        "tooltip": "Only used by entry_when=late_same_day. On 5m bars, cut_bars=1 "
                   "means decide on the second-to-last bar of the session and fill at "
                   "the next (final) bar's open; higher = decide earlier in the day. "
                   "0 is deliberately NOT allowed: deciding on the final bar (and "
                   "filling at/near it) is the exact look-ahead this family was caught "
                   "on in TTIBS 1.0 - min=1 closes that door structurally.",
        "depends_on": {"entry_when": "late_same_day"},
    },
    "exit_mode": {
        "default": "ibs_exit", "type": "str",
        "options": ["next_close", "strength", "ibs_exit"],
        "label": "Exit rule",
        "tooltip": "next_close = first close after entry. strength = first close > "
                   "prior day's high. ibs_exit = first day with IBS > 0.8 (closed "
                   "strong). All capped at hold_cap trading days, scan starting the "
                   "session AFTER the entry session, unchanged from TTIBS 1.1.",
    },
    "hold_cap": {
        "default": 6, "min": 1, "max": 10, "step": 1, "type": "int",
        "hard_min": 1, "hard_max": 20,
        "label": "Max hold (trading days)",
        "tooltip": "Force-exit at this day's close if no exit signal has fired yet.",
    },
    "ma200": {
        "default": False, "type": "bool",
        "label": "200-session regime filter",
        "tooltip": "Only enter when the entry-relevant close > the 200-session SMA of "
                   "daily closes. next_open: trailing SMA inclusive of today (matches "
                   "TTIBS 1.1 exactly, decision is at today's own close). "
                   "late_same_day: SMA of the PRIOR 200 COMPLETED sessions only "
                   "(today's close is excluded - using today's final close here would "
                   "be a same-day look-ahead).",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (core sanity)": {
        "trigger": ["mon1pct", "ibs"], "mon_drop": [0.01], "ibs_entry": [0.20],
        "entry_when": ["late_same_day"], "cut_bars": [1],
        "exit_mode": ["next_close"], "hold_cap": [4], "ma200": [False],
    },
    "Medium (trigger x exit)": {
        "trigger": ["mon1pct", "mon_ibs", "ibs"], "mon_drop": [0.01],
        "ibs_entry": [0.15, 0.20, 0.25], "entry_when": ["late_same_day", "next_open"],
        "cut_bars": [1, 2, 3], "exit_mode": ["next_close", "strength", "ibs_exit"],
        "hold_cap": [4], "ma200": [False],
    },
    "Long   (full triage grid)": {
        "trigger": ["mon1pct", "mon_ibs", "ibs"], "mon_drop": [0.01],
        "ibs_entry": [0.10, 0.20, 0.30], "entry_when": ["late_same_day", "next_open"],
        "cut_bars": [1, 2, 3, 6], "exit_mode": ["next_close", "strength", "ibs_exit"],
        "hold_cap": [2, 4, 6], "ma200": [False, True],
    },
}


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b))
        a = b
    return bounds


def _third_weekday(year, month, weekday=2):
    """Date of the 3rd occurrence of `weekday` (0=Mon..6=Sun) in (year, month).
    weekday=2 -> 3rd Wednesday (the standard quarterly futures-roll reference)."""
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0,
                       base_win=60, pre_days=12, post_days=2):
    """Return a sorted list of daily-bar indices `s` such that the jump
    close[s-1] -> open[s] is a detected quarterly roll seam.

    day_open/day_close: per-session daily arrays (np.ndarray).
    day_ts: list/array of pandas Timestamps, one per session (session's first bar).

    Method: restrict the search to a calendar window around each quarter's (Mar/Jun/
    Sep/Dec) 3rd Wednesday -- [3rd-Wed - pre_days, 3rd-Wed + post_days] -- and within
    that window flag the single day with the largest |overnight gap| IF it clears both
    an absolute floor (abs_th points) and a local-baseline ratio (>= ratio_th x the
    trailing base_win-session median |gap|, excluding the window itself). A global
    outlier scan mostly re-finds real crashes (COVID Mar-2020, Aug-2015, Aug-2024)
    rather than the roll stitch, which is why the search is calendar-scoped instead.
    """
    n = len(day_close)
    if n < base_win + 5:
        return []
    ts = pd.DatetimeIndex(day_ts)
    if ts.tz is not None:
        ts = ts.tz_localize(None)             # compare tz-naive vs. tz-naive 3rd-Wed refs
    gap = np.empty(n); gap[:] = np.nan
    gap[1:] = day_open[1:] - day_close[:-1]
    abs_gap = np.abs(gap)

    baseline = np.full(n, np.nan)
    for i in range(base_win, n):
        window = abs_gap[i - base_win:i]
        window = window[~np.isnan(window)]
        if len(window) >= max(10, base_win // 3):
            baseline[i] = np.median(window)

    quarters = sorted({(t.year, t.month) for t in ts if t.month in (3, 6, 9, 12)})
    seams = []
    for (y, m) in quarters:
        wed3 = _third_weekday(y, m)
        win_start = wed3 - pd.Timedelta(days=pre_days)
        win_end = wed3 + pd.Timedelta(days=post_days)
        idx_in_win = [i for i in range(n) if win_start <= ts[i] <= win_end
                      and not np.isnan(gap[i]) and not np.isnan(baseline[i])]
        if not idx_in_win:
            continue
        best = max(idx_in_win, key=lambda i: abs_gap[i])
        if abs_gap[best] >= abs_th and baseline[best] > 0 and \
           (abs_gap[best] / baseline[best]) >= ratio_th:
            seams.append(best)
    return sorted(seams)


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    trigger: str = "ibs", mon_drop: float = 0.01, ibs_entry: float = 0.20,
    entry_when: str = "late_same_day", cut_bars: int = 1,
    exit_mode: str = "next_close",
    hold_cap: int = 4, ma200: bool = False,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    if entry_when not in ("late_same_day", "next_open"):
        entry_when = "late_same_day"
    if cut_bars < 1:
        cut_bars = 1                          # 0 is the look-ahead this fork exists to avoid
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 20:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None or index is None:
        return None                       # needs real dates (weekday, roll seams)

    bounds = _session_bounds(did, n)
    D = len(bounds)
    if D < 210:                            # need real headroom for ma200 warm-up etc
        return None

    idx = pd.DatetimeIndex(index)
    day_open  = np.array([o[a] for a, b in bounds])
    day_high  = np.array([h[a:b].max() for a, b in bounds])
    day_low   = np.array([l[a:b].min() for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_start_bar = np.array([a for a, b in bounds])
    day_end_bar   = np.array([b - 1 for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    weekday = np.array([t.dayofweek for t in day_ts])

    rng = day_high - day_low
    ibs = np.where(rng > 1e-9, (day_close - day_low) / np.where(rng > 1e-9, rng, 1.0), 0.5)

    # Trailing 200-session SMA, inclusive of today (known at today's own close -> no
    # look-ahead for entry_when=next_open, byte-identical to TTIBS 1.1). csum-based so
    # it's O(D), not an O(D*200) rolling-window loop. Also gives us csum0, reused below
    # for the late_same_day gate's PRIOR-200 (excl. today) variant.
    sma200 = np.full(D, np.nan)
    csum = np.cumsum(day_close)
    csum0 = np.concatenate([[0.0], csum])          # csum0[i] = sum of day_close[:i]
    if D >= 200:
        sma200[199:] = (csum0[200:] - csum0[:D - 199]) / 200.0

    seam_days = detect_roll_seams(day_open, day_close, day_ts)
    force_exit_days = {s - 1 for s in seam_days if s - 1 >= 0}
    blocked_fill_days = set(force_exit_days)

    pnl_list, trade_log = [], []
    t = 1                                   # need a prior day for reference closes
    while t < D:
        if _stop_event is not None and _stop_event.is_set():
            break

        if entry_when == "next_open":
            signal = False
            if trigger == "mon1pct":
                if weekday[t] == 0:
                    signal = day_close[t] <= day_close[t - 1] * (1.0 - mon_drop)
            elif trigger == "mon_ibs":
                if weekday[t] == 0:
                    signal = (day_close[t] < day_close[t - 1]) and (ibs[t] < 0.5)
            elif trigger == "ibs":
                signal = ibs[t] < ibs_entry

            if signal and ma200:
                if t < 199 or np.isnan(sma200[t]):
                    signal = False
                else:
                    signal = signal and (day_close[t] > sma200[t])

            if not signal:
                t += 1
                continue

            fill_day = t + 1
            if fill_day >= D:
                t += 1; continue
            entry_price = day_open[fill_day]
            entry_bar = day_start_bar[fill_day]

            if fill_day in blocked_fill_days:
                t += 1; continue

            first_check = fill_day

        else:  # late_same_day
            a, b = bounds[t]
            k = b - 1 - cut_bars
            if k <= a:
                t += 1; continue            # session too short for this many cut_bars

            ph = h[a:k + 1].max(); pl = l[a:k + 1].min(); pc = c[k]
            prng = ph - pl
            partial_ibs = (pc - pl) / prng if prng > 1e-9 else 0.5

            signal = False
            if trigger == "mon1pct":
                if weekday[t] == 0:
                    signal = pc <= day_close[t - 1] * (1.0 - mon_drop)
            elif trigger == "mon_ibs":
                if weekday[t] == 0:
                    signal = (pc < day_close[t - 1]) and (partial_ibs < 0.5)
            elif trigger == "ibs":
                signal = partial_ibs < ibs_entry

            if signal and ma200:
                if t < 200:
                    signal = False          # need 200 PRIOR completed sessions (excl. today)
                else:
                    prior_mean = (csum0[t] - csum0[t - 200]) / 200.0
                    signal = signal and (pc > prior_mean)

            if not signal:
                t += 1
                continue

            fill_day = t                    # fill is still inside today's own session
            entry_price = o[k + 1]
            entry_bar = k + 1

            if fill_day in blocked_fill_days:
                t += 1; continue

            first_check = t + 1             # exit scan starts the NEXT session

        last_day = min(first_check + hold_cap - 1, D - 1)

        exit_day = None
        exit_price = None
        for cday in range(first_check, last_day + 1):
            if cday in force_exit_days:
                exit_day = cday; exit_price = day_close[cday]; break
            if exit_mode == "next_close":
                exit_day = cday; exit_price = day_close[cday]; break
            if exit_mode == "strength" and day_close[cday] > day_high[cday - 1]:
                exit_day = cday; exit_price = day_close[cday]; break
            if exit_mode == "ibs_exit" and ibs[cday] > 0.8:
                exit_day = cday; exit_price = day_close[cday]; break
            if cday == last_day:
                exit_day = cday; exit_price = day_close[cday]; break

        if exit_day is None:
            # ran out of loaded data before an exit resolved -> DROP the trade
            # entirely (lockbox-honest end-of-data handling; never truncate).
            break

        pnl = exit_price - entry_price
        mae_pts = entry_price - min(day_low[fill_day:exit_day + 1].min(), entry_price)
        exit_bar = day_end_bar[exit_day]
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(entry_bar), int(exit_bar), float(pnl), 1,
                              float(entry_price), float(exit_price), float(mae_pts)))
        t = exit_day + 1

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/TTIBS_1_3.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOADS = os.path.join(ROOT, "augur_uploads")
    MASTER  = os.path.join(UPLOADS, "NOADJ_NQ_5m_RTH.csv")
    MULT    = 20.0
    FEE     = 0.533

    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))]
    df = df.sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("TTIBS 1.3 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)" %
          (len(df), len(set(day_id))))
    print()

    configs = [
        ("ibs<0.20, next_open, next_close, cap4", dict(trigger="ibs", ibs_entry=0.20,
            entry_when="next_open", exit_mode="next_close", hold_cap=4)),
        ("ibs<0.20, late_same_day cut1, next_close, cap4", dict(trigger="ibs", ibs_entry=0.20,
            entry_when="late_same_day", cut_bars=1, exit_mode="next_close", hold_cap=4)),
        ("mon1pct, late_same_day cut2, strength, cap6", dict(trigger="mon1pct", mon_drop=0.01,
            entry_when="late_same_day", cut_bars=2, exit_mode="strength", hold_cap=6)),
        ("mon_ibs, late_same_day cut3, ibs_exit, cap4", dict(trigger="mon_ibs",
            entry_when="late_same_day", cut_bars=3, exit_mode="ibs_exit", hold_cap=4)),
        ("ibs<0.20, late_same_day cut1, next_close, cap4, ma200", dict(trigger="ibs",
            ibs_entry=0.20, entry_when="late_same_day", cut_bars=1,
            exit_mode="next_close", hold_cap=4, ma200=True)),
    ]

    print("%-46s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD $"))
    print("-" * 95)
    for label, kw in configs:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index, **kw,
                         return_trades=True)
        if r is None:
            print("%-46s  NO TRADES" % label); continue
        net_pts = r["total_pnl"] - FEE * r["num_trades"]
        net_usd = net_pts * MULT
        dd_usd = r["max_drawdown"] * MULT   # gross DD (cost not folded into curve here)
        print("%-46s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(dd_usd)))

    print()
    print("Sane-output check only -- trust real numbers only from the full triage run.")

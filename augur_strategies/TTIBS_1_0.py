"""
TTIBS 1.0 — Turnaround-Tuesday / Internal-Bar-Strength daily mean reversion (LONG ONLY).

Concept: buy weakness on a DAILY bar, mean-revert. IBS = (close-low)/(high-low) reads
where the close landed inside the day's own range (near 0 = closed on the low, near 1 =
closed on the high). Three entry triggers ("trigger" param):

  - mon1pct : Monday AND close <= prior session's close x (1 - mon_drop). The classic
              "Turnaround Tuesday" setup — buy a Monday selloff, expect a bounce.
  - mon_ibs : Monday AND close < prior close AND IBS < 0.5 (weak AND closed soft).
  - ibs     : ANY day with IBS < ibs_entry (the plain SPY-style IBS mean-reversion
              trigger, no day-of-week gate).

"Prior session's close" is just the previous row in the daily series, so a missing
Friday (holiday) automatically falls back to the prior trading day's close — no
special-casing needed.

Two fill modes ("fill_mode"): `close` = fill at the signal day's own close (a KNOWN,
documented look-ahead — kept only as a look-ahead-vs-honest comparison baseline, never
the gate-deciding mode). `next_open` = fill at the NEXT session's real 09:30 RTH open
(the deploy-honest mode) — uses the actual first-5m-bar open of the next session, not
an approximation.

Three exits ("exit_mode"), all capped at `hold_cap` trading days:
  - next_close : exit at the first close after entry (1-day round trip for next_open
                 fills; a genuine next-day hold for close fills).
  - strength   : exit at the first day's close whose close > the PRIOR day's high.
  - ibs_exit   : exit at the first day's close with IBS > 0.8 (closed strong).

Optional `ma200` regime gate: only enter when close > the 200-session SMA of daily
closes (trailing, inclusive of today — no look-ahead, since the decision is made at
today's own close). No stop-loss in v1.0 (matches the published SPY/ETF IBS family).

── Roll-seam guard (NOADJ quarterly stitch) ───────────────────────────────────────
The NOADJ continuous-contract stitch embeds a real price discontinuity at every
quarterly roll (Mar/Jun/Sep/Dec). `detect_roll_seams()` finds it by searching a
calendar window around each quarter's 3rd Wednesday (roll week) for the day whose
|overnight gap| is both >=15 points and >=2.5x the trailing 60-session median |gap| —
a LOCAL outlier check, not a global one (a global scan mostly re-finds real crashes
like Mar-2020 / Aug-2015 / Aug-2024, which swamp the roll seam in raw magnitude).
Calibrated on the 2010-2025-06-30 window: 48/64 quarters flag, offsets vs. the 3rd
Wednesday cluster at a median of -2 days (range -12..+2) — i.e. a few days BEFORE
roll-Wednesday, matching the documented pattern. See scratchpad ttibs_triage_prereg.md
for the calibration detail. Any position open going into the close of the day BEFORE a
flagged seam is force-exited there; no new entry may FILL on that day either —
positions never hold across a detected seam.

── Data window / end-of-data handling ─────────────────────────────────────────────
Requires `day_id` (session grouping) AND `index` (real bar timestamps, for weekday /
month / the roll-seam calendar search) — same precedent as REPLAY_1_0.py: returns None
if `index` isn't supplied (e.g. run through a code path that only wires up day_id).
A position still open when the loaded array runs out is DROPPED entirely, never
force-closed at the last available bar — this is what makes the lockbox-honest
"exclude, don't truncate" rule fall out for free: just don't load data past the seal
date, and any trailing open trade silently disappears.

PNL = SHARES*(EXIT-ENTRY), points only, no cost/$ baked in — fees (cost_pts) applied
downstream by the engine, same convention as every other strategy in this library
(ORB_3_1.py, DRIVE_1_0.py). NQ costs: 0.533 pts/RT, $20/pt (applied by the caller).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'TTIBS 1.0 · Turnaround-Tuesday / IBS mean reversion (long)'
DESCRIPTION = ("Daily buy-weakness mean reversion, long only: Monday-selloff or "
               "any-day low-IBS entry, exit on strength/IBS-recovery/next-close, "
               "capped hold. Next-open (deploy-honest) vs close (look-ahead) fills "
               "both reported. Roll-seam guarded. NQ daily RTH.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}   # daily bars built from 5m RTH
# Not a fork of ORB/ENGU-Q/DRIVE — a from-scratch daily mean-reversion family,
# triaged as a challenger against those champions (deliberately no _AUGUR_PARENT).

DEFAULT_PARAMS = {
    "trigger": {
        "default": "ibs", "type": "str",
        "options": ["mon1pct", "mon_ibs", "ibs"],
        "label": "Entry trigger",
        "tooltip": "mon1pct = Monday selloff >= mon_drop vs prior close (classic "
                   "Turnaround Tuesday). mon_ibs = Monday, down day, AND IBS<0.5. "
                   "ibs = any day with IBS < ibs_entry (no day-of-week gate).",
    },
    "mon_drop": {
        "default": 0.01, "min": 0.0, "max": 0.05, "step": 0.0025, "type": "float",
        "label": "Monday drop threshold (fraction)",
        "tooltip": "Only used by trigger=mon1pct: today's close must be <= prior "
                   "close x (1 - mon_drop). 0.01 = a 1% Monday selloff.",
        "depends_on": {"trigger": "mon1pct"},
    },
    "ibs_entry": {
        "default": 0.20, "min": 0.05, "max": 0.40, "step": 0.05, "type": "float",
        "label": "IBS entry threshold",
        "tooltip": "Only used by trigger=ibs: enter when IBS = (close-low)/(high-low) "
                   "is below this. Lower = closer to the day's low = deeper weakness.",
        "depends_on": {"trigger": "ibs"},
    },
    "fill_mode": {
        "default": "next_open", "type": "str",
        "options": ["close", "next_open"],
        "label": "Entry fill",
        "tooltip": "next_open (deploy-honest) = fill at the NEXT session's real 09:30 "
                   "open. close = fill at the signal day's own close — a documented "
                   "look-ahead, kept only for comparison; never trust this mode alone.",
    },
    "exit_mode": {
        "default": "ibs_exit", "type": "str",
        "options": ["next_close", "strength", "ibs_exit"],
        "label": "Exit rule",
        "tooltip": "next_close = first close after entry. strength = first close > "
                   "prior day's high. ibs_exit = first day with IBS > 0.8 (the "
                   "2026-07-14 triage's surviving plateau: ibs_exit + hold_cap=6 is "
                   "the only exit_mode/hold_cap combo that clears all 6 gates -- "
                   "hold_cap 2/4 correlate too strongly with the ENGU-Q champion). "
                   "All capped at hold_cap trading days.",
    },
    "hold_cap": {
        "default": 6, "min": 1, "max": 10, "step": 1, "type": "int",
        "label": "Max hold (trading days)",
        "tooltip": "Force-exit at this day's close if no exit signal has fired yet. "
                   "6 is the triage-validated default (see exit_mode tooltip); 2/4 "
                   "fail the not-a-disguise gate vs ENGU-Q.",
    },
    "ma200": {
        "default": False, "type": "bool",
        "label": "200-session regime filter",
        "tooltip": "Only enter when close > the 200-session SMA of daily closes "
                   "(trailing, inclusive of today). Off = pure mean reversion, no "
                   "trend-regime gate.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (core sanity)": {
        "trigger": ["mon1pct", "ibs"], "mon_drop": [0.01], "ibs_entry": [0.20],
        "fill_mode": ["next_open"], "exit_mode": ["next_close"],
        "hold_cap": [4], "ma200": [False],
    },
    "Medium (trigger x exit)": {
        "trigger": ["mon1pct", "mon_ibs", "ibs"], "mon_drop": [0.01],
        "ibs_entry": [0.15, 0.20, 0.25], "fill_mode": ["close", "next_open"],
        "exit_mode": ["next_close", "strength", "ibs_exit"],
        "hold_cap": [4], "ma200": [False],
    },
    # The pre-registered triage grid (see scratchpad/ttibs/ttibs_triage_prereg.md):
    # 5 trigger-variants (mon1pct + mon_ibs + ibs x {0.10,0.20,0.30}) x 3 exit_mode x
    # 2 fill_mode x 3 hold_cap x 2 ma200 = 180 configs.
    "Long   (full triage grid)": {
        "trigger": ["mon1pct", "mon_ibs", "ibs"], "mon_drop": [0.01],
        "ibs_entry": [0.10, 0.20, 0.30], "fill_mode": ["close", "next_open"],
        "exit_mode": ["next_close", "strength", "ibs_exit"],
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
    fill_mode: str = "next_open", exit_mode: str = "next_close",
    hold_cap: int = 4, ma200: bool = False,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
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

    # Trailing 200-session SMA, inclusive of today (known at today's own close ->
    # no look-ahead). csum-based so it's O(D), not an O(D*200) rolling-window loop.
    sma200 = np.full(D, np.nan)
    if D >= 200:
        csum = np.cumsum(day_close)
        csum0 = np.concatenate([[0.0], csum])          # csum0[i] = sum of day_close[:i]
        sma200[199:] = (csum0[200:] - csum0[:D - 199]) / 200.0

    seam_days = detect_roll_seams(day_open, day_close, day_ts)
    force_exit_days = {s - 1 for s in seam_days if s - 1 >= 0}
    blocked_fill_days = set(force_exit_days)

    pnl_list, trade_log = [], []
    t = 1                                   # need a prior day for reference closes
    while t < D:
        if _stop_event is not None and _stop_event.is_set():
            break

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

        if fill_mode == "close":
            fill_day = t
            entry_price = day_close[t]
            entry_bar = day_end_bar[t]
        else:  # next_open
            fill_day = t + 1
            if fill_day >= D:
                t += 1; continue
            entry_price = day_open[fill_day]
            entry_bar = day_start_bar[fill_day]

        if fill_day in blocked_fill_days:
            t += 1; continue

        first_check = fill_day if fill_mode == "next_open" else fill_day + 1
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/TTIBS_1_0.py
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
    # tiny window smoke test: 3 years, well within the pre-lockbox span
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))]
    df = df.sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("TTIBS 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)" %
          (len(df), len(set(day_id))))
    print()

    configs = [
        ("ibs<0.20, next_open, next_close, cap4", dict(trigger="ibs", ibs_entry=0.20,
            fill_mode="next_open", exit_mode="next_close", hold_cap=4)),
        ("ibs<0.20, close(lookahead), next_close, cap4", dict(trigger="ibs", ibs_entry=0.20,
            fill_mode="close", exit_mode="next_close", hold_cap=4)),
        ("mon1pct, next_open, strength, cap6", dict(trigger="mon1pct", mon_drop=0.01,
            fill_mode="next_open", exit_mode="strength", hold_cap=6)),
        ("mon_ibs, next_open, ibs_exit, cap4", dict(trigger="mon_ibs",
            fill_mode="next_open", exit_mode="ibs_exit", hold_cap=4)),
        ("ibs<0.20, next_open, next_close, cap4, ma200", dict(trigger="ibs", ibs_entry=0.20,
            fill_mode="next_open", exit_mode="next_close", hold_cap=4, ma200=True)),
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
    seams = detect_roll_seams(
        np.array([df.loc[df.index.date == d, "open"].iloc[0]
                  for d in sorted(set(df.index.date))]),
        np.array([df.loc[df.index.date == d, "close"].iloc[-1]
                  for d in sorted(set(df.index.date))]),
        [pd.Timestamp(d, tz="US/Eastern") for d in sorted(set(df.index.date))],
    )
    print("Roll seams detected in this 3yr window (daily-bar index):", seams)
    print()
    print("Gross-ish net (fee subtracted, mult applied); house engine applies cost_pts")
    print("downstream the same way (see DRIVE_1_0.py / ORB_3_1.py). Sane-output check")
    print("only -- trust real numbers only from the full triage run.")

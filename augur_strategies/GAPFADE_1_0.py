"""
GAPFADE 1.0 — CONDITIONED small-gap fade on NQ (both sides).

Concept: the NAIVE overnight-gap fade (buy any gap-down, target prior close) is publicly
documented as NET NEGATIVE on ES 5m 2011-2021 (buy open on any gap-down>0.15%, target
prior close: 777 trades, negative). The published edge, where it exists, lives only in a
CONDITIONED small-gap fade: a gap-size band (too small = no edge to harvest, too large =
a real breakaway move, not a fade), plus a weakness/strength condition on the prior day,
plus a modest partial-fill target instead of assuming every gap closes 100%.

── Gap definition ──────────────────────────────────────────────────────────────────────
gap_pct = 100 * (today's 09:30 RTH open - prior RTH close) / prior RTH close, computed
from the DAILY-aggregated open/close of the 5m RTH master (open = today's first 5m bar's
open = the real fill price; prior close = yesterday's last 5m bar's close). A negative
gap_pct is a gap DOWN (fade = LONG); positive is a gap UP (fade = SHORT).

── Roll-seam guard (CRITICAL, not cosmetic) ────────────────────────────────────────────
GAPFADE's "gap" IS the close[t-1]->open[t] jump -- the exact quantity the NOADJ
quarterly-roll stitch also corrupts. `detect_roll_seams()` (copied verbatim from
TTIBS_1_0.py's calibrated detector -- house convention is each strategy plugin stays
self-contained, no cross-imports of other strategy files) finds the roll jump by
searching a calendar window around each quarter's 3rd Wednesday for the day whose
|overnight gap| is both >=15 points and >=2.5x the trailing 60-session median |gap| (a
LOCAL outlier check; a global scan mostly re-finds real crashes like Mar-2020/Aug-2015,
which swamp the seam in raw magnitude). ANY day flagged as a seam is skipped entirely --
no signal, no trade -- because trading it would fade a fake several-hundred-point
"gap" that is really just the continuous-contract stitch, not a market event.

── Entry / management ──────────────────────────────────────────────────────────────────
Signal fires when band_min <= |gap_pct| <= band_max (and, if set, the `conditioning`
filter on yesterday's daily bar agrees) and the day is not a detected seam. Entry fills
at the day's first 5m bar's open (the actual 09:30 print -- no slippage assumption
needed, since that IS the gap's own open price). Target/stop are then evaluated bar-by-
bar through the session on the 5m master:
  - `target_mode="full"`      -> target = prior close (the classic full gap-fill).
  - `target_mode="partial_75"`-> target = entry + 0.75 * (entry-to-prior-close distance),
                                  in the fade direction.
  - stop = mirror distance (entry-to-target) x `stop_mult`, opposite side of entry.
  - `time_exit="1300"`  -> scheduled flat-out at the 13:00 ET bar's OPEN if nothing else
    fired yet (a scheduled market exit pre-empts that same bar's own intrabar stop/target
    check -- the order already filled at the open before intrabar movement is assessed).
  - `time_exit="close"` -> hold to the session's last 5m bar.
  - Always flat by the session close regardless of time_exit (single-session trades only
    -- GAPFADE never holds overnight, so the lockbox "exclude if exit is past the seal"
    rule can never trigger: every trade that enters on/before the cutoff also exits
    on/before it, by construction).

Execution conventions mirror ORB_3_1.py exactly: STOP-FIRST pessimism within a bar (if a
bar's range could hit both stop and target, the stop is assumed to have hit first);
gap-through fills at bar OPEN for stops (if a bar opens beyond the stop, fill is that
bar's open, never a better price); targets fill at the exact target price when touched
(no gap-through credit on the favorable side). PNL = EXIT-ENTRY (long) / ENTRY-EXIT
(short), raw points, no cost baked in -- cost_pts applied downstream by the engine
(NQ: 0.533 pts/RT, $20/pt), same convention as every other strategy in this library.

── Conditioning (evaluated on yesterday's daily bar -> no look-ahead) ──────────────────
  - "none"             : band membership only.
  - "yest_ibs_aligned" : yesterday's IBS=(close-low)/(high-low) < 0.25 for gap-down longs
                         (yesterday closed weak, aligned with a bounce thesis) / > 0.75
                         for gap-up shorts (yesterday closed strong).
  - "outside_bar"      : today's open lands outside yesterday's range (below yesterday's
                         low for gap-down longs / above yesterday's high for gap-up
                         shorts) -- a "outside the recent balance" gap, not noise.

`trade_mode` (Both/Long Only/Short Only) is a DIAGNOSTIC knob only -- the pre-registered
triage grid fixes it at "Both" throughout; long-only/short-only splits are reported
alongside the winning plateau, never swept as a separate grid axis.

── Data window / end-of-data handling ───────────────────────────────────────────────────
Requires `day_id` (session grouping) AND `index` (real bar timestamps, for the roll-seam
calendar search and the 13:00 time-exit check) -- same precedent as TTIBS_1_0.py /
REPLAY_1_0.py: returns None if `index` isn't supplied. Every GAPFADE trade opens and
closes within the same RTH session, so there is no "position still open when the loaded
array runs out" case to handle -- the lockbox-honest "exclude, don't truncate" rule is
satisfied automatically by never loading data past the seal date.
"""
import numpy as np
import pandas as pd
from datetime import time as _time

STRATEGY_NAME = 'GAPFADE 1.0 · conditioned small-gap fade (both sides)'
DESCRIPTION = ("Fade a band-sized overnight RTH gap (both directions): long a small "
               "gap-down, short a small gap-up, entered at the 09:30 print, targeting "
               "back toward (or partway toward) prior close. Optional conditioning on "
               "yesterday's IBS / range. Roll-seam guarded -- the gap IS the quantity "
               "the quarterly-roll stitch corrupts. NQ 5m RTH.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# From-scratch gap-fade family, triaged as a challenger -- deliberately no _AUGUR_PARENT.

DEFAULT_PARAMS = {
    "band_min": {
        "default": 0.15, "min": 0.05, "max": 0.30, "step": 0.05, "type": "float",
        "label": "Gap band floor (%)",
        "tooltip": "Minimum |gap| % to trigger a signal. Below this, published research "
                   "says there's no real edge to harvest (too close to noise).",
    },
    "band_max": {
        "default": 0.60, "min": 0.30, "max": 1.00, "step": 0.05, "type": "float",
        "label": "Gap band ceiling (%)",
        "tooltip": "Maximum |gap| % to trigger a signal. Above this, published research "
                   "says the gap is more likely a real breakaway move than fade fodder "
                   "(fill rate drops below 50% past ~0.4%).",
    },
    "conditioning": {
        "default": "yest_ibs_aligned", "type": "str",
        "options": ["none", "yest_ibs_aligned", "outside_bar"],
        "label": "Prior-day condition",
        "tooltip": "none = band membership only. yest_ibs_aligned = yesterday's IBS<0.25 "
                   "(gap-down longs) / >0.75 (gap-up shorts) -- yesterday closed weak/"
                   "strong, aligned with the fade thesis. outside_bar = today's open "
                   "lands outside yesterday's high/low range.",
    },
    "target_mode": {
        "default": "full", "type": "str",
        "options": ["full", "partial_75"],
        "label": "Target",
        "tooltip": "full = prior close (100% gap-fill). partial_75 = 0.75x the "
                   "entry-to-prior-close distance (a partial fill target).",
    },
    "stop_mult": {
        "default": 1.0, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Stop (x target distance)",
        "tooltip": "Stop distance from entry as a multiple of the entry-to-target "
                   "distance, placed on the opposite side of entry from the target. "
                   "1.0 = symmetric risk/reward.",
    },
    "time_exit": {
        "default": "close", "type": "str",
        "options": ["1300", "close"],
        "label": "Time-based exit",
        "tooltip": "1300 = scheduled flat-out at the 13:00 ET bar's open if nothing "
                   "else has fired yet. close = hold to the session's last bar. Always "
                   "flat by session close regardless (single-session trades only).",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Both", "Long Only", "Short Only"],
        "label": "Direction (diagnostic)",
        "tooltip": "Both = trade every in-band gap either direction (the triaged grid "
                   "default). Long/Short Only are diagnostic splits, not swept in the "
                   "pre-registered triage grid.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (core sanity)": {
        "band_min": [0.15], "band_max": [0.60],
        "conditioning": ["none", "yest_ibs_aligned", "outside_bar"],
        "target_mode": ["full"], "stop_mult": [1.0], "time_exit": ["close"],
        "trade_mode": ["Both"],
    },
    "Medium (band x conditioning)": {
        "band_min": [0.10, 0.15, 0.20], "band_max": [0.40, 0.60],
        "conditioning": ["none", "yest_ibs_aligned", "outside_bar"],
        "target_mode": ["full"], "stop_mult": [1.0], "time_exit": ["close"],
        "trade_mode": ["Both"],
    },
    # The pre-registered triage grid (see scratchpad/gapfade/gapfade_triage_prereg.md):
    # 3 band_min x 2 band_max x 3 conditioning x 2 target_mode x 3 stop_mult x
    # 2 time_exit = 216 configs.
    "Long   (full triage grid)": {
        "band_min": [0.10, 0.15, 0.20], "band_max": [0.40, 0.60],
        "conditioning": ["none", "yest_ibs_aligned", "outside_bar"],
        "target_mode": ["full", "partial_75"], "stop_mult": [0.75, 1.0, 1.5],
        "time_exit": ["1300", "close"], "trade_mode": ["Both"],
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
    close[s-1] -> open[s] is a detected quarterly roll seam. Copied verbatim from
    TTIBS_1_0.py (calibrated on the 2010-2025-06-30 NQ window; see that file's docstring
    and scratchpad/ttibs/ttibs_triage_prereg.md for the calibration detail) -- kept as an
    exact copy rather than a cross-import so this plugin stays self-contained per house
    convention (no strategy file imports another strategy file at runtime).
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
    band_min: float = 0.15, band_max: float = 0.60,
    conditioning: str = "yest_ibs_aligned", target_mode: str = "full",
    stop_mult: float = 1.0, time_exit: str = "close", trade_mode: str = "Both",
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
        return None                       # needs real dates (roll seams, 13:00 exit)

    bounds = _session_bounds(did, n)
    D = len(bounds)
    if D < 30:                             # need real headroom for the 60-session
        return None                        # roll-seam baseline + a prior day

    idx = pd.DatetimeIndex(index)
    day_open  = np.array([o[a] for a, b in bounds])
    day_high  = np.array([h[a:b].max() for a, b in bounds])
    day_low   = np.array([l[a:b].min() for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_start_bar = np.array([a for a, b in bounds])
    day_end_bar   = np.array([b - 1 for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]

    rng = day_high - day_low
    ibs = np.where(rng > 1e-9, (day_close - day_low) / np.where(rng > 1e-9, rng, 1.0), 0.5)

    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))

    allow_long  = trade_mode in ("Both", "Long Only")
    allow_short = trade_mode in ("Both", "Short Only")

    n_seam_skips = 0        # signal-eligible (band membership fired) but seam-skipped
    pnl_list, trade_log = [], []

    for t in range(1, D):
        if _stop_event is not None and _stop_event.is_set():
            break

        prior_close = day_close[t - 1]
        if prior_close <= 0:
            continue
        gap_pct = 100.0 * (day_open[t] - prior_close) / prior_close
        abs_gap = abs(gap_pct)
        if abs_gap < band_min or abs_gap > band_max or gap_pct == 0.0:
            continue

        is_seam = t in seam_days
        if is_seam:
            n_seam_skips += 1
            continue                       # CRITICAL: never fade a fake roll-seam gap

        long_side = gap_pct < 0            # gap DOWN -> fade LONG; gap UP -> fade SHORT
        if long_side and not allow_long:
            continue
        if (not long_side) and not allow_short:
            continue

        # ── Conditioning (evaluated on yesterday's daily bar -> no look-ahead) ────────
        if conditioning == "yest_ibs_aligned":
            ok = (ibs[t - 1] < 0.25) if long_side else (ibs[t - 1] > 0.75)
            if not ok:
                continue
        elif conditioning == "outside_bar":
            ok = (day_open[t] < day_low[t - 1]) if long_side else (day_open[t] > day_high[t - 1])
            if not ok:
                continue
        # "none" -> band membership only, no further filter

        entry_bar = int(day_start_bar[t])
        end_bar = int(day_end_bar[t])
        entry_price = float(day_open[t])

        if long_side:
            gap_dist = prior_close - entry_price          # positive
            if target_mode == "full":
                target_price = prior_close
                target_dist = gap_dist
            else:  # partial_75
                target_dist = 0.75 * gap_dist
                target_price = entry_price + target_dist
            stop_dist = target_dist * stop_mult
            stop_price = entry_price - stop_dist
        else:
            gap_dist = entry_price - prior_close           # positive
            if target_mode == "full":
                target_price = prior_close
                target_dist = gap_dist
            else:  # partial_75
                target_dist = 0.75 * gap_dist
                target_price = entry_price - target_dist
            stop_dist = target_dist * stop_mult
            stop_price = entry_price + stop_dist

        if target_dist <= 1e-9:
            continue                       # degenerate (shouldn't happen given band_min>0)

        # scheduled time-based exit bar (first bar of the session with wall-clock >= 13:00)
        time_exit_bar = None
        if time_exit == "1300":
            for k in range(entry_bar, end_bar + 1):
                if idx[k].time() >= _time(13, 0):
                    time_exit_bar = k
                    break

        exit_bar = None; exit_price = None
        worst_adverse = entry_price        # track MAE across the holding window
        for k in range(entry_bar, end_bar + 1):
            if time_exit_bar is not None and k == time_exit_bar and k > entry_bar:
                exit_bar = k; exit_price = float(o[k]); break

            if long_side:
                worst_adverse = min(worst_adverse, float(l[k]))
                if l[k] <= stop_price:                       # stop first (pessimistic)
                    ex_px = o[k] if o[k] < stop_price else stop_price   # gap-through
                    exit_bar = k; exit_price = float(ex_px); break
                if h[k] >= target_price:
                    exit_bar = k; exit_price = float(target_price); break
            else:
                worst_adverse = max(worst_adverse, float(h[k]))
                if h[k] >= stop_price:                        # stop first (pessimistic)
                    ex_px = o[k] if o[k] > stop_price else stop_price   # gap-through
                    exit_bar = k; exit_price = float(ex_px); break
                if l[k] <= target_price:
                    exit_bar = k; exit_price = float(target_price); break

            if k == end_bar:
                exit_bar = k; exit_price = float(c[k]); break   # flat by session close

        if exit_bar is None:
            continue

        pnl = (exit_price - entry_price) if long_side else (entry_price - exit_price)
        mae_pts = (entry_price - worst_adverse) if long_side else (worst_adverse - entry_price)
        mae_pts = max(mae_pts, 0.0)
        side_flag = 1 if long_side else -1

        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(entry_bar), int(exit_bar), float(pnl), side_flag,
                              float(entry_price), float(exit_price), float(mae_pts)))

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
        "n_seam_skips": int(n_seam_skips),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/GAPFADE_1_0.py
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

    print("GAPFADE 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)" %
          (len(df), len(set(day_id))))
    print()

    configs = [
        ("band .15-.60 none full stop1.0 close", dict(
            band_min=0.15, band_max=0.60, conditioning="none", target_mode="full",
            stop_mult=1.0, time_exit="close")),
        ("band .15-.60 yest_ibs full stop1.0 close", dict(
            band_min=0.15, band_max=0.60, conditioning="yest_ibs_aligned",
            target_mode="full", stop_mult=1.0, time_exit="close")),
        ("band .10-.40 outside_bar partial75 stop0.75 1300", dict(
            band_min=0.10, band_max=0.40, conditioning="outside_bar",
            target_mode="partial_75", stop_mult=0.75, time_exit="1300")),
        ("band .15-.60 yest_ibs full stop1.5 close, LONG ONLY", dict(
            band_min=0.15, band_max=0.60, conditioning="yest_ibs_aligned",
            target_mode="full", stop_mult=1.5, time_exit="close", trade_mode="Long Only")),
        ("band .15-.60 yest_ibs full stop1.5 close, SHORT ONLY", dict(
            band_min=0.15, band_max=0.60, conditioning="yest_ibs_aligned",
            target_mode="full", stop_mult=1.5, time_exit="close", trade_mode="Short Only")),
    ]

    print("%-52s %7s %5s %6s %13s %11s %6s" % ("config", "trades", "WR%", "PF", "net $", "maxDD $", "seams"))
    print("-" * 100)
    for label, kw in configs:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index, **kw,
                         return_trades=True)
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        net_pts = r["total_pnl"] - FEE * r["num_trades"]
        net_usd = net_pts * MULT
        dd_usd = r["max_drawdown"] * MULT   # gross DD (cost not folded into curve here)
        print("%-52s %7d %4.0f%% %6.2f %13s %11s %6d" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(dd_usd), r["n_seam_skips"]))

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
    print("downstream the same way (see TTIBS_1_0.py / ORB_3_1.py). Sane-output check")
    print("only -- trust real numbers only from the full triage run.")

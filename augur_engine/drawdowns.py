"""DD5 - THE AVERAGE OF THE FIVE WORST DRAWDOWNS (owner GO 2026-10-07, via MANAGER).

WHY. The house yardstick, ROC %/yr at a $30k worst drawdown (= 30 x MAR = 30 x (net per year) /
worst drawdown, valued daily, WF and LB read apart - augur_engine/book_sizing.stretch_reading),
divides by ONE episode. Book round 62's V2 vol target read 116 against #463's 94 while earning LESS
money, purely because it trimmed the single 2020 crash ($44.8k -> $35.3k); without 2020 its Sortino
was identical. DD5 sits beside every ROC @ $30k figure so a win bought by shaving one crash stands
out. It does not replace the yardstick and changes no ranking.

THE ONE DEFINITION (written once here; the web app's RUNBOARD carries the same one in index.html,
search `_dd5Of`). DD5 = the average depth, in dollars, of the 5 deepest NON-OVERLAPPING drawdown
episodes of the stretch's DAILY equity curve:
  * the curve is the running sum of the daily P&L, starting from a FLAT account (0) before the
    first row - the same peak-from-zero convention as stretch_reading's drawdown;
  * an episode runs from a peak to the trough before equity next regains that peak (equal counts
    as regained, to within 1e-9 dollars of float rounding); a dip that bounces without regaining the peak and then falls further is the SAME
    episode, so episodes never overlap;
  * an episode still open at the stretch end counts, with its depth so far;
  * fewer than 5 episodes -> the average of those found (say "(n=3)" when you print it); a curve
    that never draws down has n = 0 and DD5 = 0.
ONE-EPISODE FLAG: the worst drawdown is more than 1.3 x DD5 -> the ROC @ $30k figure is driven by
one episode. With n = 1 the worst drawdown IS DD5, so the flag cannot fire; print the (n=1).

Value it on the same daily curve and the same stretch (WF / LB) the ROC figure uses, so the worst
episode here equals that figure's worst drawdown to the cent.

    from augur_engine.drawdowns import dd5
    r = dd5(daily)                 # daily: pd.Series of $ per day, indexed by date (zeros included)
    r["dd5_usd"], r["n"], r["max_dd"], r["one_episode"], r["episodes"]

Stdlib only (pandas / numpy inputs are accepted, never required).
"""
import math

ONE_EPISODE_RATIO = 1.3


def _rows(daily_pnl, dates):
    """(values, dates-or-None) from a pd.Series, a sequence of numbers, or a sequence of
    (date, value) pairs."""
    if hasattr(daily_pnl, "index") and hasattr(daily_pnl, "to_numpy"):        # pd.Series
        vals = [float(v) for v in daily_pnl.to_numpy()]
        if dates is None:
            dates = [str(d)[:10] for d in daily_pnl.index]
        return vals, dates
    seq = list(daily_pnl if daily_pnl is not None else [])
    if seq and isinstance(seq[0], (tuple, list)) and len(seq[0]) == 2:
        if dates is not None:
            raise ValueError("dd5: pass dates either inside (date, value) pairs or as dates=, not both")
        return [float(v) for _, v in seq], [str(d)[:10] for d, _ in seq]
    return [float(v) for v in seq], dates


def episodes(daily_pnl, dates=None):
    """Every non-overlapping drawdown episode of the daily curve, in time order.

    Each episode: {"peak", "trough", "recovered", "depth", "open", "peak_i", "trough_i"}.
    peak_i is the row index of the peak (-1 = the flat account before the first row; then
    "peak" is None), trough_i the row of the lowest close inside the episode, "recovered" the
    date equity regained the peak (None while the episode is still open at the end). Dates are
    'YYYY-MM-DD' strings when dates are known, else None. depth is positive dollars."""
    vals, dts = _rows(daily_pnl, dates)
    if dts is not None and len(dts) != len(vals):
        raise ValueError("dd5: %d dates for %d daily values" % (len(dts), len(vals)))
    for i, v in enumerate(vals):
        if not math.isfinite(v):
            raise ValueError("dd5: daily P&L row %d is not a finite number (%r)" % (i, v))

    def day(i):
        return None if (dts is None or i < 0) else str(dts[i])[:10]

    out = []
    cum, peak, pi = 0.0, 0.0, -1
    in_ep, trough, ti = False, 0.0, -1
    for i, v in enumerate(vals):
        cum += v
        if cum >= peak - 1e-9:          # regained (a float-rounding hair under the peak counts)
            if in_ep:
                out.append({"peak": day(pi), "trough": day(ti), "recovered": day(i),
                            "depth": peak - trough, "open": False, "peak_i": pi, "trough_i": ti})
                in_ep = False
            peak, pi = cum, i
        elif not in_ep:
            in_ep, trough, ti = True, cum, i
        elif cum < trough:
            trough, ti = cum, i
    if in_ep:
        out.append({"peak": day(pi), "trough": day(ti), "recovered": None,
                    "depth": peak - trough, "open": True, "peak_i": pi, "trough_i": ti})
    return out


DEFAULT_START_USD = 100_000.0


def dd_pct_peak(daily_pnl, start=DEFAULT_START_USD, dates=None):
    """The worst drawdown as a PERCENTAGE, the way a broker states it (owner ask 2026-10-08).

    max over t of (peak equity up to t - equity at t) / peak equity up to t, where
    equity = `start` + the running sum of the daily P&L. Returned as a percentage (10.0 = 10%).

    WHY THIS REPLACED dd_usd / start. That ratio is a share of the STARTING account, not a
    drawdown: run #424's worst drop of $116.9k read about 117% while its P&L never went below
    zero. No open account can fall 117%.

    WHY IT IS ITS OWN PASS over the curve rather than one division applied to the worst dollar
    drawdown: the deepest drop in dollars and the deepest in percent need not be the same
    episode, because the denominator grows with the account. An early $40k fall from a $200k
    high is 20%; a late $90k fall from a $900k high is 10%. Taking the worst dollar episode and
    dividing by its peak would report 10% and miss the 20%.

    The high-water mark starts AT `start`, before any row - the flat account is its own first
    peak, matching the peak-from-zero convention the dollar figures use. So a curve that never
    makes a new high is measured against `start` throughout.

    Not capped. If equity falls below zero the drop exceeds the high that preceded it and the
    figure passes 100%, which is the honest reading of an account that lost more than it held.

    0.0 for an empty stretch, and for one that never draws down.
    """
    start = float(start)
    if not math.isfinite(start) or start <= 0:
        raise ValueError("dd_pct_peak: start must be a positive number of dollars (%r)" % (start,))
    vals, _dts = _rows(daily_pnl, dates)
    for i, v in enumerate(vals):
        if not math.isfinite(v):
            raise ValueError("dd_pct_peak: daily P&L row %d is not a finite number (%r)" % (i, v))
    equity = start
    peak = start
    worst = 0.0
    for v in vals:
        equity += v
        if equity > peak:
            peak = equity
        # peak >= start > 0 always, so this never divides by zero
        frac = (peak - equity) / peak
        if frac > worst:
            worst = frac
    return round(worst * 100.0, 4)


def dd5(daily_pnl, n=5, dates=None, ratio=ONE_EPISODE_RATIO):
    """DD5 of one stretch's daily P&L (see the module docstring for the definition).

    daily_pnl: pd.Series of $ per day indexed by date, or a sequence of daily $ (optionally with
    dates=[...] of the same length), or a sequence of (date, $) pairs. Rows are taken in the order
    given - pass them sorted by date. Returns
      {"dd5_usd": average depth of the n deepest episodes (0.0 when there are none),
       "n": how many episodes that average covers (< 5 when fewer exist),
       "episodes": those episodes, deepest first ({"peak", "trough", "depth", "open", ...}),
       "max_dd": the deepest episode's depth = the stretch's worst drawdown,
       "one_episode": max_dd > ratio x dd5_usd,
       "episodes_total": every episode the stretch has}.
    Dollar figures are rounded to the cent; the flag is decided on the unrounded figures."""
    if int(n) < 1:
        raise ValueError("dd5: n must be at least 1")
    allep = episodes(daily_pnl, dates)
    top = sorted(allep, key=lambda e: (-e["depth"], e["trough_i"]))[:int(n)]
    avg = (sum(e["depth"] for e in top) / len(top)) if top else 0.0
    worst = top[0]["depth"] if top else 0.0
    return {"dd5_usd": round(avg, 2), "n": len(top),
            "episodes": [dict(e, depth=round(e["depth"], 2)) for e in top],
            "max_dd": round(worst, 2),
            "one_episode": bool(top) and worst > float(ratio) * avg,
            "episodes_total": len(allep)}

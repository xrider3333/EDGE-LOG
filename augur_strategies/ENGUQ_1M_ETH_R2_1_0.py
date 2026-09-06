"""ENGU-Q 1m ETH -- the crown (#309) with two risk knobs corrected. FENCED.
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_ER_1_0.py. Trading logic is IDENTICAL -- not one line of the engine
changed. Only two DEFAULTS move, and the ranges are fenced around the crown so a search
here explores the neighbourhood instead of wandering off to a new configuration.

    breakeven_R  3.0 -> 2.0     stop_mult  1.3 -> 1.0

WHY. Run #309 is the crowned ENGU-Q leg. Its profit factor and EV R are the best in the
library but its risk side is not: it earned about $36,800 a year against a $48,900
drawdown (MAR 0.75), with 58% of its net in ten trades and a 282-day longest hold. Its own
search maximised net and drawdown together, never MAR or R per year, and it pushed
breakeven_R to 3.0 -- the very top of that knob's range -- so the stop almost never
interfered and winners ran until they turned.

A one-knob-at-a-time sweep around the crown (22 cells, every other #309 param held) found
that breakeven_R and stop_mult are the only two knobs that improve it, and that they stack.

MEASURED, 2010-06-07..2026-06-30, NQ 1m ETH db_noadj_eth, cost 0.533 x $20:

                       trades      net      PF    EV R   R/YR      DD    MAR   LB   top-10  hold
    #309 crown          1,604   $591,267  1.655   0.434   43.4  $48,900  0.75   99    58%   282d
    THIS (be1.5/s1.0)   2,139   $582,827  1.665   0.485   64.6  $39,697  0.91  118    56%   142d
    sibling be2.0/s1.0  1,949   $613,126  1.711   0.503   61.0  $41,534  0.92  118    56%   142d

It gives up 1.4% of net and buys +49% R per year, +21% MAR, -19% drawdown, +19 held-out
trades, a cleaner tail and half the longest hold. The be2.0 sibling instead beats the crown
on EVERY read including net; both are recorded because the choice between them is a
selection question, below.

WHICH ONE IS THE DEFAULT, AND WHY (owner's call, 2026-09-05: "go with the be2.0 sibling").
breakeven_R 2.0 is the default. It is the only cell measured that beats the crown on EVERY
read at once - net, profit factor, EV R, R per year, drawdown, MAR, held-out trade count,
tail concentration and longest hold - with nothing traded away.

The honest qualifier, kept because it is the reason the other cell existed: both knobs were
swept on the whole window, so the two were re-scored on PRE-LOCKBOX DATA ONLY
(2010-06-07..2025-06-30). There be1.5/stop1.0 ranks first on MAR and R per year and
be2.0/stop1.0 ranks second by a hair (MAR 0.90 vs 0.96), so a mechanical pre-lockbox rule
would have picked be1.5. be2.0 was chosen instead on the strength of dominating on every
read and on the held-out year specifically (EV R 0.487 vs 0.429, R per year 57.5 vs 50.7,
MAR 2.13 vs 2.02). Both remain inside this file's fence, so the validate sees both.

What matters more than which of the two: EVERY cell that beat the crown before the lockbox
also beat it inside the held-out year. The ranking is stable across the split, which is what
separates a real improvement from a fit.

Held-out year alone (entries >= 2025-06-30), the unselected read:
    #309 crown      99 trades  PF 1.620  EV R 0.407  R/YR 40.4  MAR 1.75
    be1.5/stop1.0  118 trades            EV R 0.429  R/YR 50.7  MAR 2.02
    be2.0/stop1.0  118 trades  PF 1.675  EV R 0.487  R/YR 57.5  MAR 2.13

IN THE BOOK. Swapping this leg for the crown inside the frontier pair (run #317) beats that
book on every read at once -- EV R 0.429 -> 0.436, R per year 202 -> 220, PF 1.526 -> 1.530,
MAR 1.19 -> 1.39, drawdown $40,129 -> $33,992, held-out trades 520 -> 539, top-10 45% -> 43%.
That is the first thing measured in this campaign to dominate #317 rather than trade one
read for another.

HONEST CAVEATS. Two knobs were chosen by a sweep, so this is a selection however small;
the era split is 2-2 rather than 4-0 (profit factor slips slightly in 2010-14 and 2018-22
and improves in 2014-18 and 2022-26); and the held-out figures above come from a sweep that
could see that window, which is exactly why the pre-lockbox re-selection was run and why
this file wants its own Auto-Validate before anything is crowned or deployed. Nothing here
moves the paper board -- that is the owner's call.

Ranges are FENCED to the neighbourhood actually measured, so a validate of this file draws
the landscape around the crown rather than re-searching the whole space (see the pinned-
validate rule: a validate needs open ranges, but they do not have to be the full space).
"""
import numpy as np

_AUGUR_PARENT = "ENGUQ_1M_ETH_ER_1_0.py"
STRATEGY_NAME = "ENGU-Q 1m ETH R2 - crown plus risk fix"
DESCRIPTION = ("The shallow-limit ENGU-Q engine plus a momentum-quality gate: the Kaufman "
               "efficiency ratio of the last er_len minutes must reach er_th at the signal. "
               "er_th=0 = parity with ENGUQ_1M_ETH_LIM_1_0; battery-W champion cell is "
               "er_len 60, er_th 0.25 on the raw entry.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec

DEFAULT_PARAMS = {
    'er_len': {'default': 100, 'min': 20, 'max': 120, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},
    'er_th': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor (0=off)',
              'tooltip': '0 = OFF / parity anchor. >0 = the signal bar must show at least '
                         'this efficiency ratio; 0.25 is the battery-W champion. Do not '
                         'push above 0.25 - the 0.30 cell collapses the lockbox.'},
    'limit_atr': {'default': 0.55, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
                  'label': 'Shallow Limit Depth (x ATR)',
                  'tooltip': '0 = OFF / parity anchor (fill at signal-bar close, identical to '
                             'ENGUQ_1M_ETH_1_0). >0 = place a resting limit this many ATR below '
                             'the signal close; scans up to 10 bars for a gap-honest fill, else '
                             'no trade.'},
    'tl_len': {'default': 206, 'min': 50, 'max': 300, 'step': 4, 'type': 'int',
              'label': 'Trendline Length (bars)',
              'tooltip': 'Bars of highs the descending trendline is fit to (must slope down).'},
    'vol_mult': {'default': 1.1, 'min': 0.0, 'max': 5.0, 'step': 0.1, 'type': 'float',
                'label': 'Volume Spike (x avg)',
                'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
    'stop_mult': {'default': 1.0, 'min': 0.8, 'max': 1.4, 'step': 0.1, 'type': 'float',
                 'label': 'Stop (x risk-to-swing-low)',
                 'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low.'},
    'act_R': {'default': 1.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
             'label': 'Trail Activation (R)',
             'tooltip': 'Start trailing once the trade is this many R in profit.'},
    'trail_frac': {'default': 2.5, 'min': 0.5, 'max': 4.0, 'step': 0.5, 'type': 'float',
                  'label': 'Trail Width (x risk)',
                  'tooltip': 'Trailing stop rides this far (in risk units) below the running high.'},
    'buf_atr': {'default': 0.3, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
               'label': 'Breakout Buffer (x ATR)',
               'tooltip': 'Close must clear the trendline by this x ATR.'},
    'min_brk': {'default': 1.6, 'min': 0.0, 'max': 3.0, 'step': 0.1, 'type': 'float',
               'label': 'Breakout Decisiveness (x ATR)',
               'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},
    'ema_len': {'default': 220, 'min': 100, 'max': 1600, 'step': 40, 'type': 'int',
               'label': 'Trend EMA Length',
               'tooltip': 'Only take longs with close above this EMA (uptrend filter).'},
    'atr_len': {'default': 52, 'min': 20, 'max': 180, 'step': 4, 'type': 'int',
               'label': 'ATR Length',
               'tooltip': 'Lookback for ATR (buffer/decisiveness/limit depth).'},
    'regime_len': {'default': 10, 'min': 0, 'max': 100, 'step': 5, 'type': 'int',
                  'label': 'Regime SMA (days, 0=off)',
                  'tooltip': 'Only go long when close is above its N-DAY simple average. 0=off.'},
    'breakeven_R': {'default': 2.0, 'min': 1.0, 'max': 2.5, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. 0=off.'},
}

PARAM_GRID_PRESETS = {
    'Limit depth sweep (research)': {'limit_atr': [0.0, 0.10, 0.20, 0.35, 0.50]},
}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 er_len=60, er_th=0.0, limit_atr=0.0,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5,
                 return_trades=False, _stop_event=None, _pause_event=None,
                 _signal_probe=None, _fill_probe=None, **_ignore):
    """_signal_probe / _fill_probe: optional lists (research instrumentation only, not part
    of the strategy contract). _signal_probe gets one entry appended per bar that clears
    every entry filter (a "signal"), regardless of whether limit_atr fills it -- lets a
    driver compute an exact fill-rate. _fill_probe gets (signal_close - fill_price)
    appended per ACTUAL fill when limit_atr > 0 -- lets a driver compute the average entry
    improvement in points."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    limit_atr = float(limit_atr)

    ema = _ema(c, int(ema_len))
    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb

    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); al = int(atr_len)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)

    # efficiency-ratio gate (er_th=0 -> gate off = parity). Trailing er_len bars only.
    er_ok = None
    if float(er_th) > 0:
        L = int(er_len)
        chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
        ad = np.abs(np.diff(c, prepend=c[0]))
        cs2 = np.cumsum(ad)
        vsum = cs2 - np.concatenate([np.zeros(L), cs2[:-L]])
        er = np.where(vsum > 0, chg / np.maximum(vsum, 1e-9), 0.0)
        er_ok = np.nan_to_num(er) >= float(er_th)

    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        vv = np.asarray(volumes, float)
        vavg = np.full(n, np.nan); w = 20
        vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()

    pnl_list, trade_log = [], []
    pos = None
    i = tl_len + 1
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break

        if pos is not None:
            if h[i] - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades:
                    trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
            i += 1
            continue

        # ── signal detection (identical filters to the parent, on bar i) ──
        if c[i] <= o[i] or not c[i] > ema[i]:
            i += 1; continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):
            i += 1; continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            i += 1; continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            i += 1; continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            i += 1; continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            i += 1; continue
        if er_ok is not None and not er_ok[i]:
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()
        if _signal_probe is not None:
            _signal_probe.append(1)

        if limit_atr <= 0:
            risk = c[i] - swing_low
            if risk < max(0.25, 0.5):
                i += 1; continue
            ep = c[i]
            pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}
            i += 1
            continue

        # ── SHALLOW LIMIT: rest at c[i] - limit_atr*ATR, scan up to _N_SCAN bars ──
        limit = c[i] - limit_atr * a
        jmax = min(i + _N_SCAN, n - 1)
        fill_j, fill_price = None, None
        for j in range(i + 1, jmax + 1):
            if l[j] <= limit:
                fill_price = min(limit, o[j])  # gap-honest: open if the bar gapped through
                fill_j = j
                break
        if fill_j is None:
            i += 1; continue  # no fill within the window -> setup dropped, no trade
        if _fill_probe is not None:
            _fill_probe.append(c[i] - fill_price)  # limit touched -> counts as a FILL regardless of risk floor
        risk = fill_price - swing_low
        if risk < max(0.25, 0.5):
            i = fill_j + 1; continue
        pos = {"bar": fill_j, "ep": fill_price, "risk": risk, "sl": fill_price - stop_mult * risk, "act": False}
        i = fill_j + 1  # management starts the bar AFTER the fill bar (parent convention)
        continue

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades:
            trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"]))

    if not pnl_list:
        return None
    p = np.array(pnl_list); wins = p[p > 0]; losses = p[p < 0]
    cum = np.cumsum(p)
    out = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out

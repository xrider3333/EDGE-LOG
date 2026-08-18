"""
ENGU-Q 1m RC · trendline break (long) — RISK-CAPPED
----------------------------------------------------
Fork of ENGUQ_1M_1_0.py that adds ONE new param, `risk_cap_atr`, to fix the
runaway-hold defect diagnosed 2026-08-17: initial risk is (entry_px - swing_low)
over tl_len bars, uncapped. On extreme days that distance explodes (run #223's
champion: 2025-04-07 entry, swing low 1,251.6 pts away -> trail sat 5,006 pts
below the running high -> mathematically unreachable -> 465-day hold blocking
all further entries in the final year of the sample). Same signature in #198
and #232 (353-day hold = 25% of its profit).

risk_cap_atr (float, default 0.0 = OFF): when > 0, initial risk is capped at
risk_cap_atr * ATR(atr_len) measured AT THE ENTRY BAR (uses only prior/current-bar
data already computed by the engine below -- no look-ahead). The cap applies to
the risk AFTER stop_mult, i.e.:

    raw_dist   = entry_px - swing_low                     (unchanged from parent)
    stop_dist  = raw_dist * stop_mult                      (parent's actual stop distance)
    capped     = min(stop_dist, risk_cap_atr * ATR[entry]) (only when risk_cap_atr > 0)

The stop price is entry_px - capped. Downstream R-multiples (breakeven_R, act_R,
trail_frac) all key off the SAME capped value, so once a trade's initial risk is
capped, its whole exit ladder (breakeven / trail activation / trail width) shrinks
in proportion -- no separate uncapped R survives anywhere in the trade.

PARITY: when risk_cap_atr == 0.0 (default), this file takes the untouched parent
code path -- pos["risk"] stays the parent's raw (entry_px - swing_low), stop is
entry_px - stop_mult*risk exactly as in ENGUQ_1M_1_0.py, so results are bit-identical
to the parent on any config. risk_cap_atr=0.0 is the certified parity anchor.

All other params are left fully searchable (not pinned) so this file works with
Auto-Validate like any other strategy.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m RC · trendline break, risk-capped (long)"
DESCRIPTION = ("Fork of ENGU-Q 1m adding a risk_cap_atr knob: caps initial stop "
               "distance at N x ATR(atr_len) measured at entry, so extreme swing-low "
               "days can no longer produce an unreachable trail and a runaway multi-"
               "hundred-day hold. risk_cap_atr=0 (default) = OFF, bit-identical to the "
               "uncapped parent (ENGUQ_1M_1_0).")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

DEFAULT_PARAMS = {'tl_len': {'default': 34,
          'min': 15,
          'max': 80,
          'step': 1,
          'type': 'int',
          'label': 'Trendline Length (bars)',
          'tooltip': 'Bars of highs the descending trendline is fit to (must slope down). 1m: try ~30-70 '
                     '(tl_len 34 validated).'},
'vol_mult': {'default': 1.2,
            'min': 0.0,
            'max': 5.0,
            'step': 0.1,
            'type': 'float',
            'label': 'Volume Spike (x avg)',
            'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
'stop_mult': {'default': 1.7,
             'min': 0.3,
             'max': 2.0,
             'step': 0.1,
             'type': 'float',
             'label': 'Stop (x risk-to-swing-low)',
             'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low, BEFORE the risk_cap_atr cap '
                        'is applied.'},
'act_R': {'default': 1.0,
         'min': 0.0,
         'max': 3.0,
         'step': 0.5,
         'type': 'float',
         'label': 'Trail Activation (R)',
         'tooltip': 'Start trailing once the trade is this many R (of the CAPPED risk, when the cap is on) in '
                    'profit.'},
'trail_frac': {'default': 2.5,
              'min': 0.5,
              'max': 4.0,
              'step': 0.5,
              'type': 'float',
              'label': 'Trail Width (x risk)',
              'tooltip': 'Trailing stop rides this far (in risk units, CAPPED when the cap is on) below the '
                         'running high.'},
'buf_atr': {'default': 0.35,
           'min': 0.0,
           'max': 1.0,
           'step': 0.05,
           'type': 'float',
           'label': 'Breakout Buffer (x ATR)',
           'tooltip': 'Close must clear the trendline by this x ATR.'},
'min_brk': {'default': 0.7,
           'min': 0.0,
           'max': 3.0,
           'step': 0.1,
           'type': 'float',
           'label': 'Breakout Decisiveness (x ATR)',
           'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},
'ema_len': {'default': 30,
           'min': 20,
           'max': 400,
           'step': 10,
           'type': 'int',
           'label': 'Trend EMA Length',
           'tooltip': 'Only take longs with close above this EMA (uptrend filter).'},
'atr_len': {'default': 47,
           'min': 5,
           'max': 50,
           'step': 1,
           'type': 'int',
           'label': 'ATR Length',
           'tooltip': 'Lookback for ATR (buffer/decisiveness/risk cap).'},
'regime_len': {'default': 0,
              'min': 0,
              'max': 100,
              'step': 5,
              'type': 'int',
              'label': 'Regime SMA (days, 0=off)',
              'tooltip': 'Only go long when close is above its N-DAY simple average — a longer-term trend gate on '
                         'top of the EMA. 0=off. Long (~20-50d) skips bears/chop and cuts drawdown; short whipsaws. '
                         '(390 RTH bars/day.)'},
'breakeven_R': {'default': 0.0,
               'min': 0.0,
               'max': 3.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Breakeven (R, 0=off)',
               'tooltip': 'Once the trade is this many R (of the CAPPED risk, when the cap is on) in profit (high '
                          'vs entry), raise the stop to entry so it can never go negative. 0=off.'},
'risk_cap_atr': {'default': 0.0,
               'min': 0.0,
               'max': 8.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Risk Cap (x ATR, 0=off)',
               'tooltip': 'Caps the initial stop distance (entry-to-swing-low x stop_mult) at this many x ATR('
                          'atr_len), measured at the entry bar. Fixes runaway holds on extreme-swing-low days '
                          '(diagnosed 2026-08-17: an uncapped 1,251.6-pt swing low produced an unreachable trail '
                          'and a 465-day hold). 0=off, bit-identical to the uncapped parent. All downstream R-based '
                          'levels (breakeven/act/trail) key off the same capped risk once this is > 0.'}}

PARAM_GRID_PRESETS = {'Robust (high-frequency)': {'tl_len': [25, 34, 45, 60],
                           'vol_mult': [1.1, 1.2, 1.3],
                           'stop_mult': [1.0, 1.5, 1.7],
                           'act_R': [1.0, 1.5],
                           'trail_frac': [2.0, 2.5],
                           'buf_atr': [0.2, 0.35],
                           'min_brk': [0.3, 0.7],
                           'ema_len': [30, 100, 200],
                           'atr_len': [14, 47],
                           'regime_len': [0, 20, 50],
                           'breakeven_R': [0.0, 1.0, 1.5, 2.0],
                           'risk_cap_atr': [0.0, 2.0, 3.0, 4.0]},
'Wide': {'tl_len': [20, 34, 50, 70],
        'vol_mult': [1.0, 1.2, 1.5],
        'stop_mult': [1.0, 1.5],
        'act_R': [1.0, 1.5],
        'trail_frac': [1.5, 2.5, 3.0],
        'buf_atr': [0.1, 0.35],
        'min_brk': [0.0, 0.7],
        'ema_len': [30, 200],
        'atr_len': [14, 47],
        'regime_len': [0, 30, 50, 75],
        'breakeven_R': [0.0, 1.5, 3.0],
        'risk_cap_atr': [0.0, 1.5, 2.0, 3.0, 4.0, 6.0]}}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, risk_cap_atr=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    ema = _ema(c, int(ema_len))
    # optional longer-term REGIME gate: close must be above its N-day simple average
    #   (390 RTH bars/day). 0 = off. Long lengths skip bears/chop; short lengths whipsaw.
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
    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        vv = np.asarray(volumes, float)
        vavg = np.full(n, np.nan); w = 20
        vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    cap_on = risk_cap_atr is not None and float(risk_cap_atr) > 0

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl_list, trade_log = [], []
    pos = None
    for i in range(tl_len + 1, n):
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
                # gap-through realism: if the bar OPENED beyond the stop, the fill is the
                # open (can't be filled at a stop price the market never traded through
                # cleanly) — not the exact stop price. ORB 3.0 models the same.
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
            continue
        if c[i] <= o[i] or not c[i] > ema[i]:
            continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):   # regime gate
            continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            continue
        swing_low = l[i - tl_len:i + 1].min()
        raw_risk = c[i] - swing_low
        if raw_risk < max(0.25, 0.5):
            continue
        ep = c[i]
        if cap_on:
            # Cap applies to the actual initial stop distance (raw_risk * stop_mult),
            # using ATR *at the entry bar* (already-known, no look-ahead: `a` above is
            # computed from bars strictly before/at i via the trailing-window ATR).
            # The capped value then drives EVERYTHING downstream (stop + act_R +
            # trail_frac + breakeven_R) so no uncapped R survives anywhere in the trade.
            risk = min(stop_mult * raw_risk, float(risk_cap_atr) * a)
            sl0 = ep - risk
        else:
            # PARITY PATH: bit-identical to the uncapped parent ENGUQ_1M_1_0.py.
            risk = raw_risk
            sl0 = ep - stop_mult * risk
        pos = {"bar": i, "ep": ep, "risk": risk, "sl": sl0, "act": False}

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"]))
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

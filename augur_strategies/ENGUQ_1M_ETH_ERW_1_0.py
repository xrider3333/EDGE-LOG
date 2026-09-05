"""
ENGU-Q 1m ETH - EFFICIENCY FLOOR x WIDE EXITS (research, forked 2026-09-04)
--------------------------------------------------------------------------------
Fork of ENGUQ_1M_ETH_ER_1_0.py. Stacks two independently-found edges to test whether
they compound or overlap:
  (1) the efficiency floor (run #265: er_len 60, er_th 0.25 on the #226 config ->
      PF 1.33 -> 1.60, n 2843 -> 1336, held-out 67 trades, PF 2.645).
  (2) the wider "let it run" exit structure the limit full-discovery run #310 found
      (trail_frac 4.0, act_R 3.0, stop_mult 1.7, limit_atr 0.7, regime_len 5 -> PF 2.22,
      but only 538 trades and a weak lockbox: PF 1.24 on 91 held-out trades).

DEFAULTS below are exactly run #265 (er_th=0.25, all exit knobs at the ER file's
defaults, limit_atr=0.0) -- a pinned/default run of THIS file must reproduce #265's
certified numbers bit-for-bit: n=1336, net $486,413.24, PF 1.597, held-out (entries
>= 2025-06-30) n=67, $146,230.78. Setting er_th=0.0 must reproduce the #226 engine
parity: n=2843, net $434,721.12.

Only the RANGES on the exit knobs (trail_frac, act_R, stop_mult, breakeven_R,
limit_atr) are widened here, to cover the #310 cell (trail_frac 4.0, act_R 3.0,
stop_mult 1.7, limit_atr 0.7) alongside the #265 base. er_th's range is narrowed to
[0.10, 0.35] with a floor of 0.10 (never 0.0) so a search over this file cannot
switch the efficiency gate off -- run #309's unconstrained search over the ER file
crowned er_th 0.0, defeating the entire point of the floor. Nothing in the trading
logic itself changes from the parent; this is a DEFAULT_PARAMS-only fork.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH · EFFICIENCY FLOOR x WIDE EXITS (research)"
DESCRIPTION = ("ENGU-Q ETH efficiency-gated engine (er_th default 0.25, #265) with the "
               "exit knobs (trail_frac/act_R/stop_mult/breakeven_R/limit_atr) widened to "
               "cover the #310 limit full-discovery cell (trail 4.0 / act 3.0 / stop 1.7 / "
               "limit 0.7), and er_th's search range narrowed to [0.10, 0.35] so a search "
               "cannot switch the efficiency floor off. Defaults = #265 exactly.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"
_AUGUR_PARENT = "ENGUQ_1M_ETH_ER_1_0.py"

_N_SCAN = 10  # fixed per battery-O spec

DEFAULT_PARAMS = {
    'er_len': {'default': 60, 'min': 30, 'max': 120, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},
    'er_th': {'default': 0.25, 'min': 0.10, 'max': 0.35, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor',
              'tooltip': 'Signal bar must show at least this efficiency ratio. 0.25 is the '
                         '#265 champion. Floor kept at >=0.10 on purpose - a search over this '
                         'file must not be able to switch the efficiency gate off.'},
    'limit_atr': {'default': 0.0, 'min': 0.0, 'max': 0.8, 'step': 0.05, 'type': 'float',
                  'label': 'Shallow Limit Depth (x ATR)',
                  'tooltip': '0 = OFF / parity anchor (fill at signal-bar close). >0 = place a '
                             'resting limit this many ATR below the signal close; scans up to '
                             '10 bars for a gap-honest fill, else no trade. Widened to 0.8 to '
                             'cover the #310 cell (0.7).'},
    'tl_len': {'default': 170, 'min': 50, 'max': 300, 'step': 4, 'type': 'int',
              'label': 'Trendline Length (bars)',
              'tooltip': 'Bars of highs the descending trendline is fit to (must slope down).'},
    'vol_mult': {'default': 0.8, 'min': 0.0, 'max': 5.0, 'step': 0.1, 'type': 'float',
                'label': 'Volume Spike (x avg)',
                'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
    'stop_mult': {'default': 1.0, 'min': 0.7, 'max': 2.0, 'step': 0.1, 'type': 'float',
                 'label': 'Stop (x risk-to-swing-low)',
                 'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low. Widened '
                            'to cover the #310 cell (1.7).'},
    'act_R': {'default': 2.5, 'min': 1.0, 'max': 4.0, 'step': 0.5, 'type': 'float',
             'label': 'Trail Activation (R)',
             'tooltip': 'Start trailing once the trade is this many R in profit. Widened to '
                        'cover the #310 cell (3.0) - later activation lets winners run further '
                        'before the trail engages.'},
    'trail_frac': {'default': 2.5, 'min': 1.5, 'max': 6.0, 'step': 0.5, 'type': 'float',
                  'label': 'Trail Width (x risk)',
                  'tooltip': 'Trailing stop rides this far (in risk units) below the running '
                             'high. Widened to cover the #310 cell (4.0) - a wider trail gives '
                             'winners more room, i.e. "let it run".'},
    'buf_atr': {'default': 0.9, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
               'label': 'Breakout Buffer (x ATR)',
               'tooltip': 'Close must clear the trendline by this x ATR.'},
    'min_brk': {'default': 1.3, 'min': 0.0, 'max': 3.0, 'step': 0.1, 'type': 'float',
               'label': 'Breakout Decisiveness (x ATR)',
               'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},
    'ema_len': {'default': 1380, 'min': 100, 'max': 1600, 'step': 40, 'type': 'int',
               'label': 'Trend EMA Length',
               'tooltip': 'Only take longs with close above this EMA (uptrend filter).'},
    'atr_len': {'default': 106, 'min': 20, 'max': 180, 'step': 4, 'type': 'int',
               'label': 'ATR Length',
               'tooltip': 'Lookback for ATR (buffer/decisiveness/limit depth).'},
    'regime_len': {'default': 0, 'min': 0, 'max': 100, 'step': 5, 'type': 'int',
                  'label': 'Regime SMA (days, 0=off)',
                  'tooltip': 'Only go long when close is above its N-DAY simple average. 0=off.'},
    'breakeven_R': {'default': 1.5, 'min': 1.0, 'max': 4.0, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. '
                              'Widened upper bound to 4.0 to pair with the wider trail knobs.'},
}

PARAM_GRID_PRESETS = {
    'ENGUQ ETH efficiency floor x wide exits (ERW) full discovery': {
        'trail_frac': [1.5, 2.5, 4.0, 5.0, 6.0],
        'act_R': [1.0, 2.5, 3.0, 4.0],
        'stop_mult': [0.7, 1.0, 1.7, 2.0],
        'limit_atr': [0.0, 0.35, 0.7],
        'er_th': [0.10, 0.20, 0.25, 0.35],
    },
}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 er_len=60, er_th=0.25, limit_atr=0.0,
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

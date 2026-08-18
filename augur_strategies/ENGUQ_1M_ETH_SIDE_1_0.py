"""
ENGU-Q 1m ETH - BOTH SIDES (research): the short mirror that was never tested
------------------------------------------------------------------------------
Every ENGU-Q variant ever run in this project is LONG ONLY (DIRECTION = "LONG" in all of
them). The setup is a descending trendline fit to HIGHS that price breaks UPWARD while
above its EMA. Nothing about that logic is inherently one-sided: the exact mirror is an
ASCENDING trendline fit to LOWS that price breaks DOWNWARD while below its EMA. It has
simply never been built, so this file builds it.

New param `side`:
  'long'  -> PARITY ANCHOR. Bit-identical to ENGUQ_1M_ETH_1_0.py (the certified #226
             engine). Required to reproduce n=2843 / $434,721.12 / PF 1.332 exactly.
  'short' -> the mirror only.
  'both'  -> long and short share ONE position slot (no hedging, no stacking): whichever
             signal fires first while flat takes the slot, exactly as a single account
             would behave.

The mirror, rule by rule (each line is the exact reflection of the parent):
  signal candle   parent: close > open (up bar)       mirror: close < open (down bar)
  trend filter    parent: close > EMA                 mirror: close < EMA
  trendline       parent: fit HIGHS, slope < 0        mirror: fit LOWS, slope > 0
  break           parent: close > TL + buf*ATR        mirror: close < TL - buf*ATR
                          and close > prior high              and close < prior low
  decisiveness    parent: (close-TL)/ATR >= min_brk   mirror: (TL-close)/ATR >= min_brk
  risk anchor     parent: swing LOW over window       mirror: swing HIGH over window
  initial stop    parent: entry - mult*risk           mirror: entry + mult*risk
  trail           parent: ratchet UP off running high mirror: ratchet DOWN off running low
  stop hit        parent: low <= stop                 mirror: high >= stop
  gap realism     parent: fill = open if open < stop  mirror: fill = open if open > stop

`limit_atr` carries over from the adopted shallow-limit find and mirrors too: long places
a resting BUY limit `limit_atr x ATR` BELOW the signal close; short places a resting SELL
limit the same distance ABOVE it. Both scan 10 bars, fill gap-honestly at the worse of
limit/open, and drop the signal entirely if it never fills. limit_atr=0 disables it.

The regime gate is deliberately NOT mirrored and stays long-only-shaped; it is off by
default in every certified config (regime_len=0) and mirroring an unused, admittedly
mis-scaled gate would add an untested surface for no benefit. It raises NotImplementedError
if switched on with shorts enabled rather than silently doing the wrong thing.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH - BOTH SIDES (research)"
DESCRIPTION = ("Adds the never-tested SHORT mirror of the ENGU-Q trendline break (ascending "
               "trendline fit to lows, broken downward below the EMA) to the certified 24h "
               "ETH engine. side='long' is the bit-exact parity anchor; 'both' shares one "
               "position slot between the two directions.")
VERSION = "1.0"
DIRECTION = "BOTH"
TIMEFRAME = "1m"

_N_SCAN = 10   # limit-order scan window, same fixed value as ENGUQ_1M_ETH_LIM_1_0

DEFAULT_PARAMS = {
    'side': {'default': 'long', 'type': 'str', 'options': ['long', 'short', 'both'],
             'label': 'Side',
             'tooltip': ("long = parity anchor (identical to the certified engine). "
                         "short = mirror only. both = one shared position slot.")},
    'limit_atr': {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
                  'label': 'Shallow Limit Depth (x ATR)',
                  'tooltip': ('0 = fill at the signal bar close. >0 = resting limit this many '
                              'ATR better than the close (below for longs, above for shorts).')},
    'tl_len': {'default': 170, 'min': 50, 'max': 300, 'step': 4, 'type': 'int',
               'label': 'Trendline Length (bars)'},
    'vol_mult': {'default': 0.8, 'min': 0.0, 'max': 5.0, 'step': 0.1, 'type': 'float',
                 'label': 'Volume Spike (x avg)'},
    'stop_mult': {'default': 1.0, 'min': 0.3, 'max': 2.0, 'step': 0.1, 'type': 'float',
                  'label': 'Stop (x risk-to-swing)'},
    'act_R': {'default': 2.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
              'label': 'Trail Activation (R)'},
    'trail_frac': {'default': 2.5, 'min': 0.5, 'max': 4.0, 'step': 0.5, 'type': 'float',
                   'label': 'Trail Width (x risk)'},
    'buf_atr': {'default': 0.9, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
                'label': 'Breakout Buffer (x ATR)'},
    'min_brk': {'default': 1.3, 'min': 0.0, 'max': 3.0, 'step': 0.1, 'type': 'float',
                'label': 'Breakout Decisiveness (x ATR)'},
    'ema_len': {'default': 1380, 'min': 100, 'max': 1600, 'step': 40, 'type': 'int',
                'label': 'Trend EMA Length'},
    'atr_len': {'default': 106, 'min': 4, 'max': 300, 'step': 4, 'type': 'int',
                'label': 'ATR Length'},
    'regime_len': {'default': 0, 'min': 0, 'max': 100, 'step': 5, 'type': 'int',
                   'label': 'Regime SMA (days, 0=off) - LONG ONLY'},
    'breakeven_R': {'default': 1.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
                    'label': 'Breakeven (R, 0=off)'},
}

PARAM_GRID_PRESETS = {
    "Short mirror at the certified config": {
        'side': ['short'], 'limit_atr': [0.0, 0.5], 'tl_len': [170], 'vol_mult': [0.8],
        'stop_mult': [1.0], 'act_R': [2.5], 'trail_frac': [2.5], 'buf_atr': [0.9],
        'min_brk': [1.3], 'ema_len': [1380], 'atr_len': [106], 'regime_len': [0],
        'breakeven_R': [1.5],
    },
}


def _ema(a, n):
    k = 2.0 / (n + 1.0)
    out = np.empty_like(a)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 side='long', limit_atr=0.0,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float)
    h = np.asarray(highs, float)
    l = np.asarray(lows, float)
    c = np.asarray(closes, float)
    n = len(c)
    tl_len = int(tl_len)
    if n < tl_len + 5:
        return None

    side = str(side).lower()
    do_long = side in ('long', 'both')
    do_short = side in ('short', 'both')
    if int(regime_len) > 0 and do_short:
        raise NotImplementedError(
            "regime_len is a long-only gate and is not mirrored; set regime_len=0 for shorts.")

    ema = _ema(c, int(ema_len))

    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb

    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan)
    al = int(atr_len)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)

    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        vv = np.asarray(volumes, float)
        vavg = np.full(n, np.nan)
        w = 20
        vc = np.cumsum(vv)
        vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    x = np.arange(tl_len)
    xm = x.mean()
    xd = x - xm
    xss = (xd ** 2).sum()

    pnl_list, trade_log = [], []
    pos = None
    fills = {'long_sig': 0, 'short_sig': 0, 'long_fill': 0, 'short_fill': 0}

    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break

        # manage an open position
        if pos is not None:
            if pos["dir"] == 1:
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
            else:
                if pos["ep"] - l[i] >= act_R * pos["risk"]:
                    pos["act"] = True
                if pos["act"]:
                    pos["sl"] = min(pos["sl"], l[i] + trail_frac * pos["risk"])
                if breakeven_R > 0 and (pos["ep"] - l[i]) >= breakeven_R * pos["risk"]:
                    pos["sl"] = min(pos["sl"], pos["ep"])
                if h[i] >= pos["sl"]:
                    fill = o[i] if o[i] > pos["sl"] else pos["sl"]
                    pnl = pos["ep"] - fill
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((pos["bar"], i, pnl, -1, pos["ep"]))
                    pos = None
            continue

        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        vol_ok = (vol_mult <= 0) or (
            have_vol and not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i])

        # LONG signal (parent logic, untouched)
        if do_long and c[i] > o[i] and c[i] > ema[i] and vol_ok:
            ok = True
            if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):
                ok = False
            if ok:
                hw = h[i - tl_len:i]
                slope = (xd * (hw - hw.mean())).sum() / xss
                if slope < 0:
                    tl_now = hw.mean() + slope * (tl_len - xm)
                    if (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]
                            and (c[i] - tl_now) / max(a, 0.25) >= min_brk):
                        swing_low = l[i - tl_len:i + 1].min()
                        risk = c[i] - swing_low
                        if risk >= 0.5:
                            fills['long_sig'] += 1
                            ep, bar = c[i], i
                            if limit_atr > 0:
                                lvl = c[i] - limit_atr * a
                                ep = None
                                for j in range(i + 1, min(i + 1 + _N_SCAN, n)):
                                    if l[j] <= lvl:
                                        ep = min(lvl, o[j])
                                        bar = j
                                        break
                            if ep is not None:
                                risk = ep - swing_low
                                if risk >= 0.5:
                                    fills['long_fill'] += 1
                                    pos = {"bar": bar, "ep": ep, "risk": risk, "dir": 1,
                                           "sl": ep - stop_mult * risk, "act": False}
                                    continue

        # SHORT signal (the mirror)
        if do_short and pos is None and c[i] < o[i] and c[i] < ema[i] and vol_ok:
            lw = l[i - tl_len:i]
            slope = (xd * (lw - lw.mean())).sum() / xss
            if slope > 0:
                tl_now = lw.mean() + slope * (tl_len - xm)
                if (c[i] < tl_now - buf_atr * a and c[i] < l[i - 1]
                        and (tl_now - c[i]) / max(a, 0.25) >= min_brk):
                    swing_high = h[i - tl_len:i + 1].max()
                    risk = swing_high - c[i]
                    if risk >= 0.5:
                        fills['short_sig'] += 1
                        ep, bar = c[i], i
                        if limit_atr > 0:
                            lvl = c[i] + limit_atr * a
                            ep = None
                            for j in range(i + 1, min(i + 1 + _N_SCAN, n)):
                                if h[j] >= lvl:
                                    ep = max(lvl, o[j])
                                    bar = j
                                    break
                        if ep is not None:
                            risk = swing_high - ep
                            if risk >= 0.5:
                                fills['short_fill'] += 1
                                pos = {"bar": bar, "ep": ep, "risk": risk, "dir": -1,
                                       "sl": ep + stop_mult * risk, "act": False}

    if pos is not None:
        pnl = (c[-1] - pos["ep"]) if pos["dir"] == 1 else (pos["ep"] - c[-1])
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((pos["bar"], n - 1, pnl, pos["dir"], pos["ep"]))

    if not pnl_list:
        return None
    p = np.array(pnl_list)
    wins = p[p > 0]
    losses = p[p < 0]
    cum = np.cumsum(p)
    out = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
        "_fills":        fills,
    }
    if return_trades:
        out["trades"] = trade_log
    return out

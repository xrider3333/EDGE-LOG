"""
ENGU-Q 5m · NEXT-BAR-OPEN entry-realism variant (research, battery K)
----------------------------------------------------------------------
Same signal engine as ENGUQ_5M_1_0.py (descending-trendline break, long only,
day-session defaults), with ONE free knob: entry_mode. Mirrors the mechanics of
augur_strategies/ENGUQ_1M_RT_1_0.py's entry_mode=1 exactly, ported to the 5m
engine (which has no regime_len knob, unlike the 1m file).

  entry_mode = 0  PARENT      — fill at the signal bar's own close (parity anchor,
                                 identical to ENGUQ_5M_1_0.py's behaviour).
  entry_mode = 1  NEXT-OPEN   — fill at the OPEN of the bar after the signal.
                                 risk/stop are still derived from the signal bar's
                                 close and swing-low (same convention as the 1m
                                 RT file); management starts the bar AFTER the
                                 fill bar.

No look-ahead: nothing after the fill bar is used to decide whether/where to fill.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 5m · next-bar-open (research)"
DESCRIPTION = ("Research variant of ENGU-Q 5m: entry_mode switches between parent "
              "same-bar-close fill and next-bar-open fill. All other params match "
              "ENGUQ_5M_1_0.py's DEFAULT_PARAMS.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "5m"

DEFAULT_PARAMS = {
    'entry_mode': {'default': 0, 'min': 0, 'max': 1, 'step': 1, 'type': 'int',
                   'label': 'Entry Mode',
                   'tooltip': '0=parent (signal-bar close, parity anchor). '
                              '1=next-bar-open (paper-safest fill).'},
    'tl_len': {'default': 25, 'min': 10, 'max': 60, 'step': 1, 'type': 'int',
              'label': 'Trendline Length (bars)'},
    'vol_mult': {'default': 1.3, 'min': 0.0, 'max': 5.0, 'step': 0.1, 'type': 'float',
                'label': 'Volume Spike (x avg)'},
    'stop_mult': {'default': 1.0, 'min': 0.3, 'max': 2.0, 'step': 0.1, 'type': 'float',
                 'label': 'Stop (x risk-to-swing-low)'},
    'act_R': {'default': 1.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
             'label': 'Trail Activation (R)'},
    'trail_frac': {'default': 1.5, 'min': 0.5, 'max': 4.0, 'step': 0.5, 'type': 'float',
                  'label': 'Trail Width (x risk)'},
    'buf_atr': {'default': 0.1, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
               'label': 'Breakout Buffer (x ATR)'},
    'min_brk': {'default': 0.0, 'min': 0.0, 'max': 3.0, 'step': 0.1, 'type': 'float',
               'label': 'Breakout Decisiveness (x ATR)'},
    'ema_len': {'default': 200, 'min': 20, 'max': 400, 'step': 10, 'type': 'int',
               'label': 'Trend EMA Length'},
    'atr_len': {'default': 14, 'min': 5, 'max': 50, 'step': 1, 'type': 'int',
               'label': 'ATR Length'},
    'breakeven_R': {'default': 0.0, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)'},
}

PARAM_GRID_PRESETS = {
    'Entry modes (research)': {'entry_mode': [0, 1]},
}

_RISK_FLOOR = 0.5  # matches parent's max(0.25, 0.5)


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 entry_mode=0,
                 tl_len=25, vol_mult=1.3, stop_mult=1.0, act_R=1.5, trail_frac=1.5,
                 buf_atr=0.1, min_brk=0.0, ema_len=200, atr_len=14,
                 breakeven_R=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None,
                 _signal_probe=None, _fill_probe=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    entry_mode = int(entry_mode)

    ema = _ema(c, int(ema_len))
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
        swing_low = l[i - tl_len:i + 1].min()
        if _signal_probe is not None:
            _signal_probe.append(1)

        if entry_mode == 0:
            risk = c[i] - swing_low
            if risk < _RISK_FLOOR:
                i += 1; continue
            ep = c[i]
            pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}
            i += 1
            continue

        # entry_mode == 1: NEXT-OPEN
        if i + 1 >= n:
            i += 1; continue  # no next bar to fill on -> no trade
        risk = c[i] - swing_low
        if risk < _RISK_FLOOR:
            i += 1; continue
        ep = o[i + 1]
        pos = {"bar": i + 1, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}
        i += 2  # management starts the bar AFTER the fill bar (parent convention)
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

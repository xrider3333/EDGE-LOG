"""ENGU-Q 1m · RETEST-ENTRY / NEXT-BAR-OPEN entry-realism variant (research, battery C)
---------------------------------------------------------------------------------------
Same signal engine as ENGUQ_1M_1_0.py (descending-trendline break, long only), with the
SAME #149 deploy config pinned single-valued on all 11 parent params. The only free knob
is `entry_mode`, which changes WHERE the fill happens relative to the signal bar. Every
mode is leak-free by construction: nothing after the fill bar is used to decide whether
or where to fill.

  entry_mode = 0  PARENT      — fill at the signal bar's own close (parity anchor,
                                 identical to ENGUQ_1M_1_0.py's behaviour).
  entry_mode = 1  NEXT-OPEN   — fill at the OPEN of the bar after the signal (the
                                 paper-safest fill: no same-bar-close assumption at all).
                                 Same swing-low-derived risk/stop, management starts the
                                 bar AFTER the fill bar (same convention as mode 0, where
                                 management starts the bar after the signal bar).
  entry_mode = 2  RETEST(15)  — after the signal bar, wait up to N=15 bars for price to
                                 pull back to the broken trendline's value AT THE SIGNAL
                                 BAR (a resting limit) and fill there.
  entry_mode = 3  RETEST(30)  — same as mode 2 with N=30.

RETEST fill rule (gap-honest, pessimistic on conflicts): scan bars i+1 .. i+N. On each
bar, first check the ORIGINAL stop level (the signal bar's swing-low) — if that bar's low
already trades at/through the swing-low, the setup is invalidated (price broke down before
ever retesting the line) and NO TRADE is taken; this is checked before the limit so a bar
that touches both loses to the pessimistic outcome. Otherwise, if the bar's low reaches the
limit price, fill at min(limit, that bar's open) — if the bar opened through the limit, you
were filled at the (worse-for-you, but honest) open, not the untouchable limit. No bar in
the window satisfies either condition -> no trade for that signal (the setup is dropped,
not carried forward). Because stop_mult is pinned to 1.0 in the #149 config, the initial
stop price is always exactly the swing-low, so "hits the stop" and "hits the swing-low" are
the same test — no separate stop math needed during the scan.

Management (trailing / breakeven / hard stop) is byte-identical parent logic from the fill
bar onward — the bar the fill happens on gets NO management (mirrors the parent: the
signal/entry bar itself is never management-checked), matching mode 0's convention.

Pinned #149 params (run #149 + breakeven_R 1.5, CERTIFIED 2026-08-05):
  buf_atr=0.9, ema_len=390, tl_len=48, stop_mult=1.0, trail_frac=2.5, min_brk=1.3,
  vol_mult=0.8, atr_len=30, act_R=2.5, breakeven_R=1.5, regime_len=0
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m · RETEST-ENTRY / next-bar-open (research)"
DESCRIPTION = ("Research variant of ENGU-Q 1m (#149 config pinned): entry_mode switches "
              "between parent same-bar-close fill, next-bar-open fill, and RETEST-to-"
              "trendline limit fills (N=15 / N=30). All other params pinned single-valued.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

# ── pinned #149 + breakeven_R 1.5 config (single-valued; only entry_mode is searchable) ──
_PINNED = dict(buf_atr=0.9, ema_len=390, tl_len=48, stop_mult=1.0, trail_frac=2.5,
              min_brk=1.3, vol_mult=0.8, atr_len=30, act_R=2.5, breakeven_R=1.5,
              regime_len=0)

DEFAULT_PARAMS = {
    'entry_mode': {'default': 0, 'min': 0, 'max': 3, 'step': 1, 'type': 'int',
                   'label': 'Entry Mode',
                   'tooltip': '0=parent (signal-bar close, parity anchor). '
                              '1=next-bar-open (paper-safest fill). '
                              '2=retest to broken trendline, N=15 bars. '
                              '3=retest to broken trendline, N=30 bars.'},
    'buf_atr': {'default': _PINNED['buf_atr'], 'min': _PINNED['buf_atr'], 'max': _PINNED['buf_atr'],
               'step': 0.05, 'type': 'float', 'label': 'Breakout Buffer (x ATR) [PINNED #149]',
               'tooltip': 'Pinned to the #149 deploy value.'},
    'ema_len': {'default': _PINNED['ema_len'], 'min': _PINNED['ema_len'], 'max': _PINNED['ema_len'],
               'step': 10, 'type': 'int', 'label': 'Trend EMA Length [PINNED #149]',
               'tooltip': 'Pinned to the #149 deploy value.'},
    'tl_len': {'default': _PINNED['tl_len'], 'min': _PINNED['tl_len'], 'max': _PINNED['tl_len'],
              'step': 1, 'type': 'int', 'label': 'Trendline Length (bars) [PINNED #149]',
              'tooltip': 'Pinned to the #149 deploy value.'},
    'stop_mult': {'default': _PINNED['stop_mult'], 'min': _PINNED['stop_mult'], 'max': _PINNED['stop_mult'],
                 'step': 0.1, 'type': 'float', 'label': 'Stop (x risk-to-swing-low) [PINNED #149]',
                 'tooltip': 'Pinned to the #149 deploy value (1.0 -> stop == swing-low).'},
    'trail_frac': {'default': _PINNED['trail_frac'], 'min': _PINNED['trail_frac'], 'max': _PINNED['trail_frac'],
                  'step': 0.5, 'type': 'float', 'label': 'Trail Width (x risk) [PINNED #149]',
                  'tooltip': 'Pinned to the #149 deploy value.'},
    'min_brk': {'default': _PINNED['min_brk'], 'min': _PINNED['min_brk'], 'max': _PINNED['min_brk'],
               'step': 0.1, 'type': 'float', 'label': 'Breakout Decisiveness (x ATR) [PINNED #149]',
               'tooltip': 'Pinned to the #149 deploy value.'},
    'vol_mult': {'default': _PINNED['vol_mult'], 'min': _PINNED['vol_mult'], 'max': _PINNED['vol_mult'],
                'step': 0.1, 'type': 'float', 'label': 'Volume Spike (x avg) [PINNED #149]',
                'tooltip': 'Pinned to the #149 deploy value.'},
    'atr_len': {'default': _PINNED['atr_len'], 'min': _PINNED['atr_len'], 'max': _PINNED['atr_len'],
               'step': 1, 'type': 'int', 'label': 'ATR Length [PINNED #149]',
               'tooltip': 'Pinned to the #149 deploy value.'},
    'act_R': {'default': _PINNED['act_R'], 'min': _PINNED['act_R'], 'max': _PINNED['act_R'],
             'step': 0.5, 'type': 'float', 'label': 'Trail Activation (R) [PINNED #149]',
             'tooltip': 'Pinned to the #149 deploy value.'},
    'breakeven_R': {'default': _PINNED['breakeven_R'], 'min': _PINNED['breakeven_R'], 'max': _PINNED['breakeven_R'],
                   'step': 0.5, 'type': 'float', 'label': 'Breakeven (R) [PINNED #149]',
                   'tooltip': 'Pinned to the #149 deploy value.'},
    'regime_len': {'default': _PINNED['regime_len'], 'min': _PINNED['regime_len'], 'max': _PINNED['regime_len'],
                  'step': 5, 'type': 'int', 'label': 'Regime SMA (days, 0=off) [PINNED #149]',
                  'tooltip': 'Pinned to the #149 deploy value (0 = off).'},
}

PARAM_GRID_PRESETS = {
    'Entry modes (research)': {'entry_mode': [0, 1, 2, 3]},
}

_RISK_FLOOR = 0.5  # matches parent's max(0.25, 0.5)


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 entry_mode=0,
                 tl_len=48, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=390, atr_len=30, regime_len=0,
                 breakeven_R=1.5,
                 return_trades=False, _stop_event=None, _pause_event=None,
                 _signal_probe=None, _fill_probe=None, **_ignore):
    """_signal_probe / _fill_probe: optional lists (research instrumentation only, not
    part of the strategy contract). _signal_probe gets one entry appended per bar that
    clears every entry filter (a "signal"), regardless of what entry_mode does with it —
    lets a driver compute an exact fill-rate for a given mode's own run. _fill_probe gets
    (signal_close - fill_price) appended per ACTUAL fill for entry_mode in (2, 3) — lets a
    driver compute the average retest entry improvement in points."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    entry_mode = int(entry_mode)
    N_RETEST = 15 if entry_mode == 2 else (30 if entry_mode == 3 else 0)

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

        if entry_mode == 1:
            if i + 1 >= n:
                i += 1; continue  # no next bar to fill on -> no trade
            risk = c[i] - swing_low
            if risk < _RISK_FLOOR:
                i += 1; continue
            ep = o[i + 1]
            pos = {"bar": i + 1, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}
            i += 2  # management starts the bar AFTER the fill bar (parent convention)
            continue

        # entry_mode in (2, 3): RETEST to the broken trendline value at the signal bar
        limit = tl_now
        jmax = min(i + N_RETEST, n - 1)
        fill_j, fill_price = None, None
        for j in range(i + 1, jmax + 1):
            if l[j] <= swing_low:
                break  # pessimistic: stop/invalidation level hit before a retest fill
            if l[j] <= limit:
                fill_price = min(limit, o[j])  # gap-honest: fill at the open if it gapped through
                fill_j = j
                break
        if fill_j is None:
            i += 1; continue  # no fill within the window -> setup dropped, no trade
        risk = fill_price - swing_low
        if risk < _RISK_FLOOR:
            i = fill_j + 1; continue
        if _fill_probe is not None:
            _fill_probe.append(c[i] - fill_price)
        pos = {"bar": fill_j, "ep": fill_price, "risk": risk, "sl": swing_low, "act": False}
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

"""
ENGU-Q 1m ETH - PARTIAL EXIT / SCALE-OUT (research -> candidate, 2026-09-05)
--------------------------------------------------------------------------------
Fork of ENGUQ_1M_ETH_ER_1_0.py (the certified #309 crown: buf_atr 0.3, tl_len 206,
trail_frac 2.5, limit_atr 0.55, atr_len 52, act_R 1.5, breakeven_R 3.0, ema_len 220,
er_len 100, stop_mult 1.3, regime_len 10, min_brk 1.6, vol_mult 1.1, er_th 0.0).

#309's problem is RISK-ADJUSTED return, not raw profit: MAR 0.75 ($36.8k/yr against a
$48.9k drawdown), and 58% of net sits in ten trades with a 282-day longest hold - it
rides winners for the full round trip and gives back the whole open-profit swing if a
long hold turns. This adds a PARTIAL EXIT: once open profit first reaches `partial_R`
times the initial risk, `partial_frac` of the position is banked at that level. The
remainder keeps running under the EXISTING breakeven/trailing rules, unchanged.

partial_R = 0.0 is the PARITY ANCHOR (OFF): bit-identical to ENGUQ_1M_ETH_ER_1_0, and
with er_th 0 + limit_atr 0, to the certified #226 engine (n=2843, net $434,721.12).

IMPLEMENTATION TRAP (read before touching this file): the engine counts EV R, R/YR and
top-10 share off the NUMBER of trade tuples. A partial exit must NOT emit two trade
tuples for one entry - that would double the trade count and corrupt every downstream
stat. Instead the partial is a POSITION-SIZE WEIGHTING folded into the SAME trade's
single pnl number: realised pnl = partial_frac*(partial_level - entry) +
(1-partial_frac)*(final_exit - entry). One entry -> one trade tuple, always.

Partial level is checked on the bar's HIGH, the same convention as breakeven_R. If the
SAME bar also hits the stop, the stop takes priority (assume the worse sequence - the
partial does not get a free fill on a bar that also stopped out).

PRE-REGISTERED BARS (written before running; a cell is an improvement only if it trades
one number for another in an arguably-better direction, not a straight win):
  1. MAR up >= 15% vs 0.75 (i.e. MAR >= 0.8625)
  2. R/YR down <= 5% vs 43.4 (i.e. R/YR >= 41.23)
  3. top-10 share <= 58% AND still profitable excluding the top ten
  4. >= 90 held-out trades (entries >= 2025-06-30)
  5. PF >= 1.50 (may fall from 1.655 - banking early costs PF - but not through the floor)
PRIMARY (declared before running) = partial_R 2.0, partial_frac 0.5.
"""
import numpy as np

_AUGUR_PARENT = "ENGUQ_1M_ETH_ER_1_0.py"

STRATEGY_NAME = "ENGU-Q 1m ETH · PARTIAL EXIT (research)"
DESCRIPTION = ("The #309 ENGU-Q ETH engine plus a partial-exit / scale-out knob: once open "
               "profit first reaches partial_R x initial risk, partial_frac of the position "
               "is banked at that level and the remainder keeps riding the existing "
               "breakeven/trailing rules. partial_R=0 = parity with ENGUQ_1M_ETH_ER_1_0. "
               "Targets #309's risk-adjusted-return weakness (MAR 0.75) without touching "
               "its entry logic.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec (unchanged from parent)

DEFAULT_PARAMS = {
    'er_len': {'default': 60, 'min': 20, 'max': 120, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},
    'er_th': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor (0=off)',
              'tooltip': '0 = OFF / parity anchor. >0 = the signal bar must show at least '
                         'this efficiency ratio.'},
    'limit_atr': {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
                  'label': 'Shallow Limit Depth (x ATR)',
                  'tooltip': '0 = OFF / parity anchor (fill at signal-bar close). >0 = place a '
                             'resting limit this many ATR below the signal close; scans up to '
                             '10 bars for a gap-honest fill, else no trade.'},
    'tl_len': {'default': 170, 'min': 50, 'max': 300, 'step': 4, 'type': 'int',
              'label': 'Trendline Length (bars)',
              'tooltip': 'Bars of highs the descending trendline is fit to (must slope down).'},
    'vol_mult': {'default': 0.8, 'min': 0.0, 'max': 5.0, 'step': 0.1, 'type': 'float',
                'label': 'Volume Spike (x avg)',
                'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
    'stop_mult': {'default': 1.0, 'min': 0.3, 'max': 2.0, 'step': 0.1, 'type': 'float',
                 'label': 'Stop (x risk-to-swing-low)',
                 'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low.'},
    'act_R': {'default': 2.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
             'label': 'Trail Activation (R)',
             'tooltip': 'Start trailing once the trade is this many R in profit.'},
    'trail_frac': {'default': 2.5, 'min': 0.5, 'max': 4.0, 'step': 0.5, 'type': 'float',
                  'label': 'Trail Width (x risk)',
                  'tooltip': 'Trailing stop rides this far (in risk units) below the running high.'},
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
    'breakeven_R': {'default': 1.5, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. 0=off.'},
    'partial_R': {'default': 0.0, 'min': 0.0, 'max': 6.0, 'step': 0.5, 'type': 'float',
                  'label': 'Partial Exit Trigger (R, 0=off)',
                  'tooltip': '0 = OFF / parity anchor. >0 = when open profit first reaches this '
                             'many R of initial risk, bank partial_frac of the position at that '
                             'level; the remainder keeps running under the existing breakeven '
                             'and trailing rules. Checked on the bar high, same convention as '
                             'breakeven_R; if the same bar also stops out, the stop wins.'},
    'partial_frac': {'default': 0.5, 'min': 0.25, 'max': 0.75, 'step': 0.25, 'type': 'float',
                     'label': 'Partial Exit Fraction',
                     'tooltip': 'Fraction of the position closed at the partial-R level; the '
                                'rest rides to the final exit. Ignored when partial_R=0.'},
}

PARAM_GRID_PRESETS = {
    'Limit depth sweep (research)': {'limit_atr': [0.0, 0.10, 0.20, 0.35, 0.50]},
    'Partial exit sweep (research)': {'partial_R': [0.0, 1.0, 1.5, 2.0, 3.0, 4.0]},
}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 er_len=60, er_th=0.0, limit_atr=0.0,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5, partial_R=0.0, partial_frac=0.5,
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
    partial_R = float(partial_R)
    partial_frac = float(partial_frac)

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

            stop_hit = l[i] <= pos["sl"]

            # ── PARTIAL EXIT: bank partial_frac of the position once open profit first
            # reaches partial_R x initial risk, checked on the bar's HIGH like breakeven_R.
            # If the SAME bar also stops out, the stop takes priority (worse-sequence
            # assumption) -- no free partial fill on a bar that also hit the stop.
            # This does NOT create a second trade tuple: the partial is folded into this
            # position's single realised pnl at the end (see NOTE at file top -- two tuples
            # for one entry would double-count the trade in every downstream count).
            if (not stop_hit) and partial_R > 0 and not pos["partial_done"] and \
               (h[i] - pos["ep"]) >= partial_R * pos["risk"]:
                pos["partial_done"] = True
                pos["partial_price"] = pos["ep"] + partial_R * pos["risk"]

            if stop_hit:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                if pos["partial_done"]:
                    pnl = (partial_frac * (pos["partial_price"] - pos["ep"]) +
                           (1.0 - partial_frac) * (fill - pos["ep"]))
                else:
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
            pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False,
                   "partial_done": False, "partial_price": None}
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
        pos = {"bar": fill_j, "ep": fill_price, "risk": risk, "sl": fill_price - stop_mult * risk, "act": False,
               "partial_done": False, "partial_price": None}
        i = fill_j + 1  # management starts the bar AFTER the fill bar (parent convention)
        continue

    if pos is not None:
        if pos["partial_done"]:
            pnl = (partial_frac * (pos["partial_price"] - pos["ep"]) +
                   (1.0 - partial_frac) * (c[-1] - pos["ep"]))
        else:
            pnl = c[-1] - pos["ep"]
        pnl_list.append(pnl)
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

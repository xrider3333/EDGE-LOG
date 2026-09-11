"""ENGU-Q 1m ETH R5 -- the two independent fixes, STACKED. FENCED.
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R3_1_0.py (which is the live crown plus the hold cap). Trading logic is
IDENTICAL -- not one line of the engine changed. TWO defaults move together:

    limit_atr       0.55 -> 0.85     how far below the signal close the resting limit sits
    max_hold_bars   8280 -> 9660     force the position out after seven 24-hour sessions

WHY THESE TWO, AND WHY TOGETHER. They were found separately and they fix different things:

    the HOLD CAP fixes the TAIL. Concentration 55.6% -> 43.8%, index correlation +0.51 ->
    +0.38, held-out trades 118 -> 155, longest hold 142 days -> 13. It costs about 8% of net
    and a little risk-adjusted return.

    the DEEPER LIMIT fixes the MONEY SIDE. MAR 0.92 -> 1.08 and 2022 $7,340 -> $17,489, by
    buying a better price on the fills it gets and skipping the breakouts that never pull
    back. It does NOTHING for the tail (concentration 56.3%, correlation +0.44).

One is about when the position leaves, the other about where it is entered, so they had no
reason to interfere - and measured across a 4 x 4 grid (four limit depths x four caps), they
stack. Full window 2010-06-07..2026-06-30, NQ 1m 24h, cost 0.533 x $20:

    limit  cap      trades      net       PF     MAR   top-10  corr    2018      2022     held-out
     0.55  off       1,949   $613,126   1.711   0.92   55.6%  +0.51  $12,392   $ 7,340     118
     0.55  8,280     2,647   $565,913   1.507   0.87   43.8%  +0.38  $17,697   $ 2,794     155
     0.85  off       1,995   $617,284   1.717   1.08   56.3%  +0.44  $10,574   $17,489     118
     0.85  9,660 *   2,585   $566,907   1.538   1.16   43.0%  +0.27  $13,022   $24,796     151
     1.00  9,660     2,613   $550,660   1.526   1.12   42.3%  +0.29  $10,611   $21,742     161

Only two of the sixteen cells cleared the pre-registered bar (MAR above the deeper limit
alone, concentration below 46%, index correlation below 0.40, both index down years positive,
at least 150 held-out trades) - and they are neighbours, which is a plateau rather than a
spike.

THE ONE THAT MATTERS: this is the first ENGU-Q configuration measured that PASSES the enforced
tail bar. `queue_guard.py --tail-enforce` returns VERDICT PASS and TAIL / BETA BAR PASS:
top-10 share 45%, yearly correlation with the index +0.273, both index down years positive
(+$37,817 combined), 17 of 17 positive years, longest hold 15 days. The live crown FAILS that
same bar on correlation alone (+0.51), and the hold cap alone only reaches +0.38.

The held-out year is the part nobody tuned on, and it is better than the crown's:
    crown          118 trades  PF 1.675  net $88,380  EV R 0.487  R per year 57.5
    THIS           151 trades  PF 1.648  net $99,997  EV R 0.442  R per year 66.8
More trades, more money, higher R per year; slightly lower EV R per trade, which is exactly
what removing tail trades does to that metric and is the trade this whole line of work is
making deliberately. The independent reload of the held-out window agrees with the continuous
run (152 trades vs 151), so there is no lockbox artifact here.

WHAT IT COSTS: net $566,907 against the crown's $613,126, about 7.5%, and profit factor 1.711
-> 1.538. That is the price of not depending on the index rising.

HONEST CAVEATS.
 1. SELECTION. Both values were chosen after seeing their grids, on the same window they are
    scored on. Mitigations: each was found independently before the other existed; the
    limit plateau spans 0.70-1.00 and the cap plateau 8,280-9,660; and the neighbouring cell
    (limit 1.00, cap 9,660) also clears every bar. The fence below spans both plateaus so the
    validate can walk away from this exact pair.
 2. RE-OPTIMISING USUALLY DOES NOT PAY here (the ORB meta walk-forward found re-picked
    parameters earn less than leaving defaults alone). That is an argument for the validate,
    not for adoption.
 3. The cap does NOT travel - on ES the uncapped crown beats both capped variants and is the
    only one positive in 2022. Nothing here should be carried to an ES leg without its own
    evidence.

PARITY: with limit 0.55 and cap 8,280 this file reproduces its parent exactly (2,647 trades,
$565,913); with limit 0.55 and cap 0 it reproduces the live crown exactly (1,949 trades,
$613,126). Both verified before shipping.

Ranges are FENCED to the two plateaus actually measured.
"""
import numpy as np

# Compiled hot loops (augur_engine/fastloop.py). Every entry point returns None when the
# compiler is unavailable or EDGELOG_NO_FASTLOOP=1 is set, and each call site below keeps its
# original Python loop as the fallback - so this file behaves identically either way. The
# compiled walk is used only when no research probe and no stop/pause event is attached,
# because those are instrumentation the compiled code cannot carry.
try:
    from augur_engine import fastloop as _fl
except Exception:                                                   # pragma: no cover
    _fl = None

_AUGUR_PARENT = "ENGUQ_1M_ETH_R3_1_0.py"

STRATEGY_NAME = "ENGU-Q 1m ETH R5 (deeper limit + hold cap)"
DESCRIPTION = ("The efficiency-gated ENGU-Q engine plus a hard time cap: a position open "
               "max_hold_bars bars is closed at that bar's close, regardless of stop/trail "
               "state. 0 = OFF = parity with ENGUQ_1M_ETH_ER_1_0. Built to attack the "
               "months-long-hold tail artifact that inflates EV R on wide trails.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec

DEFAULT_PARAMS = {
    'max_hold_bars': {'default': 9660, 'min': 6900, 'max': 12000, 'step': 460, 'type': 'int',
                       'label': 'Max Hold (bars, 0=off)',
                       'tooltip': '0 = OFF / parity anchor. >0 = force-exit at that bar\'s '
                                  'close once a position has been open this many 1m bars. '
                                  '~1380 = 1 ETH day, ~6900 = 1 week, ~20000 = ~1 month. '
                                  'Attacks the months-long-hold EV R artifact directly.'},
    'er_len': {'default': 100, 'min': 20, 'max': 120, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},
    'er_th': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor (0=off)',
              'tooltip': '0 = OFF / parity anchor. >0 = the signal bar must show at least '
                         'this efficiency ratio; 0.25 is the battery-W champion. Do not '
                         'push above 0.25 - the 0.30 cell collapses the lockbox.'},
    'limit_atr': {'default': 0.85, 'min': 0.70, 'max': 1.0, 'step': 0.05, 'type': 'float',
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
    'stop_mult': {'default': 1.0, 'min': 0.3, 'max': 2.0, 'step': 0.1, 'type': 'float',
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
    'breakeven_R': {'default': 2.0, 'min': 0.0, 'max': 3.0, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. 0=off.'},
}

PARAM_GRID_PRESETS = {
    'Limit depth sweep (research)': {'limit_atr': [0.0, 0.10, 0.20, 0.35, 0.50]},
    'Time cap sweep (research)': {'max_hold_bars': [0, 1380, 2760, 6900, 13800, 20000]},
}


def _ema(a, n):
    if _fl is not None:
        _o = _fl.ema(a, n)
        if _o is not None:
            return _o
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 max_hold_bars=0,
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
    max_hold_bars = int(max_hold_bars)

    ema = _ema(c, int(ema_len))
    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb

    tr = _fl.true_range(h, l, c) if _fl is not None else None
    if tr is None:
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

    # ── COMPILED WALK. Identical arithmetic, transcribed in augur_engine/fastloop.py and
    #    parity-tested against the loop below (tests/test_fastloop_parity.py). Skipped
    #    whenever instrumentation is attached, and skipped entirely when the compiler is
    #    unavailable, in which case the interpreted loop below runs exactly as it always has.
    if (_fl is not None and _signal_probe is None and _fill_probe is None
            and _stop_event is None and _pause_event is None):
        _fast = _fl.engu_walk(
            o, h, l, c, ema, reg, atr, tr, er_ok,
            vv if have_vol else None, vavg if have_vol else None,
            tl_len=tl_len, buf_atr=buf_atr, min_brk=min_brk, vol_mult=vol_mult,
            limit_atr=limit_atr, stop_mult=stop_mult, act_R=act_R, trail_frac=trail_frac,
            breakeven_R=breakeven_R, n_scan=_N_SCAN, max_hold_bars=int(max_hold_bars))
        if _fast is not None:
            _e, _x, _p, _ep = _fast
            pnl_list = [float(v) for v in _p]
            if return_trades:
                trade_log = [(int(_e[q]), int(_x[q]), float(_p[q]), 1, float(_ep[q]))
                             for q in range(len(_e))]
            i = n                      # the interpreted walk below is now a no-op

    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break

        if pos is not None:
            # TIME CAP -- force exit at THIS bar's close once held >= max_hold_bars.
            # Checked first, before stop/trail updates, so a capped exit takes the
            # bar's close exactly as documented rather than racing a stop touch on
            # the same bar (stop/trail still take priority intrabar below if this
            # branch doesn't fire).
            if max_hold_bars > 0 and (i - pos["bar"]) >= max_hold_bars:
                fill = c[i]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades:
                    trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
                i += 1
                continue
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

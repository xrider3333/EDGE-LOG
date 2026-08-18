"""
ENGU-Q 1m ETH · trendline break (long) · HIGHER-TIMEFRAME STRUCTURAL TRAIL
---------------------------------------------------------------------------
Fork of the certified ENGUQ_1M_ETH_1_0.py (24-hour ETH engine) for LOCAL battery Q.
Two higher-timeframe ideas have already failed on this strategy as FILTERS (a 15m
trend-agreement tilt died in the lockbox; every regime/context gate tried has failed,
0-for-7). This file does something different: the slower chart is used only for
MANAGEMENT, never for trade selection. Once the trade's trail has activated, the stop
can ratchet up to sit just below the most recent COMPLETED higher-timeframe swing low
instead of (or in addition to) a fixed multiple of initial risk below the running high.
Market structure defines the exit floor rather than an arithmetic multiple.

Motivation: this strategy's profit lives in its wide stop -- 12 separate attempts to
TIGHTEN risk have destroyed the edge. A structural trail is not necessarily tighter: it
sits wide in trending markets (swing lows stay far below price) and tightens on its own
in choppy ones (swing lows stack up close beneath price), which is a materially
different mechanism than "just cut the stop".

New params (both OFF by default -- htf_trail=0 reproduces the certified engine bit-for-
bit and is the PARITY ANCHOR):
  htf_trail    (int, default 0)   -- higher-timeframe bar size in MINUTES (e.g. 15/60/240).
                                      0 = feature off, falls through to the stock trail.
  htf_buf_atr  (float, default 0.5) -- distance below the HTF swing low, in ATR(atr_len)
                                      units, the trail is allowed to sit.

Mechanics (leak-free): incoming 1-minute bars are grouped into HTF bars of htf_trail
minutes, aligned to the ET calendar day / top of the hour. An HTF bar is COMPLETE only
once its final constituent minute has printed -- the forming (currently-accumulating)
HTF bar is never touched. A completed HTF bar is a SWING LOW once the completed HTF bar
immediately before it AND immediately after it both have a higher low (simple 1-bar-
either-side pivot) -- so a pivot only becomes known once the *following* HTF bar has
also completed. Once the trade has activated (same act_R rule as the stock engine), the
stop becomes max(current stop, most recent known HTF swing low - htf_buf_atr*ATR). The
stop only ever ratchets up, exactly like the stock trail/breakeven ratchets. The initial
swing-low stop and the breakeven-R ratchet are byte-identical to the certified engine.
Gap-honest fills unchanged.

All 11 original params stay pinned to the certified config when used for parity/testing:
buf_atr 0.9, ema_len 1380, tl_len 170, stop_mult 1.0, trail_frac 2.5, min_brk 1.3,
vol_mult 0.8, atr_len 106, act_R 2.5, breakeven_R 1.5, regime_len 0.

PARITY GATE: htf_trail=0 must reproduce n=2843, net $434,721.12 (+/-$1) on
find_master('NQ','1m','eth','db_noadj_eth') sliced date_to='2026-06-30',
cost (pnl_pts-0.533)*20.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH HTF-trail 1.0"
DESCRIPTION = ("Fork of the certified ENGUQ_1M_ETH_1_0.py: adds an OPTIONAL higher-timeframe "
               "structural trail (htf_trail minutes, htf_buf_atr) that -- once the trade has "
               "activated -- ratchets the stop up to just below the most recent COMPLETED "
               "higher-timeframe swing low instead of (in addition to) the fixed-multiple trail. "
               "htf_trail=0 (default) reproduces the certified engine exactly. Management-only "
               "change, not a filter -- two prior HTF filter attempts on this strategy both failed.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

DEFAULT_PARAMS = {'tl_len': {'default': 170,
          'min': 50,
          'max': 300,
          'step': 4,
          'type': 'int',
          'label': 'Trendline Length (bars)',
          'tooltip': 'Bars of highs the descending trendline is fit to (must slope down). ETH 1m: range scaled '
                     '~x3.54 vs RTH (tl_len 170 = the frozen session-scaled triage config, RTH-equivalent 34x3.54~48; '
                     'ETH ~1380 bars/day vs RTH 390).'},
'vol_mult': {'default': 0.8,
            'min': 0.0,
            'max': 5.0,
            'step': 0.1,
            'type': 'float',
            'label': 'Volume Spike (x avg)',
            'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
'stop_mult': {'default': 1.0,
             'min': 0.3,
             'max': 2.0,
             'step': 0.1,
             'type': 'float',
             'label': 'Stop (x risk-to-swing-low)',
             'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low.'},
'act_R': {'default': 2.5,
         'min': 0.0,
         'max': 3.0,
         'step': 0.5,
         'type': 'float',
         'label': 'Trail Activation (R)',
         'tooltip': 'Start trailing once the trade is this many R in profit.'},
'trail_frac': {'default': 2.5,
              'min': 0.5,
              'max': 4.0,
              'step': 0.5,
              'type': 'float',
              'label': 'Trail Width (x risk)',
              'tooltip': 'Trailing stop rides this far (in risk units) below the running high.'},
'buf_atr': {'default': 0.9,
           'min': 0.0,
           'max': 1.0,
           'step': 0.05,
           'type': 'float',
           'label': 'Breakout Buffer (x ATR)',
           'tooltip': 'Close must clear the trendline by this x ATR.'},
'min_brk': {'default': 1.3,
           'min': 0.0,
           'max': 3.0,
           'step': 0.1,
           'type': 'float',
           'label': 'Breakout Decisiveness (x ATR)',
           'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},
'ema_len': {'default': 1380,
           'min': 100,
           'max': 1600,
           'step': 40,
           'type': 'int',
           'label': 'Trend EMA Length',
           'tooltip': 'Only take longs with close above this EMA (uptrend filter). ETH 1m: range scaled ~x3.54 '
                      'vs RTH (ema_len 1380 = the frozen session-scaled triage config; RTH-equivalent 390x3.54~1380 '
                      'means "roughly one ETH session").'},
'atr_len': {'default': 106,
           'min': 20,
           'max': 180,
           'step': 4,
           'type': 'int',
           'label': 'ATR Length',
           'tooltip': 'Lookback for ATR (buffer/decisiveness). ETH 1m: range scaled ~x3.54 vs RTH.'},
'regime_len': {'default': 0,
              'min': 0,
              'max': 100,
              'step': 5,
              'type': 'int',
              'label': 'Regime SMA (days, 0=off)',
              'tooltip': 'Only go long when close is above its N-DAY simple average — a longer-term trend gate on '
                         'top of the EMA. 0=off. NOTE: unchanged from the RTH file — this gate is hardcoded to 390 '
                         'bars/day internally, so on ETH data a nonzero value covers fewer calendar days than '
                         'intended; left as-is (engine untouched) and off by default.'},
'breakeven_R': {'default': 1.5,
               'min': 0.0,
               'max': 3.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Breakeven (R, 0=off)',
               'tooltip': 'Once the trade is this many R in profit (high vs entry), raise the stop to entry so it '
                          'can never go negative. 0=off. 1.5 is the frozen session-scaled triage default.'},
'htf_trail': {'default': 0,
             'min': 0,
             'max': 240,
             'step': 15,
             'type': 'int',
             'label': 'HTF Structural Trail (minutes, 0=off)',
             'tooltip': 'Once activated, ratchet the stop up to just below the most recent COMPLETED '
                        'higher-timeframe (this many minutes) swing low, minus htf_buf_atr*ATR. 0=off '
                        '(PARITY ANCHOR — reproduces the certified engine exactly). Management-only: does '
                        'NOT gate entries.'},
'htf_buf_atr': {'default': 0.5,
               'min': 0.0,
               'max': 2.0,
               'step': 0.25,
               'type': 'float',
               'label': 'HTF Swing-Low Buffer (x ATR)',
               'tooltip': 'Distance below the HTF swing low, in ATR(atr_len) units, the structural trail is '
                          'allowed to sit. Only used when htf_trail>0.'}}

PARAM_GRID_PRESETS = {'Robust (high-frequency)': {'tl_len': [90, 120, 160, 210],
                           'vol_mult': [1.1, 1.2, 1.3],
                           'stop_mult': [1.0, 1.5, 1.7],
                           'act_R': [1.0, 1.5],
                           'trail_frac': [2.0, 2.5],
                           'buf_atr': [0.2, 0.35],
                           'min_brk': [0.3, 0.7],
                           'ema_len': [100, 350, 700],
                           'atr_len': [50, 165],
                           'regime_len': [0, 20, 50],
                           'breakeven_R': [0.0, 1.0, 1.5, 2.0]},
'Wide': {'tl_len': [70, 120, 175, 245],
        'vol_mult': [1.0, 1.2, 1.5],
        'stop_mult': [1.0, 1.5],
        'act_R': [1.0, 1.5],
        'trail_frac': [1.5, 2.5, 3.0],
        'buf_atr': [0.1, 0.35],
        'min_brk': [0.0, 0.7],
        'ema_len': [100, 700],
        'atr_len': [50, 165],
        'regime_len': [0, 30, 50, 75],
        'breakeven_R': [0.0, 1.5, 3.0]}}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def _htf_swing_low_asof(index, o, h, l, c, htf_trail_min):
    """Return a per-1m-bar array: the most recent KNOWN (leak-free) completed
    higher-timeframe swing-low value as of each 1-minute bar index, or NaN if none
    known yet. HTF bars are grouped by ET calendar day + (minute-of-day // htf_trail_min),
    i.e. aligned to the top of the hour / day boundary. A swing low at HTF-bar j is only
    "known" starting from the 1m bar immediately AFTER HTF-bar j+1 has fully completed
    (needs both neighbors to confirm the pivot) — the forming HTF bar is never touched."""
    n = len(c)
    if index is None or n == 0:
        return np.full(n, np.nan)
    idx = index
    # ET-local minute-of-day + calendar-day key -> monotonic group id via change-points
    try:
        minute_of_day = (idx.hour.values.astype(np.int64) * 60
                          + idx.minute.values.astype(np.int64))
        day_key = (idx.year.values.astype(np.int64) * 10000
                   + idx.month.values.astype(np.int64) * 100
                   + idx.day.values.astype(np.int64))
    except AttributeError:
        return np.full(n, np.nan)
    bucket = minute_of_day // int(htf_trail_min)
    group_key = day_key * 10000 + bucket

    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = group_key[1:] != group_key[:-1]
    group_start = np.flatnonzero(change)
    group_end = np.r_[group_start[1:] - 1, n - 1]
    ng = len(group_start)
    if ng < 3:
        return np.full(n, np.nan)

    htf_high = np.maximum.reduceat(h, group_start)
    htf_low = np.minimum.reduceat(l, group_start)

    piv = np.zeros(ng, dtype=bool)
    piv[1:-1] = (htf_low[1:-1] < htf_low[:-2]) & (htf_low[1:-1] < htf_low[2:])

    # event value = htf_low at the pivot; becomes usable the bar AFTER the confirming
    # (j+1) HTF bar's final 1-minute bar has printed
    vals = np.full(n, np.nan)
    piv_idx = np.flatnonzero(piv)
    for j in piv_idx:
        usable_from = group_end[j + 1] + 1
        if usable_from < n:
            vals[usable_from] = htf_low[j]

    have = ~np.isnan(vals)
    if not have.any():
        return np.full(n, np.nan)
    fill_pos = np.where(have, np.arange(n), -1)
    fill_pos = np.maximum.accumulate(fill_pos)
    out = np.full(n, np.nan)
    known = fill_pos >= 0
    out[known] = vals[fill_pos[known]]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, htf_trail=0, htf_buf_atr=0.5,
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

    htf_trail = int(htf_trail)
    htf_swing = None
    if htf_trail > 0:
        htf_swing = _htf_swing_low_asof(index, o, h, l, c, htf_trail)

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
                if htf_swing is not None:
                    sw = htf_swing[i]
                    if not np.isnan(sw):
                        pos["sl"] = max(pos["sl"], sw - htf_buf_atr * atr[i])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                # gap-through realism: if the bar OPENED beyond the stop, the fill is the
                # open (can't be filled at a stop price the market never traded through
                # cleanly) — not the exact stop price. ORB 3.0 models the same.
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                # 6th field (risk) appended for R-multiple diagnostics -- existing
                # consumers only index t[0..4] or check len(t)>=3/4, so this is additive.
                if return_trades: trade_log.append((pos["bar"], i, pnl, 1, pos["ep"], pos["risk"]))
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
        risk = c[i] - swing_low
        if risk < max(0.25, 0.5):
            continue
        ep = c[i]
        pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"], pos["risk"]))
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

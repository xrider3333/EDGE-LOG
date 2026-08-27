"""
ENGU-Q 1m ETH · trendline break (long)
----------------------------------
Session-branched ENGU-Q (1m) for the 24-hour ETH (electronic/Globex) tape, mirroring the
existing TF-branched pattern (1m/5m/15m each get their own file so optimization doesn't
contaminate across timeframes). Same descending-trendline-break engine as ENGUQ_1M_1_0.py
(RTH) — only the time-lookback defaults + ranges are scaled for the ETH day. An ETH trading
day carries ~1380 1m bars vs RTH's 390 (24h continuous session vs 9:30-16:00 ET), so every
bar-count lookback (ema_len, tl_len, atr_len) is scaled by that ratio, ~x3.54, so the
trendline/EMA/ATR windows span roughly the same *calendar* time on ETH as they do on RTH.
Non-time params (vol_mult, stop_mult, act_R, trail_frac, buf_atr, min_brk, regime_len,
breakeven_R) are dimensionless multipliers/fractions and are left untouched.

Created 2026-08-05 from the Round-6 ETH triage (SESSION_SCALED config): frozen #149 RTH
params time-scaled x3.54, cleared triage on NQ 1m ETH db_noadj_eth <=2026-06-30
(n=2843, net=$434,721.12, PF=1.33). This file exists because run_validate only searches a
strategy file's own DEFAULT_PARAMS ranges, and the stock ENGUQ_1M_1_0.py caps ema_len at
~400 — unreachable for the ETH-scaled ema_len=1380. Trading logic below is an EXACT copy of
ENGUQ_1M_1_0.py's run_backtest — nothing in the engine itself changed, only defaults/ranges.
Data-derived rebuild of the discretionary ENGU. See Trading/ENGUQ_DB/ENGUQ_STRATEGY.md.

Entry (long): uptrend (close>EMA), GREEN candle CLOSING ABOVE a descending trendline
fit to the last tl_len highs (breaks the line of lower-highs = the pullback), above the
prior high, on a volume spike, decisive break. Stop = swing low; exit = trailing stop.
Trades are returned rich: (entry_idx, exit_idx, pnl_pts, side=+1, entry_px) -> MAE/MFE.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH 1.0"
DESCRIPTION = ("ENGU-Q 1m tuned for the 24h ETH tape: green candle breaking a descending trendline of recent lower-highs, above the trend EMA, on a volume spike; trailing exit. Time-lookbacks (ema_len/tl_len/atr_len) scaled ~x3.54 vs the RTH ENGUQ_1M_1_0 file to match ETH's ~1380 bars/day vs RTH's 390. Session-scaled config cleared triage on NQ 1m ETH (n=2843, net=$434,721.12, PF=1.33); formal Auto-Validate pending.")
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
                         'top of the EMA. 0=off. Days are TRUE calendar days on this ETH file (~1091 1m bars/day); '
                         'the inherited RTH 390 bars/day constant was corrected 2026-08-26, so a value here now '
                         'means what it says. Pinned off in the deployed frozen config — battery U closed the '
                         'trend-gate family (ENGUQ.md §1.4).'},
'cooldown_bars': {'default': 0, 'min': 0, 'max': 240, 'step': 5, 'type': 'int',
              'label': 'Re-entry cooldown (bars, 0=off)',
              'tooltip': 'After a trade closes, ignore new entry signals for this many 1m bars. '
                         'Added 2026-08-26 for owner item 896 (clusters of back-to-back trades). '
                         '0 = off = deployed behaviour. Causal: it only looks at when the previous '
                         'trade ENDED.'},
    'freeze_overnight': {'default': False, 'type': 'bool',
        'label': 'Freeze stop updates overnight (18:00-09:30 ET)',
        'tooltip': 'ON = trail/breakeven levels do not UPDATE during overnight bars; the existing stop stays live. Round-6 R6d flagged overnight exits as a net drag. OFF = certified triage behaviour.'},
'breakeven_R': {'default': 1.5,
               'min': 0.0,
               'max': 3.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Breakeven (R, 0=off)',
               'tooltip': 'Once the trade is this many R in profit (high vs entry), raise the stop to entry so it '
                          'can never go negative. 0=off. 1.5 is the frozen session-scaled triage default.'}}

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


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 cooldown_bars=0,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, freeze_overnight=False,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    ema = _ema(c, int(ema_len))
    # optional longer-term REGIME gate: close must be above its N-day simple average.
    # 0 = off. Long lengths skip bears/chop; short lengths whipsaw.
    #
    # BARS PER DAY IS SESSION-SPECIFIC. This file is the ETH (24h) variant, where a
    # trading day carries ~1091 one-minute bars, not RTH's 390. It was forked from the
    # RTH file and every other time-lookback (ema_len / tl_len / atr_len) was rescaled
    # for the 24h tape -- but this constant was left at 390, so `regime_len` silently
    # meant ~0.28 of a day each instead of one. regime_len=20 was really ~5.7 days.
    #
    # Nothing was ever DEPLOYED wrong: regime_len is pinned 0 (off) in the frozen config
    # (ENGUQ_1M_ETH_FROZEN_1_0.py), and battery U (ENGUQ.md 1.4) knew about this and
    # compensated by passing pre-scaled values. But a correct-looking sweep run by anyone
    # who had not read that footnote would have swept the wrong lengths entirely, which
    # is the kind of bug that produces a confident wrong answer.
    ETH_BARS_PER_DAY = 1091      # measured on the NQ 1m ETH master, not assumed
    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * ETH_BARS_PER_DAY
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

    # freeze_overnight (2026-08-18, round-6 R6d follow-up): the ETH study measured the
    # overnight-EXIT bucket as a net DRAG (-21% of net). ON = during overnight bars
    # (ET time >= 18:00 or < 09:30) the stop LEVEL does not update (no trail activation
    # flip, no ratchet, no breakeven arm) -- the existing stop stays LIVE on every bar
    # and still fills gap-honestly (safety unchanged). OFF (default) = bit-identical to
    # the certified triage run (n=2843 / $434,721.12 / PF 1.332 / DD -$50,420). Needs
    # bar timestamps (`index`); without them the flag silently stays off.
    frozen = None
    if freeze_overnight and index is not None and len(index) == n:
        try:
            import pandas as _pd
            _idx = _pd.DatetimeIndex(index)
            _mod = _idx.hour * 60 + _idx.minute
            frozen = np.asarray((_mod >= 1080) | (_mod < 570))
        except Exception:
            frozen = None

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl_list, trade_log = [], []
    # RE-ENTRY COOLDOWN (owner item 896, 2026-08-26): "no strategy should be messing up by
    # taking 5 trades in a row like that". After an exit, refuse new entries for this many
    # bars. Strictly causal -- it reads only the index of an exit that has already
    # happened, never anything about the trade it is about to skip. 0 = off, which is the
    # deployed behaviour, so this knob changes nothing until it is swept.
    cooldown_bars = int(cooldown_bars or 0)
    last_exit = -10 ** 9
    pos = None
    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        if pos is not None:
            if frozen is None or not frozen[i]:
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
                last_exit = i
            continue
        if cooldown_bars > 0 and (i - last_exit) < cooldown_bars:
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

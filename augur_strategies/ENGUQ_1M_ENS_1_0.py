"""
ENGU-Q 1m · 2-LOT ENSEMBLE (research fork) — ride+target lot + trailed lot.
----------------------------------------------------------------------------
Same #ENGUQ_1M_1_0 entry (descending-trendline-break long, uptrend EMA filter,
volume spike, decisive break) run as a 2-contract book with TWO exit plans in
parallel, pattern copied from ORB_3_0_ENS.py (item E / ORB.md §4.16):

    • Lot A (ride)  : parent's initial stop (stop_mult x risk-to-swing-low),
                      breakeven ratchet at breakeven_R (same as parent),
                      take-profit at entry + target_R x risk. NO trailing.
    • Lot B (trail) : same entry + initial stop, parent's act_R/trail_frac
                      trailing stop. NO target, NO breakeven — the trail is
                      its only manager, ridden to the parent's own exit
                      (data end / stop) exactly like the single-lot file.

Accounting mirrors the ORB ensemble: ONE trade is booked when BOTH lots have
closed, PnL = 0.5*(lotA + lotB) (the 1-contract-equivalent), so num_trades /
win_rate / PF / DD compare directly against ENGUQ_1M_1_0's own report. ENGU-Q
holds overnight/multi-day (no EOD flat) — whatever ends a trade in the parent
(stop hit, or data exhaustion) ends BOTH lots at that same price.

Research fork: **FAILED the gated validate twice** (runs #196/#197, 2026-08-05,
window 2010-06-07->2026-06-30 pinned, NQ 1m db_noadj_rth): PBO + luck gates fire
on the searched population; the free search drifts to vol_mult 0 / target 8R.
The deploy-neighborhood config beat the parent on a 250-day smoke (net/PF/DD all
better) but never survived the honest gates. Parked — do NOT deploy; see
PARAM_LIBRARY.md transferable-idea 9 before re-running anything here.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m · 2-lot ENSEMBLE (ride+target / trail) [RESEARCH FORK]"
DESCRIPTION = ("Research fork of ENGU-Q 1m: the same trendline-break entry run as a 2-contract "
               "book — lot A rides to a target_R take-profit with the parent's breakeven ratchet, "
               "lot B rides the parent's act_R/trail_frac trailing stop with no cap. Booked as the "
               "50/50 blend per trade (1-contract-equivalent), same pattern as ORB_3_0_ENS.py. "
               "NOT yet walk-forward validated — discovery fork for target_R.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_PARENT = "ENGUQ_1M_1_0.py"

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
             'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low. Shared by BOTH lots.'},
'act_R': {'default': 1.0,
         'min': 0.0,
         'max': 3.0,
         'step': 0.5,
         'type': 'float',
         'label': 'Trail Activation (R)',
         'tooltip': 'Lot B (trail) starts trailing once the trade is this many R in profit.'},
'trail_frac': {'default': 2.5,
              'min': 0.5,
              'max': 4.0,
              'step': 0.5,
              'type': 'float',
              'label': 'Trail Width (x risk)',
              'tooltip': 'Lot B (trail) rides this far (in risk units) below the running high.'},
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
           'tooltip': 'Lookback for ATR (buffer/decisiveness).'},
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
               'tooltip': 'Lot A (ride) only: once the trade is this many R in profit (high vs entry), raise '
                          'lot A stop to entry so it can never go negative. 0=off. Lot B (trail) ignores this '
                          'setting — its own trailing stop is its only manager.'},
'target_R': {'default': 4.5,
            'min': 2.0,
            'max': 8.0,
            'step': 0.5,
            'type': 'float',
            'label': 'Lot A Target (R multiples)',
            'tooltip': 'Take-profit for the RIDE lot (lot A) at this multiple of initial risk '
                       '(entry-to-swing-low distance). Lot B (trail) has no cap — it rides the '
                       'act_R/trail_frac trailing stop instead. 4.5R default, same starting point as '
                       "ORB 3.0's validated ensemble target."}}

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
                           'target_R': [3.0, 4.0, 4.5, 5.0, 6.0]},
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
        'target_R': [3.0, 4.0, 4.5, 5.0, 6.0]}}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, target_R=4.5,
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

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl_list, trade_log = [], []
    pos = None
    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        if pos is not None:
            ep = pos["ep"]; risk = pos["risk"]
            # ── lot B (trail): update trail FIRST, using only this bar's high (no look-ahead) ──
            if pos["b_on"]:
                if h[i] - ep >= act_R * risk:
                    pos["b_act"] = True
                if pos["b_act"]:
                    pos["bst"] = max(pos["bst"], h[i] - trail_frac * risk)
            # ── breakeven arm (lot A only; lot B has no breakeven — its trail manages it).
            #    Armed BEFORE the stop check, exactly like the parent (ENGUQ_1M_1_0.py
            #    raises sl to entry before testing l[i] on the same bar). ──
            if pos["a_on"] and breakeven_R > 0 and (h[i] - ep) >= breakeven_R * risk:
                pos["ast"] = max(pos["ast"], ep)
            # ── stop checks (both lots), parent's gap-through fill realism ──
            if pos["a_on"] and l[i] <= pos["ast"]:
                fill = o[i] if o[i] < pos["ast"] else pos["ast"]
                pos["a_pnl"] = fill - ep; pos["a_on"] = False; pos["a_ex"] = i
            if pos["b_on"] and l[i] <= pos["bst"]:
                fill = o[i] if o[i] < pos["bst"] else pos["bst"]
                pos["b_pnl"] = fill - ep; pos["b_on"] = False; pos["b_ex"] = i
            # ── lot A (ride) target check, gap-aware: a favorable gap through the target
            #    fills at the open (mirrors the stop-side gap realism above); a bar that
            #    touches both stop and target resolves stop-first (conservative). ──
            if pos["a_on"] and target_R > 0 and h[i] >= pos["tgt"]:
                fill = o[i] if o[i] > pos["tgt"] else pos["tgt"]
                pos["a_pnl"] = fill - ep; pos["a_on"] = False; pos["a_ex"] = i
            if not pos["a_on"] and not pos["b_on"]:
                last_ex = max(pos["a_ex"], pos["b_ex"])
                pnl = 0.5 * (pos["a_pnl"] + pos["b_pnl"])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], last_ex, pnl, 1, ep))
                pos = None
            continue
        # ── entry: IDENTICAL to ENGUQ_1M_1_0.py ──
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
        init_stop = ep - stop_mult * risk
        tgt = (ep + target_R * risk) if target_R > 0 else np.inf
        pos = {"bar": i, "ep": ep, "risk": risk,
               "ast": init_stop, "bst": init_stop, "b_act": False, "tgt": tgt,
               "a_on": True, "b_on": True,
               "a_pnl": 0.0, "b_pnl": 0.0, "a_ex": -1, "b_ex": -1}

    if pos is not None:
        # data exhaustion: whatever ends a trade in the parent (its own end-of-loop
        # close at the last price) ends BOTH lots at that same price — ENGU-Q holds
        # overnight/multi-day, there is no EOD flat to fall back on.
        ep = pos["ep"]
        if pos["a_on"]:
            pos["a_pnl"] = c[-1] - ep; pos["a_ex"] = n - 1
        if pos["b_on"]:
            pos["b_pnl"] = c[-1] - ep; pos["b_ex"] = n - 1
        pnl = 0.5 * (pos["a_pnl"] + pos["b_pnl"])
        pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl, 1, ep))
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

"""
ENGU-Q 1m ETH · trendline break (long) · MULTI-POSITION
--------------------------------------------------------
LOCAL RESEARCH BATTERY M — CONCURRENT POSITIONS (2026-08-18).

Fork of ENGUQ_1M_ETH_1_0.py (the certified 24h ETH engine) that tests ONE untested
lever: the strategy holds AT MOST ONE position at a time today, so while a monster
hold is running (run #223's champion: entered 2025-04-07, never hit its trail, zero
trades for the following year) every new qualifying signal is silently dropped.
Twelve prior attempts to fix this by tightening risk (caps/tighter trails/hold
limits/sizing) all destroyed the edge, because the edge lives in the wide stop.
This file does NOT touch entry logic, management logic (breakeven ratchet, trail,
gap-honest stop fill), or add any filter — it only changes the PORTFOLIO-SLOT count.

New param: `max_concurrent` (int, default 1). At default, this file is required to
reproduce ENGUQ_1M_ETH_1_0.py's output bit-for-bit (the parity anchor / gate for this
whole research battery) — see PARITY NOTE below for exactly how sameness is preserved.

When max_concurrent > 1: a new signal opens a NEW independent position (its own
swing-low stop, its own breakeven ratchet, its own trail off its own running high,
its own gap-honest fill) whenever FEWER than max_concurrent positions are open. Each
position is managed and closed independently, exactly as the single-position engine
manages its one position. Nothing about how a position is entered, sized (still 1
contract), or exited is changed — only how many can be open side-by-side.

PARITY NOTE: the original single-position loop reads `if pos is not None: <manage>;
continue` — i.e. once ANY position is open, the entry block is skipped for the WHOLE
bar even if that position closes on this very bar (no same-bar re-entry into the slot
that just freed up). To stay bit-identical at max_concurrent=1, this file gates the
entry block on the OPEN COUNT AT THE START OF THE BAR (before this bar's management
runs), not the count after management. For max_concurrent=1 that is exactly
`pos is not None` at bar-start, so behavior is unchanged. For max_concurrent>1 the
same rule is applied per-bar globally (if all N slots were occupied at bar-start, no
new entries that bar even if one just closed) — the natural generalization of the
existing rule, not a new one.

Trades are returned rich: (entry_idx, exit_idx, pnl_pts, side=+1, entry_px) -> MAE/MFE,
exactly as the single-position engine, so downstream analytics (mae_mfe, equity
curves, regime_report, etc.) work unmodified. With max_concurrent>1 multiple trades
can be simultaneously in-flight (overlapping entry_idx/exit_idx ranges) — this is new
and downstream code that assumes non-overlapping trades should be checked before use.
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH MP 1.0"
DESCRIPTION = ("Multi-position fork of ENGUQ_1M_ETH_1_0: identical entry/management/exit logic, "
               "but allows up to `max_concurrent` independent positions open at once instead of just "
               "one, so a long-running hold no longer blocks new signals. max_concurrent=1 reproduces "
               "the certified ETH engine exactly (parity anchor). Research battery M, 2026-08-18.")
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
'max_concurrent': {'default': 1,
               'min': 1,
               'max': 10,
               'step': 1,
               'type': 'int',
               'label': 'Max Concurrent Positions',
               'tooltip': 'How many independent positions this strategy may hold open at once. 1 = current '
                          'single-position behaviour (parity anchor, bit-identical to ENGUQ_1M_ETH_1_0). >1 lets '
                          'a long-running hold keep riding while new signals open separate positions alongside it '
                          '— entry/management/exit rules are unchanged, only the portfolio slot count.'}}

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
                           'breakeven_R': [0.0, 1.0, 1.5, 2.0],
                           'max_concurrent': [1, 2, 3]},
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
        'breakeven_R': [0.0, 1.5, 3.0],
        'max_concurrent': [1, 2, 3, 5]}}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, max_concurrent=1,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    max_concurrent = max(1, int(max_concurrent))
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
    positions = []          # list of open-position dicts (was a single `pos`)
    open_count_series = np.zeros(n, dtype=np.int16)   # how many positions open AT the start of each bar

    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break

        open_at_start = len(positions)          # same quantity `pos is not None` captured, generalized
        open_count_series[i] = open_at_start

        # --- manage every currently-open position (same per-position rules as the
        #     single-position engine: activation, trailing, breakeven, gap-honest stop) ---
        if positions:
            still_open = []
            for pos in positions:
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
                    if return_trades: trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                else:
                    still_open.append(pos)
            positions = still_open

        # PARITY NOTE (see module docstring): gate entry on the count AT BAR-START,
        # not after this bar's management closed slots -- no same-bar re-entry into a
        # slot that just freed up. At max_concurrent=1 this is exactly the original
        # `if pos is not None: ...; continue` behaviour.
        if open_at_start >= max_concurrent:
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
        positions.append({"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False})

    for pos in positions:
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
        out["_open_count_series"] = open_count_series   # research-only diagnostic, not part of the standard contract
    return out

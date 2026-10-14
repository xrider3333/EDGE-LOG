"""ENGU-Q 1m ETH HC -- the CROWN plus a HOLD CAP (force-exit after N bars).
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R2_1_0.py (crown #335). RESEARCH SIBLING. Report only.

WHY THIS EXISTS. The owner asked on 2026-10-12 for real walk-forward numbers on the quick-exit
idea after this lane's P&L scatter showed the crown's fast exits have a ZERO percent win rate
(every one of 187 trades held under an hour is a loss, because a fast exit IS a trailing-stop
hit). The scatter was EX-POST slicing - it could only say what happened to trades that happened
to exit fast. THIS FILE ASKS THE RUNNABLE QUESTION INSTEAD: what if fast exits are FORCED?
`owner override 10-12` of the power-first gate for these cells.

WHAT IT CHANGES. One knob, `max_hold_bars`: once a position has been open that many bars it is
closed at that bar's CLOSE, regardless of stop or trail state. At 1-minute bars on the 23-hour
tape, 15 = quarter hour, 60 = one hour, 240 = four hours, 1380 = one session, 6900 = one week.
0 = OFF and the file is trade-for-trade identical to the crown - that parity is the harness gate.

HONEST PRIOR, written before the run. The hold cap is ALREADY on this house's dead list
(memory `enguq-r57-entry-rules-dead` and the ENGU-Q round notes: "changing what the strategy does
with a signal it has already taken, without reducing exposure to winners - which rules out the hold
cap, the partial exit and risk caps, all already dead"). And the structural reason is the scatter
itself: 490 trades held 24h+ made $1.03M while 1,563 shorter ones lost $539k, so a cap can only
convert survivors into non-survivors. The expected result is that every cap loses money and that
tighter caps lose more. This is run to produce the NUMBERS the owner asked for, not because the
prior changed.

LATTICE NOTE, re-cut 2026-10-14 for HOLD CAP r2 (docs/PREREG_enguq_holdcap_r2_2026-10-14.md).
`max_hold_bars` is fenced 0..6900 step 60 -- one-hour resolution, capped at one week.

The r1 fence was 0..20000 step 5, which r1 needed to reach its 15-minute cell. A full Auto-Validate
does not: the owner's smallest named cell is 2 hours, and r1 already measured 15, 30 and 60 minutes
and found them dead or marginal. 4,001 lattice points for one knob inside a 900-trial search over
fourteen knobs is resolution nobody asked for, bought with trials the other knobs need.

The fence holds all five of the owner's named cells EXACTLY -- off 0, two hours 60x2, four hours
60x4, one session 60x23, one week 60x115 -- and still searches 116 values with 0 = off in the
space, so it is a re-cut and not a pinning. tools/enguq_queue_holdcap_r2.py asserts all five land
on the declared lattice and REFUSES to queue if any does not; that check sits in the queue path
rather than in tests/ so the ship stays on the fast contract tier, and it blocks the run itself
rather than a push, which is the thing that matters.
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

_AUGUR_PARENT = "ENGUQ_1M_ETH_R2_1_0.py"
STRATEGY_NAME = "ENGU-Q 1m ETH HC - crown plus a hold cap (research)"
DESCRIPTION = ("The shallow-limit ENGU-Q engine plus a momentum-quality gate: the Kaufman "
               "efficiency ratio of the last er_len minutes must reach er_th at the signal. "
               "er_th=0 = parity with ENGUQ_1M_ETH_LIM_1_0; battery-W champion cell is "
               "er_len 60, er_th 0.25 on the raw entry.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec

DEFAULT_PARAMS = {
    'er_len': {'default': 100, 'min': 20, 'max': 120, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},
    'er_th': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor (0=off)',
              'tooltip': '0 = OFF / parity anchor. >0 = the signal bar must show at least '
                         'this efficiency ratio; 0.25 is the battery-W champion. Do not '
                         'push above 0.25 - the 0.30 cell collapses the lockbox.'},
    'limit_atr': {'default': 0.55, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
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
    'stop_mult': {'default': 1.0, 'min': 0.8, 'max': 1.4, 'step': 0.1, 'type': 'float',
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
    'max_hold_bars': {'default': 0, 'min': 0, 'max': 6900, 'step': 60, 'type': 'int',
                      'label': 'Hold cap (bars, 0 = off)',
                      'tooltip': 'Force-close at this bar\'s close once the position has been open this many 1-minute bars. 0 = OFF = parity with the crown. 15 = quarter hour, 60 = one hour, 1380 = one session.'},
    'breakeven_R': {'default': 2.0, 'min': 1.0, 'max': 2.5, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. 0=off.'},
}
# phantom_safe (2026-09-26, WEBULL_GO_LIVE.md 3.7) is a run_backtest KEYWORD ARGUMENT, not a
# DEFAULT_PARAMS entry -- deliberately, per the review that caught the first draft: every
# search-space builder in the repo (augur_engine/auto.py's _auto_space_from_params, used by
# run_auto/Auto-Validate, plus optimizer.py's two grid builders) turns a DEFAULT_PARAMS 'bool'
# into a dimension it sweeps over [True, False], ignoring 'options' entirely. Registering the
# switch there would have spent every future tune/validate's trial budget probing a live-only
# safety flag, let a fold-truncated walk choose it, and changed the seeded sampler's space so
# an existing R2 auto-validate could no longer reproduce its trials with the flag off (hard
# rule 6). Kept OFF the ordinary way instead: the kwarg default below is False, so every caller
# that does not pass it -- every backtest, validate, and grid/random search -- runs exactly as
# before. The engine hands **params straight to run_backtest (augur_engine/engine.py), so
# api/cloud_signal.py's ENGUQ_335 leg reaches it by passing phantom_safe=True explicitly in its
# own params dict, without this file ever exposing a knob for it. See the SHALLOW LIMIT block
# below for what True changes.

PARAM_GRID_PRESETS = {
    'Limit depth sweep (research)': {'limit_atr': [0.0, 0.10, 0.20, 0.35, 0.50]},
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
                 er_len=60, er_th=0.0, limit_atr=0.0,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5, max_hold_bars=0,
                 phantom_safe=False,
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
            breakeven_R=breakeven_R, n_scan=_N_SCAN,
            max_hold_bars=int(max_hold_bars),
            phantom_safe=phantom_safe)
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
            # HOLD CAP -- force exit at THIS bar's close once held >= max_hold_bars.
            #   Checked before the stop/trail updates so a capped exit takes the bar's close
            #   exactly as documented rather than racing a stop touch on the same bar. This is
            #   TCAP's block, copied rather than re-derived so both files cap identically.
            if int(max_hold_bars) > 0 and (i - pos["bar"]) >= int(max_hold_bars):
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
            # WEBULL_GO_LIVE.md 3.7: jmax got clamped to n-1 because the data ends before
            # this setup's 10-bar window is over, not because the window genuinely ran out
            # with no fill. Off (default): the FULL-backtest reading -- the window always
            # finishes in a full backtest, so "no fill yet" and "no fill, ever" are the same
            # thing and the walk is free to move on to a later signal. On: a live/replay
            # caller cannot yet tell those two apart either, so it stops the walk here
            # instead of guessing -- no trade for this setup, and no later signal considered
            # until a fresh call sees more bars and can finish the scan for real.
            if phantom_safe and jmax < i + _N_SCAN:
                break
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

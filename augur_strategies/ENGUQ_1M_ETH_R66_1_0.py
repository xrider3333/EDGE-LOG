"""ENGU-Q 1m ETH R66 -- the crown plus ONE entry filter: a minimum initial risk width.
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R2_1_0.py (the crown's file). RESEARCH SIBLING, round 66, pre-registered in
ENGUQ_R66_PREREG.md before any hold length, survival rate or profit number was read. Not a paper
leg, not a book leg.

Identical to the parent except that a signal is taken only when
    (signal close - swing low over tl_len bars) / ATR  >=  min_risk_atr
Entry filter only. Exits, stops, trailing, the limit scan and the hold are the parent's.

WHY THIS ONE KEEPS THE LONG HOLDS, argued from the exit rule and not from data. The trade is
closed by a trail riding trail_frac x risk below the running high, and that distance is fixed IN
POINTS at entry and never widens. A trade therefore lives exactly as long as the market never
retraces trail_frac x risk from its best level; retracements scale with volatility; so the number
of days a trade can survive is an increasing function of risk / ATR AT THE SIGNAL BAR. The 35-day
hold that is this family's entire sealed year did not survive five weeks by luck of entry - it
survived because its trail was wide enough in volatility terms to absorb five weeks of pullback.
Ordinary survivors, which round 65 showed are far too common to be worth selecting, are trades
with ordinary trails that are taken out in days.

THE INVERSE EXPERIMENT ALREADY RAN. ENGUQ_1M_RC_1_0 capped initial risk at k x ATR and failed hard
- $453,532 down to -$75,905 at the tightest cap - and was written up as "ENGU-Q's profit LIVES in
the wide stop". If capping risk destroys the edge, selecting for wide risk is the experiment
nobody ran.

HOW IT IS WIRED. Folded into er_ok, the per-bar boolean the parent already evaluates at the signal
bar and already hands to the compiled walk, so the filter runs identically in both paths with no
engine or fastloop change. min_risk_atr at 0 leaves er_ok exactly as the parent built it, so the
file returns the parent's trade list trade for trade. Everything read is backward-looking: the
swing low is over [i-tl_len, i] and the ATR is the parent's own.

SCALE, measured as design groundwork before the bar was written: risk at entry runs 3.2 to 64.6
ATR with a median of 8.83, because the swing low is taken over 170 bars. A threshold near 1 ATR
would do nothing; the useful range is the one the DEFAULT_PARAMS fence covers.
"""
import numpy as np
import pandas as pd

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
STRATEGY_NAME = "ENGU-Q 1m ETH R66 - minimum initial risk width"
DESCRIPTION = ("The crown's ENGU-Q engine plus ONE entry test: the initial risk - signal "
               "close minus the swing low - must be at least min_risk_atr ATRs wide. The "
               "trail rides trail_frac x that risk, so a wider stop is what lets a trade "
               "absorb weeks of pullback and become a long hold. 0 = OFF, trade-for-trade "
               "parity with ENGUQ_1M_ETH_R2_1_0. Research sibling, round 66.")
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
    'min_risk_atr': {'default': 8.83, 'min': 0.0, 'max': 20.0, 'step': 0.01, 'type': 'float',
                     'label': 'Minimum initial risk (ATRs)',
                     'tooltip': 'Signal is taken only when the entry-to-swing-low distance is at least this many ATRs. 0 = OFF. Population median is 8.83, quartiles 7.12 and 11.53.'},
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
                 breakeven_R=1.5, min_risk_atr=0.0,
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

    # -- MINIMUM RISK WIDTH (round 66) at the SIGNAL bar. Folded into er_ok so the compiled and
    #    interpreted walks apply it identically, with no engine or fastloop change. 0 leaves
    #    er_ok exactly as the parent built it -> identical trade list.
    _mr = float(min_risk_atr)
    if _mr > 0:
        _tl = int(tl_len)
        _lo = pd.Series(l).rolling(_tl + 1, min_periods=_tl + 1).min().to_numpy()
        _a = np.where(np.isfinite(atr) & (atr > 0), atr, np.nan)
        with np.errstate(invalid='ignore'):
            _rr = (c - _lo) / _a
        # an unmeasurable window (the first tl_len bars, or a missing ATR) is REFUSED, never
        # waved through - the same convention the round-65 sibling uses.
        risk_ok = np.where(np.isnan(_rr), False, _rr >= _mr)
        er_ok = risk_ok if er_ok is None else (er_ok & risk_ok)

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
            breakeven_R=breakeven_R, n_scan=_N_SCAN, max_hold_bars=0,
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

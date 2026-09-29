"""ENGU-Q 1m ETH R62 -- the paper cell plus ONE new gate: a session window on the SIGNAL bar.
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R2_1_0.py (the crown's file). RESEARCH SIBLING, round 62, pre-registered
in ENGUQ_R62_PREREG.md before a single cell was measured. Not a paper leg, not a book leg.

Trading logic is IDENTICAL to the parent except for one added test: a signal is only taken when
the SIGNAL BAR's own timestamp falls inside [sess_from, sess_to) in US Eastern time. Exits,
stops, trailing, the limit scan and the hold are untouched -- a trade entered at 15:55 still runs
for weeks if it earns that.

WHY. Every dollar this family has made comes from trades that survive their first day: on the
paper cell over 2010-2026, the 1,078 intraday deaths cost $493,422, which is almost exactly the
whole net, while the 270 trades held longer than three days made $634,270. Day-one survival by
entry hour is 37-40% for 09:00-16:59 ET entries and 9-13% outside it, in EACH of the four eras
2010-14, 2015-18, 2019-22 and 2023-26, with no drift. The mechanism is liquidity: ENGU-Q reads
the imbalance of buyers and sellers, and outside the US cash session there is not enough size on
the NQ tape for that imbalance to mean anything.

HOW THE GATE IS WIRED, and why it costs nothing in parity. The window is folded into `er_ok`,
the per-bar boolean the parent already tests at the signal bar and already hands to the compiled
walk. So the gate runs identically in the compiled and interpreted paths, with no engine change
and no fastloop change. With sess_from 0 and sess_to 2400 the mask is all-True and this file
returns a trade list identical to the parent -- that identity is clause 6 of the pre-registration
and is asserted by the round's own harness.

The window is pinned to the US cash session (09:30-16:00 ET) on MECHANISM, not to the
best-looking hours in the table above. Neighbouring windows are reported as a plateau, never
selected from.

`index` is declared in the signature on purpose: the engine hands bar timestamps ONLY to
strategies that declare it, and the gate reads the signal bar's own timestamp, never the fill
bar's (FILL-bar conditions leak -- tag at the signal bar).
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
STRATEGY_NAME = "ENGU-Q 1m ETH R62 - cash-session entry window"
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
    'sess_from': {'default': 930, 'min': 0, 'max': 1600, 'step': 30, 'type': 'int',
                  'tooltip': 'Signal bar must be at or after this US Eastern clock time, '
                             'written HHMM. 0 with sess_to 2400 = OFF / parity with the parent.'},
    'sess_to': {'default': 1600, 'min': 800, 'max': 2400, 'step': 30, 'type': 'int',
                'tooltip': 'Signal bar must be BEFORE this US Eastern clock time, written HHMM. '
                           'Exits and holds are never gated - only the entry signal.'},
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
                 breakeven_R=1.5, sess_from=0, sess_to=2400, index=None,
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

    # ── SESSION WINDOW on the SIGNAL bar (round 62). Folded into er_ok so the compiled walk
    #    and the interpreted walk apply it identically, with no engine or fastloop change.
    #    OFF (0..2400) leaves er_ok exactly as the parent built it -> identical trade list.
    _sf, _st = int(sess_from), int(sess_to)
    if index is None and not (_sf <= 0 and _st >= 2400):
        # FAIL LOUD. A caller that narrows the window but supplies no bar timestamps would
        # otherwise get the PARENT trade list back under this file name - a silent no-op that
        # would quietly turn a forward shadow arm into a duplicate of its own control.
        raise ValueError(
            "ENGUQ_1M_ETH_R62: sess_from/sess_to narrow the entry window to %04d-%04d but no "
            "bar index was supplied. The engine hands timestamps only to strategies that "
            "declare index; call run_backtest with arrays that carry an index." % (_sf, _st))
    if index is not None and not (_sf <= 0 and _st >= 2400):
        _ts = pd.DatetimeIndex(index)
        _ts = _ts.tz_convert("America/New_York") if _ts.tz is not None else _ts.tz_localize("UTC").tz_convert("America/New_York")
        _hhmm = _ts.hour.values * 100 + _ts.minute.values
        hour_ok = (_hhmm >= _sf) & (_hhmm < _st)
        er_ok = hour_ok if er_ok is None else (er_ok & hour_ok)

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

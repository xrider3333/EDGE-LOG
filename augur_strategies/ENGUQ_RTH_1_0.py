"""ENGU-Q RTH -- the ENGU-Q mechanism re-ranged for a 390-bar REGULAR-HOURS session.
--------------------------------------------------------------------------------
Pre-registration: docs/PREREG_enguq_rth_r1_2026-10-10.md (draft + addenda 1, 2, 3).
Reviewed by STRATEGY-BEATING (inbox #67, #69); the folds and four pins are addenda 2 and 3.
Derived from ENGUQ_1M_ETH_R2_1_0.py (crown #335) by PATCHING, not by retyping, so the
code-parity diff shows only the intended additions.

WHY THIS FILE EXISTS. The owner asked on 2026-10-09 for a market-hours ENGU-Q for the Webull
QQQ book, after FRONTIER's Q36 showed the crown's settings run unchanged on QQQ's own bars make
308 walk-forward trades against the leg's 1,194. This is a NEW FIT on the tape it would trade,
not a port. The bar it must beat is Q36's reference - NQ #335's own signals filled on QQQ prints,
ROC at $30k of 28.42 - by more than the round's power line of 12.70, so about 41.1.

WHAT IS NEW, and it is only two things plus the fences:

1. Two NQ PRICE FLOORS become searchable knobs. The crown hard-codes an ATR floor of 0.25 in the
   break test and a risk floor of 0.50 points in both entry paths. Both are absolute NQ POINTS. On
   QQQ, where a share trades in cents, they reject nearly every candidate bar - they are the
   mechanism behind the 308-against-1,194 trade count. `atr_floor` and `risk_floor` expose them,
   on lattices that still hold the crown's own 0.25 / 0.50 so NQ parity stays exact.
2. Every lookback is re-fenced for a 390-bar session instead of a 1,380-bar one, and the fences
   are ANCHORED so the crown's own settings remain reachable (`tl_len` 206 = 10 + 4x49,
   `atr_len` 52 = 12 + 4x10). A search space that cannot express the cell it is compared against
   is a void round; this lane shipped that defect once already.

GUARDS at the new zero values (STRATEGY-BEATING pin 4):
  - `atr_floor` 0 would divide the break test by a zero ATR on a flat bar, and infinity passes any
    `min_brk`. Guarded with max(a, atr_floor, 1e-9).
  - `risk_floor` 0 would admit zero-risk entries, where the stop sits at the entry and R is
    undefined. Guarded by skipping any trade with risk <= 0.

THE COMPILED WALK IS DELIBERATELY NOT USED HERE, and that is a correctness point, not a
performance choice. augur_engine/fastloop.py hard-codes BOTH floors (`den = a if a > 0.25 else
0.25` and `if risk < 0.5`) and takes no parameter for either, so a compiled run would silently
ignore every `atr_floor` / `risk_floor` the search picks and hand back NQ-floored trades. The
interpreted walk below is therefore the only walk, the block that dispatches to the compiler is
REMOVED rather than left to be re-enabled by accident, and the per-trial cost is MEASURED in a
timed trial before 900 are queued (prereg addendum 2) instead of assumed.

NOTE ON `regime_len`: the code multiplies it by 390 bars. On this regular-hours tape one block is
exactly ONE SESSION, where on the crown's 23-hour tape the same 10 is about 2.8 sessions. The knob
means something different here; that is intended and recorded.

HONEST PRIOR, written before any number (prereg section d): both QQQ Auto-Validates this house has
run came back WEAK, re-searching a crown has not paid here before, and this family's money is in
multi-day survivors that the existing executor already preserves. My prior is that this search does
NOT produce something distinguishably better than Q36's 28.42 reference. The round is run because
the owner asked, because the operational case for a QQQ-native leg is real, and because a clean
falsification closes the question.
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

# Lineage only. Deliberately NOT _AUGUR_PARENT: this file carries FULL ranges and is its own
# search parent, so pointing a "re-run the parent" helper at the crown would re-run narrow NQ
# fences instead of this space.
_AUGUR_DERIVED_FROM = "ENGUQ_1M_ETH_R2_1_0.py"
STRATEGY_NAME = "ENGU-Q RTH - market-hours fit, 390-bar session"
DESCRIPTION = ("The shallow-limit ENGU-Q engine plus a momentum-quality gate: the Kaufman "
               "efficiency ratio of the last er_len minutes must reach er_th at the signal. "
               "er_th=0 = parity with ENGUQ_1M_ETH_LIM_1_0; battery-W champion cell is "
               "er_len 60, er_th 0.25 on the raw entry.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec

DEFAULT_PARAMS = {
    'er_len': {'default': 100, 'min': 10, 'max': 390, 'step': 10, 'type': 'int',
               'label': 'Efficiency Lookback (min)',
               'tooltip': 'Bars in the efficiency-ratio window (net move / path length).'},

    'er_th': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.05, 'type': 'float',
              'label': 'Efficiency Floor (0=off)',
              'tooltip': '0 = OFF / parity anchor. >0 = the signal bar must show at least '
                         'this efficiency ratio; 0.25 is the battery-W champion. Do not '
                         'push above 0.25 - the 0.30 cell collapses the lockbox.'},

    'limit_atr': {'default': 0.55, 'min': 0.0, 'max': 1.5, 'step': 0.05, 'type': 'float',
                  'label': 'Shallow Limit Depth (x ATR)',
                  'tooltip': '0 = OFF / parity anchor (fill at signal-bar close, identical to '
                             'ENGUQ_1M_ETH_1_0). >0 = place a resting limit this many ATR below '
                             'the signal close; scans up to 10 bars for a gap-honest fill, else '
                             'no trade.'},

    'tl_len': {'default': 206, 'min': 10, 'max': 782, 'step': 4, 'type': 'int',
              'label': 'Trendline Length (bars)',
              'tooltip': 'Bars of highs the descending trendline is fit to (must slope down).'},

    'vol_mult': {'default': 1.1, 'min': 0.0, 'max': 2.0, 'step': 0.1, 'type': 'float',
                'label': 'Volume Spike (x avg)',
                'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},

    'stop_mult': {'default': 1.0, 'min': 0.5, 'max': 2.0, 'step': 0.1, 'type': 'float',
                 'label': 'Stop (x risk-to-swing-low)',
                 'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low.'},

    'act_R': {'default': 1.5, 'min': 0.5, 'max': 3.0, 'step': 0.25, 'type': 'float',
             'label': 'Trail Activation (R)',
             'tooltip': 'Start trailing once the trade is this many R in profit.'},

    'trail_frac': {'default': 2.5, 'min': 1.0, 'max': 4.0, 'step': 0.25, 'type': 'float',
                  'label': 'Trail Width (x risk)',
                  'tooltip': 'Trailing stop rides this far (in risk units) below the running high.'},

    'buf_atr': {'default': 0.3, 'min': 0.0, 'max': 1.0, 'step': 0.05, 'type': 'float',
               'label': 'Breakout Buffer (x ATR)',
               'tooltip': 'Close must clear the trendline by this x ATR.'},

    'min_brk': {'default': 1.6, 'min': 0.5, 'max': 3.0, 'step': 0.1, 'type': 'float',
               'label': 'Breakout Decisiveness (x ATR)',
               'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},

    'ema_len': {'default': 220, 'min': 20, 'max': 1560, 'step': 20, 'type': 'int',
               'label': 'Trend EMA Length',
               'tooltip': 'Only take longs with close above this EMA (uptrend filter).'},

    'atr_len': {'default': 52, 'min': 12, 'max': 392, 'step': 4, 'type': 'int',
               'label': 'ATR Length',
               'tooltip': 'Lookback for ATR (buffer/decisiveness/limit depth).'},

    'regime_len': {'default': 10, 'min': 0, 'max': 20, 'step': 1, 'type': 'int',
                  'label': 'Regime SMA (days, 0=off)',
                  'tooltip': 'Only go long when close is above its N-DAY simple average. 0=off.'},

    'risk_floor': {'default': 0.50, 'min': 0.00, 'max': 0.50, 'step': 0.01, 'type': 'float',
                   'label': 'Minimum risk (price units)',
                   'tooltip': "Reject an entry whose stop distance is smaller than this, in the instrument's own price units. 0.50 is the value hard-coded for NQ points; on QQQ shares, where a cent is a tick, 0.50 rejects nearly every bar. 0.00 = off, and a zero-risk entry is still skipped."},
    'atr_floor': {'default': 0.25, 'min': 0.00, 'max': 0.25, 'step': 0.01, 'type': 'float',
                  'label': 'ATR floor in the break test (price units)',
                  'tooltip': "Floor under the ATR when the break is sized as a multiple of it, in the instrument's own price units. 0.25 is the value hard-coded for NQ points. 0.00 = off, held off a true zero so a flat bar cannot divide by zero."},
    'breakeven_R': {'default': 2.0, 'min': 0.0, 'max': 4.0, 'step': 0.5, 'type': 'float',
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
                 breakeven_R=1.5, risk_floor=0.50, atr_floor=0.25, phantom_safe=False,
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

    # ── NO COMPILED WALK HERE, AND THIS IS A CORRECTNESS LINE, NOT A SPEED ONE.
    #    The crown dispatches to augur_engine/fastloop.py's engu_walk at this point. That
    #    transcription hard-codes BOTH floors this file exposes -- `den = a if a > 0.25 else
    #    0.25` and `if risk < 0.5` -- and its signature has no parameter for either, so a
    #    compiled run would quietly discard whatever atr_floor / risk_floor the search chose
    #    and hand back NQ-floored trades. The dispatch is DELETED rather than disabled so it
    #    cannot be switched back on without reading this. Cost is measured, not assumed:
    #    prereg addendum 2 times one trial before 900 are queued.
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
        # pin 4: the 1e-9 keeps a flat bar from dividing by zero when atr_floor is 0.
        if (c[i] - tl_now) / max(a, float(atr_floor), 1e-9) < min_brk:
            i += 1; continue
        if er_ok is not None and not er_ok[i]:
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()
        if _signal_probe is not None:
            _signal_probe.append(1)

        if limit_atr <= 0:
            risk = c[i] - swing_low
            # pin 4: risk <= 0 is skipped whatever the floor says -- the stop would sit at or
            # above the entry and R would be undefined.
            if risk <= 0 or risk < float(risk_floor):
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
        if risk <= 0 or risk < float(risk_floor):   # pin 4, as above
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

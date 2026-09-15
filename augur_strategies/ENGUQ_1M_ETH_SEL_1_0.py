"""ENGU-Q 1m ETH SEL -- RESEARCH SIBLING for round 57: change WHICH setups are taken.
--------------------------------------------------------------------------------
Pre-registration: ENGUQ_R57_PREREG.md (committed a7f0811 before any cell ran). This file is the
instrument that document describes in sections 2 and 5. It is NOT a crown, NOT a paper leg and
is never Auto-Validated as a four-knob search; a hypothesis that passes gets its own fenced
single-hypothesis file later.

WHAT IT IS. A copy of ENGUQ_1M_ETH_R5_1_0.py (whose trade walk reproduces R2 exactly at limit
0.55 / cap 0) with DEFAULT_PARAMS reset to the R2 defaults (= run #335 crown, paper ENGUQ_335),
plus FOUR entry-selection knobs, every one default OFF:

    quiet_pct    H-A  quiet-tape stand-down: drop the signal when the 14-bar ATR sits below this
                      percentile of the prior 252 sessions' ATR14 (stride-23 samples, >= 60
                      sessions and >= 100 samples, else the signal passes)
    stretch_max  H-B  daily stretch cap: drop the signal when (close - prior session's 20-session
                      close SMA) / prior session's 14-session daily ATR is above this
    rec_min      H-C  leg recovery floor: drop the signal when (close - swing low) / (trendline
                      window high - swing low) is below this
    vol_clock    H-D  clock-unit volume test: REPLACES the 20-bar volume test; the signal needs
                      volume >= this x the mean volume at the same ET clock minute over the prior
                      20 sessions (>= 10 prints; a missing baseline FAILS)

Sessions roll at 18:00 ET (session key = date of ET timestamp + 6 h), factorised in bar order.

HOW THE RULES ENTER THE WALK. Each rule is a boolean per-bar mask ANDed into the existing `er_ok`
argument of augur_engine.fastloop.engu_walk (passed as `er_ok` when the efficiency gate is off).
The walk tests er_ok[i] at the SIGNAL bar i, after the breakout tests and before the resting
limit is placed; a failed test moves to i+1 like every other filter. No rule reads the fill bar.
With every knob OFF the mask is None and the byte-identical compiled walk runs; fastloop.py is
untouched. The interpreted fallback uses the same combined er_ok at its er_ok test.

TIMESTAMPS. The signature declares `index=None` explicitly: the engine and auto.py hand bar
timestamps (walk-forward slices included) only to plugins that NAME `index`. If a session-keyed
knob (quiet_pct, stretch_max, vol_clock) is on and no index arrives, this file RAISES - it never
goes silently inert. rec_min needs no timestamps.

SPEED. Knob-free arrays (session keys, the ATR14 percentile, the daily stretch, the clock-volume
baseline, and the recovery ratio per tl_len) are memoised per process, keyed by bar count, first
and last timestamp and volume nbytes (plus a small price / volume fingerprint so two different
tapes with the same shape can never share an entry), so a later validate pays each once per
frame.

RESEARCH-ONLY INSTRUMENTATION (not part of the strategy contract, never in a validate):
    _mask_override       boolean array that REPLACES the combined rule mask (needs a knob on;
                         keeps the compiled path) - the S12 day-shift null uses it
    _signal_index_probe  list; the interpreted walk appends the signal bar index i at every bar
                         that clears every entry filter (forces the interpreted walk) - audits
    _signal_probe / _fill_probe   unchanged from R5
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

STRATEGY_NAME = "ENGU-Q 1m ETH SEL (round 57 research sibling)"
DESCRIPTION = ("RESEARCH ONLY. The R2 crown's engine (R5 walk at R2 defaults) plus four "
               "pre-registered entry-selection knobs, all default OFF = parity with "
               "ENGUQ_1M_ETH_R2_1_0: quiet-tape stand-down, daily stretch cap, leg recovery "
               "floor, clock-unit volume test. One knob at a time; never validated as a "
               "four-knob search.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_N_SCAN = 10  # fixed per battery-O spec

# frozen rule constants (ENGUQ_R57_PREREG.md section 5) - NOT knobs
_QA_ATR_LEN = 14
_QA_LOOKBACK = 252
_QA_MIN_SESS = 60
_QA_STRIDE = 23
_QA_MIN_SAMPLES = 100
_HB_ATR_SESS = 14
_HB_SMA_SESS = 20
_HD_SESS = 20
_HD_MIN_PRINTS = 10

DEFAULT_PARAMS = {
    'max_hold_bars': {'default': 0, 'min': 0, 'max': 12000, 'step': 460, 'type': 'int',
                       'label': 'Max Hold (bars, 0=off)',
                       'tooltip': '0 = OFF (the R2 crown). >0 = force-exit at that bar\'s '
                                  'close once a position has been open this many 1m bars. '
                                  '9,660 = the R5 replication setting.'},
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
                'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off. '
                           'Ignored (switched off) while vol_clock > 0.'},
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
    'breakeven_R': {'default': 2.0, 'min': 1.0, 'max': 2.5, 'step': 0.5, 'type': 'float',
                   'label': 'Breakeven (R, 0=off)',
                   'tooltip': 'Once the trade is this many R in profit, raise the stop to entry. 0=off.'},
    # ── round 57 entry-selection knobs (ENGUQ_R57_PREREG.md section 5), all OFF by default ──
    'quiet_pct': {'default': 0.0, 'min': 0.0, 'max': 30.0, 'step': 10.0, 'type': 'float',
                  'label': 'H-A Quiet-Tape Floor (ATR14 pctile, 0=off)',
                  'tooltip': '0 = OFF. >0 = skip the signal when the 14-bar ATR ranks below this '
                             'percentile of the prior 252 sessions (18:00 ET roll). Needs bar '
                             'timestamps. Pre-registered grid 10 / 20 (centre) / 30.'},
    'stretch_max': {'default': 0.0, 'min': 0.0, 'max': 2.0, 'step': 0.5, 'type': 'float',
                    'label': 'H-B Daily Stretch Cap (daily ATRs, 0=off)',
                    'tooltip': '0 = OFF. >0 = skip the signal when the close sits more than this '
                               'many prior-session daily ATR(14) above the prior session\'s '
                               '20-session close SMA. Needs bar timestamps. Grid 2.0 / 1.5 '
                               '(centre) / 1.0.'},
    'rec_min': {'default': 0.0, 'min': 0.0, 'max': 0.55, 'step': 0.05, 'type': 'float',
                'label': 'H-C Leg Recovery Floor (0=off)',
                'tooltip': '0 = OFF. >0 = skip the signal when the close has recovered less than '
                           'this share of the trendline window\'s high-to-swing-low leg. Grid '
                           '0.35 / 0.45 (centre) / 0.55.'},
    'vol_clock': {'default': 0.0, 'min': 0.0, 'max': 1.5, 'step': 0.25, 'type': 'float',
                  'label': 'H-D Clock-Unit Volume (x same-minute mean, 0=off)',
                  'tooltip': '0 = OFF (the 20-bar vol_mult test). >0 = REPLACE that test: the '
                             'signal bar\'s volume must reach this x the mean volume at the same '
                             'ET clock minute over the prior 20 sessions (>= 10 prints, else no '
                             'trade). Needs bar timestamps. Grid 1.0 / 1.25 (centre) / 1.5.'},
}

PARAM_GRID_PRESETS = {
    'Limit depth sweep (research)': {'limit_atr': [0.0, 0.10, 0.20, 0.35, 0.50]},
    'Time cap sweep (research)': {'max_hold_bars': [0, 1380, 2760, 6900, 13800, 20000]},
    'R57 H-A quiet tape (pre-registered)': {'quiet_pct': [0.0, 10.0, 20.0, 30.0]},
    'R57 H-B daily stretch (pre-registered)': {'stretch_max': [0.0, 2.0, 1.5, 1.0]},
    'R57 H-C leg recovery (pre-registered)': {'rec_min': [0.0, 0.35, 0.45, 0.55]},
    'R57 H-D clock volume (pre-registered)': {'vol_clock': [0.0, 1.0, 1.25, 1.5]},
}


def _ema(a, n):
    if _fl is not None:
        _o = _fl.ema(a, n)
        if _o is not None:
            return _o
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# round 57 rule features (knob-free, memoised per process)
# ─────────────────────────────────────────────────────────────────────────────

_MEMO_CAP = 4
_MEMO = {}            # feature name -> [(key, value), ...], index 0 = least recently used


def _memo_get(name, key):
    lst = _MEMO.get(name)
    if not lst:
        return None
    for j, (k, v) in enumerate(lst):
        if k == key:
            lst.append(lst.pop(j))
            return v
    return None


def _memo_put(name, key, value):
    lst = _MEMO.setdefault(name, [])
    lst.append((key, value))
    del lst[:-_MEMO_CAP]
    return value


def _ro(a):
    a.setflags(write=False)
    return a


def _as_index(index, n):
    ix = pd.DatetimeIndex(index)
    if len(ix) != n:
        raise ValueError("ENGUQ SEL: index has %d timestamps for %d bars" % (len(ix), n))
    return ix


def _frame_key(h, l, c, volumes, ix):
    """(bar count, first and last timestamp, volume nbytes) + a price / volume fingerprint."""
    n = len(c)
    if ix is not None and len(ix):
        t0, t1, tz = int(ix.asi8[0]), int(ix.asi8[-1]), str(ix.tz)
    else:
        t0 = t1 = tz = None
    if volumes is None:
        vnb, vsum = -1, None
    else:
        va = np.asarray(volumes, float)
        vnb, vsum = int(va.nbytes), float(np.nansum(va))
    fp = (float(c[0]), float(c[-1]), float(h[n // 2]), float(l[n // 3]), float(np.sum(c)))
    return (n, t0, t1, tz, vnb, vsum) + fp


def _sessions(ix, n):
    """(session index per bar, ET clock minute per bar, session starts, session ends)."""
    key = ("sess", n, int(ix.asi8[0]), int(ix.asi8[-1]), str(ix.tz))
    hit = _memo_get("sess", key)
    if hit is not None:
        return hit
    sh = ix + pd.Timedelta(hours=6)
    if sh.tz is not None:
        sh = sh.tz_localize(None)
    sess = pd.factorize(sh.normalize().asi8)[0].astype(np.int64)
    minute = (np.asarray(ix.hour, np.int64) * 60 + np.asarray(ix.minute, np.int64))
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    ends = np.r_[starts[1:], n]
    if len(starts) != int(sess.max()) + 1:
        raise ValueError("ENGUQ SEL: session keys are not contiguous (index not sorted?)")
    return _memo_put("sess", key, (_ro(sess), _ro(minute), _ro(starts), _ro(ends)))


def _feat_quiet(tr, ses, fkey):
    """H-A: q[k] = percentile of ATR14[k] against the prior 252 sessions' stride-23 samples."""
    hit = _memo_get("quiet", fkey)
    if hit is not None:
        return hit
    sess, _minute, starts, ends = ses
    n = len(tr)
    atr14 = pd.Series(np.asarray(tr, float)).rolling(_QA_ATR_LEN, min_periods=_QA_ATR_LEN).mean().to_numpy()
    samples = [atr14[s:e:_QA_STRIDE] for s, e in zip(starts, ends)]
    q = np.full(n, np.nan)
    for s_ in range(_QA_MIN_SESS, len(starts)):
        ref = np.concatenate(samples[max(0, s_ - _QA_LOOKBACK):s_])
        ref = ref[~np.isnan(ref)]
        if len(ref) < _QA_MIN_SAMPLES:
            continue
        ref.sort()
        seg = atr14[starts[s_]:ends[s_]]
        r = 100.0 * np.searchsorted(ref, seg, side="right") / float(len(ref))
        r[np.isnan(seg)] = np.nan
        q[starts[s_]:ends[s_]] = r
    return _memo_put("quiet", fkey, _ro(q))


def _feat_stretch(h, l, c, ses, fkey):
    """H-B: S[i] = (c[i] - SMA20_{s-1}) / ATRd_{s-1}, sessions rolling at 18:00 ET."""
    hit = _memo_get("stretch", fkey)
    if hit is not None:
        return hit
    sess, _minute, starts, ends = ses
    Ht = np.maximum.reduceat(h, starts)
    Lt = np.minimum.reduceat(l, starts)
    Ct = c[ends - 1]
    TRd = np.empty(len(starts))
    TRd[0] = Ht[0] - Lt[0]
    if len(starts) > 1:
        Cp = Ct[:-1]
        TRd[1:] = np.maximum(Ht[1:] - Lt[1:], np.maximum(np.abs(Ht[1:] - Cp), np.abs(Lt[1:] - Cp)))
    ATRd = pd.Series(TRd).rolling(_HB_ATR_SESS, min_periods=_HB_ATR_SESS).mean().to_numpy()
    SMA = pd.Series(Ct).rolling(_HB_SMA_SESS, min_periods=_HB_SMA_SESS).mean().to_numpy()
    prevA = np.r_[np.nan, ATRd[:-1]][sess]
    prevS = np.r_[np.nan, SMA[:-1]][sess]
    ok = np.isfinite(prevA) & np.isfinite(prevS) & (prevA > 0)
    S = np.full(len(c), np.nan)
    S[ok] = (c[ok] - prevS[ok]) / prevA[ok]
    return _memo_put("stretch", fkey, _ro(S))


def _feat_recovery(h, l, c, tl_len, fkey):
    """H-C: rec[i] = (c[i] - min l[i-tl..i]) / (max h[i-tl..i-1] - min l[i-tl..i])."""
    key = fkey + (int(tl_len),)
    hit = _memo_get("rec", key)
    if hit is not None:
        return hit
    tl_len = int(tl_len)
    wh_roll = pd.Series(h).rolling(tl_len, min_periods=tl_len).max().to_numpy()
    WH = np.r_[np.nan, wh_roll[:-1]]
    SL = pd.Series(l).rolling(tl_len + 1, min_periods=tl_len + 1).min().to_numpy()
    den = WH - SL
    ok = den > 0
    rec = np.full(len(c), np.nan)
    rec[ok] = (c[ok] - SL[ok]) / den[ok]
    return _memo_put("rec", key, _ro(rec))


def _feat_clock_base(vv, ses, fkey):
    """H-D: B[k] = mean volume at clock minute m[k] over sessions sess[k]-20..sess[k]-1 that
    printed that minute; NaN if sess[k] < 21 or fewer than 10 prints."""
    hit = _memo_get("clock", fkey)
    if hit is not None:
        return hit
    sess, minute, starts, _ends = ses
    n = len(sess)
    if vv is None:
        return _memo_put("clock", fkey, _ro(np.full(n, np.nan)))
    vv = np.asarray(vv, float)
    width = int(len(starts)) + 1
    key = minute * width + sess
    pool = np.flatnonzero(np.isfinite(vv))                  # a NaN volume = not printed
    order = pool[np.argsort(key[pool], kind="stable")]
    ks = key[order]
    cs = np.concatenate([[0.0], np.cumsum(vv[order])])
    lo = np.searchsorted(ks, minute * width + np.maximum(sess - _HD_SESS, 0), side="left")
    hi = np.searchsorted(ks, key, side="left")
    cnt = hi - lo
    B = np.full(n, np.nan)
    ok = (sess >= _HD_SESS + 1) & (cnt >= _HD_MIN_PRINTS)
    B[ok] = (cs[hi[ok]] - cs[lo[ok]]) / cnt[ok]
    return _memo_put("clock", fkey, _ro(B))


def _true_range(h, l, c):
    """The walk's own true range (identical arithmetic to run_backtest below)."""
    tr = _fl.true_range(h, l, c) if _fl is not None else None
    if tr is None:
        n = len(c)
        tr = np.empty(n); tr[0] = h[0] - l[0]
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def _rule_features(opens, highs, lows, closes, volumes=None, index=None, tl_len=206, tr=None):
    """Research helper: the four in-engine rule features on one frame, exactly as run_backtest
    builds them. Returns dict(q, stretch, rec, clock_base, vol_vs_clock); the session-keyed ones
    are None when no index is given."""
    h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    ix = _as_index(index, n) if index is not None else None
    fkey = _frame_key(h, l, c, volumes, ix)
    if tr is None:
        tr = _true_range(h, l, c)
    out = dict(rec=_feat_recovery(h, l, c, tl_len, fkey), q=None, stretch=None,
               clock_base=None, vol_vs_clock=None)
    if ix is not None:
        ses = _sessions(ix, n)
        out["q"] = _feat_quiet(tr, ses, fkey)
        out["stretch"] = _feat_stretch(h, l, c, ses, fkey)
        vv = None if volumes is None else np.asarray(volumes, float)
        B = _feat_clock_base(vv, ses, fkey)
        out["clock_base"] = B
        if vv is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                out["vol_vs_clock"] = vv / B
    return out


def _rule_mask(h, l, c, volumes, ix, tr, tl_len, quiet_pct, stretch_max, rec_min, vol_clock):
    """AND of every enabled rule's per-bar pass mask (True = the signal may be taken)."""
    n = len(c)
    fkey = _frame_key(h, l, c, volumes, ix)
    ses = _sessions(ix, n) if ix is not None else None
    m = np.ones(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        if quiet_pct > 0:
            q = _feat_quiet(tr, ses, fkey)
            m &= ~(np.isfinite(q) & (q < quiet_pct))
        if stretch_max > 0:
            S = _feat_stretch(h, l, c, ses, fkey)
            m &= ~(np.isfinite(S) & (S > stretch_max))
        if rec_min > 0:
            rec = _feat_recovery(h, l, c, tl_len, fkey)
            m &= ~(np.isfinite(rec) & (rec < rec_min))
        if vol_clock > 0:
            vv = None if volumes is None else np.asarray(volumes, float)
            B = _feat_clock_base(vv, ses, fkey)
            if vv is None:
                m &= False                                   # no volume = no baseline = FAIL
            else:
                m &= np.isfinite(B) & (vv >= vol_clock * B)
    return m


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 max_hold_bars=0,
                 er_len=60, er_th=0.0, limit_atr=0.0,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5,
                 quiet_pct=0.0, stretch_max=0.0, rec_min=0.0, vol_clock=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None,
                 _signal_probe=None, _fill_probe=None,
                 _mask_override=None, _signal_index_probe=None, **_ignore):
    """_signal_probe / _fill_probe: optional lists (research instrumentation only, not part
    of the strategy contract). _signal_probe gets one entry appended per bar that clears
    every entry filter (a "signal"), regardless of whether limit_atr fills it -- lets a
    driver compute an exact fill-rate. _fill_probe gets (signal_close - fill_price)
    appended per ACTUAL fill when limit_atr > 0 -- lets a driver compute the average entry
    improvement in points. _signal_index_probe gets the signal bar index i at the same point.
    _mask_override replaces the combined round-57 rule mask (a knob must be on)."""
    quiet_pct = float(quiet_pct); stretch_max = float(stretch_max)
    rec_min = float(rec_min); vol_clock = float(vol_clock)
    session_knob_on = quiet_pct > 0 or stretch_max > 0 or vol_clock > 0
    rule_on = session_knob_on or rec_min > 0
    if session_knob_on and index is None:
        raise ValueError("ENGUQ SEL: quiet_pct / stretch_max / vol_clock need bar timestamps, but "
                         "no index was passed (quiet_pct=%g stretch_max=%g vol_clock=%g). Refusing "
                         "to run the rule silently OFF." % (quiet_pct, stretch_max, vol_clock))
    if _mask_override is not None and not rule_on:
        raise ValueError("ENGUQ SEL: _mask_override replaces a rule mask, but every rule knob is OFF")

    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    ix = _as_index(index, n) if index is not None else None
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

    # ── round 57 entry-selection rules: one boolean per bar, tested at the SIGNAL bar by the
    #    walk's own er_ok test. All knobs OFF -> rule_mask None -> er_ok untouched -> parity.
    if rule_on:
        if _mask_override is not None:
            rule_mask = np.asarray(_mask_override, dtype=bool)
            if rule_mask.shape != (n,):
                raise ValueError("ENGUQ SEL: _mask_override has shape %s for %d bars"
                                 % (rule_mask.shape, n))
        else:
            rule_mask = _rule_mask(h, l, c, volumes, ix, tr, tl_len,
                                   quiet_pct, stretch_max, rec_min, vol_clock)
        er_ok = rule_mask if er_ok is None else (er_ok & rule_mask)
    if vol_clock > 0:
        vol_mult = 0.0             # H-D REPLACES the 20-bar test (the walk tests vol_mult > 0)

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
    #    parity-tested against the loop below (tests/test_fastloop_parity.py,
    #    tests/test_enguq_sel_parity.py). Skipped whenever instrumentation is attached, and
    #    skipped entirely when the compiler is unavailable, in which case the interpreted loop
    #    below runs exactly as it always has.
    if (_fl is not None and _signal_probe is None and _fill_probe is None
            and _signal_index_probe is None
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
        if er_ok is not None and not er_ok[i]:      # efficiency gate AND the round-57 rule mask
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()
        if _signal_probe is not None:
            _signal_probe.append(1)
        if _signal_index_probe is not None:
            _signal_index_probe.append(i)

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

"""
TTMSQZ 3.0 ES30T — the ES30N neighbourhood with a DEEP-SQUEEZE SIZE TILT.

WHY THIS EXISTS (round 8, 2026-09-08; owner: "keep improving our best ttm model")
  Twelve one-change variants of the crown (run #299) were scanned alone and stacked as the
  book leg. Eleven were worse or flat. The one near miss was not a change to the trading
  rules at all — it was SIZE: take every trade the crown takes, but put 1.5 contracts on the
  ones entered while the verifying hourly squeeze is DEEP rather than merely on.

  Scan on the pinned window (2010-06-07..2026-06-30, ES 30m, 0.363 pts a round trip):
  188 of 359 trades qualify; alone the tilt beats the crown on profit factor (2.23 vs 2.12)
  and on the lockbox ($6,948 vs $4,992); stacked as three ES contracts on the ORB 234 +
  ENGU-Q 309 baseline it lifts annualised MAR 2.00 -> 2.09 at UNCHANGED whole-run drawdown
  ($34,903) with the book lockbox up 3%. That is +4.5% against a bar of +5%, so round 8
  crowned NOTHING and this file exists to settle it under the house gates instead.

WHAT "DEEP" MEANS, AND WHY IT IS NOT A FITTED KNOB
  The verification state is the ratio (bb_mult x stdev) / (kc_mult x ATR) of the hourly
  frame — below 1.0 is Carter's squeeze, which is exactly what run #299 already requires.
  "Deep" is that same ratio at or under 0.85, the house threshold `compression_sizes(...,
  thr=0.85)` in augur_engine/ml_keel.py has used since the KEEL overlay work (2026-09-06).
  It is A PRIORI, it is NOT searched here, and the multiplier is FIXED at 1.5 — the lesson
  of run #331, where an open multiplier let an in-sample-money search crown the most
  aggressive corner of its own fence and fail the drawdown clause.
  The ratio is also computed at FIXED length 20 / Bollinger 2.0 / Keltner 1.5 rather than
  from the searched knobs, so the meaning of "deep" cannot drift as the search moves.

WHAT IS SEARCHED: the same four knobs, over the same admissible set, as TTMSQZ_3_0_ES30N.py
  (run #299's file). Everything else is frozen in the wrapper. So this run answers exactly
  one question: does the crown's own neighbourhood, sized this way, hold up out of sample?

COST CONVENTION (the engine subtracts cost_pts ONCE per trade)
  A trade sized s returns `s*raw - (s-1)*cost`, so after the engine's single subtraction the
  trade is worth `s*(raw - cost)` — the extra half contract pays its own commission and
  slippage. The job MUST carry cost_pts 0.363 (ES) or the sizing is mispriced.

Engine = TTMSQZ_3_0.py, imported unchanged. Control = run #299 (TTMSQZ_3_0_ES30N.py), same
window, same master, same costs, same lockbox.
"""
import os
from importlib import util as _u

import numpy as np
import pandas as pd

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

# Exactly TTMSQZ_3_0_ES30N.py's frozen set: the four searched knobs (kc_mult, stop_atr,
# eod_cutoff, gate_len) are absent, so the searched values flow through untouched.
_FROZEN = {'length': 20, 'bb_mult': 2.0, 'min_sq_bars': 1, 'entry_fill': 'open',
           'exit_mode': 'fade', 'fade_bars': 1, 'gate_tf_min': 60, 'gate_mode': 'sq_on',
           'gate_fired_k': 3, 'gate_bars': 2, 'direction': 'both'}

# THE TILT — fixed, a priori, not searched.
_TILT_MULT = 1.5            # contracts on a deep-squeeze entry (1.0 otherwise)
_DEEP_THR = 0.85            # the house "deep compression" threshold (ml_keel.compression_sizes)
_TILT_TF_MIN = 60           # the verifying frame, in minutes
_TILT_LEN, _TILT_BB, _TILT_KC = 20, 2.0, 1.5    # fixed ratio definition (see docstring)
_COST_PTS = 0.363           # ES round trip in points — must match the job's cost_pts


def _deep_state(highs, lows, closes, day_id, index):
    """Boolean per base bar: is the last COMPLETE hourly bar's compression ratio <= _DEEP_THR?

    Same session-anchored construction as TTMSQZ_3_0._htf_gate's dial branch — base bars are
    grouped by minutes-since-session-open // 60, a group's state becomes readable on its last
    base bar's close, and bar u reads the latest group that has completed by u."""
    h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    did = np.asarray(day_id)
    idx = pd.DatetimeIndex(index)
    mins = idx.hour.values * 60 + idx.minute.values
    first_of_day = np.zeros(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        first_of_day[a:b] = mins[a]
        a = b
    bucket = (mins - first_of_day) // int(_TILT_TF_MIN)
    grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
    change = np.empty(n, bool); change[0] = True; change[1:] = grp[1:] != grp[:-1]
    gstart = np.flatnonzero(change)
    gend = np.append(gstart[1:], n) - 1
    hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
    ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
    cc = c[gend]
    s_ = pd.Series(cc)
    dev = s_.rolling(int(_TILT_LEN)).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(int(_TILT_LEN)).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((_TILT_BB * dev) / (_TILT_KC * atr)).to_numpy()
    warm = int(_TILT_LEN) * 2 + 5
    j = np.searchsorted(gend, np.arange(n), side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    r = np.where(ok, ratio[jj], np.nan)
    return np.isfinite(r) & (r <= float(_DEEP_THR))


def _rescore(trades):
    """Metrics from a sized trade list (the engine re-derives these again after costs)."""
    pnls = np.array([t[2] for t in trades], float)
    if not len(pnls):
        return None
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    return {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
        "trades": trades,
    }


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """Run #299's neighbourhood, with deep-squeeze entries sized 1.5.

    `index` is named explicitly because the engine only hands bar timestamps to a strategy
    that declares them by name, and both the verification frame and the tilt read the clock.
    An out-of-set configuration is REFUSED (None), never clamped."""
    if not _in_neighbourhood(kw):
        return None
    kw.update(_FROZEN)
    res = _t3.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           index=index, return_trades=True, **kw)
    if not res or not res.get("trades"):
        return res
    if index is None or day_id is None:
        return None          # no clock, no honest tilt
    deep = _deep_state(highs, lows, closes, day_id, index)
    n = len(deep)
    out = []
    for t in res["trades"]:
        eb = int(t[0])
        d = bool(deep[min(max(eb - 1, 0), n - 1)])      # the DECISION bar, one before the fill
        s = float(_TILT_MULT) if d else 1.0
        pnl = s * float(t[2]) - (s - 1.0) * float(_COST_PTS)
        out.append((eb, int(t[1]), pnl) + tuple(t[3:]))
    return _rescore(out)


# ── THE NEIGHBOURHOOD IS BINDING (same set as TTMSQZ_3_0_ES30N.py) ───────────
# Auto-Validate widens a strategy's declared min/max when the optimum sits near an edge.
# That is right for an open search and fatal for a fenced one (runs 290 and 293), so
# admissibility is enforced HERE, where nothing can widen it, and an out-of-set
# configuration is refused rather than clamped.
_ADMISSIBLE = {'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5],
               'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        v = kw[k]
        if not any(abs(float(v) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


squeeze_indicators = _t3.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 ES30T · ES 30m Carter neighbourhood + 1.5x on deep squeezes'
DESCRIPTION = ("Run #299's neighbourhood with one change that is not a trading rule: every trade is "
               "still taken, but the ones entered while the verifying hourly squeeze is DEEP (ratio "
               "at or under 0.85) are sized 1.5 instead of 1. The multiplier and the threshold are "
               "fixed a priori; only the same four knobs run #299 searched vary.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}

DEFAULT_PARAMS = {
    'kc_mult': {'default': 1.5, 'min': 1.25, 'max': 1.75, 'step': 0.25, 'type': 'float',
                'label': 'Keltner ATR multiplier',
                'tooltip': 'Pocket value 1.5; one step either side, as in run 299.'},
    'stop_atr': {'default': 1.5, 'min': 1.5, 'max': 2.5, 'step': 0.5, 'type': 'float',
                 'label': 'Protective stop, ATR multiples',
                 'tooltip': 'Run 299 chose 1.5; the set keeps 2.0 and 2.5.'},
    'eod_cutoff': {'default': 1, 'min': 1, 'max': 5, 'step': 2, 'type': 'int',
                   'label': 'No entries inside the last N bars of the session',
                   'tooltip': 'Run 299 chose 1; the set keeps 3 and 5.'},
    'gate_len': {'default': 20, 'min': 16, 'max': 24, 'step': 4, 'type': 'int',
                 'label': 'Verification squeeze length',
                 'tooltip': 'Length of the hourly squeeze that verifies each entry. Pocket value 20.'},
}

PARAM_GRID_PRESETS = {
    "Short  (ES 30m deep-squeeze tilt neighbourhood)": {
        'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5],
        'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]},
}

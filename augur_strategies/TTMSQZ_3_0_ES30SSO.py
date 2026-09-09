"""
TTMSQZ 3.0 ES30SSO — the book leg, sized up on the trade the whole edge lives in.

WHERE THIS CAME FROM, AND WHY IT IS NOT A FISHING TRIP
  Round 15b asked a mechanical question: the strategy blocks entries in the last bars of the session
  (`eod_cutoff`) but has nothing equivalent at the open, even though the first bars are the noisiest
  of the day. The expected answer was that filtering them would help. The answer was INVERTED, and
  by a distance: the 87 trades that enter on the session's first available bar average $805 against
  $115 for the other 270 — seven times the rest of the population, 24 percent of the trades — and
  blocking them removes $70,053 of a $101,017 leg.

  The shop's own preference is that a subset that good gets SIZED, never filtered. So this file puts
  1.5 contracts on it, exactly the shape and multiplier already validated for the deep-squeeze tilt.

WHAT "THE OPEN BAR" MEANS, precisely, because there is an off-by-one waiting here
  A fire is decided on a closed bar and filled at the NEXT bar's open, so no trade can ever enter on
  the session's very first bar — the first version of this measurement looked for ordinal 0 and found
  zero trades. The rule is the first bar an entry can occur on: ordinal 1, the 10:00 ET bar on a
  30-minute chart, whose fire was decided on the 09:30 bar's close. That is the overnight gap
  releasing into an hour that is still coiled, which is a coherent story rather than a found pattern.

THE MEASUREMENT (tools/ttmsqz_r15e_open_bar_tilt.py), on the leg the paper book carries, with the
pre-lockbox trades split 60/40 by time and the rule fixed before the split:

                                  discovery                 holdout                  lockbox
                              net    DD    MAR    $/ctr   net     DD    MAR      net    DD   LB PF
    book leg, unchanged     31,333  2,018  0.97    154   52,706  4,338  0.76   16,977  2,003  6.72
    1.5x on open-bar        41,600  1,923  1.35    184   72,123  5,330  0.84   22,321  2,003  8.52
    2.0x on open-bar        51,866  1,929  1.67    229   91,540  6,322  0.90   27,664  2,003 10.32
    flat 1.5x (leverage)    47,000  3,027  0.97    154   79,059  6,507  0.76   25,466  3,005  6.72

  The flat-1.5x row is the control that matters: scaling every trade cannot change annualised MAR,
  and it does not. The tilt DOES — 0.97 to 1.35 in discovery and 0.76 to 0.84 in the holdout — and it
  leaves the lockbox drawdown untouched at $2,003 while the flat version pushes it to $3,005. So this
  is not leverage wearing a rule as a costume. Permutation on the discovery half: +$399 a trade,
  p = 0.0000. The multiplier is fixed at 1.5 a priori rather than searched; 2.0 measures better on
  every column above and is deliberately NOT used, because a search that picks the biggest size is
  the exact failure runs #331 and #352 already produced.

  HONEST LIMIT: the rule was found by looking at these trades. The holdout and lockbox columns are
  the evidence, the discovery column is where it came from, and the lockbox holds 16 trades in total.
  This run exists because a scan is not evidence until the house gates have seen it.

HOW IT COMPOSES WITH THE DEEP-SQUEEZE TILT
  The two conditions are independent, so a trade can meet both, and the multipliers MULTIPLY: 1.0 for
  a plain trade, 1.5 for one or the other, 2.25 for both. That ladder is disclosed rather than capped,
  because a cap would be a new knob nobody has justified — but it does mean the whole-contract
  question from round 11 gets harder, and that belongs in the adoption decision, not in this run.

THE BAR, WRITTEN BEFORE THE RUN, against the book leg (run #353):
  (a) PASS, or WEAK on the overfit check alone;
  (b) lockbox net at least $16,977 AND lockbox profit factor at least 6.72;
  (c) whole-run annualised MAR at least 1.450, at a whole-run drawdown no more than 25 percent above
      its $4,338 — a wider drawdown clause than the last three bars used, and stated here as such,
      because this change ADDS SIZE and is expected to cost some drawdown. It must earn its risk in
      MAR rather than merely avoid drawdown.

Everything else is unchanged and imported from TTMSQZ_3_0_ES30SS.py rather than copied.
"""
import os
from importlib import util as _u

import numpy as np
import pandas as pd

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0_ES30SS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0_ES30SS.py"))
_ss = _u.module_from_spec(_sp); _sp.loader.exec_module(_ss)

_GATE_LEN = 20            # run #299's crowned value - frozen, as in ES30SS20
_OPEN_MULT = 1.5          # THE ONE CHANGE, fixed a priori
_OPEN_ORDINAL = 1         # the first bar an entry can occur on (see the docstring)


def _session_ordinal(day_id):
    """Each bar's position within its own session, 0 for the first."""
    did = np.asarray(day_id)
    out = np.zeros(len(did), int)
    a = 0
    while a < len(did):
        b = a
        while b < len(did) and did[b] == did[a]:
            b += 1
        out[a:b] = np.arange(b - a)
        a = b
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """The book leg with 1.5 contracts on entries that fill on the session's first available bar.

    The parent has already applied the deep-squeeze tilt and the engine's single cost subtraction is
    still to come, so this re-prices each trade the same way the parent does: a trade whose size goes
    from s to s*m returns `s*m*raw - (s*m - 1)*cost`, which the engine turns into `s*m*(raw - cost)`.
    Both factors are known at the decision bar - the session ordinal of the fill bar is a calendar
    fact, and the compression state comes from the last complete hourly group."""
    if not _ss._in_neighbourhood(kw):
        return None
    kw["gate_len"] = _GATE_LEN
    res = _ss.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           index=index, return_trades=True, **kw)
    if not res or not res.get("trades"):
        return res
    if day_id is None:
        return None
    ordinal = _session_ordinal(day_id)
    cost = float(_ss._COST_PTS)
    deep = _ss._deep_state(highs, lows, closes, day_id, index)
    nn = len(deep)
    out = []
    for t in res["trades"]:
        eb = int(t[0])
        if ordinal[eb] != _OPEN_ORDINAL:
            out.append(tuple(t))
            continue
        # undo the parent's pricing for this trade, then re-price at s * _OPEN_MULT
        s_parent = float(_ss._TILT_MULT) if bool(deep[min(max(eb - 1, 0), nn - 1)]) else 1.0
        raw = (float(t[2]) + (s_parent - 1.0) * cost) / s_parent
        s = s_parent * float(_OPEN_MULT)
        out.append((eb, int(t[1]), s * raw - (s - 1.0) * cost) + tuple(t[3:]))
    return _ss._rescore(out)


squeeze_indicators = _ss.squeeze_indicators
_ADMISSIBLE = {k: v for k, v in _ss._ADMISSIBLE.items() if k != "gate_len"}
_in_neighbourhood = _ss._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SSO - the book leg, 1.5x on the session open-bar entry'
DESCRIPTION = ("The leg the paper book carries, with 1.5 contracts on the trades that fill on the "
               "session's first available bar - the overnight gap releasing into an hour that is "
               "still coiled. Those 87 of 357 trades average 805 dollars against 115 for the rest.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SS.py"

DEFAULT_PARAMS = {k: v for k, v in _ss.DEFAULT_PARAMS.items() if k != "gate_len"}

PARAM_GRID_PRESETS = {
    "Short  (ES 30m structural stop, open-bar tilt)": {
        k: v for k, v in list(_ss.PARAM_GRID_PRESETS.values())[0].items() if k != "gate_len"},
}

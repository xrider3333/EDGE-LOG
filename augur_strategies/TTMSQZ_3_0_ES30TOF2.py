"""
TTMSQZ 3.0 ES30TOF2 - the HONEST STACK on the clean ATR engine (TTM round 19b, idea 2).

WHY THIS EXISTS (2026-09-30)
  The same-bar gap-stop bug (fixed b3242e77) inflated every structural-stop TTM leg; the ATR-stop
  engine (TTMSQZ_3_0.py, runs #299 / #340) was clean. Round 19b (tools/ttmsqz_r19b_atr_stack.py,
  prereg tools/TTM_R19_PREREG.txt) put the three validated changes on that clean engine together:
    1. deep-squeeze size tilt 1.5x (run #340, TTMSQZ_3_0_ES30T.py - reused here, not re-derived);
    2. open-bar size tilt 1.5x on entries that fill on the session's first available bar
       (ordinal 1, the #368 idea - TTMSQZ_3_0_ES30SSO.py's rule);
    3. leave after the SECOND fading momentum bar instead of the first (the #364 idea).
  On the ADJ master it beat its raw twin (#299 cell) in both stretches and the book's TTM #459 leg in
  walk-forward (ROC@$30k 24.6% vs 21.0%, Sortino 2.16 vs 1.91); it lost only to #459's 15-trade
  lockbox, which the owner set aside for TTM on 2026-09-29 (MANAGER inbox #22). Pre-registered
  validate bar: tools/TTM_R20_PREREG.txt addendum 3.

THE TWO TILTS MULTIPLY -> each trade is sized 1.0, 1.5 or 2.25 (per contract of the book weight).
  Both are known at the decision bar: the deep state reads the last COMPLETE hourly group at the
  fire bar (ES30T._deep_state), and the fill bar's session ordinal is a calendar fact.
COST CONVENTION (engine subtracts cost_pts ONCE per trade): a trade sized s returns
  s*raw - (s-1)*cost, which the engine turns into s*(raw - cost). The job MUST carry cost_pts 0.363.

WHAT IS SEARCHED: exactly run #299 / #340's four knobs over the same binding set (kc_mult, stop_atr,
  eod_cutoff, gate_len); fade_bars = 2 and both tilts are frozen. Out-of-set configs are REFUSED.
DATA: ES 30m RTH on the roll-corrected ADJ master (source db_adj_rth, pinned) - the squeeze reads
  across sessions, and TTM is flat at every close, so back-adjustment changes only indicator reads.
"""
import os
from importlib import util as _u

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_sp = _u.spec_from_file_location("TTMSQZ_3_0_ES30T", os.path.join(_HERE, "TTMSQZ_3_0_ES30T.py"))
_es30t = _u.module_from_spec(_sp); _sp.loader.exec_module(_es30t)
_t3 = _es30t._t3

_FROZEN = dict(_es30t._FROZEN, fade_bars=2)     # the #364 change; everything else = run #299
_DEEP_MULT = float(_es30t._TILT_MULT)             # 1.5, run #340
_OPEN_MULT = 1.5                                  # the #368 change, fixed a priori
_OPEN_ORDINAL = 1                                 # first bar an entry can fill on (fire on bar 0)
_COST_PTS = float(_es30t._COST_PTS)               # 0.363


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
    """Run #299's neighbourhood with fade-after-2 and the multiplied 1.0 / 1.5 / 2.25 size ladder."""
    if not _es30t._in_neighbourhood(kw):
        return None
    kw.update(_FROZEN)
    res = _t3.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           index=index, return_trades=True, **kw)
    if not res or not res.get("trades"):
        return res
    if index is None or day_id is None:
        return None                                  # no clock, no honest tilt
    deep = _es30t._deep_state(highs, lows, closes, day_id, index)
    ordinal = _session_ordinal(day_id)
    n = len(deep)
    out = []
    for t in res["trades"]:
        eb = int(t[0])
        s = _DEEP_MULT if bool(deep[min(max(eb - 1, 0), n - 1)]) else 1.0   # the DECISION bar
        if ordinal[min(eb, n - 1)] == _OPEN_ORDINAL:
            s *= _OPEN_MULT
        out.append((eb, int(t[1]), s * float(t[2]) - (s - 1.0) * _COST_PTS) + tuple(t[3:]))
    return _es30t._rescore(out)


squeeze_indicators = _t3.squeeze_indicators
_ADMISSIBLE = _es30t._ADMISSIBLE
_in_neighbourhood = _es30t._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30TOF2 - clean ATR engine + deep-squeeze and open-bar tilts + fade after 2'
DESCRIPTION = ("Run 299's ES 30m neighbourhood on the clean ATR-stop engine with three validated changes "
               "stacked: 1.5x on deep hourly squeezes, 1.5x on session-open entries (they multiply to a "
               "1.0 / 1.5 / 2.25 ladder) and an exit on the second fading bar. Only run 299's four knobs vary.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30T.py"

DEFAULT_PARAMS = dict(_es30t.DEFAULT_PARAMS)
PARAM_GRID_PRESETS = {
    "Short  (ES 30m honest stack neighbourhood, round 19b)": {
        'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5],
        'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]},
}

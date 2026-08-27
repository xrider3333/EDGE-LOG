"""
TTMSQZ 3.0 R5NQ5 — round-5 NEIGHBOURHOOD: the compression dial, on NQ 5m range-break.

WHY THIS SHAPE
  Rounds 1-4 established the family's one real edge: take a short-timeframe squeeze fire
  ONLY while a higher timeframe is still compressed. Three pinned validates of it all PASSED
  their lockbox (runs 279/280/281) and all failed the SAME single gate - sample size. They
  trade 13 to 25 times a year.

  Round 5 (tools/ttmsqz_round5_depth.py) attacked exactly that. Carter's squeeze is binary -
  Bollinger band inside Keltner channel - which is the ratio of their widths crossing 1.0.
  Exposing that ratio as a dial, and shortening the verification lookback, multiplies the
  trade count while holding profit factor and the lockbox: 74 cells cleared profit factor
  1.15 with a positive lockbox AND 200-plus trades, where the round-4 pocket had none.

  This file does NOT crown the best of those 74 - that would be picking the maximum of a
  hand-run scan, which is how every free search in this family overfit. It declares a small
  PRE-REGISTERED neighbourhood around the promising region (54 combinations) and lets
  Auto-Validate choose inside it with its own walk-forward, overfit and lockbox gates.
  Mechanism, entry, exit and the verification rule are frozen in code and cannot be
  overridden by the search.

Local pre-read of the neighbourhood centre (conservative fills, 2010-06-07..2026-06-30,
lockbox = last 12 months): 2,200 trades / $156,881 / PF 1.23 / DD $39,845 / MAR 3.94 / lockbox +$8,848 - about 140 trades a year, where the round-4 pocket managed 20.
Robustness of that centre: 9 of 13 single-knob neighbours keep profit factor 1.15 or better with a positive lockbox; two neighbours (base length 16, Keltner 1.75) are markedly BETTER than the centre, which is why the choice is left to the validate rather than made by hand.

Engine = TTMSQZ_3_0.py, imported unchanged. Frozen at: Bollinger 2.0, minimum squeeze 1 bar, stop entry at the squeeze range edge, ride exit, 2 ATR stop, no entries in the last 3 bars, verification timeframe 60 minutes, verification rule squeeze-on, direction both.
"""
import os
from importlib import util as _u
_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

_FROZEN = {'bb_mult': 2.0, 'min_sq_bars': 1, 'entry_fill': 'range_break', 'exit_mode': 'ride', 'fade_bars': 1, 'stop_atr': 2.0, 'eod_cutoff': 3, 'gate_tf_min': 60, 'gate_mode': 'sq_on', 'gate_bars': 12, 'gate_fired_k': 3, 'direction': 'both'}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None, **kw):
    """The searched knobs arrive in kw; the mechanism is frozen and cannot be overridden.

    `index` is named explicitly because the engine only hands bar timestamps to a strategy
    that declares them, and the verification frame is built on the wall clock whenever they
    are available."""
    if not _in_neighbourhood(kw):
        return None          # outside the pre-registered neighbourhood - refused, not clamped
    kw.update(_FROZEN)
    return _t3.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                            index=index, **kw)


# ── THE NEIGHBOURHOOD IS BINDING (added 2026-08-23 after run 290) ─────────────
# Auto-Validate widens a strategy's declared min/max when the optimum sits near an edge
# (its #26/#30 range-widening feature). That is helpful for an open search and fatal for a
# PRE-REGISTERED one: run 290 was handed this neighbourhood, the ranges were widened under
# it, and the search rode them out to base length 8 and a threshold of 1.45 - well outside
# what was declared - landing on an overfit configuration (overfit probability 0.82) that
# lost 51,596 dollars in the lockbox.
#
# So admissibility is enforced HERE, where nothing can widen it: a configuration outside the
# declared set is not silently clamped (that would misreport what ran) - it is REFUSED, the
# same way a strategy refuses a window with too little history. The search sees it as an
# invalid configuration and cannot crown it.
_ADMISSIBLE = {'gate_len': [14, 16, 20], 'gate_ratio': [1.0, 1.15, 1.3], 'length': [16, 20, 24], 'kc_mult': [1.5, 1.75]}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        v = kw[k]
        if not any(abs(float(v) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


squeeze_indicators = _t3.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 R5NQ5 · NQ 5m range-break, compression dial'
DESCRIPTION = ("Round-5 neighbourhood: a stop entry at the squeeze range edge on 5-minute NQ, held to the close with only the protective stop. The verification timeframe must be compressed "
               "at entry, with the compression threshold itself one of the searched knobs.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {'gate_len': {'default': 16, 'min': 14, 'max': 20, 'step': 2, 'type': 'int', 'label': 'Verification squeeze length', 'tooltip': 'How far back the higher timeframe measures its own compression. Round 5 found short lookbacks admit far more trades; 14, 16 and 20 all held.'}, 'gate_ratio': {'default': 1.15, 'min': 1.0, 'max': 1.3, 'step': 0.15, 'type': 'float', 'label': 'Compression threshold on the verification timeframe', 'tooltip': "1.00 is Carter's published squeeze exactly. Above it admits nearly-coiled bars, which is what lifts the trade count."}, 'length': {'default': 20, 'min': 16, 'max': 24, 'step': 4, 'type': 'int', 'label': 'Base squeeze length', 'tooltip': 'Carter default 20, on the traded timeframe.'}, 'kc_mult': {'default': 1.5, 'min': 1.5, 'max': 1.75, 'step': 0.25, 'type': 'float', 'label': 'Keltner ATR multiplier (traded timeframe)', 'tooltip': 'Carter default 1.5. 1.75 loosens the traded-timeframe squeeze definition.'}}

PARAM_GRID_PRESETS = {"Short  (NQ 5m range-break neighbourhood)": {'gate_len': [14, 16, 20], 'gate_ratio': [1.0, 1.15, 1.3], 'length': [16, 20, 24], 'kc_mult': [1.5, 1.75]}}

"""
TTMSQZ 3.0 NQ15BN — NEIGHBOURHOOD validate target for the round-4 pocket (NQ 15m range-break + ride).

WHY THIS EXISTS (owner question 2026-08-23: "why are these all pinned?")
  Free discovery overfits this family every time (runs 268/269/270/272/277), so the pocket
  cells were first validated PINNED. But a pinned single-config validate declares 14 knobs
  while searching none, so the house sample gate divides trades by 14 and fails on
  arithmetic (run 279: 17.3 trades per knob against a floor of 30) — and the surfaces that
  need MORE THAN ONE configuration (overfit probability, the neighbourhood map, the plateau
  read, the deflated Sharpe) come back empty.

  This file is the middle road: it declares ONLY the four knobs whose neighbours were
  measured robust (audit workflow 2026-08-23: all 13 single-knob neighbours of this cell
  keep profit factor 1.22+ with a positive lockbox), each over a TIGHT grid centred on the
  pocket. Every other knob is frozen at the pocket value by the engine defaults below, so
  the search cannot wander off the cell — but the validate now has a real configuration
  space to measure overfit against, and the trades-per-knob arithmetic becomes honest.

Engine = TTMSQZ_3_0.py, imported unchanged (conservative same-bar stop, audit 2026-08-23).
Verification frame pinned to 4 base bars per hourly check (the grid code path does not hand strategies bar timestamps; the bar-count frame is bit-identical to the clock frame here).
Frozen at: length 20, Bollinger 2.0, minimum squeeze 1 bar, stop entry at the squeeze range edge, ride exit, verification timeframe 60 minutes, verification rule squeeze-on, direction both.
"""
import os
from importlib import util as _u
_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

_FROZEN = {'length': 20, 'bb_mult': 2.0, 'min_sq_bars': 1, 'entry_fill': 'range_break', 'exit_mode': 'ride', 'fade_bars': 1, 'gate_tf_min': 60, 'gate_mode': 'sq_on', 'gate_fired_k': 3, 'gate_bars': 4, 'direction': 'both'}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None, **kw):
    """Neighbourhood wrapper: the searched knobs arrive in kw, everything else is frozen at
    the pocket configuration (kw never overrides _FROZEN), and anything outside the declared
    set is refused.

    `index` is named explicitly because the engine only hands bar timestamps to a strategy
    that declares them by name, and the verification frame prefers the wall clock."""
    if not _in_neighbourhood(kw):
        return None          # outside the pre-registered neighbourhood - refused, not clamped
    kw.update(_FROZEN)
    return _t3.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                            index=index, **kw)


# ── THE NEIGHBOURHOOD IS BINDING (added 2026-08-23 after runs 290 and 293) ────
# Auto-Validate widens a strategy's declared min/max when the optimum sits near an edge (its
# #26/#30 range-widening feature). That is right for an open search and fatal for a fenced
# one. Run 293 was handed this neighbourhood and left it: gate length 8 against a declared
# floor of 16, Keltner 2.25 against a declared ceiling of 1.75, and an entry cutoff of MINUS
# ONE - a value with no meaning at all, and below the floor of zero the engine strategy
# itself declares. It crowned that and lost 60,094 dollars in the lockbox.
#
# Admissibility is therefore enforced HERE, where nothing can widen it. An out-of-set
# configuration is REFUSED, not clamped: clamping would run one thing and report another.
_ADMISSIBLE = {'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5], 'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        v = kw[k]
        if not any(abs(float(v) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


squeeze_indicators = _t3.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 NQ15BN · NQ 15m range-break + ride neighbourhood (60m squeeze-on verified)'
DESCRIPTION = ("Round-4 pocket with a tight neighbourhood around it: Stop entry at the squeeze range edge held to the close on 15-minute NQ, verified by the hourly squeeze being compressed. Only four "
               "knobs vary, each one step either side of the pocket value; the mechanism, "
               "the entry style, the exit and the 60-minute verification are frozen.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "15m"}

DEFAULT_PARAMS = {'kc_mult': {'default': 1.5, 'min': 1.25, 'max': 1.75, 'step': 0.25, 'type': 'float', 'label': 'Keltner ATR multiplier', 'tooltip': 'Pocket value 1.5; one step either side. Both neighbours held in the robustness sweep.'}, 'stop_atr': {'default': 2.0, 'min': 1.5, 'max': 2.5, 'step': 0.5, 'type': 'float', 'label': 'Protective stop, ATR multiples', 'tooltip': 'Pocket value 2.0; both neighbours held in the robustness sweep.'}, 'eod_cutoff': {'default': 3, 'min': 1, 'max': 5, 'step': 2, 'type': 'int', 'label': 'No entries inside the last N bars of the session', 'tooltip': 'Pocket value 3; both neighbours held in the robustness sweep.'}, 'gate_len': {'default': 20, 'min': 16, 'max': 24, 'step': 4, 'type': 'int', 'label': 'Verification squeeze length', 'tooltip': 'Length of the hourly squeeze that verifies each entry. Pocket value 20.'}}

PARAM_GRID_PRESETS = {
    "Short  (NQ 15m range-break + ride neighbourhood)": {'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5], 'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]},
}

"""
NOISE 1.1 SBS+V90 x HOURLY-COMPRESSION SIZE TILT, SIZE FIXED AT 1.5 — the second fenced validate.

WHY A SECOND RUN
  Run #331 put the size tilt through Auto-Validate with the size itself in the fence (1.5 or 2)
  and PASSED every house gate - walk-forward 8 of 8, overfit probability 0.19, lockbox 101,628
  dollars at profit factor 1.65. It did NOT clear the bar written down before it ran: the search
  crowns on in-sample money, every fenced cell trades the IDENTICAL list and differs only in
  size, so in-sample money is monotone in size and the search crowned the 2x corner - whose
  lockbox drawdown sat 31% above raw against a 25% cap. Fourteen of the sixteen cells cleared
  every clause; every 1.5x cell did. The owner asked for the 1.5x run.

  This file is NOISE_1_1_SBS_V90_CT.py with the size frozen at 1.5 - the size already running
  in the paper forward test as NOISE_SBS_V90_C15 - so the search can only choose WHICH hourly
  check verifies the trade, never how much to lever it. Eight cells, pre-registered.

COST CONVENTION, STATE, LEGITIMACY, FENCE: identical to the CT file, by import (see its
docstring). The job MUST carry cost_pts = 0.533.

LOCAL PRE-READ (pinned window, house costs; every cell already clears the bar below):
  60/20/1.00  $457,391  PF 1.45  DD $17,251  MAR 1.65 | LB $70,738  PF 1.40  DD $17,251   (= C15)
  60/20/1.15  $475,589  PF 1.45  DD $17,251  MAR 1.72 | LB $69,440  PF 1.38  DD $17,251
  30/16/1.15  $513,656  PF 1.45  DD $19,991  MAR 1.60 | LB $74,743  PF 1.38  DD $18,147
  raw leg     $395,169  PF 1.41  DD $18,425  MAR 1.34 | LB $60,001  PF 1.36  DD $16,125

PRE-REGISTERED BAR (unchanged from run 331, judged on the run doc, never re-cut)
  verdict PASS, or WEAK where the overfit check is the ONLY failing gate; AND lockbox >= the raw
  leg 60,001 dollars at a lockbox drawdown no more than 25% above raw 16,125; AND annualised
  MAR >= raw 1.34.
"""
import importlib.util as _ilu
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ct_for_ct15", _os.path.join(_HERE, "NOISE_1_1_SBS_V90_CT.py"))
_ct = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_ct)

STRATEGY_NAME = 'NOISE 1.1 SBS+V90 x hourly-compression size tilt, fixed 1.5x'
DESCRIPTION = ("The NOISE paper leg, core frozen as deployed, every trade kept; trades decided "
               "while the higher-timeframe squeeze was compressed are sized 1.5 contracts, the "
               "rest one. The size is fixed; only the three gate knobs vary, over a fenced set.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_SBS_V90.py"

_TILT = 1.5

DEFAULT_PARAMS = {k: dict(v) for k, v in _ct.DEFAULT_PARAMS.items() if k != "tilt_mult"}

_ADMISSIBLE = {"gate_tf_min": [30, 60], "gate_len": [16, 20], "gate_ratio": [1.0, 1.15]}
PARAM_GRID_PRESETS = {"Short  (the fenced 8-cell gate neighbourhood, size fixed 1.5)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k in kw and not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_tf_min=60, gate_len=20, gate_ratio=1.0, return_trades=False, **kw):
    if not _in_neighbourhood(dict(gate_tf_min=gate_tf_min, gate_len=gate_len, gate_ratio=gate_ratio)):
        return None          # outside the pre-registered set - refused, never clamped
    kw.pop("tilt_mult", None)   # the size is not a knob here
    return _ct.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                            gate_tf_min=gate_tf_min, gate_len=gate_len, gate_ratio=gate_ratio,
                            tilt_mult=_TILT, return_trades=return_trades)

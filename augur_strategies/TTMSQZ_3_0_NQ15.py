"""
TTMSQZ 3.0 NQ15 — PINNED single-config validate target: the round-4 NQ 15m Carter entry cell.

Free discovery overfits (runs 268-272, 277 all crowned wanderers that lost their lockbox),
so the round-4 pocket cells are validated PINNED: every knob collapsed to the cell's exact
configuration. Engine and semantics = TTMSQZ_3_0.py, imported unchanged (conservative
same-bar stop convention, audit 2026-08-23).

Local pre-read (tools/ttmsqz_round4_mtf.py, conservative fills, 2010-06-07..2026-06-30,
LB = last 12 months): 424 trades / $62,461 / PF 1.69 / DD $6,385 / MAR 9.78 / LB +$10,896 (PF 1.73) / 11-of-17 years.
Robustness: a ridge, not a plateau - collapses when the HOURLY gate is retuned (gate length 16 or Keltner 1.25 kill it); the traded-timeframe knobs are stable.
"""
import os
from importlib import util as _u
_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

run_backtest = _t3.run_backtest

STRATEGY_NAME = 'TTMSQZ 3.0 NQ15 · pinned NQ 15m Carter entry (60m squeeze-on verified)'
DESCRIPTION = ("Pinned round-4 pocket: Carter entry with the momentum-fade exit on 15-minute NQ. Every knob frozen; the 60-minute squeeze "
               "must be compressed at entry (last-completed-bar causal).")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "15m"}

_P = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
          exit_mode="fade", fade_bars=1, stop_atr=2.0, eod_cutoff=3,
          gate_tf_min=60, gate_mode="sq_on", gate_len=20, gate_fired_k=3, direction="both")

def _pin(k, v):
    if isinstance(v, str):
        return {"default": v, "type": "str", "options": [v], "label": k, "tooltip": "pinned"}
    if isinstance(v, float):
        return {"default": v, "min": v, "max": v, "step": 1.0, "type": "float", "label": k, "tooltip": "pinned"}
    return {"default": v, "min": v, "max": v, "step": 1, "type": "int", "label": k, "tooltip": "pinned"}

DEFAULT_PARAMS = {k: _pin(k, v) for k, v in _P.items()}
PARAM_GRID_PRESETS = {"Short  (pinned NQ 15m Carter entry)": {k: [v] for k, v in _P.items()}}

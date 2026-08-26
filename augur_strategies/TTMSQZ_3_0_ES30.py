"""
TTMSQZ 3.0 ES30 — PINNED single-config validate target: the round-4 ES 30m Carter entry cell.

Free discovery overfits (runs 268-272, 277 all crowned wanderers that lost their lockbox),
so the round-4 pocket cells are validated PINNED: every knob collapsed to the cell's exact
configuration. Engine and semantics = TTMSQZ_3_0.py, imported unchanged (conservative
same-bar stop convention, audit 2026-08-23).

Local pre-read (tools/ttmsqz_round4_mtf.py, conservative fills, 2010-06-07..2026-06-30,
LB = last 12 months): 314 trades / $45,790 / PF 2.06 / DD $3,896 / MAR 11.75 / LB +$5,140 (PF 2.31) / 14-of-17 years.
Robustness: a genuine plateau - all 13 single-knob neighbors keep PF >= 1.22 and a positive lockbox (audit workflow 2026-08-23).
"""
import os
from importlib import util as _u
_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

run_backtest = _t3.run_backtest

STRATEGY_NAME = 'TTMSQZ 3.0 ES30 · pinned ES 30m Carter entry (60m squeeze-on verified)'
DESCRIPTION = ("Pinned round-4 pocket: Carter entry (market at next open on the fire) with the momentum-fade exit on 30-minute ES. Every knob frozen; the 60-minute squeeze "
               "must be compressed at entry (last-completed-bar causal).")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}

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
PARAM_GRID_PRESETS = {"Short  (pinned ES 30m Carter entry)": {k: [v] for k, v in _P.items()}}

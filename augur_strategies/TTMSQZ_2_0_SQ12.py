"""
TTMSQZ 2.0 SQ12 — PINNED single-config validate target: studies row 424 (ES 30m Min 12-bar squeeze).

Round-2 pocket cell frozen for a fair Auto-Validate: free discovery wanders off the pocket
(run 272 crowned a 102-trade overfit on NQ 60m instead of testing it), so this file collapses
every knob to the row's exact configuration — the search space IS the one point. Engine and
semantics = TTMSQZ_2_0.py, imported unchanged.

Local pre-read (tools/ttmsqz_round2.py, ES 30m RTH 2010-06-07..2026-06-30, LB last 12 mo):
177 trades / $21,855 / PF 1.87 / DD $3,121 / MAR 7.00 / LB +$7,555 (PF 18.3) / 14-of-17 years.
"""
import os
from importlib import util as _u
_sp = _u.spec_from_file_location(
    "TTMSQZ_2_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_2_0.py"))
_t2 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t2)

run_backtest = _t2.run_backtest
squeeze_indicators = _t2.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 2.0 SQ12 · pinned ES 30m twelve-bar squeeze (momentum-fade exit)'
DESCRIPTION = ("Pinned round-2 pocket: only squeeze fires after 12+ bars of compression are "
               "traded, Carter direction, next-open entry, momentum-fade exit, 2 ATR stop, flat at "
               "the close. Studies row 424; every knob frozen.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}

_P = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=12, entry_dir="mom",
          entry_fill="open", confirm_bars=0, gate="none", exit_mode="fade",
          fade_bars=1, target_mult=1.0, stop_atr=2.0, eod_cutoff=3, direction="both")

def _pin(k, v):
    if isinstance(v, str):
        return {"default": v, "type": "str", "options": [v], "label": k, "tooltip": "pinned"}
    if isinstance(v, float):
        return {"default": v, "min": v, "max": v, "step": 1.0, "type": "float", "label": k, "tooltip": "pinned"}
    return {"default": v, "min": v, "max": v, "step": 1, "type": "int", "label": k, "tooltip": "pinned"}

DEFAULT_PARAMS = {k: _pin(k, v) for k, v in _P.items()}
PARAM_GRID_PRESETS = {"Short  (pinned row 424)": {k: [v] for k, v in _P.items()}}

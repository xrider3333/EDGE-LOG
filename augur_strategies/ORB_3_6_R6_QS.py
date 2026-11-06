"""
ORB 3.6 R6 + QUIET-OR STOP (risk scout r1 cell B7, MANAGER 11-04; gauntlet 11-06).
Prereg: C:/EdgeLog/manager/prereg/PREREG_orb314_quiet_stop_gauntlet_2026-11-06.md.

WHAT THIS IS
  ORB_3_6_R6.py (the #314 file: its five crown knobs keep their own validate ranges) plus two knobs the core loop has
  no hook for. The core's source (ORB_3_6.py) is patched at import at three anchors, each asserted to occur the stated
  number of times, so the loop is the live loop and quiet_lo = 1.0 is #314 trade for trade (parity gate in the prereg).

KNOBS
  quiet_q   OR width / daily ATR(14) below which the stop tightens. Daily ATR(14) = the mean session range (high - low)
            of the 14 PRIOR sessions, as the scout's orb_sim.py defines it: causal, nothing from today.
  quiet_lo  stop multiplier on quiet-OR days: risk = stop_frac x range x quiet_lo. 1.0 = off. The target and the
            breakeven arm are in units of that (tightened) risk, exactly as the scout's B7 cell scored them.
  A session with fewer than 14 prior sessions has no ATR and is never scaled.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os
import types as _types

_HERE = _os.path.dirname(_os.path.abspath(__file__))

_sp = _ilu.spec_from_file_location("_orb36_r6_for_qs", _os.path.join(_HERE, "ORB_3_6_R6.py"))
_r6 = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_r6)

_PATCHES = [
    # 1. signature: two knobs before the live-only flag (once)
    ("    flat_eod: bool = True, skip_holidays: bool = True,\n    session_in_progress: bool = False,\n",
     "    flat_eod: bool = True, skip_holidays: bool = True,\n    quiet_q: float = 0.15, quiet_lo: float = 1.0,\n"
     "    session_in_progress: bool = False,\n", 1),
    # 2. causal daily ATR(14) per session start, built once before the walk (once)
    ("    pnl_list, trade_log = [], []\n",
     "    pnl_list, trade_log = [], []\n"
     "    _qs_datr = {}\n"
     "    if quiet_lo < 1.0:\n"
     "        _qs_rng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)\n"
     "        for _si, (a, b) in enumerate(_sess_bounds):\n"
     "            if _si >= 14:\n"
     "                _qs_datr[a] = float(_qs_rng[_si - 14:_si].mean())\n", 1),
    # 3. the session's scale, right after the opening range is known (once)
    ("            rng   = or_hi - or_lo\n",
     "            rng   = or_hi - or_lo\n"
     "            _qs = 1.0\n"
     "            if quiet_lo < 1.0:\n"
     "                _qs_d = _qs_datr.get(i)\n"
     "                if _qs_d is not None and _qs_d > 0 and rng / _qs_d < quiet_q:\n"
     "                    _qs = quiet_lo\n", 1),
    # 4. the stop, long and short (twice)
    ("                            risk  = stop_frac * rng\n",
     "                            risk  = stop_frac * rng * _qs\n", 2),
]


def _patched_core():
    src = open(_os.path.join(_HERE, "ORB_3_6.py"), encoding="utf-8").read().replace("\r\n", "\n")
    for old, new, cnt in _PATCHES:
        assert src.count(old) == cnt, "ORB_3_6.py anchor moved (%d, want %d): %r" % (src.count(old), cnt, old[:60])
        src = src.replace(old, new)
    src = src.split('\nif __name__ == "__main__"')[0]
    m = _types.ModuleType("_orb36_core_qs")
    m.__file__ = _os.path.join(_HERE, "ORB_3_6.py")
    exec(compile(src, m.__file__, "exec"), m.__dict__)
    return m


_core = _patched_core()

STRATEGY_NAME = "ORB 3.6 R6 (#314) + quiet-OR stop"
DESCRIPTION = ("ORB #314's file with a tighter stop on days whose opening range is small against the 14-session daily "
               "ATR (risk scout B7). quiet_lo 1.0 = #314 exactly; both knobs co-tuned next to the crown's ranges.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_R6.py"

DEFAULT_PARAMS = dict(_r6.DEFAULT_PARAMS)
DEFAULT_PARAMS.update({
    "quiet_q":  {"default": 0.15, "min": 0.10, "max": 0.25, "step": 0.05, "type": "float",
                 "label": "OR / daily-ATR(14) below which the stop tightens"},
    "quiet_lo": {"default": 0.60, "min": 0.50, "max": 1.00, "step": 0.10, "type": "float",
                 "label": "Stop multiplier on quiet-OR days (1.0 = off = #314)"},
})

PARAM_GRID_PRESETS = {"Short  (scout B7 cells)": {"quiet_q": [0.15, 0.20], "quiet_lo": [0.6, 1.0]}}

run_backtest = _core.run_backtest

"""
NOISE 1.8 CT304 + CHURN KNOBS -- MANAGER #278 (owner 11-04: 23 one-bar round trips on Webull paper).

WHAT THIS IS
  Run #382 (NOISE_1_8_CT304.py) with three entry / exit knobs the core loop has no hook for. The core's own source
  (NOISE_1_0.py) is patched at import at exactly four anchors, each asserted to occur once, so the loop is the live
  loop and every knob at its default is #382 exactly.

KNOBS
  max_entries      0 = off; else no new entry after the Nth entry of the session.
  reentry_confirm  0 = off; N = an entry after the session's first needs its last N closes (the signal bar and the N-1
                   before it) on the trade's side of session VWAP (long: close > VWAP). N = 1 is r1/r2's 'confirm' cell.
                   Without it a close past the band but through VWAP fills next bar and exits the bar after: the one-bar
                   churn. Ranged 0..3 for the gauntlet (PREREG_noise382_reentry_confirm_gauntlet_2026-11-06.md).
  vwap_buf_k       0 = off; else the VWAP exit needs the close k x ATR past VWAP. ATR = mean true range of the 14 closed
                   5m bars up to and including the signal bar (causal).
  entry_vwap       False = off; True = EVERY entry needs its signal close on the trade's side of session VWAP (r2, MANAGER #168).
  exit_closes      1 = today's exit (first close across VWAP); N = N consecutive closes across VWAP before the exit queues.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os
import types as _types

_HERE = _os.path.dirname(_os.path.abspath(__file__))

_sp = _ilu.spec_from_file_location("_noise_ct304_for_churn", _os.path.join(_HERE, "NOISE_1_8_CT304.py"))
_ct = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_ct)

_PATCHES = [
    ("    return_levels: bool = False,\n):\n    o = np.asarray(opens, float)",
     "    return_levels: bool = False,\n    max_entries: int = 0, reentry_confirm: int = 0, vwap_buf_k: float = 0.0,\n"
     "    entry_vwap: bool = False, exit_closes: int = 1,\n"
     "):\n    o = np.asarray(opens, float)"),
    ("    pnl_list, trade_log = [], []\n",
     "    pnl_list, trade_log = [], []\n"
     "    _tr = np.maximum(h - l, np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]]))\n"
     "    _atr5 = np.convolve(_tr, np.ones(14) / 14.0)[:n] if vwap_buf_k else None\n"),
    ("        pos = 0; entry_px = 0.0; entry_k = -1\n",
     "        pos = 0; entry_px = 0.0; entry_k = -1; n_entries = 0; _xs = 0\n"),
    ("                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0\n",
     "                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0; n_entries += 1; _xs = 0\n"),
    ("                    if pos > 0 and sc[k] < VWAP[k]:\n                        trig = True\n"
     "                    elif pos < 0 and sc[k] > VWAP[k]:\n",
     "                    _b = vwap_buf_k * _atr5[a + k] if vwap_buf_k else 0.0\n"
     "                    if pos > 0 and sc[k] < VWAP[k] - _b:\n                        trig = True\n"
     "                    elif pos < 0 and sc[k] > VWAP[k] + _b:\n"),
    ("                    if confirm_bars > 1:\n                        long_trig = long_trig and streak_long",
     "                    if max_entries and n_entries >= max_entries:\n"
     "                        long_trig = short_trig = False\n"
     "                    if reentry_confirm and n_entries >= 1 and VWAP is not None:\n"
     "                        _rc = range(max(0, k - int(reentry_confirm) + 1), k + 1)\n"
     "                        long_trig = long_trig and all(sc[_j] > VWAP[_j] for _j in _rc)\n"
     "                        short_trig = short_trig and all(sc[_j] < VWAP[_j] for _j in _rc)\n"
     "                    if entry_vwap and VWAP is not None:\n"
     "                        long_trig = long_trig and sc[k] > VWAP[k]\n"
     "                        short_trig = short_trig and sc[k] < VWAP[k]\n"
     "                    if confirm_bars > 1:\n                        long_trig = long_trig and streak_long"),
    ("                if trig:\n                    if _dl is not None:\n                        if exit_mode == \"vwap\":\n",
     "                if exit_closes > 1 and exit_mode == \"vwap\":\n"
     "                    _xs = _xs + 1 if trig else 0\n"
     "                    trig = trig and _xs >= exit_closes\n"
     "                if trig:\n                    if _dl is not None:\n                        if exit_mode == \"vwap\":\n"),
]


def _patched_core():
    src = open(_os.path.join(_HERE, "NOISE_1_0.py"), encoding="utf-8").read().replace("\r\n", "\n")
    for old, new in _PATCHES:
        assert src.count(old) == 1, "NOISE_1_0.py anchor moved: %r" % old[:60]
        src = src.replace(old, new)
    src = src.split('\nif __name__ == "__main__"')[0]
    m = _types.ModuleType("_noise_core_churn")
    m.__file__ = _os.path.join(_HERE, "NOISE_1_0.py")
    exec(compile(src, m.__file__, "exec"), m.__dict__)
    return m


_core = _patched_core()
_CHURN_KEYS = ("max_entries", "reentry_confirm", "vwap_buf_k", "entry_vwap", "exit_closes")

STRATEGY_NAME = "NOISE 1.8 CT304 (#382) + churn knobs"
DESCRIPTION = "Run #382 with an entries-per-session cap, a re-entry VWAP confirm and a VWAP exit buffer; all off = #382."
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304.py"
REQUIRED_LOOKBACK_SESSIONS = _ct.REQUIRED_LOOKBACK_SESSIONS
_COST_PTS = _ct._COST_PTS
_CROWN = {"gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15, "tilt_mult": 2.0}   # run #382 champion

# GAUNTLET (11-06): the parent's four crown knobs ride along with #382's own validate ranges so the 900-trial search
# co-tunes the churn knob next to them (tools/gauntlet_queue.py, scope C3). Defaults = the #382 champion (_CROWN).
DEFAULT_PARAMS = {k: dict(_ct.DEFAULT_PARAMS[k], default=v) for k, v in _CROWN.items()}
DEFAULT_PARAMS.update({
    "max_entries": {"default": 0, "min": 0, "max": 3, "step": 1, "type": "int", "label": "Entries per session cap (0 = off)"},
    "reentry_confirm": {"default": 0, "min": 0, "max": 3, "step": 1, "type": "int", "label": "Re-entry needs the last N closes on the trade's side of VWAP (0 = off)"},
    "vwap_buf_k": {"default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float", "label": "VWAP exit buffer, x 5m ATR"},
    "entry_vwap": {"default": False, "type": "bool", "label": "Every entry needs close on the trade's side of VWAP"},
    "exit_closes": {"default": 1, "min": 1, "max": 3, "step": 1, "type": "int", "label": "Consecutive closes across VWAP before exit"},
})
PARAM_GRID_PRESETS = {"Short  (#278 prereg cells)": {"max_entries": [0, 1, 2, 3], "reentry_confirm": [0, 1],
                                                     "vwap_buf_k": [0.0, 0.1, 0.25, 0.5]}}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 max_entries=0, reentry_confirm=0, vwap_buf_k=0.0, entry_vwap=False, exit_closes=1, return_trades=False, return_levels=False, **kw):
    churn = dict(max_entries=int(max_entries), reentry_confirm=int(reentry_confirm), vwap_buf_k=float(vwap_buf_k),
                 entry_vwap=bool(entry_vwap), exit_closes=int(exit_closes))
    inner = _ct._base.run_backtest                       # NBHD -> NOISE_1_0
    g = inner.__globals__
    held = g["_base"]

    class _Core:                                          # NBHD filters kwargs by the core's signature: bind the knobs here
        def __getattr__(self, k):
            return getattr(_core, k)

        @staticmethod
        def run_backtest(*a, **k):
            return _core.run_backtest(*a, **dict(k, **churn))
    g["_base"] = _Core()
    try:
        return _ct.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                                return_trades=return_trades, return_levels=return_levels, **dict(_CROWN, **kw))
    finally:
        g["_base"] = held

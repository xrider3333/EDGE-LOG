# AUGUR-SOURCE: claude-review
"""DISC OPENLONGS 1.0 - the owner's three long setups (CBU, EBU, ENGU) taken only in the opening window.

Provenance: w132 alpha hunt (owner rule 11-14), DISC lane leg "J4". Harness
C:/EdgeLog/_anatomy_cache/w132_disc/journal_ideas.py; parity script parity_j4.py next to it.
Journal finding behind it (setups/ journals, 09-24): CBU at the open +0.33 R vs +0.03 R later, ENGU +0.28 R vs -0.06 R;
the three long setups together 35 real trades, mean R t 2.9 (owner real-trades read 10-12).

The rule = three EXISTING strategy files run unchanged, loaded by file path (the CBDQ_1M_1_0.py sibling idiom;
augur_strategies/ has no __init__.py), each at fixed settings, then only trades whose FILL bar starts inside
09:30 .. 09:30 + `window_min` ET are kept. One contract per sub-leg; the sub-legs may overlap in time (up to 3 open).
  CBU  = CBUQ_2_0.py   base any, window day, exit ride (BE at +1R then ride), vol 1.5x, range 1.2 ATR, body 0.7 ATR
         (the owner's final CBU alert settings, prereg s.11).
  EBU  = EBUQ_1M_1_0.py  file defaults, exit ride, BE 1R.
  ENGU = ENGU_2_0.py     file defaults except body 3x median, no pullback, end_min 360, no vol filter, ride, BE 1R.
The window filter is applied AFTER each file's own walk, exactly as the harness did, so each file's per-session caps
and one-position rule still count trades later in the day (they cannot fill inside the window anyway: the window
starts at the open, and a later fill can never block an earlier one).
The sibling files are NOT modified. Only `window_min` is searched (hard bounds 5..90).
"""
import importlib.util as _ilu
import os as _os

import numpy as np

from augur_engine import setup_kit as SK

STRATEGY_NAME = "DISC OPENLONGS 1.0"
DESCRIPTION = ("Owner's CBU + EBU + ENGU long setups (existing CBUQ_2_0 / EBUQ_1M_1_0 / ENGU_2_0 files at fixed "
               "settings), keeping only fills in the first window_min minutes after 09:30 ET. w132 DISC leg J4.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_WIN_MIN, _WIN_MAX = 5, 90
_RTH_OPEN = 570

DEFAULT_PARAMS = {
    'window_min': {'default': 30, 'min': _WIN_MIN, 'max': _WIN_MAX, 'step': 5, 'type': 'int',
                   'label': 'Opening window (minutes after 09:30)',
                   'tooltip': 'Keep only trades that FILL on a bar starting before 09:30 + this many minutes ET.'},
}
PARAM_GRID_PRESETS = {'w132 J4 (harness)': {'window_min': [30]}}

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SUBS = {}


def _sub(fn):
    if fn not in _SUBS:
        sp = _ilu.spec_from_file_location("_disc_openlongs_" + fn[:-3].lower(), _os.path.join(_HERE, fn))
        m = _ilu.module_from_spec(sp)
        sp.loader.exec_module(m)
        _SUBS[fn] = m
    return _SUBS[fn]


_LEGS = (
    ("CBUQ_2_0.py", dict(base='any', window='day', exit_mode='ride', vol_mult=1.5, range_atr=1.2, body_atr=0.7)),
    ("EBUQ_1M_1_0.py", dict(exit_mode='ride', be_R=1.0)),
    ("ENGU_2_0.py", dict(body_mult=3.0, pb_atr=0.0, end_min=360, vol_mult=0.0, exit_mode='ride', be_R=1.0)),
)


def _defaults(m):
    return {k: v['default'] for k, v in m.DEFAULT_PARAMS.items()}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None, window_min=30,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("DISC_OPENLONGS_1_0: run_backtest needs `index` matching the price arrays' length")
    if volumes is None:
        raise ValueError("DISC_OPENLONGS_1_0: the CBU volume rule needs `volumes`")
    w = int(window_min)
    if not (_WIN_MIN <= w <= _WIN_MAX):
        raise ValueError("DISC_OPENLONGS_1_0: window_min must be %d..%d, got %r" % (_WIN_MIN, _WIN_MAX, window_min))
    minute = SK.sessions(index)[1]
    out = []
    for fn, kw in _LEGS:
        m = _sub(fn)
        p = _defaults(m)
        p.update(kw)
        r = m.run_backtest(opens, highs, lows, closes, volumes=volumes, index=index, return_trades=True, **p)
        for t in ((r or {}).get('trades') or []):
            mm = int(minute[int(t[0])])
            if _RTH_OPEN <= mm < _RTH_OPEN + w:
                out.append(tuple(t))
    out.sort(key=lambda t: (int(t[0]), int(t[1])))
    return SK.stats(out, return_trades=return_trades)

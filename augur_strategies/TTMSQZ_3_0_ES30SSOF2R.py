"""
TTMSQZ 3.0 ES30SSOF2R - the TTM book leg (run #369) with a ROLL GUARD.

WHY THIS EXISTS (2026-09-26, MANAGER dispatch; ROLL_AUDIT.md section 3.3)
  The ES 30m master is a raw stitch of front-month contracts. TTM is flat at every close, so it
  never books a contract offset - but its squeeze, ATR, momentum, hourly verification and open-bar
  tilt all read ACROSS sessions, so the price jump at a contract switch looks like a real opening
  gap. The roll audit found every one of the 19 trades that differ between raw and back-adjusted
  data starts 0-2 business days after a true switch, and the largest removed trades are roll-day
  longs (2022-12-12 +$1,769, 2023-09-11 +$1,098, 2024-06-17 +$5,837) that the open-bar tilt sized up.
  On back-adjusted data run #369 falls from 354 trades / $135,884 / PF 3.117 / MAR 1.83 to
  355 / $121,491 / PF 2.789 / MAR 1.43, with the lockbox and the walk-forward folds unchanged.

THE GUARD, AND WHY IT IS BAR-LEVEL RATHER THAN A BLACKOUT
  Every bar before each true contract switch is shifted by that switch's offset (Panama
  back-adjustment), using the exact switch table tools/data/contract_switches_ES.csv - never the
  house seam detector, which the audit found catches only 19 of 64 switches. The strategy then runs
  unchanged on the continuous series. The alternative - blocking entries for N days after a roll -
  throws away the real trades on those days along with the fake ones, and needs an N nobody can
  justify. The price series is the thing that is wrong, so the price series is what gets fixed.

WHY THIS IS NOT LOOK-AHEAD, stated because back-adjustment uses offsets from later switches
  A switch's offset is added to EVERY bar before it, so for any decision bar before that switch its
  whole lookback window moves by the same constant. Every quantity this leg reads is invariant to a
  constant shift - band widths, ranges, ATR, the momentum regression's slope, the compression ratio,
  and trade P&L in points - and the roll audit verified it directly: a +5,000-point shift of the full
  window leaves #369's trades identical. So a future switch cannot change a past decision; only a
  switch INSIDE a decision bar's lookback changes it, and that switch has already happened. In live
  trading the guard needs only the switches that have already occurred.
  P&L is unchanged by the shift for another reason too: the leg is flat at every session close and
  every switch falls outside regular hours (19:00-20:00 ET), so no trade spans one.

EVERYTHING ELSE IS RUN #369, imported rather than copied: structural stop, deep-squeeze tilt, open-bar
tilt, fade after two bars, hourly verification at length 20, the same fenced knobs and the same refusal
of out-of-set configurations.

THE BAR, WRITTEN BEFORE THE RUN. This is a CORRECTION, not an improvement - it is expected to earn
less than #369, because #369's figure includes fake trades. So it is not judged against #369's raw
money. It is judged on whether the honest leg still stands:
  (a) PASS, or WEAK on the overfit check alone;
  (b) whole-run figures match the roll audit's back-adjusted #369 within 2 percent of net
      ($121,491), proving the file does what the audit measured;
  (c) lockbox net at least $20,000 and lockbox profit factor at least 5 - the audit says the lockbox
      is unchanged, so a large fall here would mean the guard broke something;
  (d) whole-run annualised MAR above the corrected parents it replaced: #368 at 1.31 and #353 at
      1.15, both on back-adjusted data.
  Swapping the paper leg or the book leg onto this file is an OWNER decision either way.
"""
import os
from importlib import util as _u

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_sp = _u.spec_from_file_location("TTMSQZ_3_0_ES30SSOF2", os.path.join(_HERE, "TTMSQZ_3_0_ES30SSOF2.py"))
_base = _u.module_from_spec(_sp); _sp.loader.exec_module(_base)

_ROOT = "ES"
_SWITCHES_CSV = os.path.join(os.path.dirname(_HERE), "tools", "data", "contract_switches_%s.csv" % _ROOT)
_INCLUDE_INFERRED = False   # raw Databento switches only, as the roll audit measured (the post-raw
                            # rows are inferred from another feed and one of them is not trusted)


def _load_switches():
    sw = pd.read_csv(_SWITCHES_CSV)
    if not _INCLUDE_INFERRED:
        sw = sw[sw["source"] == "databento_raw"]
    sw = sw[np.isfinite(sw["contract_offset"].astype(float))]
    return (sw["switch_sec"].to_numpy(np.int64), sw["contract_offset"].to_numpy(float))


_SW_SEC, _SW_OFF = _load_switches()


def _bar_seconds(index):
    ix = pd.DatetimeIndex(index)
    if ix.tz is None:
        ix = ix.tz_localize("US/Eastern")
    return ix.tz_convert("UTC").asi8 // 10**9


def roll_offsets(index):
    """Points to add to each bar: the sum of the offsets of every true switch AFTER that bar."""
    sec = _bar_seconds(index)
    add = np.zeros(len(sec))
    for s, off in zip(_SW_SEC, _SW_OFF):
        add[sec < s] += off
    return add


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """Run #369 on a roll-continuous price series. Without a bar index there is no way to place the
    switches, so the file refuses rather than silently running unguarded."""
    if index is None:
        return None
    add = roll_offsets(index)
    o, h, l, c = (np.asarray(x, float) + add for x in (opens, highs, lows, closes))
    return _base.run_backtest(o, h, l, c, volumes=volumes, day_id=day_id, index=index,
                              return_trades=return_trades, **kw)


squeeze_indicators = _base.squeeze_indicators
_ADMISSIBLE = _base._ADMISSIBLE
_in_neighbourhood = _base._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SSOF2R - the book leg (run 369) with a roll guard'
DESCRIPTION = ("Run 369 on a price series with every true ES contract switch removed, so a roll is no "
               "longer read as an opening gap. A correction, not an improvement: it drops the fake "
               "squeezes the roll audit found 0-2 days after some switches.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SSOF2.py"

DEFAULT_PARAMS = dict(_base.DEFAULT_PARAMS)
PARAM_GRID_PRESETS = {
    "Short  (ES 30m book leg with roll guard)": dict(list(_base.PARAM_GRID_PRESETS.values())[0]),
}

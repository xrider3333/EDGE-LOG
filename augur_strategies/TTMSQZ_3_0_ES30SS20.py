"""
TTMSQZ 3.0 ES30SS20 - the structural stop with the VERIFICATION LENGTH FIXED at the crowned value.

WHY THIS EXISTS (2026-09-09, immediately after run #352)
  Run #352 put the structural stop through Auto-Validate and PASSED every house gate - plateau,
  walk-forward, sample, consistency, overfit and luck, with an overfit probability of 0.17 and a
  deflated Sharpe that beats the luck bar. It did NOT clear the bar written before it ran, and the
  reason is the one this shop has seen before (run #331): a search that crowns on in-sample money
  walks to the loosest corner of its own fence. It chose a verification length of 16 instead of 20,
  which nearly doubles the trade count - 665 against 357 - and takes the whole-run drawdown to
  $7,143 against the book leg's $4,549, a 57 percent rise against a 10 percent cap. Annualised MAR
  came out 0.956 against the book leg's 0.957: a dead heat bought with more risk, which is exactly
  what the drawdown clause exists to catch.

  So this file asks the question the round was actually about - does the STOP help - with the knob
  the search ran away on held at the value run #299 and run #340 both crowned, months before this
  stop was ever considered. That is one change at a time, not a cell picked to fit a bar: gate_len
  20 is the incumbent's own value and the value the paper book carries today.

  At that cell the mechanism reads 357 trades, profit factor 2.70, $73,720, drawdown $3,642 and a
  lockbox of $11,710 at 5.38; with run #340's validated deep-squeeze tilt on top, $101,017 at 2.91,
  drawdown $4,338 - BELOW the book leg's $4,549 - and a lockbox of $16,977 at 6.72.

  THE BAR, unchanged from run #352 so the two are comparable: (a) PASS, or WEAK on the overfit
  check alone; (b) lockbox net at least $6,948 and lockbox profit factor at least 2.38; (c)
  whole-run annualised MAR at least the book leg's, at a drawdown no more than 10 percent above its
  $4,549. And the caveat run #352 could not settle still stands: this stop is about 76 percent wider
  per contract than the ATR stop it replaces, so adoption needs a gap-stress read either way.

  Everything else - the mechanism, the hourly verification, the tilt, the cost convention - is
  identical to TTMSQZ_3_0_ES30SS.py, which this file imports rather than copies.
"""
import os
from importlib import util as _u

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0_ES30SS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0_ES30SS.py"))
_ss = _u.module_from_spec(_sp); _sp.loader.exec_module(_ss)

_GATE_LEN = 20        # run #299's and run #340's crowned value - frozen, not searched


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """The structural-stop leg with the verification length pinned. Out-of-set configurations are
    refused by the parent file, never clamped."""
    kw["gate_len"] = _GATE_LEN
    return _ss.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                            index=index, return_trades=return_trades, **kw)


squeeze_indicators = _ss.squeeze_indicators
_ADMISSIBLE = {k: v for k, v in _ss._ADMISSIBLE.items() if k != "gate_len"}
_in_neighbourhood = _ss._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SS20 - structural stop, verification length fixed at 20'
DESCRIPTION = ("The structural-stop leg of run #352 with the one knob its search ran away on held at the "
               "value run #299 and run #340 both crowned. Two knobs vary; the stop, the hourly "
               "verification and the validated size tilt are unchanged.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SS.py"

DEFAULT_PARAMS = {k: v for k, v in _ss.DEFAULT_PARAMS.items() if k != "gate_len"}

PARAM_GRID_PRESETS = {
    "Short  (ES 30m structural stop, gate length 20)": {
        k: v for k, v in list(_ss.PARAM_GRID_PRESETS.values())[0].items() if k != "gate_len"},
}

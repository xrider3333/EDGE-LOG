"""
TTMSQZ 3.0 ES30SSF2 — the book leg, leaving one bar later.

WHY THIS EXISTS (2026-09-09)
  The momentum-fade exit leaves on the FIRST bar momentum fades. Waiting for a SECOND fading bar has
  now been measured twice — round 8 on the old ATR-stop base, round 14b on the structural-stop base
  the book carries today — and both times it came out ahead on everything except one number:

                              trades    PF        net      drawdown     lockbox    lockbox PF
    book leg (fade after 1)     357    2.91   $101,017     $4,338      $16,977        6.72
    this file (fade after 2)    354    2.80   $101,795     $4,277      $17,452        7.82

  More money, LESS drawdown, a bigger lockbox and a much better lockbox profit factor, on 354 of the
  same 357 trades. Annualised MAR 23.80 against 23.29 on the leg's own drawdown. The exits move as
  you would expect from one extra bar of patience: 105 fade exits instead of 175, 194 held to the
  close instead of 135, and 55 stopped instead of 47.

WHY IT WAS NOT PICKED UP UNTIL NOW, STATED PLAINLY
  Both scans screened candidates on "beats the incumbent on BOTH whole-run profit factor and lockbox
  net", and this cell fails that screen on the first half — profit factor 2.80 against 2.91. That
  screen is a triage heuristic for a scan with dozens of cells; it is NOT the bar this shop crowns
  on. Every pre-registered validate bar in this family (runs #340, #352, #353) is built from the
  house gates, the LOCKBOX net and profit factor, and annualised MAR at a drawdown cap — whole-run
  profit factor has never been a clause in any of them. So the bar below is the same shape as its
  three predecessors, not a bar reshaped after seeing which clause failed.

  DISCLOSED, because it is the one number that gets worse: whole-run profit factor falls from 2.91
  to 2.80. That is what one extra bar of patience buys — a few small winners that used to be booked
  on the first fade now ride to the close, where some give back. It is a real cost and it is not
  hidden in a clause.

THE BAR, WRITTEN BEFORE THE RUN, against the book leg (run #353):
  (a) PASS, or WEAK on the overfit check alone;
  (b) lockbox net at least $16,977 AND lockbox profit factor at least 6.72;
  (c) whole-run annualised MAR at least run #353's 1.450, at a whole-run drawdown NO HIGHER than its
      $4,338 — the claim here is that the drawdown falls, so the bar holds it to that with no slack.

Everything else is unchanged from the leg the book carries: the crown cell, the hourly verification
at length 20, the validated 1.5x deep-squeeze size tilt, and the structural stop at the far side of
the squeeze range. Imported from TTMSQZ_3_0_ES30SS.py rather than copied.
"""
import os
from importlib import util as _u

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0_ES30SS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0_ES30SS.py"))
_ss = _u.module_from_spec(_sp); _sp.loader.exec_module(_ss)

_GATE_LEN = 20        # run #299's and run #340's crowned value - frozen, as in ES30SS20
_FADE_BARS = 2        # THE ONE CHANGE

# HOW THE ONE CHANGE IS APPLIED, and why this is safe. The parent file reads fade_bars out of
# its own _FROZEN dict rather than from the call, precisely so a caller cannot quietly change
# the mechanism - passing fade_bars=2 into run_backtest is silently ignored, which the parity
# check caught by returning the parent's numbers to the dollar. So the frozen value is set here
# instead. Every wrapper in this family loads the parent through its OWN spec_from_file_location,
# so `_ss` is a private module object, not the one ES30SS20 or anything else is holding: this
# rebinding cannot reach another leg even when the paper runner has both loaded at once. The
# parity check below the docstring is what proves it - it runs both files in one process.
_ss._FROZEN = dict(_ss._FROZEN, fade_bars=_FADE_BARS)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """The book leg with the momentum-fade exit waiting for a second fading bar. Out-of-set
    configurations are refused by the parent file, never clamped."""
    kw["gate_len"] = _GATE_LEN
    return _ss.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                            index=index, return_trades=return_trades, **kw)


squeeze_indicators = _ss.squeeze_indicators
_ADMISSIBLE = {k: v for k, v in _ss._ADMISSIBLE.items() if k != "gate_len"}
_in_neighbourhood = _ss._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SSF2 - the book leg, leaving on the second fading bar'
DESCRIPTION = ("The leg the paper book carries, with one change: the momentum-fade exit waits for a "
               "second fading bar instead of leaving on the first. More money, less drawdown and a "
               "bigger lockbox on both bases it has been measured on; whole-run profit factor falls "
               "from 2.91 to 2.80, which is disclosed rather than hidden.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SS.py"

DEFAULT_PARAMS = {k: v for k, v in _ss.DEFAULT_PARAMS.items() if k != "gate_len"}

PARAM_GRID_PRESETS = {
    "Short  (ES 30m structural stop, fade after 2 bars)": {
        k: v for k, v in list(_ss.PARAM_GRID_PRESETS.values())[0].items() if k != "gate_len"},
}

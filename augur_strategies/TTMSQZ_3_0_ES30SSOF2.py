"""
TTMSQZ 3.0 ES30SSOF2 — both validated changes at once: the open-bar tilt AND the later fade.

Two single changes to the book leg were validated within an hour of each other, each against a bar
written before it ran, each on a different part of the trade:

    run #368  size    1.5 contracts on the session open-bar entry - the 87 of 357 trades that fill
                      on the first bar an entry can happen, which average $805 against $115
    run #364  exit    leave on the SECOND fading bar rather than the first

They touch nothing in common - one decides how much, the other decides when to leave - so the
question is simply whether they add up. This file is that question, and NOTHING about it is a new
idea: it is two validated changes in one leg, with every other knob, the structural stop, the
hourly verification and the deep-squeeze tilt exactly as the book carries them.

WHAT THEY MEASURE TOGETHER, on the pinned window, all four legs run in one process:

                            trades   PF        net    drawdown    MAR    lockbox  LB PF  LB dd
    book leg (run #353)       357   2.91   $101,017    $4,338   1.450   $16,977   6.72  $2,003
    fade 2   (run #364)       354   2.80   $101,795    $4,277   1.482   $17,452   7.82  $1,978
    open bar (run #368)       357   3.28   $136,043    $5,330   1.589   $22,321   8.52  $2,003
    BOTH     (this file)      354   3.12   $135,884    $4,634   1.826   $22,739   9.89  $1,978

  They do more than add up, and the reason is legible: the open-bar tilt buys money by putting
  more size on the best trades, and it pays for that with drawdown - $4,338 to $5,330. The later
  fade gives most of that drawdown back, to $4,634, while keeping the money. Annualised MAR is
  1.826 against the book leg's 1.450, a quarter better, and the lockbox is larger than either
  parent's at a lockbox drawdown lower than either parent's.

WHY THIS IS STILL A SEPARATE RUN RATHER THAN AN ASSUMPTION
  Two changes that each help can interact badly - the later fade holds trades longer, and the open-bar
  tilt puts more size on precisely the trades that tend to run - so the combination could concentrate
  risk in a way neither did alone. That is exactly what a drawdown clause is for.

THE BAR, WRITTEN BEFORE THE RUN, against the book leg (run #353: $101,017, drawdown $4,338,
annualised MAR 1.450, lockbox $16,977 at profit factor 6.72):
  (a) PASS, or WEAK on the overfit check alone;
  (b) lockbox net at least run #368's $22,321 - the better of the two parents, not the incumbent,
      because a combination that cannot beat its own best half is not worth the extra complexity;
  (c) whole-run annualised MAR at least run #368's 1.589, at a whole-run drawdown no more than 25
      percent above the book leg's $4,338, the same size-aware clause run #368 was held to.

Imported from TTMSQZ_3_0_ES30SSO.py, which imports the structural-stop file, which imports the
engine. Nothing is copied.
"""
import os
from importlib import util as _u

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0_ES30SSO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0_ES30SSO.py"))
_so = _u.module_from_spec(_sp); _sp.loader.exec_module(_so)

_FADE_BARS = 2      # run #364's change, applied on the parent's own private frozen copy

# The chain freezes fade_bars two levels down, in the structural-stop file, and a passed value is
# silently ignored by design. Each wrapper loads its parent through its OWN spec_from_file_location,
# so this rebinding reaches only this file's copy - the parity check runs every leg in one process
# and would show it if that were not true.
_so._ss._FROZEN = dict(_so._ss._FROZEN, fade_bars=_FADE_BARS)

run_backtest = _so.run_backtest
squeeze_indicators = _so.squeeze_indicators
_ADMISSIBLE = _so._ADMISSIBLE
_in_neighbourhood = _so._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SSOF2 - open-bar tilt (run 368) plus the later fade (run 364)'
DESCRIPTION = ("Both validated changes in one leg: 1.5 contracts on the session open-bar entry, and "
               "the momentum-fade exit waiting for a second fading bar. Everything else is the leg "
               "the paper book carries.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SSO.py"

DEFAULT_PARAMS = dict(_so.DEFAULT_PARAMS)
PARAM_GRID_PRESETS = {
    "Short  (ES 30m structural stop, open-bar tilt, fade 2)": dict(list(_so.PARAM_GRID_PRESETS.values())[0]),
}

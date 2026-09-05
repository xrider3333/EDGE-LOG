"""
NOISE 1.3 WIDE -- run #316's neighbourhood, re-fenced so the crown is not on an edge.

WHY THIS FILE EXISTS (owner 2026-09-05: "do the wider re-run on 316. we need to make
sure theres no concentration where a handfull of trades lead it to being profiable").

Run #316 validated NOISE_1_1_LB51.py, whose four open knobs make exactly 90 cells
(lookback 5 x band_mult_short 3 x confirm_bars 2 x stop_k 3). It passed well: 8 of 8
walk-forward folds, 4 of 4 neighbours holding PF >= 1, plateau AGREES, the best
annualised MAR of any NOISE run at 1.13, the smallest drawdown at $19.7k, stress across
time reads SPREAD, and -- the reason it is the candidate -- NO concentration caution.

Two things are wrong with stopping there, and this file fixes both.

1. THE CROWN SAT ON TWO FENCES. #316 crowned lookback 37 and stop_k 2.0. Those are the
   MINIMUM and the MAXIMUM of LB51's ranges. A search that walks to the edge of its own
   fence is telling you the fence is in the wrong place: the optimum it wanted was
   outside, and what got crowned is the best cell it was allowed to reach, not the best
   cell there is. Neither number can be read as a plateau centre while it is on a wall.

2. PBO WAS MEASURED ON 90 CELLS. PBO -- the probability the crown was a lucky draw from
   the configurations searched -- came back 0.46 on #316. Compare run #304 at 0.14 on
   495 cells and run #302 at 0.60 on 570. A 90-cell population gives a noisy estimate in
   both directions, so #316's 0.46 is not yet evidence either way. This file searches
   600 cells so its PBO sits on the same footing as #304's and the three become directly
   comparable.

WHAT CHANGED, AND WHAT DELIBERATELY DID NOT:

    knob               LB51 (#316)          here                 why
    lookback           37..65 step 7        16..65 step 7        crown was ON the 37 wall;
                                                                 same lattice, extended DOWN
                                                                 so 37 becomes interior
    stop_k             1.5..2.0 step .25    1.5..2.5 step .25    crown was ON the 2.0 wall
    band_mult_short    1.25..1.75           1.00..2.00           room either side of 1.5
    confirm_bars       1..2                 1..3                 room above 2
    everything else    pinned to the crown  UNCHANGED            band_mult_long 0.75,
                                                                 vol_skip_pct 90, day-type
                                                                 skip_bot_short 0.2/0.8,
                                                                 bandwidth stop, vwap exit

    8 x 5 x 3 x 5 = 600 cells (LB51: 90).

WHY NOT OPEN vol_skip_pct AND band_mult_long TOO. Because that is run #302, and #302 is
the cautionary tale: NOISE_1_0's fifteen wide-open knobs let the sampler wander off the
champion core entirely and it came back WEAK with PBO 0.60. Widening a neighbourhood is
not the same move as removing the neighbourhood. This file widens the four knobs that
were demonstrably fenced too tight and holds the rest exactly where #316 had them, so
any change in the verdict is attributable to those four and nothing else.

WHAT THIS RUN IS ACTUALLY BEING ASKED. The owner's question is not "can we find a bigger
number" -- it is whether the edge survives without its luckiest handful of trades. So
read the report in this order and stop at the first failure:

  1. CONCENTRATION, first and hardest. Run #304 is the worked example of why: it holds
     the best PBO on the board at 0.14 and its top five trades are 137% of its net --
     strip them and it LOSES $7,381. Low overfit odds bought with an edge that dies
     without five trades is not a tradable edge. If the crown here shows a concentration
     caution, it fails regardless of everything below it.
  2. PBO on 600 cells. Below ~0.30 is the bar #304 set on a comparable population.
  3. Is the crown INTERIOR this time? If it walks to 16 or to 2.5 the fence is still
     wrong and the answer is another re-fence, not an adoption.
  4. Walk-forward folds against #316's 8 of 8, and the lockbox.
  5. Only then the money.

CAUTION THAT TRAVELS WITH IT. Widening the fence raises the number of configurations
searched from 90 to 600, and PBO is measured against exactly that. A higher PBO here is
not automatically worse than #316's 0.46 -- a bigger search is more honest about its own
selection risk. Compare it to #304's 0.14 on 495, which is the like-for-like reading.

Window, costs, source and lockbox are pinned to run #316's own job so the verdicts are
directly comparable to it (the HARD RULE on rerun windows).
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_wide13", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.3 WIDE - run #316 neighbourhood re-fenced, 600 cells'
DESCRIPTION   = ("Run #316's search space with the two walls its crown sat on moved outward - "
                 "lookback down to 16, stop_k up to 2.5 - plus room either side of the short "
                 "band and the confirm bars. 600 cells instead of 90, so PBO is measured on a "
                 "population comparable to run #304's. Everything outside those four knobs is "
                 "held exactly where #316 had it.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

DEFAULT_PARAMS = {
    # defaults are run #316's crowned cell, so the file documents what it is centred on
    'lookback':        {'default': 37, 'min': 16, 'max': 65, 'step': 7, 'type': 'int',
                        'label': 'Lookback (bars) - WIDENED DOWN (#316 crowned 37, the old floor)'},
    'band_mult_long':  {'default': 0.75, 'min': 0.75, 'max': 0.75, 'step': 0.25, 'type': 'float',
                        'label': 'Long band multiple - PINNED (crown)'},
    'band_mult_short': {'default': 1.5, 'min': 1.0, 'max': 2.0, 'step': 0.25, 'type': 'float',
                        'label': 'Short band multiple - WIDENED both ways around 1.5'},
    'exit_mode':       {'default': 'vwap', 'type': 'str', 'options': ['vwap'],
                        'label': 'Exit - PINNED (crown)'},
    'side':            {'default': 'Both', 'type': 'str', 'options': ['Both'],
                        'label': 'Side - PINNED (crown)'},
    'window':          {'default': 'all_day', 'type': 'str', 'options': ['all_day'],
                        'label': 'Window - PINNED (crown)'},
    'flat_eod':        {'default': True, 'type': 'bool', 'options': [True],
                        'label': 'Flat at close - PINNED on'},
    'skip_holidays':   {'default': False, 'type': 'bool', 'options': [False],
                        'label': 'Skip holidays - PINNED off (crown)'},
    'stop_mode':       {'default': 'bandwidth', 'type': 'str', 'options': ['bandwidth'],
                        'label': 'Stop mode - PINNED (crown)'},
    'confirm_bars':    {'default': 1, 'min': 1, 'max': 3, 'step': 1, 'type': 'int',
                        'label': 'Confirm bars - WIDENED to 1-3'},
    'daytype_mode':    {'default': 'skip_bot_short', 'type': 'str', 'options': ['skip_bot_short'],
                        'label': 'Day-type filter - PINNED (crown)'},
    'daytype_lo':      {'default': 0.2, 'min': 0.2, 'max': 0.2, 'step': 0.05, 'type': 'float',
                        'label': 'Day-type low - PINNED (crown)'},
    'daytype_hi':      {'default': 0.8, 'min': 0.8, 'max': 0.8, 'step': 0.05, 'type': 'float',
                        'label': 'Day-type high - PINNED (crown)'},
    'vol_skip_pct':    {'default': 90.0, 'min': 90.0, 'max': 90.0, 'step': 1.0, 'type': 'float',
                        'label': 'Vol-skip percentile - PINNED (crown, deliberately not opened)'},
    'stop_k':          {'default': 2.0, 'min': 1.5, 'max': 2.5, 'step': 0.25, 'type': 'float',
                        'label': 'Stop k - WIDENED UP (#316 crowned 2.0, the old ceiling)'},
}

# the mechanism is NOISE_1_0's, untouched - this file only re-fences the search space.
run_backtest = _base.run_backtest

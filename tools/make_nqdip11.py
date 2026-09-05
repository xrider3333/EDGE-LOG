"""Build augur_strategies/NQDIP_1_1.py from NQDIP_1_0.py (which stays untouched: run #307).
Adds three long-only dip legs, each with its own slot, switch and ranged knobs:
  IBS    : daily internal bar strength (close-low)/(high-low) < ibs_thr while close > trend
           -> buy next open; exit when IBS > ibs_exit or after ibs_hold days.
  STREAK : streak_n consecutive lower closes while close > trend -> buy next open;
           exit on the first up close or after streak_hold days.
  GAPDN  : today opened at least gap_atr x ATR20 BELOW yesterday's close, yesterday's
           close > trend -> signal on today's close, buy next open; exit on a close above
           the gap day's high or after gap_hold days.
Every assert below guards the exact 1.0 text; with the new legs OFF, 1.1 == 1.0."""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "augur_strategies", "NQDIP_1_0.py"), encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    assert src.count(old) >= 1, "anchor missing: " + old[:60]
    src = src.replace(old, new, count)


rep("STRATEGY_NAME = 'NQDIP 1.0 · Nasdaq dip book (4 long-only dip mechanisms, one file)'",
    "STRATEGY_NAME = 'NQDIP 1.1 · Nasdaq dip book (7 long-only dip mechanisms, one file)'\n_AUGUR_PARENT = \"NQDIP_1_0.py\"")
rep('NQDIP 1.0 — the Nasdaq dip-buying BOOK as one strategy (four mechanisms, long-only).',
    'NQDIP 1.1 — NQDIP 1.0 plus three more dip legs (IBS, losing streak, gap-down), long-only.\n'
    'Frequency lever for R / YR: same tape, more independent dip triggers. With use_ibs /\n'
    'use_streak / use_gapdn OFF this file reproduces NQDIP_1_0 (run #307) to the dollar.\n'
    '  IBS    : (close-low)/(high-low) of the daily bar < ibs_thr while close > trend\n'
    '           -> buy next open; exit when IBS > ibs_exit or after ibs_hold days\n'
    '  STREAK : streak_n consecutive lower closes while close > trend -> buy next open;\n'
    '           exit on the first up close or after streak_hold days\n'
    '  GAPDN  : open >= gap_atr x ATR20 below the prior close with prior close > trend ->\n'
    '           signal on that day close, buy next open; exit on a close above the gap-day\n'
    '           high or after gap_hold days')
rep('    "use_cap": {"default": True, "type": "bool", "label": "Run the capitulation leg"},\n}',
    '    "use_cap": {"default": True, "type": "bool", "label": "Run the capitulation leg"},\n'
    '    "ibs_thr": {"default": 0.2, "min": 0.1, "max": 0.3, "step": 0.05, "type": "float", "label": "IBS buy below",\n'
    '                "tooltip": "Daily internal bar strength (close-low)/(high-low) below this = closed near the low."},\n'
    '    "ibs_exit": {"default": 0.7, "min": 0.5, "max": 0.9, "step": 0.1, "type": "float", "label": "IBS exit above"},\n'
    '    "ibs_hold": {"default": 5, "min": 2, "max": 8, "step": 1, "type": "int", "label": "IBS max hold (days)"},\n'
    '    "streak_n": {"default": 3, "min": 2, "max": 5, "step": 1, "type": "int", "label": "Down-close streak length"},\n'
    '    "streak_hold": {"default": 5, "min": 2, "max": 8, "step": 1, "type": "int", "label": "Streak max hold (days)"},\n'
    '    "gap_atr": {"default": 0.5, "min": 0.25, "max": 1.0, "step": 0.25, "type": "float", "label": "Gap-down size (x ATR20)"},\n'
    '    "gap_hold": {"default": 3, "min": 1, "max": 5, "step": 1, "type": "int", "label": "Gap-down max hold (days)"},\n'
    '    "use_ibs": {"default": True, "type": "bool", "label": "Run the IBS leg"},\n'
    '    "use_streak": {"default": True, "type": "bool", "label": "Run the losing-streak leg"},\n'
    '    "use_gapdn": {"default": True, "type": "bool", "label": "Run the gap-down leg"},\n}')
rep("    use_rsi: bool = True, use_dbl: bool = True, use_pb: bool = True, use_cap: bool = True,\n",
    "    use_rsi: bool = True, use_dbl: bool = True, use_pb: bool = True, use_cap: bool = True,\n"
    "    ibs_thr: float = 0.2, ibs_exit: float = 0.7, ibs_hold: int = 5,\n"
    "    streak_n: int = 3, streak_hold: int = 5, gap_atr: float = 0.5, gap_hold: int = 3,\n"
    "    use_ibs: bool = True, use_streak: bool = True, use_gapdn: bool = True,\n")
rep('    legs = [("RSI", use_rsi), ("DBL", use_dbl), ("PB", use_pb), ("CAP", use_cap)]',
    '    ibs_hold, streak_n, streak_hold, gap_hold = int(ibs_hold), int(streak_n), int(streak_hold), int(gap_hold)\n'
    '    rng_d = dh - dl\n'
    '    ibs = np.where(rng_d > 1e-9, (dc - dl) / np.where(rng_d > 1e-9, rng_d, 1.0), 0.5)\n'
    '    legs = [("RSI", use_rsi), ("DBL", use_dbl), ("PB", use_pb), ("CAP", use_cap),\n'
    '            ("IBS", use_ibs), ("STREAK", use_streak), ("GAPDN", use_gapdn)]')
# signal block: turn the trailing `else:` (CAP) into explicit branches + the three new legs
rep('                else:\n'
    '                    rng = dh[d] - dl[d]\n'
    '                    s = (dc[d] < do[d] and rng > 0 and not np.isnan(atr20[d]) and rng >= cap_mult * atr20[d]\n'
    '                         and (dc[d] - dl[d]) / rng <= cap_q)\n',
    '                elif mech == "CAP":\n'
    '                    rng = dh[d] - dl[d]\n'
    '                    s = (dc[d] < do[d] and rng > 0 and not np.isnan(atr20[d]) and rng >= cap_mult * atr20[d]\n'
    '                         and (dc[d] - dl[d]) / rng <= cap_q)\n'
    '                elif mech == "IBS":\n'
    '                    s = dc[d] > trend[d] and rng_d[d] > 0 and ibs[d] < ibs_thr\n'
    '                elif mech == "STREAK":\n'
    '                    s = (d >= streak_n and dc[d] > trend[d]\n'
    '                         and all(dc[d - j] < dc[d - j - 1] for j in range(streak_n)))\n'
    '                else:  # GAPDN\n'
    '                    s = (not np.isnan(atr20[d]) and dc[d - 1] > trend[d - 1]\n'
    '                         and (dc[d - 1] - do[d]) >= gap_atr * atr20[d])\n')
# exit block
rep('                else:\n'
    '                    ex = (d - de >= cap_hold)\n',
    '                elif mech == "CAP":\n'
    '                    ex = (d - de >= cap_hold)\n'
    '                elif mech == "IBS":\n'
    '                    ex = (rng_d[d] > 0 and ibs[d] > ibs_exit) or (d - de >= ibs_hold)\n'
    '                elif mech == "STREAK":\n'
    '                    ex = (dc[d] > dc[d - 1]) or (d - de >= streak_hold)\n'
    '                else:  # GAPDN: gap day = de - 1\n'
    '                    ex = (dc[d] > dh[de - 1]) or (d - de >= gap_hold)\n')
out = os.path.join(ROOT, "augur_strategies", "NQDIP_1_1.py")
open(out, "w", encoding="utf-8").write(src)
import ast; ast.parse(src)
print("wrote", out, "syntax OK")

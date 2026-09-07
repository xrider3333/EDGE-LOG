"""Fast unit tests for tools/exit_autopsy.py's MFE/MAE/capture arithmetic.

Synthetic bars only — no engine, no network, no Firestore. Exercises
mfe_mae_points (raw point excursion + which bar it peaked on) and the
winners' capture read (final PnL / MFE) inside block().
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.exit_autopsy import block, mfe_mae_points  # noqa: E402


def test_mfe_mae_points_long():
    # bars 0..4: a long entered at bar 0 (epx=100) that runs up to 108 (bar 2)
    # before pulling back and being stopped out for +3 at bar 4. MFE should read
    # the best excursion (8, at bar 2) and MAE the worst (0, never below entry).
    highs = np.array([101.0, 105.0, 108.0, 106.0, 103.0])
    lows = np.array([99.0, 100.0, 104.0, 101.0, 100.0])
    trade = dict(eb=0, xb=4, pnl=3.0, side=1, epx=100.0)
    mfe, mae, peak_bar = mfe_mae_points(trade, highs, lows)
    assert mfe == 8.0
    assert mae == -1.0  # lowest low in [0,4] is 99 -> 99-100 = -1
    assert peak_bar == 2


def test_mfe_mae_points_short():
    # a short entered at 100 (epx) that dips to 90 (bar 1, best favourable move)
    # then bounces to 104 (bar 3, worst adverse move) before exit at bar 4.
    highs = np.array([101.0, 92.0, 96.0, 104.0, 98.0])
    lows = np.array([98.0, 90.0, 93.0, 99.0, 95.0])
    trade = dict(eb=0, xb=4, pnl=-2.0, side=-1, epx=100.0)
    mfe, mae, peak_bar = mfe_mae_points(trade, highs, lows)
    # short favourable = down: best = 100-90 = 10 at bar 1
    assert mfe == 10.0
    # short adverse = up: worst = 100-104 = -4 at bar 3
    assert mae == -4.0
    assert peak_bar == 1


def test_block_capture_and_give_back():
    # Two winners and one loser, hand-built so capture/give-back are exact:
    #   winner A: MFE $100, final $80  -> capture 0.80, give-back $20
    #   winner B: MFE $100, final $40  -> capture 0.40, give-back $60
    #   loser  C: MFE $60,  final -$50 -> a loser that was up 1R (R=$50) before losing
    tr = pd.DataFrame([
        dict(eb=0, xb=5, held=5, side=1, mfe_usd=100.0, mae_usd=-10.0, final_usd=80.0,
             peak_frac=0.4, exit_date=pd.Timestamp("2020-01-01")),
        dict(eb=0, xb=5, held=5, side=1, mfe_usd=100.0, mae_usd=-10.0, final_usd=40.0,
             peak_frac=0.6, exit_date=pd.Timestamp("2020-01-02")),
        dict(eb=0, xb=5, held=5, side=1, mfe_usd=60.0, mae_usd=-55.0, final_usd=-50.0,
             peak_frac=0.5, exit_date=pd.Timestamp("2020-01-03")),
    ])
    r_unit_usd = 50.0  # matches the loser's own loss, so it reads as exactly 1R
    b = block(tr, r_unit_usd, window_years=1.0)

    assert b["n"] == 3
    assert b["winners"]["n"] == 2
    assert b["winners"]["capture_med"] == 0.6  # median of 0.80, 0.40
    assert b["losers"]["n"] == 1
    assert b["losers"]["mfe_r_med"] == 1.2  # 60/50
    assert b["losers"]["share_reached_1r"] == 1.0  # the one loser reached >= 1R
    assert b["losers"]["share_reached_0_5r"] == 1.0
    # give-back: winners (20+60)=80, loser (60-(-50))=110 -> sum 190 -> $190/yr
    assert b["give_back"]["usd_per_year"] == 190.0

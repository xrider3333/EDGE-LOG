"""
MISC_SUPERSCALPER 1.0 - port of TradingView "NQ/MNQ Super Scalper [BACKTEST]" (Pine v6).

Source: https://www.tradingview.com/script/6ve1ax1D-NQ-MNQ-Super-Scalper-BACKTEST/
Author Crispigino (open source). Ported from the cached text
C:\\EdgeLog\\_research_cache\\tv_scalp\\superscalper\\NQ_MNQ_Super_Scalper_v1.pine
(3,292 lines, sha256 5b8a1304c7aacbe10030cee4495965d7cbb3fe131d540995a3f0c887673beb2e).
This file is a re-implementation, not a copy of the Pine text.

WHAT THE SCRIPT TRADES
  Six entry paths evaluated on every 1-minute bar CLOSE, in the script's priority order,
  at most one long and one short ticket per bar:
    MAIN  trend + RSI + 2-close structure break, confirmed by ORB retest / ORB-rejection /
          OTE zone, behind ~12 veto layers (dirScore, structure, HTF, trend alignment,
          overextension, short volume score, macro veto)
    BOS   break of structure with a confluence count and dynamic gate relaxation
    OB    order-block displacement (ICT), 5-rule star gate
    RE    EMA21 pullback retest in an AER-regime trend
    TRAP  liquidity sweep reversal (fake break of the sweep range)
    OD    opening-drive volume spike in the 07:28 / 08:30 / 09:00 CT windows (flat only)
  Each entry is a market order (next bar's OPEN, process_orders_on_close=false) with its
  own strategy.exit bracket (stop + limit) computed on the signal bar. pyramiding=20.
  The script's 20-pattern "smart exit" block is hard-wired OFF (smartExitL/S = false), so
  the brackets are the only exits; nothing closes at session end.

PORT SEMANTICS (TV parity first)
  - Every indicator is computed on bar t's close with TradingView's definitions: ta.rma /
    ta.ema seeded with the SMA, ta.atr = rma(true range), ta.rsi = rma ratio, ta.dmi/adx,
    ta.vwap anchored at the CME trading-day start (18:00 ET), population ta.stdev,
    ta.linreg, ta.mfi, ta.pivothigh/low with their confirmation delay, Pine v6 na rules
    (any comparison with na is false, math.max/min with na is na, nz()).
  - Built-in ta.* calls see the value passed at call time: ta.sma(atr, 50) runs before the
    session re-selection of `atr`, so it is an SMA of ATR(14) (as in TV).
  - The script's own order of evaluation is kept: `var` levels written later in the bar
    (volume profile, nearSup/nearRes) are read with their PREVIOUS-bar value by the entry
    block; onHigh/onLow are read before and after their own update exactly where the
    script reads them.
  - Session strings are evaluated in America/Chicago on the bar OPEN time (time(tf, sess)
    with all seven days); dayofmonth() resets use the Chicago calendar day.
  - request.security, higher timeframes (5/15/60/240, lookahead_off): an HTF bar's values
    become visible on the 1m bar whose close reaches the HTF bar's scheduled end (= its
    last 1m bar), never earlier; until then the previous HTF bar's values. 5/15/60-minute
    bars are clock-aligned; 240-minute bars are anchored at the 17:00 CT session start and
    the last one ends at the 16:00 CT close. h15s[5] etc. are 1-minute history.
  - Daily request ([1]/[2], lookahead_on): previous CME sessions (18:00 ET start), all day.
    Daily CLOSE = settlement approximation (knob daily_close, see PORT GAPS).
  - Cross symbols at 1m (lookahead_off, value carried forward outside the symbol's hours):
    ES1! = NOADJ_ES_1m_ETH (db_noadj_eth) high/low, raw like TV's ES1!;
    SPY  = not held -> ES close (roll difference-adjusted) sampled 09:30-16:00 ET and carried
           forward (spy_proxy='es_rth', default; 'es' = all hours; 'none' = na);
    QQQ  = alpaca_split_rth 1m close. Feeds attach only on an NQ tape (engine roll context
           root NQ) and are read only for the run's own window (no rows past its end).
  - Fills: market entry at the next bar's open. Bracket stop/limit work from the fill bar
    itself (TV fills exits on the entry bar; the published trade list has same-minute
    entries/exits). Stop/limit prices are rounded to the 0.25 tick, as TV rounds order
    prices. Gap through a level at the open fills at the open. When a bar could
    touch both legs: intrabar='worst' (default) = adverse leg first (stop first for every
    ticket); 'tv' = TradingView broker emulator path: open->high->low->close when the high
    is closer to the open than the low, else open->low->high->close. Fills inside a bar are
    applied in path order.
  - close_entries_rule: the script does not set it, so TV's default FIFO applies to this
    futures strategy - an exit order closes the OLDEST open trade, whichever ticket's
    bracket fired (close_rule='fifo', default; 'any' = each bracket closes its own ticket).
    Total points are identical; only the per-trade pairing differs.
  - pyramiding: up to `pyramiding` (default 20, the script's cap) open entries in one
    direction; an entry that would exceed it is not filled. A long and a short order placed
    on the same flat bar fill in code order at the next open (the second reverses the first
    at the same price - a zero-length trade, exit reason 'reverse').
  - Roll seams (NOADJ master): every open ticket is closed at the close of the last bar
    before each contract switch of the audited roll table (augur_engine.rolls), no entry
    may fill on that bar's ET calendar day up to the switch, no pending order survives it,
    and nothing fills inside a bar the switch splits (BBRSI's seam-eve guard, made exact
    for ETH bars). ROLL_SIGNAL = 'raw': TV trades raw NQ1! prices and this file mixes point
    and percent logic, so signals read raw prices and the engine refuses any crossing.
  - A ticket still open when the loaded data ends is DROPPED (lockbox-honest).
  - P&L in POINTS, gross: no commission, no slippage (the engine subtracts cost_pts per
    round trip). TV itself was run with $0.62/side and 2 ticks slippage per side.

INPUTS - 41 in the script. 31 are knobs below (author defaults, searchable ranges about
x0.5..x1.5). DROPPED (no effect on any order):
  showSuperTrend, showDirPulse, useDirBarColor   (plot toggles)
  showStructLabels, structLabelMode, structMinSwingATR, structMinBarsBetween
                                                  (only drive the HL/LL label drawing)
  projFwd                                         (projection line only)
  obMaxBoxes                                      (box drawing removed in the script)
  divLookback                                     (RSI/delta divergences only feed the
                                                   post-entry dirScore additions and the
                                                   disabled smart exits)
  Kept although labelled "Show ...": useOB (gates OB detection), showQQQLevels /
  showORBMid / showONRange (feed TP targets and S/R levels).
Port knobs: intrabar, close_rule, pyramiding, spy_proxy, footprint, daily_close.
Our-port knobs (not in the script): sl_cap_atr, sl_scale, tp_scale, max_hold_bars,
be_trigger, vix_feed - see OUR PORT ADDITIONS.

OUR PORT ADDITIONS (improvement-round knobs; every default reproduces the as-ported
trades exactly - tests/test_misc_superscalper.py pins it on synthetic data and on NQ 1m
ETH 2024-06-03..06-14)
  Exit knobs act only on each ticket's bracket, AFTER every entry gate (minProfit, R:R,
  score and star checks all see the script's own levels), so the candidate entries are
  unchanged; only the position-dependent gates (pyramiding cap, flat-only OD, no long
  while short) see the different positions the new exits leave.
  - sl_cap_atr 'off' | '3.0': the author's comment says the session stop is "never > 3
    ATR", but math.min(close + atr*3, ...) / math.max(close - atr*3, ...) is a no-op.
    '3.0' applies it where the author wrote it (Pine lines 687/692/702/707): the session
    stops slEthL / slRthL / slEthS / slRthS, i.e. the tickets of the paths whose stop IS
    the session stop - MAIN, BOS and RE: stop distance from the signal close <= 3 x ATR
    (the session-selected ATR of those lines). Capping on those lines or on the finished
    session stop gives the same price (the ETH points cap and the 1-ATR floor commute with
    it). TRAP's own stop is bounded at 1.5-2.5 ATR, so a capped session-stop input never
    changes it; OB and OD keep their own stops, uncapped.
    cap scope = the author's lines only (TV decision 10-14, before any number)
  - sl_scale (0.40..1.20): stop = close + (stop - close) x sl_scale on every path, after
    the cap.
  - tp_scale (1.0..2.0): target = close + (target - close) x tp_scale on every path,
    close = the signal bar's close. Both scales and the cap run before the 0.25 tick
    rounding of order prices.
  - max_hold_bars (0 = off): a trade open N bars (its fill bar included) exits at the
    open of bar fill+N (market), before that bar's entries; reason 'time'. Bars, not
    minutes (the 17:00 ET halt and weekends count no bars). Under FIFO pairing the oldest
    trade is the one that times out; one live bracket is cancelled with it (its own if
    still live, else the oldest).
  - be_trigger (0 = off): once a bar trades at entry + be_trigger x initial risk (longs;
    entry - ... for shorts; entry = the fill price, risk = |entry - initial stop|), that
    ticket's stop moves to its entry price from the NEXT bar on - a bar that reaches the
    trigger is still judged against the old stop. Tickets with no positive risk never arm.
  - vix_feed 'none' | 'daily': 'daily' replaces the missing CBOE:VIX 1m (PORT GAP 2) with
    CBOE's daily VIX close, New York dates. Source = hidden param _vix_file:
      'raw' (default)  C:\\EdgeLog\\_research_cache\\public_series\\cboe\\VIX_History.csv
                       (CBOE's own file, DATE MM/DD/YYYY, CLOSE), sha256 6edc3e39...b565a
      'derived'        C:\\EdgeLog\\_research_cache\\public_series\\cboe_vol_daily.csv
                       (VIX_close; ends 2025-06-27), sha256 9790df06...4e2470
    The digest is checked at every load (refused on any mismatch), and every row dated after
    the last chart bar's CME trading date is dropped immediately after parsing, before any
    other use (a 2024 run never holds a 2025 row). Rows dated on a day that is not an NQ
    session day on the tape (no bar
    13:00-15:59 ET: CME holiday sessions, which the file carries from 2022) are dropped.
    Day D's close is usable from 16:15 ET on D (bars stamped 16:15 or later); vixClose =
    the latest usable close; vixPrev = the usable close as of the session 10 NQ sessions
    earlier (sessions counted on the tape, not VIX rows). The script's own f_vixRiseThresh
    / f_vixFallThresh / vixMag then score dirScoreFull factor 6 unchanged. Warm-up: na
    (factor 0) until the tape's first 16:15 / its 11th session.

PORT GAPS (closest honest equivalent; what / why / expected effect)
  1. request.footprint(50, 70) needs TV Premium tick data we do not hold for history.
     footprint='none' (default) reproduces the script's OWN na-footprint branch exactly
     (buy/sell vol 0, delta 0, total = bar volume, POC/VAH/VAL na -> buy/sell ratios 99,
     delta slope 0): every order-flow vote is neutral, the BOS flow factor and the TRAP
     flow gate always pass. footprint='clv' = close-location buy/sell split per bar
     (approximation; POC/VAH/VAL stay na). Effect: medium - flow terms move many dynamic
     thresholds by 0.05-0.5.
  2. USI:TICK and CBOE:VIX 1m are not held -> na, as TV returns for a missing symbol:
     dirScoreFull factors 5 (TICK, up to +-2) and 6 (VIX, up to +-1.5) are 0. Effect:
     medium on the dirScore vetoes / confidence, none on the ORB/OB/BOS geometry.
     vix_feed='daily' (ours) is a daily stand-in for factor 6, not TV's 1m slope.
  3. SPY 1m not held -> ES stand-in (see spy_proxy). Only the NQ-vs-SPY relative-strength
     vote (+-0.5) uses it. Effect: small.
  4. TV daily bars for futures default to settlement-as-close; settlement is approximated
     by the close of the 15:59 ET bar (daily_close='settle'; 'last' = last trade). Feeds
     pivots PP/R1/S1/R2/S2, the ICT daily bias and the OD prior-close vote. Effect: small.
  5. ta.pivothigh/low tie rule (equal highs inside the window) is not documented; this port
     needs the pivot strictly above the left bars and >= the right bars. Effect: small to
     medium on swing-structure flags (HH/HL/LL/LH, CHoCH, SMT).
  6. A 1m bar missing at the end of an HTF bucket delays that HTF bar by one 1m bar (TV's
     historical mapping may show it one bar earlier). Effect: negligible on NQ.
  7. Warm-up: TV computes from its full chart history; the port from the first loaded bar
     (EMA200, 4h EMA21 ~4 sessions, daily [2]). Early-window trades can differ.
  8. Roll seams: TV's NQ1! rolls on its own date and holds through it; the port goes flat
     before each NOADJ switch (see above). Effect: a handful of trades per quarter.
  9. 240-minute bucket alignment: anchored at the 17:00 CT session start (TV's futures
     convention as understood here, not verified on a chart). Effect: small (4h EMAs only
     feed the h4 "not bear / not bull" gate).
 10. No account model: TV ran with initial_capital 15,000 and 5% margin, so on MNQ it can
     force margin-call liquidations once ~6-7 tickets are open. The port trades points per
     contract (max concurrent tickets seen on 2024 NQ: 6). Effect: negligible to small.
 11. TV's published run is on MNQ1!: same prices, different VOLUME. Every relative-volume
     gate here reads NQ volume. Effect: medium for trade-by-trade parity, not for the logic.

LOOK-AHEAD / REPAINT NOTES ON THE PINE (for the record): none found that uses future bars.
  The daily request is the safe [1]/[2]+lookahead_on idiom; HTF requests are lookahead_off;
  pivots are used only once confirmed; the volume profile/nearSup are end-of-bar `var`s read
  on the next bar. Non-reproducibility (not look-ahead): request.footprint depends on the
  account tier and its historical depth, and TICK/VIX/SPY sessions differ from NQ's.

Needs `index` (bar timestamps) and must run inside an engine roll context (run it through
augur_engine.run_backtest); returns None without an index.
"""
import hashlib
import io
import math
import os
import warnings

import numpy as np
import pandas as pd

STRATEGY_NAME = "MISC_SUPERSCALPER 1.0 · TV NQ/MNQ Super Scalper port (6 paths, brackets)"
DESCRIPTION = ("Port of the TradingView 'NQ/MNQ Super Scalper [BACKTEST]' (Crispigino): six "
               "1-minute entry paths (MAIN/BOS/OB/RE/TRAP/OD) behind dozens of session- and "
               "regime-scaled vetoes, one stop+limit bracket per entry, pyramiding 20, next-"
               "open fills, FIFO trade pairing, roll-seam guarded. NQ 1m ETH.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
# TV runs this on raw (unadjusted) NQ1!/MNQ1! prices and the logic mixes fixed-point and
# percent thresholds, so neither a difference nor a ratio adjustment leaves it unchanged:
# signals read raw prices, every ticket is closed before a contract switch, and the engine
# refuses any trade that would still cross one.
ROLL_SIGNAL = "raw"


def _knob_f(default, lo, hi, step, label, tip):
    return {"default": default, "min": lo, "max": hi, "step": step, "type": "float",
            "label": label, "tooltip": tip}


def _knob_i(default, lo, hi, label, tip, step=1):
    return {"default": default, "min": lo, "max": hi, "step": step, "type": "int",
            "label": label, "tooltip": tip}


def _knob_b(default, label, tip):
    return {"default": default, "type": "bool", "label": label, "tooltip": tip}


DEFAULT_PARAMS = {
    # ── 1 - Signal ──
    "longs_enabled": _knob_b(True, "Enable long trades (longsEnabled)",
                             "Script default true. Note the script's BOS and OB long paths "
                             "ignore this switch (ported as written)."),
    "eth_enabled": _knob_b(True, "Enable ETH entries (ethEnabled)",
                           "Script default true. Off = only bars inside 07:00-16:00 CT may "
                           "enter (OD is RTH-only anyway)."),
    "adx_min": _knob_i(25, 12, 38, "ADX minimum (adxMin)", "Script default 25 (trend gate)."),
    "short_min_rules": _knob_i(5, 0, 8, "Short min rules (shortMinRules)",
                               "Script default 5 of the 8-rule short volume/flow score."),
    # ── 2 - Exits ──
    "tp_buffer": _knob_f(1.0, 0.5, 1.5, 0.25, "TP buffer pts (tpBuffer)",
                         "Script default 1.0 point inside the S/R target."),
    "min_profit": _knob_f(5.0, 2.5, 7.5, 0.5, "Min profit pts (minProfit)",
                          "Script default 5.0: a ticket is only opened when its TP is at "
                          "least this far from the signal close."),
    "tp1_mult": _knob_f(4.0, 2.0, 6.0, 0.5, "TP1 x ATR (tp1Mult)",
                        "Script default 4.0: fallback S/R target distance."),
    # ── 3 - ICT features ──
    "use_orb": _knob_b(True, "Opening range votes (useORB)",
                       "Script default true. Only gates the ORB terms of dirScore (the ORB "
                       "retest entry itself ignores it, as in the script)."),
    "use_fvg": _knob_b(True, "Fair value gaps (useFVG)", "Script default true (TP/SR levels)."),
    "fvg_min_pct": _knob_f(0.3, 0.15, 0.45, 0.05, "FVG min x ATR (fvgMinPct)",
                           "Script default 0.3."),
    "use_ote": _knob_b(True, "OTE zone 62-79% (useOTE)", "Script default true (MAIN confirm)."),
    "use_bos": _knob_b(True, "BOS/MSS (useBOS)", "Script default true."),
    "bos_len": _knob_i(10, 5, 15, "BOS lookback (bosLen)", "Script default 10 bars."),
    "bos_min_rules": _knob_i(0, 0, 8, "BOS min rules (bosMinRules)",
                             "Script default 0 (= fire all); script range 0..8."),
    "use_sweep": _knob_b(True, "Liquidity sweep (useSweep)", "Script default true (TRAP path)."),
    "sweep_len": _knob_i(20, 10, 30, "Sweep lookback (sweepLen)", "Script default 20 bars."),
    "use_od": _knob_b(True, "Opening drive (useOD)", "Script default true (OD path)."),
    "retest_min_rules": _knob_i(2, 0, 5, "Retest min rules (retestMinRules)",
                                "Script default 2 (RE path score floor)."),
    # ── 5 - Liquidity ──
    "min_rel_vol": _knob_f(1.2, 0.6, 1.8, 0.1, "Min relative volume (minRelVol)",
                           "Script default 1.2 (MAIN liquidity gate)."),
    "min_atr_pts": _knob_f(5.0, 2.5, 7.5, 0.5, "Min ATR points (minAtrPts)",
                           "Script default 5.0 (MAIN liquidity gate, ATR14)."),
    # ── 7b - extra levels (feed TP/SR, so they are trading inputs) ──
    "show_qqq_levels": _knob_b(True, "QQQ levels in TP/SR (showQQQLevels)",
                               "Script default true: QQQ round numbers scaled to NQ."),
    "qqq_increment": {"default": "5.0", "type": "str", "options": ["2.5", "5.0", "10.0"],
                      "label": "QQQ level spacing (qqqIncrement)",
                      "tooltip": "Script default 5.0; script options 2.5 / 5.0 / 10.0."},
    "show_orb_mid": _knob_b(True, "ORB midline level (showORBMid)", "Script default true."),
    "show_on_range": _knob_b(True, "Overnight range levels (showONRange)",
                             "Script default true."),
    # ── 7 - overlays (the volume profile feeds TP/SR + thresholds) ──
    "hvb_lookback": _knob_i(50, 25, 75, "Volume-profile lookback (hvbLookback)",
                            "Script default 50 bars."),
    "hvb_bins": _knob_i(15, 8, 22, "Volume-profile bins (hvbBins)", "Script default 15."),
    # ── 8 - order blocks ──
    "use_ob": _knob_b(True, "Order blocks (useOB)",
                      "Script default true ('Show Order Blocks' - it gates OB detection)."),
    "use_ob_trade": _knob_b(True, "OB as trade signal (useOBTrade)", "Script default true."),
    "ob_lookback": _knob_i(20, 10, 30, "OB lookback (obLookback)", "Script default 20 bars."),
    "ob_min_move": _knob_f(1.5, 0.75, 2.25, 0.25, "OB min move x ATR (obMinMove)",
                           "Script default 1.5."),
    "ob_min_rules": _knob_i(2, 0, 5, "OB min rules (obMinRules)",
                            "Script default 2 of 5 (+1 in thin sessions)."),
    # ── port mechanics ──
    # Each carries ONE search option (TV 10-14, prereg Amendment 4): the Auto-Validate searches every str knob's
    # options, and a fill model or a stand-in feed is a fidelity setting, never a tuning knob. Passing another value
    # explicitly still works (the Stage 0 parity harness runs intrabar='tv').
    "intrabar": {"default": "worst", "type": "str", "options": ["worst"],
                 "label": "Intrabar order (fill model)",
                 "tooltip": "worst = stop leg first whenever a bar touches both legs. tv = "
                            "TradingView broker-emulator path (O-H-L-C when the high is "
                            "closer to the open, else O-L-H-C). A fill-honesty choice: pin "
                            "it, do not search it."},
    "close_rule": {"default": "fifo", "type": "str", "options": ["fifo"],
                   "label": "Trade pairing (close_entries_rule)",
                   "tooltip": "fifo = TV default for futures (an exit closes the oldest open "
                              "trade). any = each bracket closes its own ticket. Same total "
                              "points; per-trade rows differ."},
    "pyramiding": _knob_i(20, 1, 30, "Max concurrent entries (pyramiding)",
                          "Script strategy() pyramiding=20."),
    "spy_proxy": {"default": "es_rth", "type": "str", "options": ["es_rth"],
                  "label": "SPY stand-in",
                  "tooltip": "SPY 1m is not held. es_rth = ES close (roll-adjusted) sampled "
                             "09:30-16:00 ET and carried forward like SPY's session; es = ES "
                             "all hours; none = na (relative strength vote off)."},
    "footprint": {"default": "none", "type": "str", "options": ["none"],
                  "label": "Footprint data",
                  "tooltip": "request.footprint is TV Premium tick data. none = the script's "
                             "own no-footprint branch (exact). clv = close-location buy/sell "
                             "split per bar (approximation)."},
    "daily_close": {"default": "settle", "type": "str", "options": ["settle"],
                    "label": "Daily close",
                    "tooltip": "settle = TV's settlement-as-close daily bars (approximated by "
                               "the 15:59 ET bar close). last = the session's last trade."},
    # ── OUR PORT ADDITIONS (not in the script). DEFAULTS = the improvement round's chosen cell (TV 10-14, prereg
    # Amendments 3-4, 2024 development year: tp_scale 2.0, be_trigger 1.0, vix_feed daily; the other three at their
    # as-ported values). The AS-PORTED trades = AS_PORTED_OURS below, passed explicitly (tests pin both). ──
    "sl_cap_atr": {"default": "off", "type": "str", "options": ["off", "3.0"],
                   "label": "Stop cap x ATR (ours)",
                   "tooltip": "3.0 = the author's stated 'never > 3 ATR' stop cap, actually "
                              "applied on the lines he wrote it on: the session stops (MAIN, "
                              "BOS, RE tickets) sit <= 3 x ATR from the signal close. OB / OD "
                              "stops stay uncapped. off = as written (the script's "
                              "math.min/max is a no-op)."},
    "sl_scale": _knob_f(1.0, 0.40, 1.20, 0.05, "Stop distance x (ours)",
                        "Every ticket's stop distance from the signal close x this, after the "
                        "cap and after every entry gate. 1.0 = as written."),
    "tp_scale": _knob_f(2.0, 1.0, 2.0, 0.25, "Target distance x (ours)",
                        "Every path's target: tp = close + (tp - close) x this, close = the "
                        "signal bar's close; applied after the minProfit entry gate. 1.0 = as "
                        "written."),
    "max_hold_bars": _knob_i(0, 0, 240, "Max hold bars (ours)",
                             "0 = off. A ticket open N bars (fill bar included) exits at the "
                             "next bar's open (market): exit bar = fill bar + N.", step=30),
    "be_trigger": _knob_f(1.0, 0.0, 2.0, 0.5, "Breakeven trigger x risk (ours)",
                          "0 = off. Once price trades at entry + this x initial risk (longs; "
                          "mirrored for shorts) the ticket's stop moves to its entry price from "
                          "the NEXT bar on; never on the trigger bar itself."),
    "vix_feed": {"default": "daily", "type": "str", "options": ["none", "daily"],
                 "label": "VIX stand-in (ours)",
                 "tooltip": "none = CBOE:VIX 1m not held -> na (as ported). daily = CBOE daily "
                            "VIX close (sha256-pinned file), each day's close usable from 16:15 "
                            "ET, vixPrev = the close 10 NQ sessions earlier; feeds the script's "
                            "own VIX rising/falling vote."},
    "session_filter": {"default": "all", "type": "str", "options": ["all", "outside_rth", "rth"],
                       "label": "Entry session (ours)",
                       "tooltip": "all = as written. outside_rth = entries only from signal bars outside "
                                  "09:30-15:59 New York time; rth = only from signal bars inside it. Exits "
                                  "are untouched. Added for the Auto-Validate's search (prereg Amendment 5, "
                                  "MANAGER #135) after r2 found every RTH window losing on 2024."},
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {k: [v["default"]] for k, v in DEFAULT_PARAMS.items()},
    "Medium (author-knob grid)": {
        "adx_min": [20, 25, 30], "min_profit": [4.0, 5.0, 6.0],
        "short_min_rules": [4, 5, 6], "ob_min_rules": [1, 2, 3],
    },
    "Long   (adds exits + fill model)": {
        "adx_min": [20, 25, 30], "min_profit": [4.0, 5.0, 6.0], "tp1_mult": [3.0, 4.0, 5.0],
        "short_min_rules": [4, 5, 6], "ob_min_rules": [1, 2, 3],
        "intrabar": ["worst", "tv"],
    },
}

AS_PORTED_OURS = dict(sl_cap_atr="off", sl_scale=1.0, tp_scale=1.0, max_hold_bars=0, be_trigger=0.0,
                      vix_feed="none")   # the as-ported script, before the improvement round
IMPROVED_R1 = dict(sl_cap_atr="off", sl_scale=1.0, tp_scale=2.0, max_hold_bars=0, be_trigger=1.0,
                   vix_feed="daily")      # the round's chosen cell = the file defaults

PATH_NAMES = {1: "MAIN", 2: "BOS", 3: "OB", 4: "RE", 5: "TRAP", 6: "OD"}
EXIT_NAMES = {1: "stop", 2: "limit", 3: "reverse", 4: "roll_flat", 5: "time"}

# ═════════════════════════════════════════════════════════════════════════════
# Compiled kernels. Each _k_* function is plain Python that Numba can compile; the same
# source runs interpreted when Numba is missing or EDGELOG_NO_FASTLOOP=1, so both paths
# produce the same trades (tests/test_misc_superscalper.py pins it).
# ═════════════════════════════════════════════════════════════════════════════


def _fast_enabled():
    if str(os.environ.get("EDGELOG_NO_FASTLOOP", "")).strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import numba  # noqa: F401
        return True
    except Exception:
        return False


_JIT = {}
_JIT_WARNED = set()


# Below this many bars the interpreted kernels are quicker than Numba's one-time compile
# (tests, the contract suite, short probes); the output is identical either way.
_FAST_MIN_BARS = 20000
_N_BARS = [0]


def _kern(name):
    """The kernel `_k_<name>`: compiled when allowed, else the Python function itself."""
    f = {"rma": _k_rma, "hurst": _k_hurst, "pivot": _k_pivot, "state": _k_state, "fvg": _k_fvg, "vrz": _k_vrz,
         "ob": _k_ob, "bos": _k_bos, "profile": _k_profile, "walk": _k_walk}[name]
    if not _fast_enabled() or _N_BARS[0] < _FAST_MIN_BARS:
        return f
    j = _JIT.get(name)
    if j is None:
        try:
            from numba import njit
            # compiled once per process (~25 s), no on-disk cache: the engine loads strategy files under a name
            # Numba cannot re-import, and registering it needs module tricks the roll-guard lint forbids
            j = njit(cache=False)(f)
        except Exception:
            j = f
        _JIT[name] = j
    if j is f:
        return f

    def call(*a):
        try:
            return j(*a)
        except Exception as exc:
            try:                               # a stale / foreign cache entry: compile afresh
                from numba import njit
                j2 = njit(cache=False)(f)
                r = j2(*a)
                _JIT[name] = j2
                return r
            except Exception as exc2:          # a compile failure falls back, loudly
                if name not in _JIT_WARNED:
                    _JIT_WARNED.add(name)
                    warnings.warn("MISC_SUPERSCALPER: compiled kernel %s failed (%s / %s); "
                                  "running it interpreted" % (name, exc, exc2))
                _JIT[name] = f
                return f(*a)
    return call


def _k_rma(x, n, alpha):
    """Pine rma/ema recursion: seeded with the SMA of the first n valid values, re-seeded
    after an na input (Pine: sum := na(sum[1]) ? ta.sma(src, n) : alpha*src+(1-alpha)*sum[1])."""
    m = x.shape[0]
    out = np.empty(m)
    prev = np.nan
    for i in range(m):
        if prev != prev:
            if i >= n - 1:
                s = 0.0
                ok = True
                for k in range(i - n + 1, i + 1):
                    xv = x[k]
                    if xv != xv:
                        ok = False
                        break
                    s += xv
                if ok:
                    prev = s / n
        else:
            prev = alpha * x[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _k_hurst(c):
    """The script's f_hurst(): R/S over scales 50/25/13/6 (1/2/3/8 segments) of
    close-close[1] (nz), log-log slope, clamped to [0, 1]; 0.5 with fewer than 2 points."""
    n = c.shape[0]
    ret = np.zeros(n)
    for i in range(1, n):
        d = c[i] - c[i - 1]
        ret[i] = d if d == d else 0.0
    out = np.empty(n)
    lens = (50, 25, 13, 6)
    nsegs = (1, 2, 3, 8)
    for i in range(n):
        sx = 0.0
        sy = 0.0
        sxy = 0.0
        sx2 = 0.0
        npnt = 0
        for sc in range(4):
            L = lens[sc]
            rs_sum = 0.0
            v = 0
            for g in range(nsegs[sc]):
                start = g * L
                m = 0.0
                for j in range(L):
                    idx = i - start - j
                    if idx >= 0:
                        m += ret[idx]
                m /= L
                cum = 0.0
                cmax = -1e10
                cmin = 1e10
                ss = 0.0
                for j in range(L):
                    idx = i - start - j
                    rv = ret[idx] if idx >= 0 else 0.0
                    d = rv - m
                    cum += d
                    if cum > cmax:
                        cmax = cum
                    if cum < cmin:
                        cmin = cum
                    ss += d * d
                r = cmax - cmin
                s = math.sqrt(ss / L)
                rs = r / s if (s > 0 and r > 0) else 0.0
                if rs > 0:
                    rs_sum += rs
                    v += 1
            if v > 0:
                lx = math.log(L)
                ly = math.log(rs_sum / v)
                sx += lx
                sy += ly
                sxy += lx * ly
                sx2 += lx * lx
                npnt += 1
        hval = 0.5
        if npnt >= 2:
            den = npnt * sx2 - sx * sx
            if abs(den) > 1e-10:
                hval = (npnt * sxy - sx * sy) / den
        out[i] = max(0.0, min(1.0, hval))
    return out


def _k_pivot(x, left, right, is_high):
    """ta.pivothigh/low(src, left, right): the value `right` bars back when it is strictly
    beyond every left bar and at least as extreme as every right bar; na otherwise."""
    n = x.shape[0]
    out = np.empty(n)
    out[:] = np.nan
    for i in range(left + right, n):
        p = x[i - right]
        if p != p:
            continue
        ok = True
        for k in range(i - right - left, i - right):
            v = x[k]
            if v != v or (is_high and v >= p) or ((not is_high) and v <= p):
                ok = False
                break
        if ok:
            for k in range(i - right + 1, i + 1):
                v = x[k]
                if v != v or (is_high and v > p) or ((not is_high) and v < p):
                    ok = False
                    break
        if ok:
            out[i] = p
    return out


def _k_state(o, h, l, c, in_rth, in_asia, in_london, new_day, in_premarket, in_overnight,
             in_orb_build, orb_lock_bar):
    """Session ranges, ORB / pre-market / overnight levels, ORB break flags (script order)."""
    n = c.shape[0]
    nan = np.nan
    rth_hi = np.empty(n); rth_lo = np.empty(n)
    asia_hi = np.empty(n); asia_lo = np.empty(n)
    lon_hi = np.empty(n); lon_lo = np.empty(n)
    orb_hi = np.empty(n); orb_lo = np.empty(n); orb_mid = np.empty(n)
    orb_locked = np.zeros(n, np.bool_)
    pm_hi = np.empty(n); pm_lo = np.empty(n); pm_mid = np.empty(n)
    on_hi = np.empty(n); on_lo = np.empty(n)
    on_hi_prev = np.empty(n); on_lo_prev = np.empty(n)
    brk_up = np.zeros(n, np.bool_); brk_dn = np.zeros(n, np.bool_)
    dev_h = nan; dev_l = nan; rh = nan; rl = nan; prev_rth = False
    ah = nan; al = nan; prev_asia = False
    lh = nan; ll = nan; prev_lon = False
    oh = nan; ol = nan; om = nan; locked = False
    ph = nan; pl = nan; pmid = nan
    nh = nan; nl = nan
    bu = False; bd = False
    for i in range(n):
        hi = h[i]; lo = l[i]
        if in_rth[i]:
            if not prev_rth:
                dev_h = hi; dev_l = lo
            else:
                dev_h = max(dev_h if dev_h == dev_h else hi, hi)
                dev_l = min(dev_l if dev_l == dev_l else lo, lo)
        if (not in_rth[i]) and prev_rth:
            rh = dev_h; rl = dev_l
        prev_rth = in_rth[i]
        if in_asia[i]:
            if not prev_asia:
                ah = hi; al = lo
            else:
                ah = max(ah if ah == ah else hi, hi)
                al = min(al if al == al else lo, lo)
        prev_asia = in_asia[i]
        if in_london[i]:
            if not prev_lon:
                lh = hi; ll = lo
            else:
                lh = max(lh if lh == lh else hi, hi)
                ll = min(ll if ll == ll else lo, lo)
        prev_lon = in_london[i]
        on_hi_prev[i] = nh; on_lo_prev[i] = nl
        if new_day[i]:
            oh = nan; ol = nan; om = nan; locked = False
            ph = nan; pl = nan; pmid = nan
            nh = nan; nl = nan
        if in_premarket[i]:
            ph = hi if ph != ph else max(ph, hi)
            pl = lo if pl != pl else min(pl, lo)
            pmid = (ph + pl) / 2.0
        if in_overnight[i]:
            nh = hi if nh != nh else max(nh, hi)
            nl = lo if nl != nl else min(nl, lo)
        if in_orb_build[i] and not locked:
            oh = hi if oh != oh else max(oh, hi)
            ol = lo if ol != ol else min(ol, lo)
        if orb_lock_bar[i]:
            locked = True
            om = (oh + ol) / 2.0 if (oh == oh and ol == ol) else nan
        if new_day[i]:
            bu = False; bd = False
        if locked and oh == oh:
            if c[i] > oh * 1.001:
                bu = True
            if c[i] < ol * 0.999:
                bd = True
        rth_hi[i] = rh; rth_lo[i] = rl
        asia_hi[i] = ah; asia_lo[i] = al
        lon_hi[i] = lh; lon_lo[i] = ll
        orb_hi[i] = oh; orb_lo[i] = ol; orb_mid[i] = om; orb_locked[i] = locked
        pm_hi[i] = ph; pm_lo[i] = pl; pm_mid[i] = pmid
        on_hi[i] = nh; on_lo[i] = nl
        brk_up[i] = bu; brk_dn[i] = bd
    return (rth_hi, rth_lo, asia_hi, asia_lo, lon_hi, lon_lo, orb_hi, orb_lo, orb_mid,
            orb_locked, pm_hi, pm_lo, pm_mid, on_hi, on_lo, on_hi_prev, on_lo_prev,
            brk_up, brk_dn)


def _k_fvg(h, l, c, bull_new, bear_new, max_age, max_fill, max_touch):
    """FVG zone tracking with fill ratio / age / touch count and the script's expiry."""
    n = c.shape[0]
    nan = np.nan
    bhi_o = np.empty(n); blo_o = np.empty(n); bfill_o = np.empty(n)
    bage_o = np.empty(n); btouch_o = np.empty(n)
    rhi_o = np.empty(n); rlo_o = np.empty(n); rfill_o = np.empty(n)
    rage_o = np.empty(n); rtouch_o = np.empty(n)
    bhi = nan; blo = nan; bfill = 0.0; bage = 0; btouch = 0
    rhi = nan; rlo = nan; rfill = 0.0; rage = 0; rtouch = 0
    for i in range(n):
        if bull_new[i]:
            bhi = l[i]; blo = h[i - 2]; bfill = 0.0; bage = 0; btouch = 0
        if bear_new[i]:
            rhi = l[i - 2]; rlo = h[i]; rfill = 0.0; rage = 0; rtouch = 0
        if bhi == bhi and blo == blo:
            bage += 1
            sz = bhi - blo
            if sz > 0 and l[i] <= bhi and l[i] >= blo:
                bfill = max(bfill, (bhi - l[i]) / sz)
                btouch += 1
        if rhi == rhi and rlo == rlo:
            rage += 1
            sz = rhi - rlo
            if sz > 0 and h[i] >= rlo and h[i] <= rhi:
                rfill = max(rfill, (h[i] - rlo) / sz)
                rtouch += 1
        if bhi == bhi and (c[i] < blo or bage > max_age[i] or bfill > max_fill[i]
                           or btouch > max_touch[i]):
            bhi = nan; blo = nan
        if rlo == rlo and (c[i] > rhi or rage > max_age[i] or rfill > max_fill[i]
                           or rtouch > max_touch[i]):
            rhi = nan; rlo = nan
        bhi_o[i] = bhi; blo_o[i] = blo; bfill_o[i] = bfill; bage_o[i] = bage
        btouch_o[i] = btouch
        rhi_o[i] = rhi; rlo_o[i] = rlo; rfill_o[i] = rfill; rage_o[i] = rage
        rtouch_o[i] = rtouch
    return bhi_o, blo_o, bfill_o, bage_o, btouch_o, rhi_o, rlo_o, rfill_o, rage_o, rtouch_o


def _k_vrz(is_vrz, h, l):
    """Last three volume-range-zone bars (high, low) and the newest mid."""
    n = h.shape[0]
    vh = np.empty((n, 3)); vl = np.empty((n, 3)); vmid = np.empty(n)
    ah = np.empty(3); al = np.empty(3); am = np.empty(3)
    ah[:] = np.nan; al[:] = np.nan; am[:] = np.nan
    cnt = 0
    for i in range(n):
        if is_vrz[i]:
            if cnt < 3:
                ah[cnt] = h[i]; al[cnt] = l[i]; am[cnt] = (h[i] + l[i]) / 2.0
                cnt += 1
            else:
                for k in range(2):
                    ah[k] = ah[k + 1]; al[k] = al[k + 1]; am[k] = am[k + 1]
                ah[2] = h[i]; al[2] = l[i]; am[2] = (h[i] + l[i]) / 2.0
        for k in range(3):
            vh[i, k] = ah[k]; vl[i, k] = al[k]
        vmid[i] = am[cnt - 1] if cnt > 0 else np.nan
    return vh, vl, vmid


def _k_ob(o, h, l, c, enabled, strong_up, strong_dn, stars_bull, stars_bear, min_dyn,
          sl_dist_long, sl_dist_short, lookback, use_trade):
    """Order-block search (first opposite candle within `lookback` bars) + trade fire."""
    n = c.shape[0]
    bull_mid = np.empty(n); bear_mid = np.empty(n)
    bull_fire = np.zeros(n, np.bool_); bear_fire = np.zeros(n, np.bool_)
    bull_sl = np.empty(n); bear_sl = np.empty(n)
    bull_sl[:] = np.nan; bear_sl[:] = np.nan
    bm = np.nan
    rm = np.nan
    for i in range(n):
        if enabled[i]:
            kmax = min(lookback, i - 1)
            if strong_up[i]:
                for k in range(1, kmax + 1):
                    if c[i - k] < o[i - k]:
                        bm = (h[i - k] + l[i - k]) / 2.0
                        if use_trade and stars_bull[i] >= min_dyn[i]:
                            bull_fire[i] = True
                            bull_sl[i] = l[i - k] - sl_dist_long[i] * 0.25
                        break
            if strong_dn[i]:
                for k in range(1, kmax + 1):
                    if c[i - k] > o[i - k]:
                        rm = (h[i - k] + l[i - k]) / 2.0
                        if use_trade and stars_bear[i] >= min_dyn[i]:
                            bear_fire[i] = True
                            bear_sl[i] = h[i - k] + sl_dist_short[i] * 0.25
                        break
        bull_mid[i] = bm
        bear_mid[i] = rm
    return bull_mid, bear_mid, bull_fire, bull_sl, bear_fire, bear_sl


def _k_bos(raw_bull, raw_bear):
    """bullBOS / bearBOS with the shared 10-bar cooldown (lastBosBar starts at 0)."""
    n = raw_bull.shape[0]
    bull = np.zeros(n, np.bool_); bear = np.zeros(n, np.bool_)
    last = 0
    for i in range(n):
        b = raw_bull[i] and (i - last > 10)
        s = raw_bear[i] and (i - last > 10)
        bull[i] = b; bear[i] = s
        if b or s:
            last = i
    return bull, bear


def _k_profile(c, o, v, hvb_hi, hvb_lo, lookback, bins):
    """Rolling volume profile (POC / value area / point of void / zones 2-3 / node
    strength / POC buy share), end-of-bar `var` values exactly as the script's loops."""
    n = c.shape[0]
    z1o = np.empty(n); z2o = np.empty(n); z3o = np.empty(n); povo = np.empty(n)
    vaho = np.empty(n); valo = np.empty(n); pbpo = np.empty(n); prbo = np.empty(n)
    prso = np.empty(n); nso = np.empty(n)
    z1 = np.nan; z2 = np.nan; z3 = np.nan; pov = np.nan; vah = np.nan; val = np.nan
    pbp = 50.0; prb = 0.0; prs = 0.0; ns = 0.0
    calc = np.zeros(bins); buy = np.zeros(bins); sell = np.zeros(bins)
    for i in range(n):
        hi = hvb_hi[i]; lo = hvb_lo[i]
        bs = (hi - lo) / bins if hi > lo else 0.0
        if bs > 0 and i - (lookback - 1) >= 0:
            for b in range(bins):
                calc[b] = 0.0; buy[b] = 0.0; sell[b] = 0.0
            for k in range(lookback):
                j = i - k
                bi = math.floor((c[j] - lo) / bs)
                if bi > bins - 1:
                    bi = bins - 1
                if bi < 0:
                    bi = 0
                bidx = int(bi)
                bv = v[j] if v[j] == v[j] else 0.0
                calc[bidx] += bv
                if c[j] > o[j]:
                    buy[bidx] += bv
                elif c[j] < o[j]:
                    sell[bidx] += bv
                else:
                    buy[bidx] += bv * 0.5
                    sell[bidx] += bv * 0.5
            tot = 0.0; poc = 0; pocv = 0.0
            for b in range(bins):
                bv = calc[b]
                tot += bv
                if bv > pocv:
                    pocv = bv; poc = b
            z1 = lo + poc * bs + bs / 2.0
            pb = buy[poc]; ps = sell[poc]
            pbp = pb / pocv * 100.0 if pocv > 0 else 50.0
            prb = pb; prs = ps
            target = tot * 0.70
            vav = pocv; lo_i = poc; hi_i = poc
            for _s in range(bins):
                if vav >= target or (lo_i <= 0 and hi_i >= bins - 1):
                    break
                vb = calc[lo_i - 1] if lo_i > 0 else 0.0
                va = calc[hi_i + 1] if hi_i < bins - 1 else 0.0
                if vb >= va and lo_i > 0:
                    lo_i -= 1; vav += vb
                elif hi_i < bins - 1:
                    hi_i += 1; vav += va
                elif lo_i > 0:
                    lo_i -= 1; vav += vb
            vah = lo + (hi_i + 1) * bs
            val = lo + lo_i * bs
            pidx = poc; pmin = pocv
            for b in range(lo_i, hi_i + 1):
                if b != poc and calc[b] < pmin:
                    pmin = calc[b]; pidx = b
            pov = lo + pidx * bs + bs / 2.0
            ns = pocv / tot * 100.0 if tot > 0 else 0.0
            calc[poc] = 0.0
            for rank in range(2):
                mi = 0; mv = 0.0
                for b in range(bins):
                    if calc[b] > mv:
                        mv = calc[b]; mi = b
                if mv > 0:
                    zm = lo + mi * bs + bs / 2.0
                    if rank == 0:
                        z2 = zm
                    else:
                        z3 = zm
                    calc[mi] = 0.0
        z1o[i] = z1; z2o[i] = z2; z3o[i] = z3; povo[i] = pov; vaho[i] = vah; valo[i] = val
        pbpo[i] = pbp; prbo[i] = prb; prso[i] = prs; nso[i] = ns
    return z1o, z2o, z3o, povo, vaho, valo, pbpo, prbo, prso, nso


def _k_walk(o, h, l, c, chain_l, tp_l, sl_l, od_l, odtp_l, odsl_l,
            chain_s, tp_s, sl_s, od_s, odtp_s, odsl_s,
            no_fill, flat_bar, cap, mode_tv, fifo, max_trades, max_hold, be_mult):
    """The broker: next-open market entries, per-ticket stop/limit brackets active from
    the fill bar, intrabar path ordering, FIFO / own-ticket pairing, pyramiding cap,
    same-bar reversal, roll-seam force-flat. Trades still open at the end are dropped.
    OUR PORT ADDITIONS (0 = off, the as-ported broker exactly): max_hold = a trade open
    that many bars exits at the next open (market, before that bar's entries); be_mult =
    once a bar trades at entry +/- be_mult x initial risk, that ticket's stop moves to its
    entry price from the NEXT bar on."""
    n = c.shape[0]
    cap_alloc = cap + 4
    # open trades (FIFO queue, oldest first)
    t_bar = np.zeros(cap_alloc, np.int64); t_px = np.zeros(cap_alloc)
    t_path = np.zeros(cap_alloc, np.int64); t_id = np.zeros(cap_alloc, np.int64)
    t_sig = np.zeros(cap_alloc, np.int64); t_sl = np.zeros(cap_alloc)
    t_tp = np.zeros(cap_alloc)
    ntr = 0
    # live brackets (insertion order = age)
    b_sl = np.zeros(cap_alloc); b_tp = np.zeros(cap_alloc)
    b_own = np.zeros(cap_alloc, np.int64)
    b_ep = np.zeros(cap_alloc); b_trig = np.zeros(cap_alloc)       # breakeven (ours)
    b_arm = np.zeros(cap_alloc, np.bool_)
    nbr = 0
    side = 0
    next_id = 0
    # pending orders (placed at bar u-1 close)
    p_side = np.zeros(2, np.int64); p_path = np.zeros(2, np.int64)
    p_tp = np.zeros(2); p_sl = np.zeros(2); p_rank = np.zeros(2, np.int64)
    p_sig = np.zeros(2, np.int64)
    npd = 0
    # outputs
    oe = np.zeros(max_trades, np.int64); ox = np.zeros(max_trades, np.int64)
    osd = np.zeros(max_trades, np.int64); oep = np.zeros(max_trades)
    oxp = np.zeros(max_trades); ors = np.zeros(max_trades, np.int64)
    opa = np.zeros(max_trades, np.int64); osg = np.zeros(max_trades, np.int64)
    osl = np.zeros(max_trades); otp = np.zeros(max_trades)
    obsl = np.zeros(max_trades); obtp = np.zeros(max_trades)
    nout = 0
    max_open = 0
    f_key = np.zeros(cap_alloc); f_px = np.zeros(cap_alloc)
    f_rs = np.zeros(cap_alloc, np.int64); f_b = np.zeros(cap_alloc, np.int64)
    for u in range(n):
        # ── 0) max-hold market exits at this bar's open (ours; oldest trade first) ──
        if max_hold > 0:
            while ntr > 0 and u - t_bar[0] >= max_hold:
                if nout < max_trades:
                    oe[nout] = t_bar[0]; ox[nout] = u; osd[nout] = side
                    oep[nout] = t_px[0]; oxp[nout] = o[u]; ors[nout] = 5
                    opa[nout] = t_path[0]; osg[nout] = t_sig[0]
                    osl[nout] = t_sl[0]; otp[nout] = t_tp[0]
                    obsl[nout] = np.nan; obtp[nout] = np.nan
                    nout += 1
                bi = 0                              # its own bracket if alive, else the oldest
                for b in range(nbr):
                    if b_own[b] == t_id[0]:
                        bi = b
                        break
                for b in range(bi, nbr - 1):
                    b_sl[b] = b_sl[b + 1]; b_tp[b] = b_tp[b + 1]; b_own[b] = b_own[b + 1]
                    b_ep[b] = b_ep[b + 1]; b_trig[b] = b_trig[b + 1]; b_arm[b] = b_arm[b + 1]
                nbr -= 1
                for j in range(ntr - 1):
                    t_bar[j] = t_bar[j + 1]; t_px[j] = t_px[j + 1]
                    t_path[j] = t_path[j + 1]; t_id[j] = t_id[j + 1]
                    t_sig[j] = t_sig[j + 1]; t_sl[j] = t_sl[j + 1]; t_tp[j] = t_tp[j + 1]
                ntr -= 1
            if ntr == 0:
                side = 0
                nbr = 0
        # ── 1) market entries at this bar's open ──
        if npd > 0:
            order0 = 0
            if npd == 2 and p_rank[1] < p_rank[0]:
                order0 = 1
            if not no_fill[u]:
                for q in range(npd):
                    k = order0 if q == 0 else 1 - order0
                    sd = p_side[k]
                    if ntr > 0 and side != sd:
                        for j in range(ntr):          # reversal closes every open trade
                            if nout < max_trades:
                                oe[nout] = t_bar[j]; ox[nout] = u; osd[nout] = side
                                oep[nout] = t_px[j]; oxp[nout] = o[u]; ors[nout] = 3
                                opa[nout] = t_path[j]; osg[nout] = t_sig[j]
                                osl[nout] = t_sl[j]; otp[nout] = t_tp[j]
                                obsl[nout] = np.nan; obtp[nout] = np.nan
                                nout += 1
                        ntr = 0
                        nbr = 0
                        side = 0
                    if ntr < cap:
                        t_bar[ntr] = u; t_px[ntr] = o[u]; t_path[ntr] = p_path[k]
                        t_id[ntr] = next_id; t_sig[ntr] = p_sig[k]
                        t_sl[ntr] = p_sl[k]; t_tp[ntr] = p_tp[k]
                        ntr += 1
                        b_sl[nbr] = p_sl[k]; b_tp[nbr] = p_tp[k]; b_own[nbr] = next_id
                        b_ep[nbr] = o[u]; b_trig[nbr] = np.nan; b_arm[nbr] = False
                        if be_mult > 0.0:
                            risk = (o[u] - p_sl[k]) if sd > 0 else (p_sl[k] - o[u])
                            if risk > 0.0:
                                b_trig[nbr] = o[u] + sd * be_mult * risk
                        nbr += 1
                        next_id += 1
                        side = sd
                        if ntr > max_open:
                            max_open = ntr
            npd = 0
        # ── 2) bracket exits along the intrabar path ──
        if nbr > 0:
            ou = o[u]; hu = h[u]; lu = l[u]
            if mode_tv:
                high_first = (hu - ou) < (ou - lu)
            else:
                high_first = side < 0                 # adverse leg first for the position
            rng_up = hu - ou
            rng_dn = ou - lu
            rng_hl = hu - lu
            nf = 0
            for b in range(nbr):
                s_ = b_sl[b]; t_ = b_tp[b]
                has_s = s_ == s_
                has_t = t_ == t_
                key = -1.0
                px = 0.0
                rs = 0
                if side > 0:
                    if has_s and ou <= s_:
                        key = 0.0; px = ou; rs = 1
                    elif has_t and ou >= t_:
                        key = 0.0; px = ou; rs = 2
                    else:
                        hit_s = has_s and lu <= s_
                        hit_t = has_t and hu >= t_
                        if high_first:
                            if hit_t:
                                key = 1.0 + (0.999 * (t_ - ou) / rng_up if rng_up > 0 else 0.0)
                                px = t_; rs = 2
                            elif hit_s:
                                key = 2.0 + (0.999 * (hu - s_) / rng_hl if rng_hl > 0 else 0.0)
                                px = s_; rs = 1
                        else:
                            if hit_s:
                                key = 1.0 + (0.999 * (ou - s_) / rng_dn if rng_dn > 0 else 0.0)
                                px = s_; rs = 1
                            elif hit_t:
                                key = 2.0 + (0.999 * (t_ - lu) / rng_hl if rng_hl > 0 else 0.0)
                                px = t_; rs = 2
                else:
                    if has_s and ou >= s_:
                        key = 0.0; px = ou; rs = 1
                    elif has_t and ou <= t_:
                        key = 0.0; px = ou; rs = 2
                    else:
                        hit_s = has_s and hu >= s_
                        hit_t = has_t and lu <= t_
                        if high_first:
                            if hit_s:
                                key = 1.0 + (0.999 * (s_ - ou) / rng_up if rng_up > 0 else 0.0)
                                px = s_; rs = 1
                            elif hit_t:
                                key = 2.0 + (0.999 * (hu - t_) / rng_hl if rng_hl > 0 else 0.0)
                                px = t_; rs = 2
                        else:
                            if hit_t:
                                key = 1.0 + (0.999 * (ou - t_) / rng_dn if rng_dn > 0 else 0.0)
                                px = t_; rs = 2
                            elif hit_s:
                                key = 2.0 + (0.999 * (s_ - lu) / rng_hl if rng_hl > 0 else 0.0)
                                px = s_; rs = 1
                if key >= 0.0:
                    f_key[nf] = key; f_px[nf] = px; f_rs[nf] = rs; f_b[nf] = b
                    nf += 1
            if nf > 0:
                # stable insertion sort by path position (ties: older bracket first)
                for a in range(1, nf):
                    kk = f_key[a]; kp = f_px[a]; kr = f_rs[a]; kb = f_b[a]
                    j = a - 1
                    while j >= 0 and f_key[j] > kk:
                        f_key[j + 1] = f_key[j]; f_px[j + 1] = f_px[j]
                        f_rs[j + 1] = f_rs[j]; f_b[j + 1] = f_b[j]
                        j -= 1
                    f_key[j + 1] = kk; f_px[j + 1] = kp; f_rs[j + 1] = kr; f_b[j + 1] = kb
                dead = np.zeros(nbr, np.bool_)
                for q in range(nf):
                    b = f_b[q]
                    dead[b] = True
                    ti = 0
                    if not fifo:
                        for j in range(ntr):
                            if t_id[j] == b_own[b]:
                                ti = j
                                break
                    if nout < max_trades:
                        oe[nout] = t_bar[ti]; ox[nout] = u; osd[nout] = side
                        oep[nout] = t_px[ti]; oxp[nout] = f_px[q]; ors[nout] = f_rs[q]
                        opa[nout] = t_path[ti]; osg[nout] = t_sig[ti]
                        osl[nout] = t_sl[ti]; otp[nout] = t_tp[ti]
                        obsl[nout] = b_sl[b]; obtp[nout] = b_tp[b]
                        nout += 1
                    for j in range(ti, ntr - 1):
                        t_bar[j] = t_bar[j + 1]; t_px[j] = t_px[j + 1]
                        t_path[j] = t_path[j + 1]; t_id[j] = t_id[j + 1]
                        t_sig[j] = t_sig[j + 1]; t_sl[j] = t_sl[j + 1]; t_tp[j] = t_tp[j + 1]
                    ntr -= 1
                m = 0
                for b in range(nbr):
                    if not dead[b]:
                        b_sl[m] = b_sl[b]; b_tp[m] = b_tp[b]; b_own[m] = b_own[b]
                        b_ep[m] = b_ep[b]; b_trig[m] = b_trig[b]; b_arm[m] = b_arm[b]
                        m += 1
                nbr = m
                if ntr == 0:
                    side = 0
        # ── 2b) breakeven arming (ours): a surviving ticket whose trigger traded on this
        #        bar gets its stop at entry from the next bar on (this bar's fills are done) ──
        if be_mult > 0.0 and nbr > 0:
            for b in range(nbr):
                tg = b_trig[b]
                if not b_arm[b] and tg == tg:
                    if (side > 0 and h[u] >= tg) or (side < 0 and l[u] <= tg):
                        b_arm[b] = True
                        if side > 0:
                            b_sl[b] = max(b_sl[b], b_ep[b])
                        else:
                            b_sl[b] = min(b_sl[b], b_ep[b])
        # ── 3) roll-seam eve: flat at this bar's close ──
        if flat_bar[u] and ntr > 0:
            for j in range(ntr):
                if nout < max_trades:
                    oe[nout] = t_bar[j]; ox[nout] = u; osd[nout] = side
                    oep[nout] = t_px[j]; oxp[nout] = c[u]; ors[nout] = 4
                    opa[nout] = t_path[j]; osg[nout] = t_sig[j]
                    osl[nout] = t_sl[j]; otp[nout] = t_tp[j]
                    obsl[nout] = np.nan; obtp[nout] = np.nan
                    nout += 1
            ntr = 0
            nbr = 0
            side = 0
        # ── 4) signals at this bar's close -> orders for the next open ──
        if flat_bar[u] or u == n - 1:
            continue
        is_long = ntr > 0 and side > 0
        is_short = ntr > 0 and side < 0
        is_flat = ntr == 0
        if chain_l[u] > 0 and not is_short:
            p_side[npd] = 1; p_path[npd] = chain_l[u]; p_tp[npd] = tp_l[u]
            p_sl[npd] = sl_l[u]; p_rank[npd] = 2 * (chain_l[u] - 1); p_sig[npd] = u
            npd += 1
        elif od_l[u] and is_flat:
            p_side[npd] = 1; p_path[npd] = 6; p_tp[npd] = odtp_l[u]
            p_sl[npd] = odsl_l[u]; p_rank[npd] = 10; p_sig[npd] = u
            npd += 1
        if chain_s[u] > 0 and not is_long:
            p_side[npd] = -1; p_path[npd] = chain_s[u]; p_tp[npd] = tp_s[u]
            p_sl[npd] = sl_s[u]; p_rank[npd] = 2 * (chain_s[u] - 1) + 1; p_sig[npd] = u
            npd += 1
        elif od_s[u] and is_flat:
            p_side[npd] = -1; p_path[npd] = 6; p_tp[npd] = odtp_s[u]
            p_sl[npd] = odsl_s[u]; p_rank[npd] = 11; p_sig[npd] = u
            npd += 1
    return (oe[:nout], ox[:nout], osd[:nout], oep[:nout], oxp[:nout], ors[:nout],
            opa[:nout], osg[:nout], osl[:nout], otp[:nout], obsl[:nout], obtp[:nout],
            max_open)


# ═════════════════════════════════════════════════════════════════════════════
# Pine ta.* helpers (vectorized) and small utilities
# ═════════════════════════════════════════════════════════════════════════════

def _f(x):
    return np.asarray(x, dtype=np.float64)


def _sh(x, k):
    """x[k] (Pine history), na-padded."""
    x = _f(x)
    out = np.full(x.shape, np.nan)
    if 0 < k < len(x):
        out[k:] = x[:len(x) - k]
    elif k == 0:
        out[:] = x
    return out


def _shb(x, k):
    """bool history: Pine v6 bools are never na, out-of-range history reads false."""
    x = np.asarray(x, dtype=bool)
    out = np.zeros(x.shape, bool)
    if 0 < k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def _nz(x, y=0.0):
    x = _f(x)
    return np.where(np.isnan(x), y, x)


def _clamp(x, lo, hi):
    """math.max(lo, math.min(hi, x)) - na propagates."""
    return np.maximum(lo, np.minimum(hi, x))


def _ne(a, b):
    """Pine `a != b` - false when either side is na."""
    a = _f(a); b = _f(b)
    return (a != b) & ~np.isnan(a) & ~np.isnan(b)


def _sel(*args):
    """Pine ternary chain c1 ? v1 : c2 ? v2 : ... : default (first true condition wins)."""
    default = args[-1]
    pairs = args[:-1]
    conds = [np.asarray(pairs[i], dtype=bool) for i in range(0, len(pairs), 2)]
    shape = conds[0].shape
    vals = [np.broadcast_to(_f(pairs[i + 1]), shape) for i in range(0, len(pairs), 2)]
    return np.select(conds, vals, default=np.broadcast_to(_f(default), shape))


def _S(ph, v_open, v_morning, v_lunch, v_afternoon, v_last, v_premkt, v_london, v_asia):
    """A ternary chain over the eight session flags only. isOpen/isMorning/isLunch/
    isAfternoon/isLast/inPreMkt/inLondon/inAsia partition the CT day, so the chain is a
    table lookup on the bar's phase whatever order the script lists them in."""
    return np.array([v_open, v_morning, v_lunch, v_afternoon, v_last, v_premkt, v_london,
                     v_asia], dtype=np.float64)[ph]


def _sma(x, n):
    return pd.Series(_f(x)).rolling(int(n), min_periods=int(n)).mean().to_numpy()


def _rsum(x, n):
    return pd.Series(_f(x)).rolling(int(n), min_periods=int(n)).sum().to_numpy()


def _highest(x, n):
    return pd.Series(_f(x)).rolling(int(n), min_periods=int(n)).max().to_numpy()


def _lowest(x, n):
    return pd.Series(_f(x)).rolling(int(n), min_periods=int(n)).min().to_numpy()


def _stdev(x, n):
    return pd.Series(_f(x)).rolling(int(n), min_periods=int(n)).std(ddof=0).to_numpy()


def _rma(x, n):
    return _kern("rma")(np.ascontiguousarray(_f(x)), int(n), 1.0 / n)


def _ema(x, n):
    return _kern("rma")(np.ascontiguousarray(_f(x)), int(n), 2.0 / (n + 1.0))


def _tr(h, l, c, handle_na):
    c1 = _sh(c, 1)
    tr = np.maximum(np.maximum(h - l, np.abs(h - c1)), np.abs(l - c1))
    if len(tr):
        tr[0] = (h[0] - l[0]) if handle_na else np.nan
    return tr


def _atr(h, l, c, n):
    return _rma(_tr(h, l, c, True), n)


def _fixnan(x):
    return pd.Series(_f(x)).ffill().to_numpy()


def _adx(h, l, c, di_len, adx_len):
    up = h - _sh(h, 1)
    down = -(l - _sh(l, 1))
    with np.errstate(invalid="ignore"):
        plus_dm = np.where(np.isnan(up), np.nan, np.where((up > down) & (up > 0), up, 0.0))
        minus_dm = np.where(np.isnan(down), np.nan, np.where((down > up) & (down > 0), down, 0.0))
    trur = _rma(_tr(h, l, c, False), di_len)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = _fixnan(100.0 * _rma(plus_dm, di_len) / trur)
        minus = _fixnan(100.0 * _rma(minus_dm, di_len) / trur)
        s = plus + minus
        return 100.0 * _rma(np.abs(plus - minus) / np.where(s == 0, 1.0, s), adx_len)


def _rsi(x, n):
    x1 = _sh(x, 1)
    u = np.maximum(x - x1, 0.0)
    d = np.maximum(x1 - x, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = _rma(u, n) / _rma(d, n)
        return 100.0 - 100.0 / (1.0 + rs)


def _linreg(y, L, off):
    y = _f(y)
    n = len(y)
    out = np.full(n, np.nan)
    if n >= L:
        W = np.lib.stride_tricks.sliding_window_view(y, L)
        x = np.arange(L, dtype=np.float64)
        sx = x.sum(); sxx = (x * x).sum()
        sy = W.sum(axis=1)
        sxy = W @ x
        slope = (L * sxy - sx * sy) / (L * sxx - sx * sx)
        intercept = sy / L - slope * sx / L
        out[L - 1:] = intercept + slope * (L - 1 - off)
    return out


def _mfi(src, v, n):
    chg = src - _sh(src, 1)
    with np.errstate(invalid="ignore"):
        up_src = np.where(chg <= 0.0, 0.0, src)
        dn_src = np.where(chg >= 0.0, 0.0, src)
    upper = _rsum(v * up_src, n)
    lower = _rsum(v * dn_src, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 - 100.0 / (1.0 + upper / lower)


def _group_cumsum(x, g):
    return pd.Series(_f(x)).groupby(np.asarray(g)).cumsum().to_numpy()


def _last_two(piv):
    """(newest, previous) confirmed pivot value as of each bar (the sl0/sl1 chain)."""
    mask = ~np.isnan(piv)
    vals = piv[mask]
    cnt = np.cumsum(mask)
    v0 = np.full(len(piv), np.nan)
    v1 = np.full(len(piv), np.nan)
    if len(vals):
        i0 = cnt - 1
        ok0 = i0 >= 0
        v0[ok0] = vals[i0[ok0]]
        i1 = cnt - 2
        ok1 = i1 >= 0
        v1[ok1] = vals[i1[ok1]]
    return v0, v1


def _first_code(oks):
    """1-based index of the first true path per bar (the script's priority chain), 0 = none."""
    out = np.zeros(len(oks[0]), np.int64)
    for k in range(len(oks) - 1, -1, -1):
        out = np.where(np.asarray(oks[k], bool), k + 1, out)
    return out.astype(np.int64)


def _epoch_s(idx):
    """Unix seconds of a tz-aware DatetimeIndex whatever its storage unit."""
    try:
        idx = idx.as_unit("ns")
    except Exception:
        pass
    return (idx.asi8 // 10 ** 9).astype(np.int64)


def _in_sess(m, a, b):
    """time(timeframe.period, "HHMM-HHMM", tz) != 0 for a bar opening at minute-of-day m."""
    s = (a // 100) * 60 + a % 100
    e = (b // 100) * 60 + b % 100
    if s < e:
        return (m >= s) & (m < e)
    return (m >= s) | (m < e)


# ═════════════════════════════════════════════════════════════════════════════
# Cross-symbol feeds (ES1!, SPY stand-in, QQQ) - read only the run's own window
# ═════════════════════════════════════════════════════════════════════════════

_FEED_MEMO = {}
_FEED_WARNED = set()


def _csv_time_slice(path, t_lo, t_hi):
    """Rows with t_lo <= time <= t_hi from a time-sorted master CSV, reading only that
    byte range (binary search on line starts), so no row past t_hi is ever parsed."""
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        header = fh.readline()
        data_start = fh.tell()

        def line_time_at(off):
            if off <= data_start:
                fh.seek(data_start)
            else:
                fh.seek(off - 1)
                fh.readline()
            line = fh.readline()
            if not line:
                return None
            return int(float(line.split(b",", 1)[0]))

        def lower_bound(t):
            lo, hi = data_start, size
            while hi - lo > 65536:
                mid = (lo + hi) // 2
                tm = line_time_at(mid)
                if tm is None or tm >= t:
                    hi = mid
                else:
                    lo = mid
            if lo <= data_start:
                fh.seek(data_start)
            else:
                fh.seek(lo - 1)
                fh.readline()
            while True:
                pos = fh.tell()
                line = fh.readline()
                if not line:
                    return pos
                if int(float(line.split(b",", 1)[0])) >= t:
                    return pos

        a = lower_bound(int(t_lo))
        b = lower_bound(int(t_hi) + 1)
        fh.seek(a)
        blob = fh.read(max(0, b - a))
    cols = header.decode("utf-8", "replace").strip().split(",")
    if not blob.strip():
        return None
    df = pd.read_csv(io.BytesIO(blob), header=None, names=cols)
    t = df["time"].to_numpy(dtype=np.int64)
    if len(t) > 1 and np.any(np.diff(t) <= 0):
        df = df.sort_values("time").drop_duplicates("time", keep="last")
    return df


def _load_feed(instrument, timeframe, session, source, t_lo, t_hi):
    try:
        from augur_engine.data import find_master
        from augur_engine.paths import UPLOADS
        m = find_master(instrument, timeframe, session, source)
        if m is None:
            return None
        path = os.path.join(UPLOADS, m["filename"])
        st = os.stat(path)
        key = (path, st.st_mtime, st.st_size, int(t_lo), int(t_hi))
        hit = _FEED_MEMO.get(key)
        if hit is not None:
            return hit
        df = _csv_time_slice(path, t_lo, t_hi)
        if df is None or not len(df):
            return None
        out = {k: df[k].to_numpy(dtype=np.float64) for k in ("open", "high", "low", "close")}
        out["time"] = df["time"].to_numpy(dtype=np.int64)
        if len(_FEED_MEMO) >= 6:
            _FEED_MEMO.pop(next(iter(_FEED_MEMO)))
        _FEED_MEMO[key] = out
        return out
    except Exception as exc:
        k = (instrument, source)
        if k not in _FEED_WARNED:
            _FEED_WARNED.add(k)
            warnings.warn("MISC_SUPERSCALPER: %s %s feed unavailable (%s)" % (instrument, source, exc))
        return None


def _align(feed_t, feed_v, t):
    """request.security(sym, timeframe.period, x, lookahead_off): the feed bar opening at
    the chart bar's time, else the most recent earlier one (carried forward)."""
    out = np.full(len(t), np.nan)
    if feed_t is None or not len(feed_t):
        return out
    pos = np.searchsorted(feed_t, t, side="right") - 1
    ok = pos >= 0
    out[ok] = feed_v[pos[ok]]
    return out


def _feeds(epoch, mode_spy, want, inject_es=None, inject_qqq=None):
    """(esHigh, esLow, spyClose, qqqClose) aligned to the chart bars; na when not held."""
    n = len(epoch)
    nanv = np.full(n, np.nan)
    es = inject_es
    qqq = inject_qqq
    if want and n:
        t_lo = int(epoch[0]) - 10 * 86400
        t_hi = int(epoch[-1])
        if es is None:
            es = _load_feed("ES", "1m", "eth", "db_noadj_eth", t_lo, t_hi)
        if qqq is None:
            qqq = _load_feed("QQQ", "1m", "rth", "alpaca_split_rth", t_lo, t_hi)
    es_h = es_l = spy = nanv
    if es is not None:
        et = np.asarray(es["time"], np.int64)
        es_h = _align(et, _f(es["high"]), epoch)
        es_l = _align(et, _f(es["low"]), epoch)
        if mode_spy != "none":
            ec = _f(es["close"])
            try:                                   # SPY has no contract rolls: take the ES roll
                from augur_engine import rolls as _R   # steps out, forward (causal), anchored
                fa = _R.forward_adjust(et, _f(es["open"]), _f(es["high"]), _f(es["low"]),
                                       ec, "ES", 60)[3]   # at the slice's first bar
                if len(fa) == len(ec) and len(ec):
                    ec = fa - (fa[0] - ec[0])
            except Exception:
                pass
            if mode_spy == "es_rth":
                loc = _epoch_s(pd.DatetimeIndex(pd.to_datetime(et, unit="s", utc=True)).tz_convert(
                    "America/New_York").tz_localize(None))
                mod = (loc // 60) % 1440
                keep = (mod >= 570) & (mod < 960)
                spy = _align(et[keep], ec[keep], epoch)
            else:
                spy = _align(et, ec, epoch)
    qqq_c = nanv
    if qqq is not None:
        qqq_c = _align(np.asarray(qqq["time"], np.int64), _f(qqq["close"]), epoch)
    return es_h, es_l, spy, qqq_c


# ── OUR PORT ADDITION: daily VIX stand-in for CBOE:VIX 1m (vix_feed='daily') ──
# _vix_file -> (path, sha256, date column, date format, close column)
_VIX_FILES = {
    "raw": (r"C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv",
            "6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a",
            "DATE", "%m/%d/%Y", "CLOSE"),
    "derived": (r"C:\EdgeLog\_research_cache\public_series\cboe_vol_daily.csv",
                "9790df06b649df21d34ab7cb31a5ed5e4c3c71fcda33952d1f41e431cb4e2470",
                "date", "%Y-%m-%d", "VIX_close"),
}
_VIX_MEMO = {}
_VIX_MISSING_WARNED = set()
_VIX_USABLE_MIN = 16 * 60 + 15          # day D's close is usable from 16:15 ET on D
_VIX_PREV_SESSIONS = 10


def _load_vix_daily(which, last_day):
    """(NY date as days since 1970-01-01, close) from the sha256-pinned CBOE file `which`
    ('raw' | 'derived'), holding no row dated after `last_day` (the last chart bar's CME
    trading date): those rows are dropped right after parsing, before anything else reads
    the table. Refuses (ValueError) when the file's bytes do not match its pinned digest.
    Memo key = (file choice, path, mtime, size, last_day)."""
    if which not in _VIX_FILES:
        raise ValueError("MISC_SUPERSCALPER: _vix_file must be one of %s, got %r"
                         % (sorted(_VIX_FILES), which))
    path, sha, dcol, dfmt, vcol = _VIX_FILES[which]
    if not os.path.exists(path):              # e.g. the CI box: no VIX = the script's own missing-data branch
        if which not in _VIX_MISSING_WARNED:
            _VIX_MISSING_WARNED.add(which)
            warnings.warn("MISC_SUPERSCALPER: VIX file %s is not on this machine - vix_feed='daily' runs with "
                          "NO VIX (same as 'none')" % path)
        return np.zeros(0, np.int64), np.zeros(0, np.float64)
    st = os.stat(path)
    key = (which, path, st.st_mtime_ns, st.st_size, int(last_day))
    hit = _VIX_MEMO.get(key)
    if hit is not None:
        return hit
    with open(path, "rb") as fh:
        blob = fh.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != sha:
        raise ValueError("MISC_SUPERSCALPER: refused %s - sha256 %s does not match the pinned "
                         "%s" % (path, digest, sha))
    df = pd.read_csv(io.BytesIO(blob), usecols=[dcol, vcol], dtype={dcol: str})
    d = pd.to_datetime(df[dcol], format=dfmt).to_numpy().astype("datetime64[D]").astype(np.int64)
    keep = d <= int(last_day)                  # lockbox-honest: nothing after the window
    out = _vix_table(d[keep], df[vcol].to_numpy()[keep])
    if len(_VIX_MEMO) >= 8:
        _VIX_MEMO.pop(next(iter(_VIX_MEMO)))
    _VIX_MEMO[key] = out
    return out


def _vix_table(dates, closes):
    """Sorted, de-duplicated (day number since 1970-01-01, close) arrays; `dates` may be
    day numbers or anything pandas reads as a calendar date."""
    d = np.asarray(dates)
    if d.dtype.kind not in "iu":
        d = pd.to_datetime(pd.Series(d)).to_numpy().astype("datetime64[D]").astype(np.int64)
    d = d.astype(np.int64)
    v = pd.to_numeric(pd.Series(np.asarray(closes)), errors="coerce").to_numpy(np.float64)
    order = np.argsort(d, kind="stable")
    d = d[order]; v = v[order]
    last = np.r_[d[1:] != d[:-1], True] if len(d) else np.zeros(0, bool)
    return d[last], v[last]


def _vix_daily(loc, vdate, vclose):
    """(vixClose, vixPrev) per chart bar from daily closes, no look-ahead.
    NQ session days = ET dates on which this tape has a bar stamped 13:00-15:59 ET (CME
    holiday sessions halt at 13:00 ET; NYSE early closes run to 13:15). VIX rows dated on
    any other day are dropped (the CBOE file carries CME-holiday rows from 2022). A bar
    stamped at or after 16:15 ET on session day D sees D's close: vixClose = the latest
    kept close dated on or before the latest such D; vixPrev = the same value as of the
    session 10 NQ sessions before D (sessions counted on the tape, not VIX rows). Both are
    na until the tape holds enough sessions (warm-up)."""
    loc = np.asarray(loc, np.int64)
    n = len(loc)
    day = loc // 86400
    mod = (loc // 60) % 1440
    sess = np.unique(day[(mod >= 13 * 60) & (mod < 16 * 60)])
    if not len(sess):
        return np.full(n, np.nan), np.full(n, np.nan)
    vdate = np.asarray(vdate, np.int64)
    vclose = _f(vclose)
    keep = np.isin(vdate, sess) & np.isfinite(vclose)
    vd = vdate[keep]; vc = vclose[keep]
    asof = np.full(len(sess), np.nan)
    if len(vd):
        j = np.searchsorted(vd, sess, side="right") - 1
        asof = np.where(j >= 0, vc[np.maximum(j, 0)], np.nan)
    usable = sess * 86400 + _VIX_USABLE_MIN * 60
    k = np.searchsorted(usable, loc, side="right") - 1
    vix_close = np.where(k >= 0, asof[np.maximum(k, 0)], np.nan)
    kp = k - _VIX_PREV_SESSIONS
    vix_prev = np.where(kp >= 0, asof[np.maximum(kp, 0)], np.nan)
    return vix_close, vix_prev


# ── OUR PORT ADDITIONS: exit levels, applied after every entry gate ──
# chain path codes whose ticket stop IS the session stop (sessionSlLong / sessionSlShort)
_SESSION_STOP_PATHS = (1, 2, 4)                # MAIN, BOS, RE


def _exit_levels(c, atr, tp, sl, is_long, P, cap_mask=None):
    """Stop cap (sl_cap_atr, only where cap_mask: the session-stop tickets), then stop
    scale (sl_scale, every ticket), and target scale (tp_scale, every ticket) on the signal
    bar's levels; c = the signal bar's close, atr = the session-selected ATR the script's
    stop code uses. Each step is skipped at its default, so the as-ported prices pass
    through bit-for-bit."""
    tp = _f(tp); sl = _f(sl)
    if P["sl_cap_atr"] != "off" and cap_mask is not None:
        k = float(P["sl_cap_atr"])
        bound = c - k * atr if is_long else c + k * atr
        capped = np.maximum(sl, bound) if is_long else np.minimum(sl, bound)
        sl = np.where(np.asarray(cap_mask, bool) & np.isfinite(bound) & np.isfinite(sl),
                      capped, sl)
    if P["sl_scale"] != 1.0:
        sl = c + (sl - c) * P["sl_scale"]
    if P["tp_scale"] != 1.0:
        tp = c + (tp - c) * P["tp_scale"]
    return tp, sl


# ═════════════════════════════════════════════════════════════════════════════
# Higher-timeframe and daily requests
# ═════════════════════════════════════════════════════════════════════════════

def _htf_values(bucket, bucket_end, epoch, tf, h, l, c):
    """HTF bars from chart bars grouped by `bucket` -> (ema9, ema21, close, mid20) mapped to
    the chart with lookahead_off: bar j shows from the chart bar whose close reaches j's end."""
    n = len(c)
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    ends = np.r_[starts[1:], n] - 1
    H = np.maximum.reduceat(h, starts)
    L = np.minimum.reduceat(l, starts)
    C = c[ends]
    E = bucket_end[starts]
    f9 = _ema(C, 9)
    s21 = _ema(C, 21)
    mid = (_highest(H, 20) + _lowest(L, 20)) / 2.0
    j = np.searchsorted(E, epoch + tf, side="right") - 1
    ok = j >= 0
    out = []
    for arr in (f9, s21, C, mid):
        v = np.full(n, np.nan)
        v[ok] = arr[j[ok]]
        out.append(v)
    return out


def _daily_prev(tdate, m_et, h, l, c, mode):
    """request.security(D, [high[1], low[1], close[1], high[2], low[2]], lookahead_on)."""
    n = len(c)
    starts = np.flatnonzero(np.r_[True, tdate[1:] != tdate[:-1]])
    ends = np.r_[starts[1:], n] - 1
    H = np.maximum.reduceat(h, starts)
    L = np.minimum.reduceat(l, starts)
    C = c[ends].astype(np.float64)
    if mode == "settle":
        pre = m_et < 960                         # bars opening before 16:00 ET
        grp = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, n]))
        idx = np.where(pre, np.arange(n), -1)
        last_pre = pd.Series(idx).groupby(grp).max().to_numpy()
        C = np.where(last_pre >= 0, c[np.maximum(last_pre, 0)], C)
    g = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, n]))

    def back(arr, k):
        out = np.full(n, np.nan)
        ok = g - k >= 0
        out[ok] = arr[g[ok] - k]
        return out
    return back(H, 1), back(L, 1), back(C, 1), back(H, 2), back(L, 2)


# ═════════════════════════════════════════════════════════════════════════════
# The script, bar-close logic (vectorized over all bars, stateful parts in kernels)
# ═════════════════════════════════════════════════════════════════════════════

def _build(o, h, l, c, v, epoch, loc, tf, P, feeds):
    with np.errstate(divide="ignore", invalid="ignore"):
        return _build_inner(o, h, l, c, v, epoch, loc, tf, P, feeds, len(c))


def _build_inner(o, h, l, c, v, epoch, loc, tf, P, feeds, n):
    bar = np.arange(n)
    # ── clock ──
    m_et = (loc // 60) % 1440
    m_ct = (m_et - 60) % 1440
    ct_day = (loc - 3600) // 86400
    new_day = np.zeros(n, bool)
    new_day[1:] = ct_day[1:] != ct_day[:-1]
    ct_day = None  # free
    tdate = (loc + 6 * 3600) // 86400                      # CME trading date (18:00 ET)
    I = lambda a, b: _in_sess(m_ct, a, b)                  # noqa: E731
    isOpen = I(830, 930); isMorning = I(930, 1100); isLunch = I(1100, 1300)
    isAfternoon = I(1300, 1500); isLast = I(1500, 1600)
    inAsia = I(1600, 100); inLondon = I(100, 400); inPreMkt = I(400, 830)
    inRTH = I(700, 1600); inETH = ~inRTH
    ph = np.full(n, 7, np.int64)
    ph[isOpen] = 0; ph[isMorning] = 1; ph[isLunch] = 2; ph[isAfternoon] = 3; ph[isLast] = 4
    ph[inPreMkt] = 5; ph[inLondon] = 6
    kzAM = I(900, 1000); kzPM = I(1300, 1400); kz02 = I(200, 300)
    inPreMarket = I(300, 830); inORBBuild = I(830, 845); inOvernight = I(1500, 830)
    orbLockBar = I(845, 846)

    hlc3 = (h + l + c) / 3.0
    c1 = _sh(c, 1); o1 = _sh(o, 1); v1 = _sh(v, 1); v2 = _sh(v, 2)
    h2 = _sh(h, 2); l2 = _sh(l, 2)

    # ── base indicators ──
    atrFast = _atr(h, l, c, 10); atrMed = _atr(h, l, c, 14); atrSlow = _atr(h, l, c, 20)
    adx = _adx(h, l, c, 14, 14)
    vwapVal = _group_cumsum(hlc3 * v, tdate) / _group_cumsum(v, tdate)
    ema9 = _ema(c, 9); ema21 = _ema(c, 21); ema100 = _ema(c, 100); ema200 = _ema(c, 200)
    e12 = _ema(c, 12); e26 = _ema(c, 26)
    macdLine = e12 - e26
    e12 = e26 = None  # free
    macdSig = _ema(macdLine, 9)
    macdHist = macdLine - macdSig
    macdBear = (macdLine < macdSig) & (macdHist < 0)
    macdBull = (macdLine > macdSig) & (macdHist > 0)
    macdHist = macdLine = macdSig = None  # free

    esHigh, esLow, spyClose, qqqClose = feeds[:4]
    if len(feeds) > 5:
        vixClose, vixPrev = feeds[4], feeds[5]
    else:
        vixClose = np.full(n, np.nan); vixPrev = np.full(n, np.nan)
    c10 = _sh(c, 10)
    rocNQ = np.where(_ne(c, 0) & _ne(c10, 0), (c - c10) / c10 * 100.0, 0.0)
    spy10 = _sh(spyClose, 10)
    rocSPY = np.where(_ne(spyClose, 0) & _ne(spy10, 0), (spyClose - spy10) / spy10 * 100.0, 0.0)
    spy10 = spyClose = None  # free
    rsSpread = rocNQ - rocSPY
    rocNQ = rocSPY = None  # free

    nanv = np.full(n, np.nan)
    qinc = float(P["qqq_increment"])
    qqqRatio = np.where(qqqClose > 0, c / qqqClose, np.nan)
    qqqUp1 = qqqUp2 = qqqDn1 = qqqDn2 = nanv
    if P["show_qqq_levels"]:
        okq = ~np.isnan(qqqRatio) & ~np.isnan(qqqClose)
        qU1 = qinc * np.ceil(qqqClose / qinc)
        qD1 = qinc * np.floor(qqqClose / qinc)
        qqqUp1 = np.where(okq, qU1 * qqqRatio, np.nan)
        qqqUp2 = np.where(okq, (qU1 + qinc) * qqqRatio, np.nan)
        qqqDn1 = np.where(okq, qD1 * qqqRatio, np.nan)
        qqqDn2 = np.where(okq, (qD1 - qinc) * qqqRatio, np.nan)
    okq = qD1 = qU1 = qinc = qqqClose = qqqRatio = None  # free

    prevDayH, prevDayL, prevDayC, prev2DayH, prev2DayL = _daily_prev(
        tdate, m_et, h, l, c, P["daily_close"])
    m_et = None  # free
    pivotPP = (prevDayH + prevDayL + prevDayC) / 3.0
    pivotR1 = 2 * pivotPP - prevDayL
    pivotS1 = 2 * pivotPP - prevDayH
    pivotR2 = pivotPP + (prevDayH - prevDayL)
    pivotS2 = pivotPP - (prevDayH - prevDayL)
    nn = lambda x: ~np.isnan(x)                            # noqa: E731
    dBullCont = nn(prevDayC) & nn(prev2DayH) & (prevDayC > prev2DayH)
    dBearCont = nn(prevDayC) & nn(prev2DayL) & (prevDayC < prev2DayL)
    dBullRev = nn(prevDayL) & nn(prev2DayL) & nn(prevDayC) & (prevDayL < prev2DayL) & (prevDayC > prev2DayL)
    prev2DayL = None  # free
    dBearRev = nn(prevDayH) & nn(prev2DayH) & nn(prevDayC) & (prevDayH > prev2DayH) & (prevDayC < prev2DayH)
    prev2DayH = None  # free
    dailyBias = _sel(dBullCont, 1.0, dBullRev, 1.0, dBearCont, -1.0, dBearRev, -1.0, 0.0)
    dBearCont = dBearRev = dBullCont = dBullRev = None  # free

    # VWAP bands: reset on Chicago calendar-day change
    gday = np.cumsum(new_day)
    cumVol2 = _group_cumsum(v, gday)
    cumVolPr = _group_cumsum(hlc3 * v, gday)
    cumVolPr2 = _group_cumsum(hlc3 * hlc3 * v, gday)
    vwapCalc = np.where(cumVol2 > 0, cumVolPr / cumVol2, c)
    cumVolPr = None  # free
    vwapVar = np.where(cumVol2 > 0, cumVolPr2 / cumVol2 - vwapCalc * vwapCalc, 0.0)
    cumVol2 = cumVolPr2 = None  # free
    vwapStd = np.sqrt(np.maximum(0.0, vwapVar))
    vwapVar = None  # free
    vwapUp1 = vwapCalc + vwapStd; vwapDn1 = vwapCalc - vwapStd
    vwapUp2 = vwapCalc + vwapStd * 2; vwapDn2 = vwapCalc - vwapStd * 2
    vwapStd = None  # free

    rsiRaw = _rsi(c, 7)
    bbBasis = _sma(c, 20)
    bbDev = 1.5 * _stdev(c, 20)
    bbUpper = bbBasis + bbDev; bbLower = bbBasis - bbDev
    bbBasis = bbDev = None  # free
    kcMid = _ema(c, 20)
    kcUpper = kcMid + atrSlow * 1.5; kcLower = kcMid - atrSlow * 1.5
    kcMid = None  # free
    sqzOn = (bbUpper < kcUpper) & (bbLower > kcLower)
    kcLower = kcUpper = None  # free
    sqzFired = _shb(sqzOn, 1) & ~sqzOn
    sqzHL = _highest(h, 20); sqzLL = _lowest(l, 20)
    sqzMidRef = ((sqzHL + sqzLL) / 2.0 + _sma(c, 20)) / 2.0
    sqzMom = _linreg(c - sqzMidRef, 20, 0)
    sqzMidRef = None  # free
    sm1 = _sh(sqzMom, 1); sm2 = _sh(sqzMom, 2); sm3 = _sh(sqzMom, 3)
    momRecentBull = (sqzMom > 0) & ((sm1 <= 0) | (sm2 <= 0) | (sm3 <= 0))
    momRecentBear = (sqzMom < 0) & ((sm1 >= 0) | (sm2 >= 0) | (sm3 >= 0))
    sm2 = sm3 = None  # free
    bbWidth = bbUpper - bbLower
    bbUpper = None  # free
    bbPos = np.where(bbWidth > 0, (c - bbLower) / bbWidth, 0.5)
    bbLower = bbWidth = None  # free

    # ── AER regime (uses ATR14 - `atr` before its session re-selection) ──
    aerDisp = np.abs(c - c10)
    aerPath = _rsum(np.abs(c - c1), 10)
    aerER = np.where(_ne(aerPath, 0), aerDisp / aerPath, 0.0)
    aerDisp = aerPath = None  # free
    aerMeanATR = _sma(atrMed, 50)
    aerATRatio = np.where(_ne(aerMeanATR, 0), atrMed / aerMeanATR, 1.0)
    aerDynThresh = np.minimum(0.25 * aerATRatio, 0.65)
    aerTrending = aerER > aerDynThresh
    aerUptrend = aerTrending & (c > c10)
    aerDowntrend = aerTrending & (c < c10)
    c10 = None  # free
    aerNonTrending = aerER <= aerDynThresh
    aerDynThresh = aerER = None  # free
    aerChoppy = aerNonTrending & (atrMed > aerMeanATR)
    aerConsolidation = aerNonTrending & (atrMed <= aerMeanATR)
    aerNonTrending = None  # free
    T = aerTrending; C_ = aerChoppy
    aerTrending = aerChoppy = None  # free

    hurst = _kern("hurst")(np.ascontiguousarray(c))

    avgVol = _sma(v, 20)
    relVol = np.where(avgVol > 0, v / avgVol, 1.0)
    liquidityOk = (relVol >= P["min_rel_vol"]) & (atrMed >= P["min_atr_pts"])

    csBody = np.abs(c - o)
    csUpperWk = h - np.maximum(c, o)
    csLowerWk = np.minimum(c, o) - l
    csRange = h - l
    csAvgBody = _sma(csBody, 14)
    csBullBar = c > o; csBearBar = c < o
    csBullEngulf = csBullBar & _shb(csBearBar, 1) & (csBody > csAvgBody) & (c > o1) & (o <= c1)
    csBearEngulf = csBearBar & _shb(csBullBar, 1) & (csBody > csAvgBody) & (c < o1) & (o >= c1)
    csBearBar = csBullBar = o1 = None  # free
    csHammer = (csLowerWk > csBody * 2.0) & (csUpperWk < csBody * 0.3) & (csBody < csAvgBody) & (csBody > 0)
    csShootSt = (csUpperWk > csBody * 2.0) & (csLowerWk < csBody * 0.3) & (csBody < csAvgBody) & (csBody > 0)
    csAvgBody = None  # free
    csDojiFactor = _sel(I(830, 930), 0.08, I(1700, 100), 0.03, I(1100, 1300), 0.04, 0.05)
    csDoji = (csRange > 0) & (csBody < csRange * csDojiFactor)
    csDojiFactor = None  # free

    # session-selected ATR
    atr = np.where((ph == 0) | (ph == 1) | (ph == 4), atrFast,
                   np.where((ph == 2) | (ph == 3), atrMed, atrSlow))
    atrFast = atrMed = atrSlow = None  # free

    # ── ADF ──
    adfDy = c - c1
    adfX = _nz(c1, 0.0)
    adfXY = adfDy * adfX; adfX2 = adfX * adfX; adfDy2 = adfDy * adfDy
    adf = {}
    for N in (30, 50, 80):
        sDy = _sma(adfDy, N) * N; sX = _sma(adfX, N) * N; sXY = _sma(adfXY, N) * N
        sX2 = _sma(adfX2, N) * N; sDy2 = _sma(adfDy2, N) * N
        d = N * sX2 - sX * sX
        g = np.where(_ne(d, 0), (N * sXY - sX * sDy) / d, 0.0)
        a = (sDy - g * sX) / N
        sse = np.maximum(0.0, sDy2 - 2 * a * sDy - 2 * g * sXY + a * a * N + 2 * a * g * sX + g * g * sX2)
        se = np.where(_ne(d, 0), np.sqrt(np.maximum(0.0, sse / (N - 2) * N / d)), 1.0)
        adf[N] = np.where(se > 0, g / se, 0.0)
    N = a = adfDy = adfDy2 = adfX = adfX2 = adfXY = g = None  # free
    sDy = sDy2 = sX = sX2 = sXY = se = sse = None  # free
    adfStat = np.where(np.isin(ph, (0, 1, 4)), adf[30], np.where(np.isin(ph, (2, 3)), adf[50], adf[80]))
    adf = None  # free
    adfN = _S(ph, 30, 30, 50, 50, 30, 80, 80, 80)
    adfMeanRevert = adfStat < (-2.86 - 2.74 / adfN)
    adfN = None  # free
    adfTrending = adfStat > -1.0
    adfStat = None  # free
    adfSessWt = np.where(adfMeanRevert, _S(ph, 1.0, 0.9, 1.2, 1.0, 0.9, 2.5, 2.0, 2.0),
                         _S(ph, 1.0, 0.9, 0.7, 0.8, 0.9, 0.5, 0.6, 0.4))
    adfShift = (_sel(adfMeanRevert, 0.03, adfTrending, -0.03, 0.0) * adfSessWt
                * _sel(T, 1.1, C_, 0.8, 1.0) * _sel(adx >= 35, 1.1, adx < 15, 0.7, 1.0))
    adfSessWt = None  # free
    hurstPersist = hurst > (0.55 - adfShift)
    hurstRevert = hurst < (0.45 + adfShift)
    adfShift = hurst = None  # free

    def f_dyn(b, sO, sL, sA, rT, rC, aH, aL, lo, hi, ahi=30):
        sess = _S(ph, sO, -sO * 0.3, sL, sL * 0.5, sO * 0.3, sA, sA * 0.8, sA)
        reg = _sel(T, rT, C_, rC, 0.0)
        adj = _sel(adx >= ahi, aH, adx < 20, aL, 0.0)
        return _clamp(b + sess + reg + adj, lo, hi)

    adxA = lambda hi_v, lo_v: _sel(adx >= 30, hi_v, adx < 20, lo_v, 0.0)   # noqa: E731
    regTC = lambda tv, cv: _sel(T, tv, C_, cv, 0.0)                         # noqa: E731
    hurA = lambda pv, rv: _sel(hurstPersist, pv, hurstRevert, rv, 0.0)      # noqa: E731
    volR = lambda hv, lv: _sel(aerATRatio >= 1.5, hv, aerATRatio < 0.8, lv, 0.0)  # noqa: E731
    volRatio = _nz(aerATRatio, 1.0)

    # profile (end-of-bar `var`s) - computed now, read with their previous-bar value
    hvbL = int(P["hvb_lookback"]); hvbB = int(P["hvb_bins"])
    hvbHi = _highest(h, hvbL); hvbLo = _lowest(l, hvbL)
    prof = _kern("profile")(np.ascontiguousarray(c), np.ascontiguousarray(o),
                            np.ascontiguousarray(v), np.ascontiguousarray(hvbHi),
                            np.ascontiguousarray(hvbLo), hvbL, hvbB)
    hvbB = hvbHi = hvbL = hvbLo = None  # free
    z1, z2, z3, pov, vah, val, pbp, prb, prs, ns = prof
    prof = None  # free
    hvbZone1 = _sh(z1, 1); hvbZone2 = _sh(z2, 1); hvbZone3 = _sh(z3, 1)
    z1 = z2 = z3 = None  # free
    povLevel = _sh(pov, 1); vahLevel = _sh(vah, 1); valLevel = _sh(val, 1)
    pov = vah = val = None  # free
    pocBuyPct = _sh(pbp, 1); pocBuyPct[:1] = 50.0
    pbp = None  # free
    pocRawBuy = _sh(prb, 1); pocRawBuy[:1] = 0.0
    prb = None  # free
    pocRawSell = _sh(prs, 1); pocRawSell[:1] = 0.0
    prs = None  # free
    nodeStrength = _sh(ns, 1); nodeStrength[:1] = 0.0
    ns = None  # free

    povDist = np.where(nn(povLevel), np.abs(c - povLevel) / atr, 99.0)
    nearPoV = povDist < _S(ph, 0.8, 0.9, 1.2, 1.0, 0.8, 1.5, 1.3, 1.5)
    povDist = None  # free

    # VRZ
    vrzMult = _clamp(1.8 + _S(ph, 0.5, -0.15, -0.3, -0.15, 0.2, 0.3, 0.24, 0.3)
                     + regTC(0.2, -0.2) + adxA(0.2, -0.15), 1.2, 2.8)
    isVrz = (v > avgVol * vrzMult) & (atr > 0)
    vrzMult = None  # free
    vrzH, vrzL, vrzMid = _kern("vrz")(np.ascontiguousarray(isVrz), np.ascontiguousarray(h),
                                      np.ascontiguousarray(l))
    isVrz = None  # free
    vrzBias = np.where(nn(vrzMid), _sel(c > vrzMid, 1.0, c < vrzMid, -1.0, 0.0), 0.0)
    vrzMid = None  # free

    # RSI thresholds
    rsiBullFloor = _clamp(55.0 + _S(ph, -3.0, 0.9, 2.0, 1.0, -0.9, 3.0, 2.4, 3.0)
                          + adxA(-3.0, 3.0) + _sel(aerUptrend, -2.0, C_, 3.0, 0.0), 48.0, 62.0)
    rsiBullCap = _clamp(78.0 + _S(ph, 4.0, -1.2, -2.0, -1.0, 1.2, -3.0, -2.4, -3.0)
                        + _sel(adx >= 35, 4.0, adx >= 25, 2.0, adx < 20, -3.0, 0.0)
                        + _sel(aerUptrend, 3.0, C_, -3.0, 0.0), 72.0, 86.0)
    rsiBearCap = _clamp(43.0 + _S(ph, 3.0, -0.9, -2.0, -1.0, 0.9, -3.0, -2.4, -3.0)
                        + adxA(3.0, -3.0) + _sel(aerDowntrend, 3.0, C_, -3.0, 0.0), 36.0, 50.0)
    rsiBearFloor = _clamp(22.0 + _S(ph, -4.0, 1.2, 2.0, 1.0, -1.2, 3.0, 2.4, 3.0)
                          + _sel(adx >= 35, -4.0, adx >= 25, -2.0, adx < 20, 3.0, 0.0)
                          + _sel(aerDowntrend, -3.0, C_, 3.0, 0.0), 14.0, 28.0)
    rsi1 = _sh(rsiRaw, 1)
    rsiBull = (rsiRaw >= rsiBullFloor) & (rsiRaw < rsiBullCap) & (rsiRaw > rsi1)
    rsiBullCap = rsiBullFloor = None  # free
    rsiBear = (rsiRaw <= rsiBearCap) & (rsiRaw > rsiBearFloor) & (rsiRaw < rsi1)
    rsi1 = rsiBearCap = rsiBearFloor = rsiRaw = None  # free

    rsThr = _clamp(0.1 + _S(ph, -0.03, 0.009, 0.03, 0.015, -0.009, 0.04, 0.032, 0.04)
                   + regTC(-0.02, 0.02) + adxA(-0.02, 0.02), 0.04, 0.20)
    rsWeak = rsSpread < -rsThr
    rsStrong = rsSpread > rsThr
    rsSpread = rsThr = None  # free

    trapFpRatio = f_dyn(1.3, 0.3, -0.15, -0.2, 0.15, -0.1, 0.15, -0.1, 1.0, 2.0)
    bosVolThresh = f_dyn(1.3, 0.3, -0.2, -0.3, 0.1, -0.1, 0.15, -0.15, 0.9, 2.0)
    mfiWtHi = f_dyn(1.5, 0.3, -0.25, -0.3, 0.15, -0.1, 0.15, -0.1, 1.0, 2.2)
    mfiWtLo = _clamp(1.0 + _S(ph, 0.2, -0.06, -0.15, -0.075, 0.06, -0.2, -0.16, -0.2)
                     + regTC(0.1, -0.1), 0.6, 1.5)
    exitVolClimax = f_dyn(2.0, 0.5, -0.3, -0.4, 0.2, -0.2, 0.2, -0.2, 1.3, 3.0)
    confVolBounce = _clamp(1.2 + _S(ph, 0.3, -0.09, -0.2, -0.1, 0.09, -0.2, -0.16, -0.2)
                           + regTC(0.1, -0.1), 0.8, 1.8)
    obVolThresh = _clamp(1.2 + _S(ph, 0.3, -0.09, -0.15, -0.075, 0.09, -0.2, -0.16, -0.2)
                         + regTC(0.1, -0.1), 0.8, 1.8)
    mfiExhBuyThresh = f_dyn(80.0, 3.0, -2.0, -3.0, 2.0, -2.0, 2.0, -2.0, 72.0, 90.0, ahi=35)
    mfiExhSelThresh = f_dyn(20.0, -3.0, 2.0, 3.0, -2.0, 2.0, -2.0, 2.0, 10.0, 28.0, ahi=35)
    bosBreakMult = f_dyn(0.5, 0.15, -0.1, -0.1, 0.1, -0.05, 0.1, -0.05, 0.25, 0.8)
    f_dyn = None  # free

    # ── stateful session levels / ORB ──
    st = _kern("state")(*[np.ascontiguousarray(x) for x in (
        o, h, l, c, inRTH, inAsia, inLondon, new_day, inPreMarket, inOvernight, inORBBuild,
        orbLockBar)])
    inORBBuild = inOvernight = new_day = orbLockBar = None  # free
    (rthHigh, rthLow, asiaHigh, asiaLow, londonHigh, londonLow, orbHigh, orbLow, orbMid,
     orbLocked, pmHigh, pmLow, pmMid, onHigh, onLow, onHighPrev, onLowPrev,
     orbBrokenUp, orbBrokenDown) = st
    st = None  # free

    asiaRW = np.where(nn(asiaHigh), asiaHigh, h) - np.where(nn(asiaLow), asiaLow, l)
    londonRW = np.where(nn(londonHigh), londonHigh, h) - np.where(nn(londonLow), londonLow, l)
    onRW = np.where(nn(onHighPrev), onHighPrev, h) - np.where(nn(onLowPrev), onLowPrev, l)
    onHighPrev = onLowPrev = None  # free
    sessionRW = np.where(inAsia, asiaRW, np.where(inLondon, np.maximum(asiaRW, londonRW), onRW))
    asiaRW = londonRW = onRW = None  # free
    ethSlCap = np.maximum(15.0, sessionRW * 1.5)
    sessionRW = None  # free

    kz = kzAM | kzPM
    volAdjF = _sel(relVol >= exitVolClimax, 0.10, relVol >= mfiWtHi, 0.05, relVol < mfiWtLo, -0.05, 0.0)
    adxF = _sel(adx >= 30, 0.10, adx >= 20, 0.0, -0.10)
    dynFloorSell = atr * _clamp(1.5 + _sel(kz, 0.10, isOpen, 0.20, isMorning, 0.05, isLunch, -0.20,
                                           isAfternoon, 0.0, isLast, 0.10, inAsia, -0.15,
                                           inLondon, 0.05, inPreMkt, -0.05, 0.0)
                                + _sel(aerDowntrend, 0.25, aerConsolidation, -0.10, C_, -0.20, 0.0)
                                + adxF + volAdjF, 0.8, 2.5)
    dynFloorLong = atr * _clamp(1.8 + _sel(kz, 0.15, isOpen, 0.25, isMorning, 0.05, isLunch, -0.25,
                                           isAfternoon, 0.0, isLast, 0.10, inAsia, -0.20,
                                           inLondon, 0.05, inPreMkt, -0.05, 0.0)
                                + _sel(aerUptrend, 0.25, aerConsolidation, -0.10, C_, -0.20, 0.0)
                                + adxF + volAdjF, 1.0, 3.0)
    adxF = volAdjF = None  # free
    slSess = _S(ph, 0.3, -0.09, 0.2, 0.1, 0.09, 0.2, 0.15, 0.25)
    slAdx = adxA(-0.10, 0.20)
    slVol = volR(0.20, -0.10)
    dynSlDistLong = atr * _clamp(2.0 + slSess + _sel(aerUptrend, -0.20, aerDowntrend, 0.50,
                                                     aerConsolidation, 0.30, C_, 0.80, 0.0)
                                 + slAdx + slVol, 1.2, 3.0)
    dynSlDistShort = atr * _clamp(2.0 + slSess + _sel(aerDowntrend, -0.20, aerUptrend, 0.50,
                                                      aerConsolidation, 0.30, C_, 0.80, 0.0)
                                  + slAdx + slVol, 1.2, 4.5)
    slAdx = slSess = slVol = None  # free
    bufSess = _S(ph, 0.5, -0.15, 0.3, 0.15, 0.15, 0.0, 0.0, 0.0)
    bufVol = volR(0.50, -0.30)
    dynBufLong = volRatio * _clamp(2.0 + bufSess + bufVol, 1.0, 5.0)
    dynBufShort = volRatio * _clamp(3.0 + bufSess + bufVol, 1.0, 6.0)
    bufSess = None  # free
    dynBufETH = volRatio * _clamp(3.0 + _sel(inAsia, -0.50, inLondon, 0.20, inPreMkt, 0.10, 0.0)
                                  + bufVol, 1.0, 6.0)
    bufVol = None  # free
    sessionTpLong = c + dynFloorLong * 2.0
    sessionTpShort = c - dynFloorSell * 2.0

    # ── HTF gate ──
    def bucket_minutes(P_):
        b = epoch // (P_ * 60)
        return b, (b + 1) * P_ * 60
    b5, e5 = bucket_minutes(5); b15, e15 = bucket_minutes(15); b60, e60 = bucket_minutes(60)
    bucket_minutes = None  # free
    mss = (m_ct - 1020) % 1440                             # minutes since 17:00 CT
    b240 = tdate * 6 + mss // 240
    tdate = None  # free
    sess_end = epoch - (mss * 60) - (epoch % 60) + 23 * 3600   # 16:00 CT = start + 23h
    e240 = np.minimum(epoch - (mss % 240) * 60 - (epoch % 60) + 240 * 60, sess_end)
    mss = sess_end = None  # free
    h5f, h5s, h5c, h5mid = _htf_values(b5, e5, epoch, tf, h, l, c)
    b5 = e5 = None  # free
    h15f, h15s, h15c, h15mid = _htf_values(b15, e15, epoch, tf, h, l, c)
    b15 = e15 = None  # free
    h60f, h60s, h60c, h60mid = _htf_values(b60, e60, epoch, tf, h, l, c)
    b60 = e60 = None  # free
    h4f, h4s, _h4c, _h4m = _htf_values(b240, e240, epoch, tf, h, l, c)
    _h4c = _h4m = b240 = e240 = None  # free
    h4sep = np.abs(h4f - h4s) / c * 100.0
    h4notBear = (h4f > h4s) | (h4sep < 0.5)
    h4notBull = (h4f < h4s) | (h4sep < 0.5)
    h4f = h4s = h4sep = None  # free
    htfBull = (h5f > h5s) & (h15f > h15s) & (h60f > h60s) & h4notBear
    h4notBear = None  # free
    htfBear = (h5f < h5s) & (h15f < h15s) & (h60f < h60s) & h4notBull
    h4notBull = None  # free

    adxMin = float(P["adx_min"])
    trendUp = htfBull & (ema9 > ema21) & (ema21 > ema100) & (c > vwapVal) & (adx > adxMin)
    trendDown = htfBear & (ema9 < ema21) & (ema21 < ema100) & (c < vwapVal) & (adx > adxMin)
    adxMin = None  # free

    hh5 = _highest(h, 5); ll5 = _lowest(l, 5)
    swH = _sh(hh5, 1); swL = _sh(ll5, 1); prevSwH = _sh(hh5, 2); prevSwL = _sh(ll5, 2)
    hh5 = ll5 = None  # free
    brkL = (c > swH) & (c1 > prevSwH)
    prevSwH = None  # free
    brkS = (c < swL) & (c1 < prevSwL)
    prevSwL = None  # free
    longBrkClean = c > swH + atr * 0.2
    swH = None  # free
    shortBrkConf = c < swL
    swL = None  # free

    # ── strategy A (ORB retest) / B (failed ORB rotation) ──
    retProx = _clamp(0.002 + _S(ph, 0.001, -0.0003, 0.0, 0.0, 0.0003, 0.0, 0.0, 0.0)
                     + regTC(0.0005, -0.0005), 0.001, 0.004)
    orbRetestLong = orbBrokenUp & (l <= orbHigh * (1 + retProx)) & (l >= orbHigh * (1 - retProx))
    orbRetestShort = orbBrokenDown & (h >= orbLow * (1 - retProx)) & (h <= orbLow * (1 + retProx))
    retProx = None  # free
    orbWickLong = orbRetestLong & ((np.minimum(o, c) - l) > np.abs(c - o) * 0.5)
    orbWickShort = orbRetestShort & ((h - np.maximum(o, c)) > np.abs(c - o) * 0.5)
    orbFlowLong = orbRetestLong & (c > o) & (v > v1)
    orbFlowShort = orbRetestShort & (c < o) & (v > v1)
    orbConfirmLong = orbRetestLong & (c > orbHigh) & (orbWickLong | orbFlowLong)
    orbFlowLong = orbRetestLong = orbWickLong = None  # free
    orbConfirmShort = orbRetestShort & (c < orbLow) & (orbWickShort | orbFlowShort)
    orbFlowShort = orbRetestShort = orbWickShort = None  # free
    stratA_Long = orbLocked & orbConfirmLong
    stratA_Short = orbLocked & orbConfirmShort
    orbFailed = orbLocked & nn(orbHigh) & ~orbBrokenUp & ~orbBrokenDown
    atORBHigh = np.abs(c - orbHigh) / orbHigh < 0.003
    atORBLow = np.abs(c - orbLow) / orbLow < 0.003
    rejAtHigh = orbFailed & atORBHigh & (h > orbHigh) & (c < orbHigh) & ((h - c) > (c - l) * 1.5)
    atORBHigh = None  # free
    rejAtLow = orbFailed & atORBLow & (l < orbLow) & (c > orbLow) & ((c - l) > (h - c) * 1.5)
    atORBLow = orbFailed = None  # free
    cleanCandle = (csRange > atr * 0.3) & (csBody > csRange * 0.3)
    stratB_Short = rejAtHigh & cleanCandle
    rejAtHigh = None  # free
    stratB_Long = rejAtLow & cleanCandle
    cleanCandle = rejAtLow = None  # free

    # ── opening drive (base) ──
    odRTHOpen = I(830, 836); odEconData = I(728, 733); odSecondWave = I(900, 906)
    I = None  # free
    odWindow = bool(P["use_od"]) & (odRTHOpen | odEconData | odSecondWave)
    odVolThresh = _clamp(_sel(odRTHOpen, 2.5, odEconData, 3.0, odSecondWave, 2.0, 2.5)
                         + regTC(-0.3, 0.4)
                         + _sel(adx >= 35, -0.3, adx >= 25, -0.15, adx < 15, 0.3, 0.0)
                         + hurA(-0.2, 0.2), 1.5, 4.0)
    odVolSpike = v > avgVol * odVolThresh
    odVolThresh = None  # free
    odBuildupThresh = _clamp(1.5 + regTC(-0.2, 0.3) + adxA(-0.15, 0.15), 1.0, 2.5)
    odPriorVol = (_nz(v1) + _nz(v2)) / 2.0
    v1 = v2 = None  # free
    odVolBuildup = odPriorVol > avgVol * odBuildupThresh
    odBuildupThresh = odPriorVol = None  # free
    odBodyRatioMin = _clamp(0.50 + regTC(-0.05, 0.08) + _sel(adx >= 35, -0.05, adx < 15, 0.05, 0.0)
                            + np.where(relVol >= 3.0, -0.05, 0.0), 0.35, 0.65)
    odBodyRatio = np.where(csRange > 0, csBody / csRange, 0.0)
    odStrongBull = (c > o) & (odBodyRatio > odBodyRatioMin) & ~csDoji
    odStrongBear = (c < o) & (odBodyRatio > odBodyRatioMin) & ~csDoji
    odBodyRatio = odBodyRatioMin = None  # free
    odPmBiasLong = np.where(nn(pmMid), c > pmMid, True)
    odPmBiasShort = np.where(nn(pmMid), c < pmMid, True)
    odHtfBiasLong = (h60f > h60s) | (h15f > h15s)
    odHtfBiasShort = (h60f < h60s) | (h15f < h15s)
    odPrevDayBiasLong = nn(prevDayC) & (c > prevDayC)
    odPrevDayBiasShort = nn(prevDayC) & (c < prevDayC)
    prevDayC = None  # free
    odAboveOvernightH = nn(onHigh) & (c > onHigh)
    odBelowOvernightL = nn(onLow) & (c < onLow)
    odOvernightWt = _sel(T & (adx >= 25), 2, isOpen, 2, C_, 1, 1)
    odBuildupWt = _sel(C_, 2, isOpen & (adx >= 25), 2, T, 1, 1)
    odEngulfWt = _sel(T & (adx >= 30), 1, C_, 2, isOpen, 1, 2)
    odSmtWt = _sel(inAsia, 0, isOpen & (adx >= 25), 2, isMorning & (adx >= 25), 2, isAfternoon, 1,
                   T & (adx >= 30), 2, isLunch, 1, 1)
    odConfLongBase = (odPmBiasLong.astype(float) + odHtfBiasLong + odPrevDayBiasLong
                      + np.where(odAboveOvernightH, odOvernightWt, 0.0)
                      + np.where(odVolBuildup, odBuildupWt, 0.0)
                      + np.where(csBullEngulf | csHammer, odEngulfWt, 0.0))
    odAboveOvernightH = odHtfBiasLong = odPmBiasLong = odPrevDayBiasLong = None  # free
    odConfShortBase = (odPmBiasShort.astype(float) + odHtfBiasShort + odPrevDayBiasShort
                       + np.where(odBelowOvernightL, odOvernightWt, 0.0)
                       + np.where(odVolBuildup, odBuildupWt, 0.0)
                       + np.where(csBearEngulf | csShootSt, odEngulfWt, 0.0))
    odBelowOvernightL = odBuildupWt = odEngulfWt = odHtfBiasShort = odOvernightWt = odPmBiasShort = odPrevDayBiasShort = odVolBuildup = None  # free
    odMinConf = _clamp(_sel(odRTHOpen, 4, odEconData, 5, odSecondWave, 4, 4)
                       + _sel(C_, 1, T & (adx >= 30), -1, 0)
                       + _sel(hurstRevert, 1, hurstPersist, -1, 0), 3, 7)
    odSecondWave = None  # free
    odBuyGateEarly = odWindow & odVolSpike & odStrongBull & (odConfLongBase >= odMinConf)
    odSellGateEarly = odWindow & odVolSpike & odStrongBear & (odConfShortBase >= odMinConf)
    odBuf = atr * _clamp(_sel(odRTHOpen, 0.4, odEconData, 0.6, 0.4) + regTC(-0.05, 0.1)
                         + _sel(adx >= 35, -0.05, adx < 15, 0.05, 0.0)
                         + np.where(relVol >= 4.0, 0.1, 0.0), 0.2, 0.8)
    odEconData = odRTHOpen = None  # free
    odSlLong = l - odBuf
    odSlShort = h + odBuf
    odBuf = None  # free
    odTpFloor = _clamp(1.5 + regTC(0.5, -0.3) + _sel(adx >= 35, 0.3, adx < 15, -0.2, 0.0), 0.8, 3.0)
    tpRR = _sel(T & (adx >= 25), 2.5, C_, 1.5, 2.0)
    tgt = c + (c - odSlLong) * tpRR
    for lvl, extra in ((prevDayH, True), (onHigh, True), (pivotR1, True), (orbHigh, orbLocked)):
        tgt = np.where(nn(lvl) & (lvl > c) & (lvl < tgt) & extra, lvl, tgt)
    prevDayH = None  # free
    odTpLong = np.maximum(tgt, c + atr * odTpFloor)
    tgt = c - (odSlShort - c) * tpRR
    tpRR = None  # free
    for lvl, extra in ((prevDayL, True), (onLow, True), (pivotS1, True), (orbLow, orbLocked)):
        tgt = np.where(nn(lvl) & (lvl < c) & (lvl > tgt) & extra, lvl, tgt)
    extra = prevDayL = None  # free
    odTpShort = np.minimum(tgt, c - atr * odTpFloor)
    odTpFloor = tgt = None  # free

    # ── FVG ──
    fvgMinSize = atr * float(P["fvg_min_pct"])
    bullFVG = bool(P["use_fvg"]) & (l > h2) & ((l - h2) >= fvgMinSize)
    bearFVG = bool(P["use_fvg"]) & (h < l2) & ((l2 - h) >= fvgMinSize)
    fvgMinSize = None  # free
    fvgMaxAge = _sel(isOpen, 80, isMorning, 100, isLunch, 280, isAfternoon, 200, inAsia, 150,
                     T, 120, 200)
    fvgMaxFill = _sel(T, 0.80, C_, 0.65, 0.75)
    fvgMaxTouch = _sel(T, 5, C_, 3, 4)
    fv = _kern("fvg")(*[np.ascontiguousarray(x) for x in (
        h, l, c, bullFVG, bearFVG, fvgMaxAge, fvgMaxFill, fvgMaxTouch)])
    bearFVG = bullFVG = fvgMaxAge = fvgMaxFill = fvgMaxTouch = None  # free
    fvgBullHi, fvgBullLo, fvgBullFill, fvgBullAge, fvgBullTouch = fv[:5]
    fvgBearHi, fvgBearLo, fvgBearFill, fvgBearAge, fvgBearTouch = fv[5:]
    fv = None  # free
    fvgAgeDecay = _sel(isOpen, 0.004, isMorning, 0.0035, isLunch, 0.001, isAfternoon, 0.002,
                       inAsia, 0.003, T, 0.003, 0.002)
    fvgTouchPen = _sel(T, 0.12, C_, 0.20, 0.15)
    fvgBullQuality = np.where(nn(fvgBullHi), np.maximum(
        0.0, 1.0 - fvgBullFill - fvgBullTouch * fvgTouchPen - fvgBullAge * fvgAgeDecay), 0.0)
    fvgBullAge = fvgBullFill = fvgBullTouch = None  # free
    fvgBearQuality = np.where(nn(fvgBearHi), np.maximum(
        0.0, 1.0 - fvgBearFill - fvgBearTouch * fvgTouchPen - fvgBearAge * fvgAgeDecay), 0.0)
    fvgAgeDecay = fvgBearAge = fvgBearFill = fvgBearTouch = fvgTouchPen = None  # free
    fvgQualityGate = _sel(isOpen, 0.20, isMorning, 0.25, isLunch, 0.40, isAfternoon, 0.30,
                          inAsia, 0.35, T & (adx >= 25), 0.25, C_, 0.40, 0.30)

    # ── OTE ──
    swingHigh = sqzHL; swingLow = sqzLL; swingRange = swingHigh - swingLow
    sqzHL = sqzLL = None  # free
    inOTELong = bool(P["use_ote"]) & (c >= swingHigh - swingRange * 0.79) & (c <= swingHigh - swingRange * 0.62)
    inOTEShort = bool(P["use_ote"]) & (c <= swingLow + swingRange * 0.79) & (c >= swingLow + swingRange * 0.62)
    oteMidLong = ((swingHigh - swingRange * 0.62) + (swingHigh - swingRange * 0.79)) / 2.0
    swingHigh = None  # free
    oteMidShort = ((swingLow + swingRange * 0.79) + (swingLow + swingRange * 0.62)) / 2.0
    swingLow = None  # free

    # ── order blocks ──
    obLookback = int(P["ob_lookback"])
    obEnabled = bool(P["use_ob"]) & (bar > obLookback)
    strongMoveUp = (c > c1 + atr * float(P["ob_min_move"])) & (c > o) & (v > avgVol * obVolThresh)
    strongMoveDown = (c < c1 - atr * float(P["ob_min_move"])) & (c < o) & (v > avgVol * obVolThresh)
    c1 = obVolThresh = None  # free
    obInKZ = kz02 | kzAM | kzPM
    kz02 = kzAM = kzPM = None  # free
    starsBull = (htfBull.astype(np.int64) + (c < vwapVal) + (l > h2) + (relVol >= mfiWtHi) + obInKZ)
    starsBear = (htfBear.astype(np.int64) + (c > vwapVal) + (h < l2) + (relVol >= mfiWtHi) + obInKZ)
    obMinDyn = (int(P["ob_min_rules"]) + _sel(inAsia, 1, inLondon, 1, inPreMkt, 1, isLast, 1, 0)).astype(np.int64)
    obr = _kern("ob")(*[np.ascontiguousarray(x) for x in (
        o, h, l, c, obEnabled, strongMoveUp, strongMoveDown, starsBull.astype(np.int64),
        starsBear.astype(np.int64), obMinDyn, dynSlDistLong, dynSlDistShort)],
        obLookback, bool(P["use_ob_trade"]))
    obEnabled = obLookback = obMinDyn = starsBear = starsBull = strongMoveDown = strongMoveUp = None  # free
    obBullMid, obBearMid, obBullTradeFire, obBullSl, obBearTradeFire, obBearSl = obr
    obr = None  # free

    # ── TP engine ──
    tpRegimeMult = _sel(aerUptrend | aerDowntrend, 1.2, aerConsolidation, 0.8, 0.6)
    tpRegimeMultSell = _sel(aerDowntrend, 1.2, aerConsolidation, 0.7, 0.6)
    adxTpScale = _sel(adx > 30, 1.2, adx > 20, 1.0, 0.85)
    tpVolScale = np.maximum(0.8, np.minimum(volRatio, 1.5))
    volRatio = None  # free
    tpSessionMult = _sel(kz, 1.05, isOpen, 1.10, isLunch, 0.85, isLast, 1.03, inAsia, 0.90, 1.0)
    tpMultBuy = tpRegimeMult * adxTpScale * tpVolScale * tpSessionMult
    tpRegimeMult = None  # free
    tpMultSell = tpRegimeMultSell * adxTpScale * tpVolScale * tpSessionMult
    adxTpScale = tpRegimeMultSell = tpSessionMult = tpVolScale = None  # free
    tpFloorBuy = dynFloorLong
    tpFloorSell = dynFloorSell
    fpPocMid = nanv                                         # footprint POC: na (PORT GAP 1)
    nanv = None  # free
    showORBMid = bool(P["show_orb_mid"]); showON = bool(P["show_on_range"])
    showQ = bool(P["show_qqq_levels"])
    T_ = np.ones(n, bool)
    res_levels = [(pivotR1, T_), (pivotR2, T_), (pivotPP, T_), (orbHigh, orbLocked),
                  (pmHigh, T_), (pmMid, T_), (vwapUp1, T_), (vwapUp2, T_), (fpPocMid, T_),
                  (orbMid, orbLocked & showORBMid), (onHigh, T_ & showON),
                  (qqqUp1, T_ & showQ), (qqqUp2, T_ & showQ), (hvbZone1, T_), (hvbZone2, T_),
                  (povLevel, T_), (vahLevel, T_), (fvgBullLo, fvgBullQuality > fvgQualityGate),
                  (fvgBearHi, fvgBearQuality > fvgQualityGate), (obBullMid, T_), (obBearMid, T_),
                  (oteMidShort, trendDown & (swingRange > atr * 2))]
    fvgBullLo = oteMidShort = qqqUp2 = vwapUp2 = None  # free
    sup_levels = [(pivotS1, T_), (pivotS2, T_), (pivotPP, T_), (orbLow, orbLocked),
                  (pmLow, T_), (pmMid, T_), (vwapDn1, T_), (vwapDn2, T_), (fpPocMid, T_),
                  (orbMid, orbLocked & showORBMid), (onLow, T_ & showON),
                  (qqqDn1, T_ & showQ), (qqqDn2, T_ & showQ), (hvbZone1, T_), (hvbZone2, T_),
                  (povLevel, T_), (valLevel, T_), (fvgBullHi, fvgBullQuality > fvgQualityGate),
                  (fvgBearLo, fvgBearQuality > fvgQualityGate), (obBullMid, T_), (obBearMid, T_),
                  (oteMidLong, trendUp & (swingRange > atr * 2))]
    fpPocMid = fvgBearLo = fvgBearQuality = fvgBullQuality = fvgQualityGate = oteMidLong = qqqDn2 = vwapDn2 = None  # free
    nearestResAbove = c + atr * float(P["tp1_mult"])
    for lvl, m in res_levels:
        nearestResAbove = np.where(m & (lvl > c) & (lvl < nearestResAbove), lvl, nearestResAbove)
    res_levels = None  # free
    nearestSupBelow = c - atr * float(P["tp1_mult"])
    for lvl, m in sup_levels:
        nearestSupBelow = np.where(m & (lvl < c) & (lvl > nearestSupBelow), lvl, nearestSupBelow)
    sup_levels = None  # free

    # footprint (PORT GAP 1)
    if P["footprint"] == "clv":
        rng = h - l
        fpBuyVol = np.where(rng > 0, v * (c - l) / rng, v * 0.5)
        fpSellVol = v - fpBuyVol
    else:
        fpBuyVol = np.zeros(n)
        fpSellVol = np.zeros(n)
    rng = None  # free
    fpDelta = fpBuyVol - fpSellVol
    cumFpDelta = _group_cumsum(fpDelta, gday)
    gday = None  # free
    fpDeltaSlope = cumFpDelta - _sh(cumFpDelta, 10)
    cumFpDelta = None  # free
    fpDeltaBull = fpDeltaSlope > 0
    fpDeltaBear = fpDeltaSlope < 0
    deltaMag = np.where(avgVol > 0, np.minimum(2.0, np.abs(fpDeltaSlope) / (avgVol * 0.1)), 1.0)
    fpDeltaSlope = None  # free
    fpBuyRatio = np.where(fpSellVol > 0, fpBuyVol / fpSellVol, 99.0)
    fpSellRatio = np.where(fpBuyVol > 0, fpSellVol / fpBuyVol, 99.0)
    flowA = lambda bv, rv: _sel(fpDeltaBull, bv, fpDeltaBear, rv, 0.0)      # noqa: E731

    starVol = _sel(relVol >= exitVolClimax, 0.08, relVol >= mfiWtHi, 0.04, relVol < mfiWtLo, -0.08, 0.0)
    starAdx = _sel(adx >= 30, 0.08, adx >= 20, 0.0, -0.08)
    starSess = _sel(kz, 0.05, isOpen, 0.05, isLunch, -0.30, isLast, 0.03, inPreMkt, -0.20,
                    inLondon, -0.20, inAsia, -0.25, isAfternoon, -0.10, 0.0)
    inPreMkt = kz = None  # free
    flowS = _sel((fpDelta < 0) & (fpSellRatio >= trapFpRatio), 0.05 * deltaMag, fpDeltaBear,
                 0.03 * deltaMag, -0.05)
    flowL = _sel((fpDelta > 0) & (fpBuyRatio >= trapFpRatio), 0.05 * deltaMag, fpDeltaBull,
                 0.03 * deltaMag, -0.05)
    trendS = _sel(aerDowntrend, 0.10, aerConsolidation, -0.05, C_, -0.15, 0.0)
    trendL = _sel(aerUptrend, 0.10, aerConsolidation, -0.05, C_, -0.15, 0.0)

    def star_base(stars):
        return _sel(stars >= 5, 1.0, stars >= 4, 0.85, stars >= 3, 0.7, stars >= 2, 0.55, 0.4)

    def starAdjTpShort(rawTp, stars):
        dm = _clamp(star_base(stars) + trendS + starVol + starAdx + flowS + starSess, 0.3, 1.25)
        return np.minimum(c - (c - rawTp) * dm, c - tpFloorSell)

    def starAdjTpLong(rawTp, stars):
        dm = _clamp(star_base(stars) + trendL + starVol + starAdx + flowL + starSess, 0.3, 1.25)
        return np.maximum(c + (rawTp - c) * dm, c + tpFloorBuy)

    tpBuffer = float(P["tp_buffer"])
    mainTpLong = np.maximum(nearestResAbove, c + dynFloorLong * 1.8)
    mainTpShort = np.maximum(nearestSupBelow, c - dynFloorSell * 1.5)
    mainTpLongAdj = np.maximum(c + (mainTpLong - c) * tpMultBuy - tpBuffer, c + tpFloorBuy)
    mainTpLong = None  # free
    mainTpShortAdj = np.minimum(c - (c - mainTpShort) * tpMultSell + tpBuffer, c - tpFloorSell)
    mainTpShort = None  # free
    bosTpLong = np.maximum(nearestResAbove, c + dynFloorLong * 1.2)
    bosTpShort = np.maximum(nearestSupBelow, c - dynFloorSell * 1.2)
    bosTpLongAdj = np.maximum(c + (bosTpLong - c) * tpMultBuy * 0.7, c + tpFloorBuy)
    bosTpLong = None  # free
    bosTpShortAdj = np.minimum(c - (c - bosTpShort) * tpMultSell * 0.7, c - tpFloorSell)
    bosTpShort = None  # free
    obTpLong = np.maximum(nearestResAbove, c + dynFloorLong * 1.5)
    dynFloorLong = nearestResAbove = None  # free
    obTpShort = np.maximum(nearestSupBelow, c - dynFloorSell * 1.0)
    dynFloorSell = None  # free
    obTpLongAdj = np.maximum(c + (obTpLong - c) * tpMultBuy - tpBuffer, c + tpFloorBuy)
    obTpLong = tpMultBuy = None  # free
    obTpShortAdj = np.minimum(c - (c - obTpShort) * tpMultSell + tpBuffer, c - tpFloorSell)
    obTpShort = tpBuffer = tpMultSell = None  # free

    # ── BOS ──
    bosLen = int(P["bos_len"])
    bosHighVal = _sh(_highest(h, bosLen), 1)
    bosLowVal = _sh(_lowest(l, bosLen), 1)
    bosLen = None  # free
    bosBreakSize = atr * bosBreakMult
    bosBreakMult = None  # free
    useBOS = bool(P["use_bos"])
    bosBullRaw = useBOS & (c > bosHighVal) & ((c - bosHighVal) > bosBreakSize) & (relVol >= bosVolThresh) & (c > o)
    bosHighVal = None  # free
    bosBearRaw = useBOS & (c < bosLowVal) & ((bosLowVal - c) > bosBreakSize) & (relVol >= bosVolThresh) & (c < o)
    bosBreakSize = bosLowVal = bosVolThresh = useBOS = None  # free
    bullBOS, bearBOS = _kern("bos")(np.ascontiguousarray(bosBullRaw), np.ascontiguousarray(bosBearRaw))
    bosBearRaw = bosBullRaw = None  # free
    bosCreatedFVG = (l > h2) | (h < l2)
    h2 = l2 = None  # free
    bosInKZ = obInKZ
    obInKZ = None  # free
    bosBuyConfBase = np.where(bullBOS, (
        (h5f > h5s).astype(np.int64) + (c > vwapVal) + (adx > 25) + aerUptrend + bosInKZ
        + bosCreatedFVG + (c > ema21) + (relVol >= 1.5) + fpDeltaBull + (fpBuyRatio >= 1.5)
        + csBullEngulf + ~csDoji), 0)
    bosSellConfBase = np.where(bearBOS, (
        (h5f < h5s).astype(np.int64) + (c < vwapVal) + (adx > 25) + aerDowntrend + bosInKZ
        + bosCreatedFVG + (c < ema21) + (relVol >= 1.5) + fpDeltaBear + (fpSellRatio >= 1.5)
        + csBearEngulf + ~csDoji), 0)
    bosCreatedFVG = bosInKZ = csDoji = None  # free

    # ── liquidity trap (sweep) ──
    sweepLen = int(P["sweep_len"])
    swpHighVal = _sh(_highest(h, sweepLen), 1)
    swpLowVal = _sh(_lowest(l, sweepLen), 1)
    sweepLen = None  # free
    swpAvgRange = _sma(csRange, 20)
    swpWickMin = atr * _clamp(0.6 + _S(ph, 0.15, -0.045, 0.1, -0.05, 0.05, 0.15, 0.12, 0.15)
                              + regTC(0.1, -0.1), 0.3, 1.0)
    swpWickBodyThresh = _clamp(1.2 + regTC(0.2, -0.2)
                               + _S(ph, 0.1, -0.03, -0.1, -0.05, 0.03, 0.0, 0.0, 0.0), 0.8, 1.8)
    swpVolThresh = _clamp(1.7 + _S(ph, 0.3, -0.09, -0.3, -0.15, 0.1, -0.4, -0.32, -0.4)
                          + adxA(0.2, -0.2), 1.0, 2.8)
    swpRangeThresh = _clamp(1.3 + _S(ph, 0.15, -0.045, -0.1, -0.05, 0.045, 0.15, 0.12, 0.15)
                            + regTC(0.1, -0.1), 0.9, 1.8)
    swpMeanUpper = _sma(csUpperWk, 20); swpMeanLower = _sma(csLowerWk, 20)
    swpStdUpper = _stdev(csUpperWk, 20); swpStdLower = _stdev(csLowerWk, 20)
    swpStdevFactor = _sel(isOpen, 1.2, isMorning, 1.3, isLunch, 1.8, isAfternoon, 1.5, inAsia, 1.8,
                          T & (adx >= 30), 1.1, T, 1.3, C_, 1.7, adx < 15, 1.7, 1.5)
    swpStdevOkHigh = csUpperWk > swpMeanUpper + swpStdevFactor * swpStdUpper
    csUpperWk = swpMeanUpper = swpStdUpper = None  # free
    swpStdevOkLow = csLowerWk > swpMeanLower + swpStdevFactor * swpStdLower
    csLowerWk = swpMeanLower = swpStdLower = swpStdevFactor = None  # free
    swpFakeHigh = (h > swpHighVal) & (c < swpHighVal)
    swpHighVal = None  # free
    swpFakeLow = (l < swpLowVal) & (c > swpLowVal)
    swpLowVal = None  # free
    upW = h - np.maximum(o, c); loW = np.minimum(o, c) - l
    swpWickOk = (upW > swpWickMin) | (loW > swpWickMin)
    swpWickMin = None  # free
    swpWickBody = np.where(csBody > 0, np.maximum(upW, loW) / csBody >= swpWickBodyThresh, True)
    swpWickBodyThresh = None  # free
    swpVolOk = relVol >= swpVolThresh
    swpVolThresh = None  # free
    swpRangeOk = csRange > swpAvgRange * swpRangeThresh
    swpAvgRange = swpRangeThresh = None  # free
    useSweep = bool(P["use_sweep"])
    bullSweep = useSweep & swpFakeHigh & swpWickOk & swpWickBody & swpVolOk & swpRangeOk & swpStdevOkHigh
    swpFakeHigh = swpStdevOkHigh = None  # free
    bearSweep = useSweep & swpFakeLow & swpWickOk & swpWickBody & swpVolOk & swpRangeOk & swpStdevOkLow
    swpFakeLow = swpRangeOk = swpStdevOkLow = swpVolOk = swpWickBody = swpWickOk = useSweep = None  # free

    longsEnabled = bool(P["longs_enabled"])
    baseL = trendUp & rsiBull & brkL & longBrkClean
    brkL = longBrkClean = rsiBull = trendUp = None  # free
    baseS = trendDown & rsiBear & brkS & shortBrkConf
    brkS = rsiBear = shortBrkConf = trendDown = None  # free
    vizSigL = liquidityOk & longsEnabled & baseL
    baseL = None  # free
    vizSigS = liquidityOk & baseS
    baseS = liquidityOk = None  # free
    stratC_Long = inOTELong & (swingRange > atr * 2)
    inOTELong = None  # free
    stratC_Short = inOTEShort & (swingRange > atr * 2)
    inOTEShort = swingRange = None  # free

    # ── swing structure (pivots 3/3) ──
    pk = _kern("pivot")
    pivLow = pk(np.ascontiguousarray(l), 3, 3, False)
    pivHigh = pk(np.ascontiguousarray(h), 3, 3, True)
    sl0, sl1 = _last_two(pivLow)
    pivLow = None  # free
    sh0, sh1 = _last_two(pivHigh)
    pivHigh = None  # free
    hlBullish = nn(sl0) & nn(sl1) & (sl0 > sl1)
    llBearish = nn(sl0) & nn(sl1) & (sl0 < sl1)
    sl1 = None  # free
    hhBullish = nn(sh0) & nn(sh1) & (sh0 > sh1)
    lhBearish = nn(sh0) & nn(sh1) & (sh0 < sh1)
    sh1 = None  # free
    fullBullStruct = hhBullish & hlBullish
    fullBearStruct = llBearish & lhBearish
    chochBull = fullBearStruct & nn(sh0) & (c > sh0)
    sh0 = None  # free
    chochBear = fullBullStruct & nn(sl0) & (c < sl0)
    sl0 = None  # free

    # ── SMT (NQ vs ES pivots 5/5) ──
    esPivH = pk(np.ascontiguousarray(_f(esHigh)), 5, 5, True)
    esHigh = None  # free
    esPivL = pk(np.ascontiguousarray(_f(esLow)), 5, 5, False)
    esLow = pk = None  # free
    esSwHi1, esSwHi2 = _last_two(esPivH)
    esPivH = None  # free
    esSwLo1, esSwLo2 = _last_two(esPivL)
    esPivL = None  # free
    smtBearRaw = hhBullish & nn(esSwHi1) & nn(esSwHi2) & (esSwHi1 <= esSwHi2)
    esSwHi1 = esSwHi2 = None  # free
    smtBullRaw = llBearish & nn(esSwLo1) & nn(esSwLo2) & (esSwLo1 >= esSwLo2)
    esSwLo1 = esSwLo2 = None  # free
    smtLatch = _clamp(_sel(isOpen, 10, isMorning, 12, isLunch, 20, isAfternoon, 16, inAsia, 25,
                           T, 12, 15) + _sel(adx >= 35, -3, adx < 15, 5, 0), 5, 35)
    smtBearBar = np.maximum.accumulate(np.where(smtBearRaw, bar, 0))
    smtBearRaw = None  # free
    smtBullBar = np.maximum.accumulate(np.where(smtBullRaw, bar, 0))
    smtBullRaw = None  # free
    smtBear = ((bar - smtBearBar) <= smtLatch) & (smtBearBar > 0)
    smtBearBar = None  # free
    smtBull = ((bar - smtBullBar) <= smtLatch) & (smtBullBar > 0)
    smtBullBar = smtLatch = None  # free
    bosBuyConf = bosBuyConfBase + (bullBOS & fullBullStruct)
    bosBuyConfBase = None  # free
    bosSellConf = bosSellConfBase + (bearBOS & fullBearStruct)
    bosSellConfBase = None  # free

    # ── range position ──
    lo30 = _lowest(l, 30); lo90 = _lowest(l, 90); lo180 = _lowest(l, 180)
    hi30 = _highest(h, 30); hi90 = _highest(h, 90); hi180 = _highest(h, 180)
    wide = isLunch | C_ | inAsia | inPreMarket
    rangeLoNow = _sel(isOpen & (adx >= 30), lo30, isMorning, lo90, T & (adx >= 25), lo90,
                      isAfternoon, lo90, isLast, lo90, wide, lo180, lo90)
    lo180 = lo30 = lo90 = None  # free
    rangeHiNow = _sel(isOpen & (adx >= 30), hi30, isMorning, hi90, T & (adx >= 25), hi90,
                      isAfternoon, hi90, isLast, hi90, wide, hi180, hi90)
    hi180 = hi30 = hi90 = isLast = wide = None  # free
    rangeLo = _sh(rangeLoNow, 1); rangeHi = _sh(rangeHiNow, 1)
    rangeLoNow = rangeHiNow = None  # free
    rangeSz = rangeHi - rangeLo
    rangeHi = None  # free
    rangePos = np.where(rangeSz > 0, (c - rangeLo) / rangeSz, 0.5)
    rangeLo = rangeSz = None  # free
    pmAsia = inPreMarket | inAsia
    rLowBlockShort = _clamp(0.20 + adxA(-0.03, 0.04)
                            + _sel(aerDowntrend, -0.08, aerUptrend, 0.08, C_, 0.05, 0.0)
                            + volR(0.05, -0.03) + np.where(pmAsia, 0.08, 0.0), 0.08, 0.40)
    rHighBlockShort = _clamp(0.65 + adxA(0.05, -0.05)
                             + _sel(aerUptrend, -0.10, aerDowntrend, 0.15, C_, 0.0, 0.0)
                             + flowA(-0.05 * deltaMag, 0.05 * deltaMag), 0.55, 0.85)
    rHighBlockLong = _clamp(0.80 + adxA(0.03, -0.04)
                            + _sel(aerUptrend, 0.08, aerDowntrend, -0.08, C_, -0.05, 0.0)
                            + volR(-0.05, 0.03) + np.where(pmAsia, -0.08, 0.0), 0.60, 0.92)
    pmAsia = None  # free
    rLowBlockLong = _clamp(0.35 + adxA(-0.05, 0.05)
                           + _sel(aerDowntrend, 0.10, aerUptrend, -0.15, C_, 0.0, 0.0)
                           + _sel(fpDeltaBear, 0.05 * deltaMag, fpDeltaBull, -0.05 * deltaMag, 0.0),
                           0.15, 0.45)
    rangeBlocksShort_low = (rangePos >= 0.0) & (rangePos < rLowBlockShort)
    rLowBlockShort = None  # free
    rangeBlocksShort_high = (rangePos <= 1.0) & (rangePos > rHighBlockShort)
    rHighBlockShort = None  # free
    rangeBlocksLong_high = (rangePos <= 1.0) & (rangePos > rHighBlockLong)
    rHighBlockLong = None  # free
    rangeBlocksLong_low = (rangePos >= 0.0) & (rangePos < rLowBlockLong)
    rLowBlockLong = rangePos = None  # free

    # ── capitulation ──
    ud = aerUptrend | aerDowntrend
    capVol = _sel(C_, 3.0, ud, 2.2, 2.5)
    capBody = _sel(C_, 1.8, ud, 1.3, 1.5)
    cdn = []; cup = []
    for k in range(5):
        ck = _sh(c, k); okk = _sh(o, k); rk = _sh(relVol, k)
        big = (rk >= capVol) & (np.abs(ck - okk) >= atr * capBody)
        cdn.append((ck < okk) & big)
        cup.append((ck > okk) & big)
    big = capBody = capVol = ck = okk = rk = None  # free
    capDepth = _sel((adx >= 30) & ud, 2, isOpen, 3, isMorning, 3, isAfternoon, 4,
                    C_ | inAsia | inPreMarket | isLunch, 5, T, 3, 4)
    inPreMarket = ud = None  # free

    def cap_any(lst):
        return np.where(capDepth >= 5, lst[0] | lst[1] | lst[2] | lst[3] | lst[4],
                        np.where(capDepth >= 4, lst[0] | lst[1] | lst[2] | lst[3],
                                 np.where(capDepth >= 3, lst[0] | lst[1] | lst[2], lst[0] | lst[1])))
    capitulationDown = cap_any(cdn)
    cdn = None  # free
    capitulationUp = cap_any(cup)
    cap_any = cup = None  # free

    bigLowerWick = (loW >= atr * 0.8) & (loW > upW)
    bigUpperWick = (upW >= atr * 0.8) & (upW > loW)
    loW = upW = None  # free
    wickBlocksShort = bigLowerWick
    bigLowerWick = None  # free
    wickBlocksLong = bigUpperWick
    bigUpperWick = None  # free

    # ── HTF confluence ──
    def tf_vote(cc, fE, sE, mid):
        return (_sel(cc > sE, 0.5, cc < sE, -0.5, 0.0) + _sel(fE > sE, 1.0, fE < sE, -1.0, 0.0)
                + _sel(cc > mid, 0.5, cc < mid, -0.5, 0.0))
    h5Vote = tf_vote(h5c, h5f, h5s, h5mid)
    h5c = h5mid = None  # free
    h15Vote = tf_vote(h15c, h15f, h15s, h15mid)
    h15c = h15f = h15mid = None  # free
    h60Vote = tf_vote(h60c, h60f, h60s, h60mid)
    h60c = h60f = h60mid = tf_vote = None  # free
    htfConfScore = h5Vote * 1.0 + h15Vote * 1.5 + h60Vote * 2.0
    htfDivWt = (_S(ph, 1.0, 0.9, 0.7, 0.8, 0.9, 0.5, 0.6, 0.4) * _sel(T, 1.1, C_, 0.7, 0.9)
                * _sel(adx >= 35, 1.2, adx >= 25, 1.0, adx < 15, 0.6, 0.8)
                * _sel(hurstRevert, 1.2, hurstPersist, 0.8, 1.0)
                * _sel(relVol >= 2.0, 1.2, relVol < 0.7, 0.7, 1.0))
    pen = np.zeros(n)
    pen = np.where((h5Vote <= -1.0) & (h15Vote >= 1.0) & (h60Vote >= 1.0), -2.0 * htfDivWt, pen)
    pen = np.where((h5Vote >= 1.0) & (h15Vote <= -1.0) & (h60Vote <= -1.0), 2.0 * htfDivWt, pen)
    h15Vote = h5Vote = h60Vote = htfDivWt = None  # free
    htfConfScore = htfConfScore + pen
    pen = None  # free
    X7 = _sel(isOpen, 7.0, T, 6.5, 6.0)
    X4 = _sel(isOpen, 4.0, T, 3.5, 3.0)
    X5o = np.where(isOpen, 5.0, 4.0)
    X3o = np.where(isOpen, 3.0, 2.0)

    # ── OD deferred ──
    odChochWt = _sel(isOpen, 2, isMorning, 2, isAfternoon, 1, T & (adx >= 30), 2, inAsia, 0, 1)
    odStructWt = _sel(T & (adx >= 25), 2, isOpen, 1, C_, 1, 1)
    odDeltaWt = _sel(isOpen & (adx >= 25), 2, T, 1, 1)
    odConfLong = (odConfLongBase + np.where(smtBull, odSmtWt, 0.0) + np.where(chochBull, odChochWt, 0.0)
                  + np.where(fullBullStruct, odStructWt, 0.0) + np.where(fpDeltaBull, odDeltaWt, 0.0))
    odConfLongBase = None  # free
    odConfShort = (odConfShortBase + np.where(smtBear, odSmtWt, 0.0) + np.where(chochBear, odChochWt, 0.0)
                   + np.where(fullBearStruct, odStructWt, 0.0) + np.where(fpDeltaBear, odDeltaWt, 0.0))
    odChochWt = odConfShortBase = odDeltaWt = odSmtWt = odStructWt = None  # free
    odHtfVetoThresh = _sel(isOpen, 5.0, isMorning, 4.5, isLunch, 3.5, isAfternoon, 4.0, inAsia, 3.0,
                           T & (adx >= 30), 4.5, C_, 3.0, 4.0)
    odHtfVetoBuy = htfConfScore <= -odHtfVetoThresh
    odHtfVetoSell = htfConfScore >= odHtfVetoThresh
    odHtfVetoThresh = None  # free
    pmRng = pmHigh - pmLow
    odPmRangePos = np.where(nn(pmHigh) & nn(pmLow) & (pmRng > 0), (c - pmLow) / pmRng, 0.5)
    pmRng = None  # free
    odPmBlockSellBelow = _sel(T, 0.25, C_, 0.35, adx >= 30, 0.22, adx < 15, 0.35, isOpen, 0.28, 0.30)
    odPmBlockBuyAbove = _sel(T, 0.75, C_, 0.65, adx >= 30, 0.78, adx < 15, 0.65, isOpen, 0.72, 0.70)
    odPmVetoBuy = odPmRangePos > odPmBlockBuyAbove
    odPmBlockBuyAbove = None  # free
    odPmVetoSell = odPmRangePos < odPmBlockSellBelow
    odPmBlockSellBelow = odPmRangePos = None  # free
    odContraHigh = _sel(isOpen, 3.5, T & (adx >= 30), 2.5, C_, 2.0, 3.0)
    odContraMid = _sel(isOpen, 2.0, T, 1.0, 1.5)
    odContraAdj = _sel(htfConfScore >= odContraHigh, 2, htfConfScore >= odContraMid, 1, 0)
    odContraAdjBuy = _sel(htfConfScore <= -odContraHigh, 2, htfConfScore <= -odContraMid, 1, 0)
    odContraHigh = odContraMid = None  # free
    odBuyRaw = ((odBuyGateEarly | (odWindow & odVolSpike & odStrongBull
                                   & (odConfLong >= odMinConf + odContraAdjBuy)))
                & ~odHtfVetoBuy & ~odPmVetoBuy)
    odBuyGateEarly = odConfLong = odContraAdjBuy = odHtfVetoBuy = odPmVetoBuy = odStrongBull = None  # free
    odSellRaw = ((odSellGateEarly | (odWindow & odVolSpike & odStrongBear
                                     & (odConfShort >= odMinConf + odContraAdj)))
                 & ~odHtfVetoSell & ~odPmVetoSell)
    odConfShort = odContraAdj = odHtfVetoSell = odMinConf = odPmVetoSell = odSellGateEarly = odStrongBear = odVolSpike = None  # free
    odWindow = None  # free

    htfVetoShort = _clamp(3.0 + _S(ph, -0.5, 0.15, 1.0, 0.5, -0.15, 0.5, 0.4, 0.5)
                          + _sel(aerUptrend, -1.0, aerDowntrend, 1.0, C_, 0.5, 0.0)
                          + adxA(-0.5, 0.5) + volR(-0.3, 0.3) + flowA(-0.5, 0.5)
                          + hurA(-0.3, 0.3), 1.0, 6.0)
    htfVetoLong = _clamp(-3.0 + _S(ph, 0.5, -0.15, 0.5, -0.5, 0.15, 0.5, 0.4, 0.5)
                         + _sel(aerDowntrend, 1.0, aerUptrend, -1.0, C_, -0.5, 0.0)
                         + adxA(0.5, -0.5) + volR(0.3, -0.3)
                         + _sel(fpDeltaBear, 0.5, fpDeltaBull, -0.5, 0.0)
                         + hurA(0.3, -0.3), -6.0, -1.0)
    htfBlocksShort = htfConfScore >= htfVetoShort
    htfVetoShort = None  # free
    htfBlocksLong = htfConfScore <= htfVetoLong
    htfVetoLong = None  # free

    shortAux = (hlBullish.astype(np.int64) + hhBullish + rangeBlocksShort_high + capitulationDown
                + wickBlocksShort)
    capitulationDown = rangeBlocksShort_high = None  # free
    longAux = (llBearish.astype(np.int64) + lhBearish + rangeBlocksLong_low + capitulationUp
               + wickBlocksLong)
    capitulationUp = rangeBlocksLong_low = None  # free
    auxSess = _S(ph, -0.3, -0.15, 0.3, 0.1, -0.1, 0.3, 0.2, 0.3)
    auxAdx = adxA(-0.2, 0.2)
    auxHur = hurA(-0.15, 0.2)
    auxVol = _sel(relVol >= 2.0, -0.2, relVol < 0.7, 0.2, 0.0)
    shortAuxThr = _clamp(2.0 + _sel(htfConfScore >= X5o, -1.0, htfConfScore >= X3o, -0.5,
                                    htfConfScore <= -X5o, 1.5, htfConfScore <= -X3o, 0.8, 0.0)
                         + _sel(aerUptrend, -0.3, aerDowntrend, 0.5, C_, 0.2, 0.0)
                         + auxSess + auxAdx + auxHur + auxVol
                         + _sel(c > ema100 + atr * 1.0, -0.3, c < ema100 - atr * 1.0, 0.5, 0.0)
                         + flowA(-0.2, 0.3), 1.0, 4.0)
    longAuxThr = _clamp(2.0 + _sel(htfConfScore <= -X5o, -1.0, htfConfScore <= -X3o, -0.5,
                                   htfConfScore >= X5o, 1.5, htfConfScore >= X3o, 0.8, 0.0)
                        + _sel(aerDowntrend, -0.3, aerUptrend, 0.5, C_, 0.2, 0.0)
                        + auxSess + auxAdx + auxHur + auxVol
                        + _sel(c < ema100 - atr * 1.0, -0.3, c > ema100 + atr * 1.0, 0.5, 0.0)
                        + _sel(fpDeltaBear, -0.2, fpDeltaBull, 0.2, 0.0), 1.0, 4.0)
    auxAdx = auxHur = auxSess = auxVol = None  # free
    structBlocksShort = rangeBlocksShort_low | htfBlocksShort | (shortAux >= shortAuxThr)
    htfBlocksShort = rangeBlocksShort_low = shortAux = shortAuxThr = None  # free
    structBlocksLong = rangeBlocksLong_high | htfBlocksLong | (longAux >= longAuxThr)
    htfBlocksLong = longAux = longAuxThr = rangeBlocksLong_high = None  # free

    # ── retest ──
    bearRetest = aerDowntrend & (h > ema21) & (c < ema21) & ~hlBullish
    bullRetest = aerUptrend & (l < ema21) & (c > ema21) & ~llBearish
    cleanBody = (csRange > 0) & (csBody / csRange > 0.3)
    csRange = None  # free
    bullRetestScore = ((adx > 25).astype(np.int64) + (relVol >= confVolBounce) + (c > vwapVal)
                       + htfBull + cleanBody + fpDeltaBull)
    htfBull = None  # free
    bearRetestScore = ((adx > 25).astype(np.int64) + (relVol >= confVolBounce) + (c < vwapVal)
                       + htfBear + cleanBody + fpDeltaBear)
    cleanBody = htfBear = None  # free
    rmr = float(P["retest_min_rules"])
    retestMinBear = np.minimum(6.0, rmr + hhBullish + (htfConfScore >= 3.0) + (c > ema100))
    retestMinBull = np.minimum(6.0, rmr + lhBearish + (htfConfScore <= -3.0) + (c < ema100)
                               + _S(ph, 1.5, 1.0, 0.0, 0.0, 0.5, 1.0, 0.0, 0.5))
    rmr = None  # free
    bullRetestOk = bullRetest & (bullRetestScore >= retestMinBull)
    bullRetest = bullRetestScore = retestMinBull = None  # free
    bearRetestOk = bearRetest & (bearRetestScore >= retestMinBear)
    bearRetest = bearRetestScore = retestMinBear = None  # free

    # ── structural gates (shorts) ──
    shortHtfSlopeOk = (h15s < _sh(h15s, 5)) & (h60s < _sh(h60s, 3))
    shortVwapSlopeOk = vwapVal <= _sh(vwapVal, 5)
    shortRolledOver = c < _highest(h, 10) - atr * 1.0
    structGateCount = shortHtfSlopeOk.astype(np.int64) + shortVwapSlopeOk + shortRolledOver
    shortHtfSlopeOk = shortRolledOver = shortVwapSlopeOk = None  # free

    mfiVal = _mfi(hlc3, v, 14)
    hlc3 = None  # free
    mfiBull = (mfiVal > 50) & (mfiVal < 80)
    mfiBear = (mfiVal < 50) & (mfiVal > 20)
    mfiExhBuy = mfiVal >= mfiExhBuyThresh
    mfiExhBuyThresh = None  # free
    mfiExhSel = mfiVal <= mfiExhSelThresh
    mfiExhSelThresh = None  # free
    # TICK / VIX: not held -> na (PORT GAP 2): tickBull/Bear false, tickMag 0, vix flags false.
    lrSlope = _linreg(c, 40, 0) - _linreg(c, 40, 1)
    emaSlope = (ema9 - _sh(ema9, 5)) / 5.0
    vwapBias = _sel(c > vwapCalc, 1.0, c < vwapCalc, -1.0, 0.0)
    vwapCalc = None  # free
    htfSlope = h5f - h5s
    h5f = None  # free
    sgn = lambda x: _sel(x > 0, 1.0, x < 0, -1.0, 0.0)      # noqa: E731
    x = None  # free

    # ── dirScoreFull (pre-entry part; the post-hoc divergence/absorption terms come after
    #    the entry block in the script and never reach an order) ──
    mfiMag = np.minimum(1.5, np.abs(mfiVal - 50.0) / 30.0)
    mfiVal = None  # free
    rawFlowDelta = fpBuyVol - fpSellVol
    fpBuyVol = fpSellVol = None  # free
    rawFlowMag = np.where(avgVol > 0, np.minimum(1.5, np.abs(rawFlowDelta) / (avgVol * 0.3)), 0.0)
    avgVol = None  # free
    d = np.zeros(n)
    d = d + sgn(lrSlope)
    lrSlope = None  # free
    d = d + sgn(emaSlope)
    emaSlope = None  # free
    d = d + vwapBias
    vwapBias = None  # free
    d = d + sgn(htfSlope)
    htfSlope = None  # free
    d = d + 0.0                                            # 5. TICK (na)
    if P["vix_feed"] == "none":
        d = d + 0.0                                        # 6. VIX (na)
    else:                                                  # 6. VIX, daily stand-in (ours)
        vixRiseT = np.maximum(1.005, np.minimum(1.05, 1.01 + _S(
            ph, 0.02, -0.006, -0.005, -0.0025, 0.006, -0.005, -0.004, -0.005)
            + _sel(T, 0.005, C_, -0.005, 0.0)))
        vixFallT = np.maximum(0.95, np.minimum(0.995, 0.99 + _S(
            ph, -0.02, 0.006, 0.005, 0.0025, -0.006, 0.005, 0.004, 0.005)
            + _sel(T, -0.005, C_, 0.005, 0.0)))
        vixOk = nn(vixClose) & nn(vixPrev)
        vixRising = vixOk & (vixClose > vixPrev * vixRiseT)
        vixFalling = vixOk & (vixClose < vixPrev * vixFallT)
        vixMag = np.where(nn(vixClose), np.minimum(1.5, np.maximum(0.5, vixClose / 20.0)), 1.0)
        d = d + _sel(vixFalling, 1.0 * vixMag, vixRising, -1.0 * vixMag, 0.0)
    vixClose = vixFallT = vixFalling = vixMag = vixOk = vixPrev = vixRiseT = vixRising = None  # free
    d = d + _sel(fpDeltaBull, 1.5 * deltaMag, fpDeltaBear, -1.5 * deltaMag, 0.0)
    d = d + _sel(mfiBull, 0.5 * mfiMag, mfiBear, -0.5 * mfiMag, 0.0)
    mfiBear = mfiBull = None  # free
    d = d + np.where(mfiExhBuy, -1.0, 0.0)
    d = d + np.where(mfiExhSel, 1.0, 0.0)
    d = d + _sel((rawFlowDelta > 0) & (c > o), 0.5 * rawFlowMag, (rawFlowDelta < 0) & (c < o),
                 -0.5 * rawFlowMag, 0.0)
    rawFlowDelta = rawFlowMag = None  # free
    d = d + _sel(aerUptrend, 1.5, aerDowntrend, -1.5, 0.0)
    d = d + dailyBias
    dailyBias = None  # free
    d = d + np.where(hurstPersist, _sel(aerUptrend, 1.0, aerDowntrend, -1.0, 0.0), 0.0)
    d = d + np.where(hurstRevert, _sel(aerUptrend, -0.5, aerDowntrend, 0.5, 0.0), 0.0)
    d = d + _sel(rsStrong, 0.5, rsWeak, -0.5, 0.0)
    rsStrong = rsWeak = None  # free
    d = d + _sel(macdBull, 0.5, macdBear, -0.5, 0.0)
    macdBear = macdBull = None  # free
    d = d + vrzBias * _sel(isOpen, 0.7, isMorning, 0.6, isLunch, 0.3, isAfternoon, 0.4, inAsia, 0.3,
                           T, 0.6, adx >= 30, 0.6, 0.5)
    vrzBias = None  # free
    d = d + _sel(c > ema200, 0.5, c < ema200, -0.5, 0.0)
    structWt = _sel(isOpen, 2.0, isMorning, 1.8, isLunch, 0.8, isAfternoon, 1.2, inAsia, 0.5,
                    T & (adx >= 25), 1.8, 1.5)
    structPartialWt = _sel(isOpen, 0.7, isMorning, 0.6, inAsia, 0.2, isLunch, 0.3, isAfternoon, 0.4,
                           T & (adx >= 25), 0.6, 0.5)
    d = d + _sel(fullBullStruct, structWt, fullBearStruct, -structWt,
                 hlBullish & hhBullish, structPartialWt, llBearish & lhBearish, -structPartialWt, 0.0)
    fullBearStruct = fullBullStruct = structPartialWt = structWt = None  # free
    smtWt = _sel(isOpen, 1.5, isMorning, 1.3, inAsia, 0.4, isLunch, 0.7, isAfternoon, 0.9,
                 T & (adx >= 25), 1.3, 1.0)
    d = d + _sel(smtBull, smtWt, smtBear, -smtWt, 0.0)
    smtBear = smtBull = smtWt = None  # free
    chochWt = _sel(isOpen, 2.0, isMorning, 1.8, isLunch, 0.8, isAfternoon, 1.2, inAsia, 0.6,
                   T & (adx >= 30), 2.0, T, 1.8, adx >= 25, 1.5, 1.2)
    d = d + _sel(chochBull, chochWt, chochBear, -chochWt, 0.0)
    chochBear = chochBull = chochWt = None  # free
    csWt = _sel(isOpen, 0.7, isMorning, 0.6, isLunch, 0.3, isAfternoon, 0.4, inAsia, 0.2,
                T & (adx >= 30), 0.7, T, 0.6, C_, 0.4, 0.5)
    d = d + _sel(csBullEngulf | csHammer, csWt, csBearEngulf | csShootSt, -csWt, 0.0)
    csBearEngulf = csBullEngulf = csHammer = csShootSt = csWt = None  # free
    pocWt = (_sel(isOpen, 0.6, isMorning, 0.5, isLunch, 0.3, isAfternoon, 0.4, inAsia, 0.2, T, 0.5, 0.4)
             * _sel(nodeStrength >= 15, 1.3, nodeStrength >= 10, 1.0, 0.7))
    d = d + _sel(pocBuyPct > 60, pocWt, pocBuyPct < 40, -pocWt, 0.0)
    pocBuyPct = pocWt = None  # free
    pocDelta = pocRawBuy - pocRawSell
    pocRawBuy = pocRawSell = None  # free
    pocDeltaNorm = np.where(nodeStrength >= 10, sgn(pocDelta), 0.0)
    pocDelta = sgn = None  # free
    pocRawWt = _sel(isOpen, 0.8, isMorning, 0.7, isLunch, 0.3, isAfternoon, 0.5, inAsia, 0.2, T, 0.6, 0.4)
    d = d + pocDeltaNorm * pocRawWt
    pocDeltaNorm = pocRawWt = None  # free
    povWt = _sel(isOpen, 0.4, isMorning, 0.35, isLunch, 0.2, isAfternoon, 0.25, inAsia, 0.15, T, 0.35, 0.25)
    d = d + _sel(nearPoV & (c > o), povWt, nearPoV & (c < o), -povWt, 0.0)
    nearPoV = povWt = None  # free
    bosWt = _sel(isOpen, 2.5, isMorning, 2.0, isLunch, 0.8, isAfternoon, 1.5, inAsia, 0.5,
                 T & (adx >= 30), 2.0, C_, 0.6, 1.5)
    d = d + _sel(bullBOS, bosWt, bearBOS, -bosWt, 0.0)
    bosWt = None  # free
    sqzWt = _sel(isOpen, 1.5, isMorning, 1.3, isLunch, 0.5, isAfternoon, 0.8, inAsia, 0.3, T, 1.2, 0.7)
    d = d + _sel(sqzFired & (sqzMom > 0), sqzWt, sqzFired & (sqzMom < 0), -sqzWt, 0.0)
    sqzWt = None  # free
    retestWt = _sel(isOpen, 1.5, isMorning, 1.2, isLunch, 0.5, isAfternoon, 0.8, inAsia, 0.3,
                    T & (adx >= 25), 1.2, C_, 0.4, hurstPersist, 1.0, 0.7)
    d = d + _sel(bullRetestOk, retestWt, bearRetestOk, -retestWt, 0.0)
    retestWt = None  # free
    momFlipWt = _sel(isOpen, 0.8, isMorning, 0.7, isLunch, 0.3, isAfternoon, 0.5, inAsia, 0.2,
                     T, 0.6, C_, 0.2, 0.4)
    d = d + _sel(momRecentBull, momFlipWt, momRecentBear, -momFlipWt, 0.0)
    momFlipWt = None  # free
    regFlipWt = _sel(isOpen, 1.5, isMorning, 1.2, isLunch, 0.5, isAfternoon, 0.8, inAsia, 0.3,
                     adx >= 30, 1.3, adx < 20, 0.4, hurstPersist, 1.0, 0.7)
    d = d + _sel(aerUptrend & ~_shb(aerUptrend, 1), regFlipWt, aerDowntrend & ~_shb(aerDowntrend, 1),
                 -regFlipWt, 0.0)
    regFlipWt = None  # free
    useORB = bool(P["use_orb"])
    orbWt = np.where(orbLocked, _sel(isMorning, 1.5, isOpen, 1.2, isAfternoon, 0.5, inAsia, 0.2,
                                     adx >= 30, 1.3, C_, 0.3, hurstPersist, 1.0, 0.5), 0.0)
    if useORB:
        d = d + _sel(orbBrokenUp, orbWt, orbBrokenDown, -orbWt, 0.0)
    else:
        d = d + 0.0
    orbBrokenDown = orbBrokenUp = orbWt = None  # free
    orbConfWt = np.where(orbLocked, _sel(isMorning, 2.0, isOpen, 1.5, isAfternoon, 0.5, adx >= 30, 1.5,
                                         C_, 0.3, hurstPersist, 1.2, 0.5), 0.0)
    if useORB:
        d = d + _sel(orbConfirmLong, orbConfWt, orbConfirmShort, -orbConfWt, 0.0)
    else:
        d = d + 0.0
    orbConfWt = orbConfirmLong = orbConfirmShort = useORB = None  # free
    dirScoreFull = d
    d = None  # free

    dsVetoShort = _clamp(2.0 + _S(ph, -0.3, 0.09, 0.5, 0.25, -0.09, 0.3, 0.24, 0.3)
                         + _sel(aerUptrend, -0.5, aerDowntrend, 0.8, C_, 0.3, 0.0)
                         + adxA(-0.3, 0.3) + volR(-0.2, 0.2) + flowA(-0.3, 0.3)
                         + hurA(-0.2, 0.2), 1.0, 4.0)
    dsVetoLong = _clamp(-2.0 + _S(ph, 0.3, -0.09, 0.3, -0.25, 0.09, 0.3, 0.25, 0.3)
                        + _sel(aerDowntrend, 0.5, aerUptrend, -0.8, C_, -0.3, 0.0)
                        + adxA(0.3, -0.3) + volR(0.2, -0.2)
                        + _sel(fpDeltaBear, 0.3, fpDeltaBull, -0.3, 0.0)
                        + hurA(0.2, -0.2), -4.0, -1.0)
    dirBlocksShortFull = dirScoreFull >= dsVetoShort
    dsVetoShort = None  # free
    dirBlocksLongFull = dirScoreFull <= dsVetoLong
    dsVetoLong = None  # free

    early = np.zeros(n)
    early = early + _sel(h5s > _sh(h5s, 5), 1.0, h5s < _sh(h5s, 5), -1.0, 0.0)
    h5s = None  # free
    early = early + _sel(h15s > _sh(h15s, 5), 1.0, h15s < _sh(h15s, 5), -1.0, 0.0)
    h15s = None  # free
    early = early + _sel(h60s > _sh(h60s, 3), 1.0, h60s < _sh(h60s, 3), -1.0, 0.0)
    h60s = None  # free
    early = early + _sel(ema9 > ema21, 1.0, ema9 < ema21, -1.0, 0.0)
    ema9 = None  # free
    early = early + _sel(c > vwapVal, 1.0, c < vwapVal, -1.0, 0.0)
    early = early + _sel(aerUptrend, 1.5, aerDowntrend, -1.5, 0.0)
    vSess = _S(ph, -0.5, 0.15, 0.5, 0.25, -0.15, 0.3, 0.24, 0.3)
    dirVetoThreshSell = _clamp(4.0 + vSess + _sel(aerUptrend, -0.5, aerDowntrend, 0.5,
                                                  aerConsolidation, 0.3, C_, 0.5, 0.0)
                               + adxA(-0.3, 0.3) + volR(-0.3, 0.3) + flowA(-0.3, 0.3)
                               + hurA(-0.2, 0.2), 2.5, 6.0)
    dirTightenThreshSell = _clamp(2.0 + _S(ph, -0.3, 0.09, 0.3, 0.15, -0.09, 0.2, 0.16, 0.2)
                                  + _sel(aerUptrend, -0.3, C_, 0.3, 0.0) + adxA(-0.2, 0.2)
                                  + volR(-0.15, 0.15) + flowA(-0.2, 0.2) + hurA(-0.15, 0.15),
                                  1.0, 3.5)
    flowA = None  # free
    dirVetoThreshBuy = _clamp(4.0 + vSess + _sel(aerDowntrend, -0.5, aerUptrend, 0.5,
                                                 aerConsolidation, 0.3, C_, 0.5, 0.0)
                              + adxA(-0.3, 0.3) + volR(-0.3, 0.3)
                              + _sel(fpDeltaBear, -0.3, fpDeltaBull, 0.3, 0.0)
                              + hurA(-0.2, 0.2), 2.5, 6.0)
    vSess = None  # free
    dirBlocksShortHard = early >= dirVetoThreshSell
    dirVetoThreshSell = None  # free
    dirTightensShort = (early >= dirTightenThreshSell) & ~dirBlocksShortHard
    dirTightenThreshSell = None  # free
    structReqShort = np.where(dirTightensShort, 2, 1)
    dirTightensShort = None  # free
    shortStructOk = ~dirBlocksShortHard & (structGateCount >= structReqShort)
    dirBlocksShortHard = structGateCount = structReqShort = None  # free
    dirBlocksLong = early <= -dirVetoThreshBuy
    dirVetoThreshBuy = early = None  # free

    trendAlignBuf = atr * _clamp(0.3 + _S(ph, 0.2, -0.06, 0.1, -0.05, 0.06, 0.05, 0.04, 0.05)
                                 + volR(0.15, -0.10) + _sel(C_, 0.15, aerConsolidation, -0.05, 0.0)
                                 + adxA(0.1, -0.1) + hurA(0.05, -0.05), 0.1, 0.8)
    aerConsolidation = volR = None  # free
    tsl = _sel(adx >= 30, 3, adx >= 20, 5, 7)
    tsl = tsl + _S(ph, -1, -1, 1, 0, 0, 1, 1, 1)
    tsl = tsl + _sel(T, -1, C_, 1, 0)
    tsl = tsl + hurA(-1, 1)
    tsl = np.clip(tsl, 2, 10).astype(np.int64)
    lagi = bar - tsl
    bar = tsl = None  # free
    ema100Lag = np.where(lagi >= 0, ema100[np.maximum(lagi, 0)], np.nan)
    lagi = None  # free
    shortTrendAlignOk = (c < ema100 - trendAlignBuf) & (ema100 < ema100Lag)
    longTrendAlignOk = (c > ema100 + trendAlignBuf) & (ema100 > ema100Lag)
    ema100 = ema100Lag = trendAlignBuf = None  # free

    shortVolumeScore = ((relVol >= mfiWtHi).astype(np.int64)
                        + ((fpDelta < 0) & (fpSellRatio >= trapFpRatio)) + fpDeltaBear
                        + (ema21 < _sh(ema21, 5)) + ((vwapVal - c) > atr * 0.5) + aerDowntrend
                        + ((c - nearestSupBelow) > atr * 1.0) + ((c < o) & ((o - c) > atr * 0.3)))
    fpDelta = nearestSupBelow = None  # free
    shortVolumeOk = shortStructOk & (shortVolumeScore >= int(P["short_min_rules"]))
    shortStructOk = shortVolumeScore = None  # free

    # ── overextension ──
    ema21DistAtr = (c - ema21) / atr
    ema21 = None  # free
    vwapDistAtr = (c - vwapVal) / atr
    sessDistAdj = _S(ph, 0.5, 0.3, -0.3, 0.0, 0.2, 0.0, 0.0, -0.4)
    vwapDyn = _sel(adx >= 35, 2.5, adx >= 25, 1.8, 1.2) + sessDistAdj
    mfiWt = _sel(relVol >= mfiWtHi, 1.5, relVol >= mfiWtLo, 1.0, 0.5)
    mfiWtHi = None  # free
    lowVolThr = _sel(isOpen, 0.6, isMorning, 0.65, isLunch, 0.9, isAfternoon, 0.8, inAsia, 0.9, T, 0.7, 0.8)
    sessThreshAdj = _S(ph, 0.75, 0.4, -0.5, -0.1, 0.3, 0.0, 0.0, -0.5)
    nodeAdjOx = _sel(nodeStrength >= 15, -0.3, nodeStrength >= 10, -0.15, nodeStrength < 5, 0.2, 0.0)
    adxOx = _sel(adx >= 35, 0.5, adx < 20, -0.5, 0.0)

    emaDynL = _sel(aerUptrend & (adx >= 30), 2.5, T, 2.0, C_, 1.0, 1.5) + sessDistAdj
    sc = np.zeros(n)
    sc = sc + _sel(ema21DistAtr >= emaDynL * 1.5, 2.0, ema21DistAtr >= emaDynL, 1.0, 0.0)
    emaDynL = None  # free
    sc = sc + _sel(vwapDistAtr >= vwapDyn * 1.3, 1.5, vwapDistAtr >= vwapDyn, 0.75, 0.0)
    sc = sc + np.where(lhBearish, _sel(htfConfScore >= X7, 0.5, htfConfScore >= X4, 1.0, 1.5), 0.0)
    sc = sc + np.where(mfiExhBuy, mfiWt * mfiMag, 0.0)
    mfiExhBuy = None  # free
    sc = sc + np.where(relVol < lowVolThr, _sel(htfConfScore >= X4, 1.0, 0.5), 0.0)
    sc = sc + np.where(wickBlocksShort, 0.5, 0.0)
    wickBlocksShort = None  # free
    th = np.full(n, 3.0)
    th = th + _sel(htfConfScore >= X7, 1.5, htfConfScore >= X4, 0.75, 0.0)
    th = th + _sel(aerUptrend, 0.5, C_, -0.5, 0.0)
    th = th + adxOx
    th = th + _sel(fpDeltaBull, 0.3 * deltaMag, fpDeltaBear, -0.3 * deltaMag, 0.0)
    th = th + hurA(0.3, -0.3)
    th = th + nodeAdjOx
    th = th + sessThreshAdj
    longOverextended = sc >= _clamp(th, 2.0, 6.5)

    emaDynS = _sel(aerDowntrend & (adx >= 30), 2.5, T, 2.0, C_, 1.0, 1.5) + sessDistAdj
    sessDistAdj = None  # free
    sc = np.zeros(n)
    sc = sc + _sel(-ema21DistAtr >= emaDynS * 1.5, 2.0, -ema21DistAtr >= emaDynS, 1.0, 0.0)
    emaDynS = None  # free
    sc = sc + _sel(-vwapDistAtr >= vwapDyn * 1.3, 1.5, -vwapDistAtr >= vwapDyn, 0.75, 0.0)
    vwapDistAtr = vwapDyn = None  # free
    sc = sc + np.where(hhBullish, _sel(htfConfScore <= -X7, 0.5, htfConfScore <= -X4, 1.0, 1.5), 0.0)
    sc = sc + np.where(mfiExhSel, mfiWt * mfiMag, 0.0)
    mfiExhSel = mfiMag = mfiWt = None  # free
    sc = sc + np.where(relVol < lowVolThr, _sel(htfConfScore <= -X4, 1.0, 0.5), 0.0)
    lowVolThr = None  # free
    sc = sc + np.where(wickBlocksLong, 0.5, 0.0)
    wickBlocksLong = None  # free
    th = np.full(n, 3.0)
    th = th + _sel(htfConfScore <= -X7, 1.5, htfConfScore <= -X4, 0.75, 0.0)
    th = th + _sel(aerDowntrend, 0.5, C_, -0.5, 0.0)
    th = th + adxOx
    adxOx = None  # free
    th = th + _sel(fpDeltaBear, 0.3 * deltaMag, fpDeltaBull, -0.3 * deltaMag, 0.0)
    deltaMag = None  # free
    th = th + hurA(0.3, -0.3)
    th = th + nodeAdjOx
    nodeAdjOx = None  # free
    th = th + sessThreshAdj
    sessThreshAdj = None  # free
    shortOverextended = sc >= _clamp(th, 2.0, 6.5)
    sc = th = None  # free

    sessionAllowed = bool(P["eth_enabled"]) | inRTH
    sigL = (sessionAllowed & vizSigL & (stratA_Long | stratB_Long | stratC_Long) & ~dirBlocksLong
            & ~dirBlocksLongFull & ~structBlocksLong & longTrendAlignOk & ~longOverextended)
    stratA_Long = stratB_Long = stratC_Long = vizSigL = None  # free
    sigS = (sessionAllowed & vizSigS & (stratA_Short | stratB_Short | stratC_Short) & shortVolumeOk
            & ~dirBlocksShortFull & ~structBlocksShort & shortTrendAlignOk & ~shortOverextended)
    stratA_Short = stratB_Short = stratC_Short = vizSigS = None  # free

    # ── confidence ──
    proxDist = _clamp(0.5 + _S(ph, 0.2, -0.06, -0.1, -0.05, 0.06, -0.15, -0.12, -0.15)
                      + regTC(0.15, -0.1) + adxA(0.1, -0.1), 0.2, 0.9) * atr
    near = lambda lvl, m=True: m & nn(lvl) & (np.abs(c - lvl) < proxDist)   # noqa: E731
    nearSupKey = ((near(pmLow) | near(pmMid) | near(orbLow, orbLocked) | near(orbMid, orbLocked)
                   | ((np.abs(c - vwapVal) < proxDist) & (c > vwapVal))
                   | (near(pivotPP) & (c > pivotPP)) | near(pivotS1))
                  & (((np.minimum(o, c) - l) > csBody * 0.5) | ((c > o) & fpDeltaBull)
                     | ((c > o) & (relVol >= confVolBounce))))
    nearResKey = ((near(pmHigh) | near(pmMid) | near(orbHigh, orbLocked) | near(orbMid, orbLocked)
                   | ((np.abs(c - vwapVal) < proxDist) & (c < vwapVal))
                   | (near(pivotPP) & (c < pivotPP)) | near(pivotR1))
                  & (((h - np.maximum(o, c)) > csBody * 0.5) | ((c < o) & fpDeltaBear)
                     | ((c < o) & (relVol >= confVolBounce))))
    confVolBounce = csBody = near = vwapVal = None  # free
    momThresh = _sel(T, 0.25, C_, 0.45, 0.35)
    adjThresh = np.maximum(0.1, momThresh + _S(ph, -0.08, 0.024, 0.1, 0.05, -0.024, 0.1, 0.08, 0.1))
    momThresh = None  # free
    inHotZone = (np.abs(sqzMom) / atr >= adjThresh) & (atr >= aerMeanATR * 0.85)
    adjThresh = aerMeanATR = None  # free
    htfConfThr = _sel(isOpen, 5.0, T, 4.5, 4.0)
    meanOk = np.abs(ema21DistAtr) <= 1.5
    ema21DistAtr = None  # free
    smU = sqzMom > sm1
    smD = sqzMom < sm1
    sm1 = None  # free
    momL = ((sqzFired & (sqzMom > 0)) | (sqzOn & (sqzMom > 0) & smU) | momRecentBull
            | (inHotZone & (sqzMom > 0) & smU))
    momRecentBull = smU = None  # free
    momS = ((sqzFired & (sqzMom < 0)) | (sqzOn & (sqzMom < 0) & smD) | momRecentBear
            | (inHotZone & (sqzMom < 0) & smD))
    inHotZone = momRecentBear = smD = sqzFired = sqzMom = sqzOn = None  # free
    confLong = ((htfConfScore >= htfConfThr).astype(np.int64) + (dirScoreFull >= 3.0)
                + (hlBullish & hhBullish) + fpDeltaBull + meanOk + momL
                + (bbPos <= _sel(aerUptrend, 0.25, C_, 0.45, 0.35)) + nearSupKey)
    momL = nearSupKey = None  # free
    confShort = ((htfConfScore <= -htfConfThr).astype(np.int64) + (dirScoreFull <= -3.0)
                 + (llBearish & lhBearish) + fpDeltaBear + meanOk + momS
                 + (bbPos >= _sel(aerDowntrend, 0.75, C_, 0.55, 0.65)) + nearResKey)
    bbPos = htfConfThr = meanOk = momS = nearResKey = None  # free

    # ── macro veto ──
    mvSess = _S(ph, 0.3, 0.25, 0.0, 0.1, 0.15, 0.0, 0.05, 0.0)
    mvThrSess = _S(ph, -0.3, -0.2, 0.3, 0.1, -0.1, 0.3, 0.2, 0.3)
    mvThrAdx = _sel(adx >= 35, -0.2, adx < 15, 0.2, 0.0)
    mvThrHur = _sel(hurstRevert, 0.3, hurstPersist, -0.2, 0.0)
    mvThrVol = _sel(relVol >= 2.0, -0.15, relVol < 0.7, 0.15, 0.0)

    def macro_override(htf_term, flow_flag, dir_flag):      # Pine's += sequence, in order
        ov = np.zeros(n)
        ov = ov + htf_term
        ov = ov + np.where(flow_flag, 0.5, 0.0)
        ov = ov + np.where(dir_flag, 0.5, 0.0)
        ov = ov + mvSess
        ov = ov + np.where(adx >= 30, 0.2, 0.0)
        ov = ov + np.where(relVol >= exitVolClimax, 0.2, 0.0)
        ov = ov + np.where(hurstPersist, 0.2, 0.0)
        return ov
    ovL = macro_override(_sel(htfConfScore >= X7, 1.0, htfConfScore >= X4, 0.5, 0.0),
                         fpDeltaBull, dirScoreFull >= 4.0)
    thrL = _clamp(_sel(aerDowntrend, 2.5, C_, 2.0, 1.5) + mvThrSess + mvThrAdx + mvThrHur + mvThrVol,
                  1.0, 3.5)
    macroVetoLong = (llBearish & lhBearish) & (ovL < thrL)
    lhBearish = llBearish = ovL = thrL = None  # free
    ovS = macro_override(_sel(htfConfScore <= -X7, 1.0, htfConfScore <= -X4, 0.5, 0.0),
                         fpDeltaBear, dirScoreFull <= -4.0)
    X4 = X7 = macro_override = None  # free
    thrS = _clamp(_sel(aerUptrend, 2.5, C_, 2.0, 1.5) + mvThrSess + mvThrAdx + mvThrHur + mvThrVol,
                  1.0, 3.5)
    mvThrAdx = mvThrHur = mvThrSess = mvThrVol = None  # free
    macroVetoShort = (hlBullish & hhBullish) & (ovS < thrS)
    hhBullish = hlBullish = ovS = thrS = None  # free

    ssExtra = _S(ph, 0, 0, 2, 0, 3, 0, 2, 1) + _sel(C_ & (adx < 20), 2, C_, 1, 0)

    bosTpMult = _clamp(1.1 + _S(ph, 0.15, 0.1, -0.15, 0.05, -0.05, -0.15, -0.1, -0.1)
                       + _sel(aerUptrend, 0.05, C_, -0.1, 0.0), 0.9, 1.3)
    reTpMult = _clamp(1.05 + _S(ph, -0.1, -0.05, -0.15, 0.15, 0.1, -0.1, -0.15, -0.15)
                      + _sel(aerUptrend, 0.05, C_, -0.1, 0.0) + hurA(0.05, -0.05), 0.8, 1.25)
    obTpMult = _clamp(1.0 + _S(ph, 0.15, -0.05, -0.1, 0.15, -0.2, 0.0, -0.15, -0.2)
                      + _sel(aerUptrend, 0.05, C_, -0.05, 0.0), 0.8, 1.2)
    trapTpMult = _clamp(0.85 + _S(ph, -0.1, 0.05, 0.0, -0.05, -0.1, -0.05, -0.2, -0.1)
                        + regTC(0.05, -0.05), 0.6, 1.0)
    regTC = None  # free

    gAdx = adxA(-0.2, 0.2)
    adxA = None  # free
    gHur = hurA(-0.1, 0.15)
    hurA = None  # free
    gVol = _sel(relVol >= exitVolClimax, -0.2, relVol < mfiWtLo, 0.2, 0.0)
    mfiWtLo = None  # free
    bosGateReqLong = np.maximum(_S(ph, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.5, 0.5), np.minimum(
        2.0, 1.0 + np.where(bosBuyConf >= 6, -0.5, 0.0)
        + _S(ph, -0.3, -0.15, 0.3, 0.15, -0.1, 0.5, 0.15, 0.2)
        + _sel(htfConfScore >= X5o, -0.3, htfConfScore <= -X3o, 0.3, 0.0)
        + _sel(aerUptrend, -0.15, aerDowntrend, 0.2, C_, 0.15, 0.0) + gAdx + gHur + gVol))
    bosGateReqShort = np.maximum(_S(ph, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0), np.minimum(
        2.0, 1.0 + np.where(bosSellConf >= 6, -0.5, 0.0)
        + _S(ph, -0.3, -0.15, 0.3, 0.15, -0.1, 0.5, 0.4, 0.5)
        + _sel(htfConfScore <= -X5o, -0.3, htfConfScore >= X3o, 0.3, 0.0)
        + _sel(aerDowntrend, -0.15, aerUptrend, 0.2, C_, 0.15, 0.0) + gAdx + gHur + gVol))
    X3o = X5o = aerDowntrend = aerUptrend = gAdx = gHur = gVol = htfConfScore = None  # free
    bosLongOptGates = (~structBlocksLong).astype(np.int64) + ~longOverextended
    bosShortOptGates = (~structBlocksShort).astype(np.int64) + ~shortOverextended

    povProxAtr = np.where(nn(povLevel), np.abs(c - povLevel) / atr, 99.0)
    pbt = _S(ph, 99.0, 99.0, 99.0, 99.0, 99.0, 1.5, 1.3, 1.5)
    pbt = pbt + _sel(adfMeanRevert, -0.2, adfTrending, 0.3, 0.0)
    adfMeanRevert = adfTrending = None  # free
    pbt = pbt + _sel(nodeStrength >= 15, -0.15, nodeStrength < 5, 0.2, 0.0)
    nodeStrength = None  # free
    pbt = pbt + _sel(adx < 20, -0.1, adx >= 35, 0.2, 0.0)
    pbt = pbt + _sel(hurstRevert, -0.1, hurstPersist, 0.15, 0.0)
    pbt = np.maximum(0.8, pbt)
    ethPovBlock = povProxAtr < pbt
    pbt = povProxAtr = None  # free

    # ── nearSup / nearRes (end of bar; the entry block reads the previous bar's) ──
    sup_c = [(pivotS1, T_), (pivotS2, T_), (pivotPP, T_), (orbLow, orbLocked), (pmLow, T_),
             (pmMid, T_), (vwapDn1, T_), (orbMid, orbLocked & showORBMid), (onLow, T_ & showON),
             (qqqDn1, T_ & showQ), (hvbZone1, T_), (hvbZone2, T_), (hvbZone3, T_), (povLevel, T_),
             (valLevel, T_), (vahLevel, T_), (fvgBullHi, T_), (obBullMid, T_), (obBearMid, T_),
             (rthLow, inETH | isOpen), (ema200, T_)]
    fvgBullHi = orbLow = pivotS1 = pivotS2 = pmLow = qqqDn1 = rthLow = vwapDn1 = None  # free
    res_c = [(pivotR1, T_), (pivotR2, T_), (pivotPP, T_), (orbHigh, orbLocked), (pmHigh, T_),
             (pmMid, T_), (vwapUp1, T_), (orbMid, orbLocked & showORBMid), (onHigh, T_ & showON),
             (qqqUp1, T_ & showQ), (hvbZone1, T_), (hvbZone2, T_), (hvbZone3, T_), (povLevel, T_),
             (vahLevel, T_), (valLevel, T_), (fvgBearHi, T_), (obBullMid, T_), (obBearMid, T_),
             (rthHigh, inETH | isOpen), (ema200, T_)]
    ema200 = fvgBearHi = hvbZone1 = hvbZone2 = hvbZone3 = obBearMid = obBullMid = orbHigh = None  # free
    orbLocked = orbMid = pivotPP = pivotR1 = pivotR2 = pmHigh = pmMid = povLevel = None  # free
    qqqUp1 = rthHigh = showON = showORBMid = showQ = vahLevel = valLevel = vwapUp1 = None  # free
    for k in range(3):
        sup_c += [(vrzL[:, k], T_), (vrzH[:, k], T_)]
        res_c += [(vrzH[:, k], T_), (vrzL[:, k], T_)]
    T_ = k = vrzH = vrzL = None  # free
    nearSupNow = np.full(n, -np.inf)
    for lvl, m in sup_c:
        nearSupNow = np.where(m & (lvl < c) & (lvl > nearSupNow), lvl, nearSupNow)
    sup_c = None  # free
    nearResNow = np.full(n, np.inf)
    for lvl, m in res_c:
        nearResNow = np.where(m & (lvl > c) & (lvl < nearResNow), lvl, nearResNow)
    lvl = m = res_c = None  # free
    nearSupNow = np.where(np.isinf(nearSupNow), np.nan, nearSupNow)
    nearResNow = np.where(np.isinf(nearResNow), np.nan, nearResNow)
    nearSup = _sh(nearSupNow, 1)
    nearSupNow = None  # free
    nearRes = _sh(nearResNow, 1)
    nearResNow = None  # free

    # ── session SL (reads nearSup/nearRes from the previous bar) ──
    sessLow = np.where(inAsia, np.where(nn(asiaLow), asiaLow, l),
                       np.where(inLondon, np.minimum(np.where(nn(asiaLow), asiaLow, l),
                                                     np.where(nn(londonLow), londonLow, l)),
                                np.where(nn(onLow), onLow, l)))
    asiaLow = londonLow = onLow = None  # free
    sessHigh = np.where(inAsia, np.where(nn(asiaHigh), asiaHigh, h),
                        np.where(inLondon, np.maximum(np.where(nn(asiaHigh), asiaHigh, h),
                                                      np.where(nn(londonHigh), londonHigh, h)),
                                 np.where(nn(onHigh), onHigh, h)))
    asiaHigh = londonHigh = onHigh = None  # free
    atrSlL = c - dynSlDistLong
    structEthL = np.where(sessLow > 0, sessLow - dynBufETH, c - dynSlDistLong)
    sessLow = None  # free
    slEthL = np.maximum(np.minimum(c + atr * 3.0, np.minimum(structEthL, atrSlL)), c - ethSlCap)
    structEthL = None  # free
    structRthL = np.where(nn(nearSup) & (nearSup < c), nearSup - dynBufLong, c - dynSlDistLong)
    dynBufLong = dynSlDistLong = nearSup = None  # free
    slRthL = np.minimum(c + atr * 3.0, np.minimum(structRthL, atrSlL))
    atrSlL = structRthL = None  # free
    sessionSlLong = np.minimum(np.where(inETH, slEthL, slRthL), c - atr * 1.0)
    slEthL = slRthL = None  # free
    atrSlS = c + dynSlDistShort
    structEthS = np.where(sessHigh > 0, sessHigh + dynBufETH, c + dynSlDistShort)
    dynBufETH = sessHigh = None  # free
    slEthS = np.minimum(np.maximum(c - atr * 3.0, np.maximum(structEthS, atrSlS)), c + ethSlCap)
    ethSlCap = structEthS = None  # free
    structRthS = np.where(nn(nearRes) & (nearRes > c), nearRes + dynBufShort, c + dynSlDistShort)
    dynBufShort = dynSlDistShort = nearRes = None  # free
    slRthS = np.maximum(c - atr * 3.0, np.maximum(structRthS, atrSlS))
    atrSlS = structRthS = None  # free
    sessionSlShort = np.maximum(np.where(inETH, slEthS, slRthS), c + atr * 1.0)
    inETH = slEthS = slRthS = None  # free

    # ═══ ENTRY CANDIDATES (position-independent; the walk applies isLong/isShort/isFlat) ═══
    minProfit = float(P["min_profit"])
    bosMinRules = int(P["bos_min_rules"])
    common_l = ~dirBlocksLong & ~dirBlocksLongFull & ~macroVetoLong
    dirBlocksLong = dirBlocksLongFull = None  # free
    common_s = ~dirBlocksShortFull & ~macroVetoShort
    dirBlocksShortFull = None  # free

    tp1 = starAdjTpLong(np.where(inRTH, mainTpLongAdj, sessionTpLong), confLong)
    ok1 = sigL & ~macroVetoLong & ((tp1 - c) >= minProfit)
    sigL = None  # free
    tp2 = starAdjTpLong(np.where(inRTH, bosTpLongAdj, sessionTpLong), confLong)
    bosTpLongAdj = None  # free
    tp2 = c + (tp2 - c) * bosTpMult
    ok2 = (sessionAllowed & bullBOS & (bosBuyConf >= bosMinRules) & longTrendAlignOk & common_l
           & ~ethPovBlock & (bosLongOptGates >= bosGateReqLong) & ((tp2 - c) >= minProfit))
    bosBuyConf = bosGateReqLong = bosLongOptGates = bullBOS = None  # free
    tp3 = starAdjTpLong(np.where(inRTH, obTpLongAdj, sessionTpLong), confLong)
    obTpLongAdj = None  # free
    tp3 = c + (tp3 - c) * obTpMult
    ok3 = (sessionAllowed & obBullTradeFire & common_l & ~structBlocksLong & longTrendAlignOk
           & ~longOverextended & ((tp3 - c) >= minProfit))
    obBullTradeFire = None  # free
    reRawL = np.where(inRTH, np.maximum(c + (mainTpLongAdj - c), c + tpFloorBuy), sessionTpLong)
    tp4 = c + (starAdjTpLong(reRawL, confLong) - c) * reTpMult
    reRawL = None  # free
    ok4 = (sessionAllowed & bullRetestOk & longsEnabled & common_l & ~structBlocksLong
           & longTrendAlignOk & ~longOverextended & ((tp4 - c) >= minProfit))
    bullRetestOk = None  # free
    trapRawL = np.where(inRTH, np.maximum(c + (mainTpLongAdj - c) * 0.9, c + tpFloorBuy), sessionTpLong)
    mainTpLongAdj = sessionTpLong = None  # free
    tp5 = c + (starAdjTpLong(trapRawL, confLong) - c) * trapTpMult
    starAdjTpLong = trapRawL = None  # free
    trapCap = _sel(isOpen, 2.5, isMorning, 2.0, isLunch, 1.8, isAfternoon, 2.0, inAsia, 1.5,
                   inLondon, 1.8, T, 2.2, 1.8)
    inAsia = inLondon = isAfternoon = isLunch = isMorning = isOpen = None  # free
    sl5 = np.maximum(np.minimum(sessionSlLong, l - atr * 0.3), c - atr * trapCap)
    ok5 = (sessionAllowed & bearSweep & longsEnabled & common_l & ~structBlocksLong
           & longTrendAlignOk & ~longOverextended & (fpDeltaBull | (fpBuyRatio >= trapFpRatio))
           & (confLong >= ssExtra + 1) & ((tp5 - c) >= minProfit))
    bearSweep = common_l = confLong = fpBuyRatio = longOverextended = longTrendAlignOk = structBlocksLong = None  # free
    chainL = _first_code([ok1, ok2, ok3, ok4, ok5])
    tpL = np.select([ok1, ok2, ok3, ok4, ok5], [tp1, tp2, tp3, tp4, tp5], np.nan)
    tp1 = tp2 = tp3 = tp4 = tp5 = None  # free
    slL = np.select([ok1, ok2, ok3, ok4, ok5],
                    [sessionSlLong, sessionSlLong, obBullSl, sessionSlLong, sl5], np.nan)
    obBullSl = ok1 = ok2 = ok3 = ok4 = ok5 = sessionSlLong = sl5 = None  # free
    odL = (odBuyRaw & longsEnabled & (dirScoreFull >= 0) & ~macroVetoLong
           & ((odTpLong - c) >= minProfit))
    longsEnabled = macroVetoLong = odBuyRaw = None  # free

    tq1 = starAdjTpShort(np.where(inRTH, mainTpShortAdj, sessionTpShort), confShort)
    oq1 = sigS & ~macroVetoShort & ((c - tq1) >= minProfit)
    sigS = None  # free
    tq2 = starAdjTpShort(np.where(inRTH, bosTpShortAdj, sessionTpShort), confShort)
    bosTpShortAdj = None  # free
    tq2 = c - (c - tq2) * bosTpMult
    bosTpMult = None  # free
    oq2 = (sessionAllowed & bearBOS & (bosSellConf >= bosMinRules) & shortTrendAlignOk & shortVolumeOk
           & common_s & ~ethPovBlock & (bosShortOptGates >= bosGateReqShort)
           & (confShort >= ssExtra + 3) & ((c - tq2) >= minProfit))
    bearBOS = bosGateReqShort = bosMinRules = bosSellConf = bosShortOptGates = ethPovBlock = None  # free
    tq3 = starAdjTpShort(np.where(inRTH, obTpShortAdj, sessionTpShort), confShort)
    obTpShortAdj = None  # free
    tq3 = c - (c - tq3) * obTpMult
    obTpMult = None  # free
    oq3 = (sessionAllowed & obBearTradeFire & shortVolumeOk & common_s & ~structBlocksShort
           & shortTrendAlignOk & ~shortOverextended & (confShort >= ssExtra + 1)
           & ((c - tq3) >= minProfit))
    obBearTradeFire = None  # free
    reRawS = np.where(inRTH, np.minimum(c - (c - mainTpShortAdj), c - tpFloorSell), sessionTpShort)
    tq4 = c - (c - starAdjTpShort(reRawS, confShort)) * reTpMult
    reRawS = reTpMult = None  # free
    oq4 = (sessionAllowed & bearRetestOk & shortVolumeOk & common_s & ~structBlocksShort
           & shortTrendAlignOk & ~shortOverextended & (confShort >= ssExtra + 1)
           & ((c - tq4) >= minProfit))
    bearRetestOk = None  # free
    trapRawS = np.where(inRTH, np.minimum(c - (c - mainTpShortAdj) * 0.9, c - tpFloorSell), sessionTpShort)
    inRTH = mainTpShortAdj = sessionTpShort = None  # free
    tq5 = c - (c - starAdjTpShort(trapRawS, confShort)) * trapTpMult
    starAdjTpShort = trapRawS = trapTpMult = None  # free
    sq5 = np.minimum(np.maximum(sessionSlShort, h + atr * 0.3), c + atr * trapCap)
    trapCap = None  # free
    oq5 = (sessionAllowed & bullSweep & shortVolumeOk & common_s & ~structBlocksShort
           & shortTrendAlignOk & ~shortOverextended & (fpDeltaBear | (fpSellRatio >= trapFpRatio))
           & (confShort >= ssExtra + 1) & ((c - tq5) >= minProfit))
    bullSweep = common_s = confShort = fpSellRatio = sessionAllowed = shortOverextended = shortTrendAlignOk = shortVolumeOk = None  # free
    ssExtra = structBlocksShort = trapFpRatio = None  # free
    chainS = _first_code([oq1, oq2, oq3, oq4, oq5])
    tpS = np.select([oq1, oq2, oq3, oq4, oq5], [tq1, tq2, tq3, tq4, tq5], np.nan)
    tq1 = tq2 = tq3 = tq4 = tq5 = None  # free
    slS = np.select([oq1, oq2, oq3, oq4, oq5],
                    [sessionSlShort, sessionSlShort, obBearSl, sessionSlShort, sq5], np.nan)
    obBearSl = oq1 = oq2 = oq3 = oq4 = oq5 = sessionSlShort = sq5 = None  # free
    odS = (odSellRaw & (dirScoreFull <= 0) & ~macroVetoShort & ((c - odTpShort) >= minProfit))
    dirScoreFull = macroVetoShort = minProfit = odSellRaw = None  # free

    return dict(chainL=chainL, tpL=tpL, slL=slL, odL=np.asarray(odL, bool), odTpL=odTpLong,
                odSlL=odSlLong, chainS=chainS, tpS=tpS, slS=slS, odS=np.asarray(odS, bool),
                odTpS=odTpShort, odSlS=odSlShort, atr=atr)


# ═════════════════════════════════════════════════════════════════════════════
# Roll-seam calendar for the walk
# ═════════════════════════════════════════════════════════════════════════════

def _seam_masks(epoch, loc, tf):
    """(no_fill, flat_bar) from the engine's roll context: flat at the close of the last
    bar that ends at or before each switch; no entry fill on that bar's ET calendar day up
    to it, nor inside a bar the switch splits."""
    n = len(epoch)
    no_fill = np.zeros(n, bool)
    flat_bar = np.zeros(n, bool)
    from augur_engine import rolls as _R
    ctx = _R.current_roll_context()
    if ctx is None:
        raise _R.RollContextMissing(
            "MISC_SUPERSCALPER needs the roll calendar: run it through augur_engine.run_backtest "
            "or wrap the call in augur_engine.rolls.roll_context(root, bar_times, bar_seconds).")
    root = ctx.get("root")
    if root is None or n == 0:
        return no_fill, flat_bar
    inst, _off, _ib = _R._switch_arrays(root, ctx.get("table_dir"))
    if not len(inst):
        return no_fill, flat_bar
    inst = inst[(inst > epoch[0]) & (inst < epoch[-1] + tf)]
    ends = epoch + tf
    day = loc // 86400
    for s in inst:
        e = int(np.searchsorted(ends, s, side="right")) - 1     # last bar ending <= switch
        if e >= 0:
            flat_bar[e] = True
            first = int(np.searchsorted(day, day[e], side="left"))
            no_fill[first:e + 1] = True
        split = (epoch < s) & (ends > s)
        no_fill |= split
    return no_fill, flat_bar


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def _params(params):
    P = {k: v["default"] for k, v in DEFAULT_PARAMS.items()}
    for k, v in params.items():
        if k in P:
            P[k] = v
    for k, meta in DEFAULT_PARAMS.items():
        t = meta.get("type")
        if t == "int":
            P[k] = int(round(float(P[k])))
        elif t == "float":
            P[k] = float(P[k])
        elif t == "bool":
            P[k] = (str(P[k]).strip().lower() in ("1", "true", "yes")) if isinstance(P[k], str) else bool(P[k])
        else:
            P[k] = str(P[k])
    return P


def _time_arrays(index, n):
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    epoch = _epoch_s(idx.tz_convert("UTC"))
    loc = _epoch_s(idx.tz_convert("America/New_York").tz_localize(None))
    d = np.diff(epoch)
    d = d[d > 0]
    tf = int(np.median(d)) if len(d) else 60
    return epoch, loc, max(tf, 1)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, _stop_event=None, _pause_event=None, **params):
    o = np.ascontiguousarray(_f(opens)); h = np.ascontiguousarray(_f(highs))
    l = np.ascontiguousarray(_f(lows)); c = np.ascontiguousarray(_f(closes))
    n = len(c)
    if n < 250 or index is None or len(index) != n:
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    v = np.ascontiguousarray(_f(volumes)) if volumes is not None and len(volumes) == n else np.zeros(n)
    P = _params(params)
    epoch, loc, tf = _time_arrays(index, n)
    _N_BARS[0] = n

    feeds_mode = str(params.get("_feeds", "auto")).lower()
    want = feeds_mode == "on"
    if feeds_mode == "auto":
        try:
            from augur_engine import rolls as _R
            ctx = _R.current_roll_context()
            want = bool(ctx and ctx.get("root") == "NQ")
        except Exception:
            want = False
    feeds = _feeds(epoch, P["spy_proxy"], want and feeds_mode != "off",
                   inject_es=params.get("_feed_es"), inject_qqq=params.get("_feed_qqq"))
    if P["vix_feed"] == "daily":
        last_day = int((loc[-1] + 6 * 3600) // 86400)   # the last bar's CME trading date
        inj = params.get("_feed_vix")         # tests: (dates, closes) instead of a file
        if inj is not None:
            vd, vc = _vix_table(*inj)
            vd, vc = vd[vd <= last_day], vc[vd <= last_day]
        else:
            vd, vc = _load_vix_daily(str(params.get("_vix_file", "raw")), last_day)
        feeds = tuple(feeds) + _vix_daily(loc, vd, vc)

    sig = _build(o, h, l, c, v, epoch, loc, tf, P, feeds)
    if P["session_filter"] != "all":        # OUR PORT: entries only from the chosen signal-bar window (New York time)
        m_ny = (loc // 60) % 1440
        in_rth = (m_ny >= 570) & (m_ny < 960)                      # 09:30-15:59, the r2 E1 split
        drop = in_rth if P["session_filter"] == "outside_rth" else ~in_rth
        sig = dict(sig)
        for k in ("chainL", "chainS"):
            sig[k] = np.where(drop, 0, sig[k]).astype(sig[k].dtype)
        for k in ("odL", "odS"):
            sig[k] = np.asarray(sig[k], bool) & ~drop
    no_fill, flat_bar = _seam_masks(epoch, loc, tf)
    if _stop_event is not None and _stop_event.is_set():
        return None

    n_sig = int((sig["chainL"] > 0).sum() + sig["odL"].sum() + (sig["chainS"] > 0).sum()
                + sig["odS"].sum())
    max_trades = 2 * n_sig + 8
    tick = float(params.get("_tick", 0.25))

    def lvl(x):                     # TV rounds order prices to the symbol tick (nearest)
        x = _f(x)
        return np.ascontiguousarray(np.floor(x / tick + 0.5) * tick if tick > 0 else x)
    atr = sig["atr"]                # OUR PORT exit knobs: after every entry gate
    tpL, slL = _exit_levels(c, atr, sig["tpL"], sig["slL"], True, P,
                            np.isin(sig["chainL"], _SESSION_STOP_PATHS))
    odTpL, odSlL = _exit_levels(c, atr, sig["odTpL"], sig["odSlL"], True, P)     # OD: no cap
    tpS, slS = _exit_levels(c, atr, sig["tpS"], sig["slS"], False, P,
                            np.isin(sig["chainS"], _SESSION_STOP_PATHS))
    odTpS, odSlS = _exit_levels(c, atr, sig["odTpS"], sig["odSlS"], False, P)
    walk = _kern("walk")
    res = walk(o, h, l, c,
               sig["chainL"], lvl(tpL), lvl(slL), sig["odL"], lvl(odTpL), lvl(odSlL),
               sig["chainS"], lvl(tpS), lvl(slS), sig["odS"], lvl(odTpS), lvl(odSlS),
               no_fill, flat_bar, int(P["pyramiding"]), P["intrabar"] == "tv",
               P["close_rule"] == "fifo", max_trades, int(P["max_hold_bars"]),
               float(P["be_trigger"]))
    eb, xb, sd, ep, xp, rs, pa, sg, tsl, ttp, bsl, btp, max_open = res
    if len(eb) == 0:
        return None
    pnls = np.where(sd > 0, xp - ep, ep - xp).astype(np.float64)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float(min(0.0, (cum - peak).min())),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = [(int(eb[i]), int(xb[i]), float(pnls[i]), int(sd[i]), float(ep[i]),
                          float(xp[i])) for i in range(len(eb))]
    if params.get("_detail"):
        out["trade_detail"] = [
            {"entry_bar": int(eb[i]), "exit_bar": int(xb[i]), "signal_bar": int(sg[i]),
             "side": int(sd[i]), "entry_price": float(ep[i]), "exit_price": float(xp[i]),
             "pnl_pts": float(pnls[i]), "path": PATH_NAMES.get(int(pa[i]), "?"),
             "exit_reason": EXIT_NAMES.get(int(rs[i]), "?"),
             "ticket_sl": float(tsl[i]), "ticket_tp": float(ttp[i]),
             "exit_order_sl": float(bsl[i]), "exit_order_tp": float(btp[i]),
             "signal_close": float(c[sg[i]]), "signal_atr": float(atr[sg[i]])}
            for i in range(len(eb))]
        out["max_open_tickets"] = int(max_open)
    return out

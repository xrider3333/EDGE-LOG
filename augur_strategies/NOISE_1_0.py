"""
NOISE 1.0 — wide-band intraday momentum envelope (VWAP-exit variant).

Concept credit: Zarattini/Aziz/Barbon "Beat the Market" — trade a session-relative
envelope: UB/LB anchored to the wider of {today's open, yesterday's close}, band
WIDTH scaled by a rolling realized-noise estimate (sigma = mean |close-open| /
open over the prior LOOKBACK sessions, read at the SAME bar-of-day index every
time). A CLOSE outside the band is the momentum entry, filled next bar's open; a
CLOSE back inside a reference (VWAP, by default) is the mean-reversion exit.
EDGELOG's challenger rounds 10-12 (2026-07) found the paper's own tight bands
(~1.0x, 14-day lookback) choppy/regime-fragile on NQ 5m — widening to 1.5x
SYMMETRIC bands + switching the exit from "back inside the entry band" to "back
below session VWAP" made the edge regime-healthy across the whole 2010-2025 span
instead of just a concentrated slice of it.

Full engine spec + the checkpoint-gated research build lives in
tools/noise_research.py (the "sigma[t] / ref_hi / ref_lo / signals at bar closes,
fills at next open / vwap-band-boundary exits / EOD flat" contract, INCLUDING the
warmup and re-entry rules) — this file is a straight, byte-for-byte port of that
engine into the house run_backtest(opens,highs,lows,closes,...) contract. Read
that file first if you're touching the entry/exit math; this docstring only
covers the plugin-specific surface (params, presets, validation status).

VALIDATION STATUS (stated honestly — read before treating this as "validated"):
  PASSED the IS/WF battery 4/5 (walk-forward 5/6 folds green, neighborhood
  stability, family-level consistency, bootstrap P ~ 0 on the in-sample edge).
  FAILED NOISE's own pre-registered ES-transfer promotion bar (requires PF >=
  1.2; best observed is PF ~1.03-1.12 across rounds, ES PF 1.12 in round-12).
  Note: the engine's generic per-run cross-instrument sanity check (validate.py's
  transfer gate, PF >= 1.0) is a DIFFERENT, looser bar than NOISE's own 1.2
  promotion requirement -- a validate run can show that generic check "pass"
  (e.g. run #225, PF 1.033) without NOISE having cleared ES-transfer for
  promotion purposes. That failure stands.
  The lockbox for this family (2025-06-30 -> 2026-06-30) is SPENT — it has
  been read multiple times: full-window auto-validates runs 202/203 rendered
  and analyzed the lockbox slice in detail (the owner's own LB-gyration
  investigation 2026-08-09/10), and the 2026-08-11 pre-registered gate test
  read it again. Any future lockbox read is CONFIRMATORY ONLY; it can never
  be used to promote NOISE.
  Net: this is an OWNER-DIRECTED BACKEND-TESTING PROMOTION, not a crowned
  strategy — it clears the owner's stated IS/WF bar, but it has NOT cleared the
  full validation roadmap (ES-transfer failed, lockbox spent/confirmatory-only),
  and it is not in the current book. Forward paper trading is the only
  remaining new-evidence path. Runnable in Builder -> Auto-Validate for
  further work.

Reference numbers (frozen defaults, NQ 5m RTH, source=db_noadj_rth, cost_pts=0.533,
data <= 2025-06-29): n=3,147 trades, net $254,383, PF 1.31, DD -$31,240, MAR 8.14.
2010-2017 (the paper's own tighter-config era): +$15.8k net — the wide-band/VWAP-
exit config is what keeps that early stretch from being a drag, not a highlight.

Known weakness (banked autopsy): 2020 is the softest year in the per-year P&L —
the VWAP exit whipsaws hardest in extreme-volatility regimes (COVID crash/recovery)
because VWAP itself is at its noisiest exactly then. Not fixed here; a vol-regime
filter is the natural next lever if this gets picked up again.

PNL = SHARES*(EXIT-ENTRY); fees (cost_pts) are applied downstream by the engine,
not inside this file (see tools/noise_research.py's docstring for why that
convention matters: it's the same _apply_costs() every plugin goes through).

2026-08-08 -- protective stop researched and validated (pre-lockbox). NOISE had
NO stop-loss at all -- its only exit was the VWAP cross (or the band exit in
'band' mode) -- so after a breakout entry that went wrong, VWAP sat far behind
price and losers could run a long way before the exit rule caught up. Round-16
research (scratchpad/noise_exits.py -> promoted to tools/noise_exits_research.py;
full writeup in docs/samples/noise_exits_report.md) tested 25 exit/stop variants
pre-lockbox (date_to=2025-06-29) under a pre-registered adoption rule (worst
trade cut >=40%, net >=85% of baseline, MAR >= baseline, 2010-17 subtotal >= $0).
WINNER: a protective stop at k x (the entry bar's own band excursion), k=1.0 --
now shippable as stop_mode='bandwidth', stop_k=1.0 below. Reviewer-audited
numbers, NQ 5m RTH, source=db_noadj_rth, cost_pts=0.533, date_to=2025-06-29:
  baseline (no stop): n=3147 . net $254,382.98 . maxDD -$31,239.80 . MAR 8.143 .
    worst trade -$15,465.66
  with stop k=1.0   : n=3185 . net $268,371.16 . maxDD -$21,659.59 . MAR 12.390 .
    worst trade -$4,707.10
  exit mix with stop: primary(vwap) 1960 . eod 954 . stop 271. Stops on the
  entry bar: 0. Optimistic fills: 0/271. Eras (2010-17 / 2018-20 / 2021-25):
  baseline $15,845 / $35,077 / $203,461 -> with stop $15,264 / $45,708 / $207,399.
HONEST CAVEATS (read before treating this as more validated than it is):
  (a) this family's LOCKBOX IS SPENT (see VALIDATION STATUS above) -- the
      protective-stop variant itself has NOT been holdout-tested. It needs a
      paper-forward stretch before it's anything more than a pre-lockbox finding.
  (b) the stop does NOT fix the regime concentration this file already banks as
      a known weakness -- pre-2018 is still only ~6% of total profit either way
      ($15,845 of $254,383 baseline = 6.2%; $15,264 of $268,371 with-stop = 5.7%).
Ships default OFF (stop_mode='off') -- every reference number and docstring
claim elsewhere in this file is unaffected until someone opts in.

2026-08-17 -- entry-quality filters researched pre-lockbox (variant campaign vs the
run-#231 champion: lookback 44, bands 0.75/1.5, vwap exit, bandwidth stop k=1.75).
Methodology mirrored the 2026-08-08 stop research: adoption bar PRE-REGISTERED
before any backtest (net >= champion, MAR >= champion, 2010-17 subtotal >= $0,
worst year not worse, plateau across pre-declared threshold neighbors, mechanism
sanity), ALL selection on the pre-lockbox window (2010-06-07 -> 2025-02-10, run
#231's optimize window; the 2025-02-11 -> 2026-08-12 lockbox is SPENT and was
read exactly once, confirmatory, AFTER the pick). Harness: tools/
noise_variant_research.py (parity vs this file proven exact to the cent).
Champion baseline on the selection window: n=5,113 . net $277,123.31 . PF 1.2406 .
maxDD -$19,482.27 . MAR 14.22 . 2010-17 +$11,524 . worst year 2010 -$2,278.
WINNER (pre-registered Occam combo rule): confirm_bars=2 + daytype_mode=
'skip_bot_short' -- require 2 consecutive closes outside the band before entering,
and take no SHORT entries on a day whose PRIOR day closed in the bottom 20% of its
own range (the program-wide "shorts fail after weak closes / buy-weakness" pattern,
banked across 4+ families):
  n=4,010 . net $332,699.25 . PF 1.3992 . maxDD -$14,076.45 . MAR 23.64 .
  2010-17 +$22,262 . worst year 2010 -$1,581 . only negative year = 2010.
  Neighborhood: every neighbor (daytype_lo 0.15/0.25, confirm 3, lookback 36/52,
  band_mult_long 0.5/1.0, band_mult_short 1.25/1.75, stop_k 1.5/2.0) stays at
  $303k-$338k net, MAR 17-24.7 -- a plateau, not a magic cell.
  Also individually clearing the bar (banked, not shipped as defaults):
  vol_skip_pct=90 (skip entries when the PRIOR day's range percentile vs the
  trailing 252 sessions is >= 90; plateau 90/95/98; day-clustered permutation
  p=0.001 that those days underperform) -- n=4,309 . net $310,689.59 . MAR 16.32.
  Dead ends (banked): vol-conditional exit switch (the k1.75 stop already does
  that job), time-decay exits, asymmetric stop_k, skip-after-loss, skip-low-vol.
  CONFIRMATORY one-look (full window incl. the SPENT lockbox, never used for
  selection): net $367,959 . PF 1.322; lockbox slice positive (+$35.3k, PF 1.11)
  but SMALLER than the baseline champion's same slice (+$58.9k) -- the filters
  gave back some 2025-26 profit; carried honestly, the pre-lockbox bar is what
  was pre-registered. All four filter knobs ship default OFF -- byte-identical
  baseline when untouched (smoke tests a/b unchanged below).
"""
import numpy as np

STRATEGY_NAME = 'NOISE 1.0 · intraday momentum envelope'
DESCRIPTION   = ("Wide symmetric bands (1.5x a rolling realized-noise estimate) around "
                 "the wider of today's open / yesterday's close. Momentum breakout entry "
                 "at the next bar's open, VWAP mean-reversion exit by default. NQ 5m "
                 "default. Owner-directed backend-testing promotion — passes the IS/WF "
                 "bar, has NOT cleared its own ES-transfer promotion bar (PF >= 1.2; "
                 "the engine's generic per-run transfer check, PF >= 1.0, is a looser, "
                 "different bar) or the lockbox.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# From-scratch concept (Zarattini/Aziz/Barbon), not a fork of an existing EDGELOG
# family -- deliberately no _AUGUR_PARENT.

DEFAULT_PARAMS = {
    "lookback": {
        "default": 14, "min": 5, "max": 120, "step": 1, "type": "int",
        "label": "Noise lookback (sessions)",
        "tooltip": "How many PRIOR days feed the band-width estimate (how 'noisy' this "
                   "time of day usually is). 14 = the frozen/validated setting. Shorter "
                   "reacts faster to a changing regime but is a noisier estimate itself.",
    },
    "band_mult_long": {
        "default": 1.5, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Upper band width (x noise)",
        "tooltip": "How far above the reference level the long-side band sits, as a "
                   "multiple of the noise estimate. 1.5 validated -- WIDE on purpose. "
                   "Widths BELOW ~1.25 revert toward the original paper's config, which "
                   "EDGELOG's own testing found choppier / regime-concentrated (only "
                   "worked well in a slice of years) rather than robust across the full "
                   "2010-2025 span.",
    },
    "band_mult_short": {
        "default": 1.5, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Lower band width (x noise)",
        "tooltip": "Same as the upper band width, mirrored for the short side. 1.5 "
                   "validated (symmetric). Widths BELOW ~1.25 revert toward the original "
                   "paper's narrower, regime-concentrated config -- see the upper-band "
                   "tooltip.",
    },
    "exit_mode": {
        "default": "vwap", "type": "str",
        "options": ["vwap", "band", "boundary"],
        "label": "Exit rule",
        "tooltip": "vwap (validated default) = exit when price closes back across the "
                   "session's running VWAP -- needs volume data; silently falls back to "
                   "'band' if this master has none. band = exit when price closes back "
                   "INSIDE the entry band (the original paper's exit). boundary = a "
                   "tighter intrabar stop right at the band level (fills immediately on "
                   "a touch, not on the next bar's open) -- more trades, smaller ones, "
                   "unvalidated at scale.",
    },
    "side": {
        "default": "Both", "type": "str",
        "options": ["Both", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either band break (validated). Long/Short Only for "
                   "research -- band math is unchanged, this only suppresses entries on "
                   "the disallowed side.",
    },
    "window": {
        "default": "all_day", "type": "str",
        "options": ["all_day", "morning", "afternoon_block"],
        "label": "Entry window",
        "tooltip": "all_day (validated) = new entries allowed any time. morning = only "
                   "take NEW entries in roughly the first 2.5 hours of the session. "
                   "afternoon_block = block NEW entries in roughly the last 2 hours. "
                   "Either way, a position already open keeps being managed normally -- "
                   "this only gates fresh signals.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight) -- this is a "
                   "hard rule of the engine itself (always applied, every session), not "
                   "actually a toggle. Keep ON; present for contract consistency with "
                   "the other EDGELOG strategy files.",
    },
    "skip_holidays": {
        "default": False, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close / half-day sessions (Thanksgiving, Christmas Eve, "
                   "Memorial Day, July-3, etc) -- detected by session LENGTH (a half-day "
                   "has far fewer bars than a normal RTH day), same helper as ORB_3_0. "
                   "OFF by default = no change (matches the validated numbers above); "
                   "turn ON to avoid them. The rolling noise estimate still LEARNS from "
                   "a skipped half-day (it's real market data); this only stops the "
                   "engine from trading it.",
    },
    "stop_mode": {
        "default": "off", "type": "str",
        "options": ["off", "bandwidth", "atr", "fixed"],
        "label": "Protective stop",
        "tooltip": "NOISE's ONLY exit by default is the VWAP cross (or the band-mode "
                   "equivalent) -- there is NO stop-loss, so after a breakout entry "
                   "that goes wrong, VWAP sits far behind price and losers can run a "
                   "long way before the exit rule catches up (the frozen baseline's "
                   "worst trade is -$15,466). off (default) = no change, matches every "
                   "validated number in this file. bandwidth = the RESEARCHED WINNER "
                   "(2026-08-08, reviewer-audited) -- a stop set at k x how far THIS "
                   "trade's entry bar broke outside its own band, so a trade that broke "
                   "out further gets more room and one that barely broke out gets a "
                   "tighter leash. atr = a stop at k x the prior-20-session average "
                   "daily range, in points -- RESEARCH-ONLY, not separately validated. "
                   "fixed = a stop at a flat k x 100 points -- RESEARCH-ONLY, not "
                   "separately validated.",
    },
    "confirm_bars": {
        "default": 1, "min": 1, "max": 4, "step": 1, "type": "int",
        "label": "Entry confirmation (closes outside band)",
        "tooltip": "How many CONSECUTIVE bar closes outside the band are required "
                   "before entering (filled at the next bar's open, as always). 1 = "
                   "the frozen behavior (first close outside enters, no change). 2 = "
                   "the 2026-08-17 researched winner -- waits one extra bar for "
                   "confirmation, cutting the one-bar head-fakes.",
    },
    "daytype_mode": {
        "default": "off", "type": "str",
        "options": ["off", "skip_bot_short", "skip_bot_all", "skip_top_long", "skip_top_all"],
        "label": "Prior-day close-position filter",
        "tooltip": "Gate today's NEW entries on where YESTERDAY closed inside its own "
                   "range ((close-low)/(high-low), known before today's open -- fully "
                   "causal). off (default) = no change. skip_bot_short = the 2026-08-17 "
                   "researched winner: take no SHORT entries the day after a close in "
                   "the bottom 20% of the day's range (shorts after weak closes is the "
                   "program-wide losing pattern). skip_bot_all blocks both sides on "
                   "those days; the two skip_top modes mirror at the top 20% (research-"
                   "only, tested WORSE -- kept for completeness).",
    },
    "daytype_lo": {
        "default": 0.2, "min": 0.05, "max": 0.45, "step": 0.05, "type": "float",
        "label": "Bottom close-position threshold",
        "tooltip": "The skip_bot_* cutoff: yesterday's close-position at or below this "
                   "counts as a bottom close. 0.2 researched; 0.15/0.25 neighbors also "
                   "clear the bar (plateau). Only read when daytype_mode is a skip_bot "
                   "mode.",
    },
    "daytype_hi": {
        "default": 0.8, "min": 0.55, "max": 0.95, "step": 0.05, "type": "float",
        "label": "Top close-position threshold",
        "tooltip": "The skip_top_* cutoff (mirror of daytype_lo). Research-only; the "
                   "skip_top modes tested WORSE than baseline.",
    },
    "vol_skip_pct": {
        "default": 0.0, "min": 0.0, "max": 99.0, "step": 1.0, "type": "float",
        "label": "Skip entries above prior-day vol percentile (0=off)",
        "tooltip": "0 (default) = no change. Otherwise: take no NEW entries on a day "
                   "whose PRIOR day's range/close, percentile-ranked against the "
                   "trailing 252 sessions (strictly prior -- fully causal), is at or "
                   "above this value. 90 = the 2026-08-17 researched single (skips the "
                   "top-decile vol days, where NOISE's day-mean is -$100 vs +$142 "
                   "elsewhere, day-clustered permutation p=0.001; plateau at 90/95/98). "
                   "Cleared the pre-registered bar alone but is NOT part of the shipped "
                   "winner combo (the combo with it failed the beat-best-component "
                   "rule).",
    },
    "stop_k": {
        "default": 1.0, "min": 0.25, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stop size (x band excursion / ATR / points)",
        "tooltip": "Multiplier applied in whatever unit the Protective stop mode above "
                   "measures -- band-excursion points for 'bandwidth', prior-20-session "
                   "ATR points for 'atr', or flat 100-pt units for 'fixed'. k=1.0 under "
                   "'bandwidth' is the validated cell (net $254,383->$268,371, max "
                   "drawdown -$31,240->-$21,660, worst trade -$15,466->-$4,707, MAR "
                   "8.14->12.39; NQ 5m RTH, pre-lockbox). Other k values and the other "
                   "two modes are research-only, not separately validated.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (frozen + near plateau)": {
        "lookback": [10, 14, 21], "band_mult_long": [1.4, 1.5, 1.6],
        "band_mult_short": [1.5], "exit_mode": ["vwap"], "side": ["Both"],
        "window": ["all_day"],
    },
    "Medium (round-11 core)": {
        "lookback": [14, 30], "band_mult_long": [1.0, 1.25, 1.5],
        "band_mult_short": [1.25, 1.5], "exit_mode": ["vwap", "band"],
        "side": ["Both", "Long Only"], "window": ["all_day"],
    },
    "Long   (full round-11 grid)": {
        # 3 lookback x 3 bml x 3 bms x 2 exit x 2 window = 108 cells (side held at
        # 'Both'; boundary exit excluded -- it's a different/unvalidated fill model,
        # kept out of the round-11-style vwap-vs-band sweep).
        "lookback": [10, 14, 21], "band_mult_long": [1.0, 1.25, 1.5],
        "band_mult_short": [1.0, 1.25, 1.5], "exit_mode": ["vwap", "band"],
        "side": ["Both"], "window": ["all_day", "morning"],
    },
    "Stop  (protective-stop sweep)": {
        "stop_mode": ["off", "bandwidth"], "stop_k": [0.5, 1.0, 1.5, 2.0],
        "lookback": [14], "band_mult_long": [1.5], "band_mult_short": [1.5],
        "exit_mode": ["vwap"], "side": ["Both"], "window": ["all_day"],
    },
    "Filter (2026-08-17 winner vs champion)": {
        # The #231 champion core PINNED; only the researched filter knobs vary.
        # Includes the exact champion cell (confirm 1 / off / 0) so a validate on
        # this preset is a controlled champion-vs-variant comparison. 12 cells.
        "lookback": [44], "band_mult_long": [0.75], "band_mult_short": [1.5],
        "exit_mode": ["vwap"], "side": ["Both"], "window": ["all_day"],
        "stop_mode": ["bandwidth"], "stop_k": [1.75],
        "confirm_bars": [1, 2, 3], "daytype_mode": ["off", "skip_bot_short"],
        "vol_skip_pct": [0.0, 90.0],
    },
}


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b)); a = b
    return bounds


def _sigma_matrix(o, c, sess_bounds, lookback):
    n_sess = len(sess_bounds)
    max_len = max((b - a) for a, b in sess_bounds) if sess_bounds else 0
    AD = np.full((n_sess, max_len), np.nan, dtype=float)
    for si, (a, b) in enumerate(sess_bounds):
        o0 = o[a]
        m = b - a
        AD[si, :m] = np.abs(c[a:b] - o0) / o0
    sigma = np.full((n_sess, max_len), np.nan, dtype=float)
    with np.errstate(invalid="ignore"):
        for si in range(lookback, n_sess):
            sigma[si, :] = np.nanmean(AD[si - lookback:si, :], axis=0)
    return sigma


def _atr_by_session(h, l, sess_bounds, period):
    """ATR20d convention (research-only stop_mode='atr'): mean of (session high -
    session low) over the PRIOR `period` sessions, strictly prior -- no lookahead.
    NaN until `period` prior sessions exist, same as the sigma warmup; the stop
    is then skipped for that trade (falls back to no-stop for it). Matches
    tools/noise_exits_research.py's compute_atr_by_session exactly."""
    n_sess = len(sess_bounds)
    sess_range = np.array([h[a:b].max() - l[a:b].min() for a, b in sess_bounds], float)
    atr = np.full(n_sess, np.nan, dtype=float)
    for si in range(period, n_sess):
        atr[si] = sess_range[si - period:si].mean()
    return atr


def _vol_percentile(h, l, c, sess_bounds, ref_n=252, min_obs=60):
    """vol_skip_pct helper (2026-08-17): pct[si] = percentile rank of the PRIOR
    session's (H-L)/C among the ref_n sessions strictly before that prior session.
    NaN when fewer than min_obs reference sessions exist (treated as not-extreme,
    i.e. the filter stays inactive that day). Fully causal: session si only ever
    reads sessions that FINISHED before si opens."""
    n_sess = len(sess_bounds)
    vals = np.array([(h[a:b].max() - l[a:b].min()) / c[b - 1] for a, b in sess_bounds], float)
    pct = np.full(n_sess, np.nan, dtype=float)
    for si in range(1, n_sess):
        j = si - 1
        lo = max(0, j - ref_n)
        ref = vals[lo:j]
        if len(ref) >= min_obs:
            pct[si] = 100.0 * np.mean(ref < vals[j])
    return pct


def _daytype_pos(h, l, c, sess_bounds):
    """daytype_mode helper (2026-08-17): pos[si] = the PRIOR session's close
    position in its own range, (C-L)/(H-L). NaN for the first session or a
    zero-range day (filter inactive). Fully causal."""
    n_sess = len(sess_bounds)
    cp = np.full(n_sess, np.nan, dtype=float)
    for si in range(1, n_sess):
        a, b = sess_bounds[si - 1]
        rng = h[a:b].max() - l[a:b].min()
        if rng > 1e-12:
            cp[si] = (c[b - 1] - l[a:b].min()) / rng
    return cp


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    lookback: int = 14, band_mult_long: float = 1.5, band_mult_short: float = 1.5,
    exit_mode: str = "vwap", side: str = "Both", window: str = "all_day",
    flat_eod: bool = True, skip_holidays: bool = False,
    stop_mode: str = "off", stop_k: float = 1.0,
    confirm_bars: int = 1, daytype_mode: str = "off",
    daytype_lo: float = 0.2, daytype_hi: float = 0.8,
    vol_skip_pct: float = 0.0,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    # vwap needs volume -- silently fall back to the band exit if this master has none
    # (documented above; keeps the strategy usable on a volumeless master rather than
    # erroring out).
    if exit_mode == "vwap" and v is None:
        exit_mode = "band"

    allow_long  = side in ("Both", "Long Only")
    allow_short = side in ("Both", "Short Only")

    sess_bounds = _session_bounds(did, n)

    # Half-day / holiday skip (skip_holidays): identical helper to ORB_3_0/DRIVE_1_0 --
    # a session shorter than 70% of the MEDIAN session length is a half-day. OFF by
    # default = no change. The sigma estimate below still uses EVERY session's bars
    # (a half-day is real market data for the noise estimate) -- this flag only skips
    # TRADING it, same as ORB_3_0's convention.
    _holiday_start = set()
    if skip_holidays and len(sess_bounds) > 4:
        _lens = np.array([b - a for a, b in sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    sigma = _sigma_matrix(o, c, sess_bounds, lookback)

    # Protective stop (stop_mode != 'off') -- see DEFAULT_PARAMS tooltip + the
    # 2026-08-08 docstring block above for the researched/validated 'bandwidth'
    # case. ATR20d is only computed when stop_mode == 'atr' so this stays a
    # true no-op (byte-identical) whenever the default 'off' is untouched.
    stop_atr = _atr_by_session(h, l, sess_bounds, 20) if stop_mode == "atr" else None

    # 2026-08-17 filter knobs -- both computed ONLY when their knob is on, so the
    # defaults stay a true no-op (byte-identical; proven by smoke tests a/b below).
    confirm_bars = max(1, int(confirm_bars))
    vol_pct = _vol_percentile(h, l, c, sess_bounds) if vol_skip_pct > 0.0 else None
    dt_pos = _daytype_pos(h, l, c, sess_bounds) if daytype_mode != "off" else None

    pnl_list, trade_log = [], []
    prev_close = None
    for si, (a, b) in enumerate(sess_bounds):
        if _stop_event is not None and _stop_event.is_set():
            break
        m = b - a
        if a in _holiday_start:
            continue                                # skip trading AND state update, ORB-style
        if prev_close is None or si < lookback:
            prev_close = c[b - 1]
            continue

        so, sh, sl, sc = o[a:b], h[a:b], l[a:b], c[a:b]
        sv = v[a:b] if v is not None else None
        ref_hi = max(so[0], prev_close)
        ref_lo = min(so[0], prev_close)
        sigma_row = sigma[si, :]
        with np.errstate(invalid="ignore"):
            UB = ref_hi * (1.0 + band_mult_long * sigma_row[:m])
            LB = ref_lo * (1.0 - band_mult_short * sigma_row[:m])
        atr_pts = stop_atr[si] if stop_atr is not None else None

        # 2026-08-17 session-level entry gates (all causal, prior-session data only).
        sess_block_entries = False
        if vol_pct is not None and not np.isnan(vol_pct[si]) and vol_pct[si] >= vol_skip_pct:
            sess_block_entries = True
        block_long = block_short = False
        if dt_pos is not None and not np.isnan(dt_pos[si]):
            dp = dt_pos[si]
            if daytype_mode == "skip_bot_short" and dp <= daytype_lo:
                block_short = True
            elif daytype_mode == "skip_bot_all" and dp <= daytype_lo:
                block_long = block_short = True
            elif daytype_mode == "skip_top_long" and dp >= daytype_hi:
                block_long = True
            elif daytype_mode == "skip_top_all" and dp >= daytype_hi:
                block_long = block_short = True

        VWAP = None
        if exit_mode == "vwap" and sv is not None:
            typical = (sh + sl + sc) / 3.0
            cum_tpv = np.cumsum(typical * sv)
            cum_v = np.cumsum(sv)
            with np.errstate(invalid="ignore", divide="ignore"):
                VWAP = cum_tpv / cum_v

        pos = 0; entry_px = 0.0; entry_k = -1
        entry_pending = 0        # queued long(+1)/short(-1) entry, fills at THIS bar's open
        exit_pending = False     # queued exit, fills at THIS bar's open
        stop_level = None        # protective-stop price, set at entry (stop_mode != 'off')
        streak_long = streak_short = 0   # confirm_bars bookkeeping (2026-08-17)

        for k in range(m):
            is_last = (k == m - 1)

            # STEP A -- execute fills queued from the PREVIOUS bar's close signal.
            if exit_pending:
                ex_px = so[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                pnl_list.append(pnl)
                if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
                pos = 0; exit_pending = False
            if entry_pending != 0 and pos == 0:
                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0
                stop_level = None
                if stop_mode == "bandwidth":
                    band_val = UB[k] if pos > 0 else LB[k]
                    if not np.isnan(band_val):
                        stop_level = (entry_px - stop_k * (band_val - ref_hi)) if pos > 0 \
                            else (entry_px + stop_k * (ref_lo - band_val))
                elif stop_mode == "atr":
                    if atr_pts is not None and not np.isnan(atr_pts):
                        stop_level = (entry_px - stop_k * atr_pts) if pos > 0 \
                            else (entry_px + stop_k * atr_pts)
                elif stop_mode == "fixed":
                    P = stop_k * 100.0
                    stop_level = (entry_px - P) if pos > 0 else (entry_px + P)

            # STEP A2 -- protective stop (stop_mode != 'off'), checked intrabar EVERY
            # bar AFTER the entry bar (never on k == entry_k). Stop-first pessimism:
            # if this bar's OPEN already gapped through the level, fill at the open
            # (can't get the stop price); else if the bar's low/high touches the
            # level intrabar, fill AT the level. An early stop-out frees the position
            # to re-enter later in the same session -- STEP D below still runs this
            # same iteration once pos==0, same mechanism that already lets a vwap/
            # band exit be followed by a same-bar re-entry signal.
            if pos != 0 and k != entry_k and stop_level is not None and not np.isnan(stop_level):
                if pos > 0:
                    if so[k] < stop_level:
                        ex_px = so[k]
                        pnl_list.append(ex_px - entry_px)
                        if return_trades: trade_log.append((a + entry_k, a + k, ex_px - entry_px, 1, entry_px))
                        pos = 0
                    elif sl[k] <= stop_level:
                        ex_px = stop_level
                        pnl_list.append(ex_px - entry_px)
                        if return_trades: trade_log.append((a + entry_k, a + k, ex_px - entry_px, 1, entry_px))
                        pos = 0
                else:
                    if so[k] > stop_level:
                        ex_px = so[k]
                        pnl_list.append(entry_px - ex_px)
                        if return_trades: trade_log.append((a + entry_k, a + k, entry_px - ex_px, -1, entry_px))
                        pos = 0
                    elif sh[k] >= stop_level:
                        ex_px = stop_level
                        pnl_list.append(entry_px - ex_px)
                        if return_trades: trade_log.append((a + entry_k, a + k, entry_px - ex_px, -1, entry_px))
                        pos = 0

            # STEP B -- boundary-mode intrabar exit (checked while in a position).
            if pos != 0 and exit_mode == "boundary":
                if pos > 0:
                    band = UB[k]
                    if not np.isnan(band):
                        if so[k] < band:
                            pnl_list.append(so[k] - entry_px)
                            if return_trades: trade_log.append((a + entry_k, a + k, so[k] - entry_px, 1, entry_px))
                            pos = 0
                        elif sl[k] <= band:
                            pnl_list.append(band - entry_px)
                            if return_trades: trade_log.append((a + entry_k, a + k, band - entry_px, 1, entry_px))
                            pos = 0
                elif pos < 0:
                    band = LB[k]
                    if not np.isnan(band):
                        if so[k] > band:
                            pnl_list.append(entry_px - so[k])
                            if return_trades: trade_log.append((a + entry_k, a + k, entry_px - so[k], -1, entry_px))
                            pos = 0
                        elif sh[k] >= band:
                            pnl_list.append(entry_px - band)
                            if return_trades: trade_log.append((a + entry_k, a + k, entry_px - band, -1, entry_px))
                            pos = 0

            # STEP C -- vwap/band exit trigger evaluated at THIS bar's close.
            if pos != 0 and exit_mode in ("vwap", "band"):
                trig = False
                if exit_mode == "vwap" and VWAP is not None and not np.isnan(VWAP[k]):
                    if pos > 0 and sc[k] < VWAP[k]:
                        trig = True
                    elif pos < 0 and sc[k] > VWAP[k]:
                        trig = True
                elif exit_mode == "band":
                    if pos > 0 and not np.isnan(UB[k]) and sc[k] < UB[k]:
                        trig = True
                    elif pos < 0 and not np.isnan(LB[k]) and sc[k] > LB[k]:
                        trig = True
                if trig:
                    if is_last:
                        ex_px = sc[k]
                        pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                        pnl_list.append(pnl)
                        if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
                        pos = 0
                    else:
                        exit_pending = True

            # confirm_bars streak bookkeeping (2026-08-17): consecutive closes outside
            # each band, each bar's close judged against THAT bar's own band level --
            # finished-bar data only. Only maintained when the knob is active.
            if confirm_bars > 1:
                ub_s, lb_s = UB[k], LB[k]
                streak_long = streak_long + 1 if (not np.isnan(ub_s)) and sc[k] > ub_s else 0
                streak_short = streak_short + 1 if (not np.isnan(lb_s)) and sc[k] < lb_s else 0

            # STEP D -- new-entry signal at THIS bar's close (only if now flat).
            if pos == 0 and not is_last and 1 <= k <= m - 2 and not sess_block_entries:
                in_window = True
                if window == "morning":
                    in_window = (k <= 29)
                elif window == "afternoon_block":
                    in_window = (k <= m - 26)
                if in_window:
                    ub_k, lb_k = UB[k], LB[k]
                    long_trig = allow_long and not block_long and (not np.isnan(ub_k)) and (sc[k] > ub_k)
                    short_trig = allow_short and not block_short and (not np.isnan(lb_k)) and (sc[k] < lb_k)
                    if confirm_bars > 1:
                        long_trig = long_trig and streak_long >= confirm_bars
                        short_trig = short_trig and streak_short >= confirm_bars
                    if long_trig and short_trig:
                        entry_pending = 1 if (sc[k] - ub_k) >= (lb_k - sc[k]) else -1
                    elif long_trig:
                        entry_pending = 1
                    elif short_trig:
                        entry_pending = -1

            # STEP E -- EOD backstop: force flat at the session's last bar close.
            if is_last and pos != 0:
                ex_px = sc[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                pnl_list.append(pnl)
                if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
                pos = 0

        prev_close = sc[-1]

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — runs TWO configs on the NQ 5m RTH master through the real engine
# (source PINNED to db_noadj_rth, matching tools/noise_research.py):
#   (a) stop_mode='off'       -> must reproduce the frozen no-stop baseline exactly.
#   (b) stop_mode='bandwidth', stop_k=1.0 -> must reproduce the 2026-08-08
#       reviewer-audited protective-stop numbers (docstring block above).
#   Run:  python augur_strategies/NOISE_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from augur_engine.engine import run_backtest as eng_bt

    DATE_TO = "2025-06-29"        # matches tools/noise_research.py's checkpoint window
    FEE, MULT = 0.533, 20.0       # NQ costs: 0.533 pts/RT, $20/pt

    base_params = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                        exit_mode="vwap", side="Both", window="all_day",
                        flat_eod=True, skip_holidays=False)

    def _run(label, extra_params, expect_n, expect_net, expect_dd, expect_pf=None,
             dd_tol=1.0, date_to=None):
        params = dict(base_params, **extra_params)
        _dt = date_to or DATE_TO
        r = eng_bt("NOISE_1_0.py", instrument="NQ", timeframe="5m", session="rth",
                   source="db_noadj_rth", cost_pts=FEE, date_to=_dt, params=params)
        if r is None:
            print("  %-38s NO TRADES / no master found — check augur_uploads/ + optimizer_history.db" % label)
            return False
        n   = r["num_trades"]
        net = r["total_pnl"] * MULT
        pf  = r["profit_factor"]
        dd  = r["max_drawdown"] * MULT
        print("%s - NQ 5m RTH, source=db_noadj_rth (<= %s)" % (label, _dt))
        print("  params:   %s" % params)
        print("  got:      n=%d net=$%s PF=%.4f DD=$%s" % (n, format(net, ",.2f"), pf, format(dd, ",.2f")))
        exp_pf_str = ("PF=%.4f " % expect_pf) if expect_pf is not None else ""
        print("  expected: n=%d net=$%s %sDD=$%s" % (
            expect_n, format(expect_net, ",.2f"), exp_pf_str, format(expect_dd, ",.2f")))
        ok = (n == expect_n and abs(net - expect_net) < 1 and abs(dd - expect_dd) < dd_tol)
        if expect_pf is not None:
            ok = ok and abs(pf - expect_pf) < 0.01
        print("  SMOKE TEST (%s): %s" % (label, "PASS" if ok else "FAIL"))
        print()
        return ok

    ok_a = _run("(a) stop_mode='off' (no-stop baseline)", dict(stop_mode="off"),
                expect_n=3147, expect_net=254382.98, expect_dd=-31239.80, expect_pf=1.3110)

    ok_b = _run("(b) stop_mode='bandwidth', stop_k=1.0 (validated stop)",
                dict(stop_mode="bandwidth", stop_k=1.0),
                expect_n=3185, expect_net=268371.16, expect_dd=-21659.59, dd_tol=1.0)

    # (c)/(d) -- the 2026-08-17 filter research, parity-gated against
    # tools/noise_variant_research.py's reviewer numbers on the #231 selection
    # window (date_to=2025-02-10). Core = the #231 champion (44/0.75/1.5, vwap,
    # bandwidth k=1.75).
    champ = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                 stop_mode="bandwidth", stop_k=1.75)

    ok_c = _run("(c) champion + confirm_bars=2 + skip_bot_short (2026-08-17 winner)",
                dict(champ, confirm_bars=2, daytype_mode="skip_bot_short"),
                expect_n=4010, expect_net=332699.25, expect_dd=-14076.45,
                expect_pf=1.3992, date_to="2025-02-10")

    ok_d = _run("(d) champion + vol_skip_pct=90 (banked single)",
                dict(champ, vol_skip_pct=90.0),
                expect_n=4309, expect_net=310689.59, expect_dd=-19040.79,
                expect_pf=1.3749, date_to="2025-02-10")

    print("OVERALL: %s" % ("PASS" if (ok_a and ok_b and ok_c and ok_d) else "FAIL"))
    sys.exit(0 if (ok_a and ok_b and ok_c and ok_d) else 1)

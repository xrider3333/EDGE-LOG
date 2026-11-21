"""ENGU-Q 1m ETH VS -- the crown's signal, scored at CONSTANT DOLLAR RISK per trade.
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R2_1_0.py. Entries, exits, stops and trailing are the parent's, called
through it -- not one line of that logic is copied or changed here. The ONLY thing this file
does is decide HOW BIG each trade is, and it decides it from the trade's own initial stop
distance, which the parent already reports.

    size_i = vs_target_pts / risk_i,  clamped to [vs_min_u, vs_max_u]

`risk_i` is the parent's own `levels[i]["risk"]`: the distance from entry to the INITIAL stop,
fixed at the entry bar. Nothing after the entry bar enters the size, so there is no look-ahead.

WHY THIS FILE EXISTS. ENGU-Q trades a fixed 1 NQ, so a trade whose stop sits 6 points away
risks a sixth of what a 137-point-stop trade risks (the measured 5th/95th of `risk` over
2016-07..2025-06 is 6.0 / 136.9 points, median 34.2). The family's own anatomy says volatility
is one of only two things that separate its winners, so the fixed unit is spending most of its
drawdown on its widest-stop trades. Screened on the frozen crown over the walk-forward window
(cost 0.783, mult 20, lockbox unread):

                        net        $/yr      worst DD   DD % of $100k   net per $1 of DD
    base, fixed 1 NQ   $379,469   $42,179    $38,872        38.9             9.76
    this, vol-scaled   $203,513   $22,621    $15,317        15.3            13.29

Less money and a much shallower drawdown. Scaled so both reach the owner's 35% cap, the
vol-scaled arm is worth about $465k against the base's $342k -- roughly +36%. THAT COMPARISON
IS POST-HOC (it was computed after the screen, not pre-registered), so it is the hypothesis
this file exists to test, not a result. The pre-registered grade for the validate is written
down before it runs: equal-drawdown net against the base at the 35% cap, with the walk-forward
fold count and DD5 beside it.

WHAT THE SEARCH MAY AND MAY NOT MOVE. vs_target_pts is FIXED at 35 (min == max), one tick off
the measured median risk, so every trade risks the same dollars and the search cannot buy net
by levering up -- which is how the sibling idea A passed a net test while being worth 26% LESS
than the base at the same drawdown. The 14 entry/exit knobs keep the parent's ranges, so what
the search actually answers is "which ENGU-Q configuration is best when every trade risks the
same", not "how big should the trades be".

THE COST CONTRACT, and it is the one sharp edge in this file. The engine charges cost ONCE per
trade (augur_engine.engine._apply_costs subtracts cost_pts from each trade's points, flat, with
no notion of size). A size-scaled trade must therefore carry the extra (size - 1) charges
itself, so this file emits

    pnl_i = size_i * gross_i - (size_i - 1) * vs_cost_pts

and the engine's own single subtraction completes it to size_i * (gross_i - cost). That is only
correct when vs_cost_pts equals the cost the JOB runs at, so vs_cost_pts is a fixed knob set to
0.783 -- the registered ENGU-Q line on the adjusted master -- and a job at any other cost must
change it in the same breath. tests/test_enguq_vs_sizing.py pins this identity, including the
mismatch case, so a wrong cost shows up as a failing test rather than a quietly flattering run.

The 10-NQ BOOK CAP, up front: at the scale that brings this arm to a 35% drawdown its mean unit
is about 3.3 NQ and its clamp peak is 9.1 NQ. That is most of the book's 10-NQ cap before any
other NQ leg, so even a validated version may not fit beside #335. The cap question is the
book's, not this file's, and it is stated here so nobody re-derives it later.
"""
# AUGUR-SOURCE: claude-review
#   Written by the ENGUQ lane (Claude), reviewed by a second lane before it was shipped. The
#   marker is a real comment, not a line in the docstring, because plugin_gate's MARKER_RX only
#   matches a comment at the start of a line. `claude-review` is one of its HUMAN_SOURCES, so the
#   file is treated as hand-written and needs no REVIEWED.json stamp; the second-lane read is a
#   house rule, not something the gate can enforce, which is why it is recorded here.
import numpy as np

from augur_engine.strategies import load_strategy

STRATEGY_NAME = "ENGU-Q 1m ETH VS - crown signal, constant dollar risk"

_PARENT = "ENGUQ_1M_ETH_R2_1_0.py"
_VS_KEYS = ("vs_target_pts", "vs_min_u", "vs_max_u", "vs_cost_pts")

DEFAULT_PARAMS = {
    # ---- the parent's knobs, ranges unchanged (a search here explores the crown's own space)
    "er_len":      {"type": "int",   "min": 20,  "max": 120,  "step": 10,   "default": 100,
                    "label": "Efficiency lookback"},
    "er_th":       {"type": "float", "min": 0.0, "max": 0.5,  "step": 0.05, "default": 0.0,
                    "label": "Efficiency floor"},
    "limit_atr":   {"type": "float", "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.55,
                    "label": "Limit offset (ATR)"},
    "tl_len":      {"type": "int",   "min": 50,  "max": 300,  "step": 4,    "default": 206,
                    "label": "Trend lookback"},
    "vol_mult":    {"type": "float", "min": 0.0, "max": 5.0,  "step": 0.1,  "default": 1.1,
                    "label": "Volume spike multiple"},
    "stop_mult":   {"type": "float", "min": 0.8, "max": 1.4,  "step": 0.1,  "default": 1.0,
                    "label": "Stop distance (ATR)"},
    "act_R":       {"type": "float", "min": 0.0, "max": 3.0,  "step": 0.5,  "default": 1.5,
                    "label": "Trail arms at (R)"},
    "trail_frac":  {"type": "float", "min": 0.5, "max": 4.0,  "step": 0.5,  "default": 2.5,
                    "label": "Trail distance (ATR)"},
    "buf_atr":     {"type": "float", "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.3,
                    "label": "Level buffer (ATR)"},
    "min_brk":     {"type": "float", "min": 0.0, "max": 3.0,  "step": 0.1,  "default": 1.6,
                    "label": "Minimum break (ATR)"},
    "ema_len":     {"type": "int",   "min": 100, "max": 1600, "step": 40,   "default": 220,
                    "label": "Trend EMA"},
    "atr_len":     {"type": "int",   "min": 20,  "max": 180,  "step": 4,    "default": 52,
                    "label": "ATR lookback"},
    "regime_len":  {"type": "int",   "min": 0,   "max": 100,  "step": 5,    "default": 10,
                    "label": "Regime lookback"},
    "breakeven_R": {"type": "float", "min": 1.0, "max": 2.5,  "step": 0.5,  "default": 2.0,
                    "label": "Breakeven at (R)"},
    # ---- sizing: FIXED, deliberately not searchable (see the header)
    "vs_target_pts": {"type": "float", "min": 35.0, "max": 35.0, "step": 1.0, "default": 35.0,
                      "label": "Risk per trade (points)",
                      "tooltip": "Every trade is sized to risk this many points: size = this / "
                                 "the trade's own initial stop distance. FIXED so the search "
                                 "cannot raise net by levering up."},
    "vs_min_u":      {"type": "float", "min": 0.25, "max": 0.25, "step": 0.05, "default": 0.25,
                      "label": "Smallest unit",
                      "tooltip": "Size floor. A very wide stop would otherwise size to nearly "
                                 "nothing and drop the trade out of the book."},
    "vs_max_u":      {"type": "float", "min": 4.0, "max": 4.0, "step": 0.5, "default": 4.0,
                      "label": "Largest unit",
                      "tooltip": "Size cap. The inverse of a tiny stop is unbounded, and an "
                                 "unclamped size is a different strategy from this one."},
    "vs_cost_pts":   {"type": "float", "min": 0.783, "max": 0.783, "step": 0.001,
                      "default": 0.783, "label": "Cost per round trip (points)",
                      "tooltip": "MUST equal the cost the job runs at: the extra (size - 1) "
                                 "charges are applied here because the engine charges cost "
                                 "once per trade regardless of size."},
}

PARAM_GRID_PRESETS = {
    "Short - crown neighbourhood": {
        "breakeven_R": [1.5, 2.0, 2.5], "stop_mult": [0.9, 1.0, 1.1],
    },
    "Medium - crown neighbourhood + trail": {
        "breakeven_R": [1.5, 2.0, 2.5], "stop_mult": [0.9, 1.0, 1.1],
        "act_R": [1.0, 1.5, 2.0], "trail_frac": [2.0, 2.5, 3.0],
    },
    "Long - entry side too": {
        "breakeven_R": [1.5, 2.0, 2.5], "stop_mult": [0.9, 1.0, 1.1],
        "act_R": [1.0, 1.5, 2.0], "trail_frac": [2.0, 2.5, 3.0],
        "min_brk": [1.4, 1.6, 1.8], "buf_atr": [0.25, 0.3, 0.35],
    },
}


def trade_sizes(risks, target_pts, min_u, max_u):
    """One size per trade from its own initial stop distance, clamped.

    Split out so tests can read it without the engine: `risks` is the parent's per-trade
    `levels[i]["risk"]` in points. A missing or non-positive risk sizes to 1.0 rather than
    raising -- the parent reports one row per trade, and a trade whose ladder was dropped
    should keep trading at the base unit, not vanish or blow up.
    """
    r = np.asarray(risks, dtype=np.float64)
    bad = ~np.isfinite(r) | (r <= 0)
    s = np.where(bad, 1.0, float(target_pts) / np.where(bad, 1.0, r))
    return np.clip(s, float(min_u), float(max_u))


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 return_trades=False, _stop_event=None, _pause_event=None, **params):
    """The parent's walk, re-weighted trade by trade. Returns the parent's own dict shape.

    The parent is asked for levels (its per-trade stop ladder) because `risk` is the sizing
    input, and that forces its interpreted walk. The claim that matters is NOT the general
    compiled-vs-interpreted parity: test_fastloop_parity covers ENGU-Q's own shape but passes
    return_levels in none of its cases, so it says nothing about the levels path. What this file
    actually depends on is narrower -- asking for levels must not change which trades happen --
    and tests/test_enguq_vs_sizing.py pins exactly that, plus that every levels row carries a
    usable `risk` (without one, sizing would silently fall back to 1.0 and this file would be
    the base leg wearing a different name).
    """
    target = float(params.get("vs_target_pts", 35.0))
    min_u = float(params.get("vs_min_u", 0.25))
    max_u = float(params.get("vs_max_u", 4.0))
    cost = float(params.get("vs_cost_pts", 0.783))
    inner = {k: v for k, v in params.items() if k not in _VS_KEYS}

    mod = load_strategy(_PARENT)
    out = mod.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           return_trades=True, return_levels=True,
                           _stop_event=_stop_event, _pause_event=_pause_event, **inner)
    if not out or not out.get("trades"):
        return out

    trades = list(out["trades"])
    levels = list(out.get("levels") or [])
    risks = [((levels[i] or {}).get("risk") if i < len(levels) else None) for i in range(len(trades))]
    sizes = trade_sizes([(np.nan if r is None else r) for r in risks], target, min_u, max_u)

    # size * gross, minus the EXTRA (size - 1) cost charges the engine will not apply itself
    scaled = []
    for t, s in zip(trades, sizes):
        nt = list(t)
        nt[2] = float(s) * float(t[2]) - (float(s) - 1.0) * cost
        scaled.append(tuple(nt))

    p = np.array([t[2] for t in scaled], dtype=np.float64)
    wins = p[p > 0]
    losses = p[p < 0]
    cum = np.cumsum(p)
    res = dict(out)
    res.update({
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(p.size),
        "win_rate":      round(float(wins.size) / p.size * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(wins.size),
        "losses":        int(losses.size),
    })
    if return_trades:
        res["trades"] = scaled
        res["sizes"] = [float(s) for s in sizes]
    else:
        res.pop("trades", None)
        res.pop("levels", None)
    return res

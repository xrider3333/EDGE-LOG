"""
ORB 3.6 (C2, ride+BE) + SELF-ADJUSTING (PERCENTILE) EFFICIENCY FLOOR.

Why this file exists (2026-09-04): run #278 (ORB_3_4_ER_1_0.py) put a FIXED efficiency-
ratio floor on ORB and looked great on the bench (PF 1.263 -> 1.385), but the search
crowned a threshold so high it took ZERO trades in the held-out year -- a fixed cutoff
on a quantity whose distribution drifts over 16 years of regime change is not robust.

Fix: instead of a fixed er_th, gate on where the entry's efficiency ratio RANKS against
its own trailing history. `er_keep` = keep the entry only if the efficiency ratio on the
bar BEFORE entry is in the top `er_keep` fraction of ER values seen over the trailing
`er_win` bars (~1 year of 5m RTH bars). The floor rides with the regime instead of being
pinned to whatever the in-sample distribution happened to look like.

Efficiency ratio (Kaufman), on 5m closes, computed on the bar strictly BEFORE entry:
    ER[i] = |close[i] - close[i-er_len]| / sum_{j=i-er_len+1..i} |close[j] - close[j-1]|
Net move over path travelled -- 1.0 = pure trend, ~0 = pure chop.

Percentile floor, made causal and fast:
  * threshold sampled every 500 bars from a trailing er_win-bar window of ER values
    STRICTLY BEFORE the sample point, then HELD FORWARD until the next sample -- never
    reads ER values at or after the bar it gates.
  * before the first sample point (bar 500), there isn't a year of trailing ER history
    yet -> no filtering (same warm-up convention as ORB_3_6's atr_filter/vpace_filter).
  * er_keep=0.0 (default) -> gate OFF -> bit-exact parity with the #234 C2 champion.

Legality of the wrapper approach (same argument as ORB_3_4_ER_1_0.py): ORB takes at
most ONE trade per session (first signal, no re-entry) and is always flat by the close,
so dropping a session's trade on a feature known BEFORE that session's entry bar cannot
free a second entry to fire later that same session -- post-hoc filtering the finished
trade list is path-exact, not an approximation, for this family only.

PRE-REGISTERED BARS (tools/orb_erp_bench.py, written before running):
  1. full-window PF > parent PF (#234 C2, same window, same costs)
  2. the PF gain holds in >= 3 of 4 eras (2010-14, 14-18, 18-22, 22+)
  3. >= 40 trades in the held-out year (entries >= 2025-06-30) -- anti-starvation,
     the exact failure mode #278 had with a FIXED floor
  4. EV R AND R/YR both above the parent's (#234 C2: EV R ~0.18, R/YR ~29)
PRIMARY cell (declared before running): er_len=12, er_keep=0.60.
Bench grid: er_len in {6,12} x er_keep in {0.40,0.50,0.60,0.70} (8 cells) + control.

_AUGUR_PARENT = ORB_3_6_C2.py: entries + exits are C2's pinned config, unchanged. This
file's only addition is the percentile-ER post-filter on top of C2's finished trades.
"""
import numpy as np
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6_C2.py")
_spec = _ilu.spec_from_file_location("_orb36_c2_erp", _SRC)
_c2 = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_c2)

STRATEGY_NAME = "ORB 3.6 · #234 C2 + self-adjusting (percentile) efficiency floor"
DESCRIPTION = ("The #234 C2 champion (ride+BE, all knobs pinned) taking a session's "
               "trade only when the prior-bar Kaufman efficiency ratio ranks in the top "
               "er_keep fraction of its own trailing er_win-bar (~1yr) history -- a "
               "PERCENTILE floor that rides with the regime, replacing the fixed floor "
               "(#278) that starved to zero trades in the held-out year. er_keep=0 = off "
               "= exact #234 C2.")
VERSION = "1.0"
TIMEFRAME = "5m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_C2.py"

DEFAULT_PARAMS = dict(_c2.DEFAULT_PARAMS)
DEFAULT_PARAMS["er_keep"] = {
    "default": 0.0, "min": 0.30, "max": 0.80, "step": 0.05, "type": "float",
    "label": "Efficiency percentile keep-fraction (0 = off)",
    "tooltip": "Keep the entry only if the prior-bar Kaufman efficiency ratio is in the "
               "top er_keep fraction of ER values over the trailing er_win-bar window "
               "(sampled every 500 bars, held forward -- causal). 0 disables the gate "
               "(exact #234 C2 parity). Replaces a FIXED floor (which starved to 0 "
               "held-out trades) with one that adapts to the regime.",
}
DEFAULT_PARAMS["er_len"] = {
    "default": 12, "min": 6, "max": 24, "step": 2, "type": "int",
    "label": "Efficiency window (5m bars)",
    "tooltip": "Bars in the Kaufman efficiency ratio (net move / path travelled), "
               "computed on the bar before entry. 12 = one hour.",
}
DEFAULT_PARAMS["er_win"] = {
    "default": 20000, "min": 20000, "max": 20000, "step": 1000, "type": "int",
    "label": "Percentile trailing window (bars) — PINNED (~1yr of 5m RTH)",
    "tooltip": "Trailing window of ER values the keep-fraction threshold is computed "
               "over. Fixed, not searched.",
}

PARAM_GRID_PRESETS = {
    "Short (percentile ER scan on the #234 C2 champion)": {
        "er_len": [6, 12], "er_keep": [0.40, 0.50, 0.60, 0.70], "er_win": [20000],
    },
}

# The base engine (ORB_3_6.run_backtest, re-exported unchanged by ORB_3_6_C2) takes a
# FIXED keyword list, no **kw of its own. This wrapper has **kw -- augur_engine passes
# "extras" (e.g. index) to any strategy whose signature accepts **kw, so we must filter
# down to what the base actually accepts before forwarding (see ORB_3_4_ER_1_0.py for
# the TypeError this avoids). Read off the base's OWN signature, not a hand-kept list.
_BASE_SIG = _inspect.signature(_c2.run_backtest).parameters
_BASE_TAKES_KW = any(p.kind == p.VAR_KEYWORD for p in _BASE_SIG.values())


def _base_kw(kw):
    """Only the keywords the base engine can actually receive."""
    if _BASE_TAKES_KW:
        return kw
    return {k: v for k, v in kw.items() if k in _BASE_SIG}


def _efficiency_ratio(closes, L):
    """ER[i] = |close[i]-close[i-L]| / sum|close[j]-close[j-1]| over the last L bars
    ending at i. Vectorized; ER[i] for i<L is 0 (insufficient history -- same
    convention as ORB_3_4_ER_1_0.py)."""
    c = np.asarray(closes, float)
    chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
    ad = np.abs(np.diff(c, prepend=c[0]))
    cs = np.cumsum(ad)
    vs = cs - np.concatenate([np.zeros(L), cs[:-L]])
    er = np.nan_to_num(np.where(vs > 0, chg / np.maximum(vs, 1e-9), 0.0))
    return er


def _percentile_thresholds(er, er_keep, er_win, sample_every=500):
    """Causal, held-forward rolling-quantile threshold.

    At each sample point s (multiples of `sample_every`), the threshold is the
    (1-er_keep) quantile of ER values in the trailing window [max(0,s-er_win), s) --
    STRICTLY before s. That threshold is held forward for every bar until the next
    sample point. Returns (sample_points, thresholds) -- sample_points[k] is the first
    bar index the threshold thresholds[k] applies to; bars before sample_points[0] get
    no threshold (warm-up -> caller does not filter them).
    """
    n = len(er)
    q = 1.0 - float(er_keep)
    sample_points, thresholds = [], []
    s = sample_every
    while s < n:
        lo = max(0, s - er_win)
        window = er[lo:s]
        if window.size:
            thresholds.append(float(np.quantile(window, q)))
            sample_points.append(s)
        s += sample_every
    return sample_points, thresholds


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 er_keep: float = 0.0, er_len: int = 12, er_win: int = 20000,
                 return_trades: bool = False, **kw):
    res = _c2.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           return_trades=True, **_base_kw(kw))
    if res is None:
        return None
    trades = res["trades"]
    if float(er_keep) > 0 and trades:
        c = np.asarray(closes, float)
        L = int(er_len)
        W = int(er_win)
        er = _efficiency_ratio(c, L)
        sample_points, thresholds = _percentile_thresholds(er, er_keep, W)
        if sample_points:
            sp = np.asarray(sample_points)
            kept = []
            for t in trades:
                eidx = int(t[0])
                before = eidx - 1
                if before < 0 or before < sample_points[0]:
                    kept.append(t)  # warm-up: no year of trailing ER history yet -> allow
                    continue
                # last sample point <= `before` -> the held-forward threshold in force
                pos = np.searchsorted(sp, before, side="right") - 1
                thr = thresholds[pos]
                if er[before] >= thr:
                    kept.append(t)
            trades = kept
    pnls = np.array([t[2] for t in trades], float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum) if len(cum) else np.array([])
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()) if len(pnls) else 0.0,
        "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trades
    return out

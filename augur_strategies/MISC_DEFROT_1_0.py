"""MISC DEFROT 1.0 - midday defensive-vs-cyclical sector residual sets NQ's afternoon direction.

# AUGUR-SOURCE: claude-review

Provenance: OPUS-HUNT futures, strategy 107 cell 107a (DEFROT-NOON r1,
C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S107: PREREG.md, RESULTS.md, s107_build.py,
s107_eval.py; side panel built by s107_panel.py, parity by s107_parity.py). The hunt judged it
FAIL (Route A missed: EVAL-A net t 0.91; Route B book add missed on P 0.779 and folds 5/8;
profit concentrated in 2020 and 2022). NOT A BLIND READ for 2016-07..2025-06: that stretch was
judged once by the hunt. This file exists so the engine's Auto-Validate can judge it, with the
2025-07..2026-06 lockbox never read by the hunt.

-- The rule (defaults = cell 107a) ---------------------------------------------------------
Each eligible session, at the signal time S (default 12:00:00 ET):
  * r_f = ln(close of the fund's bar starting S-5min / open of its bar starting 09:30), per fund;
  * ROT = mean(r over the DEFENSIVE basket) - mean(r over the CYCLICAL basket);
      basket 0 (registered): XLU XLP XLV  vs  XLY XLK XLI XLF
      basket 1:              XLU XLP XLV  vs  XLY XLK XLI XLF XLE XLB
      basket 2:              XLU XLP      vs  XLY XLK
      basket 3:              XLU XLP XLV  vs  XLY XLK
  * OLS ROT_j = a + b r_SPY_j over the `win` eligible sessions STRICTLY BEFORE today;
    e = ROT - a - b r_SPY; s = SD of the fitted window residuals (ddof 2); z = e / s.
  * z >= +z_thr -> SHORT 1 NQ; z <= -z_thr -> LONG 1 NQ (`sides`: 0 both, 1 short only,
    2 long only).
Entry = OPEN of the NQ bar starting S. Exit = OPEN of the NQ bar starting `exit_min` (minute of
day ET); exit_min 960 (default) = CLOSE of the NQ bar starting 15:55. No stop, no target, one
trade a session at most, never overnight.

ELIGIBLE SESSION (the fit window counts only these): a full NYSE session - some panel fund has a bar
starting at or after 13:00 ET, which separates the scheduled early closes (last bar 12:55; known before
the open from the NYSE calendar) from a data-vendor hole late in a full day (2019-08-12: every fund
stops at 15:25-15:30, NQ trades the full day, the hunt kept it) - and SPY plus every basket fund has
a bar starting exactly 09:30 and exactly S-5min. No forward fill, no substitution. A trade further
needs the NQ bars at S and at the exit in the job's bars.

INFORMATION TIMES: every ETF input is the close of a bar that ENDS at S, i.e. final at the entry
open. The fit uses sessions strictly before today (rolling sums shifted one session). NQ prices
enter only as the fill. The NQ master is the clock and the fill; the signal never reads NQ.

-- Data ---------------------------------------------------------------------------------------
ETF prices come from the pinned side panel (prices only, alpaca_split_rth 5m RTH, SPY + 9 SPDRs,
2016-01-04..2026-06-30, built causally from the masters on disk by s107_panel.py):
    C:/EdgeLog/alpaca_cache/defrot_panel/defrot_panel_v1.npz
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
The first z needs `win` eligible sessions after 2016-01-04 (default: 2016-03-31).

-- Costs --------------------------------------------------------------------------------------
PnL is NQ points in the trade tuple; the job charges the house round trip (cost_pts 0.533, mult 20).

-- Auto-Validate ranges -----------------------------------------------------------------------
sig_min 11:00..13:00 (5) x z_thr 0.5..2.0 (7) x win 40..120 (5) x basket 0..3 (4) x exit_min
14:00..16:00 (5) x sides 0..2 (3) = 10,500 grid points.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC DEFROT 1.0 · midday defensive-vs-cyclical sector residual -> NQ afternoon (12:00 -> close)'
DESCRIPTION = ("At 12:00 ET, if defensive sector ETFs (XLU XLP XLV) have beaten cyclicals (XLY XLK XLI XLF) since "
               "the open by more than their trailing SPY beta explains (z >= 1), short NQ to the close; if cyclicals "
               "lead by as much, buy NQ. ETF prices come from a pinned side panel; the NQ master is the clock and fill.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_adj_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/defrot_panel/defrot_panel_v1.npz"
PANEL_SHA256 = "b49482c3a647c4ed3c9b960abf4889c38941d8359aa002641a12fb3690a4595e"

DEFAULT_PARAMS = {
    "sig_min": {"hard_min": 600, "default": 720, "min": 660, "max": 780, "step": 30, "type": "int",
                "label": "Signal / entry time (minute of day ET)",
                "tooltip": "720 = 12:00. ETF moves are measured 09:30 open -> this time; NQ is entered at the open of the bar starting here."},
    "z_thr": {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
              "label": "Residual z threshold",
              "tooltip": "Trade when the defensive-minus-cyclical residual is at least this many SDs from its SPY fit."},
    "win": {"hard_min": 20, "default": 60, "min": 40, "max": 120, "step": 20, "type": "int",
            "label": "Fit window (eligible sessions)",
            "tooltip": "Rolling OLS of the rotation on SPY over this many eligible sessions, ending the session before."},
    "basket": {"default": 0, "min": 0, "max": 3, "step": 1, "type": "int",
               "label": "Basket definition",
               "tooltip": "0 XLU XLP XLV vs XLY XLK XLI XLF (registered); 1 adds XLE XLB to cyclicals; 2 XLU XLP vs XLY XLK; 3 XLU XLP XLV vs XLY XLK."},
    "exit_min": {"hard_min": 810, "default": 960, "min": 840, "max": 960, "step": 30, "type": "int",
                 "label": "Exit time (minute of day ET)",
                 "tooltip": "Exit at the open of the NQ bar starting here; 960 = the 16:00 close (close of the 15:55 bar)."},
    "sides": {"default": 0, "min": 0, "max": 2, "step": 1, "type": "int",
              "label": "Sides (0 both, 1 short only, 2 long only)",
              "tooltip": "Which side of the signal trades."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 107a)": {"sig_min": [720], "z_thr": [1.0], "win": [60], "basket": [0],
                                    "exit_min": [960], "sides": [0]},
    "Medium (neighbours)": {"sig_min": [690, 720, 750], "z_thr": [0.75, 1.0, 1.25, 1.5], "win": [40, 60, 80],
                            "basket": [0, 1, 2, 3], "exit_min": [840, 900, 960], "sides": [0, 1, 2]},
}

PNL_UNITS = "points"

_OPEN_MIN = 570      # 09:30 ET
_LAST_MIN = 955      # 15:55 ET, the last RTH bar
_FULL_MIN = 780      # a fund bar starting >= 13:00 ET exists = not a scheduled NYSE early close (last bar 12:55)
_DEF = {0: ("XLU", "XLP", "XLV"), 1: ("XLU", "XLP", "XLV"), 2: ("XLU", "XLP"), 3: ("XLU", "XLP", "XLV")}
_CYC = {0: ("XLY", "XLK", "XLI", "XLF"), 1: ("XLY", "XLK", "XLI", "XLF", "XLE", "XLB"), 2: ("XLY", "XLK"),
        3: ("XLY", "XLK")}

_CACHE = {}          # per-process: the panel and the z series by (sig_min, basket, win)


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_DEFROT_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        names = [str(x) for x in z["names"]]
        p = {"dates": z["dates"].astype("int64"), "col": {n: i for i, n in enumerate(names)},
             "o930": z["o930"].astype("float64"), "cl": z["cl"], "last": z["last"].astype("int64")}
    _CACHE["panel"] = p
    return p


def _zmap(p, sig_min, basket, win):
    """{yyyymmdd: z} over the eligible sessions that have a full fit window before them."""
    key = ("z", int(sig_min), int(basket), int(win))
    if key in _CACHE:
        return _CACHE[key]
    col = p["col"]; k = (int(sig_min) - 5 - _OPEN_MIN) // 5
    dfn = [col[n] for n in _DEF[int(basket)]]; cyn = [col[n] for n in _CYC[int(basket)]]
    use = [col["SPY"]] + dfn + cyn
    o = p["o930"]; c = p["cl"][:, k, :].astype("float64")
    ok = (p["last"].max(1) >= _FULL_MIN) & np.isfinite(o[:, use]).all(1) & np.isfinite(c[:, use]).all(1)
    dates = p["dates"][ok]
    r = np.log(c[ok] / o[ok])
    y = r[:, dfn].mean(1) - r[:, cyn].mean(1)
    x = r[:, col["SPY"]]
    w = int(win)
    s = pd.DataFrame({"x": x, "y": y, "xx": x * x, "yy": y * y, "xy": x * y})
    m = s.rolling(w, min_periods=w).sum().shift(1)          # sessions t-w .. t-1 only
    sxx = m.xx - m.x ** 2 / w; syy = m.yy - m.y ** 2 / w; sxy = m.xy - m.x * m.y / w
    b = sxy / sxx; a = (m.y - b * m.x) / w
    ssr = (syy - b * sxy).clip(lower=0.0)
    sd = np.sqrt(ssr / (w - 2))
    zz = ((s.y - a - b * s.x) / sd).to_numpy()
    good = np.isfinite(zz)
    out = dict(zip(dates[good].tolist(), zz[good].tolist()))
    _CACHE[key] = out
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 sig_min: int = 720, z_thr: float = 1.0, win: int = 60, basket: int = 0,
                 exit_min: int = 960, sides: int = 0,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if int(basket) not in _DEF or int(exit_min) <= int(sig_min) or (int(sig_min) - _OPEN_MIN) % 5:
        return None
    p = _panel()
    if p is None:
        return None
    zm = _zmap(p, sig_min, basket, win)
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [n]])
    thr = float(z_thr); sd_ok = int(sides)
    at_close = int(exit_min) >= 960
    xm = _LAST_MIN if at_close else int(exit_min)
    trades = []
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        zv = zm.get(int(date[a]))
        if zv is None:
            continue
        side = -1 if zv >= thr else (1 if zv <= -thr else 0)
        if side == 0 or (sd_ok == 1 and side > 0) or (sd_ok == 2 and side < 0):
            continue
        m = minute[a:b]
        e = np.flatnonzero(m == int(sig_min)); x = np.flatnonzero(m == xm)
        if len(e) == 0 or len(x) == 0:
            continue
        eb = a + int(e[0]); xb = a + int(x[0])
        ep = float(o[eb]); xp = float(c[xb]) if at_close else float(o[xb])
        trades.append((eb, xb, float(side * (xp - ep)), side, ep, xp))
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; ls = p[p < 0]
    gw = float(w.sum()); gl = float(-ls.sum())
    cum = np.cumsum(p); peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float(min(0.0, (cum - peak).min())),
           "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Every trade enters at the signal time and leaves the same session: none is held through a close."""
    return [[] for _ in (trades or [])]

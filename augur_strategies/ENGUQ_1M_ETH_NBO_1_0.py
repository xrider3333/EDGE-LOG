"""ENGU-Q 1m ETH · NEXT-BAR-OPEN entry-realism variant (research, battery E).
-----------------------------------------------------------------------------
ETH analogue of ENGUQ_1M_RT_1_0.py's entry_mode=1 (next-bar-open). Same descending-
trendline-break engine and SAME #226-config pinned single-valued params as
ENGUQ_1M_ETH_FROZEN_1_0.py (the ETH parity anchor: tl_len 170 · vol_mult 0.8 ·
stop_mult 1.0 · act_R 2.5 · trail_frac 2.5 · buf_atr 0.9 · min_brk 1.3 · ema_len 1380 ·
atr_len 106 · regime_len 0 (off) · breakeven_R 1.5). The ONLY change from the FROZEN
engine is WHERE the fill happens relative to the signal bar:

  PARENT (FROZEN, entry_mode=0 equivalent) — fill at the signal bar's own close.
  THIS FILE (NBO)                          — fill at the OPEN of the bar AFTER the
                                              signal bar (no same-bar-close assumption).
                                              Same swing-low-derived risk/stop as the
                                              parent (computed off the signal bar's
                                              close and swing low, exactly like RT
                                              mode 1); management starts the bar AFTER
                                              the fill bar (`i += 2` from the signal
                                              bar, mirroring RT mode 1's convention).

Leak-free by construction: nothing after the fill bar is used to decide whether or
where to fill. If the signal bar is the last bar in the array (no next bar to fill
on), no trade is taken for that signal.

Trading logic besides the fill mechanic (EMA trend filter, regime gate, volume spike,
descending-trendline fit/break, ATR buffer/decisiveness, trailing stop, breakeven) is
copied unchanged from ENGUQ_1M_ETH_1_0.py / ENGUQ_1M_ETH_FROZEN_1_0.py's run_backtest.

Created 2026-08-17 for battery E (ETH+NBO paper-readiness check): the RTH engine was
shown to tolerate next-bar-open entry at ~+1.87% net cost (basically free realism);
this file checks whether the same NBO fill survives on the ETH engine. See
ENGUQ_1M_RT_1_0.py for the RTH sibling and its RETEST-entry modes (not mirrored here —
this file only carries the NBO mechanic, no entry_mode parameter).
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH · next-bar-open (research, battery E)"
DESCRIPTION = ("ETH analogue of ENGUQ_1M_RT_1_0.py's entry_mode=1: same #226 ETH-pinned "
              "config as ENGUQ_1M_ETH_FROZEN_1_0.py, fill moved from the signal bar's own "
              "close to the OPEN of the bar after the signal (paper-safest fill). All "
              "other params pinned single-valued; no search space.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

# ── pinned #226 ETH transfer config (single-valued; identical to ENGUQ_1M_ETH_FROZEN_1_0.py) ──
_PINNED = dict(tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
              buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
              breakeven_R=1.5)

DEFAULT_PARAMS = {
    "tl_len":      {"default": _PINNED["tl_len"],      "min": _PINNED["tl_len"],      "max": _PINNED["tl_len"],      "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": _PINNED["vol_mult"],    "min": _PINNED["vol_mult"],    "max": _PINNED["vol_mult"],    "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": _PINNED["stop_mult"],   "min": _PINNED["stop_mult"],   "max": _PINNED["stop_mult"],   "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": _PINNED["act_R"],       "min": _PINNED["act_R"],       "max": _PINNED["act_R"],       "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": _PINNED["trail_frac"],  "min": _PINNED["trail_frac"],  "max": _PINNED["trail_frac"],  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":     {"default": _PINNED["buf_atr"],     "min": _PINNED["buf_atr"],     "max": _PINNED["buf_atr"],     "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": _PINNED["min_brk"],     "min": _PINNED["min_brk"],     "max": _PINNED["min_brk"],     "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": _PINNED["ema_len"],     "min": _PINNED["ema_len"],     "max": _PINNED["ema_len"],     "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": _PINNED["atr_len"],     "min": _PINNED["atr_len"],     "max": _PINNED["atr_len"],     "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": _PINNED["regime_len"],  "min": _PINNED["regime_len"],  "max": _PINNED["regime_len"],  "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": _PINNED["breakeven_R"], "min": _PINNED["breakeven_R"], "max": _PINNED["breakeven_R"], "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
}

PARAM_GRID_PRESETS = {
    "PINNED - ETH #226 NBO": {
        "tl_len":      [170], "vol_mult":    [0.8], "stop_mult":   [1.0],
        "act_R":       [2.5], "trail_frac":  [2.5], "buf_atr":     [0.9],
        "min_brk":     [1.3], "ema_len":     [1380], "atr_len":    [106],
        "regime_len":  [0],   "breakeven_R": [1.5],
    }
}

_RISK_FLOOR = 0.5  # matches parent's max(0.25, 0.5)


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
                 buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, regime_len=0,
                 breakeven_R=1.5,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)

    ema = _ema(c, int(ema_len))
    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb

    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); al = int(atr_len)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)

    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        vv = np.asarray(volumes, float)
        vavg = np.full(n, np.nan); w = 20
        vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()

    pnl_list, trade_log = [], []
    pos = None
    i = tl_len + 1
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break

        if pos is not None:
            if h[i] - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades:
                    trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
            i += 1
            continue

        # ── signal detection (identical filters to ENGUQ_1M_ETH_1_0.py, on bar i) ──
        if c[i] <= o[i] or not c[i] > ema[i]:
            i += 1; continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):
            i += 1; continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            i += 1; continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            i += 1; continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            i += 1; continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()

        # ── NEXT-BAR-OPEN fill (the only mechanic that differs from the FROZEN parent) ──
        if i + 1 >= n:
            i += 1; continue  # no next bar to fill on -> no trade
        risk = c[i] - swing_low
        if risk < _RISK_FLOOR:
            i += 1; continue
        ep = o[i + 1]
        pos = {"bar": i + 1, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}
        i += 2  # management starts the bar AFTER the fill bar (parent convention)
        continue

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades:
            trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"]))

    if not pnl_list:
        return None
    p = np.array(pnl_list); wins = p[p > 0]; losses = p[p < 0]
    cum = np.cumsum(p)
    out = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out

"""
ENGU-Q 1m ETH — NIGHT-TRAIL-OFF research variant of the certified 24h config (#226).

Battery-B hypothesis: exits taken between 18:00 and 09:29 ET account for a net -21% drag
on #226's (ENGUQ_1M_ETH_FROZEN_1_0.py) PnL -- overnight trail whipsaws (the trail stops
the trade out at night, price re-rallies before the ETH-morning bars). Time-of-day is
known in advance for every bar, so gating on it is leak-free by construction.

Adds ONE new param, `night_mode` (int 0/1/2), on top of the 11 params of #226 (all 11
PINNED to the frozen config below -- this file is single-purpose, not a general search):
  0 = OFF. Byte-identical to ENGUQ_1M_ETH_1_0.py's run_backtest (the parent engine) --
      this is the parity anchor: with night_mode=0 this file must reproduce the exact
      #226 numbers (n=2843, net=$434,721.12 on NQ 1m ETH db_noadj_eth <=2026-06-30,
      cost (pnl_pts-0.533)x20).
  1 = NIGHT-TRAIL-OFF. During bars whose ET time-of-day is >=18:00 or <09:30, the
      TRAILING-stop component (act_R activation + the trail ratchet) is not evaluated --
      no ratchet ticks, no trail-triggered exit that bar. The INITIAL stop and the
      breakeven-ratcheted stop level (breakeven_R) stay fully live every bar, day or
      night, so the hard floor is never removed. Because the ratchet is monotonic
      (`sl = max(sl, ...)`) simply skipping the update at night and resuming the same
      max() at the next live bar means the trail "resumes from its last ratcheted level"
      automatically -- it can never loosen.
  2 = Same suspension as mode 1, but ONLY while the trade has not yet closed at
      +1R unrealized (measured on bar CLOSES, `close - entry >= 1.0 * risk`). Once a
      trade has closed at >=+1R even once, the trail stays active around the clock for
      the rest of that trade's life (the "reached_1R" flag is sticky per-position).

Everything else -- entry logic, ATR/EMA/trendline math, stop math, cost convention -- is
an EXACT, unedited copy of ENGUQ_1M_ETH_1_0.py's run_backtest. This file only adds the
night_mode gate around the trail block and pins the other 11 params to the #226 config.

Created 2026-08-17 for local research battery B (LOCAL ONLY -- no Firestore job enqueued
by this driver; the supervisor session decides adoption from the printed comparison).
"""
import numpy as np

STRATEGY_NAME = "ENGU-Q 1m ETH NIGHT-TRAIL-OFF 1.0"
DESCRIPTION = ("Research variant of the certified 24h ENGU-Q ETH config (#226): suspends "
               "the TRAILING stop (not the initial/breakeven floor) during 18:00-09:29 ET "
               "bars, to test whether overnight trail whipsaw is a net drag. night_mode "
               "0=off (parity anchor, byte-identical to #226) / 1=suspend overnight / "
               "2=suspend overnight only before the trade has closed at +1R. All other "
               "params PINNED to the frozen #226 config.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_1_0.py"

# PINNED: the 11 parent params are nailed to the frozen #226 config (identical to
#   ENGUQ_1M_ETH_FROZEN_1_0.py's DEFAULT_PARAMS). night_mode is the ONLY searchable knob.
DEFAULT_PARAMS = {
    "tl_len":      {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
    "night_mode":  {"default": 0,    "min": 0,    "max": 2,    "step": 1,   "type": "int",   "label": "Night Trail Suspension (0 off / 1 always / 2 until +1R)"},
}

PARAM_GRID_PRESETS = {
    "night_mode sweep (0/1/2, others pinned to #226)": {
        "tl_len":      [170],
        "vol_mult":    [0.8],
        "stop_mult":   [1.0],
        "act_R":       [2.5],
        "trail_frac":  [2.5],
        "buf_atr":     [0.9],
        "min_brk":     [1.3],
        "ema_len":     [1380],
        "atr_len":     [106],
        "regime_len":  [0],
        "breakeven_R": [1.5],
        "night_mode":  [0, 1, 2],
    }
}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, night_mode=0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    night_mode = int(night_mode)
    ema = _ema(c, int(ema_len))
    # optional longer-term REGIME gate: close must be above its N-day simple average
    #   (390 RTH bars/day). 0 = off. Long lengths skip bears/chop; short lengths whipsaw.
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

    # Night-window flags (ET time-of-day, known in advance -> leak-free). Only computed
    # when night_mode is actually on and an index was handed in; night_mode=0 never
    # touches this, keeping that path byte-identical to the parent engine.
    night = None
    if night_mode in (1, 2) and index is not None and len(index) == n:
        hh = np.asarray(index.hour)
        mm = np.asarray(index.minute)
        night = (hh >= 18) | (hh < 9) | ((hh == 9) & (mm < 30))

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl_list, trade_log = [], []
    pos = None
    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        if pos is not None:
            suppress_trail = False
            if night is not None and night[i]:
                if night_mode == 1:
                    suppress_trail = True
                elif night_mode == 2 and not pos.get("reached_1R", False):
                    suppress_trail = True
            if not suppress_trail:
                if h[i] - pos["ep"] >= act_R * pos["risk"]:
                    pos["act"] = True
                if pos["act"]:
                    pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if night_mode == 2 and not pos.get("reached_1R", False):
                if (c[i] - pos["ep"]) >= 1.0 * pos["risk"]:
                    pos["reached_1R"] = True
            if l[i] <= pos["sl"]:
                # gap-through realism: if the bar OPENED beyond the stop, the fill is the
                # open (can't be filled at a stop price the market never traded through
                # cleanly) — not the exact stop price. ORB 3.0 models the same.
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
            continue
        if c[i] <= o[i] or not c[i] > ema[i]:
            continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):   # regime gate
            continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            continue
        swing_low = l[i - tl_len:i + 1].min()
        risk = c[i] - swing_low
        if risk < max(0.25, 0.5):
            continue
        ep = c[i]
        pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False,
               "reached_1R": False}

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"]))
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

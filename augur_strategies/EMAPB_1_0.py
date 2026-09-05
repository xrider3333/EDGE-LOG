"""
EMAPB 1.0 — 1-minute EMA-pullback CONTINUATION with the house risk engine (NQ RTH, both sides).

Why this exists (owner 2026-09-04: rank on EV R and R / YR — frequency with a kept edge):
the two validated house edges are continuation entries with tight initial risk on a
1-minute tape (ENGU-Q) and at the open (ORB). Every fade tested here has died. This is
the simplest continuation family not yet in the library: trade WITH the fast/slow EMA
regime, enter on the close-confirmed resumption after a pullback to the fast EMA, risk
the pullback swing, breakeven at be_R, then trail behind the fast EMA. Several entries
per session are allowed, so it can trade far more often than ORB.

Mechanics (long side; shorts are the mirror):
  regime  : EMA(ema_fast) > EMA(ema_slow) of 1m closes
  pullback: a bar whose LOW <= EMA(ema_fast) (the most recent such bar is "the pullback";
            its low is the swing low, its high the trigger level)
  trigger : first later bar that CLOSES above the pullback bar's high, while still in
            regime and inside the entry window -> enter at the NEXT bar's OPEN
  stop    : entry - stop_mult x (entry - pullback low); risk must be > 0
  BE      : a bar CLOSES >= entry + be_R x risk -> stop moves to entry on the NEXT bar
  trail   : after BE, stop = max(stop, EMA_fast - trail_atr x ATR14) evaluated on the
            close, acted on the next bar (ratchet only)
  fills   : gap-honest (a bar opening through the stop fills at its open); flat at the
            session's last bar close; entry window minute_from..minute_to ET;
            max_trades_per_day; cooldown_bars after any exit
PnL in POINTS per contract, costs applied downstream (cost_pts 0.533 NQ RTH).
Needs day_id and index. The pure-Python loop is lean (all indicators vectorized).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'EMAPB 1.0 · 1m EMA-pullback continuation, house risk engine'
DESCRIPTION = ("Trade with the fast/slow EMA regime on 1-minute bars: after a pullback to the fast "
               "EMA, enter on the close-confirmed resumption, risk the pullback swing, breakeven, "
               "trail the fast EMA. Several trades per session. Flat by the close.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}

DEFAULT_PARAMS = {
    "ema_fast": {"default": 20, "min": 10, "max": 40, "step": 10, "type": "int", "label": "Fast EMA (bars)"},
    "ema_slow": {"default": 100, "min": 50, "max": 200, "step": 50, "type": "int", "label": "Slow EMA (bars)"},
    "stop_mult": {"default": 1.0, "min": 0.75, "max": 1.5, "step": 0.25, "type": "float", "label": "Stop (x pullback swing)"},
    "be_R": {"default": 1.0, "min": 0.5, "max": 1.5, "step": 0.5, "type": "float", "label": "Breakeven at (R)"},
    "trail_atr": {"default": 1.0, "min": 0.5, "max": 1.5, "step": 0.5, "type": "float", "label": "Trail below fast EMA (x ATR14)"},
    "max_trades_per_day": {"default": 6, "min": 3, "max": 10, "step": 1, "type": "int", "label": "Max trades per day"},
    "cooldown_bars": {"default": 5, "min": 0, "max": 20, "step": 5, "type": "int", "label": "Cooldown after exit (bars)"},
    "minute_from": {"default": 575, "min": 575, "max": 575, "step": 1, "type": "int", "label": "Entry window start (min of day, 575=09:35)"},
    "minute_to": {"default": 930, "min": 930, "max": 930, "step": 1, "type": "int", "label": "Entry window end (930=15:30)"},
}

PARAM_GRID_PRESETS = {
    "Short  (defaults)": {"ema_fast": [20], "ema_slow": [100], "stop_mult": [1.0], "be_R": [1.0], "trail_atr": [1.0]},
    "Medium (pre-registered 27)": {"ema_fast": [10, 20, 40], "ema_slow": [50, 100, 200], "stop_mult": [0.75, 1.0, 1.5],
                                   "be_R": [1.0], "trail_atr": [1.0]},
}


def _ema(x, L):
    a = 2.0 / (L + 1.0)
    out = np.empty_like(x); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def run_backtest(
    opens, highs, lows, closes, volumes=None, day_id=None, index=None,
    ema_fast: int = 20, ema_slow: int = 100, stop_mult: float = 1.0, be_R: float = 1.0,
    trail_atr: float = 1.0, max_trades_per_day: int = 6, cooldown_bars: int = 5,
    minute_from: int = 575, minute_to: int = 930,
    return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 500 or day_id is None or index is None or len(day_id) != n:
        return None
    did = np.asarray(day_id)
    idx = pd.DatetimeIndex(index)
    mins = (idx.hour * 60 + idx.minute).values
    ef = _ema(c, int(ema_fast)); es = _ema(c, int(ema_slow))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))); tr[0] = h[0] - l[0]
    atr = _ema(tr, 14)
    last_bar = np.zeros(n, bool)
    last_bar[-1] = True
    last_bar[:-1] = did[1:] != did[:-1]

    pnl_list = []; trade_log = []
    side = 0; entry = 0.0; stop = 0.0; risk = 0.0; be_done = False; be_next = False; pend_stop = None
    pb_hi = pb_lo = None; pb_side = 0
    day_trades = 0; cur_day = -1; cooldown = 0; ei = -1
    pending = 0   # +1/-1 -> enter at this bar's open
    for i in range(1, n):
        if _stop_event is not None and (i & 65535) == 0 and _stop_event.is_set():
            return None
        if did[i] != cur_day:
            cur_day = did[i]; day_trades = 0; pb_hi = pb_lo = None; pb_side = 0
            pending = 0
        # ---- fills at this bar's open ----
        if pending != 0 and side == 0:
            side = pending; pending = 0; entry = o[i]; ei = i
            stop = entry - side * risk; be_done = False; be_next = False; pend_stop = None
            day_trades += 1
        if side != 0:
            if pend_stop is not None:
                stop = pend_stop if side == 1 and pend_stop > stop else (pend_stop if side == -1 and pend_stop < stop else stop)
                pend_stop = None
            ex = None
            if side == 1:
                if o[i] <= stop: ex = o[i]
                elif l[i] <= stop: ex = stop
            else:
                if o[i] >= stop: ex = o[i]
                elif h[i] >= stop: ex = stop
            if ex is None and last_bar[i]:
                ex = c[i]
            if ex is not None:
                pnl = side * (ex - entry)
                pnl_list.append(pnl)
                if return_trades:
                    trade_log.append((int(ei), int(i), float(pnl), int(side), float(entry), float(ex)))
                side = 0; cooldown = int(cooldown_bars)
            else:
                # manage on the close: BE then trail, acted next bar
                if not be_done and side * (c[i] - entry) >= be_R * risk:
                    be_done = True; pend_stop = entry
                elif be_done:
                    t = ef[i] - side * trail_atr * atr[i]
                    if (side == 1 and t > stop) or (side == -1 and t < stop):
                        pend_stop = t
                continue
        if cooldown > 0:
            cooldown -= 1
        # ---- signal on this bar's close (flat only) ----
        if last_bar[i] or i + 1 >= n or last_bar[i + 1]:
            continue
        regime = 1 if ef[i] > es[i] else (-1 if ef[i] < es[i] else 0)
        if regime == 0:
            pb_hi = pb_lo = None; pb_side = 0; continue
        if pb_side != regime:
            pb_hi = pb_lo = None; pb_side = regime
        if regime == 1 and l[i] <= ef[i]:
            pb_hi, pb_lo = h[i], l[i]
        elif regime == -1 and h[i] >= ef[i]:
            pb_hi, pb_lo = h[i], l[i]
        elif pb_hi is not None and cooldown == 0 and day_trades < int(max_trades_per_day) \
                and minute_from <= mins[i] <= minute_to:
            if regime == 1 and c[i] > pb_hi:
                rk = stop_mult * (c[i] - pb_lo)
                if rk > 0:
                    pending = 1; risk = rk; pb_hi = pb_lo = None
            elif regime == -1 and c[i] < pb_lo:
                rk = stop_mult * (pb_hi - c[i])
                if rk > 0:
                    pending = -1; risk = rk; pb_hi = pb_lo = None
    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {"total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
           "win_rate": float(100.0 * len(wins) / len(pnls)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - peak).min()), "avg_pnl": float(pnls.mean()),
           "wins": int(len(wins)), "losses": int(len(losses))}
    if return_trades:
        out["trades"] = trade_log
    return out

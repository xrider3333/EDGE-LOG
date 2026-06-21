"""
OPENING RANGE BREAKOUT (ORB) — momentum / volatility-expansion at the open.

Define the opening range (high/low of the first N bars of the RTH session); when
price breaks the range, enter in the break direction and ride it, flat by close.

WHY this one is different from the constructs that failed:
  • The 16yr ES/NQ feasibility found ORB's BEST year is 2022 (the bear) on every
    config — the opposite of the long-beta strategies that died in down years.
    Breakouts feed on trend + volatility expansion, which bear markets supply.
  • It works TWO-SIDED (not just long), so it's a real momentum edge, not bull-beta.
  • Frequent (~1 trade/day), EOD-flat → roll-immune, cheap.

Mechanics:
  • Opening range = high/low of the first `or_bars` bars of each session.
  • Direction (`trade_mode`):
      First-candle dir  — trade only the way the opening-range candle closed
      Both              — trade either break (purest, most two-sided)
      Long Only / Short Only
  • Entry at the break level (range edge ± buffer); if the bar gaps through, fill
    at that bar's open (pessimistic).
  • Stop = `stop_frac` × opening-range width away from entry (1.0 = the opposite
    extreme). Optional `target_R` take-profit at a multiple of initial risk.
  • Exit on stop, target, or the session's last bar (no overnight).
  • One entry per session (the first break).

Needs per-bar session ids (day_id). Opening range is in BARS, so on 5-min data
6 bars = 30 min, 3 = 15 min, 12 = 60 min. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 1.0 · open-momentum'
DESCRIPTION   = ("Break of the first-N-bars opening range, ride the move, flat by close. "
                 "A momentum/vol-expansion capture whose best year (16yr test) was the "
                 "2022 bear — two-sided, frequent, roll-immune. Tune OR length + stop/target.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "or_bars": {
        "default": 6, "min": 1, "max": 24, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "Length of the opening range in BARS. On 5-min data: 3=15min, "
                   "6=30min, 12=60min. Longer = fewer, higher-quality breaks.",
    },
    "trade_mode": {
        "default": "First-candle dir", "type": "str",
        "options": ["First-candle dir", "Both", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "First-candle dir = trade only the way the opening-range candle "
                   "closed (best NQ Sharpe in test). Both = either break (most two-sided, "
                   "least beta). Long/Short Only for research.",
    },
    "stop_frac": {
        "default": 1.0, "min": 0.25, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range width. "
                   "1.0 = the opposite extreme of the range. Smaller = tighter stop, "
                   "more losers but smaller ones.",
    },
    "target_R": {
        "default": 0.0, "min": 0.0, "max": 10.0, "step": 0.5, "type": "float",
        "label": "Target (× risk, 0=EOD only)",
        "tooltip": "Take-profit at this multiple of initial risk (entry-to-stop). "
                   "0 disables it → ride to the session close (let winners run).",
    },
    "breakout_buf": {
        "default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": "Require price to clear the range edge by this fraction of the range "
                   "width before entering — filters marginal pokes. 0 = trade the touch.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (OR + direction)": {
        "or_bars": [3, 6, 12], "trade_mode": ["First-candle dir", "Both"],
        "stop_frac": [1.0], "target_R": [0.0], "breakout_buf": [0.0], "flat_eod": [True],
    },
    "Medium (stops + targets)": {
        "or_bars": [3, 6, 12], "trade_mode": ["First-candle dir", "Both", "Long Only"],
        "stop_frac": [0.5, 1.0], "target_R": [0.0, 2.0, 3.0],
        "breakout_buf": [0.0, 0.1], "flat_eod": [True],
    },
    "Long   (full sweep)": {
        "or_bars": [2, 3, 6, 9, 12, 18],
        "trade_mode": ["First-candle dir", "Both", "Long Only", "Short Only"],
        "stop_frac": [0.5, 0.75, 1.0, 1.5], "target_R": [0.0, 1.5, 2.0, 3.0, 5.0],
        "breakout_buf": [0.0, 0.05, 0.1, 0.2], "flat_eod": [True],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 6, trade_mode: str = "First-candle dir",
    stop_frac: float = 1.0, target_R: float = 0.0, breakout_buf: float = 0.0,
    flat_eod: bool = True,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None                      # ORB needs session structure

    allow_long  = trade_mode in ("First-candle dir", "Both", "Long Only")
    allow_short = trade_mode in ("First-candle dir", "Both", "Short Only")

    pnl_list, trade_log = [], []

    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if m > or_bars + 1 and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            or_hi = sh[:or_bars].max()
            or_lo = sl[:or_bars].min()
            rng   = or_hi - or_lo
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf    = breakout_buf * rng
                up_lvl = or_hi + buf
                dn_lvl = or_lo - buf

                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; ek = -1
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl
                        dn = sl[k] <= dn_lvl
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            stop  = entry - stop_frac * rng
                            tgt   = entry + target_R * (entry - stop) if target_R > 0 else np.inf
                            pos = 1; ek = k; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            stop  = entry + stop_frac * rng
                            tgt   = entry - target_R * (stop - entry) if target_R > 0 else -np.inf
                            pos = -1; ek = k; continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                pnl_list.append(stop - entry)
                                if return_trades: trade_log.append((i + ek, i + k, stop - entry, 1, entry))
                                pos = 0; break
                            if target_R > 0 and sh[k] >= tgt:
                                pnl_list.append(tgt - entry)
                                if return_trades: trade_log.append((i + ek, i + k, tgt - entry, 1, entry))
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                pnl_list.append(entry - stop)
                                if return_trades: trade_log.append((i + ek, i + k, entry - stop, -1, entry))
                                pos = 0; break
                            if target_R > 0 and sl[k] <= tgt:
                                pnl_list.append(entry - tgt)
                                if return_trades: trade_log.append((i + ek, i + k, entry - tgt, -1, entry))
                                pos = 0; break
                if pos != 0:                                        # EOD flat at last close
                    pnl = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
        i = j

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, dtype=float)
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

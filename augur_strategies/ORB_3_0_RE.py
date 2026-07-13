"""
OPENING RANGE BREAKOUT — 137-lock + RE-ENTRY research (item Q, ORB.md §6).

ORB takes ONE trade per session: on whipsaw days the first break stops out and the session is
over — even when the real move then leaves without us. This file allows ONE second entry,
only after the FIRST trade exits on its STOP (a target hit or EOD ends the session as before),
selected by `reentry_mode`:

    "none"     baseline — one trade/session (== ORB_3_0_BE; the anchor).
    "rebreak"  re-enter the SAME side if price comes all the way back and re-breaks the same
               range edge (touch fill at the level, vol-filtered like a fresh break).
    "flip"     enter the OPPOSITE side on a touch of the other range edge. NB: a 1.75x-range
               stop already sits beyond the far edge, so this fires almost immediately after
               the stop-out — fills gap-aware at the far level / the next open.
    "sar"      stop-and-reverse — the stop fill IS the new entry (opposite side, same bar,
               entry = actual exit price incl. gap-through), managed from the next bar.

The second trade carries the full exit stack of the first (1.75xOR stop, 4.5R target,
breakeven 1.0R, EOD flat, gap-through realism). Max 2 trades/session. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 137-lock + re-entry research (reentry_mode)'
DESCRIPTION   = ("Run #137's champion + 1.0R breakeven, plus ONE optional second entry after a "
                 "stop-out: same-side re-break, opposite-side flip, or immediate stop-and-reverse. "
                 "Research for item Q — do whipsaw days pay for a second shot?")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_BE.py"

DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "target_R":     {"default": 4.5,  "min": 4.5,  "max": 4.5,  "step": 0.5,  "type": "float", "label": "Target (× risk)"},
    "be_after_R":   {"default": 1.0,  "min": 0.0,  "max": 4.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk, 0=off)"},
    "reentry_mode": {
        "default": "none", "type": "str",
        "options": ["none", "rebreak", "flip", "sar"],
        "label": "Re-entry after stop-out",
        "tooltip": "none = one trade/session (deploy). rebreak = same side on a re-break of the "
                   "same edge. flip = opposite side on the far edge (fires fast — the stop sits "
                   "beyond it). sar = reverse at the stop fill itself. Max 2 trades/session.",
    },
}

PARAM_GRID_PRESETS = {
    "Re-entry bake-off (137+BE lock)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_after_R": [1.0],
        "reentry_mode": ["none", "rebreak", "flip", "sar"],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_after_R: float = 1.0, reentry_mode: str = "none",
    flat_eod: bool = True, skip_holidays: bool = True,
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

    allow_long  = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    pnl_list, trade_log = [], []
    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if i in _holiday_start:
            i = j; continue
        if _allow_start.get(i, True) is False:
            i = j; continue
        if m > or_bars + 1 and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            sv = v[i:j] if v is not None else None
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
                _risk = 0.0; _mfe = 0.0; _be = False
                n_done = 0          # trades exited this session
                first_side = 0      # side of trade 1
                may_reenter = False # armed only by a STOP exit of trade 1

                def _arm(side, px, k):
                    nonlocal pos, entry, stop, tgt, ek, _risk, _mfe, _be
                    pos = side; entry = px; ek = k
                    _risk = stop_frac * rng
                    stop = entry - _risk if side > 0 else entry + _risk
                    tgt = (entry + target_R * _risk) if side > 0 else (entry - target_R * _risk)
                    if target_R <= 0:
                        tgt = np.inf if side > 0 else -np.inf
                    _mfe = 0.0; _be = False

                def _book(px_exit, k, side):
                    nonlocal n_done
                    pnl = (px_exit - entry) if side > 0 else (entry - px_exit)
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, i + k, pnl, side, entry))
                    n_done += 1

                for k in range(or_bars, m):
                    if pos == 0:
                        if n_done >= 2 or (n_done == 1 and not may_reenter):
                            break
                        if n_done == 0:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                            if not (up or dn):
                                continue
                            if vol_filter > 0 and sv is not None and k > 0:
                                mv = sv[:k].mean()
                                if mv > 0 and sv[k] < vol_filter * mv:
                                    continue
                            if long_ok and up:
                                first_side = 1
                                _arm(1, max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl, k); continue
                            elif short_ok and dn:
                                first_side = -1
                                _arm(-1, min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl, k); continue
                            continue
                        # ── second entry (only after a stop-out of trade 1) ──
                        if reentry_mode == "rebreak":
                            if first_side > 0 and sh[k] >= up_lvl:
                                if vol_filter > 0 and sv is not None and k > 0:
                                    mv = sv[:k].mean()
                                    if mv > 0 and sv[k] < vol_filter * mv:
                                        continue
                                _arm(1, max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl, k); continue
                            if first_side < 0 and sl[k] <= dn_lvl:
                                if vol_filter > 0 and sv is not None and k > 0:
                                    mv = sv[:k].mean()
                                    if mv > 0 and sv[k] < vol_filter * mv:
                                        continue
                                _arm(-1, min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl, k); continue
                        elif reentry_mode == "flip":
                            if first_side > 0 and short_ok and sl[k] <= dn_lvl:
                                _arm(-1, min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl, k); continue
                            if first_side < 0 and long_ok and sh[k] >= up_lvl:
                                _arm(1, max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl, k); continue
                        continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:
                                ex_px = so[k] if so[k] < stop else stop
                                _book(ex_px, k, 1)
                                was_first = (n_done == 1)
                                if was_first and reentry_mode != "none":
                                    may_reenter = True
                                    if reentry_mode == "sar" and short_ok:
                                        _arm(-1, ex_px, k)          # reverse at the fill
                                        may_reenter = False
                                        continue
                                pos = 0
                                if n_done >= 2 or not may_reenter:
                                    break
                                continue
                            if target_R > 0 and sh[k] >= tgt:
                                _book(tgt, k, 1); pos = 0; break
                            if be_after_R > 0 and not _be:
                                _mfe = max(_mfe, sh[k] - entry)
                                if _mfe >= be_after_R * _risk:
                                    _be = True; stop = entry
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop
                                _book(ex_px, k, -1)
                                was_first = (n_done == 1)
                                if was_first and reentry_mode != "none":
                                    may_reenter = True
                                    if reentry_mode == "sar" and long_ok:
                                        _arm(1, ex_px, k)
                                        may_reenter = False
                                        continue
                                pos = 0
                                if n_done >= 2 or not may_reenter:
                                    break
                                continue
                            if target_R > 0 and sl[k] <= tgt:
                                _book(tgt, k, -1); pos = 0; break
                            if be_after_R > 0 and not _be:
                                _mfe = max(_mfe, entry - sl[k])
                                if _mfe >= be_after_R * _risk:
                                    _be = True; stop = entry
                if pos != 0:                                        # EOD flat
                    pnl = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
        i = j

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

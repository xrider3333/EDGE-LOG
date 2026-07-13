"""
OPENING RANGE BREAKOUT — 2-LOT PYRAMID: add the runner only at +1R (item U, ORB.md §6).

The ensemble (§4.16 / run #159) enters BOTH contracts at the break. This variant adds lot B
only when the trade PROVES itself — a resting stop order at entry + pyramid_at_R × risk (the
same level where lot A's breakeven arms), so:

    • Lot A (ride) : the deploy single-lot — 1.75×OR stop, breakeven→entry at be_after_R,
                     take-profit at target_R, EOD flat.
    • Lot B (adder): fills on the first TOUCH of entry ± pyramid_at_R × risk (gap-aware);
                     its stop starts at lot A's ENTRY (so at fill it risks exactly the
                     pyramided distance and the whole position risks ~0 R net); then trails
                     on the rolling trail_bars-bar low/high to EOD. Never fills on losers.

Accounting matches the ensemble: ONE booked trade per session = 0.5 × (lotA + lotB), with
lotB = 0 when it never fills — i.e. per-2-contract-capital, directly comparable to run #159
and the single-lot deploy. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 2-lot pyramid (add at +R)'
DESCRIPTION   = ("The #137 entry with the 2nd contract added only at +pyramid_at_R × risk (a "
                 "resting stop where the breakeven arms) instead of at the break: half the "
                 "entry risk of the ensemble, doubles up only on provers. Lot B trails on an "
                 "N-bar low/high. Booked as the 50/50 blend (2-contract-capital basis).")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_ENS.py"

DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "target_R":     {"default": 4.5,  "min": 4.5,  "max": 4.5,  "step": 0.5,  "type": "float", "label": "Lot A target (× risk)"},
    "be_after_R":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Lot A breakeven (× risk) — PINNED"},
    "pyramid_at_R": {
        "default": 1.0, "min": 0.25, "max": 3.0, "step": 0.25, "type": "float",
        "label": "Add lot B at (× risk)",
        "tooltip": "Resting stop for the 2nd contract at entry ± this multiple of initial risk. "
                   "1.0 = where the breakeven arms. Lower adds earlier (more fills, more risk); "
                   "higher adds only on strong movers.",
    },
    "trail_bars": {
        "default": 5, "min": 2, "max": 12, "step": 1, "type": "int",
        "label": "Lot B trail (bars)",
        "tooltip": "Trail the added contract on the rolling N-bar low (long) / high (short) from "
                   "its own fill; stop only moves favorably; ride to trail-out or EOD.",
    },
}

PARAM_GRID_PRESETS = {
    "Pyramid (add level × trail)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_after_R": [1.0],
        "pyramid_at_R": [0.5, 1.0, 1.5, 2.0], "trail_bars": [3, 5, 8],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_after_R: float = 1.0, pyramid_at_R: float = 1.0, trail_bars: int = 5,
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

                pos = 0; entry = 0.0; ek = -1; risk = 0.0
                ast = 0.0; a_on = False; a_pnl = 0.0; a_ex = -1
                tgt = 0.0; _mfe = 0.0; _be = False
                add_lvl = 0.0                 # resting stop for lot B
                bst = 0.0; b_on = False; b_in = False; b_entry = 0.0; b_pnl = 0.0; b_ex = -1; ekb = -1
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl
                        dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            pos = 1
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            pos = -1
                        else:
                            continue
                        ek = k; risk = stop_frac * rng
                        ast = entry - risk if pos > 0 else entry + risk
                        tgt = (entry + target_R * risk) if pos > 0 else (entry - target_R * risk)
                        if target_R <= 0:
                            tgt = np.inf if pos > 0 else -np.inf
                        add_lvl = (entry + pyramid_at_R * risk) if pos > 0 else (entry - pyramid_at_R * risk)
                        a_on = True; a_pnl = 0.0; a_ex = -1
                        b_on = b_in = False; b_pnl = 0.0; b_ex = -1
                        _mfe = 0.0; _be = False
                        continue
                    # ── manage ──
                    if pos > 0:
                        # lot B fill: resting buy-stop at add_lvl (gap-aware), only while A is alive or B already in
                        if not b_in and pyramid_at_R > 0 and sh[k] >= add_lvl and (a_on or b_on):
                            b_entry = so[k] if so[k] > add_lvl else add_lvl
                            bst = entry                                   # initial stop = lot A entry
                            b_in = b_on = True; ekb = k
                        if b_on and trail_bars > 0 and k > ekb:
                            ts = max(ekb, k - trail_bars)
                            trail_low = sl[ts:k].min() if k > ts else sl[ekb]
                            bst = max(bst, trail_low)
                        if a_on and sl[k] <= ast:
                            ex = so[k] if so[k] < ast else ast
                            a_pnl = ex - entry; a_on = False; a_ex = k
                        if b_on and sl[k] <= bst:
                            ex = so[k] if so[k] < bst else bst
                            b_pnl = ex - b_entry; b_on = False; b_ex = k
                        if a_on and target_R > 0 and sh[k] >= tgt:
                            a_pnl = tgt - entry; a_on = False; a_ex = k
                        if a_on and be_after_R > 0 and not _be:
                            _mfe = max(_mfe, sh[k] - entry)
                            if _mfe >= be_after_R * risk:
                                _be = True; ast = entry
                    else:
                        if not b_in and pyramid_at_R > 0 and sl[k] <= add_lvl and (a_on or b_on):
                            b_entry = so[k] if so[k] < add_lvl else add_lvl
                            bst = entry
                            b_in = b_on = True; ekb = k
                        if b_on and trail_bars > 0 and k > ekb:
                            ts = max(ekb, k - trail_bars)
                            trail_high = sh[ts:k].max() if k > ts else sh[ekb]
                            bst = min(bst, trail_high)
                        if a_on and sh[k] >= ast:
                            ex = so[k] if so[k] > ast else ast
                            a_pnl = entry - ex; a_on = False; a_ex = k
                        if b_on and sh[k] >= bst:
                            ex = so[k] if so[k] > bst else bst
                            b_pnl = b_entry - ex; b_on = False; b_ex = k
                        if a_on and target_R > 0 and sl[k] <= tgt:
                            a_pnl = entry - tgt; a_on = False; a_ex = k
                        if a_on and be_after_R > 0 and not _be:
                            _mfe = max(_mfe, entry - sl[k])
                            if _mfe >= be_after_R * risk:
                                _be = True; ast = entry
                    if not a_on and not b_on and not (not b_in and pyramid_at_R > 0):
                        break
                    if not a_on and not b_on and b_in:
                        break
                if pos != 0:
                    eod = 0.0
                    if a_on or b_on:
                        px = sc[-1]
                        if a_on: a_pnl = (px - entry) if pos > 0 else (entry - px); a_ex = j - 1 - i
                        if b_on: b_pnl = (px - b_entry) if pos > 0 else (b_entry - px); b_ex = j - 1 - i
                    pnl = 0.5 * (a_pnl + (b_pnl if b_in else 0.0))
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((i + ek, i + max(a_ex, b_ex if b_in else a_ex), pnl, 1 if pos > 0 else -1, entry))
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

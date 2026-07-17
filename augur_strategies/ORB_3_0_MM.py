"""
OPENING RANGE BREAKOUT — MEASURED-MOVE TARGET (X4 study).

ORB_3_0_BE.py byte-for-byte (touch entry with gap-aware fill, pessimistic stop-first,
gap-through stop fills, breakeven armed on bar CLOSE at be_after_R x risk acting from
the next bar, EOD flat, skip_holidays, atr_filter, vol_filter, 137-locked defaults)
with ONE change: the profit target is quoted in OPENING-RANGE WIDTHS instead of
R-multiples. New knob target_orw: tgt = entry +/- target_orw * rng (rng = OR width);
0 = no target (ride to EOD). target_R is REMOVED.

Equivalence anchor: risk = stop_frac*rng = 1.75*rng, so the deploy target_R=4.5 x risk
== 4.5*1.75 = 7.875 OR-widths — target_orw=7.875 must reproduce the BE deploy config
exactly (same trades, same geometry). The measured-move thesis: a target proportional
to the range itself (not the stop) should trade win rate up against expectancy.
PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 137-lock + breakeven · measured-move target (target_orw)'
DESCRIPTION   = ("Run #137's champion config LOCKED (or1 / stop 1.75 / vol 1.25 / Both / "
                 "skip-holidays / be_after_R 1.0) with the R-multiple target swapped for a "
                 "MEASURED-MOVE target: target_orw x opening-range width beyond entry. "
                 "target_orw=7.875 reproduces the deploy 4.5R exactly (4.5 x 1.75 = 7.875 "
                 "OR-widths); smaller values test the classic measured-move projection "
                 "(1-2 x range) that trades WR up against expectancy. 0 = ride to EOD.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Lineage: measured-move target study on top of the ORB 3.0 breakeven deployable (#137+BE config).
_AUGUR_PARENT = "ORB_3_0_BE.py"

# ── 137-LOCK: every knob pinned to run #137's champion (single-point min=max) so the
#    Auto-Validate search can ONLY move target_orw. flat_eod / skip_holidays dropped from
#    the search dict entirely (bools would expand to [True,False]) — the signature defaults
#    below carry 137's values. atr_filter 0.1 kept for fidelity (it's a proven no-op).
DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "be_after_R":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk, 0=off)"},
    "target_orw": {
        # Default 7.875 = the EXACT deploy equivalence point (target_R 4.5 x stop_frac
        # 1.75). The measured-move sweep explores 1.0-5.0 OR-widths — the projection a
        # chart trader would actually draw. 0 disables the target (ride to EOD flat).
        "default": 7.875, "min": 7.875, "max": 7.875, "step": 0.125, "type": "float",
        "label": "Target (× OR width, 0=off)",
        "tooltip": "Profit target quoted in opening-range WIDTHS beyond entry (the "
                   "measured-move projection), replacing the R-multiple target. "
                   "7.875 == the deploy 4.5R (4.5 x 1.75 stop). 0 = no target.",
    },
}

PARAM_GRID_PRESETS = {
    "MM sweep (137+BE locked)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "be_after_R": [1.0],
        "target_orw": [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.875],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_orw: float = 7.875,
    atr_filter: float = 0.1,
    be_after_R: float = 0.0,
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

    # ── Vol-regime filter (atr_filter > 0): precompute per-session allow mask.
    #    Skip a session whose recent 5-session avg range sits below atr_filter ×
    #    the trailing 60-session median range — i.e. the calm regimes the regime
    #    report card flagged as ORB's weakest bucket. Trailing-only windows, so
    #    no look-ahead. atr_filter == 0 leaves everything allowed (no change).
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b
    # ── Half-day / holiday skip (skip_holidays): a half-day session has far fewer
    #    bars than a normal RTH day. Flag sessions shorter than 70% of the MEDIAN
    #    session length (timeframe-agnostic, no calendar needed). Catches early
    #    closes (Thanksgiving, Memorial Day, July-3, Christmas Eve) plus any
    #    partial first/last session at the dataset edges. OFF by default.
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
                continue                          # warm-up → allow
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
        if i in _holiday_start:                  # half-day / holiday skip
            i = j; continue
        if _allow_start.get(i, True) is False:   # vol-regime filter skipped this session
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
                _risk = 0.0; _mfe = 0.0; _be = False        # breakeven state (be_after_R)
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl
                        dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # volume filter — skip thin-volume pokes
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            stop  = entry - stop_frac * rng
                            tgt   = entry + target_orw * rng if target_orw > 0 else np.inf
                            pos = 1; ek = k; _risk = entry - stop; _mfe = 0.0; _be = False; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            stop  = entry + stop_frac * rng
                            tgt   = entry - target_orw * rng if target_orw > 0 else -np.inf
                            pos = -1; ek = k; _risk = stop - entry; _mfe = 0.0; _be = False; continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                # Gap-through realism: if the bar OPENED below the stop,
                                # a stop order fills at the open, not the stop price.
                                # Booking exactly `stop` understated losses — the main
                                # inflator behind the tight-stop fake-PF artifact.
                                ex_px = so[k] if so[k] < stop else stop
                                pnl_list.append(ex_px - entry)
                                if return_trades: trade_log.append((i + ek, i + k, ex_px - entry, 1, entry))
                                pos = 0; break
                            if target_orw > 0 and sh[k] >= tgt:
                                pnl_list.append(tgt - entry)
                                if return_trades: trade_log.append((i + ek, i + k, tgt - entry, 1, entry))
                                pos = 0; break
                            # Breakeven (be_after_R): arm on this bar's CLOSE once unrealized
                            # high-water >= X × initial risk; the entry-price stop takes effect
                            # from the NEXT bar (causal — no intrabar sequence guess). Checked
                            # AFTER stop/target so it can't rescue a bar that already stopped.
                            if be_after_R > 0 and not _be:
                                _mfe = max(_mfe, sh[k] - entry)
                                if _mfe >= be_after_R * _risk:
                                    _be = True; stop = entry
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                pnl_list.append(entry - ex_px)
                                if return_trades: trade_log.append((i + ek, i + k, entry - ex_px, -1, entry))
                                pos = 0; break
                            if target_orw > 0 and sl[k] <= tgt:
                                pnl_list.append(entry - tgt)
                                if return_trades: trade_log.append((i + ek, i + k, entry - tgt, -1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not _be:            # breakeven arm (see long side)
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

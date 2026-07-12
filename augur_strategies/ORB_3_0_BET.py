"""
OPENING RANGE BREAKOUT — 137-lock + BREAKEVEN-TRIGGER research (be_mode).

Item K (ORB.md §6). Item H proved the R-multiple breakeven (move stop -> entry once
unrealized profit >= 1.0 x initial risk) cuts drawdown ~33% and holds in the lockbox.
This file asks the follow-up: is the R-multiple the BEST arming signal, or does a
different trigger protect better? It keeps run #137's champion config FULLY PINNED and
exposes ONE selectable breakeven trigger via `be_mode`, so each trigger can be swept in
ISOLATION against the identical entry/exit plumbing (any drawdown delta is attributable
to the trigger alone — see ORB.md §6 item K methodology).

be_mode selects which signal arms the breakeven (stop -> entry); exactly one is active:
    "off"    no breakeven (= exact #137 behaviour).
    "R"      arm when MFE >= be_after_R   x initial risk   (== ORB_3_0_BE.py; the control).
    "bars"   arm after be_after_bars bars in the trade      (time-based).
    "atr"    arm when MFE >= be_after_atr x trailing session ATR (vol-normalized, decoupled
             from the wide 1.75 stop).
    "orw"    arm when MFE >= be_after_orw x opening-range width (decoupled from stop_frac).
    "struct" arm on the first higher-low (long) / lower-high (short) off the trade's
             trough/peak that closes back on the profitable side (price-structure).

INVARIANT: with be_mode="R" this file is behaviourally identical to ORB_3_0_BE.py (the arm
math and its placement are copied verbatim), so be_mode="R"/be_after_R=1.0 reproduces run
#154/#156 and be_after_R=0 (or be_mode="off") reproduces plain #137 ($567,297 full window).
Arms on the bar CLOSE, acts from the next bar (causal). PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 137-lock + BE-trigger research (be_mode)'
DESCRIPTION   = ("Run #137's champion LOCKED with a selectable breakeven trigger (be_mode: "
                 "R / time / ATR / OR-width / structure). Research fork for item K — does a "
                 "smarter arm-signal beat the static 1.0R breakeven? Sweep one mode at a time.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_BE.py"

# ── 137-LOCK (== ORB_3_0_BE): every base knob pinned to run #137's champion; only the
#    breakeven TRIGGER moves. Presets sweep one mode's threshold at a time so the run
#    report's 2C PDP shows that trigger's drawdown curve in isolation.
DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "target_R":     {"default": 4.5,  "min": 4.5,  "max": 4.5,  "step": 0.5,  "type": "float", "label": "Target (× risk)"},
    "be_mode": {
        "default": "R", "type": "str",
        "options": ["off", "R", "bars", "atr", "orw", "struct"],
        "label": "Breakeven trigger",
        "tooltip": "Which signal arms the move-stop-to-entry: off / R (× risk) / bars (time) / "
                   "atr (× session ATR) / orw (× opening-range width) / struct (first higher-low). "
                   "Sweep ONE mode's threshold at a time; compare each best vs the R control.",
    },
    "be_after_R":    {"default": 1.0, "min": 0.0, "max": 4.0,  "step": 0.1, "type": "float", "label": "BE: × risk (be_mode=R)"},
    "be_after_bars": {"default": 0,   "min": 0,   "max": 20,   "step": 1,   "type": "int",   "label": "BE: bars in trade (be_mode=bars)"},
    "be_after_atr":  {"default": 0.0, "min": 0.0, "max": 1.5,  "step": 0.05,"type": "float", "label": "BE: × session ATR (be_mode=atr)"},
    "be_after_orw":  {"default": 0.0, "min": 0.0, "max": 3.0,  "step": 0.25,"type": "float", "label": "BE: × range width (be_mode=orw)"},
}

PARAM_GRID_PRESETS = {
    # One preset per trigger family — fixes be_mode and sweeps only that mode's threshold,
    # so a grid/Auto run produces a clean isolated 2C PDP (read on the MAX DD / MAR toggle).
    "BE-trigger R  (137 lock)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_mode": ["R"],
        "be_after_R": [0.0, 0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 2.5],
    },
    "BE-trigger TIME (bars)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_mode": ["bars"],
        "be_after_bars": [0, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20],
    },
    "BE-trigger ATR (× session)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_mode": ["atr"],
        "be_after_atr": [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0],
    },
    "BE-trigger OR-width": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_mode": ["orw"],
        "be_after_orw": [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0],
    },
}

_ATR_LOOKBACK = 14   # trailing sessions for the ATR (session-range) estimate


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_mode: str = "R",
    be_after_R: float = 0.0, be_after_bars: int = 0,
    be_after_atr: float = 0.0, be_after_orw: float = 0.0,
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

    # ── Session boundaries ────────────────────────────────────────────────────
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b

    # ── Half-day / holiday skip (skip_holidays) — identical to ORB_3_0_BE. ─────
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    # ── Per-session range → vol-regime filter mask AND the trailing ATR (be_mode="atr").
    #    Trailing windows only (no look-ahead). _atr_by_start[a] = mean of the PRIOR
    #    _ATR_LOOKBACK session ranges; warm-up sessions fall back to the OR width in-loop.
    _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
    _allow_start = {}
    _atr_by_start = {}
    for _si, (a, b) in enumerate(_sess_bounds):
        if _si > 0:
            _atr_by_start[a] = float(_srng[max(0, _si - _ATR_LOOKBACK):_si].mean())
        if atr_filter > 0 and len(_sess_bounds) > 6 and _si >= 6:
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
                # session ATR for be_mode="atr" (fallback to OR width until warmed up)
                _sess_atr = _atr_by_start.get(i, rng)
                if not (_sess_atr > 0):
                    _sess_atr = rng

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; ek = -1
                _risk = 0.0; _mfe = 0.0; _be = False        # breakeven state
                _trough = 0.0; _peak = 0.0                  # structure state (be_mode="struct")
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
                            tgt   = entry + target_R * (entry - stop) if target_R > 0 else np.inf
                            pos = 1; ek = k; _risk = entry - stop; _mfe = 0.0; _be = False
                            _trough = sl[k]; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            stop  = entry + stop_frac * rng
                            tgt   = entry - target_R * (stop - entry) if target_R > 0 else -np.inf
                            pos = -1; ek = k; _risk = stop - entry; _mfe = 0.0; _be = False
                            _peak = sh[k]; continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                ex_px = so[k] if so[k] < stop else stop     # gap-through realism
                                pnl_list.append(ex_px - entry)
                                if return_trades: trade_log.append((i + ek, i + k, ex_px - entry, 1, entry))
                                pos = 0; break
                            if target_R > 0 and sh[k] >= tgt:
                                pnl_list.append(tgt - entry)
                                if return_trades: trade_log.append((i + ek, i + k, tgt - entry, 1, entry))
                                pos = 0; break
                            # ── Breakeven arm (be_mode dispatch) — checked AFTER stop/target so
                            #    it can't rescue a bar that already exited. Arms on this bar's
                            #    close; the entry-price stop acts from the next bar (causal).
                            if not _be:
                                mv = sh[k] - entry
                                if mv > _mfe: _mfe = mv
                                arm = False
                                if   be_mode == "R"    and be_after_R    > 0: arm = _mfe >= be_after_R   * _risk
                                elif be_mode == "bars" and be_after_bars > 0: arm = (k - ek) >= be_after_bars
                                elif be_mode == "atr"  and be_after_atr  > 0: arm = _mfe >= be_after_atr  * _sess_atr
                                elif be_mode == "orw"  and be_after_orw  > 0: arm = _mfe >= be_after_orw  * rng
                                elif be_mode == "struct":                     arm = (sl[k] > sl[k-1]) and (sl[k-1] <= _trough + 1e-9) and (sc[k] >= entry)
                                if arm:
                                    _be = True; stop = entry
                            if sl[k] < _trough: _trough = sl[k]
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                pnl_list.append(entry - ex_px)
                                if return_trades: trade_log.append((i + ek, i + k, entry - ex_px, -1, entry))
                                pos = 0; break
                            if target_R > 0 and sl[k] <= tgt:
                                pnl_list.append(entry - tgt)
                                if return_trades: trade_log.append((i + ek, i + k, entry - tgt, -1, entry))
                                pos = 0; break
                            if not _be:
                                mv = entry - sl[k]
                                if mv > _mfe: _mfe = mv
                                arm = False
                                if   be_mode == "R"    and be_after_R    > 0: arm = _mfe >= be_after_R   * _risk
                                elif be_mode == "bars" and be_after_bars > 0: arm = (k - ek) >= be_after_bars
                                elif be_mode == "atr"  and be_after_atr  > 0: arm = _mfe >= be_after_atr  * _sess_atr
                                elif be_mode == "orw"  and be_after_orw  > 0: arm = _mfe >= be_after_orw  * rng
                                elif be_mode == "struct":                     arm = (sh[k] < sh[k-1]) and (sh[k-1] >= _peak - 1e-9) and (sc[k] <= entry)
                                if arm:
                                    _be = True; stop = entry
                            if sh[k] > _peak: _peak = sh[k]
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

"""
OPENING RANGE BREAKOUT 3.2 — TRAILING RESEARCH fork (NOT the deployable base).

Identical ENTRY/filter/stop scaffolding to ORB 3.1 (same breakout, vol filter, 0.5-floor
range-frac stop, gap-through realism, partial+bar-trail). What's added is three ways to
manage the RUNNER, so we can test whether a smarter trail beats 3.1's fixed N-bar trail:

    • trail_atr        chandelier trail: stop = high-water-mark − trail_atr × session-ATR
                       (avg range of the prior atr_period sessions). Adapts to volatility
                       instead of a fixed bar count. >0 overrides the bar trail.
    • trail_activate_R only start trailing once open profit ≥ this R-multiple — let the
                       trade breathe early, then lock in. 0 = trail from entry (= 3.1).
    • breakeven_R      once open profit ≥ this R, ratchet the stop to entry (kill the
                       left tail). 0 = off.

VALIDITY INVARIANT: with trail_atr=0, trail_activate_R=0, breakeven_R=0 this file is
byte-equivalent to ORB 3.1 (the bar-trail path is untouched), so any A/B delta is
attributable to the new mechanics alone. Verified in the smoke test below.

This is a RESEARCH file — sweep it, don't deploy from it blind. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.2 · trail research (chandelier + activate + breakeven)'
DESCRIPTION   = ("ORB 3.1 entry + three runner-management levers: chandelier ATR trail, "
                 "trail-activation threshold, and breakeven ratchet. For A/B research on "
                 "whether a smarter trail beats the fixed N-bar trail. NQ 5m default.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_1.py"

DEFAULT_PARAMS = {
    "or_bars": {"default": 1, "min": 1, "max": 12, "step": 1, "type": "int",
                "label": "Opening range (bars)", "tooltip": "OR length in bars (5m: 1=5min, 3=15min)."},
    "trade_mode": {"default": "Both", "type": "str",
                   "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
                   "label": "Direction", "tooltip": "Both = either break."},
    "stop_frac": {"default": 0.75, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
                  "label": "Stop (× range width)", "tooltip": "Initial stop as × OR width. Floor 0.5."},
    "vol_filter": {"default": 1.25, "min": 0.0, "max": 3.0, "step": 0.25, "type": "float",
                   "label": "Volume filter (× session avg, 0=off)",
                   "tooltip": "Breakout bar volume ≥ this × session mean."},
    "breakout_buf": {"default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
                     "label": "Breakout buffer (× range)", "tooltip": "Clear the edge by this × range."},
    "partial_exit_R": {"default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
                       "label": "Partial exit / lot-1 TP (× risk, 0=off)",
                       "tooltip": "Book half at this R; runner is then managed by the trail levers."},
    "trail_bars": {"default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
                   "label": "Bar trail (N-bar low/high, 0=off)",
                   "tooltip": "Fixed N-bar trail (3.1 mechanism). Ignored if trail_atr > 0."},
    # ── research levers ────────────────────────────────────────────────────────
    "trail_atr": {"default": 0.0, "min": 0.0, "max": 6.0, "step": 0.25, "type": "float",
                  "label": "Chandelier ATR trail (× session-ATR, 0=off)",
                  "tooltip": "Stop = high-water-mark − trail_atr × avg range of prior atr_period "
                             "sessions. Volatility-adaptive. >0 overrides the bar trail."},
    "trail_activate_R": {"default": 0.0, "min": 0.0, "max": 4.0, "step": 0.5, "type": "float",
                         "label": "Activate trail after (× risk, 0=from entry)",
                         "tooltip": "Only begin trailing once open profit ≥ this R. Lets the trade "
                                    "breathe early, then locks in."},
    "breakeven_R": {"default": 0.0, "min": 0.0, "max": 4.0, "step": 0.5, "type": "float",
                    "label": "Breakeven ratchet after (× risk, 0=off)",
                    "tooltip": "Once open profit ≥ this R, move the stop to entry."},
    "atr_period": {"default": 5, "min": 2, "max": 20, "step": 1, "type": "int",
                   "label": "Session-ATR lookback", "tooltip": "Sessions averaged for the chandelier ATR.",
                   "depends_on": {"trail_atr": True}},
    # ── inherited 3.1 knobs ────────────────────────────────────────────────────
    "atr_filter": {"default": 0.0, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
                   "label": "Vol-regime filter (× trailing median, 0=off)",
                   "tooltip": "Skip low-vol sessions below this × trailing-60 median range."},
    "target_R": {"default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
                 "label": "Runner target (× risk, 0=trail/EOD)", "tooltip": "Optional hard TP on the runner."},
    "flat_eod": {"default": True, "type": "bool", "label": "Flat by session close",
                 "tooltip": "Exit at each session's last bar. Keep ON."},
    "skip_holidays": {"default": False, "type": "bool", "label": "Skip holiday half-days",
                      "tooltip": "Skip short (half-day) sessions by bar count."},
}

PARAM_GRID_PRESETS = {
    "Chandelier scan": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75], "vol_filter": [1.25],
        "breakout_buf": [0.0], "partial_exit_R": [0.0], "trail_bars": [0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "atr_period": [5],
        "trail_atr": [1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
        "trail_activate_R": [0.0, 1.0, 2.0], "breakeven_R": [0.0, 1.0],
    },
    "Activate + breakeven (bar trail)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75], "vol_filter": [1.25],
        "breakout_buf": [0.0], "partial_exit_R": [0.0], "trail_bars": [5], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "trail_atr": [0.0],
        "trail_activate_R": [0.0, 1.0, 2.0], "breakeven_R": [0.0, 1.0, 2.0],
    },
}


def run_backtest(
    opens, highs, lows, closes, volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 0.75, vol_filter: float = 1.25, breakout_buf: float = 0.0,
    partial_exit_R: float = 0.0, trail_bars: int = 0,
    trail_atr: float = 0.0, trail_activate_R: float = 0.0, breakeven_R: float = 0.0,
    atr_period: int = 5,
    atr_filter: float = 0.0, target_R: float = 0.0,
    flat_eod: bool = True, skip_holidays: bool = False,
    day_id=None, return_trades: bool = False, _stop_event=None, _pause_event=None,
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
    _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
    _sidx_of = {a: si for si, (a, b) in enumerate(_sess_bounds)}

    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
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
            # session-ATR (prior sessions only) for the chandelier trail
            session_atr = None
            _si = _sidx_of.get(i)
            if trail_atr > 0 and _si is not None and _si >= 1:
                session_atr = float(_srng[max(0, _si - atr_period):_si].mean())
            or_hi = sh[:or_bars].max(); or_lo = sl[:or_bars].min()
            rng = or_hi - or_lo
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf = breakout_buf * rng
                up_lvl = or_hi + buf; dn_lvl = or_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                hwm_hi = -np.inf; hwm_lo = np.inf
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl; dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            risk = stop_frac * rng; stop = entry - risk
                            tgt  = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0
                            hwm_hi = -np.inf; hwm_lo = np.inf; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            risk = stop_frac * rng; stop = entry + risk
                            tgt  = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0
                            hwm_hi = -np.inf; hwm_lo = np.inf; continue
                    else:
                        # incorporate the just-completed bar (k-1) into the water marks — no look-ahead
                        hwm_hi = max(hwm_hi, sh[k - 1]); hwm_lo = min(hwm_lo, sl[k - 1])
                        manage = (partial_exit_R == 0 or p_done)
                        if pos > 0:
                            if manage:
                                prof = hwm_hi - entry
                                if breakeven_R > 0 and prof >= breakeven_R * risk:
                                    stop = max(stop, entry)
                                if trail_activate_R <= 0 or prof >= trail_activate_R * risk:
                                    if trail_atr > 0 and session_atr and session_atr > 0:
                                        stop = max(stop, hwm_hi - trail_atr * session_atr)
                                    elif trail_bars > 0:
                                        ts = max(ek, k - trail_bars)
                                        stop = max(stop, sl[ts:k].min() if k > ts else sl[ek])
                            if sl[k] <= stop:
                                ex_px = so[k] if so[k] < stop else stop
                                raw = ex_px - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                        else:
                            if manage:
                                prof = entry - hwm_lo
                                if breakeven_R > 0 and prof >= breakeven_R * risk:
                                    stop = min(stop, entry)
                                if trail_activate_R <= 0 or prof >= trail_activate_R * risk:
                                    if trail_atr > 0 and session_atr and session_atr > 0:
                                        stop = min(stop, hwm_lo + trail_atr * session_atr)
                                    elif trail_bars > 0:
                                        ts = max(ek, k - trail_bars)
                                        stop = min(stop, sh[ts:k].max() if k > ts else sh[ek])
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop
                                raw = entry - ex_px
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                if pos != 0:
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
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


# ── Smoke test: (1) INVARIANT — new levers off == ORB 3.1; (2) variants move results.
if __name__ == "__main__":
    import os, pandas as pd
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT = 20.0
    import importlib.util
    def _load(name):
        spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "augur_strategies", name + ".py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    orb31 = _load("ORB_3_1")
    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    A = [df["open"].values, df["high"].values, df["low"].values, df["close"].values]
    K = dict(volumes=df["volume"].values, day_id=df["day_id"].values)
    base = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25, flat_eod=True)

    r31 = orb31.run_backtest(*A, **K, **base, partial_exit_R=0.0, trail_bars=5)
    r32 = run_backtest(*A, **K, **base, partial_exit_R=0.0, trail_bars=5,
                       trail_atr=0.0, trail_activate_R=0.0, breakeven_R=0.0)
    ok = (abs(r31["total_pnl"] - r32["total_pnl"]) < 1e-6 and r31["num_trades"] == r32["num_trades"])
    print(f"INVARIANT (3.2 levers off == 3.1):  {'PASS' if ok else 'FAIL'}   "
          f"3.1=${r31['total_pnl']*MULT:,.0f}/{r31['num_trades']}  3.2=${r32['total_pnl']*MULT:,.0f}/{r32['num_trades']}")
    print()
    print("%-40s %7s %5s %6s %12s %12s" % ("variant", "trades", "WR%", "PF", "net $", "maxDD $"))
    print("-" * 92)
    for lab, kw in [
        ("3.1 baseline  bar-trail 5",              dict(trail_bars=5)),
        ("chandelier 2.5xATR",                     dict(trail_atr=2.5)),
        ("chandelier 3.0xATR",                     dict(trail_atr=3.0)),
        ("bar-trail 5 + activate@1R",              dict(trail_bars=5, trail_activate_R=1.0)),
        ("bar-trail 5 + breakeven@1R",             dict(trail_bars=5, breakeven_R=1.0)),
        ("chandelier 3.0 + activate@1R + BE@1R",   dict(trail_atr=3.0, trail_activate_R=1.0, breakeven_R=1.0)),
    ]:
        r = run_backtest(*A, **K, **base, **kw)
        print("%-40s %7d %4.0f%% %6.2f %12s %12s" % (
            lab, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(r["total_pnl"]*MULT), "${:,.0f}".format(r["max_drawdown"]*MULT)))

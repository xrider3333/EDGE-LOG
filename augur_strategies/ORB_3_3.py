"""
OPENING RANGE BREAKOUT 3.3 — TIME-STRUCTURE research fork (NOT the deployable base).

Identical entry/exit scaffolding to ORB 3.1 (deployable single-lot ride + bar-trail),
plus two session-clock levers to test whether *when* in the session matters:

    • entry_cutoff_bars  only ENTER if the breakout fires before this session-bar index.
                         5-min RTH: 12=first hour, 24=first 2h, 36=first 3h. Skips
                         late-day breaks (thin, prone to reverse). 0 = enter any time.
    • time_stop_bar      if still in a position AT this session-bar index, exit at that
                         bar's close (absolute midday time-stop — bail on trades that
                         haven't worked by lunch, before the afternoon chop/reversal).
                         5-min RTH: bar t ≈ 9:30 + 5·t min → 42≈13:00, 48≈13:30, 54≈14:00.
                         0 = off (ride to trail / EOD).

VALIDITY INVARIANT: with entry_cutoff_bars=0 and time_stop_bar=0 this is byte-equivalent
to ORB 3.1 (asserted in the smoke test). Research file — sweep, don't deploy blind.
PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.3 · time-structure research (entry window + time-stop)'
DESCRIPTION   = ("ORB 3.1 deployable exits + two session-clock levers: an entry-time cutoff "
                 "(skip late-day breaks) and an absolute midday time-stop. For A/B research on "
                 "whether time-of-day filtering helps. NQ 5m default.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_1.py"

DEFAULT_PARAMS = {
    "or_bars": {"default": 1, "min": 1, "max": 12, "step": 1, "type": "int",
                "label": "Opening range (bars)", "tooltip": "OR length in bars (5m: 1=5min)."},
    "trade_mode": {"default": "Both", "type": "str",
                   "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
                   "label": "Direction", "tooltip": "Both = either break."},
    "stop_frac": {"default": 0.75, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
                  "label": "Stop (× range width)", "tooltip": "Initial stop × OR width. Floor 0.5."},
    "vol_filter": {"default": 1.25, "min": 0.0, "max": 3.0, "step": 0.25, "type": "float",
                   "label": "Volume filter (× session avg, 0=off)", "tooltip": "Breakout-bar volume gate."},
    "breakout_buf": {"default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
                     "label": "Breakout buffer (× range)", "tooltip": "Clear the edge by this × range."},
    "partial_exit_R": {"default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
                       "label": "Partial exit (× risk, 0=off)", "tooltip": "Book half at this R; runner trails."},
    "trail_bars": {"default": 5, "min": 0, "max": 20, "step": 1, "type": "int",
                   "label": "Bar trail (N-bar low/high, 0=off)", "tooltip": "Trail the runner. 5 = deployable."},
    # ── time-structure research levers ─────────────────────────────────────────
    "entry_cutoff_bars": {"default": 0, "min": 0, "max": 72, "step": 1, "type": "int",
                          "label": "Entry cutoff (session bar, 0=off)",
                          "tooltip": "Only enter if the breakout fires before this session-bar index. "
                                     "5m RTH: 12=1h, 24=2h, 36=3h. Skips late-day breaks."},
    "time_stop_bar": {"default": 0, "min": 0, "max": 78, "step": 1, "type": "int",
                      "label": "Time-stop (session bar, 0=off)",
                      "tooltip": "Force-exit at this session-bar index if still in a trade. "
                                 "5m RTH: 42≈13:00, 48≈13:30, 54≈14:00. 0 = ride to trail/EOD."},
    # ── inherited ──────────────────────────────────────────────────────────────
    "atr_filter": {"default": 0.0, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
                   "label": "Vol-regime filter (0=off)", "tooltip": "Skip low-vol sessions (off = best)."},
    "target_R": {"default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
                 "label": "Runner target (× risk, 0=trail/EOD)", "tooltip": "Optional hard TP."},
    "flat_eod": {"default": True, "type": "bool", "label": "Flat by session close", "tooltip": "Keep ON."},
    "skip_holidays": {"default": False, "type": "bool", "label": "Skip holiday half-days",
                      "tooltip": "Skip short (half-day) sessions by bar count."},
}

PARAM_GRID_PRESETS = {
    "Entry-window scan": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75], "vol_filter": [1.25],
        "breakout_buf": [0.0], "partial_exit_R": [0.0], "trail_bars": [5], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "time_stop_bar": [0],
        "entry_cutoff_bars": [0, 6, 12, 18, 24, 36, 48],
    },
    "Time-stop scan": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75], "vol_filter": [1.25],
        "breakout_buf": [0.0], "partial_exit_R": [0.0], "trail_bars": [5], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "entry_cutoff_bars": [0],
        "time_stop_bar": [0, 36, 42, 48, 54, 60, 66],
    },
}


def run_backtest(
    opens, highs, lows, closes, volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 0.75, vol_filter: float = 1.25, breakout_buf: float = 0.0,
    partial_exit_R: float = 0.0, trail_bars: int = 5,
    entry_cutoff_bars: int = 0, time_stop_bar: int = 0,
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
                for k in range(or_bars, m):
                    if pos == 0:
                        # entry-time cutoff — no new entries at/after this session bar
                        if entry_cutoff_bars > 0 and k >= entry_cutoff_bars:
                            break
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
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            risk = stop_frac * rng; stop = entry + risk
                            tgt  = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; continue
                    else:
                        if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                            ts = max(ek, k - trail_bars)
                            if pos > 0:
                                stop = max(stop, sl[ts:k].min() if k > ts else sl[ek])
                            else:
                                stop = min(stop, sh[ts:k].max() if k > ts else sh[ek])
                        if pos > 0:
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
                            # absolute time-stop — flat at this session bar's close
                            if time_stop_bar > 0 and k >= time_stop_bar:
                                raw = sc[k] - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                        else:
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
                            if time_stop_bar > 0 and k >= time_stop_bar:
                                raw = entry - sc[k]
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


# ── Smoke test: (1) INVARIANT — both levers off == ORB 3.1; (2) variants move results.
if __name__ == "__main__":
    import os, pandas as pd, importlib.util
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT = 20.0
    def _load(name):
        spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "augur_strategies", name + ".py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
    orb31 = _load("ORB_3_1")
    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    A = [df["open"].values, df["high"].values, df["low"].values, df["close"].values]
    K = dict(volumes=df["volume"].values, day_id=df["day_id"].values)
    base = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25, trail_bars=5, flat_eod=True)

    r31 = orb31.run_backtest(*A, **K, partial_exit_R=0.0, **base)
    r33 = run_backtest(*A, **K, partial_exit_R=0.0, entry_cutoff_bars=0, time_stop_bar=0, **base)
    ok = (abs(r31["total_pnl"] - r33["total_pnl"]) < 1e-6 and r31["num_trades"] == r33["num_trades"])
    print(f"INVARIANT (3.3 levers off == 3.1):  {'PASS' if ok else 'FAIL'}   "
          f"3.1=${r31['total_pnl']*MULT:,.0f}/{r31['num_trades']}  3.3=${r33['total_pnl']*MULT:,.0f}/{r33['num_trades']}")
    print()
    print("%-34s %7s %5s %6s %12s %12s" % ("variant", "trades", "WR%", "PF", "net $", "maxDD $"))
    print("-" * 84)
    for lab, kw in [
        ("3.1 baseline (no time levers)",   {}),
        ("entry cutoff 12 (first hour)",    dict(entry_cutoff_bars=12)),
        ("entry cutoff 24 (first 2h)",      dict(entry_cutoff_bars=24)),
        ("time-stop 48 (~13:30)",           dict(time_stop_bar=48)),
        ("time-stop 54 (~14:00)",           dict(time_stop_bar=54)),
        ("cutoff 24 + time-stop 54",        dict(entry_cutoff_bars=24, time_stop_bar=54)),
    ]:
        r = run_backtest(*A, **K, partial_exit_R=0.0, **base, **kw)
        print("%-34s %7d %4.0f%% %6.2f %12s %12s" % (
            lab, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(r["total_pnl"]*MULT), "${:,.0f}".format(r["max_drawdown"]*MULT)))

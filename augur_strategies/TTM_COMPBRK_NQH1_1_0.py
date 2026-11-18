"""
TTM COMPBRK NQH1 1.0 - first 1-hour inside bar of the session, broken in the daily-trend direction. NQ 15m RTH. Family TTM.

ORIGIN (w121 compression-break hunt 11-13, w132 loose screen 11-14, lane TTM; MANAGER 11-18 next test).
Prereg C:/EdgeLog/manager/prereg/PREREG_ttm_w121_compression_break_2026-11-13.md, cell H1.
Harness C:/EdgeLog/_anatomy_cache/ttm_w121/gate.py (cell H1). Parity at file defaults = harness cell H1.

RULE (finished bars only; hour bars = 15m bars grouped by clock hour):
  1. Daily trend = sign(prior session close - SMA(sma_len) of session closes up to the prior session). Up = long only.
  2. The first clock-hour bar starting between h_start and h_end (minutes ET) that is INSIDE the previous hour bar of
     the same session (high <= prior high, low >= prior low).
  3. After that hour closes: buy stop at its high + 1 tick (long; mirror short), live on 15m bars starting before
     entry_end. Fill = max(level, bar open) (gaps fill at the open). Stop = the inside hour's far end.
  4. Exit at the stop (a gap through it fills at the open) or the session's last close. One trade per session.
"""
# AUGUR-SOURCE: claude-review
import numpy as np
import pandas as pd

STRATEGY_NAME = "TTM COMPBRK NQH1 1.0 - first hourly inside bar, trend-side break"
DESCRIPTION = ("First 1h inside bar (10:30-13:30 ET) broken by a tick in the daily SMA50 trend direction; stop at the "
               "inside bar's far end, hold to the close.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "15m"}

DEFAULT_PARAMS = {
    "sma_len": {"default": 50, "min": 20, "max": 100, "step": 10, "type": "int",
                "label": "Daily trend SMA (sessions)", "tooltip": "Harness 50."},
    "h_start": {"default": 630, "min": 600, "max": 690, "step": 30, "type": "int",
                "label": "First inside hour (min ET)", "tooltip": "630 = 10:30 hour."},
    "h_end": {"default": 810, "min": 720, "max": 840, "step": 30, "type": "int",
              "label": "Last inside hour (min ET)", "tooltip": "810 = 13:30 hour."},
    "entry_end": {"default": 900, "min": 810, "max": 945, "step": 15, "type": "int",
                  "label": "No entry at/after (min ET)", "tooltip": "900 = 15:00."},
    "tick_buf": {"default": 1, "min": 0, "max": 8, "step": 1, "type": "int",
                 "label": "Break buffer (ticks)", "tooltip": "Harness 1 tick = 0.25 pt."},
}

PARAM_GRID_PRESETS = {"Short (harness H1)": {k: [v["default"]] for k, v in DEFAULT_PARAMS.items()}}

TICK = 0.25


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 sma_len=50, h_start=630, h_end=810, entry_end=900, tick_buf=1,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 200 or index is None:
        return None
    idx = pd.DatetimeIndex(index)
    et = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    mins = np.asarray(et.hour * 60 + et.minute); day = et.normalize(); ar = np.arange(n)
    g = pd.DataFrame({"d": day, "c": c, "i": ar}).groupby("d")
    D = pd.DataFrame({"c": g.c.last(), "f": g.i.min(), "e": g.i.max()})
    tr = np.sign(D.c - D.c.rolling(int(sma_len)).mean()).shift(1)
    hr = et.floor("h")
    G = pd.DataFrame({"hr": hr, "h": h, "l": l, "i": ar}).groupby("hr").agg(h=("h", "max"), l=("l", "min"), e=("i", "max"))
    G["d"] = G.index.normalize(); G["m"] = G.index.hour * 60 + G.index.minute
    G["ins"] = (G.h <= G.h.shift(1)) & (G.l >= G.l.shift(1)) & (G.d == G.d.shift(1))
    C = G[G.ins & (G.m >= int(h_start)) & (G.m <= int(h_end))].groupby("d").head(1).set_index("d")
    buf = float(tick_buf) * TICK; ee = int(entry_end)
    pnl, log = [], []
    for k_, d in enumerate(D.index):
        if k_ < 60 or d not in C.index:
            continue
        s = tr.iloc[k_]
        if not np.isfinite(s) or s == 0:
            continue
        s = int(s); r0 = C.loc[d]; e = int(D.e.iloc[k_]); start = int(r0.e) + 1
        lvl = r0.h + buf if s > 0 else r0.l - buf; stop = r0.l if s > 0 else r0.h
        j = None
        for k in range(start, e + 1):
            if mins[k] >= ee:
                break
            if (s > 0 and h[k] >= lvl) or (s < 0 and l[k] <= lvl):
                j = k; break
        if j is None:
            continue
        en = max(lvl, o[j]) if s > 0 else min(lvl, o[j])
        if s * (en - stop) <= 0:
            continue
        ex, xi = c[e], e
        for k in range(j, e + 1):
            if k > j and ((s > 0 and o[k] <= stop) or (s < 0 and o[k] >= stop)):
                ex, xi = o[k], k; break
            if (s > 0 and l[k] <= stop) or (s < 0 and h[k] >= stop):
                ex, xi = stop, k; break
        p = s * (ex - en); pnl.append(p)
        if return_trades:
            log.append((int(j), int(xi), float(p), int(s), float(en)))
        if _stop_event is not None and _stop_event.is_set():
            return None
    if not pnl:
        return None
    p = np.array(pnl); w = p[p > 0]; ls = p[p < 0]; cum = np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)), "win_rate": float(100 * len(w) / len(p)),
           "profit_factor": float(w.sum() / -ls.sum()) if len(ls) else float("inf"),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()), "avg_pnl": float(p.mean()),
           "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = log
    return out

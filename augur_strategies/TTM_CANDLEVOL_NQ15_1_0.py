"""
TTM CANDLEVOL NQ15 1.0 - strong candle + relative volume, daily-trend side only, NQ 15m RTH. Family TTM.

ORIGIN (w119 owner hunt 11-09, w132 loose screen 11-14, lane TTM). Preregs:
  C:/EdgeLog/manager/prereg/PREREG_ttm_candlevol_es15_2026-11-09.md (rules, frozen before numbers)
  C:/EdgeLog/manager/prereg/PREREG_ttm_w132_candlevol_nq15_2026-11-14.md (NQ transfer)
Harness C:/EdgeLog/_anatomy_cache/ttm_w119/w132nq_gate.py, arm T2, WF 2016-07..2025-06 at 0.783 pt:
489 trades (54/yr), gross 7.49 pt/trade vs random-entry 0.21 (p 0.000 over 200 draws), $7,294/yr, 6 of 8 folds +.
Parity at file defaults = harness arm T2.

RULE (finished bars only):
  1. Daily trend = sign(prior session's last close - SMA(sma_len) of prior session closes). Up = long only.
  2. Signal bar starts between win_start and win_end (minutes ET) and is not the session's last bar:
     body/range >= body_min, close in the top loc_min of the range (long; mirror for short), bar coloured with the
     trend, relative volume = bar volume / mean of the same-time bar over the prior 20 sessions >= relv_min.
  3. Entry at the next bar's open. Stop = the signal bar's far end (1R). Target = entry + target_R x risk.
     Time stop: flat at the close of the first bar starting at or after time_stop_min, else the session's last bar.
     Gaps through stop/target fill at the open. One trade at a time.
"""
# AUGUR-SOURCE: claude-review
import numpy as np
import pandas as pd

STRATEGY_NAME = "TTM CANDLEVOL NQ15 1.0 - strong candle + volume with the daily trend"
DESCRIPTION = ("Strong-bodied 15m bar closing at its extreme on 1.5x same-time volume, in the daily SMA50 trend "
               "direction; enter next open, stop at the bar's far end, 2R target, flat by 15:30.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "15m"}

DEFAULT_PARAMS = {
    "body_min": {"default": 0.6, "min": 0.4, "max": 0.8, "step": 0.05, "type": "float",
                 "label": "Min body / range", "tooltip": "Harness 0.6."},
    "loc_min": {"default": 0.75, "min": 0.6, "max": 0.9, "step": 0.05, "type": "float",
                "label": "Close location (top share)", "tooltip": "Long: close in the top (1-loc_min) of the bar. Harness 0.75."},
    "relv_min": {"default": 1.5, "min": 1.0, "max": 2.5, "step": 0.1, "type": "float",
                 "label": "Min relative volume", "tooltip": "Bar volume / same-time mean of 20 prior sessions. Harness 1.5."},
    "target_R": {"default": 2.0, "min": 1.0, "max": 4.0, "step": 0.5, "type": "float",
                 "label": "Target (x risk)", "tooltip": "Harness T2 = 2.0."},
    "sma_len": {"default": 50, "min": 20, "max": 100, "step": 10, "type": "int",
                "label": "Daily trend SMA (sessions)", "tooltip": "Harness 50."},
    "win_start": {"default": 600, "min": 585, "max": 660, "step": 15, "type": "int",
                  "label": "First signal bar (min ET)", "tooltip": "600 = 10:00."},
    "win_end": {"default": 795, "min": 720, "max": 870, "step": 15, "type": "int",
                "label": "Last signal bar (min ET)", "tooltip": "795 = 13:15."},
    "time_stop_min": {"default": 930, "min": 870, "max": 945, "step": 15, "type": "int",
                      "label": "Time stop bar (min ET)", "tooltip": "930 = 15:30 bar close."},
}

PARAM_GRID_PRESETS = {"Short (harness T2)": {k: [v["default"]] for k, v in DEFAULT_PARAMS.items()}}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 body_min=0.6, loc_min=0.75, relv_min=1.5, target_R=2.0, sma_len=50,
                 win_start=600, win_end=795, time_stop_min=930,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 200 or index is None or volumes is None:
        return None
    v = np.asarray(volumes, float)
    idx = pd.DatetimeIndex(index)
    et = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    mins = np.asarray(et.hour * 60 + et.minute); day = et.normalize()
    dc = pd.Series(c, index=day).groupby(level=0).last()
    trend = np.sign(dc - dc.rolling(int(sma_len)).mean()).shift(1)
    tr = trend.reindex(day).values
    rv = pd.DataFrame({"m": mins, "v": v})
    avg = rv.groupby("m").v.transform(lambda s: s.shift(1).rolling(20).mean()).values
    with np.errstate(divide="ignore", invalid="ignore"):
        relv = v / avg
    rng_ = h - l; pos = rng_ > 0; safe = np.where(pos, rng_, 1.0)
    body = np.where(pos, np.abs(c - o) / safe, 0.0); loc = np.where(pos, (c - l) / safe, 0.5)
    dv = day.values; nxt_same = np.r_[dv[1:] == dv[:-1], False]
    lm = float(loc_min)
    win = (mins >= int(win_start)) & (mins <= int(win_end)) & nxt_same & np.isfinite(tr) & (tr != 0)
    sig = win & (body >= float(body_min)) & (relv >= float(relv_min)) & \
        (((tr > 0) & (loc >= lm) & (c > o)) | ((tr < 0) & (loc <= 1 - lm) & (c < o)))
    tR, ts = float(target_R), int(time_stop_min)
    pnl, log = [], []; last = -1
    for i in np.flatnonzero(sig):
        if i <= last:
            continue
        s = int(tr[i]); j = i + 1; en = o[j]; stop = l[i] if s > 0 else h[i]; risk = abs(en - stop)
        if risk <= 0 or s * (en - stop) <= 0:
            continue
        tgt = en + s * tR * risk; k = j
        while True:
            if (s > 0 and l[k] <= stop) or (s < 0 and h[k] >= stop):
                ex = min(stop, o[k]) if s > 0 else max(stop, o[k]); break
            if (s > 0 and h[k] >= tgt) or (s < 0 and l[k] <= tgt):
                ex = max(tgt, o[k]) if s > 0 else min(tgt, o[k]); break
            if mins[k] >= ts or not nxt_same[k]:
                ex = c[k]; break
            k += 1
        p = s * (ex - en); pnl.append(p); last = k
        if return_trades:
            log.append((int(j), int(k), float(p), int(s), float(en)))
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

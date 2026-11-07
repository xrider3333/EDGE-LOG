"""
PCB 1.0 - PRIOR-CLOSE BREAK (was "GAPGO break", renamed PCB by the owner 11-07). Family PCB. NQ 5m ETH no-adj.

ORIGIN: MANAGER #155/#158/#160, lane ORB. Prereg C:/EdgeLog/manager/prereg/PREREG_gapgo_break_r2_2026-11-07.md, arm A.
r2 (fixed rule, 2010-06-07..2025-08-12) read gross 1.43 pts/trade, BELOW the 3.0 power bar; the owner asked for a full
validate anyway (MANAGER #160).

RULE (all on finished bars):
  1. Prior close = the last RTH (09:30-16:00 ET) bar close of the previous session.
  2. Premarket range = high/low of the 04:00-09:30 ET bars. The opening range is 09:30-09:40, so the first trigger bar is
     the one starting at 09:40 (earliest_min).
  3. LONG at the close of the first bar whose close is above the premarket high OR above the running session high, AND
     above the prior close. SHORT is the mirror. One trade per session. No entry at or after latest_min.
  4. Stop = the prior close (pinned - the defining idea). Breakeven: once a bar closes at entry + be_R x risk, the stop
     moves to entry from the next bar. Target = entry + target_R x risk. Flat at the last RTH bar.
  5. Short sessions (fewer than 70% of the median RTH bars) and roll-seam sessions (the audited calendar) are skipped.
     The no-adj prior close on a seam day belongs to the old contract.
"""
# AUGUR-SOURCE: claude-review
import numpy as np
import pandas as pd

from augur_engine.rolls import seam_days as detect_roll_seams

STRATEGY_NAME = "PCB 1.0 - prior-close break"
DESCRIPTION = ("Above yesterday's RTH close, a close through the premarket high or the session high goes long (mirror "
               "short). Stop at the prior close, breakeven and target in R, flat at the close.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
ROLL_SIGNAL = "raw"

DEFAULT_PARAMS = {
    "be_R": {"default": 0.5, "min": 0.25, "max": 1.0, "step": 0.25, "type": "float",
             "label": "Breakeven after (x risk)", "tooltip": "r2 used 0.5 (#314's exit)."},
    "target_R": {"default": 5.0, "min": 2.0, "max": 8.0, "step": 0.5, "type": "float",
                 "label": "Target (x risk)", "tooltip": "r2 used 5.0 (#314's exit)."},
    "earliest_min": {"default": 580, "min": 580, "max": 600, "step": 5, "type": "int",
                     "label": "Earliest trigger bar (minutes after midnight ET)", "tooltip": "580 = 09:40."},
    "latest_min": {"default": 955, "min": 600, "max": 955, "step": 15, "type": "int",
                   "label": "No entry at/after (minutes ET)", "tooltip": "r2: before 10:00 held all the edge; 955 = off."},
}

PARAM_GRID_PRESETS = {"Short (r2 arm A)": {"be_R": [0.5], "target_R": [5.0], "earliest_min": [580], "latest_min": [955]}}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 be_R=0.5, target_R=5.0, earliest_min=580, latest_min=955,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float); l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 200 or index is None:
        return None
    idx = pd.DatetimeIndex(index)
    et = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    mins = np.asarray(et.hour * 60 + et.minute); day = np.asarray(et.normalize())
    rth = np.flatnonzero((mins >= 570) & (mins < 960))
    if not len(rth):
        return None
    ud, st = np.unique(day[rth], return_index=True)
    ends = np.r_[st[1:], len(rth)]
    med = np.median(ends - st)
    d_open = np.array([o[rth[a]] for a in st]); d_close = np.array([c[rth[b - 1]] for b in ends])
    seam = set(detect_roll_seams(d_open, d_close, [idx[rth[a]] for a in st]))
    pm = (mins >= 240) & (mins < 570)
    pmh, pml = {}, {}
    for k in np.flatnonzero(pm):
        dk = day[k]
        pmh[dk] = max(pmh.get(dk, -np.inf), h[k]); pml[dk] = min(pml.get(dk, np.inf), l[k])
    be_R, target_R = float(be_R), float(target_R); e_min, l_min = int(earliest_min), int(latest_min)
    pnl, log = [], []
    for s in range(1, len(ud)):
        a, b = st[s], ends[s]
        r = rth[a:b]
        d = ud[s]
        if s in seam or b - a < 0.70 * med or d not in pmh:
            continue
        pc = d_close[s - 1]; ph, pl = pmh[d], pml[d]
        k0 = int(np.sum(mins[r] < e_min))
        if k0 < 1 or len(r) - k0 < 2:
            continue
        ek = side = None
        rh, rl = h[r[:k0]].max(), l[r[:k0]].min()
        for k in range(k0, len(r) - 1):
            i = r[k]
            if mins[i] >= l_min:
                break
            if (c[i] > ph or c[i] > rh) and c[i] > pc:
                ek, side = k, 1; break
            if (c[i] < pl or c[i] < rl) and c[i] < pc:
                ek, side = k, -1; break
            rh, rl = max(rh, h[i]), min(rl, l[i])
        if ek is None:
            continue
        ep = c[r[ek]]; risk = abs(ep - pc)
        if risk <= 0:
            continue
        stp, be_l, tg = ep - side * risk, ep + side * be_R * risk, ep + side * target_R * risk
        armed, px, xi = False, None, r[-1]
        for k in range(ek + 1, len(r)):
            i = r[k]
            if armed:
                stp = max(stp, ep) if side > 0 else min(stp, ep)
            if side * ((l[i] if side > 0 else h[i]) - stp) <= 0:
                px = o[i] if side * (o[i] - stp) < 0 else stp; xi = i; break
            if not armed and side * (c[i] - be_l) >= 0:
                armed = True
            if side * ((h[i] if side > 0 else l[i]) - tg) >= 0:
                px = tg; xi = i; break
        if px is None:
            px = c[r[-1]]
        p = side * (px - ep)
        pnl.append(p)
        if return_trades:
            log.append((int(r[ek]), int(xi), float(p), int(side), float(ep)))
        if _stop_event is not None and _stop_event.is_set():
            return None
    if not pnl:
        return None
    p = np.array(pnl); w = p[p > 0]; ls = p[p < 0]
    cum = np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)), "win_rate": float(100 * len(w) / len(p)),
           "profit_factor": float(w.sum() / -ls.sum()) if len(ls) else float("inf"),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()), "avg_pnl": float(p.mean()),
           "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = log
    return out

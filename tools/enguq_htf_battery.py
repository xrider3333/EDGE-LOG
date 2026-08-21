"""BATTERY V -- HTF / momentum-quality confirmation gates on ENGU-Q (owner-directed hunt,
2026-08-21: "price action or indicator confirmation from higher timeframes, or params
taken from other momentum strategies (NOISE)").

PRE-REGISTERED before any result is read. A gate cell is PROMISING only if, versus its
MATCHED entry control (raw #226 or the adopted limit-0.50), ALL hold:
  P1  PF >= control PF + 0.02          (a real quality lift, not rounding)
  P2  lockbox PF >= control lockbox PF
  P3  lockbox net >= control lockbox net
  P4  net >= 85% of control net        (a filter may trim, not gut)
  P5  stuck guard: longest hold <= 120d AND >= 40 lockbox trades
Judged on PF + lockbox per edgelog-netdd-unreliable. Adjacent prior art, stated honestly:
the daily-SMA regime gate died 0-for-5 (battery U) by removing winners faster than
losers. These gates are DIFFERENT in kind -- they measure the QUALITY of the move at the
signal (efficiency, expansion, HTF alignment), not the level of a long trend average --
but the burden of proof is on them.

Engine: exact copy of ENGUQ_1M_ETH_LIM_1_0.run_backtest with ONE addition -- an `allow`
boolean mask consulted after every parent filter. allow=None must reproduce the certified
numbers exactly (raw $434,721.12 / limit-0.50 $513,007.57) or the battery is void.

Gates (every input is trailing data through bar i, nothing later):
  vwap    close above the session's volume-weighted average price
  er60_25 / er60_35   Kaufman efficiency ratio of the last 60 bars >= 0.25 / 0.35
  mom15 / mom60       close above the close 15 / 60 minutes ago
  atrx    14-bar ATR at least 1.1x the 106-bar ATR (volatility expansion, NOISE-style)
  hl15    the last 15-bar low sits above the prior 15-bar window's low (higher lows)
"""
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(tl_len=170, vol_mult=0.8, stop_mult=1.0, act_R=2.5, trail_frac=2.5,
            buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106, breakeven_R=1.5)
N_SCAN = 10
OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15"
       r"\scratchpad\htf_battery.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o = arr["open"]; h = arr["high"]; l = arr["low"]; c = arr["close"]
v = np.asarray(arr["volume"], float); day = np.asarray(arr["day_id"])
idx = arr["index"]; n = len(c)


def _ema(a, ln):
    k = 2.0 / (ln + 1.0)
    out = np.empty_like(a)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def engine(allow=None, limit_atr=0.0, tl_len=170, vol_mult=0.8, stop_mult=1.0,
           act_R=2.5, trail_frac=2.5, buf_atr=0.9, min_brk=1.3, ema_len=1380,
           atr_len=106, breakeven_R=1.5):
    """ENGUQ_1M_ETH_LIM_1_0.run_backtest verbatim + the allow-mask; returns trade list."""
    tl_len = int(tl_len)
    ema = _ema(c, int(ema_len))
    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); al = int(atr_len)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    vavg = np.full(n, np.nan); w = 20
    vc = np.cumsum(v); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w
    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()

    trades = []
    pos = None
    i = tl_len + 1
    while i < n:
        if pos is not None:
            if h[i] - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                trades.append((pos["bar"], i, fill - pos["ep"], 1, pos["ep"]))
                pos = None
            i += 1
            continue
        if c[i] <= o[i] or not c[i] > ema[i]:
            i += 1; continue
        if vol_mult > 0 and not (not np.isnan(vavg[i]) and v[i] >= vol_mult * vavg[i]):
            i += 1; continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            i += 1; continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            i += 1; continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            i += 1; continue
        if allow is not None and not allow[i]:      # <-- the ONLY addition
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()
        if limit_atr <= 0:
            risk = c[i] - swing_low
            if risk < 0.5:
                i += 1; continue
            pos = {"bar": i, "ep": c[i], "risk": risk,
                   "sl": c[i] - stop_mult * risk, "act": False}
            i += 1; continue
        limit = c[i] - limit_atr * a
        jmax = min(i + N_SCAN, n - 1)
        fill_j = None
        for j in range(i + 1, jmax + 1):
            if l[j] <= limit:
                fill_price = min(limit, o[j]); fill_j = j
                break
        if fill_j is None:
            i += 1; continue
        risk = fill_price - swing_low
        if risk < 0.5:
            i = fill_j + 1; continue
        pos = {"bar": fill_j, "ep": fill_price, "risk": risk,
               "sl": fill_price - stop_mult * risk, "act": False}
        i = fill_j + 1
        continue
    if pos is not None:
        trades.append((pos["bar"], n - 1, c[-1] - pos["ep"], 1, pos["ep"]))
    return trades


def stats(trades):
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ent = pd.to_datetime([idx[int(t[0])] for t in trades]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in trades]).tz_localize(None)
    cum = np.cumsum(d)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lb = d[ent >= pd.Timestamp(LB_START)]
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    hold = (ext - ent).total_seconds() / 86400.0
    return dict(n=len(d), net=float(d.sum()), dd=dd, pf=float(pf),
                lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf),
                hold=float(hold.max()))


# ── gate masks (trailing data only) ─────────────────────────────────────────────────
print("building masks ...", flush=True)
masks = {}

pv = np.cumsum(c * v); vv_ = np.cumsum(v)
day_start = np.zeros(n, dtype=int)
s0 = 0
for i in range(1, n):
    if day[i] != day[i - 1]:
        s0 = i
    day_start[i] = s0
pv0 = np.where(day_start > 0, pv[np.maximum(day_start - 1, 0)], 0.0)
vv0 = np.where(day_start > 0, vv_[np.maximum(day_start - 1, 0)], 0.0)
den = vv_ - vv0
vwap = np.where(den > 0, (pv - pv0) / np.maximum(den, 1e-9), c)
masks["vwap"] = c > vwap

for L, th, nm in ((60, 0.25, "er60_25"), (60, 0.35, "er60_35")):
    chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
    ad = np.abs(np.diff(c, prepend=c[0]))
    cs = np.cumsum(ad)
    vol_sum = cs - np.concatenate([np.zeros(L), cs[:-L]])
    er = np.where(vol_sum > 0, chg / np.maximum(vol_sum, 1e-9), 0.0)
    masks[nm] = np.nan_to_num(er) >= th

masks["mom15"] = c > np.concatenate([np.full(15, np.inf), c[:-15]])
masks["mom60"] = c > np.concatenate([np.full(60, np.inf), c[:-60]])

tr_ = np.empty(n); tr_[0] = h[0] - l[0]
for i in range(1, n):
    tr_[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
cs = np.cumsum(tr_)
atr14 = np.full(n, np.nan); atr14[13:] = (cs[13:] - np.concatenate([[0], cs[:-14]])) / 14
atr106 = np.full(n, np.nan); atr106[105:] = (cs[105:] - np.concatenate([[0], cs[:-106]])) / 106
masks["atrx"] = np.nan_to_num(atr14 / np.maximum(atr106, 1e-9)) >= 1.1

lo15 = pd.Series(l).rolling(15).min().values
prev15 = np.concatenate([np.full(15, -np.inf), lo15[:-15]])
masks["hl15"] = np.nan_to_num(lo15, nan=-np.inf) > prev15

# ── parity, then the sweep ──────────────────────────────────────────────────────────
print("parity ...", flush=True)
ctl_raw = stats(engine(None, 0.0, **CERT))
ctl_l50 = stats(engine(None, 0.5, **CERT))
print("  raw :", {k: round(vv, 3) if isinstance(vv, float) else vv for k, vv in ctl_raw.items()})
print("  l50 :", {k: round(vv, 3) if isinstance(vv, float) else vv for k, vv in ctl_l50.items()})
ok = (ctl_raw["n"] == 2843 and abs(ctl_raw["net"] - 434721.12) < 1.0
      and ctl_l50["n"] == 2924 and abs(ctl_l50["net"] - 513007.57) < 1.0)
print("  PARITY:", "PASS" if ok else "FAIL")
if not ok:
    sys.exit(1)

rows = {"ctl_raw": ctl_raw, "ctl_l50": ctl_l50}
for gname, m in masks.items():
    for lim, ctl, tag in ((0.0, ctl_raw, "raw"), (0.5, ctl_l50, "l50")):
        s = stats(engine(m, lim, **CERT))
        g = dict(P1=s["pf"] >= ctl["pf"] + 0.02, P2=s["lb_pf"] >= ctl["lb_pf"],
                 P3=s["lb_net"] >= ctl["lb_net"], P4=s["net"] >= 0.85 * ctl["net"],
                 P5=s["hold"] <= 120 and s["lb_n"] >= 40)
        s["gates"] = g
        rows["%s_%s" % (gname, tag)] = s
        print(f"  {gname:8s} {tag}: n={s['n']:5d} net=${s['net']:10,.0f} DD=${s['dd']:8,.0f} "
              f"PF={s['pf']:.3f} LB=${s['lb_net']:8,.0f} (n={s['lb_n']}, PF={s['lb_pf']:.3f}) "
              f"-> {'PROMISING' if all(g.values()) else 'fail ' + ''.join(k for k, ok_ in g.items() if not ok_)}",
              flush=True)

json.dump(rows, open(OUT, "w"), indent=1, default=float)
print("SAVED ->", OUT)

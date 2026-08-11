"""Price ENGU-Q's MILD same-bar trail assumption (found in the 2026-08-11 audit).

The engine raises the trailing stop / breakeven using bar i's HIGH and then checks
bar i's LOW against that freshly-raised stop in the same iteration — assuming the
high printed before the low. A live stop order (the NT port) only moves at bar
close, so intrabar spike-up-then-down days exit at the PREVIOUS bar's stop level.

This runs the #149 champion twice on the same data:
  ENGINE : trail/BE updated from THIS bar's high, checked against this bar's low
  LAGGED : trail/BE updated from the PREVIOUS bar's high (what a real resting
           stop order can do), checked against this bar's low

The gap = the honest cost of the assumption. Expected: small (unlike ORB).

Run:  python3.13.exe tools/enguq_trail_lag.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_strategies.ENGUQ_1M_1_0 import NQ_DEPLOY_PARAMS_149, _ema  # noqa: E402

MULT, COST_PTS = 20.0, 0.533
P = dict(NQ_DEPLOY_PARAMS_149)


def sim(o, h, l, c, v, lagged):
    tl_len = int(P["tl_len"]); ema_len = int(P["ema_len"])
    buf_atr = P["buf_atr"]; min_brk = P["min_brk"]; atr_len = int(P["atr_len"])
    vol_mult = P["vol_mult"]; stop_mult = P["stop_mult"]
    act_R = P["act_R"]; trail_frac = P["trail_frac"]; be_R = P["breakeven_R"]
    n = len(c)
    ema = _ema(c, ema_len)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan)
    cs = np.cumsum(tr)
    atr[atr_len - 1:] = (cs[atr_len - 1:] - np.concatenate([[0], cs[:-atr_len]])) / atr_len
    atr = np.where(np.isnan(atr), tr, atr)
    vv = np.asarray(v, float)
    vavg = np.full(n, np.nan); w = 20
    vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl = []
    pos = None
    for i in range(tl_len + 1, n):
        if pos is not None:
            # reference high for trail/BE: engine = THIS bar's high; lagged = PREVIOUS bar's
            ref_h = h[i - 1] if lagged else h[i]
            if ref_h - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], ref_h - trail_frac * pos["risk"])
            if be_R > 0 and (ref_h - pos["ep"]) >= be_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl.append(fill - pos["ep"])
                pos = None
            continue
        if c[i] <= o[i] or not c[i] > ema[i]:
            continue
        if vol_mult > 0 and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            continue
        risk = c[i] - l[i - tl_len:i + 1].min()
        if risk < 0.5:
            continue
        pos = {"ep": c[i], "risk": risk, "sl": c[i] - stop_mult * risk, "act": False}
    if pos is not None:
        pnl.append(c[-1] - pos["ep"])
    return np.array(pnl)


def main():
    master = find_master("NQ", "1m", "rth")
    arr = load_master_arrays(master, date_from=None, date_to=None)
    o, h, l, c, v = arr["open"], arr["high"], arr["low"], arr["close"], arr["volume"]
    idx = arr["index"]
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    print(f"NQ 1m RTH  {idx[0].date()} -> {idx[-1].date()}  ({years:.1f}y)   params = #149 + BE 1.5")
    for label, lagged in (("ENGINE (same-bar high)", False), ("LAGGED (prev-bar high)", True)):
        p = sim(o, h, l, c, v, lagged)
        net = float((p - COST_PTS).sum()) * MULT
        w_ = p[p > 0]; lo = p[p < 0]
        pf = float(w_.sum()) / max(abs(float(lo.sum())), 1e-9)
        print(f"  {label:<24} n={len(p):>5,}  net ${net:>10,.0f}  (${net/years:,.0f}/yr)  PF {pf:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

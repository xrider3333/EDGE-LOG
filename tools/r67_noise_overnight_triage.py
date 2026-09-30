# -*- coding: utf-8 -*-
"""NOISE ROUND 67 - the break must clear the overnight extreme (docs/PREREG_noise_r67_overnight_2026-09-30.md).

OVERNIGHT = every ETH bar from the previous RTH session's 16:00 to this session's 09:30 (complete before the open). A
long is CLEARED when the signal bar's close is above the overnight high, a short when below the overnight low;
uncleared signals are skipped INSIDE the strategy (NOISE_1_0.py source patched in memory at the entry step, nothing on
disk changes), so the flat slot can take a later cleared break. Neighbours: the level moved out / in by 10% of the
overnight range. Run WITHOUT the trial cache (patched copies). Round 63/65/66 harness and owner yardstick.

  python tools/r67_noise_overnight_triage.py  -> tools/r37_results/r67_overnight.txt
"""
import os
import sys
import types

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

COST, M, ACCT = 0.533, 20.0, 100000.0
LAST = "2026-09-16"
WF0, LB0, LB1 = (pd.Timestamp(x).date() for x in ("2016-06-30", "2025-07-16", "2026-07-16"))
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
IDX = pd.DatetimeIndex(A["index"])
O, H, L, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
DATE = np.array(IDX.date)
SRC_PATH = os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py")
SRC = open(SRC_PATH, encoding="utf-8").read()


def build(esc=None):
    s = SRC
    if esc is not None:
        anchor = "                    if long_trig and short_trig:\n"
        assert s.count(anchor) == 1, "entry anchor not unique"
        patch = ("                    long_trig = long_trig and bool(_ESC_L[a + k])\n"
                 "                    short_trig = short_trig and bool(_ESC_S[a + k])\n")
        s = s.replace(anchor, patch + anchor)
    m = types.ModuleType("noise_r67_%s" % ("plain" if esc is None else "esc"))
    m.__file__ = SRC_PATH
    exec(compile(s, SRC_PATH, "exec"), m.__dict__)
    if esc is not None:
        m._ESC_L, m._ESC_S = esc
    return m


# ---- the overnight range per RTH session, from the ETH master ------------------------------------------------------
EA = load_master_arrays(find_master("NQ", "5m", "eth", "db_noadj_eth"), date_from="2010-06-01", date_to=LAST)
ET = pd.DatetimeIndex(EA["index"]).tz_convert("America/New_York")
EH, EL = np.asarray(EA["high"], float), np.asarray(EA["low"], float)
ETN = ET.asi8
_rth = pd.DatetimeIndex(IDX).tz_convert("America/New_York")
_days = pd.DatetimeIndex(sorted(set(_rth.normalize())))
ONH = pd.Series(np.nan, index=_days)
ONL = pd.Series(np.nan, index=_days)
for i in range(1, len(_days)):
    t0 = (_days[i - 1] + pd.Timedelta(hours=16)).value
    t1 = (_days[i] + pd.Timedelta(hours=9, minutes=30)).value
    lo, hi = np.searchsorted(ETN, t0, "left"), np.searchsorted(ETN, t1, "left")
    if hi > lo:
        ONH.iloc[i] = EH[lo:hi].max()
        ONL.iloc[i] = EL[lo:hi].min()
BAR_ONH = ONH.reindex(_rth.normalize()).to_numpy()
BAR_ONL = ONL.reindex(_rth.normalize()).to_numpy()


def on_clear(frac):
    """(cleared_long, cleared_short) per RTH bar: close beyond the overnight extreme moved out by frac x range."""
    rng = BAR_ONH - BAR_ONL
    with np.errstate(invalid="ignore"):
        cl = C > BAR_ONH + frac * rng
        cs = C < BAR_ONL - frac * rng
    ok = np.isfinite(rng)
    return (cl & ok, cs & ok)


CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
BASES = [("NOISE #304 crown", CROWN), ("NOISE #243 retired", dict(CROWN, lookback=44, vol_skip_pct=90.0))]


def trades(module, params):
    r = run_backtest(module, arrays=A, params=params, cost_pts=COST, return_trades=True)
    return sorted(r["trades"], key=lambda z: int(z[0]))


def stats(pairs, a, b):
    k = np.array([p[0] for p in pairs], int)
    v = np.array([p[1] for p in pairs], float) * M
    d = DATE[np.maximum(k - 1, 0)]
    m = (d >= a) & ((d < b) if b is not None else np.ones(len(d), bool))
    q, dq = v[m], d[m]
    if not len(q):
        return None
    y = (pd.Timestamp(b or LAST) - pd.Timestamp(a)).days / 365.25
    daily = pd.Series(q).groupby(dq).sum().to_numpy()             # NOISE is flat by the close: day P&L is final
    cum = np.cumsum(daily)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    down = np.sqrt(np.mean(np.minimum(q, 0.0) ** 2))
    mar = (q.sum() / y) / dd if dd > 0 else 0.0
    return dict(n=len(q), net=float(q.sum()), dd=dd, roc=100 * q.sum() / y / ACCT, r30=30 * mar,
                so=(q.mean() / down) * np.sqrt(len(q) / y) if down > 0 else 0.0,
                ex1=float(q.sum() - q.max()))


def show(label, pairs):
    s = {nm: stats(pairs, a, b) for nm, a, b in (("WF", WF0, LB0), ("LB", LB0, LB1), ("tail", LB1, None))}
    w, l_, t = s["WF"], s["LB"], s["tail"]
    print("  %-32s WF %4d tr ROC@30k %5.1f%% Sort %4.2f (%5.1f%%/yr, DD $%6s) | LB %3d tr ROC@30k %5.1f%% Sort %4.2f "
          "(%5.1f%%/yr, DD $%6s, ex-top $%7s) | tail $%6s" % (
              label, w["n"], w["r30"], w["so"], w["roc"], format(int(w["dd"]), ","), l_["n"], l_["r30"], l_["so"],
              l_["roc"], format(int(l_["dd"]), ","), format(int(l_["ex1"]), ","),
              format(int(t["net"]), ",") if t else "0"))
    return s


def judge(name, s, twin, neighbours):
    ok = (s["WF"]["r30"] > twin["WF"]["r30"] and s["LB"]["r30"] > twin["LB"]["r30"]
          and s["WF"]["so"] > twin["WF"]["so"] and s["LB"]["so"] > twin["LB"]["so"]
          and s["WF"]["n"] >= 100 and s["LB"]["n"] >= 50 and s["LB"]["ex1"] > 0
          and all(nb["WF"]["r30"] > twin["WF"]["r30"] for nb in neighbours))
    why = []
    for st in ("WF", "LB"):
        if s[st]["r30"] <= twin[st]["r30"]:
            why.append("%s ROC@30k %.1f <= twin %.1f" % (st, s[st]["r30"], twin[st]["r30"]))
        if s[st]["so"] <= twin[st]["so"]:
            why.append("%s Sortino %.2f <= twin %.2f" % (st, s[st]["so"], twin[st]["so"]))
    if s["LB"]["ex1"] <= 0:
        why.append("LB loses without its biggest trade")
    if not all(nb["WF"]["r30"] > twin["WF"]["r30"] for nb in neighbours):
        why.append("a neighbour does not agree (spike, not plateau)")
    print("    -> %s: %s" % (name, "PASSES THE TRIAGE" if ok else "FAILS (" + "; ".join(why) + ")"))
    return ok


if __name__ == "__main__":
    plain = build()
    print("tape 2010-06-07 .. %s, cost %.3f, $%d/pt; ROC@30k = 30 x MAR with drawdown valued daily" % (LAST, COST, M))
    print("overnight range found for %.2f%% of RTH sessions" % (100 * np.isfinite(ONH.to_numpy()).mean()))
    verdict = {}
    for bname, params in BASES:
        t0 = trades(plain, params)
        allow = np.ones(len(IDX), bool)
        tp = trades(build(esc=(allow, allow)), params)                # the patch with every break allowed = plain
        assert [(int(x[0]), round(float(x[2]), 9)) for x in tp] == [(int(x[0]), round(float(x[2]), 9)) for x in t0], \
            "patched copy does not reproduce the plain strategy"
        print("")
        print("%s  (%d trades)" % (bname, len(t0)))
        cl, cs = on_clear(0.0)
        sg = np.array([int(x[0]) - 1 for x in t0])
        sd = np.array([int(np.sign(x[3])) for x in t0])
        print("  descriptive: %.1f%% of the plain breaks already clear the overnight extreme" % (100 * np.where(sd > 0, cl[sg], cs[sg]).mean()))
        raw = show("raw twin", [(int(x[0]), float(x[2])) for x in t0])
        res = {}
        for frac in (0.0, 0.1, -0.1):
            res[frac] = show("clears overnight %+.1f range%s" % (frac, "" if frac == 0.0 else " (neighbour)"),
                             [(int(x[0]), float(x[2])) for x in trades(build(esc=on_clear(frac)), params)])
        verdict[bname] = judge("clears overnight extreme", res[0.0], raw, [res[0.1], res[-0.1]])
    print("")
    print("OVERNIGHT CLEARANCE on BOTH bases: %s" % ("SURVIVES -> fenced Auto-Validate" if all(verdict.values()) else "DEAD - record it"))

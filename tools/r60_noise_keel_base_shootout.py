# -*- coding: utf-8 -*-
"""NOISE ROUND 60 - which base should KEEL v12 sit on? The live Webull leg against the alternatives.

Since 2026-09-24 the Webull NOISE leg trades run #382's pick (compression tilt: 30-minute squeeze, length 16,
threshold 1.15, 2.0x) with KEEL v12 on top. Round 55 measured that pick CONTINUOUSLY and it failed its own
pre-registered drawdown and MAR clauses (drawdown +43% vs the crown, loses to flat leverage in the sealed year).
KEEL v12 also carries its OWN hourly-squeeze 1.5x, so on #382 the compression bet is stacked twice.

Bases, each alone and with KEEL v12 walked on its own trades (the way every validate's KEEL row is built):
  #304 live crown raw | #382 pick (30-min 2.0x, the live base) | hourly squeeze 1.5x (round 55's pick, the
  centre of the queued CT304H validate) | hourly squeeze 1.25x.
One continuous tape 2010-06-07 .. 2026-09-16 (last Databento bar), cost 0.533, run #382's own stretches:
IS before 2016-06-30, WF 2016-06-30 .. 2025-07-16, LB from 2025-07-16. Reported per stretch: net, max drawdown,
MAR (annual net / drawdown), ROC %/yr on $100k, mean size, and the exposure-matched control - the crown traded
at the same mean size - because a stack that cannot beat that is leverage.

  python tools/r60_noise_keel_base_shootout.py  -> tools/r37_results/r60_keel_base_shootout.txt  (~15 min)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
from research_beacon import beacon                                    # noqa: E402

LAST = pd.Timestamp("2026-09-16").date()
WF0, LB0 = pd.Timestamp("2016-06-30").date(), pd.Timestamp("2025-07-16").date()
M, ACCT = 20.0, 100000.0
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07",
                      date_to=str(LAST))
IDX = pd.DatetimeIndex(A["index"])
END = IDX[-1].date()
print("tape 2010-06-07 .. %s (%d bars), Yahoo-appended sessions excluded" % (END, len(IDX)))


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
BASES = [
    ("#304 crown raw", "NOISE_1_0.py", CROWN),
    ("#382 pick 30-min 2.0x (LIVE base)", "NOISE_1_8_CT304.py",
     dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0)),
    ("hourly squeeze 1.5x (CT304H centre)", "NOISE_1_8_CT304H.py", dict(gate_len=20, gate_ratio=1.0, tilt_mult=1.5)),
    ("hourly squeeze 1.25x", "NOISE_1_8_CT304H.py", dict(gate_len=20, gate_ratio=1.0, tilt_mult=1.25)),
]


def yrs(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


STRETCH = [("IS", None, WF0), ("WF", WF0, LB0), ("LB", LB0, None)]
SPAN = {"IS": yrs("2010-06-07", WF0), "WF": yrs(WF0, LB0), "LB": yrs(LB0, END)}


def block(d, p):
    out = {}
    for nm, a, b in STRETCH:
        m = np.ones(len(d), bool)
        if a is not None:
            m &= d >= a
        if b is not None:
            m &= d < b
        q = p[m]
        cum = np.cumsum(q)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()) if len(q) else 0.0
        net = float(q.sum())
        out[nm] = dict(n=int(m.sum()), net=net, dd=dd, mar=(net / SPAN[nm]) / dd if dd > 0 else 0.0,
                       roc=100 * net / SPAN[nm] / ACCT)
    return out


rows = []
crown_pts = None
with beacon("NOISE r60 - KEEL base shoot-out", total=len(BASES)) as bc:
    for i, (name, fn, params) in enumerate(BASES, 1):
        r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=0.533, return_trades=True)
        trades = sorted(r["trades"], key=lambda z: z[0])
        kw = K.keel_walk(A, trades, version="v12")
        d = np.array([IDX[max(int(e) - 1, 0)].date() for e in kw["E"]])
        base_p = kw["P"] * M
        if crown_pts is None:
            crown_pts = (d, base_p)
        plug = r.get("trade_sizes")
        plug = np.asarray(plug, float) if plug is not None and len(plug) == len(base_p) else np.ones(len(base_p))
        rows.append((name, "alone", block(d, base_p), float(plug.mean())))
        rows.append((name, "+ KEEL v12", block(d, base_p * kw["size"]), float((plug * kw["size"]).mean())))
        bc.step(i)
        print("done:", name, "| trades", len(base_p), "| mean plugin size %.2f, mean KEEL size %.2f"
              % (plug.mean(), kw["size"].mean()), flush=True)

print("\n%-38s %-11s %5s | %-44s | %-44s" % ("base", "overlay", "size", "WF  net / DD / MAR / ROC%yr",
                                             "LB  net / DD / MAR / ROC%yr"))
for name, ov, b, sz in rows:
    w, l_ = b["WF"], b["LB"]
    print("%-38s %-11s %5.2f | $%9s  $%7s  %4.2f  %5.1f%% | $%8s  $%7s  %4.2f  %5.1f%%" % (
        name, ov, sz, format(int(w["net"]), ","), format(int(w["dd"]), ","), w["mar"], w["roc"],
        format(int(l_["net"]), ","), format(int(l_["dd"]), ","), l_["mar"], l_["roc"]))

print("\nEXPOSURE-MATCHED CONTROL: the crown traded at each row's mean size (flat leverage). MAR does not move with")
print("size, so the control's MAR is the crown's; the question is whether each stack's MAR beats it.")
cb = block(*crown_pts)
print("crown MAR  WF %.2f  LB %.2f" % (cb["WF"]["mar"], cb["LB"]["mar"]))
for name, ov, b, sz in rows[1:]:
    print("  %-38s %-11s WF MAR %4.2f (%s)   LB MAR %4.2f (%s)" % (
        name, ov, b["WF"]["mar"], "beats flat leverage" if b["WF"]["mar"] > cb["WF"]["mar"] else "LOSES to flat leverage",
        b["LB"]["mar"], "beats" if b["LB"]["mar"] > cb["LB"]["mar"] else "LOSES"))

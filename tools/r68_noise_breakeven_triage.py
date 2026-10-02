# -*- coding: utf-8 -*-
"""NOISE ROUND 68 - breakeven at +1R on a bar CLOSE, then ride (docs/PREREG_noise_r68_breakeven_2026-10-02.md).

Owner idea via MANAGER #21. R = fill price to the trade's own initial bandwidth stop. When a bar CLOSES with the open
trade >= BE_R x R in profit (the fill bar's close counts), the stop moves to the fill price for every LATER bar and is
checked exactly as the crown checks it. NOISE_1_0.py is patched IN MEMORY (nothing on disk changes) and re-simulated,
so a slot freed by a breakeven exit can take a later break. Legs keep their size rule (s x net per trade):
  NOISE #382 = 2.0x when the 30-minute compression gate (16, 1.15) is on at the decision bar (NOISE_1_8_CT304.py)
  NOISE #422 = 1.75x on the 60-minute gate (20, 1.15)                                          (NOISE_1_8_CT304H.py)
The rebuilt legs must reproduce those strategy files trade for trade first. Neighbours 0.5R / 1.5R.
OWNER YARDSTICK: ROC %/yr at a $30k worst drawdown = 30 x MAR, drawdown valued DAILY; WF and LB apart; beat the raw twin
(same leg, crown exit) on it AND Sortino in both; >= 100 WF / 50 LB trades; LB profitable without its biggest trade;
both neighbours beat the twin's WF ROC at $30k. Run WITHOUT the trial cache (patched copies).

  python tools/r68_noise_breakeven_triage.py  -> tools/r37_results/r68_breakeven.txt
"""
import importlib.util as ilu
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
H, L, C = (np.asarray(A[k], float) for k in ("high", "low", "close"))
DATE = np.array(IDX.date)
SRC_PATH = os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py")
SRC = open(SRC_PATH, encoding="utf-8").read()
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def load(fn):
    sp = ilu.spec_from_file_location(fn[:-3] + "_r68", os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


SQ = load("NOISE_1_1_SBS_V90_SQ.py")
LEGS = [("NOISE #382 (30-min gate 16/1.15, 2.0x)", "NOISE_1_8_CT304.py",
         dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0), (30, 16, 1.15, 2.0)),
        ("NOISE #422 (60-min gate 20/1.15, 1.75x)", "NOISE_1_8_CT304H.py",
         dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75), (60, 20, 1.15, 1.75))]


def build(be_r=None):
    s = SRC
    if be_r:
        anchor = "            # STEP C -- vwap/band exit trigger evaluated at THIS bar's close.\n"
        assert s.count(anchor) == 1, "STEP C anchor not unique"
        patch = ("            if pos != 0 and stop_level is not None and not np.isnan(stop_level):\n"
                 "                if _BE['k'] != a + entry_k:\n"
                 "                    _BE['k'] = a + entry_k; _BE['R'] = abs(entry_px - stop_level); _BE['moved'] = False\n"
                 "                if (not _BE['moved']) and _BE['R'] > 0 and (sc[k] - entry_px) * pos >= BE_R * _BE['R']:\n"
                 "                    stop_level = entry_px; _BE['moved'] = True; _BE['n'] += 1\n")
        s = s.replace(anchor, patch + anchor)
    m = types.ModuleType("noise_r68_%s" % be_r)
    m.__file__ = SRC_PATH
    exec(compile(s, SRC_PATH, "exec"), m.__dict__)
    m.BE_R = be_r
    m._BE = {"k": -1, "R": 0.0, "moved": False, "n": 0}
    return m


def trades(module):
    r = run_backtest(module, arrays=A, params=CROWN, cost_pts=COST, return_trades=True)
    return sorted(r["trades"], key=lambda z: int(z[0]))


def sized(tr, gate):
    """(fill bar, net points) with the leg's size rule; gate None = unsized #304."""
    if gate is None:
        return [(int(x[0]), float(x[2])) for x in tr]
    tf, ln, ratio, tilt = gate
    comp = SQ._compression(H, L, C, np.asarray(A["day_id"]), A["index"], tf, ln, ratio)
    out = []
    for x in tr:
        dec = int(x[0]) - 1
        s = tilt if (0 <= dec < len(C) and bool(comp[dec])) else 1.0
        out.append((int(x[0]), s * float(x[2])))
    return out


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
                so=(q.mean() / down) * np.sqrt(len(q) / y) if down > 0 else 0.0, ex1=float(q.sum() - q.max()))


def show(label, pairs):
    s = {nm: stats(pairs, a, b) for nm, a, b in (("WF", WF0, LB0), ("LB", LB0, LB1), ("tail", LB1, None))}
    w, l_, t = s["WF"], s["LB"], s["tail"]
    print("  %-26s WF %4d tr ROC@30k %5.1f%% Sort %4.2f (%5.1f%%/yr, DD $%6s) | LB %3d tr ROC@30k %5.1f%% Sort %4.2f "
          "(%5.1f%%/yr, DD $%6s, ex-top $%7s) | tail $%7s" % (
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
    print("tape 2010-06-07 .. %s, cost %.3f, $%d/pt; ROC@30k = 30 x MAR with drawdown valued daily" % (LAST, COST, M))
    t0 = trades(build())
    runs = {}
    for r in (1.0, 0.5, 1.5):
        mod = build(r)
        runs[r] = (trades(mod), mod._BE["n"])
    # the patch with an unreachable move must be the crown, trade for trade
    tp = trades(build(1e9))
    assert [(int(x[0]), int(x[1]), round(float(x[2]), 9)) for x in tp] == \
           [(int(x[0]), int(x[1]), round(float(x[2]), 9)) for x in t0], "patched copy does not reproduce the crown"
    be1 = runs[1.0][0]
    zero = sum(1 for x in be1 if abs(float(x[2]) + COST) < 1e-6)
    print("descriptive (#304 unsized): %d trades; the 1.0R move fired on %d of %d trades; %d exits at breakeven "
          "(net = -cost)" % (len(t0), runs[1.0][1], len(be1), zero))
    print("")
    print("NOISE #304 unsized (reference only)")
    show("crown exit", sized(t0, None))
    show("breakeven 1.0R", sized(be1, None))
    verdict = {}
    for name, fn, params, gate in LEGS:
        leg = load(fn)
        r = run_backtest(leg, arrays=A, params=params, cost_pts=COST, return_trades=True)
        ref = sorted([(int(x[0]), round(float(x[2]), 9)) for x in r["trades"]])
        mine = sorted([(k, round(v, 9)) for k, v in sized(t0, gate)])
        assert ref == mine, "%s: rebuilt leg does not reproduce %s" % (name, fn)
        print("")
        print("%s - rebuilt leg reproduces %s (%d trades)" % (name, fn, len(ref)))
        twin = show("raw twin (crown exit)", sized(t0, gate))
        res = {rr: show("breakeven %.1fR%s" % (rr, "" if rr == 1.0 else " (neighbour)"), sized(runs[rr][0], gate))
               for rr in (1.0, 0.5, 1.5)}
        verdict[name] = judge("breakeven 1.0R", res[1.0], twin, [res[0.5], res[1.5]])
    print("")
    print("BREAKEVEN AT +1R ON A CLOSE, on BOTH legs: %s" % (
        "SURVIVES -> fenced Auto-Validate" if all(verdict.values()) else "DEAD - record it"))

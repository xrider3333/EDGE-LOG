# -*- coding: utf-8 -*-
"""NOISE ROUND 63 - triage of the two pre-registered mechanisms (docs/PREREG_noise_r63_2026-09-28.md, commit 77298fc9).

  A  PYRAMID ON CONFIRMATION: add one contract at entry + 1.0 R in the trade's favour (R = entry to its own stop), riding
     the original exit. Neighbours 0.5 R / 1.5 R.
  B  HALF-HOUR DECISION CHECKPOINTS: new entries only on bars closing at HH:00 / HH:30. Neighbour: quarter-hour.

Both are built from NOISE_1_0.py's own source, patched IN MEMORY (nothing on disk changes): (a) each trade record also
carries its protective stop level, (b) the entry step gains a checkpoint condition. The stop-carrying copy must
reproduce the unpatched strategy trade for trade, or the script stops.

OWNER YARDSTICK: ROC %/yr at a $30k worst drawdown = 30 x MAR, drawdown valued DAILY; WF and LB apart; beat the raw twin
on it AND Sortino in both; >= 100 WF / 50 LB trades; LB profitable without its biggest trade; plateau neighbours agree.

  python tools/r63_noise_pyramid_checkpoint_triage.py  -> tools/r37_results/r63_triage.txt
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


def build(stop_tag=False, every=None):
    s = SRC
    if stop_tag:
        lines = s.split("\n")
        n = 0
        for i, ln in enumerate(lines):
            if "trade_log.append(" in ln and ln.rstrip().endswith("entry_px))"):
                lines[i] = ln.rstrip()[:-len("entry_px))")] + "entry_px, stop_level))"
                n += 1
        assert n >= 10, "stop tag patched only %d trade records" % n
        s = "\n".join(lines)
    if every:
        old = "                if in_window:\n"
        assert s.count(old) == 1, "entry-window anchor not unique"
        s = s.replace(old, "                if in_window and ((k + 1) %% %d == 0):\n" % every)
    m = types.ModuleType("noise_r63_%s_%s" % (int(stop_tag), every))
    m.__file__ = SRC_PATH
    exec(compile(s, SRC_PATH, "exec"), m.__dict__)
    return m


CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
BASES = [("NOISE #304 crown", CROWN), ("NOISE #243 retired", dict(CROWN, lookback=44, vol_skip_pct=90.0))]


def trades(module, params):
    r = run_backtest(module, arrays=A, params=params, cost_pts=COST, return_trades=True)
    return sorted(r["trades"], key=lambda z: int(z[0]))


def pyramid(tr, k):
    """Per-trade net points of base + add (entry + k*R), from the bars. Returns list of (entry_bar, pts)."""
    out = []
    for t in tr:
        ke, kx, net, side, epx, stop = int(t[0]), int(t[1]), float(t[2]), int(np.sign(t[3])), float(t[4]), t[5]
        tot = net
        if stop is not None and np.isfinite(stop) and abs(epx - stop) > 1e-9:
            R = abs(epx - float(stop))
            xpx = epx + side * (net + COST)
            last = kx - 1 if (kx > ke and abs(xpx - O[kx]) < 1e-9) else kx
            trig = epx + side * k * R
            for j in range(ke, last + 1):
                hit = (H[j] >= trig) if side > 0 else (L[j] <= trig)
                if hit:
                    gap = (O[j] >= trig) if side > 0 else (O[j] <= trig)
                    fill = O[j] if (gap and j > ke) else trig
                    tot += side * (xpx - fill) - COST
                    break
        out.append((ke, tot))
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
    plain, tagged = build(), build(stop_tag=True)
    ck30, ck15 = build(stop_tag=True, every=6), build(stop_tag=True, every=3)
    print("tape 2010-06-07 .. %s, cost %.3f, $%d/pt; ROC@30k = 30 x MAR with drawdown valued daily\n" % (LAST, COST, M))
    verdict = {}
    for bname, params in BASES:
        t0 = trades(plain, params)
        t1 = trades(tagged, params)
        assert len(t0) == len(t1) and all(abs(float(a[2]) - float(b[2])) < 1e-9 and int(a[0]) == int(b[0])
                                          for a, b in zip(t0, t1)), "stop-tagged copy does not reproduce " + bname
        assert len(t1[0]) >= 6, "engine dropped the stop field"
        print("%s  (%d trades; the stop-tagged copy reproduces every trade)" % (bname, len(t0)))
        raw = show("raw twin", [(int(x[0]), float(x[2])) for x in t0])
        p10 = show("A pyramid +1 at 1.0 R", pyramid(t1, 1.0))
        p05 = show("A neighbour 0.5 R", pyramid(t1, 0.5))
        p15 = show("A neighbour 1.5 R", pyramid(t1, 1.5))
        c30 = show("B half-hour checkpoints", [(int(x[0]), float(x[2])) for x in trades(ck30, params)])
        c15 = show("B neighbour quarter-hour", [(int(x[0]), float(x[2])) for x in trades(ck15, params)])
        verdict[(bname, "A")] = judge("A pyramid 1.0 R", p10, raw, [p05, p15])
        verdict[(bname, "B")] = judge("B half-hour checkpoints", c30, raw, [c15])
        print()
    for idea in ("A", "B"):
        both = all(verdict[(b, idea)] for b, _ in BASES)
        print("IDEA %s on BOTH bases: %s" % (idea, "SURVIVES -> fenced Auto-Validate" if both else "DEAD - record it"))

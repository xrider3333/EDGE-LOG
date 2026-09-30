# -*- coding: utf-8 -*-
"""NOISE ROUND 66 - ES confirmation of the NQ break (docs/PREREG_noise_r66_esconfirm_2026-09-30.md), round 63/65 harness.

A long is CONFIRMED when ES's close on the NQ signal bar is above ES's own noise band (crown formula and knobs on ES's
own bars), a short when below ES's lower band; unconfirmed signals are skipped INSIDE the strategy (NOISE_1_0.py source
patched in memory at the entry step, nothing on disk changes), so the flat slot can take a later confirmed break.
Neighbours: ES band at 0.5x / 1.5x the crown multipliers. Run WITHOUT the trial cache (patched copies).

OWNER YARDSTICK: ROC %/yr at a $30k worst drawdown = 30 x MAR, drawdown valued DAILY; WF and LB apart; beat the raw twin
on it AND Sortino in both; >= 100 WF / 50 LB trades; LB profitable without its biggest trade; both neighbours beat the
twin's WF ROC at $30k.

  python tools/r66_noise_esconfirm_triage.py  -> tools/r37_results/r66_esconfirm.txt
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
    m = types.ModuleType("noise_r66_%s" % ("plain" if esc is None else "esc"))
    m.__file__ = SRC_PATH
    exec(compile(s, SRC_PATH, "exec"), m.__dict__)
    if esc is not None:
        m._ESC_L, m._ESC_S = esc
    return m


# ---- ES's own noise band, aligned to the NQ bars by timestamp -------------------------------------------------------
EA = load_master_arrays(find_master("ES", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
EIDX = pd.DatetimeIndex(EA["index"])
EO, EC = np.asarray(EA["open"], float), np.asarray(EA["close"], float)
_h = types.ModuleType("noise_r66_helpers")
exec(compile(SRC, SRC_PATH, "exec"), _h.__dict__)
EB = _h._session_bounds(np.asarray(EA["day_id"]), len(EC))


def es_confirm(lookback, mult_long, mult_short):
    """(confirm_long, confirm_short, es_sign_since_open) on the NQ index; a missing ES bar = unconfirmed."""
    sig = _h._sigma_matrix(EO, EC, EB, lookback)
    cl = np.zeros(len(EC), bool)
    cs = np.zeros(len(EC), bool)
    up = np.zeros(len(EC), float)
    prev = None
    for si, (a, b) in enumerate(EB):
        m = b - a
        up[a:b] = np.sign(EC[a:b] - EO[a])
        if prev is None or si < lookback:
            prev = EC[b - 1]
            continue
        with np.errstate(invalid="ignore"):
            ub = max(EO[a], prev) * (1.0 + mult_long * sig[si, :m])
            lb = min(EO[a], prev) * (1.0 - mult_short * sig[si, :m])
            cl[a:b] = EC[a:b] > ub
            cs[a:b] = EC[a:b] < lb
        prev = EC[b - 1]
    pos = pd.Series(np.arange(len(EIDX)), index=EIDX).reindex(IDX)
    ok = pos.notna().to_numpy()
    p = pos.fillna(0).astype(int).to_numpy()
    return (cl[p] & ok, cs[p] & ok, np.where(ok, up[p], 0.0))


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
    verdict = {}
    for bname, params in BASES:
        t0 = trades(plain, params)
        allow = np.ones(len(IDX), bool)
        tp = trades(build(esc=(allow, allow)), params)                # the patch with every break allowed = plain
        assert [(int(x[0]), round(float(x[2]), 9)) for x in tp] == [(int(x[0]), round(float(x[2]), 9)) for x in t0], \
            "patched copy does not reproduce the plain strategy"
        lb, ml, ms = params["lookback"], params["band_mult_long"], params["band_mult_short"]
        print("")
        print("%s  (%d trades)" % (bname, len(t0)))
        cl, cs, up = es_confirm(lb, ml, ms)
        sg = np.array([int(x[0]) - 1 for x in t0])
        sd = np.array([int(np.sign(x[3])) for x in t0])
        conf = np.where(sd > 0, cl[sg], cs[sg])
        same = (up[sg] == sd)
        print("  descriptive: %.1f%% of the plain breaks are ES-confirmed; ES's move since its open agrees on %.1f%%"
              % (100 * conf.mean(), 100 * same.mean()))
        raw = show("raw twin", [(int(x[0]), float(x[2])) for x in t0])
        res = {}
        for fac in (1.0, 0.5, 1.5):
            e = es_confirm(lb, fac * ml, fac * ms)
            res[fac] = show("ES-confirmed %.1fx band%s" % (fac, "" if fac == 1.0 else " (neighbour)"),
                            [(int(x[0]), float(x[2])) for x in trades(build(esc=e[:2]), params)])
        verdict[bname] = judge("ES-confirmed 1.0x", res[1.0], raw, [res[0.5], res[1.5]])
    print("")
    print("ES CONFIRMATION on BOTH bases: %s" % ("SURVIVES -> fenced Auto-Validate" if all(verdict.values()) else "DEAD - record it"))

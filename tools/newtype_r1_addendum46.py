# -*- coding: utf-8 -*-
"""POST-VERDICT ADDENDUM - MANAGER review #46 edits on ROUND r1 and BONDLEAD r1, run AFTER both Stage A verdicts
(the review was missed before the runs; disclosed in MANAGER inbox #349). Report only - no verdict can change: both
primaries fail A1 on their own numbers. Uses the frozen Stage A scripts in this folder."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import halfhour_r1_stageA as HH                                       # noqa: E402
import round_r1_stageA as RN                                          # noqa: E402
import bondlead_r1_stageA as BL                                       # noqa: E402

ROLLS = os.path.join(HH.ROOT, "tools", "data", "contract_switches_NQ.csv")


def roc(x, bdays):
    return HH.own(x, bdays)


def round_part():
    print("=== ROUND r1 - MANAGER #46 edits (post-verdict report) ===")
    days, X = RN.bars()
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    wfd = (days >= HH.WF0) & (days <= HH.WF1)
    Xw = {f: np.where(wfd[:, None], v, np.nan) for f, v in X.items()}

    # (1) null without offsets near the 50s for the G100 cells
    rng = np.random.default_rng(RN.SEED)
    nm, npv = [], []
    for _ in range(RN.NULL_DRAWS):
        f = rng.uniform(0.1, 0.4) if rng.random() < 0.5 else rng.uniform(0.6, 0.9)
        f50 = rng.uniform(0.1, 0.9)
        vals = []
        for c in RN.CELLS:
            P, _ = RN.run_cell(Xw, c, f if c[1] == 100 else f50)
            vals.append(roc(HH.daily(P, days, bdays).to_numpy(), bdays)["roc"])
        vals = np.nan_to_num(np.array(vals), nan=-1e9)
        nm.append(vals.max())
        npv.append(vals[0])
    print("  (1) null with G100 offsets kept away from the 50s: family-max p95 %.2f; primary-cell null median %.2f "
          "(the primary was -2.50)" % (np.percentile(nm, 95), np.median(npv)))

    # (2) per calendar year with crossing counts, and a G = 0.5%-of-price twin (snapped to the nearest 50, at least 50)
    s = RN.signals(Xw, "CROSS", 100, 0.0)
    P, on = RN.trades(Xw, s, 30)
    first = X["open"][:, 0]
    Gd = np.maximum(50.0, np.round(0.005 * first / 50.0) * 50.0)
    C = Xw["close"]
    m = np.floor(C / Gd[:, None])
    mp = np.full_like(m, np.nan)
    mp[:, 1:] = m[:, :-1]
    s2 = np.where(m > mp, 1.0, np.where(m < mp, -1.0, 0.0))
    s2[:, :RN.K0] = 0.0
    s2[:, RN.K1 + 1:] = 0.0
    s2[np.isnan(mp) | np.isnan(m)] = 0.0
    P2, on2 = RN.trades(Xw, s2, 30)
    yr = days.year
    print("  (2) by calendar year: primary G100 crossings / trades / $   |   0.5%%-of-price grid G / trades / $")
    for y in sorted(set(yr[wfd])):
        k = np.asarray(yr == y) & np.asarray(wfd)
        print("      %d  %5d / %5d / $%9s   |   G %s / %5d / $%9s" % (
            y, int((s[k] != 0).sum()), int(on[k].sum()), format(int(P[k].sum()), ","),
            "/".join(str(int(g)) for g in sorted(set(Gd[k]))), int(on2[k].sum()), format(int(P2[k].sum()), ",")))
    x2 = HH.daily(P2, days, bdays).to_numpy()
    s2t = roc(x2, bdays)
    print("      0.5%%-of-price twin whole WF: n %d  net $%s  own ROC@30k %.2f (primary -2.50)" % (
        int(on2.sum()), format(int(s2t["net"]), ","), s2t["roc"]))

    # (3) roll-day trades apart (the first RTH session after each contract switch)
    r = pd.read_csv(ROLLS)
    sw = pd.to_datetime(r["switch_et"]).dt.normalize()
    rolld = set()
    for d in sw:
        nxt = days[days > d]
        if len(nxt):
            rolld.add(nxt[0])
    kr = np.asarray(days.isin(list(rolld)))
    print("  (3) roll-day sessions in the WF: %d; primary trades on them %d, $%s; on all other sessions %d, $%s" % (
        int((kr & np.asarray(wfd)).sum()), int(on[kr].sum()), format(int(P[kr].sum()), ","),
        int(on[~kr].sum()), format(int(P[~kr].sum()), ",")))


def bondlead_part():
    print("=== BONDLEAD r1 - MANAGER #46 edits (post-verdict report) ===")
    days, O, C, funds = BL.load()
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    wf = np.asarray((days >= HH.WF0) & (days <= HH.WF1))
    names, kend, z0 = BL.PRIMARY
    y = BL.morning(O, C, kend)
    xf = BL.morning(*funds["IEF"], kend)
    beta = np.full(len(days), np.nan)
    v = np.flatnonzero(~np.isnan(y) & ~np.isnan(xf))
    for j in range(BL.LOOK, len(v)):
        w = v[j - BL.LOOK:j]
        beta[v[j]] = np.polyfit(xf[w], y[w], 1)[0]
    z = BL.cell_z(BL.PRIMARY, O, C, funds)
    P, on = BL.leg(O, C, z, kend, z0, wf)
    bw = beta[wf & ~np.isnan(beta)]
    flips = int((np.diff(np.sign(bw)) != 0).sum())
    print("  (2) the 60-session slope changed sign %d times in the WF; positive on %.0f%% of WF days" % (
        flips, 100 * (bw > 0).mean()))
    for lab, k in (("slope > 0 (bonds and NQ move together)", beta > 0), ("slope < 0 (bonds up when NQ down)", beta < 0)):
        print("      %-42s trades %4d  $%s" % (lab, int(on[k].sum()), format(int(P[k].sum()), ",")))
    x = pd.Series(P, index=days).reindex(bdays, fill_value=0.0).to_numpy()
    k22 = np.asarray(bdays.year != 2022)
    s22 = roc(x[k22], bdays[k22])
    print("      without calendar 2022: own ROC@30k %.2f, net $%s (whole WF -2.03)" % (s22["roc"], format(int(s22["net"]), ",")))
    sgn = np.sign(xf)
    ok = wf & ~np.isnan(xf) & (sgn != 0)
    P3 = np.where(ok, (sgn * (C[:, 77] - O[:, kend]) - BL.COST) * BL.M, 0.0)
    P3 = np.nan_to_num(P3)
    s3 = roc(pd.Series(P3, index=days).reindex(bdays, fill_value=0.0).to_numpy(), bdays)
    print("  (4) sign-only twin (bonds up in the morning -> buy NQ at noon, no slope): n %d  net $%s  own ROC@30k %.2f" % (
        int(ok.sum()), format(int(s3["net"]), ","), s3["roc"]))
    print("  (1) second-master question to ELwA: moot (BONDLEAD dead); not raised")


if __name__ == "__main__":
    round_part()
    bondlead_part()

# -*- coding: utf-8 -*-
"""Shared Stage A pieces for the TTM lane's 2026-10-07 preregs (VRPES r1, JUMPSPLIT r1), per MANAGER's review of #567
(C:/EdgeLog/manager/reviews/REVIEW_VRPES_JUMPSPLIT_2026-10-07.md):
- every ROC @ $30k printed with its DD5 beside it (#77; augur_engine/drawdowns.py), worst DD > 1.3 x DD5 flagged;
- the RISK r1 lead-vs-raw trio (Ruling 2): the lead = ROC@30k(timed) - ROC@30k(raw), each sized on its own drawdown in the
  stretch, must be > 0 over the WF, over EX (the WF without the rows 2020-02-15 .. 04-30, joined end to end) and in EARLY;
  paired d = the daily timed minus raw at fixed WF $30k multipliers must be > 0 in >= 6 of the 9 WF July-June years;
- the minimum detectable book-add lead converted into the leg's own $/yr at a $30k drawdown (ROC 1 = $1,000 a year);
- the book add against #463 (93.81 / 3.816) and against the RESMOM line L = #463 + 0.264 x RES (120.82 / 3.916)."""
import numpy as np
import pandas as pd

from augur_engine.drawdowns import dd5
import halfhour_r1_stageA as HH

EX0, EX1 = pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-30")
WF_YEARS = list(range(2016, 2025))                                      # July-June years 2016-17 .. 2024-25


def stat(x, days):
    x = np.asarray(x, float)
    days = pd.DatetimeIndex(days)
    st = HH.own(x, days)
    if st is None:
        return dict(roc=float("nan"), sort=float("nan"), net=float(x.sum()), max_dd=0.0, dd5=0.0, ratio=float("nan"),
                    one=False)
    r = dd5(pd.Series(x, index=days))
    st = dict(st)
    st["dd5"] = float(r["dd5_usd"])
    st["ratio"] = st["max_dd"] / st["dd5"] if st["dd5"] > 0 else float("nan")
    st["one"] = bool(r["one_episode"])
    return st


def fmt(st):
    return "ROC@30k %6.2f  Sortino %5.2f  net $%9s  DD $%7s / DD5 $%7s (x%.2f%s)" % (
        st["roc"], st["sort"], format(int(round(st["net"])), ","), format(int(round(st["max_dd"])), ","),
        format(int(round(st["dd5"])), ","), st["ratio"], ", DRIVEN BY ONE EPISODE" if st["one"] else "")


def jy_sums(x, days):
    days = pd.DatetimeIndex(days)
    return [float(np.asarray(x)[(days >= pd.Timestamp(y, 7, 1)) & (days < pd.Timestamp(y + 1, 7, 1))].sum())
            for y in WF_YEARS]


def lead_trio(xt, xr, days, wf, early, label):
    """RISK r1 trio for timed xt vs raw xr on one calendar `days` (masks wf / early). Returns (pass, lines)."""
    days = pd.DatetimeIndex(days)
    ex = wf & ~np.asarray((days >= EX0) & (days <= EX1))
    out, ok = [], True
    for lab, m in (("WF", wf), ("EX (no 2020-02-15..04-30)", ex), ("EARLY", early)):
        a, b = stat(xt[m], days[m]), stat(xr[m], days[m])
        ld = a["roc"] - b["roc"]
        ok &= bool(np.isfinite(ld) and ld > 0)
        out.append("    %-26s lead %+7.2f  timed %s | raw %s" % (lab, ld, fmt(a), fmt(b)))
    kt = 30000.0 / stat(xt[wf], days[wf])["max_dd"]
    kr = 30000.0 / stat(xr[wf], days[wf])["max_dd"]
    d = np.where(wf, kt * np.asarray(xt) - kr * np.asarray(xr), 0.0)
    ys = jy_sums(d, days)
    npos = sum(v > 0 for v in ys)
    ok &= npos >= 6
    out.append("    paired d (x%.3f timed - x%.3f raw, fixed WF $30k multipliers) > 0 in %d of 9 July-June years: %s" % (
        kt, kr, npos, " ".join("%+.0fk" % (v / 1000) for v in ys)))
    return ok, ["  RISK r1 TRIO %s vs raw: %s" % (label, "PASS" if ok else "FAIL")] + out


def mde_line(xb, B, years, twin=True):
    """The power line's minimum detectable lead (5% line) for a coin-flip leg xb on #463's WF index: at the $30k
    own-drawdown sizing (twin=True) or at the VOL scale."""
    bdays = pd.DatetimeIndex(B.index)
    xx = HH.scaled(xb)[0] if twin else HH.vol_scaled(xb, B, bdays)[0]
    return float(HH.PL.power_line(B.to_numpy() + xx, B.to_numpy(), years)["line_5pct"])


def mde_own(make_cf, held, B, mde, n=200, seed=20261007):
    """MDE in the leg's own money (MANAGER review, edit 12): the leg's own ROC@30k - which IS its own $/yr at a $30k
    drawdown / 1,000 - at which the leg, sized to a $30k own drawdown, lifts #463's WF ROC@30k by `mde` (the $30k-twin
    power line's 5% line). For each of n coin-flip draws (make_cf(rng) -> daily $ on #463's WF index) the leg is de-meaned
    over its held rows, then a constant $ per held row is added until the point lead hits `mde` (bisection); the median
    over draws is the number, p25 / p75 beside it. (At the VOL scale a sparse leg's lead SATURATES: a deterministic edge
    raises its daily SD as fast as its mean, so the VOL line is not converted.)"""
    bdays = pd.DatetimeIndex(B.index)
    Bv = B.to_numpy()
    base = HH.own(Bv, bdays)["roc"]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        x0 = np.asarray(make_cf(rng), float).copy()
        x0[held] -= x0[held].mean()

        def lead(mu):
            x = x0.copy()
            x[held] += mu
            return HH.own(Bv + HH.scaled(x)[0], bdays)["roc"] - base, x

        lo, hi = 0.0, 100.0
        if lead(lo)[0] > mde:
            lo = -100.0
            while lead(lo)[0] > mde and lo > -1e7:
                lo *= 2.0
        while lead(hi)[0] < mde and hi < 1e7:
            hi *= 2.0
        for _k in range(50):
            mid = 0.5 * (lo + hi)
            if lead(mid)[0] < mde:
                lo = mid
            else:
                hi = mid
        out.append((hi, HH.own(lead(hi)[1], bdays)["roc"]))
    a = np.array(out)
    return dict(mu=np.percentile(a[:, 0], [25, 50, 75]), roc=np.percentile(a[:, 1], [25, 50, 75]), n=n)


def book_adds(x, B, L, years, name, no2020=False):
    """REPORT: book + leg at the VOL scale and the $30k twin, against #463 and the RESMOM line L; DD5 beside each."""
    bdays = pd.DatetimeIndex(B.index)
    xv, s = HH.vol_scaled(x, B, bdays)
    xd, dd = HH.scaled(x)
    lines = []
    for base_lab, base in (("#463", B.to_numpy()), ("RESMOM line", L.to_numpy())):
        b0 = stat(base, bdays)
        for lab, xx, sz in (("VOL scale", xv, s), ("$30k own DD twin", xd, 30000.0 / dd if dd > 0 else float("nan"))):
            st = stat(base + xx, bdays)
            idx = HH.PL.stationary_indices(len(xx), 1000, 20, np.random.default_rng(HH.SEED))
            lead = HH.PL.roc30((base + xx)[idx], years) - HH.PL.roc30(base[idx], years)
            lead = lead[np.isfinite(lead)]
            lines.append("  REPORT %s + %s at %-16s (x%.3f): %s  lead %+.2f  bootstrap p5 %+.1f" % (
                base_lab, name, lab, sz, fmt(st), st["roc"] - b0["roc"], float(np.percentile(lead, 5))))
    if no2020:
        k = np.asarray(bdays.year != 2020)
        a, b = stat((B.to_numpy() + xv)[k], bdays[k]), stat(B.to_numpy()[k], bdays[k])
        lines.append("  VOL-scale lead over #463 WITHOUT calendar 2020: %+.2f (%s)" % (a["roc"] - b["roc"], fmt(a)))
    return lines

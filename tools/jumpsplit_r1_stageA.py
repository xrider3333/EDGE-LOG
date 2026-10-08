# -*- coding: utf-8 -*-
"""JUMPSPLIT r1 STAGE A - a diffusive morning continues, a jump morning does not (docs/PREREG_jumpsplit_r1_2026-10-07.md +
ADDENDUM 1; TTM scope rank 8, opened by MANAGER 2026-10-07; review C:/EdgeLog/manager/reviews/REVIEW_VRPES_JUMPSPLIT_2026-10-07.md).
NQ and ES are separate arms, judged apart.

Bipower variation separates a morning's continuous variance from its jumps (Barndorff-Nielsen & Shephard 2004, 2006;
Huang & Tauchen 2005). Per arm: from the 30 5m RTH log returns of 09:30-12:00 (bars k 0..29; the first from the 09:30
open), RV = sum r^2, BV = (pi/2)(30/29) sum |r_i||r_i-1|, RJ = (RV - BV) / RV (not truncated). p = the share of the 252
prior ELIGIBLE sessions' RJ below today's. ELIGIBLE (ADDENDUM 1 edit 2) = decided from the morning and the calendar only:
bars k 0..30 all present, not a CME US-holiday session (it ends with the 12:55 or 13:00 bar) and not an early close (it ends with
the 13:10 / 13:15 bar); the CME schedule is published in advance and is cross-checked against the NYSE rule list. DIFFUSIVE (p <= 1/3) and the morning moved: 1 contract in
the morning's direction at the 12:00 bar's open (k 30), out at the close of the last bar <= 15:55 present (k 77 unless an
afternoon gap); no stop. NO-ADJUST 5m RTH masters (no RTH roll switch 2010-2025). NQ 0.533 pt x $20, ES 0.363 pt x $50.

  python tools/jumpsplit_r1_stageA.py --predata  -> eligibility, the RJ diagnostics (edits 5-6), counts, power lines and
                                                   their own-$/yr conversion (no real direction)
  python tools/jumpsplit_r1_stageA.py            -> Stage A (refuses unless the prereg is on origin/main)
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HOME = os.environ.get("EDGELOG_HOME") or "C:/EdgeLog"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402
import ttm_r1_common as TC                                              # noqa: E402

ARMS = {"NQ": (0.533, 20.0), "ES": (0.363, 50.0)}
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY0, EARLY1 = pd.Timestamp("2011-07-01"), pd.Timestamp("2016-06-30")
NBAR, NOON, HIST = 78, 30, 252
TERC, QUART = 1.0 / 3.0, 1.0 / 4.0
NULL_DRAWS, SEED = 1000, 20261007
AC_SWITCH = 0.10
PREREG = "docs/PREREG_jumpsplit_r1_2026-10-07.md"
PUB = os.path.join(HOME, "_research_cache", "public_series")
STRETCHES = [("EARLY 2011-07..2016-06", EARLY0, EARLY1), ("WF", WF0, WF1),
             ("WF 2016-21", WF0, pd.Timestamp("2021-12-31")), ("WF 2022-25", pd.Timestamp("2022-01-01"), WF1)]


def stock_days():
    raw = os.path.join(PUB, "cboe", "VIX_History.csv")
    prov = json.load(open(os.path.join(PUB, "public_series_provenance.json"), encoding="utf-8"))["cboe\\VIX_History.csv"]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], "VIX_History.csv is not the photograph"
    v = pd.read_csv(raw)
    v.columns = [c.strip().upper() for c in v.columns]
    return pd.DatetimeIndex(pd.to_datetime(v["DATE"], format="%m/%d/%Y"))


def nyse_early_closes(y0=2010, y1=2025):
    """NYSE 13:00 closes by rule: the day after Thanksgiving; Dec 24 on Mon-Thu; Jul 3 on Mon-Thu (2013: Wed, etc.)."""
    out = []
    for y in range(y0, y1 + 1):
        nov = pd.date_range("%d-11-01" % y, "%d-11-30" % y)
        out.append(nov[nov.dayofweek == 3][3] + pd.Timedelta(days=1))
        for md in ("12-24", "07-03"):
            d = pd.Timestamp("%d-%s" % (y, md))
            if d.dayofweek <= 3:
                out.append(d)
    return pd.DatetimeIndex(out)


def grid(sym):
    A = load_master_arrays(find_master(sym, "5m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None)
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.DatetimeIndex(ts.normalize())
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    ok = (k >= 0) & (k < NBAR)
    G = {}
    for f in ("open", "close"):
        X = np.full((len(days), NBAR), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        G[f] = X
    return days, G


def build(sym, sdays, early):
    days, G = grid(sym)
    have = np.isfinite(G["close"])
    morning_ok = np.isfinite(G["open"][:, 0]) & have[:, :NOON].all(axis=1) & np.isfinite(G["open"][:, NOON])
    nb = have.sum(axis=1)
    last = np.where(have.any(axis=1), NBAR - 1 - np.argmax(have[:, ::-1], axis=1), -1)
    full_to = np.array([bool(h[:k + 1].all()) if k >= 0 else False for h, k in zip(have, last)])
    # the CME schedule (published in advance): a US holiday session ends with the 12:55 or 13:00 bar (stock market
    # closed), an
    # early close with the 13:10 or 13:15 bar; both complete up to their end. Cross-checked against the NYSE rule list.
    stock = ~(full_to & np.isin(last, (41, 42)))
    half = full_to & np.isin(last, (44, 45))
    elig = morning_ok & stock & ~half
    # the morning: bars k 0..29 only (edit 1)
    O0 = G["open"][:, 0]
    Cm = G["close"][:, :NOON]
    assert Cm.shape[1] == 30 and NOON == 30
    r = np.diff(np.log(np.c_[O0, Cm]), axis=1)
    n = r.shape[1]
    rv = (r ** 2).sum(axis=1)
    bv = (np.pi / 2.0) * (n / (n - 1.0)) * (np.abs(r[:, 1:]) * np.abs(r[:, :-1])).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rj = np.where(elig & (rv > 0), (rv - bv) / rv, np.nan)
    dirn = np.where(elig, np.sign(Cm[:, -1] - O0), 0.0)
    # trailing ranks over the 252 prior eligible sessions (RJ for the state, morning RV for the null's strata)
    ei = np.flatnonzero(elig & np.isfinite(rj))
    p = np.full(len(days), np.nan)
    prv = np.full(len(days), np.nan)
    for j in range(HIST, len(ei)):
        h = ei[j - HIST:j]
        i = ei[j]
        p[i] = float((rj[h] < rj[i]).mean())
        prv[i] = float((rv[h] < rv[i]).mean())
    # exit = the last bar <= 15:55 present (k 77 unless an afternoon gap)
    return dict(sym=sym, days=days, G=G, rj=rj, rv=rv, r=r, dirn=dirn, p=p, prv=prv, elig=elig, half=half, stock=stock,
                last=last, nbars=nb, morning_ok=morning_ok, early=early)


def label(D):
    """Nested state: 2 = bottom quartile, 1 = tercile-not-quartile, 0 = other; -1 = no state."""
    p = D["p"]
    lab = np.full(len(p), -1)
    f = np.isfinite(p)
    lab[f] = np.where(p[f] <= QUART, 2, np.where(p[f] <= TERC, 1, 0))
    return lab


def side_of(D, lab, cell):
    on = (lab >= 1) if cell == "tercile" else (lab == 2)
    return np.where(on & (D["dirn"] != 0), D["dirn"], 0.0)


def pnl(D, side, cost_mult=1.0):
    cost, m = ARMS[D["sym"]]
    G = D["G"]
    x = np.zeros(len(side))
    t = np.flatnonzero(side != 0)
    if len(t):
        assert (D["last"][t] > NOON).all(), "an exit bar at or before the fill bar"
        ex = G["close"][t, D["last"][t]]
        x[t] = side[t] * (ex - G["open"][t, NOON]) * m - cost_mult * cost * m
    return x


def trades(D, side):
    t = np.flatnonzero(side != 0)
    d = D["days"][t]
    return pd.DataFrame({"date": d, "side": side[t],
                         "signal_ts": d + pd.Timedelta(minutes=570 + 5 * (NOON - 1)),
                         "fill_ts": d + pd.Timedelta(minutes=570 + 5 * NOON),
                         "exit_ts": d + pd.to_timedelta(570 + 5 * D["last"][t], unit="m"),
                         "pnl": pnl(D, side)[t]})


def mask(days, a, b):
    return np.asarray((days >= a) & (days <= b))


def autocorr(z, lags=5):
    z = z.astype(float) - z.mean()
    v = (z * z).mean()
    return [float((z[:-k] * z[k:]).mean() / v) for k in range(1, lags + 1)]


def spearman(a, b):
    f = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[f]).rank().corr(pd.Series(b[f]).rank()))


def predata(D, B, bdays, years, RDd, ecl, sdays):
    days, sym = D["days"], D["sym"]
    wf = mask(days, WF0, WF1)
    have78 = D["nbars"] == NBAR
    print("ARM %s: %d sessions; eligible %d (morning complete %d, stock market open %d, early-close pattern %d)" % (
        sym, len(days), int(D["elig"].sum()), int(D["morning_ok"].sum()), int(D["stock"].sum()), int(D["half"].sum())))
    hd = days[D["half"]]
    ec = ecl[(ecl >= days[0]) & (ecl <= days[-1])]
    print("  early closes seen: %d; vs the NYSE rule list (%d days): seen but not in the rules %s; rule days not seen %s" % (
        len(hd), len(ec), [str(d.date()) for d in hd[~hd.isin(ec)]], [str(d.date()) for d in ec[~ec.isin(hd)]]))
    hol = days[~D["stock"]]
    vix_on_hol = hol[hol.isin(sdays)]
    print("  CME holiday sessions (stock market closed): %d; of them with a row in the VIX photograph: %d (%s)" % (
        len(hol), len(vix_on_hol), ", ".join(str(d.date()) for d in vix_on_hol[:8])))
    odd = days[D["morning_ok"] & D["stock"] & ~D["half"] & (D["last"] < NBAR - 1)]
    print("  regular sessions ending before 15:55: %s" % [str(d.date()) for d in odd])
    gap = D["elig"] & ~have78
    print("  ELIGIBLE sessions the 78-bar rule would have DROPPED (afternoon-only gaps): %d -> %s; exit = last bar <= 15:55 "
          "on those" % (int(gap.sum()), ", ".join("%s (last %02d:%02d)" % (d.date(), (570 + 5 * k) // 60, (570 + 5 * k) % 60)
                                                  for d, k in zip(days[gap], D["last"][gap]))))
    f = wf & np.isfinite(D["p"])
    nrm = np.abs(D["G"]["close"][:, NOON - 1] - D["G"]["open"][:, 0]) / D["G"]["open"][:, 0] / np.sqrt(D["rv"])
    print("  RJ DIAGNOSTICS (edit 5, WF): Spearman RJ vs morning RV %+.3f; RJ vs |move|/sqrt(RV) %+.3f" % (
        spearman(D["rj"][f], D["rv"][f]), spearman(D["rj"][f], nrm[f])))
    for lab, sel in (("diffusive p <= 1/3", f & (D["p"] <= TERC)), ("middle", f & (D["p"] > TERC) & (D["p"] < 2 / 3.)),
                     ("jump p >= 2/3", f & (D["p"] >= 2 / 3.))):
        z = (D["r"][sel] == 0).mean()
        s0 = np.mean(D["r"][sel, 0] ** 2 / D["rv"][sel])
        mrv = np.median(np.sqrt(D["rv"][sel] * 252 / 30 * 78) * 100)
        print("    %-20s n %4d  share of zero 5m returns %.3f  09:30 bar's share of RV %.3f  median morning vol %.1f%% "
              "(annualised)  median RV-rank %.2f" % (lab, int(sel.sum()), z, s0, mrv, np.nanmedian(D["prv"][sel])))
    ind = (D["p"][np.isfinite(D["p"])] <= TERC).astype(float)
    ac = autocorr(ind)
    mode = "within-year CIRCULAR SHIFT" if max(ac) > AC_SWITCH else "within year x morning-RV-tercile SHUFFLE"
    print("  STATE AUTOCORRELATION (edit 6) lags 1-5: %s -> null = %s" % (" ".join("%+.3f" % a for a in ac), mode))
    lab = label(D)
    for cell in ("tercile", "quartile"):
        s = side_of(D, lab, cell)
        per = pd.Series(days.year[wf & (s != 0)]).value_counts().sort_index()
        print("  COUNTS bottom %s: %d WF trades (%.0f a year), long %d / short %d; per calendar year %s; R days %d" % (
            cell, int((wf & (s != 0)).sum()), (wf & (s != 0)).sum() / years, int((wf & (s > 0)).sum()),
            int((wf & (s < 0)).sum()), {int(k): int(v) for k, v in per.items()}, int((wf & (s != 0) & days.isin(RDd)).sum())))
    sp = side_of(D, lab, "tercile")
    jp = np.where((D["p"] >= 2 / 3.) & (D["dirn"] != 0), D["dirn"], 0.0)
    al = np.where(np.isfinite(D["p"]) & (D["dirn"] != 0), D["dirn"], 0.0)
    for lab_, a, b in STRETCHES:
        m = mask(days, a, b)
        print("    %-22s primary %4d; twins: all sessions %4d, jump mornings %4d" % (
            lab_, int((m & (sp != 0)).sum()), int((m & (al != 0)).sum()), int((m & (jp != 0)).sum())))
    tr = trades(D, np.where(wf, sp, 0.0))
    assert (tr["fill_ts"] - tr["signal_ts"] == pd.Timedelta(minutes=5)).all() and (tr["fill_ts"].dt.hour == 12).all()
    print("  trade rows carry signal_ts (the 11:55 bar) and fill_ts (the 12:00 bar): first %s / %s" % (
        tr["signal_ts"].iloc[0], tr["fill_ts"].iloc[0]))
    on = wf & (sp != 0)
    rng = np.random.default_rng(SEED)

    def cf(g):
        return pd.Series(pnl(D, np.where(on, g.choice([-1.0, 1.0], size=len(sp)), 0.0)), index=days).reindex(
            bdays, fill_value=0.0).to_numpy()

    xb = cf(rng)
    print("  POWER LINES %s (coin-flip sides on the primary's schedule; no real direction is computed)" % sym)
    HH.power_lines(xb, B, years)
    mde = TC.mde_line(xb, B, years)
    ent = np.flatnonzero(np.isin(bdays, days[on]))
    r = TC.mde_own(cf, ent, B, mde)
    print("  MDE IN OWN MONEY (edit 12): the $30k-twin line's minimum detectable lead %.1f needs own ROC@30k %.1f (p25 %.1f / "
          "p75 %.1f over %d coin-flip draws) = own $%s a year at a $30k drawdown, vs the $15,000 MDL" % (
              mde, r["roc"][1], r["roc"][0], r["roc"][2], r["n"], format(int(round(r["roc"][1] * 1000)), ",")))


def null_draws(Ds, bdays, RD, rng, modes):
    """Family max over the four cells (two arms x two cells) of own ROC@30k and of the R-day sum, per draw."""
    labs = {s: label(D) for s, D in Ds.items()}
    roc, rs = np.empty(NULL_DRAWS), np.empty(NULL_DRAWS)
    strata = {}
    for s, D in Ds.items():
        yr = D["days"].year
        wf = mask(D["days"], WF0, WF1) & (labs[s] >= 0)
        rvt = np.where(D["prv"] <= TERC, 0, np.where(D["prv"] >= 2 / 3., 2, 1))
        groups = []
        for y in np.unique(yr[wf]):
            if modes[s].startswith("within-year CIRCULAR"):
                groups.append(("circ", np.flatnonzero(wf & (yr == y))))
            else:
                for t in (0, 1, 2):
                    groups.append(("perm", np.flatnonzero(wf & (yr == y) & (rvt == t))))
        strata[s] = groups
    for i in range(NULL_DRAWS):
        r1, r2 = [], []
        for s, D in Ds.items():
            lab = labs[s].copy()
            for kind, ii in strata[s]:
                if len(ii) < 2:
                    continue
                lab[ii] = np.roll(lab[ii], int(rng.integers(1, len(ii)))) if kind == "circ" else lab[rng.permutation(ii)]
            for cell in ("tercile", "quartile"):
                xb = pd.Series(pnl(D, side_of(D, lab, cell)), index=D["days"]).reindex(bdays, fill_value=0.0).to_numpy()
                r1.append(TC.stat(xb, bdays)["roc"])
                r2.append(float(xb[RD].sum()))
        roc[i], rs[i] = np.nanmax(r1), max(r2)
    return roc, rs


def stage_a(Ds, B, bdays, years, RD, modes):
    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", PREREG], capture_output=True, text=True,
                         cwd=ROOT).stdout.strip()
    print("  PREREG on main: %s last changed in %s" % (PREREG, sha or "NOT ON MAIN - STOP"))
    if not sha:
        return
    import balance_r1_stageA as BAL
    L = BAL.load_L(B)[0]
    legs = BAL.book_leg_dailies(bdays, B)
    rng = np.random.default_rng(SEED)
    nroc, nrs = null_draws(Ds, bdays, RD, rng, modes)
    q_roc, q_rs = float(np.percentile(nroc, 95)), float(np.percentile(nrs, 95))
    print("  FAMILY NULL (%d draws; NQ %s, ES %s): family-max own ROC@30k p95 %.2f; family-max R-day sum p95 $%s" % (
        NULL_DRAWS, modes["NQ"], modes["ES"], q_roc, format(int(q_rs), ",")))
    p0, p1 = HH.worst_window(B)
    pos = None
    for sym, D in Ds.items():
        days = D["days"]
        lab = label(D)
        wf = mask(days, WF0, WF1)
        early = mask(days, EARLY0, EARLY1)
        sides = {"PRIMARY diffusive tercile": side_of(D, lab, "tercile"), "neighbour quartile": side_of(D, lab, "quartile"),
                 "twin ALL sessions": np.where(lab >= 0, D["dirn"], 0.0),
                 "twin JUMP mornings": np.where((D["p"] >= 2 / 3.) & (D["dirn"] != 0), D["dirn"], 0.0)}
        print("=== ARM %s ===" % sym)
        X = {}
        for lab_, s in sides.items():
            x = pnl(D, s)
            X[lab_] = x
            parts = []
            for st_lab, a, b in STRETCHES:
                m = mask(days, a, b)
                xs = pd.Series(x[m], index=days[m])
                xs = xs.reindex(bdays[(bdays >= a) & (bdays <= b)], fill_value=0.0) if a >= WF0 else xs
                parts.append("%s n %d: %s" % (st_lab, int((m & (s != 0)).sum()), TC.fmt(TC.stat(xs.to_numpy(), xs.index))))
            print("  %-26s\n      %s" % (lab_, "\n      ".join(parts)))
        s = sides["PRIMARY diffusive tercile"]
        xp = X["PRIMARY diffusive tercile"]
        xb = pd.Series(np.where(wf, xp, 0.0), index=days).reindex(bdays, fill_value=0.0).to_numpy()
        st = TC.stat(xb, bdays)
        t = xp[wf & (s != 0)]
        pf = t[t > 0].sum() / -t[t < 0].sum()
        ys = TC.jy_sums(xb, bdays)
        rsum = float(xb[RD].sum())
        earner = st["roc"] >= 5 and rsum > q_rs
        route = st["roc"] >= 15 or earner
        k20 = np.asarray(bdays.year != 2020)
        s20 = TC.stat(xb[k20], bdays[k20])
        route20 = s20["roc"] >= 15 or (s20["roc"] >= 5 and earner)
        x2 = pnl(D, np.where(wf, s, 0.0), cost_mult=2.0)
        exm = wf & mask(days, TC.EX0, TC.EX1)
        a4 = (t.sum() - t.max() > 0) and (x2.sum() > 0) and (xp[wf & ~exm].sum() > 0)
        xn = X["neighbour quartile"][wf].sum()
        allt = X["twin ALL sessions"]
        ok_trio, lines = TC.lead_trio(np.where(wf | early, xp, 0.0), np.where(wf | early, allt, 0.0), days, wf, early,
                                      "DIFFUSIVE vs ALL sessions")
        print("\n".join(lines))
        a5 = all(xp[mask(days, a, b)].sum() > 0 for lab_, a, b in STRETCHES if lab_ != "WF")
        jt = X["twin JUMP mornings"][wf & (sides["twin JUMP mornings"] != 0)]
        a7 = t.mean() > (jt.mean() if len(jt) else -np.inf)
        print("  A7 pole: diffusive per-trade $%.1f vs jump-morning per-trade $%.1f" % (t.mean(), jt.mean() if len(jt) else np.nan))
        print("  R-DAY SUM $%s (family null p95 $%s); dollars inside #463's worst WF drawdown (%s .. %s) $%s" % (
            format(int(rsum), ","), format(int(q_rs), ","), p0.date(), p1.date(),
            format(int(xb[(bdays > p0) & (bdays <= p1)].sum()), ",")))
        bars = [("A1 route (>= 15, or >= 5 + R-day sum > family p95)", route),
                ("A1 count (>= 100 and 50 a year)", len(t) >= 100 and len(t) / years >= 50), ("PF > 1", pf > 1),
                (">= 6 of 9 July-June years", sum(v > 0 for v in ys) >= 6), ("A1b route without 2020", route20),
                ("A2 own ROC > family null p95", st["roc"] > q_roc), ("A3 neighbour net > 0", xn > 0),
                ("A4 net > 0 w/o best trade, at 2x cost, w/o 2020-02-15..04-30", a4),
                ("A5 standalone net > 0 in EARLY, WF 2016-21, WF 2022-25", a5),
                ("A5 RISK r1 trio vs all sessions", ok_trio), ("A7 diffusive per-trade > jump per-trade", a7)]
        print("  PRIMARY WF: n %d (%.0f/yr)  %s  PF %.2f  years + %d/9  no-2020 ROC %.2f" % (
            len(t), len(t) / years, TC.fmt(st), pf, sum(v > 0 for v in ys), s20["roc"]))
        for b, v in bars:
            print("    %-70s %s" % (b, "pass" if v else "FAIL"))
        verdict = "PASS" if all(v for _, v in bars) else "FAIL"
        # overlap (edits 10-11)
        if sym == "NQ":
            pos = pos or HH.book_positions(days)
            nz = pos["NOISE"][:, NOON]
            tt = wf & (s != 0)
            same = float(((np.sign(nz) == s) & (nz != 0))[tt].mean())
            orb = pos["ORB"][:, NOON]
            print("  OVERLAP at 12:00: NOISE #422 same side on %.0f%% of NQ-arm trades (opposite %.0f%%); ORB same %.0f%%" % (
                100 * same, 100 * float(((np.sign(nz) == -s) & (nz != 0))[tt].mean()),
                100 * float(((np.sign(orb) == s) & (orb != 0))[tt].mean())))
            held = np.zeros((len(days), NBAR))
            held[tt, NOON:] = s[tt][:, None]
            print("  overlap of held bars: " + HH.overlap(held[wf], {k: v[wf] for k, v in pos.items()}))
            if same > 0.5:
                flat = tt & (nz == 0)
                fn = float(xp[flat].sum())
                print("  NQ arm on NOISE-flat sessions: n %d net $%s -> %s" % (
                    int(flat.sum()), format(int(fn), ","), "ok" if fn > 0 else "an NQ pass is filed 'NOISE re-expression'"))
                if fn <= 0 and verdict == "PASS":
                    verdict = "PASS filed 'NOISE re-expression' - no plugin until MANAGER rules"
        else:
            ttm = legs["TTM"].to_numpy()
            both = (xb != 0) & (ttm != 0)
            print("  ES arm vs #463's ES leg (TTM #459 x3): daily P&L correlation %.3f on all WF days, %.3f on days both "
                  "trade (%d days)" % (np.corrcoef(xb, ttm)[0, 1], np.corrcoef(xb[both], ttm[both])[0, 1] if both.sum() > 2
                                       else np.nan, int(both.sum())))
        print("\n".join(TC.book_adds(xb, B, L, years, "JUMPSPLIT " + sym)))
        print("  long vs short: long $%s (%d) / short $%s (%d)" % (
            format(int(xp[wf & (s > 0)].sum()), ","), int((wf & (s > 0)).sum()), format(int(xp[wf & (s < 0)].sum()), ","),
            int((wf & (s < 0)).sum())))
        for bps in (0, 5, 10, 20):
            cost, m = ARMS[sym]
            g = (wf & (s != 0))
            net = (xp[g] + cost * m).sum() - (bps / 1e4 * D["G"]["open"][g, NOON] * m).sum()
            print("  cost curve %2d bps: net $%s" % (bps, format(int(net), ",")))
        path = []
        for k in range(NOON + 5, NBAR, 6):
            path.append(float((s[wf] * (D["G"]["close"][wf, k] - D["G"]["open"][wf, NOON]))[s[wf] != 0].mean() * ARMS[sym][1]))
        print("  event path (mean $ from the fill, 30m marks 12:25 .. 15:55): " + " ".join("%.0f" % v for v in path))
        print("  ARM %s VERDICT: %s" % (sym, verdict))


def main(argv):
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("JUMPSPLIT r1 - NQ / ES 5m RTH no-adjust; arms judged apart")
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    RDd = pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))
    RD = np.asarray(bdays.isin(RDd))
    sdays = stock_days()
    ecl = nyse_early_closes()
    Ds = {s: build(s, sdays, None) for s in ARMS}
    modes = {}
    for s, D in Ds.items():
        ind = (D["p"][np.isfinite(D["p"])] <= TERC).astype(float)
        modes[s] = "within-year CIRCULAR SHIFT" if max(autocorr(ind)) > AC_SWITCH else "within year x morning-RV-tercile SHUFFLE"
    if "--predata" in argv:
        for D in Ds.values():
            predata(D, B, bdays, years, RDd, ecl, sdays)
        return
    stage_a(Ds, B, bdays, years, RD, modes)


if __name__ == "__main__":
    main(sys.argv[1:])

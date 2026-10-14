# -*- coding: utf-8 -*-
"""NOISE NEXT-THREE (MANAGER #82, 2026-10-10) - the power-first lines for the three drafts. NO CANDIDATE RESULT IS READ.

#422 = NOISE_1_8_CT304H (gate 20 / 1.15, 1.75x) on the NQ 5m RTH no-adjust master, cost 0.533 pt, $20 a point, walk-
forward stretch only (signal date 2016-07-01 .. 2025-06-29). #422's own trades are already seen (anatomy, ledger 2.82).

N1 GAMMA-SORT  #422 sized 1.5x on short-gamma days / 0.5x on long-gamma days (GAMMA r1's state, p <= 1/3 / >= 2/3).
               Null = the state labels shuffled within each July-June year (counts kept). Only the label COUNTS per year
               are read here; the real assignment is never applied.
N2 HALVES      forward read of #422's two halves in band units (sigma at the signal bar). Power = months of forward
               trades to see the edge halve / vanish (one-sided 5%, 80%).
N3 MIRROR      after the session's FIRST #422 VWAP exit (a failed break), the opposite side at the same fill (next open),
               held to the session's last close, no stop. Coin-flip sides on that schedule; the real side is never used.

ROC@30k = 30 x (net a year) / max drawdown, valued daily. MDE = the true edge at which the median draw clears its bar.
    python power_next3.py
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
import importlib.util as ilu                                          # noqa: E402

W0, W1 = pd.Timestamp("2016-07-01").date(), pd.Timestamp("2025-06-29").date()
YRS = 8.994
DRAWS, SEED = 2000, 20261010
DIX = r"C:\EdgeLog\_research_cache\squeezemetrics\DIX.csv"
_s = ilu.spec_from_file_location("_n10", os.path.join(REPO, "augur_strategies", "NOISE_1_0.py"))
N10 = ilu.module_from_spec(_s)
_s.loader.exec_module(N10)


def roc30(daily):
    cum = np.cumsum(daily)
    dd = np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum)
    return 30.0 * (cum[-1] / YRS) / max(dd, 1.0), dd


def trades():
    A = R.A
    O, C = np.asarray(A["open"], float), np.asarray(A["close"], float)
    idx, day = R.IDX, np.asarray(A["day_id"])
    ct = R.load("NOISE_1_8_CT304H.py")
    tr = sorted(run_backtest(ct, arrays=A, params=dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75),
                             cost_pts=R.COST, return_trades=True)["trades"], key=lambda t: int(t[0]))
    # UNIT trades = the #304 core run alone (since the 10-08 roll guard the wrapper's sized pnl no longer divides back
    # to raw points), matched entry-for-entry; exit kinds and band units are read from the unit run.
    core = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
                window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
                confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
    tu = sorted(run_backtest(R.load("NOISE_1_0.py"), arrays=A, params=core,      # the #304 core (CT304H's _FROZEN)
                             cost_pts=R.COST, return_trades=True)["trades"], key=lambda t: int(t[0]))
    assert [(int(a[0]), int(a[1])) for a in tr] == [(int(b[0]), int(b[1])) for b in tu], "sized / unit trades differ"
    starts = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    ends = np.r_[starts[1:], len(day)]
    s_of = np.repeat(np.arange(len(starts)), ends - starts)
    sig = N10._sigma_matrix(O, C, list(zip(starts, ends)), 40)
    rows = []
    for t, u in zip(tr, tu):
        k0, k1, pnl, side = int(t[0]), int(t[1]), float(t[2]), float(np.sign(t[3]))
        ks = k0 - 1
        d = idx[ks].date()
        if not (W0 <= d <= W1):
            continue
        unit = float(u[2])
        epx = float(t[4]) if len(t) > 4 else float(O[k0])
        xpx = epx + side * (unit + R.COST)
        si = s_of[ks]
        last = k1 == ends[si] - 1
        kind = ("eod" if last and abs(xpx - C[k1]) < 1e-6 else
                "vwap" if abs(xpx - O[k1]) < 1e-6 else "stop")
        assert abs(xpx * 4 - round(xpx * 4)) < 1e-6 or kind == "stop", "unit exit off the tick grid"
        rows.append(dict(date=d, session=si, k1=k1, kind=kind, side=side, unit=unit * R.M, sized=pnl * R.M, size=float(t[3]) * side,
                         epx=epx, xpx=xpx, last_close=float(C[ends[si] - 1]), last_bar=int(ends[si] - 1),
                         sigma=float(sig[si, ks - starts[si]])))
    return pd.DataFrame(rows), starts, idx


def jy(dates):
    d = pd.DatetimeIndex(dates)
    return np.where(d.month >= 7, d.year, d.year - 1)


def main():
    T, starts, idx = trades()
    print("#422 WF trades %d, unit $%.0f, sized $%.0f (anatomy parity: 2,797 / $330,878 unit)" % (
        len(T), T.unit.sum(), T.sized.sum()))
    print("exit kinds (anatomy: 745 eod / 1,943 VWAP / 109 stops):", T.kind.value_counts().to_dict())
    sess = pd.Index(sorted({idx[s].date() for s in starts if W0 <= idx[s].date() <= W1}))
    daily = T.groupby("date").sized.sum().reindex(sess, fill_value=0.0)
    base, base_dd = roc30(daily.to_numpy())
    print("#422 sized, own WF ROC@30k %.2f, max DD $%.0f, sessions %d" % (base, base_dd, len(sess)))
    rng = np.random.default_rng(SEED)

    # ---------------- N1 GAMMA-SORT: label-shuffle null of the tilt (counts per year only) ----------------
    print("\nN1 GAMMA-SORT  DIX.csv sha256 %s" % hashlib.sha256(open(DIX, "rb").read()).hexdigest()[:16])
    g = pd.read_csv(DIX, parse_dates=["date"]).set_index("date").sort_index()["gex"].astype(float)
    rk = g.rolling(253).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    gd = rk.index.date
    p = np.array([rk.iloc[np.searchsorted(gd, d) - 1] if np.searchsorted(gd, d) > 0 else np.nan for d in sess])
    lab = np.where(p <= 1 / 3, 1.5, np.where(p >= 2 / 3, 0.5, 1.0))
    lab[np.isnan(p)] = 1.0
    y = jy(sess)
    for yy in sorted(set(y)):
        m = y == yy
        print("  July-June %d: short-gamma %3d  long-gamma %3d  middle %3d" % (
            yy, (lab[m] == 1.5).sum(), (lab[m] == 0.5).sum(), (lab[m] == 1.0).sum()))
    print("  mean size %.3f (1.0 = no leverage change)" % lab.mean())
    dv = daily.to_numpy()
    nd = []
    for _ in range(DRAWS):
        sh = lab.copy()
        for yy in set(y):
            m = np.flatnonzero(y == yy)
            sh[m] = rng.permutation(sh[m])
        nd.append(roc30(dv * sh)[0] - base)
    nd = np.array(nd)
    med, p95, sd = np.median(nd), np.percentile(nd, 95), nd.std()
    print("  null delta ROC (tilt - #422): median %.2f  p95 %.2f  SD %.2f" % (med, p95, sd))
    print("  MDE 50%% = %.2f ROC points (= $%.0f a year at a $30k drawdown); 80%% = %.2f ($%.0f)" % (
        p95 - med, 1000 * (p95 - med), p95 - med + 0.84 * sd, 1000 * (p95 - med + 0.84 * sd)))

    # ---------------- N2 HALVES: band-unit power on the forward rows ----------------
    print("\nN2 HALVES (band units = signed move / (sigma x entry), cost included)")
    T["bu"] = T.side * (T.xpx - T.epx) / (T.epx * T.sigma)
    n_yr = len(T) / YRS
    for lab_, sub in (("all trades", T), ("held to close", T[T.kind == "eod"]), ("VWAP exits (failed)", T[T.kind == "vwap"]),
                      ("stops", T[T.kind == "stop"])):
        print("  %-20s n %5d (%.0f a yr)  mean %+.3f  sd %.3f band units  share %.1f%%" % (
            lab_, len(sub), len(sub) / YRS, sub.bu.mean(), sub.bu.std(), 100 * len(sub) / len(T)))
    mu, s = T.bu.mean(), T.bu.std()
    for frac, what in ((1.0, "edge gone (mean 0)"), (0.5, "edge halved")):
        n = ((1.645 + 0.84) * s / (frac * mu)) ** 2
        print("  %-20s needs %5.0f forward trades = %4.1f months at %.0f a year (80%%, one-sided 5%%)" % (
            what, n, 12 * n / n_yr, n_yr))
    fs = (T.kind == "vwap").mean()
    nf = ((1.645 * np.sqrt(fs * (1 - fs)) + 0.84 * np.sqrt((fs + .1) * (1 - fs - .1))) / 0.1) ** 2
    print("  failed-break share %.1f%%: +10 points needs %.0f forward trades = %.1f months" % (100 * fs, nf, 12 * nf / n_yr))

    # ---------------- N3 MIRROR: coin-flip sides on the schedule ----------------
    print("\nN3 MIRROR (first VWAP exit of the session, opposite side, next-open fill, held to the last close, no stop)")
    F = T[(T.kind == "vwap") & (T.k1 < T.last_bar)].groupby("session").head(1)
    mv = (F.last_close - F.xpx).to_numpy()                          # signed by PRICE, not by any side
    cost = R.COST * R.M
    fd = F.date.to_numpy()
    print("  schedule: %d trades (%.0f a year), |move| median %.1f pt" % (len(F), len(F) / YRS, np.median(np.abs(mv))))
    sess_ix = {d: i for i, d in enumerate(sess)}
    pos = np.array([sess_ix[d] for d in fd])

    def draws(mu_pt):
        out, dds, nets = [], [], []
        for _ in range(DRAWS):
            sgn = rng.choice([-1.0, 1.0], size=len(mv))
            dd_ = np.zeros(len(sess))
            np.add.at(dd_, pos, sgn * mv * R.M - cost + mu_pt * R.M)
            r, d = roc30(dd_)
            out.append(r); dds.append(d); nets.append(dd_.sum() / YRS)
        return np.array(out), np.array(dds), np.array(nets)

    r0, _, _ = draws(0.0)
    bar = max(15.0, np.percentile(r0, 95))
    print("  coin-flip null ROC@30k: median %.2f  p95 %.2f  SD %.2f  -> bar = max(15, p95) = %.2f" % (
        np.median(r0), np.percentile(r0, 95), r0.std(), bar))
    lo, hi = 0.0, 200.0
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        if np.median(draws(mid)[0]) >= bar:
            hi = mid
        else:
            lo = mid
    r1, d1, n1 = draws(hi)
    mde = hi * R.M * len(F) / YRS * 30000.0 / np.median(d1)
    print("  MDE 50%%: true edge %.1f pt a trade ($%.0f at 1 NQ) = $%.0f a year at a $30k drawdown" % (
        hi, hi * R.M, mde))
    lo2, hi2 = hi, 400.0
    for _ in range(18):
        mid = 0.5 * (lo2 + hi2)
        if np.percentile(draws(mid)[0], 20) >= bar:
            hi2 = mid
        else:
            lo2 = mid
    r2, d2, _ = draws(hi2)
    print("  MDE 80%%: %.1f pt a trade = $%.0f a year at a $30k drawdown" % (
        hi2, hi2 * R.M * len(F) / YRS * 30000.0 / np.median(d2)))


if __name__ == "__main__":
    main()

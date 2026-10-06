# -*- coding: utf-8 -*-
"""SKEWREAL r1 STAGE A - weekly realized skewness across the ten gated funds (docs/PREREG_skewreal_r1_2026-10-06.md).

Realized skewness from intraday returns predicts the next week's return with a NEGATIVE sign (Amaya, Christoffersen,
Jacobs & Vasquez 2015 JFE). Rule: at each week's last close, RSK_i = sqrt(N) x sum(r^3) / (sum(r^2))^1.5 over fund i's
within-session 5m log returns that week (no overnight return). LONG the 3 lowest, SHORT the 3 highest, filled at the next
session's open, held to the open one week later (fixed shares). Equal-risk inside each side (dollars ~ 1 / trailing
60-session daily vol, $50k a side), then BETA-NEUTRAL: a SPY overlay of -(portfolio beta to SPY, trailing 60 sessions).
The dollar-neutral book without the overlay prints as a report. Costs: 5 bps a side on the dollars traded at each
rebalance (stress 10 / 20). Price returns only (split-adjusted bars carry no dividends; disclosed).

Cells: 1-week hold = PRIMARY; 2-week hold = two staggered half-capital cohorts, each rebalanced every other week.
Family null: each week the fund labels are shuffled before the sort (same 3 long / 3 short, same sizing rule), x1,000,
statistic = the family max own ROC@$30k. Data: the photographed NOISE fund pull (ledger 2.83; masters re-hashed against
C:/EdgeLog/_anatomy_cache/noise_funds_r1/pull.json), loaded with date_to 2025-06-29. WF 2016-07-01 .. 2025-06-29.

  python tools/skewreal_r1_stageA.py --counts   -> weeks, name-weeks, eligibility (no returns)
  python tools/skewreal_r1_stageA.py --power    -> the power line from one label-shuffled (random) book
  python tools/skewreal_r1_stageA.py            -> Stage A
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
import r8_transfer_etf as R8                                            # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402
from augur_engine.paths import UPLOADS                                  # noqa: E402

FUNDS = ("SPY", "QQQ", "TLT", "XLF", "XLU", "XLV", "XLP", "XLI", "XLY", "XLK")
SIDE_USD, K, LOOK = 50_000.0, 3, 60
BPS, STRESS = (5.0, (10.0, 20.0))
WF0, WF1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
HALVES = [(WF0, pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), WF1)]
NULL_DRAWS, SEED = 1000, 20261006
PREREG = "docs/PREREG_skewreal_r1_2026-10-06.md"


def photographs():
    reg = json.load(open(os.path.join(HOME, "_anatomy_cache", "noise_funds_r1", "pull.json"), encoding="utf-8"))["registered"]
    B, D, E = R8.eng()
    for f in FUNDS:
        m = D.find_master(f, "5m", "rth", "alpaca_split_rth")
        sha = hashlib.sha256(open(os.path.join(UPLOADS, m["filename"]), "rb").read()).hexdigest()
        assert m["filename"] == reg[f + "|5m"]["filename"] and sha == reg[f + "|5m"]["sha256"], f + ": not the photographed pull"
    return len(FUNDS)


def load():
    """Per fund: session open, session close, and the session's sums of r^2 / r^3 / count of within-session 5m returns."""
    out = {}
    for f in FUNDS:
        a = R8.load(f, "5m", R8.PRE)
        ts = pd.DatetimeIndex(a["index"])
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        o, c = np.asarray(a["open"], float), np.asarray(a["close"], float)
        day = pd.DatetimeIndex(ts.normalize())
        df = pd.DataFrame({"day": day, "o": o, "c": c})
        g = df.groupby("day", sort=True)
        first_o, last_c = g.o.first(), g.c.last()
        lc = np.log(c)
        r = np.r_[np.nan, np.diff(lc)]
        newday = np.r_[True, day[1:] != day[:-1]]
        r[newday] = np.log(c[newday] / o[newday])                       # a session's first bar: its own open-to-close
        df["r2"], df["r3"] = r ** 2, r ** 3
        g = df.groupby("day", sort=True)
        out[f] = pd.DataFrame({"O": first_o, "C": last_c, "S2": g.r2.sum(), "S3": g.r3.sum(), "N": g.r2.count()})
    days = out["SPY"].index
    assert days[-1] <= WF1, "a session after 2025-06-29 is in memory - abort"
    P = {k: np.column_stack([out[f][k].reindex(days).to_numpy() for f in FUNDS]) for k in ("O", "C", "S2", "S3", "N")}
    return days, P


def weeks(days, P):
    """Per signal week: last session index L, entry index e (next session), skew per fund, sigma, beta, eligibility."""
    wk = pd.DatetimeIndex(days).to_period("W-FRI")
    codes, uniq = pd.factorize(wk)
    C = P["C"]
    ret = np.vstack([np.full(len(FUNDS), np.nan), C[1:] / C[:-1] - 1.0])
    W = []
    for w in range(len(uniq) - 1):
        idx = np.flatnonzero(codes == w)
        L = int(idx[-1])
        e = L + 1
        if e >= len(days) or L < LOOK + 1:
            continue
        S2, S3, N = (np.nansum(P[k][idx], axis=0) for k in ("S2", "S3", "N"))
        with np.errstate(invalid="ignore", divide="ignore"):
            sk = np.sqrt(N) * S3 / S2 ** 1.5
        rr = ret[L - LOOK + 1:L + 1]
        sig = np.nanstd(rr, axis=0, ddof=1)
        spy = rr[:, 0]
        beta = np.array([np.cov(rr[:, i], spy, ddof=1)[0, 1] / np.var(spy, ddof=1) if np.all(np.isfinite(rr[:, i])) else np.nan
                         for i in range(len(FUNDS))])
        ok = np.isfinite(sk) & (N >= 0.8 * np.nanmax(N)) & np.isfinite(sig) & (sig > 0) & np.isfinite(beta) & \
            np.isfinite(P["O"][e])
        W.append(dict(L=L, e=e, sk=sk, sig=sig, beta=beta, ok=ok, day=days[e]))
    return W


def prep(P, W, hold):
    """Per WF signal week with a valid exit: entry/exit session indices, eligibility, sizing inputs and the per-$ path
    (rows = funds, columns = sessions e .. exit) of fixed shares bought at the entry open and sold at the exit open."""
    O, C = P["O"], P["C"]
    recs = []
    for j, wk in enumerate(W):
        if not (WF0 <= wk["day"] <= WF1):
            continue
        xi = j + hold
        if xi >= len(W):
            break
        e, xe = wk["e"], W[xi]["e"]
        ok = wk["ok"] & np.isfinite(O[xe])
        if ok.sum() < 2 * K:
            continue
        path = np.zeros((len(FUNDS), xe - e + 1))
        path[:, 0] = (C[e] - O[e]) / O[e]
        if xe - e > 1:
            path[:, 1:-1] = ((C[e + 1:xe] - C[e:xe - 1]) / O[e]).T
        path[:, -1] = (O[xe] - C[xe - 1]) / O[e]
        recs.append(dict(j=j, coh=j % hold, e=e, xe=xe, ok=ok, path=np.nan_to_num(path), sig=wk["sig"],
                         beta=np.nan_to_num(wk["beta"]), sk=wk["sk"]))
    return recs


def book(days, recs, hold, keys=None, overlay=True, bps=BPS, side=0):
    """Daily $ P&L, shape (D, n_sessions). keys: None = the real skew sort (D = 1); else (D, n_weeks_total, n_funds)
    random keys replacing the sort (the label-shuffle null). Long the K lowest keys, short the K highest, among the
    eligible; equal-risk inside each side ($50k a side, split across `hold` cohorts); SPY overlay to zero beta.
    side: +1 / -1 keeps one side only (report; no overlay)."""
    Dn = 1 if keys is None else keys.shape[0]
    X = np.zeros((Dn, len(days)))
    prev = [np.zeros((Dn, len(FUNDS))) for _ in range(hold)]
    names = 0
    rows = np.arange(Dn)[:, None]
    for r in recs:
        kk = np.broadcast_to(r["sk"], (Dn, len(FUNDS))) if keys is None else keys[:, r["j"], :]
        okm = np.broadcast_to(r["ok"], kk.shape)
        lo = np.argsort(np.where(okm, kk, np.inf), axis=1, kind="stable")[:, :K]
        hi = np.argsort(np.where(okm, -kk, np.inf), axis=1, kind="stable")[:, :K]
        inv = 1.0 / r["sig"]
        w = np.zeros((Dn, len(FUNDS)))
        if side >= 0:
            wl = inv[lo]
            w[rows, lo] = wl / wl.sum(axis=1, keepdims=True) * SIDE_USD / hold
        if side <= 0:
            wh = inv[hi]
            w[rows, hi] = -wh / wh.sum(axis=1, keepdims=True) * SIDE_USD / hold
        if overlay and side == 0:
            w[:, 0] -= w @ r["beta"]
        names += (2 * K if side == 0 else K)
        X[:, r["e"]] -= bps / 1e4 * np.abs(w - prev[r["coh"]]).sum(axis=1)
        prev[r["coh"]] = w
        X[:, r["e"]:r["xe"] + 1] += w @ r["path"]
    return X, names


def to_book(days, x, bdays):
    return pd.Series(x, index=pd.DatetimeIndex(days)).reindex(bdays, fill_value=0.0).to_numpy()


def stats(days, x, bdays, years):
    xb = to_book(days, np.asarray(x).reshape(-1), bdays)
    st = HH.own(xb, bdays)
    yrs = [xb[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
    return xb, st, yrs


def main(argv):
    n = photographs()
    days, P = load()
    W = weeks(days, P)
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    wf_w = [w for w in W if WF0 <= w["day"] <= WF1]
    lost = int((~pd.DatetimeIndex(days[(days >= WF0)]).isin(bdays)).sum())
    print("SKEWREAL r1 - %d funds, photographs re-hashed against pull.json: OK; %d sessions %s .. %s; %d WF signal weeks; "
          "%d WF sessions not on the book's day index" % (n, len(days), days[0].date(), days[-1].date(), len(wf_w), lost))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    elig = np.array([w["ok"].sum() for w in wf_w])
    print("  COUNTS: eligible funds per WF week min %d / median %d; weeks with < 6 eligible %d; name-weeks per cell: "
          "1-week %d (%.0f a year), 2-week %d" % (elig.min(), int(np.median(elig)), int((elig < 6).sum()),
                                                  6 * int((elig >= 6).sum()), 6 * (elig >= 6).sum() / years,
                                                  6 * int((elig >= 6).sum())))
    if "--counts" in argv:
        return
    rng = np.random.default_rng(SEED)
    R1, R2 = prep(P, W, 1), prep(P, W, 2)
    if "--power" in argv:
        x, _ = book(days, R1, 1, keys=rng.random((1, len(W), len(FUNDS))))
        print("POWER LINES (one label-shuffled book on the primary's schedule; no real sort is computed)")
        HH.power_lines(to_book(days, x[0], bdays), B, years)
        return

    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", PREREG], capture_output=True, text=True,
                         cwd=ROOT).stdout.strip()
    print("  PREREG on main: %s last changed in %s" % (PREREG, sha or "NOT ON MAIN - STOP"))
    if not sha:
        return
    RD = np.asarray(bdays.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    rows = {}
    for hold, lab, R in ((1, "1-week hold  PRIMARY", R1), (2, "2-week hold (2 cohorts)", R2)):
        x, names = book(days, R, hold)
        xb, st, yrs = stats(days, x, bdays, years)
        wk = pd.Series(xb, index=bdays).groupby(bdays.to_period("W-FRI")).sum()
        wk = wk[wk != 0]
        pf = wk[wk > 0].sum() / -wk[wk < 0].sum() if (wk < 0).any() else np.inf
        rows[hold] = dict(x=x, xb=xb, st=st, yrs=yrs, pf=pf, names=names, wk=wk)
        if hold == 1:
            rr = np.sort(xb[RD])
            print("  R-DAY SUM (printed first): primary $%s over %d R days, $%s without its 3 best" % (
                format(int(rr.sum()), ","), int(RD.sum()), format(int(rr[:-3].sum()), ",")))
        print("  rebalances %d;" % len(R), end="")
        print("  %-26s name-weeks %4d (%3.0f/yr)  net $%9s  PF(weekly) %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  "
              "years + %d/9" % (lab, names, names / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","),
                                 st["roc"], st["sort"], sum(v > 0 for v in yrs)))
    # family null: shuffled fund labels each week, both cells, x NULL_DRAWS
    keys = rng.random((NULL_DRAWS, len(W), len(FUNDS)))
    X1, X2 = book(days, R1, 1, keys=keys)[0], book(days, R2, 2, keys=keys)[0]
    nmax = np.array([np.nanmax([HH.own(to_book(days, X1[i], bdays), bdays)["roc"],
                                HH.own(to_book(days, X2[i], bdays), bdays)["roc"]]) for i in range(NULL_DRAWS)])
    q95 = float(np.percentile(nmax, 95))
    print("  family null (%d weekly label shuffles, count-matched): family-max own ROC@30k p95 %.2f" % (NULL_DRAWS, q95))
    pr = rows[1]
    a1, no2020, route = HH.standalone(pr["st"], pr["pf"], pr["names"], years, pr["yrs"], pr["xb"], bdays, B,
                                      "SKEWREAL primary")
    a2 = pr["st"]["roc"] > q95
    a3 = rows[2]["st"]["net"] > 0
    ex_best = float(pr["wk"].sum() - pr["wk"].max())
    st10 = stats(days, book(days, R1, 1, bps=STRESS[0])[0], bdays, years)[1]
    bars = [("A1 standalone (%s)" % route, a1), ("A1b without 2020", no2020), ("A2 null p95 %.2f" % q95, a2),
            ("A3 2-week net > 0", a3), ("net without the best week > 0", ex_best > 0),
            ("net at 10 bps a side > 0", st10["net"] > 0)]
    ok = all(v for _, v in bars)
    power_only = (not a1) and pr["st"]["roc"] >= 15 and all(v for _, v in bars[1:])
    print("  checks: net without the best week $%s; at 10 bps a side $%s" % (format(int(ex_best), ","),
                                                                             format(int(st10["net"]), ",")))
    print("  VERDICT: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in bars),
                                   "PASS -> plugin + window-pinned Auto-Validate on a ranged file" if ok else
                                   "RESEARCH ROW (fails on count / power only)" if power_only else "FAIL (dead, no variants)"))
    HH.book_report(pr["xb"], B, years, "SKEWREAL")

    print("DIAGNOSTICS (no verdict)")
    for lab, kw in (("dollar-neutral, no SPY overlay (report)", dict(overlay=False)),
                    ("long side only (report)", dict(side=1)), ("short side only (report)", dict(side=-1))):
        x, nm = book(days, R1, 1, **kw)
        s = stats(days, x, bdays, years)[1]
        print("  %-42s net $%9s  own ROC@30k %6.2f  Sortino %5.2f" % (lab, format(int(s["net"]), ","), s["roc"], s["sort"]))
    print("  cost curve, primary net at 0 / 5 / 10 / 20 bps a side: %s" % " / ".join(
        "$" + format(int(stats(days, book(days, R1, 1, bps=b)[0], bdays, years)[1]["net"]), ",") for b in (0, 5, 10, 20)))
    for a, b in HALVES:
        m = (bdays >= a) & (bdays <= b)
        print("  half %s .. %s: net $%s" % (a.date(), b.date(), format(int(pr["xb"][m].sum()), ",")))
    print("  per WF year: %s" % ", ".join("%d $%s" % (2016 + i, format(int(v), ",")) for i, v in enumerate(pr["yrs"])))
    wk = pr["wk"]
    print("  weeks: %d traded, positive %d, mean $%+.0f, best 5: %s; worst 5: %s" % (
        len(wk), int((wk > 0).sum()), wk.mean(), ", ".join("%s $%s" % (p, format(int(v), ",")) for p, v in wk.nlargest(5).items()),
        ", ".join("%s $%s" % (p, format(int(v), ",")) for p, v in wk.nsmallest(5).items())))
    dows = pd.Series(pr["xb"], index=bdays)
    dows = dows[dows != 0]
    print("  event path, mean $ by session of the hold (Mon..Fri incl. the exit open on the next Monday): %s" % " ".join(
        "%+.0f" % v for v in dows.groupby(dows.index.dayofweek).mean().to_numpy()))
    picks = np.zeros((2, len(FUNDS)))
    for w in wf_w:
        el = np.flatnonzero(w["ok"])
        if len(el) < 2 * K:
            continue
        o = el[np.argsort(w["sk"][el], kind="stable")]
        picks[0, o[:K]] += 1
        picks[1, o[-K:]] += 1
    print("  how often each fund is long / short: %s" % ", ".join("%s %d/%d" % (f, picks[0, i], picks[1, i])
                                                               for i, f in enumerate(FUNDS)))
    print("  overlap: the same ten funds are NOISE's fund-habitat tests (intraday noise-band breakouts, docs/SCOPE_NOISE_"
          "2026-10-05.md part A); SKEWREAL holds a weekly cross-section - different mechanism, no shared position rule")


if __name__ == "__main__":
    main(sys.argv[1:])

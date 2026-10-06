# -*- coding: utf-8 -*-
"""IMPLIEDMOVE r1 STAGE A - the option market's yardstick for an expansion day, ES (docs/PREREG_impliedmove_r1_2026-10-06.md).

When the realized move runs past what options priced, hedgers who are short gamma chase it (Baltussen, Da, Lammers &
Martens 2021 JFE), and the gap between implied and realized variance is information (Bollerslev, Tauchen & Zhou 2009 RFS).
Rule: the implied daily move IM = prior-day VIX close / 100 / sqrt(252) x the session's 09:30 open. If the first hour's
range (09:30-10:30) is >= k x IM, take 1 ES at the 10:30 open in the first hour's direction (10:25 bar close vs the 09:30
open) and hold to the 15:55 bar's close. No stop. 0.363 pt a round trip, $50 a point. Intra-session only, so the ES 5m
no-adjust master is exact (the level enters only through the open, which is the real traded price).

Cells: k 1.0 and k 1.25 (no third value; MANAGER #67). The BINDING null is the realized twin: the same rule with IM
replaced by the trailing 20-session realized move (sqrt of the mean 5m realized variance x the open), its k set so the
twin has the SAME number of WF trades as the cell (count-only calibration). Beat it, or it is NOISE on ES again.
VIX = the CBOE photograph in C:/EdgeLog/_research_cache/public_series/cboe/VIX_History.csv, sha256 checked against
public_series_provenance.json before use; rows after 2025-06-29 are dropped on read.
Walk-forward stretch only (2016-07-01 .. 2025-06-29); the ES master is loaded with date_to 2025-06-29.

  python tools/impliedmove_r1_stageA.py --counts   -> trade counts, NOISE #422 overlap, R days (no returns)
  python tools/impliedmove_r1_stageA.py --power    -> the power line from a COIN-FLIP side on the primary's schedule
  python tools/impliedmove_r1_stageA.py            -> Stage A
"""
import hashlib
import json
import os
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

COST, M = 0.363, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY1 = pd.Timestamp("2016-06-30")
HOUR = np.sqrt(60.0 / 390.0)          # the implied move for ONE hour (the first hour's yardstick)
KPAIRS = {"A": [1.0, 1.25], "B": [1.25, 1.5]}       # prereg: MANAGER rules A (literal #67 numbers) or B (recommended)
RULING = "B"      # MANAGER #68: no return had been read, so B (k 1.25 / 1.5) is registered; A prints as a REPORT
CELLS = KPAIRS[RULING]
PRIMARY = CELLS[0]
SEED = 20261006
VIXDIR = os.path.join(HOME, "_research_cache", "public_series")
HALVES = [(WF0, pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), WF1)]


def vix():
    raw = os.path.join(VIXDIR, "cboe", "VIX_History.csv")
    prov = json.load(open(os.path.join(VIXDIR, "public_series_provenance.json"), encoding="utf-8"))["cboe\\VIX_History.csv"]
    sha = hashlib.sha256(open(raw, "rb").read()).hexdigest()
    assert sha == prov["sha256"], "VIX photograph does not match its provenance - abort"
    v = pd.read_csv(raw)
    v.columns = [c.strip().upper() for c in v.columns]
    v["DATE"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    v = v[v["DATE"] <= WF1].set_index("DATE")["CLOSE"].astype(float)
    return v, prov


def grid():
    A = load_master_arrays(find_master("ES", "5m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.DatetimeIndex(pd.Index(ts.date))
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    G = {}
    ok = (k >= 0) & (k < 78)
    for f in ("open", "high", "low", "close"):
        X = np.full((len(days), 78), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        G[f] = X
    full = ~np.isnan(G["close"][:, 77]) & ~np.isnan(G["open"][:, 0]) & ~np.isnan(G["open"][:, 12]) & \
        (np.isfinite(G["high"][:, :12]).sum(axis=1) >= 10)
    return days[full], {f: X[full] for f, X in G.items()}


def build():
    days, G = grid()
    O, H, L, C = G["open"], G["high"], G["low"], G["close"]
    v, prov = vix()
    # the latest VIX close strictly BEFORE session d: the session's own VIX row is never read
    vprev = pd.Series([v[v.index < d].iloc[-1] if (v.index < d).any() else np.nan for d in days], index=days)
    o0 = O[:, 0]
    im = vprev.to_numpy() / 100.0 / np.sqrt(252.0) * o0 * HOUR
    fh = np.nanmax(H[:, :12], axis=1) - np.nanmin(L[:, :12], axis=1)
    side = np.sign(C[:, 11] - o0)
    lc = np.log(C)
    r = np.concatenate([np.log(C[:, :1] / O[:, :1]), np.diff(lc, axis=1)], axis=1)
    rv = pd.Series(np.where(np.isfinite(r).sum(axis=1) >= 70, np.nansum(r ** 2, axis=1), np.nan), index=days)
    rm = np.sqrt(rv.rolling(20, min_periods=20).mean().shift(1)).to_numpy() * o0
    move = (C[:, 77] - O[:, 12]) * M                                     # $ for side +1
    path = {k: (C[:, k] - O[:, 12]) * M for k in range(17, 78, 6)}
    return dict(days=days, im=im, rm=rm, fh=fh, side=side, move=move, path=path, o12=O[:, 12], vprev=vprev.to_numpy(),
                prov=prov)


def sched(D, k, base="im"):
    ref = D[base]
    on = np.isfinite(ref) & np.isfinite(D["fh"]) & (D["fh"] >= k * ref) & (D["side"] != 0)
    return np.where(on, D["side"], 0.0)


def pnl(D, s, cost_pts=None):
    c = COST * M if cost_pts is None else cost_pts * M
    return np.where(s != 0, s * D["move"] - c, 0.0)


def twin_k(D, n_target, wf):
    """The realized-move multiple whose WF trade count equals n_target (bisection on counts only)."""
    lo, hi = 0.01, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        n = int((sched(D, mid, "rm")[wf] != 0).sum())
        lo, hi = (mid, hi) if n > n_target else (lo, mid)
    return hi


def noise_days():
    t = pd.read_csv(os.path.join(HOME, "book_legs", "NOISE422_raw_trades.csv"))
    d = pd.to_datetime(t.entry_time.str[:10])
    sd = np.where(t.side.str.lower().str.startswith("l"), 1.0, -1.0)
    return pd.Series(sd, index=d).groupby(level=0).first()


def main(argv):
    D = build()
    days = D["days"]
    wf = np.asarray((days >= WF0) & (days <= WF1))
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("IMPLIEDMOVE r1 - ES 5m RTH no-adjust, %d full sessions (%s .. %s), %d in the WF stretch; VIX photograph %s "
          "(fetched %s, sha256 %s... verified)" % (len(days), days[0].date(), days[-1].date(), int(wf.sum()),
                                                  D["prov"]["url"], D["prov"]["fetched_at"], D["prov"]["sha256"][:12]))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    print("  k pair %s = %s on the HOUR-scaled implied move (daily move x sqrt(60/390))" % (RULING, CELLS))
    S = {k: np.where(wf, sched(D, k), 0.0) for k in CELLS}
    T = {}
    for k in CELLS:
        kt = twin_k(D, int((S[k] != 0).sum()), wf)
        T[k] = (kt, np.where(wf, sched(D, kt, "rm"), 0.0))
    RD = np.asarray(days.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    if "--counts" in argv or "--power" in argv:
        nz = noise_days()
        for k in CELLS:
            s = S[k]
            n = int((s != 0).sum())
            ns = nz.reindex(days).to_numpy()
            both = (s != 0) & np.isfinite(ns)
            print("  COUNTS k %.2f: %d WF trades (%.0f a year), long %d / short %d; realized twin k %.3f -> %d trades; "
                  "both on %d days" % (k, n, n / years, int((s > 0).sum()), int((s < 0).sum()), T[k][0],
                                       int((T[k][1] != 0).sum()), int(((s != 0) & (T[k][1] != 0)).sum())))
            print("    OVERLAP (schedule only): NOISE #422 trades NQ on %d of its %d days (%.0f%%), same side on %d; "
                  "%d of its days are R days" % (int(both.sum()), n, 100 * both.sum() / max(n, 1),
                                                  int((both & (ns == s)).sum()), int(((s != 0) & RD).sum())))
        print("  R: %d of the %d WF sessions here are R days" % (int((RD & wf).sum()), int(wf.sum())))
    if "--counts" in argv:
        return
    if "--power" in argv:
        s = S[PRIMARY]
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(s))
        x = HH_daily(D, pnl(D, np.where(s != 0, coin, 0.0)), bdays)
        print("POWER LINES (coin-flip sides on the primary's schedule; no real direction is computed)")
        HH.power_lines(x, B, years)
        return

    import subprocess
    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", "docs/PREREG_impliedmove_r1_2026-10-06.md"],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip()
    print("  PREREG on main: docs/PREREG_impliedmove_r1_2026-10-06.md last changed in %s" % (sha or "NOT ON MAIN - STOP"))
    if not sha:
        return
    P0 = pnl(D, S[PRIMARY])
    rr = np.sort(P0[RD & (S[PRIMARY] != 0)])
    print("  R-DAY SUM (printed first; MANAGER #67): primary $%s over %d trade days in R, $%s without its 3 best" % (
        format(int(rr.sum()), ","), len(rr), format(int(rr[:-3].sum()), ",") if len(rr) > 3 else "-"))
    rows = {}
    for k in CELLS:
        for lab, s in (("k %.2f%s" % (k, "  PRIMARY" if k == PRIMARY else ""), S[k]),
                       ("  realized twin k %.3f" % T[k][0], T[k][1])):
            P = pnl(D, s)
            x = HH_daily(D, P, bdays)
            st = HH.own(x, bdays)
            tr = P[s != 0]
            pf = tr[tr > 0].sum() / -tr[tr < 0].sum() if (tr < 0).any() else np.inf
            yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
            rows[lab] = dict(x=x, st=st, n=len(tr), pf=pf, yrs=yrs, P=P, s=s)
            print("  %-26s n %4d (%3.0f/yr)  net $%9s  PF %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  years + %d/9" % (
                lab, len(tr), len(tr) / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","),
                st["roc"], st["sort"], sum(v > 0 for v in yrs)))
    plab = "k %.2f  PRIMARY" % PRIMARY
    pr = rows[plab]
    a1, no2020, route = HH.standalone(pr["st"], pr["pf"], pr["n"], years, pr["yrs"], pr["x"], bdays, B, "IMPLIEDMOVE primary")
    a2 = all(rows[[l for l in rows if l.startswith("k %.2f" % k)][0]]["st"]["roc"] >
             rows["  realized twin k %.3f" % T[k][0]]["st"]["roc"] for k in CELLS)
    a3 = rows["k %.2f" % CELLS[1]]["st"]["net"] > 0
    tr = pr["P"][pr["s"] != 0]
    ex_best = float(tr.sum() - tr.max())
    stress = float(pnl(D, pr["s"], cost_pts=2 * COST)[pr["s"] != 0].sum())
    se = np.where(np.asarray((days >= pd.Timestamp(D0)) & (days <= EARLY1)), sched(D, PRIMARY), 0.0)
    early = float(pnl(D, se)[se != 0].sum())
    print("  checks: net without the best trade $%s; at 2x cost $%s; EARLY 2010-06..2016-06 n %d net $%s" % (
        format(int(ex_best), ","), format(int(stress), ","), int((se != 0).sum()), format(int(early), ",")))
    bars = [("A1 standalone (%s)" % route, a1), ("A1b without 2020", no2020),
            ("A2 beats the count-matched realized twin, both cells", a2), ("A3 k 1.25 net > 0", a3),
            ("net ex-best > 0", ex_best > 0), ("2x cost net > 0", stress > 0), ("EARLY net > 0", early > 0)]
    ok = all(v for _, v in bars)
    print("  VERDICT: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in bars),
                                   "PASS -> plugin + window-pinned Auto-Validate on a ranged file" if ok else
                                   "FAIL (dead, no variants)"))
    HH.book_report(pr["x"], B, years, "IMPLIEDMOVE")
    for k in [k for k in KPAIRS["A"] if k not in CELLS]:                  # MANAGER #68: pair A is a REPORT, never a cell
        sa = np.where(wf, sched(D, k), 0.0)
        kt = twin_k(D, int((sa != 0).sum()), wf)
        for lab, s in (("REPORT pair A k %.2f" % k, sa), ("REPORT its realized twin k %.3f" % kt,
                                                          np.where(wf, sched(D, kt, "rm"), 0.0))):
            st = HH.own(HH_daily(D, pnl(D, s), bdays), bdays)
            print("  %-32s n %4d  net $%9s  own ROC@30k %6.2f  Sortino %5.2f" % (
                lab, int((s != 0).sum()), format(int(st["net"]), ","), st["roc"], st["sort"]))

    print("DIAGNOSTICS (no verdict)")
    on = pr["s"] != 0
    print("  event path, mean $ a trade at each half-hour close 11:00 .. 15:55: %s" % " ".join(
        "%+.0f" % np.nanmean(pr["s"][on] * D["path"][k][on]) for k in sorted(D["path"])))
    for a, b in HALVES:
        m = on & np.asarray((days >= a) & (days <= b))
        print("  half %s .. %s: n %d net $%s mean $%+.0f" % (a.date(), b.date(), int(m.sum()),
                                                          format(int(pr["P"][m].sum()), ","), pr["P"][m].mean()))
    for sd, nm in ((1, "long"), (-1, "short")):
        m = pr["s"] == sd
        print("  %-6s n %4d net $%9s mean $%+.0f" % (nm, int(m.sum()), format(int(pr["P"][m].sum()), ","),
                                                   pr["P"][m].mean() if m.any() else float("nan")))
    print("  cost curve (bps of the entry price, round trip) 0 / 5 / 10 / 20: %s" % " / ".join(
        "$" + format(int(np.where(on, pr["s"] * D["move"] - bp / 1e4 * D["o12"] * M, 0.0).sum()), ",")
        for bp in (0, 5, 10, 20)))
    print("  per WF year: %s" % ", ".join("%d $%s" % (2016 + i, format(int(v), ",")) for i, v in enumerate(pr["yrs"])))
    for lab, m in (("prior VIX < 20", on & (D["vprev"] < 20)), ("prior VIX >= 20", on & (D["vprev"] >= 20))):
        print("  %-16s n %4d net $%9s mean $%+.0f" % (lab, int(m.sum()), format(int(pr["P"][m].sum()), ","),
                                                     pr["P"][m].mean() if m.any() else float("nan")))
    cand = np.zeros((len(days), 78))
    cand[on, 12:] = pr["s"][on][:, None]
    print("  REPORT overlap with #463 NQ legs (bars held, ES side vs NQ legs): %s" % HH.overlap(cand, HH.book_positions(days)))


def HH_daily(D, x, bdays):
    return pd.Series(x, index=D["days"]).reindex(bdays, fill_value=0.0).to_numpy()


if __name__ == "__main__":
    main(sys.argv[1:])

# -*- coding: utf-8 -*-
"""RELVOL r1 STAGE A - ES-vs-NQ relative volatility, beta-neutral, one session (docs/PREREG_relvol_r1_2026-10-06.md).

High idiosyncratic volatility earns low future returns (Ang, Hodrick, Xing & Zhang 2006 JF; 2009 JFE). At the index level,
NQ's volatility in excess of ES's is the tech-specific part. Rule: at each RTH close, Q = sqrt(sum of NQ's 5m realized
variance over the last L sessions / the same for ES); its percentile among the previous 252 sessions' Q. In the top
(1 - q) tail, SHORT 1 NQ and LONG h ES for the NEXT session (09:30 open to the 15:55 bar's close); in the bottom tail, the
mirror. h = beta x NQ notional / ES notional at the entry open, beta = OLS slope of NQ's open-to-close log return on ES's
over the previous 60 sessions. Cost 0.533 pt NQ ($20) + h x 0.363 pt ES ($50) a round trip. No stop, never held overnight,
so the no-adjust masters are exact (every return is inside one session).

Cells (L, q): (20, 0.9) PRIMARY, (20, 0.8), (40, 0.9). Family null: each cell's signal days per July-June year, with
their sides, moved to random sessions of the same year (keeps count, side mix and NQ-vs-ES drift; removes the timing).
Walk-forward stretch only (2016-07-01 .. 2025-06-29); both masters are loaded with date_to 2025-06-29.

  python tools/relvol_r1_stageA.py --counts   -> trade counts per cell (no returns)
  python tools/relvol_r1_stageA.py --power    -> the power line from a COIN-FLIP side on the primary's schedule
  python tools/relvol_r1_stageA.py            -> Stage A
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402

C_NQ, C_ES, M_NQ, M_ES = 0.533, 0.363, 20.0, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY1 = pd.Timestamp("2016-06-30")
PRIMARY = (20, 0.9)
CELLS = [PRIMARY, (20, 0.8), (40, 0.9)]
NULL_DRAWS, SEED = 1000, 20261006
HALVES = [(WF0, pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), WF1)]


def grid(root):
    """(days, O, C): (D, 78) 5m open / close on RTH sessions that have their 15:55 bar."""
    A = load_master_arrays(find_master(root, "5m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    o, c = np.asarray(A["open"], float), np.asarray(A["close"], float)
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.DatetimeIndex(pd.Index(ts.date))
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    O = np.full((len(days), 78), np.nan)
    C = np.full((len(days), 78), np.nan)
    ok = (k >= 0) & (k < 78)
    O[di[ok], k[ok]] = o[ok]
    C[di[ok], k[ok]] = c[ok]
    full = ~np.isnan(C[:, 77]) & ~np.isnan(O[:, 0])
    return days[full], O[full], C[full]


def build():
    dE, OE, CE = grid("ES")
    dN, ON, CN = grid("NQ")
    days = dE.intersection(dN)
    ie, inq = dE.get_indexer(days), dN.get_indexer(days)
    OE, CE, ON, CN = OE[ie], CE[ie], ON[inq], CN[inq]

    def rv(O, C):
        lc = np.log(C)
        r = np.diff(lc, axis=1)
        r = np.concatenate([np.log(C[:, :1] / O[:, :1]), r], axis=1)
        good = np.isfinite(r).sum(axis=1) >= 70
        return np.where(good, np.nansum(r ** 2, axis=1), np.nan)

    rvE, rvN = pd.Series(rv(OE, CE), days), pd.Series(rv(ON, CN), days)
    ocE, ocN = pd.Series(np.log(CE[:, 77] / OE[:, 0]), days), pd.Series(np.log(CN[:, 77] / ON[:, 0]), days)
    beta = (ocN.rolling(60).cov(ocE) / ocE.rolling(60).var())
    pct = {}
    for L in sorted({c[0] for c in CELLS}):
        q = np.sqrt(rvN.rolling(L, min_periods=L).sum() / rvE.rolling(L, min_periods=L).sum())
        pct[L] = q.rolling(253, min_periods=253).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    # trade on session t from the signal at close t-1
    b = beta.shift(1).to_numpy()
    h = b * (ON[:, 0] * M_NQ) / (OE[:, 0] * M_ES)
    spread = (CN[:, 77] - ON[:, 0]) * M_NQ - h * (CE[:, 77] - OE[:, 0]) * M_ES     # $ for side +1 (long NQ / short ES)
    cost = C_NQ * M_NQ + h * C_ES * M_ES
    notional = ON[:, 0] * M_NQ + np.abs(h) * OE[:, 0] * M_ES
    path = {k: (CN[:, k] - ON[:, 0]) * M_NQ - h * (CE[:, k] - OE[:, 0]) * M_ES for k in range(5, 78, 6)}
    rel20 = (ocN - ocE).rolling(20).sum()
    relpct = rel20.rolling(253, min_periods=253).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    return dict(days=days, h=h, spread=spread, cost=cost, notional=notional, path=path,
                pct={L: p.shift(1).to_numpy() for L, p in pct.items()}, relpct=relpct.shift(1).to_numpy(), beta=b)


def engu_held(days):
    """True on sessions where ENGU-Q #335 (raw book leg export, all long) holds a position at any time of the day."""
    t = pd.read_csv(os.path.join(os.environ.get("EDGELOG_HOME") or "C:/EdgeLog", "book_legs", "ENGUQ335_raw_trades.csv"))
    held = set()
    for a, b in zip(pd.to_datetime(t.entry_time.str[:10]), pd.to_datetime(t.exit_time.str[:10])):
        held.update(pd.date_range(a, b, freq="D"))
    return np.asarray(days.isin(pd.DatetimeIndex(sorted(held))))


def r_days(days):
    """True on R's days: L = #463 + 0.264 x RES, its 45 drawdown episodes (ledger 2.79; q19/residual_days.csv in_R)."""
    r = pd.read_csv(os.path.join(os.environ.get("EDGELOG_HOME") or "C:/EdgeLog", "_anatomy_cache", "q19", "residual_days.csv"))
    return np.asarray(days.isin(pd.DatetimeIndex(pd.to_datetime(r.date[r.in_R.astype(bool)]))))


def sides(D, L, q):
    p = D["pct"][L]
    s = np.zeros(len(p))
    s[p >= q] = -1.0
    s[p <= 1.0 - q] = 1.0
    s[~np.isfinite(D["h"]) | ~np.isfinite(D["spread"])] = 0.0
    return s


def pnl(D, s, cost_mult=1.0, cost_override=None):
    c = D["cost"] * cost_mult if cost_override is None else cost_override
    return np.where(s != 0, s * D["spread"] - c, 0.0)


def daily(D, x, bdays):
    return pd.Series(x, index=D["days"]).reindex(bdays, fill_value=0.0).to_numpy()


def in_wf(D):
    return np.asarray((D["days"] >= WF0) & (D["days"] <= WF1))


def year_block(d):
    return np.where(d.month >= 7, d.year, d.year - 1)


def main(argv):
    D = build()
    days = D["days"]
    wf = in_wf(D)
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("RELVOL r1 - ES and NQ 5m RTH no-adjust, %d common full sessions (%s .. %s), %d in the WF stretch" % (
        len(days), days[0].date(), days[-1].date(), int(wf.sum())))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    print("  hedge h (ES per NQ) in WF: median %.2f, 5-95%% %.2f-%.2f" % (
        np.nanmedian(D["h"][wf]), np.nanpercentile(D["h"][wf], 5), np.nanpercentile(D["h"][wf], 95)))
    S = {c: np.where(wf, sides(D, *c), 0.0) for c in CELLS}

    EH, RD = engu_held(days), r_days(days)
    if "--counts" in argv or "--power" in argv:
        for c in CELLS:
            s = S[c]
            print("  COUNTS L %d q %.1f: %d WF trades (%.0f a year): short-NQ %d, long-NQ %d" % (
                c[0], c[1], int((s != 0).sum()), (s != 0).sum() / years, int((s < 0).sum()), int((s > 0).sum())))
        s = S[PRIMARY]
        for sd, nm in ((-1, "short-NQ arm"), (1, "long-NQ arm")):
            m = s == sd
            print("  OVERLAP (schedule only) primary %s: ENGU-Q #335 holds its long on %d of %d trade days (%.0f%%); "
                  "%d of them are R days" % (nm, int((m & EH).sum()), int(m.sum()), 100 * (m & EH).sum() / max(m.sum(), 1),
                                              int((m & RD).sum())))
        print("  R: %d of the %d WF sessions here are R days; ENGU-Q #335 holds on %d%% of all WF sessions" % (
            int((RD & wf).sum()), int(wf.sum()), round(100 * (EH & wf).sum() / wf.sum())))
    if "--counts" in argv:
        return
    if "--power" in argv:
        s = S[PRIMARY]
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(s))
        x = daily(D, pnl(D, np.where(s != 0, coin, 0.0)), bdays)
        print("POWER LINES (coin-flip sides on the primary's schedule; no real direction is computed)")
        HH.power_lines(x, B, years)
        return

    import subprocess
    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", "docs/PREREG_relvol_r1_2026-10-06.md"],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip()
    print("  PREREG on main: docs/PREREG_relvol_r1_2026-10-06.md last changed in %s" % (sha or "NOT ON MAIN - STOP"))
    if not sha:
        return
    P0 = pnl(D, S[PRIMARY])
    rr = np.sort(P0[RD & (S[PRIMARY] != 0)])
    print("  R-DAY SUM (printed first; MANAGER #67 (3)): primary $%s over %d trade days in R, $%s without its 3 best; "
          "short-NQ arm $%s, long-NQ arm $%s" % (
              format(int(rr.sum()), ","), len(rr), format(int(rr[:-3].sum()), ",") if len(rr) > 3 else "-",
              format(int(P0[RD & (S[PRIMARY] < 0)].sum()), ","), format(int(P0[RD & (S[PRIMARY] > 0)].sum()), ",")))
    rows = {}
    for c in CELLS:
        s = S[c]
        P = pnl(D, s)
        x = daily(D, P, bdays)
        st = HH.own(x, bdays)
        n = int((s != 0).sum())
        tr = P[s != 0]
        pf = tr[tr > 0].sum() / -tr[tr < 0].sum() if (tr < 0).any() else np.inf
        yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
        rows[c] = dict(x=x, st=st, n=n, pf=pf, yrs=yrs, P=P, s=s)
        print("  %-20s n %4d (%3.0f/yr)  net $%9s  PF %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  years + %d/9" % (
            "L %d q %.1f%s" % (c[0], c[1], "  PRIMARY" if c == PRIMARY else ""), n, n / years,
            format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
            sum(v > 0 for v in yrs)))

    # family null: signal days (with their sides) moved to random sessions of the same July-June year
    rng = np.random.default_rng(SEED)
    yb = year_block(days)
    wf_idx = {y: np.flatnonzero(wf & (yb == y)) for y in np.unique(yb[wf])}
    nmax = np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        vals = []
        for c in CELLS:
            s = S[c]
            sn = np.zeros(len(s))
            for y, ix in wf_idx.items():
                sv = s[ix][s[ix] != 0]
                if len(sv):
                    sn[rng.choice(ix, size=len(sv), replace=False)] = sv
            vals.append(HH.own(daily(D, pnl(D, sn), bdays), bdays)["roc"])
        nmax[i] = np.nanmax(vals)
    q95 = float(np.percentile(nmax, 95))
    print("  family null (%d same-year date shuffles): family-max own ROC@30k p95 %.2f" % (NULL_DRAWS, q95))

    pr = rows[PRIMARY]
    a1, no2020, route = HH.standalone(pr["st"], pr["pf"], pr["n"], years, pr["yrs"], pr["x"], bdays, B, "RELVOL primary")
    a2 = pr["st"]["roc"] > q95
    a3 = all(rows[c]["st"]["net"] > 0 for c in CELLS if c != PRIMARY)
    tr = pr["P"][pr["s"] != 0]
    ex_best = float(tr.sum() - tr.max())
    stress = float(pnl(D, pr["s"], cost_mult=2.0)[pr["s"] != 0].sum())
    se = np.where(np.asarray((days >= pd.Timestamp(D0)) & (days <= EARLY1)), sides(D, *PRIMARY), 0.0)
    early = float(pnl(D, se)[se != 0].sum())
    print("  checks: net without the best trade $%s; at 2x cost $%s; EARLY 2010-06..2016-06 n %d net $%s" % (
        format(int(ex_best), ","), format(int(stress), ","), int((se != 0).sum()), format(int(early), ",")))
    bars = [("A1 standalone (%s)" % route, a1), ("A1b without 2020", no2020), ("A2 null p95 %.2f" % q95, a2),
            ("A3 neighbours net > 0", a3), ("net ex-best > 0", ex_best > 0), ("2x cost net > 0", stress > 0),
            ("EARLY net > 0", early > 0)]
    ok = all(v for _, v in bars)
    print("  VERDICT: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in bars),
                                   "PASS -> plugin + pinned Auto-Validate" if ok else "FAIL (dead, no variants)"))
    HH.book_report(pr["x"], B, years, "RELVOL")

    print("DIAGNOSTICS (no verdict)")
    on = pr["s"] != 0
    print("  event path, mean $ a trade at each half-hour close 10:00 .. 15:55: %s" % " ".join(
        "%+.0f" % np.nanmean(pr["s"][on] * D["path"][k][on]) for k in sorted(D["path"])))
    for a, b in HALVES:
        m = on & np.asarray((days >= a) & (days <= b))
        print("  half %s .. %s: n %d net $%s mean $%+.0f" % (a.date(), b.date(), int(m.sum()),
                                                          format(int(pr["P"][m].sum()), ","), pr["P"][m].mean()))
    for sd, nm in ((-1, "short NQ / long ES (top tail)"), (1, "long NQ / short ES (bottom tail)")):
        m = pr["s"] == sd
        print("  %-34s n %4d net $%9s mean $%+.0f" % (nm, int(m.sum()), format(int(pr["P"][m].sum()), ","),
                                                     pr["P"][m].mean() if m.any() else float("nan")))
    print("  cost curve (bps of notional, both legs) 0 / 5 / 10 / 20: %s" % " / ".join(
        "$" + format(int(pnl(D, pr["s"], cost_override=bp / 1e4 * D["notional"])[on].sum()), ",") for bp in (0, 5, 10, 20)))
    print("  per WF year: %s" % ", ".join("%d $%s" % (2016 + i, format(int(v), ",")) for i, v in enumerate(pr["yrs"])))
    ep, cur = [], None
    for i in np.flatnonzero(on):
        if cur and i == cur[1] + 1 and pr["s"][i] == cur[2]:
            cur = (cur[0], i, cur[2], cur[3] + pr["P"][i])
        else:
            if cur:
                ep.append(cur)
            cur = (i, i, pr["s"][i], pr["P"][i])
    if cur:
        ep.append(cur)
    epv = np.array([e[3] for e in ep])
    top = sorted(ep, key=lambda e: -abs(e[3]))[:5]
    print("  episodes: %d, mean $%+.0f, positive %d; largest: %s" % (len(ep), epv.mean(), int((epv > 0).sum()), "; ".join(
        "%s..%s %s $%s" % (days[e[0]].date(), days[e[1]].date(), "shortNQ" if e[2] < 0 else "longNQ", format(int(e[3]), ","))
        for e in top)))
    # MANAGER #68 (1): the scope's 5-session hold as a REPORT, never a cell. RTH only - each of the 5 sessions is opened
    # and closed inside the session (5 round trips; overnight excluded, so no roll gap enters), non-overlapping episodes.
    s5 = np.zeros(len(days))
    last = -1
    for i in np.flatnonzero(pr["s"] != 0):
        if i > last:
            s5[i:i + 5] = pr["s"][i]
            last = i + 4
    s5 = np.where(wf, s5, 0.0)
    P5 = pnl(D, s5)
    st5 = HH.own(daily(D, P5, bdays), bdays)
    print("  REPORT 5-session hold (RTH only, re-entered each session): %d episodes, %d sessions, net $%s, own ROC@30k "
          "%.2f, Sortino %.2f" % (int(np.sum((s5 != 0) & (np.r_[0, s5[:-1]] != s5))), int((s5 != 0).sum()),
                                  format(int(st5["net"]), ","), st5["roc"], st5["sort"]))
    rp = D["relpct"][on]
    ok_ = np.isfinite(rp)
    print("  signal vs 20-day relative RETURN percentile: corr %.2f (sides vs relative return, %d trades)" % (
        float(np.corrcoef(pr["s"][on][ok_], rp[ok_])[0, 1]), int(ok_.sum())))
    cand = np.zeros((len(days), 78))
    cand[on] = (pr["s"][on])[:, None]                       # the NQ leg's side, held all session
    print("  REPORT overlap with #463 NQ legs (NQ leg's held bars): %s" % HH.overlap(cand, HH.book_positions(days)))


if __name__ == "__main__":
    main(sys.argv[1:])

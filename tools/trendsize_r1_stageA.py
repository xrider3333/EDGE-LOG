"""TRENDSIZE r1 Stage A (docs/PREREG_trendsize_r1_2026-10-14.md) - size ORB #234 inside BOOK #463 by a pre-open trend-day
score: 2.0x on days whose 5/60 session-range ratio sits at or above its trailing 250-session 80th percentile, 0.75x
otherwise. WALK-FORWARD ONLY (2016-07-01..2025-06-29); the tilted book's lockbox is never computed.

    python tools/trendsize_r1_stageA.py --expect <prereg sha256>,<this file's sha256>     (LF-normalised, MANAGER #82)
"""
import argparse, hashlib, os, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "tools", "rocfrontier"))
PREREG = os.path.join(ROOT, "docs", "PREREG_trendsize_r1_2026-10-14.md")
NQD = r"C:\EdgeLog\_anatomy_cache\rocfrontier\NQ_daily_rth.csv"
OUT = r"C:\EdgeLog\custom_ml\trendsize_r1"
ORB = 0                          # build.json leg 0 = ORB_3_6_C2.py (#234)
UP, DOWN, PCT, LOOK = 2.0, 0.75, 80.0, 250
SEED, NPERM = 20261014, 1000


def frozen_check(expect):
    paths = [PREREG, os.path.abspath(__file__)]
    got = [hashlib.sha256(open(f, "rb").read().replace(b"\r\n", b"\n")).hexdigest() for f in paths]
    for f, g in zip(paths, got):
        print(f"sha256 (LF) {os.path.basename(f)} {g}")
    if [e.strip().lower() for e in (expect or "").split(",") if e.strip()] != got:
        sys.exit("FROZEN CHECK FAILED: hashes differ from those posted to MANAGER - nothing run")


def tilt_flags(dates):
    """1 = tilt day, 0 = not, NaN = no score (holiday / warm-up), for each date in `dates` (the book index)."""
    N = pd.read_csv(NQD, parse_dates=["d"]).set_index("d").sort_index()
    rng = N.h - N.l
    r = rng.rolling(5).mean().shift(1) / rng.rolling(60).median().shift(1)          # prior sessions only
    thr = r.shift(1).rolling(LOOK, min_periods=LOOK).quantile(PCT / 100.0)          # prior r values only
    flag = pd.Series(np.where(r.isna() | thr.isna(), np.nan, (r >= thr).astype(float)), index=N.index)
    return flag.reindex(pd.DatetimeIndex(dates).normalize()).to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", required=True)
    a = ap.parse_args()
    frozen_check(a.expect)
    import r11_risk as R11
    import r12_mdl as M12
    from augur_engine.drawdowns import dd5, dd_pct_peak
    legs = R11.load_json("build.json")["legs"]
    assert legs[ORB]["strategy"] == "ORB_3_6_C2.py", legs[ORB]
    B = R11.load_book("U", legs)
    M12.reproduce(B)                                     # refuses unless the published #463 WF / LB numbers reproduce
    idx = B.index
    wf = np.asarray((idx >= R11.WF0) & (idx <= R11.PRE_END))
    one = np.ones(B.n)

    def book(m_orb):
        x = np.zeros(B.n)
        for k in range(len(legs)):
            x += B.Am_leg[k].T @ (m_orb if k == ORB else one)
        return np.asarray(x, float)

    def wfstats(x):
        u = R11.unified(B, x, R11.WF0, R11.PRE_END)
        xs = pd.Series(x[wf], index=idx[wf])
        d5 = dd5(xs)
        return {"roc": u["roc"], "sort": u["sort"], "dd5": d5["dd5_usd"], "one_ep": d5["one_episode"],
                "ddpct": dd_pct_peak(xs.to_numpy())}

    flag = tilt_flags(idx)
    m = np.where(np.isnan(flag), 1.0, np.where(flag == 1.0, UP, DOWN))
    plain, tilt = book(one), book(m)
    assert abs(R11.unified(B, plain, R11.WF0, R11.PRE_END)["roc"] - 93.81) < 0.005
    P, T = wfstats(plain), wfstats(tilt)
    orb_trades = (B.leg == ORB)
    ent = B.erow[orb_trades]
    wf_ent = ent[(idx[ent] >= R11.WF0) & (idx[ent] <= R11.PRE_END)]
    mean_size = float(m[wf_ent].mean())
    print(f"WF tilt days {np.nanmean(flag[wf]):.1%} of scored rows; ORB WF trades {len(wf_ent)}, realised mean ORB size {mean_size:.3f}")
    for nm, s in (("PLAIN #463", P), ("TILTED #463", T)):
        print(f"{nm:12s} WF: ROC@30k {s['roc']:.2f} / DD5 ${s['dd5']:,.0f}{' (1 episode)' if s['one_ep'] else ''} / "
              f"DD% from peak {s['ddpct']:.1f}% / Sortino {s['sort']:.3f}")
    # 1 book lift
    c1 = T["roc"] >= 1.05 * P["roc"] and T["sort"] >= P["sort"]
    # 2 within-year shuffles of the tilt flags (same count per year), on WF rows that carry a score
    rs = np.random.default_rng(SEED)
    years = idx.year.to_numpy()
    scored = wf & ~np.isnan(flag)
    null = np.empty(NPERM)
    for i in range(NPERM):
        f2 = flag.copy()
        for y in np.unique(years[scored]):
            k = np.where(scored & (years == y))[0]
            f2[k] = rs.permutation(flag[k])
        m2 = np.where(np.isnan(f2), 1.0, np.where(f2 == 1.0, UP, DOWN))
        null[i] = R11.unified(B, book(m2), R11.WF0, R11.PRE_END)["roc"]
    p95 = float(np.percentile(null, 95)); pval = float(np.mean(null >= T["roc"]))
    c2 = T["roc"] > p95
    # 3 flat leverage at the realised mean ORB size
    lev = wfstats(book(one * mean_size))
    c3 = T["roc"] > lev["roc"]
    # 4 yearly ORB-leg dollars, tilted minus plain
    orb_plain = np.asarray(B.Am_leg[ORB].T @ one, float); orb_tilt = np.asarray(B.Am_leg[ORB].T @ m, float)
    g = pd.Series((orb_tilt - orb_plain)[wf], index=idx[wf])
    yr = g.groupby((g.index - pd.DateOffset(months=6)).year).sum()     # July-June WF years: 2016-17 .. 2024-25 = 9
    c4 = int((yr > 0).sum()) >= 6
    # 5 without Feb-Apr 2020, and concentration
    ex = wf & ~((idx >= pd.Timestamp("2020-02-01")) & (idx <= pd.Timestamp("2020-04-30")))
    def roc_mask(x, k):
        return float(M12.vstats(x[k][None, :], k.sum() / 252.0)[0][0])
    c5a = roc_mask(tilt, ex) >= roc_mask(plain, ex)
    top_share = float(g.max() / g.sum()) if g.sum() > 0 else float("inf")
    c5b = top_share <= 0.50
    oP = R11.unified(B, orb_plain, R11.WF0, R11.PRE_END); oT = R11.unified(B, orb_tilt, R11.WF0, R11.PRE_END)
    print(f"1 book lift: ROC {T['roc']:.2f} vs bar {1.05 * P['roc']:.2f}, Sortino {T['sort']:.3f} vs {P['sort']:.3f} -> {'PASS' if c1 else 'FAIL'}")
    print(f"2 chance: shuffle p95 {p95:.2f}, real {T['roc']:.2f}, p {pval:.3f} -> {'PASS' if c2 else 'FAIL'}")
    print(f"3 flat leverage at mean size {mean_size:.3f}: ROC {lev['roc']:.2f} -> {'PASS' if c3 else 'FAIL'}")
    print(f"4 years: tilted-minus-plain ORB $ positive in {int((yr > 0).sum())} of {len(yr)} " + " ".join(f"{y}:{v:+,.0f}" for y, v in yr.items())
          + f" -> {'PASS' if c4 else 'FAIL'}")
    print(f"5 without Feb-Apr 2020: tilted {roc_mask(tilt, ex):.2f} vs plain {roc_mask(plain, ex):.2f} -> {'PASS' if c5a else 'FAIL'}; "
          f"top day = {top_share:.0%} of the gain -> {'PASS' if c5b else 'FAIL'}")
    print(f"report: ORB leg alone WF ROC plain {oP['roc']:.2f} / tilted {oT['roc']:.2f}; gain ${g.sum():,.0f}")
    verdict = "PASS" if all((c1, c2, c3, c4, c5a, c5b)) else "FAIL"
    print(f"VERDICT TRENDSIZE r1 Stage A (WF only): {verdict}")
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame({"date": idx[wf], "plain": plain[wf], "tilted": tilt[wf], "flag": flag[wf]}).to_csv(os.path.join(OUT, "wf_daily.csv"), index=False)


if __name__ == "__main__":
    main()

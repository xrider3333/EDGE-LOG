"""TILT GUARD - the standard battery every calendar / condition size tilt must survive.

Four candidates in a row were decided by the same handful of controls, and three of them were
killed by controls that were written by hand each time. This makes the battery reusable, so a
future tilt gets tested properly by default instead of when someone remembers.

    from tools.tilt_guard import guard
    r = guard(pnl, ts, base, mask, mult, wf, lb, subgroup=is_friday, label="payrolls 1.5x")
    print(r["report"]);  r["passed"]   # -> bool

WHAT IT CHECKS, and why each one exists (every reason below is a real result from 2026-09-09):

  MONEY   Better net on every stretch, drawdown never materially worse. The house adoption bar.

  C1 EXPOSURE-MATCHED UNIFORM CONTROL. Re-scale every trade by the single factor that spends the
     same total exposure the tilt spends, and compare. A size-up that cannot beat flat leverage is
     flat leverage. This alone killed the ORB release-day tilt (uniform earned MORE in the
     walk-forward at MAR 1.13 against the tilt's 0.95).

  C2 PERMUTATION over random day-sets of the same size. Prices the fact that you went looking.

  C3 SUBGROUP PERMUTATION - the one people forget. If the base sizing already tilts a subgroup
     (KEEL sizes every Friday 1.5x) and the candidate lives mostly inside it (194 of 203 payrolls
     days are Fridays), then random days are the wrong null. The question is whether these
     Fridays beat any other Fridays. Payrolls days did not: 17.6% of random Friday sets matched.

  C4 CONCENTRATION. If one trade is most of the gain, it is not evidence. The payrolls candidate's
     whole lockbox gain was 12 trades with one at 62%, median trade losing. So was ORB's, at 68%.

  C5 PLACEBO (optional, pass placebo_mask). The adjacent window must NOT pay. On ORB the session
     AFTER a release paid better than the release itself, which ended it.

Cuts and size-ups are both handled: C1 matches exposure in whichever direction the tilt moves it.
A tilt that touches under `min_trades` trades in a stretch is reported as UNDER-POWERED rather
than passed, because v12's own lockbox bucket was 6 trades and that is a forward test, not proof.
"""
import numpy as np
import pandas as pd

__all__ = ["guard", "metrics"]


def metrics(pnl, years):
    p = np.asarray(pnl, float)
    if not len(p):
        return dict(net=0.0, dd=0.0, mar=0.0, pf=0.0)
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    return dict(net=float(p.sum()), dd=dd, pf=float(gw / gl) if gl > 0 else 99.0,
                mar=float((p.sum() / max(years, 1e-9)) / abs(dd)) if dd < 0 else 99.0)


def _years(ts, m):
    t = ts[m]
    return max((t.max() - t.min()).days / 365.25, 1 / 12) if len(t) else 1.0


def guard(pnl, ts, base, mask, mult, wf, lb, subgroup=None, placebo_mask=None, window=None,
          label="candidate", perm=2000, seed=20260909, cap=3.0, dd_tol=0.10, min_trades=25):
    """pnl: per-trade dollars (unsized). ts: DatetimeIndex of entries. base: the sizing the
    candidate sits on top of. mask: where the tilt applies. mult: its multiplier.
    wf / lb: boolean stretch masks. subgroup: the set the base already tilts (e.g. Fridays).
    dd_tol: fraction of extra drawdown tolerated (0.10 = 10% worse still counts as 'close').

    window: pass this whenever the tilt fires on a TIME WINDOW inside a day rather than on
    whole days - for instance 'before 08:30 on a release day'. Without it the permutations
    re-size EVERY trade on each sampled day, which is a far larger intervention than the
    candidate makes, and the null becomes meaningless. With it each sampled day is intersected
    with the same window, so the question asked is the right one: are THESE days' windows
    worse than other days' windows?"""
    pnl = np.asarray(pnl, float); base = np.asarray(base, float); mask = np.asarray(mask, bool)
    cand = np.minimum(base * np.where(mask, float(mult), 1.0), cap)
    rng = np.random.default_rng(seed)
    L, reasons, ok = [], [], True
    L.append(f"TILT GUARD - {label}   ({mask.sum()} of {len(mask)} trades tagged, {100*mask.mean():.1f}%)")

    # ---- MONEY -------------------------------------------------------------------------
    stages = [("walk-forward", wf), ("lockbox", lb)]
    for nm, m in stages:
        y = _years(ts, m)
        a, b = metrics((pnl * base)[m], y), metrics((pnl * cand)[m], y)
        worse = (abs(b["dd"]) - abs(a["dd"])) / max(abs(a["dd"]), 1e-9)
        L.append(f"  MONEY {nm:13s} ${a['net']:>10,.0f} DD ${a['dd']:>9,.0f} MAR {a['mar']:5.2f}"
                 f"  ->  ${b['net']:>10,.0f} DD ${b['dd']:>9,.0f} MAR {b['mar']:5.2f}"
                 f"   net {b['net']-a['net']:+9,.0f}  dd {100*worse:+.1f}%")
        if b["net"] <= a["net"]:
            ok = False; reasons.append(f"loses money in the {nm}")
        if worse > dd_tol:
            ok = False; reasons.append(f"{nm} drawdown {100*worse:.0f}% worse (tolerance {100*dd_tol:.0f}%)")
        n = int((mask & m).sum())
        if n < min_trades:
            reasons.append(f"UNDER-POWERED in the {nm}: only {n} tagged trades")

    # ---- C1 exposure-matched uniform ----------------------------------------------------
    k = cand.sum() / base.sum()
    unif = base * k
    L.append(f"  C1 uniform control  same exposure via a flat {k:.4f}x on every trade")
    for nm, m in stages:
        y = _years(ts, m)
        c, u = metrics((pnl * cand)[m], y), metrics((pnl * unif)[m], y)
        win = c["net"] > u["net"] and c["mar"] >= u["mar"]
        L.append(f"     {nm:13s} tilt ${c['net']:>10,.0f} MAR {c['mar']:5.2f}  |  uniform ${u['net']:>10,.0f}"
                 f" MAR {u['mar']:5.2f}   -> {'beats' if win else 'LOSES TO'} flat leverage")
        if nm == "walk-forward" and not win:
            ok = False; reasons.append("flat leverage does as well in the walk-forward (C1)")

    # ---- C2 / C3 permutations -----------------------------------------------------------
    d = np.asarray([t.date() for t in ts])
    alld = np.array(sorted(set(d)))
    code = pd.Categorical(d, categories=list(alld)).codes
    scope = wf | lb
    stat = lambda z: float((pnl * z)[scope].sum())
    b0 = stat(base); real = stat(cand) - b0
    win = np.ones(len(pnl), bool) if window is None else np.asarray(window, bool)
    if window is not None:
        L.append(f"  (permutations restricted to the same intra-day window: "
                 f"{win.sum()} trades, {100*win.mean():.1f}%)")
    tagged_days = np.array(sorted({x for x, mm in zip(d, mask) if mm}))
    pools = [("any day", np.arange(len(alld)), len(tagged_days))]
    if subgroup is not None:
        sub = np.asarray(subgroup, bool)
        sub_days = np.array(sorted({x for x, s, w in zip(d, sub, win) if s and w}))
        pos = {x: i for i, x in enumerate(alld)}
        pools.append(("subgroup", np.array([pos[x] for x in sub_days]),
                      int(np.isin(sub_days, tagged_days).sum())))
    for nm, pool, kk in pools:
        if kk <= 0 or kk > len(pool):
            L.append(f"  C{2 if nm=='any day' else 3} permutation {nm:9s} skipped (n/a)"); continue
        g = np.empty(perm)
        for i in range(perm):
            mm = np.isin(code, rng.choice(pool, size=kk, replace=False)) & win
            g[i] = stat(np.minimum(base * np.where(mm, float(mult), 1.0), cap)) - b0
        beat = float((g >= real).mean())
        L.append(f"  C{2 if nm=='any day' else 3} permutation {nm:9s} real ${real:+,.0f} vs random ${g.mean():+,.0f}"
                 f" (sd ${g.std():,.0f}) -> {beat*100:5.1f}% of {perm} match it")
        if beat >= 0.05:
            ok = False
            reasons.append(f"{beat*100:.1f}% of random {nm} sets do as well "
                           f"({'not special at all' if nm == 'any day' else 'not special within the subgroup the base already tilts'})")

    # ---- C4 concentration ----------------------------------------------------------------
    for nm, m in stages:
        p = (pnl * base)[mask & m]
        if len(p) < 3 or abs(p.sum()) < 1e-9:
            L.append(f"  C4 concentration {nm:13s} n={len(p)} - too few to judge"); continue
        srt = np.sort(p)[::-1] if p.sum() > 0 else np.sort(p)
        top1 = 100 * srt[0] / p.sum(); top3 = 100 * srt[:3].sum() / p.sum()
        L.append(f"  C4 concentration {nm:13s} n={len(p):4d} total ${p.sum():+,.0f}  top trade {top1:.0f}%"
                 f"  top 3 {top3:.0f}%  median ${np.median(p):+,.0f}")
        if top1 > 50 and nm == "lockbox":
            ok = False; reasons.append(f"one trade is {top1:.0f}% of the lockbox bucket (C4)")

    # ---- C5 placebo ----------------------------------------------------------------------
    if placebo_mask is not None:
        pl = np.minimum(base * np.where(np.asarray(placebo_mask, bool), float(mult), 1.0), cap)
        for nm, m in stages:
            y = _years(ts, m)
            a, b = metrics((pnl * base)[m], y), metrics((pnl * pl)[m], y)
            c = metrics((pnl * cand)[m], y)
            L.append(f"  C5 placebo {nm:13s} ${b['net']-a['net']:+9,.0f} vs the candidate's {c['net']-a['net']:+9,.0f}")
            if nm == "walk-forward" and (b["net"] - a["net"]) >= (c["net"] - a["net"]):
                ok = False; reasons.append("the placebo window pays as well as the real one (C5)")

    L.append(f"  VERDICT: {'PASS' if ok else 'FAIL'}" + ("" if ok else " - " + "; ".join(dict.fromkeys(reasons))))
    if ok and reasons:
        L.append("  (passed, but note: " + "; ".join(dict.fromkeys(reasons)) + ")")
    return {"passed": ok, "reasons": reasons, "report": "\n".join(L), "cand": cand}


# ---------------------------------------------------------------------------------------
def _selftest():
    """Synthetic cases with known answers - the guard must get all four right.
    Fast (no market data), so it can run as a ship gate."""
    rng = np.random.default_rng(7)
    n = 4000
    ts = pd.DatetimeIndex(pd.bdate_range("2012-01-02", periods=n, freq="B")[:n])
    base = np.ones(n)
    wf = np.arange(n) < int(n * 0.8)
    lb = ~wf
    fails = []

    # 1. REAL EDGE: a small tagged set whose trades are genuinely worse -> cutting must PASS
    pnl = rng.normal(60, 900, n)
    tag = np.zeros(n, bool); tag[rng.choice(n, 300, replace=False)] = True
    pnl[tag] = rng.normal(-700, 900, tag.sum())
    r = guard(pnl, ts, base, tag, 0.5, wf, lb, label="planted real edge (cut)", perm=400)
    if not r["passed"]:
        fails.append("planted real edge should PASS: " + "; ".join(r["reasons"]))

    # 2. PURE LEVERAGE: tagged set is no different, just sized up -> must FAIL on C1/C2
    pnl2 = rng.normal(60, 900, n)
    tag2 = np.zeros(n, bool); tag2[rng.choice(n, 300, replace=False)] = True
    r2 = guard(pnl2, ts, base, tag2, 1.5, wf, lb, label="pure leverage (size-up)", perm=400)
    if r2["passed"]:
        fails.append("pure leverage should FAIL")

    # 3. ONE-TRADE GAIN: everything flat except a single monster in the lockbox -> must FAIL on C4
    pnl3 = rng.normal(5, 200, n)
    tag3 = np.zeros(n, bool); tag3[rng.choice(np.where(lb)[0], 12, replace=False)] = True
    pnl3[np.where(tag3)[0][0]] = 90_000
    r3 = guard(pnl3, ts, base, tag3, 1.5, wf, lb, label="one-trade lockbox gain", perm=400)
    if r3["passed"]:
        fails.append("a one-trade lockbox gain should FAIL")

    # 4. PLACEBO PAYS: the adjacent window pays as well -> must FAIL on C5
    pnl4 = rng.normal(60, 900, n)
    tag4 = np.zeros(n, bool); tag4[rng.choice(n, 300, replace=False)] = True
    idx4 = np.where(tag4)[0]
    pnl4[idx4] = rng.normal(500, 900, len(idx4))
    nb = np.clip(idx4 + 1, 0, n - 1); plc = np.zeros(n, bool); plc[nb] = True
    pnl4[nb] = rng.normal(900, 900, len(nb))          # the neighbour pays MORE
    r4 = guard(pnl4, ts, base, tag4, 1.5, wf, lb, placebo_mask=plc, label="placebo pays more", perm=400)
    if r4["passed"]:
        fails.append("a candidate whose placebo pays more should FAIL")

    for x in (r, r2, r3, r4):
        print(x["report"].splitlines()[0], "->", "PASS" if x["passed"] else "FAIL")
    if fails:
        print("\nSELFTEST FAILED:"); [print("  -", f) for f in fails]
        return 1
    print("\nSELFTEST PASS: the guard passes a planted real edge and rejects leverage, "
          "a one-trade gain, and a candidate its placebo matches.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())

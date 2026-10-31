r"""TEST 240 parts (b) + (c) - NOISE #382 half. Prereg (locked before this ran): docs/PREREG_noise_t240_timedecay_2026-10-31.md.

(b) REGIME-GATED TRAIL: test 239's E1 (3 x ATR14 trail from the best close) and E5 (breakeven at 1R, then 2 x ATR14 trail)
    armed only once a trend-day gate is true at a bar's close (the stop set there acts from the next bar; once armed it stays
    armed for the trade):
      G1 range expansion  session range so far >= 1.0 x the prior 20 sessions' mean day range
      G2 VWAP slope       session VWAP now minus 12 bars ago, in the trade's direction, >= 0.10 x that mean range
      G3 breadth (ES)     ES 5m RTH is on the trade's side of its own session open (proxy: the only breadth series on file)
(c) VOL-SCALED PARTIAL: close F at T = m x the prior 20 sessions' mean day range (known at entry), the rest held to the
    leg's exit; fills on bars e+1..x-1 at the target level; one extra exit commission on the scaled part (test 75's rule).

Verdict line: #382's crown run once 2010-06-07..2025-07-15 (lockbox never loaded), IS to 2021-12-31, OOS 2022-01-01..
2025-07-15 (test 239's split and tools). Second line: test 74's WF-chain rebuild.

    python tools/noise_t240_regime_exits.py   -> C:\EdgeLog\_anatomy_cache\t240\{full,chain}_bc.csv
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as t74  # noqa: E402
import noise_t75b_exits as t75b  # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t240"
GATES = {"G1": "range expansion", "G2": "VWAP slope", "G3": "ES confirms"}
TRAILS = {"E1": "ATR trail 3x14", "E5": "BE 1R + 2 ATR trail"}
PARTIALS = [(m, f, fl) for m in (0.25, 0.50, 0.75) for f, fl in ((1 / 3, "1/3"), (1 / 2, "1/2"))]
KEYS = t75b.KEYS


def features(A, idx):
    """Per-bar causal features: range so far / prior mean range, VWAP 12-bar slope / prior mean range, prior mean range,
    ES side vs its session open (+1 above, -1 below, 0 unknown)."""
    H, L, C, V = (np.asarray(A[k], float) for k in ("high", "low", "close", "volume"))
    day = idx.normalize()
    df = pd.DataFrame(dict(h=H, l=L, c=C, v=V, day=day))
    g = df.groupby("day", sort=False)
    hi, lo = g.h.cummax(), g.l.cummin()
    rng_day = g.h.transform("max") - g.l.transform("min")
    per_day = pd.Series(rng_day.values, index=day).groupby(level=0).first()
    mr = per_day.rolling(20).mean().shift(1)
    mr_bar = mr.reindex(day).to_numpy()
    tp = (df.h + df.l + df.c) / 3
    pv, vv = (tp * df.v).groupby(df.day, sort=False).cumsum(), df.v.groupby(df.day, sort=False).cumsum()
    vw = np.where(vv > 0, pv / vv.replace(0, np.nan), tp).astype(float)
    pos = g.cumcount().to_numpy()
    lag = np.arange(len(vw)) - np.minimum(pos, 12)
    slope = vw - vw[lag]
    m = find_master("ES", "5m", "rth", "db_noadj_rth")
    E = load_master_arrays(m, date_from=str(idx[0].date()), date_to=str(idx[-1].date()))
    eidx = pd.DatetimeIndex(E["index"])
    eidx = eidx.tz_convert("America/New_York").tz_localize(None) if eidx.tz is not None else eidx
    es = pd.DataFrame(dict(c=np.asarray(E["close"], float), o=np.asarray(E["open"], float)), index=eidx)
    es_open = es.o.groupby(eidx.normalize()).transform("first")
    es_side = np.sign(es.c - es_open).reindex(idx).fillna(0.0).to_numpy()
    return dict(rx=((hi - lo).to_numpy() / mr_bar), vs=slope / mr_bar, mr=mr_bar, es=es_side)


def gate_ok(F, gate, j, sd):
    if gate == "G1":
        return F["rx"][j] >= 1.0
    if gate == "G2":
        return sd * F["vs"][j] >= 0.10
    return F["es"][j] == sd


def sim_gated(tr, A, F, trail, gate):
    O, H, L, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    a14 = t75b.atr(H, L, C, 14)
    out = []
    for f, e, x, sd, ep, raw, s, risk in tr:
        at_open = abs((ep + sd * raw) - O[x]) < 1e-9
        last = x - 1 if at_open else x
        stop, best_c, mfe, be, armed, res = None, ep, 0.0, False, False, raw
        for j in range(e, last + 1):
            if j > e and stop is not None:
                hit = None
                if sd * (O[j] - stop) <= 0:
                    hit = sd * (O[j] - ep)
                elif sd * ((L[j] if sd > 0 else H[j]) - stop) <= 0:
                    hit = sd * (stop - ep)
                if hit is not None:
                    res = min(hit, raw) if j == x else hit
                    break
            if j >= x:
                break
            mfe = max(mfe, sd * ((H[j] if sd > 0 else L[j]) - ep))
            best_c = max(best_c, C[j]) if sd > 0 else min(best_c, C[j])
            armed = armed or bool(gate_ok(F, gate, j, sd))
            if not armed:
                continue
            if trail == "E1":
                stop = best_c - sd * 3 * a14[j]
            else:
                if risk > 0 and mfe >= risk:
                    be = True
                if be:
                    t2 = best_c - sd * 2 * a14[j]
                    stop = max(ep, t2) if sd > 0 else min(ep, t2)
        out.append(res)
    return np.asarray(out)


def sim_partial(tr, A, F, mult, frac, cost):
    O, H, L = (np.asarray(A[k], float) for k in ("open", "high", "low"))
    out = []
    for f, e, x, sd, ep, raw, s, risk in tr:
        T = mult * F["mr"][e]
        res = raw
        if np.isfinite(T) and T > 0:
            for j in range(e + 1, x):
                if ((H[j] - ep) if sd > 0 else (ep - L[j])) >= T:
                    res = frac * T + (1 - frac) * raw - frac * cost / 2.0
                    break
        out.append(res)
    return np.asarray(out)


def grid(tr, A, idx, meta, stretches, label):
    F = features(A, idx)
    p = t74.paths(tr, A)
    mfe, risk = p.mfe.to_numpy(), p.risk.to_numpy()
    raw0 = np.asarray([t[5] for t in tr])
    cells = [("%s+%s" % (g, t), "%s %s gated on %s" % (t, TRAILS[t], GATES[g]), lambda g=g, t=t: sim_gated(tr, A, F, t, g))
             for g in GATES for t in TRAILS]
    cells += [("P%.2f/%s" % (m, fl), "partial %s at %.2f x mean day range" % (fl, m),
               lambda m=m, f=f: sim_partial(tr, A, F, m, f, meta["cost"])) for m, f, fl in PARTIALS]
    rows, base = [], {}
    for sname, d0, d1 in stretches:
        fo, yrs, cap, give, m = t75b.stretch(tr, raw0, idx, meta, d0, d1, mfe, risk)
        base[sname] = (fo, yrs)
        rows.append(dict(line=label, stretch=sname, cell="HOLD", what="#382 as is", **{k: fo[k] for k in KEYS},
                         years_won="-", mfe_captured=cap, giveback_med_R=give, changed=0, trades=int(m.sum())))
    for cid, what, fn in cells:
        r = fn()
        for sname, d0, d1 in stretches:
            fo, yrs, cap, give, m = t75b.stretch(tr, r, idx, meta, d0, d1, mfe, risk)
            by = base[sname][1]
            won = int((yrs > by.reindex(yrs.index) + 1e-9).sum())
            rows.append(dict(line=label, stretch=sname, cell=cid, what=what, **{k: fo[k] for k in KEYS},
                             years_won="%d/%d" % (won, len(yrs)), mfe_captured=cap, giveback_med_R=give,
                             changed=int((np.abs(r - raw0)[m] > 1e-9).sum()), trades=int(m.sum())))
        print("  %s %s done" % (label, cid), flush=True)
    return pd.DataFrame(rows)


def verdict(g):
    """The prereg's 239 rule on the full line: OOS ROC and Sortino beat hold, >= 3 of 4 OOS years, not one episode
    (worst DD <= 1.3 x DD5 or hold's flag), IS ROC beats hold."""
    out = []
    oos, ins = g[g.stretch.str.startswith("OOS")].set_index("cell"), g[g.stretch.str.startswith("IS")].set_index("cell")
    h, hi = oos.loc["HOLD"], ins.loc["HOLD"]
    for c in oos.index.drop("HOLD"):
        o, i = oos.loc[c], ins.loc[c]
        won = int(str(o.years_won).split("/")[0])
        ok = dict(roc=o.roc30 > h.roc30, sortino=o.sortino > h.sortino, years=won >= 3,
                  episode=(not o.one_episode) or bool(h.one_episode), is_roc=i.roc30 > hi.roc30)
        out.append(dict(cell=c, lift=all(ok.values()), **ok))
    return pd.DataFrame(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 260)
    tr, A, idx, meta = t75b.full_trades()
    g = grid(tr, A, idx, meta, [("IS 2010-21", idx[0].normalize(), t75b.IS_END),
                                 ("OOS 2022-25.07", pd.Timestamp("2022-01-01"), idx[-1].normalize())], "full")
    g.to_csv(os.path.join(OUT, "full_bc.csv"), index=False)
    print(g.drop(columns=["what"]).round(3).to_string(index=False), flush=True)
    v = verdict(g)
    v.to_csv(os.path.join(OUT, "verdict_bc.csv"), index=False)
    print(v.to_string(index=False))
    print("LIFTS: %d of %d" % (int(v.lift.sum()), len(v)), flush=True)
    ctr, cA, cidx, cmeta = t74.chain()
    wf = cmeta["wf"]
    c = grid(ctr, cA, cidx, dict(cost=cmeta["cost"], mult=cmeta["mult"]),
             [("WF chain", pd.Timestamp(wf["from"]), pd.Timestamp(wf["to"]))], "chain")
    c.to_csv(os.path.join(OUT, "chain_bc.csv"), index=False)
    print(c.drop(columns=["what"]).round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""TEST 240 (owner GO 10-31, MANAGER #150) - SAME-DAY GIVEBACK READ: on days when BOTH NOISE #382 and ORB #314 give back,
what did the tape do? Descriptive, not a test: every trait is printed beside its base rate on the other days both legs traded.

Giveback trade (fixed before computing): MFE >= 1R (R = the entry's own protective-stop distance) AND the trade closed with
less than 1/3 of its MFE. A "both" day = each leg has at least one giveback trade that day.

Sources, read-only:
  backtest  the two WF chains as tests 74 rebuilt them (NOISE tools/noise_t74_giveback.chain, ORB tools/orb_t74_giveback.chain),
            NQ 5m RTH db_noadj_rth, overlap 2016-10 .. 2025-07-15; the lockbox is never loaded.
  webull    the box trades.csv (NOISE + ORB legs, QQQ) with QQQ 1m bars - a handful of days, listed, not rated. The box
            file has no stop distance, so a live giveback = MFE >= 1.0 QQQ pt and closed < 1/3 of it.

Day traits on the NQ 5m session (all of the day itself, i.e. AFTER the fact - this explains the giveback days, it is not a
filter anyone could trade):
  late_rev60 / late_rev90  the last 60 / 90 minutes move against the open-to-then direction by >= 25% of the day's range
  range_x                  day range >= 1.3 x the mean range of the prior 20 sessions
  vwap_flat                |close - session VWAP| <= 15% of the day range (the day ended back at its average price)
  gap                      |open - prior close| >= 0.5 x the prior 20-session mean range
  vol_hi                   prior 20-session realised vol in the top third of the sample
  fomc / cpi               scheduled FOMC decision day / CPI release day (tools/event_size_scan.py calendars)
  dow                      weekday

    python tools/t240_giveback_days.py     -> C:\EdgeLog\_anatomy_cache\t240\{giveback_days.csv, traits.csv}
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as nz  # noqa: E402
import orb_t74_giveback as ob  # noqa: E402
import event_size_scan as ev  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t240"
ARM_R = 1.0
KEEP = 1 / 3
LIVE_FLOOR = 1.0                 # QQQ points of MFE before a live trade can count as a giveback


def flag(tr, A, idx, leg):
    p = nz.paths(tr, A)
    p["leg"] = leg
    p["day"] = [idx[e].normalize() for e in p.e]
    p["gb"] = (p.risk > 0) & (p.mfe >= ARM_R * p.risk) & (p.raw < KEEP * p.mfe)
    return p


def day_traits(A, idx):
    O, H, L, C, V = (np.asarray(A[k], float) for k in ("open", "high", "low", "close", "volume"))
    df = pd.DataFrame(dict(o=O, h=H, l=L, c=C, v=V), index=idx)
    df["day"] = idx.normalize()
    df["tp"] = (df.h + df.l + df.c) / 3
    rows = []
    for d, g in df.groupby("day"):
        if len(g) < 60:                                   # half days and holes: no late-day read
            continue
        rng = g.h.max() - g.l.min()
        if rng <= 0:
            continue
        vw = float((g.tp * g.v).sum() / g.v.sum()) if g.v.sum() > 0 else float(g.tp.mean())
        row = dict(day=d, o=g.o.iloc[0], c=g.c.iloc[-1], rng=rng, vwap_flat=abs(g.c.iloc[-1] - vw) <= 0.15 * rng)
        for m in (60, 90):
            k = m // 5
            mid = g.c.iloc[-k - 1]
            early, late = mid - g.o.iloc[0], g.c.iloc[-1] - mid
            row["late_rev%d" % m] = bool(np.sign(early) != 0 and np.sign(late) == -np.sign(early) and abs(late) >= 0.25 * rng)
        rows.append(row)
    t = pd.DataFrame(rows).set_index("day")
    mr = t.rng.rolling(20).mean().shift(1)
    t["range_x"] = t.rng >= 1.3 * mr
    t["gap"] = (t.o - t.c.shift(1)).abs() >= 0.5 * mr
    rv = np.log(t.c).diff().rolling(20).std().shift(1)
    t["vol_hi"] = rv >= rv.quantile(2 / 3)
    fomc = {pd.Timestamp(x) for x in ev.fomc_decision_days()}
    cpi = {pd.Timestamp(x) for x in ev.CPI_RELEASES}
    t["fomc"] = [d in fomc for d in t.index]
    t["cpi"] = [d in cpi for d in t.index]
    t["dow"] = [d.day_name()[:3] for d in t.index]
    return t.dropna(subset=["rng"])


def main():
    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, "chains.pkl")
    if os.path.exists(cache):
        n, o, T0 = pd.read_pickle(cache)
    else:
        ntr, nA, nidx, _ = nz.chain()
        otr, oA, oidx, _ = ob.chain()
        n, o, T0 = flag(ntr, nA, nidx, "NOISE"), flag(otr, oA, oidx, "ORB"), day_traits(nA, nidx)
        pd.to_pickle((n, o, T0), cache)
    d0, d1 = max(n.day.min(), o.day.min()), min(n.day.max(), o.day.max())
    n, o = n[(n.day >= d0) & (n.day <= d1)], o[(o.day >= d0) & (o.day <= d1)]
    nd, od = n.groupby("day").gb.any(), o.groupby("day").gb.any()
    both_traded = nd.index.intersection(od.index)
    lab = pd.Series("neither", index=both_traded)
    lab[nd[both_traded] & od[both_traded]] = "both"
    lab[nd[both_traded] & ~od[both_traded]] = "NOISE only"
    lab[~nd[both_traded] & od[both_traded]] = "ORB only"
    T = T0.reindex(both_traded).dropna(subset=["rng"])
    T["label"] = lab.reindex(T.index)
    T.to_csv(os.path.join(OUT, "giveback_days.csv"))
    traits = ["late_rev60", "late_rev90", "range_x", "vwap_flat", "gap", "vol_hi", "fomc", "cpi"]
    T["any"] = T.label != "neither"
    groups = ["both", "NOISE only", "ORB only", "neither"]
    rows = []
    for tr_ in traits:
        r = dict(trait=tr_)
        for g in groups:
            s = T[T.label == g][tr_].astype(bool)
            r[g] = round(100 * s.mean(), 1) if len(s) else np.nan
        rest = T[T.label != "both"][tr_].astype(bool)
        r["not both"] = round(100 * rest.mean(), 1)
        r["any leg"] = round(100 * T[T["any"]][tr_].astype(bool).mean(), 1)
        rows.append(r)
    for dn in ("Mon", "Tue", "Wed", "Thu", "Fri"):
        r = dict(trait="dow " + dn)
        for g in groups:
            s = T[T.label == g].dow
            r[g] = round(100 * (s == dn).mean(), 1) if len(s) else np.nan
        r["not both"] = round(100 * (T[T.label != "both"].dow == dn).mean(), 1)
        r["any leg"] = round(100 * (T[T["any"]].dow == dn).mean(), 1)
        rows.append(r)
    R = pd.DataFrame(rows)
    cnt = T.label.value_counts()
    R.loc[len(R)] = dict(trait="days (n)", **{g: int(cnt.get(g, 0)) for g in groups}, **{"not both": int((T.label != "both").sum()), "any leg": int(T["any"].sum())})
    R.to_csv(os.path.join(OUT, "traits.csv"), index=False)
    print("overlap %s .. %s, both legs traded on %d days" % (d0.date(), d1.date(), len(T)))
    print("giveback trades: NOISE %d of %d, ORB %d of %d" % (n.gb.sum(), len(n), o.gb.sum(), len(o)))
    pn, po = (T.label.isin(["both", "NOISE only"])).mean(), (T.label.isin(["both", "ORB only"])).mean()
    print("both-leg giveback days: %d observed vs %.1f expected if the legs gave back independently (%.1f%% x %.1f%% x %d)"
          % ((T.label == "both").sum(), pn * po * len(T), 100 * pn, 100 * po, len(T)))
    print(R.to_string(index=False))
    # Webull: the few live days, listed
    w = pd.read_csv(nz.BOX)
    w = w[w.exit_px.notna() & w.leg.isin(["NOISE", "ORB"])].copy()
    wn, wo = nz.webull(), ob.webull()
    wn["leg"], wo["leg"] = "NOISE", "ORB"
    W = pd.concat([wn, wo])
    W["day"] = pd.to_datetime(W.entry).dt.normalize()
    W["gb_any"] = (W.mfe >= LIVE_FLOOR) & (W.final < KEEP * W.mfe)          # no stop distance in the box file: a fixed floor
    wd = W.groupby(["day", "leg"]).gb_any.any().unstack()
    live_both = wd[(wd.get("NOISE", False) == True) & (wd.get("ORB", False) == True)].index  # noqa: E712
    print("\nWebull days both legs traded: %d, both gave back (closed < 1/3 of MFE): %d -> %s"
          % (int(wd.notna().all(axis=1).sum()), len(live_both), ", ".join(str(d.date()) for d in live_both)))
    W.to_csv(os.path.join(OUT, "webull_both.csv"), index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

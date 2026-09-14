"""
ROUND 55 - expand the frontier opening-range leg inside the best book. (2026-09-14)

Where the frontier stands. Round 53 found that run #297's configuration is the best opening-range
leg on the sealed year inside the adopted four-leg book, and the house scorer then confirmed it as
run #375: return-over-drawdown 38.18 -> 41.12 on the selection stretch and 10.33 -> 11.19 on the
sealed year, for the same money, with the sealed-year drawdown 8% shallower. Separately, another
session's run #379 upgraded the squeeze slot to the combined leg - but put run #314 in the
opening-range slot, and round 53 showed #314 is WORSE than the old control there.

So nobody has run the two independent upgrades together: the combined squeeze leg AND the #297
opening-range leg. This round does, and it expands the frontier around #297 in two ways:

  1. A FINE filter surface. Round 53 tested only three filter pairs, so #297 was the best of three
     coarse samples. Here both filter thresholds move on a 7 x 7 grid with the control's geometry
     held fixed, to see whether #297 sits on a broad ridge or on a lucky coarse sample.
  2. Its geometry neighbours: stop, target and breakeven each one step either side, at #297's filters.

DISCIPLINE, stated before the run. The sealed year was already used to pick #297 in round 53, so it is
no longer a clean holdout for choosing among #297's neighbours. This sweep is read for SHAPE - is the
ridge broad and does #297 sit inside it - and NOT to crown a new maximum. A neighbour that beats #297
by a hair is not a reason to move. The only job this can queue is the combination of two upgrades
that were each chosen and confirmed independently.

Uses the house book engine (augur_engine.book.run_book) with #379's own leg definitions read from its
job document, so every figure matches the runner by construction; only the opening-range leg changes.
Run from the shared checkout (BACKTEST_SPEED.md rule 3). Writes its results after every variant.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

OUT = os.path.join(ROOT, "_r55_frontier_orb_leg.csv")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def load_379_legs():
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter as FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    jobs = list(u.collection("backtests").where(filter=FF("run_id", "==", 379)).stream())
    assert jobs, "run #379's job document was not found"
    d = jobs[0].to_dict()
    return d["legs"], d["date_from"], d["date_to"], int(d.get("lockbox_months", 12))


def score(res):
    bk = res.get("book") or {}          # run_book nests the stage figures under "book"
    pre = bk.get("pre_lockbox") or {}
    lb = bk.get("lockbox") or {}
    res = dict(res, slices_held=bk.get("slices_held"))
    def nd(x):
        dd = float(x.get("max_drawdown") or 0)
        return (float(x.get("total_pnl") or 0) / dd) if dd > 0 else float("nan")
    return dict(pre_net=float(pre.get("total_pnl") or 0), pre_dd=float(pre.get("max_drawdown") or 0),
                pre_pf=float(pre.get("profit_factor") or 0), pre_nd=nd(pre),
                lb_net=float(lb.get("total_pnl") or 0), lb_dd=float(lb.get("max_drawdown") or 0),
                lb_pf=float(lb.get("profit_factor") or 0), lb_nd=nd(lb),
                slices=res.get("slices_held"))


def main():
    import pandas as pd
    from augur_engine.book import run_book
    from research_beacon import beacon

    legs379, dfrom, dto, lbm = load_379_legs()
    orb_i = [i for i, l in enumerate(legs379) if str(l["strategy"]).startswith("ORB")]
    assert len(orb_i) == 1, "expected exactly one opening-range leg in #379"
    orb_i = orb_i[0]
    base_orb = dict(legs379[orb_i])
    control_geom = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
                        trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25,
                        stop_frac=2.0, target_R=5.5, be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)

    def orb_leg(params, strategy="ORB_3_6.py"):
        leg = dict(base_orb)
        leg["strategy"] = strategy
        leg["params"] = params
        return leg

    variants = [("#379 as run (ORB #314)", dict(base_orb), True)]
    variants.append(("#234 control", orb_leg(dict(control_geom)), False))
    variants.append(("#297 frontier", orb_leg(dict(control_geom, atr_filter=0.75, vpace_filter=0.8)), False))
    for a in (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        for v in (0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 1.00):
            if (a, v) in ((0.70, 0.70), (0.75, 0.80)):
                continue
            variants.append(("filters %.2f/%.2f" % (a, v),
                             orb_leg(dict(control_geom, atr_filter=a, vpace_filter=v)), False))
    for s in (1.75, 2.0, 2.25):
        for t in (5.0, 5.5, 6.0):
            for b in (0.8, 1.0, 1.2):
                if (s, t, b) == (2.0, 5.5, 1.0):
                    continue
                variants.append(("geom s%.2f t%.1f be%.1f" % (s, t, b),
                                 orb_leg(dict(control_geom, atr_filter=0.75, vpace_filter=0.8,
                                              stop_frac=s, target_R=t, be_after_R=b)), False))

    rows = []
    t0 = time.time()
    with beacon("round 55 frontier ORB leg in the combined-squeeze book", total=len(variants)) as bc:
        for i, (label, leg, verbatim) in enumerate(variants, 1):
            legs = [dict(l) for l in legs379]
            legs[orb_i] = leg
            res = run_book(legs, date_from=dfrom, date_to=dto, lockbox_months=lbm, slices=8)
            r = dict(variant=label, **score(res))
            rows.append(r)
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print("[%4.0fs] %3d/%d %-26s sel %6.2f | sealed %6.2f  (net %9.0f dd %7.0f pf %.3f) slices %s"
                  % (time.time() - t0, i, len(variants), label, r["pre_nd"], r["lb_nd"],
                     r["lb_net"], r["lb_dd"], r["lb_pf"], r["slices"]), flush=True)
            bc.step(i)
            if i == 1:
                ok = abs(r["pre_net"] - 1479041.64) < 5 and abs(r["lb_net"] - 294141.87) < 5
                print("PARITY vs run #379 (pre $1,479,041.64 / sealed $294,141.87): %s"
                      % ("EXACT" if ok else "MISMATCH - stop and investigate"), flush=True)
                if not ok:
                    sys.exit(2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

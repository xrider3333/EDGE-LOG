"""
ROUND 55b - bound the tighter-stop trend before anybody believes it. (2026-09-14)

Round 55's geometry block found its best sealed-year cells at stop 1.75 with breakeven 0.8 - the
LOWEST stop and the LOWEST breakeven on that grid, and better on the selection stretch too. A best
cell sitting on the edge of its grid says nothing about where the peak is; the trend may keep
climbing past the edge, which is what fitting to one year looks like, or it may turn over, which is
what a real plateau looks like. This extends the grid past the edge on both knobs, holding target
5.5 and #297's filters fixed, in the same combined-squeeze book at exact parity with run #379.

Read for SHAPE only. The sealed year was used to pick #297 in round 53, so a new sealed-year maximum
here is selection, not evidence, and nothing from this file is queued.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
OUT = os.path.join(ROOT, "_r55b_bound_stop.csv")


def main():
    import importlib.util as ilu
    import pandas as pd
    from augur_engine.book import run_book
    from research_beacon import beacon

    sp = ilu.spec_from_file_location("r55", os.path.join(ROOT, "tools", "r55_frontier_orb_leg.py"))
    r55 = ilu.module_from_spec(sp)
    sp.loader.exec_module(r55)           # safe: r55 only runs its sweep under __main__

    legs379, dfrom, dto, lbm = r55.load_379_legs()
    oi = [i for i, l in enumerate(legs379) if str(l["strategy"]).startswith("ORB")][0]
    geom = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
                trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25,
                stop_frac=2.0, target_R=5.5, be_after_R=1.0, atr_filter=0.75, vpace_filter=0.8)
    cells = [(s, b) for s in (1.0, 1.25, 1.5, 1.75, 2.0, 2.25) for b in (0.4, 0.6, 0.8, 1.0)]
    rows = []
    t0 = time.time()
    with beacon("round 55b bound the tighter-stop trend", total=len(cells)) as bc:
        for i, (s, b) in enumerate(cells, 1):
            legs = [dict(l) for l in legs379]
            legs[oi] = dict(legs379[oi], strategy="ORB_3_6.py",
                            params=dict(geom, stop_frac=s, be_after_R=b))
            r = r55.score(run_book(legs, date_from=dfrom, date_to=dto, lockbox_months=lbm, slices=8))
            r.update(stop=s, be=b)
            rows.append(r)
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print("[%4.0fs] stop %.2f be %.1f  sel %6.2f | sealed %6.2f  (sealed net %8.0f dd %6.0f) slices %s"
                  % (time.time() - t0, s, b, r["pre_nd"], r["lb_nd"], r["lb_net"], r["lb_dd"], r["slices"]),
                  flush=True)
            bc.step(i)
    df = pd.DataFrame(rows)
    for col, title in (("lb_nd", "SEALED YEAR"), ("pre_nd", "SELECTION STRETCH")):
        print("\n%s return-over-drawdown (rows = stop x range, columns = breakeven at R)" % title)
        print(df.pivot_table(index="stop", columns="be", values=col).round(2).to_string())
    print("wrote", OUT)


if __name__ == "__main__":
    main()

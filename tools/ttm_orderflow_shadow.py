"""TTM 20b FORWARD SHADOW - order flow + candle on the fires the hourly gate blocks (no orders anywhere).

Pre-registered in tools/TTM_R20_PREREG.txt addendum 1 (a85a666f). Starts 2026-10-01. The NinjaTrader
10-second capture (C:\\EdgeLog\\ohlc\\ES_10s.csv / NQ_10s.csv, append-only, also imported into the library
as the nt_noadj_eth 10s masters) IS the shadow's log: every fire is recomputed from the refreshed masters
with round 20a's exact code, so this can be run at any time and gives the same answer.

  python tools/ttm_orderflow_shadow.py            -> progress + current read
Runs on demand (no nightly job needed: everything is recomputed from the data). Until 150 blocked fires with
coverage exist it prints COUNTS ONLY. At 150 it reads EXACTLY the first 150 by fire time (gated fires over the
same dates), saves the verdict to first_verdict.json and never recomputes it (MANAGER review 2026-09-30).
PASS needs all of:
  (1) blocked fires where BOTH order flow and the candle agree: mean R >= the gated fires' mean R (same dates);
  (2) their net stays positive without their 3 biggest trades;
  (3) one-sided permutation p <= 0.10, both-agree vs the rest of the blocked fires.
A pass goes to Frontier for a book test; it is not an adoption.
Writes the fire rows to C:\\EdgeLog\\ttm_shadow\\orderflow_fires.csv.
"""
import os
import sys
import json
import importlib.util

import numpy as np
import pandas as pd

os.environ["TTM_R20_FROM"] = "2026-10-01"
# Only COMPLETED sessions: today counts once it has closed (16:15 ET), else the shadow stops at the prior
# weekday - a mid-session master refresh must never turn a live trade into a force-closed one.
_et = pd.Timestamp.now(tz="America/New_York")
_last = _et.normalize() if (_et.weekday() < 5 and (_et.hour, _et.minute) >= (16, 15)) else     (_et.normalize() - pd.offsets.BDay(1))
os.environ["TTM_R20_TO"] = _last.strftime("%Y-%m-%d")
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("r20a", os.path.join(HERE, "ttmsqz_r20a_orderflow.py"))
R = importlib.util.module_from_spec(sp)
sp.loader.exec_module(R)

NEED = 150
OUT_DIR = r"C:\EdgeLog\ttm_shadow"


def main():
    tens = {r: R.load_10s(r) for r in ("ES", "NQ")}
    rows = []
    for inst, tf in R.CELLS:
        for g in ("sq_on", "none"):
            rows += R.cell_fires(inst, tf, g, tens[inst])
    df = pd.DataFrame(rows)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(OUT_DIR, "orderflow_fires.csv"), index=False)
    if df.empty:
        print("TTM order-flow shadow: no fires since %s yet" % R.CAP_FROM.date())
        return
    df["fire_ts"] = pd.to_datetime(df["fire_bar"], utc=True)
    G = df[(df.gate == "sq_on") & df.ok]
    U = df[(df.gate == "none") & df.ok]
    gk = set(zip(G.inst, G.tf, G.entry_bar))
    B = U[[k not in gk for k in zip(U.inst, U.tf, U.entry_bar)]].sort_values("fire_ts", kind="stable")
    print("TTM order-flow shadow since %s (through %s): %d of %d blocked fires with coverage, %d gated" % (
        R.CAP_FROM.date(), df.exit_date.max().date(), len(B), NEED, len(G)))
    vpath = os.path.join(OUT_DIR, "first_verdict.json")
    if os.path.exists(vpath):          # read ONCE (pre-registered read point) - never recomputed
        with open(vpath, encoding="utf-8") as fh:
            v = json.load(fh)
        print("  FIRST VERDICT (read %s on the first %d blocked fires, through %s): %s" % (
            v["read_at"], v["n_blocked"], v["cutoff"], v["verdict"]))
        return
    if len(B) < NEED:                  # counts only until the read point (no interim statistics)
        print("  counts only until %d blocked fires (by pre-registration) - no statistics shown" % NEED)
        return
    B = B.iloc[:NEED]                  # EXACTLY the first 150 by fire time
    cutoff = B["fire_ts"].iloc[-1]
    Gc = G[G["fire_ts"] <= cutoff]     # the gated fires over the same dates
    both = B[B.agree & B.candle]
    rest = B[~(B.agree & B.candle)]
    p = R.perm_p(both.R.values, rest.R.values)
    ex3 = both.usd.sum() - both.usd.nlargest(3).sum()
    ok = [len(both) > 0 and both.R.mean() >= (Gc.R.mean() if len(Gc) else -np.inf), ex3 > 0, p <= 0.10]
    verdict = "PASS -> book test" if all(ok) else "FAIL"
    v = dict(read_at=pd.Timestamp.now(tz="America/New_York").isoformat(timespec="seconds"), n_blocked=int(len(B)),
             cutoff=str(cutoff), verdict=verdict,
             both_n=int(len(both)), both_mean_R=float(both.R.mean()) if len(both) else None,
             both_net=float(both.usd.sum()), both_net_ex_top3=float(ex3),
             rest_n=int(len(rest)), rest_mean_R=float(rest.R.mean()) if len(rest) else None,
             gated_n=int(len(Gc)), gated_mean_R=float(Gc.R.mean()) if len(Gc) else None, p=float(p),
             clauses=dict(mean_R_vs_gated=bool(ok[0]), ex_top3_positive=bool(ok[1]), p_le_010=bool(ok[2])))
    with open(vpath, "w", encoding="utf-8") as fh:
        json.dump(v, fh, indent=1)
    print("  both agree %d  mean R %+.3f  net $%s  (ex top 3 $%s) | rest %d  mean R %+.3f | gated %d  mean R %+.3f | p %.3f" % (
        len(both), v["both_mean_R"] if v["both_mean_R"] is not None else np.nan, "{:,.0f}".format(both.usd.sum()),
        "{:,.0f}".format(ex3), len(rest), v["rest_mean_R"] if v["rest_mean_R"] is not None else np.nan,
        len(Gc), v["gated_mean_R"] if v["gated_mean_R"] is not None else np.nan, p))
    print("  FIRST VERDICT: %s (mean R vs gated %s, ex-top-3 positive %s, p<=0.10 %s) - saved to %s, read once" % (
        verdict, *["yes" if x else "NO" for x in ok], vpath))


if __name__ == "__main__":
    main()

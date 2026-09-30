"""TTM 20b FORWARD SHADOW - order flow + candle on the fires the hourly gate blocks (no orders anywhere).

Pre-registered in tools/TTM_R20_PREREG.txt addendum 1 (a85a666f). Starts 2026-10-01. The NinjaTrader
10-second capture (C:\\EdgeLog\\ohlc\\ES_10s.csv / NQ_10s.csv, append-only, also imported into the library
as the nt_noadj_eth 10s masters) IS the shadow's log: every fire is recomputed from the refreshed masters
with round 20a's exact code, so this can be run at any time and gives the same answer.

  python tools/ttm_orderflow_shadow.py            -> progress + current read
First verdict at 150 forward fires the gate blocks, with coverage. PASS needs all of:
  (1) blocked fires where BOTH order flow and the candle agree: mean R >= the gated fires' mean R (same dates);
  (2) their net stays positive without their 3 biggest trades;
  (3) one-sided permutation p <= 0.10, both-agree vs the rest of the blocked fires.
A pass goes to Frontier for a book test; it is not an adoption.
Writes the fire rows to C:\\EdgeLog\\ttm_shadow\\orderflow_fires.csv.
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

os.environ["TTM_R20_FROM"] = "2026-10-01"
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
    G = df[(df.gate == "sq_on") & df.ok]
    U = df[(df.gate == "none") & df.ok]
    gk = set(zip(G.inst, G.tf, G.entry_bar))
    B = U[[k not in gk for k in zip(U.inst, U.tf, U.entry_bar)]]
    both = B[B.agree & B.candle]
    rest = B[~(B.agree & B.candle)]
    p = R.perm_p(both.R.values, rest.R.values)
    ex3 = both.usd.sum() - both.usd.nlargest(3).sum()
    print("TTM order-flow shadow since %s (through %s): %d of %d blocked fires with coverage" % (
        R.CAP_FROM.date(), df.exit_date.max().date(), len(B), NEED))
    print("  both agree %d  mean R %+.3f  net $%s  (ex top 3 $%s) | rest %d  mean R %+.3f | gated %d  mean R %+.3f | p %.3f" % (
        len(both), both.R.mean() if len(both) else np.nan, "{:,.0f}".format(both.usd.sum()), "{:,.0f}".format(ex3),
        len(rest), rest.R.mean() if len(rest) else np.nan, len(G), G.R.mean() if len(G) else np.nan, p))
    if len(B) >= NEED:
        ok = [len(both) > 0 and both.R.mean() >= (G.R.mean() if len(G) else -np.inf), ex3 > 0, p <= 0.10]
        print("  FIRST VERDICT: %s (mean R vs gated %s, ex-top-3 positive %s, p<=0.10 %s)" % (
            "PASS -> book test" if all(ok) else "FAIL", *["yes" if x else "NO" for x in ok]))
    else:
        print("  no verdict yet - the bar is read at %d blocked fires" % NEED)


if __name__ == "__main__":
    main()

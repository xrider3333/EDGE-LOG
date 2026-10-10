# CLOSING-PRESSURE map check (MANAGER GO 10-10; reading shelf No. 27: Bogousslavsky & Muravyev 2023, J. Financial Markets 66).
# Paper: US stock closing-auction prices sit off the 16:00 quote midpoint by 8.1 bp on average (absolute, per stock), and the push
# reverts overnight; moves in the last five minutes of CONTINUOUS trading revert about five times less. Two questions for the house:
#  (1) does a 15:55 futures exit (NOISE / ORB) pay a closing-pressure tax?  (2) is an overnight FADE of index-level closing pressure a
#      leg (enter at 16:00 against the push, exit at the next 09:30 open)?
# NO P&L READ: from the masters only the SIZE (standard deviation, no direction) of the 16:00 -> next 09:30 move and the price level are
# measured on WF days. The edge is the paper's per-stock deviation diversified to the index, a generous upper bound.
import sys
import numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays

WF = ("2016-07-01", "2025-06-29")
MKT = {"ES": (50.0, 0.363, 70), "NQ": (20.0, 0.533, 20)}     # mult, house RT cost (points), effective number of index names (S&P ~70, NDX ~20)
DEV_BP = 8.1                                                  # paper: mean absolute auction deviation per stock (bp)
YEARS = 9.0
MP = 0.42


def overnight(mk):
    A = load_master_arrays(find_master(mk, "5m", "rth", "db_noadj_rth"), date_from=WF[0], date_to=WF[1])
    idx = pd.DatetimeIndex(A["index"]); df = pd.DataFrame({"o": A["open"], "c": A["close"]}, index=idx)
    t = df.index.strftime("%H:%M"); day = df.index.normalize()
    c = df["c"][t == "15:55"].groupby(day[t == "15:55"]).first()        # bar START stamps: closes at 16:00
    o = df["o"][t == "09:30"].groupby(day[t == "09:30"]).first()
    nxt = o.shift(-1).reindex(c.index) if False else o.reindex(o.index)
    j = c.index.intersection(o.index)
    on = np.log(o.shift(-1)[j] / c[j]).dropna()
    return float(on.std()), float(c.mean()), len(on)


def sim(edge_bp, sd, price, mult, cost, n_per_year, n=4000, seed=20261010):
    rng = np.random.default_rng(seed); k = int(YEARS * n_per_year)
    pnl = (edge_bp / 1e4 + sd * rng.standard_normal((n, k))) * price * mult - cost * mult
    eq = np.cumsum(pnl, axis=1); dd = np.max(np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq, axis=1)
    roc = 30.0 * (eq[:, -1] / YEARS) / np.where(dd > 0, dd, np.nan)
    return roc, pnl.mean() * n_per_year


print("(1) 15:55 EXIT: the paper's deviation is in the 16:00 AUCTION print of stocks; a futures exit at 15:55 trades before it, and the")
print("    last five minutes of continuous trading revert ~5x less (paper) - no closing-pressure tax on a 15:55 exit, none on 16:00 either.\n")
for mk, (mult, cost, neff) in MKT.items():
    sd, px, nd = overnight(mk)
    idx_dev = DEV_BP / np.sqrt(neff)
    print("%s: 16:00 -> next 09:30 move size (sd) %.3f%% over %d WF nights, mean price %.0f; RT cost %.3f pt = %.2f bp"
          % (mk, sd * 100, nd, px, cost, cost / px * 1e4))
    for lab, e, npy in (("every night, index deviation %.1f bp (8.1 / sqrt %d), all of it captured" % (idx_dev, neff), idx_dev, 250),
                        ("same, McLean-Pontiff x 0.42", idx_dev * MP, 250),
                        ("special days only (rebalance / expiry, 12 a year) at the FULL per-stock 8.1 bp", DEV_BP, 12)):
        roc, net = sim(e, sd, px, mult, cost, npy)
        print("   FADE %s: net $%.0f / yr / contract; ROC@30k median %.1f, P(>=15) %.3f" % (lab, net, np.nanmedian(roc), np.nanmean(roc >= 15)))

# PREMACRO map check (MANAGER #100 (1)) - Kurov, Sancetta, Strasser & Wolfe 2019 pre-release drift before the 10:00 ET releases.
# NO P&L READ: from the masters only the SIZE of the 09:30 -> 10:00 move (its standard deviation, no direction) and the price level
# are measured, on WF days 2016-07-01..2025-06-29. Everything else is the paper's numbers (ECB WP 1901 Table 3, E-mini S&P, 2008-2014)
# pushed through a simulation of the one trade an UNINFORMED trader can make: watch the first part of the pre-release window, then
# follow its sign into the release (exit just before 10:00). Also printed: the "oracle" bound - knowing the surprise sign (the leak).
import sys
import numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays

WF = ("2016-07-01", "2025-06-29")
MKT = {"ES": (50.0, 0.363), "NQ": (20.0, 0.533)}          # house mult, round-trip cost in points (tools/orb_nt1_macro830.py)
STRESS = 0.25
# Table 3, E-mini, [t-30min, t-5sec]: the five 10:00 ET drift releases: (gamma % per 1-SD surprise, R2)
PAPER = {"ISM non-manufacturing": (0.139, 0.19), "Pending home sales": (0.154, 0.09), "ISM manufacturing": (0.091, 0.06),
         "Existing home sales": (0.113, 0.10), "CB consumer confidence": (0.035, 0.01)}
EVENTS_PER_YEAR = 5 * 12
YEARS = 9.0
R2 = float(np.mean([v[1] for v in PAPER.values()]))
MP = 0.42                                                   # McLean & Pontiff 2016: ~58% lower after publication


def window_stats(mk):
    A = load_master_arrays(find_master(mk, "5m", "rth", "db_noadj_rth"), date_from=WF[0], date_to=WF[1])
    idx = pd.DatetimeIndex(A["index"]); df = pd.DataFrame({"o": A["open"], "c": A["close"]}, index=idx)
    t = df.index.strftime("%H:%M"); day = df.index.normalize()
    o930 = df["o"][t == "09:30"].groupby(day[t == "09:30"]).first()
    c955 = df["c"][t == "09:55"].groupby(day[t == "09:55"]).first()       # bar START stamps: the 09:55 bar closes at 10:00
    j = o930.index.intersection(c955.index)
    r = np.log(c955[j] / o930[j])
    return float(r.std()), float(o930[j].mean()), len(j)


def sim(sd30, price, mult, cost, r2, f, oracle=False, scale=1.0, n=4000, seed=20261010):
    """per-event P&L (1 contract, $) for n paths of YEARS x EVENTS_PER_YEAR events -> ROC at $30k per path"""
    rng = np.random.default_rng(seed); k = int(YEARS * EVENTS_PER_YEAR)
    g = np.sqrt(r2) * sd30; sn = np.sqrt(max(sd30 ** 2 - g ** 2, 0.0))
    z = rng.standard_normal((n, k)); e1 = rng.standard_normal((n, k)); e2 = rng.standard_normal((n, k))
    r1 = g * f * z + np.sqrt(f) * sn * e1
    r2_ = g * (1 - f) * z + np.sqrt(1 - f) * sn * e2
    side = np.sign(z) if oracle else np.sign(r1)
    hold = (g * z + sn * (np.sqrt(f) * e1 + np.sqrt(1 - f) * e2)) if oracle else r2_   # the oracle holds the whole 30 min
    pnl = scale * side * hold * price * mult - cost * mult
    eq = np.cumsum(pnl, axis=1); dd = np.max(np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq, axis=1)
    roc = 30.0 * (eq[:, -1] / YEARS) / np.where(dd > 0, dd, np.nan)
    return roc, pnl.mean()


print("paper: five 10:00 ET drift releases, mean R2 of the 30-min pre-window on the surprise %.3f; %d events a year; WF %.0f years" % (R2, EVENTS_PER_YEAR, YEARS))
for mk, (mult, cost) in MKT.items():
    sd30, px, nd = window_stats(mk)
    print("\n%s: 09:30->10:00 move size (sd) %.3f%% over %d WF days, mean price %.0f, cost %.3f pt ($%.2f) RT" % (mk, sd30 * 100, nd, px, cost, cost * mult))
    for lab, r2, sc in (("paper-era signal, no decay", R2, 1.0), ("McLean-Pontiff on the drift (gamma x 0.42)", R2 * MP ** 2, 1.0)):
        best = None
        for f in (1 / 6, 1 / 3, 1 / 2, 2 / 3):              # watch 5 / 10 / 15 / 20 minutes, then follow - the BEST is kept (generous)
            roc, mu = sim(sd30, px, mult, cost, r2, f, scale=sc)
            if best is None or np.nanmedian(roc) > np.nanmedian(best[1]):
                best = (f, roc, mu)
        f, roc, mu = best
        print("  FOLLOW (%s): best watch %d min -> mean $%.1f / contract / event net; ROC@30k median %.1f, P(>=15) %.3f"
              % (lab, round(f * 30), mu, np.nanmedian(roc), np.nanmean(roc >= 15)))
        roc_s, mu_s = sim(sd30, px, mult, cost + STRESS, r2, f, scale=sc)
        print("      stress cost (+0.25 pt): mean $%.1f, ROC median %.1f" % (mu_s, np.nanmedian(roc_s)))
    for lab, r2 in (("ORACLE, paper-era", R2), ("ORACLE, McLean-Pontiff", R2 * MP ** 2)):
        roc, mu = sim(sd30, px, mult, cost, r2, 0.0, oracle=True)
        print("  %s (knows the surprise sign at 09:30 - the leak, NOT tradable): mean $%.1f / event; ROC median %.1f, P(>=15) %.3f"
              % (lab, mu, np.nanmedian(roc), np.nanmean(roc >= 15)))

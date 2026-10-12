# TV SCALP MAP (MANAGER #112, owner order 10-12): map-check the top public TradingView SCALPING strategies on NQ / ES against the
# house yardstick and REAL costs (commission + 1 tick slippage each side). NO P&L READ of any strategy: from the masters only bar
# RANGES (ATR, size only, no direction) on WF days 2016-07-01..2025-06-29 are measured, to turn each script's ATR-based stop into
# points. Everything else is the AUTHOR'S OWN reported win rate / profit factor (unverified, in-sample, TradingView broker emulator).
# For each: avg win / avg loss implied by (win rate, PF), cost as a share of the average win, the break-even win rate after costs,
# and ROC@$30k (iid two-outcome trades, 9 years) as claimed, then with the edge halved (Falck-Rej-Thesmar: OOS ~ half of IS) and
# quartered (+ McLean-Pontiff). Map checks have no curve: DD5 / DD% / Sortino = '-'.
import sys
import numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays

WF = ("2016-07-01", "2025-06-29")
YEARS = 9.0
# owner rule: commission + 1 tick slippage each side. NQ: $4.12 RT commission + 2 x $5 = $14.12 (0.706 pt); ES: $4.12 + 2 x $12.50 = $29.12 (0.582 pt)
COST_PT = {"NQ": 14.12 / 20.0, "ES": 29.12 / 50.0}
MULT = {"NQ": 20.0, "ES": 50.0}


def atr(mk, tf, n=14):
    A = load_master_arrays(find_master(mk, tf, "rth", "db_noadj_rth"), date_from=WF[0], date_to=WF[1])
    h, l, c = (pd.Series(A[k]) for k in ("high", "low", "close"))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().median())


def sim(W, R, L, n_yr, mk, net_edge_scale=1.0, cost_pt=None, n=3000, seed=20261012):
    """two-outcome trades: win +R*L, loss -L (points), edge scaled by net_edge_scale (decay shrinks W toward break-even), cost per RT"""
    c = COST_PT[mk] if cost_pt is None else cost_pt
    e_gross = W * R * L - (1 - W) * L
    w = W if net_edge_scale == 1.0 else ((1.0 / (R + 1)) + (W - 1.0 / (R + 1)) * net_edge_scale)   # shrink the win rate's excess over zero-edge
    rng = np.random.default_rng(seed); k = int(YEARS * n_yr)
    win = rng.random((n, k)) < w
    pnl = (np.where(win, R * L, -L) - c) * MULT[mk]
    eq = np.cumsum(pnl, axis=1); dd = np.max(np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq, axis=1)
    roc = 30.0 * (eq[:, -1] / YEARS) / np.where(dd > 0, dd, np.nan)
    return np.nanmedian(roc), float(np.nanmean(roc >= 15)), pnl.mean() * n_yr, e_gross, w


A1 = atr("NQ", "1m"); A5 = atr("NQ", "5m"); E5 = atr("ES", "5m")
A30 = A1 / np.sqrt(2); A60 = A5 * np.sqrt(12)
print("NQ ATR(14) median over WF: 1m %.2f pt, 5m %.2f pt (30s ~ %.2f, 1h ~ %.2f by sqrt-time); ES 5m %.2f pt" % (A1, A5, A30, A60, E5))
print("owner-rule cost per round trip: NQ %.3f pt ($14.12), ES %.3f pt ($29.12)\n" % (COST_PT["NQ"], COST_PT["ES"]))

# name, market, author's win rate, author's PF, avg-loss assumption (points), trades a year (assumed where not stated), costs already in the author's PF?
CANDS = [
    ("NQ/MNQ Super Scalper [BACKTEST] (Crispigino, open source; MNQ 1m, 24/5, 6 entry paths x 8-factor score, pyramiding 20; 1 year)",
     "NQ", 0.637, 1.23, 1.5 * A1, 2934, True),
    ("30-second NQ/ES '80% winrate' scalper (tight trailing ATR target, static stop 2.5 x ATR14 on 30s; 'long-term PF 1.3')",
     "NQ", 0.80, 1.30, 2.5 * A30, 1500, False),
    ("TS V1 Nasdaq Scalping System (doerki87, PROTECTED; 1-HOUR chart despite the name; trend + counter-trend)",
     "NQ", 0.7235, 1.43, 1.0 * A60, 150, False),
    ("VWAP-RSI Scalper FINAL v1 (michaelriggs, open source; RSI(3) extreme with VWAP + EMA trend, stop 1 ATR / target 2 ATR, <= 3 a day)",
     "NQ", 0.42, 1.37, 1.0 * A5, 375, False),
    ("same VWAP-RSI on ES 5m", "ES", 0.42, 1.37, 1.0 * E5, 375, False),
]
for name, mk, W, PF, L, nyr, net in CANDS:
    R = PF * (1 - W) / W
    c = COST_PT[mk]
    be = (L + c) / (R * L + L) if not net else float("nan")
    print(name)
    print("   author: win %.1f%%, PF %.2f -> avg win / avg loss %.2f; avg loss ~%.1f pt, avg win ~%.1f pt; %d trades a year%s"
          % (W * 100, PF, R, L, R * L, nyr, " (author's PF already NET of 2 ticks a side + commission)" if net else " (no costs stated: read as GROSS)"))
    if not net:
        print("   cost = %.0f%% of the average win; break-even win rate after costs %.1f%% (author %.1f%%)" % (100 * c / (R * L), 100 * be, 100 * W))
    for lab, sc in (("as claimed", 1.0), ("edge x 0.5 (OOS ~ half IS)", 0.5), ("edge x 0.25 (+ publication decay)", 0.25)):
        med, p15, yr, eg, w = sim(W, R, L, nyr, mk, sc, cost_pt=(0.0 if net else None))
        print("   %-34s win %.1f%%: net $%8.0f / yr / contract; ROC@30k median %6.1f, P(>=15) %.3f | DD5 - | DD%% - | Sortino -"
              % (lab, 100 * w, yr, med, p15))
    print()

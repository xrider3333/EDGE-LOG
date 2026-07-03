# xcheck_orb.py — cross-check blotter: ORB SIMPLE (python engine) vs TradingView.
# Runs the engine on the most recent N sessions of the NQ/ES 5m RTH master and
# prints a DIAGNOSTIC trade blotter: side, entry/exit prices, exit reason, plus
# each session's opening-range hi/lo and last-bar time. Load pine/ORB_3_0.pine
# on the matching TV chart (5m, RTH, same config) and compare trade-for-trade.
#
# The extra columns exist to pin every engine-vs-TV mismatch to its real cause:
#   • side flip / entry-bar flip  → knife-edge OR-boundary (1-tick data diff)
#   • last-bar time != 16:00      → RTH master has post-close bars (session bug)
#   • exit reason differs         → stop-vs-EOD / gap-through fill ordering
#
# Run:  python tools/xcheck_orb.py            (NQ, default config)
#       set XC_INST=ES & python tools/xcheck_orb.py
import os, sys
import importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = {"NQ": ("master_00c66966.csv", 20), "ES": ("master_a85a0438.csv", 50)}
INST = os.environ.get("XC_INST", "NQ").upper()
N_SESSIONS = int(os.environ.get("XC_SESS", "10"))
# Date-range mode (preferred): set XC_FROM/XC_TO (YYYY-MM-DD) to target a window
# that matches the chart you loaded in TV. Pick a window AWAY from a quarterly
# roll (NQ rolls mid-Mar/Jun/Sep/Dec) so AUGUR's continuous and TV's continuous
# are on the SAME underlying contract — e.g. XC_FROM=2026-05-01 XC_TO=2026-05-29
# is clean NQM2026 mid-cycle. Without these, falls back to the last N sessions.
XC_FROM = os.environ.get("XC_FROM", "").strip()
XC_TO   = os.environ.get("XC_TO", "").strip()

CFG = dict(or_bars=3, trade_mode="Both", stop_frac=0.75,
           vol_filter=0.0, breakout_buf=0.0, target_R=0.0, flat_eod=True)

fname, mult = MASTERS[INST]
# Override the master file (e.g. a NOADJ_*.csv) to cross-check older history vs TV
# with Back-adjustment OFF:  set XC_MASTER=NOADJ_NQ_5m_RTH.csv
fname = os.environ.get("XC_MASTER", fname)
spec = importlib.util.spec_from_file_location(
    "orbs", os.path.join(ROOT, "augur_strategies", "ORB_3_0.py"))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

df = pd.read_csv(os.path.join(ROOT, "augur_uploads", fname))
dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
df.index = dt
dates = pd.Series(df.index).dt.date
all_dates = sorted(dates.unique())
if XC_FROM or XC_TO:
    lo = pd.Timestamp(XC_FROM).date() if XC_FROM else all_dates[0]
    hi = pd.Timestamp(XC_TO).date()   if XC_TO   else all_dates[-1]
    keep_dates = [d for d in all_dates if lo <= d <= hi]
    win_desc = f"date range {lo} -> {hi}"
else:
    keep_dates = all_dates[-N_SESSIONS:]
    win_desc = f"last {N_SESSIONS} sessions"
if not keep_dates:
    print("NO SESSIONS in requested window."); sys.exit(0)
m = dates.isin(keep_dates).values
df = df[m]
O = df["open"].values; H = df["high"].values
L = df["low"].values;  C = df["close"].values
DAY = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

r = mod.run_backtest(O, H, L, C, volumes=df["volume"].values,
                     day_id=DAY, return_trades=True, **CFG)

print(f"ORB SIMPLE xcheck | {INST} 5m RTH | {win_desc} "
      f"({keep_dates[0]} -> {keep_dates[-1]}, {len(keep_dates)} sessions)")
print(f"config: {CFG}")
if not r or not r.get("trades"):
    print("NO TRADES in window."); sys.exit(0)
print(f"{r['num_trades']} trades | WR {r['win_rate']:.0f}% | "
      f"PF {min(r['profit_factor'],99):.2f} | gross {r['total_pnl']:,.2f} pts "
      f"(${r['total_pnl']*mult:,.0f})")
print()

# ── Per-session OR levels + last-bar time, so we can re-derive side/price/reason.
or_bars = CFG["or_bars"]
sess = {}   # first_bar_idx -> dict(or_hi, or_lo, last_idx)
i = 0
while i < len(C):
    j = i
    while j < len(C) and DAY[j] == DAY[i]:
        j += 1
    sess[i] = dict(or_hi=H[i:i+or_bars].max(), or_lo=L[i:i+or_bars].min(), last=j-1)
    i = j

def sess_start_of(b):
    s = b
    while s > 0 and DAY[s] == DAY[s-1]:
        s -= 1
    return s

# TV reports NET P&L (commission $2.83/order x 2 = $5.66 round-turn, slippage 0).
# The engine books GROSS points, so show a net-$ column = gross - $5.66 to line
# up directly with TV's "Net PnL USD". Tiny residuals after that are fractional-
# tick stop-fill differences, not a logic gap.
RT_COST = 5.66
hdr = (f"{'#':>3} {'side':>4} {'entry (ET)':<16} {'in_px':>9} "
       f"{'exit (ET)':<16} {'out_px':>9} {'why':>4} {'pts':>8} "
       f"{'gross$':>10} {'net$(TV)':>10}   {'OR hi/lo':>18} {'last bar':>6}")
print(hdr); print("-" * len(hdr))
for idx, (eb, xb, pnl) in enumerate(r["trades"], 1):
    s = sess_start_of(eb)
    or_hi = sess[s]["or_hi"]; or_lo = sess[s]["or_lo"]; last = sess[s]["last"]
    # side: engine checks long (up-break) first, then short (same tie-break)
    up = H[eb] >= or_hi
    side = "L" if up else "S"
    if side == "L":
        in_px = max(or_hi, O[eb]) if O[eb] > or_hi else or_hi
        out_px = in_px + pnl
    else:
        in_px = min(or_lo, O[eb]) if O[eb] < or_lo else or_lo
        out_px = in_px - pnl
    why = "eod" if xb == last else "stop"
    last_t = str(df.index[last])[11:16]
    et = str(df.index[eb])[:16]; xt = str(df.index[xb])[:16]
    orlbl = f"{or_hi:.2f}/{or_lo:.2f}"
    print(f"{idx:>3} {side:>4} {et:<16} {in_px:>9.2f} "
          f"{xt:<16} {out_px:>9.2f} {why:>4} {pnl:>8.2f} "
          f"{pnl*mult:>10,.2f} {pnl*mult-RT_COST:>10,.2f}   {orlbl:>18} {last_t:>6}")
print()
print("Compare against pine/ORB_3_0.pine on the SAME chart "
      f"({INST}1! or continuous, 5m, RTH session, ET timezone), vol filter = 0.")
print("Mismatch decoder:")
print("  - side or entry-bar differs -> knife-edge OR boundary (1-tick data diff)")
print("  - 'last bar' != 15:55       -> RTH master has post-close bars (session bug)")
print("  - why differs (stop/eod)    -> stop-vs-EOD / gap-through fill ordering")

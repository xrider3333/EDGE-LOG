# -*- coding: utf-8 -*-
"""NOISE ROUND 64 - FORWARD PROGRESS COUNT, OUTCOME-BLIND (addendum 5): built from r64_noise_delta_read.py up to the trade tags,
with every P&L field removed - it prints session usability, tagged-trade counts per bucket and the pace to the 150-trade read.
  python tools/r64_forward_count.py   (R64_DATE_TO = the master's last session)

ORIGINAL HEADER (the descriptive historical read):

Pre-registration docs/PREREG_noise_r64_delta_2026-09-30.md (commit 6b3f35de, before any outcome split). NOISE #304's crown
trades whose signal bar lies in a usable 10-second capture session; BACKED = the signal bar's summed delta has the
trade's sign. Too few trades to judge - this only decides the forward shadow is worth reading, and records the numbers.

  python tools/r64_noise_delta_read.py  -> tools/r37_results/r64_delta_read.txt
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402


TEN = os.environ.get("EDGELOG_NQ_10S", r"C:\EdgeLog\ohlc\NQ_10s.csv")
DATE_TO = os.environ.get("R64_DATE_TO", "2026-10-14")   # the recorded read's last session, pinned so it reproduces
M, COST = 20.0, 0.533
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)

# ---- the capture: usable sessions and 5-minute delta sums --------------------------------------------------------
d = pd.read_csv(TEN)
d["end"] = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
t = d.end.dt.time
rth = d[(t > pd.Timestamp("09:30").time()) & (t <= pd.Timestamp("16:00").time()) & (d.end.dt.dayofweek < 5)
        & (d.end.dt.date <= pd.Timestamp(DATE_TO).date())].copy()
g = rth.groupby(rth.end.dt.date)
q = pd.DataFrame({"bars": g.size(), "dnz": g.apply(lambda x: (x.delta != 0).mean())})
USABLE = set(q[(q.bars >= 2000) & (q.dnz >= 0.8)].index)
rth["T"] = (rth.end - pd.Timedelta(seconds=1)).dt.floor("5min")           # END-stamped 10s bar -> its 5m bar start
bar_delta = rth.groupby("T")["delta"].sum()
rth["day"] = rth.end.dt.date
rth["cum"] = rth.groupby("day")["delta"].cumsum()
cum_at_bar_end = rth.groupby("T")["cum"].last()
# MISSING ROWS (PAPER-NT8 #20, 2026-10-02): a row flagged rt=3, or with volume but no buy/sell split, has NO delta - it is
# missing, not zero (sleep/back-fill windows). A tag whose window holds any such row is left untagged.
# R64_MISSING_RULE=0 reproduces the reads recorded before this rule.
rth["miss"] = (rth.rt == 3) | ((rth.volume > 0) & (rth.buy_vol + rth.sell_vol == 0))
if os.environ.get("R64_MISSING_RULE", "1") == "0":
    rth["miss"] = False
bar_miss = rth.groupby("T")["miss"].any()
cum_miss = rth.assign(m=rth.groupby("day")["miss"].cummax()).groupby("T")["m"].last()

# ---- NOISE #304 crown trades on the 5-minute master ----------------------------------------------------------------
sp = ilu.spec_from_file_location("n10_r64", os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py"))
N10 = ilu.module_from_spec(sp)
sp.loader.exec_module(N10)
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2025-06-01", date_to=DATE_TO)
IDX = pd.DatetimeIndex(A["index"])

# PRICE GUARD (audit 2026-09-30 evening, outcome-blind): the capture must be the master's contract. A session counts only
# if >= 80% of its 5-minute closes rebuilt from the END-stamped 10s bars equal the master's close exactly (median 96%;
# 09-14 was 31% with a ~298-point gap = the capture already on December while the master was still on September).
# R64_PRICE_GUARD=0 reproduces the first recorded read (45 sessions, 30 trades).
close10 = rth.groupby("T")["close"].last()
_m = pd.Series(A["close"], index=IDX.tz_convert("America/New_York")).to_frame("c").join(close10.rename("c10"), how="inner")
match = (_m.c == _m.c10).groupby(_m.index.date).mean()
if os.environ.get("R64_PRICE_GUARD", "1") != "0":
    dropped = sorted(x for x in USABLE if match.get(x, 0.0) < 0.8)
    USABLE -= set(dropped)
    print("price guard: dropped %s" % (", ".join(str(x) for x in dropped) or "none"))
print("usable capture sessions: %d of %d (%s .. %s)" % (len(USABLE), len(q), min(USABLE), max(USABLE)))
tr = run_backtest(N10, arrays=A, params=CROWN, cost_pts=COST, return_trades=True)["trades"]
rows = []
for x in tr:
    sig = IDX[int(x[0]) - 1]
    if sig.date() not in USABLE:
        continue
    side = int(np.sign(x[3]))
    bd = np.nan if bar_miss.get(sig, False) else bar_delta.get(sig, np.nan)
    cd = np.nan if cum_miss.get(sig, False) else cum_at_bar_end.get(sig, np.nan)
    rows.append(dict(sig=sig, day=sig.date(), side=side, 
                     backed=(np.sign(bd) == side) if (np.isfinite(bd) and bd != 0) else None,
                     cum_backed=(np.sign(cd) == side) if (np.isfinite(cd) and cd != 0) else None))

T = pd.DataFrame(rows)
F = T[T.day >= pd.Timestamp("2026-10-01").date()] if len(T) else T
cap = q[q.index >= pd.Timestamp("2026-10-01").date()]
print("FORWARD (from 2026-10-01, outcome-blind - no P&L read): capture sessions %d, usable %d" % (
    len(cap), sum(1 for x in cap.index if x in USABLE)))
for tag in ("backed", "cum_backed"):
    s = F[tag] if len(F) else pd.Series(dtype=object)
    print("  %-11s tagged %d of %d trades (backed %d / unbacked %d); untagged %d" % (
        tag, s.notna().sum(), len(F), (s == True).sum(), (s == False).sum(), s.isna().sum()))
if len(F):
    days = (F.day.max() - pd.Timestamp("2026-10-01").date()).days + 1
    rate = F["backed"].notna().sum() / max(days, 1)
    print("  pace: %.2f tagged trades a calendar day -> 150 tagged at about %s" % (
        rate, (pd.Timestamp("2026-10-01") + pd.Timedelta(days=int(150 / rate))).date() if rate > 0 else "never"))

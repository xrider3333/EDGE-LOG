# -*- coding: utf-8 -*-
"""NOISE ROUND 60 - the frontier configs on sessions NO validate has seen (2026-07-16 .. 2026-09-16).

Every NOISE validate in rounds 54-60 ended at 2026-07-16 (or 2026-08-12 for the older ones), and the master now
runs to 2026-09-16 on Databento bars (Yahoo rows after that are excluded - a different feed across a roll).
About 45 sessions: REPORTED, never judged - at NOISE's ~1.2 trades a day this is a sanity column, not evidence.

  python tools/r60_noise_fresh_tail.py  -> tools/r37_results/r60_fresh_tail.txt
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

LAST = pd.Timestamp("2026-09-16").date()
T0, T1 = pd.Timestamp("2026-07-16").date(), pd.Timestamp("2026-08-12").date()
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07")
IDX = pd.DatetimeIndex(A["index"])


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
ROWS = [
    ("#304 live crown, raw", "NOISE_1_0.py", CROWN),
    ("#243 retired crown, raw", "NOISE_1_0.py", dict(CROWN, lookback=44, vol_skip_pct=90.0)),
    ("#382 pick: 30-min squeeze 2.0x (Webull base)", "NOISE_1_8_CT304.py",
     dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0)),
    ("hourly squeeze 1.5x (round-55 pick)", "NOISE_1_8_CT304H.py", dict(gate_len=20, gate_ratio=1.0, tilt_mult=1.5)),
    ("hourly FILTER 20/1.0 (textbook)", "NOISE_1_9_HSQ304H.py", dict(gate_len=20, gate_ratio=1.0)),
    ("hourly FILTER 20/1.15 (#398 crown)", "NOISE_1_9_HSQ304H.py", dict(gate_len=20, gate_ratio=1.15)),
    ("#394 crown waits 2 closes", "NOISE_1_0.py", dict(CROWN, confirm_bars=2)),
]


def stats(p):
    p = np.asarray(p, float)
    if not len(p):
        return "  0 trades"
    cum = np.cumsum(p)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    pf = gw / gl if gl > 0 else float("inf")
    return "%4d tr  $%8s  PF %5.2f  DD $%6s  win %3.0f%%" % (len(p), format(int(p.sum()), ","), pf,
                                                              format(int(dd), ","), 100 * (p > 0).mean())


print("fresh tail: %s .. %s (unseen by the round 54-60 validates) and %s .. %s (unseen by every NOISE validate)"
      % (T0, LAST, T1, LAST))
print("%-46s | %-50s | %-50s" % ("config", "2026-07-16 .. 09-16", "2026-08-12 .. 09-16"))
for name, fn, params in ROWS:
    r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=0.533, return_trades=True)
    t = r["trades"] if r and r.get("trades") else []
    d = np.array([IDX[max(int(x[0]) - 1, 0)].date() for x in t])
    p = np.array([x[2] * 20.0 for x in t], float)
    a = p[(d >= T0) & (d <= LAST)]
    b = p[(d >= T1) & (d <= LAST)]
    print("%-46s | %-50s | %-50s" % (name, stats(a), stats(b)))

# ---- how unusual is the filter's silence? longest runs of sessions between two kept trades --------------
print("\nhourly squeeze FILTER dry spells, full history to %s (sessions between consecutive kept trades)" % LAST)
SESS = np.array(sorted(set(d for d in IDX.date if d <= LAST)))
spos = {d: i for i, d in enumerate(SESS)}
for name, params in (("20/1.0 (textbook)", dict(gate_len=20, gate_ratio=1.0)),
                     ("20/1.15 (#398 crown)", dict(gate_len=20, gate_ratio=1.15))):
    r = run_backtest(mod("NOISE_1_9_HSQ304H.py"), arrays=A, params=params, cost_pts=0.533, return_trades=True)
    d = sorted({IDX[max(int(x[0]) - 1, 0)].date() for x in r["trades"]} & set(SESS))
    k = np.array([spos[x] for x in d] + [len(SESS) - 1])
    gaps = np.diff(k)
    top = np.argsort(gaps)[::-1][:5]
    print("  %-22s %4d trade days; median gap %d sessions; longest gaps: %s" % (
        name, len(d), int(np.median(gaps)),
        ", ".join("%d from %s" % (gaps[i], SESS[k[i]]) for i in top)))

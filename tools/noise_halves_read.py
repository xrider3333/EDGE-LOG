# -*- coding: utf-8 -*-
"""NOISE HALVES - the failed-break share, forward (a REPORT LINE in the weekly NOISE read; MANAGER #83, 2026-10-10).

NOISE #422 earns on the trend-day break held to the close and loses on the breaks cut at VWAP (the 10-05 anatomy, ledger
2.82; FRONTIER's Q35 on the July trip). This prints, for the #304 core trades #382 and #422 share (sizes differ, entries and
exits do not), the share of each exit kind and each kind's mean in BAND UNITS (signed move over sigma x entry, cost 0.533
included) - a count and a scale-free unit, so neither grows with NQ's price. Forward = signal dates from 2026-07-01 to the
master's last bar; the walk-forward reference (2016-07-01 .. 2025-06-29) and its calendar-year range sit beside it.

NO ALARM (the HALVES draft, C:/EdgeLog/_anatomy_cache/noise_next3/DRAFT_noise_next3_2026-10-10.md): the share swings
0.60-0.80 by year, so a +10-point rise clears the WF p97.5 of a 120-trade window only 27% of the time (240 trades: 40%).
FRONTIER's harm monitor is the alarm. Read it with the year range, never against a line.

NQ 5m RTH no-adjust master (the engine runs signals ratio-adjusted, fills raw - the 10-08 roll guard). Unit P&L comes from
the #304 core run itself: since the roll guard a wrapper's sized pnl no longer divides back to points.
    python tools/noise_halves_read.py
"""
import importlib.util as _ilu
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402

COST = 0.533
WF0, WF1, FWD0 = pd.Timestamp("2016-07-01").date(), pd.Timestamp("2025-06-29").date(), pd.Timestamp("2026-07-01").date()
CORE = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both", window="all_day",
            flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
            daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
KINDS = ("held to close", "VWAP exit", "stop")


def trades():
    m = find_master("NQ", "5m", "rth", "db_noadj_rth")
    A = load_master_arrays(m, date_from="2010-06-07", date_to=str(m.get("date_to"))[:10])
    O, C = np.asarray(A["open"], float), np.asarray(A["close"], float)
    idx, day = pd.DatetimeIndex(A["index"]), np.asarray(A["day_id"])
    path = os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py")
    tr = sorted(run_backtest(load_strategy(path), arrays=A, params=CORE, cost_pts=COST, return_trades=True)["trades"],
                key=lambda t: int(t[0]))
    s = _ilu.spec_from_file_location("_n10_halves", path)
    N = _ilu.module_from_spec(s)
    s.loader.exec_module(N)
    starts = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    ends = np.r_[starts[1:], len(day)]
    s_of = np.repeat(np.arange(len(starts)), ends - starts)
    sig = N._sigma_matrix(O, C, list(zip(starts, ends)), CORE["lookback"])
    rows = []
    for t in tr:
        k0, k1, net, side, epx = int(t[0]), int(t[1]), float(t[2]), float(np.sign(t[3])), float(t[4])
        si = s_of[k0 - 1]
        xpx = epx + side * (net + COST)
        kind = ("held to close" if k1 == ends[si] - 1 and abs(xpx - C[k1]) < 1e-6 else
                "VWAP exit" if abs(xpx - O[k1]) < 1e-6 else "stop")
        rows.append(dict(date=idx[k0 - 1].date(), kind=kind, bu=side * (xpx - epx - side * COST) / (epx * sig[si, k0 - 1 - starts[si]])))
    return pd.DataFrame(rows), str(m.get("date_to"))[:10]


def block(T):
    n = len(T)
    out = {"n": n}
    for k in KINDS:
        sub = T[T.kind == k]
        out[k] = (len(sub) / n if n else np.nan, sub.bu.mean() if len(sub) else np.nan)
    out["all"] = T.bu.mean() if n else np.nan
    return out


def main():
    T, last = trades()
    wf = T[(T.date >= WF0) & (T.date <= WF1)]
    fw = T[T.date >= FWD0]
    yr = wf.groupby(pd.DatetimeIndex(wf.date).year).kind.apply(lambda s: (s == "VWAP exit").mean())
    print("NOISE HALVES (report line, no alarm) - #304 core = #382 / #422 entries and exits, NQ 5m RTH, cost %.3f, master to %s"
          % (COST, last))
    for lab, B in (("walk-forward 2016-07..2025-06", block(wf)), ("forward from 2026-07-01", block(fw))):
        print("  %-30s n %5d | failed (VWAP) %5.1f%% mean %+.2f bu | held to close %5.1f%% mean %+.2f bu | stop %4.1f%% | "
              "all %+.3f bu" % (lab, B["n"], 100 * B["VWAP exit"][0], B["VWAP exit"][1], 100 * B["held to close"][0],
                                B["held to close"][1], 100 * B["stop"][0], B["all"]))
    print("  WF failed share by calendar year: %s (range %.0f-%.0f%%)" % (
        ", ".join("%d %.0f%%" % (y, 100 * v) for y, v in yr.items()), 100 * yr.min(), 100 * yr.max()))
    if len(fw):
        print("  forward failed share %.1f%% on %d trades - %s the WF year range" % (
            100 * (fw.kind == "VWAP exit").mean(), len(fw),
            "inside" if yr.min() <= (fw.kind == "VWAP exit").mean() <= yr.max() else "OUTSIDE"))


if __name__ == "__main__":
    main()

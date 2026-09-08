"""PARITY: the ETFDIP_* plugins on the new 1d masters vs tools/r25_weak_edge_book.py.

The plugin files only earn the right to be queued as BOOK legs if they reproduce the
pre-registered r25 harness. This script proves it leg by leg:

  r25 side    — imports r25_weak_edge_book and calls ITS OWN `run_cell` (not a
                re-implementation), fed the MASTER's arrays.
  plugin side — augur_engine.run_backtest on the same registered 1d master, sliced to the
                same first bar (date_from 2009-06-01) so the warm-up consumes the same
                days, with cost_pts=0 (the plugin bills its own costs).
  both sides  — trades filtered to exit date >= 2010-06-07, r25's WIN_FROM. Compared on
                n / net / PF and on the trade lists themselves. Same bars on both sides,
                so a difference here is LOGIC and nothing else. That is the gate.

  drift column— r25's own `run_cell` is ALSO run on a fresh yfinance download made exactly
                the way r25 makes it (start 2009-06-01, end 2025-06-30, auto_adjust=True),
                and its net is printed beside the others. It is not a gate. Yahoo re-scales
                a total-return series on every dividend and rounds its adjusted prints, so
                two downloads minutes apart differ by ~0.02% of price; the PB20 rule turns
                on knife-edge comparisons (`low <= EMA`, `close > the signal day's high`)
                and one flipped comparison moves a trade. Measured on 2026-09-08: two r25
                runs 20 minutes apart disagreed by 1 trade on QQQ/PB20L and $169 on
                TLT/PB20L, with the DBL7 and RSI2 legs identical. So the drift column
                bounds how reproducible r25 itself is; it is not a defect in the plugins.

WHY the slice starts a year before the window: r25 gives its ETF legs a year of pre-window
bars to warm the 200-day trend filter and only then drops trades that closed before
2010-06-07. Slicing the master at 2010-06-07 instead would spend the first ~210 trading
days of the window on warm-up and lose about a year of trades. A BOOK job has ONE window
for every leg (augur_engine/book.py `run_book`), so this is a real difference between the
parity read here and what a book run pinned to 2010-06-07 will produce — stated, not hidden.

Also printed: the max |price| difference between the fresh download and the master over
the shared bars. Yahoo total-return prices are re-scaled on every dividend, so a master
built on a different day is a different tape; a non-zero number here explains any PnL gap.

Usage: python tools/etf_book_parity.py [--tickers GLD,TLT,IWM,QQQ]
"""
import argparse
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest                   # noqa: E402

WARM_FROM = "2009-06-01"      # r25's ETF download start
WIN_FROM = "2010-06-07"       # r25's WIN_FROM (trades before this are dropped)
WIN_TO = "2025-06-29"
SOURCE = "yahoo_adj"

# r25 cell -> (plugin file, params). allow_shorts is the only structural switch.
CELLS = {
    "DBL7L": ("ETFDIP_DBL7_1_0.py", {}),
    "RSI2L": ("ETFDIP_RSI2_1_0.py", {"allow_shorts": False}),
    "RSI2B": ("ETFDIP_RSI2_1_0.py", {"allow_shorts": True}),
    "PB20L": ("ETFDIP_PB20_1_0.py", {}),
}


def _load_r25():
    sp = importlib.util.spec_from_file_location(
        "r25", os.path.join(ROOT, "tools", "r25_weak_edge_book.py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _stats(pnls):
    p = np.asarray(pnls, float)
    if len(p) == 0:
        return 0, 0.0, 0.0
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    return len(p), float(p.sum()), float(gw / gl) if gl > 1e-9 else 99.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="GLD,TLT,IWM,QQQ")
    a = ap.parse_args()
    r25 = _load_r25()
    import yfinance as yf

    lo = pd.Timestamp(WIN_FROM).date()
    rows = []
    worst = 0.0

    def _cell(run_cell, do_, dh_, dl_, dc_, dts, cell):
        out = run_cell(do_, dh_, dl_, dc_, dts, cell,
                       shares_fn=lambda de, o=do_: r25.NOTIONAL / o[de],
                       cost_fn=lambda de, dx, o=do_: r25.ETF_COST / (r25.NOTIONAL / o[de]))
        return [z for z in out if z[0] >= lo]

    for tk in a.tickers.split(","):
        tk = tk.strip()
        master = find_master(tk, "1d", "rth", SOURCE)
        if master is None:
            print(f"{tk}: NO MASTER (run tools/build_etf_masters.py first)")
            continue
        arr = load_master_arrays(master, date_from=WARM_FROM, date_to=WIN_TO)
        mdates = [d.date() for d in arr["index"]]
        mo, mh, ml, mc = arr["open"], arr["high"], arr["low"], arr["close"]

        # r25's own data path, verbatim — drift reference only
        df = yf.download(tk, start=WARM_FROM, end="2025-06-30", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        fo, fh, fl, fc = (df[c].values.astype(float) for c in ["Open", "High", "Low", "Close"])
        fdts = [d.date() for d in df.index]
        k = min(len(mdates), len(fdts))
        if mdates[:k] != fdts[:k]:
            print(f"{tk}: WARNING master/download calendars differ within the first {k} bars")
        worst = max(worst, float(np.abs(mc[:k] - fc[:k]).max()))

        for cell, (plugin, extra) in CELLS.items():
            ref = _cell(r25.run_cell, mo, mh, ml, mc, mdates, cell)      # r25 rule, master bars
            drift = _cell(r25.run_cell, fo, fh, fl, fc, fdts, cell)      # r25 rule, fresh bars
            res = run_backtest(plugin, arrays=arr, params=dict(extra), cost_pts=0.0,
                               return_trades=True)
            tr = (res or {}).get("trades") or []
            idx = arr["index"]
            got = [(idx[min(int(t[1]), len(idx) - 1)].date(), float(t[2])) for t in tr]
            got = [z for z in got if z[0] >= lo]

            n0, net0, pf0 = _stats([z[1] for z in ref])
            n1, net1, pf1 = _stats([z[1] for z in got])
            _, netd, _ = _stats([z[1] for z in drift])
            same_dates = [z[0] for z in ref] == [z[0] for z in got]
            dmax = (max(abs(x[1] - y[1]) for x, y in zip(ref, got))
                    if same_dates and ref else float("nan"))
            ok = (n0 == n1 and abs(net0 - net1) < 1.0 and same_dates)
            rows.append((f"{tk}/{cell}", n0, net0, pf0, n1, net1, pf1, dmax, netd, ok))

    print(f"\nwindow {WIN_FROM} -> {WIN_TO} (data warmed from {WARM_FROM}); both sides on the "
          f"MASTER's bars.\nmax |master close - fresh r25 download close| = ${worst:.4f}\n")
    hdr = (f"{'leg':12}{'r25 n':>7}{'r25 net$':>11}{'r25 PF':>8}"
           f"{'plug n':>8}{'plug net$':>11}{'plug PF':>9}{'max|dPnL|':>11}"
           f"{'r25 fresh$':>12}  parity")
    print(hdr); print("-" * len(hdr))
    for lg, n0, v0, f0, n1, v1, f1, dm, nd, ok in rows:
        print(f"{lg:12}{n0:>7}{v0:>11,.0f}{f0:>8.3f}{n1:>8}{v1:>11,.0f}{f1:>9.3f}"
              f"{dm:>11.4f}{nd:>12,.0f}  {'MATCH' if ok else 'DIFF'}")
    bad = [r for r in rows if not r[-1]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} legs match on identical bars "
          f"(the gate). 'r25 fresh$' is the same r25 rule on a fresh Yahoo pull "
          f"- tape drift, not a gate.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

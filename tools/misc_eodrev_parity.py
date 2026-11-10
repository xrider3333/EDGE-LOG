"""Parity: MISC_EODREV_1_0.py / 1_1.py through the engine on the SPY 5m RTH master vs the opus-hunt harness series.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109) saved net dollars a session per $1 a side:
  1_0  s14_series.pkl  (gross, cost, ...)  - the frozen r3 rule (s14_c1val.py)
  1_1  s19_series.pkl  (net, net_stress)   - the registered composite (s19_xval.py)
This runs the plugin at its defaults through augur_engine.run_backtest and compares dollars a day.
The harness also traded 21 half days on after-hours 10-minute prints; the plugin skips them (reported, not a failure).
    python tools/misc_eodrev_parity.py          (1_0)
    python tools/misc_eodrev_parity.py --v11    (1_1)
"""
import os
import pickle
import sys

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, SHARED)        # the shared checkout holds the master registry; the plugin itself is read from REPO
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/"


def main():
    v11 = "--v11" in sys.argv
    os.chdir(SHARED)                                   # the registry (masters) lives in the shared checkout
    from augur_engine import data as D
    from augur_engine import run_backtest
    m = D.find_master("SPY", "5m", "rth", "alpaca_split_rth")
    arr = D.load_master_arrays(m, date_from="2016-01-04", date_to="2026-06-30")
    name = "MISC_EODREV_1_1.py" if v11 else "MISC_EODREV_1_0.py"
    r = run_backtest(os.path.join(REPO, "augur_strategies", name), params={}, arrays=arr, return_trades=True)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    got = pd.Series({idx[t[0]].normalize(): t[2] for t in r["trades"]})
    if v11:
        want = pickle.load(open(HUNT + "s19_series.pkl", "rb"))[0] * 1e5
    else:
        g, c = pickle.load(open(HUNT + "s14_series.pkl", "rb"))[:2]
        want = (g - c) * 1e5
    j = pd.concat([got.rename("plugin"), want.rename("harness")], axis=1)
    both = j.dropna()
    d = (both.plugin - both.harness).abs()
    print("%s: plugin days %d | harness days %d | both %d | only plugin %d | only harness %d" % (
        name, got.size, want.size, len(both), j.harness.isna().sum(), j.plugin.isna().sum()))
    print("max abs diff $%.6f | plugin total $%.2f | harness total (same days) $%.2f" % (d.max(), both.plugin.sum(), both.harness.sum()))
    if j.plugin.isna().sum():
        print("harness-only days (half days):", [str(x.date()) for x in j.index[j.plugin.isna()][:12]])
    ok = d.max() < 1e-6 and j.harness.isna().sum() == 0
    print("PARITY", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

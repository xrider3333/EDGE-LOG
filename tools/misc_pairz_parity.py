"""Parity: augur_strategies/MISC_PAIRZ_1_0.py at its defaults vs the opus-hunt S76 harness, cell 76c.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S76) saved
  trades_76c.csv  every 76c pair trade (d, a, b, fill_min, exit_idx, gross, cost, net), 2016-01 .. 2025-06-30
  series.pkl      ['76c'] = net $ a session, 2016-07-01 .. 2025-06-30, zero days included
Two checks, both on 2016-07-01 .. 2025-06-30 only:
  1. TRADES: the plugin's own pair trades (its _pair_trades) vs trades_76c.csv, matched on (day, pair).
  2. ENGINE: the plugin through augur_engine.run_backtest on the SPY 5m RTH alpaca_split_rth master (the clock),
     one trade a session, vs the series' non-zero days.
THE SEAL: the plugin's panel runs to 2026-06-30; this tool hands the plugin a copy cut at 2025-06-30 before anything
is computed, and loads the master only to 2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_pairz_parity.py
"""
import importlib.util
import os
import pickle
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S76/"
LO, HI = 20160701, 20250630


def load_plugin_sealed(seal=HI):
    """Import the plugin from this checkout and give it the panel cut at `seal` (nothing later is ever used)."""
    spec = importlib.util.spec_from_file_location("misc_pairz_1_0_parity", os.path.join(REPO, "augur_strategies",
                                                                                       "MISC_PAIRZ_1_0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod._panel()
    if p is None:
        return mod, None
    k = p["dates"] <= seal
    mod._CACHE.clear()
    mod._CACHE["panel"] = {key: (v[k] if isinstance(v, np.ndarray) else v) for key, v in p.items()}
    return mod, mod._CACHE["panel"]


def plugin_trades(mod, p, **kw):
    prm = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    prm.update(kw)
    hc = prm.pop("high_corr_only")
    out = []
    for a, b in (mod.PAIRS_CORR80 if hc else mod.PAIRS):
        r, fi, ei, g, c = mod._pair_trades(p, a, b, **prm)
        out.append(pd.DataFrame({"d": p["dates"][r], "a": a, "b": b, "fill_min": 570 + 10 * fi, "exit_idx": ei,
                                 "gross": g, "cost": c}))
    T = pd.concat(out, ignore_index=True)
    T["net"] = T.gross - T.cost
    return T


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    # ---- 1. trades
    T = plugin_trades(mod, p)
    H = pd.read_csv(HUNT + "trades_76c.csv")
    H["d"] = pd.to_datetime(H.d).dt.strftime("%Y%m%d").astype("int64")
    T = T[(T.d >= LO) & (T.d <= HI)]; H = H[(H.d >= LO) & (H.d <= HI)]
    J = T.merge(H[["d", "a", "b", "fill_min", "exit_idx", "gross", "cost", "net"]], on=["d", "a", "b"], how="outer",
                suffixes=("_p", "_h"), indicator=True)
    both = J[J._merge == "both"]
    same = ((both.fill_min_p == both.fill_min_h) & (both.exit_idx_p == both.exit_idx_h)
            & ((both.net_p - both.net_h).abs() < 1e-6))
    print("TRADES 2016-07-01..2025-06-30: plugin %d | harness %d | matched (day, pair) %d | only plugin %d | "
          "only harness %d | identical fill/exit/net %d (%.2f%% of harness)" % (
              len(T), len(H), len(both), (J._merge == "left_only").sum(), (J._merge == "right_only").sum(),
              same.sum(), 100.0 * same.sum() / max(1, len(H))))
    if (~same).sum() or (J._merge != "both").sum():
        print("  mismatches (first 12):")
        print(J[(J._merge != "both") | ~J.index.isin(both.index[same])].head(12).to_string())
    # ---- 2. engine, one trade a session
    os.chdir(SHARED)                                   # the master registry lives in the shared checkout
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    from augur_engine import run_backtest
    m = D.find_master("SPY", "5m", "rth", "alpaca_split_rth")
    arr = D.load_master_arrays(m, date_from="2016-07-01", date_to="2025-06-30")
    r = run_backtest(mod, params={}, arrays=arr, return_trades=True)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    got = pd.Series({idx[t[0]].normalize(): t[2] for t in r["trades"]})
    want = pickle.load(open(HUNT + "series.pkl", "rb"))["76c"]
    want = want[want != 0]
    j = pd.concat([got.rename("plugin"), want.rename("harness")], axis=1)
    bo = j.dropna()
    d = (bo.plugin - bo.harness).abs()
    print("ENGINE (SPY 5m clock) 2016-07-01..2025-06-30: plugin days %d | harness non-zero days %d | both %d | "
          "only plugin %d | only harness %d | days within $0.01 %d (%.2f%%) | max abs diff $%.4f" % (
              got.size, want.size, len(bo), j.harness.isna().sum(), j.plugin.isna().sum(), (d < 0.01).sum(),
              100.0 * (d < 0.01).sum() / max(1, want.size), d.max() if len(d) else float("nan")))
    if j.plugin.isna().sum():
        print("  harness-only days:", [str(x.date()) for x in j.index[j.plugin.isna()][:12]])
    if j.harness.isna().sum():
        print("  plugin-only days:", [str(x.date()) for x in j.index[j.harness.isna()][:12]])
    ok = same.sum() == len(H) == len(T) and j.isna().sum().sum() == 0 and (d < 0.01).all()
    print("PARITY", "PASS" if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

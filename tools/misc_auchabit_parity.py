"""Parity: augur_strategies/MISC_AUCHABIT_1_0.py at its defaults vs the opus-hunt S86 harness, cell 86a.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S86) saved
  panel.pkl       its inputs (10-minute bars, daily split / raw closes), 2016-01-04 .. 2025-06-30
  trades_86a.csv  every 86a pick (day, name, side, R, raw_prev_close), 2017-04-03 .. 2025-06-30 (86c: trades_86c.csv)
  series.pkl      ['86a'] = net $ a FULL session, 2016-07-01 .. 2025-06-30, zero before 2017-04-01 and on no-trade days
Checks, all on <= 2025-06-30:
  0. DATA    the pinned panel vs panel.pkl: rows, FULL flags, O50 / C50 / official close / raw close, membership.
  1. PICKS   the plugin's own picks (its _picks) vs trades_86a.csv on (day, name, side), with R and the prior raw close.
  2. ENGINE  the plugin through augur_engine.run_backtest on the SPY 5m RTH alpaca_split_rth master (the clock), one
             trade a session, vs the series' non-zero days: days matched, net plugin vs hunt (pct), daily correlation.
  3. 86c     weekday_habit ON, period_len 20 vs trades_86c.csv / series '86c' (the other prereg cell on the grid).
  4. OVERLAP daily correlation of the plugin's 86a with PICK6 = s25_series.pkl ('U100-k5', 'X composite'), net at 1 cent
             and $100k a side = (gross - (2 x cost - 0.6e-4)) x 1e5, sliced to <= 2025-06-30 when read.
THE SEAL: the plugin's panel runs to 2026-06-30; this tool hands the plugin a copy cut at 2025-06-30 before anything is
computed, loads the master only to 2025-06-30 and slices every hunt series at read. No return or PnL after 2025-06-30
is computed or printed.
    python tools/misc_auchabit_parity.py
"""
import importlib.util
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/"
S86 = HUNT + "futures/S86/"
SEAL = 20250630
LO, HI = "2017-04-01", "2025-06-30"
EARLY_HUNT = pd.to_datetime([
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03",
    "2024-11-29", "2024-12-24"])


def load_plugin_sealed(seal=SEAL):
    """Import the plugin from this checkout and give it the panel cut at `seal` (nothing later is ever used).
    Returns (module, the cut panel arrays) or (module, None) when the pinned panel is not on this machine."""
    spec = importlib.util.spec_from_file_location("misc_auchabit_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_AUCHABIT_1_0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = mod._read_panel()
    if a is None:
        return mod, None
    k = a["dates"] <= int(seal)
    a = {key: (v if key == "names" else v[k]) for key, v in a.items()}
    mod._CACHE.clear()
    mod._CACHE["panel"] = mod._prepare(**a)
    return mod, a


def plugin_picks(mod, **kw):
    """The plugin's picks as a frame (day, name, side, R, raw_prev_close) - the trades_86x.csv layout."""
    prm = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    prm.update(kw)
    p = mod._CACHE["panel"]
    Rv = p["R"].to_numpy()
    rows = []
    for i, hi, lo in mod._picks(p, prm["period_len"], prm["k"], prm["min_price"], prm["weekday_habit"]):
        for side, ii in ((1, hi), (-1, lo)):
            for j in ii:
                rows.append((int(p["dates"][i]), p["names"][j], side, float(Rv[i, j]), float(p["rp"][i, j])))
    return pd.DataFrame(rows, columns=["d", "name", "side", "R", "raw_prev_close"])


def hunt_trades(cell):
    H = pd.read_csv(S86 + "trades_%s.csv" % cell, float_precision="round_trip")
    H["d"] = pd.to_datetime(H.day).dt.strftime("%Y%m%d").astype("int64")
    return H[H.d <= SEAL]


def compare_picks(T, H, lab):
    lo = int(LO.replace("-", ""))
    T = T[(T.d >= lo) & (T.d <= SEAL)]
    J = T.merge(H[["d", "name", "side", "R", "raw_prev_close"]], on=["d", "name", "side"], how="outer",
                suffixes=("_p", "_h"), indicator=True)
    both = J[J._merge == "both"]
    rsame = ((both.R_p == both.R_h) | (both.R_p.isna() & both.R_h.isna())) & (both.raw_prev_close_p == both.raw_prev_close_h)
    print("PICKS %s %s..%s: plugin %d | hunt %d | matched (day, name, side) %d | only plugin %d | only hunt %d | "
          "same R and prior raw close %d (%.2f%% of hunt) | trade days plugin %d hunt %d" % (
              lab, LO, HI, len(T), len(H), len(both), (J._merge == "left_only").sum(), (J._merge == "right_only").sum(),
              rsame.sum(), 100.0 * rsame.sum() / max(1, len(H)), T.d.nunique(), H.d.nunique()))
    bad = J[(J._merge != "both")]
    if len(bad):
        print(bad.head(12).to_string())
    return len(both) == len(H) == len(T) and bool(rsame.all())


def check_data(a):
    Z = pickle.load(open(S86 + "panel.pkl", "rb"))
    B = Z["B"]
    hn = [s for s in Z["names"] if s != "SPY"]
    tdays = Z["split_c"].index.union(B["O1550"].index)
    assert tdays.max() <= pd.Timestamp("2025-06-30")
    rows = pd.to_datetime(pd.Series(a["dates"]).astype(str), format="%Y%m%d")
    ok = len(rows) == len(tdays) and bool((rows.values == tdays.values).all())
    hfull = B["O1550"]["SPY"].reindex(tdays).notna().values & ~tdays.isin(EARLY_HUNT)
    ok_full = bool((a["full"] == hfull).all())
    ix = [a["names"].index(s) for s in hn]
    res = {}
    for key, ref in (("o50", B["O1550"]), ("c50", B["C1550"]), ("dc", Z["split_c"]), ("raw", Z["raw_c"])):
        x = np.asarray(a[key], np.float32)[:, ix]
        y = ref.reindex(index=tdays, columns=hn).to_numpy(np.float32)
        res[key] = bool((np.isnan(x) == np.isnan(y)).all() and (x[~np.isnan(x)] == y[~np.isnan(y)]).all())
    U = json.load(open(HUNT + "universe_pit100.json"))
    M = np.zeros((len(tdays), len(hn)), bool)
    for y in range(2017, 2026):
        r = tdays.year == y
        M[np.ix_(r, [hn.index(s) for s in U[str(y)][:100] if s in hn])] = True
    res["member"] = bool((np.asarray(a["member"])[:, ix] == M).all())
    print("DATA <= 2025-06-30: rows %d vs hunt %d same %s | FULL %d same %s | bit-identical on the hunt's %d names: %s"
          % (len(rows), len(tdays), ok, int(a["full"].sum()), ok_full, len(hn), res))
    return ok and ok_full and all(res.values())


def engine_series(mod, arr, **kw):
    from augur_engine import run_backtest
    r = run_backtest(mod, params=kw, arrays=arr, return_trades=True)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    s = pd.Series({idx[t[0]].normalize(): t[2] for t in r["trades"]}).sort_index()
    assert s.index.max() <= pd.Timestamp("2025-06-30")
    return s


def compare_series(got, cell):
    want = pickle.load(open(S86 + "series.pkl", "rb"))[cell]
    want = want[want.index <= "2025-06-30"]
    want = want[want != 0]
    early = got[got.index < LO]
    g = got[(got.index >= LO) & (got.index <= HI)]
    j = pd.concat([g.rename("plugin"), want.rename("hunt")], axis=1)
    bo = j.dropna()
    d = (bo.plugin - bo.hunt).abs()
    jj = j.fillna(0.0)
    pct = 100.0 * (g.sum() - want.sum()) / abs(want.sum())
    print("ENGINE %s (SPY 5m clock) %s..%s: plugin days %d | hunt non-zero days %d | both %d | only plugin %d | "
          "only hunt %d | days within $0.01 %d (%.2f%%) | max abs diff $%.2e | net plugin $%.2f vs hunt $%.2f (%+.4f%%) | "
          "daily corr %.6f" % (cell, LO, HI, g.size, want.size, len(bo), j.hunt.isna().sum(), j.plugin.isna().sum(),
                               (d < 0.01).sum(), 100.0 * (d < 0.01).sum() / max(1, want.size), d.max() if len(d) else np.nan,
                               g.sum(), want.sum(), pct, jj.plugin.corr(jj.hunt)))
    if len(early):
        print("  the plugin also trades %d session(s) before %s (%s .. %s): the hunt counts trades from %s, the rule "
              "allows them from the first day with a 60-session habit" % (len(early), LO, early.index[0].date(),
                                                                         early.index[-1].date(), LO))
    if j.plugin.isna().sum():
        print("  hunt-only days:", [str(x.date()) for x in j.index[j.plugin.isna()][:12]])
    if j.hunt.isna().sum():
        print("  plugin-only days:", [str(x.date()) for x in j.index[j.hunt.isna()][:12]])
    return j.isna().sum().sum() == 0 and (d < 0.01).all(), g


def pick6_overlap(s86):
    g, c = pickle.load(open(HUNT + "s25_series.pkl", "rb"))[("U100-k5", "X composite")]
    g = g[g.index <= "2025-06-30"]
    c = c[c.index <= "2025-06-30"]
    s23 = (g - (2 * c - 0.6e-4)) * 1e5
    i = s86.index.union(s23.index)
    a = s86.reindex(i).fillna(0.0).loc[LO:HI]
    b = s23.reindex(i).fillna(0.0).loc[LO:HI]
    both = s86.index.intersection(s23.index)
    both = both[(both >= LO) & (both <= HI)]
    out = {"corr_union_zero_filled": round(float(a.corr(b)), 3),
           "corr_common_days": round(float(s86.loc[both].corr(s23.loc[both])), 3), "common_days": int(len(both)),
           "by_stretch": {k: round(float(a.loc[x:y].corr(b.loc[x:y])), 3) for k, (x, y) in (
               ("2017-04..2020-12", ("2017-04-01", "2020-12-31")), ("2021-01..2025-06", ("2021-01-01", HI)))}}
    print("OVERLAP 86a vs PICK6 (s25 U100-k5 X composite, 1 cent, $100k a side) %s..%s: %s" % (LO, HI, out))
    return out


def main():
    mod, a = load_plugin_sealed()
    if a is None:
        sys.exit("no pinned panel on this machine")
    ok0 = check_data(a)
    ok1 = compare_picks(plugin_picks(mod), hunt_trades("86a"), "86a")
    ok3 = compare_picks(plugin_picks(mod, weekday_habit=True, period_len=20), hunt_trades("86c"), "86c")
    os.chdir(SHARED)                                   # the master registry lives in the shared checkout
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    m = D.find_master("SPY", "5m", "rth", "alpaca_split_rth")
    arr = D.load_master_arrays(m, date_from="2016-07-01", date_to="2025-06-30")
    ok2, s86 = compare_series(engine_series(mod, arr), "86a")
    ok4, _ = compare_series(engine_series(mod, arr, weekday_habit=True, period_len=20), "86c")
    pick6_overlap(s86)
    ok = ok0 and ok1 and ok2 and ok3 and ok4
    print("PARITY", "PASS" if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Parity: augur_strategies/MISC_AUCREV_1_0.py at its defaults vs the opus-hunt S85 harness, cell 85a.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S85, s85_lib.py + s85_run.py) saved
  daily_85a.csv   gross / cost / net $ a traded session at $100k a side, BASE cost, 2017-04-03 .. 2025-06-30
  series.pkl      ['85a'] = the same net $ series
Three checks, all on sessions <= 2025-06-30 only:
  1. PICKS: the plugin's picks (hygiene applied AFTER the pick) vs the harness's eligibility (s85_lib: the 8%
     mismatch filter and the post-entry print checks applied BEFORE ranking), rebuilt here on the same frames.
  2. DAILY: the plugin's own daily nets (its _daily) vs daily_85a.csv: sessions, gross, cost, net, correlation.
  3. ENGINE: the plugin through augur_engine.run_backtest on the SPY 5m RTH alpaca_split_rth master (the clock),
     one trade a session, vs series.pkl['85a'].
THE SEAL: the plugin's panel runs to 2026-06-30; this tool cuts the panel's ARRAYS at 2025-06-30 before the plugin
derives anything, and loads the master only to 2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
The hunt's series starts 2017-04-03 (its DISC stretch began 2017-04-01); the plugin also trades 2017-01-03 ..
2017-03-31 (the universe starts 2017) - those sessions are counted apart, never a gap.
    python tools/misc_aucrev_parity.py
"""
import hashlib
import importlib.util
import os
import pickle
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S85/"
SEAL = 20250630
HUNT_FROM = 20170401
SESSION_KEYS = ("dates", "early", "full", "c30", "c40", "o55", "c55", "split", "raw", "member")   # row = a session


def fresh_plugin():
    """A fresh copy of the plugin module from this checkout (its own empty cache)."""
    spec = importlib.util.spec_from_file_location("misc_aucrev_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_AUCREV_1_0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CACHE.clear()
    return mod


def sealed_arrays(mod, seal=SEAL):
    """The pinned panel's raw arrays with every session row after `seal` removed (None when not on this machine)."""
    if not os.path.exists(mod.PANEL_PATH):
        return None
    with open(mod.PANEL_PATH, "rb") as fh:
        if hashlib.sha256(fh.read()).hexdigest() != mod.PANEL_SHA256:
            raise RuntimeError("panel is not the pinned build")
    z = np.load(mod.PANEL_PATH, allow_pickle=False)
    k = np.asarray(z["dates"]).astype("int64") <= int(seal)
    return {key: (np.asarray(z[key])[k] if key in SESSION_KEYS else np.asarray(z[key])) for key in z.files}


def load_plugin_sealed(seal=SEAL):
    """Import the plugin from this checkout and give it the panel's arrays cut at `seal` (nothing later is derived
    or used). Returns (module, frames) or (module, None) when the pinned panel is not on this machine."""
    mod = fresh_plugin()
    cut = sealed_arrays(mod, seal)
    mod._CACHE["panel"] = None if cut is None else mod._frames(cut)
    return mod, mod._CACHE["panel"]


def defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def plugin_daily(mod, p, **kw):
    """The plugin's net $ a traded session (its own _daily) as a Series indexed by yyyymmdd."""
    prm = defaults(mod)
    prm.update(kw)
    dd, net = mod._daily(p, **prm)
    return pd.Series(net, index=dd)


def hunt_style_picks(mod, p, **kw):
    """The harness's order: post-entry checks and the 8% filter applied BEFORE ranking (s85_lib.build/picks)."""
    prm = defaults(mod)
    prm.update(kw)
    nm = p["names"]
    r = p["r1530"] if prm["freeze_1540"] else p["r1540"]
    resid = r[nm] - mod._beta(p, prm["beta_len"]).mul(r["SPY"], axis=0)
    elig = p["pre"] & (p["rp"] >= float(prm["min_price"])) & p["okx"]
    if prm["nasdaq_only"]:
        elig = elig & p["nas"][None, :]
    s = resid.where(elig)
    n = s.notna().sum(axis=1)
    ra = s.rank(axis=1, ascending=True, method="first")
    rd = s.rank(axis=1, ascending=False, method="first")
    day = (n >= int(prm["min_names"])).to_numpy()[:, None]
    return (ra <= int(prm["k"])) & day, (rd <= int(prm["k"])) & day


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    assert int(p["days"].max()) <= SEAL
    prm = defaults(mod)
    # ---- 1. picks: plugin (hygiene after the pick) vs harness order (hygiene before ranking)
    L, S, n = mod._picks(p, prm["k"], prm["beta_len"], prm["min_price"], prm["beta_adjust"], prm["freeze_1540"],
                         prm["nasdaq_only"], prm["min_names"])
    L2, S2 = L & p["okx"], S & p["okx"]
    Lh, Sh = hunt_style_picks(mod, p)
    differ = ((L2 != Lh) | (S2 != Sh)).any(axis=1)
    dropped = ((L & ~p["okx"]) | (S & ~p["okx"])).to_numpy().sum()
    print("PICKS <= 2025-06-30: sessions with a pick %d | sessions where plugin and harness-order picks differ %d | "
          "picked name-days dropped by the after-pick hygiene %d" % (int(L.any(axis=1).sum()), int(differ.sum()),
                                                                    int(dropped)))
    if differ.any():
        print("  differing sessions:", [int(d) for d in differ.index[differ.to_numpy()][:12]])
    # ---- 2. daily nets vs daily_85a.csv
    got = plugin_daily(mod, p)
    H = pd.read_csv(HUNT + "daily_85a.csv")
    H.index = pd.to_datetime(H.iloc[:, 0]).dt.strftime("%Y%m%d").astype("int64")
    H = H[H.index <= SEAL]
    early = got[got.index < HUNT_FROM]
    g = got[(got.index >= HUNT_FROM) & (got.index <= SEAL)]
    j = pd.concat([g.rename("plugin"), H["net"].rename("hunt")], axis=1)
    bo = j.dropna()
    d = (bo.plugin - bo.hunt).abs()
    print("DAILY 2017-04-01..2025-06-30: plugin sessions %d | hunt sessions %d | matched %d | only plugin %d | "
          "only hunt %d | max abs diff $%.2e | net plugin $%.2f vs hunt $%.2f (%+.6f%%) | daily corr %.9f" % (
              len(g), len(H), len(bo), int(j.hunt.isna().sum()), int(j.plugin.isna().sum()), d.max(),
              bo.plugin.sum(), H.net.sum(), 100.0 * (g.sum() / H.net.sum() - 1.0), bo.plugin.corr(bo.hunt)))
    print("  plugin sessions before the hunt's 2017-04-01 slice (universe starts 2017-01-03): %d (%s .. %s)" % (
        len(early), early.index.min() if len(early) else "-", early.index.max() if len(early) else "-"))
    # ---- 3. engine on the SPY 5m clock
    os.chdir(SHARED)                                   # the master registry lives in the shared checkout
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    from augur_engine import data as D
    from augur_engine import run_backtest
    m = D.find_master("SPY", "5m", "rth", "alpaca_split_rth")
    arr = D.load_master_arrays(m, date_from="2016-01-04", date_to="2025-06-30")
    idx = pd.DatetimeIndex(arr["index"])
    idx = (idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx)
    assert idx.max() < pd.Timestamp("2025-07-01")
    r = run_backtest(mod, params={}, arrays=arr, return_trades=True)
    eng = pd.Series({int(idx[t[0]].strftime("%Y%m%d")): t[2] for t in r["trades"]})
    ok_bars = all(idx[t[0]].hour * 60 + idx[t[0]].minute == 950 and idx[t[1]].hour * 60 + idx[t[1]].minute == 955
                  and idx[t[0]].date() == idx[t[1]].date() for t in r["trades"])
    want = pickle.load(open(HUNT + "series.pkl", "rb"))["85a"]
    want.index = pd.DatetimeIndex(want.index).strftime("%Y%m%d").astype("int64")
    want = want[want.index <= SEAL]
    e2 = eng[eng.index >= HUNT_FROM]
    j2 = pd.concat([e2.rename("engine"), want.rename("hunt")], axis=1)
    b2 = j2.dropna()
    d2 = (b2.engine - b2.hunt).abs()
    print("ENGINE (SPY 5m clock) 2017-04-01..2025-06-30: engine trades %d | hunt sessions %d | matched %d | "
          "only engine %d | only hunt %d | max abs diff $%.2e | every trade enters on the 15:50 bar and exits on the "
          "same day's 15:55 bar: %s | engine trades before 2017-04-01: %d" % (
              len(e2), len(want), len(b2), int(j2.hunt.isna().sum()), int(j2.engine.isna().sum()),
              d2.max() if len(d2) else float("nan"), ok_bars, int((eng.index < HUNT_FROM).sum())))
    if j2.engine.isna().any():
        print("  hunt-only sessions:", [int(x) for x in j2.index[j2.engine.isna().to_numpy()][:12]])
    if j2.hunt.isna().any():
        print("  engine-only sessions:", [int(x) for x in j2.index[j2.hunt.isna().to_numpy()][:12]])
    ok = (not differ.any() and len(bo) == len(H) == len(g) and (d < 1e-6).all()
          and len(b2) == len(want) == len(e2) and (d2 < 1e-6).all() and ok_bars)
    print("PARITY", "PASS (exact)" if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Parity: augur_strategies/MISC_NIGHTPERSIST_1_0.py at its defaults vs the opus-hunt S83 harness, cell 83d.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S83: s83_lib.py + s83_run.py) saved
  trades_83d.csv  one row per traded night, indexed by the EXIT day: gross / cost by side, missing exits, the eligible
                  count n, net $ at $100k a side (trades_83a / 83b / 83c.csv for the other three cells)
  series.pkl      ['83d'] = net $ per session 2017-04-03 .. 2025-06-30 by exit day, zero days included
Checks, all on sessions <= 2025-06-30 only:
  1. PICKS: the plugin's picks (the open print of t before the pick, t's close prints checked AFTER the pick) vs the
     harness order (t's close prints required before ranking), rebuilt here on the same frames.
  2. NIGHTS: the plugin's own nights (its _book) vs trades_83d.csv by exit day: nights, eligible count, missing exits,
     gross and cost by side, net; totals and daily correlation.
  3. CELLS: the switches at cells 83a / 83b / 83c vs trades_83a / 83b / 83c.csv (nights and net).
  4. ENGINE: the plugin through augur_engine.run_backtest on the SPY 5m RTH alpaca_split_rth master (the clock), one
     trade a night, vs series.pkl['83d']: every trade enters on t's 15:55 bar and exits on the next clock session's
     09:30 bar, which must be the harness's exit day; mark_open_trades = minus half the night's cost.
THE SEAL: the plugin's panel runs to 2026-06-30; this tool cuts the panel's ARRAYS at 2025-06-30 before the plugin
derives anything (so the last entry is 2025-06-27, as in the harness) and loads the master only to 2025-06-30. No
return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_nightpersist_parity.py
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
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S83/"
SEAL = 20250630
HUNT_FROM = 20170401
SESSION_KEYS = ("dates", "o", "c", "r", "member", "full", "half", "spy_open", "spy_close")   # row = a session
CELLS = {"83a": {"beta_resid": True, "lookback": 120}, "83b": {"beta_resid": True, "lookback": 250},
         "83c": {"beta_resid": True, "tug": True, "lookback": 60}}
COLS = ["n", "miss", "gl", "gs", "cl", "cs", "g", "c", "net"]


def fresh_plugin():
    """A fresh copy of the plugin module from this checkout (its own empty cache)."""
    spec = importlib.util.spec_from_file_location("misc_nightpersist_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_NIGHTPERSIST_1_0.py"))
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


def defaults(mod, **kw):
    kn = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    kn.update(kw)
    return mod._knobs(kn)


def plugin_nights(mod, p, **kw):
    """The plugin's nights (its _book) indexed by the EXIT day, with the entry day as a column."""
    bk = mod._book(p, **defaults(mod, **kw)).copy()
    bk["entry"] = bk.index.to_numpy()
    return bk.set_index("exit")


def hunt_trades(cell):
    H = pd.read_csv(HUNT + "trades_%s.csv" % cell, parse_dates=["exit"])
    H.index = H["exit"].dt.strftime("%Y%m%d").astype("int64")
    return H[H.index <= SEAL]


def hunt_style_picks(mod, p, kn):
    """The harness's order (s83_lib.trade): t's close prints (split and raw) required BEFORE ranking."""
    S = mod._signal(p, kn["lookback"], kn["min_price"], kn["beta_resid"], kn["tug"])
    el = (p["member"] & (p["rp"] >= float(kn["min_price"])) & S.notna() & p["closed"]
          & p["dayok"][:, None])
    ne = el.sum(axis=1)
    el = el & (ne >= int(kn["min_names"])).to_numpy()[:, None]
    sc = S.where(el)
    rk = sc.rank(axis=1, ascending=False, method="first")
    n = sc.notna().sum(axis=1)
    act = (n >= int(kn["min_names"])).to_numpy()[:, None]
    k = int(kn["k"])
    return (rk <= k) & act, (rk > (n.to_numpy()[:, None] - k)) & sc.notna() & act


def compare_nights(got, H, cols):
    j = got[cols].join(H[cols], rsuffix="_h", how="outer")
    both = j.dropna(subset=["net", "net_h"])
    dif = {c: float((both[c] - both[c + "_h"]).abs().max()) if len(both) else float("nan") for c in cols}
    return dict(plugin=len(got), hunt=len(H), matched=len(both), only_plugin=int(j["net_h"].isna().sum()),
                only_hunt=int(j["net"].isna().sum()), maxdiff=dif, net_plugin=float(got["net"].sum()),
                net_hunt=float(H["net"].sum()),
                corr=float(both["net"].corr(both["net_h"])) if len(both) > 2 else float("nan"),
                hunt_only_days=[int(x) for x in j.index[j["net"].isna().to_numpy()][:12]],
                plugin_only_days=[int(x) for x in j.index[j["net_h"].isna().to_numpy()][:12]])


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    assert int(p["days"].max()) <= SEAL
    kn = defaults(mod)
    ok = True
    # ---- 1. picks: plugin (close prints checked after the pick) vs harness order (before ranking)
    L, S, n = mod._picks(p, kn["lookback"], kn["k"], kn["min_price"], kn["beta_resid"], kn["tug"], kn["min_names"])
    L2, S2 = L & p["closed"], S & p["closed"]
    Lh, Sh = hunt_style_picks(mod, p, kn)
    differ = ((L2 != Lh) | (S2 != Sh)).any(axis=1)
    dropped = int(((L & ~p["closed"]) | (S & ~p["closed"])).to_numpy().sum())
    print("PICKS <= 2025-06-30: sessions with a pick %d | sessions where plugin and harness-order picks differ %d | "
          "picked name-nights dropped by the after-pick close-print check %d" % (
              int(L.any(axis=1).sum()), int(differ.sum()), dropped))
    if differ.any():
        print("  differing sessions:", [int(d) for d in differ.index[differ.to_numpy()][:12]])
    ok &= not differ.any()
    # ---- 2. nights vs trades_83d.csv
    got = plugin_nights(mod, p)
    H = hunt_trades("83d")
    r = compare_nights(got, H, COLS)
    print("NIGHTS 83d (by exit day, all <= 2025-06-30): plugin %d | hunt %d | matched %d | only plugin %d | only hunt "
          "%d | net plugin $%.2f vs hunt $%.2f (%+.6f%%) | corr %.9f" % (
              r["plugin"], r["hunt"], r["matched"], r["only_plugin"], r["only_hunt"], r["net_plugin"], r["net_hunt"],
              100.0 * (r["net_plugin"] / r["net_hunt"] - 1.0), r["corr"]))
    print("  max abs diff by column:", {c: "%.2e" % v for c, v in r["maxdiff"].items()})
    print("  first / last exit: plugin %s .. %s | hunt %s .. %s | missing exit opens booked 0: plugin %d, hunt %d" % (
        got.index.min(), got.index.max(), H.index.min(), H.index.max(), int(got["miss"].sum()), int(H["miss"].sum())))
    if r["only_hunt"] or r["only_plugin"]:
        print("  hunt-only exits:", r["hunt_only_days"], "| plugin-only exits:", r["plugin_only_days"])
    ok &= (r["matched"] == r["plugin"] == r["hunt"] and all(v < 1e-6 for v in r["maxdiff"].values()))
    # ---- 3. the other cells through the switches
    for cell, kw in CELLS.items():
        rc = compare_nights(plugin_nights(mod, p, **kw), hunt_trades(cell), COLS)
        print("CELL %s %s: plugin %d | hunt %d | matched %d | max abs net diff $%.2e | net plugin $%.2f vs hunt $%.2f" % (
            cell, kw, rc["plugin"], rc["hunt"], rc["matched"], rc["maxdiff"]["net"], rc["net_plugin"], rc["net_hunt"]))
        ok &= (rc["matched"] == rc["plugin"] == rc["hunt"] and rc["maxdiff"]["net"] < 1e-6)
    # ---- 4. engine on the SPY 5m clock
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
    cdays = pd.Index(sorted(set(int(x) for x in idx.strftime("%Y%m%d"))))
    pdays = pd.Index(p["days"])
    print("CLOCK vs PANEL sessions 2016-01-04 .. 2025-06-30: clock %d, panel %d, clock-only %s, panel-only %s" % (
        len(cdays), len(pdays), [int(x) for x in cdays.difference(pdays)][:10],
        [int(x) for x in pdays.difference(cdays)][:10]))
    res = run_backtest(mod, params={}, arrays=arr, return_trades=True)
    tr = res["trades"]
    nxt_clock = dict(zip(cdays[:-1], cdays[1:]))
    bars_ok = True
    for t in tr:
        e, x = idx[t[0]], idx[t[1]]
        ed, xd = int(e.strftime("%Y%m%d")), int(x.strftime("%Y%m%d"))
        bars_ok &= ((e.hour, e.minute) == (15, 55) and (x.hour, x.minute) == (9, 30) and nxt_clock.get(ed) == xd
                    and xd in H.index)
    eng = pd.Series({int(idx[t[1]].strftime("%Y%m%d")): t[2] for t in tr}).sort_index()
    want = pickle.load(open(HUNT + "series.pkl", "rb"))["83d"]
    want.index = pd.DatetimeIndex(want.index).strftime("%Y%m%d").astype("int64")
    want = want[want.index <= SEAL]
    wnz = want[want != 0]
    e2 = eng[eng.index >= HUNT_FROM]
    j2 = pd.concat([e2.rename("engine"), wnz.rename("hunt")], axis=1)
    b2 = j2.dropna()
    d2 = (b2.engine - b2.hunt).abs()
    full = eng.reindex(want.index).fillna(0.0)
    print("ENGINE (SPY 5m clock, exit-day booking) 2017-04-01 .. 2025-06-30: engine trades %d | hunt nights %d | "
          "matched %d | only engine %d | only hunt %d | max abs diff $%.2e | net engine $%.2f vs hunt $%.2f (%+.6f%%) "
          "| daily corr (zero days incl., %d sessions) %.9f | every trade 15:55 of t -> 09:30 of the next clock "
          "session = the hunt's exit day: %s | engine trades before 2017-04-01: %d" % (
              len(e2), len(wnz), len(b2), int(j2.hunt.isna().sum()), int(j2.engine.isna().sum()),
              d2.max() if len(d2) else float("nan"), e2.sum(), want.sum(), 100.0 * (e2.sum() / want.sum() - 1.0),
              len(want), full.corr(want), bars_ok, int((eng.index < HUNT_FROM).sum())))
    if j2.engine.isna().any():
        print("  hunt-only exits:", [int(x) for x in j2.index[j2.engine.isna().to_numpy()][:12]])
    if j2.hunt.isna().any():
        print("  engine-only exits:", [int(x) for x in j2.index[j2.hunt.isna().to_numpy()][:12]])
    marks = mod.mark_open_trades(tr, arr["open"], arr["high"], arr["low"], arr["close"], volumes=arr.get("volume"),
                                 day_id=arr.get("day_id"), index=arr["index"])
    mk = [abs(mm[0][1] + 0.5 * float(H.loc[int(idx[t[1]].strftime("%Y%m%d")), "c"]))
          if len(mm) == 1 and mm[0][0] == t[0] else float("inf") for mm, t in zip(marks, tr)]
    print("MARKS: %d trades, each one mark at its entry bar = minus half the night's cost: max abs diff vs the hunt's "
          "cost / 2 $%.2e" % (len(marks), max(mk) if mk else float("nan")))
    ok &= (len(b2) == len(wnz) == len(e2) and bool((d2 < 1e-6).all()) and bars_ok and (max(mk) if mk else 1) < 1e-6)
    print("PARITY", "PASS (exact)" if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

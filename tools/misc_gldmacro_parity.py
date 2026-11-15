"""Parity: augur_strategies/MISC_GLDMACRO_1_0.py vs the opus-hunt S97 harness - cell 97a (the defaults), 97c, 97b.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S97, s97_lib.py + s97_eval.py) saved
  trades_97a.csv   one row a release day D: Dm1, ret, px, shares, gross, cost, net, types ($250k a trade),
                   2010-06-17 .. 2025-06-18 (TUNE and EVAL)
  trades_97c.csv   the same trades at double cost
  trades_97b.csv   cell 97b: CPI and payroll days, 09:30 open -> close of the last RTH 5m bar, 2016-07 .. 2025-06
  series.pkl       {'97a', '97b', '97c'} -> net $ a GLD session over EVAL 2016-07-01 .. 2025-06-30, zero days included
Checks, all on sessions <= 2025-06-30 only:
  1. TRADES: the plugin through augur_engine.run_backtest on the GLD 5m RTH alpaca_split_rth master (loaded by the
     engine's own load_master_arrays from the shared checkout's registry, to 2025-06-30) vs every hunt trade whose
     entry session is a master session (D-1 from 2016-01-04 for 97a / 97c; 97b from 2016-07-01): matched on D, the
     same entry day, entry bar = D-1's last 5m bar (the 09:30 bar for 97b), exit bar = D's last 5m bar, shares, gross,
     cost and net; total net plugin vs hunt (pct). The engine's trade list must equal the plugin's own _trades.
  2. SERIES: the engine's trades booked on their exit day, zero-filled over the hunt's EVAL sessions, vs series.pkl:
     max abs diff, daily correlation, totals.
  Cells: 97a = the defaults; 97c = cents_share 1.0 / fee_bps 0.6 (the hunt's double cost); 97b = events CPI+EMP, entry
  release_open. 97b is REPORT ONLY: the hunt rounded the 5m prices to float32 (s97_eval.py) and the plugin reads the
  master's float64 prices, so a gap of cents a trade (or one share at the floor now and then) is that rounding.
THE SEAL: the panel's arrays are cut at 2025-06-30 before the plugin derives anything, and the master is loaded only to
2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_gldmacro_parity.py      (one process, ~250 MB peak: never while the PC is in QUIET)
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
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S97/"
SEAL = 20250630
SEAL_DAY = "2025-06-30"
FIRST_SESSION = "2016-01-04"                    # the GLD 5m master's first session
PANEL_KEYS = ("dates", "close", "raw", "last_min")
CELLS = (("97a", {}, "2016-01-04", True),
         ("97c", {"cents_share": 1.0, "fee_bps": 0.6}, "2016-01-04", True),
         ("97b", {"events": "CPI+EMP", "entry": "release_open"}, "2016-07-01", False))


def fresh_plugin():
    """A fresh copy of the plugin module from this checkout (its own empty cache)."""
    spec = importlib.util.spec_from_file_location("misc_gldmacro_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_GLDMACRO_1_0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CACHE.clear()
    return mod


def sealed_arrays(mod, seal=SEAL):
    """The pinned panel's arrays with every session after `seal` removed (None when the panel is not on this
    machine). Raises when the file on disk is not the pinned build."""
    if not os.path.exists(mod.PANEL_PATH):
        return None
    with open(mod.PANEL_PATH, "rb") as fh:
        if hashlib.sha256(fh.read()).hexdigest() != mod.PANEL_SHA256:
            raise RuntimeError("panel is not the pinned build")
    z = np.load(mod.PANEL_PATH, allow_pickle=False)
    k = np.asarray(z["dates"]).astype("int64") <= int(seal)
    return {key: np.asarray(z[key])[k] for key in PANEL_KEYS}


def load_plugin_sealed(seal=SEAL):
    """Import the plugin from this checkout and give it the panel cut at `seal` (nothing later is derived or used).
    Returns (module, panel) or (module, None) when the pinned panel is not on this machine."""
    mod = fresh_plugin()
    cut = sealed_arrays(mod, seal)
    mod._CACHE["panel"] = None if cut is None else mod._derive(cut)
    return mod, mod._CACHE["panel"]


def defaults(mod, **kw):
    prm = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    prm.update(kw)
    return prm


def engine():
    """augur_engine from the SHARED checkout: its registry (optimizer_history.db) knows the masters."""
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    from augur_engine import data as D
    from augur_engine import run_backtest
    return D, run_backtest


def master_arrays(D, date_from=FIRST_SESSION, date_to=SEAL_DAY):
    """The GLD 5m RTH alpaca_split_rth master's bars, never past the seal. (None, None) when not on this machine."""
    date_to = min(str(date_to), SEAL_DAY)
    m = D.find_master("GLD", "5m", "rth", "alpaca_split_rth")
    if m is None:
        return None, None
    arr = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    assert idx.max() < pd.Timestamp(SEAL_DAY) + pd.Timedelta(days=1)
    return m, arr


def plugin_frame(mod, p, arr, **kw):
    """The plugin's own trades (its _trades) for one config, with the bar clock of each entry / exit."""
    T = pd.DataFrame(mod._trades(p, arr["index"], arr["open"], arr["close"], **defaults(mod, **kw)))
    if not len(T):
        return T
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    T["Dts"] = pd.to_datetime(T.D.astype(str), format="%Y%m%d")
    T["entry_ts"] = idx[T.e.to_numpy()]
    T["exit_ts"] = idx[T.x.to_numpy()]
    row_of = {int(d): i for i, d in enumerate(p["dates"])}
    lm = p["last_min"]
    em = T.entry_ts.dt.hour * 60 + T.entry_ts.dt.minute
    xm = T.exit_ts.dt.hour * 60 + T.exit_ts.dt.minute
    T["bars_ok"] = [(ets.normalize() == pd.Timestamp(str(ed))
                     and (int(a) == (570 if kw.get("entry") == "release_open" else int(lm[row_of[int(ed)]])))
                     and xts.normalize() == pd.Timestamp(str(dd)) and int(b) == int(lm[row_of[int(dd)]]))
                    for ets, xts, ed, dd, a, b in zip(T.entry_ts, T.exit_ts, T.entry_day, T.D, em, xm)]
    return T


def compare_trades(T, H, label, lo, exact):
    """exact: same shares and net to 1e-6. Not exact (97b): shares within one (the float32 floor) and net within $1
    plus that share's move."""
    T = T[(T.Dts >= pd.Timestamp(lo)) & (T.Dts <= pd.Timestamp(SEAL_DAY))].drop(columns=["D"])
    H = H[(H.D >= pd.Timestamp(lo)) & (H.D <= pd.Timestamp(SEAL_DAY))]
    J = T.merge(H, left_on="Dts", right_on="D", how="outer", suffixes=("_p", "_h"), indicator=True)
    both = J[J._merge == "both"]
    same_day = both.entry_day.astype("int64").astype(str) == both.Dm1.dt.strftime("%Y%m%d")
    dsh = (both.shares_p - both.shares_h).abs()
    same_sh = dsh < 1e-9
    dnet = (both.net_p - both.net_h).abs()
    if exact:
        ok_rows = same_day & same_sh & both.bars_ok.astype(bool) & (dnet < 1e-6)
    else:
        allowed = 1.0 + dsh * (both.p_out - both.p_in).abs()
        ok_rows = same_day & (dsh <= 1) & both.bars_ok.astype(bool) & (dnet <= allowed)
    tp, th = float(T.net.sum()), float(H.net.sum())
    print("%s TRADES %s..%s: plugin %d | hunt %d | matched on D %d | only plugin %d | only hunt %d | same entry day %d |"
          " entry / exit on the session's own clock bars %d | same shares %d | max |net diff| $%.2e (gross $%.2e, cost"
          " $%.2e) | net plugin $%.2f vs hunt $%.2f (%+.6f%%)" % (
              label, lo, SEAL_DAY, len(T), len(H), len(both), int((J._merge == "left_only").sum()),
              int((J._merge == "right_only").sum()), int(same_day.sum()), int(both.bars_ok.astype(bool).sum()),
              int(same_sh.sum()), float(dnet.max()) if len(both) else float("nan"),
              float((both.gross_p - both.gross_h).abs().max()) if len(both) else float("nan"),
              float((both.cost_p - both.cost_h).abs().max()) if len(both) else float("nan"), tp, th,
              100.0 * (tp / th - 1.0) if th else float("nan")))
    bad = J[(J._merge != "both") | ~J.index.isin(both.index[ok_rows])]
    if len(bad):
        print("  rows off (first 12):")
        print(bad[["Dts", "D", "_merge", "entry_day", "Dm1", "shares_p", "shares_h", "net_p", "net_h"]]
              .head(12).to_string())
    return len(bad) == 0 and len(both) == len(H) == len(T)


def compare_series(T, want, label, exact):
    """The engine's net booked on each trade's exit day, zero-filled over the hunt's session list. Not exact (97b):
    within $5 a day (one share at the float32 floor on a release-day move, plus cents)."""
    s = pd.Series(0.0, index=pd.DatetimeIndex(want.index))
    g = T.groupby(T.exit_ts.dt.normalize()).net.sum()
    g = g[(g.index >= s.index[0]) & (g.index <= s.index[-1])]
    extra = g.index.difference(s.index)
    s.loc[g.index.intersection(s.index)] = g.loc[g.index.intersection(s.index)].values
    w = pd.Series(np.asarray(want, float), index=s.index)
    d = (s - w).abs()
    corr = float(np.corrcoef(s.values, w.values)[0, 1])
    print("%s SERIES EVAL %s..%s: sessions %d | trade days plugin %d, hunt %d | max abs diff $%.2e | daily corr %.9f |"
          " total plugin $%.2f vs hunt $%.2f" % (label, s.index[0].date(), s.index[-1].date(), len(s),
                                                 int((s != 0).sum()), int((w != 0).sum()), float(d.max()), corr,
                                                 float(s.sum()), float(w.sum())))
    if len(extra):
        print("  trade days outside the hunt's session list:", [str(x.date()) for x in extra[:12]])
    return len(extra) == 0 and bool((d < (1e-6 if exact else 5.0)).all())


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    assert int(p["dates"].max()) <= SEAL
    cwd = os.getcwd()
    os.chdir(SHARED)
    try:
        D, run_backtest = engine()
        m, arr = master_arrays(D)
    finally:
        os.chdir(cwd)
    if arr is None:
        sys.exit("no GLD 5m master on this machine")
    print("GLD 5m master id %s (%s): %d bars %s .. %s; panel sessions %d (cut at %s)" % (
        m["id"], m["filename"], len(arr["close"]), pd.DatetimeIndex(arr["index"])[0].date(),
        pd.DatetimeIndex(arr["index"])[-1].date(), len(p["dates"]), SEAL_DAY))
    cal = set(int(x) for x in p["dates"])
    for t in ("FOMC", "CPI", "EMP"):
        miss = [int(d) for d in mod.EVENT_DAYS[t] if 20160104 <= d <= SEAL and int(d) not in cal]
        print("  %s days 2016-01-04..%s that are not GLD sessions (no trade): %s" % (t, SEAL_DAY, miss))
    series = pickle.load(open(HUNT + "series.pkl", "rb"))
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    ok = {}
    for cell, kw, lo, exact in CELLS:
        T = plugin_frame(mod, p, arr, **kw)
        r = run_backtest(mod, params=dict(kw), arrays=arr, return_trades=True)
        eng = [(int(t[0]), int(t[1]), round(float(t[2]), 9)) for t in (r or {}).get("trades") or []]
        own = [(int(a), int(b), round(float(c), 9)) for a, b, c in sorted(zip(T.e, T.x, T.net), key=lambda z: (z[1], z[0]))]
        same_engine = eng == own
        print("%s ENGINE: run_backtest trades %d == the plugin's own _trades: %s | first entry %s, last exit %s" % (
            cell, len(eng), same_engine, idx[eng[0][0]] if eng else "-", idx[eng[-1][1]] if eng else "-"))
        H = pd.read_csv(HUNT + "trades_%s.csv" % cell, parse_dates=["D", "Dm1"])
        H = H[H.Dm1 >= pd.Timestamp(FIRST_SESSION)]
        a = compare_trades(T, H, cell, lo, exact)
        b = compare_series(T, series[cell], cell, exact)
        ok[cell] = bool(same_engine and a and b)
    print("PARITY 97a %s | 97c %s | 97b (report only; float32 rounding allowed) %s" % tuple(
        ("PASS (exact)" if ok[c] else "GAP (see above)") if c != "97b" else ("PASS" if ok[c] else "GAP (see above)")
        for c in ("97a", "97c", "97b")))
    return 0 if (ok["97a"] and ok["97c"]) else 1


if __name__ == "__main__":
    sys.exit(main())

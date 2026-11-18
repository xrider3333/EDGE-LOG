"""Parity: augur_strategies/MISC_GLDNIGHT_1_0.py vs the opus-hunt harness cell 160a (GLD-NIGHT, official prints).

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/db_masters/r20_run.py + r19_lib.py + r18_lib.py) saved no trade
file for round 20, only its printed lines (r20_160_out.txt). So this tool
  (a) REPLICA: recomputes cell 160a from C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv with the harness's own
      formulas - FRACTIONAL shares: a night into session D = 100000 x (open(D) / close(D-1) - 1), cost = 2 x (0.005 /
      close(D-1) + 0.3e-4) x 100000, weeknights = sessions exactly 1 calendar day apart, WF = exit day D in
      2016-07-01 .. 2025-06-30, July-June folds, max DD = the harness's ddof on the daily net series (peak floored at
      0) - and checks it against every figure the harness printed for 160a (trades, net a year, max DD, folds up, net
      by calendar year to $0.1k), parsed from r20_160_out.txt. The printed precision is the limit of that check;
  (b) ENGINE: runs the plugin through augur_engine.run_backtest on the GLD 5m RTH alpaca_split_rth master (the
      engine's own load_master_arrays from the shared checkout's registry, 2016-06-30 .. 2025-06-30, so the hunt's
      first night 2016-06-30 -> 07-01 has its entry bar) and compares it trade for trade with the replica: same
      nights, entry bar = D-1's last 5m bar, exit bar = D's 09:30 bar, and net(engine) = net(replica) x shares x px /
      100000 exactly - the whole gap is the whole-share floor. Also the same run on bars from 2016-07-01 (what a job
      pinned to the WF window sees: one night fewer).
  Report only: the replica on every night and on weekend nights (official prints; the harness printed those two cells
  on 5m BAR prices, so no reference), and the weeknight replica with the yahoo daily closes swapped in as the entry
  print (the alpaca raw close is off on 2020-03-12 and 2020-03-16).
THE SEAL: the daily file is read only to 2025-06-30, the panel's arrays are cut at 2025-06-30 before the plugin derives
anything, and the master is loaded only to 2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_gldnight_parity.py      (one process, under 200 MB, a few seconds: never while the PC is in QUIET)
Result 2026-11-18 (panel sha 274eff68...): (a) replica 1,767 trades, WF net $65,041.40 ($7,229.57 a year), max DD
$16,765.88, 7 of 9 folds, by-year = the harness print: MATCH on every printed figure. (b) engine 1,767 / 1,767 nights,
WF net $64,978.98 ($7,222.63 a year), max DD $16,755.22, 7 of 9 folds; gap -$62.42 (-0.096 pct) = the whole-share
floor to 1e-12. Bars from 2016-07-01: 1,766 trades (the 2016-06-30 -> 07-01 night has no entry bar).
"""
import csv
import hashlib
import importlib.util
import os
import re
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT_OUT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/db_masters/r20_160_out.txt"
RAW = "C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv"
SIBLING = "C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz"
SEAL = 20250630
SEAL_DAY = "2025-06-30"
W0, W1 = pd.Timestamp("2016-07-01"), pd.Timestamp(SEAL_DAY)
YRS = (W1 - W0).days / 365.25                   # the harness's r18_lib.YRS
FIRST_BARS = "2016-06-30"                       # the entry session of the hunt's first WF night
NU = 100000.0
CELL = "160a official prints"


def fresh_plugin():
    """A fresh copy of the plugin module from this checkout (its own empty cache)."""
    spec = importlib.util.spec_from_file_location("misc_gldnight_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_GLDNIGHT_1_0.py"))
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
    return {key: np.asarray(z[key])[k] for key in mod.PANEL_KEYS}


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


def master_arrays(D, date_from=FIRST_BARS, date_to=SEAL_DAY):
    """The GLD 5m RTH alpaca_split_rth master's bars, never past the seal. (None, None) when not on this machine."""
    date_to = min(str(date_to), SEAL_DAY)
    m = D.find_master("GLD", "5m", "rth", "alpaca_split_rth")
    if m is None:
        return None, None
    arr = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    assert idx.max() < pd.Timestamp(SEAL_DAY) + pd.Timedelta(days=1)
    return m, arr


# ------------------------------------------------------------------------------------------------ (a) the replica
def read_daily_sealed(path=RAW):
    """GLD_1Day_raw.csv to the seal: nothing after 2025-06-30 is parsed."""
    dts, op, cl = [], [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["date"][:10] > SEAL_DAY:
                break
            dts.append(r["date"][:10])
            op.append(float(r["open"]))
            cl.append(float(r["close"]))
    return pd.DataFrame({"open": op, "close": cl}, index=pd.to_datetime(dts))


def replica(r, nights="weeknights", close_override=None):
    """The harness's cell on fractional shares: one row a traded night with exit day D in WF (D, Dm1, gap, px, gross,
    cost, net). r20_run.py: on_off = NU * (r.open / r.close.shift(1) - 1); cost = 2 * (0.005 / prevraw + 0.3e-4) * NU;
    wkn = gap == 1, wke = gap >= 3. close_override (report only) replaces the ENTRY print; cost stays on the raw
    close."""
    prev = r.close.shift(1)
    base = prev if close_override is None else close_override.reindex(r.index).shift(1)
    gap = pd.Series(np.concatenate([[0], np.diff(r.index.values).astype("timedelta64[D]").astype("int64")]),
                    index=r.index)
    T = pd.DataFrame({"D": r.index, "Dm1": pd.Series(r.index, index=r.index).shift(1), "gap": gap, "px": prev,
                      "gross": NU * (r.open / base - 1.0), "cost": 2.0 * (0.005 / prev + 0.3e-4) * NU})
    T["net"] = T.gross - T.cost
    k = {"weeknights": T.gap == 1, "weekend_only": T.gap >= 3, "every_night": T.gap >= 1}[nights]
    T = T[k & T.gross.notna() & (T.D >= W0) & (T.D <= W1)]
    return T.reset_index(drop=True)


def ddof(s):
    """r18_lib.ddof: max drawdown of a daily net series, the peak floored at 0."""
    c = np.asarray(s.cumsum())
    return float((np.maximum(np.maximum.accumulate(c), 0) - c).max())


def stats(D, net, sessions):
    """The harness's judge() reads on a trade list booked on its exit day, zero-filled over the WF sessions."""
    s = pd.Series(0.0, index=sessions)
    s.loc[pd.DatetimeIndex(D)] = np.asarray(net, float)
    fid = (s.index.year - 2016) + (s.index.month >= 7).astype(int) - 1
    fold = s.groupby(fid).sum()
    return {"trades": int(len(D)), "net": float(s.sum()), "net_yr": float(s.sum() / YRS), "dd": ddof(s),
            "folds": [float(v) for v in fold.values], "folds_up": int((fold > 0).sum()),
            "years": {int(k): float(v) for k, v in s.groupby(s.index.year).sum().items()}}


def harness_reference(path=HUNT_OUT, cell=CELL):
    """The figures the harness printed for one cell: trades, net a year, max DD, folds up / folds, by-year $k."""
    if not os.path.exists(path):
        return None
    L = open(path, encoding="utf-8").read().split("\n")
    i = next(k for k, ln in enumerate(L) if ln.startswith("########") and cell in ln)
    a = re.search(r"trades (\d+) \((\d+)/yr\) \| net/yr ([\-\d,]+) .*\| max DD ([\d,]+) .*folds up (\d+) of (\d+)", L[i + 1])
    yrs = {int(y): float(v) for y, v in re.findall(r"(\d{4}) ([+\-][\d.]+)", L[i + 2])}
    n = lambda t: float(t.replace(",", ""))
    return {"line": L[i + 1].strip(), "trades": int(a.group(1)), "net_yr": n(a.group(3)), "dd": n(a.group(4)),
            "folds_up": int(a.group(5)), "n_folds": int(a.group(6)), "years_k": yrs}


def fmt_folds(v):
    return " ".join("%+.0f" % x for x in v)


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    assert int(p["dates"].max()) <= SEAL
    r = read_daily_sealed()
    assert r.index.max() <= W1
    r = r[r.index >= pd.Timestamp("2016-01-01")]
    pdts = pd.to_datetime(pd.Series(p["dates"].astype(str)), format="%Y%m%d")
    assert pd.DatetimeIndex(pdts).equals(r.index), "panel calendar != the daily file's"
    assert np.array_equal(p["open"], r.open.values) and np.array_equal(p["close"], r.close.values)
    sessions = r.index[(r.index >= W0) & (r.index <= W1)]
    print("WF %s .. %s: %d sessions, %.4f years (the harness's YRS). Every figure below is WF only." % (
        W0.date(), W1.date(), len(sessions), YRS))

    # ---- (a) fractional replica vs the harness's printed 160a
    ref = harness_reference()
    R = replica(r)
    sa = stats(R.D, R.net, sessions)
    print("\n(a) REPLICA, fractional shares, weeknights, official prints (the harness's formulas on GLD_1Day_raw.csv)")
    if ref is None:
        print("  harness output %s not on this machine: no reference" % HUNT_OUT)
        ok_a = False
    else:
        print("  HARNESS (r20_160_out.txt): %s" % ref["line"])
        yk = {y: round(v / 1e3, 1) for y, v in sa["years"].items()}
        checks = [("trades", sa["trades"] == ref["trades"]), ("net/yr to the dollar", round(sa["net_yr"]) == ref["net_yr"]),
                  ("max DD to the dollar", round(sa["dd"]) == ref["dd"]),
                  ("folds up", sa["folds_up"] == ref["folds_up"] and len(sa["folds"]) == ref["n_folds"]),
                  ("net by calendar year to $0.1k", all(abs(yk[y] - ref["years_k"][y]) < 0.051 for y in ref["years_k"])
                   and sorted(yk) == sorted(ref["years_k"]))]
        ok_a = all(v for _, v in checks)
        print("  replica vs harness print: " + " | ".join("%s %s" % (k, "MATCH" if v else "DIFFERS") for k, v in checks))
        print("  by calendar year $k: replica %s | harness %s" % (
            " ".join("%d %+.1f" % (y, v) for y, v in yk.items()),
            " ".join("%d %+.1f" % (y, v) for y, v in ref["years_k"].items())))
    print("  replica: trades %d (%.0f/yr) | WF net $%.2f | net/yr $%.2f | max DD $%.2f | gross/trade $%.2f, cost/trade "
          "$%.2f | folds up %d of %d" % (sa["trades"], sa["trades"] / YRS, sa["net"], sa["net_yr"], sa["dd"],
                                         R.gross.mean(), R.cost.mean(), sa["folds_up"], len(sa["folds"])))
    print("  replica July-June fold nets $ (2016-17 .. 2024-25): %s" % fmt_folds(sa["folds"]))

    # ---- (b) the engine file on the 5m master
    cwd = os.getcwd()
    os.chdir(SHARED)
    try:
        D, run_backtest = engine()
        m, arr = master_arrays(D)
    finally:
        os.chdir(cwd)
    if arr is None:
        sys.exit("no GLD 5m master on this machine")
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    print("\n(b) ENGINE, whole shares: GLD 5m master id %s (%s), %d bars %s .. %s; panel sessions %d (cut at %s)" % (
        m["id"], m["filename"], len(idx), idx[0].date(), idx[-1].date(), len(p["dates"]), SEAL_DAY))
    T = pd.DataFrame(mod._trades(p, arr["index"], arr["open"], arr["close"], **defaults(mod)))
    res = run_backtest(mod, params={}, arrays=arr, return_trades=True)
    eng = [(int(t[0]), int(t[1]), round(float(t[2]), 9)) for t in (res or {}).get("trades") or []]
    own = [(int(a), int(b), round(float(c), 9)) for a, b, c in sorted(zip(T.e, T.x, T.net), key=lambda z: (z[1], z[0]))]
    same_engine = eng == own and len(eng) > 0
    T["Dts"] = pd.to_datetime(T.D.astype(str), format="%Y%m%d")
    T["entry_ts"], T["exit_ts"] = idx[T.e.to_numpy()], idx[T.x.to_numpy()]
    row_of = {int(d): i for i, d in enumerate(p["dates"])}
    em = (T.entry_ts.dt.hour * 60 + T.entry_ts.dt.minute).to_numpy()
    xm = (T.exit_ts.dt.hour * 60 + T.exit_ts.dt.minute).to_numpy()
    bars_ok = np.array([ets.normalize() == pd.Timestamp(str(ed)) and int(a) == int(p["last_min"][row_of[int(ed)]])
                        and xts.normalize() == dts and int(b) == 570
                        for ets, xts, ed, dts, a, b in zip(T.entry_ts, T.exit_ts, T.entry_day, T.Dts, em, xm)])
    T = T[(T.Dts >= W0) & (T.Dts <= W1)]
    J = T.merge(R, left_on="Dts", right_on="D", how="outer", suffixes=("_e", "_r"), indicator=True)
    both = J[J._merge == "both"]
    scale = both.shares * both.px_e / NU
    d_px = float((both.px_e - both.px_r).abs().max())
    d_scaled = float((both.net_e - both.net_r * scale).abs().max())
    d_floor = float((both.shares - np.floor(NU / both.px_r)).abs().max())
    se = stats(T.Dts, T.net, sessions)
    gap = se["net"] - sa["net"]
    print("  run_backtest trades %d == the plugin's own _trades: %s | first entry %s, last exit %s | engine metrics: "
          "total_pnl $%.2f, max_drawdown (trade by trade) $%.2f" % (
              len(eng), same_engine, idx[eng[0][0]], idx[eng[-1][1]], res["total_pnl"], -res["max_drawdown"]))
    print("  TRADES WF: engine %d | replica %d | same night %d | only engine %d | only replica %d | entry bar = D-1's "
          "last 5m bar and exit bar = D's 09:30 bar: %d of %d" % (
              len(T), len(R), len(both), int((J._merge == "left_only").sum()), int((J._merge == "right_only").sum()),
              int(bars_ok.sum()), len(bars_ok)))
    print("  per trade: max |px diff| $%.2e | shares == floor(100000 / px): max diff %.0f | max |net(engine) - "
          "net(replica) x shares x px / 100000| $%.2e | shares x px / 100000: min %.6f, mean %.6f, max %.6f" % (
              d_px, d_floor, d_scaled, float(scale.min()), float(scale.mean()), float(scale.max())))
    print("  engine: trades %d (%.0f/yr) | WF net $%.2f | net/yr $%.2f | max DD $%.2f | folds up %d of %d" % (
        se["trades"], se["trades"] / YRS, se["net"], se["net_yr"], se["dd"], se["folds_up"], len(se["folds"])))
    print("  engine July-June fold nets $: %s" % fmt_folds(se["folds"]))
    print("  GAP engine - replica: WF net $%+.2f (%+.4f%%), $%+.2f a year, max DD $%+.2f; sum over trades of "
          "net(replica) x (shares x px / 100000 - 1) = $%+.2f -> the whole-share floor explains $%.2f of it "
          "(unexplained $%.2e)" % (gap, 100.0 * gap / sa["net"], gap / YRS, se["dd"] - sa["dd"],
                                   float((both.net_r * (scale - 1.0)).sum()),
                                   float((both.net_r * (scale - 1.0)).sum()),
                                   abs(gap - float((both.net_r * (scale - 1.0)).sum()))))
    ok_b = bool(same_engine and len(both) == len(T) == len(R) and bars_ok.all() and d_px < 1e-9 and d_floor == 0
                and d_scaled < 1e-6)
    # ---- the same run on bars from the WF window's first day (what a job pinned to the window sees)
    k0 = int(np.searchsorted(idx.values, np.datetime64(W0)))
    T2 = pd.DataFrame(mod._trades(p, arr["index"][k0:], arr["open"][k0:], arr["close"][k0:], **defaults(mod)))
    lost = sorted(set(T.D) - set(T2.D))
    print("  bars from %s (a job pinned to the WF window): trades %d, WF net $%.2f; nights lost at the edge: %s" % (
        W0.date(), len(T2), float(T2.net.sum()), lost))

    # ---- report only
    print("\nREPORT ONLY (fractional replica, official prints, WF; the harness printed these two cells on 5m bar prices)")
    for nm in ("every_night", "weekend_only"):
        Rn = replica(r, nm)
        sn = stats(Rn.D, Rn.net, sessions)
        Tn = pd.DataFrame(mod._trades(p, arr["index"], arr["open"], arr["close"], **defaults(mod, nights=nm)))
        Tn = Tn[(Tn.D >= 20160701) & (Tn.D <= SEAL)]
        print("  %-12s replica trades %d, net/yr $%.0f, max DD $%.0f, folds up %d of %d | engine trades %d, net/yr $%.0f"
              % (nm, sn["trades"], sn["net_yr"], sn["dd"], sn["folds_up"], len(sn["folds"]), len(Tn),
                 float(Tn.net.sum()) / YRS))
    if os.path.exists(SIBLING):
        z = np.load(SIBLING, allow_pickle=False)
        k = np.asarray(z["dates"]).astype("int64") <= SEAL
        y = pd.Series(np.asarray(z["close"], float)[k],
                      index=pd.to_datetime(pd.Series(np.asarray(z["dates"])[k].astype(str)), format="%Y%m%d"))
        Ry = replica(r, close_override=y)
        sy = stats(Ry.D, Ry.net, sessions)
        dd_ = (Ry.set_index("D").net - R.set_index("D").net)
        big = dd_[dd_.abs() > 500]
        print("  weeknights with the yahoo daily close as the entry print: trades %d, WF net $%.2f (%+.2f vs the raw "
              "close), net/yr $%.0f, max DD $%.0f, folds up %d of %d | trades that move by more than $500: %s" % (
                  sy["trades"], sy["net"], sy["net"] - sa["net"], sy["net_yr"], sy["dd"], sy["folds_up"],
                  len(sy["folds"]), "; ".join("%s %+.0f" % (d.date(), v) for d, v in big.items()) or "none"))
    print("\nPARITY (a) replica vs the harness print: %s | (b) engine vs replica, gap = whole shares: %s" % (
        "PASS" if ok_a else "GAP (see above)", "PASS" if ok_b else "GAP (see above)"))
    return 0 if (ok_a and ok_b) else 1


if __name__ == "__main__":
    sys.exit(main())

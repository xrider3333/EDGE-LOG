"""Parity: augur_strategies/MISC_AUCSHORT_1_0.py vs the opus-hunt S135 harness, cell 135a. WALK-FORWARD WINDOW ONLY.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S135, s135_eval.py) saved trades.csv: one row a fund-day
(fund, date, gross, cost, net, ...), $100,000 a trade with FRACTIONAL shares on the entry print, 492 trades
2016-07-12 .. 2025-06-26, net $13,416.52.
  (a) FRACTIONAL REPLICA at $100k: the plugin's own _trades(fractional=True) - the plugin's day selection (frozen
      point-in-time calendar, exchange-calendar skips, full-session rule) and prices, with the harness's sizing - vs
      trades.csv, matched on fund + date: counts, every trade only one side has, max abs difference in gross / cost /
      net, totals. Also: the tighter announcement rule's effect (auction rows the harness rule keeps and this file's
      rule drops), and the job's TLT bars vs the panel's TLT columns on every traded TLT day.
  (b) ENGINE at $100k and at $300k: the file through augur_engine.run_backtest (the engine's normal loader for a
      module + arrays) on the TLT 5m RTH alpaca_split_rth master loaded 2016-07-01 .. 2025-06-30; the engine's trade
      list must equal the plugin's own _trades. Trades, net total and per calendar year, max drawdown (trade sequence),
      per-fold (July - June) nets, and the gap to (a) split into its two causes: the share count is priced on the prior
      raw close instead of the 09:35 print, and it is floored to whole shares.
THE SEAL: the panel's arrays are cut at 2025-06-30 before the plugin derives anything and the master is loaded only to
2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_aucshort_parity.py      (one process, under 300 MB, a few seconds)
Exit code 0 when (a) is exact (every trade matched, net within 1e-6 a trade) and the engine equals the plugin.
"""
import hashlib
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S135/"
SEAL = 20250630
SEAL_DAY = "2025-06-30"
WF_FROM = "2016-07-01"
UNIT = 100000


def fresh_plugin():
    """A fresh copy of the plugin module from this checkout (its own empty cache)."""
    spec = importlib.util.spec_from_file_location("misc_aucshort_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_AUCSHORT_1_0.py"))
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


def engine():
    """augur_engine from the SHARED checkout: its registry (optimizer_history.db) knows the masters."""
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    from augur_engine import data as D
    from augur_engine import run_backtest
    return D, run_backtest


def master_arrays(D, date_from=WF_FROM, date_to=SEAL_DAY):
    """The TLT 5m RTH alpaca_split_rth master's bars, never past the seal. (None, None) when not on this machine."""
    date_to = min(str(date_to), SEAL_DAY)
    m = D.find_master("TLT", "5m", "rth", "alpaca_split_rth")
    if m is None:
        return None, None
    arr = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    assert idx.max() < pd.Timestamp(SEAL_DAY) + pd.Timedelta(days=1)
    return m, arr


def hunt_trades():
    H = pd.read_csv(HUNT + "trades.csv", parse_dates=["date"])
    H = H[H.date <= pd.Timestamp(SEAL_DAY)].copy()
    H["D"] = H.date.dt.strftime("%Y%m%d").astype("int64")
    return H


def frame(rows):
    T = pd.DataFrame(rows)
    if len(T):
        T["date"] = pd.to_datetime(T.D.astype(str), format="%Y%m%d")
    return T


def fold_of(ts):
    """July - June fold label: 2016-07 .. 2017-06 = 'FY17'."""
    return "FY%02d" % ((ts.year + (1 if ts.month >= 7 else 0)) % 100)


def summary(T, col="net"):
    """trades, total, max drawdown of the trade-sequence cumulative, per calendar year, per July - June fold."""
    T = T.sort_values(["date", "fund"])
    v = T[col].to_numpy(float)
    cum = np.cumsum(v)
    return {"n": int(len(T)), "net": float(v.sum()),
            "dd": float((cum - np.maximum.accumulate(cum)).min()) if len(v) else 0.0,
            "year": T.groupby(T.date.dt.year)[col].sum(), "fold": T.groupby(T.date.map(fold_of))[col].sum(),
            "fund": T.groupby("fund").size().to_dict()}


def table(cols):
    """cols: [(label, summary dict)] -> printed table."""
    labs = [c[0] for c in cols]
    w = max(22, max(len(x) for x in labs) + 2)
    line = lambda name, vals: print("%-22s" % name + "".join(("%" + str(w) + "s") % v for v in vals))
    line("", labs)
    line("trades", ["%d" % c[1]["n"] for c in cols])
    line("  IEF / TLT", ["%d / %d" % (c[1]["fund"].get("IEF", 0), c[1]["fund"].get("TLT", 0)) for c in cols])
    line("WF net $", ["%+.2f" % c[1]["net"] for c in cols])
    line("max DD $ (trade seq)", ["%.2f" % c[1]["dd"] for c in cols])
    for y in sorted(set().union(*[set(c[1]["year"].index) for c in cols])):
        line("  %d%s" % (y, " (H2)" if y == 2016 else (" (H1)" if y == 2025 else "")),
             ["%+.2f" % c[1]["year"].get(y, 0.0) for c in cols])
    for f in sorted(set().union(*[set(c[1]["fold"].index) for c in cols])):
        line("  fold %s (Jul-Jun)" % f, ["%+.2f" % c[1]["fold"].get(f, 0.0) for c in cols])


def announcement_effect(mod):
    """Auction rows on WF dates that the harness rule (announcement < auction date) keeps and this file's rule
    (announcement <= the session before) drops - read from the source JSON when it is on this machine. Calendar
    facts only."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import misc_aucshort_panel as B
    if not os.path.exists(B.AUCTIONS):
        print("ANNOUNCEMENT RULE: source JSON not on this machine - not checked")
        return None
    kept, late = B.auction_calendar()
    frozen = sorted(r for f in ("IEF", "TLT") for r in mod.AUCTIONS[f])
    same = [(a, n, f, int(t.split("-")[0])) for a, n, f, t in kept] == frozen
    changed = [r for r in late if r[1] < r[0]]            # kept by '<', dropped by '<= prior session'
    both = [r for r in late if r[1] >= r[0]]              # dropped by both rules
    print("ANNOUNCEMENT RULE: frozen table == the JSON under this file's filter: %s (%d rows) | rows the harness rule "
          "kept and the tighter rule drops: %d %s | rows both rules drop (announcement = auction date): %s" % (
              same, len(frozen), len(changed), changed, both))
    return same and not changed


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
        sys.exit("no TLT 5m master on this machine")
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    print("TLT 5m master id %s (%s): %d bars %s .. %s; panel sessions %d (cut at %s, sha %s...)" % (
        m["id"], m["filename"], len(arr["close"]), idx[0].date(), idx[-1].date(), len(p["dates"]), SEAL_DAY,
        mod.PANEL_SHA256[:8]))
    ann_ok = announcement_effect(mod)

    # ---- calendar accounting on the WF window (no prices) ----
    lo, hi = int(WF_FROM.replace("-", "")), SEAL
    cal = set(int(x) for x in p["dates"])
    row_of = {int(d): i for i, d in enumerate(p["dates"])}
    acc = {"fund-days": 0, "not a session": 0, "rule i (early close)": 0, "rule ii (before a closure)": 0}
    skipped = []
    for f in ("IEF", "TLT"):
        for a in sorted({r[0] for r in mod.AUCTIONS[f] if lo <= r[0] <= hi}):
            acc["fund-days"] += 1
            if a not in cal:
                acc["not a session"] += 1
                continue
            s = int(p["calskip"][row_of[a]])
            if s:
                acc["rule i (early close)" if s == 1 else "rule ii (before a closure)"] += 1
                skipped.append("%s %d (%s)" % (f, a, "i" if s == 1 else "ii"))
    print("CALENDAR %s..%s: %s | dropped: %s" % (WF_FROM, SEAL_DAY, acc, skipped))

    # ---- (a) fractional replica vs trades.csv ----
    H = hunt_trades()
    R = frame(mod._trades(p, arr["index"], arr["open"], notional=UNIT, fractional=True))
    J = R.merge(H, on=["fund", "D"], how="outer", suffixes=("_p", "_h"), indicator=True)
    both = J[J._merge == "both"]
    only_h = J[J._merge == "right_only"]
    only_p = J[J._merge == "left_only"]
    dg, dc, dn = [float((both[c + "_p"] - both[c + "_h"]).abs().max()) for c in ("gross", "cost", "net")]
    print("(a) FRACTIONAL REPLICA $%d vs trades.csv: plugin %d | hunt %d | matched on fund + date %d | only hunt %d | "
          "only plugin %d | max abs diff gross $%.2e, cost $%.2e, net $%.2e | net plugin $%.2f vs hunt $%.2f" % (
              UNIT, len(R), len(H), len(both), len(only_h), len(only_p), dg, dc, dn, float(R.net.sum()),
              float(H.net.sum())))
    for nm, X, c in (("only in trades.csv (dropped by this file)", only_h, "net_h"),
                     ("only in the plugin", only_p, "net_p")):
        for r in X.itertuples():
            print("  %s: %s %d net $%.2f" % (nm, r.fund, r.D, getattr(r, c)))
    ok_a = len(both) == len(H) == len(R) and dn < 1e-6
    # the job's TLT bars vs the panel's TLT columns on the traded TLT days (prices compared, no return formed)
    tl = R[R.fund == "TLT"]
    pin = p["TLT_o935"][tl.row.to_numpy()]
    pout = p["TLT_o1255"][tl.row.to_numpy()]
    same_tlt = bool(np.array_equal(pin, tl.p_in.to_numpy()) and np.array_equal(pout, tl.p_out.to_numpy())
                    and (p["TLT_full"][tl.row.to_numpy()] == 1).all())
    print("    TLT bars == the panel's TLT columns on all %d traded TLT days (09:35 open, 12:55 open, full flag): %s"
          % (len(tl), same_tlt))
    em = idx[R.e.to_numpy()]
    xm = idx[R.x.to_numpy()]
    bars_ok = bool(((em.hour * 60 + em.minute) == 575).all() and ((xm.hour * 60 + xm.minute) == 775).all()
                   and (em.normalize() == R.date.to_numpy()).all() and (xm.normalize() == R.date.to_numpy()).all())
    print("    every entry bar is its day's 09:35 bar and every exit bar its 12:55 bar: %s" % bars_ok)

    # ---- (b) the engine at $100k and $300k ----
    cols = [("trades.csv $100k", summary(H)), ("(a) fractional $100k", summary(R))]
    ok_e = True
    E = {}
    for N in (UNIT, 3 * UNIT):
        T = frame(mod._trades(p, arr["index"], arr["open"], notional=N))
        r = run_backtest(mod, params={"notional": N}, arrays=arr, return_trades=True)
        eng = [(int(t[0]), int(t[1]), round(float(t[2]), 9), int(t[3])) for t in (r or {}).get("trades") or []]
        own = [(int(a), int(b), round(float(c), 9), -1) for a, b, c in
               sorted(zip(T.e, T.x, T.net), key=lambda z: (z[1], z[0]))]
        same = eng == own
        ok_e = ok_e and same and len(T) == len(R)
        s = summary(T)
        print("(b) ENGINE $%d: run_backtest trades %d == the plugin's own _trades: %s | total_pnl $%.2f, max_drawdown "
              "$%.2f, win rate %.1f, PF %.3f | first entry %s, last exit %s" % (
                  N, len(eng), same, r["total_pnl"], r["max_drawdown"], r["win_rate"], r["profit_factor"],
                  idx[eng[0][0]], idx[eng[-1][1]]))
        cols.append(("engine $%dk" % (N // 1000), s))
        E[N] = T
    print()
    table(cols)

    # ---- the gap (a) -> engine at $100k, split by cause ----
    T = E[UNIT].merge(R[["fund", "D", "gross", "cost", "net"]], on=["fund", "D"], suffixes=("", "_frac"))
    move = T.p_in - T.p_out                                         # dollars a share to the short, WF only
    g_px = (UNIT / T.px) * move                                     # fractional shares on the prior raw close
    print("\nGAP (a) -> engine at $%d, %d trades:" % (UNIT, len(T)))
    print("  gross: fractional on the 09:35 print $%.2f -> fractional on the prior raw close $%.2f (sizing price: "
          "%+.2f) -> whole shares $%.2f (floor: %+.2f)" % (
              T.gross_frac.sum(), g_px.sum(), g_px.sum() - T.gross_frac.sum(), T.gross.sum(),
              T.gross.sum() - g_px.sum()))
    print("  cost: $%.2f -> $%.2f (%+.2f: the floor only; both price the cost on the prior raw close)" % (
        T.cost_frac.sum(), T.cost.sum(), T.cost.sum() - T.cost_frac.sum()))
    print("  net: $%.2f -> $%.2f (%+.2f, %+.3f pct)" % (T.net_frac.sum(), T.net.sum(), T.net.sum() - T.net_frac.sum(),
                                                         100.0 * (T.net.sum() / T.net_frac.sum() - 1.0)))
    expo = T.shares * T.p_in / UNIT
    print("  dollars short at 09:35 / N: mean %.5f, min %.5f, max %.5f | shares lost at the floor: mean %.3f | max abs "
          "net diff a trade $%.2f" % (expo.mean(), expo.min(), expo.max(), (UNIT / T.px - T.shares).mean(),
                                      (T.net - T.net_frac).abs().max()))
    n3, n1 = float(E[3 * UNIT].net.sum()), float(E[UNIT].net.sum())
    print("  engine $300k vs 3 x engine $100k: $%.2f vs $%.2f (%+.2f: the floor loses under one share per trade at "
          "either size)" % (n3, 3 * n1, n3 - 3 * n1))
    print("\nPARITY (a) fractional replica vs trades.csv: %s | engine == plugin: %s | TLT bars == panel: %s | "
          "announcement rule changes no trade: %s" % ("PASS (exact)" if ok_a else "GAP (see above)", ok_e, same_tlt,
                                                      ann_ok))
    return 0 if (ok_a and ok_e and same_tlt and bars_ok) else 1


if __name__ == "__main__":
    sys.exit(main())

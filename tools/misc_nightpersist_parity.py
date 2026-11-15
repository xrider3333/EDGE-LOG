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
THE CORPORATE-ACTION NIGHT GUARD (plugin, not in the harness) voids a picked name-night whose raw / split close ratio
moves > 0.5 pct from t to t+1: no PnL, no cost, slot not refilled. Every voided name-night is listed with the dollars
the hunt booked for it; the plugin's nights may differ from the hunt ONLY on the exit days of voided name-nights, and
with those dollars put back every night (and the engine series and the marks) must match the hunt exactly.
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


def voided_name_nights(mod, p, kn):
    """Every name-night the corporate-action guard voids at knobs `kn` (picked, t's close prints present, the raw /
    split close ratio moves more than mod._CA_MOVE from t to t+1), traded legs only, each with the dollars the hunt
    booked for it: side x notional / k x the night's split return (0 for a missing exit open) less the name's cost
    (the plugin's own cost formula). One row a name-night: entry, exit, name, side, gross, cost, net, miss."""
    L, S, _ = mod._picks(p, kn["lookback"], kn["k"], kn["min_price"], kn["beta_resid"], kn["tug"], kn["min_names"])
    brk = (p["ca_break"] & p["closed"]).to_numpy()
    nn = float(kn["notional"]) / int(kn["k"])
    cents = 2.0 * float(kn["spread_cents"]) / 100.0
    fee = round(2.0 * float(kn["fee_bps"]) * 1e-4, 12)
    hold, raw = p["hold"].to_numpy(), p["R"].to_numpy()
    legs = int(kn["legs"])
    rows = []
    for sign, side, M in ((1.0, "long", L), (-1.0, "short", S)):
        if (legs == 1 and sign < 0) or (legs == 2 and sign > 0):
            continue
        for i, j in np.argwhere(M.to_numpy(dtype=bool) & brk):
            h = hold[i, j]
            g = sign * nn * (0.0 if np.isnan(h) else h)
            c = nn * (cents / raw[i, j] + fee)
            rows.append({"entry": int(p["days"][i]), "exit": int(p["nxt"][i]), "name": p["names"][j], "side": side,
                         "gross": g, "cost": c, "net": g - c, "miss": int(np.isnan(h))})
    cols = ["entry", "exit", "name", "side", "gross", "cost", "net", "miss"]
    return pd.DataFrame(rows, columns=cols).sort_values(["entry", "side", "name"]).reset_index(drop=True)


def with_voids_added_back(got, V):
    """The plugin's nights (by exit day) with the voided name-nights' hunt dollars put back = the hunt's book."""
    out = got.copy()
    if V.empty:
        return out
    lg = V["side"] == "long"
    add = pd.DataFrame({"exit": V["exit"], "gl": V["gross"].where(lg, 0.0), "gs": V["gross"].where(~lg, 0.0),
                        "cl": V["cost"].where(lg, 0.0), "cs": V["cost"].where(~lg, 0.0), "g": V["gross"],
                        "c": V["cost"], "net": V["net"], "miss": V["miss"]}).groupby("exit").sum()
    add = add.reindex(out.index).fillna(0.0)
    for col in add.columns:
        out[col] = out[col] + add[col]
    return out


def differing_days(got, H, cols=COLS, tol=1e-6):
    """Exit days on which the plugin's night and the hunt's differ (either missing, or any column off by > tol)."""
    j = got[cols].join(H[cols], rsuffix="_h", how="outer")
    bad = j["net"].isna() | j["net_h"].isna()
    for col in cols:
        bad |= (j[col] - j[col + "_h"]).abs() > tol
    return {int(x) for x in j.index[bad.to_numpy()]}


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
    # ---- 2. nights vs trades_83d.csv: as booked (guard on), and with the voided name-nights put back
    got = plugin_nights(mod, p)
    H = hunt_trades("83d")
    V = voided_name_nights(mod, p, kn)
    off = sorted({int(d) for d in V["entry"]} - {int(d) for d in got["entry"]})
    gap = differing_days(got, H)
    vdays = {int(d) for d in V["exit"]}
    print("VOIDED name-nights, cell 83d, by the corporate-action guard (all <= 2025-06-30): %d on %d nights | "
          "the hunt's $ for each (side x $10k x the split night return, less the name's cost):" % (len(V), len(vdays)))
    for v in V.itertuples():
        print("  entry %d -> exit %d  %-6s %-5s  gross $%+10.2f  cost $%7.2f  net $%+10.2f%s" % (
            v.entry, v.exit, v.name, v.side, v.gross, v.cost, v.net, "  (exit open missing)" if v.miss else ""))
    print("  TOTAL voided: gross $%+.2f, cost $%.2f, net $%+.2f (the hunt booked this; the plugin books $0)" % (
        V["gross"].sum(), V["cost"].sum(), V["net"].sum()))
    if off:
        print("  voided name-nights on nights the plugin does not trade (a void emptied a side):", off[:12])
    print("NIGHTS 83d AS BOOKED (guard on): plugin %d nights, net $%.2f | hunt %d nights, net $%.2f | differ on %d "
          "exit days, every one an exit of a voided name-night: %s" % (
              len(got), got["net"].sum(), len(H), H["net"].sum(), len(gap), gap <= vdays))
    if not gap <= vdays:
        print("  differing exits with NO void:", sorted(gap - vdays)[:12])
    r = compare_nights(with_voids_added_back(got, V), H, COLS)
    print("NIGHTS 83d + VOIDS PUT BACK (by exit day, all <= 2025-06-30): plugin %d | hunt %d | matched %d | only "
          "plugin %d | only hunt %d | net plugin $%.2f vs hunt $%.2f (%+.6f%%) | corr %.9f" % (
              r["plugin"], r["hunt"], r["matched"], r["only_plugin"], r["only_hunt"], r["net_plugin"], r["net_hunt"],
              100.0 * (r["net_plugin"] / r["net_hunt"] - 1.0), r["corr"]))
    print("  max abs diff by column:", {c: "%.2e" % v for c, v in r["maxdiff"].items()})
    print("  first / last exit: plugin %s .. %s | hunt %s .. %s | missing exit opens booked 0: plugin %d, hunt %d" % (
        got.index.min(), got.index.max(), H.index.min(), H.index.max(),
        int(got["miss"].sum() + V["miss"].sum()), int(H["miss"].sum())))
    if r["only_hunt"] or r["only_plugin"]:
        print("  hunt-only exits:", r["hunt_only_days"], "| plugin-only exits:", r["plugin_only_days"])
    ok &= (not off and gap <= vdays and r["matched"] == r["plugin"] == r["hunt"]
           and all(v < 1e-6 for v in r["maxdiff"].values()))
    # ---- 3. the other cells through the switches (voids put back the same way)
    for cell, kw in CELLS.items():
        g3, H3 = plugin_nights(mod, p, **kw), hunt_trades(cell)
        V3 = voided_name_nights(mod, p, defaults(mod, **kw))
        gap3, vdays3 = differing_days(g3, H3), {int(d) for d in V3["exit"]}
        rc = compare_nights(with_voids_added_back(g3, V3), H3, COLS)
        print("CELL %s %s: voided %d name-nights (hunt net $%+.2f) | as booked differs on %d exit days, all void "
              "exits: %s | voids put back: plugin %d | hunt %d | matched %d | max abs net diff $%.2e | net plugin "
              "$%.2f vs hunt $%.2f" % (cell, kw, len(V3), V3["net"].sum(), len(gap3), gap3 <= vdays3, rc["plugin"],
                              rc["hunt"], rc["matched"], rc["maxdiff"]["net"], rc["net_plugin"], rc["net_hunt"]))
        if len(V3):
            print("  voided:", ["%d %s %s $%+.2f" % (v.entry, v.name, v.side, v.net) for v in V3.itertuples()])
        ok &= (gap3 <= vdays3 and rc["matched"] == rc["plugin"] == rc["hunt"] and rc["maxdiff"]["net"] < 1e-6)
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
    vnet = V.groupby("exit")["net"].sum() if len(V) else pd.Series(dtype=float)
    vcost = V.groupby("exit")["cost"].sum() if len(V) else pd.Series(dtype=float)
    raw2 = pd.concat([e2.rename("engine"), wnz.rename("hunt")], axis=1)
    gap2 = {int(x) for x in raw2.index[(raw2.engine.isna() | raw2.hunt.isna()
                                        | ((raw2.engine - raw2.hunt).abs() > 1e-6)).to_numpy()]}
    e2a = e2 + vnet.reindex(e2.index).fillna(0.0)          # the voided name-nights' hunt dollars put back
    j2 = pd.concat([e2a.rename("engine"), wnz.rename("hunt")], axis=1)
    b2 = j2.dropna()
    d2 = (b2.engine - b2.hunt).abs()
    full = (eng + vnet.reindex(eng.index).fillna(0.0)).reindex(want.index).fillna(0.0)
    print("ENGINE AS BOOKED (guard on) 2017-04-01 .. 2025-06-30: net engine $%.2f vs hunt $%.2f | differs on %d exit "
          "days, every one an exit of a voided name-night: %s" % (e2.sum(), want.sum(), len(gap2), gap2 <= vdays))
    print("ENGINE + VOIDS PUT BACK (SPY 5m clock, exit-day booking) 2017-04-01 .. 2025-06-30: engine trades %d | hunt "
          "nights %d | matched %d | only engine %d | only hunt %d | max abs diff $%.2e | net engine $%.2f vs hunt "
          "$%.2f (%+.6f%%) | daily corr (zero days incl., %d sessions) %.9f | every trade 15:55 of t -> 09:30 of the "
          "next clock session = the hunt's exit day: %s | engine trades before 2017-04-01: %d" % (
              len(e2), len(wnz), len(b2), int(j2.hunt.isna().sum()), int(j2.engine.isna().sum()),
              d2.max() if len(d2) else float("nan"), e2a.sum(), want.sum(), 100.0 * (e2a.sum() / want.sum() - 1.0),
              len(want), full.corr(want), bars_ok, int((eng.index < HUNT_FROM).sum())))
    if j2.engine.isna().any():
        print("  hunt-only exits:", [int(x) for x in j2.index[j2.engine.isna().to_numpy()][:12]])
    if j2.hunt.isna().any():
        print("  engine-only exits:", [int(x) for x in j2.index[j2.hunt.isna().to_numpy()][:12]])
    marks = mod.mark_open_trades(tr, arr["open"], arr["high"], arr["low"], arr["close"], volumes=arr.get("volume"),
                                 day_id=arr.get("day_id"), index=arr["index"])
    mk = []
    for mm, t in zip(marks, tr):
        xd = int(idx[t[1]].strftime("%Y%m%d"))
        want_cost = float(H.loc[xd, "c"]) - float(vcost.get(xd, 0.0))   # the hunt's cost less the voided names'
        mk.append(abs(mm[0][1] + 0.5 * want_cost) if len(mm) == 1 and mm[0][0] == t[0] else float("inf"))
    print("MARKS: %d trades, each one mark at its entry bar = minus half the night's cost (the voided names' cost "
          "out): max abs diff vs the hunt's cost / 2 $%.2e" % (len(marks), max(mk) if mk else float("nan")))
    ok &= (gap2 <= vdays and len(b2) == len(wnz) == len(e2) and bool((d2 < 1e-6).all()) and bars_ok
           and (max(mk) if mk else 1) < 1e-6)
    print("PARITY", ("PASS (exact; the %d voided name-nights put back)" % len(V)) if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Parity: augur_strategies/MISC_EXPCAL_1_0.py vs the opus-hunt harness cell 58c (expiry-calendar long, NQ).

Reference: C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S58/trades_58c.csv (s58_run.py, build(excl_fomc=True,
kind='union') on the NQ 5m RTH db_adj_rth master, 2010-06-07 .. 2025-06-30) and the allocator's daily series
C:/EdgeLog/_anatomy_cache/bookq/allocator_legs/OPUS_58c.csv (2016-07-01 .. 2025-06-30).
What runs: the plugin is loaded with the engine's own loader (augur_engine.load_strategy - the plugin gate runs) and
run with the engine's own augur_engine.run_backtest (roll guard and all) on the engine's own load_master_arrays, on
BOTH masters: db_adj_rth (the harness's) and db_noadj_rth (the job's). Trade for trade: same dates, same type
(F = 09:30 entry, P = 14:00 entry), per-trade net dollars. Also the run a job pinned to 2016-07-01 sees.
THE SEAL: every load stops at 2025-06-30 (asserted); no P&L after it is computed or printed.
Run from the shared checkout (its registry knows the masters):
    cd C:/Users/xride/OneDrive/Desktop/EDGE-LOG && python <worktree>/tools/misc_expcal_parity.py [--out PARITY_RAW.txt]
One process, about 300 MB, under a minute.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"

import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402

PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_EXPCAL_1_0.py")
TRADES = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S58/trades_58c.csv"
DAILY = "C:/EdgeLog/_anatomy_cache/bookq/allocator_legs/OPUS_58c.csv"
SEAL_DAY = "2025-06-30"
START = "2010-06-07"
WF0 = "2016-07-01"
SOURCES = ("db_adj_rth", "db_noadj_rth")


def engine():
    """augur_engine from the SHARED checkout: only its registry (optimizer_history.db) knows the masters (a worktree's
    find_master returns None). The PLUGIN is always this checkout's file, loaded by absolute path."""
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    import augur_engine as ae
    from augur_engine import data as D
    return ae, D


def load_arrays(D, source, date_from=START, date_to=SEAL_DAY):
    date_to = min(str(date_to), SEAL_DAY)
    m = D.find_master("NQ", "5m", "rth", source)
    if m is None:
        return None, None
    arr = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
    loc = et_index(arr)
    assert loc.max() < pd.Timestamp(SEAL_DAY) + pd.Timedelta(days=1), "bars past the seal"
    return m, arr


def et_index(arr):
    idx = pd.DatetimeIndex(arr["index"])
    return idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx


def engine_trades(ae, mod, arr):
    """The engine-path trade list as a frame: one row a trade (d, e, x, usd, p_in, p_out, typ)."""
    res = ae.run_backtest(mod, params={}, arrays=arr, return_trades=True)
    loc = et_index(arr)
    rows = []
    for t in (res or {}).get("trades") or []:
        e, x = int(t[0]), int(t[1])
        assert loc[e].normalize() == loc[x].normalize() and loc[x].hour * 60 + loc[x].minute == 955
        em = loc[e].hour * 60 + loc[e].minute
        rows.append((loc[x].normalize(), e, x, float(t[2]), float(t[4]), float(t[5]), {570: "F", 840: "P"}[em],
                     int(t[3])))
    T = pd.DataFrame(rows, columns=["d", "e", "x", "usd", "p_in", "p_out", "typ", "side"])
    return res, T


def compare(T, ref):
    """(same dates, same types, max abs per-trade $ difference, n engine, n ref)."""
    a = T.set_index("d")
    b = ref.set_index("d")
    same_dates = bool(len(a) == len(b) and (a.index == b.index).all())
    if not same_dates:
        only_e = sorted(set(a.index) - set(b.index))
        only_r = sorted(set(b.index) - set(a.index))
        return False, False, float("nan"), len(a), len(b), only_e, only_r
    same_typ = bool((a.typ.values == b.typ.values).all())
    dmax = float(np.max(np.abs(a.usd.values - b.usd.values))) if len(a) else 0.0
    return True, same_typ, dmax, len(a), len(b), [], []


def main(out=None):
    lines = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        lines.append(s)

    ae, D = engine()
    mod = ae.load_strategy(PLUGIN)                      # the engine's loader: the plugin gate runs here
    P("plugin", mod.__file__)
    P("engine", os.path.dirname(ae.__file__), "| cwd", os.getcwd())
    ref = pd.read_csv(TRADES, parse_dates=["d"], float_precision="round_trip")   # default parser: 1 ulp off
    assert ref.d.max() <= pd.Timestamp(SEAL_DAY)
    refwf = ref[ref.d >= WF0]
    P("reference trades_58c.csv: %d trades %s .. %s, net $%.2f | WF %s..%s: %d trades, net $%.2f"
      % (len(ref), ref.d.min().date(), ref.d.max().date(), ref.usd.sum(), WF0, SEAL_DAY, len(refwf), refwf.usd.sum()))
    keep = {}
    for src in SOURCES:
        m, arr = load_arrays(D, src)
        if arr is None:
            P(src, "master not on this machine")
            continue
        P("\n== %s (master id %s, %s) bars %d, %s .. %s" % (src, m.get("id"), m.get("filename"), len(arr["close"]),
                                                          et_index(arr)[0], et_index(arr)[-1]))
        res, T = engine_trades(ae, mod, arr)
        rs = ((res or {}).get("_meta") or {}).get("roll_stamp") or {}
        P("  roll stamp: master_type=%s signal_method=%s (%s) trades_crossing=%s guard=%s warning=%s"
          % (rs.get("master_type"), rs.get("signal_method"), rs.get("method_source"), rs.get("trades_crossing"),
             rs.get("guard"), rs.get("warning")))
        own = mod._trades(arr["index"], arr["open"])
        P("  engine trades %d == plugin's own _trades %d: %s; all side +1: %s"
          % (len(T), len(own), len(T) == len(own) and all(a == b["net"] for a, b in zip(T.usd, own)),
             bool((T.side == 1).all())))
        ok, okt, dmax, n1, n2, oe, orr = compare(T, ref)
        P("  FULL %s..%s: engine %d vs harness %d | same dates %s | same F/P type %s | max abs per-trade diff $%.3e"
          % (START, SEAL_DAY, n1, n2, ok, okt, dmax))
        if not ok:
            P("    only engine:", [str(d.date()) for d in oe][:40])
            P("    only harness:", [str(d.date()) for d in orr][:40])
        P("  FULL net engine $%.2f vs harness $%.2f" % (T.usd.sum(), ref.usd.sum()))
        W = T[T.d >= WF0]
        ok, okt, dmax, n1, n2, oe, orr = compare(W, refwf)
        P("  WF   %s..%s: engine %d vs harness %d | same dates %s | same type %s | max abs diff $%.3e | net engine "
          "$%.2f vs harness $%.2f" % (WF0, SEAL_DAY, n1, n2, ok, okt, dmax, W.usd.sum(), refwf.usd.sum()))
        # the run a job pinned to the WF start sees
        m2, arr2 = load_arrays(D, src, date_from=WF0)
        res2, T2 = engine_trades(ae, mod, arr2)
        ok, okt, dmax, n1, n2, _, _ = compare(T2, refwf)
        P("  JOB-WINDOW bars from %s: engine %d vs harness %d | same dates %s | max abs diff $%.3e | net $%.2f | "
          "engine metrics num_trades %s total_pnl %.2f"
          % (WF0, n1, n2, ok, dmax, T2.usd.sum(), res2.get("num_trades"), res2.get("total_pnl")))
        # the allocator's daily series
        dl = pd.read_csv(DAILY, parse_dates=["date"], float_precision="round_trip").set_index("date")
        assert dl.index.max() <= pd.Timestamp(SEAL_DAY)
        sess = pd.DatetimeIndex(sorted(set(et_index(arr2).normalize())))
        mine = pd.Series(0.0, index=sess)
        mine.loc[pd.DatetimeIndex(T2.d)] = T2.usd.values
        cnt = pd.Series(0, index=sess)
        cnt.loc[pd.DatetimeIndex(T2.d)] = 1
        same_idx = bool(len(sess) == len(dl) and (sess == dl.index).all())
        P("  DAILY vs OPUS_58c.csv: rows engine %d vs file %d, same dates %s" % (len(sess), len(dl), same_idx))
        if same_idx:
            P("    max abs daily diff $%.3e | trade-count column equal %s | sum engine $%.2f file $%.2f"
              % (float(np.max(np.abs(mine.values - dl.pnl.values))), bool((cnt.values == dl.trades.values).all()),
                 mine.sum(), dl.pnl.sum()))
        else:
            P("    only engine:", [str(d.date()) for d in sess.difference(dl.index)][:20],
              "only file:", [str(d.date()) for d in dl.index.difference(sess)][:20])
        keep[src] = (arr, T)
        del arr2
    if len(keep) == 2:
        (aa, Ta), (an, Tn) = keep["db_adj_rth"], keep["db_noadj_rth"]
        P("\n== adj vs noadj")
        la, ln = et_index(aa), et_index(an)
        P("  bar clocks identical: %s (adj %d bars, noadj %d bars)" % (bool(len(la) == len(ln) and (la == ln).all()),
                                                                     len(la), len(ln)))
        same = bool(len(Ta) == len(Tn) and (Ta.d.values == Tn.d.values).all())
        P("  same trade dates: %s (%d vs %d)" % (same, len(Ta), len(Tn)))
        if same:
            df = Tn.usd.values - Ta.usd.values
            P("  per-trade $ noadj - adj: max abs %.3e, trades not bit-equal: %d, sum of differences $%.6f"
              % (float(np.max(np.abs(df))), int((df != 0).sum()), float(df.sum())))
            oa, on = np.asarray(aa["open"], float), np.asarray(an["open"], float)
            off_in = on[Tn.e.values] - oa[Ta.e.values]
            off_out = on[Tn.x.values] - oa[Ta.x.values]
            P("  MASTER opens, back-adjust offset (noadj - adj) at the entry bars: min %.4f max %.4f | offset at the exit "
              "bar - offset at the entry bar: max abs %.3e (0 = the adjust is one constant inside every traded session)"
              % (off_in.min(), off_in.max(), float(np.max(np.abs(off_out - off_in)))))
            allo = on - oa
            la_d = la.normalize()
            chg = np.flatnonzero((np.diff(allo) != 0) & (la_d[1:] == la_d[:-1]))
            P("  bars where the offset changes INSIDE a session (whole master to the seal): %d" % len(chg))
            P("  ENGINE TUPLE prices on noadj: entry (field 4) - raw open: max abs %.3e | exit (field 5) - raw open: min "
              "%.2f max %.2f  <- the engine's difference re-price maps the ENTRY back to raw and leaves the EXIT on the "
              "adjusted series (augur_engine/rolls.py reprice_result); dollars (field 2) are unaffected"
              % (float(np.max(np.abs(Tn.p_in.values - on[Tn.e.values]))), float((Tn.p_out.values - on[Tn.x.values]).min()),
                 float((Tn.p_out.values - on[Tn.x.values]).max())))
            P("  dtypes: adj open %s, noadj open %s" % (aa["open"].dtype, an["open"].dtype))
            for i in np.flatnonzero(df != 0)[:40]:
                P("     %s %s adj $%r | noadj $%r" % (Ta.d[i].date(), Ta.typ[i], Ta.usd[i], Tn.usd[i]))
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    o = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    main(o)

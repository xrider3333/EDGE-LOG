"""Build / check the pinned NQ panel of augur_strategies/MISC_ESALONE_1_0.py, and run its parity with hunt cell 73d.

    python tools/esalone_nq_panel.py build     # walk NQ 1m ETH db_adj_eth with ENGUQ_1M_ETH_R2_1_0.py at its defaults,
                                               # 2010-06-07 .. bars starting before 2026-06-30 17:00 ET, and write the
                                               # trade intervals into the plugin's NQ PANEL block (in place)
    python tools/esalone_nq_panel.py parity    # ES 1m ETH db_adj_eth 2010-06-07 .. 2025-06-30 17:00 ET (the hunt cut):
                                               # the plugin at nq_gate 0 / 1 / 2 vs hunt trades 73d / 73a / 73b, and the
                                               # panel's NQ flag vs the hunt's nqflag_eval.npy

RULES (owner GO 11-14): data on disk only, no downloads; nothing after 2025-06-30 is scored or printed. `build`
walks NQ through 2026-06-30 only to record WHEN the NQ leg held a position (state, not returns): it prints the
pre-2025-07 checks and the panel size, never a PnL, count or statistic of the later bars.
"""
import gc
import importlib.util
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
SHARED = r"C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
HUNT = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S73/"
PLUGIN = os.path.join(HERE, "augur_strategies", "MISC_ESALONE_1_0.py")
TZ = "America/New_York"
PANEL_CUT = pd.Timestamp("2026-06-30 17:00", tz=TZ)
HUNT_CUT = pd.Timestamp("2025-06-30 17:00", tz=TZ)


def rss():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2 ** 30
    except Exception:
        return float("nan")


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load(inst, date_to, cut):
    """Master arrays from the registry (the shared checkout holds it), bars with start < cut."""
    D = _shared_data()
    m = D.find_master(inst, "1m", "eth", "db_adj_eth")
    a = D.load_master_arrays(m, date_from="2010-06-07", date_to=date_to)
    idx = pd.DatetimeIndex(a["index"])
    idx = idx.tz_localize(TZ) if idx.tz is None else idx.tz_convert(TZ)
    k = np.asarray(idx < cut)
    out = {f: np.asarray(a[f], float)[k] for f in ("open", "high", "low", "close", "volume")}
    out["index"] = idx[k]
    out["meta"] = a.get("meta")
    del a
    gc.collect()
    return out, m


def _shared_data():
    """augur_engine.data pointed (read-only) at the shared checkout's master registry and uploads: a worktree has
    neither, and the registry must never be copied or touched (see the house rule on the shared registry)."""
    from augur_engine import data as D
    D.UPLOADS = os.path.join(SHARED, "augur_uploads")
    D.DB_PATH = os.path.join(SHARED, "optimizer_history.db")
    return D


def _b36(v):
    v = int(v)
    if v < 0:
        raise ValueError(v)
    s = ""
    while True:
        v, r = divmod(v, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
        if v == 0:
            return s


def build():
    r2 = _mod(os.path.join(HERE, "augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py"), "R2")
    prm = {k: v["default"] for k, v in r2.DEFAULT_PARAMS.items()}
    d, m = _load("NQ", "2026-06-30", PANEL_CUT)
    print("NQ master %s (built %s); bars %d  %s .. (panel cut %s)  rss %.2f GB"
          % (m.get("filename"), str(m.get("provenance", ""))[:80], len(d["close"]), d["index"][0], PANEL_CUT, rss()))
    r = r2.run_backtest(d["open"], d["high"], d["low"], d["close"], d["volume"], return_trades=True, **prm)
    E = np.array([q[0] for q in r["trades"]], np.int64); X = np.array([q[1] for q in r["trades"]], np.int64)
    del r
    t_min = d["index"].tz_convert("UTC").tz_localize(None).asi8 // 60_000_000_000
    n = len(t_min)
    end_min = int(PANEL_CUT.tz_convert("UTC").tz_localize(None).value // 60_000_000_000)
    st = t_min[E]
    en = np.where(X + 1 < n, t_min[np.minimum(X + 1, n - 1)], end_min)
    assert np.all(en > st) and np.all(st[1:] >= en[:-1]), "intervals overlap"
    # check against the hunt's own NQ flag on the hunt window (bars starting before 2025-06-30 17:00 ET)
    hk = np.asarray(d["index"] < HUNT_CUT)
    fl = np.zeros(n + 1, np.int32)
    np.add.at(fl, E, 1); np.add.at(fl, X + 1, -1)
    mine = (np.cumsum(fl)[:-1] > 0).astype(np.int8)[hk]
    hunt = np.load(HUNT + "nqflag_eval.npy")
    pre = st < int(HUNT_CUT.tz_convert("UTC").tz_localize(None).value // 60_000_000_000)
    if len(hunt) == len(mine):
        diff = np.flatnonzero(hunt != mine)
        print("NQ flag vs hunt nqflag_eval.npy (hunt window, %d bars): %d bars differ%s"
              % (len(mine), len(diff), "" if not len(diff) else " (first %s, last %s)"
                 % (d["index"][hk][diff[0]], d["index"][hk][diff[-1]])))
    else:
        print("NQ flag vs hunt: bar counts differ (%d here vs %d hunt) - master changed; compare skipped"
              % (len(mine), len(hunt)))
    print("NQ trades entered before the hunt cut: %d (hunt EVAL walk: see nqflag_eval)" % int(pre.sum()))
    toks = []
    prev = 0
    for a_, b_ in zip(st, en):
        toks.append(_b36(int(a_) - prev)); toks.append(_b36(int(b_) - int(a_))); prev = int(b_)
    lines, cur = [], ""
    for tkn in toks:
        if len(cur) + len(tkn) + 1 > 104:
            lines.append(cur); cur = ""
        cur += tkn + " "
    if cur:
        lines.append(cur)
    body = "_NQ_HEAD = (%d, %d, %d)\n_NQ_PANEL = (\n%s)\n" % (
        int(t_min[0]), end_min, len(st), "".join('    "%s"\n' % s for s in lines))
    src = open(PLUGIN, encoding="utf-8").read()
    new = re.sub(r"(# BEGIN NQ PANEL\n).*?(# END NQ PANEL)", lambda mm: mm.group(1) + body + mm.group(2), src,
                 flags=re.S)
    assert new != src or body in src
    with open(PLUGIN, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print("panel written: %d intervals, %d chars, %d lines  rss %.2f GB" % (len(st), len(body), len(lines), rss()))


def _hunt_trades(cell):
    df = pd.read_csv(HUNT + "trades_%s_eval.csv" % cell)
    df["entry"] = pd.to_datetime(df["entry"], utc=True)
    df["exit"] = pd.to_datetime(df["exit"], utc=True)
    return df


def _cmp(name, mine, hunt, lo, hi):
    """Match by (entry time, exit time); report counts and PnL agreement, both restricted to exits in [lo, hi]."""
    def win(df):
        xd = df["exit"].dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
        return df[(xd >= lo) & (xd <= hi)]
    a = win(mine); b = win(hunt)
    ka = set(zip(a.entry.astype("int64"), a.exit.astype("int64")))
    kb = set(zip(b.entry.astype("int64"), b.exit.astype("int64")))
    both = ka & kb
    j = a.merge(b, on=["entry", "exit"], suffixes=("_m", "_h"))
    dp = np.abs(j.g_m - j.g_h).max() if len(j) else float("nan")
    ent_a = set(a.entry.astype("int64")); ent_b = set(b.entry.astype("int64"))
    print("%s %s..%s: plugin %d, hunt %d, same entry+exit %d (%.2f%% of hunt), same entry %d; max |pnl diff| on "
          "matched %.6f pt" % (name, lo, hi, len(ka), len(kb), len(both), 100.0 * len(both) / max(1, len(kb)),
                                len(ent_a & ent_b), dp))
    only_a = sorted(ka - kb)[:5]; only_b = sorted(kb - ka)[:5]
    for tag, lst in (("plugin only", only_a), ("hunt only", only_b)):
        for e, x in lst:
            print("    %s: %s -> %s" % (tag, pd.Timestamp(e, tz="UTC").tz_convert(TZ), pd.Timestamp(x, tz="UTC").tz_convert(TZ)))
    return len(both), len(kb)


def parity():
    sys.path.insert(0, HERE)
    P = _mod(PLUGIN, "ESALONE")
    prm = {k: v["default"] for k, v in P.DEFAULT_PARAMS.items()}
    d, m = _load("ES", "2025-06-30", HUNT_CUT)
    print("ES master %s; bars %d %s .. %s  rss %.2f GB" % (m.get("filename"), len(d["close"]), d["index"][0],
                                                         d["index"][-1], rss()))
    idx = d["index"]
    tt = idx.tz_convert("UTC")
    for gate, cell in ((0, "73d"), (1, "73a"), (2, "73b")):
        r = P.run_backtest(d["open"], d["high"], d["low"], d["close"], d["volume"], index=idx,
                           return_trades=True, **dict(prm, nq_gate=gate))
        tr = r["trades"]
        mine = pd.DataFrame({"entry": tt[[q[0] for q in tr]], "exit": tt[[q[1] for q in tr]],
                             "g": [q[2] for q in tr]})
        hunt = _hunt_trades(cell)
        print("nq_gate %d vs hunt %s:" % (gate, cell))
        for lo, hi in (("2010-06-07", "2016-06-30"), ("2016-07-01", "2025-06-30")):
            _cmp("  ", mine, hunt, pd.Timestamp(lo), pd.Timestamp(hi))
    # the engine path (roll guard + introspection) at defaults, EVAL stretch only
    try:
        from augur_engine import run_backtest as ERB
        arr = {"open": d["open"], "high": d["high"], "low": d["low"], "close": d["close"], "volume": d["volume"],
               "index": idx, "day_id": pd.factorize(idx.tz_localize(None).normalize())[0].astype("int64"),
               "meta": d["meta"]}
        r = ERB(P, arrays=arr, params=prm, return_trades=True)
        tr = r["trades"]
        mine = pd.DataFrame({"entry": tt[[q[0] for q in tr]], "exit": tt[[q[1] for q in tr]],
                             "g": [q[2] for q in tr]})
        print("engine path (augur_engine.run_backtest) at defaults vs hunt 73d:")
        _cmp("  ", mine, _hunt_trades("73d"), pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-30"))
    except Exception as e:
        print("engine path: %s: %s" % (type(e).__name__, str(e)[:300]))
    print("rss %.2f GB" % rss())


if __name__ == "__main__":
    {"build": build, "parity": parity}[sys.argv[1]]()

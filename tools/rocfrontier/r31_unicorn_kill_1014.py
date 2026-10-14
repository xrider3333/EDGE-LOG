"""UNICORN KILL TEST 10-14 (STRATEGY-BEATING; MANAGER #172): arXiv 2511.12490's drift-regime factor rebuilt on our Alpaca daily
stocks, then stripped of same-close fills, its 0.6 bp cost and its hindsight universe one at a time. Pre-registered in
docs/PREREG_SB_UNICORN_KILL_2026-10-14.md (the LF sha256 below is checked before anything loads).

    python tools/rocfrontier/r31_unicorn_kill_1014.py

Writes only C:/EdgeLog/_anatomy_cache/rocfrontier/unicorn1014/. Reads only; no augur_engine change.
"""
import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from augur_engine import seat_pipeline as SP              # noqa: E402
from augur_engine import drawdowns as DD                   # noqa: E402

NOTE = os.path.join(REPO, "docs", "PREREG_SB_UNICORN_KILL_2026-10-14.md")
NOTE_SHA = "55c8c57a227b138b99c76fb4bcab1ad1653dfae1f27308b7ee14ed8d417b104d"
SRC = r"C:\EdgeLog\alpaca_cache\siporb"
OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\unicorn1014"
TS = pd.Timestamp
ACCT = 100_000.0
WF = (TS("2016-07-01"), TS("2025-06-29"))
AFTER = (TS("2025-06-30"), TS("2026-06-30"))
EXCH = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}
TOPN, DVWIN, REGWIN, REGTH, REVWIN, WVAL = 500, 63, 63, 0.60, 10, 0.7
CELLS = (  # name, fill, cost bp, weights key
    ("(a) as published: close fill, 0.6 bp, U", "close", 0.6, "U"),
    ("(b) next-open fill, 0.6 bp, U", "open", 0.6, "U"),
    ("(c) close fill, 5 bp, U", "close", 5.0, "U"),
    ("(d) close fill, 10 bp, U", "close", 10.0, "U"),
    ("(e) next-open fill, 10 bp, U", "open", 10.0, "U"),
    ("(f) REPORT: close fill, 0.6 bp, point-in-time P", "close", 0.6, "P"),
    ("(g) REPORT: close fill, 0.6 bp, U, value on split-ADJUSTED price", "close", 0.6, "Uadj"),
)


def sha_lf(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def load():
    a = pd.read_csv(os.path.join(SRC, "assets.csv"), dtype=str, keep_default_na=False)
    a = a[a.exchange.isin(EXCH) & ~a.name.str.contains(r"Depositary|\bADR\b", case=False, regex=True)]
    keep = set(a.symbol)
    raw = pd.read_parquet(os.path.join(SRC, "daily_raw.parquet"), columns=["symbol", "date", "c", "v"])
    spl = pd.read_parquet(os.path.join(SRC, "daily_split.parquet"), columns=["symbol", "date", "o", "c"])
    raw = raw[raw.symbol.isin(keep)]
    spl = spl[spl.symbol.isin(keep)]
    rc = raw.pivot(index="date", columns="symbol", values="c")
    vv = raw.pivot(index="date", columns="symbol", values="v").reindex_like(rc)
    sc = spl.pivot(index="date", columns="symbol", values="c").reindex_like(rc)
    so = spl.pivot(index="date", columns="symbol", values="o").reindex_like(rc)
    cnt = rc.notna().sum(axis=1)
    cal = cnt.index[cnt >= 1000]
    rc, vv, sc, so = (x.loc[cal].sort_index() for x in (rc, vv, sc, so))
    return rc, vv, sc, so


def edge_weights(member, price_for_value, sc):
    """-> (T x N) target weights (fraction of the account, longs +0.5 / shorts -0.5) from the paper's EDGE, plus counts"""
    r = sc / sc.shift(1) - 1.0
    up = (r > 0).astype(float).where(r.notna())
    upfrac = up.shift(1).rolling(REGWIN, min_periods=REGWIN).mean()          # days t-1 .. t-63
    rev = -(sc / sc.shift(REVWIN) - 1.0)
    have = member & price_for_value.notna() & sc.notna()
    val = (1.0 / price_for_value).where(have).rank(axis=1, pct=True)
    rv = rev.where(have)
    rz = rv.sub(rv.mean(axis=1), axis=0).div(rv.std(axis=1, ddof=0), axis=0)
    base = WVAL * val + (1 - WVAL) * rz
    act = have & (upfrac > REGTH) & base.notna()
    e = base.where(act)
    z = e.sub(e.mean(axis=1), axis=0)                                        # the sd cancels inside each side
    zp, zn = z.clip(lower=0), (-z).clip(lower=0)
    w = 0.5 * zp.div(zp.sum(axis=1), axis=0) - 0.5 * zn.div(zn.sum(axis=1), axis=0)
    w = w.fillna(0.0)
    counts = pd.DataFrame({"active": act.sum(axis=1), "long": (w > 0).sum(axis=1), "short": (w < 0).sum(axis=1)})
    return w, counts


def book(w, ret, ends, bp):
    """target weights w[t] held over the period whose return is ret[t] and which ends on ends[t]; cost bp on every unit traded"""
    W = w.to_numpy() * ACCT
    R = np.nan_to_num(ret.to_numpy(), nan=0.0)
    carried = np.zeros(W.shape[1])
    pnl, turn, contrib = np.zeros(len(W)), np.zeros(len(W)), np.zeros_like(W)
    for t in range(len(W)):
        traded = np.abs(W[t] - carried).sum()
        contrib[t] = W[t] * R[t]
        pnl[t] = contrib[t].sum() - bp * 1e-4 * traded
        turn[t] = traded / ACCT
        carried = W[t] * (1.0 + R[t])
    ok = ~pd.isna(ends)
    return (pd.Series(pnl[ok], index=pd.DatetimeIndex(ends[ok])), pd.Series(turn[ok], index=pd.DatetimeIndex(ends[ok])),
            pd.DataFrame(contrib[ok], index=pd.DatetimeIndex(ends[ok]), columns=w.columns))


def read(s, turn, a, b):
    f = SP.figures(s, a, b)
    x = SP.window(s, a, b)
    sh = float(x.mean() / x.std() * np.sqrt(252.0)) if x.std() > 0 else float("nan")
    return dict(roc30=f["roc30"], dd5=f["dd5"], one_episode=f["one_episode"], dd_pct=DD.dd_pct_peak(x.to_numpy(float), start=ACCT),
                sortino=f["sortino"], sharpe=sh, net_per_year=f["net_per_year"], max_dd=f["dd"],
                turnover=float(SP.window(turn, a, b).mean()) if turn is not None else float("nan"), days=len(x))


def fmt(nm, st):
    return (f"  {nm}: ROC @ $30k {st['roc30']:.1f} | DD5 ${st['dd5']:,.0f}{' (one episode)' if st['one_episode'] else ''} | "
            f"DD% from peak {st['dd_pct']:.1f}% | Sortino {st['sortino']:.2f} || Sharpe {st['sharpe']:.2f}, net ${st['net_per_year']:,.0f} "
            f"a year, turnover {100 * st['turnover']:.0f}% a day")


def main():
    t0 = time.time()
    got = sha_lf(NOTE)
    if got != NOTE_SHA:
        raise SystemExit(f"refused: the prereg note's LF sha256 is {got[:16]}..., not the frozen {NOTE_SHA[:16]}... (nothing run)")
    os.makedirs(OUT, exist_ok=True)
    print(f"note {got[:16]}... verified (MANAGER #172)", flush=True)
    rc, vv, sc, so = load()
    dates = rc.index
    print(f"data: {rc.shape[1]:,} common names, {len(dates):,} sessions {dates[0].date()} .. {dates[-1].date()} ({time.time() - t0:.0f}s)",
          flush=True)
    dv63 = (rc * vv).rolling(DVWIN, min_periods=DVWIN).mean()
    last = dv63.iloc[-1].where(rc.iloc[-1].notna()).dropna()
    U = list(last.sort_values(ascending=False).index[:TOPN])
    memU = pd.DataFrame(True, index=dates, columns=U)
    prev = dv63.shift(1).where(rc.notna())
    rk = prev.rank(axis=1, ascending=False, method="first")
    memP = rk <= TOPN
    print(f"U: {len(U)} names chosen on 2026-06-30 (top: {', '.join(U[:12])}); P: {int(memP.sum(axis=1).median())} members a day "
          f"(median), {int(memP.any().sum()):,} distinct names over the years", flush=True)
    Pcols = list(memP.columns[memP.any()])
    W = {}
    W["U"], cU = edge_weights(memU, rc[U], sc[U])
    W["Uadj"], _ = edge_weights(memU, sc[U], sc[U])
    W["P"], cP = edge_weights(memP[Pcols], rc[Pcols], sc[Pcols])
    print(f"active names a day (median): U {int(cU.active.median())} (longs {int(cU.long.median())} / shorts {int(cU.short.median())}), "
          f"P {int(cP.active.median())}; active share of U {float((cU.active / sc[U].notna().sum(axis=1)).median()):.0%}", flush=True)
    ends_close = np.array(list(dates[1:]) + [pd.NaT], dtype=object)
    ends_open = np.array(list(dates[2:]) + [pd.NaT, pd.NaT], dtype=object)
    rows, lines, yearly = [], [], {}
    for name, fill, bp, key in CELLS:
        w = W[key]
        cols = w.columns
        if fill == "close":
            ret = (sc[cols].shift(-1) / sc[cols] - 1.0)
            s, turn, contrib = book(w, ret, ends_close, bp)
        else:
            ret = (so[cols].shift(-2) / so[cols].shift(-1) - 1.0)
            s, turn, contrib = book(w, ret, ends_open, bp)
        k0 = len(lines)
        lines.append(f"\n{name}")
        for nm, (a, b) in (("WF 2016-07-01..2025-06-29", WF), ("AFTER 2025-06-30..2026-06-30", AFTER)):
            st = read(s, turn, a, b)
            lines.append(fmt(nm, st))
            rows.append(dict(cell=name, stretch=nm.split(" ")[0], cost_bp=bp, fill=fill, universe=key, **st))
        x = SP.window(s, WF[0], AFTER[1])
        yr = x.groupby(x.index.year).apply(lambda q: q.mean() / q.std() * np.sqrt(252.0) if q.std() > 0 else np.nan)
        yearly[name] = yr.round(2).to_dict()
        lines.append("  Sharpe by year: " + ", ".join(f"{k} {v:.1f}" for k, v in yr.items()))
        if name.startswith(("(a)", "(b)")):
            c = contrib.loc[WF[0]:WF[1]].stack()
            top = c.sort_values(ascending=False)
            net = float(SP.window(s, *WF).sum())
            lines.append("  WF top 5 stock-days: " + "; ".join(f"{d.date()} {sym} ${v:,.0f}" for (d, sym), v in top.head(5).items()))
            lines.append(f"  WF top 20 stock-days = ${top.head(20).sum():,.0f} = {top.head(20).sum() / net:.0%} of WF net ${net:,.0f}")
        s.to_csv(os.path.join(OUT, "daily_" + name[:3].strip("() ") + ".csv"), header=["pnl"])
        print("\n".join(lines[k0:]), flush=True)
    for key, cols in (("U", U), ("P", Pcols)):
        m = memU if key == "U" else memP[Pcols]
        r = (sc[cols].shift(-1) / sc[cols] - 1.0).where(m)
        eq = pd.Series(r.mean(axis=1).to_numpy() * ACCT, index=pd.DatetimeIndex(ends_close)).dropna()
        eq = eq[eq.index.notna()]
        for nm, (a, b) in (("WF", WF), ("AFTER", AFTER)):
            st = read(eq, None, a, b)
            msg = fmt(f"BENCHMARK equal-weight long {key}, {nm}", st)
            lines.append(msg)
            print(msg, flush=True)
            rows.append(dict(cell=f"benchmark EW long {key}", stretch=nm, cost_bp=0.0, fill="close", universe=key, **st))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "unicorn1014_summary.csv"), index=False)
    json.dump(dict(note_sha=got, U=U, yearly_sharpe=yearly), open(os.path.join(OUT, "unicorn1014_meta.json"), "w"), indent=1, default=str)
    open(os.path.join(OUT, "UNICORN1014.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"\ndone in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()

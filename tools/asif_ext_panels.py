r"""tools/asif_ext_panels.py -- AS-IF EXTENSION side panels for the book as-if series (owner "stockprices ok", 2026-11-21).

WHY. Three book legs read SHA-pinned side panels that end 2026-06-30, so their as-if series (tools/book_asif_series.py)
stopped there: PICK6 (MISC_EODREV_1_2, run #511), OPUS86a (MISC_AUCHABIT_1_0, run #526) and GLDNIGHT
(MISC_GLDNIGHT_1_0, run #541). The pinned panels must stay as they are (runs #511 / #526 / #541 reproduce from them).
Each plugin now takes an OPTIONAL extension panel through an environment variable (PANEL_EXT_ENV in the file; unset =
the pinned behaviour, byte for byte). Sessions after the pinned panel's last date are scored on the extension panel,
from its own rows only - nothing is spliced.

This script builds those extension panels from fresh Alpaca SIP pulls. It NEVER writes a pinned *_v1.npz.

    python tools/asif_ext_panels.py gldnight     -> C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_asif.npz
    python tools/asif_ext_panels.py auchabit     -> C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_asif.npz
    python tools/asif_ext_panels.py eodrev       -> C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_u100_panel_asif.npz
                                                   (api/eodrev_live.refresh_panel, same code as the paper lane's
                                                   nightly live panel, but from a FIXED start 2025-09-01: the live
                                                   panel rolls 420 days back, so its July 2026 betas would lose their
                                                   warm-up within weeks and the as-if would drift)
    python tools/asif_ext_panels.py check        -> each extension panel against its pinned panel on the overlap

Layouts are the pinned builders' (tools/misc_gldnight_panel.py, tools/misc_auchabit_panel.py) with these differences:
  * GLDNIGHT: GLD daily official open / close come from Alpaca 1Day bars (adjustment raw; split pulled too and must be
    equal - GLD never split), the 5m clock from the GLD 5m RTH master (alpaca_split_rth) in the shared registry;
    window 2026-05-01 .. the master's last session (the first night after the pinned end needs 2026-06-30 as D-1);
  * AUCHABIT: 10-minute SIP split bars, the bar that starts 15:50 (open = O50, close = C50), one request per session
    (eodrev_live.window_bars), daily split close (dc) and raw close from Alpaca 1Day bars; names = the 2025 and 2026
    point-in-time top-100 lists; window 2025-09-29 .. the last completed session (warm-up for a 120-session habit);
    FULL = SPY has a 15:50 bar AND the SPY 5m RTH master's last bar that session is 15:55 (a half day stops at
    12:55 - the pinned build used a frozen early-close list instead; same rule, data-driven).
Read-only on the registry. Never touches orders, the box or api/ state. Keys via augur_engine.alpaca_keys, never printed.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SHARED)          # the shared checkout's augur_engine + master registry (the worktree registry trap)
from api import eodrev_live as L  # noqa: E402  (fetch_bars, window_bars, _keys, refresh_panel)

NY = "America/New_York"
CACHE = "C:/EdgeLog/alpaca_cache"
GLD_PINNED = CACHE + "/gldnight_panel/gldnight_panel_v1.npz"
GLD_OUT = CACHE + "/gldnight_panel/gldnight_panel_asif.npz"
AUC_PINNED = CACHE + "/auchabit_panel/auchabit_panel_v1.npz"
AUC_OUT = CACHE + "/auchabit_panel/auchabit_panel_asif.npz"
EOD_PINNED = CACHE + "/eodrev_panel/eodrev_u100_panel_v1.npz"
EOD_OUT = CACHE + "/eodrev_panel/eodrev_u100_panel_asif.npz"
EOD_START = "2025-09-01"                    # fixed: a 250-session beta is warm by 2026-07-01
UNIVERSE = os.path.join(HERE, "tools", "data", "eodrev_universe_pit100.json")
PINNED = {GLD_PINNED, AUC_PINNED, EOD_PINNED}


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _save(path, arrays):
    assert os.path.abspath(path) not in {os.path.abspath(p) for p in PINNED}, "refusing to overwrite a pinned panel"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez(tmp, **arrays)
    os.replace(tmp, path)
    print("wrote %s  rows %d  %s .. %s  sha256 %s" % (path, len(arrays["dates"]), arrays["dates"][0],
                                                      arrays["dates"][-1], _sha(path)))


def _master_sessions(sym):
    """{yyyymmdd: (first minute, last minute)} of the sym 5m RTH alpaca_split_rth master (shared registry)."""
    cwd = os.getcwd()
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    try:
        m = D.find_master(sym, "5m", "rth", "alpaca_split_rth")
        assert m is not None, "%s 5m master not registered" % sym
        a = D.load_master_arrays(m, date_from="2025-06-01", date_to=None)
    finally:
        os.chdir(cwd)
    idx = a["index"].tz_convert(NY)
    d = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    mm = (idx.hour * 60 + idx.minute).to_numpy()
    df = pd.DataFrame({"d": d, "m": mm})
    g = df.groupby("d").m
    print("%s 5m master id %s: %d sessions to %s" % (sym, m["id"], g.ngroups, int(df.d.max())))
    return pd.DataFrame({"first": g.min(), "last": g.max()})


def _iso(x):
    return x.isoformat().replace("+00:00", "Z")


def _daily(frames, sym, col):
    df = frames.get(sym)
    if df is None or not len(df):
        return pd.Series(dtype=float)
    t = pd.to_datetime(df["t"], utc=True).dt.tz_convert(NY).dt.strftime("%Y%m%d").astype("int64")
    return pd.Series(df[col].values.astype(float), index=t.values).groupby(level=0).first()


def _end_utc():
    """Midnight ET today: daily bars of COMPLETED sessions only."""
    today = dt.datetime.now(L._ny()).date()
    return dt.datetime.combine(today, dt.time(0, 0), tzinfo=L._ny()).astimezone(dt.timezone.utc)


# ------------------------------------------------------------------ GLDNIGHT
def build_gldnight(out=GLD_OUT, start="2026-05-01"):
    keys = L._keys()
    a = dt.datetime.fromisoformat(start).replace(tzinfo=L._ny()).astimezone(dt.timezone.utc)
    b = _end_utc()
    raw = L.fetch_bars(["GLD"], "1Day", _iso(a), _iso(b), adjustment="raw", keys=keys)
    spl = L.fetch_bars(["GLD"], "1Day", _iso(a), _iso(b), adjustment="split", keys=keys)
    o, c = _daily(raw, "GLD", "o"), _daily(raw, "GLD", "c")
    so, sc = _daily(spl, "GLD", "o"), _daily(spl, "GLD", "c")
    if not (o.index.equals(so.index) and np.allclose(o.values, so.values) and np.allclose(c.values, sc.values)):
        sys.exit("GLD raw and split daily bars differ (a split or re-adjustment) - nothing written")
    ms = _master_sessions("GLD")
    cal = o.index[o.index <= int(ms.index.max())]
    miss = sorted(set(cal) - set(ms.index))
    extra = sorted(set(ms.index[ms.index >= int(cal[0])]) - set(cal))
    if miss or extra:
        sys.exit("calendar mismatch daily vs 5m master: only daily %s, only master %s" % (miss[:10], extra[:10]))
    first = ms["first"].reindex(cal).to_numpy().astype("int64")
    last = ms["last"].reindex(cal).to_numpy().astype("int64")
    if (first != 570).any():
        sys.exit("5m sessions whose first bar is not 09:30: %s" % list(cal[first != 570]))
    days = pd.to_datetime(pd.Series(cal.astype(str)), format="%Y%m%d")
    gap = np.concatenate([[0], np.diff(days.values).astype("timedelta64[D]").astype("int64")])
    arrays = {"dates": np.asarray(cal, "int64"), "open": o.reindex(cal).to_numpy(np.float64),
              "close": c.reindex(cal).to_numpy(np.float64), "raw": c.reindex(cal).to_numpy(np.float64),
              "first_min": first, "last_min": last, "gap": gap.astype("int64")}
    print("short sessions (last bar not 15:55):", {int(d): int(m) for d, m in zip(cal, last) if m != 955})
    _save(out, arrays)


# ------------------------------------------------------------------ AUCHABIT
def build_auchabit(out=AUC_OUT, start="2025-09-29"):
    keys = L._keys()
    U = json.load(open(UNIVERSE, encoding="utf-8"))
    years = sorted(y for y in U if int(y) >= int(start[:4]))
    names = sorted({s for y in years for s in U[y][:100]} - {"SPY"})
    syms = names + ["SPY"]
    a = dt.datetime.fromisoformat(start).replace(tzinfo=L._ny()).astimezone(dt.timezone.utc)
    b = _end_utc()
    print("auchabit ext: %d names (lists %s), %s .. %s" % (len(names), years, a.date(), b.date()))
    dsp = L.fetch_bars(syms, "1Day", _iso(a), _iso(b), adjustment="split", keys=keys)
    draw = L.fetch_bars(syms, "1Day", _iso(a), _iso(b), adjustment="raw", keys=keys)
    rows = _daily(dsp, "SPY", "c").index.sort_values()
    b10 = L.window_bars(syms, list(rows), keys=keys)

    def at50(sym, col):
        df = b10.get(sym)
        if df is None or not len(df):
            return pd.Series(dtype=float)
        t = pd.to_datetime(df["t"], utc=True).dt.tz_convert(NY)
        k = ((t.dt.hour * 60 + t.dt.minute) == 950).values
        idx = t[k].dt.strftime("%Y%m%d").astype("int64")
        return pd.Series(df[col].values[k].astype(float), index=idx.values).groupby(level=0).first()

    O = pd.DataFrame({s: at50(s, "o") for s in syms}).reindex(rows)
    C = pd.DataFrame({s: at50(s, "c") for s in syms}).reindex(rows)
    dc = pd.DataFrame({s: _daily(dsp, s, "c") for s in names}).reindex(index=rows, columns=names)
    rw = pd.DataFrame({s: _daily(draw, s, "c") for s in names}).reindex(index=rows, columns=names)
    ms = _master_sessions("SPY")
    lastbar = ms["last"].reindex(rows)
    full = (O["SPY"].notna() & (lastbar == 955)).to_numpy()
    member = np.zeros((len(rows), len(names)), bool)
    col = {s: j for j, s in enumerate(names)}
    yr = (np.asarray(rows) // 10000).astype(int)
    for y in years:
        r = yr == int(y)
        member[np.ix_(r, [col[s] for s in U[y][:100] if s in col])] = True
    print("rows %d, FULL %d, not full: %s" % (len(rows), int(full.sum()),
                                             [int(d) for d, f in zip(rows, full) if not f]))
    arrays = {"dates": np.asarray(rows, "int64"), "names": np.array(names), "full": full,
              "o50": O[names].values.astype("float32"), "c50": C[names].values.astype("float32"),
              "dc": dc.values.astype("float32"), "raw": rw.values.astype("float32"), "member": member}
    _save(out, arrays)


# ------------------------------------------------------------------ the overlap check
def check():
    """Each extension panel against its pinned panel on the dates both carry: price cells, then the champion's daily
    P&L computed by the plugin on each panel alone (the number the as-if series actually uses)."""
    import importlib.util

    def plug(fn):
        sp = importlib.util.spec_from_file_location(fn[:-3], os.path.join(HERE, "augur_strategies", fn))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    def cells(label, pa, pb, keys, names_key=None):
        za, zb = np.load(pa), np.load(pb)
        common = np.intersect1d(za["dates"], zb["dates"])
        ia = np.searchsorted(za["dates"], common)
        ib = np.searchsorted(zb["dates"], common)
        print("%s: overlap %d sessions %s .. %s" % (label, len(common), common[0], common[-1]))
        if names_key:
            na, nb = [str(x) for x in za[names_key]], [str(x) for x in zb[names_key]]
            nm = sorted(set(na) & set(nb))
            ja, jb = [na.index(s) for s in nm], [nb.index(s) for s in nm]
        for k in keys:
            A = za[k][ia].astype(float)
            B = zb[k][ib].astype(float)
            if names_key:
                A, B = A[:, ja], B[:, jb]
            ok = np.isfinite(A) & np.isfinite(B) & (A != 0)
            r = np.abs(B[ok] / A[ok] - 1)
            print("   %-6s cells %7d  |ratio-1| > 1e-4: %5d  > 1e-2: %4d  max %.4g" % (
                k, int(ok.sum()), int((r > 1e-4).sum()), int((r > 1e-2).sum()), float(r.max()) if len(r) else 0))

    def pnl_cmp(label, a, b, since):
        ks = sorted(d for d in set(a) | set(b) if int(d) >= since)
        both = [d for d in ks if d in a and d in b]
        x = np.array([a[d] for d in both])
        y = np.array([b[d] for d in both])
        same = int(np.sum(np.abs(x - y) < 0.01))
        print("   %s daily P&L since %d: pinned %d days $%.0f, ext %d days $%.0f; both %d, equal to the cent %d, "
              "corr %.3f" % (label, since, sum(1 for d in ks if d in a), sum(a.get(d, 0) for d in ks),
                             sum(1 for d in ks if d in b), sum(b.get(d, 0) for d in ks), len(both), same,
                             float(np.corrcoef(x, y)[0, 1]) if len(both) > 2 else float("nan")))

    if os.path.exists(GLD_OUT):
        cells("GLDNIGHT", GLD_PINNED, GLD_OUT, ("open", "close", "raw", "first_min", "last_min", "gap"))
    if os.path.exists(AUC_OUT):
        cells("AUCHABIT", AUC_PINNED, AUC_OUT, ("o50", "c50", "dc", "raw"), "names")
        m = plug("MISC_AUCHABIT_1_0.py")
        champ = dict(notional=100000, spread_cents=1.0, fee_bps=0.3, period_len=60, k=1, min_price=80,
                     weekday_habit=False, legs=0)                          # run #526 champion
        pa = m._prepare(**m._read_panel())
        pb = m._prepare(**m._read_panel(AUC_OUT, pinned=False))
        f = lambda p: {int(d): float(v) for d, v in zip(*m._daily(p, **champ))}
        pnl_cmp("#526 champion", f(pa), f(pb), 20260102)
    if os.path.exists(EOD_OUT):
        cells("EODREV", EOD_PINNED, EOD_OUT, ("ps", "pe", "c10", "dc", "raw"), "names")
        m = plug("MISC_EODREV_1_2.py")
        champ = dict(notional=100000, spread_cents=1.0, fee_bps=0.3, k=3, beta_len=180, min_price=60,
                     beta_adjust=True, period_len=60, period_wt=1.5)      # run #511 champion
        a = m._daily_pnl(m._load_panel(EOD_PINNED, m.PANEL_SHA256), cache={}, **champ)
        b = m._daily_pnl(m._load_panel(EOD_OUT, None), cache={}, **champ)
        pnl_cmp("#511 champion", a, b, 20260102)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("gldnight", "auchabit", "eodrev", "check"))
    a = ap.parse_args(argv)
    if a.what == "gldnight":
        build_gldnight()
    elif a.what == "auchabit":
        build_auchabit()
    elif a.what == "eodrev":
        days_back = (dt.date.today() - dt.date.fromisoformat(EOD_START)).days
        assert os.path.abspath(EOD_OUT) not in {os.path.abspath(p) for p in PINNED | {L.DEFAULT_PANEL}}
        L.refresh_panel(EOD_OUT, days_back=days_back)
    else:
        check()
    return 0


if __name__ == "__main__":
    sys.exit(main())

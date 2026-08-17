"""
ORB HUNT — the search for a better LEGAL ORB than run #230 / ORB_3_4_C221.

Owner directive 2026-08-17: "continue searching for better / different / improved
variants of ORB. dont stop until youve found one."

Ground rules baked in here (from ORB.md + memory edgelog-orb-grail-hunt):
  * LEGAL ONLY. Every filter input must close strictly BEFORE the bar that fills.
    close_confirm=True makes the entry a bar-close decision, so nothing on the fill
    bar is ever unknowable. The retired vol_filter is not reachable from this file.
  * THE LOCKBOX IS THE JUDGE, NOT THE IN-SAMPLE. The 24k-config screen measured
    spearman(IS MAR -> LB $) = -0.088, i.e. NEGATIVE. Ranking on in-sample is worse
    than useless here, so every table prints IS and LB side by side and nothing is
    ever crowned on the IS column.
  * PIN THE WINDOW. Splits are fixed dates, never "last N days of whatever synced".

Windows (fixed):
    FULL  2010-06-07 .. 2026-08-13
    IS    ..           .. 2025-08-13     (fit / screen here)
    LB    2025-08-13   .. 2026-08-13     (run #230's own lockbox; reused, so treat
                                          it as a sanity check, not a fresh gate)

Usage:
    python tools/orb_hunt.py control          # reproduce C221, prove the harness
    python tools/orb_hunt.py <sweep-name>     # see SWEEPS at the bottom
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
MULT = 20.0          # NQ $/point
COST_PTS = 0.533     # $5.66 commission / 20 + 0.25 pt slippage

IS_END = "2025-08-13"
LB_END = "2026-08-13"

# run #230's crowned config — the thing every variant has to beat.
C221 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, breakout_buf=0.25,
            close_confirm=True, partial_exit_R=3.0, trail_bars=3, target_R=5.5,
            atr_filter=0.7, vpace_filter=0.7, flat_eod=True, skip_holidays=True)


# ── data ─────────────────────────────────────────────────────────────────────────
_BARS = None


def bars():
    """NQ 5m RTH master as a dict of arrays + an ET DatetimeIndex. Cached."""
    global _BARS
    if _BARS is not None:
        return _BARS
    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    _BARS = dict(
        open=df["open"].values.astype(float), high=df["high"].values.astype(float),
        low=df["low"].values.astype(float), close=df["close"].values.astype(float),
        volume=df["volume"].values.astype(float) if "volume" in df.columns else None,
        day_id=df["day_id"].values, index=pd.DatetimeIndex(df["_dt"]),
    )
    return _BARS


def slice_bars(date_from=None, date_to=None):
    """Window the master by ET calendar date. day_id is re-factorized so session
    boundaries stay correct inside the slice."""
    b = bars()
    idx = b["index"]
    m = np.ones(len(idx), bool)
    if date_from:
        m &= (idx.date >= pd.Timestamp(date_from).date())
    if date_to:
        m &= (idx.date <= pd.Timestamp(date_to).date())
    out = {k: (v[m] if isinstance(v, np.ndarray) else v[m])
           for k, v in b.items() if v is not None}
    out["day_id"] = pd.factorize(pd.Series(out["index"]).dt.date)[0]
    return out


# ── strategy loading ─────────────────────────────────────────────────────────────
_MODS = {}


def strat(name):
    """Load a strategy file from augur_strategies/ by filename."""
    if name in _MODS:
        return _MODS[name]
    path = os.path.join(ROOT, "augur_strategies", name)
    spec = importlib.util.spec_from_file_location("_hunt_" + name.replace(".", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


# ── scoring ──────────────────────────────────────────────────────────────────────
def score(trades_pts, mult=MULT, cost=COST_PTS):
    """Net-dollar stats from a list of RAW (pre-cost) point PnLs."""
    if not len(trades_pts):
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, mar=0.0, wr=0.0, avg=0.0)
    p = (np.asarray(trades_pts, float) - cost) * mult
    wins, losses = p[p > 0], p[p < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum())
    return dict(n=len(p), net=net, pf=(gw / gl if gl > 1e-9 else float("inf")),
                dd=abs(dd), mar=(net / abs(dd) if dd else float("inf")),
                wr=100.0 * len(wins) / len(p), avg=net / len(p))


def run(strategy, params, date_from=None, date_to=None):
    """Backtest one config on one window. Returns (stats, trades) where trades is a
    list of (entry_i, exit_i, raw_pnl_pts, side, entry_px) in the SLICE's indexing."""
    b = slice_bars(date_from, date_to)
    mod = strat(strategy)
    r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"],
                         volumes=b.get("volume"), day_id=b["day_id"],
                         return_trades=True, **params)
    if not r:
        return score([]), [], b
    tr = r.get("trades") or []
    return score([t[2] for t in tr]), tr, b


def row(label, params, strategy="ORB_3_4.py"):
    """One IS + LB + FULL reading for a config."""
    is_s, _, _ = run(strategy, params, None, IS_END)
    lb_s, _, _ = run(strategy, params, IS_END, LB_END)
    fu_s, _, _ = run(strategy, params, None, LB_END)
    return dict(label=label, params=params, strategy=strategy,
                IS=is_s, LB=lb_s, FULL=fu_s)


HDR = ("%-46s | %5s %10s %5s %8s | %4s %9s %5s" %
       ("config", "IS n", "IS net", "IS PF", "IS MAR", "LB n", "LB net", "LB PF"))


def show(rows, title=""):
    if title:
        print("\n=== %s ===" % title)
    print(HDR)
    print("-" * len(HDR))
    for r in rows:
        i, l = r["IS"], r["LB"]
        print("%-46s | %5d %10s %5.2f %8.2f | %4d %9s %5.2f" % (
            r["label"][:46], i["n"], "${:,.0f}".format(i["net"]), min(i["pf"], 9.99),
            min(i["mar"], 99), l["n"], "${:,.0f}".format(l["net"]), min(l["pf"], 9.99)))


def full_line(r):
    f = r["FULL"]
    return ("FULL  n=%d  net=%s  PF=%.3f  DD=%s  MAR=%.2f  WR=%.1f%%" % (
        f["n"], "${:,.0f}".format(f["net"]), f["pf"],
        "${:,.0f}".format(f["dd"]), f["mar"], f["wr"]))


# ── sweeps ───────────────────────────────────────────────────────────────────────
def sweep_control():
    """Prove the harness reproduces run #230 before trusting anything else."""
    r = row("C221 (run #230 champion)", C221)
    show([r], "CONTROL")
    print("\n" + full_line(r))
    print("\nexpected from run #230 / memory: n=2607  net=$348,129  PF=1.263  "
          "DD=$35,474  MAR=9.81  WR=49.4%")


def sweep_be():
    """Item H on the legal base: offer run #230's champion the breakeven lever.
    The voided touch-entry study found a robust 0.9-1.3R plateau (DD -33%). The
    judge is the LB column + the FULL DD, never the IS net."""
    rows = []
    for be in (0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0):
        p = dict(C221, be_after_R=be)
        rows.append(row("C221 + be_after_R=%.1f" % be, p, "ORB_3_6.py"))
    show(rows, "BREAKEVEN SCAN (be=0.0 row = the #230 champion)")
    print()
    for r in rows:
        print("%-34s %s" % (r["label"], full_line(r)))


def _year_table(strategy, params, label):
    """Year-by-year net for one config over the full window."""
    s, tr, b = run(strategy, params, None, LB_END)
    idx = b["index"]
    ys = {}
    for t in tr:
        y = idx[t[0]].year
        ys.setdefault(y, []).append(t[2])
    print("\n%s — by year (net $, n):" % label)
    for y in sorted(ys):
        st = score(ys[y])
        print("  %d  %10s  n=%3d  PF %.2f" % (y, "${:+,.0f}".format(st["net"]), st["n"], min(st["pf"], 9.99)))
    return s


def sweep_beyears():
    """Stability check of the BE plateau: year-by-year, be=0 vs 0.8 vs 1.0 vs 1.2."""
    for be in (0.0, 0.8, 1.0, 1.2):
        _year_table("ORB_3_6.py", dict(C221, be_after_R=be), "be=%.1f" % be)


def sweep_cutoff():
    """Item #411: does barring late entries help the champion? Exact emulation:
    the strategy takes ONE trade per session at the FIRST qualifying bar, so
    dropping trades whose entry bar is after the cutoff IS the cutoff strategy."""
    base_p = dict(C221, be_after_R=1.0)
    for label, params in (("be=1.0", base_p), ("be=0 (champion)", C221)):
        strategy = "ORB_3_6.py"
        _, tr, b = run(strategy, params, None, IS_END)
        _, trlb, blb = run(strategy, params, IS_END, LB_END)
        idx, idxlb = b["index"], blb["index"]
        print("\n=== ENTRY-TIME CUTOFF on %s ===" % label)
        print("%-14s | %5s %10s %5s %8s | %4s %9s %5s" %
              ("cutoff (ET)", "IS n", "IS net", "IS PF", "IS MAR", "LB n", "LB net", "LB PF"))
        for cut in ("16:00", "15:00", "14:00", "13:00", "12:00", "11:30", "11:00", "10:30"):
            hh, mm = map(int, cut.split(":"))
            lim = hh * 60 + mm
            keep = [t[2] for t in tr
                    if idx[t[0]].hour * 60 + idx[t[0]].minute < lim]
            keeplb = [t[2] for t in trlb
                      if idxlb[t[0]].hour * 60 + idxlb[t[0]].minute < lim]
            i, l = score(keep), score(keeplb)
            print("%-14s | %5d %10s %5.2f %8.2f | %4d %9s %5.2f" % (
                "< " + cut, i["n"], "${:,.0f}".format(i["net"]), min(i["pf"], 9.99),
                min(i["mar"], 99), l["n"], "${:,.0f}".format(l["net"]), min(l["pf"], 9.99)))


def sweep_side():
    """Item #414: long/short split of the champion (First-candle dir picks the side;
    this reads whether one side is deadweight, as item D claimed on the leaky base)."""
    for be in (0.0, 1.0):
        p = dict(C221, be_after_R=be)
        _, tr, b = run("ORB_3_6.py", p, None, IS_END)
        _, trlb, _ = run("ORB_3_6.py", p, IS_END, LB_END)
        for side, name in ((1, "LONG"), (-1, "SHORT")):
            i = score([t[2] for t in tr if t[3] == side])
            l = score([t[2] for t in trlb if t[3] == side])
            print("be=%.1f %-5s | IS n=%4d net=%10s PF=%.2f | LB n=%3d net=%9s PF=%.2f" % (
                be, name, i["n"], "${:,.0f}".format(i["net"]), min(i["pf"], 9.99),
                l["n"], "${:,.0f}".format(l["net"]), min(l["pf"], 9.99)))


def sweep_beneighbors():
    """Does be~1.0 help config NEIGHBORS too, or only the exact champion? A lever
    that only works on one point is curve-fit; a real lever helps the region."""
    neighbors = [
        ("champion", {}),
        ("stop 1.75", dict(stop_frac=1.75)),
        ("stop 1.5", dict(stop_frac=1.5)),
        ("trail 5", dict(trail_bars=5)),
        ("partial 2.5", dict(partial_exit_R=2.5)),
        ("target 5.0", dict(target_R=5.0)),
        ("or_bars 3", dict(or_bars=3)),
        ("buf 0.20", dict(breakout_buf=0.20)),
    ]
    print("%-14s | %-10s %10s %8s %8s | %10s %8s %8s" %
          ("neighbor", "window", "be=0 net", "be0 DD", "be0 MAR", "be=1 net", "be1 DD", "be1 MAR"))
    for name, delta in neighbors:
        p0 = dict(C221, **delta)
        p1 = dict(C221, be_after_R=1.0, **delta)
        f0 = row("x", p0, "ORB_3_6.py")["FULL"]
        f1 = row("x", p1, "ORB_3_6.py")["FULL"]
        print("%-14s | %-10s %10s %8s %8.2f | %10s %8s %8.2f" % (
            name, "FULL", "${:,.0f}".format(f0["net"]), "${:,.0f}".format(f0["dd"]), f0["mar"],
            "${:,.0f}".format(f1["net"]), "${:,.0f}".format(f1["dd"]), f1["mar"]))


def _daily_frame():
    """Per-session daily OHLC from the 5m master (for prior-day pattern features)."""
    b = bars()
    idx = b["index"]
    df = pd.DataFrame(dict(date=idx.date, h=b["high"], l=b["low"],
                           o=b["open"], c=b["close"]))
    d = df.groupby("date").agg(o=("o", "first"), h=("h", "max"),
                               l=("l", "min"), c=("c", "last"))
    d["rng"] = d["h"] - d["l"]
    return d


def sweep_tilts():
    """Items #416/X15: NR7 / inside-day size tilts + prior-day-structure buckets on
    the be=1.0 candidate. All features are PRIOR-day (causal). A tilt multiplies
    size on flagged days; capital-matched by scaling so avg size stays 1.0."""
    d = _daily_frame()
    dates = list(d.index)
    pos = {dt: i for i, dt in enumerate(dates)}
    rng = d["rng"].values
    hi, lo = d["h"].values, d["l"].values

    # prior-day flags, aligned to TRADE day t (computed from day t-1 and earlier)
    nr7, inside = {}, {}
    for i in range(7, len(dates)):
        nr7[dates[i]] = rng[i - 1] <= rng[max(0, i - 7):i].min() + 1e-12
        inside[dates[i]] = (hi[i - 1] <= hi[i - 2]) and (lo[i - 1] >= lo[i - 2])

    p = dict(C221, be_after_R=1.0)
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        _, tr, b = run("ORB_3_6.py", p, f, t_)
        idx = b["index"]
        trades = [(idx[t[0]].date(), t[2]) for t in tr]
        for name, flags in (("NR7", nr7), ("inside-day", inside)):
            on = [x for dt_, x in trades if flags.get(dt_, False)]
            off = [x for dt_, x in trades if not flags.get(dt_, False)]
            so, sf = score(on), score(off)
            print("%s %-11s | flagged n=%4d avg=%7s PF=%.2f | rest n=%4d avg=%7s PF=%.2f" % (
                win, name, so["n"], "${:,.0f}".format(so["avg"]), min(so["pf"], 9.99),
                sf["n"], "${:,.0f}".format(sf["avg"]), min(sf["pf"], 9.99)))
        # capital-matched tilt read: does upsizing flagged days lift MAR?
        for name, flags, mult_on in (("NR7 x1.25", nr7, 1.25), ("ID x1.25", inside, 1.25),
                                     ("NR7 x1.5", nr7, 1.5), ("ID x1.5", inside, 1.5)):
            w = np.array([mult_on if flags.get(dt_, False) else 1.0 for dt_, _ in trades])
            if not len(w):
                continue
            w = w / w.mean()          # capital-matched
            pnl = np.array([x for _, x in trades])
            pd_ = (pnl - COST_PTS) * MULT * w
            cum = np.cumsum(pd_); ddv = float((cum - np.maximum.accumulate(cum)).min())
            base = (pnl - COST_PTS) * MULT
            cb = np.cumsum(base); db = float((cb - np.maximum.accumulate(cb)).min())
            print("   %s tilt %-9s: net %11s (base %11s)  MAR %6.2f (base %6.2f)" % (
                win, name, "${:,.0f}".format(pd_.sum()), "${:,.0f}".format(base.sum()),
                pd_.sum() / abs(ddv) if ddv else 99, base.sum() / abs(db) if db else 99))


def sweep_conditions():
    """Session-level condition buckets on the be=1.0 candidate. Every feature is
    known AT 09:30 (gap, day-of-week, prior-day trend) or when the OR completes
    (OR width pctile), and each deletes WHOLE sessions — so drop-the-trade is an
    EXACT emulation of the filter. Diagnostic first: only a monotone, both-window
    toxic bucket justifies a knob."""
    d = _daily_frame()
    dates = list(d.index)
    dpos = {dt: i for i, dt in enumerate(dates)}
    rng, hi, lo, cl, op = d["rng"].values, d["h"].values, d["l"].values, d["c"].values, d["o"].values

    # trailing 20-day ATR for gap normalization (prior days only)
    atr20 = np.full(len(dates), np.nan)
    for i in range(1, len(dates)):
        a = max(0, i - 20)
        atr20[i] = rng[a:i].mean() if i > a else np.nan

    p = dict(C221, be_after_R=1.0)
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        _, tr, b = run("ORB_3_6.py", p, f, t_)
        idx = b["index"]
        rows_ = []
        for t in tr:
            dt_ = idx[t[0]].date()
            i = dpos.get(dt_)
            if i is None or i < 21:
                continue
            gap = abs(op[i] - cl[i - 1]) / atr20[i] if atr20[i] > 0 else np.nan
            dow = idx[t[0]].dayofweek
            ptrend = 1 if cl[i - 1] >= op[i - 1] else -1          # prior day up/down
            rows_.append(dict(pnl=t[2], gap=gap, dow=dow, ptrend=ptrend,
                              side=t[3], date=dt_))
        rw = pd.DataFrame(rows_)
        print("\n--- %s (n=%d) ---" % (win, len(rw)))
        # gap buckets
        qs = rw["gap"].quantile([0.33, 0.66]).values
        for name, m in (("gap small", rw["gap"] <= qs[0]),
                        ("gap mid", (rw["gap"] > qs[0]) & (rw["gap"] <= qs[1])),
                        ("gap large", rw["gap"] > qs[1])):
            s = score(rw[m]["pnl"].values)
            print("  %-10s n=%4d avg=%7s PF=%.2f" % (name, s["n"], "${:,.0f}".format(s["avg"]), min(s["pf"], 9.99)))
        # day of week
        for dow, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
            s = score(rw[rw["dow"] == dow]["pnl"].values)
            print("  %-10s n=%4d avg=%7s PF=%.2f" % (name, s["n"], "${:,.0f}".format(s["avg"]), min(s["pf"], 9.99)))
        # prior-day trend vs today's trade side (with/against)
        for name, m in (("with prior", rw["ptrend"] == rw["side"]),
                        ("against", rw["ptrend"] != rw["side"])):
            s = score(rw[m]["pnl"].values)
            print("  %-10s n=%4d avg=%7s PF=%.2f" % (name, s["n"], "${:,.0f}".format(s["avg"]), min(s["pf"], 9.99)))


def _tilt_read(rw, weights, label):
    """Capital-matched tilt: weights is a per-trade array; normalized to mean 1."""
    w = np.asarray(weights, float)
    w = w / w.mean()
    pnl = (rw["pnl"].values - COST_PTS) * MULT * w
    base = (rw["pnl"].values - COST_PTS) * MULT
    def mar(x):
        cum = np.cumsum(x); dd = float((cum - np.maximum.accumulate(cum)).min())
        return (x.sum() / abs(dd) if dd else 99), abs(dd)
    m1, d1 = mar(pnl); m0, d0 = mar(base)
    print("  %-24s net %11s (base %11s)  DD %9s (base %9s)  MAR %6.2f (base %6.2f)" % (
        label, "${:,.0f}".format(pnl.sum()), "${:,.0f}".format(base.sum()),
        "${:,.0f}".format(d1), "${:,.0f}".format(d0), m1, m0))


def sweep_ctilt():
    """Counter-prior-day + day-of-week as capital-matched SIZE TILTS on the be=1.0
    candidate. Tilt, don't cut (the B/M/N/O lesson). A-priori weights, no tuning."""
    d = _daily_frame()
    dates = list(d.index)
    dpos = {dt: i for i, dt in enumerate(dates)}
    cl, op = d["c"].values, d["o"].values

    p = dict(C221, be_after_R=1.0)
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        _, tr, b = run("ORB_3_6.py", p, f, t_)
        idx = b["index"]
        rows_ = []
        for t in tr:
            dt_ = idx[t[0]].date()
            i = dpos.get(dt_)
            if i is None or i < 2:
                continue
            ptrend = 1 if cl[i - 1] >= op[i - 1] else -1
            rows_.append(dict(pnl=t[2], dow=idx[t[0]].dayofweek,
                              against=(ptrend != t[3])))
        rw = pd.DataFrame(rows_)
        print("\n--- %s (n=%d) ---" % (win, len(rw)))
        _tilt_read(rw, np.where(rw["against"], 1.5, 0.75), "against x1.5 / with x0.75")
        _tilt_read(rw, np.where(rw["against"], 1.5, 1.0), "against x1.5 / with x1.0")
        _tilt_read(rw, np.where(rw["against"], 2.0, 0.5), "against x2.0 / with x0.5")
        dw = rw["dow"].map({0: 0.5, 1: 0.75, 2: 1.0, 3: 1.25, 4: 1.5}).values
        _tilt_read(rw, dw, "DOW ramp 0.5..1.5")
        _tilt_read(rw, np.where(rw["dow"] == 0, 0.5, 1.0), "Mon x0.5")
        both = np.where(rw["against"], 1.5, 0.75) * rw["dow"].map(
            {0: 0.5, 1: 0.75, 2: 1.0, 3: 1.25, 4: 1.5}).values
        _tilt_read(rw, both, "against + DOW combo")


def sweep_fade():
    """Item R re-ask: the failed-break fade (ORB_FADE_1_0, entry at the failure
    bar's close = legal). Old verdict 'net-negative everywhere' predates the
    close-confirm era; now the crowned ORB deliberately SKIPS false wicks, so the
    fade would be a non-overlapping companion leg if it works at all."""
    rows = []
    for ob in (1, 2):
        for tR in (0.0, 1.0, 1.5, 2.0):
            for vg in (0.0, 1.25):
                p = dict(or_bars=ob, trade_mode="Both", vol_gate=vg,
                         stop_pad=0.15, target_R=tR)
                rows.append(row("fade or%d tR%.1f vg%.2f" % (ob, tR, vg),
                                p, "ORB_FADE_1_0.py"))
    show(rows, "FAILED-BREAK FADE RE-ASK")


def sweep_orw():
    """Item #413: OR-width percentile buckets on the be=1.0 candidate. ORW is known
    the moment the OR completes (before any entry) and gates whole sessions, so
    dropping trades is an exact emulation."""
    p = dict(C221, be_after_R=1.0)
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        _, tr, b = run("ORB_3_6.py", p, f, t_)
        idx = b["index"]
        # per-session OR width (first 2 bars = or_bars 2) and its prior-20 pctile
        dfb = pd.DataFrame(dict(date=idx.date, h=b["high"], l=b["low"]))
        g = dfb.groupby("date")
        orw = {}
        for dt_, grp in g:
            orw[dt_] = grp["h"].values[:2].max() - grp["l"].values[:2].min()
        dates = sorted(orw)
        pct = {}
        for i, dt_ in enumerate(dates):
            if i < 20:
                continue
            prior = np.array([orw[dates[j]] for j in range(i - 20, i)])
            pct[dt_] = (prior < orw[dt_]).mean()
        rows_ = [(pct.get(idx[t[0]].date()), t[2]) for t in tr]
        rows_ = [(q, x) for q, x in rows_ if q is not None]
        print("\n--- %s (n=%d) ---" % (win, len(rows_)))
        for name, m0, m1 in (("ORW p0-33", 0.0, 1 / 3), ("ORW p33-66", 1 / 3, 2 / 3),
                             ("ORW p66-100", 2 / 3, 1.01)):
            s = score([x for q, x in rows_ if m0 <= q < m1])
            print("  %-12s n=%4d avg=%7s PF=%.2f" % (name, s["n"], "${:,.0f}".format(s["avg"]), min(s["pf"], 9.99)))


def sweep_ens():
    """Item #410 (old item E) on the legal base: a 2-lot ensemble = lot A ride+BE
    to target, lot B trailed from entry. Entry logic is identical across exit
    configs (exits never affect the entry bar), so blending two runs' per-session
    PnLs 50/50 IS the 2-lot book, exactly — no new strategy code needed."""
    legs = {
        "champion+be (partial3+trail3)": dict(C221, be_after_R=1.0),
        "A ride+BE (no trail, tgt 5.5)": dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0),
        "B trail-from-entry (trail 3)":  dict(C221, be_after_R=1.0, partial_exit_R=0.0, target_R=0.0, trail_bars=3),
        "B5 trail-from-entry (trail 5)": dict(C221, be_after_R=1.0, partial_exit_R=0.0, target_R=0.0, trail_bars=5),
    }
    out = {}
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        res = {}
        for name, p in legs.items():
            _, tr, b = run("ORB_3_6.py", p, f, t_)
            res[name] = {b["index"][t[0]].date(): t[2] for t in tr}
        out[win] = res
        print("\n--- %s ---" % win)
        for name in legs:
            s = score(list(res[name].values()))
            print("  %-30s n=%4d net=%11s PF=%.2f DD=%9s MAR=%6.2f" % (
                name, s["n"], "${:,.0f}".format(s["net"]), min(s["pf"], 9.99),
                "${:,.0f}".format(s["dd"]), s["mar"]))
        # blends (same sessions; a session missing from one leg contributes its half)
        for la, lb_ in (("A ride+BE (no trail, tgt 5.5)", "B trail-from-entry (trail 3)"),
                        ("A ride+BE (no trail, tgt 5.5)", "B5 trail-from-entry (trail 5)"),
                        ("champion+be (partial3+trail3)", "B trail-from-entry (trail 3)")):
            days = sorted(set(res[la]) | set(res[lb_]))
            blend = [0.5 * res[la].get(d_, 0.0) + 0.5 * res[lb_].get(d_, 0.0) for d_ in days]
            s = score(blend)
            print("  BLEND %-24s n=%4d net=%11s PF=%.2f DD=%9s MAR=%6.2f" % (
                (la.split()[0] + "+" + lb_.split()[0])[:24], s["n"], "${:,.0f}".format(s["net"]),
                min(s["pf"], 9.99), "${:,.0f}".format(s["dd"]), s["mar"]))


def sweep_ridebe():
    """The ens sweep's surprise: ride+BE with NO partial and NO trail beats the
    champion in both windows on fewer knobs. Characterize it: FULL stats, the BE
    plateau, target plateau, and stop plateau — plateaus only, no re-picking."""
    A = dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0)
    rows = [row("champion+be (the queued C1)", dict(C221, be_after_R=1.0), "ORB_3_6.py"),
            row("RIDE+BE (A)", A, "ORB_3_6.py")]
    for be in (0.8, 1.2, 1.5):
        rows.append(row("A be=%.1f" % be, dict(A, be_after_R=be), "ORB_3_6.py"))
    for tR in (4.5, 5.0, 6.0, 0.0):
        rows.append(row("A target=%.1f" % tR, dict(A, target_R=tR), "ORB_3_6.py"))
    for sf in (1.75, 2.25):
        rows.append(row("A stop=%.2f" % sf, dict(A, stop_frac=sf), "ORB_3_6.py"))
    show(rows, "RIDE+BE CHARACTERIZATION")
    print()
    for r in rows:
        print("%-30s %s" % (r["label"], full_line(r)))


def sweep_noise():
    """Item #408 diagnostic (the never-built salvage candidate): bucket the ride+BE
    candidate's trades by the NOISE-style time-of-day profile of their entry bar —
    prior-14-day mean |close-open| at that bar-of-day vs the day's all-bar mean
    (causal: prior sessions only). A monotone, both-window pattern would justify an
    in-loop gate; anything else kills the idea cheaply."""
    b = bars()
    idx = b["index"]
    bod = idx.hour * 60 + idx.minute            # bar-of-day key (ET minutes)
    co = np.abs(b["close"] - b["open"])
    dfb = pd.DataFrame(dict(date=idx.date, bod=bod, co=co))
    # per (date, bod) value → pivot: rows=date, cols=bod
    piv = dfb.pivot_table(index="date", columns="bod", values="co", aggfunc="mean")
    dates = list(piv.index)
    dpos = {dt: i for i, dt in enumerate(dates)}
    vals = piv.values
    # prior-14-day mean per bod, and per-day all-bod mean of that same window
    ratio = np.full_like(vals, np.nan)
    for i in range(14, len(dates)):
        w = np.nanmean(vals[i - 14:i, :], axis=0)          # per-bod noise, prior 14d
        allm = np.nanmean(w)
        if allm > 0:
            ratio[i, :] = w / allm                          # >1 = noisy time of day
    colpos = {c: k for k, c in enumerate(piv.columns)}

    A = dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0)
    for win, (f, t_) in (("IS", (None, IS_END)), ("LB", (IS_END, LB_END))):
        _, tr, bb = run("ORB_3_6.py", A, f, t_)
        bidx = bb["index"]
        rows_ = []
        for t in tr:
            dt_ = bidx[t[0]].date()
            bd = bidx[t[0]].hour * 60 + bidx[t[0]].minute
            i, k = dpos.get(dt_), colpos.get(bd)
            if i is None or k is None or i < 14:
                continue
            r_ = ratio[i, k]
            if r_ == r_:
                rows_.append((r_, t[2]))
        rw = np.array([r_ for r_, _ in rows_])
        qs = np.quantile(rw, [0.25, 0.5, 0.75])
        print("\n--- %s (n=%d) ---" % (win, len(rows_)))
        for name, m0, m1 in (("quietest q1", -1, qs[0]), ("q2", qs[0], qs[1]),
                             ("q3", qs[1], qs[2]), ("noisiest q4", qs[2], 99)):
            s = score([x for r_, x in rows_ if m0 <= r_ < m1])
            print("  %-12s n=%4d avg=%7s PF=%.2f" % (name, s["n"], "${:,.0f}".format(s["avg"]), min(s["pf"], 9.99)))


def sweep_reenter():
    """ORB 3.7: re-entry after a breakeven SCRATCH (not a loss). reenter=0 must
    reproduce the ride+BE candidate exactly (parity check row)."""
    A = dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0)
    rows = [row("ride+BE via 3.6 (parity ref)", A, "ORB_3_6.py")]
    for re_ in (0, 1, 2):
        rows.append(row("3.7 reenter=%d" % re_, dict(A, reenter_scratch=re_), "ORB_3_7.py"))
    show(rows, "RE-ENTRY AFTER BE SCRATCH")
    print()
    for r in rows:
        print("%-30s %s" % (r["label"], full_line(r)))


SWEEPS = {"control": sweep_control, "be": sweep_be, "beyears": sweep_beyears,
          "cutoff": sweep_cutoff, "side": sweep_side, "beneighbors": sweep_beneighbors,
          "tilts": sweep_tilts, "conditions": sweep_conditions, "ctilt": sweep_ctilt,
          "fade": sweep_fade, "orw": sweep_orw, "ens": sweep_ens, "ridebe": sweep_ridebe,
          "noise": sweep_noise, "reenter": sweep_reenter}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "control"
    if which not in SWEEPS:
        print("unknown sweep %r; have: %s" % (which, ", ".join(SWEEPS)))
        sys.exit(1)
    SWEEPS[which]()

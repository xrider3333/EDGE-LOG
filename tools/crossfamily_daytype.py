# -*- coding: utf-8 -*-
"""
CROSS-FAMILY DAY-TYPE FILTER — does NOISE's prior-day close-position filter transfer
to ORB (the standing crown, run #234) and to ENGU-Q (the RTH champion, run #149/#227)?

Round log + pre-registered adoption bar: CROSSFAMILY_DAYTYPE.md (repo root).

Ground rules baked in here:
  * WINDOWS ARE PINNED to each family's own crowned run, never "last N days of
    whatever synced".
  * BOTH families' lockboxes are ALREADY SPENT (ORB's 2025-08-13..2026-08-13 has been
    read many times; ENGU-Q's trailing year likewise). They are printed as a
    confirmatory column and are never used to select anything.
  * The filter is implemented IN-ENGINE, never as a post-hoc trade-list filter,
    because vetoing an entry can free a later signal in the same session (NOISE's
    "ADDED trades" lesson).

Usage:
    python tools/crossfamily_daytype.py control     # reproduce both crowns
    python tools/crossfamily_daytype.py orb         # ORB: 4 modes x 3 thresholds
    python tools/crossfamily_daytype.py enguq       # ENGU-Q: same
    python tools/crossfamily_daytype.py attrib      # PnL attribution on both families
    python tools/crossfamily_daytype.py years       # year-by-year deltas
    python tools/crossfamily_daytype.py all
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# masters are gitignored, so a worktree checkout falls back to the desktop checkout
_UPLOADS = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UPLOADS):
    _UPLOADS = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

COST_PTS = 0.533          # $5.66 commission / 20 + 0.25 pt slippage
MULT = 20.0               # NQ $/point

# ── families ─────────────────────────────────────────────────────────────────────
# window ends are each family's own crowned run's windows.
FAMILIES = {
    "orb": dict(
        master="NOADJ_NQ_5m_RTH.csv",
        strategy="ORB_3_8.py",
        parent="ORB_3_6.py",
        sel_end="2025-08-12",          # run #234 optimize window end
        lb_end="2026-08-13",           # run #234 lockbox end (SPENT)
        params=dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0,
                    breakout_buf=0.25, close_confirm=True, partial_exit_R=0.0,
                    trail_bars=0, target_R=5.5, be_after_R=1.0, atr_filter=0.7,
                    vpace_filter=0.7, flat_eod=True, skip_holidays=True),
        expect="run #234 (ORB_3_6_C2): n=2607 net=$389,874 PF=1.307 DD=$29,142 MAR=13.38",
        long_only=False,
    ),
    "enguq": dict(
        master="NOADJ_NQ_1m_RTH.csv",
        strategy="ENGUQ_1M_DT_1_0.py",
        parent="ENGUQ_1M_1_0.py",
        sel_end="2025-06-30",
        lb_end="2026-06-30",           # 1m RTH master has a real hole after 2026-07-16
        params=dict(tl_len=48, ema_len=390, regime_len=0, buf_atr=0.9, min_brk=1.3,
                    atr_len=30, vol_mult=0.8, stop_mult=1.0, act_R=2.5,
                    trail_frac=2.5, breakeven_R=1.5),
        expect="run #149/#227 config: n=2048 net=$477,520",
        long_only=True,
    ),
}

MODES = ["skip_bot_short", "skip_bot_all", "skip_top_long", "skip_top_all"]
LO_GRID = [0.15, 0.20, 0.25]
HI_GRID = [0.85, 0.80, 0.75]


# ── data ─────────────────────────────────────────────────────────────────────────
_BARS = {}


def bars(fam):
    if fam in _BARS:
        return _BARS[fam]
    df = pd.read_csv(os.path.join(_UPLOADS, FAMILIES[fam]["master"]))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    _BARS[fam] = dict(
        open=df["open"].values.astype(float), high=df["high"].values.astype(float),
        low=df["low"].values.astype(float), close=df["close"].values.astype(float),
        volume=df["volume"].values.astype(float) if "volume" in df.columns else None,
        day_id=df["day_id"].values, index=pd.DatetimeIndex(df["_dt"]),
    )
    return _BARS[fam]


def slice_bars(fam, date_from=None, date_to=None):
    b = bars(fam)
    idx = b["index"]
    m = np.ones(len(idx), bool)
    if date_from:
        m &= (idx.date >= pd.Timestamp(date_from).date())
    if date_to:
        m &= (idx.date <= pd.Timestamp(date_to).date())
    out = {k: v[m] for k, v in b.items() if v is not None}
    out["day_id"] = pd.factorize(pd.Series(out["index"]).dt.date)[0]
    return out


_MODS = {}


def strat(name):
    if name in _MODS:
        return _MODS[name]
    path = os.path.join(ROOT, "augur_strategies", name)
    spec = importlib.util.spec_from_file_location("_cfdt_" + name.replace(".", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


# ── scoring ──────────────────────────────────────────────────────────────────────
def score(trades_pts):
    """Net-dollar stats from RAW (pre-cost) point PnLs. MaxDD printed POSITIVE."""
    p = np.asarray(list(trades_pts), float)
    if not len(p):
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, mar=0.0, wr=0.0, avg=0.0)
    p = (p - COST_PTS) * MULT
    wins, losses = p[p > 0], p[p < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    net = float(p.sum())
    return dict(n=len(p), net=net, pf=(gw / gl if gl > 1e-9 else float("inf")),
                dd=dd, mar=(net / dd if dd else float("inf")),
                wr=100.0 * len(wins) / len(p), avg=net / len(p))


def run(fam, params, date_from=None, date_to=None, strategy=None):
    """Backtest one config on one window. Returns (stats, trades, bars_slice)."""
    f = FAMILIES[fam]
    b = slice_bars(fam, date_from, date_to)
    mod = strat(strategy or f["strategy"])
    r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"],
                         volumes=b.get("volume"), day_id=b["day_id"],
                         return_trades=True, **params)
    if not r:
        return score([]), [], b
    tr = r.get("trades") or []
    return score([t[2] for t in tr]), tr, b


def row(fam, label, extra=None):
    """One SELECTION + LOCKBOX + FULL reading for a config."""
    f = FAMILIES[fam]
    p = dict(f["params"], **(extra or {}))
    sel, _, _ = run(fam, p, None, f["sel_end"])
    lb_start = str((pd.Timestamp(f["sel_end"]) + pd.Timedelta(days=1)).date())
    lb, _, _ = run(fam, p, lb_start, f["lb_end"])
    fu, _, _ = run(fam, p, None, f["lb_end"])
    return dict(label=label, params=p, SEL=sel, LB=lb, FULL=fu)


HDR = ("%-34s | %5s %10s %5s %7s %9s | %10s %6s | %4s %9s %5s" %
       ("config", "n", "SEL net", "PF", "MAR", "SEL DD", "FULL net", "F MAR",
        "LBn", "LB net", "LB PF"))


def show(rows, title=""):
    if title:
        print("\n=== %s ===" % title)
    print(HDR)
    print("-" * len(HDR))
    for r in rows:
        s, l, f = r["SEL"], r["LB"], r["FULL"]
        print("%-34s | %5d %10s %5.2f %7.2f %9s | %10s %6.2f | %4d %9s %5.2f" % (
            r["label"][:34], s["n"], "${:,.0f}".format(s["net"]), min(s["pf"], 9.99),
            min(s["mar"], 999), "${:,.0f}".format(s["dd"]),
            "${:,.0f}".format(f["net"]), min(f["mar"], 999),
            l["n"], "${:,.0f}".format(l["net"]), min(l["pf"], 9.99)))


# ── sweeps ───────────────────────────────────────────────────────────────────────
def sweep_control():
    """Reproduce both crowns through the forked files with the filter OFF."""
    for fam in ("orb", "enguq"):
        f = FAMILIES[fam]
        r = row(fam, "%s crown (filter OFF)" % fam.upper())
        show([r], "CONTROL — %s" % fam.upper())
        fu = r["FULL"]
        print("\nFULL %s..%s  n=%d net=%s PF=%.3f DD=%s MAR=%.2f WR=%.1f%%" % (
            "2010-06-07", f["lb_end"], fu["n"], "${:,.0f}".format(fu["net"]),
            fu["pf"], "${:,.0f}".format(fu["dd"]), fu["mar"], fu["wr"]))
        print("expected: %s" % f["expect"])


def _mode_rows(fam):
    f = FAMILIES[fam]
    rows = [row(fam, "CROWN (filter OFF)")]
    for mode in MODES:
        if f["long_only"] and mode == "skip_bot_short":
            continue                       # structural no-op, proven in the smoke test
        grid = LO_GRID if mode.startswith("skip_bot") else HI_GRID
        key = "daytype_lo" if mode.startswith("skip_bot") else "daytype_hi"
        for thr in grid:
            rows.append(row(fam, "%s @%.2f" % (mode, thr),
                            {"daytype_mode": mode, key: thr}))
    return rows


def sweep_orb():
    rows = _mode_rows("orb")
    show(rows, "ORB (run #234 crown) — 4 modes x 3 thresholds")
    _verdicts("orb", rows)


def sweep_enguq():
    rows = _mode_rows("enguq")
    show(rows, "ENGU-Q (run #149/#227 RTH champion) — 3 live modes x 3 thresholds")
    print("\nNOTE: skip_bot_short is omitted — ENGU-Q is LONG-ONLY, so it is a")
    print("      structural no-op (asserted bit-identical in the fork's smoke test).")
    _verdicts("enguq", rows)


def _verdicts(fam, rows):
    base = rows[0]
    bs, bf = base["SEL"], base["FULL"]
    print("\n--- pre-registered bar, gates 1+2 (SELECTION window only) ---")
    print("%-34s %12s %10s   %s" % ("config", "d net $", "d MAR", "gates 1+2"))
    for r in rows[1:]:
        s = r["SEL"]
        dn, dm = s["net"] - bs["net"], s["mar"] - bs["mar"]
        ok = (dn >= 0) and (dm >= 0)
        print("%-34s %12s %10.2f   %s" % (
            r["label"][:34], "${:+,.0f}".format(dn), dm, "PASS" if ok else "fail"))
    print("(FULL-window delta for reference only — the lockbox is SPENT on both families)")
    for r in rows[1:]:
        print("   %-34s full d net %s" % (
            r["label"][:34], "${:+,.0f}".format(r["FULL"]["net"] - bf["net"])))


def _year_map(fam, params, end):
    _, tr, b = run(fam, params, None, end)
    idx = b["index"]
    out = {}
    for t in tr:
        out.setdefault(idx[t[0]].year, []).append(t[2])
    return out


def sweep_years():
    """Year-by-year net for the crown and each mode at its researched threshold."""
    for fam in ("orb", "enguq"):
        f = FAMILIES[fam]
        base = _year_map(fam, f["params"], f["lb_end"])
        yrs = sorted(base)
        print("\n=== %s — year-by-year net $ (full window, filter thresholds 0.20/0.80) ===" % fam.upper())
        cols = [m for m in MODES if not (f["long_only"] and m == "skip_bot_short")]
        print("%6s %12s | %s" % ("year", "CROWN", " ".join("%14s" % m[:14] for m in cols)))
        maps = {m: _year_map(fam, dict(f["params"], daytype_mode=m), f["lb_end"]) for m in cols}
        better = {m: 0 for m in cols}
        worse = {m: 0 for m in cols}
        for y in yrs:
            bn = score(base[y])["net"]
            cells = []
            for m in cols:
                mn = score(maps[m].get(y, []))["net"]
                d = mn - bn
                if d > 1e-6:
                    better[m] += 1
                elif d < -1e-6:
                    worse[m] += 1
                cells.append("%14s" % "{:+,.0f}".format(d))
            print("%6d %12s | %s" % (y, "${:,.0f}".format(bn), " ".join(cells)))
        print("%6s %12s | %s" % ("+/-", "", " ".join(
            "%14s" % ("%d up / %d dn" % (better[m], worse[m])) for m in cols)))


def _diff(base_tr, var_tr):
    """Removed / added decomposition keyed by (entry_idx, entry_px)."""
    bkey = {(t[0], round(t[4], 4)): t for t in base_tr}
    vkey = {(t[0], round(t[4], 4)): t for t in var_tr}
    removed = [bkey[k] for k in bkey if k not in vkey]
    added = [vkey[k] for k in vkey if k not in bkey]
    altered = [(bkey[k], vkey[k]) for k in bkey if k in vkey
               and abs(bkey[k][2] - vkey[k][2]) > 1e-9]
    return removed, added, altered


def sweep_attrib():
    """NOISE-style PnL attribution: what drove each mode, and how concentrated is it."""
    for fam in ("orb", "enguq"):
        f = FAMILIES[fam]
        print("\n=== %s — ATTRIBUTION (selection window %s..%s) ===" % (
            fam.upper(), "2010-06-07", f["sel_end"]))
        bs, btr, bb = run(fam, f["params"], None, f["sel_end"])
        cols = [m for m in MODES if not (f["long_only"] and m == "skip_bot_short")]
        print("%-16s %6s %11s %11s %11s %8s %8s  %s" % (
            "mode", "n", "d net $", "d long $", "d short $", "removed", "added",
            "tie-back"))
        for m in cols:
            vs, vtr, _ = run(fam, dict(f["params"], daytype_mode=m), None, f["sel_end"])
            rm, ad, al = _diff(btr, vtr)
            d = vs["net"] - bs["net"]
            dl = (score([t[2] for t in vtr if t[3] > 0])["net"]
                  - score([t[2] for t in btr if t[3] > 0])["net"])
            ds = (score([t[2] for t in vtr if t[3] < 0])["net"]
                  - score([t[2] for t in btr if t[3] < 0])["net"])
            tie = (-score([t[2] for t in rm])["net"] + score([t[2] for t in ad])["net"]
                   + sum((v[2] - b0[2]) * MULT for b0, v in al))
            print("%-16s %6d %11s %11s %11s %8d %8d  %s (%s)" % (
                m, vs["n"], "${:+,.0f}".format(d), "${:+,.0f}".format(dl),
                "${:+,.0f}".format(ds), len(rm), len(ad),
                "OK" if abs(tie - d) < 1.0 else "off",
                "${:+,.0f}".format(tie)))
            if rm:
                rp = sorted((-(t[2] - COST_PTS) * MULT for t in rm), reverse=True)
                top10 = sum(rp[:10])
                print("      removed: total %s | avg %s | 10 best avoidances %s (%s of the delta)" % (
                    "${:+,.0f}".format(sum(rp)), "${:+,.0f}".format(sum(rp) / len(rp)),
                    "${:+,.0f}".format(top10),
                    ("%.0f%%" % (100.0 * top10 / d)) if abs(d) > 1 else "n/a"))


def sweep_buckets():
    """The mechanism, strategy-side but filter-free: bucket every CROWN trade by the
    prior day's close position and read avg $ / PF per bucket, split by side. This is
    what the filter is betting on, shown directly. If the NOISE pattern transferred,
    the bottom bucket's SHORT row would be clearly negative."""
    for fam in ("orb", "enguq"):
        f = FAMILIES[fam]
        _, tr, b = run(fam, f["params"], None, f["lb_end"])
        did = np.asarray(b["day_id"])
        n = len(did)
        sb, a = [], 0
        while a < n:
            bb = a
            while bb < n and did[bb] == did[a]:
                bb += 1
            sb.append((a, bb)); a = bb
        mod = strat(f["strategy"])
        dp = mod._daytype_pos(b["high"], b["low"], b["close"], sb)
        ordm = {a0: si for si, (a0, b0) in enumerate(sb)}
        starts = np.array([a0 for a0, _ in sb])
        rows = []
        for t in tr:
            si = ordm.get(starts[np.searchsorted(starts, t[0], "right") - 1])
            p = dp[si] if si is not None else np.nan
            if p == p:
                rows.append((p, t[2], t[3]))
        print("\n=== %s — CROWN trades bucketed by PRIOR-DAY close position ===" % fam.upper())
        print("(full window; 'bottom' = yesterday closed in the weakest fifth of its own range)")
        print("%-14s %-7s %6s %10s %9s %6s" % ("bucket", "side", "n", "net $", "avg $", "PF"))
        edges = [(0.0, 0.2, "0.0-0.2 weak"), (0.2, 0.4, "0.2-0.4"), (0.4, 0.6, "0.4-0.6"),
                 (0.6, 0.8, "0.6-0.8"), (0.8, 1.01, "0.8-1.0 strong")]
        for lo, hi, name in edges:
            for side, tag in ((None, "both"), (1, "long"), (-1, "short")):
                sel = [x for p, x, s in rows if lo <= p < hi and (side is None or s == side)]
                if not sel:
                    continue
                st = score(sel)
                print("%-14s %-7s %6d %10s %9s %6.2f" % (
                    name, tag, st["n"], "${:,.0f}".format(st["net"]),
                    "${:,.0f}".format(st["avg"]), min(st["pf"], 9.99)))


SWEEPS = {"control": sweep_control, "orb": sweep_orb, "enguq": sweep_enguq,
          "years": sweep_years, "attrib": sweep_attrib, "buckets": sweep_buckets}


def sweep_all():
    for k in ("control", "orb", "enguq", "years", "attrib", "buckets"):
        SWEEPS[k]()


SWEEPS["all"] = sweep_all


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "control"
    if which not in SWEEPS:
        print("unknown sweep %r; have: %s" % (which, ", ".join(SWEEPS)))
        sys.exit(1)
    SWEEPS[which]()

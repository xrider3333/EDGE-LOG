# -*- coding: utf-8 -*-
"""
ENGU-Q DAY-TYPE LEVERS — ROUND 2 (2026-08-22).

The two leads the 2026-08-18 cross-family study (CROSSFAMILY_DAYTYPE.md) banked and
deliberately did not chase:

  LEAD 1  equal-drawdown resize of the strong-close skip (skip_top_long), sized back up
          so selection-window maxDD ~= the baseline's, then compared on net at equal risk.
  LEAD 2  buy-weakness size tilt: bigger size on entries the day after a WEAK close.

Pre-registration: CROSSFAMILY_DAYTYPE.md section "ROUND 2" (committed BEFORE this ran).
Sizing is a POST-PROCESSING OVERLAY on return_trades output — the engine models 1 NQ and
both cost components (commission + slippage) are per contract, so a size-s trade nets
exactly s x the 1-lot netted dollars (fractional view exact; micro view charges MNQ drag).

Usage:
    python tools/enguq_daytype_levers.py control
    python tools/enguq_daytype_levers.py lead1
    python tools/enguq_daytype_levers.py lead2
    python tools/enguq_daytype_levers.py lockbox    # ONE confirmatory look, labelled
    python tools/enguq_daytype_levers.py all
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UPLOADS = os.path.join(ROOT, "augur_uploads")
if not os.path.isfile(os.path.join(_UPLOADS, "NOADJ_NQ_1m_RTH.csv")):
    _UPLOADS = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

COST_PTS = 0.533           # $5.66 RT commission /20 + 0.25 pt slippage, per NQ contract
MULT = 20.0                # NQ $/pt
MNQ_MULT = 2.0             # MNQ $/pt
MNQ_COST_D = 1.98          # $ per micro RT: $1.48 commission + 0.25 pt x $2 slippage
SEL_END = "2025-06-30"     # run #149/#227 selection window end (pinned)
LB_END = "2026-06-30"      # spent lockbox end (1m master hole after 2026-07-16)
CAP = 1.50                 # pre-registered sizing cap

P149 = dict(tl_len=48, ema_len=390, regime_len=0, buf_atr=0.9, min_brk=1.3,
            atr_len=30, vol_mult=0.8, stop_mult=1.0, act_R=2.5,
            trail_frac=2.5, breakeven_R=1.5)

HI_GRID = [0.85, 0.80, 0.75]
LO_GRID = [0.15, 0.20, 0.25]
TILT_GRID = [1.5, 2.0]


# ── data / engine ────────────────────────────────────────────────────────────────
_B = {}


def bars(date_from=None, date_to=None):
    key = (date_from, date_to)
    if key in _B:
        return _B[key]
    if "raw" not in _B:
        df = pd.read_csv(os.path.join(_UPLOADS, "NOADJ_NQ_1m_RTH.csv"))
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        _B["raw"] = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = _B["raw"]
    m = np.ones(len(df), bool)
    d = df["_dt"].dt.date
    if date_from:
        m &= (d >= pd.Timestamp(date_from).date()).values
    if date_to:
        m &= (d <= pd.Timestamp(date_to).date()).values
    sl = df[m]
    out = dict(open=sl["open"].values.astype(float), high=sl["high"].values.astype(float),
               low=sl["low"].values.astype(float), close=sl["close"].values.astype(float),
               volume=sl["volume"].values.astype(float),
               day_id=pd.factorize(sl["_dt"].dt.date)[0],
               index=pd.DatetimeIndex(sl["_dt"]))
    _B[key] = out
    return out


_MOD = None


def mod():
    global _MOD
    if _MOD is None:
        path = os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_DT_1_0.py")
        spec = importlib.util.spec_from_file_location("_eqdt", path)
        _MOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_MOD)
    return _MOD


def run(extra=None, date_to=SEL_END, date_from=None):
    b = bars(date_from, date_to)
    r = mod().run_backtest(b["open"], b["high"], b["low"], b["close"],
                           volumes=b["volume"], day_id=b["day_id"],
                           return_trades=True, **dict(P149, **(extra or {})))
    return (r.get("trades") or []) if r else [], b


def dollars(t, size=1.0):
    """Netted $ for one trade at fractional NQ size (exact: costs are per contract)."""
    return size * (t[2] - COST_PTS) * MULT


def stats(dl):
    dl = np.asarray(list(dl), float)
    if not len(dl):
        return dict(n=0, net=0.0, dd=0.0, mar=0.0, pf=0.0)
    cum = np.cumsum(dl)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    w, l = dl[dl > 0], dl[dl < 0]
    net = float(dl.sum())
    return dict(n=len(dl), net=net, dd=dd, mar=(net / dd if dd else float("inf")),
                pf=(float(w.sum()) / max(-float(l.sum()), 1e-9)))


def years_of(trades, b, sizes=None):
    out = {}
    for i, t in enumerate(trades):
        s = 1.0 if sizes is None else sizes[i]
        out.setdefault(b["index"][t[0]].year, 0.0)
        out[b["index"][t[0]].year] += dollars(t, s)
    return out


def prior_pos_per_trade(trades, b):
    """Prior-session close position for each trade's entry session (causal)."""
    did = np.asarray(b["day_id"]); n = len(did)
    sb, a = [], 0
    while a < n:
        e = a
        while e < n and did[e] == did[a]:
            e += 1
        sb.append((a, e)); a = e
    dp = mod()._daytype_pos(b["high"], b["low"], b["close"], sb)
    starts = np.array([x for x, _ in sb])
    return [dp[np.searchsorted(starts, t[0], "right") - 1] for t in trades]


def fmt(x):
    return "${:+,.0f}".format(x) if x < 0 else "${:,.0f}".format(x)


# ── control ──────────────────────────────────────────────────────────────────────
def control():
    tr, b = run(date_to=LB_END)
    st = stats([dollars(t) for t in tr])
    print("CONTROL full window 2010-06-07..%s: n=%d net=%s DD=%s PF=%.3f" % (
        LB_END, st["n"], fmt(st["net"]), fmt(st["dd"]), st["pf"]))
    print("expected: n=2048 net=$477,520 (run #149/#227)")
    ts, _ = run(date_to=SEL_END)
    ss = stats([dollars(t) for t in ts])
    print("SELECTION 2010-06-07..%s: n=%d net=%s DD=%s MAR=%.2f" % (
        SEL_END, ss["n"], fmt(ss["net"]), fmt(ss["dd"]), ss["mar"]))
    ok = st["n"] == 2048 and abs(st["net"] - 477520) < 2
    print("PARITY: %s" % ("PASS" if ok else "FAIL — REFUSING TO PROCEED"))
    return ok


# ── LEAD 1: equal-drawdown resize of skip_top_long ──────────────────────────────
def lead1():
    btr, bb = run()
    base = stats([dollars(t) for t in btr])
    byrs = years_of(btr, bb)
    bworst = min(byrs.values())
    print("=== LEAD 1 — equal-DD resize of skip_top_long (selection %s) ===" % SEL_END)
    print("baseline: n=%d net=%s DD=%s MAR=%.2f | worst year %s (%d)" % (
        base["n"], fmt(base["net"]), fmt(base["dd"]), base["mar"], fmt(bworst),
        min(byrs, key=byrs.get)))
    for hi in HI_GRID:
        vtr, vb = run({"daytype_mode": "skip_top_long", "daytype_hi": hi})
        v1 = stats([dollars(t) for t in vtr])
        s = min(CAP, base["dd"] / v1["dd"]) if v1["dd"] else CAP
        vs = stats([dollars(t, s) for t in vtr])
        # integer views
        k = int(round(10 * s))               # micros per 1x-equivalent
        micro = [k * ((t[2] * MNQ_MULT) - MNQ_COST_D) for t in vtr]
        ms = stats(micro)
        vyrs = years_of(vtr, vb, [s] * len(vtr))
        vworst = min(vyrs.values())
        # concentration: add back the 10 most lucrative avoided trades
        vkey = {(t[0], round(t[4], 4)) for t in vtr}
        removed = [t for t in btr if (t[0], round(t[4], 4)) not in vkey]
        removed.sort(key=lambda t: dollars(t))            # most negative first
        add_back = removed[:10]
        adj = sorted(vtr + add_back, key=lambda t: t[0])
        a1 = stats([dollars(t) for t in adj])
        s2 = min(CAP, base["dd"] / a1["dd"]) if a1["dd"] else CAP
        adj_net = s2 * a1["net"]
        g1 = vs["net"] > base["net"]
        g3 = vworst >= bworst - 5000
        g4 = adj_net > base["net"]
        g5 = ms["net"] > base["net"]
        print("\n--- threshold %.2f ---" % hi)
        print(" filtered 1x : n=%d net=%s DD=%s MAR=%.2f PF=%.3f (PF is size-invariant)" % (
            v1["n"], fmt(v1["net"]), fmt(v1["dd"]), v1["mar"], v1["pf"]))
        print(" s = min(%.2f, %s/%s) = %.4f" % (CAP, fmt(base["dd"]), fmt(v1["dd"]), s))
        print(" FRACTIONAL sized: net=%s DD=%s MAR=%.2f  -> gate1 net>base: %s (%s)" % (
            fmt(vs["net"]), fmt(vs["dd"]), vs["mar"], "PASS" if g1 else "fail",
            fmt(vs["net"] - base["net"])))
        print(" worst year sized: %s (%d) vs baseline %s  -> gate3: %s" % (
            fmt(vworst), min(vyrs, key=vyrs.get), fmt(bworst), "PASS" if g3 else "fail"))
        print(" CONCENTRATION: +10 luckiest avoidances back (worth %s at 1x) ->"
              " DD=%s s'=%.4f net'=%s  -> gate4: %s" % (
                  fmt(sum(dollars(t) for t in add_back)), fmt(a1["dd"]), s2,
                  fmt(adj_net), "PASS" if g4 else "fail"))
        print(" INTEGER: nearest whole NQ = %d (s=%.2f) -> %s" % (
            round(s), s, "the unsized round-1 fail" if round(s) == 1 else "%d lots" % round(s)))
        print(" MICRO %d MNQ: net=%s DD=%s MAR=%.2f  (drag %s vs fractional)"
              "  -> gate5 net>base: %s" % (
                  k, fmt(ms["net"]), fmt(ms["dd"]), ms["mar"],
                  fmt(ms["net"] - vs["net"]), "PASS" if g5 else "fail"))
        # per-year deltas vs baseline (sized)
        dels = {y: vyrs.get(y, 0.0) - byrs.get(y, 0.0) for y in sorted(byrs)}
        wy = [y for y, d in dels.items() if d < -5000]
        print(" years worse by >$5k vs baseline: %s" % (
            ", ".join("%d (%s)" % (y, fmt(dels[y])) for y in wy) if wy else "none"))


# ── LEAD 2: buy-weakness size tilt ──────────────────────────────────────────────
def lead2():
    btr, bb = run()
    base = stats([dollars(t) for t in btr])
    byrs = years_of(btr, bb)
    bworst = min(byrs.values())
    pos = prior_pos_per_trade(btr, bb)
    print("=== LEAD 2 — weak-close size tilt (overlay on the champion list, selection %s) ===" % SEL_END)
    print("baseline: n=%d net=%s DD=%s MAR=%.2f | worst year %s" % (
        base["n"], fmt(base["net"]), fmt(base["dd"]), base["mar"], fmt(bworst)))
    for m in TILT_GRID:
        for lo in LO_GRID:
            sizes = [m if (p == p and p <= lo) else 1.0 for p in pos]
            dl = [dollars(t, s) for t, s in zip(btr, sizes)]
            st = stats(dl)
            vyrs = years_of(btr, bb, sizes)
            vworst = min(vyrs.values())
            ntilt = sum(1 for s in sizes if s > 1)
            gain = st["net"] - base["net"]
            extras = sorted(((s - 1.0) * dollars(t) for t, s in zip(btr, sizes) if s > 1),
                            reverse=True)
            top10 = sum(x for x in extras[:10] if x > 0)
            g1 = st["net"] > base["net"]
            g2 = st["mar"] > base["mar"]
            g4 = vworst >= bworst - 5000
            g5 = (gain - top10) > 0
            print("\n m=%.1fx lo=%.2f  (%d of %d trades tilted)" % (m, lo, ntilt, base["n"]))
            print("  net=%s (%s) DD=%s MAR=%.2f PF=%.3f | net:%s MAR:%s" % (
                fmt(st["net"]), fmt(gain), fmt(st["dd"]), st["mar"], st["pf"],
                "PASS" if g1 else "fail", "PASS" if g2 else "fail"))
            print("  worst year %s vs baseline %s -> %s | conc: gain-top10extra=%s -> %s" % (
                fmt(vworst), fmt(bworst), "PASS" if g4 else "fail",
                fmt(gain - top10), "PASS" if g5 else "fail"))
            dels = {y: vyrs.get(y, 0) - byrs.get(y, 0) for y in sorted(byrs)}
            wy = [y for y, d in dels.items() if d < -5000]
            print("  years worse by >$5k: %s" % (
                ", ".join("%d (%s)" % (y, fmt(dels[y])) for y in wy) if wy else "none"))


# ── lockbox: ONE confirmatory look, clearly labelled ────────────────────────────
def lockbox():
    print("=== LOCKBOX (SPENT — confirmatory only, selected nothing) 2025-07-01..%s ===" % LB_END)
    lb_from = "2025-07-01"
    btr, _ = run(date_to=LB_END, date_from=lb_from)
    base = stats([dollars(t) for t in btr])
    print("baseline LB: n=%d net=%s DD=%s" % (base["n"], fmt(base["net"]), fmt(base["dd"])))
    # lead 1 at each threshold, with s derived from the SELECTION window only
    bsel, _ = run()
    bdd = stats([dollars(t) for t in bsel])["dd"]
    for hi in HI_GRID:
        vsel, _ = run({"daytype_mode": "skip_top_long", "daytype_hi": hi})
        s = min(CAP, bdd / stats([dollars(t) for t in vsel])["dd"])
        vtr, _ = run({"daytype_mode": "skip_top_long", "daytype_hi": hi},
                     date_to=LB_END, date_from=lb_from)
        st = stats([dollars(t, s) for t in vtr])
        print("lead1 @%.2f sized %.3fx: n=%d net=%s DD=%s" % (
            hi, s, st["n"], fmt(st["net"]), fmt(st["dd"])))
    # lead 2 cells
    btr_lb, bb_lb = run(date_to=LB_END, date_from=lb_from)
    pos = prior_pos_per_trade(btr_lb, bb_lb)
    for m in TILT_GRID:
        for lo in LO_GRID:
            sizes = [m if (p == p and p <= lo) else 1.0 for p in pos]
            st = stats([dollars(t, s) for t, s in zip(btr_lb, sizes)])
            print("lead2 m=%.1f lo=%.2f: net=%s DD=%s" % (m, lo, fmt(st["net"]), fmt(st["dd"])))


CMDS = {"control": control, "lead1": lead1, "lead2": lead2, "lockbox": lockbox}


def _all():
    if control() is False:
        sys.exit(1)
    lead1(); lead2(); lockbox()


CMDS["all"] = _all

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "control"
    CMDS[which]()

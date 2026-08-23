# -*- coding: utf-8 -*-
"""
ORB 0.6-0.8-BAND LONG VETO — round 2 of the day-type work (CROSSFAMILY_DAYTYPE.md).

Round 1's bucket table found the crowned ORB's genuinely bad population: LONG entries
the day after the prior session closed in the 0.6-0.8 band of its own range
(-$103/trade over 252 trades, PF 0.79, full window). This harness tests the
pre-registered veto of exactly that band (`skip_band_long` in ORB_3_8.py).

Pre-registered adoption bar: CROSSFAMILY_DAYTYPE.md section R2.2 — written and
committed BEFORE any of these sweeps ran. Selection window pinned to run #234's own
optimize window (2010-06-07 -> 2025-08-12); the lockbox (2025-08-13 -> 2026-08-13)
is SPENT and is read once, confirmatory only.

Usage:
    python tools/orb_daytype_band.py control    # reproduce the crown ($389,874 / 2,607)
    python tools/orb_daytype_band.py buckets    # band x side table, SELECTION window + full
    python tools/orb_daytype_band.py sweep      # the 4 pre-declared band edges + mirrors
    python tools/orb_daytype_band.py years      # per-year deltas vs the crown (gate 4 + 6)
    python tools/orb_daytype_band.py attrib     # attribution + top-10 concentration (gate 5+7)
    python tools/orb_daytype_band.py overlap    # veto-day overlap with the crown's atr_filter
    python tools/orb_daytype_band.py es         # ES transfer, nothing refitted (diagnostic)
    python tools/orb_daytype_band.py all
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_UPLOADS = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UPLOADS):
    _UPLOADS = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

# Windows pinned to run #234's own Firestore doc (read 2026-08-23).
SEL_END = "2025-08-12"
LB_START = "2025-08-13"
LB_END = "2026-08-13"

CROWN = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, breakout_buf=0.25,
             close_confirm=True, partial_exit_R=0.0, trail_bars=0, target_R=5.5,
             be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7, flat_eod=True,
             skip_holidays=True)

INSTR = {
    "nq": dict(master="NOADJ_NQ_5m_RTH.csv", cost=0.533, mult=20.0),
    "es": dict(master="NOADJ_ES_5m_RTH.csv", cost=0.363, mult=50.0),
}

# The four pre-declared band edges (CROSSFAMILY_DAYTYPE.md R2.2).
BANDS = [(0.55, 0.80), (0.60, 0.80), (0.60, 0.85), (0.65, 0.85)]

_BARS, _MOD = {}, {}


def bars(instr):
    if instr in _BARS:
        return _BARS[instr]
    df = pd.read_csv(os.path.join(_UPLOADS, INSTR[instr]["master"]))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    _BARS[instr] = dict(
        open=df["open"].values.astype(float), high=df["high"].values.astype(float),
        low=df["low"].values.astype(float), close=df["close"].values.astype(float),
        volume=df["volume"].values.astype(float) if "volume" in df.columns else None,
        index=pd.DatetimeIndex(df["_dt"]),
    )
    return _BARS[instr]


def slice_bars(instr, date_from=None, date_to=None):
    b = bars(instr)
    idx = b["index"]
    m = np.ones(len(idx), bool)
    if date_from:
        m &= (idx.date >= pd.Timestamp(date_from).date())
    if date_to:
        m &= (idx.date <= pd.Timestamp(date_to).date())
    out = {k: (v[m] if v is not None else None) for k, v in b.items()}
    out["day_id"] = pd.factorize(pd.Series(out["index"]).dt.date)[0]
    return out


def strat():
    if "m" not in _MOD:
        path = os.path.join(ROOT, "augur_strategies", "ORB_3_8.py")
        spec = importlib.util.spec_from_file_location("_orbband", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD["m"] = mod
    return _MOD["m"]


def score(trades_pts, instr="nq"):
    c, mult = INSTR[instr]["cost"], INSTR[instr]["mult"]
    p = np.asarray(list(trades_pts), float)
    if not len(p):
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, mar=0.0, wr=0.0, avg=0.0)
    p = (p - c) * mult
    wins, losses = p[p > 0], p[p < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    net = float(p.sum())
    return dict(n=len(p), net=net, pf=(gw / gl if gl > 1e-9 else float("inf")),
                dd=dd, mar=(net / dd if dd else float("inf")),
                wr=100.0 * len(wins) / len(p), avg=net / len(p))


def run(params, date_from=None, date_to=None, instr="nq"):
    b = slice_bars(instr, date_from, date_to)
    r = strat().run_backtest(b["open"], b["high"], b["low"], b["close"],
                             volumes=b["volume"], day_id=b["day_id"],
                             return_trades=True, **params)
    tr = (r or {}).get("trades") or []
    return score([t[2] for t in tr], instr), tr, b


def band_params(lo, hi, mode="skip_band_long"):
    return dict(CROWN, daytype_mode=mode, daytype_band_lo=lo, daytype_band_hi=hi)


def hdr(title):
    print("\n=== %s ===" % title)


def line(label, s):
    print("%-34s n=%5d  net=%11s  PF=%5.2f  DD=%9s  MAR=%6.2f" % (
        label[:34], s["n"], "${:,.0f}".format(s["net"]), min(s["pf"], 9.99),
        "${:,.0f}".format(s["dd"]), min(s["mar"], 999)))


# ── sweeps ───────────────────────────────────────────────────────────────────────
def sweep_control():
    hdr("CONTROL — reproduce run #234 through ORB_3_8 (filter OFF)")
    fu, _, _ = run(CROWN, None, LB_END)
    line("FULL 2010-06-07..%s" % LB_END, fu)
    print("expected: n=2607 net=$389,874 PF=1.307 DD=$29,142 MAR=13.38")
    ok = fu["n"] == 2607 and abs(fu["net"] - 389874) < 1.0
    print("MATCH: %s" % ("PASS" if ok else "FAIL — STOP THE ROUND"))
    sel, _, _ = run(CROWN, None, SEL_END)
    line("SELECTION 2010-06-07..%s" % SEL_END, sel)
    return ok


def _trade_band(tr, b):
    """(prior-day close position, pnl, side) for each trade."""
    did = np.asarray(b["day_id"])
    n = len(did)
    sb, a = [], 0
    while a < n:
        e = a
        while e < n and did[e] == did[a]:
            e += 1
        sb.append((a, e)); a = e
    dp = strat()._daytype_pos(b["high"], b["low"], b["close"], sb)
    starts = np.array([s for s, _ in sb])
    out = []
    for t in tr:
        si = int(np.searchsorted(starts, t[0], "right") - 1)
        p = dp[si]
        if p == p:
            out.append((p, t[2], t[3]))
    return out


def sweep_buckets():
    for win_name, end in (("SELECTION 2010-06-07..%s" % SEL_END, SEL_END),
                          ("FULL 2010-06-07..%s" % LB_END, LB_END)):
        _, tr, b = run(CROWN, None, end)
        rows = _trade_band(tr, b)
        hdr("CROWN trades by PRIOR-DAY close-position band x side — %s" % win_name)
        print("%-16s %-6s %6s %11s %9s %6s" % ("band", "side", "n", "net $", "avg $", "PF"))
        edges = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        for lo, hi in edges:
            for side, tag in ((None, "both"), (1, "long"), (-1, "short")):
                sel = [x for p, x, s in rows if lo <= p < hi and (side is None or s == side)]
                if not sel:
                    continue
                st = score(sel)
                print("%-16s %-6s %6d %11s %9s %6.2f" % (
                    "%.1f-%.1f" % (lo, min(hi, 1.0)), tag, st["n"],
                    "${:,.0f}".format(st["net"]), "${:,.0f}".format(st["avg"]),
                    min(st["pf"], 9.99)))


def sweep_bands():
    hdr("PRE-REGISTERED BAND SWEEP — selection window %s (lockbox NOT consulted)" % SEL_END)
    base, _, _ = run(CROWN, None, SEL_END)
    line("CROWN (veto OFF)", base)
    results = []
    for lo, hi in BANDS:
        s, _, _ = run(band_params(lo, hi), None, SEL_END)
        results.append(((lo, hi), s))
        line("skip_band_long %.2f-%.2f" % (lo, hi), s)
    print("\n--- gates 1+2 (net AND MAR at least the crown's, selection window) ---")
    all_pass = True
    for (lo, hi), s in results:
        dn, dm = s["net"] - base["net"], s["mar"] - base["mar"]
        ok = dn >= 0 and dm >= 0
        all_pass = all_pass and ok
        print("  %.2f-%.2f  d net %12s   d MAR %+7.2f   %s" % (
            lo, hi, "${:+,.0f}".format(dn), dm, "PASS" if ok else "fail"))
    print("gate 3 (plateau, all four edges): %s" % ("PASS" if all_pass else "FAIL"))
    # diagnostics: the symmetric short veto and both-sides veto at the named band
    print("\n--- DIAGNOSTICS (not gates): mirrors at 0.60-0.80 ---")
    for mode in ("skip_band_short", "skip_band_all"):
        s, _, _ = run(band_params(0.60, 0.80, mode), None, SEL_END)
        line(mode + " 0.60-0.80", s)


def sweep_years():
    hdr("YEAR-BY-YEAR vs the crown — selection window (gates 4 + 6)")
    def ymap(params):
        _, tr, b = run(params, None, SEL_END)
        idx = b["index"]
        out = {}
        for t in tr:
            out.setdefault(idx[t[0]].year, []).append(t[2])
        return out
    base = ymap(CROWN)
    var = ymap(band_params(0.60, 0.80))
    up = dn = 0
    early_b = early_v = 0.0
    worst = (None, 0.0)
    for y in sorted(base):
        bn = score(base[y])["net"]
        vn = score(var.get(y, []))["net"]
        d = vn - bn
        if d > 1e-6: up += 1
        elif d < -1e-6: dn += 1
        if y <= 2017:
            early_b += bn; early_v += vn
        if d < worst[1]:
            worst = (y, d)
        print("  %d  crown %12s   veto %12s   d %11s" % (
            y, "${:,.0f}".format(bn), "${:,.0f}".format(vn), "${:+,.0f}".format(d)))
    print("improved years %d / worsened %d  (gate 4 needs improved > worsened)" % (up, dn))
    print("worst single year delta: %s in %s (gate 4 floor -$5,000)" % (
        "${:+,.0f}".format(worst[1]), worst[0]))
    print("early era 2010-2017: crown %s vs veto %s  (gate 6 needs veto >= crown)" % (
        "${:,.0f}".format(early_b), "${:,.0f}".format(early_v)))


def sweep_attrib():
    hdr("ATTRIBUTION + CONCENTRATION — selection window (gates 5 + 7)")
    bs, btr, _ = run(CROWN, None, SEL_END)
    vs, vtr, _ = run(band_params(0.60, 0.80), None, SEL_END)
    bkey = {(t[0], round(t[4], 4)): t for t in btr}
    vkey = {(t[0], round(t[4], 4)): t for t in vtr}
    removed = [bkey[k] for k in bkey if k not in vkey]
    added = [vkey[k] for k in vkey if k not in bkey]
    altered = [(bkey[k], vkey[k]) for k in bkey if k in vkey
               and abs(bkey[k][2] - vkey[k][2]) > 1e-9]
    d = vs["net"] - bs["net"]
    c, mult = INSTR["nq"]["cost"], INSTR["nq"]["mult"]
    tie = (-score([t[2] for t in removed])["net"] + score([t[2] for t in added])["net"]
           + sum((v[2] - b0[2]) * mult for b0, v in altered))
    print("net delta %s | removed %d added %d altered %d | tie-back %s (%s)" % (
        "${:+,.0f}".format(d), len(removed), len(added), len(altered),
        "OK" if abs(tie - d) < 1.0 else "OFF", "${:+,.0f}".format(tie)))
    rm_long = [t for t in removed if t[3] > 0]
    rm_short = [t for t in removed if t[3] < 0]
    print("removed LONG %d worth %s | removed SHORT %d worth %s  (gate 7: gain must be removed longs)" % (
        len(rm_long), "${:,.0f}".format(score([t[2] for t in rm_long])["net"]),
        len(rm_short), "${:,.0f}".format(score([t[2] for t in rm_short])["net"])))
    if removed:
        avoid = sorted((-(t[2] - c) * mult for t in removed), reverse=True)
        top10 = sum(avoid[:10])
        print("10 best avoidances worth %s; delta minus top-10 = %s  (gate 5 needs > 0)" % (
            "${:+,.0f}".format(top10), "${:+,.0f}".format(d - top10)))


def sweep_overlap():
    hdr("OVERLAP with the crown's atr_filter (0.7) — selection window, session level")
    b = slice_bars("nq", None, SEL_END)
    did = np.asarray(b["day_id"])
    h, l, c = b["high"], b["low"], b["close"]
    n = len(did)
    sb, a = [], 0
    while a < n:
        e = a
        while e < n and did[e] == did[a]:
            e += 1
        sb.append((a, e)); a = e
    # atr_filter veto set — same formula as the strategy file
    srng = np.array([h[a:e].max() - l[a:e].min() for a, e in sb], float)
    atr_veto = set()
    for si in range(6, len(sb)):
        recent = srng[max(0, si - 5):si].mean()
        ref = np.median(srng[max(0, si - 60):si])
        if ref > 0 and recent < 0.7 * ref:
            atr_veto.add(si)
    dp = strat()._daytype_pos(h, l, c, sb)
    band = {si for si in range(len(sb)) if dp[si] == dp[si] and 0.60 <= dp[si] < 0.80}
    both = atr_veto & band
    print("sessions in selection window: %d" % len(sb))
    print("atr_filter vetoes the whole session on: %d days" % len(atr_veto))
    print("prior close in the 0.60-0.80 band (band veto active for longs): %d days" % len(band))
    print("overlap (both true): %d days = %.1f%% of band days already killed by atr_filter" % (
        len(both), 100.0 * len(both) / max(1, len(band))))


def sweep_es():
    hdr("ES TRANSFER — nothing refitted (diagnostic; no formal ES bar is banked for ORB)")
    if not os.path.exists(os.path.join(_UPLOADS, INSTR["es"]["master"])):
        print("ES master not found — skipped"); return
    for label, params in (("ES crown config (veto OFF)", CROWN),
                          ("ES + skip_band_long 0.60-0.80", band_params(0.60, 0.80))):
        fu, _, _ = run(params, None, LB_END, instr="es")
        line(label + " FULL", fu)
        se, _, _ = run(params, None, SEL_END, instr="es")
        line(label + " SEL", se)
    print("context: #230 crown certified ES PF 1.032; #234's recorded ES preview PF 1.051.")


def sweep_lockbox():
    hdr("LOCKBOX %s..%s — SPENT, CONFIRMATORY ONLY, read once, selects nothing" % (LB_START, LB_END))
    for label, params in (("crown", CROWN), ("skip_band_long 0.60-0.80", band_params(0.60, 0.80))):
        s, _, _ = run(params, LB_START, LB_END)
        line(label, s)


SWEEPS = {"control": sweep_control, "buckets": sweep_buckets, "sweep": sweep_bands,
          "years": sweep_years, "attrib": sweep_attrib, "overlap": sweep_overlap,
          "es": sweep_es, "lockbox": sweep_lockbox}


def sweep_all():
    if not sweep_control():
        sys.exit(1)
    for k in ("buckets", "sweep", "years", "attrib", "overlap"):
        SWEEPS[k]()


SWEEPS["all"] = sweep_all


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "control"
    if which not in SWEEPS:
        print("unknown sweep %r; have: %s" % (which, ", ".join(SWEEPS)))
        sys.exit(1)
    SWEEPS[which]()

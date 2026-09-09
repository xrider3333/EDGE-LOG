"""
ORB ROUND 11 -- RNG fork sweep driver (2026-09-09).

Sweeps ORB_3_6_RNG.py's opening-range YARDSTICK knobs (rng_mode, rng_blend,
rng_atr_mult, rng_level_mode, rng_scope) on top of the #314 crown, one run per
config on the WHOLE master (identical warm-up / filter history everywhere),
sliced by date afterwards. Also prints the "wick vs body" diagnostic requested
in the spec: on the 5-year window, the crown's own opening-range distribution
(high-low width vs body width) and the crown's trades bucketed by that ratio.

    python tools/orb_hunt11_rng.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END          # noqa: E402
from tools.orb_hunt3 import robustness                    # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

FIVE_Y_START = "2021-08-13"

# ── the #314 crown, per ROUND11_SPEC.md ───────────────────────────────────────
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
            partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
            breakout_buf=0.25)
CROWN = dict(BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0,
             be_after_R=0.5)

# ── main grid ("all" scope: new width feeds buffer + stop/target/BE together) ──
BLEND_VALS = [0.0, 0.25, 0.5, 0.75]
ATR_VALS = [0.5, 1.0, 1.5]
LEVELS = ["hl", "body"]

CONFIGS = [("CROWN (#314)", {})]
CONFIGS.append(("hl / lvl=body", dict(rng_level_mode="body")))
for lvl in LEVELS:
    CONFIGS.append(("body / lvl=%s" % lvl, dict(rng_mode="body", rng_level_mode=lvl)))
for b in BLEND_VALS:
    for lvl in LEVELS:
        CONFIGS.append(("mid b=%.2f / lvl=%s" % (b, lvl),
                        dict(rng_mode="mid", rng_blend=b, rng_level_mode=lvl)))
for m in ATR_VALS:
    for lvl in LEVELS:
        CONFIGS.append(("atr m=%.1f / lvl=%s" % (m, lvl),
                        dict(rng_mode="atr", rng_atr_mult=m, rng_level_mode=lvl)))

# ── "stop_only" variant set: old hl width still feeds the buffer, the new width
#    feeds ONLY stop/target/BE risk. Mirrors every non-hl-width config above. ──
SO_CONFIGS = [("hl / lvl=body [SO]", dict(rng_level_mode="body", rng_scope="stop_only"))]
for lvl in LEVELS:
    SO_CONFIGS.append(("body / lvl=%s [SO]" % lvl,
                        dict(rng_mode="body", rng_level_mode=lvl, rng_scope="stop_only")))
for b in BLEND_VALS:
    for lvl in LEVELS:
        SO_CONFIGS.append(("mid b=%.2f / lvl=%s [SO]" % (b, lvl),
                            dict(rng_mode="mid", rng_blend=b, rng_level_mode=lvl,
                                 rng_scope="stop_only")))
for m in ATR_VALS:
    for lvl in LEVELS:
        SO_CONFIGS.append(("atr m=%.1f / lvl=%s [SO]" % (m, lvl),
                            dict(rng_mode="atr", rng_atr_mult=m, rng_level_mode=lvl,
                                 rng_scope="stop_only")))
# note: [SO] rows are pure book-keeping vs the *matching* "all"-scope row above --
# for "hl / lvl=body" scope makes no difference (width IS hl already either way);
# kept in for completeness / as a zero-diff sanity check.

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        day_id = pd.factorize(df["_dt"].dt.date)[0]
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float), day_id=day_id,
                  index=pd.DatetimeIndex(df["_dt"]))
    return _B


def sessions():
    b = bars()
    idx = b["index"]
    return pd.Series(idx.date).drop_duplicates().values


def trades_of(over):
    """Run the fork ONCE on the whole master; return [(entry_dt, net$)]. Entries
    after LB_END are dropped (never load or report the lockbox here)."""
    b = bars()
    r = strat("ORB_3_6_RNG.py").run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(CROWN, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d <= le:
            out.append((d.tz_localize(None), (t[2] - COST) * MULT))
    return out


def stats(tr, win_start=None):
    """tr = [(entry_dt, net$)] already inside the window."""
    if len(tr) < 5:
        return None
    dts = [d for d, _ in tr]
    p = np.array([x for _, x in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    return dict(n=len(p), net=p.sum(), dd=dd,
                pf=(wins.sum() / abs(losses.sum())) if len(losses) else np.inf,
                mar=(p.sum() / yrs) / dd if dd and yrs > 0 else np.nan,
                evr=evr, ryr=evr * len(p) / yrs if (yrs > 0 and evr == evr) else np.nan,
                tpy=len(p) / yrs if yrs > 0 else np.nan,
                worst12=rob["worst"], win12=rob["win_pct"])


def slice_win(tr, start, end):
    lo = pd.Timestamp(start) if start else None
    hi = pd.Timestamp(end) if end else None
    out = []
    for d, v in tr:
        if lo is not None and d < lo:
            continue
        if hi is not None and d > hi:
            continue
        out.append((d, v))
    return out


WINDOWS = [("FULL", None, LB_END), ("IS", None, IS_END), ("OOS", IS_END, LB_END),
           ("5y", FIVE_Y_START, LB_END)]


def fmt_row(lab, s):
    if s is None:
        return "%-24s   (n<5, skipped)" % lab
    return ("%-24s %5d %12s %11s %6.3f %7.2f %7.3f %7.1f %9.1f %6.1f"
            % (lab, s["n"], "${:,.0f}".format(s["net"]), "${:,.0f}".format(s["dd"]),
               s["pf"], s["mar"], s["evr"], s["ryr"], s["worst12"], s["win12"]))


HDR = ("%-24s %5s %12s %11s %6s %7s %7s %7s %9s %6s"
       % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "worst12", "win12%"))


def gate_check(allw, crown):
    """allw / crown = dict window_label -> stats. Returns (pass_bool, reason_str)."""
    fu, five, oos = allw.get("FULL"), allw.get("5y"), allw.get("OOS")
    if fu is None or five is None or oos is None:
        return False, "insufficient trades in one or more windows"
    c_full, c_5y, c_oos = crown["FULL"], crown["5y"], crown["OOS"]
    reasons = []
    if not (five["mar"] > c_5y["mar"]):
        reasons.append("G1(5y MAR %.2f <= crown %.2f)" % (five["mar"], c_5y["mar"]))
    if not (fu["mar"] > 0.85):
        reasons.append("G1(full MAR %.2f <= 0.85)" % fu["mar"])
    if not (fu["net"] >= 0.95 * c_full["net"]):
        reasons.append("G2(full net %.0f < 95%% of crown %.0f)" % (fu["net"], c_full["net"]))
    if not (oos["net"] >= c_oos["net"]):
        reasons.append("G3(OOS net %.0f < crown %.0f)" % (oos["net"], c_oos["net"]))
    if not (oos["pf"] >= c_oos["pf"]):
        reasons.append("G3(OOS PF %.3f < crown %.3f)" % (oos["pf"], c_oos["pf"]))
    if not (fu["tpy"] >= 120):
        reasons.append("G5(trades/yr %.0f < 120)" % fu["tpy"])
    return (len(reasons) == 0), "; ".join(reasons)


# ── knob-space neighbours for the plateau check (G4) ──────────────────────────
def cfg_of(lab, all_cfgs):
    for l2, over in all_cfgs:
        if l2 == lab:
            return over
    return None


def neighbours(lab, over, all_cfgs):
    mode = over.get("rng_mode", "hl")
    lvl = over.get("rng_level_mode", "hl")
    scope_suffix = " [SO]" if over.get("rng_scope") == "stop_only" else ""
    out = []
    other_lvl = "body" if lvl == "hl" else "hl"
    if mode == "mid":
        b = over.get("rng_blend", 1.0)
        iv = BLEND_VALS.index(b) if b in BLEND_VALS else None
        if iv is not None:
            if iv > 0:
                out.append("mid b=%.2f / lvl=%s%s" % (BLEND_VALS[iv - 1], lvl, scope_suffix))
            if iv < len(BLEND_VALS) - 1:
                out.append("mid b=%.2f / lvl=%s%s" % (BLEND_VALS[iv + 1], lvl, scope_suffix))
        out.append("mid b=%.2f / lvl=%s%s" % (b, other_lvl, scope_suffix))
    elif mode == "atr":
        m = over.get("rng_atr_mult", 0.0)
        iv = ATR_VALS.index(m) if m in ATR_VALS else None
        if iv is not None:
            if iv > 0:
                out.append("atr m=%.1f / lvl=%s%s" % (ATR_VALS[iv - 1], lvl, scope_suffix))
            if iv < len(ATR_VALS) - 1:
                out.append("atr m=%.1f / lvl=%s%s" % (ATR_VALS[iv + 1], lvl, scope_suffix))
        out.append("atr m=%.1f / lvl=%s%s" % (m, other_lvl, scope_suffix))
    elif mode == "body":
        out.append("body / lvl=%s%s" % (other_lvl, scope_suffix))
    else:  # hl
        out.append("hl / lvl=%s%s" % (other_lvl, scope_suffix))
    return [n for n in out if n != lab]


def main():
    out_lines = []

    def emit(s):
        print(s)
        out_lines.append(s)

    emit("=" * 140)
    emit("ORB ROUND 11 -- RNG: how the opening range is MEASURED (ORB_3_6_RNG.py) "
         "-- entries to %s, gates vs #314 crown" % LB_END)
    emit("=" * 140)

    ALL_CFGS = CONFIGS + SO_CONFIGS

    cache = {}
    for lab, over in ALL_CFGS:
        cache[lab] = trades_of(over)

    all_stats = {}   # lab -> {window_label: stats}
    for lab, over in ALL_CFGS:
        all_stats[lab] = {}
        for wlab, wstart, wend in WINDOWS:
            all_stats[lab][wlab] = stats(slice_win(cache[lab], wstart, wend), wstart)

    crown_stats = all_stats["CROWN (#314)"]
    gate_results = {}
    for lab, _ in ALL_CFGS:
        gate_results[lab] = gate_check(all_stats[lab], crown_stats)

    emit("\nMAIN GRID -- new width feeds buffer AND stop/target/BE together (rng_scope=all)")
    for wlab, wstart, wend in WINDOWS:
        emit("\n" + "-" * 140)
        emit("%s window (%s .. %s)" % (wlab, wstart or "start", wend))
        emit(HDR)
        emit("-" * 140)
        for lab, _ in CONFIGS:
            emit(fmt_row(lab, all_stats[lab][wlab]))

    emit("\nSTOP-ONLY VARIANT SET -- buffer keeps the ORIGINAL high-low width; only "
         "stop/target/BE risk uses the new width (rng_scope=stop_only)")
    for wlab, wstart, wend in WINDOWS:
        emit("\n" + "-" * 140)
        emit("%s window (%s .. %s)" % (wlab, wstart or "start", wend))
        emit(HDR)
        emit("-" * 140)
        emit(fmt_row("CROWN (#314)", crown_stats[wlab]))
        for lab, _ in SO_CONFIGS:
            emit(fmt_row(lab, all_stats[lab][wlab]))

    emit("\n" + "=" * 140)
    emit("GATE READ (vs #314 crown; G4 plateau computed separately below)")
    emit("=" * 140)
    for lab, _ in ALL_CFGS:
        ok, reason = gate_results[lab]
        emit("%-26s %-6s %s" % (lab, "PASS" if ok else "FAIL",
             reason if not ok else "all gates clear (G1/G2/G3/G5)"))

    # ── best config overall (excluding crown) by 5y MAR, among rows with all windows ──
    def has_all_windows(lab):
        return all(all_stats[lab][w] is not None for w, _, _ in WINDOWS)

    cands = [(lab, all_stats[lab]["5y"]["mar"]) for lab, _ in ALL_CFGS
             if lab != "CROWN (#314)" and has_all_windows(lab)]
    best_lab, best_mar = (max(cands, key=lambda x: x[1]) if cands else (None, None))
    emit("\nBest config overall by 5y MAR: %s (5y MAR %.2f vs crown %.2f)"
         % (best_lab, best_mar, crown_stats["5y"]["mar"]) if best_lab
         else "\nNo config had trades in every window.")

    # ── plateau check (G4) on the single best config vs its knob-space neighbours ──
    if best_lab:
        over = cfg_of(best_lab, ALL_CFGS)
        nbrs = neighbours(best_lab, over, ALL_CFGS)
        gain_best = best_mar - crown_stats["5y"]["mar"]
        plateau_ok = True
        plateau_notes = []
        for nb in nbrs:
            s = all_stats.get(nb, {}).get("5y")
            if s is None:
                plateau_ok = False
                plateau_notes.append("%s: no trades / not run" % nb)
                continue
            nb_gain = s["mar"] - crown_stats["5y"]["mar"]
            frac = (nb_gain / gain_best) if gain_best > 0 else 0.0
            note = "%s: 5y MAR %.2f (%.0f%% of best's gain)" % (nb, s["mar"], 100 * frac)
            plateau_notes.append(note)
            if gain_best <= 0 or frac < 0.70:
                plateau_ok = False
        emit("\nPLATEAU CHECK (G4) on %s vs neighbours %s:" % (best_lab, nbrs))
        for n in plateau_notes:
            emit("  " + n)
        emit("  G4 = %s" % ("PLATEAU" if plateau_ok else "NOT PLATEAU"))
    else:
        emit("\nPLATEAU CHECK (G4): skipped, no eligible best config.")

    # ── DIAGNOSTIC (not required by spec): wick-vs-body character of the opening
    #    range on the 5-year window, and the crown's own trades bucketed by it. ──
    emit("\n" + "=" * 140)
    emit("DIAGNOSTIC -- crown's opening-range HIGH-LOW width vs BODY width, 5-year window "
         "(%s .. %s)" % (FIVE_Y_START, LB_END))
    emit("=" * 140)

    b = bars()
    o, h, l, c = b["open"], b["high"], b["low"], b["close"]
    did = b["day_id"]
    idx = b["index"]
    n = len(c)
    _sess_bounds = []
    a0 = 0
    while a0 < n:
        b1 = a0
        while b1 < n and did[b1] == did[a0]:
            b1 += 1
        _sess_bounds.append((a0, b1)); a0 = b1

    lo_ts = pd.Timestamp(FIVE_Y_START, tz=idx.tz)
    hi_ts = pd.Timestamp(LB_END, tz=idx.tz)
    OR_BARS = 2
    day_ratio = {}     # day_id start-index -> (hl_width, body_width, ratio)
    for (a, bnd) in _sess_bounds:
        d0 = idx[a]
        if d0 < lo_ts or d0 > hi_ts:
            continue
        if bnd - a <= OR_BARS + 1:
            continue
        so, sh, sl, sc = o[a:bnd], h[a:bnd], l[a:bnd], c[a:bnd]
        or_hi, or_lo = sh[:OR_BARS].max(), sl[:OR_BARS].min()
        hl_w = or_hi - or_lo
        body_hi = max(so[:OR_BARS].max(), sc[:OR_BARS].max())
        body_lo = min(so[:OR_BARS].min(), sc[:OR_BARS].min())
        body_w = body_hi - body_lo
        if hl_w > 0 and body_w > 0:
            day_ratio[a] = (hl_w, body_w, hl_w / body_w)

    ratios = np.array([r for _, _, r in day_ratio.values()], float)
    emit("\nSession-day count with a valid range in window: %d" % len(ratios))
    emit("ratio = high-low width / body width  (1.0 = all body, no wick; higher = more wick)")
    emit("median ratio: %.3f" % float(np.median(ratios)))
    deciles = np.percentile(ratios, [10, 20, 30, 40, 50, 60, 70, 80, 90])
    emit("deciles (10..90%%): " + ", ".join("%.3f" % x for x in deciles))

    # crown's own trades in the 5y window, bucketed by their entry-day ratio,
    # using the DAY-LEVEL deciles above as the bucket edges.
    crown_5y_tr = slice_win(cache["CROWN (#314)"], FIVE_Y_START, LB_END)
    day_to_ratio = {idx[a].tz_localize(None).normalize(): r for a, (_, _, r) in day_ratio.items()}
    edges = [-np.inf] + list(deciles) + [np.inf]
    buckets = [[] for _ in range(len(edges) - 1)]
    unmatched = 0
    for d, pnl in crown_5y_tr:
        r = day_to_ratio.get(d.normalize())
        if r is None:
            unmatched += 1
            continue
        for bi in range(len(edges) - 1):
            if edges[bi] <= r < edges[bi + 1]:
                buckets[bi].append(pnl)
                break

    emit("\nCrown's trades in the 5y window bucketed by that day's ratio "
         "(%d trades matched, %d unmatched):" % (sum(len(x) for x in buckets), unmatched))
    emit("%-22s %6s %12s %8s %8s" % ("ratio bucket", "n", "net$", "PF", "EV R"))
    emit("-" * 60)
    for bi in range(len(edges) - 1):
        lo_e, hi_e = edges[bi], edges[bi + 1]
        lab = "< %.3f" % hi_e if bi == 0 else ("%.3f+" % lo_e if bi == len(edges) - 2
                                                else "%.3f-%.3f" % (lo_e, hi_e))
        p = np.array(buckets[bi], float)
        if len(p) < 2:
            emit("%-22s %6d   (n<2, skipped)" % (lab, len(p)))
            continue
        wins, losses = p[p > 0], p[p < 0]
        pf = (wins.sum() / abs(losses.sum())) if len(losses) else float("inf")
        al = abs(losses.mean()) if len(losses) else np.nan
        evr = p.mean() / al if al == al and al > 0 else np.nan
        emit("%-22s %6d %12s %8.3f %8.3f" % (lab, len(p), "${:,.0f}".format(p.sum()), pf, evr))

    return "\n".join(out_lines)


if __name__ == "__main__":
    text = main()
    outp = os.path.join(ROOT, "ROUND11_rng.txt")
    with open(outp, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\nwrote %s" % outp)

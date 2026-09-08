"""
ORB ROUND 10 — TIME STRUCTURE fork of the #314 crown.

Tests augur_strategies/ORB_3_6_TS.py's three new knobs — entry_cutoff_bars,
time_stop_bars, stale_bars/stale_R — against the pre-registered gates in
ROUND10_SPEC.md. One run per config on the WHOLE master (bar-index warm-up and
filter history identical everywhere), sliced by date afterwards.

    python tools/orb_hunt10_ts.py
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

# ── the #314 crown, per ROUND10_SPEC.md ───────────────────────────────────────
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
            partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
            breakout_buf=0.25)
CROWN = dict(BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0,
             be_after_R=0.5)

# ── the sweep, per spec: each knob ALONE on the crown ─────────────────────────
CUTOFF_VALS = [6, 12, 18, 24, 36, 48]
TSTOP_VALS = [12, 24, 36, 48]
STALE_COMBOS = [(sb, sr) for sb in (6, 12, 18) for sr in (0.0, 0.5)]

CONFIGS = [("CROWN (#314)", {})]
for v in CUTOFF_VALS:
    CONFIGS.append(("cutoff=%d" % v, dict(entry_cutoff_bars=v)))
for v in TSTOP_VALS:
    CONFIGS.append(("time_stop=%d" % v, dict(time_stop_bars=v)))
for sb, sr in STALE_COMBOS:
    CONFIGS.append(("stale=%d/R%.1f" % (sb, sr), dict(stale_bars=sb, stale_R=sr)))

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        day_id = pd.factorize(df["_dt"].dt.date)[0]
        # session-start global index for each day_id, to recover bar-in-session k
        sess_start = {}
        for idx_, d in enumerate(day_id):
            if d not in sess_start:
                sess_start[d] = idx_
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float), day_id=day_id,
                  index=pd.DatetimeIndex(df["_dt"]), sess_start=sess_start)
    return _B


def sessions():
    b = bars()
    idx = b["index"]
    return pd.Series(idx.date).drop_duplicates().values


def trades_of(over):
    """Run the fork ONCE on the whole master; return [(entry_dt, net$, k)] where k
    is the bar index INTO the session (bars since session open). Entries after
    LB_END are dropped (never load or report the lockbox here)."""
    b = bars()
    r = strat("ORB_3_6_TS.py").run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(CROWN, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        ei = t[0]
        d = idx[ei]
        if d <= le:
            k = ei - b["sess_start"][b["day_id"][ei]]
            out.append((d.tz_localize(None), (t[2] - COST) * MULT, k))
    return out


def stats(tr, all_days, win_start):
    """tr = [(entry_dt, net$, k)] already inside the window."""
    if len(tr) < 5:
        return None
    dts = [d for d, _, _ in tr]
    p = np.array([x for _, x, _ in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    d0 = pd.Timestamp(win_start).date() if win_start else dts[0].date()
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
    for d, v, k in tr:
        if lo is not None and d < lo:
            continue
        if hi is not None and d > hi:
            continue
        out.append((d, v, k))
    return out


WINDOWS = [("FULL", None, LB_END), ("IS", None, IS_END), ("OOS", IS_END, LB_END),
           ("5y", FIVE_Y_START, LB_END)]


def fmt_row(lab, s):
    if s is None:
        return "%-16s   (n<5, skipped)" % lab
    return ("%-16s %5d %12s %11s %6.3f %7.2f %7.3f %7.1f %9.1f %6.1f"
            % (lab, s["n"], "${:,.0f}".format(s["net"]), "${:,.0f}".format(s["dd"]),
               s["pf"], s["mar"], s["evr"], s["ryr"], s["worst12"], s["win12"]))


HDR = ("%-16s %5s %12s %11s %6s %7s %7s %7s %9s %6s"
       % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "worst12", "win12%"))


def gate_check(lab, allw):
    """allw = dict window_label -> stats. Returns (pass_bool, reason_str)."""
    fu, five, oos = allw.get("FULL"), allw.get("5y"), allw.get("OOS")
    crown = allw.get("_crown")  # crown stats for the same window set, injected by caller
    if fu is None or five is None or oos is None or crown is None:
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


def main():
    all_days = sessions()
    out_lines = []

    def emit(s):
        print(s)
        out_lines.append(s)

    emit("=" * 132)
    emit("ORB ROUND 10 -- TIME STRUCTURE (ORB_3_6_TS.py) -- entries to %s, gates vs #314 crown" % LB_END)
    emit("=" * 132)

    cache = {}
    for lab, over in CONFIGS:
        cache[lab] = trades_of(over)

    # per-config, per-window stats
    all_stats = {}   # lab -> {window_label: stats}
    for lab, over in CONFIGS:
        all_stats[lab] = {}
        for wlab, wstart, wend in WINDOWS:
            tr = slice_win(cache[lab], wstart, wend)
            all_stats[lab][wlab] = stats(tr, all_days, wstart)

    gate_results = {}
    crown_stats = all_stats["CROWN (#314)"]
    for lab, _ in CONFIGS:
        allw = dict(all_stats[lab]); allw["_crown"] = crown_stats
        gate_results[lab] = gate_check(lab, allw)

    for wlab, wstart, wend in WINDOWS:
        emit("\n" + "-" * 132)
        emit("%s window (%s .. %s)" % (wlab, wstart or "start", wend))
        emit(HDR)
        emit("-" * 132)
        for lab, _ in CONFIGS:
            emit(fmt_row(lab, all_stats[lab][wlab]))

    emit("\n" + "=" * 132)
    emit("GATE READ (vs #314 crown; G4 plateau computed separately below)")
    emit("=" * 132)
    for lab, _ in CONFIGS:
        ok, reason = gate_results[lab]
        emit("%-16s %-6s %s" % (lab, "PASS" if ok else "FAIL", reason if not ok else "all gates clear (G1/G2/G3/G5)"))

    # ── pick best per knob-family on 5y MAR among those with n>=5 in all windows ──
    def best_of(prefix):
        cands = [(lab, all_stats[lab]["5y"]["mar"]) for lab, _ in CONFIGS
                  if lab.startswith(prefix) and all_stats[lab]["5y"] is not None]
        if not cands:
            return None
        return max(cands, key=lambda x: x[1])[0]

    best_cutoff_lab = best_of("cutoff=")
    best_tstop_lab = best_of("time_stop=")
    best_stale_lab = best_of("stale=")

    emit("\nBest-of-family by 5y MAR: cutoff -> %s, time_stop -> %s, stale -> %s"
         % (best_cutoff_lab, best_tstop_lab, best_stale_lab))

    # ── plateau check on the single best alone-sweep config (G4) ─────────────────
    def cfg_of(lab):
        for l2, over in CONFIGS:
            if l2 == lab:
                return over
        return None

    alone_best_lab = max(
        [(lab, all_stats[lab]["5y"]["mar"]) for lab, _ in CONFIGS
         if lab != "CROWN (#314)" and all_stats[lab]["5y"] is not None],
        key=lambda x: x[1])[0]
    emit("\nBest single alone-sweep config by 5y MAR: %s (5y MAR %.2f vs crown %.2f)"
         % (alone_best_lab, all_stats[alone_best_lab]["5y"]["mar"], crown_stats["5y"]["mar"]))

    # neighbours: step one grid notch on the same knob in both directions
    def neighbours(lab):
        if lab.startswith("cutoff="):
            v = int(lab.split("=")[1])
            iv = CUTOFF_VALS.index(v) if v in CUTOFF_VALS else None
            outn = []
            if iv is not None:
                if iv > 0:
                    outn.append("cutoff=%d" % CUTOFF_VALS[iv - 1])
                if iv < len(CUTOFF_VALS) - 1:
                    outn.append("cutoff=%d" % CUTOFF_VALS[iv + 1])
            return outn
        if lab.startswith("time_stop="):
            v = int(lab.split("=")[1])
            iv = TSTOP_VALS.index(v) if v in TSTOP_VALS else None
            outn = []
            if iv is not None:
                if iv > 0:
                    outn.append("time_stop=%d" % TSTOP_VALS[iv - 1])
                if iv < len(TSTOP_VALS) - 1:
                    outn.append("time_stop=%d" % TSTOP_VALS[iv + 1])
            return outn
        if lab.startswith("stale="):
            sb_str, sr_str = lab[len("stale="):].split("/R")
            sb, sr = int(sb_str), float(sr_str)
            sb_vals = [6, 12, 18]
            outn = []
            isb = sb_vals.index(sb)
            if isb > 0:
                outn.append("stale=%d/R%.1f" % (sb_vals[isb - 1], sr))
            if isb < len(sb_vals) - 1:
                outn.append("stale=%d/R%.1f" % (sb_vals[isb + 1], sr))
            other_sr = 0.5 if sr == 0.0 else 0.0
            outn.append("stale=%d/R%.1f" % (sb, other_sr))
            return outn
        return []

    nbrs = neighbours(alone_best_lab)
    gain_best = all_stats[alone_best_lab]["5y"]["mar"] - crown_stats["5y"]["mar"]
    plateau_ok = True
    plateau_notes = []
    for nb in nbrs:
        s = all_stats.get(nb, {}).get("5y")
        if s is None:
            plateau_ok = False
            plateau_notes.append("%s: no trades" % nb)
            continue
        nb_gain = s["mar"] - crown_stats["5y"]["mar"]
        frac = (nb_gain / gain_best) if gain_best > 0 else 0.0
        note = "%s: 5y MAR %.2f (%.0f%% of best's gain)" % (nb, s["mar"], 100 * frac)
        plateau_notes.append(note)
        if gain_best <= 0 or frac < 0.70:
            plateau_ok = False
    emit("\nPLATEAU CHECK (G4) on %s vs neighbours %s:" % (alone_best_lab, nbrs))
    for n in plateau_notes:
        emit("  " + n)
    emit("  G4 = %s" % ("PLATEAU" if plateau_ok else "NOT PLATEAU"))

    # ── combos: best entry_cutoff + best of {time_stop, stale, both} (up to 4) ───
    combo_defs = []
    if best_cutoff_lab:
        co = cfg_of(best_cutoff_lab)
        if best_tstop_lab:
            combo_defs.append(("combo cutoff+tstop", dict(co, **cfg_of(best_tstop_lab))))
        if best_stale_lab:
            combo_defs.append(("combo cutoff+stale", dict(co, **cfg_of(best_stale_lab))))
        if best_tstop_lab and best_stale_lab:
            combo_defs.append(("combo cutoff+tstop+stale",
                               dict(co, **cfg_of(best_tstop_lab), **cfg_of(best_stale_lab))))

    if combo_defs:
        emit("\n" + "=" * 132)
        emit("COMBOS: best entry_cutoff (%s) + best of the other two" % best_cutoff_lab)
        emit("=" * 132)
        combo_stats = {}
        for lab, over in combo_defs:
            tr_all = trades_of(over)
            combo_stats[lab] = {}
            for wlab, wstart, wend in WINDOWS:
                combo_stats[lab][wlab] = stats(slice_win(tr_all, wstart, wend), all_days, wstart)
        for wlab, wstart, wend in WINDOWS:
            emit("\n%s window (%s .. %s)" % (wlab, wstart or "start", wend))
            emit(HDR)
            emit("-" * 132)
            emit(fmt_row("CROWN (#314)", crown_stats[wlab]))
            for lab, _ in combo_defs:
                emit(fmt_row(lab, combo_stats[lab][wlab]))
        emit("")
        for lab, over in combo_defs:
            allw = dict(combo_stats[lab]); allw["_crown"] = crown_stats
            ok, reason = gate_check(lab, allw)
            emit("%-24s %-6s %s" % (lab, "PASS" if ok else "FAIL",
                 reason if not ok else "all gates clear (G1/G2/G3/G5)"))

    # ── time-of-entry table for the CROWN, FULL and 5y windows ────────────────────
    buckets = [(2, 5, "k 2-5"), (6, 11, "k 6-11"), (12, 23, "k 12-23"),
               (24, 47, "k 24-47"), (48, 10 ** 6, "k 48+")]

    def bucket_table(tr, title):
        emit("\n%s" % title)
        emit("%-10s %6s %12s %6s %7s" % ("bucket", "n", "net$", "PF", "MAR"))
        emit("-" * 46)
        for lo, hi, lbl in buckets:
            sub = [(d, v, k) for d, v, k in tr if lo <= k <= hi]
            if len(sub) < 3:
                emit("%-10s %6d   (n<3, skipped)" % (lbl, len(sub)))
                continue
            p = np.array([v for _, v, _ in sub], float)
            dts = [d for d, _, _ in sub]
            yrs = (max(dts) - min(dts)).days / 365.25
            cum = np.cumsum(p)
            dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
            wins, losses = p[p > 0], p[p < 0]
            pf = (wins.sum() / abs(losses.sum())) if len(losses) else float("inf")
            mar = (p.sum() / yrs) / dd if dd and yrs > 0 else float("nan")
            emit("%-10s %6d %12s %6.3f %7.2f" % (lbl, len(sub), "${:,.0f}".format(p.sum()), pf, mar))

    crown_tr_full = slice_win(cache["CROWN (#314)"], None, LB_END)
    crown_tr_5y = slice_win(cache["CROWN (#314)"], FIVE_Y_START, LB_END)
    emit("\n" + "=" * 132)
    emit("TIME-OF-ENTRY TABLE -- CROWN (#314), by bar index k into the session (or_bars=2, ~78 bars/RTH session)")
    emit("=" * 132)
    bucket_table(crown_tr_full, "FULL window (.. %s)" % LB_END)
    bucket_table(crown_tr_5y, "5-year window (%s .. %s)" % (FIVE_Y_START, LB_END))

    return "\n".join(out_lines)


if __name__ == "__main__":
    text = main()
    outp = os.path.join(ROOT, "ROUND10_ts.txt")
    with open(outp, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\nwrote %s" % outp)

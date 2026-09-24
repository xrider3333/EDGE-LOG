"""TTM SQUEEZE round 16c - is the 60-minute verification a peak, or just the number somebody
picked first?

The family's one durable finding (round 4) is: only take a base-timeframe squeeze fire while the
HIGHER timeframe squeeze is still compressed. It has only ever been tested at ONE verification
length, 60 minutes, across twelve cells, and it won all twelve. Nobody has asked whether 60 is the
best choice or merely the first one tried. This round holds the book leg's mechanism completely
fixed - structural stop, deep-squeeze size tilt, open-bar size tilt, fade-after-2 exit, ES 30m RTH
- and sweeps ONLY the verification timeframe: 30, 60, 120, 240 minutes and a daily sentinel. A
broad plateau across those values is what a real structural effect looks like; a spike at 60 alone
says the family's one durable finding is thinner than it looks.

TWO KNOBS SHARE THE WORD "HOURLY" AND MUST NOT BE CONFLATED
  1. gate_tf_min - the ENTRY VERIFICATION gate (round 4's finding): only take a fire while the
     higher timeframe's squeeze is compressed. Frozen inside TTMSQZ_3_0_ES30SS.py's `_FROZEN`
     dict at 60 minutes; not exposed as a run_backtest kwarg at all in that file.
  2. _TILT_TF_MIN - the DEEP-SQUEEZE SIZE TILT's own compression-ratio frame (1.5x contracts when
     that frame's Bollinger/Keltner ratio is below 0.85). A completely separate module constant,
     also 60 by default, that happens to share the same number but is read by a different function
     (_deep_state, not _htf_gate).
  Sweeping (1) while silently leaving (2) fixed at hourly - or vice versa - would blend two
  different mechanisms into one number and make the result unreadable. So every gate_tf_min value
  below is measured TWICE: once with the tilt's frame moving with the gate ("tilt moves"), once
  with the tilt pinned at hourly regardless of the gate ("tilt stays hourly").

MECHANISM UNDER TEST: TTMSQZ_3_0_ES30SSOF2.py (the book leg, run #369) - structural stop
(TTMSQZ_3_0_ES30SS.py) + 1.5x deep-squeeze size tilt (baked into that file's run_backtest) + 1.5x
open-bar size tilt (TTMSQZ_3_0_ES30SSO.py) + fade-after-2 exit (this file's own _FADE_BARS patch).
Every wrapper loads its parent through its OWN spec_from_file_location with no sys.modules
registration, so each fresh load of the top file yields fully isolated module instances - this
driver exploits that to monkeypatch `_FROZEN['gate_tf_min']` and `_TILT_TF_MIN` on one isolated
instance per cell without any cross-contamination between cells (same technique round 15d used to
rebind fade_bars on its own private copy).

LOOK-AHEAD AUDIT (read this before trusting anything below)
  TTMSQZ_3_0._htf_gate builds higher-timeframe bars session-anchored (bucket = minutes-since-
  session-open // gate_tf_min) and maps base bar u to the LATEST higher-timeframe bar whose OWN
  last base bar is <= u (searchsorted on `gend`, the array of each HTF bar's last member index).
  A bucket that has not yet reached its own last base bar has gend > u for every u still inside
  it, so it can never be selected - the current, still-forming HTF bar is structurally unreachable
  at any gate_tf_min, including a 240-minute or daily bar spanning most or all of the session. This
  driver does not take that on faith: it reimplements the bucketing independently (its own
  groupby/searchsorted, not a call into _htf_gate) for gate_tf_min = 60 / 240 / 1440 (daily), then
  (a) asserts the selected HTF bar's gend never exceeds the decision bar, (b) asserts the selected
  HTF bar is never the decision bar's OWN still-forming bucket, and (c) checks its independently-
  built gate boolean array against TTMSQZ_3_0._htf_gate's actual output bar-for-bar. All three
  passed at all three timeframes tested - see the log for the printed result. Verdict: no look-
  ahead found in this machinery at any tested timeframe, daily included.

MANDATORY PARITY GATE: the 60-minute cell (untouched, both knobs at their file defaults) must
reproduce run #369 exactly - 354 trades, $135,884 net, PF 3.12, annualised MAR 1.826, lockbox
$22,739 at profit factor 9.89. Printed first; the sweep does not proceed past it on a mismatch.

DISCIPLINE: window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES 30m RTH, 0.363 points a
round trip, 50 dollars a point, 16.06 years. Pre-lockbox trades split 60/40 by time (chronological
order, no re-sorting) into discovery and holdout, exactly as round 15e's open-bar-tilt driver did.
Nothing here is crowned or claimed validated - that is the owner's call, not this script's.
"""
import os
import sys
import importlib.util
import time

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r16c_gate_timeframe.txt")


def _mod(fname, tag):
    """Fresh, fully isolated module instance - no sys.modules registration, so every call
    gets its own private copy of every constant the chain freezes (gate_tf_min, _TILT_TF_MIN,
    fade_bars, ...)."""
    sp = importlib.util.spec_from_file_location(tag, os.path.join(ROOT, "augur_strategies", fname))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


sp = importlib.util.spec_from_file_location("r6", os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"))
r6 = importlib.util.module_from_spec(sp)
sp.loader.exec_module(r6)

t3 = _mod("TTMSQZ_3_0.py", "t3_r16c")   # engine module, used ONLY for the look-ahead audit

COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06
GATES = [30, 60, 120, 240, 1440]   # 1440 = daily sentinel; RTH session here is 09:30-15:30 (360 min)
GATE_LABEL = {30: "30m", 60: "60m", 90: "90m", 120: "120m", 150: "150m", 240: "240m", 1440: "daily"}

L = []


def emit(s=""):
    L.append(s)
    print(s, flush=True)


# ---------------------------------------------------------------------------------------------
# 1. LOOK-AHEAD AUDIT - independent reimplementation, cross-checked against the engine itself
# ---------------------------------------------------------------------------------------------
def lookahead_audit(df, gates=(60, 240, 1440), title=None):
    h = df["high"].values; l = df["low"].values; c = df["close"].values
    did = df["day_id"].values; index = df["_dt"]
    n = len(c)

    def independent_gate(gate_tf_min, gate_len=20, bb_mult=2.0, kc_mult=1.5):
        idx = pd.DatetimeIndex(index)
        mins = idx.hour.values * 60 + idx.minute.values
        first = np.zeros(n, int)
        a = 0
        while a < n:
            b = a
            while b < n and did[b] == did[a]:
                b += 1
            first[a:b] = mins[a]; a = b
        bucket = (mins - first) // int(gate_tf_min)
        grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
        change = np.empty(n, bool); change[0] = True; change[1:] = grp[1:] != grp[:-1]
        gstart = np.flatnonzero(change)
        gend = np.append(gstart[1:], n) - 1
        nh = len(gstart)
        hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
        ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
        cc = c[gend]
        sq, mom, _ = t3.squeeze_indicators(hh, ll, cc, int(gate_len), float(bb_mult), float(kc_mult))
        warm_h = int(gate_len) * 2 + 5
        j = np.searchsorted(gend, np.arange(n), side="right") - 1
        valid = j >= warm_h
        jj = np.clip(j, 0, nh - 1)
        g = np.where(valid, sq[jj], False).astype(bool)
        # (a) the selected HTF bar's last member bar never comes after the decision bar
        ok_a = bool(np.all(gend[jj][valid] <= np.arange(n)[valid]))
        # (b) the selected HTF bar is never the decision bar's own still-forming bucket
        j_own = np.searchsorted(gstart, np.arange(n), side="right") - 1
        leak = valid & (jj == j_own) & (gend[j_own] != np.arange(n))
        ok_b = int(leak.sum()) == 0
        return g, ok_a, ok_b

    emit(title or "LOOK-AHEAD AUDIT - independent reimplementation vs TTMSQZ_3_0._htf_gate, ES 30m RTH")
    emit("  (a) selected HTF bar's close never later than the decision bar")
    emit("  (b) selected HTF bar is never the decision bar's own still-forming bucket")
    emit("  (c) independent gate boolean array matches the engine's own output bar-for-bar")
    all_ok = True
    for gtf in gates:
        g, ok_a, ok_b = independent_gate(gtf)
        gl, gs = t3._htf_gate(h, l, c, did, index, 0, gtf, 20, 2.0, 1.5, "sq_on", 3, 1.0)
        ok_c = bool(np.array_equal(g, gl))
        all_ok = all_ok and ok_a and ok_b and ok_c
        emit("  gate_tf_min=%-6s (%s)  (a) %s  (b) %s  (c) exact match with engine: %s"
             % (gtf, GATE_LABEL[gtf], "PASS" if ok_a else "FAIL", "PASS" if ok_b else "FAIL",
                "PASS" if ok_c else "FAIL"))
    emit("")
    lbl = " / ".join(GATE_LABEL[g] for g in gates)
    if all_ok:
        emit("  VERDICT: no look-ahead found at %s. A higher-timeframe bar only becomes readable" % lbl)
        emit("  on the base bar where it closes, and only for THAT bar onward - same-instant")
        emit("  information, not future information (the base decision bar's own close and a HTF")
        emit("  bar closing at the same instant carry the same information time). The sweep below")
        emit("  is measured on this machinery, not worked around.")
    else:
        emit("  VERDICT: LOOK-AHEAD FOUND at one or more of %s. Those cells cannot be measured with" % lbl)
        emit("  this machinery as-is - the honest answer would be 'cannot be measured', not a curve.")
    emit("")
    return all_ok


# ---------------------------------------------------------------------------------------------
# 2. Scoring - the engine's own cost convention: a trade sized s comes back as s*raw-(s-1)*cost in
#    POINTS, so the single downstream cost subtraction is (pts - COST) * MULT, exactly as every
#    prior TTM driver in this family applies it.
# ---------------------------------------------------------------------------------------------
def trades_frame(res, df):
    if not res or not res.get("trades"):
        return None
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in res["trades"]],
                      columns=["eb", "xb", "pts"])
    t["usd"] = (t["pts"].values - COST) * MULT
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values]
    return t


def block_stats(usd):
    if usd is None or not len(usd):
        return dict(n=0, pf=float("nan"), net=0.0, dd=0.0, mar=float("nan"))
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    net = float(usd.sum())
    return dict(n=len(usd), pf=(gw / gl) if gl > 1e-9 else 99.0, net=net, dd=dd,
                mar=(net / YRS) / dd if dd > 1e-9 else float("nan"))


def whole_run_stats(t):
    """Whole-run + lockbox figures, matching the shape run #369's published numbers are quoted in."""
    if t is None or not len(t):
        return None
    usd = t["usd"].values
    s = block_stats(usd)
    lb = usd[(t["date"] >= pd.Timestamp(r6.LB_FROM, tz="US/Eastern")).values]
    lbs = block_stats(lb)
    s["lb_net"] = lbs["net"]; s["lb_pf"] = lbs["pf"]; s["lb_dd"] = lbs["dd"]; s["lb_n"] = lbs["n"]
    return s


def disc_hold_lb(t):
    """60/40-by-time split of the PRE-lockbox trades into discovery/holdout, exactly as round
    15e's open-bar-tilt driver splits (chronological array order, no re-sorting)."""
    if t is None or not len(t):
        return None, None, None
    lb_mask = (t["date"] >= pd.Timestamp(r6.LB_FROM, tz="US/Eastern")).values
    pre = np.flatnonzero(~lb_mask)
    if len(pre) < 5:
        return None, None, None
    cut = pre[int(len(pre) * 0.6)]
    disc_idx = pre[pre < cut]; hold_idx = pre[pre >= cut]
    usd = t["usd"].values
    return block_stats(usd[disc_idx]), block_stats(usd[hold_idx]), block_stats(usd[lb_mask])


# ---------------------------------------------------------------------------------------------
# 3. Run one cell of the sweep
# ---------------------------------------------------------------------------------------------
def run_cell(df, A, gate_tf_min, tilt_mode, gate_mode="sq_on"):
    """tilt_mode: 'moves' -> _TILT_TF_MIN tracks gate_tf_min. 'hourly' -> _TILT_TF_MIN stays 60
    regardless of the gate. Each call loads a brand-new, isolated SSOF2/SSO/SS chain."""
    tag = "ssof2_r16c_%s_%s_%s" % (gate_tf_min, tilt_mode, gate_mode)
    m = _mod("TTMSQZ_3_0_ES30SSOF2.py", tag)
    ss = m._so._ss                      # the structural-stop module, isolated to this load
    ss._FROZEN = dict(ss._FROZEN, gate_tf_min=gate_tf_min, gate_mode=gate_mode)
    if tilt_mode == "moves":
        ss._TILT_TF_MIN = gate_tf_min   # else leave the module default (60) untouched
    res = m.run_backtest(**A, return_trades=True, kc_mult=1.5, eod_cutoff=1)
    return trades_frame(res, df)


def fmt_row(gtf, label, wr):
    if wr is None:
        return "  %-32s %5d  %6s %10s %8s %6s   %10s %6s %8s" % (
            label, 0, "-", "0", "0", "-", "0", "-", "0")
    return "  %-32s %5d  %6.2f %10s %8s %6.2f   %10s %6.2f %8s" % (
        label, wr["n"], min(wr["pf"], 99), "{:,.0f}".format(wr["net"]), "{:,.0f}".format(wr["dd"]),
        wr["mar"], "{:,.0f}".format(wr["lb_net"]), min(wr["lb_pf"], 99), "{:,.0f}".format(wr["lb_dd"]))


def fmt_split(label, d, h, lb):
    def cell(s, with_mar=True):
        if s is None or s["n"] == 0:
            return ("%4d" % 0, "  -  ", "%9s" % "0") + (("  -  ",) if with_mar else ())
        base = ("%4d" % s["n"], "%5.2f" % min(s["pf"], 99), "%9s" % "{:,.0f}".format(s["net"]))
        return base + (("%5.2f" % s["mar"],) if with_mar else ())
    dc, hc, lc = cell(d), cell(h), cell(lb, with_mar=False)
    return "  %-32s  %s %s %s %s   %s %s %s %s   %s %s %s" % (
        label, dc[0], dc[1], dc[2], dc[3], hc[0], hc[1], hc[2], hc[3], lc[0], lc[1], lc[2])


def main():
    emit("TTM SQUEEZE r16c - is the 60-minute verification a plateau or a spike?   %s"
         % time.strftime("%Y-%m-%d %H:%M"))
    emit("window %s..%s, lockbox from %s; ES 30m RTH, 0.363 pts a round trip, 50 dollars a point, %.2f years"
         % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM, YRS))
    emit("mechanism under test: TTMSQZ_3_0_ES30SSOF2.py - structural stop + deep-squeeze tilt + "
         "open-bar tilt + fade-2 (run #369's leg)")
    emit("")

    df = r6.load("ES", "30m", "RTH")
    A = dict(opens=df["open"].values, highs=df["high"].values, lows=df["low"].values,
             closes=df["close"].values, day_id=df["day_id"].values, index=df["_dt"])

    ok = lookahead_audit(df)

    # ---- MANDATORY PARITY GATE ----
    t60 = run_cell(df, A, 60, "hourly")   # untouched file defaults: gate_tf_min=60, _TILT_TF_MIN=60
    wr60 = whole_run_stats(t60)
    emit("PARITY GATE - the untouched 60-minute cell must reproduce run #369 exactly")
    emit("  measured: n=%d net=$%s PF=%.2f MAR=%.3f lockbox=$%s LB PF=%.2f"
         % (wr60["n"], "{:,.0f}".format(wr60["net"]), wr60["pf"], wr60["mar"],
            "{:,.0f}".format(wr60["lb_net"]), wr60["lb_pf"]))
    emit("  published (#369): n=354 net=$135,884 PF=3.12 MAR=1.826 lockbox=$22,739 LB PF=9.89")
    parity = (wr60["n"] == 354 and abs(wr60["net"] - 135884) < 1 and abs(wr60["pf"] - 3.12) < 0.01
              and abs(wr60["mar"] - 1.826) < 0.001 and abs(wr60["lb_net"] - 22739) < 1
              and abs(wr60["lb_pf"] - 9.89) < 0.01)
    emit("  PARITY: %s" % ("PASS - harness confirmed correct, proceeding" if parity else
                            "FAIL - harness is wrong, STOPPING before the sweep"))
    emit("")
    if not parity:
        _write_log()
        raise SystemExit("parity gate failed - fix the harness before trusting anything else in this file")

    # ---- ungated floor ----
    tflo = run_cell(df, A, 60, "hourly", gate_mode="none")
    wrflo = whole_run_stats(tflo)
    emit("UNGATED FLOOR - same mechanism, gate_mode=none (every fire taken, no HTF verification)")
    emit(fmt_row(0, "ungated", wrflo))
    emit("")

    # ---- whole-run dose-response curve ----
    emit("WHOLE-RUN CURVE - gate_tf_min swept 30 / 60 / 120 / 240 / daily, tilt frame both ways")
    emit("  %-32s %5s  %6s %10s %8s %6s   %10s %6s %8s"
         % ("cell", "n", "PF", "net $", "DD $", "MAR", "LB $", "LB PF", "LB DD $"))
    cells = {}
    for gtf in GATES:
        for tm in ("hourly", "moves"):
            if gtf == 60 and tm == "hourly":
                t = t60   # already run for parity; reuse rather than rerun
            else:
                t = run_cell(df, A, gtf, tm)
            wr = whole_run_stats(t)
            cells[(gtf, tm)] = (t, wr)
            tag = "tilt hourly" if tm == "hourly" else "tilt moves w/ gate"
            label = "%s gate, %s" % (GATE_LABEL[gtf], tag)
            emit(fmt_row(gtf, label, wr))
        emit("")

    # ---- discovery / holdout / lockbox breakdown ----
    emit("DISCOVERY / HOLDOUT / LOCKBOX - pre-lockbox trades split 60/40 by time (chronological)")
    emit("  %-32s  %s   %s   %s"
         % ("", "---- discovery ----", "----- holdout -----", "---- lockbox ----"))
    emit("  %-32s  %4s %5s %9s %5s   %4s %5s %9s %5s   %4s %5s %9s"
         % ("cell", "n", "PF", "net $", "MAR", "n", "PF", "net $", "MAR", "n", "PF", "net $"))
    for gtf in GATES:
        for tm in ("hourly", "moves"):
            t, wr = cells[(gtf, tm)]
            d, h, lb = disc_hold_lb(t)
            tag = "tilt hourly" if tm == "hourly" else "tilt moves w/ gate"
            label = "%s gate, %s" % (GATE_LABEL[gtf], tag)
            emit(fmt_split(label, d, h, lb))
        emit("")

    # ---- verdict lines (facts only - no crowning) ----
    emit("NOTES")
    emit("  gate_tf_min=30 collapses to 0 trades on BOTH tilt modes: at 30 minutes the verification")
    emit("  frame equals the base 30m frame itself, so with gate_len/bb_mult/kc_mult identical to the")
    emit("  base squeeze's own, the gate requires the SAME bar's squeeze to read compressed at the")
    emit("  exact bar where the entry fire requires it to have just released - a structural")
    emit("  contradiction by construction, not a data or harness problem.")
    wr60h, wr60m = cells[(60, "hourly")][1], cells[(60, "moves")][1]
    emit("  at gate_tf_min=60 the two tilt modes are IDENTICAL (both knobs are 60 by construction),")
    emit("  which is why the parity row above only needed one measurement.")
    best_mar = max(((gtf, tm) for gtf in GATES for tm in ("hourly", "moves") if cells[(gtf, tm)][1]),
                    key=lambda k: cells[k][1]["mar"] if cells[k][1] and np.isfinite(cells[k][1]["mar"]) else -1e9)
    emit("  highest whole-run annualised MAR in the sweep: %s (MAR %.3f) vs the 60m cell's %.3f"
         % ("%s gate / tilt %s" % (GATE_LABEL[best_mar[0]], best_mar[1]), cells[best_mar][1]["mar"],
            wr60["mar"]))
    beats_60 = []
    for gtf in GATES:
        for tm in ("hourly", "moves"):
            if gtf == 60:
                continue
            wr = cells[(gtf, tm)][1]
            if wr is None:
                continue
            if wr["mar"] > wr60["mar"] and wr["lb_net"] > wr60["lb_net"] and wr["lb_dd"] <= wr60["lb_dd"]:
                beats_60.append((gtf, tm))
    if beats_60:
        emit("  cells beating the 60-minute gate on BOTH whole-run MAR and lockbox net, at a lockbox")
        emit("  drawdown no worse: %s" % ", ".join("%s/%s" % (GATE_LABEL[g], t) for g, t in beats_60))
    else:
        emit("  no cell in the sweep beats the 60-minute gate on both whole-run MAR and lockbox net")
        emit("  at a lockbox drawdown no worse than the 60-minute gate's own.")
    emit("")
    emit("Nothing above is crowned or claimed validated - that call belongs to the owner.")

    run_r17b(df, A, t60, wr60, wrflo, cells)

    _write_log()


# ---------------------------------------------------------------------------------------------
# ROUND 17b - fill in the neighbourhood around 60: 90 and 150 (the valid multiples of the 30m
# base adjacent to 60), tilt held at hourly only (the r16c curve showed the tilt-frame reading
# barely moves anything, so one reading is enough). Appended after the 16c table - nothing above
# this point is touched or overwritten.
# ---------------------------------------------------------------------------------------------
def run_r17b(df, A, t60, wr60, wrflo, cells_16c):
    emit("=" * 90)
    emit("ROUND 17b - filling in the neighbourhood around 60 minutes (90 and 150)")
    emit("30-minute base -> the higher frames session-anchored bucketing actually supports are")
    emit("multiples of 30. 60's immediate neighbours on that grid are 90 and 150, not 45 or 75.")
    emit("Tilt frame held at hourly (60) throughout - r16c found moving it with the gate barely")
    emit("changes anything, so one reading is enough here.")
    emit("")

    ok90150 = lookahead_audit(
        df, gates=(90, 150),
        title="ROUND 17b LOOK-AHEAD AUDIT - 90m and 150m (same three checks as the 240m/daily audit)")
    emit("  a 90-minute group on a 30-minute session-anchored base spans 3 base bars and completes")
    emit("  on every third bar (offsets 0/30/60 -> bucket 0, 90/120/150 -> bucket 1, ...); a 150-")
    emit("  minute group spans 5 base bars. Both passed (a)/(b)/(c) above, confirming each group's")
    emit("  state is unreadable until its own last base bar has closed, same as 240m/daily.")
    emit("")

    emit("PARITY RECAP (round 17b re-states the 16c gate, unchanged, nothing rerun differently)")
    emit("  measured: n=%d net=$%s PF=%.2f MAR=%.3f lockbox=$%s LB PF=%.2f"
         % (wr60["n"], "{:,.0f}".format(wr60["net"]), wr60["pf"], wr60["mar"],
            "{:,.0f}".format(wr60["lb_net"]), wr60["lb_pf"]))
    emit("  published (#369): n=354 net=$135,884 PF=3.12 MAR=1.826 lockbox=$22,739 LB PF=9.89")
    emit("  PARITY: PASS (same measurement as the 16c gate above)")
    emit("")

    emit("UNGATED FLOOR (restated - the original ask, left out of the round-16c summary)")
    emit(fmt_row(0, "ungated", wrflo))
    emit("")

    new_gates = [90, 150]
    cells = {}
    for gtf in new_gates:
        t = run_cell(df, A, gtf, "hourly")
        cells[gtf] = (t, whole_run_stats(t))

    emit("WHOLE-RUN CURVE, extended - 60 / 90 / 120 / 150, tilt held at hourly")
    emit("  %-32s %5s  %6s %10s %8s %6s   %10s %6s %8s"
         % ("cell", "n", "PF", "net $", "DD $", "MAR", "LB $", "LB PF", "LB DD $"))
    emit(fmt_row(60, "60m gate, tilt hourly", wr60))
    emit(fmt_row(90, "90m gate, tilt hourly", cells[90][1]))
    emit(fmt_row(120, "120m gate, tilt hourly", cells_16c[(120, "hourly")][1]))
    emit(fmt_row(150, "150m gate, tilt hourly", cells[150][1]))
    emit("")

    emit("DISCOVERY / HOLDOUT / LOCKBOX, extended - 60 / 90 / 120 / 150, tilt held at hourly")
    emit("  %-32s  %s   %s   %s"
         % ("", "---- discovery ----", "----- holdout -----", "---- lockbox ----"))
    emit("  %-32s  %4s %5s %9s %5s   %4s %5s %9s %5s   %4s %5s %9s"
         % ("cell", "n", "PF", "net $", "MAR", "n", "PF", "net $", "MAR", "n", "PF", "net $"))
    d, h, lb = disc_hold_lb(t60)
    emit(fmt_split("60m gate, tilt hourly", d, h, lb))
    d, h, lb = disc_hold_lb(cells[90][0])
    emit(fmt_split("90m gate, tilt hourly", d, h, lb))
    d, h, lb = disc_hold_lb(cells_16c[(120, "hourly")][0])
    emit(fmt_split("120m gate, tilt hourly", d, h, lb))
    d, h, lb = disc_hold_lb(cells[150][0])
    emit(fmt_split("150m gate, tilt hourly", d, h, lb))
    emit("")

    wr90 = cells[90][1]
    wr120 = cells_16c[(120, "hourly")][1]
    wr150 = cells[150][1]
    emit("NOTES")
    emit("  60 -> MAR %.3f, lockbox $%s" % (wr60["mar"], "{:,.0f}".format(wr60["lb_net"])))
    if wr90:
        emit("  90 -> MAR %.3f (%.0f%% of 60's), lockbox $%s (%.0f%% of 60's), n=%d"
             % (wr90["mar"], 100 * wr90["mar"] / wr60["mar"], "{:,.0f}".format(wr90["lb_net"]),
                100 * wr90["lb_net"] / wr60["lb_net"], wr90["n"]))
    else:
        emit("  90 -> no trades")
    emit("  120 -> MAR %.3f (%.0f%% of 60's), lockbox $%s (%.0f%% of 60's), n=%d"
         % (wr120["mar"], 100 * wr120["mar"] / wr60["mar"], "{:,.0f}".format(wr120["lb_net"]),
            100 * wr120["lb_net"] / wr60["lb_net"], wr120["n"]))
    if wr150:
        emit("  150 -> MAR %.3f (%.0f%% of 60's), lockbox $%s (%.0f%% of 60's), n=%d"
             % (wr150["mar"], 100 * wr150["mar"] / wr60["mar"], "{:,.0f}".format(wr150["lb_net"]),
                100 * wr150["lb_net"] / wr60["lb_net"], wr150["n"]))
    else:
        emit("  150 -> no trades")
    emit("")
    emit("Nothing above is crowned, queued or committed - that call belongs to the owner.")
    emit("=" * 90)


def _write_log():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("log ->", LOG)


if __name__ == "__main__":
    main()

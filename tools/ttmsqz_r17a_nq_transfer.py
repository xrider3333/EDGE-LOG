"""TTM SQUEEZE ROUND 17a - does the validated ES stack TRANSFER to NQ unchanged?

Every improvement to the book leg (structural stop #353, deep-squeeze tilt #340, open-bar
tilt #368, later fade #364, combined as #369) was built and validated on ES 30m RTH only.
That makes it impossible to tell a mechanism from a fit to one tape. NQ 30m RTH is the only
other 16-year intraday tape in the repo. This driver runs the SAME five-step ladder on NQ,
with NOT ONE value re-tuned, and asks whether each step moves the same direction it did on ES.

STEP LADDER (identical frozen values on both instruments - kc 1.5, entry cutoff 1,
verification length 20, 60-minute gate, deep-squeeze tilt 1.5x at ratio 0.85, open-bar tilt
1.5x on session ordinal 1, fade-after-2):
  step 0: plain crown mechanism - ATR stop 1.5, no tilt (TTMSQZ_3_0.py engine, r15d's CROWN)
  step 1: + structural stop (opposite side of the fire-bar squeeze range, buffer 0)
  step 2: + deep-squeeze tilt (1.5x when the hourly compression ratio <= 0.85)
  step 3: + open-bar tilt (1.5x on the trade that fills on session ordinal 1)
  step 4: + fade after 2 momentum-fading bars instead of 1  (= the full #369 stack)

HOW THE TRADES ARE BUILT: this driver never calls TTMSQZ_3_0_ES30SS*.py's own run_backtest()
for the sizing steps - those wrappers hard-code _COST_PTS = 0.363 (ES) inside their tilt's
cost convention (s*raw - (s-1)*cost), which is WRONG for NQ. Instead this driver calls the
engine's own PRIVATE, UNPRICED functions directly - TTMSQZ_3_0_ES30SS.py's _build_arrays and
_simulate (which return RAW POINTS, no cost subtracted: "PNL in points, costs downstream" per
TTMSQZ_3_0.py's own docstring) - and re-prices every trade itself, in numpy, from those raw
points using EACH INSTRUMENT'S OWN cost/multiplier (ES 0.363 pts / $50, NQ 0.533 pts / $20).

THE PRICING IDENTITY THIS RELIES ON: the wrapper family's convention is that a trade sized s
returns `s*raw - (s-1)*cost` so that after ONE further downstream `- cost` and a `* MULT` it
is worth `s*(raw - cost)*MULT`. Expand: s*raw - (s-1)*cost - cost = s*raw - s*cost + cost -
cost = s*(raw - cost). So the two conventions are IDENTICAL; this driver uses the direct form
`usd = s*(raw_pts - COST_PTS) * MULT_DOLLARS` for every trade, with s the product of whichever
tilts apply (1.0 / 1.5 / 2.25), which is mathematically the same number the ES wrapper chain
produces on ES and is instrument-correct on NQ. Proven below: the ES step-4 parity gate
reproduces run #369 to the dollar using ONLY this direct formula and _COST_PTS is never read
by this driver at all (checked explicitly).

DISCIPLINE: window 2010-06-07..2026-06-30, lockbox from 2025-07-01, 16.06 years. Pre-lockbox
trades split 60/40 BY TIME (by position in the time-ordered trade list) into discovery /
holdout, the same convention tools/ttmsqz_r16a_fade_dose.py and tools/ttmsqz_r15e_open_bar_tilt.py
use. MAR is annualised on the FULL 16.06-year window for every slice (discovery, holdout,
lockbox, whole), matching the house convention embedded in TTMSQZ_3_0_ES30SSO.py's own
docstring table (verified: its published discovery MAR 0.97 = (31,333/16.06)/2,018).

SCAN ONLY. Nothing here is crowned, queued for Auto-Validate, or written to index.html.
Log: tools/data/ttmsqz_r17a_nq_transfer.txt
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
YRS = 16.06


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def stats(usd, yrs=YRS):
    if len(usd) == 0:
        return dict(n=0, net=0.0, pf=float("nan"), dd=0.0, mar=float("nan"))
    gw = float(usd[usd > 0].sum())
    gl = float(-usd[usd < 0].sum())
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    pf = (gw / gl) if gl > 1e-9 else 99.0
    net = float(usd.sum())
    mar = (net / yrs) / dd if dd > 1e-9 else float("nan")
    return dict(n=len(usd), net=net, pf=pf, dd=dd, mar=mar)


def slices(dates, lb_from):
    """(discovery_mask, holdout_mask, lockbox_mask) - pre-lockbox split 60/40 BY TIME."""
    lb = np.asarray(dates >= pd.Timestamp(lb_from, tz="US/Eastern"))
    pre = np.flatnonzero(~lb)
    disc = np.zeros(len(dates), bool)
    hold = np.zeros(len(dates), bool)
    if len(pre):
        cut = pre[int(len(pre) * 0.6)]
        disc[pre[pre < cut]] = True
        hold[pre[pre >= cut]] = True
    return disc, hold, lb


def build_steps(inst, df, t3, ss, sso, COST, MULT):
    """Returns a dict step -> (usd array, exit-date array) for steps 0..4, all built from
    RAW points re-priced with this instrument's own cost/multiplier - never the ES wrapper's
    baked-in _COST_PTS."""
    o = np.asarray(df["open"].values, float)
    h = np.asarray(df["high"].values, float)
    l = np.asarray(df["low"].values, float)
    c = np.asarray(df["close"].values, float)
    did = np.asarray(df["day_id"].values)
    idx = df["_dt"]
    cost = COST[inst]
    mult = MULT[inst]

    out = {}

    # ---- STEP 0: plain crown mechanism, ATR stop 1.5, no tilt (r15d's CROWN, fade_bars=1) ----
    CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
                 exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60,
                 gate_mode="sq_on", gate_len=20, gate_bars=2, gate_ratio=1.0, gate_fired_k=3,
                 direction="both")
    r0 = t3.run_backtest(opens=o, highs=h, lows=l, closes=c, day_id=did, index=idx,
                         return_trades=True, **CROWN)
    tr0 = r0["trades"] if (r0 and r0.get("trades")) else []
    eb0 = np.array([int(x[0]) for x in tr0], int)
    xb0 = np.array([int(x[1]) for x in tr0], int)
    pts0 = np.array([float(x[2]) for x in tr0], float)
    usd0 = 1.0 * (pts0 - cost) * mult
    out[0] = (usd0, pd.DatetimeIndex(idx)[xb0])

    # ---- shared arrays for the structural-stop engine (kc_mult 1.5, gate_len 20 - both frozen,
    # ---- identical on every step from here on; _build_arrays does not depend on fade_bars or
    # ---- eod_cutoff, so it is built once and reused for fade=1 (steps 1-3) and fade=2 (step 4) ----
    arrs = ss._build_arrays(o, h, l, c, did, idx, 1.5, 20)
    EOD_CUTOFF = 1
    STRUCT_BUF = ss._STRUCT_BUF          # 0.0, frozen - same literal value on both instruments
    DIRECTION = "both"

    def raw_trades(fade_bars):
        tl = ss._simulate(o, h, l, c, arrs["n"], arrs["warm"], arrs["mom"], arrs["atr"],
                          arrs["fire"], arrs["rng_hi"], arrs["rng_lo"], arrs["gate_long"],
                          arrs["gate_short"], arrs["last_bar"], fade_bars, EOD_CUTOFF,
                          STRUCT_BUF, DIRECTION)
        eb = np.array([t[0] for t in tl], int)
        xb = np.array([t[1] for t in tl], int)
        pts = np.array([t[2] for t in tl], float)
        return eb, xb, pts

    # deep-squeeze compression state - instrument's own bars, frozen ratio definition (length 20,
    # BB 2.0, KC 1.5, threshold 0.85), tilt multiplier 1.5 - all read from the module, not retyped
    deep = ss._deep_state(h, l, c, did, idx)
    nn = len(deep)
    TILT_MULT = ss._TILT_MULT            # 1.5, frozen
    ordinal = sso._session_ordinal(did)
    OPEN_MULT = sso._OPEN_MULT           # 1.5, frozen
    OPEN_ORDINAL = sso._OPEN_ORDINAL     # 1, frozen

    # ---- STEP 1: structural stop, fade=1, NO tilt ----
    eb1, xb1, pts1 = raw_trades(1)
    usd1 = 1.0 * (pts1 - cost) * mult
    out[1] = (usd1, pd.DatetimeIndex(idx)[xb1])

    # ---- STEP 2: + deep-squeeze tilt (same trades as step 1, resized) ----
    dec1 = np.clip(eb1 - 1, 0, nn - 1)
    deep_mult1 = np.where(deep[dec1], TILT_MULT, 1.0)
    usd2 = deep_mult1 * (pts1 - cost) * mult
    out[2] = (usd2, pd.DatetimeIndex(idx)[xb1])

    # ---- STEP 3: + open-bar tilt on top (multiplicative, same trades) ----
    open_mult1 = np.where(ordinal[eb1] == OPEN_ORDINAL, OPEN_MULT, 1.0)
    combo1 = deep_mult1 * open_mult1
    usd3 = combo1 * (pts1 - cost) * mult
    out[3] = (usd3, pd.DatetimeIndex(idx)[xb1])

    # ---- STEP 4: structural stop, fade=2, + deep tilt + open-bar tilt (= full #369 stack) ----
    eb4, xb4, pts4 = raw_trades(2)
    dec4 = np.clip(eb4 - 1, 0, nn - 1)
    deep_mult4 = np.where(deep[dec4], TILT_MULT, 1.0)
    open_mult4 = np.where(ordinal[eb4] == OPEN_ORDINAL, OPEN_MULT, 1.0)
    combo4 = deep_mult4 * open_mult4
    usd4 = combo4 * (pts4 - cost) * mult
    out[4] = (usd4, pd.DatetimeIndex(idx)[xb4])

    return out


def main():
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r17a_r6")
    COST, MULT = r6.COST, r6.MULT   # {"NQ": 0.533, "ES": 0.363}, {"NQ": 20.0, "ES": 50.0}

    t3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "r17a_t3")
    ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "r17a_ss")
    sso = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SSO.py"), "r17a_sso")

    L = []

    def emit(x=""):
        L.append(x)
        print(x, flush=True)

    emit("TTM SQUEEZE r17a - does the validated ES stack TRANSFER to NQ, unchanged?")
    emit("window %s..%s, lockbox from %s, %.2f years" % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM, YRS))
    emit("ES: 0.363 pts/round trip, $50/pt.  NQ: 0.533 pts/round trip, $20/pt.")
    emit("frozen everywhere: kc_mult 1.5, entry cutoff 1, verification length 20, 60-minute gate,")
    emit("deep-squeeze tilt 1.5x at ratio<=0.85, open-bar tilt 1.5x on session ordinal 1, fade-after-2.")
    emit("")
    emit("COST-CONVENTION CHECK: this driver builds every trade from _build_arrays/_simulate, which")
    emit("return raw points with NO cost subtracted (TTMSQZ_3_0.py: 'PNL in points, costs downstream').")
    emit("Re-pricing is done here as usd = tilt_multiplier * (raw_pts - COST_PTS[inst]) * MULT[inst].")
    emit("ss._COST_PTS (the ES-only constant, 0.363) is read: %r -- and never used by this driver's own"
         % ss._COST_PTS)
    emit("pricing code (grep of this file's build_steps() shows no reference to ss._COST_PTS or")
    emit("ss._rescore, only to ss._build_arrays / ss._simulate / ss._deep_state / ss._STRUCT_BUF /")
    emit("ss._TILT_MULT, all of which are pure functions of the bars passed in, not of the instrument).")
    emit("")

    dfs = {inst: r6.load(inst, "30m", "RTH") for inst in ("ES", "NQ")}
    steps = {inst: build_steps(inst, dfs[inst], t3, ss, sso, COST, MULT) for inst in ("ES", "NQ")}

    # ============================= PARITY GATE (ES step 4 vs run #369) =============================
    emit("=" * 100)
    emit("PARITY GATE - ES step 4 (structural stop + deep tilt + open-bar tilt + fade-2) must")
    emit("reproduce run #369 to the dollar before any other number in this log is trusted.")
    emit("=" * 100)
    usd4_es, dates4_es = steps["ES"][4]
    w = stats(usd4_es)
    disc_m, hold_m, lb_m = slices(dates4_es, r6.LB_FROM)
    lb = stats(usd4_es[lb_m])
    WANT = dict(n=354, net=135884, pf=3.12, dd=4634, mar=1.826, lb_net=22739, lb_pf=9.89)
    checks = [
        ("n", w["n"], WANT["n"], 0),
        ("net $", w["net"], WANT["net"], 1.0),
        ("PF", w["pf"], WANT["pf"], 0.01),
        ("whole-run DD $", w["dd"], WANT["dd"], 1.0),
        ("MAR", w["mar"], WANT["mar"], 0.003),
        ("lockbox net $", lb["net"], WANT["lb_net"], 1.0),
        ("lockbox PF", lb["pf"], WANT["lb_pf"], 0.01),
    ]
    parity_ok = True
    for name, got, ref, tol in checks:
        ok = abs(got - ref) <= tol
        parity_ok = parity_ok and ok
        emit("  %-16s got %10s   published %10s   %s" % (
            name, ("%.3f" % got if isinstance(got, float) else got),
            ("%.3f" % ref if isinstance(ref, float) else ref), "OK" if ok else "MISMATCH"))
    emit("")
    out_path = os.path.join(ROOT, "tools", "data", "ttmsqz_r17a_nq_transfer.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if not parity_ok:
        emit("PARITY GATE FAILED - harness numbers below would not be trustworthy. Stopping.")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        raise SystemExit(1)
    emit("PARITY GATE PASSED (ES step 4 reproduces run #369 to the dollar). Continuing.")
    emit("")

    # ================================ PER-STEP, PER-INSTRUMENT TABLE ================================
    STEP_LABEL = {0: "step0 plain crown (ATR stop, no tilt)",
                  1: "step1 + structural stop",
                  2: "step2 + deep-squeeze tilt",
                  3: "step3 + open-bar tilt",
                  4: "step4 + fade-after-2 (=#369 stack)"}

    whole_stats = {inst: {} for inst in ("ES", "NQ")}
    slice_stats = {inst: {} for inst in ("ES", "NQ")}
    for inst in ("ES", "NQ"):
        for s in range(5):
            usd, dates = steps[inst][s]
            w = stats(usd)
            d_m, h_m, l_m = slices(dates, r6.LB_FROM)
            d = stats(usd[d_m]); h = stats(usd[h_m]); lb = stats(usd[l_m])
            whole_stats[inst][s] = w
            slice_stats[inst][s] = dict(discovery=d, holdout=h, lockbox=lb)

    emit("=" * 100)
    emit("WHOLE-RUN AND LOCKBOX, ES (reference) vs NQ (transfer)")
    emit("=" * 100)
    emit("%-38s %4s %6s %10s %8s %6s | %10s %6s" % (
        "step", "n", "PF", "net $", "DD $", "MAR", "LB net $", "LB PF"))
    for inst in ("ES", "NQ"):
        emit("-- %s --" % inst)
        for s in range(5):
            w = whole_stats[inst][s]
            lb = slice_stats[inst][s]["lockbox"]
            emit("%-38s %4d %6.2f %10s %8s %6.3f | %10s %6.2f" % (
                STEP_LABEL[s], w["n"], min(w["pf"], 99), "{:,.0f}".format(w["net"]),
                "{:,.0f}".format(w["dd"]), w["mar"], "{:,.0f}".format(lb["net"]), min(lb["pf"], 99)))
    emit("")

    emit("=" * 100)
    emit("DISCOVERY / HOLDOUT / LOCKBOX split (pre-lockbox trades split 60/40 by time)")
    emit("=" * 100)
    H = ("%-38s %s" % ("", "-------- discovery --------   -------- holdout --------   -------- lockbox --------"))
    emit(H)
    emit("%-38s %4s %6s %10s %8s   %4s %6s %10s %8s   %4s %6s %10s %8s" % (
        "step", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $"))
    for inst in ("ES", "NQ"):
        emit("-- %s --" % inst)
        for s in range(5):
            ss_ = slice_stats[inst][s]
            d, h, lb = ss_["discovery"], ss_["holdout"], ss_["lockbox"]
            emit("%-38s %4d %6.2f %10s %8s   %4d %6.2f %10s %8s   %4d %6.2f %10s %8s" % (
                STEP_LABEL[s], d["n"], min(d["pf"], 99), "{:,.0f}".format(d["net"]), "{:,.0f}".format(d["dd"]),
                h["n"], min(h["pf"], 99), "{:,.0f}".format(h["net"]), "{:,.0f}".format(h["dd"]),
                lb["n"], min(lb["pf"], 99), "{:,.0f}".format(lb["net"]), "{:,.0f}".format(lb["dd"])))
    emit("")

    # ================================ DIRECTION OF EACH STEP'S CHANGE ================================
    emit("=" * 100)
    emit("DIRECTION OF EACH STEP'S CHANGE - net $, whole-run MAR, lockbox net $ (this step vs the")
    emit("previous step), ES vs NQ. 'match' = both instruments moved the same way (or both flat).")
    emit("=" * 100)
    emit("%-30s %18s %18s %8s" % ("step", "ES delta", "NQ delta", "match?"))
    same_dir_count = 0
    for s in range(1, 5):
        es_prev, es_cur = whole_stats["ES"][s - 1], whole_stats["ES"][s]
        nq_prev, nq_cur = whole_stats["NQ"][s - 1], whole_stats["NQ"][s]
        es_lb_prev = slice_stats["ES"][s - 1]["lockbox"]["net"]
        es_lb_cur = slice_stats["ES"][s]["lockbox"]["net"]
        nq_lb_prev = slice_stats["NQ"][s - 1]["lockbox"]["net"]
        nq_lb_cur = slice_stats["NQ"][s]["lockbox"]["net"]

        d_net_es = es_cur["net"] - es_prev["net"]
        d_net_nq = nq_cur["net"] - nq_prev["net"]
        d_mar_es = es_cur["mar"] - es_prev["mar"]
        d_mar_nq = nq_cur["mar"] - nq_prev["mar"]
        d_lb_es = es_lb_cur - es_lb_prev
        d_lb_nq = nq_lb_cur - nq_lb_prev

        net_match = (d_net_es >= 0) == (d_net_nq >= 0)
        mar_match = (d_mar_es >= 0) == (d_mar_nq >= 0)
        lb_match = (d_lb_es >= 0) == (d_lb_nq >= 0)
        votes = int(net_match) + int(mar_match) + int(lb_match)
        step_matches = votes >= 2   # majority of the three signals agree in direction
        same_dir_count += int(step_matches)

        emit("%-30s net %+8s  MAR %+6.3f  LB %+7s   net %+8s  MAR %+6.3f  LB %+7s   %s" % (
            STEP_LABEL[s], "{:,.0f}".format(d_net_es), d_mar_es, "{:,.0f}".format(d_lb_es),
            "{:,.0f}".format(d_net_nq), d_mar_nq, "{:,.0f}".format(d_lb_nq),
            "SAME" if step_matches else "DIFFERENT"))
    emit("")
    emit("%d of 4 steps move net $ / MAR / lockbox net in the SAME direction on NQ as on ES "
         "(majority vote of the three)." % same_dir_count)
    emit("")

    # ================================ DAILY PROFIT CORRELATION, STEP 4 ================================
    emit("=" * 100)
    emit("DAILY-PROFIT CORRELATION, NQ step 4 vs ES step 4 (the number that matters if NQ step 4 were")
    emit("a second book leg). Round 9 found NQ squeeze cells correlate with the NQ crowns already -")
    emit("so a high number here is EXPECTED and does not by itself argue against adding the leg; it")
    emit("argues for sizing/portfolio treatment rather than treating the two as independent bets.")
    emit("=" * 100)
    usd_es4, dates_es4 = steps["ES"][4]
    usd_nq4, dates_nq4 = steps["NQ"][4]
    day_es = pd.DatetimeIndex(dates_es4).tz_convert("US/Eastern").normalize()
    day_nq = pd.DatetimeIndex(dates_nq4).tz_convert("US/Eastern").normalize()
    s_es = pd.Series(usd_es4, index=day_es).groupby(level=0).sum()
    s_nq = pd.Series(usd_nq4, index=day_nq).groupby(level=0).sum()
    all_days = s_es.index.union(s_nq.index)
    s_es = s_es.reindex(all_days, fill_value=0.0)
    s_nq = s_nq.reindex(all_days, fill_value=0.0)
    corr_all = float(np.corrcoef(s_es.values, s_nq.values)[0, 1])
    active = (s_es.values != 0) | (s_nq.values != 0)
    corr_active = float(np.corrcoef(s_es.values[active], s_nq.values[active])[0, 1]) if active.sum() > 2 else float("nan")
    emit("daily $ series length %d trading days (%d with a trade in either leg)" % (len(all_days), int(active.sum())))
    emit("correlation, all days (0-fill on no-trade days): %.3f" % corr_all)
    emit("correlation, days with a trade in either leg only: %.3f" % corr_active)
    emit("")

    # ================================ VERDICT ================================
    emit("=" * 100)
    emit("VERDICT")
    emit("=" * 100)
    emit("%d of 4 steps help on NQ in the same direction as on ES." % same_dir_count)

    nq0_hold_mar = slice_stats["NQ"][0]["holdout"]["mar"]
    nq4_hold_mar = slice_stats["NQ"][4]["holdout"]["mar"]
    nq4_lb = slice_stats["NQ"][4]["lockbox"]
    worth_validate = (nq4_lb["net"] > 0) and (nq4_lb["pf"] > 1.5) and (nq4_hold_mar > nq0_hold_mar)
    emit("NQ step 4 lockbox: net $%s, PF %.2f (positive & PF>1.5: %s)" % (
        "{:,.0f}".format(nq4_lb["net"]), min(nq4_lb["pf"], 99),
        "YES" if (nq4_lb["net"] > 0 and nq4_lb["pf"] > 1.5) else "NO"))
    emit("NQ holdout MAR: step0 %.3f -> step4 %.3f (%s)" % (
        nq0_hold_mar, nq4_hold_mar, "IMPROVED" if nq4_hold_mar > nq0_hold_mar else "NOT improved"))
    emit("NQ step 4 on its own looks worth a validate: %s" % ("YES" if worth_validate else "NO"))
    emit("")
    emit("Nothing here is crowned or queued. This is a scan result for the owner's call.")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\nlog -> tools/data/ttmsqz_r17a_nq_transfer.txt")


if __name__ == "__main__":
    main()

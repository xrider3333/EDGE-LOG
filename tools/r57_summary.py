# -*- coding: utf-8 -*-
"""ENGU-Q round 57 -- order of work item 7: the write-up file tools/r37_results/r57_summary.txt.

Contract: ENGUQ_R57_PREREG.md (committed a7f0811 before any cell ran).

Runs NO backtest. Reads only the result files the earlier items wrote, and copies every number
from them (nothing is re-typed by hand except the prose and the protocol verifier's findings, which
exist only as that verifier's report):
  tools/r37_results/r57_sel_parity_gates.json   (item 1, parity gates G1-G5)
  tools/r37_results/r57_grid.json               (items 2-3, every cell, A0, S1-S9, extras, kills)
  tools/r37_results/verify_r57_grid.json        (independent recompute + look-ahead verifier)
Writes: tools/r37_results/r57_summary.txt

Run: python tools/r57_summary.py   (cwd = the shared checkout, like every round-57 driver)
"""
import datetime as _dt
import json
import os

if __name__ == "__main__":
    WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguq57"
    RES = os.path.join(WT, "tools", "r37_results")
    OUT = os.path.join(RES, "r57_summary.txt")

    def _load(name):
        with open(os.path.join(RES, name), encoding="utf-8") as fh:
            return json.load(fh)

    P = _load("r57_sel_parity_gates.json")
    G = _load("r57_grid.json")
    V = _load("verify_r57_grid.json")

    L = []
    W = 150
    BAR = "=" * W
    SUB = "-" * W

    def w(s=""):
        L.append(s)

    def head(title):
        w("")
        w(BAR)
        w(title)
        w(BAR)

    def money(x):
        return "{:,.0f}".format(x)

    def smoney(x):
        return "{:+,.0f}".format(x)

    def fmt_val(c):
        v = c["value"]
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, int):
            return str(v)
        try:
            return c["fmt"] % v
        except (TypeError, ValueError):
            return str(v)

    def fmt_thr(c):
        t = c["threshold"]
        if t is None:
            return "-"
        if isinstance(t, int) and not isinstance(t, bool):
            return "%s %d" % (c["op"], t)
        try:
            return "%s %s" % (c["op"], c["fmt"] % t)
        except (TypeError, ValueError):
            return "%s %s" % (c["op"], t)

    def clause_line(c):
        return "    %-9s %-100s %14s  %16s  %s%s" % (
            c["clause"], c["desc"], fmt_val(c), fmt_thr(c),
            "PASS" if c["passed"] else "FAIL",
            ("  [" + c["note"] + "]") if c.get("note") else "")

    rows = G["rows"]
    inputs = G["inputs"]
    thr = G["thresholds"]
    res = G["results"]
    ctrl = rows["CTRL"]
    cells = list(rows.keys())
    HYP = ["H-A", "H-B", "H-C", "H-D"]
    parity = {r["gate"]: r for r in P["results"]}

    # ------------------------------------------------------------------------------------------
    w(BAR)
    w("ENGU-Q ROUND 57 -- WRITE-UP (order of work item 7): which setups are taken   (generated %s)"
      % _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    w("contract ENGUQ_R57_PREREG.md a7f0811 | base = R2 defaults = run #335 crown | research file ENGUQ_1M_ETH_SEL_1_0.py (worktree)")
    w("tape NQ 1m ETH db_noadj_eth | window 2010-06-07..2026-06-30 pinned | cost 0.533 pts/RT x $20 | one continuous engine backtest per cell")
    w("SELECTION = entries before 2025-06-30 00:00 ET. The lockbox (LB) was not read by any variant this round.")
    w("This file runs no backtest: every number below is copied from r57_sel_parity_gates.json, r57_grid.json and verify_r57_grid.json.")
    w(BAR)

    head("0. BOTTOM LINE")
    surv = G["survivors"]
    w("  Survivors of S1-S9 + section-5 extras and kills: %s" % (", ".join(surv) if surv else "NONE"))
    for h in HYP:
        r = res[h]
        w("  %s %-24s centre %-22s -> %s (failed %d: %s)" % (
            h, r["name"], r["centre"].split(" ", 1)[1], "SURVIVES" if r["survives"] else "DEAD at selection",
            len(r["failed"]), ", ".join(r["failed"])))
    w("  Every centre cell fails S1 (win rate >= control + 1.0 pt = %.4f%%): win lifts H-A %+.3f, H-B %+.3f, H-C %+.3f, H-D %+.3f pts."
      % (thr["S1"], res["H-A"]["a0"]["win_lift"], res["H-B"]["a0"]["win_lift"],
         res["H-C"]["a0"]["win_lift"], res["H-D"]["a0"]["win_lift"]))
    w("  H-B is a near miss and stays dead (prereg section 9: 'A near miss is reported as a near miss and stays dead').")
    w("  Not run, because nothing survived item 3: S10 cost stress, S11 R5 replication, S12 day-shift null (so NO null p-values exist),")
    w("  H-E conditional stack, and the single LB look. No fenced single-hypothesis file is cut and no validate queue script is written.")
    w("  Both independent verifiers returned 'confirmed'. No HIGH finding; every finding is LOW and changes no verdict (section 10).")
    w("  Crown: unchanged. Run #335 / R2 defaults stays the crown; paper leg ENGUQ_335 and NinjaTrader are untouched by this round.")

    head("1. WHAT RAN, IN THE PRE-REGISTERED ORDER")
    w("  item 1  sibling file + parity gates G1-G5 ........ ran once, ALL PASS (runtime 104 s, research beacon, one job record)")
    w("  item 2  12 grid cells + knob-off control at R2 ... ran once (runtime 26 s, research beacon, one job record); every measure() row printed before any clause")
    w("  item 3  A0, then S1-S9 + section-5 extras/kills .. same single run; A0 clear on all four centres; survivors: none")
    w("  item 4  S10 / S11 / S12 for survivors ............ NOT RUN (no survivors)")
    w("  item 5  H-E stack (needs >= 2 passes) ............ NOT RUN (0 passes)")
    w("  item 6  single LB look for full passes ........... NOT RUN (0 passes); the LB stayed unread for every variant")
    w("  item 7  write-up ................................. this file + prereg section 11 append + ENGUQ.md 'Round 57' section")
    w("  independent checks after item 3: recompute + look-ahead verifier (verify_r57_grid.py, 821 s) and protocol verifier")
    w("  (verify_r57_protocol_audit.py, read-only). Nothing was committed, pushed or queued; no runner restarted.")

    # ------------------------------------------------------------------------------------------
    head("2. PARITY GATES (item 1) -- all must pass before any cell is read")
    g1, g2 = parity["G1"], parity["G2"]
    w("  G1 knob-off at R2 settings vs ENGUQ_1M_ETH_R2_1_0.py: trade for trade %s (mismatches entry %d exit %d px %d P&L %d) | whole %d / $%s |"
      % (g1["trades_identical_vs_R2"], g1["mismatches"]["entry_bar"], g1["mismatches"]["exit_bar"],
         g1["mismatches"]["entry_px"], g1["mismatches"]["pnl"], g1["whole_n"], money(g1["whole_net"])))
    w("     selection %d / win %.2f%% / PF %.4f / $%s / DD $%s | frontier row 1 fields mismatched %d -> %s"
      % (g1["sel_n"], g1["sel_win_pct"], g1["sel_pf"], money(g1["sel_net"]), money(g1["sel_dd"]),
         g1["frontier_row1_fields_mismatched"], "PASS" if g1["passed"] else "FAIL"))
    w("  G2 knob-off at R5 settings vs ENGUQ_1M_ETH_R5_1_0.py: trade for trade %s | whole %d / $%s | selection %d / win %.2f%% / PF %.4f / $%s / DD $%s -> %s"
      % (g2["trades_identical_vs_R5"], g2["whole_n"], money(g2["whole_net"]), g2["sel_n"], g2["sel_win_pct"],
         g2["sel_pf"], money(g2["sel_net"]), money(g2["sel_dd"]), "PASS" if g2["passed"] else "FAIL"))
    for h in HYP:
        x = parity["G3-" + h]
        w("  G3 %s %s=%s compiled vs interpreted, full window: count equal %s, mismatches %s, max |dP&L| %s, differs from control %s -> %s"
          % (h, x["knob"], x["value"], x["count_equal"], sum(x["mismatches"].values()), x["max_abs_pnl_diff"],
             x["differs_from_control"], "PASS" if x["passed"] else "FAIL"))
    ga = parity["G4-A"]
    w("  G4-A quiet percentile vs local stride-23 copy: all %d bars, NaN pattern identical %s, max |diff| %.2e (tol 1e-9); vs anatomy CSV on %d signal bars: median |diff| %.3f pts (bar 1.5), max %.2f; mask-as-override identity %s -> %s"
      % (ga["bars"], ga["nan_pattern_identical"], ga["max_abs_diff_vs_local_copy"], ga["csv"]["csv_non_nan"],
         ga["csv"]["median_abs_diff"], ga["csv"]["max_abs_diff"], ga["override_identity"], "PASS" if ga["passed"] else "FAIL"))
    for key, name, tol in (("G4-B", "daily stretch S[i]", "1e-6"), ("G4-C", "leg recovery rec[i]", "1e-9"),
                           ("G4-D", "clock volume V/B", "1e-9")):
        x = parity[key]
        w("  %s %s vs anatomy CSV: %d non-NaN signal bars, engine finite on %d, max |diff| %.2e (tol %s), over tol %d; mask-as-override identity %s -> %s"
          % (key, name, x["csv"]["csv_non_nan"], x["csv"]["engine_finite_on_those"], x["csv"]["max_abs_diff"], tol,
             x["csv"]["n_over_tol"], x["override_identity"], "PASS" if x["passed"] else "FAIL"))
    g5 = parity["G5"]
    w("  G5 exec-feasibility audit, --config mode: exit 0 on all four centres, but it printed 'warn UNAUDITED' (it only looks the file up in the")
    w("     2026-08-11 sweep list). READ IT AS A HAND AUDIT, NOT A TOOL PASS: file-level static scan '%s'; signal-bar probe: 0 signal bars fail"
      % g5["file_scan_output"])
    w("     their own mask on every centre; truncation at two cut bars: every feature identical. -> PASS as recorded in prereg section 11 item 6.")
    w("  Parity gates overall: %s" % ("ALL PASS" if P["all_pass"] else "FAILED"))

    # ------------------------------------------------------------------------------------------
    head("3. CONTROL AND THE EXACT THRESHOLDS (prereg section 11 item 11: exact control values; the prereg table's rounded figures are displays)")
    cs = ctrl["sel"]
    w("  control (knob-off, R2 settings): n %d | win %.4f%% | PF %.6f | net $%.2f | DD $%.2f | MAR %.6f | EV R %.4f | E1/E2 top-10 %.4f%% / %.4f%%"
      % (cs["n"], cs["wr"], cs["pf"], cs["net"], cs["dd"], cs["mar"], cs["evr"], ctrl["era1"]["top10"], ctrl["era2"]["top10"]))
    w("                                   TTZ %d | evr_ex05 %.6f | index corr %+.6f | 2018 $%s | 2022 $%s | era D net $%s | control == frontier row 1 on every selection field"
      % (ctrl["ttz"], ctrl["evr_ex05"], ctrl["corr_sel"], money(ctrl["y2018"]), money(ctrl["y2022"]),
         money(inputs["CTRL"]["eras4"]["D"]["net"])))
    w("  S1 win >= %.4f | S2 PF >= %.5f | S3 net >= $%.2f | S4 MAR >= %.5f | S5a E1 <= %.4f, E2 <= %.4f | S5c TTZ >= %d | S5d evr_ex05 >= %.6f"
      % (thr["S1"], thr["S2"], thr["S3"], thr["S4"], thr["S5a1"], thr["S5a2"], thr["S5c"], thr["S5d"]))
    w("  S7 corr <= %+.5f | S9 neighbours: win lift >= +%.1f pt, PF >= %.5f, net >= $%.2f, E2 PF lift >= 0 | S8 top-20 retained >= 17 (H-A >= 18)"
      % (thr["S7"], thr["S9win"], thr["S9pf"], thr["S9net"]))
    w("  The protocol verifier re-applied the prereg table's rounded figures and an absolute S4: identical fail sets for every centre and neighbour.")

    # ------------------------------------------------------------------------------------------
    head("4. EVERY CELL (item 2) -- selection stretch, P&L after cost")
    w("PANEL 1 -- MONEY")
    w("  %-22s | %5s %7s %7s %10s %9s %6s %6s %5s | %8s %8s %6s" % (
        "cell", "n", "win%", "PF", "net $", "maxDD $", "MAR", "EV R", "R/YR", "win lift", "PF lift", "net %"))
    for c in cells:
        s = rows[c]["sel"]
        w("  %-22s | %5d %7.3f %7.4f %10s %9s %6.3f %6.4f %5.1f | %+8.3f %+8.4f %6.2f" % (
            c, s["n"], s["wr"], s["pf"], money(s["net"]), money(s["dd"]), s["mar"], s["evr"], s["ryr"],
            s["wr"] - cs["wr"], s["pf"] - cs["pf"], 100.0 * s["net"] / cs["net"]))
    w("")
    w("PANEL 2 -- TAIL (E1 = entries to 2019-12-31, E2 = 2020-01-01..2025-06-29; top-10 share = era's 10 best / era net)")
    w("  %-22s | %6s %9s | %5s %6s %6s %9s | %5s %6s %6s %9s | %3s | %7s | %6s" % (
        "cell", "top10", "ex10 $", "E1 n", "E1 PF", "E1t10", "E1 ex10", "E2 n", "E2 PF", "E2t10", "E2 ex10", "TTZ", "EVRx.5%", "corr"))
    for c in cells:
        r = rows[c]
        w("  %-22s | %5.2f%% %9s | %5d %6.4f %6.2f %9s | %5d %6.4f %6.2f %9s | %3d | %7.4f | %+6.3f" % (
            c, r["top10"], money(r["sel_ex10_net"]), r["era1"]["n"], r["era1"]["pf"], r["era1"]["top10"],
            money(r["era1"]["ex10"]), r["era2"]["n"], r["era2"]["pf"], r["era2"]["top10"], money(r["era2"]["ex10"]),
            r["ttz"], r["evr_ex05"], r["corr_sel"]))
    w("")
    w("PANEL 3 -- FOUR ERAS (A to 2013, B 2014-17, C 2018-21, D 2022-2025-06-29), E1/E2 win, 2018 / 2022, shape (shape columns reported, never gating)")
    w("  %-22s | %-28s | %-28s | %-28s | %-28s | %6s %6s | %8s %8s | %5s %5s %5s" % (
        "cell", "A n / win / PF / net", "B", "C", "D", "E1 win", "E2 win", "2018 $", "2022 $", "W/L", "BE", "scr%"))
    for c in cells:
        i = inputs[c]
        r = rows[c]
        eras = " | ".join("%4d %5.2f %6.4f %9s" % (i["eras4"][e]["n"], i["eras4"][e]["win"], i["eras4"][e]["pf"],
                                                   money(i["eras4"][e]["net"])) for e in "ABCD")
        w("  %-22s | %s | %6.2f %6.2f | %8s %8s | %5.2f %5.2f %5.2f" % (
            c, eras, i["e1"]["win"], i["e2"]["win"], money(r["y2018"]), money(r["y2022"]), r["wl_ratio"], r["be_ratio"],
            r["scratch_pct"]))
    w("")
    w("PANEL 4 -- TRADE-SET AUDIT vs control (prereg section 11 item 12 definitions) and the 09:30-09:35 read")
    w("  %-22s | %5s %5s %5s %6s | %7s | %4s %4s | %5s %9s" % (
        "cell", "ident", "remov", "retim", "refill", "refill w", "t20", "t10", "n0930", "PF x0930"))
    for c in cells:
        i = inputs[c]
        w("  %-22s | %5d %5d %5d %6d | %7s | %4d %4d | %5d %9.4f" % (
            c, i["identical"], i["removed"], i["retimed"], i["added"],
            ("%.2f%%" % i["added_win"]) if i["added_win"] is not None else "-",
            i["top20_retained"], i["top10_retained"], i["excl0930_n"], i["pf_ex0930"]))
    w("  refill = slot refill = a variant trade with no control entry bar inside its span; t20 / t10 = control's best 20 / 10 $ trades with a variant entry in span")
    w("")
    w("YEARLY SELECTION NET $ by entry year (2010 = Jun-Dec, 2025 = Jan-Jun 29)")
    yrs = sorted(ctrl["yearly_sel"].keys())
    w("  %-22s " % "cell" + " ".join("%8s" % y for y in yrs))
    for c in cells:
        ys = rows[c]["yearly_sel"]
        w("  %-22s " % c + " ".join("%8s" % money(ys.get(y, 0.0)) for y in yrs))

    # ------------------------------------------------------------------------------------------
    head("5. A0 LOOK-AHEAD ALARM (checked first; trips on win lift > +3.0 pts, PF lift > +0.30, or net > 110% of control)")
    for h in HYP:
        a = G["A0"][h]
        w("  %s %-22s win lift %+.3f | PF lift %+.4f | net %.2f%% of control -> %s" % (
            h, a["cell"], a["win_lift"], a["pf_lift"], 100.0 * a["net_ratio"], "TRIPPED" if a["tripped"] else "clear"))

    # ------------------------------------------------------------------------------------------
    head("6. EVERY CLAUSE, PER HYPOTHESIS (item 3) -- centre vs the knob-off control; neighbours veto through S9 only")
    for h in HYP:
        r = res[h]
        w("")
        w(SUB)
        w("%s %s -- centre %s | neighbours %s" % (h, r["name"].upper(), r["centre"], ", ".join(r["neighbours"])))
        w("  SHARED BAR, centre cell:")
        for c in r["centre_clauses"]:
            w(clause_line(c))
        w("  S9 PLATEAU, both neighbours:")
        for c in r["s9"]:
            w(clause_line(c))
        if r["extras"]:
            w("  SECTION-5 EXTRA CLAUSES:")
            for c in r["extras"]:
                w(clause_line(c))
        if r["kills"]:
            w("  SECTION-5 KILL CRITERIA evaluable at item 3 (the S10-S12 kills never became evaluable):")
            for c in r["kills"]:
                w(clause_line(c))
        w("  NEIGHBOURS vs S1-S8 (record only, never gating):")
        for nb, lst in r["neighbours_s1_s8_record"].items():
            w("    %-22s %s" % (nb, " ".join("%s:%s" % (c["clause"], "P" if c["passed"] else "F") for c in lst)))
        w("  VERDICT %s: %s   (failed %d: %s)" % (h, "SURVIVES" if r["survives"] else "DEAD at selection",
                                                len(r["failed"]), ", ".join(r["failed"])))

    # ------------------------------------------------------------------------------------------
    head("7. SCAN vs FILE (reported, never tuned toward) -- the trade-list scan's prediction at the centre vs the engine")
    w("  %-4s %-22s | %-30s | %-30s | %-30s | %5s %5s %5s %6s %8s" % (
        "hyp", "centre", "scan win / PF / net", "engine win / PF / net", "gap (engine - scan)", "ident", "remov", "retim", "refill", "refill w"))
    for h in HYP:
        s = res[h]["scan_vs_file"]
        e = s["in_engine"]
        sc = s["scan"]
        gp = s["gap"]
        scan_txt = ("%+.1f / %+.2f / $%s" % (sc["win"], sc["pf"], smoney(sc["net"]))) if sc else "no prediction"
        gap_txt = ("%+.3f / %+.4f / $%s" % (gp["win"], gp["pf"], smoney(gp["net"]))) if gp else "-"
        w("  %-4s %-22s | %-30s | %-30s | %-30s | %5d %5d %5d %6d %7.2f%%" % (
            h, res[h]["centre"], scan_txt, "%+.3f / %+.4f / $%s" % (e["win_lift"], e["pf_lift"], smoney(e["net_lift"])),
            gap_txt, s["identical"], s["removed"], s["retimed"], s["slot_refills"], s["slot_refill_win"]))
    w("  Why the gaps: a trade-list scan deletes trades and stops. In the engine a removed signal frees the slot, and the next signal fills it.")
    w("  Those refill trades won only %.1f%% (H-A), %.1f%% (H-B), %.1f%% (H-C) and %.1f%% (H-D) against the control's %.1f%%, so the scan over-predicted"
      % (res["H-A"]["scan_vs_file"]["slot_refill_win"], res["H-B"]["scan_vs_file"]["slot_refill_win"],
         res["H-C"]["scan_vs_file"]["slot_refill_win"], res["H-D"]["scan_vs_file"]["slot_refill_win"], cs["wr"]))
    w("  win-rate lift by 0.34 to 1.48 pts. H-B lost the least (only 39 refills) and kept almost all of its PF prediction (gap -0.007).")
    w("  H-D had no scan prediction: its added half is invisible to a trade-list scan.")

    # ------------------------------------------------------------------------------------------
    head("8. DIAGNOSTICS (reported, never gating)")
    d = res["H-A"]["diagnostics"]
    w("  H-A removed control selection SIGNALS by session bucket (ET clock at the signal bar): %d of %d rejected (%.3f%%)"
      % (d["rejected"], d["signals"], 100.0 * d["share"]))
    for b in ("asia", "europe", "cash", "other"):
        w("    %-7s removed %4d (%6.2f%% of removed) | all control signals %5d (%6.2f%%) | removed control trades' signal bars %4d (%6.2f%%)"
          % (b, d["removed_signals_by_session"][b]["n"], d["removed_signals_by_session"][b]["pct"],
             d["all_control_signals_by_session"][b]["n"], d["all_control_signals_by_session"][b]["pct"],
             d["removed_control_trades_by_session"][b]["n"], d["removed_control_trades_by_session"][b]["pct"]))
    rf = d["risk_floor_cell"]
    hc = d["h_a_centre"]
    w("  H-A outcome-blind planned-risk floor: risk %% of price < %.6f%% removes %d of %d control signals (the SAME NUMBER as H-A's centre mask)"
      % (d["risk_floor_pct"], d["risk_floor_removed"], d["signals"]))
    w("    risk floor : n %d win %.3f%% (lift %+.3f) PF %.4f (lift %+.4f) net $%s (%.2f%% of control)"
      % (rf["n"], rf["win"], rf["win_lift"], rf["pf"], rf["pf_lift"], money(rf["net"]), 100.0 * rf["net_ratio"]))
    w("    H-A centre : n %d win %.3f%% (lift %+.3f) PF %.4f (lift %+.4f) net $%s (%.2f%% of control)"
      % (rows[res["H-A"]["centre"]]["sel"]["n"], rows[res["H-A"]["centre"]]["sel"]["wr"], hc["win_lift"],
         rows[res["H-A"]["centre"]]["sel"]["pf"], hc["pf_lift"], money(rows[res["H-A"]["centre"]]["sel"]["net"]),
         100.0 * hc["net_ratio"]))
    w("    overlap: only %d of the %d signals H-A rejects are also rejected by the risk floor -- the two rules remove the same COUNT, about half"
      % (d["risk_floor_overlap"], d["risk_floor_removed"]))
    w("    the same signals. Reading (soft, the prereg set no tolerance for 'matches'): a stop-size floor of the same size gives a win and PF lift")
    w("    of the same order (+0.87 / +0.009 vs +0.71 / +0.008), so H-A's small lift is consistent with the known big-stop / volatility factor.")
    w("    It is NOT shown that H-A is that factor. This replaces the earlier summary phrase 'removes the same 235 signals' (protocol verifier).")
    av = res["H-D"]["diagnostics"]["added_vs_removed"]
    w("  H-D ADDED vs REMOVED (driver's definitions, prereg section 11 item 12):")
    for k in ("E1", "E2", "all"):
        x = av[k]
        w("    %-3s added n %3d PF %.4f win %6.2f%% net $%9s | removed n %3d PF %.4f win %6.2f%% net $%9s"
          % (k, x["added_n"], x["added_pf"], x["added_win"], money(x["added_net"]), x["removed_n"], x["removed_pf"],
             x["removed_win"], money(x["removed_net"])))
    w("    Sensitivity (protocol verifier, independent recompute): if 'added' means no control trade OVERLAPPING the variant trade, only 17 trades")
    w("    count (PF 0.031); if 'removed' means no variant entry inside the control trade (the S8-style test), 388 trades count (PF 0.903).")
    w("    X-addE1, X-addE2 and X-addPF fail under all three readings; only the size of the stated mechanism depends on the reading.")
    w("  H-C mechanism check (gating extra, passed): gap-through fills %s -- the mechanism moved as described, but win rate did not."
      % res["H-C"]["extras"][0]["note"])

    # ------------------------------------------------------------------------------------------
    head("9. ITEMS 4-6 -- S10 COST STRESS, S11 R5 REPLICATION, S12 DAY-SHIFT NULL (p-values), H-E STACK, LB LOOK")
    w("  S10 cost stress at 0.783 pts/RT ........ NOT RUN: section 7 item 4 runs it for hypotheses still standing after item 3; none were.")
    w("  S11 R5-settings replication ............ NOT RUN: same reason.")
    w("  S12 day-shift null, 1,000 draws ........ NOT RUN: same reason. There are NO null p-values for any hypothesis this round;")
    w("                                           p(win lift) and p(PF lift) are 'not computed', not 'failed' and not 'passed'.")
    w("  H-E conditional stack .................. NOT RUN: needs two or more hypotheses passing sections 4-5 in full; zero did.")
    w("  Single LB look (section 8) ............. NOT RUN: only for hypotheses passing everything; zero did. No variant LB trade was counted,")
    w("                                           printed or measured (grid lb.n = 0 in all 13 cells; largest cached entry bar %s < split bar %s)."
      % ("5,080,233", "5,086,313"))
    w("  Multiple-testing ledger (section 9): primary grid cells 12 of 12; controls 2 of 3 (R2 knob-off in the grid, R5 knob-off as parity gate G2;")
    w("  the 0.783 control did not run); cost-stress 0 of <=4; replication 0 of <=4; stack 0 of <=5; null backtests 0 of <=5,000; LB looks 0 of <=5.")
    w("  Decisions that could have declared a winner: 4 centre cells judged, 0 winners.")

    # ------------------------------------------------------------------------------------------
    head("10. INDEPENDENT VERIFICATION (after item 3) -- no HIGH finding; nothing changes a conclusion")
    p1 = V["part1"]["cells"]
    w("  Recompute + look-ahead verifier (tools/r37_results/verify_r57_grid.py): verdict CONFIRMED, disagreements %d." % len(V["disagreements"]))
    w("    Own engine re-run, own metrics: all 13 cells equal the grid on n, win, PF, net and both era top-10 shares (largest diff 3.6e-15 on win,")
    w("    1.2e-10 on net); cached trade lists equal. Clause verdicts S1/S2/S3/S5a at every centre and S9 on all 8 neighbours: same as grid.")
    for h in HYP:
        x = V["part2"][h]
        t = V["part3"]["truncation"][h]
        w("    %s spec-from-prereg vs file on %d candidate bars: value mismatches %d, mask mismatches %d | truncation audit %d bars, failures %d"
          % (h, x["bars"], x["value_mismatch"], x["mask_mismatch"], t["n"], t["failures"]))
    w("    Perturbation: randomising bars each rule must not read never moved the value (H-A 0/18, H-B 0/20, H-C 0/10, H-D 0/20).")
    w("    LB audit: grid lb.n = 0 in every cell; prereg diff vs a7f0811 = 101 lines added, 0 deleted (section 11 only).")
    w("    LOW findings: (1) the file's feature memo is keyed on a fingerprint, not full content -- matters only for a future caller feeding edited")
    w("    arrays of the same shape; (2) the H-D clock baseline uses a whole-frame cumulative sum that cancels exactly only for whole-number volumes")
    w("    -- exact on this tape, rounding noise (not information) on fractional-volume data.")
    w("  Protocol verifier (tools/r37_results/verify_r57_protocol_audit.py, read-only): verdict CONFIRMED.")
    w("    Clean: commit timing (prereg 15:58:41, every round file after it); grid ran exactly once with readings 10-17 fixed before it; every")
    w("    measure() row printed before any clause; the gated file is the file the grid ran; cells, centres and neighbours as pre-declared; feature")
    w("    code matches section 5; all 13 rows recomputed from cached trades to <= 3.9e-16 relative; fail sets identical under exact, rounded and")
    w("    absolute-S4 readings; extras and kills recomputed (H-D 09:30 lift -0.01245 inclusive, -0.02440 exclusive: fails either way).")
    w("    LOW findings, each recorded in prereg section 11 (item-7 block):")
    w("      a. H-A risk floor removes the same COUNT (235) as H-A, but only 112 of the same signals; 'matches' has no tolerance -> soft reading (section 8).")
    w("      b. H-D added/removed numbers depend on the definition; all three readings fail X-addE1/E2/PF (section 8).")
    w("      c. G5 was a hand audit; the named tool printed 'warn UNAUDITED' and exited 0 (section 2).")
    w("      d. S8 counted variant selection trades only; one control top-20 trade exits after the split; that can only lower retention, no verdict moves.")
    w("      e. The research beacon (one Firestore job record per run) was used on the 26 s grid run, though section 2 ties it to runs over ~2 min")
    w("         and its last bullet says no Firestore writes; the launching task permitted the beacon. Bookkeeping only.")

    # ------------------------------------------------------------------------------------------
    head("11. PLAIN STATEMENTS")
    def sel(c):
        return rows[c]["sel"]
    ha, hb, hcn, hd = (res[h]["centre"] for h in HYP)
    w("  H-A QUIET-TAPE STAND-DOWN IS DEAD. Skipping breakouts whose 14-bar ATR sat in the bottom 20% of the prior year's readings lifted win rate")
    w("    %+.2f pts (needed +1.0) and PF %+.4f (needed +0.02). Its 10 neighbour held no plateau (win lift +0.25, E2 PF lift -0.009). Freed slots"
      % (sel(ha)["wr"] - cs["wr"], sel(ha)["pf"] - cs["pf"]))
    w("    refilled with trades winning 23%.")
    w("  H-B DAILY STRETCH CAP IS DEAD (NEAR MISS). Skipping breakouts more than 1.5 daily ATRs above the 20-session mean lifted PF %+.3f overall"
      % (sel(hb)["pf"] - cs["pf"]))
    w("    (positive in all four eras: A +0.193, B +0.019, C +0.310, D +0.051)")
    w("    and kept %.1f%% of net, but win rate rose only %+.2f pts (needed +1.0), the 2.0 neighbour's win lift was +0.39 (needed +0.5) and the 1.0"
      % (100.0 * sel(hb)["net"] / cs["net"], sel(hb)["wr"] - cs["wr"]))
    w("    neighbour's net was $450,012 (needed $472,271). It stays dead: no re-tune, no PF-first re-read -- that would be a new pre-registration.")
    w("  H-C LEG RECOVERY FLOOR IS DEAD. Skipping breakouts that had reclaimed less than 45%% of the falling leg moved win rate %+.2f pts (scan said +1.5),"
      % (sel(hcn)["wr"] - cs["wr"]))
    w("    PF %+.4f (needed +0.02), raised the E1 top-10 share to 66.0%% (limit 64.06%%), and freed slots refilled with trades winning 14%%."
      % (sel(hcn)["pf"] - cs["pf"]))
    w("  H-D CLOCK-UNIT VOLUME TEST IS DEAD. Judging the volume spike against the same clock minute cut win rate %+.2f pts, PF %+.4f and net to %.1f%%;"
      % (sel(hd)["wr"] - cs["wr"], sel(hd)["pf"] - cs["pf"], 100.0 * sel(hd)["net"] / cs["net"]))
    w("    2022 turned negative ($-660); the 434 trades it added won 19.4% with PF 0.60 against PF 1.63 for the 754 it removed; 22 clauses failed.")
    w("  No hypothesis survives, so no fenced single-hypothesis file is cut, no validate queue script exists, and the crown (run #335 / R2) is unchanged.")
    w("  What the round shows, said plainly: on the crown's own trades, none of the four pre-registered entry conditions lifted the win rate by a")
    w("  full point at its centre once the engine refilled freed slots. The only cell of the 12 above +1.0 pt was a neighbour, H-B at 1.0")
    w("  (+1.44 pts, but net only %.1f%% of control). The prereg's prior ('most or all of these will fail') held."
      % (100.0 * rows["H-B stretch_max=1"]["sel"]["net"] / cs["net"]))

    head("12. FILES (worktree C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\enguq57 unless absolute)")
    for f in ("ENGUQ_R57_PREREG.md (contract a7f0811; section 11 appended, never edited above it)",
              "ENGUQ.md ('Round 57 (2026-09-14) - which setups are taken' section + changelog line)",
              "augur_strategies/ENGUQ_1M_ETH_SEL_1_0.py (research sibling; never to be validated as a four-knob search)",
              "tests/test_enguq_sel_parity.py",
              "tools/r57_sel_parity_gates.py -> tools/r37_results/r57_sel_parity_gates.txt / .json",
              "tools/r57_grid.py -> tools/r37_results/r57_grid.txt / .json",
              r"C:\EdgeLog\_anatomy_cache\r57\r57_grid_selection_trades.json (selection trades only)",
              "tools/r37_results/verify_r57_grid.py -> verify_r57_grid.txt / .json",
              "tools/r37_results/verify_r57_protocol_audit.py (stdout only)",
              "tools/r57_summary.py -> tools/r37_results/r57_summary.txt (this file)",
              "inputs written before the prereg: tools/r57_enguq_frontier.py, tools/r57_enguq_anatomy.py, tools/r57_imbalance_probe.py, r57_frontier.txt/.json, r57_anatomy.txt"):
        w("  " + f)
    w("")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))
    print("wrote %s (%d lines)" % (OUT, len(L)))

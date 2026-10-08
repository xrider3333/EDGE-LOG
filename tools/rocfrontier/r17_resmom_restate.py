"""RESMOM r1 - THE IN-HOLD LOOK-AHEAD RESTATEMENT (MANAGER #116 / #118 / #119 / #127, TTM's reviews #115 / #117 / #521; 2026-10-07).

The registered RES line (resmom_cells_daily_wf.csv, the 0.264 x RES inside L = #463 + 0.264 x RES = WF ROC @ $30k 120.82 / Sortino
3.916 / worst drawdown $36,526) was judged under r17_resmom's post_mode 'remove' (r17_resmom_export.py builds it with rm_build(...,
"remove"); Stage A judged the same reading): a name with ANY hygiene flag INSIDE THE HOLD (a registered split, the gap scan, TBIS, a
raw gap beyond +-50%, a spin-off ex-date) was removed before the ranking, and the random-name null drew from that filtered pool -
look-ahead (a name is dropped because of what happened after the rank).

This restates the SAME registered cells - same universe, scores, windows, fills, costs, borrow, dividends, audit, seeds - under
post_mode 'close' = MANAGER's hygiene edit S1 (#127; [HYG-S1] in the code - RESMOM's own [S1] is the score identity): the pinned
calendar carries no announcement date, so no in-hold event may remove a name at the rank. Every name flagged inside the hold STAYS,
valued on the split-safe path (a registered or calendar split inside the hold rides the split-adjusted series, never the raw one), and
a spin-off / stock-dividend ex-date e inside the hold (f < e <= x) CLOSES the position at the official close of e-1 (no mark, no
dividend whose ex-date is e or later, no borrow after it; the exit cost on that row). The null (500 draws, the registered seeds)
draws from the same pool with the same cut paths. No new search, no variant. The registered reading is re-run first (without its
null - Stage A's is on file) and must reproduce the registered line row for row, or nothing is written.

Beside it, as a REPORT with its count (MANAGER #127: '[A18]'s removal reading is printed beside it'): post_mode 'keep' - flagged names
kept on the split-safe path but an announced (calendar) split or a [D2] ex-date inside the hold REMOVES the name at the rank (the
reading of the withdrawn 2.93 draft, L 120.95, superseded before it shipped: the calendar cannot show those events were known at
the rank).

It prints the three readings side by side - each cell's WF ROC @ $30k with DD5 beside it (owner rule of 2026-10-07, MANAGER #120),
Sortino, worst drawdown, dollars a year, DO / rho_dd on #463's drawdown days, the null's p95, Stage A's checks - then the book line
L = #463 + 0.264 x RES on each (the frozen c of PREREG_RESMOM_LINE_R1.txt [F2]) with its 5 deepest episodes and its drawdown-day
profile (MDL r1's rule, r18_divrun.ref_build), L at the c the registered volatility rule gives on the restated RES (information
only), and the P&L of the positions with an in-hold event by kind (the four hygiene flags, a calendar split, a closed spin-off /
stock dividend, a calendar split the vendor's split factor does not show). Writes resmom_cells_daily_wf_close.csv (+ .sha256; the
registered file is never touched) and resmom_restate_close.json. WF only - every loader cuts its inputs before 2025-06-30; the
sealed year is never read.
usage (from the worktree, EDGELOG_ROOT = the shared checkout):  python tools/rocfrontier/r17_resmom_restate.py"""
import hashlib, json, os, sys, time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import r17_resmom as M                                                         # noqa: E402  (the registered harness + its 'close' and 'keep' readings)
import r18_divrun as DV                                                        # noqa: E402  (the reference book's one implementation: ref_build and its drawdown-day structure)
from augur_engine.drawdowns import dd5                                         # noqa: E402  (the owner's DD5, MANAGER #120)

JUDGED, REPORT = "close", "keep"                                               # the restatement's reading ([HYG-S1]) and the removal reading printed beside it as a report
OUT_CSV = os.path.join(M.OUT, f"resmom_cells_daily_wf_{JUDGED}.csv")
OUT_JSON = os.path.join(M.OUT, f"resmom_restate_{JUDGED}.json")
REG_CSV = os.path.join(M.OUT, "resmom_cells_daily_wf.csv")
SA_JSON = os.path.join(M.OUT, "resmom_stageA.json")
LINE_C = 0.264                                                                 # the frozen c of the RESMOM forward line ([F2]); the restatement keeps it
assert DV.REF_W == LINE_C
KINDS = M.HYG + ("calendar_split", "closed_spin", "calendar_split_no_factor_move")
LAB = {"remove": "the registered reading: every in-hold flag removed before the ranking",
       "close": "THE RESTATEMENT, MANAGER's hygiene edit S1: no in-hold removal, splits on the split-safe path, a spin-off / stock-dividend ex-date closes the position at the close before it",
       "keep": "REPORT, the removal reading: an announced split or a [D2] ex-date inside the hold removes the name at the rank"}


def dd5_of(x, dates):
    """DD5 on the same daily curve and stretch the ROC figure uses, with its episodes (deepest first)"""
    r = dd5(pd.Series(np.asarray(x, float), index=pd.DatetimeIndex(dates)))
    eps = [{"peak": str(e["peak"])[:10], "trough": str(e["trough"])[:10], "recovered": None if e.get("recovered") is None else str(e["recovered"])[:10], "depth": float(e["depth"]), "open": bool(e.get("open"))} for e in r["episodes"]]
    return {"dd5": float(r["dd5_usd"]), "n": int(r["n"]), "dd5_max_dd": float(r["max_dd"]), "one_episode": bool(r["one_episode"]), "episodes": eps}


def line_stats(x, dates):
    st = dict(M.R11.stats(np.asarray(x, float), pd.DatetimeIndex(dates)))
    st["usd_year"] = st["net"] / st["years"]
    st.update(dd5_of(x, dates))
    return st


def no_factor_move(W, f, x, cols):
    """(n,) bool: a calendar split ex-date in f < t <= x on which the vendor's split factor does not move (no registered split flag and |F_t / F_(t-1) - 1| <= 1%) - a split the split-safe series may not carry"""
    out = np.zeros(len(cols), bool)
    for k, j in enumerate(np.asarray(cols)):
        for t in np.flatnonzero(W.CSPL[f + 1:x + 1, j]) + f + 1:
            with np.errstate(invalid="ignore", divide="ignore"):
                moved = bool(W.chg[t, j]) or bool(abs(W.F[t, j] / W.F[t - 1, j] - 1.0) > 0.01)
            out[k] |= not moved
    return out


def flagged_pnl(W, L, run):
    """the base run's positions (run.pos: $ at the base costs) with an in-hold event: the four hygiene flags on r+1 .. x, a calendar split ex-date in f < t <= x, a [D2] spin-off / stock-dividend ex-date in f < t <= x
    (under 'close' the position was closed at the close before it), and a calendar split the vendor's factor does not show. Their P&L by kind ($; a position with two kinds counts under each), the count, the net and
    the 10 largest by |P&L|"""
    p = run.pos
    ri, col, side, pnl = (np.asarray(v) for v in (p.rec, p.col, p.side, p.pnl))
    ri, col, pnl = ri.astype(np.int64), col.astype(np.int64), pnl.astype(float)
    fl = np.zeros((len(KINDS), len(ri)), bool)
    for u in np.unique(ri):
        m = ri == u
        rec = L.recs[int(u)]
        fl[:4, m] = W.hyg(rec.r + 1, rec.x, col[m])
        fl[4, m] = M.csplit_hit(W, rec.f + 1, rec.x, col[m])
        fl[5, m] = M.spn_hit(W, rec.f + 1, rec.x, col[m])
        fl[6, m] = no_factor_move(W, rec.f, rec.x, col[m])
    hit = fl.any(axis=0)
    sel = np.flatnonzero(hit)
    top = sel[np.argsort(-np.abs(pnl[sel]), kind="stable")][:10]
    rows = [(float(pnl[i]), str(W.syms[col[i]]), f"{W.days[L.recs[int(ri[i])].f]:%Y-%m-%d}", "long" if side[i] > 0 else "short", "+".join(KINDS[q] for q in range(len(KINDS)) if fl[q, i])) for i in top]
    nfm = [f"{W.syms[col[i]]} {'long' if side[i] > 0 else 'short'} {W.days[L.recs[int(ri[i])].f]:%Y-%m-%d} ${pnl[i]:,.0f}" for i in np.flatnonzero(fl[6])]
    return {"positions": int(hit.sum()), "of_positions": int(len(ri)), "net_usd": float(pnl[hit].sum()), "by_kind_usd": {h: float(pnl[fl[q]].sum()) for q, h in enumerate(KINDS)},
            "positions_by_kind": {h: int(fl[q].sum()) for q, h in enumerate(KINDS)}, "top10": rows, "calendar_split_no_factor_move_list": nfm}


def cell_rec(c, xB, wf, dates):
    st = c["base"]
    out = {k: st.get(k) for k in ("net", "years", "roc", "sortino", "max_dd", "years_pos", "net_ex2020", "net_ex_best_days", "net_ex_best_pos", "n_pos", "n_units")}
    out["usd_year"] = st["net"] / st["years"]
    out.update(dd5_of(np.asarray(xB, float)[wf], dates))
    out["seat"] = {k: c["seat"].get(k) for k in ("DO", "rho_dd", "DO_ex_episode", "years_pos")}
    out["A2"] = {k: c["A2"].get(k) for k in ("c", "roc", "sortino", "max_dd", "net")}
    out["net_10bps"] = c["stress"]["10 bps"]["net"]
    return out


def counts(L):
    tot = {}
    for cn in L.cnt.values():
        for k, v in cn.items():
            tot[k] = tot.get(k, 0) + int(v)
    return tot


def main():
    pok = M.prereg_ok()
    t0 = time.time()
    sa_all = json.load(open(SA_JSON))
    sa = sa_all["stageA"]
    cal, _ = M.wide_load(M.S.LB0)
    B, _ = M.A13.load_463()
    bk, dd, S12 = M.book_checks(B)
    if not (bk["ok"] and dd["ok"]):
        M.refuse("restatement refused: #463 does not reproduce the registered WF numbers / drawdown structure (nothing written)")
    D = M.load_data(M.S.LB0)
    tbis = M.D15.load_tbis(M.S.LB0)
    es_frames, _ = M.D15.load_es(M.S.LB0)
    W = M.build_world(D, M.S.LB0, es_frames, tbis, cal)
    M.D15.release(D)
    M.apply_audit(W, M.read_audit())
    rows = M.A13.book_rows(B, W)
    csi = M.attach_calendar_splits(W, cal)
    print(f"prereg {'verified' if pok['verified'] else 'NOT verified'}; world ready ({time.time() - t0:.0f}s); the calendar's splits placed on the grid: {csi}", flush=True)
    idx = pd.DatetimeIndex(B.index)
    wf = B.mask(M.WF0, M.PRE_END)
    dates = idx[wf]
    # 1. the REGISTERED reading, re-run without its null (Stage A's is on file): it must be the registered line row for row
    t1 = time.time()
    resR, objR = M.evaluate(W, B, S12, rows, "remove", 0, 0)
    reg = pd.read_csv(REG_CSV)
    for cell in M.CELLS:
        got = np.asarray(objR.series[cell][0], float)[wf]
        if len(got) != len(reg) or np.abs(got - reg[cell].to_numpy(float)).max() > 0.01 or abs(resR["cells"][cell]["base"]["net"] - sa["cells"][cell]["base"]["net"]) > 0.01:
            M.refuse(f"restatement refused: the 'remove' reading's {cell} is not the registered line ({os.path.basename(REG_CSV)} / Stage A's net) - nothing written")
    print(f"'remove' (the registered reading) reproduces {os.path.basename(REG_CSV)} row for row and Stage A's nets, RES and RAW, to $0.01 ({time.time() - t1:.0f}s)", flush=True)
    # 2. the RESTATED reading ([HYG-S1]) and the removal reading beside it, each with its null (the registered seeds)
    got = {"remove": (resR, objR)}
    for pm in (JUDGED, REPORT):
        t1 = time.time()
        got[pm] = M.evaluate(W, B, S12, rows, pm, M.NREP, 0)
        print(f"'{pm}' reading + its {M.NREP}-draw null done ({time.time() - t1:.0f}s)", flush=True)
    out = {"what": "RESMOM r1 in-hold look-ahead restatement (MANAGER #116 / #118 / #119 / #127): registered post_mode 'remove'; restated under 'close' (MANAGER's hygiene edit S1); 'keep' (the removal reading) as a report",
           "registered_post_mode": "remove", "restated_post_mode": JUDGED, "report_post_mode": REPORT, "labels": LAB,
           "line_c": LINE_C, "wf": [f"{dates[0]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}"], "calendar_splits_on_grid": csi, "readings": {}}
    for pm in ("remove", JUDGED, REPORT):
        res, obj = got[pm]
        nul = sa["null"] if pm == "remove" else res["null"]
        rd = {"null": {"p95_max": nul["roc_max"]["p95"], "by_cell_p95": {c: nul["by_cell"][c]["p95"] for c in M.CELLS}, "source": "resmom_stageA.json (registered)" if pm == "remove" else "this run"},
              "counts": counts(obj.legs), "cells": {}}
        for cell in M.CELLS:
            c = res["cells"][cell]
            cr = cell_rec(c, obj.series[cell][0], wf, dates)
            cr["checks"] = sa["cells"][cell]["checks"] if pm == "remove" else c["checks"]
            cr["PASS"] = sa["cells"][cell]["PASS"] if pm == "remove" else c["PASS"]
            cr["checks_failed"] = [k for k, v in cr["checks"].items() if not v]
            try:                                                                # a report row: a failure here is printed, never fatal to the restatement
                cr["events"] = flagged_pnl(W, obj.legs, obj.runs[cell])
            except Exception as e:
                cr["events_error"] = f"{type(e).__name__}: {e}"
                print(f"  the in-hold events report for {pm} {cell} failed: {cr['events_error']}", flush=True)
            rd["cells"][cell] = cr
        out["readings"][pm] = rd
    # 3. the restated export (the registered file is never touched)
    ser = {pm: {cell: np.asarray(got[pm][1].series[cell][0], float)[wf] for cell in M.CELLS} for pm in (JUDGED, REPORT)}
    rst = ser[JUDGED]
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "book_mtm": np.asarray(B.raw, float)[wf], "RES": rst["RES"], "RAW": rst["RAW"]})
    assert (pd.to_datetime(df["date"]) < M.S.LB0).all(), "the export must stop before the sealed year"
    os.makedirs(M.OUT, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, float_format="%.6f", lineterminator="\n")
    sha = hashlib.sha256(open(OUT_CSV, "rb").read()).hexdigest()
    with open(OUT_CSV + ".sha256", "w") as f:
        f.write(sha + "  " + os.path.basename(OUT_CSV) + "\n")
    out["restated_csv"], out["restated_csv_sha256"] = OUT_CSV, sha
    # 4. the book line L on each reading at the frozen c, L at the rule's c on the restated RES (information only), #463 alone
    book = np.asarray(B.raw, float)[wf]
    regRES = reg["RES"].to_numpy(float)
    c_rule = out["readings"][JUDGED]["cells"]["RES"]["A2"]["c"]
    lines = {"registered L = #463 + 0.264 x RES ('remove')": book + LINE_C * regRES,
             f"RESTATED L = #463 + 0.264 x RES ('{JUDGED}', hygiene edit S1)": book + LINE_C * rst["RES"],
             f"report: #463 + 0.264 x RES ('{REPORT}', the removal reading)": book + LINE_C * ser[REPORT]["RES"]}
    if c_rule is not None and np.isfinite(c_rule):
        lines[f"#463 + {c_rule:.3f} x restated RES (the rule's c; information only)"] = book + c_rule * rst["RES"]
    lines["#463 alone"] = book
    out["lines"] = {k: line_stats(v, dates) for k, v in lines.items()}
    refs = {"registered": DV.ref_build(B, regRES), "restated": DV.ref_build(B, rst["RES"])}
    out["dd_day_profile"] = {k: r.structure for k, r in refs.items()}
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    # ---- the print
    print(f"\nRESMOM r1 RESTATEMENT, WF {dates[0]:%Y-%m-%d} .. {dates[-1]:%Y-%m-%d}")
    for pm in ("remove", JUDGED, REPORT):
        print(f"  '{pm}' = {LAB[pm]}")
    for pm in ("remove", JUDGED, REPORT):
        rd = out["readings"][pm]
        cn = rd["counts"]
        print(f"  [{pm}] null p95 (MAX over the 2 cells) {rd['null']['p95_max']:.2f} ({rd['null']['source']}); pool {cn.get('pool', 0):,}; removed in-hold: " + ", ".join(f"{k} {cn.get(k, 0)}" for k in ("post_split", "post_gap", "post_tbis", "post_jump", "post_spin", "post_calendar_split"))
              + ("; kept with an in-hold flag: " + ", ".join(f"{k} {cn.get(k, 0)}" for k in ("kept_split", "kept_gap", "kept_tbis", "kept_jump", "kept_flagged")) if pm != "remove" else "")
              + ("; kept with a calendar split in the hold " + f"{cn.get('kept_calendar_split', 0)}; closed at the close before a spin-off / stock-dividend ex-date {cn.get('closed_spin', 0)}" if pm == JUDGED else ""))
        for cell in M.CELLS:
            c = rd["cells"][cell]
            flag = " DRIVEN BY ONE EPISODE" if c["one_episode"] else ""
            print(f"    {cell}: ROC@30k {c['roc']:.2f} / DD5 ${c['dd5']:,.0f}{flag} | Sortino {c['sortino']:.3f} | worst DD ${c['max_dd']:,.0f} | net ${c['net']:,.0f} = ${c['usd_year']:,.0f} a year (10 bps ${c['net_10bps']:,.0f}) | "
                  f"DO {c['seat']['DO']:+.3f} rho_dd {c['seat']['rho_dd']:+.3f} | A2 c {c['A2']['c']:.4f} -> #463 + c x cell ROC {c['A2']['roc']:.2f} Sortino {c['A2']['sortino']:.3f} | Stage A {'PASS' if c['PASS'] else 'fail'} ({len(c['checks_failed'])} failed: {c['checks_failed']})")
            ev = c.get("events")
            if ev and ev["positions"]:
                print(f"      positions with an in-hold event {ev['positions']} of {ev['of_positions']}, net ${ev['net_usd']:,.0f}; by kind " + ", ".join(f"{h} ${v:,.0f} ({ev['positions_by_kind'][h]})" for h, v in ev["by_kind_usd"].items() if ev["positions_by_kind"][h]))
                print("      largest |P&L|: " + "; ".join(f"{s} {sd} {d} ${v:,.0f} [{h}]" for v, s, d, sd, h in ev["top10"]))
                if ev["calendar_split_no_factor_move_list"]:
                    print("      CALENDAR SPLIT THE VENDOR'S FACTOR DOES NOT SHOW (the split-safe path may carry it as a move): " + "; ".join(ev["calendar_split_no_factor_move_list"]))
    print("  THE BOOK LINE (WF daily; ROC @ $30k with DD5 beside it):")
    for k, st in out["lines"].items():
        flag = " DRIVEN BY ONE EPISODE" if st["one_episode"] else ""
        print(f"    {k}: ROC@30k {st['roc']:.2f} / DD5 ${st['dd5']:,.0f}{flag} | Sortino {st['sort']:.3f} | worst DD ${st['max_dd']:,.0f} | net ${st['net']:,.0f} = ${st['usd_year']:,.0f} a year")
        print("      5 deepest episodes: " + "; ".join(f"{e['peak']}..{e['trough']} ${e['depth']:,.0f}{' (open)' if e['open'] else ''}" for e in st["episodes"]))
    for k, g in out["dd_day_profile"].items():
        print(f"  L's drawdown days ({k}; MDL r1's rule): {g['episodes']} qualifying episodes of {g['all_episodes']}, {g['days']} DD days, {g['weeks']} DD weeks, deepest ${g['deepest']:,.0f}, by year {g['by_year']}")
    print(f"written {OUT_CSV} sha256 {sha} and {OUT_JSON} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()

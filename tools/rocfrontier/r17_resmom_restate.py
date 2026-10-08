"""RESMOM r1 - THE IN-HOLD LOOK-AHEAD RESTATEMENT (MANAGER #116 / #118 / #119, TTM's reviews #115 / #117 / #521; 2026-10-07).

The registered RES line (resmom_cells_daily_wf.csv, the 0.264 x RES inside L = #463 + 0.264 x RES = WF ROC @ $30k 120.82 / Sortino
3.916 / worst drawdown $36,526) was judged under r17_resmom's post_mode 'remove' (r17_resmom_export.py builds it with rm_build(...,
"remove"); Stage A judged the same reading): a name with ANY hygiene flag INSIDE THE HOLD (a registered split, the gap scan, TBIS, a
raw gap beyond +-50%, a spin-off ex-date) was removed before the ranking, and the random-name null drew from that filtered pool -
look-ahead (a name is dropped because of what happened after the rank).

This restates the SAME registered cells - same universe, scores, windows, fills, costs, borrow, dividends, audit, seeds - under
post_mode 'keep': a name flagged inside the hold STAYS, valued on the split-safe path (never the raw one); only events known at the
rank remove a name: an announced (calendar) split ex-date or a [D2] spin-off / stock-dividend ex-date inside the hold; the null
(500 draws, the registered seeds) draws from the kept pool. No new search, no variant. The registered reading is re-run first
(without its null - Stage A's is on file) and must reproduce the registered line row for row, or nothing is written.

It prints both readings side by side - each cell's WF ROC @ $30k with DD5 beside it (owner rule of 2026-10-07, MANAGER #120),
Sortino, worst drawdown, dollars a year, DO / rho_dd on #463's drawdown days, the null's p95, Stage A's checks - then the book line
L = #463 + 0.264 x RES on both (the frozen c of PREREG_RESMOM_LINE_R1.txt [F2]) with its 5 deepest episodes and its drawdown-day
profile (MDL r1's rule, r18_divrun.ref_build), L at the c the registered volatility rule gives on the restated RES (information
only), and the P&L of the kept flagged positions by flag. Writes resmom_cells_daily_wf_keep.csv (+ .sha256; the registered file is
never touched) and resmom_restate_keep.json. WF only - every loader cuts its inputs before 2025-06-30; the sealed year is never read.
usage (from the worktree, EDGELOG_ROOT = the shared checkout):  python tools/rocfrontier/r17_resmom_restate.py"""
import hashlib, json, os, sys, time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import r17_resmom as M                                                         # noqa: E402  (the registered harness + its 'keep' reading)
import r18_divrun as DV                                                        # noqa: E402  (the reference book's one implementation: ref_build and its drawdown-day structure)
from augur_engine.drawdowns import dd5                                         # noqa: E402  (the owner's DD5, MANAGER #120)

OUT_CSV = os.path.join(M.OUT, "resmom_cells_daily_wf_keep.csv")
OUT_JSON = os.path.join(M.OUT, "resmom_restate_keep.json")
REG_CSV = os.path.join(M.OUT, "resmom_cells_daily_wf.csv")
SA_JSON = os.path.join(M.OUT, "resmom_stageA.json")
LINE_C = 0.264                                                                 # the frozen c of the RESMOM forward line ([F2]); the restatement keeps it
assert DV.REF_W == LINE_C


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


def flagged_pnl(W, L, run):
    """the base run's positions (run.pos: $ at the base costs) whose name has a hygiene flag inside the hold (r+1 .. x): their P&L by flag ($; a position with two flags counts under each), the count, the net and the 10 largest by |P&L|"""
    p = run.pos
    ri, col, side, pnl = (np.asarray(v) for v in (p.rec, p.col, p.side, p.pnl))
    ri, col, pnl = ri.astype(np.int64), col.astype(np.int64), pnl.astype(float)
    fl = np.zeros((4, len(ri)), bool)
    for u in np.unique(ri):
        m = ri == u
        rec = L.recs[int(u)]
        fl[:, m] = W.hyg(rec.r + 1, rec.x, col[m])
    hit = fl.any(axis=0)
    sel = np.flatnonzero(hit)
    top = sel[np.argsort(-np.abs(pnl[sel]), kind="stable")][:10]
    rows = [(float(pnl[i]), str(W.syms[col[i]]), f"{W.days[L.recs[int(ri[i])].f]:%Y-%m-%d}", "long" if side[i] > 0 else "short", "+".join(M.HYG[q] for q in range(4) if fl[q, i])) for i in top]
    return {"positions": int(hit.sum()), "of_positions": int(len(ri)), "net_usd": float(pnl[hit].sum()), "by_flag_usd": {h: float(pnl[fl[q]].sum()) for q, h in enumerate(M.HYG)},
            "positions_by_flag": {h: int(fl[q].sum()) for q, h in enumerate(M.HYG)}, "top10": rows}


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
    # 2. the RESTATED reading, its null on the kept pool
    t1 = time.time()
    resK, objK = M.evaluate(W, B, S12, rows, "keep", M.NREP, 0)
    print(f"'keep' reading + its {M.NREP}-draw null done ({time.time() - t1:.0f}s)", flush=True)
    out = {"what": "RESMOM r1 in-hold look-ahead restatement (MANAGER #116 / #118 / #119): registered post_mode 'remove' vs 'keep'", "registered_post_mode": "remove",
           "line_c": LINE_C, "wf": [f"{dates[0]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}"], "calendar_splits_on_grid": csi, "readings": {}}
    for pm, res, obj in (("remove", resR, objR), ("keep", resK, objK)):
        nul = sa["null"] if pm == "remove" else res["null"]
        rd = {"null": {"p95_max": nul["roc_max"]["p95"], "by_cell_p95": {c: nul["by_cell"][c]["p95"] for c in M.CELLS}, "source": "resmom_stageA.json (registered)" if pm == "remove" else "this run"},
              "counts": counts(obj.legs), "cells": {}}
        for cell in M.CELLS:
            c = res["cells"][cell]
            cr = cell_rec(c, obj.series[cell][0], wf, dates)
            cr["checks"] = sa["cells"][cell]["checks"] if pm == "remove" else c["checks"]
            cr["PASS"] = sa["cells"][cell]["PASS"] if pm == "remove" else c["PASS"]
            cr["checks_failed"] = [k for k, v in cr["checks"].items() if not v]
            if pm == "keep":
                try:                                                            # a report row: a failure here is printed, never fatal to the restatement
                    cr["flagged"] = flagged_pnl(W, obj.legs, obj.runs[cell])
                except Exception as e:
                    cr["flagged_error"] = f"{type(e).__name__}: {e}"
                    print(f"  the kept-flagged report for {cell} failed: {cr['flagged_error']}", flush=True)
            rd["cells"][cell] = cr
        out["readings"][pm] = rd
    # 3. the restated export (the registered file is never touched)
    keep = {cell: np.asarray(objK.series[cell][0], float)[wf] for cell in M.CELLS}
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "book_mtm": np.asarray(B.raw, float)[wf], "RES": keep["RES"], "RAW": keep["RAW"]})
    assert (pd.to_datetime(df["date"]) < M.S.LB0).all(), "the export must stop before the sealed year"
    os.makedirs(M.OUT, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, float_format="%.6f", lineterminator="\n")
    sha = hashlib.sha256(open(OUT_CSV, "rb").read()).hexdigest()
    with open(OUT_CSV + ".sha256", "w") as f:
        f.write(sha + "  " + os.path.basename(OUT_CSV) + "\n")
    out["keep_csv"], out["keep_csv_sha256"] = OUT_CSV, sha
    # 4. the book line L on both readings at the frozen c, L at the rule's c on the restated RES (information only), #463 alone
    book = np.asarray(B.raw, float)[wf]
    regRES = reg["RES"].to_numpy(float)
    c_keep = out["readings"]["keep"]["cells"]["RES"]["A2"]["c"]
    lines = {"registered L = #463 + 0.264 x RES ('remove')": book + LINE_C * regRES, "restated L = #463 + 0.264 x RES ('keep')": book + LINE_C * keep["RES"]}
    if c_keep is not None and np.isfinite(c_keep):
        lines[f"#463 + {c_keep:.3f} x restated RES (the rule's c; information only)"] = book + c_keep * keep["RES"]
    lines["#463 alone"] = book
    out["lines"] = {k: line_stats(v, dates) for k, v in lines.items()}
    refs = {"registered": DV.ref_build(B, regRES), "restated": DV.ref_build(B, keep["RES"])}
    out["dd_day_profile"] = {k: r.structure for k, r in refs.items()}
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    # ---- the print
    print(f"\nRESMOM r1 RESTATEMENT, WF {dates[0]:%Y-%m-%d} .. {dates[-1]:%Y-%m-%d}: 'remove' = the registered reading (in-hold flags removed before the ranking); 'keep' = flagged names kept on the split-safe path, only an announced split "
          "or a [D2] ex-date inside the hold removes a name, the null on the kept pool")
    for pm in ("remove", "keep"):
        rd = out["readings"][pm]
        cn = rd["counts"]
        print(f"  [{pm}] null p95 (MAX over the 2 cells) {rd['null']['p95_max']:.2f} ({rd['null']['source']}); pool {cn.get('pool', 0):,}; removed in-hold: " + ", ".join(f"{k} {cn.get(k, 0)}" for k in ("post_split", "post_gap", "post_tbis", "post_jump", "post_spin", "post_calendar_split"))
              + ("; kept with an in-hold flag: " + ", ".join(f"{k} {cn.get(k, 0)}" for k in ("kept_split", "kept_gap", "kept_tbis", "kept_jump", "kept_flagged")) if pm == "keep" else ""))
        for cell in M.CELLS:
            c = rd["cells"][cell]
            flag = " DRIVEN BY ONE EPISODE" if c["one_episode"] else ""
            print(f"    {cell}: ROC@30k {c['roc']:.2f} / DD5 ${c['dd5']:,.0f}{flag} | Sortino {c['sortino']:.3f} | worst DD ${c['max_dd']:,.0f} | net ${c['net']:,.0f} = ${c['usd_year']:,.0f} a year (10 bps ${c['net_10bps']:,.0f}) | "
                  f"DO {c['seat']['DO']:+.3f} rho_dd {c['seat']['rho_dd']:+.3f} | A2 c {c['A2']['c']:.4f} -> #463 + c x cell ROC {c['A2']['roc']:.2f} Sortino {c['A2']['sortino']:.3f} | Stage A {'PASS' if c['PASS'] else 'fail'} ({len(c['checks_failed'])} failed: {c['checks_failed']})")
            if c.get("flagged"):
                fl = c["flagged"]
                print(f"      kept flagged positions {fl['positions']} of {fl['of_positions']}, net ${fl['net_usd']:,.0f}; by flag " + ", ".join(f"{h} ${v:,.0f} ({fl['positions_by_flag'][h]})" for h, v in fl["by_flag_usd"].items()))
                print("      largest |P&L|: " + "; ".join(f"{s} {sd} {d} ${v:,.0f} [{h}]" for v, s, d, sd, h in fl["top10"]))
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

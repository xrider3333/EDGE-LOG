"""RESMOM r1 - the forward BOOK line's GATE ([F1] of PREREG_RESMOM_LINE_R1.txt, MANAGER #70): RES's DO over #463's 460 WF drawdown days
against the 95th percentile of the registered random-name null's DO (the Stage A draws: same code, same seed [20261005, 0, 0]), and RES's
drawdown-day dollars without its best #463 drawdown episode. RAW reported beside. WF only - every input is cut before 2025-06-30 by the
harness's own loaders; the sealed year is never read.   usage (from the worktree, EDGELOG_ROOT = the shared checkout):
    python tools/rocfrontier/r17_resmom_gate.py"""
import hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r17_resmom as M                                                         # noqa: E402  (the registered harness, unchanged)

LINE_PREREG = os.path.join(HERE, "PREREG_RESMOM_LINE_R1.txt")
LINE_SHA = "9ab77351453c4561cf9f852fe6aea48027a181d3764d7b811d5ea416f2f28211"                                              # LF sha256 of PREREG_RESMOM_LINE_R1.txt as committed before this ran
OUT = os.path.join(M.OUT, "resmom_line_gate.json")


def sha_lf(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def main():
    if sha_lf(LINE_PREREG) != LINE_SHA:
        M.refuse("gate refused: PREREG_RESMOM_LINE_R1.txt is not the registered text (nothing computed)")
    pok = M.prereg_ok()                                                        # PREREG_RESMOM_R1.txt unchanged (its sha and committed blob)
    print("line registration: PREREG_RESMOM_LINE_R1.txt sha256 matches; " + ("RESMOM prereg verified" if pok["verified"] else "RESMOM prereg NOT verified"))
    t0 = time.time()
    cal, _ = M.wide_load(M.S.LB0)
    B, _ = M.A13.load_463()
    bk, dd, S12 = M.book_checks(B)
    if not (bk["ok"] and dd["ok"]):
        M.refuse("gate refused: #463 does not reproduce the registered WF numbers / drawdown structure (nothing computed)")
    D = M.load_data(M.S.LB0)
    tbis = M.D15.load_tbis(M.S.LB0)
    es_frames, _ = M.D15.load_es(M.S.LB0)
    audit = M.read_audit()
    W = M.build_world(D, M.S.LB0, es_frames, tbis, cal)
    M.D15.release(D)
    M.apply_audit(W, audit)
    rows = M.A13.book_rows(B, W)
    L = M.rm_build(W, M.WF0, M.PRE_END, "remove")                              # the REGISTERED reading, as Stage A built it
    acc = M.rm_null(W, L, M.NREP, 0)                                           # the registered null draws (vcode 0 = Stage A's registered streams)
    book_loss = -float(S12.x[S12.dd].sum())
    res = {"line_prereg_sha256_lf": LINE_SHA, "resmom_prereg_sha256_lf": M.PREREG_SHA, "harness_sha256": sha_lf(M.__file__), "gate_sha256": sha_lf(__file__),
           "null_draws": int(M.NREP), "seed": M.SEED, "book_dd_days": int(S12.n_dd_days), "book_loss_over_dd_days": book_loss, "cells": {}}
    for cell in M.CELLS:
        base = M.run_cell(W, M.cell_leg(L, cell), M.D15.l1_cfg(), pos=True)
        xB = M.D15.to_B(base.x, rows, B.n)
        seat = M.D15.seat_measure(S12, xB)
        eps = M.D15.episodes_table(S12, xB)
        dd_usd = float(np.asarray(xB, float)[S12.rows][S12.dd].sum())
        best = max(eps, key=lambda e: e["cell_pnl"])
        roc_n, rho_n, do_n = M.D15.null_cell(S12, acc[cell], rows, B.n)
        roc_p95 = M.D15.pctl(roc_n, 95)                                       # must equal Stage A's by_cell p95: the draws ARE the Stage A draws
        sa = json.load(open(os.path.join(M.OUT, "resmom_stageA.json")))["stageA"]["null"]["by_cell"][cell]["p95"]
        if abs(roc_p95 - sa) > 1e-9:
            M.refuse(f"gate refused: the null draws do not reproduce Stage A's ({cell} ROC p95 {roc_p95} vs {sa}) - nothing judged")
        do_n = np.asarray(do_n, float)
        fin = do_n[np.isfinite(do_n)]
        p95 = float(np.percentile(fin, 95))
        pct = float((fin < seat["DO"]).mean() * 100.0)
        c = {"net_wf": float(np.asarray(xB, float)[S12.rows].sum()), "DO": seat["DO"], "rho_dd": seat["rho_dd"], "dd_days_usd": dd_usd,
             "best_episode": {k: best[k] for k in ("peak", "trough", "dd_days", "cell_pnl")}, "dd_days_usd_without_best_episode": dd_usd - best["cell_pnl"],
             "episodes_positive": int(sum(1 for e in eps if e["cell_pnl"] > 0)), "episodes": len(eps),
             "null_DO": {"p5": float(np.percentile(fin, 5)), "p50": float(np.percentile(fin, 50)), "p95": p95, "finite": int(len(fin)), "dd_usd_p95": p95 * book_loss},
             "DO_percentile_in_null": pct, "null_roc_p95_reproduces_stage_a": roc_p95}
        c["gate_a"] = bool(seat["DO"] > p95)
        c["gate_b"] = bool(c["dd_days_usd_without_best_episode"] > 0)
        res["cells"][cell] = c
        print(f"{cell}: WF net ${c['net_wf']:,.0f}; over #463's {S12.n_dd_days} drawdown days ${dd_usd:,.0f} (DO {seat['DO']:+.3f}, rho_dd {seat['rho_dd']:+.3f}; "
              f"{c['episodes_positive']} of {c['episodes']} episodes positive); random-name null DO p5 / p50 / p95 {c['null_DO']['p5']:+.3f} / {c['null_DO']['p50']:+.3f} / "
              f"{p95:+.3f} (= ${p95 * book_loss:,.0f}); RES-style DO sits at the null's {pct:.1f}th percentile; without its best episode "
              f"({best['peak']} .. {best['trough']}, ${best['cell_pnl']:,.0f}): ${c['dd_days_usd_without_best_episode']:,.0f}", flush=True)
    r = res["cells"]["RES"]
    res["gate_pass"] = bool(r["gate_a"] and r["gate_b"])
    res["verdict"] = ("GATE PASS - the forward BOOK line opens ([F2])" if res["gate_pass"] else
                      "GATE FAIL - book-add report PASS, drawdown help at chance level; NO line opens")
    print(f"[F1] (a) RES's DO above the null's 95th percentile: {'YES' if r['gate_a'] else 'NO'}; (b) positive without its best episode: {'YES' if r['gate_b'] else 'NO'} -> {res['verdict']}")
    print(f"gate took {time.time() - t0:.0f}s")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print("written", OUT)


if __name__ == "__main__":
    main()

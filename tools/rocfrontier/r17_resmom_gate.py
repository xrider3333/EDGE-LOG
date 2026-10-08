"""RESMOM r1 - the forward BOOK line's GATE ([F1] of PREREG_RESMOM_LINE_R1.txt, MANAGER #70): RES's DO over #463's 460 WF drawdown days
against the 95th percentile of the registered random-name null's DO (the Stage A draws: same code, same seed [20261005, 0, 0]), and RES's
drawdown-day dollars without its best #463 drawdown episode. RAW reported beside. WF only - every input is cut before 2025-06-30 by the
harness's own loaders; the sealed year is never read.   usage (from the worktree, EDGELOG_ROOT = the shared checkout):
    python tools/rocfrontier/r17_resmom_gate.py                       the REGISTERED reading (r17_resmom's post_mode 'remove') -> resmom_line_gate.json, exactly as it always ran
    python tools/rocfrontier/r17_resmom_gate.py --post-mode close     NOTE 2 [N9] (PREREG_RESMOM_LINE_R1_NOTE2.txt): the same gate, [F1] unchanged in its rule, re-read BEFORE the first rank under MANAGER's hygiene edit S1 (post_mode 'close'):
                                                                      RES's DO over #463's 460 drawdown days against the 95th percentile of the S1 null's DO (the restatement's 500 draws: same code, same seed [20261005, 0, 0], refused unless
                                                                      their ROC p95 reproduce resmom_restate_close.json's by cell) and RES's drawdown-day dollars without its best episode -> resmom_line_gate_close.json (the
                                                                      registered resmom_line_gate.json is never written by this run); a FAIL under S1 means no line opens on 2026-10-30: nothing is ranked and the lane tells MANAGER"""
import hashlib, json, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r17_resmom as M                                                         # noqa: E402  (the registered harness, unchanged)

LINE_PREREG = os.path.join(HERE, "PREREG_RESMOM_LINE_R1.txt")
LINE_SHA = "9ab77351453c4561cf9f852fe6aea48027a181d3764d7b811d5ea416f2f28211"                                              # LF sha256 of PREREG_RESMOM_LINE_R1.txt as committed before this ran
NOTE2_PREREG = os.path.join(HERE, "PREREG_RESMOM_LINE_R1_NOTE2.txt")
NOTE2_SHA = "1382813fa89148a8183700f37df08d9ad6b6eea67ac4b4bf099288bc9280d23d"                                             # LF sha256 of NOTE 2 as committed (39862c9d): [N9] is the rule of the --post-mode close run
OUT = os.path.join(M.OUT, "resmom_line_gate.json")                             # the registered gate's record: the default run writes it as it always did; the S1 re-read NEVER does
OUT_CLOSE = os.path.join(M.OUT, "resmom_line_gate_close.json")                 # [N9] the S1 re-read's record
RESTATE_JSON = os.path.join(M.OUT, "resmom_restate_close.json")                # the restatement's record: readings -> close -> null -> by_cell_p95 is what the S1 draws must reproduce
STAGE_A_JSON = os.path.join(M.OUT, "resmom_stageA.json")                       # Stage A's record: the registered draws' ROC p95 by cell


def sha_lf(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def parse_args(argv):
    """[] -> 'remove' (the registered gate, exactly as it always ran); ['--post-mode', 'close'] or ['--post-mode=close'] -> 'close' (NOTE 2 [N9]); '--post-mode remove' is the default spelt out; anything else refuses (nothing computed)"""
    args = list(argv)
    if not args:
        return "remove"
    if args[0].startswith("--post-mode="):
        val, rest = args[0].split("=", 1)[1], args[1:]
    elif args[0] == "--post-mode" and len(args) >= 2:
        val, rest = args[1], args[2:]
    else:
        M.refuse(f"gate refused: unknown argument(s) {args} - the one option is --post-mode close (nothing computed)")
    if val not in ("remove", "close") or rest:
        M.refuse(f"gate refused: --post-mode takes 'close' (NOTE 2 [N9]) or 'remove' (the registered reading, the default) and nothing else; got {args} (nothing computed)")
    return val


def reference_p95(post_mode, cell):
    """the ROC p95 the null draws of this reading must reproduce: Stage A's for the registered reading, the restatement's (readings -> close -> null -> by_cell_p95) for the S1 one"""
    if post_mode == "close":
        with open(RESTATE_JSON, encoding="utf-8") as f:
            return float(json.load(f)["readings"]["close"]["null"]["by_cell_p95"][cell])
    with open(STAGE_A_JSON) as f:
        return json.load(f)["stageA"]["null"]["by_cell"][cell]["p95"]


def registered_gate():
    """the registered gate's numbers (resmom_line_gate.json) for the S1 re-read to print beside its own -> (record or None): per cell DO, the null's p95, the dollars without the best episode and the episode, the verdict"""
    if not os.path.exists(OUT):
        return None
    with open(OUT, encoding="utf-8") as f:
        g = json.load(f)
    return {"gate_pass": g.get("gate_pass"), "verdict": g.get("verdict"), "cells": {c: {"DO": v["DO"], "null_DO_p95": v["null_DO"]["p95"], "dd_days_usd": v["dd_days_usd"], "dd_days_usd_without_best_episode": v["dd_days_usd_without_best_episode"],
                                                                                         "best_episode": v["best_episode"], "episodes_positive": v["episodes_positive"], "episodes": v["episodes"]} for c, v in g["cells"].items()}}


def same_results(a, b, tol=1e-9):
    """two gate records agree: the same keys, numbers within tol (relative to the larger), everything else equal - the time-stamped / code-stamped fields (gate_sha256, harness_sha256) are not part of the result"""
    skip = {"gate_sha256", "harness_sha256"}
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a) - skip, set(b) - skip
        return ka == kb and all(same_results(a[k], b[k], tol) for k in ka)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same_results(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return a == b


def main(argv=None):
    post_mode = parse_args(sys.argv[1:] if argv is None else argv)
    s1 = post_mode == "close"
    if sha_lf(LINE_PREREG) != LINE_SHA:
        M.refuse("gate refused: PREREG_RESMOM_LINE_R1.txt is not the registered text (nothing computed)")
    if s1 and (not os.path.exists(NOTE2_PREREG) or sha_lf(NOTE2_PREREG) != NOTE2_SHA):
        M.refuse("gate refused: PREREG_RESMOM_LINE_R1_NOTE2.txt is not the registered text - [N9] is the rule of this run (nothing computed)")
    pok = M.prereg_ok()                                                        # PREREG_RESMOM_R1.txt unchanged (its sha and committed blob)
    print("line registration: PREREG_RESMOM_LINE_R1.txt sha256 matches; " + ("NOTE 2 (LF sha256 1382813f...) matches; " if s1 else "") + ("RESMOM prereg verified" if pok["verified"] else "RESMOM prereg NOT verified"))
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
    if s1:
        M.attach_calendar_splits(W, cal)                                       # CHOICE [L30]: as the restatement built its world (it only counts the calendar's splits under 'close'; the pool and the paths do not read it)
    L = M.rm_build(W, M.WF0, M.PRE_END, post_mode)                             # 'remove': the REGISTERED reading, as Stage A built it; 'close': the S1 reading, as the restatement built it ([N9])
    acc = M.rm_null(W, L, M.NREP, 0)                                           # the null draws (vcode 0 = the registered streams, seeds [20261005, cell, 0]): Stage A's under 'remove', the restatement's under 'close'
    book_loss = -float(S12.x[S12.dd].sum())
    res = {"line_prereg_sha256_lf": LINE_SHA, "resmom_prereg_sha256_lf": M.PREREG_SHA, "harness_sha256": sha_lf(M.__file__), "gate_sha256": sha_lf(__file__),
           "null_draws": int(M.NREP), "seed": M.SEED, "book_dd_days": int(S12.n_dd_days), "book_loss_over_dd_days": book_loss, "cells": {}}
    if s1:
        res = {"post_mode": post_mode, "note2_sha256_lf": NOTE2_SHA, "restatement_record": RESTATE_JSON, **res}
    for cell in M.CELLS:
        base = M.run_cell(W, M.cell_leg(L, cell), M.D15.l1_cfg(), pos=True)
        xB = M.D15.to_B(base.x, rows, B.n)
        seat = M.D15.seat_measure(S12, xB)
        eps = M.D15.episodes_table(S12, xB)
        dd_usd = float(np.asarray(xB, float)[S12.rows][S12.dd].sum())
        best = max(eps, key=lambda e: e["cell_pnl"])
        roc_n, rho_n, do_n = M.D15.null_cell(S12, acc[cell], rows, B.n)
        roc_p95 = M.D15.pctl(roc_n, 95)                                       # must equal the reference's: the draws ARE the registered ones (Stage A's under 'remove', the restatement's under 'close')
        sa = reference_p95(post_mode, cell)
        if abs(roc_p95 - sa) > 1e-9:
            M.refuse(f"gate refused: the null draws do not reproduce {'the restatement' if s1 else 'Stage A'}'s ({cell} ROC p95 {roc_p95} vs {sa}) - nothing judged")
        do_n = np.asarray(do_n, float)
        fin = do_n[np.isfinite(do_n)]
        p95 = float(np.percentile(fin, 95))
        pct = float((fin < seat["DO"]).mean() * 100.0)
        c = {"net_wf": float(np.asarray(xB, float)[S12.rows].sum()), "DO": seat["DO"], "rho_dd": seat["rho_dd"], "dd_days_usd": dd_usd,
             "best_episode": {k: best[k] for k in ("peak", "trough", "dd_days", "cell_pnl")}, "dd_days_usd_without_best_episode": dd_usd - best["cell_pnl"],
             "episodes_positive": int(sum(1 for e in eps if e["cell_pnl"] > 0)), "episodes": len(eps),
             "null_DO": {"p5": float(np.percentile(fin, 5)), "p50": float(np.percentile(fin, 50)), "p95": p95, "finite": int(len(fin)), "dd_usd_p95": p95 * book_loss},
             "DO_percentile_in_null": pct, ("null_roc_p95_reproduces_restatement" if s1 else "null_roc_p95_reproduces_stage_a"): roc_p95}
        c["gate_a"] = bool(seat["DO"] > p95)
        c["gate_b"] = bool(c["dd_days_usd_without_best_episode"] > 0)
        res["cells"][cell] = c
        print(f"{cell}: WF net ${c['net_wf']:,.0f}; over #463's {S12.n_dd_days} drawdown days ${dd_usd:,.0f} (DO {seat['DO']:+.3f}, rho_dd {seat['rho_dd']:+.3f}; "
              f"{c['episodes_positive']} of {c['episodes']} episodes positive); random-name null DO p5 / p50 / p95 {c['null_DO']['p5']:+.3f} / {c['null_DO']['p50']:+.3f} / "
              f"{p95:+.3f} (= ${p95 * book_loss:,.0f}); RES-style DO sits at the null's {pct:.1f}th percentile; without its best episode "
              f"({best['peak']} .. {best['trough']}, ${best['cell_pnl']:,.0f}): ${c['dd_days_usd_without_best_episode']:,.0f}", flush=True)
    r = res["cells"]["RES"]
    res["gate_pass"] = bool(r["gate_a"] and r["gate_b"])
    if s1:
        res["verdict"] = ("GATE PASS under S1 - the forward BOOK line opens ([F2], NOTE 2 [N9])" if res["gate_pass"] else
                          "GATE FAIL under S1 - book-add report PASS, drawdown help at chance level; NO line opens: nothing is ranked on 2026-10-30 and the lane tells MANAGER (NOTE 2 [N9])")
    else:
        res["verdict"] = ("GATE PASS - the forward BOOK line opens ([F2])" if res["gate_pass"] else
                          "GATE FAIL - book-add report PASS, drawdown help at chance level; NO line opens")
    print(f"[F1] (a) RES's DO above the null's 95th percentile: {'YES' if r['gate_a'] else 'NO'}; (b) positive without its best episode: {'YES' if r['gate_b'] else 'NO'} -> {res['verdict']}")
    if s1:
        reg = registered_gate()                                                # beside, never a route: the registered reading's numbers (resmom_line_gate.json) for the comparison [N9] asks for
        res["registered_gate"] = reg
        if reg is None:
            print(f"beside: the registered gate's record {OUT} is not on file (nothing to compare)")
        else:
            for cell in M.CELLS:
                g, c = reg["cells"][cell], res["cells"][cell]
                print(f"beside, {cell}: registered gate (post_mode 'remove') DO {g['DO']:+.3f} vs the null's p95 {g['null_DO_p95']:+.3f}, ${g['dd_days_usd_without_best_episode']:,.0f} without its best episode "
                      f"({g['best_episode']['peak']} .. {g['best_episode']['trough']}); S1 (post_mode 'close') DO {c['DO']:+.3f} vs {c['null_DO']['p95']:+.3f}, ${c['dd_days_usd_without_best_episode']:,.0f} without its best episode "
                      f"({c['best_episode']['peak']} .. {c['best_episode']['trough']})", flush=True)
            print(f"beside: the registered gate read '{reg['verdict']}'; the S1 re-read reads '{res['verdict']}'")
    print(f"gate took {time.time() - t0:.0f}s")
    path = OUT_CLOSE if s1 else OUT                                            # the S1 re-read writes ONLY its own record; the registered resmom_line_gate.json is never overwritten by it
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if s1 and os.path.exists(path):                                            # CHOICE [L31]: a gate record is computed once - a second run that agrees rewrites nothing, one that differs never overwrites it
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        if not same_results(old, json.loads(json.dumps(res, default=float))):
            M.refuse(f"gate refused: {path} holds a different gate record (the data, the harness or the code changed since it was written) - never overwritten (nothing written)")
        print(f"{path} is on file and agrees with this run - nothing rewritten")
        return res
    with open(path, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print("written", path)
    return res


if __name__ == "__main__":
    main()

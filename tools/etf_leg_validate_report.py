"""THE SIX ETF LEG VALIDATES, IN ONE TABLE - verdict, which gates moved it, and what it crowned.

WHY (2026-09-09). `tools/queue_etf_leg_validates.py` put the seven ETF book legs through leg-level
Auto-Validate for the first time (six jobs, because the two QQQ RSI2 legs differ only in a bool the
search always explores). This reads those runs back and prints the things the pre-registered bar
actually turns on, rather than a verdict word on its own:

  * the verdict, and WHICH of the six house gates moved it - a leg that fails `sample` because it
    has 25 trades per parameter is a different animal from one that fails `luck`;
  * walk-forward efficiency in BOTH modes, because the engine reports the worse-scoring mode as
    `wfe` and the anchored/rolling gap is itself informative on a thin leg;
  * the lockbox trade count NEXT TO the lockbox P&L, so nobody reads a figure built on six trades
    as evidence;
  * whether the crown is the cell the book carries - if it is not, the book's leg is still
    unvalidated whatever the verdict says (the run #343 precedent).

Read it with `tools/etf_leg_prewindow.py`, which scores the same crowns on the 2006-2009 stretch
round 25 never loaded.

    python tools/etf_leg_validate_report.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.book_dd_attribution import all_jobs, DEFAULT_UID, _m   # noqa: E402
from tools.etf_leg_prewindow import BOOK_CELL, FIXED, same_cell   # noqa: E402

TAG = "etf leg validate"      # matched case-insensitively: the job note writes it in caps
GATES = ("luck", "wfe", "pbo", "consistency", "sample", "plateau")


def main():
    jobs = all_jobs(DEFAULT_UID)
    rows = []
    for rid, j in sorted(jobs.items()):
        if TAG not in str(j.get("note") or "").lower() or j.get("type") != "validate":
            continue
        if j.get("status") != "done":
            print("  (run #%s %s on %s is %s - not read)"
                  % (rid, j.get("strategy"), j.get("instrument"), j.get("status")))
            continue
        rows.append((rid, j))
    if not rows:
        sys.exit("no finished ETF leg validates found")

    print("SIX ETF LEG VALIDATES - full discovery, window 2009-06-01..2026-06-30, 12-month lockbox\n")
    hdr = ("%-5s %-14s %-7s %5s  %-26s %6s %6s %6s %5s %10s  %s"
           % ("run", "leg", "verdict", "gates", "gates that FAILED", "wfe-r", "wfe-a", "t/par",
              "LB n", "LB pnl $", "crown = book cell?"))
    print(hdr)
    print("-" * len(hdr))
    detail = []
    for rid, j in rows:
        fn, inst = j.get("strategy"), j.get("instrument")
        res = j.get("result") or {}
        v = res.get("validate") or {}
        ch = v.get("checks") or {}
        lb = v.get("lockbox") or {}
        crown = dict(res.get("best_params") or {})
        cells = BOOK_CELL.get((fn, inst), [])
        agree = any(same_cell(crown, c)[0] for c in cells) if cells else None
        failed = [g for g in GATES if ch.get(g) is False]
        wr = (v.get("wf_rolling") or {}).get("wfe")
        wa = (v.get("wf_anchored") or {}).get("wfe")
        nm = "%s %s" % (fn.replace("ETFDIP_", "").replace("_1_0.py", ""), inst)
        print("%-5s %-14s %-7s %5s  %-26s %6s %6s %6s %5s %10s  %s"
              % (rid, nm, v.get("verdict"), "%s/%s" % (sum(1 for g in GATES if ch.get(g)), len(GATES)),
                 ",".join(failed) or "-",
                 ("%.3f" % wr) if isinstance(wr, (int, float)) else "-",
                 ("%.3f" % wa) if isinstance(wa, (int, float)) else "-",
                 ("%.1f" % v["trades_per_param"]) if v.get("trades_per_param") is not None else "-",
                 lb.get("trades"), _m(lb.get("pnl") or 0),
                 ("YES" if agree else "no - DIFFERENT leg") if cells else "?"))
        detail.append((rid, nm, fn, inst, crown, cells, agree, v))

    print("\nCROWNS vs THE CELLS THE BOOK CARRIES")
    for rid, nm, fn, inst, crown, cells, agree, v in detail:
        ck = ", ".join("%s=%s" % (k, crown[k]) for k in sorted(crown) if k not in FIXED)
        print("  #%-4s %-14s crown: %s" % (rid, nm, ck))
        for c in cells:
            ok, diff = same_cell(crown, c)
            bk = ", ".join("%s=%s" % (k, c[k]) for k in sorted(c) if k not in FIXED)
            print("       %-14s book : %s%s" % ("", bk, "" if ok else
                  "   <- differs on " + ", ".join("%s (%s vs %s)" % (k, a, b) for k, (a, b) in diff.items())))

    print("\nWHY EACH VERDICT LANDED WHERE IT DID (the gates the house actually scores)")
    for rid, nm, fn, inst, crown, cells, agree, v in detail:
        ch = v.get("checks") or {}
        es = v.get("edge_sig") or {}
        pl = v.get("plateau") or {}
        pb = v.get("pbo") or {}
        ca = v.get("causal") or {}
        print("  #%-4s %-14s %s | " % (rid, nm, v.get("verdict"))
              + " ".join("%s=%s" % (g, "ok" if ch.get(g) else "NO") for g in GATES))
        print("       edge t=%s p=%s | plateau %s/%s %s | pbo %s (%s) | dsr %s | causal %s"
              % (es.get("t_stat"), es.get("p_value"), pl.get("good"), pl.get("tot"), pl.get("verdict"),
                 pb.get("pbo"), pb.get("verdict"),
                 ("%.3f" % v["dsr"]) if isinstance(v.get("dsr"), (int, float)) else "-",
                 (ca.get("verdict") or "-")))


if __name__ == "__main__":
    main()

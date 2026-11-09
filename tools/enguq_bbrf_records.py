"""Run records for the BBRF stage-2 cells (W47 standing rule, MANAGER #145).

One record per reported stage-2 cell, at the 0.45 ES pt real round trip - the cost the cells were
scored at.  The four numbers were measured during the run by augur_engine.drawdowns.four_numbers off
each cell's own DAILY dollar series with zero days included, and are handed to
run_record.write_record through numbers=, which stores a lane's dict exactly as given.  Nothing is
re-derived here.

THE 48 GATE CELLS GET NO RECORDS.  They are per-trade R statistics with no daily dollar series, and
numbers not measured with a daily series are not written.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
if not os.path.isdir(os.path.join(_ROOT, "augur_engine")) and os.path.isdir(SHARED_CHECKOUT):
    sys.path.insert(0, SHARED_CHECKOUT)

import tools.run_record as run_record                  # noqa: E402

SRC = r"C:\EdgeLog\_anatomy_cache\enguq_bbrf_gate\stage2.json"
WIN_FROM, WIN_TO = "2010-06-06", "2025-06-30"


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    years = d["years"]
    cost = d["cost_pts"]["real"]
    written = refused = skipped = 0
    out = "-"
    for r in d["rows"]:
        if r.get("trades", 0) < 2 or r.get("roc30") is None:
            # a cell with no four numbers is not a row; the chart cannot tell a figure that does
            # not exist from one that was never measured
            skipped += 1
            continue
        nums = {"roc30": r["roc30"], "dd5_usd": r["dd5_usd"], "dd_pct_peak": r["dd_pct_peak"],
                "sortino": r["sortino"], "one_episode": r["one_episode"],
                "net_usd": r["net_usd_real"], "from": WIN_FROM, "to": WIN_TO, "years": years}
        note = ("BBRF stage 2 %s @%.2f pt real RT; %d/8 folds; closes at draft, no trial budget"
                % (r["cell"], cost, r["folds_positive"]))
        got = run_record.write_record(
            "ENGUQ", "lane", "preLB",
            strategy="enguq_bbrf_stage2 | %s" % r["cell"],
            family="ENGU-Q", instrument="ES", timeframe="5m",
            numbers=nums, trades=r["trades"], gross_pt=None, cost_pt=cost,
            ledger_row="2.220", note=note[:200],
            prereg="docs/PREREG_enguq_bodybreak_rfloor_2026-11-09.md")
        if got:
            written += 1
            out = got
        else:
            refused += 1
    print("written %d  refused %d  skipped (no four numbers) %d" % (written, refused, skipped))
    print("file " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

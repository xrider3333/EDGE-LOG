"""Backfill one run record per reported pullback-break r2 cell (MANAGER #145).

WHY numbers= AND NOT daily=.  Every figure in stage1.json was measured by
augur_engine.drawdowns.four_numbers off the cell's own DAILY $ series, zero days included -
that is the documented lane path in run_record's own docstring ("a tail that already holds the
four numbers hands its own dict in; the numbers are stored as given").  Nothing here is derived
from anything else, and no figure I did not measure is written.

TWO COST RUNGS PER CELL, which is the #142 rule: 0.533 ES pt (the house headline the verdict
rests on) and 0.25 ES pt (my ladder's lowest rung).  MANAGER #144 settled the cost question:
the real house ES round trip is 0.45 pt commission+exchange and 0.95 pt with slippage, so my
0.08 and 0.10 rungs are BELOW ANY REAL COST and are deliberately NOT written as records.
"""
import json, sys
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import tools.run_record as run_record

SRC = r"C:/EdgeLog/_anatomy_cache/enguq_pullback_break_r2/stage1.json"
RUNGS = ("0.533", "0.25")
WIN_FROM, WIN_TO, YEARS = "2010-06-06", "2025-06-30", 15.07

d = json.load(open(SRC, encoding="utf-8"))
rows = d["rows"]
written = refused = 0
for r in rows:
    for rung in RUNGS:
        hl = dict(r["ladder"][rung])
        hl["from"], hl["to"], hl["years"] = WIN_FROM, WIN_TO, YEARS
        note = "pullback-break r2 %s %s @%s pt%s; %d/8 folds" % (
            r["cell"], r["exit"], rung,
            " (below any real cost per MANAGER #144: house ES RT 0.45 pt)" if rung == "0.25" else " house",
            r["folds_positive"])
        got = run_record.write_record(
            "ENGUQ", "lane", "preLB",
            strategy="enguq_pullback_break_r2 | %s | %s" % (r["cell"], r["exit"]),
            family="ENGU-Q", instrument="ES", timeframe="5m",
            numbers=hl, trades=r["trades"],
            gross_pt=None,                       # the screen measured gross in R, not points
            cost_pt=float(rung),
            ledger_row="2.218", note=note[:200],
            prereg="docs/PREREG_enguq_pullback_break_2026-11-04.md")
        if got:
            written += 1
            out = got
        else:
            refused += 1
print("written", written, "refused", refused)
print("file", out if written else "-")

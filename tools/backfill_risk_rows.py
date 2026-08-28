#!/usr/bin/env python3
"""Backfill WIN % / SHARPE / SORTINO / AVG LOSS onto STUDIES registry rows.

WHY THIS EXISTS (owner, 2026-08-28: "can you backfill this info").
On COMPARE > STUDIES the SWEEPS level shows four axes reading `not recorded` for
every row: WIN %, SHARPE, SORTINO and EV IN R. That is not a display bug. Nothing
ever *recorded* those figures for a local .py sweep -- the drivers printed money,
drawdown, profit factor and a trade count and stopped there -- so there is nothing
on disk to read. Filling them in means RE-RUNNING the sweep and recomputing them
from its own trades.

`augur_engine/analytics.py` now owns the one definition of each figure, shared by
run_backtest and validate, so a re-run puts the SAME arithmetic on the axis that an
Auto-Validate row already sits on.

HOW A STUDY GETS BACKFILLED
  1. its driver's per-cell row builder gains the four figures (see
     tools/noise_hunt5_plateau.py `row_of` for the pattern -- it is four lines);
  2. the driver is re-run, which rewrites its results JSON;
  3. this script maps each JSON cell to its registry row and writes `wr`, `sh`,
     `so` and `avl` into index.html.

THE MAPPING IS VERIFIED, NOT ASSUMED. Every row is matched on figures the registry
already holds (trade count, profit factor, net) before anything is written. A cell
whose numbers do not line up is REFUSED and named -- a mis-mapped row would put one
config's Sharpe under another config's name, which is worse than a blank.

    python tools/backfill_risk_rows.py                 # report only, writes nothing
    python tools/backfill_risk_rows.py --write         # apply
"""
import argparse
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "index.html")
# The results JSONs are written wherever the DRIVER ran, which is the shared checkout
#   (that is where the data lives), while index.html is edited in a worktree. Those are
#   two different folders, so the two paths are separate options rather than one REPO.
RESULTS = os.environ.get("EDGELOG_RESULTS_DIR") or REPO


# ─────────────────────────────────────────────────────────────────────────────────
# One entry per study that has been re-run with the figures. Each returns
# {row name -> cell dict}. Adding a study is one function plus one line in STUDIES.
# ─────────────────────────────────────────────────────────────────────────────────
def cells_noiseplateau243():
    """NOISE study B, the plateau sweep -- tools/noise_hunt5_plateau.py."""
    p = os.path.join(RESULTS, "_noise_plateau_243.json")
    if not os.path.exists(p):
        return None, "results file not found: re-run tools/noise_hunt5_plateau.py"
    d = json.load(io.open(p, encoding="utf-8"))
    ax, cat = d["axes"], d["categorical"]
    out = {"Crown (run 243)": d["crown"]}
    for key, label, fmt in (("A1", "Lookback", "%d"), ("A2", "Band Long", "%.2f"),
                            ("A3", "Band Short", "%.2f"), ("A4", "Stop k", "%.2f"),
                            ("A5", "Weak-Close", "%.2f"), ("A6", "Vol Skip", "%d"),
                            ("A7", "Confirm", "%d")):
        for v, row in ax[key]["rows"].items():
            out["%s %s" % (label, fmt % float(v))] = row
    for key, lab, name in (("A4", "stop OFF (stop_mode='off')", "Stop OFF"),
                           ("A5", "day-type OFF (= vs90 alone)", "Short Veto OFF"),
                           ("A6", "vol-skip OFF (= run #241)", "Vol Skip OFF (= #241)")):
        e = (ax[key].get("endpoints") or {}).get(lab)
        if e:
            out[name] = e
    for name, key, v in (("Exit at Band", "C1", "band"), ("Long Only", "C2", "Long Only"),
                         ("Short Only", "C2", "Short Only"), ("Morning Only", "C3", "morning"),
                         ("Afternoon Only", "C3", "afternoon_block")):
        r = cat[key]["rows"].get(v)
        if r:
            out[name] = r
    return out, None


STUDIES = {"noiseplateau243": cells_noiseplateau243}


# ─────────────────────────────────────────────────────────────────────────────────
def study_segment(html, key):
    """(start, end) of one study's slice of RESEARCH_STUDIES.

    The end must be the next STUDY, not the next `{key:'` -- that string also occurs
    in ordinary app code below the registry, and on the LAST study the loose search
    ran the segment on into the code and pulled a `{n:0,...}` object in as a row.
    A study is `{key:'x',title:'...'`, so match that shape, and fall back to the end
    of the array literal.
    """
    i = html.index("{key:'%s'" % key)
    m = re.search(r"\{key:'[a-z0-9_-]+',title:'", html[i + 10:])
    if m:
        return i, i + 10 + m.start()
    e = html.find("\n      ];", i)
    return i, (e if e > 0 else len(html))


def registry_rows(seg):
    """[{n, name, span, pf, trd, is}] for every row in one study segment."""
    out = []
    for m in re.finditer(r"\{n:(\d+),", seg):
        s = m.start()
        e = seg.find("{n:", s + 3)
        body = seg[s:(e if e > 0 else len(seg))]
        nm = re.search(r"name:'([^']*)'", body)
        num = lambda f: (lambda g: float(g.group(1)) if g else None)(
            re.search(r"[,{]%s:(-?[\d.]+)" % f, body))
        out.append(dict(n=int(m.group(1)), name=(nm.group(1) if nm else ""),
                        start=s, end=(e if e > 0 else len(seg)), body=body,
                        pf=num("pf"), trd=num("trd"), is_=num("is")))
    return out


def verify(row, cell):
    """The mapping is only trusted when the figures the registry ALREADY holds agree.

    Trade count must match exactly - it is an integer and a re-run of the same config
    over the same window reproduces it. Profit factor is allowed 1% for rounding, since
    the registry stores it to two decimals.
    """
    if row["trd"] is not None and cell.get("n") is not None:
        if int(row["trd"]) != int(cell["n"]):
            return "trade count %s vs %s" % (int(row["trd"]), int(cell["n"]))
    if row["pf"] is not None and cell.get("pf"):
        if abs(row["pf"] - cell["pf"]) > max(0.011, 0.01 * cell["pf"]):
            return "PF %.2f vs %.3f" % (row["pf"], cell["pf"])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply (default: report only)")
    ap.add_argument("--study", default=None, help="one study key (default: all known)")
    ap.add_argument("--html", default=HTML,
                    help="index.html to patch. Defaults to this checkout, but the standing "
                         "rule is to edit in a worktree - point this at yours.")
    ap.add_argument("--results-dir", default=RESULTS,
                    help="folder holding the drivers' results JSONs (default: this checkout)")
    a = ap.parse_args()
    globals()["RESULTS"] = a.results_dir

    target = a.html
    html = io.open(target, encoding="utf-8", newline="").read()
    keys = [a.study] if a.study else list(STUDIES)
    total_ok = total_skip = 0

    for key in keys:
        cells, err = STUDIES[key]()
        print("\n=== %s ===" % key)
        if err:
            print("  SKIPPED - %s" % err)
            continue
        i, j = study_segment(html, key)
        seg = html[i:j]
        rows = registry_rows(seg)
        edits, skipped = [], []
        for r in rows:
            cell = cells.get(r["name"])
            if cell is None:
                skipped.append((r["name"], "no matching cell in the results file"))
                continue
            why = verify(r, cell)
            if why:
                skipped.append((r["name"], "figures disagree - " + why))
                continue
            add = []
            for fld, ck, fmt in (("wr", "win", "%.1f"), ("sh", "sharpe", "%.3f"),
                                 ("so", "sortino", "%.3f"), ("avl", "avg_loss", "%.0f"),
                                 ("evr", "evr", "%.3f")):
                v = cell.get(ck)
                if v is None or ("[,{]%s:" % fld) and re.search(r"[,{]%s:" % fld, r["body"]):
                    continue
                add.append("%s:%s" % (fld, fmt % float(v)))
            if add:
                edits.append((r, ",".join(add)))
        for r, add in edits[:4]:
            print("  %-24s + %s" % (r["name"], add))
        if len(edits) > 4:
            print("  ... %d more" % (len(edits) - 4))
        for nm, why in skipped:
            print("  REFUSED %-22s %s" % (nm, why))
        total_ok += len(edits)
        total_skip += len(skipped)

        if a.write and edits:
            # apply back-to-front so earlier offsets stay valid
            for r, add in sorted(edits, key=lambda t: -t[0]["start"]):
                abs_at = i + r["start"] + len("{n:%d" % r["n"])
                html = html[:abs_at] + "," + add + html[abs_at:]
    if a.write:
        io.open(target, "w", encoding="utf-8", newline="").write(html)
        print("\nwrote index.html")
    print("\n%d row(s) backfilled, %d refused%s"
          % (total_ok, total_skip, "" if a.write else "  (dry run - nothing written)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

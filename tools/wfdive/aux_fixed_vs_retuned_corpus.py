"""AUX (no replay, no lock needed): corpus-wide check of Q1's pattern (re-tuned WF
lower than fixed-settings WF) beyond the #335/#257 examples in the task context.

Reads ONLY _wfdive_data/runs.json + coverage.json (the Gather agent's saved data --
no Firestore call, no backtest). For every non-book run that carries BOTH
validate.wf_oos (the re-tuned, per-fold-refit walk-forward) and
gate_validate.ungated_wf (the FIXED crowned-champion walk-forward slice), compares
PF and net. Deduplicates to one (newest) run per (strategy-file, instrument,
timeframe) family so this is N independent families, not N re-validates of a
handful of strategies (memory: "runs cluster by FAMILY").

This is supporting/corroborating evidence for Q1 (not this script's own lens,
which is lens_lblen.py / lockbox-length power) -- included because it required no
extra compute and materially strengthens the answer with a much larger n than the
two worked examples in the task brief.

Run: python tools/wfdive/aux_fixed_vs_retuned_corpus.py
Writes: _wfdive_data/aux_fixed_vs_retuned_corpus.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfdive.common import load_runs, family_key, DATA_DIR  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "aux_fixed_vs_retuned_corpus.json")


def main():
    runs = load_runs()
    cov = json.load(open(os.path.join(DATA_DIR, "coverage.json"), encoding="utf-8"))
    book_ids = set(cov.get("books", {}).get("ids") or [])

    rows = []
    for d in runs:
        if d["id"] in book_ids:
            continue
        v = d.get("validate") or {}
        wo = v.get("wf_oos") or {}
        gv = d.get("gate_validate") or {}
        uw = gv.get("ungated_wf") or {}
        if not wo.get("trades") or not uw.get("num_trades"):
            continue
        rows.append({
            "id": d["id"], "family": family_key(d), "strategy": d.get("strategy"),
            "instrument": d.get("instrument"), "timeframe": d.get("timeframe"),
            "retuned_wf_pf": wo.get("profit_factor"), "fixed_wf_pf": uw.get("profit_factor"),
            "retuned_wf_net": wo.get("net"), "fixed_wf_net": uw.get("total_pnl"),
            "retuned_wf_trades": wo.get("trades"), "fixed_wf_trades": uw.get("num_trades"),
        })

    n_all = len(rows)
    fixed_pf_higher_all = sum(1 for r in rows
                               if r["fixed_wf_pf"] and r["retuned_wf_pf"]
                               and r["fixed_wf_pf"] > r["retuned_wf_pf"])
    fixed_net_higher_all = sum(1 for r in rows
                                if r["fixed_wf_net"] is not None and r["retuned_wf_net"] is not None
                                and r["fixed_wf_net"] > r["retuned_wf_net"])

    seen = set()
    dedup = []
    for r in sorted(rows, key=lambda r: -r["id"]):
        if r["family"] in seen:
            continue
        seen.add(r["family"])
        dedup.append(r)
    n_fam = len(dedup)
    fixed_pf_higher_fam = sum(1 for r in dedup
                               if r["fixed_wf_pf"] and r["retuned_wf_pf"]
                               and r["fixed_wf_pf"] > r["retuned_wf_pf"])
    fixed_net_higher_fam = sum(1 for r in dedup
                                if r["fixed_wf_net"] is not None and r["retuned_wf_net"] is not None
                                and r["fixed_wf_net"] > r["retuned_wf_net"])

    payload = {
        "note": "validate.wf_oos = re-tuned (each fold refits params on its own past) "
                "walk-forward, stitched. gate_validate.ungated_wf = the FIXED crowned "
                "champion's single params replayed over the same walk-forward date "
                "range. Both fields are already saved on the run doc -- no replay run "
                "by this script.",
        "n_runs_with_both_fields": n_all,
        "fixed_wf_pf_beats_retuned_wf_pf": {"n": fixed_pf_higher_all, "of": n_all,
                                             "share": round(fixed_pf_higher_all / n_all, 3)},
        "fixed_wf_net_beats_retuned_wf_net": {"n": fixed_net_higher_all, "of": n_all,
                                               "share": round(fixed_net_higher_all / n_all, 3)},
        "deduped_to_independent_families": {
            "n_families": n_fam,
            "fixed_wf_pf_beats_retuned_wf_pf": {"n": fixed_pf_higher_fam, "of": n_fam,
                                                 "share": round(fixed_pf_higher_fam / n_fam, 3)},
            "fixed_wf_net_beats_retuned_wf_net": {"n": fixed_net_higher_fam, "of": n_fam,
                                                   "share": round(fixed_net_higher_fam / n_fam, 3)},
        },
        "rows_all": rows,
        "rows_deduped_families": dedup,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"wrote {OUT_PATH}: {n_all} runs ({n_fam} independent families); "
          f"fixed WF PF beats re-tuned WF PF in {fixed_pf_higher_fam}/{n_fam} families "
          f"({round(100 * fixed_pf_higher_fam / n_fam, 1)}%)")


if __name__ == "__main__":
    main()

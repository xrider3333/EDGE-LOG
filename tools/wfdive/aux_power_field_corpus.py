"""AUX (no replay, no lock needed): corpus-wide read of the engine's OWN #94
statistical-power field (validate.py power_stats -> doc.power) across every
non-book run with a lockbox. This is the engine's classical one-sided z-test
power to detect the champion's OWN claimed per-trade edge (Stage-A/optimize-
window mean per-trade PnL) at the ACTUAL saved lockbox's sample size -- already
computed and saved by validate.py at run time, so this script only reads it.

Complements lens_lblen.py's own month-block bootstrap (which asks the same "is
the lockbox long enough" question a different, distribution-free way, and can
evaluate hypothetical 18/24/36-month lockboxes the saved `power` field cannot,
since that field is static to whatever lockbox_months the run actually used).

Run: python tools/wfdive/aux_power_field_corpus.py
Writes: _wfdive_data/aux_power_field_corpus.json
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfdive.common import load_runs, DATA_DIR  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "aux_power_field_corpus.json")


def main():
    runs = load_runs()
    cov = json.load(open(os.path.join(DATA_DIR, "coverage.json"), encoding="utf-8"))
    book_ids = set(cov.get("books", {}).get("ids") or [])

    rows = []
    for d in runs:
        if d["id"] in book_ids:
            continue
        v = d.get("validate") or {}
        if not v.get("lockbox"):
            continue
        p = d.get("power") or {}
        if not p or p.get("error"):
            continue
        rows.append({
            "id": d["id"], "strategy": d.get("strategy"),
            "instrument": d.get("instrument"), "timeframe": d.get("timeframe"),
            "lockbox_months": (v.get("windows") or {}).get("lockbox_months"),
            "n_lockbox_trades": p.get("n"),
            "achieved_power": p.get("achieved_power"),
            "powered_ge_0.80": bool(p.get("powered")),
            "mde_per_trade": p.get("mde_per_trade"),
            "claimed_per_trade": p.get("claimed_per_trade"),
            "lockbox_pass": (v.get("lockbox") or {}).get("pass"),
        })

    vals = [r["achieved_power"] for r in rows if r["achieved_power"] is not None]
    n_powered = sum(1 for r in rows if r["powered_ge_0.80"])
    payload = {
        "note": "achieved_power/powered/mde_per_trade/claimed_per_trade are validate.py's "
                "OWN #94 power_stats() output (one-sided z-test, alpha=0.05, target "
                "power=0.80), read straight off each run doc's top-level `power` field -- "
                "not recomputed here.",
        "n_runs_with_usable_power_field": len(rows),
        "n_powered_ge_0.80": n_powered,
        "share_powered": round(n_powered / len(rows), 3) if rows else None,
        "median_achieved_power": round(statistics.median(vals), 3) if vals else None,
        "share_achieved_power_lt_0.20": (round(sum(1 for x in vals if x < 0.20) / len(vals), 3)
                                          if vals else None),
        "share_achieved_power_lt_0.50": (round(sum(1 for x in vals if x < 0.50) / len(vals), 3)
                                          if vals else None),
        "rows": rows,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"wrote {OUT_PATH}: {len(rows)} runs, {n_powered} powered (>=0.80), "
          f"median achieved_power={payload['median_achieved_power']}")


if __name__ == "__main__":
    main()

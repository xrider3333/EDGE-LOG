"""Scout candidate strategy families for the candidate-matrix builder (owner request
2026-09-16). For every strategy file behind a wf_ran=True run in runs.json:
  - load the module, compute _auto_space_from_params(DEFAULT_PARAMS)
  - count REAL free knobs (numeric range with hi>lo, or a categorical/bool with >1
    option) -- a knob pinned to one value (lo==hi, or a single-option cat) is not a
    search dimension even though it appears in DEFAULT_PARAMS
  - try rebuild_plan() (tools/backfill_wf_oos.py) on each associated run doc (no
    Firestore -- the doc is already in runs.json) to see which runs replay cleanly
  - report instrument/timeframe/session/data_source/date span/cost_pts/trades per
    saved run (best_trades / days_in_test) as a trades/yr proxy

No backtests are run here -- this is metadata/inspection only, safe to run anytime.
"""
import json
import os
import sys

WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, WORKTREE_ROOT)
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "tools"))

from tools.wfdive import common  # noqa: E402

common.setup_data_env(verbose=False)

from augur_engine.strategies import load_strategy  # noqa: E402
from augur_engine.auto import _auto_space_from_params  # noqa: E402
from backfill_wf_oos import rebuild_plan  # noqa: E402


def free_knob_count(dp):
    space = _auto_space_from_params(dp)
    n = 0
    detail = []
    for name, spec in space.items():
        kind = spec[0]
        if kind == "cat":
            real = len(spec[1]) > 1
        elif kind == "int":
            _, lo, hi, step = spec
            real = hi > lo
        else:
            _, lo, hi, step = spec
            real = hi > lo
        if real:
            n += 1
        detail.append((name, kind, real))
    return n, detail


def main():
    runs = common.load_runs()
    by_id = {str(r.get("id")): r for r in runs}
    fams = {}
    for r in runs:
        if r.get("book") is not None:
            continue
        v = r.get("validate") or {}
        if not v.get("wf_ran"):
            continue
        strat = r.get("strategy")
        fams.setdefault(strat, []).append(r)

    out = {}
    for strat in sorted(fams):
        rows = fams[strat]
        try:
            mod = load_strategy(strat)
            dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
            n_knobs, detail = free_knob_count(dp)
            pinned = bool(getattr(mod, "_PINNED", False))
            parent = getattr(mod, "_AUGUR_PARENT", None)
        except Exception as e:
            out[strat] = {"error": f"{type(e).__name__}: {e}"}
            continue
        run_rows = []
        for r in rows:
            plan, why = rebuild_plan(r)
            run_rows.append({
                "id": r.get("id"), "instrument": r.get("instrument"),
                "timeframe": r.get("timeframe"), "data_source": r.get("data_source"),
                "date_from": r.get("date_from"), "date_to": r.get("date_to"),
                "days_in_test": r.get("days_in_test"), "best_trades": r.get("best_trades"),
                "cost_pts": r.get("cost_pts"), "wf_best_mode": (r.get("validate") or {}).get("wf_best_mode"),
                "n_folds": (r.get("validate") or {}).get("n_folds"),
                "rebuild_ok": plan is not None, "rebuild_why": why,
                "verdict": (r.get("validate") or {}).get("verdict"),
                "starred": r.get("starred"),
            })
        out[strat] = {
            "n_knobs": n_knobs, "knob_detail": detail, "pinned": pinned, "parent": parent,
            "runs": run_rows,
        }
    path = os.path.join(common.DATA_DIR, "isdepth", "scout_families_raw.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print("wrote", path)
    # quick console summary: n_knobs >= 3, sorted by family, one line each
    for strat in sorted(out):
        o = out[strat]
        if "error" in o:
            continue
        if o["n_knobs"] < 3:
            continue
        oks = [rr["id"] for rr in o["runs"] if rr["rebuild_ok"]]
        tfs = sorted(set((rr["timeframe"], rr["instrument"], rr["data_source"]) for rr in o["runs"]))
        print(f"{strat:32s} knobs={o['n_knobs']:2d} pinned={o['pinned']!s:5s} "
              f"runs={[rr['id'] for rr in o['runs']]} rebuild_ok={oks} tf={tfs}")


if __name__ == "__main__":
    main()

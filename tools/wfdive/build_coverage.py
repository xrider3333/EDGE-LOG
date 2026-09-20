"""wfdive Gather step 4: from _wfdive_data/runs.json, build _wfdive_data/coverage.json
(counts every downstream agent needs so nobody re-derives them differently) plus
sanity-check #335 / #257 against the CONTEXT numbers (step 5).

Read-only, no Firestore access (works purely off the saved runs.json). Run from
this worktree:

    python tools/wfdive/build_coverage.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

sys.path.insert(0, common.WORKTREE_ROOT)
from tools.backfill_wf_oos import rebuild_plan  # noqa: E402


def is_book(d):
    """A BOOK job — pools legs, has no walk-forward folds (memory: exclude
    books from WF analysis). Two independent signals, either one is enough:
    the `book` field is only ever populated by a book run, and `scope` carries
    the human label the runner assigns from job.get('type') ('book' ->
    '📚 Book')."""
    if d.get("book") is not None:
        return True
    scope = str(d.get("scope") or "")
    return "Book" in scope or "📚" in scope


def has_validate(d):
    return bool(d.get("validate"))


def has_lockbox(d):
    v = d.get("validate") or {}
    return isinstance(v.get("lockbox"), dict) and v["lockbox"] is not None


def has_wf_oos(d):
    v = d.get("validate") or {}
    return isinstance(v.get("wf_oos"), dict)


def has_ungated_wf(d):
    gv = d.get("gate_validate") or {}
    return isinstance(gv.get("ungated_wf"), dict)


def has_selection_k2(d):
    sel = d.get("selection")
    if not isinstance(sel, dict):
        return False
    try:
        return int(sel.get("k") or 0) >= 2
    except (TypeError, ValueError):
        return False


def has_88b(d):
    """The #88b forward-lockbox continuation: any selection candidate/robust
    row carrying its own 'lockbox' key (not just None — a config that took
    zero lockbox trades still gets the key, set to None, so check for
    PRESENCE of the key on at least one row, matching validate.py's
    `c["lockbox"] = _lbs` / `c["lockbox"] = None` — both count as "the block
    ran", only a genuinely absent key means it didn't)."""
    sel = d.get("selection")
    if not isinstance(sel, dict):
        return False
    rows = (sel.get("candidates") or []) + (sel.get("robust") or [])
    return any(isinstance(r, dict) and "lockbox" in r for r in rows)


def main():
    runs = common.load_runs()
    print(f"loaded {len(runs)} run(s) from runs.json")

    books = [d for d in runs if is_book(d)]
    book_ids = {d.get("id") for d in books}
    non_book = [d for d in runs if d.get("id") not in book_ids]
    with_validate = [d for d in runs if has_validate(d)]
    with_lockbox = [d for d in runs if has_lockbox(d)]
    with_wf_oos = [d for d in runs if has_wf_oos(d)]
    with_ungated_wf = [d for d in runs if has_ungated_wf(d)]
    with_selection_k2 = [d for d in runs if has_selection_k2(d)]
    with_88b = [d for d in runs if has_88b(d)]
    # A BOOK carries a minimal validate.{lb_idx,lockbox,verdict} block (its own pooled
    # lockbox) but NEVER wf_ran/wf_best_mode/wf_oos (books pool legs — no walk-forward
    # folds), so "with_validate"/"with_lockbox" above INCLUDE all 41 books; report the
    # non-book-only counts alongside so nobody mistakes a book's lockbox for a WF-eligible
    # Auto-Validate run (memory: "#366 is a BOOK — exclude books from WF analysis").
    with_validate_excl_books = [d for d in with_validate if d.get("id") not in book_ids]
    with_lockbox_excl_books = [d for d in with_lockbox if d.get("id") not in book_ids]
    wf_oos_book_overlap = [d.get("id") for d in with_wf_oos if d.get("id") in book_ids]

    replay = {}   # status word -> [ {id, reason} ]
    for d in runs:
        plan, reason = rebuild_plan(d)
        status = "ok" if plan is not None else "refused"
        replay.setdefault(status, []).append(
            {"id": d.get("id"), "reason": reason} if reason else
            {"id": d.get("id"), "n_folds": len(plan["folds"]), "mode": plan["mode"]}
        )
    replayable_ok = replay.get("ok", [])
    replayable_refused = replay.get("refused", [])
    # group refusal reasons so the report isn't 300 near-duplicate lines
    refusal_reason_counts = {}
    for r in replayable_refused:
        # collapse to the reason's first clause (before " - " or " (") for grouping
        head = r["reason"].split(" - ")[0].split(" (")[0]
        refusal_reason_counts[head] = refusal_reason_counts.get(head, 0) + 1

    families = {}
    for d in runs:
        fk = common.family_key(d)
        families.setdefault(fk, []).append(d.get("id"))

    coverage = {
        "total_runs": len(runs),
        "books": {"count": len(books), "ids": sorted(d.get("id") for d in books)},
        "non_book_runs": len(non_book),
        # includes books (every book carries a minimal validate.{lb_idx,lockbox,verdict});
        # use the _excl_books counts below for "real" Auto-Validate coverage
        "with_validate": len(with_validate),
        "with_lockbox": len(with_lockbox),
        "with_validate_excl_books": len(with_validate_excl_books),
        "with_lockbox_excl_books": len(with_lockbox_excl_books),
        "with_wf_oos": len(with_wf_oos),
        "with_wf_oos_book_overlap": wf_oos_book_overlap,  # sanity: should be [] (books never wf_ran)
        "with_ungated_wf": len(with_ungated_wf),
        "with_selection_k_ge_2": len(with_selection_k2),
        "with_88b_holdout": len(with_88b),
        "replayable_fold_rows": {
            "ok": len(replayable_ok),
            "refused": len(replayable_refused),
            "refusal_reason_counts": dict(sorted(refusal_reason_counts.items(),
                                                  key=lambda kv: -kv[1])),
        },
        "families": {
            "count": len(families),
            "keys_with_run_ids": {k: sorted(v, key=lambda x: (x is None, x))
                                   for k, v in sorted(families.items())},
        },
    }

    out_path = os.path.join(common.DATA_DIR, "coverage.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(coverage, f, default=str, indent=1)
    print(f"saved coverage to {out_path}")
    print(json.dumps({k: v for k, v in coverage.items() if k != "families"}, default=str, indent=1))
    print(f"families: {coverage['families']['count']}")

    # ── step 5: sanity-check #335 and #257 against CONTEXT ────────────────────
    by_id = {str(d.get("id")): d for d in runs}
    print("\n=== sanity check #335 (ENGU-Q crown) ===")
    d335 = by_id.get("335")
    if d335:
        v = d335.get("validate") or {}
        wfoos = v.get("wf_oos") or {}
        sel = d335.get("selection") or {}
        cands = sel.get("candidates") or []
        wf_pnls = sorted(c.get("wf_oos_pnl") for c in cands if c.get("wf_oos_pnl") is not None)
        crowned = [c for c in cands if c.get("crowned")]
        gv = d335.get("gate_validate") or {}
        print(f"  wf_best_mode={v.get('wf_best_mode')!r} (context implies 'rolling' is the "
              f"PRIMARY re-tuned scheme actually stitched into wf_oos)")
        print(f"  wf_oos: net={wfoos.get('net')} trades={wfoos.get('trades')} "
              f"pf={wfoos.get('profit_factor')}  <-- context: 16,402 pts / 1,822 trades / PF 1.37")
        print(f"  selection candidates wf_oos_pnl range: {wf_pnls[0] if wf_pnls else None} .. "
              f"{wf_pnls[-1] if wf_pnls else None}  <-- context: 15,597..21,868 pts")
        print(f"  is_max_crowned={sel.get('is_max_crowned')}  crowned candidate is_pnl="
              f"{crowned[0].get('is_pnl') if crowned else None}  <-- context: crowned = top one, also IS-max")
        print(f"  gate_validate.ungated_wf total_pnl={gv.get('ungated_wf', {}).get('total_pnl')} "
              f"pf={gv.get('ungated_wf', {}).get('profit_factor')}  <-- context: fixed-settings "
              f"WF PF 1.94 (~$448k = ~22,400 pts @ $20/pt)")
    else:
        print("  #335 NOT FOUND in runs.json")

    print("\n=== sanity check #257 (ORB crown) ===")
    d257 = by_id.get("257")
    if d257:
        v = d257.get("validate") or {}
        wfoos = v.get("wf_oos") or {}
        sel = d257.get("selection") or {}
        cands = sel.get("candidates") or []
        gv = d257.get("gate_validate") or {}
        print(f"  wf_best_mode={v.get('wf_best_mode')!r}")
        print(f"  wf_oos: net={wfoos.get('net')} trades={wfoos.get('trades')} "
              f"pf={wfoos.get('profit_factor')}  <-- context: 16,955.5 pts, PF 1.36")
        print(f"  selection: n_candidates={len(cands)} (k={sel.get('k')})  <-- context: ONE finalist")
        print(f"  gate_validate.ungated_wf total_pnl={gv.get('ungated_wf', {}).get('total_pnl')} "
              f"pf={gv.get('ungated_wf', {}).get('profit_factor')}  <-- context: PF 1.35")
    else:
        print("  #257 NOT FOUND in runs.json")


if __name__ == "__main__":
    main()

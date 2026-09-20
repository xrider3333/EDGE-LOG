"""wfdive Gather step 3-4: stream users/<uid>/runs with a field mask, save
_wfdive_data/runs.json + _wfdive_data/coverage.json.

Read-only. One field-masked read per run doc (Firestore bills a read per
document regardless of the projection, so masking saves bandwidth/local size,
not read count) plus one cheap count() aggregation up front. Run from this
worktree:

    python tools/wfdive/extract_runs.py

Hard cap: refuses to read past MAX_READS (1200) documents; the count()
aggregation shows the true total first so a runaway collection is caught
before that happens.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

MAX_READS = 1200
FIELD_TRIM_BYTES = 200_000  # per-field cap (task: "keep it only if <200 KB per run")

# ── field mask ────────────────────────────────────────────────────────────────
# Dotted paths select nested map fields without pulling their siblings (verified
# against tools/backfill_wf_oos.py's LIST_FIELDS, which already relies on this
# working 3 levels deep: "validate.wf_oos.src"). Deliberately EXCLUDES the large
# per-config/per-trade arrays this dive does not need: points, dist, equity_top,
# win_dist*, mae_mfe*, stress, regime, context, relationship, surrogate,
# auto_expand, steering, the diagnostic 'pills' (adversarial/acf/tailfit/...),
# and validate.gate_bakeoff (a full duplicate of the top-level gate_validate
# block, including its heavy candidates/hybrids/tilts/keel/cutoff_sweep rows —
# top-level gate_validate is masked down to just the ungated_*/span/wf_range
# sub-fields this dive actually reads, which are three orders of magnitude
# smaller: measured 169,500 bytes for the full gate_validate block on #335 vs a
# few KB for the specific sub-paths below).
FIELDS = [
    # identity / job metadata
    "id", "strategy", "scope", "instrument", "timeframe", "data_source",
    "source_name", "cost_pts", "commission_usd", "slippage_pts", "n_trials",
    "starred", "note", "archived", "date_from", "date_to", "createdAt",
    "timestamp", "famKey", "famSeq", "repeat_of_run", "wf_mode",
    "evolved_file", "multiplier", "days_in_test", "n_combos", "n_valid", "bars",
    "book",  # non-null => a BOOK job (pools legs, no WF folds — exclude from WF analysis)
    # Stage-A (75% in-sample) champion metrics — "best_*" IS the Stage-A
    # first-75%-split headline; there is NO separate saved field for the
    # Stage-A 25%-holdout slice (see NOTE in the module docstring below).
    "best_pnl_pts", "best_pnl_usd", "best_pnl_per_day", "best_pf",
    "best_win_rate", "best_trades", "best_dd_usd", "best_params",
    # walk-forward fold rows (PRIMARY scheme; each row carries that fold's own
    # re-tuned params + train_bars/test_bars/oos_*)
    "top10_results",
    # #88 OOS-checked champion selection — FULL block (candidates + robust),
    # each candidate carrying params/is_pnl/wf_oos_pnl/folds_held/crowned AND
    # (the #88b block, validate.py ~807-880) its own "lockbox"/"lb_equity" —
    # the one place a lockbox number exists for configs OTHER than the crowned
    # champion, i.e. the IS-max-vs-WF-crowned lockbox comparison Q2 needs.
    "selection",
    # validate.* — the Stage A/B/C report card, masked to the fields this dive
    # needs (excludes validate.gate_bakeoff, a duplicate of gate_validate; see
    # the module-level comment above)
    "validate.verdict", "validate.checks", "validate.n_pass", "validate.n_gates",
    "validate.wf_ran", "validate.wf_best_mode", "validate.n_folds",
    "validate.folds_held", "validate.wfe", "validate.windows", "validate.lb_idx",
    "validate.lockbox", "validate.wf_oos",  # wf_oos.equity kept (~1.6 KB, not trimmed)
    "validate.champion", "validate.wf_rolling", "validate.wf_anchored",
    "validate.dsr", "validate.is_pf", "validate.is_dd", "validate.is_sharpe",
    "validate.is_trades", "validate.n_params", "validate.trades_per_param",
    "validate.total_sharpe", "validate.total_sortino", "validate.total_win_rate",
    "validate.total_trades", "validate.total_dd", "validate.total_avg_win",
    "validate.total_avg_loss", "validate.mc_p95", "validate.pbo",
    "validate.transfer", "validate.thresholds", "validate.flags",
    "validate.plateau", "validate.evolved_file", "validate.discover",
    "validate.discover_err",
    "power",  # #94 statistical power for the lockbox verdict (top-level; validate.power unused/None)
    # gate_validate.* — the FIXED-champion sliced-per-stretch numbers (1E's WF
    # column reads ungated_wf); masked to just these sub-fields, NOT the whole
    # block (see comment above)
    "gate_validate.ungated_pre", "gate_validate.ungated_lockbox",
    "gate_validate.ungated_full", "gate_validate.ungated_is",
    "gate_validate.ungated_wf", "gate_validate.ungated_wf_lb",
    "gate_validate.wf_range", "gate_validate.span", "gate_validate.lockbox_from",
    "gate_validate.lockbox_months", "gate_validate.verdict",
    "gate_validate.gate_earns_pre",
]

# NOTE (surprise, confirmed against augur_engine/auto.py + validate.py): Stage
# A's own 75/25-split holdout metric (run_auto computes `rec["oos_pnl"]` etc.
# per top-24 config over the LAST 25% of the optimize window, augur_engine/
# auto.py lines ~1124-1132) is used only transiently to populate `A["top"]`
# inside validate.py's Stage A — and that Stage-A top-24 list (WITH its
# oos_pnl/oos_pf holdout numbers) is never written to the saved run doc at
# all. `top10_results` on the doc is `result.get("top")` from run_validate's
# RETURNED dict, which is the WALK-FORWARD fold list (`folds`), not Stage A's
# own top-24 — a naming collision between run_auto's "top" (Stage A configs)
# and run_validate's "top" (Stage B folds). There is therefore no saved field
# path for "the champion's Stage-A 25% holdout score" distinct from (a) the
# 75%-training best_* fields and (b) the walk-forward / gate_validate / lockbox
# numbers already masked above.


def _size(x):
    try:
        return len(json.dumps(x, default=str))
    except Exception:
        return FIELD_TRIM_BYTES + 1


def _trim_large_fields(doc):
    """Replace any TOP-LEVEL field (including selection/gate_validate/validate,
    which are the only ones capable of growing large under this mask) over
    FIELD_TRIM_BYTES with a marker, recording what was trimmed. Guards against
    an unusual run (e.g. save_fold_detail on, or an oversized selection pool)
    blowing the local runs.json up even though #335/#257 measured well under
    this cap."""
    trimmed = []
    for k, v in list(doc.items()):
        if v is None:
            continue
        n = _size(v)
        if n > FIELD_TRIM_BYTES:
            doc[k] = {"_trimmed": True, "_original_bytes": n}
            trimmed.append({"field": k, "bytes": n})
    return trimmed


def main():
    common.low_priority()
    db = common.fs_client()
    col = common.runs_collection(db)

    total = None
    try:
        agg = col.count().get()
        total = int(agg[0][0].value)
    except Exception as e:
        print(f"[extract_runs] count() aggregation failed ({type(e).__name__}: {e}) — "
              "proceeding without a known total")
    print(f"[extract_runs] collection reports {total if total is not None else '?'} run doc(s)")
    if total is not None and total > MAX_READS:
        raise SystemExit(f"REFUSING: {total} runs > MAX_READS={MAX_READS} budget — "
                          "narrow the query or raise the budget deliberately")

    q = col.select(FIELDS)
    runs = []
    n_reads = 0
    t0 = time.time()
    for snap in q.stream():
        n_reads += 1
        if n_reads > MAX_READS:
            raise SystemExit(f"REFUSING: exceeded MAX_READS={MAX_READS} mid-stream "
                              f"(read {n_reads} so far) — stopping without saving a "
                              "partial/inconsistent file")
        d = snap.to_dict() or {}
        d["id"] = d.get("id", snap.id)  # fall back to the doc id if the field is absent
        trimmed = _trim_large_fields(d)
        if trimmed:
            d["_trimmed_fields"] = trimmed
            print(f"  #{d['id']}: trimmed {[t['field'] for t in trimmed]} "
                  f"({[t['bytes'] for t in trimmed]} bytes)")
        runs.append(d)

    print(f"[extract_runs] streamed {n_reads} doc(s) in {time.time()-t0:.1f}s "
          f"(field-masked reads; 1 Firestore read each)")

    common._ensure_data_dir()
    out_path = os.path.join(common.DATA_DIR, "runs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(runs, f, default=str, indent=1)
    print(f"[extract_runs] saved {len(runs)} run(s) to {out_path} "
          f"({os.path.getsize(out_path)/1024:.0f} KB)")
    return runs


if __name__ == "__main__":
    main()

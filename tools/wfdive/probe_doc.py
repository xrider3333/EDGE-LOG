"""wfdive Gather step 2/5: open ONE full (un-masked) run doc, print its schema, and
save it to _wfdive_data/probe_<id>_full.json for other agents to inspect by hand.

Used during the initial dive to find field paths (validate/gate_validate/selection/
top10_results[0] keys) before writing extract_runs.py's field mask, and to sanity-
check specific runs (#335, #257) against known numbers. Each call is exactly ONE
Firestore read per run id — keep calls to a handful of ids, never a loop over the
whole collection (that is extract_runs.py's job, via a field mask).

Usage (from this worktree):
    python tools/wfdive/probe_doc.py 335 257 366
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def describe(d):
    lines = [f"TOP-LEVEL KEYS ({len(d)}):"]
    for k in sorted(d.keys()):
        v = d[k]
        t = type(v).__name__
        if isinstance(v, dict):
            ks = sorted(v.keys())
            extra = f" keys={ks[:8]}{'...' if len(ks) > 8 else ''}"
        elif isinstance(v, list):
            extra = f" len={len(v)}"
        else:
            extra = f" = {v!r}"[:120]
        lines.append(f"  {k:28s} {t:8s}{extra}")
    return "\n".join(lines)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    db = common.fs_client()
    col = common.runs_collection(db)
    for rid in argv:
        ref = col.document(str(rid))
        snap = ref.get()
        print(f"=== #{rid} exists={snap.exists} ===")
        if not snap.exists:
            continue
        d = snap.to_dict() or {}
        print(describe(d))
        common._ensure_data_dir()
        out = os.path.join(common.DATA_DIR, f"probe_{rid}_full.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(d, f, default=str, indent=1)
        print(f"saved full doc to {out} ({os.path.getsize(out)} bytes)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

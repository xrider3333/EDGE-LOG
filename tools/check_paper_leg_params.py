"""CHECK PAPER LEG PARAMS -- fails when a paper leg's parameter values no longer sit on the set
api/paper_leg_params.py records for it, or when index.html's inline PAPER_LEG_PARAMS is stale.

    python tools/check_paper_leg_params.py                  # Firestore run docs (read-only), then index.html
    python tools/check_paper_leg_params.py --cache DIR      # run docs from DIR/<run>.json (a saved trim)
    python tools/check_paper_leg_params.py --sync           # rewrite index.html's PAPER_LEG_PARAMS line
    python tools/check_paper_leg_params.py --no-docs        # skip the run docs (no credentials)

The set number is the rank of the leg's cell in the run doc's saved search grid (`points`) by
in-sample net - the order of the report's 1E config table under NET $ - see the module.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
METRIC = {'total_pnl', 'num_trades', 'win_rate', 'profit_factor', 'wins', 'losses', 'avg_pnl', 'max_drawdown',
          'fold', 'train_bars', 'test_bars', 'pnl', 'dd', 'trades', 'pf', 'wr', 'sharpe', 'sortino', 'n'}
# keys a live cfg adds that are not run parameters
NOT_PARAMS = {"asset", "phantom_safe", "sess_from", "sess_to"}
# the one line index.html carries (just above QE_LEG_VERSIONS, indented); the file is CRLF
INLINE_RE = re.compile("^[ \\t]*const PAPER_LEG_PARAMS=[^\\r\\n]*;(?=\\r?$)", re.M)


def live_cfgs():
    import api.paper as p
    import api.cloud_signal as cs
    cfgs = {}
    for v in p.PAPER_LEGS:
        cfgs[v["key"]] = {"params": dict(v.get("params") or {}), "gate": v.get("gate"), "run": (v.get("source") or {}).get("run")}
    for k, v in list(cs.CROWN_LEGS.items()) + list(cs.SHADOW_LEGS.items()):
        cfgs[k] = {"params": dict(v.get("params") or {}), "keel": v.get("keel")}
    return cfgs


def _eq(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _params_of(row):
    return {k: v for k, v in row.items() if k not in METRIC and not k.startswith("oos_") and not k.startswith("is_")}


def _on(leg, row):
    return all(k in row and _eq(v, row[k]) for k, v in leg.items())


def run_doc(rid, cache):
    if cache:
        f = os.path.join(cache, "%s.json" % rid)
        return json.load(open(f)) if os.path.exists(f) else None
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        cred = os.path.join(SHARED, "serviceAccount.json")
        if not os.path.exists(cred):
            cred = os.path.join(ROOT, "serviceAccount.json")
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client().collection("users").document(UID).collection("runs").document(str(rid)).get().to_dict()


def derive(doc, params):
    """(rank or None, grid size, matched_on) for a leg's params against one run doc."""
    lp = {k: v for k, v in params.items() if k not in NOT_PARAMS}
    V = doc.get("validate") or {}
    on = []
    if V.get("champion") and _on(lp, V.get("champion") or {}):
        on.append("champion")
    pts = [x for x in (doc.get("points") or []) if isinstance(x, dict)]
    pts = sorted(pts, key=lambda x: -float(x.get("pnl") or 0))
    rank = [i + 1 for i, x in enumerate(pts) if _on(lp, _params_of(x))]
    if rank:
        on.append("grid_rank_by_is_net")
    return (rank[0] if rank else None), len(pts), on


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--no-docs", action="store_true")
    a = ap.parse_args(argv)
    import api.paper_leg_params as m
    cfgs = live_cfgs()
    fails = []
    for k in m.CELLS:
        if k not in cfgs:
            fails.append("%s: recorded in paper_leg_params.CELLS but no such paper leg exists" % k)
    for k in cfgs:
        if k not in m.CELLS:
            fails.append("%s: a paper leg with no recorded set - add it to api/paper_leg_params.CELLS" % k)
    if not a.no_docs:
        docs = {}
        for k, c in sorted(m.CELLS.items()):
            if k not in cfgs:
                continue
            r = c["run"]
            if cfgs[k].get("run") not in (None, r):
                fails.append("%s: LEG_SOURCE says run %s, CELLS says %s" % (k, cfgs[k]["run"], r))
            if r not in docs:
                docs[r] = run_doc(r, a.cache)
            d = docs[r]
            if not d:
                fails.append("%s: run #%s doc not found" % (k, r))
                continue
            rank, grid, on = derive(d, cfgs[k]["params"])
            if rank != c["cell"] or grid != c["grid"]:
                fails.append("%s: run #%s -> set %r of %s by the run doc, CELLS records %r of %s (%s)"
                             % (k, r, rank, grid, c["cell"], c["grid"], ", ".join(on) or "no match"))
            print("%-20s #%s.%s %-6s %s" % (k, r, rank if rank is not None else "?", m.variant_of(cfgs[k]), ", ".join(on) or "NO MATCH"))
    # index.html's inline copy (read and written byte-for-byte: the file is CRLF)
    want = m.inline_js(cfgs)
    idx = os.path.join(ROOT, "index.html")
    src = open(idx, encoding="utf-8", newline="").read()
    mm = INLINE_RE.search(src)
    ind = mm.group(0)[:len(mm.group(0)) - len(mm.group(0).lstrip())] if mm else ""
    if not mm:
        fails.append("index.html: no 'const PAPER_LEG_PARAMS=' line")
    elif mm.group(0) != ind + want:
        if a.sync:
            open(idx, "w", encoding="utf-8", newline="").write(src[:mm.start()] + ind + want + src[mm.end():])
            print("index.html PAPER_LEG_PARAMS rewritten")
        else:
            fails.append("index.html: PAPER_LEG_PARAMS is stale - run with --sync")
    if fails:
        print("\n".join("FAIL " + f for f in fails))
        return 1
    print("OK: %d legs, every set matches" % len(m.CELLS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

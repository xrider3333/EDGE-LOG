"""Backfill engine-written SHARPE/SORTINO onto the GATE / TILT / HYBRID blocks of
runs that predate v73.419 -- IN PLACE, on their own run numbers.

Discipline: reproduce the run's gate bake-off exactly (same pinned config, window,
master, costs, lockbox boundary and walk-forward split), then VERIFY every block's
net + trade count against what is already stored. Only blocks that reproduce
EXACTLY get their two scalars written. A block that does not reproduce is left
alone -- writing a ratio computed on a different trade set than the dollars beside
it would be silently wrong.

Usage:  python backfill_scatter.py 234 243          (dry run, verifies only)
        python backfill_scatter.py 234 243 --write  (writes verified blocks)
"""
import sys, json, math
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import numpy as np
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

import augur_engine as ae
from augur_engine.engine import load_master_arrays, find_master, load_strategy, run_backtest
from augur_engine.ml_gate import gate_validate as GV

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
BLOCKS = ("pre", "lockbox", "full", "is_rng", "wf_rng", "wf_lb")

cred = credentials.Certificate(ROOT + r"\serviceAccount.json")
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)
db = firestore.client()
runs = db.collection("users").document(UID).collection("runs")

WRITE = "--write" in sys.argv
RIDS = [a for a in sys.argv[1:] if not a.startswith("--")]


def close(a, b, tol=1e-6):
    if a is None or b is None:
        return a is None and b is None
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def blk_matches(new, old):
    """A block reproduces when its dollars AND its trade count both match."""
    if not isinstance(new, dict) or not isinstance(old, dict):
        return False
    if int(new.get("num_trades") or -1) != int(old.get("num_trades") or -2):
        return False
    return close(new.get("total_pnl"), old.get("total_pnl"))


def add_scalars(dst, src, stats):
    """Copy sharpe/sortino from a reproduced block onto the stored block."""
    n = 0
    for k in ("sharpe", "sortino"):
        v = src.get(k)
        if v is not None and k not in dst:
            dst[k] = float(v)
            n += 1
    stats[0] += n
    return n


for rid in RIDS:
    print("=" * 74)
    ref = runs.document(rid)
    doc = ref.get().to_dict() or {}
    gv_old = doc.get("gate_validate")
    if not gv_old:
        print(f"RUN {rid}: no gate bake-off stored - nothing to fill."); continue

    strat = doc["strategy"]
    inst, tf = doc.get("instrument"), doc.get("timeframe", "5m")
    src_key = doc.get("data_source")
    dfrom, dto = doc.get("date_from"), doc.get("date_to")
    cost = float(doc.get("cost_pts") or 0)
    lb_from = gv_old.get("lockbox_from")
    lbm = int(gv_old.get("lockbox_months") or 12)
    gates = tuple(gv_old.get("gates") or ())
    thr = tuple(gv_old.get("thresholds") or ())
    print(f"RUN {rid}: {strat} | {inst} {tf} | {src_key} | {dfrom}..{dto} | cost {cost}")
    print(f"   lockbox_from {lb_from} | lockbox_months {lbm} | gates {len(gates)} x thr {len(thr)}")

    master = find_master(inst, tf, "rth", src_key)
    if master is None:
        print("   ! no master found - skipping"); continue
    arrays = load_master_arrays(master, date_from=dfrom, date_to=dto)
    mod = load_strategy(ROOT + r"\augur_strategies\\" + strat)
    base = run_backtest(mod, arrays=arrays, params={}, cost_pts=cost, return_trades=True)
    trades = base.get("trades") or []
    print(f"   re-ran pinned config: {len(trades)} trades, net {base.get('total_pnl'):.2f}")

    # ---- faithfulness gate #1: the whole book must reproduce -------------------
    uf = gv_old.get("ungated_full") or {}
    if int(uf.get("num_trades") or -1) != len(trades) or not close(uf.get("total_pnl"), base.get("total_pnl")):
        print(f"   ! ABORT - book does not reproduce (stored {uf.get('num_trades')} trades /"
              f" {uf.get('total_pnl')}). Data or engine drifted; refusing to write.")
        continue

    # ---- recover the EXACT walk-forward boundary ------------------------------
    # The doc keeps wf_range only as dates, but the original split was made on a bar
    # timestamp. The stored ungated IS trade count pins it exactly: the boundary is the
    # entry of the first walk-forward trade. wf_to was clamped to the lockbox start.
    idx = arrays["index"]; nb = len(idx)
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades if len(t) >= 3], key=lambda x: x[0])
    ets = np.array([idx[min(t[0], nb - 1)] for t in T])
    uis = gv_old.get("ungated_is") or {}
    n_is = int(uis.get("num_trades") or 0)
    if not n_is or n_is >= len(T):
        print("   ! no usable stored IS split - IS/WF blocks will be skipped")
        wf0 = None
    else:
        wf0 = pd.Timestamp(ets[n_is])
        print(f"   recovered walk-forward start {wf0} (from stored IS count {n_is})")

    gv_new = GV(arrays, trades, gates=gates, thresholds=thr, lockbox_months=lbm,
                wf_from=(str(wf0) if wf0 is not None else None),
                wf_to=(lb_from if wf0 is not None else None), lb_from=lb_from)
    if not gv_new:
        print("   ! recompute produced nothing - skipping"); continue

    stats = [0]           # scalars written
    filled, skipped = {}, {}

    def do_group(name, olds, news, keyf):
        newmap = {keyf(c): c for c in news}
        for o in olds:
            n = newmap.get(keyf(o))
            if n is None:
                skipped[name + ":missing"] = skipped.get(name + ":missing", 0) + 1
                continue
            for b in BLOCKS:
                ob, nb2 = o.get(b), n.get(b)
                if not isinstance(ob, dict) or not isinstance(nb2, dict):
                    continue
                if blk_matches(nb2, ob):
                    if add_scalars(ob, nb2, stats):
                        filled[name + "." + b] = filled.get(name + "." + b, 0) + 1
                else:
                    skipped[name + "." + b] = skipped.get(name + "." + b, 0) + 1
            # gate cards also carry the flattened pre_* pair
            if name == "gate" and isinstance(o.get("pre"), dict):
                pass

    # GATE candidates: stored cards keep block dicts under the same names
    do_group("gate", gv_old.get("candidates") or [], gv_new.get("candidates") or [],
             lambda c: (str(c.get("model")), round(float(c.get("threshold") or 0), 4)))
    do_group("tilt", gv_old.get("tilts") or [], gv_new.get("tilts") or [],
             lambda c: (str(c.get("model")), str(c.get("scheme"))))
    do_group("hybrid", gv_old.get("hybrids") or [], gv_new.get("hybrids") or [],
             lambda c: (str(c.get("model")), str(c.get("scheme")), round(float(c.get("floor") or 0), 4)))

    # the flattened pre_sharpe / pre_sortino the gate card carries alongside pre_pnl
    # A gate card does not store its pre-lockbox block as a dict -- it keeps those stats
    # flattened (pre_pnl / kept_pre), so verify against those two instead.
    nmap = {(str(c.get("model")), round(float(c.get("threshold") or 0), 4)): c
            for c in (gv_new.get("candidates") or [])}
    for o in (gv_old.get("candidates") or []):
        n = nmap.get((str(o.get("model")), round(float(o.get("threshold") or 0), 4)))
        # the recomputed card is flattened the same way the stored one is, so both the
        # verification and the two scalars come off the pre_* fields, not a nested block
        ok = bool(n) and int((n or {}).get("kept_pre") or -1) == int(o.get("kept_pre") or -2) \
            and close((n or {}).get("pre_pnl"), o.get("pre_pnl"))
        if ok:
            for a, b in (("pre_sharpe", "pre_sharpe"), ("pre_sortino", "pre_sortino")):
                v = n.get(b)
                if v is not None and a not in o:
                    o[a] = float(v); stats[0] += 1
                    filled["gate.pre(flat)"] = filled.get("gate.pre(flat)", 0) + 1
        elif n:
            skipped["gate.pre(flat)"] = skipped.get("gate.pre(flat)", 0) + 1

    # the ungated reference blocks the matrix reads beside the variants
    for k in ("ungated_pre", "ungated_lockbox", "ungated_full", "ungated_is",
              "ungated_wf", "ungated_wf_lb"):
        ob, nb2 = gv_old.get(k), gv_new.get(k)
        if isinstance(ob, dict) and isinstance(nb2, dict):
            if blk_matches(nb2, ob):
                if add_scalars(ob, nb2, stats):
                    filled[k] = 1
            else:
                skipped[k] = 1

    print(f"   FILLED blocks: {json.dumps(filled, sort_keys=True)}")
    print(f"   SKIPPED (did not reproduce): {json.dumps(skipped, sort_keys=True) or '{}'}")
    print(f"   scalars written into the doc structure: {stats[0]}")

    if WRITE and stats[0]:
        ref.update({"gate_validate": gv_old})
        print(f"   >> WROTE run {rid} (gate bake-off updated in place)")
    elif WRITE:
        print("   >> nothing verified - doc left untouched")
    else:
        print("   (dry run - no write)")

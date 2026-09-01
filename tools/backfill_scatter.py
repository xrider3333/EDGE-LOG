"""Backfill engine-written SHARPE / SORTINO onto the GATE / TILT / HYBRID blocks of runs
saved before v73.419 -- IN PLACE, on their own run numbers.

Those two measures come off a stored equity curve, and only the RAW top-10 keep one, so on
an older run every ML column sits the SORTINO / SHARPE axes out and the 1E scatter warns
"N of M not plotted". The engine writes them at validate time now; this fills in the past.

DISCIPLINE -- the whole point of this tool:
  * reproduce the run's bake-off exactly: its own pinned/crowned config, window, master,
    costs, lockbox boundary and walk-forward split;
  * VERIFY every recomputed block against the net AND trade count already stored;
  * write the two scalars ONLY onto blocks that reproduce. A ratio computed from a
    different trade set than the dollars beside it is silently wrong, and silently wrong
    is worse than missing.

CONFIG RESOLUTION (this one bit hard -- keep it):
  A PINNED card carries its configuration in DEFAULT_PARAMS *only*, and several cards reuse
  the parent's function outright (ORB_3_6_C2.py ends `run_backtest = _base.run_backtest`).
  engine.run_backtest does NOT fill defaults, so params={} runs the PARENT's signature
  defaults -- for ORB_3_6_C2 that is breakeven OFF / partial 3.0 / trail 3, i.e. the
  pre-breakeven #230 book, which replayed #230's $348,129 instead of the crown's $389,874.
  So: try the run's saved champion params first, fall back to DEFAULT_PARAMS, and keep
  whichever actually reproduces.

Usage:
  python tools/backfill_scatter.py 234 243           verify only (dry run)
  python tools/backfill_scatter.py 234 --write       write verified blocks
  python tools/backfill_scatter.py --all             verify every unfilled run
  python tools/backfill_scatter.py --all --write     fill everything that reproduces
  python tools/backfill_scatter.py --all --write --limit 10
"""
import sys, os, json, math, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

import augur_engine as ae
from augur_engine.engine import load_master_arrays, find_master, load_strategy, run_backtest
from augur_engine.ml_gate import gate_validate as GV

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
BLOCKS = ("pre", "lockbox", "full", "is_rng", "wf_rng", "wf_lb")
DOC_CEILING = 1_000_000          # Firestore hard cap is 1 MiB; leave room for the additions

# the admin key is gitignored, so it lives in the shared checkout even when this runs
# from a worktree -- look there too rather than dying on a missing file.
_CRED = next((p for p in (
    os.path.join(ROOT, "serviceAccount.json"),
    os.path.expanduser(r"~\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"),
) if os.path.isfile(p)), None)
if not _CRED:
    raise SystemExit("serviceAccount.json not found (checked this repo and the shared checkout)")
cred = credentials.Certificate(_CRED)
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)
db = firestore.client()
runs = db.collection("users").document(UID).collection("runs")

WRITE = "--write" in sys.argv
ALL = "--all" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])
RIDS = [a for a in sys.argv[1:] if not a.startswith("--") and a.isdigit()]


def close(a, b, tol=1e-6):
    if a is None or b is None:
        return a is None and b is None
    a, b = float(a), float(b)
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def blk_matches(new, old):
    if not isinstance(new, dict) or not isinstance(old, dict):
        return False
    if int(new.get("num_trades") or -1) != int(old.get("num_trades") or -2):
        return False
    return close(new.get("total_pnl"), old.get("total_pnl"))


def is_filled(gv):
    cands = gv.get("candidates") or []
    tilts = gv.get("tilts") or []
    return (any(c.get("pre_sharpe") is not None for c in cands)
            or any((t.get("full") or {}).get("sharpe") is not None for t in tilts))


def candidate_configs(doc, mod):
    """The configs worth trying, best guess first. Verification decides which wins."""
    out = []
    bp = doc.get("best_params")
    if isinstance(bp, dict) and bp:
        out.append(("saved champion params", dict(bp)))
    dp = ae.strategy_params(mod) or {}
    pin = {k: v.get("default") for k, v in dp.items()
           if isinstance(v, dict) and v.get("default") is not None}
    if pin:
        out.append(("DEFAULT_PARAMS", pin))
    return out


def backfill(rid, write=False):
    """-> (status, note, scalars_written)"""
    ref = runs.document(str(rid))
    doc = ref.get().to_dict() or {}
    gv_old = doc.get("gate_validate")
    if not isinstance(gv_old, dict):
        return "skip", "no gate bake-off stored", 0
    if is_filled(gv_old):
        return "skip", "already filled", 0

    strat = doc.get("strategy")
    if not strat or not os.path.isfile(os.path.join(ROOT, "augur_strategies", str(strat))):
        return "skip", f"strategy file missing: {strat}", 0

    inst, tf = doc.get("instrument"), doc.get("timeframe", "5m")
    src = doc.get("data_source") or None
    sess = "eth" if (src and "eth" in str(src).lower()) else "rth"
    dfrom, dto = doc.get("date_from"), doc.get("date_to")
    cost = float(doc.get("cost_pts") or 0)
    lb_from = gv_old.get("lockbox_from")
    lbm = int(gv_old.get("lockbox_months") or 12)
    gates = tuple(gv_old.get("gates") or ())
    thr = tuple(gv_old.get("thresholds") or ())
    if not gates or not thr:
        return "skip", "bake-off records no gate/threshold set", 0

    master = find_master(inst, tf, sess, src)
    if master is None:
        return "skip", f"no master for {inst} {tf} {sess} {src}", 0
    arrays = load_master_arrays(master, date_from=dfrom, date_to=dto)
    mod = load_strategy(os.path.join(ROOT, "augur_strategies", str(strat)))

    uf = gv_old.get("ungated_full") or {}
    want_n, want_p = uf.get("num_trades"), uf.get("total_pnl")

    trades = used = None
    for label, cfg in candidate_configs(doc, mod):
        try:
            base = run_backtest(mod, arrays=arrays, params=cfg, cost_pts=cost,
                                return_trades=True)
        except Exception:
            continue
        t = base.get("trades") or []
        if int(want_n or -1) == len(t) and close(want_p, base.get("total_pnl")):
            trades, used = t, label
            break
    if trades is None:
        return "nomatch", ("book does not reproduce under any saved config "
                           f"(stored {want_n} trades / {want_p})"), 0

    idx = arrays["index"]; nb = len(idx)
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades if len(t) >= 3],
               key=lambda x: x[0])
    ets = np.array([idx[min(t[0], nb - 1)] for t in T])
    # the doc keeps wf_range only as DATES, but the stored IS trade count pins the real
    # boundary exactly: it is the entry of the first walk-forward trade.
    n_is = int((gv_old.get("ungated_is") or {}).get("num_trades") or 0)
    wf0 = pd.Timestamp(ets[n_is]) if (n_is and n_is < len(T)) else None

    gv_new = GV(arrays, trades, gates=gates, thresholds=thr, lockbox_months=lbm,
                wf_from=(str(wf0) if wf0 is not None else None),
                wf_to=(lb_from if wf0 is not None else None), lb_from=lb_from)
    if not gv_new:
        return "nomatch", "recompute produced no bake-off", 0

    n_written = [0]
    skipped = {}

    def add(dst, src_blk):
        for k in ("sharpe", "sortino"):
            v = src_blk.get(k)
            if v is not None and k not in dst:
                dst[k] = float(v); n_written[0] += 1

    def group(name, olds, news, keyf):
        nmap = {keyf(c): c for c in news}
        for o in olds:
            n = nmap.get(keyf(o))
            if n is None:
                skipped[name] = skipped.get(name, 0) + 1
                continue
            for b in BLOCKS:
                ob, nbk = o.get(b), n.get(b)
                if isinstance(ob, dict) and isinstance(nbk, dict):
                    if blk_matches(nbk, ob):
                        add(ob, nbk)
                    else:
                        skipped[f"{name}.{b}"] = skipped.get(f"{name}.{b}", 0) + 1

    group("gate", gv_old.get("candidates") or [], gv_new.get("candidates") or [],
          lambda c: (str(c.get("model")), round(float(c.get("threshold") or 0), 4)))
    group("tilt", gv_old.get("tilts") or [], gv_new.get("tilts") or [],
          lambda c: (str(c.get("model")), str(c.get("scheme"))))
    group("hybrid", gv_old.get("hybrids") or [], gv_new.get("hybrids") or [],
          lambda c: (str(c.get("model")), str(c.get("scheme")),
                     round(float(c.get("floor") or 0), 4)))

    # a gate card keeps its pre-lockbox stats FLATTENED (pre_pnl / kept_pre), not as a
    # nested block -- so both the check and the two scalars come off the pre_* fields.
    nmap = {(str(c.get("model")), round(float(c.get("threshold") or 0), 4)): c
            for c in (gv_new.get("candidates") or [])}
    for o in (gv_old.get("candidates") or []):
        n = nmap.get((str(o.get("model")), round(float(o.get("threshold") or 0), 4)))
        if not n:
            continue
        if int(n.get("kept_pre") or -1) == int(o.get("kept_pre") or -2) \
           and close(n.get("pre_pnl"), o.get("pre_pnl")):
            for a, b in (("pre_sharpe", "pre_sharpe"), ("pre_sortino", "pre_sortino")):
                v = n.get(b)
                if v is not None and a not in o:
                    o[a] = float(v); n_written[0] += 1
        else:
            skipped["gate.pre"] = skipped.get("gate.pre", 0) + 1

    for k in ("ungated_pre", "ungated_lockbox", "ungated_full", "ungated_is",
              "ungated_wf", "ungated_wf_lb"):
        ob, nbk = gv_old.get(k), gv_new.get(k)
        if isinstance(ob, dict) and isinstance(nbk, dict) and blk_matches(nbk, ob):
            add(ob, nbk)

    if not n_written[0]:
        return "nomatch", f"nothing verified (skips: {skipped})", 0

    note = f"via {used}" + (f" | PARTIAL, skips: {skipped}" if skipped else "")
    if write:
        size = len(json.dumps(doc, default=str))
        if size > DOC_CEILING:
            return "toobig", f"doc {round(size/1024)} KB is at the Firestore cap", 0
        ref.update({"gate_validate": gv_old})
    return ("wrote" if write else "ok"), note, n_written[0]


targets = RIDS
if ALL:
    targets = []
    for d in runs.select(["gate_validate"]).stream():
        gv = (d.to_dict() or {}).get("gate_validate")
        if isinstance(gv, dict) and not is_filled(gv):
            targets.append(d.id)
    targets.sort(key=lambda x: int(x) if str(x).isdigit() else 0, reverse=True)
    if LIMIT:
        targets = targets[:LIMIT]

print(f"backfill_scatter: {len(targets)} run(s) | write={WRITE}", flush=True)
tally, total, t0 = {}, 0, time.time()
for i, rid in enumerate(targets, 1):
    ts = time.time()
    try:
        status, note, n = backfill(rid, write=WRITE)
    except Exception as e:
        status, note, n = "error", f"{type(e).__name__}: {e}", 0
        traceback.print_exc()
    tally[status] = tally.get(status, 0) + 1
    total += n
    print(f"[{i}/{len(targets)}] run {rid}: {status} (+{n}) {note} "
          f"[{time.time()-ts:.0f}s]", flush=True)

print(f"\nDONE in {(time.time()-t0)/60:.1f} min | scalars written: {total} | {tally}",
      flush=True)

"""wfdive VERIFY replay: does the crowned champion's FIXED-settings walk-forward
figure lean on the part of the WF span that Stage A already optimised on?

Engine facts (augur_engine/auto.py): Stage A's in-sample slice is bars [0, int(0.75n))
of the optimize window (OOS_SPLIT = 0.75, bar-count split); the walk-forward folds
(both schemes) test bars [init, n) with init = int(0.40n). So bars [0.40n, 0.75n) are
BOTH "walk-forward years" for the fixed champion AND inside Stage A's search window.

For each run: ONE backtest of validate.champion over the optimize window (the exact
make_slice_evaluator path the engine uses), trades entry-bar-sliced into
  A = [init, ksplit)   WF years that Stage A searched on
  B = [ksplit, n)      WF years Stage A never saw
and the run's own PRIMARY-scheme re-tuned fold rows summed over the same two stretches
(fold test bounds rebuilt from train_bars/test_bars exactly as auto.py lays them out).

One heavy replay at a time (common.cpu_lock), below-normal priority, single process.
Run from the worktree root:  python tools/wfdive/verify_predict_replay.py [ids...]
Writes _wfdive_data/verify_predict_replay.json.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth", "yahoo_adj": "rth"}  # = tools/backfill_wf_oos.py
DEFAULT_IDS = [335, 243, 257, 304, 384]


def _stats(pnls):
    if not pnls:
        return None
    gw = sum(x for x in pnls if x > 0); gl = -sum(x for x in pnls if x < 0)
    return {"n": len(pnls), "net": round(sum(pnls), 1),
            "pf": (round(gw / gl, 3) if gl > 0 else None),
            "win_rate": round(100.0 * sum(1 for x in pnls if x > 0) / len(pnls), 1)}


def main(ids):
    common.low_priority()
    common.setup_data_env()
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.auto import make_slice_evaluator, OOS_SPLIT
    import pandas as pd

    runs = common.load_runs()
    by = {r["id"]: r for r in runs}
    out = {}
    for rid in ids:
        d = by.get(rid)
        if not d:
            out[str(rid)] = {"error": "not in runs.json"}; continue
        v = d.get("validate") or {}
        champ = v.get("champion") or {}
        win = (v.get("windows") or {}).get("optimize") or [None, None]
        sess = SESSION.get(d.get("data_source"))
        if not champ or not win[0] or not sess:
            out[str(rid)] = {"error": f"missing champion/window/session ({d.get('data_source')!r})"}; continue
        master = find_master(d["instrument"], d["timeframe"], sess, d["data_source"])
        if master is None:
            out[str(rid)] = {"error": "no master"}; continue
        t0 = time.time()
        with common.cpu_lock(f"verify replay #{rid}"):
            arrays = load_master_arrays(master, date_from=str(win[0]), date_to=str(win[1]))
            n = len(arrays["close"])
            ev = make_slice_evaluator(d["strategy"], arrays, float(d.get("cost_pts") or 0.0))
            m = ev(0, n, champ, keep_trades=True)
        el = time.time() - t0
        if not m:
            out[str(rid)] = {"error": "backtest returned None"}; continue
        trades = m.get("trades") or []
        init = int(n * 0.40); ksplit = int(n * OOS_SPLIT)
        idx = arrays.get("index")
        def _date(i):
            try:
                return str(pd.Timestamp(idx[max(0, min(i, len(idx) - 1))]).date())
            except Exception:
                return None
        def _years(a, b):
            try:
                return round((pd.Timestamp(idx[min(b, len(idx) - 1)]) - pd.Timestamp(idx[a])).total_seconds() / (365.25 * 86400), 3)
            except Exception:
                return None
        A = [float(t[2]) for t in trades if init <= int(t[0]) < ksplit]
        B = [float(t[2]) for t in trades if ksplit <= int(t[0]) < n]
        IS = [float(t[2]) for t in trades if int(t[0]) < ksplit]
        WF = [float(t[2]) for t in trades if int(t[0]) >= init]
        # re-tuned fold rows on the same stretches (primary scheme rows = top10_results)
        rows = [r for r in (d.get("top10_results") or []) if isinstance(r, dict) and r.get("fold") is not None]
        nf = len(rows)
        tsize = max(1, (n - init) // nf) if nf else None
        rt = {"A": [], "B": [], "mixed": []}
        fold_map = []
        for r in rows:
            fno = int(r["fold"])
            te_s = init + (fno - 1) * tsize
            te_e = n if fno == nf else te_s + tsize
            ok_bars = (int(r.get("test_bars") or 0) == te_e - te_s)
            tag = "A" if te_e <= ksplit else ("B" if te_s >= ksplit else "mixed")
            rt[tag].append(r)
            fold_map.append({"fold": fno, "te_s": te_s, "te_e": te_e, "from": _date(te_s), "to": _date(te_e - 1),
                             "stretch": tag, "test_bars_match": ok_bars, "oos_pnl": round(float(r.get("oos_pnl") or 0), 1),
                             "oos_trades": r.get("oos_trades"), "oos_pf": r.get("oos_pf")})
        def _rt_sum(rs):
            if not rs:
                return None
            return {"n_folds": len(rs), "net": round(sum(float(r.get("oos_pnl") or 0) for r in rs), 1),
                    "trades": sum(int(r.get("oos_trades") or 0) for r in rs),
                    "held": sum(1 for r in rs if float(r.get("oos_pf") or 0) > 1)}
        # fixed champion restricted to the exact fold bounds of the A-folds and B-folds (so both sides
        # cover identical bars, ignoring a 'mixed' fold that straddles ksplit)
        def _fixed_on(rs):
            sel = []
            for r in rs:
                fm = next(x for x in fold_map if x["fold"] == int(r["fold"]))
                sel += [float(t[2]) for t in trades if fm["te_s"] <= int(t[0]) < fm["te_e"]]
            return _stats(sel)
        out[str(rid)] = {
            "strategy": d["strategy"], "instrument": d["instrument"], "timeframe": d["timeframe"], "session": sess,
            "optimize_window": win, "bars_replayed": n, "bars_on_doc": d.get("bars"),
            "init_bar_0_40n": init, "ksplit_bar_0_75n": ksplit,
            "date_init": _date(init), "date_ksplit": _date(ksplit), "date_end": _date(n - 1),
            "years_A": _years(init, ksplit), "years_B": _years(ksplit, n - 1),
            "full_window_champion": {"n": m.get("num_trades"), "net": round(float(m.get("total_pnl") or 0), 1), "pf": m.get("profit_factor")},
            "doc_ungated_wf": ((d.get("gate_validate") or {}).get("ungated_wf") or {}).get("total_pnl"),
            "doc_ungated_wf_n": ((d.get("gate_validate") or {}).get("ungated_wf") or {}).get("num_trades"),
            "fixed_IS_0_to_ksplit": _stats(IS), "doc_best_pnl_pts": d.get("best_pnl_pts"), "doc_best_trades": d.get("best_trades"),
            "fixed_WF_all": _stats(WF),
            "fixed_A_wf_inside_stageA_search": _stats(A), "fixed_B_wf_never_searched": _stats(B),
            "fixed_on_A_folds_exact_bounds": _fixed_on(rt["A"]), "fixed_on_B_folds_exact_bounds": _fixed_on(rt["B"]),
            "retuned_A_folds": _rt_sum(rt["A"]), "retuned_B_folds": _rt_sum(rt["B"]), "retuned_mixed_fold": _rt_sum(rt["mixed"]),
            "wf_best_mode": v.get("wf_best_mode"), "fold_map": fold_map, "elapsed_s": round(el, 1),
        }
        print(f"#{rid} {d['strategy']} replayed {n} bars in {el:.1f}s; fixed A {out[str(rid)]['fixed_A_wf_inside_stageA_search']} | "
              f"fixed B {out[str(rid)]['fixed_B_wf_never_searched']} | retuned A {out[str(rid)]['retuned_A_folds']} | retuned B {out[str(rid)]['retuned_B_folds']}")
    path = os.path.join(common.DATA_DIR, "verify_predict_replay.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, default=str, indent=1)
    print(f"saved -> {path}")


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] or DEFAULT_IDS
    main(ids)

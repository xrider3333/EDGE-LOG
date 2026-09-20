r"""Validate a candidate matrix (build_matrix.py output) against the source run's OWN saved
figures -- owner request 2026-09-16, step 3 of the candidate-matrix job.

Two checks, no market data reloaded (everything comes from the .npz/.json build_matrix.py
already produced plus the run doc already in runs.json):

  (a) FULL-WINDOW REPRODUCTION. The matrix's "champion" row (validate.champion / best_params,
      replayed warm over the run's own full window) must reproduce:
        - gate_validate.ungated_full   (net, trades) over the WHOLE window
        - gate_validate.ungated_lockbox (net, trades) over entries >= lockbox_from
      (gate_validate's own ungated_* slices are built the identical way: ONE full-window
      champion backtest, entries assigned to windows by ENTRY TIMESTAMP -- see
      augur_engine/ml_gate.py `_sl(entry_ts, pnls, t0, t1)` and validate.py's
      `full = run_backtest(..., date_from=opt_from, date_to=date_to, return_trades=True)`.)

  (b) FOLD ARGMAX REPRODUCTION. For >=2 saved walk-forward fold rows (top10_results), the
      argmax of TRAINING-window net among the matrix's first n_trials "sampler" candidates,
      after augur_engine.auto.WF_MIN_SIDE/MAX_TRADE_RATE/MAX_PF (`_is_real`) + min_trades
      (exactly _wf_fold_row's own selection rule), should be the SAME params the run actually
      saved for that fold, and that pick's TEST-window net (from the SAME warm trade list)
      should be close to the saved oos_pnl -- with any gap attributable to WARM (this matrix)
      vs COLD (the saved fold, which re-ran the strategy from a blank slate at the fold's own
      training-window start) evaluation, quantified explicitly.

Usage:
    python tools/wfdive/isdepth/validate_matrix.py 299
    python tools/wfdive/isdepth/validate_matrix.py 299 --folds 1 5 8
"""
import argparse
import json
import os
import sys

WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, WORKTREE_ROOT)
TOOLS_DIR = os.path.join(WORKTREE_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from tools.wfdive import common  # noqa: E402

OUT_DIR = os.path.join(common.DATA_DIR, "isdepth")

WF_MIN_SIDE = 5
MAX_TRADE_RATE = 0.015
MAX_PF = 6.0


def load_matrix(run_id):
    import numpy as np
    npz_path = os.path.join(OUT_DIR, f"matrix_{run_id}.npz")
    json_path = os.path.join(OUT_DIR, f"matrix_{run_id}.json")
    z = np.load(npz_path)
    with open(json_path, "r", encoding="utf-8") as f:
        side = json.load(f)
    return z, side


def config_trades(z, side, cfg_index):
    """(entry_bar, exit_bar, net) arrays for one config index, from the CSR-style offsets."""
    off = z["offsets"]
    a, b = int(off[cfg_index]), int(off[cfg_index + 1])
    return z["entry_bar"][a:b], z["exit_bar"][a:b], z["net"][a:b], z["entry_ns"][a:b]


def window_stats(net):
    """num_trades/net/wins/losses/profit_factor for an already-sliced net array."""
    import numpy as np
    n = len(net)
    if n == 0:
        return {"num_trades": 0, "net": 0.0, "wins": 0, "losses": 0, "profit_factor": 0.0}
    gw = float(net[net > 0].sum())
    gl = float(-net[net < 0].sum())
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    return {"num_trades": int(n), "net": float(net.sum()),
            "wins": int((net > 0).sum()), "losses": int((net < 0).sum()), "profit_factor": pf}


def is_real(stats, nbars):
    return (stats["wins"] >= WF_MIN_SIDE and stats["losses"] >= WF_MIN_SIDE
            and (stats["num_trades"] / max(1, nbars)) <= MAX_TRADE_RATE
            and stats["profit_factor"] <= MAX_PF)


def check_full_and_lockbox(doc, z, side):
    import pandas as pd
    cfg_idx = side["champion_index"]
    if cfg_idx >= len(side["configs"]):
        return {"ok": False, "reason": f"champion_index {cfg_idx} not built yet "
                f"({len(side['configs'])} configs built so far)"}
    entry_bar, exit_bar, net, entry_ns = config_trades(z, side, cfg_idx)
    full = {"num_trades": int(len(net)), "net": float(net.sum())}

    gv = doc.get("gate_validate") or {}
    saved_full = gv.get("ungated_full") or {}
    saved_lb = gv.get("ungated_lockbox") or {}
    lb_from = gv.get("lockbox_from") or side.get("lockbox_from")

    out = {"champion_index": cfg_idx, "n_bars": side["n_bars"],
          "full": {"replayed_trades": full["num_trades"], "replayed_net": full["net"],
                   "saved_trades": saved_full.get("num_trades"), "saved_net": saved_full.get("total_pnl"),
                   "d_trades": (full["num_trades"] - saved_full.get("num_trades", 0)
                                if saved_full.get("num_trades") is not None else None),
                   "d_net": (full["net"] - saved_full.get("total_pnl", 0.0)
                            if saved_full.get("total_pnl") is not None else None)}}

    if lb_from:
        cutoff_ns = int(pd.Timestamp(lb_from, tz="US/Eastern").value)
        mask = entry_ns >= cutoff_ns
        lb_net = float(net[mask].sum())
        lb_n = int(mask.sum())
        out["lockbox"] = {"lockbox_from": lb_from, "replayed_trades": lb_n, "replayed_net": lb_net,
                          "saved_trades": saved_lb.get("num_trades"), "saved_net": saved_lb.get("total_pnl"),
                          "d_trades": (lb_n - saved_lb.get("num_trades", 0)
                                       if saved_lb.get("num_trades") is not None else None),
                          "d_net": (lb_net - saved_lb.get("total_pnl", 0.0)
                                   if saved_lb.get("total_pnl") is not None else None)}
    else:
        out["lockbox"] = {"error": "no lockbox_from on the doc/sidecar"}

    net_tol = max(0.05, 1e-4 * abs(saved_full.get("total_pnl", 0.0) or 0.0))
    d_net_full = out["full"]["d_net"]
    ok_full = (out["full"]["d_trades"] == 0 and d_net_full is not None and abs(d_net_full) <= net_tol)
    lb = out.get("lockbox", {})
    lb_tol = max(0.05, 1e-4 * abs(saved_lb.get("total_pnl", 0.0) or 0.0))
    d_net_lb = lb.get("d_net")
    ok_lb = ("error" not in lb and lb.get("d_trades") == 0
             and d_net_lb is not None and abs(d_net_lb) <= lb_tol)
    out["ok_full"] = bool(ok_full)
    out["ok_lockbox"] = bool(ok_lb)
    out["net_tol"] = net_tol
    out["lb_tol"] = lb_tol
    return out


def fold_window_bounds(mode, fb):
    te_s, te_e = fb["te_s"], fb["te_e"]
    train_bars = fb.get("train_bars_saved")
    if mode == "anchored":
        tr_start, tr_end = 0, te_s
    else:  # rolling
        tr_start, tr_end = te_s - int(train_bars), te_s
    return tr_start, tr_end, te_s, te_e


def check_fold(doc, z, side, fold_no):
    top = doc.get("top10_results") or []
    row = next((r for r in top if int(r.get("fold")) == fold_no), None)
    if row is None:
        return {"ok": False, "reason": f"no saved fold {fold_no} on this run"}
    fb = next((f for f in side["fold_bounds"] if f["fold"] == fold_no), None)
    if fb is None:
        return {"ok": False, "reason": f"fold {fold_no} not in sidecar fold_bounds"}
    mode = side["wf_mode"]
    tr_start, tr_end, te_s, te_e = fold_window_bounds(mode, fb)
    nbars_train = tr_end - tr_start
    min_trades = side["min_trades"]
    n_trials = side["n_trials"]
    pkeys = side["pkeys"]

    sampler_cfgs = [c for c in side["configs"] if c["tag"] == "sampler" and c["index"] < n_trials]
    if len(sampler_cfgs) < n_trials:
        return {"ok": False, "reason": f"only {len(sampler_cfgs)}/{n_trials} sampler configs "
                "built so far - build the matrix further before validating folds"}

    recs = []
    for c in sampler_cfgs:
        entry_bar, exit_bar, net, _ = config_trades(z, side, c["index"])
        mask = (entry_bar >= tr_start) & (entry_bar < tr_end)
        tr_net = net[mask]
        if len(tr_net) < min_trades:
            continue
        stats = window_stats(tr_net)
        recs.append((c, stats))
    if not recs:
        return {"ok": False, "reason": "no sampler candidate cleared min_trades on the "
                f"training window [{tr_start},{tr_end})"}
    gated = [(c, s) for c, s in recs if is_real(s, nbars_train)]
    pool = gated or recs
    champ_c, champ_s = max(pool, key=lambda cs: cs[1]["net"])

    saved_params = {k: row.get(k) for k in pkeys}
    picked_params = champ_c["params"]
    params_match = all(
        (abs(float(picked_params[k]) - float(saved_params[k])) < 1e-6
         if isinstance(saved_params[k], (int, float)) and isinstance(picked_params.get(k), (int, float))
         else picked_params.get(k) == saved_params[k])
        for k in pkeys
    )

    # test-window (warm) net for the picked candidate, vs the saved oos figure (cold)
    entry_bar, exit_bar, net, _ = config_trades(z, side, champ_c["index"])
    mask_te = (entry_bar >= te_s) & (entry_bar < te_e)
    warm_test = window_stats(net[mask_te])
    saved_oos_net = float(row.get("oos_pnl") or 0.0)
    saved_oos_trades = int(row.get("oos_trades") or 0)

    return {
        "ok": True, "fold": fold_no, "mode": mode,
        "train_window": [tr_start, tr_end], "test_window": [te_s, te_e],
        "n_train_bars": nbars_train, "n_candidates_considered": len(recs),
        "n_gated": len(gated),
        "picked_index": champ_c["index"], "picked_train_net": champ_s["net"],
        "picked_train_trades": champ_s["num_trades"],
        "params_match_saved_fold_champion": bool(params_match),
        "picked_params": picked_params, "saved_params": saved_params,
        "warm_test_net": warm_test["net"], "warm_test_trades": warm_test["num_trades"],
        "cold_saved_oos_net": saved_oos_net, "cold_saved_oos_trades": saved_oos_trades,
        "d_net_warm_minus_cold": warm_test["net"] - saved_oos_net,
        "d_trades_warm_minus_cold": warm_test["num_trades"] - saved_oos_trades,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", type=int)
    ap.add_argument("--folds", type=int, nargs="*", default=None,
                    help="fold numbers to check (default: first and last saved fold)")
    args = ap.parse_args()

    doc = next(r for r in common.load_runs() if str(r.get("id")) == str(args.run_id))
    z, side = load_matrix(args.run_id)

    out = {"run_id": args.run_id, "strategy": side["strategy"], "n_configs_built": len(side["configs"])}
    out["full_and_lockbox"] = check_full_and_lockbox(doc, z, side)

    fold_nos = args.folds
    if not fold_nos:
        all_folds = sorted(f["fold"] for f in side["fold_bounds"])
        fold_nos = sorted(set([all_folds[0], all_folds[len(all_folds) // 2], all_folds[-1]]))
    out["folds"] = [check_fold(doc, z, side, f) for f in fold_nos]

    path = os.path.join(OUT_DIR, f"validate_{args.run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)

    fal = out["full_and_lockbox"]
    print(f"=== run #{args.run_id} {side['strategy']} -- full+lockbox reproduction ===")
    print(json.dumps(fal, indent=1, default=str))
    print(f"\n=== fold argmax reproduction ({len(out['folds'])} fold(s) checked) ===")
    for fr in out["folds"]:
        if not fr.get("ok"):
            print(f"fold {fr.get('fold')}: SKIPPED - {fr.get('reason')}")
            continue
        print(f"fold {fr['fold']} ({fr['mode']}): train={fr['train_window']} test={fr['test_window']} "
             f"n_train_bars={fr['n_train_bars']} candidates_min_trades_ok={fr['n_candidates_considered']} "
             f"gated={fr['n_gated']}")
        print(f"  picked idx={fr['picked_index']} train_net={fr['picked_train_net']:.2f} "
             f"train_trades={fr['picked_train_trades']} MATCH_SAVED_FOLD_CHAMPION="
             f"{fr['params_match_saved_fold_champion']}")
        print(f"  test(warm) net={fr['warm_test_net']:.2f} trades={fr['warm_test_trades']} vs "
             f"saved(cold) oos net={fr['cold_saved_oos_net']:.2f} trades={fr['cold_saved_oos_trades']} "
             f"-- d_net={fr['d_net_warm_minus_cold']:+.2f} d_trades={fr['d_trades_warm_minus_cold']:+d}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()

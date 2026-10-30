# -*- coding: utf-8 -*-
"""WF CHAIN REBUILD + FOUR NUMBERS for a NOISE validate run (MANAGER #93; the validate store keeps only chain points).

For each walk-forward fold (validate.top10_results rows: the fold champion's params, train_bars, test_bars, oos_pnl,
oos_trades) the champion is re-run on the validate's own optimize-window arrays from bar 0 (= the warm start) and its
trades that ENTER inside the fold's test slice [train_bars, train_bars + test_bars) are kept. Parity: each fold's net
points and trade count must equal the stored oos_pnl / oos_trades, and the chain's total must equal validate.wf_oos.net.
Then the chain's daily $ series (x the run's multiplier, booked on the entry bar's date - NOISE is flat by the close)
gives the FOUR NUMBERS: ROC@30k (30 x net a year / worst DD), DD5 (house helper), DD% from the peak ($100k start,
house helper) and the daily Sortino. The lockbox: the crown re-run over the whole window, trades entering inside
validate.windows.lockbox, same numbers.

  python tools/noise_chain_read.py --run 490 [--twin]   one Firestore read of users/<uid>/runs/<n>, cached as run<n>.json
  extra for the TP job: --twin  prints the crown with tp off and the crown's tp neighbours on the WF and LB stretches
  --cost 0.7825  also prints the chain + lockbox at the owner's real cost (commission + 1 tick a side): the same
                 trades, each re-costed per contract (size x the cost difference) - never a re-run at another
                 cost_pts, which under-charges NOISE's tilted trades (the tilt folds (s-1) x 0.533 itself)
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak                    # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402

HERE = os.environ.get("NOISE_CHAIN_CACHE", r"C:\EdgeLog\_anatomy_cache\noise_tp_validate")   # run<n>.json cache
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TP_LEVELS = ["off", "1.0", "1.5", "2.0", "3.0"]


def fetch(n):
    p = os.path.join(HERE, "run%d.json" % n)
    if os.path.exists(p):
        return json.load(open(p))
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    d = firestore.client().collection("users").document(UID).collection("runs").document(str(n)).get().to_dict() or {}
    json.dump(d, open(p, "w"), default=str, indent=1)
    return d


def trades(strategy, arrays, params, cost):
    """the engine's trades, entry-sorted, each with its SIZE appended as the last field (1.0 for unsized files). A file
    that folds its size into the P&L (NOISE's tilt: pts = s*raw - (s-1)*size_cost_pts, engine cost once) must have
    folded the run's own cost, or no re-costing below is valid."""
    r = run_backtest(strategy, arrays=arrays, params=params, cost_pts=cost, return_trades=True) or {}
    T = r.get("trades") or []
    S = r.get("trade_sizes")
    S = [1.0] * len(T) if not (isinstance(S, (list, tuple)) and len(S) == len(T)) else S
    fc = r.get("size_cost_pts")
    if fc is not None and any(float(s) != 1.0 for s in S) and abs(float(fc) - cost) > 1e-9:
        raise SystemExit("file folds size cost %.4f but the run costs %.4f - read at the file's cost" % (float(fc), cost))
    return sorted([tuple(t) + (float(s),) for t, s in zip(T, S)], key=lambda t: int(t[0]))


def four(dates, pnl_usd, sess, years):
    daily = pd.Series(pnl_usd, index=dates).groupby(level=0).sum().reindex(sess, fill_value=0.0)
    x = daily.to_numpy()
    cum = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum)) if len(x) else 0.0
    d5 = dd5(daily)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    p = np.asarray(pnl_usd, float)
    w, l = p[p > 0], p[p < 0]
    return dict(roc=30 * (cum[-1] / years) / mdd if mdd > 0 else float("nan"), dd5=d5["dd5_usd"], one=d5["one_episode"],
                ddp=dd_pct_peak(daily), so=x.mean() / dn * np.sqrt(len(x) / years) if dn > 0 else float("nan"),
                n=len(p), net_yr=p.sum() / years, win=100 * len(w) / max(len(p), 1),
                wl=(w.mean() / -l.mean()) if len(w) and len(l) else float("nan"), mdd=mdd)


def line(lab, f):
    return ("  %-34s ROC@30k %6.2f | DD5 $%6.0f%s | DD%% %5.2f | Sortino %4.2f || trades %4d  win %4.1f%%  avg win/loss %.2fx"
            "  net $%.0f/yr  worst DD $%.0f" % (lab, f["roc"], f["dd5"], " (1 EPISODE)" if f["one"] else "", f["ddp"], f["so"],
                                                 f["n"], f["win"], f["wl"], f["net_yr"], f["mdd"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--twin", action="store_true")
    ap.add_argument("--cost", type=float, default=None,
                    help="also read the chain + lockbox at this cost (points a round trip); refused if any trade moves")
    a = ap.parse_args()
    d = fetch(a.run)
    v = d["validate"]
    strat = load_strategy(os.path.join(REPO, "augur_strategies", d["strategy"]))
    cost, mult = float(d["cost_pts"]), float(d.get("multiplier") or 20.0)
    win = v["windows"]
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    print("run #%d %s on %s (%s), cost %.3f, mult %.0f; optimize %s .. %s; lockbox %s .. %s; champion %s" % (
        a.run, d["strategy"], m.get("filename"), d["data_source"], cost, mult, win["optimize"][0], win["optimize"][1],
        win["lockbox"][0], win["lockbox"][1], v.get("champion")))
    A = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    pkeys = list((v.get("champion") or d.get("best_params") or {}).keys())
    rows = sorted([r for r in d.get("top10_results") or [] if "fold" in r], key=lambda r: int(r["fold"]))
    wf = v["wf_oos"]
    print("WF chain: %d folds (%s), stored net %.1f pts, %d trades, max DD %.1f pts, Sortino %.2f" % (
        len(rows), wf.get("mode"), wf["net"], wf["trades"], wf["max_drawdown"], wf["sortino"]))
    ch_d, ch_p, ok = [], [], True
    did = np.asarray(A["day_id"])
    warm = int(win.get("warm_days") or 0)

    def warm_start(a0):
        """auto.make_slice_evaluator's warm_start_bar: the first bar of the session `warm` sessions before bar a0."""
        if warm <= 0 or a0 <= 0:
            return a0
        target = int(did[a0]) - warm
        return 0 if target <= int(did[0]) else int(np.searchsorted(did, target, side="left"))

    def sliced(lo, hi):
        return {k: (x[lo:hi] if hasattr(x, "__len__") and not isinstance(x, (str, dict)) and len(x) == len(idx) else x)
                for k, x in A.items()}
    # BOARD 38: prefer the stored bound timestamps; with indices only, refuse when the data changed.
    from augur_engine.fold_anchor import fold_bounds_check, data_fp, BoundsDrift
    _run_fp = d.get("data_fp") if isinstance(d.get("data_fp"), dict) else None
    _today_fp = data_fp(A, m) if (_run_fp and _run_fp.get("date_from") == d["date_from"]
                                  and _run_fp.get("date_to") == win["optimize"][1]) else None
    _expect = (int(rows[-1]["train_bars"]) + int(rows[-1]["test_bars"])) if rows else None
    _pos = {t: i for i, t in enumerate(idx)}

    def _bounds(r):
        try:
            kind, (x0, x1) = fold_bounds_check(dict(r, test_start=int(r["train_bars"])),
                                               {"bars": _expect, **(_run_fp or {})} if _today_fp else {"bars": _expect},
                                               today_bars=len(idx), today_fp=_today_fp, run_label=a.run)
        except BoundsDrift as e:
            raise SystemExit(str(e))
        if kind == "ts":
            def at(x):
                t = pd.Timestamp(x)
                t = t.tz_convert("America/New_York").tz_localize(None) if t.tzinfo is not None else t
                if t not in _pos:
                    raise SystemExit("FOLD BOUNDS UNSAFE: run #%s fold bound %s is not in today's data; not re-reading" % (a.run, x))
                return _pos[t]
            return at(x0), at(x1) + 1
        return int(r["train_bars"]), int(r["train_bars"]) + int(r["test_bars"])

    def fold_trades(r, c):
        s0, s1 = _bounds(r)
        pp = {k: r[k] for k in pkeys}
        w = warm_start(s0)                                  # the validate scores each fold WARM, on the slice [w, s1)
        return s0, s1, pp, [(int(t[0]) + w,) + tuple(t[1:]) for t in trades(strat, sliced(w, s1), pp, c)
                            if int(t[0]) >= s0 - w]
    fold_tr = []
    for r in rows:
        s0, s1, pp, tr = fold_trades(r, cost)
        fold_tr.append(tr)
        net = sum(float(t[2]) for t in tr)
        good = abs(net - float(r["oos_pnl"])) < 1e-6 * max(1.0, abs(net)) + 1e-6 and len(tr) == int(r["oos_trades"])
        ok &= good
        print("  fold %d %s  bars %d..%d  %d trades / %.2f pts  (stored %d / %.2f)  %s" % (
            int(r["fold"]), pp, s0, s1, len(tr), net, int(r["oos_trades"]), float(r["oos_pnl"]), "OK" if good else "MISMATCH"))
        ch_d += [idx[int(t[0]) - 1].normalize() for t in tr]
        ch_p += [float(t[2]) * mult for t in tr]
    tot = sum(ch_p) / mult
    ok &= abs(tot - float(wf["net"])) < 0.1 and len(ch_p) == int(wf["trades"])
    print("PARITY %s: chain %.1f pts / %d trades vs stored %.1f / %d" % ("PASS" if ok else "FAIL", tot, len(ch_p), wf["net"],
                                                                          wf["trades"]))
    if not ok:
        raise SystemExit("chain parity failed - no four numbers printed")
    sess = pd.Index(sorted({x.normalize() for x in idx if pd.Timestamp(wf["from"]) <= x.normalize() <= pd.Timestamp(wf["to"])}))
    print("\nFOUR NUMBERS (daily, $ at mult %.0f; DD%% on $100k)" % mult)
    print(line("WF chain %s .. %s (%.2f yrs)" % (wf["from"], wf["to"], float(wf["years"])), four(ch_d, ch_p, sess, float(wf["years"]))))
    B = load_master_arrays(m, date_from=d["date_from"], date_to=win["lockbox"][1])
    bi = pd.DatetimeIndex(B["index"])
    bi = bi.tz_convert("America/New_York").tz_localize(None) if bi.tz is not None else bi
    lb0, lb1 = pd.Timestamp(win["lockbox"][0]), pd.Timestamp(win["lockbox"][1])
    lsess = pd.Index(sorted({x.normalize() for x in bi if lb0 <= x.normalize() <= lb1}))
    ly = (lb1 - lb0).days / 365.25
    champ = dict(v.get("champion") or d["best_params"])

    def stretch(params, lo, hi, sessions, yrs, c=cost, keep=None):
        tr = [t for t in trades(strat, B, params, c) if lo <= bi[int(t[0]) - 1].normalize() <= hi]
        if keep is not None:
            keep.extend(tr)
        return four([bi[int(t[0]) - 1].normalize() for t in tr], [float(t[2]) * mult for t in tr], sessions, yrs)
    lb_tr = []
    lbc = stretch(champ, lb0, lb1, lsess, ly, keep=lb_tr)
    print(line("LB crown %s" % champ, lbc))
    print("  (stored lockbox: %d trades, %.1f pts)" % (v["lockbox"]["trades"], v["lockbox"]["pnl"]))
    if a.cost is not None:
        # the SAME trades (the parity-checked chain and the lockbox read above) re-costed per contract: a size-s trade
        # pays s x the cost. NOT a re-run at cost_pts=c - the engine charges cost once a trade and NOISE's tilt folds
        # (s-1) x its own 0.533, so a re-run under-charges every sized trade by (s-1) x (c - 0.533).
        dc = a.cost - cost
        print("\nAT COST %.4f (the run's own %.4f above; same trades, each re-costed size x %.4f)" % (a.cost, cost, dc))
        ft = [t for tr in fold_tr for t in tr]
        print("  sized trades: WF %d of %d, LB %d of %d" % (sum(t[-1] != 1.0 for t in ft), len(ft),
                                                          sum(t[-1] != 1.0 for t in lb_tr), len(lb_tr)))
        print(line("WF chain at %.4f" % a.cost, four(ch_d, [(float(t[2]) - t[-1] * dc) * mult for t in ft], sess,
                                                    float(wf["years"]))))
        print(line("LB crown at %.4f" % a.cost, four([bi[int(t[0]) - 1].normalize() for t in lb_tr],
                                                    [(float(t[2]) - t[-1] * dc) * mult for t in lb_tr], lsess, ly)))
    if a.twin and "tp" in champ:
        w0, w1 = pd.Timestamp(wf["from"]), pd.Timestamp(wf["to"])
        print("\nTARGET READ (the crown's gate cell, tp varied; WF = the crown re-read on the chain's dates - a hindsight row,"
              " paired; LB apart)")
        for tp in TP_LEVELS:
            p = dict(champ, tp=tp)
            print(line("WF tp %-4s%s" % (tp, " <- crown" if tp == str(champ["tp"]) else ""), stretch(p, w0, w1, sess, float(wf["years"]))))
            print(line("LB tp %-4s" % tp, stretch(p, lb0, lb1, lsess, ly)))


if __name__ == "__main__":
    main()

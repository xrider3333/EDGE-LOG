"""ORB item 171 — the ML gate as a SIZE TILT instead of a keep/skip CUT.

The gate currently deletes every trade whose model probability is under the cut-off. That is a
CUT, and ORB.md's loudest lesson is that cuts lose on this strategy (vol-regime, VIX, black-swan,
DD-throttle, entry-time, RVOL — all failed) while the same signal applied as a SIZE TILT wins
(risk-parity, time-of-day, long/short). The gate has never been tried as a tilt. This tests it.

PRE-REGISTERED (written before the run, nothing tuned afterwards):

  Config      the crowned ensemble champion — ORB_3_0_ENS, or1 / Both / stop 1.75 / vol 1.25 /
              atr 0.1 / be 1.0 / target 4.0 / trail 12, NQ 5m RTH, net of 0.533 pts.
  Probability the SAME causal walk the gate uses (gate_trades at threshold 0, so nothing is
              dropped and we just read the score). Trained only on trades that closed before
              each entry. Warm-up trades have no score and always get weight 1.0.
  Schemes     all a-priori, none fitted to the result:
                cut@50   w = 1 if p >= .50 else 0          (what the gate does today)
                tier     w = 2.0 / 1.0 / 0.5 for p >= .55 / .45-.55 / < .45
                         (the 2/1/0.5 shape is copied from sizing.py's time tiers; the .45/.55
                          break-points are the gate's own existing grid values)
                linear   w = clip(1 + 4*(p - .50), 0.25, 3.0)
  Capital     every scheme is capital-matched to the flat size-1 risk budget, and the matching
              constant k is computed on the PRE-LOCKBOX slice only, then applied unchanged to the
              lockbox — so no lockbox information leaks into the sizing.
  Cap         final size capped at 3 contracts (the rp-cap3 doctrine, ORB.md §4.7).
  BAR         adopt only if a tilt beats the flat baseline on MAR in BOTH windows (the standard
              ORB.md applies to every add-on) AND beats cut@50 on the lockbox.

Usage:  python tools/orb_gate_tilt.py
"""
import sys, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import gate_trades
from augur_engine.sizing import trade_features, mar

INST = (sys.argv[1] if len(sys.argv) > 1 else "NQ").upper()
MULT = {"NQ": 20.0, "ES": 50.0}.get(INST, 20.0)
FEE = 5.66 / MULT + 0.25
STRAT = "ORB_3_0_ENS.py"
# The NQ champion, applied to ES with NO re-fit - the same transfer test ORB.md uses everywhere
# else. If the tilt is a real structural effect it should survive the instrument change; if it is
# NQ-specific curve-fitting it should not.
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
           breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12, flat_eod=True)
MODELS = ("logistic", "rf", "xgb", "tree", "et")
CAP = 3.0
# Pinned to the run-report window so these numbers sit beside #194/#195 without a window slide.
DFROM, DTO = "2010-06-07", "2026-06-30"
LB_FROM = "2025-06-30"


def _w_cut(p):
    return np.where(np.isnan(p), 1.0, (p >= 0.50).astype(float))


def _w_tier(p):
    w = np.where(p >= 0.55, 2.0, np.where(p >= 0.45, 1.0, 0.5))
    return np.where(np.isnan(p), 1.0, w)


def _w_linear(p):
    return np.where(np.isnan(p), 1.0, np.clip(1.0 + 4.0 * (p - 0.50), 0.25, 3.0))


SCHEMES = (("cut@50", _w_cut), ("tier", _w_tier), ("linear", _w_linear))


def _metrics(pnl_pts, size):
    """Net dollar metrics for one slice at the given per-trade contract sizes."""
    net = size * (pnl_pts - FEE) * MULT
    if not len(net):
        return None
    cum = np.cumsum(net)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(net[net > 0].sum()); gl = float(-net[net < 0].sum())
    live = size > 1e-9
    return {"net": float(net.sum()), "n": int(live.sum()),
            "pf": (gw / gl) if gl > 1e-9 else float("inf"),
            "dd": dd, "mar": mar(net.sum(), dd),
            "avg_sz": float(size[live].mean()) if live.any() else 0.0,
            "max_sz": float(size.max())}


def main():
    m = find_master(INST, "5m", "rth")
    arrays = load_master_arrays(m, DFROM, DTO)
    res = run_backtest(STRAT, instrument=INST, timeframe="5m", session="rth",
                       params=CFG, cost_pts=0.0, date_from=DFROM, date_to=DTO,
                       return_trades=True)
    T = sorted(res["trades"], key=lambda t: int(t[0]))
    idx = np.asarray(arrays["index"])
    nb = len(idx)
    ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])
    pnl, risk, _ebar, _side = trade_features(T, arrays, CFG["stop_frac"], CFG["or_bars"])

    import pandas as pd
    lb_start = pd.Timestamp(LB_FROM)
    _tz = getattr(pd.Timestamp(idx[-1]), "tzinfo", None)   # the master index is tz-aware
    if _tz is not None and lb_start.tzinfo is None:
        lb_start = lb_start.tz_localize(_tz)
    pre = ts < lb_start
    lb = ~pre
    print(f"=== ORB item 171 — ML gate as a SIZE TILT ({INST} 5m RTH, {STRAT}) ===")
    print(f"window {DFROM} -> {DTO}  ·  master {m['filename']}")
    print(f"{len(T)} trades  ·  pre-lockbox {int(pre.sum())}  ·  lockbox {int(lb.sum())}  "
          f"(from {str(lb_start)[:10]})")

    # ── baseline: flat 1 contract, every trade ────────────────────────────────────────────
    flat = np.ones(len(T))
    base = {"pre": _metrics(pnl[pre], flat[pre]), "lb": _metrics(pnl[lb], flat[lb])}

    # ── score each model once (threshold 0 => nothing dropped, pure scoring walk) ──────────
    probs = {}
    for mdl in MODELS:
        g = gate_trades(arrays, [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T],
                        model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42)
        p = np.asarray(g.get("prob"), float) if g and g.get("prob") is not None else None
        if p is None or len(p) != len(T):
            print(f"  ! {mdl}: no usable scores, skipped")
            continue
        probs[mdl] = p
        print(f"  scored {mdl:<9} warm-up {int(np.isnan(p).sum()):>4}  "
              f"median p {np.nanmedian(p):.3f}")
    if len(probs) > 1:                       # free extra: the 5-model consensus score
        probs["avg5"] = np.nanmean(np.vstack([probs[k] for k in MODELS if k in probs]), axis=0)

    hdr = (f"\n{'model':<9}{'scheme':<9}"
           f"{'PRE net $':>12}{'MAR':>7}{'DD $':>11}{'n':>6}   "
           f"{'LB net $':>11}{'MAR':>7}{'DD $':>10}{'n':>5}{'maxSz':>7}")
    print(hdr); print("-" * len(hdr))
    b = base
    print(f"{'—':<9}{'flat 1':<9}"
          f"{b['pre']['net']:>12,.0f}{b['pre']['mar']:>7.1f}{b['pre']['dd']:>11,.0f}{b['pre']['n']:>6}   "
          f"{b['lb']['net']:>11,.0f}{b['lb']['mar']:>7.1f}{b['lb']['dd']:>10,.0f}{b['lb']['n']:>5}{1.0:>7.1f}")

    rows = []
    for mdl, p in probs.items():
        for name, fn in SCHEMES:
            w = fn(p)
            denom = float((w[pre] * risk[pre]).sum())
            if denom <= 1e-12:
                continue
            k = float(risk[pre].sum()) / denom        # capital-match on PRE-LOCKBOX only
            size = np.minimum(w * k, CAP)
            r = {"model": mdl, "scheme": name,
                 "pre": _metrics(pnl[pre], size[pre]), "lb": _metrics(pnl[lb], size[lb])}
            rows.append(r)
            print(f"{mdl:<9}{name:<9}"
                  f"{r['pre']['net']:>12,.0f}{r['pre']['mar']:>7.1f}{r['pre']['dd']:>11,.0f}{r['pre']['n']:>6}   "
                  f"{r['lb']['net']:>11,.0f}{r['lb']['mar']:>7.1f}{r['lb']['dd']:>10,.0f}{r['lb']['n']:>5}"
                  f"{r['lb']['max_sz']:>7.1f}")

    # ── verdict against the pre-registered bar ────────────────────────────────────────────
    print("\n--- pre-registered bar: beat flat on MAR in BOTH windows, and beat cut@50 on lockbox ---")
    cut = {r["model"]: r for r in rows if r["scheme"] == "cut@50"}
    passed = []
    for r in rows:
        if r["scheme"] == "cut@50":
            continue
        c = cut.get(r["model"])
        ok = (r["pre"]["mar"] > base["pre"]["mar"] and r["lb"]["mar"] > base["lb"]["mar"]
              and c is not None and r["lb"]["mar"] > c["lb"]["mar"])
        if ok:
            passed.append(r)
        print(f"  {r['model']:<9}{r['scheme']:<9}"
              f"pre MAR {r['pre']['mar']:>6.1f} vs {base['pre']['mar']:.1f}  |  "
              f"LB MAR {r['lb']['mar']:>6.1f} vs flat {base['lb']['mar']:.1f} / "
              f"cut {c['lb']['mar'] if c else float('nan'):.1f}   "
              f"{'PASS' if ok else 'fail'}")
    print(f"\n{len(passed)} of {len(rows) - len(cut)} tilt variants clear the bar.")


if __name__ == "__main__":
    main()

"""enguq_timecap_bench.py -- bench driver for ENGUQ_1M_ETH_TCAP_1_0.py (campaign 2026-09-05).

PRE-REGISTERED BARS (written before running; all five must pass for PROMISING):
  1. EV R >= 0.434 (the #309 crown, continuous-lockbox measured)
  2. top-10 share < 55% (strictly better than the crown's 58%)
  3. still profitable excluding the top ten trades
  4. >= 90 held-out trades (entries >= 2025-06-30; the crown has 99)
  5. R/YR >= 43.4 (the crown)
PRIMARY (declared before running) = max_hold_bars 6900 (one week) on the #309 base.

PARITY (mandatory):
  A. max_hold_bars=0, #309 params, NQ 1m ETH db_noadj_eth 2010-06-07..2026-06-30,
     cost 0.533 x $20  ->  n=1604, net $591,267, PF 1.655 (#309 crown numbers)
  B. DEFAULT_PARAMS (er_th 0.0, max_hold_bars 0) on the same window
     ->  n=2843, net $434,721.12 (#226 frozen control)

BENCH (<=14 engine runs): on the #309 base, max_hold_bars in
  {0, 1380, 2760, 6900, 13800, 20000}; then the best two caps repeated with
  trail_frac 4.0 (the setting that normally produces the tail artifact).
"""
from __future__ import annotations
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _has_registry(root: pathlib.Path) -> bool:
    db = root / "optimizer_history.db"
    return db.exists() and db.stat().st_size > 0


_DATA_REPO = REPO if _has_registry(REPO) else pathlib.Path(
    r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, str(_DATA_REPO))
# NOTE: augur_engine.paths derives STRAT_DIR/DB_PATH from wherever the augur_engine
# package itself lives (its __file__), not from sys.path order alone -- so the plugin
# under test must physically exist in _DATA_REPO/augur_strategies for load_strategy()
# to find it. This driver's caller is responsible for staging the file there before
# running (see the campaign's materialize step); do NOT also insert the worktree path
# here, that would shadow augur_engine with a copy that lacks the data (optimizer_
# history.db / augur_uploads are gitignored and only live in the shared checkout).

import numpy as np                                              # noqa: E402
import pandas as pd                                             # noqa: E402
from augur_engine.engine import run_backtest                    # noqa: E402
from augur_engine.data import find_master, load_master_arrays   # noqa: E402

PLUGIN = "ENGUQ_1M_ETH_TCAP_1_0.py"
WIN = ("2010-06-07", "2026-06-30")
SPLIT = "2025-06-30"
COST, MULT = 0.533, 20.0

P309 = {
    "buf_atr": 0.3, "tl_len": 206, "trail_frac": 2.5, "limit_atr": 0.55, "atr_len": 52,
    "act_R": 1.5, "breakeven_R": 3.0, "ema_len": 220, "er_len": 100, "stop_mult": 1.3,
    "regime_len": 10, "min_brk": 1.6, "vol_mult": 1.1, "er_th": 0.0,
}

# CROWN reference (continuous_lb_check.py measured, ENGUQ.md section 1.0 / crown change)
CROWN = dict(evr=0.434, top10_share=58.0, lb_trades=99, ryr=43.4)


def _stats(pnls, years, mult=MULT):
    n = len(pnls)
    if not n:
        return dict(n=0, pf=None, wr=None, net=0.0, dd=0.0, mar=None, evr=None, ryr=None)
    a = np.asarray(pnls, dtype=float)
    gp = float(a[a > 0].sum())
    gl = float(-a[a < 0].sum())
    pf = (gp / gl) if gl > 0 else None
    wr = 100.0 * float((a > 0).sum()) / n
    net = float(a.sum()) * mult
    cum = np.cumsum(a)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) * mult
    evr = (1 - wr / 100.0) * (pf - 1) if pf is not None else None
    ryr = (evr * n / years) if (evr is not None and years) else None
    mar = ((net / years) / dd) if (years and dd > 0) else None
    return dict(n=n, pf=pf, wr=wr, net=net, dd=dd, mar=mar, evr=evr, ryr=ryr)


def _run(arr, idx, tz, params):
    r = run_backtest(PLUGIN, arrays=arr, params=dict(params), cost_pts=COST,
                      return_trades=True)
    trades = r.get("trades") or []
    rows = []
    for t in trades:
        ei, xi, pnl = int(t[0]), int(t[1]), float(t[2])
        rows.append((idx[ei], idx[min(xi, len(idx) - 1)], pnl))
    return r, rows


def bench_cell(label, arr, idx, tz, params):
    def _ts(s):
        t = pd.Timestamp(s)
        return t.tz_localize(tz) if (tz is not None and t.tz is None) else t

    r, rows = _run(arr, idx, tz, params)
    if not rows:
        print("%-40s NO TRADES" % label)
        return None
    ent = pd.DatetimeIndex([x[0] for x in rows])
    ext = pd.DatetimeIndex([x[1] for x in rows])
    pnl = [x[2] for x in rows]
    hold_days = [(b - a).days for a, b in zip(ent, ext)]

    split = _ts(SPLIT)
    y_all = max((_ts(WIN[1]) - _ts(WIN[0])).days, 1) / 365.25
    A = _stats(pnl, y_all)

    lb_m = ent >= split
    lb_pnl = [p for p, k in zip(pnl, lb_m) if k]
    y_lb = max((_ts(WIN[1]) - split).days, 1) / 365.25
    LB = _stats(lb_pnl, y_lb)

    # top-10 share of NET (whole run, matches continuous_lb_check convention on the
    # relevant stretch -- here the whole run since there is no separate selection
    # window declared for this cell-by-cell bench)
    sp = sorted(pnl)
    ex10 = sp[:-10] if len(sp) > 10 else sp
    A10 = _stats(ex10, y_all)
    share = (1 - A10["net"] / A["net"]) * 100.0 if A["net"] else None

    longest = int(max(hold_days)) if hold_days else 0

    print("=" * 118)
    print(label)
    print("  WHOLE RUN  n=%d PF=%.3f wr=%.1f net=$%.0f DD=$%.0f MAR=%s EV R=%.3f R/YR=%.1f"
          % (A["n"], A["pf"] or 0, A["wr"] or 0, A["net"], A["dd"],
             ("%.2f" % A["mar"]) if A["mar"] else "-", A["evr"] or 0, A["ryr"] or 0))
    print("  HELD-OUT   n=%d PF=%s net=$%.0f EV R=%s R/YR=%s"
          % (LB["n"], ("%.3f" % LB["pf"]) if LB["pf"] else "-", LB["net"],
             ("%.3f" % LB["evr"]) if LB["evr"] else "-",
             ("%.1f" % LB["ryr"]) if LB["ryr"] else "-"))
    print("  ex-top-10: net=$%.0f (whole run)  ->  top-10 share=%s   longest hold=%d days"
          % (A10["net"], ("%.0f%%" % share) if share is not None else "-", longest))

    return dict(label=label, params=dict(params), whole=A, held_out=LB, ex_top10=A10,
                top10_share=share, longest_hold_days=longest)


def check_bars(cell):
    """Pre-registered bars vs the #309 crown (CROWN dict)."""
    if cell is None:
        return False, ["NO TRADES"]
    fails = []
    evr = cell["whole"]["evr"] or 0
    ryr = cell["whole"]["ryr"] or 0
    share = cell["top10_share"]
    lb_n = cell["held_out"]["n"]
    ex10_net = cell["ex_top10"]["net"]
    if evr < CROWN["evr"]:
        fails.append("EV R %.3f < %.3f" % (evr, CROWN["evr"]))
    if share is None or share >= 55.0:
        fails.append("top-10 share %s >= 55%%" % (("%.0f%%" % share) if share is not None else "-"))
    if ex10_net <= 0:
        fails.append("ex-top-10 net $%.0f <= 0" % ex10_net)
    if lb_n < 90:
        fails.append("held-out trades %d < 90" % lb_n)
    if ryr < CROWN["ryr"]:
        fails.append("R/YR %.1f < %.1f" % (ryr, CROWN["ryr"]))
    return (len(fails) == 0), fails


def main():
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if not m:
        raise SystemExit("no NQ 1m ETH master")
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(arr["index"])
    tz = idx.tz

    out = {"parity": {}, "grid": [], "primary": None}

    # ---- PARITY A: max_hold_bars=0, #309 params ----
    r, rows = _run(arr, idx, tz, dict(P309, max_hold_bars=0))
    n_a, net_a, pf_a = r.get("num_trades"), r.get("total_pnl", 0) * MULT, r.get("profit_factor")
    print("PARITY A (max_hold_bars=0, #309 params): n=%d net=$%.0f PF=%s"
          % (n_a, net_a, pf_a))
    ok_a = (n_a == 1604 and abs(net_a - 591267) < 1500 and pf_a is not None and abs(pf_a - 1.655) < 0.01)
    print("PARITY A -> %s  (want n=1604 net=$591,267 PF=1.655)" % ("PASS" if ok_a else "FAIL"))
    out["parity"]["A"] = dict(n=n_a, net=net_a, pf=pf_a, ok=ok_a)

    # ---- PARITY B: DEFAULT_PARAMS (er_th 0, max_hold_bars 0) ----
    r2, rows2 = _run(arr, idx, tz, {})
    n_b, net_b, pf_b = r2.get("num_trades"), r2.get("total_pnl", 0) * MULT, r2.get("profit_factor")
    print("PARITY B (DEFAULT_PARAMS, #226 anchor): n=%d net=$%.2f PF=%s"
          % (n_b, net_b, pf_b))
    ok_b = (n_b == 2843 and abs(net_b - 434721.12) < 1.0)
    print("PARITY B -> %s  (want n=2843 net=$434,721.12)" % ("PASS" if ok_b else "FAIL"))
    out["parity"]["B"] = dict(n=n_b, net=net_b, pf=pf_b, ok=ok_b)

    if not (ok_a and ok_b):
        print("\n*** PARITY FAILED -- stopping before spending bench runs. ***")
        d = REPO / "tools"
        (d / "_enguq_timecap.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        return

    # ---- BENCH grid on #309 base ----
    caps = [0, 1380, 2760, 6900, 13800, 20000]
    cells = {}
    for cap in caps:
        params = dict(P309, max_hold_bars=cap)
        cell = bench_cell("#309 base, max_hold_bars=%d" % cap, arr, idx, tz, params)
        cells[cap] = cell
        out["grid"].append(cell)

    # rank caps (excluding 0, the OFF/parity cell) by EV R to pick "best two" for the
    # trail_frac 4.0 follow-up
    scored = [(cap, (c["whole"]["evr"] or -1)) for cap, c in cells.items() if cap != 0 and c]
    scored.sort(key=lambda x: -x[1])
    best_two = [cap for cap, _ in scored[:2]]
    print("\nBest two caps by whole-run EV R (excl. 0/off): %s" % best_two)

    for cap in best_two:
        params = dict(P309, max_hold_bars=cap, trail_frac=4.0)
        cell = bench_cell("trail_frac=4.0 + max_hold_bars=%d" % cap, arr, idx, tz, params)
        out["grid"].append(cell)

    # ---- PRIMARY verdict: max_hold_bars=6900 on the #309 base ----
    primary_cell = cells.get(6900)
    ok, fails = check_bars(primary_cell)
    print("\n" + "=" * 118)
    print("PRIMARY (max_hold_bars=6900, #309 base) -> %s" % ("PROMISING" if ok else "DEAD"))
    if not ok:
        for f in fails:
            print("  FAIL: %s" % f)
    out["primary"] = dict(cap=6900, ok=ok, fails=fails, cell=primary_cell)

    # ---- also report every OTHER cell against the same bars, honestly ----
    print("\nAll cells vs the five bars:")
    for cell in out["grid"]:
        if cell is None:
            continue
        c_ok, c_fails = check_bars(cell)
        print("  %-42s %s%s" % (cell["label"], "PASS" if c_ok else "FAIL",
                                 ("" if c_ok else "  (" + "; ".join(c_fails) + ")")))

    d = REPO / "tools"
    (d / "_enguq_timecap.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("\nwrote", d / "_enguq_timecap.json")


if __name__ == "__main__":
    main()

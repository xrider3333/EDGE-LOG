"""BOOK ERW-SWAP bench — does the highest per-trade-edge leg (ENGU-Q ETH ERW) help the
leading BOOK (run #261, R/YR 113.3) if pooled into it, or bolted on as a 4th leg?

WHY: R/YR = EV R x trades/yr is the cross-strategy rank read. Books win on trade count
(#261: R/YR 113.3, EV R 0.214, 8,494 pre-lockbox trades / 16.1y, PF 1.3427, WR 37.46%,
PASS with 554 lockbox trades). The 2026-09-04 campaign found the highest EV R of any
single-strategy config in project history: ENGU-Q ETH "efficiency floor x wide exits"
(ENGUQ_1M_ETH_ERW_1_0.py) at trail_frac 4.0 / act_R 3.0 / er_th 0.25 -> EV R 1.10 (672
trades/16y, PF 2.33, R/YR 46, 4/4 eras) and a tamer sibling at trail_frac 5.0 -> EV R
0.82 (832 trades, PF 2.02, R/YR 42). QUESTION: does adding this leg to #261's book raise
the book's EV R without losing enough trades to drop R/YR below #261's?

ANCHOR (run #261, book job legs, pinned window 2010-06-07 -> 2026-06-30, lockbox 12mo):
  ORB_3_6_C2.py      NQ 5m RTH db_noadj_rth  cost 0.533  mult 20  weight 1  (defaults)
  ENGUQ_1M_1_0.py    NQ 1m RTH db_noadj_rth  cost 0.533  mult 20  weight 1  (NQ_DEPLOY_PARAMS_149)
  NOISE_1_1_SBS_V90.py NQ 5m RTH db_noadj_rth cost 0.533 mult 20  weight 1  (defaults)
Certified: pre-lockbox 8,494 trades, net $984,200.31, PF 1.3427, WR 37.46%, DD $56,090.
Lockbox (12mo, from 2025-06-30): 554 trades, PF 1.5138, net $261,793.65, pass=True.

ERW leg spec (all variants): ENGUQ_1M_ETH_ERW_1_0.py, NQ 1m ETH db_noadj_eth,
cost 0.533, mult 20, weight 1. er_th=0.25 always (the efficiency floor). V1 trail_frac
5.0 / act_R 3.0. V2 & V3 trail_frac 4.0 / act_R 3.0. All other params at file defaults.

PRE-REGISTERED BARS (all must pass on THIS #261 window, pooled, no leg selection):
  1. pooled R/YR > 113.3           (#261's R/YR)
  2. pooled EV R > 0.214           (#261's EV R)
  3. pooled PF > 1.3427            (#261's pre-lockbox PF)
  4. >= 400 held-out (lockbox) trades
  5. held-out pooled PF > 1.2
PRIMARY cell (declared before running): V1 (add ERW trail5/act3 as a 4th leg to #261
unchanged) — additive, least likely to break the pooling; V2/V3 reported for shape.
If a variant passes all five, queue ONE BOOK job for it, pinned to #261's exact window/
costs, preset "BOOK: leader plus the ENGU-Q high-EV-R leg". If none passes, DEAD.

Run:  python tools/book_erw_swap_bench.py
"""
import sys
import json
import pathlib
import importlib.util

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from augur_engine import run_book  # noqa: E402

COST = 0.533
MULT = 20
DATE_FROM = "2010-06-07"
DATE_TO = "2026-06-30"
LOCKBOX_MONTHS = 12

REF_261 = {"trades": 8494, "net": 984200.31, "pf": 1.3427, "wr": 37.46, "dd": 56090.18,
           "lb_trades": 554, "lb_pf": 1.5138}
YEARS = 5867 / 365.25  # days_in_test from run #261 doc


def _defaults(fn):
    sp = importlib.util.spec_from_file_location("m", REPO / "augur_strategies" / fn)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


ENG149 = {"tl_len": 48, "ema_len": 390, "regime_len": 0, "buf_atr": 0.9, "min_brk": 1.3,
          "atr_len": 30, "vol_mult": 0.8, "stop_mult": 1.0, "act_R": 2.5,
          "trail_frac": 2.5, "breakeven_R": 1.5}

ORB_C2 = {"strategy": "ORB_3_6_C2.py", "params": _defaults("ORB_3_6_C2.py"),
          "instrument": "NQ", "timeframe": "5m", "session": "rth",
          "source": "db_noadj_rth", "cost_pts": COST, "mult": MULT, "weight": 1}
ENGQ = {"strategy": "ENGUQ_1M_1_0.py", "params": ENG149,
        "instrument": "NQ", "timeframe": "1m", "session": "rth",
        "source": "db_noadj_rth", "cost_pts": COST, "mult": MULT, "weight": 1}
NOISE_V90 = {"strategy": "NOISE_1_1_SBS_V90.py", "params": _defaults("NOISE_1_1_SBS_V90.py"),
             "instrument": "NQ", "timeframe": "5m", "session": "rth",
             "source": "db_noadj_rth", "cost_pts": COST, "mult": MULT, "weight": 1}

LEGS_261 = [ORB_C2, ENGQ, NOISE_V90]


def erw_leg(trail_frac, act_R, er_th=0.25):
    p = _defaults("ENGUQ_1M_ETH_ERW_1_0.py")
    p["trail_frac"] = trail_frac
    p["act_R"] = act_R
    p["er_th"] = er_th
    return {"strategy": "ENGUQ_1M_ETH_ERW_1_0.py", "params": p,
            "instrument": "NQ", "timeframe": "1m", "session": "eth",
            "source": "db_noadj_eth", "cost_pts": COST, "mult": MULT, "weight": 1}


ERW_T5 = erw_leg(5.0, 3.0)
ERW_T4 = erw_leg(4.0, 3.0)

VARIANTS = {
    "V1 (+ERW t5/a3, 4-leg)": LEGS_261 + [ERW_T5],
    "V2 (+ERW t4/a3, 4-leg)": LEGS_261 + [ERW_T4],
    "V3 (ORB+ORB_ENGQ replaced by ERW t4/a3, 3-leg)": [ORB_C2, NOISE_V90, ERW_T4],
}


def ev_r(pf, wr_pct):
    wr = wr_pct / 100.0
    if pf is None:
        return None
    return (1 - wr) * (pf - 1)


def r_per_yr(evr, n, years):
    if evr is None:
        return None
    return evr * (n / years)


def run_and_report(name, legs, expect_ref=None):
    r = run_book(legs, date_from=DATE_FROM, date_to=DATE_TO,
                 lockbox_months=LOCKBOX_MONTHS, slices=8, progress_cb=lambda d, t: None)
    b = r["book"]
    pre = b["pre_lockbox"]
    lb = b["lockbox"]
    evr = ev_r(pre["profit_factor"], pre["win_rate"])
    ryr = r_per_yr(evr, pre["num_trades"], YEARS)
    lb_evr = ev_r(lb["profit_factor"], lb["win_rate"]) if lb else None
    print(f"\n=== {name} ===")
    for l in b["legs"]:
        print(f"  leg {l['strategy']:<28} {l['instrument']} {l['timeframe']} {l['session']:<4}"
              f" {l['trades']:>5} trades  net ${l['net']:>12,.0f}")
    print(f"  pooled pre-lockbox: n={pre['num_trades']}  net=${pre['total_pnl']:,.0f}  "
          f"PF={pre['profit_factor']}  WR={pre['win_rate']}%  DD=${pre['max_drawdown']:,.0f}")
    print(f"  EV R = {evr:.4f}   R/YR = {ryr:.2f}")
    if lb:
        print(f"  lockbox (held-out): n={lb['num_trades']}  PF={lb['profit_factor']}  "
              f"WR={lb['win_rate']}%  net=${lb['total_pnl']:,.0f}  EV R={lb_evr}")
    if expect_ref:
        dn = abs(pre["total_pnl"] - expect_ref["net"]) / expect_ref["net"]
        dt = abs(pre["num_trades"] - expect_ref["trades"]) / expect_ref["trades"]
        ok = dn < 0.02 and dt < 0.02
        print(f"  PARITY vs #261: net off {dn*100:.2f}%, trades off {dt*100:.2f}% "
              f"-> {'PASS' if ok else 'FAIL'}")
        return r, ok
    return r, None


def main():
    out = {}

    print("STEP 2 — reproduce #261 (anchor)")
    r261, parity_ok = run_and_report("#261 anchor (reproduced)", LEGS_261, expect_ref=REF_261)
    out["anchor"] = r261["book"]
    if not parity_ok:
        print("\n*** PARITY FAILED — stopping before variants (per brief). ***")
        json.dump(out, open(REPO / "tools" / "_book_erw_swap.json", "w"), indent=2, default=str)
        return 1

    anchor_pre = r261["book"]["pre_lockbox"]
    anchor_evr = ev_r(anchor_pre["profit_factor"], anchor_pre["win_rate"])
    anchor_ryr = r_per_yr(anchor_evr, anchor_pre["num_trades"], YEARS)
    print(f"\nAnchor EV R = {anchor_evr:.4f}  R/YR = {anchor_ryr:.2f}  "
          f"(brief states EV R 0.214 / R/YR 113.3 — compare)")

    print("\nSTEP 3 — variants")
    results = {}
    for name, legs in VARIANTS.items():
        r, _ = run_and_report(name, legs)
        results[name] = r["book"]
        out[name] = r["book"]

    print("\n=== VERDICT (bars: R/YR>113.3, EV R>0.214, PF>1.3427, LB n>=400, LB PF>1.2) ===")
    primary = "V1 (+ERW t5/a3, 4-leg)"
    any_pass = False
    for name, b in results.items():
        pre = b["pre_lockbox"]
        lb = b["lockbox"]
        evr = ev_r(pre["profit_factor"], pre["win_rate"])
        ryr = r_per_yr(evr, pre["num_trades"], YEARS)
        lb_pf = lb["profit_factor"] if lb else None
        lb_n = lb["num_trades"] if lb else 0
        bars = [ryr > 113.3, evr > 0.214, pre["profit_factor"] > 1.3427,
                lb_n >= 400, (lb_pf or 0) > 1.2]
        verdict = "PROMISING" if all(bars) else "DEAD"
        tag = " <- PRIMARY" if name == primary else ""
        any_pass = any_pass or all(bars)
        print(f"  {name}{tag}: R/YR={ryr:.2f} EV R={evr:.4f} PF={pre['profit_factor']} "
              f"LB n={lb_n} LB PF={lb_pf} bars={bars} -> {verdict}")

    out["_verdict_bars"] = {"ryr_gt": 113.3, "evr_gt": 0.214, "pf_gt": 1.3427,
                             "lb_n_gte": 400, "lb_pf_gt": 1.2}
    out["_any_pass"] = any_pass
    json.dump(out, open(REPO / "tools" / "_book_erw_swap.json", "w"), indent=2, default=str)
    print(f"\nwritten tools/_book_erw_swap.json  any_pass={any_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

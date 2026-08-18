"""
LOCAL research battery G — RISK-CAP variant sweep for ENGUQ_1M_RC_1_0.py.

Diagnosis (2026-08-17): ENGU-Q's initial risk = (entry_px - swing_low over tl_len)
x stop_mult, uncapped. On extreme days this explodes (run #223 champion: 2025-04-07
entry, 1,251.6-pt swing low -> trail 5,006 pts below the running high -> mathematically
unreachable -> 465-day hold blocking all further entries in the sample's final year).
Same signature in #198 and #232 (353-day hold = 25% of its profit).

This script:
  1. PARITY check: risk_cap_atr=0.0 must reproduce the certified #149+BE1.5 baseline
     exactly (n=2054, net $453,531.86) on NQ 1m rth db_noadj_rth, date_to=2026-07-16.
  2. Sweeps risk_cap_atr in {1.5, 2.0, 3.0, 4.0, 6.0} on two configs (BASELINE champion
     params, and the high-drawdown ALT config) over the full window, with the lockbox
     (LB) sliced by ENTRY date >= 2025-07-16.
  3. For every cell reports: n, net, PF, maxDD, net/DD, LB n, LB net, LB net/DD,
     longest hold (days), top-10-trade share of net, and 2022 net.
  4. Applies the PRE-REGISTERED pass/fail bars from the prompt.

Run:  python3.13.exe tools/enguq_riskcap_sweep.py
Outputs: <scratchpad>/enguq_riskcap.pkl / .json / .md  (path printed at the end;
override with ENGUQ_RC_OUT_DIR env var).
"""
import json
import os
import pickle
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_strategies import ENGUQ_1M_RC_1_0 as RC  # noqa: E402

MULT, COST_PTS = 20.0, 0.533
DATE_TO = "2026-07-16"
LB_ENTRY_FROM = date(2025, 7, 16)

BASELINE_PARAMS = dict(buf_atr=0.9, ema_len=390, tl_len=48, stop_mult=1.0,
                       trail_frac=2.5, min_brk=1.3, vol_mult=0.8, atr_len=30,
                       act_R=2.5, breakeven_R=1.5, regime_len=0)
ALT_PARAMS = dict(tl_len=72, vol_mult=0.7, stop_mult=1.9, act_R=2.5, trail_frac=4.0,
                  buf_atr=0.4, min_brk=1.6, ema_len=90, atr_len=18, regime_len=0,
                  breakeven_R=2.5)

CAP_GRID = [0.0, 1.5, 2.0, 3.0, 4.0, 6.0]

OUT_DIR = os.environ.get(
    "ENGUQ_RC_OUT_DIR",
    r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad",
)


def load_data():
    master = find_master("NQ", "1m", "rth", "db_noadj_rth")
    if master is None:
        raise SystemExit("find_master('NQ','1m','rth','db_noadj_rth') -> None; check masters registry")
    arr = load_master_arrays(master, date_from=None, date_to=DATE_TO)
    return arr


def run_one(arr, params, risk_cap_atr):
    p = dict(params)
    p["risk_cap_atr"] = risk_cap_atr
    out = RC.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"],
                          volumes=arr["volume"], day_id=arr["day_id"],
                          return_trades=True, **p)
    return out


def analyze(out, idx):
    """Compute the full metric set for one run's output dict (with trades)."""
    if out is None or not out.get("trades"):
        return None
    trades = out["trades"]  # (entry_idx, exit_idx, pnl_pts, side, entry_px)
    pnl_pts = np.array([t[2] for t in trades])
    net_pts = pnl_pts - COST_PTS
    net_dollars = net_pts * MULT
    cum = np.cumsum(net_dollars)
    running_max = np.maximum.accumulate(cum)
    dd = cum - running_max
    max_dd = float(dd.min())
    wins = net_dollars[net_dollars > 0]
    losses = net_dollars[net_dollars < 0]
    pf = float(wins.sum()) / max(abs(float(losses.sum())), 1e-9)
    net = float(net_dollars.sum())
    n = len(trades)

    entry_dates = [idx[t[0]].date() for t in trades]
    exit_dates = [idx[t[1]].date() for t in trades]
    hold_days = [(ed2 - ed1).days for ed1, ed2 in zip(entry_dates, exit_dates)]
    longest_hold = max(hold_days) if hold_days else 0

    top10_share = float(np.sort(net_dollars)[::-1][:10].sum()) / net if net else float("nan")

    y2022_net = float(net_dollars[[ed.year == 2022 for ed in entry_dates]].sum())

    lb_mask = np.array([ed >= LB_ENTRY_FROM for ed in entry_dates])
    lb_n = int(lb_mask.sum())
    lb_net = float(net_dollars[lb_mask].sum())
    lb_cum = np.cumsum(net_dollars[lb_mask]) if lb_n else np.array([0.0])
    lb_rmax = np.maximum.accumulate(lb_cum)
    lb_dd = float((lb_cum - lb_rmax).min()) if lb_n else 0.0
    lb_net_dd = lb_net / abs(lb_dd) if lb_dd != 0 else float("nan")

    return {
        "n": n, "net": round(net, 2), "pf": round(pf, 3), "max_dd": round(max_dd, 2),
        "net_dd": round(net / abs(max_dd), 3) if max_dd != 0 else float("nan"),
        "lb_n": lb_n, "lb_net": round(lb_net, 2), "lb_net_dd": round(lb_net_dd, 3),
        "longest_hold_days": int(longest_hold), "top10_share": round(top10_share, 4),
        "net_2022": round(y2022_net, 2),
    }


def main():
    arr = load_data()
    idx = arr["index"]
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    print(f"NQ 1m RTH db_noadj_rth  {idx[0].date()} -> {idx[-1].date()}  ({years:.1f}y)  date_to={DATE_TO}")

    results = {"parity": None, "sweep": {"baseline": {}, "alt": {}}}

    # ---- STEP 2: PARITY ----
    out0 = run_one(arr, BASELINE_PARAMS, 0.0)
    n0 = out0["num_trades"] if out0 else 0
    net0 = float((np.array([t[2] for t in out0["trades"]]) - COST_PTS).sum() * MULT) if out0 else 0.0
    exp_n, exp_net = 2054, 453531.86
    parity_pass = (n0 == exp_n) and (abs(net0 - exp_net) <= 1.0)
    results["parity"] = {"n": n0, "net": round(net0, 2), "expected_n": exp_n,
                         "expected_net": exp_net, "pass": bool(parity_pass)}
    print(f"\nPARITY (risk_cap_atr=0.0 vs certified #149+BE1.5): n={n0} (exp {exp_n})  "
         f"net=${net0:,.2f} (exp ${exp_net:,.2f})  ->  {'PASS' if parity_pass else 'FAIL'}")
    if not parity_pass:
        print("PARITY FAILED — stopping, not running the sweep.")
        _write_outputs(results)
        return 1

    # ---- STEP 3: SWEEP ----
    for label, params in (("baseline", BASELINE_PARAMS), ("alt", ALT_PARAMS)):
        print(f"\n=== {label.upper()} config sweep ===")
        for cap in CAP_GRID:
            out = run_one(arr, params, cap)
            m = analyze(out, idx)
            key = f"cap_{cap}"
            results["sweep"][label][key] = m
            if m is None:
                print(f"  risk_cap_atr={cap:<4}  NO TRADES")
                continue
            print(f"  risk_cap_atr={cap:<4}  n={m['n']:>5}  net=${m['net']:>12,.2f}  PF={m['pf']:.2f}  "
                 f"maxDD=${m['max_dd']:>12,.2f}  net/DD={m['net_dd']:.2f}  "
                 f"LB n={m['lb_n']:>3} net=${m['lb_net']:>10,.2f} net/DD={m['lb_net_dd']:.2f}  "
                 f"longestHold={m['longest_hold_days']}d  top10={m['top10_share']*100:.1f}%  "
                 f"2022=${m['net_2022']:>10,.2f}")

    # ---- STEP 4: PRE-REGISTERED BARS ----
    base0 = results["sweep"]["baseline"]["cap_0.0"]
    alt0 = results["sweep"]["alt"]["cap_0.0"]
    print("\n=== VERDICTS (pre-registered bars) ===")
    verdicts = {"baseline": {}, "alt": {}}
    any_win = False
    for cap in CAP_GRID:
        if cap == 0.0:
            continue
        b = results["sweep"]["baseline"][f"cap_{cap}"]
        if b is None:
            verdicts["baseline"][cap] = "NO TRADES"
        else:
            dd_improve = (b["max_dd"] - base0["max_dd"]) / abs(base0["max_dd"])  # negative = improved (less negative)
            # maxDD improves >=10% means abs(dd) shrinks by >=10%
            dd_ok = abs(b["max_dd"]) <= abs(base0["max_dd"]) * 0.90
            net_ok = b["net"] >= base0["net"] * 0.90
            hold_ok = b["longest_hold_days"] <= 120
            win = dd_ok and net_ok and hold_ok
            any_win = any_win or win
            verdicts["baseline"][cap] = (
               f"{'WIN' if win else 'fail'}  (ddOK={dd_ok} net>=90%OK={net_ok} hold<=120dOK={hold_ok}; "
               f"maxDD ${b['max_dd']:,.0f} vs base ${base0['max_dd']:,.0f}; net ${b['net']:,.0f} vs base ${base0['net']:,.0f}; "
               f"hold {b['longest_hold_days']}d)")
        a = results["sweep"]["alt"][f"cap_{cap}"]
        if a is None:
            verdicts["alt"][cap] = "NO TRADES"
        else:
            dd_ok = abs(a["max_dd"]) <= 80000
            lb_ok = a["lb_net"] >= 44333 and a["lb_n"] >= 40
            hold_ok = a["longest_hold_days"] <= 120
            win = dd_ok and lb_ok and hold_ok
            any_win = any_win or win
            verdicts["alt"][cap] = (
               f"{'WIN' if win else 'fail'}  (maxDD<=80k OK={dd_ok} (${a['max_dd']:,.0f}); "
               f"LBnet>=44333&LBn>=40 OK={lb_ok} (LBnet ${a['lb_net']:,.0f}, LBn {a['lb_n']}); "
               f"hold<=120dOK={hold_ok} ({a['longest_hold_days']}d))")
    results["verdicts"] = verdicts
    for label in ("baseline", "alt"):
        for cap, v in verdicts[label].items():
            print(f"  {label} cap={cap}: {v}")
    if not any_win:
        print("\nOVERALL: FAILED — no cell cleared its pre-registered bar.")
        results["overall"] = "FAILED"
    else:
        results["overall"] = "at least one cell WON"
        print("\nOVERALL: at least one cell cleared its bar (see WIN rows above).")

    _write_outputs(results)
    return 0


def _write_outputs(results):
    os.makedirs(OUT_DIR, exist_ok=True)
    pkl_path = os.path.join(OUT_DIR, "enguq_riskcap.pkl")
    json_path = os.path.join(OUT_DIR, "enguq_riskcap.json")
    md_path = os.path.join(OUT_DIR, "enguq_riskcap.md")
    with open(pkl_path, "wb") as f:
        pickle.dump(results, f)
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    with open(md_path, "w") as f:
        f.write(_render_md(results))
    print(f"\nWrote: {pkl_path}\n       {json_path}\n       {md_path}")


def _render_md(r):
    lines = ["# ENGUQ RISK-CAP research battery G\n"]
    p = r["parity"]
    lines.append(f"## Parity\nn={p['n']} (expected {p['expected_n']})  net=${p['net']:,.2f} "
                 f"(expected ${p['expected_net']:,.2f})  -> **{'PASS' if p['pass'] else 'FAIL'}**\n")
    for label in ("baseline", "alt"):
        lines.append(f"## {label.upper()} sweep\n")
        lines.append("| risk_cap_atr | n | net | PF | maxDD | net/DD | LB n | LB net | LB net/DD | longest hold (d) | top10 share | 2022 net |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for key, m in r["sweep"][label].items():
            cap = key.replace("cap_", "")
            if m is None:
                lines.append(f"| {cap} | NO TRADES | | | | | | | | | | |")
                continue
            lines.append(f"| {cap} | {m['n']} | ${m['net']:,.2f} | {m['pf']} | ${m['max_dd']:,.2f} | "
                         f"{m['net_dd']} | {m['lb_n']} | ${m['lb_net']:,.2f} | {m['lb_net_dd']} | "
                         f"{m['longest_hold_days']} | {m['top10_share']*100:.1f}% | ${m['net_2022']:,.2f} |")
        lines.append("")
    lines.append("## Verdicts (pre-registered bars)\n")
    for label in ("baseline", "alt"):
        for cap, v in r["verdicts"][label].items():
            lines.append(f"- {label} cap={cap}: {v}")
    lines.append(f"\n**Overall: {r['overall']}**\n")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

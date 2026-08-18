"""
LOCAL battery Q — HIGHER-TIMEFRAME STRUCTURAL TRAIL parity + sweep.

Runs the ENGUQ_1M_ETH_HTF_1_0 fork against NQ 1m ETH (db_noadj_eth):
 1. Parity gate: htf_trail=0 must reproduce the certified ENGUQ_1M_ETH_1_0 result
    (n=2843, net=$434,721.12 +/- $1) on the <=2026-06-30 slice.
 2. 3x3 sweep over htf_trail in {15,60,240} x htf_buf_atr in {0.25,0.5,1.0}, on
    the FULL history (no date_to cap) — matching how the certified config itself
    is evaluated for its full-history stats, with a separate LB (entry>=2025-06-30)
    slice computed from the same run's trade log.
 5. Diagnostic: average hold length + average exit-R, HTF-config vs baseline, and
    whether the HTF trail exits earlier/later on average.

Output: <scratch>/enguq_htftrail.pkl / .json / .md

Run:  python3.13.exe tools/enguq_htftrail_sweep.py
"""
import json
import os
import pickle
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_strategies import ENGUQ_1M_ETH_HTF_1_0 as HTF  # noqa: E402

SCRATCH = r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad"
os.makedirs(SCRATCH, exist_ok=True)

MULT, COST_PTS = 20.0, 0.533

CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)

PARITY_N = 2843
PARITY_NET = 434721.12

STUCK_MAX_HOLD_DAYS = 120
STUCK_MIN_LB_TRADES = 40
BAR_MIN_NET_DR = 9.50
BAR_MIN_LB_NET = 80_000.0
BAR_MIN_FULL_NET = 400_000.0
LB_ENTRY_FROM = pd.Timestamp("2025-06-30", tz="US/Eastern")


def run(arrays, params):
    return HTF.run_backtest(
        arrays["open"], arrays["high"], arrays["low"], arrays["close"],
        volumes=arrays.get("volume"), day_id=arrays.get("day_id"), index=arrays.get("index"),
        return_trades=True, **params)


def trades_to_df(res, index):
    """trade_log rows: (entry_idx, exit_idx, pnl_pts, side, entry_px, risk_pts)."""
    rows = res["trades"]
    df = pd.DataFrame(rows, columns=["entry_idx", "exit_idx", "pnl_pts", "side", "entry_px", "risk_pts"])
    df["entry_time"] = index[df["entry_idx"].values]
    df["exit_time"] = index[df["exit_idx"].values]
    df["hold_days"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 86400.0
    df["pnl_dollars"] = (df["pnl_pts"] - COST_PTS) * MULT
    df["exit_R"] = df["pnl_pts"] / df["risk_pts"].replace(0, np.nan)
    return df


def net_pf_dd(pnl_dollars):
    p = np.asarray(pnl_dollars, float)
    if len(p) == 0:
        return 0.0, float("nan"), 0.0
    wins = p[p > 0]; losses = p[p < 0]
    net = float(p.sum())
    pf = float(wins.sum()) / max(abs(float(losses.sum())), 1e-9)
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    return net, pf, dd


def by_year(df):
    out = {}
    for yr, g in df.groupby(df["exit_time"].dt.year):
        out[int(yr)] = round(float(g["pnl_dollars"].sum()), 2)
    return out


def top10_share(df):
    p = df["pnl_dollars"].values
    if len(p) == 0 or p.sum() == 0:
        return float("nan")
    top10 = np.sort(p)[::-1][:10].sum()
    return float(top10 / p.sum())


def summarize(df, label):
    net, pf, dd = net_pf_dd(df["pnl_dollars"].values)
    dr = net / abs(dd) if dd != 0 else float("nan")
    lb = df[df["entry_time"] >= LB_ENTRY_FROM]
    lb_net, lb_pf, _ = net_pf_dd(lb["pnl_dollars"].values)
    longest_hold = float(df["hold_days"].max()) if len(df) else 0.0
    median_hold = float(df["hold_days"].median()) if len(df) else 0.0
    avg_hold = float(df["hold_days"].mean()) if len(df) else 0.0
    avg_exit_R = float(df["exit_R"].mean()) if len(df) else float("nan")
    last_entry = str(df["entry_time"].max()) if len(df) else None
    return {
        "label": label,
        "n": int(len(df)),
        "net": round(net, 2),
        "pf": round(pf, 3) if pf == pf else None,
        "max_dd": round(dd, 2),
        "net_over_dd": round(dr, 3) if dr == dr else None,
        "by_year": by_year(df),
        "lb_n": int(len(lb)),
        "lb_net": round(lb_net, 2),
        "lb_pf": round(lb_pf, 3) if lb_pf == lb_pf else None,
        "longest_hold_days": round(longest_hold, 2),
        "median_hold_days": round(median_hold, 3),
        "avg_hold_days": round(avg_hold, 3),
        "avg_exit_R": round(avg_exit_R, 4) if avg_exit_R == avg_exit_R else None,
        "last_entry": last_entry,
        "top10_share": round(top10_share(df), 4) if top10_share(df) == top10_share(df) else None,
    }


def main():
    master = find_master("NQ", "1m", "eth", "db_noadj_eth")
    assert master is not None, "no master for NQ 1m eth db_noadj_eth"

    # ---- 1) PARITY GATE (sliced <=2026-06-30, htf_trail=0) ----
    arr_p = load_master_arrays(master, date_from=None, date_to="2026-06-30")
    res_p = run(arr_p, dict(CERT, htf_trail=0, htf_buf_atr=0.5))
    p_n = res_p["num_trades"] if res_p else 0
    p_pnl = np.array([t[2] for t in res_p["trades"]]) if res_p else np.array([])
    p_net = float((p_pnl - COST_PTS).sum()) * MULT if len(p_pnl) else 0.0
    parity_pass = (p_n == PARITY_N) and (abs(p_net - PARITY_NET) <= 1.0)
    print(f"PARITY  n={p_n} (want {PARITY_N})   net=${p_net:,.2f} (want ${PARITY_NET:,.2f})   "
          f"{'PASS' if parity_pass else 'FAIL'}")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parity": {"n": p_n, "net": round(p_net, 2), "want_n": PARITY_N, "want_net": PARITY_NET,
                   "pass": bool(parity_pass)},
    }
    if not parity_pass:
        print("PARITY GATE FAILED -- stopping, committing nothing.")
        with open(os.path.join(SCRATCH, "enguq_htftrail.json"), "w") as f:
            json.dump(result, f, indent=2, default=str)
        return 1

    # ---- 2) full-history data (no date_to cap) ----
    arr_full = load_master_arrays(master, date_from=None, date_to=None)
    idx_full = arr_full["index"]

    # baseline (htf_trail=0) on full history, for the diagnostic comparison
    res_base = run(arr_full, dict(CERT, htf_trail=0, htf_buf_atr=0.5))
    df_base = trades_to_df(res_base, idx_full)
    base_summary = summarize(df_base, "baseline (htf_trail=0, full history)")
    print(f"BASELINE  n={base_summary['n']}  net=${base_summary['net']:,.2f}  "
          f"PF={base_summary['pf']}  DD=${base_summary['max_dd']:,.2f}  "
          f"avg_hold={base_summary['avg_hold_days']:.3f}d  avg_exit_R={base_summary['avg_exit_R']}")

    cells = []
    htf_trails = [15, 60, 240]
    htf_bufs = [0.25, 0.50, 1.00]
    for ht in htf_trails:
        for hb in htf_bufs:
            params = dict(CERT, htf_trail=ht, htf_buf_atr=hb)
            res = run(arr_full, params)
            if res is None or not res.get("trades"):
                cell = {"htf_trail": ht, "htf_buf_atr": hb, "n": 0, "net": 0.0,
                        "disqualified": True, "disqual_reason": "no trades", "pass": False}
                cells.append(cell)
                print(f"htf_trail={ht:>3} buf={hb:.2f}  NO TRADES")
                continue
            df = trades_to_df(res, idx_full)
            summ = summarize(df, f"htf_trail={ht} htf_buf_atr={hb}")

            stuck_dq = []
            if summ["longest_hold_days"] > STUCK_MAX_HOLD_DAYS:
                stuck_dq.append(f"longest_hold {summ['longest_hold_days']:.1f}d > {STUCK_MAX_HOLD_DAYS}d")
            if summ["lb_n"] < STUCK_MIN_LB_TRADES:
                stuck_dq.append(f"lb_n {summ['lb_n']} < {STUCK_MIN_LB_TRADES}")
            disqualified = len(stuck_dq) > 0

            bar_pass = (not disqualified
                        and (summ["net_over_dd"] is not None and summ["net_over_dd"] >= BAR_MIN_NET_DR)
                        and summ["lb_net"] >= BAR_MIN_LB_NET
                        and summ["net"] >= BAR_MIN_FULL_NET)

            cell = dict(summ)
            cell.update({"htf_trail": ht, "htf_buf_atr": hb, "disqualified": disqualified,
                         "disqual_reasons": stuck_dq, "pass": bool(bar_pass)})
            cells.append(cell)
            print(f"htf_trail={ht:>3} buf={hb:.2f}  n={summ['n']:>5}  net=${summ['net']:>12,.2f}  "
                  f"PF={summ['pf']}  DD=${summ['max_dd']:>10,.2f}  net/DD={summ['net_over_dd']}  "
                  f"LB n={summ['lb_n']} net=${summ['lb_net']:,.2f}  "
                  f"longest_hold={summ['longest_hold_days']:.1f}d  "
                  f"{'DISQUALIFIED(' + ';'.join(stuck_dq) + ')' if disqualified else ('PASS' if bar_pass else 'fail-bar')}")

    result["baseline"] = base_summary
    result["cells"] = cells
    result["cert_params"] = CERT
    result["bar"] = {"net_over_dd_min": BAR_MIN_NET_DR, "lb_net_min": BAR_MIN_LB_NET,
                     "full_net_min": BAR_MIN_FULL_NET, "stuck_max_hold_days": STUCK_MAX_HOLD_DAYS,
                     "stuck_min_lb_trades": STUCK_MIN_LB_TRADES}

    any_pass = any(c.get("pass") for c in cells)
    result["any_cell_passes"] = bool(any_pass)
    print(f"\nANY CELL PASSES: {any_pass}")

    # ---- diagnostic: earlier/later exit, DD, net, hold, exit-R vs baseline ----
    scored_cells = [c for c in cells if c.get("n", 0) > 0]
    if scored_cells:
        mean_hold = float(np.mean([c["avg_hold_days"] for c in scored_cells]))
        exitRs = [c["avg_exit_R"] for c in scored_cells if c.get("avg_exit_R") is not None]
        mean_exit_R = float(np.mean(exitRs)) if exitRs else float("nan")
        mean_dd = float(np.mean([c["max_dd"] for c in scored_cells]))
        mean_net = float(np.mean([c["net"] for c in scored_cells]))
        base_hold = base_summary["avg_hold_days"]
        base_exit_R = base_summary["avg_exit_R"] or float("nan")
        base_dd = base_summary["max_dd"]
        base_net = base_summary["net"]
        direction = "LATER" if mean_hold > base_hold else ("EARLIER" if mean_hold < base_hold else "SAME")
        diag = {
            "baseline_avg_hold_days": base_hold, "sweep_avg_hold_days": round(mean_hold, 3),
            "hold_direction_vs_baseline": direction,
            "baseline_avg_exit_R": base_exit_R, "sweep_avg_exit_R": round(mean_exit_R, 4) if mean_exit_R == mean_exit_R else None,
            "baseline_max_dd": base_dd, "sweep_avg_max_dd": round(mean_dd, 2),
            "dd_direction_vs_baseline": "LOWER (cuts DD)" if mean_dd > base_dd else ("HIGHER" if mean_dd < base_dd else "SAME"),
            "baseline_net": base_net, "sweep_avg_net": round(mean_net, 2),
            "net_direction_vs_baseline": "HIGHER (raises net)" if mean_net > base_net else ("LOWER" if mean_net < base_net else "SAME"),
        }
        result["diagnostic"] = diag
        print(f"\nDIAGNOSTIC: sweep avg hold {mean_hold:.3f}d vs baseline {base_hold:.3f}d -> exits {direction}")
        print(f"            sweep avg exit-R {mean_exit_R:.4f} vs baseline {base_exit_R:.4f}"
              if mean_exit_R == mean_exit_R and base_exit_R == base_exit_R else "            exit-R: n/a")
        print(f"            sweep avg maxDD ${mean_dd:,.2f} vs baseline ${base_dd:,.2f} ({diag['dd_direction_vs_baseline']})")
        print(f"            sweep avg net ${mean_net:,.2f} vs baseline ${base_net:,.2f} ({diag['net_direction_vs_baseline']})")

    with open(os.path.join(SCRATCH, "enguq_htftrail.pkl"), "wb") as f:
        pickle.dump(result, f)
    with open(os.path.join(SCRATCH, "enguq_htftrail.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    lines = ["# ENGU-Q ETH HTF structural trail -- battery Q", "",
             f"Generated: {result['generated_at']}", "",
             f"## Parity gate: {'PASS' if parity_pass else 'FAIL'}",
             f"n={p_n} (want {PARITY_N}), net=${p_net:,.2f} (want ${PARITY_NET:,.2f})", "",
             f"## Baseline (htf_trail=0, full history, no date_to cap)",
             f"n={base_summary['n']}, net=${base_summary['net']:,.2f}, PF={base_summary['pf']}, "
             f"DD=${base_summary['max_dd']:,.2f}, net/DD={base_summary['net_over_dd']}, "
             f"avg_hold={base_summary['avg_hold_days']:.3f}d, LB n={base_summary['lb_n']} "
             f"net=${base_summary['lb_net']:,.2f}", "",
             "## Sweep (9 cells)", "",
             "| htf_trail | htf_buf_atr | n | net | PF | maxDD | net/DD | LB n | LB net | LB PF | "
             "longest_hold(d) | median_hold(d) | avg_hold(d) | last_entry | top10_share | disqualified | PASS |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in cells:
        lines.append(
            f"| {c['htf_trail']} | {c['htf_buf_atr']} | {c.get('n',0)} | "
            f"${c.get('net',0):,.2f} | {c.get('pf')} | ${c.get('max_dd',0):,.2f} | "
            f"{c.get('net_over_dd')} | {c.get('lb_n',0)} | ${c.get('lb_net',0):,.2f} | "
            f"{c.get('lb_pf')} | {c.get('longest_hold_days',0)} | {c.get('median_hold_days',0)} | "
            f"{c.get('avg_hold_days',0)} | {c.get('last_entry')} | {c.get('top10_share')} | "
            f"{';'.join(c.get('disqual_reasons',[])) or '-'} | {c.get('pass')} |")
    lines += ["", f"ANY CELL PASSES: {any_pass}"]
    if "diagnostic" in result:
        d = result["diagnostic"]
        lines += ["", "## Diagnostic: structural trail vs fixed-multiple baseline", "",
                  f"- Avg hold: sweep {d['sweep_avg_hold_days']}d vs baseline {d['baseline_avg_hold_days']}d "
                  f"-> exits **{d['hold_direction_vs_baseline']}** on average",
                  f"- Avg exit-R: sweep {d['sweep_avg_exit_R']} vs baseline {d['baseline_avg_exit_R']}",
                  f"- Avg maxDD: sweep ${d['sweep_avg_max_dd']:,.2f} vs baseline ${d['baseline_max_dd']:,.2f} "
                  f"({d['dd_direction_vs_baseline']})",
                  f"- Avg net: sweep ${d['sweep_avg_net']:,.2f} vs baseline ${d['baseline_net']:,.2f} "
                  f"({d['net_direction_vs_baseline']})"]
    with open(os.path.join(SCRATCH, "enguq_htftrail.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

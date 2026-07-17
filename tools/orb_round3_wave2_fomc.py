"""ORB round-3 wave-2 item X11 — FOMC decision-day overlay (ORB.md round 3).

Story (pre-registered BEFORE looking at the buckets): ORB entries fire in the morning;
on FOMC decision days the 14:00 ET statement nukes whatever position is still on, so
HALF-SIZE (0.5x) on FOMC decision days should cut DD more than PnL. 0.75x and 1.25x are
run only for the plateau read. Dates are the Fed's own scheduled-meeting decision days
(tools/data/fomc_dates.txt, scraped from federalreserve.gov — unscheduled/emergency
meetings and notation votes excluded).

Method: deploy config on FULL once with trades; slice the trade list by ET entry date
(valid — strategy is EOD-flat). Buckets: FOMC decision day / first session AFTER FOMC /
all other days. Tilts multiply size on FOMC-day trades (1.0 otherwise) — no trade is
deleted. Judge: tilt graduates only if MAR >= baseline in BOTH OPT and LB, AND it sits
on a plateau (neighbors pass too); a single knife-edge pass does not graduate.

Anchor (must reproduce, else the data path is wrong):
    deploy on FULL -> net ~$574,177, DD ~$26,763, 3951 trades.

Usage:  python tools/orb_round3_wave2_fomc.py
"""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import datetime as _dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest, find_master, load_master_arrays

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
LB_START = _dt.date(2025, 6, 30)          # OPT = entry date < this ; LB = entry date >= this
PARAMS = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
              atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
ANCHOR = dict(net=574_177.0, dd=26_763.0, n=3951)
DATES_FILE = os.path.join(ROOT, "tools", "data", "fomc_dates.txt")
TILTS = [0.5, 0.75, 1.25]                 # pre-registered: 0.5x; neighbors for plateau read


def load_fomc_dates(path):
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            out.append(_dt.date.fromisoformat(ln))
    return sorted(set(out))


def bar_dates_et(arr):
    """ET calendar date per bar. arr['index'] may be epoch seconds OR a tz-aware
    US/Eastern DatetimeIndex depending on loader path — normalize robustly."""
    idx = arr["index"]
    if isinstance(idx, pd.DatetimeIndex):
        dt = idx.tz_convert("US/Eastern") if idx.tz is not None else idx
    else:
        vals = np.asarray(idx)
        if np.issubdtype(vals.dtype, np.datetime64):
            dt = pd.DatetimeIndex(vals)          # already wall-clock datetimes
        else:
            dt = (pd.to_datetime(vals.astype(np.int64), unit="s", utc=True)
                    .tz_convert("US/Eastern"))
    return np.array([d.date() for d in dt])


def bucket_stats(pnls_usd):
    p = np.asarray(pnls_usd, dtype=float)
    if p.size == 0:
        return dict(n=0, net=0.0, avg=0.0, wr=0.0, pf=0.0)
    gw = p[p > 0].sum()
    gl = -p[p < 0].sum()
    return dict(n=int(p.size), net=float(p.sum()), avg=float(p.mean()),
                wr=100.0 * float((p > 0).mean()),
                pf=(gw / gl) if gl > 0 else float("inf"))


def win_kpi(pnls_usd):
    """net / max-DD / MAR from a FRESH cumsum inside the window."""
    p = np.asarray(pnls_usd, dtype=float)
    if p.size == 0:
        return dict(net=0.0, dd=0.0, mar=0.0, n=0)
    eq = np.concatenate([[0.0], np.cumsum(p)])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    return dict(net=net, dd=dd, mar=(net / dd if dd > 0 else 0.0), n=int(p.size))


def main():
    fomc = load_fomc_dates(DATES_FILE)
    print(f"FOMC decision days loaded: {len(fomc)}  ({fomc[0]} .. {fomc[-1]})  "
          f"[{DATES_FILE}]", flush=True)

    print("loading master + FULL window ...", flush=True)
    master = find_master(INST, TF, SESS)
    if master is None:
        print("no NQ 5m rth master found"); sys.exit(1)
    arr = load_master_arrays(master, date_from=FULL[0], date_to=FULL[1])

    r = run_backtest("ORB_3_0_BE.py", arrays=arr, params=PARAMS, cost_pts=FEE,
                     return_trades=True)
    trades = r.get("trades") or []
    net = r["total_pnl"] * MULT
    dd = abs(r.get("max_drawdown", 0) or 0) * MULT
    n = len(trades)

    # ── HARD ANCHOR ───────────────────────────────────────────────────────────
    print("\n=== ANCHOR (deploy on FULL) ===")
    ok = (abs(net - ANCHOR["net"]) <= 5.0 and abs(dd - ANCHOR["dd"]) <= 5.0
          and n == ANCHOR["n"])
    print(f"  net ${net:,.0f} (expect ${ANCHOR['net']:,.0f} +/-$5) | "
          f"DD ${dd:,.0f} (expect ${ANCHOR['dd']:,.0f} +/-$5) | "
          f"trades {n} (expect {ANCHOR['n']})")
    print(f"  ANCHOR {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  STOP: anchor failed — data path is wrong, aborting.")
        sys.exit(1)

    # ── bucket assignment by ET entry date ────────────────────────────────────
    dates = bar_dates_et(arr)
    sessions = np.array(sorted(set(dates)))              # trading days in the data
    fomc_set = set(fomc)
    # day AFTER = first SESSION strictly after each FOMC date (Wed decision -> Thu)
    after_set = set()
    for d in fomc:
        j = np.searchsorted(sessions, d, side="right")
        if j < len(sessions):
            after_set.add(sessions[j])
    after_set -= fomc_set                                # never double-count

    entry_dates = np.array([dates[t[0]] for t in trades])
    pnl_usd = np.array([t[2] * MULT for t in trades], dtype=float)
    in_fomc = np.array([d in fomc_set for d in entry_dates])
    in_after = np.array([d in after_set for d in entry_dates])
    in_other = ~(in_fomc | in_after)

    fomc_in_window = [d for d in fomc if sessions[0] <= d <= sessions[-1]]
    fomc_sessions = [d for d in fomc_in_window if d in set(sessions)]
    fomc_traded = sorted(set(entry_dates[in_fomc]))
    print(f"\nFOMC days inside the data window: {len(fomc_in_window)} "
          f"({len(fomc_sessions)} were trading sessions); "
          f"{len(fomc_traded)} of them actually had an ORB trade "
          f"({int(in_fomc.sum())} trades).")

    print("\n=== BUCKETS (FULL, deploy config) ===")
    hdr = f"  {'bucket':<16} {'n':>5} {'net$':>12} {'avg$':>9} {'WR%':>6} {'PF':>6}"
    print(hdr)
    for tag, mask in (("FOMC day", in_fomc), ("day after FOMC", in_after),
                      ("all other days", in_other)):
        s = bucket_stats(pnl_usd[mask])
        pf = f"{s['pf']:6.2f}" if np.isfinite(s["pf"]) else "   inf"
        print(f"  {tag:<16} {s['n']:>5} {s['net']:>12,.0f} {s['avg']:>9,.0f} "
              f"{s['wr']:>6.1f} {pf}")

    # ── tilt test: multiply size on FOMC-day trades (1.0 otherwise) ───────────
    opt_m = entry_dates < LB_START
    lb_m = ~opt_m

    def tilted(k):
        w = np.where(in_fomc, k, 1.0)
        return pnl_usd * w

    base_o = win_kpi(pnl_usd[opt_m]); base_l = win_kpi(pnl_usd[lb_m])
    print("\n=== TILT: size k on FOMC decision days (pre-registered k=0.5) ===")
    print(f"  {'k':>5} | {'OPT net$':>11} {'DD$':>9} {'MAR':>6} | "
          f"{'LB net$':>10} {'DD$':>8} {'MAR':>6} | pass")
    print(f"  {'1.00':>5} | {base_o['net']:>11,.0f} {base_o['dd']:>9,.0f} "
          f"{base_o['mar']:>6.2f} | {base_l['net']:>10,.0f} {base_l['dd']:>8,.0f} "
          f"{base_l['mar']:>6.2f} | (baseline)")
    results = {}
    for k in TILTS:
        p = tilted(k)
        o = win_kpi(p[opt_m]); l = win_kpi(p[lb_m])
        ok_o = o["mar"] >= base_o["mar"] - 1e-9
        ok_l = l["mar"] >= base_l["mar"] - 1e-9
        results[k] = (o, l, ok_o and ok_l)
        print(f"  {k:>5.2f} | {o['net']:>11,.0f} {o['dd']:>9,.0f} {o['mar']:>6.2f} | "
              f"{l['net']:>10,.0f} {l['dd']:>8,.0f} {l['mar']:>6.2f} | "
              f"{'PASS' if (ok_o and ok_l) else 'fail'}"
              f"  (OPT {'>=' if ok_o else '<'} base, LB {'>=' if ok_l else '<'} base)")

    # ── JUDGE ─────────────────────────────────────────────────────────────────
    print("\n=== JUDGE ===")
    p05 = results[0.5][2]; p075 = results[0.75][2]; p125 = results[1.25][2]
    for k in TILTS:
        o, l, p = results[k]
        print(f"  k={k:.2f}: MAR OPT {o['mar']:.2f} vs {base_o['mar']:.2f}, "
              f"LB {l['mar']:.2f} vs {base_l['mar']:.2f} -> "
              f"{'passes both windows' if p else 'does NOT pass both windows'}")
    if p05 and p075:
        print("  VERDICT: 0.5x FOMC half-size GRADUATES — passes both windows and "
              "sits on a plateau (0.75x neighbor also passes).")
    elif p05:
        print("  VERDICT: 0.5x passes both windows but the 0.75x neighbor fails — "
              "knife-edge, does NOT graduate.")
    else:
        print("  VERDICT: pre-registered 0.5x FOMC half-size does NOT graduate "
              "(fails the MAR>=baseline test in at least one window).")
    if p125:
        print("  NOTE: 1.25x (upsizing FOMC days) also passes — the FOMC-day tilt "
              "direction is not identified; treat any pass above with suspicion.")


if __name__ == "__main__":
    main()

"""ml_gate look-ahead measurement (read-only experiment, no production files touched).

CONTEXT: augur_engine/ml_gate.py `entry_features(arrays)` builds a per-bar feature
matrix where row i uses bars <= i INCLUDING bar i's own high/low/close (mom_5,
mom_20, atr_norm, atr_ratio, trend_20, range_pos; tod_sin/tod_cos/dow are clock-only
and safe). `gate_trades` (and every other reader of entry_features' output) then
does `X = F[E]` where E = trade ENTRY bar. But every strategy plugin fills at the
entry bar's OPEN (next-bar-open-style fill on the signal), so reading row E leaks
that same bar's high/low/close into the feature the gate scores the trade with —
one bar of intrabar look-ahead.

This script measures how much that inflates gated results by re-running gate_trades
with (a) the feature matrix AS SHIPPED (F[E], contaminated) and (b) a CAUSAL version
where the non-clock feature columns are shifted down one row (row E reads bar E-1's
close instead), leaving tod_sin/tod_cos/dow untouched (the entry-bar clock IS known
at the open).

FIXED 2026-08-10: augur_engine/ml_gate.py now ships `entry_features_causal(arrays)`
(the same shift built here as `build_causal_feats`) and the four contaminated
readers (gate_trades' default feats, gate_explain, gate_calibration,
gate_feature_select) call it instead of the raw `entry_features`. The "GATED
default (no feats=)" row added below calls gate_trades with NO feats= at all — it
should now match the "GATED causal" row exactly, proving the shipped default is
no longer contaminated (not just that a hand-built causal matrix is safe).

Run:  python tools/gate_lookahead_audit.py   (from repo root, or anywhere — path is
      resolved relative to this file)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import load_strategy
from augur_engine.ml_gate import entry_features, entry_features_causal, gate_trades

MULT_NQ = 20.0
COST_PTS = 0.533

GATE_KW = dict(model="logistic", threshold=0.50, min_history=30, refit_every=25, seed=42)


def _fmt_money(x):
    return "${:,.0f}".format(x)


def _net_after_cost(trades, mult, cost_pts):
    """trades: [(entry, exit, pnl_pts, side, entry_px), ...] gross points.
    Apply the same flat per-round-trip cost_pts subtraction the engine uses,
    return total NET dollars."""
    pnls = np.array([t[2] for t in trades], float)
    net_pts = pnls - cost_pts
    return float(net_pts.sum() * mult)


def _stats_dollars(trades, mult, cost_pts):
    pnls = np.array([t[2] for t in trades], float) - cost_pts
    n = len(pnls)
    if n == 0:
        return dict(total_pnl=0.0, num_trades=0, win_rate=0.0, profit_factor=0.0, max_drawdown=0.0)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls) * mult
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    return dict(
        total_pnl=float(pnls.sum() * mult),
        num_trades=n,
        win_rate=float(100.0 * len(wins) / n),
        profit_factor=(gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        max_drawdown=float((cum - peak).min()),
    )


def build_causal_feats(F, names):
    """Shift non-clock columns down one row (row i -> reads row i-1's inputs).
    Clock columns (tod_sin, tod_cos, dow) stay unshifted — known at the open."""
    clock_cols = {"tod_sin", "tod_cos", "dow"}
    F = np.asarray(F, float)
    Fc = F.copy()
    lag_idx = [j for j, nm in enumerate(names) if nm not in clock_cols]
    if lag_idx:
        sub = F[:, lag_idx]
        sub_lagged = np.vstack([sub[0:1], sub[:-1]])
        Fc[:, lag_idx] = sub_lagged
    return Fc


def run_gate_comparison(label, arrays, trades, mult, cost_pts):
    F, names = entry_features(arrays)
    F_causal = build_causal_feats(F, names)

    raw_stats = _stats_dollars(trades, mult, cost_pts)

    g_base = gate_trades(arrays, trades, feats=F, **GATE_KW)
    g_causal = gate_trades(arrays, trades, feats=F_causal, **GATE_KW)
    # v2026-08-10 (post-fix verification): gate_trades called with NO feats= at all now
    # defaults to entry_features_causal internally (augur_engine/ml_gate.py), so it
    # should reproduce the explicit-causal leg exactly — proving the shipped default
    # is no longer contaminated, not just that a hand-built causal matrix is safe.
    g_default = gate_trades(arrays, trades, **GATE_KW)

    kept_base = g_base["trades"] if g_base else []
    kept_causal = g_causal["trades"] if g_causal else []
    kept_default = g_default["trades"] if g_default else []

    base_stats = _stats_dollars(kept_base, mult, cost_pts)
    causal_stats = _stats_dollars(kept_causal, mult, cost_pts)
    default_stats = _stats_dollars(kept_default, mult, cost_pts)

    print("=" * 100)
    print(label)
    print("feature columns:", names)
    print("-" * 100)
    hdr = "%-22s %14s %8s %8s %6s %14s" % (
        "variant", "total_pnl", "trades", "win%", "PF", "maxDD")
    print(hdr)
    print("-" * 100)
    for nm, s in (("RAW (ungated)", raw_stats),
                  ("GATED baseline (F[E])", base_stats),
                  ("GATED causal (F[E-1])", causal_stats),
                  ("GATED default (no feats=)", default_stats)):
        pf = s["profit_factor"]
        pf_s = "%.2f" % pf if pf != float("inf") else "inf"
        print("%-22s %14s %8d %7.1f%% %8s %14s" % (
            nm, _fmt_money(s["total_pnl"]), s["num_trades"], s["win_rate"], pf_s,
            _fmt_money(s["max_drawdown"])))
    print("-" * 100)
    delta_pnl = base_stats["total_pnl"] - causal_stats["total_pnl"]
    delta_n = base_stats["num_trades"] - causal_stats["num_trades"]
    delta_wr = base_stats["win_rate"] - causal_stats["win_rate"]
    print("DELTA (baseline - causal): total_pnl=%s  num_trades=%+d  win_rate=%+.1fpp" % (
        _fmt_money(delta_pnl), delta_n, delta_wr))
    default_matches_causal = (
        abs(default_stats["total_pnl"] - causal_stats["total_pnl"]) < 0.01
        and default_stats["num_trades"] == causal_stats["num_trades"])
    print("POST-FIX CHECK: gate_trades(no feats=) == GATED causal -> %s" % (
        "PASS" if default_matches_causal else "FAIL"))
    if g_base:
        print("baseline gate summary:", {k: v for k, v in g_base["summary"].items()
                                          if k in ("model", "threshold", "n_fits", "warmup",
                                                    "degenerate", "n_total", "n_kept", "n_skipped")})
    if g_causal:
        print("causal   gate summary:", {k: v for k, v in g_causal["summary"].items()
                                          if k in ("model", "threshold", "n_fits", "warmup",
                                                    "degenerate", "n_total", "n_kept", "n_skipped")})
    print()
    return dict(raw=raw_stats, base=base_stats, causal=causal_stats, default=default_stats,
                default_matches_causal=default_matches_causal)


def audit_orb():
    print("\n##### ORB 3.1 — NQ 5m RTH, source=tv, pre-lockbox (date_to=2025-06-29) #####\n")
    master = find_master("NQ", "5m", session="rth", source="tv")
    if master is None:
        print("!! no NQ 5m rth source=tv master found — listing masters:")
        from augur_engine.data import list_masters
        for m in list_masters():
            print(" ", m.get("instrument"), m.get("timeframe"), m.get("session"), m.get("source"), m.get("filename"))
        return None

    mod = load_strategy("ORB_3_1.py")

    # champion params, run #125 (ORB.md / BACKTESTING_STACK.md): ORB_3_1.py at
    # "p0/trail5" -- partial_exit_R=0, trail_bars=5 (single-lot ride + 5-bar trailing
    # stop), or1/stop.75/vol1.25/Both. Certified: full-history n=4064, net $360,640.26,
    # PF 1.611, DD -$9,351.60.
    champ_params = dict(
        or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
        breakout_buf=0.0, close_confirm=False,
        partial_exit_R=0.0, trail_bars=5,
        atr_filter=0.0, target_R=0.0,
        flat_eod=True, skip_holidays=False,
    )

    for label, date_to in (("PRE-LOCKBOX (date_to=2025-06-29)", "2025-06-29"),
                            ("FULL HISTORY (no date_to)", None)):
        arrays = load_master_arrays(master, date_from=None, date_to=date_to)
        O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
        V = arrays.get("volume")
        did = arrays.get("day_id")
        res = mod.run_backtest(O, H, L, C, volumes=V, day_id=did,
                                return_trades=True, **champ_params)
        if res is None:
            print(label, "-> NO TRADES"); continue
        trades = res["trades"]
        net_gross = res["total_pnl"] * MULT_NQ
        net_after_cost = _net_after_cost(trades, MULT_NQ, COST_PTS)
        print(f"{label}: bars={len(C)} sessions={int(did.max())+1 if did is not None else '?'} "
              f"trades={res['num_trades']} gross_pnl=${net_gross:,.0f} "
              f"net_after_cost(${COST_PTS}/pt)=${net_after_cost:,.0f}")
        if date_to == "2025-06-29":
            print(f"  sanity target ~$306,516 net")
        else:
            print(f"  sanity target ~$360,640 net")

    # Use pre-lockbox window for the gate comparison (matches the sanity check + is the
    # window gate_validate would actually train/select on).
    arrays = load_master_arrays(master, date_from=None, date_to="2025-06-29")
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V = arrays.get("volume")
    did = arrays.get("day_id")
    res = mod.run_backtest(O, H, L, C, volumes=V, day_id=did,
                            return_trades=True, **champ_params)
    trades = res["trades"]
    print(f"\nGate comparison built on {len(trades)} ORB 3.1 trades "
          f"(cost_pts={COST_PTS}, NQ mult={MULT_NQ})\n")
    return run_gate_comparison("ORB 3.1 (NQ 5m RTH, tv, pre-lockbox)", arrays, trades,
                                MULT_NQ, COST_PTS)


def audit_noise():
    print("\n##### NOISE 1.0 — NQ, source=db_noadj_rth #####\n")
    master = find_master("NQ", "5m", session="rth", source="db_noadj_rth")
    if master is None:
        # try without session filter, or another timeframe NOISE_1_0 might expect
        from augur_engine.data import list_masters
        cands = [m for m in list_masters() if m.get("source") == "db_noadj_rth" and m.get("instrument") == "NQ"]
        if cands:
            master = cands[0]
        else:
            print("!! no NQ db_noadj_rth master found — listing masters:")
            for m in list_masters():
                print(" ", m.get("instrument"), m.get("timeframe"), m.get("session"), m.get("source"), m.get("filename"))
            return None
    print("using master:", master.get("filename"), master.get("timeframe"), master.get("session"))

    mod = load_strategy("NOISE_1_0.py")
    params = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                  exit_mode="vwap", side="Both", window="all_day", flat_eod=True,
                  skip_holidays=False, stop_mode="bandwidth", stop_k=1.75)

    arrays = load_master_arrays(master, date_from=None, date_to=None)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V = arrays.get("volume")
    did = arrays.get("day_id")
    import inspect
    sig = inspect.signature(mod.run_backtest).parameters
    kwargs = dict(volumes=V, return_trades=True, **params)
    if "day_id" in sig:
        kwargs["day_id"] = did
    res = mod.run_backtest(O, H, L, C, **kwargs)
    if res is None:
        print("NOISE_1_0 -> NO TRADES with these params"); return None
    trades = res["trades"]
    print(f"NOISE 1.0: bars={len(C)} trades={res['num_trades']} "
          f"gross_pnl=${res['total_pnl']*MULT_NQ:,.0f} "
          f"net_after_cost=${_net_after_cost(trades, MULT_NQ, COST_PTS):,.0f}")
    return run_gate_comparison("NOISE 1.0 (NQ, db_noadj_rth)", arrays, trades, MULT_NQ, COST_PTS)


if __name__ == "__main__":
    orb_result = audit_orb()
    try:
        noise_result = audit_noise()
    except Exception as e:
        import traceback
        print("\nNOISE_1_0 audit failed:", e)
        traceback.print_exc()

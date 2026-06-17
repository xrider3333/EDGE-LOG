"""The callable backtest entry point (streamlit-free).

run_backtest() ties a strategy plugin + a master (or raw arrays) + params together,
using the SAME rules as the Streamlit app:
  • signature introspection — pass volumes/day_id only if the plugin declares them
    (or has **kwargs), so older plugins that don't take them still work;
  • cost application — subtract cost_pts (commission+slippage per round-trip, in
    points) from each trade and re-derive NET metrics, byte-identical to the app's
    _apply_costs / augur_mp_worker path.
"""
import inspect

from .strategies import load_strategy
from .data import find_master, load_master_arrays
from .analytics import monte_carlo_drawdown


def _apply_costs(m, cost_pts):
    """Re-derive NET metrics from the trade list after subtracting cost_pts/trade.
    Same math as augur_mp_worker._apply_costs (kept inline so this package is
    self-contained)."""
    trades = m.get("trades") if isinstance(m, dict) else None
    if not trades:
        return m
    net = []
    for t in trades:
        nt = list(t)
        if len(nt) >= 3:
            nt[2] = nt[2] - cost_pts
        net.append(tuple(nt))
    pnls = [t[2] for t in net]
    n = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    total = float(sum(pnls))
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    out = dict(m)
    out.update({"total_pnl": total, "num_trades": n,
                "win_rate": (100.0 * wins / n) if n else 0.0,
                "profit_factor": pf, "max_drawdown": float(mdd),
                "avg_pnl": (total / n) if n else 0.0,
                "wins": wins, "losses": losses, "trades": net})
    return out


def run_backtest(strategy, *, instrument=None, timeframe="5m", session="rth",
                 source=None, params=None, master=None, arrays=None,
                 cost_pts=0.0, return_trades=False, mc_sims=0, mc_block=1):
    """Run one backtest and return the metrics dict (with a "_meta" block).

    strategy   : plugin filename ('ORB_SIMPLE_1_0.py'), path, or a loaded module.
    Data is resolved in priority order: explicit `arrays` -> explicit `master` row
    -> find_master(instrument, timeframe, session, source).
    cost_pts   : per-round-trip cost in POINTS (e.g. NQ $5.66 / $20 = 0.283).
    """
    mod = strategy if hasattr(strategy, "run_backtest") else load_strategy(strategy)
    params = dict(params or {})

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(
                    f"no master for instrument={instrument} timeframe={timeframe} "
                    f"session={session} source={source}")
        arrays = load_master_arrays(master)

    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V = arrays.get("volume")
    did = arrays.get("day_id")

    fn = mod.run_backtest
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    extras = {}
    if V is not None and (has_kw or "volumes" in sp):
        extras["volumes"] = V
    if did is not None and (has_kw or "day_id" in sp):
        extras["day_id"] = did

    want_trades = bool(return_trades or cost_pts > 0 or mc_sims > 0)
    res = fn(O, H, L, C, **extras, **params, return_trades=want_trades)

    if res and cost_pts > 0:
        res = _apply_costs(res, cost_pts)

    if isinstance(res, dict):
        if mc_sims and res.get("trades"):
            res["mc"] = monte_carlo_drawdown([t[2] for t in res["trades"]],
                                             n_sims=int(mc_sims), block=int(mc_block))
        if not return_trades:
            res.pop("trades", None)
        res["_meta"] = {
            "strategy": getattr(mod, "STRATEGY_NAME", None),
            "master": (arrays.get("meta") or {}).get("name"),
            "bars": int(len(C)),
            "cost_pts": float(cost_pts),
        }
    return res

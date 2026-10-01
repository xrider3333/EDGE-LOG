"""A SECOND READING OF EVERY RUN AT REALISTIC COST, beside the flat one.

WHY (owner GO 2026-09-30, from MANAGER's ziplime review, idea 2). Every run charges ONE flat
cost per round trip - 0.533 NQ points is the house figure - and reports a single net. That
number answers "did the rule find an edge", not "would the edge survive being traded". The case
that made this urgent: live NOISE on Webull paid about $0.30 per share each way against an edge
of about $0.10 per share. A crown can look strong and still be inside its own costs.

WHAT THIS GIVES, and what it deliberately does not:

  - `readings()` - net at the flat cost (unchanged, for reference), net at DOUBLE cost, and the
    BREAKEVEN cost: the per-round-trip cost at which the run's net reaches zero. Breakeven is
    the honest headline, because it is one number a human can compare against a broker's real
    figure without re-running anything.
  - `realistic()` - a size- and volume-aware reading: a fee per contract, half the spread, and
    slippage that grows with volatility. **It is NOT FITTED.** Its defaults are published
    figures, not measured ones, so every result it returns carries `fitted=False` and the
    provenance of each input. Fitting it to the Webull and NinjaTrader fills is a separate job
    needing those lanes' data; until then this is a sanity reading, not a verdict.

THE COST CONTRACT, which is easy to get wrong. Trades arrive NET - `run_backtest` has already
subtracted `cost_pts` from each one (see analytics.py's note: "never re-subtract"). So
re-costing means ADDING BACK the original charge and then subtracting the new one. Charging the
new cost on top of a net trade list double-counts, which is exactly the bug that note exists to
prevent. Every function here takes the run's own `cost_pts` for that reason and refuses to
guess it.

Nothing here changes a stored run. It is a reading computed from a run's trades on demand, so
no cache key moves and no existing number shifts.
"""
import numpy as np

# Published, NOT measured. Each entry says where it came from so a reader can weigh it.
# Fitting these to real fills is the open half of this work.
# `tick_usd` is what ONE tick is worth on ONE unit - a contract for futures, a SHARE for a
# stock or ETF. Getting QQQ wrong here (a $1 tick instead of a $0.01 one) made its cost read
# 100x too small, which silently turned the one case this reading exists for into a pass.
DEFAULT_INPUTS = {
    "NQ": dict(fee_per_unit_usd=2.09, tick_size=0.25, tick_usd=5.0,
               half_spread_ticks=0.5, slip_frac_of_atr=0.01,
               note="CME + broker round-turn fee, half-tick spread each way, slippage 1% of ATR "
                    "each way - published/assumed figures, not fitted"),
    "ES": dict(fee_per_unit_usd=2.09, tick_size=0.25, tick_usd=12.5,
               half_spread_ticks=0.5, slip_frac_of_atr=0.01,
               note="as NQ; ES is usually tighter, so this is conservative"),
    "QQQ": dict(fee_per_unit_usd=0.30, tick_size=0.01, tick_usd=0.01,
                half_spread_ticks=1.0, slip_frac_of_atr=0.02,
                note="Webull paper MEASURED about $0.30/share round trip against a ~$0.10/share "
                     "edge - the case that prompted this reading"),
}


def gross_pnls(trades, cost_pts):
    """Per-trade GROSS points, undoing the flat charge the backtest already applied.

    `cost_pts` must be the run's own value. Passing 0 for a run that charged a cost silently
    treats its net as gross and understates every re-costed reading.
    """
    c = float(cost_pts or 0.0)
    return np.array([float(t[2]) + c for t in (trades or []) if len(t) >= 3], dtype="float64")


def readings(trades, cost_pts, mult=1.0):
    """Net at the flat cost, at double it, and the cost at which the run breaks even.

    `mult` converts a point to money (20 for NQ, 50 for ES, 1 for a share). Returns points and
    money side by side, because the flat cost is quoted in points and a broker quotes money.
    """
    g = gross_pnls(trades, cost_pts)
    n = len(g)
    c = float(cost_pts or 0.0)
    if n == 0:
        return dict(n_trades=0, cost_pts=c, net_flat_pts=0.0, net_double_pts=0.0,
                    breakeven_cost_pts=None, headroom_x=None, gross_pts=0.0,
                    net_flat_usd=0.0, net_double_usd=0.0, breakeven_cost_usd=None)
    gross = float(g.sum())
    net_flat = gross - n * c
    net_double = gross - n * (2.0 * c)
    # The cost per round trip that would take net to zero. Negative gross means the rule loses
    # money before any cost at all, so there is no positive breakeven to quote.
    breakeven = (gross / n) if gross > 0 else None
    return dict(
        n_trades=n, cost_pts=c, gross_pts=gross,
        net_flat_pts=net_flat, net_double_pts=net_double,
        breakeven_cost_pts=breakeven,
        # How many times the charged cost the run could absorb before breaking even. 1.0 means
        # it is exactly at its limit; below 1.0 it is already under water at the flat cost.
        headroom_x=(breakeven / c) if (breakeven is not None and c > 0) else None,
        net_flat_usd=net_flat * float(mult), net_double_usd=net_double * float(mult),
        breakeven_cost_usd=(breakeven * float(mult)) if breakeven is not None else None,
    )


def realistic_cost_pts(instrument, atr_pts=None, contracts=1, inputs=None):
    """A per-round-trip cost in POINTS: fee + spread + volatility-scaled slippage.

    Returns (cost_pts, breakdown). The breakdown names every component so a reader can see
    which assumption is doing the work, and carries fitted=False - these are published
    figures, not fitted to our fills.
    """
    cfg = dict(DEFAULT_INPUTS.get(str(instrument).upper(),
                                  DEFAULT_INPUTS["NQ"]))
    if inputs:
        cfg.update(inputs)
    tick, tick_usd = float(cfg["tick_size"]), float(cfg["tick_usd"])
    pts_per_usd = tick / tick_usd if tick_usd else 0.0

    fee_pts = float(cfg["fee_per_unit_usd"]) * pts_per_usd * max(1, int(contracts))
    spread_pts = float(cfg["half_spread_ticks"]) * tick * 2.0        # in and out
    slip_pts = 0.0
    if atr_pts:
        # a fraction of the bar's own range, each way - this is the volatility-aware part
        slip_pts = float(cfg["slip_frac_of_atr"]) * float(atr_pts) * 2.0
    total = fee_pts + spread_pts + slip_pts
    return total, dict(fee_pts=fee_pts, spread_pts=spread_pts, slippage_pts=slip_pts,
                       total_pts=total, contracts=max(1, int(contracts)),
                       atr_pts=(float(atr_pts) if atr_pts else None),
                       fitted=False, source=cfg["note"])


def realistic(trades, cost_pts, instrument, mult=1.0, atr_pts=None, contracts=1, inputs=None):
    """The run re-costed at the realistic figure, next to its flat reading.

    `survives` is the question the reading exists to answer: is the run still profitable once
    a plausible real cost is charged? It is reported alongside `fitted=False`, so a negative
    answer is a prompt to measure, never a verdict on its own.
    """
    r = readings(trades, cost_pts, mult)
    rc, breakdown = realistic_cost_pts(instrument, atr_pts, contracts, inputs)
    n, gross = r["n_trades"], r["gross_pts"]
    net = gross - n * rc if n else 0.0
    out = dict(r)
    out.update(realistic_cost_pts=rc, net_realistic_pts=net,
               net_realistic_usd=net * float(mult),
               realistic_breakdown=breakdown,
               survives=(net > 0) if n else None,
               # A run whose breakeven sits under the realistic cost is inside its own costs,
               # whatever its flat net says.
               realistic_over_breakeven=(
                   (rc / r["breakeven_cost_pts"]) if r["breakeven_cost_pts"] else None))
    return out


def summary_lines(r):
    """Plain-English lines for a run report. No code identifiers, no tables."""
    if not r.get("n_trades"):
        return ["No trades, so there is nothing to re-cost."]
    lines = []
    be = r.get("breakeven_cost_pts")
    if be is None:
        lines.append("This run loses money before any cost is charged, so there is no "
                     "break-even cost to quote.")
    else:
        lines.append("It breaks even at %.3f points per round trip, against the %.3f it was "
                     "charged - it can absorb %.1f times its own cost."
                     % (be, r["cost_pts"], r["headroom_x"]))
        lines.append("At double cost the net is %s." % _money(r["net_double_usd"]))
    if "net_realistic_pts" in r:
        b = r["realistic_breakdown"]
        lines.append("At a realistic %.3f points per round trip (%.3f fee, %.3f spread, %.3f "
                     "slippage) the net is %s."
                     % (r["realistic_cost_pts"], b["fee_pts"], b["spread_pts"],
                        b["slippage_pts"], _money(r["net_realistic_usd"])))
        lines.append("Those cost inputs are published figures, NOT fitted to our own fills, so "
                     "treat this as a sanity check rather than a verdict.")
    return lines


def _money(v):
    return ("-$%s" % format(abs(v), ",.0f")) if v < 0 else ("$%s" % format(v, ",.0f"))

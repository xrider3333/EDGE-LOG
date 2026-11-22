"""RISK-% SIZING of a finished trade list (owner 11-22, board 132): "instead of just one NQ, what would happen if it
trades 1 / 2 / 3 % of account equity" - risk %, "since that's how traders normally trade (1-3% per trade)".

Pure: entries and exits are the run's own; only HOW MANY CONTRACTS each trade carries changes.

THE RULE (owner spec):
  * start equity $30,000 (the ROC @ $30k yardstick) and it COMPOUNDS: equity at a trade's entry = start + the dollars
    of every trade that EXITED at or before that entry (realized only - an open trade's paper P&L is not spendable);
  * risk_usd  = equity_at_entry x pct;
  * contracts = floor(risk_usd / (risk_pts x point value)) in MICRO units (0.1 of a contract: MNQ for NQ, MES for ES),
                capped at 10 full contracts (owner max);
  * risk_pts  = the trade's own initial risk (|entry - initial stop|) when the strategy exposes it; otherwise the run's
                MEDIAN LOSING TRADE in points (per contract, after cost), and the result says so (risk_fallback);
  * 0 contracts -> the trade is SKIPPED and counted; an account at or below zero takes no trade;
  * trade $ = gross points x point value x contracts - cost per contract x contracts
            ( = net points per contract x point value x contracts ).
FIXED 1 NQ is the plain one-contract chain, no compounding.

THE READ (every column, the same way): the daily equity curve, net, end equity, max DD $, DD % from peak on the $30k
start, ROC @ $30k (annualised, drawdowns.four_numbers), DD5, Sortino (daily, zero days in), trades taken, trades
skipped, the most contracts any trade used, and RUIN = equity ever under 50 % of the start.
"""
from __future__ import annotations

import math

from .drawdowns import four_numbers

START_USD = 30_000.0
MAX_CONTRACTS = 10.0
MICRO = 0.1
RUIN_FRAC = 0.5
PCTS = (0.01, 0.02, 0.03)


def median_loss_pts(net_pts_per_contract):
    """|median| of the losing trades' net points per contract, or None when no trade lost."""
    losses = sorted(-float(x) for x in net_pts_per_contract if float(x) < 0)
    if not losses:
        return None
    k = len(losses)
    return losses[k // 2] if k % 2 else 0.5 * (losses[k // 2 - 1] + losses[k // 2])


def contracts_for(equity, pct, risk_pts, point_value, max_contracts=MAX_CONTRACTS, micro=MICRO):
    """floor(equity x pct / (risk_pts x point_value)) in `micro` steps, capped. 0.0 when it rounds to nothing."""
    if equity <= 0 or not risk_pts or risk_pts <= 0 or point_value <= 0:
        return 0.0
    raw = (equity * pct) / (risk_pts * point_value)
    steps = math.floor(raw / micro + 1e-9)
    c = round(steps * micro, 6)
    return min(c, float(max_contracts))


def size_chain(trades, *, point_value, cost_pts, pct=None, start=START_USD, max_contracts=MAX_CONTRACTS,
               micro=MICRO, fallback_risk=None):
    """Size one chain. `trades`: dicts with e (entry time, sortable), x (exit time), p (net points at the file's unit,
    after cost), z (the file's own size, default 1), r (initial risk points or None), d (exit session day).
    pct None = FIXED 1 contract. -> dict(rows=[(d, usd)], taken, skipped, max_c, ruin, min_equity, risk_fallback_n)."""
    order = sorted(range(len(trades)), key=lambda i: (trades[i]["e"], i))
    by_exit = sorted(range(len(trades)), key=lambda i: (trades[i]["x"], i))
    usd = [0.0] * len(trades)
    sized = [False] * len(trades)
    realized = 0.0
    xp = 0
    taken = skipped = fb_n = 0
    max_c = 0.0
    eq_min = start
    for i in order:
        t = trades[i]
        # bank every trade that exited at or before this entry (in exit order) before sizing it
        while xp < len(by_exit) and trades[by_exit[xp]]["x"] <= t["e"]:
            j = by_exit[xp]
            if sized[j]:
                realized += usd[j]
                eq_min = min(eq_min, start + realized)
            xp += 1
        z = float(t.get("z") or 1.0) or 1.0
        net_pc = float(t["p"]) / z                       # net points per contract
        if pct is None:
            c = 1.0
        else:
            rk = t.get("r")
            if rk is None or not (float(rk) > 0):
                rk = fallback_risk
                fb_n += 1
            c = contracts_for(start + realized, pct, rk, point_value, max_contracts, micro) if rk else 0.0
        if c <= 0:
            skipped += 1
            continue
        gross = net_pc + float(cost_pts)
        usd[i] = gross * point_value * c - float(cost_pts) * point_value * c
        sized[i] = True
        taken += 1
        max_c = max(max_c, c)
    while xp < len(by_exit):                             # bank the rest for the ruin read
        j = by_exit[xp]
        if sized[j]:
            realized += usd[j]
            eq_min = min(eq_min, start + realized)
        xp += 1
    rows = [(trades[i]["d"], usd[i]) for i in range(len(trades)) if sized[i]]
    return {"rows": rows, "taken": taken, "skipped": skipped, "max_c": round(max_c, 6),
            "ruin": eq_min < RUIN_FRAC * start, "min_equity": round(eq_min, 2), "risk_fallback_n": fb_n}


def read_chain(sized, days, start=START_USD):
    """Daily curve + the KPIs for one sized chain over the stretch's `days` (every day, zero days included)."""
    acc = {}
    for d, u in sized["rows"]:
        acc[d] = acc.get(d, 0.0) + u
    ds = sorted(set(days) | set(acc))
    daily = [acc.get(d, 0.0) for d in ds]
    eq, s = [], start
    for v in daily:
        s += v
        eq.append(round(s, 2))
    f = four_numbers(daily, dates=ds, start=start) if len(ds) >= 2 else {}
    peak, mdd = start, 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, peak - v)
    net = math.fsum(daily)
    return {"d": ds, "eq": eq, "net": round(net, 2), "end_equity": round(start + net, 2), "max_dd_usd": round(mdd, 2),
            "dd_pct": (round(f["dd_pct_peak"], 2) if f.get("dd_pct_peak") is not None else None),
            "roc30": (round(f["roc30"], 2) if f.get("roc30") is not None else None),
            "dd5": f.get("dd5_usd"), "sortino": (round(f["sortino"], 3) if f.get("sortino") is not None else None),
            "one_episode": f.get("one_episode"), "trades": sized["taken"], "skipped": sized["skipped"],
            "max_contracts": sized["max_c"], "ruin": bool(sized["ruin"]), "min_equity": sized["min_equity"],
            "risk_fallback_n": sized["risk_fallback_n"]}


def sizing_table(trades, days, *, point_value, cost_pts, start=START_USD, pcts=PCTS, max_contracts=MAX_CONTRACTS,
                 micro=MICRO):
    """FIXED 1 + RISK pct columns. -> {"start", "risk_src", "fallback_risk_pts", "cols": {"fixed": read, "r1": ...}}.
    risk_src: "trade" (every trade carries its own stop), "mixed", or "median_loss" (none does)."""
    net_pc = [float(t["p"]) / (float(t.get("z") or 1.0) or 1.0) for t in trades]
    have = sum(1 for t in trades if t.get("r") is not None and float(t["r"]) > 0)
    fb = median_loss_pts(net_pc) if have < len(trades) else None
    src = "trade" if have == len(trades) else ("median_loss" if have == 0 else "mixed")
    cols = {"fixed": read_chain(size_chain(trades, point_value=point_value, cost_pts=cost_pts, pct=None, start=start),
                                days, start)}
    for p in pcts:
        k = "r%g" % (p * 100)
        cols[k] = read_chain(size_chain(trades, point_value=point_value, cost_pts=cost_pts, pct=p, start=start,
                                        max_contracts=max_contracts, micro=micro, fallback_risk=fb), days, start)
        cols[k]["pct"] = p
    return {"start": start, "risk_src": src, "fallback_risk_pts": (round(fb, 4) if fb is not None else None),
            "max_contracts_cap": max_contracts, "micro": micro, "ruin_frac": RUIN_FRAC, "cols": cols}

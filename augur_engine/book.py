"""BOOK runs — score N strategies traded side by side as ONE strategy.

A BOOK is what the owner actually deploys: two (or more) strategies running in the same
account, 1 contract each. Until now the app could not measure one — Auto-Validate takes a
single strategy file — so book numbers were computed offline by tools/t5_runboard.py and
pasted into the web app by hand (the "BOOKS problem" in RUNBOARD.md item B).

What this does: run every leg over the SAME window with FIXED params, convert each leg's
trades to DOLLARS with that leg's own contract multiplier, pool every trade into one pile
bucketed by EXIT DATE, and score the pile as one strategy. Pooling is what makes PF and
drawdown true BOOK numbers: a day where one leg loses and the other wins nets out first,
exactly as the account would see it.

Honesty boundaries — these are deliberate, do not "improve" them without reading item B:
  * A book run is a REPLAY of already-frozen params. Nothing is tuned here, so there is no
    in-sample search and no walk-forward fold engine result to report. `top10_results` is
    left empty on purpose so the app never shows house numbers in a WF column.
  * The LOCKBOX split IS reported: the legs' params were frozen before that stretch, so the
    last `lockbox_months` are a genuine unseen-data read for the book as a whole.
  * The 8-equal-stretch consistency count rides under `book.slices` as its OWN thing. It is
    a house test, NOT the app's walk-forward, and must never be merged into a WF column.
"""
from __future__ import annotations

import numpy as np

from .engine import run_backtest
from .data import find_master, load_master_arrays

# contract $ per point, mirroring the web app's INSTRUMENTS table. A leg may override with
# its own "mult" — that wins, so an instrument this table has never heard of still works.
_MULT = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "RTY": 50, "M2K": 5,
         "YM": 5, "MYM": 0.5, "CL": 1000, "MCL": 100, "GC": 100, "MGC": 10,
         "SI": 5000, "ZB": 1000, "ZN": 1000, "6E": 125000, "BTC": 5, "MBT": 0.1}


def _leg_mult(leg):
    m = leg.get("mult")
    try:
        if m and float(m) > 0:
            return float(m)
    except Exception:
        pass
    return float(_MULT.get(str(leg.get("instrument") or "").upper(), 20))


def _leg_trades(leg, date_from, date_to):
    """Run ONE leg over the window; return [(exit_date, pnl_usd), ...] plus a small info dict.

    Trades are stamped by EXIT date — one uniform convention across every leg, so a trade
    that spans midnight lands in the day it was actually closed and booked.
    """
    inst = leg.get("instrument")
    tf = leg.get("timeframe", "5m")
    sess = leg.get("session") or "rth"
    src = leg.get("source")
    # A saved run does not always record its SESSION, so a leg can arrive claiming "rth" while
    # its data source is an overnight (eth) master — the pair then matches nothing and the whole
    # book dies. Try the leg as given, then the session its own source name implies, then drop
    # the source pin entirely. Whatever finally matched is reported back in the leg info, so a
    # book never silently runs on data the leg did not ask for.
    tries = [(sess, src)]
    implied = "eth" if "eth" in str(src or "").lower() else ("rth" if "rth" in str(src or "").lower() else None)
    if implied and implied != sess:
        tries.append((implied, src))
    for _s in ("eth", "rth"):
        if (_s, None) not in tries:
            tries.append((_s, None))
    master = None
    for _s, _src in tries:
        master = find_master(inst, tf, _s, _src)
        if master is not None:
            sess, src = _s, _src
            break
    if master is None:
        raise ValueError(
            f"no data for leg {leg.get('strategy')} ({inst} {tf}) — tried "
            + ", ".join(f"session={a}/source={b or 'any'}" for a, b in tries))
    arr = load_master_arrays(master, date_from=date_from, date_to=date_to)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {},
                       cost_pts=float(leg.get("cost_pts", 0) or 0), return_trades=True)
    raw_trades = list(res.get("trades") or [])

    # ── OPTIONAL ML GATE (2026-08-27, owner: "also need a ML version with top ML's of ea") ──
    # A book leg may carry the same `gate` block a PAPER leg carries. The strategy still
    # picks its own trades; the gate scores each one from what was known at that instant
    # and either refuses it or resizes it.
    #
    # WHY IT CALLS api.paper_gate INSTEAD OF REIMPLEMENTING. api/paper_gate.py already
    # applies these gates for the live forward test, and its own docstring says it
    # deliberately does not reimplement augur_engine.ml_gate's leak rule. Writing a second
    # copy here would give the book and the paper board two things that merely RESEMBLE
    # each other, and the whole point of a gated book is to be comparable to the gated
    # paper legs. So: one implementation, imported lazily (engine -> api is the wrong
    # direction for a module-level import, and a book with no gate must not pay for it).
    #
    # A gate that cannot run degrades to the UNGATED leg, never to an empty one. An empty
    # leg would silently look like "this strategy had a quiet decade" instead of "the
    # overlay broke", so the failure is recorded in the leg info where the report shows it.
    gate_cfg = leg.get("gate")
    sized = [(t, 1.0) for t in raw_trades]
    gate_info = None
    if gate_cfg and raw_trades:
        try:
            from api import paper_gate as _pg
            sized, gate_info = _pg.apply_gate(arr, raw_trades, gate_cfg)
        except Exception as _e:
            sized = [(t, 1.0) for t in raw_trades]
            gate_info = {"ok": False, "error": "%s: %s" % (type(_e).__name__, _e),
                         "note": "gate failed - this leg ran UNGATED"}

    mult = _leg_mult(leg)
    weight = float(leg.get("weight", 1) or 1)
    idx = arr["index"]
    out = []
    # exit-bar timestamps -> calendar day. astype("datetime64[D]") on the whole index once is
    # both faster and warning-free (np.datetime64(x, "D") on a tz-aware stamp warns per call).
    days_idx = np.asarray(idx, dtype="datetime64[D]")
    last = len(days_idx) - 1
    # `size` is the gate's per-trade size multiplier (1.0 everywhere when ungated), so the
    # ungated path is bit-identical to before this feature existed.
    for t, size in sized:
        try:
            out.append((days_idx[min(int(t[1]), last)],
                        float(t[2]) * mult * weight * float(size)))
        except Exception:
            continue
    info = {"strategy": leg.get("strategy"), "instrument": inst, "timeframe": tf,
            "session": sess, "source": src, "mult": mult, "weight": weight,
            "trades": len(out), "net": round(sum(p for _, p in out), 2),
            "master": (arr.get("meta") or {}).get("name"),
            "cost_pts": float(leg.get("cost_pts", 0) or 0)}
    if gate_cfg:
        # Report what the overlay actually did, not just that one was configured -- a gate
        # that quietly fell back to ungated must be visible in the run report.
        info["gate"] = {"mode": gate_cfg.get("mode"), "model": gate_cfg.get("model"),
                        "threshold": gate_cfg.get("threshold"),
                        "raw_trades": len(raw_trades), "kept": len(out)}
        if gate_info:
            for k in ("ok", "error", "note", "n_skipped", "warnings", "size_norm"):
                if gate_info.get(k) is not None:
                    info["gate"][k] = gate_info[k]
    return out, info


def _daily(trades):
    """[(date, $)] -> (dates ascending, per-day $) — the account's daily P&L."""
    if not trades:
        return np.array([], dtype="datetime64[D]"), np.array([], dtype=float)
    d = np.array([t[0] for t in trades], dtype="datetime64[D]")
    p = np.array([t[1] for t in trades], dtype=float)
    days, inv = np.unique(d, return_inverse=True)
    tot = np.zeros(len(days), dtype=float)
    np.add.at(tot, inv, p)
    return days, tot


def _stats(trades):
    """Book metrics over whatever slice of pooled trades it is handed.

    PF is trade-level (gross wins / gross losses, every leg in one pile). Drawdown is
    measured on the DAILY account curve, not trade-by-trade, because the account only ever
    marks once a day and two legs' intraday swings are not additive in a meaningful way.
    Returned drawdown is POSITIVE dollars.
    """
    if not trades:
        return None
    p = np.array([t[1] for t in trades], dtype=float)
    wins = p[p > 0]
    losses = p[p < 0]
    gw = float(wins.sum())
    gl = float(-losses.sum())
    _, daily = _daily(trades)
    cum = np.cumsum(daily)
    dd = float((cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0
    net = float(p.sum())
    return {
        "total_pnl": round(net, 2),
        "num_trades": int(len(p)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": round(100.0 * len(wins) / len(p), 2) if len(p) else 0.0,
        "profit_factor": round(gw / gl, 4) if gl > 1e-9 else None,
        "max_drawdown": round(abs(dd), 2),
        "avg_pnl": round(net / len(p), 2) if len(p) else 0.0,
        "gross_win": round(gw, 2),
        "gross_loss": round(gl, 2),
    }


def _downsample(cum, boundary_i, n_points):
    """Endpoint-pinned downsample of a cumulative curve, carrying an index with it.

    Endpoint-pinned means the LAST sample is the true final value, so the curve's plotted
    end always equals the run's net — the same rule validate.py uses for its own curves.
    """
    n = len(cum)
    if n <= n_points:
        return [round(float(x), 2) for x in cum], (int(boundary_i) if boundary_i is not None else None)
    step = (n - 1) / float(n_points - 1)
    out = [round(float(cum[int(round(i * step))]), 2) for i in range(n_points)]
    bi = None if boundary_i is None else int(boundary_i / step)
    return out, bi


def run_book(legs, *, date_from=None, date_to=None, lockbox_months=12,
             slices=8, equity_points=400, name=None, progress_cb=None):
    """Run a BOOK: every leg over one window with fixed params, pooled and scored as one.

    legs: [{strategy, params, instrument, timeframe, session, source, cost_pts, mult, weight}]
           plus an optional `gate` block per leg (same shape api/paper.py's PAPER_LEGS use:
           {mode, model, threshold, size_norm, recycle_factor, ...}). With no `gate` the leg
           runs exactly as it always has.

    The result is shaped like the other engine results so the runner can persist it as an
    ordinary run: `best` carries the PRE-LOCKBOX metrics (the same convention a validate run
    uses for best_pnl_usd — the stretch that is not the holdout), while `validate.equity`
    spans the WHOLE window with `lb_idx` marking where the lockbox starts.
    """
    legs = [l for l in (legs or []) if l and l.get("strategy")]
    if not legs:
        raise ValueError("a book needs at least one leg")

    pooled = []
    leg_info = []
    for i, leg in enumerate(legs):
        if progress_cb:
            progress_cb(int(5 + 70.0 * i / len(legs)), 100)
        tr, info = _leg_trades(leg, date_from, date_to)
        pooled.extend(tr)
        leg_info.append(info)
    if not pooled:
        raise ValueError("the book produced no trades over this window")

    pooled.sort(key=lambda t: t[0])
    if progress_cb:
        progress_cb(78, 100)

    days, daily = _daily(pooled)
    cum = np.cumsum(daily)

    # ── lockbox split: the last `lockbox_months` of the window. The legs' params were
    #    frozen before this stretch, so for the BOOK it is a genuine unseen-data read.
    lb_from = None
    if lockbox_months and len(days):
        lb_from = days[-1] - np.timedelta64(int(round(lockbox_months * 30.44)), "D")
    pre = [t for t in pooled if lb_from is None or t[0] < lb_from]
    lb = [t for t in pooled if lb_from is not None and t[0] >= lb_from]

    best = _stats(pre) or _stats(pooled)
    whole = _stats(pooled)
    lb_st = _stats(lb)

    # equity curve in DOLLARS over the whole window, with the lockbox door carried through
    # the downsample so the chart can shade the holdout correctly.
    bnd = int(np.searchsorted(days, lb_from)) if lb_from is not None else None
    equity, lb_idx = _downsample(cum, bnd, int(equity_points or 400))

    # ── house consistency test: the daily curve cut into `slices` equal stretches, count
    #    the profitable ones. NOT the walk-forward fold engine — see the module docstring.
    sl = []
    if len(daily) >= slices:
        for part in np.array_split(np.arange(len(daily)), slices):
            sl.append(round(float(daily[part].sum()), 2))
    held = sum(1 for x in sl if x > 0)

    if progress_cb:
        progress_cb(95, 100)

    lb_pass = bool(lb_st and lb_st["total_pnl"] > 0
                   and (lb_st["profit_factor"] or 0) >= 1.0)
    return {
        "best": best,
        "best_params": {"book": [l["strategy"] for l in leg_info]},
        "equity": equity,
        "book": {
            "name": name or " + ".join(str(l.get("strategy") or "") for l in leg_info),
            "legs": leg_info,
            "whole": whole,
            "pre_lockbox": best,
            "lockbox": lb_st,
            "slices": sl,
            "slices_held": held,
            "slices_n": len(sl),
            "lockbox_from": (str(lb_from) if lb_from is not None else None),
            "date_from": (str(days[0]) if len(days) else None),
            "date_to": (str(days[-1]) if len(days) else None),
            "trading_days": int(len(days)),
        },
        # the report card the app already knows how to read. WF is deliberately absent.
        "validate": {
            "verdict": ("PASS" if lb_pass and held >= max(1, int(round(len(sl) * 0.75)))
                        else ("WEAK" if lb_pass else "FAIL")),
            "equity": equity,
            "lb_idx": lb_idx,
            "lockbox": ({"pnl": lb_st["total_pnl"], "pf": lb_st["profit_factor"] or 0,
                         "trades": lb_st["num_trades"], "pass": lb_pass} if lb_st else None),
            "book": True,
        },
        "n_combos": 1,
        "n_evaluated": 1,
        "date_from": (str(days[0]) if len(days) else None),
        "date_to": (str(days[-1]) if len(days) else None),
    }

r"""tools/forward_parity.py -- FORWARD PARITY report + FORWARD CLOCK for the live Webull legs.

WHY (OWNER GO 2026-11-03, GAUNTLET scope E6 + E10, MANAGER #256). Forward paper trading is
the real out-of-sample test now that most lockboxes are spent, but paper parity was only
reported ad hoc. This prints, per live Webull leg and per ISO week:
  * forward trades (closed), hit rate and average P&L a share on the P&L OF RECORD (Webull's
    fill when one was captured, else the book price), against the BACKTEST's own P&L for the
    SAME trades (pnl_backtest, the engine's signal-ledger prices) -- the expectation;
  * execution slippage in $ (fp.exec_usd: fills vs the backtest once the known design gap
    is taken out; negative = worse than the backtest) and how many trades were FLAGGED;
  * the FORWARD CLOCK (E10): trades so far against 300, months so far against 6, which comes
    first at the current pace, and the date a written verdict is due.
"Avg R" is reported as $ a share: these legs have no fixed per-trade risk unit.

Read-only. It runs the executor's own publish-time pipeline (api/qqq_exec: trades.csv ->
_trade_parity -> _merge_reprice -> _merge_backtest_exits -> _apply_broker_parity) so the
numbers are the ones the PAPER tab shows; it writes nothing unless --out is given. Run it on
the box (EDGELOG_HOME=/home/ubuntu/edgelog). The two NinjaTrader legs (NOISE_H_RF, ENGUQ_335
on NT) are PAPER-NT8's half of w88 and are not read here.

  python tools/forward_parity.py                 # all weeks, all legs, text
  python tools/forward_parity.py --json --out f.json
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLOCK_TRADES = 300
CLOCK_MONTHS = 6


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def load_rows(log=lambda *_: None):
    """trades.csv rows with the executor's parity fields merged, oldest first."""
    from api import qqq_exec as qx
    state = qx.load_state(log=log) or {}
    rows = []
    for r in qx._all_trades_from_csv(cap=100000):
        row = dict(r)
        row.update(qx._trade_parity(r, log=log))
        rows.append(row)
    qx._merge_reprice(rows, log=log)
    qx._merge_backtest_exits(rows, state)
    by_base = qx._broker_orders_by_base(qx._all_broker_orders_from_csv(cap=100000))
    qx._apply_broker_parity(rows, by_base, engine_px=qx._engine_prices_by_trade(log=log), log=log)
    rows.sort(key=lambda r: str(r.get("exit_ts") or ""))
    return rows, qx.LIVE_FROM


def family(leg):
    leg = str(leg or "")
    return "DIP_424" if leg.startswith("DIP_") else leg


def _stats(rows):
    n = len(rows)
    out = {"n": n}
    for key, src in (("fwd", "pnl_record"), ("bt", "pnl_backtest")):
        ps = []
        for r in rows:
            p, sh = _f(r.get(src)), _f(r.get("shares")) or 0
            if p is None and key == "fwd":
                p = _f(r.get("pnl"))
            if p is not None and sh:
                ps.append(p / sh)
        out[key + "_n"] = len(ps)
        out[key + "_hit"] = round(sum(p > 0 for p in ps) / len(ps), 3) if ps else None
        out[key + "_avg_ps"] = round(sum(ps) / len(ps), 4) if ps else None
    ex = [_f((r.get("fp") or {}).get("exec_usd")) for r in rows]
    ex = [e for e in ex if e is not None]
    out["slip_usd"] = round(sum(ex), 2)
    out["slip_n"] = len(ex)
    out["flagged"] = sum(bool((r.get("fp") or {}).get("flag")) for r in rows)
    out["book_only"] = sum(bool(r.get("book_only")) for r in rows)
    return out


def clock(rows, start, today):
    n = len(rows)
    t0 = dt.date.fromisoformat(start)
    months = (today - t0).days / 30.44
    by_months = t0 + dt.timedelta(days=round(CLOCK_MONTHS * 30.44))
    by_trades = None
    if n and months > 0:
        by_trades = t0 + dt.timedelta(days=round((today - t0).days * CLOCK_TRADES / n))
    due = min(d for d in (by_months, by_trades) if d)
    return {"start": start, "trades": n, "trades_goal": CLOCK_TRADES,
            "months": round(months, 2), "months_goal": CLOCK_MONTHS,
            "first": "trades" if by_trades and by_trades < by_months else "months",
            "verdict_due": due.isoformat(), "done": n >= CLOCK_TRADES or today >= by_months}


def build(rows, live_from, today):
    legs = {}
    for r in rows:
        if not str(r.get("exit_ts") or "")[:10]:
            continue
        legs.setdefault(family(r.get("leg")), []).append(r)
    report = {"generated": today.isoformat(), "legs": {}}
    for leg, lr in sorted(legs.items()):
        weeks = {}
        for r in lr:
            d = dt.date.fromisoformat(str(r["exit_ts"])[:10])
            y, w, _ = d.isocalendar()
            weeks.setdefault(f"{y}-W{w:02d}", []).append(r)
        start = max(live_from, str(lr[0]["exit_ts"])[:10]) if lr else live_from
        report["legs"][leg] = {"all": _stats(lr),
                               "weeks": {k: _stats(v) for k, v in sorted(weeks.items())},
                               "clock": clock(lr, start, today)}
    return report


def _fmt(s):
    def pct(x):
        return "-" if x is None else f"{x * 100:.0f}%"

    def ps(x):
        return "-" if x is None else f"{x:+.3f}"
    return (f"n {s['n']:3d} | hit fwd {pct(s['fwd_hit'])} bt {pct(s['bt_hit'])} ({s['bt_n']} priced)"
            f" | $/sh fwd {ps(s['fwd_avg_ps'])} bt {ps(s['bt_avg_ps'])}"
            f" | slip ${s['slip_usd']:+.2f} ({s['slip_n']}) | flagged {s['flagged']}"
            f" | book-only {s['book_only']}")


def text(report):
    out = [f"FORWARD PARITY {report['generated']} (Webull legs; fwd = P&L of record, bt = backtest same trades)"]
    for leg, L in report["legs"].items():
        c = L["clock"]
        out.append(f"\n{leg}: {_fmt(L['all'])}")
        out.append(f"  clock: {c['trades']}/{c['trades_goal']} trades, {c['months']}/{c['months_goal']} months"
                   f" since {c['start']} -> {c['first']} first, verdict due {c['verdict_due']}"
                   + (" (DUE NOW)" if c["done"] else ""))
        for wk, s in L["weeks"].items():
            out.append(f"  {wk}: {_fmt(s)}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today)")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    rows, live_from = load_rows()
    rep = build(rows, live_from, today)
    s = json.dumps(rep, indent=1) if a.json else text(rep)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(s)
    print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

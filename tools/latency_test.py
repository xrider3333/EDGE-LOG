"""Webull PAPER order-latency test (owner order 11-21, via MANAGER).

N round trips of 1 share (default SPY: QQQ is the book's symbol, so a test never collides with
a strategy), MARKET, regular session only. Prints a latency table from our own clock plus
Webull's own place_time / filled_time stamps, then makes sure the test position is flat.

Why not premarket: the order adapter refuses an extended-hours OPEN by design
(_extended_hours_refusal: after hours the book may only reduce a position it holds), and
Webull takes only LIMIT orders outside regular hours. So this runs right after the open
(09:31 ET) or any time in the session.

SAFETY
- PAPER only: refuses to run unless the adapter's effective mode is PAPER.
- Its own leg (LATTEST) and its own state file (eodrev dir is not touched): no strategy
  leg, no QQQ.
- 1 share, at most 5 round trips, one open position at a time; every BUY is followed by a
  SELL of the FILLED qty only; a final flatten check reads the position and sells what is
  left (never more).
- --dry-run prints the plan and sends nothing.

Run on the box:  cd ~/edgelog/EDGE-LOG && set -a && . ../edgelog.env && set +a &&
                 ../venv/bin/python -u tools/latency_test.py --n 3
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

HOME = os.environ.get("EDGELOG_HOME", "/home/ubuntu/edgelog")
sys.path.insert(0, os.path.join(HOME, "EDGE-LOG"))
ET = ZoneInfo("America/New_York")
DIR = os.path.join(HOME, "latency_test")
LEG = "LATTEST"
MAX_N = 5


def make_adapter(log=print):
    from api import webull_orders as wo
    cfg = dict(wo.load_config(None))
    os.makedirs(DIR, exist_ok=True)
    cfg["state_path"] = os.path.join(DIR, "orders_state.json")
    cfg["kill_file"] = os.path.join(DIR, "KILL")
    rails = dict(cfg.get("rails") or {})
    rails.update({"max_shares_per_leg": 1, "max_total_position_shares": 100000,
                  "daily_loss_limit_usd": 0, "one_open_position_per_leg": True})
    cfg["rails"] = rails
    cfg["other_book_states"] = [cfg.get("qqq_state_path") or wo.DEFAULT_STATE_PATH]
    ad = wo.OrderAdapter(config=cfg, log=log)
    mode, why = ad.effective_mode()
    if mode != wo.MODE_PAPER:
        raise SystemExit(f"latency_test: adapter mode is {mode} ({why}) -- PAPER only")
    return ad


def detail(ad, coid):
    """Webull's own record of one order: status, filled qty/price, place/fill epoch ms."""
    from api import webull_orders as wo
    mode = ad.effective_mode()[0]
    c = ad._client(mode)
    acct = ad._account_id(mode, c)
    o = ((wo._safe_response(c.order_v3.get_order_detail(acct, coid)) or {}).get("orders")
         or [{}])[0]
    return {"status": o.get("status"), "filled": float(o.get("filled_quantity") or 0),
            "price": o.get("filled_price"),
            "place_ms": int(o["place_time"]) if o.get("place_time") else None,
            "fill_ms": int(o["filled_time"]) if o.get("filled_time") else None}


def one_order(ad, sym, side, intent, sid, qty):
    t0 = time.time()
    rec = ad.place_stock_order(leg=LEG, signal_id=sid, symbol=sym, side=side, qty=qty,
                               intent=intent, order_type="MARKET")
    t_ack = time.time()
    coid = ((rec.get("parts") or [{}])[0].get("client_order_id")) or rec.get("client_order_id")
    row = {"sid": sid, "side": side, "ok": bool(rec.get("ok")), "reason": rec.get("reason"),
           "send": t0, "ack": t_ack, "coid": coid}
    if not row["ok"] or not coid:
        return row
    for _ in range(40):                     # up to ~10 s for the fill
        time.sleep(0.25)
        try:
            d = detail(ad, coid)
        except Exception as e:              # noqa: BLE001 - a read error is logged, retried
            row["read_err"] = repr(e)[:120]
            continue
        row.update(d)
        row["fill_seen"] = time.time()
        if d["status"] in ("FILLED", "REJECTED", "CANCELLED", "CANCELED", "FAILED"):
            break
    return row


def held(ad, sym):
    try:
        pos = ad.positions() or {}
        return float(((pos.get("broker") or {}).get(sym)) or 0)
    except Exception:                        # noqa: BLE001
        return None


def ms(a, b):
    return None if a is None or b is None else round((b - a) * 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--sym", default="SPY")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.sym.upper() == "QQQ":
        raise SystemExit("latency_test: QQQ is the book's symbol -- use SPY or another symbol")
    n = max(1, min(MAX_N, a.n))
    now = dt.datetime.now(ET)
    if not (dt.time(9, 30, 30) <= now.time() <= dt.time(15, 50)) or now.weekday() >= 5:
        raise SystemExit(f"latency_test: regular session only (09:30:30-15:50 ET), now {now:%a %H:%M:%S}")
    print(f"plan: {n} round trips, 1 share {a.sym} MARKET, PAPER, leg {LEG}")
    if a.dry_run:
        return
    ad = make_adapter()
    start = held(ad, a.sym)
    if start is None:
        raise SystemExit("latency_test: positions unreadable -- not sending")
    rows = []
    stamp = now.strftime("%Y%m%d%H%M%S")
    for i in range(n):
        b = one_order(ad, a.sym, "BUY", "OPEN", f"LATTEST-{stamp}-{i}-B", 1)
        rows.append(b)
        q = int(b.get("filled") or 0)
        if q <= 0:
            print("buy did not fill -- stopping", json.dumps(b, default=str))
            break
        s = one_order(ad, a.sym, "SELL", "CLOSE", f"LATTEST-{stamp}-{i}-S", q)
        rows.append(s)
        time.sleep(1.0)
    end = held(ad, a.sym)
    left = (end or 0) - (start or 0)
    if left > 0:
        print(f"flatten: {left:g} {a.sym} left from the test -- selling it")
        rows.append(one_order(ad, a.sym, "SELL", "CLOSE", f"LATTEST-{stamp}-F", int(left)))
    print(f"{'order':28} {'ok':3} {'send->ack':>9} {'send->wb_place':>14} {'wb_place->fill':>14} "
          f"{'send->fill(wb)':>14} {'send->seen':>10} price")
    tot = []
    for r in rows:
        wp = r.get("place_ms") / 1000 if r.get("place_ms") else None
        wf = r.get("fill_ms") / 1000 if r.get("fill_ms") else None
        sf = ms(r["send"], wf)
        if sf is not None:
            tot.append(sf)
        print(f"{r['sid']:28} {'Y' if r['ok'] else 'N':3} {ms(r['send'], r['ack']) or '-':>9} "
              f"{ms(r['send'], wp) or '-':>14} {ms(wp, wf) or '-':>14} {sf or '-':>14} "
              f"{ms(r['send'], r.get('fill_seen')) or '-':>10} {r.get('price') or r.get('reason')}")
    if tot:
        tot.sort()
        print(f"send->fill ms: median {tot[len(tot) // 2]}, max {tot[-1]} over {len(tot)} orders")
    with open(os.path.join(DIR, f"latency_{stamp}.json"), "w") as f:
        json.dump(rows, f, default=str, indent=1)
    end2 = held(ad, a.sym)
    print(f"position {a.sym}: start {start:g}, end {end2 if end2 is not None else '?'}")


if __name__ == "__main__":
    main()

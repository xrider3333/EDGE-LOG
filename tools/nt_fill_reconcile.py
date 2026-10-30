"""tools/nt_fill_reconcile.py -- B1 NT side: NinjaTrader DEMO fills vs the book's trades, after the close.

Read-only. No broker call: the two inputs are files the pipeline already writes.
  book   Firestore users/{uid}/paper_trades, the shadow round trips of the legs NinjaTrader trades
         (nt_legs(): NOISE_H_RF + ENGUQ_335 today), closed on `day`.
  broker C:\\EdgeLog\\fills.csv (tools/EdgeLogExport.cs): ExecutionId, Time (UTC), Account, Instrument,
         Action, Qty, Price, Commission, OrderId, SignalName. DEMO7240108 rows only - never 1810769.
Both become naive New York datetimes and go to tools/reconcile_core.reconcile (its docstring is the spec).

SIZES ARE DOLLARS PER POINT. reconcile_core prices a pair as (close - open) x shares, so a leg's
"shares" here are contracts x the contract's $/point: NOISE trades MNQ ($2/pt), round(size x 3)
contracts (EdgeLogNOISE Qty = 3, q = Math.Round(size * Qty)); ENGU-Q trades 1 NQ ($20/pt) per unit.
The book side is rounded the same way so a 3.58-unit day is the 11 contracts NinjaTrader sent.

INTENT comes from the signal name: NZ / EQ open; NZexit, NZstop, EQx, 'Exit on session close' and
'Close' close. A nameless or unknown row keeps its leg from the instrument (MNQ = NOISE, NQ = ENGU-Q).
Partial fills of one order (same OrderId) are one row at the share-weighted price.

  python tools/nt_fill_reconcile.py --day 2026-10-29           print the report
  python tools/nt_fill_reconcile.py --push                     today (after 17:00 ET), phone note if missing
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import reconcile_core as rc                               # noqa: E402
from api import paper_reconcile as pr                      # noqa: E402

NY, UTC = ZoneInfo("America/New_York"), dt.timezone.utc
FILLS_CSV = r"C:\EdgeLog\fills.csv"
STATE = r"C:\EdgeLog\nt_fill_reconcile.json"
DEMO = "DEMO7240108"
SHARED_KEY = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"     # a worktree has none
TOL_SEC = 90.0                    # NT stamps a fill at the broker's time; the book at the bar - 0-30 s apart
# leg family -> (instrument root, contracts per book unit, $ per point)
SPEC = {"NOISE": ("MNQ", 3, 2.0), "ENGUQ": ("NQ", 1, 20.0)}
BOOK_USD_PER_PT = 20.0            # paper_trades pnl_usd = points x $20 x size, NOISE included
CLOSE_SIGNALS =("NZEXIT", "NZSTOP", "EQX", "EXIT ON SESSION CLOSE", "CLOSE")


def nt_legs(day):
    """The legs NinjaTrader trades on `day`: whatever the NZ and EQ signal names map to."""
    return {pr.leg_from_signal(s, trade_date=day) for s in ("NZ", "EQ")}


def _family(leg):
    return "ENGUQ" if str(leg).startswith("ENGUQ") else "NOISE"


def _ny(ts_utc_text):
    return dt.datetime.fromisoformat(ts_utc_text).replace(tzinfo=UTC).astimezone(NY).replace(tzinfo=None)


def _leg_for(row, day):
    sig = (row.get("SignalName") or "").strip()
    leg = pr.leg_from_signal(sig, trade_date=day) if sig.upper()[:2] in ("NZ", "EQ") else None
    if leg:
        return leg
    root = (row.get("Instrument") or "").split(" ")[0].upper()
    for fam, (inst, _q, _m) in SPEC.items():
        if root == inst:
            return {l for l in nt_legs(day) if _family(l) == fam}.pop()
    return None


def nt_orders(day, fills_path=FILLS_CSV):
    """(orders, log_start) from fills.csv's demo rows, one row per OrderId."""
    by_order, stamps = {}, []
    with open(fills_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts = _ny(r["Time"])
            except (KeyError, ValueError):
                continue
            stamps.append(ts)
            if r.get("Account") != DEMO:
                continue
            leg = _leg_for(r, ts.date())
            qty, px = rc._f(r.get("Qty")), rc._f(r.get("Price"))
            if not leg or not qty or px is None:
                continue
            sig = (r.get("SignalName") or "").strip().upper()
            o = by_order.setdefault(r.get("OrderId") or r.get("ExecutionId"), {
                "ts": ts, "leg": leg, "intent": "CLOSE" if sig in CLOSE_SIGNALS else "OPEN",
                "side": (r.get("Action") or "").upper(), "qty": 0.0, "notional": 0.0,
                "ok": True, "signal_id": ""})
            o["qty"] += qty
            o["notional"] += qty * px
    orders = []
    for o in by_order.values():
        _inst, _q, mult = SPEC[_family(o["leg"])]
        orders.append({"ts": o["ts"], "leg": o["leg"], "intent": o["intent"], "side": o["side"],
                       "shares": o["qty"] * mult, "ok": True, "fill_px": o["notional"] / o["qty"],
                       "signal_id": ""})
    return orders, (min(stamps) if stamps else None)


def book_trades(rows, day):
    """Book round trips of the NinjaTrader legs from paper_trades docs (dicts)."""
    legs, out = nt_legs(day), []
    for x in rows:
        leg = x.get("leg")
        if leg not in legs or str(x.get("open")).lower() == "true":
            continue
        try:
            ent = dt.datetime.fromisoformat(x["entryIso"]).astimezone(NY).replace(tzinfo=None)
            ext = dt.datetime.fromisoformat(x["exitIso"]).astimezone(NY).replace(tzinfo=None)
        except (KeyError, TypeError, ValueError):
            continue
        _inst, q, mult = SPEC[_family(leg)]
        size = rc._f(x.get("size")) or 1.0
        contracts = max(1, round(size * q))
        pnl = rc._f(x.get("pnl_usd"))
        # the book prices every leg in NQ ($20/pt) x size; restate it at the contracts NinjaTrader sends
        pnl = None if pnl is None else pnl / (size * BOOK_USD_PER_PT) * contracts * mult
        out.append({"leg": leg, "side": "long" if str(x.get("side")) in ("1", "1.0", "long") else "short",
                    "shares": contracts * mult, "entry_ts": ent, "exit_ts": ext,
                    "entry_px": rc._f(x.get("entry_px")), "exit_px": rc._f(x.get("exit_px")),
                    "pnl": pnl})
    return out


def read_book(day, db=None):
    if db is None:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            key = next(k for k in (os.path.join(ROOT, "serviceAccount.json"), SHARED_KEY) if os.path.exists(k))
            firebase_admin.initialize_app(credentials.Certificate(key))
        db = firestore.client()
    from tools.paper_review_routine import UID
    col = db.collection("users").document(UID).collection("paper_trades")
    rows = []
    for d0 in (day - dt.timedelta(days=4), day):           # opens a few days back (ENGU-Q holds overnight)
        for snap in col.where("close_day", "==", d0.isoformat()).stream():
            rows.append(snap.to_dict())
    return rows


def run(day, rows, fills_path=FILLS_CSV):
    trades = book_trades(rows, day)
    orders, log_start = nt_orders(day, fills_path)
    return rc.reconcile(day, trades, orders, (), log_start=log_start, tol_sec=TOL_SEC)


def words(day, rep):
    """The one phone line: what the book made or lost on the trades NinjaTrader never filled."""
    miss = [x for x in rep.get("no_fill") or []]
    strays = rep.get("orphan_fills") or []
    parts = [f"{x['leg']} {x['which']} at {str(x['ts'])[11:16]}" for x in miss]
    parts += [f"stray {x['leg']} {x['intent'].lower()} at {str(x['ts'])[11:16]}" for x in strays]
    lead = "; ".join(parts[:3]) + (f" (+{len(parts) - 3} more)" if len(parts) > 3 else "")
    return f"NinjaTrader demo vs book {day:%m-%d}: {len(miss)} trade(s) not filled, {len(strays)} stray fill(s) - {lead}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", help="YYYY-MM-DD (default today, New York)")
    ap.add_argument("--push", action="store_true", help="phone note once a day when missing")
    a = ap.parse_args(argv)
    day = dt.date.fromisoformat(a.day) if a.day else dt.datetime.now(NY).date()
    rep = run(day, read_book(day))
    line = words(day, rep) if rep["status"] == "missing" else f"{day}: {rep['status']}"
    print(line)
    print(json.dumps({k: rep[k] for k in ("status", "book_usd", "broker_usd", "slippage_usd")}, default=str))
    if a.push and rep["status"] == "missing":
        try:
            st = json.load(open(STATE, encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        if st.get("pushed_day") != day.isoformat():
            from api import ntfy_push
            ntfy_push.push(line, title="NinjaTrader fills check", priority="high")
            st["pushed_day"] = day.isoformat()
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(st, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

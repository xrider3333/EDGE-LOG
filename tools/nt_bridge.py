# nt_bridge.py — CLI client for the EdgeLogBridge NinjaTrader 8 AddOn.
#
# The AddOn (tools/nt/EdgeLogBridge.cs) runs INSIDE NinjaTrader and serves a local JSON
# HTTP API on 127.0.0.1:8391 — reads (health/accounts/positions/orders/strategies/
# executions) plus two mutation endpoints (flatten, order). This script is the human/
# script-facing front door so we never have to hand-craft curl calls mid-session.
#
# SAFETY MODEL — three independent rails, all enforced inside the AddOn (not here):
#   L1  live account 1810769 is hard-refused in the AddOn's own code — no config can
#       re-enable it, short of editing and recompiling the .cs file.
#   L2  C:\EdgeLog\bridge.json is an allowlist — an account must be listed there before
#       ANY mutation (flatten/order) against it is accepted.
#   L3  orders_enabled must be true in that same bridge.json for /order to work at all;
#       flatten is gated by L1+L2 only, since flattening only ever reduces risk.
# This client can't bypass any of that — it just relays your call and prints the AddOn's
# 403 + reason when a rail blocks you. Reads are read-only by construction (GET only).
#
# HOW TO RUN
#   python tools/nt_bridge.py health
#   python tools/nt_bridge.py positions
#   python tools/nt_bridge.py executions --today
#   python tools/nt_bridge.py flatten --account Sim101 --yes
#   python tools/nt_bridge.py order --account Sim101 --instrument NQ --action BUY --qty 1 --yes
#
# Override the bridge URL (e.g. different port) with env EDGELOG_BRIDGE_URL.
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")


def _call(method, path, params=None, body=None):
    """One HTTP round-trip to the AddOn. Returns (status_code, parsed_json_or_None)."""
    url = BASE.rstrip("/") + path
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url += ("&" if "?" in url else "?") + qs
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        print(f"Bridge not reachable at {BASE} - is NinjaTrader running with "
              f"EdgeLogBridge compiled in? (F5 + restart NT)")
        sys.exit(2)


def _print_rows(rows, cols):
    """Minimal fixed-width table — no dependency on a third-party pretty-printer."""
    if not rows:
        print("(none)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def cmd_health(args):
    status, data = _call("GET", "/health")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"status={status} ok={data.get('ok')} version={data.get('version')}")
    print(f"started_utc={data.get('started_utc')}")
    print(f"accounts={data.get('accounts')}")
    print(f"orders_enabled={data.get('orders_enabled')} live_locked={data.get('live_locked')}")
    print(f"allowed_accounts={data.get('allowed_accounts')}")


def cmd_accounts(args):
    status, data = _call("GET", "/accounts")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    _print_rows(data.get("accounts", []), ["name", "cash", "realized", "live_locked"])


def cmd_positions(args):
    status, data = _call("GET", "/positions")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    _print_rows(data.get("positions", []), ["account", "instrument", "side", "qty", "avg_price"])


def cmd_orders(args):
    params = {"all": 1} if args.all else None
    status, data = _call("GET", "/orders", params=params)
    if args.json:
        print(json.dumps(data, indent=2))
        return
    _print_rows(data.get("orders", []),
                ["account", "order_id", "name", "instrument", "action", "type", "state",
                 "qty", "limit", "stop", "filled"])


def cmd_strategies(args):
    status, data = _call("GET", "/strategies")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    _print_rows(data.get("strategies", []), ["account", "name", "state", "instrument", "position"])


def cmd_executions(args):
    status, data = _call("GET", "/executions")
    rows = data.get("executions", [])
    if args.today:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = [r for r in rows if str(r.get("time_utc", "")).startswith(today)]
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    _print_rows(rows, ["account", "exec_id", "time_utc", "instrument", "side", "qty", "price"])


def cmd_connections(args):
    status, data = _call("GET", "/connections")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    _print_rows(data.get("connections", []), ["name", "status"])


def cmd_connect(args):
    # No --yes here on purpose: connecting is the same act as clicking the
    # Connections menu — it moves no money and holds no position. The AddOn only
    # dials names that already exist in the user's saved connection list.
    status, data = _call("POST", "/connect", params={"name": args.name})
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")
    if status != 200:
        sys.exit(1)


def cmd_strategy(args):
    # enable/disable a strategy INSTANCE by name. The AddOn resolves the instance
    # (account collections -> its own parked registry -> a walk of the grid rows)
    # and refuses via the same L1/L2 rails as every other mutation.
    if not args.yes:
        print(f"Would {args.action} strategy {args.name}. Re-run with --yes.")
        sys.exit(1)
    status, data = _call("POST", f"/strategy/{args.action}", params={"name": args.name})
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")
    if status != 200:
        sys.exit(1)


def cmd_shutdown(args):
    if not args.yes:
        print("Would cleanly shut down NinjaTrader. Re-run with --yes.")
        sys.exit(1)
    status, data = _call("POST", "/shutdown")
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")


def cmd_gridrows(args):
    status, data = _call("GET", "/reflect/gridrows")
    if args.json:
        print(json.dumps(data, indent=2)); return
    _print_rows(data.get("rows", []), ["row_type", "name", "account", "state", "strategy_reachable", "field"])


def cmd_cancel(args):
    if not args.yes:
        print(f"Would cancel order_id={args.order_id} on account={args.account}. Re-run with --yes.")
        sys.exit(1)
    status, data = _call("POST", "/cancel", params={"account": args.account, "order_id": args.order_id})
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")
    if status != 200:
        sys.exit(1)


def cmd_flatten(args):
    if not args.yes:
        print(f"Would flatten account={args.account}. Re-run with --yes to confirm.")
        sys.exit(1)
    status, data = _call("POST", "/flatten", params={"account": args.account})
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")
    if status != 200:
        sys.exit(1)


def cmd_order(args):
    body = {"account": args.account, "instrument": args.instrument, "action": args.action,
             "type": args.type, "qty": args.qty}
    if args.limit is not None:
        body["limit"] = args.limit
    if args.name:
        body["name"] = args.name
    if not args.yes:
        print(f"Would submit order: {json.dumps(body)}. Re-run with --yes to confirm.")
        sys.exit(1)
    status, data = _call("POST", "/order", body=body)
    print(json.dumps(data, indent=2) if args.json else f"status={status} {data}")
    if status != 200:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="CLI client for the EdgeLogBridge NT8 AddOn.")
    ap.add_argument("--json", action="store_true", help="print raw JSON instead of a table")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(func=cmd_health)
    sub.add_parser("accounts").set_defaults(func=cmd_accounts)
    sub.add_parser("positions").set_defaults(func=cmd_positions)
    sub.add_parser("strategies").set_defaults(func=cmd_strategies)
    sub.add_parser("connections").set_defaults(func=cmd_connections)

    p = sub.add_parser("connect")
    p.add_argument("--name", required=True, help="saved connection name, e.g. the NT demo")
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("orders")
    p.add_argument("--all", action="store_true", help="include filled/cancelled, not just working")
    p.set_defaults(func=cmd_orders)

    p = sub.add_parser("executions")
    p.add_argument("--today", action="store_true", help="filter to today's date (UTC)")
    p.set_defaults(func=cmd_executions)

    p = sub.add_parser("strategy")
    p.add_argument("action", choices=["enable", "disable"])
    p.add_argument("--name", required=True, help="strategy instance name, e.g. EdgeLogENGUQ1m")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_strategy)

    p = sub.add_parser("shutdown")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_shutdown)

    sub.add_parser("gridrows").set_defaults(func=cmd_gridrows)

    p = sub.add_parser("cancel")
    p.add_argument("--account", required=True)
    p.add_argument("--order_id", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("flatten")
    p.add_argument("--account", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_flatten)

    p = sub.add_parser("order")
    p.add_argument("--account", required=True)
    p.add_argument("--instrument", required=True)
    p.add_argument("--action", required=True, choices=["BUY", "SELL"])
    p.add_argument("--qty", required=True, type=int)
    p.add_argument("--type", default="MARKET", choices=["MARKET", "LIMIT"])
    p.add_argument("--limit", type=float, default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_order)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

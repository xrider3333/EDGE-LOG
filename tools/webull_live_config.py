r"""tools/webull_live_config.py -- the LIVE sizing + caps profile for BOTH config files (B4 + B5).

WHY (Webull live audit 2026-11-04, owner GO A, MANAGER #267/#268). The caps and the loss stop
live in TWO files that must agree: the executor's qqq_exec/config.json (share table, the
breaker that SELLS) and the order adapter's webull_orders/config.json rails (gate the OPENs).
Arming live with them out of step is a silent risk, so the LIVE profile is written to both
by this one tool and checked by it before arming.

THE OWNER'S SIZING RULE (11-04): 1 backtest contract = 1 share, base 1 share; the signal's size
multiplier applies EXACTLY (size 2.0 = 2 shares, KEEL kept as paper runs it, rounded to the
nearest share by api/qqq_exec._sized_shares, shares_wanted recorded). No size override and no
forced KEEL 1.0 -- that is already how the executor sizes, so B4 is this profile, not new code.
Caps 3 per leg / 3 total so a 2x tilt with KEEL fits. Only NOISE trades live: every other leg,
every DIP lot included, is 0 shares (0 = the executor's own silent skip). The live_legs
allowlist and the stock_last4 pin are the rails builder's (B3/B9); this tool only checks them.

  python tools/webull_live_config.py --check            # exit 1 if either file is off-profile
  python tools/webull_live_config.py --write --dry-run  # show what would change
  python tools/webull_live_config.py --write --yes      # back up both files, write the profile

Run on the box, after the close, while flat. Never touches the mode or the arm file.
"""
import argparse
import copy
import datetime as dt
import json
import os
import shutil
import sys

HOME = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog")
EXEC_CFG = os.path.join(HOME, "qqq_exec", "config.json")
ORDERS_CFG = os.path.join(HOME, "webull_orders", "config.json")

LIVE_LEGS = ["NOISE"]
BASE_SHARES = 1
MAX_PER_LEG = 3
MAX_TOTAL = 3
DAILY_LOSS_USD = 40


def _dip_legs():
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from api.qqq_exec import DIP_LEGS
        return list(DIP_LEGS)
    except Exception:
        return []


def live_exec(cfg):
    out = copy.deepcopy(cfg)
    shares = {k: 0 for k in (out.get("shares") or {})}
    shares.update({k: 0 for k in ("ORB", "ENGUQ", *_dip_legs())})
    shares.update({k: BASE_SHARES for k in LIVE_LEGS})
    out["shares"] = shares
    out["max_shares_per_leg"] = MAX_PER_LEG
    out["daily_loss_limit_usd"] = DAILY_LOSS_USD
    out["dip_max_total_shares"] = 0
    return out


def live_orders(cfg):
    out = copy.deepcopy(cfg)
    r = out.setdefault("rails", {})
    r["max_shares_per_leg"] = MAX_PER_LEG
    r["max_total_position_shares"] = MAX_TOTAL
    r["daily_loss_limit_usd"] = float(DAILY_LOSS_USD)
    r.setdefault("live_legs", list(LIVE_LEGS))
    return out


def problems(ex, od):
    p = []
    sh = ex.get("shares") or {}
    for leg, n in sh.items():
        want = BASE_SHARES if leg in LIVE_LEGS else 0
        if n != want:
            p.append(f"exec shares[{leg}] = {n}, LIVE profile {want}")
    for leg in ("ORB", "ENGUQ", *_dip_legs()):
        if leg not in sh:
            p.append(f"exec shares has no {leg} entry (the code default would size it)")
    if ex.get("max_shares_per_leg") != MAX_PER_LEG:
        p.append(f"exec max_shares_per_leg {ex.get('max_shares_per_leg')} != {MAX_PER_LEG}")
    if ex.get("daily_loss_limit_usd") != DAILY_LOSS_USD:
        p.append(f"exec daily_loss_limit_usd {ex.get('daily_loss_limit_usd')} != {DAILY_LOSS_USD}")
    r = od.get("rails") or {}
    if r.get("max_shares_per_leg") != MAX_PER_LEG:
        p.append(f"orders rails.max_shares_per_leg {r.get('max_shares_per_leg')} != {MAX_PER_LEG}")
    if r.get("max_total_position_shares") != MAX_TOTAL:
        p.append(f"orders rails.max_total_position_shares {r.get('max_total_position_shares')} != {MAX_TOTAL}")
    if float(r.get("daily_loss_limit_usd") or 0) != float(DAILY_LOSS_USD):
        p.append(f"orders rails.daily_loss_limit_usd {r.get('daily_loss_limit_usd')} != {DAILY_LOSS_USD}")
    if list(r.get("live_legs") or []) != LIVE_LEGS:
        p.append(f"orders rails.live_legs {r.get('live_legs')} != {LIVE_LEGS}")
    if not str((od.get("account") or {}).get("stock_last4") or "").strip():
        p.append("orders account.stock_last4 not set (LIVE account must be pinned by number)")
    return p


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, f"{path}.pre-live-{stamp}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--exec-config", default=EXEC_CFG)
    ap.add_argument("--orders-config", default=ORDERS_CFG)
    a = ap.parse_args(argv)
    ex, od = _load(a.exec_config), _load(a.orders_config)
    if a.write:
        nex, nod = live_exec(ex), live_orders(od)
        for name, old, new in (("exec", ex, nex), ("orders", od, nod)):
            for k in sorted(set(old) | set(new)):
                if old.get(k) != new.get(k):
                    print(f"{name}.{k}: {json.dumps(old.get(k))} -> {json.dumps(new.get(k))}")
        if a.yes and not a.dry_run:
            _write(a.exec_config, nex)
            _write(a.orders_config, nod)
            print("written (backups: *.pre-live-<stamp>)")
        ex, od = nex, nod
    p = problems(ex, od)
    for x in p:
        print("OFF-PROFILE:", x)
    print("LIVE PROFILE OK" if not p else f"{len(p)} problem(s)")
    return 0 if not p else 1


if __name__ == "__main__":
    sys.exit(main())

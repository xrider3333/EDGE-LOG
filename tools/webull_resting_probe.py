"""tools/webull_resting_probe.py -- one-off PAPER probe of Webull resting orders (owner GO
2026-09-29 via MANAGER inbox #32: "a stop and an OCO far from the price, cancelled at
once, while flat -- Webull PAPER account only, never touch login/PIN").

Answers, for the resting ORB stop/target gateway design (WEBULL_PAPER_TODO item 19: resting
ORB stops), what Webull's paper sandbox does with:
  S1  a BUY STOP_LOSS (buy-opening while flat) far ABOVE the price  -> accepted? status?
  S2  a SHORT STOP_LOSS far BELOW while S1 rests                     -> 417 box-order rule?
  S3  replace_order on S1's stop price                                -> supported?
  S4  cancel S1                                                       -> CANCELLED?
  S5  a SHORT STOP_LOSS alone (sell-opening while flat)               -> accepted?
  S6  a native OCO: BUY STOP_LOSS far above + BUY LIMIT far below     -> accepted?
  S7  cancel ONE OCO leg                                              -> sibling cancelled?
Every order is 1 share of QQQ, DAY, CORE session, priced ~8% away so it cannot trigger
or fill, and is cancelled within seconds. Nothing is ever left resting: a finally block
cancels every id this run placed and confirms each is terminal (exit 2 if not).

Refuses (sends nothing) unless: effective mode PAPER on the sandbox host; the live book
(qqq_exec state) has no open legs and no pending re-send; Webull shows no QQQ position
and no open QQQ order; it is 09:40-15:40 ET on a weekday; the run starts 75-150 s into a
5-minute bar (bar-close decisions happen in the first ~10 s of a bar); the QQQ 1m cache
is fresh. Aborts to cleanup if the live signal ledger changes or the bar clock passes
270 s. State is isolated under a temp dir (never the live adapter's state.json), no
token is created in the live token dir, and nothing printed carries keys, tokens,
account numbers or Webull request ids.

Run on the box:  set -a; . ~/edgelog/edgelog.env; set +a
                 cd ~/edgelog/EDGE-LOG && ~/edgelog/venv/bin/python <this file> [--send]
                 (a bare run is preflight only; --send places and cancels the orders)
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time

REPO = os.environ.get("EDGELOG_REPO") or os.getcwd()
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from api import webull_orders as WO  # noqa: E402
import logging  # noqa: E402

# the SDK can log a signed request (with its key headers) on an error: silence it all
_wl = logging.getLogger("webull")
_wl.addHandler(logging.NullHandler())
_wl.setLevel(logging.CRITICAL + 1)
_wl.propagate = False

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None

SYMBOL = "QQQ"
AWAY = 0.08            # every probe price sits 8% from the last close
BAR_START_MIN, BAR_START_MAX = 75, 150
BAR_DEADLINE = 270
TERMINAL = {"CANCELLED", "FILLED", "FAILED", "EXPIRED", "REJECTED"}

OUT = []


def _scrub(s):
    """Strip anything that could be an id, key or token: UUIDs (Webull request ids), long
    digit runs (account numbers), key/token header values, and any 16+ character run of
    key-like characters that is not this probe's own order id or an UPPER_SNAKE code."""
    s = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
               "<id>", str(s))
    s = re.sub(r"(?i)(x-app-key|x-access-token|x-signature|app_key|app_secret|access_token)\S*",
               "<secret>", s)
    s = re.sub(r"\b[A-Za-z0-9+/=_]{16,}\b",
               lambda m: m.group(0) if (m.group(0).startswith("QXPRB")
                                        or ("_" in m.group(0) and m.group(0).isupper()))
               else "<id>", s)
    return re.sub(r"\b\d{7,}\b", "<num>", s)


def _redact(s):
    return _scrub(s)[:400]


def say(msg):
    line = _redact(msg)
    OUT.append(line)
    print(line, flush=True)


def say_step(label, value):
    """One result line: the step label as written (this script's own constant, e.g.
    S2_short_stop_below_while_S1_rests -- scrubbing it turned every label into <id>),
    then the value, which alone goes through _redact."""
    line = f"{label}: {_redact(json.dumps(value, default=str))}"
    OUT.append(line)
    print(line, flush=True)


def now_et():
    return dt.datetime.now(tz=ET)


def bar_seconds(t=None):
    t = t or now_et()
    return (t.minute % 5) * 60 + t.second + t.microsecond / 1e6


def live_book_flat():
    d = os.environ.get("EDGELOG_QQQ_EXEC_DIR") or os.path.join(
        os.environ.get("EDGELOG_HOME", ""), "qqq_exec")
    with open(os.path.join(d, "state.json"), encoding="utf-8") as f:
        s = json.load(f)
    legs = s.get("legs") or {}
    resend = s.get("_broker_resend") or {}
    return (not legs and not resend), f"legs={len(legs)} resend={len(resend)}"


def signals_mtime():
    p = os.path.join(os.environ.get("EDGELOG_HOME", ""), "cloud_signal", "signals.csv")
    try:
        return os.path.getmtime(p)
    except OSError:
        return None


def last_close():
    p = os.path.join(os.environ.get("EDGELOG_HOME", ""), "ohlc", "QQQ_1m.csv")
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    r = rows[-1]
    age = time.time() - float(r["time"])
    return float(r["close"]), age


def items(resp):
    """Every per-order dict in a v3 response (combo-shaped or a list)."""
    r = WO._safe_response(resp)
    out = []
    if isinstance(r, dict):
        out.extend(WO._order_items(r))
        for k in ("data", "list", "orders_list"):
            v = r.get(k)
            if isinstance(v, list):
                for c in v:
                    out.extend(WO._order_items(c) or ([c] if isinstance(c, dict) else []))
    elif isinstance(r, list):
        for c in r:
            if isinstance(c, dict):
                out.extend(WO._order_items(c) or [c])
    return out


def summarize(it):
    keep = ("client_order_id", "combo_type", "order_type", "side", "status", "quantity",
            "filled_quantity", "stop_price", "limit_price", "time_in_force", "symbol")
    return {k: it.get(k) for k in keep if k in it}


def err_text(e):
    return f"{type(e).__name__}: {e}"


class Probe:
    def __init__(self, dry_run=False):
        self.dry = dry_run
        self.placed = []          # every client_order_id Webull accepted from this run
        self.maybe = []           # ids whose placement raised (normally refused)
        self.results = {}
        self.sig0 = signals_mtime()
        base = tempfile.mkdtemp(prefix="edgelog_resting_probe_")
        cfg = WO.load_config(os.path.join(base, "__no_such_config__.json"))
        cfg["mode"] = WO.MODE_PAPER
        cfg["paper_keys_path"] = WO.DEFAULT_PAPER_KEYS
        cfg["paper_token_dir"] = os.path.join(base, "paper_token")
        cfg["state_path"] = os.path.join(base, "state.json")
        cfg["kill_file"] = os.path.join(base, "KILL_never_created")
        cfg["arm_live_file"] = os.path.join(base, "ARM_LIVE_never_created")
        cfg["live_keys_path"] = os.path.join(base, "live_keys_never_created.json")
        cfg["live_token_dir"] = os.path.join(base, "live_token_never_created")
        cfg["rails"]["max_shares_per_leg"] = 1
        cfg["rails"]["max_total_position_shares"] = 1
        self.ad = WO.OrderAdapter(config=cfg, log=lambda m: None)
        mode, reason = self.ad.effective_mode()
        if mode != WO.MODE_PAPER:
            raise SystemExit(f"REFUSED: effective mode {mode} ({reason})")
        self.c = self.ad._client(WO.MODE_PAPER)
        host = self._host()
        if host != WO.SANDBOX_TRADE_HOST:
            raise SystemExit(f"REFUSED: client host {host!r} is not the sandbox host")
        self.acct = self.ad._account_id(WO.MODE_PAPER, self.c)
        tag = now_et().strftime("%H%M%S")
        self.coid = lambda step: f"QXPRB{tag}{step}"

    def _host(self):
        try:
            from webull.core.common import api_type as _t
            from webull.core.endpoint.resolver_endpoint_request import ResolveEndpointRequest
            api = self.c.order_v3.client
            return api._endpoint_resolver.resolve(ResolveEndpointRequest(api.get_region_id(), _t.DEFAULT))
        except Exception:
            return None

    # -- reads --
    def broker_qty(self):
        resp = self.c.account_v2.get_account_position(self.acct)
        return WO._positions_from_response(resp).get(SYMBOL, 0.0)

    def open_orders(self):
        try:
            resp = self.c.order_v3.get_order_open(self.acct, 50)
        except TypeError:
            resp = self.c.order_v3.get_order_open(self.acct)
        return [summarize(i) for i in items(resp) if str(i.get("symbol", SYMBOL)).upper() == SYMBOL]

    def detail(self, coid):
        try:
            resp = self.c.order_v3.get_order_detail(self.acct, coid)
            its = items(resp)
            return [summarize(i) for i in its] or [{"raw_keys": sorted((WO._safe_response(resp) or {}).keys())}]
        except Exception as e:
            return [{"error": err_text(e)}]

    def status(self, coid):
        for d in self.detail(coid):
            if d.get("client_order_id") in (None, coid) and d.get("status"):
                return str(d["status"]).upper()
        return None

    # -- writes --
    def order(self, coid, side, order_type, stop=None, limit=None, combo="NORMAL"):
        o = {"combo_type": combo, "client_order_id": coid, "symbol": SYMBOL,
             "instrument_type": "EQUITY", "market": "US", "order_type": order_type,
             "quantity": "1", "support_trading_session": "CORE", "side": side,
             "time_in_force": "DAY", "entrust_type": "QTY"}
        if stop is not None:
            o["stop_price"] = f"{stop:.2f}"
        if limit is not None:
            o["limit_price"] = f"{limit:.2f}"
        return o

    def place(self, orders, combo_id=None):
        coids = [o["client_order_id"] for o in orders]
        if self.dry:
            return {"ok": True, "dry_run": True}
        try:
            if combo_id:
                resp = self.c.order_v3.place_order(self.acct, orders, client_combo_order_id=combo_id)
            else:
                resp = self.c.order_v3.place_order(self.acct, orders)
            self.placed.extend(coids)
            return {"ok": True, "items": [summarize(i) for i in items(resp)]}
        except Exception as e:
            # a refusal normally means nothing rests, but a timeout might not: cleanup
            # looks these up too and cancels any it finds live
            self.maybe.extend(coids)
            return {"ok": False, "error": err_text(e)}

    def cancel(self, coid):
        if self.dry:
            return {"ok": True, "dry_run": True}
        try:
            self.c.order_v3.cancel_order(self.acct, coid)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": err_text(e)}

    def wait_terminal(self, coid, secs=8.0):
        t0 = time.time()
        st = None
        while time.time() - t0 < secs:
            st = self.status(coid)
            if st in TERMINAL:
                return st
            time.sleep(1.0)
        return st

    def guard(self, where):
        bs = bar_seconds()
        if bs > BAR_DEADLINE:
            raise RuntimeError(f"bar clock {bs:.0f}s past {BAR_DEADLINE}s before {where}")
        if signals_mtime() != self.sig0:
            raise RuntimeError(f"live signal ledger changed before {where}")
        flat, why = live_book_flat()
        if not flat:
            raise RuntimeError(f"live book not flat before {where} ({why})")

    # -- the probe --
    def preflight(self):
        t = now_et()
        if t.weekday() > 4 or not (dt.time(9, 40) <= t.time() < dt.time(15, 40)):
            raise SystemExit(f"REFUSED: {t:%a %H:%M} ET is outside 09:40-15:40 on a weekday")
        bs = bar_seconds(t)
        if not (BAR_START_MIN <= bs <= BAR_START_MAX):
            raise SystemExit(f"REFUSED: {bs:.0f}s into the 5m bar; start between "
                             f"{BAR_START_MIN}-{BAR_START_MAX}s")
        flat, why = live_book_flat()
        if not flat:
            raise SystemExit(f"REFUSED: live book not flat ({why})")
        q = self.broker_qty()
        if abs(q) > 1e-9:
            raise SystemExit(f"REFUSED: Webull shows a QQQ position ({q})")
        oo = self.open_orders()
        if oo:
            raise SystemExit(f"REFUSED: Webull shows {len(oo)} open QQQ order(s)")
        px, age = last_close()
        if age > 300:
            raise SystemExit(f"REFUSED: QQQ 1m cache is {age:.0f}s old")
        self.px = px
        self.up = round(px * (1 + AWAY), 2)
        self.up2 = round(px * (1 + AWAY + 0.01), 2)
        self.dn = round(px * (1 - AWAY), 2)
        say(f"preflight ok: {t:%H:%M:%S} ET, {bs:.0f}s into the bar, flat at Webull and in "
            f"the book, last close {px:.2f} -> probe prices above {self.up} / below {self.dn}")

    def run(self):
        R = self.results
        s1 = self.coid("S1")
        self.guard("S1")
        R["S1_buy_stop_above"] = self.place([self.order(s1, "BUY", "STOP_LOSS", stop=self.up)])
        time.sleep(1.5)
        R["S1_detail"] = self.detail(s1)
        R["open_after_S1"] = self.open_orders()

        s2 = self.coid("S2")
        self.guard("S2")
        R["S2_short_stop_below_while_S1_rests"] = self.place(
            [self.order(s2, "SHORT", "STOP_LOSS", stop=self.dn)])
        if R["S2_short_stop_below_while_S1_rests"].get("ok"):
            R["S2_cancel"] = self.cancel(s2)
            R["S2_final"] = self.wait_terminal(s2)

        self.guard("S3")
        if self.dry:
            R["S3_replace_stop"] = {"dry_run": True}
        else:
            try:
                self.c.order_v3.replace_order(self.acct, [{
                    "client_order_id": s1, "quantity": "1", "stop_price": f"{self.up2:.2f}"}])
                R["S3_replace_stop"] = {"ok": True}
            except Exception as e:
                R["S3_replace_stop"] = {"ok": False, "error": err_text(e)}
        time.sleep(1.5)
        R["S3_detail"] = self.detail(s1)

        R["S4_cancel"] = self.cancel(s1)
        R["S4_final"] = self.wait_terminal(s1)

        s5 = self.coid("S5")
        self.guard("S5")
        R["S5_short_stop_alone"] = self.place([self.order(s5, "SHORT", "STOP_LOSS", stop=self.dn)])
        time.sleep(1.5)
        R["S5_detail"] = self.detail(s5)
        R["S5_cancel"] = self.cancel(s5)
        R["S5_final"] = self.wait_terminal(s5)

        a, b, k = self.coid("A"), self.coid("B"), self.coid("K")
        self.guard("S6")
        R["S6_oco"] = self.place([self.order(a, "BUY", "STOP_LOSS", stop=self.up, combo="OCO"),
                                  self.order(b, "BUY", "LIMIT", limit=self.dn, combo="OCO")],
                                 combo_id=k)
        time.sleep(1.5)
        R["S6_detail_A"] = self.detail(a)
        R["S6_detail_B"] = self.detail(b)
        R["open_after_S6"] = self.open_orders()

        R["S7_cancel_A_only"] = self.cancel(a)
        R["S7_A_final"] = self.wait_terminal(a)
        time.sleep(2.0)
        R["S7_B_after_A_cancel"] = self.status(b)

    def cleanup(self):
        left = []
        if self.dry:
            return left
        for coid in dict.fromkeys(self.placed + self.maybe):
            st = self.status(coid)
            if st in TERMINAL:
                continue
            if st is None and coid in self.maybe and coid not in self.placed:
                continue          # refused at placement and Webull has no record of it
            self.cancel(coid)
            st = self.wait_terminal(coid, secs=10.0)
            if st not in TERMINAL:
                left.append((coid, st))
        self.results["cleanup_left_open"] = left
        if not self.dry:
            self.results["final_open_orders"] = self.open_orders()
            self.results["final_broker_qty"] = self.broker_qty()
        return left


def main():
    ap = argparse.ArgumentParser()
    # SENDING IS OPT-IN (2026-09-29 review): a bare run is the dry run -- preflight only.
    # The probe places and cancels about ten QQQ paper orders on the account the book
    # trades, so it sends only with --send (--dry-run is kept, and wins).
    ap.add_argument("--send", action="store_true",
                    help="really place (and cancel) the probe's paper orders; without it "
                         "the run is preflight only")
    ap.add_argument("--dry-run", action="store_true", help="preflight only, send nothing "
                                                          "(the default)")
    ap.add_argument("--out", default=os.path.join(os.environ.get("EDGELOG_HOME", "."),
                                                  "probe", "resting_probe_result.json"))
    args = ap.parse_args()
    dry = args.dry_run or not args.send
    p = Probe(dry_run=dry)
    p.preflight()
    if dry:
        say("dry run: preflight passed, nothing sent (pass --send to place the probe's "
            "paper orders)")
        return 0
    err = None
    try:
        p.run()
    except Exception as e:
        err = err_text(e)
        say(f"ABORTED to cleanup: {err}")
    finally:
        left = p.cleanup()
    p.results["aborted"] = err
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(json.dumps(json.loads(_redact_json(p.results)), indent=1))
    for k, v in p.results.items():
        say_step(k, v)
    if left:
        say(f"!!! LEFT OPEN: {left}")
        return 2
    return 0 if not err else 1


def _redact_json(obj):
    """JSON text of `obj` with every string value passed through _redact."""
    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [walk(v) for v in o]
        if isinstance(o, str):
            return _scrub(o)
        return o
    return json.dumps(walk(obj), default=str)


if __name__ == "__main__":
    sys.exit(main())

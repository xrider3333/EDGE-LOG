r"""tools/qqq_failover_sim.py -- offline two-host FAILOVER simulation for the QQQ shadow
adapter (api/qqq_exec.py, engine signal source) with its broker mirror armed in PAPER.

WHY THIS EXISTS (2026-09-14). The cross-host lease fix gates the broker SEND step, but the
adapter's memory -- open lots, the row-number engine_cursor into api/cloud_signal.py's
signals.csv, today's realized P&L / breaker, and api/webull_orders.py's own order/belief file --
all live on each host's local disk under EDGELOG_HOME. This driver asks what a takeover by a
second host (the planned Oracle Cloud VM) actually does with that, using the REAL tick() /
serve() / qqq_exec_thread() / OrderAdapter code paths.

SAFE TO RUN ANYTIME. Every path default is pointed at a fresh temp dir BEFORE the api modules
are imported; the Webull SDK client is a MagicMock over one in-memory QQQ position book shared by
both "hosts" (one real account); Firestore is a dict; ntfy, the nightly reprice subprocess and the
EOD summary are stubbed. Nothing touches C:\EdgeLog, Firestore, Webull or the owner's phone.

    python tools/qqq_failover_sim.py

SCENARIOS (result on main as of 2026-09-14 -- each prints GAP PRESENT until fixed; D and E
print "gap closed" since the LEASE PROTOCOL in api/qqq_exec.py, same day):
  A  PC dies holding an open lot -> VM takes over: VM skips the strategy EXIT (no lot), EOD
     flatten closes nothing, broker stays long overnight; boot reconcile halts every OPEN on
     every leg (and index.html never renders the published broker.halted field).
  B  a fresh ENTRY emitted during the ~90 s handover gap is absorbed by the new host's cursor
     seed and never acted on.
  C  a host that served before returns with its OLD state.json/cursor within 30 min of the other
     host's round trip -> re-trades it: duplicate BUY+SELL at the broker and a duplicate row in
     trades.csv. (Since 2026-09-14 both hosts send the SAME client_order_ids -- derived from the
     trade id, no longer from each host's wall clock -- but each host keeps its own order record
     and nothing checks the other's; whether Webull itself refuses a reused client_order_id is
     unverified, and this fake broker accepts it.)
  D  api/runner.py's fallback in-process thread (ensure_standalone() returns False on Linux
     whenever the systemd unit is not serving -- including when it is REFUSING on the lease)
     never calls _check_lease; it republishes the doc every tick and then reads itself as the
     lease holder.
  E  after both hosts have published and writes stop, the last writer reads "ours" and the
     other reads "stale": both pass _check_lease_for_broker.
  F  single host: an EXIT for an OLD trade closes whatever lot is open on that leg (EXIT rows
     carry no entry identity) -- the live ledger had exactly such a row on 2026-09-14 09:31 ET.
     CLOSED 2026-09-14: ENTRY/EXIT rows carry a trade id (api/trade_id.py) and the adapter
     closes a lot only with the EXIT carrying the same id; an id-less EXIT closes nothing. The
     check fails again if the stale EXIT closes the lot OR the trade's own EXIT no longer does.
"""
import csv
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import time
import types
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNAL_COLS = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
               "bar_source", "trade_id"]
qe = WO = NY = BASE = TID = None
DOC = {}
BROKER = {"QQQ": 0}
PLACED = []
ACTIVE = {"name": None}
MARK = {"px": 701.0}
HARNESS_ERRORS = []


def _expect(ok, what):
    """A harness self-check. A GAP verdict is only meaningful if the simulated broker really
    received the orders the scenario depends on -- when an adapter change stopped every send
    (2026-09-14: account selection by class), A and C silently flipped to "gap closed"."""
    if not ok:
        HARNESS_ERRORS.append(what)
        print(f"   !! HARNESS: {what}")


def _setup():
    global qe, WO, NY, BASE, TID
    BASE = tempfile.mkdtemp(prefix="qqq_failover_sim_")
    decoy = os.path.join(BASE, "_decoy")
    os.environ["EDGELOG_HOME"] = decoy
    os.environ["EDGELOG_QQQ_EXEC_DIR"] = os.path.join(decoy, "qqq_exec")
    for k in ["EDGELOG_WEBULL_ORDERS_CONFIG", "EDGELOG_WEBULL_PAPER_KEYS",
              "EDGELOG_WEBULL_PAPER_TOKEN_DIR", "EDGELOG_WEBULL_KEYS", "EDGELOG_WEBULL_TOKEN_DIR",
              "EDGELOG_WEBULL_ARM_LIVE", "EDGELOG_WEBULL_ORDERS_KILL", "EDGELOG_WEBULL_ORDERS_STATE",
              "EDGELOG_NQ_10S_PRIMARY", "EDGELOG_NQ_10S_FALLBACK"]:
        os.environ[k] = os.path.join(decoy, k.lower())
    os.environ.pop("NTFY_TOPIC", None)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from zoneinfo import ZoneInfo
    from api import qqq_exec as _qe
    from api import trade_id as _tid
    from api import webull_orders as _wo
    qe, WO, NY, TID = _qe, _wo, ZoneInfo("America/New_York"), _tid
    assert qe.OUT_DIR.startswith(BASE), f"refusing to run: adapter dir is {qe.OUT_DIR}"
    assert WO.DEFAULT_STATE_PATH.startswith(BASE), f"refusing to run: {WO.DEFAULT_STATE_PATH}"
    qe._notify = lambda *a, **k: None
    qe._maybe_run_reprice = lambda *a, **k: None
    qe._maybe_send_eod_summary = lambda *a, **k: None
    qe._engine_mark_price = lambda leg, log=print: (MARK["px"], "engine_sim")


# ── fake Firestore: the one shared users/{uid}/meta/qqq_exec doc ─────────────────────────
class _Snap:
    def __init__(self, d):
        self._d = d
        self.exists = d is not None

    def to_dict(self):
        return None if self._d is None else json.loads(json.dumps(self._d, default=str))


class _Ref:
    def collection(self, name):
        return _Coll()

    def get(self):
        return _Snap(DOC if DOC else None)

    def set(self, d, merge=False, timeout=None, retry=None):
        d = json.loads(json.dumps(d, default=str))
        if not merge:
            DOC.clear()
        DOC.update(d)


class _Coll:
    def document(self, name):
        return _Ref()


class FakeDb:
    def collection(self, name):
        return _Coll()


FDB = FakeDb()


# ── fake broker: one QQQ position book shared by both hosts (one real account) ──────────
def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


def _make_client():
    c = MagicMock()
    # account_class: api/webull_orders.py picks the stock account by class since 1ed627e;
    # without it every simulated order fails, and scenarios A and C pass vacuously.
    c.account_v2.get_account_list.return_value = _resp(
        {"data": [{"account_id": "PAPER1", "account_class": "INDIVIDUAL_MARGIN"}]})

    def place(account_id, orders):
        o = orders[0]
        q = int(o["quantity"])
        BROKER["QQQ"] += q if o["side"] == "BUY" else -q
        PLACED.append({"host": ACTIVE["name"], "coid": o["client_order_id"], "side": o["side"], "qty": q})
        return _resp({"status": "SUBMITTED"})

    def positions(account_id):
        n = BROKER["QQQ"]
        rows = [{"symbol": "QQQ", "quantity": abs(n), "side": "SHORT" if n < 0 else "LONG"}] if n else []
        return _resp({"data": rows})

    c.order_v3.place_order.side_effect = place
    c.account_v2.get_account_position.side_effect = positions
    return c


CLIENT = _make_client()


class Host:
    """One machine: its own adapter folder, signal ledger, state.json and order-adapter file."""

    def __init__(self, name):
        self.name = name
        self.root = os.path.join(BASE, name)
        self.q = os.path.join(self.root, "qqq_exec")
        self.cs = os.path.join(self.root, "cloud_signal")
        wo = os.path.join(self.root, "webull_orders")
        for d in (self.q, self.cs, wo):
            os.makedirs(d)
        keys = os.path.join(self.root, "webull_paper_keys.json")
        with open(keys, "w", encoding="utf-8") as f:
            json.dump({"app_key": "AK", "app_secret": "AS"}, f)
        cfg = WO.load_config(os.path.join(wo, "config.json"))
        cfg.update(mode="PAPER", state_path=os.path.join(wo, "state.json"), paper_keys_path=keys,
                   kill_file=os.path.join(wo, "KILL"), arm_live_file=os.path.join(wo, "ARM_LIVE"),
                   live_keys_path=os.path.join(self.root, "live_keys.json"))
        cfg["rails"] = dict(cfg["rails"], session_start="00:00", session_end="23:59")
        self.wo_cfg = cfg
        self.sig = os.path.join(self.cs, "signals.csv")
        self.hb = os.path.join(self.cs, "heartbeat.json")
        self.logs = []
        self.adapter = self.state = self.cfg = None

    def log(self, m):
        self.logs.append(str(m))

    def activate(self):
        ACTIVE["name"] = self.name
        qe.OUT_DIR = self.q
        qe.CONFIG_PATH = os.path.join(self.q, "config.json")
        qe.STATE_PATH = os.path.join(self.q, "state.json")
        qe.ORDERS_CSV = os.path.join(self.q, "orders.csv")
        qe.TRADES_CSV = os.path.join(self.q, "trades.csv")
        qe.BROKER_ORDERS_CSV = os.path.join(self.q, "broker_orders.csv")
        qe.SERVING_LOCK = os.path.join(self.q, "SERVING.lock")
        name = self.name
        qe._lease_host_id = lambda: name
        qe._ORDER_ADAPTER = self.adapter
        cs = types.SimpleNamespace(DEFAULT_PATHS={"signals_path": self.sig, "heartbeat_path": self.hb},
                                   read_bar_source=lambda paths=None: {})
        qe._cs_module = lambda: cs
        with open(self.hb, "w", encoding="utf-8") as f:
            json.dump({"ts": dt.datetime.now(NY).isoformat(), "ok": True, "note": "sim"}, f)

    def boot(self):
        """A fresh adapter PROCESS on this host -- what qqq_exec_thread does at start."""
        self.adapter = WO.OrderAdapter(config=self.wo_cfg, log=self.log)
        self.adapter._build_client = lambda m: CLIENT
        self.activate()
        qe._PROCESS["booted"] = False
        self.state = qe.load_state(log=self.log)
        self.cfg = qe.load_config(log=self.log)
        qe._reconcile_broker_at_boot(log=self.log)

    def tick(self, hhmm, day="2026-09-15", publish=True):
        self.activate()
        now = dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=NY)
        _cfg, self.state, doc = qe.tick(cfg=self.cfg, state=self.state, now=now, db=FDB,
                                        uid="uid1", log=self.log)
        if publish:
            _Ref().set(doc)
        return doc

    def emit(self, event, leg, side, ref, px, emitted_hhmm, day="2026-09-15", entry=None, no_id=False):
        """One signals.csv row as api/cloud_signal.py writes it. The trade id is built exactly
        as the engine builds it: from the ENTRY bar (`ref` on an ENTRY row, `entry` on an EXIT
        row, whose own `ref` is the exit bar). `no_id` writes an OLD row with no trade id."""
        new = not os.path.exists(self.sig)

        def _iso(t):
            return t if "T" in str(t) else (f"{day}T{t}:00-04:00" if t else "")

        ref_time = _iso(ref)
        tid = ""
        if not no_id and event in ("ENTRY", "EXIT"):
            tid = TID.make(leg, ref_time if event == "ENTRY" else _iso(entry), side) or ""
        with open(self.sig, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SIGNAL_COLS)
            if new:
                w.writeheader()
            w.writerow({"emitted_at": f"{day}T{emitted_hhmm}:05-04:00", "leg": leg, "event": event,
                        "side": side, "ref_time": ref_time, "ref_price": px, "shares": 140,
                        "reason": "", "bar_source": "webull", "trade_id": tid})

    def grep(self, needle):
        return [m for m in self.logs if needle in m]

    def rows(self, fname):
        p = os.path.join(self.q, fname)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))


def _reset():
    BROKER["QQQ"] = 0
    PLACED.clear()
    DOC.clear()
    MARK["px"] = 701.0


def _age_lease(sec):
    DOC["lease"]["leased_at"] = float(DOC["lease"]["leased_at"]) - sec


def _both(hosts, *a, **k):
    for h in hosts:
        h.emit(*a, **k)


def _header(t):
    print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)


def scenario_a():
    _header("A. PC dies holding an open lot; the cloud VM takes over")
    _reset()
    pc, vm = Host("owners-pc-A"), Host("oracle-vm-A")
    _both((pc, vm), "SEED", "ORB_R6", "", "", "", "09:20")
    pc.boot()
    pc.tick("09:30")
    _both((pc, vm), "ENTRY", "ORB_R6", "long", "09:55", 700.00, "10:00")
    pc.tick("10:00")
    print(f"PC opened: legs={list(pc.state['legs'])}  broker QQQ={BROKER['QQQ']}")
    _expect(BROKER["QQQ"] > 0, "A: the PC's OPEN never reached the simulated broker")
    vm.activate()
    print(f"VM standby, PC lease fresh -> may serve? {qe._check_lease(FDB, 'uid1', log=vm.log)}")
    _age_lease(100)
    print(f"VM after PC silent 100 s -> may serve? {qe._check_lease(FDB, 'uid1', log=vm.log)}")
    vm.boot()
    print(f"VM boot reconcile: halted={vm.adapter._halted} ({vm.adapter._halt_reason})")
    vm.tick("10:02")
    print(f"VM first tick: cursor={vm.state.get('engine_cursor')} legs={list(vm.state['legs'])}")
    _both((pc, vm), "EXIT", "ORB_R6", "long", "11:25", 704.00, "11:30", entry="09:55")
    vm.tick("11:30")
    skipped = vm.grep("no open shadow lot")
    print(f"VM on the strategy EXIT: {skipped}")
    MARK["px"] = 703.0
    vm.tick("15:59")
    orphan = BROKER["QQQ"]
    print(f"after VM EOD flatten: VM legs={list(vm.state['legs'])}  broker QQQ={orphan}")
    vm.emit("ENTRY", "NOISE_304", "long", "09:40", 702.00, "09:45", day="2026-09-16")
    vm.tick("09:45", day="2026-09-16")
    last = vm.rows("broker_orders.csv")[-1]
    print(f"next morning NOISE entry on VM: shadow legs={list(vm.state['legs'])}  broker row "
          f"mode={last['mode']} ({last['reason'][:50]}...)  doc broker.halted="
          f"{DOC.get('broker', {}).get('halted')}")
    return "A overnight orphan after takeover", bool(orphan and skipped and last["mode"] == "BLOCKED")


def scenario_b():
    _header("B. A signal emitted during the handover gap is never acted on")
    _reset()
    pc, vm = Host("owners-pc-B"), Host("oracle-vm-B")
    _both((pc, vm), "SEED", "NOISE_304", "", "", "", "09:20")
    pc.boot()
    pc.tick("09:30")
    _both((pc, vm), "ENTRY", "NOISE_304", "long", "09:40", 702.00, "09:45")
    _age_lease(100)
    vm.boot()
    vm.tick("09:46")
    print(f"VM first tick 1 min after a fresh ENTRY: cursor={vm.state.get('engine_cursor')} "
          f"legs={list(vm.state['legs'])} orders={len(vm.rows('orders.csv'))} broker QQQ={BROKER['QQQ']}")
    return "B gap signal swallowed", (not vm.state["legs"] and not vm.rows("orders.csv"))


def scenario_c():
    _header("C. A host returns with its OLD state within 30 min of the other host's trade")
    _reset()
    pc, vm = Host("owners-pc-C"), Host("oracle-vm-C")
    _both((pc, vm), "SEED", "ORB_R6", "", "", "", "09:20")
    pc.boot()
    pc.tick("09:30")
    _age_lease(100)
    vm.boot()
    vm.tick("09:37")
    _both((pc, vm), "ENTRY", "ORB_R6", "long", "12:55", 700.00, "13:00")
    vm.tick("13:00")
    _both((pc, vm), "EXIT", "ORB_R6", "long", "13:15", 703.00, "13:20", entry="12:55")
    vm.tick("13:20")
    print(f"VM traded the round trip: broker QQQ={BROKER['QQQ']}  VM trades={len(vm.rows('trades.csv'))}")
    _expect(len(PLACED) == 2, "C: the VM's round trip did not reach the simulated broker as BUY+SELL")
    _age_lease(100)
    time.sleep(1.1)
    pc.boot()
    print(f"PC boot: reconcile halted={pc.adapter._halted}  saved cursor={pc.state.get('engine_cursor')}")
    pc.tick("13:23")
    for p in PLACED:
        print(f"   {p['host']:<12} {p['side']:<5} {p['qty']}  client_order_id={p['coid']}")
    pc_trades = pc.rows("trades.csv")
    return "C duplicate round trip on return", (len(PLACED) == 4 and len(pc_trades) == 1)


def scenario_d():
    _header("D. The runner's fallback thread runs the book without checking the lease")
    _reset()
    DOC["lease"] = {"host_id": "owners-pc-D", "leased_at": time.time()}
    vm = Host("oracle-vm-D")
    vm.emit("SEED", "ORB_R6", "", "", "", "09:20")
    vm.boot()
    qe.serve(FDB, ["uid1"], log=vm.log)
    refused = bool(vm.grep("REFUSING"))
    real_name = qe.os.name
    qe.os.name = "posix"
    try:
        falls_back = qe.ensure_standalone(log=vm.log) is False
    finally:
        qe.os.name = real_name
    print(f"systemd unit serve() refused={refused}; runner boot on Linux then starts its own "
          f"in-process ticker={falls_back}")
    orig_should, orig_tick_sec = qe._should_publish, qe.TICK_SEC
    pub = {"yes": 0, "calls": 0}

    def counting_should(state, doc, force=False):
        r = orig_should(state, doc, force=force)
        pub["calls"] += 1
        pub["yes"] += 1 if r[0] else 0
        return r

    qe._should_publish = counting_should
    qe.TICK_SEC = 1.05
    stop, ticks = threading.Event(), {"n": 0}

    def on_tick(log=print):
        ticks["n"] += 1
        if ticks["n"] >= 4:
            stop.set()

    vm.activate()
    before = len(vm.grep("REFUSING"))
    watchdog = threading.Timer(15.0, stop.set)   # a loop that waits instead of ticking must not hang the sim
    watchdog.start()
    try:
        qe.qqq_exec_thread(FDB, ["uid1"], stop=stop, log=vm.log, on_tick=on_tick)
        time.sleep(1.5)
    finally:
        watchdog.cancel()
        qe._should_publish, qe.TICK_SEC = orig_should, orig_tick_sec
    saved = {}
    if os.path.exists(qe.STATE_PATH):   # a loop that refused never ticked, so never saved
        with open(qe.STATE_PATH, encoding="utf-8") as f:
            saved = json.load(f)
    print(f"in-process ticker: {ticks['n']} ticks, new refusals={len(vm.grep('REFUSING')) - before}, "
          f"doc changed on {pub['yes']}/{pub['calls']} ticks, doc lease holder now="
          f"{DOC.get('lease', {}).get('host_id')}, broker gate on last tick ok={saved.get('_broker_lease_ok')}")
    return "D fallback thread ignores lease", (falls_back and ticks["n"] >= 4
                                               and len(vm.grep("REFUSING")) == before
                                               and saved.get("_broker_lease_ok") is True)


def scenario_e():
    _header("E. Both hosts pass the broker gate once lease writes stop")
    DOC.clear()
    DOC["lease"] = {"host_id": "owners-pc-E", "leased_at": time.time() - 120}
    qe._lease_host_id = lambda: "owners-pc-E"
    a = qe._check_lease_for_broker(FDB, "uid1", log=lambda *_: None)
    qe._lease_host_id = lambda: "oracle-vm-E"
    b = qe._check_lease_for_broker(FDB, "uid1", log=lambda *_: None)
    print(f"last writer (PC) -> {a}\nother host (VM)  -> {b}")
    return "E both pass broker gate", (a[0] and b[0])


def scenario_f():
    _header("F. One host: an EXIT for an OLD trade closes TODAY's lot on that leg")
    _reset()
    h = Host("single-F")
    h.emit("SEED", "NOISE_304", "", "", "", "09:20")
    h.boot()
    h.tick("09:30")
    h.emit("ENTRY", "NOISE_304", "long", "09:55", 700.00, "10:00")
    h.tick("10:00")
    _expect([p["side"] for p in PLACED] == ["BUY"], "F: today's OPEN did not reach the simulated broker")
    # the live 2026-09-14 row: the EXIT of the 2026-09-03 trade that entered 11:00, exit bar 15:55
    h.emit("EXIT", "NOISE_304", "long", "2026-09-03T15:55:00-04:00", 717.61, "10:30",
           entry="2026-09-03T11:00:00-04:00")
    h.tick("10:30")
    # the same stale EXIT as an OLD row with no trade id at all
    h.emit("EXIT", "NOISE_304", "long", "2026-09-03T15:55:00-04:00", 717.61, "10:31", no_id=True)
    h.tick("10:31")
    stale_closed = (not h.state["legs"]) or bool(h.rows("trades.csv"))
    refused = {k: v for k, v in ((DOC.get("trade_ids") or {}).get("today") or {}).items() if v}
    print(f"after the stale EXITs: legs={list(h.state['legs'])} trades={len(h.rows('trades.csv'))} "
          f"broker orders={[(p['side'], p['qty']) for p in PLACED]} published trade_ids.today={refused}")
    h.emit("EXIT", "NOISE_304", "long", "11:25", 704.00, "11:30", entry="09:55")
    h.tick("11:30")
    t = (h.rows("trades.csv") or [{}])[-1]
    own_closed = not h.state["legs"] and t.get("exit_px") == "703.99"
    print(f"its own EXIT (same trade id): legs={list(h.state['legs'])} trade entry={t.get('entry_px')} "
          f"exit={t.get('exit_px')} pnl={t.get('pnl')} broker orders={[(p['side'], p['qty']) for p in PLACED]}")
    return "F stale EXIT closes today's lot", (stale_closed or not own_closed)


def main():
    _setup()
    results = [s() for s in (scenario_a, scenario_b, scenario_c, scenario_d, scenario_e, scenario_f)]
    _header("SUMMARY")
    for name, gap in results:
        print(f"  {'GAP PRESENT' if gap else 'gap closed '}  {name}")
    print(f"\n(temp dir: {BASE})")
    if HARNESS_ERRORS:
        print("\nHARNESS BROKEN -- the verdicts above cannot be trusted:")
        for e in HARNESS_ERRORS:
            print(f"  - {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()

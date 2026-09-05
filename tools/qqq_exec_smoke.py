"""Unit-style smoke test for api/qqq_exec.py -- the QQQ SHADOW execution adapter.

Feeds a synthetic C:\\EdgeLog-shaped fills.csv through the adapter in a TEMP directory
(never touches the real C:\\EdgeLog\\qqq_exec\\*) with a fixed price source (no network,
no Webull, no yfinance) and asserts:

  1. ORB entry (2 lots) -> partial exit (1 lot) -> Close (last lot) produces ONE closed
     round-trip in trades.csv, with a partial EXIT order recorded before the final one.
  2. ENGUQ entry left open (no matching exit fill in the file) survives ticks up to
     flat_by, then gets force-closed and tagged EOD at/after flat_by.
  3. NOISE entry fired AFTER last_entry is REFUSED -- no shadow lot opens, an ENTER
     order row is still logged with a REFUSED reason.
  4. Injecting a big adverse quote after ORB is open trips the daily-loss breaker:
     closes the lot tagged BREAKER, sets breaker_tripped, and further entries that day
     are ignored even inside the entry window.

Run: python tools/qqq_exec_smoke.py
"""
import csv
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def write_fills(path, rows):
    cols = ["ExecutionId", "Time", "Account", "Instrument", "Action", "Qty", "Price",
            "Commission", "OrderId", "SignalName"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(r)


def fixed_ratio(ratio):
    def _fn(log=print):
        return {"ratio": ratio, "source": "test-fixed", "at": "2026-09-02 09:00:00"}
    return _fn


def no_quote(log=print):
    return None


def bad_quote_factory(price):
    def _fn(symbol="QQQ", log=print):
        return (price, 1.0)
    return _fn


def main():
    tmp = tempfile.mkdtemp(prefix="qqq_exec_smoke_")
    try:
        qe.OUT_DIR = tmp
        qe.CONFIG_PATH = os.path.join(tmp, "config.json")
        qe.STATE_PATH = os.path.join(tmp, "state.json")
        qe.ORDERS_CSV = os.path.join(tmp, "orders.csv")
        qe.TRADES_CSV = os.path.join(tmp, "trades.csv")
        os.environ["NTFY_TOPIC"] = ""  # push best-effort no-ops, keep the log quiet-ish

        fills_path = os.path.join(tmp, "fills.csv")
        # RATIO = 30 (NQ points per QQQ dollar), so an NQ price of 30000 -> QQQ $1000.
        # Times are UTC naive (EdgeLogExport.cs writes ToUniversalTime); the adapter converts to ET.
        # Signal tags are the real NinjaTrader ones: ORB / EQ (ENGU-Q) / NZ (NOISE).
        rows = [
            # ORB entry: BUY 2 @ 30000 (long)
            ["e1", "2026-09-02 13:35:00", "Sim101", "NQ 12-26", "BUY", "2", "30000", "0", "o1", "ORB"],
            # ORB partial exit: SELL 1 @ 30030 (signal blank == generic reduce)
            ["e2", "2026-09-02 14:00:00", "Sim101", "NQ 12-26", "SELL", "1", "30030", "0", "o2", ""],
            # ORB final exit: SELL 1 @ 30060, tagged Close
            ["e3", "2026-09-02 14:15:00", "Sim101", "NQ 12-26", "SELL", "1", "30060", "0", "o3", "Close"],
            # ENGUQ entry, left open (no exit fill in this file at all)
            ["e4", "2026-09-02 14:30:00", "DEMO7240108", "NQ 12-26", "BUY", "1", "30000", "0", "o4", "EQ"],
            # NOISE entry AFTER last_entry (15:55) -- must be refused
            ["e5", "2026-09-02 19:57:00", "DEMO7240108", "MNQ 12-26", "BUY", "1", "30000", "0", "o5", "NZ"],
        ]
        write_fills(fills_path, rows)

        ratio_fn = fixed_ratio(30.0)

        print("Test 1+2+3: ORB round-trip (partial+full exit), ENGUQ left open, "
              "NOISE refused (after last_entry)")
        # Feed heartbeat so _check_feed doesn't block entries.
        os.makedirs(os.path.dirname(fills_path), exist_ok=True)
        import json, time as _t
        with open(os.path.join(tmp, "addon_heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump({"ts_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                      "accounts": 1, "seen": 1, "version": "2.1", "accts": {}}, f)

        now1 = datetime(2026, 9, 2, 10, 20)  # after e1/e2/e3, before e4 processed too (all in one batch is fine)
        cfg, state, doc = qe.tick(fills_path=fills_path, now=now1, quote_fn=no_quote,
                                  ratio_fn=ratio_fn)

        check("ORB round-trip closed (1 trade recorded)",
             os.path.exists(qe.TRADES_CSV) and _count_rows(qe.TRADES_CSV) == 1)
        if os.path.exists(qe.TRADES_CSV):
            with open(qe.TRADES_CSV, encoding="utf-8") as f:
                trow = list(csv.DictReader(f))[0]
            check("ORB trade leg == ORB", trow["leg"] == "ORB", trow["leg"])
            check("ORB trade shares == 5 (config default)", int(trow["shares"]) == 5, trow["shares"])
            # entry 30000/30=1000, partial exit 30030/30=1001, final exit 30060/30=1002
            # weighted exit isn't computed (single-lot model uses the LAST fill price
            # for the round-trip's exit_px) -- just assert direction is profitable long
            check("ORB trade pnl > 0 (long, price rose)", float(trow["pnl"]) > 0, trow["pnl"])

        orders = _read_rows(qe.ORDERS_CSV)
        orb_orders = [o for o in orders if o["leg"] == "ORB"]
        check("ORB produced ENTER + 2 EXIT orders", len(orb_orders) == 3,
             f"got {len(orb_orders)}: {[o['action'] for o in orb_orders]}")

        check("ENGUQ lot still open after tick", "ENGUQ" in state["legs"])

        noise_orders = [o for o in orders if o["leg"] == "NOISE"]
        check("NOISE entry logged as refused", len(noise_orders) == 1
             and "REFUSED" in noise_orders[0]["reason"], noise_orders)
        check("NOISE never opened a shadow lot", "NOISE" not in state["legs"])

        print("\nTest 4: flat_by force-closes ENGUQ, tags EOD")
        now2 = datetime(2026, 9, 2, 15, 59)  # past flat_by (15:58)
        cfg, state, doc = qe.tick(fills_path=fills_path, now=now2, quote_fn=no_quote,
                                  ratio_fn=ratio_fn, cfg=cfg, state=state)
        check("ENGUQ closed by flat_by", "ENGUQ" not in state["legs"])
        orders = _read_rows(qe.ORDERS_CSV)
        eod = [o for o in orders if o["leg"] == "ENGUQ" and o["reason"] == "EOD"]
        check("ENGUQ EXIT tagged EOD", len(eod) == 1, eod)

        print("\nTest 5: breaker trips on a big adverse mark, further entries ignored")
        # Fresh scenario: open a new ORB lot, then mark it deep underwater via quote_fn.
        rows2 = [
            ["b1", "2026-09-03 13:35:00", "Sim101", "NQ 12-26", "BUY", "2", "30000", "0", "b1", "ORB"],
        ]
        fills_path2 = os.path.join(tmp, "fills2.csv")
        write_fills(fills_path2, rows2)
        with open(os.path.join(tmp, "addon_heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump({"ts_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                      "accounts": 1, "seen": 1, "version": "2.1", "accts": {}}, f)
        cfg2 = qe.load_config()
        state2 = qe._default_state()
        now3 = datetime(2026, 9, 3, 9, 40)
        cfg2, state2, doc2 = qe.tick(fills_path=fills_path2, now=now3, quote_fn=no_quote,
                                     ratio_fn=ratio_fn, cfg=cfg2, state=state2)
        check("ORB lot opened for breaker test", "ORB" in state2["legs"])
        entry_px = state2["legs"]["ORB"]["entry_px"] if "ORB" in state2["legs"] else None

        # entry ~ $1000 (30000/30), 5 shares. A drop to $900 on 5 shares = $500 loss,
        # well past the default daily_loss_limit_usd of 150.
        bad_quote = bad_quote_factory(900.0)
        now4 = datetime(2026, 9, 3, 9, 41)
        cfg2, state2, doc2 = qe.tick(fills_path=fills_path2, now=now4, quote_fn=bad_quote,
                                     ratio_fn=ratio_fn, cfg=cfg2, state=state2)
        check("breaker tripped", state2.get("breaker_tripped") is True)
        check("ORB lot force-closed by breaker", "ORB" not in state2["legs"])
        orders2 = _read_rows(qe.ORDERS_CSV)
        breaker_rows = [o for o in orders2 if o["reason"] == "BREAKER"]
        check("BREAKER exit order logged", len(breaker_rows) >= 1, breaker_rows)

        # A same-day entry after the trip must be ignored.
        rows2b = rows2 + [
            ["b2", "2026-09-03 13:45:00", "Sim101", "MNQ 12-26", "BUY", "1", "30000", "0", "b2", "ORB"],
        ]
        write_fills(fills_path2, rows2b)
        now5 = datetime(2026, 9, 3, 9, 46)
        cfg2, state2, doc2 = qe.tick(fills_path=fills_path2, now=now5, quote_fn=no_quote,
                                     ratio_fn=ratio_fn, cfg=cfg2, state=state2)
        check("post-breaker entry ignored (breaker still tripped)",
             state2.get("breaker_tripped") is True and "ORB" not in state2["legs"])

        print("\nTest 7: NT PARITY -- a normal round-trip parity-checks OK")
        # Test 1's ORB round-trip already went through real routed entry+exit fills
        # (e1 entry, e2 partial exit, e3 final exit) with a FIXED ratio (30.0) the
        # whole way through, so it should reconcile cleanly.
        doc7 = qe._build_doc(cfg, state, False, 0.0)
        orb_trade = next((t for t in doc7["trades_all"]
                          if t["leg"] == "ORB" and t.get("nt_entry_exec_id") == "e1"),
                         None)
        check("ORB trade present in trades_all", orb_trade is not None)
        if orb_trade:
            check("ORB trade carries nt_entry_exec_id", orb_trade.get("nt_entry_exec_id") == "e1",
                 orb_trade.get("nt_entry_exec_id"))
            check("ORB trade carries nt_exit_exec_id", orb_trade.get("nt_exit_exec_id") == "e3",
                 orb_trade.get("nt_exit_exec_id"))
            check("ORB trade parity_ok is True", orb_trade.get("parity_ok") is True,
                 orb_trade)
        check("doc parity summary sees >=1 checked trade", doc7["parity"]["checked"] >= 1,
             doc7["parity"])

        print("\nTest 8: NT PARITY -- a ratio jump between entry and exit FAILS parity")
        fills_path3 = os.path.join(tmp, "fills3.csv")
        write_fills(fills_path3, [
            ["p1", "2026-09-04 13:35:00", "Sim101", "NQ 12-26", "BUY", "1", "30000", "0", "p1", "ORB"],
        ])
        with open(os.path.join(tmp, "addon_heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump({"ts_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                      "accounts": 1, "seen": 1, "version": "2.1", "accts": {}}, f)
        cfg3 = qe.load_config()
        state3 = qe._default_state()
        now_p1 = datetime(2026, 9, 4, 9, 40)
        cfg3, state3, doc3 = qe.tick(fills_path=fills_path3, now=now_p1, quote_fn=no_quote,
                                     ratio_fn=fixed_ratio(30.0), cfg=cfg3, state=state3)
        check("ORB lot opened for parity-fail test", "ORB" in state3["legs"])
        # ratio jumps hard (30 -> 45) before the exit fill lands -- expected_usd derived
        # from ratio_at_entry (30) will diverge sharply from the pnl actually realized
        # (priced off the post-jump ratio), which is exactly what should trip parity.
        write_fills(fills_path3, [
            ["p1", "2026-09-04 13:35:00", "Sim101", "NQ 12-26", "BUY", "1", "30000", "0", "p1", "ORB"],
            ["p2", "2026-09-04 13:50:00", "Sim101", "NQ 12-26", "SELL", "1", "30030", "0", "p2", "Close"],
        ])
        now_p2 = datetime(2026, 9, 4, 9, 41)
        cfg3, state3, doc3 = qe.tick(fills_path=fills_path3, now=now_p2, quote_fn=no_quote,
                                     ratio_fn=fixed_ratio(45.0), cfg=cfg3, state=state3)
        check("ORB lot closed for parity-fail test", "ORB" not in state3["legs"])
        orb_trade8 = next((t for t in doc3["trades_all"] if t["leg"] == "ORB"), None)
        check("parity-fail trade found", orb_trade8 is not None)
        if orb_trade8:
            check("ratio jump trade parity_ok is False", orb_trade8.get("parity_ok") is False,
                 orb_trade8)
            check("ratio jump trade has a parity_note", bool(orb_trade8.get("parity_note")),
                 orb_trade8)
        check("doc parity summary sees a failed trade", doc3["parity"]["failed"] >= 1, doc3["parity"])

        print("\nTest 9: FEED UPTIME -- injected stale ticks make a day invalid")
        state_feed = qe._default_state()
        # 09:25-09:59 open, mostly healthy...
        for m in range(0, 35, 5):
            qe._accumulate_feed_uptime(state_feed, datetime(2026, 9, 4, 9, 25 + m), stale=False)
        # ...then a long stale stretch (feed down) before recovering, well past 12:00.
        for total_min in range(0, 185, 5):
            hh = 10 + total_min // 60
            mm = total_min % 60
            qe._accumulate_feed_uptime(state_feed, datetime(2026, 9, 4, hh, mm), stale=True)
        feed_days9 = qe._build_feed_days(state_feed)
        d9 = next((d for d in feed_days9 if d["date"] == "2026-09-04"), None)
        check("2026-09-04 present in feed_days", d9 is not None)
        if d9:
            check("stale-heavy day marked invalid", d9["valid"] is False, d9)
            check("stale_min > 0 on the stale-heavy day", d9["stale_min"] > 0, d9)
            check("uptime_pct < 0.95 on the stale-heavy day", d9["uptime_pct"] < 0.95, d9)

        print("\nTest 10: RATIO HEALTH -- a stale calibration raises warn")
        state_ratio = qe._default_state()
        state_ratio["calib"] = {"ratio": 41.0, "source": "test", "at": "2026-09-04 09:00:00"}
        state_ratio["ratio_hist"] = [{"at": "2026-09-04 09:00:00", "ratio": 41.0, "source": "test"}]
        now10 = datetime(2026, 9, 4, 10, 0, 0)  # 60 min after calib, inside market window
        health10 = qe._build_ratio_health(state_ratio, now10)
        check("stale ratio (60 min old, in-window) raises warn", health10["warn"] is True, health10)
        check("stale ratio note is non-empty", bool(health10.get("note")), health10)

        fresh_state = qe._default_state()
        fresh_state["calib"] = {"ratio": 41.0, "source": "test", "at": "2026-09-04 09:55:00"}
        fresh_state["ratio_hist"] = [{"at": "2026-09-04 09:55:00", "ratio": 41.0, "source": "test"}]
        health_fresh = qe._build_ratio_health(fresh_state, now10)
        check("fresh ratio (5 min old) does not warn on age alone", health_fresh["warn"] is False,
             health_fresh)

        print("\nTest 6: mode refusal -- a non-SHADOW mode is forced back to SHADOW")
        bad_cfg_path = os.path.join(tmp, "config_bad.json")
        import json as _json
        with open(bad_cfg_path, "w") as f:
            _json.dump({**qe.DEFAULT_CONFIG, "mode": "LIVE"}, f)
        qe.CONFIG_PATH = bad_cfg_path
        forced = qe.load_config()
        check("mode='LIVE' refused and forced to SHADOW", forced["mode"] == "SHADOW", forced["mode"])

        print()
        if FAILURES:
            print(f"SMOKE TEST: {len(FAILURES)} FAILURE(S): {FAILURES}")
            sys.exit(1)
        print("SMOKE TEST: ALL PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _count_rows(path):
    return len(_read_rows(path))


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    main()

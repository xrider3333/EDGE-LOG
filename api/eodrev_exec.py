"""Strategy 23 (MISC_EODREV_1_2, run #511) basket executor for Webull PAPER.

OWNER GO 11-14 via MANAGER ("build for webull. curious if we get it to work"). Separate from
the QQQ legs (api/qqq_exec.py): its own process, its own order-adapter state file and rails,
its own ledger. It never touches QQQ. PAPER ONLY: it refuses to run unless the order adapter's
effective mode is PAPER (never LIVE, whatever the config says).

ONE DAY (python -m api.eodrev_exec run, started by a systemd timer at 15:27 ET Mon-Fri):
  15:29  read the signal file OPUS-HUNT writes by 15:24 (format agreed 11-14):
         <EODREV_DIR>/signal_YYYY-MM-DD.json  {"date","asof_et","status":"OK"|"SKIP","k",
         "long":[{"sym","px","score","exch"} x k],"short":[...], "panel_date", ...}
         missing / wrong date / malformed = no trade + phone alert; SKIP = no trade, no alert.
  15:30  6 MARKET entries: top k long (BUY), bottom k short (SHORT), equal dollars,
         usd_per_side / k per name, whole shares, sized from the file's 15:20 px.
         ONE-SIDED GUARD: a refused entry closes (or cancels, if unfilled) its rank pair
         (L_i <-> S_i); more than one refused = flatten the whole basket. One alert, reason
         in the ledger.
  15:59:00  MARKET exits for every entry still open (exit_at; Webull OpenAPI refuses MOC /
         AT_AUCTION for US equity with HTTP 417, so the exit is a plain MARKET order).
  15:59:35  FALLBACK: any exit that was refused, or that Webull's own record shows dead
         (REJECTED/CANCELLED/FAILED), is retried with a second MARKET order.
  16:05  read the fills, write the day's P&L to the ledger. DAILY LOSS RAIL: a day losing
         more than daily_loss_limit_usd blocks the NEXT session (the rail clears after it).
A kill file (<EODREV_DIR>/KILL) stops new entries; exits always go out.
"""
import argparse
import datetime as _dt
import json
import math
import os
import sys
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:          # pragma: no cover
    ZoneInfo = None

EODREV_DIR = os.environ.get("EDGELOG_EODREV_DIR", "/home/ubuntu/edgelog/eodrev")
STRATEGY = "MISC_EODREV_1_2"
RUN = 511
LEG_PREFIX = "EODREV"
TZ = "America/New_York"

DEFAULTS = {
    "enabled": True,
    "usd_per_side": 10000.0,
    "k": 3,
    "daily_loss_limit_usd": 400.0,
    "gate_at": "15:29",
    "enter_at": "15:30",
    "exit_at": "15:59:00",         # MARKET exit (MOC is refused by Webull OpenAPI, HTTP 417)
    "async_check_at": "15:31:00",  # one look for refusals that arrive AFTER acceptance
    "fallback_at": "15:59:35",
    "settle_at": "16:05",
    "max_px_drift": 0.05,          # skip a name whose file px is >5% off the ledger sanity band
    "min_price": 60.0,
    "require_probe_ok": True,      # no basket until a probe has passed (1-share MARKET exit filled)
}


def _et_now():
    return _dt.datetime.now(tz=ZoneInfo(TZ))


def _at(day, hhmm):
    parts = [int(x) for x in str(hhmm).split(":")] + [0]
    return _dt.datetime(day.year, day.month, day.day, parts[0], parts[1], parts[2],
                        tzinfo=ZoneInfo(TZ))


def paths(base=None):
    base = base or EODREV_DIR
    return {
        "dir": base,
        "config": os.path.join(base, "config.json"),
        "state": os.path.join(base, "exec_state.json"),
        "ledger": os.path.join(base, "ledger.jsonl"),
        "orders_state": os.path.join(base, "orders_state.json"),
        "kill": os.path.join(base, "KILL"),
        "log": os.path.join(base, "exec.log"),
    }


def load_cfg(p):
    cfg = dict(DEFAULTS)
    try:
        with open(p["config"], encoding="utf-8") as f:
            cfg.update(json.load(f) or {})
    except FileNotFoundError:
        pass
    return cfg


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def _append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# -- signal file -----------------------------------------------------------------------------
def signal_path(day, base=None):
    return os.path.join(base or EODREV_DIR, f"signal_{day.isoformat()}.json")


def read_signal(day, cfg, base=None):
    """(signal, None) to trade; (None, ("skip", why)) = no trade, no alert;
    (None, ("alert", why)) = no trade + phone alert."""
    path = signal_path(day, base)
    if not os.path.exists(path):
        return None, ("alert", f"signal file missing at gate ({os.path.basename(path)})")
    try:
        with open(path, encoding="utf-8") as f:
            sig = json.load(f)
    except Exception as e:
        return None, ("alert", f"signal file unreadable ({type(e).__name__}: {e})")
    if str(sig.get("date")) != day.isoformat():
        return None, ("alert", f"signal file date {sig.get('date')!r} is not today")
    if str(sig.get("status", "OK")).upper() == "SKIP":
        return None, ("skip", f"signal SKIP: {sig.get('reason') or 'no reason given'}")
    k = int(cfg.get("k") or 3)
    longs, shorts = sig.get("long") or [], sig.get("short") or []
    if len(longs) != k or len(shorts) != k:
        return None, ("alert", f"signal has {len(longs)} long / {len(shorts)} short, want {k}/{k}")
    syms = [str(x.get("sym") or "").upper() for x in longs + shorts]
    if not all(syms) or len(set(syms)) != len(syms):
        return None, ("alert", f"signal symbols missing or repeated: {syms}")
    if "QQQ" in syms:
        return None, ("alert", "signal names QQQ, which the QQQ book trades -- refused")
    for x in longs + shorts:
        try:
            px = float(x.get("px"))
        except (TypeError, ValueError):
            return None, ("alert", f"signal px unreadable for {x.get('sym')}")
        if not (px > 0 and math.isfinite(px)):
            return None, ("alert", f"signal px not positive for {x.get('sym')}")
    return sig, None


def plan_entries(sig, cfg, day):
    """[{leg, sym, side ('long'|'short'), qty, ref_px}] -- equal dollars per name."""
    k = int(cfg.get("k") or 3)
    per_name = float(cfg["usd_per_side"]) / k
    out = []
    for side, key, tag in (("long", "long", "L"), ("short", "short", "S")):
        for i, x in enumerate(sig[key], 1):
            px = float(x["px"])
            qty = int(per_name // px)
            if qty < 1:
                continue
            out.append({"leg": f"{LEG_PREFIX}_{tag}{i}", "sym": str(x["sym"]).upper(),
                        "side": side, "qty": qty, "ref_px": px,
                        "exch": x.get("exch"), "day": day.isoformat()})
    return out


def broker_side(side, intent):
    if intent == "OPEN":
        return "BUY" if side == "long" else "SHORT"
    return "SELL" if side == "long" else "BUY"


def signal_id(day, leg, what):
    return f"{LEG_PREFIX}-{day.strftime('%Y%m%d')}-{leg.split('_')[-1]}-{what}"


# -- rail ------------------------------------------------------------------------------------
def rail_blocks(state, day):
    until = state.get("rail_blocks_through")
    return bool(until) and day.isoformat() <= str(until)


def next_session(day):
    d = day + _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    return d


def day_pnl(entries):
    """Realised P&L of the day from booked fills; None when any fill price is missing."""
    tot = 0.0
    for e in entries:
        ep, xp, q = e.get("entry_fill"), e.get("exit_fill"), e.get("filled_qty") or 0
        if not q:
            continue
        if ep is None or xp is None:
            return None
        tot += (xp - ep) * q if e["side"] == "long" else (ep - xp) * q
    return tot


def _probe_side_ok(x):
    try:
        return bool(x.get("open_ok")) and float(x.get("exit_filled") or 0) >= 1
    except (TypeError, ValueError):
        return False


def probe_ok(p):
    """True once any probe run recorded, on both sides, the entry accepted AND a 1-share MARKET
    exit FILLED. (Old MOC-acceptance records no longer count: Webull refuses MOC, HTTP 417.)"""
    try:
        with open(os.path.join(p["dir"], "probe.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line).get("results") or []
                if len(r) == 2 and all(_probe_side_ok(x) for x in r):
                    return True
    except (FileNotFoundError, ValueError):
        pass
    return False


# -- broker ----------------------------------------------------------------------------------
def make_adapter(p, log=print):
    from api import webull_orders as wo
    cfg = wo.load_config(None)
    cfg = dict(cfg)
    cfg["state_path"] = p["orders_state"]
    cfg["kill_file"] = p["kill"]
    rails = dict(cfg.get("rails") or {})
    rails.update({"max_shares_per_leg": 2000, "max_total_position_shares": 100000,
                  "daily_loss_limit_usd": 0, "one_open_position_per_leg": True})
    cfg["rails"] = rails
    cfg["other_book_states"] = [cfg.get("qqq_state_path") or wo.DEFAULT_STATE_PATH]
    ad = wo.OrderAdapter(config=cfg, log=log)
    mode, why = ad.effective_mode()
    if mode != wo.MODE_PAPER:
        raise SystemExit(f"eodrev: order adapter mode is {mode} ({why}) -- PAPER only, not running")
    return ad


def send(ad, e, intent, day, order_type="MARKET", what=None, qty=None):
    sid = signal_id(day, e["leg"], what or intent[0])
    try:
        rec = ad.place_stock_order(leg=e["leg"], signal_id=sid, symbol=e["sym"],
                                   side=broker_side(e["side"], intent),
                                   qty=int(qty if qty is not None else e["qty"]),
                                   intent=intent, order_type=order_type)
    except Exception as ex:      # place_stock_order never raises by contract; belt and braces
        rec = {"ok": False, "reason": f"{type(ex).__name__}: {ex}"}
    rec = dict(rec or {})
    rec["_sid"] = sid
    return rec


def lookup(ad, rec):
    """{"status","filled","price"} of every part of a send, summed; None if unreadable."""
    try:
        mode = ad.effective_mode()[0]
        client = ad._client(mode)
        acct = ad._account_id(mode, client)
    except Exception:
        return None
    coids = [pt.get("client_order_id") for pt in (rec.get("parts") or []) if pt.get("client_order_id")]
    coids = coids or [rec.get("client_order_id")]
    filled, notional, statuses = 0.0, 0.0, []
    for c in coids:
        if not c:
            continue
        ans = ad._lookup_order(client, acct, c, detail=True)
        if not ans:
            return None
        statuses.append(ans["status"])
        q = float(ans.get("filled") or 0)
        if q and ans.get("price"):
            filled += q
            notional += q * float(ans["price"])
    if not statuses:
        return None
    st = statuses[0] if len(set(statuses)) == 1 else "MIXED:" + ",".join(statuses)
    return {"status": st, "filled": filled, "price": (notional / filled) if filled else None}


def pair_of(e, entries):
    """The basket's own pairing: long rank i <-> short rank i (EODREV_L2 <-> EODREV_S2)."""
    tag = e["leg"].split("_")[-1]
    want = f"{LEG_PREFIX}_{'S' if tag[0] == 'L' else 'L'}{tag[1:]}"
    return next((x for x in entries if x["leg"] == want), None)


LOOKUP_TRIES = 3
LOOKUP_PAUSE_S = 1.0


def lookup_retry(ad, rec, tries=None, pause=None):
    """lookup() with a bounded retry; None only when every try failed."""
    tries = LOOKUP_TRIES if tries is None else tries
    pause = LOOKUP_PAUSE_S if pause is None else pause
    for i in range(max(1, int(tries))):
        ans = lookup(ad, rec)
        if ans is not None:
            return ans
        if pause and i + 1 < tries:
            time.sleep(pause)
    return None


def _done(ans):
    return str((ans or {}).get("status")) in ("FILLED", "REJECTED", "CANCELLED", "CANCELED", "FAILED")


def unwind(ad, e, day, why, log=print):
    """Take an accepted entry back out. Cancel any unfilled remainder FIRST, re-read the order's
    final state, then MARKET-close only the quantity that actually filled. A lookup that fails
    every retry sends NOTHING (never close a position that may not exist): the leg is left for
    the exit / fallback and a note is returned for the alert. Returns a note string or None."""
    e["unwind_reason"] = why
    try:                                             # ALWAYS cancel the open first
        c = ad.cancel_order(e["open_rec"].get("client_order_id") or e["open_sid"]) or {}
    except Exception as ex:
        c = {"ok": False, "reason": f"{type(ex).__name__}: {ex}"}
    e["unwind_cancel"] = {"ok": bool(c.get("ok")), "reason": c.get("reason")}
    ans = lookup_retry(ad, e["open_rec"])            # final state AFTER the cancel (fill race)
    if ans is None:
        e["unwind"] = "lookup failed"
        return f"{e['sym']} {e['side']}: order lookup failed, left for the exit"
    filled = int(float(ans.get("filled") or 0))
    if filled <= 0:
        if _done(ans) or e["unwind_cancel"].get("ok"):
            e.update(unwind="cancelled", open_ok=False)
            log(f"[PICK6 #511] UNWIND cancel {e['leg']} {e['sym']}: {why}")
            return None
        e["unwind"] = "cancel unconfirmed"
        return f"{e['sym']} {e['side']}: cancel not confirmed, left for the exit"
    e["close_qty"] = filled
    rec = send(ad, e, "CLOSE", day, order_type="MARKET", what="UW", qty=filled)
    if rec.get("ok"):
        e.update(unwind="closed", exit_ok=True, exit_reason=rec.get("reason"), exit_rec=rec)
    else:                       # left WITHOUT exit_rec so the exit AND the fallback retry it
        e.update(unwind="close refused", unwind_rec=rec, unwind_close_reason=rec.get("reason"))
    log(f"[PICK6 #511] UNWIND close {filled} {e['leg']} {e['sym']}: "
        f"{'ok' if rec.get('ok') else 'REFUSED ' + str(rec.get('reason'))} ({why})")
    return None if rec.get("ok") else f"{e['sym']} unwind close refused, exit will retry"


def _notify(msg, title="PICK6 #511", log=print):
    try:
        from api import ntfy_push
        ntfy_push.push_result(msg, title=title, priority="high", timeout=4)
    except Exception as e:
        log(f"[PICK6 #511] phone push failed: {type(e).__name__}: {e}")


# -- the day ---------------------------------------------------------------------------------
def _sleep_until(t, now_fn, log):
    while True:
        left = (t - now_fn()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 20.0))


def run_day(p=None, now_fn=_et_now, adapter=None, log=print, notify=_notify, sleep=True):
    p = p or paths()
    os.makedirs(p["dir"], exist_ok=True)
    cfg = load_cfg(p)
    state = _load_json(p["state"], {})
    now = now_fn()
    day = now.date()
    if now.weekday() >= 5:
        return {"day": str(day), "result": "weekend"}
    wait = (lambda t: _sleep_until(t, now_fn, log)) if sleep else (lambda t: None)

    def finish(result, ledger_day=None, **extra):
        state["last_day"] = day.isoformat()
        state.pop("open_basket", None)
        _save_json(p["state"], state)
        ld = ledger_day or day.isoformat()
        rec = {"day": ld, "strategy": STRATEGY, "run": RUN, "result": result, **extra}
        _append(p["ledger"], rec)
        log(f"[PICK6 #511] {ld} {result}")
        return rec

    # RESUME after a restart: a saved basket that never finished is closed out first, so
    # nothing strands overnight. Runs even when disabled / killed (exits always go out).
    ob = state.get("open_basket")
    if ob and ob.get("entries") and state.get("last_day") != ob.get("day"):
        bday = ob["day"]
        same = bday == day.isoformat()
        notify(f"PICK6 #511: RESTART found an open basket from {bday} at {now:%H:%M:%S} ET - "
               f"{'resuming exits' if same else 'closing it NOW'}", log=log)
        entries = ob["entries"]
        ad = adapter or make_adapter(p, log=log)
        w = wait if same else (lambda t: None)
        if same:
            w(_at(day, cfg.get("exit_at") or DEFAULTS["exit_at"]))
        _close_out(ad, entries, day, cfg, w, notify, log)
        return _settle(ad, entries, day, cfg, state, w, notify,
                       lambda r, **x: finish(r, ledger_day=bday, resumed_on=day.isoformat(), **x),
                       one_sided=None, log=log)

    if not cfg.get("enabled", True):
        return {"day": str(day), "result": "disabled"}
    if state.get("last_day") == day.isoformat():
        return {"day": str(day), "result": "already ran today"}
    from api import market_calendar
    if not market_calendar.is_session(day):
        return {"day": str(day), "result": "holiday"}
    if market_calendar.session_close_et(day) != "16:00":
        return finish("no trade", why=f"early close {market_calendar.session_close_et(day)} ET - "
                                       f"no basket (exit window is after the close)")

    if rail_blocks(state, day):
        return finish("blocked by daily loss rail", rail=state.get("rail_reason"))
    if cfg.get("require_probe_ok", True) and not probe_ok(p):
        notify("PICK6 #511: no trade today - the 1-share MARKET exit probe has not passed", log=log)
        return finish("no trade", why="probe not passed")
    wait(_at(day, cfg["gate_at"]))
    sig, why = read_signal(day, cfg, p["dir"])
    if sig is None:
        kind, text = why
        if kind == "alert":
            notify(f"PICK6 #511: no trade today - {text}", log=log)
        return finish("no trade", why=text)
    if os.path.exists(p["kill"]):
        return finish("no trade", why="kill file present")
    plan = plan_entries(sig, cfg, day)
    ad = adapter or make_adapter(p, log=log)

    wait(_at(day, cfg["enter_at"]))
    entries = []
    for e in plan:
        rec = send(ad, e, "OPEN", day)
        e = dict(e, open_ok=bool(rec.get("ok")), open_sid=rec["_sid"],
                 open_reason=rec.get("reason"), open_rec=rec)
        entries.append(e)
        log(f"[PICK6 #511] OPEN {e['leg']} {e['side']} {e['qty']} {e['sym']}: "
            f"{'ok' if e['open_ok'] else 'REFUSED ' + str(e['open_reason'])}")
    one_sided = None
    handled = set()

    def guard(when):
        """Pair rule: one refused entry unwinds its rank pair; >1 refused flattens the basket."""
        nonlocal one_sided
        refused = [e for e in entries if not e["open_ok"] and e.get("unwind") != "cancelled"]
        new = [e for e in refused if e["leg"] not in handled]
        if not new:
            return
        handled.update(e["leg"] for e in new)
        why = "; ".join(f"{e['sym']} {e['side']}: {str(e['open_reason'])[:80]}" for e in new)
        live = [e for e in entries if e["open_ok"] and e.get("unwind") not in ("cancelled", "closed")]
        if len(refused) > 1:
            targets, action = live, "flattened the whole basket"
        else:
            pr = pair_of(new[0], entries)
            targets = [pr] if pr in live else []
            action = (f"unwound its pair {targets[0]['sym']} {targets[0]['side']}" if targets
                      else "no open pair to unwind")
        notes = [n for n in (unwind(ad, t, day, f"entry refused: {why}", log=log) for t in targets) if n]
        one_sided = one_sided or {"refused": [], "reason": "", "action": "", "unwound": []}
        one_sided["refused"] += [e["leg"] for e in new]
        one_sided["reason"] = "; ".join(x for x in (one_sided["reason"], why) if x)
        one_sided["action"] = action
        one_sided["unwound"] += [t["leg"] for t in targets]
        one_sided.setdefault("notes", []).extend(notes)
        one_sided.setdefault("when", []).append(when)
        notify((f"PICK6 #511: entries refused ({when}) - {why} -> {action}"
                + (" | " + "; ".join(notes) if notes else ""))[:400], log=log)

    guard("at entry")
    wait(_at(day, cfg.get("async_check_at") or "15:31:00"))
    for e in entries:                                 # ASYNC REJECT: refused after acceptance
        if not e["open_ok"] or e.get("unwind"):
            continue
        ans = lookup_retry(ad, e["open_rec"])
        if ans and str(ans["status"]) in ("REJECTED", "CANCELLED", "CANCELED", "FAILED") \
                and not float(ans.get("filled") or 0):
            e.update(open_ok=False, open_reason=f"async {ans['status']}")
    guard("15:31 check")
    _save_basket(p, state, day, entries)

    wait(_at(day, cfg.get("exit_at") or DEFAULTS["exit_at"]))
    _close_out(ad, entries, day, cfg, wait, notify, log)
    _save_basket(p, state, day, entries)
    return _settle(ad, entries, day, cfg, state, wait, notify, finish, sig=sig,
                   one_sided=one_sided, log=log)


def _save_basket(p, state, day, entries):
    """Persist the open basket so a restart can resume it (cleared when the day finishes)."""
    state["open_basket"] = {"day": day.isoformat(), "entries": entries}
    _save_json(p["state"], state)


def _close_out(ad, entries, day, cfg, wait, notify, log):
    """MARKET exit at exit_at, then the MARKET fallback at fallback_at."""
    for e in entries:
        if not e["open_ok"] or e.get("unwind") in ("cancelled", "closed") or e.get("exit_rec"):
            continue
        if e.get("unwind") in ("lookup failed", "cancel unconfirmed"):
            ans = lookup_retry(ad, e["open_rec"])     # reconcile: close only what really filled
            if ans is None:
                e["reconcile_failed"] = True
                notify(f"PICK6 #511: {e['sym']} {e['side']} order state unreadable at exit - "
                       f"NOTHING sent, check the account", log=log)
                continue
            q = int(float(ans.get("filled") or 0))
            if q <= 0:
                e.update(unwind="cancelled", open_ok=False)
                continue
            e["close_qty"] = q
        rec = send(ad, e, "CLOSE", day, order_type="MARKET", what="X", qty=e.get("close_qty"))
        e.update(exit_ok=bool(rec.get("ok")), exit_reason=rec.get("reason"), exit_rec=rec)
        log(f"[PICK6 #511] EXIT MARKET {e['leg']} {e['sym']}: "
            f"{'ok' if e['exit_ok'] else 'REFUSED ' + str(e['exit_reason'])}")

    wait(_at(day, cfg["fallback_at"]))
    for e in entries:
        if not e["open_ok"] or e.get("reconcile_failed") or e.get("fb_rec"):
            continue
        need = not e.get("exit_ok")
        if not need:
            ans = lookup(ad, e["exit_rec"])
            e["exit_check"] = ans
            need = bool(ans) and str(ans["status"]) in ("REJECTED", "CANCELLED", "CANCELED", "FAILED")
        if need:
            rec = send(ad, e, "CLOSE", day, order_type="MARKET", what="FB", qty=e.get("close_qty"))
            e.update(fb_ok=bool(rec.get("ok")), fb_reason=rec.get("reason"), fb_rec=rec)
            log(f"[PICK6 #511] FALLBACK MARKET {e['leg']} {e['sym']}: "
                f"{'ok' if e['fb_ok'] else 'REFUSED ' + str(e['fb_reason'])}")
            if not e["fb_ok"]:
                notify(f"PICK6 #511: {e['sym']} {e['side']} {e.get('close_qty') or e['qty']} NOT "
                       f"CLOSED - exit and fallback market both failed; position held overnight",
                       log=log)


def _settle(ad, entries, day, cfg, state, wait, notify, finish, sig=None, one_sided=None, log=print):
    wait(_at(day, cfg["settle_at"]))
    for e in entries:
        if not e["open_ok"]:
            continue
        o = lookup(ad, e["open_rec"]) or {}
        xr = e.get("fb_rec") or e.get("exit_rec")
        x = (lookup(ad, xr) if xr else None) or {}
        e.update(entry_fill=o.get("price"), filled_qty=o.get("filled") or 0,
                 exit_fill=x.get("price"), exit_status=x.get("status"),
                 exit_filled=x.get("filled"))
        if o.get("filled") and x.get("filled") is not None and x.get("filled") < o["filled"]:
            notify(f"PICK6 #511: {e['sym']} exit filled {x.get('filled')} of {o['filled']} "
                   f"({x.get('status')}) - check the account", log=log)
    pnl = day_pnl(entries)
    limit = float(cfg.get("daily_loss_limit_usd") or 0)
    if pnl is not None and limit and pnl <= -abs(limit):
        nxt = next_session(day)
        state["rail_blocks_through"] = nxt.isoformat()
        state["rail_reason"] = f"{day} lost {pnl:.2f} (limit {limit:.0f})"
        notify(f"PICK6 #511: day loss {pnl:.2f} hit the {limit:.0f} rail - no trade {nxt}", log=log)
    slim = [{k: v for k, v in e.items() if not k.endswith("_rec")} for e in entries]
    return finish("traded", pnl=pnl, entries=slim, signal_asof=(sig or {}).get("asof_et"),
                  panel_date=(sig or {}).get("panel_date"), one_sided=one_sided)


# -- Monday probe (MANAGER 11-14 items a + b) ------------------------------------------------
def run_probe(sym="AAPL", p=None, adapter=None, log=print, notify=None, wait_s=2.0, wait_tries=15):
    """1 share BUY + MARKET SELL, and 1 share SHORT + MARKET BUY on `sym`, PAPER only, in RTH.
    Passes only when both 1-share MARKET exits show FILLED on Webull's own record."""
    p = p or paths()
    os.makedirs(p["dir"], exist_ok=True)
    ad = adapter or make_adapter(p, log=log)
    day = _et_now().date()
    out = []
    for side in ("long", "short"):
        e = {"leg": f"{LEG_PREFIX}_P{'L' if side == 'long' else 'S'}", "sym": sym.upper(),
             "side": side, "qty": 1}
        o = send(ad, e, "OPEN", day, what="PO")
        m = send(ad, e, "CLOSE", day, order_type="MARKET", what="PX") if o.get("ok") else None
        ans = None
        if m is not None and m.get("ok"):
            for _ in range(int(wait_tries)):
                ans = lookup(ad, m)
                if ans and float(ans.get("filled") or 0) >= 1:
                    break
                time.sleep(wait_s)
        r = {"side": side, "open_ok": o.get("ok"), "open_reason": o.get("reason"),
             "exit_ok": (m or {}).get("ok"), "exit_reason": (m or {}).get("reason"),
             "exit_status": (ans or {}).get("status"), "exit_filled": (ans or {}).get("filled") or 0,
             "et": _et_now().strftime("%H:%M:%S")}
        out.append(r)
        log(f"[PICK6 #511 probe] {json.dumps(r, default=str)}")
    _append(os.path.join(p["dir"], "probe.jsonl"), {"day": str(day), "results": out})
    good = len(out) == 2 and all(_probe_side_ok(x) for x in out)
    (notify or _notify)(("PICK6 #511 probe PASSED: " if good else "PICK6 #511 probe FAILED: ") + "; ".join(
        f"{x['side']} open {'ok' if x.get('open_ok') else x.get('open_reason')}, "
        f"exit {('filled ' + str(x.get('exit_filled'))) if _probe_side_ok(x) else (x.get('exit_reason') or x.get('exit_status'))}" for x in out)[:400], log=log)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run", "probe", "check"))
    ap.add_argument("--sym", default="AAPL")
    ap.add_argument("--date", help="check: parse this day's signal file only")
    a = ap.parse_args(argv)
    p = paths()
    logf = open(p["log"], "a", encoding="utf-8") if os.path.isdir(p["dir"]) else None

    def log(msg):
        line = f"{_et_now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    if a.cmd == "check":
        day = _dt.date.fromisoformat(a.date) if a.date else _et_now().date()
        cfg = load_cfg(p)
        sig, why = read_signal(day, cfg, p["dir"])
        print(json.dumps({"why": why, "plan": plan_entries(sig, cfg, day) if sig else None}, indent=1))
        return 0
    if a.cmd == "probe":
        run_probe(a.sym, p, log=log)
        return 0
    print(json.dumps(run_day(p, log=log), default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

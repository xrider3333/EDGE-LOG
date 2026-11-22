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
  15:59:40  PREP: read every open entry's filled qty in parallel AND pre-build its exit order
         (symbol, side, qty, client_order_id, MARKET, DAY, CORE) -- unreadable = one retry at exit.
  15:59:50  the pre-built MARKET exits all go IN PARALLEL (exit_at; Webull OpenAPI refuses MOC /
         AT_AUCTION for US equity with HTTP 417). The adapter lock is let go for the HTTP call
         (wire_unlocked) so the six sends are on the wire together.
  15:59:54  FALLBACK for anything not FILLED: read the exit's status + filled qty; working /
         partial = cancel, confirm by reading; refused or dead = straight on. Then a NEW id
         (-FB) for min(close_qty - filled, live broker position) -- position unreadable or a
         cancel unconfirmed = alert, nothing sent. HARD CAP: nothing is sent at/after 15:59:59.5.
  16:00:05  AFTER CLOSE: read positions; a leftover from these legs = phone alert first, then
         an EXTENDED-HOURS LIMIT flatten (session ALL), marketable +/-0.3% off the last price.
         Prep >= exit (or any bad order of the three times) = alert + safe default times.
  16:05  re-check positions (still held = alert), read the fills, write the day's P&L to the ledger. DAILY LOSS RAIL: a day losing
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
    "prep_at": "15:59:40",         # read filled qty + pre-build every exit order
    "exit_at": "15:59:50",         # MARKET exits, all in parallel (MOC refused by Webull, HTTP 417)
    "async_check_at": "15:31:00",  # one look for refusals that arrive AFTER acceptance
    "fallback_at": "15:59:54",
    "flatten_at": "16:00:05",      # after the close: leftover -> alert + extended-hours LIMIT
    "settle_at": "16:05",
    "max_px_drift": 0.05,          # skip a name whose file px is >5% off the ledger sanity band
    "min_price": 60.0,
    "require_probe_ok": True,      # no basket until a probe has passed (1-share MARKET exit filled)
}


def _et_now():
    return _dt.datetime.now(tz=ZoneInfo(TZ))


def _at(day, hhmm):
    parts = str(hhmm).split(":") + ["0"]
    sec = float(parts[2])
    return _dt.datetime(day.year, day.month, day.day, int(parts[0]), int(parts[1]), int(sec),
                        int(round((sec - int(sec)) * 1e6)), tzinfo=ZoneInfo(TZ))


HARD_CAP = "15:59:59.5"           # nothing is SENT at or after this (fallback / probe)
SAFE_TIMES = {"prep_at": "15:59:40", "exit_at": "15:59:50", "fallback_at": "15:59:54",
              "flatten_at": "16:00:05"}
CONFIRM_PAUSE_S = 0.25            # between the cancel-confirm reads (fits before HARD_CAP)
FLATTEN_PCT = 0.003               # after-close LIMIT this far through the last price


def _secs(hhmm):
    parts = str(hhmm).split(":") + ["0"]
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def exit_times(cfg, notify=None, log=print):
    """prep_at < exit_at < fallback_at < HARD_CAP, all after 15:50, and flatten_at after the
    16:00 close (and before 16:05 settle) -- else one alert and the SAFE defaults (a pinned
    prep_at >= exit_at would read qty AFTER the exits went; a pre-16:00 flatten_at would
    silently skip the after-close check)."""
    vals = {k: str(cfg.get(k) or DEFAULTS[k]) for k in SAFE_TIMES}
    try:
        s = [_secs(vals[k]) for k in ("prep_at", "exit_at", "fallback_at", "flatten_at")]
        ok = (_secs("15:50") <= s[0] < s[1] < s[2] < _secs(HARD_CAP)
              and _secs("16:00") < s[3] < _secs(cfg.get("settle_at") or DEFAULTS["settle_at"]))
    except (TypeError, ValueError, IndexError):
        ok = False
    if ok:
        return vals
    msg = (f"PICK6 #511: exit times refused (prep {vals['prep_at']}, exit {vals['exit_at']}, "
           f"fallback {vals['fallback_at']}, flatten {vals['flatten_at']}: need prep < exit < "
           f"fallback < {HARD_CAP} and 16:00 < flatten < settle) - using "
           f"{SAFE_TIMES['prep_at']} / {SAFE_TIMES['exit_at']} / {SAFE_TIMES['fallback_at']} / "
           f"{SAFE_TIMES['flatten_at']}")
    if notify:
        notify(msg, log=log)
    else:
        log(msg)
    return dict(SAFE_TIMES)


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


def run_day(p=None, now_fn=_et_now, adapter=None, log=print, notify=_notify, sleep=True,
            resume_only=False):
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
        legs = open_legs(ob["entries"])
        if same and legs and now >= _at(day, RESUME_UNTIL):
            # verifier 11-20: a same-day restart after the 16:00 close never sends market
            # exits -- same rule as --resume-only: one HIGH line, no order, basket kept
            notify(f"PICK6 #511: restart at {now:%H:%M} ET after 16:00 with {len(legs)} basket "
                   f"legs still open - NO order sent, check the account", log=log)
            return {"day": str(day), "result": "restart after 16:00, alert only",
                    "open_legs": len(legs)}
        notify(f"PICK6 #511: RESTART found an open basket from {bday} at {now:%H:%M:%S} ET - "
               f"{'resuming exits' if same else 'closing it NOW'}", log=log)
        entries = ob["entries"]
        ad = adapter or make_adapter(p, log=log)
        w = wait if same else (lambda t: None)
        _close_out(ad, entries, day, cfg, w, notify, log, now_fn=now_fn)
        return _settle(ad, entries, day, cfg, state, w, notify,
                       lambda r, **x: finish(r, ledger_day=bday, resumed_on=day.isoformat(), **x),
                       one_sided=None, log=log, now_fn=now_fn)

    if resume_only:                                   # --resume-only: never a fresh entry
        return {"day": str(day), "result": "resume-only: nothing to resume"}
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
    # ENTRY GUARD (MANAGER 11-20): only ever blocks an ENTRY -- exits / resume untouched.
    # Today's basket already saved = this day already entered; after 15:50 ET = too late
    # for the 15:59 exit window. One alert line; the saved basket is left as it is.
    late = now_fn() > _at(day, ENTRY_CUTOFF)
    ob_today = (state.get("open_basket") or {}).get("day") == day.isoformat()
    if ob_today or late:
        why = ("today's basket is already saved - no second entry" if ob_today else
               f"now is past {ENTRY_CUTOFF} ET - too late to enter")
        notify(f"PICK6 #511: entry refused - {why}", log=log)
        if ob_today:
            return {"day": str(day), "result": "entry refused", "why": why}
        return finish("entry refused", why=why)
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

    _save_basket(p, state, day, entries)             # at once: a crash before 15:31 must not lose it
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

    _close_out(ad, entries, day, cfg, wait, notify, log, now_fn=now_fn)
    _save_basket(p, state, day, entries)
    return _settle(ad, entries, day, cfg, state, wait, notify, finish, sig=sig,
                   one_sided=one_sided, log=log, now_fn=now_fn)


# -- restart hook (edgelog-eodrev-resume.service at boot, edgelog-eodrev-alert.service) -----
RESUME_FROM = "15:27"
ENTRY_CUTOFF = "15:50"
RESUME_UNTIL = "16:00"


def open_legs(entries):
    """Basket legs that hold (or may hold) a position no exit has been sent for."""
    return [e for e in entries or () if e.get("open_ok")
            and e.get("unwind") not in ("cancelled", "closed")
            and not e.get("exit_ok") and not e.get("fb_ok")]


def _unfinished_basket(state):
    ob = state.get("open_basket") or {}
    if not ob.get("entries") or state.get("last_day") == ob.get("day"):
        return None
    return ob


def resume_only(p=None, now_fn=_et_now, adapter=None, log=print, notify=_notify, sleep=True):
    """`run --resume-only` (the boot unit): a no-op unless TODAY's saved basket has open
    legs and now is 15:27-16:00 ET -- then run_day's resume branch closes it (15:59 exits,
    filled qty only). Never a fresh entry. After 16:00 with legs still open: one HIGH phone
    line, no order."""
    p = p or paths()
    state = _load_json(p["state"], {})
    now = now_fn()
    day = now.date()
    ob = _unfinished_basket(state)
    legs = open_legs((ob or {}).get("entries"))
    if not ob or ob.get("day") != day.isoformat() or not legs:
        return {"day": str(day), "result": "resume-only: nothing to resume"}
    if now < _at(day, RESUME_FROM):
        return {"day": str(day), "result": "resume-only: before 15:27, nothing to do"}
    if now >= _at(day, RESUME_UNTIL):
        notify(f"PICK6 #511: box restarted at {now:%H:%M} ET after 16:00 with {len(legs)} basket "
               f"legs still open - NO order sent, check the account", log=log)
        return {"day": str(day), "result": "resume-only: after 16:00, alert only",
                "open_legs": len(legs)}
    return run_day(p, now_fn=now_fn, adapter=adapter, log=log, notify=notify, sleep=sleep,
                   resume_only=True)


def alert_failed(p=None, now_fn=_et_now, log=print, notify=_notify):
    """OnFailure= hook (edgelog-eodrev-alert.service): one HIGH phone line, never an order."""
    p = p or paths()
    try:
        ob = _unfinished_basket(_load_json(p["state"], {}))
        n = len(open_legs((ob or {}).get("entries")))
    except Exception:
        n = "?"
    msg = f"PICK6 unit failed at {now_fn():%H:%M}, basket {n} legs open"
    notify(msg, log=log)
    return {"result": "alert", "msg": msg}


def _save_basket(p, state, day, entries):
    """Persist the open basket so a restart can resume it (cleared when the day finishes)."""
    state["open_basket"] = {"day": day.isoformat(), "entries": entries}
    _save_json(p["state"], state)


EXIT_POOL = 6            # one worker per basket name (k=3 -> 6 legs)
CANCEL_TRIES = 3         # reads after a working exit's cancel, LOOKUP_PAUSE_S apart
DEAD = ("REJECTED", "CANCELLED", "CANCELED", "FAILED")


def _pool_each(fn, items):
    """Run fn(item) for every item on a small thread pool and wait for all of them. Each
    worker writes only its own entry dict. An exception in one worker never stops the rest;
    it is re-raised after all have finished."""
    items = list(items)
    if not items:
        return
    import concurrent.futures as cf
    errs = []
    with cf.ThreadPoolExecutor(max_workers=min(EXIT_POOL, len(items)),
                               thread_name_prefix="pick6-exit") as pool:
        for f in [pool.submit(fn, x) for x in items]:
            try:
                f.result()
            except Exception as ex:      # pragma: no cover - workers catch their own errors
                errs.append(ex)
    if errs:
        raise errs[0]


def _exit_due(e):
    return e["open_ok"] and e.get("unwind") not in ("cancelled", "closed") and not e.get("exit_rec")


def _read_close_qty(ad, e, tries=None):
    """Set e["close_qty"] from the entry's FILLED qty (never the ordered qty). Returns False
    when the order state could not be read (close_qty left unset)."""
    if e.get("close_qty"):
        return True
    ans = lookup_retry(ad, e["open_rec"], tries=tries)
    if ans is None:
        return False
    q = int(float(ans.get("filled") or 0))
    if q <= 0:
        e.update(unwind="cancelled", open_ok=False)
    else:
        e["close_qty"] = q
    return True


def _build_exit(e, day, what="X", qty=None):
    """The exit order, built at prep_at so exit_at only has the HTTP send left."""
    sid = signal_id(day, e["leg"], what)
    try:
        from api.webull_orders import _sanitize_client_order_id as _coid
        coid = _coid(sid)
    except Exception:                 # pragma: no cover
        coid = sid
    return {"leg": e["leg"], "signal_id": sid, "client_order_id": coid, "symbol": e["sym"],
            "side": broker_side(e["side"], "CLOSE"),
            "qty": int(qty if qty is not None else e["close_qty"]), "intent": "CLOSE",
            "order_type": "MARKET", "tif": "DAY", "session": "CORE"}


def send_order(ad, o, **extra):
    """Send a pre-built order dict as-is; the record carries _sid and the send's own clock."""
    k = {x: o[x] for x in ("leg", "signal_id", "symbol", "side", "qty", "intent",
                           "order_type", "tif")}
    k.update(extra)
    t0 = time.monotonic()
    try:
        rec = ad.place_stock_order(**k)
    except Exception as ex:      # place_stock_order never raises by contract; belt and braces
        rec = {"ok": False, "reason": f"{type(ex).__name__}: {ex}"}
    rec = dict(rec or {})
    rec.update(_sid=o["signal_id"], _t0=t0, _t1=time.monotonic())
    return rec


def _warm(ad):
    """Client + account id cached before exit_at (no token / account call on the hot path)."""
    try:
        mode = ad.effective_mode()[0]
        ad._account_id(mode, ad._client(mode))
    except Exception:
        pass


def _live_qty(ad, e):
    """Shares of this leg's direction Webull holds in e's symbol now; None = unreadable."""
    fn = getattr(ad, "positions", None)
    if fn is None:
        return None
    try:
        b = (fn() or {}).get("broker")
    except Exception:
        return None
    if not isinstance(b, dict):
        return None
    q = float(b.get(str(e["sym"]).upper(), 0) or 0)
    return int(max(q, 0.0) if e["side"] == "long" else max(-q, 0.0))


def _cancel_confirm(ad, rec, now_fn=None, cap=None):
    """Cancel an exit and read until Webull's record is terminal. (cancel answer, final
    lookup) -- final None = not confirmed (never re-send then)."""
    try:
        c = ad.cancel_order(rec.get("client_order_id") or rec.get("_sid")) or {}
    except Exception as ex:
        c = {"ok": False, "reason": f"{type(ex).__name__}: {ex}"}
    for i in range(CANCEL_TRIES):
        fin = lookup(ad, rec)
        if fin is not None and _done(fin):
            return c, fin
        if cap is not None and now_fn is not None and now_fn() >= cap:
            break
        if CONFIRM_PAUSE_S and i + 1 < CANCEL_TRIES:
            time.sleep(CONFIRM_PAUSE_S)
    return c, None


def _close_out(ad, entries, day, cfg, wait, notify, log, now_fn=_et_now):
    """prep_at: read every open entry's filled qty and pre-build its exit. exit_at: the
    pre-built MARKET exits all go IN PARALLEL with the adapter lock let go for the HTTP call
    (an unreadable prep read is retried once there; still unreadable = alert, nothing sent).
    fallback_at: see _fallback_one -- never a send at/after HARD_CAP."""
    t = exit_times(cfg, notify, log)
    wait(_at(day, t["prep_at"]))

    def prep(e):
        e["_prep_ok"] = _read_close_qty(ad, e)
        if e.get("close_qty"):
            e["exit_order"] = _build_exit(e, day)
    _pool_each(prep, [e for e in entries if _exit_due(e)])
    _warm(ad)

    wait(_at(day, t["exit_at"]))

    def exit_one(e):
        if not _exit_due(e):
            return
        if not e.pop("_prep_ok", True) or not e.get("close_qty"):
            if not _read_close_qty(ad, e, tries=1):       # the one retry at exit_at
                e["reconcile_failed"] = True
                notify(f"PICK6 #511: {e['sym']} {e['side']} order state unreadable at exit - "
                       f"NOTHING sent, check the account", log=log)
                return
            if not e.get("close_qty"):                    # nothing filled -> nothing to close
                return
        o = e.get("exit_order")
        if not o or int(o["qty"]) != int(e["close_qty"]):
            o = e["exit_order"] = _build_exit(e, day)
        rec = send_order(ad, o, wire_unlocked=True, skip_gateway=True)
        e.update(exit_ok=bool(rec.get("ok")), exit_reason=rec.get("reason"), exit_rec=rec)
        log(f"[PICK6 #511] EXIT MARKET {e['leg']} {e['sym']}: "
            f"{'ok' if e['exit_ok'] else 'REFUSED ' + str(e['exit_reason'])}")
    _pool_each(exit_one, entries)
    for e in entries:
        e.pop("_prep_ok", None)
    sent = [e["exit_rec"] for e in entries if e.get("exit_rec") and "_t0" in e["exit_rec"]]
    if sent:
        t0 = min(r["_t0"] for r in sent)
        spread = {"n": len(sent), "start_ms": round((max(r["_t0"] for r in sent) - t0) * 1e3, 1),
                  "all_back_ms": round((max(r["_t1"] for r in sent) - t0) * 1e3, 1)}
        for e in entries:
            if e.get("exit_rec") in sent:
                e["exit_spread"] = spread
        log(f"[PICK6 #511] EXIT SPREAD {spread}")

    wait(_at(day, t["fallback_at"]))
    cap = _at(day, HARD_CAP)
    _pool_each(lambda e: _fallback_one(ad, e, day, notify, log, now_fn, cap),
               [e for e in entries if e["open_ok"] and not e.get("reconcile_failed")
                and not e.get("fb_rec") and e.get("close_qty") and e.get("exit_rec")])


def _fallback_one(ad, e, day, notify, log, now_fn=_et_now, cap=None):
    """Anything not FILLED: READ the exit's status + filled qty first. Working / partial =
    cancel and confirm by reading (unconfirmed = alert, nothing sent). Then a NEW id (-FB)
    for min(close_qty - filled, live broker position) -- a fill that lands between the read
    and the resend can never turn into a short. Position unreadable = alert, nothing sent.
    Nothing is sent at or after `cap` (HARD_CAP)."""
    cap = cap or _at(day, HARD_CAP)
    cq = int(e.get("close_qty") or 0)
    done = 0
    xr = e["exit_rec"]
    if e.get("exit_ok") or xr.get("outcome") == "UNKNOWN":
        ans = lookup(ad, xr)
        e["exit_check"] = ans
        if ans is None:
            e["fb_skipped"] = "exit state unreadable"
            notify(f"PICK6 #511: {e['sym']} {e['side']} exit state unreadable at fallback - "
                   f"nothing re-sent, check the account", log=log)
            return
        st = str(ans.get("status"))
        done = int(float(ans.get("filled") or 0))
        if st == "FILLED" or done >= cq:
            return
        if st not in DEAD:                               # still working / pending / partial
            notify(f"PICK6 #511: {e['sym']} {e['side']} exit still {st} ({done} of {cq}) "
                   f"at fallback - cancelling and re-sending the rest", log=log)
            c, fin = _cancel_confirm(ad, xr, now_fn, cap)
            e["exit_cancel"] = {"ok": bool(c.get("ok")), "reason": c.get("reason")}
            if fin is None:
                e["fb_skipped"] = "cancel unconfirmed"
                notify(f"PICK6 #511: {e['sym']} {e['side']} exit cancel NOT confirmed - "
                       f"nothing re-sent (no double sell), check the account", log=log)
                log(f"[PICK6 #511] FALLBACK held {e['leg']} {e['sym']}: cancel unconfirmed")
                return
            e["exit_check"] = fin
            done = int(float(fin.get("filled") or 0))
    rem = cq - done
    if rem <= 0:
        return
    live = _live_qty(ad, e)
    if live is None:
        e["fb_skipped"] = "position unreadable"
        notify(f"PICK6 #511: {e['sym']} {e['side']} {rem} may be open but the live position "
               f"could not be read at fallback - nothing sent, check the account", log=log)
        return
    if live < rem:
        log(f"[PICK6 #511] FALLBACK {e['leg']} {e['sym']}: rest {rem} capped to live {live}")
    rem = min(rem, live)
    if rem <= 0:
        e["fb_skipped"] = "already flat at Webull"
        return
    if now_fn() >= cap:
        e["fb_skipped"] = "past hard cap"
        notify(f"PICK6 #511: {e['sym']} {e['side']} {rem} NOT re-sent - past the {HARD_CAP} "
               f"cap; the after-close check flattens it extended-hours", log=log)
        return
    e["exit_part_filled"] = done
    rec = send_order(ad, _build_exit(e, day, what="FB", qty=rem), wire_unlocked=True,
                     skip_gateway=True)
    e.update(fb_ok=bool(rec.get("ok")), fb_reason=rec.get("reason"), fb_rec=rec, fb_qty=rem)
    log(f"[PICK6 #511] FALLBACK MARKET {rem} {e['leg']} {e['sym']}: "
        f"{'ok' if e['fb_ok'] else 'REFUSED ' + str(e['fb_reason'])}")
    if not e["fb_ok"]:
        notify(f"PICK6 #511: {e['sym']} {e['side']} {rem} NOT "
               f"CLOSED - exit and fallback market both failed; position held overnight",
               log=log)


def _last_price(sym, log=print):
    """Webull snapshot price for `sym`, time-boxed to 5 s; None when unavailable."""
    import concurrent.futures as cf
    try:
        from api import qqq_exec
        pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pick6-quote")
        fut = pool.submit(qqq_exec._webull_quote_raw, sym, log)
        pool.shutdown(wait=False)
        res = fut.result(timeout=5.0)
        px = res[0] if isinstance(res, tuple) else None
        return float(px) if px else None
    except Exception:
        return None


def _after_close(ad, entries, day, notify, log):
    """16:00:05: any leftover from these legs = phone alert FIRST (whatever happens next),
    then an EXTENDED-HOURS LIMIT flatten (session ALL; Webull takes only LIMIT outside RTH)
    priced FLATTEN_PCT through the last price. Returns the legs that had a leftover."""
    left = []
    for e in entries:
        if not (e.get("open_ok") and e.get("close_qty")):
            continue
        q = _live_qty(ad, e)
        if q is None:
            if getattr(ad, "positions", None) is None:
                continue                                    # a double without a position read
            notify(f"PICK6 #511: {e['sym']} position unreadable after the close - check the "
                   f"account", log=log)
            left.append(e)
            continue
        q = min(q, int(e["close_qty"]))
        if q <= 0:
            continue
        left.append(e)
        e["after_close_left"] = q
        notify(f"PICK6 #511: {e['sym']} {e['side']} {q} STILL HELD after the close - "
               f"sending an extended-hours LIMIT flatten", log=log)
        working = False
        for xr in (e.get("exit_rec"), e.get("fb_rec")):     # dead exits roll the books back
            ans = lookup(ad, xr) if xr else None
            if ans is not None and not _done(ans):
                # a still-working exit is cancelled and confirmed dead first: never a LIMIT
                # on top of a live market order
                c, ans = _cancel_confirm(ad, xr)
                if ans is None:
                    working = True
            if ans and hasattr(ad, "apply_order_outcome"):
                try:
                    ad.apply_order_outcome(xr.get("_sid"), ans.get("status"), ans.get("filled"))
                except Exception:
                    pass
        if working:
            notify(f"PICK6 #511: {e['sym']} an exit is still working after the close and its "
                   f"cancel is NOT confirmed - no extended-hours flatten sent, check the account",
                   log=log)
            continue
        q2 = _live_qty(ad, e)                               # a cancel can race a last fill
        q = min(q, q2) if q2 is not None else q
        if q <= 0:
            continue
        px = _last_price(e["sym"], log)
        if not px:
            # never price off an old exit / entry print: alert loudly, leave it for 16:05 / owner
            notify(f"PICK6 #511: CHECK NOW - {e['sym']} {e['side']} {q} held after the close and "
                   f"NO live quote - extended-hours flatten NOT sent, close it by hand", log=log)
            continue
        sell = e["side"] == "long"
        lim = round(float(px) * ((1 - FLATTEN_PCT) if sell else (1 + FLATTEN_PCT)), 2)
        o = dict(_build_exit(e, day, what="AH", qty=q), order_type="LIMIT", session="ALL")
        rec = send_order(ad, o, extended_hours=True, limit_price=lim)
        e.update(ah_ok=bool(rec.get("ok")), ah_reason=rec.get("reason"), ah_limit=lim, ah_qty=q)
        log(f"[PICK6 #511] AFTER-CLOSE LIMIT {q} {e['sym']} @ {lim}: "
            f"{'ok' if e['ah_ok'] else 'REFUSED ' + str(e['ah_reason'])}")
        if not e["ah_ok"]:
            notify(f"PICK6 #511: {e['sym']} extended-hours flatten REFUSED "
                   f"({str(e['ah_reason'])[:120]}) - close it by hand", log=log)
    return left


def _settle(ad, entries, day, cfg, state, wait, notify, finish, sig=None, one_sided=None, log=print,
            now_fn=_et_now):
    wait(_at(day, exit_times(cfg, None, log)["flatten_at"]))
    after = now_fn()
    left = []
    if after.date() == day and after >= _at(day, "16:00"):   # same day, after the close only
        left = _after_close(ad, entries, day, notify, log)
    wait(_at(day, cfg["settle_at"]))
    for e in left:
        q = _live_qty(ad, e)
        e["settle_left"] = q
        if q is None or q > 0:
            notify(f"PICK6 #511: {e['sym']} {e['side']} STILL "
                   f"{'unreadable' if q is None else str(q) + ' held'} at settle after the "
                   f"extended-hours flatten - check the account", log=log)
    for e in entries:
        if not e["open_ok"]:
            continue
        o = lookup(ad, e["open_rec"]) or {}
        xr = e.get("fb_rec") or e.get("exit_rec")
        x = dict((lookup(ad, xr) if xr else None) or {})
        pre = int(e.get("exit_part_filled") or 0) if e.get("fb_rec") else 0
        if pre and x.get("filled") is not None:      # a resend of the rest: add the first part
            px0 = (e.get("exit_check") or {}).get("price")
            f1 = float(x.get("filled") or 0)
            if px0 and x.get("price") and f1:
                x["price"] = (pre * float(px0) + f1 * float(x["price"])) / (pre + f1)
            elif not f1:
                x["price"] = px0
            x["filled"] = pre + f1
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


# -- probe (MANAGER 11-14 a + b; rewritten 11-20 after the same-second exit bug) -------------
def run_probe(sym="AAPL", p=None, adapter=None, log=print, notify=None, wait_s=2.0, wait_tries=30,
              short_sym="MSFT", now_fn=_et_now, sleep=True):
    """1 share BUY `sym` + 1 share SHORT `short_sym` (separate symbols: Webull refuses opposing
    open orders on one symbol, HTTP 417 OPEN_ORDER_HAS_BOX_ORDER). PAPER only, in RTH.
    Each entry must FILL (wait_tries x wait_s, else alert + unwind). Held until exit_at
    (15:59:50) -> MARKET exit of the filled qty; anything not filled by fallback_at (15:59:54)
    is CANCELLED and confirmed dead first (unconfirmed = alert, no second order), then a MARKET
    fallback for the rest only -- never after HARD_CAP. Passes only when both exits show filled
    on Webull's own record."""
    p = p or paths()
    os.makedirs(p["dir"], exist_ok=True)
    ad = adapter or make_adapter(p, log=log)
    cfg = load_cfg(p)
    wait = (lambda t: _sleep_until(t, now_fn, log)) if sleep else (lambda t: None)
    nap = (lambda: time.sleep(wait_s)) if wait_s else (lambda: None)
    note = notify or _notify
    day = now_fn().date()
    legs = []
    for side, s in (("long", sym), ("short", short_sym)):
        e = {"leg": f"{LEG_PREFIX}_P{'L' if side == 'long' else 'S'}", "sym": s.upper(),
             "side": side, "qty": 1}
        o = send(ad, e, "OPEN", day, what="PO")
        e.update(open_ok=bool(o.get("ok")), open_reason=o.get("reason"), open_rec=o,
                 open_sid=o.get("_sid"), entry_filled=0)
        if e["open_ok"]:
            ans = None
            for _ in range(int(wait_tries)):
                ans = lookup(ad, o)
                if ans and float(ans.get("filled") or 0) >= 1:
                    break
                nap()
            e["entry_filled"] = int(float((ans or {}).get("filled") or 0))
            e["entry_status"] = (ans or {}).get("status")
            if e["entry_filled"] < 1:
                note(f"PICK6 #511 probe: {e['sym']} {side} entry not filled ({e['entry_status']}) "
                     f"- unwinding", log=log)
                unwind(ad, e, day, "probe entry not filled", log=log)
                e["open_ok"] = False
        legs.append(e)
    times = exit_times(cfg, note, log)
    cap = _at(day, HARD_CAP)
    wait(_at(day, times["exit_at"]))
    for e in legs:
        if not e["open_ok"]:
            continue
        m = send(ad, e, "CLOSE", day, order_type="MARKET", what="PX", qty=e["entry_filled"])
        e.update(exit_ok=bool(m.get("ok")), exit_reason=m.get("reason"), exit_rec=m)
    wait(_at(day, times["fallback_at"]))
    for e in legs:
        if not e["open_ok"]:
            continue
        ans = lookup(ad, e["exit_rec"]) if e.get("exit_ok") else None
        for _ in range(int(wait_tries) if e.get("exit_ok") else 0):
            if ans and (float(ans.get("filled") or 0) >= e["entry_filled"] or _done(ans)):
                break
            if now_fn() >= cap:
                break
            nap()
            ans = lookup(ad, e["exit_rec"])
        rem = e["entry_filled"] - int(float((ans or {}).get("filled") or 0))
        if e.get("exit_ok") and rem > 0 and not _done(ans):
            # CANCEL BEFORE RESEND (VERIFIER 11-21): a stuck exit never gets a second order
            # until Webull's own record shows it dead
            c, fin = _cancel_confirm(ad, e["exit_rec"], now_fn, cap)
            e["exit_cancel"] = {"ok": bool(c.get("ok")), "reason": c.get("reason")}
            if fin is None:
                note(f"PICK6 #511 probe: {e['sym']} {e['side']} exit cancel NOT confirmed - "
                     f"nothing re-sent, check the paper account", log=log)
                e.update(fb_ok=False, fb_reason="cancel unconfirmed")
                rem = 0
            else:
                ans = fin
                rem = e["entry_filled"] - int(float(fin.get("filled") or 0))
        if rem > 0 and now_fn() >= cap:
            note(f"PICK6 #511 probe: {e['sym']} {e['side']} {rem} not closed by {HARD_CAP} - "
                 f"nothing sent after the cap, check the paper account", log=log)
            e.update(fb_ok=False, fb_reason="past hard cap")
        elif rem > 0:
            pre = int(float((ans or {}).get("filled") or 0))
            fb = send(ad, e, "CLOSE", day, order_type="MARKET", what="PF", qty=rem)
            e.update(fb_ok=bool(fb.get("ok")), fb_reason=fb.get("reason"))
            ans = None
            for _ in range(int(wait_tries) if fb.get("ok") else 0):
                ans = lookup(ad, fb)
                if ans and float(ans.get("filled") or 0) >= rem:
                    break
                nap()
            if ans is not None:
                ans = dict(ans, filled=pre + float(ans.get("filled") or 0))
            if not (ans and float(ans.get("filled") or 0) >= e["entry_filled"]):
                note(f"PICK6 #511 probe: {e['sym']} {e['side']} NOT CLOSED - exit and fallback "
                     f"failed; check the paper account", log=log)
        e.update(exit_status=(ans or {}).get("status"), exit_filled=(ans or {}).get("filled") or 0)
    out = []
    for e in legs:
        r = {"side": e["side"], "sym": e["sym"], "open_ok": e["open_ok"],
             "open_reason": e.get("open_reason"), "entry_filled": e["entry_filled"],
             "exit_ok": e.get("exit_ok"), "exit_reason": e.get("exit_reason"),
             "fb_ok": e.get("fb_ok"), "fb_reason": e.get("fb_reason"),
             "exit_status": e.get("exit_status"), "exit_filled": e.get("exit_filled") or 0,
             "et": now_fn().strftime("%H:%M:%S")}
        out.append(r)
        log(f"[PICK6 #511 probe] {json.dumps(r, default=str)}")
    _append(os.path.join(p["dir"], "probe.jsonl"), {"day": str(day), "probe": "v3 hold-to-1559",
                                                     "results": out})
    good = len(out) == 2 and all(_probe_side_ok(x) for x in out)
    note(("PICK6 #511 probe PASSED: " if good else "PICK6 #511 probe FAILED: ") + "; ".join(
        f"{x['sym']} {x['side']} open {'ok' if x.get('open_ok') else x.get('open_reason')}, "
        f"exit {('filled ' + str(x.get('exit_filled'))) if _probe_side_ok(x) else (x.get('exit_reason') or x.get('exit_status'))}" for x in out)[:400], log=log)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run", "probe", "check", "alert-failed"))
    ap.add_argument("--resume-only", action="store_true",
                    help="run: only resume today's open basket (boot unit); never a fresh entry")
    ap.add_argument("--sym", default="AAPL")
    ap.add_argument("--short-sym", default="MSFT")
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
        run_probe(a.sym, p, log=log, short_sym=a.short_sym)
        return 0
    if a.cmd == "alert-failed":
        print(json.dumps(alert_failed(p, log=log), default=str))
        return 0
    if a.resume_only:
        print(json.dumps(resume_only(p, log=log), default=str)[:2000])
        return 0
    print(json.dumps(run_day(p, log=log), default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

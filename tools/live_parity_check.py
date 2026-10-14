r"""tools/live_parity_check.py -- the NIGHTLY PARITY CHECK of the live Webull legs (box side).

WHY (OWNER ORDER 2026-10-14, via MANAGER #163). From 09-21 to 09-25 the live ORB leg silently
dropped five trades: a half-day rule made every morning entry look "late", the engine skipped
each one without a log line (api/cloud_signal.py _diff_leg's "late" skip), and nobody noticed for
weeks. The owner: "make sure it does not happen again". This is the net that catches the NEXT
silent drop whatever its cause -- a skip rule, a feed gap, a restart, a stuck executor: after the
close it replays every LIVE leg with the engine's own code on the box's own bars and compares the
replay with that day's live signals and Webull fills. Any difference = ONE plain phone push that
night naming the leg, the time and the side.

WHICH LEGS. Exactly the legs that send Webull orders: api/cloud_signal.py CROWN_LEGS entries with
no "shadow" flag whose engine key api/qqq_exec.py turns into orders (ENGINE_LEG_MAP, or the DIP
key whose trade-id slot picks one of the seven DIP exec legs). Today: ORB_R6, NOISE_382, DIP_424.
Every SHADOW_LEGS entry (ENGUQ_335 -- a no-order tracker since 2026-10-09, MANAGER #113 -- and
the NOISE_422_* / DIP_424K / DIP_424F research arms) writes only the shadow ledger and is never
compared. A leg is also not compared on a day before its cfg "live_since" (DIP_424) or before its
first SEED row in the live ledger (it was not running live yet).

THE REPLAY. One end-of-day engine call per leg -- the backtest's own answer for the finished
session, which is what the live engine should have traded: cloud_signal.historical_bars ->
closed_arrays(now = the session close + 5 min, leg_warmup_sessions) -> leg_decision_trades (the
same function step() and the stream path call: run_leg_trades with the session_in_progress /
vol_prior_ranges / decide_at_close extras, or api/dip_live.py for DIP_424's daily series), offline
(fetch=False), on <home>/ohlc/QQQ_5m.csv (+ QQQ_1d.csv). Read-only: nothing here writes a bar
cache, a ledger, a state file or the KEEL store. KEEL and the plugin's sizes are NOT compared --
only the TIMES and SIDES of entries and exits.
  * Engine trades whose ENTRY bar or EXIT bar falls on the day are compared.
  * The live side is that day's ENTRY/EXIT rows of <home>/cloud_signal/signals.csv (by the row's
    bar time, ref_time -- so an EXIT written after midnight still counts for its own day). SEED,
    LEVELS and VOID_ENTRY rows are not trades.
  * Matched by leg + kind + side (+ the DIP slot) + bar time. A trade entered before the leg's
    latest SEED (absorbed at a cold start -- e.g. DIP_424's open positions on 10-13) is not
    expected live, nor is the exit of a trade whose entry was never signalled live (that entry was
    the finding on its own day).

FINDINGS (one log line each; all of them in ONE push):
  ENGINE_ONLY  the replay takes a trade (or exit) the live engine never signalled -- the 09-21 case.
               Names the live engine's own skip reason when its state.json still holds one.
  LIVE_ONLY    a live ENTRY/EXIT the replay does not produce.
  TIME_DIFF    same leg, kind and side, bar time off by <= 30 minutes -- usually a bar the feed
               restated after the fact (reported, but on its own it pushes at low priority).
  NO_FILL      a live ENTRY/EXIT with no Webull fill in <home>/qqq_exec/broker_orders.csv (its
               OPEN/CLOSE rows, by the executor's own order id) -- names the refusal / block reason
               on record. The CLOSE of a trade whose OPEN never filled is folded into the OPEN's.
  UNREADABLE   an input is missing or unreadable (signals.csv, the bar cache, the Webull order
               record), the day's bars are incomplete, or a leg's replay failed -- the check could
               not be made, which is itself worth knowing.

OUTPUT. <home>/cloud_signal/parity/<day>.json (written atomically: a temp file renamed over it) and
one log line per finding, or one quiet "parity OK" line. The push (api/ntfy_push.plain, the house
plain format, times on the owner's clock) goes once per day: a re-run with the same findings does
not push again. --no-push never pushes. Exit 0 always -- even when an input is missing or the
check itself crashes (that becomes an UNREADABLE finding and the push); exit 1 only on bad
arguments.

USAGE (on the box: deploy/cloud/edgelog-parity.timer, Mon-Fri 16:20 New York time):
  python tools/live_parity_check.py --home ~/edgelog                 # the last settled session
  python tools/live_parity_check.py --home DIR --day 2026-10-13 --no-push --json
Without --day it checks today once today's session is settled (10 minutes after the close, past
the engine's EOD settle), else the previous session -- so the timer's catch-up run after the box
was down at 16:20 checks the session it missed. An explicit --day of today before then is refused
(nothing checked, exit 0); a day in the future or a malformed one is a bad argument (exit 1).
"""
import argparse
import csv
import datetime as _dt
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TAG = "[live-parity]"
KINDS = ("ENGINE_ONLY", "LIVE_ONLY", "TIME_DIFF", "NO_FILL", "UNREADABLE")
TRADE_EVENTS = ("ENTRY", "EXIT")
TIME_DIFF_MAX_MIN = 30           # same side, bar time off by at most this -> TIME_DIFF, not a miss
REPLAY_AFTER_CLOSE_MIN = 5       # the replay's `now`: the session close + this (every bar closed)
TOO_EARLY_AFTER_CLOSE_MIN = 10   # today's check refuses to run before close + this (EOD settle)
PUSH_AREA = "Live vs backtest"
PUSH_ACTION = "ask Claude (PAPER-WB chat) to check it before the next open"
PUSH_ACTION_TIME_DIFF = "nothing - usually a price bar the data feed corrected later"
PUSH_ITEMS = 3                   # items named on the lock screen, then "+N more"
_ON_RECORD = "on record"


# ── small helpers ────────────────────────────────────────────────────────────────────────
def _cs():
    from api import cloud_signal
    return cloud_signal


def _tz():
    cs = _cs()
    return cs._zi(cs.TZ)


def _now_et():
    return _dt.datetime.now(tz=_tz())


def _say(msg, log=print):
    """One log line: '<ET wall clock> [live-parity] <msg>'. Never raises."""
    try:
        log(f"{_now_et():%Y-%m-%d %H:%M:%S} {TAG} {msg}")
    except Exception:
        pass


def _parse_ts(s):
    """ISO text (or a datetime) -> aware ET datetime, or None. A naive value is read as ET."""
    if s is None:
        return None
    try:
        if isinstance(s, _dt.datetime):
            d = s
        else:
            txt = str(s).strip()
            if not txt:
                return None
            d = _dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
        tz = _tz()
        return d.astimezone(tz) if d.tzinfo is not None else d.replace(tzinfo=tz)
    except Exception:
        return None


def _hhmm(d):
    return d.strftime("%H:%M") if d is not None else "??:??"


def _iso(d):
    return d.isoformat() if d is not None else None


def _truthy(v):
    return str(v or "").strip().lower() in ("true", "1", "yes")


def _one_line(x, limit=160):
    s = " ".join(str(x or "").split())
    return s if len(s) <= limit else s[:limit - 3] + "..."


def parity_paths(home):
    """Every file this tool reads, and the one directory it writes, under `home`."""
    cs = _cs()
    p = dict(cs._paths(home))
    exec_dir = os.path.join(home, "qqq_exec")
    p.update({
        "exec_dir": exec_dir,
        "trades_csv": os.path.join(exec_dir, "trades.csv"),
        "broker_orders_csv": os.path.join(exec_dir, "broker_orders.csv"),
        "orders_csv": os.path.join(exec_dir, "orders.csv"),
        "out_dir": os.path.join(p["state_dir"], "parity"),
    })
    return p


def _read_csv(path):
    """list of row dicts, or None when the file is missing; raises on an unreadable file."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── which legs send Webull orders ────────────────────────────────────────────────────────
def _executor_sends_orders():
    """key -> True when api/qqq_exec.py turns this engine key's rows into Webull orders
    (ENGINE_LEG_MAP, or the DIP key whose trade-id slot names a DIP exec leg). None when the
    executor module cannot be imported (the caller then trusts the cfg flags alone)."""
    try:
        from api import qqq_exec as qe
        mapped = set(qe.ENGINE_LEG_MAP) | {qe.DIP_ENGINE_KEY}
        return lambda key: key in mapped
    except Exception:
        return None


def order_legs(crown=None, shadow=None, sends_orders=None):
    """({key: cfg} of the legs that send Webull orders, {key: why not compared}).

    A leg is compared when it is in CROWN_LEGS, carries no "shadow" flag, and the executor maps
    its key to an order leg. Every SHADOW_LEGS entry (a no-order tracker / research arm) and
    anything else is listed with the reason it is not compared."""
    cs = _cs()
    crown = cs.CROWN_LEGS if crown is None else crown
    shadow = cs.SHADOW_LEGS if shadow is None else shadow
    if sends_orders is None:
        sends_orders = _executor_sends_orders()
    legs, skipped = {}, {}
    for key, cfg in crown.items():
        if (cfg or {}).get("shadow"):
            skipped[key] = "flagged shadow: a no-order tracker, never sends a Webull order"
        elif sends_orders is not None and not sends_orders(key):
            skipped[key] = "the executor (api/qqq_exec.py) sends no orders for this key"
        else:
            legs[key] = cfg
    for key, cfg in shadow.items():
        if key not in legs and key not in skipped:
            skipped[key] = ("SHADOW_LEGS: a no-order tracker / research arm, writes only the "
                            "shadow ledger")
    return legs, skipped


# ── the replay ───────────────────────────────────────────────────────────────────────────
def session_close_dt(day):
    cs = _cs()
    hh, mm = (int(x) for x in cs.market_calendar.session_close_et(day).split(":"))
    return _dt.datetime.combine(day, _dt.time(hh, mm), tzinfo=_tz())


def default_day(now):
    """The session to check when --day is not given: today once its session is settled (the close
    + TOO_EARLY_AFTER_CLOSE_MIN), else the last session before today -- so the timer's catch-up
    run after the box was down at 16:20 (Persistent=true: at boot, maybe the next morning) still
    checks the session it missed rather than refusing an unfinished one."""
    cs = _cs()
    d = now.date()
    if cs.market_calendar.is_session(d) and now >= session_close_dt(d) + _dt.timedelta(
            minutes=TOO_EARLY_AFTER_CLOSE_MIN):
        return d
    d -= _dt.timedelta(days=1)
    for _ in range(15):
        if cs.market_calendar.is_session(d):
            return d
        d -= _dt.timedelta(days=1)
    return now.date()


def replay_now(day):
    return session_close_dt(day) + _dt.timedelta(minutes=REPLAY_AFTER_CLOSE_MIN)


def day_bars_check(arrays, day, tf):
    """(complete, n_bars, last_bar_start) of `day`'s session in `arrays`. Complete = the
    session's own last bar is there (15:55, or 12:55 on a half day, for 5m)."""
    cs = _cs()
    import numpy as np
    idx = arrays["index"]
    pos = np.flatnonzero(np.asarray(idx.date) == day)
    n = int(len(pos))
    if not n:
        return False, 0, None
    last = idx[int(pos[-1])]
    complete = bool(cs._is_session_last_bar(last, tf))
    return complete, n, last


def engine_replay(key, cfg, day, paths, bars=None, log=None):
    """The engine's trades for `key` at the end of `day`'s session -- exactly what step() hands
    _diff_leg, computed once on the finished session. {"trades": [trade dicts] or None,
    "error": text or None, "plain": the error in plain words, "bars": n, "complete": bool}.
    Read-only; never raises."""
    cs = _cs()
    quiet = log or (lambda *_a, **_k: None)
    out = {"trades": None, "error": None, "plain": None, "bars": 0, "complete": False}

    def fail(error, plain):
        out["error"], out["plain"] = error, plain
        return out
    try:
        tf = cfg["timeframe"]
        epoch = (bars or {}).get(tf)
        if epoch is None:
            epoch = cs.historical_bars(tf, paths)
        if epoch is None or not len(epoch):
            return fail(f"the box's QQQ {tf} bar cache is missing or empty",
                        "its price bars are missing")
        now = replay_now(day)
        arrays = cs.closed_arrays(epoch, now, tf, cs.leg_warmup_sessions(cfg))
        if arrays is None:
            return fail(f"no QQQ {tf} bars up to {day.isoformat()}", "its price bars are missing")
        complete, n, last = day_bars_check(arrays, day, tf)
        out["bars"], out["complete"] = n, complete
        if not n:
            return fail(f"no QQQ {tf} bars for {day.isoformat()} in the box's cache",
                        "the day's price bars are missing")
        if not complete:
            return fail(f"the box's QQQ {tf} bars for {day.isoformat()} stop at the "
                        f"{_hhmm(last)} bar ({n} bars) -- the session is incomplete",
                        "the day's price bars are incomplete")
        why = {}
        trades, _diff_arrays = cs.leg_decision_trades(cfg, arrays, key, tf, now, paths, False,
                                                      log=quiet, why_out=why)
        if trades is None:
            return fail("replay not ready: " + str(why.get("text") or why.get("key")
                                                   or "no reason given"),
                        "its daily price series is not ready")
        out["trades"] = list(trades)
        return out
    except Exception as e:
        return fail(f"replay failed ({type(e).__name__}: {_one_line(e, 120)})",
                    "its replay failed")


# ── the live ledger ──────────────────────────────────────────────────────────────────────
def _row_slot(row):
    from api import trade_id as _tid
    p = _tid.parse(row.get("trade_id"))
    return (p or {}).get("slot")


def live_trade_rows(rows, leg):
    """The leg's ENTRY/EXIT rows (every day), de-duplicated by (event, trade id, bar time),
    each with parsed "_t" (bar time) and "_slot"."""
    out, seen = [], set()
    for r in rows or []:
        if r.get("leg") != leg or r.get("event") not in TRADE_EVENTS:
            continue
        t = _parse_ts(r.get("ref_time"))
        if t is None:
            continue
        k = (r.get("event"), r.get("trade_id") or "", t.isoformat(), r.get("side"))
        if k in seen:
            continue
        seen.add(k)
        out.append(dict(r, _t=t, _slot=_row_slot(r)))
    return out


def seed_times(rows, leg):
    """Sorted emitted_at times of the leg's SEED rows in the live ledger."""
    out = []
    for r in rows or []:
        if r.get("leg") == leg and r.get("event") == "SEED":
            t = _parse_ts(r.get("emitted_at"))
            if t is not None:
                out.append(t)
    return sorted(out)


def _live_since_gate(cfg, day):
    want = (cfg or {}).get("live_since")
    return bool(want) and day.isoformat() < str(want)


# ── matching ─────────────────────────────────────────────────────────────────────────────
def _match(eng, live, max_min=TIME_DIFF_MAX_MIN):
    """Pair engine and live events of one kind: same side and slot; the same bar time first,
    then the nearest within `max_min` minutes. -> (exact [(e, l)], near [(e, l)], eng_left,
    live_left)."""
    used_e, used_l = set(), set()
    exact, near = [], []
    for i, e in enumerate(eng):
        for j, l in enumerate(live):
            if j in used_l or i in used_e:
                continue
            if e["side"] == l["side"] and e["slot"] == l["slot"] and e["time"] == l["time"]:
                exact.append((e, l))
                used_e.add(i)
                used_l.add(j)
                break
    cands = []
    for i, e in enumerate(eng):
        if i in used_e:
            continue
        for j, l in enumerate(live):
            if j in used_l or e["side"] != l["side"] or e["slot"] != l["slot"]:
                continue
            gap = abs((e["time"] - l["time"]).total_seconds())
            if gap <= max_min * 60:
                cands.append((gap, e["time"], i, j))
    for _gap, _t, i, j in sorted(cands, key=lambda c: (c[0], c[1])):
        if i in used_e or j in used_l:
            continue
        near.append((eng[i], live[j]))
        used_e.add(i)
        used_l.add(j)
    return (exact, near, [e for i, e in enumerate(eng) if i not in used_e],
            [l for j, l in enumerate(live) if j not in used_l])


def _ev(kind, side, slot, t, tid, **kw):
    return dict(kind=kind, side=side, slot=slot or None, time=t, tid=tid, **kw)


def _finding(kind, leg, event, side, slot, t, detail, **kw):
    f = {"kind": kind, "leg": leg, "event": event, "side": side, "slot": slot or None,
         "time": _iso(t), "hhmm": _hhmm(t) if t is not None else None, "detail": detail}
    f.update(kw)
    f["id"] = "|".join(str(x) for x in (kind, leg, event, side, slot or "", f["time"] or "",
                                        kw.get("live_time") or ""))
    return f


def _state_skip(state_leg, tid):
    rec = ((state_leg or {}).get("trades") or {}).get(tid) or {}
    return rec.get("skipped") or None


def compare_leg(key, cfg, day, trades, live_rows_all, seeds, state_leg=None):
    """Findings for one leg's replay `trades` against its live rows (see the module docstring).
    -> (findings, summary dict)."""
    cs = _cs()
    tf_sec = cs.TIMEFRAME_SECONDS.get(cfg.get("timeframe"), 300)
    seed_cut = None
    end_of_day = session_close_dt(day) + _dt.timedelta(hours=8)
    for s in seeds:
        if s <= end_of_day:
            seed_cut = s
    recs = []
    for t in trades or []:
        et = _parse_ts(t.get("entry_time"))
        if et is None:
            continue
        xt = None if t.get("still_open") else _parse_ts(t.get("exit_time"))
        tid = cs._entry_key(key, t)
        absorbed = bool(seed_cut is not None
                        and et + _dt.timedelta(seconds=tf_sec) <= seed_cut)
        recs.append({"tid": tid, "side": t.get("side"), "slot": t.get("slot") or None,
                     "entry": et, "exit": xt, "absorbed": absorbed})

    day_live = [r for r in live_rows_all if r["_t"].date() == day]
    live_ent = [_ev("ENTRY", r.get("side"), r["_slot"], r["_t"], r.get("trade_id") or "", row=r)
                for r in day_live if r.get("event") == "ENTRY"]
    live_entry_tids = {r.get("trade_id") for r in live_rows_all
                       if r.get("event") == "ENTRY" and r.get("trade_id")}
    live_entries_all = [r for r in live_rows_all if r.get("event") == "ENTRY"]

    findings = []
    summary = {"engine_trades_on_day": 0, "absorbed_at_seed": [], "live_rows_on_day": len(day_live),
               "matched": 0, "time_diff": 0, "not_expected_live": []}

    eng_ent = []
    for r in recs:
        if r["entry"].date() != day:
            continue
        summary["engine_trades_on_day"] += 1
        if r["absorbed"]:
            summary["absorbed_at_seed"].append(r["tid"])
            continue
        eng_ent.append(_ev("ENTRY", r["side"], r["slot"], r["entry"], r["tid"], rec=r))
    exact, near, eng_left, live_left = _match(eng_ent, live_ent)
    matched_tids = {e["tid"] for e, _l in exact + near}
    missed_tids = {e["tid"] for e in eng_left}
    summary["matched"] += len(exact)
    summary["time_diff"] += len(near)

    for e, l in near:
        gap = round((l["time"] - e["time"]).total_seconds() / 60.0)
        findings.append(_finding(
            "TIME_DIFF", key, "ENTRY", e["side"], e["slot"], e["time"],
            f"entry at the {_hhmm(e['time'])} bar in the replay, the {_hhmm(l['time'])} bar live "
            f"({gap:+d} min) -- usually a bar restated after the fact",
            live_time=_iso(l["time"]), minutes=gap, trade_id=e["tid"],
            live_trade_id=l["tid"]))
    for e in eng_left:
        r = e["rec"]
        skip = _state_skip(state_leg, e["tid"])
        exit_txt = (f", exit at the {_hhmm(r['exit'])} bar" if r["exit"] is not None
                    and r["exit"].date() == day else "")
        findings.append(_finding(
            "ENGINE_ONLY", key, "ENTRY", e["side"], e["slot"], e["time"],
            f"the replay takes this trade (entry at the {_hhmm(e['time'])} bar{exit_txt}); the "
            f"live engine wrote no ENTRY row"
            + (f" (its memory has it skipped as {skip!r})" if skip else ""),
            trade_id=e["tid"], engine_skip=skip))
    live_only_tids = set()
    for l in live_left:
        r = l["row"]
        live_only_tids.add(l["tid"])
        exit_rows = [x for x in live_rows_all if x.get("event") == "EXIT"
                     and x.get("trade_id") and x.get("trade_id") == l["tid"]]
        exit_txt = (f", its live exit at the {_hhmm(exit_rows[0]['_t'])} bar"
                    if exit_rows else "")
        findings.append(_finding(
            "LIVE_ONLY", key, "ENTRY", l["side"], l["slot"], l["time"],
            f"live ENTRY at the {_hhmm(l['time'])} bar{exit_txt}; the replay of the finished "
            f"session takes no such trade", trade_id=l["tid"],
            reason=_one_line(r.get("reason"), 100)))

    # ── exits ──
    eng_exit = []
    for r in recs:
        if r["exit"] is None or r["exit"].date() != day:
            continue
        if r["absorbed"]:
            summary["not_expected_live"].append({"trade_id": r["tid"], "why": "absorbed at the SEED"})
            continue
        if r["entry"].date() == day:
            if r["tid"] in missed_tids:
                continue                                   # folded into its ENGINE_ONLY entry
            if r["tid"] not in matched_tids:
                continue
        else:
            has_live = r["tid"] in live_entry_tids or any(
                x.get("side") == r["side"] and x["_slot"] == r["slot"]
                and abs((x["_t"] - r["entry"]).total_seconds()) <= TIME_DIFF_MAX_MIN * 60
                for x in live_entries_all)
            if not has_live:
                summary["not_expected_live"].append(
                    {"trade_id": r["tid"], "why": "its entry was never signalled live"})
                continue
        eng_exit.append(_ev("EXIT", r["side"], r["slot"], r["exit"], r["tid"], rec=r))
    # a live EXIT of a trade entered on an earlier day that the replay never had (its entry was a
    # LIVE_ONLY finding on its own day) is folded into that finding, not reported again
    by_tid = {r["tid"]: r for r in recs}
    live_entry_by_tid = {x.get("trade_id"): x for x in live_entries_all if x.get("trade_id")}

    def _replay_has(entry_row):
        return any(r["side"] == entry_row.get("side") and r["slot"] == entry_row["_slot"]
                   and abs((r["entry"] - entry_row["_t"]).total_seconds())
                   <= TIME_DIFF_MAX_MIN * 60 for r in recs)
    live_exit = []
    for r in day_live:
        tid = r.get("trade_id") or ""
        if r.get("event") != "EXIT" or (tid and tid in live_only_tids):
            continue
        ent = live_entry_by_tid.get(tid)
        if ent is not None and ent["_t"].date() < day and tid not in by_tid                 and not _replay_has(ent):
            summary["not_expected_live"].append(
                {"trade_id": tid, "why": "live exit of a trade the replay never had (its entry "
                                         "was the finding on its own day)"})
            continue
        live_exit.append(_ev("EXIT", r.get("side"), r["_slot"], r["_t"], tid, row=r))
    exact, near, eng_left, live_left = _match(eng_exit, live_exit)
    summary["matched"] += len(exact)
    summary["time_diff"] += len(near)
    for e, l in near:
        gap = round((l["time"] - e["time"]).total_seconds() / 60.0)
        findings.append(_finding(
            "TIME_DIFF", key, "EXIT", e["side"], e["slot"], e["time"],
            f"exit at the {_hhmm(e['time'])} bar in the replay, the {_hhmm(l['time'])} bar live "
            f"({gap:+d} min) -- usually a bar restated after the fact",
            live_time=_iso(l["time"]), minutes=gap, trade_id=e["tid"], live_trade_id=l["tid"]))
    for e in eng_left:
        other = [x for x in live_rows_all if x.get("event") == "EXIT" and x.get("trade_id") == e["tid"]]
        instead = (f"; live exited it at the {_hhmm(other[0]['_t'])} bar on "
                   f"{other[0]['_t'].date().isoformat()} instead" if other
                   else "; no live EXIT row for it at all (a live position may still be open)")
        findings.append(_finding(
            "ENGINE_ONLY", key, "EXIT", e["side"], e["slot"], e["time"],
            f"the replay exits {e['tid']} at the {_hhmm(e['time'])} bar{instead}",
            trade_id=e["tid"]))
    for l in live_left:
        rec = by_tid.get(l["tid"])
        if rec is None:
            where = "the replay has no such trade"
        elif rec["exit"] is None:
            where = "the replay still holds that trade"
        else:
            where = (f"the replay exits that trade at the {_hhmm(rec['exit'])} bar on "
                     f"{rec['exit'].date().isoformat()}")
        findings.append(_finding(
            "LIVE_ONLY", key, "EXIT", l["side"], l["slot"], l["time"],
            f"live EXIT at the {_hhmm(l['time'])} bar for {l['tid'] or '(no trade id)'}; {where}",
            trade_id=l["tid"], reason=_one_line(l["row"].get("reason"), 100)))
    return findings, summary


# ── Webull fills ─────────────────────────────────────────────────────────────────────────
def _broker_rows_for(broker_rows, tid, intent):
    from api import trade_id as _tid
    if not tid:
        return []
    base = _tid.broker_signal_base(tid, intent)
    return [b for b in broker_rows or [] if str(b.get("signal_id") or "").startswith(base)]


def _filled(rows):
    return any(_truthy(b.get("ok")) for b in rows)


def _no_fill_reason(rows, exec_leg, event, t, orders_rows):
    """Plain reason for a live row with no Webull fill: the broker record's own words, else what
    the book did, else that nothing acted on it."""
    if rows:
        b = rows[-1]
        outcome = (b.get("outcome") or "").strip() or ("sent, not accepted" if _truthy(b.get("sent"))
                                                       else "not sent")
        why = _one_line(b.get("reason"), 140) or "no reason recorded"
        return f"{outcome} ({b.get('mode') or '?'} mode): {why}"
    action = "ENTER" if event == "ENTRY" else "EXIT"
    for o in orders_rows or []:
        if exec_leg and o.get("leg") != exec_leg:
            continue
        ot = _parse_ts(o.get("ts_et"))
        if o.get("action") == action and ot is not None and t is not None \
                and t <= ot <= t + _dt.timedelta(hours=2):
            return (f"the book recorded the {action.lower()} at {_hhmm(ot)} but no Webull order "
                    f"is {_ON_RECORD}")
    return "no Webull order and no book order on record -- the executor never acted on it"


def _exec_leg_for(key, tid):
    try:
        from api import qqq_exec as qe
        return qe._exec_leg_for(key, tid)
    except Exception:
        return None


def fill_findings(key, day, live_rows_all, broker_rows, orders_rows):
    """NO_FILL findings for the leg's live ENTRY/EXIT rows on `day`."""
    out = []
    for r in live_rows_all:
        if r["_t"].date() != day:
            continue
        ev, tid = r.get("event"), r.get("trade_id") or ""
        intent = "OPEN" if ev == "ENTRY" else "CLOSE"
        if not tid:
            out.append(_finding("NO_FILL", key, ev, r.get("side"), r["_slot"], r["_t"],
                                "the live row has no trade id, so the executor refuses it"))
            continue
        rows = _broker_rows_for(broker_rows, tid, intent)
        if _filled(rows):
            continue
        if ev == "EXIT":
            open_rows = _broker_rows_for(broker_rows, tid, "OPEN")
            if not _filled(open_rows):
                continue        # folded: its OPEN never filled (that is the finding, on its day)
        exec_leg = _exec_leg_for(key, tid)
        reason = _no_fill_reason(rows, exec_leg, ev, r["_t"], orders_rows)
        out.append(_finding(
            "NO_FILL", key, ev, r.get("side"), r["_slot"], r["_t"],
            f"live {ev} at the {_hhmm(r['_t'])} bar ({tid}) has no Webull fill -- {reason}",
            trade_id=tid, exec_leg=exec_leg, broker_rows=len(rows)))
    return out


# ── the phone push ───────────────────────────────────────────────────────────────────────
def _leg_word(leg):
    try:
        return _cs()._keel_leg_word(leg)
    except Exception:
        return str(leg).split("_")[0]


def _push_item(f):
    from api import ntfy_push
    if f["kind"] == "UNREADABLE":
        what = f"could not check {_leg_word(f['leg'])}" if f.get("leg") else "could not run the check"
        return f"{what}: {_one_line(f.get('plain') or f.get('detail'), 90)}"
    t = _parse_ts(f.get("time"))
    clock = ntfy_push.hhmm(t, now=t) if t is not None else "??:??"
    name = f"{_leg_word(f['leg'])} {clock} {f.get('side')}"
    if f.get("event") == "EXIT":
        name += " exit"
    if f.get("slot"):
        name += f" ({f['slot']})"
    return {"ENGINE_ONLY": f"no live signal for {name}",
            "LIVE_ONLY": f"live {name} is not in the backtest",
            "TIME_DIFF": f"{name} came {abs(int(f.get('minutes') or 0))} min off the backtest",
            "NO_FILL": f"no Webull fill for {name}"}.get(f["kind"], name)


def build_push(findings):
    """ONE plain note (api/ntfy_push.plain) for every finding, or None when there are none.
    Trading is AFFECTED (high) by a miss, an extra trade or a missing fill; a check that could
    not run is 'needs a fix' (default); bar-time differences alone are a low 'heads up'."""
    from api import ntfy_push
    if not findings:
        return None
    order = {"ENGINE_ONLY": 0, "LIVE_ONLY": 1, "NO_FILL": 2, "UNREADABLE": 3, "TIME_DIFF": 4}
    fs = sorted(findings, key=lambda f: (order.get(f["kind"], 9), f.get("time") or ""))
    kinds = {f["kind"] for f in fs}
    affected = bool(kinds & {"ENGINE_ONLY", "LIVE_ONLY", "NO_FILL"})
    items = [_push_item(f) for f in fs]
    items = [i[:1].upper() + i[1:] for i in items]
    problem = ntfy_push.join_problems(items, limit=PUSH_ITEMS)
    if affected:
        return ntfy_push.plain(PUSH_AREA, "CHECK NOW",
                               "the live book did not trade like its backtest today", problem,
                               PUSH_ACTION, priority="high")
    if "UNREADABLE" in kinds:
        return ntfy_push.plain(PUSH_AREA, "needs a fix",
                               "not affected as far as known - tonight's check could not run",
                               problem, PUSH_ACTION, priority="default")
    return ntfy_push.plain(PUSH_AREA, "heads up", None, problem, PUSH_ACTION_TIME_DIFF,
                           priority="low")


def _send_push(note, log=print):
    """(sent, detail) -- api/ntfy_push.push_result: True / False, or None when NTFY_TOPIC is
    unset. Never raises; never logs the topic or token."""
    try:
        from api import ntfy_push
        ok, detail = ntfy_push.push_result(note["message"], title=note["title"],
                                           priority=note["priority"], log=log)
        return ok, detail
    except Exception as e:
        return False, f"{type(e).__name__}: {_one_line(e, 80)}"


# ── output ───────────────────────────────────────────────────────────────────────────────
def write_json_atomic(path, doc):
    """Write `doc` beside `path` and rename it over -- a reader sees the old file or the new."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), int(time.time() * 1000) % 100000)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, sort_keys=False, default=str)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _log_finding(f, day, log):
    slot = f" [{f['slot']}]" if f.get("slot") else ""
    when = f" {f['event'].lower()} {f.get('side')} {f.get('hhmm')}" if f.get("event") else ""
    _say(f"{day.isoformat()} {f['kind']} {f.get('leg') or '-'}{when}{slot}: {f['detail']}", log)


# ── the check ────────────────────────────────────────────────────────────────────────────
def run_check(home, day, push=True, now=None, log=print, legs=None, skipped=None,
              replay=None, pusher=None):
    """Run the parity check for `day` (a date) on the files under `home` and return the result
    doc (also written to <home>/cloud_signal/parity/<day>.json). `legs` / `skipped` override
    order_legs() (tests), `replay(key, cfg, day, paths, bars)` overrides engine_replay, and
    `pusher(note) -> (sent, detail)` overrides the real push. Raises only on a bug the caller
    (main) turns into an UNREADABLE finding."""
    cs = _cs()
    paths = parity_paths(home)
    now = now or _now_et()
    if legs is None:
        legs, auto_skipped = order_legs()
        skipped = auto_skipped if skipped is None else skipped
    skipped = dict(skipped or {})
    replay = replay or engine_replay
    findings = []
    doc = {"day": day.isoformat(), "generated_at": now.isoformat(), "home": home,
           "tool": "tools/live_parity_check.py", "compared_legs": sorted(legs),
           "not_compared": skipped, "legs": {}, "findings": findings}

    def unreadable(what, plain, leg=None):
        findings.append(_finding("UNREADABLE", leg, None, None, None, None, what, plain=plain))

    # the live ledger
    sig_rows = None
    try:
        sig_rows = _read_csv(paths["signals_path"])
        if sig_rows is None:
            unreadable(f"the live ledger {paths['signals_path']} is missing",
                       "the live signal file is missing")
    except Exception as e:
        unreadable(f"the live ledger could not be read ({type(e).__name__}: {_one_line(e, 100)})",
                   "the live signal file could not be read")
    state = {}
    try:
        state = cs._load_state(paths) or {}
    except Exception:
        state = {}
    # the executor's Webull record (needed only when there are live rows to check)
    broker_rows = orders_rows = None
    broker_err = None
    try:
        broker_rows = _read_csv(paths["broker_orders_csv"])
        if broker_rows is None:
            broker_err = f"{paths['broker_orders_csv']} is missing"
    except Exception as e:
        broker_err = f"broker_orders.csv could not be read ({type(e).__name__})"
    try:
        orders_rows = _read_csv(paths["orders_csv"]) or []
    except Exception:
        orders_rows = []
    try:
        trades_rows = _read_csv(paths["trades_csv"])
        doc["executor_trades_on_day"] = sum(
            1 for t in trades_rows or []
            if str(t.get("entry_ts") or "")[:10] == day.isoformat()
            or str(t.get("exit_ts") or "")[:10] == day.isoformat())
    except Exception:
        doc["executor_trades_on_day"] = None

    # the bar caches, once per timeframe
    bars, bars_err = {}, {}
    for tf in sorted({c["timeframe"] for c in legs.values()}):
        try:
            df = cs.historical_bars(tf, paths)
            if df is None or not len(df):
                bars_err[tf] = f"the box's QQQ {tf} bar cache is missing or empty"
                unreadable(bars_err[tf], f"the QQQ {tf} price bars are missing")
            else:
                bars[tf] = df
        except Exception as e:
            bars_err[tf] = f"the box's QQQ {tf} bar cache could not be read ({type(e).__name__})"
            unreadable(bars_err[tf], f"the QQQ {tf} price bars could not be read")

    no_fill_rows = []
    for key in sorted(legs):
        cfg = legs[key]
        info = {"compared": False}
        doc["legs"][key] = info
        if _live_since_gate(cfg, day):
            info["why_not"] = f"not live until {cfg.get('live_since')}"
            continue
        live_all = live_trade_rows(sig_rows, key) if sig_rows is not None else []
        seeds = seed_times(sig_rows, key) if sig_rows is not None else []
        if seeds and seeds[0].date() > day:
            info["why_not"] = (f"not live on the box yet: its first SEED in the live ledger is "
                               f"{seeds[0].date().isoformat()}")
            continue
        if sig_rows is not None:
            no_fill_rows.append((key, live_all))       # fills are checked even if the replay fails
        if cfg["timeframe"] in bars_err:
            info["why_not"] = bars_err[cfg["timeframe"]]
            continue
        res = replay(key, cfg, day, paths, bars)
        info.update(bars=res.get("bars"), complete=res.get("complete"))
        if res.get("error"):
            info["why_not"] = res["error"]
            unreadable(f"{key}: {res['error']}", res.get("plain") or _one_line(res["error"], 80),
                       leg=key)
            continue
        trades = res.get("trades") or []
        info["engine_trades"] = [
            {"trade_id": cs._entry_key(key, t), "side": t.get("side"), "slot": t.get("slot"),
             "entry_time": t.get("entry_time"), "exit_time": t.get("exit_time"),
             "still_open": bool(t.get("still_open"))}
            for t in trades
            if str(t.get("entry_time") or "")[:10] == day.isoformat()
            or str(t.get("exit_time") or "")[:10] == day.isoformat()]
        if sig_rows is None:
            info["why_not"] = "the live ledger is unreadable"
            continue
        info["compared"] = True
        fs, summary = compare_leg(key, cfg, day, trades, live_all, seeds,
                                  (state.get("legs") or {}).get(key))
        info.update(summary)
        findings.extend(fs)

    # Webull fills for every compared leg's live rows of the day
    day_rows = sum(1 for _k, rows in no_fill_rows for r in rows if r["_t"].date() == day)
    if day_rows and broker_rows is None:
        unreadable(f"the Webull order record cannot be checked: {broker_err}",
                   "the Webull order record is missing")
    elif day_rows:
        for key, rows in no_fill_rows:
            findings.extend(fill_findings(key, day, rows, broker_rows, orders_rows))

    # other legs' rows in the live ledger that day (not compared -- listed, never pushed)
    other = {}
    for r in sig_rows or []:
        if r.get("event") in TRADE_EVENTS and r.get("leg") not in legs:
            t = _parse_ts(r.get("ref_time"))
            if t is not None and t.date() == day:
                other[r.get("leg")] = other.get(r.get("leg"), 0) + 1
    if other:
        doc["other_live_rows"] = other
        _say(f"{day.isoformat()} live ledger rows of legs that are not compared: "
             + ", ".join(f"{k} x{v}" for k, v in sorted(other.items())), log)

    # log, push, write
    for f in findings:
        _log_finding(f, day, log)
    counts = {k: sum(1 for f in findings if f["kind"] == k) for k in KINDS}
    doc["counts"] = counts
    doc["ok"] = not findings
    compared = [k for k, v in doc["legs"].items() if v.get("compared")]
    if not findings:
        _say(f"{day.isoformat()} parity OK -- {len(compared)} leg(s) compared "
             f"({', '.join(compared) or 'none'}), every live signal matches the replay and has a "
             f"Webull fill", log)
    doc["push"] = _maybe_push(findings, paths, day, push, pusher, log)
    out_path = os.path.join(paths["out_dir"], f"{day.isoformat()}.json")
    write_json_atomic(out_path, doc)
    doc["_path"] = out_path
    return doc


def _maybe_push(findings, paths, day, push, pusher, log):
    """The push block of the result doc. ONE push per day: a re-run (the timer's catch-up, a
    manual run, a --no-push re-check) whose findings match the ones already pushed for this day
    does not push again and carries the earlier push's record forward. "sent" = this day's
    findings have reached the phone (True / False / None: NTFY_TOPIC unset or nothing to send);
    "sent_this_run" = this run sent it."""
    ids = sorted(f["id"] for f in findings)
    block = {"wanted": bool(findings), "sent": None, "sent_this_run": False, "finding_ids": ids}
    if not findings:
        return block
    note = build_push(findings)
    block.update(title=note["title"], message=note["message"], priority=note["priority"])
    prev = _read_json(os.path.join(paths["out_dir"], f"{day.isoformat()}.json")) or {}
    pp = prev.get("push") or {}
    if pp.get("sent") and sorted(pp.get("finding_ids") or []) == ids:
        block.update(sent=True, detail="already pushed for this day with the same findings",
                     pushed_at=pp.get("pushed_at"))
        _say(f"{day.isoformat()} push skipped: already sent for these findings", log)
        return block
    if not push:
        block["detail"] = "--no-push"
        _say(f"{day.isoformat()} push not sent (--no-push): {note['title']}", log)
        return block
    sent, detail = (pusher or _send_push)(note)
    block.update(sent=sent, sent_this_run=bool(sent), detail=detail,
                 pushed_at=_now_et().isoformat() if sent else None)
    _say(f"{day.isoformat()} push {'sent' if sent else 'NOT sent'} ({note['priority']}): "
         f"{note['title']} -- {detail}", log)
    return block


def _crash_doc(home, day, err, push, pusher, log):
    """The check itself failed: one UNREADABLE finding, written and pushed like any other.
    Never raises."""
    try:
        f = _finding("UNREADABLE", None, None, None, None, None,
                     f"the parity check crashed: {err}", plain="the check crashed")
        _log_finding(f, day, log)
        paths = parity_paths(home)
        doc = {"day": day.isoformat(), "generated_at": _now_et().isoformat(), "home": home,
               "tool": "tools/live_parity_check.py", "findings": [f], "ok": False,
               "counts": {k: int(k == "UNREADABLE") for k in KINDS}}
        doc["push"] = _maybe_push([f], paths, day, push, pusher, log)
        write_json_atomic(os.path.join(paths["out_dir"], f"{day.isoformat()}.json"), doc)
        return doc
    except Exception as e:
        _say(f"{day} could not even record the crash ({type(e).__name__}: {e})", log)
        return None


def main(argv=None, log=print, pusher=None, now=None):
    ap = argparse.ArgumentParser(description="Nightly parity check: replay every live Webull leg "
                                             "on the box's own bars and compare it with the day's "
                                             "live signals and Webull fills.")
    ap.add_argument("--home", default=None, help="EDGELOG_HOME (default: api/cloud_signal.edgelog_home)")
    ap.add_argument("--day", default=None, help="session date YYYY-MM-DD (default: the last settled session -- "
                                         "today from 10 min after the close, New York time)")
    ap.add_argument("--no-push", action="store_true", help="never send the phone push")
    ap.add_argument("--json", action="store_true", help="print the result doc as JSON")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 1
    try:
        cs = _cs()
        now = now or _now_et()
        home = a.home or cs.edgelog_home()
        if a.day:
            try:
                day = _dt.date.fromisoformat(a.day)
            except ValueError:
                _say(f"bad --day {a.day!r} (want YYYY-MM-DD)", log)
                return 1
        else:
            day = default_day(now)
        if day > now.date():
            _say(f"--day {day.isoformat()} is in the future", log)
            return 1
    except Exception as e:
        _say(f"bad arguments ({type(e).__name__}: {e})", log)
        return 1
    try:
        if not cs.market_calendar.is_session(day):
            _say(f"{day.isoformat()} is not a trading session -- nothing to check", log)
            return 0
        if day == now.date() and now < session_close_dt(day) + _dt.timedelta(
                minutes=TOO_EARLY_AFTER_CLOSE_MIN):
            _say(f"{day.isoformat()}: the session is not settled yet (the check runs from "
                 f"{TOO_EARLY_AFTER_CLOSE_MIN} min after the close) -- nothing checked", log)
            return 0
        doc = run_check(home, day, push=not a.no_push, now=now, log=log, pusher=pusher)
    except Exception as e:
        doc = _crash_doc(home, day, f"{type(e).__name__}: {_one_line(e, 160)}",
                         not a.no_push, pusher, log)
    if a.json and doc is not None:
        try:
            log(json.dumps({k: v for k, v in doc.items() if not k.startswith("_")}, indent=2,
                           default=str))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""BOOKS toggle (owner-approved 2026-11-19): the paper page's BOOKS card sets each book leg to
OFF / SHADOW / PAPER; the QQQ box applies it at a flat moment onto the switches it ALREADY has.

ONE classification table (BOOK_LEG_CLASS) -- index.html carries a mirrored JS table
(BOOKS_LEG_CLASS); tests/test_books_toggle.py checks the two agree.

Firestore:
  users/{uid}/meta/book_legs              written by tools/book_legs_publish.py (the PC), read by the page
  users/{uid}/meta/books_toggle           written by the page: {legs:{<leg id>: OFF|SHADOW|PAPER}, by, ts}
  users/{uid}/meta/books_toggle_applied   written by the box after it applied a set: {legs, applied_ts,
                                          applied_by, effects, src_ts}; the page row reads 'pending' until
                                          applied_ts covers the page's own ts

Box side (api/qqq_exec.py calls books_toggle_step):
  * reads the toggle doc ONLY at flat moments (no open lot): at boot when flat, then at most
    once per READ_EVERY_SEC while flat -- never per tick;
  * refuses unless the broker adapter's effective mode is PAPER (never LIVE, never touches the
    arm file or the LIVE config);
  * an unreadable / invalid doc changes NOTHING;
  * the only switch it drives is config.json's existing per-leg "legs_off" (applied through
    load_config from the local books_toggle_applied.json; config.json itself is never written).
    OFF or SHADOW on a box exec leg = in legs_off (no orders; MANAGER 11-19: the two differ only
    in the label / record -- the signal still shows on the shadow board); PAPER = not added.
    A leg missing from the doc changes nothing. Every leg without a box switch is record-only.
  * a toggle can only ever ADD a leg to legs_off; it never removes one config.json lists.
No decision or order-path logic lives here.
"""
import json
import os
import time

STATES = ("OFF", "SHADOW", "PAPER")
RANK = {"OFF": 0, "SHADOW": 1, "PAPER": 2}

# Gate flags: a leg whose class is "gated" stays at SHADOW max until its flag is True here (and in
# the JS mirror). Clear it in code, on purpose, after the must-fix lands.
GATES = {"pick6": False}

# What the QQQ box actually runs (api/cloud_signal.py LIVE_LEGS / SHADOW_LEGS):
#   ORB   run #314 (ORB_3_6_R6)          live paper exec leg ORB
#   NOISE run #382 (NOISE_1_8_CT304)     live paper exec leg NOISE
#   ENGU-Q run #335                      a no-order shadow TRACKER since 2026-10-09 (no live row)
#   NOISE #422 plain / fixed / KEEL      no-order shadow legs
#   NOISE #555.1 keel (CT304H_FT)       live paper exec leg NOISE555 (2026-11-22)
#   NOISE #545.1 keel (CT304H_KFX)      live paper exec leg NOISE545 (2026-11-22)
BOX_VERSION = {"ORB": "#314", "NOISE": "#382", "ENGUQ": "#335", "NOISE555": "#555.1 keel", "NOISE545": "#545.1 keel"}

_NQ = "NQ futures - no QQQ executor for this strategy"

# id -> {cls, max, exec_leg, reason, gate, feed}
#   cls  paper | shadow | gated | shadow_only | grey
#   max  the highest state the page / box will accept
BOOK_LEG_CLASS = {
    "ORB314":   {"cls": "paper", "max": "PAPER", "exec_leg": "ORB", "reason": "QQQ executor runs ORB #314", "gate": None, "feed": "cloud_signal ORB_R6"},
    "ORB234":   {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314, not #234", "gate": None, "feed": None},
    "ORB257":   {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314, not #257", "gate": None, "feed": None},
    "ORB421":   {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314, not #421", "gate": None, "feed": None},
    "ORB546":   {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314, not #546", "gate": None, "feed": None},
    "NOISE382": {"cls": "paper", "max": "PAPER", "exec_leg": "NOISE", "reason": "QQQ executor runs NOISE #382", "gate": None, "feed": "cloud_signal NOISE_382"},
    "NOISE555": {"cls": "paper", "max": "PAPER", "exec_leg": "NOISE555", "reason": "QQQ executor runs NOISE #555.1 keel", "gate": None, "feed": "cloud_signal NOISE_555"},
    "NOISE545": {"cls": "paper", "max": "PAPER", "exec_leg": "NOISE545", "reason": "QQQ executor runs NOISE #545.1 keel", "gate": None, "feed": "cloud_signal NOISE_545"},
    "NOISE422": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #422 (box shadow leg NOISE_422_PLAIN)", "gate": None, "feed": "cloud_signal NOISE_422_PLAIN"},
    "NOISE304": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #304", "gate": None, "feed": None},
    "NOISE398": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #398", "gate": None, "feed": None},
    "NOISE406": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #406", "gate": None, "feed": None},
    "ENGUQ335": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "order path flattens at close, the leg holds overnight; QQQ settings not tuned", "gate": None, "feed": "cloud_signal ENGUQ_335"},
    "ENGUQ407": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ENGU-Q #335, not #407", "gate": None, "feed": None},
    "PICK6":    {"cls": "gated", "max": "PAPER", "exec_leg": None, "reason": "gated: PICK6 probe + restart hook must-fix", "gate": "pick6", "feed": None},
    "OPUS86a":  {"cls": "gated", "max": "PAPER", "exec_leg": None, "reason": "gated: PICK6 probe + restart hook must-fix", "gate": "pick6", "feed": None},
    "GLDNIGHT": {"cls": "shadow_only", "max": "SHADOW", "exec_leg": None, "reason": "no GLD executor - owner: skip", "gate": None, "feed": None},
    "TTMx3":    {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": "ES futures, paper runs on NinjaTrader, not Webull", "gate": None, "feed": None},
    "OPUS55a":  {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": _NQ, "gate": None, "feed": None},
    "OPUS107a": {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": _NQ, "gate": None, "feed": None},
    "TTIBS300": {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": _NQ, "gate": None, "feed": None},
    "OPUS58c":  {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": _NQ, "gate": None, "feed": None},
    "OPUS58c_h": {"cls": "grey", "max": "OFF", "exec_leg": None, "reason": _NQ, "gate": None, "feed": None},
    # board 142 ML legs (11-22): research what-if rows, no order path
    "NOISE422_fixed": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #422 fixed tilts", "gate": None, "feed": None},
    "NOISE422_keel": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382, not #422 KEEL", "gate": None, "feed": None},
    "NOISE382_fixed": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs NOISE #382 KEEL, not the fixed-tilt version", "gate": None, "feed": None},
    "NOISE382_keel": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "as-if of the live NOISE #382.2 KEEL leg; record only", "gate": None, "feed": None},
    "ORB234_gate": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314, not #234 gated", "gate": None, "feed": None},
    "NOISE555_keel": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "as-if of NOISE #555.1 + KEEL v12; record only (board 170)", "gate": None, "feed": None},
    "NOISE545_keel": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "as-if of NOISE #545.1 + KEEL v12; record only (board 170)", "gate": None, "feed": None},
    "DISC525_hybrid": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "research, selection in-sample: DISC #525 hybrid logistic; record only (board 170)", "gate": None, "feed": None},
    "ENGUQ556": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "as-if of ENGU-Q #556 champion (run FAIL); record only (board 177)", "gate": None, "feed": None},
    "ORB314_gate": {"cls": "shadow", "max": "SHADOW", "exec_leg": None, "reason": "QQQ executor runs ORB #314 ungated, not the gated version", "gate": None, "feed": None},
}

APPLIED_NAME = "books_toggle_applied.json"
READ_EVERY_SEC = 600.0


def max_state(leg_id, gates=None):
    """The highest state `leg_id` may take now. Unknown ids = OFF only."""
    c = BOOK_LEG_CLASS.get(str(leg_id or ""))
    if not c:
        return "OFF"
    m = c["max"]
    if c["cls"] == "gated" and not (gates if gates is not None else GATES).get(c["gate"]):
        m = "SHADOW"
    return m


def allowed(leg_id, state, gates=None):
    return state in RANK and RANK[state] <= RANK[max_state(leg_id, gates)]


def validate(doc, gates=None):
    """(ok, legs, why). The whole doc is refused on ANY bad entry -- a half-valid set is never
    applied. legs = {leg id: state}."""
    if not isinstance(doc, dict):
        return False, None, "doc missing or not an object"
    legs = doc.get("legs")
    if not isinstance(legs, dict):
        return False, None, "no legs map"
    out = {}
    for k, v in legs.items():
        k, s = str(k), str(v or "").upper()
        if k not in BOOK_LEG_CLASS:
            return False, None, f"unknown leg {k!r}"
        if s not in STATES:
            return False, None, f"{k}: bad state {v!r}"
        if not allowed(k, s, gates):
            return False, None, f"{k}: {s} not allowed (max {max_state(k, gates)})"
        out[k] = s
    return True, out, "ok"


def effects(legs):
    """{leg id: what the box does} and the exec legs the set turns off."""
    eff, off = {}, []
    for k, s in sorted(legs.items()):
        ex = BOOK_LEG_CLASS[k]["exec_leg"]
        if ex and s == "OFF":
            eff[k] = f"{ex} off (legs_off)"
            off.append(ex)
        elif ex and s == "PAPER":
            eff[k] = f"{ex} on"
        elif ex:
            eff[k] = "SHADOW: no orders, signal on the shadow board"
            off.append(ex)
        else:
            eff[k] = "record only (no box switch)"
    return eff, sorted(set(off))


def applied_path(out_dir):
    return os.path.join(out_dir, APPLIED_NAME)


def load_applied(out_dir):
    """The last APPLIED set, or None. Never raises."""
    try:
        with open(applied_path(out_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def save_applied(out_dir, rec):
    os.makedirs(out_dir, exist_ok=True)
    p = applied_path(out_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
    os.replace(tmp, p)


def applied_legs_off(out_dir):
    """Exec legs the last applied set turns off ([] when none / unreadable). load_config adds
    these to config.json's legs_off -- it can only ADD."""
    d = load_applied(out_dir) or {}
    off = d.get("legs_off")
    return [x for x in off if isinstance(x, str)] if isinstance(off, list) else []


def _changed_lines(prev, new):
    p = (prev or {}).get("legs") or {}
    return [f"{k} {p.get(k, '-')}->{v}" for k, v in sorted(new.items()) if p.get(k) != v]


def step(*, out_dir, read_doc, broker_mode, flat, boot, mem, now=None, say=None,
         publish=None, log=print):
    """One check. Returns what happened (a short word) -- never raises.

    read_doc()  -> the toggle doc dict (raises / returns None when unreadable)
    broker_mode -> the adapter's effective mode string
    flat        -> True when no lot is open
    boot        -> True on the first call of the process
    mem         -> a dict this function keeps its throttle in
    say(line)   -> one phone line per applied change
    publish(rec)-> write the applied echo to Firestore"""
    try:
        now = time.time() if now is None else now
        if not flat:
            return "not flat"
        if not boot and now - float(mem.get("last_read") or 0) < READ_EVERY_SEC:
            return "throttled"
        if str(broker_mode or "").upper() != "PAPER":
            mem["last_read"] = now
            return "refused: broker mode is not PAPER"
        mem["last_read"] = now
        try:
            doc = read_doc()
        except Exception as e:
            log(f"[books-toggle] read failed ({type(e).__name__}) -- nothing changed")
            return "unreadable"
        if doc is None:
            return "no doc"
        ok, legs, why = validate(doc)
        if not ok:
            log(f"[books-toggle] invalid doc ({why}) -- nothing changed")
            src = str(doc.get("ts") if isinstance(doc, dict) else "")
            if mem.get("invalid_ts") != src:       # ONE line + echo per doc ts, not per read
                mem["invalid_ts"] = src
                prev = load_applied(out_dir) or {}
                rec = dict(prev, status="invalid", reason=str(why)[:160], src_ts=src,
                           applied_ts="invalid:" + src)
                if say is not None:
                    try:
                        say(rec, ("Books toggle REFUSED (invalid, nothing changed): " + why)[:180])
                    except Exception as e:
                        log(f"[books-toggle] phone line failed ({type(e).__name__})")
                if publish is not None:
                    try:
                        publish(rec)
                    except Exception as e:
                        log(f"[books-toggle] echo publish failed ({type(e).__name__})")
            return "invalid"
        prev = load_applied(out_dir)
        src_ts = doc.get("ts")
        if prev and prev.get("legs") == legs and prev.get("src_ts") == src_ts:
            return "same"
        eff, off = effects(legs)
        rec = {"legs": legs, "legs_off": off, "effects": eff, "src_ts": src_ts, "status": "applied",
               "applied_by": str(doc.get("by") or "page")[:40],
               "applied_ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + "Z"}
        save_applied(out_dir, rec)
        changes = _changed_lines(prev, legs)
        if changes and say is not None:
            try:
                say(rec, "Books toggle applied: " + ", ".join(changes)[:180])
            except Exception as e:
                log(f"[books-toggle] phone line failed ({type(e).__name__})")
        if publish is not None:
            try:
                publish(rec)
            except Exception as e:
                log(f"[books-toggle] echo publish failed ({type(e).__name__})")
        log(f"[books-toggle] applied {len(legs)} legs, legs_off+={off}")
        return "applied"
    except Exception as e:
        log(f"[books-toggle] step crashed ({type(e).__name__}: {e}) -- nothing changed")
        return "error"

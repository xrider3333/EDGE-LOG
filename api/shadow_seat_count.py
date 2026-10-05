"""SEAT-TEST cadence for the forward shadows on the NT8 PAPER board (STRATEGY-BEATING request, 2026-10-04).

When a forward shadow reaches 50 CLOSED forward trades, and again at every further 50, post one line to
the STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y inbox: 'shadow X reached N closed trades on DATE'. That lane
then runs its seat read (tools/rocfrontier/PREREG_MDL_R1.txt). A seat is an owner question, never an
automatic adoption - this module only counts and notifies.

Counted: trades of the leg that are CLOSED (not open) and FORWARD (backfill is False - the config was on the
board when the trade happened). Source: the nightly trade bundle (api/paper_bundle.py) - 1-3 Firestore reads.
State: C:\\EdgeLog\\shadow_seat_count.json remembers the last multiple of 50 reported per shadow, so a
re-run never posts twice and a missed night catches up with one line at the current count.

The order-flow size rule is NOT a board leg (it is scored on ORB / TTM trades by tools/orb_orderflow_shadow.py
and tools/ttm_orderflow_shadow.py, owned by those lanes), so it is not counted here.
"""
import datetime as dt
import json
import os
import subprocess
import sys

SHADOWS = {
    "DIP_ES_452": "DIP ES #452",
    "DIP_NQ_433": "DIP NQ #433",
    "ORB_239": "ORB #239",
    "ORB_257": "ORB #257",
    "TTM_458_KEEL": "TTM KEEL (#458)",
    "ENGUQ_335_S1": "ENGU-Q S1",
    "ENGUQ_335_S2": "ENGU-Q S2",
}
STEP = 50
TO_LANE = "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y"
STATE_PATH = r"C:\EdgeLog\shadow_seat_count.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def count_closed_forward(trades):
    """{leg: closed forward trade count} for the shadows in SHADOWS."""
    out = {k: 0 for k in SHADOWS}
    for t in trades or []:
        leg = t.get("leg")
        if leg not in out:
            continue
        if t.get("open") or t.get("backfill"):
            continue
        if not (t.get("close_day") or t.get("exitIso") or t.get("exitTime")):
            continue
        out[leg] += 1
    return out


def due_lines(counts, state, day):
    """(lines to post, new state). One line per shadow whose count crossed a new multiple of STEP."""
    new_state = dict(state or {})
    lines = []
    for leg, n in counts.items():
        mult = n // STEP
        if mult >= 1 and mult > int(new_state.get(leg, 0)):
            lines.append(f"shadow {SHADOWS[leg]} reached {mult * STEP} closed trades on {day}"
                         + (f" (now {n})" if n != mult * STEP else ""))
            new_state[leg] = mult
    return lines, new_state


def _read_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def _post(line):
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "chat_inbox.py"), "post", TO_LANE,
                    "--from", "PAPER-NT8", line], check=True, capture_output=True, text=True, timeout=60)


def run(trades, *, day=None, state_path=STATE_PATH, post=_post, dry_run=False, log=print):
    """Count, decide, post, remember. Returns the lines (posted or, with dry_run, would-post)."""
    day = day or dt.date.today().isoformat()
    counts = count_closed_forward(trades)
    lines, new_state = due_lines(counts, _read_state(state_path), day)
    log("shadow seat count: " + ", ".join(f"{SHADOWS[k]} {v}" for k, v in counts.items()))
    for ln in lines:
        log(("would post: " if dry_run else "posting: ") + ln)
        if not dry_run:
            post(ln)
    if lines and not dry_run:
        _write_state(state_path, new_state)
    return lines


def run_from_bundle(db, uid, **kw):
    from . import paper_bundle
    trades, _meta = paper_bundle.read_bundle(db, uid)
    if trades is None:
        (kw.get("log") or print)("shadow seat count: no trade bundle - skipped")
        return []
    return run(trades, **kw)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, ROOT)
    import firebase_admin
    from firebase_admin import credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
    from tools.paper_review_routine import UID
    from api import shadow_seat_count as me
    me.run_from_bundle(firestore.client(), UID, dry_run=a.dry_run)

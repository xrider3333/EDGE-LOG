"""One-off repair for the 2026-09-08 QQQ SHADOW feed_days entry.

WHAT HAPPENED (2026-09-08, second live shadow day): the adapter's 5s tick thread was
absent for roughly half the session -- ticks=2386 recorded where a full 09:25-16:05 ET
session at TICK_SEC=5 produces ~4740 expected ticks (api.qqq_exec._expected_ticks).
Causes: ~6 runner restarts by other sessions, plus 2,245 Firestore publish failures in
runner.log ("RetryError: Timeout of 60.0s exceeded ... 503 failed to connect to all
addresses", a known IPv6-to-googleapis problem on this box) -- each failed publish used
to BLOCK the tick loop for 60s (fixed separately in api/qqq_exec.py's non-blocking
_Publisher). The OLD uptime formula (1 - stale_ticks/ticks) only ever looked at ticks
that DID happen, so this day published as uptime_pct=1.0 / valid=true / readiness
days_valid=1 -- silently overstating the evidence the go-live decision rests on.

WHAT THIS SCRIPT DOES: nothing to the recorded ticks/stale_ticks (that IS what happened
-- the honest record). api/qqq_exec.py's _build_feed_days already recomputes
coverage_pct/uptime_pct/valid from those raw counts under the new coverage-based rule
(module docstring feature (2)), which alone already reads this day as invalid
(coverage_pct ~ 0.50). This script's only change is stamping an explicit, plain-English
`note` onto the STORED raw day (state.json's feed_days["2026-09-08"]) that names the
actual root cause, so the reconstruction reason travels with the record on the web tab
rather than only living in a chat log or runner.log.

Never touches trades.csv / orders.csv -- this is a feed-uptime bookkeeping fix only, not
a PnL correction. No shadow lot or order is created, modified, or removed.

Dry-run by default: prints the before/after and changes no files. --apply backs up the
current state.json to state.json.pre-repair, writes the updated state.json, and appends
one line to C:\\EdgeLog\\qqq_exec\\corrections.log. Idempotent: if the note is already
stamped (a prior --apply already ran), a second --apply is a no-op that says so, rather
than re-appending to corrections.log or re-copying the backup.

Run: python tools/qqq_exec_repair_20260908.py           (dry run)
     python tools/qqq_exec_repair_20260908.py --apply    (writes state.json + logs it)
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe  # noqa: E402

TARGET_DAY = "2026-09-08"
NOTE = ("reconstructed: adapter absent ~half the session (runner restarts + Firestore "
        "publish stalls) -- not valid evidence")


def _computed_read(state, day, label):
    row = next((d for d in qe._build_feed_days(state) if d["date"] == day), None)
    if row is None:
        print(f"[repair] ({label}) no computed feed_days row for {day}")
        return None
    print(f"[repair] ({label}) computed: ticks={row['ticks']} expected_ticks="
          f"{row['expected_ticks']} coverage_pct={row['coverage_pct']} "
          f"uptime_pct={row['uptime_pct']} valid={row['valid']} note={row['note']!r}")
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the change (default: dry-run, no files touched)")
    ap.add_argument("--state", default=qe.STATE_PATH,
                    help=f"override state.json path (default: {qe.STATE_PATH}, the real "
                         f"production file)")
    a = ap.parse_args()

    if not os.path.exists(a.state):
        print(f"[repair] no state file at {a.state} -- nothing to repair")
        return 1

    with open(a.state, encoding="utf-8") as f:
        state = json.load(f)

    feed_days = state.get("feed_days") or {}
    raw = feed_days.get(TARGET_DAY)
    if raw is None:
        print(f"[repair] no feed_days entry for {TARGET_DAY} in {a.state} -- nothing to repair")
        return 1

    print(f"[repair] {TARGET_DAY} BEFORE (raw stored): {json.dumps(raw)}")
    _computed_read(state, TARGET_DAY, "before")

    if str(raw.get("note") or "") == NOTE:
        print(f"[repair] {TARGET_DAY} already carries the reconstructed note -- "
              f"idempotent no-op, nothing to apply")
        return 0

    new_raw = dict(raw)
    new_raw["note"] = NOTE
    new_feed_days = dict(feed_days)
    new_feed_days[TARGET_DAY] = new_raw
    new_state = dict(state)
    new_state["feed_days"] = new_feed_days

    print(f"[repair] {TARGET_DAY} AFTER (raw stored): {json.dumps(new_raw)}")
    row = _computed_read(new_state, TARGET_DAY, "after")
    if row is not None:
        if row["valid"] is not False:
            print(f"[repair] WARNING: expected valid=False after the coverage-rule fix, "
                  f"got {row['valid']!r} -- check _expected_ticks/_build_feed_days before "
                  f"trusting this repair")
        if not (0.30 <= row["coverage_pct"] <= 0.70):
            print(f"[repair] WARNING: expected coverage_pct roughly ~0.50 for the "
                  f"2026-09-08 incident, got {row['coverage_pct']} -- double-check the "
                  f"recorded ticks before applying")

    if not a.apply:
        print("[repair] DRY RUN -- no files changed. Re-run with --apply to write.")
        return 0

    backup = a.state + ".pre-repair"
    shutil.copy2(a.state, backup)
    with open(a.state, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, default=str)
    print(f"[repair] wrote {a.state} (backup at {backup})")

    corrections_log = os.path.join(os.path.dirname(a.state) or qe.OUT_DIR, "corrections.log")
    os.makedirs(os.path.dirname(corrections_log) or ".", exist_ok=True)
    ticks = int(raw.get("ticks") or 0)
    expected = qe._expected_ticks(TARGET_DAY)
    coverage = round(ticks / expected, 4) if expected else 0.0
    with open(corrections_log, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
               f"qqq_exec_repair_20260908 --apply: feed_days[{TARGET_DAY}].note set to "
               f"{NOTE!r} (ticks={ticks} expected_ticks={expected} "
               f"coverage_pct~={coverage:.4f}); trades.csv/orders.csv untouched\n")
    print(f"[repair] appended to {corrections_log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

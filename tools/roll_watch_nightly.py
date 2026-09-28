"""THE UNATTENDED HALF OF roll_watch: measure the roll the evening it happens, append it,
and tell the lanes that are waiting for it.

WHY (TTM's ask, 2026-09-27). TTM's roll guard re-reads `tools/data/rolls_ES.csv` every run,
and the fake squeeze it guards against fires 0-2 days after a roll - so a row that lands a day
late is no use. The December 2026 expiry is Friday 12-18, and the switch will happen somewhere
in the ten days before it, on an evening nobody is watching. This runs on its own.

WHAT IT DOES, once per evening while a roll window is open:
  1. Measures the master-minus-capture step for each root (`tools/roll_watch.py`).
  2. Appends the row ONLY when the measurement is clean - a step of at least half the expected
     carry, with both sides quiet. Otherwise it writes nothing.
  3. Posts one line to TTM's inbox and to MANAGER's either way, so a silent night is visible
     as a silent night rather than as nothing having run.

WHAT IT WILL NOT DO. It will not append a row it is not sure of, and it will not append twice.
If it finds nothing, that is reported, not papered over - the calendar guard in
`augur_engine/roll_guard.py` arms for the whole window regardless of whether a row exists, so
a caller is protected either way. A row this writes carries `status=measured`, never `exact`.

It is safe to run on any day: outside a roll window it does nothing and says so.

    python tools/roll_watch_nightly.py             # measure, append if clean, post
    python tools/roll_watch_nightly.py --dry-run   # do everything except write or post
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import roll_guard, rolls  # noqa: E402
import tools.roll_watch as rw  # noqa: E402

ME = "ELWA-FEATURES"
TELL = ("TTM", "MANAGER")
ROOTS = ("ES", "NQ")


def post(chat, text, dry=False):
    if dry:
        print("   [dry-run] would post to %s" % chat)
        return
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "chat_inbox.py"),
                        "post", chat, "--from", ME, text],
                       cwd=ROOT, check=False, capture_output=True, timeout=120)
        print("   posted to %s" % chat)
    except Exception as e:
        print("   could not post to %s: %s" % (chat, e))


def one_root(root, dry):
    """Returns a one-line plain-English result for this root."""
    today = dt.date.today()
    win = roll_guard.roll_window_for(today)
    if not win:
        return None
    since = int(__import__("pandas").Timestamp(str(win[0]), tz="US/Eastern").timestamp())
    until = int(dt.datetime.now(dt.timezone.utc).timestamp())

    # already have it?
    have = [r for r in rolls.real_switches(root)
            if win[0] <= dt.date.fromtimestamp(r["switch_sec"]) < win[1]]
    if have:
        return ("%s: already recorded - %s, offset %s, status %s. Nothing to do."
                % (root, have[0]["switch_et"], have[0]["offset_pts"], have[0]["status"]))

    best, err = rw.measure(root, since, until)
    if best is None:
        return ("%s: no switch measured yet in this window (%s). The calendar guard is armed "
                "for the whole window regardless, so callers stay protected." % (root, err))
    if not best["clean"]:
        return ("%s: a step of %+.2f points was seen at %s, but the two sides are too noisy "
                "to trust (widest p5..p95 %.2f), so NOTHING was written. Worth a human look."
                % (root, best["offset"], best["et"], best["tightest"]))
    row, err = rw.append_row(root, best, dry=dry)
    if row is None:
        return "%s: not appended (%s)." % (root, err)
    return ("%s: MEASURED and %s - %s, offset %+.2f points (spread flat at %.2f over %d "
            "minutes before, %.2f over %d after), status measured, kind %s. TTM's guard will "
            "pick it up on its next run."
            % (root, "appended to tools/data/rolls_%s.csv" % root if not dry else "WOULD append",
               row["switch_et"], best["offset"], best["med_before"], best["n_before"],
               best["med_after"], best["n_after"], row["kind"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    today = dt.date.today()
    win = roll_guard.roll_window_for(today)
    if not win:
        nxt = min(e for y in (today.year, today.year + 1)
                  for e in roll_guard.quarterly_expiries(y) if e > today)
        print("Not in a roll window today (%s). The next expiry is %s, so the window opens %s."
              % (today, nxt, nxt - dt.timedelta(days=roll_guard.WINDOW_DAYS_BEFORE)))
        return 0

    print("Roll window open: %s .. %s (expiry %s)" % (win[0], win[1] - dt.timedelta(days=1), win[1]))
    lines = []
    for root in ROOTS:
        try:
            r = one_root(root, a.dry_run)
        except Exception as e:                      # never let one root stop the other
            r = "%s: the check failed with %s: %s" % (root, type(e).__name__, e)
        if r:
            print("  " + r)
            lines.append(r)

    if not lines:
        return 0
    appended = any("MEASURED and appended" in x for x in lines)
    head = ("Roll watch %s (expiry %s). %s"
            % (today, win[1], "A switch was measured and written to the roll table."
               if appended else "No switch written tonight."))
    body = head + "  " + "  ".join(lines)
    for chat in TELL:
        post(chat, body, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

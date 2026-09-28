"""ONE COMMITTED ROLL TABLE PER ROOT - the single source of truth for when NQ and ES
changed contract, and by how much.

WHY (owner GO on ROLL_AUDIT.md decision 13, 2026-09-26). Until now "when did the contract
roll" was answered by a detector that ran over whatever window a strategy happened to be
looking at. It found 19 of 64 NQ switches on RTH data (ROLL_AUDIT 2.2), and each strategy
file carried its own copy of it. A table removes the question: the switches are known, they
are written down once, and every consumer reads the same rows.

WHAT GOES IN. `tools/data/contract_switches_<root>.csv` already holds the ground truth,
recovered from `databento_raw` by the max-volume-per-UTC-day rule. This script turns it into
`tools/data/rolls_<root>.csv` with three additions, none of which are cosmetic:

  1. **The two `inferred_after_raw_end` rows are dropped.** ROLL_AUDIT 2.7 establishes that
     2026-06-14 18:10 and 2026-09-13 18:10 are ordinary weekend gaps on the still-June and
     still-September contract - NOT rolls. Leaving them in would back-adjust 412 and -384.5
     points of real weekend price move out of the series.
  2. **The four real 2026 tail switches are added**, which the raw feed cannot see because it
     stops on 2026-06-07. They are IN-BAR: the switch happened inside a single bar, so the
     bar opens on one contract and closes on the next.
  3. **Explicit not-a-roll rows** for the tail events that look like rolls, so a future reader
     does not have to re-litigate them.

THE 2026 TAIL OFFSETS ARE ESTIMATES, AND THE TABLE SAYS SO IN A COLUMN.
`status=estimated` with a confidence interval, against `status=exact` for the 64 rows
measured from the raw feed. They were raised as a blocker before this work started and the
owner said go anyway, so the honest thing is to carry the uncertainty in the data rather than
in a document nobody reads. Any consumer can refuse to trade across an estimated switch:
`rolls.py` exposes exactly that. Replacing them with measured values needs a Databento
re-pull for 2026-06..09 (ROLL_AUDIT 6.3 repair order, docs/DATA_TAIL_2026.md).

SIGN CONVENTION. `offset_pts` is NEW contract minus OLD contract at the last minute both
traded, so it is positive when the deferred contract is more expensive (contango) and
negative in backwardation. Both happen: 33 of 64 NQ switches and 39 of 64 ES switches are
NEGATIVE, nearly all of them in the near-zero-rate years, when the dividend yield beat
financing. Never assume a roll steps price up.

    python tools/build_roll_table.py                 # writes tools/data/rolls_NQ.csv, rolls_ES.csv
    python tools/build_roll_table.py --check         # verify the committed tables, write nothing
"""
import argparse
import csv
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tools", "data")
ET = "US/Eastern"

COLUMNS = ["root", "old", "new", "switch_sec", "switch_et", "offset_pts", "offset_ci_pts",
           "offset_sec", "kind", "source", "status", "note"]

# ---------------------------------------------------------------------------------------
# The 2026 tail. Everything the raw feed cannot see, stated once, with its evidence.
# Figures and reasoning: ROLL_AUDIT.md 2.7 (the event table and the "Offsets (V)" notes).
# ---------------------------------------------------------------------------------------

# Real switches, inside a single bar. `offset_pts` is the central estimate and
# `offset_ci_pts` the range the two independent methods agree on.
TAIL_ROLLS = [
    # root, ET timestamp of the bar the switch happened inside, old, new, offset, ci, source, note
    ("NQ", "2026-06-15 03:30", "NQM6", "NQU6", 293.0, "288..300", "cross_root",
     "In-bar: the 03:30 ET bar opens 30,252.00 and closes 30,563.00 on 5m (24h masters only; "
     "on RTH masters this switch falls cleanly between the 06-12 close and the 06-15 open). "
     "Estimate from the June-to-Sep contract spread on 06-01..06-05 (+0.967%), the one-step "
     "daily NQ/QQQ ratio change (+0.951%) and the NQ/ES minute-ratio step at 03:30."),
    ("ES", "2026-06-15 05:30", "ESM6", "ESU6", 64.0, "61..66", "cross_root",
     "In-bar: the 05:30 ET bar opens 7,521.50 and closes 7,584.50 on 5m (24h masters only). "
     "Estimate from the contract spread on 06-01..06-05 (+0.826%), the daily ES/SPY ratio "
     "change (+0.861%) and the minute-ratio step at 05:30 with NQ flat. NQ and ES rolled two "
     "hours apart, so neither root confirms the other's timing."),
    ("NQ", "2026-09-14 11:30", "NQU6", "NQZ6", 296.5, "292.50..300.50", "capture_spread",
     "In-bar, and on EVERY Yahoo-fed master this time, RTH and 24h: the 11:30 ET bar opens "
     "29,077.00 and closes 29,454.50 on 5m. MEASURED 2026-09-28 by tools/roll_watch.py: the "
     "master-minus-capture spread is flat at 0.00 over the 600 minutes before this bar and "
     "+296.50 over the 535 after, with a p5..p95 width of 8.00 on the later side. This "
     "replaces the original +295.00 estimate, which was the median over a window that also "
     "spanned the capture's OWN roll a day later.", "measured"),
    ("ES", "2026-09-14 11:30", "ESU6", "ESZ6", 67.75, "67.50..68.00", "capture_spread",
     "In-bar, on every Yahoo-fed master: the 11:30 ET bar opens 7,612.00 and closes 7,691.50 "
     "on 5m. MEASURED 2026-09-28 by tools/roll_watch.py: the master-minus-capture spread is "
     "flat at 0.00 over the 600 minutes before and +67.75 over the 539 after, with a p5..p95 "
     "width of 0.50. This confirms the original estimate to the tick.", "measured"),
]

# Events that look like rolls and are NOT. Recorded so nobody adjusts them out again.
NOT_ROLLS = [
    ("NQ", "2026-06-08 00:00", "feed_seam",
     "Databento-to-Yahoo hand-off, June contract on both sides. The Sunday 06-07 evening "
     "session is missing from the 1m 24h master. Jump +383.25 is a weekend move plus the "
     "missing session, not a carry."),
    ("ES", "2026-06-08 00:00", "feed_seam",
     "Same hand-off, June contract on both sides. Jump +48.75."),
    ("NQ", "2026-06-14 18:10", "weekend_gap",
     "Real June-contract weekend gap, +412.00. 18:00-18:09 is missing and the 18:10 bars "
     "have volume 0. This is one of the two rows the ground-truth file wrongly labelled "
     "inferred_after_raw_end."),
    ("ES", "2026-06-14 18:10", "weekend_gap",
     "Real June-contract weekend gap, +65.25. Wrongly labelled inferred_after_raw_end."),
    ("NQ", "2026-09-13 18:10", "weekend_gap",
     "Real September-contract weekend gap, -384.50; the NinjaTrader capture shows -394.0 "
     "over the same weekend. Wrongly labelled inferred_after_raw_end."),
    ("ES", "2026-09-13 18:10", "weekend_gap",
     "Real September-contract weekend gap, -50.00; the capture shows -51.5. Wrongly "
     "labelled inferred_after_raw_end."),
    ("NQ", "2026-08-06 00:09", "hole_end",
     "First bar after the 37-day summer hole, not a switch. The -780.75 step is five weeks "
     "of missing price. See docs/DATA_TAIL_2026.md."),
    ("ES", "2026-08-06 00:09", "hole_end",
     "First bar after the summer hole, +237.75 of missing price, not a switch."),
    ("NQ", "2026-09-08 00:00", "holiday_gap",
     "Labor Day: the holiday session and the Monday-evening reopen are missing. +177.50 is "
     "a real move."),
    ("ES", "2026-09-08 00:00", "holiday_gap",
     "Labor Day, +0.50. A real move."),
]


def _et_to_sec(stamp):
    """'YYYY-MM-DD HH:MM' in US/Eastern -> unix seconds."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
    except Exception:                                   # pragma: no cover
        import pytz
        tz = pytz.timezone(ET)
    naive = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    try:
        return int(naive.replace(tzinfo=tz).timestamp())
    except Exception:                                   # pragma: no cover - pytz path
        return int(tz.localize(naive).timestamp())


def classify_kind(switch_et):
    """Where in the trading day a switch landed.

    The 24-hour session opens at 18:00 ET. Every one of the 64 measured switches came
    between 18:00 and 20:02, so a switch stamped in the first minutes of the session is a
    REOPEN (nothing is holding across it on a 24h master beyond the session boundary), and
    a later one is MID_SESSION. On an RTH master both kinds fall between sessions.
    """
    hhmm = switch_et[11:]
    hh, mm = int(hhmm[:2]), int(hhmm[3:5])
    if hh == 18 and mm <= 10:
        return "reopen"
    return "mid_session"


def rows_for(root, src_dir=DATA):
    """Every table row for one root, earliest first."""
    out = []
    path = os.path.join(src_dir, "contract_switches_%s.csv" % root)
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["source"] != "databento_raw":
                # the two inferred_after_raw_end rows are weekend gaps, not rolls - see
                # NOT_ROLLS, which records them explicitly instead
                continue
            out.append(dict(
                root=root, old=r["old"], new=r["new"],
                switch_sec=int(r["switch_sec"]), switch_et=r["switch_et"],
                offset_pts="%.2f" % float(r["contract_offset"]),
                offset_ci_pts="", offset_sec=r["prev_bar_et"],
                kind=classify_kind(r["switch_et"]), source="databento_raw",
                status="exact", note=""))

    for entry in TAIL_ROLLS:
        rt, stamp, old, new, off, ci, source, note = entry[:8]
        # A tail row is ESTIMATED unless it has since been measured against a second feed.
        # The September 2026 pair were upgraded to `measured` on 2026-09-28; June cannot be,
        # because the NinjaTrader capture only starts 2026-06-23, after that switch.
        status = entry[8] if len(entry) > 8 else "estimated"
        if rt != root:
            continue
        out.append(dict(root=root, old=old, new=new, switch_sec=_et_to_sec(stamp),
                        switch_et=stamp, offset_pts="%.2f" % off, offset_ci_pts=ci,
                        offset_sec=stamp, kind="in_bar", source=source,
                        status=status, note=note))

    for rt, stamp, kind, note in NOT_ROLLS:
        if rt != root:
            continue
        out.append(dict(root=root, old="", new="", switch_sec=_et_to_sec(stamp),
                        switch_et=stamp, offset_pts="0.00", offset_ci_pts="",
                        offset_sec="", kind="not_a_roll", source=kind,
                        status="exact", note=note))

    out.sort(key=lambda r: r["switch_sec"])
    return out


def write(root, rows, out_dir=DATA):
    path = os.path.join(out_dir, "rolls_%s.csv" % root)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def summarise(root, rows):
    real = [r for r in rows if r["kind"] != "not_a_roll"]
    est = [r for r in real if r["status"] == "estimated"]
    meas = [r for r in real if r["status"] == "measured"]
    in_bar = [r for r in real if r["kind"] == "in_bar"]
    neg = [r for r in real if float(r["offset_pts"]) < 0]
    return ("%s: %d switches (%d exact, %d measured, %d ESTIMATED), %d in-bar, %d with a "
            "negative offset, plus %d not-a-roll rows. First %s, last %s."
            % (root, len(real), len(real) - len(est) - len(meas), len(meas), len(est),
               len(in_bar), len(neg), len(rows) - len(real),
               real[0]["switch_et"], real[-1]["switch_et"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="rebuild in memory and compare against the committed tables")
    ap.add_argument("--out", default=DATA)
    a = ap.parse_args()

    bad = 0
    for root in ("NQ", "ES"):
        rows = rows_for(root)
        print(summarise(root, rows))
        if a.check:
            path = os.path.join(a.out, "rolls_%s.csv" % root)
            if not os.path.exists(path):
                print("  MISSING %s" % path)
                bad += 1
                continue
            with open(path, encoding="utf-8") as fh:
                have = list(csv.DictReader(fh))
            if len(have) != len(rows):
                print("  DIFFERS: committed has %d rows, rebuild has %d" % (len(have), len(rows)))
                bad += 1
                continue
            diffs = [(i, k) for i, (h, r) in enumerate(zip(have, rows))
                     for k in COLUMNS if str(h.get(k, "")) != str(r.get(k, ""))]
            if diffs:
                print("  DIFFERS on %d field(s), first: row %d field %s" % (len(diffs), diffs[0][0], diffs[0][1]))
                bad += 1
            else:
                print("  committed table matches the rebuild exactly")
        else:
            print("  wrote", write(root, rows, a.out))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

# Builds tools/data/ndx_members.csv - point-in-time Nasdaq-100 membership for NQBRD r1 (PREREG_ALPACA_R1.txt, family B).
# Source: tools/data/ndx_members_wikipedia.json = the Wikipedia 'Nasdaq-100' Components list in the revision in effect on
# the first of each month, 2016-06 .. 2026-07 (read 2026-09-30, before any stock bar existed on the machine).
# Rule: the list known at the START of a month is the membership for that whole month (no look-ahead; changes during a
# month count from the next month). Patch: the mid-2016 revisions kept an April-2016 list, so the dated changes in the
# article's own "Changes in 2016" log are applied from the first month after each (XRAY 06-20, MCHP 07-18, SHPG 10-19).
# Wikipedia removed the Components section in July 2026; the 2026-07 list stays in force after it (forward stretch only).
# Tickers are as the list printed them at the time (FB until 2022-06, PCLN until 2018-03 ...); symbol renames are mapped
# when bars are pulled, not here.
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
PATCH_2016 = {"2016-07-01": ({"XRAY"}, {"LMCA", "LMCK", "BATRA", "BATRK"}),
              "2016-08-01": ({"MCHP"}, {"ENDP"}),
              "2016-11-01": ({"SHPG"}, {"LLTC"})}


def monthly():
    js = json.load(open(os.path.join(DATA, "ndx_members_wikipedia.json"), encoding="utf-8"))
    cur, out = set(js["base"].split()), []
    for month, revid, at, how, note, add, rem, count in js["months"]:
        cur = (cur | set(add.split())) - set(rem.split())
        assert len(cur) == count, (month, len(cur), count)          # transcription check against the page's own count
        out.append([month, revid, at, how, note, set(cur)])
    patched, extra_add, extra_rem = [], set(), set()
    for month, revid, at, how, note, members in out:
        if month in PATCH_2016:
            a, r = PATCH_2016[month]
            extra_add |= a; extra_rem |= r
        if month >= "2016-12-01":                                    # the 2016-12 revision already holds all three changes
            assert extra_add <= members and not (extra_rem & members), month
            extra_add, extra_rem = set(), set()
        m = (members | extra_add) - extra_rem
        patched.append([month, revid, at, how, note, m, sorted(extra_add), sorted(extra_rem)])
    return patched


def main():
    rows = monthly()
    months = [r[0] for r in rows]
    intervals, open_from = [], {}
    for i, (month, *_rest) in enumerate(rows):
        members = rows[i][5]
        prev = rows[i - 1][5] if i else set()
        for t in sorted(members - prev):
            open_from[t] = month
        for t in sorted(prev - members):
            intervals.append((t, open_from.pop(t), month))
    for t, f in sorted(open_from.items()):
        intervals.append((t, f, ""))                                  # still a member at the last list (2026-07)
    intervals.sort()
    with open(os.path.join(DATA, "ndx_members.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "from", "to"])                         # from inclusive, to exclusive (month starts); '' = open
        w.writerows(intervals)
    with open(os.path.join(DATA, "ndx_members_sources.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "wikipedia_revid", "revision_utc", "method", "list_note", "members", "patch_added", "patch_removed"])
        for month, revid, at, how, note, m, pa, pr in rows:
            w.writerow([month, revid, at, how, note, len(m), " ".join(pa), " ".join(pr)])
    print(f"{len(intervals)} membership intervals for {len({t for t, _, _ in intervals})} tickers, months {months[0]} .. {months[-1]}; "
          f"members per month {min(len(r[5]) for r in rows)}-{max(len(r[5]) for r in rows)}")


def members_on(day, path=None):
    """Tickers that were members on a date (YYYY-MM-DD) - for the NQBRD harness."""
    m = day[:7] + "-01"
    with open(path or os.path.join(DATA, "ndx_members.csv"), encoding="utf-8") as fh:
        return sorted(r["ticker"] for r in csv.DictReader(fh) if r["from"] <= m and (r["to"] == "" or m < r["to"]))


if __name__ == "__main__":
    main()

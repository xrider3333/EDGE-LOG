r"""WHICH PULL WAS THIS COMPUTED ON, AND DOES THE VENDOR STILL SAY THE SAME THING?

    python tools/alpaca_provenance.py --list                      every series, newest pull each
    python tools/alpaca_provenance.py --list GE                   one symbol's pull history
    python tools/alpaca_provenance.py --changed                   series the vendor has revised
    python tools/alpaca_provenance.py --check GE --timeframe 1Day --start 2021-07-01 --end 2021-08-31

`--check` RE-PULLS from Alpaca and compares the result with the newest recorded pull, printing
"cache differs from a fresh pull" when they disagree. That is not a bug report: Alpaca computes
`adjustment=split` at query time and corrects its own history - GE's 2021-07-30 daily bar came
back 12.95 at ~15:45 and 103.60 at ~17:20 the same afternoon - so the right response is to
RE-PULL rather than patch, and to treat results built on the older pull as suspect.

It costs one request per 10,000 bars and goes through the shared account pace, so a narrow
--start/--end is polite to the other four lanes.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from augur_engine import pull_provenance as prov  # noqa: E402

EXIT_DIFFERS = 2        # so a nightly job can gate on it; 1 = could not answer


def _print_rows(rows):
    for r in rows:
        print("  " + prov.describe(r))
        if r.get("wrote_to"):
            print("      -> %s" % r["wrote_to"])


def cmd_list(symbol=None):
    rows = prov.read_all()
    if not rows:
        print("No pulls recorded yet (%s)." % prov.manifest_path())
        print("Every fetch_bars call files one from now on; nothing backfills the past.")
        return 0
    if symbol:
        want = symbol.upper()
        rows = [r for r in rows if r.get("symbol") == want]
        if not rows:
            print("No recorded pulls for %s." % want)
            return 0
        rows.sort(key=lambda r: r.get("pulled_at_epoch") or 0, reverse=True)
        print("%s - %d recorded pull(s), newest first:" % (want, len(rows)))
        _print_rows(rows)
        return 0
    newest = {}
    for r in rows:
        k = r.get("series")
        if k not in newest or (r.get("pulled_at_epoch") or 0) > (newest[k].get("pulled_at_epoch") or 0):
            newest[k] = r
    print("%d series, %d pulls recorded in %s:"
          % (len(newest), len(rows), prov.manifest_path()))
    _print_rows(sorted(newest.values(), key=lambda r: r.get("symbol") or ""))
    return 0


def cmd_changed():
    rows = prov.read_all()
    series = sorted({(r.get("symbol"), r.get("timeframe"), r.get("adjustment"), r.get("feed"))
                     for r in rows})
    found = 0
    for sym, tf, adj, feed in series:
        pairs = prov.changed_between_pulls(sym, tf, adj, feed)
        for older, newer in pairs:
            found += 1
            print("%s %s %s: the vendor's answer CHANGED" % (sym, tf, adj))
            print("    %s -> %s rows, %s -> %s"
                  % ("{:,}".format(older.get("rows") or 0),
                     "{:,}".format(newer.get("rows") or 0),
                     older.get("pulled_at"), newer.get("pulled_at")))
    if not found:
        print("No series has been pulled twice with a differing result.")
        print("That is the expected state; it is not proof the vendor never revises.")
    return 0


def cmd_check(symbol, timeframe, start, end, adjustment, feed):
    from tools.import_alpaca_stocks import fetch_bars    # noqa: WPS433 - CLI-only import
    from augur_engine import alpaca_keys
    key, secret = alpaca_keys.load_keys()
    print("re-pulling %s %s %s..%s (adjustment=%s, feed=%s)"
          % (symbol, timeframe, start, end, adjustment, feed))
    df = fetch_bars(symbol, timeframe, start, end, key, secret,
                    feed=feed, adjustment=adjustment)
    # fetch_bars has just filed its own receipt for THIS pull, so compare against the one before
    # it rather than against itself.
    hist = prov.history(symbol, timeframe, adjustment, feed)
    if len(hist) < 2:
        print("This is the first recorded pull of that series, so there is nothing to compare "
              "it with. It is now on record: %s" % prov.describe(hist[0] if hist else None))
        return 0
    prev = hist[1]
    if prev.get("content_hash") == prov.content_hash(df):
        print("unchanged since the pull of %s (%s rows)"
              % (prev.get("pulled_at"), "{:,}".format(prev.get("rows") or 0)))
        return 0
    print("cache differs from a fresh pull: %s %s was pulled %s with %s rows (%s); the vendor "
          "now returns %s rows (%s)."
          % (symbol, timeframe, prev.get("pulled_at"),
             "{:,}".format(prev.get("rows") or 0), (prev.get("content_hash") or "?")[:19],
             "{:,}".format(len(df)), prov.content_hash(df)[:19]))
    print("Alpaca computes adjustment=%s at QUERY TIME and corrects its own history, so RE-PULL "
          "rather than patch the cache, and treat any result computed on the older pull as "
          "suspect." % adjustment)
    return EXIT_DIFFERS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", nargs="?", const="", metavar="SYMBOL",
                    help="recorded pulls; a symbol narrows it to that one's history")
    ap.add_argument("--changed", action="store_true",
                    help="series whose answer changed between two pulls of the same window")
    ap.add_argument("--check", metavar="SYMBOL", help="re-pull and compare with the last record")
    ap.add_argument("--timeframe", default="1Day")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--adjustment", default="split")
    ap.add_argument("--feed", default="sip")
    a = ap.parse_args(argv)

    if a.check:
        if not (a.start and a.end):
            ap.error("--check needs --start and --end, so the window matches a recorded pull")
        return cmd_check(a.check.upper(), a.timeframe, a.start, a.end, a.adjustment, a.feed)
    if a.changed:
        return cmd_changed()
    if a.list is not None:
        return cmd_list(a.list or None)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

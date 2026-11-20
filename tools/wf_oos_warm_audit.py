"""READ-ONLY: which stored validate.wf_oos blocks the warm-start fix would change, and why.

WHAT THIS ANSWERS, and it is the question MANAGER asked before any re-backfill (2026-11-20).
tools/backfill_wf_oos.py replayed every fold COLD. "Warm starts for every scored out-of-sample
stretch" (7a95b816) landed 2026-09-20, and since then validate scores each fold from
auto.WARM_DAYS sessions earlier, carrying in a position already open when the stretch begins. So
the verifier could not reproduce such a fold -- and because a fold mismatch REFUSES the whole
block, the failure mode was always "cannot verify", never a wrong number written.

That distinction decides whether anything stored has to be rebuilt, so this tool measures it
instead of assuming it. For every run doc it reads only the fields it needs and sorts the run
into one of five buckets:

  BLOCK FROM THE VALIDATE (src 'validate')   correct by construction - the validate wrote it with
                                             the same warm scoring it used, cold replay never
                                             touched it
  BACKFILLED, COLD ERA                       replayed cold, validated cold: right either way
  BACKFILLED, WARM ERA                       the ONLY bucket where a stored block could be wrong,
                                             because a cold replay produced a block for a warm
                                             run. --replay re-reads these fold by fold
  NO BLOCK, WARM ERA                         coverage the cold verifier cannot reach today; the
                                             fix makes these backfillable
  NO BLOCK, COLD ERA                         ordinary remaining backfill work, unaffected

Nothing is written, no Firestore field is updated, and --replay only READS market data. Pass
--replay to re-verify the at-risk bucket fold by fold under both arms and print the deltas; it
is off by default because each replay loads a full master and takes minutes.

    python tools/wf_oos_warm_audit.py
    python tools/wf_oos_warm_audit.py --replay
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import backfill_wf_oos as B                                      # noqa: E402

FIELDS = ["id", "timestamp", "strategy", "instrument", "timeframe", "data_source",
          "validate.wf_ran", "validate.wf_best_mode", "validate.wf_oos.src",
          "validate.wf_oos.v", "validate.wf_oos.trades", "validate.wf_oos.net",
          "validate.wf_oos.backfill.warm_days"]


def classify(d):
    """-> (bucket, warm_days, why) for one run doc. Pure, so it is readable on its own."""
    v = d.get("validate") if isinstance(d.get("validate"), dict) else {}
    if v.get("wf_ran") is not True:
        return "no walk-forward", None, "validate.wf_ran is not True"
    warm_days, why = B.warm_days_for_doc(d)
    block = v.get("wf_oos") if isinstance(v.get("wf_oos"), dict) else None
    warm = warm_days > 0
    if block is None:
        return ("no block, warm era" if warm else "no block, cold era"), warm_days, why
    if block.get("src") != "backfill":
        return "block from the validate", warm_days, why
    return ("backfilled, WARM era" if warm else "backfilled, cold era"), warm_days, why


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", action="store_true",
                    help="re-verify the at-risk bucket fold by fold (reads market data, slow)")
    ap.add_argument("--limit", type=int, default=0, help="cap the replays (0 = all of them)")
    a = ap.parse_args(argv)

    db = B._db()
    runs = db.collection("users").document(B.UID).collection("runs")
    buckets, rows = {}, []
    for s in runs.select(FIELDS).stream():
        d = s.to_dict() or {}
        bucket, warm_days, why = classify(d)
        buckets.setdefault(bucket, []).append((d.get("id") or s.id, d, warm_days, why))
        rows.append(bucket)

    print("WARM-START AUDIT of stored validate.wf_oos blocks   (read-only)")
    print("warm starts landed %s; auto.WARM_DAYS is %d today"
          % (B.WARM_STARTS_FROM, B._warm_days_now()))
    print("%d run doc(s) read" % len(rows))
    print()
    order = ["backfilled, WARM era", "no block, warm era", "block from the validate",
             "backfilled, cold era", "no block, cold era", "no walk-forward"]
    for b in order:
        got = buckets.get(b) or []
        print("  %-26s %4d" % (b, len(got)))
    extra = [b for b in buckets if b not in order]
    for b in extra:
        print("  %-26s %4d" % (b, len(buckets[b])))
    print()

    at_risk = buckets.get("backfilled, WARM era") or []
    if not at_risk:
        print("NOTHING STORED IS AFFECTED. No backfilled block belongs to a warm-era run, so no")
        print("stored block would change: the cold verifier refused warm-era runs rather than")
        print("writing a wrong block for one. The fix changes what can be VERIFIED from here on,")
        print("not any number already saved - so there is no re-backfill to decide about.")
    else:
        print("%d BACKFILLED BLOCK(S) BELONG TO WARM-ERA RUNS - these are the ones to decide on:"
              % len(at_risk))
        for rid, d, wd, why in sorted(at_risk, key=lambda x: str(x[1].get("timestamp") or "")):
            w = ((d.get("validate") or {}).get("wf_oos") or {})
            print("  run %-6s %s  %-34s stored: %s trades, net %s pts   (%s)"
                  % (rid, d.get("timestamp"), d.get("strategy"), w.get("trades"), w.get("net"),
                     why))
        if a.replay:
            print()
            print("RE-VERIFYING fold by fold (read-only; the era arm first, then the other):")
            todo = at_risk[:a.limit] if a.limit else at_risk
            for rid, d, wd, why in todo:
                print()
                print("-" * 78)
                B.one(db, rid, write=False, log=print)
        else:
            print()
            print("Pass --replay to re-verify these fold by fold (reads market data, slow).")

    uncov = buckets.get("no block, warm era") or []
    if uncov:
        print()
        print("%d warm-era run(s) carry NO block at all - coverage the cold verifier could not"
              % len(uncov))
        print("reach, and what the fix opens up. Newest first:")
        for rid, d, wd, why in sorted(uncov, key=lambda x: str(x[1].get("timestamp") or ""),
                                      reverse=True)[:20]:
            print("  run %-6s %s  %s %s" % (rid, d.get("timestamp"), d.get("strategy"),
                                            d.get("instrument")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

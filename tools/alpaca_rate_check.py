r"""Prove the account-wide Alpaca pace across REAL processes. Takes about a minute.

WHY THIS EXISTS AS A TOOL AND NOT A TEST. The unit tests in tests/test_alpaca_rate.py drive an
injected clock, so they run instantly and cover the arithmetic, the failure modes and the
invariant. What they cannot do is run four processes against one file on this filesystem - and
that is the thing that found both real defects in the limiter:

  - The first version used an O_EXCL lock FILE with a timestamp inside it and a stale-breaker.
    Its two constants were the wrong way round (break at 15s, give up at 10s), so a leftover lock
    could never be broken. One process waited its full 10 seconds, failed open, and sent an
    UNRECORDED request. Ten requests at a cap of six put NINE into one 60-second window and
    recorded four.
  - With an OS lock instead (released by the kernel when the handle closes or the process dies):
    twelve requests across four processes, worst window six, all six of the budget recorded, the
    opening cluster spread 0.124s instead of 15.076s.

Run it after any change to the locking or the window arithmetic:

    python tools/alpaca_rate_check.py            # 4 lanes, 3 requests each, cap 6
    python tools/alpaca_rate_check.py --lanes 5 --each 4 --limit 10

It writes only to a temporary directory - never the real state file - and makes no network call.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = """import sys, time
sys.path.insert(0, %r)
from augur_engine import alpaca_rate as r
path, n, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
granted = []
for _ in range(n):
    r.wait(path, limit=limit)
    granted.append(time.time())
print(repr(granted))
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", type=int, default=4, help="how many processes pull at once")
    ap.add_argument("--each", type=int, default=3, help="requests per process")
    ap.add_argument("--limit", type=int, default=6, help="the cap to test against")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as d:
        state = os.path.join(d, "state", "alpaca_rate.json")
        child = os.path.join(d, "child.py")
        with open(child, "w", encoding="utf-8") as fh:
            fh.write(CHILD % ROOT)

        t0 = time.time()
        procs = [subprocess.Popen([sys.executable, child, state, str(a.each), str(a.limit)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(a.lanes)]
        granted, failed = [], []
        for p in procs:
            out, err = p.communicate(timeout=600)
            if p.returncode != 0:
                failed.append(err.strip()[-400:])
                continue
            granted += eval(out.strip())            # a list of floats this script just wrote
        if failed:
            for f in failed:
                print("a lane failed:", f)
            return 1
        granted.sort()
        elapsed = time.time() - t0

        # The invariant: no 60-second window anywhere holds more than the cap.
        worst, worst_at = 0, 0.0
        for i, t in enumerate(granted):
            n = sum(1 for x in granted[i:] if x < t + 60.0)
            if n > worst:
                worst, worst_at = n, t - granted[0]

        recorded = len(json.load(open(state, encoding="utf-8"))["requests"])
        spread = granted[min(a.limit, len(granted)) - 1] - granted[0]

        print("%d lanes x %d requests = %d, cap %d"
              % (a.lanes, a.each, len(granted), a.limit))
        print("worst 60s window : %d   (starting %.3fs in)" % (worst, worst_at))
        print("opening cluster  : %.3fs for the first %d" % (spread, min(a.limit, len(granted))))
        print("recorded in state: %d of the %d that should be in the live window"
              % (recorded, min(a.limit, len(granted))))
        print("elapsed          : %.1fs" % elapsed)

        bad = []
        if worst > a.limit:
            bad.append("%d requests in one 60s window against a cap of %d - the account went "
                       "over" % (worst, a.limit))
        if recorded < min(a.limit, len(granted)):
            bad.append("only %d requests were recorded: something failed open, so the next lane "
                       "to ask will be told there is more budget than there is" % recorded)
        if spread > 5.0:
            bad.append("the first %d took %.1fs - a lane is waiting on the lock, not on the cap"
                       % (min(a.limit, len(granted)), spread))
        for b in bad:
            print("FAIL:", b)
        print("PASS" if not bad else "FAILED")
        return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

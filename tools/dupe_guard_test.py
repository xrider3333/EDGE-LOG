"""
Exercise the duplicate-work guard against the incident that caused it.

Run it:  python tools/dupe_guard_test.py            (offline, synthetic jobs)
         python tools/dupe_guard_test.py --live     (also replays the real 2026-08-18 jobs)

The offline half needs nothing but the repo. The --live half reads the owner's own
backtest jobs out of Firestore read-only, replays the four NOISE validate jobs that ran
twice on 2026-08-18, and proves the guard would have caught every one of them.

Every case asserts BOTH directions, because a guard that flags everything is as useless
as one that flags nothing:
  * a true repeat is DETECTED, and
  * a job differing in exactly one meaningful field is NOT flagged.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import dupe_guard as dg  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

# A realistic pinned NOISE validate job, shaped exactly like the real ones.
BASE = {
    "type": "validate", "strategy": "NOISE_1_1_SBS.py",
    "date_from": "2010-06-07", "date_to": "2026-08-12",
    "instrument": "NQ", "timeframe": "5m", "source": "db_noadj_rth", "session": "rth",
    "mult": 20, "cost_pts": 0.533, "commission_usd": 5.66, "slippage_pts": 0.25,
    "discover": "auto", "n_trials": 300, "n_rounds": 5, "wf_folds": 0,
    "lockbox_months": 18, "min_trades": 30, "transfer_to": "ES", "dsr": True,
    # cosmetic: must never affect the fingerprint
    "note": "the original note", "provider": "claude-cli", "workers": 4,
    "equity_points": 400, "status": "done", "finishedAt": 1787064394.0,
}


def _passed(ok, label, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -- " + detail) if detail else ""))
    return ok


def offline_cases():
    print("\nOFFLINE CASES -- synthetic jobs, no network")
    ok = True

    # 1. The exact incident: same work, DIFFERENT free-text note. Must be caught.
    again = dict(BASE, note="a different note written by the second session",
                 status="queued", finishedAt=None)
    m = dg.scan_for_duplicate(again, [("job-original", BASE)])
    ok &= _passed(m is not None and m["job_id"] == "job-original",
                  "identical work with a different note IS detected",
                  "this is the exact shape of the 2026-08-18 incident")

    # 2. The old broken check, for contrast: looking only at in-flight jobs finds nothing.
    inflight_only = [(i, j) for i, j in [("job-original", BASE)]
                     if j.get("status") in ("queued", "running")]
    ok &= _passed(dg.scan_for_duplicate(again, inflight_only) is None,
                  "the OLD in-flight-only check misses it",
                  "which is precisely why the four runs happened")

    # 3. Cosmetic-only differences must never split the fingerprint.
    cosmetic = dict(BASE, note="x", provider="ollama", workers=1, equity_points=800,
                    mc_sims=500, progress=100, elapsed_s=99.0)
    ok &= _passed(dg.job_fingerprint(cosmetic) == dg.job_fingerprint(BASE),
                  "provider / workers / chart resolution do NOT change the fingerprint")

    # 4. Integer vs float, and blank vs missing, must not read as a difference.
    loose = dict(BASE, mult=20.0, n_trials=300.0, date_to="2026-08-12")
    ok &= _passed(dg.job_fingerprint(loose) == dg.job_fingerprint(BASE),
                  "20 and 20.0 are the same multiplier")

    # 5. NOT-A-DUPLICATE: one meaningful field changed at a time. None may be flagged.
    singles = [
        ("date_to", "2026-08-19", "a later end date is a run on newer data"),
        ("date_from", "2012-01-03", "a different start date is a different window"),
        ("strategy", "NOISE_1_1_SBA.py", "a different strategy file"),
        ("source", "tv", "a different data master"),
        ("session", "eth", "a different session"),
        ("instrument", "ES", "a different contract"),
        ("mult", 50, "a different multiplier"),
        ("cost_pts", 0.75, "a different cost assumption"),
        ("commission_usd", 4.00, "a different commission"),
        ("slippage_pts", 0.5, "a different slippage"),
        ("n_trials", 500, "a wider search"),
        ("n_rounds", 8, "more search rounds"),
        ("lockbox_months", 12, "a different lockbox length"),
        ("min_trades", 50, "a different trade floor"),
        ("wf_folds", 8, "walk-forward folds turned on"),
        ("discover", "none", "a grid-constrained search"),
        ("transfer_to", None, "no transfer check"),
        ("type", "grid", "a different job type"),
    ]
    for field, value, why in singles:
        cand = dict(BASE, status="queued", finishedAt=None)
        cand[field] = value
        m = dg.scan_for_duplicate(cand, [("job-original", BASE)])
        ok &= _passed(m is None, "NOT flagged when only %s differs" % field, why)

    # 6. A failed job is not a duplicate -- rerunning it is a retry, which is wanted.
    broke = dict(BASE, status="error", error="boom")
    ok &= _passed(dg.scan_for_duplicate(dict(BASE, status="queued"),
                                        [("job-broken", broke)]) is None,
                  "a job that ERRORED is not treated as a duplicate",
                  "repeating a failure is a retry, not wasted work")

    # 7. The explanation names the field, so a near miss can be audited.
    d = dg.explain_difference(BASE, dict(BASE, date_to="2026-08-19"))
    ok &= _passed(list(d) == ["date_to"], "the difference is explainable",
                  "reports exactly: %r" % d)
    return ok


def live_cases():
    print("\nLIVE CASES -- replaying the real 2026-08-18 jobs from Firestore (read-only)")
    import firebase_admin
    from firebase_admin import credentials, firestore
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred = credentials.Certificate(os.path.join(root, "serviceAccount.json"))
    try:
        firebase_admin.initialize_app(cred)
    except ValueError:
        pass
    db = firestore.client()
    col = db.collection("users").document(UID).collection("backtests")
    jobs = [(s.id, s.to_dict() or {}) for s in col.stream()]
    print("  read %d backtest job documents" % len(jobs))

    noise = [(i, j) for i, j in jobs
             if j.get("type") == "validate" and "NOISE_1_1" in str(j.get("strategy", ""))]
    print("  %d of them are NOISE_1_1 validate jobs" % len(noise))

    ok = True
    # Group the real jobs by fingerprint. The four configurations that ran twice must
    # come out as four groups of two, and the one that ran once as a group of one.
    groups = {}
    for i, j in noise:
        groups.setdefault(dg.job_fingerprint(j), []).append((i, j))
    twos = [g for g in groups.values() if len(g) == 2]
    ones = [g for g in groups.values() if len(g) == 1]
    print("  grouped by fingerprint: %d configurations run twice, %d run once"
          % (len(twos), len(ones)))
    for g in sorted(groups.values(), key=lambda g: g[0][1].get("strategy", "")):
        print("     %-24s x%d" % (g[0][1].get("strategy"), len(g)))
    ok &= _passed(len(twos) == 4 and len(ones) == 1,
                  "the guard recovers the incident exactly: 4 doubled, 1 single")

    # Now replay it properly: take each SECOND job and ask the guard, as the runner
    # would, whether it repeats something already finished.
    for g in twos:
        g_sorted = sorted(g, key=lambda x: dg._finished_at(x[1]))
        first_id, first = g_sorted[0]
        second_id, second = g_sorted[1]
        m = dg.scan_for_duplicate(second, jobs, exclude_ids=(second_id,))
        hit = m is not None and m["job_id"] == first_id
        ok &= _passed(hit, "%s: the repeat is caught, pointing at the original"
                      % first.get("strategy"),
                      dg.describe(m) if m else "no match")

    # And the configuration that only ran once must NOT be flagged.
    for g in ones:
        only_id, only = g[0]
        m = dg.scan_for_duplicate(only, jobs, exclude_ids=(only_id,))
        ok &= _passed(m is None, "%s ran once and is NOT flagged" % only.get("strategy"))

    # A genuinely new job that differs in exactly one meaningful field must pass clean.
    if noise:
        _, sample = noise[0]
        fresh = dict(sample, date_to="2026-08-20", status="queued", finishedAt=None)
        m = dg.scan_for_duplicate(fresh, jobs)
        ok &= _passed(m is None,
                      "the same configuration on NEWER data is NOT flagged",
                      "only date_to changed: %r" % dg.explain_difference(sample, fresh))
    return ok


if __name__ == "__main__":
    good = offline_cases()
    if "--live" in sys.argv:
        good = live_cases() and good
    print("\nRESULT: " + ("ALL CHECKS PASSED" if good else "SOMETHING FAILED"))
    sys.exit(0 if good else 1)

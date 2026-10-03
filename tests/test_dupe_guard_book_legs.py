"""
dupe_guard reads a BOOK's legs (pre-run review round 2, 2026-10-03).

WHY: book jobs carry their legs under "legs" (api/runner.py hands job.get("legs") to run_book),
but MATERIAL_FIELDS named only "book_legs". Two books with DIFFERENT legs on the same window and
name fingerprinted identically, so the second was marked a repeat of the first. "legs" is now
material ("book_legs" kept). A job with no "legs" key - every non-book job - fingerprints exactly
as before; the golden below was computed with the pre-edit module.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import dupe_guard as DG

LEG_A = {"strategy": "NOISE_1_0.py", "params": {"k": 1.5, "n": 20}, "instrument": "NQ", "weight": 1}
LEG_B = {"strategy": "ORB_3_6.py", "params": {"or_min": 30}, "instrument": "NQ", "weight": 1}
BOOK = {"type": "book", "strategy": "BOOK 463", "date_from": "2016-07-01", "date_to": "2026-06-30",
        "lockbox_months": 12, "legs": [LEG_A, LEG_B]}

NON_BOOK = {"type": "validate", "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m", "session": "rth",
            "source": "db_adj_rth", "date_from": "2016-07-01", "date_to": "2026-06-30", "n_trials": 300, "wf_folds": 8,
            "lockbox_months": 12, "cost_pts": 0.533, "params": {"a": 1, "b": 2.0}, "note": "x", "status": "done"}
NON_BOOK_FP_BEFORE = "50b89c7fb65b4a12"      # DG.job_fingerprint(NON_BOOK) on the module before "legs" was added


def _done(job, t=100.0):
    return dict(job, status="done", finishedAt=t)


def test_two_books_differing_only_in_legs_are_not_repeats():
    other = dict(BOOK, legs=[LEG_A, dict(LEG_B, params={"or_min": 15})])
    assert DG.job_fingerprint(BOOK) != DG.job_fingerprint(other)
    assert set(DG.explain_difference(BOOK, other)) == {"legs"}
    assert DG.scan_for_duplicate(other, [("j1", _done(BOOK))]) is None
    fewer = dict(BOOK, legs=[LEG_A])
    assert DG.scan_for_duplicate(fewer, [("j1", _done(BOOK))]) is None


def test_identical_books_are_repeats():
    same = dict(BOOK, legs=[dict(LEG_A), dict(LEG_B)], note="rerun to confirm")     # same legs, new note
    assert DG.job_fingerprint(same) == DG.job_fingerprint(BOOK)
    m = DG.scan_for_duplicate(same, [("j1", _done(BOOK)), ("j0", dict(BOOK, legs=[LEG_B], status="done"))])
    assert m is not None and m["job_id"] == "j1" and m["n_matches"] == 1
    # cosmetic representation never reads as a change: 20 vs 20.0, dict key order
    cos = dict(BOOK, legs=[{"weight": 1.0, "instrument": "NQ", "params": {"n": 20.0, "k": 1.5}, "strategy": "NOISE_1_0.py"},
                           LEG_B])
    assert DG.job_fingerprint(cos) == DG.job_fingerprint(BOOK)


def test_a_non_book_jobs_fingerprint_is_unchanged():
    assert "legs" not in NON_BOOK
    assert DG.job_fingerprint(NON_BOOK) == NON_BOOK_FP_BEFORE


def test_legs_and_book_legs_are_both_material():
    assert "legs" in DG.MATERIAL_FIELDS and "book_legs" in DG.MATERIAL_FIELDS
    assert "legs" not in DG.REPEAT_FIELDS
    assert DG.job_fingerprint(dict(BOOK, book_legs=["x"])) != DG.job_fingerprint(BOOK)

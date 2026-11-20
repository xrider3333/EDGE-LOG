"""tools/wf_oos_warm_audit.py - the read-only triage that decides whether the warm-start fix
to tools/backfill_wf_oos.py requires any stored validate.wf_oos block to be rebuilt.

Only `classify` is tested, because it is the whole judgement: the rest of the tool is a
Firestore stream and some printing. The buckets matter because exactly ONE of them (a block
written by the COLD backfill verifier for a run validated after warm starts landed) could hold
a wrong number; the audit run on 2026-11-20 found that bucket EMPTY across 495 run docs, which
is why nothing was re-backfilled.
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools import wf_oos_warm_audit as A                                    # noqa: E402
from tools import backfill_wf_oos as B                                      # noqa: E402

COLD_TS = "2026-09-08 19:01"        # ENGU-Q #335
WARM_TS = "2026-09-21 08:52"        # ENGU-Q #407, one day after 7a95b816


def _doc(ts, block=None, wf_ran=True):
    v = {"wf_ran": wf_ran, "wf_best_mode": "rolling"}
    if block is not None:
        v["wf_oos"] = block
    return {"timestamp": ts, "strategy": "ENGUQ_1M_ETH_R2_1_0.py", "validate": v}


def test_a_validate_written_block_is_never_at_risk():
    """The validate wrote it with the same warm scoring it used; cold replay never touched it."""
    for ts in (COLD_TS, WARM_TS):
        bucket, _wd, _why = A.classify(_doc(ts, {"v": 1, "src": "validate", "trades": 10}))
        assert bucket == "block from the validate"


def test_the_only_at_risk_bucket_is_a_backfilled_block_on_a_warm_era_run():
    assert A.classify(_doc(WARM_TS, {"v": 1, "src": "backfill"}))[0] == "backfilled, WARM era"
    assert A.classify(_doc(COLD_TS, {"v": 1, "src": "backfill"}))[0] == "backfilled, cold era"


def test_missing_blocks_are_split_by_era():
    assert A.classify(_doc(WARM_TS))[0] == "no block, warm era"
    assert A.classify(_doc(COLD_TS))[0] == "no block, cold era"


def test_a_run_without_walk_forward_is_out_of_scope():
    bucket, wd, why = A.classify(_doc(WARM_TS, wf_ran=False))
    assert bucket == "no walk-forward" and wd is None


def test_the_era_and_its_reason_come_from_the_tool_being_fixed():
    """classify must not re-derive the era - it has to agree with backfill_wf_oos by construction,
    or the audit could clear a run the fix would then replay differently."""
    for ts in (COLD_TS, WARM_TS):
        _b, wd, why = A.classify(_doc(ts, {"v": 1, "src": "backfill"}))
        assert (wd, why) == B.warm_days_for_doc({"timestamp": ts})

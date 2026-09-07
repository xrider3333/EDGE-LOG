"""
FirestoreQueue.sweep_orphans against a fake collection (2026-09-07).

WHY THESE EXIST. On the night of 2026-09-06 the machine slept with four validates
claimed. Every claiming process died. The morning found:

  * three docs on status='running' - swept correctly, but each still carrying the
    control='pause' a dead worker never acted on, so the next runner to claim one
    would have parked in the 1-second pause loop for ever; and
  * NOISE_1_3_WIDE on status='paused' at 85%, which the sweep could not even see,
    because it only ever queried status='running'.

The verdict table itself is pinned in test_runner_orphans.py. This file pins what the
sweep DOES with that verdict: which docs it looks at, and exactly which fields the
requeue writes.
"""
import datetime
import os
import sys

import pytest

# sweep_orphans builds a real Firestore FieldFilter and uses firestore.DELETE_FIELD, so
# these two are needed to call it at all. Neither is in requirements-dev.txt: CI covers
# the streamlit-free ENGINE layer, and pulling firebase-admin in for it would drag grpc
# and google-cloud-firestore into every run. This module therefore SKIPS on CI and runs
# for real on the machine that actually runs the queue, which is where it matters. The
# pure decision table (orphan_verdict) has no such dependency and is always exercised,
# in tests/test_runner_orphans.py.
pytest.importorskip("google.cloud.firestore_v1.base_query",
                    reason="google-cloud-firestore is not part of the CI dev deps")
pytest.importorskip("firebase_admin",
                    reason="firebase-admin is not part of the CI dev deps")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.runner import FirestoreQueue, _WORKER_ID


class _FakeRef:
    def __init__(self, doc):
        self.doc = doc

    def update(self, patch):
        self.doc.writes.append(dict(patch))
        self.doc.data.update({k: v for k, v in patch.items()
                              if not _is_delete(v)})
        for k, v in patch.items():
            if _is_delete(v):
                self.doc.data.pop(k, None)


def _is_delete(v):
    return "DELETE_FIELD" in repr(v) or v.__class__.__name__ == "Sentinel"


class _FakeSnap:
    def __init__(self, doc_id, data, update_age_min=1.0):
        self.id = doc_id
        self.data = dict(data)
        self.writes = []
        self.update_time = (datetime.datetime.now(datetime.timezone.utc)
                            - datetime.timedelta(minutes=update_age_min))
        self.reference = _FakeRef(self)

    def to_dict(self):
        return dict(self.data)


class _FakeQuery:
    def __init__(self, snaps):
        self._snaps = snaps

    def stream(self):
        return iter(self._snaps)


class _FakeCollection:
    """Answers only the two equality filters the sweep uses."""

    def __init__(self, snaps):
        self.snaps = snaps
        self.queried = []

    def where(self, filter=None):
        want = filter.value              # google FieldFilter exposes .value
        self.queried.append(want)
        return _FakeQuery([s for s in self.snaps if s.data.get("status") == want])


class _FakeDoc:
    def __init__(self, col):
        self._col = col

    def collection(self, _name):
        return self._col


class _FakeDb:
    def __init__(self, col):
        self._col = col

    def collection(self, _name):
        return self

    def document(self, _uid):
        return _FakeDoc(self._col)


def _queue(snaps):
    q = FirestoreQueue.__new__(FirestoreQueue)     # no credentials, no network
    q.col = "backtests"
    q.allow = {"uid1"}
    q.db = _FakeDb(_FakeCollection(snaps))
    return q, q.db._col


def _ago(minutes):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)


def test_sweep_reads_both_claimed_statuses():
    q, col = _queue([])
    q.sweep_orphans(log=lambda *a: None)
    assert col.queried == ["running", "paused"]


def test_paused_job_with_a_dead_runner_is_requeued():
    # NOISE_1_3_WIDE: paused at 85%, claimed by a pid that no longer exists, and
    # (claimed by pre-heartbeat code) carrying no heartbeat at all.
    snap = _FakeSnap("A_noise13_wide",
                     {"status": "paused", "progress": 85, "control": "run",
                      "strategy": "NOISE_1_3_WIDE.py", "claimedBy": "runner-999999-deadbe"})
    q, _ = _queue([snap])
    assert q.sweep_orphans(log=lambda *a: None) == 1
    assert snap.data["status"] == "queued"
    assert snap.data["progress"] == 0


def test_requeue_clears_the_stale_control_flag():
    snap = _FakeSnap("job_paused_ctl",
                     {"status": "running", "progress": 34, "control": "pause",
                      "strategy": "ENGUQ_1M_ETH_ERW_1_0.py",
                      "claimedBy": "runner-999999-deadbe",
                      "heartbeat_at": _ago(500)})
    q, _ = _queue([snap])
    q.sweep_orphans(log=lambda *a: None)
    assert "control" not in snap.data, "a stale pause would park the next claim for ever"
    assert "heartbeat_at" not in snap.data
    assert "stale control='pause' cleared" in snap.data["orphan_note"]


def test_a_live_paused_job_is_left_alone(monkeypatch):
    # A runner parked in its pause loop keeps its heartbeat thread running, so the
    # doc stays fresh and its pid is still an api.runner process. Pause must mean
    # "hold this job", never "hand it to somebody else".
    import api.runner as R
    monkeypatch.setattr(R, "_claimant_alive", lambda _cb: True)
    snap = _FakeSnap("job_live_pause",
                     {"status": "paused", "progress": 40, "control": "pause",
                      "strategy": "NOISE_1_1.py", "claimedBy": "runner-4242-abcdef",
                      "heartbeat_at": _ago(0.2)})
    q, _ = _queue([snap])
    assert q.sweep_orphans(log=lambda *a: None) == 0
    assert snap.data["status"] == "paused"
    assert snap.writes == []


def test_a_paused_job_whose_runner_was_killed_is_requeued_at_once(monkeypatch):
    # The overnight case: the doc looks fresh because the process died seconds after
    # its last write, but the pid is gone, so there is nothing to wait for.
    import api.runner as R
    monkeypatch.setattr(R, "_claimant_alive", lambda _cb: False)
    snap = _FakeSnap("job_killed_pause",
                     {"status": "paused", "progress": 85, "control": "run",
                      "strategy": "NOISE_1_3_WIDE.py", "claimedBy": "runner-4242-abcdef",
                      "heartbeat_at": _ago(0.2)})
    q, _ = _queue([snap])
    assert q.sweep_orphans(log=lambda *a: None) == 1
    assert snap.data["status"] == "queued"
    assert "control" not in snap.data


def test_my_own_claim_is_never_swept():
    snap = _FakeSnap("job_mine",
                     {"status": "running", "progress": 5, "claimedBy": _WORKER_ID,
                      "strategy": "ORB.py", "heartbeat_at": _ago(9999)})
    q, _ = _queue([snap])
    assert q.sweep_orphans(log=lambda *a: None) == 0
    assert snap.writes == []


def test_dry_run_counts_without_writing():
    snap = _FakeSnap("job_dry",
                     {"status": "running", "progress": 12, "control": "pause",
                      "strategy": "X.py", "claimedBy": "runner-999999-deadbe",
                      "heartbeat_at": _ago(500)})
    q, _ = _queue([snap])
    lines = []
    assert q.sweep_orphans(log=lines.append, dry_run=True) == 1
    assert snap.writes == []
    assert any("DEAD" in ln for ln in lines)

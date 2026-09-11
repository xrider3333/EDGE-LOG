"""RESEARCH BEACON - make a local sweep visible on the top bar and in BUILDER.

THE GAP THIS CLOSES. Auto-Validates and books run on the runner, so they write a job record
and show up everywhere. The research drivers in this folder do not - they run in a plain
Python process on this machine, and for however long they take (a 54-cell sweep is an hour)
the app shows an idle queue. The owner asked, 2026-09-11: "make sure those internal runs or
sweeps show up on the bar / builder as well."

HOW IT WORKS. A beacon writes an ordinary job record with status 'running' and keeps its
heartbeat fresh, so the queue dials and the BUILDER queue card pick it up with no changes on
their side. It is never `queued`, which matters: the runner claims by status=='queued' and
would otherwise try to execute a record that has no strategy to run.

    from research_beacon import beacon
    with beacon("ENGU-Q limit x cap grid", total=16) as b:
        for i, cell in enumerate(cells, 1):
            ...
            b.step(i)              # updates the percentage on the bar

On exit it marks the record done (or error, with the message) and the dial clears itself.
Killing the process leaves the heartbeat to go stale, which is exactly what the amber
STALLED dial is for - a beacon cannot lie about being alive any more than a real job can.

COST. One write on start, one per step (throttled to at most one every 3 seconds) and one on
exit. The Firestore budget is a READ budget - the listeners already open are what cost, and
this adds no listener.
"""
import atexit
import datetime as _dt
import os
import time
import traceback

_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
_CRED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"
_MIN_WRITE_S = 3.0


def _col():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(_CRED))
    return (firestore.client().collection("users").document(_UID)
            .collection("backtests"))


class Beacon(object):
    """Visible marker for a local research run. Never raises into the caller."""

    def __init__(self, label, total=0, note=""):
        self.label = str(label)
        self.total = int(total or 0)
        self.note = str(note or "")
        self.ref = None
        self._last = 0.0
        self._pct = 0

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        try:
            now = _dt.datetime.now(_dt.timezone.utc)
            doc = {
                "type": "research", "status": "running", "progress": 0,
                "strategy": self.label,
                "preset": "LOCAL RESEARCH (not a validate - no lockbox, no verdict)",
                "createdAt": now, "startedAt": now, "heartbeat_at": now,
                "heartbeat_pid": os.getpid(),
                "claimedBy": "research-%d" % os.getpid(),
                "note": (self.note or
                         "A research driver running on this machine, shown here so the queue "
                         "is not silently busy. It produces no run number and no verdict."),
            }
            self.ref = _col().add(doc)[1]
            atexit.register(self._safety_net)
        except Exception:                                          # noqa: BLE001
            self.ref = None                                        # never block research
        return self

    def step(self, done, total=None):
        if total:
            self.total = int(total)
        if self.total > 0:
            self._pct = max(0, min(100, int(round(100.0 * float(done) / self.total))))
        self._beat()

    def _beat(self, force=False):
        if self.ref is None:
            return
        t = time.time()
        if not force and (t - self._last) < _MIN_WRITE_S:
            return
        self._last = t
        try:
            self.ref.update({"progress": self._pct,
                             "heartbeat_at": _dt.datetime.now(_dt.timezone.utc)})
        except Exception:                                          # noqa: BLE001
            pass

    def finish(self, status="done", error=""):
        if self.ref is None:
            return
        try:
            patch = {"status": status, "progress": 100 if status == "done" else self._pct,
                     "finishedAt": _dt.datetime.now(_dt.timezone.utc)}
            if error:
                patch["error"] = str(error)[:400]
            self.ref.update(patch)
        except Exception:                                          # noqa: BLE001
            pass
        finally:
            self.ref = None

    def _safety_net(self):
        # a driver that exits without the context manager still clears its dial
        if self.ref is not None:
            self.finish("done")

    # -- context manager ---------------------------------------------------
    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.finish("done")
        else:
            self.finish("error", "".join(traceback.format_exception_only(exc_type, exc)))
        return False


def beacon(label, total=0, note=""):
    return Beacon(label, total=total, note=note)


if __name__ == "__main__":
    # smoke test: a dial appears, sweeps to 100% and clears.
    with beacon("BEACON SMOKE TEST", total=10) as b:
        for i in range(1, 11):
            time.sleep(1.0)
            b.step(i)
            print("  step %d/10" % i, flush=True)
    print("done - the dial should be gone")

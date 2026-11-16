"""
The orphan verdict behind api/runner.py's sweep (2026-09-07).

WHY: three runner restarts on the night of 2026-09-06 each killed the job in flight,
and the old boot-only "no write for 60 minutes" rule could not see a job killed seconds
before the boot (its doc was fresh). Two validates sat on status='running' for hours.
These pin the decision table so a later edit cannot quietly bring that back.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.runner import (orphan_verdict, _claimant_pid, ORPHAN_HB_STALE_MIN,
                        ORPHAN_LEGACY_STALE_MIN)


def test_fresh_heartbeat_is_alive_even_when_pid_unknown():
    dead, why = orphan_verdict(0.5, 0.5, None)
    assert dead is False and "fresh" in why


def test_stale_heartbeat_is_dead_even_if_the_process_is_alive():
    # the runner process survived but the job thread inside it stopped writing
    dead, why = orphan_verdict(ORPHAN_HB_STALE_MIN + 1, 0.1, True)
    assert dead is True and "heartbeat stopped" in why


def test_dead_claimant_kills_a_fresh_heartbeat_immediately():
    # a restart killed the runner seconds ago: the doc is fresh, the pid is gone
    dead, why = orphan_verdict(0.2, 0.2, False)
    assert dead is True and "gone" in why


def test_legacy_claim_dead_process_is_dead_now():
    dead, why = orphan_verdict(None, 0.5, False)
    assert dead is True and "no heartbeat" in why


def test_legacy_claim_live_process_is_alive():
    dead, why = orphan_verdict(None, 30.0, True)
    assert dead is False


def test_legacy_claim_unknown_process_falls_back_to_the_60_minute_rule():
    assert orphan_verdict(None, ORPHAN_LEGACY_STALE_MIN - 1, None)[0] is False
    dead, why = orphan_verdict(None, ORPHAN_LEGACY_STALE_MIN + 1, None)
    assert dead is True and "no write" in why


def test_nothing_known_is_not_dead():
    assert orphan_verdict(None, None, None) == (False, "cannot tell yet")


def test_claimant_pid_parses_the_runner_stamp_only():
    assert _claimant_pid("runner-35608-ab12cd") == 35608
    assert _claimant_pid("cmdthread") is None
    assert _claimant_pid(None) is None
    assert _claimant_pid("runner-notanumber-x") is None


# ── CROSS-MACHINE CLAIMS (2026-11-16, desktop workers 6-8) ─────────────────────────────────
# The Razer requeued GecC04RGdW twice while desktop worker 6 held it with a 0-minute-old
# heartbeat, because a desktop pid is not in the Razer's process table. A pid only means
# something on the box that issued it.
def test_foreign_host_claim_with_a_fresh_heartbeat_is_alive():
    from api.runner import _claimant_alive, _HOST
    assert _claimant_alive("runner-24540-abc", "some-other-box") is None, \
        "a foreign claim cannot be judged by pid here"
    assert orphan_verdict(0.0, 0.0, None) == (False, "heartbeat fresh")


def test_foreign_host_claim_with_a_stale_heartbeat_is_dead():
    from api.runner import _claimant_alive
    assert _claimant_alive("runner-24540-abc", "some-other-box") is None
    dead, why = orphan_verdict(ORPHAN_HB_STALE_MIN + 1, 0.1, None)
    assert dead and "heartbeat stopped" in why


def test_same_host_dead_pid_is_still_dead():
    from api.runner import _claimant_alive, _HOST
    assert _claimant_alive("runner-999999-abc", _HOST) is False
    assert orphan_verdict(0.2, 0.2, False)[0] is True


def test_claim_without_a_host_keeps_todays_behaviour():
    """A Razer-only fleet must be bit-for-bit unchanged: no claimHost = judge by pid."""
    from api.runner import _claimant_alive
    assert _claimant_alive("runner-999999-abc") is False
    assert _claimant_alive("runner-999999-abc", None) is False


def test_the_claim_stamps_the_host():
    import inspect, re
    from api import runner as R
    src = inspect.getsource(R)
    assert re.search(r'"claimedBy": _WORKER_ID,\s*\n\s*"claimHost": _HOST,', src), \
        "every claim must carry the host that made it"
    assert '_claimant_alive(j.get("claimedBy"), j.get("claimHost"))' in src, \
        "the sweep must pass the claim's host"

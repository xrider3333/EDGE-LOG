"""Unit tests for api.nt_exec_review -- the per-strategy fingerprint fix (dropping the
retired EdgeLogORBV2 entry, matching a fill by account AND instrument prefix instead of
account alone) and the Windows console-encoding fix for the fill-review log line.

Background (2026-09-23): the live bridge showed EdgeLogNOISE trading MNQ (qty 3) and
EdgeLogENGUQ1m trading NQ (qty 1), both on DEMO7240108 -- but _match_strategy matched
fills by account only, so every demo fill (regardless of instrument) matched whichever
EXPECTED entry the dict iteration reached first, and every real NOISE fill on MNQ was
marked REVIEW because it "looked like" a different strategy's fill. Separately,
runner.log showed `[exec-review] respond failed: UnicodeEncodeError: ... '\\u26a0'`: the
phone alert for a flagged fill had already gone out by the time a plain print() of that
same glyph crashed on this machine's cp1252 console, so the crash's own log line hid a
working notify behind what looked like a failure.

Never hits the live bridge or a real notification service: _get and _notify are always
stubbed, and the seen-exec_id state file is always redirected under tmp_path.
"""
import os
import sys

from api import nt_exec_review as E


def _fill(account, instrument, qty, *, exec_id="e1", time_utc="2026-09-23T14:30:00Z",
           side="Long", price=20000.0):
    return {"exec_id": exec_id, "account": account, "instrument": instrument, "qty": qty,
            "side": side, "price": price, "time_utc": time_utc}


# ── EXPECTED / _match_strategy / evaluate: account + instrument prefix ────────────────

def test_orbv2_is_no_longer_a_fingerprint():
    assert "EdgeLogORBV2" not in E.EXPECTED
    assert set(E.EXPECTED) == {"EdgeLogNOISE", "EdgeLogENGUQ1m"}


def test_mnq_qty3_on_demo_matches_noise_and_is_not_flagged():
    assert E.evaluate(_fill("DEMO7240108", "MNQ 12-26", 3)) == (False, None)


def test_nq_qty1_on_demo_matches_enguq_and_is_not_flagged():
    assert E.evaluate(_fill("DEMO7240108", "NQ 12-26", 1)) == (False, None)


def test_nq_qty2_on_demo_flagged_on_qty():
    flagged, reason = E.evaluate(_fill("DEMO7240108", "NQ 12-26", 2))
    assert flagged is True
    assert reason == "qty 2 exceeds EdgeLogENGUQ1m's configured max 1"


def test_mnq_qty4_on_demo_flagged_on_qty():
    flagged, reason = E.evaluate(_fill("DEMO7240108", "MNQ 12-26", 4))
    assert flagged is True
    assert reason == "qty 4 exceeds EdgeLogNOISE's configured max 3"


def test_es_on_demo_flagged_naming_instrument_and_account():
    flagged, reason = E.evaluate(_fill("DEMO7240108", "ES 12-26", 1))
    assert flagged is True
    assert "ES 12-26" in reason
    assert "DEMO7240108" in reason


def test_fill_on_live_account_flagged_with_todays_reason():
    flagged, reason = E.evaluate(_fill("1810769", "NQ 12-26", 1))
    assert flagged is True
    assert reason == "no known strategy trades account '1810769'"


def test_mnq_instrument_resolves_to_noise_not_enguq():
    """Regression for the account-only match: an MNQ fill must resolve to NOISE, never
    to ENGU-Q's "NQ" prefix. Plain str.startswith is naturally exact here -- "NQ" is a
    substring of "MNQ" but not a PREFIX of it, so a naive `in` check would have wrongly
    cross-matched where startswith does not."""
    name, exp = E._match_strategy({"account": "DEMO7240108", "instrument": "MNQ 12-26"})
    assert name == "EdgeLogNOISE"


def test_nq_instrument_resolves_to_enguq_not_noise():
    name, exp = E._match_strategy({"account": "DEMO7240108", "instrument": "NQ 12-26"})
    assert name == "EdgeLogENGUQ1m"


def test_mnq_does_not_startswith_nq():
    # pins the literal claim in the task/comment: keep it explicit, not just implied.
    assert not "MNQ 12-26".startswith("NQ")


def test_nq_does_not_startswith_mnq():
    assert not "NQ 12-26".startswith("MNQ")


# ── _safe_print: tolerate a console that can't encode the fill's warning glyph ────────

class _CP1252Stream:
    """Minimal stand-in for the real Windows console: raises UnicodeEncodeError on
    anything cp1252 can't represent, exactly like the runner's stdout does."""
    encoding = "cp1252"

    def __init__(self):
        self.chunks = []

    def write(self, s):
        s.encode("cp1252")  # raises UnicodeEncodeError on '⚠', like the real console
        self.chunks.append(s)

    def flush(self):
        pass


def test_safe_print_does_not_raise_on_cp1252_stream(monkeypatch):
    fake = _CP1252Stream()
    monkeypatch.setattr(sys, "stdout", fake)
    E._safe_print("[exec-review] REVIEW: ⚠ REVIEW fill: should not raise")
    written = "".join(fake.chunks)
    assert written  # something was written
    assert "⚠" not in written  # unencodable glyph replaced, not passed through raw


def test_safe_print_passes_plain_text_through(capsys):
    E._safe_print("[exec-review] fill: DEMO7240108 NQ 12-26 Long 1 @ 20000.0 (now)")
    assert "DEMO7240108 NQ 12-26" in capsys.readouterr().out


# ── publish(): a flagged fill under a cp1252 console must not hide behind ─────────────
# "respond failed" -- the notify already happened by the time the log line is printed.

def test_publish_flagged_fill_does_not_crash_or_log_respond_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "STATE_PATH", str(tmp_path / "seen_executions.json"))
    notified = []
    monkeypatch.setattr(E, "_notify", notified.append)

    fill = _fill("DEMO7240108", "ES 12-26", 1, exec_id="flagged-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    fake_stdout = _CP1252Stream()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    E.publish()

    out = "".join(fake_stdout.chunks)
    assert "respond failed" not in out
    assert "REVIEW" in out

    # the phone message itself must be untouched (still carries the real glyph) --
    # only the CONSOLE print is softened, per "do not change the phone message text".
    assert len(notified) == 1
    assert notified[0].startswith("⚠ REVIEW fill:")
    assert "ES 12-26" in notified[0]

    # the seen-state file landed under tmp_path, nowhere near the live runner state.
    assert os.path.exists(str(tmp_path / "seen_executions.json"))


def test_publish_ok_fill_is_notified_without_review_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "STATE_PATH", str(tmp_path / "seen_executions.json"))
    notified = []
    monkeypatch.setattr(E, "_notify", notified.append)

    fill = _fill("DEMO7240108", "MNQ 12-26", 3, exec_id="ok-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    E.publish()

    assert notified == ["fill: DEMO7240108 MNQ 12-26 Long 3 @ 20000.0 (2026-09-23T14:30:00Z)"]


def test_publish_does_not_renotify_a_seen_exec_id(tmp_path, monkeypatch):
    state_path = tmp_path / "seen_executions.json"
    monkeypatch.setattr(E, "STATE_PATH", str(state_path))
    notified = []
    monkeypatch.setattr(E, "_notify", notified.append)

    fill = _fill("DEMO7240108", "MNQ 12-26", 3, exec_id="dupe-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    E.publish()
    assert len(notified) == 1
    E.publish()  # same exec_id again -- state file now has it recorded
    assert len(notified) == 1

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

import pytest

from api import nt_exec_review as E
from api import ntfy_push as N


class _Pushes(list):
    """Stand-in for E._notify(message, title, priority): .append(message) like before, plus the title and
    priority of each push in .titles / .priorities."""
    def __init__(self):
        super().__init__()
        self.titles, self.priorities = [], []

    def __call__(self, message, title=None, priority=None):
        self.append(message)
        self.titles.append(title)
        self.priorities.append(priority)


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
    notified = _Pushes()
    monkeypatch.setattr(E, "_notify", notified)

    fill = _fill("DEMO7240108", "ES 12-26", 1, exec_id="flagged-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    fake_stdout = _CP1252Stream()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    E.publish()

    out = "".join(fake_stdout.chunks)
    assert "respond failed" not in out
    assert "REVIEW" in out

    # the phone text is the plain format now (2026-10-07): no warning glyph, no account number, a
    # unique-enough title, and the problem in words. The CONSOLE line keeps the old REVIEW format.
    assert len(notified) == 1
    assert notified[0].startswith("Trading: AFFECTED - a paper strategy traded something it should not.")
    assert "ES @ 20,000.00" in notified[0] and "DEMO7240108" not in notified[0] and "⚠" not in notified[0]
    assert notified.titles == ["Paper fill: unexpected"] and notified.priorities == ["default"]

    # the seen-state file landed under tmp_path, nowhere near the live runner state.
    assert os.path.exists(str(tmp_path / "seen_executions.json"))


def test_publish_ok_fill_is_notified_without_review_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "STATE_PATH", str(tmp_path / "seen_executions.json"))
    notified = _Pushes()
    monkeypatch.setattr(E, "_notify", notified)

    fill = _fill("DEMO7240108", "MNQ 12-26", 3, exec_id="ok-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    E.publish()

    assert notified == ["Trading: not affected.\nPrice 20,000.00 at 07:30.\nDo: nothing."]
    assert notified.titles == ["Paper fill: NOISE bought 3 MNQ"] and notified.priorities == ["low"]


def test_publish_does_not_renotify_a_seen_exec_id(tmp_path, monkeypatch):
    state_path = tmp_path / "seen_executions.json"
    monkeypatch.setattr(E, "STATE_PATH", str(state_path))
    notified = _Pushes()
    monkeypatch.setattr(E, "_notify", notified)

    fill = _fill("DEMO7240108", "MNQ 12-26", 3, exec_id="dupe-1")
    monkeypatch.setattr(
        E, "_get", lambda path: {"executions": [fill]} if path == "/executions" else None)

    E.publish()
    assert len(notified) == 1
    E.publish()  # same exec_id again -- state file now has it recorded
    assert len(notified) == 1


# ── the plain phone text (2026-10-07) ───────────────────────────────────────────────────────────

NOW_AFTER_FILL = 1791346290          # 2026-10-07 04:11:30 UTC, 6 seconds after the fill below


def _utc(text):
    import datetime as dt
    return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def _no_live_fills_csv(tmp_path, monkeypatch):
    """_signal_name() reads fills.csv beside the seen-state file; never the live C:\\EdgeLog one."""
    monkeypatch.setattr(E, "STATE_PATH", str(tmp_path / "seen_executions.json"))
    monkeypatch.delenv("EDGELOG_FILLS_CSV", raising=False)
    monkeypatch.setattr(N, "_now", lambda: _utc("2026-09-23 14:30:30"))   # the clock publish() sees


def test_paper_fill_text_names_the_strategy_and_uses_phoenix_time():
    # the owner's own example: fill DEMO7240108 NQ 12-26 Long 1 @ 31477.75 at 2026-10-07 04:11:24 (UTC)
    f = _fill("DEMO7240108", "NQ 12-26", 1, exec_id="p1", time_utc="2026-10-07 04:11:24", price=31477.75)
    n = E.build_note(f, now=_utc("2026-10-07 04:11:30"))
    assert n["title"] == "Paper fill: ENGU-Q bought 1 NQ"
    assert n["message"] == "Trading: not affected.\nPrice 31,477.75 at 21:11.\nDo: nothing."     # 04:11 UTC = 21:11 Phoenix
    assert n["priority"] == "low" and not N.lint(n)


def test_paper_stop_out_says_stop_hit(tmp_path, monkeypatch):
    fills = tmp_path / "fills.csv"
    fills.write_text("ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId,SignalName\n"
                     "e-stop,2026-10-07 13:40:26,DEMO7240108,MNQ 12-26,SELL,1,31172.25,0,1,NZstop\n")
    f = _fill("DEMO7240108", "MNQ 12-26", 1, exec_id="e-stop", time_utc="2026-10-07 13:40:26", side="Short", price=31172.25)
    n = E.build_note(f, now=_utc("2026-10-07 13:40:40"))
    assert n["title"] == "Paper fill: NOISE stop hit"
    assert n["message"].split("\n")[1] == "Sold 1 MNQ @ 31,172.25 at 06:40."
    assert n["priority"] == "low" and not N.lint(n)


def test_unknown_signal_name_is_a_plain_fill(tmp_path):
    f = _fill("DEMO7240108", "MNQ 12-26", 1, exec_id="nope", time_utc="2026-10-07 13:40:26", side="Short")
    assert E.build_note(f, now=_utc("2026-10-07 13:40:40"))["title"] == "Paper fill: NOISE sold 1 MNQ"


def test_real_account_fill_text():
    # the owner's own example: 1810769 MNQ 12-26 Short 1 @ 31172.25 at 2026-10-07 13:40:26 (UTC)
    f = _fill("1810769", "MNQ 12-26", 1, exec_id="r1", time_utc="2026-10-07 13:40:26", side="Short", price=31172.25)
    flagged, reason = E.evaluate(f)
    assert flagged
    n = E.build_note(f, reason, now=_utc("2026-10-07 13:40:40"))
    assert n["title"] == "Real account fill"
    assert n["message"].split("\n")[1] == "You sold 1 MNQ @ 31,172.25 at 06:40 (not an EdgeLog strategy)."
    assert n["message"].split("\n")[2] == "Do: nothing if this was you; if not, check your broker."
    assert n["priority"] == "low" and not N.lint(n)
    assert "1810769" not in n["title"] + n["message"] and "REVIEW" not in n["message"]


def test_paper_fill_over_its_size_limit_is_the_one_that_says_affected():
    f = _fill("DEMO7240108", "MNQ 12-26", 12, exec_id="big", time_utc="2026-10-06 22:10:00", price=31610.75)
    flagged, reason = E.evaluate(f)
    n = E.build_note(f, reason, now=_utc("2026-10-06 22:10:10"))
    assert n["title"] == "Paper fill: NOISE too big"
    assert n["message"].startswith("Trading: AFFECTED - NOISE traded more than its size limit of 3.")
    assert n["priority"] == "default" and not N.lint(n)


def test_old_fill_gets_a_day_word_not_a_utc_stamp():
    f = _fill("DEMO7240108", "NQ 12-26", 1, exec_id="old", time_utc="2026-10-06 04:11:24")
    n = E.build_note(f, now=_utc("2026-10-07 04:11:30"))
    assert n["message"].split("\n")[1] == "Price 20,000.00 at yesterday 21:11."


def test_every_fill_kind_passes_the_format_lint():
    for acct, inst, qty in (("DEMO7240108", "NQ 12-26", 1), ("DEMO7240108", "ES 12-26", 1), ("1810769", "NQ 12-26", 1),
                            ("Sim101", "NQ 12-26", 1), ("DEMO7240108", "NQ 12-26", 5)):
        f = _fill(acct, inst, qty, exec_id="k", time_utc="2026-10-07 13:40:26")
        flagged, reason = E.evaluate(f)
        n = E.build_note(f, reason if flagged else None, now=_utc("2026-10-07 13:41:00"))
        assert not N.lint(n), (acct, inst, qty, n, N.lint(n))
        assert len(n["title"]) < 40


def test_publish_pushes_real_account_fill_low_and_keeps_the_console_line(tmp_path, monkeypatch, capsys):
    notified = _Pushes()
    monkeypatch.setattr(E, "_notify", notified)
    monkeypatch.setattr(N, "_now", lambda: _utc("2026-10-07 13:41:00"))
    f = _fill("1810769", "MNQ 12-26", 1, exec_id="r2", time_utc="2026-10-07 13:40:26", side="Short", price=31172.25)
    monkeypatch.setattr(E, "_get", lambda path: {"executions": [f]} if path == "/executions" else None)
    E.publish()
    assert notified.titles == ["Real account fill"] and notified.priorities == ["low"]
    assert "REVIEW fill: 1810769" in capsys.readouterr().out          # the runner.log line is unchanged


def test_a_bug_in_the_plain_text_never_loses_the_alert(monkeypatch):
    notified = _Pushes()
    monkeypatch.setattr(E, "_notify", notified)
    monkeypatch.setattr(E, "build_note", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(E, "_get", lambda path: {"executions": [_fill("1810769", "MNQ 12-26", 1, exec_id="boom")]}
                        if path == "/executions" else None)
    E.publish()
    assert len(notified) == 1 and notified[0].startswith("⚠ REVIEW fill: 1810769")      # the old text, still sent
    assert notified.titles == [None] and notified.priorities == [None]

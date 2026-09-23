"""Unit tests for api.nt_preflight -- watchdog-roster parsing (fix for the ORB V2 drift)
and the bridge-comparison check() itself.

Background (2026-09-23): EdgeLogORBV2 was switched off 2026-08-17 and removed from the
NinjaTrader watchdog's roster (tools/nt_recover.ps1's $expected line) 2026-09-09/10, but
this module kept its own hardcoded copy of the old roster and reported
"STRATEGY MISSING: EdgeLogORBV2" every morning even though nothing was wrong. The fix
reads the expected roster from the watchdog script itself (_expected_roster /
_parse_expected_names) so the two lists cannot drift apart again. These tests pin the
parser against the shapes the real script actually uses (a trailing comment on the
assignment line, a stale commented-out assignment left in place, single- and
double-quoted names) and pin check()'s bridge-comparison behavior with a stubbed bridge.

Never touches the live nt_recover.ps1 or the live bridge: every test either passes an
explicit tmp_path script to _expected_roster()/check(), or monkeypatches _get.
"""
from api import nt_preflight as P


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ── _parse_expected_names ───────────────────────────────────────────────────────────

def test_plain_line_single_quoted():
    text = "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')\n"
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_trailing_comment_with_quotes_and_parens_is_not_scanned():
    # shaped like the real 2026-09-10 line: an inline comment mentions a removed
    # strategy BY NAME in quotes and later lines use parens -- neither may leak into
    # the parsed roster, because the assignment regex stops at the assignment's own
    # closing ')', before the comment text even starts.
    text = (
        "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')   "
        "# 2026-09-10: ORBPAR REMOVED - naming a PAR row (see notes) 'EdgeLogORBPAR' -\n"
        "#   it shares Sim101 + NQ 09-26 with EdgeLogORBPAR (see the memory note).\n"
    )
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_commented_out_assignment_is_ignored():
    text = (
        "# $expected = @('EdgeLogOldRoster')\n"
        "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')\n"
    )
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_indented_comment_is_still_recognised_as_a_comment():
    text = "   # $expected = @('EdgeLogOldRoster')\n$expected = @('EdgeLogNOISE')\n"
    assert P._parse_expected_names(text) == ["EdgeLogNOISE"]


def test_last_assignment_wins():
    text = (
        "$expected = @('EdgeLogFirst')\n"
        "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')\n"
    )
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_double_quoted_names():
    text = '$expected = @("EdgeLogNOISE", "EdgeLogENGUQ1m")\n'
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_mixed_quote_styles():
    text = "$expected = @(\"EdgeLogNOISE\", 'EdgeLogENGUQ1m')\n"
    assert P._parse_expected_names(text) == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_empty_parens_yields_no_names():
    assert P._parse_expected_names("$expected = @()\n") == []


def test_no_assignment_at_all_yields_no_names():
    assert P._parse_expected_names("# just a comment\nWrite-Host 'hi'\n") == []


# ── _expected_roster: file resolution + fallback ─────────────────────────────────────

def test_expected_roster_reads_watchdog_file(tmp_path):
    p = _write(tmp_path, "recover.ps1", "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')\n")
    names, source = P._expected_roster(p)
    assert names == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]
    assert source == "watchdog"


def test_missing_file_falls_back_to_builtin(tmp_path):
    names, source = P._expected_roster(str(tmp_path / "nope.ps1"))
    assert names == P.BUILTIN_ROSTER
    assert source == "built-in"


def test_empty_at_expansion_falls_back_to_builtin(tmp_path):
    p = _write(tmp_path, "recover.ps1", "$expected = @()\n")
    names, source = P._expected_roster(p)
    assert names == P.BUILTIN_ROSTER
    assert source == "built-in"


def test_undecodable_file_falls_back_to_builtin(tmp_path):
    p = tmp_path / "recover.ps1"
    p.write_bytes(b"$expected = @('Edge\xffLog')\n")  # 0xFF is never valid UTF-8
    names, source = P._expected_roster(str(p))
    assert names == P.BUILTIN_ROSTER
    assert source == "built-in"


def test_env_var_override(tmp_path, monkeypatch):
    p = _write(tmp_path, "recover.ps1", "$expected = @('EdgeLogFromEnv')\n")
    monkeypatch.setenv("EDGELOG_NT_RECOVER_PS1", p)
    names, source = P._expected_roster()
    assert names == ["EdgeLogFromEnv"]
    assert source == "watchdog"


def test_function_argument_beats_env_var(tmp_path, monkeypatch):
    env_p = _write(tmp_path, "env.ps1", "$expected = @('EdgeLogFromEnv')\n")
    arg_p = _write(tmp_path, "arg.ps1", "$expected = @('EdgeLogFromArg')\n")
    monkeypatch.setenv("EDGELOG_NT_RECOVER_PS1", env_p)
    names, source = P._expected_roster(arg_p)
    assert names == ["EdgeLogFromArg"]


# ── check(): bridge comparison, with a stubbed bridge ────────────────────────────────

def _stub_bridge(monkeypatch, *, strategies, demo_cash=100000.0, health_ok=True):
    responses = {
        "/health": ({"ok": True} if health_ok else None),
        "/strategies": {"strategies": strategies},
        "/accounts": {"accounts": [{"name": P.DEMO_ACCOUNT, "cash": demo_cash}]},
    }
    monkeypatch.setattr(P, "_get", lambda path: responses.get(path))


def _todays_roster_ps1(tmp_path):
    return _write(tmp_path, "recover.ps1", "$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m')\n")


def test_check_ok_with_todays_roster(tmp_path, monkeypatch):
    strategies = [
        {"name": "EdgeLogNOISE", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "MNQ 12-26"},
        {"name": "EdgeLogENGUQ1m", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "NQ 12-26"},
    ]
    _stub_bridge(monkeypatch, strategies=strategies)
    ps1 = _todays_roster_ps1(tmp_path)

    rep = P.check(nt_recover_path=ps1)

    assert rep["ok"] is True
    assert rep["problems"] == []
    assert rep["roster_source"] == "watchdog"
    assert rep["expected"] == ["EdgeLogNOISE", "EdgeLogENGUQ1m"]


def test_check_flags_missing_strategy(tmp_path, monkeypatch):
    strategies = [
        {"name": "EdgeLogNOISE", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "MNQ 12-26"},
    ]
    _stub_bridge(monkeypatch, strategies=strategies)
    ps1 = _todays_roster_ps1(tmp_path)

    rep = P.check(nt_recover_path=ps1)

    assert rep["ok"] is False
    assert "STRATEGY MISSING: EdgeLogENGUQ1m" in rep["problems"]


def test_check_flags_live_account_exposure_first(tmp_path, monkeypatch):
    strategies = [
        {"name": "EdgeLogNOISE", "account": P.LIVE_ACCOUNT, "state": "Realtime",
         "instrument": "MNQ 12-26"},
        {"name": "EdgeLogENGUQ1m", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "NQ 12-26"},
    ]
    _stub_bridge(monkeypatch, strategies=strategies)
    ps1 = _todays_roster_ps1(tmp_path)

    rep = P.check(nt_recover_path=ps1)

    assert rep["ok"] is False
    assert rep["problems"][0] == f"LIVE ACCOUNT EXPOSURE: EdgeLogNOISE on {P.LIVE_ACCOUNT}"


def test_check_builtin_fallback_still_reports_source(tmp_path, monkeypatch):
    """The watchdog file being unreadable must not itself become a preflight failure --
    the built-in roster is used and roster_source says so."""
    strategies = [
        {"name": "EdgeLogNOISE", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "MNQ 12-26"},
        {"name": "EdgeLogENGUQ1m", "account": P.DEMO_ACCOUNT, "state": "Realtime",
         "instrument": "NQ 12-26"},
    ]
    _stub_bridge(monkeypatch, strategies=strategies)

    rep = P.check(nt_recover_path=str(tmp_path / "nope.ps1"))

    assert rep["roster_source"] == "built-in"
    assert rep["expected"] == P.BUILTIN_ROSTER
    assert rep["ok"] is True

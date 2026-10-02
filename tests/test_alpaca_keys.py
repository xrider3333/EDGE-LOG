r"""The one Alpaca key lookup: augur_engine/alpaca_keys.py (2026-10-02).

WHY THE REGISTRY FALLBACK EXISTS. The owner saved the key as Windows USER environment
variables. A process only inherits those if it STARTED after they were set, so every runner
process and every session already running is blind to them, and restarting the fleet to pick
up a variable is a poor trade. Windows stores user variables in the registry at
HKCU\Environment, so reading that is the same fact from the same place without a restart.

TWO HANDLING RULES ARE THE POINT OF THIS FILE, not incidental to it:

  1. The value is returned to the caller and never printed, logged or written. `describe()`
     exists so a tool can say WHERE the key came from without saying what it is - not even a
     prefix, because an Alpaca key id alone identifies the account.

  2. No test may read the owner's real key. conftest's _isolate_alpaca_keys fixture empties
     every source (env, the JSON paths, and a stub winreg) for the whole suite, and the
     "nothing is configured" assertions here are written `not any(...)` rather than
     `== (None, None)`: if the isolation ever broke, pytest's assertion rewriting would print
     the resolved tuple - the real key - into the output, and into whatever CI log holds it.
     The weaker-looking assertion is the one that cannot leak.

Every fake registry here is installed over that stub via sys.modules, which works because the
module does `import winreg` INSIDE the lookup rather than at import time - on purpose, since
the module has to import cleanly on the Oracle box too.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import alpaca_keys as ak  # noqa: E402


# ── a fake registry ──────────────────────────────────────────────────────────────────────
class FakeWinreg:
    """Just enough winreg to stand in for the real one: a dict of value names, and the same
    failure shape (OSError) the real module raises for a missing key or value."""
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 0x20019
    REG_SZ = 1

    def __init__(self, values=None, path="Environment", open_error=None, query_error=None):
        self.values = dict(values or {})
        self.path = path
        self.open_error = open_error
        self.query_error = query_error
        self.opened = []            # (root, path, reserved, access) of every OpenKey
        self.queried = []           # every value name asked for
        self.closed = 0

    def OpenKey(self, root, path, reserved=0, access=0):
        self.opened.append((root, path, reserved, access))
        if self.open_error is not None:
            raise self.open_error
        if path != self.path:
            raise OSError(2, "no such registry key")
        return self

    def QueryValueEx(self, handle, name):
        self.queried.append(name)
        if self.query_error is not None:
            raise self.query_error
        if name not in self.values:
            raise OSError(2, "no such value")
        return self.values[name], self.REG_SZ

    # the module uses OpenKey as a context manager
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed += 1
        return False


@pytest.fixture
def reg(monkeypatch):
    """Install a fake winreg holding both values."""
    def _install(values=None, **kw):
        fake = FakeWinreg(values if values is not None else
                          {"ALPACA_API_KEY": "REG_KEY", "ALPACA_SECRET_KEY": "REG_SECRET"}, **kw)
        monkeypatch.setitem(sys.modules, "winreg", fake)
        return fake
    return _install


def _json_at(tmp_path, name, payload, bom=False):
    p = tmp_path / name
    body = json.dumps(payload).encode("utf-8")
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + body)
    return str(p)


@pytest.fixture
def sources(monkeypatch, tmp_path):
    """Point the JSON sources at real temp files, in the module's own order."""
    def _install(secrets=None, augur=None, tools=None, bom=False):
        paths = [str(tmp_path / "missing_secrets.json"),
                 str(tmp_path / "missing_augur.json"),
                 str(tmp_path / "missing_tools.json")]
        if secrets is not None:
            paths[0] = _json_at(tmp_path, "secrets.json", secrets, bom)
        if augur is not None:
            paths[1] = _json_at(tmp_path, "augur_config.json", augur, bom)
        if tools is not None:
            paths[2] = _json_at(tmp_path, "tools_keys.json", tools, bom)
        monkeypatch.setattr(ak, "JSON_SOURCES", (
            (paths[0], "key", "secret"),
            (paths[1], "alpaca_key", "alpaca_secret"),
            (paths[2], "key", "secret"),
        ))
        return paths
    return _install


# ══════════════════════════════════════════════════════════ 1. nothing configured
def test_nothing_configured_resolves_to_nothing():
    assert not any(ak.load_keys()), "with no source present the lookup must find nothing"
    assert ak.describe() == "not found"


def test_it_never_raises_when_every_source_is_absent():
    """A credential lookup that throws turns a recoverable "no key yet" into a crash in
    whatever called it - api/runner.py's SPY tick, for one."""
    for _ in range(3):
        assert not any(ak.load_keys())


# ══════════════════════════════════════════════════════════ 2. the environment
def test_the_process_environment_is_read_first(monkeypatch, reg, sources):
    reg({"ALPACA_API_KEY": "REG_KEY", "ALPACA_SECRET_KEY": "REG_SECRET"})
    sources(secrets={"key": "FILE_KEY", "secret": "FILE_SECRET"})
    monkeypatch.setenv("ALPACA_API_KEY", "ENV_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "ENV_SECRET")
    assert ak.load_keys() == ("ENV_KEY", "ENV_SECRET")
    assert ak.describe() == "the process environment"


def test_half_a_pair_in_the_environment_is_not_a_hit(monkeypatch, reg):
    """One variable set and the other missing is a half-finished setup, not a key. Falling
    through is right: pairing an env key with a file's secret would 401 in a way nobody
    could read off the error."""
    reg()
    monkeypatch.setenv("ALPACA_API_KEY", "ENV_KEY")
    assert ak.load_keys() == ("REG_KEY", "REG_SECRET")


# ══════════════════════════════════════════════════════════ 3. the registry fallback
def test_the_registry_is_read_when_the_environment_lacks_the_keys(reg):
    """THE WHOLE POINT: this session's own process started before the owner saved the
    variables, so os.environ cannot see them and the registry can."""
    fake = reg()
    assert ak.load_keys() == ("REG_KEY", "REG_SECRET")
    assert ak.describe() == "the Windows user environment in the registry"
    assert fake.opened, "it must actually have opened the key"


def test_it_reads_HKCU_Environment_read_only_and_only_those_two_values(reg):
    fake = reg()
    ak.load_keys()
    root, path, _reserved, access = fake.opened[0]
    assert root == FakeWinreg.HKEY_CURRENT_USER, "the user's own environment, not HKLM"
    assert path == "Environment"
    assert access == FakeWinreg.KEY_READ, "read-only: this lookup never writes the registry"
    assert set(fake.queried) == {"ALPACA_API_KEY", "ALPACA_SECRET_KEY"}, (
        "it must ask for the two named values and nothing else")
    assert fake.closed >= 1, "the handle must be closed (it is opened as a context manager)"


def test_the_registry_values_are_stripped(reg):
    """setx and a hand-edit through the System panel both leave trailing whitespace easily;
    a key with a stray space 401s."""
    reg({"ALPACA_API_KEY": "  REG_KEY \t", "ALPACA_SECRET_KEY": "REG_SECRET  "})
    assert ak.load_keys() == ("REG_KEY", "REG_SECRET")


def test_an_empty_registry_value_is_not_a_hit(reg, sources):
    reg({"ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": "REG_SECRET"})
    sources(secrets={"key": "FILE_KEY", "secret": "FILE_SECRET"})
    assert ak.load_keys() == ("FILE_KEY", "FILE_SECRET")


def test_only_one_value_present_in_the_registry_falls_through(reg, sources):
    reg({"ALPACA_API_KEY": "REG_KEY"})
    sources(secrets={"key": "FILE_KEY", "secret": "FILE_SECRET"})
    assert ak.load_keys() == ("FILE_KEY", "FILE_SECRET")


def test_a_registry_that_cannot_be_opened_is_simply_not_found(reg, sources):
    reg(open_error=PermissionError(5, "access denied"))
    sources(secrets={"key": "FILE_KEY", "secret": "FILE_SECRET"})
    assert ak.load_keys() == ("FILE_KEY", "FILE_SECRET")


def test_a_registry_that_raises_on_query_is_simply_not_found(reg):
    reg(query_error=OSError(13, "boom"))
    assert not any(ak.load_keys())


def test_no_winreg_at_all_is_simply_not_found(monkeypatch, sources):
    """The box is Linux. The module has to import and run there, which is why `import
    winreg` is inside the function and an ImportError means "not found", not a crash."""
    import builtins
    real_import = builtins.__import__

    def _no_winreg(name, *a, **k):
        if name == "winreg":
            raise ImportError("No module named 'winreg'")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "winreg", raising=False)
    monkeypatch.setattr(builtins, "__import__", _no_winreg)
    sources(secrets={"key": "FILE_KEY", "secret": "FILE_SECRET"})
    assert ak.load_keys() == ("FILE_KEY", "FILE_SECRET")


# ══════════════════════════════════════════════════════════ 4. the JSON files
def test_the_out_of_repo_secrets_file_comes_before_the_repo_ones(sources):
    sources(secrets={"key": "SECRETS_KEY", "secret": "SECRETS_SECRET"},
            augur={"alpaca_key": "AUGUR_KEY", "alpaca_secret": "AUGUR_SECRET"},
            tools={"key": "TOOLS_KEY", "secret": "TOOLS_SECRET"})
    assert ak.load_keys() == ("SECRETS_KEY", "SECRETS_SECRET")
    assert ak.describe() == "secrets.json"


def test_augur_config_comes_before_tools_alpaca_keys(sources):
    sources(augur={"alpaca_key": "AUGUR_KEY", "alpaca_secret": "AUGUR_SECRET"},
            tools={"key": "TOOLS_KEY", "secret": "TOOLS_SECRET"})
    assert ak.load_keys() == ("AUGUR_KEY", "AUGUR_SECRET")


def test_the_last_json_source_is_still_reached(sources):
    sources(tools={"key": "TOOLS_KEY", "secret": "TOOLS_SECRET"})
    assert ak.load_keys() == ("TOOLS_KEY", "TOOLS_SECRET")


def test_a_bom_prefixed_file_is_read(sources):
    """The owner's deploy_notes one-liner is PowerShell `Set-Content -Encoding utf8`, which
    on Windows PowerShell 5.1 writes a UTF-8 BOM. encoding="utf-8" raises "Unexpected UTF-8
    BOM", the bare except swallows it, and the tool then says "no key found" to someone who
    did exactly what they were told. utf-8-sig reads both."""
    sources(secrets={"key": "BOM_KEY", "secret": "BOM_SECRET"}, bom=True)
    assert ak.load_keys() == ("BOM_KEY", "BOM_SECRET")


def test_a_corrupt_file_does_not_stop_a_later_source(tmp_path, monkeypatch):
    bad = tmp_path / "secrets.json"
    bad.write_text("{not valid json")
    good = _json_at(tmp_path, "tools_keys.json", {"key": "TOOLS_KEY", "secret": "TOOLS_SECRET"})
    monkeypatch.setattr(ak, "JSON_SOURCES", (
        (str(bad), "key", "secret"),
        (str(tmp_path / "missing.json"), "alpaca_key", "alpaca_secret"),
        (good, "key", "secret"),
    ))
    assert ak.load_keys() == ("TOOLS_KEY", "TOOLS_SECRET")


def test_a_file_with_the_wrong_field_names_is_not_a_hit(sources):
    """augur_config.json uses alpaca_key/alpaca_secret and the other two use key/secret.
    A file holding the other pair of names must not half-resolve."""
    sources(secrets={"alpaca_key": "X", "alpaca_secret": "Y"})
    assert not any(ak.load_keys())


# ══════════════════════════════════════════════════════════ 5. the value never leaks
def test_describe_never_returns_the_key_or_any_prefix(monkeypatch, reg, sources):
    """An Alpaca key id identifies the account on its own, so even four characters of it is
    not something to put in a log line."""
    secret_value = "PKZZQQ11WWEE22RRTT33"
    for install in (lambda: monkeypatch.setenv("ALPACA_API_KEY", secret_value) or
                    monkeypatch.setenv("ALPACA_SECRET_KEY", secret_value),
                    lambda: reg({"ALPACA_API_KEY": secret_value,
                                 "ALPACA_SECRET_KEY": secret_value}),
                    lambda: sources(secrets={"key": secret_value, "secret": secret_value})):
        install()
        where = ak.describe()
        assert secret_value not in where
        for n in (4, 6, 8):
            assert secret_value[:n] not in where, (
                "describe() must not reveal even the first %d characters" % n)
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)


def test_the_module_never_prints_or_writes(reg):
    """A print() or a log line added here later is how a key ends up in a log file that gets
    pasted into a chat. Pinned as source text because that is the mistake's shape."""
    src = open(os.path.join(ROOT, "augur_engine", "alpaca_keys.py"), encoding="utf-8").read()
    code = chr(10).join(line for line in src.splitlines()
                        if not line.lstrip().startswith("#"))
    for banned in ("print(", "logging.", "sys.stdout", "sys.stderr", "write("):
        assert banned not in code, "%s has no business in a credential lookup" % banned
    assert code.count("open(") == 1, (
        "exactly one open(): the JSON reader. winreg.OpenKey is capital-O and read-only")
    assert "KEY_READ" in code and "KEY_WRITE" not in code and "SetValue" not in code, (
        "the registry is read, never written")


def test_no_key_is_hardcoded(reg):
    """A staged module is exactly where a 'temporary' pasted key survives."""
    src = open(os.path.join(ROOT, "augur_engine", "alpaca_keys.py"), encoding="utf-8").read()
    import re
    for m in re.findall(r"[A-Z0-9]{16,}", src):
        assert m in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"), (
            "a long literal that is not a variable name: %s" % m)


# ══════════════════════════════════════════════════════════ 6. everyone uses this one
def test_every_consumer_delegates_here():
    """Three tools had their own copy with three different orders. The whole point of this
    module is that there is one; a new local copy would undo it silently."""
    for rel in ("tools/import_alpaca_stocks.py", "tools/backfill_qqq_5m_alpaca.py",
                "api/spy_daily.py"):
        src = open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()
        assert "alpaca_keys" in src, "%s must use the shared lookup" % rel
        assert 'os.environ.get("ALPACA_API_KEY")' not in src, (
            "%s still resolves the key itself" % rel)


def test_the_env_var_names_are_the_agreed_ones():
    """PAPER-WB's QQQ backfill, api/spy_daily.py and the ROC-frontier pulls all read these
    names; the owner saved exactly these two. Renaming either breaks all of them at once."""
    assert ak.ENV_KEY == "ALPACA_API_KEY"
    assert ak.ENV_SECRET == "ALPACA_SECRET_KEY"


def test_the_help_text_names_both_working_routes():
    """Whatever a tool prints when there is no key has to be actionable: the environment
    variables (which now work without a restart) and the out-of-repo file."""
    assert "ALPACA_API_KEY" in ak.HELP and "ALPACA_SECRET_KEY" in ak.HELP
    assert "secrets" in ak.HELP
    assert "restart" in ak.HELP.lower(), (
        "the reason the registry read exists is the thing a reader needs to know")

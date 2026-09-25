"""tests/test_deploy_cloud_templates.py -- structural checks on the deploy/cloud/
systemd unit + logrotate templates and install.sh's own wiring of them (items C and E,
2026-09-25).

These are plain-text/shell/systemd-unit files, not Python, so nothing else in this
suite reads them. This is deliberately NOT a systemd/logrotate functional test --
neither is installed in the test environment, and unit-file semantics like whether
PathChanged= actually fires on a `mv`-created file, or whether logrotate's `maxsize`
interacts with `daily` the way the comment claims, can only be verified on the real
box (see this task's own delivered report). What IS checked here, portably: every
placeholder a template file uses has a matching `sed` substitution in install.sh (so a
new/renamed placeholder can never silently ship unsubstituted), the new items C/E
files exist with the settings the task specified, and install.sh actually installs +
enables them.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOUD_DIR = os.path.join(ROOT, "deploy", "cloud")

PLACEHOLDER_RE = re.compile(r"__EDGELOG_[A-Z_]+__")


def _read(name):
    with open(os.path.join(CLOUD_DIR, name), encoding="utf-8") as f:
        return f.read()


def _install_sh():
    return _read("install.sh")


def _sed_substituted_tokens(install_sh_text):
    """Every __EDGELOG_X__ token install.sh substitutes via `sed -e "s#TOKEN#...#g"`,
    anywhere in the file -- see this module's own docstring for why a whole-file check
    (not scoped to one sed block) is the right amount of precision here."""
    return set(re.findall(r's#(__EDGELOG_[A-Z_]+__)#', install_sh_text))


# ── item E: edgelog-keel-state.path ───────────────────────────────────────────────────────
def test_keel_state_path_unit_watches_the_nq_master_and_triggers_the_service():
    text = _read("edgelog-keel-state.path")
    assert "[Path]" in text
    assert "PathChanged=__EDGELOG_HOME__/nq/NOADJ_NQ_5m_RTH.csv" in text
    assert "Unit=edgelog-keel-state.service" in text
    assert "[Install]" in text
    assert re.search(r"^WantedBy=", text, re.MULTILINE)


def test_keel_state_path_unit_does_not_use_pathmodified():
    """PathModified= is the wrong directive for a scp-to-.tmp-then-mv push (the unit's
    own comment explains why, and mentions the directive name for that reason) -- a
    regression back to it as an ACTUAL (uncommented) directive would silently miss
    every push."""
    text = _read("edgelog-keel-state.path")
    active_lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    assert not any(ln.strip().startswith("PathModified=") for ln in active_lines)


def test_keel_state_path_is_installed_and_enabled_by_install_sh():
    sh = _install_sh()
    unit_loop = re.search(r"for unit in ([^\n]+); do", sh)
    assert unit_loop, "install.sh's systemd unit-templating loop must still exist"
    units = unit_loop.group(1).split()
    assert "edgelog-keel-state.path" in units
    assert "edgelog-keel-state.service" in units   # the .path unit is useless alone
    assert "edgelog-keel-state.timer" in units     # the fallback must stay installed too

    enable_lines = [ln for ln in sh.splitlines() if "systemctl enable" in ln]
    assert any("edgelog-keel-state.path" in ln for ln in enable_lines), (
        "edgelog-keel-state.path is installed but never enabled -- it would never "
        "start on boot")
    assert any("edgelog-keel-state.timer" in ln for ln in enable_lines)


# ── item C: edgelog.logrotate ─────────────────────────────────────────────────────────────
def test_logrotate_template_has_every_required_directive():
    text = _read("edgelog.logrotate")
    assert "__EDGELOG_HOME__/logs/*.log" in text
    for directive in ("daily", "rotate 14", "maxsize 100M", "compress", "delaycompress",
                     "missingok", "notifempty", "copytruncate"):
        assert re.search(rf"^\s*{re.escape(directive)}\s*$", text, re.MULTILINE), (
            f"missing logrotate directive: {directive!r}")
    assert re.search(r"^\s*su\s+\S+\s+\S+\s*$", text, re.MULTILINE), "missing an su user/group line"


def test_logrotate_template_is_installed_by_install_sh():
    sh = _install_sh()
    assert "edgelog.logrotate" in sh
    assert "/etc/logrotate.d/edgelog" in sh


# ── generic: every placeholder any template uses is actually substituted somewhere ───────
def test_every_placeholder_in_every_template_has_a_sed_substitution():
    sh = _install_sh()
    substituted = _sed_substituted_tokens(sh)
    assert substituted, "install.sh must substitute at least one __EDGELOG_*__ token"

    template_files = [f for f in os.listdir(CLOUD_DIR)
                      if f.endswith((".service", ".timer", ".path", ".logrotate"))]
    assert len(template_files) >= 8, "sanity: expected the usual set of unit templates to exist"

    missing = {}
    for fname in template_files:
        tokens = set(PLACEHOLDER_RE.findall(_read(fname)))
        gap = tokens - substituted
        if gap:
            missing[fname] = gap
    assert not missing, (
        f"template file(s) use a placeholder install.sh never substitutes: {missing}")


def test_new_item_c_and_e_files_are_utf8_text_with_no_crlf_surprises():
    """Not a hard requirement, just a guard against an accidental binary/BOM paste --
    every other file in this directory is plain LF/CRLF-agnostic ASCII-ish text."""
    for fname in ("edgelog.logrotate", "edgelog-keel-state.path"):
        raw = open(os.path.join(CLOUD_DIR, fname), "rb").read()
        assert b"\x00" not in raw
        raw.decode("utf-8")   # must not raise

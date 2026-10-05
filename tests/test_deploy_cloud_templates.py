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


# ── 2026-10-05: Webull freshness monitor units + the root-owned qqq_bars.log fix (#33) ───────
def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_freshness_service_runs_the_monitor_as_the_box_user_without_append_logs():
    text = _read("edgelog-freshness.service")
    lines = _active_lines(text)
    assert "Type=oneshot" in lines
    assert "User=__EDGELOG_USER__" in lines
    assert "EnvironmentFile=__EDGELOG_HOME__/edgelog.env" in lines
    assert any(ln.startswith("ExecStart=") and "tools/webull_freshness.py" in ln for ln in lines)
    # the tool logs itself: systemd must not open (and root-own) a log file for it
    assert not any(ln.startswith(("StandardOutput=append:", "StandardError=append:",
                                  "StandardOutput=file:", "StandardError=file:"))
                   for ln in lines)
    # it must never restart anything on its own say-so: no Exec line names systemctl
    assert not any("systemctl" in ln for ln in lines if ln.startswith("Exec"))


def test_freshness_timer_every_two_minutes_around_the_clock():
    lines = _active_lines(_read("edgelog-freshness.timer"))
    assert "OnCalendar=*-*-* *:00/2:00" in lines
    assert "Unit=edgelog-freshness.service" in lines
    assert "WantedBy=timers.target" in lines
    assert not any(ln.startswith("OnCalendar=") and "Mon..Fri" in ln for ln in lines)


def test_freshness_units_are_installed_and_the_timer_enabled_by_install_sh():
    sh = _install_sh()
    units = re.search(r"for unit in ([^\n]+); do", sh).group(1).split()
    assert "edgelog-freshness.service" in units and "edgelog-freshness.timer" in units
    enable_lines = [ln for ln in sh.splitlines()
                    if "systemctl enable" in ln and not ln.strip().startswith("#")]
    assert any("edgelog-freshness.timer" in ln for ln in enable_lines)


def test_qqq_bars_unit_never_lets_systemd_create_its_log_as_root():
    """finding #33: StandardOutput=append: made systemd create qqq_bars.log as root, and
    logrotate (su to the box user, copytruncate) then failed every night."""
    lines = _active_lines(_read("edgelog-qqq-bars.service"))
    assert not any(ln.startswith(("StandardOutput=append:", "StandardError=append:"))
                   for ln in lines)
    start = [ln for ln in lines if ln.startswith("ExecStart=")]
    assert len(start) == 1
    assert ">> __EDGELOG_HOME__/logs/qqq_bars.log 2>&1" in start[0]
    assert "tools/qqq_bars_publish.py --recent 2" in start[0]
    pre = [ln for ln in lines if ln.startswith("ExecStartPre=+")]
    assert pre and "chown -h __EDGELOG_USER__:__EDGELOG_USER__ __EDGELOG_HOME__/logs/qqq_bars.log" in pre[0]
    # runs as root in a user-writable dir: refuse a symlink before touch (which follows links)
    assert pre[0].index("test ! -L __EDGELOG_HOME__/logs/qqq_bars.log &&") < pre[0].index("touch ")
    # systemd expands $VAR / ${VAR} in Exec lines: the root command must not rely on any
    assert "$" not in pre[0]


def test_install_sh_precreates_and_chowns_every_appended_log():
    """Every log a unit appends to (StandardOutput=append:<home>/logs/X.log) must be created
    by install.sh as the run user, or systemd creates it root-owned and breaks logrotate."""
    sh = _install_sh()
    m = re.search(r"for log in ([^;\n]+); do", sh)
    assert m, "install.sh must pre-create the log files"
    precreated = set(m.group(1).split())
    appended = set()
    for fname in os.listdir(CLOUD_DIR):
        if fname.endswith(".service"):
            appended |= set(re.findall(r"append:__EDGELOG_HOME__/logs/([A-Za-z0-9_]+)\.log",
                                       _read(fname)))
    appended |= {"qqq_bars", "freshness"}
    assert appended <= precreated, f"logs not pre-created: {appended - precreated}"
    assert re.search(r'sudo chown -h "\$\{RUN_USER\}:\$\{RUN_USER\}" "\$\{EDGELOG_HOME\}"/logs/\*\.log', sh)


def test_logrotate_still_rotates_as_the_box_user_with_copytruncate():
    text = _read("edgelog.logrotate")
    assert re.search(r"^\s*su __EDGELOG_USER__ __EDGELOG_USER__\s*$", text, re.MULTILINE)
    assert re.search(r"^\s*copytruncate\s*$", text, re.MULTILINE)

"""tests/test_box_config_snapshot.py -- tools/box_config_snapshot.py's pure
snapshot-writing/diffing logic (take_snapshot), exercised entirely against pytest's
`tmp_path` temp directories with fake file bytes. No test here touches ssh, scp, or
C:\\EdgeLog -- take_snapshot never knows or cares where its bytes came from.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import box_config_snapshot  # noqa: E402


def test_first_snapshot_writes_every_present_file_and_has_no_diff(tmp_path):
    files = {
        "qqq_exec/config.json": b'{"a": 1}',
        "webull_orders/config.json": b'{"b": 2}',
        "cloud_signal/config.json": None,  # not present on the box
    }
    snap_dir, written, diff_text = box_config_snapshot.take_snapshot(
        files, dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 12, 0, 0))
    assert written == ["qqq_exec/config.json", "webull_orders/config.json"]
    assert diff_text == ""
    assert os.path.isfile(os.path.join(snap_dir, "qqq_exec", "config.json"))
    assert not os.path.exists(os.path.join(snap_dir, "cloud_signal", "config.json"))
    with open(os.path.join(snap_dir, "qqq_exec", "config.json"), "rb") as f:
        assert f.read() == b'{"a": 1}'


def test_second_snapshot_diffs_against_the_first(tmp_path):
    box_config_snapshot.take_snapshot(
        {"qqq_exec/config.json": b'{"caps": {"NOISE_382": 60}}\n'},
        dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 9, 0, 0))
    _, written, diff_text = box_config_snapshot.take_snapshot(
        {"qqq_exec/config.json": b'{"caps": {"NOISE_382": 80}}\n'},
        dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 10, 0, 0))
    assert written == ["qqq_exec/config.json"]
    assert "qqq_exec/config.json" in diff_text
    assert "-{" in diff_text or "-{\"caps\"" in diff_text
    assert "80" in diff_text


def test_identical_second_snapshot_has_empty_diff(tmp_path):
    content = b'{"same": true}\n'
    box_config_snapshot.take_snapshot(
        {"a.json": content}, dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 9, 0, 0))
    _, _, diff_text = box_config_snapshot.take_snapshot(
        {"a.json": content}, dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 10, 0, 0))
    assert diff_text == ""


def test_new_file_appearing_is_flagged_as_new(tmp_path):
    box_config_snapshot.take_snapshot(
        {"a.json": b"{}"}, dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 9, 0, 0))
    _, _, diff_text = box_config_snapshot.take_snapshot(
        {"a.json": b"{}", "b.json": b"{}"}, dest_root=str(tmp_path),
        now=dt.datetime(2026, 9, 26, 10, 0, 0))
    assert "b.json" in diff_text
    assert "new file this snapshot" in diff_text


def test_file_disappearing_is_flagged_as_missing(tmp_path):
    box_config_snapshot.take_snapshot(
        {"a.json": b"{}", "b.json": b"{}"}, dest_root=str(tmp_path),
        now=dt.datetime(2026, 9, 26, 9, 0, 0))
    _, _, diff_text = box_config_snapshot.take_snapshot(
        {"a.json": b"{}", "b.json": None}, dest_root=str(tmp_path),
        now=dt.datetime(2026, 9, 26, 10, 0, 0))
    assert "b.json" in diff_text
    assert "missing from this one" in diff_text


def test_snapshot_dir_is_a_timestamp_under_dest_root(tmp_path):
    snap_dir, _, _ = box_config_snapshot.take_snapshot(
        {"a.json": b"{}"}, dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 12, 34, 56))
    assert os.path.basename(snap_dir) == "20260926_123456"
    assert os.path.dirname(snap_dir) == str(tmp_path)


def test_default_dest_root_is_under_edgelog_home_box_config_history(monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", r"C:\FakeHome")
    assert box_config_snapshot._default_dest_root() == os.path.join(
        r"C:\FakeHome", "box_config_history")


def test_systemd_unit_filter_keeps_only_known_suffixes():
    names = ["edgelog-qqq-exec.service", "edgelog-cloud-signal.service",
            "edgelog-keel-state.path", "edgelog-keel-state.timer", "README.needrestart"]
    kept = [n for n in names if n.endswith(box_config_snapshot.SYSTEMD_SUFFIXES)]
    assert kept == ["edgelog-qqq-exec.service", "edgelog-cloud-signal.service",
                    "edgelog-keel-state.path", "edgelog-keel-state.timer"]


# ── systemd drop-in overrides (RestartSec etc. live outside the .service file) ─────────
def test_dropin_rel_path_keeps_the_unit_d_structure():
    got = box_config_snapshot._dropin_rel_path(
        "/etc/systemd/system/edgelog-qqq-exec.service.d/standby.conf")
    assert got == "etc/systemd/system/edgelog-qqq-exec.service.d/standby.conf"


def test_dropin_rel_path_returns_none_outside_etc_systemd_system():
    assert box_config_snapshot._dropin_rel_path("/etc/other/place.conf") is None


# ── masking sensitive-looking values in printed diffs ──────────────────────────────────
def test_mask_sensitive_redacts_account_like_keys():
    line = '-  "account": "1234567890",'
    assert box_config_snapshot._mask_sensitive(line) == '-  "account": "12**",'


def test_mask_sensitive_leaves_ordinary_keys_alone():
    line = '+  "cap": "80",'
    assert box_config_snapshot._mask_sensitive(line) == line


def test_mask_sensitive_matches_key_secret_token_id_case_insensitively():
    for line, expect_masked in [
        ('"API_KEY": "sk-abcdef123456",', "sk**"),
        ('"client_secret": "verysecretvalue",', "ve**"),
        ('"access_token": "tok_abcdefgh",', "to**"),
        ('"account_id": "998877",', "99**"),
    ]:
        masked = box_config_snapshot._mask_sensitive(line)
        assert expect_masked in masked
        # the original value never survives into the masked line
        raw_value = line.split(":", 1)[1].strip().strip('",')
        assert raw_value not in masked


def test_diff_masks_sensitive_values_end_to_end(tmp_path):
    box_config_snapshot.take_snapshot(
        {"webull_orders/config.json": b'{\n  "account": "1234567890",\n  "cap": 60\n}\n'},
        dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 9, 0, 0))
    _, _, diff_text = box_config_snapshot.take_snapshot(
        {"webull_orders/config.json": b'{\n  "account": "9999999999",\n  "cap": 80\n}\n'},
        dest_root=str(tmp_path), now=dt.datetime(2026, 9, 26, 10, 0, 0))
    assert "1234567890" not in diff_text
    assert "9999999999" not in diff_text
    assert "80" in diff_text  # a non-sensitive key's value is still visible

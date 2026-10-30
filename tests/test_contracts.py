import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import contracts as C  # noqa: E402


def test_inbox_item_ok_and_bad():
    C.validate_inbox_item({"id": 3, "at": "2026-10-30 13:43", "from": "MANAGER", "text": "hi", "status": "open"})
    for bad in ({"id": 0, "at": "2026-10-30 13:43", "from": "M", "text": "x", "status": "open"},
                {"id": 1, "at": "10-30", "from": "M", "text": "x", "status": "open"},
                {"id": 1, "at": "2026-10-30 13:43", "from": "M", "text": "x", "status": "closed"}):
        with pytest.raises(ValueError):
            C.validate_inbox_item(bad)


def test_run_record_stage_and_extra_keys():
    r = C.validate_run_record({"ts": "2026-10-30T10:00:00", "lane": "FRONTIER", "stage": "WF", "roc30k": 80.43})
    assert r.placeable()
    with pytest.raises(ValueError):
        C.validate_run_record({"ts": "t", "lane": "X", "stage": "FULL"})
    with pytest.raises(ValueError):
        C.validate_run_record({"ts": "t", "lane": "X", "stage": "WF", "dedup": 1})
    assert not C.validate_run_record({"ts": "t", "lane": "X", "stage": "LB"}).placeable()


def test_task_both_formats():
    a = C.validate_task_text("STATUS: ⭕ open\n# Task: read a log\nbody")
    b = C.validate_task_text("# Q7 - Log sweep\nStatus: 🟢 done - waiting\nbody")
    assert (a.status_icon, a.title) == ("⭕", "read a log") and b.status_icon == "🟢"
    with pytest.raises(ValueError):
        C.validate_task_text("no status\n# Task: x")


def test_check_counts_bad_lines(tmp_path):
    inbox = tmp_path / "in"; inbox.mkdir()
    (inbox / "A.jsonl").write_text(json.dumps({"id": 1, "at": "2026-10-30 13:43", "from": "M", "text": "x", "status": "open"}) + "\n"
                                   + json.dumps({"id": 2}) + "\n", encoding="utf-8")
    n, bad = C.check("inbox", inbox_dir=str(inbox))
    assert n == 1 and len(bad) == 1 and ":2:" in bad[0]

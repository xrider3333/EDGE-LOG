"""tools/qwen_task.py (MANAGER #222): the one door - add/list/show, Q<next> under a lock, STATUS.md row kept UTF-8."""
import datetime
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_task as T  # noqa: E402

TODAY = datetime.date.today().isoformat()
STATUS = ("# Qwen task board  (⭕ open · 🟡 Qwen working)\r\n| # | Task | Status | Note |\r\n|---|------|--------|------|\r\n"
          "| Q1 | one | ✅ | x |\r\n| Q12 | twelve | ⭕ | small, read-only |\r\n")


def _w(p, s):
    with open(p, "wb") as f:
        f.write(s.encode("utf-8"))


def _r(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8")


@pytest.fixture
def tdir(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_TASKS_DIR", str(tmp_path))
    _w(str(tmp_path / "STATUS.md"), STATUS)
    _w(str(tmp_path / "Q1-one.md"), "STATUS: ✅ closed\n# Q1 - one\n")
    _w(str(tmp_path / "Q12-twelve.md"), "# Q12 - twelve\nStatus: ⭕ open\n")
    return tmp_path


def test_add_writes_file_and_row(tdir):
    n = T.add_task("Check the | logs", "line one\nline two", "MANAGER")
    assert n == 13
    p = T.find(13)
    assert os.path.basename(p) == "Q13-check-the-logs.md"
    lines = _r(p).split("\n")
    assert lines[0] == "STATUS: ⭕ open"
    assert lines[1] == "# Q13 - Check the / logs"
    assert lines[2] == "From: MANAGER · Date: %s" % TODAY
    assert lines[3] == "" and lines[4] == "line one" and lines[5] == "line two"
    st = _r(str(tdir / "STATUS.md"))
    assert st == STATUS + "| Q13 | Check the / logs | ⭕ | %s filed by MANAGER |\r\n" % TODAY


def test_new_file_copies_newest_eol(tdir):
    _w(str(tdir / "Q12-twelve.md"), "# Q12\r\nStatus: x\r\n")
    os.utime(str(tdir / "Q12-twelve.md"), None)
    os.utime(str(tdir / "Q1-one.md"), (1, 1))
    p = T.find(T.add_task("t", "a\nb"))
    raw = _r(p)
    assert raw.count("\r\n") == raw.count("\n") > 0


def test_number_counts_status_rows_too(tdir):
    _w(str(tdir / "STATUS.md"), STATUS + "| Q20 | hand filed | ⭕ | x |\r\n")
    assert T.add_task("t", "b") == 21


def test_status_missing_newline_and_bom(tdir):
    with open(str(tdir / "STATUS.md"), "wb") as f:
        f.write(b"\xef\xbb\xbf| Q1 | one | \xe2\x9c\x85 | x |")
    T.add_task("t", "b", "ENGUQ")
    raw = open(str(tdir / "STATUS.md"), "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8").endswith("| Q1 | one | ✅ | x |\r\n| Q13 | t | ⭕ | %s filed by ENGUQ |\r\n" % TODAY)


def test_parallel_adds_get_distinct_numbers(tdir):
    got, errs = [], []

    def go(i):
        try:
            got.append(T.add_task("task %d" % i, "body"))
        except Exception as e:                       # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    assert not errs and sorted(got) == list(range(13, 21))
    st = _r(str(tdir / "STATUS.md"))
    assert all(st.count("| Q%d |" % n) == 1 for n in got)
    assert not os.path.exists(str(tdir / T.LOCK_NAME))


def test_stale_lock_is_broken(tdir):
    lp = str(tdir / T.LOCK_NAME)
    _w(lp, "1 0")
    os.utime(lp, (1, 1))
    assert T.add_task("t", "b") == 13


def test_held_lock_times_out(tdir):
    _w(str(tdir / T.LOCK_NAME), "1 0")
    with pytest.raises(TimeoutError):
        with T.Lock(str(tdir), wait_s=0.2):
            pass


def test_list_and_show_cli(tdir, capsys):
    T.add_task("hello", "world")
    assert T.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Q13" in out and "STATUS: ⭕ open" in out and "Q1 " in out
    assert T.main(["show", "13"]) == 0 and "world" in capsys.readouterr().out
    assert T.main(["show", "99"]) == 1


def test_cli_add(tdir, capsys):
    assert T.main(["add", "cli task", "do it", "--from", "PAPER-NT8"]) == 0
    assert "Q13 filed" in capsys.readouterr().out
    assert "From: PAPER-NT8" in _r(T.find(13))


def test_chat_tools_queue_instead_of_calling(tdir):
    import qwen_cascade
    import qwen_vote
    r = qwen_cascade.cascade("give json", qwen_cascade.json_check(["a"]))
    assert r["queued"] == 13 and r["escalate"] is False and "PROMPT:\ngive json" in _r(T.find(13))
    v = qwen_vote.vote("is it bad?", "token = sk-abcdef1234567890abcdef\nok\n", 3)
    assert v["queued"] == 14 and v["label"] is None
    assert "sk-abcdef1234567890abcdef" not in _r(T.find(14))           # redacted before it is filed

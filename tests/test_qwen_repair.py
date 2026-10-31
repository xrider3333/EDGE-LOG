"""tools/qwen_repair.py (C2): pytest fail -> Q task -> diff -> scratch re-test, N tries then Claude."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_repair as R  # noqa: E402

GOOD = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
WRONG = GOOD.replace("a + b", "a * b")
BAD_PATH = "--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n"


def _git(cwd, *a):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(a), cwd=cwd, check=True,
                   capture_output=True)


def _write(p, s):
    with open(p, "w", newline="\n") as f:
        f.write(s)


def _worktrees(repo):
    out = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True).stdout
    return len(out.strip().splitlines())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_REPAIR_DIR", str(tmp_path / "state"))
    r = tmp_path / "repo"
    r.mkdir()
    _write(r / "calc.py", "def add(a, b):\n    return a - b\n")
    _write(r / "test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    _git(r, "init", "-q")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "init")
    return r


class Fake:
    def __init__(self):
        self.tasks, self.posts, self.results = [], [], {}

    def add(self, title, body, frm="MANAGER"):
        self.tasks.append((title, body, frm))
        return 100 + len(self.tasks)

    def post(self, chat, text, frm):
        self.posts.append((chat, text, frm))

    def result(self, n):
        return self.results.get(n)

    def check(self, rid):
        return R.cmd_check(rid, add_task=self.add, post=self.post, result_of=self.result)


def test_pass_files_nothing(repo):
    _write(repo / "calc.py", "def add(a, b):\n    return a + b\n")
    f = Fake()
    assert R.cmd_file(str(repo), ["test_calc.py"], add_task=f.add) is None
    assert f.tasks == []
    assert not os.path.exists(R.state_dir())


def test_file_writes_task_and_state(repo):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], tries=2, frm="TBIS", add_task=f.add)
    assert rid == "r101"
    title, body, frm = f.tasks[0]
    assert frm == "TBIS" and str(repo) in body and "test_calc.py" in body
    assert "```diff" in body and "assert" in body and "never touch tests" in body
    st = R.load_state(rid)
    assert st["try"] == 1 and st["tries"] == 2 and st["q"] == [101]


def test_check_pass_writes_patch_lane_untouched(repo):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], add_task=f.add)
    f.results[101] = "Fix:\n```diff\n" + GOOD + "```\n"
    assert f.check(rid) == 0
    with open(os.path.join(R.state_dir(), rid + ".patch")) as fh:
        assert "a + b" in fh.read()
    assert "a - b" in (repo / "calc.py").read_text()
    assert _worktrees(repo) == 1
    assert len(f.tasks) == 1 and f.posts == []


def test_not_ready(repo):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], add_task=f.add)
    assert f.check(rid) == 2


def test_check_fail_refiles_with_prev_diff(repo):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], tries=3, add_task=f.add)
    f.results[101] = "```diff\n" + WRONG + "```"
    assert f.check(rid) == 1
    assert len(f.tasks) == 2 and "a * b" in f.tasks[1][1] and "did NOT fix" in f.tasks[1][1]
    assert R.load_state(rid)["try"] == 2 and f.posts == []
    assert _worktrees(repo) == 1


def test_n_tries_hands_off(repo):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], tries=2, frm="TBIS", add_task=f.add)
    f.results[101] = f.results[102] = "```diff\n" + WRONG + "```"
    assert f.check(rid) == 1
    assert f.check(rid) == 1
    assert len(f.tasks) == 2
    assert f.posts == [("TBIS", "C2: Qwen could not fix test_calc.py in 2 tries - over to Claude", "QWEN")]
    assert R.load_state(rid)["done"] == "handed_off"


@pytest.mark.parametrize("res", ["no fence here", "```diff\n" + BAD_PATH + "```"])
def test_bad_diff_handled(repo, res):
    f = Fake()
    rid = R.cmd_file(str(repo), ["test_calc.py"], tries=2, add_task=f.add)
    f.results[101] = res
    assert f.check(rid) == 1
    assert "C2:" in f.tasks[1][1]
    assert _worktrees(repo) == 1

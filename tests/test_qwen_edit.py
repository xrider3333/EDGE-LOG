"""tools/qwen_edit.py (C4): Claude plan -> one Q task per file -> Qwen diff -> scratch re-test -> combined patch."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_edit as E  # noqa: E402

CALC = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
UTIL = """--- a/util.py
+++ b/util.py
@@ -1,2 +1,2 @@
 def double(x):
-    return x
+    return add(x, x)
"""
UTIL_IMPORT = """--- a/util.py
+++ b/util.py
@@ -1,2 +1,4 @@
+from calc import add
+
 def double(x):
-    return x
+    return add(x, x)
"""
WRONG = CALC.replace("a + b", "a * b")
PLAN = """# plan
Goal: make add and double right

## FILE calc.py
Change add to return a + b.
Tests: test_calc.py

## FILE util.py
double(x) returns add(x, x); import add from calc.
Tests: test_util.py
"""


def _git(cwd, *a):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(a), cwd=cwd, check=True,
                   capture_output=True)


def _write(p, s):
    with open(p, "w", newline="\n") as f:
        f.write(s)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_EDIT_DIR", str(tmp_path / "state"))
    r = tmp_path / "repo"
    r.mkdir()
    _write(r / "calc.py", "def add(a, b):\n    return a - b\n")
    _write(r / "util.py", "def double(x):\n    return x\n")
    _write(r / "test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    _write(r / "test_util.py", "from util import double\n\n\ndef test_double():\n    assert double(4) == 8\n")
    _git(r, "init", "-q")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "init")
    _write(tmp_path / "plan.md", PLAN)
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

    def answer(self, diff):
        self.results[100 + len(self.tasks)] = "```diff\n" + diff + "```\n"


def _start(repo, fk):
    return E.cmd_plan(str(repo), str(repo.parent / "plan.md"), frm="LANE", add_task=fk.add)


def _check(eid, fk):
    return E.cmd_check(eid, add_task=fk.add, post=fk.post, result_of=fk.result)


def test_plan_validation(repo):
    wt = str(repo)
    p = E.parse_plan(PLAN, wt)
    assert p["goal"] == "make add and double right"
    assert [f["path"] for f in p["files"]] == ["calc.py", "util.py"]
    assert p["files"][1]["tests"] == ["test_util.py"]
    bad = {
        "escapes": "Goal\n## FILE ../x.py\nchange\nTests: t.py\n",
        "absolute": "Goal\n## FILE C:/x.py\nchange\nTests: t.py\n",
        "no tests": "Goal\n## FILE a.py\nchange\n",
        "no goal": "## FILE a.py\nchange\nTests: t.py\n",
        "no files": "Goal only\n",
        "twice": "Goal\n## FILE a.py\nc\nTests: t\n## FILE a.py\nc\nTests: t\n",
        "too many": "Goal\n" + "".join("## FILE f%d.py\nc\nTests: t\n" % i for i in range(9)),
    }
    for why, text in bad.items():
        with pytest.raises(E.PlanError):
            E.parse_plan(text, wt)
    assert len(E.parse_plan("Goal\n" + "".join("## FILE f%d.py\nc\nTests: t\n" % i for i in range(8)),
                            wt)["files"]) == 8


def test_first_task_filed_for_first_file_only(repo):
    fk = Fake()
    eid = _start(repo, fk)
    assert eid == "e101" and len(fk.tasks) == 1
    title, body, frm = fk.tasks[0]
    assert "calc.py" in title and frm == "LANE"
    assert "THIS FILE: calc.py" in body and "return a - b" in body
    assert "unified diff for THIS file only under a ```diff fence" in body
    assert "Acceptance tests: test_calc.py" in body and "## FILE util.py" in body
    assert os.path.exists(os.path.join(E.state_dir(), "e101.json"))


def test_diff_touching_other_file_refused(repo):
    fk = Fake()
    eid = _start(repo, fk)
    fk.answer(CALC + UTIL)
    assert _check(eid, fk) == 1
    assert "REFUSED" in fk.tasks[-1][1] and "util.py" in fk.tasks[-1][1]
    assert E.load_state(eid)["accepted"] == []


def test_pass_then_next_file_with_accepted_context(repo):
    fk = Fake()
    eid = _start(repo, fk)
    assert _check(eid, fk) == 2  # no RESULT yet
    fk.answer(CALC)
    assert _check(eid, fk) == 0
    st = E.load_state(eid)
    assert st["idx"] == 1 and st["accepted"] == [CALC]
    body = fk.tasks[-1][1]
    assert "THIS FILE: util.py" in body and "Diffs already accepted" in body and "a + b" in body
    assert open(repo / "calc.py").read().endswith("a - b\n")  # lane worktree untouched


def test_fail_refile_then_hand_off(repo):
    fk = Fake()
    eid = _start(repo, fk)
    fk.answer(WRONG)
    assert _check(eid, fk) == 1
    assert len(fk.tasks) == 2 and "try 2/2" in fk.tasks[-1][0] and "FAILED" in fk.tasks[-1][1]
    fk.answer(WRONG)
    assert _check(eid, fk) == 1
    assert len(fk.tasks) == 2
    assert fk.posts and fk.posts[0][0] == "LANE" and fk.posts[0][2] == "QWEN"
    assert "over to Claude" in fk.posts[0][1]
    assert E.load_state(eid)["done"] == "handed_off"
    assert _check(eid, fk) == 1


def test_final_patch_is_combined_and_applies(repo):
    fk = Fake()
    eid = _start(repo, fk)
    fk.answer(CALC)
    assert _check(eid, fk) == 0
    fk.answer(UTIL)  # without the import: test_util fails in scratch
    assert _check(eid, fk) == 1
    fk.answer(UTIL_IMPORT)
    assert _check(eid, fk) == 0
    patch = os.path.join(E.state_dir(), "%s.patch" % eid)
    assert open(patch).read() == CALC + UTIL_IMPORT
    assert fk.posts == [("LANE", "C4: plan %s done - review + apply %s" % (eid, patch), "QWEN")]
    subprocess.run(["git", "apply", "--check", patch], cwd=repo, check=True)
    assert open(repo / "util.py").read() == "def double(x):\n    return x\n"

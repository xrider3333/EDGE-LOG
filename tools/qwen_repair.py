"""C2 QWEN REPAIR LOOP (one door, MANAGER #222): pytest failures -> Q task -> Qwen diff -> scratch re-test, N tries
then Claude. Nothing here calls a model: the task goes through qwen_task.add_task and tools/qwen_runner.py does it.

  python tools/qwen_repair.py file <worktree> <nodeids-or-file>... [--tries 3] [--from LANE]
      run pytest there (10 min cap); all pass -> exit 0, nothing filed; else file ONE Q task, state in
      C:/EdgeLog/qwen_repair/<id>.json (<id> = r<Q number>; override dir with QWEN_REPAIR_DIR)
  python tools/qwen_repair.py check <id>
      read the Q task's RESULT, take the ```diff fence, `git apply --check` + apply it in a SCRATCH detached
      worktree, re-run the same tests there. Pass -> <id>.patch (review and apply it yourself; never applied to
      the lane's worktree). Fail -> next Q task with new output + previous diff while tries < N, else one inbox
      line to the lane: "C2: Qwen could not fix <tests> in N tries - over to Claude". Scratch removed after.
Exit codes: 0 pass/patch written, 1 refiled or handed off, 2 not ready (no RESULT yet).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qwen_task  # noqa: E402

TIMEOUT_S = 600
MAX_OUT = 8000
INSTRUCTION = ("Propose a minimal fix as a unified diff (paths relative to the worktree root, git style a/ b/) in "
               "your RESULT under a ```diff fence; touch only files under the worktree; never touch tests to make "
               "them pass unless the test itself is wrong, and say so. Read files only - do not run or write "
               "anything.")


def state_dir():
    return os.environ.get("QWEN_REPAIR_DIR") or r"C:\EdgeLog\qwen_repair"


def _state_path(rid):
    return os.path.join(state_dir(), "%s.json" % rid)


def load_state(rid):
    with open(_state_path(rid), encoding="utf-8") as f:
        return json.load(f)


def save_state(st):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = _state_path(st["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _state_path(st["id"]))


def trim(out, limit=MAX_OUT):
    """Keep the key traceback: from the FAILURES/ERRORS banner on (else the whole text), capped at limit chars."""
    m = re.search(r"^=+ (FAILURES|ERRORS) =+$", out, re.M)
    s = out[m.start():] if m else out
    if len(s) > limit:
        s = s[:limit // 2] + "\n... [trimmed] ...\n" + s[-(limit // 2):]
    return s


def run_tests(cwd, tests):
    """(passed, trimmed output)."""
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + list(tests)
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        partial = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        return False, trim("pytest TIMEOUT after %d s\n%s" % (TIMEOUT_S, partial))
    return p.returncode == 0, trim((p.stdout or "") + (p.stderr or ""))


def _body(st, output, prev_diff=None):
    parts = ["Worktree: %s" % st["worktree"], "Failing tests: %s" % " ".join(st["tests"]),
             "Try %d of %d (C2 repair loop)." % (st["try"], st["tries"]), "", INSTRUCTION, "",
             "pytest output:", "```", output, "```"]
    if prev_diff:
        parts += ["", "Your previous diff did NOT fix it (output above is after applying it):", "```diff",
                  prev_diff.rstrip("\n"), "```"]
    return "\n".join(parts)


def _file_task(st, output, prev_diff, add_task):
    title = "C2 repair %s try %d/%d" % (" ".join(st["tests"])[:50], st["try"], st["tries"])
    n = add_task(title, _body(st, output, prev_diff), frm=st["from"])
    st["q"].append(n)
    return n


def cmd_file(worktree, tests, tries=3, frm="MANAGER", add_task=None, runner=run_tests):
    add_task = add_task or qwen_task.add_task
    worktree = os.path.abspath(worktree)
    ok, out = runner(worktree, tests)
    if ok:
        print("C2: all pass - nothing filed")
        return None
    st = {"worktree": worktree, "tests": list(tests), "tries": int(tries), "try": 1, "from": frm, "q": []}
    n = _file_task(st, out, None, add_task)
    st["id"] = "r%d" % n
    save_state(st)
    print("C2: filed Q%d (repair id %s, try 1/%d)" % (n, st["id"], st["tries"]))
    return st["id"]


def task_result(n):
    p = qwen_task.find(n)
    if not p:
        return None
    text = qwen_task._read(p)[0]
    m = re.search(r"^## RESULT\s*$", text, re.M)
    return text[m.end():] if m else None


def extract_diff(result):
    m = re.search(r"```diff[^\n]*\n(.*?)```", result or "", re.S)
    if not m:
        return None
    d = m.group(1).replace("\r\n", "\n")
    return d if d.endswith("\n") else d + "\n"


def _git(cwd, *args, inp=None):
    return subprocess.run(["git"] + list(args), cwd=cwd, input=inp, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def try_in_scratch(worktree, diff, tests, runner=run_tests):
    """(passed, output). Detached scratch worktree at HEAD + the lane's uncommitted changes + diff; always removed."""
    scratch = tempfile.mkdtemp(prefix="c2scratch-")
    os.rmdir(scratch)
    r = _git(worktree, "worktree", "add", "--detach", scratch, "HEAD")
    if r.returncode:
        return False, "C2: scratch worktree add failed: %s" % r.stderr.strip()
    try:
        local = _git(worktree, "diff", "HEAD", "--binary").stdout
        if local.strip():
            _git(scratch, "apply", "--whitespace=nowarn", inp=local)
        chk = _git(scratch, "apply", "--check", "--whitespace=nowarn", inp=diff)
        if chk.returncode:
            return False, "C2: diff does not apply (git apply --check):\n%s" % chk.stderr.strip()
        ap = _git(scratch, "apply", "--whitespace=nowarn", inp=diff)
        if ap.returncode:
            return False, "C2: git apply failed:\n%s" % ap.stderr.strip()
        return runner(scratch, tests)
    finally:
        _git(worktree, "worktree", "remove", "--force", scratch)
        shutil.rmtree(scratch, ignore_errors=True)
        _git(worktree, "worktree", "prune")


def _hand_off(st, post):
    msg = "C2: Qwen could not fix %s in %d tries - over to Claude" % (" ".join(st["tests"]), st["tries"])
    if post is None:
        import chat_inbox
        post = chat_inbox.post
    post(st["from"], msg, "QWEN")
    st["done"] = "handed_off"
    return msg


def cmd_check(rid, add_task=None, post=None, runner=run_tests, result_of=task_result):
    add_task = add_task or qwen_task.add_task
    st = load_state(rid)
    if st.get("done"):
        print("C2: %s already %s" % (rid, st["done"]))
        return 0 if st["done"] == "patch" else 1
    res = result_of(st["q"][-1])
    if res is None:
        print("C2: Q%d has no RESULT yet" % st["q"][-1])
        return 2
    diff = extract_diff(res)
    if not diff:
        ok, out = False, "C2: RESULT had no ```diff fence"
    else:
        ok, out = try_in_scratch(st["worktree"], diff, st["tests"], runner)
    if ok:
        patch = os.path.join(state_dir(), "%s.patch" % rid)
        with open(patch, "w", encoding="utf-8", newline="\n") as f:
            f.write(diff)
        st["done"] = "patch"
        save_state(st)
        print("C2: PASS in scratch - review, then apply: git -C %s apply %s" % (st["worktree"], patch))
        return 0
    if st["try"] < st["tries"]:
        st["try"] += 1
        n = _file_task(st, out, diff, add_task)
        save_state(st)
        print("C2: still failing - filed Q%d (try %d/%d)" % (n, st["try"], st["tries"]))
        return 1
    msg = _hand_off(st, post)
    save_state(st)
    print(msg)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file")
    f.add_argument("worktree")
    f.add_argument("tests", nargs="+")
    f.add_argument("--tries", type=int, default=3)
    f.add_argument("--from", dest="frm", default="MANAGER")
    c = sub.add_parser("check")
    c.add_argument("id")
    a = ap.parse_args(argv)
    if a.cmd == "file":
        cmd_file(a.worktree, a.tests, a.tries, a.frm)
        return 0
    return cmd_check(a.id)


if __name__ == "__main__":
    sys.exit(main())

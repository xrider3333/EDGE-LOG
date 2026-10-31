"""C4 QWEN EDIT (one door): a Claude lane writes the patch plan, Qwen edits ONE file at a time. Nothing here calls a
model: each step is a Q task through qwen_task.add_task and tools/qwen_runner.py does it.

  python tools/qwen_edit.py plan <worktree> <plan.md> [--from LANE]
      validate the plan (goal line + one '## FILE <relative path>' section per file, max 8, every path inside the
      worktree, each with a 'Tests:' line), store state in C:/EdgeLog/qwen_edit/<id>.json (<id> = e<Q number>;
      override dir with QWEN_EDIT_DIR) and file a Q task for the FIRST file only.
  python tools/qwen_edit.py check <id>
      read the RESULT ```diff, refuse it if it touches any other file, apply it in a SCRATCH worktree that carries
      the accepted diffs so far, run that file's tests. Pass -> next file's task (or, after the last file,
      <id>.patch = combined diff + inbox line "C4: plan <id> done - review + apply <patch>"). Fail -> refile, up to
      2 tries per file, then an inbox line from QWEN to the lane. Never writes to the lane's worktree.
Template: docs/QWEN_EDIT_PLAN_TEMPLATE.md. Exit codes: 0 step passed / patch written, 1 refiled or handed off,
2 not ready (no RESULT yet).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qwen_task  # noqa: E402
from qwen_repair import extract_diff, run_tests, task_result, try_in_scratch  # noqa: E402

MAX_FILES = 8
TRIES = 2
MAX_CONTENT = 12000
INSTRUCTION = ("Return the edit as a unified diff for THIS file only under a ```diff fence (paths relative to the "
               "worktree root, git style a/ b/). Do not touch any other file. Read files only - do not run or "
               "write anything.")


class PlanError(ValueError):
    pass


def state_dir():
    return os.environ.get("QWEN_EDIT_DIR") or r"C:\EdgeLog\qwen_edit"


def _state_path(eid):
    return os.path.join(state_dir(), "%s.json" % eid)


def load_state(eid):
    with open(_state_path(eid), encoding="utf-8") as f:
        return json.load(f)


def save_state(st):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = _state_path(st["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _state_path(st["id"]))


def parse_plan(text, worktree):
    """-> {'goal', 'files': [{'path', 'change', 'tests'}]}. Raises PlanError."""
    text = text.replace("\r\n", "\n")
    parts = re.split(r"^## FILE[ \t]+(.+?)[ \t]*$", text, flags=re.M)
    head = [ln.strip() for ln in parts[0].splitlines() if ln.strip() and not ln.startswith("# ")]
    if not head:
        raise PlanError("plan has no goal line before the first '## FILE'")
    goal = re.sub(r"^goal:\s*", "", head[0], flags=re.I)
    files = []
    root = os.path.realpath(worktree)
    for i in range(1, len(parts), 2):
        rel = parts[i].strip().strip("`").replace("\\", "/")
        body = parts[i + 1].strip()
        if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel):
            raise PlanError("path must be relative to the worktree: %r" % rel)
        full = os.path.realpath(os.path.join(root, rel))
        if os.path.commonpath([root, full]) != root or full == root:
            raise PlanError("path escapes the worktree: %r" % rel)
        if any(f["path"] == rel for f in files):
            raise PlanError("file listed twice: %r" % rel)
        m = re.search(r"^(?:tests|acceptance(?: tests)?):\s*(.+)$", body, re.I | re.M)
        tests = re.split(r"[\s,]+", m.group(1).strip()) if m else []
        tests = [t.strip("`") for t in tests if t.strip("`")]
        if not tests:
            raise PlanError("no 'Tests:' line for %r" % rel)
        if not body.replace(m.group(0), "").strip():
            raise PlanError("no change described for %r" % rel)
        files.append({"path": rel, "change": body, "tests": tests})
    if not files:
        raise PlanError("plan has no '## FILE <path>' sections")
    if len(files) > MAX_FILES:
        raise PlanError("plan has %d files - max %d" % (len(files), MAX_FILES))
    return {"goal": goal, "files": files}


def diff_paths(diff):
    """Every path a unified diff touches (a/ and b/ sides, /dev/null dropped)."""
    out = set()
    for ln in diff.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", ln)
        if m:
            out.update(m.groups())
            continue
        m = re.match(r"^(?:---|\+\+\+) (\S+)", ln)
        if m and m.group(1) != "/dev/null":
            p = m.group(1)
            out.add(p[2:] if p[:2] in ("a/", "b/") else p)
    return out


def _content(worktree, rel):
    p = os.path.join(worktree, rel)
    if not os.path.exists(p):
        return "(new file - does not exist yet)"
    with open(p, encoding="utf-8", errors="replace") as f:
        s = f.read()
    if len(s) > MAX_CONTENT:
        s = s[:MAX_CONTENT // 2] + "\n... [middle trimmed - ask for a narrower plan if you need it] ...\n" + \
            s[-(MAX_CONTENT // 2):]
    return s


def _body(st, feedback=None, prev_diff=None):
    cur = st["files"][st["idx"]]
    parts = ["C4 plan %s - file %d of %d, try %d of %d" % (st.get("id", "?"), st["idx"] + 1, len(st["files"]),
                                                          st["try"], TRIES),
             "Worktree: %s" % st["worktree"], "", "THIS FILE: %s" % cur["path"], "", INSTRUCTION, "",
             "Acceptance tests: %s" % " ".join(cur["tests"]), "", "## Whole plan (context)", st["plan_text"].strip(),
             "", "## Current content of %s" % cur["path"], "```", _content(st["worktree"], cur["path"]), "```"]
    if st["accepted"]:
        parts += ["", "## Diffs already accepted (applied before yours)", "```diff",
                  "".join(st["accepted"]).rstrip("\n"), "```"]
    if prev_diff is not None or feedback:
        parts += ["", "## Your previous try FAILED", "```", feedback or "", "```"]
        if prev_diff:
            parts += ["```diff", prev_diff.rstrip("\n"), "```"]
    return "\n".join(parts)


def _file_task(st, add_task, feedback=None, prev_diff=None):
    cur = st["files"][st["idx"]]
    title = "C4 edit %s (%d/%d) try %d/%d" % (cur["path"][-50:], st["idx"] + 1, len(st["files"]), st["try"], TRIES)
    n = add_task(title, _body(st, feedback, prev_diff), frm=st["from"])
    st["q"].append(n)
    return n


def cmd_plan(worktree, plan_path, frm="MANAGER", add_task=None):
    add_task = add_task or qwen_task.add_task
    worktree = os.path.abspath(worktree)
    with open(plan_path, encoding="utf-8") as f:
        text = f.read()
    plan = parse_plan(text, worktree)
    st = {"worktree": worktree, "plan_text": text, "goal": plan["goal"], "files": plan["files"], "idx": 0,
          "try": 1, "from": frm, "q": [], "accepted": []}
    n = _file_task(st, add_task)
    st["id"] = "e%d" % n
    save_state(st)
    print("C4: filed Q%d (plan %s, file 1/%d %s)" % (n, st["id"], len(st["files"]), st["files"][0]["path"]))
    return st["id"]


def _post(post):
    if post is None:
        import chat_inbox
        post = chat_inbox.post
    return post


def cmd_check(eid, add_task=None, post=None, runner=run_tests, result_of=task_result):
    add_task = add_task or qwen_task.add_task
    st = load_state(eid)
    if st.get("done"):
        print("C4: %s already %s" % (eid, st["done"]))
        return 0 if st["done"] == "patch" else 1
    res = result_of(st["q"][-1])
    if res is None:
        print("C4: Q%d has no RESULT yet" % st["q"][-1])
        return 2
    cur = st["files"][st["idx"]]
    diff = extract_diff(res)
    if not diff:
        ok, out = False, "C4: RESULT had no ```diff fence"
    else:
        other = sorted(p for p in diff_paths(diff) if p != cur["path"])
        if other:
            ok, out = False, "C4: REFUSED - diff touches other files %s; THIS file only: %s" % (other, cur["path"])
        elif not diff_paths(diff):
            ok, out = False, "C4: diff names no file"
        else:
            ok, out = try_in_scratch(st["worktree"], "".join(st["accepted"]) + diff, cur["tests"], runner)
    if ok:
        st["accepted"].append(diff)
        if st["idx"] + 1 < len(st["files"]):
            st["idx"] += 1
            st["try"] = 1
            n = _file_task(st, add_task)
            save_state(st)
            print("C4: %s PASS - filed Q%d for file %d/%d" % (cur["path"], n, st["idx"] + 1, len(st["files"])))
            return 0
        patch = os.path.join(state_dir(), "%s.patch" % eid)
        with open(patch, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(st["accepted"]))
        st["done"] = "patch"
        save_state(st)
        msg = "C4: plan %s done - review + apply %s" % (eid, patch)
        _post(post)(st["from"], msg, "QWEN")
        print(msg)
        return 0
    if st["try"] < TRIES:
        st["try"] += 1
        n = _file_task(st, add_task, out, diff)
        save_state(st)
        print("C4: %s failed - refiled Q%d (try %d/%d)" % (cur["path"], n, st["try"], TRIES))
        return 1
    msg = "C4: plan %s - Qwen could not edit %s in %d tries (%d of %d files accepted) - over to Claude" % (
        eid, cur["path"], TRIES, len(st["accepted"]), len(st["files"]))
    _post(post)(st["from"], msg, "QWEN")
    st["done"] = "handed_off"
    save_state(st)
    print(msg)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("worktree")
    p.add_argument("plan")
    p.add_argument("--from", dest="frm", default="MANAGER")
    c = sub.add_parser("check")
    c.add_argument("id")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        try:
            cmd_plan(a.worktree, a.plan, a.frm)
        except PlanError as e:
            print("C4: plan refused - %s" % e)
            return 1
        return 0
    return cmd_check(a.id)


if __name__ == "__main__":
    sys.exit(main())

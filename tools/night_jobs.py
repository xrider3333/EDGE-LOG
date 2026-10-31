"""B19 NIGHT JOBS, LOCAL (MANAGER #201, owner 10-30 19:00: no cloud routine - Qwen does it, local). Code-only tidy jobs
J1-J5 from C:\\EdgeLog\\manager\\night_jobs.md. The tool does the mechanical part; each job files ONE Q task (tools/qwen_task.py
add) carrying the raw output + the shared guard text; the Qwen runner writes the fix list / PR body under ## RESULT; `pr`
puts that result on branch night/<job>-<date> as docs/night/<job>-<date>.md and pushes the branch (never main). Claude
reviews before anything merges. No code is changed by this tool or by Qwen.

    python tools/night_jobs.py run [--job J1,J3] [--dry-run]    today's jobs (J1 Mon, J2 Wed, J3 daily, J4 Fri, J5 1st weekday)
    python tools/night_jobs.py pr [--dry-run]                   push a branch for each done night task not yet pushed

Mechanical part per job: J1 tools/*.py stems referenced nowhere (Q12 method) + pyflakes unused imports; J2 docs/*.md and
README naming tools/*.py or tests/*.py paths that no longer exist; J3 the pure-unit test files 3x (fixed order, then reverse
order) and the tests whose outcome differs; J4 pyflakes on tools/ api/ tests/; J5 TODO/FIXME/XXX with file:line + blame date.
State (which Q task belongs to which job/date, which were pushed): C:\\EdgeLog\\manager\\night_jobs_state.json.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qwen_task as QT  # noqa: E402

STATE = os.environ.get("NIGHT_JOBS_STATE", r"C:\EdgeLog\manager\night_jobs_state.json")
JOBS_MD = r"C:\EdgeLog\manager\night_jobs.md"
MAX_RAW = 12000
TEXT_EXT = (".py", ".md", ".ps1", ".json", ".vbs", ".cmd", ".bat", ".html", ".txt", ".yaml", ".yml", ".cfg", ".ini",
            ".sh", ".cs", ".pine", ".service", ".timer")
SKIP_DIRS = {".git", ".cline", "node_modules", "__pycache__", ".venv", "dist", ".pytest_cache"}
# test files that need local data, the engine tier or the network are not "pure unit"
NOT_UNIT = re.compile(r"augur_engine|augur_strategies|C:\\\\EdgeLog|C:/EdgeLog|firestore|requests\.|urllib|socket|"
                      r"pytest\.mark\.(live|network|slow)")


def _git(*a, cwd=REPO):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def jobs_for(day):
    """J1 Mon, J2 Wed, J3 every weekday, J4 Fri, J5 the first weekday of the month."""
    wd, out = day.weekday(), []
    if wd > 4:
        return out
    if wd == 0:
        out.append("J1")
    if wd == 2:
        out.append("J2")
    out.append("J3")
    if wd == 4:
        out.append("J4")
    first = day.replace(day=1)
    while first.weekday() > 4:
        first += datetime.timedelta(days=1)
    if day == first:
        out.append("J5")
    return out


def _corpus(exclude_tests=True):
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (exclude_tests and d == "tests"
                                                                 and os.path.samefile(root, REPO))]
        for f in files:
            if f.endswith(TEXT_EXT):
                p = os.path.join(root, f)
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        yield p, fh.read()
                except OSError:
                    continue


def _pyflakes(paths):
    p = subprocess.run([sys.executable, "-m", "pyflakes", *paths], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return [ln for ln in (p.stdout + p.stderr).splitlines() if ln.strip()]


def j1():
    stems = {f[:-3]: os.path.join(REPO, "tools", f) for f in os.listdir(os.path.join(REPO, "tools"))
             if f.endswith(".py")}
    alive = set()
    for p, txt in _corpus():
        for s in stems:
            if s not in alive and os.path.normcase(p) != os.path.normcase(stems[s]) and s in txt:
                alive.add(s)
    dead = sorted(set(stems) - alive)
    unused = [ln for ln in _pyflakes(["tools", "api"]) if "imported but unused" in ln]
    return ("tools/*.py stems referenced nowhere outside themselves (tests/ excluded; Q12 method): %d\n%s\n\n"
            "pyflakes 'imported but unused' in tools/ api/: %d\n%s"
            % (len(dead), "\n".join("tools/%s.py" % s for s in dead), len(unused), "\n".join(unused)))


def j2():
    ref = re.compile(r"\b((?:tools|tests|api)/[\w/.-]+\.(?:py|ps1|vbs|cmd|bat|json))")
    out = []
    docs = [os.path.join(REPO, "README.md")] + [os.path.join(REPO, "docs", f) for f in
                                                 sorted(os.listdir(os.path.join(REPO, "docs"))) if f.endswith(".md")]
    for d in docs:
        if not os.path.exists(d) or re.search(r"PREREG|PREDATA", os.path.basename(d)):
            continue
        with open(d, encoding="utf-8", errors="replace") as fh:
            for n, ln in enumerate(fh, 1):
                for m in ref.findall(ln):
                    if not os.path.exists(os.path.join(REPO, m)):
                        out.append("%s:%d: %s" % (os.path.relpath(d, REPO), n, m))
    return "doc lines naming a repo path that no longer exists (PREREG/PREDATA skipped): %d\n%s" % (
        len(out), "\n".join(out))


def unit_tests():
    keep = []
    for f in sorted(os.listdir(os.path.join(REPO, "tests"))):
        if f.startswith("test_") and f.endswith(".py"):
            with open(os.path.join(REPO, "tests", f), encoding="utf-8", errors="replace") as fh:
                if not NOT_UNIT.search(fh.read()):
                    keep.append("tests/" + f)
    return keep


def _pytest_outcomes(files, timeout=1800):
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", *files], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    res = {}
    for ln in p.stdout.splitlines():
        m = re.match(r"(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)", ln)
        if m:
            res[m.group(2)] = m.group(1)
    return res


def j3():
    files = unit_tests()
    runs = [_pytest_outcomes(files), _pytest_outcomes(files), _pytest_outcomes(list(reversed(files)))]
    ids = sorted(set().union(*runs))
    flaky = ["%s  %s" % (t, " / ".join(r.get(t, "missing") for r in runs)) for t in ids
             if len({r.get(t) for r in runs}) > 1]
    failing = sorted(t for t in ids if all(r.get(t) in ("FAILED", "ERROR") for r in runs))
    return ("pure-unit files: %d, tests: %d. 3 runs: fixed order, fixed order, reversed file order.\n"
            "outcome differs across runs: %d\n%s\n\nfails in all 3 (not flaky, listed for info): %d\n%s"
            % (len(files), len(ids), len(flaky), "\n".join(flaky), len(failing), "\n".join(failing)))


def j4():
    lines = _pyflakes(["tools", "api", "tests"])
    return "pyflakes on tools/ api/ tests/ (ruff is not installed; pyflakes is): %d\n%s" % (len(lines), "\n".join(lines))


def j5():
    p = _git("grep", "-n", "-I", "-E", r"\b(TODO|FIXME|XXX)\b", "--", "*.py", "*.md", "*.ps1", "*.html")
    hits, out = p.stdout.splitlines()[:400], []
    for h in hits:
        f, n = h.split(":", 2)[:2]
        b = _git("blame", "-L", "%s,%s" % (n, n), "--date=short", "--", f).stdout
        m = re.search(r"\d{4}-\d{2}-\d{2}", b)
        out.append("%s  (%s)" % (h[:240], m.group(0) if m else "?"))
    return "TODO/FIXME/XXX hits: %d (first 400 listed, blame date in brackets)\n%s" % (len(p.stdout.splitlines()),
                                                                                        "\n".join(out))


RUN = {"J1": j1, "J2": j2, "J3": j3, "J4": j4, "J5": j5}
TITLE = {"J1": "dead code", "J2": "stale docs", "J3": "flaky tests", "J4": "lint hygiene", "J5": "TODO census"}


def job_text(job, md=JOBS_MD):
    """(guard text, this job's prompt) from night_jobs.md."""
    txt = open(md, encoding="utf-8").read()

    def sect(head):
        m = re.search(r"(?ms)^## %s.*?\n(.*?)(?=^## |\Z)" % re.escape(head), txt)
        return re.sub(r"(?m)^> ?", "", m.group(1)).strip() if m else ""
    return sect("Shared guard text"), sect(job)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {"tasks": []}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def body(job, raw, day):
    guard, prompt = job_text(job)
    if len(raw) > MAX_RAW:
        raw = raw[:MAX_RAW] + "\n... (cut at %d chars)" % MAX_RAW
    return ("Night job %s (%s), %s. Filed by tools/night_jobs.py (B19). READ-ONLY: change no file; write your answer under\n"
            "## RESULT in this file. The answer becomes the PR body on branch night/%s-%s; Claude reviews it.\n\n"
            "## Guard\n%s\n\n## Job\n%s\n\n## What to write\nA fix list: one line per change worth making (file:line, the "
            "change, why it is behaviour-neutral), then items left alone and why. Use ONLY the raw output below; check a "
            "doubtful line with grep before listing it. If nothing is worth doing, write 'nothing worth a PR'.\n\n"
            "## Raw output\n```\n%s\n```\n" % (job, TITLE[job], day, job.lower(), day, guard, prompt, raw))


def cmd_run(jobs, dry, day):
    st = load_state()
    for j in jobs:
        raw = RUN[j]()
        if dry:
            print("== %s ==\n%s\n" % (j, raw[:3000]))
            continue
        n = QT.add_task("Night %s %s %s" % (j, TITLE[j], day), body(j, raw, day), frm="NIGHT-JOBS")
        st["tasks"].append({"job": j, "day": day, "q": n, "pushed": None})
        print("%s -> Q%d" % (j, n))
    if not dry:
        save_state(st)


def _result(q):
    p = QT.find(q)
    if not p:
        return None, None
    text = QT._read(p)[0]
    status = next((ln for ln in text.splitlines()[:3] if ln.lower().startswith("status:")), "")
    m = re.search(r"(?ms)^## RESULT\s*\n(.*)", text)
    return status, (m.group(1).strip() if m else "")


def cmd_pr(dry):
    st = load_state()
    for t in st["tasks"]:
        if t.get("pushed"):
            continue
        status, res = _result(t["q"])
        if not res or not any(i in status for i in ("🟢", "✅")):
            continue
        br = "night/%s-%s" % (t["job"].lower(), t["day"])
        if dry:
            print("would push %s from Q%d (%d chars)" % (br, t["q"], len(res)))
            continue
        wt = os.path.join(os.path.dirname(REPO), "night-" + t["job"].lower())
        _git("fetch", "-q", "origin", "main")
        _git("worktree", "remove", "--force", wt)
        r = _git("worktree", "add", "-B", br, wt, "origin/main")
        if r.returncode:
            print("worktree failed for %s: %s" % (br, r.stderr.strip()))
            continue
        os.makedirs(os.path.join(wt, "docs", "night"), exist_ok=True)
        rel = "docs/night/%s-%s.md" % (t["job"].lower(), t["day"])
        with open(os.path.join(wt, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write("# Night %s %s - %s (Q%d, written by Qwen, NOT reviewed)\n\n%s\n" % (
                t["job"], TITLE[t["job"]], t["day"], t["q"], res))
        _git("add", rel, cwd=wt)
        _git("commit", "-q", "-m", "night %s %s: Qwen fix list (Q%d), for Claude review" % (t["job"], t["day"], t["q"]),
             cwd=wt)
        r = _git("push", "-q", "-u", "origin", br, cwd=wt)
        _git("worktree", "remove", "--force", wt)
        if r.returncode:
            print("push failed for %s: %s" % (br, r.stderr.strip()))
            continue
        t["pushed"] = br
        print("pushed %s -> https://github.com/xrider3333/EDGE-LOG/compare/main...%s?expand=1" % (br, br))
    if not dry:
        save_state(st)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "pr"])
    ap.add_argument("--job", default=None, help="comma list, e.g. J1,J3 (default: today's schedule)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    day = datetime.date.today()
    if a.cmd == "run":
        jobs = [j.strip().upper() for j in a.job.split(",")] if a.job else jobs_for(day)
        cmd_run([j for j in jobs if j in RUN], a.dry_run, day.isoformat())
    else:
        cmd_pr(a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

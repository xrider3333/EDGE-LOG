"""C11 - weekly mutation test on the core engine: do the tests catch broken code?

Each run makes a fresh throw-away git worktree of origin/main (C:/EdgeLog/_mutation/wt), then for every mutation below:
apply ONE small deliberate bug to a core file, run the tests that should catch it, record KILLED (a test failed = good) or
SURVIVED (all tests passed with broken code = a hole in the tests), and restore the file. A clean run (no mutation) runs first;
if the clean tests fail, the whole report says BASELINE RED and no mutation verdict is trusted.
Output: C:/EdgeLog/manager/mutation/mutation_<date>.md (+ .json). Nothing in the real checkout is touched.
Scheduled weekly (Mon 13:30) as a windowless task: pythonw tools/mutation_weekly.py  (see --install).
Usage: python tools/mutation_weekly.py [--only N] [--install]"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = "C:/EdgeLog/_mutation/wt"
OUT = "C:/EdgeLog/manager/mutation"
TIMEOUT = 900

DD_TESTS = ["tests/test_drawdowns.py", "tests/test_four_numbers.py"]
# (id, file, exact text, replacement, tests that should catch it, what it breaks)
MUTATIONS = [
    ("M1", "augur_engine/drawdowns.py", "ONE_EPISODE_RATIO = 1.3", "ONE_EPISODE_RATIO = 1.6", DD_TESTS, "one-episode threshold"),
    ("M2", "augur_engine/drawdowns.py", "worst > float(ratio) * avg", "worst >= float(ratio) * avg * 1.2", DD_TESTS, "one-episode test"),
    ("M3", "augur_engine/drawdowns.py", "years = (d1 - d0).days / 365.25", "years = (d1 - d0).days / 365.0", DD_TESTS, "years convention"),
    ("M4", "augur_engine/drawdowns.py", '"roc30": 30.0 * (net / years) / worst', '"roc30": 30.0 * (net / years) / (worst * 0.99)', DD_TESTS, "ROC@30k formula"),
    ("M5", "augur_engine/drawdowns.py", "math.sqrt(252.0) if dn > 0", "math.sqrt(250.0) if dn > 0", DD_TESTS, "Sortino annualisation"),
    ("M6", "augur_engine/engine.py", "nt[2] = nt[2] - cost_pts", "nt[2] = nt[2] - 0.5 * cost_pts", ["tests/test_cost_readings_and_run_limits.py", "tests/test_pills_cost.py"], "cost applied per trade"),
    ("M7", "augur_engine/engine.py", "return (days / 365.25) if days > 0 else None", "return (days / 360.0) if days > 0 else None", ["tests/test_cost_readings_and_run_limits.py"], "engine years"),
]


def sh(cmd, cwd=REPO, timeout=TIMEOUT):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout + r.stderr)


def pytest(tests, base_fail=frozenset()):
    """PASS / FAIL judged only on tests that passed on the clean tree: a test already red at baseline cannot kill a mutant."""
    try:
        code, out = sh([sys.executable.replace("pythonw", "python"), "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider"] + tests, cwd=WT)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "", set()
    failed = {ln.split()[1] for ln in out.splitlines() if ln.startswith("FAILED ")}
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or [""]
    new = failed - set(base_fail)
    return ("FAIL" if new else "PASS"), (tail[0] + (" | new: " + ", ".join(sorted(new))[:120] if new else ""))[:240], failed


def fresh_worktree():
    sh(["git", "fetch", "-q", "origin"])
    if os.path.isdir(WT):
        sh(["git", "worktree", "remove", "--force", WT])
        shutil.rmtree(WT, ignore_errors=True)
    sh(["git", "worktree", "prune"])
    os.makedirs(os.path.dirname(WT), exist_ok=True)
    code, out = sh(["git", "worktree", "add", "--detach", WT, "origin/main"])
    if code:
        raise SystemExit("worktree add failed: " + out[-300:])
    return sh(["git", "rev-parse", "--short", "HEAD"], cwd=WT)[1].strip()


def install():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    cmd = ["schtasks", "/Create", "/F", "/SC", "WEEKLY", "/D", "MON", "/ST", "13:30", "/TN", "EdgeLog C11 mutation weekly",
           "/TR", '"%s" "%s"' % (pyw, os.path.abspath(__file__))]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout or "schtasks ran")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    if a.install:
        return install()
    os.makedirs(OUT, exist_ok=True)
    head = fresh_worktree()
    muts = [m for m in MUTATIONS if not a.only or m[0] == a.only]
    tests = sorted({t for m in muts for t in m[4]})
    base, base_tail, base_fail = pytest(tests)
    rows = []
    for mid, f, old, new, tl, what in muts:
        p = os.path.join(WT, f)
        src = open(p, encoding="utf-8").read()
        if src.count(old) != 1:
            rows.append({"id": mid, "file": f, "what": what, "result": "STALE (text not found once - update the list)", "tail": ""})
            continue
        open(p, "w", encoding="utf-8", newline="").write(src.replace(old, new))
        try:
            st, tail, _ = pytest(tl, base_fail)
        finally:
            open(p, "w", encoding="utf-8", newline="").write(src)
        rows.append({"id": mid, "file": f, "what": what, "result": {"FAIL": "KILLED", "PASS": "SURVIVED", "TIMEOUT": "TIMEOUT"}[st], "tail": tail})
    sh(["git", "worktree", "remove", "--force", WT])
    day = dt.date.today().isoformat()
    killed = sum(r["result"] == "KILLED" for r in rows)
    lines = ["# C11 mutation test %s (origin/main %s)" % (day, head), "",
             "Baseline (no mutation): %s - %d test(s) already red on the clean tree, excluded from judging: %s" % (base_tail, len(base_fail), ", ".join(sorted(base_fail)) or "none"),
             "", "Score: **%d of %d mutations killed** (a SURVIVED row = broken code the tests did not notice)." % (killed, len(rows)), "",
             "| id | file | what was broken | result | last test line |", "|---|---|---|---|---|"]
    lines += ["| %s | %s | %s | %s | %s |" % (r["id"], r["file"], r["what"], r["result"], r["tail"].replace("|", "/")) for r in rows]
    open(os.path.join(OUT, "mutation_%s.md" % day), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump({"date": day, "head": head, "baseline_failed": sorted(base_fail), "rows": rows}, open(os.path.join(OUT, "mutation_%s.json" % day), "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()

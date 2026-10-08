"""SHIP LINT - no new roll detector (owner ask 2026-10-08 via MANAGER #54, item 4).

The 09-25 roll audit found 25 strategy files each carrying its own copy of a day-level roll-seam
detector that saw 19 of 64 NQ switches. They now import the one audited calendar
(augur_engine/rolls.seam_days, built from tools/data/rolls_<ROOT>.csv). This test runs in the
pre-push suite, so it gates every ship: it FAILS when any function in augur_strategies/,
augur_engine/ or api/ defines its own roll detector, and when a NEW or CHANGED file under tools/
does. augur_engine/rolls.py is the only home of the calendar. Research scripts in tools/ that
already carried a detector before this rule are listed in GRANDFATHERED_TOOLS with the reason; they
are history, and the list never grows - a new tool imports augur_engine.rolls instead.

A function counts as a roll detector when ANY of
  * its name says so: detect_roll*, find_roll*, *roll_seam*, *roll_seams*, *seam_detect*,
    *detect_seam*, roll_gap*, *_roll_days, *_rolls_from_gaps (nested defs included); or
  * it has the retired copy's signature: both a `ratio_th` and an `abs_th` parameter; or
  * it carries the retired ALGORITHM, whatever it is called (TTM review #56 point 6): a quarterly
    month set (3, 6, 9, 12) or `month % 3`, an absolute value, and a max / argmax pick - the
    "largest |open - prior close| near each quarter's third week" search.
And, in augur_strategies / augur_engine / api, the evasions are refused too: binding a detector name
by assignment or lambda, importing one from anywhere but augur_engine.rolls, a strategy importing
from tools/, and reaching one through getattr / exec / eval / __import__ / import_module. The
run-time crossing guard in the engine stays the backstop for what a lint cannot see.
"""
import ast
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNED = ("augur_strategies", "augur_engine", "api")
HOME = os.path.join("augur_engine", "rolls.py")
NAME_RE = re.compile(r"(^|_)(detect|find)_?rolls?($|_)|roll_?seams?|seam_?detect|detect_?seams?|"
                     r"^roll_?gaps?|_roll_days$|rolls_from_gaps", re.IGNORECASE)
# Named exemptions OUTSIDE rolls.py, each with its reason. Not a detector a trade can read.
EXEMPT = {
    "augur_engine/data_quality.py::roll_seam_check":
        "audits a master against its adjusted twin (stack pill 2.6); no backtest or trade reads it",
    "augur_engine/setup_kit.py::contract_switch_sessions":
        "SETUPS research harness (setups lane): picks the one session per quarter whose prior-day "
        "level is blanked on 24h tapes - a heuristic found by the algorithm fingerprint 2026-10-08, "
        "flagged to MANAGER to move onto rolls.seam_days_for by its owning lane; no engine run reads it",
}
# tools/ files that defined a detector BEFORE 2026-10-08 live in tests/_roll_lint_baseline.txt -
# historical research, written once; that list never grows.


def _baseline():
    p = os.path.join(ROOT, "tests", "_roll_lint_baseline.txt")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as fh:
        return {ln.strip().replace("\\", "/") for ln in fh if ln.strip() and not ln.startswith("#")}


QUARTER = {3, 6, 9, 12}
PICKS = {"max", "argmax", "nanargmax", "argsort", "sorted", "idxmax"}
DYNAMIC = {"getattr", "exec", "eval", "__import__", "import_module"}


def _has_algorithm(fn_node):
    """The retired detector's fingerprint inside one function (nested code included)."""
    quarter = absval = pick = False
    for n in ast.walk(fn_node):
        if isinstance(n, (ast.Tuple, ast.List, ast.Set)):
            vals = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, int)}
            if QUARTER <= vals:
                quarter = True
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and \
                isinstance(n.right, ast.Constant) and n.right.value == 3 and \
                isinstance(n.left, ast.Attribute) and n.left.attr == "month":
            quarter = True
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in ("abs", "fabs", "absolute"):
                absval = True
            if name in PICKS:
                pick = True
    return quarter and absval and pick


def detectors_in_source(src, filename="<src>"):
    """[(function name, line)] of roll detectors defined in `src`: by name, by the retired signature,
    or by the retired algorithm."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = {a.arg for a in node.args.args + node.args.kwonlyargs}
        if NAME_RE.search(node.name) or {"ratio_th", "abs_th"} <= args or _has_algorithm(node):
            hits.append((node.name, node.lineno))
    return hits


def evasions_in_source(src, filename="<src>", strategy=False):
    """[(what, line)] of ways to reach a roll detector without defining one: a detector name bound
    by assignment / lambda, imported from anywhere but augur_engine.rolls, named in a getattr / exec /
    eval / import call; and, in a strategy file, any import from tools/ or any exec / eval."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod = (n.module or "")
            from_rolls = mod in ("augur_engine.rolls", "rolls") or (n.level and mod == "rolls")
            if strategy and mod.split(".")[0] == "tools":
                hits.append(("imports from tools/ (%s)" % mod, n.lineno))
            for a in n.names:
                if not from_rolls and (NAME_RE.search(a.name) or NAME_RE.search(a.asname or "")):
                    hits.append(("imports %s from %s" % (a.name, mod or "."), n.lineno))
        elif isinstance(n, ast.Import):
            for a in n.names:
                if strategy and a.name.split(".")[0] == "tools":
                    hits.append(("imports tools/ (%s)" % a.name, n.lineno))
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for tg in targets:
                for x in ast.walk(tg):
                    if isinstance(x, ast.Name) and NAME_RE.search(x.id):
                        hits.append(("binds %s by assignment" % x.id, n.lineno))
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in DYNAMIC:
                if strategy and name in ("exec", "eval"):
                    hits.append(("calls %s" % name, n.lineno))
                for a in n.args:
                    for x in ast.walk(a):
                        if isinstance(x, ast.Constant) and isinstance(x.value, str) and \
                                (NAME_RE.search(x.value) or (strategy and x.value.startswith("tools"))):
                            hits.append(("%s(%r)" % (name, x.value[:40]), n.lineno))
    return hits


def _py_files(rel_dir):
    base = os.path.join(ROOT, rel_dir)
    for d, _dirs, files in os.walk(base):
        if "__pycache__" in d:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
        return fh.read()


@pytest.mark.parametrize("rel_dir", SCANNED)
def test_no_roll_detector_outside_the_audited_module(rel_dir):
    bad = []
    for rel in _py_files(rel_dir):
        if rel == HOME.replace("\\", "/"):
            continue
        src = _read(rel)
        for name, line in detectors_in_source(src, rel):
            if "%s::%s" % (rel, name) in EXEMPT:
                continue
            bad.append("%s:%d %s()" % (rel, line, name))
        for what, line in evasions_in_source(src, rel, strategy=(rel_dir == "augur_strategies")):
            if "%s::%s" % (rel, what) in EXEMPT:
                continue
            bad.append("%s:%d %s" % (rel, line, what))
    assert not bad, ("roll detector defined outside augur_engine/rolls.py - import "
                     "augur_engine.rolls.seam_days (the one audited calendar) instead:\n  "
                     + "\n  ".join(bad))


def _changed_tools():
    """tools/*.py files new or changed against origin/main; None when git cannot say."""
    try:
        out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", "origin/main", "--", "tools"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip().endswith(".py")]


def test_no_new_roll_detector_in_tools():
    changed = _changed_tools()
    if changed is None:
        pytest.skip("git cannot list changed files here (CI shallow clone) - the full scan above still runs")
    base = _baseline()
    bad = []
    for rel in changed:
        if rel in base or not os.path.exists(os.path.join(ROOT, rel)):
            continue
        for name, line in detectors_in_source(_read(rel), rel):
            bad.append("%s:%d %s()" % (rel, line, name))
    assert not bad, ("new roll detector in tools/ - import augur_engine.rolls (seam_days, crossing_trades, "
                     "back_adjust) instead:\n  " + "\n  ".join(bad))


def test_the_lint_catches_a_planted_copy():
    planted = ("def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0):\n"
               "    return []\n"
               "def my_gap_finder(o, c, ts, ratio_th=3, abs_th=10):\n"
               "    return []\n"
               "def find_rolls(x):\n"
               "    return x\n"
               "def ordinary(x, ratio=2):\n"
               "    return x\n")
    names = [n for n, _ in detectors_in_source(planted)]
    assert names == ["detect_roll_seams", "my_gap_finder", "find_rolls"]


def test_the_lint_catches_ttm_evasions():
    """TTM review #56 point 6: a renamed copy with renamed knobs, the logic nested inside
    run_backtest, a lambda, an import from a grandfathered tools/ file, getattr / exec."""
    renamed = (
        "import numpy as np\n"
        "def q(o, c, ts, r=2.5, a=15.0):\n"
        "    gap = np.abs(o[1:] - c[:-1])\n"
        "    qs = [t for t in ts if t.month in (3, 6, 9, 12)]\n"
        "    return [int(np.argmax(gap))] if qs else []\n")
    assert [n for n, _ in detectors_in_source(renamed)] == ["q"]
    nested = (
        "def run_backtest(open_, high, low, close, **kw):\n"
        "    def helper(ts, g):\n"
        "        return max((i for i, t in enumerate(ts) if t.month % 3 == 0), key=lambda i: abs(g[i]))\n"
        "    return {}\n")
    assert [n for n, _ in detectors_in_source(nested)] == ["run_backtest", "helper"]
    ev = (
        "from tools.rocfrontier_scan import detect_roll_seams as q\n"
        "from tools.misc import helper\n"
        "import tools.r16_misc_triage\n"
        "detect_roll_seams = lambda *a: []\n"
        "f = getattr(mod, 'detect_roll_seams')\n"
        "exec('x = 1')\n")
    whats = [w for w, _ in evasions_in_source(ev, strategy=True)]
    assert any("imports detect_roll_seams" in w for w in whats)
    assert sum(1 for w in whats if "tools/" in w) == 3
    assert any("binds detect_roll_seams" in w for w in whats)
    assert any(w.startswith("getattr(") for w in whats) and "calls exec" in whats
    ok = "from augur_engine.rolls import seam_days as detect_roll_seams\n"
    assert evasions_in_source(ok, strategy=True) == []


def test_roll_aware_files_adjust_from_the_table():
    """Every ROLL_AWARE entry (the guard's only exception) reads the roll table itself and never
    asks a seam detector, so its crossing trades carry no contract step."""
    from augur_engine import rolls as R
    for fn in sorted(R.ROLL_AWARE):
        src = _read(os.path.join("augur_strategies", fn))
        assert "rolls_%s.csv" in src or "rolls_" in src, fn
        assert "detect_roll_seams(" not in src.replace("import seam_days as detect_roll_seams", ""), fn

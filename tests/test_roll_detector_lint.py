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
PICKS = {"max", "argmax", "nanargmax", "argsort", "sorted", "idxmax", "nlargest", "nsmallest", "sort",
         "partition", "argpartition", "nanmax", "amax", "sort_values", "heappush", "heappop"}
ABS = {"abs", "fabs", "absolute", "sign", "hypot"}
QUARTER_ATTRS = {"quarter", "is_quarter_end", "is_quarter_start", "qyear"}
DYNAMIC = {"getattr", "exec", "eval", "__import__", "import_module", "spec_from_file_location", "run_path",
           "run_module"}
STRATEGY_BANNED_CALLS = {"compile", "FunctionType", "globals", "run_path", "run_module", "exec", "eval"}
TOOLS_MODULE_RE = re.compile(r"(^|[/\\])tools[/\\][A-Za-z_]\w*\.py$|^tools(\.[A-Za-z_]\w*)+$")


def _call_name(n):
    f = n.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _fold(node):
    """The string a constant expression builds ('roll_' + 'seam_check', f-strings of constants),
    or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        x, y = _fold(node.left), _fold(node.right)
        return None if x is None or y is None else x + y
    if isinstance(node, ast.JoinedStr):
        parts = [_fold(v) if not isinstance(v, ast.FormattedValue) else None for v in node.values]
        return None if any(p is None for p in parts) else "".join(parts)
    return None


def _month_names(tree):
    """Names assigned from a `.month` attribute anywhere (mo = t.month)."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Attribute) and n.value.attr == "month":
            out |= {tg.id for tg in n.targets if isinstance(tg, ast.Name)}
    return out


def _quarter_names(tree):
    """Names assigned from a quarter cue anywhere (QM = set(range(3, 13, 3)), Q = (3, 6, 9, 12)), so
    the cue still counts where the name is used in another scope."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and _quarter_cue_in(n.value):
            out |= {tg.id for tg in n.targets if isinstance(tg, ast.Name)}
    return out


def _quarter_cue_in(node):
    for n in ast.walk(node):
        if isinstance(n, (ast.Tuple, ast.List, ast.Set)):
            vals = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, int)}
            if QUARTER <= vals:
                return True
        if isinstance(n, ast.Call) and _call_name(n) in ("range", "arange") and len(n.args) == 3 and \
                all(isinstance(x, ast.Constant) for x in n.args) and \
                n.args[0].value == 3 and n.args[2].value == 3 and n.args[1].value in (12, 13):
            return True
    return False


def _has_algorithm(node, months=frozenset(), quarters=frozenset()):
    """The retired detector's fingerprint inside one scope (nested code included): a quarter cue,
    an absolute value, and a pick of the largest - each in any of its common spellings."""
    quarter = absval = pick = False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in quarters:
            quarter = True
        elif isinstance(n, (ast.Tuple, ast.List, ast.Set)):
            vals = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, int)}
            if QUARTER <= vals:
                quarter = True
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and \
                isinstance(n.right, ast.Constant) and n.right.value == 3 and \
                ((isinstance(n.left, ast.Attribute) and n.left.attr == "month") or
                 (isinstance(n.left, ast.Name) and n.left.id in months)):
            quarter = True
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow) and \
                isinstance(n.right, ast.Constant) and n.right.value == 2:
            absval = True
        elif isinstance(n, ast.Attribute) and n.attr in QUARTER_ATTRS:
            quarter = True
        elif isinstance(n, ast.Call):
            name = _call_name(n)
            if name in ABS:
                absval = True
            if name in ("maximum", "fmax") and any(isinstance(x, ast.UnaryOp) and isinstance(x.op, ast.USub)
                                                   for x in n.args):
                absval = True
            if name in PICKS:
                pick = True
            if name in ("range", "arange") and len(n.args) == 3 and \
                    all(isinstance(x, ast.Constant) for x in n.args) and \
                    n.args[0].value == 3 and n.args[2].value == 3 and n.args[1].value in (12, 13):
                quarter = True
    return quarter and absval and pick


def detectors_in_source(src, filename="<src>"):
    """[(name, line)] of roll detectors in `src`: a def or lambda by name, by the retired signature, or
    carrying the retired algorithm - module-level code counted as one more scope ('<module>')."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    months, quarters = _month_names(tree), _quarter_names(tree)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = {a.arg for a in node.args.args + node.args.kwonlyargs}
            if NAME_RE.search(node.name) or {"ratio_th", "abs_th"} <= args or \
                    _has_algorithm(node, months, quarters):
                hits.append((node.name, node.lineno))
        elif isinstance(node, ast.Lambda) and _has_algorithm(node, months, quarters):
            hits.append(("<lambda>", node.lineno))
    top = ast.Module(body=[s for s in tree.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                                      ast.ClassDef))], type_ignores=[])
    if not any(n == "<lambda>" for n, _ in hits) and _has_algorithm(top, months, quarters):
        hits.append(("<module>", 1))
    return hits


def _docstring_ids(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            out.add(id(n.body[0].value))
    return out


def evasions_in_source(src, filename="<src>", strategy=False):
    """[(what, line)] of ways to reach a roll detector without defining one:
      * a detector name bound by assignment / lambda, imported from anywhere but augur_engine.rolls,
        used as an attribute (mod.roll_seam_check), or written in a string or subscript key outside a
        docstring (getattr(m, 'roll_' + 'seam_check') is folded first);
      * in a strategy file: any import of tools/, any string naming a tools/ module or file, and
        runpy / compile / types.FunctionType / globals() / sys.modules / exec / eval."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    docs = _docstring_ids(tree)
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod = (n.module or "")
            from_rolls = mod in ("augur_engine.rolls", "rolls") or (n.level and mod == "rolls")
            if strategy and mod.split(".")[0] in ("tools", "runpy"):
                hits.append(("imports from %s" % mod, n.lineno))
            for a in n.names:
                if not from_rolls and (NAME_RE.search(a.name) or NAME_RE.search(a.asname or "")):
                    hits.append(("imports %s from %s" % (a.name, mod or "."), n.lineno))
        elif isinstance(n, ast.Import):
            for a in n.names:
                if strategy and a.name.split(".")[0] in ("tools", "runpy"):
                    hits.append(("imports %s" % a.name, n.lineno))
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for tg in targets:
                for x in ast.walk(tg):
                    if isinstance(x, ast.Name) and NAME_RE.search(x.id):
                        hits.append(("binds %s by assignment" % x.id, n.lineno))
        elif isinstance(n, ast.Attribute):
            if NAME_RE.search(n.attr):
                hits.append(("uses .%s" % n.attr, n.lineno))
            if strategy and n.attr == "modules" and isinstance(n.value, ast.Name) and n.value.id == "sys":
                hits.append(("uses sys.modules", n.lineno))
            if strategy and n.attr == "FunctionType":
                hits.append(("uses types.FunctionType", n.lineno))
        elif isinstance(n, ast.Call):
            name = _call_name(n)
            if strategy and name in STRATEGY_BANNED_CALLS:
                hits.append(("calls %s" % name, n.lineno))
            if name in DYNAMIC:
                for a in n.args:
                    s = _fold(a)
                    if s is not None and (NAME_RE.search(s) or (strategy and TOOLS_MODULE_RE.search(s.strip()))):
                        hits.append(("%s(%r)" % (name, s[:40]), n.lineno))
        if isinstance(n, (ast.Constant, ast.BinOp, ast.JoinedStr)) and id(n) not in docs:
            s = _fold(n)
            if s is not None and len(s) < 200:
                if NAME_RE.fullmatch(s.strip()) or NAME_RE.search(s.strip()) and s.strip().isidentifier():
                    hits.append(("names %r in a string" % s[:40], getattr(n, "lineno", 0)))
                elif strategy and TOOLS_MODULE_RE.search(s.strip()):
                    hits.append(("names a tools/ module %r" % s[:40], getattr(n, "lineno", 0)))
    # one report per (what, line)
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


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


TTM_VARIANTS = {   # TTM's attack on the lint, 2026-10-08 (C:/EdgeLog/_anatomy_cache/restate_roll/ttm_verify)
    "A1 month % 3 via a local name": (
        "import numpy as np\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    g = np.abs(opens[1:] - closes[:-1])\n"
        "    out = []\n"
        "    for i, t in enumerate(day_ts[1:]):\n"
        "        mo = t.month\n"
        "        if mo % 3 == 0 and 14 <= t.day <= 21:\n"
        "            out.append(i)\n"
        "    s = max(out, key=lambda i: g[i]) if out else None\n"
        "    return {}\n", False),
    "A2 quarter set built by range()": (
        "import numpy as np\n"
        "QM = set(range(3, 13, 3))\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    g = np.abs(opens[1:] - closes[:-1])\n"
        "    c = [i for i, t in enumerate(day_ts[1:]) if t.month in QM]\n"
        "    s = int(np.argmax(g[c])) if c else None\n"
        "    return {}\n", False),
    "A3 abs rewritten as maximum(g, -g)": (
        "import numpy as np\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    d = opens[1:] - closes[:-1]\n"
        "    g = np.maximum(d, -d)\n"
        "    c = [i for i, t in enumerate(day_ts[1:]) if t.month in (3, 6, 9, 12)]\n"
        "    s = int(np.argmax(g[c])) if c else None\n"
        "    return {}\n", False),
    "A4 pick rewritten as nlargest": (
        "import numpy as np\nimport pandas as pd\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    g = pd.Series(np.abs(opens[1:] - closes[:-1]))\n"
        "    c = [i for i, t in enumerate(day_ts[1:]) if t.month in (3, 6, 9, 12)]\n"
        "    s = g.iloc[c].nlargest(1).index\n"
        "    return {}\n", False),
    "A5 quarter from .quarter": (
        "import numpy as np\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    g = np.abs(opens[1:] - closes[:-1])\n"
        "    q = np.array([t.quarter for t in day_ts])\n"
        "    s = int(np.argmax(g * (q[1:] == q[:-1])))\n"
        "    return {}\n", False),
    "A7 algorithm in a module-level lambda": (
        "import numpy as np\n"
        "pick = lambda ts, g: max((i for i, t in enumerate(ts) if t.month in (3, 6, 9, 12)), key=lambda i: abs(g[i]))\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    s = pick(day_ts[1:], opens[1:] - closes[:-1])\n"
        "    return {}\n", False),
    "E1 getattr with the name split in two": (
        "import augur_engine.data_quality as dq\n"
        "f = getattr(dq, 'roll_' + 'seam_check')\n", True),
    "E2 plain attribute call": (
        "import augur_engine.data_quality as dq\n"
        "def go(m):\n"
        "    return dq.roll_seam_check(m)\n", False),
    "E3 tools/ file loaded by path": (
        "import importlib.util as u\n"
        "sp = u.spec_from_file_location('x', 'C:/repo/' + 'tools/rocfrontier_scan.py')\n"
        "m = u.module_from_spec(sp)\nsp.loader.exec_module(m)\n", True),
    "E4 runpy.run_path": (
        "import runpy\n"
        "ns = runpy.run_path('tools/rocfrontier_scan.py')\n", True),
    "E5 sys.modules lookup": (
        "import sys\n"
        "def run_backtest(opens, highs, lows, closes, day_ts=None, **kw):\n"
        "    s = sys.modules['tools.rocfrontier_scan'].detect_roll_seams(opens, closes, day_ts)\n"
        "    return {}\n", True),
    "E6 compile + FunctionType": (
        "import types\n"
        "code = compile(open('x.txt').read(), 'x', 'exec')\n"
        "f = types.FunctionType(code.co_consts[0], {})\n", True),
    "E7 globals()[name] binding": (
        "import augur_engine.data_quality as dq\n"
        "globals()['detect_roll_seams'] = dq.roll_seam_check\n", True),
    "C1 control: detect_roll_seams defined": ("def detect_roll_seams(o, c, ts):\n    return []\n", False),
    "C2 control: from tools import (strategy)": ("from tools.rocfrontier_scan import detect_roll_seams as q\n", True),
}


@pytest.mark.parametrize("name", sorted(TTM_VARIANTS))
def test_the_lint_catches_ttm_evasions(name):
    """TTM review #56 point 6 and the 10-08 attack on the lint: renamed copies, the algorithm in
    other spellings / a lambda / module level, and every way of reaching a detector without defining
    one. (A6 - a plain gap-threshold rule with renamed knobs, no quarter, no pick - is the honest
    limit: it is indistinguishable from real gap logic; the runtime guard is the backstop.)"""
    src, strat = TTM_VARIANTS[name]
    assert detectors_in_source(src) or evasions_in_source(src, strategy=strat), name


def test_the_redirect_and_a_roll_table_path_are_not_evasions():
    ok = ("from augur_engine.rolls import seam_days as detect_roll_seams\n"
          "import os, importlib.util\n"
          "_T = os.path.join(os.path.dirname(__file__), 'tools', 'data', 'rolls_NQ.csv')\n"
          "def run_backtest(o, h, l, c, **kw):\n"
          "    s = detect_roll_seams(o, c, None)\n"
          "    return {}\n")
    assert evasions_in_source(ok, strategy=True) == [] and detectors_in_source(ok) == []


def test_roll_aware_files_adjust_from_the_table():
    """Every ROLL_AWARE entry (the guard's only exception) reads the roll table itself and never
    asks a seam detector, so its crossing trades carry no contract step."""
    from augur_engine import rolls as R
    for fn in sorted(R.ROLL_AWARE):
        src = _read(os.path.join("augur_strategies", fn))
        assert "rolls_%s.csv" in src or "rolls_" in src, fn
        assert "detect_roll_seams(" not in src.replace("import seam_days as detect_roll_seams", ""), fn

r"""WHICH TESTS COULD A SET OF CHANGED FILES POSSIBLY BREAK?

WHY THIS EXISTS (2026-10-04). The pre-push engine tier takes about 23 minutes. It is held across
the whole rebase-gate-push by the machine-wide push lock, so local lanes no longer overtake each
other - but the owner's CLOUD sessions push straight to main from another machine, where no local
lock can reach them. TRADING-LOG lost a full 25-minute gate to exactly that (its tl-ledgerlabel
run, overtaken mid-gate by 3e8097c0). After such a rejection the lane must rebase and gate again,
and re-running all 23 minutes to absorb somebody else's unrelated commit is the waste worth
removing.

THE RULE WE WERE ASKED FOR DOES NOT WORK, and this is the important part. The ask was: if the
incoming commits "touch nothing in the engine tier" - nothing under augur_engine/, api/ or tests/
- re-run only the fast tiers. But the engine tier READS far more than those three directories.
Measured on this repo:

    index.html    read by 5 test files
    docs/, *.md   read by 10+
    tools/data/   read by 8
    setups/       read by 2

So a commit touching "only" index.html or only a doc can still change what the suite sees, and
waving it through on a path test would be how a red main ships. Worse, the commit that prompted
the ask (3e8097c0) touched index.html AND tests/test_dupe_fields_parity.py - under the literal
rule it would not have narrowed at all.

WHAT THIS DOES INSTEAD. It narrows by what the tests actually READ, not by where a file lives:

  1. A changed test file is affected, trivially.
  2. A changed repo .py file is mapped to its module, and then to every module that imports it,
     TRANSITIVELY - a test that imports augur_engine/data.py is affected by a change to
     augur_engine/rolls.py, because data imports rolls. Missing that transitive step is the one
     way a selection like this goes quietly wrong.
  3. A changed non-.py file (index.html, a doc, a csv under tools/data) affects any test whose
     source mentions that path or its basename.

IT FAILS SAFE. `tests_for` returns None - meaning "cannot narrow, run everything" - whenever it
cannot be sure: a changed file that configures the run itself (conftest.py, pytest.ini,
requirements), a .py it cannot map to a module, a selection so large there is nothing to save, or
any exception at all. None is always the safe answer, and it is the default on every doubt.

IT IS ONLY EVER FOR RE-VALIDATION. The first gate on a branch always runs in full. This narrows
the SECOND one, when the only thing that changed since the full green run is somebody else's
commits. Nothing here decides that; see the pre-push hook, which does the deciding and verifies
the claim against a real git diff rather than trusting an environment variable.
"""
import ast
import os
import subprocess
import sys
import warnings

# Changing any of these changes how the whole suite runs, so no narrowing is defensible.
RUN_CONFIG = (
    "tests/conftest.py", "pytest.ini", "setup.cfg", "tox.ini", "pyproject.toml",
    "requirements.txt", "requirements-dev.txt", "conftest.py",
)

# Above this share of the suite there is no time to save and more chance the selection is wrong.
MAX_SHARE = 0.4

# The engine tier runs tests/ with these two IGNORED - each has a tier of its own (the
# strategy contract runs before it, the surrogate battery only when surrogate.py changes).
# A narrowed re-validation stands in for the ENGINE tier, so it has to be a SUBSET of what
# that tier would have run. Without this, an index.html change narrowed to a set that
# included the 4-minute surrogate battery - MORE work than the thing it was approximating.
NOT_IN_ENGINE_TIER = ("tests/test_strategy_contract.py", "tests/test_surrogate.py")


def _git(root, *args):
    p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else ""


def repo_py_files(root):
    return [p for p in _git(root, "ls-files", "*.py").splitlines() if p.strip()]


def test_files(root):
    return [p for p in _git(root, "ls-files", "tests/test_*.py").splitlines() if p.strip()]


def module_of(path):
    """'augur_engine/data.py' -> 'augur_engine.data'; a package __init__ -> the package."""
    p = path[:-3] if path.endswith(".py") else path
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _imported_names(src):
    """Every module name this source imports, as written. Syntax errors yield nothing."""
    out = set()
    try:
        # A repo file with a stray backslash in a string raises SyntaxWarning while being
        # parsed. That is the parsed file's business, not this tool's, and it clutters the
        # output of any suite that calls in here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(src)
    except Exception:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:          # relative imports stay inside a package
                out.add(node.module)
                for a in node.names:                    # `from augur_engine import data`
                    out.add(node.module + "." + a.name)
    return out


_GRAPH_CACHE = {}


def import_graph(root, tree=None):
    """{module: set of REPO modules it imports}, plus {module: path}.

    Cached per (root, tree): building it parses every .py in the repo, about 18 seconds here, and
    a caller that asks repeatedly about the SAME tree should pay for that once. The tree sha is
    part of the key so a different checkout can never be answered from a stale graph. Third-party names are
    dropped: only modules that exist in this repo can be affected by a change in it."""
    key = (os.path.abspath(root), tree or _git(root, "rev-parse", "HEAD^{tree}").strip())
    if key in _GRAPH_CACHE:
        return _GRAPH_CACHE[key]
    paths = repo_py_files(root)
    by_module = {}
    for p in paths:
        by_module[module_of(p)] = p
    # Tests do not import tools as a package - they put tools/ on sys.path and say
    # `import push_lock`, or load the file by path. So register the BARE STEM too, which is what
    # makes a changed tools/*.py reach its tests at all (without this, tools/wt.py selected
    # nothing, which is the same hole the hook's tools tier exists for). Only when the stem is
    # unambiguous across the repo: tools/data.py and augur_engine/data.py must never collapse
    # into one name.
    stems = {}
    for p in paths:
        stems.setdefault(os.path.basename(p)[:-3], []).append(p)
    for stem, owners in stems.items():
        if len(owners) == 1 and stem not in by_module:
            by_module[stem] = owners[0]
    imports = {}
    for p in paths:
        try:
            with open(os.path.join(root, p), encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except Exception:
            src = ""
        mine = set()
        for name in _imported_names(src):
            if name in by_module:
                mine.add(name)
            else:
                # `from augur_engine.data import x` names a module plus an attribute
                head = name.rsplit(".", 1)[0]
                if head in by_module:
                    mine.add(head)
        imports[module_of(p)] = mine
    _GRAPH_CACHE[key] = (imports, by_module)
    return imports, by_module


def importers_closure(changed_modules, imports):
    """Every module that reaches any changed module through imports, transitively.

    This is the step that makes the selection trustworthy. A test importing augur_engine.data is
    affected by a change to augur_engine.rolls because data imports rolls; a direct-importers-only
    answer would miss it and skip a test that genuinely covers the change.
    """
    importers = {}
    for mod, deps in imports.items():
        for d in deps:
            importers.setdefault(d, set()).add(mod)
    affected = set(changed_modules)
    frontier = list(changed_modules)
    while frontier:
        m = frontier.pop()
        for up in importers.get(m, ()):
            if up not in affected:
                affected.add(up)
                frontier.append(up)
    return affected


def tests_for(changed_paths, root):
    """The test files these changes could break, or None for "cannot narrow - run everything"."""
    try:
        changed = [p.strip().replace("\\", "/") for p in changed_paths if p.strip()]
        if not changed:
            return set()                      # nothing changed: nothing to re-run

        for p in changed:
            if p in RUN_CONFIG or os.path.basename(p) == "conftest.py":
                return None                   # changes how everything runs

        tests = test_files(root)
        if not tests:
            return None
        picked, changed_modules, non_py = set(), set(), []
        for p in changed:
            if p.startswith("tests/") and os.path.basename(p).startswith("test_"):
                picked.add(p)
            elif p.endswith(".py"):
                changed_modules.add(module_of(p))
            else:
                non_py.append(p)

        imports, by_module = import_graph(root)
        for m in changed_modules:
            if m not in by_module:
                # A .py this tree does not have: a file the incoming commit DELETED, or one
                # outside git's listing. Either way the graph cannot speak for it.
                return None

        if changed_modules:
            affected = importers_closure(changed_modules, imports)
            for t in tests:
                tm = module_of(t)
                if tm in affected or (imports.get(tm, set()) & affected):
                    picked.add(t)

        # Reached by NAME, not by import: a test that mentions index.html, a doc, a csv under
        # tools/data - or that loads a tool by path or asserts on its SOURCE TEXT, which several
        # do. Tests read all of those in this repo, which is exactly why a path-based rule would
        # be wrong. Changed .py files go through here as well as through the graph: belt and
        # braces, because a selection that misses a test is the only failure that matters.
        by_name = list(non_py)
        for p in changed:
            if p.endswith(".py") and not p.startswith("tests/"):
                by_name.append(p)
        if by_name:
            names = set()
            for p in by_name:
                names.add(p)
                names.add(os.path.basename(p))
                stem = os.path.basename(p)
                if stem.endswith(".py"):
                    names.add(stem[:-3])
            for t in tests:
                try:
                    with open(os.path.join(root, t), encoding="utf-8", errors="replace") as fh:
                        src = fh.read()
                except Exception:
                    return None
                if any(n in src for n in names):
                    picked.add(t)

        if len(picked) > MAX_SHARE * len(tests):
            return None                       # nothing worth saving, and more room to be wrong
        return picked
    except Exception:
        return None                           # every doubt resolves to "run everything"


def _main():
    """CLI for the pre-push hook: changed paths on stdin, the test files to run on stdout.

    Prints NOTHING when it cannot narrow. The hook treats empty output as "run the full tier",
    so every failure mode here - no paths, an unmappable file, too large a selection, a crash -
    comes out as the safe answer without the hook needing to know which happened.
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    paths = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not paths:
        return 0                       # nothing differs: say nothing, the hook runs everything
    picked = tests_for(paths, a.root)
    if picked is None:
        return 0
    picked = {t for t in picked if t.replace(chr(92), "/") not in NOT_IN_ENGINE_TIER}
    if not picked:                     # nothing the engine tier covers is affected
        return 0
    print(" ".join(os.path.join(a.root, t).replace(chr(92), "/") for t in sorted(picked)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

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

  Added 2026-10-08, when tools/hook_tests.py started using this on EVERY ship that has a pre-lock
  test stamp (not only on the rare retry after a cloud push), so every hole below now matters:

  4. RELATIVE imports are resolved. api/paper.py says `from .util import json_safe` and
     `from . import paper_exitday`; until 2026-10-08 those edges were dropped ("relative imports
     stay inside a package"), so a change to api/util.py did not reach a test that imports only
     api.paper. `importlib.import_module("X")` / `__import__("X")` with a literal name count as
     imports too.
  5. A changed file NAMED in a repo file's CODE - a string literal, not a comment or docstring
     (its path, or its basename with extension: "NOISE_1_0.py", "index.html",
     "trade_scores.json", matched as a whole path word) - makes that module affected, and so
     every test that imports it. Strategy variants load their parent by path, tools read data
     files by name; rule 3 only looked at the tests' own source. (Matching comments too put
     api/runner.py, and so 182 of 247 test files, behind every index.html change.)
  6. DIRECTORIES. A file whose code names a changed file's own directory (any but the five big
     generic ones, GENERIC_DIRS) is affected - it may build the file's path from that name. A
     file whose code LISTS a directory (glob / listdir / scandir / iterdir / ls-files) is
     affected by a change directly in it; one that lists recursively (os.walk, rglob, "**") by a
     change anywhere under it - the listed directory read off the call's own arguments, followed
     back through the names they use (code_facts). tests/test_master_write_guard.py globs
     tools/*.py, so a new tool is its input though no test names it. A listing whose directory
     the code does not name (os.listdir(HERE)) is assumed to list its own folder; the hook's
     always-run SMOKE set covers the tests that do that.

  Parsing 23 MB of Python takes ~45 s, so a caller that has checked its worktree is clean can
  pass cache_path: each file's imports and facts are kept on disk keyed by path + git blob sha,
  under a fingerprint of this file (import_graph).

IT FAILS SAFE. `tests_for` returns None - meaning "cannot narrow, run everything" - whenever it
cannot be sure: a changed file that configures the run itself (conftest.py, pytest.ini,
requirements), a .py it cannot map to a module, a selection so large there is nothing to save, or
any exception at all. None is always the safe answer, and it is the default on every doubt.
(tools/hook_tests.py passes max_share=None: a large selection is still smaller than the whole
tier it stands in for, and it is the SKIPPED tests, not the selected ones, that need evidence.)

IT IS ONLY EVER FOR RE-VALIDATION. A test is only ever skipped because it really PASSED on an
earlier tree and nothing it reads changed since. tools/hook_tests.py does the deciding: it keeps
a stamp of the test files that really ran green on each tree (its own pytest runs, nothing
claimed), diffs that tree against the one being pushed itself, and asks this module which tests
the difference could break.
"""
import ast
import hashlib
import json
import os
import re
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
_DEFAULT_SHARE = object()     # default for tests_for(max_share=): "MAX_SHARE as it is at call time"

# The engine tier runs tests/ with these two IGNORED - each has a tier of its own (the
# strategy contract runs before it, the surrogate battery only when surrogate.py changes).
# A narrowed re-validation stands in for the ENGINE tier, so it has to be a SUBSET of what
# that tier would have run. Without this, an index.html change narrowed to a set that
# included the 4-minute surrogate battery - MORE work than the thing it was approximating.
NOT_IN_ENGINE_TIER = ("tests/test_strategy_contract.py", "tests/test_surrogate.py")

# Rule 6. A directory named in a source is only evidence of reading a file in it when the name is
# specific: "tools", "docs", "tests", "api" and "augur_engine" are named by nearly every file (a
# sys.path line, an import root), so naming one of them says nothing on its own. They still count
# for a source that LISTS directories - that is the case where the name alone is the input.
GENERIC_DIRS = frozenset(("tools", "docs", "tests", "api", "augur_engine"))

# A source that enumerates a directory: its inputs include files nobody names.
_LISTS_A_DIR = re.compile(r"\b(?:glob|iglob|rglob|listdir|scandir|walk|iterdir)\s*\(|ls-files")


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


def _relative_base(module, is_pkg, level):
    """The package a relative import at `level` starts from, for a file whose module is `module`
    ('api.paper', level 1 -> 'api'); None when it climbs above the top or there is no package."""
    pkg = module.split(".") if is_pkg else module.split(".")[:-1]
    if not pkg or level - 1 >= len(pkg):
        return None
    return ".".join(pkg[:len(pkg) - (level - 1)])


def _literal_import(node):
    """'X' for importlib.import_module("X") / import_module("X") / __import__("X"), else None."""
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    if name not in ("import_module", "__import__") or not node.args:
        return None
    a = node.args[0]
    return a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None


def _parse(src):
    """The AST, or None for a file Python cannot parse."""
    try:
        # A repo file with a stray backslash in a string raises SyntaxWarning while being
        # parsed. That is the parsed file's business, not this tool's, and it clutters the
        # output of any suite that calls in here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(src)
    except Exception:
        return None


def _imported_names(src, module=None, is_pkg=False, tree=None):
    """Every module name this source imports, as written. Syntax errors yield nothing.

    With `module` (the importing file's own module name) relative imports are resolved against
    its package; without it they are skipped, since resolving one needs that context."""
    out = set()
    tree = tree if tree is not None else _parse(src)
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                              # `from . import x`, `from .util import y`
                base = _relative_base(module, is_pkg, node.level) if module else None
                if base is None:
                    continue
                head = base + "." + node.module if node.module else base
            elif node.module:
                head = node.module
            else:
                continue
            out.add(head)
            for a in node.names:                        # `from augur_engine import data`
                out.add(head + "." + a.name)
        elif isinstance(node, ast.Call):
            lit = _literal_import(node)
            if lit:
                out.add(lit)
    return out


_LIST_CALLS = frozenset(("glob", "iglob", "rglob", "listdir", "scandir", "walk", "iterdir"))


def _docstring_ids(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


_WILD = re.compile(r"[*?\[%{]")


def _listed_dirs(seq, recursive):
    """From the literals of one listing call, in source order, the directory names it lists.

    Each literal is split on / and \\ into components. A component with a wildcard or format
    character (* ? [ % {) is a pattern; one with a dot is a file name; the rest are directory
    names. The call lists the LAST directory name before the first pattern (os.path.join(ROOT,
    "tools", "data", "*.csv") lists data, not tools); a recursive call (os.walk, rglob, "**")
    lists everything under EVERY directory it names. Returns (flat, deep) name sets; both empty
    means the code does not say which directory it lists."""
    comps = []
    for lit in seq:
        comps.extend(c for c in re.split(r"[/\\]", lit) if c not in ("", ".", ".."))
    deep, last = set(), None
    for c in comps:
        if c == "ls-files":
            continue
        if _WILD.search(c):
            if "**" in c:
                recursive = True
            break
        if "." in c:
            continue
        last = c
        deep.add(c)
    if recursive:
        return set(), deep
    return ({last} if last else set()), set()


def code_facts(tree):
    """What a file's CODE (not its comments or docstrings) says about the files it reads:

      literals  every string literal in the code, each in quotes - where a path it opens is named
      flat      the directory names its listing calls (glob / listdir / scandir / iterdir, or a
                git ls-files command) enumerate - see _listed_dirs - following the names they use
                one or two steps back (STRAT_DIR = os.path.join(ROOT, "augur_strategies"))
      deep      the same for recursive listings (os.walk, rglob, "**"): everything under them
      blind     a listing call whose directory the code does not name (os.listdir(HERE))

    A mention in a comment or docstring is not a read; matching those put api/runner.py (and so
    most of the suite) behind every index.html change. None when there is no tree."""
    if tree is None:
        return None
    docs = _docstring_ids(tree)
    assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    assigns.setdefault(tgt.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assigns.setdefault(node.target.id, []).append(node.value)

    def seq(node, depth, out):
        """String literals under `node` in SOURCE order, names followed back `depth` steps."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                out.append(node.value)
            return out
        if isinstance(node, ast.Name):
            if depth < 2:
                for v in assigns.get(node.id, ()):
                    seq(v, depth + 1, out)
            return out
        for _field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, ast.AST):
                        seq(v, depth, out)
            elif isinstance(value, ast.AST):
                seq(value, depth, out)
        return out

    literals, flat, deep, blind = [], set(), set(), False
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docs):
            literals.append(node.value)
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) \
                else None
            git_ls = any(isinstance(m, ast.Constant) and m.value == "ls-files"
                         for a in node.args for m in ast.walk(a))
            if name in _LIST_CALLS or git_ls:
                lits = []
                if isinstance(f, ast.Attribute):
                    seq(f.value, 0, lits)          # Path(...).iterdir(): the receiver
                for a in node.args:
                    seq(a, 0, lits)
                fl, dp = _listed_dirs(lits, name in ("walk", "rglob"))
                flat |= fl
                deep |= dp
                if not fl and not dp:
                    blind = True
    q = lambda xs: "\n".join('"%s"' % x for x in xs)
    return {"literals": q(literals), "flat": frozenset(flat), "deep": frozenset(deep),
            "blind": blind}


_GRAPH_CACHE = {}
_SOURCES = {}
_FACTS = {}

# A parse cache for callers that pass none (import_graph). None: no cache. tests/
# test_affected_tests.py points it at a temp copy of the machine cache, so the selector's own
# tests do not re-parse 23 MB of Python for every case.
DEFAULT_CACHE_PATH = None


def _graph_key(root, tree=None):
    return (os.path.abspath(root), tree or _git(root, "rev-parse", "HEAD^{tree}").strip())


def sources(root, tree=None, cache_path=None):
    """{path: source text} of every repo .py file, as import_graph read it (same cache). A file
    answered from the disk cache has None here; read_source reads it on demand."""
    key = _graph_key(root, tree)
    import_graph(root, key[1], cache_path)
    return _SOURCES.get(key, {})


def facts(root, tree=None, cache_path=None):
    """{path: code_facts(...)} of every repo .py file (same cache as import_graph)."""
    key = _graph_key(root, tree)
    import_graph(root, key[1], cache_path)
    return _FACTS.get(key, {})


def read_source(root, path):
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _self_key():
    """Fingerprint of THIS file: a cache written by other selector code is never read."""
    try:
        with open(os.path.abspath(__file__), "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()[:16]
    except Exception:
        return None


def _blob_shas(root):
    """{path: git blob sha} of every tracked .py whose file on disk IS that blob: the index's sha,
    minus every path `git status` reports as differing (staged or not). A dirty file is parsed
    from disk and never cached, so the cache can only ever answer for exactly the bytes on disk."""
    out = {}
    for ln in _git(root, "ls-files", "-s", "--", "*.py").splitlines():
        meta, _, path = ln.partition("\t")
        bits = meta.split()
        if len(bits) >= 2 and path:
            out[path] = bits[1]
    st = subprocess.run(["git", "-C", root, "status", "--porcelain", "--untracked-files=no",
                         "--no-renames"], capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    if st.returncode != 0:
        return {}                          # cannot tell which files are dirty: cache nothing
    for ln in (st.stdout or "").splitlines():
        out.pop(ln[3:].strip().strip('"'), None)
    return out


def _load_cache(path, key):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    if not isinstance(data, dict) or data.get("key") != key or not key:
        return {}
    ent = data.get("entries")
    return ent if isinstance(ent, dict) else {}


def _save_cache(path, key, entries):
    """Atomic; never raises - an unwritten cache only costs the parse next time."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"key": key, "entries": entries}, fh)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def import_graph(root, tree=None, cache_path=None):
    """{module: set of REPO modules it imports}, plus {module: path}.

    Cached per (root, tree): building it parses every .py in the repo (23 MB of it - ~45 seconds
    with the code facts, 2026-10-08), and a caller that asks repeatedly about the SAME tree
    should pay for that once. The tree sha is part of the key so a different checkout can never
    be answered from a stale graph. Third-party names are dropped: only modules that exist in
    this repo can be affected by a change in it.

    cache_path (tools/hook_tests.py passes one, on a worktree it has checked is clean) keeps each
    file's imports and code facts on disk keyed by its path AND git blob sha, under a fingerprint
    of this very file - so a file is only ever answered from the cache when its bytes are the
    bytes that were parsed, by the code that parsed them. Two trees a few commits apart share
    nearly every blob, so the second build re-parses only what changed."""
    key = _graph_key(root, tree)
    if key in _GRAPH_CACHE:
        return _GRAPH_CACHE[key]
    paths = repo_py_files(root)
    cache_path = cache_path or DEFAULT_CACHE_PATH
    ckey = _self_key() if cache_path else None
    blobs = _blob_shas(root) if ckey else {}
    cache = _load_cache(cache_path, ckey) if ckey else {}
    fresh = {}
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
    srcs, fx = {}, {}
    for p in paths:
        ent = cache.get(p)
        if ent and blobs.get(p) and ent.get("blob") == blobs[p]:
            names = set(ent.get("imports") or ())
            f = ent.get("facts")
            fx[p] = None if f is None else {
                "literals": f["literals"], "flat": frozenset(f["flat"]),
                "deep": frozenset(f["deep"]), "blind": bool(f["blind"])}
            srcs[p] = None                     # read from disk only if a rule needs the text
        else:
            try:
                with open(os.path.join(root, p), encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
            except Exception:
                src = ""
            srcs[p] = src
            tree = _parse(src)
            fx[p] = code_facts(tree)
            names = _imported_names(src, module_of(p), p.endswith("/__init__.py"), tree)
        if ckey and blobs.get(p):
            f = fx[p]
            fresh[p] = {"blob": blobs[p], "imports": sorted(names), "facts": None if f is None else {
                "literals": f["literals"], "flat": sorted(f["flat"]), "deep": sorted(f["deep"]),
                "blind": f["blind"]}}
        mine = set()
        for name in names:
            if name in by_module:
                mine.add(name)
            else:
                # `from augur_engine.data import x` names a module plus an attribute
                head = name.rsplit(".", 1)[0]
                if head in by_module:
                    mine.add(head)
        imports[module_of(p)] = mine
    if ckey:
        _save_cache(cache_path, ckey, fresh)    # this tree's files only: the cache never grows
    _GRAPH_CACHE[key] = (imports, by_module)
    _SOURCES[key] = srcs
    _FACTS[key] = fx
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


def _dir_pattern(dirs):
    """Matches a source that names any of `dirs` as a path piece - quoted, or between slashes -
    rather than merely containing the letters ("api" inside "rapid"). None for no dirs."""
    if not dirs:
        return None
    alt = "|".join(re.escape(d) for d in sorted(dirs, key=len, reverse=True))
    return re.compile(r"[\"'/\\](?:%s)[\"'/\\]" % alt)


def _names_a_dir(src, dirs):
    pat = _dir_pattern(dirs)
    return bool(pat and pat.search(src))


def reached_by_name(changed, srcs, fx=None, raw=None, read=None):
    """Rules 5 and 6: the repo files whose source names a changed file, or names its directory in
    the way that makes the file one of its inputs. A changed file itself is never in the answer.

    `srcs` is {path: source}. `fx` is {path: code_facts} - a file with facts is judged by its
    CODE (string literals, the arguments of its listing calls); `raw` is the set of paths always
    judged by their whole text instead, comments included (the tests: each is only ever picked
    itself, so reading them generously costs one file, never a closure). A file without facts
    (it does not parse) is judged by its whole text too."""
    fx = fx or {}
    raw = raw or set()
    names, own_dirs, all_dirs, parents = set(), set(), set(), set()
    for p in changed:
        names.add(p)
        base = os.path.basename(p)
        if "." in base:                    # "data.py", "index.html" - never a bare stem here
            names.add(base)
        parts = p.split("/")[:-1]
        all_dirs.update(parts)
        if parts:
            parents.add(parts[-1])
            if parts[-1] not in GENERIC_DIRS:
                own_dirs.add(parts[-1])
    # The name as a whole word of a path: "data.py" in 'augur_engine/data.py' or "data.py", never
    # inside "metadata.py" - a substring match there would only cost re-runs, but on every ship.
    named = re.compile(r"(?<![A-Za-z0-9_.\-])(?:%s)(?![A-Za-z0-9_])"
                       % "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    own_pat, all_pat = _dir_pattern(own_dirs), _dir_pattern(all_dirs)
    # For CODE, a bare basename ("README.md", "config.json") only counts with evidence it is THIS
    # file: the file sits at the repo root, the reader sits in the same folder (a path built from
    # its own __file__), or the reader's code also names the file's folder. Without that, every
    # module that writes some README.md became a reader of tools/rocfrontier/README.md (85 test
    # files). A full path ("tools/rocfrontier/README.md") always counts.
    by_base = {}
    for p in changed:
        base = os.path.basename(p)
        if "." in base:
            parts = p.split("/")[:-1]
            by_base.setdefault(base, []).append((os.path.dirname(p), parts[-1] if parts else ""))
    word = r"(?<![A-Za-z0-9_.\-])(%s)(?![A-Za-z0-9_])"
    base_re = re.compile(word % "|".join(re.escape(b) for b in sorted(by_base, key=len,
                                                                       reverse=True))) \
        if by_base else None
    full = [p for p in changed if "/" in p]
    path_re = re.compile(word % "|".join(re.escape(x) for x in sorted(full, key=len,
                                                                      reverse=True))) \
        if full else None
    dir_pats = {}

    def code_names_it(q, text):
        if path_re is not None and path_re.search(text):
            return True
        if base_re is None:
            return False
        for b in set(base_re.findall(text)):
            for d, par in by_base.get(b, ()):
                if d == "" or os.path.dirname(q) == d:
                    return True
                if par:
                    pat = dir_pats.get(par)
                    if pat is None:
                        pat = dir_pats[par] = _dir_pattern({par})
                    if pat.search(text):
                        return True
        return False

    hit = set()
    for q, src in srcs.items():
        if q in changed:
            continue
        f = None if q in raw else fx.get(q)
        if f is None:                      # whole text: tests, and anything that does not parse
            if src is None:
                src = read(q) if read else ""
            if named.search(src):
                hit.add(q)
            elif own_pat is not None and own_pat.search(src):
                hit.add(q)
            elif all_pat is not None and _LISTS_A_DIR.search(src) and all_pat.search(src):
                hit.add(q)
            continue
        if code_names_it(q, f["literals"]):
            hit.add(q)
        elif own_pat is not None and own_pat.search(f["literals"]):
            hit.add(q)
        elif f["flat"] & parents or f["deep"] & all_dirs:
            hit.add(q)
        elif f["blind"]:
            # It lists a directory the code does not name. Assume its own: a change anywhere
            # under the folder this module sits in is its input.
            here = os.path.dirname(q)
            if any(p.startswith(here + "/") if here else "/" not in p for p in changed):
                hit.add(q)
    return hit


def tests_for(changed_paths, root, max_share=_DEFAULT_SHARE, cache_path=None):
    """The test files these changes could break, or None for "cannot narrow - run everything".

    max_share=None lifts the size cap (see the module docstring); the default keeps MAX_SHARE,
    read at call time so a caller that changes it is honoured."""
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

        imports, by_module = import_graph(root, cache_path=cache_path)
        for m in changed_modules:
            if m not in by_module:
                # A .py this tree does not have: a file the incoming commit DELETED, or one
                # outside git's listing. Either way the graph cannot speak for it.
                return None

        # Rules 5 and 6: a module that names a changed file or its directory reads it, so it is
        # as good as changed; a test that does is picked outright.
        tests_set = set(tests)
        for q in reached_by_name(changed, sources(root, cache_path=cache_path),
                                 facts(root, cache_path=cache_path),
                                 read=lambda q: read_source(root, q)):
            if q in tests_set:
                picked.add(q)
            else:
                changed_modules.add(module_of(q))

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

        share = MAX_SHARE if max_share is _DEFAULT_SHARE else max_share
        if share is not None and len(picked) > share * len(tests):
            return None                       # nothing worth saving, and more room to be wrong
        return picked
    except Exception:
        return None                           # every doubt resolves to "run everything"


def _main():
    """CLI: changed paths on stdin, the test files to run on stdout. (The pre-push hook used this
    until 2026-10-08; it now goes through tools/hook_tests.py, which imports tests_for directly.)

    Prints NOTHING when it cannot narrow - every failure mode here (no paths, an unmappable file,
    too large a selection, a crash) comes out as "run the full tier". --cache PATH keeps the
    per-blob parse cache there (a clean worktree only - see import_graph).
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()
    paths = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not paths:
        return 0                       # nothing differs: say nothing, the hook runs everything
    picked = tests_for(paths, a.root, cache_path=a.cache)
    if picked is None:
        return 0
    picked = {t for t in picked if t.replace(chr(92), "/") not in NOT_IN_ENGINE_TIER}
    if not picked:                     # nothing the engine tier covers is affected
        return 0
    print(" ".join(os.path.join(a.root, t).replace(chr(92), "/") for t in sorted(picked)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

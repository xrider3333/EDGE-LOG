"""Strategy plugin loading + listing (streamlit-free).

Mirrors optimizer._load_strategy_module: load a plugin BY FILE PATH with an
mtime-keyed cache (so an edited strategy is picked up, and distinct files stay
distinct). Listing reads STRATEGY_NAME without importing every module (cheap regex)
and the Library #s from augur_config.json's strat_nums.
"""
import os
import re
import json
import hashlib
import importlib.util

from .paths import STRAT_DIR, PINE_DIR, CONFIG

_CACHE = {}   # path -> (mtime, module)
_SHA_CACHE = {}   # path -> (mtime, sha256 hexdigest) -- separate dict, mirrors _CACHE's
                  # (path, mtime) memoization style but keyed to content-hash, not the
                  # loaded module (see strategy_file_sha).


def _resolve(name_or_path: str) -> str:
    """Accept a bare filename ('ORB_3_0.py' or 'ORB_3_0'), or an
    absolute path. Returns an absolute .py path under augur_strategies/."""
    if os.path.isabs(name_or_path) and os.path.exists(name_or_path):
        return name_or_path
    p = name_or_path if name_or_path.endswith(".py") else name_or_path + ".py"
    return os.path.join(STRAT_DIR, os.path.basename(p))


def load_strategy(name_or_path):
    """Load (or return cached) strategy module from a filename/path."""
    path = _resolve(name_or_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"strategy not found: {path}")
    mt = os.path.getmtime(path)
    hit = _CACHE.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    spec = importlib.util.spec_from_file_location(
        "augur_engine_strat_" + os.path.basename(path).replace(".", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "run_backtest"):
        raise AttributeError(f"{os.path.basename(path)} has no run_backtest()")
    _CACHE[path] = (mt, mod)
    return mod


def strategy_file_sha(path) -> str:
    """SHA-256 of the strategy file's raw BYTES (content, not mtime) -- the trial
    cache's key (docs/INCREMENTAL_BACKTEST_REUSE.md) needs a content hash so a
    same-mtime-different-content edit (e.g. a git checkout) still misses, and a
    same-content-different-mtime file (e.g. a touch with no edit) still hits.
    Memoized by (path, mtime) in a dict SEPARATE from `_CACHE` (the loaded-module
    cache) so this can be called for a strategy that hasn't been loaded/won't be
    loaded via `load_strategy` (e.g. a bare path string).

    Fail-open by design: raises (FileNotFoundError/OSError) if `path` can't be
    read, same as any other bare `open()` call -- callers building a cache key
    must treat that as "cannot source this field, do not cache," never guess or
    fall back to a stale hash."""
    mt = os.path.getmtime(path)
    hit = _SHA_CACHE.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    _SHA_CACHE[path] = (mt, digest)
    return digest


# WHAT A STRATEGY ACTUALLY DEPENDS ON (2026-09-28, TTM's report).
#
# The trial cache keyed on the SHA of the top-level strategy file alone. That is wrong for
# how this repo's strategy files are really written: a variant is a thin WRAPPER that loads
# its parent by file path at runtime -
#
#     _sp = _u.spec_from_file_location("TTMSQZ_3_0_ES30SSOF2",
#                                      os.path.join(_HERE, "TTMSQZ_3_0_ES30SSOF2.py"))
#     _base = _u.module_from_spec(_sp); _sp.loader.exec_module(_base)
#
# so a fix inside the PARENT left every wrapper's sha unchanged and the cache replayed the old
# results on a re-validation. Silently. TTM hit this and worked around it by editing each
# wrapper by hand; ORB, NOISE and ENGU-Q wrappers are built the same way.
#
# A second case of the same bug class, found while fixing it: a roll-guarded strategy reads
# `tools/data/rolls_<root>.csv` at run time. That table is NOT frozen - the September 2026 NQ
# offset moved from 295.00 to a measured 296.50 on 2026-09-28, and December's switch gets
# appended the evening it happens. A cached trial keyed only on code would replay results
# computed against the old offsets.
#
# So the key hashes the CLOSURE: the file, every other strategy file it reaches, and any data
# file under tools/data that those files name. Found two ways, because neither alone is
# enough: the loaded module's own globals (precise - it catches `_base` above) and string
# literals in the source (catches a parent loaded inside a function, where no global exists).
_CLOSURE_CACHE = {}
_DATA_SUFFIXES = (".csv", ".json")


def _literal_deps(path, strat_dir, data_dir):
    """Sibling strategy files and tools/data files named as string literals in `path`."""
    import ast as _ast
    out = set()
    try:
        tree = _ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return out
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Constant) or not isinstance(node.value, str):
            continue
        v = node.value
        if v.endswith(".py"):
            cand = os.path.join(strat_dir, os.path.basename(v))
            if os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(path):
                out.add(os.path.abspath(cand))
        elif v.endswith(_DATA_SUFFIXES) and "%s" not in v:
            cand = os.path.join(data_dir, os.path.basename(v))
            if os.path.exists(cand):
                out.add(os.path.abspath(cand))
        elif v.endswith(_DATA_SUFFIXES) and "%s" in v:
            # e.g. "rolls_%s.csv" - hash every file that pattern can name, so the key moves
            # when ANY of them changes. Cheap: there are two.
            import glob as _glob
            for hit in _glob.glob(os.path.join(data_dir, v.replace("%s", "*"))):
                out.add(os.path.abspath(hit))
    return out


def _module_deps(mod, strat_dir):
    """Strategy files reachable through the loaded module's own globals."""
    out = set()
    for v in list(getattr(mod, "__dict__", {}).values()):
        f = getattr(v, "__file__", None)
        if not f:
            continue
        f = os.path.abspath(f)
        if os.path.dirname(f) == os.path.abspath(strat_dir) and f.endswith(".py"):
            out.add(f)
    return out


def strategy_closure_sha(path, mod=None) -> str:
    """SHA-256 over the strategy file AND everything it depends on.

    This is what the trial cache keys on. Returns "" if the top-level file cannot be read -
    callers must treat that as "cannot source this field, do not cache", never guess.
    """
    path = os.path.abspath(path)
    strat_dir = os.path.dirname(path)
    data_dir = os.path.join(os.path.dirname(strat_dir), "tools", "data")

    seen, queue, files = set(), [path], []
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        files.append(cur)
        if cur.endswith(".py"):
            for dep in _literal_deps(cur, strat_dir, data_dir):
                if dep not in seen:
                    queue.append(dep)
    if mod is not None:
        for dep in _module_deps(mod, strat_dir):
            if dep not in seen:
                seen.add(dep)
                files.append(dep)
                for d2 in _literal_deps(dep, strat_dir, data_dir):
                    if d2 not in seen:
                        seen.add(d2)
                        files.append(d2)

    parts = []
    for f in sorted(files):
        try:
            parts.append("%s:%s" % (os.path.basename(f), strategy_file_sha(f)))
        except Exception:
            if f == path:
                return ""          # the file we were asked about is unreadable
    key = ";".join(parts)
    mt_key = (path, key)
    if mt_key in _CLOSURE_CACHE:
        return _CLOSURE_CACHE[mt_key]
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    _CLOSURE_CACHE.clear()          # tiny; keyed on content so it can never go stale
    _CLOSURE_CACHE[mt_key] = digest
    return digest


def strategy_closure_files(path, mod=None):
    """The files strategy_closure_sha() hashed - for reporting and tests."""
    path = os.path.abspath(path)
    strat_dir = os.path.dirname(path)
    data_dir = os.path.join(os.path.dirname(strat_dir), "tools", "data")
    seen, queue, files = set(), [path], []
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        files.append(cur)
        if cur.endswith(".py"):
            queue.extend(d for d in _literal_deps(cur, strat_dir, data_dir) if d not in seen)
    if mod is not None:
        for dep in _module_deps(mod, strat_dir):
            if dep not in seen:
                seen.add(dep)
                files.append(dep)
    return sorted(files)


def strategy_params(mod):
    """The strategy's DEFAULT_PARAMS dict."""
    return getattr(mod, "DEFAULT_PARAMS", {})


def _name_of(path) -> str:
    try:
        txt = open(path, encoding="utf-8").read()
        m = re.search(r'^STRATEGY_NAME\s*=\s*[\'"](.+?)[\'"]', txt, re.M)
        return m.group(1) if m else os.path.splitext(os.path.basename(path))[0]
    except Exception:
        return os.path.basename(path)


def _pine_path(py_file: str) -> str:
    """The conventional .pine sidecar path for a strategy .py filename."""
    base = os.path.splitext(os.path.basename(py_file))[0]
    return os.path.join(PINE_DIR, base + ".pine")


def _pine_via(pine_path: str):
    """Provenance of a .pine: reads the '// AUGUR-PINE: <src>' marker AUGUR writes when
    it generates/reviews one. Returns one of qwen|claude|claude-review|bundled|scaffold,
    or 'hand' if the .pine exists without a marker (hand-ported or pre-marker)."""
    try:
        txt = open(pine_path, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'(?mi)^//\s*AUGUR-PINE:\s*([a-z\-]+)', txt)
    return m.group(1).lower() if m else "hand"


def list_strategies():
    """List available strategy plugins, sorted by Library #. Each entry:
    {file, name, num, has_py, has_pine, added} where `added` is the .py mtime
    (epoch seconds) so the web Library can show 'date added' and sort by it."""
    nums = {}
    try:
        nums = json.load(open(CONFIG, encoding="utf-8")).get("strat_nums", {})
    except Exception:
        pass
    out = []
    for f in os.listdir(STRAT_DIR):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        py = os.path.join(STRAT_DIR, f)
        try:
            added = os.path.getmtime(py)
        except OSError:
            added = None
        pp = _pine_path(f)
        has_pine = os.path.exists(pp)
        out.append({"file": f, "name": _name_of(py), "num": nums.get(f),
                    "has_py": True, "has_pine": has_pine,
                    "pine_via": _pine_via(pp) if has_pine else None,
                    "added": added})
    out.sort(key=lambda d: (d["num"] is None, d["num"] or 0, d["file"]))
    return out

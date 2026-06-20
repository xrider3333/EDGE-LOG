"""Strategy plugin loading + listing (streamlit-free).

Mirrors optimizer._load_strategy_module: load a plugin BY FILE PATH with an
mtime-keyed cache (so an edited strategy is picked up, and distinct files stay
distinct). Listing reads STRATEGY_NAME without importing every module (cheap regex)
and the Library #s from augur_config.json's strat_nums.
"""
import os
import re
import json
import importlib.util

from .paths import STRAT_DIR, PINE_DIR, CONFIG

_CACHE = {}   # path -> (mtime, module)


def _resolve(name_or_path: str) -> str:
    """Accept a bare filename ('ORB_SIMPLE_1_0.py' or 'ORB_SIMPLE_1_0'), or an
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

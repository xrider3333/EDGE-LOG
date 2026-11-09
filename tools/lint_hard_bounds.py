"""HARD-BOUND LINT (owner GO 11-09, MANAGER #195).

Lists numeric params in strategy files that declare neither hard_min nor hard_max,
so auto-expand may widen them past the file's range (up to the 2x-width cap; zero
stays a floor when the declared min is >= 0). Report only - changes nothing.

    python tools/lint_hard_bounds.py augur_strategies/NQDIP_1_1.py [more files]
    python tools/lint_hard_bounds.py --all          # every augur_strategies/*.py
"""
import glob
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.auto import lint_hard_bounds  # noqa: E402


def lint_file(path):
    spec = importlib.util.spec_from_file_location("_lint_" + os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = getattr(mod, "DEFAULT_PARAMS", None)
    return lint_hard_bounds(dp) if isinstance(dp, dict) else None


def main(argv):
    files = sorted(glob.glob(os.path.join(ROOT, "augur_strategies", "*.py"))) if "--all" in argv \
        else [a for a in argv if a.endswith(".py")]
    if not files:
        print(__doc__)
        return 2
    n_open = 0
    for f in files:
        try:
            miss = lint_file(f)
        except Exception as e:  # a broken file is reported, not fatal
            print("%-40s  ERROR %s" % (os.path.basename(f), type(e).__name__))
            continue
        if miss is None:
            continue
        n_open += bool(miss)
        print("%-40s  %d unfenced: %s" % (os.path.basename(f), len(miss), ", ".join(miss)) if miss
              else "%-40s  all fenced" % os.path.basename(f))
    print("files with unfenced params: %d of %d" % (n_open, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

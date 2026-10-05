r"""Does this strategy read price LEVELS, and does that matter on a back-adjusted master?

    python tools/adj_level_check.py NOISE_1_8_CT304H ADJ_NQ_5m_RTH.csv
    python tools/adj_level_check.py --all ADJ_NQ_5m_RTH.csv      # every strategy, slow
    python tools/adj_level_check.py NOISE_1_8_CT304H ADJ_NQ_5m_RTH.csv --sessions 800

Run it from the SHARED checkout: a worktree has no augur_uploads (BACKTEST_SPEED.md rule 3).

The answer comes from running the strategy twice - once as the master stands, once with every
price moved by the instrument's real cumulative roll offset - and comparing the trades. See
augur_engine/adj_level.py for why this is a probe and not a source scan.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from augur_engine import adj_level                              # noqa: E402
from augur_engine.data import load_master_arrays                # noqa: E402
from augur_engine.strategies import load_strategy               # noqa: E402
from augur_engine.paths import STRAT_DIR                        # noqa: E402

EXIT_DEPENDENT = 2        # so a caller can gate on it; 0 = nothing to say, 1 = could not run


def check(name, master_file, sessions=None):
    if sessions:
        adj_level.PROBE_SESSIONS = int(sessions)
    arrays = load_master_arrays({"filename": master_file})
    mod = load_strategy(name if name.endswith(".py") else name + ".py")
    kind, detail = adj_level.verdict(mod, arrays, master_file)
    return kind, detail


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("strategy", nargs="?", help="strategy file name, with or without .py")
    ap.add_argument("master", help="master CSV in augur_uploads, e.g. ADJ_NQ_5m_RTH.csv")
    ap.add_argument("--all", action="store_true", help="every strategy against this master")
    ap.add_argument("--sessions", type=int, default=None,
                    help="probe window in sessions (default %d)" % adj_level.PROBE_SESSIONS)
    a = ap.parse_args(argv)

    if not adj_level.is_back_adjusted(a.master):
        print("%s is not back-adjusted, so there is nothing for this check to warn about."
              % a.master)
        return 0

    print("%s carries a cumulative back-adjustment of %.0f points."
          % (a.master, adj_level.adjustment_offset_pts(a.master)))

    names = []
    if a.all:
        names = sorted(f[:-3] for f in os.listdir(STRAT_DIR)
                       if f.endswith(".py") and not f.startswith("_"))
    elif a.strategy:
        names = [a.strategy]
    else:
        ap.error("give a strategy, or --all")

    worst = 0
    for name in names:
        try:
            kind, detail = check(name, a.master, a.sessions)
        except Exception as e:
            print("  %-34s could not run (%s: %s)" % (name, type(e).__name__, e))
            worst = max(worst, 1)
            continue
        label = {"dependent": "READS LEVELS", "invariant": "ok",
                 "unknown": "cannot judge"}[kind]
        print("  %-34s %-13s %s" % (name, label, detail))
        if kind == "dependent":
            worst = max(worst, EXIT_DEPENDENT)
    return worst


if __name__ == "__main__":
    sys.exit(main())

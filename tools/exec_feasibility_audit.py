#!/usr/bin/env python3
"""EXECUTION-FEASIBILITY AUDIT — the guard that would have caught the ORB leak.

The rule this enforces, in one sentence:

    for every simulated fill, every input the decision used must already exist
    at the moment of that fill.

The ORB family broke it for months: it filled at the opening-range edge the instant
price touched (intrabar) but gated the trade on the breakout bar's FINISHED volume.
Walk-forward, lockbox and the ES transfer all re-ran the same engine, so the leak
sailed through every statistical gate. Nothing in the repo would have flagged it.
This script is that missing check.

It is a STATIC scanner, not a proof. It catches the specific, mechanical mistakes
that have actually bitten this repo. It cannot catch a novel one — the human
question ("does every input exist at the moment of this fill?") still has to be
asked before crowning anything.

CHECKS
  1  HIDDEN-KNOB SWEEP (hard fail)
     A parameter that appears in PARAM_GRID_PRESETS but NOT in DEFAULT_PARAMS.
     Removing a knob from DEFAULT_PARAMS only hides it from the Builder UI —
     the optimizer builds its combos straight from the presets, so the knob is
     still being swept, invisibly. This is exactly how ORB_3_4 kept running the
     look-ahead volume filter it was written to replace.

  2  FABRICATED METRICS (hard fail)
     run_backtest hands back a hard-coded profit factor / drawdown with no PnL
     computed. The run looks finished and means nothing.

  3  STOP WITHOUT GAP-THROUGH REALISM (warn)
     The exit books the exact stop price with no check for a bar that OPENED
     past it. A resting stop fills at the open on a gap-through; booking the
     stop price is money that was never available.

  4  LOOK-AHEAD KNOB STILL IN A SWEEP (warn)
     A parameter this repo has already recorded as a look-ahead is still being
     swept somewhere.

USAGE
  python tools/exec_feasibility_audit.py                 # whole library
  python tools/exec_feasibility_audit.py FILE [FILE...]  # named files only
  python tools/exec_feasibility_audit.py --changed       # files changed vs origin/main

EXIT CODES
  0 = no hard failures (warnings may still be printed)
  1 = at least one hard failure
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(HERE, "augur_strategies")

# parameters this repo has already established are look-ahead. Add to this list the
# moment a new one is found - that is what makes the next leak cheap to catch.
KNOWN_LEAK_KNOBS = {
    "vol_filter": ("reads the ENTRY bar's finished volume while the fill is intrabar "
                   "(the 2026-08-10 ORB leak). The legal replacement is vpace_filter, "
                   "which only reads bars BEFORE the entry bar."),
}


def _load(path):
    """Import a strategy file without running anything, returning its module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_efa_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_hidden_knob_sweep(path, src):
    """CHECK 1 - a knob swept by the presets but absent from DEFAULT_PARAMS."""
    out = []
    try:
        mod = _load(path)
    except Exception as e:
        return [("warn", "could not import to inspect its knobs (%s: %s)"
                 % (type(e).__name__, str(e)[:60]))]
    dp = getattr(mod, "DEFAULT_PARAMS", None)
    presets = getattr(mod, "PARAM_GRID_PRESETS", None)
    if not isinstance(dp, dict) or not isinstance(presets, dict):
        return out
    # A strategy may legitimately expose a grid-only shorthand that maps back onto
    # real knobs (AOSTOCH's "k_band" -> k_low/k_high). It must SAY SO out loud, by
    # declaring GRID_ONLY_PARAMS at module level. Silence is the bug.
    allowed = set(getattr(mod, "GRID_ONLY_PARAMS", ()) or ())
    for label, grid in presets.items():
        if not isinstance(grid, dict):
            continue
        for k in grid:
            if k not in dp and k not in allowed:
                out.append(("fail",
                            "preset %r sweeps %r, which is NOT in DEFAULT_PARAMS. "
                            "Hiding a knob from the UI does not stop the optimizer "
                            "sweeping it - remove it from the preset too. If it is a "
                            "deliberate grid-only shorthand, declare it in "
                            "GRID_ONLY_PARAMS so the intent is on the record."
                            % (label.strip(), k)))
    return out


def check_fabricated_metrics(path, src):
    """CHECK 2 - hard-coded performance numbers instead of a simulation."""
    out = []
    if "is a STUB, not a backtest" in src:
        return out          # already quarantined: it raises before it can return

    for m in re.finditer(r"return\s*\{", src):
        block = src[m.start():m.start() + 800]
        end = block.find("}")
        if end > 0:
            block = block[:end]
        pf = re.search(r'"profit_factor"\s*:\s*([0-9.]+)\s*[,\n]', block)
        pnl = re.search(r'"total_pnl"\s*:\s*([0-9.]+)\s*[,\n]', block)
        if pf and pnl and float(pnl.group(1)) == 0.0 and float(pf.group(1)) != 0.0:
            line = src[:m.start()].count("\n") + 1
            out.append(("fail",
                        "line %d returns a hard-coded profit factor of %s with "
                        "total_pnl 0.0 - this is not a backtest, it is a stub "
                        "handing back invented numbers."
                        % (line, pf.group(1))))
    return out


STOP_TEST = re.compile(
    r"^\s*if\s+(?:s?l|lows?)\s*\[\s*\w+\s*\]\s*<=\s*([\w\[\]\"']+)|"
    r"^\s*if\s+(?:s?h|highs?)\s*\[\s*\w+\s*\]\s*>=\s*([\w\[\]\"']+)", re.M)
GAP_IDIOM = re.compile(r"(?:o|so|opens)\s*\[\s*\w+\s*\]\s*[<>]")


def check_gap_through(path, src):
    """CHECK 3 - a stop booked at its own price with no gap-through handling."""
    if "raise RuntimeError" in src[:src.find("def run_backtest") + 4000]:
        return []                                  # quarantined file, skip
    hits = STOP_TEST.findall(src)
    if not hits:
        return []
    names = {(a or b) for a, b in hits}
    stopish = {n for n in names if "stop" in n.lower() or "sl" in n.lower()}
    if not stopish:
        return []
    if GAP_IDIOM.search(src):
        return []                                  # file handles gaps somewhere
    return [("warn",
             "tests a stop (%s) but nowhere compares the bar OPEN against it. A bar "
             "that gapped straight through the stop is still being booked at the stop "
             "price, which is money that was never available."
             % ", ".join(sorted(stopish))[:60])]


def check_leak_knobs(path, src):
    """CHECK 4 - a knob already known to be look-ahead is still being swept."""
    out = []
    pi = src.find("PARAM_GRID_PRESETS")
    if pi < 0:
        return out
    presets_src = src[pi:]
    for knob, why in KNOWN_LEAK_KNOBS.items():
        if re.search(r'["\']%s["\']\s*:' % re.escape(knob), presets_src):
            out.append(("warn", "still sweeps %r in its presets - %s" % (knob, why)))
    return out


CHECKS = (check_hidden_knob_sweep, check_fabricated_metrics,
          check_gap_through, check_leak_knobs)


def audit(paths):
    fails = warns = 0
    for p in sorted(paths):
        name = os.path.basename(p)
        try:
            src = open(p, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print("  ?  %-24s could not read (%s)" % (name, e))
            continue
        msgs = []
        for fn in CHECKS:
            try:
                msgs += fn(p, src)
            except Exception as e:
                msgs.append(("warn", "%s crashed: %s" % (fn.__name__, e)))
        for level, msg in msgs:
            if level == "fail":
                fails += 1
                print("  FAIL %-22s %s" % (name, msg))
            else:
                warns += 1
                print("  warn %-22s %s" % (name, msg))
    return fails, warns


def changed_files():
    try:
        base = subprocess.run(["git", "merge-base", "HEAD", "origin/main"],
                              capture_output=True, text=True, cwd=HERE)
        ref = base.stdout.strip() or "origin/main"
        r = subprocess.run(["git", "diff", "--name-only", ref, "--"],
                           capture_output=True, text=True, cwd=HERE)
        out = []
        for line in r.stdout.splitlines():
            if line.startswith("augur_strategies/") and line.endswith(".py"):
                fp = os.path.join(HERE, line)
                if os.path.exists(fp):
                    out.append(fp)
        return out
    except Exception:
        return []


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if "--changed" in argv:
        paths = changed_files()
        if not paths:
            print("EXEC-FEASIBILITY: no strategy files changed - nothing to audit.")
            return 0
        print("EXEC-FEASIBILITY: auditing %d changed strategy file(s)" % len(paths))
    elif args:
        paths = [a if os.path.isabs(a) else os.path.join(os.getcwd(), a) for a in args]
    else:
        paths = [os.path.join(STRAT_DIR, f) for f in os.listdir(STRAT_DIR)
                 if f.endswith(".py") and not f.startswith("_")]
        print("EXEC-FEASIBILITY: auditing the whole library (%d files)" % len(paths))

    fails, warns = audit(paths)
    print("EXEC-FEASIBILITY: %s  (%d hard failure(s), %d warning(s))"
          % ("FAIL" if fails else "PASS", fails, warns))
    if fails:
        print("  A hard failure means a run of that file would produce a number you "
              "cannot trade. Fix it or remove the file from the library.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

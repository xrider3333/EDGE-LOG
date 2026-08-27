#!/usr/bin/env python3
"""
tools/index_extra_audit.py -- does dropping the `index` extra change any number?

WHY
    augur_engine.run_backtest decides which "extras" (volumes / day_id / index) to hand
    a strategy by INSPECTING its signature:

        if _idx is not None and (has_kw or "index" in sp):
            extras["index"] = _idx

    `has_kw` means "this strategy has a **kw catch-all". So today EVERY **kw strategy is
    handed the bar timestamps whether it wants them or not. That is what broke CI on
    2026-08-26: ORB_3_4_ER_1_0 wraps an older engine, forwarded its **kw straight
    through, and the older engine had never heard of `index`.

    The narrow fix (filter inside that wrapper) is already shipped. The DEEPER fix is to
    drop `has_kw` from the condition above, so only a strategy that explicitly declares
    `index` receives it -- which kills this whole bug class instead of catching it one
    file at a time. The only reason it has not been done is the open question: does any
    strategy silently RELY on timestamps it never declared? A source scan says no. A
    scan is not proof. This is the proof.

METHOD
    For every AFFECTED strategy -- has **kw, does not declare `index` -- run the real
    engine twice over the SAME real market data:

        A: arrays WITH    "index"   (today's behaviour)
        B: arrays WITHOUT "index"   (what the deeper fix would produce)

    The engine only adds the extra when arrays.get("index") is not None, so deleting
    that single key reproduces the proposed change exactly -- no engine edit, and no way
    for the audit and the real change to drift apart.

    Then compare every headline metric AND the full trade list, entry for entry. Any
    difference at all is a finding.

COVERAGE HONESTY
    A strategy that takes ZERO trades on the sample proves nothing: both runs are
    trivially equal. Those are counted separately as NOT EXERCISED rather than as
    passes, so the summary can never read cleaner than the evidence behind it.

AFTER THE FIX LANDS this audit is a tautology -- the engine no longer passes the extra
    to these strategies, so both arms are trivially equal. It is a PRE-change decision
    tool, kept in the tree as the reproducible evidence behind that decision and for the
    next time someone is tempted to widen the condition again.

Exit codes: 0 = nothing changed, 1 = something changed, 2 = inconclusive.

Usage:
  python tools/index_extra_audit.py
  python tools/index_extra_audit.py --tf 1m --date-from 2025-01-01
"""
import argparse
import importlib.util as ilu
import inspect
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine import list_strategies, load_strategy, run_backtest          # noqa: E402
from augur_engine.data import find_master, load_master_arrays                  # noqa: E402
from augur_engine.paths import STRAT_DIR                                       # noqa: E402
from augur_engine.strategies import strategy_params                            # noqa: E402

METRICS = ("total_pnl", "num_trades", "win_rate", "profit_factor",
           "max_drawdown", "avg_pnl", "wins", "losses")


def affected():
    """The strategies the deeper fix would actually change: a **kw catch-all and no
    declared `index`. One that DECLARES index keeps receiving it either way; one with no
    **kw never received it in the first place. Quarantined stubs are skipped -- they
    raise by design (same marker string the contract tests and the feasibility audit
    both key off, so quarantining a file takes effect here with no edit)."""
    out = []
    for s in list_strategies():
        f = s["file"]
        path = os.path.join(STRAT_DIR, f)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if "is a STUB, not a backtest" in fh.read():
                    continue
            spec = ilu.spec_from_file_location("aud_" + f[:-3], path)
            mod = ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "run_backtest", None)
            if fn is None:
                continue
            sp = inspect.signature(fn).parameters
            if not any(p.kind == p.VAR_KEYWORD for p in sp.values()):
                continue
            if "index" in sp:
                continue
            out.append(f)
        except Exception:
            pass
    return out


def defaults(mod):
    return {k: v.get("default") for k, v in strategy_params(mod).items()
            if isinstance(v, dict) and "default" in v}


def _eq(a, b, tol=1e-9):
    if a is None and b is None:
        return True
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        if math.isinf(a) or math.isinf(b):
            return a == b
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return a == b


def diff(ra, rb):
    """Every way the two runs disagree. Empty list means the same outcome, trade for
    trade -- not merely the same headline totals."""
    if ra is None and rb is None:
        return []
    if (ra is None) != (rb is None):
        return ["one run returned None, the other did not"]
    d = []
    for k in METRICS:
        va, vb = ra.get(k), rb.get(k)
        if not _eq(va, vb):
            d.append("%s: with-index=%r without=%r" % (k, va, vb))
    ta, tb = ra.get("trades") or [], rb.get("trades") or []
    if len(ta) != len(tb):
        d.append("trade count: %d vs %d" % (len(ta), len(tb)))
    else:
        for i, (x, y) in enumerate(zip(ta, tb)):
            if list(x) != list(y):
                d.append("trade #%d differs: %s vs %s" % (i, x, y))
                break
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--session", default="RTH")
    ap.add_argument("--instrument", default="NQ")
    ap.add_argument("--date-from", default="2024-06-01")
    ap.add_argument("--date-to", default="2026-06-01")
    a = ap.parse_args()

    master = find_master(a.instrument, a.tf, a.session)
    if not master:
        print("AUDIT: INCONCLUSIVE -- no %s %s %s master" % (a.instrument, a.tf, a.session))
        return 2
    arrays = load_master_arrays(master, a.date_from, a.date_to)
    if arrays.get("index") is None:
        print("AUDIT: INCONCLUSIVE -- loaded arrays carry no index; nothing to drop")
        return 2

    without = dict((k, v) for k, v in arrays.items() if k != "index")
    files = affected()
    print("AUDIT index-extra  |  %s  |  %s bars  %s..%s  |  %d affected strategies\n"
          % (master["name"], format(len(arrays["close"]), ","),
             a.date_from, a.date_to, len(files)))

    same, changed, empty, broke = [], [], [], []
    for f in files:
        try:
            mod = load_strategy(f)
            p = defaults(mod)
            ra = run_backtest(mod, arrays=arrays, params=dict(p), return_trades=True)
            rb = run_backtest(mod, arrays=without, params=dict(p), return_trades=True)
        except Exception as e:
            broke.append((f, "%s: %s" % (type(e).__name__, e)))
            print("  ERROR      %-34s %s: %s" % (f, type(e).__name__, str(e)[:64]))
            continue
        n = (ra or {}).get("num_trades") or 0
        d = diff(ra, rb)
        if d:
            changed.append((f, d))
            print("  CHANGED    %-34s %5d trades  <-- %s" % (f, n, d[0]))
        elif not n:
            empty.append(f)
            print("  no-trades  %-34s %5d trades  (proves nothing)" % (f, n))
        else:
            same.append(f)
            print("  same       %-34s %5d trades" % (f, n))

    print("\n" + "-" * 78)
    print("IDENTICAL (and actually traded): %d" % len(same))
    print("CHANGED:                         %d" % len(changed))
    print("NOT EXERCISED (0 trades):        %d%s"
          % (len(empty), ("  -> " + ", ".join(empty)) if empty else ""))
    print("ERRORED:                         %d" % len(broke))
    for f, e in broke:
        print("    %-34s %s" % (f, e[:80]))
    for f, d in changed:
        print("\n  %s" % f)
        for line in d[:6]:
            print("    - %s" % line)

    if changed:
        print("\nVERDICT: dropping the index extra CHANGES numbers. "
              "Do NOT land the deeper fix as-is.")
        return 1
    if not same:
        print("\nVERDICT: INCONCLUSIVE -- nothing actually traded, so nothing was proven.")
        return 2
    print("\nVERDICT: no strategy changed. %d traded and matched exactly%s."
          % (len(same),
             ("; %d took no trades and prove nothing" % len(empty)) if empty else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

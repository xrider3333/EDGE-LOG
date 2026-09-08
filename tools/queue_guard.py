"""queue_guard.py -- catch a config whose entire edge is ten trades or a single
months-long hold, BEFORE it gets queued.

WHY THIS EXISTS
----------------
`tools/continuous_lb_check.py` (2026-09-05) proved that a run's saved lockbox verdict can be
an artifact: `run_validate` grades the lockbox off an INDEPENDENT reload from the split date
(no prior history), while the config, run continuously, may hold its last position to the
end of the window and take ZERO real lockbox trades -- run #310 did exactly this (verdict
PASS on the doc, 0 continuous lockbox trades vs 91 invented by the reload, a 449-day hold).
In the same sweep two BOOK-job legs turned out to have top-10 trade shares of 101% and 104%
-- they LOSE money once their ten best trades are deleted, i.e. the entire "edge" is a
handful of outliers. Five queued jobs had to be cancelled by hand that day. This guard
generalises that one-off check into a function any queue script can call before it fires a
job at the runner, and hard-codes nothing about which strategy family it runs on.

WHAT IT DOES
------------
guard() runs ONE CONTINUOUS backtest over [date_from, date_to] (the same master arrays used
throughout, no reload) and slices the resulting trades by ENTRY time at `split`. It reports,
per stretch (selection = entries before split, lockbox = entries on/after split): n, profit
factor, win %, net $, max drawdown $, MAR, EV R and R per year (EV R = (1-win%)*(PF-1); R/YR
= EV R * trades-per-year of that stretch -- the same definitions continuous_lb_check.py and
ENGUQ.md section 1.0 use). It also computes: the selection-stretch net with the ten best
trades deleted (and that deletion's share of net -- the concentration read), the longest
single hold in calendar days, and a SECOND, independent RELOAD backtest from `split` to
`date_to` (mirroring what `run_validate` itself grades the lockbox on) so the two lockbox
trade counts can be compared side by side.

*** CONCENTRATION ALONE MUST NEVER FAIL THIS GUARD. *** ENGUQ.md section 1.0 measured the
DEPLOYED ENGU-Q leg (#226) at an 80% top-10 share and the crowned NOISE configurations at
22-42% -- both are working, shipped edges, not artifacts. What actually distinguishes an
artifact from a fat-tailed-but-real edge is whether the config still nets positive once its
ten best trades are gone, and whether it goes on trading in the held-out year at all. A future
session "fixing" this guard to fail on high concentration by itself would break it on the
program's own deployed strategy -- don't.

VERDICT (three hard reasons, checked in this priority order; concentration is a WARNING only)
  ARTIFACT (exit 1) -- continuous lockbox trades == 0 while the independent reload shows > 0.
      The #310 shape: the config never actually traded the lockbox, it just marked out a
      position that had been held open since before the split.
  ARTIFACT (exit 1) -- the selection-stretch net, with its ten best trades deleted, is <= 0.
      The 101%/104% shape from the 2026-09-05 BOOK legs: the whole "edge" is ten outliers;
      take them away and the config loses money.
  SUSPECT  (exit 2, warn not fail) -- top-10 share of selection net >= 90%, OR the reload and
      continuous lockbox trade counts differ by more than 50% of the continuous count. Neither
      one is disqualifying by itself (see the concentration note above) -- it means "look at
      this before trusting its validate verdict at face value", not "reject it".
  PASS (exit 0) -- none of the above.

USAGE
-----
  python tools/queue_guard.py --strategy ENGUQ_1M_ETH_ER_1_0.py --params '{"buf_atr":0.3,...}' \\
      --instrument NQ --timeframe 1m --session eth --source db_noadj_eth --cost 0.533 --mult 20 \\
      --from 2010-06-07 --to 2026-06-30 --split 2025-06-30

  python tools/queue_guard.py --run 310       # pulls best_params / instrument / timeframe /
                                               # data_source / cost_pts / multiplier /
                                               # validate.windows off users/<uid>/runs/310 --
                                               # ONE doc read (Firestore Spark quota is 50k
                                               # reads/day -- never stream a collection here).

THE {} TRAP -- FIXED 2026-09-08
--------------------------------
`--params '{}'` (or any dict missing keys) used to fall straight through to the strategy
plugin's own run_backtest() KEYWORD defaults -- which are frequently just the file's
INHERITED PARENT defaults, kept as a byte-for-byte parity anchor, and can be a totally
different configuration from the one the file's DEFAULT_PARAMS dict (what the web Builder
actually pre-fills, and what the owner has chosen as "the current default") describes. On
ENGUQ_1M_ETH_R2_1_0.py this meant `--params '{}'` silently re-ran the frozen #226 parity
anchor (2,838 trades / $432,954, breakeven_R 1.5 / stop_mult 1.0, inherited from the
signature) and PASSED it, while the runner's own BOOK job #323 for the SAME file with the
SAME empty leg params ran the file's real default (the "be2.0 sibling", breakeven_R 2.0 /
stop_mult 1.0, 1,949 trades / $613,125) -- a guard that never actually graded the
configuration it was asked about. Caught grading run #323's leg 2026-09-08.

THE FIX: `resolve_params()` below now mirrors what a real job carries -- a real job never
hits this gap because the web Builder always populates every param from
DEFAULT_PARAMS[k]['default'] before it ever writes a job doc (api/runner.py's sync_meta,
~line 972-982, ships that same 'default' key to the browser for exactly this reason);
augur_engine.engine.run_backtest / augur_engine.book.run_book both simply forward **params
straight to the plugin function with NO resolution step of their own, trusting the caller
to have already filled in every key. Every guard() call below now takes DEFAULT_PARAMS[k]
['default'] for any key the caller does not supply, then overlays the caller's params on
top -- so `{}` now means "the file's real defaults", exactly like a real queued job, not
"whatever the function signature happens to say". The resolved params (and which key came
from where) print at the top of every report so a mismatch with a run doc is visible
before trusting the verdict. A strategy with no DEFAULT_PARAMS at all has nothing to
resolve against and falls back to the pre-fix behaviour -- the report says so explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


# augur_engine.paths derives the master registry + uploads from the PACKAGE's own location,
# and a git worktree carries the code but not the (gitignored) optimizer_history.db or
# augur_uploads -- import the engine from whichever checkout actually holds the data, so this
# tool runs identically from a worktree and from the shared checkout (same trick as
# continuous_lb_check.py).
def _has_registry(root: pathlib.Path) -> bool:
    db = root / "optimizer_history.db"
    return db.exists() and db.stat().st_size > 0


_DATA_REPO = REPO if _has_registry(REPO) else pathlib.Path(
    r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, str(_DATA_REPO))
import numpy as np                                                    # noqa: E402
import pandas as pd                                                   # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.analytics import expectancy_r as _engine_expectancy_r  # noqa: E402
from augur_engine.strategies import load_strategy, strategy_params    # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
# data_source -> session, the same map tools/backfill_keel.py uses for run docs that
# carry no explicit `session` field.
_SOURCE_SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth", "tv": "rth"}


def resolve_params(strategy_file, params):
    """Resolve a strategy's EFFECTIVE params exactly the way a real queued job carries them:
    DEFAULT_PARAMS[k]['default'] for every key the caller does not supply, overlaid by
    whatever the caller DID supply. NEVER the plugin run_backtest() function's own keyword
    defaults -- see "THE {} TRAP" in the module docstring for why those can be a different
    configuration entirely.

    Returns (resolved, source, has_default_params):
      resolved            -- dict, the params to actually pass to run_backtest.
      source              -- dict[key -> 'default'|'caller'], which side each key came from.
      has_default_params  -- False if the strategy file exposes no DEFAULT_PARAMS at all, in
          which case `resolved` is just the caller's params, unchanged -- there is nothing
          to resolve against, so every key the caller omits still falls back to the
          plugin's own signature default, exactly as before this fix. Callers must surface
          this case rather than silently treating it as fully resolved.
    """
    caller = dict(params or {})
    mod = load_strategy(strategy_file)
    dp = strategy_params(mod) or {}
    if not dp:
        return caller, {k: "caller" for k in caller}, False
    resolved, source = {}, {}
    for k, meta in dp.items():
        if isinstance(meta, dict) and "default" in meta:
            resolved[k] = meta["default"]
            source[k] = "default"
    for k, v in caller.items():
        resolved[k] = v
        source[k] = "caller"
    return resolved, source, True


def format_resolved_report(strategy_file, resolved, source, has_default_params):
    """Report lines for guard()'s printout: one sorted-keys RESOLVED PARAMS line, then which
    keys came from DEFAULT_PARAMS vs the caller -- so a mismatch with a run doc's saved
    params is visible before trusting the verdict."""
    line = ", ".join("%s=%r" % (k, resolved[k]) for k in sorted(resolved))
    out = ["RESOLVED PARAMS: %s" % (line or "(none)")]
    if not has_default_params:
        out.append(
            "NOTE: %s has no DEFAULT_PARAMS -- nothing to resolve against; every key not "
            "supplied by the caller falls back to the plugin's own run_backtest() signature "
            "default (pre-fix behaviour)." % strategy_file)
        return out
    from_default = sorted(k for k, v in source.items() if v == "default")
    from_caller = sorted(k for k, v in source.items() if v == "caller")
    out.append("  from DEFAULT_PARAMS (%d): %s"
               % (len(from_default), ", ".join(from_default) or "(none)"))
    out.append("  from caller         (%d): %s"
               % (len(from_caller), ", ".join(from_caller) or "(none)"))
    return out


def split_from_lockbox(date_to, lockbox_months):
    """The exact lockbox-cutoff arithmetic augur_engine.validate.run_validate uses
    (lb_start = date_to - int(lockbox_months * 30.44) days), exposed so a queue script that
    already carries `date_to` + `lockbox_months` on a job (every validate/book job does) can
    compute the identical split date guard() should slice entries at, instead of re-deriving
    its own (and risking a policy that quietly disagrees with what the engine itself grades)."""
    hi = pd.Timestamp(date_to)
    lo = hi - pd.Timedelta(days=int(float(lockbox_months) * 30.44))
    return lo.date().isoformat()


# ── shared stats block (n / PF / win% / net$ / maxDD$ / MAR / EV R / R-YR) ──────────────
def _stats(pnls, years, mult):
    """Per-stretch stats from a list of point P&Ls. Same arithmetic as
    continuous_lb_check._stats and ENGUQ.md section 1.0's table."""
    n = len(pnls)
    if not n:
        return dict(n=0, pf=None, wr=None, net=0.0, dd=0.0, mar=None, evr=None, ryr=None)
    a = np.asarray(pnls, dtype=float)
    gp = float(a[a > 0].sum())
    gl = float(-a[a < 0].sum())
    pf = (gp / gl) if gl > 0 else None
    wr = 100.0 * float((a > 0).sum()) / n
    net = float(a.sum()) * mult
    cum = np.cumsum(a)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) * mult
    evr = (1 - wr / 100.0) * (pf - 1) if pf is not None else None
    ryr = (evr * n / years) if (evr is not None and years) else None
    mar = ((net / years) / dd) if (years and dd > 0) else None
    return dict(n=n, pf=pf, wr=wr, net=net, dd=dd, mar=mar, evr=evr, ryr=ryr)


def _fmt(d):
    def g(k, f, w):
        v = d.get(k)
        return (f % v).rjust(w) if v is not None else "-".rjust(w)
    return ("n=%-5d PF=%s wr=%s net=$%s DD=$%s MAR=%s EV R=%s R/YR=%s"
            % (d["n"], g("pf", "%.3f", 6), g("wr", "%.1f", 5), g("net", "%.0f", 9),
               g("dd", "%.0f", 8), g("mar", "%.2f", 6), g("evr", "%.3f", 6),
               g("ryr", "%.1f", 6)))


def guard(strategy_file, params, *, instrument, timeframe, session, source, cost_pts, mult,
         date_from, date_to, split, label=None):
    """Run ONE continuous backtest over [date_from, date_to], grade it, and return a verdict
    dict. See the module docstring for the three hard reasons and the exit-code mapping
    (also placed on the returned dict as result["exit_code"])."""
    label = label or strategy_file
    resolved_params, param_source, has_dp = resolve_params(strategy_file, params)

    print("=" * 118)
    print("%s   [%s]" % (label, strategy_file))
    for line in format_resolved_report(strategy_file, resolved_params, param_source, has_dp):
        print("  " + line)

    master = find_master(instrument, timeframe, session, source)
    if not master:
        raise SystemExit(f"no master for instrument={instrument} timeframe={timeframe} "
                         f"session={session} source={source}")
    arr = load_master_arrays(master, date_from=date_from, date_to=date_to)
    idx = pd.DatetimeIndex(arr["index"])

    r = run_backtest(strategy_file, arrays=arr, params=dict(resolved_params),
                     cost_pts=cost_pts, return_trades=True)
    trades = r.get("trades") or []          # (entry_i, exit_i, pnl_pts, side, entry_price)

    if not trades:
        print("  NO TRADES over the window -- nothing to grade")
        reasons = ["ARTIFACT: zero trades over the whole window -- there is no edge to queue."]
        print("  VERDICT: ARTIFACT -- " + reasons[0])
        return dict(label=label, strategy=strategy_file, params=params,
                   resolved_params=resolved_params, param_source=param_source,
                   has_default_params=has_dp, verdict="ARTIFACT",
                   reasons=reasons, exit_code=1, n_all=0)

    # The master's index is tz-aware ET (load_master_arrays factorizes day_id on the ET
    # calendar date); stamp every boundary into the SAME zone so a comparison never
    # silently compares naive to aware, or shifts a boundary by hours (same trick as
    # continuous_lb_check.py).
    tz = idx.tz

    def _ts(s):
        t = pd.Timestamp(s)
        return t.tz_localize(tz) if (tz is not None and t.tz is None) else t

    split_ts, from_ts, to_ts = _ts(split), _ts(date_from), _ts(date_to)

    rows = [(idx[int(t[0])], idx[min(int(t[1]), len(idx) - 1)], float(t[2])) for t in trades]
    ent = pd.DatetimeIndex([x[0] for x in rows])
    ext = pd.DatetimeIndex([x[1] for x in rows])
    pnl = [x[2] for x in rows]
    hold_days = [(b - a).days for a, b in zip(ent, ext)]

    sel_m = ent < split_ts
    lb_m = ~sel_m
    y_sel = max((split_ts - (ent.min() if sel_m.any() else from_ts)).days, 1) / 365.25
    y_lb = max((to_ts - split_ts).days, 1) / 365.25
    y_all = max((to_ts - from_ts).days, 1) / 365.25

    S = _stats([p for p, k in zip(pnl, sel_m) if k], y_sel, mult)
    L = _stats([p for p, k in zip(pnl, lb_m) if k], y_lb, mult)
    A = _stats(pnl, y_all, mult)

    # ex-top-10 concentration, measured on the SELECTION stretch only (never chosen on the
    # lockbox) -- matches continuous_lb_check.py's convention including its <=10-trade no-op.
    sp = sorted([p for p, k in zip(pnl, sel_m) if k])
    S10 = _stats(sp[:-10] if len(sp) > 10 else sp, y_sel, mult)
    share = (1 - S10["net"] / S["net"]) * 100.0 if S["net"] else None

    # the RELOAD the engine actually grades the lockbox on -- an independent warm-start-free
    # run from `split` to `date_to`, same shape as run_validate's own lockbox call.
    rl = run_backtest(strategy_file, instrument=instrument, timeframe=timeframe,
                      session=session, source=source,
                      params=dict(resolved_params), cost_pts=cost_pts,
                      date_from=split, date_to=date_to)
    rl_n = int(rl.get("num_trades") or 0)
    longest = int(max(hold_days)) if hold_days else 0

    engine_evr = r.get("expectancy_r")
    cross_evr = _engine_expectancy_r(trades)

    print("  SELECTION  %s..%s  %s" % (date_from, split, _fmt(S)))
    print("  LOCKBOX    %s..%s  %s   <- CONTINUOUS, sliced by ENTRY time" % (split, date_to, _fmt(L)))
    print("  WHOLE RUN                         %s" % _fmt(A))
    print("  engine expectancy_r=%s (analytics.expectancy_r cross-check=%s)  |  longest hold %d days"
          % ("%.3f" % engine_evr if engine_evr is not None else "-",
             "%.3f" % cross_evr if cross_evr is not None else "-", longest))
    print("  ex-top-10 (selection): net=$%.0f  EV R=%s  R/YR=%s   -> top-10 share of net %s"
          % (S10["net"], ("%.3f" % S10["evr"]) if S10["evr"] is not None else "-",
             ("%.1f" % S10["ryr"]) if S10["ryr"] is not None else "-",
             ("%.0f%%" % share) if share is not None else "-"))
    print("  RELOAD lockbox n=%d vs CONTINUOUS lockbox n=%d" % (rl_n, L["n"]))

    # ── the verdict: three hard reasons, checked in priority order ──────────────────────
    reasons = []
    verdict = "PASS"

    if L["n"] == 0 and rl_n > 0:
        verdict = "ARTIFACT"
        reasons.append(
            "ARTIFACT: continuous run took 0 lockbox trades (its last entry is held open to "
            "the end of the window) while the independent reload invents %d -- the config "
            "never actually traded the lockbox, it only marks out a long-held position. "
            "This is run #310's shape." % rl_n)

    if S10["net"] is not None and S10["net"] <= 0:
        verdict = "ARTIFACT"
        reasons.append(
            "ARTIFACT: deleting the ten best selection-window trades turns net from $%.0f to "
            "$%.0f -- the entire edge is ten outlier trades; take them away and this configuration "
            "loses money. This is the 101%%/104%% top-10-share shape two queued BOOK legs showed "
            "on 2026-09-05." % (S["net"], S10["net"]))

    if verdict != "ARTIFACT":
        if share is not None and share >= 90:
            verdict = "SUSPECT"
            reasons.append(
                "SUSPECT (warn, not fail): top-10 share of selection net is %.0f%% (>=90%%). "
                "Concentration ALONE is not disqualifying -- the deployed ENGU-Q leg runs 80%% "
                "and NOISE crowns run 22-42%% -- but it did not also fail the ex-top-10-net "
                "check above, so look at the trade list before trusting a validate PASS at "
                "face value." % share)
        base = max(L["n"], 1)
        diverge_pct = abs(rl_n - L["n"]) / base * 100.0
        if diverge_pct > 50:
            verdict = "SUSPECT"
            reasons.append(
                "SUSPECT (warn, not fail): reload lockbox trades (%d) differ from the continuous, "
                "entry-sliced count (%d) by %.0f%% (>50%%) -- this family's own validate verdict "
                "is graded on an independent reload that does not match what the config would "
                "actually have traded continuously (BACKTESTING_STACK.md 2026-08-08/09-05)."
                % (rl_n, L["n"], diverge_pct))

    if not reasons:
        reasons.append(
            "PASS: continuous lockbox trades exist and are broadly in line with the reload, "
            "and the edge survives deleting its ten best selection-window trades.")

    exit_code = {"PASS": 0, "ARTIFACT": 1, "SUSPECT": 2}[verdict]
    print("  VERDICT: %s" % verdict)
    for line in reasons:
        print("    - " + line)

    return dict(label=label, strategy=strategy_file, params=params,
               resolved_params=resolved_params, param_source=param_source,
               has_default_params=has_dp, verdict=verdict,
               reasons=reasons, exit_code=exit_code, sel=S, lb=L, all=A, sel_ex10=S10,
               top10_share=share, reload_n=rl_n, continuous_lb_n=L["n"],
               longest_hold_days=longest, engine_expectancy_r=engine_evr,
               cross_expectancy_r=cross_evr, date_from=date_from, date_to=date_to,
               split=split)


# ── --run N: pull the leg off a Firestore run doc (ONE doc read, never a stream) ────────
def _guard_kwargs_from_run(run_id, cred_path):
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    db = firestore.client()
    d = (db.collection("users").document(UID).collection("runs")
        .document(str(run_id)).get().to_dict())
    if not d:
        raise SystemExit(f"run #{run_id}: no such doc under users/{UID}/runs")

    strategy = d.get("strategy")
    params = d.get("best_params") or (d.get("validate") or {}).get("champion") or {}
    instrument = d.get("instrument")
    timeframe = d.get("timeframe")
    source = d.get("data_source")
    session = _SOURCE_SESSION.get(source)
    if not session:
        s = str(source or "").lower()
        session = "eth" if "eth" in s else ("rth" if "rth" in s else None)
    cost_pts = float(d.get("cost_pts") or 0.0)
    mult = float(d.get("multiplier") or d.get("mult") or 1.0)

    windows = ((d.get("validate") or {}).get("windows") or {})
    opt = windows.get("optimize") or [None, None]
    lb = windows.get("lockbox") or [None, None]
    date_from = opt[0] or d.get("date_from")
    split = lb[0]
    date_to = lb[1] or d.get("date_to")

    missing = [k for k, v in dict(strategy=strategy, params=params, instrument=instrument,
                                  timeframe=timeframe, session=session, source=source,
                                  date_from=date_from, date_to=date_to, split=split).items()
              if not v]
    if missing:
        raise SystemExit(
            f"run #{run_id}: doc is missing {missing} -- got strategy={strategy!r} "
            f"instrument={instrument!r} timeframe={timeframe!r} session={session!r} "
            f"source={source!r} date_from={date_from!r} date_to={date_to!r} split={split!r} "
            f"(validate.windows={windows!r})")

    kw = dict(strategy_file=strategy, params=params, instrument=instrument,
             timeframe=timeframe, session=session, source=source, cost_pts=cost_pts,
             mult=mult, date_from=date_from, date_to=date_to, split=split,
             label=f"run #{run_id}")
    return kw, d


def _print_doc_count_check(result, run_id, doc):
    """--run only: print the guard's own trade count next to the run doc's, flagged
    COUNT MISMATCH when they differ by more than 5% -- but ONLY against a like-for-like
    figure. Three sources, in order of preference:

      1. a BOOK doc's `book.legs[]` entry for THIS strategy file -- a whole-window replay
         of exactly one leg (augur_engine/book.py, no split) -> vs guard WHOLE RUN n.
         This is the apples-to-apples check that would have caught the #323 mismatch.
      2. a validate doc's `gate_validate.ungated_full` (whole-window, continuous, sliced
         by entry time -- the engine's own re-run, see edgelog-validate-header-75-split)
         -> vs guard WHOLE RUN n; else `gate_validate.ungated_pre` -> vs guard SELECTION n.
      3. `best_trades` -- the Stage-A 75%-IS-SPLIT figure, a DIFFERENT window from any
         guard stretch, so it is printed for orientation only and NEVER flagged.
    """
    strategy_file = result.get("strategy")
    guard_all = (result.get("all") or {}).get("n")
    guard_sel = (result.get("sel") or {}).get("n")

    def _n(block):
        if not isinstance(block, dict):
            return None
        for k in ("trades", "n", "num_trades"):
            if block.get(k) is not None:
                try:
                    return int(block[k])
                except Exception:
                    return None
        return None

    legs = ((doc.get("book") or {}).get("legs")) or []
    leg = next((l for l in legs if l.get("strategy") == strategy_file), None)
    gv = doc.get("gate_validate") or {}
    if leg is not None and _n(leg) is not None:
        doc_n, doc_label, guard_n, guard_label = (
            _n(leg), "book leg `trades` (whole-window replay of this leg)",
            guard_all, "guard WHOLE RUN n")
    elif _n(gv.get("ungated_full")) is not None:
        doc_n, doc_label, guard_n, guard_label = (
            _n(gv.get("ungated_full")), "gate_validate.ungated_full trades (continuous, whole window)",
            guard_all, "guard WHOLE RUN n")
    elif _n(gv.get("ungated_pre")) is not None:
        doc_n, doc_label, guard_n, guard_label = (
            _n(gv.get("ungated_pre")), "gate_validate.ungated_pre trades (continuous, pre-lockbox)",
            guard_sel, "guard SELECTION n")
    else:
        bt = doc.get("best_trades")
        if bt is None:
            print("  run #%s: doc carries no comparable trade count (no book leg, no "
                  "gate_validate.ungated_*, no best_trades)." % run_id)
        else:
            print("  run #%s: best_trades = %s is the Stage-A 75%%-IS-split figure (a different "
                  "window from every guard stretch) -- shown for orientation, not compared; "
                  "guard SELECTION n = %s, WHOLE RUN n = %s." % (run_id, bt, guard_sel, guard_all))
        return
    if guard_n is None:
        print("  run #%s: guard produced no comparable count (NO TRADES?) -- skipping the "
              "count check against %s = %s." % (run_id, doc_label, doc_n))
        return
    base = max(int(doc_n), 1)
    diverge_pct = abs(int(guard_n) - int(doc_n)) / base * 100.0
    flag = "   *** COUNT MISMATCH ***" if diverge_pct > 5 else ""
    print("  run #%s: %s = %d   vs  %s = %d   (%.1f%% diff)%s"
          % (run_id, doc_label, doc_n, guard_label, guard_n, diverge_pct, flag))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=int, help="pull the leg off users/<uid>/runs/<N> instead "
                                            "of the explicit flags below (one doc read)")
    ap.add_argument("--strategy", help="strategy plugin filename, e.g. ENGUQ_1M_ETH_ER_1_0.py")
    ap.add_argument("--params", default="{}", help="JSON dict of the leg's params")
    ap.add_argument("--instrument")
    ap.add_argument("--timeframe")
    ap.add_argument("--session")
    ap.add_argument("--source")
    ap.add_argument("--cost", dest="cost_pts", type=float, default=None,
                    help="per-round-trip cost in POINTS")
    ap.add_argument("--mult", dest="mult", type=float, default=None)
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--split", help="ET calendar date the selection/lockbox split falls on")
    ap.add_argument("--label")
    ap.add_argument("--cred", default=str(REPO / "serviceAccount.json"),
                    help="Firebase service-account JSON (repo root, gitignored)")
    a = ap.parse_args()

    run_doc = None
    if a.run is not None:
        kw, run_doc = _guard_kwargs_from_run(a.run, a.cred)
    else:
        required = dict(strategy=a.strategy, instrument=a.instrument, timeframe=a.timeframe,
                        session=a.session, source=a.source, date_from=a.date_from,
                        date_to=a.date_to, split=a.split)
        missing = [k for k, v in required.items() if not v]
        if missing:
            ap.error("missing required flag(s): --" + ", --".join(missing)
                     + " (or use --run N to pull them from Firestore)")
        kw = dict(strategy_file=a.strategy, params=json.loads(a.params),
                 instrument=a.instrument, timeframe=a.timeframe, session=a.session,
                 source=a.source, cost_pts=(a.cost_pts if a.cost_pts is not None else 0.0),
                 mult=(a.mult if a.mult is not None else 1.0), date_from=a.date_from,
                 date_to=a.date_to, split=a.split, label=a.label)

    result = guard(**kw)
    if run_doc is not None:
        _print_doc_count_check(result, a.run, run_doc)
    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()

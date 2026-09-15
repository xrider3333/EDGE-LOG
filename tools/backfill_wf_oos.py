"""Backfill the walk-forward out-of-sample block (validate.wf_oos) onto existing validated
runs (ENGINE_BRIEF.md STAGE 2, owner-approved 2026-09-15).

WHY: before this, no saved run carried a walk-forward Sharpe, Sortino or drawdown -- every
fold's real per-trade OOS pnls existed only transiently inside auto.py's `_wf_fold_row` and
were discarded before the doc was saved (analytics.wf_oos_block, validate.py). Every NEW
Auto-Validate now saves this block; this tool gets it onto runs validated BEFORE that shipped
by re-running each fold's out-of-sample slice with that fold's OWN saved champion params and
checking the replay against the figures the app already shows for that fold.

NOTHING here is written on trust:
  * the fold-bound reconstruction is scheme-agnostic (rolling AND anchored): te_s(f) =
    train_bars(fold 1) + sum(test_bars of folds before f), te_e(f) = te_s(f) + test_bars(f).
    train_bars(fold 1) is the SAME bar count in both windowing schemes (run_auto's `init`),
    so this reconstructs both from the doc alone -- unlike validate.py's own
    `_anchored_fold_bounds` (test_start == train_bars), which is only valid for ANCHORED,
    because that identity only holds when the training window starts at bar 0;
  * the reconstructed data window is PINNED to validate.windows.optimize (exactly what Stage B
    passed run_auto) and the loaded bar count must equal the fold rows' own train_bars(fold 1)
    + sum(test_bars) -- a data change since the run validated is refused (bars_mismatch), never
    silently absorbed;
  * every fold's params are read straight off that fold's OWN saved row (exactly as auto.py's
    `_wf_fold_row` passed them to `ev`) -- a strategy whose DEFAULT_PARAMS gained a knob since
    the run validated is refused (not reconstructible), never guessed at with a default;
  * every fold must independently reproduce the saved oos_trades/oos_pnl/oos_pf/oos_wins
    (tolerances below) -- ONE fold failing to match skips the WHOLE run; a block half-built
    from real trades and half from a mismatch would disagree with numbers the app already
    shows elsewhere for the same fold;
  * the block itself is built by the SAME `analytics.wf_oos_block` helper engine validates
    live with (its OWN reconciliation guard runs again on top), so the arithmetic can never
    drift from a live Auto-Validate's;
  * the write is refused when the runner's own size estimate of the finished doc is over its
    budget, and it carries a last-update-time precondition, so a doc that changed after it was
    read (a re-validate, a race with another backfill) is never overwritten.

Usage:
  python tools/backfill_wf_oos.py 335                 dry run (default): replay, verify, report
  python tools/backfill_wf_oos.py 335 382 325 --write  write the verified blocks
  python tools/backfill_wf_oos.py 335 --force          rebuild a run that already has one
  python tools/backfill_wf_oos.py --list [--limit 50]  runs with walk-forward fold rows

Exit code: 0 when every run was written, dry-run or already covered; 1 when any run was
refused (mismatch, too big, changed, conflict, cannot replay) or failed.

Run it from the SHARED checkout: the master registry (optimizer_history.db) and
serviceAccount.json live there, not in worktrees. Check `python tools/queue_truth.py` first
and keep to ONE process if jobs are running -- a replay runs a real backtest per fold, and a
busy box makes every job (including the owner's) slower. Firestore reads: one per run in a
dry run (two when writing, for the pre-write precondition check); --list is one field-masked
read per saved run (per listed run with --limit, newest run numbers first).

A DRY RUN WRITES NOTHING TO FIRESTORE -- not even the research beacon's queue-bar marker
(tools/research_beacon.py writes a job record), which is only opened with --write. A long dry
run is therefore visible only in this terminal's own per-fold log, not on the app's top bar.

Each fold's replay-vs-saved comparison travels inside the written block
(validate.wf_oos.backfill.matches: replayed trades/net/pf/wins, the doc's saved figures, and
d_trades/d_net/d_pf), so a later reader can see how close each fold came, not only that it
cleared the tolerances. A fold with no losing OOS trade has engine PF inf, which the runner's
json_safe saved as null: a saved null oos_pf matches a replayed inf (trades, wins and net must
still match).
"""
import argparse
import copy
import datetime
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.analytics import wf_oos_block, bar_date_bounds  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth"}      # as the other backfill tools
TOOL_VERSION = "tools/backfill_wf_oos.py v1"
# statuses that are not a refusal: main() exits 0 only when every run ended in one of these
OK_STATUSES = ("written", "dry", "covered")

# fold-match tolerances (ENGINE_BRIEF STAGE2 item 6)
NET_ABS_TOL = 0.05        # points
NET_REL_TOL = 1e-4        # x |saved oos_pnl|
PF_TOL = 0.002


class ReplaySkip(Exception):
    """The run cannot be replayed faithfully here (no master, params not reconstructible,
    the data window no longer matches...)."""


def _make_beacon(label, total=0):
    """Indirection over `research_beacon.beacon` so tests can stub the queue-bar marker
    without a real Firestore write -- the same way `one()` accepts `rebuild=` injection.
    research_beacon.Beacon opens its OWN Firestore client (hardcoded credential path,
    independent of this tool's `_db()`/`db`), so monkeypatching `B._db` alone does not
    stop it; tests monkeypatch `B._make_beacon` instead."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from research_beacon import beacon
    return beacon(label, total=total)


class _NoBeacon:
    """What a DRY run gets instead of `_make_beacon`: the same `with ... as b: b.step(i)`
    shape, and no Firestore write (research_beacon's marker is one)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def step(self, i):
        pass


def _int_or_none(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)) and math.isfinite(x):
        return int(x)
    return None


def _pf_close(a, b, tol=PF_TOL):
    """abs(a - b) <= tol, with float('inf') only equal to itself (a finite PF a rounding
    tick off from an infinite one is still a real disagreement)."""
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= tol


def _pf_matches(replayed, saved, tol=PF_TOL):
    """A replayed PF against the doc's saved oos_pf. `saved` None means the runner's
    json_safe nulled a non-finite PF -- in practice the +inf of a fold with no losing
    trade -- so it matches a replayed +inf and nothing else (trades/wins/net are still
    checked separately, so a null never waves through a fold that disagrees there)."""
    if saved is None:
        return math.isinf(replayed) and replayed > 0
    return _pf_close(replayed, saved, tol)


def _pf_delta(replayed, saved):
    """replayed - saved for the provenance row, JSON-safe: 0.0 when both are the same
    infinite PF (a saved null reads as +inf, see _pf_matches), None when only one side
    is finite (there is no honest number for that gap)."""
    s = float("inf") if saved is None else float(saved)
    r = float(replayed)
    if math.isfinite(r) and math.isfinite(s):
        return r - s
    return 0.0 if r == s else None


def _finite_or_none(x, nd=None):
    """x (rounded to nd places when given) if it is a finite number, else None -- the same
    null a runner-saved doc would carry, so the provenance rows never hold an inf/NaN."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, nd) if nd is not None else f


# ── what to replay ───────────────────────────────────────────────────────────────────────
def fold_bounds_from_rows(rows):
    """Reconstruct each fold's out-of-sample bar bounds from the doc's OWN saved
    `top10_results` rows alone. -> (bounds, expect_n, None) or (None, None, reason).

    bounds: [{"fold": int, "te_s": int, "te_e": int, "test_bars": int, "row": the saved
    fold row}, ...] in fold order. expect_n: the bar count the reconstructed window must
    have (train_bars(fold 1) + sum(test_bars over all folds)) -- a data change since the
    run validated shows up as a mismatch against this, not a silently different window.

    THE FORMULA (MAP critic, scheme-agnostic): te_s(f) = train_bars(fold 1) +
    sum(test_bars of folds before f), te_e(f) = te_s(f) + test_bars(f). train_bars(fold 1)
    is `init` in BOTH walk-forward schemes (run_auto: rolling's train window is always
    exactly `init` bars long; anchored's fold-1 train window is bars [0, init) too -- the
    schemes only diverge from fold 2 on), so this single formula reconstructs ROLLING and
    ANCHORED bounds identically. Do NOT reach for validate.py's `_anchored_fold_bounds`
    (test_start == that fold's OWN train_bars) here -- that identity only holds when the
    training window starts at bar 0, which is true for anchored but false for every rolling
    fold after the first (its train window slides forward, so test_start = tr_end, not
    train_bars)."""
    if not isinstance(rows, list) or not rows:
        return None, None, "no top10_results fold rows on the doc"
    try:
        ordered = sorted(rows, key=lambda r: int(r["fold"]))
    except Exception:
        return None, None, "a top10_results row carries no fold number - not a walk-forward run"
    # run_auto (auto.py's fold loop, and wf_pool.py's parallel path) can drop a fold's row
    # entirely when zero of its n_trials training-window trials clear min_trades (`if row is
    # not None: records.append(row)`) -- a narrow but real gap, not just theoretical. The
    # cumulative-sum formula below silently shifts every later fold's te_s/te_e if a middle
    # fold is missing, so refuse plainly here rather than lean on bars_mismatch or a fold
    # replay mismatch to catch it indirectly downstream.
    fold_numbers = [int(r["fold"]) for r in ordered]
    expected = list(range(1, len(ordered) + 1))
    if fold_numbers != expected:
        return None, None, (f"top10_results fold numbers are {fold_numbers}, not the "
                            f"contiguous {expected} a {len(ordered)}-fold walk-forward needs "
                            "(a fold whose training window cleared no trials is dropped, not "
                            "saved, so a gap or a duplicate here means the bar-bound "
                            "reconstruction cannot be trusted)")
    try:
        train0 = int(ordered[0]["train_bars"])
    except Exception:
        return None, None, "fold 1 carries no train_bars - cannot anchor the fold-bound reconstruction"
    bounds = []
    cum_test = 0
    for row in ordered:
        f = int(row["fold"])
        try:
            test_bars = int(row["test_bars"])
        except Exception:
            return None, None, f"fold {f} carries no test_bars"
        if test_bars <= 0:
            return None, None, f"fold {f} has test_bars <= 0"
        for k in ("oos_pnl", "oos_trades", "oos_pf"):
            if k not in row:
                return None, None, f"fold {f} carries no {k} - cannot verify a match against it"
        te_s = train0 + cum_test
        te_e = te_s + test_bars
        cum_test += test_bars
        bounds.append({"fold": f, "te_s": te_s, "te_e": te_e, "test_bars": test_bars, "row": row})
    return bounds, train0 + cum_test, None


def fold_params(pkeys, rows):
    """Per-fold param dict exactly as auto.py's `_wf_fold_row` passed to `ev`: every key in
    `pkeys` (the strategy's CURRENT DEFAULT_PARAMS-declared knobs), read off that fold's own
    saved row -- the same `{k: champ.get(k) for k in pkeys}` the engine already saved.
    -> (list of param dicts in `rows` order, None) or (None, reason) when any row is missing
    a knob the strategy declares today (its DEFAULT_PARAMS changed since this run validated --
    refused, never filled in with a default the run never actually used)."""
    if not pkeys:
        return None, "the strategy exposes no tunable DEFAULT_PARAMS"
    out = []
    for row in rows:
        params = {k: row[k] for k in pkeys if k in row}
        if len(params) != len(pkeys):
            missing = sorted(set(pkeys) - set(params))
            return None, (f"fold {row.get('fold')} row is missing param(s) {missing} - not "
                          "reconstructible (the strategy's DEFAULT_PARAMS may have changed "
                          "since this run validated)")
        out.append(params)
    return out, None


def rebuild_plan(d):
    """Everything needed to replay a doc's walk-forward folds, taken from the doc itself.
    -> (plan, None) or (None, reason).

    The window is PINNED to validate.windows.optimize -- exactly what run_validate's Stage B
    passed to run_auto for the PRIMARY scheme (ENGINE_BRIEF D1/D8) -- so the causal features
    and every fold's champion search match what actually ran. A doc missing that window is
    refused rather than guessed (a floating end would change every fold's champion)."""
    if not isinstance(d, dict):
        return None, "no doc"
    v = d.get("validate") if isinstance(d.get("validate"), dict) else {}
    if v.get("wf_ran") is not True:
        return None, "validate.wf_ran is not True on this doc - walk-forward did not run"
    mode = str(v.get("wf_best_mode") or "").lower()
    if mode not in ("rolling", "anchored"):
        return None, f"no usable validate.wf_best_mode on the doc ({v.get('wf_best_mode')!r})"
    if v.get("evolved_file") or d.get("evolved_file"):
        return None, ("validated an AI-evolved copy of the strategy - the saved strategy file "
                      "is not the code that ran, so it cannot be replayed")
    top = d.get("top10_results")
    bounds, expect_n, reason = fold_bounds_from_rows(top if isinstance(top, list) else [])
    if reason:
        return None, reason
    for k in ("strategy", "instrument", "timeframe"):
        if not d.get(k):
            return None, f"no {k} on the doc"
    src = d.get("data_source")
    sess = SESSION.get(src)
    if not sess:
        return None, f"unknown data_source {src!r}"
    win = v.get("windows") if isinstance(v.get("windows"), dict) else {}
    opt = win.get("optimize") if isinstance(win.get("optimize"), list) else []
    if len(opt) < 2 or not opt[0] or not opt[1]:
        return None, ("no validate.windows.optimize window recorded on the doc - the walk-"
                      "forward data window cannot be pinned")
    try:
        cost_pts = float(d.get("cost_pts"))
    except (TypeError, ValueError):
        return None, "no cost_pts on the doc"
    plan = {"strategy": d["strategy"], "instrument": d["instrument"], "timeframe": d["timeframe"],
            "session": sess, "source": src, "cost_pts": cost_pts, "mode": mode,
            "date_from": str(opt[0]), "date_to": str(opt[1]),
            "expect_n": expect_n, "folds": bounds}
    return plan, None


# ── per-fold replay + match ──────────────────────────────────────────────────────────────
def build_fold_match(ev, index, fb, params, dp=4):
    """Re-run ONE fold's out-of-sample slice with its saved params and compare the replay to
    the doc's own saved oos_trades/oos_pnl/oos_pf/oos_wins for that fold (ENGINE_BRIEF STAGE2
    item 6). `ev` is a `make_slice_evaluator` closure (or a stand-in with the same
    `ev(a, b, params, keep_trades=True) -> metrics|None` contract) -- injected so this can be
    unit tested without a real strategy or market data.

    -> {"fold", "ok", "reason" (None when ok), "pnls" (replayed net trade pnls, in trade
    order), "oos_pnl"/"oos_trades"/"oos_wins"/"oos_pf" (the REPLAYED values -- what feeds
    wf_oos_block, not the saved ones), "saved" ({"trades", "net", "pf", "wins"} exactly as
    the doc holds them, None where the doc has null), "d_trades"/"d_net"/"d_pf" (replayed
    minus saved; d_pf None when either side is not a finite PF -- 0.0 when both are the
    same infinite PF), "from"/"to" (this fold's OOS calendar bounds)}."""
    row, te_s, te_e = fb["row"], fb["te_s"], fb["te_e"]
    fold = fb["fold"]
    n_s = int(row.get("oos_trades") or 0)
    net_s = float(row.get("oos_pnl") or 0.0)
    # A fold whose OOS trades were ALL winners has engine PF float('inf'); the runner's
    #   json_safe saves every non-finite float as null, so the doc's oos_pf is None for
    #   exactly that fold. Keep the None (do not coerce it to 0.0, which would refuse a
    #   perfect replay) and let _pf_matches read it as the infinite PF it was.
    pf_s = None if row.get("oos_pf") is None else float(row.get("oos_pf"))
    wins_s = _int_or_none(row.get("oos_wins"))
    saved = {"trades": n_s, "net": net_s, "pf": pf_s, "wins": wins_s}
    om = ev(te_s, te_e, params, keep_trades=True)
    if not om:
        return {"fold": fold, "ok": False,
                "reason": "the evaluator returned nothing for this fold's slice",
                "pnls": [], "oos_pnl": 0.0, "oos_trades": 0, "oos_wins": None, "oos_pf": 0.0,
                "saved": saved, "d_trades": -n_s, "d_net": -net_s, "d_pf": None,
                "from": None, "to": None}
    # `_apply_costs` (engine.py) already nets these trades of cost_pts when cost_pts > 0 --
    # read them straight, exactly like ENGINE_BRIEF D6 fixed `_wf_fold_row` to do.
    trades = list(om.get("trades") or [])
    pnls = [round(float(t[2]), dp) for t in trades]
    n_r = len(pnls)
    net_r = float(om.get("total_pnl", sum(pnls)) if om.get("total_pnl") is not None else sum(pnls))
    pf_r = float(om.get("profit_factor", 0.0) or 0.0)
    wins_r = _int_or_none(om.get("wins"))

    reasons = []
    if n_r != n_s:
        reasons.append(f"trades {n_r} vs saved {n_s}")
    if wins_s is not None and wins_r is not None and wins_r != wins_s:
        reasons.append(f"wins {wins_r} vs saved {wins_s}")
    net_tol = max(NET_ABS_TOL, NET_REL_TOL * abs(net_s))
    if abs(net_r - net_s) > net_tol:
        reasons.append(f"net {net_r:.3f} vs saved {net_s:.3f} (tol {net_tol:.3f})")
    if not _pf_matches(pf_r, pf_s):
        reasons.append(f"PF {pf_r:.4f} vs saved "
                       + ("null (an infinite PF, as json_safe saves it)" if pf_s is None
                          else f"{pf_s:.4f}"))

    d0, d1 = bar_date_bounds(index, te_s, te_e)
    return {"fold": fold, "ok": not reasons, "reason": ("; ".join(reasons) or None),
            "pnls": pnls, "oos_pnl": net_r, "oos_trades": n_r, "oos_wins": wins_r,
            "oos_pf": pf_r, "saved": saved, "d_trades": n_r - n_s, "d_net": net_r - net_s,
            "d_pf": _pf_delta(pf_r, pf_s), "from": d0, "to": d1}


def build_block(matches, mode, dp=1):
    """The saved `validate.wf_oos` shape, from every fold's replay -- ONLY when every fold
    matched (ENGINE_BRIEF STAGE2 item 6: "ALL folds must match, else skip the run"). Built by
    the SAME `analytics.wf_oos_block` helper a live validate uses, so its own reconciliation
    guard runs again here on top of the per-fold checks above. -> block dict or None."""
    if not matches or not all(m["ok"] for m in matches):
        return None
    folds = [{"fold": m["fold"], "pnls": m["pnls"], "oos_pnl": m["oos_pnl"],
             "oos_trades": m["oos_trades"], "oos_wins": m["oos_wins"], "oos_pf": m["oos_pf"],
             "from": m["from"], "to": m["to"]} for m in matches]
    return wf_oos_block(folds, mode=mode, dp=dp, src="backfill")


PROVENANCE_KEYS = ("f", "trades", "net", "pf", "wins", "saved", "d_trades", "d_net", "d_pf")


def provenance_row(m):
    """One `backfill.matches` entry (ENGINE_BRIEF STAGE 2 "per-fold match deltas"): what the
    replay produced, what the doc had saved for that fold, and the gap between them -- so
    anyone reading a backfilled block later can see HOW close each fold came, not just that
    it cleared the tolerances. Non-finite PFs are stored as null (as json_safe would), never
    as inf, so the entry is plain JSON. A `rebuild` that did not supply saved figures (only
    test doubles) gets nulls there rather than invented numbers."""
    saved = m.get("saved") if isinstance(m.get("saved"), dict) else {}
    return {"f": m["fold"], "trades": m["oos_trades"],
            "net": _finite_or_none(m["oos_pnl"], 4), "pf": _finite_or_none(m["oos_pf"], 4),
            "wins": m.get("oos_wins"),
            "saved": {"trades": saved.get("trades"), "net": _finite_or_none(saved.get("net"), 4),
                      "pf": _finite_or_none(saved.get("pf"), 4), "wins": saved.get("wins")},
            "d_trades": m.get("d_trades"), "d_net": _finite_or_none(m.get("d_net"), 6),
            "d_pf": _finite_or_none(m.get("d_pf"), 6)}


def bars_mismatch_reason(n, expect_n, folds):
    """The refusal text when the pinned window's bar count `n` is not the fold rows' own
    train_bars(fold 1) + sum(test_bars). Two different stories produce that, and the
    message must not tell the wrong one:

      * run_auto DROPS a fold's row when none of its training trials clears min_trades
        (`if row is not None: records.append(row)`). A dropped middle fold is already
        refused by fold_bounds_from_rows (non-contiguous numbers); dropped TRAILING folds
        leave 1..k contiguous and surface here instead, as the loaded window being LONGER
        than the saved rows account for -- by at least one fold's worth of test bars
        (every fold before the last is exactly `tsize` bars; the last one is tsize plus
        the remainder). The data may well be unchanged.
      * anything else (fewer bars, or a surplus smaller than a fold) points at the data or
        the window itself having changed since the run validated.

    `folds` = plan["folds"] (fold_bounds_from_rows output, in fold order)."""
    base = f"bars_mismatch: window has {n} bars, the fold rows expect {expect_n}"
    last_tb = int(folds[-1]["test_bars"]) if folds else 0
    surplus = int(n) - int(expect_n)
    if folds and last_tb > 0 and surplus >= last_tb:
        train0 = int(folds[0]["row"].get("train_bars") or 0)
        init_note = ("and train_bars(fold 1) = int(0.40 x the loaded bars) still holds, so the "
                     "window itself looks unchanged" if int(int(n) * 0.40) == train0 else
                     f"(note: train_bars(fold 1) {train0} != int(0.40 x {n}) = "
                     f"{int(int(n) * 0.40)}, so the window may ALSO have changed)")
        return (f"{base} - {surplus} surplus bars >= the last saved fold's test_bars "
                f"({last_tb}): the last fold(s) were likely dropped by run_auto (no training "
                f"trial cleared min_trades, so no row was saved) {init_note}; the saved rows "
                "cannot pin the dropped fold(s), so this run is not backfilled")
    return f"{base} (the data changed since this run validated)"


def rebuild_from_market_data(plan, log=print):
    """Load the strategy + the pinned data window and replay every fold. Not unit-tested
    directly (everything above is) -- see tests/test_backfill_wf_oos.py."""
    from augur_engine.strategies import load_strategy
    from augur_engine.auto import _auto_space_from_params, make_slice_evaluator
    from augur_engine.data import find_master, load_master_arrays
    mod = load_strategy(plan["strategy"])
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    pkeys = list(_auto_space_from_params(dp).keys())
    rows = [fb["row"] for fb in plan["folds"]]
    params_list, reason = fold_params(pkeys, rows)
    if reason:
        raise ReplaySkip(reason)
    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        raise ReplaySkip(f"no master for {plan['instrument']} {plan['timeframe']} {plan['session']} "
                         f"{plan['source']} (the master registry lives in the shared checkout)")
    arrays = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
    n = len(arrays["close"])
    if n != plan["expect_n"]:
        raise ReplaySkip(bars_mismatch_reason(n, plan["expect_n"], plan["folds"]))
    ev = make_slice_evaluator(mod, arrays, plan["cost_pts"])
    index = arrays.get("index")
    log(f"  loaded {n} bars {plan['date_from']}..{plan['date_to']}, {len(plan['folds'])} fold(s)")
    return [build_fold_match(ev, index, fb, params)
            for fb, params in zip(plan["folds"], params_list)]


# ── payload + Firestore plumbing (mirrors tools/backfill_lb_tails.py's discipline) ────────
def check_payload(payload):
    """Refuse (ValueError) anything but a well-formed wf_oos block at exactly
    'validate.wf_oos', carrying this tool's provenance."""
    if set(payload) != {"validate.wf_oos"}:
        raise ValueError(f"refusing to write {sorted(payload)}: a wf_oos backfill writes "
                         "only validate.wf_oos")
    block = payload["validate.wf_oos"]
    if not (isinstance(block, dict) and block.get("v") == 1 and block.get("src") == "backfill"):
        raise ValueError("refusing to write a malformed wf_oos block")
    for k in ("mode", "n_folds", "trades", "net", "equity", "folds"):
        if k not in block:
            raise ValueError(f"refusing to write a wf_oos block missing {k!r}")
    bf = block.get("backfill")
    if not (isinstance(bf, dict) and bf.get("tool") and bf.get("at")
            and isinstance(bf.get("matches"), list)):
        raise ValueError("refusing to write a wf_oos block without backfill provenance")
    for mrow in bf["matches"]:
        if not (isinstance(mrow, dict) and all(k in mrow for k in PROVENANCE_KEYS)):
            raise ValueError("refusing to write a wf_oos block whose backfill.matches rows do "
                             f"not all carry {list(PROVENANCE_KEYS)}")
    if len(bf["matches"]) != block.get("n_folds"):
        raise ValueError("refusing to write a wf_oos block whose backfill.matches does not "
                         "cover every fold")
    return True


def apply_update(doc, payload):
    """A deep copy of `doc` with Firestore update semantics applied (a dotted key sets that
    nested field). Used to size the finished doc before writing it."""
    out = copy.deepcopy(doc)
    for path, value in payload.items():
        parts = path.split(".")
        cur = out
        for p in parts[:-1]:
            nxt = cur.get(p)
            if nxt is None:
                nxt = cur[p] = {}
            if not isinstance(nxt, dict):
                raise ValueError(f"cannot set {path!r}: {p!r} is not a map on the doc")
            cur = nxt
        cur[parts[-1]] = copy.deepcopy(value)
    return out


def size_check(doc, size_fn=None, budget=None):
    """The runner's own Firestore size estimate against its own budget (api/runner.py
    _doc_size / DOC_SIZE_BUDGET), so a backfill can never push a doc past the limit the
    runner saves under. -> (fits, bytes, budget). An unmeasurable doc does not fit."""
    if size_fn is None or budget is None:
        from api.runner import _doc_size, DOC_SIZE_BUDGET
        size_fn = size_fn or _doc_size
        budget = DOC_SIZE_BUDGET if budget is None else budget
    n = int(size_fn(doc) or 0)
    return (0 < n <= int(budget)), n, int(budget)


def same_block(a, b):
    """Two reads of a value hold the same content. Compared as serialised text, not with ==,
    because two reads of a NaN stat are two NaN objects and NaN != NaN."""
    import json as _json
    try:
        return _json.dumps(a, sort_keys=True, default=str) == _json.dumps(b, sort_keys=True, default=str)
    except Exception:
        return False


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _run_ref(db, run_id):
    return db.collection("users").document(UID).collection("runs").document(str(run_id))


def _write_landed(ref, payload):
    """After a write raised: read the doc back and say whether THIS write's block is on it. A
    commit the server applied but whose reply was lost looks like a failure to the client."""
    try:
        s = ref.get()
        d = s.to_dict() if getattr(s, "exists", False) else None
        wf = ((d or {}).get("validate") or {}).get("wf_oos")
        return isinstance(wf, dict) and same_block(wf, payload.get("validate.wf_oos"))
    except Exception:
        return False


def one(db, run_id, write=False, force=False, *, rebuild=None, size_fn=None, budget=None,
        log=print, at=None):
    """Replay, verify and (write=True) backfill one run's validate.wf_oos. Returns a status
    word: nodoc / skip / covered / mismatch / toobig / dry / changed / conflict / written.
    covered = the doc already carries validate.wf_oos (pass --force to rebuild it); skip = the
    run cannot be replayed faithfully here, or a fold's replay disagreed with the saved
    figures badly enough that no block was even built (a reconciliation-guard refusal)."""
    ref = _run_ref(db, run_id)
    snap = ref.get()
    d = snap.to_dict() if getattr(snap, "exists", False) else None
    if not d:
        log(f"#{run_id}: no doc"); return "nodoc"
    v = d.get("validate") if isinstance(d.get("validate"), dict) else {}
    if not force and isinstance(v.get("wf_oos"), dict):
        log(f"#{run_id}: already carries validate.wf_oos (src={v['wf_oos'].get('src')!r}) - "
            "skip, pass --force to rebuild it")
        return "covered"
    plan, why = rebuild_plan(d)
    if plan is None:
        log(f"#{run_id}: {why} - skip"); return "skip"
    log(f"#{run_id} {plan['strategy']} {plan['instrument']} {plan['timeframe']} window "
        f"{plan['date_from']}..{plan['date_to']} (pinned) mode {plan['mode']} "
        f"{len(plan['folds'])} fold(s)")
    t0 = time.time()
    try:
        matches = (rebuild or rebuild_from_market_data)(plan, log=log)
    except ReplaySkip as e:
        log(f"#{run_id}: {e} - not written"); return "skip"
    log(f"  replayed in {time.time() - t0:.0f}s")
    for m in matches:
        tag = "OK" if m["ok"] else f"MISMATCH: {m['reason']}"
        _dpf = m.get("d_pf")
        log(f"  fold {m['fold']}: trades {m['oos_trades']} (d {m.get('d_trades', 0):+d}) "
            f"net {m['oos_pnl']:.2f} (d {m.get('d_net', 0.0):+.4f}) "
            f"pf {m['oos_pf']:.3f} (d {('n/a' if _dpf is None else format(_dpf, '+.4f'))}) "
            f"-- {tag}")
    if not all(m["ok"] for m in matches):
        log(f"#{run_id}: FOLD MISMATCH - not written"); return "mismatch"
    block = build_block(matches, plan["mode"])
    if block is None:
        log(f"#{run_id}: the reconciliation guard refused the block - not written"); return "mismatch"
    at = at or _now()
    block["backfill"] = {"tool": TOOL_VERSION, "at": at,
                         "matches": [provenance_row(m) for m in matches]}
    log(f"  block: net {block['net']} pts, {block['trades']} trades, "
        f"PF {block['profit_factor']}, win_rate {block['win_rate']}%, "
        f"max_drawdown {block['max_drawdown']}, sharpe {block['sharpe']}, "
        f"sortino {block['sortino']}, years {block['years']}")
    payload = {"validate.wf_oos": block}
    check_payload(payload)
    fits, nbytes, cap = size_check(apply_update(d, payload), size_fn, budget)
    now_bytes = size_check(d, size_fn, budget)[1]
    log(f"  doc size: {now_bytes / 1024:.0f} KB now, {nbytes / 1024:.0f} KB with wf_oos, "
        f"runner budget {cap / 1024:.0f} KB")
    if not fits:
        log(f"#{run_id}: REFUSED - the doc would be over the runner's size budget"); return "toobig"
    if not write:
        log(f"#{run_id}: dry run - not written (pass --write)"); return "dry"
    # The replay took real time. Read the doc again and write only if the fold rows this
    #   block was built from are exactly what they were, and nobody else backfilled it in the
    #   meantime; the precondition then covers the short remaining gap.
    snap2 = ref.get()
    d2 = snap2.to_dict() if getattr(snap2, "exists", False) else None
    v2 = (d2 or {}).get("validate") if isinstance((d2 or {}).get("validate"), dict) else {}
    if (not d2 or not same_block(d2.get("top10_results"), d.get("top10_results"))
            or (isinstance(v2.get("wf_oos"), dict) and not force)):
        log(f"#{run_id}: the doc changed during the replay - not written, run it again")
        return "changed"
    fits2, nbytes2, _ = size_check(apply_update(d2, payload), size_fn, budget)
    if not fits2:
        log(f"#{run_id}: REFUSED - the doc grew past the runner's size budget ({nbytes2 / 1024:.0f} KB)")
        return "toobig"
    # retry=None: the client would otherwise re-send a commit whose reply was lost with the
    #   SAME precondition, which now fails - and report a write that landed as a conflict.
    try:
        ref.update(payload, option=db.write_option(last_update_time=snap2.update_time), retry=None)
    except Exception as e:
        if _write_landed(ref, payload):
            log(f"#{run_id}: the write raised {type(e).__name__}, but the doc carries this "
                f"backfill's stamp ({at}) - the reply was lost, the write landed")
        elif type(e).__name__ in ("FailedPrecondition", "Aborted"):
            log(f"#{run_id}: the doc changed just before the write - not written, run it again")
            return "conflict"
        else:
            raise
    log(f"#{run_id}: WRITTEN validate.wf_oos ({block['trades']} trades, net {block['net']} pts, "
        f"PF {block['profit_factor']})")
    return "written"


LIST_FIELDS = ["id", "strategy", "instrument", "timeframe", "date_from", "date_to",
               "validate.wf_ran", "validate.wf_best_mode", "validate.wf_oos.v",
               "validate.wf_oos.src", "validate.wf_oos.trades", "validate.wf_oos.net",
               "top10_results"]


def list_row(run_id, d):
    """One --list line from a field-masked doc, or None when the run has no walk-forward
    fold rows at all (nothing this tool could ever act on)."""
    top = (d or {}).get("top10_results")
    if not isinstance(top, list) or not top or not isinstance(top[0], dict) or "fold" not in top[0]:
        return None
    v = d.get("validate") if isinstance(d.get("validate"), dict) else {}
    wf = v.get("wf_oos")
    if isinstance(wf, dict):
        cov = f"wf_oos v{wf.get('v')} src={wf.get('src')!r} {wf.get('trades')} trades net {wf.get('net')}"
    elif v.get("wf_ran"):
        cov = "no wf_oos yet - a dry run would attempt this"
    else:
        cov = "validate.wf_ran is False - nothing to backfill"
    return (f"#{run_id} {d.get('strategy')} {d.get('instrument')} {d.get('timeframe')} "
            f"{d.get('date_from')}..{d.get('date_to')} | mode {v.get('wf_best_mode')} | "
            f"{len(top)} fold(s) | {cov}")


def list_runs(db, log=print, limit=None):
    """--list. Without --limit every run doc is streamed (field-masked) and sorted here.

    With --limit the query is ORDERED BY `id` DESCENDING BEFORE it is limited, so the cap
    keeps the NEWEST runs -- an unordered .limit(n) returns the first n docs in document-id
    order, and Firestore compares doc ids as STRINGS ("99" > "400"), so it would silently
    list old runs and skip the recent ones a backfill is most likely wanted for. `id` is
    the field the runner's own run counter orders by (api/runner.py _next_run_id: the
    integer run number, written on every saved run doc; the local-history sync carries the
    SQLite INTEGER id). Firestore leaves a doc with NO `id` field out of an ordered query,
    so such a doc can only be reached unlimited or by naming its run number; a provisional
    id (an epoch second, flagged id_provisional until the runner renumbers it) sorts first.
    The string "DESCENDING" is Query.DESCENDING's value, kept literal so this module never
    imports google.cloud at import time."""
    runs = db.collection("users").document(UID).collection("runs")
    q = runs.select(LIST_FIELDS)
    if limit:
        q = q.order_by("id", direction="DESCENDING").limit(int(limit))
    rows = []
    for s in q.stream():
        line = list_row(s.id, s.to_dict() or {})
        if line:
            rows.append((int(s.id) if str(s.id).isdigit() else -1, line))
    for _, line in sorted(rows, reverse=True):
        log(line)
    log(f"{len(rows)} run(s) with walk-forward fold rows")


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    # the admin key is gitignored, so it lives in the shared checkout even when this runs from
    #   a worktree - look there too rather than dying on a missing file
    cred = next((p for p in (os.path.join(ROOT, "serviceAccount.json"),
                             os.path.expanduser(r"~\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"))
                 if os.path.isfile(p)), None)
    if not cred:
        raise SystemExit("serviceAccount.json not found (checked this checkout and the shared one)")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="backfill_wf_oos.py",
        description="Backfill the walk-forward out-of-sample block (validate.wf_oos) onto "
                    "validated runs. Dry run by default: re-runs each fold's out-of-sample "
                    "slice with that fold's saved champion params and writes the block ONLY "
                    "when every fold reproduces the saved figures.",
        epilog="Run from the shared checkout (master registry + serviceAccount.json live "
               "there). Check `python tools/queue_truth.py` first and keep to ONE process if "
               "jobs are running - a replay runs a real backtest per fold. A dry run writes "
               "nothing to Firestore, so it opens no research beacon (no top-bar dial).")
    ap.add_argument("runs", nargs="*", type=int, help="run numbers, e.g. 335")
    ap.add_argument("--write", action="store_true",
                    help="write the verified block and show the replay on the app's top bar "
                         "via the research beacon (default: dry run - nothing written to "
                         "Firestore, beacon included)")
    ap.add_argument("--force", action="store_true",
                    help="rebuild a run that already carries validate.wf_oos")
    ap.add_argument("--list", action="store_true",
                    help="list runs with walk-forward fold rows and whether they carry a "
                         "wf_oos block (field-masked; one read per saved run)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of runs read by --list: the NEWEST by run number "
                         "(ordered by the run doc's `id` before limiting; a doc with no "
                         "`id` field is left out)")
    a = ap.parse_args(argv)
    if not a.runs and not a.list:
        ap.print_help()
        return 2
    os.chdir(ROOT)
    import augur_engine.data as _data
    if os.environ.get("EDGELOG_UPLOADS"):        # run from a worktree against the shared masters
        _data.UPLOADS = os.environ["EDGELOG_UPLOADS"]
    if os.environ.get("EDGELOG_DB_PATH"):        # ...and the shared master registry: a worktree's own
        import augur_engine.paths as _paths      #   optimizer_history.db is an empty untracked file
        _paths.DB_PATH = _data.DB_PATH = os.environ["EDGELOG_DB_PATH"]
    db = _db()
    if a.list:
        list_runs(db, limit=a.limit)
    rc = 0
    if a.runs:
        # The research beacon is itself a Firestore WRITE (its queue-bar marker doc). A dry run
        #   promises to write nothing, so it only gets a beacon when --write was given; a dry
        #   run's replay is still visible in this terminal's own per-fold log.
        with (_make_beacon(f"backfill_wf_oos {a.runs}", total=len(a.runs)) if a.write
              else _NoBeacon()) as b:
            for i, rid in enumerate(a.runs, 1):
                try:
                    status = one(db, rid, write=a.write, force=a.force)
                except Exception as e:
                    print(f"#{rid}: FAILED {type(e).__name__}: {e}")
                    rc = 1
                    b.step(i)
                    continue
                if status not in OK_STATUSES:
                    rc = 1            # a refusal: a batch script must not read it as success
                b.step(i)
    return rc


if __name__ == "__main__":
    sys.exit(main())

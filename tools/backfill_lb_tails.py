"""Backfill the 1A funnel's dense LOCKBOX TAILS onto existing run docs (2026-09-13).

WHY (owner, 2026-09-13): the lockbox on the 1A CONFIG FUNNEL "still shows as stretched".
Every ML line - gate candidates, tilts, hybrids, KEEL and the chosen gate - saves ONE
300-point stride sample of the whole run. On #384 that is 4,075 trades, so the held-out
year's 273 trades get about 20 of those points, and once the funnel gives the lockbox a
quarter of its width they are drawn as long straight strokes. Validates from this version on
also save a dense sample of just the lockbox stretch beside each curve
(augur_engine/analytics.lockbox_tail, carried as equity.lb_tail / equity.lb_tail_gated).
Runs validated before that have none, so the crowns the owner actually looks at would keep
the stretched lockbox until each one is re-validated (about 45 minutes each, and under a new
run number). This replays a run's gate bake-off over the run's OWN pinned window and adds
ONLY the tails.

A tail has to be the real cumulative of the same trades the saved curve was cut from - the
funnel stitches it straight onto the saved points - so NOTHING here is written on trust:
  * reproduction: the replayed ungated pre-lockbox and lockbox blocks must match the doc's
    (trade counts exact, totals within 0.5%), otherwise the whole run is skipped;
  * every row: the replayed 300-point curve must equal the SAVED curve point for point, the
    trade count must agree, the tail must sit where the funnel will put it (door = the
    ungated pre-lockbox count, end = the saved final value), and its lockbox span must land
    within 1.5 of the row's saved lockbox total. A row that fails any of it is skipped and
    named; the rest of the run still gets its tails;
  * only verified tails are merged, and only into deep copies of the SAVED rows. Every stat
    block, every saved curve and validate.gate_bakeoff stay exactly as they are (a guard
    re-checks that before any write);
  * the write is refused when the runner's own size estimate of the finished doc is over its
    budget, and it carries a last-update-time precondition, so a doc that changed after it
    was read is never overwritten.

"Already covered" is decided LINE BY LINE. A run whose KEEL row picked up a tail from
tools/backfill_keel.py (or any run where only some lines carry one) still gets tails on the
lines that lack them; the lines that have one keep it as saved. A run is skipped only when a
backfill already stamped it, or when every line that can carry a tail already does. A line
can carry one only when its tail would add points: on a short run, or one whose lockbox is a
big share of its trades, the saved curve already draws the lockbox more densely.

Usage:
  python tools/backfill_lb_tails.py 384                  dry run (default): replay, verify, report
  python tools/backfill_lb_tails.py 384 --write          write the verified tails
  python tools/backfill_lb_tails.py 384 --force          rebuild every line's tail, even saved ones
  python tools/backfill_lb_tails.py --list               runs with a gate block, and their tails

Exit code: 0 when every run was written, dry-run, already covered or had nothing to write;
1 when any run was refused (mismatch, too big, changed, conflict, cannot replay) or failed.

Run it from the SHARED checkout: the master registry (optimizer_history.db) and
serviceAccount.json live there, not in worktrees. A replay re-walks every gate model, so it
takes minutes per run. --list reads one document per saved run (field-masked, so the reads
are small, but each one still counts against the daily Firestore read quota).
"""
import argparse
import collections
import copy
import datetime
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.analytics import (LB_TAIL_CAP, downsample_curve, lb_tail_adds_points,  # noqa: E402
                                    lb_tail_line_cap)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth"}      # as tools/backfill_keel.py
TOOL_VERSION = "tools/backfill_lb_tails.py v1"
# statuses that are not a refusal: main() exits 0 only when every run ended in one of these
OK_STATUSES = ("written", "dry", "nothing", "covered")

REPRO_TOL = 0.005     # ungated totals: within 0.5% (the backfill_keel guard)
SPAN_TOL = 1.5        # tail span vs the saved lockbox total: whole-point rounding at both ends
END_TOL = 0.05        # the funnel's own guard on "tail ends on the saved final value"

ROW_KINDS = ("candidates", "tilts", "hybrids")
_KIND_NAME = {"candidates": "gate", "tilts": "tilt", "hybrids": "hybrid",
              "keel": "KEEL", "chosen": "chosen gate"}
# The ONLY fields a backfill may write. Firestore cannot update one element of an array, so
#   the three row arrays are rewritten whole - from deep copies of the saved rows, checked by
#   check_payload to differ from the saved rows in lb_tail* keys and nothing else.
PAYLOAD_KEYS = ("gate_validate.candidates", "gate_validate.tilts", "gate_validate.hybrids",
                "gate_validate.keel.equity.lb_tail", "gate_validate.equity.lb_tail_gated",
                "gate_validate.lb_tail_backfill")
STAMP_KEY = "gate_validate.lb_tail_backfill"


class ReplaySkip(Exception):
    """The run cannot be replayed faithfully here (no master, the book does not reproduce...)."""


def _num(x):
    """A finite real number. bool is not a number here, and neither is None."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


# ── what to replay ───────────────────────────────────────────────────────────────────────
def rebuild_plan(d):
    """Everything needed to replay a doc's gate bake-off, taken from the doc itself.
    -> (plan, None) or (None, reason).

    The window is PINNED: validate loaded its arrays from the optimize start to date_to, and a
    later start would change the causal entry features and every model walk, so the curves
    would not reproduce. A blank end would float to the newest bars, so it falls back to the
    lockbox end the validate recorded, and a run with neither is refused."""
    if not isinstance(d, dict):
        return None, "no doc"
    gv = d.get("gate_validate")
    if not (isinstance(gv, dict) and isinstance(gv.get("ungated_pre"), dict)
            and isinstance(gv.get("ungated_lockbox"), dict)):
        return None, "no gate_validate block on the doc"
    v = d.get("validate") if isinstance(d.get("validate"), dict) else {}
    if v.get("evolved_file") or d.get("evolved_file"):
        return None, ("validated an AI-evolved copy of the strategy - the saved strategy file is "
                      "not the code that ran, so it cannot be replayed")
    params = v.get("champion") or d.get("best_params")
    if not isinstance(params, dict) or not params:
        return None, "no champion params on the doc"
    src = d.get("data_source")
    sess = SESSION.get(src)
    if not sess:
        return None, f"unknown data_source {src!r}"
    for k in ("strategy", "instrument", "timeframe"):
        if not d.get(k):
            return None, f"no {k} on the doc"
    win = v.get("windows") if isinstance(v.get("windows"), dict) else {}
    opt = win.get("optimize") if isinstance(win.get("optimize"), list) else []
    lbw = win.get("lockbox") if isinstance(win.get("lockbox"), list) else []
    date_from = (opt[0] if opt else None) or d.get("date_from")
    date_to = d.get("date_to") or (lbw[1] if len(lbw) > 1 else None)
    if not date_from or not date_to:
        return None, ("data window not recorded - an open end would float to the newest bars "
                      "and change every model walk")
    lb_from = gv.get("lockbox_from")
    if not lb_from:
        return None, "no lockbox boundary recorded on the gate block"
    try:
        p_n = int(gv["ungated_pre"]["num_trades"]); l_n = int(gv["ungated_lockbox"]["num_trades"])
        p_net = float(gv["ungated_pre"]["total_pnl"]); l_net = float(gv["ungated_lockbox"]["total_pnl"])
    except Exception:
        return None, "the ungated blocks carry no trade count / total"
    k = gv.get("keel")
    keel_ok = isinstance(k, dict) and not k.get("error")
    wf = gv.get("wf_range") if isinstance(gv.get("wf_range"), list) and len(gv["wf_range"]) == 2 \
        else [None, None]
    kwargs = {"lb_from": lb_from, "wf_from": wf[0], "wf_to": wf[1], "keel": bool(keel_ok),
              # the KEEL row the doc saved, not today's default version
              "keel_version": (str(k["version"]) if keel_ok and k.get("version") else None)}
    if isinstance(gv.get("gates"), list):
        kwargs["gates"] = tuple(str(g) for g in gv["gates"])
    if isinstance(gv.get("thresholds"), list):
        kwargs["thresholds"] = tuple(float(t) for t in gv["thresholds"])
    # settings absent from an older doc fall back to the engine's defaults; the point-for-point
    #   curve check below is what decides whether that was right
    for name, cast in (("lockbox_months", int), ("min_kept", int), ("min_keep_frac", float),
                       ("windows", int)):
        if gv.get(name) is not None:
            kwargs[name] = cast(gv[name])
    plan = {"strategy": d["strategy"], "instrument": d["instrument"], "timeframe": d["timeframe"],
            "session": sess, "source": src, "params": dict(params),
            "cost_pts": float(d.get("cost_pts") or 0.0), "multiplier": float(d.get("multiplier") or 1.0),
            "date_from": str(date_from), "date_to": str(date_to),
            "expect_n": p_n + l_n, "expect_net": p_net + l_net, "kwargs": kwargs}
    return plan, None


def check_trade_book(plan, trades):
    """Cheap first gate, before minutes of model walks: the replayed champion book must have
    the saved trade count and (within 0.5%) the saved net. -> (ok, message)."""
    n = len(trades or [])
    try:
        net = float(sum(float(t[2]) for t in (trades or []) if len(t) >= 3))
    except Exception:
        return False, "replayed trades are not engine-shaped"
    want_n, want_net = int(plan["expect_n"]), float(plan["expect_net"])
    ok = n == want_n and abs(net - want_net) <= REPRO_TOL * max(1.0, abs(want_net))
    return ok, f"champion book {n} trades, net {net:.1f} pts vs doc {want_n} trades, {want_net:.1f} pts"


def check_reproduction(saved_gv, rebuilt_gv):
    """The replayed ungated pre-lockbox and lockbox blocks against the doc's: counts exact,
    totals within 0.5%, same lockbox boundary. -> (ok, report lines)."""
    if not isinstance(rebuilt_gv, dict):
        return False, ["the replay produced no gate block"]
    ok, lines = True, []
    for blk in ("ungated_pre", "ungated_lockbox"):
        s, r = saved_gv.get(blk), rebuilt_gv.get(blk)
        try:
            ns, nr = int(s["num_trades"]), int(r["num_trades"])
            ps, pr = float(s["total_pnl"]), float(r["total_pnl"])
        except Exception:
            ok = False
            lines.append(f"{blk}: missing on the doc or the replay")
            continue
        good = ns == nr and abs(pr - ps) <= REPRO_TOL * max(1.0, abs(ps))
        ok = ok and good
        lines.append(f"{blk}: n {nr} vs doc {ns}, net {pr:.1f} vs doc {ps:.1f} pts"
                     + ("" if good else "  <- MISMATCH"))
    if str(rebuilt_gv.get("lockbox_from")) != str(saved_gv.get("lockbox_from")):
        ok = False
        lines.append(f"lockbox_from: replay {rebuilt_gv.get('lockbox_from')} vs doc "
                     f"{saved_gv.get('lockbox_from')}  <- MISMATCH")
    return ok, lines


# ── row matching + verification ──────────────────────────────────────────────────────────
def row_key(kind, row):
    """A row's identity across the saved doc and its replay: gate model+cut-off, tilt
    model+scheme, hybrid model. None when the row cannot be identified."""
    if not isinstance(row, dict):
        return None
    try:
        if kind == "candidates":
            return (str(row["model"]), round(float(row["threshold"]), 4))
        if kind == "tilts":
            return (str(row["model"]), str(row["scheme"]))
        if kind == "hybrids":
            return (str(row["model"]),)
    except Exception:
        return None
    return None


def _label(kind, key):
    if key is None:
        return _KIND_NAME[kind]
    if kind in ("candidates", "chosen"):
        return f"{_KIND_NAME[kind]} {key[0]}@{key[1]:.2f}"
    return f"{_KIND_NAME[kind]} " + "/".join(str(x) for x in key)


def _lockbox_total(row):
    lb = row.get("lockbox") if isinstance(row, dict) else None
    return lb.get("total_pnl") if isinstance(lb, dict) else None


def match_rows(saved_gv, rebuilt_gv):
    """Pair every SAVED line that could carry a tail with its replayed twin.
    -> entries {kind, index, label, saved_eq, rebuilt_eq, lb_total, problem}; problem is None
    when the pair is ready for verify_row. A key seen twice on either side is ambiguous and
    both rows are skipped rather than guessed at."""
    out = []
    rebuilt_gv = rebuilt_gv if isinstance(rebuilt_gv, dict) else {}
    for kind in ROW_KINDS:
        saved = saved_gv.get(kind) if isinstance(saved_gv.get(kind), list) else []
        rebuilt = rebuilt_gv.get(kind) if isinstance(rebuilt_gv.get(kind), list) else []
        s_count = collections.Counter(row_key(kind, r) for r in saved)
        r_count = collections.Counter(row_key(kind, r) for r in rebuilt)
        r_map = {row_key(kind, r): r for r in rebuilt if row_key(kind, r) is not None}
        for i, r in enumerate(saved):
            key = row_key(kind, r)
            problem = None
            if key is None:
                problem = "the saved row cannot be identified"
            elif s_count[key] > 1 or r_count[key] > 1:
                problem = "ambiguous - more than one row with this identity"
            elif key not in r_map:
                problem = "the replay made no such row"
            twin = None if problem else r_map[key]
            out.append({"kind": kind, "index": i, "label": _label(kind, key),
                        "saved_eq": r.get("equity") if isinstance(r, dict) else None,
                        "rebuilt_eq": twin.get("equity") if isinstance(twin, dict) else None,
                        "lb_total": _lockbox_total(r), "problem": problem})

    k = saved_gv.get("keel")
    if isinstance(k, dict):
        rk = rebuilt_gv.get("keel")
        problem = None
        if k.get("error"):
            problem = "the saved KEEL row is an error row"
        elif not isinstance(rk, dict) or rk.get("error"):
            problem = f"the replay's KEEL row failed: {(rk or {}).get('error') if isinstance(rk, dict) else rk}"
        elif str(rk.get("version")) != str(k.get("version")):
            problem = f"the replay ran KEEL {rk.get('version')}, the doc saved {k.get('version')}"
        out.append({"kind": "keel", "index": None, "label": "KEEL " + str(k.get("version") or "?"),
                    "saved_eq": k.get("equity"),
                    "rebuilt_eq": rk.get("equity") if (problem is None) else None,
                    "lb_total": _lockbox_total(k), "problem": problem})

    ch, eq = saved_gv.get("chosen"), saved_gv.get("equity")
    if isinstance(ch, dict) and isinstance(eq, dict) and "cum_gated" in eq:
        key = row_key("candidates", ch)
        rch = rebuilt_gv.get("chosen")
        rkey = row_key("candidates", rch)
        problem = None
        if key is None:
            problem = "the saved chosen gate cannot be identified"
        elif rkey != key:
            _who = (f"{rkey[0]}@{rkey[1]:.2f}" if rkey is not None else "no gate")
            problem = f"the replay crowned {_who}, the doc crowned {key[0]}@{key[1]:.2f}"
        # The one-look block when the gate earned it; otherwise the crowned candidate's own
        #   lockbox block measures the same trades (its curve IS this line).
        _lb = saved_gv.get("lockbox")
        lbg = _lockbox_total({"lockbox": _lb.get("gated")}) if isinstance(_lb, dict) else None
        if lbg is None and key is not None:
            twins = [c for c in (saved_gv.get("candidates") or []) if row_key("candidates", c) == key]
            lbg = _lockbox_total(twins[0]) if len(twins) == 1 else None
        out.append({"kind": "chosen", "index": None, "label": _label("chosen", key),
                    "saved_eq": eq,
                    "rebuilt_eq": rebuilt_gv.get("equity") if problem is None else None,
                    "lb_total": lbg, "problem": problem})
    return out


def expected_j0(n, pts, i0):
    """How many saved points sit strictly before the last pre-lockbox trade: the saved
    curve's own index rule (downsample_curve) replayed on the trade numbers."""
    idx = downsample_curve(range(int(n)), cap=int(pts), ndp=None)
    return sum(1 for v in idx[:-1] if v < int(i0) - 1)


def verify_row(entry, saved_gv):
    """-> (plain-json tail, None) when the replayed tail is safe to stitch onto the SAVED
    curve, else (None, reason)."""
    if entry.get("problem"):
        return None, entry["problem"]
    ck, tk = ("cum_gated", "lb_tail_gated") if entry["kind"] == "chosen" else ("cum", "lb_tail")
    s_eq, r_eq = entry.get("saved_eq"), entry.get("rebuilt_eq")
    try:
        p = int(saved_gv["ungated_pre"]["num_trades"])
        l = int(saved_gv["ungated_lockbox"]["num_trades"])
    except Exception:
        return None, "the doc's ungated blocks carry no trade counts"
    s_cum = s_eq.get(ck) if isinstance(s_eq, dict) else None
    if not isinstance(s_cum, list) or len(s_cum) < 3:
        return None, "the saved row has no curve"
    r_cum = r_eq.get(ck) if isinstance(r_eq, dict) else None
    if not isinstance(r_cum, list):
        return None, "the replay made no curve for this row"
    if len(r_cum) != len(s_cum):
        return None, f"replayed curve has {len(r_cum)} points, the saved one {len(s_cum)}"
    for i, (a, b) in enumerate(zip(s_cum, r_cum)):
        if not (_num(a) and _num(b) and a == b):
            return None, f"replayed curve differs at point {i} ({b} vs saved {a})"
    n_s, n_r = s_eq.get("n"), r_eq.get("n")
    if not (_int(n_s) and _int(n_r) and n_s == n_r):
        return None, f"trade count n differs (replay {n_r}, saved {n_s})"
    if n_s != p + l:
        # the funnel refuses a tail whose curve is not pre-lockbox + lockbox trades long
        return None, f"saved n {n_s} is not {p} pre-lockbox + {l} lockbox trades"
    t = r_eq.get(tk)
    if not isinstance(t, dict):
        return None, "the replay made no tail for this row"
    tc = t.get("cum")
    if t.get("v") != 1:
        return None, f"unknown tail format v={t.get('v')!r}"
    if not (_int(t.get("i0")) and t["i0"] == p):
        return None, f"tail door i0 {t.get('i0')} is not the ungated pre-lockbox count {p}"
    if not (_int(t.get("pts")) and t["pts"] == len(s_cum)):
        return None, f"tail was cut for {t.get('pts')} saved points, the saved curve has {len(s_cum)}"
    # j0 may be the saved curve's last index (pts-1): a lockbox so small only the final saved
    #   point is past the door. The engine writes it, the funnel stitches it - one bound in all
    #   three places.
    if not (_int(t.get("j0")) and 1 <= t["j0"] <= len(s_cum) - 1
            and t["j0"] == expected_j0(n_s, len(s_cum), p)):
        return None, f"tail j0 {t.get('j0')} does not match the saved curve's index rule"
    if not (isinstance(tc, list) and 1 <= len(tc) <= l and all(_num(x) for x in tc)
            and _num(t.get("base"))):
        return None, "tail values are missing, too many or not finite"
    if not lb_tail_adds_points(len(tc), len(s_cum), t["j0"]):
        # the funnel refuses it too: stitching would draw this lockbox with fewer real points
        return None, (f"the saved curve already has {len(s_cum) - t['j0']} points from the door on, "
                      f"a {len(tc)}-point tail adds none")
    if abs(tc[-1] - s_cum[-1]) > END_TOL:
        return None, f"tail ends at {tc[-1]}, the saved curve at {s_cum[-1]}"
    lb_total = entry.get("lb_total")
    if not _num(lb_total):
        return None, "no saved lockbox total to check the tail against"
    span = float(tc[-1]) - float(t["base"])
    if abs(span - float(lb_total)) > SPAN_TOL:
        return None, f"tail span {span:.1f} is not the saved lockbox total {float(lb_total):.1f}"
    return json.loads(json.dumps(t, allow_nan=False)), None


def verify_rows(saved_gv, rebuilt_gv, keep_tailed=False):
    """match_rows + verify_row for every saved line. -> results {kind, index, label, ok, kept,
    reason, tail}. keep_tailed: a saved line that already carries a well-formed tail keeps it
    (kept=True, never rewritten) - the default run; --force rebuilds those too."""
    res = []
    for e in match_rows(saved_gv, rebuilt_gv):
        tk = "lb_tail_gated" if e["kind"] == "chosen" else "lb_tail"
        if keep_tailed and isinstance(e.get("saved_eq"), dict) and _tail_shape_ok(e["saved_eq"].get(tk)):
            res.append({"kind": e["kind"], "index": e["index"], "label": e["label"], "ok": False,
                        "kept": True, "reason": "already carries a lockbox tail - left as saved",
                        "tail": None})
            continue
        tail, why = verify_row(e, saved_gv)
        res.append({"kind": e["kind"], "index": e["index"], "label": e["label"],
                    "ok": tail is not None, "kept": False, "reason": why, "tail": tail})
    return res


# ── merge + payload ──────────────────────────────────────────────────────────────────────
def _lines(gv):
    """Every saved line that could carry a tail: (label, equity dict, curve key, tail key)."""
    gv = gv if isinstance(gv, dict) else {}
    out = []
    for kind in ROW_KINDS:
        for r in (gv.get(kind) if isinstance(gv.get(kind), list) else []):
            if isinstance(r, dict):
                out.append((_label(kind, row_key(kind, r)), r.get("equity"), "cum", "lb_tail"))
    k = gv.get("keel")
    if isinstance(k, dict) and not k.get("error"):
        out.append(("KEEL " + str(k.get("version") or "?"), k.get("equity"), "cum", "lb_tail"))
    if isinstance(gv.get("chosen"), dict) and isinstance(gv.get("equity"), dict):
        out.append((_label("chosen", row_key("candidates", gv["chosen"])), gv["equity"],
                    "cum_gated", "lb_tail_gated"))
    return out


def existing_tails(gv):
    """(lines already carrying a WELL-FORMED tail, the backfill stamp or None). A null, a string
    or any other junk under a tail key is not a tail - the funnel ignores it, so it must not
    make a run look covered either."""
    n = sum(1 for _lbl, eq, _ck, tk in _lines(gv) if isinstance(eq, dict) and _tail_shape_ok(eq.get(tk)))
    return n, (gv.get("lb_tail_backfill") if isinstance(gv, dict) else None)


def line_cap(gv):
    """Lockbox points per line the engine gives this run's grid (analytics.lb_tail_line_cap, the
    same call ml_gate makes). A doc without its gate / cut-off lists replays on the engine's
    default grid, which keeps the full cap."""
    gv = gv if isinstance(gv, dict) else {}
    if isinstance(gv.get("gates"), list) and isinstance(gv.get("thresholds"), list):
        g, t = len(gv["gates"]), len(gv["thresholds"])
        return lb_tail_line_cap(g * t + 3 * g + 2)
    return LB_TAIL_CAP


def tail_coverage(gv):
    """Which lines already carry a tail and which could carry one but do not.
    -> {"have": [labels], "missing": [labels], "stamp": the backfill stamp or None}.
    A line 'could carry' one when its curve is on the run's full trade list and a tail at this
    run's per-line cap would add lockbox points (the rule the engine and the funnel apply) -
    so a run where no tail can help never looks like it is waiting for a backfill."""
    gv = gv if isinstance(gv, dict) else {}
    have, missing = [], []
    try:
        p = int(gv["ungated_pre"]["num_trades"]); l = int(gv["ungated_lockbox"]["num_trades"])
    except Exception:
        p = l = 0
    cap = line_cap(gv)
    for lbl, eq, ck, tk in _lines(gv):
        if not isinstance(eq, dict):
            continue
        if _tail_shape_ok(eq.get(tk)):
            have.append(lbl)
            continue
        cum, n = eq.get(ck), eq.get("n")
        if not (p >= 2 and l >= 1 and cap >= 1 and isinstance(cum, list) and len(cum) >= 3
                and _int(n) and n == p + l):
            continue
        j0 = expected_j0(n, len(cum), p)
        if j0 >= 1 and lb_tail_adds_points(min(cap, l), len(cum), j0):
            missing.append(lbl)
    return {"have": have, "missing": missing, "stamp": gv.get("lb_tail_backfill")}


def merge_tails(saved_gv, results):
    """Verified tails merged into DEEP COPIES of the saved rows; saved_gv is never touched.
    -> {"candidates"/"tilts"/"hybrids": full row list (only for kinds with a verified row),
        "keel_tail": tail, "gated_tail": tail}."""
    merged = {}
    for kind in ROW_KINDS:
        oks = [r for r in results if r["kind"] == kind and r["ok"]]
        if not oks:
            continue
        rows = copy.deepcopy(saved_gv[kind])
        for r in oks:
            rows[r["index"]]["equity"]["lb_tail"] = copy.deepcopy(r["tail"])
        merged[kind] = rows
    for kind, name in (("keel", "keel_tail"), ("chosen", "gated_tail")):
        oks = [r for r in results if r["kind"] == kind and r["ok"]]
        if oks:
            merged[name] = copy.deepcopy(oks[0]["tail"])
    return merged


def _tail_shape_ok(t):
    try:
        json.dumps(t, allow_nan=False)
    except Exception:
        return False
    return (isinstance(t, dict) and t.get("v") == 1 and isinstance(t.get("cum"), list)
            and len(t["cum"]) >= 1 and all(_num(x) for x in t["cum"]) and _num(t.get("base"))
            and all(_int(t.get(k)) for k in ("i0", "j0", "pts")))


_ABSENT = object()


def _minus_row_tail(rows):
    """Rows with ONLY equity.lb_tail taken out - the one key a backfill may add or change on a
    row. Any other lb_tail* key (a row-level one, equity.lb_tail_gated on a candidate, an
    equity.lb_tail_x) stays in, so it cannot slip past the comparison with the saved rows."""
    out = []
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("equity"), dict) and "lb_tail" in r["equity"]:
            r = dict(r, equity={q: w for q, w in r["equity"].items() if q != "lb_tail"})
        out.append(r)
    return out


def check_payload(saved_gv, payload):
    """Refuse (ValueError) any payload that could touch more than the tails: a key outside
    PAYLOAD_KEYS (validate.gate_bakeoff, a stat block, a saved curve...), a row array that
    differs from the saved one in anything but each row's equity.lb_tail, or a tail that is
    not well formed (a null or junk tail the payload adds or changes is refused, not written)."""
    for k, v in payload.items():
        if k not in PAYLOAD_KEYS:
            raise ValueError(f"refusing to write {k!r}: a lockbox backfill writes only tails")
        if k in ("gate_validate.candidates", "gate_validate.tilts", "gate_validate.hybrids"):
            kind = k.split(".", 1)[1]
            saved = saved_gv.get(kind)
            if not isinstance(v, list) or not isinstance(saved, list) or len(v) != len(saved):
                raise ValueError(f"refusing to write {k!r}: row count differs from the saved doc")
            if _minus_row_tail(v) != _minus_row_tail(saved):
                raise ValueError(f"refusing to write {k!r}: a row differs from the saved doc "
                                 "in more than its equity.lb_tail")
            for r, s in zip(v, saved):
                t = (r.get("equity") or {}).get("lb_tail", _ABSENT) if isinstance(r, dict) else _ABSENT
                if t is _ABSENT:
                    continue
                st = (s.get("equity") or {}).get("lb_tail", _ABSENT) if isinstance(s, dict) else _ABSENT
                if st is not _ABSENT and same_block(t, st):
                    continue                       # the saved row's own tail, carried over untouched
                if not _tail_shape_ok(t):
                    raise ValueError(f"refusing to write {k!r}: malformed tail")
        elif k == STAMP_KEY:
            if not (isinstance(v, dict)
                    and set(v) == {"version", "at", "rows_written", "rows_skipped", "rows_kept"}):
                raise ValueError("refusing to write a malformed provenance stamp")
        elif not _tail_shape_ok(v):
            raise ValueError(f"refusing to write {k!r}: malformed tail")
    if STAMP_KEY not in payload:
        raise ValueError("refusing to write tails without the provenance stamp")
    return True


def _now():
    # to the microsecond: the stamp is how a write whose reply was lost is recognised afterwards
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_update(saved_gv, results, merged, at=None, version=TOOL_VERSION):
    """The Firestore update for one run: dotted field paths -> values, or {} when no row
    verified. Checked by check_payload before it is returned."""
    n_ok = sum(1 for r in results if r["ok"])
    n_kept = sum(1 for r in results if r.get("kept"))
    if not n_ok:
        return {}
    payload = {}
    for kind in ROW_KINDS:
        if kind in merged:
            payload["gate_validate." + kind] = merged[kind]
    if merged.get("keel_tail") is not None:
        payload["gate_validate.keel.equity.lb_tail"] = merged["keel_tail"]
    if merged.get("gated_tail") is not None:
        payload["gate_validate.equity.lb_tail_gated"] = merged["gated_tail"]
    payload[STAMP_KEY] = {"version": str(version), "at": at or _now(),
                          "rows_written": int(n_ok), "rows_skipped": int(len(results) - n_ok - n_kept),
                          "rows_kept": int(n_kept)}
    check_payload(saved_gv, payload)
    return payload


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


def summary_lines(results):
    """Owner-facing report for one run's rows."""
    lines = []
    parts = []
    todo = [r for r in results if not r.get("kept")]
    for kind in ROW_KINDS + ("keel", "chosen"):
        rs = [r for r in todo if r["kind"] == kind]
        if rs:
            name = {"candidates": "gates", "tilts": "tilts", "hybrids": "hybrids"}.get(kind, _KIND_NAME[kind])
            parts.append(f"{name} {sum(r['ok'] for r in rs)}/{len(rs)}")
    n_ok = sum(1 for r in results if r["ok"])
    n_kept = len(results) - len(todo)
    lines.append(f"rows: {n_ok} of {len(todo)} verified ({', '.join(parts) or 'no ML rows'})"
                 + (f"; {n_kept} already carried a tail and stay as saved" if n_kept else ""))
    oks = [r["tail"] for r in results if r["ok"]]
    if oks:
        def _dist(vals):
            c = collections.Counter(vals)
            if len(c) == 1:
                return str(next(iter(c)))
            return ", ".join(f"{v} ({k} rows)" for v, k in sorted(c.items()))
        lines.append(f"tails: i0 {_dist([t['i0'] for t in oks])} | j0 {_dist([t['j0'] for t in oks])}"
                     f" | m {_dist([len(t['cum']) for t in oks])} | pts {_dist([t['pts'] for t in oks])}")
    for r in todo:
        if not r["ok"]:
            lines.append(f"  SKIP {r['label']}: {r['reason']}")
    return lines


# ── Firestore + market data (not unit-tested: everything above is) ───────────────────────
def rebuild_from_market_data(plan, log=print):
    """Replay the champion book and the gate bake-off on the pinned window."""
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from augur_engine.ml_gate import gate_validate
    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        raise ReplaySkip(f"no master for {plan['instrument']} {plan['timeframe']} {plan['session']} "
                         f"{plan['source']} (the master registry lives in the shared checkout)")
    arr = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
    res = run_backtest(plan["strategy"], arrays=arr, params=plan["params"],
                       cost_pts=plan["cost_pts"], return_trades=True)
    trades = list((res or {}).get("trades") or [])
    ok, msg = check_trade_book(plan, trades)
    log("  " + msg + ("" if ok else "  <- MISMATCH"))
    if not ok:
        raise ReplaySkip("the champion book does not reproduce on the pinned window")
    return gate_validate(arr, trades, **plan["kwargs"])


def same_block(a, b):
    """Two reads of a gate block hold the same values. Compared as serialised text, not with
    ==, because two reads of a NaN stat are two NaN objects and NaN != NaN."""
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    except Exception:
        return False


def _run_ref(db, run_id):
    return db.collection("users").document(UID).collection("runs").document(str(run_id))


def _write_landed(ref, payload):
    """After a write raised: read the doc back and say whether THIS write's stamp is on it. A
    commit the server applied but whose reply was lost looks like a failure to the client."""
    try:
        s = ref.get()
        d = s.to_dict() if getattr(s, "exists", False) else None
        st = ((d or {}).get("gate_validate") or {}).get("lb_tail_backfill")
        return isinstance(st, dict) and same_block(st, payload.get(STAMP_KEY))
    except Exception:
        return False


def one(db, run_id, write=False, force=False, *, rebuild=None, size_fn=None, budget=None,
        log=print, at=None):
    """Replay, verify and (write=True) backfill one run. Returns a status word:
    nodoc / skip / covered / mismatch / nothing / toobig / dry / changed / conflict / written.
    covered = every line that can carry a tail already has one (or a backfill stamped the
    run); skip = the run cannot be replayed faithfully here."""
    ref = _run_ref(db, run_id)
    snap = ref.get()
    d = snap.to_dict() if getattr(snap, "exists", False) else None
    if not d:
        log(f"#{run_id}: no doc"); return "nodoc"
    plan, why = rebuild_plan(d)
    if plan is None:
        log(f"#{run_id}: {why} - skip"); return "skip"
    gv = d["gate_validate"]
    cov = tail_coverage(gv)
    if not force:
        stamp = cov["stamp"]
        if isinstance(stamp, dict):
            log(f"#{run_id}: backfilled {stamp.get('at')} ({stamp.get('rows_written')} rows) - skip, "
                "pass --force to rebuild its tails"); return "covered"
        if not cov["missing"] and cov["have"]:
            log(f"#{run_id}: all {len(cov['have'])} line(s) that can carry a lockbox tail already do - "
                "skip, pass --force to rebuild them"); return "covered"
        if not cov["missing"]:
            log(f"#{run_id}: no line can carry a lockbox tail - the saved curves already draw the "
                "lockbox at least as densely as a tail would - not written"); return "nothing"
        if cov["have"]:
            log(f"#{run_id}: {len(cov['have'])} line(s) already carry a tail and stay as saved; "
                f"{len(cov['missing'])} line(s) lack one")
    kw = plan["kwargs"]
    log(f"#{run_id} {plan['strategy']} {plan['instrument']} {plan['timeframe']} "
        f"window {plan['date_from']}..{plan['date_to']} (pinned) LB {kw['lb_from']} | "
        f"{len(kw.get('gates', ()))} gates x {len(kw.get('thresholds', ()))} cut-offs, "
        f"KEEL {kw['keel_version'] if kw['keel'] else 'off'}")
    t0 = time.time()
    try:
        rebuilt = (rebuild or rebuild_from_market_data)(plan)
    except ReplaySkip as e:
        log(f"#{run_id}: {e} - not written"); return "skip"
    ok, lines = check_reproduction(gv, rebuilt)
    for ln in lines:
        log("  " + ln)
    log(f"  replayed in {time.time() - t0:.0f}s")
    if not ok:
        log(f"#{run_id}: REPRODUCTION MISMATCH - not written"); return "mismatch"
    results = verify_rows(gv, rebuilt, keep_tailed=not force)
    for ln in summary_lines(results):
        log("  " + ln)
    payload = build_update(gv, results, merge_tails(gv, results), at=at)
    if not payload:
        log(f"#{run_id}: no row verified - not written"); return "nothing"
    fits, nbytes, cap = size_check(apply_update(d, payload), size_fn, budget)
    now_bytes = size_check(d, size_fn, budget)[1]
    log(f"  doc size: {now_bytes / 1024:.0f} KB now, {nbytes / 1024:.0f} KB with tails, "
        f"runner budget {cap / 1024:.0f} KB")
    if not fits:
        log(f"#{run_id}: REFUSED - the doc would be over the runner's size budget"); return "toobig"
    if not write:
        log(f"#{run_id}: dry run - not written (pass --write)"); return "dry"
    # The replay took minutes. Read the doc again and write only if its gate block is exactly
    #   the one the tails were verified against; the precondition then covers the short gap
    #   between this read and the write.
    snap2 = ref.get()
    d2 = snap2.to_dict() if getattr(snap2, "exists", False) else None
    if not d2 or not same_block(d2.get("gate_validate"), gv):
        log(f"#{run_id}: the gate block changed during the replay - not written, run it again")
        return "changed"
    fits2, nbytes2, _ = size_check(apply_update(d2, payload), size_fn, budget)
    if not fits2:
        log(f"#{run_id}: REFUSED - the doc grew past the runner's size budget ({nbytes2 / 1024:.0f} KB)")
        return "toobig"
    # retry=None: the client would otherwise re-send a commit whose reply was lost (a Wi-Fi flap,
    #   a 503) with the SAME precondition, which now fails - and report a write that landed as a
    #   conflict. One attempt; if it raises, read the doc back and look for this write's stamp.
    try:
        ref.update(payload, option=db.write_option(last_update_time=snap2.update_time), retry=None)
    except Exception as e:
        if _write_landed(ref, payload):
            log(f"#{run_id}: the write raised {type(e).__name__}, but the doc carries this backfill's "
                f"stamp ({payload[STAMP_KEY]['at']}) - the reply was lost, the write landed")
        elif type(e).__name__ in ("FailedPrecondition", "Aborted"):
            log(f"#{run_id}: the doc changed just before the write - not written, run it again")
            return "conflict"
        else:
            raise
    log(f"#{run_id}: WRITTEN {sum(r['ok'] for r in results)} lockbox tail(s) "
        f"({', '.join(k for k in payload if k != STAMP_KEY)})")
    return "written"


LIST_FIELDS = ["strategy", "instrument", "timeframe", "date_from", "date_to",
               "gate_validate.ungated_pre.num_trades", "gate_validate.ungated_lockbox.num_trades",
               "gate_validate.n_candidates", "gate_validate.keel.version",
               "gate_validate.keel.equity.lb_tail.i0", "gate_validate.equity.lb_tail_gated.i0",
               "gate_validate.lb_tail_backfill"]


def list_row(run_id, d):
    """One --list line from a field-masked doc, or None when the run has no gate block."""
    gv = (d or {}).get("gate_validate")
    if not isinstance(gv, dict) or not isinstance(gv.get("ungated_pre"), dict):
        return None
    st = gv.get("lb_tail_backfill")
    k_eq = (gv.get("keel") or {}).get("equity") if isinstance(gv.get("keel"), dict) else None
    # The field mask cannot reach inside the gate / tilt / hybrid row ARRAYS (Firestore selects
    #   whole arrays, and those are most of the doc), so without a backfill stamp this can only
    #   see the KEEL row and the chosen gate - and says so, rather than calling a run covered
    #   because tools/backfill_keel.py happened to leave a tail on its KEEL row.
    if isinstance(st, dict):
        tails = f"backfilled {st.get('at')} ({st.get('rows_written')} rows, {st.get('rows_skipped')} skipped)"
    elif (isinstance(k_eq, dict) and "lb_tail" in k_eq) or "lb_tail_gated" in (gv.get("equity") or {}):
        tails = "KEEL/gate tail seen, other rows not read here - a dry run shows which lines lack one"
    else:
        tails = "no KEEL/gate tail (other rows not read here)"
    return (f"#{run_id} {d.get('strategy')} {d.get('instrument')} {d.get('timeframe')} "
            f"{d.get('date_from')}..{d.get('date_to')} | pre {gv['ungated_pre'].get('num_trades')} "
            f"LB {(gv.get('ungated_lockbox') or {}).get('num_trades')} | "
            f"{gv.get('n_candidates')} gates | KEEL {(gv.get('keel') or {}).get('version') if isinstance(gv.get('keel'), dict) else '-'}"
            f" | {tails}")


def list_runs(db, log=print):
    runs = db.collection("users").document(UID).collection("runs")
    rows = []
    for s in runs.select(LIST_FIELDS).stream():
        line = list_row(s.id, s.to_dict() or {})
        if line:
            rows.append((int(s.id) if str(s.id).isdigit() else -1, line))
    for _, line in sorted(rows, reverse=True):
        log(line)
    log(f"{len(rows)} run(s) with a gate block")


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
        prog="backfill_lb_tails.py",
        description="Backfill the 1A funnel's dense lockbox tails onto saved runs. Dry run by "
                    "default: replays each run's gate bake-off on its pinned window, verifies every "
                    "row point for point against the saved curve, and reports.",
        epilog="Run from the shared checkout (master registry + serviceAccount.json live there).")
    ap.add_argument("runs", nargs="*", type=int, help="run numbers, e.g. 384")
    ap.add_argument("--write", action="store_true",
                    help="write the verified tails (default: dry run, nothing written)")
    ap.add_argument("--force", action="store_true",
                    help="rebuild a run that already carries tails")
    ap.add_argument("--list", action="store_true",
                    help="list runs with a gate block and whether they carry tails "
                         "(field-masked; one read per saved run)")
    a = ap.parse_args(argv)
    if not a.runs and not a.list:
        ap.print_help()
        return 2
    os.chdir(ROOT)
    import augur_engine.data as _data
    if os.environ.get("EDGELOG_UPLOADS"):        # run from a worktree against the shared masters
        _data.UPLOADS = os.environ["EDGELOG_UPLOADS"]
    db = _db()
    if a.list:
        list_runs(db)
    rc = 0
    for rid in a.runs:
        try:
            status = one(db, rid, write=a.write, force=a.force)
        except Exception as e:
            print(f"#{rid}: FAILED {type(e).__name__}: {e}")
            rc = 1
            continue
        if status not in OK_STATUSES:
            rc = 1               # a refusal: a batch script must not read it as success
    return rc


if __name__ == "__main__":
    sys.exit(main())

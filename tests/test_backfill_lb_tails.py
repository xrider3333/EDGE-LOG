"""tools/backfill_lb_tails.py - the lockbox-tail backfill for saved runs (2026-09-13).

WHY: the 1A funnel stitches a row's lb_tail straight onto its SAVED 300-point curve, so a
tail replayed from a curve that is even one point different would draw a lockbox the run
never had. The backfill therefore writes nothing on trust. These tests pin, with no
Firestore and no market data:
  * an exact replay merges a tail onto every row, into deep copies of the SAVED rows;
  * one curve point off, a tail span that misses the saved lockbox total, or a tail whose
    door / index / end is wrong skips THAT row and names it - the others still get theirs;
  * the saved doc is never mutated, and the payload can only ever carry the tail fields (no
    validate.gate_bakeoff, no stat block, no saved curve) - check_payload refuses otherwise;
  * the runner's own size guard refuses a doc that would go over its budget;
  * the orchestration (dry run, write with a precondition, changed doc, conflict) on a fake
    Firestore;
  * "already covered" is per line: a KEEL-only tail (tools/backfill_keel.py) does not block
    the other lines, junk under a tail key is not a tail, and a run where no tail can add
    points is not replayed; a write whose reply was lost is recognised by its own stamp; the
    exit code is non-zero on any refusal; a tail that adds no points is skipped; a door on
    the last saved point (a tiny lockbox) verifies;
  * the matcher accepts the real engine's output shape (gate_validate on synthetic arrays).

Rows below are #384-shaped: the scalar and stat blocks are copied from the saved run doc,
while the curves and lockbox totals are built from synthetic trades with the real analytics
helpers so that every number on a row agrees with its curve.
"""
import copy
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_REPO, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import backfill_lb_tails as B  # noqa: E402
from augur_engine.analytics import (LB_TAIL_CAP, downsample_curve, lockbox_tail,  # noqa: E402
                                    strip_lb_tails)

N, I0 = 1400, 1300          # 100 lockbox trades, so the 80-point stride is exercised
RUN = "384"

# ── #384-shaped rows (scalar + stat blocks verbatim from the saved doc, curves added below) ──
_STAT_A = {"win_rate": 29.387755102040817, "num_trades": 245, "sortino": 2.174,
           "total_pnl": 3522.161249999971, "avg_pnl": 14.376168367346821,
           "profit_factor": 1.2217469628614321, "sharpe": 0.924,
           "max_drawdown": -3239.9134062500107, "rec": 1.09}
_STAT_B = {"win_rate": 30.34324942791762, "wins": 663, "losses": 1522, "num_trades": 2185,
           "sortino": 2.823, "total_pnl": 27707.62864000914, "avg_win": 170.21140783519132,
           "avg_pnl": 12.680836906182673, "profit_factor": 1.3254264007975434,
           "avg_loss": 55.94121862990979, "max_drawdown": -3395.212079320958, "sharpe": 1.062}


def _cand(model, pre_pnl, kept_pre):
    return {"model": model, "threshold": 0.45, "eligible": True, "kept_pre": kept_pre,
            "pre_pnl": pre_pnl, "pre_pf": 1.33424875833534, "pre_wr": 29.77712824260139,
            "pre_rec": 8.28, "pre_sharpe": 0.935, "pre_sortino": 2.565,
            "lockbox": dict(_STAT_A), "full": dict(_STAT_A), "is_rng": dict(_STAT_A),
            "wf_rng": dict(_STAT_A), "wf_lb": dict(_STAT_A)}


def _tilt(scheme, rule):
    return {"model": "logistic", "scheme": scheme, "rule": rule, "crownable": False,
            "n_trades": 4075, "kept_pre": 3802, "avg_size": 1.011, "max_size": 1.69,
            "cutoff": None, "pre_rec": 11.74,
            "sizes": {"normal": 1630, "dropped": 0, "small": 1093, "big": 1352},
            "pre": dict(_STAT_B), "lockbox": dict(_STAT_B), "full": dict(_STAT_B),
            "is_rng": dict(_STAT_B), "wf_rng": dict(_STAT_B), "wf_lb": dict(_STAT_B)}


def _hyb():
    return {"model": "logistic", "scheme": "linear", "rule": "slides 0.25x to 3x on survivors",
            "floor": 0.45, "cutoff": 0.45, "crownable": False, "n_trades": 2982,
            "kept_pre": 2737, "max_size": 2.48, "pre_rec": 8.88,
            "sizes": {"normal": 2517, "dropped": 1093, "small": 370, "big": 95},
            "pre": dict(_STAT_B), "lockbox": dict(_STAT_B), "full": dict(_STAT_B),
            "is_rng": dict(_STAT_B), "wf_rng": dict(_STAT_B), "wf_lb": dict(_STAT_B)}


def _keel():
    return {"model": "keel", "scheme": "skill-gated expectancy tilt", "version": "v12",
            "rule": "size = clip(1 + 0.5 * trust * z, 0.5, 2.0); trust = clip(t_dollar / 2, 0, 1)",
            "trust_mean": 0.115, "trust_on": 0.2, "member_trust": {"huber": 0.0, "et": 0.045, "logit": 0.462},
            "crownable": False, "n_trades": 4075, "kept_pre": 3802, "avg_size": 1.211,
            "max_size": 3.0, "cutoff": None, "pre_rec": 5.53,
            "sizes": {"dropped": 0, "normal": 3361, "big": 482, "small": 232},
            "pre": dict(_STAT_B), "lockbox": dict(_STAT_B), "full": dict(_STAT_B),
            "is_rng": dict(_STAT_B), "wf_rng": dict(_STAT_B), "wf_lb": dict(_STAT_B)}


def _world(I0=I0):
    """-> (saved_doc, rebuilt_gv, full curves by line). The rebuilt block is what an exact
    replay returns: the same curves plus the tails the real helper cuts from them, and a
    couple of stat values that differ (the merge must never take those). I0 moves the door
    (the default is the module's 1,300 of 1,400)."""
    rng = np.random.default_rng(384)
    pnl = rng.normal(0.6, 30.0, N)
    keep_log, keep_et = rng.random(N) > 0.28, rng.random(N) > 0.07
    w_tier = rng.choice([0.5, 1.0, 2.0], N)
    w_lin = np.clip(1.0 + 4.0 * (rng.random(N) - 0.5), 0.25, 3.0)
    w_keel = np.clip(rng.normal(1.2, 0.3, N), 0.5, 2.0)
    per_trade = {("candidates", 0): np.where(keep_log, pnl, 0.0),
                 ("candidates", 1): np.where(keep_et, pnl, 0.0),
                 ("tilts", 0): pnl * w_tier,
                 ("tilts", 1): pnl * w_lin,
                 ("hybrids", 0): np.where(keep_log, pnl * w_lin, 0.0),
                 ("keel", None): pnl * w_keel,
                 ("chosen", None): np.where(keep_et, pnl, 0.0)}      # the crowned et@0.45 line

    gv = {"gates": ["logistic", "rf", "xgb", "tree", "et"], "thresholds": [0.45, 0.5, 0.55, 0.6],
          "n_candidates": 2, "lockbox_months": 12, "windows": 4, "min_kept": 50,
          "min_keep_frac": 0.1, "min_keep_applied": 380, "span": ["2010-06-07", "2026-06-30"],
          "lockbox_from": "2025-06-30", "wf_range": ["2016-10-12", "2025-06-30"],
          "ungated_pre": {"num_trades": I0, "total_pnl": float(pnl[:I0].sum()), "sharpe": 0.961},
          "ungated_lockbox": {"num_trades": N - I0, "total_pnl": float(pnl[I0:].sum()), "sharpe": 0.926},
          "ungated_full": {"num_trades": N, "total_pnl": float(pnl.sum())},
          "candidates": [_cand("logistic", 24711.750250000005, 2737), _cand("et", 26037.829312500042, 3552)],
          "tilts": [_tilt("tier", "0.5x under 45% | 1x 45-55% | 2x over 55%"),
                    _tilt("linear", "slides 0.25x to 3x, 1x at 50%")],
          "hybrids": [_hyb()], "keel": _keel(),
          "chosen": {"model": "et", "threshold": 0.45, "impl": "et", "pre": dict(_STAT_B)},
          "lockbox": None, "gate_earns_pre": False,
          "verdict": "UNGATED WINS PRE-LOCKBOX - no gate earns its keep; lockbox not opened",
          "selection_rule": "net_dollars_mar_floor_80_minkeep"}
    for (kind, i), x in per_trade.items():
        cf = np.cumsum(x)
        if kind == "chosen":
            gv["equity"] = {"cum_ungated": downsample_curve(np.cumsum(pnl)),
                            "cum_gated": downsample_curve(cf), "n": N}
            continue
        row = gv[kind] if i is None else gv[kind][i]
        row["equity"] = {"cum": downsample_curve(cf, cap=300, ndp=None), "n": N}
        row["lockbox"]["total_pnl"] = float(x[I0:].sum())
    champ = {"buf_atr": 0.9, "max_hold_bars": 9600, "tl_len": 178, "stop_mult": 0.9}
    doc = {"id": 384, "strategy": "ENGUQ_1M_ETH_R3_1_0.py", "instrument": "NQ", "timeframe": "1m",
           "data_source": "db_noadj_eth", "session": None, "cost_pts": 0.533, "multiplier": 20.0,
           "date_from": "2010-06-07", "date_to": "2026-06-30", "best_params": dict(champ),
           "gate_validate": gv,
           "validate": {"champion": dict(champ), "evolved_file": None,
                        "windows": {"wf_split": "2016-10-12", "optimize": ["2010-06-07", "2025-06-29"],
                                    "lockbox_months": 12, "lockbox": ["2025-06-30", "2026-06-30"]},
                        "gate_bakeoff": copy.deepcopy(gv),
                        "lockbox": {"trades": 277, "pnl": 3366.998843749967}},
           "equity": [float(v) for v in range(400)]}

    rebuilt = copy.deepcopy(gv)
    for (kind, i), x in per_trade.items():
        cf = np.cumsum(x)
        if kind == "chosen":
            rebuilt["equity"]["lb_tail_gated"] = lockbox_tail(cf, I0, 300, LB_TAIL_CAP, ndp=1)
            continue
        row = rebuilt[kind] if i is None else rebuilt[kind][i]
        row["equity"]["lb_tail"] = lockbox_tail(cf, I0, 300, LB_TAIL_CAP, None)
    rebuilt["candidates"][0]["pre_sharpe"] = 9.99            # a replay may drift in its stats;
    rebuilt["tilts"][1]["lockbox"]["sharpe"] = 9.99          #   the merge keeps the SAVED ones
    return doc, rebuilt, per_trade


@pytest.fixture
def world():
    return _world()


def _by_label(results):
    return {r["label"]: r for r in results}


# ─────────────────────────────────────────────────────────────────────────────
# exact replay -> every row merged
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_replay_merges_a_tail_onto_every_row(world):
    doc, rebuilt, per_trade = world
    gv = doc["gate_validate"]
    results = B.verify_rows(gv, rebuilt)
    assert [r["label"] for r in results] == [
        "gate logistic@0.45", "gate et@0.45", "tilt logistic/tier", "tilt logistic/linear",
        "hybrid logistic", "KEEL v12", "chosen gate et@0.45"]
    assert all(r["ok"] for r in results), [(r["label"], r["reason"]) for r in results]
    for r in results:
        t = r["tail"]
        assert t["i0"] == I0 and t["pts"] == 300 and len(t["cum"]) == LB_TAIL_CAP
        assert t["j0"] == B.expected_j0(N, 300, I0) and 1 <= t["j0"] <= 299
        json.dumps(t, allow_nan=False)
    merged = B.merge_tails(gv, results)
    payload = B.build_update(gv, results, merged, at="2026-09-13T12:00:00Z")
    assert set(payload) == set(B.PAYLOAD_KEYS)
    assert payload[B.STAMP_KEY] == {"version": B.TOOL_VERSION, "at": "2026-09-13T12:00:00Z",
                                    "rows_written": 7, "rows_skipped": 0, "rows_kept": 0}
    # each merged tail is exactly the one the real helper cuts from that row's full curve
    for (kind, i), x in per_trade.items():
        cf = np.cumsum(x)
        if kind == "chosen":
            assert payload["gate_validate.equity.lb_tail_gated"] == lockbox_tail(cf, I0, 300, LB_TAIL_CAP, ndp=1)
        elif kind == "keel":
            assert payload["gate_validate.keel.equity.lb_tail"] == lockbox_tail(cf, I0, 300, LB_TAIL_CAP)
        else:
            assert payload["gate_validate." + kind][i]["equity"]["lb_tail"] == \
                lockbox_tail(cf, I0, 300, LB_TAIL_CAP)
    # the funnel's stitch lands on the true per-trade cumulative
    t = payload["gate_validate.tilts"][1]["equity"]["lb_tail"]
    cf = np.cumsum(per_trade[("tilts", 1)])
    assert t["base"] == int(round(cf[I0 - 1])) and t["cum"][-1] == int(round(cf[-1]))
    assert abs(t["cum"][-1] - t["base"] - gv["tilts"][1]["lockbox"]["total_pnl"]) <= 1.0
    # and the replay's drifted stats never reach the doc
    assert payload["gate_validate.candidates"][0]["pre_sharpe"] == 0.935
    assert payload["gate_validate.tilts"][1]["lockbox"]["sharpe"] == 1.062
    assert B.summary_lines(results)[0] == \
        "rows: 7 of 7 verified (gates 2/2, tilts 2/2, hybrids 1/1, KEEL 1/1, chosen gate 1/1)"


# ─────────────────────────────────────────────────────────────────────────────
# one element off / span mismatch / broken tail -> that row skipped, the rest merged
# ─────────────────────────────────────────────────────────────────────────────

def test_one_curve_point_off_skips_only_that_row(world):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    rebuilt["candidates"][1]["equity"]["cum"][150] += 1
    rebuilt["equity"]["cum_gated"][10] = round(rebuilt["equity"]["cum_gated"][10] + 0.1, 1)
    results = B.verify_rows(gv, rebuilt)
    by = _by_label(results)
    assert not by["gate et@0.45"]["ok"]
    assert by["gate et@0.45"]["reason"].startswith("replayed curve differs at point 150")
    assert not by["chosen gate et@0.45"]["ok"]
    assert by["chosen gate et@0.45"]["reason"].startswith("replayed curve differs at point 10")
    assert sum(r["ok"] for r in results) == 5
    payload = B.build_update(gv, results, B.merge_tails(gv, results), at="x")
    cands = payload["gate_validate.candidates"]
    assert "lb_tail" in cands[0]["equity"] and "lb_tail" not in cands[1]["equity"]
    assert cands[1] == gv["candidates"][1]                  # the skipped row is the saved row
    assert "gate_validate.equity.lb_tail_gated" not in payload
    assert payload[B.STAMP_KEY]["rows_written"] == 5 and payload[B.STAMP_KEY]["rows_skipped"] == 2
    assert any(ln.startswith("  SKIP gate et@0.45: replayed curve differs") for ln in B.summary_lines(results))


@pytest.mark.parametrize("where,delta,ok", [
    ("saved_total", 2.0, False),      # the saved lockbox total disagrees with the tail's span
    ("saved_total", -1.6, False),
    ("saved_total", 1.4, True),       # whole-point rounding at both ends is tolerated
    ("saved_total", -1.4, True),
    ("tail_base", 3.0, False),        # the replayed tail starts from the wrong value
])
def test_tail_span_mismatch_skips_that_row(world, where, delta, ok):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    t = rebuilt["tilts"][1]["equity"]["lb_tail"]
    if where == "saved_total":           # measured from the tail's own span, so the edge is exact
        gv["tilts"][1]["lockbox"]["total_pnl"] = float(t["cum"][-1] - t["base"]) + delta
    else:                                # the true total sits within 1 of the span; 3 is out
        t["base"] += delta
    by = _by_label(B.verify_rows(gv, rebuilt))
    assert by["tilt logistic/linear"]["ok"] is ok
    if not ok:
        assert by["tilt logistic/linear"]["reason"].startswith("tail span")
    assert all(r["ok"] for lbl, r in by.items() if lbl != "tilt logistic/linear")


def _kept_pre_tail(per_trade):
    """The web's once-shipped bug, replayed: door at the hybrid's own kept_pre, still
    claiming the ungated count."""
    cf = np.cumsum(per_trade[("hybrids", 0)])
    # density rule off: an early door leaves more saved points past it, and the engine would
    #   refuse that tail on density alone - here the door itself must be what gets it skipped
    t = lockbox_tail(cf, 1000, 300, LB_TAIL_CAP, only_if_denser=False)
    return dict(t, i0=I0)


@pytest.mark.parametrize("mutate,expect", [
    (lambda eq, pt: eq["lb_tail"].update(i0=I0 - 1), "tail door i0"),
    (lambda eq, pt: eq["lb_tail"].update(pts=299), "tail was cut for 299"),
    (lambda eq, pt: eq["lb_tail"].update(j0=eq["lb_tail"]["j0"] + 1), "does not match the saved curve's index rule"),
    (lambda eq, pt: eq["lb_tail"]["cum"].__setitem__(-1, eq["lb_tail"]["cum"][-1] + 1), "tail ends at"),
    (lambda eq, pt: eq["lb_tail"].update(v=2), "unknown tail format"),
    (lambda eq, pt: eq["lb_tail"].update(cum=[]), "tail values"),
    (lambda eq, pt: eq["lb_tail"]["cum"].__setitem__(3, float("nan")), "tail values"),
    (lambda eq, pt: eq["lb_tail"].update(cum=list(range(N - I0 + 1))), "tail values"),
    (lambda eq, pt: eq.pop("lb_tail"), "the replay made no tail"),
    (lambda eq, pt: eq.update(n=N + 1), "trade count n differs"),
    (lambda eq, pt: eq.update(lb_tail=_kept_pre_tail(pt)), "index rule"),
])
def test_a_wrong_tail_is_skipped_and_named(world, mutate, expect):
    doc, rebuilt, per_trade = world
    mutate(rebuilt["hybrids"][0]["equity"], per_trade)
    results = B.verify_rows(doc["gate_validate"], rebuilt)
    by = _by_label(results)
    assert not by["hybrid logistic"]["ok"]
    assert expect in by["hybrid logistic"]["reason"], by["hybrid logistic"]["reason"]
    assert sum(r["ok"] for r in results) == 6


def test_ambiguous_missing_and_mismatched_rows_are_skipped_not_guessed(world):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    gv["hybrids"].append(copy.deepcopy(gv["hybrids"][0]))          # two saved "hybrid logistic"
    rebuilt["tilts"] = rebuilt["tilts"][:1]                          # the replay lost one tilt
    rebuilt["keel"] = {"error": "ValueError: boom"}
    rebuilt["chosen"] = dict(rebuilt["chosen"], model="rf")         # the replay crowned another gate
    by = _by_label(B.verify_rows(gv, rebuilt))
    assert by["hybrid logistic"]["reason"].startswith("ambiguous")
    assert by["tilt logistic/linear"]["reason"] == "the replay made no such row"
    assert by["KEEL v12"]["reason"].startswith("the replay's KEEL row failed")
    assert by["chosen gate et@0.45"]["reason"] == "the replay crowned rf@0.45, the doc crowned et@0.45"
    assert [lbl for lbl, r in by.items() if r["ok"]] == ["gate logistic@0.45", "gate et@0.45", "tilt logistic/tier"]
    rebuilt2 = copy.deepcopy(_world()[1])
    rebuilt2["keel"]["version"] = "v13"
    assert B.verify_rows(_world()[0]["gate_validate"], rebuilt2)[5]["reason"] == \
        "the replay ran KEEL v13, the doc saved v12"


# ─────────────────────────────────────────────────────────────────────────────
# saved rows untouched; payload carries only tails
# ─────────────────────────────────────────────────────────────────────────────

def test_saved_doc_is_never_mutated_and_merged_rows_are_deep_copies(world):
    doc, rebuilt, _ = world
    before = copy.deepcopy(doc)
    gv = doc["gate_validate"]
    results = B.verify_rows(gv, rebuilt)
    merged = B.merge_tails(gv, results)
    payload = B.build_update(gv, results, merged, at="x")
    projected = B.apply_update(doc, payload)
    B.size_check(projected, size_fn=lambda d: 1, budget=10)
    assert doc == before
    assert "lb_tail" not in json.dumps(doc)
    for kind in B.ROW_KINDS:
        for m, s in zip(merged[kind], gv[kind]):
            assert m is not s and m["equity"] is not s["equity"]
            for k, v in s.items():
                if isinstance(v, (dict, list)):
                    assert m[k] is not v                     # no shared containers either
    merged["candidates"][0]["lockbox"]["total_pnl"] = -1.0   # editing a copy leaves the doc alone
    merged["keel_tail"]["cum"].append(123)
    assert doc == before and projected["gate_validate"]["keel"]["equity"]["lb_tail"]["cum"][-1] != 123


def test_payload_never_touches_gate_bakeoff_stat_blocks_or_saved_curves(world):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    results = B.verify_rows(gv, rebuilt)
    payload = B.build_update(gv, results, B.merge_tails(gv, results), at="x")
    assert all(k.startswith("gate_validate.") for k in payload)
    assert "gate_bakeoff" not in json.dumps(payload)
    assert not any(k.startswith("validate") for k in payload)
    projected = B.apply_update(doc, payload)
    # remove the tails (and the stamp) and the doc is byte-for-byte the saved one
    assert json.dumps(strip_lb_tails(projected["gate_validate"]), sort_keys=True) == \
        json.dumps(gv, sort_keys=True)
    assert {k: v for k, v in projected.items() if k != "gate_validate"} == \
        {k: v for k, v in doc.items() if k != "gate_validate"}
    assert "lb_tail" not in json.dumps(projected["validate"])
    assert projected["gate_validate"]["lb_tail_backfill"]["rows_written"] == 7

    # the guard refuses anything wider than tails
    def refused(p):
        with pytest.raises(ValueError):
            B.check_payload(gv, p)

    refused(dict(payload, **{"validate.gate_bakeoff": strip_lb_tails(gv)}))
    refused(dict(payload, **{"gate_validate.ungated_lockbox": gv["ungated_lockbox"]}))
    refused(dict(payload, **{"gate_validate.equity": dict(gv["equity"])}))
    _good_tail = payload["gate_validate.keel.equity.lb_tail"]            # well-formed, wrong place
    refused(dict(payload, **{"validate.gate_bakeoff.equity.lb_tail_gated": _good_tail}))
    refused(dict(payload, **{"gate_validate.ungated_pre": _good_tail}))
    for mutate in (lambda rows: rows[0]["lockbox"].update(total_pnl=1.0),      # a stat block
                   lambda rows: rows[1]["equity"]["cum"].__setitem__(0, 7),   # a saved curve
                   lambda rows: rows[0].update(pre_sharpe=9.99),              # a scalar stat
                   lambda rows: rows.append(copy.deepcopy(rows[0])),          # an extra row
                   lambda rows: rows[0]["equity"]["lb_tail"].update(cum=[float("nan")])):
        p = copy.deepcopy(payload)
        mutate(p["gate_validate.candidates"])
        refused(p)
    refused({k: v for k, v in payload.items() if k != B.STAMP_KEY})
    refused(dict(payload, **{B.STAMP_KEY: dict(payload[B.STAMP_KEY], extra=1)}))
    refused(dict(payload, **{"gate_validate.keel.equity.lb_tail": {"v": 1, "cum": [1]}}))
    assert B.check_payload(gv, payload) is True
    assert B.build_update(gv, [dict(r, ok=False, tail=None) for r in results], {}, at="x") == {}


# ─────────────────────────────────────────────────────────────────────────────
# size guard = the runner's own
# ─────────────────────────────────────────────────────────────────────────────

def test_size_refusal_uses_the_runners_own_guard(world):
    import api.runner as R
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    results = B.verify_rows(gv, rebuilt)
    payload = B.build_update(gv, results, B.merge_tails(gv, results), at="x")
    fits, n, cap = B.size_check(B.apply_update(doc, payload))
    assert fits and cap == R.DOC_SIZE_BUDGET and n == R._doc_size(B.apply_update(doc, payload))
    assert n - R._doc_size(doc) > 1500                           # the tails do add bytes
    big = dict(copy.deepcopy(doc), junk="x" * (R.DOC_SIZE_BUDGET - R._doc_size(doc) - 1500))
    assert B.size_check(big)[0]                                   # fits before the tails...
    fits, n, cap = B.size_check(B.apply_update(big, payload))
    assert not fits and n > cap == R.DOC_SIZE_BUDGET              # ...and is refused after them
    assert B.size_check(doc, size_fn=lambda d: 0, budget=10**9)[0] is False   # unmeasurable


# ─────────────────────────────────────────────────────────────────────────────
# reproduction guard, window pinning, --list
# ─────────────────────────────────────────────────────────────────────────────

def test_reproduction_guard(world):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    assert B.check_reproduction(gv, rebuilt)[0]
    tot = gv["ungated_pre"]["total_pnl"]
    for blk, field, value, ok in (
            ("ungated_pre", "num_trades", I0 + 1, False),
            ("ungated_lockbox", "num_trades", N - I0 - 1, False),
            ("ungated_pre", "total_pnl", tot * 1.006, False),
            ("ungated_pre", "total_pnl", tot * 1.004, True)):
        r = copy.deepcopy(rebuilt)
        r[blk][field] = value
        good, lines = B.check_reproduction(gv, r)
        assert good is ok, lines
        assert any("MISMATCH" in ln for ln in lines) is (not ok)
    assert not B.check_reproduction(gv, dict(rebuilt, lockbox_from="2025-07-01"))[0]
    assert not B.check_reproduction(gv, None)[0]
    plan, _ = B.rebuild_plan(doc)
    trades = [(i, i + 1, float(p)) for i, p in enumerate([1.0] * N)]
    plan2 = dict(plan, expect_net=float(N))
    assert B.check_trade_book(plan2, trades)[0]
    assert not B.check_trade_book(plan2, trades[:-1])[0]


def test_rebuild_plan_pins_the_window_and_uses_the_docs_own_settings(world):
    doc, _, _ = world
    plan, why = B.rebuild_plan(doc)
    assert why is None
    assert (plan["date_from"], plan["date_to"]) == ("2010-06-07", "2026-06-30")
    assert (plan["session"], plan["source"], plan["cost_pts"]) == ("eth", "db_noadj_eth", 0.533)
    assert plan["params"] == doc["validate"]["champion"]
    assert plan["expect_n"] == N
    assert plan["kwargs"] == {"lb_from": "2025-06-30", "wf_from": "2016-10-12", "wf_to": "2025-06-30",
                              "keel": True, "keel_version": "v12",
                              "gates": ("logistic", "rf", "xgb", "tree", "et"),
                              "thresholds": (0.45, 0.5, 0.55, 0.6), "lockbox_months": 12,
                              "min_kept": 50, "min_keep_frac": 0.1, "windows": 4}
    # the optimize start wins over date_from; a blank end pins to the recorded lockbox end
    d = copy.deepcopy(doc)
    d["date_from"], d["date_to"] = "2011-01-01", None
    assert (B.rebuild_plan(d)[0]["date_from"], B.rebuild_plan(d)[0]["date_to"]) == ("2010-06-07", "2026-06-30")
    d["validate"]["windows"] = {}
    assert B.rebuild_plan(d)[0] is None and "window" in B.rebuild_plan(d)[1]
    d = copy.deepcopy(doc)
    d["gate_validate"]["keel"] = {"error": "boom"}
    assert (B.rebuild_plan(d)[0]["kwargs"]["keel"], B.rebuild_plan(d)[0]["kwargs"]["keel_version"]) == (False, None)
    for edit, reason in ((lambda x: x.update(data_source="tv"), "unknown data_source"),
                         (lambda x: x["validate"].update(evolved_file="evo.py"), "AI-evolved"),
                         (lambda x: x.pop("gate_validate"), "no gate_validate"),
                         (lambda x: (x["validate"].pop("champion"), x.pop("best_params")), "no champion")):
        d = copy.deepcopy(doc)
        edit(d)
        plan, why = B.rebuild_plan(d)
        assert plan is None and reason in why


def test_existing_tails_and_list_rows(world):
    doc, rebuilt, _ = world
    assert B.existing_tails(doc["gate_validate"]) == (0, None)
    assert B.existing_tails(rebuilt) == (7, None)
    line = B.list_row(RUN, doc)
    assert line.startswith("#384 ENGUQ_1M_ETH_R3_1_0.py NQ 1m 2010-06-07..2026-06-30 | pre 1300 LB 100")
    assert line.endswith("KEEL v12 | no KEEL/gate tail (other rows not read here)")
    masked = {"strategy": "S", "gate_validate": {"ungated_pre": {"num_trades": 5},
                                                 "lb_tail_backfill": {"at": "T", "rows_written": 37,
                                                                      "rows_skipped": 0}}}
    assert B.list_row("9", masked).endswith("backfilled T (37 rows, 0 skipped)")
    assert B.list_row("9", {"strategy": "S"}) is None


# ─────────────────────────────────────────────────────────────────────────────
# orchestration on a fake Firestore (no network, no market data)
# ─────────────────────────────────────────────────────────────────────────────

class FailedPrecondition(Exception):
    pass


class _Snap:
    def __init__(self, doc, t):
        self._d, self.exists, self.update_time = copy.deepcopy(doc), doc is not None, t

    def to_dict(self):
        return copy.deepcopy(self._d)


class ServiceUnavailable(Exception):
    pass


class _Ref:
    def __init__(self, *reads):
        self.reads, self.gets, self.updates, self.fail = list(reads), 0, [], None
        self.land_then_fail, self.retries = None, []

    def get(self):
        doc, t = self.reads[min(self.gets, len(self.reads) - 1)]
        self.gets += 1
        return _Snap(doc, t)

    def update(self, payload, option=None, retry="DEFAULT"):
        self.retries.append(retry)
        if self.land_then_fail is not None:
            # the server applied the commit, then the reply was lost
            doc, _t = self.reads[-1]
            self.reads.append((B.apply_update(doc, payload), "t-after"))
            self.updates.append((copy.deepcopy(payload), option))
            raise self.land_then_fail
        if self.fail is not None:
            raise self.fail
        self.updates.append((copy.deepcopy(payload), option))


class _DB:
    def __init__(self, ref):
        self.ref = ref

    def collection(self, name):
        return self

    def document(self, name):
        return self.ref if name == RUN else self

    def write_option(self, **kw):
        return ("precondition", kw)


def _run(ref, rebuilt, **kw):
    log = []
    status = B.one(_DB(ref), int(RUN), rebuild=lambda plan: copy.deepcopy(rebuilt), log=log.append,
                   at="2026-09-13T12:00:00Z", **kw)
    return status, log


def test_one_dry_run_writes_nothing(world):
    doc, rebuilt, _ = world
    ref = _Ref((doc, "t1"))
    status, log = _run(ref, rebuilt)
    assert status == "dry" and ref.updates == [] and ref.gets == 1
    text = "\n".join(log)
    assert "window 2010-06-07..2026-06-30 (pinned)" in text
    assert "rows: 7 of 7 verified" in text and "dry run - not written" in text


def test_one_write_uses_a_precondition_on_a_fresh_read(world):
    doc, rebuilt, _ = world
    ref = _Ref((doc, "t1"), (dict(doc, archived=True), "t2"))     # an unrelated field changed
    status, log = _run(ref, rebuilt, write=True)
    assert status == "written", log
    assert len(ref.updates) == 1
    payload, option = ref.updates[0]
    assert option == ("precondition", {"last_update_time": "t2"})
    assert ref.retries == [None]              # one attempt: a blind re-send would trip its own precondition
    assert set(payload) == set(B.PAYLOAD_KEYS)
    assert payload[B.STAMP_KEY]["at"] == "2026-09-13T12:00:00Z"


def test_one_refuses_changed_conflicting_oversized_mismatched_or_tailed_docs(world):
    doc, rebuilt, _ = world
    changed = copy.deepcopy(doc)
    changed["gate_validate"]["verdict"] = "re-validated"
    ref = _Ref((doc, "t1"), (changed, "t2"))
    assert _run(ref, rebuilt, write=True)[0] == "changed" and ref.updates == []

    ref = _Ref((doc, "t1"))
    ref.fail = FailedPrecondition("stale")
    assert _run(ref, rebuilt, write=True)[0] == "conflict"

    ref = _Ref((doc, "t1"))
    assert _run(ref, rebuilt, write=True, budget=10_000)[0] == "toobig" and ref.updates == []

    bad = copy.deepcopy(rebuilt)
    bad["ungated_pre"]["num_trades"] += 1
    ref = _Ref((doc, "t1"))
    assert _run(ref, bad, write=True)[0] == "mismatch" and ref.updates == []

    tailed = copy.deepcopy(doc)
    tailed["gate_validate"] = copy.deepcopy(rebuilt)
    ref = _Ref((tailed, "t1"))
    status, log = _run(ref, rebuilt, write=True)
    assert status == "covered" and "pass --force" in log[-1] and ref.updates == []

    none_ok = copy.deepcopy(rebuilt)
    for k in B.ROW_KINDS:
        for r in none_ok[k]:
            r["equity"].pop("lb_tail")
    none_ok["keel"]["equity"].pop("lb_tail")
    none_ok["equity"].pop("lb_tail_gated")
    ref = _Ref((doc, "t1"))
    assert _run(ref, none_ok, write=True)[0] == "nothing" and ref.updates == []

    def _no_master(plan):
        raise B.ReplaySkip("no master for NQ 1m eth db_noadj_eth")
    ref = _Ref((doc, "t1"))
    assert B.one(_DB(ref), int(RUN), write=True, rebuild=_no_master, log=[].append) == "skip"
    assert ref.updates == []


def test_force_rebuilds_a_run_that_already_has_tails(world):
    doc, rebuilt, _ = world
    tailed = copy.deepcopy(doc)
    tailed["gate_validate"]["equity"]["lb_tail_gated"] = copy.deepcopy(rebuilt["equity"]["lb_tail_gated"])
    ref = _Ref((tailed, "t1"), (tailed, "t2"))
    status, _ = _run(ref, rebuilt, write=True, force=True)
    assert status == "written" and len(ref.updates) == 1


def test_help_and_no_arguments_never_touch_firestore(monkeypatch):
    def _boom():
        raise AssertionError("Firestore opened")
    monkeypatch.setattr(B, "_db", _boom)
    assert B.main([]) == 2
    with pytest.raises(SystemExit) as e:
        B.main(["--help"])
    assert e.value.code == 0
    out = subprocess.run([sys.executable, os.path.join(_TOOLS, "backfill_lb_tails.py"), "--help"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--write" in out.stdout and "--list" in out.stdout


# ─────────────────────────────────────────────────────────────────────────────
# review fixes (2026-09-13): per-line coverage, stricter payload guard, lost replies,
# exit codes, the density rule and the j0 = pts-1 door
# ─────────────────────────────────────────────────────────────────────────────

def _keel_only(doc, rebuilt):
    """What tools/backfill_keel.py leaves after the engine ships: the KEEL row carries a tail,
    nothing else does, and there is no backfill stamp."""
    d = copy.deepcopy(doc)
    d["gate_validate"]["keel"]["equity"]["lb_tail"] = copy.deepcopy(rebuilt["keel"]["equity"]["lb_tail"])
    return d


def test_a_keel_only_tail_does_not_block_the_other_lines(world):
    doc, rebuilt, _ = world
    d = _keel_only(doc, rebuilt)
    cov = B.tail_coverage(d["gate_validate"])
    assert cov["have"] == ["KEEL v12"] and len(cov["missing"]) == 6 and cov["stamp"] is None
    ref = _Ref((d, "t1"), (d, "t2"))
    status, log = _run(ref, rebuilt, write=True)
    assert status == "written", log
    payload, _opt = ref.updates[0]
    # the six lines without a tail get one; the KEEL row's own tail is left exactly as saved
    assert "gate_validate.keel.equity.lb_tail" not in payload
    assert payload[B.STAMP_KEY]["rows_written"] == 6 and payload[B.STAMP_KEY]["rows_kept"] == 1
    assert "1 line(s) already carry a tail and stay as saved; 6 line(s) lack one" in "\n".join(log)
    assert all("lb_tail" in r["equity"] for k in B.ROW_KINDS for r in payload["gate_validate." + k])
    # --list no longer calls such a run covered
    assert "other rows not read here" in B.list_row(RUN, d)
    assert "has tails" not in B.list_row(RUN, d)


def test_row_only_tails_fill_the_keel_and_the_chosen_gate(world):
    doc, rebuilt, _ = world
    d = copy.deepcopy(doc)
    for k in B.ROW_KINDS:
        for r, rr in zip(d["gate_validate"][k], rebuilt[k]):
            r["equity"]["lb_tail"] = copy.deepcopy(rr["equity"]["lb_tail"])
    assert B.list_row(RUN, d).endswith("no KEEL/gate tail (other rows not read here)")
    ref = _Ref((d, "t1"), (d, "t2"))
    status, log = _run(ref, rebuilt, write=True)
    assert status == "written", log
    payload, _opt = ref.updates[0]
    assert set(payload) == {"gate_validate.keel.equity.lb_tail", "gate_validate.equity.lb_tail_gated",
                            B.STAMP_KEY}
    assert payload[B.STAMP_KEY]["rows_kept"] == 5


def test_covered_stamped_and_hopeless_runs_skip_the_replay(world):
    doc, rebuilt, _ = world

    def _never(plan):
        raise AssertionError("replayed a run that needed no replay")
    stamped = copy.deepcopy(doc)
    stamped["gate_validate"]["lb_tail_backfill"] = {"version": "v1", "at": "T", "rows_written": 3,
                                                    "rows_skipped": 4, "rows_kept": 0}
    log = []
    assert B.one(_DB(_Ref((stamped, "t1"))), int(RUN), write=True, rebuild=_never, log=log.append) == "covered"
    assert "pass --force" in log[-1]
    # a run whose lockbox is 60% of its trades: the saved curves already out-draw any tail
    short, _r, _p = _world(I0=560)
    assert B.tail_coverage(short["gate_validate"])["missing"] == []
    assert B.one(_DB(_Ref((short, "t1"))), int(RUN), write=True, rebuild=_never, log=[].append) == "nothing"
    # --force still rebuilds a stamped run
    ref = _Ref((stamped, "t1"), (stamped, "t2"))
    assert _run(ref, rebuilt, write=True, force=True)[0] == "written"


def test_existing_tails_count_only_well_formed_tails(world):
    doc, rebuilt, _ = world
    gv = copy.deepcopy(doc["gate_validate"])
    gv["candidates"][0]["equity"]["lb_tail"] = None
    gv["tilts"][0]["equity"]["lb_tail"] = "junk"
    gv["keel"]["equity"]["lb_tail_x"] = copy.deepcopy(rebuilt["keel"]["equity"]["lb_tail"])  # wrong key
    assert B.existing_tails(gv) == (0, None)
    cov = B.tail_coverage(gv)
    assert cov["have"] == [] and len(cov["missing"]) == 7


def test_check_payload_refuses_null_foreign_and_row_level_tail_keys(world):
    doc, rebuilt, _ = world
    gv = doc["gate_validate"]
    results = B.verify_rows(gv, rebuilt)
    payload = B.build_update(gv, results, B.merge_tails(gv, results), at="x")
    good = payload["gate_validate.keel.equity.lb_tail"]
    for mutate in (lambda rows: rows[0]["equity"].update(lb_tail=None),
                   lambda rows: rows[0]["equity"].update(lb_tail_gated={"cum": "junk"}),
                   lambda rows: rows[0].update(lb_tail="x" * 1000),
                   lambda rows: rows[1]["equity"].update(lb_tail_x=list(range(50000))),
                   lambda rows: rows[1]["equity"].update(lb_tail_gated=copy.deepcopy(good)),
                   lambda rows: rows[0]["equity"].update(lb_tail=dict(good, cum=[]))):
        p = copy.deepcopy(payload)
        mutate(p["gate_validate.candidates"])
        with pytest.raises(ValueError):
            B.check_payload(gv, p)
    # a tail the SAVED row already carries passes through unchanged, even one the funnel ignores
    saved = copy.deepcopy(gv)
    saved["candidates"][0]["equity"]["lb_tail"] = None
    p = copy.deepcopy(payload)
    p["gate_validate.candidates"][0]["equity"]["lb_tail"] = None
    assert B.check_payload(saved, p) is True


def test_a_lost_reply_on_a_landed_write_is_reported_as_written(world):
    doc, rebuilt, _ = world
    ref = _Ref((doc, "t1"), (doc, "t2"))
    ref.land_then_fail = FailedPrecondition("the client's own retry tripped the precondition")
    status, log = _run(ref, rebuilt, write=True)
    assert status == "written", log
    assert "the reply was lost, the write landed" in "\n".join(log)
    # a transient error that did NOT land is not a conflict and not a success: it raises
    ref = _Ref((doc, "t1"), (doc, "t2"))
    ref.fail = ServiceUnavailable("503")
    with pytest.raises(ServiceUnavailable):
        _run(ref, rebuilt, write=True)
    # and a real concurrent change is still a conflict
    ref = _Ref((doc, "t1"), (doc, "t2"))
    ref.fail = FailedPrecondition("stale")
    assert _run(ref, rebuilt, write=True)[0] == "conflict"


def test_main_exit_code_reflects_refusals(monkeypatch):
    monkeypatch.setattr(B, "_db", lambda: object())
    seen = {}

    def _one(db, rid, write=False, force=False):
        seen[rid] = (write, force)
        if rid == 999:
            raise RuntimeError("boom")
        return {384: "written", 385: "dry", 386: "covered", 387: "nothing", 310: "mismatch",
                311: "conflict", 312: "toobig", 313: "changed", 314: "skip", 315: "nodoc"}[rid]
    monkeypatch.setattr(B, "one", _one)
    assert B.main(["384", "385", "386", "387", "--write"]) == 0
    for bad in ("310", "311", "312", "313", "314", "315", "999"):
        assert B.main(["384", bad]) == 1, bad
    assert seen[384] == (False, False)


def test_a_tail_that_adds_no_points_is_skipped(world):
    doc, rebuilt, per_trade = world
    cf = np.cumsum(per_trade[("tilts", 0)])
    # 20 points at a door with 21 saved points past it: the stitch would not add a point
    thin = lockbox_tail(cf, I0, 300, 20, None, only_if_denser=False)
    assert 300 - thin["j0"] == 21
    rebuilt["tilts"][0]["equity"]["lb_tail"] = thin
    by = _by_label(B.verify_rows(doc["gate_validate"], rebuilt))
    assert not by["tilt logistic/tier"]["ok"] and "adds none" in by["tilt logistic/tier"]["reason"]
    assert sum(r["ok"] for r in by.values()) == 6


def test_a_tiny_lockbox_door_at_the_last_saved_point_verifies():
    doc, rebuilt, _ = _world(I0=1396)          # 4 lockbox trades: only the final saved point is past the door
    results = B.verify_rows(doc["gate_validate"], rebuilt)
    assert all(r["ok"] for r in results), [(r["label"], r["reason"]) for r in results]
    assert {r["tail"]["j0"] for r in results} == {299} and {len(r["tail"]["cum"]) for r in results} == {4}


# ─────────────────────────────────────────────────────────────────────────────
# the real engine's output shape passes the matcher
# ─────────────────────────────────────────────────────────────────────────────

def test_real_gate_validate_output_verifies_against_its_tail_free_twin():
    import augur_engine.ml_gate as G
    rng = np.random.default_rng(7)
    idx = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                        pd.Timestamp("2020-01-21", tz="US/Eastern"), freq="5min", tz="US/Eastern")
    n = len(idx)
    close = 1000.0 + np.cumsum(rng.normal(0, 1.0, n))
    arrays = {"open": close.copy(), "high": close + 1.0, "low": close - 1.0, "close": close.copy(),
              "volume": np.full(n, 1000.0),
              "day_id": pd.factorize(pd.Series(idx).dt.date)[0].astype("int64"), "index": idx}
    trades = [(int(e), int(e) + 6, float(rng.normal(0.5, 10.0))) for e in np.arange(50, n - 10, 14)]
    out = G.gate_validate(arrays, trades, gates=("logistic",), thresholds=(0.5,), min_kept=1,
                          min_keep_frac=0.0, lb_from="2020-01-16", keel=False)
    assert out is not None and out["chosen"] is not None
    saved = json.loads(json.dumps(strip_lb_tails(out), default=str))    # a pre-tail doc, via JSON
    results = B.verify_rows(saved, out)
    assert len(results) == 1 + 2 + 1 + 1                                  # gate, 2 tilts, hybrid, chosen
    assert all(r["ok"] for r in results), [(r["label"], r["reason"]) for r in results]
    assert B.check_reproduction(saved, out)[0]
    payload = B.build_update(saved, results, B.merge_tails(saved, results), at="x")
    assert set(payload) == set(B.PAYLOAD_KEYS) - {"gate_validate.keel.equity.lb_tail"}

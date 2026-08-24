"""ML gate for the PAPER forward-test legs — the "bouncer" and the "bouncer + size dial".

WHY THIS FILE EXISTS (2026-08-16, owner: "build the gate. specifically for noise hybrid
or the top ml"). Until now api/paper.py ran RAW configs only: it called run_backtest with
a plain params dict and logged whatever came back. Every ML result the project has ever
produced lived in the OPTIMIZE/VALIDATE path (augur_engine/ml_gate.py, surfaced in a run's
`gate_validate` block) and none of it was ever forward-tested. That is the gap this closes.

WHAT A GATE IS, in plain terms. The strategy picks its trades exactly as it always has.
A second model then looks at each trade the moment it fires, scores its chance of making
money from conditions that were already known at that instant, and either:

  • CUT mode    — refuses trades scoring under the cut-off ("the bouncer"); or
  • HYBRID mode — refuses trades under the cut-off AND sizes the survivors by score:
                  low scores trade smaller, high scores trade bigger ("the size dial"); or
  • TILT mode   — refuses NOTHING. Every trade is taken, only the SIZE moves with the
                  score ("the size tilt", added 2026-08-24). Two a-priori schemes, lifted
                  verbatim from ml_gate.gate_validate's tilt rows: "tier" (0.5x under 45%,
                  1x from 45 to 55%, 2x over 55%) and "linear" (slides 0.25x to 3x, 1x at
                  50%). Warm-up trades size 1.0. Normalised by the frozen size_norm (the
                  mean weight over the source run's pre-lockbox trades) and capped at 3x,
                  exactly the report's mean_weight_matched_pre_lockbox_cap3 rule. A tilt
                  has no cut-off and never uses the recycle factor -- it skips nothing, so
                  there is no freed capital to respend.

The base strategy file is never touched, which is the whole appeal: a gate is an overlay
you can switch off.

THE LEAK RULE, which is the entire reason this is safe. The model is only ever trained on
trades that had already FINISHED before the current trade's entry bar — outcomes that were
genuinely known at the time. Until `min_history` trades have completed the gate is off duty
and trades pass through untouched. That discipline lives in augur_engine.ml_gate.gate_trades
and this module deliberately does not reimplement it; it calls that function with
threshold=0.0 (a pure scoring pass that keeps everything) and then applies the cut-off and
the size dial to the returned scores. That is byte-for-byte how gate_validate builds its own
candidate and hybrid rows, so a paper leg and the run that crowned it are computing the same
thing rather than two things that merely resemble each other.

THE ONE PLACE PAPER DIFFERS FROM THE BACKTEST, stated plainly because it matters:
gate_validate normalises hybrid sizes by the MEAN weight over its pre-lockbox survivors, so
the row carries the same average size as the ungated baseline. A forward test cannot compute
that mean -- the mean of a window that includes the future is exactly the kind of hindsight
this project spends its time hunting. So `size_norm` is a FROZEN CONSTANT, calibrated once
against the source run's own window by tools/paper_gate_calibrate.py and pinned in the leg
config next to the params. Same discipline as the params themselves: measured once, written
down, never recomputed from data the leg has not lived through.
"""
import numpy as np

__all__ = ["apply_gate", "score_trades", "GATE_DEFAULTS"]

# Shared defaults. These match augur_engine.ml_gate.gate_trades' own signature, so a leg
# config that omits them behaves identically to the validate run that crowned it.
GATE_DEFAULTS = {"min_history": 30, "refit_every": 25, "seed": 42, "size_norm": 1.0,
                 "recycle_factor": 1.0}

# The hybrid size curve, lifted verbatim from ml_gate.gate_validate's hybrid block:
# 1x at a 50% score, sliding to 0.25x at the bottom and 3x at the top. Not fitted -- an
# a-priori shape, which is the only reason it is defensible to carry forward.
_TILT_SLOPE = 4.0
_TILT_LO, _TILT_HI = 0.25, 3.0
_SIZE_CAP = 3.0


def _tilt_weights(prob, warm, scheme):
    """Raw (pre-normalisation) tilt weights for TILT mode, matching ml_gate.gate_validate's
    _tilt_schemes byte-for-byte: tier = 0.5x under 45% / 1x 45-55% / 2x over 55%; linear =
    the same slide the hybrid uses. Warm-up (NaN score) trades weigh 1.0."""
    p = np.where(warm, 0.5, prob)
    if str(scheme) == "tier":
        w = np.where(p >= 0.55, 2.0, np.where(p >= 0.45, 1.0, 0.5))
    else:
        w = np.clip(1.0 + _TILT_SLOPE * (p - 0.50), _TILT_LO, _TILT_HI)
    return np.where(warm, 1.0, w)


def _cfg(gate, key):
    v = (gate or {}).get(key)
    return GATE_DEFAULTS[key] if v is None else v


def _sorted_order(trades):
    """Indices that sort trades by ENTRY bar. ml_gate.gate_trades sorts its own copy the
    same way with the same stable sort, so scores come back aligned to THIS order --
    which is what lets us map them onto the full (entry, exit, pnl, side, price) tuples
    instead of the 3-tuples gate_trades hands back."""
    return sorted(range(len(trades)), key=lambda i: int(trades[i][0]))


def score_trades(arrays, trades, gate):
    """Win-probability per trade, in entry-bar order. None if the gate could not run.

    threshold=0.0 keeps every trade, so this is a pure scoring pass -- no decision is
    made here. The cut-off is applied by apply_gate below, exactly as gate_validate
    sweeps its own thresholds over one set of scores.
    """
    if not trades:
        return None
    from augur_engine.ml_gate import gate_trades
    g = gate_trades(arrays, trades, model=str(gate["model"]), threshold=0.0,
                    min_history=int(_cfg(gate, "min_history")),
                    refit_every=int(_cfg(gate, "refit_every")),
                    seed=int(_cfg(gate, "seed")))
    if not g or g.get("prob") is None:
        return None
    prob = np.asarray(g["prob"], float)
    if len(prob) != len(trades):
        return None
    return prob


def apply_gate(arrays, trades, gate):
    """Run one leg's gate over its raw trade list.

    trades : the engine's NET trade tuples (entry_bar, exit_bar, pnl_pts, side, entry_px)
             -- net because the gate must learn which trades win AFTER costs, not before.
    gate   : {"mode": "cut"|"hybrid", "model": ..., "threshold": float, "size_norm": float,
              ...}

    Returns (kept, info) where `kept` is a list of (trade_tuple, size_multiplier) for the
    trades that survived, and `info` is a json-safe summary for the daily report. Falls
    back to "every trade, size 1.0" with a warning in `info` if the gate could not run --
    a gate that fails must degrade to the ungated leg, never to an empty day that looks
    like a quiet market.
    """
    raw = list(trades or [])
    if not raw:
        return [], {"ok": True, "n_in": 0, "n_kept": 0, "n_skipped": 0, "warnings": []}

    order = _sorted_order(raw)
    ordered = [raw[i] for i in order]
    info = {"model": str(gate.get("model")), "mode": str(gate.get("mode") or "cut"),
            "threshold": (None if gate.get("threshold") is None
                          else float(gate.get("threshold"))),
            "scheme": (str(gate["scheme"]) if gate.get("scheme") else None),
            "size_norm": float(_cfg(gate, "size_norm")),
            "min_history": int(_cfg(gate, "min_history")),
            "refit_every": int(_cfg(gate, "refit_every")),
            "source_run": gate.get("source_run"),
            "n_in": len(ordered), "warnings": []}

    try:
        prob = score_trades(arrays, ordered, gate)
    except Exception as e:
        prob = None
        info["warnings"].append(f"gate scoring failed: {type(e).__name__}: {e}")

    if prob is None:
        # UNGATED FALLBACK. Deliberate: a broken gate must not silently delete a day's
        # trades, because "no trades" and "the gate refused them all" look identical on
        # the board and only one of them is a market observation.
        info.update({"ok": False, "n_kept": len(ordered), "n_skipped": 0,
                     "n_warmup": None, "avg_size": 1.0})
        info["warnings"].append("gate did not run - leg fell back to UNGATED")
        return [(t, 1.0) for t in ordered], info

    mode = str(gate.get("mode") or "cut").lower()
    warm = np.isnan(prob)
    if mode == "tilt":
        # TILT: no cut-off, every trade is taken; only the size moves with the score.
        # Normalised by the frozen size_norm and capped at 3x, matching the report's
        # mean_weight_matched_pre_lockbox_cap3 rule. No recycle: nothing is skipped, so
        # there is no freed capital to respend.
        keep = np.ones(len(ordered), bool)
        w = _tilt_weights(prob, warm, gate.get("scheme") or "tier")
        norm = float(_cfg(gate, "size_norm")) or 1.0
        w = np.minimum(w / norm, _SIZE_CAP)
        kept = [(ordered[i], float(w[i])) for i in range(len(ordered))]
        kept_w = np.array([s for _, s in kept], float) if kept else np.array([], float)
        info.update({
            "ok": True, "n_kept": len(kept), "n_skipped": 0,
            "n_warmup": int(warm.sum()), "skipped_pnl_pts": 0.0,
            "avg_size": (round(float(kept_w.mean()), 3) if len(kept_w) else None),
            "max_size": (round(float(kept_w.max()), 3) if len(kept_w) else None),
        })
        return kept, info

    thr = float(gate["threshold"])
    # NaN = the bouncer was still off duty (warm-up). Those trades pass, exactly as
    # gate_trades lets them pass, so a short window reads as honest rather than filtered.
    keep = ~(prob < thr)

    if mode == "hybrid":
        pf = np.where(warm, 0.5, prob)
        w = np.clip(1.0 + _TILT_SLOPE * (pf - 0.50), _TILT_LO, _TILT_HI)
        w = np.where(warm, 1.0, w)
        norm = float(_cfg(gate, "size_norm")) or 1.0
        w = np.minimum(w / norm, _SIZE_CAP)
        # ── RECYCLE (owner 2026-08-16, the "hybrid recycle" column) ──────────────
        # A gate that refuses most trades leaves capital idle. Recycle spends it: every
        # SURVIVING trade is scaled so the book commits the same total contracts as the
        # ungated book would have. It adds no trades -- same entries, bigger size -- and
        # it multiplies drawdown by exactly the same factor as profit.
        #
        # FROZEN, like size_norm, and for the same reason: the honest factor is
        # (all trades / kept trades), and a forward test cannot count its own future
        # trades without reaching into it. Measured once on the source run's window by
        # tools/paper_gate_calibrate.py and pinned in the leg config.
        #
        # Applied AFTER the 3x per-trade cap, matching the report: the cap bounds how far
        # one score may stretch a trade, while recycle is a book-level capital decision.
        rec = float(_cfg(gate, "recycle_factor")) or 1.0
        if rec != 1.0:
            w = w * rec
    else:
        w = np.ones(len(ordered), float)

    kept = [(ordered[i], float(w[i])) for i in range(len(ordered)) if keep[i]]
    kept_w = np.array([s for _, s in kept], float) if kept else np.array([], float)
    skipped_pnl = float(sum(float(ordered[i][2]) for i in range(len(ordered)) if not keep[i]))
    info.update({
        "ok": True,
        "n_kept": len(kept), "n_skipped": int(len(ordered) - len(kept)),
        "n_warmup": int(warm.sum()),
        "skipped_pnl_pts": round(skipped_pnl, 4),
        "avg_size": (round(float(kept_w.mean()), 3) if len(kept_w) else None),
        "max_size": (round(float(kept_w.max()), 3) if len(kept_w) else None),
    })
    return kept, info


def calibrate_size_norm(arrays, trades, gate, upto_index=None):
    """The frozen `size_norm` divisor for a hybrid leg — see this module's docstring.

    Reproduces gate_validate's normalisation: mean raw tilt weight over the SURVIVORS
    (score >= cut-off) within the calibration span, so the leg carries the same average
    size as its ungated baseline. `upto_index` bounds the span to bars strictly before it
    (pass the source run's lockbox start to match that run exactly).

    Returns (size_norm, detail) or (None, detail) when there is nothing to calibrate on.
    """
    order = _sorted_order(trades)
    ordered = [trades[i] for i in order]
    prob = score_trades(arrays, ordered, gate)
    if prob is None:
        return None, {"error": "gate scoring failed"}
    warm = np.isnan(prob)
    if str(gate.get("mode") or "cut").lower() == "tilt":
        # TILT keeps everything; the divisor is the mean raw tilt weight over ALL
        # pre-lockbox trades, exactly ml_gate's `w[_pre_m].mean()`. No recycle.
        keep = np.ones(len(ordered), bool)
        w = _tilt_weights(prob, warm, gate.get("scheme") or "tier")
    else:
        thr = float(gate["threshold"])
        keep = ~(prob < thr)
        pf = np.where(warm, 0.5, prob)
        w = np.clip(1.0 + _TILT_SLOPE * (pf - 0.50), _TILT_LO, _TILT_HI)
        w = np.where(warm, 1.0, w)

    span = np.ones(len(ordered), bool)
    if upto_index is not None:
        span = np.array([int(t[0]) < int(upto_index) for t in ordered], bool)
    sel = keep & span
    if not sel.any():
        return None, {"error": "no survivors in the calibration span",
                      "n_trades": len(ordered)}
    norm = float(w[sel].mean())
    # The recycle factor is measured over the WHOLE source window (not just the calibration
    # span): all trades the config produced divided by the ones the gate kept. That is the
    # "spend the freed capital" ratio the report's recycle column uses.
    n_all, n_kept = len(ordered), int(keep.sum())
    rec = (n_all / n_kept) if n_kept else 1.0
    return norm, {
        "n_trades": n_all, "n_in_span": int(span.sum()),
        "n_survivors_in_span": int(sel.sum()),
        "n_kept_all": n_kept,
        "n_warmup": int(warm.sum()),
        "raw_mean_weight": round(norm, 6),
        "max_size_after_norm": round(float(np.minimum(w[sel] / norm, _SIZE_CAP).max()), 3),
        "recycle_factor": round(rec, 6),
        "max_size_recycled": round(float(np.minimum(w[sel] / norm, _SIZE_CAP).max() * rec), 3),
    }

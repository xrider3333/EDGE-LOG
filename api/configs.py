"""Per-trade CONFIG blotter — same trade list the champion RAW blotter shows, but with
a per-trade keep/skip decision (GATE) or per-trade size multiplier (TILT / HYBRID) laid
on top, using the exact SAME model the run's own gate bake-off (augur_engine.ml_gate.
gate_validate, called from augur_engine.validate.run_validate) computed with. No
Firestore dependency here; the caller passes the payload — kept dependency-light like
api/blotter.py, api/bars.py and api/similar.py.

WHY THIS IS REPRODUCIBLE (read augur_engine/ml_gate.py before assuming it isn't):
augur_engine.ml_gate.gate_trades() is NOT fitted per walk-forward fold. It is ONE
continuous chronological walk over every trade in the window: refit every `refit_every`
newly-completed trades on all trades whose EXIT precedes the new trade's ENTRY, score,
repeat. There is no fold boundary to recover — feed it the identical (arrays, trades,
model, threshold, min_history, refit_every, seed) the original run used and every
per-trade decision falls out byte-for-byte, because the model fit at trade k never
depends on any threshold (see the loop in gate_trades: training uses ALL completed
trades regardless of keep/skip, and probabilities are computed BEFORE the threshold
mask is applied — augur_engine.ml_gate.gate_validate exploits this exact fact to score
once and mask many). So a single threshold=0.0 "scoring pass" here is genuinely
equivalent to whatever threshold the run picked.

The two things that CAN throw this off, both honestly reported in `meta` rather than
silently swallowed:
  - the payload's date_from/date_to not matching the exact window
    augur_engine.validate.run_validate used for its "full" trade list (opt_from..date_to)
    — compared against payload["gate_validate"]["span"] when the caller supplies it;
  - model/threshold/min_history/refit_every/seed not matching what the run's own gate
    bake-off used — min_history/refit_every/seed are NEVER overridden by
    augur_engine.validate.run_validate (always 30/25/42), so those are safe to hardcode;
    model/threshold ARE run-specific and are read from payload["model"]/["threshold"]
    (explicit override) -> payload["gate_validate"]["chosen"] (the run's own pick, if the
    caller forwards it) -> augur_engine.ml_gate.gate_trades' own defaults (logistic/0.50)
    as the last resort, each case labelled in meta.model_source/threshold_source.
"""
import os
import time

import numpy as np
import pandas as pd

from api.blotter import champion_blotter
from api.similar import _resolve_strategy_for_run
from augur_engine.data import find_master, load_master_arrays
from augur_engine.ml_gate import gate_trades

CONFIGS = ("raw", "gate", "tilt", "hybrid")

_TILT_SCHEMES = {
    "tier": lambda p: np.where(p >= 0.55, 2.0, np.where(p >= 0.45, 1.0, 0.5)),
    "linear": lambda p: np.clip(1.0 + 4.0 * (p - 0.50), 0.25, 3.0),
}


def _lockbox_start(idx, payload, gv):
    """Resolve the SAME lockbox boundary augur_engine.ml_gate.gate_validate would have
    used for this run: an explicit lockbox_from wins, else lockbox_months back from the
    window's last bar (gate_validate's own default formula) — mirroring gate_validate's
    lb_start computation exactly (including the lb_from tz-localize dance)."""
    lb_from = payload.get("lockbox_from") or (gv or {}).get("lockbox_from")
    if lb_from:
        lb = pd.Timestamp(lb_from)
        if lb.tzinfo is None:
            tz = getattr(idx, "tz", None)
            if tz is not None:
                lb = lb.tz_localize(tz)
        return lb, "run_gate_validate" if (gv or {}).get("lockbox_from") else "override"
    months = float(payload.get("lockbox_months") or (gv or {}).get("lockbox_months") or 12)
    return idx[-1] - pd.DateOffset(months=months), "default_12mo"


def _score_model(a, raw_trades, model, seed=42, min_history=30, refit_every=25):
    """ONE threshold=0.0 scoring pass (the same trick augur_engine.ml_gate.gate_validate
    uses) -> per-trade win-probability, remapped from gate_trades' internal
    entry-sorted order back to `raw_trades`' own order (defensive: gate_trades sorts by
    entry bar internally: if raw_trades wasn't already chronological, index j of its
    'prob' array is NOT trade j of raw_trades)."""
    n = len(raw_trades)
    order = sorted(range(n), key=lambda i: int(raw_trades[i][0]))
    g0 = gate_trades(a, raw_trades, model=model, threshold=0.0,
                     min_history=min_history, refit_every=refit_every, seed=seed)
    if g0 is None:
        return None, None
    prob_sorted = np.asarray(g0["prob"], float)
    prob = np.full(n, np.nan)
    for j, orig_i in enumerate(order):
        prob[orig_i] = prob_sorted[j]
    return prob, g0["summary"]


def _reconcile(gv, model, threshold, n_kept, net_pts):
    """Compare our computed (n_kept, net points) for this exact model@threshold against
    the run's OWN saved augur_engine.ml_gate.gate_validate candidate list (the 'full'
    block spans the same window champion_blotter/gate_trades ran here). None (not a
    mismatch, just 'nothing to check') if the caller didn't forward gate_validate, or
    that model@threshold isn't among the candidates it swept."""
    if not gv or not isinstance(gv, dict):
        return {"checked": False, "note": "no run gate_validate summary in payload — nothing to compare"}
    cands = gv.get("candidates") or []
    hit = None
    for c in cands:
        if str(c.get("model")) == str(model) and abs(float(c.get("threshold", -9)) - float(threshold)) < 1e-6:
            hit = c
            break
    if hit is None or not isinstance(hit.get("full"), dict):
        return {"checked": False,
                "note": f"model={model}@{threshold:.2f} not among the run's saved gate_validate "
                        f"candidates (or it carries no 'full' block) — nothing to compare"}
    ref_n = hit["full"].get("num_trades")
    ref_pnl = hit["full"].get("total_pnl")
    n_diff = (n_kept - ref_n) if ref_n is not None else None
    pnl_diff = (net_pts - ref_pnl) if ref_pnl is not None else None
    match = (n_diff == 0) and (ref_pnl is not None and abs(pnl_diff) < 0.01)
    return {"checked": True, "ref_n_kept": ref_n, "ref_net_pts": ref_pnl,
            "computed_n_kept": int(n_kept), "computed_net_pts": round(float(net_pts), 2),
            "n_diff": n_diff, "net_pts_diff": (round(pnl_diff, 2) if pnl_diff is not None else None),
            "match": bool(match)}


def load_config_trades(root, payload, log=print) -> dict:
    """Serve one CONFIG's (raw/gate/tilt/hybrid) per-trade keep/size list to the web
    (config_trades runner command).

    payload: the usual blotter/bars payload (instrument, timeframe, session, source,
    strategy, params, cost_pts, mult, date_from, date_to, run_id, code) PLUS:
      config    : 'raw' | 'gate' | 'tilt' | 'hybrid' (default 'raw')
      model     : optional gate model name override (e.g. 'rf')
      threshold : optional cut-off override (gate/hybrid floor)
      scheme    : optional tilt/hybrid sizing scheme ('linear' default, or 'tier' —
                  tilt only; hybrid is always 'linear', matching gate_validate)
      gate_validate : optional — the run's OWN saved augur_engine.ml_gate.gate_validate()
                  output (as stored on the run doc). Not required to compute a config,
                  but without it 'model'/'threshold' fall back to engine defaults instead
                  of "the run's own chosen values", and the reconciliation check has
                  nothing to compare against.
      lockbox_from / lockbox_months : optional overrides for the tilt/hybrid capital-
                  matching boundary (else read off gate_validate, else 12mo default).

    Returns {"ok": True, "config", "model", "threshold", "rows": [...], "summary": {...},
    "meta": {...}} or {"ok": False, "error": ...}.
    """
    t0 = time.time()
    config = str(payload.get("config") or "raw").lower()
    if config not in CONFIGS:
        return {"ok": False, "error": f"unknown config {config!r} (must be one of {CONFIGS})"}

    instrument = payload.get("instrument")
    timeframe = payload.get("timeframe") or "5m"
    session = payload.get("session") or "rth"
    source = payload.get("source")
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    cost_pts = float(payload.get("cost_pts") or 0)
    mult = float(payload.get("mult") or 20)

    if not instrument or not payload.get("strategy"):
        return {"ok": False, "error": "instrument and strategy are required"}

    # ── Step 1: the trade list — ONE code path (champion_blotter), same as api/similar.py.
    strat = _resolve_strategy_for_run(root, payload, log)
    if strat is None:
        return {"ok": False,
                "error": f"strategy '{payload.get('strategy')}' is gone from augur_strategies "
                         f"and no code snapshot is available to rebuild it"}
    rows, bmeta, raw_trades = champion_blotter(
        strat, instrument, timeframe, session=session, params=payload.get("params") or {},
        cost_pts=cost_pts, mult=mult, date_from=date_from, date_to=date_to, source=source,
        return_raw=True)
    if not rows:
        return {"ok": False, "error": "champion_blotter produced no trades for this config"}
    n = len(rows)
    pnl_pts = np.array([float(t[2]) for t in raw_trades], float)
    pnl_usd = np.array([float(r["pnl_usd"]) for r in rows], float)
    net_usd_raw = float(pnl_usd.sum())

    gv = payload.get("gate_validate") if isinstance(payload.get("gate_validate"), dict) else None

    # ── span sanity check (honesty requirement: flag, don't silently trust, a window
    #    mismatch against the run's own saved gate_validate span). ──────────────────
    span_note = None
    if gv and isinstance(gv.get("span"), (list, tuple)) and len(gv["span"]) == 2:
        got_from = str(rows[0]["entry_time"])[:10]
        got_to = str(rows[-1]["entry_time"])[:10]
        want_from, want_to = str(gv["span"][0]), str(gv["span"][1])
        if got_from != want_from or got_to > want_to:
            span_note = (f"WINDOW MISMATCH vs run's gate_validate span: this call covers "
                         f"{got_from}..{got_to}, the run's gate bake-off covered "
                         f"{want_from}..{want_to} — per-trade decisions below are NOT "
                         f"guaranteed to reproduce the run's saved gate summary")

    if config == "raw":
        out_rows = [{"trade_no": r["trade_no"], "kept": True, "size": 1.0, "score": None}
                    for r in rows]
        summary = {"n_total": n, "n_kept": n, "pct_kept": 100.0,
                   "net_usd_raw": round(net_usd_raw, 2), "net_usd_config": round(net_usd_raw, 2)}
        meta = {"master": bmeta.get("master"), "source": bmeta.get("source"),
               "date_from": date_from, "date_to": date_to, "n_total": n,
               "elapsed_s": round(time.time() - t0, 3)}
        log(f"    -> config_trades: raw, {n} trades, net ${net_usd_raw:,.0f} "
            f"[{time.time() - t0:.2f}s]")
        return {"ok": True, "config": "raw", "model": None, "threshold": None,
               "rows": out_rows, "summary": summary, "meta": meta}

    # ── gate/tilt/hybrid all need the arrays entry_features scores off of. Independent
    #    load (same fallback chain + window champion_blotter used above) so this stays
    #    dependency-light instead of threading arrays back out of champion_blotter. ──
    m = ((find_master(instrument, timeframe, session, source) if source else None)
         or find_master(instrument, timeframe, session) or find_master(instrument, timeframe))
    if not m:
        return {"ok": False, "error": f"no master for instrument={instrument} timeframe={timeframe}"}
    a = load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx = a["index"]
    if idx is None or len(idx) == 0:
        return {"ok": False, "error": f"master '{m.get('name')}' has no bars in window "
                                      f"{date_from}..{date_to}"}

    chosen = (gv or {}).get("chosen") or {}
    if payload.get("model"):
        model, model_source = str(payload["model"]), "override"
    elif chosen.get("model"):
        model, model_source = str(chosen["model"]), "run_chosen"
    else:
        model, model_source = "logistic", "engine_default"

    if payload.get("threshold") is not None:
        threshold, threshold_source = float(payload["threshold"]), "override"
    elif chosen.get("threshold") is not None:
        threshold, threshold_source = float(chosen["threshold"]), "run_chosen"
    else:
        threshold, threshold_source = 0.50, "engine_default"

    min_history, refit_every, seed = 30, 25, 42   # never overridden by run_validate — safe to fix

    prob, g_summary = _score_model(a, raw_trades, model, seed=seed,
                                   min_history=min_history, refit_every=refit_every)
    if prob is None:
        return {"ok": False,
                "error": f"gate model '{model}' produced no result "
                         f"(too few trades, or every trade shares one outcome)"}

    warm = np.isnan(prob)

    if config == "gate":
        keep = warm | (prob >= threshold)      # NaN (warm-up) passes through, like gate_trades
        size = np.where(keep, 1.0, 0.0)
        net_pts_kept = float(pnl_pts[keep].sum())
        out_rows = [{"trade_no": int(rows[i]["trade_no"]), "kept": bool(keep[i]),
                    "size": float(size[i]),
                    "score": (None if warm[i] else round(float(prob[i]), 4))}
                   for i in range(n)]
        net_usd_config = float(pnl_usd[keep].sum())
        n_kept = int(keep.sum())
        recon = _reconcile(gv, model, threshold, n_kept, net_pts_kept)
        scheme = None

    else:  # tilt / hybrid
        scheme = str(payload.get("scheme") or "linear").lower()
        if config == "hybrid":
            scheme = "linear"                   # gate_validate hybrids are always linear
        if scheme not in _TILT_SCHEMES:
            return {"ok": False, "error": f"unknown scheme {scheme!r} (must be 'linear' or 'tier')"}
        fn = _TILT_SCHEMES[scheme]
        p_filled = np.where(warm, 0.5, prob)
        w = np.where(warm, 1.0, fn(p_filled))    # NaN entries always weight 1.0 (gate_validate)

        lb_start, lb_source = _lockbox_start(idx, payload, gv)
        entry_ts = np.array([idx[min(int(t[0]), len(idx) - 1)] for t in raw_trades])
        pre_mask = entry_ts < lb_start

        if config == "hybrid":
            keep = warm | (prob >= threshold)    # floor pinned to the gate's own cut-off
            w = w * keep
            norm_mask = pre_mask & keep
        else:
            keep = np.ones(n, bool)              # tilt never skips a trade
            norm_mask = pre_mask

        w_norm = w[norm_mask]
        mean_w = float(w_norm.mean()) if len(w_norm) and float(w_norm.mean()) > 1e-9 else 1.0
        size = np.minimum(w / mean_w, 3.0)
        size = np.where(keep, size, 0.0)

        out_rows = [{"trade_no": int(rows[i]["trade_no"]), "kept": bool(keep[i]),
                    "size": round(float(size[i]), 4),
                    "score": (None if warm[i] else round(float(prob[i]), 4))}
                   for i in range(n)]
        net_usd_config = float((pnl_usd * size).sum())
        n_kept = int(keep.sum())
        net_pts_kept = float((pnl_pts * size).sum())
        recon = _reconcile(gv, model, threshold, n_kept, net_pts_kept) if config == "hybrid" else \
            {"checked": False, "note": "tilt rows are never crownable in gate_validate — "
                                       "no per-model@threshold 'full' block exists to compare against; "
                                       "reconciliation only applies to gate/hybrid"}

    summary = {"n_total": n, "n_kept": n_kept, "pct_kept": round(100.0 * n_kept / n, 2),
              "net_usd_raw": round(net_usd_raw, 2), "net_usd_config": round(net_usd_config, 2)}
    meta = {"master": bmeta.get("master"), "source": bmeta.get("source"),
           "date_from": date_from, "date_to": date_to, "n_total": n,
           "model_source": model_source, "threshold_source": threshold_source,
           "min_history": min_history, "refit_every": refit_every, "seed": seed,
           "scheme": scheme,
           "warmup": int(warm.sum()),
           "n_fits": (g_summary or {}).get("n_fits"), "degenerate": (g_summary or {}).get("degenerate"),
           "reconciliation": recon,
           "elapsed_s": round(time.time() - t0, 3)}
    if config in ("tilt", "hybrid"):
        meta["lockbox_from"] = str(lb_start.date())
        meta["lockbox_from_source"] = lb_source
    if span_note:
        meta["span_warning"] = span_note

    log(f"    -> config_trades: {config} {model}@{threshold:.2f}, {n} trades, "
        f"{n_kept} kept ({100.0 * n_kept / n:.1f}%), net ${net_usd_config:,.0f} "
        f"(raw ${net_usd_raw:,.0f}) [{time.time() - t0:.2f}s]"
        + (f" -- {span_note}" if span_note else ""))

    return {"ok": True, "config": config, "model": model, "threshold": threshold,
           "rows": out_rows, "summary": summary, "meta": meta}

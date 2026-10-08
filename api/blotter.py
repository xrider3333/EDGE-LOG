"""Per-trade blotter export — regenerate a run's champion trade-by-trade and write a CSV.
Used by the runner (auto-save a blotter next to every persisted run) and callable ad-hoc.
No Firestore dependency here; the caller passes the config. Kept dependency-light so a
runner save never fails a run (best-effort — wrap calls in try/except)."""
import os
import augur_engine as ae
from augur_engine.data import find_master, load_master_arrays

FIELDS = ["trade_no", "entry_time", "exit_time", "hold_bars",
          "entry_px", "exit_px", "pnl_pts", "pnl_usd", "cum_usd", "side"]


def champion_blotter(strategy, instrument, timeframe, session="rth", params=None,
                     cost_pts=0.0, mult=20.0, date_from=None, date_to=None, source=None,
                     return_raw=False):
    """Run the champion once (return_trades) and return (rows, meta): a list of per-trade
    dict rows plus {"master", "source", ...} naming the master that actually served the
    run — the caller surfaces it so a fallback resolution is never silent. Empty rows if
    the config produces no trades or the master is missing.

    `source` pins the master the run was made on (repo rule: comparison reruns pin the
    data window AND the master). Without it, resolution falls back to the registry's
    first instrument+timeframe(+session) match — which is source-ORDERED, so a tv-master
    run would silently get its blotter from the db_noadj master (run #162 did).

    `return_raw=True` returns a THIRD element: the raw (entry_bar, exit_bar, pnl_pts, ...)
    trade tuples straight off the engine, in the SAME order as `rows` (rows[i]['trade_no']
    == i+1 <-> raw_trades[i]) — for callers (api/configs.py) that need bar indices / net
    points to feed augur_engine.ml_gate, without re-running the backtest a second time and
    risking a different trade list."""
    m = ((find_master(instrument, timeframe, session, source) if source else None)
         or find_master(instrument, timeframe, session) or find_master(instrument, timeframe))
    if not m:
        return ([], {}, []) if return_raw else ([], {})
    meta = {"master": m.get("name"), "source": m.get("source"),
            "requested_source": source or None,
            "date_from": date_from or None, "date_to": date_to or None}
    # Slice with the SAME window the backtest runs on — trade tuples carry bar indices
    # into the sliced arrays, so an unsliced index here would shift every timestamp/price
    # by the number of pre-window bars.
    a = load_master_arrays(m, date_from=date_from, date_to=date_to)
    idx, close = a["index"], a["close"]
    bt = ae.run_backtest(strategy, instrument=instrument, timeframe=timeframe, session=session,
                         arrays=a, params=params or {}, cost_pts=float(cost_pts or 0),
                         return_trades=True)
    raw_trades = list((bt or {}).get("trades") or [])
    rows, cum = [], 0.0
    for i, t in enumerate(raw_trades, 1):
        eb, xb, pnl = int(t[0]), int(t[1]), float(t[2])
        ep = float(t[4]) if len(t) > 4 else float(close[eb])
        # Trade tuple shape varies by strategy file: some carry a side flag at index 3
        # (1=long/-1=short — ORB/AOSTOCH/BBRSI/EMAX/ENGUQ/DRIVE families), some are a
        # bare (entry_bar, exit_bar, pnl) 3-tuple with no side and no entry price
        # (legacy ENGU_1_1_x/ENGU_1_3_x family) — entry_px already falls back to
        # close[eb] above for those.
        side_flag = int(t[3]) if len(t) > 3 else None
        # docs/VISUAL_TRADE_REPORT.md §2.5: this engine's exit logic can defer a fill to
        # the FOLLOWING bar (or an EOD backstop), so "exit = close[xb]" is not reliably
        # the real fill price. The trade tuple never carries a true exit price either, so
        # reconstruct it by cost-inversion: net pnl + cost = gross points moved, and
        # inverting that arithmetic recovers the exact fill the simulator used.
        gross = pnl + float(cost_pts or 0)
        if side_flag is not None:
            side = 1 if side_flag >= 0 else -1
        else:
            # No side flag on this tuple — infer it the only way available: whichever
            # direction's implied exit price lands closer to the bar's actual close.
            long_exit = ep + gross
            short_exit = ep - gross
            side = 1 if abs(float(close[xb]) - long_exit) <= abs(float(close[xb]) - short_exit) else -1
        exit_px = ep + gross if side == 1 else ep - gross
        usd = pnl * float(mult)
        cum += usd
        rows.append({"trade_no": i, "entry_time": str(idx[eb])[:16], "exit_time": str(idx[xb])[:16],
                     "hold_bars": xb - eb, "entry_px": round(ep, 2), "exit_px": round(exit_px, 2),
                     "pnl_pts": round(pnl, 2), "pnl_usd": round(usd, 2), "cum_usd": round(cum, 0),
                     "side": "long" if side == 1 else "short"})
    if return_raw:
        return rows, meta, raw_trades
    return rows, meta


def write_csv(rows, path, meta=None):
    """Write blotter rows to a CSV at `path` (creates parent dirs). Returns path or None.
    `meta` (which master/window built these rows) goes to a `<path>.meta.json` sidecar so
    a cached CSV can still say which master served it."""
    if not rows:
        return None
    import csv
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    if meta:
        try:
            import json
            import time
            with open(path + ".meta.json", "w", encoding="utf-8") as f:
                json.dump({**meta, "generated_at": time.strftime("%Y-%m-%d %H:%M")}, f)
        except Exception:
            pass
    return path


# Historical strategy-file renames (git history) — old run docs still carry the old name.
# Normalized-key → current filename. ORB_SIMPLE→ORB_3_0: commit 4395bb6, file unchanged since,
# so regenerating an old ORB_SIMPLE run with ORB_3_0.py is byte-exact.
_RENAMES = {"orbsimple10": "ORB_3_0.py"}


def _resolve_strategy(root, name):
    """Run docs sometimes carry the strategy's display LABEL ('ORB 3.1 · low-DOF + …'),
    not the plugin filename ('ORB_3_1.py') — and some carry a filename that has since been
    RENAMED. Resolve: exact file → rename alias → normalized prefix match (longest wins)."""
    import re
    import glob as _glob
    base = os.path.join(root, "augur_strategies")
    fn = name if str(name).endswith(".py") else str(name) + ".py"
    if os.path.isfile(os.path.join(base, fn)):
        return name
    _n = re.sub(r"[^a-z0-9]", "", str(name).lower().replace(".py", ""))
    for old, new in _RENAMES.items():
        if (_n.startswith(old) or old.startswith(_n)) and os.path.isfile(os.path.join(base, new)):
            return new
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    nl = norm(name)
    cands = []
    for f in _glob.glob(os.path.join(base, "*.py")):
        stem = os.path.splitext(os.path.basename(f))[0]
        ns = norm(stem)
        if ns and (nl.startswith(ns) or ns.startswith(nl)):
            cands.append((len(ns), os.path.basename(f)))
    return max(cands)[1] if cands else name


def _module_from_code(root, rid, code, log=print):
    """Rebuild a run's strategy from its stored code snapshot (the exact source the run
    executed). Used when the plugin file no longer exists (renamed/deleted, or the run was
    pruned from the local DB but lives on in Firestore — the web sends d.code_snapshot).
    Writes blotters/_snapshot_run{rid}.py and imports it; None if unusable."""
    if not code or not isinstance(code, str) or len(code) < 100:
        return None
    try:
        import importlib.util
        snap = os.path.join(root, "blotters", f"_snapshot_run{rid}.py")
        os.makedirs(os.path.dirname(snap), exist_ok=True)
        with open(snap, "w", encoding="utf-8") as f:
            f.write(code)
        spec = importlib.util.spec_from_file_location(f"snap_run{rid}", snap)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "run_backtest"):
            log(f"    -> strategy rebuilt from run {rid}'s code snapshot")
            return mod
    except Exception as e:
        log(f"    -> snapshot rebuild failed: {type(e).__name__}: {e}")
    return None


def _snapshot_from_db(root, rid):
    """Pull code_snapshot for a run id from the local history DB (may be pruned)."""
    import sqlite3
    db = os.path.join(root, "optimizer_history.db")
    if not os.path.isfile(db):
        return None
    try:
        con = sqlite3.connect(db)
        row = con.execute("SELECT code_snapshot FROM runs WHERE id=?", (int(rid),)).fetchone()
        con.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


# Firestore caps a command doc at 1MB - a 10k-trade 1m blotter would burst it. load_blotter_rows
# serves the most-recent MAXR trades and says so; the full CSV always stays on disk. Module-level
# (not a local) so a test can patch it; the readings below are computed BEFORE this cap trims.
MAXR = 6000


def _num(v):
    """A finite float from a CSV string / number, else None (blank, text, NaN, inf, bool)."""
    import math
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _plain(o):
    """Plain JSON types only: numpy scalars -> python, NaN/inf -> None, tuples -> lists."""
    import math
    import numpy as np
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(x) for x in o]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    return o


def blotter_readings(rows, payload):
    """The run's SECOND readings, computed from ALL its rows (call it before any MAXR cap):

      cost       augur_engine.cost_readings.readings() - net at the charged cost, at double
                 cost, break-even cost per round trip, headroom. Needs payload cost_pts (the
                 cost the run was charged; never guessed as 0) and mult (money per point).
      realistic  cost_readings.realistic() for an instrument with PUBLISHED inputs only
                 (cost_readings.DEFAULT_INPUTS) - the module would silently fall back to NQ's.
                 No ATR in a blotter, so slippage is NOT included (slippage_included False).
      limits     run_limits: what this run does not model (items / lines / counts / basis).
      summary    cost_readings.summary_lines() - the module's own plain sentences.

    Never raises: any exception becomes {"ok": False, "error": ...} so the blotter is still
    served. Rows' pnl_pts is NET (the backtest already charged cost_pts; the engine module adds
    it back itself, so nothing is pre-added here).
    """
    try:
        import re
        from augur_engine import cost_readings, run_limits
        payload = payload or {}
        n_rows = len(rows)
        pts = [(r, _num(r.get("pnl_pts"))) for r in rows]
        trades = [(i, i + 1, p) for i, (_, p) in enumerate(pts) if p is not None]
        cost_pts, mult = _num(payload.get("cost_pts")), _num(payload.get("mult"))
        if cost_pts is not None and cost_pts < 0:
            cost_pts = None
        if mult is not None and mult <= 0:
            mult = None
        inst = str(payload.get("instrument") or "").strip()

        # ---- cost: refuses to guess the charged cost or the point value ------------------
        cost = None
        if cost_pts is None:
            cost = {"ok": False, "error": "cost_pts missing from the request - the readings need "
                    "the cost this run was charged per round trip and will not guess 0"}
        elif mult is None:
            cost = {"ok": False, "error": "mult missing from the request - the readings need the "
                    "money value of one point"}
        else:
            cost = {"ok": True, **cost_readings.readings(trades, cost_pts, mult)}

        # ---- realistic: published inputs only, no ATR -> no slippage ----------------------
        merged = None
        if inst.upper() not in cost_readings.DEFAULT_INPUTS:
            realistic = {"ok": False,
                         "why": "no published cost inputs for %s" % (inst or "(no instrument)")}
        elif not cost["ok"]:
            realistic = {"ok": False, "why": "needs the cost reading first (%s)" % cost["error"]}
        else:
            merged = full = cost_readings.realistic(trades, cost_pts, inst.upper(), mult,
                                                    atr_pts=None, contracts=1)
            realistic = {"ok": True, "instrument": inst.upper(), "contracts": 1,
                         "slippage_included": False, "atr_pts": None, "fitted": False}
            realistic.update({k: full[k] for k in (
                "realistic_cost_pts", "net_realistic_pts", "net_realistic_usd",
                "survives", "realistic_over_breakeven", "realistic_breakdown")})

        # ---- limits: the run's settings + what the rows can tell --------------------------
        run = {"n_trades": n_rows}
        for k in ("instrument", "timeframe", "session", "source", "date_from", "date_to",
                  "family", "fill_rule"):
            if payload.get(k):
                run[k] = payload[k]
        if cost_pts is not None:
            run["cost_pts"] = cost_pts
        if isinstance(payload.get("marked_daily"), bool):
            run["marked_daily"] = payload["marked_daily"]
        date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        lb_from = str(payload.get("lockbox_from") or "")[:10]
        if date_re.fullmatch(lb_from):
            dto = str(payload.get("date_to") or "")[:10]
            lb = [(r, p) for r, p in pts
                  if date_re.fullmatch(str(r.get("exit_time") or "")[:10])
                  and str(r.get("exit_time"))[:10] >= lb_from]
            if lb or not (dto and dto < lb_from):    # no lockbox at all if the window ends first
                # money: the row's own pnl_usd, else points x mult; if any row has neither, the
                # whole lockbox is read in points and pnl_units says so.
                usd = []
                for r, p in lb:
                    u = _num(r.get("pnl_usd"))
                    usd.append(u if u is not None else (p * mult if (p is not None and mult is not None) else None))
                if all(v is not None for v in usd):
                    vals, run["pnl_units"] = usd, "usd"
                else:
                    vals, run["pnl_units"] = [p for _, p in lb if p is not None], "pts"
                run["lockbox_from"] = lb_from
                run["lockbox_trades"] = len(vals)
                run["lockbox_net"] = float(sum(vals))
                run["lockbox_top_trade_net"] = float(max(vals)) if vals else None
        limits = {"ok": True, "items": run_limits.not_modelled(run), "lines": run_limits.lines(run),
                  "counts": run_limits.counts(run), "basis": run}

        # ---- summary: the module's own sentences (realistic included when it ran) --------
        # Contained on its own: the sentences are a convenience over numbers already computed
        # (summary_lines itself raises when a run was charged cost_pts == 0 - headroom is None),
        # so a failure here must not throw the readings away.
        summary, summary_error = [], None
        if cost["ok"]:
            try:
                summary = cost_readings.summary_lines(
                    merged if merged is not None else {k: v for k, v in cost.items() if k != "ok"})
            except Exception as e:
                summary_error = "%s: %s" % (type(e).__name__, e)
        res = {"ok": True, "n_rows": n_rows, "n_trades": len(trades), "cost": cost,
               "realistic": realistic, "limits": limits, "summary": summary}
        if summary_error:
            res["summary_error"] = summary_error
        return _plain(res)
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def load_blotter_rows(root, payload, log=print):
    """Serve a run's blotter to the web (get_blotter runner command).

    Search order: {root}/blotters/run{id}_{inst}_{tf}.csv (the runner's auto-saves), then
    ../Trading/ENGUQ_DB/blotters/ (the ENGU research runs). If neither exists and the
    payload carries the champion config (strategy/params/window), regenerate the blotter
    on the spot and cache it under {root}/blotters for next time. Returns a json-safe
    {ok, rows, n, source|regenerated} dict — rows use the FIELDS schema.

    A truthy payload["readings"] also attaches out["readings"] (see blotter_readings: cost,
    realistic, limits, summary), computed from ALL the run's rows before the MAXR cap trims what
    is sent. It needs payload cost_pts + mult (+ instrument; optional lockbox_from, family,
    fill_rule, marked_daily, date_from/date_to, source). Absent the flag, nothing changes.
    """
    import csv
    rid = payload.get("run_id")
    inst = payload.get("instrument") or ""
    tf = payload.get("timeframe") or "5m"
    name = f"run{rid}_{inst}_{tf}.csv"
    cands = [os.path.join(root, "blotters", name),
             os.path.join(os.path.dirname(root), "Trading", "ENGUQ_DB", "blotters", name)]

    def _cap(rows, extra):
        out = {"ok": True, "n": len(rows), **extra}
        if len(rows) > MAXR:      # module constant: serve the most-recent MAXR trades, say so
            out["rows"] = rows[-MAXR:]
            out["capped"] = len(rows) - MAXR
        else:
            out["rows"] = rows
        if payload.get("readings"):    # from ALL rows, before the cap trimmed what is sent
            out["readings"] = blotter_readings(rows, payload)
        return out

    for pth in cands:
        if os.path.isfile(pth):
            with open(pth, newline="", encoding="utf-8") as f:
                rows = [dict(r) for r in csv.DictReader(f)]
            if rows:
                log(f"    -> blotter served from {pth} ({len(rows)} trades)")
                extra = {"source": os.path.basename(os.path.dirname(pth)) + "/" + name}
                try:   # sidecar meta (which master/window built this CSV) rides along
                    import json
                    with open(pth + ".meta.json", encoding="utf-8") as f:
                        extra["master"] = (json.load(f) or {}).get("master")
                except Exception:
                    pass
                return _cap(rows, extra)
    params = payload.get("params") or {}
    if not payload.get("strategy") or not params:
        return {"ok": False,
                "error": f"no saved blotter ({name}) and the run carries no champion config to regenerate one"}
    # Resolve the strategy: filename -> label match -> the run's own CODE SNAPSHOT (web doc
    # or local DB) when the plugin file no longer exists on disk.
    strat = _resolve_strategy(root, payload["strategy"])
    fn = strat if str(strat).endswith(".py") else str(strat) + ".py"
    if not os.path.isfile(os.path.join(root, "augur_strategies", fn)):
        mod = (_module_from_code(root, rid, payload.get("code"), log)
               or _module_from_code(root, rid, _snapshot_from_db(root, rid), log))
        if mod is None:
            return {"ok": False,
                    "error": f"strategy '{payload['strategy']}' is gone from augur_strategies "
                             f"and no code snapshot is available to rebuild it"}
        strat = mod
    rows, bmeta = champion_blotter(strat, inst, tf,
                                   session=payload.get("session") or "rth", params=params,
                                   cost_pts=float(payload.get("cost_pts") or 0),
                                   mult=float(payload.get("mult") or 20),
                                   date_from=payload.get("date_from"), date_to=payload.get("date_to"),
                                   source=payload.get("source"))
    if not rows:
        return {"ok": False, "error": "champion re-run produced no trades"}
    try:
        write_csv(rows, os.path.join(root, "blotters", name), meta=bmeta)   # cache for next time
    except Exception:
        pass
    log(f"    -> blotter regenerated ({len(rows)} trades) for run {rid} "
        f"from master '{bmeta.get('master')}'")
    return _cap(rows, {"regenerated": True, "master": bmeta.get("master")})

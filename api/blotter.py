"""Per-trade blotter export — regenerate a run's champion trade-by-trade and write a CSV.
Used by the runner (auto-save a blotter next to every persisted run) and callable ad-hoc.
No Firestore dependency here; the caller passes the config. Kept dependency-light so a
runner save never fails a run (best-effort — wrap calls in try/except)."""
import os
import augur_engine as ae
from augur_engine.data import find_master, load_master_arrays

FIELDS = ["trade_no", "entry_time", "exit_time", "hold_bars",
          "entry_px", "exit_px", "pnl_pts", "pnl_usd", "cum_usd"]


def champion_blotter(strategy, instrument, timeframe, session="rth", params=None,
                     cost_pts=0.0, mult=20.0, date_from=None, date_to=None):
    """Run the champion once (return_trades) and return a list of per-trade dict rows.
    Empty list if the config produces no trades or the master is missing."""
    m = find_master(instrument, timeframe, session) or find_master(instrument, timeframe)
    if not m:
        return []
    a = load_master_arrays(m)
    idx, close = a["index"], a["close"]
    bt = ae.run_backtest(strategy, instrument=instrument, timeframe=timeframe, session=session,
                         params=params or {}, cost_pts=float(cost_pts or 0),
                         date_from=date_from, date_to=date_to, return_trades=True)
    rows, cum = [], 0.0
    for i, t in enumerate((bt or {}).get("trades") or [], 1):
        eb, xb, pnl = int(t[0]), int(t[1]), float(t[2])
        ep = float(t[4]) if len(t) > 4 else float(close[eb])
        usd = pnl * float(mult)
        cum += usd
        rows.append({"trade_no": i, "entry_time": str(idx[eb])[:16], "exit_time": str(idx[xb])[:16],
                     "hold_bars": xb - eb, "entry_px": round(ep, 2), "exit_px": round(float(close[xb]), 2),
                     "pnl_pts": round(pnl, 2), "pnl_usd": round(usd, 2), "cum_usd": round(cum, 0)})
    return rows


def write_csv(rows, path):
    """Write blotter rows to a CSV at `path` (creates parent dirs). Returns path or None."""
    if not rows:
        return None
    import csv
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
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


def load_blotter_rows(root, payload, log=print):
    """Serve a run's blotter to the web (get_blotter runner command).

    Search order: {root}/blotters/run{id}_{inst}_{tf}.csv (the runner's auto-saves), then
    ../Trading/ENGUQ_DB/blotters/ (the ENGU research runs). If neither exists and the
    payload carries the champion config (strategy/params/window), regenerate the blotter
    on the spot and cache it under {root}/blotters for next time. Returns a json-safe
    {ok, rows, n, source|regenerated} dict — rows use the FIELDS schema.
    """
    import csv
    rid = payload.get("run_id")
    inst = payload.get("instrument") or ""
    tf = payload.get("timeframe") or "5m"
    name = f"run{rid}_{inst}_{tf}.csv"
    cands = [os.path.join(root, "blotters", name),
             os.path.join(os.path.dirname(root), "Trading", "ENGUQ_DB", "blotters", name)]
    # Firestore caps a command doc at 1MB — a 10k-trade 1m blotter would burst it. Serve the
    # most-recent MAXR trades and say so; the full CSV always stays on disk.
    MAXR = 6000

    def _cap(rows, extra):
        out = {"ok": True, "n": len(rows), **extra}
        if len(rows) > MAXR:
            out["rows"] = rows[-MAXR:]
            out["capped"] = len(rows) - MAXR
        else:
            out["rows"] = rows
        return out

    for pth in cands:
        if os.path.isfile(pth):
            with open(pth, newline="", encoding="utf-8") as f:
                rows = [dict(r) for r in csv.DictReader(f)]
            if rows:
                log(f"    -> blotter served from {pth} ({len(rows)} trades)")
                return _cap(rows, {"source": os.path.basename(os.path.dirname(pth)) + "/" + name})
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
    rows = champion_blotter(strat, inst, tf,
                            session=payload.get("session") or "rth", params=params,
                            cost_pts=float(payload.get("cost_pts") or 0),
                            mult=float(payload.get("mult") or 20),
                            date_from=payload.get("date_from"), date_to=payload.get("date_to"))
    if not rows:
        return {"ok": False, "error": "champion re-run produced no trades"}
    try:
        write_csv(rows, os.path.join(root, "blotters", name))   # cache for next time
    except Exception:
        pass
    log(f"    -> blotter regenerated ({len(rows)} trades) for run {rid}")
    return _cap(rows, {"regenerated": True})

"""Run-history access from optimizer_history.db (streamlit-free).

The Streamlit app writes every optimization to the `runs` table. This exposes that
history to the web: list_runs() for the browse list (no big blobs), get_run() for the
detail view (best_params / top10_results / equity_curves_json parsed to objects).
"""
import json
import base64
import gzip
import sqlite3

from .paths import DB_PATH


def _downsample_equity(cum, final, n=160):
    """Cumulative-PnL list -> a compact equity series (~n points) for the web chart."""
    full = len(cum)
    if full > n:
        step = full / n
        cum = [cum[int(i * step)] for i in range(n)]
    return {"cum": [round(float(x), 1) for x in cum], "final": final, "n": full}

# Columns for the browse list — everything useful EXCEPT the big blobs
# (code_snapshot ~10KB, full_results, top10_results, equity_curves_json).
_LIST_COLS = ("id,timestamp,strategy,instrument,timeframe,scope,data_source,source_name,"
              "n_combos,n_valid,bars,days_in_test,date_from,date_to,best_pnl_usd,"
              "best_pnl_pts,best_pf,best_win_rate,best_trades,best_dd_usd,best_pnl_per_day,"
              "multiplier,starred,note,app_version,elapsed_s")


def list_runs(limit=None):
    """All runs as trimmed dicts, newest first (no large blobs). Returns [] if the
    history DB hasn't been initialized yet (no `runs` table — e.g. a fresh copy)."""
    q = f"SELECT {_LIST_COLS} FROM runs ORDER BY id DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(q)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return []
        raise
    finally:
        conn.close()


def get_run(run_id):
    """One run with detail blobs parsed (best_params, top10_results, full_results,
    equity_curves_json). Drops the big code_snapshot. Returns None if not found."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("SELECT * FROM runs WHERE id=?", (int(run_id),))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(zip(cols, row))
    for k in ("best_params", "top10_results", "full_results"):
        v = d.get(k)
        if isinstance(v, str) and v:
            try:
                d[k] = json.loads(v)
            except Exception:
                pass
    # equity_curves_json is base64+gzip JSON (list of curves). Decode the best
    # (rank-1) curve's cumulative PnL, downsample, and drop the raw blob.
    raw = d.pop("equity_curves_json", None)
    if isinstance(raw, str) and len(raw) > 50:
        try:
            curves = json.loads(gzip.decompress(base64.b64decode(raw)))
            if curves:
                cum = curves[0].get("cum_pnl_usd") or []
                if cum:
                    d["equity"] = _downsample_equity(cum, curves[0].get("final_pnl"))
        except Exception:
            pass
    d.pop("code_snapshot", None)
    return d

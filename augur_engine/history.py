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
from .analytics import downsample_pnls, downsample_points

# metric keys (not parameters) — excluded when extracting param values for scatter/heatmap
_METRIC_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown",
                "avg_pnl", "wins", "losses", "oos_pnl", "oos_trades", "oos_pf", "fold",
                "test_bars", "train_bars", "pnl"}


def _maybe_gzip_json(v):
    """Parse a value that may be plain JSON or base64+gzip JSON (legacy blobs)."""
    if not isinstance(v, str) or not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        pass
    try:
        return json.loads(gzip.decompress(base64.b64decode(v)))
    except Exception:
        return None


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


def _mar(pnl_usd, dd_usd):
    """MAR = net PnL / |max drawdown| — the drawdown-adjusted return you size on.
    Derived (not stored), so it's available for ranking/columns without a migration."""
    dd = abs(float(dd_usd or 0.0)); pnl = float(pnl_usd or 0.0)
    return round(pnl / dd, 2) if dd > 1e-9 else None


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
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for d in rows:                       # derived drawdown-adjusted return (net/|maxDD|)
            d["mar"] = _mar(d.get("best_pnl_usd"), d.get("best_dd_usd"))
        return rows
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return []
        raise
    finally:
        conn.close()


def get_run(run_id):
    """One run with detail blobs parsed (best_params, top10_results, full_results,
    equity_curves_json). KEEPS the strategy code_snapshot (so the web report can show the EXACT
    source that produced the run) plus a short code_sha fingerprint. Returns None if not found."""
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
    d["mar"] = _mar(d.get("best_pnl_usd"), d.get("best_dd_usd"))   # drawdown-adjusted return
    for k in ("best_params", "top10_results"):
        v = d.get(k)
        if isinstance(v, str) and v:
            try:
                d[k] = json.loads(v)
            except Exception:
                pass
    mult = float(d.get("multiplier") or 1) or 1

    # full_results (base64+gzip list of every config) -> dist + points panels.
    fr = _maybe_gzip_json(d.pop("full_results", None))
    if isinstance(fr, list) and fr:
        d["dist"] = downsample_pnls([c.get("total_pnl", 0) for c in fr if isinstance(c, dict)])
        pts = []
        for c in fr:
            if not isinstance(c, dict):
                continue
            row_ = {k: v for k, v in c.items()
                    if k not in _METRIC_KEYS and isinstance(v, (int, float))}
            row_["pnl"] = round(float(c.get("total_pnl", 0) or 0), 1)
            pts.append(row_)
        d["points"] = downsample_points(pts)

    # equity_curves_json (base64+gzip list of curves, cum in $) -> equity, equity_top, stress.
    curves = _maybe_gzip_json(d.pop("equity_curves_json", None))
    if isinstance(curves, list) and curves:
        cum0 = curves[0].get("cum_pnl_usd") or []
        if cum0:
            d["equity"] = _downsample_equity([x / mult for x in cum0],
                                             round((curves[0].get("final_pnl") or 0) / mult, 1))
            # stress: net PnL across 8 chronological windows (deltas of the cumulative curve)
            if len(cum0) >= 16:
                pts_pnl = [cum0[0]] + [cum0[i] - cum0[i - 1] for i in range(1, len(cum0))]
                N, sz = 8, len(pts_pnl) // 8
                d["stress"] = [round(sum(pts_pnl[i*sz:(len(pts_pnl) if i == N-1 else (i+1)*sz)]) / mult, 1)
                               for i in range(N)]
        etop = []
        for cv in curves[:6]:
            cm = cv.get("cum_pnl_usd") or []
            if not cm:
                continue
            if len(cm) > 80:
                step = len(cm) / 80
                cm = [cm[int(i * step)] for i in range(80)]
            etop.append({"cum": [round(x / mult, 1) for x in cm]})   # map, not nested array
        if etop:
            d["equity_top"] = etop
    # Keep the strategy source THIS run executed (the whole plugin file, captured at run time) so a
    # run is always reproducible from the web. Add a short sha fingerprint; cap a pathological blob.
    snap = d.get("code_snapshot")
    if isinstance(snap, str) and snap:
        try:
            import hashlib
            d["code_sha"] = hashlib.sha256(snap.encode("utf-8", "ignore")).hexdigest()[:12]
        except Exception:
            pass
        if len(snap) > 300_000:
            d["code_snapshot"] = snap[:300_000] + "\n\n# … truncated for sync …"
    return d

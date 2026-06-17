"""
GROK ENGU/ES Strategy Optimizer
────────────────────────────────────────────────────────────────────
Python port of Pine Script: GROK ENGU/ES (I) v20
Systematically tests every parameter combination to maximise PNL.

Run with:  streamlit run optimizer.py
────────────────────────────────────────────────────────────────────
"""

__version__ = "5.8.103"

# Loud startup banner — prints to the terminal so you can confirm WHICH file
# is actually running, independent of any browser cache.
print("\n" + "=" * 50)
print(f"  AUGUR  v{__version__}  —  running from this file")
print("=" * 50 + "\n", flush=True)

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import itertools
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
from datetime import datetime
import time
import sqlite3
import json
import os
import math
import shutil

# CPU / parallelism. The i7-1260P has 4 P-cores + 8 E-cores (16 logical).
# Default to a value that uses the fast cores plus a couple E-cores while
# leaving headroom so the laptop stays responsive. User-adjustable in Settings.
_CPU_LOGICAL = os.cpu_count() or 4
DEFAULT_WORKERS = max(1, min(6, _CPU_LOGICAL - 2))
MAX_SELECTABLE_WORKERS = max(1, _CPU_LOGICAL)

# ──────────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG + THEME SYSTEM
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Augur · Strategy Optimizer",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Allow Pandas Styler to render larger tables (we still cap styling adaptively).
try:
    pd.set_option("styler.render.max_elements", 2_000_000)
except Exception:
    pass

# CSS gets injected later — after we know the active theme from config.


# ──────────────────────────────────────────────────────────────────────────────
#  INSTRUMENT & TIMEFRAME CONFIGS
# ──────────────────────────────────────────────────────────────────────────────
INSTRUMENTS = {
    "ES":   {"ticker": "ES=F",  "multiplier": 50},
    "MES":  {"ticker": "ES=F",  "multiplier": 5},
    "NQ":   {"ticker": "NQ=F",  "multiplier": 20},
    "MNQ":  {"ticker": "NQ=F",  "multiplier": 2},
    "RTY":  {"ticker": "RTY=F", "multiplier": 50},
    "M2K":  {"ticker": "RTY=F", "multiplier": 5},
    "YM":   {"ticker": "YM=F",  "multiplier": 5},
    "MYM":  {"ticker": "YM=F",  "multiplier": 0.5},
    "CL":   {"ticker": "CL=F",  "multiplier": 1000},
    "MCL":  {"ticker": "CL=F",  "multiplier": 100},
    "GC":   {"ticker": "GC=F",  "multiplier": 100},
    "MGC":  {"ticker": "GC=F",  "multiplier": 10},
    "Custom": {"ticker": "",    "multiplier": 1},
}

TIMEFRAMES = {
    "1m  (7-day max on Yahoo)":   {"interval": "1m",  "period": "7d"},
    "5m  (60-day max on Yahoo)":  {"interval": "5m",  "period": "60d"},
    "15m (60-day max on Yahoo)":  {"interval": "15m", "period": "60d"},
    "30m (60-day max on Yahoo)":  {"interval": "30m", "period": "60d"},
    "1h  (730-day max on Yahoo)": {"interval": "1h",  "period": "730d"},
    "1d  (5-year max on Yahoo)":  {"interval": "1d",  "period": "1825d"},
}


# ──────────────────────────────────────────────────────────────────────────────
#  OPTIMIZATION PARAMETER GRIDS
#  Combos verified: Short=216 · Medium=1458 · Long=5400
# ──────────────────────────────────────────────────────────────────────────────
SCOPE_GRIDS = {
    "Short  (~216 combos  · ~5 sec)": {
        "lookback_len":       [8, 13, 18],
        "min_red_dominance":  [0.60, 0.70],
        "min_breakout_pts":   [5.0, 9.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],       # only used when use_percent=True
        "max_body_ratio":     [0.40, 0.60],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.5, 2.0, 2.5],
        "be_bars":            [2],
    },
    "Medium (~1,458 combos · ~30 sec)": {
        "lookback_len":       [8, 13, 18],
        "min_red_dominance":  [0.55, 0.65, 0.75],
        "min_breakout_pts":   [5.0, 9.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],
        "max_body_ratio":     [0.35, 0.50, 0.65],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.5, 2.0, 2.5],
        "be_bars":            [1, 2, 3],
    },
    "Long   (~5,400 combos · ~2 min)": {
        "lookback_len":       [5, 8, 13, 18, 23],
        "min_red_dominance":  [0.55, 0.65, 0.75],
        "min_breakout_pts":   [4.0, 7.0, 10.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],
        "max_body_ratio":     [0.30, 0.45, 0.60],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.0, 1.5, 2.0, 2.5, 3.0],
        "be_bars":            [1, 2, 3],
    },
    "Custom": {},
}


# ──────────────────────────────────────────────────────────────────────────────
#  RUN HISTORY  ─  SQLite-backed local storage
# ──────────────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "optimizer_history.db")

def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            instrument    TEXT,
            timeframe     TEXT,
            data_source   TEXT,
            scope         TEXT,
            n_combos      INTEGER,
            n_valid       INTEGER,
            bars          INTEGER,
            date_from     TEXT,
            date_to       TEXT,
            days_in_test  INTEGER,
            best_pnl_pts  REAL,
            best_pnl_usd  REAL,
            best_pnl_per_day REAL,
            best_win_rate REAL,
            best_pf       REAL,
            best_trades   INTEGER,
            best_dd_usd   REAL,
            best_params   TEXT,   -- JSON
            top10_results TEXT,   -- JSON
            starred       INTEGER DEFAULT 0,
            note          TEXT    DEFAULT '',
            app_version   TEXT,
            code_snapshot TEXT    -- the run_backtest source captured at run time
        )
    """)
    # Backward-compatible column adds (so older DBs upgrade in place)
    cols_now = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    for col, ddl in [
        ("days_in_test",       "INTEGER"),
        ("best_pnl_per_day",   "REAL"),
        ("best_dd_usd",        "REAL"),
        ("starred",            "INTEGER DEFAULT 0"),
        ("note",               "TEXT DEFAULT ''"),
        ("app_version",        "TEXT"),
        ("code_snapshot",      "TEXT"),
        ("full_results",       "TEXT"),   # complete results DataFrame as JSON
        ("equity_curves_json", "TEXT"),   # top-10 equity curves as JSON
        ("multiplier",         "REAL"),   # $ per point, needed to re-render charts
        ("strategy",           "TEXT DEFAULT ''"),  # strategy name at run time
        ("source_name",        "TEXT DEFAULT ''"),  # CSV/source name at run time
        ("commission_usd",     "REAL DEFAULT 0"),   # per-trade commission ($ round trip)
        ("slippage_pts",       "REAL DEFAULT 0"),   # per-trade slippage (pts round trip)
        ("elapsed_s",          "REAL DEFAULT 0"),   # wall-clock run duration (seconds)
    ]:
        if col not in cols_now:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {ddl}")
    conn.commit()
    return conn


def _compress(text: str) -> str:
    """gzip + base64 a JSON string so the DB stays light even with 5k-row results."""
    import gzip, base64
    return base64.b64encode(gzip.compress(text.encode("utf-8"))).decode("ascii")

def _decompress(blob: str) -> str:
    import gzip, base64
    return gzip.decompress(base64.b64decode(blob.encode("ascii"))).decode("utf-8")


HISTORY_CAP = 500   # rolling cap — unstarred runs over this get pruned

def save_run(instrument, timeframe, data_source, scope, n_combos, n_valid,
             bars, date_from, date_to, days_in_test, multiplier,
             best_row, top10_df, code_snapshot="",
             full_results_df=None, equity_curves=None, strategy="", source_name="",
             commission_usd=0.0, slippage_pts=0.0, elapsed_s=0.0):
    """Persist a completed optimization run, then prune oldest unstarred runs over cap."""
    conn = _db_conn()
    # Strategy-agnostic: params are everything in best_row that isn't a metric
    METRIC_KEYS = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                   "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd",
                   "oos_pnl","oos_trades","oos_pf","oos_pnl_usd","fold","test_bars"}
    best_params = {k: best_row[k] for k in best_row.keys() if k not in METRIC_KEYS}

    pnl_usd_val = float(best_row.get("pnl_usd", 0))
    pnl_per_day = pnl_usd_val / days_in_test if days_in_test else 0.0

    # Serialize + compress full results (typical 5k-row DataFrame -> ~20-100 KB after gzip)
    full_results_blob = ""
    if full_results_df is not None and len(full_results_df) > 0:
        full_results_blob = _compress(full_results_df.to_json(orient="records"))

    # Equity curves contain Timestamp objects -> coerce to ISO strings
    equity_blob = ""
    if equity_curves:
        safe_curves = []
        for c in equity_curves:
            safe_curves.append({
                "rank":        c.get("rank"),
                "label":       c.get("label"),
                "timestamps":  [str(t) for t in c.get("timestamps", [])],
                "cum_pnl_usd": list(c.get("cum_pnl_usd", [])),
                "final_pnl":   c.get("final_pnl"),
            })
        equity_blob = _compress(json.dumps(safe_curves))

    conn.execute("""
        INSERT INTO runs
            (timestamp, instrument, timeframe, data_source, scope,
             n_combos, n_valid, bars, date_from, date_to, days_in_test,
             best_pnl_pts, best_pnl_usd, best_pnl_per_day,
             best_win_rate, best_pf, best_trades, best_dd_usd,
             best_params, top10_results, starred, note,
             app_version, code_snapshot, full_results, equity_curves_json,
             multiplier, strategy, source_name)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        instrument, timeframe, data_source, scope,
        n_combos, n_valid, bars, date_from, date_to, days_in_test,
        float(best_row.get("total_pnl", 0)),
        pnl_usd_val,
        round(pnl_per_day, 2),
        float(best_row.get("win_rate", 0)),
        float(best_row.get("profit_factor", 0)),
        int(best_row.get("num_trades", 0)),
        float(best_row.get("dd_usd", 0)),
        json.dumps(best_params),
        top10_df.to_json(orient="records"),
        0,
        "",
        __version__,
        code_snapshot,
        full_results_blob,
        equity_blob,
        float(multiplier),
        strategy,
        source_name,
    ))
    try:
        _new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("UPDATE runs SET commission_usd=?, slippage_pts=?, elapsed_s=? "
                     "WHERE id=?",
                     (float(commission_usd), float(slippage_pts),
                      float(elapsed_s), _new_id))
    except Exception:
        pass
    conn.commit()

    n_unstarred = conn.execute("SELECT COUNT(*) FROM runs WHERE starred=0").fetchone()[0]
    if n_unstarred > HISTORY_CAP:
        to_delete = n_unstarred - HISTORY_CAP
        conn.execute("""
            DELETE FROM runs
            WHERE id IN (
                SELECT id FROM runs WHERE starred=0 ORDER BY id ASC LIMIT ?
            )
        """, (to_delete,))
        conn.commit()
        _bust_db_caches()
    conn.close()

def load_all_runs() -> pd.DataFrame:
    """Return all saved runs as a DataFrame, newest first.
    NOTE: pulls heavy blob columns too — use load_runs_light() for lists."""
    conn = _db_conn()
    df = pd.read_sql("SELECT * FROM runs ORDER BY id DESC", conn)
    conn.close()
    return df

# ── Hot-query micro-caches ─────────────────────────────────────────────────────
# load_runs_light / load_csv_metas are called several times PER RERUN (sidebar,
# exec tab, results ledger, roadmap auto-detect). Cache the small DataFrames and
# bust on write (each DB-write helper calls _bust_db_caches) with a short TTL as
# the safety net. Plain dicts — works from worker threads, no Streamlit dependency.
_DB_CACHE = {"runs": None, "runs_t": 0.0, "csv": None, "csv_t": 0.0}
_DB_CACHE_TTL = 3.0

def _bust_db_caches():
    _DB_CACHE["runs"] = None
    _DB_CACHE["csv"] = None
    try:
        _SCORED_RUN_CACHE.clear()   # relabel/delete/star can change scores/rows
        try:
            os.remove(_SCORED_CACHE_PATH)
        except OSError:
            pass
    except NameError:
        pass                        # defined later in the file; fine at startup


def load_runs_light() -> pd.DataFrame:
    """Lightweight run list (no heavy blob columns) for sidebars/headers/tables.
    Avoids decompressing full_results/equity_curves on every rerun. Cached (see
    _DB_CACHE) because it's hit ~4-6x per rerun."""
    if (_DB_CACHE["runs"] is not None
            and time.time() - _DB_CACHE["runs_t"] < _DB_CACHE_TTL):
        return _DB_CACHE["runs"].copy()
    conn = _db_conn()
    cols = ("id, timestamp, strategy, instrument, timeframe, scope, "
            "days_in_test, best_pnl_usd, best_win_rate, best_pf, best_trades, "
            "best_dd_usd, date_from, date_to, starred, multiplier, "
            "n_combos, n_valid, bars, source_name, commission_usd, slippage_pts, "
            "elapsed_s")
    try:
        df = pd.read_sql(f"SELECT {cols} FROM runs ORDER BY id DESC", conn)
    except Exception:
        # Schema mismatch fallback: full select
        df = pd.read_sql("SELECT * FROM runs ORDER BY id DESC", conn)
    conn.close()
    _DB_CACHE["runs"] = df.copy(); _DB_CACHE["runs_t"] = time.time()
    return df

def load_run_by_id(run_id: int) -> dict:
    """Return a single run's full data including top-10 results and code snapshot."""
    conn = _db_conn()
    row = pd.read_sql(f"SELECT * FROM runs WHERE id={run_id}", conn).iloc[0]
    conn.close()
    return row.to_dict()

def delete_run(run_id: int):
    conn = _db_conn()
    conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
    conn.commit()
    _bust_db_caches()
    conn.close()


@st.cache_data(show_spinner=False)
def _run_wf_summary(run_id: int) -> str:
    """Walk-forward summary for the Past-runs table: 'held/total' folds that held up
    out-of-sample (OOS PF > 1), e.g. '4/6'. Returns '' for non-walk-forward runs or
    when no per-fold data is stored. Cached per run id — a run's full_results never
    changes once saved — so the table stays fast (no decompress on every rerun)."""
    try:
        from io import StringIO as _SIO
        row = load_run_by_id(int(run_id))
        blob = row.get("full_results") if row else None
        if not blob:
            return ""
        fr = pd.read_json(_SIO(_decompress(blob)))
        if "fold" not in fr.columns or "oos_pf" not in fr.columns or not len(fr):
            return ""
        _held = int((pd.to_numeric(fr["oos_pf"], errors="coerce").fillna(0) > 1.0).sum())
        return f"{_held}/{len(fr)}"
    except Exception:
        return ""


def _run_robustness_score(row, fr):
    """Out-of-sample ROBUSTNESS score (0-100) for a saved run. Rewards configs that
    hold up on UNSEEN data: walk-forward > single-split OOS > unvalidated; thin trade
    counts and in-sample↔out-of-sample gaps are penalised; net PNL is deliberately
    secondary. `row` = run dict, `fr` = its full_results DataFrame (or None). Returns a
    dict with the score + its components so the ranking can show WHY."""
    def _f(x, d=0.0):
        try: return float(x)
        except Exception: return d
    is_pf  = _f(row.get("best_pf"))
    trades = int(_f(row.get("best_trades")))
    kind, oos_pf, held, nfold = "unvalidated", None, None, None
    try:
        if fr is not None and len(fr):
            cols = set(fr.columns)
            if {"fold", "oos_pf"} <= cols:
                kind = "walk-forward"
                _o = fr["oos_pf"].replace([np.inf, -np.inf], np.nan)
                oos_pf = float(_o.mean() or 0); nfold = len(fr)
                held = int((fr["oos_pf"] > 1.0).sum())
                if "profit_factor" in cols:
                    is_pf = float(fr["profit_factor"].replace([np.inf, -np.inf], np.nan).mean() or is_pf)
                if "oos_trades" in cols:
                    trades = int(fr["oos_trades"].sum())
            elif {"oos_pf", "profit_factor", "oos_trades"} <= cols:
                kind = "out-of-sample"
                _c = fr[(fr["profit_factor"] > 1.0) & (fr["oos_pf"] > 1.0)
                        & (fr["oos_trades"] >= OOS_MIN_TRADES)]
                if len(_c):
                    _c = _c.assign(_m=_c[["profit_factor", "oos_pf"]].min(axis=1)) \
                           .sort_values("_m", ascending=False)
                    b = _c.iloc[0]
                    oos_pf = float(b["oos_pf"]); is_pf = float(b["profit_factor"])
                    trades = int(b["oos_trades"])
                else:
                    oos_pf = 0.0   # nothing validated out-of-sample
    except Exception:
        pass
    if kind == "walk-forward":      rob = oos_pf or 0.0
    elif kind == "out-of-sample":   rob = (min(is_pf, oos_pf) if oos_pf else 0.0)
    else:                           rob = is_pf * 0.45   # unvalidated → discounted
    pf_score = max(0.0, min(100.0, (rob - 1.0) / 2.0 * 100))   # PF 1→0, 2→50, 3→100
    rel = 0.40 if trades < 10 else 0.65 if trades < 30 else 0.85 if trades < 100 else 1.0
    score = pf_score * rel
    if kind == "walk-forward" and nfold:
        score *= (held / nfold)                     # only held-up folds count
    if kind in ("walk-forward", "out-of-sample") and oos_pf is not None and is_pf > oos_pf:
        score -= min(25.0, (is_pf - oos_pf) * 12.0)  # overfit gap penalty
    if kind == "unvalidated":
        score *= 0.6
    score = max(0.0, min(100.0, round(score)))
    return {"score": int(score), "kind": kind, "rob_pf": round(rob, 2),
            "oos_pf": (round(oos_pf, 2) if oos_pf is not None else None),
            "is_pf": round(is_pf, 2), "trades": int(trades), "held": held, "nfold": nfold}

def rename_strategy_in_runs(old_name: str, new_name: str) -> int:
    """Update the stored strategy name on all past runs that used the old name.
    Returns the number of rows updated. Keeps the Results history in sync when
    a strategy is renamed in the Library."""
    if not old_name or old_name == new_name:
        return 0
    conn = _db_conn()
    cur = conn.execute("UPDATE runs SET strategy=? WHERE strategy=?",
                       (new_name, old_name))
    n = cur.rowcount
    # Also keep the executions table consistent (queued/live records)
    try:
        conn.execute("UPDATE executions SET strategy_name=? WHERE strategy_name=?",
                     (new_name, old_name))
    except Exception:
        pass
    conn.commit()
    _bust_db_caches()
    conn.close()
    return n

def set_runs_strategy(run_ids, new_name: str) -> int:
    """Force the stored strategy name on specific runs (by id). Used to relabel
    historical runs whose stored name has drifted from the current Library name."""
    if not run_ids:
        return 0
    conn = _db_conn()
    n = 0
    for rid in run_ids:
        cur = conn.execute("UPDATE runs SET strategy=? WHERE id=?", (new_name, int(rid)))
        n += cur.rowcount
    conn.commit()
    _bust_db_caches()
    conn.close()
    return n

def relabel_all_runs_to_single_strategy(new_name: str) -> int:
    """Relabel EVERY saved run's strategy to new_name. Safe to use when the
    Library effectively has one strategy and all history belongs to it."""
    if not new_name:
        return 0
    conn = _db_conn()
    cur = conn.execute("UPDATE runs SET strategy=?", (new_name,))
    n = cur.rowcount
    conn.commit()
    _bust_db_caches()
    conn.close()
    return n

def toggle_star(run_id: int):
    conn = _db_conn()
    conn.execute("UPDATE runs SET starred = 1 - starred WHERE id=?", (run_id,))
    conn.commit()
    _bust_db_caches()
    conn.close()

def update_note(run_id: int, note: str):
    conn = _db_conn()
    conn.execute("UPDATE runs SET note=? WHERE id=?", (note, run_id))
    conn.commit()
    _bust_db_caches()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
#  BACKTEST ENGINE  ─  faithful Python port of Pine Script v20
# ──────────────────────────────────────────────────────────────────────────────
def run_backtest(opens, highs, lows, closes, return_trades=False, **params):
    """Strategy dispatcher -> active plugin."""
    strat = _get_active_strategy()
    if strat and hasattr(strat, 'run_backtest'):
        return strat.run_backtest(opens, highs, lows, closes,
                                  return_trades=return_trades, **params)
    return None

# ──────────────────────────────────────────────────────────────────────────────
#  DATA FETCHING
# ──────────────────────────────────────────────────────────────────────────────
def _fetch_yahoo_raw(ticker: str, interval: str, period: str):
    """UNCACHED Yahoo pull. The background auto-refresh THREAD must use this one:
    calling the @st.cache_data wrapper from a bare thread takes Streamlit cache
    locks outside any script run, which intermittently DEADLOCKED the next script
    run mid-execution — the session went permanently deaf (widget changes stored
    but no reruns: the stuck-Custom-scope bug, the Settings grey-out)."""
    try:
        raw = yf.download(ticker, interval=interval, period=period,
                          auto_adjust=True, progress=False, timeout=15)
        # yfinance sometimes returns MultiIndex columns — flatten
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if df.empty:
            return None, f"No data returned for '{ticker}'. Check the ticker symbol."
        return df, None
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=300)   # cache 5 min so re-runs don't re-download
def fetch_yahoo(ticker: str, interval: str, period: str):
    return _fetch_yahoo_raw(ticker, interval, period)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_benchmark_curve(symbol: str, start: str, end: str):
    """Daily buy-&-hold % return for SPY/QQQ over [start,end] (YYYY-MM-DD strings).
    Returns (dates_list, pct_list) where pct[0]=0.0 and pct[i]=close_i/close_0-1,
    or (None, err). Used to overlay a market benchmark on the equity chart."""
    try:
        import datetime as _dt
        _s = pd.to_datetime(start).date()
        # pad the end by a day so the final session is included
        _e = (pd.to_datetime(end) + pd.Timedelta(days=2)).date()
        # timeout is LOAD-BEARING: this runs MID-SCRIPT-RUN. An unbounded network
        # call here hung entire runs for minutes (frontend stuck on "running",
        # every widget click batched and lost — the deaf-UI bug), especially while
        # the auto-refresh thread was hitting yfinance's shared session in parallel.
        raw = yf.download(symbol, start=str(_s), end=str(_e),
                          interval="1d", auto_adjust=True, progress=False,
                          timeout=8)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        if raw is None or raw.empty or "Close" not in raw.columns:
            return None, f"No benchmark data for {symbol}"
        c = raw["Close"].dropna()
        if len(c) < 2:
            return None, f"Too few benchmark points for {symbol}"
        c0 = float(c.iloc[0])
        if c0 == 0:
            return None, "Benchmark base price is zero"
        dates = [d.to_pydatetime() if hasattr(d, "to_pydatetime") else d for d in c.index]
        pct = [float(v) / c0 - 1.0 for v in c.tolist()]
        return (dates, pct), None
    except Exception as exc:
        return None, str(exc)


def parse_tv_csv(uploaded_file):
    """
    Parse a TradingView chart-data CSV export into a standard OHLCV DataFrame.
    Handles both Unix epoch timestamps (seconds) and human-readable date strings.
    Extra indicator columns (VWAP, MAs, heatmap lines, etc.) are ignored automatically.
    """
    try:
        text = uploaded_file.read().decode("utf-8")
        df   = pd.read_csv(StringIO(text))
        df.columns = [c.strip().lower() for c in df.columns]

        remap = {
            "time": "DateTime", "open": "Open", "high": "High",
            "low":  "Low",      "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns=remap)

        if "DateTime" in df.columns:
            sample = df["DateTime"].iloc[0]
            # TradingView exports Unix timestamps (seconds since 1970) as integers
            # e.g. 1773277800 -> need unit='s'. Plain date strings are handled separately.
            if pd.api.types.is_numeric_dtype(df["DateTime"]) or str(sample).isdigit():
                df["DateTime"] = pd.to_datetime(df["DateTime"], unit="s", utc=True)
            else:
                df["DateTime"] = pd.to_datetime(df["DateTime"], utc=True, errors="coerce")
            df = df.set_index("DateTime").sort_index()

        # Keep only the 5 OHLCV columns — extra TV indicator columns are dropped here
        available = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[available].dropna()

        if df.empty:
            return None, "CSV parsed but no valid OHLCV rows found."
        return df, None
    except Exception as exc:
        return None, f"CSV parse error: {exc}"


# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


# ── Multiprocessing worker (runs a chunk of combos in a separate process) ─────
# Module-level so it's picklable. Each worker process loads the strategy from
# its file path ONCE, then evaluates every param dict in its chunk. This gives
# true multi-core parallelism (bypasses the GIL) for the heavy backtest loops.
_MP_STRAT_CACHE = {}   # per-worker-process cache: fpath -> module

def _mp_load_strategy(fpath):
    mod = _MP_STRAT_CACHE.get(fpath)
    if mod is None:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("_augur_mp_strat", fpath)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MP_STRAT_CACHE[fpath] = mod
    return mod

def _mp_eval_chunk(args):
    """Evaluate a list of param dicts in a worker process.
    args = (strategy_path, chunk_of_param_dicts, O, H, L, C, min_trades)
    Returns list of {**params, **metrics} for combos meeting min_trades."""
    fpath, chunk, O, H, L, C, min_trades = args
    mod = _mp_load_strategy(fpath)
    out = []
    for p in chunk:
        try:
            m = mod.run_backtest(O, H, L, C, **p)
        except Exception:
            m = None
        if m and m.get("num_trades", 0) >= min_trades:
            out.append({**p, **m})
    return out


# ── PC sleep prevention (Windows) ────────────────────────────────────────────
def _prevent_sleep():
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    except Exception:
        pass

def _allow_sleep():
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


# ── Expanded DB schema ────────────────────────────────────────────────────────
def _db_init_extras():
    """Add strategies, csv_files, and executions tables if not present."""
    conn = _db_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            code       TEXT,
            note       TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS csv_files (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            filename   TEXT,
            instrument TEXT,
            timeframe  TEXT,
            rows       INTEGER,
            date_from  TEXT,
            date_to    TEXT,
            created_at TEXT,
            is_master  INTEGER DEFAULT 0,
            source     TEXT DEFAULT 'tv',
            provenance TEXT DEFAULT ''
        )
    """)
    # Auto-migrate: add newer columns to pre-existing csv_files tables
    try:
        _cols = [r[1] for r in conn.execute("PRAGMA table_info(csv_files)").fetchall()]
        for _c, _ddl in [("timeframe", "TEXT"), ("is_master", "INTEGER DEFAULT 0"),
                         ("source", "TEXT DEFAULT 'tv'"), ("provenance", "TEXT DEFAULT ''"),
                         ("session", "TEXT DEFAULT ''")]:
            if _c not in _cols:
                conn.execute(f"ALTER TABLE csv_files ADD COLUMN {_c} {_ddl}")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            exec_uuid     TEXT,
            name          TEXT,
            status        TEXT DEFAULT 'queued',
            instrument    TEXT,
            timeframe     TEXT,
            data_source   TEXT,
            scope         TEXT,
            strategy_name TEXT,
            n_combos      INTEGER DEFAULT 0,
            progress      INTEGER DEFAULT 0,
            n_valid       INTEGER DEFAULT 0,
            created_at    TEXT,
            started_at    TEXT,
            finished_at   TEXT,
            run_id        INTEGER,
            error_msg     TEXT,
            config_json   TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_strategy(name, code, note=""):
    conn = _db_conn()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO strategies (name,code,note,created_at,updated_at) VALUES (?,?,?,?,?)",
        (name, code, note, now, now)
    )
    conn.commit(); conn.close()

def update_strategy(sid, name=None, code=None, note=None):
    conn = _db_conn()
    if name is not None: conn.execute("UPDATE strategies SET name=?,updated_at=? WHERE id=?",
                                      (name, datetime.now().isoformat(), sid))
    if code is not None: conn.execute("UPDATE strategies SET code=?,updated_at=? WHERE id=?",
                                      (code, datetime.now().isoformat(), sid))
    if note is not None: conn.execute("UPDATE strategies SET note=?,updated_at=? WHERE id=?",
                                      (note, datetime.now().isoformat(), sid))
    conn.commit(); conn.close()

def delete_strategy(sid):
    conn = _db_conn()
    conn.execute("DELETE FROM strategies WHERE id=?", (sid,))
    conn.commit(); conn.close()

def load_strategies():
    conn = _db_conn()
    df = pd.read_sql("SELECT * FROM strategies ORDER BY id DESC", conn)
    conn.close()
    return df

def _detect_timeframe(text: str) -> str:
    """Best-effort timeframe detection from a CSV name/filename.
    Recognizes seconds ('5s','10s','30sec'), minutes ('5m','15min'), hours,
    days, weeks, 'daily'/'weekly'/'hourly', 'tick'. Returns a normalized label
    ('5s','1m','5m','15m','1h','4h','1D','1W',…) or '' if it can't tell.
    NOTE: for sub-minute data prefer `_infer_tf_from_df` (the bar spacing is
    authoritative) — many TradingView second-chart exports omit the unit."""
    import re as _re
    t = (text or "").lower()
    # seconds first ('5s','10s','30sec', TV's '10S_hash'). Look-behind blocks a
    # number glued to letters/digits ('v20s'); the trailing not-alnum lookahead
    # (instead of \b) lets the unit butt against '_'/'.'/',' as TV exports do.
    m = _re.search(r'(?<![a-z0-9])(\d+)\s*(?:seconds?|secs?|s)(?![a-z0-9])', t)
    if m: return f"{int(m.group(1))}s"
    m = _re.search(r'(\d+)\s*(min|m)\b', t)
    if m: return f"{int(m.group(1))}m"
    m = _re.search(r'(\d+)\s*(hour|hr|h)\b', t)
    if m: return f"{int(m.group(1))}h"
    m = _re.search(r'(\d+)\s*(day|d)\b', t)
    if m: return f"{int(m.group(1))}D"
    m = _re.search(r'(\d+)\s*(week|wk|w)\b', t)
    if m: return f"{int(m.group(1))}W"
    if "daily" in t: return "1D"
    if "weekly" in t: return "1W"
    if "hourly" in t: return "1h"
    if "tick" in t: return "tick"
    return ""


def _infer_tf_from_df(df) -> str:
    """Authoritative timeframe inference from the MEDIAN spacing between bars.
    Robust to session gaps (the median ignores the minority of large gaps) and
    works when the filename carries no unit — the reliable path for sub-minute
    charts (5s/10s). Returns a normalized tag ('5s','10s','1m','5m',…) or ''."""
    try:
        if df is None or len(df) < 3:
            return ""
        idx = pd.to_datetime(pd.Series(df.index))
        secs = idx.diff().dt.total_seconds().dropna()
        secs = secs[secs > 0]
        if len(secs) < 2:
            return ""
        med = float(secs.median())
    except Exception:
        return ""
    if med <= 0:
        return ""
    cands = [(1,"1s"),(2,"2s"),(3,"3s"),(5,"5s"),(10,"10s"),(15,"15s"),(30,"30s"),
             (60,"1m"),(120,"2m"),(180,"3m"),(300,"5m"),(600,"10m"),(900,"15m"),
             (1800,"30m"),(2700,"45m"),(3600,"1h"),(7200,"2h"),(14400,"4h"),
             (86400,"1D"),(604800,"1W")]
    best = min(cands, key=lambda c: abs(med - c[0]) / c[0])
    return best[1] if abs(med - best[0]) / best[0] <= 0.5 else ""


# Micro/mini futures roots, ordered LONGEST-first so "MES" wins over "ES",
# "MNQ" over "NQ", "MGC" over "GC", etc. when scanning a filename.
_INSTR_ORDER = ["MES", "MNQ", "M2K", "MYM", "MCL", "MGC",
                "ES", "NQ", "RTY", "YM", "CL", "GC"]

def _detect_instrument(name: str) -> str:
    """Best-effort instrument key (ES/MES/NQ/…) from a TradingView export name.
    Handles exchange prefixes + continuous-contract notation
    ('CME_MINI_ES1!, 5', 'MNQ1!', 'COMEX_GC1!', 'ES=F'). Returns '' if unsure.
    Boundaries: the root may be glued to a digit ('ES1!') but not a letter
    ('MESA' must NOT match 'MES')."""
    import re as _re
    s = (name or "").upper()
    for key in _INSTR_ORDER:
        if _re.search(r'(?<![A-Z0-9])' + key + r'(?![A-Z])', s):
            return key
    return ""

def _detect_session(df) -> str:
    """Trading session of an OHLCV frame: 'rth' (regular hours only) vs 'eth'
    (24h / overnight). '' if undeterminable. Heuristic: ETH carries overnight
    bars (before 08:00 or at/after 20:00 ET); a regular-session export has
    essentially none. Keeping RTH and ETH in SEPARATE masters matters — mixing
    them gives inconsistent bar spacing that corrupts bar-based strategies."""
    try:
        idx = pd.to_datetime(pd.Series(df.index), utc=True).dt.tz_convert("US/Eastern")
        overnight = float(((idx.dt.hour < 8) | (idx.dt.hour >= 20)).mean())
        return "rth" if overnight < 0.05 else "eth"
    except Exception:
        return ""

def _rth_filter_df(df):
    """Keep only the 09:30-16:00 ET regular cash session (weekdays) of an OHLCV
    frame. Lets a 24h Yahoo pull extend an RTH-only master without contaminating
    it with overnight bars (same hours the Databento RTH masters were built on)."""
    try:
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        et   = idx.tz_convert("US/Eastern")
        mins = et.hour * 60 + et.minute
        keep = (mins >= 9 * 60 + 30) & (mins < 16 * 60) & (et.dayofweek < 5)
        return df[keep]
    except Exception:
        return df

# Common timeframe options offered in selectors (extend as needed)
TIMEFRAME_TAGS = ["1s","2s","3s","5s","10s","15s","30s","1m","2m","3m","5m","10m","15m","30m","45m","1h","2h","4h","1D","1W","tick","Other"]

def save_csv_meta(name, filename, instrument, rows, date_from, date_to, timeframe="",
                  is_master=0, source="tv", provenance="", session=""):
    conn = _db_conn()
    conn.execute(
        "INSERT INTO csv_files (name,filename,instrument,timeframe,rows,date_from,date_to,"
        "created_at,is_master,source,provenance,session) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, filename, instrument, timeframe, rows, date_from, date_to,
         datetime.now().isoformat(), int(is_master), source, provenance, session)
    )
    conn.commit(); conn.close()
    _bust_db_caches()

def delete_csv_meta(cid):
    conn = _db_conn()
    row = conn.execute("SELECT filename FROM csv_files WHERE id=?", (cid,)).fetchone()
    if row:
        # CSV files live in augur_uploads/ (CSV_DIR is defined later but path is fixed)
        fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "augur_uploads", row[0])
        try: os.remove(fpath)
        except: pass
    conn.execute("DELETE FROM csv_files WHERE id=?", (cid,))
    conn.commit(); conn.close()
    _bust_db_caches()

def update_csv_meta(cid, name=None, instrument=None, timeframe=None):
    conn = _db_conn()
    if name is not None:
        conn.execute("UPDATE csv_files SET name=? WHERE id=?", (name, cid))
    if instrument is not None:
        conn.execute("UPDATE csv_files SET instrument=? WHERE id=?", (instrument, cid))
    if timeframe is not None:
        conn.execute("UPDATE csv_files SET timeframe=? WHERE id=?", (timeframe, cid))
    conn.commit(); conn.close()
    _bust_db_caches()

def load_csv_metas():
    if (_DB_CACHE["csv"] is not None
            and time.time() - _DB_CACHE["csv_t"] < _DB_CACHE_TTL):
        return _DB_CACHE["csv"].copy()
    conn = _db_conn()
    df = pd.read_sql("SELECT * FROM csv_files ORDER BY id DESC", conn)
    conn.close()
    _DB_CACHE["csv"] = df.copy(); _DB_CACHE["csv_t"] = time.time()
    return df


# ── CSV combiner: merge multiple OHLCV files into a contiguous master ─────────
def _tf_to_minutes(tf: str) -> float:
    """Convert a timeframe label to minutes. Returns 0 for unknown/tick."""
    import re as _re
    t = (tf or "").strip().lower()
    if not t or t == "tick":
        return 0.0
    m = _re.match(r'(\d+)\s*s', t)          # seconds: '5s','10s'
    if m: return int(m.group(1)) / 60.0
    m = _re.match(r'(\d+)\s*m', t)          # minutes
    if m and 'mo' not in t: return float(int(m.group(1)))
    m = _re.match(r'(\d+)\s*h', t)          # hours
    if m: return int(m.group(1)) * 60.0
    m = _re.match(r'(\d+)\s*d', t)          # days
    if m: return int(m.group(1)) * 60.0 * 24
    m = _re.match(r'(\d+)\s*w', t)          # weeks
    if m: return int(m.group(1)) * 60.0 * 24 * 7
    return 0.0


def _read_stored_csv(filename: str):
    """Load a saved CSV (in CSV_DIR) into an OHLCV DataFrame, or (None, err)."""
    path = os.path.join(CSV_DIR, filename)
    if not os.path.exists(path):
        return None, f"File not found: {filename}"
    class _F:
        def __init__(s, b): s._b = b
        def read(s): return s._b
        def seek(s, *a): pass
    with open(path, "rb") as fh:
        return parse_tv_csv(_F(fh.read()))


def combine_ohlcv_frames(frames, timeframe: str, gap_tolerance: float = 1.5,
                         labels=None):
    """Merge a list of OHLCV DataFrames (datetime-indexed) into one.

    - Concatenates, drops duplicate timestamps (keeps last), sorts ascending.
    - Detects gaps larger than `gap_tolerance` × the expected bar interval and
      reports the contiguous segments between them.
    - If `labels` (one string per frame) is given, tags each row with its
      origin in a 'source' column and reports a per-source row breakdown.

    Returns (merged_df, info).
    """
    pairs = [(f, (labels[i] if labels and i < len(labels) else "csv"))
             for i, f in enumerate(frames) if f is not None and not f.empty]
    if not pairs:
        return None, {"error": "No valid data to combine."}

    tagged = []
    for f, lbl in pairs:
        g = f.copy()
        # Normalise every frame to UTC so mixing sources (e.g. a raw Yahoo pull
        # with a TradingView export) can't raise "Both dates must have the same
        # UTC offset" when the combined index is sliced.
        try:
            g.index = pd.to_datetime(g.index, utc=True)
        except Exception:
            pass
        g["__src"] = lbl
        tagged.append(g)
    merged = pd.concat(tagged, axis=0)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    # Per-source row counts (after dedupe, keep=last so later frames win overlaps)
    src_counts = merged["__src"].value_counts().to_dict() if "__src" in merged.columns else {}

    bar_min = _tf_to_minutes(timeframe)
    segments = []
    n_gaps = 0
    if bar_min > 0 and len(merged) > 1:
        deltas = merged.index.to_series().diff().dt.total_seconds() / 60.0
        gap_thresh = bar_min * gap_tolerance
        seg_start = merged.index[0]
        prev = merged.index[0]
        for ts, d in zip(merged.index[1:], deltas.iloc[1:]):
            if d > gap_thresh:
                seg_rows = len(merged.loc[seg_start:prev])
                segments.append((seg_start, prev, seg_rows))
                n_gaps += 1
                seg_start = ts
            prev = ts
        seg_rows = len(merged.loc[seg_start:prev])
        segments.append((seg_start, prev, seg_rows))
    else:
        segments.append((merged.index[0], merged.index[-1], len(merged)))

    largest = max(segments, key=lambda s: s[2]) if segments else None
    info = {
        "total_rows": len(merged),
        "date_from": str(merged.index[0]),
        "date_to": str(merged.index[-1]),
        "n_gaps": n_gaps,
        "segments": segments,
        "largest_segment": largest,
        "expected_bar_minutes": bar_min,
        "source_counts": src_counts,
    }
    return merged, info


def df_to_tv_csv_bytes(df) -> bytes:
    """Serialize an OHLCV DataFrame to TradingView-style CSV bytes.
    Writes Unix-second 'time' column + OHLCV so it round-trips through parse_tv_csv.
    A '__src' provenance column (if present) is written as 'source' and ignored
    by the parser (only OHLCV is read back)."""
    out = df.copy()
    idx = pd.to_datetime(out.index, utc=True)
    ns = idx.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64")
    unix = (ns // 1_000_000_000).astype("int64")
    cols = {"time": unix}
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in out.columns:
            cols[c.lower()] = out[c].values
    if "__src" in out.columns:
        cols["source"] = out["__src"].values
    flat = pd.DataFrame(cols)
    return flat.to_csv(index=False).encode("utf-8")


def save_master_csv(df, name, instrument, timeframe, source="tv",
                    provenance="", overwrite_filename=None, session="") -> tuple[bool, str]:
    """Write a combined master DataFrame to CSV_DIR and register it in csv_files.
    If overwrite_filename is given, reuse that file + update its row (in-place
    extend of an existing master)."""
    try:
        # RTH ceiling guard: a TV-drop export can carry stray post-16:00 bars
        # (16:00/16:05/16:10) that the Yahoo-only _rth_filter_df never sees. The
        # cash session's last 5-min bar starts 15:55; drop anything at/after 16:00
        # so an RTH master can never be contaminated regardless of ingest path.
        if str(session).lower() == "rth":
            try:
                _idx = df.index
                if _idx.tz is None:
                    _idx = _idx.tz_localize("UTC")
                _et = _idx.tz_convert("US/Eastern")
                df = df[(_et.hour * 60 + _et.minute) < 16 * 60]
            except Exception:
                pass
        fn = overwrite_filename or f"master_{uuid.uuid4().hex[:8]}.csv"
        raw = df_to_tv_csv_bytes(df)
        with open(os.path.join(CSV_DIR, fn), "wb") as fh:
            fh.write(raw)
        df0 = str(df.index[0])[:10]; df1 = str(df.index[-1])[:10]
        conn = _db_conn()
        if overwrite_filename:
            if session:
                conn.execute(
                    "UPDATE csv_files SET rows=?, date_from=?, date_to=?, provenance=?, "
                    "session=? WHERE filename=?",
                    (len(df), df0, df1, provenance, session, fn))
            else:
                conn.execute(
                    "UPDATE csv_files SET rows=?, date_from=?, date_to=?, provenance=? "
                    "WHERE filename=?",
                    (len(df), df0, df1, provenance, fn))
            conn.commit(); conn.close()
            _bust_db_caches()
        else:
            conn.close()
            save_csv_meta(name, fn, instrument, len(df), df0, df1,
                          timeframe=timeframe, is_master=1, source=source,
                          provenance=provenance, session=session)
        return True, fn
    except Exception as ex:
        return False, str(ex)


def _build_provenance(info, source, parts, source_csv_ids=None):
    """JSON provenance string: which parts/spans built a master, per-source
    counts, and (for exact 'in-master' detection) the source CSV ids merged in."""
    import json as _json
    return _json.dumps({
        "source": source,
        "built_at": datetime.now().isoformat(timespec="minutes"),
        "total_rows": info.get("total_rows"),
        "date_from": info.get("date_from","")[:16],
        "date_to": info.get("date_to","")[:16],
        "n_gaps": info.get("n_gaps"),
        "source_counts": info.get("source_counts", {}),
        "parts": parts,
        "source_csv_ids": list(source_csv_ids or []),
    })


def find_master(instrument, timeframe, source="tv"):
    """Return the csv_files row (dict) for an existing master matching
    instrument+timeframe+source, or None."""
    conn = _db_conn()
    try:
        df = pd.read_sql(
            "SELECT * FROM csv_files WHERE is_master=1 AND instrument=? "
            "AND timeframe=? AND source=? ORDER BY id DESC LIMIT 1",
            conn, params=(instrument, timeframe, source))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None


def list_masters():
    """All master CSVs as a DataFrame."""
    conn = _db_conn()
    try:
        df = pd.read_sql(
            "SELECT * FROM csv_files WHERE is_master=1 ORDER BY instrument,timeframe,source",
            conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def _csv_in_master(csv_row, masters_df):
    """Is this (non-master) CSV likely already folded into a master?

    Detection: EXACT (provenance records this CSV's id) is checked across ALL
    masters first; only if no exact match is found do we fall back to the
    INFERRED heuristic (same instrument+timeframe and the CSV's date span sits
    inside the master's span).
    Returns (covered: bool, master_name: str|"", exact: bool).
    """
    if masters_df is None or masters_df.empty:
        return False, "", False
    cid = csv_row.get("id")
    inst = str(csv_row.get("instrument","")).strip()
    tf   = str(csv_row.get("timeframe","")).strip()
    cf   = str(csv_row.get("date_from","")); ct = str(csv_row.get("date_to",""))
    # Pass 1: exact via provenance ids (authoritative)
    if cid is not None:
        for _, m in masters_df.iterrows():
            prov = m.get("provenance","") or ""
            if not prov:
                continue
            try:
                pj = json.loads(prov)
                if int(cid) in [int(x) for x in pj.get("source_csv_ids", [])]:
                    return True, m.get("name",""), True
            except Exception:
                pass
    # Pass 2: inferred via instrument+tf+date overlap
    for _, m in masters_df.iterrows():
        if (str(m.get("instrument","")).strip()==inst
                and str(m.get("timeframe","")).strip()==tf and inst and tf):
            mf = str(m.get("date_from","")); mt = str(m.get("date_to",""))
            if mf and mt and cf and ct and mf <= cf and ct <= mt:
                return True, m.get("name",""), False
    return False, "", False


def recommend_masters(csv_metas, masters_df):
    """Suggest masters worth building: groups of 2+ same instrument+timeframe
    non-master CSVs that aren't already covered by a master.
    Returns list of dicts: {instrument, timeframe, n_csvs, source}."""
    if csv_metas is None or csv_metas.empty:
        return []
    df = csv_metas.copy()
    if "is_master" in df.columns:
        df = df[df["is_master"].fillna(0).astype(int) == 0]
    recs = []
    grouped = df.groupby([df["instrument"].astype(str).str.strip(),
                          df["timeframe"].astype(str).str.strip()])
    for (inst, tf), grp in grouped:
        if not inst or not tf or tf.lower() == "nan":
            continue
        if len(grp) < 2:
            continue
        # Skip if a TV master already exists for this inst+tf
        if masters_df is not None and not masters_df.empty:
            ex = masters_df[(masters_df["instrument"].astype(str).str.strip()==inst)
                            & (masters_df["timeframe"].astype(str).str.strip()==tf)
                            & (masters_df["source"].astype(str).str.strip()=="tv")]
            if not ex.empty:
                continue
        recs.append({"instrument": inst, "timeframe": tf,
                     "n_csvs": len(grp), "source": "tv"})
    return recs


# ── Auto-refresh config (persisted in augur_config.json under 'autorefresh') ──
def _get_autorefresh_cfg() -> dict:
    """Returns {'enabled_global': bool, 'masters': {key: bool}} where key is
    'instrument|timeframe|source'."""
    cfg = _load_config_json()
    ar = cfg.get("autorefresh", {})
    if "masters" not in ar:
        ar["masters"] = {}
    if "enabled_global" not in ar:
        ar["enabled_global"] = False
    return ar

def _save_autorefresh_cfg(ar: dict):
    cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
    try:
        existing = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                existing = json.load(f)
        existing["autorefresh"] = ar
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass

def _ar_key(instrument, timeframe, source):
    return f"{instrument}|{timeframe}|{source}"


def _yahoo_interval_for(tf: str):
    """Map a timeframe tag to a (yahoo_interval, period) pair, or None if Yahoo
    doesn't support it."""
    iv_map = {"1m":"1m","2m":"2m","5m":"5m","15m":"15m","30m":"30m",
              "1h":"60m","1D":"1d","1W":"1wk"}
    iv = iv_map.get(tf)
    if iv is None:
        return None
    per = "7d" if iv in ("1m","2m","5m") else ("60d" if iv in ("15m","30m","60m") else "2y")
    return iv, per


def auto_refresh_masters(progress_cb=None) -> list:
    """For every master with auto-refresh enabled:
      • Yahoo masters → pull recent data and extend.
      • TradingView masters → ingest any matching files dropped in WATCH_DIR.
    Also ingests watch-folder files for ANY existing TV master (instrument+tf
    inferred from filename) when global watch is on.
    Returns a list of human-readable result strings (what changed).
    """
    results = []
    ar = _get_autorefresh_cfg()
    masters = list_masters()
    if masters.empty:
        return results

    for _, m in masters.iterrows():
        inst = str(m.get("instrument","")).strip()
        tf   = str(m.get("timeframe","")).strip()
        src  = str(m.get("source","tv")).strip()
        key  = _ar_key(inst, tf, src)
        if not ar["masters"].get(key, False):
            continue   # not toggled on for this master

        if progress_cb: progress_cb(f"Refreshing {inst} {tf} · {src}…")

        existing_df, eerr = _read_stored_csv(m["filename"])
        if existing_df is None:
            results.append(f"⚠ {m['name']}: {eerr}")
            continue
        before_rows = len(existing_df)
        before_to = str(existing_df.index[-1])[:16]
        frames = [existing_df]; labels = ["existing"]; parts = [f"existing ({before_rows:,})"]

        # Session identity (rth vs eth). Backfill the stored value the first time,
        # then keep RTH and ETH masters strictly separate so a deep RTH export
        # can't contaminate a 24h master with mismatched bar spacing.
        msess = str(m.get("session","") or "") or _detect_session(existing_df)

        # Yahoo pull — for ANY master whose instrument+timeframe Yahoo supports, not
        # only source=="yahoo", so merged (and TV) masters stay Yahoo-fresh hands-free.
        # Existing rows are preserved; Yahoo only extends/refreshes the recent end.
        # RTH masters: Yahoo intraday is 24h, so we FILTER its pull down to the
        # 09:30-16:00 ET cash session before extending (keeps RTH masters current
        # too, instead of letting them go stale).
        ivp = _yahoo_interval_for(tf)
        _yt = INSTRUMENTS.get(inst, {}).get("ticker", "") if isinstance(INSTRUMENTS.get(inst), dict) else ""
        tk = _yt or str(m.get("instrument", ""))
        if ivp and tk:
            iv, per = ivp
            ydf, yerr = _fetch_yahoo_raw(tk, iv, per)   # thread-safe: NO st.cache_data
            if ydf is not None and not ydf.empty:
                if ydf.index.tz is None:
                    ydf.index = ydf.index.tz_localize("UTC")
                if msess == "rth":
                    ydf = _rth_filter_df(ydf)
                if ydf is not None and not ydf.empty:
                    frames.append(ydf); labels.append("yahoo")
                    parts.append(f"Yahoo {tk}{' RTH' if msess=='rth' else ''} ({len(ydf):,})")
            elif yerr:
                results.append(f"⚠ {m['name']}: Yahoo {yerr}")

        # Watch-folder ingest — TradingView exports dropped for this instrument+tf
        # AND matching session (so an RTH drop never lands in an ETH master).
        ingested_files = _scan_watch_folder_for(inst, tf, session=msess)
        for fpath, fdf in ingested_files:
            frames.append(fdf); labels.append("tv-drop")
            parts.append(f"{os.path.basename(fpath)} ({len(fdf):,})")

        if len(frames) <= 1:
            continue   # nothing new to add

        merged, info = combine_ohlcv_frames(frames, tf, labels=labels)
        if merged is None or len(merged) <= before_rows:
            continue   # no net-new rows

        prov = _build_provenance(info, src, parts)
        ok, _r = save_master_csv(merged, m["name"], inst, tf, source=src,
                                 provenance=prov, overwrite_filename=m["filename"],
                                 session=msess)
        if ok:
            added = len(merged) - before_rows
            results.append(
                f"✓ {m['name']}: +{added:,} rows "
                f"({before_rows:,}→{len(merged):,}) · now through {str(merged.index[-1])[:16]}")
            # Move any ingested watch files to _ingested so they don't repeat
            if ingested_files:
                for fpath, _ in ingested_files:
                    try:
                        shutil.move(fpath, os.path.join(WATCH_DONE_DIR, os.path.basename(fpath)))
                    except Exception:
                        pass
    # Drops that match NO existing master identity (new instrument / timeframe /
    # session — e.g. your first RTH export) become brand-new masters here.
    try:
        results += _ingest_unmatched_watch_drops(masters)
    except Exception as _e:
        results.append(f"⚠ new-master ingest failed: {_e}")
    return results


def _classify_watch_file(path):
    """Load a watch-folder CSV and detect its (instrument, timeframe, session).
    Timeframe comes from the bar spacing (authoritative), falling back to the
    filename; instrument from the symbol token; session from the bar times.
    Returns (df, instrument, timeframe, session); df is None on failure."""
    dfx, err = _read_stored_csv_abs(path)
    if dfx is None or dfx.empty:
        return None, "", "", ""
    fn   = os.path.basename(path)
    inst = _detect_instrument(fn)
    tf   = _infer_tf_from_df(dfx) or _detect_timeframe(fn)
    sess = _detect_session(dfx)
    return dfx, inst, tf, sess


def _scan_watch_folder_for(instrument, timeframe, session=None):
    """Return [(path, df)] for WATCH_DIR CSVs that POSITIVELY match the given
    instrument + timeframe (detected from the symbol + bar spacing, not a loose
    substring), and — when `session` is given — the same trading session, so an
    RTH drop never merges into an ETH master (or vice-versa)."""
    out = []
    try:
        files = [f for f in os.listdir(WATCH_DIR)
                 if f.lower().endswith(".csv") and not f.startswith("_")]
    except Exception:
        return out
    for fn in files:
        p = os.path.join(WATCH_DIR, fn)
        dfx, inst, tf, sess = _classify_watch_file(p)
        if dfx is None:
            continue
        if inst != instrument or tf != timeframe:
            continue
        if session is not None and sess and sess != session:
            continue
        out.append((p, dfx))
    return out


def _ingest_unmatched_watch_drops(masters):
    """Create NEW masters from watch-folder drops whose (instrument, timeframe,
    session) is owned by NO existing master — a brand-new instrument, a new
    timeframe, or your first RTH export. Multi-chunk drops for the same identity
    are stitched (dedupe overlaps, sort, gap-detect) into one master."""
    results = []
    try:
        files = [f for f in os.listdir(WATCH_DIR)
                 if f.lower().endswith(".csv") and not f.startswith("_")]
    except Exception:
        return results
    groups = {}   # (inst, tf, session) -> [(path, df)]
    for fn in files:
        p = os.path.join(WATCH_DIR, fn)
        dfx, inst, tf, sess = _classify_watch_file(p)
        if dfx is None or not inst or not tf:
            continue   # can't route confidently — leave it for the user
        groups.setdefault((inst, tf, sess), []).append((p, dfx))
    if not groups:
        return results
    # Identities already owned by an existing master (use stored session, else
    # detect from its data) so we never create a duplicate of one that exists.
    known = set()
    if masters is not None and not masters.empty:
        for _, m in masters.iterrows():
            msess = str(m.get("session","") or "")
            if not msess:
                _mdf, _ = _read_stored_csv(m.get("filename",""))
                msess = _detect_session(_mdf) if _mdf is not None else ""
            known.add((str(m.get("instrument","")).strip(),
                       str(m.get("timeframe","")).strip(), msess))
    for (inst, tf, sess), items in groups.items():
        if (inst, tf, sess) in known:
            continue   # an existing master owns this identity → main loop handles it
        frames = [d for _, d in items]
        labels = [os.path.basename(p) for p, _ in items]
        merged, info = combine_ohlcv_frames(frames, tf, labels=labels)
        if merged is None or merged.empty:
            continue
        nm   = f"{inst} {tf}{' RTH' if sess == 'rth' else ''} (TV)"
        prov = _build_provenance(info, "tv",
                                 [f"{os.path.basename(p)} ({len(d):,})" for p, d in items])
        ok, _r = save_master_csv(merged, nm, inst, tf, source="tv",
                                 provenance=prov, session=sess)
        if ok:
            results.append(
                f"✓ NEW master {nm}: {len(merged):,} rows "
                f"({str(merged.index[0])[:10]}→{str(merged.index[-1])[:10]})")
            for p, _ in items:
                try:
                    shutil.move(p, os.path.join(WATCH_DONE_DIR, os.path.basename(p)))
                except Exception:
                    pass
            # Auto-enable refresh for the new master so a LATER batch of drops
            # keeps extending it (otherwise a second drop would sit unmatched).
            try:
                _ar = _get_autorefresh_cfg()
                _ar.setdefault("masters", {})[_ar_key(inst, tf, "tv")] = True
                _ar["enabled_global"] = True
                _save_autorefresh_cfg(_ar)
            except Exception:
                pass
    return results


def _read_stored_csv_abs(path):
    """Like _read_stored_csv but takes an absolute path (for the watch folder)."""
    if not os.path.exists(path):
        return None, "not found"
    class _F:
        def __init__(s, b): s._b = b
        def read(s): return s._b
        def seek(s, *a): pass
    try:
        with open(path, "rb") as fh:
            return parse_tv_csv(_F(fh.read()))
    except Exception as ex:
        return None, str(ex)

def upsert_exec_record(exec_uuid, name, config, status="queued"):
    conn = _db_conn()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO executions
            (exec_uuid,name,status,instrument,timeframe,data_source,scope,
             strategy_name,n_combos,created_at,config_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        exec_uuid, name, status,
        config.get("instrument",""), config.get("timeframe",""),
        config.get("data_source",""), config.get("scope",""),
        config.get("strategy_name",""), config.get("n_combos",0),
        now, json.dumps(config),
    ))
    conn.commit(); conn.close()

def update_exec_record(exec_uuid, **kwargs):
    if not kwargs: return
    conn = _db_conn()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [exec_uuid]
    conn.execute(f"UPDATE executions SET {cols} WHERE exec_uuid=?", vals)
    conn.commit(); conn.close()

def load_executions():
    conn = _db_conn()
    df = pd.read_sql("SELECT * FROM executions ORDER BY id DESC", conn)
    conn.close()
    return df


# ── Auto-optimizer (Bayesian via optuna, graceful random-search fallback) ─────
try:
    import optuna as _optuna
    _optuna.logging.set_verbosity(_optuna.logging.WARNING)
    _HAS_OPTUNA = True
except Exception:
    _HAS_OPTUNA = False


def _auto_space_from_params(default_params: dict) -> dict:
    """Build a search space spec from a strategy's DEFAULT_PARAMS.

    Each entry -> ('float', lo, hi, step) | ('int', lo, hi, step) | ('cat', [choices]).
    Bool/str params become categorical. Conditional params (depends_on) are
    included; the evaluator collapses inactive ones so they don't add noise.
    """
    space = {}
    if not default_params:
        return space
    for name, meta in default_params.items():
        if not isinstance(meta, dict):
            continue
        typ = meta.get("type", "float")
        if typ == "bool":
            space[name] = ("cat", [True, False])
        elif typ == "str":
            opts = meta.get("options") or [meta.get("default")]
            space[name] = ("cat", list(opts))
        elif typ == "int":
            space[name] = ("int", int(meta.get("min", 0)), int(meta.get("max", 10)),
                           int(meta.get("step", 1) or 1))
        else:  # float
            space[name] = ("float", float(meta.get("min", 0.0)),
                           float(meta.get("max", 1.0)),
                           float(meta.get("step", 0.0) or 0.0))
    return space


class _AutoSampler:
    """Proposes parameter sets to evaluate, maximizing a scalar objective.

    Uses Optuna (TPE/Bayesian) when available; otherwise a seeded random
    search over the same space. Same interface either way:
        ask() -> (trial_id, params_dict)
        tell(trial_id, value)            # value = objective (higher is better)
        best() -> (best_params, best_value)
    """

    def __init__(self, space: dict, n_trials: int, seed: int = 42):
        self.space = space
        self.n_trials = n_trials
        self._best_val = float("-inf")
        self._best_params = None
        if _HAS_OPTUNA:
            self._study = _optuna.create_study(
                direction="maximize",
                sampler=_optuna.samplers.TPESampler(seed=seed, n_startup_trials=12),
            )
            self._pending = {}   # trial_number -> optuna trial
        else:
            import random as _random
            self._rng = _random.Random(seed)

    def _sample_random(self):
        p = {}
        for name, spec in self.space.items():
            kind = spec[0]
            if kind == "cat":
                p[name] = self._rng.choice(spec[1])
            elif kind == "int":
                _, lo, hi, step = spec
                step = max(1, int(step))
                n = (hi - lo) // step
                p[name] = lo + step * self._rng.randint(0, max(0, n))
            else:  # float
                _, lo, hi, step = spec
                if step and step > 0:
                    n = int(round((hi - lo) / step))
                    p[name] = round(lo + step * self._rng.randint(0, max(0, n)), 6)
                else:
                    p[name] = round(self._rng.uniform(lo, hi), 6)
        return p

    def ask(self):
        if _HAS_OPTUNA:
            trial = self._study.ask()
            p = {}
            for name, spec in self.space.items():
                kind = spec[0]
                if kind == "cat":
                    p[name] = trial.suggest_categorical(name, spec[1])
                elif kind == "int":
                    _, lo, hi, step = spec
                    p[name] = trial.suggest_int(name, lo, hi, step=max(1, int(step)))
                else:
                    _, lo, hi, step = spec
                    if step and step > 0:
                        p[name] = trial.suggest_float(name, lo, hi, step=step)
                    else:
                        p[name] = trial.suggest_float(name, lo, hi)
            self._pending[trial.number] = trial
            return trial.number, p
        else:
            tid = self._rng.random()
            return tid, self._sample_random()

    def tell(self, trial_id, value):
        v = float(value) if (value is not None and np.isfinite(value)) else float("-inf")
        if _HAS_OPTUNA:
            tr = self._pending.pop(trial_id, None)
            if tr is not None:
                self._study.tell(tr, v)
        if v > self._best_val:
            self._best_val = v

    def best(self):
        return self._best_params, self._best_val


# ══════════════════════════════════════════════════════════════════════════════
#  AGENTIC AI OPTIMIZATION ENGINE  (🧠 AI Optimize · 🧬 AI Evolve)
# ──────────────────────────────────────────────────────────────────────────────
#  Round loop: run a sweep → send results to Claude → Claude proposes the next
#  search region (and, in Evolve mode, optional strategy-code edits) → apply →
#  repeat. Out-of-sample validation (default on) splits data so the AI can't
#  fool itself by overfitting the in-sample window.
# ══════════════════════════════════════════════════════════════════════════════

AI_DEFAULT_ROUNDS = 5
AI_OOS_SPLIT = 0.75   # optimize on first 75%, validate on last 25%
# Minimum out-of-sample trades before we'll render a robustness verdict. Below
# this the OOS sample is statistical noise, so we say "too few to judge" rather
# than pretend. (A real edge needs far more; this is just the floor for honesty.)
OOS_MIN_TRADES = 10
# Walk-forward champion gate: a fold's champion must have at least this many
# WINNING and this many LOSING trades, so a few-loss profit-factor mirage (the
# engine's optimistic intrabar fills can spit out PF 100+) can't win a fold.
# Among configs that clear it, the champion is chosen by NET PNL, not raw max-PF.
WF_MIN_SIDE = 5
# Two sanity caps on champion / headline selection, because a one-way trend lets the
# optimizer manufacture fake edges the wins/losses gate can't catch:
#   • TRADE RATE — a config trading more often than this is implausibly frequent for a
#     breakout strategy and is almost always a high-frequency fill / micro-structure
#     artifact (a walk-forward fold hit 800-1,350 trades at PF 14-16 that "survived"
#     out-of-sample yet isn't tradeable). Normal configs here sit ~0.004-0.010/bar.
#   • PROFIT FACTOR — an in-sample PF above this over a full window is almost always
#     overfit or a fill artifact (real edges sit ~1.3-3). The optimizer games a lone
#     rate cap right to its boundary, so the PF ceiling is what actually closes it.
# Offending configs are DEMOTED from headline + champion selection (still shown in the
# results table; only the ranking changes).
MAX_TRADE_RATE = 0.015   # trades per bar (~1 per 67 bars ≈ a couple per session day)
MAX_PF = 6.0


def _split_is_oos(df, split=AI_OOS_SPLIT):
    """Chronological in-sample / out-of-sample split. Returns (is_df, oos_df)."""
    n = len(df)
    k = int(n * split)
    return df.iloc[:k], df.iloc[k:]


def _apply_costs(m, cost_pts):
    """Re-derive NET metrics from a backtest's trade list after subtracting
    `cost_pts` (commission + slippage, in points) from EACH round-trip trade.
    Cost scales with trade count, so high-frequency configs are penalised hardest
    — which is the point. Needs the trade list (return_trades=True); returns the
    metrics unchanged if it's absent."""
    trades = m.get("trades") if isinstance(m, dict) else None
    if not trades:
        return m
    net = []
    for t in trades:
        nt = list(t)
        if len(nt) >= 3:
            nt[2] = nt[2] - cost_pts        # trade pnl is t[2], in points
        net.append(tuple(nt))
    pnls   = [t[2] for t in net]
    n      = len(pnls)
    wins   = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw     = sum(x for x in pnls if x > 0)
    gl     = -sum(x for x in pnls if x < 0)
    total  = float(sum(pnls))
    if   gl > 1e-9: pf = gw / gl
    elif gw > 0:    pf = float("inf")
    else:           pf = 0.0
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    out = dict(m)
    out.update({"total_pnl": total, "num_trades": n,
                "win_rate": (100.0 * wins / n) if n else 0.0,
                "profit_factor": pf, "max_drawdown": float(mdd),
                "avg_pnl": (total / n) if n else 0.0,
                "wins": wins, "losses": losses, "trades": net})
    return out


def _ai_quick_grid_eval(strat_module, O, H, L, C, combos, min_trades, cost_pts=0.0):
    """Run a list of param dicts against a strategy module; return list of
    {**params, **metrics} for those meeting min_trades, NET of cost_pts per trade
    (commission+slippage) so AI runs match Auto-Optimize. Used per AI round."""
    out = []
    for p in combos:
        try:
            if cost_pts > 0:
                m = _apply_costs(strat_module.run_backtest(O, H, L, C, return_trades=True, **p), cost_pts)
            else:
                m = strat_module.run_backtest(O, H, L, C, **p)
        except Exception:
            m = None
        if m and m.get("num_trades", 0) >= min_trades:
            # Keep only scalar fields. return_trades=True (used for cost-netting)
            # adds a bulky 'trades' LIST to m; _ai_results_digest calls .unique()
            # per column and would choke on the unhashable list. Strip non-scalars.
            rec = {k: v for k, v in {**p, **m}.items()
                   if not isinstance(v, (list, tuple, dict, set, np.ndarray))}
            out.append(rec)
    return out


def _wf_gate(strat_module, O, H, L, C, candidates, cost_pts=0.0, volumes=None,
             n_windows=4, min_oos_trades=8, hold_frac=0.6, max_try=10, test_start_frac=0.0):
    """WALK-FORWARD GATE with fallback. Given ranked candidate configs (best→worst),
    test each FIXED config across `n_windows` sequential time windows spanning the
    HELD-OUT region [test_start_frac … end]. The FIRST candidate profitable (PF>1) in
    ≥ hold_frac of its ACTIVE windows passes — that's the deployable config. Tries up to
    `max_try` candidates so a survivor deeper in the list isn't missed (the 'go back
    enough' requirement). For an HONEST out-of-sample gate the caller must rank the
    candidates on data BEFORE test_start_frac (so the test windows are truly unseen);
    test_start_frac=0 tests the full series (a consistency check, not pure OOS).
    Returns (survivor_cfg_or_None, attempts) — attempts lists per-candidate
    {rank, config, windows[], active, held, passed} for transparency."""
    n = len(C)
    t0 = int(n * max(0.0, min(0.9, test_start_frac)))
    span = n - t0
    bounds = [t0 + int(round(k * span / n_windows)) for k in range(n_windows + 1)]
    attempts = []
    for ci, cfg in enumerate(candidates[:max_try]):
        windows = []
        for w in range(n_windows):
            a, b = bounds[w], bounds[w + 1]
            if b - a < 30:
                continue
            v = volumes[a:b] if volumes is not None else None
            try:
                m = strat_module.run_backtest(O[a:b], H[a:b], L[a:b], C[a:b],
                                              volumes=v, return_trades=True, **cfg)
                if cost_pts > 0 and m:
                    m = _apply_costs(m, cost_pts)
            except Exception:
                m = None
            tr  = int((m or {}).get("num_trades", 0) or 0)
            pf  = float((m or {}).get("profit_factor", 0) or 0) if m else 0.0
            pnl = float((m or {}).get("total_pnl", 0) or 0) if m else 0.0
            windows.append({"window": w + 1, "trades": tr,
                            "pf": round(pf, 2), "pnl": round(pnl, 2)})
        active = [x for x in windows if x["trades"] >= min_oos_trades]
        held   = [x for x in active if x["pf"] > 1.0 and x["pnl"] > 0]
        passed = (len(active) >= max(2, n_windows // 2)
                  and len(active) > 0 and (len(held) / len(active)) >= hold_frac)
        attempts.append({"rank": ci + 1, "config": cfg, "windows": windows,
                         "active": len(active), "held": len(held), "passed": passed})
        if passed:
            return cfg, attempts
    return None, attempts


def _ai_results_digest(records, top_n=12):
    """Compress a round's results into a compact text table for the AI prompt.
    Sorted by total_pnl desc; only the most informative columns."""
    if not records:
        return "No valid results (all combos failed or had too few trades)."
    df = pd.DataFrame(records).sort_values("total_pnl", ascending=False)
    keep_metrics = ["total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown"]
    param_cols = [c for c in df.columns if c not in {
        "total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
        "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd"}]
    cols = param_cols + [c for c in keep_metrics if c in df.columns]
    head = df[cols].head(top_n)
    lines = ["\t".join(cols)]
    for _, r in head.iterrows():
        lines.append("\t".join(
            f"{r[c]:.4g}" if isinstance(r[c], (int, float, np.floating)) else str(r[c])
            for c in cols))
    # Also summarize ranges explored
    summary = []
    for c in param_cols:
        vals = df[c].dropna().unique()
        if len(vals):
            try:
                summary.append(f"{c}: {min(vals):g}…{max(vals):g}")
            except Exception:
                summary.append(f"{c}: {list(vals)[:5]}")
    return ("Top results this round (tab-separated):\n" + "\n".join(lines)
            + "\n\nRanges explored:\n" + " · ".join(summary))


_AI_OPT_SYSTEM = (
    "You are a quantitative trading-strategy optimizer embedded in a backtesting "
    "tool called Augur. Each round you receive: the strategy's tunable parameters "
    "(with min/max/type), the results of the latest backtest sweep (top configs by "
    "total PNL, plus in-sample vs out-of-sample PNL), and the best config found so "
    "far. Your job: propose the NEXT set of parameter ranges to search, focusing the "
    "search where results look strongest while avoiding overfitting (a config that "
    "wins in-sample but collapses out-of-sample is overfit — distrust it). "
    "Respond ONLY with a compact JSON object, no prose, no markdown fences. Schema:\n"
    "{\n"
    '  "reasoning": "<=2 sentences on what you learned and your next move",\n'
    '  "next_ranges": { "<param>": [v1, v2, ...], ... },   // discrete values to try next per parameter\n'
    '  "stop": false   // set true if further search is unlikely to help\n'
    "}\n"
    "Only include parameters you want to change; omit others to keep their current "
    "search values. Keep each parameter's list to 2-5 values so the grid stays small."
)

_AI_EVOLVE_SYSTEM = (
    "You are a quantitative trading-strategy engineer embedded in Augur. In addition "
    "to tuning parameters, you may REWRITE the strategy's Python code to improve it "
    "(e.g. add a filter, change exit logic, fix a weakness visible in the results). "
    "You receive the current full strategy source, its parameters, and backtest "
    "results (in-sample vs out-of-sample). A config that wins in-sample but fails "
    "out-of-sample is overfit — prefer robust, simple changes over complex ones that "
    "only fit noise. The strategy file MUST keep the Augur plugin contract: module "
    "globals STRATEGY_NAME, DEFAULT_PARAMS (dict of {type,min,max,step,label,tooltip}), "
    "PARAM_GRID_PRESETS, and a run_backtest(opens,highs,lows,closes,**params,"
    "return_trades=False,_stop_event=None,_pause_event=None) that returns a dict with "
    "total_pnl,num_trades,win_rate,profit_factor,max_drawdown,avg_pnl,wins,losses. "
    "Respond ONLY with compact JSON, no markdown fences. Schema:\n"
    "{\n"
    '  "reasoning": "<=3 sentences",\n'
    '  "next_ranges": { "<param>": [..] },\n'
    '  "code_edit": null,            // OR a COMPLETE new strategy .py file as a string\n'
    '  "code_edit_summary": "",      // 1 line describing the code change, if any\n'
    '  "stop": false\n'
    "}\n"
    "Only set code_edit when a code change is warranted; most rounds should be null. "
    "When you do edit, return the ENTIRE file, not a diff."
)


def ai_propose_next(api_key, mode, strategy_src, default_params, digest,
                    best_config, round_num, total_rounds, oos_note=""):
    """Call Claude to get the next-round proposal. Returns (proposal_dict, error)."""
    import requests, json as _json
    system = _AI_EVOLVE_SYSTEM if mode == "evolve" else _AI_OPT_SYSTEM
    param_spec = {k: {kk: vv for kk, vv in v.items()
                      if kk in ("type", "min", "max", "step", "options")}
                  for k, v in (default_params or {}).items()}
    user = (
        f"Round {round_num} of {total_rounds}.\n\n"
        f"PARAMETERS:\n{_json.dumps(param_spec, indent=0)}\n\n"
        f"BEST CONFIG SO FAR:\n{_json.dumps(best_config, default=str)}\n\n"
        f"{oos_note}\n\n"
        f"LATEST RESULTS:\n{digest}\n"
    )
    if mode == "evolve":
        user += f"\n\nCURRENT STRATEGY SOURCE:\n```python\n{strategy_src}\n```"
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": 8000 if mode == "evolve" else 1500,
                  "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=120,
        )
        if resp.status_code != 200:
            return None, f"API error {resp.status_code}: {resp.text[:200]}"
        text = resp.json()["content"][0]["text"].strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        prop = _json.loads(text)
        return prop, None
    except _json.JSONDecodeError as je:
        return None, f"AI returned invalid JSON: {je}"
    except Exception as ex:
        return None, str(ex)


def validate_strategy_code(code: str):
    """Validate AI-written strategy code against the plugin contract WITHOUT
    persisting it. Returns (module, error). Runs a tiny smoke backtest."""
    import tempfile as _tf
    try:
        compile(code, "<ai_strategy>", "exec")   # syntax
    except SyntaxError as se:
        return None, f"Syntax error: {se}"
    tmpf = None
    try:
        with _tf.NamedTemporaryFile(suffix=".py", delete=False, mode="w",
                                    encoding="utf-8") as f:
            f.write(code); tmpf = f.name
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("_ai_cand", tmpf)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for attr in ("STRATEGY_NAME", "DEFAULT_PARAMS", "run_backtest"):
            if not hasattr(mod, attr):
                return None, f"Missing required '{attr}'"
        if not isinstance(mod.DEFAULT_PARAMS, dict) or not mod.DEFAULT_PARAMS:
            return None, "DEFAULT_PARAMS must be a non-empty dict"
        # Smoke test: run on synthetic data with default params
        import numpy as _np
        n = 300; rng = _np.random.RandomState(0)
        c = _np.cumsum(rng.randn(n)) + 100
        o = c + rng.randn(n) * 0.2
        h = _np.maximum(o, c) + 0.3; l = _np.minimum(o, c) - 0.3
        defaults = {k: v.get("default") for k, v in mod.DEFAULT_PARAMS.items()
                    if isinstance(v, dict)}
        res = mod.run_backtest(o, h, l, c, **defaults)
        if res is not None:
            for mk_ in ("total_pnl", "num_trades", "win_rate"):
                if mk_ not in res:
                    return None, f"run_backtest result missing '{mk_}'"
        return mod, None
    except Exception as ex:
        return None, f"Validation run failed: {ex}"
    finally:
        if tmpf:
            try: os.unlink(tmpf)
            except Exception: pass


# ── Execution Manager (process-level singleton via cache_resource) ────────────
@st.cache_resource
def get_exec_manager():
    """Survives ALL Streamlit reruns and tab navigation — lives in process memory."""
    return _ExecManager()


class _ExecManager:
    """Thread pool + live execution tracking. Writes progress to SQLite."""

    MAX_WORKERS = 2

    def __init__(self):
        self._pool   = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="augur")
        self._execs  = {}          # uuid -> live dict
        self._lock   = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────
    def submit(self, exec_uuid: str, config: dict,
               df: pd.DataFrame, multiplier: float, min_trades: int):
        stop_ev  = threading.Event()
        pause_ev = threading.Event()
        pause_ev.set()          # start unpaused

        with self._lock:
            self._execs[exec_uuid] = {
                "uuid":     exec_uuid,
                "name":     config.get("name", exec_uuid[:8]),
                "status":   "running",
                "progress": 0,
                "total":    0,
                "n_valid":  0,
                "start_ts": time.time(),
                "instrument": config.get("instrument",""),
                "timeframe":  config.get("timeframe",""),
                "scope":      config.get("scope",""),
                "strategy_name": config.get("strategy_name",""),
                "strategy_path": config.get("strategy_path",""),
                "source_name":   config.get("source_name",""),
                "n_combos":   config.get("n_combos",0),
                "stop_ev":  stop_ev,
                "pause_ev": pause_ev,
                "results":  None,
                "error":    None,
            }

        _prevent_sleep()
        update_exec_record(exec_uuid, status="running",
                           started_at=datetime.now().isoformat())

        future = self._pool.submit(
            self._run_job, exec_uuid, config, df, multiplier, min_trades,
            stop_ev, pause_ev,
        )

        def _done(f):
            _allow_sleep()
            err = f.exception()
            with self._lock:
                ex = self._execs.get(exec_uuid, {})
                if err:
                    ex["status"] = "error"
                    ex["error"]  = str(err)
                    update_exec_record(exec_uuid, status="error",
                                       finished_at=datetime.now().isoformat(),
                                       error_msg=str(err))
                elif stop_ev.is_set():
                    ex["status"] = "stopped"
                    update_exec_record(exec_uuid, status="stopped",
                                       finished_at=datetime.now().isoformat())
                else:
                    ex["status"] = "completed"
                    update_exec_record(exec_uuid, status="completed",
                                       finished_at=datetime.now().isoformat())

        future.add_done_callback(_done)

    def pause(self, exec_uuid):
        with self._lock:
            ex = self._execs.get(exec_uuid)
            if ex and ex["status"] == "running":
                ex["pause_ev"].clear()
                ex["status"] = "paused"
                update_exec_record(exec_uuid, status="paused")

    def resume(self, exec_uuid):
        with self._lock:
            ex = self._execs.get(exec_uuid)
            if ex and ex["status"] == "paused":
                ex["pause_ev"].set()
                ex["status"] = "running"
                update_exec_record(exec_uuid, status="running")

    def stop(self, exec_uuid):
        with self._lock:
            ex = self._execs.get(exec_uuid)
            if ex:
                ex["stop_ev"].set()
                ex["pause_ev"].set()   # unblock if paused
                ex["status"] = "stopped"
                update_exec_record(exec_uuid, status="stopped",
                                   finished_at=datetime.now().isoformat())

    def get(self, exec_uuid):
        with self._lock:
            return dict(self._execs.get(exec_uuid, {}))

    def get_all(self):
        with self._lock:
            return [dict(v) for v in self._execs.values()]

    def get_active_count(self):
        with self._lock:
            return sum(1 for v in self._execs.values()
                       if v["status"] in ("running","paused"))

    def best_result(self, exec_uuid):
        with self._lock:
            return (self._execs.get(exec_uuid) or {}).get("results")

    # ── background worker ─────────────────────────────────────────────────
    def _run_job(self, exec_uuid, config, df, multiplier, min_trades,
                 stop_ev, pause_ev):
        O = df["Open"].to_numpy(dtype=float)
        H = df["High"].to_numpy(dtype=float)
        L = df["Low"].to_numpy(dtype=float)
        C = df["Close"].to_numpy(dtype=float)

        # Use the strategy that was active when this run was BUILT (captured in
        # config), not whatever is globally active now — so switching strategies
        # in the UI mid-run can't make a run use the wrong strategy.
        _run_strat_path = config.get("strategy_path", "") or ""
        _run_strat = None
        if _run_strat_path and os.path.exists(_run_strat_path):
            _run_strat, _ = _load_strategy_module(_run_strat_path)
        if _run_strat is None:
            _run_strat = _get_active_strategy()   # fallback
        # Diagnostic fingerprint: prove WHICH strategy this run actually uses.
        # Printed to the terminal so identical-results-across-strategies bugs
        # are immediately visible (different name+hash = genuinely different code).
        try:
            import hashlib as _hl
            _src_for_hash = ""
            if _run_strat_path and os.path.exists(_run_strat_path):
                with open(_run_strat_path, encoding="utf-8") as _hf:
                    _src_for_hash = _hf.read()
            _code_hash = _hl.md5(_src_for_hash.encode()).hexdigest()[:8] if _src_for_hash else "????"
            print(f"[AUGUR run] strategy='{getattr(_run_strat,'STRATEGY_NAME','?')}' "
                  f"file={os.path.basename(_run_strat_path) or '(active)'} "
                  f"code_hash={_code_hash} opt_mode={config.get('opt_mode')}")
        except Exception:
            _code_hash = "????"

        # Per-trade trading costs (commission + slippage), in POINTS per round trip.
        # commission $ → points via the contract multiplier; slippage is already pts.
        _comm_usd = float(config.get("commission_usd", 0) or 0)
        _slip_pts = float(config.get("slippage_pts", 0) or 0)
        _cost_pts = ((_comm_usd / multiplier) if multiplier else 0.0) + _slip_pts

        def _bt(*a, **kw):
            """Run THIS run's strategy. With costs on, re-derive every metric from
            the trade list NET of commission+slippage so the optimizer can't crown
            cost-bleed high-frequency configs."""
            fn = (_run_strat.run_backtest
                  if (_run_strat and hasattr(_run_strat, "run_backtest"))
                  else run_backtest)
            if _cost_pts <= 0:
                return fn(*a, **kw)
            _want = kw.get("return_trades", False)
            kw = dict(kw); kw["return_trades"] = True
            m = fn(*a, **kw)
            if not m:
                return m
            m = _apply_costs(m, _cost_pts)
            if not _want:
                m.pop("trades", None)
            return m

        _strat_dp = getattr(_run_strat, "DEFAULT_PARAMS", None) if _run_strat else None

        # ── Session-id + volume plumbing ──────────────────────────────────────
        # Make session-anchored strategies (daily bias, flat-by-close, VWAP) work
        # in-app, not just in the test harness. We derive a per-bar session id
        # (day_id) and a volume array ONCE, then slice them in lockstep with
        # O/H/L/C at each eval window. CRITICAL: pass day_id/volumes ONLY to a
        # strategy whose run_backtest declares them (or accepts **kwargs). Older
        # strategies (ENGU 1/GROK/ENGU 2) don't, and an unexpected-kwarg TypeError
        # gets swallowed by the eval try/except into a silent "0 valid" — the same
        # failure mode as the old multiprocessing bug. Introspection avoids that.
        _V = df["Volume"].to_numpy(dtype=float) if "Volume" in df.columns else None
        try:
            _eidx = pd.to_datetime(pd.Series(df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAY = pd.factorize(_eidx.dt.date)[0].astype("int64")
        except Exception:
            _DAY = None
        try:
            import inspect as _inspect
            _bt_fn0 = (_run_strat.run_backtest
                       if (_run_strat and hasattr(_run_strat, "run_backtest")) else run_backtest)
            _sp = _inspect.signature(_bt_fn0).parameters
            _has_kw = any(p.kind == p.VAR_KEYWORD for p in _sp.values())
            _pass_vol = (_V is not None) and (_has_kw or ("volumes" in _sp))
            _pass_day = (_DAY is not None) and (_has_kw or ("day_id" in _sp))
        except Exception:
            _pass_vol = _pass_day = False

        def _sx(_a, _b):
            """Per-window session/volume extras, filtered to what the strategy accepts."""
            _e = {}
            if _pass_vol: _e["volumes"] = _V[_a:_b]
            if _pass_day: _e["day_id"]  = _DAY[_a:_b]
            return _e
        if _pass_vol or _pass_day:
            print(f"[AUGUR run] session plumbing on: day_id={_pass_day} volumes={_pass_vol}")

        opt_mode = config.get("opt_mode", "grid")
        records = []

        if opt_mode == "auto":
            # ── Bayesian / random auto-search maximizing total PNL ──────────
            n_trials = int(config.get("n_trials", 200))
            space = _auto_space_from_params(_strat_dp)
            _param_keys = list(space.keys())
            _oos_on = bool(config.get("oos_on", True)) and len(C) >= 200
            _oos_method = config.get("oos_method", "single")

            # Collapse inactive conditional params to their default (clean signature).
            def _collapse(p):
                pe = dict(p)
                if _strat_dp:
                    for k, meta in _strat_dp.items():
                        cond = meta.get("depends_on") if isinstance(meta, dict) else None
                        if cond and k in pe and not all(p.get(dk) == dv
                                                        for dk, dv in cond.items()):
                            pe[k] = meta.get("default")
                return pe

            if _oos_on and _oos_method == "walkforward" and len(C) >= 4000:
                # ── WALK-FORWARD (TODO #7) ─────────────────────────────────
                # Anchored: each fold RE-OPTIMIZES on all history up to its test
                # slice (best use of thin data), then tests that fold's champion
                # — picked by in-sample profit factor — on the next unseen slice.
                # One champion row per fold → param drift + per-fold OOS are
                # visible. Folds auto-fit the bar count.
                _n = len(C)
                # Folds scale with data: ~one per 3k bars, 2-8. A year of intraday
                # supports more folds (more regimes) than a few weeks; capped so
                # each test window keeps enough trades to read.
                _wf_req = int(config.get("wf_folds", 0) or 0)
                n_folds = (max(2, min(8, _wf_req)) if _wf_req >= 2
                           else min(8, max(2, _n // 3000)))
                _init  = int(_n * 0.40)
                _tsize = max(1, (_n - _init) // n_folds)
                n_total = n_trials * n_folds
                update_exec_record(exec_uuid, n_combos=n_total)
                with self._lock:
                    if exec_uuid in self._execs:
                        self._execs[exec_uuid]["total"] = n_total
                _done = 0
                for _f in range(n_folds):
                    if stop_ev.is_set():
                        break
                    _tr_end = _init + _f * _tsize
                    _te_s   = _tr_end
                    _te_e   = _n if _f == n_folds - 1 else _te_s + _tsize
                    _Otr, _Htr, _Ltr, _Ctr = O[:_tr_end], H[:_tr_end], L[:_tr_end], C[:_tr_end]
                    _Ote, _Hte, _Lte, _Cte = O[_te_s:_te_e], H[_te_s:_te_e], L[_te_s:_te_e], C[_te_s:_te_e]
                    _samp = _AutoSampler(space, n_trials, seed=42)
                    _recs = []
                    for _i in range(n_trials):
                        if stop_ev.is_set():
                            break
                        pause_ev.wait()
                        _tid, _p = _samp.ask()
                        _pe = _collapse(_p)
                        _m = _bt(_Otr, _Htr, _Ltr, _Ctr, **_sx(0, _tr_end), **_pe)
                        if _m and _m["num_trades"] >= min_trades:
                            _samp.tell(_tid, float(_m["total_pnl"]))
                            _recs.append({**_pe, **_m})
                        else:
                            _samp.tell(_tid, float("-inf"))
                        _done += 1
                        if _done % 10 == 0:
                            with self._lock:
                                if exec_uuid in self._execs:
                                    self._execs[exec_uuid]["progress"] = _done
                                    self._execs[exec_uuid]["n_valid"]  = len(records)
                            update_exec_record(exec_uuid, progress=_done, n_valid=len(records))
                    if not _recs:
                        continue
                    # Champion = best NET PNL among configs that clear a realism
                    # gate (>= WF_MIN_SIDE wins AND >= WF_MIN_SIDE losses), so a
                    # few-loss profit-factor MIRAGE can't win the fold — an
                    # un-gated max-PF pick was crowning PF-100+ overfits. Falls
                    # back to best PNL if a one-regime stretch leaves nothing
                    # balanced (the fold still shows, just flagged thin downstream).
                    _twin = max(1, len(_Ctr))
                    _wfg = [r for r in _recs
                            if int(r.get("wins", 0) or 0)   >= WF_MIN_SIDE
                            and int(r.get("losses", 0) or 0) >= WF_MIN_SIDE
                            and (int(r.get("num_trades", 0) or 0) / _twin) <= MAX_TRADE_RATE
                            and float(r.get("profit_factor", 0) or 0) <= MAX_PF]
                    _champ = max(_wfg or _recs,
                                 key=lambda r: float(r.get("total_pnl", 0) or 0))
                    _pp = {k: _champ[k] for k in _param_keys if k in _champ}
                    try:
                        _om = _bt(_Ote, _Hte, _Lte, _Cte, **_sx(_te_s, _te_e), **_pp)
                    except Exception:
                        _om = None
                    _row = dict(_champ)
                    _row["fold"]       = _f + 1
                    _row["test_bars"]  = _te_e - _te_s
                    _row["oos_pnl"]    = float(_om["total_pnl"]) if _om else 0.0
                    _row["oos_trades"] = int(_om["num_trades"]) if _om else 0
                    _row["oos_pf"]     = float(_om.get("profit_factor", 0)) if _om else 0.0
                    records.append(_row)
                    with self._lock:
                        if exec_uuid in self._execs:
                            self._execs[exec_uuid]["n_valid"] = len(records)

            else:
                # ── SINGLE split (or no OOS): optimize on first slice, re-test ──
                #    every surviving config on the held-out tail.
                sampler = _AutoSampler(space, n_trials, seed=42)
                n_total = n_trials
                update_exec_record(exec_uuid, n_combos=n_total)
                with self._lock:
                    if exec_uuid in self._execs:
                        self._execs[exec_uuid]["total"] = n_total
                if _oos_on:
                    _ksplit = int(len(C) * AI_OOS_SPLIT)
                    Ois, His, Lis, Cis = O[:_ksplit], H[:_ksplit], L[:_ksplit], C[:_ksplit]
                    Oo,  Ho,  Lo,  Co  = O[_ksplit:], H[_ksplit:], L[_ksplit:], C[_ksplit:]
                else:
                    Ois, His, Lis, Cis = O, H, L, C
                    _ksplit = len(C)

                seen_sigs = set()
                for idx in range(n_trials):
                    if stop_ev.is_set():
                        break
                    pause_ev.wait()
                    if stop_ev.is_set():
                        break
                    tid, p = sampler.ask()
                    p_eval = _collapse(p)
                    m = _bt(Ois, His, Lis, Cis, **_sx(0, _ksplit), **p_eval)
                    if m and m["num_trades"] >= min_trades:
                        obj = float(m["total_pnl"])
                        sig = tuple(sorted(p_eval.items()))
                        if sig not in seen_sigs:
                            seen_sigs.add(sig)
                            records.append({**p_eval, **m})
                    else:
                        obj = float("-inf")   # penalize invalid (too few trades)
                    sampler.tell(tid, obj)
                    if idx % 10 == 0 or idx == n_total - 1:
                        with self._lock:
                            if exec_uuid in self._execs:
                                self._execs[exec_uuid]["progress"] = idx + 1
                                self._execs[exec_uuid]["n_valid"]  = len(records)
                        update_exec_record(exec_uuid, progress=idx+1, n_valid=len(records))

                if _oos_on and records:
                    for _rec in records:
                        _pp = {k: _rec[k] for k in _param_keys if k in _rec}
                        try:
                            _om = _bt(Oo, Ho, Lo, Co, **_sx(_ksplit, len(C)), **_pp)
                        except Exception:
                            _om = None
                        _rec["oos_pnl"]    = float(_om["total_pnl"]) if _om else 0.0
                        _rec["oos_trades"] = int(_om["num_trades"])  if _om else 0
                        _rec["oos_pf"]     = float(_om.get("profit_factor", 0)) if _om else 0.0

        else:
            # ── Grid search (exhaustive) — parallelized across CPU cores ─────
            grid = config.get("grid", SCOPE_GRIDS["Short  (~216 combos  · ~5 sec)"])
            combo_dicts = _effective_combos(grid, _strat_dp)
            n_total = len(combo_dicts)
            update_exec_record(exec_uuid, n_combos=n_total)
            with self._lock:
                if exec_uuid in self._execs:
                    self._execs[exec_uuid]["total"] = n_total

            # Resolve THIS run's strategy file path for worker processes
            _spath = config.get("strategy_path", "") or _run_strat_path
            if not (_spath and os.path.exists(_spath)):
                try:
                    _spath = get_strategy_registry().get("current_path", "") or ""
                except Exception:
                    _spath = ""

            n_workers = int(config.get("n_workers", DEFAULT_WORKERS))
            # ── Multiprocessing via augur_mp_worker (streamlit-free) ──────────
            # v5.8.7 disabled MP because spawn-mode workers re-imported this whole
            # Streamlit app and every combo silently errored. The dedicated worker
            # module imports only numpy/stdlib, so workers stay clean. The OHLCV
            # arrays ship ONCE per worker (pool initializer), params per chunk.
            # Pool spin-up costs a few seconds → only worth it for bigger grids.
            use_mp = (n_workers > 1 and n_total >= 200
                      and bool(_spath) and os.path.exists(_spath))

            if use_mp:
                done_combos = 0
                _mp_err_first = None; _mp_err_n = 0; _max_tr_seen = 0
                try:
                    import augur_mp_worker as _mpw
                    _initargs = (_spath, O, H, L, C,
                                 (_V if _pass_vol else None),
                                 (_DAY if _pass_day else None),
                                 _cost_pts)
                    chunk_sz = max(8, math.ceil(n_total / (n_workers * 6)))
                    _idx_combos = list(enumerate(combo_dicts))
                    chunks = [_idx_combos[i:i + chunk_sz]
                              for i in range(0, n_total, chunk_sz)]
                    _t_mp0 = time.time()
                    _by_idx = {}
                    with ProcessPoolExecutor(max_workers=n_workers,
                                             initializer=_mpw.init_worker,
                                             initargs=_initargs) as pool:
                        futs = {pool.submit(_mpw.eval_chunk, ch): len(ch)
                                for ch in chunks}
                        from concurrent.futures import as_completed as _asc
                        for f in _asc(futs):
                            if stop_ev.is_set():
                                for ff in futs:
                                    ff.cancel()
                                break
                            pause_ev.wait()
                            for _ci, _cm, _cerr in f.result():
                                if _cerr is not None:
                                    _mp_err_n += 1
                                    if _mp_err_first is None:
                                        _mp_err_first = _cerr
                                elif _cm:
                                    if _cm["num_trades"] > _max_tr_seen:
                                        _max_tr_seen = _cm["num_trades"]
                                    if _cm["num_trades"] >= min_trades:
                                        _by_idx[_ci] = _cm
                            done_combos += futs[f]
                            with self._lock:
                                if exec_uuid in self._execs:
                                    self._execs[exec_uuid]["progress"] = done_combos
                                    self._execs[exec_uuid]["n_valid"]  = len(_by_idx)
                            update_exec_record(exec_uuid, progress=done_combos,
                                               n_valid=len(_by_idx))
                    with self._lock:
                        if exec_uuid in self._execs:
                            self._execs[exec_uuid]["max_tr_seen"] = int(_max_tr_seen)
                    # Rebuild records in combo order → output identical to the
                    # single-thread path (downstream sorts don't see a difference).
                    for _ci in sorted(_by_idx):
                        records.append({**combo_dicts[_ci], **_by_idx[_ci]})
                    print(f"[AUGUR run] MP grid: {n_total} combos x {n_workers} workers "
                          f"in {time.time() - _t_mp0:.1f}s ({_mp_err_n} errors)", flush=True)
                    if _mp_err_n and not records:
                        with self._lock:
                            if exec_uuid in self._execs:
                                self._execs[exec_uuid]["run_error"] = _mp_err_first
                                self._execs[exec_uuid]["n_errors"]  = _mp_err_n
                except Exception as _mpex:
                    # Pool-level failure (spawn, pickling, memory…) → discard any
                    # partials and run the single-thread path. NEVER lose the run
                    # or silently report 0 valid (the v5.8.7 failure mode).
                    print(f"[AUGUR run] MP pool failed ({type(_mpex).__name__}: {_mpex}) "
                          f"— falling back to single-thread.", flush=True)
                    records = []
                    use_mp = False

            if not use_mp:
                _first_err = None; _n_err = 0; _st_max_tr = 0
                for idx, p in enumerate(combo_dicts):
                    if stop_ev.is_set():
                        break
                    pause_ev.wait()         # blocks here if paused
                    if stop_ev.is_set():
                        break

                    # Capture per-combo failures instead of letting them vanish —
                    # if EVERY combo errors (e.g. a param/strategy mismatch) we want
                    # to tell the user WHY, not silently report 0 valid combos.
                    try:
                        m = _bt(O, H, L, C, **_sx(0, len(C)), **p)
                    except Exception as _ce:
                        _n_err += 1
                        if _first_err is None:
                            _first_err = f"{type(_ce).__name__}: {_ce}"
                        m = None
                    if m:
                        if m["num_trades"] > _st_max_tr:
                            _st_max_tr = m["num_trades"]
                        if m["num_trades"] >= min_trades:
                            records.append({**p, **m})

                    if idx % 100 == 0 or idx == n_total - 1:
                        with self._lock:
                            if exec_uuid in self._execs:
                                self._execs[exec_uuid]["progress"] = idx + 1
                                self._execs[exec_uuid]["n_valid"]  = len(records)
                        update_exec_record(exec_uuid, progress=idx+1, n_valid=len(records))
                with self._lock:
                    if exec_uuid in self._execs:
                        self._execs[exec_uuid]["max_tr_seen"] = int(_st_max_tr)
                if not records and _first_err is not None:
                    with self._lock:
                        if exec_uuid in self._execs:
                            self._execs[exec_uuid]["run_error"] = _first_err
                            self._execs[exec_uuid]["n_errors"]  = _n_err

        if not records:
            # Completed, but nothing met MIN T. Record WHY so the UI can explain it
            # instead of leaving the Results panel silently empty.
            with self._lock:
                _ex      = self._execs.get(exec_uuid, {})
                _run_err = _ex.get("run_error")
                _nerr    = _ex.get("n_errors", 0)
            if _run_err:
                _nr_msg = (f"0 valid combinations — every backtest errored "
                           f"({_nerr}/{n_total}). First error: {_run_err}")
            else:
                _mxt = int(_ex.get("max_tr_seen", 0) or 0)
                if _mxt > 0:
                    _sugg = max(5, (_mxt * 3) // 4)
                    _nr_msg = (f"0 valid combinations — your MIN T is {min_trades} but the "
                               f"best config only made {_mxt} trades on this data window. "
                               f"Short date ranges have few trades (this strategy makes "
                               f"~1/session). Lower MIN T to ~{_sugg}, or use a longer "
                               f"date range / full data.")
                else:
                    _nr_msg = (f"0 valid combinations — no parameter set produced "
                               f"≥ {min_trades} trades. Try lowering MIN T, widening "
                               f"the scope, or using more data.")
            with self._lock:
                if exec_uuid in self._execs:
                    self._execs[exec_uuid]["status"] = "completed"
                    self._execs[exec_uuid]["n_valid"] = 0
                    self._execs[exec_uuid]["no_results"] = True
                    self._execs[exec_uuid]["no_results_msg"] = _nr_msg
            update_exec_record(exec_uuid, status="completed", n_valid=0,
                               error_msg=_nr_msg)
            return

        # Walk-forward rows carry a "fold" column and must stay in fold order;
        # everything else is ranked by in-sample PNL.
        _is_wf = bool(records) and ("fold" in records[0])
        res = pd.DataFrame(records)
        if not _is_wf:
            # Realism-gated headline: rank configs that took enough wins AND enough
            # losses (not a one-sided fluke) ABOVE the rest, so res.iloc[0] — the
            # headline KPIs + top-10 equity + the saved "best" — can't be a
            # profit-factor mirage (the single-winner / few-loss configs a one-way
            # trend produces). The full table + charts still include every config;
            # only the RANKING changes. WF runs keep fold order (own champion gate).
            if {"wins", "losses"} <= set(res.columns):
                _nb = max(1, len(C))
                _real = ((res["wins"].fillna(0)    >= WF_MIN_SIDE)
                         & (res["losses"].fillna(0) >= WF_MIN_SIDE)
                         & ((res["num_trades"].fillna(0) / _nb) <= MAX_TRADE_RATE)
                         & (res["profit_factor"].fillna(0) <= MAX_PF)).astype(int)
                res = (res.assign(_real=_real)
                          .sort_values(["_real", "total_pnl"], ascending=[False, False])
                          .drop(columns="_real"))
            else:
                res = res.sort_values("total_pnl", ascending=False)
        res = res.reset_index(drop=True)
        res["pnl_usd"] = res["total_pnl"]    * multiplier
        res["avg_usd"] = res["avg_pnl"]      * multiplier
        res["dd_usd"]  = res["max_drawdown"] * multiplier
        if "oos_pnl" in res.columns:
            res["oos_pnl_usd"] = res["oos_pnl"] * multiplier
        # Walk-forward headline = the LAST fold's champion (most recent re-optimize
        # = what you'd deploy next); otherwise the top in-sample config.
        best = res.iloc[-1] if _is_wf else res.iloc[0]

        # Equity curves for top 10  — parameter-agnostic (works for any strategy)
        equity_curves = []
        param_names = [c for c in res.columns
                       if c not in ("total_pnl","num_trades","win_rate","profit_factor",
                                    "max_drawdown","avg_pnl","wins","losses",
                                    "pnl_usd","avg_usd","dd_usd",
                                    "oos_pnl","oos_trades","oos_pf","oos_pnl_usd","fold","test_bars")]
        for i in range(0 if _is_wf else min(10, len(res))):   # skip for walk-forward
            row = res.iloc[i]
            params = {k: row[k] for k in param_names if k in row}
            # Coerce numpy types to native Python
            for k, v in params.items():
                if isinstance(v, (np.integer,)): params[k] = int(v)
                elif isinstance(v, (np.floating,)): params[k] = float(v)
                elif isinstance(v, (np.bool_,)): params[k] = bool(v)
            # CRITICAL: inject day_id/volumes via _sx, same as every eval site.
            # Without this, day_id-dependent strategies (ORB, OVERNIGHT_HOLD)
            # return None here → no equity curve saved → blank PNL graph.
            m2 = _bt(O, H, L, C, return_trades=True, **_sx(0, len(C)), **params)
            if m2 and m2.get("trades"):
                trades    = m2["trades"]
                exit_bars = [t[1] for t in trades]
                cum_usd   = (np.cumsum([t[2] for t in trades]) * multiplier).tolist()
                equity_curves.append({
                    "rank":        i+1,
                    "label":       f"#{i+1} ${row['pnl_usd']:,.0f} ({int(row['num_trades'])}T {row['win_rate']:.0f}%WR)",
                    "timestamps":  [df.index[b] for b in exit_bars],
                    "cum_pnl_usd": cum_usd,
                    "final_pnl":   float(row["pnl_usd"]),
                })

        # Store result in memory
        with self._lock:
            if exec_uuid in self._execs:
                self._execs[exec_uuid]["results"] = {
                    "res": res, "best": best.to_dict(),
                    "multiplier": multiplier, "equity_curves": equity_curves,
                    "df_index": df.index,
                    "commission_usd": _comm_usd, "slippage_pts": _slip_pts,
                }

        # Save to run history
        days_in_test = max(1, (df.index[-1] - df.index[0]).days)
        # Capture the ACTUAL strategy plugin source THIS run used (from the
        # path captured at build time), not whatever is globally active now —
        # otherwise switching strategies between runs mislabels the snapshot.
        code_snap = ""
        try:
            _snap_path = _run_strat_path or get_strategy_registry().get("current_path", "")
            if _snap_path and os.path.exists(_snap_path):
                with open(_snap_path, "r", encoding="utf-8") as _sf:
                    code_snap = _sf.read()
        except Exception:
            code_snap = ""
        if not code_snap:
            # Fallback: at least grab the run's strategy module run_backtest source
            try:
                import inspect as _insp
                if _run_strat and hasattr(_run_strat, "run_backtest"):
                    code_snap = _insp.getsource(_run_strat.run_backtest)
            except Exception:
                code_snap = ""
        try:
            save_run(
                instrument=config.get("instrument",""),
                timeframe=config.get("timeframe",""),
                data_source=config.get("data_source",""),
                scope=config.get("scope",""),
                n_combos=n_total, n_valid=len(res),
                bars=len(df),
                date_from=str(df.index[0])[:10],
                date_to=str(df.index[-1])[:10],
                days_in_test=days_in_test,
                multiplier=multiplier,
                best_row=best.to_dict(),
                top10_df=res.head(10),
                code_snapshot=code_snap,
                full_results_df=res,
                equity_curves=equity_curves,
                strategy=config.get("strategy_name",""),
                source_name=config.get("source_name",""),
                commission_usd=config.get("commission_usd", 0.0),
                slippage_pts=config.get("slippage_pts", 0.0),
                elapsed_s=(time.time()
                           - float(self._execs.get(exec_uuid, {}).get("start_ts",
                                                                      time.time()))),
            )
        except Exception as _save_err:
            # Record the failure so it can surface in the UI rather than vanishing
            try:
                self._execs[exec_uuid]["save_error"] = str(_save_err)
            except Exception:
                pass
            import traceback as _tb
            _tb.print_exc()

        # ── Learn a per-backtest time so the builder ETA self-corrects ────────
        # Divide by the SAME backtest count the live ETA uses (exec "total"), so
        # the next projection matches what actually happens on this data size.
        try:
            _ex = self._execs.get(exec_uuid, {})
            _elapsed = time.time() - float(_ex.get("start_ts", 0) or 0)
            _n_bt    = int(_ex.get("total", 0) or n_total or 0)
            if _elapsed > 0.5 and _n_bt > 0:
                _save_eta_calib(_elapsed / _n_bt, len(df))
        except Exception:
            pass


# Init extra tables on startup
try:
    _db_init_extras()
except Exception:
    pass

# CSV upload directory
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "augur_uploads")
os.makedirs(CSV_DIR, exist_ok=True)

# Watched folder: drop TradingView CSV exports here and Augur auto-ingests them
# into matching masters on app open (when auto-refresh is enabled).
WATCH_DIR = os.path.join(os.path.dirname(CSV_DIR), "augur_watch")
os.makedirs(WATCH_DIR, exist_ok=True)
# Where ingested watch-files are moved so they aren't re-processed
WATCH_DONE_DIR = os.path.join(WATCH_DIR, "_ingested")
os.makedirs(WATCH_DONE_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY PLUGIN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
import importlib.util, glob

STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "augur_strategies")
os.makedirs(STRATEGIES_DIR, exist_ok=True)

# The built-in ENGU translation prompt for Claude API
_TRANSLATION_SYSTEM_PROMPT = (
    "Translate the Pine Script strategy to a Python plugin for Augur. "
    "Output ONLY valid Python file content, no markdown.\n\n"
    "Required exports: STRATEGY_NAME, DESCRIPTION, VERSION, "
    "DEFAULT_PARAMS (param->dict with default/min/max/step/type/label/tooltip), "
    "PARAM_GRID_PRESETS (scope->param_grid), "
    "run_backtest(opens,highs,lows,closes,**params,return_trades=False).\n"
    "Return dict(total_pnl,num_trades,win_rate,profit_factor,max_drawdown,"
    "avg_pnl,wins,losses) or None. If return_trades: add trades list."
)
@st.cache_resource
def get_strategy_registry():
    """Process-level singleton holding loaded strategy modules."""
    return {"current_path": None, "current_module": None}


_STRAT_MOD_CACHE = {}  # filepath -> (mtime, module)

def _load_strategy_module(filepath: str):
    """Dynamically load a .py strategy plugin. Returns (module, None) or (None, error).
    Cached by (path, mtime) so unchanged files aren't recompiled every rerun."""
    try:
        mtime = os.path.getmtime(filepath)
        cached = _STRAT_MOD_CACHE.get(filepath)
        if cached and cached[0] == mtime:
            return cached[1], None
    except Exception:
        mtime = None
    try:
        # Read the file manually with UTF-8 so Windows cp1252 doesn't choke
        # on em-dashes, arrows, or other non-ASCII chars in docstrings/comments.
        with open(filepath, "r", encoding="utf-8") as fh:
            source = fh.read()

        spec = importlib.util.spec_from_file_location("augur_strategy", filepath)
        mod  = importlib.util.module_from_spec(spec)
        code = compile(source, filepath, "exec")
        exec(code, mod.__dict__)

        if not hasattr(mod, "run_backtest"):
            return None, "Missing run_backtest() function"
        if not hasattr(mod, "DEFAULT_PARAMS"):
            return None, "Missing DEFAULT_PARAMS dict"
        if mtime is not None:
            _STRAT_MOD_CACHE[filepath] = (mtime, mod)
        return mod, None
    except Exception as ex:
        return None, str(ex)


def _set_strategy_market(filepath, instrument, timeframe):
    """Write/replace the _AUGUR_MARKET catalogue tag in a strategy file so it's
    grouped under the right instrument · timeframe (and can't be cross-applied)."""
    import re as _re
    try:
        with open(filepath, encoding="utf-8") as fh:
            src = fh.read()
        src = _re.sub(r'(?m)^_AUGUR_MARKET\s*=\s*\{[^}]*\}\s*\n?', '', src)
        if not src.endswith("\n"):
            src += "\n"
        src += f"\n_AUGUR_MARKET = {repr({'instrument': instrument or '', 'timeframe': timeframe or ''})}\n"
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(src)
        try:
            _STRAT_MOD_CACHE.pop(filepath, None)
        except Exception:
            pass
        return True, "tagged"
    except Exception as ex:
        return False, str(ex)


def _list_strategy_files() -> list[dict]:
    """Scan augur_strategies/ and return info about each plugin."""
    results = []
    for fpath in sorted(glob.glob(os.path.join(STRATEGIES_DIR, "*.py"))):
        fname = os.path.basename(fpath)
        try:
            ctime = os.path.getmtime(fpath)
            cdate = datetime.fromtimestamp(ctime).strftime("%d %b '%y")
        except Exception:
            cdate = "?"
        try:
            mod, err = _load_strategy_module(fpath)
            if mod:
                # Market tag for the catalogue: explicit _AUGUR_MARKET, else inferred
                # from an AI-tuned strategy's embedded metrics.
                _mk = getattr(mod, "_AUGUR_MARKET", None)
                _tm = getattr(mod, "_AUGUR_TUNED_METRICS", None)
                _gm = lambda d, k: (d.get(k) if isinstance(d, dict) else None)
                results.append({
                    "path":    fpath,
                    "file":    fname,
                    "name":    getattr(mod, "STRATEGY_NAME", fname),
                    "desc":    getattr(mod, "DESCRIPTION", ""),
                    "version": getattr(mod, "VERSION", "?"),
                    "added":   cdate,
                    "instrument": str(_gm(_mk, "instrument") or _gm(_tm, "instrument") or ""),
                    "timeframe":  str(_gm(_mk, "timeframe")  or _gm(_tm, "timeframe")  or ""),
                    "superseded": getattr(mod, "_AUGUR_SUPERSEDED_BY", None),
                    "parent": getattr(mod, "_AUGUR_PARENT", None),
                    "ok":      True,
                })
            else:
                results.append({"path": fpath, "file": fname, "name": fname,
                                "desc": f"Load error: {err}", "added": cdate, "ok": False})
        except Exception as ex:
            results.append({"path": fpath, "file": fname, "name": fname,
                            "desc": str(ex), "added": cdate, "ok": False})
    return results


def _pine_scaffold(name: str, desc: str, dp: dict) -> str:
    """Pine v5 scaffold from a strategy's params (inputs only — entry/exit logic
    can't be auto-translated from arbitrary Python, so it's a clearly-marked TODO)."""
    L = ["//@version=5",
         f"// AUGUR . {name} — Pine SCAFFOLD (inputs only).",
         (f"// {desc[:90]}" if desc else "// (no description)"),
         "// NOTE: the entry/exit LOGIC is NOT auto-ported from the Python strategy",
         "// (that can't be done reliably). Fill in the signal + orders below, or ask",
         "// AUGUR to hand-write a full Pine port for this strategy.",
         f'strategy("{name}", overlay=true, default_qty_type=strategy.fixed,',
         "     default_qty_value=1, pyramiding=0, process_orders_on_close=true)",
         "",
         "// -- Inputs (from the strategy's parameters) --"]
    for k, meta in (dp or {}).items():
        if not isinstance(meta, dict):
            continue
        t = meta.get("type", "float"); d = meta.get("default"); lbl = str(meta.get("label", k))
        if t == "bool":
            L.append(f'{k} = input.bool({str(bool(d)).lower()}, "{lbl}")')
        elif t == "int":
            L.append(f'{k} = input.int({int(d) if d is not None else 0}, "{lbl}")')
        elif t == "str":
            opts = meta.get("options")
            L.append(f'{k} = input.string("{d}", "{lbl}"'
                     + (f', options={[str(o) for o in opts]})' if opts else ")"))
        else:
            L.append(f'{k} = input.float({float(d) if d is not None else 0.0}, "{lbl}")')
    L += ["", "// -- TODO: port the signal + entry/exit from the Python strategy --",
          "// longCond  = false",
          "// shortCond = false",
          "// if strategy.position_size == 0 and longCond",
          '//     strategy.entry("L", strategy.long)']
    return "\n".join(L)


def _strategy_pine(sf: dict) -> str:
    """Pine for a Library strategy: a hand-written port if one exists
    (pine/<basename>.pine, or a module-level _PINE string), else a params scaffold —
    so every strategy card can offer a Pine download."""
    try:
        _pf = os.path.join(os.path.dirname(STRATEGIES_DIR), "pine",
                           os.path.splitext(sf.get("file", ""))[0] + ".pine")
        if os.path.exists(_pf):
            return open(_pf, encoding="utf-8").read()
    except Exception:
        pass
    mod = None
    try:
        mod, _e = _load_strategy_module(sf["path"])
    except Exception:
        pass
    if mod is not None and isinstance(getattr(mod, "_PINE", None), str) and mod._PINE.strip():
        return mod._PINE
    dp = getattr(mod, "DEFAULT_PARAMS", {}) if mod else {}
    return _pine_scaffold(sf.get("name", "Strategy"), sf.get("desc", "") or "", dp)


def _rename_strategy(filepath: str, new_name: str) -> tuple[bool, str]:
    """Rewrite the STRATEGY_NAME = "..." line inside a plugin file, and
    propagate the new name to all past runs + execution records so the
    Results tab stays in sync."""
    import re as _re
    try:
        # Capture the current (old) name first so we can update history
        old_name = ""
        try:
            _mod_old, _ = _load_strategy_module(filepath)
            if _mod_old is not None:
                old_name = getattr(_mod_old, "STRATEGY_NAME", "")
        except Exception:
            old_name = ""

        with open(filepath, "r", encoding="utf-8") as fh:
            src = fh.read()
        # Replace the first STRATEGY_NAME assignment
        safe = new_name.replace('"', "'")
        new_src, n = _re.subn(
            r'STRATEGY_NAME\s*=\s*["\'].*?["\']',
            f'STRATEGY_NAME = "{safe}"',
            src, count=1,
        )
        if n == 0:
            # No existing line — inject one near the top after imports
            new_src = f'STRATEGY_NAME = "{safe}"\n' + src
        # Validate before writing
        import tempfile as _tf
        with _tf.NamedTemporaryFile(suffix=".py", delete=False,
                                    mode="w", encoding="utf-8") as tmp:
            tmp.write(new_src); tp = tmp.name
        mod, err = _load_strategy_module(tp)
        os.unlink(tp)
        if err:
            return False, err
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(new_src)
        # Invalidate the cached module so the new name loads immediately
        try: _STRAT_MOD_CACHE.pop(filepath, None)
        except Exception: pass
        # Propagate to saved runs / executions
        n_runs = 0
        if old_name and old_name != new_name:
            try: n_runs = rename_strategy_in_runs(old_name, new_name)
            except Exception: n_runs = 0
        return True, (f"Renamed · {n_runs} past run(s) updated"
                      if n_runs else "Renamed")
    except Exception as ex:
        return False, str(ex)


def _get_active_strategy():
    """Return the currently selected strategy module, or the built-in ENGU."""
    reg = get_strategy_registry()
    if reg.get("current_module"):
        return reg["current_module"]
    # Lazy-load built-in ENGU as fallback
    engu_path = os.path.join(STRATEGIES_DIR, "engu.py")
    if os.path.exists(engu_path):
        mod, err = _load_strategy_module(engu_path)
        if mod:
            reg["current_module"] = mod
            reg["current_path"]   = engu_path
            return mod
    return None


def _set_active_strategy(filepath: str) -> tuple[bool, str]:
    """Load and activate a strategy file."""
    mod, err = _load_strategy_module(filepath)
    if err:
        return False, err
    reg = get_strategy_registry()
    reg["current_module"] = mod
    reg["current_path"]   = filepath
    return True, f"Loaded: {getattr(mod,'STRATEGY_NAME', filepath)}"


def _grid_raw_size(grid) -> int:
    """Raw cross-product size of a grid, capped (no enumeration)."""
    n = 1
    for v in (grid or {}).values():
        n *= max(len(v), 1)
        if n > 1_000_000_000:
            break
    return n


MAX_GRID_COMBOS = 2_000_000   # refuse to ENUMERATE grids beyond this


def _effective_combos(grid, default_params=None):
    """Return the list of UNIQUE active parameter combinations.

    A parameter can declare `depends_on: {other_param: value}` in the
    strategy's DEFAULT_PARAMS. When that condition isn't met, the parameter
    is inactive and its value doesn't matter — so we collapse it to its
    default to avoid running (and counting) redundant identical backtests.
    """
    if not grid:
        return []
    # HARD GUARD: never materialize an absurd cross-product. A wide-open Custom
    # grid (e.g. 5 params × full ranges ≈ 50 MILLION combos) used to spin here
    # for MINUTES with the GIL pinned — the script run never finished, the
    # frontend stayed 'running', and every widget click in the app was silently
    # swallowed (the stuck-Custom-scope / deaf-UI bug, found via py-spy).
    if _grid_raw_size(grid) > MAX_GRID_COMBOS:
        print(f"[AUGUR] grid too large to enumerate "
              f"({_grid_raw_size(grid):,} > {MAX_GRID_COMBOS:,}) — refusing.", flush=True)
        return []
    keys = list(grid.keys())
    deps = {}
    if default_params:
        for k, meta in default_params.items():
            if isinstance(meta, dict) and meta.get("depends_on"):
                deps[k] = meta["depends_on"]
    raw = itertools.product(*[grid[k] for k in keys])
    seen = set()
    out = []
    for combo in raw:
        p = dict(zip(keys, combo))
        norm = dict(p)
        for k, cond in deps.items():
            if k in norm:
                active = all(p.get(dep_k) == dep_v for dep_k, dep_v in cond.items())
                if not active:
                    norm[k] = None
        sig = tuple(sorted(norm.items()))
        if sig not in seen:
            seen.add(sig)
            out.append(p)
    return out


def _count_effective_combos(grid, default_params=None):
    """ANALYTIC count of unique active combos — never enumerates.

    The old `len(_effective_combos(...))` materialized the full cross-product
    just to count it. Instead: enumerate only the CONTROLLER params (the ones
    other params' depends_on conditions reference — tiny cardinality), and for
    each controller assignment multiply the value-counts of the params active
    under it (inactive params collapse to 1). Exact same number, microseconds.
    """
    if not grid:
        return 0
    deps = {}
    if default_params:
        for k, meta in default_params.items():
            if isinstance(meta, dict) and meta.get("depends_on"):
                deps[k] = meta["depends_on"]
    dependents = {k: cond for k, cond in deps.items() if k in grid}
    controllers = sorted({dk for cond in dependents.values() for dk in cond}
                         & set(grid.keys()))
    # Nested case (a controller is itself dependent): fall back to the exact
    # enumerator only when small; otherwise report the raw product.
    if any(c in dependents for c in controllers):
        if _grid_raw_size(grid) <= 200_000:
            return len(_effective_combos(grid, default_params))
        return _grid_raw_size(grid)
    others = [k for k in grid if k not in controllers]
    total = 0
    _ctrl_iter = (itertools.product(*[grid[c] for c in controllers])
                  if controllers else [()])
    for cvals in _ctrl_iter:
        assign = dict(zip(controllers, cvals))
        n = 1
        for k in others:
            cond = dependents.get(k)
            if cond and not all(assign.get(dk) == dv for dk, dv in cond.items()):
                continue                      # inactive → collapses to 1 value
            n *= max(len(grid[k]), 1)
        total += n
    return total


def _ai_seed_grid(default_params, points=4):
    """Build an initial coarse search grid from a strategy's DEFAULT_PARAMS:
    a few values spanning each numeric param's range; bool/str → all options."""
    grid = {}
    for name, meta in (default_params or {}).items():
        if not isinstance(meta, dict):
            continue
        typ = meta.get("type", "float")
        if typ == "bool":
            grid[name] = [True, False]
        elif typ == "str":
            grid[name] = list(meta.get("options", [meta.get("default")]))
        else:
            lo = meta.get("min", 0); hi = meta.get("max", 1)
            step = meta.get("step", 0) or 0
            try:
                if typ == "int":
                    vals = list(np.linspace(lo, hi, points))
                    vals = sorted(set(int(round(v)) for v in vals))
                else:
                    vals = [round(float(v), 6) for v in np.linspace(lo, hi, points)]
                grid[name] = vals or [meta.get("default")]
            except Exception:
                grid[name] = [meta.get("default")]
    return grid


def _ai_handoff_paths():
    """Filesystem bridge between the app and a Claude Code session: the app
    writes the round context to handoff.json; Claude Code writes the next-round
    decision to proposal.json. Both live next to optimizer.py."""
    base = os.path.dirname(os.path.abspath(__file__))
    return (os.path.join(base, "augur_ai_handoff.json"),
            os.path.join(base, "augur_ai_proposal.json"))


def _ai_write_handoff(session, rnd, src, dp, digest, oos_note) -> bool:
    """Write the keyless-AI handoff file: the SAME context the API path sends to
    Claude, as JSON, for a Claude Code session to read and respond to."""
    import json as _json
    hpath, ppath = _ai_handoff_paths()
    param_spec = {k: {kk: vv for kk, vv in v.items()
                      if kk in ("type", "min", "max", "step", "options")}
                  for k, v in (dp or {}).items()}
    _evolve = session.get("mode") == "evolve"
    schema = ('{"round_key": "<echo exactly>", "reasoning": "<1-3 sentences>", '
              '"next_ranges": {"<param>": [<values within min/max>], ...}, "stop": false'
              + (', "code_edit": "<full new strategy .py source>", '
                 '"code_edit_summary": "<what changed>"' if _evolve else '') + '}')
    payload = {
        "_instructions": (
            "AUGUR keyless-AI handoff — you (Claude Code) are the optimizer for this round. "
            "Read this file, then WRITE the file augur_ai_proposal.json (same folder) containing "
            "EXACTLY this JSON shape: " + schema + ". Rules: echo round_key verbatim; every value "
            "in next_ranges must stay within that param's min/max from param_spec; only include "
            "params you want to change; set stop=true when results have converged."
            + (" For Evolve, code_edit must be the COMPLETE strategy .py (it is re-validated "
               "before use)." if _evolve else "")),
        "round_key": f"{session.get('sid','')}-{rnd}",
        "mode": session.get("mode", "optimize"),
        "round": rnd, "total_rounds": session.get("total_rounds"),
        "strategy_name": session.get("strategy_name", ""),
        "instrument": session.get("instrument", ""), "timeframe": session.get("timeframe", ""),
        "min_trades": session.get("min_trades"),
        "costs": {"commission_usd": session.get("commission_usd", 0),
                  "slippage_pts": session.get("slippage_pts", 0),
                  "multiplier": session.get("multiplier", 1)},
        "param_spec": param_spec,
        "current_grid": session.get("grid", {}),
        "best_config_so_far": session.get("best", {}),
        "out_of_sample_note": oos_note,
        "latest_results": digest,
    }
    if _evolve:
        payload["current_strategy_source"] = src
    try:
        if os.path.exists(ppath):
            os.remove(ppath)               # clear any stale proposal from a prior round
        with open(hpath, "w", encoding="utf-8") as f:
            _json.dump(payload, f, indent=1, default=str)
        return True
    except Exception:
        return False


def _ai_read_proposal(session, rnd):
    """Read Claude Code's proposal file for the current round. Returns
    (proposal_dict, error). Refuses a proposal whose round_key doesn't match."""
    import json as _json
    _hpath, ppath = _ai_handoff_paths()
    if not os.path.exists(ppath):
        return None, ("No proposal yet — in your Claude Code chat say "
                      "“process the AUGUR round”, then click Apply.")
    try:
        with open(ppath, encoding="utf-8") as f:
            prop = _json.load(f)
    except Exception as ex:
        return None, f"Proposal file is not valid JSON yet: {ex}"
    want = f"{session.get('sid','')}-{rnd}"
    if str(prop.get("round_key", "")) != want:
        return None, (f"That proposal is for a different round (got "
                      f"{prop.get('round_key')!r}, need {want!r}).")
    return prop, None


def _ai_keyless_apply(session):
    """Phase 2 of a keyless round: read Claude Code's proposal and apply it
    (next_ranges, + validated code_edit for Evolve, + stop), then resume the
    loop. Mirrors the API path's apply logic. Returns (applied: bool, message)."""
    rnd = session.get("round", 0)
    prop, perr = _ai_read_proposal(session, rnd)
    if perr:
        return False, perr
    log = session.setdefault("log", [])
    strat, _serr = _load_strategy_module(session["strategy_path"])
    dp = getattr(strat, "DEFAULT_PARAMS", {}) if strat else {}
    log.append(f"R{rnd}: {str(prop.get('reasoning',''))[:300]}")
    # Evolve: apply a validated, versioned code edit (same gate as the API path)
    if session.get("mode") == "evolve" and prop.get("code_edit"):
        mod, verr = validate_strategy_code(prop["code_edit"])
        if verr:
            log.append(f"R{rnd}: ⚠ code edit rejected — {verr}")
        else:
            base = os.path.splitext(os.path.basename(session["strategy_path"]))[0].split("__ai_r")[0]
            newpath = os.path.join(STRATEGIES_DIR, f"{base}__ai_r{rnd}.py")
            try:
                with open(newpath, "w", encoding="utf-8") as f:
                    f.write(prop["code_edit"])
                session["strategy_path"] = newpath
                dp = getattr(mod, "DEFAULT_PARAMS", dp)
                log.append(f"R{rnd}: \U0001f9ec evolved → {os.path.basename(newpath)} "
                           f"({str(prop.get('code_edit_summary',''))[:160]})")
            except Exception as we:
                log.append(f"R{rnd}: code write failed — {we}")
    # Apply next parameter ranges (merge over current grid, keep all params present)
    nr = prop.get("next_ranges") or {}
    if isinstance(nr, dict) and nr:
        newgrid = dict(session.get("grid", {}))
        for k, vals in nr.items():
            if k in dp and isinstance(vals, list) and vals:
                newgrid[k] = vals
        seed = _ai_seed_grid(dp, points=3)
        for k in dp.keys():
            newgrid.setdefault(k, seed.get(k, [dp[k].get("default")]))
        session["grid"] = {k: v for k, v in newgrid.items() if k in dp}
    stop = bool(prop.get("stop"))
    try:
        hpath, ppath = _ai_handoff_paths()
        for p in (hpath, ppath):
            if os.path.exists(p):
                os.remove(p)
    except Exception:
        pass
    if stop or session.get("round", 0) >= session.get("total_rounds", 0):
        session["status"] = "done"
        log.append(f"R{rnd}: {'converged — AI signalled stop.' if stop else 'reached round limit.'} Done.")
    else:
        session["status"] = "running"
    return True, "Applied."


def ai_run_one_round(session: dict, api_key: str) -> dict:
    """Execute ONE agentic round in-place on `session` (a dict held in
    st.session_state). Mutates and returns it. Designed to be called once per
    fragment tick so the UI stays responsive and survives reruns.

    session keys:
      mode ('optimize'|'evolve'), strategy_path, O/H/L/C arrays (is+oos),
      min_trades, total_rounds, round, grid, best (config dict), best_oos,
      history (list of round summaries), status, oos_on, log
    """
    import json as _json
    rnd = session["round"] + 1
    session["round"] = rnd
    log = session.setdefault("log", [])

    # Load the current strategy (may have been code-edited in a prior round)
    spath = session["strategy_path"]
    strat, serr = _load_strategy_module(spath)
    if strat is None:
        session["status"] = "error"
        log.append(f"R{rnd}: strategy load failed — {serr}")
        return session

    Ois, His, Lis, Cis = session["is_arrays"]
    grid = session["grid"]
    dp = getattr(strat, "DEFAULT_PARAMS", {})
    combos = _effective_combos(grid, dp)
    # Cap combos per round so a round stays quick (the AI iterates, not brute-forces)
    if len(combos) > session.get("max_combos_per_round", 400):
        combos = combos[: session["max_combos_per_round"]]

    # Per-trade costs so AI runs are NET, matching Auto-Optimize.
    _mult = session.get("multiplier", 1) or 1
    _cost_pts = (float(session.get("commission_usd", 0) or 0) / _mult) + float(session.get("slippage_pts", 0) or 0)

    # 1) Run the in-sample sweep
    is_records = _ai_quick_grid_eval(strat, Ois, His, Lis, Cis, combos, session["min_trades"], _cost_pts)
    if not is_records:
        log.append(f"R{rnd}: no valid configs (try wider ranges / fewer filters).")
    # Best in-sample config this round
    round_best = None
    if is_records:
        round_best = max(is_records, key=lambda r: r["total_pnl"])

    # 2) Out-of-sample validation of the round's best
    oos_note = "Out-of-sample validation: OFF."
    oos_pnl = None
    if session.get("oos_on") and round_best is not None:
        Oo, Ho, Lo, Co = session["oos_arrays"]
        pcols = {k: round_best[k] for k in dp.keys() if k in round_best}
        try:
            if _cost_pts > 0:
                oos_m = _apply_costs(strat.run_backtest(Oo, Ho, Lo, Co, return_trades=True, **pcols), _cost_pts)
            else:
                oos_m = strat.run_backtest(Oo, Ho, Lo, Co, **pcols)
        except Exception:
            oos_m = None
        if oos_m:
            oos_pnl = float(oos_m["total_pnl"])
            is_pnl = float(round_best["total_pnl"])
            gap = (oos_pnl - is_pnl)
            oos_note = (f"Out-of-sample check on this round's best config: "
                        f"in-sample PNL={is_pnl:.1f}, out-of-sample PNL={oos_pnl:.1f}. "
                        f"{'⚠ Likely overfit (OOS much worse).' if oos_pnl < is_pnl*0.3 else 'Holds up reasonably.'}")
        else:
            oos_note = "Out-of-sample best config produced no trades (possibly overfit)."

    # Track global best (by in-sample, but record oos)
    if round_best is not None:
        if session.get("best") is None or round_best["total_pnl"] > session["best"].get("total_pnl", -1e18):
            session["best"] = dict(round_best)
            session["best_oos"] = oos_pnl
            session["best_round"] = rnd
            session["best_strategy_path"] = spath

    # 3) Ask Claude for the next move
    digest = _ai_results_digest(is_records)
    src = ""
    if session["mode"] == "evolve":
        try:
            with open(spath, encoding="utf-8") as f: src = f.read()
        except Exception: src = ""

    # KEYLESS engine: hand the round off to a Claude Code session via files
    # (no API key / no spend) and PAUSE here. _ai_keyless_apply() resumes once
    # the proposal file appears. The API path below is unchanged.
    if session.get("engine") == "claude_code":
        _ai_write_handoff(session, rnd, src, dp, digest, oos_note)
        session["status"] = "awaiting_claude"
        log.append(f"R{rnd}: \U0001f4e4 exported for Claude Code — say "
                   f"“process the AUGUR round”, then click Apply.")
        session.setdefault("history", []).append(
            {"round": rnd, "is_best_pnl": (round_best["total_pnl"] if round_best else None),
             "oos_pnl": oos_pnl, "n_valid": len(is_records),
             "reasoning": "(awaiting Claude Code proposal)", "code_changed": False, "error": None})
        return session

    prop, perr = ai_propose_next(
        api_key, session["mode"], src, dp, digest,
        session.get("best", {}), rnd, session["total_rounds"], oos_note)

    summary = {"round": rnd, "is_best_pnl": round_best["total_pnl"] if round_best else None,
               "oos_pnl": oos_pnl, "n_valid": len(is_records),
               "reasoning": "", "code_changed": False, "error": perr}

    if perr:
        log.append(f"R{rnd}: AI error — {perr}")
        session.setdefault("history", []).append(summary)
        # keep going with same grid next round unless out of rounds
    else:
        summary["reasoning"] = prop.get("reasoning", "")[:300]
        log.append(f"R{rnd}: {summary['reasoning']}")

        # 3a) Apply code edit (Evolve mode only), with validation + versioning
        if session["mode"] == "evolve" and prop.get("code_edit"):
            new_code = prop["code_edit"]
            mod, verr = validate_strategy_code(new_code)
            if verr:
                log.append(f"R{rnd}: ⚠ code edit rejected — {verr}")
            else:
                # Version the edit: write a new file, switch session to it
                base = os.path.splitext(os.path.basename(spath))[0]
                base = base.split("__ai_r")[0]
                newfn = f"{base}__ai_r{rnd}.py"
                newpath = os.path.join(STRATEGIES_DIR, newfn)
                try:
                    with open(newpath, "w", encoding="utf-8") as f:
                        f.write(new_code)
                    session["strategy_path"] = newpath
                    summary["code_changed"] = True
                    summary["code_summary"] = prop.get("code_edit_summary", "")[:160]
                    log.append(f"R{rnd}: 🧬 strategy evolved → {newfn} "
                               f"({summary.get('code_summary','')})")
                    # Reload default params for the new code's grid
                    dp = getattr(mod, "DEFAULT_PARAMS", dp)
                except Exception as we:
                    log.append(f"R{rnd}: code write failed — {we}")

        # 3b) Apply next parameter ranges (merge over current grid)
        nr = prop.get("next_ranges") or {}
        if isinstance(nr, dict) and nr:
            newgrid = dict(session["grid"])
            for k, vals in nr.items():
                if k in dp and isinstance(vals, list) and vals:
                    newgrid[k] = vals
            # Ensure every param still present (use seed for any new code params)
            seed = _ai_seed_grid(dp, points=3)
            for k in dp.keys():
                newgrid.setdefault(k, seed.get(k, [dp[k].get("default")]))
            # Drop params no longer in the (possibly edited) strategy
            session["grid"] = {k: v for k, v in newgrid.items() if k in dp}

        if prop.get("stop"):
            session["status"] = "done"
            log.append(f"R{rnd}: AI signalled stop — converged.")

    session.setdefault("history", []).append(summary)

    # 4) Round bookkeeping / termination
    if session["round"] >= session["total_rounds"] and session["status"] == "running":
        session["status"] = "done"
        log.append(f"Reached round limit ({session['total_rounds']}). Done.")
    return session


def _ai_save_to_history(session: dict):
    """Persist the AI session's best result into the runs DB so it appears in
    Results → Past Runs like any other run. Idempotent per session."""
    if session.get("_saved_to_history"):
        return
    best = session.get("best")
    if not best:
        session["_saved_to_history"] = True
        return
    try:
        mult = session.get("multiplier", 1) or 1
        # Build a best_row dict with $-denominated metrics
        best_row = dict(best)
        pnl_usd = float(best.get("total_pnl", 0)) * mult
        best_row["pnl_usd"] = pnl_usd
        best_row["dd_usd"]  = float(best.get("max_drawdown", 0)) * mult
        best_row["avg_usd"] = float(best.get("avg_pnl", 0)) * mult
        top10 = pd.DataFrame([best_row])
        mode_lbl = "AI Evolve" if session.get("mode") == "evolve" else "AI Optimize"
        # Strategy name: the evolved/promoted one if present, else the original
        strat_nm = session.get("promoted_name") or session.get("strategy_name", "")
        # Capture the final strategy code
        code_snap = ""
        try:
            with open(session.get("best_strategy_path") or session["strategy_path"],
                      encoding="utf-8") as f:
                code_snap = f.read()
        except Exception:
            code_snap = ""
        rounds = session.get("round", 0)
        oos = session.get("best_oos")
        save_run(
            instrument=session.get("instrument",""),
            timeframe=session.get("timeframe",""),
            data_source="CSV",
            scope=f"{mode_lbl} ({rounds}r)",
            n_combos=rounds, n_valid=len(session.get("history", [])),
            bars=0, date_from="", date_to="", days_in_test=1,
            multiplier=mult, best_row=best_row, top10_df=top10,
            code_snapshot=code_snap,
            full_results_df=top10, equity_curves=None,
            strategy=strat_nm, source_name=session.get("source_name",""),
        )
        session["_saved_to_history"] = True
        session.setdefault("log", []).append(
            f"💾 Saved best to Results history (in-sample PNL {best.get('total_pnl',0):,.0f}"
            + (f", OOS {oos:,.0f}" if oos is not None else "") + ").")
    except Exception as ex:
        session.setdefault("log", []).append(f"History save failed: {ex}")
        session["_saved_to_history"] = True


def _promote_evolved_strategy(session: dict):
    """Auto-save the final evolved strategy into the Library as a selectable
    strategy (renamed so it's clearly an AI-evolved version). Idempotent."""
    if session.get("_promoted"):
        return
    spath = session.get("best_strategy_path") or session.get("strategy_path")
    orig = session.get("orig_strategy_path")
    # Only promote if the strategy actually changed (evolve produced a new file)
    if not spath or spath == orig or not os.path.exists(spath):
        session["_promoted"] = True
        return
    try:
        with open(spath, encoding="utf-8") as f:
            code = f.read()
        # Validate once more before promoting
        mod, err = validate_strategy_code(code)
        if err:
            session.setdefault("log", []).append(f"Promote skipped (invalid): {err}")
            session["_promoted"] = True
            return
        # Give it a clear evolved name
        import re as _re, datetime as _dt
        base_name = getattr(mod, "STRATEGY_NAME", "Strategy")
        stamp = _dt.datetime.now().strftime("%m%d-%H%M")
        evo_name = f"{base_name.split(' · AI')[0]} · AI-evolved {stamp}"
        new_code = _re.sub(r'STRATEGY_NAME\s*=\s*["\'].*?["\']',
                           f'STRATEGY_NAME = "{evo_name}"', code, count=1)
        # Save into the Library strategies dir with a clean filename
        fn = f"evolved_{stamp.replace('-','_')}_{uuid.uuid4().hex[:4]}.py"
        dest = os.path.join(STRATEGIES_DIR, fn)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(new_code)
        session["promoted_path"] = dest
        session["promoted_name"] = evo_name
        session.setdefault("log", []).append(
            f"✅ Auto-saved evolved strategy to Library: {evo_name}")
    except Exception as ex:
        session.setdefault("log", []).append(f"Promote failed: {ex}")
    session["_promoted"] = True


def _strategy_param_diff(orig_dp, tuned_params):
    """Return [(param, old_default, new_value)] for params whose tuned value
    differs from the strategy's original default — the human-readable 'what changed'."""
    diffs = []
    for k, v in (tuned_params or {}).items():
        if k not in (orig_dp or {}):
            continue
        if isinstance(v, np.integer):    v = int(v)
        elif isinstance(v, np.floating):  v = float(v)
        elif isinstance(v, np.bool_):     v = bool(v)
        old = orig_dp[k].get("default")
        if old != v:
            diffs.append((k, old, v))
    return diffs


def save_tuned_strategy_profile(orig_path, tuned_params, metrics=None, label="AI-tuned"):
    """Clone a strategy .py into the Library with the found params baked in as the
    new DEFAULT_PARAMS defaults — the ORIGINAL file is untouched. Robust: appends a
    small override block at module end rather than editing the (possibly nested)
    DEFAULT_PARAMS source by regex. Validates before writing.
    Returns (new_path, new_name, diff_list, error)."""
    import re as _re, datetime as _dt, json as _json
    omod, oerr = _load_strategy_module(orig_path)
    if omod is None:
        return None, None, [], f"original strategy invalid: {oerr}"
    try:
        with open(orig_path, encoding="utf-8") as f:
            code = f.read()
    except Exception as ex:
        return None, None, [], f"can't read original: {ex}"
    odp = getattr(omod, "DEFAULT_PARAMS", {})
    # Keep only real params, JSON-clean numpy scalars
    clean = {}
    for k, v in (tuned_params or {}).items():
        if k not in odp:
            continue
        if isinstance(v, np.integer):    v = int(v)
        elif isinstance(v, np.floating):  v = float(v)
        elif isinstance(v, np.bool_):     v = bool(v)
        clean[k] = v
    diffs = _strategy_param_diff(odp, clean)
    stamp = _dt.datetime.now().strftime("%m%d-%H%M")
    base_name = getattr(omod, "STRATEGY_NAME", "Strategy").split(" · ")[0]
    new_name = f"{base_name} · {label} {stamp}"
    new_code = _re.sub(r'STRATEGY_NAME\s*=\s*["\'].*?["\']',
                       f'STRATEGY_NAME = {new_name!r}', code, count=1)
    override = (
        f"\n\n# ── Augur {label} profile — baked-in defaults "
        f"(original: {os.path.basename(orig_path)}) ──\n"
        f"_AUGUR_TUNED = {repr(clean)}\n"
        f"try:\n"
        f"    for _k, _v in _AUGUR_TUNED.items():\n"
        f"        if _k in DEFAULT_PARAMS:\n"
        f"            DEFAULT_PARAMS[_k]['default'] = _v\n"
        f"except Exception:\n"
        f"    pass\n")
    if metrics:
        override += f"_AUGUR_TUNED_METRICS = {repr(metrics)}\n"
        _mi = metrics.get("instrument") if isinstance(metrics, dict) else None
        _mt = metrics.get("timeframe") if isinstance(metrics, dict) else None
        if _mi or _mt:   # auto-tag the catalogue market for AI-built strategies
            override += (f"_AUGUR_MARKET = "
                         f"{repr({'instrument': _mi or '', 'timeframe': _mt or ''})}\n")
    final = new_code + override
    vmod, verr = validate_strategy_code(final)
    if verr:
        return None, None, diffs, f"tuned profile failed validation: {verr}"
    fn = f"tuned_{stamp.replace('-','_')}_{uuid.uuid4().hex[:4]}.py"
    dest = os.path.join(STRATEGIES_DIR, fn)
    try:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(final)
    except Exception as ex:
        return None, None, diffs, f"write failed: {ex}"
    return dest, new_name, diffs, None


def _promote_tuned_strategy(session):
    """On AI OPTIMIZE completion, clone the strategy into the Library with the best
    config's params baked in (original UNTOUCHED). Idempotent. Stores new path/name/
    diff on the session for the UI. (Evolve uses _promote_evolved_strategy instead.)"""
    if session.get("_tuned_saved"):
        return
    session["_tuned_saved"] = True
    if session.get("mode") != "optimize":
        return
    best = session.get("best")
    orig = session.get("orig_strategy_path") or session.get("strategy_path")
    if not best or not orig:
        return
    omod, _e = _load_strategy_module(orig)
    if omod is None:
        return
    odp = getattr(omod, "DEFAULT_PARAMS", {})
    params = {k: best[k] for k in odp.keys() if k in best}
    mult = session.get("multiplier", 1) or 1
    metrics = {
        "in_sample_pnl_usd": round(float(best.get("total_pnl", 0)) * mult),
        "in_sample_pf": round(float(best.get("profit_factor", 0) or 0), 2),
        "in_sample_trades": int(best.get("num_trades", 0)),
        "out_of_sample_pnl_usd": (round(float(session["best_oos"]) * mult)
                                  if session.get("best_oos") is not None else None),
        "rounds": session.get("round"),
        "instrument": session.get("instrument", ""),
        "timeframe": session.get("timeframe", ""),
        "source": session.get("source_name", ""),
    }
    path, name, diffs, err = save_tuned_strategy_profile(orig, params, metrics=metrics,
                                                         label="AI-tuned")
    if err:
        session.setdefault("log", []).append(f"Tuned profile not saved: {err}")
        return
    session["tuned_path"] = path
    session["tuned_name"] = name
    session["tuned_diff"] = diffs
    session.setdefault("log", []).append(
        f"✅ Saved tuned profile to Library: {name} ({len(diffs)} params changed)")


def translate_pine_to_python(pine_code: str, api_key: str) -> tuple[str | None, str | None]:
    """Call Claude API to translate Pine Script -> Python plugin. Returns (code, error)."""
    import requests, json as _json
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 4000,
                "system":     _TRANSLATION_SYSTEM_PROMPT,
                "messages":   [{"role": "user",
                                "content": f"Translate this Pine Script strategy:\n\n```pinescript\n{pine_code}\n```"}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None, f"API error {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        code = data["content"][0]["text"].strip()
        # Strip markdown fences if Claude added them anyway
        if code.startswith("```"):
            lines = code.splitlines()
            code  = "\n".join(lines[1:-1] if lines[-1]=="```" else lines[1:])
        return code, None
    except Exception as ex:
        return None, str(ex)


def _save_strategy_config_json():
    """Persist active strategy path to augur_config.json for restart persistence."""
    cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
    reg = get_strategy_registry()
    try:
        existing = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                existing = json.load(f)
        existing["active_strategy"] = reg.get("current_path", "")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


def _load_config_json() -> dict:
    cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_eta_calib(sec_per_bt: float, bars: int):
    """Persist a measured seconds-per-backtest so the builder's ETA self-corrects
    after each real run (the projection used to be a flat constant that ignored
    data size, so it never matched the live ETA). Written from the worker thread —
    a plain JSON overwrite, tolerant of the occasional racey read."""
    try:
        cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
        cfg = _load_config_json()
        prev = cfg.get("eta_calib", {}) or {}
        # Exponential smoothing so one weird run doesn't whipsaw the estimate.
        old = float(prev.get("sec_per_bt", 0) or 0)
        new = float(sec_per_bt)
        sm  = new if old <= 0 else (0.5 * old + 0.5 * new)
        cfg["eta_calib"] = {"sec_per_bt": sm, "bars": int(bars)}
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def _get_eta_calib() -> dict:
    try:
        return _load_config_json().get("eta_calib", {}) or {}
    except Exception:
        return {}


def _save_last_run_cfg(cfg: dict):
    """Persist the last launched run config (JSON-safe parts) so Quick Run can
    re-fire it with one click — including across app restarts."""
    try:
        st.session_state["_last_run_cfg"] = cfg          # full copy for this session
    except Exception:
        pass
    try:
        safe = {k: v for k, v in cfg.items() if k != "_csv_file"}
        json.dumps(safe)                                 # validate JSON-serializable
        cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
        c = _load_config_json()
        c["last_run_cfg"] = safe
        with open(cfg_path, "w") as f:
            json.dump(c, f, indent=2)
    except Exception:
        pass


def _get_last_run_cfg() -> dict:
    lrc = st.session_state.get("_last_run_cfg")
    if lrc:
        return lrc
    try:
        return _load_config_json().get("last_run_cfg", {}) or {}
    except Exception:
        return {}


# ── Per-strategy validation roadmap ──────────────────────────────────────────
# The canonical "is it deployable yet?" pipeline. Each strategy tracks its own
# progress (persisted in augur_config.json under "roadmaps"). A few steps auto-tick
# from run history; the rest are manual checkmarks the user controls.
VALIDATION_STEPS = [
    ("feasibility", "Feasibility / hypothesis",
     "Does the edge plausibly exist at all? (feasibility sweep or diagnostic)"),
    ("insample",    "In-sample optimization",
     "A grid or Auto search found a candidate config. (auto-ticks once any run exists)"),
    ("plateau",     "Plateau check (robust params)",
     "The winning config sits in a CLUSTER of good configs, not a lonely right-tail "
     "spike — read the PNL Distribution panel's PLATEAU/ISOLATED-SPIKE verdict."),
    ("stress",      "Stress-test across time",
     "Profit is SPREAD across time windows, not concentrated in one lucky stretch "
     "(🔬 Stress-test this config across time)."),
    ("oos",         "Out-of-sample / Walk-forward",
     "Survives data it was never optimized on. (auto-ticks once any Walk-Forward run exists)"),
    ("transfer",    "Cross-instrument transfer",
     "The edge appears on more than one instrument (e.g. ES AND NQ) → structural, not a "
     "single-symbol artifact. (auto-ticks once runs span ≥2 instruments)"),
    ("costs",       "Cost & slippage realism",
     "Edge survives realistic commission + slippage (raise both, re-check PF/PNL)."),
    ("drawdown",    "Drawdown / Monte-Carlo sizing",
     "Sized for the worst-case equity path, not the one lucky ordering "
     "(trade-order shuffle / Monte-Carlo on the drawdown)."),
    ("paper",       "Paper / forward test",
     "Ran live on fresh, unseen data with NO money on the line."),
    ("deploy",      "Deploy (small size)",
     "Trading it for real — start at minimum size and scale only after it behaves."),
]

# Steps Augur can tick FOR you from run history; the rest are manual judgment calls.
AUTO_CAPABLE_STEPS = {"insample", "oos", "transfer", "costs"}


def _get_roadmap(strat_file: str) -> dict:
    try:
        return dict(_load_config_json().get("roadmaps", {}).get(strat_file, {}) or {})
    except Exception:
        return {}


def _save_roadmap(strat_file: str, state: dict):
    try:
        cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
        cfg = _load_config_json()
        cfg.setdefault("roadmaps", {})[strat_file] = state
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def _roadmap_auto(strat_name: str):
    """Which steps the run history already satisfies for this strategy (by name).
    Returns (auto, run_ids): auto[step]=True, run_ids[step]=the run id that
    satisfied it (newest match) so the roadmap can LINK to the evidence."""
    auto, rids = {}, {}
    try:
        h = load_runs_light()
        if h is None or h.empty or "strategy" not in h.columns:
            return auto, rids
        hs = h[h["strategy"].astype(str).str.strip() == str(strat_name).strip()]
        if hs.empty:
            return auto, rids
        auto["insample"] = True
        rids["insample"] = int(hs.iloc[0]["id"])           # newest run overall
        if "scope" in hs.columns:
            _wf = hs[hs["scope"].astype(str).str.lower().str.contains("walk|🔁")]
            if not _wf.empty:
                auto["oos"] = True
                rids["oos"] = int(_wf.iloc[0]["id"])
        if "instrument" in hs.columns and hs["instrument"].astype(str).str.strip().nunique() >= 2:
            auto["transfer"] = True
            # link the newest run on a DIFFERENT instrument than the latest one
            _i0 = str(hs.iloc[0]["instrument"]).strip()
            _other = hs[hs["instrument"].astype(str).str.strip() != _i0]
            rids["transfer"] = int(_other.iloc[0]["id"]) if not _other.empty \
                               else int(hs.iloc[0]["id"])
        # Costs: satisfied once the edge has been measured net of real (non-zero)
        # commission/slippage — which the optimizer bakes into every config.
        _cc = pd.to_numeric(hs.get("commission_usd"), errors="coerce").fillna(0) if "commission_usd" in hs.columns else None
        _sp = pd.to_numeric(hs.get("slippage_pts"),  errors="coerce").fillna(0) if "slippage_pts"  in hs.columns else None
        if (_cc is not None and (_cc > 0).any()) or (_sp is not None and (_sp > 0).any()):
            auto["costs"] = True
            _mask = ((_cc > 0) if _cc is not None else False) | \
                    ((_sp > 0) if _sp is not None else False)
            try:
                rids["costs"] = int(hs[_mask].iloc[0]["id"])
            except Exception:
                pass
    except Exception:
        pass
    return auto, rids


def _render_validation_roadmap(strat_file: str, strat_name: str, kp: str = "",
                               parent_file: str = None):
    """Checklist of the deploy pipeline for ONE strategy, with progress + persistence.
    If the strategy declares `_AUGUR_PARENT`, the parent's ticked steps are inherited
    (flagged 'inherited — re-confirm') so a forked strategy doesn't restart at zero."""
    state = _get_roadmap(strat_file)
    auto, _run_ids = _roadmap_auto(strat_name)
    inh   = _get_roadmap(parent_file) if parent_file else {}
    def _eff(k):                 # own check > auto-detected > inherited from parent
        return bool(state.get(k, auto.get(k, bool(inh.get(k)))))
    done  = sum(1 for k, _, _ in VALIDATION_STEPS if _eff(k))
    total = len(VALIDATION_STEPS)
    pct   = int(done / total * 100)
    _col  = "var(--good)" if done == total else ("var(--accent)" if done >= total // 2 else "var(--t3)")
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin:2px 0 6px'><span style='font-size:.8rem;font-weight:700'>Deploy readiness</span>"
        f"<span style='font-size:.78rem;font-weight:800;color:{_col}'>{done}/{total} · {pct}%</span></div>"
        f"<div class='pg-t'><div class='pg-f' style='width:{pct}%'></div></div>"
        f"<div style='font-size:.68rem;opacity:.5;margin:5px 0 4px'>"
        f"<span style='color:var(--accent)'>⚙ auto</span> = Augur ticks it from your run "
        f"history · <span style='opacity:.8'>✋ manual</span> = your call"
        + (f" · <span style='color:#7fb0ff'>↳ inherited</span> from parent #"
           f"{_strategy_master_num(parent_file)} — re-confirm" if parent_file else "")
        + "</div>",
        unsafe_allow_html=True)
    # "▶ set up" deep-links: jump to the right tab with the right scope/trials
    # pre-selected (and THIS strategy activated) so a roadmap step is one click
    # from actually running its test.
    _STEP_SETUP = {
        "insample": dict(tab="▶  EXECUTIONS", scope="MEDIUM",
                         tip="Medium grid ready — pick your data, hit Run"),
        "plateau":  dict(tab="▶  EXECUTIONS", scope="MEDIUM",
                         tip="Run a Medium grid, then read the PLATEAU verdict under "
                             "the PNL Distribution in Results"),
        "oos":      dict(tab="▶  EXECUTIONS", scope="🔁 WALK-FORWARD", trials=200,
                         tip="Walk-Forward · 200 trials ready — pick data, hit Run"),
        "transfer": dict(tab="▶  EXECUTIONS", scope="🔁 WALK-FORWARD", trials=200,
                         tip="Walk-Forward ready — switch Instrument + CSV to the "
                             "OTHER market (ES↔NQ), then Run"),
        "stress":   dict(tab="◎  RESULTS",
                         tip="Load this strategy's run, then open 🔬 Stress-test "
                             "this config across time"),
        "drawdown": dict(tab="◎  RESULTS",
                         tip="Load this strategy's run, then open 🎲 Drawdown "
                             "Monte-Carlo (size to the p95)"),
    }
    changed = False
    for i, (k, lbl, hlp) in enumerate(VALIDATION_STEPS, 1):
        eff = _eff(k)
        if k in AUTO_CAPABLE_STEPS and auto.get(k):
            tag = "  ·  ⚙ auto ✓ found in history"
        elif k in AUTO_CAPABLE_STEPS:
            tag = "  ·  ⚙ auto — ticks when you run it"
        elif inh.get(k) and state.get(k) is None:
            tag = "  ·  ↳ inherited (re-confirm)"
        else:
            tag = "  ·  ✋ manual"
        _setup = _STEP_SETUP.get(k)
        _rid = _run_ids.get(k) if auto.get(k) else None
        if _setup or _rid:
            _rc1, _rc2, _rc3 = st.columns([9, 1.3, 0.9])
            new = _rc1.checkbox(f"{i}. {lbl}{tag}", value=eff,
                                key=f"{kp}rm_{strat_file}_{k}", help=hlp)
            # Evidence link: open the run that satisfied this step in Results
            if _rid and _rc2.button(f"#{_rid} ↗", key=f"{kp}ev_{strat_file}_{k}",
                                    help=f"Open run #{_rid} — the run that "
                                         f"satisfied this step — in Results"):
                try:
                    _row = load_run_by_id(int(_rid))
                    if _quick_load_run(_row):
                        st.session_state["_hist_sel_ids"] = [int(_rid)]
                        st.session_state["_pending_tab"] = "◎  RESULTS"
                        st.rerun()
                except Exception as _ex:
                    st.toast(f"Couldn't load run #{_rid}: {_ex}")
            if _setup and _rc3.button("▶", key=f"{kp}go_{strat_file}_{k}",
                                      help=f"Set this test up: {_setup['tip']}"):
                try:
                    _sp = os.path.join(STRATEGIES_DIR, strat_file)
                    if os.path.exists(_sp):
                        _set_active_strategy(_sp)
                        _save_strategy_config_json()
                except Exception:
                    pass
                if _setup.get("scope"):
                    st.session_state["_pending_scope"] = _setup["scope"]
                if _setup.get("trials"):
                    st.session_state["_pending_trials"] = _setup["trials"]
                st.session_state["_pending_tab"] = _setup["tab"]
                st.toast("→ " + _setup["tip"])
                st.rerun()
        else:
            new = st.checkbox(f"{i}. {lbl}{tag}", value=eff,
                              key=f"{kp}rm_{strat_file}_{k}", help=hlp)
        if new != _eff(k):
            state[k] = new
            changed = True
    if changed:
        _save_roadmap(strat_file, state)


def _strategy_master_num(fname: str) -> int:
    """Stable, persistent 'master number' for a strategy file — assigned the first
    time it's seen and kept in augur_config.json, so it never renumbers when other
    strategies are added or deleted. (CSVs use their permanent DB id instead.)"""
    if not fname:
        return 0
    _reg = st.session_state.get("_strat_nums")
    if _reg is None:
        _reg = dict(_load_config_json().get("strat_nums", {}))
        st.session_state["_strat_nums"] = _reg
    if fname not in _reg:
        _reg[fname] = (max(_reg.values()) + 1) if _reg else 1
        st.session_state["_strat_nums"] = _reg
        try:
            cfg_path = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
            existing = _load_config_json()
            existing["strat_nums"] = _reg
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception:
            pass
    return int(_reg[fname])

# On startup: restore last-used strategy
_cfg = _load_config_json()
if _cfg.get("active_strategy") and os.path.exists(_cfg["active_strategy"]):
    _set_active_strategy(_cfg["active_strategy"])

# ══════════════════════════════════════════════════════════════════════════════
#  AUGUR — Strategy Optimizer  v3.0  UI

# ══════════════════════════════════════════════════════════════════════════════
#  AUGUR  - Strategy Optimizer v3.3
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  AUGUR v4.0  —  UI Layer
# ══════════════════════════════════════════════════════════════════════════════

APP_NAME = "Augur"
__version_display__ = __version__

# ── THEMES ────────────────────────────────────────────────────────────────────
THEMES = {
    "Liquid Carbon":     "Carbon-fiber dark · liquid glass frost",
    "Liquid Gunmetal":   "Steel-blue metal · liquid glass frost",
    "Vapor Glass":    "Frosted dark · violet→teal accent",
    "Mercury Mono":   "Pure grayscale glass",
    "Origin Indigo":  "Single-hue indigo fintech",
    "Default":   "Dark teal",
    "Mercury":   "Chrome glass",
    "Obsidian":  "Deep matte black",
    "Ash":       "Warm charcoal",
}

_BASE_CSS = """
<style>
/* Readability: lift the smallest caption/help text site-wide */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{
    font-size:.8rem !important; opacity:.75 !important; line-height:1.5 !important}
/* ── Reset gap ── */
/* Flush top app-bar: kill Streamlit's header, pull content to the top ── */
/* Header: make it invisible but KEEP it in the layout so the sidebar
   collapse/expand control (which lives inside it) stays reachable. */
[data-testid="stHeader"]{background:transparent !important;
    box-shadow:none !important;height:0 !important;min-height:0 !important}
[data-testid="stToolbar"]{visibility:hidden !important;pointer-events:none !important}
[data-testid="stDecoration"]{display:none !important}
/* Sidebar: narrower default (240px) and COLLAPSIBLE again. Only force the width
   while it's OPEN; the collapse arrow is restored so the user can hide it and the
   main area gets the room back. */
/* Allow a RANGE (not a hard lock) so Streamlit's native drag-resize handle on the
   sidebar's right edge works — locking width:240px!important disabled it, so the
   sidebar could only be collapsed/expanded, never widened. */
[data-testid="stSidebar"][aria-expanded="true"]{
    min-width:240px !important;max-width:620px !important}
/* Sidebar toggle buttons.
   stExpandSidebarButton = reopen chevron (lives in the 0-height stHeader, so it
   gets crushed to 0×0 — pull it out with position:fixed below the appbar).
   stSidebarCollapsedControl = older Streamlit name for the same thing; keep both.
   stSidebarCollapseButton = close arrow inside the open sidebar. */
/* stExpandSidebarButton is a <button> inside stToolbar (which we hide via
   visibility:hidden). Use visibility:visible + position:fixed to escape the
   hidden parent and pin the reopen chevron just below the appbar. */
[data-testid="stExpandSidebarButton"]{
    position:fixed !important;visibility:visible !important;opacity:1 !important;
    display:flex !important;align-items:center !important;justify-content:center !important;
    z-index:1000000 !important;left:8px !important;top:54px !important;
    width:32px !important;height:32px !important;
    background:var(--bg2) !important;border:1px solid var(--s1) !important;
    border-radius:9px !important;box-shadow:0 2px 10px rgba(0,0,0,.4) !important;
    color:var(--t2) !important;cursor:pointer !important;pointer-events:auto !important}
/* Legacy testid for older Streamlit versions */
[data-testid="stSidebarCollapsedControl"]{
    position:fixed !important;visibility:visible !important;opacity:1 !important;
    display:flex !important;z-index:1000000 !important;
    left:8px !important;top:54px !important;width:32px !important;height:32px !important}
[data-testid="stSidebarCollapsedControl"] button{
    width:32px !important;height:32px !important;
    background:var(--bg2) !important;border:1px solid var(--s1) !important;
    border-radius:9px !important;color:var(--t2) !important}
/* Close arrow inside the open sidebar — always visible */
[data-testid="stSidebarCollapseButton"]{
    visibility:visible !important;opacity:1 !important;z-index:1000000 !important}
[data-testid="stSidebarCollapseButton"] button{
    background:transparent !important;color:var(--t2) !important;border:none !important}
.block-container{padding-top:0 !important}
[data-testid="stMainBlockContainer"]{padding-top:0 !important}
[data-testid="stAppViewBlockContainer"]{padding-top:0 !important}
/* Context strip overlays the right end of the tab row (zero vertical cost).
   The main-page logo is GONE — it lives in the sidebar; tabs sit flush left so
   they align vertically with the tiles beneath them. */
[data-testid="stMainBlockContainer"]{position:relative}
div[data-testid="stElementContainer"]:has(.ctxstrip){
    position:absolute;top:0;left:0;right:0;z-index:30;width:auto !important;
    margin:0 !important;padding:0 !important;height:0 !important;min-height:0 !important;
    pointer-events:none}
.ctxstrip{position:absolute;top:15px;right:5rem;font-size:.68rem;color:var(--t3);
    display:flex;gap:14px;align-items:center;white-space:nowrap;pointer-events:none;
    overflow:hidden;max-width:34vw;text-overflow:ellipsis}
/* Narrow window: drop the strip rather than let it overlap the tab labels */
@media (max-width:1250px){.ctxstrip{display:none}}
.ctxstrip b{color:var(--t2);font-weight:700}
.ctxstrip .ok{color:var(--good)} .ctxstrip .acc{color:var(--accent)}
/* ── Tabs: monochrome strip, flush left — aligned with the tiles below.
   The MAIN tab bar is STICKY: it pins to the top of the viewport as you
   scroll (glassy backdrop so content sliding under stays legible). Only the
   top-level bar sticks — nested sub-tab bars (Library/Results) scroll away. */
[data-testid="stTabs"]{background:transparent;border-bottom:1px solid var(--s2);
    padding:0;margin:0 0 10px 0}
[data-testid="stTabs"] [data-baseweb="tab-list"]{gap:2px !important;
    justify-content:flex-start}
/* Sticky must sit on the tab-bar WRAPPER (first child of the tabs root): the
   tab-list's own parent is exactly its height, so sticky on the list itself had
   zero room to travel. :not(tab-panel *) keeps nested sub-tab bars normal. */
[data-testid="stMainBlockContainer"]
  [data-testid="stTabs"]:not([data-baseweb="tab-panel"] *) > div > div:first-child{
    position:sticky !important;top:0 !important;z-index:60;
    background:rgba(10,12,18,.82) !important;
    backdrop-filter:blur(22px) saturate(140%);
    -webkit-backdrop-filter:blur(22px) saturate(140%);
    border-bottom:1px solid var(--s2)}
[data-testid="stTabs"] button{background:transparent !important;border:none !important;
    border-bottom:2px solid transparent !important;
    padding:14px 16px !important;font-size:.72rem !important;font-weight:600 !important;
    letter-spacing:.13em !important;text-transform:uppercase !important;
    color:var(--t3) !important;transition:all .15s !important;margin-bottom:-1px !important;
    font-variant-emoji:text !important}
[data-testid="stTabs"] button p{font-variant-emoji:text !important}
[data-testid="stTabs"] button[aria-selected="true"]{color:var(--t1) !important;
    border-bottom:2px solid var(--accent) !important;background:transparent !important}
[data-testid="stTabs"] button:hover{color:var(--t1) !important;background:transparent !important}
[data-testid="stTabsContent"]{padding-top:.6rem !important;clear:both}
/* ── Tiles ── */
/* Liquid glass: near-transparent fill + heavy blur so tiles melt into the
   background; a faint top-sheen gradient gives the "wet glass" read. */
.tile{background:linear-gradient(165deg,rgba(255,255,255,.045),rgba(255,255,255,.012) 38%,rgba(255,255,255,.02));
    border-radius:var(--r);padding:16px 20px;margin-bottom:10px;
    border:1px solid rgba(255,255,255,.05);
    backdrop-filter:blur(28px) saturate(170%);
    -webkit-backdrop-filter:blur(28px) saturate(170%);
    box-shadow:0 1px 0 rgba(255,255,255,.07) inset, 0 4px 24px rgba(0,0,0,.14);
    transition:all .2s}
.tile:hover{background:linear-gradient(165deg,rgba(255,255,255,.06),rgba(255,255,255,.02) 38%,rgba(255,255,255,.03));
    box-shadow:0 1px 0 rgba(255,255,255,.1) inset, 0 6px 28px rgba(0,0,0,.22)}
.tile-active{background:var(--s3) !important;
    border:1px solid rgba(255,255,255,.18) !important;
    box-shadow:0 1px 0 rgba(255,255,255,.16) inset, 0 8px 32px rgba(0,0,0,.35) !important}
/* Keyed-container tiles (st.container(key="tilebox_*")) render as glass tiles */
[class*="st-key-tilebox_"]{
    background:linear-gradient(165deg,rgba(255,255,255,.045),rgba(255,255,255,.012) 38%,rgba(255,255,255,.02)) !important;
    border-radius:var(--r) !important;
    padding:16px 20px !important;margin-bottom:20px !important;
    border:1px solid rgba(255,255,255,.05) !important;
    backdrop-filter:blur(28px) saturate(170%) !important;
    -webkit-backdrop-filter:blur(28px) saturate(170%) !important;
    box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 6px 26px rgba(0,0,0,.15) !important}
.tile-h{font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;
    color:var(--t3);font-weight:700;margin-bottom:10px}
/* Sidebar run / queue tiles — each run is one card */
[class*="st-key-runtile_"], [class*="st-key-qtile_"]{
    background:var(--s1) !important;border-radius:10px !important;
    padding:10px 12px !important;margin-bottom:8px !important;
    border:1px solid var(--glass-bd,rgba(255,255,255,.08)) !important;
    box-shadow:0 1px 0 var(--glass-edge,rgba(255,255,255,.06)) inset !important}
[class*="st-key-runtile_"] .stButton button,
[class*="st-key-qtile_"] .stButton button{
    padding:3px 0 !important;font-size:.72rem !important;font-weight:600 !important;
    min-height:0 !important;border-radius:7px !important;
    background:var(--s2) !important;border:1px solid var(--glass-bd,rgba(255,255,255,.1)) !important}
[class*="st-key-runtile_"] .stButton button:hover,
[class*="st-key-qtile_"] .stButton button:hover{
    background:var(--accent) !important;color:#0a0c14 !important}
[class*="st-key-runtile_"] [data-testid="stHorizontalBlock"],
[class*="st-key-qtile_"] [data-testid="stHorizontalBlock"]{gap:4px !important}
[class*="st-key-runtile_"] [data-testid="column"],
[class*="st-key-qtile_"] [data-testid="column"]{padding:0 1px !important}
/* Quick-select chips: compact cell-like toggle buttons */
[class*="st-key-qchip_"] .stButton button{
    background:var(--s2) !important;border:1px solid var(--glass-bd,rgba(255,255,255,.08)) !important;
    color:var(--t2) !important;font-size:.7rem !important;font-weight:600 !important;
    padding:2px 9px !important;border-radius:7px !important;min-height:0 !important;
    height:26px !important;line-height:1 !important;
    box-shadow:none !important;transition:background .1s,color .1s,border-color .1s !important;
    white-space:nowrap}
[class*="st-key-qchip_"] .stButton button:hover{
    background:var(--s3) !important;color:var(--t1) !important;
    border-color:var(--accent) !important}
[class*="st-key-qchipsel_"] .stButton button{
    background:var(--accent) !important;color:#0a0c14 !important;
    border:1px solid var(--accent) !important;font-size:.7rem !important;font-weight:700 !important;
    padding:2px 9px !important;border-radius:7px !important;min-height:0 !important;
    height:26px !important;line-height:1 !important;
    box-shadow:none !important;white-space:nowrap}
[class*="st-key-qmore_"] .stButton button{
    background:transparent !important;border:1px dashed var(--glass-bd,rgba(255,255,255,.14)) !important;
    color:var(--t3) !important;font-size:.7rem !important;font-weight:700 !important;
    padding:2px 8px !important;border-radius:7px !important;min-height:0 !important;
    height:26px !important;line-height:1 !important;box-shadow:none !important}
[class*="st-key-qmore_"] .stButton button:hover{color:var(--t1) !important;
    border-color:var(--accent) !important}
.qchip-wrap [data-testid="stHorizontalBlock"]{gap:5px !important;flex-wrap:wrap}
.qchip-wrap [data-testid="column"]{width:auto !important;flex:0 0 auto !important;padding:0 !important;min-width:0 !important}
/* Active strategy tile: accent left edge */
[class*="st-key-tilebox_strat_act_"]{
    border-left:3px solid var(--accent) !important;
    background:var(--s3) !important}
/* Selected tile (Library action-bar model): bright accent ring on strategy OR csv */
[class*="st-key-tilebox_strat"][class*="xsel_"],
[class*="st-key-tilebox_csvsel_"]{
    border:1.5px solid var(--accent) !important;
    box-shadow:0 0 0 1px var(--accent) inset,0 6px 26px rgba(0,0,0,.28) !important;
    background:var(--s3) !important}
/* Library consolidated action bars: a sticky-feeling toolbar above the tiles */
[class*="st-key-lib_strat_actionbar"],[class*="st-key-lib_csv_actionbar"]{
    background:var(--s2) !important;border:1px solid var(--accent) !important;
    border-radius:12px !important;padding:8px 12px !important;margin-bottom:12px !important;
    box-shadow:0 4px 18px rgba(0,0,0,.22) !important}
[class*="st-key-lib_strat_actionbar"] .stButton button,
[class*="st-key-lib_strat_actionbar"] .stDownloadButton button,
[class*="st-key-lib_csv_actionbar"] .stButton button,
[class*="st-key-lib_csv_actionbar"] .stDownloadButton button{
    white-space:nowrap !important;font-size:.74rem !important;font-weight:600 !important;
    padding:5px 6px !important;min-height:0 !important;min-width:0 !important;overflow:hidden}
/* Quiet action buttons inside tiles (icon-led, low emphasis until hover) */
.tile-row .stButton button, .tile-row .stDownloadButton button,
[class*="st-key-tilebox_strat"] .stButton button,
[class*="st-key-tilebox_strat"] .stDownloadButton button{
    background:rgba(255,255,255,.04) !important;
    border:1px solid rgba(255,255,255,.06) !important;
    font-size:.72rem !important;font-weight:500 !important;
    padding:5px 4px !important;opacity:.75;
    white-space:nowrap !important;min-width:0 !important;
    min-height:0 !important;line-height:1.1 !important;overflow:hidden}
.tile-row .stButton button:hover, .tile-row .stDownloadButton button:hover,
[class*="st-key-tilebox_strat"] .stButton button:hover,
[class*="st-key-tilebox_strat"] .stDownloadButton button:hover{
    opacity:1;background:var(--accent) !important;color:#0a0c14 !important}
/* Past-runs toolbar: filters + actions on ONE row — keep labels on one line so
   they don't letter-stack when the columns get tight. */
[class*="st-key-hist_toolbar_box"] .stButton button,
[class*="st-key-hist_toolbar_box"] .stDownloadButton button{
    white-space:nowrap !important;min-width:0 !important;overflow:hidden;
    padding:5px 6px !important;font-size:.73rem !important;line-height:1.15 !important}
[class*="st-key-hist_toolbar_box"] [data-baseweb="select"]{font-size:.78rem}
/* ── KPI ── */
.kg{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 10px}
.kt{flex:1 1 120px;min-width:112px;max-width:190px;padding:10px 14px;border-radius:var(--r);background:var(--s1)}
.kl{font-size:.71rem;text-transform:uppercase;letter-spacing:.12em;color:var(--t4);margin-bottom:1px}
.kv{font-size:1.35rem;font-weight:700;color:var(--t1);line-height:1.15}
.kd{font-size:.73rem;margin-top:2px}
.kp{color:var(--good)}.kn{color:var(--bad)}.km{color:var(--t4)}
/* KPI comparison matrix (Overall / In-sample / Out-of-sample × PNL/WR/PF/Trades) */
.mx{display:grid;grid-template-columns:118px repeat(4,1fr);gap:6px;margin:4px 0 10px;align-items:stretch}
.mcell{padding:8px 12px;border-radius:var(--r);background:var(--s1);font-size:1.06rem;
  font-weight:700;color:var(--t1);line-height:1.15;display:flex;align-items:center}
.mrl{display:flex;align-items:center;font-size:.74rem;font-weight:700;color:var(--t2);
  text-transform:uppercase;letter-spacing:.05em}
.mhd{font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;color:var(--t4);
  font-weight:600;align-self:end;padding:0 4px 3px}
/* ── Section label ── */
.sl{font-size:.71rem;font-weight:600;text-transform:uppercase;letter-spacing:.16em;
    color:var(--t4);margin-bottom:10px}
/* ── Badges ── */
.bg{display:inline-block;padding:1px 7px;border-radius:20px;font-size:.71rem;font-weight:700}
.bg-g{background:rgba(0,200,140,.12);color:var(--good)}
.bg-b{background:rgba(100,150,255,.12);color:var(--info)}
.bg-y{background:rgba(255,200,50,.12);color:var(--warn)}
.bg-r{background:rgba(220,90,90,.12);color:var(--bad)}
.bg-x{opacity:.4}
/* ── Status bar ── */
.sb{display:flex;align-items:center;gap:12px;padding:7px 16px;border-radius:var(--r);
    background:var(--s1);font-size:.76rem;margin-bottom:8px}
.sb-l{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--t4)}
.sb-v{font-weight:600;color:var(--t1)}.sb-d{opacity:.15}
/* ── Progress ── */
.pg-t{border-radius:3px;height:4px;overflow:hidden;background:var(--s1);margin-top:5px}
.pg-f{height:4px;border-radius:3px;background:var(--accent);transition:width .4s}
/* ── Exec row ── */
.er{background:transparent;border-radius:var(--r);padding:8px 2px;margin-bottom:2px;
    border-bottom:1px solid var(--s1)}
/* ── Metric ── */
div[data-testid="metric-container"]{background:var(--s1) !important;
    border-radius:var(--r) !important;padding:10px 14px !important;border:none !important}
/* ── Misc ── */
hr{opacity:.08 !important}
/* Kill horizontal divider bleed between/inside tiles */
[data-testid="stVerticalBlock"]{gap:.4rem !important}
[data-testid="stVerticalBlockBorderWrapper"]{border:none !important;box-shadow:none !important}
[data-testid="stHorizontalBlock"]{border:none !important}
.tile [data-testid="stVerticalBlock"]{gap:.25rem !important}
.tile hr, .tile + hr{display:none !important}
/* Tighten button row vertical footprint inside tiles */
.tile-row{margin-top:-2px}
.tile-row [data-testid="column"]{padding:0 2px}
/* Run bar — keyed container pinned just below the tab row, right-aligned.
   Native buttons inside (no JS relocation -> no duplicates, no flashing). */
.st-key-rundock_box{position:fixed;top:50px;right:16px;z-index:9990;
    width:min(640px,72vw);
    background:var(--bg2);
    backdrop-filter:blur(30px) saturate(140%);
    -webkit-backdrop-filter:blur(30px) saturate(140%);
    border:1px solid var(--glass-bd,rgba(255,255,255,.12));border-radius:11px;
    box-shadow:0 6px 24px rgba(0,0,0,.35);
    padding:8px 14px !important}
.st-key-rundock_box [data-testid="stHorizontalBlock"]{gap:8px !important;align-items:center}
.st-key-rundock_box [data-testid="column"]{padding:0 2px !important}
.st-key-rundock_box .stButton button{
    padding:3px 0 !important;font-size:.82rem !important;font-weight:700 !important;
    min-height:0 !important;
    background:var(--s2) !important;border:1px solid rgba(255,255,255,.12) !important;
    margin:0 !important}
.st-key-rundock_box .stButton button:hover{
    background:var(--accent) !important;color:#0a0c14 !important}
/* Smooth the progress bar so timer refreshes don't flash */
.st-key-rundock_box .pg-f{transition:width .4s ease}
/* Continuous CSS spinner for live runs — spins smoothly in the browser regardless
   of how often Streamlit reruns, so "is it still going?" is always obvious. */
@keyframes augurspin{to{transform:rotate(360deg)}}
.augur-spin{display:inline-block;width:9px;height:9px;border:2px solid var(--accent);
    border-top-color:transparent;border-radius:50%;animation:augurspin .7s linear infinite;
    vertical-align:-1px;margin-right:3px}
/* Inline info hint — hover for the explanation; replaces space-eating captions */
.ihint{display:inline-flex;align-items:center;justify-content:center;
    width:15px;height:15px;border-radius:50%;border:1px solid rgba(255,255,255,.25);
    color:var(--t3);font-size:.6rem;font-weight:700;margin-left:7px;cursor:help;
    vertical-align:1px;font-style:normal}
.ihint:hover{color:var(--t1);border-color:var(--accent)}
/* ── GLASS UNIFICATION (origin-style minimalism) ─────────────────────────────
   One surface recipe for EVERY card-like element across all tabs: a barely-there
   gradient fill, hairline border, deep blur, no drop shadows. The content reads;
   the chrome disappears. */
.tile, [class*="st-key-tilebox_"],
[class*="st-key-runtile_"], [class*="st-key-qtile_"],
.st-key-lib_strat_actionbar, .st-key-lib_csv_actionbar,
.st-key-hist_toolbar_box, .kt, .er{
    background:linear-gradient(168deg,rgba(255,255,255,.028),rgba(255,255,255,.006) 42%,rgba(255,255,255,.012)) !important;
    border:1px solid rgba(255,255,255,.042) !important;
    backdrop-filter:blur(32px) saturate(155%) !important;
    -webkit-backdrop-filter:blur(32px) saturate(155%) !important;
    box-shadow:0 1px 0 rgba(255,255,255,.045) inset !important;
    border-radius:var(--r) !important}
.tile:hover, [class*="st-key-tilebox_"]:hover{
    background:linear-gradient(168deg,rgba(255,255,255,.04),rgba(255,255,255,.012) 42%,rgba(255,255,255,.018)) !important}
/* Expanders: glass lives on the OUTER stExpander wrapper only; the inner
   details/summary stay fully transparent (stacked layers read heavier than
   the tiles — the "dropdown tiles don't match" issue). */
[data-testid="stExpander"] details{
    background:transparent !important;border:none !important;
    box-shadow:none !important;
    backdrop-filter:none !important;-webkit-backdrop-filter:none !important}
[data-testid="stExpander"] summary{background:transparent !important}
.block-container{padding-bottom:40px !important}
/* History action toolbar — flat, blends into background like the tab row */
.st-key-hist_toolbar_box{border-bottom:1px solid rgba(255,255,255,.06);
    margin-bottom:6px;padding-bottom:2px}
.st-key-hist_toolbar_box .stButton > button,
.st-key-hist_toolbar_box .stDownloadButton > button{
    background:transparent !important;background-color:transparent !important;
    border:none !important;border-radius:0 !important;
    color:var(--t3) !important;font-size:.82rem !important;font-weight:600 !important;
    padding:6px 2px !important;box-shadow:none !important;
    border-bottom:2px solid transparent !important;
    transition:color .12s,border-color .12s;width:100% !important;min-height:0 !important}
.st-key-hist_toolbar_box .stButton > button:hover,
.st-key-hist_toolbar_box .stDownloadButton > button:hover{
    background:transparent !important;background-color:transparent !important;
    color:var(--t1) !important;border:none !important;
    border-bottom:2px solid var(--accent) !important}
.st-key-hist_toolbar_box .stButton > button:active,
.st-key-hist_toolbar_box .stButton > button:focus,
.st-key-hist_toolbar_box .stButton > button:focus-visible,
.st-key-hist_toolbar_box .stDownloadButton > button:active,
.st-key-hist_toolbar_box .stDownloadButton > button:focus{
    background:transparent !important;background-color:transparent !important;
    border:none !important;border-bottom:2px solid var(--accent) !important;
    box-shadow:none !important;color:var(--t1) !important}
.st-key-hist_toolbar_box .stButton > button:disabled,
.st-key-hist_toolbar_box .stDownloadButton > button:disabled{
    color:var(--t4) !important;opacity:.35 !important;
    background:transparent !important;border:none !important;
    border-bottom:2px solid transparent !important}
.st-key-hist_toolbar_box [data-testid="column"]{padding:0 !important}
.st-key-hist_toolbar_box [data-testid="stHorizontalBlock"]{gap:4px !important;align-items:center}
/* Past runs (expander) + Results — SAME glass recipe as every other tile
   (the old var(--s1) fill made expanders visibly more opaque than tiles). */
[data-testid="stExpander"]{
    background:linear-gradient(168deg,rgba(255,255,255,.028),rgba(255,255,255,.006) 42%,rgba(255,255,255,.012)) !important;
    border:1px solid rgba(255,255,255,.042) !important;
    border-radius:var(--r) !important;
    backdrop-filter:blur(32px) saturate(155%) !important;
    -webkit-backdrop-filter:blur(32px) saturate(155%) !important;
    box-shadow:0 1px 0 rgba(255,255,255,.045) inset !important}
.st-key-results_box{
    background:linear-gradient(168deg,rgba(255,255,255,.028),rgba(255,255,255,.006) 42%,rgba(255,255,255,.012)) !important;
    border:1px solid rgba(255,255,255,.042) !important;
    border-radius:var(--r) !important;padding:18px 20px !important;
    backdrop-filter:blur(32px) saturate(155%) !important;
    -webkit-backdrop-filter:blur(32px) saturate(155%) !important;
    box-shadow:0 1px 0 var(--glass-edge,rgba(255,255,255,.08)) inset,0 6px 24px rgba(0,0,0,.2) !important}
/* Compact sort dropdown in the toolbar */
.st-key-hist_toolbar_box .stSelectbox div[data-baseweb="select"]>div{
    min-height:0 !important;padding:2px 6px !important;font-size:.78rem !important;
    background:transparent !important;border:1px solid var(--glass-bd,rgba(255,255,255,.1)) !important}
/* Target each toolbar button by its own key wrapper (most robust).
   Double the key-class to out-specify the global .stButton rule. */
.st-key-h_cmp.st-key-h_cmp button, .st-key-h_star.st-key-h_star button,
.st-key-h_del.st-key-h_del button,
.st-key-h_dl_html.st-key-h_dl_html button, .st-key-h_dl_all.st-key-h_dl_all button,
.st-key-h_dl_top.st-key-h_dl_top button,
.st-key-h_dl_html_x button, .st-key-h_dl_html_d button,
.st-key-h_dl_all_d button, .st-key-h_dl_top_d button{
    background:transparent !important;background-color:transparent !important;
    border:none !important;border-radius:0 !important;box-shadow:none !important;
    color:var(--t2) !important;font-size:.78rem !important;font-weight:600 !important;
    padding:6px 2px !important;min-height:0 !important;
    border-bottom:2px solid transparent !important}
.st-key-h_cmp.st-key-h_cmp button:hover, .st-key-h_star.st-key-h_star button:hover,
.st-key-h_del.st-key-h_del button:hover,
.st-key-h_dl_html.st-key-h_dl_html button:hover,
.st-key-h_dl_all.st-key-h_dl_all button:hover,
.st-key-h_dl_top.st-key-h_dl_top button:hover{
    background:transparent !important;background-color:transparent !important;
    color:var(--t1) !important;border:none !important;
    border-bottom:2px solid var(--accent) !important}
.st-key-h_cmp.st-key-h_cmp button:disabled, .st-key-h_star.st-key-h_star button:disabled,
.st-key-h_del.st-key-h_del button:disabled,
.st-key-h_dl_html_x button:disabled, .st-key-h_dl_html_d button:disabled,
.st-key-h_dl_all_d button:disabled, .st-key-h_dl_top_d button:disabled{
    background:transparent !important;background-color:transparent !important;
    border:none !important;border-bottom:2px solid transparent !important;
    box-shadow:none !important;color:var(--t4) !important;opacity:.35 !important}
/* Compact number inputs in Custom scope — tighter height, smaller labels */
.stNumberInput label{font-size:.71rem !important;opacity:.5 !important;
    text-transform:uppercase;letter-spacing:.06em;margin-bottom:0 !important}
.stNumberInput input{padding:4px 6px !important;font-size:.82rem !important}
.stNumberInput button{padding:0 !important;min-height:0 !important}
[data-testid="stSidebar"]{background:var(--bg2);border-right:1px solid var(--s1)}
/* Pull the sidebar content up — stock padding left a big dead gap above the
   🔮 Augur block. Header (collapse chevron row) keeps just enough height. */
/* Sidebar: float the collapse-chevron header at top-right so the Augur
   block starts at the very top, horizontally aligned with the main tab row
   (the header row used to push everything ~45px down). */
[data-testid="stSidebarHeader"]{position:absolute !important;top:2px;right:2px;
    z-index:10;padding:4px !important;height:auto !important;
    background:transparent !important}
[data-testid="stSidebarUserContent"]{padding-top:10px !important}
/* ── Buttons: make interactive elements clearly tappable ── */
.stButton button, .stDownloadButton button{
    background:var(--s2) !important;
    color:var(--t1) !important;
    border:1px solid rgba(255,255,255,.08) !important;
    border-radius:var(--r) !important;
    font-size:.78rem !important;font-weight:600 !important;
    transition:all .15s !important;
}
.stButton button:hover, .stDownloadButton button:hover{
    background:var(--accent) !important;
    color:#0a0c14 !important;
    border-color:var(--accent) !important;
}
/* Primary buttons (Run, Save) get the accent fill by default */
.stButton button[kind="primary"]{
    background:var(--accent) !important;color:#0a0c14 !important;
    border-color:var(--accent) !important;
}
.stButton button[kind="primary"]:hover{opacity:.85 !important}
/* Text inputs / selects: subtle surface so they read as editable */
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"],
.stTextArea textarea{
    background:var(--s1) !important;
    border:1px solid rgba(255,255,255,.06) !important;
    border-radius:var(--r) !important;color:var(--t1) !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus{
    border-color:var(--accent) !important;
}
</style>
"""

_GLASS_FX = """
.tile,.kt,.er,.sb,div[data-testid="metric-container"]{
backdrop-filter:blur(30px) saturate(130%) !important;
-webkit-backdrop-filter:blur(30px) saturate(130%) !important;
box-shadow:0 1px 0 var(--glass-edge) inset,0 8px 32px rgba(0,0,0,.28) !important;
border:1px solid var(--glass-bd) !important}
.sl,.sb-l,.kl{letter-spacing:.14em !important;font-weight:500 !important}
"""

_THEME_CSS = {
"Liquid Glass Light": """<style>:root{
--bg:#EAF0FA;--bg2:rgba(255,255,255,.55);
--s1:rgba(20,40,80,.05);--s2:rgba(20,40,80,.09);--s3:rgba(60,120,240,.12);
--r:18px;--t1:#0F1A2E;--t2:#46546E;--t3:rgba(20,35,65,.5);--t4:rgba(20,35,65,.38);
--accent:#2E7BFF;--good:#16B981;--bad:#F0506A;--warn:#E0A020;--info:#2E7BFF;
--glass-edge:rgba(255,255,255,.85);--glass-bd:rgba(255,255,255,.7);
--tab-bar:rgba(255,255,255,.4);--tab-sel:rgba(46,123,255,.12);--tab-hov:rgba(255,255,255,.6);
}[data-testid="stAppViewContainer"]{
background:
  radial-gradient(ellipse 80% 60% at 12% 0%,rgba(120,170,255,.30),transparent 60%),
  radial-gradient(ellipse 70% 55% at 90% 10%,rgba(190,150,255,.24),transparent 55%),
  radial-gradient(ellipse 90% 70% at 50% 100%,rgba(120,235,200,.22),transparent 60%),
  linear-gradient(165deg,#F4F8FF,#EAF0FA 60%,#E2EAF6) !important;
background-attachment:fixed !important;color:var(--t1)}
.tile,.kt,.er,.sb,div[data-testid="metric-container"]{
backdrop-filter:blur(36px) saturate(160%) brightness(1.04) !important;
-webkit-backdrop-filter:blur(36px) saturate(160%) brightness(1.04) !important;
background:linear-gradient(155deg,rgba(255,255,255,.75),rgba(255,255,255,.5)) !important;
box-shadow:0 1px 0 var(--glass-edge) inset,0 0 0 .5px rgba(255,255,255,.5) inset,
  0 10px 34px rgba(40,80,160,.12),0 2px 8px rgba(46,123,255,.05) !important;
border:1px solid var(--glass-bd) !important;
border-radius:var(--r) !important}
.sl,.sb-l,.kl{letter-spacing:.14em !important;font-weight:500 !important}
.pg-f{background:linear-gradient(90deg,#2E7BFF,#16B981)}</style>""",

"Liquid Carbon": """<style>:root{
--bg:#0A0B0D;--bg2:rgba(16,18,20,.55);
--s1:rgba(255,255,255,.05);--s2:rgba(255,255,255,.09);--s3:rgba(90,200,250,.14);
--r:18px;--t1:#EDEFF2;--t2:#9AA0A8;--t3:rgba(255,255,255,.4);--t4:rgba(255,255,255,.3);
--accent:#5AC8FA;--good:#3FD08A;--bad:#FF5F6D;--warn:#FFC15A;--info:#5AC8FA;
--glass-edge:rgba(255,255,255,.2);--glass-bd:rgba(255,255,255,.12);
--tab-bar:rgba(255,255,255,.025);--tab-sel:rgba(90,200,250,.14);--tab-hov:rgba(255,255,255,.045);
}[data-testid="stAppViewContainer"]{
background:
  repeating-linear-gradient(45deg,rgba(255,255,255,.013) 0 2px,transparent 2px 6px),
  radial-gradient(ellipse 80% 60% at 18% 0%,rgba(90,200,250,.10),transparent 60%),
  radial-gradient(ellipse 70% 55% at 88% 12%,rgba(255,255,255,.04),transparent 55%),
  radial-gradient(ellipse at 30% 0%,#15171B,#0A0B0D 58%,#060708) !important;
background-attachment:fixed !important;color:var(--t1)}
.tile,.kt,.er,.sb,div[data-testid="metric-container"]{
backdrop-filter:blur(52px) saturate(190%) brightness(1.06) !important;
-webkit-backdrop-filter:blur(52px) saturate(190%) brightness(1.06) !important;
background:linear-gradient(155deg,rgba(30,34,40,.5),rgba(17,20,25,.4)),
  linear-gradient(155deg,rgba(255,255,255,.24),rgba(255,255,255,.06)) !important;
box-shadow:0 1.5px 0 rgba(255,255,255,.45) inset,0 0 0 1px rgba(255,255,255,.09) inset,
  0 2px 34px rgba(255,255,255,.07) inset,
  0 20px 54px rgba(0,0,0,.52),0 3px 16px rgba(90,200,250,.10) !important;
border:1px solid rgba(255,255,255,.18) !important;border-radius:20px !important}
.sl,.sb-l,.kl{letter-spacing:.14em !important;font-weight:500 !important}
.pg-f{background:linear-gradient(90deg,#5AC8FA,#3FD08A)}</style>""",

"Liquid Gunmetal": """<style>:root{
--bg:#0D1014;--bg2:rgba(18,22,28,.55);
--s1:rgba(160,180,200,.06);--s2:rgba(160,180,200,.10);--s3:rgba(127,168,201,.16);
--r:18px;--t1:#E6EAF0;--t2:#919BAA;--t3:rgba(200,212,228,.42);--t4:rgba(200,212,228,.3);
--accent:#8FB8D9;--good:#5FBE9A;--bad:#E5707E;--warn:#D8B36A;--info:#8FB8D9;
--glass-edge:rgba(190,210,230,.2);--glass-bd:rgba(170,190,210,.14);
--tab-bar:rgba(160,180,200,.03);--tab-sel:rgba(127,168,201,.16);--tab-hov:rgba(160,180,200,.05);
}[data-testid="stAppViewContainer"]{
background:
  radial-gradient(ellipse 80% 60% at 18% 0%,rgba(127,168,201,.16),transparent 60%),
  radial-gradient(ellipse 70% 55% at 88% 12%,rgba(150,170,200,.10),transparent 55%),
  linear-gradient(160deg,#1A2029,#0D1014 55%,#090C10) !important;
background-attachment:fixed !important;color:var(--t1)}
.tile,.kt,.er,.sb,div[data-testid="metric-container"]{
backdrop-filter:blur(52px) saturate(180%) brightness(1.05) !important;
-webkit-backdrop-filter:blur(52px) saturate(180%) brightness(1.05) !important;
background:linear-gradient(155deg,rgba(26,32,40,.5),rgba(15,19,25,.4)),
  linear-gradient(155deg,rgba(200,218,236,.22),rgba(200,218,236,.06)) !important;
box-shadow:0 1.5px 0 rgba(220,232,245,.42) inset,0 0 0 1px rgba(200,218,236,.09) inset,
  0 2px 34px rgba(200,218,236,.07) inset,
  0 20px 54px rgba(0,0,0,.48),0 3px 16px rgba(127,168,201,.11) !important;
border:1px solid rgba(200,218,236,.18) !important;border-radius:20px !important}
.sl,.sb-l,.kl{letter-spacing:.14em !important;font-weight:500 !important}
.pg-f{background:linear-gradient(90deg,#8FB8D9,#A9C3DA)}</style>""",

"Vapor Glass": """<style>:root{
--bg:#0B0E14;--bg2:rgba(11,14,20,.7);
--s1:rgba(255,255,255,.035);--s2:rgba(255,255,255,.06);--s3:rgba(124,92,255,.10);
--r:14px;--t1:#EAF0FF;--t2:#9BA6BC;--t3:rgba(255,255,255,.34);--t4:rgba(255,255,255,.3);
--accent:#7C5CFF;--good:#46E0C8;--bad:#FF6A8A;--warn:#FFC861;--info:#6FA8FF;
--glass-edge:rgba(255,255,255,.10);--glass-bd:rgba(255,255,255,.09);
--tab-bar:rgba(255,255,255,.02);--tab-sel:rgba(124,92,255,.10);--tab-hov:rgba(255,255,255,.03);
}[data-testid="stAppViewContainer"]{
background:radial-gradient(ellipse at 25% 12%,#15182A,#0B0E14 46%,#080A10) !important;
background-attachment:fixed !important;color:var(--t1)}
__GLASS__
.pg-f{background:linear-gradient(90deg,#7C5CFF,#46E0C8)}</style>""",

"Mercury Mono": """<style>:root{
--bg:#080A0C;--bg2:rgba(8,10,12,.7);
--s1:rgba(255,255,255,.03);--s2:rgba(255,255,255,.055);--s3:rgba(255,255,255,.09);
--r:14px;--t1:#F4F6F8;--t2:#8A929C;--t3:rgba(255,255,255,.32);--t4:rgba(255,255,255,.28);
--accent:#E8EBED;--good:#A9C2B4;--bad:#C9A2A2;--warn:#D6C79A;--info:#A8BBC8;
--glass-edge:rgba(255,255,255,.10);--glass-bd:rgba(255,255,255,.08);
--tab-bar:rgba(255,255,255,.018);--tab-sel:rgba(255,255,255,.05);--tab-hov:rgba(255,255,255,.028);
}[data-testid="stAppViewContainer"]{
background:radial-gradient(ellipse at 50% 0%,#14181C,#080A0C 50%) !important;
background-attachment:fixed !important;color:var(--t1)}
__GLASS__
.pg-f{background:linear-gradient(90deg,#fff,rgba(255,255,255,.45))}</style>""",

"Origin Indigo": """<style>:root{
--bg:#0A0F1E;--bg2:rgba(10,15,30,.7);
--s1:rgba(99,124,255,.05);--s2:rgba(99,124,255,.09);--s3:rgba(99,124,255,.14);
--r:14px;--t1:#EEF1FF;--t2:#8E9AC8;--t3:rgba(180,195,255,.34);--t4:rgba(180,195,255,.3);
--accent:#637CFF;--good:#4FD6B0;--bad:#FF6A8A;--warn:#F1B45A;--info:#637CFF;
--glass-edge:rgba(150,170,255,.12);--glass-bd:rgba(99,124,255,.16);
--tab-bar:rgba(99,124,255,.03);--tab-sel:rgba(99,124,255,.10);--tab-hov:rgba(99,124,255,.05);
}[data-testid="stAppViewContainer"]{
background:radial-gradient(ellipse at 28% 14%,#111A33,#0A0F1E 48%,#070A14) !important;
background-attachment:fixed !important;color:var(--t1)}
__GLASS__
.pg-f{background:linear-gradient(90deg,#637CFF,#9BA9FF)}</style>""",

"Daylight Glass": """<style>:root{
--bg:#FBFBFD;--bg2:rgba(255,255,255,.72);
--s1:rgba(255,255,255,.78);--s2:rgba(255,255,255,.92);--s3:rgba(29,158,117,.08);
--r:14px;--t1:#11141A;--t2:#5A626E;--t3:rgba(0,0,0,.4);--t4:rgba(0,0,0,.32);
--accent:#1D9E75;--good:#1D9E75;--bad:#D8503A;--warn:#C98A1E;--info:#2E6FD6;
--glass-edge:rgba(255,255,255,.9);--glass-bd:rgba(0,0,0,.07);
--tab-bar:rgba(0,0,0,.02);--tab-sel:rgba(29,158,117,.08);--tab-hov:rgba(0,0,0,.03);
}[data-testid="stAppViewContainer"]{
background:radial-gradient(ellipse at 30% 0%,#FFFFFF,#F2F4F8 60%) !important;
background-attachment:fixed !important;color:var(--t1)}
.tile,.kt,.er,.sb,div[data-testid="metric-container"]{
backdrop-filter:blur(30px) saturate(130%) !important;
-webkit-backdrop-filter:blur(30px) saturate(130%) !important;
box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.05) !important;
border:1px solid var(--glass-bd) !important}
.sl,.sb-l,.kl{letter-spacing:.14em !important;font-weight:500 !important}
.pg-f{background:linear-gradient(90deg,#1D9E75,#46C89E)}</style>""",

"Default": """<style>:root{
--bg:#0a0c14;--bg2:rgba(10,12,20,.95);--s1:rgba(255,255,255,.04);--s2:rgba(255,255,255,.06);
--s3:rgba(0,212,170,.08);--r:10px;
--t1:#e0e4f0;--t2:#b0b8d0;--t3:rgba(255,255,255,.35);--t4:rgba(255,255,255,.3);
--accent:#00d4aa;--good:#00d4aa;--bad:#e05c5c;--warn:#ffc832;--info:#508cff;
--tab-bar:rgba(255,255,255,.02);--tab-sel:rgba(0,212,170,.06);--tab-hov:rgba(255,255,255,.03);
}[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--t1)}
.pg-f{background:linear-gradient(90deg,#00d4aa,#508cff)}</style>""",

"Mercury": """<style>:root{
--bg:#0e0e14;--bg2:rgba(16,16,24,.6);--s1:linear-gradient(160deg,rgba(255,255,255,.055),
rgba(255,255,255,.02) 40%,rgba(255,255,255,.04));
--s2:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.035) 40%,rgba(255,255,255,.06));
--s3:linear-gradient(160deg,rgba(255,255,255,.1),rgba(255,255,255,.05) 40%,rgba(255,255,255,.07));
--r:14px;--t1:#f8f8fa;--t2:#d0d0d8;--t3:rgba(255,255,255,.35);--t4:rgba(255,255,255,.4);
--accent:rgba(255,255,255,.85);--good:#a8c0b0;--bad:#c8a0a0;--warn:#d8c890;--info:#a8c0d0;
--tab-bar:rgba(255,255,255,.02);--tab-sel:rgba(255,255,255,.05);--tab-hov:rgba(255,255,255,.03);
}[data-testid="stAppViewContainer"]{
background:radial-gradient(ellipse at 30% 20%,#1c1c28,#0e0e14 40%,#08080c) !important;
background-attachment:fixed !important;color:var(--t1)}
.tile,.kt,.er,.sb,div[data-testid="metric-container"],[data-testid="stTabs"]{
backdrop-filter:blur(30px) saturate(120%) !important;
-webkit-backdrop-filter:blur(30px) saturate(120%) !important;
box-shadow:0 1px 0 rgba(255,255,255,.1) inset,0 6px 24px rgba(0,0,0,.3) !important;
border:1px solid rgba(255,255,255,.08) !important}
.sl,.sb-l,.kl{letter-spacing:.22em !important;font-weight:300 !important}
.pg-f{background:linear-gradient(90deg,#fff,rgba(255,255,255,.5))}</style>""",

"Obsidian": """<style>:root{
--bg:#08080a;--bg2:#0c0c0e;--s1:rgba(255,255,255,.03);--s2:rgba(255,255,255,.05);
--s3:rgba(255,255,255,.07);--r:8px;
--t1:#c8cad0;--t2:#909098;--t3:rgba(255,255,255,.25);--t4:rgba(255,255,255,.2);
--accent:#808890;--good:#70a880;--bad:#b07070;--warn:#b0a060;--info:#7090b0;
--tab-bar:rgba(255,255,255,.015);--tab-sel:rgba(255,255,255,.04);--tab-hov:rgba(255,255,255,.025);
}[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--t1)}
.pg-f{background:#808890}</style>""",

"Vapor": """<style>:root{
--bg:#0a0a18;--bg2:#0e0e1c;--s1:rgba(140,80,255,.06);--s2:rgba(140,80,255,.1);
--s3:rgba(0,255,180,.08);--r:12px;
--t1:#e8e0ff;--t2:#b0a8d0;--t3:rgba(200,180,255,.35);--t4:rgba(200,180,255,.3);
--accent:#00ffb4;--good:#00ffb4;--bad:#ff6090;--warn:#ffcc00;--info:#80b0ff;
--tab-bar:rgba(140,80,255,.04);--tab-sel:rgba(0,255,180,.08);--tab-hov:rgba(140,80,255,.06);
}[data-testid="stAppViewContainer"]{
background:linear-gradient(135deg,#0a0a18,#12081e 50%,#080818) !important;color:var(--t1)}
.pg-f{background:linear-gradient(90deg,#00ffb4,#8050ff)}</style>""",

"Ash": """<style>:root{
--bg:#1a1816;--bg2:#1e1c1a;--s1:rgba(255,240,220,.04);--s2:rgba(255,240,220,.06);
--s3:rgba(220,180,120,.08);--r:10px;
--t1:#e8e0d8;--t2:#b0a898;--t3:rgba(255,240,220,.3);--t4:rgba(255,240,220,.25);
--accent:#d4a870;--good:#90b878;--bad:#c07060;--warn:#d8b850;--info:#80a0c0;
--tab-bar:rgba(255,240,220,.02);--tab-sel:rgba(220,180,120,.08);--tab-hov:rgba(255,240,220,.03);
}[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--t1)}
.pg-f{background:linear-gradient(90deg,#d4a870,#c07850)}</style>""",
}

def apply_theme(name):
    css = _THEME_CSS.get(name, _THEME_CSS["Vapor Glass"])
    css = css.replace("__GLASS__", _GLASS_FX)
    return _BASE_CSS + css

# ── Apply theme ───────────────────────────────────────────────────────────────
_cfg_now = _load_config_json()
_active_theme = _cfg_now.get("theme", "Vapor Glass")
if _active_theme not in THEMES:
    _active_theme = "Vapor Glass"
st.session_state.setdefault("active_theme", _active_theme)
st.markdown(apply_theme(st.session_state["active_theme"]), unsafe_allow_html=True)

# Restore saved parallel-worker count
_saved_w = _cfg_now.get("workers", DEFAULT_WORKERS)
try: _saved_w = min(max(1, int(_saved_w)), MAX_SELECTABLE_WORKERS)
except Exception: _saved_w = DEFAULT_WORKERS
# NOTE: don't pre-seed "cfg_workers" here — it's a WIDGET key (the Settings
# slider), and seeding it while the slider also passes a default triggers the
# "created with a default value but also had its value set via Session State"
# warning on every rerun. The slider's own default (read from _saved_workers)
# covers first render; the widget key persists after that.
st.session_state.setdefault("_saved_workers", _saved_w)
# Table density (comfortable/compact/ultra) — persisted in augur_config.json;
# the control lives in Settings, the Library tables read this session value.
# None-SAFE on purpose: the density segmented-control writes None into its own
# widget key when a pill gets deselected mid-click, and setdefault() does NOT
# replace an existing None — that crashed the next rerun on `None >= 1`.
if st.session_state.get("_lib_density") is None:
    try:
        st.session_state["_lib_density"] = int(_cfg_now.get("ui_density", 1))
    except (TypeError, ValueError):
        st.session_state["_lib_density"] = 1
st.session_state["_lib_compact"] = st.session_state["_lib_density"] >= 1
# Density → table row height (px). Ultra packs ~50% more rows than comfortable.
_DENSITY_RH = {0: 34, 1: 27, 2: 21}
def _lib_rowh():
    _v = st.session_state.get("_lib_density")
    try:
        _v = int(_v)
    except (TypeError, ValueError):
        _v = 1
    return _DENSITY_RH.get(_v, 27)

# ── Session state ─────────────────────────────────────────────────────────────
exec_manager = get_exec_manager()
for _k, _v in [("results_data", None), ("compare_set", set()), ("queue", [])]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# Auto-refresh masters once per session (Tier 1: on app open). Only does work
# for masters the user toggled on; results are stashed for a notification.
# Auto-refresh now runs in a BACKGROUND THREAD — it was blocking first paint for
# ~10-15s (Yahoo pulls + watch-folder ingest) on every app open. The UI paints
# immediately; results surface as a toast on the next rerun after it finishes.
# Module-level dict (not session_state) because the thread has no script context.
_AR_BG = globals().setdefault("_AR_BG_STATE", {"msgs": None, "running": False})
if not st.session_state.get("_autorefresh_ran"):
    st.session_state["_autorefresh_ran"] = True
    _ar_cfg = _get_autorefresh_cfg()
    if _ar_cfg.get("enabled_global") and any(_ar_cfg.get("masters", {}).values()) \
            and not _AR_BG["running"]:
        _AR_BG["running"] = True
        def _ar_bg_worker():
            try:
                _AR_BG["msgs"] = auto_refresh_masters() or []
            except Exception as _are:
                _AR_BG["msgs"] = [f"⚠ Auto-refresh error: {_are}"]
            finally:
                _AR_BG["running"] = False
        # NOTE: deliberately NO script-run-context attach and NO st.* calls inside
        # this thread (auto_refresh_masters now uses the uncached _fetch_yahoo_raw).
        # A bare thread touching Streamlit's cache machinery intermittently
        # deadlocked the session's next script run — widget changes were stored
        # but never triggered reruns (the stuck-Custom-scope / deaf-UI bug).
        threading.Thread(target=_ar_bg_worker, daemon=True,
                         name="augur-autorefresh").start()
# Surface finished background-refresh results (once) on whatever rerun comes next.
if _AR_BG.get("msgs") is not None:
    st.session_state["_autorefresh_results"] = _AR_BG["msgs"]
    _AR_BG["msgs"] = None

import inspect as _inspect
_HAS_FRAG_TIMER = ("run_every" in _inspect.signature(st.fragment).parameters
                   if hasattr(st, "fragment") else False)
_HAS_FRAG_TIMER_SB = _HAS_FRAG_TIMER

# ── Sidebar = Execution Manager (live runs · queue · recent) ──────────────────
active_strat = _get_active_strategy()
hist = load_runs_light()

def _scope_kind(scope):
    """Short, unambiguous badge for a run's scope — so WF, Auto, AI, and grid runs
    are distinguishable at a glance (they used to all read the same in the sidebar)."""
    s = str(scope or "").lower()
    if "walk" in s or "🔁" in str(scope): return "🔁 WF"
    if "evolve" in s or "🧬" in str(scope): return "🧬 Evolve"
    if "ai optimize" in s or "🧠" in str(scope): return "🧠 AI"
    if "auto" in s: return "🤖 Auto"
    if "custom" in s: return "✎ Custom"
    if s.startswith(("short","medium","long","xl","xxl")): return "▦ " + s.split()[0].title()
    return "▦ Grid"


def _sidebar_manager_body():
    """Render active runs, queue, and recent — each run as its own tile."""
    execs = exec_manager.get_all()
    live = [e for e in execs if e["status"] in ("running","paused")]
    q = st.session_state.get("queue", [])

    def _fmt_dur(s):
        s=int(max(0,s))
        return f"{s}s" if s<60 else (f"{s//60}m {s%60}s" if s<3600 else f"{s//3600}h {(s%3600)//60}m")

    # Library cross-reference: source NAME → CSV #, strategy file → master #.
    try:
        _csvnum = {}
        _cm = load_csv_metas()
        if _cm is not None and not _cm.empty:
            for _, _cr in _cm.iterrows():
                for _k in (_cr.get("name"), _cr.get("filename")):
                    if _k and str(_k) != "nan":
                        _csvnum[str(_k).strip()] = int(_cr.get("id", 0) or 0)
    except Exception:
        _csvnum = {}
    def _libdet(strat_name, strat_path, src_name, inst, tf):
        """Detail line with Library #s: '#18 ORB SIMPLE · #26 NQ 5m RTH'."""
        _sn = _strategy_master_num(os.path.basename(strat_path)) if strat_path else 0
        _bits = [(f"#{_sn} " if _sn else "") + (strat_name or "—")]
        _cn = _csvnum.get(str(src_name or "").strip())
        if src_name:
            _bits.append((f"#{_cn} " if _cn else "") + src_name)
        else:
            _bits.append(f"{inst} {tf}".strip())
        return " · ".join(_bits)

    # ── QUICK RUN: one-click re-fire of the last launched config ────────
    _lrc = _get_last_run_cfg()
    if _lrc and _lrc.get("strategy_name"):
        _qr_lbl = (f"{_scope_kind(_lrc.get('scope',''))} · "
                   f"{str(_lrc.get('strategy_name',''))[:16]} · "
                   f"{_lrc.get('instrument','')} {_lrc.get('timeframe','')}")
        if st.button(f"↻ Quick Run", key="sb_quickrun", width="stretch",
                     help=f"Re-run the last config: {_qr_lbl}"):
            _qcfg = dict(_lrc)
            _qdf, _qerr = _load_df_for_config(_qcfg)
            if _qerr or _qdf is None or len(_qdf) < 50:
                st.toast(f"Quick Run failed: {_qerr or 'no data'}")
            else:
                _qeid = str(uuid.uuid4())
                upsert_exec_record(_qeid, _qcfg["name"], _qcfg)
                exec_manager.submit(_qeid, _qcfg, _qdf,
                                    _qcfg.get("multiplier", 1),
                                    _qcfg.get("min_trades", 30))
                st.toast(f"↻ Re-running: {_qcfg['name']}")
                st.rerun()
        st.markdown(f"<div style='font-size:.66rem;opacity:.45;margin:-4px 0 8px;"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
                    f"{_qr_lbl}</div>", unsafe_allow_html=True)

    # ── ACTIVE ─────────────────────────────────────────────────────────
    st.markdown("<div style='font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;"
                "color:var(--t3);margin:2px 0 5px'>Active</div>", unsafe_allow_html=True)
    if live:
        for ex in live:
            total=max(ex.get("total",1),1); prog=ex.get("progress",0)
            pct=min(100,int(prog/total*100)); is_p=ex["status"]=="paused"
            elapsed=time.time()-ex.get("start_ts",time.time())
            eta=_fmt_dur((elapsed/prog)*(total-prog)) if (prog>0 and not is_p) else "—"
            eid=ex["uuid"]
            with st.container(key=f"runtile_{eid}"):
                _mode_lbl = _scope_kind(ex.get("scope",""))
                _det = _libdet(ex.get("strategy_name",""), ex.get("strategy_path",""),
                               ex.get("source_name",""), ex.get("instrument",""),
                               ex.get("timeframe",""))
                _unit = "trials" if str(ex.get("scope","")).lower().startswith("auto") else "combos"
                # Continuous CSS spinner (smooth, browser-native) when running; a
                # paused glyph otherwise. Proof-of-life independent of refresh rate.
                _spin = ("<span class='augur-spin'></span>" if not is_p
                         else "<span style='color:#e0a341'>❙❙</span>")
                try:
                    _started = datetime.fromtimestamp(ex.get("start_ts", time.time())).strftime("%H:%M:%S")
                except Exception:
                    _started = "—"
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:7px;margin-bottom:4px'>"
                    f"<span class='bg {'bg-y' if is_p else 'bg-g'}'>{'PAUSED' if is_p else 'RUNNING'}</span>"
                    f"<span style='font-weight:700;font-size:.76rem;overflow:hidden;text-overflow:ellipsis;"
                    f"white-space:nowrap'>{ex['name']}</span></div>"
                    f"<div style='font-size:.71rem;color:var(--accent);margin-bottom:5px;"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{_mode_lbl} · {_det}</div>"
                    # progress bar, then ALL metrics beneath it
                    f"<div class='pg-t'><div class='pg-f' style='width:{pct}%'></div></div>"
                    f"<div style='font-size:.72rem;opacity:.6;margin:5px 0 2px;font-weight:600'>"
                    f"{prog:,}/{total:,} {_unit} · {pct}% · {ex['n_valid']:,} valid</div>"
                    f"<div style='font-size:.71rem;opacity:.6;margin:0 0 7px'>"
                    f"{_spin} {_fmt_dur(elapsed)} elapsed "
                    f"· ETA {eta} · started {_started}</div>",
                    unsafe_allow_html=True)
                cc1,cc2=st.columns(2)
                if is_p:
                    if cc1.button("▶ Resume",key=f"sb_r_{eid}",width="stretch"):
                        exec_manager.resume(eid); st.rerun()
                else:
                    if cc1.button("❙❙ Pause",key=f"sb_p_{eid}",width="stretch"):
                        exec_manager.pause(eid); st.rerun()
                if cc2.button("■ Stop",key=f"sb_s_{eid}",width="stretch"):
                    exec_manager.stop(eid); st.rerun()
    else:
        st.caption("Nothing running.")

    # ── QUEUE ──────────────────────────────────────────────────────────
    st.markdown(f"<div style='font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;"
                f"color:var(--t3);margin:12px 0 5px'>Queue ({len(q)})</div>",
                unsafe_allow_html=True)
    if q:
        for qi,qc in enumerate(q):
            with st.container(key=f"qtile_{qi}"):
                _qdet = _libdet(qc.get('strategy_name',''), qc.get('strategy_path',''),
                                qc.get('source_name',''), qc.get('instrument',''),
                                qc.get('timeframe',''))
                st.markdown(
                    f"<div style='font-size:.74rem;font-weight:700;margin-bottom:5px'>{qc['name']}"
                    f"<br><span style='opacity:.45;font-weight:400;font-size:.72rem'>"
                    f"{_scope_kind(qc.get('scope',''))} · {_qdet}<br>"
                    f"{qc.get('n_combos',0):,} combos</span></div>",
                    unsafe_allow_html=True)
                qb1,qb2,qb3=st.columns(3)
                if qb1.button("Run",key=f"sbq_run_{qi}",width="stretch"):
                    c2=st.session_state.queue.pop(qi)
                    df2,e2=_load_df_for_config(c2)
                    if not e2 and df2 is not None and len(df2)>=50:
                        eid2=str(uuid.uuid4()); upsert_exec_record(eid2,c2["name"],c2)
                        exec_manager.submit(eid2,c2,df2,c2["multiplier"],c2["min_trades"])
                    st.rerun()
                if qb2.button("Up",key=f"sbq_up_{qi}",width="stretch",disabled=(qi==0)):
                    qq=st.session_state.queue; qq[qi-1],qq[qi]=qq[qi],qq[qi-1]; st.rerun()
                if qb3.button("✕",key=f"sbq_del_{qi}",width="stretch"):
                    st.session_state.queue.pop(qi); st.rerun()
    else:
        st.caption("Queue empty.")

    # (Recent runs render in _sidebar_recent_body below — OUTSIDE the auto-refresh
    #  fragment, so the list no longer flashes every 1.5s during an active run.)


def _sidebar_recent_body():
    """Last 5 completed runs. Rendered OUTSIDE the 1.5s auto-refresh fragment so the
    list stops flashing during a run — completed runs don't change mid-run anyway."""
    st.markdown("<div style='font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;"
                "color:var(--t3);margin:12px 0 5px'>Recent runs</div>", unsafe_allow_html=True)
    _hist = load_runs_light()
    if not _hist.empty:
        for _, rr in _hist.head(5).iterrows():
            _star="⭐ " if rr.get("starred") else ""
            _tk=str(rr.get("instrument","")).split("–")[0].split("(")[0].strip()[:6]
            _tf=str(rr.get("timeframe","")).split("(")[0].strip()[:5]
            _pnl=rr.get("best_pnl_usd",0) or 0
            try: _pf=float(rr.get("best_pf",0) or 0)
            except Exception: _pf=0.0
            _strat=str(rr.get("strategy","") or "—")[:16]
            _col="var(--good)" if _pnl>=0 else "var(--bad)"
            _sk=_scope_kind(rr.get("scope",""))
            st.markdown(
                f"<div style='font-size:.7rem;padding:4px 0;border-bottom:1px solid var(--s1)'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span style='opacity:.7;font-weight:600'>{_star}#{int(rr['id'])} · {_tk} {_tf}</span>"
                f"<span style='color:{_col};font-weight:700'>${_pnl:,.0f}</span></div>"
                f"<div style='display:flex;justify-content:space-between;opacity:.45;margin-top:1px'>"
                f"<span>{_strat}</span><span style='color:var(--accent);opacity:.8'>{_sk}</span>"
                f"<span>PF {_pf:.2f}</span></div></div>",
                unsafe_allow_html=True)
    else:
        st.caption("No runs yet.")

# Self-refresh ONLY the manager (its own fragment) so it never interrupts the
# main page while showing live progress.
_sb_running_now = any(e["status"] in ("running","paused") for e in exec_manager.get_all())
if _HAS_FRAG_TIMER:
    @st.fragment(run_every=("1s" if _sb_running_now else None))
    def _sidebar_manager():
        _sidebar_manager_body()
else:
    def _sidebar_manager():
        _sidebar_manager_body()

with st.sidebar:
    st.markdown(f"<div style='padding:4px 4px 8px;font-weight:800;font-size:1rem;"
                f"letter-spacing:.16em;text-transform:uppercase;"
                f"background:linear-gradient(90deg,var(--accent),var(--info,var(--accent)));"
                f"-webkit-background-clip:text;-webkit-text-fill-color:transparent'>"
                f"🔮 Augur</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:.73rem;opacity:.45;line-height:1.6;"
                f"margin-bottom:10px'>v{__version__} · {len(hist)} runs · "
                f"{exec_manager.get_active_count()} active</div>",
                unsafe_allow_html=True)
    _sidebar_manager()
    _sidebar_recent_body()   # static list, outside the 1.5s fragment → no flashing


# ── Status / Run dock ──────────────────────────────────────────────────────────
_rd = st.session_state.results_data
active_execs = exec_manager.get_all()
running = [e for e in active_execs if e["status"] in ("running","paused")]

# ── Hydrate the Results panel from completed runs (open item #1, Option A) ───────
#    Every completed run — each queued one included — is already saved to the
#    "Past runs" table (newest-first) and stays individually reviewable there.
#    The live panel FOLLOWS the newest completed run by default, BUT the moment
#    the user opens a specific run from Past runs it LOCKS onto that run: a later
#    completion can no longer pull them off the run they're reviewing.  This is
#    what previously broke — the old loop force-overwrote the panel with the most
#    recent run on every rerun, so earlier queued runs were never reviewable live
#    and clicking one snapped you straight back to the latest.
#
#    "Pinned" = the user has an active Past-runs row selection that matches the
#    run currently shown (loaded_from_id).  An auto-loaded history fallback sets
#    loaded_from_id but leaves _hist_sel_ids empty, so it is NOT treated as a pin
#    and the panel will still advance to a freshly-completed run.
_pin_sel = st.session_state.get("_hist_sel_ids") or []
_pin_id  = (_rd or {}).get("meta", {}).get("loaded_from_id")
_user_pinned = bool(_pin_sel) and _pin_id is not None and _pin_id == _pin_sel[-1]
_done_execs = [e for e in active_execs
               if e["status"] == "completed" and e.get("results")]
_newest_done = _done_execs[-1] if _done_execs else None   # newest-submitted
if (not _user_pinned) and _newest_done is not None \
   and (_rd is None or _rd.get("meta", {}).get("exec_uuid") != _newest_done["uuid"]):
    cex = _newest_done
    r = cex["results"]
    try:
        dit = max(1, (r["df_index"][-1] - r["df_index"][0]).days) if r.get("df_index") is not None else 1
    except: dit = 1
    st.session_state.results_data = {
        "res": r["res"], "best": r["best"], "multiplier": r["multiplier"],
        "equity_curves": r["equity_curves"],
        "meta": {"instrument":cex.get("instrument","") or "",
                 "timeframe":cex.get("timeframe","") or "",
                 "data_source":"","scope":cex.get("scope","") or "",
                 "n_combos":cex.get("n_combos",0) or 0,
                 "n_valid":len(r["res"]),"n_bars":0,
                 "date_from":"","date_to":"","days_in_test":dit,
                 "strategy":cex.get("strategy_name","") or cex.get("strategy","") or "",
                 "source_name":cex.get("source_name","") or "",
                 "commission_usd":r.get("commission_usd",0),"slippage_pts":r.get("slippage_pts",0),
                 "price_min":0.0,"price_max":0.0,"exec_uuid":cex["uuid"]},
    }
    _rd = st.session_state.results_data

def _apply_date_filter(df, cfg):
    """Slice an OHLCV frame to the config's [date_from, date_to] window (inclusive,
    by calendar date). No-op when neither bound is set or the frame is empty.
    Lets the user backtest a sub-range of a deep 16yr master without re-exporting."""
    if df is None or df.empty:
        return df
    d0 = cfg.get("date_from"); d1 = cfg.get("date_to")
    if not d0 and not d1:
        return df
    try:
        idx = df.index
        if getattr(idx, "tz", None) is None:
            idx = idx.tz_localize("UTC")
        et = idx.tz_convert("US/Eastern")
        dts = et.normalize().date
        import datetime as _dt
        mask = np.ones(len(df), dtype=bool)
        if d0:
            lo = _dt.date.fromisoformat(str(d0))
            mask &= np.array([d >= lo for d in dts])
        if d1:
            hi = _dt.date.fromisoformat(str(d1))
            mask &= np.array([d <= hi for d in dts])
        return df[mask]
    except Exception:
        return df


@st.cache_data(show_spinner=False, max_entries=6)
def _parse_master_cached(path: str, mtime: float):
    """Parse a stored CSV once per (path, mtime). Masters are 300k+ rows and were
    re-parsed synchronously on EVERY Run click — the multi-second freeze right
    after hitting Run. mtime in the key auto-invalidates when a master refreshes."""
    with open(path, "rb") as fh:
        class _F:
            def __init__(s, b): s._b = b
            def read(s): return s._b
            def seek(s, p): pass
        return parse_tv_csv(_F(fh.read()))


def _load_df_for_config(cfg):
    if cfg["data_source"] == "Yahoo":
        df, err = fetch_yahoo(cfg["ticker"], cfg["tf_cfg"]["interval"], cfg["tf_cfg"]["period"])
    else:
        lib_path = cfg.get("_csv_lib_path")
        if lib_path and os.path.exists(lib_path):
            try:
                df, err = _parse_master_cached(lib_path, os.path.getmtime(lib_path))
            except Exception:
                with open(lib_path, "rb") as fh:
                    class _F:
                        def __init__(s, b): s._b = b
                        def read(s): return s._b
                        def seek(s, p): pass
                    df, err = parse_tv_csv(_F(fh.read()))
        elif cfg.get("_csv_file") is not None:
            df, err = parse_tv_csv(cfg["_csv_file"])
        else:
            return None, "No CSV file available."
    if df is not None and not err:
        df = _apply_date_filter(df, cfg)
    return df, err


# ── Auto-run queue: ONLY chain to the next run after one finishes — never
#    launch from a cold idle (so queuing while nothing runs does NOT start it).
#    We "arm" auto-run while a run is active; when it later goes idle with the
#    arm set and a queue waiting, we launch the next one and re-arm.
if running:
    st.session_state["_autorun_armed"] = True
    st.session_state["_autorun_last"] = None
elif st.session_state.get("_autorun_armed") and st.session_state.get("queue"):
    _head = st.session_state.queue[0]
    _head_sig = f"{id(_head)}:{_head.get('name','')}"
    if st.session_state.get("_autorun_last") != _head_sig:
        st.session_state["_autorun_last"] = _head_sig
        _next = st.session_state.queue.pop(0)
        _dfn, _en = _load_df_for_config(_next)
        if not _en and _dfn is not None and len(_dfn) >= 50:
            _eidn = str(uuid.uuid4())
            upsert_exec_record(_eidn, _next["name"], _next)
            exec_manager.submit(_eidn, _next, _dfn, _next["multiplier"], _next["min_trades"])
            st.toast(f"Auto-started: {_next['name']}")
        else:
            st.toast(f"Skipped '{_next['name']}': {_en or 'insufficient data'}")
        try: st.rerun(scope="app")
        except TypeError: st.rerun()
elif not st.session_state.get("queue"):
    # Queue drained — disarm so a future manually-started run is needed to re-arm.
    st.session_state["_autorun_armed"] = False

# Minimal watcher: only active while a run is going AND a queue is waiting, so
# the moment the run finishes we rerun the app and the auto-run block above
# launches the next queued run. Off entirely when there's no queue (no churn).
if _HAS_FRAG_TIMER and running and st.session_state.get("queue"):
    @st.fragment(run_every="1.5s")
    def _autorun_watcher():
        _act = [e for e in exec_manager.get_all() if e["status"] in ("running","paused")]
        if not _act:  # run finished — kick the app so the next queued run starts
            try: st.rerun(scope="app")
            except TypeError: st.rerun()
    _autorun_watcher()

# (Run dock removed — the live execution manager lives in the sidebar, which
#  self-refreshes as its own fragment so it never interrupts the main page.)


# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════
# ── Top app-bar: logo (left) + live context strip (right), overlaid ON the
#    tab row via CSS so the header costs zero vertical space. The context strip
#    answers "what am I set up to run / what just happened / is anything going"
#    without leaving whatever tab you're on.
_ab_hist = load_runs_light()
_ctx_bits = []
try:
    _cs_path = get_strategy_registry().get("current_path", "") or ""
    if active_strat is not None and _cs_path:
        _cs_num = _strategy_master_num(os.path.basename(_cs_path))
        _cs_nm = str(getattr(active_strat, "STRATEGY_NAME", "?"))[:24]
        _ctx_bits.append(f"<span><span class='acc'>#{_cs_num}</span> <b>{_cs_nm}</b></span>")
except Exception:
    pass
try:
    if not _ab_hist.empty:
        _lr0 = _ab_hist.iloc[0]
        _lr_pnl = float(_lr0.get("best_pnl_usd", 0) or 0)
        _lr_col = "ok" if _lr_pnl >= 0 else ""
        _ctx_bits.append(
            f"<span>last #{int(_lr0['id'])} {_scope_kind(_lr0.get('scope',''))} · "
            f"<b class='{_lr_col}'>${_lr_pnl:,.0f}</b> · PF {float(_lr0.get('best_pf',0) or 0):.2f}</span>")
except Exception:
    pass
try:
    _n_act = exec_manager.get_active_count()
    _ctx_bits.append(f"<span class='ok'>▶ {_n_act} running</span>" if _n_act
                     else "<span>idle</span>")
except Exception:
    pass
# (Main-page logo removed — it lives in the sidebar. Only the context strip
#  overlays the tab row, so the tabs align flush-left with the tiles below.)
st.markdown(
    f"<div class='ctxstrip'>{''.join(_ctx_bits)}</div>",
    unsafe_allow_html=True)

# Auto-refresh notification: a brief toast that auto-dismisses, NOT a banner that
# sits pinned at the top of the page taking vertical space.
_arr = st.session_state.pop("_autorefresh_results", None)
if _arr:
    _added = [r for r in _arr if r.startswith("✓")]
    _warns = [r for r in _arr if not r.startswith("✓")]
    if _added:
        try:
            st.toast(f"Auto-refresh updated {len(_added)} master"
                     f"{'' if len(_added) == 1 else 's'} on open", icon="🔄")
        except Exception:
            pass
    for w in _warns:
        try:
            st.toast(str(w)[:140])
        except Exception:
            pass

# key= makes the active tab persist across full app reruns (Streamlit ≥1.34).
# Without it, firing a run (which calls st.rerun()) snapped the view back to the
# first tab (LIBRARY) every time — the "glitchy after firing" the user reported.
# Apply any pending navigation/setup BEFORE the tab + scope widgets instantiate
# (widget keys can only be written before their widget renders). Set by the
# roadmap's "▶ set up" buttons to jump to Executions with the right scope ready.
if (_pt := st.session_state.pop("_pending_tab", None)):
    st.session_state["augur_main_tabs"] = _pt
    # st.tabs ignores programmatic session-state writes, so ALSO click the tab
    # button on the frontend (zero-height component, runs once on this render).
    try:
        import streamlit.components.v1 as _stc
        _stc.html(f"""<script>
          const want = {_pt.strip()!r};
          const t = [...window.parent.document.querySelectorAll('button[role="tab"]')]
                    .find(b => b.textContent.trim() === want);
          if (t) t.click();
        </script>""", height=0)
    except Exception:
        pass
if (_ps := st.session_state.pop("_pending_scope", None)):
    st.session_state["_scope_tier_committed"] = _ps
    st.session_state["ex_scope_seg"] = _ps
if (_pn := st.session_state.pop("_pending_trials", None)):
    st.session_state["_ntrials_committed"] = int(_pn)

# default= lands new sessions on RESULTS (what you check most); the key keeps
# whatever tab you switch to sticky across reruns within the session.
tab_lib, tab_exec, tab_results, tab_cmp, tab_ref, tab_research, tab_set = st.tabs([
    "◫  LIBRARY", "▶  EXECUTIONS", "◎  RESULTS",
    "⇄  COMPARE", "❖  REFERENCE", "◈  RESEARCH", "▦  SETTINGS",
], key="augur_main_tabs", default="◎  RESULTS")
tab_upload = tab_lib  # uploads now live inside Library
tab_hist = tab_results  # history merged into Results



# ══════════════════════════════════════════════════════════════════════════════
#  NULL-SAFE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _n(r, k, d=0):
    v = r.get(k) if hasattr(r,'get') else None
    return d if v is None else v
def _s(r, k, d="?"):
    v = r.get(k) if hasattr(r,'get') else None
    return d if (v is None or v == "") else v
PARAM_COLS = ["lookback_len","min_red_dominance","min_breakout_pts",
              "max_body_ratio","prev_body_lookback","rr_input","be_bars"]

def _hint(text: str) -> str:
    """Inline hover ⓘ — tuck an explanation behind an icon instead of a caption."""
    _t = str(text).replace("'", "&#39;").replace('"', "&quot;")
    return f"<span class='ihint' title='{_t}'>i</span>"


def _fmt_date(ts):
    """Convert timestamp string to 'MON 26 MAY '26 · 14:30' (military time)."""
    try:
        from datetime import datetime as _dt
        if isinstance(ts, str):
            dt = _dt.fromisoformat(ts.replace(" ","T")[:19])
        else:
            dt = ts
        return dt.strftime("%a %d %b '%y · %H:%M").upper()
    except:
        return str(ts)[:16]

def _quick_load_run(row):
    try:
        res_loaded = pd.read_json(StringIO(_decompress(row["full_results"])))
        ec_loaded = []
        if row.get("equity_curves_json"):
            for c in json.loads(_decompress(row["equity_curves_json"])):
                ec_loaded.append({
                    "rank": c["rank"], "label": c["label"],
                    "timestamps": [pd.Timestamp(t) for t in c["timestamps"]],
                    "cum_pnl_usd": c["cum_pnl_usd"], "final_pnl": c["final_pnl"],
                })
        st.session_state.results_data = {
            "res": res_loaded,
            "best": (res_loaded.iloc[-1] if "fold" in res_loaded.columns
                     else res_loaded.iloc[0]).to_dict(),
            "multiplier": float(_n(row,"multiplier",1) or 1),
            "equity_curves": ec_loaded,
            "meta": {
                "instrument": _s(row,"instrument"), "timeframe": _s(row,"timeframe"),
                "data_source": _s(row,"data_source"), "scope": _s(row,"scope"),
                "n_combos": int(_n(row,"n_combos")), "n_valid": int(_n(row,"n_valid")),
                "n_bars": int(_n(row,"bars")), "date_from": _s(row,"date_from"),
                "date_to": _s(row,"date_to"),
                "days_in_test": int(_n(row,"days_in_test",1)),
                "strategy": _s(row,"strategy"),
                "source_name": _s(row,"source_name"),
                "commission_usd": _n(row,"commission_usd",0), "slippage_pts": _n(row,"slippage_pts",0),
                "price_min": 0.0, "price_max": 0.0,
                "loaded_from_id": int(row["id"]),
            },
        }
        return True
    except Exception as ex:
        st.error(f"Could not load: {ex}")
        return False


def _rd_from_run_row(row):
    """Build a results_data dict from a DB run row (or None if no full results)."""
    if not row.get("full_results"):
        return None
    res = pd.read_json(StringIO(_decompress(row["full_results"])))
    ec = []
    if row.get("equity_curves_json"):
        for c in json.loads(_decompress(row["equity_curves_json"])):
            ec.append({"rank": c["rank"], "label": c["label"],
                       "timestamps": [pd.Timestamp(t) for t in c["timestamps"]],
                       "cum_pnl_usd": c["cum_pnl_usd"], "final_pnl": c["final_pnl"]})
    return {
        "res": res,
        "best": (res.iloc[-1] if "fold" in res.columns else res.iloc[0]).to_dict(),
        "multiplier": float(row.get("multiplier") or 1), "equity_curves": ec,
        "meta": {"instrument": row.get("instrument") or "",
                 "timeframe": row.get("timeframe") or "",
                 "data_source": row.get("data_source") or "",
                 "scope": row.get("scope") or "",
                 "n_combos": int(row.get("n_combos") or 0),
                 "n_valid": int(row.get("n_valid") or len(res)),
                 "n_bars": int(row.get("bars") or 0),
                 "date_from": row.get("date_from") or "",
                 "date_to": row.get("date_to") or "",
                 "days_in_test": int(row.get("days_in_test") or 1),
                 "strategy": row.get("strategy") or "",
                 "source_name": row.get("source_name") or "",
                 "commission_usd": row.get("commission_usd") or 0, "slippage_pts": row.get("slippage_pts") or 0,
                 "loaded_from_id": int(row["id"])},
    }


def _build_report_html(_rd):
    """Build a self-contained HTML report (KPIs + top-10 + all charts) from a
    results_data dict. Returns the HTML string."""
    res  = _rd["res"]; best = pd.Series(_rd["best"]); meta = _rd["meta"]
    ec   = _rd.get("equity_curves", [])
    METRIC_COLS = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                   "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd",
                   "oos_pnl","oos_trades","oos_pf","oos_pnl_usd","fold","test_bars"}
    param_cols = [c for c in res.columns if c not in METRIC_COLS]
    num_param_cols = [c for c in param_cols
                      if pd.api.types.is_numeric_dtype(res[c]) and res[c].nunique() > 1]
    days = meta.get("days_in_test",1) or 1; ppd = best["pnl_usd"]/days
    bg = "#0a0c14"
    figs = []

    if ec:
        fe = go.Figure()
        for i,c in enumerate(ec):
            fe.add_trace(go.Scatter(x=c["timestamps"],y=c["cum_pnl_usd"],mode="lines",
                name=c["label"],line=dict(width=3 if i==0 else 1.5,
                color="#00d4aa" if i==0 else None)))
        fe.add_hline(y=0,line_dash="dot",line_color="#222")
        fe.update_layout(template="plotly_dark",paper_bgcolor=bg,plot_bgcolor=bg,
                         height=380,margin=dict(t=30));figs.append(("Equity",fe))
    fd = px.histogram(res.head(2000),x="pnl_usd",nbins=60,
        color_discrete_sequence=["#00d4aa"]); fd.add_vline(x=best["pnl_usd"],
        line_dash="dash",line_color="gold")
    fd.update_layout(template="plotly_dark",paper_bgcolor=bg,plot_bgcolor=bg,
        showlegend=False,height=260,margin=dict(t=30),title="PNL Distribution")
    figs.append(("Distribution",fd))
    if num_param_cols:
        cv = res[num_param_cols+["pnl_usd"]].corr()["pnl_usd"].drop("pnl_usd").sort_values()
        fc = go.Figure(go.Bar(x=cv.values,y=cv.index,orientation="h",
            marker_color=["#c07070" if v<0 else "#70b080" for v in cv.values],
            text=[f"{v:+.3f}" for v in cv.values],textposition="outside"))
        fc.update_layout(template="plotly_dark",paper_bgcolor=bg,plot_bgcolor=bg,
            xaxis=dict(range=[-1,1]),height=max(220,40*len(cv)),margin=dict(t=30),
            title="Correlation with PNL");figs.append(("Correlations",fc))
        pcc = res.head(500).copy()
        dimc = num_param_cols+[c for c in ["win_rate","pnl_usd"] if c in pcc.columns]
        fp = go.Figure(go.Parcoords(line=dict(color=pcc["pnl_usd"],colorscale="RdYlGn",
            showscale=True,colorbar=dict(x=1.06,thickness=12,len=0.9)),
            dimensions=[dict(label=c[:10],values=pcc[c]) for c in dimc]))
        fp.update_layout(template="plotly_dark",paper_bgcolor=bg,height=470,
            margin=dict(t=70,l=80,r=110,b=55));figs.append(("Parallel",fp))

    top_cols = param_cols + [c for c in ["pnl_usd","win_rate","profit_factor",
               "num_trades","dd_usd"] if c in res.columns]
    rn = {"pnl_usd":"PNL $","win_rate":"Win%","profit_factor":"PF",
          "num_trades":"Trades","dd_usd":"MaxDD $"}
    top10_html = res[top_cols].head(10).rename(columns=rn).to_html(
        index=False,border=0,float_format=lambda x:f"{x:,.2f}")
    ts2 = datetime.now().strftime("%Y%m%d_%H%M")
    kpi = (f"<div class='kpis'>"
           f"<div class='k'><span>Total PNL</span><b>${best['pnl_usd']:,.0f}</b></div>"
           f"<div class='k'><span>PNL/Day</span><b>${ppd:,.0f}</b></div>"
           f"<div class='k'><span>Win Rate</span><b>{best['win_rate']:.1f}%</b></div>"
           f"<div class='k'><span>Profit Factor</span><b>{best['profit_factor']:.2f}</b></div>"
           f"<div class='k'><span>Trades</span><b>{int(best['num_trades'])}</b></div>"
           f"<div class='k'><span>Max DD</span><b>${best.get('dd_usd',0):,.0f}</b></div></div>")
    parts=["<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Augur report</title>",
        "<style>body{background:#0a0c14;color:#d4d8e8;font-family:system-ui;"
        "padding:24px;max-width:1400px;margin:0 auto}h2{color:#cdd9e5;margin-top:28px}"
        ".kpis{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.k{border:1px solid "
        "#1a2040;border-radius:10px;padding:10px 16px;min-width:110px}.k span{display:block;"
        "font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;opacity:.5}"
        ".k b{font-size:1.3rem;color:#fff}table{border-collapse:collapse;width:100%;"
        "margin-top:8px;font-size:.82rem}th,td{border:1px solid #1a2040;padding:6px 10px;"
        "text-align:right}th{background:#13162a;color:#9aa3c0}tr:first-child td{color:#00d4aa;"
        "font-weight:700}</style></head><body>",
        f"<h1 style='color:#00d4aa'>Augur v{__version__} — Run #{meta.get('loaded_from_id','')}</h1>",
        f"<div style='opacity:.5;font-size:.85rem'>{meta.get('instrument','')} · "
        f"{meta.get('date_from','')} → {meta.get('date_to','')} · "
        f"{meta.get('n_valid',len(res)):,} valid combos</div>",
        kpi, "<h2>Top 10 Parameter Sets</h2>", top10_html]
    for i2,(t3,f3) in enumerate(figs):
        parts.append(f"<h2>{t3}</h2>")
        parts.append(f3.to_html(include_plotlyjs="cdn" if i2==0 else False,full_html=False))
    parts.append("</body></html>")
    return "\n".join(parts)


def _build_run_bundle(_rd, code_snap=""):
    """ONE ZIP with everything a run can give you — the HTML report (KPIs + top-10 +
    all charts), the full results CSV, the top-10 CSV, and the exact strategy .py —
    so a single download replaces the separate report / CSV / top-10 / code buttons."""
    import io as _io, zipfile as _zip
    res = _rd["res"]
    _buf = _io.BytesIO()
    with _zip.ZipFile(_buf, "w", _zip.ZIP_DEFLATED) as _z:
        try: _z.writestr("report.html", _build_report_html(_rd))
        except Exception: pass
        try: _z.writestr("all_results.csv", res.to_csv(index=False))
        except Exception: pass
        try: _z.writestr("top10.csv", res.head(10).to_csv(index=False))
        except Exception: pass
        if code_snap and str(code_snap).strip():
            _z.writestr("strategy.py", str(code_snap))
    return _buf.getvalue()


def _build_config(*, run_name, inst_name, tf_name, data_source, scope,
                  custom_grid, ticker, tf_cfg, multiplier, min_trades, sel_strat,
                  csv_lib_path=None, csv_file_obj=None, csv_src_name="",
                  opt_mode="grid", n_trials=0, auto_oos=True, auto_oos_method="single",
                  wf_folds=0, commission_usd=0.0, slippage_pts=0.0,
                  date_from=None, date_to=None):
    grid = custom_grid or {}
    if not grid:
        strat = _get_active_strategy()
        if strat and hasattr(strat, "PARAM_GRID_PRESETS"):
            grid = next(iter(strat.PARAM_GRID_PRESETS.values()), {})
        else:
            grid = next(iter(SCOPE_GRIDS.values()), {})
    _strat = _get_active_strategy()
    _dp = getattr(_strat, "DEFAULT_PARAMS", None) if _strat else None
    # Capture the EXACT strategy file active at build time, so a run uses the
    # strategy it was launched with — even if the user switches strategies in
    # the UI while it's queued or running. (Fixes auto-optimize using the wrong
    # strategy / identical results across strategies.)
    try:
        _strat_path = get_strategy_registry().get("current_path", "") or ""
    except Exception:
        _strat_path = ""
    if opt_mode == "auto":
        n = int(n_trials)
        _scope_lbl = "Auto"
    else:
        n = _count_effective_combos(grid, _dp) if grid else 0
        _scope_lbl = scope.split("(")[0].strip().split()[0] if scope else "Run"
    _src_label = csv_src_name if (data_source == "CSV" and csv_src_name) else (
                 ticker if data_source == "Yahoo" else "")
    return {
        "name": run_name or f"{inst_name.split()[0]} {_scope_lbl}",
        "instrument": inst_name, "timeframe": tf_name,
        "data_source": data_source, "source_name": _src_label,
        "scope": ("🔁 Walk-Forward" if (opt_mode=="auto" and auto_oos_method=="walkforward")
                  else "Auto-Optimize" if opt_mode=="auto" else scope),
        "strategy_name": sel_strat, "strategy_path": _strat_path, "grid": grid, "n_combos": n,
        "opt_mode": opt_mode, "n_trials": int(n_trials),
        "oos_on": bool(auto_oos), "oos_method": auto_oos_method, "wf_folds": int(wf_folds),
        "commission_usd": float(commission_usd), "slippage_pts": float(slippage_pts),
        "n_workers": int(st.session_state.get("cfg_workers", DEFAULT_WORKERS)),
        "ticker": ticker, "tf_cfg": tf_cfg, "multiplier": multiplier,
        "min_trades": min_trades, "_csv_lib_path": csv_lib_path,
        "_csv_file": csv_file_obj,
        "date_from": (str(date_from) if date_from else None),
        "date_to":   (str(date_to) if date_to else None),
    }



# ══════════════════════════════════════════════════════════════════════════════
#  TAB: LIBRARY
# ══════════════════════════════════════════════════════════════════════════════
with tab_lib:
    # Auto-fix orphan files
    try:
        for fn in os.listdir(STRATEGIES_DIR):
            fp = os.path.join(STRATEGIES_DIR, fn)
            if os.path.isfile(fp) and not fn.endswith(".py") and "_py" in fn:
                nfn = fn.replace("_py", ".py", 1)
                np2 = os.path.join(STRATEGIES_DIR, nfn)
                if not os.path.exists(np2):
                    os.rename(fp, np2)
    except: pass

    if saved_fn := st.session_state.pop("_plugin_just_saved", None):
        st.toast(f"Saved: {saved_fn}")

    # Table density plumbing (the "compact" toggle itself lives in the Strategies
    # caption row — putting a widget here wedged blank space between the main tab
    # bar and the subtabs). Both Library tables read the shared session value.
    _LIB_CAP = 30                               # rows shown before the table scrolls
    import inspect as _insp_df
    _DF_ROWH_OK = "row_height" in _insp_df.signature(st.dataframe).parameters

    lib_s, lib_c = st.tabs(["STRATEGIES", "CSV DATA"])

    # ─────────────────────── STRATEGIES ───────────────────────
    with lib_s:
        sf_list = _list_strategy_files()
        if not sf_list:
            st.caption("No strategies yet. Add one below.")
        else:
            # ── Sort: ACTIVE first, then most-recently-RUN, then the rest ──
            #    (was market-grouped; the Market column keeps that context and the
            #     table headers are click-sortable if you want a different order)
            def _mkt_key(s):
                _i = (s.get("instrument") or "").strip(); _t = (s.get("timeframe") or "").strip()
                return f"{_i} · {_t}" if (_i or _t) else "~Untagged"
            _act_path0 = get_strategy_registry().get("current_path", "")
            _last_used = {}
            try:
                _hl = load_runs_light()      # id DESC → first hit per name = latest
                if _hl is not None and not _hl.empty:
                    for _nm, _ts in zip(_hl["strategy"], _hl["timestamp"]):
                        _nm = str(_nm or "").strip()
                        if _nm and _nm not in _last_used:
                            _last_used[_nm] = str(_ts or "")
            except Exception:
                pass
            sf_list.sort(key=lambda s: s.get("name", ""))                       # tertiary
            sf_list.sort(key=lambda s: _last_used.get(str(s.get("name","")).strip(), ""),
                         reverse=True)                                           # recency
            sf_list.sort(key=lambda s: s["path"] != _act_path0)                  # active 1st
            st.caption("Sorted by last used (active strategy pinned on top). Market "
                       "column shows each strategy's catalogued instrument · timeframe — "
                       "set it with EDIT; column headers sort. Row density: Settings tab.")
            _LIB_RH = _lib_rowh()

            # ── Consolidated action bar: select a strategy below, then act on it here ──
            _sel = st.session_state.get("_lib_sel_strat")
            _sel_sf = next((s for s in sf_list if s["file"] == _sel), None)
            with st.container(key="lib_strat_actionbar"):
                if _sel_sf is None:
                    st.caption("▸ Select a strategy below to activate, edit, download "
                               "or delete it.")
                else:
                    _is_act = (_sel_sf["path"] == get_strategy_registry().get("current_path", ""))
                    ab0, ab1, ab2, ab3, ab4, ab5 = st.columns([5.4, 1.5, 1.2, 1.0, 1.3, 1.0])
                    ab0.markdown(
                        f"<div style='font-weight:800;padding-top:7px'>"
                        f"<span style='color:var(--accent)'>▸</span> {_sel_sf['name']}"
                        f"<span style='opacity:.5;font-size:.72rem;font-weight:600;"
                        f"margin-left:8px'>{_sel_sf['file']}</span></div>",
                        unsafe_allow_html=True)
                    if _is_act:
                        ab1.button("✓ Active", key="lab_act", width="stretch",
                                   disabled=True)
                    else:
                        if ab1.button("○ Activate", key="lab_act", width="stretch"):
                            ok, msg = _set_active_strategy(_sel_sf["path"])
                            if ok: _save_strategy_config_json(); st.rerun()
                            else: st.error(msg)
                    if ab2.button("EDIT", key="lab_edit", width="stretch"):
                        _ek = f"_sc_{_sel_sf['file']}"
                        st.session_state[_ek] = not st.session_state.get(_ek, False)
                        st.rerun()
                    try:
                        ab3.download_button("PY", data=open(_sel_sf["path"], encoding="utf-8").read(),
                                            file_name=_sel_sf["file"], mime="text/x-python",
                                            width="stretch", key="lab_py", help="Download .py")
                    except: pass
                    try:
                        ab4.download_button("Pine", data=_strategy_pine(_sel_sf),
                                            file_name=os.path.splitext(_sel_sf["file"])[0] + ".pine",
                                            mime="text/plain", width="stretch",
                                            key="lab_pine", help="Download Pine Script")
                    except: pass
                    if ab5.button("DEL", key="lab_del", width="stretch"):
                        st.session_state[f"_del_{_sel_sf['file']}"] = True
                        st.rerun()

            # Per-strategy validation roadmap — the idea→deploy checklist, with the
            # steps the run history already satisfies ticked automatically.
            if _sel_sf is not None:
                with st.expander(f"✓ Validation roadmap — #{_strategy_master_num(_sel_sf['file'])} "
                                 f"{_sel_sf['name']}", expanded=False):
                    st.caption("The path from idea to deploy. Steps marked “found in run "
                               "history” tick automatically as you run them; the rest are "
                               "yours to check off. Saved per strategy.")
                    _render_validation_roadmap(_sel_sf["file"], _sel_sf["name"], kp="lib_",
                                               parent_file=_sel_sf.get("parent"))

            # ── Strategies TABLE (one tile, row-click selects) ──────────────
            # Replaces the per-strategy tiles: ~35px/row vs ~80px/tile. Click a
            # row to select it (Streamlit highlights it); the toolbar above acts
            # on the selection. Column headers are click-sortable.
            _act_path = get_strategy_registry().get("current_path", "")
            _rows_tbl = []
            for sf in sf_list:
                _mk = _mkt_key(sf)
                _rows_tbl.append({
                    "\u25cf": "\u2713" if sf["path"] == _act_path else "",
                    "#": _strategy_master_num(sf["file"]),
                    "Name": sf["name"],
                    "Market": "" if _mk == "~Untagged" else _mk,
                    "Ver": str(sf.get("version", "?")),
                    "Added": sf.get("added", "?"),
                    "Note": (("superseded \u2192 " + str(sf["superseded"])) if sf.get("superseded") else ""),
                    "Description": (sf.get("desc", "") or "")[:90],
                    "File": sf["file"],
                })
            _sdf_tbl = pd.DataFrame(_rows_tbl)
            _tbl_h = 40 + min(len(_sdf_tbl), _LIB_CAP) * _LIB_RH
            _df_kw = {"row_height": _LIB_RH} if _DF_ROWH_OK else {}
            _tsel = st.dataframe(
                _sdf_tbl, hide_index=True, height=_tbl_h, width="stretch",
                on_select="rerun", selection_mode="single-row",
                key="lib_strat_table", **_df_kw,
                column_config={
                    "\u25cf": st.column_config.TextColumn("\u25cf", width="small",
                                                     help="\u2713 = active strategy"),
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Name": st.column_config.TextColumn("Name", width="large"),
                    "Description": st.column_config.TextColumn("Description", width="large"),
                })
            _trows = (_tsel.get("selection", {}).get("rows", [])
                      if isinstance(_tsel, dict) else [])
            if _trows and _trows[0] < len(sf_list):
                _newf = sf_list[_trows[0]]["file"]
                if _newf != _sel:
                    st.session_state["_lib_sel_strat"] = _newf
                    st.rerun()

            # ── Selected-strategy panels (delete confirm \u00b7 edit) ─────────────
            if _sel_sf is not None:
                sf = _sel_sf
                is_active = (sf["path"] == _act_path)
                if st.session_state.get(f"_del_{sf['file']}"):
                    dc1, dc2, dc3 = st.columns([3, 1, 1])
                    dc1.markdown(f"<span style='color:var(--bad);font-size:.8rem;"
                                 f"padding-top:6px;display:inline-block'>"
                                 f"Delete <b>{sf['name']}</b>? This cannot be undone.</span>",
                                 unsafe_allow_html=True)
                    if dc2.button("\u2713 Delete", key=f"dy_{sf['file']}", width="stretch"):
                        os.remove(sf["path"])
                        if is_active:
                            reg = get_strategy_registry(); reg["current_path"]=None; reg["current_module"]=None
                        st.session_state.pop(f"_del_{sf['file']}", None)
                        st.session_state["_lib_sel_strat"] = None
                        st.rerun()
                    if dc3.button("\u2715 Cancel", key=f"dn_{sf['file']}", width="stretch"):
                        st.session_state.pop(f"_del_{sf['file']}", None)
                        st.rerun()

                if st.session_state.get(f"_sc_{sf['file']}"):
                    rn1, rn2 = st.columns([4,1])
                    rn_key = f"rn_{sf['file']}_{sf['name']}"
                    new_nm = rn1.text_input("Strategy name", value=sf["name"], key=rn_key)
                    if rn2.button("Rename", key=f"rb_{sf['file']}",
                                  width="stretch"):
                        ok, msg = _rename_strategy(sf["path"], new_nm)
                        if ok:
                            reg = get_strategy_registry()
                            reg["current_module"] = None
                            if reg.get("current_path") == sf["path"]:
                                _set_active_strategy(sf["path"])
                            st.session_state[f"_sc_{sf['file']}"] = False
                            for k in list(st.session_state.keys()):
                                if k.startswith(f"rn_{sf['file']}"):
                                    del st.session_state[k]
                            st.toast(f"Renamed to {new_nm} \u00b7 {msg}")
                            st.rerun()
                        else:
                            st.error(msg)
                    mk1, mk2 = st.columns(2)
                    _insts = [""] + list(INSTRUMENTS.keys())
                    _ci = sf.get("instrument") or ""
                    _mi = mk1.selectbox("Market \u00b7 Instrument", _insts,
                            index=_insts.index(_ci) if _ci in _insts else 0,
                            key=f"mki_{sf['file']}")
                    _tfo = [""] + TIMEFRAME_TAGS
                    _ct = sf.get("timeframe") or ""
                    _mt = mk2.selectbox("Market \u00b7 Timeframe", _tfo,
                            index=_tfo.index(_ct) if _ct in _tfo else 0,
                            key=f"mktf_{sf['file']}")
                    if st.button("\u25c6 Tag market", key=f"mkb_{sf['file']}"):
                        ok, msg = _set_strategy_market(sf["path"], _mi, _mt)
                        if ok:
                            reg = get_strategy_registry(); reg["current_module"] = None
                            if reg.get("current_path") == sf["path"]:
                                _set_active_strategy(sf["path"])
                            st.session_state[f"_sc_{sf['file']}"] = False
                            st.toast(f"Tagged {_mi or '?'} {_mt}"); st.rerun()
                        else:
                            st.error(msg)
                    try:
                        sc = open(sf["path"], encoding="utf-8").read()
                        edited = st.text_area("Code", value=sc, height=240,
                                              key=f"le_{sf['file']}",
                                              label_visibility="collapsed")
                        if st.button("Save code", key=f"ls_{sf['file']}"):
                            import tempfile as _tf
                            with _tf.NamedTemporaryFile(suffix=".py", delete=False,
                                                         mode="w", encoding="utf-8") as tmp:
                                tmp.write(edited); tp = tmp.name
                            m2, e2 = _load_strategy_module(tp); os.unlink(tp)
                            if e2: st.error(f"Invalid: {e2}")
                            else:
                                with open(sf["path"],"w",encoding="utf-8") as fh: fh.write(edited)
                                if is_active:
                                    reg = get_strategy_registry(); reg["current_module"]=None
                                    _set_active_strategy(sf["path"])
                                st.session_state[f"_sc_{sf['file']}"] = False
                                st.session_state["_plugin_just_saved"] = sf["file"]
                                st.rerun()
                    except Exception as ex: st.error(str(ex))


        # ── Add strategy ──
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        with st.expander("+  Add Strategy"):
            ast1, ast2 = st.tabs(["Upload .py", "Translate Pine Script"])
            with ast1:
                up_file=st.file_uploader("Choose .py",type=["py"],key="up_py")
                up_name=st.text_input("Name (optional)",key="up_name",placeholder="my_strategy")
                if up_file and st.button("Save",key="up_save",type="primary"):
                    import tempfile as _tf5
                    fname=(up_name.strip() or up_file.name.replace(".py",""))
                    stem="".join(c if c.isalnum() or c in "_-" else "_" for c in fname)
                    fname=stem+".py"
                    code=up_file.read().decode("utf-8")
                    with _tf5.NamedTemporaryFile(suffix=".py",delete=False,mode="w",encoding="utf-8") as tmp:
                        tmp.write(code); tp=tmp.name
                    m3,e3=_load_strategy_module(tp); os.unlink(tp)
                    if e3: st.error(f"Invalid: {e3}")
                    else:
                        with open(os.path.join(STRATEGIES_DIR,fname),"w",encoding="utf-8") as fh: fh.write(code)
                        st.session_state["_plugin_just_saved"]=fname; st.rerun()
            with ast2:
                pine=st.text_area("Pine Script",height=160,key="up_pine",placeholder="//@version=6...")
                uc1,uc2=st.columns(2)
                api_k=uc1.text_input("API key",type="password",key="up_api",help="Not stored")
                tname=uc2.text_input("Name",key="up_tname",placeholder="EMA Cross")
                if st.button("Translate",key="up_trans"):
                    if not pine.strip(): st.warning("Paste code first")
                    elif not api_k.strip(): st.warning("Enter API key")
                    elif not tname.strip(): st.warning("Enter name")
                    else:
                        with st.spinner("Translating..."): code2,err2=translate_pine_to_python(pine,api_k)
                        if err2: st.error(err2)
                        else: st.session_state["_tc"]=code2; st.session_state["_tn"]=tname; st.success("Done!")
                if st.session_state.get("_tc"):
                    edited2=st.text_area("Review",value=st.session_state["_tc"],height=240,key="up_rev")
                    st.session_state["_tc"]=edited2
                    if st.button("Save translated",key="up_tsave",type="primary"):
                        import tempfile as _tf6
                        stem2="".join(c if c.isalnum() or c in "_-" else "_" for c in st.session_state["_tn"])
                        fn2=stem2+".py"
                        with _tf6.NamedTemporaryFile(suffix=".py",delete=False,mode="w",encoding="utf-8") as tmp:
                            tmp.write(edited2);tp2=tmp.name
                        m4,e4=_load_strategy_module(tp2);os.unlink(tp2)
                        if e4: st.error(e4)
                        else:
                            with open(os.path.join(STRATEGIES_DIR,fn2),"w",encoding="utf-8") as fh: fh.write(edited2)
                            st.session_state.pop("_tc",None); st.session_state.pop("_tn",None)
                            st.session_state["_plugin_just_saved"]=fn2; st.rerun()

    # ─────────────────────── CSV DATA ───────────────────────
    with lib_c:
        cm2=load_csv_metas()
        _masters_all = cm2[cm2["is_master"].fillna(0).astype(int)==1] if (not cm2.empty and "is_master" in cm2.columns) else cm2.iloc[0:0]
        _plain = cm2[cm2["is_master"].fillna(0).astype(int)==0] if (not cm2.empty and "is_master" in cm2.columns) else cm2

        # ── Recommendation nudge: suggest building masters where useful ──
        _recs = recommend_masters(cm2, _masters_all)
        if _recs:
            _rec_bits = ", ".join(f"<b>{r['instrument']} {r['timeframe']}</b> "
                                  f"({r['n_csvs']} files)" for r in _recs[:4])
            st.markdown(
                f"<div style='background:var(--s3);border:1px solid var(--glass-bd);"
                f"border-radius:12px;padding:10px 14px;margin-bottom:10px'>"
                f"<span style='font-size:.85rem'>💡 <b>Tip:</b> you have multiple "
                f"CSVs that could be combined into a master for: {_rec_bits}. "
                f"Use <b>⧉ Combine into Master CSV</b> below to stitch them into one "
                f"continuous, extendable history.</span></div>",
                unsafe_allow_html=True)

        # ── Consolidated action bar: select a CSV below, then act on it here ──
        _csv_sel = st.session_state.get("_lib_sel_csv")
        _sel_cr = None
        if _csv_sel is not None and not cm2.empty:
            _m = cm2[cm2["id"] == _csv_sel]
            if not _m.empty:
                _sel_cr = _m.iloc[0]
        if not cm2.empty:
            with st.container(key="lib_csv_actionbar"):
                if _sel_cr is None:
                    st.caption("▸ Select a CSV below to edit, download or delete it.")
                else:
                    cb0, cb1, cb2, cb3 = st.columns([6.5, 1.3, 1.0, 1.0])
                    cb0.markdown(
                        f"<div style='font-weight:800;padding-top:7px'>"
                        f"<span style='color:var(--accent)'>▸</span> #{int(_sel_cr['id'])} "
                        f"{_sel_cr['name']}"
                        f"<span style='opacity:.5;font-size:.72rem;font-weight:600;"
                        f"margin-left:8px'>{int(_sel_cr['rows']):,} rows</span></div>",
                        unsafe_allow_html=True)
                    if cb1.button("EDIT", key="cab_edit", width="stretch"):
                        _ek = f"_ce_{_sel_cr['id']}"
                        st.session_state[_ek] = not st.session_state.get(_ek, False)
                        st.rerun()
                    try:
                        _fp = os.path.join(CSV_DIR, _sel_cr["filename"])
                        if os.path.exists(_fp):
                            with open(_fp, "rb") as _fh:
                                cb2.download_button("⬇ CSV", _fh.read(), _sel_cr["filename"],
                                                    "text/csv", width="stretch",
                                                    key="cab_dl", help="Download CSV")
                    except: pass
                    if cb3.button("DEL", key="cab_del", width="stretch"):
                        st.session_state[f"_cdel_{_sel_cr['id']}"] = True
                        st.rerun()

        # ── Reusable CSV tile renderer ───────────────────────────────────
        def _render_csv_tile_extras(cr):
            # Confirm delete
            if st.session_state.get(f"_cdel_{cr['id']}"):
                d1,d2,d3 = st.columns([3,1,1])
                d1.markdown(f"<span style='color:var(--bad);font-size:.8rem;"
                            f"padding-top:6px;display:inline-block'>"
                            f"Delete <b>{cr['name']}</b>?</span>",
                            unsafe_allow_html=True)
                if d2.button("✓ Delete",key=f"cdy_{cr['id']}",width="stretch"):
                    delete_csv_meta(cr["id"])
                    st.session_state.pop(f"_cdel_{cr['id']}",None); st.rerun()
                if d3.button("✕ Cancel",key=f"cdn_{cr['id']}",width="stretch"):
                    st.session_state.pop(f"_cdel_{cr['id']}",None); st.rerun()
            if st.session_state.get(f"_ce_{cr['id']}"):
                e1,e2,e3,e4 = st.columns([3,2,2,1])
                nn = e1.text_input("Name", value=cr["name"], key=f"cn_{cr['id']}_{cr['name']}")
                ni = e2.selectbox("Instrument", list(INSTRUMENTS.keys()),
                                  index=list(INSTRUMENTS.keys()).index(cr["instrument"])
                                  if cr.get("instrument") in INSTRUMENTS else 0,
                                  key=f"ci_{cr['id']}")
                _cur_tf = cr.get("timeframe") or _detect_timeframe(cr.get("name","")) or "5m"
                _tfi = TIMEFRAME_TAGS.index(_cur_tf) if _cur_tf in TIMEFRAME_TAGS else TIMEFRAME_TAGS.index("5m")
                nt = e3.selectbox("Timeframe", TIMEFRAME_TAGS, index=_tfi, key=f"ctf_{cr['id']}")
                if e4.button("Save", key=f"cs_{cr['id']}", width="stretch"):
                    update_csv_meta(cr["id"], name=nn, instrument=ni, timeframe=nt)
                    st.session_state[f"_ce_{cr['id']}"]=False
                    st.toast("Updated"); st.rerun()

        # ── CSV TABLE (one tile, row-click selects) ──────────────────────
        # Masters first, then imported CSVs. Click a row to select; the toolbar
        # above acts on it. Column headers are click-sortable.
        if not cm2.empty:
            _csv_disp = []          # parallel list of row dicts + id order
            _csv_ids  = []
            def _type_label(cr):
                if int(cr.get("is_master", 0) or 0) != 1:
                    return ""
                _sess = str(cr.get("session", "") or "").lower()
                _lbl = "\u25c6 MASTER\u00b7" + ("RTH" if _sess == "rth" else "ETH")
                try:
                    _csrc = str(cr.get("source", "tv") or "tv")
                    _ar = _get_autorefresh_cfg()
                    _on = bool(_ar.get("masters", {}).get(
                        _ar_key(str(cr.get("instrument", "")).strip(),
                                str(cr.get("timeframe", "")).strip(), _csrc), False))
                    _ysup = _yahoo_interval_for(str(cr.get("timeframe", "")).strip()) is not None
                    _lbl += "  \u27f3" if (_on and _ysup) else "  \u23f8"
                except Exception:
                    pass
                return _lbl
            _ordered = pd.concat([_masters_all, _plain]) if not _masters_all.empty else cm2
            for _, cr in _ordered.iterrows():
                _is_m = int(cr.get("is_master", 0) or 0) == 1
                _inm = ""
                if not _is_m and not _masters_all.empty:
                    try:
                        _cov = _csv_in_master(cr, _masters_all)
                        if _cov and _cov[0]:
                            _inm = "\u2713 in master" if _cov[2] else "\u2248 likely in master"
                    except Exception:
                        _inm = ""
                _csv_disp.append({
                    "#": int(cr["id"]),
                    "Type": _type_label(cr),
                    "Name": str(cr.get("name", "") or ""),
                    "Inst": str(cr.get("instrument", "") or ""),
                    "TF": str(cr.get("timeframe", "") or ""),
                    "Rows": int(cr.get("rows", 0) or 0),
                    "From": str(cr.get("date_from", "") or ""),
                    "To": str(cr.get("date_to", "") or ""),
                    "In master": _inm,
                    "Added": _fmt_date(cr["created_at"]) if cr.get("created_at") else "?",
                })
                _csv_ids.append(int(cr["id"]))
            _cdf_tbl = pd.DataFrame(_csv_disp)
            _rh_c = _lib_rowh()
            _ctbl_h = 40 + min(len(_cdf_tbl), _LIB_CAP) * _rh_c
            _cdf_kw = {"row_height": _rh_c} if _DF_ROWH_OK else {}
            _csel_tbl = st.dataframe(
                _cdf_tbl, hide_index=True, height=_ctbl_h, width="stretch",
                on_select="rerun", selection_mode="single-row",
                key="lib_csv_table", **_cdf_kw,
                column_config={
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Name": st.column_config.TextColumn("Name", width="large"),
                    "Rows": st.column_config.NumberColumn("Rows", format="%d"),
                })
            _crows = (_csel_tbl.get("selection", {}).get("rows", [])
                      if isinstance(_csel_tbl, dict) else [])
            if _crows and _crows[0] < len(_csv_ids):
                _newid = _csv_ids[_crows[0]]
                if _newid != _csv_sel:
                    st.session_state["_lib_sel_csv"] = _newid
                    st.rerun()
            # Selected-CSV panels (delete confirm \u00b7 edit) render once, below.
            if _sel_cr is not None:
                _render_csv_tile_extras(_sel_cr)

        if cm2.empty:
            st.caption("No CSVs saved yet. Add one below.")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        with st.expander("+  Add CSV"):
            csv_up=st.file_uploader("TradingView export CSV",type=["csv"],key="up_csv")
            csv_name=st.text_input("Name",key="up_csv_name",placeholder="ES 5m Jan-May")
            ucsv1, ucsv2 = st.columns(2)
            csv_inst=ucsv1.selectbox("Instrument",list(INSTRUMENTS.keys()),key="up_csv_inst")
            # Auto-detect timeframe: the DATA's bar spacing is authoritative; fall
            # back to the name/filename. Sub-minute charts (5s/10s) often have no
            # unit in the filename, so sniffing the data is the reliable path.
            _auto_tf = ""
            if csv_up is not None:
                try:
                    _sk = f"_tfsniff_{getattr(csv_up,'name','')}_{getattr(csv_up,'size',0)}"
                    if _sk in st.session_state:
                        _auto_tf = st.session_state[_sk]
                    else:
                        _sniff_df, _ = parse_tv_csv(csv_up); csv_up.seek(0)
                        _auto_tf = _infer_tf_from_df(_sniff_df) if _sniff_df is not None else ""
                        st.session_state[_sk] = _auto_tf
                except Exception:
                    _auto_tf = ""
            _auto_tf = _auto_tf or _detect_timeframe(csv_name) or (_detect_timeframe(csv_up.name) if csv_up else "")
            _tf_idx = TIMEFRAME_TAGS.index(_auto_tf) if _auto_tf in TIMEFRAME_TAGS else TIMEFRAME_TAGS.index("5m")
            csv_tf=ucsv2.selectbox("Timeframe",TIMEFRAME_TAGS,index=_tf_idx,key="up_csv_tf",
                                   help="Auto-detected from the data's bar spacing (then the "
                                        "name) — adjust if wrong. Masters are kept separately "
                                        "per instrument + timeframe.")
            if csv_up and st.button("Save CSV",key="up_csv_save",type="primary"):
                try:
                    raw=csv_up.read(); csv_up.seek(0)
                    fn3=f"csv_{uuid.uuid4().hex[:8]}.csv"
                    with open(os.path.join(CSV_DIR,fn3),"wb") as fh: fh.write(raw)
                    df_tmp,_=parse_tv_csv(csv_up); csv_up.seek(0)
                    if df_tmp is not None:
                        save_csv_meta(csv_name or fn3,fn3,csv_inst,len(df_tmp),
                                      str(df_tmp.index[0])[:10],str(df_tmp.index[-1])[:10],
                                      timeframe=csv_tf)
                        # Look up the id just assigned to this CSV
                        _newid = None
                        try:
                            _cc = _db_conn()
                            _rr = _cc.execute("SELECT id FROM csv_files WHERE filename=? LIMIT 1",
                                              (fn3,)).fetchone()
                            _newid = _rr[0] if _rr else None
                            _cc.close()
                        except Exception:
                            _newid = None
                        # AUTO-master: append to the matching TV master, or CREATE one
                        # if none exists yet. Works for sub-minute charts too — the TF
                        # was sniffed from the data's bar spacing above.
                        _msg = "Saved!"
                        try:
                            _m = find_master(csv_inst, csv_tf, "tv")
                            if _m:
                                _mdf, _ = _read_stored_csv(_m["filename"])
                                if _mdf is not None:
                                    _merged, _info = combine_ohlcv_frames(
                                        [_mdf, df_tmp], csv_tf,
                                        labels=["tv-existing", "tv-import"])
                                    _ids = []
                                    try:
                                        _pj = json.loads(_m.get("provenance", "") or "{}")
                                        _ids.extend(int(x) for x in _pj.get("source_csv_ids", []))
                                    except Exception:
                                        pass
                                    if _newid is not None:
                                        _ids.append(int(_newid))
                                    _prov = _build_provenance(_info, "tv",
                                        [f"existing master ({len(_mdf):,})",
                                         f"{csv_name or fn3} ({len(df_tmp):,})"],
                                        source_csv_ids=sorted(set(_ids)))
                                    save_master_csv(_merged, _m["name"], csv_inst, csv_tf,
                                        source="tv", provenance=_prov,
                                        overwrite_filename=_m["filename"])
                                    _msg = (f"Saved + extended master '{_m['name']}' "
                                            f"→ {_info['total_rows']:,} rows")
                            else:
                                _mname = f"{csv_inst} {csv_tf} master (TV)"
                                _prov = _build_provenance(
                                    {"total_rows": len(df_tmp),
                                     "date_from": str(df_tmp.index[0]),
                                     "date_to": str(df_tmp.index[-1]), "n_gaps": 0}, "tv",
                                    [f"{csv_name or fn3} ({len(df_tmp):,})"],
                                    source_csv_ids=[int(_newid)] if _newid is not None else [])
                                save_master_csv(df_tmp, _mname, csv_inst, csv_tf,
                                    source="tv", provenance=_prov)
                                _msg = f"Saved + created master '{_mname}' ({len(df_tmp):,} rows)"
                        except Exception:
                            pass
                        st.toast(_msg); st.rerun()
                except Exception as ex: st.error(str(ex))

            # One-tap: add the just-uploaded CSV into its matching master
            _off = st.session_state.get("_offer_master")
            if _off:
                st.success(f"📦 A master exists for {_off['instrument']} @ "
                           f"{_off['timeframe']}: **{_off['master']['name']}**.")
                oc1, oc2 = st.columns(2)
                if oc1.button(f"➕ Add to master", key="off_add",
                              type="primary", width="stretch"):
                    mdf, merr = _read_stored_csv(_off["master"]["filename"])
                    ndf, nerr = _read_stored_csv(_off["csv_filename"])
                    if mdf is not None and ndf is not None:
                        merged, info = combine_ohlcv_frames(
                            [mdf, ndf], _off["timeframe"],
                            labels=["tv-existing","tv-import"])
                        # Carry forward the master's prior ids + this new CSV id
                        _ids = []
                        try:
                            _pj = json.loads(_off["master"].get("provenance","") or "{}")
                            _ids.extend(int(x) for x in _pj.get("source_csv_ids", []))
                        except Exception:
                            pass
                        if _off.get("csv_id") is not None:
                            _ids.append(int(_off["csv_id"]))
                        prov = _build_provenance(info, "tv",
                            [f"existing master ({len(mdf):,})",
                             f"{_off['csv_name']} ({len(ndf):,})"],
                            source_csv_ids=sorted(set(_ids)))
                        ok,_r = save_master_csv(merged, _off["master"]["name"],
                            _off["instrument"], _off["timeframe"], source="tv",
                            provenance=prov,
                            overwrite_filename=_off["master"]["filename"])
                        if ok:
                            st.session_state.pop("_offer_master", None)
                            st.toast(f"Master extended → {info['total_rows']:,} rows "
                                     f"({info['n_gaps']} gaps)")
                            st.rerun()
                        else:
                            st.error(f"Failed: {_r}")
                    else:
                        st.error(merr or nerr or "Could not read files.")
                if oc2.button("Not now", key="off_skip", width="stretch"):
                    st.session_state.pop("_offer_master", None); st.rerun()

        # ── Combine CSVs into a master ──────────────────────────────────
        with st.expander("⧉  Combine into Master CSV"):
            st.caption("Merge several CSVs of the SAME instrument + timeframe into one "
                       "continuous file. Overlaps are de-duplicated; gaps split the data "
                       "into segments. Masters are kept SEPARATE by source "
                       "(TradingView vs Yahoo) so you can extend and compare each.")
            cm3 = load_csv_metas()
            if cm3.empty:
                st.caption("Add some CSVs first.")
            else:
                mcol1, mcol2, mcol3 = st.columns(3)
                _insts = sorted({str(r.get("instrument","")).strip()
                                 for _,r in cm3.iterrows() if str(r.get("instrument","")).strip()})
                m_inst = mcol1.selectbox("Instrument", _insts or list(INSTRUMENTS.keys()),
                                         key="mrg_inst")
                _sub = cm3[cm3["instrument"].astype(str).str.strip()==m_inst]
                _tfs = sorted({str(r.get("timeframe","")).strip()
                               for _,r in _sub.iterrows()
                               if str(r.get("timeframe","")).strip()
                               and str(r.get("timeframe","")).strip().lower()!="nan"})
                m_tf = mcol2.selectbox("Timeframe", _tfs or ["5m"], key="mrg_tf")
                m_src = mcol3.selectbox("Master source", ["TradingView","Yahoo"],
                    key="mrg_src",
                    help="TradingView = built from your imported CSVs. "
                         "Yahoo = pulled from Yahoo Finance. Kept separate so you "
                         "can compare data quality between the two.")
                _src_key = "tv" if m_src == "TradingView" else "yahoo"

                # Does a master already exist for this instrument+timeframe+source?
                _existing = find_master(m_inst, m_tf, _src_key)
                if _existing:
                    st.info(f"📦 Existing {m_src} master: **{_existing['name']}** "
                            f"({int(_existing['rows']):,} rows · "
                            f"{_existing['date_from']}→{_existing['date_to']}). "
                            f"New data will EXTEND it.")

                frames_info = []   # (label, df)
                _errs = []

                if _src_key == "tv":
                    # TradingView master: built from imported (non-master) CSVs
                    _match = _sub[(_sub["timeframe"].astype(str).str.strip()==m_tf)]
                    _match = _match[_match.get("is_master",0).fillna(0).astype(int)==0] \
                             if "is_master" in _match.columns else _match
                    if _match.empty and not _existing:
                        st.caption(f"No TradingView CSVs for {m_inst} @ {m_tf}.")
                    else:
                        _opts = {f"{r['name']} ({r['rows']:,} rows · {r['date_from']}→{r['date_to']})": r
                                 for _,r in _match.iterrows()}
                        picks = st.multiselect("CSVs to combine", list(_opts.keys()),
                                               default=list(_opts.keys()), key="mrg_picks")
                        for k in picks:
                            frames_info.append(("import:"+_opts[k]["name"][:20], _opts[k]))
                else:
                    # Yahoo master: pulled from Yahoo Finance
                    _def_tk = INSTRUMENTS.get(m_inst,{}).get("ticker","") if isinstance(INSTRUMENTS.get(m_inst),dict) else ""
                    yh_ticker = st.text_input("Yahoo ticker", value=_def_tk,
                        key="mrg_yh_tk", placeholder="ES=F",
                        help="e.g. ES=F for S&P futures, AAPL for Apple.")
                    st.caption("Yahoo intraday history is limited (~7d for 1–5m, "
                               "~60d for 15–60m). Re-pull periodically to extend the master.")

                m_name = st.text_input("Master name", key="mrg_name",
                    value=(_existing["name"] if _existing
                           else f"{m_inst.split()[0]} {m_tf} MASTER · {m_src}"))

                cprev, csave = st.columns(2)
                _verb = "Extend & Save" if _existing else "Build & Save"
                if cprev.button("Preview", key="mrg_prev", width="stretch"):
                    st.session_state["_mrg_do"] = "preview"
                if csave.button(_verb, key="mrg_save", type="primary",
                                width="stretch"):
                    st.session_state["_mrg_do"] = "save"

                _do = st.session_state.pop("_mrg_do", None)
                if _do:
                    frames = []; labels = []; parts = []; _src_ids = []
                    # If extending, start from the existing master's data and
                    # carry forward any CSV ids it already recorded.
                    if _existing:
                        edf, eerr = _read_stored_csv(_existing["filename"])
                        if edf is not None:
                            frames.append(edf); labels.append(_src_key+"-existing")
                            parts.append(f"existing master ({len(edf):,} rows)")
                            try:
                                _pj = json.loads(_existing.get("provenance","") or "{}")
                                _src_ids.extend(int(x) for x in _pj.get("source_csv_ids", []))
                            except Exception:
                                pass
                        else:
                            _errs.append(f"Existing master: {eerr}")
                    # TradingView: add picked CSVs (and record their ids)
                    if _src_key == "tv":
                        for lbl, r in frames_info:
                            dfx, ex = _read_stored_csv(r["filename"])
                            if dfx is not None:
                                frames.append(dfx); labels.append("tv-import")
                                parts.append(f"{r['name']} ({r['rows']:,} rows)")
                                if r.get("id") is not None:
                                    _src_ids.append(int(r["id"]))
                            else: _errs.append(f"{r['name']}: {ex}")
                    # Yahoo: pull
                    else:
                        _tk = st.session_state.get("mrg_yh_tk","").strip()
                        if _tk:
                            _iv_map = {"1m":"1m","2m":"2m","5m":"5m","15m":"15m","30m":"30m",
                                       "1h":"60m","1D":"1d","1W":"1wk"}
                            _iv = _iv_map.get(m_tf, "5m")
                            _per = "7d" if _iv in ("1m","2m","5m") else ("60d" if _iv in ("15m","30m","60m") else "2y")
                            with st.spinner(f"Pulling {_tk} from Yahoo…"):
                                ydf, yerr = fetch_yahoo(_tk, _iv, _per)
                            if ydf is not None:
                                if ydf.index.tz is None:
                                    ydf.index = ydf.index.tz_localize("UTC")
                                frames.append(ydf); labels.append("yahoo")
                                parts.append(f"Yahoo {_tk} ({len(ydf):,} rows)")
                            else:
                                _errs.append(f"Yahoo: {yerr}")
                        else:
                            _errs.append("Enter a Yahoo ticker first.")

                    for e in _errs: st.warning(e)

                    if frames:
                        merged, info = combine_ohlcv_frames(frames, m_tf, labels=labels)
                        if merged is None:
                            st.error(info.get("error","Nothing to combine."))
                        else:
                            seg = info["largest_segment"]
                            st.markdown(
                                f"**{info['total_rows']:,} rows** total · "
                                f"{info['date_from'][:16]} → {info['date_to'][:16]}  \n"
                                f"**{info['n_gaps']} gap(s)** → "
                                f"**{len(info['segments'])} segment(s)**")
                            # Source breakdown
                            _sc = info.get("source_counts", {})
                            if _sc:
                                _bd = " · ".join(f"{k}: {v:,}" for k,v in _sc.items())
                                st.caption(f"By source → {_bd}")
                            if info["n_gaps"] > 0:
                                for s0,s1,sr in info["segments"][:8]:
                                    st.caption(f"   • {str(s0)[:16]} → {str(s1)[:16]}  ({sr:,} rows)")
                                st.info(f"Largest continuous block: {seg[2]:,} rows "
                                        f"({str(seg[0])[:10]} → {str(seg[1])[:10]}).")
                            if _do == "save":
                                prov = _build_provenance(info, _src_key, parts,
                                                         source_csv_ids=sorted(set(_src_ids)))
                                ok, res = save_master_csv(
                                    merged, m_name, m_inst, m_tf, source=_src_key,
                                    provenance=prov,
                                    overwrite_filename=(_existing["filename"] if _existing else None))
                                if ok:
                                    _act = "Extended" if _existing else "Saved"
                                    st.success(f"{_act} {m_src} master '{m_name}' "
                                               f"→ {info['total_rows']:,} rows.")
                                    st.rerun()
                                else:
                                    st.error(f"Save failed: {res}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: EXECUTIONS
# ══════════════════════════════════════════════════════════════════════════════
# NOTE: deliberately NOT @st.fragment anymore. Fragment-scoped reruns of this
# tab desynced the frontend widget registry on this Streamlit build: the FIRST
# widget change after a full run fired fine, but the next change (e.g. switching
# Scope away from Custom) never reached the server — the dropdown changed "in
# name only" while the old scope's UI stayed. Verified via server-side render
# logging: the second change produced no rerun at all. Full reruns are cheap now
# (master-parse cache, DB micro-caches), so correctness wins.
def _exec_tab_fragment():
    """Executions tab body as a FRAGMENT (perf): widget changes here (instrument,
    timeframe, CSV, scope, trials, costs) rerun ONLY this block instead of the
    whole ~8k-line script - removes the repeated grey-out lag after hitting Run,
    especially while a backtest worker is competing for the CPU. Run/Queue still
    st.rerun() the full app on purpose so the sidebar dock sees the new run."""
    global active_strat
    active_strat = _get_active_strategy()

    # ══ TILE 1 · DATA + STRATEGY (consolidated to two compact rows) ══════
    _date_from = None; _date_to = None
    with st.container(key="tilebox_source"):
        st.markdown("<div class='tile-h'>Data &amp; Strategy</div>", unsafe_allow_html=True)
        data_source = "CSV"   # data always comes from the CSV picker
        csv_file = None; _csv_lib_path = None; _csv_src_name = ""
        inst_list = list(INSTRUMENTS.keys())

        # ── ONE row: Instrument · Timeframe · Strategy · CSV · Date range ──
        # (single horizontal flow — pick left to right, hit Run below)
        cA1, cA2, cA3, cB1, cB2 = st.columns([0.8, 0.7, 1.7, 1.7, 1.1])
        inst_name = cA1.selectbox("Instrument", inst_list, key="ex_inst_c")
        ic = INSTRUMENTS[inst_name]
        multiplier = ic.get("multiplier", 1)
        ticker = "CSV"; tf_cfg = {"interval": "csv"}
        cm = load_csv_metas(); cm_all = cm.copy()
        if not cm.empty and inst_name != "Custom":
            cm = cm[cm["instrument"].astype(str).str.strip() == inst_name]
        if not cm.empty and "timeframe" in cm.columns:
            _tfs = sorted({str(t).strip() for t in cm["timeframe"].tolist()
                           if str(t).strip() and str(t).strip().lower() != "nan"})
        else:
            _tfs = []
        tf_options = ["All"] + _tfs
        tf_name = cA2.selectbox("Timeframe", tf_options, key="ex_csv_tf")
        # Strategy picker (activates immediately — no need to visit Library)
        sf_list2 = _list_strategy_files()
        reg = get_strategy_registry(); apath = reg.get("current_path", "")
        if sf_list2:
            sd = [s["name"] for s in sf_list2]
            active_idx = next((i for i, s in enumerate(sf_list2) if s["path"] == apath), 0)
            si = cA3.selectbox("Strategy", range(len(sf_list2)), index=active_idx,
                               format_func=lambda i: f"#{_strategy_master_num(sf_list2[i]['file'])} · {sd[i]}")
            sinfo = sf_list2[si]; sel_strat = sinfo["name"]
            if sinfo["path"] != apath or not active_strat:
                ok, _ = _set_active_strategy(sinfo["path"])
                if ok:
                    _save_strategy_config_json()
                    active_strat = _get_active_strategy()
                    st.rerun()
        else:
            sel_strat = "None"; cA3.warning("No strategies — add one in Library")
        if inst_name == "Custom":
            multiplier = cA1.number_input("$/pt", 50, min_value=1, key="ex_cm2")

        # ── Row B:  CSV file · Date range ──
        cm_tf = cm
        if tf_name != "All" and not cm.empty and "timeframe" in cm.columns:
            cm_tf = cm[cm["timeframe"].astype(str).str.strip() == tf_name]
        if not cm_tf.empty:
            csv_opts = ["Select..."] + [
                f"#{int(r['id'])} · {r['name']} · {str(r.get('timeframe','') or '?')} ({r['rows']:,} rows)"
                for _, r in cm_tf.iterrows()]
        elif not cm_all.empty:
            _why = f"instrument '{inst_name}'" + ("" if tf_name == "All" else f" + {tf_name}")
            csv_opts = [f"No CSVs match {_why} — tag one in Library"]
        else:
            csv_opts = ["No CSVs — upload in Library tab"]
        csv_sel = cB1.selectbox("CSV file", csv_opts, key="ex_csv")
        _csv_src_name = ""; _sel_row = None
        if (csv_sel != "Select..." and not cm_tf.empty
                and not csv_sel.startswith("No CSVs")):
            idx3 = csv_opts.index(csv_sel) - 1
            if 0 <= idx3 < len(cm_tf):
                row3 = cm_tf.iloc[idx3]; _sel_row = row3
                _csv_lib_path = os.path.join(CSV_DIR, row3["filename"])
                tf_name = str(row3.get("timeframe", "") or "CSV")   # use the file's TF
                _csv_src_name = str(row3.get("name", "") or "")
        # Date-range slice — only when a CSV with a parseable span is selected. The
        # widget key is tied to the CSV id so switching files resets to full span
        # (a stale range from another file would be out of this file's min/max).
        if _sel_row is not None:
            import datetime as _dt
            def _pdate(v):
                try: return _dt.date.fromisoformat(str(v)[:10])
                except Exception: return None
            _lo = _pdate(_sel_row.get("date_from")); _hi = _pdate(_sel_row.get("date_to"))
            if _lo and _hi and _lo < _hi:
                # Short label, NO help icon — the ? icon forced the label to wrap
                # in this narrow column, knocking the widget out of row alignment.
                _dr = cB2.date_input("Date range", value=(_lo, _hi),
                                     min_value=_lo, max_value=_hi,
                                     key=f"ex_dr_{int(_sel_row.get('id', 0))}")
                if isinstance(_dr, (tuple, list)) and len(_dr) == 2 and _dr[0] and _dr[1]:
                    _d0, _d1 = _dr
                    _date_from = _d0.isoformat() if _d0 > _lo else None
                    _date_to   = _d1.isoformat() if _d1 < _hi else None
                    if _date_from or _date_to:
                        cB2.caption(f"▸ {_d0.isoformat()} → {_d1.isoformat()} · "
                                    f"{(_d1 - _d0).days:,} of {(_hi - _lo).days:,} days")
            else:
                cB2.markdown("<div style='opacity:.4;font-size:.72rem;padding-top:26px'>"
                             "full file</div>", unsafe_allow_html=True)
        else:
            cB2.markdown("<div style='opacity:.4;font-size:.72rem;padding-top:26px'>"
                         "pick a CSV → date range</div>", unsafe_allow_html=True)

    # ══ TILE 3 · SCOPE ═══════════════════════════════════════════════════
    with st.container(key="tilebox_scope"):
        st.markdown("<div class='tile-h'>Scope</div>", unsafe_allow_html=True)
        sg = active_strat.PARAM_GRID_PRESETS if active_strat and hasattr(active_strat,"PARAM_GRID_PRESETS") else SCOPE_GRIDS
        _preset_labels = list(sg.keys())
        # Normalize each preset to a stable tier key (first word: SHORT/MEDIUM/
        # LONG/XL/XXL) so the chosen scope SURVIVES switching strategies even
        # when the descriptive suffix differs between strategies
        # (e.g. "Medium (balanced)" vs "Medium (~1,458 combos)"). Without this,
        # the persisted label isn't found in the new strategy's options and the
        # selectbox silently resets to the first preset — which looked like the
        # grid reverting to "Short" while the label still read your pick.
        def _tier_of(lbl):
            return lbl.strip().split()[0].upper() if lbl.strip() else lbl
        _tier_to_label = {}
        for lbl in _preset_labels:
            _tier_to_label.setdefault(_tier_of(lbl), lbl)
        # Build option list = stable tiers + special scopes
        _CUSTOM = "CUSTOM"
        _AUTO_LABEL = "🤖 AUTO-OPTIMIZE"
        _WF_LABEL = "🔁 WALK-FORWARD"
        _AI_OPT_LABEL = "🧠 AI OPTIMIZE"
        _AI_EVO_LABEL = "🧬 AI EVOLVE"
        # Drop any preset whose normalized tier collides with a special scope — a
        # strategy preset literally named "Custom" was making the Scope dropdown
        # show "CUSTOM" twice. The special scopes below are the canonical ones.
        for _st in (_CUSTOM, _AUTO_LABEL, _WF_LABEL, _AI_OPT_LABEL, _AI_EVO_LABEL):
            _tier_to_label.pop(_st, None)
        _tier_opts = list(_tier_to_label.keys())
        _scope_opts = _tier_opts + [_CUSTOM, _AUTO_LABEL, _WF_LABEL, _AI_OPT_LABEL, _AI_EVO_LABEL]

        # Friendly display: show the strategy's full descriptive label for tiers,
        # numbered 1..N in dropdown order so scopes are easy to reference.
        def _fmt_scope(opt):
            _i   = (_scope_opts.index(opt) + 1) if opt in _scope_opts else 0
            _pre = f"{_i}. " if _i else ""
            if opt in _tier_to_label:
                return _pre + _tier_to_label[opt]
            return _pre + {_CUSTOM:"Custom (set ranges yourself)",
                    _AUTO_LABEL:"🤖 Auto-Optimize (smart search → max PNL)",
                    _WF_LABEL:"🔁 Walk-Forward (anchored — re-optimize, test unseen, repeat)",
                    _AI_OPT_LABEL:"🧠 AI Optimize (agentic — AI tunes across rounds)",
                    _AI_EVO_LABEL:"🧬 AI Evolve (agentic — AI rewrites the strategy)"}.get(opt, opt)

        # SEGMENTED CONTROL, not a selectbox — DELIBERATE component swap. The
        # BaseWeb select on this Streamlit build intermittently sent STALE widget
        # state: pick N's message carried pick N-1's value, so the server reran
        # one interaction behind (or skipped entirely when the stale value matched
        # its current state). Verified at the wire: the dropdown DISPLAY changed
        # while the server log showed no rerun (or a rerun rendering the previous
        # scope — the "Custom editor stuck / scope changes in name only" bug).
        # Button-class widgets (tabs/pills) never exhibited it. Pills are also a
        # better fit for 8 fixed scopes: one click, no dropdown, all visible.
        def _fmt_pill(opt):
            _i = (_scope_opts.index(opt) + 1) if opt in _scope_opts else 0
            _short = {_CUSTOM: "✎ Custom", _AUTO_LABEL: "🤖 Auto",
                      _WF_LABEL: "🔁 Walk-Fwd", _AI_OPT_LABEL: "🧠 AI Opt",
                      _AI_EVO_LABEL: "🧬 AI Evolve"}.get(opt, opt.title())
            return f"{_i}. {_short}"
        _committed = st.session_state.get("_scope_tier_committed", _scope_opts[0])
        if st.session_state.get("ex_scope_seg") not in _scope_opts:
            st.session_state["ex_scope_seg"] = (_committed if _committed in _scope_opts
                                                else _scope_opts[0])
        _scope_tier = st.segmented_control("Scope", _scope_opts, format_func=_fmt_pill,
                                           key="ex_scope_seg", selection_mode="single",
                                           label_visibility="collapsed")
        if _scope_tier is None:                      # pills allow deselect — re-pin
            _scope_tier = (_committed if _committed in _scope_opts else _scope_opts[0])
        st.session_state["_scope_tier_committed"] = _scope_tier
        # Full description of the selected scope (the pills show short names)
        st.markdown(f"<div style='font-size:.72rem;opacity:.55;margin:2px 0 8px'>"
                    f"{_fmt_scope(_scope_tier)}</div>", unsafe_allow_html=True)

        # ── STABLE-TOPOLOGY scope UI ──────────────────────────────────────
        # Streamlit 1.57's frontend fails to prune WIDGET elements when a rerun
        # stops rendering them (markdown prunes fine; inputs/sliders/checkboxes
        # ghost — verified in the DOM: after Custom→Short the caption vanished
        # but all 15 inputs stayed). Conditional widget trees also desynced the
        # session (reruns lagging one interaction behind). Fix: render the SAME
        # widget tree on EVERY run — the Custom editor and the Auto/WF controls
        # live in ALWAYS-PRESENT expanders with CONSTANT labels and constant
        # expanded=False (changing either remounts the expander = ghost risk).
        # Only captions/markdown vary with the scope. Nothing conditional =
        # nothing to prune = nothing can ghost.
        _SPECIAL = {_CUSTOM, _AUTO_LABEL, _WF_LABEL, _AI_OPT_LABEL, _AI_EVO_LABEL}
        if _scope_tier in _tier_to_label:
            scope = _tier_to_label[_scope_tier]            # full label for this strategy
        else:
            scope = _scope_tier                            # special scope sentinel
        _is_ai = _scope_tier in (_AI_OPT_LABEL, _AI_EVO_LABEL)
        _is_wf_scope = (_scope_tier == _WF_LABEL)
        opt_mode = "auto" if _scope_tier in (_AUTO_LABEL, _WF_LABEL) else "grid"
        _is_auto_mode = (opt_mode == "auto")
        _wf_folds = 0   # 0 = auto-fit fold count to data length
        auto_oos = bool(st.session_state.get("_auto_oos_committed", True))
        auto_oos_method = st.session_state.get("_auto_oos_method_committed", "single")
        # Grid ONLY when a real preset tier is selected (never for special scopes)
        custom_grid = sg.get(scope, {}) if (_scope_tier in _tier_to_label
                                            and _scope_tier not in _SPECIAL) else {}

        _eta_cal = _get_eta_calib()
        _sec_per_bt = float(_eta_cal.get("sec_per_bt", 0) or 0)
        def _est_time(n_combos):
            # Measured per-backtest time from the last real run when available.
            per = _sec_per_bt if _sec_per_bt > 0 else 0.005
            secs = n_combos * per
            if secs < 1:   return "<1 sec"
            if secs < 60:  return f"~{int(secs)} sec"
            if secs < 3600:return f"~{secs/60:.1f} min"
            return f"~{secs/3600:.1f} hr"

        # ── Auto / Walk-Forward controls — ALWAYS rendered, constant shape ──
        with st.expander("⚙ Auto / Walk-Forward settings"):
            if not _is_auto_mode:
                st.caption("Applies when Scope is 🤖 Auto-Optimize or 🔁 Walk-Forward.")
            _committed_trials = int(st.session_state.get("_ntrials_committed", 200))
            _committed_trials = max(25, min(1000, _committed_trials))
            n_trials = st.slider("Trials (backtests to run)", 25, 1000,
                                 _committed_trials, 25,
                                 help="How many parameter sets the optimizer will try. "
                                      "More trials = better optimum, longer run.")
            st.session_state["_ntrials_committed"] = int(n_trials)
            _engine = "Bayesian (Optuna)" if _HAS_OPTUNA else "Random search"
            st.markdown(
                f"<div style='font-size:.72rem;opacity:.6;margin-top:2px'>"
                f"Engine: <b>{_engine}</b> · objective: <b>max total PNL</b> · searches "
                f"every parameter's full range automatically.</div>",
                unsafe_allow_html=True)
            _oos_ui = st.checkbox("Out-of-sample validation (Auto-Optimize)",
                value=auto_oos,
                help=f"Optimize on the first {int(AI_OOS_SPLIT*100)}% of the data, then "
                     f"re-test the strongest configs on the last "
                     f"{int((1-AI_OOS_SPLIT)*100)}% they never saw. Strongly recommended. "
                     f"The Walk-Forward scope always validates (this toggle is ignored there).")
            st.session_state["_auto_oos_committed"] = bool(_oos_ui)
            _wf_opts = ["single", "walkforward"]
            _wf_lbl = {"single": f"Single {int(AI_OOS_SPLIT*100)}/"
                                 f"{int((1-AI_OOS_SPLIT)*100)} split",
                       "walkforward": "Walk-forward (rolling)"}
            _wf_idx = (_wf_opts.index(auto_oos_method)
                       if auto_oos_method in _wf_opts else 0)
            _method_ui = st.radio(
                "Validation method (Auto-Optimize)", _wf_opts, index=_wf_idx,
                format_func=lambda x: _wf_lbl[x], horizontal=True,
                help="Single split = train on the first chunk, test once on the rest. "
                     "Walk-forward = re-optimize on a growing window and test each next "
                     "unseen slice.")
            st.session_state["_auto_oos_method_committed"] = _method_ui
            _wf_auto = st.checkbox("Walk-Forward: auto-fit folds to data length",
                value=True,
                help="On = pick the fold count from the data (~one per 3,000 bars, 2-8). "
                     "Off = use the Folds slider below. Only the Walk-Forward scope uses this.")
            _wf_folds_ui = st.slider(
                "Folds (used when auto-fit is OFF)", 3, 8,
                int(st.session_state.get("_wf_folds_committed", 6) or 6),
                help="More folds = more out-of-sample tests, each on a smaller unseen slice.")
            st.session_state["_wf_folds_committed"] = int(_wf_folds_ui)

        # Resolve effective values from the always-rendered controls
        if _is_wf_scope:
            auto_oos = True
            auto_oos_method = "walkforward"
            _wf_folds = 0 if _wf_auto else int(_wf_folds_ui)
            st.caption("🔁 Anchored walk-forward: re-optimizes on a growing window, tests "
                       "each next unseen slice"
                       + (" · folds auto-fit (~one per 3,000 bars)" if _wf_auto
                          else f" · {_wf_folds} folds")
                       + f" · {int(n_trials)} trials/fold")
        elif _is_auto_mode:
            auto_oos = bool(_oos_ui)
            auto_oos_method = _method_ui

        # Projected ETA for the auto/walk-forward scopes (grid shows its own below).
        if opt_mode == "auto" and not _is_ai:
            _bt_per = (max(2, _wf_folds) if (_is_wf_scope and _wf_folds >= 2)
                       else 5 if _is_wf_scope else 1)
            _eta_bt = int(n_trials) * _bt_per
            _per_bt = _sec_per_bt or 0.02
            _eta_s = _eta_bt * _per_bt
            _eta_txt = ("<1 sec" if _eta_s < 1 else f"~{int(_eta_s)} sec" if _eta_s < 60
                        else f"~{_eta_s/60:.1f} min" if _eta_s < 3600
                        else f"~{_eta_s/3600:.1f} hr")
            st.caption(f"⏱ Projected ≈ {_eta_bt:,} backtests · {_eta_txt} "
                       f"(scales with your data size)")

        if _is_ai:
            _ai_mode = "evolve" if _scope_tier == _AI_EVO_LABEL else "optimize"
            st.session_state["_ai_pending_mode"] = _ai_mode
            if _ai_mode == "evolve":
                st.markdown(
                    "<div style='font-size:.72rem;opacity:.7;margin-top:4px;line-height:1.5'>"
                    "🧬 <b>AI Evolve</b>: each round, Claude reviews results, tunes "
                    "parameters, AND may rewrite the strategy's Python to improve it. "
                    "Evolved versions are validated, auto-saved to your Library, and "
                    "you can roll back to any.</div>", unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div style='font-size:.72rem;opacity:.7;margin-top:4px;line-height:1.5'>"
                    "🧠 <b>AI Optimize</b>: each round, Claude reviews the results and "
                    "intelligently picks the next parameter ranges to search, "
                    "converging toward the best config.</div>", unsafe_allow_html=True)
            st.caption("⚙ Configure & launch in the AI panel below the Run button.")

        # ── Custom range editor — ALWAYS rendered, constant shape ────────────
        if active_strat and hasattr(active_strat, "DEFAULT_PARAMS"):
            _custom_on = (_scope_tier == _CUSTOM)
            with st.expander("✎ Custom parameter ranges"):
                if _custom_on:
                    st.markdown("<div style='font-size:.72rem;opacity:.45;margin-bottom:6px'>"
                                "Set a range per parameter — every combination is tested.</div>",
                                unsafe_allow_html=True)
                else:
                    st.caption("Applies when Scope is 4. Custom — pick it above, then "
                               "set ranges here.")
                dp = active_strat.DEFAULT_PARAMS; _cg = {}
                _hc0, _hc1, _hc2, _hc3, _hc4 = st.columns([3, 2, 2, 2, 1.4])
                for _hcol, _htxt in ((_hc1, "MIN"), (_hc2, "MAX"), (_hc3, "STEP")):
                    _hcol.markdown(f"<div style='font-size:.64rem;letter-spacing:.08em;"
                                   f"opacity:.45;font-weight:700'>{_htxt}</div>",
                                   unsafe_allow_html=True)
                for pn, pi in dp.items():
                    typ = pi.get("type","float")
                    label = pi.get("label", pn)
                    if typ == "bool":
                        lc, vc, cc = st.columns([3, 5, 2])
                        lc.markdown(f"<div style='padding-top:6px;font-size:.8rem;"
                                    f"font-weight:600'>{label}</div>", unsafe_allow_html=True)
                        _cg[pn] = [vc.checkbox(f"on/off · {pn}", value=pi.get("default",False),
                                               label_visibility="collapsed")]
                        cc.markdown("<div style='padding-top:6px;font-size:.72rem;opacity:.5'>"
                                    "1 val</div>", unsafe_allow_html=True)
                        continue
                    is_int = (typ=="int")
                    mn,mx,stp = pi.get("min",0),pi.get("max",10),pi.get("step",1 if is_int else 0.1)
                    kw = {"step":float(1 if is_int else stp)}
                    if not is_int: kw["format"]="%.2f"
                    lc, c_mn, c_mx, c_st, c_ct = st.columns([3, 2, 2, 2, 1.4])
                    lc.markdown(f"<div style='padding-top:6px;font-size:.8rem;"
                                f"font-weight:600'>{label}</div>", unsafe_allow_html=True)
                    v1 = c_mn.number_input(f"Min · {pn}",  value=float(mn), **kw,
                                           label_visibility="collapsed")
                    v2 = c_mx.number_input(f"Max · {pn}",  value=float(mx), **kw,
                                           label_visibility="collapsed")
                    v3 = c_st.number_input(f"Step · {pn}", value=float(stp),
                                           min_value=kw["step"], **kw,
                                           label_visibility="collapsed")
                    if v2>=v1 and v3>0:
                        vs = np.arange(v1,v2+v3/2,v3)
                        _cg[pn] = [int(x) for x in vs] if is_int else [round(float(x),4) for x in vs]
                        c_ct.markdown(f"<div style='padding-top:8px;font-size:.74rem;"
                                      f"font-weight:700;color:var(--accent)'>"
                                      f"{len(_cg[pn])} vals</div>", unsafe_allow_html=True)
                    else:
                        _cg[pn] = []
                        c_ct.markdown("<div style='padding-top:8px;font-size:.72rem;"
                                      "color:var(--bad)'>⚠ bad</div>", unsafe_allow_html=True)
            if _custom_on:
                custom_grid = _cg

        if custom_grid:
            _dp_now = getattr(active_strat, "DEFAULT_PARAMS", None) if active_strat else None
            raw_nc = int(np.prod([max(len(v),1) for v in custom_grid.values()]))
            nc = _count_effective_combos(custom_grid, _dp_now)
            parts = [f"{k.replace('_',' ')}: {len(v)}" for k, v in custom_grid.items() if len(v) > 1]
            breakdown = "  ·  ".join(parts) if parts else "all single-value"
            saved = raw_nc - nc
            saved_note = (f"  ·  <span style='color:var(--good)'>"
                          f"{saved:,} skipped (inactive params)</span>") if saved > 0 else ""
            st.markdown(
                f"<div style='margin-top:8px;padding:10px 14px;border-radius:var(--r);"
                f"background:var(--s2);display:flex;justify-content:space-between;"
                f"align-items:center;flex-wrap:wrap;gap:8px'>"
                f"<div><span style='font-weight:800;font-size:1.1rem;color:var(--accent)'>"
                f"{nc:,}</span> "
                f"<span style='opacity:.6;font-size:.8rem'>combinations</span></div>"
                f"<div style='font-size:.8rem;opacity:.7'>⏱ est <b>{_est_time(nc)}</b></div>"
                f"</div>"
                f"<div style='font-size:.73rem;opacity:.4;margin-top:4px'>{breakdown}{saved_note}</div>",
                unsafe_allow_html=True)
            if nc > MAX_GRID_COMBOS:
                st.warning(f"⚠ {nc:,} combinations is too many to run as a grid "
                           f"(cap {MAX_GRID_COMBOS:,}). Narrow the Custom ranges/steps, "
                           f"or use 🤖 Auto-Optimize to search this space instead.")

    # ══ TILE 4 · RUN ═════════════════════════════════════════════════════
    with st.container(key="tilebox_run"):
        st.markdown("<div class='tile-h'>Launch</div>", unsafe_allow_html=True)
        # Per-trade trading costs — applied to EVERY config so results are realistic
        # and the optimizer can't favour cost-bleed scalpers. Defaults ≈ ES on a
        # NinjaTrader free plan; adjust for your instrument/broker (0 = gross).
        # ONE horizontal row: costs · name · min-trades · Run · Queue.
        # Plain buttons ON PURPOSE (no form): Enter must NOT launch a run —
        # an accidental keypress firing a backtest is worse than one extra click.
        cc1, cc2, rc1, rc2, rc3, rc4 = st.columns([1.1, 1.1, 1.6, 0.7, 0.9, 0.9])
        commission_usd = cc1.number_input("Commission $/RT", 0.0, 100.0,
            5.66, 0.10, key="ex_comm",
            help="Per-contract commission for a FULL round trip. ES≈$5.66 (down to "
                 "$4.26), MES≈$1.90 (down to $1.30) on NinjaTrader free. 0 = gross.")
        slippage_pts = cc2.number_input("Slippage pts/RT", 0.0, 10.0,
            0.25, 0.25, key="ex_slip",
            help="Assumed slippage per round trip, in points (ES 1 tick = 0.25 pt = "
                 "$12.50). Stops slip more than limits; 0.25–0.5 is a sane start.")
        run_name = rc1.text_input("Run name", key="ex_rn", placeholder="Optional label")
        min_trades = rc2.number_input("Min T", 1, 200, 30, key="ex_mt",
            help="Minimum trades a config must make to count. Under ~30 is "
                 "statistical noise — keep it high so the optimizer can't 'win' on "
                 "a handful of lucky trades. Lower it only if your data is short.")
        rc3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        run_now = rc3.button("Run", width="stretch", type="primary", key="ex_run")
        rc4.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        add_queue = rc4.button("Queue", width="stretch", key="ex_q")

    # ── Handle actions ────────────────────────────────────────────────────
    if add_queue or run_now:
        cfg = _build_config(run_name=run_name, inst_name=inst_name, tf_name=tf_name,
            data_source=data_source, scope=scope, custom_grid=custom_grid,
            ticker=ticker, tf_cfg=tf_cfg, multiplier=multiplier,
            min_trades=min_trades, sel_strat=sel_strat,
            csv_lib_path=_csv_lib_path, csv_file_obj=csv_file,
            csv_src_name=_csv_src_name,
            opt_mode=opt_mode, n_trials=n_trials, auto_oos=auto_oos,
            auto_oos_method=auto_oos_method, wf_folds=_wf_folds,
            commission_usd=commission_usd, slippage_pts=slippage_pts,
            date_from=_date_from, date_to=_date_to)
        if add_queue:
            st.session_state.queue.append(cfg)
            st.toast(f"Queued: {cfg['name']}")
            st.rerun()  # refresh so the sidebar shows the new queued run now
        if run_now:
            df_r, err_r = _load_df_for_config(cfg)
            if err_r or df_r is None: st.error(f"Data error: {err_r}")
            elif len(df_r) < 50: st.error("Need 50+ bars.")
            else:
                eid = str(uuid.uuid4())
                upsert_exec_record(eid, cfg["name"], cfg)
                exec_manager.submit(eid, cfg, df_r, cfg["multiplier"], cfg["min_trades"])
                _save_last_run_cfg(cfg)      # powers the sidebar ↻ Quick Run button
                st.toast(f"Started: {cfg['name']}"); st.rerun()

    st.caption("▸ Live runs, the queue, and recent runs are in the sidebar "
               "(left edge — click the » to expand).")

    # ══ AI OPTIMIZATION PANEL (🧠 AI Optimize · 🧬 AI Evolve) ═══════════════
    _ai_sess = st.session_state.get("_ai_session")
    _show_ai_panel = (st.session_state.get("_ai_pending_mode") and
                      scope in (_AI_OPT_LABEL, _AI_EVO_LABEL)) or _ai_sess
    if _show_ai_panel:
        with st.container(key="tilebox_ai"):
            _mode = (_ai_sess["mode"] if _ai_sess
                     else st.session_state.get("_ai_pending_mode", "optimize"))
            _title = "🧬 AI Evolve" if _mode == "evolve" else "🧠 AI Optimize"
            st.markdown(f"<div class='tile-h'>{_title}</div>", unsafe_allow_html=True)

            # If a session is active/finished, show its live state
            if _ai_sess:
                _st = _ai_sess.get("status", "running")
                _rnd = _ai_sess.get("round", 0)
                _tot = _ai_sess.get("total_rounds", AI_DEFAULT_ROUNDS)
                _pct = int(_rnd / max(1, _tot) * 100)
                _badge = {"running": ("bg-g", "RUNNING"), "done": ("bg-b", "DONE"),
                          "error": ("bg-r", "ERROR"), "stopped": ("bg-y", "STOPPED"),
                          "awaiting_claude": ("bg-y", "AWAITING CLAUDE CODE")}.get(_st, ("bg-g","…"))
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>"
                    f"<span class='bg {_badge[0]}'>{_badge[1]}</span>"
                    f"<span style='font-weight:700'>Round {_rnd} / {_tot}</span></div>"
                    f"<div style='font-size:.72rem;color:var(--accent);margin:-2px 0 6px'>"
                    f"strategy: {_ai_sess.get('strategy_name','?')} · "
                    f"{_ai_sess.get('instrument','')} {_ai_sess.get('timeframe','')}</div>"
                    f"<div class='pg-t'><div class='pg-f' style='width:{_pct}%'></div></div>",
                    unsafe_allow_html=True)

                _best = _ai_sess.get("best")
                if _best:
                    _bo = _ai_sess.get("best_oos")
                    st.markdown(
                        f"<div style='margin-top:8px;font-size:.8rem'>"
                        f"<b>Best so far:</b> in-sample PNL "
                        f"<span style='color:var(--good)'>{_best.get('total_pnl',0):,.0f}</span>"
                        + (f" · out-of-sample PNL <span style='color:{'var(--good)' if (_bo or 0)>0 else 'var(--bad)'}'>{_bo:,.0f}</span>"
                           if _bo is not None else "")
                        + f" · {_best.get('num_trades',0)} trades · "
                        f"PF {_best.get('profit_factor',0):.2f}</div>",
                        unsafe_allow_html=True)
                    if _bo is not None and _best.get('total_pnl',0) > 0:
                        _ratio = _bo / max(_best.get('total_pnl',1), 1e-9)
                        if _ratio < 0.3:
                            st.warning("⚠ Out-of-sample PNL is far below in-sample — "
                                       "this best config looks **overfit**. Treat with caution.")

                # Round log
                _logs = _ai_sess.get("log", [])
                if _logs:
                    with st.expander(f"Round log ({len(_logs)})", expanded=(_st=="running")):
                        for ln in _logs[-20:]:
                            st.markdown(f"<div style='font-size:.74rem;opacity:.8;"
                                        f"margin:2px 0'>{ln}</div>", unsafe_allow_html=True)

                # Saved AI strategy + what changed (shown on completion)
                _tn = _ai_sess.get("tuned_name") or _ai_sess.get("promoted_name")
                if _tn and _st in ("done", "stopped"):
                    st.success(f"💾 Saved to Library: **{_tn}** — original untouched.")
                    _td = _ai_sess.get("tuned_diff") or []
                    if _td:
                        _drows = "".join(
                            f"<tr><td style='padding:1px 12px 1px 0;color:var(--t3)'>{k}</td>"
                            f"<td style='padding:1px 8px;color:var(--t2)'>{o}</td>"
                            f"<td style='color:var(--t3)'>→</td>"
                            f"<td style='padding:1px 8px;color:var(--accent);font-weight:700'>{n}</td></tr>"
                            for k, o, n in _td)
                        st.markdown(
                            f"<div style='font-size:.76rem;margin:6px 0 2px'><b>What changed</b> "
                            f"vs the original ({len(_td)} params):</div>"
                            f"<table style='font-size:.76rem;border-collapse:collapse'>{_drows}</table>",
                            unsafe_allow_html=True)

                # Controls
                cc1, cc2 = st.columns(2)
                if _st == "running":
                    if cc1.button("⏹ Stop after this round", key="ai_stop",
                                  width="stretch"):
                        _ai_sess["status"] = "stopped"
                        _ai_sess.setdefault("log", []).append("Stopped by user.")
                        st.rerun()
                elif _st == "awaiting_claude":
                    st.info(f"📤 **Round {_rnd} exported** to `augur_ai_handoff.json`. "
                            f"In your Claude Code chat, say **“process the AUGUR round”** — "
                            f"I'll read it and write `augur_ai_proposal.json`, then click Apply.")
                    if cc1.button("📥 Apply Claude's proposal", key="ai_apply",
                                  type="primary", width="stretch"):
                        _ok, _msg = _ai_keyless_apply(_ai_sess)
                        if not _ok:
                            st.warning(_msg)
                        else:
                            if _ai_sess.get("status") in ("done", "stopped", "error"):
                                if _ai_sess.get("mode") == "evolve":
                                    _promote_evolved_strategy(_ai_sess)
                                else:
                                    _promote_tuned_strategy(_ai_sess)
                                _ai_save_to_history(_ai_sess)
                            st.rerun()
                    if cc2.button("⏹ Stop", key="ai_stop_await",
                                  width="stretch"):
                        _ai_sess["status"] = "stopped"
                        _ai_sess.setdefault("log", []).append("Stopped by user.")
                        _ai_save_to_history(_ai_sess)
                        st.rerun()
                else:
                    if cc1.button("Clear session", key="ai_clear", width="stretch"):
                        st.session_state.pop("_ai_session", None)
                        st.rerun()
                    # On finish: offer to load best results into Results tab
                    if cc2.button("📊 View best in Results", key="ai_view",
                                  width="stretch", type="primary"):
                        _bp = _ai_sess.get("best_strategy_path") or _ai_sess["strategy_path"]
                        ok, _ = _set_active_strategy(_bp)
                        st.session_state["_ai_goto_results"] = True
                        st.toast("Best strategy activated. See Results tab.")
                        st.rerun()

            else:
                # No active session — choose engine + config + start
                _cfg_key = _load_config_json().get("anthropic_key", "")
                _eng_opts = ["claude_code", "api"]
                _eng_lbl = {"claude_code": "🤝 Claude Code · no key",
                            "api": "🔑 Anthropic API key"}
                _eng_def = st.session_state.get("_ai_engine_committed",
                                                "api" if _cfg_key else "claude_code")
                if _eng_def not in _eng_opts:
                    _eng_def = "claude_code"
                _engine = st.radio(
                    "Engine", _eng_opts, index=_eng_opts.index(_eng_def),
                    format_func=lambda x: _eng_lbl[x], horizontal=True,
                    key="_ai_engine_radio",
                    help="Claude Code = run the rounds for FREE through your Claude Code "
                         "chat (each round you tell Claude to process it, no API spend). "
                         "API key = fully automatic, bills your Anthropic account.")
                st.session_state["_ai_engine_committed"] = _engine
                if _engine == "api":
                    ai_key = st.text_input(
                        "Anthropic API key", type="password", key="_ai_api_key",
                        value=_cfg_key,
                        placeholder="sk-ant-…",
                        help="Pre-filled from Settings if saved there. Each round = "
                             "one API call. Get one at console.anthropic.com.")
                else:
                    ai_key = ""
                    st.caption("No API key needed — the app runs the sweeps + "
                               "out-of-sample validation locally and hands each round to "
                               "your Claude Code session via a file. You stay in control "
                               "of every round.")
                ac1, ac2 = st.columns(2)
                ai_rounds = ac1.slider("Rounds", 1, 20, AI_DEFAULT_ROUNDS, 1,
                    key="_ai_rounds",
                    help="How many improve-and-retest cycles. Each round makes "
                         "one API call. Default 5.")
                ai_oos = ac2.checkbox("Out-of-sample validation", value=True,
                    key="_ai_oos",
                    help=f"Optimize on the first {int(AI_OOS_SPLIT*100)}% of data, "
                         f"validate on the last {int((1-AI_OOS_SPLIT)*100)}% the AI "
                         f"never sees. Catches overfitting. Strongly recommended.")
                ai_cpr = st.slider("Configs per round (backtests)", 100, 1000, 400, 50,
                    key="_ai_cpr",
                    help="Parameter combinations each round sweeps before proposing the "
                         "next ranges. Higher = more thorough per round (slower). Up to "
                         "1000 — use the high end for a serious 'for-real' run.")
                st.markdown(
                    f"<div style='font-size:.72rem;opacity:.55;line-height:1.5;margin:4px 0'>"
                    + (f"Runs unattended for {ai_rounds} round(s), ~{ai_rounds} API call(s) total. "
                       if _engine == "api" else
                       f"{ai_rounds} round(s); each pauses for your Claude Code session to "
                       f"propose the next ranges — free, no API spend. ")
                    + ("Evolved strategies auto-save to your Library."
                       if _mode == "evolve" else "")
                    + "</div>", unsafe_allow_html=True)

                if st.button(f"▶ Start {_title}", key="ai_start", type="primary",
                             width="stretch",
                             disabled=(_engine == "api" and not ai_key)):
                    # Build the session: load + split data
                    _cfg = _build_config(run_name=run_name, inst_name=inst_name,
                        tf_name=tf_name, data_source=data_source, scope="grid",
                        custom_grid={}, ticker=ticker, tf_cfg=tf_cfg,
                        multiplier=multiplier, min_trades=min_trades,
                        sel_strat=sel_strat, csv_lib_path=_csv_lib_path,
                        csv_file_obj=csv_file, csv_src_name=_csv_src_name)
                    _df, _err = _load_df_for_config(_cfg)
                    if _err or _df is None:
                        st.error(f"Data error: {_err}")
                    elif len(_df) < 100:
                        st.error("Need 100+ bars for AI optimization.")
                    else:
                        _reg = get_strategy_registry()
                        _spath = _reg.get("current_path")
                        _strat = _get_active_strategy()
                        if not _spath or _strat is None:
                            st.error("Select a strategy first.")
                        else:
                            if ai_oos:
                                _isd, _oosd = _split_is_oos(_df)
                            else:
                                _isd, _oosd = _df, _df.iloc[0:0]
                            def _arr(d):
                                return (d["Open"].to_numpy(float), d["High"].to_numpy(float),
                                        d["Low"].to_numpy(float), d["Close"].to_numpy(float))
                            # Invalidate the mtime cache for this strategy so the
                            # round loop loads a FRESH copy (avoids any stale module
                            # reuse that could make different strategies look alike).
                            try: _STRAT_MOD_CACHE.pop(_spath, None)
                            except Exception: pass
                            _strat_nm = getattr(_strat, "STRATEGY_NAME", sel_strat)
                            st.session_state.pop("_ai_session", None)  # clear any prior
                            st.session_state["_ai_session"] = {
                                "mode": _mode, "strategy_path": _spath,
                                "orig_strategy_path": _spath,
                                "engine": _engine, "sid": uuid.uuid4().hex[:8],
                                "strategy_name": _strat_nm,
                                "is_arrays": _arr(_isd),
                                "oos_arrays": _arr(_oosd) if len(_oosd) else _arr(_isd),
                                "min_trades": int(min_trades),
                                "total_rounds": int(ai_rounds), "round": 0,
                                "grid": _ai_seed_grid(getattr(_strat,"DEFAULT_PARAMS",{}), points=4),
                                "best": None, "best_oos": None, "history": [],
                                "status": "running", "oos_on": bool(ai_oos),
                                "max_combos_per_round": int(ai_cpr),
                                "instrument": inst_name, "timeframe": tf_name,
                                "source_name": _csv_src_name, "multiplier": multiplier,
                                "commission_usd": commission_usd, "slippage_pts": slippage_pts,
                                "log": [f"Started {_title} on '{_strat_nm}' · {ai_rounds} rounds · "
                                        f"OOS {'on' if ai_oos else 'off'} · "
                                        f"{len(_isd):,} IS / {len(_oosd):,} OOS bars"],
                            }
                            st.rerun()

    # ── AI round driver: advances one round per tick while running ──────────
    _ai_sess = st.session_state.get("_ai_session")
    if _ai_sess and _ai_sess.get("status") == "running":
        _key = st.session_state.get("_ai_api_key", "") or _load_config_json().get("anthropic_key", "")
        if _HAS_FRAG_TIMER:
            @st.fragment(run_every="1s")
            def _ai_round_driver():
                s = st.session_state.get("_ai_session")
                if not s or s.get("status") != "running":
                    return
                # Guard: run exactly one round per tick, not re-entrant
                if s.get("_ticking"):
                    return
                s["_ticking"] = True
                try:
                    ai_run_one_round(s, _key)
                    # On completion: auto-promote evolved strategy + save to history.
                    # NOT on 'awaiting_claude' (a keyless mid-round pause for Claude Code).
                    if s.get("status") in ("done", "stopped", "error"):
                        if s.get("mode") == "evolve":
                            _promote_evolved_strategy(s)
                        else:
                            _promote_tuned_strategy(s)
                        _ai_save_to_history(s)
                finally:
                    s["_ticking"] = False
                st.rerun(scope="app")
            _ai_round_driver()
        else:
            # No fragment timer: drive one round per manual rerun
            ai_run_one_round(_ai_sess, _key)
            if _ai_sess.get("status") in ("done", "stopped", "error"):
                if _ai_sess.get("mode") == "evolve":
                    _promote_evolved_strategy(_ai_sess)
                else:
                    _promote_tuned_strategy(_ai_sess)
                _ai_save_to_history(_ai_sess)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  RESULTS RENDERER
# ══════════════════════════════════════════════════════════════════════════════

with tab_exec:
    _exec_tab_fragment()

def _render_retest_panel(params_row, meta, multiplier, kp=""):
    """Re-test ONE config on a different CSV — no re-optimizing. The cleanest test
    of whether an edge holds on data it never saw (the 5-min, a later slice, …)."""
    with st.expander("🔁 Re-test this config on different data", expanded=False):
        st.markdown("<div style='font-size:.74rem;opacity:.6'>Same config, unseen data"
                    + _hint("Runs THIS exact config on another saved CSV (net of the "
                            "same costs). If the edge holds on data it never saw, "
                            "that's the real validation — overfit configs fall apart "
                            "here.")
                    + "</div>", unsafe_allow_html=True)
        try:
            _metas = load_csv_metas()
        except Exception:
            _metas = None
        if _metas is None or len(_metas) == 0:
            st.info("No saved CSVs to test against — add one in the Library tab.")
            return
        _recs = _metas.to_dict("records")
        def _lbl(r):
            return (f"{r.get('name') or r.get('filename','?')} · "
                    f"{r.get('timeframe','')} · {int(r.get('rows',0) or 0):,} rows")
        _sel = st.selectbox("Test on", _recs, format_func=_lbl, key=kp+"rt_csv")
        if not st.button("▶ Run re-test", key=kp+"rt_go"):
            return
        _df, _err = _read_stored_csv(_sel.get("filename", ""))
        if _err or _df is None:
            st.error(f"Couldn't load that CSV: {_err}"); return
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            st.error(f"Strategy '{_sname}' isn't in the Library, so I can't re-run it.")
            return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            st.error(f"Couldn't load strategy: {_me}"); return
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _params = {}
        for k, v in dict(params_row).items():
            if k in _METR:
                continue
            if isinstance(v, np.integer):    v = int(v)
            elif isinstance(v, np.floating): v = float(v)
            elif isinstance(v, np.bool_):    v = bool(v)
            _params[k] = v
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        O=_df["Open"].to_numpy(float); H=_df["High"].to_numpy(float)
        L=_df["Low"].to_numpy(float);  C=_df["Close"].to_numpy(float)
        try:
            _m = _mod.run_backtest(O, H, L, C, return_trades=True, **_params)
            if _cp > 0 and _m:
                _m = _apply_costs(_m, _cp)
        except Exception as _ex:
            st.error(f"Re-test failed: {_ex}"); return
        if not _m or _m.get("num_trades", 0) == 0:
            st.warning("That config produced **0 trades** on this data — its signals "
                       "didn't fire here (often a timeframe/scale mismatch).")
            return
        _pf = float(_m.get("profit_factor", 0) or 0)
        _pfs = "∞" if (_pf == float("inf") or _pf > 999) else f"{_pf:.2f}"
        _pnl_usd = float(_m["total_pnl"]) * multiplier
        _src = _sel.get("name") or _sel.get("filename")
        st.markdown(f"<div style='font-size:.8rem;font-weight:600;margin-top:6px'>"
                    f"Re-test on <b>{_src}</b> ({len(_df):,} bars"
                    f"{' · net of costs' if _cp>0 else ' · gross'}):</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div class='kg' style='margin:2px 0 4px'>
    <div class='kt'><div class='kl'>PNL</div><div class='kv'>${_pnl_usd:,.0f}</div></div>
    <div class='kt'><div class='kl'>Win Rate</div><div class='kv'>{float(_m['win_rate']):.1f}%</div></div>
    <div class='kt'><div class='kl'>Profit Factor</div><div class='kv'>{_pfs}</div></div>
    <div class='kt'><div class='kl'>Trades</div><div class='kv'>{int(_m['num_trades'])}</div></div>
    <div class='kt'><div class='kl'>Max DD</div><div class='kv'>${float(_m['max_drawdown'])*multiplier:,.0f}</div></div>
    </div>""", unsafe_allow_html=True)
        _orig_pf = float(params_row.get("profit_factor", 0) or 0)
        if _pf >= max(1.0, _orig_pf * 0.6):
            st.success(f"✓ Holds up — original PF {_orig_pf:.2f} → here {_pfs}. The edge "
                       f"survived data it never saw.")
        elif _pf >= 1.0:
            st.warning(f"~ Degrades — original PF {_orig_pf:.2f} → here {_pfs}. Still "
                       f"profitable, but the edge shrank.")
        else:
            st.error(f"✗ Breaks — original PF {_orig_pf:.2f} → here {_pfs} (< 1 = loses "
                     f"money). Likely overfit to the original data.")


def _render_stress_panel(params_row, meta, multiplier, kp=""):
    """Stress-test ONE config across consecutive time windows of its data — exposes
    CONCENTRATION / regime-dependence: did the edge work throughout the period, or did
    one lucky stretch carry the whole PNL? This is a consistency check on the SAME data
    the config was optimized on (NOT new out-of-sample data — for that use Re-test on a
    different CSV, or Walk-forward). Cheap: runs the fixed config once per window."""
    with st.expander("🔬 Stress-test this config across time", expanded=False):
        st.markdown("<div style='font-size:.74rem;opacity:.6'>Consistency across time"
                    + _hint("Splits the data into consecutive windows and runs THIS exact "
                            "config (net of the same costs) in each. A durable edge makes "
                            "money in MOST windows; an overfit one has nearly all its "
                            "profit in one stretch. Same data it was optimized on — for "
                            "unseen data use Re-test or Walk-forward.")
                    + "</div>", unsafe_allow_html=True)
        try:
            _metas = load_csv_metas()
        except Exception:
            _metas = None
        if _metas is None or len(_metas) == 0:
            st.info("No saved CSV to slice — add one in the Library tab.")
            return
        _recs = _metas.to_dict("records")
        _srcn = (meta.get("source_name", "") or "").strip()
        _def_idx = next((i for i, r in enumerate(_recs)
                         if str(r.get("name", "")).strip() == _srcn), 0) if _srcn else 0
        def _lbl(r):
            return (f"{r.get('name') or r.get('filename','?')} · "
                    f"{r.get('timeframe','')} · {int(r.get('rows',0) or 0):,} rows")
        _c1, _c2 = st.columns([3, 1])
        _sel = _c1.selectbox("Data to slice (defaults to this run's data)",
                             _recs, index=_def_idx, format_func=_lbl, key=kp+"st_csv")
        _nwin = _c2.slider("Windows", 3, 8, 5, key=kp+"st_nwin")
        if not st.button("▶ Run stress-test", key=kp+"st_go"):
            return
        _df, _err = _read_stored_csv(_sel.get("filename", ""))
        if _err or _df is None:
            st.error(f"Couldn't load that CSV: {_err}"); return
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            st.error(f"Strategy '{_sname}' isn't in the Library, so I can't re-run it.")
            return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            st.error(f"Couldn't load strategy: {_me}"); return
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _params = {}
        for k, v in dict(params_row).items():
            if k in _METR:
                continue
            if isinstance(v, np.integer):    v = int(v)
            elif isinstance(v, np.floating): v = float(v)
            elif isinstance(v, np.bool_):    v = bool(v)
            _params[k] = v
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        n = len(C)
        if n < 300:
            st.warning("Not enough bars to slice meaningfully (need ~300+)."); return
        # Session-id + volume plumbing — same as the main run path. Without day_id,
        # session-anchored strategies (ORB, OVERNIGHT_HOLD) return None → "0 trades
        # in every window". Introspect so older strategies that don't accept these
        # kwargs aren't broken by an unexpected-keyword TypeError.
        _Vst = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        try:
            _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAYst = pd.factorize(_eix.dt.date)[0].astype("int64")
        except Exception:
            _DAYst = None
        try:
            import inspect as _isp_st
            _spx = _isp_st.signature(_mod.run_backtest).parameters
            _hkx = any(p.kind == p.VAR_KEYWORD for p in _spx.values())
            _passV = (_Vst is not None) and (_hkx or ("volumes" in _spx))
            _passD = (_DAYst is not None) and (_hkx or ("day_id" in _spx))
        except Exception:
            _passV = _passD = False
        _bounds = [int(round(k * n / _nwin)) for k in range(_nwin + 1)]
        _rows = []
        for w in range(_nwin):
            a, b = _bounds[w], _bounds[w + 1]
            if b - a < 20:
                continue
            try:
                _xtra = {}
                if _passV: _xtra["volumes"] = _Vst[a:b]
                if _passD: _xtra["day_id"]  = _DAYst[a:b]
                _m = _mod.run_backtest(O[a:b], H[a:b], L[a:b], C[a:b],
                                       return_trades=True, **_xtra, **_params)
                if _cp > 0 and _m:
                    _m = _apply_costs(_m, _cp)
            except Exception:
                _m = None
            _rows.append({
                "w": w + 1,
                "from": str(_df.index[a])[:10],
                "to":   str(_df.index[min(b, n) - 1])[:10],
                "tr":  int((_m or {}).get("num_trades", 0) or 0),
                "pnl": (float((_m or {}).get("total_pnl", 0) or 0) * multiplier) if _m else 0.0,
                "pf":  float((_m or {}).get("profit_factor", 0) or 0) if _m else 0.0,
            })
        if not _rows:
            st.warning("Couldn't build any usable windows."); return
        _active = [r for r in _rows if r["tr"] > 0]
        _profit = [r for r in _active if r["pnl"] > 0]
        _na, _np_ = len(_active), len(_profit)
        _tot = sum(r["pnl"] for r in _rows)
        _pos = sum(r["pnl"] for r in _rows if r["pnl"] > 0)
        _share = (max((r["pnl"] for r in _rows), default=0.0) / _pos) if _pos > 0 else 0.0
        def _pfs(v): return "∞" if (v == float("inf") or v > 999) else f"{v:.2f}"
        _cells = []
        for r in _rows:
            _col = ("var(--good)" if r["pnl"] > 0
                    else ("var(--bad)" if r["pnl"] < 0 else "var(--t3)"))
            _cells.append(
                f"<div style='display:flex;gap:8px;padding:5px 11px;"
                f"border-top:1px solid var(--s2);font-size:.77rem;align-items:center'>"
                f"<span style='color:var(--t3);min-width:62px'>Window {r['w']}</span>"
                f"<span style='color:var(--t3);flex:1'>{r['from']} → {r['to']}</span>"
                f"<span style='min-width:46px;text-align:right'>{r['tr']}T</span>"
                f"<span style='min-width:80px;text-align:right;color:{_col};font-weight:700'>${r['pnl']:,.0f}</span>"
                f"<span style='min-width:58px;text-align:right;color:var(--t2)'>PF {(_pfs(r['pf']) if r['tr']>0 else '—')}</span>"
                f"</div>")
        st.markdown(
            f"<div style='font-size:.8rem;font-weight:600;margin:8px 0 2px'>"
            f"This config across {len(_rows)} time windows"
            f"{' · net of costs' if _cp>0 else ' · gross'}:</div>"
            f"<div style='background:var(--s1);border:1px solid var(--s2);border-radius:10px;"
            f"overflow:hidden'>" + "".join(_cells) +
            f"<div style='display:flex;justify-content:space-between;padding:6px 11px;"
            f"border-top:2px solid var(--s2);font-size:.8rem;font-weight:700'>"
            f"<span>Total ({sum(r['tr'] for r in _rows)} trades)</span>"
            f"<span style='color:{'var(--good)' if _tot>0 else 'var(--bad)'}'>${_tot:,.0f}</span>"
            f"</div></div>", unsafe_allow_html=True)
        if _na == 0:
            st.warning("This config fired **0 trades** in every window — its signals "
                       "didn't trigger on this data (timeframe/scale mismatch?).")
            return
        if _na < len(_rows):
            st.caption(f"Active in {_na} of {len(_rows)} windows "
                       f"({len(_rows) - _na} had no trades).")
        _frac = _np_ / _na
        if _na < 3:
            st.info(f"Only **{_na}** window(s) had trades — too sparse to judge "
                    f"consistency across time. Use more data or fewer windows.")
        elif _frac >= 0.8:
            st.success(f"✓ **Consistent** — profitable in **{_np_}/{_na}** active windows. "
                       f"The edge is spread across the period, not a single fluke.")
        elif _frac >= 0.5:
            st.warning(f"~ **Mixed** — profitable in **{_np_}/{_na}** windows. The edge "
                       f"works in some stretches but not others (regime-dependent).")
        else:
            st.error(f"✗ **Fragile** — profitable in only **{_np_}/{_na}** windows. Most "
                     f"of the period it didn't work — likely curve-fit to one stretch.")
        if _na >= 3 and sum(r['tr'] for r in _active) / _na < 5:
            st.caption("Few trades per window — read the win/loss *pattern*, not the "
                       "exact per-window PF (small samples are noisy).")
        if _pos > 0 and _share >= 0.60 and len(_rows) >= 3:
            st.warning(f"⚠ **Concentration risk:** {_share:.0%} of the gross profit came "
                       f"from a **single** window. Remove that stretch and most of the "
                       f"edge disappears — fragile even if the headline PNL looks strong.")


def _render_wf_equity(best, meta, multiplier, res):
    """Equity curve for the walk-forward view (which otherwise shows no chart):
    re-runs the deployed (latest-fold) config on the run's data and plots cumulative
    net PNL, with the out-of-sample tail shaded so you can see how it did on the
    unseen windows."""
    try:
        _srcn = (meta.get("source_name", "") or "").strip()
        _metas = load_csv_metas()
        _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            return
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            return
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            return
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        Vv = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        try:
            _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAYf = pd.factorize(_eix.dt.date)[0].astype("int64")
        except Exception:
            _DAYf = None
        try:
            import inspect as _isp
            _spar = _isp.signature(_mod.run_backtest).parameters
            _hk = any(p.kind == p.VAR_KEYWORD for p in _spar.values())
            _wv = (Vv is not None) and (_hk or ("volumes" in _spar))
            _wd = (_DAYf is not None) and (_hk or ("day_id" in _spar))
        except Exception:
            _wv = _wd = False
        _nbar = len(C)
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        def _row_params(_r):
            _p = {}
            for k, v in dict(_r).items():
                if k in _METR: continue
                if isinstance(v, np.integer):    v = int(v)
                elif isinstance(v, np.floating): v = float(v)
                elif isinstance(v, np.bool_):    v = bool(v)
                _p[k] = v
            return _p
        def _seg(_a, _b, _p):
            # Replay each fold's champion the SAME way the auto/walk-forward search
            # scored it — INCLUDING the per-window session id + volume, so a
            # session-anchored strategy (daily bias, flat-EOD, VWAP) reproduces its
            # saved per-fold OOS PF instead of collapsing to one giant "session".
            if _b - _a < 2: return None
            _ex = {}
            if _wv: _ex["volumes"] = Vv[_a:_b]
            if _wd: _ex["day_id"]  = _DAYf[_a:_b]
            try:
                _mm = _mod.run_backtest(O[_a:_b], H[_a:_b], L[_a:_b], C[_a:_b],
                                        return_trades=True, **_ex, **_p)
            except Exception:
                _mm = None
            return _apply_costs(_mm, _cp) if (_cp > 0 and _mm) else _mm
        # Reconstruct contiguous per-fold windows and STITCH the true walk-forward
        # equity: fold-1's champion over the initial in-sample window, then EACH
        # fold's own champion over its unseen window — so the grey segments show
        # exactly how each re-optimized config did on data it never trained on.
        if not ({"test_bars", "fold"} <= set(res.columns)) or not len(res):
            return
        _rs = res.sort_values("fold").reset_index(drop=True)
        _sizes = [int(x or 0) for x in _rs["test_bars"].tolist()]
        _oos_start = max(0, _nbar - sum(_sizes))
        _pts, _bands, _cum = [], [], 0.0
        _m0 = _seg(0, _oos_start, _row_params(_rs.iloc[0]))
        if _m0 and _m0.get("trades"):
            for t in _m0["trades"]:
                _cum += float(t[2]) * multiplier
                _pts.append((_df.index[min(int(t[1]), max(0, _oos_start - 1))], _cum, False))
        _bs = _oos_start
        for _k, _sz in enumerate(_sizes):
            _be = min(_bs + _sz, _nbar)
            if _be <= _bs: continue
            _bands.append((_bs, _be, _k + 1, float(_rs.iloc[_k].get("oos_pf", 0) or 0)))
            _mk = _seg(_bs, _be, _row_params(_rs.iloc[_k]))
            if _mk and _mk.get("trades"):
                for t in _mk["trades"]:
                    _cum += float(t[2]) * multiplier
                    _pts.append((_df.index[min(_bs + int(t[1]), _nbar - 1)], _cum, True))
            _bs = _be
        if not _pts:
            return
        _xs    = [p[0] for p in _pts]
        _is_y  = [p[1] if not p[2] else None for p in _pts]
        _oos_y = [p[1] if p[2] else None for p in _pts]
        _fo = next((i for i, p in enumerate(_pts) if p[2]), None)
        if _fo and _fo > 0:
            _oos_y[_fo - 1] = _pts[_fo - 1][1]   # bridge grey line to the in-sample end
        _bg = "#ffffff" if st.session_state.get("active_theme") == "Daylight Glass" else "#0a0c14"
        _tmpl = "plotly_white" if st.session_state.get("active_theme") == "Daylight Glass" else "plotly_dark"
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=_xs, y=_is_y, mode="lines", name="in-sample (initial fit)",
                                 line=dict(color="#46e0b0", width=2), connectgaps=False))
        fig.add_trace(go.Scatter(x=_xs, y=_oos_y, mode="lines", name="walk-forward (unseen)",
                                 line=dict(color="#8a93a8", width=2), connectgaps=True))
        for _bs2, _be2, _fn2, _pf2 in _bands:
            fig.add_vrect(x0=_df.index[max(0, min(_bs2, _nbar - 1))],
                          x1=_df.index[max(0, min(_be2 - 1, _nbar - 1))],
                          fillcolor=("rgba(150,162,196,.16)" if _fn2 % 2 else "rgba(150,162,196,.07)"),
                          line_width=0, annotation_text=f"F{_fn2} · PF {_pf2:.2f}",
                          annotation_position="top left",
                          annotation=dict(font_size=9, font_color="#9aa6d4"))
        if 0 < _oos_start < _nbar:
            fig.add_vline(x=_df.index[_oos_start], line_width=1, line_dash="dot",
                          line_color="rgba(154,166,212,.55)")
        # Overlay each fold's OUT-OF-SAMPLE PNL as a translucent bar sitting in its
        # own window, on a secondary axis — so the "OOS PNL by fold" bars and the
        # equity curve live in ONE chart instead of two.
        _bx, _by, _bc, _bw = [], [], [], []
        for _bs2, _be2, _fn2, _pfx in _bands:
            try:
                _opnl = float(_rs.iloc[_fn2 - 1].get("oos_pnl_usd", 0) or 0)
            except Exception:
                _opnl = 0.0
            _bx.append(_df.index[max(0, min((_bs2 + _be2) // 2, _nbar - 1))])
            _by.append(_opnl)
            _bc.append("#46e0b0" if _opnl > 0 else "#ff6b8e")
            try:
                _bw.append((_df.index[min(_be2 - 1, _nbar - 1)]
                            - _df.index[_bs2]).total_seconds() * 1000 * 0.7)
            except Exception:
                _bw.append(0)
        if _bx and all(_bw):
            fig.add_trace(go.Bar(x=_bx, y=_by, width=_bw, marker_color=_bc, opacity=0.38,
                                 name="OOS PNL / fold", yaxis="y2",
                                 hovertemplate="OOS PNL %{y:$,.0f}<extra></extra>"))
        fig.update_layout(template=_tmpl, paper_bgcolor=_bg, plot_bgcolor=_bg, height=340,
                          margin=dict(t=30, b=8, l=8, r=8), yaxis_title="Cum PNL ($)",
                          yaxis2=dict(title="OOS PNL / fold ($)", overlaying="y", side="right",
                                      showgrid=False, zeroline=False),
                          legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                                      font_size=10, bgcolor="rgba(0,0,0,0)"))
        # ── Optional market benchmark overlay (Results item #2) ──────────────
        # Buy-&-hold SPY/QQQ over the SAME dates, scaled to the dollar notional of
        # one contract (entry price × multiplier), so the gold line answers
        # "did this edge beat just owning the market?" on the same $ axis.
        _bkey = f"wfbench_{meta.get('id', meta.get('strategy','x'))}"
        _bc1, _bc2 = st.columns([1.1, 2.2])
        _bench_on = _bc1.checkbox("Benchmark", key=_bkey + "_on",
                                  help="Overlay SPY/QQQ buy & hold over the same dates, "
                                       "scaled to the notional of 1 contract")
        _bsym = _bc2.radio("idx", ["SPY", "QQQ"], horizontal=True,
                           key=_bkey + "_sym", label_visibility="collapsed")
        if _bench_on:
            try:
                _bnot = float(C[0]) * float(multiplier or 0)
                _d0 = str(pd.to_datetime(_xs[0]).date())
                _d1 = str(pd.to_datetime(_xs[-1]).date())
                # Never fetch while the auto-refresh thread is mid-pull: concurrent
                # yfinance calls contend on its shared session and can stall this
                # WHOLE script run (the deaf-UI hang). Overlay appears next rerun.
                if globals().get("_AR_BG_STATE", {}).get("running"):
                    _bres, _berr = None, "deferred — data auto-refresh in progress"
                else:
                    _bres, _berr = fetch_benchmark_curve(_bsym, _d0, _d1)
                if _bres and _bnot > 0:
                    _bdates, _bpct = _bres
                    _byv = [p * _bnot for p in _bpct]
                    _bfin = _byv[-1] if _byv else 0.0
                    fig.add_trace(go.Scatter(
                        x=_bdates, y=_byv, mode="lines",
                        name=f"{_bsym} buy & hold ({_bpct[-1]*100:+.1f}%)",
                        line=dict(color="#e0b54a", width=1.8, dash="dot"),
                        hovertemplate=_bsym + " %{y:$,.0f}<extra></extra>"))
                    st.caption(f"{_bsym} returned {_bpct[-1]*100:+.1f}% over this window "
                               f"≈ ${_bfin:,.0f} on the same ~${_bnot:,.0f} notional as "
                               f"1 contract.")
                elif _berr:
                    st.caption(f"Benchmark unavailable: {_berr}")
            except Exception as _bex:
                st.caption(f"Benchmark error: {_bex}")
        st.markdown("<div class='sl' style='margin-top:12px'>Walk-forward equity — "
                    "<span style='color:#46e0b0'>in-sample fit</span> then "
                    "<span style='color:#8a93a8'>each fold's unseen window</span> "
                    "· bars = <span style='color:#46e0b0'>OOS PNL</span> per fold "
                    "(right axis)</div>", unsafe_allow_html=True)
        st.plotly_chart(fig, width="stretch")
    except Exception:
        pass


def _render_mc_panel(params_row, meta, multiplier, kp=""):
    """Drawdown MONTE-CARLO for ONE config: re-run it to get the trade list, then
    shuffle the trade ORDER many times to build a distribution of max drawdowns.
    The as-traded drawdown is ONE lucky path through those trades — size to the
    95th percentile of the distribution, not to the path you happened to get."""
    with st.expander("🎲 Drawdown Monte-Carlo (position sizing)", expanded=False):
        st.markdown("<div style='font-size:.74rem;opacity:.6'>Drawdown distribution → "
                    "position sizing"
                    + _hint("Re-runs THIS exact config (net of the same costs), then "
                            "shuffles the order of its trades many times. Total PNL never "
                            "changes — but max drawdown does, a lot. Size your account so "
                            "the 95th-percentile drawdown is survivable, not just the one "
                            "historical path.")
                    + "</div>", unsafe_allow_html=True)
        _c1, _c2, _c3 = st.columns([1.2, 1.2, 1])
        _nsims = _c1.slider("Simulations", 200, 5000, 1000, 100, key=kp + "mc_n")
        _blk = _c2.slider("Block size (trades)", 1, 50, 5, 1, key=kp + "mc_b",
                          help="Shuffle CONSECUTIVE-trade blocks instead of single trades. "
                               "1 = fully random (assumes independent trades — understates "
                               "drawdown because losing streaks cluster in real vol regimes). "
                               "5-20 preserves short streaks; a sterner, more honest test.")
        if not _c3.button("▶ Run Monte-Carlo", key=kp + "mc_go"):
            return
        # ── Load data + strategy exactly like the stress panel ────────────────
        try:
            _metas = load_csv_metas()
        except Exception:
            _metas = None
        _srcn = (meta.get("source_name", "") or "").strip()
        _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            st.error("Couldn't find this run's data source in the Library."); return
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            st.error(f"Couldn't load CSV: {_e}"); return
        _nbars_run = int(meta.get("n_bars", 0) or 0)
        if _nbars_run and len(_df) > _nbars_run:
            _df = _df.iloc[:_nbars_run]          # freeze to the run's original span
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            st.error(f"Strategy '{_sname}' isn't in the Library."); return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            st.error(f"Couldn't load strategy: {_me}"); return
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _params = {}
        for k, v in dict(params_row).items():
            if k in _METR:
                continue
            if isinstance(v, np.integer):    v = int(v)
            elif isinstance(v, np.floating): v = float(v)
            elif isinstance(v, np.bool_):    v = bool(v)
            _params[k] = v
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        _Vmc = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        try:
            _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAYmc = pd.factorize(_eix.dt.date)[0].astype("int64")
        except Exception:
            _DAYmc = None
        try:
            import inspect as _ispm
            _spx = _ispm.signature(_mod.run_backtest).parameters
            _hkx = any(p.kind == p.VAR_KEYWORD for p in _spx.values())
            _xtra = {}
            if _Vmc is not None and (_hkx or "volumes" in _spx):  _xtra["volumes"] = _Vmc
            if _DAYmc is not None and (_hkx or "day_id" in _spx): _xtra["day_id"]  = _DAYmc
        except Exception:
            _xtra = {}
        with st.spinner("Re-running config for its trade list…"):
            try:
                _m = _mod.run_backtest(O, H, L, C, return_trades=True, **_xtra, **_params)
            except Exception as ex:
                st.error(f"Backtest failed: {ex}"); return
        if not _m or not _m.get("trades"):
            st.warning("Config produced no trades on this data."); return
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        pnls = np.array([t[2] for t in _m["trades"]], dtype=float) - _cp
        n_tr = len(pnls)
        usd  = pnls * multiplier

        def _max_dd(arr):
            cum = np.cumsum(arr)
            peak = np.maximum.accumulate(cum)
            return float((cum - peak).min())

        _dd_obs = _max_dd(usd)
        # ── Block-shuffle simulation (seeded → reproducible) ──────────────────
        rng = np.random.default_rng(42)
        _bs = max(1, int(_blk))
        _nblocks = math.ceil(n_tr / _bs)
        _blocks = [usd[i * _bs:(i + 1) * _bs] for i in range(_nblocks)]
        dds = np.empty(int(_nsims))
        with st.spinner(f"Shuffling {n_tr:,} trades × {int(_nsims):,} paths…"):
            for s in range(int(_nsims)):
                order = rng.permutation(_nblocks)
                path = np.concatenate([_blocks[b] for b in order])
                dds[s] = _max_dd(path)
        _pct = {p: float(np.percentile(dds, 100 - p)) for p in (50, 75, 90, 95, 99)}
        _worse = float((dds < _dd_obs).mean() * 100)

        # ── Readout ────────────────────────────────────────────────────────────
        _badge = lambda lbl, v, col: (
            f"<div style='flex:1;min-width:110px;background:var(--s1);border:1px solid "
            f"rgba(255,255,255,.05);border-radius:10px;padding:8px 12px'>"
            f"<div style='font-size:.64rem;text-transform:uppercase;letter-spacing:.08em;"
            f"color:var(--t3)'>{lbl}</div>"
            f"<div style='font-size:1rem;font-weight:800;color:{col}'>${v:,.0f}</div></div>")
        st.markdown(
            "<div style='display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px'>"
            + _badge("as-traded DD", _dd_obs, "var(--t2)")
            + _badge("median sim", _pct[50], "var(--t2)")
            + _badge("p90", _pct[90], "#e0a341")
            + _badge("p95 — size to this", _pct[95], "var(--bad)")
            + _badge("p99", _pct[99], "var(--bad)")
            + "</div>", unsafe_allow_html=True)
        # Three-way verdict. The UNLUCKY case matters most: when the real path is
        # deeper than nearly every shuffle, losses CLUSTER in time (regime streaks)
        # more than reordering reproduces — the simulation then UNDERSTATES risk
        # and the as-traded number (not p95) is the honest sizing floor.
        if _worse > 60:
            _verdict = ("the as-traded path was <b>luckier than typical</b> — most "
                        "random orderings drew deeper. Size to p95, not history.")
            _size_anchor = abs(_pct[95])
        elif _worse >= 25:
            _verdict = "the as-traded path was <b>about typical</b>. Size to p95."
            _size_anchor = abs(_pct[95])
        else:
            _verdict = ("the as-traded path was <b>worse than almost every shuffle</b> "
                        "— your losses cluster in time (losing regimes), which random "
                        "reordering destroys. The simulation UNDERSTATES the real risk: "
                        "size to the as-traded drawdown or deeper, and prefer bigger "
                        "block sizes.")
            _size_anchor = max(abs(_pct[95]), abs(_dd_obs))
        st.markdown(
            f"<div style='font-size:.78rem;opacity:.8;line-height:1.6;margin:6px 0'>"
            f"{_worse:.0f}% of shuffled paths drew down deeper than the historical "
            f"${_dd_obs:,.0f} → {_verdict} "
            f"<b>Sizing rule:</b> if your max tolerable drawdown is X% of the account, "
            f"the account should be at least <b>${_size_anchor:,.0f}</b> ÷ X%. "
            f"E.g. 20% tolerance → ${_size_anchor / 0.20:,.0f} per contract.</div>",
            unsafe_allow_html=True)
        _fig = px.histogram(pd.DataFrame({"maxDD $": dds}), x="maxDD $", nbins=60,
                            color_discrete_sequence=["#8050ff"])
        _fig.add_vline(x=_dd_obs, line_dash="dash", line_color="gold",
                       annotation_text="as-traded")
        _fig.add_vline(x=_pct[95], line_dash="dot", line_color="#e05555",
                       annotation_text="p95")
        _fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(0,0,0,0)", height=240,
                           margin=dict(t=28, b=10), showlegend=False)
        st.plotly_chart(_fig, width="stretch", key=kp + "mc_hist")
        st.caption(f"{int(_nsims):,} paths · block size {_bs} · {n_tr:,} trades · "
                   f"net of ${meta.get('commission_usd', 0)}/RT + "
                   f"{meta.get('slippage_pts', 0)}pt slippage · seed 42 (reproducible). "
                   f"Block size 1 assumes independent trades — real losing streaks "
                   f"cluster, so prefer the block-5+ numbers for sizing.")


def _render_regime_panel(params_row, meta, multiplier, kp=""):
    """REGIME REPORT CARD (TODO #13): replay ONE config, then slice its trades by
    the market conditions on each ENTRY day — volatility tercile, trend-vs-chop,
    day-of-week, and a monthly PnL heatmap. Shows WHEN the edge earns and when it
    bleeds, which is the basis for any regime filter."""
    with st.expander("🌦 Regime report card", expanded=False):
        st.markdown("<div style='font-size:.74rem;opacity:.6'>When does it earn, "
                    "when does it bleed"
                    + _hint("Re-runs this exact config (net of the same costs), then "
                            "groups its trades by the conditions on each entry day: "
                            "volatility tercile (rolling 20-day ATR), trend vs chop "
                            "(20-day efficiency ratio), weekday, and month. Losses "
                            "clustering in one bucket = a candidate regime filter.")
                    + "</div>", unsafe_allow_html=True)
        if not st.button("▶ Build report", key=kp + "rg_go"):
            return
        # ── Load data + strategy (same pattern as the stress/MC panels) ───────
        try:
            _metas = load_csv_metas()
        except Exception:
            _metas = None
        _srcn = (meta.get("source_name", "") or "").strip()
        _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            st.error("Couldn't find this run's data source in the Library."); return
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            st.error(f"Couldn't load CSV: {_e}"); return
        _nbars_run = int(meta.get("n_bars", 0) or 0)
        if _nbars_run and len(_df) > _nbars_run:
            _df = _df.iloc[:_nbars_run]
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            st.error(f"Strategy '{_sname}' isn't in the Library."); return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            st.error(f"Couldn't load strategy: {_me}"); return
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _params = {}
        for k, v in dict(params_row).items():
            if k in _METR:
                continue
            if isinstance(v, np.integer):    v = int(v)
            elif isinstance(v, np.floating): v = float(v)
            elif isinstance(v, np.bool_):    v = bool(v)
            _params[k] = v
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        _Vr = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
        _DAYr = pd.factorize(_eix.dt.date)[0].astype("int64")
        try:
            import inspect as _ispr
            _spx = _ispr.signature(_mod.run_backtest).parameters
            _hkx = any(p.kind == p.VAR_KEYWORD for p in _spx.values())
            _xtra = {}
            if _Vr is not None and (_hkx or "volumes" in _spx):  _xtra["volumes"] = _Vr
            if _hkx or "day_id" in _spx:                          _xtra["day_id"]  = _DAYr
        except Exception:
            _xtra = {}
        with st.spinner("Replaying config + computing regimes…"):
            try:
                _m = _mod.run_backtest(O, H, L, C, return_trades=True, **_xtra, **_params)
            except Exception as ex:
                st.error(f"Backtest failed: {ex}"); return
            if not _m or not _m.get("trades"):
                st.warning("No trades."); return
            _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
                  + float(meta.get("slippage_pts", 0) or 0)

            # ── Daily regime series from the bar data ──────────────────────────
            _dts = _eix.dt.date.values
            _day_df = pd.DataFrame({"d": _dts, "h": H, "l": L, "c": C}).groupby("d").agg(
                hi=("h", "max"), lo=("l", "min"), cl=("c", "last"))
            _day_df["pc"] = _day_df["cl"].shift(1)
            _tr = np.maximum(_day_df["hi"] - _day_df["lo"],
                             np.maximum((_day_df["hi"] - _day_df["pc"]).abs(),
                                        (_day_df["lo"] - _day_df["pc"]).abs()))
            _day_df["atr20"] = _tr.rolling(20).mean()
            # Efficiency ratio: |20d net move| / sum of |daily moves| → 1=trend, 0=chop
            _dmv = _day_df["cl"].diff()
            _day_df["er20"] = (_day_df["cl"].diff(20).abs()
                               / _dmv.abs().rolling(20).sum()).clip(0, 1)
            _q1, _q2 = _day_df["atr20"].quantile([1/3, 2/3])
            _erm = float(_day_df["er20"].median())

            # ── Per-trade buckets (by ENTRY day) ───────────────────────────────
            rows = []
            for (eb, xb, pnl) in _m["trades"]:
                d = _dts[eb]
                drow = _day_df.loc[d] if d in _day_df.index else None
                if drow is None or pd.isna(drow["atr20"]):
                    continue
                usd = (float(pnl) - _cp) * multiplier
                vol_b = ("Low vol" if drow["atr20"] <= _q1
                         else "High vol" if drow["atr20"] > _q2 else "Mid vol")
                tr_b = "Trend" if drow["er20"] > _erm else "Chop"
                ts = _eix.iloc[eb]
                rows.append({"usd": usd, "vol": vol_b, "trend": tr_b,
                             "dow": ts.strftime("%a"), "ym": (ts.year, ts.month)})
            if not rows:
                st.warning("Not enough warm-up history for regime stats."); return
            _t = pd.DataFrame(rows)

            def _bucket_table(col, order):
                g = _t.groupby(col)["usd"]
                out = []
                for b in order:
                    if b not in g.groups:
                        continue
                    v = g.get_group(b)
                    gw = v[v > 0].sum(); gl = -v[v < 0].sum()
                    pf = (gw / gl) if gl > 0 else float("inf")
                    _c = "var(--good)" if v.sum() >= 0 else "var(--bad)"
                    out.append(f"<tr style='border-top:1px solid var(--s1)'>"
                               f"<td style='padding:3px 10px 3px 0;color:var(--t3)'>{b}</td>"
                               f"<td style='padding:3px 10px;text-align:right'>{len(v)}</td>"
                               f"<td style='padding:3px 10px;text-align:right;color:{_c};"
                               f"font-weight:700'>${v.sum():,.0f}</td>"
                               f"<td style='padding:3px 10px;text-align:right'>"
                               f"{min(pf,99):.2f}</td>"
                               f"<td style='padding:3px 10px;text-align:right;opacity:.6'>"
                               f"${v.mean():,.0f}</td></tr>")
                hdr = ("<tr style='color:var(--t4);font-size:.62rem;text-transform:uppercase;"
                       "letter-spacing:.08em'><td></td><td style='text-align:right;padding:0 10px'>T</td>"
                       "<td style='text-align:right;padding:0 10px'>PNL $</td>"
                       "<td style='text-align:right;padding:0 10px'>PF</td>"
                       "<td style='text-align:right;padding:0 10px'>avg $</td></tr>")
                return ("<table style='border-collapse:collapse;font-size:.76rem;margin:2px 0 8px'>"
                        + hdr + "".join(out) + "</table>")

            c1, c2, c3 = st.columns(3)
            c1.markdown("<div class='sl'>Volatility (ATR20 tercile)</div>"
                        + _bucket_table("vol", ["Low vol", "Mid vol", "High vol"]),
                        unsafe_allow_html=True)
            c2.markdown("<div class='sl'>Trend vs chop (ER20)</div>"
                        + _bucket_table("trend", ["Trend", "Chop"]),
                        unsafe_allow_html=True)
            c3.markdown("<div class='sl'>Day of week</div>"
                        + _bucket_table("dow", ["Mon", "Tue", "Wed", "Thu", "Fri"]),
                        unsafe_allow_html=True)

            # ── Monthly PnL heatmap (year × month) ─────────────────────────────
            _t["yr"] = [ym[0] for ym in _t["ym"]]
            _t["mo"] = [ym[1] for ym in _t["ym"]]
            _piv = _t.pivot_table(index="yr", columns="mo", values="usd",
                                  aggfunc="sum").reindex(columns=range(1, 13))
            _fig = px.imshow(_piv, color_continuous_scale="RdYlGn", aspect="auto",
                             color_continuous_midpoint=0,
                             labels=dict(color="PNL $", x="month", y="year"))
            _fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                               height=max(220, 26 * len(_piv) + 80),
                               margin=dict(t=20, b=10))
            st.markdown("<div class='sl' style='margin-top:4px'>Monthly PNL</div>",
                        unsafe_allow_html=True)
            st.plotly_chart(_fig, width="stretch", key=kp + "rg_hm")
            _worst = _t.groupby("vol")["usd"].sum().idxmin()
            st.caption(f"Buckets use each trade's ENTRY day · net of costs · "
                       f"weakest volatility bucket: {_worst}. A filter that skips the "
                       f"bleeding bucket is the natural next experiment.")


def _render_dsr_panel(params_row, meta, multiplier, res, kp=""):
    """DEFLATED SHARPE (TODO #11): is the winner better than the best of N
    configs would look by PURE LUCK? Re-runs the winner + a seeded sample of
    other configs from this run's own grid to estimate the luck bar."""
    with st.expander("🎯 Deflated Sharpe — luck check", expanded=False):
        st.markdown("<div style='font-size:.74rem;opacity:.6'>Does the winner beat "
                    "what best-of-" + f"{int(meta.get('n_combos', 0) or 0):,}"
                    + " luck would produce"
                    + _hint("Try 2,304 coins and one lands 9-of-10 heads — not magic, "
                            "just many tries. This estimates the Sharpe the BEST of N "
                            "skill-less configs would show (from this run's own config "
                            "dispersion, Bailey/Lopez de Prado E[max] formula), then "
                            "asks how confident we are the winner's Sharpe truly beats "
                            "that bar (PSR, adjusted for fat tails/skew). DSR >= 95% "
                            "= the edge survives the multiple-testing haircut.")
                    + "</div>", unsafe_allow_html=True)
        _n_cfg = int(meta.get("n_combos", 0) or 0)
        if _n_cfg < 10 or res is None or len(res) < 5:
            st.caption("Needs a grid/auto run with a config population (N ≥ 10)."); return
        if not st.button("▶ Run luck check", key=kp + "dsr_go"):
            return
        # ── Load data + strategy (standard panel skeleton) ────────────────────
        try:
            _metas = load_csv_metas()
        except Exception:
            _metas = None
        _srcn = (meta.get("source_name", "") or "").strip()
        _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            st.error("Couldn't find this run's data source in the Library."); return
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            st.error(f"Couldn't load CSV: {_e}"); return
        _nbars_run = int(meta.get("n_bars", 0) or 0)
        if _nbars_run and len(_df) > _nbars_run:
            _df = _df.iloc[:_nbars_run]
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            st.error(f"Strategy '{_sname}' isn't in the Library."); return
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            st.error(f"Couldn't load strategy: {_me}"); return
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        _Vd = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
        _DAYd = pd.factorize(_eix.dt.date)[0].astype("int64")
        try:
            import inspect as _ispd
            _spx = _ispd.signature(_mod.run_backtest).parameters
            _hkx = any(p.kind == p.VAR_KEYWORD for p in _spx.values())
            _xtra = {}
            if _Vd is not None and (_hkx or "volumes" in _spx): _xtra["volumes"] = _Vd
            if _hkx or "day_id" in _spx:                        _xtra["day_id"]  = _DAYd
        except Exception:
            _xtra = {}
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        _years = max(0.25, (_eix.iloc[-1] - _eix.iloc[0]).days / 365.25)
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _pcols = [c for c in res.columns if c not in _METR]

        def _clean(d):
            out = {}
            for k, v in d.items():
                if k in _METR or k not in _pcols:
                    continue
                if isinstance(v, np.integer):    v = int(v)
                elif isinstance(v, np.floating): v = float(v)
                elif isinstance(v, np.bool_):    v = bool(v)
                out[k] = v
            return out

        def _ann_sr(params):
            """Annualized per-trade Sharpe (+skew/kurt) for one config, net of costs."""
            try:
                m = _mod.run_backtest(O, H, L, C, return_trades=True, **_xtra, **params)
            except Exception:
                return None
            tl = (m or {}).get("trades") or []
            if len(tl) < 10:
                return None
            p = np.array([t[2] for t in tl], float) - _cp
            sd = p.std(ddof=1)
            if sd <= 0:
                return None
            tpy = len(p) / _years
            sr = (p.mean() / sd) * np.sqrt(tpy)
            z = (p - p.mean()) / sd
            return dict(sr=float(sr), n=len(p),
                        skew=float((z**3).mean()), kurt=float((z**4).mean()))

        _K = min(40, len(res))
        with st.spinner(f"Winner + {_K} sampled configs… (seeded, ~{_K // 4}-{_K // 2}s)"):
            _win = _ann_sr(_clean(dict(params_row)))
            if _win is None:
                st.error("Winner produced too few trades to estimate a Sharpe."); return
            _rng = np.random.default_rng(42)
            _idx = _rng.choice(len(res), size=_K, replace=False)
            _srs = []
            for _i in _idx:
                _r = _ann_sr(_clean(res.iloc[int(_i)].to_dict()))
                if _r is not None:
                    _srs.append(_r["sr"])
        if len(_srs) < 8:
            st.error("Too few sampled configs produced usable Sharpe estimates."); return

        # ── Bailey/Lopez de Prado expected-max under the null ─────────────────
        from scipy import stats as _sst
        _gamma = 0.5772156649
        _vsr = float(np.var(_srs, ddof=1))
        _sr0 = (np.sqrt(_vsr)
                * ((1 - _gamma) * _sst.norm.ppf(1 - 1.0 / _n_cfg)
                   + _gamma * _sst.norm.ppf(1 - 1.0 / (_n_cfg * np.e))))
        # PSR of the winner against the luck bar, non-normality adjusted
        _sr, _T = _win["sr"], _win["n"]
        _tpy = _T / _years
        _sr_t, _sr0_t = _sr / np.sqrt(_tpy), _sr0 / np.sqrt(_tpy)   # per-trade units
        _den = np.sqrt(max(1e-9, 1 - _win["skew"] * _sr_t
                           + ((_win["kurt"] - 1) / 4.0) * _sr_t ** 2))
        _dsr = float(_sst.norm.cdf(((_sr_t - _sr0_t) * np.sqrt(_T - 1)) / _den))

        _ok = _dsr >= 0.95
        _col = "var(--good)" if _ok else ("#e0a341" if _dsr >= 0.80 else "var(--bad)")
        _verdict = ("BEATS the luck bar" if _ok else
                    "uncertain — may not beat luck" if _dsr >= 0.80 else
                    "does NOT beat the luck bar")
        st.markdown(
            f"<div style='display:flex;gap:22px;flex-wrap:wrap;align-items:baseline;"
            f"margin:8px 0 4px;font-size:.88rem'>"
            f"<span><span style='font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;"
            f"color:var(--t4)'>Winner Sharpe</span> <b>{_sr:.2f}</b></span>"
            f"<span><span style='font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;"
            f"color:var(--t4)'>Luck bar (best of {_n_cfg:,})</span> <b>{_sr0:.2f}</b></span>"
            f"<span><span style='font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;"
            f"color:var(--t4)'>Deflated Sharpe</span> "
            f"<b style='color:{_col}'>{_dsr*100:.0f}%</b></span>"
            f"<span style='color:{_col};font-weight:800'>{_verdict}</span></div>"
            f"<div style='font-size:.74rem;opacity:.6;line-height:1.6'>"
            f"Sampled {len(_srs)} configs (seed 42) → cross-config SR spread "
            f"{np.sqrt(_vsr):.2f}. The luck bar is the Sharpe the best of "
            f"{_n_cfg:,} SKILL-LESS configs would be expected to show; the DSR is "
            f"the probability the winner's edge is real after that haircut "
            f"(≥95% = pass; fat-tail/skew adjusted; {_T:,} trades over "
            f"{_years:.1f} yrs).</div>",
            unsafe_allow_html=True)


def _wf_window_stats(best, meta, multiplier, res):
    """Honest Overall / In-sample / Out-of-sample stats (PNL, win rate, profit
    factor, trades, max DD) for a walk-forward run, computed at the TRADE level by
    replaying the fold champions (the same cheap re-runs the equity chart does):
      • In-sample  = fold-1's champion over the initial in-sample window
      • Out-of-sample = each fold's champion over its unseen slice (disjoint)
      • Overall    = both stitched together (matches the equity curve)
    Champions are re-run WITH session id + volume (so VWAP/bias strategies are
    correct). Returns {"overall":d,"is":d,"oos":d} or None if it can't reconstruct."""
    try:
        if not ({"test_bars", "fold"} <= set(res.columns)) or not len(res):
            return None
        _srcn = (meta.get("source_name", "") or "").strip()
        _metas = load_csv_metas(); _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            return None
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            return None
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            return None
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            return None
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        Vv = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        try:
            _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAYf = pd.factorize(_eix.dt.date)[0].astype("int64")
        except Exception:
            _DAYf = None
        try:
            import inspect as _isp
            _spar = _isp.signature(_mod.run_backtest).parameters
            _hk = any(p.kind == p.VAR_KEYWORD for p in _spar.values())
            _wv = (Vv is not None) and (_hk or ("volumes" in _spar))
            _wd = (_DAYf is not None) and (_hk or ("day_id" in _spar))
        except Exception:
            _wv = _wd = False
        _nbar = len(C)
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        def _rp(_r):
            _p = {}
            for k, v in dict(_r).items():
                if k in _METR: continue
                if isinstance(v, np.integer):    v = int(v)
                elif isinstance(v, np.floating):  v = float(v)
                elif isinstance(v, np.bool_):     v = bool(v)
                _p[k] = v
            return _p
        def _seg_trades(_a, _b, _p):
            if _b - _a < 2: return []
            _ex = {}
            if _wv: _ex["volumes"] = Vv[_a:_b]
            if _wd: _ex["day_id"]  = _DAYf[_a:_b]
            try:
                _m = _mod.run_backtest(O[_a:_b], H[_a:_b], L[_a:_b], C[_a:_b],
                                       return_trades=True, **_ex, **_p)
            except Exception:
                return []
            if _cp > 0 and _m:
                _m = _apply_costs(_m, _cp)
            return [float(t[2]) for t in (_m.get("trades") or [])] if _m else []
        def _stats(_tr):
            n = len(_tr)
            if n == 0:
                return {"pnl_usd": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
                        "trades": 0, "dd_usd": 0.0}
            _w = [x for x in _tr if x > 0]; _l = [x for x in _tr if x < 0]
            _gw = sum(_w); _gl = -sum(_l)
            _cum = np.cumsum(_tr); _peak = np.maximum.accumulate(_cum)
            _dd = float((_cum - _peak).min()) * multiplier
            return {"pnl_usd": sum(_tr) * multiplier,
                    "win_rate": 100.0 * len(_w) / n,
                    "profit_factor": (_gw / _gl) if _gl > 1e-9 else (float("inf") if _gw > 0 else 0.0),
                    "trades": n, "dd_usd": _dd}
        _rs = res.sort_values("fold").reset_index(drop=True)
        _sizes = [int(x or 0) for x in _rs["test_bars"].tolist()]
        _oos_start = max(0, _nbar - sum(_sizes))
        _is_tr = _seg_trades(0, _oos_start, _rp(_rs.iloc[0]))
        # Per-fold OOS, computed the SAME way → the matrix, the fold table and the
        # equity curve all agree (one session-aware re-run is the single source).
        _oos_tr, _bs, _per_fold = [], _oos_start, {}
        for _k, _sz in enumerate(_sizes):
            _be = min(_bs + _sz, _nbar)
            _ft = _seg_trades(_bs, _be, _rp(_rs.iloc[_k]))
            _oos_tr += _ft
            _per_fold[int(_rs.iloc[_k].get("fold", _k + 1))] = _stats(_ft)
            _bs = _be
        return {"overall": _stats(_is_tr + _oos_tr),
                "is": _stats(_is_tr), "oos": _stats(_oos_tr),
                "per_fold": _per_fold}
    except Exception:
        return None


def _mx_table(rows):
    """Aligned Overall/IS/OOS × PNL·WR·PF·Trades matrix HTML, shared by the
    walk-forward and Auto/Grid views. PNL and PF are colour-coded by whether they
    pass (PNL > 0, PF ≥ 1). rows = [(label, stats_dict), …]."""
    def _row(_lbl, _d):
        _p = float(_d.get("pnl_usd", 0))
        _pc = "var(--good)" if _p > 0 else ("var(--bad)" if _p < 0 else "var(--t1)")
        _pf = float(_d.get("profit_factor", 0) or 0)
        _pfs = "∞" if (_pf == float("inf") or _pf > 999) else f"{_pf:.2f}"
        _pfc = "var(--good)" if _pf >= 1.0 else "var(--bad)"
        return (f"<div class='mrl'>{_lbl}</div>"
                f"<div class='mcell' style='color:{_pc}'>${_p:,.0f}</div>"
                f"<div class='mcell'>{float(_d.get('win_rate',0)):.1f}%</div>"
                f"<div class='mcell' style='color:{_pfc}'>{_pfs}</div>"
                f"<div class='mcell'>{int(_d.get('trades',0)):,}</div>")
    return ("<div class='mx'><div></div>"
            "<div class='mhd'>PNL</div><div class='mhd'>Win Rate</div>"
            "<div class='mhd'>Profit Factor</div><div class='mhd'>Trades</div>"
            + "".join(_row(_l, _d) for _l, _d in rows) + "</div>")


def _cfg_window_stats(best, meta, multiplier):
    """Overall / In-sample / Out-of-sample trade-level stats for a SINGLE config (an
    Auto/Grid run's best): replay it on the full series, the first AI_OOS_SPLIT
    in-sample slice, and the held-out tail. Session-aware. None if it can't load."""
    try:
        _srcn = (meta.get("source_name", "") or "").strip()
        _metas = load_csv_metas(); _fn = None
        if _metas is not None and len(_metas):
            for r in _metas.to_dict("records"):
                if str(r.get("name", "")).strip() == _srcn:
                    _fn = r.get("filename"); break
        if not _fn:
            return None
        _df, _e = _read_stored_csv(_fn)
        if _df is None:
            return None
        # Freeze the replay to the run's ORIGINAL bar span. Masters auto-refresh
        # (append recent bars), so replaying on the now-larger file produced an
        # Overall PNL/trades that no longer matched the saved headline tile — the
        # "$409,853 tile vs $413,247 matrix" mismatch. Masters are append-only, so
        # the first n_bars rows ARE exactly the data this run saw.
        _nbars_run = int(meta.get("n_bars", 0) or 0)
        if _nbars_run and len(_df) > _nbars_run:
            _df = _df.iloc[:_nbars_run]
        _sname = meta.get("strategy", "") or ""
        _spath = next((s["path"] for s in _list_strategy_files()
                       if s.get("ok") and s.get("name") == _sname), None)
        if not _spath:
            return None
        _mod, _me = _load_strategy_module(_spath)
        if _mod is None:
            return None
        O = _df["Open"].to_numpy(float); H = _df["High"].to_numpy(float)
        L = _df["Low"].to_numpy(float);  C = _df["Close"].to_numpy(float)
        Vv = _df["Volume"].to_numpy(float) if "Volume" in _df.columns else None
        try:
            _eix = pd.to_datetime(pd.Series(_df.index), utc=True).dt.tz_convert("US/Eastern")
            _DAYf = pd.factorize(_eix.dt.date)[0].astype("int64")
        except Exception:
            _DAYf = None
        try:
            import inspect as _isp
            _sp = _isp.signature(_mod.run_backtest).parameters
            _hk = any(p.kind == p.VAR_KEYWORD for p in _sp.values())
            _wv = (Vv is not None) and (_hk or ("volumes" in _sp))
            _wd = (_DAYf is not None) and (_hk or ("day_id" in _sp))
        except Exception:
            _wv = _wd = False
        _n = len(C)
        _cp = ((float(meta.get("commission_usd", 0) or 0) / multiplier) if multiplier else 0.0) \
              + float(meta.get("slippage_pts", 0) or 0)
        _METR = {"total_pnl","num_trades","win_rate","profit_factor","max_drawdown",
                 "avg_pnl","wins","losses","pnl_usd","avg_usd","dd_usd","oos_pnl",
                 "oos_trades","oos_pf","oos_pnl_usd","fold","test_bars","loaded_from_id","_minpf"}
        _p = {}
        for k, v in dict(best).items():
            if k in _METR:
                continue
            if isinstance(v, np.integer):    v = int(v)
            elif isinstance(v, np.floating):  v = float(v)
            elif isinstance(v, np.bool_):     v = bool(v)
            _p[k] = v
        def _seg(_a, _b):
            if _b - _a < 2:
                return []
            _ex = {}
            if _wv: _ex["volumes"] = Vv[_a:_b]
            if _wd: _ex["day_id"]  = _DAYf[_a:_b]
            try:
                _m = _mod.run_backtest(O[_a:_b], H[_a:_b], L[_a:_b], C[_a:_b],
                                       return_trades=True, **_ex, **_p)
            except Exception:
                return []
            if _cp > 0 and _m:
                _m = _apply_costs(_m, _cp)
            return [float(t[2]) for t in (_m.get("trades") or [])] if _m else []
        def _stats(_tr):
            n = len(_tr)
            if n == 0:
                return {"pnl_usd": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "trades": 0, "dd_usd": 0.0}
            _w = [x for x in _tr if x > 0]; _l = [x for x in _tr if x < 0]
            _gw = sum(_w); _gl = -sum(_l)
            _cum = np.cumsum(_tr); _peak = np.maximum.accumulate(_cum)
            return {"pnl_usd": sum(_tr) * multiplier, "win_rate": 100.0 * len(_w) / n,
                    "profit_factor": (_gw / _gl) if _gl > 1e-9 else (float("inf") if _gw > 0 else 0.0),
                    "trades": n, "dd_usd": float((_cum - _peak).min()) * multiplier}
        _split = int(_n * AI_OOS_SPLIT)
        return {"overall": _stats(_seg(0, _n)), "is": _stats(_seg(0, _split)),
                "oos": _stats(_seg(_split, _n)), "split_pct": int(AI_OOS_SPLIT * 100)}
    except Exception:
        return None


def _render_results(_rd, kp=""):
    _rd = st.session_state.results_data
    st.markdown("<div style='font-size:.92rem;font-weight:700;color:var(--accent);"
                "letter-spacing:.02em;padding-bottom:8px;margin-bottom:8px;"
                "border-bottom:1px solid var(--s2)'>◎ Results view</div>",
                unsafe_allow_html=True)
    if _rd is None:
        st.markdown("<div style='text-align:center;padding:48px;opacity:.4'>"
                    "<div style='font-size:2.5rem;margin-bottom:8px'>🔮</div>"
                    "Configure a run in the <b>Executions</b> tab, "
                    "or open a past run from <b>History</b>.</div>",
                    unsafe_allow_html=True)
    else:
        res  = _rd["res"]
        best = pd.Series(_rd["best"])
        meta = _rd["meta"]
        multiplier = _rd.get("multiplier", 1)
        ec   = _rd.get("equity_curves", [])
        bg = "#ffffff" if st.session_state.get("active_theme")=="Daylight Glass" else "#0a0c14"
        _tmpl = "plotly_white" if st.session_state.get("active_theme")=="Daylight Glass" else "plotly_dark"

        # ── Walk-forward view (self-contained; bypasses the per-config layout) ─
        if "fold" in res.columns and len(res):
            _wf_metric = {"total_pnl","num_trades","win_rate","profit_factor",
                          "max_drawdown","avg_pnl","wins","losses","pnl_usd","avg_usd",
                          "dd_usd","oos_pnl","oos_trades","oos_pf","oos_pnl_usd",
                          "fold","test_bars"}
            _pcols = [c for c in res.columns if c not in _wf_metric]
            _pf2 = lambda v: ("∞" if (v == float("inf") or v > 999) else f"{v:.2f}")
            _rid = meta.get("loaded_from_id")
            _ctx = []
            if meta.get("strategy"): _ctx.append(str(meta.get("strategy")))
            _ctx.append(meta.get("instrument","") or "—")
            if meta.get("timeframe"): _ctx.append(str(meta.get("timeframe")))
            _ridtxt = (f"<span style='color:var(--accent);font-weight:800'>Run #{_rid}</span> · "
                       if _rid else "")
            st.markdown(
                f"<div style='font-size:.84rem;font-weight:600;padding-bottom:8px;"
                f"margin-bottom:8px;border-bottom:1px solid var(--s1)'>"
                f"{_ridtxt}🔬 Walk-forward · " + " · ".join(_ctx)
                + _hint("Each fold re-optimized on all data up to its test window, "
                        "then traded the next unseen slice. Out-of-sample PF > 1 "
                        "across folds + stable params = robust; PF that swings or "
                        "drops below 1 = the edge does not generalize.")
                + "</div>", unsafe_allow_html=True)
            # Single source of truth: replay the fold champions ONCE (session-aware).
            # The matrix, the fold table, the robustness read and the equity curve all
            # consume THIS, so no two numbers can disagree (older pre-plumbing runs were
            # scored bias-inert; the replay re-derives them correctly). Falls back to
            # stored aggregates only if the source CSV is gone (_ws is None).
            _ws = _wf_window_stats(best, meta, multiplier, res)
            if _ws and _ws.get("per_fold"):
                # Overwrite the stored per-fold OOS columns with the session-aware
                # replay so EVERY downstream consumer (fold table, drift/PNL charts,
                # the aggregates + verdict below, and the matrix) reads one consistent
                # set of numbers — no split-brain between stored and re-run.
                res = res.copy(); _pfm = _ws["per_fold"]
                for _i in res.index:
                    _pfo = _pfm.get(int(res.at[_i, "fold"]))
                    if _pfo:
                        res.at[_i, "oos_pnl_usd"] = _pfo["pnl_usd"]
                        res.at[_i, "oos_pf"]      = _pfo["profit_factor"]
                        res.at[_i, "oos_trades"]  = _pfo["trades"]
            _nf = len(res)
            _tot_oos = float(res["oos_pnl_usd"].sum())
            _tot_tr  = int(res["oos_trades"].sum())
            _held    = int((res["oos_pf"] > 1.0).sum())
            _avg_is  = float(res["profit_factor"].replace([np.inf,-np.inf], np.nan).mean() or 0)
            _avg_oos = float(res["oos_pf"].replace([np.inf,-np.inf], np.nan).mean() or 0)
            # WF efficiency from the POOLED OOS vs IS profit factor (the matrix
            # numbers) — NOT the per-fold mean, which a thin fold's near-infinite PF
            # would blow up into a meaningless 1000%+.
            if _ws:
                _ip = float(_ws["is"]["profit_factor"]); _op = float(_ws["oos"]["profit_factor"])
                _wfe = (_op / _ip) if (_ip > 0 and np.isfinite(_ip) and np.isfinite(_op)) else 0
            else:
                _wfe = (_avg_oos / _avg_is) if _avg_is else 0
            _thin    = int((res["oos_trades"] < OOS_MIN_TRADES).sum())
            _stable  = sum(1 for c in _pcols if res[c].astype(str).nunique() == 1)
            _is_pnl  = float(_ws["is"]["pnl_usd"]) if _ws else float(best.get("pnl_usd", 0) or 0)
            _ov_dd   = float(_ws["overall"]["dd_usd"]) if _ws else float(best.get("dd_usd", 0) or 0)

            # ══ 1) ONE consolidated verdict strip (verdict + all WF stats inline)
            #      — header above the matrix stays ≤3 rows total.
            if _held == _nf and _nf >= 2:
                _vcol, _vtxt = "var(--good)", f"✓ Held up in all {_nf} folds"
            elif _held == 0:
                _vcol, _vtxt = "var(--bad)", "⚠ Lost OOS in every fold — overfit"
            else:
                _vcol, _vtxt = "#e0a341", f"⚠ Only {_held}/{_nf} folds held up"
            _dl = "font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;color:var(--t4)"
            _thin_chip = (f"<span><span style='{_dl}'>Thin folds</span> "
                          f"<b style='color:#e0a341'>{_thin}/{_nf} ⚠</b></span>" if _thin else "")
            st.markdown(
                "<div style='display:flex;gap:20px;flex-wrap:wrap;align-items:baseline;"
                "margin:2px 0 4px;font-size:.86rem'>"
                f"<span style='color:{_vcol};font-weight:800'>{_vtxt}</span>"
                f"<span><span style='{_dl}'>WF efficiency</span> <b>{_wfe*100:.0f}%</b></span>"
                f"<span><span style='{_dl}'>Max DD</span> <b style='color:var(--bad)'>${_ov_dd:,.0f}</b></span>"
                f"<span><span style='{_dl}'>Stability</span> <b>{_stable}/{len(_pcols)}</b> "
                f"<span style='font-size:.68rem;opacity:.5'>params fixed</span></span>"
                + _thin_chip +
                "</div>", unsafe_allow_html=True)

            # ══ 2) KPI MATRIX — Overall / In-sample / Out-of-sample, aligned ═══
            #      Columns line up (PNL · WR · PF · Trades) so each metric is
            #      directly comparable DOWN the column. Trade-level, computed by
            #      replaying the fold champions session-aware; stored-aggregate
            #      fallback if the source CSV is gone.
            st.markdown("<div class='sl' style='margin:10px 0 4px'>Performance "
                        "<span style='color:var(--t3);font-weight:400'>· overall vs "
                        "in-sample (fitted) vs out-of-sample (the honest test)</span></div>",
                        unsafe_allow_html=True)
            if _ws:
                st.markdown(_mx_table([("Overall", _ws["overall"]),
                                       ("In-sample", _ws["is"]),
                                       ("Out-of-sample", _ws["oos"])]),
                            unsafe_allow_html=True)
            else:
                st.caption("Overall/IS/OOS matrix needs the source CSV (not found) — "
                           "showing stored walk-forward aggregates instead.")
                st.markdown(f"""<div class='kg' style='margin:0 0 8px'>
    <div class='kt'><div class='kl'>Total OOS PNL</div><div class='kv'>${_tot_oos:,.0f}</div>
      <div class='kd km'>{_tot_tr} trades · avg PF {_avg_oos:.2f}</div></div>
    <div class='kt'><div class='kl'>In-sample PNL</div><div class='kv'>${_is_pnl:,.0f}</div>
      <div class='kd km'>{float(best.get('win_rate',0)):.1f}% WR · PF {_pf2(float(best.get('profit_factor',0) or 0))}</div></div>
    </div>""", unsafe_allow_html=True)

            # ══ 3) Visuals — equity, fold table, parameter detail ══════════════
            _render_wf_equity(best, meta, multiplier, res)
            _rows = []
            for _, fr in res.iterrows():
                _oc = "var(--good)" if float(fr.get("oos_pf",0) or 0) >= 1.0 else "var(--bad)"
                _flag = " ⚠" if int(fr.get("oos_trades",0)) < OOS_MIN_TRADES else ""
                _rows.append(
                    f"<tr style='border-top:1px solid var(--s1)'>"
                    f"<td style='padding:5px 8px'>{int(fr['fold'])}</td>"
                    f"<td style='padding:5px 8px'>{int(fr.get('test_bars',0)):,} bars</td>"
                    f"<td style='padding:5px 8px'>{_pf2(float(fr.get('profit_factor',0) or 0))}</td>"
                    f"<td style='padding:5px 8px'>{int(fr.get('num_trades',0))}</td>"
                    f"<td style='padding:5px 8px;color:{_oc};font-weight:700'>{_pf2(float(fr.get('oos_pf',0) or 0))}</td>"
                    f"<td style='padding:5px 8px'>{int(fr.get('oos_trades',0))}{_flag}</td>"
                    f"<td style='padding:5px 8px;color:{_oc}'>${float(fr.get('oos_pnl_usd',0)):,.0f}</td></tr>")
            st.markdown(
                "<table style='width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:8px'>"
                "<thead><tr style='color:var(--t3);text-align:left;font-size:.68rem;"
                "text-transform:uppercase;letter-spacing:.05em'>"
                "<th style='padding:4px 8px'>Fold</th><th style='padding:4px 8px'>Test window</th>"
                "<th style='padding:4px 8px'>IS PF</th><th style='padding:4px 8px'>IS trades</th>"
                "<th style='padding:4px 8px'>OOS PF</th><th style='padding:4px 8px'>OOS trades</th>"
                "<th style='padding:4px 8px'>OOS PNL</th></tr></thead><tbody>"
                + "".join(_rows) + "</tbody></table>", unsafe_allow_html=True)

            # ── Param data inline (parallel-coords drift + per-fold OOS PNL) ──────
            _num_p = [c for c in _pcols
                      if pd.api.types.is_numeric_dtype(res[c]) and res[c].nunique() > 1]
            try:
                # Parallel-coords needs the FULL width or the per-param axes collapse
                # and the labels are unreadable — give it its own row, taller, with
                # generous top/side margins for the axis titles.
                st.markdown("<div class='sl' style='margin-top:6px'>Param drift across folds "
                            "<span style='color:var(--t3);font-weight:400'>· each line = a fold's "
                            "champion, colored by out-of-sample PF</span></div>", unsafe_allow_html=True)
                if len(res) >= 2 and _num_p:
                    _pc = go.Figure(go.Parcoords(
                        line=dict(color=res["oos_pf"].clip(0, 6), colorscale="RdYlGn",
                                  cmin=0, cmax=2.5, showscale=True),
                        dimensions=[dict(label=c[:12], values=res[c]) for c in _num_p + ["oos_pf"]]))
                    _pc.update_layout(template=_tmpl, paper_bgcolor=bg, plot_bgcolor=bg,
                                      height=360, margin=dict(t=58, b=36, l=70, r=70),
                                      font=dict(size=10))
                    st.plotly_chart(_pc, width="stretch")
                else:
                    st.caption("Not enough varying numeric params to chart drift.")
            except Exception:
                pass
            with st.expander("Champion parameters — the config to deploy + every fold's settings"):
                # The config you'd actually trade (latest fold's champion), as copy chips.
                _bp = []
                for c in _pcols:
                    v = best.get(c)
                    if v is None:
                        continue
                    if isinstance(v, (bool, np.bool_)):
                        vs = "✓ on" if v else "✗ off"
                    elif isinstance(v, float):
                        vs = f"{v:g}"
                    else:
                        vs = str(v)
                    _bp.append("<span style='display:inline-flex;flex-direction:column;gap:1px;"
                        "padding:6px 12px;background:var(--s1);border-radius:8px'>"
                        f"<span style='font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;"
                        f"color:var(--t3)'>{c}</span>"
                        f"<span style='font-size:.82rem;font-weight:700;color:var(--accent)'>{vs}</span></span>")
                st.markdown("<div style='margin:2px 0'><span class='sl'>Config to copy</span>"
                            "<span style='font-size:.7rem;color:var(--t3);margin-left:8px'>"
                            "latest fold's winning parameters (what you'd trade next)</span></div>"
                            "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px'>"
                            + "".join(_bp) + "</div>", unsafe_allow_html=True)
                st.markdown("<div class='sl' style='margin-top:4px'>Every fold's champion "
                            "<span style='color:var(--t3);font-weight:400'>· full parameter "
                            "table</span></div>", unsafe_allow_html=True)
                st.dataframe(res[["fold"] + _pcols], width="stretch", hide_index=True)
            _render_retest_panel(best, meta, multiplier, kp=kp+"wf_")
            _render_stress_panel(best, meta, multiplier, kp=kp+"wf_")
            _render_mc_panel(best, meta, multiplier, kp=kp+"wf_")
            _render_regime_panel(best, meta, multiplier, kp=kp+"wf_")
            return

        # Dynamically discover which columns are strategy parameters vs metrics
        METRIC_COLS = {"total_pnl","num_trades","win_rate","profit_factor",
                       "max_drawdown","avg_pnl","wins","losses",
                       "pnl_usd","avg_usd","dd_usd",
                       "oos_pnl","oos_trades","oos_pf","oos_pnl_usd","fold","test_bars"}
        param_cols = [c for c in res.columns if c not in METRIC_COLS]
        # Numeric params only (for charts that need continuous axes)
        num_param_cols = [c for c in param_cols
                          if pd.api.types.is_numeric_dtype(res[c]) and res[c].nunique() > 1]

        days = meta.get("days_in_test",1) or 1
        ppd = best["pnl_usd"]/days

        # ── Context header (clear label · value pairs) ─────────────────────
        _strat = meta.get("strategy","") or ""
        _rid = meta.get("loaded_from_id","")
        def _cx(label,val):
            return (f"<span style='display:inline-flex;align-items:baseline;gap:5px'>"
                    f"<span style='font-size:.72rem;text-transform:uppercase;"
                    f"letter-spacing:.08em;color:var(--t3)'>{label}</span>"
                    f"<span style='font-size:.84rem;font-weight:600;color:var(--t1)'>{val}</span></span>")
        ctx_bits = []
        if _rid: ctx_bits.append(f"<span style='font-size:.84rem;font-weight:700;"
                                 f"color:var(--accent)'>Run #{_rid}</span>")
        if _strat: ctx_bits.append(_cx("Strategy", _strat))
        _srcn = meta.get("source_name","") or ""
        if _srcn: ctx_bits.append(_cx("Source", _srcn))
        ctx_bits.append(_cx("Instrument", meta.get('instrument','') or '—'))
        if meta.get("timeframe"): ctx_bits.append(_cx("TF", meta.get('timeframe')))
        ctx_bits.append(_cx("Period",
            f"{meta.get('date_from','') or '?'} → {meta.get('date_to','') or '?'} "
            f"<span style='opacity:.4;font-weight:400'>({days}d)</span>"))
        ctx_bits.append(_cx("Valid/Total",
            f"{meta.get('n_valid',len(res)):,} / {meta.get('n_combos',0):,}"))
        _cm = float(meta.get("commission_usd", 0) or 0)
        _sl = float(meta.get("slippage_pts", 0) or 0)
        if _cm > 0 or _sl > 0:
            ctx_bits.append("<span style='font-size:.78rem;font-weight:600;"
                f"color:var(--good)'>NET of ${_cm:.2f} + {_sl:g}pt/trade</span>")
        else:
            ctx_bits.append("<span style='font-size:.78rem;font-weight:600;"
                "color:var(--bad)'>GROSS (no costs)</span>")
        st.markdown(
            f"<div style='display:flex;flex-wrap:wrap;gap:8px 22px;align-items:baseline;"
            f"padding-bottom:12px;margin-bottom:12px;border-bottom:1px solid var(--s1)'>"
            + "".join(ctx_bits) + "</div>",
            unsafe_allow_html=True)

        # ── Winner summary (one compact line) ─────────────────────────────
        #   The 6 KPI tiles used to duplicate the All-Results table's top row
        #   (PF / Win% / Trades / MaxDD are all columns there). Collapsed to a
        #   single strip that leads with the winner and keeps the bits the table
        #   doesn't surface up top: PNL/day, days, points, W/L. The per-config
        #   pts / wins / losses now also live IN the table (added below).
        _wl = f"{int(best.get('wins',0))}W / {int(best.get('losses',0))}L"
        st.markdown(
            f"<div style='display:flex;flex-wrap:wrap;gap:6px 22px;align-items:baseline;"
            f"padding:4px 0 12px;margin-bottom:6px;border-bottom:1px solid var(--s1);font-size:.83rem'>"
            f"<span><b style='font-size:1.2rem;color:var(--accent)'>${best.get('pnl_usd',0):,.0f}</b>"
            f"<span style='opacity:.5'> total · {best.get('total_pnl',0):,.0f} pts</span></span>"
            f"<span><b>${ppd:,.0f}</b><span style='opacity:.5'> / day · {days}d</span></span>"
            f"<span>MaxDD <b style='color:var(--bad)'>${best.get('dd_usd',0):,.0f}</b></span>"
            f"<span>WR <b>{best.get('win_rate',0):.1f}%</b><span style='opacity:.5'> · {_wl}</span></span>"
            f"<span style='opacity:.6'>PF {best.get('profit_factor',0):.2f} · "
            f"{int(best.get('num_trades',0))}T · avg ${best.get('avg_usd',0):,.0f}</span>"
            f"</div>",
            unsafe_allow_html=True)

        # ── Overall / In-sample / Out-of-sample matrix (same look as the WF view) ──
        #    Replays the best config on the full series + a 75/25 split. For an
        #    OOS-validated Auto run the tail is a true holdout; for a plain grid the
        #    optimizer saw it all, so we label it honestly as a consistency check.
        _cs = _cfg_window_stats(best, meta, multiplier)
        if _cs and _cs["overall"]["trades"] > 0:
            _was_oos = "oos_pf" in res.columns
            _sp = _cs["split_pct"]
            _is_lbl  = "In-sample"     if _was_oos else f"First {_sp}%"
            _oos_lbl = "Out-of-sample" if _was_oos else f"Last {100-_sp}%"
            _sub = (f"overall vs in-sample ({_sp}%) vs out-of-sample ({100-_sp}%, held out)"
                    if _was_oos else
                    f"best config · first {_sp}% vs last {100-_sp}% — optimizer saw all, "
                    f"so this is a consistency check, not a true holdout")
            st.markdown(f"<div class='sl' style='margin:10px 0 4px'>Performance "
                        f"<span style='color:var(--t3);font-weight:400'>· {_sub}</span></div>",
                        unsafe_allow_html=True)
            st.markdown(_mx_table([("Overall", _cs["overall"]),
                                   (_is_lbl, _cs["is"]),
                                   (_oos_lbl, _cs["oos"])]),
                        unsafe_allow_html=True)

        # Robust config (if found) — set in the OOS block, reused by the "copy
        # these inputs" panel below. Default None so non-OOS runs are unaffected.
        _rob = None; _rob_is_top = False

        # ── Out-of-sample reality check (Auto-Optimize with OOS validation) ─
        #   Robustness is judged on PROFIT FACTOR (scale- and time-independent, so
        #   trade-sparse stretches don't distort it), gated by a minimum number of
        #   out-of-sample trades so a 2-trade fluke can't pose as signal. "Most
        #   robust" = profitable in BOTH windows with enough trades, ranked by its
        #   WORST-window profit factor (consistency, not luck).
        if "oos_pf" in res.columns and len(res):
            _spct = int(AI_OOS_SPLIT * 100)
            _isb = res.iloc[0]
            _is_tr = int(_isb.get("oos_trades", 0))
            _is_ipf = float(_isb.get("profit_factor", 0) or 0)
            _is_opf = float(_isb.get("oos_pf", 0) or 0)
            _cand = res[(res["profit_factor"] > 1.0) & (res["oos_pf"] > 1.0)
                        & (res["oos_trades"] >= OOS_MIN_TRADES)
                        & (res["num_trades"] >= OOS_MIN_TRADES)].copy()
            if len(_cand):
                _cand["_minpf"] = _cand[["profit_factor", "oos_pf"]].min(axis=1)
                _cand = _cand.sort_values("_minpf", ascending=False)
                _rob = _cand.iloc[0]; _rob_is_top = bool(_rob.name == res.index[0])
            else:
                _rob = None; _rob_is_top = False

            def _pf(v):
                try: v = float(v)
                except Exception: return "—"
                return "∞" if (v == float("inf") or v > 999) else f"{v:.2f}"
            def _ocard(title, row, accent):
                _ipf = _pf(row.get("profit_factor", 0)); _opf = _pf(row.get("oos_pf", 0))
                _ip = float(row.get("pnl_usd", 0.0)); _op = float(row.get("oos_pnl_usd", 0.0))
                _oc = "var(--good)" if float(row.get("oos_pf", 0) or 0) >= 1.0 else "var(--bad)"
                return (f"<div style='flex:1 1 260px;min-width:240px;max-width:380px;background:var(--s1);"
                        f"border:1px solid {accent};border-radius:12px;padding:11px 14px'>"
                        f"<div style='font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;"
                        f"color:{accent};font-weight:700;margin-bottom:7px'>{title}</div>"
                        f"<div style='display:flex;gap:18px;flex-wrap:wrap'>"
                        f"<span><span style='font-size:.66rem;color:var(--t3)'>IN-SAMPLE</span><br>"
                        f"<b style='font-size:1rem'>PF {_ipf}</b>"
                        f"<span style='opacity:.55;font-size:.72rem'> · ${_ip:,.0f} · {int(row.get('num_trades',0))}T</span></span>"
                        f"<span><span style='font-size:.66rem;color:var(--t3)'>OUT-OF-SAMPLE</span><br>"
                        f"<b style='font-size:1rem;color:{_oc}'>PF {_opf}</b>"
                        f"<span style='opacity:.55;font-size:.72rem'> · ${_op:,.0f} · {int(row.get('oos_trades',0))}T</span></span>"
                        f"</div></div>")
            st.markdown(
                f"<div style='font-size:.74rem;color:var(--t3);margin:2px 0 7px'>"
                f"◆ Optimized on first {_spct}% · validated on the unseen last "
                f"{100-_spct}% — profit factor is the edge; ≥{OOS_MIN_TRADES} "
                f"out-of-sample trades needed to trust it:</div>"
                f"<div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px'>"
                + _ocard("Top in-sample PNL", _isb, "var(--accent)")
                + ("" if (_rob is None or _rob_is_top)
                   else _ocard("Most robust (profitable in both)", _rob, "#5fb88f"))
                + "</div>", unsafe_allow_html=True)
            # One honest verdict, in priority order.
            if _rob is None:
                st.warning(f"⚠ **No config stayed profitable out-of-sample with ≥"
                           f"{OOS_MIN_TRADES} trades.** Treat every result here as "
                           f"**not validated** — likely overfit, or too little data. "
                           f"(Raise MIN T, widen the date range, or use walk-forward.)")
            elif _rob_is_top:
                st.success("✓ The top in-sample config is also the most robust "
                           "(profitable in both windows with enough trades) — a good sign.")
            elif _is_tr < OOS_MIN_TRADES:
                st.info(f"The top in-sample config made only **{_is_tr}** out-of-sample "
                        f"trade(s) — too few to judge it. A config that *is* robust "
                        f"(green, profitable in both) is shown beside it.")
            elif _is_ipf > 1.0 and _is_opf < 1.0:
                st.warning("⚠ The **top in-sample** config **loses money out-of-sample** "
                           "(PF < 1) — overfit. Prefer the **most robust** config.")
            else:
                st.caption("A different config (green) held up more consistently "
                           "across both windows than the top in-sample PNL.")

        # ── Configuration to copy ─────────────────────────────────────────
        # For an OOS run, the params worth TRADING are the robust config's — NOT
        # the (often overfit) top-in-sample PNL winner. Show those when we have a
        # robust pick; otherwise fall back to the top config.
        _cfg_row = best; _cfg_kind = "top"
        if _rob is not None and not _rob_is_top:
            _cfg_row = _rob; _cfg_kind = "robust"
        _best_pairs = []
        for c in param_cols:
            v = _cfg_row.get(c)
            if v is None:
                continue
            if isinstance(v, float):
                vs = f"{v:g}"
            elif isinstance(v, (bool, np.bool_)):
                vs = "✓ on" if v else "✗ off"
            else:
                vs = str(v)
            _best_pairs.append(
                f"<span style='display:inline-flex;flex-direction:column;gap:1px;"
                f"padding:6px 12px;background:var(--s1);border-radius:8px'>"
                f"<span style='font-size:.7rem;text-transform:uppercase;"
                f"letter-spacing:.06em;color:var(--t3)'>{c}</span>"
                f"<span style='font-size:.82rem;font-weight:700;color:var(--accent)'>{vs}</span>"
                f"</span>")
        _is_auto = str(meta.get("scope","")).lower().startswith("auto")
        if _cfg_kind == "robust":
            _panel_title = "🛡 Most Robust Configuration"
            _panel_hint = ("held up out-of-sample (green card above) — copy THESE, "
                           "not the top-PNL set")
        else:
            _panel_title = ("🏆 Best Configuration Found"
                            if _is_auto else "Best Configuration")
            _panel_hint = "copy these into the strategy's inputs"
        st.markdown(
            f"<div style='margin:4px 0 2px'><span class='sl'>{_panel_title}</span>"
            f"<span style='font-size:.7rem;color:var(--t3);margin-left:8px'>"
            f"{_panel_hint}</span></div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px'>"
            + "".join(_best_pairs) + "</div>",
            unsafe_allow_html=True)
        _render_retest_panel(_cfg_row, meta, multiplier, kp=kp+"gen_")
        _render_stress_panel(_cfg_row, meta, multiplier, kp=kp+"gen_")
        _render_mc_panel(_cfg_row, meta, multiplier, kp=kp+"gen_")
        _render_regime_panel(_cfg_row, meta, multiplier, kp=kp+"gen_")
        _render_dsr_panel(_cfg_row, meta, multiplier, res, kp=kp+"gen_")

        # ── Full results table (all rows, all columns) ────────────────────
        st.markdown(f"<div class='sl' style='margin-top:12px'>All Results "
                    f"({len(res):,} rows)</div>", unsafe_allow_html=True)
        rn = {"pnl_usd":"PNL $","win_rate":"Win%","profit_factor":"PF",
              "num_trades":"Trades","dd_usd":"MaxDD $","avg_usd":"Avg $",
              "total_pnl":"PNL pts","max_drawdown":"DD pts","avg_pnl":"Avg pts",
              "wins":"W","losses":"L"}
        # Include the sub-info that used to live only in the KPI tiles (PNL pts,
        # W/L) so the table is the single source of truth for every config.
        ordered = param_cols + [c for c in ["pnl_usd","total_pnl","win_rate","profit_factor",
                  "num_trades","wins","losses","dd_usd","avg_usd"] if c in res.columns]
        disp = res[ordered].rename(columns=rn)
        fmt_map = {k:v for k,v in
                   {"PNL $":"${:,.0f}","PNL pts":"{:,.0f}","Win%":"{:.1f}","PF":"{:.2f}",
                    "MaxDD $":"${:,.0f}","Avg $":"${:,.0f}"}.items() if k in disp.columns}
        grad = [c for c in ["PNL $","Win%","PF"] if c in disp.columns]

        # Pandas Styler can only render ~262k cells. For large result sets,
        # apply the gradient to just the top rows and show the rest plainly.
        STYLE_CELL_CAP = 250000
        ncells = disp.shape[0] * disp.shape[1]
        if ncells <= STYLE_CELL_CAP:
            styler = disp.style
            for g in grad:
                styler = styler.background_gradient(subset=[g], cmap="RdYlGn")
            styler = styler.format(fmt_map)
            st.dataframe(styler, width="stretch", height=360, hide_index=True)
        else:
            # Gradient just the top slice (best rows), full set shown unstyled below
            top_n = max(1, STYLE_CELL_CAP // max(disp.shape[1],1))
            st.caption(f"Showing gradient styling on the top {top_n:,} rows "
                       f"(table too large to color every cell). "
                       f"Use the CSV export below for all {len(res):,} rows.")
            top_styler = disp.head(top_n).style
            for g in grad:
                top_styler = top_styler.background_gradient(subset=[g], cmap="RdYlGn")
            top_styler = top_styler.format(fmt_map)
            st.dataframe(top_styler, width="stretch", height=360, hide_index=True)

        st.markdown("<div class='sl' style='margin-top:16px'>Charts</div>",
                    unsafe_allow_html=True)
        _html_figs = []

        # ── Equity curves (full width — needs horizontal room) ─────────────
        if ec:
            mx2 = max(1,len(ec))
            ns = 1 if mx2==1 else st.slider("Overlay top N",1,mx2,min(10,mx2),key=kp+"eq_n")
            fig_eq = go.Figure()
            for i,c in enumerate(ec[:ns]):
                fig_eq.add_trace(go.Scatter(x=c["timestamps"],y=c["cum_pnl_usd"],
                    mode="lines",name=c["label"],
                    line=dict(width=3 if i==0 else 1.5, color="#00d4aa" if i==0 else None),
                    hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:,.0f}<extra>%{fullData.name}</extra>"))
            fig_eq.add_hline(y=0,line_dash="dot",line_color="#222")
            fig_eq.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                                  height=360,hovermode="x unified",
                                  legend=dict(orientation="v",x=1.01),margin=dict(t=30))
            st.plotly_chart(fig_eq,width="stretch",key=kp+"c_eq"); _html_figs.append(("Equity",fig_eq))
        else:
            st.caption("No equity-curve data stored for this run.")

        if num_param_cols:
            # ── Parallel coordinates (full width — right after the table) ──
            st.markdown("<div class='sl' style='margin-top:8px'>Parallel Coordinates</div>",
                        unsafe_allow_html=True)
            _sm=max(1,min(2000,len(res)));_sv=min(500,_sm);_sn=min(50,_sm)
            nl=st.slider("Results to plot",_sn,_sm,_sv,max(1,_sm//10),key=kp+"pc_n") if _sn<_sm else _sm
            pc=res.head(nl).copy()
            dim_cols = num_param_cols + [c for c in ["win_rate","pnl_usd"] if c in pc.columns]
            dims=[dict(label=c[:10],values=pc[c],
                       range=[pc[c].min(),pc[c].max()]) for c in dim_cols]
            fig_pc=go.Figure(go.Parcoords(line=dict(color=pc["pnl_usd"],
                colorscale="RdYlGn",showscale=True,
                cmin=pc["pnl_usd"].quantile(.05),cmax=pc["pnl_usd"].quantile(.95),
                colorbar=dict(x=1.06,thickness=12,len=0.9)),
                dimensions=dims))
            # Wider right margin so the colorbar doesn't crowd/clip the last axis,
            # and more bottom room so the axis min-value labels aren't cut off.
            fig_pc.update_layout(template=_tmpl,paper_bgcolor=bg,
                                 height=470,margin=dict(t=70,l=80,r=110,b=55))
            st.plotly_chart(fig_pc,width="stretch",key=kp+"c_pc")
            _html_figs.append(("Parallel",fig_pc))

            # Reserved-height control row keeps paired charts bottom-aligned
            _CTRL = ("<div style='height:30px'></div>")
            PAIR_H = 320

            # ── Row: Correlation | Scatter ────────────────────────────────
            cL2, cR2 = st.columns(2)
            with cL2:
                st.markdown("<div class='sl' style='margin-top:8px'>Correlation with PNL</div>",
                            unsafe_allow_html=True)
                st.markdown(_CTRL, unsafe_allow_html=True)  # spacer to match scatter's selectors
                corr_cols = num_param_cols + ["pnl_usd"]
                cv = res[corr_cols].corr()["pnl_usd"].drop("pnl_usd").sort_values()
                fig_cr = go.Figure(go.Bar(x=cv.values,y=cv.index,orientation="h",
                    marker_color=["#c07070" if v<0 else "#70b080" for v in cv.values],
                    text=[f"{v:+.2f}" for v in cv.values],textposition="outside"))
                fig_cr.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                    xaxis=dict(range=[-1,1]),height=PAIR_H,margin=dict(t=10))
                st.plotly_chart(fig_cr,width="stretch",key=kp+"c_cr")
                _html_figs.append(("Correlations",fig_cr))
            with cR2:
                st.markdown("<div class='sl' style='margin-top:8px'>Scatter</div>",
                            unsafe_allow_html=True)
                xc,yc=st.columns(2)
                xax=xc.selectbox("X",num_param_cols,key=kp+"scx",label_visibility="collapsed")
                y_opts=[c for c in ["win_rate","profit_factor","num_trades","pnl_usd"] if c in res.columns]
                yax=yc.selectbox("Y",y_opts,key=kp+"scy",label_visibility="collapsed")
                fig_sc=px.scatter(res.head(2000),x=xax,y=yax,color="pnl_usd",
                    color_continuous_scale="RdYlGn",
                    hover_data=[c for c in ["pnl_usd","num_trades","win_rate"] if c in res.columns])
                fig_sc.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                                      height=PAIR_H,margin=dict(t=10))
                st.plotly_chart(fig_sc,width="stretch",key=kp+"c_sc")
                _html_figs.append(("Scatter",fig_sc))

            # ── Row: Distribution | Parameter Impact ──────────────────────
            cL, cR = st.columns(2)
            with cL:
                st.markdown("<div class='sl' style='margin-top:8px'>PNL Distribution</div>",
                            unsafe_allow_html=True)
                st.markdown(_CTRL, unsafe_allow_html=True)  # spacer to match impact's selector
                fig_d = px.histogram(res.head(2000),x="pnl_usd",nbins=50,
                    color_discrete_sequence=["#00d4aa"],labels={"pnl_usd":"PNL ($)"})
                # Median + IQR context so you can SEE whether the winner is a modest
                # step above the pack (robust) or a lonely right-tail spike (overfit).
                try:
                    _pv   = pd.to_numeric(res["pnl_usd"], errors="coerce").dropna()
                    _med  = float(_pv.median())
                    _q1   = float(_pv.quantile(0.25)); _q3 = float(_pv.quantile(0.75))
                    fig_d.add_vrect(x0=_q1, x1=_q3, fillcolor="#8888aa", opacity=0.10,
                                    line_width=0)
                    fig_d.add_vline(x=_med, line_dash="dot", line_color="#9aa0b5")
                except Exception:
                    _pv = None
                fig_d.add_vline(x=best["pnl_usd"],line_dash="dash",line_color="gold")
                fig_d.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                                    showlegend=False,height=PAIR_H,margin=dict(t=10))
                st.plotly_chart(fig_d,width="stretch",key=kp+"c_dist")
                _html_figs.append(("Distribution",fig_d))
                # ── Plateau vs isolated-spike readout (overfit tell) ──────────
                try:
                    if _pv is not None and len(_pv) >= 5:
                        _top  = float(best["pnl_usd"])
                        _vals = _pv.sort_values(ascending=False).to_numpy()
                        _second = float(_vals[1]) if len(_vals) > 1 else _top
                        # plateau width = how many configs land within 10% of the top
                        _thr  = _top - 0.10 * abs(_top)
                        _near = int((_pv >= _thr).sum())
                        _pct_near = 100.0 * _near / len(_pv)
                        # gap to #2 as a fraction of the IQR (spike size in pack-units)
                        _iqr  = max(_q3 - _q1, 1e-9)
                        _gap_iqr = (_top - _second) / _iqr
                        if _pct_near >= 5 and _gap_iqr < 0.75:
                            _verdict = ("var(--good)", "PLATEAU",
                                        "winner sits in a cluster of comparable configs — robust")
                        elif _pct_near >= 2 or _gap_iqr < 1.5:
                            _verdict = ("#e0a341", "SOFT PEAK",
                                        "a few neighbours are close — treat with mild caution")
                        else:
                            _verdict = ("var(--err,#e05555)", "ISOLATED SPIKE",
                                        "winner stands alone far past the pack — likely overfit, "
                                        "validate out-of-sample before trusting")
                        st.markdown(
                            f"<div style='font-size:.72rem;line-height:1.5;margin-top:2px'>"
                            f"<span style='color:{_verdict[0]};font-weight:800'>{_verdict[1]}</span> "
                            f"<span style='opacity:.7'>· {_near} of {len(_pv)} configs "
                            f"({_pct_near:.0f}%) within 10% of the top · gap to #2 = "
                            f"{_gap_iqr:.2f}× IQR</span><br>"
                            f"<span style='opacity:.55'>{_verdict[2]}</span></div>",
                            unsafe_allow_html=True)
                except Exception:
                    pass
            with cR:
                st.markdown("<div class='sl' style='margin-top:8px'>Parameter Impact</div>",
                            unsafe_allow_html=True)
                ps = st.selectbox("Parameter", num_param_cols, key=kp+"pi_p",
                                  label_visibility="collapsed")
                grp = res.groupby(ps).agg(avg=("pnl_usd","mean"),
                                          med=("pnl_usd","median")).reset_index()
                fig_pi = go.Figure()
                fig_pi.add_bar(x=grp[ps],y=grp["avg"],name="Avg",
                               marker_color="#00d4aa",opacity=.85)
                fig_pi.add_scatter(x=grp[ps],y=grp["med"],mode="lines+markers",
                                   name="Median",line=dict(color="gold",width=2))
                fig_pi.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                                     height=PAIR_H,margin=dict(t=10),
                                     legend=dict(orientation="h",y=1.12))
                st.plotly_chart(fig_pi,width="stretch",key=kp+"c_pi")
                _html_figs.append(("Impact",fig_pi))

            # ── Neighborhood robustness (TODO #12) — the winner's ±1-step
            #    parameter neighbors, looked up FREE from the existing grid
            #    results. A real optimum sits on high ground: neighbors should
            #    also be profitable. A winner whose neighbor falls off a cliff
            #    is curve-fit luck.
            try:
                _all_pcols = [c for c in res.columns
                              if c not in ("total_pnl","num_trades","win_rate",
                                           "profit_factor","max_drawdown","avg_pnl",
                                           "wins","losses","pnl_usd","avg_usd","dd_usd",
                                           "oos_pnl","oos_trades","oos_pf","oos_pnl_usd",
                                           "fold","test_bars")]
                def _nb_lookup(pcol, val):
                    _m = res
                    for c in _all_pcols:
                        _m = _m[_m[c] == (val if c == pcol else best.get(c))]
                        if _m.empty:
                            return None
                    return _m.iloc[0]
                _nbrows, _nb_good, _nb_tot = [], 0, 0
                for _p in num_param_cols:
                    _vals = sorted(pd.Series(res[_p].dropna().unique()).tolist())
                    if len(_vals) < 2 or best.get(_p) not in _vals:
                        continue
                    _ix = _vals.index(best.get(_p))
                    _cells = []
                    for _off in (-1, +1):
                        _j = _ix + _off
                        if 0 <= _j < len(_vals):
                            _r = _nb_lookup(_p, _vals[_j])
                            if _r is not None:
                                _pfv = float(_r.get("profit_factor", 0) or 0)
                                _nb_tot += 1
                                if _pfv > 1.0:
                                    _nb_good += 1
                                _col = "var(--good)" if _pfv > 1.0 else "var(--bad)"
                                _cells.append((f"{_vals[_j]:g}",
                                               f"<span style='color:{_col}'>{min(_pfv,99):.2f}</span>"))
                            else:
                                _cells.append(("—", "<span style='opacity:.3'>n/a</span>"))
                        else:
                            _cells.append(("·", "<span style='opacity:.3'>edge</span>"))
                    _wpf = float(best.get("profit_factor", 0) or 0)
                    _nbrows.append(
                        f"<tr style='border-top:1px solid var(--s1)'>"
                        f"<td style='padding:3px 10px 3px 0;color:var(--t3)'>{_p.replace('_',' ')}</td>"
                        f"<td style='padding:3px 10px;text-align:center'>{_cells[0][0]}<br>{_cells[0][1]}</td>"
                        f"<td style='padding:3px 10px;text-align:center;background:rgba(255,255,255,.03)'>"
                        f"<b>{best.get(_p):g}</b><br><b style='color:var(--accent)'>{min(_wpf,99):.2f}</b></td>"
                        f"<td style='padding:3px 10px;text-align:center'>{_cells[1][0]}<br>{_cells[1][1]}</td></tr>")
                if _nbrows:
                    _nb_ok = (_nb_good >= _nb_tot * 0.7) if _nb_tot else False
                    _nb_v = ("var(--good)", "HIGH GROUND") if _nb_ok else ("#e0a341", "CHECK NEIGHBORS")
                    st.markdown(
                        "<div class='sl' style='margin-top:10px'>Neighborhood robustness"
                        + _hint("The winner's ±1-step parameter neighbors (profit factor "
                                "shown under each value). A real optimum has profitable "
                                "neighbors — if one step away collapses, the winner is "
                                "likely curve-fit luck. Free lookup from the grid you "
                                "already ran.")
                        + f" <span style='font-size:.7rem;font-weight:800;color:{_nb_v[0]};"
                        f"margin-left:8px'>{_nb_v[1]} · {_nb_good}/{_nb_tot} neighbors "
                        f"profitable</span></div>"
                        "<table style='border-collapse:collapse;font-size:.76rem;margin:4px 0 2px'>"
                        "<tr style='color:var(--t4);font-size:.64rem;text-transform:uppercase;"
                        "letter-spacing:.08em'><td></td><td style='padding:0 10px;text-align:center'>step −</td>"
                        "<td style='padding:0 10px;text-align:center'>winner</td>"
                        "<td style='padding:0 10px;text-align:center'>step +</td></tr>"
                        + "".join(_nbrows) + "</table>", unsafe_allow_html=True)
            except Exception:
                pass

            # ── Heatmap (full width) ──────────────────────────────────────
            if len(num_param_cols) >= 2:
                st.markdown("<div class='sl' style='margin-top:8px'>Heatmap</div>",
                            unsafe_allow_html=True)
                hx2,hy2,_hsp=st.columns([1,1,3])
                hx=hx2.selectbox("Heatmap X",num_param_cols,key=kp+"hmx",index=0,
                                 label_visibility="collapsed")
                hy=hy2.selectbox("Heatmap Y",num_param_cols,key=kp+"hmy",
                                 index=min(1,len(num_param_cols)-1),
                                 label_visibility="collapsed")
                if hx != hy:
                    piv=(res.groupby([hx,hy])["pnl_usd"].mean().reset_index()
                            .pivot(index=hy,columns=hx,values="pnl_usd"))
                    fig_hm=px.imshow(piv,color_continuous_scale="RdYlGn",aspect="auto",
                                     labels=dict(color="Avg PNL $"))
                    fig_hm.update_layout(template=_tmpl,paper_bgcolor=bg,
                                         plot_bgcolor=bg,height=360,margin=dict(t=10))
                    st.plotly_chart(fig_hm,width="stretch",key=kp+"c_hm")
                    _html_figs.append(("Heatmap",fig_hm))
                else:
                    st.caption("Pick two different parameters for the heatmap.")
        else:
            # No swept params — still show distribution full width
            fig_d = px.histogram(res.head(2000),x="pnl_usd",nbins=50,
                color_discrete_sequence=["#00d4aa"],labels={"pnl_usd":"PNL ($)"})
            fig_d.add_vline(x=best["pnl_usd"],line_dash="dash",line_color="gold")
            fig_d.update_layout(template=_tmpl,paper_bgcolor=bg,plot_bgcolor=bg,
                                showlegend=False,height=300,margin=dict(t=20),
                                title="PNL Distribution")
            st.plotly_chart(fig_d,width="stretch",key=kp+"c_dist")
            _html_figs.append(("Distribution",fig_d))
            st.info("Charts that compare parameters need at least one parameter "
                    "that was swept across multiple values.")

        # ── Export ────────────────────────────────────────────────────────
        #   Downloads are now consolidated into the single "⬇ Download" button in
        #   the Past-runs toolbar at the top (one ZIP = report HTML + CSVs + code).
        st.caption("⬇ Download (report · CSVs · code) is the single button in the "
                   "Past-runs toolbar at the top — pick this run there.")


@st.fragment
def _results_tab():
    hdf = load_runs_light()

    # If the most-recent run finished with NO valid combinations, say so plainly
    # at the top of Results. Otherwise the panel below shows the PREVIOUS run (or
    # nothing) and a just-launched run looks like it silently did nothing — which
    # is exactly how the multiprocessing 0-valid bug presented.
    _dn = [e for e in exec_manager.get_all() if e.get("status") == "completed"]
    if _dn and _dn[-1].get("no_results"):
        _lr = _dn[-1]
        st.warning(f"⚠ **{_lr.get('name','Last run')}** finished with "
                   + (_lr.get("no_results_msg")
                      or "0 valid combinations (no parameter set met the "
                         "minimum-trades filter)."))

    # Fallback: if a run just completed and saved to history but nothing is
    # loaded into Results (in-memory exec cleared, or auto-run moved to the next
    # queued run), auto-load the most recent saved run so Results isn't empty.
    if st.session_state.get("results_data") is None and not hdf.empty:
        try:
            _row0 = load_run_by_id(int(hdf.iloc[0]["id"]))
            if _row0.get("full_results"):
                _quick_load_run(_row0)
        except Exception:
            pass

    # ── Past runs: compact scrollable list ────────────────────────────────
    if hdf.empty:
        st.caption("No runs yet. Configure one in the Executions tab.")
    else:
        with st.expander("🕘 Past runs", expanded=True):
            # ── Filters (pivot-table style): narrow by strategy / ticker / TF / scope ──
            def _uvals(col):
                if col not in hdf.columns: return []
                vals = sorted({str(v).strip() for v in hdf[col].tolist()
                               if str(v).strip() and str(v).strip().lower() != "nan"})
                return vals
            _f_strat = _uvals("strategy")
            _f_inst  = _uvals("instrument")
            _f_tf    = _uvals("timeframe")
            _f_scope = _uvals("scope")
            # Filter VALUES are read here (filtering must happen before the table);
            # the filter WIDGETS render in the single toolbar row below, next to the
            # compare/download actions. Changing one reruns, so this reads the latest.
            sel_strat_f = st.session_state.get("hf_strat", [])
            sel_inst_f  = st.session_state.get("hf_inst", [])
            sel_tf_f    = st.session_state.get("hf_tf", [])
            sel_scope_f = st.session_state.get("hf_scope", [])

            # Sort options (incl. star filters) — value read from session state
            # so data prep happens before the table; the widget itself lives in
            # the toolbar row below.
            SORT_OPTS={
                "Newest":("id",False,False),
                "Oldest":("id",True,False),
                "Best PNL":("best_pnl_usd",False,False),
                "Best PF":("best_pf",False,False),
                "⭐ Starred · Newest":("id",False,True),
                "⭐ Starred · Best PNL":("best_pnl_usd",False,True),
            }
            cur_sort=st.session_state.get("h_sort","Newest")
            if cur_sort not in SORT_OPTS: cur_sort="Newest"
            _col,_asc,_star_only=SORT_OPTS[cur_sort]

            fdf=hdf.copy()
            if _star_only: fdf=fdf[fdf["starred"]==1]
            # Apply pivot filters
            if sel_strat_f and "strategy" in fdf.columns:
                fdf=fdf[fdf["strategy"].astype(str).str.strip().isin(sel_strat_f)]
            if sel_inst_f and "instrument" in fdf.columns:
                fdf=fdf[fdf["instrument"].astype(str).str.strip().isin(sel_inst_f)]
            if sel_tf_f and "timeframe" in fdf.columns:
                fdf=fdf[fdf["timeframe"].astype(str).str.strip().isin(sel_tf_f)]
            if sel_scope_f and "scope" in fdf.columns:
                fdf=fdf[fdf["scope"].astype(str).str.strip().isin(sel_scope_f)]
            fdf=fdf.sort_values(_col,ascending=_asc)

            _nshow=len(fdf)
            if _nshow < len(hdf):
                st.caption(f"Showing {_nshow} of {len(hdf)} runs (filtered)")

            LCOLS=["id","starred","timestamp","strategy","source_name","instrument","timeframe","scope",
                   "days_in_test","best_pnl_usd","best_win_rate","best_pf",
                   "best_trades","best_dd_usd","date_from","date_to","elapsed_s"]
            av=[c for c in LCOLS if c in fdf.columns]
            ledger=fdf[av].copy()
            # Robustness Rank (1 = best) — the SAME score the Rankings sub-tab uses
            # (cached per run id; warm once Rankings has been opened).
            try:
                _scored_all = sorted(
                    (s for s in (_scored_run(int(i)) for i in hdf["id"].tolist()) if s),
                    key=lambda s: s.get("score", 0), reverse=True)
                _rank_map = {int(s["id"]): _ri for _ri, s in enumerate(_scored_all, 1)}
            except Exception:
                _rank_map = {}
            if "id" in fdf.columns:
                ledger["Rank"] = [_rank_map.get(int(_id), "") for _id in fdf["id"]]
            # WF detail: held/total folds, only for walk-forward runs (cached per id).
            if {"scope", "id"} <= set(fdf.columns):
                ledger["WF held"] = [
                    _run_wf_summary(int(_id))
                    if ("walk" in str(_sc).lower() or "🔁" in str(_sc)) else ""
                    for _id, _sc in zip(fdf["id"], fdf["scope"])
                ]
            # Equity sparkline per run (downsampled top-config curve; rides on the
            # same _scored_run cache the Rank column already fills).
            if "id" in fdf.columns:
                try:
                    _spark_map = {int(s["id"]): s.get("spark") for s in _scored_all}
                except Exception:
                    _spark_map = {}
                ledger["Equity"] = [_spark_map.get(int(_id)) for _id in fdf["id"]]
            ledger["starred"]=ledger["starred"].apply(lambda v:"⭐" if v else "")
            if "timestamp" in ledger.columns:
                ledger["timestamp"]=ledger["timestamp"].apply(_fmt_date)
            # Library cross-reference numbers: map each run's strategy NAME → its
            # Library master # and its source NAME → the CSV's Library id, so a Past
            # Runs row points back to the exact Library items (all ORB runs share a
            # name, so the # + Source are what actually tell them apart).
            try:
                _strat_num = {str(_sf["name"]): _strategy_master_num(_sf["file"])
                              for _sf in _list_strategy_files()
                              if _sf.get("ok") and _sf.get("name")}
            except Exception:
                _strat_num = {}
            try:
                _csv_num = {}
                _cm = load_csv_metas()
                if _cm is not None and not _cm.empty:
                    for _, _cr in _cm.iterrows():
                        for _key in (_cr.get("name"), _cr.get("filename")):
                            if _key and str(_key) != "nan":
                                _csv_num[str(_key).strip()] = int(_cr.get("id", 0) or 0)
            except Exception:
                _csv_num = {}
            if "strategy" in ledger.columns:
                def _sfmt(x):
                    if not x or str(x) == "nan": return "—"
                    _num = _strat_num.get(str(x))
                    return (f"#{_num} · " if _num else "") + str(x)[:20]
                ledger["strategy"]=ledger["strategy"].apply(_sfmt)
            if "source_name" in ledger.columns:
                def _srcfmt(x):
                    if not x or str(x) == "nan": return "—"
                    _num = _csv_num.get(str(x).strip())
                    return (f"#{_num} · " if _num else "") + str(x)[:18]
                ledger["source_name"]=ledger["source_name"].apply(_srcfmt)
            if "instrument" in ledger.columns:
                ledger["instrument"]=ledger["instrument"].apply(lambda x: str(x).split("–")[0].split("(")[0].strip()[:8] if x else "")
            if "scope" in ledger.columns:
                ledger["scope"]=ledger["scope"].apply(lambda x: str(x).split("(")[0].strip().split()[0] if x else "")
            if "timeframe" in ledger.columns:
                ledger["timeframe"]=ledger["timeframe"].apply(lambda x: str(x).split("(")[0].strip() if x else "")
            if "days_in_test" in ledger.columns:
                ledger["days_in_test"]=ledger["days_in_test"].fillna(0).astype(int)
            if "elapsed_s" in ledger.columns:
                def _fmt_el(v):
                    try: v = float(v or 0)
                    except Exception: return ""
                    if v <= 0: return ""
                    return f"{int(v)}s" if v < 60 else f"{int(v//60)}m {int(v%60)}s"
                ledger["elapsed_s"]=ledger["elapsed_s"].apply(_fmt_el)
            if "date_from" in ledger.columns and "date_to" in ledger.columns:
                ledger["range"]=ledger["date_from"].fillna("")+" -> "+ledger["date_to"].fillna("")
                ledger=ledger.drop(columns=["date_from","date_to"],errors="ignore")

            ledger=ledger.rename(columns={
                "id":"ID","starred":"★","timestamp":"Date","strategy":"Strategy",
                "source_name":"Source",
                "instrument":"Ticker","timeframe":"TF","scope":"Scope","days_in_test":"Days",
                "best_pnl_usd":"PNL $","best_win_rate":"Win%","best_pf":"PF",
                "best_trades":"Trades","best_dd_usd":"MaxDD $","range":"Range",
                "elapsed_s":"Took",
            })
            left_order=["★","Rank","ID","Equity","Date","Range","Took","Days","Ticker","TF","Strategy","Source","Scope","WF held","Trades"]
            metric_order=["PNL $","Win%","PF","MaxDD $"]
            final_order=([c for c in left_order if c in ledger.columns]
                         +[c for c in metric_order if c in ledger.columns])
            final_order+=[c for c in ledger.columns if c not in final_order]
            ledger=ledger[final_order]

            toolbar_slot=st.container(key="hist_toolbar_box")

            # Scrollable table — ~10 rows visible, scroll for the rest
            fmt_dict={"PNL $":"${:,.0f}","Win%":"{:.1f}","PF":"{:.2f}","MaxDD $":"${:,.0f}"}
            grad_cols=[c for c in ["PNL $","Win%","PF"] if c in ledger.columns]
            styler=ledger.style
            for gc in grad_cols:
                styler=styler.background_gradient(subset=[gc],cmap="RdYlGn")
            styler=styler.format({k:v for k,v in fmt_dict.items() if k in ledger.columns})
            ROWS_VISIBLE=12
            _led_rh=_lib_rowh()
            tbl_h=38+min(len(ledger),ROWS_VISIBLE)*_led_rh
            _led_colcfg = {}
            if "Equity" in ledger.columns:
                _led_colcfg["Equity"] = st.column_config.LineChartColumn(
                    "Equity", width="small",
                    help="Top config's equity curve (downsampled)")
            sel=st.dataframe(styler,width="stretch",height=tbl_h,hide_index=True,
                on_select="rerun",selection_mode="single-row",key="h_sel",
                column_config=_led_colcfg or None)

            fresh_rows=sel.get("selection",{}).get("rows",[]) if isinstance(sel,dict) else []
            sel_ids=[int(ledger.iloc[p]["ID"]) for p in fresh_rows if p<len(ledger)]
            # Persist the selection so toolbar button clicks (which trigger a
            # rerun that can clear the dataframe's transient selection) still act
            # on the row the user picked.
            if sel_ids:
                st.session_state["_hist_sel_ids"]=sel_ids
            eff_ids=sel_ids or st.session_state.get("_hist_sel_ids",[])
            ns2=len(eff_ids)

            # Toolbar (renders above table via slot, uses fresh selection)
            with toolbar_slot:
                # ONE row: filters · compare · downloads · star · delete · sort.
                _ff1,_ff2,_ff3,_ff4,a2,a3,a6,a7,a1 = st.columns(
                    [1.3,1.05,0.95,1.05, 1.3,1.5,0.5,0.5,1.25])
                _ff1.multiselect("Strategy", _f_strat, key="hf_strat",
                                 placeholder="All strategies", label_visibility="collapsed")
                _ff2.multiselect("Ticker", _f_inst, key="hf_inst",
                                 placeholder="All tickers", label_visibility="collapsed")
                _ff3.multiselect("Timeframe", _f_tf, key="hf_tf",
                                 placeholder="All TFs", label_visibility="collapsed")
                _ff4.multiselect("Scope", _f_scope, key="hf_scope",
                                 placeholder="All scopes", label_visibility="collapsed")
                _ncmp=len(st.session_state.get("compare_set",set()))
                cmp_c=a2.button(f"⚖️ Cmp ({_ncmp})" if _ncmp else "⚖️ Compare",
                                disabled=(ns2!=1),width="stretch",key="h_cmp",
                                help="Add selected run to Compare set")
                ts_h=datetime.now().strftime("%Y%m%d_%H%M")
                _dl_rd=None
                _code_snap=""
                if ns2==1:
                    try:
                        _full_row=load_run_by_id(eff_ids[0])
                        _dl_rd=_rd_from_run_row(_full_row)
                        _code_snap=_full_row.get("code_snapshot","") or ""
                    except Exception: _dl_rd=None
                # ONE download: a ZIP bundling report.html + all/top-10 CSV + strategy.py
                # (replaces the old Report / CSV / Top10 / Code buttons).
                if _dl_rd is not None:
                    try:
                        a3.download_button("⬇ Download",
                            _build_run_bundle(_dl_rd, _code_snap),
                            f"augur_run{eff_ids[0]}_{ts_h}.zip","application/zip",
                            width="stretch",key="h_dl_zip",
                            help="One ZIP: HTML report (KPIs · top-10 · charts) + full "
                                 "results CSV + top-10 CSV + the exact strategy .py")
                    except Exception:
                        a3.button("⬇ Download",disabled=True,width="stretch",key="h_dl_zip_x")
                else:
                    a3.button("⬇ Download",disabled=True,width="stretch",key="h_dl_zip_d",
                              help="Select one run" if ns2!=1 else "No full results stored")
                star_c=a6.button("⭐",disabled=(ns2==0),width="stretch",key="h_star",help="Star/unstar")
                del_c=a7.button("🗑️",disabled=(ns2==0),width="stretch",key="h_del",help="Delete")
                a1.selectbox("Sort",list(SORT_OPTS.keys()),
                             key="h_sort",label_visibility="collapsed")

            # Confirm-delete
            if st.session_state.get("_hist_del_pending"):
                hd1,hd2,hd3=st.columns([4,1,1])
                pending_ids=st.session_state["_hist_del_pending"]
                hd1.markdown(f"<span style='color:var(--bad);font-size:.82rem;"
                             f"padding-top:6px;display:inline-block'>"
                             f"Delete {len(pending_ids)} run(s)? Cannot be undone.</span>",
                             unsafe_allow_html=True)
                if hd2.button("✓ Delete",key="hist_del_yes",width="stretch"):
                    for i3 in pending_ids:
                        try: delete_run(int(i3))
                        except Exception as _de: st.error(f"Delete failed for #{i3}: {_de}")
                    st.session_state.pop("_hist_del_pending",None)
                    st.session_state.pop("h_sel",None)  # clear stale selection
                    try: st.rerun(scope="app")
                    except TypeError: st.rerun()
                if hd3.button("✕ Cancel",key="hist_del_no",width="stretch"):
                    st.session_state.pop("_hist_del_pending",None)
                    try: st.rerun(scope="app")
                    except TypeError: st.rerun()

            # Handlers
            if cmp_c and eff_ids:
                st.session_state.compare_set.update(eff_ids)
                st.toast(f"Added run #{eff_ids[0]} to Compare "
                         f"({len(st.session_state.compare_set)} total).")
                st.rerun()
            if star_c and eff_ids:
                for i3 in eff_ids: toggle_star(i3)
                st.rerun()
            if del_c and eff_ids:
                st.session_state["_hist_del_pending"]=eff_ids; st.rerun()

            # Selecting a row loads it (single source of truth). No rerun —
            # _render_results below picks it up in the same pass, so the tab
            # selection is never reset.
            if ns2==1:
                cur_loaded=(st.session_state.results_data or {}).get("meta",{}).get("loaded_from_id")
                if cur_loaded != eff_ids[0]:
                    row_in=load_run_by_id(int(eff_ids[0]))
                    if row_in.get("full_results"):
                        _quick_load_run(row_in)
                    else:
                        st.warning("No full results stored for this run (pre v1.9).")

    # ── Selected run's full results — its own tile, spaced from past runs ──
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    with st.container(key="results_box"):
        _render_results(st.session_state.results_data, kp="main_")


# (the Results tab — with its RESULTS + RANKINGS sub-tabs — is rendered further
#  down, once _rankings_tab() is defined.)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: COMPARE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cmp:
    cids = sorted(st.session_state.compare_set)
    if not cids:
        st.markdown("<div style='text-align:center;padding:40px;opacity:.35'>"
                    "Select runs in <b>History</b> -> <b>Compare</b></div>",
                    unsafe_allow_html=True)
    else:
        cb1,cb2=st.columns([5,1])
        cb1.caption(f"Comparing: {', '.join(f'#{i}' for i in cids)}")
        if cb2.button("Clear",width="stretch"):
            st.session_state.compare_set.clear(); st.rerun()
        rows=[load_run_by_id(int(i)) for i in cids]
        mdefs=[("Date",lambda r:_s(r,"timestamp")),("Ticker",lambda r:_s(r,"instrument")),
            ("TF",lambda r:_s(r,"timeframe")),("Days",lambda r:_n(r,"days_in_test","?")),
            ("PNL $",lambda r:f"${_n(r,'best_pnl_usd'):,.0f}"),
            ("PNL/Day $",lambda r:f"${_n(r,'best_pnl_per_day'):,.0f}"),
            ("Win%",lambda r:f"{_n(r,'best_win_rate'):.1f}"),
            ("PF",lambda r:f"{_n(r,'best_pf'):.2f}"),
            ("Trades",lambda r:int(_n(r,'best_trades'))),
            ("MaxDD $",lambda r:f"${_n(r,'best_dd_usd'):,.0f}")]
        for r in rows: r["_p"]=json.loads(r["best_params"]) if r.get("best_params") else {}
        for p in sorted({p for r in rows for p in r["_p"]}):
            mdefs.append((p, lambda r,p=p: r["_p"].get(p,"--")))
        trows=[]
        for nm,fn in mdefs:
            rd={"Metric":nm}
            for r in rows:
                try: rd[f"#{r['id']}"]=fn(r)
                except: rd[f"#{r['id']}"]="--"
            trows.append(rd)
        st.dataframe(pd.DataFrame(trows).set_index("Metric"),width="stretch",height=500)

        bg2="#ffffff" if st.session_state.get("active_theme")=="Daylight Glass" else "#0a0c14"
        _tmpl2 = "plotly_white" if st.session_state.get("active_theme")=="Daylight Glass" else "plotly_dark"
        cd=pd.DataFrame({f"#{r['id']}({_s(r,'instrument','?').split()[0]})":
            [_n(r,"best_pnl_usd"),_n(r,"best_pnl_per_day"),_n(r,"best_win_rate"),
             _n(r,"best_pf"),_n(r,"best_trades")] for r in rows},
            index=["PNL $","PNL/Day $","Win%","PF","Trades"])
        fig_cm=go.Figure()
        for col in cd.columns: fig_cm.add_trace(go.Bar(name=col,x=cd.index,y=cd[col]))
        fig_cm.update_layout(template=_tmpl2,paper_bgcolor=bg2,plot_bgcolor=bg2,
                              barmode="group",height=340,margin=dict(t=20))
        st.plotly_chart(fig_cm,width="stretch")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: RANKINGS
# ══════════════════════════════════════════════════════════════════════════════
# run_id -> scored dict; runs are immutable once saved. PERSISTED to disk so a
# fresh app start doesn't redo ~100 blob decompressions to build the Rank +
# sparkline columns (that was several seconds of every startup's first render).
_SCORED_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "augur_scored_cache.json")
def _load_scored_cache():
    try:
        with open(_SCORED_CACHE_PATH, encoding="utf-8") as _f:
            return {int(k): v for k, v in json.load(_f).items()}
    except Exception:
        return {}
_SCORED_RUN_CACHE = _load_scored_cache()

def _persist_scored_cache():
    try:
        with open(_SCORED_CACHE_PATH, "w", encoding="utf-8") as _f:
            # default=float: score dicts carry numpy scalars, which plain
            # json.dump rejects (and the failure was silently swallowed here).
            json.dump({str(k): v for k, v in _SCORED_RUN_CACHE.items()}, _f,
                      default=float)
    except Exception:
        pass

def _scored_run(run_id: int):
    # Memoized in a plain dict (was @st.cache_data, which never invalidated on
    # relabel/delete — stale Rankings until restart). The dict version is cleared
    # by _bust_db_caches() on every runs-table write, fixing that while keeping
    # the all-runs Rank map a lookup instead of ~100 blob decompressions.
    _hit = _SCORED_RUN_CACHE.get(int(run_id))
    if _hit is not None:
        return _hit
    try:
        row = load_run_by_id(int(run_id))
    except Exception:
        return None
    if not row:
        return None
    fr = None
    try:
        if row.get("full_results"):
            fr = pd.read_json(StringIO(_decompress(row["full_results"])))
    except Exception:
        fr = None
    # Downsampled equity curve (top config) → sparkline column in Past Runs.
    spark = None
    try:
        if row.get("equity_curves_json"):
            _ec0 = json.loads(_decompress(row["equity_curves_json"]))
            if _ec0:
                _y = _ec0[0].get("cum_pnl_usd") or []
                if len(_y) > 4:
                    _stp = max(1, len(_y) // 40)
                    spark = [float(v) for v in _y[::_stp]][:40]
    except Exception:
        spark = None
    sc = _run_robustness_score(row, fr)
    out = {**sc, "spark": spark, "id": int(run_id),
           "instrument": str(row.get("instrument") or "?"),
           "timeframe": str(row.get("timeframe") or "?"),
           "strategy": str(row.get("strategy") or ""),
           "scope": str(row.get("scope") or ""),
           "pnl_usd": float(row.get("best_pnl_usd") or 0),
           "days": int(float(row.get("days_in_test") or 0)),
           "date": str(row.get("timestamp") or "")[:10],
           "source": str(row.get("source_name") or row.get("data_source") or "")}
    _SCORED_RUN_CACHE[int(run_id)] = out
    # Batched persist (every 10th entry) — a write per entry would make OneDrive
    # re-sync the file ~100x during the first cold build. Stragglers just get
    # recomputed next start.
    if len(_SCORED_RUN_CACHE) % 10 == 0:
        _persist_scored_cache()
    return out

def _rank_group(inst, tf):
    """Normalised market key so all 'ES …' / 'ES – S&P 500 …' runs group together and
    'Nm (… max on Yahoo)' timeframes collapse to 'Nm' — fixes the fragmented groups."""
    import re as _re
    _m = _re.match(r'[A-Za-z0-9]+', str(inst or "").strip())
    _i = _m.group(0).upper() if _m else "?"
    _t = str(tf or "").split("(")[0].strip().split()
    return f"{_i} · {_t[0] if _t else '?'}"

def _rankings_tab():
    st.markdown("<div class='sl'>◆ Rankings — by out-of-sample robustness</div>",
                unsafe_allow_html=True)
    st.caption("Every run scored 0–100 on how well it holds up on UNSEEN data — walk-forward "
               "beats a single 75/25 split beats unvalidated; thin trade counts and "
               "in-sample↔out-of-sample gaps are penalised. Net PNL is secondary by design, "
               "so an overfit money-maker still ranks low. Hover any column header (ⓘ) for what it means.")
    _lr = load_runs_light()
    if _lr is None or _lr.empty:
        st.info("No runs yet — run an optimization first.")
    else:
        _scored = [s for s in (_scored_run(int(i)) for i in _lr["id"].tolist()) if s]
        _sdf = pd.DataFrame(_scored)
        _sdf["group"] = _sdf.apply(lambda r: _rank_group(r["instrument"], r["timeframe"]), axis=1)
        _groups = ["🏆 Master (all)"] + sorted(_sdf["group"].unique().tolist())
        _gsel = st.radio("Leaderboard", _groups, horizontal=True, key="_rank_group")
        _view = (_sdf if _gsel.startswith("🏆")
                 else _sdf[_sdf["group"] == _gsel]).sort_values("score", ascending=False)
        _bk = {"walk-forward": "🔬 WF", "out-of-sample": "OOS", "unvalidated": "⚠ none"}
        _TIP = {
          "Score": "0–100 overall. Rewards out-of-sample robustness; penalises thin trade counts, in-sample↔out-of-sample gaps, and no validation.",
          "Validated": "How it was checked on unseen data — WF = walk-forward (X/Y folds held); OOS = single 75/25 split; none = not validated (don't trust it).",
          "IS/OOS PF": "Profit factor in-sample / out-of-sample. A big drop from IS to OOS means overfitting.",
          "Days": "Calendar days of data tested. Few days = unreliable — a candidate to delete below.",
          "Trades": "Trades behind the result. More = more statistically reliable.",
          "Net PNL": "Best config's profit after commission + slippage. Secondary to robustness by design.",
          "Market": "Instrument + timeframe, with sources combined (e.g. all ES 5-minute runs together).",
        }
        def _th(lbl):
            tip = _TIP.get(lbl, "")
            return (f"<th style='padding:5px 8px' title=\"{tip}\">{lbl}"
                    + ("<span style='opacity:.45'> ⓘ</span>" if tip else "") + "</th>")
        _rh = []
        for _rank, (_, r) in enumerate(_view.head(40).iterrows(), 1):
            _sc = int(r["score"])
            _col = "var(--good)" if _sc >= 60 else "var(--warn)" if _sc >= 35 else "var(--bad)"
            _oos = (f"{r['oos_pf']:.2f}" if r["oos_pf"] is not None else "—")
            _wf = (f" {int(r['held'])}/{int(r['nfold'])}f" if pd.notna(r.get("nfold")) else "")
            _nm = (r["strategy"] or r["scope"] or "")[:22]
            _dys = int(r.get("days", 0) or 0)
            _dcol = "var(--bad)" if _dys < 5 else "var(--t3)"
            _rh.append(
                f"<tr style='border-top:1px solid var(--s1)'>"
                f"<td style='padding:6px 8px;color:var(--t3)'>{_rank}</td>"
                f"<td style='padding:6px 8px'><b>#{int(r['id'])}</b> "
                f"<span style='color:var(--t3);font-size:.72rem'>{_nm}</span></td>"
                f"<td style='padding:6px 8px;font-size:.74rem;color:var(--t3)'>{r['group']}</td>"
                f"<td style='padding:6px 8px;font-size:.72rem;color:var(--t3)'>{r.get('date','')}</td>"
                f"<td style='padding:6px 8px;font-size:.78rem;color:{_dcol}'>{_dys}d</td>"
                f"<td style='padding:6px 8px;font-size:.74rem'>{_bk.get(r['kind'], r['kind'])}{_wf}</td>"
                f"<td style='padding:6px 8px;font-size:.8rem'>{r['is_pf']:.2f} / {_oos}</td>"
                f"<td style='padding:6px 8px;color:var(--t3);font-size:.8rem'>{int(r['trades'])}T</td>"
                f"<td style='padding:6px 8px;font-size:.8rem'>${r['pnl_usd']:,.0f}</td>"
                f"<td style='padding:6px 8px'><b style='color:{_col};font-size:1.05rem'>{_sc}</b></td></tr>")
        st.markdown(
            "<table style='width:100%;border-collapse:collapse'>"
            "<thead><tr style='color:var(--t3);text-transform:uppercase;font-size:.62rem;letter-spacing:.05em'>"
            + _th("#") + _th("Run") + _th("Market") + _th("Date") + _th("Days")
            + _th("Validated") + _th("IS/OOS PF") + _th("Trades") + _th("Net PNL") + _th("Score")
            + "</tr></thead><tbody>" + "".join(_rh) + "</tbody></table>", unsafe_allow_html=True)

        # ── Open a run in Results, or delete junk runs ────────────────────────
        _ids = _view["id"].tolist()
        if _ids:
            _sby = dict(zip(_view["id"], _view["score"]))
            _dby = dict(zip(_view["id"], _view["days"]))
            mc1, mc2, mc3 = st.columns([3, 1, 1])
            _pick = mc1.selectbox(
                "Open or delete a run", _ids,
                format_func=lambda i: f"#{int(i)} · {int(_sby.get(i, 0))} pts · {int(_dby.get(i, 0))}d",
                key="_rank_pick")
            if mc2.button("📂 Open in Results", key="_rank_open", width="stretch"):
                _rrow = load_run_by_id(int(_pick))
                _rd = _rd_from_run_row(_rrow) if _rrow else None
                if _rd:
                    st.session_state.results_data = _rd
                    st.session_state["_hist_sel_ids"] = [int(_pick)]
                    st.toast(f"Loaded #{int(_pick)} → open the Results tab.")
                else:
                    st.warning("That run has no stored results to open.")
            if mc3.button("🗑 Delete", key="_rank_del", width="stretch"):
                st.session_state["_rank_del_confirm"] = int(_pick)
            if st.session_state.get("_rank_del_confirm") in _ids:
                _did = int(st.session_state["_rank_del_confirm"])
                d1, d2, d3 = st.columns([3, 1, 1])
                d1.warning(f"Permanently delete run #{_did}?")
                if d2.button("✓ Delete", key="_rank_del_yes", width="stretch"):
                    delete_run(_did)
                    st.session_state.pop("_rank_del_confirm", None)
                    try: _scored_run.clear()
                    except Exception: pass
                    st.toast(f"Deleted #{_did}."); st.rerun()
                if d3.button("✕ Cancel", key="_rank_del_no", width="stretch"):
                    st.session_state.pop("_rank_del_confirm", None); st.rerun()
        st.caption("⚠ none = unvalidated (don't trust). 🔬 WF with most folds held = gold standard. "
                   "Few-day runs (red) are cleanup candidates — pick one above and Delete.")


# ── Results tab: RESULTS + RANKINGS sub-tabs (Rankings is now a sub-tab here,
#    like CSV DATA sits under Library — not a top-level tab). ──────────────────
with tab_results:
    _rt_main, _rt_rank = st.tabs(["RESULTS", "RANKINGS"])
    with _rt_main:
        _results_tab()
    with _rt_rank:
        _rankings_tab()


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_set:
    with st.container(key="tilebox_set1"):
        st.markdown("<div class='sl'>Theme</div>",unsafe_allow_html=True)
        cur=st.session_state.get("active_theme","Vapor Glass")
        new_t=st.radio("theme",list(THEMES.keys()),
            index=list(THEMES.keys()).index(cur),
            horizontal=True, key="theme_r", label_visibility="collapsed")
        st.markdown(f"<div style='opacity:.4;font-size:.74rem;margin-top:-4px'>"
                    f"{THEMES.get(new_t,'')}</div>", unsafe_allow_html=True)
        if new_t != cur:
            st.session_state["active_theme"]=new_t
            cfp=os.path.join(os.path.dirname(DB_PATH),"augur_config.json")
            try:
                ex2={}
                if os.path.exists(cfp):
                    with open(cfp,encoding="utf-8") as f: ex2=json.load(f)
                ex2["theme"]=new_t
                with open(cfp,"w",encoding="utf-8") as f: json.dump(ex2,f,indent=2)
            except: pass
            st.rerun()

    # ── Anthropic API key (permanent home for AI features) ───────────────
    with st.container(key="tilebox_set2"):
        st.markdown("<div class='sl'>Anthropic API key · AI features</div>",
                    unsafe_allow_html=True)
        _saved_key = _load_config_json().get("anthropic_key", "")
        _key_in = st.text_input(
            "API key", value=_saved_key, type="password", key="settings_api_key",
            placeholder="sk-ant-…",
            help="Stored locally in augur_config.json. Used by AI Optimize / AI "
                 "Evolve and the Pine→Python translator, so you don't re-enter it.")
        if _key_in != _saved_key:
            cfp = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
            try:
                ex4 = {}
                if os.path.exists(cfp):
                    with open(cfp, encoding="utf-8") as f: ex4 = json.load(f)
                ex4["anthropic_key"] = _key_in
                with open(cfp, "w", encoding="utf-8") as f: json.dump(ex4, f, indent=2)
                st.toast("API key saved")
            except Exception as _ke:
                st.caption(f"Couldn't save key: {_ke}")
        if _saved_key:
            st.markdown("<div style='font-size:.74rem;color:var(--good);margin-top:2px'>"
                        "✓ Key saved — AI features and the translator will use it "
                        "automatically.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='font-size:.74rem;opacity:.5;margin-top:2px'>"
                        "Get a key at console.anthropic.com. Each AI round and each "
                        "translation makes one API call.</div>", unsafe_allow_html=True)

    # ── Interface ─────────────────────────────────────────────────────────
    with st.container(key="tilebox_set3"):
        st.markdown("<div class='sl'>Interface</div>", unsafe_allow_html=True)
        _dlabels = {0: "Comfortable", 1: "Compact", 2: "Ultra"}
        _dsel = st.segmented_control(
            "Table density", [0, 1, 2], format_func=lambda i: _dlabels[i],
            key="_lib_density", selection_mode="single",
            help="Row height for the Library + Past Runs tables. Ultra fits ~50% "
                 "more rows per screen.")
        if _dsel is None:
            # Deselect mid-click wrote None into the widget key; fall back to the
            # persisted value. (The top-of-script seed repairs the session key on
            # the next run — we can't write a widget key after it rendered.)
            try:
                _dsel = int(_load_config_json().get("ui_density", 1))
            except (TypeError, ValueError):
                _dsel = 1
        st.session_state["_lib_compact"] = (_dsel >= 1)
        try:
            _cfgp = os.path.join(os.path.dirname(DB_PATH), "augur_config.json")
            _cfg_ui = _load_config_json()
            if int(_cfg_ui.get("ui_density", 1)) != int(_dsel):
                _cfg_ui["ui_density"] = int(_dsel)
                with open(_cfgp, "w") as _f:
                    json.dump(_cfg_ui, _f, indent=2)
        except Exception:
            pass

    # ── Performance / parallelism ────────────────────────────────────────
    with st.container(key="tilebox_set4"):
        st.markdown("<div class='sl'>Performance · CPU cores</div>", unsafe_allow_html=True)
        _cur_w = int(st.session_state.get("cfg_workers",
                     st.session_state.get("_saved_workers", DEFAULT_WORKERS)))
        _cur_w = min(max(1, _cur_w), MAX_SELECTABLE_WORKERS)
        new_w = st.slider("Parallel workers", 1, MAX_SELECTABLE_WORKERS, _cur_w, 1,
                          key="cfg_workers",
                          help="CPU cores for GRID sweeps of 200+ combinations. More = faster "
                               "grids (near-linear), warmer machine. Auto/Walk-Forward stay "
                               "single-core by design (sequential Bayesian search, seed 42).")
        st.markdown(
            f"<div style='opacity:.55;font-size:.74rem;margin-top:-2px;line-height:1.6'>"
            f"Detected <b>{_CPU_LOGICAL}</b> logical processors · recommended "
            f"<b>{DEFAULT_WORKERS}</b> (leaves headroom). Applies to grid scopes with "
            f"≥200 combos via isolated worker processes; smaller grids and "
            f"Auto/Walk-Forward run single-core (sequential by design).</div>",
            unsafe_allow_html=True)
        # Persist worker choice to config json
        if new_w != int(st.session_state.get("_saved_workers", DEFAULT_WORKERS)):
            st.session_state["_saved_workers"] = new_w
            cfp=os.path.join(os.path.dirname(DB_PATH),"augur_config.json")
            try:
                ex3={}
                if os.path.exists(cfp):
                    with open(cfp,encoding="utf-8") as f: ex3=json.load(f)
                ex3["workers"]=new_w
                with open(cfp,"w",encoding="utf-8") as f: json.dump(ex3,f,indent=2)
            except: pass

    # ── Auto-refresh data (Tier 1: on app open) ──────────────────────────
    with st.container(key="tilebox_set5"):
        st.markdown("<div class='sl'>Auto-refresh data · on app open</div>",
                    unsafe_allow_html=True)
        _ar = _get_autorefresh_cfg()
        _ar_global = st.checkbox("Enable auto-refresh", value=bool(_ar.get("enabled_global")),
            key="ar_global",
            help="When you open Augur, enabled masters below auto-update: Yahoo "
                 "masters pull recent bars; TradingView masters ingest any matching "
                 "CSVs you've dropped in the watch folder. You'll see a summary of "
                 "what changed.")
        st.markdown(
            f"<div style='opacity:.45;font-size:.73rem;line-height:1.6;margin:-2px 0 8px'>"
            f"📂 Drop TradingView exports into <b>augur_watch/</b> — filenames must "
            f"contain the instrument + timeframe (e.g. <code>ES_5m_jan.csv</code>). "
            f"Ingested files move to augur_watch/_ingested/. "
            f"Yahoo intraday history is shallow (~7d for 1–5m), so refresh keeps a "
            f"rolling recent window current.</div>",
            unsafe_allow_html=True)

        _masters_df = list_masters()
        _ar_masters = dict(_ar.get("masters", {}))
        if _masters_df.empty:
            st.caption("No master CSVs yet. Build one in Library → Combine into Master CSV.")
        else:
            st.markdown("<div style='font-size:.73rem;text-transform:uppercase;"
                        "letter-spacing:.08em;color:var(--t3);margin:2px 0 4px'>"
                        "Per-master toggles</div>", unsafe_allow_html=True)
            _changed = False
            for _, mr in _masters_df.iterrows():
                inst = str(mr.get("instrument","")).strip()
                tf   = str(mr.get("timeframe","")).strip()
                src  = str(mr.get("source","tv")).strip()
                key  = _ar_key(inst, tf, src)
                # Use the master's own display name so this list matches the
                # Library/CSV table exactly (incl. "- no-adj", RTH/ETH, etc.).
                _nm = str(mr.get("name","") or f"{inst} {tf}").strip()
                cur = bool(_ar_masters.get(key, False))
                new = st.checkbox(
                    f"{_nm}  ({int(mr.get('rows',0)):,} rows)",
                    value=cur, key=f"ar_m_{key}", disabled=not _ar_global)
                if new != cur:
                    _ar_masters[key] = new
                    _changed = True
            if _changed or (_ar_global != bool(_ar.get("enabled_global"))):
                _ar["enabled_global"] = bool(_ar_global)
                _ar["masters"] = _ar_masters
                _save_autorefresh_cfg(_ar)

        # Manual "refresh now" button
        if not _masters_df.empty and st.button("🔄 Refresh enabled masters now",
                                               key="ar_now", width="stretch",
                                               disabled=not _ar_global):
            with st.spinner("Refreshing…"):
                _res = auto_refresh_masters()
            if _res:
                for r in _res:
                    (st.success if r.startswith("✓") else st.caption)(r)
            else:
                st.caption("Nothing new to add (already current, or no matching watch files).")

    st.markdown(f"<div style='opacity:.35;font-size:.74rem;line-height:1.7;padding:4px 4px 0'>"
                f"<b>Augur v{__version__}</b> · {HISTORY_CAP} run cap · "
                f"augur_strategies/ · augur_uploads/ · augur_watch/ · augur_config.json</div>",
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_ref:
    st.markdown("<div class='sl'>Signal Logic</div>",unsafe_allow_html=True)
    st.code("""
# 1. TREND:     red_count / lookback  >=  min_red_dominance
# 2. MOMENTUM:  close > open  (green candle)
# 3. SIZE:      body >= min_breakout_pts  (or % if use_percent)
# 4. CONTRAST:  prior candle bodies <= max_body_ratio x breakout body
#
# Entry  : close
# Stop   : entry - body
# Target : entry + body x rr_input
# BE     : after be_bars bars -> move stop to entry
""",language="python")

    st.markdown("<div class='sl' style='margin-top:16px'>Yahoo Data Limits</div>",unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([["1m","7d"],["5m","60d"],["15m","60d"],["1h","2yr"],["1d","5yr"]],
        columns=["TF","Max"]),width="stretch",hide_index=True,height=220)

    st.markdown("<div class='sl' style='margin-top:16px'>About</div>",unsafe_allow_html=True)
    st.markdown("*Augur* — Roman priests who read signs to predict outcomes. "
                "This tool reads price data to find optimal strategy parameters.")

    # ── Backtesting maturity roadmap (the expert-level TODO, in plain English) ──
    with st.container(key="tilebox_ref_roadmap"):
        st.markdown("<div class='sl'>Backtesting maturity roadmap</div>",
                    unsafe_allow_html=True)
        st.markdown("""
<div style='font-size:.8rem;line-height:1.75;opacity:.92'>
The checklist of research-grade upgrades, from the standard texts (Pardo, Aronson,
López de Prado, Bandy, Chan). Numbers match the project TODO list (CLAUDE.md). <b style='color:var(--good)'>✓ done</b> ·
<b style='color:#e0a341'>◐ partial</b> · <b style='opacity:.6'>○ planned</b><br><br>

<b style='color:var(--good)'>✓ #7 Walk-forward validation</b> — re-optimize on a growing
window, test each next unseen slice. <i>Like studying from last year's exams, then
sitting THIS year's exam — repeatedly.</i><br>

<b style='color:var(--good)'>✓ #3 Out-of-sample split (Auto)</b> — tune on the first 75%,
grade on the last 25% the optimizer never saw.<br>

<b style='color:var(--good)'>✓ #15a Drawdown Monte-Carlo (shuffle)</b> — shuffle your trades' order
1,000s of times to see how deep the dips COULD have been. <i>Same cards, different
shuffle: how bad can a cold streak get?</i><br>

<b style='color:var(--good)'>✓ #12 Neighborhood robustness</b> — check the winner's
next-door parameter settings. <i>A real hilltop has high ground around it; if one
step away falls off a cliff, you found luck, not an edge.</i><br>

<b style='color:#e0a341'>◐ #21 Realistic stop fills</b> — stops that gap through now fill
at the open (done); next: slippage that scales with how fast the market is moving.<br>

<b style='color:#e0a341'>◐ #20 Live-vs-backtest drift</b> — paper trading (starting via
the TradingView Pine port) gives real fills to compare against the engine's
predictions. <i>Does practice match the textbook?</i><br>

<b style='color:var(--good)'>✓ #11 Deflated Sharpe (multiple-testing haircut)</b> — if you try
2,304 settings, the best one looks great partly by LUCK. <i>Flip 2,304 coins ten
times each: one coin lands 9 heads — is it magic? No, you just tried a lot of
coins. This computes how good the best-of-N should look by pure chance, and only
believes results that beat that bar.</i><br>

<b style='color:var(--good)'>✓ #13 Regime report card</b> — split results by market
mood: volatile vs calm, trending vs choppy, by month/weekday (🌦 expander in Results).
<i>Shows exactly WHEN the strategy bleeds, so a filter can skip those conditions.</i><br>

<b style='opacity:.6'>○ #14 MAE/MFE distributions</b> — for every trade, how far it went
AGAINST you before resolving (MAE) and how far in your favor (MFE). <i>If 80% of
winners never dipped more than 5 points against you, a 6-point stop keeps the
winners and cuts the losers — placement from evidence, not guessing.</i><br>

<b style='opacity:.6'>○ #15b Risk-of-ruin + bootstrap MC</b> — given your account size and per-trade
risk, the probability you hit zero (or your quit-point) before the edge pays.
<i>Even a winning game bankrupts you if you bet too big per hand.</i><br>

<b style='opacity:.6'>○ #16 Vol-targeted sizing</b> — trade smaller when the market is
wild, bigger when calm, so every trade risks the same $ amount.<br>

<b style='opacity:.6'>○ #19 Lockbox holdout</b> — seal away the most recent year of
data; NEVER optimize or even look at it. One final test before going live.
<i>The exam stays sealed until exam day — peek once and it can never be a fair
test again.</i><br>

<b style='opacity:.6'>○ #18 Event-day tagging</b> — mark FOMC/CPI/NFP days; report
results with and without them (news days behave differently).<br>

<b style='opacity:.6'>○ #17 Half-day calendar</b> — Thanksgiving/Christmas-eve sessions
close at 1pm ET; "exit at close" math is subtly wrong on those days.<br>

<b style='opacity:.6'>○ #22 Capacity check</b> — how many contracts can the strategy
trade before its own orders move the price.<br>

<b style='opacity:.6'>○ #23 Order-flow enrichment (Databento)</b> — add WHO was hitting
the bid/ask: per-bar buy-volume minus sell-volume (delta) from exchange trade data.
<i>The bar chart shows the score; order flow shows who's actually pushing. The volume
filter was ORB's best lever — delta is its sharper sibling.</i><br>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TAB: RESEARCH  — analytical WF studies run outside the UI (Claude / scripts)
# ══════════════════════════════════════════════════════════════════════════════
_RESEARCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "augur_research")

def _load_research_files():
    if not os.path.isdir(_RESEARCH_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(_RESEARCH_DIR) if f.endswith(".json")],
        reverse=True
    )
    return files

def _render_research_study(data):
    import plotly.graph_objects as go

    meta = data.get("meta", {})
    runs = data.get("runs", [])

    # Meta header
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.caption(f"**Script** {meta.get('script','–')}")
    col_m2.caption(f"**Date** {meta.get('run_date','–')}")
    col_m3.caption(f"**Trials/fold** {meta.get('n_trials','–')}  ·  **Folds** {meta.get('n_folds','–')}  ·  **Init** {int(meta.get('init_frac',0)*100)}%")

    for run in runs:
        label    = run.get("label","")
        held     = run.get("total_held", 0)
        total_f  = run.get("total_folds", 0)
        oos_usd  = run.get("total_oos_usd", 0)
        folds    = run.get("folds", [])
        per_year = run.get("per_year", {})
        mult     = run.get("mult", 1)
        sign      = "+" if oos_usd >= 0 else ""
        held_col  = "var(--accent)" if held >= total_f * 0.6 else ("#e0a341" if held >= total_f * 0.4 else "var(--err,#e05555)")
        pnl_col   = "var(--accent)" if oos_usd >= 0 else "var(--err,#e05555)"

        st.markdown(
            f"<div class='tile' style='margin-top:14px'>"
            f"<div style='display:flex;align-items:baseline;gap:16px;margin-bottom:10px'>"
            f"<span style='font-size:.85rem;font-weight:700;color:var(--t1)'>{label}</span>"
            f"<span style='font-size:.78rem;color:{held_col};font-weight:600'>{held}/{total_f} folds held</span>"
            f"<span style='font-size:.78rem;color:var(--t2)'>Total OOS</span>"
            f"<span style='font-size:.88rem;font-weight:700;color:{pnl_col}'>"
            f"${sign}{oos_usd:,.0f}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

        # Fold table
        if folds:
            fold_rows = []
            for fd in folds:
                mark = "✓" if fd.get("held") else "✗"
                fold_rows.append({
                    "Fold": fd.get("fold",""),
                    "OOS Period": fd.get("yr_label",""),
                    "IS PF": round(fd.get("is_pf",0),2),
                    "IS T": fd.get("is_t",0),
                    "OOS PF": round(fd.get("oos_pf",0),2),
                    "OOS T": fd.get("oos_t",0),
                    "OOS $": f"${fd.get('oos_usd',0):+,.0f}",
                    "": mark,
                })
            st.dataframe(
                pd.DataFrame(fold_rows),
                hide_index=True,
                height=min(35 * len(fold_rows) + 38, 280),
                width="stretch",
            )

        # Per-year table + equity chart side by side
        if per_year:
            yr_col, eq_col = st.columns([1, 2])
            with yr_col:
                st.caption("Per-year OOS")
                yr_rows = []
                for yr in sorted(per_year.keys()):
                    v = per_year[yr]
                    pnl  = v[0] if isinstance(v, list) else v.get("pnl_usd", 0)
                    trds = v[1] if isinstance(v, list) else v.get("trades", 0)
                    yr_rows.append({
                        "Year": int(yr),
                        "Trades": int(trds),
                        "PNL $": f"${pnl:+,.0f}",
                        "": "+" if pnl >= 0 else "–",
                    })
                st.dataframe(pd.DataFrame(yr_rows), hide_index=True,
                             height=min(35*len(yr_rows)+38, 460),
                             width="stretch")

            with eq_col:
                # Build cumulative OOS equity from fold trade lists if available
                all_trades = []
                for fd in folds:
                    tlist = fd.get("trades", [])
                    for t in tlist:
                        all_trades.append(t[2] * mult)  # pnl_pts * mult
                if all_trades:
                    cum = [0.0]
                    for p in all_trades:
                        cum.append(cum[-1] + p)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        y=cum, mode="lines",
                        line=dict(color="#7eb8f7", width=1.5),
                        name="OOS equity"
                    ))
                    fig.add_hline(y=0, line_color="rgba(255,255,255,.2)", line_width=1)
                    fig.update_layout(
                        height=220, margin=dict(l=0,r=0,t=20,b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#c8cdd5",
                        showlegend=False,
                        xaxis=dict(showgrid=False, zeroline=False, title="Trade #"),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,.06)",
                                   zeroline=False, title="Cumul. $"),
                    )
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.caption("*(equity curve available on future runs — trade data not captured in this study)*")

        st.markdown("</div>", unsafe_allow_html=True)

with tab_research:
    @st.fragment
    def _render_research_tab():
        st.markdown("<div class='sl'>Research Studies</div>", unsafe_allow_html=True)
        st.caption("Walk-forward analyses and other studies run outside the UI. "
                   "Zero impact on Past Runs or the execution pipeline — read-only.")

        os.makedirs(_RESEARCH_DIR, exist_ok=True)
        files = _load_research_files()

        if not files:
            st.info("No research studies yet. Run `python tools/wf_vwap.py` to generate the first one — "
                    "results will appear here automatically.")
        else:
            sel = st.selectbox(
                "Study", files,
                format_func=lambda f: f.replace(".json","").replace("_"," "),
                label_visibility="collapsed",
            )
            if sel:
                try:
                    import json as _json
                    with open(os.path.join(_RESEARCH_DIR, sel)) as _f:
                        data = _json.load(_f)
                    _render_research_study(data)
                except Exception as _e:
                    st.error(f"Could not load {sel}: {_e}")

    _render_research_tab()
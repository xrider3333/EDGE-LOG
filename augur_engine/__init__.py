"""augur_engine — streamlit-free backtest engine for AUGUR.

The callable core, extracted so a web frontend (EDGELOG) and a job runner can drive
backtests WITHOUT importing the Streamlit app. It reuses the SAME assets the app
uses — strategy plugins in augur_strategies/, master CSVs in augur_uploads/, and the
SQLite history (optimizer_history.db) — but imports NO streamlit, so it runs cleanly
under FastAPI / a background runner / a notebook.

This is step 1 of the EDGELOG split (see docs/EDGELOG_ARCHITECTURE.md): a parallel,
non-breaking engine package. optimizer.py (the Streamlit app) is untouched and keeps
working exactly as before; later steps can point it at this package too.

Quick use:
    from augur_engine import run_backtest, list_strategies, list_masters
    r = run_backtest("ORB_SIMPLE_1_0.py", instrument="NQ", timeframe="5m",
                     session="rth", params={"vol_filter": 1.5})
    print(r["total_pnl"], r["profit_factor"], r["num_trades"])
"""
from .strategies import list_strategies, load_strategy, strategy_params
from .data import list_masters, find_master, load_master_arrays
from .engine import run_backtest
from .history import list_runs, get_run
from .optimize import run_grid, list_presets, expand_grid
from .auto import run_auto
from .validate import run_validate
from .analytics import monte_carlo_drawdown, deflated_sharpe, annualized_sr
from .ai import ai_optimize, ai_evolve, validate_strategy_code, call_llm

__all__ = ["list_strategies", "load_strategy", "strategy_params",
           "list_masters", "find_master", "load_master_arrays", "run_backtest",
           "list_runs", "get_run", "run_grid", "run_auto", "run_validate",
           "list_presets", "expand_grid",
           "monte_carlo_drawdown", "deflated_sharpe", "annualized_sr",
           "ai_optimize", "ai_evolve", "validate_strategy_code", "call_llm"]
__version__ = "0.1.0"

"""FastAPI server exposing the AUGUR backtest engine over HTTP.

Endpoints:
  GET  /health                 — liveness + engine version
  GET  /strategies             — available plugins [{file,name,num}]
  GET  /strategies/{file}/params — a strategy's DEFAULT_PARAMS
  GET  /masters                — registered master CSVs (trimmed)
  POST /backtest               — run one backtest, return metrics

Compute runs locally (this PC). The EDGELOG web frontend / local job-runner are the
intended callers. CORS is open for local dev; tighten allow_origins for deployment.

Run:  pip install fastapi uvicorn
      uvicorn api.server:app --reload --port 8787
"""
from typing import Optional, Dict, Any

import math
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import augur_engine as ae

app = FastAPI(title="AUGUR engine API", version=ae.__version__)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _clean(o):
    """JSON-safe: numpy scalars -> python, NaN/inf -> None, recurse dict/list/tuple."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    return o


@app.get("/health")
def health():
    return {"ok": True, "engine": ae.__version__}


@app.get("/strategies")
def strategies():
    return ae.list_strategies()


@app.get("/strategies/{file}/params")
def strategy_params(file: str):
    try:
        mod = ae.load_strategy(file)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _clean(ae.strategy_params(mod))


@app.get("/masters")
def masters():
    keep = ("name", "instrument", "timeframe", "session", "source",
            "rows", "date_from", "date_to")
    return [{k: m.get(k) for k in keep} for m in ae.list_masters()]


class BacktestRequest(BaseModel):
    strategy: str
    instrument: Optional[str] = None
    timeframe: str = "5m"
    session: str = "rth"
    source: Optional[str] = None
    params: Dict[str, Any] = {}
    cost_pts: float = 0.0
    return_trades: bool = False


@app.post("/backtest")
def backtest(req: BacktestRequest):
    try:
        r = ae.run_backtest(
            req.strategy, instrument=req.instrument, timeframe=req.timeframe,
            session=req.session, source=req.source, params=req.params,
            cost_pts=req.cost_pts, return_trades=req.return_trades)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    if r is None:
        raise HTTPException(status_code=422,
                            detail="no result (0 trades or invalid window)")
    return _clean(r)

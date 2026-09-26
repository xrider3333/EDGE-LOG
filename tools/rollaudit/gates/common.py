"""Shared helpers for the gate/roll measurement. READ-ONLY research script.

Run everything with OMP_NUM_THREADS=1 set in the environment before python starts.
"""
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "rollaudit"))

import numpy as np
import pandas as pd
import joblib

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import entry_features_causal, _make_model, gate_trades
from augur_engine.analytics import sortino_from_pnls, sharpe_from_pnls
from api import paper
import rollaudit_lib as RL

ARTIFACT_DIR = r"C:\EdgeLog\gate_models"
NQ_MULT = 20.0

LEGS = {
    "NOISE_H_RF": dict(key="NOISE_H_RF"),
    "ENGUQ_ER_H": dict(key="ENGUQ_ER_H"),
}

# The two undocumented 2026 in-bar splices (ROLL_AUDIT.md 6.3) -- NOT in
# tools/data/contract_switches_NQ.csv (only 64 databento_raw rows, through 2026-03-16).
SPLICE_TIMES_ET = [
    pd.Timestamp("2026-06-15 03:30:00", tz="US/Eastern"),
    pd.Timestamp("2026-09-14 11:30:00", tz="US/Eastern"),
]
SPLICE_DAYS_ET = [pd.Timestamp(t.date()) for t in SPLICE_TIMES_ET]


def leg_config(key):
    for l in paper.PAPER_LEGS:
        if l["key"] == key:
            return l
    raise KeyError(key)


def load_raw_arrays(leg):
    master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
    assert master is not None, f"no master for {leg}"
    arrays = load_master_arrays(master, date_from=leg.get("history_from"), date_to=None)
    return arrays, master


def get_trades(leg, arrays):
    res = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                       cost_pts=leg.get("cost_pts", 0.0), return_trades=True)
    T = sorted([tuple(t) for t in (res.get("trades") or [])], key=lambda t: t[0])
    return T, res


def fit_artifact_model(leg, arrays, trades, seed):
    """Mirrors api.gate_live._build_artifact's single fit exactly."""
    F, names = entry_features_causal(arrays)
    E = np.array([int(t[0]) for t in trades])
    P = np.array([float(t[2]) for t in trades], float)
    y = (P > 0).astype(int)
    X = F[np.clip(E, 0, len(F) - 1)]
    g = leg["gate"]
    mdl = _make_model(g["model"], int(seed))
    mdl.fit(X, y, clf__sample_weight=np.abs(P) + 1e-9)
    return mdl, X, y, P, names


def splice_bar_indices(index):
    """Nearest bar index at/after each undocumented 2026 splice instant."""
    idx = pd.DatetimeIndex(index)
    out = []
    for t in SPLICE_TIMES_ET:
        pos = idx.searchsorted(t)
        out.append(int(min(pos, len(idx) - 1)))
    return out


def mask_splice_trades(trades, index):
    """Trades that SPAN or ENTER ON the two undocumented 2026 splice bars/days.
    'span' = entry bar time < splice instant <= exit bar time.
    'enters on' = the trade's entry falls on the splice's ET calendar date.
    Returns (kept_trades, masked_trades)."""
    idx = pd.DatetimeIndex(index)
    kept, masked = [], []
    for t in trades:
        e, x = int(t[0]), int(t[1])
        e = min(e, len(idx) - 1); x = min(x, len(idx) - 1)
        et_entry = idx[e]
        et_exit = idx[x]
        bad = False
        for splice_t, splice_day in zip(SPLICE_TIMES_ET, SPLICE_DAYS_ET):
            spans = (et_entry < splice_t) and (et_exit >= splice_t)
            enters_on = pd.Timestamp(et_entry.date()) == splice_day
            if spans or enters_on:
                bad = True
                break
        (masked if bad else kept).append(t)
    return kept, masked


def corrected_trades_and_features(leg, raw_arrays, raw_trades):
    """(ii) roll-corrected view: features from RL.adjusted_arrays; trade pnls with
    stitch points removed; the two undocumented 2026 splice trades masked out."""
    adj_arrays = RL.adjusted_arrays(raw_arrays, "NQ")
    stitch = RL.stitch_points(raw_trades, raw_arrays["index"], "NQ")
    corrected = []
    for t, s in zip(raw_trades, stitch):
        t = list(t)
        t[2] = float(t[2]) - float(s)
        corrected.append(tuple(t))
    kept, masked = mask_splice_trades(corrected, raw_arrays["index"])
    return adj_arrays, kept, masked, stitch


def yrs_between(t0, t1):
    return (pd.Timestamp(t1) - pd.Timestamp(t0)).total_seconds() / (365.25 * 86400.0)


def stats_block(pnls_pts, mult=NQ_MULT, years=None):
    p = np.asarray(pnls_pts, float)
    n = len(p)
    if n == 0:
        return dict(n=0, net_usd=0.0, max_dd_usd=0.0, roc_pct_yr=None, sortino=None)
    usd = p * mult
    cum = np.cumsum(usd)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float((cum - peak).min())
    net = float(usd.sum())
    roc = None
    if years and years > 0:
        roc = (net / years) / 100000.0 * 100.0
    sortino = sortino_from_pnls(list(usd), years) if years else None
    return dict(n=n, net_usd=net, max_dd_usd=dd, roc_pct_yr=roc, sortino=sortino)

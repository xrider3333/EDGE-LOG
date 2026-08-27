"""
ORB 3.4 + EFFICIENCY FLOOR — the #230 crown config with the Kaufman efficiency-ratio
gate that run #265 validated on ENGU-Q and that transferred to ES (STUDIES row 345).

Gate: the efficiency ratio of the last `er_len` five-minute closes (net move divided by
path travelled) taken on the bar STRICTLY BEFORE the entry bar must be at least `er_th`.
er_th 0 = gate off = bit-exact #230 (the parity anchor).

Legality of the wrapper approach: ORB takes at most ONE trade per session (first signal,
no re-entry) and is flat at the close, so dropping a session's trade cannot change any
other session's trade — filtering the base engine's trade list on a causal entry-bar
feature is PATH-EXACT, not an approximation. Causality: the ER uses closes up to
entry_idx - 1 only; the entry itself is C221's bar-close decision.

Research provenance (tools/orb_er_gate_test.py, pre-registered 2026-08-23): primary cell
er12/0.25 PF 1.263→1.385, eras 3/4, DD $35,474→$27,083, lockbox (12mo to 2026-08-13)
$64,575/PF 1.31 → $88,246/PF 1.74 on 123 trades. Broad plateau on er_len 6-12.
"""
import numpy as np
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_4_C221.py")
_spec = _ilu.spec_from_file_location("_orb34_c221_er", _SRC)
_c221 = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_c221)

STRATEGY_NAME = "ORB 3.4 · #230 + efficiency floor"
DESCRIPTION = ("The #230 crown (OR 2, first-candle dir, close-confirmed) taking a session's "
               "trade only when the prior hour moved efficiently (Kaufman ER of the last "
               "er_len 5m closes, prior bar, >= er_th). er_th 0 = exact #230.")
VERSION = "1.0"
TIMEFRAME = "5m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_4_C221.py"

DEFAULT_PARAMS = dict(_c221.DEFAULT_PARAMS)
DEFAULT_PARAMS["er_len"] = {"default": 12, "min": 4, "max": 30, "step": 2, "type": "int",
                            "label": "Efficiency window (5m bars)",
                            "tooltip": "Bars in the Kaufman efficiency ratio (net move / path "
                                       "travelled), computed on the bar before entry. 12 = one hour."}
DEFAULT_PARAMS["er_th"] = {"default": 0.25, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
                           "label": "Efficiency floor (0 = off)",
                           "tooltip": "Skip the session's trade when the prior-bar efficiency "
                                      "ratio is below this. 0 disables the gate (= exact #230)."}


# The base engine takes a FIXED keyword list -- it has no **kw of its own (ORB_3_4.run_backtest,
# which ORB_3_4_C221 re-exports unchanged). This wrapper DOES have **kw, and augur_engine picks
# which "extras" to hand a strategy by inspecting its signature: a **kw catch-all reads as
# "accepts anything", so the engine passes `index` (the bar timestamps) to every such strategy.
# Forwarding **kw straight through therefore died with
#   TypeError: run_backtest() got an unexpected keyword argument 'index'
# on every CI run from 2026-08-26 on. It never showed up locally because the contract tests are
# the only caller that supplies an index -- a normal backtest or sweep passes none.
#
# Filter to what the base actually accepts, read off the base's OWN signature rather than a
# hand-kept list, so a new base parameter needs no edit here and a removed one cannot resurrect
# this bug. Deliberately general rather than a one-off `kw.pop('index')`: the next extra the
# engine learns to pass would otherwise land in exactly the same trap.
_BASE_SIG = _inspect.signature(_c221.run_backtest).parameters
_BASE_TAKES_KW = any(p.kind == p.VAR_KEYWORD for p in _BASE_SIG.values())


def _base_kw(kw):
    """Only the keywords the base engine can actually receive."""
    if _BASE_TAKES_KW:
        return kw
    return {k: v for k, v in kw.items() if k in _BASE_SIG}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 er_len: int = 12, er_th: float = 0.25,
                 return_trades: bool = False, **kw):
    res = _c221.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                             return_trades=True, **_base_kw(kw))
    if res is None:
        return None
    trades = res["trades"]
    if float(er_th) > 0 and trades:
        c = np.asarray(closes, float)
        L = int(er_len)
        chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
        ad = np.abs(np.diff(c, prepend=c[0]))
        cs = np.cumsum(ad)
        vs = cs - np.concatenate([np.zeros(L), cs[:-L]])
        er = np.nan_to_num(np.where(vs > 0, chg / np.maximum(vs, 1e-9), 0.0))
        trades = [t for t in trades if er[max(int(t[0]) - 1, 0)] >= float(er_th)]
    pnls = np.array([t[2] for t in trades], float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum) if len(cum) else np.array([])
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()) if len(pnls) else 0.0,
        "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trades
    return out

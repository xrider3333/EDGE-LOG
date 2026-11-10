"""MISC EODREV 1.0 - end-of-day reversal across 50 megacap stocks, as one plugin file.

# AUGUR-SOURCE: claude

Provenance: C:/EdgeLog/_anatomy_cache/opus_hunt1109 (s6, s13, s14; prereg + addenda 1-4 in
C:/EdgeLog/manager/prereg/PREREG_opus_xs_intraday_r1_2026-11-09.md). Parity-checked day for
day against that harness (tools/misc_eodrev_parity.py).

-- The rule -----------------------------------------------------------------------------
Each regular session, at 15:20 ET, every name with a prior RAW close >= `min_price` is ranked
on  (15:20 price / prior 15:50 close - 1)  minus  beta x SPY's same move
(`beta_adjust` off -> minus SPY's move, i.e. beta 1 for every name).
At 15:30 buy the `k` weakest and short the `k` strongest, equal dollars a name; every
position leaves at the official closing print (market-on-close).

INFORMATION TIMES (all known before the 15:30 entry):
  * the ranking uses the close of the 10-minute bar that starts 15:10 (= the 15:20 price);
  * beta = slope of the name's daily return on SPY's over the prior `beta_len` sessions,
    15:50-to-15:50 closes, ENDING THE SESSION BEFORE (shifted one day), clipped 0.3..2.5,
    1.0 until two thirds of the window exists;
  * the price floor reads YESTERDAY's raw close.
The exit print (official close) and the entry print (15:30 open) are fills, never inputs.

-- Data ---------------------------------------------------------------------------------
THE MASTER IS ONLY THE CLOCK (SPY 5m RTH): it gives the sessions and the bar numbers of each
trade. Prices of the 50 names come from a side panel built once from the Alpaca SIP pulls
(C:/EdgeLog/alpaca_cache/tbis_r3 10-minute bars + siporb daily closes):
    C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_panel_v1.npz   (sha256 pinned below)
No panel on the machine (CI, the box) -> the file returns None (no trades), never a guess.
The name list is FIXED AS OF 2016 (no NVDA / TSLA / AVGO): a stale-universe limit, disclosed.
Half days are not in the panel and are skipped.

-- Sizing and costs (INSIDE the plugin - job cost_pts 0, mult 1) --------------------------
`notional` dollars a side. Cost a name = `spread_cents` / prior raw close at the entry (half a
cent = half the quoted spread of a one-cent megacap) + `fee_bps`; the closing auction is charged
no spread. PnL is DOLLARS in the trade tuple's field 2; one trade a session = the whole basket.

-- Auto-Validate ranges -------------------------------------------------------------------
k / beta_len / min_price / beta_adjust are OPEN; notional and both cost knobs are pinned.
"""
import hashlib
import os

import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC EODREV 1.0 · megacap end-of-day reversal (15:30 -> close, dollar-neutral)'
DESCRIPTION = ("At 15:20 ET rank 50 megacaps on the day's move minus beta x SPY; at 15:30 buy the k "
               "weakest and short the k strongest, exit at the closing print. The SPY 5m master is "
               "the clock only; stock prices come from a pinned side panel. Costs inside the plugin "
               "-> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "SPY", "timeframe": "5m", "session": "rth",
                 "source": "alpaca_split_rth"}

PANEL_PATH = r"C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_panel_v1.npz"
PANEL_SHA256 = "8dace1235912fe0adbdad0e5d941bb2cd411d5fcd7204e8ca4c83cc1701779b8"

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Dollars a side",
                 "tooltip": "Fixed. Longs and shorts each total this many dollars, equal per name."},
    "spread_cents": {"default": 0.5, "min": 0.5, "max": 0.5, "step": 0.5, "type": "float",
                     "label": "Entry cost (cents a share)",
                     "tooltip": "Fixed: half a cent a share at the 15:30 entry. The closing auction is charged no spread."},
    "fee_bps": {"default": 0.3, "min": 0.3, "max": 0.3, "step": 0.1, "type": "float",
                "label": "Fees (bps a name)", "tooltip": "Fixed: 0.3 bp of notional per name."},
    "k": {"hard_min": 1, "default": 5, "min": 3, "max": 10, "step": 1, "type": "int",
          "label": "Names a side", "tooltip": "Buy the k weakest, short the k strongest."},
    "beta_len": {"hard_min": 20, "default": 60, "min": 20, "max": 250, "step": 10, "type": "int",
                 "label": "Beta window (sessions)",
                 "tooltip": "Trailing sessions for each name's beta to SPY. Ends the session before."},
    "min_price": {"default": 40, "min": 0, "max": 80, "step": 20, "type": "int",
                  "label": "Price floor ($)",
                  "tooltip": "Only names whose prior raw close is at least this. Keeps the half-cent cost small."},
    "beta_adjust": {"default": True, "type": "bool", "label": "Rank on the beta-adjusted move",
                    "tooltip": "ON = move minus beta x SPY (r3). OFF = move minus SPY (the r1 rule)."},
}

PARAM_GRID_PRESETS = {
    "Short  (frozen r3 rule)": {"k": [5], "beta_len": [60], "min_price": [40]},
    "Medium (the r3 neighbours)": {"k": [3, 5, 7, 10], "beta_len": [20, 40, 60, 90, 120, 250],
                                   "min_price": [0, 40, 80]},
}

PNL_UNITS = "usd"

_CACHE = {}          # per-process: the panel, betas by window, daily PnL by config


def _panel():
    if "panel" in _CACHE:
        return _CACHE["panel"]
    p = None
    if os.path.exists(PANEL_PATH):
        with open(PANEL_PATH, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != PANEL_SHA256:
            raise RuntimeError("MISC_EODREV_1_0: side panel %s is not the pinned build" % PANEL_PATH)
        z = np.load(PANEL_PATH, allow_pickle=False)
        nm = [str(x) for x in z["names"]]
        if nm[-1] != "SPY":
            raise RuntimeError("MISC_EODREV_1_0: side panel's last column must be SPY")
        days = pd.Index(z["dates"].astype("int64"))
        f = lambda key: pd.DataFrame(z[key], index=days, columns=nm)
        ps, pe, c10, dc, rawc = f("ps"), f("pe"), f("c10"), f("dc"), f("raw")
        names = nm[:-1]
        pc = c10.shift(1)                              # yesterday's 15:50 close
        p = {"days": days, "names": names,
             "s0": (ps / pc - 1.0),                    # prior close -> 15:20 move (SPY in the last column)
             "ret": (dc[names] / pe[names] - 1.0),     # 15:30 open -> official close (the fill, not an input)
             "rp": rawc[names].shift(1),               # yesterday's raw close
             "dr": (c10 / pc - 1.0)}                   # daily returns for beta
    _CACHE["panel"] = p
    return p


def _beta(p, w):
    key = ("beta", int(w))
    if key not in _CACHE:
        names = p["names"]; dr = p["dr"]; m = dr["SPY"]
        mp = max(20, int(w * 2 / 3))
        cov = (dr[names].mul(m, axis=0).rolling(w, min_periods=mp).mean()
               - dr[names].rolling(w, min_periods=mp).mean().mul(m.rolling(w, min_periods=mp).mean(), axis=0))
        b = cov.div(m.rolling(w, min_periods=mp).var(), axis=0)
        _CACHE[key] = b.shift(1).clip(0.3, 2.5).fillna(1.0)      # shift(1): ends the session BEFORE
    return _CACHE[key]


def _daily_pnl(p, notional, spread_cents, fee_bps, k, beta_len, min_price, beta_adjust):
    """{yyyymmdd: dollars} for one config, over every panel session."""
    key = ("pnl", float(notional), float(spread_cents), float(fee_bps), int(k), int(beta_len),
           float(min_price), bool(beta_adjust))
    if key not in _CACHE:
        names = p["names"]; s0 = p["s0"]; spy = s0["SPY"]; ret = p["ret"]; rp = p["rp"]
        if beta_adjust:
            s = s0[names] - _beta(p, int(beta_len)).mul(spy, axis=0)
        else:
            s = s0[names].sub(spy, axis=0)
        s = s.where(rp >= float(min_price))
        cost = (float(spread_cents) / 100.0) / rp + float(fee_bps) * 1e-4
        r = s.rank(axis=1, ascending=False)
        n = s.notna().sum(axis=1)
        W = (r <= int(k)) & ret.notna()                           # strongest -> short
        L = (r > n.values[:, None] - int(k)) & ret.notna()        # weakest -> long
        g = ret.where(L).mean(axis=1) - ret.where(W).mean(axis=1)
        c = cost.where(L).mean(axis=1) + cost.where(W).mean(axis=1)
        net = ((g - c) * float(notional)).dropna()
        _CACHE[key] = dict(zip(net.index.tolist(), net.values.tolist()))
    return _CACHE[key]


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 notional: int = 100000, spread_cents: float = 0.5, fee_bps: float = 0.3,
                 k: int = 5, beta_len: int = 60, min_price: int = 40, beta_adjust: bool = True,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None:
        return None
    p = _panel()
    if p is None:
        return None
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    pnl = _daily_pnl(p, notional, spread_cents, fee_bps, k, beta_len, min_price, beta_adjust)
    trades = []
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [n]])
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        d = int(date[a])
        v = pnl.get(d)
        if v is None:
            continue
        m = minute[a:b]
        e = np.flatnonzero(m == 930)                 # the bar that opens 15:30 ET
        if len(e) == 0 or m[-1] < 950 or (b - 1) <= a + int(e[0]):
            continue                                  # no 15:30 bar, or the session's close is not in the bars yet
        eb = a + int(e[0]); xb = b - 1
        trades.append((int(eb), int(xb), float(v), 1, float(o[eb]), float(c[xb])))
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; l = p[p < 0]
    gw = float(w.sum()); gl = float(-l.sum())
    cum = np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(l))}
    if return_trades:
        out["trades"] = trades
    return out

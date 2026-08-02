"""
ENGU-Q 1m CTX (context-filter research)
----------------------------------------
RESEARCH FORK of ENGUQ_1M_1_0.py (the deployed 1m trendline-break champion). This
file does NOT change the deployed strategy — it is a standalone copy that pins
every ORIGINAL strategy param to the #149 champion value (min=max=default, so no
auto search can move them) and adds two NEW prior-day market-context filter knobs
that CAN be searched: `max_vix` and `max_tnx_chg20`. Two prior-day context filters
(skip days with prior-day VIX above ~24.86, and skip days with prior-day 20-day
change in the 10y yield above ~0.298) passed a frozen-holdout test upstream of
this file; this fork exists to run them through the real Auto-Validate pipeline
(walk-forward folds + lockbox) filtered-vs-raw.

Entry (long): uptrend (close>EMA), GREEN candle CLOSING ABOVE a descending trendline
fit to the last tl_len highs (breaks the line of lower-highs = the pullback), above the
prior high, on a volume spike, decisive break. Stop = swing low; exit = trailing stop.
Trades are returned rich: (entry_idx, exit_idx, pnl_pts, side=+1, entry_px) -> MAE/MFE.

CONTEXT FILTER WIRING: `run_backtest` declares `index=None` so the engine (engine.py
/ auto.py's make_slice_evaluator, both of which pass `index` to any strategy that
literally declares that parameter name) hands it the bar-level DatetimeIndex on the
validate/auto/single call paths. Grid-mode parallel workers (augur_mp_worker /
ProcessPoolExecutor) do NOT pass `index` — so on those paths the filter knobs are
silently inert (index stays None -> no-op) even if left non-zero. INTENDED USAGE IS
AUTO-VALIDATE (the `validate` job type), not the grid/sweep paths.

When a filter knob is > 0 AND `index` is not None, the strategy lazily loads the
already-downloaded VIX/TNX daily CSVs from augur_uploads/_context/ (the same cache
augur_engine.context.fetch_external_daily writes) directly with pandas — this file
NEVER makes a network call itself, unlike fetch_external_daily (which can trigger a
yfinance pull when its cache looks stale). Missing/unreadable cache files, or any
other problem in the filter layer, fail OPEN: the strategy trades exactly as if the
knob were 0 (unfiltered), it never raises. Values are shifted +1 trading day, the
same convention context.py uses (a bar dated D only ever sees D-1's close-derived
value), so `max_vix`/`max_tnx_chg20` gate NEW ENTRIES only — an already-open
position's exits/trailing/breakeven management proceed unaffected by the filter.

With both filter knobs at 0 (their default), this file is BIT-IDENTICAL to
ENGUQ_1M_1_0.py given the same params — the filter code path is only ever entered
when a knob is > 0, and that's it for the invariance story.
"""
import os

import numpy as np

STRATEGY_NAME = "ENGU-Q 1m CTX (context-filter research)"
DESCRIPTION = ("Research fork of ENGU-Q 1m: original entry/exit params PINNED to the "
              "#149 champion values; adds two searchable prior-day context filters "
              "(max VIX, max 10y-yield 20d rise) that suppress new entries on days "
              "flagged by the prior day's close. Built to run the frozen-holdout "
              "VIX/rate-spike filters through Auto-Validate (WF + lockbox). NOT the "
              "deployed strategy.")
VERSION   = "1.0-ctx"
DIRECTION = "LONG"
TIMEFRAME = "1m"

# #149 champion params (pinned — every ORIGINAL knob's min/max collapse to its
# default so the auto sampler can only ever draw this exact point for them).
_CHAMP = {'buf_atr': 0.9, 'ema_len': 390, 'tl_len': 48, 'stop_mult': 1.0,
         'trail_frac': 2.5, 'min_brk': 1.3, 'vol_mult': 0.8, 'atr_len': 30,
         'act_R': 2.5}

DEFAULT_PARAMS = {'tl_len': {'default': _CHAMP['tl_len'],
          'min': _CHAMP['tl_len'],
          'max': _CHAMP['tl_len'],
          'step': 1,
          'type': 'int',
          'label': 'Trendline Length (bars)',
          'tooltip': 'PINNED to the #149 champion value — CTX research fork only searches the '
                     'filter knobs below.'},
'vol_mult': {'default': _CHAMP['vol_mult'],
            'min': _CHAMP['vol_mult'],
            'max': _CHAMP['vol_mult'],
            'step': 0.1,
            'type': 'float',
            'label': 'Volume Spike (x avg)',
            'tooltip': 'PINNED to the #149 champion value.'},
'stop_mult': {'default': _CHAMP['stop_mult'],
             'min': _CHAMP['stop_mult'],
             'max': _CHAMP['stop_mult'],
             'step': 0.1,
             'type': 'float',
             'label': 'Stop (x risk-to-swing-low)',
             'tooltip': 'PINNED to the #149 champion value.'},
'act_R': {'default': _CHAMP['act_R'],
         'min': _CHAMP['act_R'],
         'max': _CHAMP['act_R'],
         'step': 0.5,
         'type': 'float',
         'label': 'Trail Activation (R)',
         'tooltip': 'PINNED to the #149 champion value.'},
'trail_frac': {'default': _CHAMP['trail_frac'],
              'min': _CHAMP['trail_frac'],
              'max': _CHAMP['trail_frac'],
              'step': 0.5,
              'type': 'float',
              'label': 'Trail Width (x risk)',
              'tooltip': 'PINNED to the #149 champion value.'},
'buf_atr': {'default': _CHAMP['buf_atr'],
           'min': _CHAMP['buf_atr'],
           'max': _CHAMP['buf_atr'],
           'step': 0.05,
           'type': 'float',
           'label': 'Breakout Buffer (x ATR)',
           'tooltip': 'PINNED to the #149 champion value.'},
'min_brk': {'default': _CHAMP['min_brk'],
           'min': _CHAMP['min_brk'],
           'max': _CHAMP['min_brk'],
           'step': 0.1,
           'type': 'float',
           'label': 'Breakout Decisiveness (x ATR)',
           'tooltip': 'PINNED to the #149 champion value.'},
'ema_len': {'default': _CHAMP['ema_len'],
           'min': _CHAMP['ema_len'],
           'max': _CHAMP['ema_len'],
           'step': 10,
           'type': 'int',
           'label': 'Trend EMA Length',
           'tooltip': 'PINNED to the #149 champion value.'},
'atr_len': {'default': _CHAMP['atr_len'],
           'min': _CHAMP['atr_len'],
           'max': _CHAMP['atr_len'],
           'step': 1,
           'type': 'int',
           'label': 'ATR Length',
           'tooltip': 'PINNED to the #149 champion value.'},
'regime_len': {'default': 0,
              'min': 0,
              'max': 0,
              'step': 5,
              'type': 'int',
              'label': 'Regime SMA (days, 0=off)',
              'tooltip': 'PINNED off (0) — not part of the #149 champion config.'},
'breakeven_R': {'default': 0.0,
               'min': 0.0,
               'max': 0.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Breakeven (R, 0=off)',
               'tooltip': 'PINNED off (0) — not part of the #149 champion config.'},
# ── NEW: searchable context-filter knobs (research payload of this fork) ──
# CTX GAUNTLET: job A (raw baseline) ran with these TEMPORARILY pinned min=max=0
# (run #182, ENGU-Q-8 — confirmed n_evaluated=1, filters guaranteed off). Restored
# here to the full 0-40 / 0-1 searchable range for job B.
'max_vix': {'default': 0.0,
           'min': 0.0,
           'max': 40.0,
           'step': 1.0,
           'type': 'float',
           'label': 'MAX VIX (0=off)',
           'tooltip': 'Skip NEW entries on days whose PRIOR-day VIX close was above this. '
                      '0=off. Frozen-holdout test flagged ~24.86 (IS p80).'},
'max_tnx_chg20': {'default': 0.0,
                  'min': 0.0,
                  'max': 1.0,
                  'step': 0.05,
                  'type': 'float',
                  'label': 'MAX 10Y 20D RISE (0=off)',
                  'tooltip': 'Skip NEW entries on days whose PRIOR-day 20-trading-day change in '
                             'the 10y yield (^TNX) was above this. 0=off. Frozen-holdout test '
                             'flagged ~0.298 (IS p90).'}}

PARAM_GRID_PRESETS = {}   # research fork: no grid presets — Auto-Validate only (see docstring)


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Context-filter loading — LOCAL CACHE ONLY, never a network call from this file.
# ─────────────────────────────────────────────────────────────────────────────
_CTX_DAILY = None            # lazy-cached pandas DataFrame, index=datetime.date,
                              # columns "vix"/"tnx_chg_20d", already +1-day shifted
_CTX_LOAD_ATTEMPTED = False


def _ctx_cache_dir():
    try:
        from augur_engine.paths import UPLOADS
        return os.path.join(UPLOADS, "_context")
    except Exception:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(here), "augur_uploads", "_context")


def _load_ctx_daily():
    """Lazily load + cache the prior-day VIX level and prior-day 20-trading-day TNX
    change from the LOCAL CSVs augur_uploads/_context/ already holds (the same cache
    augur_engine.context.fetch_external_daily writes) — a pure file read, no network
    call is ever made here. Replicates that module's own causal +1-day shift (a bar
    dated D only ever sees D-1's close-derived value). Returns None (cached, so this
    only runs once per process) on ANY problem — missing files, unreadable CSV,
    pandas not importable — so a filter knob left ON with no cache present just
    silently no-ops (fail-open)."""
    global _CTX_DAILY, _CTX_LOAD_ATTEMPTED
    if _CTX_LOAD_ATTEMPTED:
        return _CTX_DAILY
    _CTX_LOAD_ATTEMPTED = True
    try:
        import pandas as pd
        cdir = _ctx_cache_dir()
        vix_p = os.path.join(cdir, "_VIX.csv")
        tnx_p = os.path.join(cdir, "_TNX.csv")
        if not (os.path.exists(vix_p) and os.path.exists(tnx_p)):
            return None
        vdf = pd.read_csv(vix_p)
        tdf = pd.read_csv(tnx_p)
        vs = pd.Series(vdf["close"].astype(float).to_numpy(),
                       index=pd.to_datetime(vdf["date"]).dt.date)
        ts = pd.Series(tdf["close"].astype(float).to_numpy(),
                       index=pd.to_datetime(tdf["date"]).dt.date)
        vs = vs[~vs.index.duplicated(keep="last")].sort_index()
        ts = ts[~ts.index.duplicated(keep="last")].sort_index()
        # same construction as context.fetch_external_daily: build a combined
        # frame (outer-aligned by date), derive tnx_chg_20d, THEN shift +1 day.
        raw = pd.DataFrame({"vix": vs, "tnx": ts})
        raw["tnx_chg_20d"] = raw["tnx"].diff(20)
        daily = raw[["vix", "tnx_chg_20d"]].shift(1)
        _CTX_DAILY = daily
    except Exception:
        _CTX_DAILY = None
    return _CTX_DAILY


def _entry_blocked_mask(index, n, max_vix, max_tnx_chg20):
    """Per-bar boolean mask, True where a NEW ENTRY should be suppressed by the
    context filter. Fail-open: any problem at all (bad index, no cache, pandas
    missing, whatever) returns an all-False mask, i.e. behaves as if unfiltered."""
    try:
        if max_vix <= 0 and max_tnx_chg20 <= 0:
            return None
        daily = _load_ctx_daily()
        if daily is None or not len(daily):
            return None
        import pandas as pd
        if hasattr(index, "date"):
            bar_dates = np.asarray(index.date)
        else:
            bar_dates = pd.to_datetime(pd.Series(index)).dt.date.to_numpy()
        if len(bar_dates) != n:
            return None
        blocked = np.zeros(n, dtype=bool)
        bds = pd.Series(bar_dates)
        if max_vix > 0:
            vv = bds.map(daily["vix"]).to_numpy(dtype=float)
            blocked |= np.where(np.isnan(vv), -np.inf, vv) > max_vix
        if max_tnx_chg20 > 0:
            tt = bds.map(daily["tnx_chg_20d"]).to_numpy(dtype=float)
            blocked |= np.where(np.isnan(tt), -np.inf, tt) > max_tnx_chg20
        return blocked
    except Exception:
        return None


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0, max_vix=0.0, max_tnx_chg20=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < tl_len + 5:
        return None
    tl_len = int(tl_len)
    ema = _ema(c, int(ema_len))
    # optional longer-term REGIME gate: close must be above its N-day simple average
    #   (390 RTH bars/day). 0 = off. Long lengths skip bears/chop; short lengths whipsaw.
    reg = None
    if int(regime_len) > 0:
        rb = int(regime_len) * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb
    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); al = int(atr_len)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        vv = np.asarray(volumes, float)
        vavg = np.full(n, np.nan); w = 20
        vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    # CONTEXT FILTER (research payload of this fork): only ever touched when a knob
    # is > 0 AND the caller handed us `index` (validate/auto/single paths — grid
    # workers don't pass it). With both knobs at 0 (default) `_blocked` stays None
    # and every line below this is dead code — byte-identical to ENGUQ_1M_1_0.py.
    _blocked = None
    if index is not None and (float(max_vix) > 0 or float(max_tnx_chg20) > 0):
        try:
            _blocked = _entry_blocked_mask(index, n, float(max_vix), float(max_tnx_chg20))
        except Exception:
            _blocked = None

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()
    pnl_list, trade_log = [], []
    pos = None
    for i in range(tl_len + 1, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        if pos is not None:
            if h[i] - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                # gap-through realism: if the bar OPENED beyond the stop, the fill is the
                # open (can't be filled at a stop price the market never traded through
                # cleanly) — not the exact stop price. ORB 3.0 models the same.
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl, 1, pos["ep"]))
                pos = None
            continue
        # NEW-ENTRY-only context gate — an open position's management above never
        # reaches this line (it `continue`s before getting here).
        if _blocked is not None and _blocked[i]:
            continue
        if c[i] <= o[i] or not c[i] > ema[i]:
            continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):   # regime gate
            continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            continue
        if (c[i] - tl_now) / max(a, 0.25) < min_brk:
            continue
        swing_low = l[i - tl_len:i + 1].min()
        risk = c[i] - swing_low
        if risk < max(0.25, 0.5):
            continue
        ep = c[i]
        pos = {"bar": i, "ep": ep, "risk": risk, "sl": ep - stop_mult * risk, "act": False}

    if pos is not None:
        pnl = c[-1] - pos["ep"]; pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl, 1, pos["ep"]))
    if not pnl_list:
        return None
    p = np.array(pnl_list); wins = p[p > 0]; losses = p[p < 0]
    cum = np.cumsum(p)
    out = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out

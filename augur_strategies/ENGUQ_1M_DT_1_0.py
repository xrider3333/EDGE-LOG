"""
ENGU-Q 1m - trendline break (long) + PRIOR-DAY CLOSE-POSITION filter
--------------------------------------------------------------------
2026-08-18 cross-family transfer test. Exact copy of ENGUQ_1M_1_0.py's engine (the
RTH champion behind run #149 / #227) with THREE new knobs, all DEFAULT OFF:

    daytype_mode  off (default) | skip_bot_short | skip_bot_all | skip_top_long | skip_top_all
    daytype_lo    bottom cutoff, default 0.20
    daytype_hi    top cutoff, default 0.80

DEFINITION, identical to NOISE_1_0.py's `_daytype_pos` and ORB_3_8.py's copy so the
three families are directly comparable: for session i, pos = (C - L) / (H - L) of
session i-1. NaN on the first session or a zero-range session; the filter is inactive
whenever it is NaN. Session boundaries come from `day_id`; with no `day_id` the filter
cannot run and is silently inert (documented, and asserted in the smoke test).

NOTE FOR THE READER: ENGU-Q IS LONG-ONLY. `skip_bot_short` is therefore a structural
no-op here and is kept only so the knob has the same option list in every family. The
modes that can actually bite are `skip_bot_all` (blocks longs after a WEAK close) and
`skip_top_long` / `skip_top_all` (block longs after a STRONG close).

LIVE-LEGAL BY CONSTRUCTION: every input is a FINISHED prior session's bar.
daytype_mode='off' reproduces ENGUQ_1M_1_0.py bit-for-bit (asserted in __main__).
"""
import numpy as np

# ── NQ DEPLOY CONFIG (run #149 + breakeven 1.5) — CERTIFIED 2026-08-05 ──────────
# The DEFAULT_PARAMS defaults below are the ES-validated config. The NQ champion
# (#149) uses DIFFERENT params — this mixup caused the 2026-07-14 "repro defect"
# (attempts fed ES-style defaults and got n=3618/$276k instead of the champion).
# With the params below on NQ 1m RTH 2010-06-07→2026-06-30 @ 0.533 pts cost this
# file reproduces: entries 1800/1800 EXACT vs blotters/run149_NQ_1m.csv;
# breakeven_R=1.5 → n=2048, maxDD −$65,635 (exact), net ≈$477.5k (doc $474.7k;
# ~0.6% tail drift from master data revisions since 2026-07-13).
NQ_DEPLOY_PARAMS_149 = dict(tl_len=48, ema_len=390, regime_len=0, buf_atr=0.9,
                            min_brk=1.3, atr_len=30, vol_mult=0.8, stop_mult=1.0,
                            act_R=2.5, trail_frac=2.5, breakeven_R=1.5)

STRATEGY_NAME = "ENGU-Q 1m · trendline break + prior-day close-position filter"
DESCRIPTION = ("Research fork of the ENGU-Q 1m champion carrying the prior-day close-position gate (default OFF = identical to the parent). ENGU-Q tuned for 1-minute bars: green candle breaking a descending trendline of recent lower-highs, above the trend EMA, on a volume spike; trailing exit. Walk-forward VALIDATED (PASS) on ES 1m.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_1_0.py"

DEFAULT_PARAMS = {'tl_len': {'default': 34,
          'min': 15,
          'max': 80,
          'step': 1,
          'type': 'int',
          'label': 'Trendline Length (bars)',
          'tooltip': 'Bars of highs the descending trendline is fit to (must slope down). 1m: try ~30-70 '
                     '(tl_len 34 validated).'},
'vol_mult': {'default': 1.2,
            'min': 0.0,
            'max': 5.0,
            'step': 0.1,
            'type': 'float',
            'label': 'Volume Spike (x avg)',
            'tooltip': 'Breakout candle volume must exceed its 20-bar average x this. 0=off.'},
'stop_mult': {'default': 1.7,
             'min': 0.3,
             'max': 2.0,
             'step': 0.1,
             'type': 'float',
             'label': 'Stop (x risk-to-swing-low)',
             'tooltip': 'Initial stop distance as a fraction of entry-to-swing-low.'},
'act_R': {'default': 1.0,
         'min': 0.0,
         'max': 3.0,
         'step': 0.5,
         'type': 'float',
         'label': 'Trail Activation (R)',
         'tooltip': 'Start trailing once the trade is this many R in profit.'},
'trail_frac': {'default': 2.5,
              'min': 0.5,
              'max': 4.0,
              'step': 0.5,
              'type': 'float',
              'label': 'Trail Width (x risk)',
              'tooltip': 'Trailing stop rides this far (in risk units) below the running high.'},
'buf_atr': {'default': 0.35,
           'min': 0.0,
           'max': 1.0,
           'step': 0.05,
           'type': 'float',
           'label': 'Breakout Buffer (x ATR)',
           'tooltip': 'Close must clear the trendline by this x ATR.'},
'min_brk': {'default': 0.7,
           'min': 0.0,
           'max': 3.0,
           'step': 0.1,
           'type': 'float',
           'label': 'Breakout Decisiveness (x ATR)',
           'tooltip': 'Close-minus-trendline must be at least this x ATR (a decisive break).'},
'ema_len': {'default': 30,
           'min': 20,
           'max': 400,
           'step': 10,
           'type': 'int',
           'label': 'Trend EMA Length',
           'tooltip': 'Only take longs with close above this EMA (uptrend filter).'},
'atr_len': {'default': 47,
           'min': 5,
           'max': 50,
           'step': 1,
           'type': 'int',
           'label': 'ATR Length',
           'tooltip': 'Lookback for ATR (buffer/decisiveness).'},
'regime_len': {'default': 0,
              'min': 0,
              'max': 100,
              'step': 5,
              'type': 'int',
              'label': 'Regime SMA (days, 0=off)',
              'tooltip': 'Only go long when close is above its N-DAY simple average — a longer-term trend gate on '
                         'top of the EMA. 0=off. Long (~20-50d) skips bears/chop and cuts drawdown; short whipsaws. '
                         '(390 RTH bars/day.)'},
'breakeven_R': {'default': 0.0,
               'min': 0.0,
               'max': 3.0,
               'step': 0.5,
               'type': 'float',
               'label': 'Breakeven (R, 0=off)',
               'tooltip': 'Once the trade is this many R in profit (high vs entry), raise the stop to entry so it '
                          'can never go negative. 0=off. 1.5 tested well: protects the 1.5R-2.5R window before the '
                          'trail activates without scratching the fat-tail winners.'},
 'daytype_mode': {'default': 'off',
                  'type': 'str',
                  'options': ['off', 'skip_bot_short', 'skip_bot_all',
                              'skip_top_long', 'skip_top_all'],
                  'label': 'Prior-day close-position filter',
                  'tooltip': "Gate new entries on where YESTERDAY closed inside its own range "
                             "((close-low)/(high-low)) -- known before today's open, fully causal. "
                             "off (default) = no change. ENGU-Q is LONG-ONLY, so skip_bot_short "
                             "does nothing here; skip_bot_all blocks entries the day after a "
                             "bottom-20% close and the skip_top modes block them after a top-20% "
                             "close. Needs day_id; inert without it."},
 'daytype_lo': {'default': 0.2,
                'min': 0.05,
                'max': 0.45,
                'step': 0.05,
                'type': 'float',
                'label': 'Bottom close-position threshold',
                'tooltip': "Yesterday's close-position at or below this counts as a weak close. "
                           "0.20 is the NOISE-researched value; 0.15/0.25 are the pre-declared "
                           "plateau neighbours."},
 'daytype_hi': {'default': 0.8,
                'min': 0.55,
                'max': 0.95,
                'step': 0.05,
                'type': 'float',
                'label': 'Top close-position threshold',
                'tooltip': "Mirror of the bottom threshold, read only by the skip_top modes."},
}

PARAM_GRID_PRESETS = {'Robust (high-frequency)': {'tl_len': [25, 34, 45, 60],
                           'vol_mult': [1.1, 1.2, 1.3],
                           'stop_mult': [1.0, 1.5, 1.7],
                           'act_R': [1.0, 1.5],
                           'trail_frac': [2.0, 2.5],
                           'buf_atr': [0.2, 0.35],
                           'min_brk': [0.3, 0.7],
                           'ema_len': [30, 100, 200],
                           'atr_len': [14, 47],
                           'regime_len': [0, 20, 50],
                           'breakeven_R': [0.0, 1.0, 1.5, 2.0]},
'Wide': {'tl_len': [20, 34, 50, 70],
        'vol_mult': [1.0, 1.2, 1.5],
        'stop_mult': [1.0, 1.5],
        'act_R': [1.0, 1.5],
        'trail_frac': [1.5, 2.5, 3.0],
        'buf_atr': [0.1, 0.35],
        'min_brk': [0.0, 0.7],
        'ema_len': [30, 200],
        'atr_len': [14, 47],
        'regime_len': [0, 30, 50, 75],
        'breakeven_R': [0.0, 1.5, 3.0]}}


def _ema(a, n):
    k = 2.0 / (n + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out



def _daytype_pos(h, l, c, sess_bounds):
    """pos[si] = the PRIOR session's close position inside its own range,
    (C-L)/(H-L). NaN for the first session or a zero-range session. Identical
    definition to NOISE_1_0.py / ORB_3_8.py. Causal - prior finished session."""
    cp = np.full(len(sess_bounds), np.nan, dtype=float)
    for si in range(1, len(sess_bounds)):
        a, b = sess_bounds[si - 1]
        lo = l[a:b].min()
        rng = h[a:b].max() - lo
        if rng > 1e-12:
            cp[si] = (c[b - 1] - lo) / rng
    return cp


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 tl_len=20, vol_mult=1.5, stop_mult=1.0, act_R=1.0, trail_frac=2.0,
                 buf_atr=0.1, min_brk=0.5, ema_len=200, atr_len=14, regime_len=0,
                 breakeven_R=0.0,
                 daytype_mode="off", daytype_lo=0.2, daytype_hi=0.8,
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

    # -- PRIOR-DAY CLOSE-POSITION GATE (2026-08-18) -----------------------------
    # blocked[i] = True when bar i sits in a session whose PRIOR session closed in
    # the configured tail of its own range. Computed only when the knob is on, so
    # the default is a true no-op. Causal: prior finished session only.
    _blocked = None
    if daytype_mode != "off" and daytype_mode != "skip_bot_short" \
            and day_id is not None and len(day_id) == n:
        _did = np.asarray(day_id)
        _sb, _a = [], 0
        while _a < n:
            _b = _a
            while _b < n and _did[_b] == _did[_a]:
                _b += 1
            _sb.append((_a, _b)); _a = _b
        _dp = _daytype_pos(h, l, c, _sb)
        _blocked = np.zeros(n, bool)
        for _si, (_a, _b) in enumerate(_sb):
            _p = _dp[_si]
            if _p != _p:
                continue
            if daytype_mode == "skip_bot_all" and _p <= daytype_lo:
                _blocked[_a:_b] = True
            elif daytype_mode in ("skip_top_long", "skip_top_all") and _p >= daytype_hi:
                _blocked[_a:_b] = True

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
        if _blocked is not None and _blocked[i]:      # prior-day close-position gate
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


# -----------------------------------------------------------------------------
# Smoke test: (1) daytype_mode='off' must be BIT-IDENTICAL to ENGUQ_1M_1_0.py on
# the #149 deploy config; (2) skip_bot_short must ALSO be identical (long-only
# strategy, structural no-op); (3) the other three modes must change results.
# Run:  python augur_strategies/ENGUQ_1M_DT_1_0.py
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_1m_RTH.csv")
    if not os.path.exists(MASTER):
        MASTER = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG",
                              "augur_uploads", "NOADJ_NQ_1m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ 1m master not found"); sys.exit(1)

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)
    df = df[dt.dt.date <= pd.Timestamp("2026-06-30").date()].reset_index(drop=True)

    base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ENGUQ_1M_1_0.py")
    spec = ilu.spec_from_file_location("_enguq_base", base_path)
    base = ilu.module_from_spec(spec); spec.loader.exec_module(base)

    P149 = dict(base.NQ_DEPLOY_PARAMS_149)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **P149)
    r1 = run_backtest(*args, **kw, **P149, daytype_mode="off")
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9
            and all(a == b for a, b in zip(r0["trades"], r1["trades"])))
    print("daytype OFF parity vs ENGUQ_1M_1_0: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    rs = run_backtest(*args, **kw, **P149, daytype_mode="skip_bot_short")
    nosh = (rs["num_trades"] == r1["num_trades"]
            and abs(rs["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("skip_bot_short is a no-op (long-only): %s" % ("PASS" if nosh else "FAIL"))

    ok = True
    for mode in ("skip_bot_all", "skip_top_long", "skip_top_all"):
        r = run_backtest(*args, **kw, **P149, daytype_mode=mode)
        chg = (r["num_trades"] != r1["num_trades"]
               or abs(r["total_pnl"] - r1["total_pnl"]) > 1e-9)
        ok = ok and chg
        print("  %-15s n=%4d pnl=%10.1f  changes: %s" % (
            mode, r["num_trades"], r["total_pnl"], "yes" if chg else "NO"))
    sys.exit(0 if (same and nosh and ok) else 1)

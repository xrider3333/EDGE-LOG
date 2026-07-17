"""
MACDRSI 1.0 — TV round-13 port #4: "MACD Bull Crossover and RSI Oversold 5 Candles
Ago-Long Strategy" by Trebor_Namor.

Source: https://www.tradingview.com/script/iifAsfrq-MACD-Bull-Crossover-and-RSI-Oversold-5-Candles-Ago-Long-Strategy/
(17.6K boosts). The TV Pine source is PROTECTED (closed) — unlike BBRSI/MACD200 this
port is NOT built from a readable Pine listing. It is built from (a) the author's own
published rule description on the script's TV page, and (b) the author's own Python
re-implementation of the same rule-set, published in his GitHub repo
https://github.com/TreborNamor/TradingView-Machine-Learning-GUI (strategy/macd_rsi.py,
using strategy/indicators.py's talib-backed rsi()/macd() and pandas barssince()/
crossed_above()/crossed_below() helpers — both mirrored in the session scratchpad as
04_github_macd_rsi.py / 04_github_indicators.py). Ported for EDGE-LOG challenger round
13 (see TV_SWEEP.md 13.4). Re-implementation, not a copy of either source's text.

Published rules:
  RSI(14) Wilder on close. Standard EMA MACD: macd = EMA(close,12) - EMA(close,26);
  signal = EMA(macd,9); hist = macd - signal.
  was_oversold[t]   = bars since RSI last <= 30 (INCLUDING bar t itself, i.e. 0 if
                       RSI[t]<=30) is <= lookback bars.
  was_overbought[t] = bars since RSI last >= 70 (same convention) is <= lookback bars.
  LONG ENTRY  at t: MACD crosses ABOVE signal (macd[t]>signal[t], macd[t-1]<=signal[t-1])
                    AND was_oversold[t].
  LONG EXIT   at t (the author's own close-rule description): "MACD Histogram is above
                    0 and MACD crosses under the signal line" AND "RSI was overbought 5
                    previous candles ago" -> crossunder(macd,signal) AND hist[t-1]>0 AND
                    was_overbought[t] (see judgment call #2 below).
  direction "long" (published): long/flat only, next-bar-open fills both ways.
  lookback: the TV script's TITLE says 5; the author's own later GitHub Python defaults
  signal_lookback_bars to 10 (see judgment call #1). No stop-loss/target in the base
  rule-set; the author's Pine strategy exposes optional SL/TP inputs that default OFF.

Judgment calls (house-honest, documented since the TV source itself is unreadable):
  1. lookback default = 5 (matches the TV *title* and script name, the actual published
     artifact we're porting) with 10 tested as a grid cell (matches the author's own
     later GitHub Python default — evidence he considered 10 an improvement, but 5 is
     what shipped under this script's boosts).
  2. Exit-rule histogram timing: hist[t] = macd[t]-signal[t] is NECESSARILY <= 0 (in
     fact strictly negative) at the crossunder bar itself, by the crossunder definition
     macd[t]<signal[t]. So "MACD Histogram is above 0" in the author's own close-rule
     description cannot refer to bar t — it must mean the bar BEFORE the cross.
     Implemented as hist[t-1] > 0, per spec. NOTE this deliberately diverges from the
     author's own later GitHub sell_signal (which dropped the histogram clause entirely:
     was_overbought & crossed_below only) — we follow the published TV rule TEXT over
     the author's simplified GitHub port, since the TV artifact (boosts, title,
     description) is the thing actually being ported.
     EMPIRICAL CAVEAT (checked NQ 5m, two independent 3yr windows 2015-17 / 2018-20):
     hist[t-1] > 0 turns out to be near-tautological given crossed_below's OWN t-1
     clause -- crossed_below(t) already requires macd[t-1]>=signal[t-1], i.e.
     hist[t-1]>=0, so the strict ">0" only excludes the knife-edge macd[t-1]==
     signal[t-1] exactly. Observed 0 exclusions out of 2,224 crossunder bars (2018-20)
     and 427/427, 319/319 matches on the 2015-17 window -- the histogram clause added
     ZERO additional filtering in both samples. This actually reconciles the two
     sources: the author's GitHub simplification (dropping the clause) is numerically
     ~equivalent to our literal reading, because "the histogram was above zero" mostly
     just restates what crossing down FROM ABOVE the signal line already means, rather
     than adding an independent condition. The formula is implemented exactly as
     specified regardless (it is the literal, auditable reading of the rule text, and
     is harmless/inert rather than wrong) -- flagged here so long_exit_sig is not
     mistaken for a stronger filter than it actually is.
  3. direction="both" is NOT published — the author's description says a short version
     was "coming" but none shipped on TV. We add a mechanical mirror (short entry =
     crossunder+was_overbought, short exit = crossover+hist[t-1]<0+was_oversold) as a
     grid-only robustness/completeness read, run as a stop-and-reverse pair on the two
     ENTRY conditions. Note the mirrored EXIT conditions are logically dominated by the
     opposite side's ENTRY condition (e.g. long_exit = short_entry AND hist[t-1]>0, a
     subset that judgment call #2 shows is empirically ~equality, not just a subset) —
     so in "both" mode position changes are effectively pure stop-and-reverse on entries
     alone; the standalone exit branches only do independent work in "long" mode (where
     the opposite entry is disabled). This is expected SAR behaviour given the formulas,
     not a bug — documented here so it isn't mistaken for dead code.
  4. EMA convention: Pine's ema() is the textbook recursive EMA, alpha=2/(len+1) from
     the first bar — reproduced here with pandas ewm(span=len, adjust=False). The
     author's own GitHub code instead calls talib.MACD(), whose EMA is SMA-seeded
     (different warm-up path, converges to the same steady state). We follow Pine
     parity (ewm) over GitHub-literal parity (talib) since the TV artifact is the thing
     being ported; the difference is invisible past the warmup mask anyway.
  5. sl_pct / tp_pct: optional intrabar risk overlay, OFF by default (0), mirroring the
     author's Pine strategy having adjustable-but-disabled SL/TP inputs. When enabled,
     copies ORB_3_1's convention exactly: stop at entry*(1-sl_pct) / target at
     entry*(1+tp_pct) for longs (mirrored for shorts), STOP-FIRST pessimism when both
     would hit the same bar, gap-through stops fill AT THE BAR'S OPEN (never a better
     price than the stop), targets fill exactly at their level (no favorable-gap
     improvement). Like ORB_3_1, the entry bar itself is never SL/TP-checked (monitoring
     starts the bar AFTER a position opens or reverses) — the whole bar's range is
     "spent" on the fill decision, consistent with the fill-at-open == earliest-possible-
     tick reasoning used throughout this port.
  6. PARAM_GRID_PRESETS ships exactly the two tiers specified for this port (Short =
     published cell, Medium = the 16-cell author-knob grid) — no Long/XL tier added, to
     keep this port's scope to what was reviewed, not house convention-by-default.

Roll-seam guard, blocked-fill day, force-flat at seam-eve close, end-of-data trade
DROPPED (never truncated): identical method + calibration to BBRSI_1_0 / TTIBS_1_0
(detect_roll_seams below is a verbatim copy). The seam-eve "blocked day" rule is
extended here to ALSO suppress SL/TP intrabar fills (BBRSI has no SL/TP mechanic to
extend) — a position open into the seam-eve day simply rides untouched to the mandatory
force-flat at that day's close, same as any other fill type on that day.

PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363 ES),
same as every library strategy. Needs day_id AND index (roll-seam calendar + session
boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'MACDRSI 1.0 · TV#4 MACD cross + RSI-oversold-recently long (Trebor_Namor)'
DESCRIPTION = ("Round-13 port of a protected-source TV strategy, built from the author's "
               "own rule description + his GitHub Python port: RSI(14)-oversold-within-"
               "lookback gates a MACD(12,26,9) bull cross for longs; exit on a bear cross "
               "with a collapsing-histogram + RSI-overbought-recently filter. Next-bar-open "
               "fills, roll-seam guarded, optional grid-only short mirror + SL/TP overlay.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "rsi_len": {
        "default": 14, "min": 4, "max": 40, "step": 1, "type": "int",
        "label": "RSI period",
        "tooltip": "Published default 14 (standard Wilder RSI length).",
    },
    "rsi_os": {
        "default": 30, "min": 10, "max": 45, "step": 1, "type": "int",
        "label": "RSI oversold threshold",
        "tooltip": "RSI <= this level arms the 'was oversold' window that gates a long "
                   "entry. Published default 30.",
    },
    "rsi_ob": {
        "default": 70, "min": 55, "max": 90, "step": 1, "type": "int",
        "label": "RSI overbought threshold",
        "tooltip": "RSI >= this level arms the 'was overbought' window that gates the "
                   "exit (and the short-mirror entry in both mode). Published default 70.",
    },
    "lookback": {
        "default": 5, "min": 1, "max": 30, "step": 1, "type": "int",
        "label": "Oversold/overbought lookback (bars)",
        "tooltip": "How many bars back an RSI extreme is still 'live' for gating a MACD "
                   "cross. The TV title/published artifact defaults this to 5; the "
                   "author's own later GitHub port defaults it to 10 (Short preset = 5, "
                   "Medium grid also tries 10).",
    },
    "macd_fast": {
        "default": 12, "min": 3, "max": 30, "step": 1, "type": "int",
        "label": "MACD fast EMA length",
        "tooltip": "Published default 12 (standard MACD).",
    },
    "macd_slow": {
        "default": 26, "min": 10, "max": 60, "step": 1, "type": "int",
        "label": "MACD slow EMA length",
        "tooltip": "Published default 26 (standard MACD).",
    },
    "macd_sig": {
        "default": 9, "min": 2, "max": 30, "step": 1, "type": "int",
        "label": "MACD signal EMA length",
        "tooltip": "Published default 9 (standard MACD).",
    },
    "direction": {
        "default": "long", "type": "str",
        "options": ["long", "both"],
        "label": "Trade direction",
        "tooltip": "long = the published long/flat strategy (entry only on the bull "
                   "cross, exit only on the bear-cross-with-histogram rule). both = an "
                   "unpublished short mirror added for completeness (the author said a "
                   "short version was 'coming' but never shipped one on TV) — a "
                   "stop-and-reverse pair on the two entry conditions; see the module "
                   "docstring for how the mirrored exit branches interact.",
    },
    "sl_pct": {
        "default": 0.0, "min": 0.0, "max": 0.10, "step": 0.01, "type": "float",
        "label": "Stop-loss (% of entry, 0=off)",
        "tooltip": "Optional intrabar stop, OFF by default (matches the published "
                   "strategy, which ships no risk overlay active). Stop-first pessimism "
                   "vs the target if both would hit the same bar; gap-through fills at "
                   "the bar's open (ORB_3_1 convention). Never checked on the entry bar.",
    },
    "tp_pct": {
        "default": 0.0, "min": 0.0, "max": 0.10, "step": 0.01, "type": "float",
        "label": "Take-profit (% of entry, 0=off)",
        "tooltip": "Optional intrabar target, OFF by default. Fills exactly at the "
                   "target level (no favorable-gap improvement), same convention as "
                   "ORB_3_1. Never checked on the entry bar.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "rsi_len": [14], "rsi_os": [30], "rsi_ob": [70], "lookback": [5],
        "macd_fast": [12], "macd_slow": [26], "macd_sig": [9],
        "direction": ["long"], "sl_pct": [0.0], "tp_pct": [0.0],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.4):
    # rsi_os {30,35} x rsi_ob {70,65} x lookback {5,10} x direction {long,both} = 16 cells.
    "Medium (author-knob grid)": {
        "rsi_len": [14], "rsi_os": [30, 35], "rsi_ob": [70, 65], "lookback": [5, 10],
        "macd_fast": [12], "macd_slow": [26], "macd_sig": [9],
        "direction": ["long", "both"], "sl_pct": [0.0], "tp_pct": [0.0],
    },
}


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b))
        a = b
    return bounds


def _third_weekday(year, month, weekday=2):
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0,
                      base_win=60, pre_days=12, post_days=2):
    """Identical method + calibration to TTIBS_1_0.detect_roll_seams (see that
    docstring): calendar-scoped local-outlier search around each quarter's 3rd
    Wednesday; returns daily indices s where close[s-1]->open[s] is a roll seam."""
    n = len(day_close)
    if n < base_win + 5:
        return []
    ts = pd.DatetimeIndex(day_ts)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    gap = np.empty(n); gap[:] = np.nan
    gap[1:] = day_open[1:] - day_close[:-1]
    abs_gap = np.abs(gap)

    baseline = np.full(n, np.nan)
    for i in range(base_win, n):
        window = abs_gap[i - base_win:i]
        window = window[~np.isnan(window)]
        if len(window) >= max(10, base_win // 3):
            baseline[i] = np.median(window)

    quarters = sorted({(t.year, t.month) for t in ts if t.month in (3, 6, 9, 12)})
    seams = []
    for (y, m) in quarters:
        wed3 = _third_weekday(y, m)
        win_start = wed3 - pd.Timedelta(days=pre_days)
        win_end = wed3 + pd.Timedelta(days=post_days)
        idx_in_win = [i for i in range(n) if win_start <= ts[i] <= win_end
                      and not np.isnan(gap[i]) and not np.isnan(baseline[i])]
        if not idx_in_win:
            continue
        best = max(idx_in_win, key=lambda i: abs_gap[i])
        if abs_gap[best] >= abs_th and baseline[best] > 0 and \
           (abs_gap[best] / baseline[best]) >= ratio_th:
            seams.append(best)
    return sorted(seams)


def _wilder_rsi(close, length):
    """Pine rsi(): Wilder smoothing (rma). ewm(alpha=1/len, adjust=False) converges to
    Pine's recursive rma after warm-up; signals are masked during warm-up anyway."""
    s = pd.Series(close)
    delta = s.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / length, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / length, adjust=False).mean()
    rs = ru / rd.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(rd > 1e-12, 100.0).where(ru > 1e-12, rsi)  # Pine edge conventions
    return rsi.to_numpy()


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    rsi_len: int = 14, rsi_os: int = 30, rsi_ob: int = 70, lookback: int = 5,
    macd_fast: int = 12, macd_slow: int = 26, macd_sig: int = 9,
    direction: str = "long", sl_pct: float = 0.0, tp_pct: float = 0.0,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None or index is None:
        return None                    # needs real dates (roll seams / session ends)

    rsi_len = int(rsi_len); rsi_os = float(rsi_os); rsi_ob = float(rsi_ob)
    lookback = int(lookback)
    macd_fast = int(macd_fast); macd_slow = int(macd_slow); macd_sig = int(macd_sig)
    sl_pct = float(sl_pct); tp_pct = float(tp_pct)
    allow_short = (direction == "both")
    use_sl = sl_pct > 0.0
    use_tp = tp_pct > 0.0

    # ── indicators (Pine-parity: Wilder RSI, textbook recursive EMA MACD) ──────────
    vrsi = _wilder_rsi(c, rsi_len)
    close_s = pd.Series(c)
    ema_fast = close_s.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close_s.ewm(span=macd_slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=macd_sig, adjust=False).mean()
    hist = (macd_line - signal_line).to_numpy()
    macd_np = macd_line.to_numpy()
    sig_np = signal_line.to_numpy()

    # crossover/crossunder(macd, signal): a[t]><b[t] and a[t-1]<=>=b[t-1] (Pine def.)
    xo = np.zeros(n, bool); xu = np.zeros(n, bool)
    xo[1:] = (macd_np[1:] > sig_np[1:]) & (macd_np[:-1] <= sig_np[:-1])
    xu[1:] = (macd_np[1:] < sig_np[1:]) & (macd_np[:-1] >= sig_np[:-1])
    hist_prev_pos = np.zeros(n, bool); hist_prev_neg = np.zeros(n, bool)
    hist_prev_pos[1:] = hist[:-1] > 0
    hist_prev_neg[1:] = hist[:-1] < 0

    # barssince(cond)[t] = bars since cond last True, INCLUDING t (0 if cond[t] True);
    # NaN before the first-ever hit. Mirrors the author's GitHub barssince() exactly
    # (numpy positions + a pandas ffill of the last-true index).
    def _bars_since(mask):
        pos_idx = np.arange(n, dtype="float64")
        last_true = np.where(mask, pos_idx, np.nan)
        last_true = pd.Series(last_true).ffill().to_numpy()
        return pos_idx - last_true

    os_hit = vrsi <= rsi_os
    ob_hit = vrsi >= rsi_ob
    with np.errstate(invalid="ignore"):
        was_os = _bars_since(os_hit) <= lookback
        was_ob = _bars_since(ob_hit) <= lookback

    long_entry_sig  = xo & was_os
    long_exit_sig   = xu & hist_prev_pos & was_ob
    short_entry_sig = xu & was_ob
    short_exit_sig  = xo & hist_prev_neg & was_os

    warm = max(150, 60)
    long_entry_sig[:warm] = False
    long_exit_sig[:warm] = False
    short_entry_sig[:warm] = False
    short_exit_sig[:warm] = False

    # ── session / roll-seam scaffolding (verbatim BBRSI_1_0 pattern) ────────────────
    bounds = _session_bounds(did, n)
    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    force_exit_days = {sd - 1 for sd in seam_days if sd - 1 >= 0}   # daily index
    # map: bar -> daily index; last bar of each day
    day_of_bar = np.empty(n, int)
    last_bar_of_day = {}
    for di, (a, b) in enumerate(bounds):
        day_of_bar[a:b] = di
        last_bar_of_day[di] = b - 1
    blocked_days = set(force_exit_days)          # no fills (signal OR sl/tp) on seam eve

    # ── event loop ──────────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    stop_lvl = None
    tgt_lvl = None
    pending = None            # None, or int side (1/-1/0) — always a plain market@open fill
    pnl_list, trade_log = [], []

    def _book(exit_bar_i, exit_price, side, ep, eb):
        pnl = (exit_price - ep) if side > 0 else (ep - exit_price)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(eb), int(exit_bar_i), float(pnl), int(side),
                              float(ep), float(exit_price)))

    def _levels(side, ep):
        if side > 0:
            sl = ep * (1.0 - sl_pct) if use_sl else None
            tp = ep * (1.0 + tp_pct) if use_tp else None
        else:
            sl = ep * (1.0 + sl_pct) if use_sl else None
            tp = ep * (1.0 - tp_pct) if use_tp else None
        return sl, tp

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        di = day_of_bar[u]

        # 1) pending order fill attempt at u's open (armed by u-1's close signal).
        #    MACDRSI has no stop-entry level (unlike BBRSI/MACD200) — every fill is a
        #    plain next-bar-open market order, per the published rule description.
        if pending is not None:
            side = pending
            if di not in blocked_days:
                fill = o[u]
                if side == 0:                          # flat exit
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0; stop_lvl = tgt_lvl = None
                elif pos == 0:
                    pos = side; entry_px = fill; entry_bar = u
                    stop_lvl, tgt_lvl = _levels(pos, entry_px)
                elif pos != side:                      # reversal ("both" mode)
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = side; entry_px = fill; entry_bar = u
                    stop_lvl, tgt_lvl = _levels(pos, entry_px)
            pending = None

        # 2) intrabar SL/TP check — only a position opened on an EARLIER bar, never
        #    the entry/reversal bar itself (ORB_3_1 convention), and never on the
        #    seam-eve blocked day (a carried position rides untouched to the forced
        #    flatten instead).
        if pos != 0 and entry_bar != u and (use_sl or use_tp) and di not in blocked_days:
            if pos > 0:
                hit_stop = stop_lvl is not None and l[u] <= stop_lvl
                hit_tgt = tgt_lvl is not None and h[u] >= tgt_lvl
                if hit_stop:
                    ex_px = o[u] if o[u] < stop_lvl else stop_lvl   # gap-through @ open
                    _book(u, ex_px, pos, entry_px, entry_bar)
                    pos = 0; stop_lvl = tgt_lvl = None
                elif hit_tgt:
                    _book(u, tgt_lvl, pos, entry_px, entry_bar)
                    pos = 0; stop_lvl = tgt_lvl = None
            else:
                hit_stop = stop_lvl is not None and h[u] >= stop_lvl
                hit_tgt = tgt_lvl is not None and l[u] <= tgt_lvl
                if hit_stop:
                    ex_px = o[u] if o[u] > stop_lvl else stop_lvl   # gap-through @ open
                    _book(u, ex_px, pos, entry_px, entry_bar)
                    pos = 0; stop_lvl = tgt_lvl = None
                elif hit_tgt:
                    _book(u, tgt_lvl, pos, entry_px, entry_bar)
                    pos = 0; stop_lvl = tgt_lvl = None

        # 3) signal evaluation at u's close -> new pending for u+1. Entries (with
        #    reversal capability) take priority over the standalone exit branches —
        #    see judgment call #3 on why the exit branches are live only in "long" mode.
        new_pending = None
        if long_entry_sig[u] and pos <= 0:
            new_pending = 1
        elif allow_short and short_entry_sig[u] and pos >= 0:
            new_pending = -1
        elif long_exit_sig[u] and pos > 0:
            new_pending = 0
        elif allow_short and short_exit_sig[u] and pos < 0:
            new_pending = 0
        pending = new_pending

        # 4) roll-seam eve: force flat at this day's final bar close, kill pending
        if di in force_exit_days and u == last_bar_of_day[di]:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar)
                pos = 0; stop_lvl = tgt_lvl = None
            pending = None

    # end of data: open trade DROPPED (never truncated)

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/MACDRSI_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT, FEE = 20.0, 0.533
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))].sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("MACDRSI 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: RSI14 30/70, lookback5, long, MACD12/26/9", dict()),
        ("lookback 10 (author's GitHub default)", dict(lookback=10)),
        ("both-direction (grid-only SAR mirror)", dict(direction="both")),
        ("long + SL 2% / TP 4% overlay", dict(sl_pct=0.02, tp_pct=0.04)),
    ]:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index,
                         return_trades=True, **kw)
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        net_usd = (r["total_pnl"] - FEE * r["num_trades"]) * MULT
        print("%-52s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(r["max_drawdown"] * MULT)))
    print("\nPoints-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")

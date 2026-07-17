"""
FLAWLESS 1.0 — TV round-13 port #9: "Flawless Victory Strategy - 15min BTC Machine
Learning Strategy" (by Trebor_Namor).

Source: https://www.tradingview.com/script/i3Uc79fF-Flawless-Victory-Strategy-15min-BTC-Machine-Learning-Strategy/
(Pine v4, 10.8K boosts). Ported for EDGE-LOG challenger round 13 (see TV_SWEEP.md).
MPL-2.0 license retained in the port notes; this file is a re-implementation, not a
copy of the Pine text.

HONEST CAVEAT (read before trusting a number out of this file): the author's own script
description says these three parameter sets were "hyper-optimized" on ONE YEAR of BTC
15-minute data. That is close to the textbook overfitting failure mode this round exists
to screen for -- a handful of published percentages (6.604% stop, 2.328% target, RSI
guards 42/70/76, ...) fit tight to a single symbol, a single timeframe, a single year.
Expect the walk-forward / lockbox to punish this hard; that is the point of running it,
not a bug in the port.

Published rules -- THREE independently-published versions, selected here by a `version`
param ("v1" default / "v2" / "v3"). All three are LONG-ONLY (long or flat -- no short
side in any version). In the original Pine, v1/v2/v3 are three separate boolean-toggle
inputs (the published default has only v1=true) that could technically all be enabled
at once, stacking overlapping order intent onto one shared "Long" position -- a
degenerate combination the author's own default never exercises. This port models the
sane, intended usage: pick exactly one version at a time.

  Shared indicators:
    RSI(14) Wilder on close (Pine's rma-based formula; same helper as BBRSI_1_0.py).
    MFI(14) on hlc3, volume-weighted: mfi = 100 - 100/(1 + upSum/downSum), where upSum /
      downSum are 14-bar trailing sums of (volume * hlc3) gated by the SIGN of
      change(hlc3) (a bar's volume*hlc3 counts toward upSum if hlc3 rose since the prior
      bar, downSum if it fell, 0 otherwise). NOTE this is NOT the textbook MFI (which
      sums the signed money-flow delta) -- it's what the Pine script literally computes.
      v3 needs volume; `run_backtest` returns None if version="v3" and volumes is None.
    BB(20, 1.0-sigma population) on close -> upper1/lower1 (v1 AND v3 both use this).
    BB(17, 1.0-sigma population) on close -> upper2/lower2 (v2 only).

  v1 (no SL/TP):
    BUY  = close < lower1  AND  rsi > rsi_buy_guard (42 published)
    SELL = close > upper1  AND  rsi > 70                              -> market close
    No stop, no target -- the opposite signal is the only exit.

  v2 (bracket):
    BUY  = close < lower2  AND  rsi > rsi_buy_guard (42 published)
    SELL = close > upper2  AND  rsi > 76                              -> market close
    PLUS a resting bracket from the entry (position-avg) price: stop = entry*(1-v2_sl%),
    limit = entry*(1+v2_tp%). Published 6.604% / 2.328%.

  v3 (bracket, MFI-gated):
    BUY  = close < lower1  AND  mfi < 60
    SELL = close > upper1  AND  rsi > 65  AND  mfi > 64                -> market close
    PLUS a bracket: stop = entry*(1-v3_sl%), limit = entry*(1+v3_tp%). Published 8.882%
    / 2.317%.

  BUY/SELL are LEVEL conditions (not crossovers) -- they can sit true for many bars in a
  row. Under Pine's pyramiding=0, that only matters on the FIRST bar the condition goes
  true while flat (or in-position, for the sell side): once filled, further true bars of
  the same-direction signal are simply no-ops (no pyramiding, no re-arming) because a
  plain market order always fills, so nothing is ever left "unfilled and re-armable".

Port semantics (house-honest, TV-parity):
  - BUY/SELL signals evaluate on bar t's CLOSE using bar-t indicator values. Entries and
    the signal-driven market close both fill at the NEXT bar's OPEN (Pine's default
    strategy.entry()/strategy.close() timing -- no calc_on_every_tick here); these are
    plain market orders with no price contingency, so they always fill.
  - The v2/v3 bracket (`strategy.exit` with stop+limit) is a SEPARATE, continuously
    resting order, independent of the market-close signal. Its stop/limit levels are
    fixed at the fill price the instant the entry fills (pyramiding 0 means
    position_avg_price never moves during a trade, so recomputing it every bar -- as
    Pine literally does -- yields the same fixed number every time). It only becomes
    checkable starting the bar AFTER the entry bar (mirrors ORB_3_1.py's stop-check
    timing: an order implied by bar X's close first acts on bar X+1's range). Checked
    stop-first (pessimistic -- if a bar's range could hit both, the stop is assumed
    first). A bar that opens beyond a level fills at that OPEN instead of the level: for
    the stop this is a WORSE fill (identical to ORB_3_1.py's gap-through-at-open
    convention); for the limit this is a BETTER fill (a natural, symmetric extension of
    the same open-aware logic -- ORB_3_1's own target code doesn't credit gaps on the
    target side, but a resting limit realistically should fill at the better price when
    the market gaps through it favorably). If a signal-driven market close and the
    bracket are both live on the same bar, the market close wins (it fills at the bar's
    literal open, which precedes any intrabar bracket touch).
  - Multi-day holds are intrinsic (no session/EOD flattening in the source). Positions
    are FORCE-FLATTENED at the close of the day before each detected NOADJ quarterly
    roll seam, and NO fill of any kind (entry, signal-close, OR bracket) may occur on
    that day (same guard + calibration as TTIBS_1_0.detect_roll_seams /
    BBRSI_1_0.detect_roll_seams, copied verbatim here -- house convention is every
    strategy plugin stays self-contained, no cross-imports). A trade still open when the
    loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363
    ES), same as every library strategy.

JUDGMENT CALL -- MFI's na guard is dead code, ported as-is: the Pine `_rsi(MFIupper,
MFIlower)` helper backing `mfi` writes its `MFIlower==0`/`MFIupper==0` special cases as
two standalone `if` STATEMENTS (not the ternary chain the built-in RSI two lines above it
correctly uses) that are never the function's last statement -- under Pine's
return-the-last-expression rule, they compute a value and throw it away. The function
therefore ALWAYS actually evaluates `100 - 100/(1 + MFIupper/MFIlower)`, unconditionally,
including when MFIlower==0 (Pine's float division by zero -> na). We port that AS WRITTEN
rather than the evidently-intended 100/0 clamp: `neg_sum` gets zero-values replaced with
NaN before the divide, so `mfi` goes NaN whenever the trailing 14 bars had zero down-bars,
and both `mfi<60` / `mfi>64` naturally read False there (NaN comparisons are False in
numpy, same convention as every other NaN-guarded comparison in this codebase) -- v3
simply withholds a signal during that stretch instead of forcing mfi=100. Flagged, not
silently "fixed".

Only `version`, `rsi_buy_guard`, and the four bracket percents are exposed as tunable
params -- every other level in the published script (RSI sell guards 70/76/65, MFI
guards 60/64, all indicator lengths) is a fixed constant per version, exactly as
published, per the round-13 port spec for this file.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
Needs volumes when version="v3" (the MFI guard); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'FLAWLESS 1.0 · TV#9 BB(1σ)+RSI long w/ optional brackets (Trebor_Namor)'
DESCRIPTION = ("Round-13 port of a 10.8K-boost TV script publishing THREE long-only "
               "BB(1-sigma)+RSI/MFI variants on 15m BTC: v1 = plain BB(20)+RSI, no "
               "stops. v2 = BB(17)+RSI + a 6.604%/2.328% bracket. v3 = BB(20)+MFI/RSI "
               "guards + an 8.882%/2.317% bracket. Author's own description says these "
               "were hyper-optimized on one year of data -- exactly the overfit pattern "
               "this round screens for.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.
# Original script targets 15m BTC; the port itself is instrument/timeframe-agnostic
# (BB/RSI/MFI are dimensionless, brackets are a % of entry price) -- tested here on the
# house's standard NQ 5m RTH dataset like every other round-13 challenger.

DEFAULT_PARAMS = {
    "version": {
        "default": "v1", "type": "str",
        "options": ["v1", "v2", "v3"],
        "label": "Published version",
        "tooltip": "v1 = BB(20,1.0)+RSI(14), no SL/TP (author's own default). v2 = "
                   "BB(17,1.0)+RSI w/ tighter guards + a fixed % bracket (stop 6.604% / "
                   "limit 2.328% of entry). v3 = BB(20,1.0)+MFI(14) buy guard, RSI+MFI "
                   "sell guard, + a fixed % bracket (stop 8.882% / limit 2.317%). v3 "
                   "needs volume data.",
    },
    "rsi_buy_guard": {
        "default": 42, "min": 20, "max": 60, "step": 1, "type": "int",
        "label": "RSI buy guard (v1/v2 only)",
        "tooltip": "Buy requires RSI(14) > this AND close below the lower BB. Published "
                   "default 42 for both v1 and v2 (shared -- the Pine source uses the "
                   "same 42 in both). v3 uses an MFI guard instead (fixed at 60, not "
                   "exposed as a param).",
    },
    "v2_sl": {
        "default": 6.604, "min": 0.5, "max": 20.0, "step": 0.001, "type": "float",
        "label": "v2 stop-loss % (from entry)",
        "tooltip": "v2 bracket stop, as a percent of the entry (position-avg) price. "
                   "Published default 6.604%. Only active when version=v2.",
    },
    "v2_tp": {
        "default": 2.328, "min": 0.2, "max": 15.0, "step": 0.001, "type": "float",
        "label": "v2 take-profit % (from entry)",
        "tooltip": "v2 bracket limit, as a percent of the entry price. Published "
                   "default 2.328%. Only active when version=v2.",
    },
    "v3_sl": {
        "default": 8.882, "min": 0.5, "max": 20.0, "step": 0.001, "type": "float",
        "label": "v3 stop-loss % (from entry)",
        "tooltip": "v3 bracket stop, as a percent of the entry price. Published "
                   "default 8.882%. Only active when version=v3.",
    },
    "v3_tp": {
        "default": 2.317, "min": 0.2, "max": 15.0, "step": 0.001, "type": "float",
        "label": "v3 take-profit % (from entry)",
        "tooltip": "v3 bracket limit, as a percent of the entry price. Published "
                   "default 2.317%. Only active when version=v3.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "version": ["v1", "v2", "v3"], "rsi_buy_guard": [42],
        "v2_sl": [6.604], "v2_tp": [2.328],
        "v3_sl": [8.882], "v3_tp": [2.317],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.9):
    # version x rsi_buy_guard x v2_sl x v2_tp = 2x2x2x2 = 16 cells. v3_sl/v3_tp held at
    # published defaults (not swept here); v1 cells differ only on rsi_buy_guard since
    # v1 ignores the bracket knobs entirely -- duplicate v1 rows across the v2_sl/v2_tp
    # axis are harmless (cost seconds, not correctness).
    "Medium (author-knob grid)": {
        "version": ["v1", "v2"], "rsi_buy_guard": [42, 50],
        "v2_sl": [6.604, 3.302], "v2_tp": [2.328, 4.656],
        "v3_sl": [8.882], "v3_tp": [2.317],
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
    version: str = "v1",
    rsi_buy_guard: int = 42,
    v2_sl: float = 6.604, v2_tp: float = 2.328,
    v3_sl: float = 8.882, v3_tp: float = 2.317,
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

    version = str(version).strip().lower()
    if version not in ("v1", "v2", "v3"):
        version = "v1"

    vol = None
    if version == "v3":
        if volumes is None:
            return None                # v3's MFI guard needs volume
        vol = np.asarray(volumes, float)
        if len(vol) != n:
            return None

    rsi_buy_guard = float(rsi_buy_guard)
    v2_sl_frac = float(v2_sl) / 100.0; v2_tp_frac = float(v2_tp) / 100.0
    v3_sl_frac = float(v3_sl) / 100.0; v3_tp_frac = float(v3_tp) / 100.0

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    rsi = _wilder_rsi(c, 14)

    s = pd.Series(c)
    basis1 = s.rolling(20).mean(); dev1 = 1.0 * s.rolling(20).std(ddof=0)
    upper1 = (basis1 + dev1).to_numpy(); lower1 = (basis1 - dev1).to_numpy()
    basis2 = s.rolling(17).mean(); dev2 = 1.0 * s.rolling(17).std(ddof=0)
    upper2 = (basis2 + dev2).to_numpy(); lower2 = (basis2 - dev2).to_numpy()

    if version == "v1":
        with np.errstate(invalid="ignore"):
            buy_sig = (c < lower1) & (rsi > rsi_buy_guard)
            sell_sig = (c > upper1) & (rsi > 70.0)
        has_bracket = False
        sl_frac = tp_frac = 0.0
    elif version == "v2":
        with np.errstate(invalid="ignore"):
            buy_sig = (c < lower2) & (rsi > rsi_buy_guard)
            sell_sig = (c > upper2) & (rsi > 76.0)
        has_bracket = True
        sl_frac, tp_frac = v2_sl_frac, v2_tp_frac
    else:  # v3
        tp3 = (h + l + c) / 3.0
        d_tp3 = np.empty(n); d_tp3[:] = np.nan
        d_tp3[1:] = tp3[1:] - tp3[:-1]
        raw_flow = vol * tp3
        with np.errstate(invalid="ignore"):
            pos_flow = np.where(d_tp3 > 0, raw_flow, 0.0)
            neg_flow = np.where(d_tp3 < 0, raw_flow, 0.0)
        pos_sum = pd.Series(pos_flow).rolling(14).sum().to_numpy()
        neg_sum_s = pd.Series(neg_flow).rolling(14).sum().replace(0.0, np.nan)
        neg_sum = neg_sum_s.to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            mfi = 100.0 - 100.0 / (1.0 + pos_sum / neg_sum)
        with np.errstate(invalid="ignore"):
            buy_sig = (c < lower1) & (mfi < 60.0)
            sell_sig = (c > upper1) & (rsi > 65.0) & (mfi > 64.0)
        has_bracket = True
        sl_frac, tp_frac = v3_sl_frac, v3_tp_frac

    warm = max(120, 60)
    buy_sig[:warm] = False
    sell_sig[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI_1_0 / TTIBS_1_0) ───
    bounds = _session_bounds(did, n)
    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    force_exit_days = {sd - 1 for sd in seam_days if sd - 1 >= 0}   # daily index
    day_of_bar = np.empty(n, int)
    last_bar_of_day = {}
    for di, (a, b) in enumerate(bounds):
        day_of_bar[a:b] = di
        last_bar_of_day[di] = b - 1
    blocked_days = set(force_exit_days)                              # no fills on seam eve

    # ── event loop ────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    stop_lvl = tp_lvl = 0.0
    pending = None            # "buy" | "close" | None -- both are plain market orders
    pnl_list, trade_log = [], []

    def _book(exit_bar_i, exit_price, ep, eb):
        pnl = exit_price - ep          # long-only
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(eb), int(exit_bar_i), float(pnl), 1,
                              float(ep), float(exit_price)))

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        di = day_of_bar[u]
        blocked = di in blocked_days

        # 1) pending market order fill attempt, AT u's OPEN (queued at u-1's close)
        if pending is not None:
            if not blocked:
                if pending == "buy" and pos == 0:
                    pos = 1; entry_px = o[u]; entry_bar = u
                    if has_bracket:
                        stop_lvl = entry_px * (1.0 - sl_frac)
                        tp_lvl = entry_px * (1.0 + tp_frac)
                elif pending == "close" and pos == 1:
                    _book(u, o[u], entry_px, entry_bar)
                    pos = 0
            pending = None                          # market order always resolves this bar
            # (either filled, or suppressed on a blocked/seam-eve day)

        # 2) bracket check, intrabar (v2/v3 only), starting the bar AFTER entry
        if pos == 1 and has_bracket and u > entry_bar and not blocked:
            if l[u] <= stop_lvl:                                # stop first (pessimistic)
                ex_px = o[u] if o[u] < stop_lvl else stop_lvl    # gap-through -> open
                _book(u, ex_px, entry_px, entry_bar)
                pos = 0; pending = None
            elif h[u] >= tp_lvl:
                ex_px = o[u] if o[u] > tp_lvl else tp_lvl        # gap-through -> open (better)
                _book(u, ex_px, entry_px, entry_bar)
                pos = 0; pending = None

        # 3) signal evaluation at u's close -> queue next bar's market order
        if pos == 0 and buy_sig[u]:
            pending = "buy"
        elif pos == 1 and sell_sig[u]:
            pending = "close"

        # 4) roll-seam eve: force flat at this day's final bar close, kill pending
        if di in force_exit_days and u == last_bar_of_day[di]:
            if pos != 0:
                _book(u, c[u], entry_px, entry_bar)
                pos = 0
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/FLAWLESS_1_0.py
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

    print("FLAWLESS 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-58s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 106)
    for label, kw in [
        ("v1 published (BB20 1.0s+RSI 42/70, no SL/TP)", dict(version="v1")),
        ("v2 published (BB17 1.0s+RSI 42/76, bracket 6.6/2.3%)", dict(version="v2")),
        ("v3 published (BB20 1.0s+MFI/RSI guards, bracket 8.9/2.3%)", dict(version="v3")),
        ("v1, RSI buy guard 50 (stricter, robustness read)", dict(version="v1", rsi_buy_guard=50)),
    ]:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, volumes=df["volume"].values,
                         day_id=day_id, index=df.index,
                         return_trades=True, **kw)
        if r is None:
            print("%-58s  NO TRADES" % label); continue
        net_usd = (r["total_pnl"] - FEE * r["num_trades"]) * MULT
        print("%-58s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(r["max_drawdown"] * MULT)))
    print("\nPoints-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")

"""
ORB 4.0 — PRIOR-DAY RANGE GATE on the run #234 machinery.

Owner 2026-08-18: "try new things". This is the first ORB variant in the program whose
entry LEVELS are informed by anything outside today's opening range.

WHY. A diagnostic on run #234's own 2,607 trades split them by where the fill sat
relative to YESTERDAY's high/low:

    bucket             n     IS avg   IS PF     LB avg   LB PF
    beyond PD range  1049      $159    1.40       $633    1.67
    inside PD range  1337       $99    1.21       $271    1.21

"Beyond" beats "inside" on average AND on profit factor in BOTH windows — the rare
factor in this program that ranks the same way twice (compare X15-X19, which never did).
The prior session's high/low is complete at 09:30, so gating on it is fully legal.

THE MECHANISM THAT MAKES THIS MORE THAN A FILTER. Screening those trades post-hoc
(just deleting the "inside" half) LOWERS MAR 13.38 -> 11.56: it halves the money to buy
a smaller drawdown, which is the amputation ORB.md has rejected since items B and M.
But a gate INSIDE the strategy is a different animal. When an early breakout is rejected
for sitting inside yesterday's range, the scan CONTINUES — so if price later clears the
prior-day level, that session still trades, just at a better location. The gate converts
"bad early entry" into "later, better entry" rather than into "no trade". Whether that
conversion actually pays is exactly what this file exists to measure.

    pdr_gate 0 = off  (bit-identical to ORB_3_6 — asserted in the smoke test)
    pdr_gate 1 = require the fill to be beyond the prior session's high (long) / low (short)
    pdr_gate 2 = require it to be beyond prior high/low OR beyond the OPPOSITE extreme
                 (i.e. anything except sitting inside yesterday's range)

VERDICT 2026-08-18: DEAD. Measured on run #230's window, ride+BE exit, gate off/1/2:

    gate  n      IS net      LB net   LB PF    full net    maxDD    MAR   roll12 win / worst
    0     2607   $300,931    $88,942  1.453    $389,874    $29,142  13.38   72.7%  -$22,050
    1     1582   $199,585    $40,990  1.342    $240,575    $20,681  11.63   70.5%   -$9,204
    2     1796   $216,235    $52,459  1.394    $268,694    $40,346   6.66   68.9%  -$32,172

The gate buys a smaller drawdown and a much softer worst-year, and pays for it with well
over a third of the money, a worse lockbox, worse PF and worse rolling-window consistency.
MAR falls in both live settings. Not adoptable.

WHY IT FAILED, AND THE LESSON WORTH KEEPING. Gate 1 takes 1,582 trades where the post-hoc
screen of the same factor kept only 1,049 — the extra ~530 are sessions where an early
signal was rejected and a LATER bar cleared yesterday's level. Those deferred trades are
bad enough to drag the whole config below even the screened subset. So the mechanism this
file was built to test — "convert a bad early entry into a later, better one" — is real
but runs the WRONG WAY: by the time price has cleared yesterday's level, the move is
extended and the R-geometry is spent. That is the same failure ORB.md section 4.18 found
for close-confirm on the old base: the damage is the confirmation DELAY, not the level.

It also reframes the diagnostic that motivated the file. "Beyond the prior-day range" looked
predictive because trades that RUN far tend to end up beyond that level — the split was
mostly selection after the fact, not a condition you can profitably require in advance.

Kept in the library as a working, parity-asserted implementation so nobody rebuilds it.

LIVE-LEGAL BY CONSTRUCTION: the prior session's high and low are fixed before this
session's first bar. Entry is still a finished-bar-close decision; BE still arms on a
finished close and acts next bar; stop-first + gap-through fills unchanged. Nothing on
any fill bar is read before it exists.
"""
import numpy as np

STRATEGY_NAME = 'ORB 4.0 · prior-day range gate'
DESCRIPTION   = ("The legal ORB base (close-confirm capable, v-pace/ATR-regime gates, "
                 "partial+trail scale-out) plus ONE new lever: move the stop to entry "
                 "once a bar CLOSES beyond be_after_R x risk. Armed on a finished bar, "
                 "acts from the next bar - live-legal. be_after_R=0 reproduces ORB_3_4 "
                 "exactly. Built to offer run #230's champion the -33%-DD lever the "
                 "old (voided) touch-entry family proved out.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars": {
        "default": 2, "min": 1, "max": 12, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "Opening-range length in BARS. On 5-min data: 1=5min, 2=10min, 3=15min.",
    },
    "trade_mode": {
        "default": "First-candle dir", "type": "str",
        "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either break. First-candle dir = only the way the "
                   "opening-range candle closed (the grail hunt's sole aggregate survivor).",
    },
    "stop_frac": {
        "default": 2.0, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range width. "
                   "FLOOR is 0.5 on purpose: below that the exact-stop-fill assumption "
                   "inflates PF.",
    },
    "vpace_filter": {
        "default": 0.7, "min": 0.0, "max": 1.4, "step": 0.1, "type": "float",
        "label": "Volume-pace gate (× trailing norm)",
        "tooltip": "Require the session's volume SO FAR (bars before this one) to be at "
                   "least this multiple of the same-length prefix averaged over the prior "
                   "20 sessions. LIVE-LEGAL: the fill bar's own volume is never read. 0=off.",
    },
    "breakout_buf": {
        "default": 0.25, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": "Require price to clear the range edge by this fraction of the range "
                   "width before entering. 0 = trade the touch.",
    },
    "close_confirm": {
        "default": True, "type": "bool",
        "label": "Close-confirmed entry (skip false wicks)",
        "tooltip": "ON (default) = only enter when a bar CLOSES beyond the edge, filling at "
                   "that close - the live-legal entry the grail hunt certified. OFF = touch "
                   "entry (models a resting stop; legal fill, but pairs with intrabar "
                   "quantities in ways the audit flagged - keep ON unless researching).",
    },
    "partial_exit_R": {
        "default": 3.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF at this R-multiple of initial risk. Remaining half trails / "
                   "rides. 0 = single lot.",
    },
    "trail_bars": {
        "default": 3, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). If a "
                   "partial is set, activates after it fires. 0 = fixed stop.",
    },
    # ── THE new lever ─────────────────────────────────────────────────────────
    "be_after_R": {
        "default": 0.0, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. The voided touch-entry "
                   "study found a robust 0.9-1.3R plateau (DD −33%); this re-asks that "
                   "question on the legal base. 0 = off (= ORB_3_4 exactly).",
    },
    # ── Inherited 3.0/3.4 knobs ───────────────────────────────────────────────
    "atr_filter": {
        "default": 0.7, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
        "label": "Vol-regime filter (× trailing median, 0=off)",
        "tooltip": "Skip a session when its recent 5-session avg range is BELOW this "
                   "multiple of the trailing 60-session median session range. Trailing-only.",
    },
    "target_R": {
        "default": 5.5, "min": 0.0, "max": 8.0, "step": 0.5, "type": "float",
        "label": "Runner target (× risk, 0=EOD/trail only)",
        "tooltip": "Optional hard take-profit for the runner at this multiple of initial "
                   "risk. 0 = ride to trail-out / close.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
    "pdr_gate": {
        "default": 0, "min": 0, "max": 2, "step": 1, "type": "int",
        "label": "Prior-day range gate (0=off)",
        "tooltip": "0 = off. 1 = only fill beyond YESTERDAY's high (long) / low (short). "
                   "2 = fill anywhere except inside yesterday's range. A rejected bar does "
                   "not end the session - the scan continues, so a later bar that clears "
                   "the level can still trade. Yesterday's range is complete at 09:30, so "
                   "this is live-legal.",
    },
    "skip_holidays": {
        "default": True, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close sessions, detected by session LENGTH. Calendar-known.",
    },
}

PARAM_GRID_PRESETS = {
    # THE hypothesis test: hold run #230's champion FIXED, sweep ONLY the new lever.
    # 9 combos incl. the be=0 control (= the champion itself, bit-identical).
    "Short  (BE scan on the #230 champion)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.0],
        "vpace_filter": [0.7], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [3.0], "trail_bars": [3], "target_R": [5.5],
        "atr_filter": [0.7], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0],
    },
    # Adds modest base breadth around the BE scan for an auto search.
    "Medium (BE + nearby base)": {
        "or_bars": [2, 3], "trade_mode": ["First-candle dir"], "stop_frac": [1.5, 2.0],
        "vpace_filter": [0.7], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [2.5, 3.0], "trail_bars": [3, 5], "target_R": [5.5],
        "atr_filter": [0.7], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.0, 0.8, 1.0, 1.2, 1.5],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 2, trade_mode: str = "First-candle dir",
    stop_frac: float = 2.0, vol_filter: float = 0.0, vpace_filter: float = 0.7,
    breakout_buf: float = 0.25, close_confirm: bool = True,
    partial_exit_R: float = 3.0, trail_bars: int = 3, be_after_R: float = 0.0,
    atr_filter: float = 0.7, target_R: float = 5.5,
    pdr_gate: int = 0,
    flat_eod: bool = True, skip_holidays: bool = True,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    allow_long  = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    # ── Session boundaries ────────────────────────────────────────────────────
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b

    # ── Half-day / holiday skip (skip_holidays) ───────────────────────────────
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    # ── Vol-regime filter (atr_filter > 0): trailing-only, no look-ahead ──────
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue                          # warm-up → allow
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    # ── V-PACE filter (legal): prior bars vs prior-20-session prefix norm ─────
    _pace_ord, _pace_ref = {}, None
    if vpace_filter > 0 and v is not None and len(_sess_bounds) > 21:
        _pace_ord = {a: si for si, (a, b) in enumerate(_sess_bounds)}
        _K = max(b - a for a, b in _sess_bounds)
        _pref = np.full((len(_sess_bounds), _K + 1), np.nan)
        for _si, (a, b) in enumerate(_sess_bounds):
            _cs = np.cumsum(np.asarray(v[a:b], dtype=float))
            _pref[_si, 1:(b - a) + 1] = _cs / np.arange(1, (b - a) + 1)
        _pace_ref = np.full_like(_pref, np.nan)
        for _si in range(20, len(_sess_bounds)):
            _pace_ref[_si, :] = np.nanmean(_pref[_si - 20:_si, :], axis=0)

    # ── PRIOR-DAY RANGE (pdr_gate > 0): yesterday's high/low, complete before this
    #    session opens, so gating a fill on it reads nothing that does not yet exist.
    _pd_hi, _pd_lo = {}, {}
    if pdr_gate > 0:
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si == 0:
                continue
            _pa, _pb = _sess_bounds[_si - 1]
            _pd_hi[a] = float(h[_pa:_pb].max())
            _pd_lo[a] = float(l[_pa:_pb].min())

    pnl_list, trade_log = [], []
    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if i in _holiday_start:                  # half-day / holiday skip
            i = j; continue
        if _allow_start.get(i, True) is False:   # vol-regime filter skipped this session
            i = j; continue
        if m > or_bars + 1 and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            sv = v[i:j] if v is not None else None
            or_hi = sh[:or_bars].max()
            or_lo = sl[:or_bars].min()
            rng   = or_hi - or_lo
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf    = breakout_buf * rng
                up_lvl = or_hi + buf
                dn_lvl = or_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                be_armed = False; be_lvl = np.nan
                for k in range(or_bars, m):
                    if pos == 0:
                        if close_confirm:
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        else:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # LEGAL v-pace gate — inputs closed BEFORE this bar.
                        if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                            _si2 = _pace_ord.get(i)
                            if _si2 is not None and k < _pace_ref.shape[1]:
                                _rf = _pace_ref[_si2, k]
                                if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                    continue
                        # legacy look-ahead filter — OFF, kept only for 3.1 parity by hand.
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                            # PRIOR-DAY GATE: reject this bar but KEEP SCANNING, so a later
                            #   bar that does clear yesterday's level can still take the trade.
                            if pdr_gate > 0 and i in _pd_hi:
                                _ph, _pl = _pd_hi[i], _pd_lo[i]
                                if pdr_gate == 1 and not (entry > _ph):
                                    continue
                                if pdr_gate == 2 and (_pl < entry < _ph):
                                    continue
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            if pdr_gate > 0 and i in _pd_lo:
                                _ph, _pl = _pd_hi[i], _pd_lo[i]
                                if pdr_gate == 1 and not (entry < _pl):
                                    continue
                                if pdr_gate == 2 and (_pl < entry < _ph):
                                    continue
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                    else:
                        # ── BREAKEVEN (the 3.6 lever): armed on a PRIOR bar's close,
                        #    applied here — i.e. from the bar AFTER the arming close.
                        #    Legal: only finished bars are read.
                        if be_armed:
                            stop = max(stop, entry) if pos > 0 else min(stop, entry)
                        # ── Trailing stop: prior bars' extremes only (excludes k).
                        if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                            ts = max(ek, k - trail_bars)
                            if pos > 0:
                                trail_low = sl[ts:k].min() if k > ts else sl[ek]
                                stop = max(stop, trail_low)   # only move up
                            else:
                                trail_high = sh[ts:k].max() if k > ts else sh[ek]
                                stop = min(stop, trail_high)  # only move down

                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                ex_px = so[k] if so[k] < stop else stop   # gap-through
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                            # arm BE off this bar's CLOSE — takes effect next bar.
                            # (checked before the partial's `continue` so a partial-fire
                            #  bar can still arm; ordering is state-neutral this bar.)
                            if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                if pos != 0:                                        # EOD flat
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
        i = j

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
# Smoke test: (1) be_after_R=0 must be BIT-IDENTICAL to ORB_3_4.py on the #230
# champion params; (2) be_after_R>0 must actually change results.
# Run:  python augur_strategies/ORB_3_6.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER  = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)

    spec = ilu.spec_from_file_location("_orb34", os.path.join(ROOT, "augur_strategies", "ORB_3_4.py"))
    base = ilu.module_from_spec(spec); spec.loader.exec_module(base)

    C230 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, breakout_buf=0.25,
                close_confirm=True, partial_exit_R=3.0, trail_bars=3, target_R=5.5,
                atr_filter=0.7, vpace_filter=0.7, flat_eod=True, skip_holidays=True)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **C230)
    r1 = run_backtest(*args, **kw, **C230, be_after_R=0.0)
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("be=0 parity vs ORB_3_4: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **C230, be_after_R=1.0)
    print("be=1.0 changes results: %s  (pnl %.1f -> %.1f, DD %.1f -> %.1f)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r2["total_pnl"], r1["max_drawdown"], r2["max_drawdown"]))
    sys.exit(0 if same else 1)

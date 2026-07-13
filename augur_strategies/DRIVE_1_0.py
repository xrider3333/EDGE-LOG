"""
DRIVE 1.0 — first-hour intraday momentum.

Concept: at the close of bar `dr_bars` (12 on 5m data = the first 60 minutes of the
session), read the direction of the move so far — sign(close[dr_bars-1] - open[0]).
Enter AT THE OPEN of the very next bar (bar index `dr_bars`) in that direction. The
initial stop sits `stop_frac` × the first-hour's high-low range away from entry.
From there: an optional take-profit at `target_R` × initial risk, an optional N-bar
prior-extreme trailing stop (identical semantics to ORB 3.1's runner trail — uses
PRIOR bars' sl/sh, only tightens, never loosens), or (the deploy default) just ride
the position to the session's last close. Exactly one trade per session — the whole
strategy is a single go/no-go decision made once, at bar `dr_bars`.

Exits are ORB-3.0/3.1-identical: the stop is checked FIRST each bar (pessimistic —
a bar that could hit either the stop or the target is scored as the stop), and a
bar that GAPS THROUGH the stop fills at that bar's open rather than the stop price
(no free "exact fill" on a gap).

Research provenance: triaged 2026-07-13 against three intraday-momentum alternatives
(PDX/NDAY prior-level breaks, LDM late-day momentum) in scratchpad/triage_new_strats.py
— DRIVE was the strongest of the four on MAR. Deep-swept 810 configs (dr_bars x thr x
stop_frac x trail_bars x target_R) in scratchpad/drive_deep.py: the sweep found a wide,
parameter-insensitive plateau at dr_bars=12, stop_frac 0.5-1.0, trail_bars=0 (10/20-bar
trails stay mostly dead, same finding as ORB's own trail research) — not a razor peak.

Deploy candidate (frozen for walk-forward / lockbox): dr_bars=12, thr=0 (trade every
qualifying session), stop_frac=0.75, target_R=0 (ride to close), trail_bars=0.
Pre-lockbox (NQ 5m RTH, db_noadj_rth, 2010-06-07 -> 2025-06-29, cost_pts=0.533):
n=3850, net=$295,437, PF=1.18, DD=-$33,712.

Known context splits (from the deep sweep, same pre-lockbox window):
  - gap_align: PF 1.26 when the overnight gap agrees in sign with the drive vs
    PF 1.08 when it disagrees. gap_align defaults OFF (deploy candidate keeps every
    session) — this is a tilt to consider, not a cut to make blindly.
  - Day-of-week: Friday is the strongest session, Wednesday the weakest.
  - Daily-PnL correlation vs the ORB 3.1 champion ~ 0.23 — DRIVE reads as a genuine
    diversifier against the current champion, not a redundant copy of it.

thr (drive-strength filter, default OFF): requires |drive| >= thr x the median
|drive| of the LAST 20 prior qualifying sessions (a trailing, no-look-ahead
reference). Sessions before 20 prior qualifying sessions exist are skipped whenever
thr > 0. The drive-history buffer is updated for EVERY session with m > dr_bars
bars, regardless of whether that session ends up trading (matches the research
code's drv_hist.append behaviour exactly) — thr, gap_align and trade_mode filter
whether a session TRADES, never whether it feeds the trailing-median reference.

PNL = SHARES*(EXIT-ENTRY); fees (cost_pts) are applied downstream by the engine,
not inside this file.
"""
import numpy as np

STRATEGY_NAME = 'DRIVE 1.0 · first-hour momentum'
DESCRIPTION   = ("First-hour drive momentum: direction = sign of the first dr_bars "
                 "bars' move, enter at the next bar's open, stop = stop_frac x the "
                 "first-hour range, optional target_R / N-bar trail, else ride to "
                 "the close. One trade per session. NQ 5m default.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Not a fork of the ORB family — a from-scratch concept triaged against ORB/ENGU-Q,
# so (deliberately) no _AUGUR_PARENT.

DEFAULT_PARAMS = {
    "dr_bars": {
        "default": 12, "min": 3, "max": 24, "step": 1, "type": "int",
        "label": "Drive window (bars)",
        "tooltip": "How much of the open decides direction; 12 = first hour on 5m.",
    },
    "thr": {
        "default": 0.0, "min": 0.0, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Drive threshold (x trailing 20-session median |drive|, 0=off)",
        "tooltip": "thr>0: require |drive| >= thr x median(|drive| of the LAST 20 "
                   "prior sessions). Sessions before 20 prior qualifying sessions "
                   "exist are skipped whenever thr>0. 0 = trade every qualifying "
                   "session (deploy default).",
    },
    "stop_frac": {
        "default": 0.75, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Stop (x first-hour range)",
        "tooltip": "Stop distance from entry as a multiple of the first dr_bars "
                   "bars' high-low range. FLOOR is 0.5 on purpose — same fill-artifact "
                   "rationale as ORB: below that the backtest's exact-stop-fill "
                   "assumption inflates PF (tight stops get whipsawed/gapped in "
                   "reality, this engine can't model that at sub-0.5 distances).",
    },
    "target_R": {
        "default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Target (x risk, 0 = ride to close)",
        "tooltip": "Optional take-profit at this multiple of initial risk "
                   "(entry-to-stop). 0 = let it ride to the session close.",
    },
    "trail_bars": {
        "default": 0, "min": 0, "max": 30, "step": 1, "type": "int",
        "label": "N-bar trailing stop (0=off)",
        "tooltip": "Trail the stop to the rolling N-bar prior low (long) / high "
                   "(short); stop only moves favorably, never loosens. Research "
                   "shows off (0) is best for this entry — the deep sweep found "
                   "10/20-bar trails mostly dead, same as ORB's own trail research.",
    },
    "gap_align": {
        "default": False, "type": "bool",
        "label": "Require gap-aligned drive",
        "tooltip": "Only trade when the overnight gap (today's open minus prior "
                   "session close) agrees in sign with the drive — research: PF 1.25 "
                   "aligned vs 1.10 opposed. Off = deploy default; tilt, don't cut.",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Both", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade whichever way the drive points (most two-sided). "
                   "Long/Short Only for research.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
    "skip_holidays": {
        "default": False, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close / half-day sessions (Thanksgiving, Christmas Eve, "
                   "Memorial Day, July-3, etc). Detected by session LENGTH (a half-day "
                   "has far fewer bars than a normal RTH day) — no calendar needed. "
                   "OFF by default = no change; turn ON to avoid them.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (core plateau)": {
        "dr_bars": [12], "thr": [0.0], "stop_frac": [0.5, 0.75, 1.0],
        "target_R": [0.0, 3.0], "trail_bars": [0], "gap_align": [False],
    },
    "Medium (window + filter)": {
        "dr_bars": [6, 9, 12, 15, 18], "thr": [0.0, 0.5, 1.0],
        "stop_frac": [0.5, 0.75, 1.0, 1.25], "target_R": [0.0, 3.0],
        "trail_bars": [0], "gap_align": [False, True],
    },
    "Long   (full)": {
        "dr_bars": [6, 9, 12, 15, 18], "thr": [0.0, 0.5, 1.0, 1.5],
        "stop_frac": [0.5, 0.6, 0.75, 1.0, 1.25, 1.5], "target_R": [0.0, 3.0, 5.0],
        "trail_bars": [0, 10, 20], "gap_align": [False, True],
        "trade_mode": ["Both", "Long Only", "Short Only"],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    dr_bars: int = 12, thr: float = 0.0, stop_frac: float = 0.75,
    target_R: float = 0.0, trail_bars: int = 0, gap_align: bool = False,
    trade_mode: str = "Both",
    flat_eod: bool = True, skip_holidays: bool = False,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    allow_long  = trade_mode in ("Both", "Long Only")
    allow_short = trade_mode in ("Both", "Short Only")

    # ── Session boundaries ────────────────────────────────────────────────────
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b

    # ── Half-day / holiday skip (skip_holidays): a half-day session has far fewer
    #    bars than a normal RTH day. Flag sessions shorter than 70% of the MEDIAN
    #    session length (timeframe-agnostic, no calendar needed). Identical helper
    #    to ORB_3_0/3_1. A flagged session is skipped ENTIRELY — it doesn't trade,
    #    and (matching the ORB `i = j; continue` convention) it also doesn't feed
    #    the drive-history / prior-close state below. OFF by default.
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    pnl_list, trade_log = [], []
    drv_hist = []          # trailing history of raw `drive` values, for the thr filter
    prev_close = None      # prior (non-skipped) session's last close, for gap_align
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

        so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]

        if m > dr_bars + 3:
            drive  = sc[dr_bars - 1] - so[0]
            fh_rng = sh[:dr_bars].max() - sl[:dr_bars].min()

            ok = True
            if thr > 0:
                if len(drv_hist) < 20:
                    ok = False
                else:
                    ref = np.median(np.abs(drv_hist[-20:]))
                    ok = abs(drive) >= thr * ref

            if ok and drive != 0 and fh_rng > 0:
                pos = 1 if drive > 0 else -1
                dir_ok = (pos > 0 and allow_long) or (pos < 0 and allow_short)

                gap_ok = True
                if gap_align:
                    if prev_close is None:
                        gap_ok = False               # no prior session to compare
                    else:
                        gap = so[0] - prev_close
                        gap_ok = gap != 0 and (gap > 0) == (drive > 0)

                if dir_ok and gap_ok:
                    entry = so[dr_bars]                          # market at next bar's open
                    risk_dist = stop_frac * fh_rng
                    stop = entry - pos * risk_dist
                    target = (entry + pos * target_R * risk_dist) if target_R > 0 else None

                    ek = dr_bars
                    exit_k = None; exit_px = None
                    for k in range(ek + 1, m):
                        if trail_bars > 0:
                            ts = max(ek, k - trail_bars)
                            if pos > 0:
                                stop = max(stop, sl[ts:k].min() if k > ts else sl[ek])
                            else:
                                stop = min(stop, sh[ts:k].max() if k > ts else sh[ek])
                        if pos > 0:
                            if sl[k] <= stop:                     # stop first (pessimistic)
                                # Gap-through realism: if the bar OPENED below the stop,
                                # a stop order fills at the open, not the stop price.
                                ex = so[k] if so[k] < stop else stop
                                exit_k, exit_px = k, ex
                                break
                            if target is not None and sh[k] >= target:
                                exit_k, exit_px = k, target
                                break
                        else:
                            if sh[k] >= stop:
                                ex = so[k] if so[k] > stop else stop  # gap-through
                                exit_k, exit_px = k, ex
                                break
                            if target is not None and sl[k] <= target:
                                exit_k, exit_px = k, target
                                break
                    if exit_k is None:                            # EOD flat
                        exit_k, exit_px = m - 1, sc[m - 1]

                    pnl = (exit_px - entry) if pos > 0 else (entry - exit_px)
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((i + ek, i + exit_k, pnl, pos, entry))

            # Drive history is updated for EVERY qualifying session (m > dr_bars),
            # independent of thr/dir/gap filtering — matches the research code.
            if m > dr_bars:
                drv_hist.append(drive)

        prev_close = sc[-1]
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
# Smoke test — runs the frozen deploy candidate on the NQ 5m RTH master through
# the real engine (pre-lockbox only) and checks it against the reference numbers
# from scratchpad/triage_new_strats.py + scratchpad/drive_deep.py.
#   Run:  python augur_strategies/DRIVE_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from augur_engine.engine import run_backtest as eng_bt

    PRELOCK_TO = "2025-06-29"     # lockbox = 2025-06-30 -> 2026-06-30, NEVER touched here
    FEE, MULT = 0.533, 20.0       # NQ costs: 0.533 pts/RT, $20/pt

    deploy = dict(dr_bars=12, thr=0.0, stop_frac=0.75, target_R=0.0, trail_bars=0,
                  gap_align=False, trade_mode="Both", flat_eod=True, skip_holidays=False)

    r = eng_bt("DRIVE_1_0.py", instrument="NQ", timeframe="5m", session="rth",
               source="db_noadj_rth", cost_pts=FEE, date_to=PRELOCK_TO, params=deploy)

    if r is None:
        print("NO TRADES / no master found — check augur_uploads/ + optimizer_history.db")
        sys.exit(1)

    n   = r["num_trades"]
    net = r["total_pnl"] * MULT
    pf  = r["profit_factor"]
    dd  = r["max_drawdown"] * MULT

    print("DRIVE 1.0 deploy candidate - NQ 5m RTH, pre-lockbox (<= %s)" % PRELOCK_TO)
    print("  params: %s" % deploy)
    print("  got:      n=%d net=$%s PF=%.2f DD=$%s" % (n, format(net, ",.0f"), pf, format(dd, ",.0f")))
    print("  expected: n=3850 net=$295,437 PF=1.18 DD=-$33,712")

    ok = (n == 3850 and abs(net - 295437) < 1 and abs(pf - 1.18) < 0.01 and abs(dd + 33712) < 1)
    print("  SMOKE TEST: %s" % ("PASS" if ok else "FAIL"))

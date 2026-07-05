"""
DISCRETIONARY REPLAY — feed the engine a list of trades you actually took.

Every other strategy in this folder INVENTS its own entries from price (ORB breaks
out, ENGU spots an engulfing candle, ...). This one does the opposite: you hand it a
CSV of the entries you took by feel — a timestamp and a side per row — and it "enters"
at those exact bars, then either replays your real exit (if you logged one) or manages
the trade mechanically (a fixed stop / target / end-of-day flat). The point is NOT to
discover a strategy; it is to run YOUR discretionary trades through the same machinery
as everything else so the gate, edge-significance test, and all 45 validation checks
can answer one honest question: **does my eye have measurable edge?**

Because it emits a normal trade list, it flows straight into the ML gate (which learns
which of your entries to keep) and run_validate (edge-significance, conformal band,
etc.) with zero extra wiring.

── CSV FORMAT ──────────────────────────────────────────────────────────────────────
Drop a file under  augur_uploads/replay/<name>.csv  (or give a full path). Header row,
then one trade per row. Column names are case-insensitive; only the first two are
required:

    timestamp,   side,   exit_time,        stop_pts, target_pts
    2024-03-11 09:35, long, 2024-03-11 10:05,       ,
    2024-03-12 14:10, short,               ,        20,   40

  timestamp / entry_time  (required) : when you entered (any parseable datetime).
  side / direction        (required) : long|short|buy|sell|1|-1.
  exit_time               (optional) : when you exited -> "as-taken" replay of YOUR
                                        trade. If blank, the trade is managed
                                        mechanically by the params below.
  stop_pts / target_pts   (optional) : per-row overrides (in POINTS) of the mechanical
                                        stop / target. Blank -> use the param defaults.

Timestamps are matched to the master's bars (US/Eastern). A row whose entry lands
outside the loaded date range is skipped (and counted in _meta["skipped"]).

PNL is in POINTS, side*(exit-entry), same convention as every strategy here — the web
layer multiplies by the instrument point value for dollars. Fills are approximated at
the matched bar's OPEN; that's a few points of slippage vs your real fill, so read the
result as "did my entries have edge," not "my exact P&L to the tick."
"""
import os
import numpy as np

STRATEGY_NAME = "REPLAY 1.0 · discretionary trade replay"
DESCRIPTION = ("Replays a CSV of trades you actually took (timestamp + side) through the "
               "engine so the gate and edge-significance test can measure whether your "
               "discretionary entries have real edge. As-taken exits if you log them, "
               "else a mechanical stop/target/EOD.")

# No fixed market — it replays whatever master you point it at.
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "entries_file": {
        "default": "", "type": "str",
        "label": "Entries CSV (name or path)",
        "tooltip": "CSV of your trades. Looked up as-given, then under augur_uploads/replay/ "
                   "and augur_uploads/. Columns: timestamp, side, [exit_time], [stop_pts], "
                   "[target_pts]. See the file header for the exact format.",
    },
    "entry_at": {
        "default": "this_open", "type": "str",
        "options": ["this_open", "this_close", "next_open"],
        "label": "Fill point",
        "tooltip": "Which price to enter at on the matched bar. this_open = the open of the "
                   "bar your timestamp falls in (default). next_open = the following bar's "
                   "open (most conservative, no chance of intrabar look-ahead).",
    },
    "default_stop_pts": {
        "default": 0.0, "min": 0.0, "max": 200.0, "step": 1.0, "type": "float",
        "label": "Mechanical stop (points, 0=off)",
        "tooltip": "Used only when a row has no exit_time and no per-row stop. Distance in "
                   "POINTS from entry. 0 = no hard stop (rely on target / EOD).",
    },
    "default_target_pts": {
        "default": 0.0, "min": 0.0, "max": 400.0, "step": 1.0, "type": "float",
        "label": "Mechanical target (points, 0=off)",
        "tooltip": "Used only when a row has no exit_time and no per-row target. Take-profit "
                   "distance in POINTS from entry. 0 = no target (ride to stop / EOD).",
    },
    "max_hold_bars": {
        "default": 0, "min": 0, "max": 500, "step": 1, "type": "int",
        "label": "Max hold (bars, 0=EOD)",
        "tooltip": "Force-exit a mechanically-managed trade after this many bars. 0 = hold "
                   "until the session close (if Flat by EOD) or the stop/target.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Close any still-open mechanical trade at its session's last bar. Ignored "
                   "for as-taken rows that carry their own exit_time.",
    },
}

# Replay isn't really swept, but a small stop/target grid answers a useful question:
# "what mechanical management would have made my discretionary ENTRIES best?"
PARAM_GRID_PRESETS = {
    "Short  (stop/target sweep)": {
        "default_stop_pts": [0.0, 15.0, 25.0, 40.0],
        "default_target_pts": [0.0, 30.0, 50.0],
        "flat_eod": [True],
    },
}


def _resolve(entries_file):
    """Find the CSV: as-given, then a couple of conventional folders next to the repo."""
    if not entries_file:
        return None
    cands = [entries_file]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
    for sub in ("augur_uploads/replay", "augur_uploads", "."):
        cands.append(os.path.join(here, sub, entries_file))
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


def _parse_side(v):
    s = str(v).strip().lower()
    if s in ("long", "buy", "b", "1", "+1", "l"):
        return 1
    if s in ("short", "sell", "s", "-1", "sh"):
        return -1
    return 0


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    entries_file: str = "", entry_at: str = "this_open",
    default_stop_pts: float = 0.0, default_target_pts: float = 0.0,
    max_hold_bars: int = 0, flat_eod: bool = True,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    import pandas as pd

    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 2 or index is None:
        return None

    path = _resolve(entries_file)
    if path is None:
        return None
    try:
        rows = pd.read_csv(path)
    except Exception:
        return None
    rows.columns = [str(col).strip().lower() for col in rows.columns]

    def col(*names):
        for nm in names:
            if nm in rows.columns:
                return rows[nm]
        return None

    c_ts = col("timestamp", "entry_time", "time", "datetime")
    c_side = col("side", "direction", "dir")
    if c_ts is None or c_side is None:
        return None
    c_exit = col("exit_time", "exit")
    c_stop = col("stop_pts", "stop")
    c_tgt = col("target_pts", "target")

    # Bar timestamps as tz-naive int64 nanoseconds, so a discretionary entry time can be
    # located with a single searchsorted. The master index is US/Eastern; drop tz on both
    # sides and compare naive wall-clock (matches how a trader reads their fill time).
    bar_idx = pd.DatetimeIndex(index)
    if bar_idx.tz is not None:
        bar_idx = bar_idx.tz_localize(None)
    bar_ns = bar_idx.asi8

    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None

    def _find_bar(ts):
        """First bar at/after ts; None if the timestamp is past the data."""
        t = pd.to_datetime(ts, errors="coerce")
        if pd.isna(t):
            return None
        if getattr(t, "tzinfo", None) is not None:
            t = t.tz_localize(None)
        k = int(np.searchsorted(bar_ns, np.datetime64(t).astype("datetime64[ns]").astype("int64"), side="left"))
        return k if 0 <= k < n else None

    pnl_list, trade_log = [], []
    skipped = 0

    for r in range(len(rows)):
        if _stop_event is not None and _stop_event.is_set():
            break
        side = _parse_side(c_side.iloc[r])
        ek = _find_bar(c_ts.iloc[r])
        if side == 0 or ek is None:
            skipped += 1
            continue

        # ── entry price / bar
        if entry_at == "next_open" and ek + 1 < n:
            ek_fill = ek + 1
            entry = o[ek_fill]
        elif entry_at == "this_close":
            ek_fill = ek
            entry = c[ek]
        else:  # this_open
            ek_fill = ek
            entry = o[ek]

        # ── as-taken exit (row carries its own exit_time)
        xt = c_exit.iloc[r] if c_exit is not None else None
        xk = _find_bar(xt) if (xt is not None and str(xt).strip() != "") else None
        if xk is not None and xk >= ek_fill:
            ex_px = o[xk] if entry_at == "next_open" else c[xk]
            pnl = side * (ex_px - entry)
            pnl_list.append(pnl)
            if return_trades:
                trade_log.append((ek_fill, xk, float(pnl), side, float(entry)))
            continue

        # ── mechanical management (no logged exit)
        sp = float(c_stop.iloc[r]) if (c_stop is not None and str(c_stop.iloc[r]).strip() not in ("", "nan")) else float(default_stop_pts)
        tp = float(c_tgt.iloc[r]) if (c_tgt is not None and str(c_tgt.iloc[r]).strip() not in ("", "nan")) else float(default_target_pts)
        stop = (entry - sp) if side > 0 else (entry + sp)
        tgt = (entry + tp) if side > 0 else (entry - tp)

        # session end (for EOD flat) and optional max-hold cap
        sess_end = n - 1
        if did is not None:
            e = ek_fill
            while e + 1 < n and did[e + 1] == did[ek_fill]:
                e += 1
            sess_end = e
        last = sess_end if flat_eod else (n - 1)
        if max_hold_bars > 0:
            last = min(last, ek_fill + int(max_hold_bars))

        exit_k, ex_px = last, c[last]
        for k in range(ek_fill + 1, last + 1):
            if side > 0:
                if sp > 0 and l[k] <= stop:                     # stop first (pessimistic)
                    ex_px = o[k] if o[k] < stop else stop        # gap-through realism
                    exit_k = k; break
                if tp > 0 and h[k] >= tgt:
                    ex_px = tgt; exit_k = k; break
            else:
                if sp > 0 and h[k] >= stop:
                    ex_px = o[k] if o[k] > stop else stop
                    exit_k = k; break
                if tp > 0 and l[k] <= tgt:
                    ex_px = tgt; exit_k = k; break
        pnl = side * (ex_px - entry)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((ek_fill, exit_k, float(pnl), side, float(entry)))

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
        "_meta": {"skipped": int(skipped), "source": os.path.basename(path)},
    }
    if return_trades:
        out["trades"] = trade_log
    return out

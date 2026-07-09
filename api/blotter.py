"""Per-trade blotter export — regenerate a run's champion trade-by-trade and write a CSV.
Used by the runner (auto-save a blotter next to every persisted run) and callable ad-hoc.
No Firestore dependency here; the caller passes the config. Kept dependency-light so a
runner save never fails a run (best-effort — wrap calls in try/except)."""
import os
import augur_engine as ae
from augur_engine.data import find_master, load_master_arrays

FIELDS = ["trade_no", "entry_time", "exit_time", "hold_bars",
          "entry_px", "exit_px", "pnl_pts", "pnl_usd", "cum_usd"]


def champion_blotter(strategy, instrument, timeframe, session="rth", params=None,
                     cost_pts=0.0, mult=20.0, date_from=None, date_to=None):
    """Run the champion once (return_trades) and return a list of per-trade dict rows.
    Empty list if the config produces no trades or the master is missing."""
    m = find_master(instrument, timeframe, session) or find_master(instrument, timeframe)
    if not m:
        return []
    a = load_master_arrays(m)
    idx, close = a["index"], a["close"]
    bt = ae.run_backtest(strategy, instrument=instrument, timeframe=timeframe, session=session,
                         params=params or {}, cost_pts=float(cost_pts or 0),
                         date_from=date_from, date_to=date_to, return_trades=True)
    rows, cum = [], 0.0
    for i, t in enumerate((bt or {}).get("trades") or [], 1):
        eb, xb, pnl = int(t[0]), int(t[1]), float(t[2])
        ep = float(t[4]) if len(t) > 4 else float(close[eb])
        usd = pnl * float(mult)
        cum += usd
        rows.append({"trade_no": i, "entry_time": str(idx[eb])[:16], "exit_time": str(idx[xb])[:16],
                     "hold_bars": xb - eb, "entry_px": round(ep, 2), "exit_px": round(float(close[xb]), 2),
                     "pnl_pts": round(pnl, 2), "pnl_usd": round(usd, 2), "cum_usd": round(cum, 0)})
    return rows


def write_csv(rows, path):
    """Write blotter rows to a CSV at `path` (creates parent dirs). Returns path or None."""
    if not rows:
        return None
    import csv
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path

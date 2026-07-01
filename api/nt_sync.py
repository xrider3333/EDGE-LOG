"""NinjaTrader → EDGELOG trade sync (runs on THIS PC inside the runner).

The NinjaScript AddOn (tools/EdgeLogExport.cs) appends every account fill to a CSV
(default C:\\EdgeLog\\fills.csv). This module reads that file, pairs the fills into
round-trip trades with FIFO position tracking, computes P&L *identically* to the
EDGELOG web app, and writes each completed trade to users/{uid}/trades — so the
journal fills in automatically, even with the browser closed and on the iPad.

Idempotent by construction: a round-trip's Firestore doc id is derived from the
ExecutionId of the fill that closed it, so re-reading the whole CSV every poll never
creates duplicates. A small local state file remembers which trades were already
written so we only touch Firestore for genuinely new/changed trades.

The P&L math, symbol handling and trade-doc schema mirror index.html exactly:
  calcPnl: gross = isFut ? ((exit-entry)*dir / ts) * tv * size : (exit-entry)*dir*size
  PRESETS: per-symbol {tv: tick value, ts: tick size}
  getBase: strip non-letters, first 3, upper.
"""
import os
import csv
import json
import time
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta

# The AddOn's fills.csv timestamp follows NinjaTrader's *display* time-zone setting, which
# the user can change (observed: some fills logged UTC, later ones logged Pacific) — so it is
# NOT reliable. The local NinjaTrader.sqlite `Executions.Time` (.NET ticks) is stored in
# absolute UTC regardless of that setting, so we prefer it (matched by ExecutionId) and only
# fall back to the CSV time when a fill isn't in the DB yet. Times are then converted to New
# York session time for the journal (handles EST/EDT).
try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # zoneinfo missing (pre-3.9) — leave times as-is
    _NY = None

# Local NinjaTrader execution DB (override with EDGELOG_NT_DB). Standard install location.
NT_DB = os.environ.get(
    "EDGELOG_NT_DB",
    os.path.expanduser(r"~\Documents\NinjaTrader 8\db\NinjaTrader.sqlite"))


def _to_ny(dt):
    """Treat a naive UTC datetime as UTC and convert to America/New_York."""
    if dt is None or _NY is None:
        return dt
    return dt.replace(tzinfo=timezone.utc).astimezone(_NY)


def _exec_utc_by_id(db_path=NT_DB):
    """Map ExecutionId -> naive UTC datetime from NinjaTrader.sqlite (absolute-UTC ticks).
    Opened read-only so it works even while NinjaTrader has the DB open. Best-effort: any
    problem (missing/locked DB) returns {} and callers fall back to the CSV timestamp."""
    out = {}
    if not db_path or not os.path.exists(db_path):
        return out
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, timeout=2)
        try:
            for eid, ticks in con.execute("SELECT ExecutionId, Time FROM Executions"):
                if eid is None or ticks is None:
                    continue
                try:
                    out[str(eid)] = datetime(1, 1, 1) + timedelta(microseconds=int(ticks) // 10)
                except Exception:
                    continue
        finally:
            con.close()
    except Exception:
        return {}
    return out


def enrich_utc_from_db(fills, db_path=NT_DB):
    """Override each fill's dt with the DB's absolute-UTC time (matched by ExecutionId).
    Leaves fills not present in the DB (e.g. web/mobile trades) untouched."""
    times = _exec_utc_by_id(db_path)
    if not times:
        return fills
    for f in fills:
        u = times.get(str(f.get("exec_id") or ""))
        if u is not None:
            f["dt"] = u
    return fills


# tick value (tv) / tick size (ts) per instrument — copied verbatim from index.html
PRESETS = {
    "ES": (12.50, 0.25), "MES": (1.25, 0.25), "NQ": (5.00, 0.25), "MNQ": (0.50, 0.25),
    "CL": (10.00, 0.01), "GC": (10.00, 0.10), "SI": (25.00, 0.005), "ZB": (31.25, 0.03125),
    "RTY": (5.00, 0.10), "YM": (5.00, 1.00), "MGC": (1.00, 0.10), "MCL": (1.00, 0.01),
    "ZN": (31.25, 0.015625), "ZC": (12.50, 0.25), "NG": (10.00, 0.001),
}

DEFAULT_FILLS = r"C:\EdgeLog\fills.csv"


def _state_path(fills_path):
    d = os.path.dirname(fills_path) or "."
    return os.path.join(d, ".edgelog_sync_state.json")


def get_base(sym):
    """'ES 03-26' -> 'ES'. Strip non-letters, take first 3, uppercase."""
    letters = "".join(c for c in (sym or "") if c.isalpha())
    return letters[:3].upper()


def is_fut(sym):
    return sym in PRESETS


def calc_pnl(sym, side, entry, exit_, size, fees):
    """Return (gross, net). side is 'LONG' or 'SHORT'. Mirrors index.html calcPnl."""
    d = 1 if side == "LONG" else -1
    if is_fut(sym):
        tv, ts = PRESETS[sym]
        gross = (((exit_ - entry) * d) / ts) * tv * size
    else:
        gross = (exit_ - entry) * d * size
    gross = round(gross, 2)
    return gross, round(gross - (fees or 0.0), 2)


def _parse_dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # last resort: ISO-ish prefix
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None


def parse_fills(path):
    """Read the AddOn's fills.csv into a list of fill dicts, in file order."""
    fills = []
    if not os.path.exists(path):
        return fills
    with open(path, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        # normalise header keys (lower, strip)
        for i, raw in enumerate(rdr):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            dt = _parse_dt(row.get("time"))
            try:
                price = float(row.get("price") or 0)
                qty = int(float(row.get("qty") or 0))
            except ValueError:
                continue
            if qty <= 0 or price <= 0 or dt is None:
                continue
            try:
                comm = float(row.get("commission") or 0)
            except ValueError:
                comm = 0.0
            fills.append({
                "exec_id": row.get("executionid") or f"row{i}",
                "dt": dt,
                "account": row.get("account") or "",
                "instrument": row.get("instrument") or "",
                "action": (row.get("action") or "").upper(),
                "qty": qty,
                "price": price,
                "commission": comm,
                "order_id": row.get("orderid") or "",
                "_i": i,
            })
    return fills


def build_trades(fills):
    """FIFO position tracking → round-trip trades, per (account, instrument).
    Mirrors the scale-in / scale-out pairing in index.html's importPDF.
    A trade opens when the position leaves flat and closes when it returns to flat.
    Returns trade dicts shaped for the EDGELOG journal."""
    groups = {}
    for f in fills:
        groups.setdefault((f["account"], f["instrument"]), []).append(f)

    trades = []
    for (account, instrument), grp in groups.items():
        grp.sort(key=lambda f: (f["dt"], f["_i"]))
        sym = get_base(instrument)
        pos = 0
        entry_qty = entry_notional = 0.0
        exit_qty = exit_notional = 0.0
        entry_dt = exit_dt = None
        entry_side = None
        entry_oid = ""
        comm_acc = 0.0           # commissions accumulated for the open round-trip
        close_exec_id = ""

        for f in grp:
            delta = f["qty"] if f["action"] == "BUY" else -f["qty"]
            new_pos = pos + delta
            comm_acc += f["commission"]
            adding = pos == 0 or (delta > 0) == (pos > 0)
            if adding:
                if pos == 0:
                    entry_side = "LONG" if f["action"] == "BUY" else "SHORT"
                    entry_oid = f["order_id"]
                    entry_dt = f["dt"]
                    entry_qty = abs(delta)
                    entry_notional = f["price"] * abs(delta)
                    exit_qty = exit_notional = 0.0
                    exit_dt = None
                    comm_acc = f["commission"]
                else:
                    entry_qty += abs(delta)
                    entry_notional += f["price"] * abs(delta)
            else:  # reducing
                closing = min(abs(delta), abs(pos))
                exit_qty += closing
                exit_notional += f["price"] * closing
                exit_dt = f["dt"]
                close_exec_id = f["exec_id"]

            if pos != 0 and new_pos == 0:
                avg_entry = entry_notional / entry_qty if entry_qty else 0.0
                avg_exit = exit_notional / exit_qty if exit_qty else 0.0
                fees = round(comm_acc, 2)
                gross, net = calc_pnl(sym, entry_side, avg_entry, avg_exit, entry_qty, fees)
                dur = None
                dur_sec = None
                if entry_dt and exit_dt:
                    dur_sec = max(0, int((exit_dt - entry_dt).total_seconds()))
                    dur = max(0, dur_sec // 60)
                e_ny = _to_ny(entry_dt)
                x_ny = _to_ny(exit_dt)
                trades.append({
                    "doc_id": "nt_" + _safe_id(close_exec_id or f"{account}{instrument}{entry_dt}{avg_exit}"),
                    "date": e_ny.strftime("%Y-%m-%d"),
                    "symbol": sym,
                    "type": entry_side,
                    "entry": round(avg_entry, 4),
                    "exit": round(avg_exit, 4),
                    "size": int(entry_qty),
                    "fees": fees,
                    "grossPnl": gross,
                    "pnl": net,
                    "setup": "—", "grade": "—", "timeframe": "—",
                    "notes": "", "chartUrl": "",
                    "durationMins": dur,
                    "durationSecs": dur_sec,
                    "entryTime": e_ny.strftime("%H:%M"),
                    "exitTime": x_ny.strftime("%H:%M") if x_ny else None,
                    "orderId": entry_oid or "",
                    "source": "NinjaTrader",
                    "assetType": "futures" if is_fut(sym) else "stock",
                    "account": account,
                    "broker": "NinjaTrader",
                    "ntExecId": close_exec_id,
                })
                pos = 0
                entry_qty = entry_notional = exit_qty = exit_notional = 0.0
                entry_dt = exit_dt = None
                entry_side = None
                entry_oid = ""
                comm_acc = 0.0
                continue
            pos = new_pos
    return trades


def _safe_id(s):
    """Firestore doc ids can't contain / and a few specials; keep it short + stable."""
    s = str(s)
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in s)
    return cleaned[:200] or hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _trade_hash(t):
    """Content hash so we only re-write a trade doc when something actually changed."""
    key = json.dumps({k: t.get(k) for k in
                      ("date", "symbol", "type", "entry", "exit", "size", "fees", "pnl")},
                     sort_keys=True, default=str)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def sync_trades(db, uid, fills_path=DEFAULT_FILLS, log=print):
    """Read fills, build round-trips, upsert new/changed ones to users/{uid}/trades.
    Writes a status doc to users/{uid}/meta/nt_sync. Returns a summary dict."""
    from firebase_admin import firestore

    fills = parse_fills(fills_path)
    enrich_utc_from_db(fills)   # prefer NinjaTrader.sqlite's absolute-UTC execution times
    trades = build_trades(fills)

    # local cursor: doc_id -> content hash already written, so steady-state writes 0 docs.
    sp = _state_path(fills_path)
    try:
        state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    except Exception:
        state = {}
    written = state.get("written", {}) if isinstance(state, dict) else {}

    col = db.collection("users").document(uid).collection("trades")
    added = updated = 0
    batch = db.batch()
    pending = 0
    for t in trades:
        h = _trade_hash(t)
        prev = written.get(t["doc_id"])
        if prev == h:
            continue  # unchanged — skip the write
        doc = {k: v for k, v in t.items() if k != "doc_id"}
        doc["createdAt"] = firestore.SERVER_TIMESTAMP
        doc["ntSync"] = True
        batch.set(col.document(t["doc_id"]), doc, merge=True)
        written[t["doc_id"]] = h
        if prev is None:
            added += 1
        else:
            updated += 1
        pending += 1
        if pending >= 400:               # Firestore batch cap is 500
            batch.commit(); batch = db.batch(); pending = 0
    if pending:
        batch.commit()

    # how many round-trips are still open (position not back to flat) — informational
    open_positions = _count_open(fills)

    state = {"written": written, "last_sync": time.time(),
             "total_trades": len(trades), "fills": len(fills)}
    try:
        json.dump(state, open(sp, "w", encoding="utf-8"))
    except Exception:
        pass

    # status doc the web subscribes to (meta/nt_sync) so the UI can show last-sync info
    try:
        db.collection("users").document(uid).collection("meta").document("nt_sync").set({
            "last_sync": time.time(),
            "total_trades": len(trades),
            "fills": len(fills),
            "open_positions": open_positions,
            "last_added": added,
            "last_updated": updated,
            "fills_path": fills_path,
            "file_present": os.path.exists(fills_path),
        })
    except Exception as e:
        log(f"  [nt-sync] status write failed: {e}")

    if added or updated:
        log(f"  [nt-sync] {added} new, {updated} updated -> users/{uid}/trades "
            f"({len(trades)} round-trips, {open_positions} open)")
    return {"added": added, "updated": updated, "total": len(trades),
            "open_positions": open_positions, "fills": len(fills),
            "file_present": os.path.exists(fills_path)}


def _count_open(fills):
    groups = {}
    for f in fills:
        groups.setdefault((f["account"], f["instrument"]), []).append(f)
    open_n = 0
    for grp in groups.values():
        grp.sort(key=lambda f: (f["dt"], f["_i"]))
        pos = 0
        for f in grp:
            pos += f["qty"] if f["action"] == "BUY" else -f["qty"]
        if pos != 0:
            open_n += 1
    return open_n

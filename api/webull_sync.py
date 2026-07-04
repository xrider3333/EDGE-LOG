"""Webull → EDGELOG trade sync (runs on THIS PC inside the runner).

Pulls FILLED stock/ETF orders from the OFFICIAL Webull OpenAPI (app key/secret the
owner generated on webull.com — never the login password), FIFO-pairs the fills into
round-trip trades exactly like nt_sync does for NinjaTrader, and upserts them to
users/{uid}/trades so Webull trades appear in the journal next to the NT ones
(broker:'Webull' → the ACCOUNT pill shows up automatically in the web app).

QUOTA RULE (owner, 2026-07-04): the pull runs ONCE PER CALENDAR DAY (New York date)
— the owner is on the free Firestore plan. The runner may call sync_trades() every
loop; this module gates itself via the local state file and returns instantly on
all but the first call of the day. Firestore writes use the same content-hash skip
as nt_sync, so steady-state days write ~0 docs.

SECRETS: credentials live OUTSIDE the repo in C:\\EdgeLog\\webull_keys.json (this
repo auto-pushes to GitHub — nothing secret may live in it). The SDK's 2FA token is
kept in C:\\EdgeLog\\webull_token\\. Neither path is ever written to Firestore.

Stock math (NOT the futures tick math): gross = (exit-entry)*dir*shares.
Webull US stock commission is $0; regulatory sell-side fees (SEC/TAF) are pennies
and are not reported per-order, so fees default to 0 — the journal's fee column
stays honest at the order level.
"""
import os
import json
import time
import hashlib
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:
    _NY = None

DEFAULT_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")
_PLACEHOLDERS = ("", "PASTE_APP_KEY_HERE", "PASTE_APP_SECRET_HERE")


def _state_path(keys_path):
    return os.path.join(os.path.dirname(keys_path) or ".", ".webull_sync_state.json")


def _ny_today():
    """Today's date string in New York (the journal's session timezone)."""
    now = datetime.now(_NY) if _NY else datetime.utcnow()
    return now.strftime("%Y-%m-%d")


def load_keys(keys_path=DEFAULT_KEYS):
    """Return {app_key, app_secret, region, backfill_days} or None if not configured."""
    if not os.path.exists(keys_path):
        return None
    try:
        cfg = json.load(open(keys_path, encoding="utf-8"))
    except Exception:
        return None
    ak = (cfg.get("app_key") or "").strip()
    sk = (cfg.get("app_secret") or "").strip()
    if ak in _PLACEHOLDERS or sk in _PLACEHOLDERS:
        return None   # template not filled in yet — silently disabled
    return {"app_key": ak, "app_secret": sk,
            "region": (cfg.get("region") or "us").strip().lower(),
            "backfill_days": int(cfg.get("backfill_days") or 90)}


# ── Webull API pull ────────────────────────────────────────────────

def _client(keys):
    """Build TradeClient from the official SDK. Import inside so the runner still
    starts when the SDK isn't installed (sync just logs a hint and skips)."""
    from webull.core.client import ApiClient
    from webull.trade.trade_client import TradeClient
    api = ApiClient(keys["app_key"], keys["app_secret"], keys["region"])
    # Persist the SDK's 2FA/access token OUTSIDE the repo so unattended daily runs
    # keep working after the one-time verification.
    try:
        os.makedirs(TOKEN_DIR, exist_ok=True)
        api.set_token_dir(TOKEN_DIR)
    except Exception:
        pass
    return TradeClient(api)


def _field(o, *names, default=None):
    """First non-empty value among candidate key names (Webull payloads vary by
    region/version — same defensive style as the web app's importCSV gc2())."""
    for n in names:
        v = o.get(n)
        if v not in (None, ""):
            return v
    return default


def _parse_when(v):
    """Webull time → naive NY-local datetime. Accepts epoch s/ms, ISO, or US format."""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            ts = float(v)
            if ts > 1e12:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.astimezone(_NY).replace(tzinfo=None) if _NY else dt.replace(tzinfo=None)
    except Exception:
        pass
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.astimezone(_NY).replace(tzinfo=None) if _NY else dt.replace(tzinfo=None)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _extract_orders(payload):
    """Order-history page payload → flat list of order dicts. Handles the shapes
    seen across Webull docs: a bare list, {'orders':[...]}, {'data':[...]},
    {'items':[...]} — and unwraps combo groups that nest 'orders'/'items'/'legs'."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        for k in ("orders", "data", "items", "order_list", "orderList"):
            if isinstance(payload.get(k), list):
                payload = payload[k]
                break
        else:
            payload = [payload]
    flat = []
    for o in payload:
        if not isinstance(o, dict):
            continue
        nested = None
        for k in ("orders", "items", "legs"):
            if isinstance(o.get(k), list) and o[k] and isinstance(o[k][0], dict):
                nested = o[k]
                break
        # unwrap only when children look like real orders (have their own qty/price)
        if nested and any(_field(c, "filled_quantity", "filled_qty", "filledQuantity") for c in nested):
            flat.extend(nested)
        else:
            flat.append(o)
    return flat


def _order_to_fill(o):
    """One FILLED Webull order → a fill dict for FIFO pairing. None if not a fill."""
    status = str(_field(o, "order_status", "status", "orderStatus", default="")).upper()
    if status and ("FILL" not in status):     # FILLED / PARTIAL_FILLED pass; WORKING etc. drop
        return None
    qty = _field(o, "filled_quantity", "filled_qty", "filledQuantity", "filled")
    px = _field(o, "avg_filled_price", "avg_fill_price", "avgFilledPrice", "filled_price",
                "filledPrice", "avg_price", "avgPrice")
    side = str(_field(o, "side", "action", "order_side", default="")).upper()
    sym = str(_field(o, "symbol", "ticker", "disSymbol", default="")).upper().strip()
    when = _parse_when(_field(o, "filled_time", "filledTime", "filled_at", "update_time",
                              "updateTime", "place_time", "placeTime", "create_time"))
    itype = str(_field(o, "instrument_type", "instrumentType", "security_type", default="EQUITY")).upper()
    try:
        qty = float(qty); px = float(px)
    except (TypeError, ValueError):
        return None
    if qty <= 0 or px <= 0 or not sym or side not in ("BUY", "SELL") or when is None:
        return None
    if itype not in ("EQUITY", "ETF", "STOCK", ""):
        return None                            # options/crypto out of scope (stocks/ETFs only)
    return {
        "exec_id": str(_field(o, "order_id", "orderId", "client_order_id", "clientOrderId",
                              default="")) or None,
        "dt": when, "symbol": sym, "action": side,
        "qty": qty, "price": px,
        "account": str(_field(o, "account_id", "accountId", default="")),
    }


def fetch_fills(keys, start_date, end_date, log=print, page_size=100, max_pages=200):
    """Pull FILLED fills from every Webull account on the key. Paginates via
    last_client_order_id; polite 1.1s sleep between calls (documented rate limits
    are ~2 req / 2 s on trade endpoints)."""
    tc = _client(keys)
    res = tc.account_v2.get_account_list()
    if res.status_code != 200:
        raise RuntimeError(f"get_account_list HTTP {res.status_code}: {res.text[:200]}")
    accts = _extract_orders(res.json())        # same tolerant unwrap works for accounts
    fills, first_sample_logged = [], False
    for a in accts:
        acct_id = _field(a, "account_id", "accountId", "id")
        if not acct_id:
            continue
        acct_num = str(_field(a, "account_number", "accountNumber", default=""))
        label = "Webull-" + acct_num[-4:] if len(acct_num) >= 4 else "Webull"
        last_coid = last_oid = None
        for _page in range(max_pages):
            time.sleep(1.1)
            res = tc.order_v2.get_order_history(
                acct_id, page_size=page_size,
                start_date=start_date, end_date=end_date,
                last_client_order_id=last_coid, last_order_id=last_oid)
            if res.status_code != 200:
                log(f"  [webull] order_history HTTP {res.status_code}: {res.text[:200]}")
                break
            orders = _extract_orders(res.json())
            if not orders:
                break
            if not first_sample_logged:
                # one-time desensitized shape log → lets us lock field names fast
                keys_seen = sorted(orders[0].keys())
                log(f"  [webull] payload fields: {keys_seen}")
                first_sample_logged = True
            page_new = 0
            for o in orders:
                f = _order_to_fill(o)
                if f:
                    f["account"] = label
                    if not any(x["exec_id"] == f["exec_id"] and x["dt"] == f["dt"] for x in fills):
                        fills.append(f); page_new += 1
                last_coid = str(_field(o, "client_order_id", "clientOrderId", default=last_coid or ""))
                last_oid = str(_field(o, "order_id", "orderId", default=last_oid or ""))
            if len(orders) < page_size and page_new == 0:
                break
            if len(orders) < page_size:
                break
    return fills


# ── FIFO pairing (stock math) ──────────────────────────────────────

def build_trades(fills):
    """FIFO position tracking → round-trip trades per (account, symbol).
    Same open→flat pairing as nt_sync.build_trades, but with STOCK P&L:
    gross = (exit-entry)*dir*shares, full symbol kept (no futures getBase)."""
    groups = {}
    for i, f in enumerate(fills):
        f["_i"] = i
        groups.setdefault((f["account"], f["symbol"]), []).append(f)

    trades = []
    for (account, symbol), grp in groups.items():
        grp.sort(key=lambda f: (f["dt"], f["_i"]))
        pos = 0.0
        entry_qty = entry_notional = exit_qty = exit_notional = 0.0
        entry_dt = exit_dt = None
        entry_side = None
        entry_oid = close_exec_id = ""

        for f in grp:
            delta = f["qty"] if f["action"] == "BUY" else -f["qty"]
            new_pos = pos + delta
            adding = pos == 0 or (delta > 0) == (pos > 0)
            if adding:
                if pos == 0:
                    entry_side = "LONG" if f["action"] == "BUY" else "SHORT"
                    entry_oid = f["exec_id"] or ""
                    entry_dt = f["dt"]
                    entry_qty = abs(delta)
                    entry_notional = f["price"] * abs(delta)
                    exit_qty = exit_notional = 0.0
                    exit_dt = None
                else:
                    entry_qty += abs(delta)
                    entry_notional += f["price"] * abs(delta)
            else:
                closing = min(abs(delta), abs(pos))
                exit_qty += closing
                exit_notional += f["price"] * closing
                exit_dt = f["dt"]
                close_exec_id = f["exec_id"] or ""

            if pos != 0 and new_pos == 0:
                avg_entry = entry_notional / entry_qty if entry_qty else 0.0
                avg_exit = exit_notional / exit_qty if exit_qty else 0.0
                d = 1 if entry_side == "LONG" else -1
                gross = round((avg_exit - avg_entry) * d * entry_qty, 2)
                fees = 0.0                      # Webull US stock commission is $0
                dur_sec = max(0, int((exit_dt - entry_dt).total_seconds())) if entry_dt and exit_dt else None
                trades.append({
                    "doc_id": "wb_" + _safe_id(close_exec_id or f"{account}{symbol}{entry_dt}{avg_exit}"),
                    "date": entry_dt.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "type": entry_side,
                    "entry": round(avg_entry, 4),
                    "exit": round(avg_exit, 4),
                    "size": int(entry_qty) if entry_qty == int(entry_qty) else entry_qty,
                    "fees": fees,
                    "grossPnl": gross,
                    "pnl": round(gross - fees, 2),
                    "setup": "—", "grade": "—", "timeframe": "—",
                    "notes": "", "chartUrl": "",
                    "durationMins": (dur_sec // 60) if dur_sec is not None else None,
                    "durationSecs": dur_sec,
                    "entryTime": entry_dt.strftime("%H:%M"),
                    "exitTime": exit_dt.strftime("%H:%M") if exit_dt else None,
                    "orderId": entry_oid,
                    "source": "Webull API",
                    "assetType": "stock",
                    "account": account,
                    "broker": "Webull",
                    "wbOrderId": close_exec_id,
                })
                pos = 0.0
                entry_qty = entry_notional = exit_qty = exit_notional = 0.0
                entry_dt = exit_dt = None
                entry_side = None
                entry_oid = close_exec_id = ""
                continue
            pos = new_pos
    return trades


def _safe_id(s):
    s = str(s)
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in s)
    return cleaned[:200] or hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _trade_hash(t):
    key = json.dumps({k: t.get(k) for k in
                      ("date", "symbol", "type", "entry", "exit", "size", "fees", "pnl")},
                     sort_keys=True, default=str)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


# ── daily-gated sync entrypoint (called from the runner loop) ──────

def sync_trades(db, uid, keys_path=DEFAULT_KEYS, log=print, force=False):
    """Once-per-NY-day Webull pull → upsert round-trips to users/{uid}/trades.
    Safe to call every runner loop: returns {'skipped': reason} instantly when
    already ran today, keys missing, or SDK not installed."""
    keys = load_keys(keys_path)
    if not keys:
        return {"skipped": "no-keys"}          # template unfilled / file missing

    sp = _state_path(keys_path)
    try:
        state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    except Exception:
        state = {}
    today = _ny_today()
    if not force and state.get("last_run_day") == today:
        return {"skipped": "already-ran-today"}

    try:
        import webull  # noqa: F401 — presence check only
    except ImportError:
        log("  [webull] SDK missing — pip install --upgrade webull-openapi-python-sdk")
        return {"skipped": "sdk-missing"}

    from firebase_admin import firestore

    # window: first run backfills backfill_days; later runs re-pull 7 days of
    # overlap (idempotent doc ids make the overlap free — same trick as nt_sync).
    if state.get("last_run_day"):
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start = (datetime.now() - timedelta(days=keys["backfill_days"])).strftime("%Y-%m-%d")

    try:
        fills = fetch_fills(keys, start, today, log=log)
    except Exception as e:
        log(f"  [webull] pull failed: {type(e).__name__}: {e}")
        # do NOT stamp last_run_day — retry on the next loop pass
        return {"error": f"{type(e).__name__}: {e}"}

    trades = build_trades(fills)
    written = state.get("written", {}) if isinstance(state, dict) else {}
    col = db.collection("users").document(uid).collection("trades")
    added = updated = pending = 0
    batch = db.batch()
    for t in trades:
        h = _trade_hash(t)
        prev = written.get(t["doc_id"])
        if prev == h:
            continue
        doc = {k: v for k, v in t.items() if k != "doc_id"}
        doc["createdAt"] = firestore.SERVER_TIMESTAMP
        doc["wbSync"] = True
        batch.set(col.document(t["doc_id"]), doc, merge=True)
        written[t["doc_id"]] = h
        added += 1 if prev is None else 0
        updated += 0 if prev is None else 1
        pending += 1
        if pending >= 400:
            batch.commit(); batch = db.batch(); pending = 0
    if pending:
        batch.commit()

    state = {"written": written, "last_run_day": today, "last_sync": time.time(),
             "total_trades": len(trades), "fills": len(fills)}
    try:
        json.dump(state, open(sp, "w", encoding="utf-8"))
    except Exception:
        pass

    # status doc for the web UI (mirrors meta/nt_sync) — one write per day, cheap
    try:
        db.collection("users").document(uid).collection("meta").document("webull_sync").set({
            "last_sync": time.time(), "total_trades": len(trades), "fills": len(fills),
            "last_added": added, "last_updated": updated, "window_start": start,
        })
    except Exception as e:
        log(f"  [webull] status write failed: {e}")

    log(f"  [webull] {added} new, {updated} updated -> users/{uid}/trades "
        f"({len(trades)} round-trips from {len(fills)} fills since {start})")
    return {"added": added, "updated": updated, "total": len(trades), "fills": len(fills)}

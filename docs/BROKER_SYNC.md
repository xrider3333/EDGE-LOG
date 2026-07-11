# EDGELOG — Automatic Broker Sync (canonical reference)

**This is the single source of truth for auto-importing broker trades into EDGELOG.**
It documents the broker-agnostic architecture, the NinjaTrader reference implementation,
every hard-won gotcha, and a step-by-step for adding a new broker (e.g. Webull). Any new
broker integration MUST satisfy the "Universal contract" in §4.

> If you're adding a broker: read §1–§4, copy the `nt_sync.py` pattern, then follow §7.

---

## 1. Why a local runner exists (the core constraint)

The EDGELOG web app (`index.html`, GitHub Pages) runs **in the browser**, which is
sandboxed — it **cannot read local files** on the user's PC or talk to a desktop trading
app. It can only read/write **Firestore**. So every broker integration is a bridge:

```
  broker (local capture) ──► local file/DB ──► RUNNER (api/runner.py --watch) ──► Firestore ──► web app
```

- **Capture** (per broker): gets fills onto the local machine — either a desktop-app plugin
  that writes a CSV, a broker API poller, or a watch-folder for exports.
- **Runner** (`api/runner.py`, one process, always-on): reads the local capture, calls the
  broker's **sync module**, writes trades to Firestore. Auto-starts at logon (§6).
- **Web app**: subscribes to Firestore and renders the journal.

Opening the website can **not** start anything on the PC — that's why a local agent is
mandatory. There is no cloud-only path unless the broker exposes a hosted API we can poll
from a server (none of ours do today).

---

## 2. Data model (what every broker writes)

Firestore layout (per user, `uid` = Firebase Auth uid):

| Path | Contents |
|---|---|
| `users/{uid}/trades/{docId}` | one round-trip trade (the journal) |
| `users/{uid}/meta/{broker}_sync` | heartbeat/status doc the UI reads (`nt_sync`, etc.) |
| `users/{uid}/commands/{id}` | on-demand commands the runner consumes (e.g. `sync_trades`) |
| `users/{uid}/backtests`, `.../runs` | AUGUR cloud-backtest queue + history (unrelated to trades) |

**Trade document schema** (produced by `nt_sync.build_trades`; match this for any broker):

```
docId       stable, derived from the closing execution id  →  "<broker>_<exitExecId>"
date        "YYYY-MM-DD"  (in America/New_York, see §5.2)
symbol      base symbol, e.g. "MES", "AAPL"   (get_base: strip non-letters, first 3, upper)
type        "LONG" | "SHORT"
entry,exit  avg fill prices (float)
size        contracts/shares (int)
fees        all-in fees, positive number (see §5.3)
grossPnl    P&L before fees
pnl         net P&L = grossPnl - fees
entryTime,exitTime  "HH:MM" (America/New_York)
durationMins, durationSecs
setup,grade,timeframe   discretionary ("—" default; the user fills these)
notes,chartUrl,tags     discretionary
orderId, account
source      "NinjaTrader" | "Webull" | ...   (drives the account toggle in the UI)
broker      same-ish label
assetType   "futures" | "stock"
createdAt   firestore.SERVER_TIMESTAMP
ntSync/…    true   (marks it as auto-synced)
```

**P&L math must mirror `index.html` exactly** (`nt_sync.calc_pnl`):
- futures: `gross = ((exit - entry) * dir / tickSize) * tickValue * size`
- stocks:  `gross = (exit - entry) * dir * size`
- `dir = +1 LONG / -1 SHORT`. `PRESETS[sym] = (tickValue, tickSize)`.

---

## 3. Reference implementation — NinjaTrader (copy this shape)

Three pieces:

### 3a. Capture — `tools/EdgeLogExport.cs` (NinjaScript AddOn)
- Subscribes to `Account.ExecutionUpdate` for **all** accounts → captures manual AND
  strategy fills.
- Appends each fill to `C:\EdgeLog\fills.csv`, header:
  `ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId`.
- Logs `ex.Time.ToUniversalTime()` (UTC). **Requires NT8 *desktop* open** (the AddOn lives
  inside it) — this is the reason web/mobile trades are missed (§5.1).
- Install: drop in `Documents/NinjaTrader 8/bin/Custom/AddOns/`, F5 compile, restart NT8.

### 3b. Sync module — `api/nt_sync.py` (the reusable brain)
- `parse_fills(path)` → list of fills.
- `enrich_utc_from_db(fills)` → override each fill's time with the **absolute-UTC** value
  from `NinjaTrader.sqlite` `Executions.Time` (see §5.2).
- `build_trades(fills)` → FIFO position tracking per `(account, instrument)`: a trade opens
  when position leaves flat and closes when it returns to flat; handles scale-in/out.
  Computes fees (§5.3), gross/net, duration, NY times.
- `sync_trades(db, uid, fills_path)` → idempotent upsert: content-hash per trade skips
  unchanged writes; local state file `C:\EdgeLog\.edgelog_sync_state.json` remembers what
  was written; writes the `meta/nt_sync` heartbeat **throttled** (on-change or ~5 min).

### 3c. Runner wiring — `api/runner.py`
- `--watch` loop: polls the backtest/command queue every `--interval`, runs `sync_trades`
  every `--trades-sec`, updates the heartbeat.
- Auth gate: only serves `uid`s in `--allow-uid`.
- Launched by `run_edgelog_hidden.vbs` (§6):
  `python -m api.runner --firestore --cred serviceAccount.json --allow-uid <uid> --watch --refresh-min 0 --interval 30 --trades-sec 20`

---

## 4. Universal contract (a new broker MUST provide)

1. **A capture** that lands fills on the local machine (API poll → file, desktop plugin →
   file, or a watch-folder of broker exports). One fill = `{execId, utcTime, account,
   symbol, side(BUY/SELL), qty, price, [commission], orderId}`.
2. **A sync module** shaped like `nt_sync.py`, exposing `sync_trades(db, uid, ...)`, that:
   - pairs fills into round-trip trades (reuse `build_trades` logic),
   - computes P&L identically to `index.html` (`calc_pnl`),
   - assigns times in **America/New_York** from an **absolute-UTC** source,
   - resolves **fees** deterministically (schedule) where possible (§5.3),
   - upserts idempotently (`docId = "<broker>_<exitExecId>"`, content-hash, local state),
   - sets `source`/`broker`/`assetType`, and writes a `meta/<broker>_sync` heartbeat.
3. **Runner registration**: add the module to the watch loop (mirror `--nt-fills` /
   `--trades-sec`), guarded by `try/except` so one broker's error can't kill the loop.
4. **Idempotent + free-tier friendly** (§5.4). **Never** automate broker login (§8).

---

## 5. Hard-won gotchas (do not relearn these)

### 5.1 Web/mobile fills bypass the local capture
Trades placed on the broker's **web or mobile** app never touch the PC (the desktop app is
offline), so the local capture misses them entirely — they're absent from the journal, the
local DB, and any real-time feed at once. Only the broker's **web export** (e.g. NinjaTrader
"Position History") has them. Design for this: a periodic export ingest can backfill, but
recognize it's a separate, manual-ish path. (Verified: the 06-22 trade was a web fill.)

### 5.2 Capture timestamps are in the platform's *display* timezone — unreliable
The desktop app's fill time follows the user's **display-TZ setting**, which they can change
(observed: 06-26 logged UTC, 06-30 logged Pacific — same account, days apart). **Never trust
it.** Use an **absolute-UTC** source instead: NinjaTrader's local `sqlite Executions.Time`
(.NET ticks) is UTC regardless of the display setting. Match by execution id, then convert
UTC → `America/New_York` (DST-correct via `zoneinfo`). For a broker API, prefer an explicit
UTC/epoch field over any "local" string.

### 5.3 Fees are a fixed schedule, NOT "post-close data"
The desktop reports `$0` commission at fill time (fees settle overnight), which makes naive
sync show inflated net P&L. But the fee is **deterministic**: validated from Cash History,
**CME micros = $0.95/side** ($1.90 round-trip/contract), zero variance across 74 fills.
`nt_sync.FEE_PER_SIDE` applies `fee = perSide * contracts * 2` at sync time → correct fees
with **no broker export and no login**. Do the same per broker: derive the schedule once
from a statement, hard-code it, and only re-verify if the broker changes rates.
- **Webull (stocks):** commission is typically $0; real costs are tiny regulatory fees
  (SEC/TAF on sells, per-share rounding). Derive the exact schedule from one Webull
  statement and encode it the same way. Don't assume $0 net.

### 5.4 Firestore free-tier (Spark) quota — the runner must be lean
Limits: **50k reads/day, 20k writes/day**, reset ~midnight Pacific.
- **Trade sync is cheap**: it reads a *local* file and only *writes* on a genuinely new/
  changed trade. Its frequency barely matters for quota.
- **The read hog is the queue poll** (`run_once`/`run_commands`). At the old 3-second default
  it was ~28k reads/day — over the limit. Use `--interval 30`.
- **Throttle the heartbeat write** to on-change / ~5 min (it was writing every 20s ≈ 4k/day
  for nothing).
- **Survive 429s**: wrap startup `sync_runs` and the queue poll in `try/except` so a transient
  quota error logs and is skipped instead of crashing the runner (it resumes when quota
  resets). Do NOT put the fix behind the Blaze billing plan — the owner is staying on Spark.

### 5.5 Windows / process gotchas
- Store-installed Python runs as **`python3.13.exe`**, not `python.exe` — filter processes by
  commandline `api.runner`, not exe name.
- Task Scheduler registration needs admin (denied) → use the **Startup folder** instead (§6).
- Launch hidden via `wscript` + a `.vbs` (no console window).

---

## 6. Auto-start (runs at logon, hands-off)

`run_edgelog_hidden.vbs` (repo root) launches the runner hidden; a copy in
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EdgeLogRunner.vbs` runs it at every
logon. `--refresh-min 0` skips the AUGUR Yahoo master-refresh (it stalled the trade loop;
AUGUR refreshes on its own app-open). Output → `C:\EdgeLog\runner.log`. Liveness:
`users/{uid}/meta/<broker>_sync.last_sync` fresh (<40s). **Requires the broker's desktop app
open** for desktop-capture brokers.

---

## 7. Adding a broker — step-by-step (Webull worked example)

1. **Pick the capture.** Webull has an **official OpenAPI** → poll it (or use its
   watch-folder export) instead of a desktop plugin. Emit fills to a local CSV/queue with the
   same columns as §4.1. Asset class = **stocks/ETFs** (`assetType:"stock"`, no tick
   multiplier — `calc_pnl` stock branch).
2. **Write `api/webull_sync.py`** modeled on `nt_sync.py`: reuse `build_trades` (pairing),
   `_to_ny` (UTC→NY), the idempotent upsert, content-hash + state file. Set
   `source:"Webull"`, `broker:"Webull"`, `docId = "wb_<exitId>"`, heartbeat
   `meta/webull_sync`.
3. **Fees:** derive Webull's stock fee schedule from one statement; encode it (don't assume
   $0). Times: use Webull's UTC/epoch fill field → NY.
4. **Register in `runner.py`**: add a `--webull-*` source + a `sync_trades`-style call in the
   watch loop, each guarded by `try/except` (§5.4). Keep the auth gate (`--allow-uid`).
5. **UI:** the account toggle already supports multiple `source`s (shipped ~v44.2) — new
   trades appear under the Webull account automatically.
6. **Never** handle the user's Webull **login/PIN** (§8). Zero-touch = compute what's
   deterministic + capture from an authorized session/API, never automated web login.

---

## 7b. Webull — AS-BUILT (what actually shipped, 2026-07)

The §7 plan was written speculatively; the real implementation differs in several ways.
This subsection is authoritative for Webull.

**Capture = the official Webull OpenAPI directly (there is NO local file / watch-folder).**
- Webull's *web* platform has **no trade-history CSV export** (verified — the Orders widget
  only offers Move/Filter). So `api/webull_sync.py` polls the **official OpenAPI** and the
  API response *is* the capture — no `fills.csv` equivalent.
- SDK: `pip install webull-openapi-python-sdk`. `TradeClient(ApiClient(app_key, app_secret,
  "us"))`. Owner generated the **App Key / App Secret** in the Webull portal (Individual
  Application → instant approval). Creds live in **`C:\EdgeLog\webull_keys.json`** (outside
  the repo, like `serviceAccount.json`); the SDK's 2FA token is cached in
  **`C:\EdgeLog\webull_token\`** (status NORMAL, ~2-wk expiry that **auto-renews on each use**
  — re-auth only needed if the runner is off > 2 weeks).

**`api/webull_sync.py` (the module):**
- `fetch_fills(keys, start, end)` → `order_v2.get_order_history` per account. **ONE bounded
  call per account** (its cursor pagination is fragile — tail cursor returns
  ORDER_NOT_FOUND; a single call returns the whole window, group orders exceeding
  page_size). Per-account `try/except` so one bad account can't sink the pull.
- `build_trades(fills)` → FIFO pairing, **stock math** `(exit-entry)*dir*shares`, keeps the
  **full symbol** (no futures `get_base` truncation). Also sets `buyOrderId`/`sellOrderId`.
- `fetch_balance(keys)` → sums `total_net_liquidation_value`/`total_cash_balance` across
  **non-futures** accounts → written to `meta/webull_sync` as `net_liq`/`cash`. The web
  derives Webull's per-account starting equity from it (**no deposit-history endpoint
  exists**, so `start = net_liq − realized Webull P&L`).
- `reconcile(fills, keys)` → compares broker live positions (`get_account_position`) to the
  fills-implied positions → `recon{ok,flat,mismatches,positions}` in `meta/webull_sync`.
  Independent integrity check (catches a fill that didn't sync) that needs no deposit data.
- `sync_trades(db, uid, keys_path, force=False)` → idempotent upsert (`docId="wb_<exitId>"`,
  content-hash, state `C:\EdgeLog\.webull_sync_state.json`) + heartbeat.

**Quota / cadence (owner is on free Spark):** the auto pull is gated to **ONCE per NY day**
via `last_run_day` in the state file — NOT the 20s NT cadence. First run backfills
`backfill_days` (**180**, the API's max window; the account's history starts 2026-01-12,
so 180d covers it all); later runs re-pull a 7-day overlap (idempotent → free). An
on-demand **`sync_webull` runner command** (`force=True`) bypasses the daily gate — this is
the web's "Sync Webull now" button.

**Fees:** captured **per-fill** from the API's `commission`+`fees` fields (NOT a hardcoded
schedule). Webull US stock commission is $0; reg fees on cheap shares round to ~$0.

**Reauth hardening:** `ApiClient(..., token_check_duration_seconds=15)` bounds a re-auth
block to ~15s (vs the SDK's 5-min default) so it can't stall the shared runner loop; on
failure `webull_sync` backs off and sets `reauth_needed` in the meta doc.

**Verified API limits:** `page_size` max **100** (200 → PARAM_ERR); order-history window max
**~180 days** (wider → PARAM_ERR); the key exposes **3 accounts** (margin/stocks — the ones
we sync; a **futures** account we deliberately skip, stocks-only; and a cash account whose
balance/position endpoints sometimes 500 — caught & skipped). **No funding/deposit/
withdrawal endpoint exists** in the whole trade API.

**Runner wiring:** `--webull-keys` (env `EDGELOG_WEBULL_KEYS`, default the JSON above);
`FirestoreQueue.sync_webull()` called on startup + piggybacked on the trades timer (self-
gated to once/day); command action `sync_webull` for on-demand. All guarded by try/except.

---

## 8. Security hard lines (all brokers)

- **Never handle broker or Firebase login/passwords/PINs.** No automated web login; browser
  sessions expire and re-auth needs credentials — that wall is intentional, not a bug.
- `serviceAccount.json` (Firebase admin key) is **backend-only, gitignored — never commit it.**
- Runner command channel obeys the `--allow-uid` allowlist; ignore jobs from other uids.
- Bulk/production Firestore writes are gated by the harness classifier — expect targeted,
  user-authorized writes, not blind mass migrations.

---

## 9. File map

| File | Role |
|---|---|
| `api/runner.py` | always-on bridge; watch loop; queue + trade sync; `--allow-uid` gate |
| `api/nt_sync.py` | **reference sync module** (parse → pair → fees/tz → idempotent upsert) |
| `api/webull_sync.py` | Webull sync — official OpenAPI poll → pair → per-fill fees → upsert; + `fetch_balance`, `reconcile`; once/day gate; §7b |
| `tools/EdgeLogExport.cs` | NinjaTrader capture AddOn (fills → `C:\EdgeLog\fills.csv`) |
| `run_edgelog_hidden.vbs` | hidden launcher; Startup-folder copy = auto-start at logon |
| `index.html` | web app; `calc_pnl`/`PRESETS` are the P&L source of truth to mirror |
| `docs/BROKER_SYNC.md` | **this file** — the canonical contract for any broker |

_Add each new broker's module + capture to §9 and §7 as it ships._

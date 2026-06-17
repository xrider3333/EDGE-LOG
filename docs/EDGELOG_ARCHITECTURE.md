# AUGUR ⇄ EDGELOG — frontend/backend split (design sketch)

Goal: keep AUGUR's validated Python backtest engine running **locally** (full cores +
your 1.6 GB of data), but drive it from a **web UI** (EDGELOG on GitHub/Firebase) with
real design freedom — instead of the constrained Streamlit desktop app.

The single idea: **separate the engine from the UI.** Today `optimizer.py` is both. Split
it so the engine becomes a callable backend and the UI becomes any web frontend you like.

```
   ┌─────────────────────────────┐         ┌──────────────────────────────┐
   │  EDGELOG web frontend        │  HTTPS  │  Firebase (Firestore + Auth) │
   │  (HTML/CSS/JS, on Firebase)  │ ───────▶│  • jobs queue (you trigger)  │
   │  • pick strategy/master/scope│         │  • results docs              │
   │  • view results / equity     │◀─────── │  • live-vs-backtest drift    │
   │  • paper-trade tracking      │         └──────────────┬───────────────┘
   └─────────────────────────────┘                        │ watch jobs / write results
                                                           ▼
                                         ┌──────────────────────────────────┐
                                         │  AUGUR runner (local PC, Python)  │
                                         │  • augur_engine.run_backtest(...) │  ← UNCHANGED
                                         │  • strategy plugins (unchanged)   │
                                         │  • masters / SQLite (unchanged)   │
                                         │  • all cores, ProcessPool grid    │
                                         └──────────────────────────────────┘
```

## What stays vs changes

| Piece | Today | After |
|---|---|---|
| `run_backtest` engine + strategy plugins | in `optimizer.py` / `augur_strategies/` | **unchanged** — extracted into `augur_engine/` |
| Grid/WF/MC/DSR/fragility logic | `optimizer.py` | **unchanged** — moved alongside the engine |
| Masters / SQLite / config | local files | **unchanged** (stay local with the runner) |
| UI (tabs, pickers, charts) | Streamlit (Python) | **replaced** by EDGELOG web (HTML/JS) |
| Where compute runs | local | **still local** (the runner) |

Your trading-critical code does **not** get rewritten. Only the UI layer is replaced, and a
thin job-runner + API is added around the engine.

## Repo structure (target)

```
augur_engine/              # pure Python, no Streamlit — the validated core
  __init__.py
  engine.py                # run_backtest dispatch, _mp_eval_chunk, grid/WF/MC/DSR
  strategies/              # the plugin .py files (moved from augur_strategies/)
  data.py                  # masters load, combine_ohlcv_frames, find_master
  history.py               # SQLite read/write (runs, executions, csv_files)
api/
  server.py                # FastAPI: POST /backtest, GET /runs, GET /masters, ...
  runner.py                # local job-runner: watch Firestore queue -> call engine -> write results
  auth.py                  # verify Firebase ID token; only your uid may enqueue
edgelog-web/               # the EDGELOG frontend (HTML/CSS/JS, deploys to Firebase Hosting)
  index.html, app.js, ...
optimizer.py               # (legacy Streamlit UI — keep running during migration)
```

## Two ways to connect web → local compute

**A. Firestore job queue (recommended — no open ports on your PC).**
1. Web writes a job doc: `{uid, strategy, master, scope, params, status:"queued"}`.
2. The local `runner.py` (always running) listens to Firestore for `status=="queued"` docs
   with your `uid`, runs `augur_engine.run_backtest(...)`, writes results back + `status="done"`.
3. Web reads the results doc and renders. PC must be on + online; nothing is exposed publicly.

**B. Local API + tunnel.** `server.py` (FastAPI) exposes `POST /backtest`; a Cloudflare/ngrok
tunnel gives it a public URL the web calls. Simpler request/response, but the endpoint is
reachable from the internet → auth is mandatory (see below).

Prefer **A**: the queue is pull-based, so your PC never accepts inbound connections.

## "Authenticate the queue" — what that means concretely

Because a job triggers code execution on your PC, the runner must accept jobs **only from you**:
- Firebase Auth signs you in on the web; each job doc is tagged with your `uid`.
- `runner.py` ignores any job whose `uid` isn't yours, and Firestore security rules reject
  writes from anyone not signed in as you.
- Result: no anonymous internet visitor can enqueue a job. This is the lock between the public
  web and your local machine — small to set up, not optional.

## Migration path (incremental, low-risk)

1. **Extract the engine**: move the backtest half of `optimizer.py` into `augur_engine/`
   (the file already splits at the `# AUGUR v4.0 — UI Layer` marker — everything above it is
   the engine). Streamlit app keeps importing from it; nothing breaks.
2. **Wrap it in FastAPI** (`/backtest`, `/runs`, `/masters`) — test locally with `curl`.
3. **Add `runner.py`** + a Firestore project; prove one round-trip (web enqueues → runner runs
   → result shows). This is also exactly the **#20 live-vs-backtest drift monitor** plumbing.
4. **Build the EDGELOG UI** page-by-page against the API; keep Streamlit as fallback until parity.
5. Retire the Streamlit UI when EDGELOG covers your workflow.

## Why this is the right shape

- **Design freedom**: real HTML/CSS/JS — TradingView chart widgets, responsive iPad layout,
  no rerun jank, no glass-CSS hacks.
- **Speed unchanged**: backtests still run on your cores + local data (cloud wouldn't be faster
  and would cost monthly for a big VM).
- **One source of truth**: the validated Python engine is reused verbatim — web and any future
  client call the same `run_backtest`.
- **Natural home for paper-trading**: EDGELOG already tracks real trades; the drift monitor
  (#20) compares them to the engine's expectation via the same results docs.
```

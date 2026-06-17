# EDGELOG ⇄ AUGUR — go-live runbook

The full pipeline is built and verified. This is the ordered checklist to make it
LIVE. Everything compute-side runs on your PC; Firebase only carries the job/result
docs and hosts the EDGELOG UI.

```
EDGELOG "AUGUR" tab ──writes job──▶ Firestore users/{uid}/backtests ──▶ runner (your PC)
        ▲ live results (onSnapshot) ◀──writes result── api.runner ──▶ augur_engine
```

## 0. One-time installs (your PC)
```
pip install -r api/requirements.txt
```

## 1. Commit the EDGELOG frontend change (test on a branch first)
The AUGUR tab was added to `index.html`. The edited file is `_edgelog_live.html` in this
repo. Apply it to your EDGE-LOG repo:
- Easiest: copy `_edgelog_live.html` over `index.html` on a **new branch**, push, open the
  branch's GitHub Pages / preview, confirm the app still loads and the **AUGUR** tab appears.
- Or apply the 6 edits by hand (all are small; see the change list below).
- Merge to main once it looks right.

The 6 edits (search-and-find in index.html):
1. `const TABS=[...]` → add `'augur'` before `'settings'`.
2. `let db=null,auth=null,colRef=null,lessonRef=null,...` → add `btRef`, `unsubBT`, `backtests`.
3. After the `unsubL=lessonRef...onSnapshot(...)` line → add the `btRef` listener on
   `users/{uid}/backtests`.
4. Tab bar `lbl`/`icons` maps → add `augur` label + `⊞` icon.
5. Sign-out handler → add `if(unsubBT)unsubBT();`.
6. In `renderApp`, before `if(activeTab==='settings')` → add the `if(activeTab==='augur'){…}`
   block (launch form + results table).

## 2. Firestore security rule
See `firestore.rules`. If your existing EDGELOG rules already let a user read/write their
own `users/{uid}/**` subtree, **you need to change nothing** — backtests is covered. Otherwise
add the `/backtests` match (snippet in that file). Paste into Firebase console → Firestore →
Rules → Publish.

## 3. Get your two values
- **Service-account key**: Firebase console → Project settings → Service accounts →
  "Generate new private key" → save the JSON as `serviceAccount.json` in this repo folder.
  (This is a SECRET — it's already fine on your local disk; do NOT commit it. Add it to
  `.gitignore`.)
- **Your Firebase uid**: Firebase console → Authentication → Users → the UID column for your
  account. (Or in EDGELOG's console, `firebase.auth().currentUser.uid`.)

## 4. Start the runner (leave it running while you trade)
Edit `run_augur_runner.bat` — paste your uid into `AUGUR_UID` — then double-click it. Or:
```
python -m api.runner --firestore --cred serviceAccount.json --allow-uid <YOUR_UID> --watch
```
It prints each job as it runs. Only jobs from your uid are executed (the auth gate).

## 5. Use it
Open EDGELOG → **AUGUR** tab → pick strategy / instrument / session / vol filter →
**Run on my PC**. The row appears `QUEUED`, flips to `RUNNING`, then `DONE` with PF / trades /
net P&L — streamed live via the same onSnapshot path EDGELOG uses for trades.

## Test without the frontend (optional sanity check)
Local queue mode needs no Firebase at all:
```
python -c "from api.runner import LocalQueue; LocalQueue().enqueue({'strategy':'ORB_SIMPLE_1_0.py','instrument':'NQ','timeframe':'5m','session':'rth','source':'tv','params':{'vol_filter':1.5},'cost_pts':0.283})"
python -m api.runner            # processes augur_jobs/*.json, writes results back
```

## What's built (all verified)
- `augur_engine/` — streamlit-free engine (dollar-identical to the app).
- `api/server.py` — FastAPI over the engine (optional; `uvicorn api.server:app --port 8787`).
- `api/runner.py` — local + Firestore job runner with the uid allowlist gate.
- EDGELOG `index.html` — the AUGUR tab (in `_edgelog_live.html`, pending your commit).

## Optional polish after launch
- Auto-populate the strategy dropdown from `GET /strategies` (or a Firestore mirror).
- Render the equity curve in the results panel (the engine already returns the trade list).
- Add a "compare" view and the validation badges (WF / DSR / MC) from the mockup.
- Wire the #20 live-vs-backtest drift monitor: compare EDGELOG's real fills to the engine's.

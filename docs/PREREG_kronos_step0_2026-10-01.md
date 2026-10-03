# PRE-REGISTRATION — KRONOS Step 0: does it forecast the next NQ session's range better than free baselines? (2026-10-01)

Owner GO via MANAGER (inbox #40), scope = C:\EdgeLog\manager\kronos_assessment_2026-09-30.md section 3. Written and
pushed BEFORE any forecast (Kronos or baseline) is scored on the test period. FAIL = Kronos is closed for good.
Honest prior (the assessment's): low - outside tests say it ties HAR, not beats it by 5%.

## Data (no lockbox is read)
- Roll-corrected 5m 24-hour masters ADJ_NQ_5m_ETH / ADJ_ES_5m_ETH (db_adj_eth), named explicitly. Only price
  RANGES are studied; no strategy, run or lockbox result is computed or read. A Kronos context window that
  contains an unadjusted splice would look like a crash, which is why the adjusted masters are used.
- Session D = 5m bars from 18:00 ET on the prior trading day to 16:55 ET on D (bars are open-labelled).
  - TARGET: RTH range of D = max(high) - min(low) of bars 09:30 .. 15:55 ET.
  - Daily bar for D (Kronos context, baselines): open/high/low/close/volume of the whole session D.
  - OVERNIGHT range of D = high - low of bars 18:00 (D-1) .. 09:25 (D) - known at 09:30 of D.
- Sessions with fewer than 70 of the 78 RTH bars (half days, holes) are dropped from scoring for EVERY model.
- Test sessions: 2024-07-01 .. 2026-09-30 (Kronos's stated training cut-off is June 2024).
  H1 = 2024-07-01 .. 2025-06-30, H2 = 2025-07-01 .. 2026-09-30 (H2 is clean for certain: the released weights
  were uploaded 2025-06-30 / 07-01 and never changed).

## Forecasts (each made with information available before 09:30 ET of D)
1. **TRAIL5**: mean RTH range of the 5 prior sessions (ORB #314's trailing-range idea).
2. **EWMA**: RiskMetrics lambda 0.94 on squared RTH range; forecast = sqrt of the EWMA before D.
3. **HAR** (log form): log R(D) = b0 + b1 log R(D-1) + b2 mean log R(D-5..D-1) + b3 mean log R(D-22..D-1), R = RTH
   range; OLS fitted ONCE on sessions 2010-07-01 .. 2024-06-28 only; forecast = exp(fitted value).
4. **OVN**: the overnight range of D.
5. **KRONOS**: NeoQuasar Kronos-small (24.7M params) + Kronos-Tokenizer-base, the official MIT release
   (github.com/shiyu-coder/Kronos; weights from its Hugging Face page). Context = the last 512 completed daily
   bars before D (columns open, high, low, close, volume, amount = volume x close); one-step-ahead forecast of D's
   daily bar; the future timestamp is D's date from the exchange calendar (a session date is public in advance),
   never taken from the real bar. T = 1.0, top_p = 0.9, 20 sampled paths per forecast, each kept SEPARATELY (the
   released predictor averages paths; we call it once per path or take its per-path output); forecast = mean over
   paths of each path's high - low. model.eval() (dropout off). One device (the RTX 3080 Ti, CUDA) for every
   seed. Five seeds: 1, 2, 3, 4, 5 (torch + numpy + python seeded per run). Inference only - no fine-tuning, no
   authors' training scripts. Code and weights are downloaded once, read before running, and kept in an
   isolated venv under C:\EdgeLog\kronos\ (system packages reused read-only; nothing installed into the repo's
   Python or the runner's).
- **One scale correction per model**, fitted on H1 only: k = argmin of mean QLIKE over H1 of (k x forecast)
  (Kronos forecasts a 24-hour bar's range, the target is the RTH range; every model gets the same treatment).
  H1 scores therefore include that one fitted number for every model; H2 is pure out-of-sample.

## Score and pass bar (all must hold; set before any number exists)
- Loss per session: QLIKE on squared ranges, L = s/h - ln(s/h) - 1, s = realised RTH range^2, h = forecast^2.
- BEST free baseline = the lowest mean QLIKE among TRAIL5, EWMA, HAR, OVN, taken SEPARATELY in each half.
- PASS needs:
  1. NQ: Kronos mean QLIKE at least 5% below the best baseline in H1 AND in H2 (seed-averaged forecast);
  2. NQ: Diebold-Mariano test on the per-session loss difference vs that baseline, Newey-West (5 lags), one-sided
     p < 0.05, in H1 AND in H2;
  3. Kronos beats the best baseline (any margin) in H2 for every one of the 5 seeds separately;
  4. ES agrees: Kronos mean QLIKE below ES's best baseline in H2 (seed-averaged).
- Anything else = FAIL, and Kronos is closed for good (no re-runs with other contexts, models or settings).
- Reported regardless: every model's QLIKE and MSE-of-log-range per half, and Kronos vs HAR head to head.
- Not done, by scope: synthetic-path / stress tests, fine-tuning, direction calls, gates, any live use.

Driver: tools/kronos_step0.py (baselines run without any download; the Kronos arm only after the download).

## STATUS 2026-10-03 - free baselines scored (after the pre-registration above); Kronos arm not yet run
`python tools/kronos_step0.py baselines` (EDGELOG_ROOT = the shared checkout). 559 scored sessions (H1 247, H2 312).
Mean QLIKE after each model's H1-fitted scale (H1 / H2):

| model | NQ | ES |
|---|---|---|
| TRAIL5 | 0.3965 / 0.3668 | 0.4724 / 0.4149 |
| EWMA | 0.5065 / 0.3931 | 0.5925 / 0.4386 |
| **HAR** | **0.3934 / 0.3522** | **0.4474 / 0.3833** |
| OVN | 0.4714 / 0.5641 | 0.5373 / 0.6191 |

HAR is the best free forecast in both halves on both markets, so Kronos must reach NQ QLIKE <= 0.3737 (H1) and
<= 0.3346 (H2), with the DM test, all 5 seeds and ES (< 0.3833 in H2) as written. The Kronos arm waits only on
the download (code + Kronos-small weights + tokenizer). The Custom ML chat's safety rules let it download only on
the owner's DIRECT yes in that chat; a relayed go does not count, and two requests were cut off by app restarts.

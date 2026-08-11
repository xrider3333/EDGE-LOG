# PAPER TRADING — live forward-test system (canonical doc)

> **Audience:** any Claude session or human picking this up cold. Everything about the
> paper-trading system, the ORB look-ahead debacle, and current live state lives here.
> Sister docs: `BACKTESTING_STACK.md` (validation methodology), `RUNBOARD.md` (compare view).
> Last full update: **2026-08-11**.

## What this is

Forward-testing the crowned strategies on live data with no real money, to answer:
**does reality track the backtest — and if not, which layer diverges?**

| Layer | What | Measures | Status |
|---|---|---|---|
| 0 · SHADOW | The always-on runner re-runs each strategy daily ~16:10 ET on master + a fresh tail resampled from the NT AddOn's live 10s feed, logs would-have trades to Firestore | Live-data drift (signal-perfect by construction — **it reproduces engine bugs, see ORB below**) | **LIVE** since 2026-08-10 (`api/paper.py`, runner hook) |
| 1 · NT DEMO | NinjaScript ports auto-trading the broker demo account `DEMO7240108` in NinjaTrader; fills flow into EDGELOG via the existing AddOn auto-import (`account` field) | Fill/slippage/execution realism | Strategies compiled + installed; **NOT yet enabled on charts** (owner action, ~2 min) |
| 2 · RECONCILE | `tools/reconcile.py --daily` shadow-vs-demo-vs-backtest compare | Which layer diverges | Not built yet — needs demo fills to exist |

- **UI:** BACKTESTER ▸ **PAPER** tab (index.html) — per-leg tiles, cumulative curve, trades table, daily report docs.
- **Daily report:** runner writes `users/{uid}/paper_reports/{YYYY-MM-DD}`; a scheduled Claude session (`edgelog-paper-eod-review`, weekdays 13:25 local = 16:25 EDT) reviews and writes its verdict into the doc (status `runner_done` → `reviewed`).
- **PAPER_START = 2026-08-11.** Trades before that date are never logged.
- Sim101 note: NT's local Sim101 exists but doesn't appear in this setup's account dropdowns; the broker demo `DEMO7240108` is the chosen paper account (arguably more realistic fills). **Never** touch account `1810769` — that's real money.

## The legs

| Leg | Config | Timing verdict | State |
|---|---|---|---|
| ENGU-Q | `ENGUQ_1M_1_0.py` #149 + breakeven 1.5, NQ 1m RTH | **CLEAN** (all conditions at bar close, entry at that close). Its one MILD trail assumption is *conservative* — live-realistic lagged trail earns **more** (+$31k/16.1y, `tools/enguq_trail_lag.py`) | Shadow: live · NT: `EdgeLogENGUQ1m` compiled, awaiting enable |
| ORB | was `ORB_3_0.py` #125, NQ 5m RTH | **LOOK-AHEAD — dead as backtested** (below) | Shadow: still logging engine numbers (flagged fiction) · NT: V1 port retired, **V2 replaces it** |
| BLEND 1:1 | ORB + ENGU-Q | Suspect — ORB leg inflated | Rollup only |

## THE ORB LOOK-AHEAD (found 2026-08-10/11 — read before touching anything ORB)

**The defect:** touch-entry ORB fills at the range edge the moment price touches it
(intrabar) but gates the trade on the breakout bar's **finished** volume
(`vol_filter=1.25 × session mean so far`) — a number that does not exist at fill time.
The backtest takes the good fill *and* hindsight-selects the bars that ended fat.

**Measured (NQ 5m RTH, 16.1y — CORRECTED 2026-08-11: two "#125"s exist; the true crown
is ORB_3_1 with trail_bars=5; `t5_runboard.py`/`api/paper.py` carry a no-trail ORB_3_0
cut under the same name. Both leak):**

| Variant | Trades | Net | Verdict |
|---|---|---|---|
| Crowned #125 (touch + vol + trail 5) | 4,076 | $360,591 (PF 1.60, MAR 2.39) | NOT live-legal |
| The no-trail "$494k cut" (touch + vol) | 4,076 | $494,065 | NOT live-legal |
| Close-confirmed + vol + trail 5 | 3,979 | **−$6,744** | live-legal; the trail whipsaws on honest fills |
| Close-confirmed / vol-off variants (no trail) | ~4k | $44–69k | live-legal ceiling, PF ≤1.08 |
| Naive live emulation (enter→eject thin bars) | 26k fills | **−$58k** | fatal: ~1,516 ejections/yr pay round turns |

~91% of the edge was the level-fill + hindsight-volume combination. Gotcha: calling
`ORB_3_1_125C.py` with no params silently uses ORB_3_1's own defaults — its pins only
bind through the Builder/validate flow.

**Library audit (2026-08-11, all 60 strategy files):** the leak is the entire
**touch-entry ORB family — 15 files** (ORB 2.0/3.0/3.1/3.2/3.3 + forks). Everything else
is CLEAN (incl. **NOISE** — signal at close, fill next open) or MILD (same-bar trail
ordering: ENGUQ/REVERT/ENGU_1_3 families). Full table in memory
`edgelog-lookahead-audit-2026-08-11`; scripts in `tools/orb_*.py`.

**Why it survived months of testing:** WF/lockbox re-run the same engine, so a look-ahead
passes every statistical gate; TV parity checks were deliberately run `volFilter=0` on both
sides ("exact cross-check"), validating everything *except* the leaking component; the Pine
port header (June 2026) documented the gap qualitatively but nobody priced it.
**New mandatory pre-crown gate: execution-feasibility audit** — for every fill, ask
*"does every input exist at the moment of this fill?"*

## ORB V2 — the live-legal candidate (`tools/nt/EdgeLogORBV2.cs`)

Volume only accumulates, so V2 watches the **forming** 5-min bar tick-by-tick:
- gate for the bar = 1.25 × mean volume of today's *closed* bars (known at bar open)
- enter **at market** the moment BOTH have happened: range edge touched AND running
  volume ≥ gate (either order). Same trade selection as the engine; honest fills.
- No ejections ever (never enters unconfirmed). One real trade/session. Stop = 0.75×range
  from fill, ride to close. Refuses to trade historical bars (no intrabar data there).
  Mid-session enable: replays today's closed bars; stands down if the day's signal
  already fired (prints which case to NT Output).
- Measured on 34 sessions of real 10s data (`tools/orb_volarm_10s.py`): identical trade
  selection, chase cost ≈ −1 pt mean / −2.6 median (worst +177). **Cannot be backtested
  over 16y** (needs intrabar volume; only ~7 weeks of 10s exists) — **the PAPER forward
  test is the arbiter.** TV cannot express V2 (Pine has no intrabar cum-volume decisions).

## Current NT state (as of 2026-08-11 ~13:40 ET)

- **Nothing is enabled in NinjaTrader.** Compiled & installed (verified in the rebuilt
  `NinjaTrader.Custom.dll`): `EdgeLogORBV2`, `EdgeLogENGUQ1m`, `EdgeLogORB30` (V1 — retired,
  do not enable). Charts exist: NQ 5-min RTH + NQ 1-min (verify RTH + ≥30 days loaded).
- To go live (owner, ~2 min): chart ▸ Strategies ▸ add `EdgeLogORBV2` (5-min) /
  `EdgeLogENGUQ1m` (1-min) ▸ Account **DEMO7240108** ▸ defaults ▸ Enabled ▸ OK.
- Known V1 lessons already fixed in V2: orphaned protective stop after NT's session-close
  flatten; historical-replay trade marks confusing the chart; thin-vol scratch churn.

## Candidate legs to add (2026-08-11 assessment)

Criteria for going live on the demo account: (a) execution-feasibility CLEAN (no
look-ahead), (b) something real to learn from a forward test, (c) low port cost.

| Candidate | Timing | Verdict |
|---|---|---|
| **ENGU-Q #149** | CLEAN | **RUN IT** — already ported and compiled |
| **ORB V2** | CLEAN by construction | **RUN IT** — un-backtestable, so forward test is the ONLY evidence path |
| **NOISE 1.0** | CLEAN (close signal → next-open fill) | **BEST THIRD LEG.** Easiest port of all (market order at next bar's open — no intrabar logic). Forward testing also sidesteps its two open problems: ES-transfer FAILED (PF 1.12) and the lockbox-status contradiction in its own docstring. Live paper data is *new* evidence neither of those blocks. Use the validated config: lookback 14 · bands 1.5/1.5 · vwap exit · both sides · all_day, `stop_mode='bandwidth', stop_k=1.0` |
| ORB_FADE_1_0 | CLEAN (close-anchored) | Only if it has a validated config — check `ORB.md`; otherwise not worth the port |
| TTIBS_1_0 | CLEAN | Daily bars, one decision/day — trivial to port BUT failed the lockbox previously; forward testing a rejected strategy is low value. Skip unless owner wants it |
| VWAP_FADE_2_0 / GAPFADE / SUPERTREND_3 / GAINZ_RF | CLEAN | Clean but never crowned — no reason to spend paper slots yet |
| REVERT / ENGU_1_3.x | MILD | Not crowned; MILD trail assumption; skip |
| Any touch-entry ORB (15 files) | **LEAK** | Never — they cannot be executed as written |

**Recommended paper book: ENGU-Q + ORB V2 + NOISE.** Three legs, three different
mechanisms (trendline break / opening-range breakout / noise-band momentum), all
execution-clean, one shared demo account.

## Open items

1. Owner: enable the two strategies (above).
2. `reconcile.py --daily` once demo fills exist.
3. Decide the shadow ORB leg: still logs engine (look-ahead) numbers — either swap it to a
   V2-equivalent shadow (needs 10s-aware shadow path) or read its PAPER line as reference-only.
4. NQ masters end 2026-07-16 — refresh from the AddOn 10s feed (import path exists:
   `tools/import_nt_ohlc.py`); needed before any fresh engine-vs-chart comparison.
5. NOISE: resolve the lockbox-spent contradiction in its docstring; ES-transfer already failed once.
6. Blend baseline ($835k) flagged suspect until ORB is re-based on live-legal rules.

## Tooling index

`api/paper.py` (shadow engine + EOD hook) · `tools/paper_smoke.py` ·
`tools/orb_live_legal_variants.py` · `tools/orb_barclose_entry.py` ·
`tools/orb_session_trace.py` (bar-by-bar "when is what known") ·
`tools/orb_live_emulation_cost.py` · `tools/orb_volarm_10s.py` (10s intrabar reconcile) ·
`tools/enguq_trail_lag.py` · `tools/nt/EdgeLogORBV2.cs` · `tools/nt/EdgeLogENGUQ1m.cs` ·
`tools/nt/SIM101_SETUP.md` (account section superseded: use DEMO7240108)

# PAPER TRADING — live forward-test system (canonical doc)

> **Audience:** any Claude session or human picking this up cold. Everything about the
> paper-trading system, the ORB look-ahead debacle, and current live state lives here.
> Sister docs: `BACKTESTING_STACK.md` (validation methodology), `RUNBOARD.md` (compare view).
> Last full update: **2026-08-11**. Legs updated **2026-08-24** (`NOISE_SBS_V90_H` added —
> the run-#243 crown with its own chosen et@0.50 hybrid gate, FORWARD EVIDENCE ONLY; the
> gate family stays closed for backtest adoption. Prior update 2026-08-23: NOISE crown →
> Short Veto + Wild10 run #243, `NOISE_SBS` leg replaced by `NOISE_SBS_V90`).

## What this is

Forward-testing the crowned strategies on live data with no real money, to answer:
**does reality track the backtest — and if not, which layer diverges?**

| Layer | What | Measures | Status |
|---|---|---|---|
| 0 · SHADOW | The always-on runner re-runs each strategy daily ~16:10 ET on master + a fresh tail resampled from the NT AddOn's live 10s feed, logs would-have trades to Firestore | Live-data drift (signal-perfect by construction — **it reproduces engine bugs, see ORB below**) | **LIVE** since 2026-08-10 (`api/paper.py`, runner hook) |
| 1 · NT DEMO | NinjaScript ports auto-trading the broker demo account `DEMO7240108` in NinjaTrader; fills flow into EDGELOG via the AddOn auto-import (`account` + `SignalName`) | Fill/slippage/execution realism | **LIVE since 2026-08-11** — NOISE trading, ENGU-Q + ORB V2 enabled but out of sync (see NT state) |
| 2 · TRADINGVIEW | Pine ports of the same strategies on layout **PAPER EdgeLog**, run in TradingView's own engine, exported as "List of trades" and matched trade-for-trade against ours (`tools/reconcile.py --tv`) | Whether the RULES are what we think they are — a second engine that shares no code with ours | **NOISE: LIVE**, reconciled 2026-08-12 (see below) · ENGU-Q: blocked on chart session |
| 3 · RECONCILE | `tools/reconcile.py --daily` shadow-vs-demo-vs-backtest compare | Which layer diverges | Not built yet — needs demo fills to exist |

**Why layer 2 earns its place.** Layers 0 and 1 both run OUR code, so both reproduce our
bugs — layer 0 says so in its own row. TradingView re-implements the strategy from the Pine
source in an engine we did not write, so a rule we got wrong shows up as a trade mismatch.
On its first run it immediately caught a defect the summary statistics hid completely: net,
profit factor and trade count all looked healthy while a quarter of the trades were being
held overnight against a hard rule. Only the trade-by-trade match exposed it.

**It is not automatic.** The trade list has to be exported by hand (TradingView ▸ Strategy
Tester ▸ List of trades ▸ download), and pasting a Pine script into the editor cannot be
automated at all — see the gotchas below. Treat this as a deliberate periodic check, run
after any change to a strategy's rules, not as a nightly job.

- **UI:** BACKTESTER ▸ **PAPER** tab (index.html) — per-leg tiles, cumulative curve, trades table, daily report docs.
- **Daily report:** runner writes `users/{uid}/paper_reports/{YYYY-MM-DD}`; a scheduled Claude session (`edgelog-paper-eod-review`, weekdays 13:25 local = 16:25 EDT) reviews and writes its verdict into the doc (status `runner_done` → `reviewed`).
- **PAPER_START = 2026-08-11.** Trades before that date are never logged.
- Sim101 note: NT's local Sim101 exists but doesn't appear in this setup's account dropdowns; the broker demo `DEMO7240108` is the chosen paper account (arguably more realistic fills). **Never** touch account `1810769` — that's real money.

## CROWNED IS NOT THE SAME AS FORWARD-TESTED (recorded 2026-08-19)

The website STUDIES board now tags every research row as CROWNED, IN PAPER, both, or neither,
and the first thing it surfaces is a mismatch that had gone unstated: **the ORB leg being
forward-tested is the PREVIOUS crown, not the current one.**

- The standing ORB champion is run #234 (ride to a 5.5x-risk target with the stop moved to
  breakeven at 1x risk, no partial exit and no trailing stop).
- The ORB paper leg still runs run #230, the round-one grail-hunt winner, which is what the
  crown was before #234 took it on 2026-08-17.
- NOISE (updated 2026-08-23): the crown moved again, to Short Veto + Wild10 (run #243 —
  run #241's config plus "skip all trades the day after a top-decile volatility
  session"), on the owner's risk-adjusted case (~2% less profit for ~41% less drawdown,
  PF 1.39 vs 1.29, best ES transfer in the family). The run-#241 leg `NOISE_SBS` was
  RETIRED after two days and REPLACED by `NOISE_SBS_V90` — the crown leg tracks the
  crown, same convention as the ENGU-Q swap — with `NOISE_225` (the old champion core)
  staying as the matched raw control. **The NinjaTrader demo leg carries NEITHER crown
  filter yet**: `EdgeLogNOISE` has both knobs (`SkipBotShort` since 08-21, `VolSkipOn` +
  `VolSkipPct` since 08-23, all default OFF) but keeps running the baseline core + gate
  until they are flipped on after an NT restart. So for NOISE the crowned config is
  forward-tested at the SHADOW layer only, and that is a recorded divergence, not an
  accident.
- ENGU-Q is aligned on the certified champion (#226 ETH), with #249 added alongside it as an
  adopted variant under its own matched control.

This is a REPORTING note. Nothing about the live paper configuration was changed to write it;
whether to move the ORB leg onto #234 is the owner call.

## The legs

| Leg | Config | Timing verdict | State |
|---|---|---|---|
| ENGU-Q | `ENGUQ_1M_1_0.py` #149 + breakeven 1.5, NQ 1m RTH | **CLEAN** (all conditions at bar close, entry at that close). Its one MILD trail assumption is *conservative* — live-realistic lagged trail earns **more** (+$31k/16.1y, `tools/enguq_trail_lag.py`) | Shadow: live · NT: `EdgeLogENGUQ1m` compiled, awaiting enable |
| ENGU-Q L50 | `ENGUQ_1M_ETH_LIM50_1_0.py` #249 — #226 ETH config + resting limit 0.50 x ATR below the signal close, 10-bar gap-honest fill window | **CLEANEST entry we run.** A resting limit is the one entry type that needs no assumption about getting a bar's closing print — you place the order and wait | Shadow: **live since 2026-08-18** · control = the ENGU-Q ETH leg · NT: limit support written, **NOT deployed** |
| ORB | `ORB_3_4_C221.py` #230 (ORB-40), NQ 5m RTH — **swapped 2026-08-16** off the retired #125 `ORB_3_0` cut | **CLEAN** — close-confirmed entry, the whole point of the grail hunt that produced it | Shadow: live · NT: V1 port retired, **V2 replaces it** |
| ORB +GATE | #230 + its own crowned **rf hybrid gate @45%** | Same as ORB — a gate is a post-trade overlay trained only on finished trades | Shadow: live · control = the ORB leg |
| NOISE | `NOISE_1_0.py` hand-built round-12 config, NQ 5m RTH | **CLEAN** (close signal → next-open fill) | **RETIRED 2026-08-16** ("remove the old noise raw") — never crowned by a run; superseded by NOISE-225 |
| NOISE-225 | `NOISE_1_0.py` #225/#202/#231 crowned core (lookback 44, 0.75/1.5, stop 1.75) | CLEAN | Shadow: live · emitted free as NOISE-225 +GATE's control · also the matched control for NOISE-241 · NT: `EdgeLogNOISE` runs this core (+ live gate) |
| NOISE-241 SHORT VETO | `NOISE_1_0.py` #241 config — the NOISE-225 core + skip short entries the day after the prior session closed in the bottom 20% of its own range | CLEAN (the filter is a session-open decision from prior-session data) | **RETIRED 2026-08-23** — held the crown 08-21→08-23, replaced by NOISE-243 below when the owner moved the crown; provenance kept |
| NOISE-243 VETO+WILD10 | `NOISE_1_0.py` #243 crowned config — the #241 config + skip ALL entries the day after a session whose (H-L)/C ranked in the top 10% of the trailing 252 sessions | CLEAN (both filters are session-open decisions from prior-session data) | **THE NOISE CROWN since 2026-08-23** (owner call: ~2% less profit for ~41% less DD, PF 1.39 vs 1.29, best ES transfer 1.116; caveat — the vol leg's gains sit in its 10 best avoided trades). Shadow: **live since 2026-08-23** · control = NOISE-225 · NT: both knobs ported (`SkipBotShort`, `VolSkipOn`, default OFF), **NOT enabled** — flipping them waits on an NT restart and an owner call |
| NOISE-243 +GATE | `NOISE_1_0.py` #243 crowned config + **run #243's own chosen hybrid gate (et @50%)** | CLEAN (the gate is a post-trade overlay trained only on finished trades; both base filters are session-open decisions) | Shadow: **live since 2026-08-24** · control = NOISE-243 (identical params, gate off) · **FORWARD EVIDENCE ONLY — the gate family is CLOSED for backtest adoption** (below) · NT: not run |
| NOISE-225 +GATE | #225 config + **tree hybrid gate @55%** | CLEAN | Shadow: live · **a forward TEST, not a crown** (below) |
| BLEND 1:1 | ORB + ENGU-Q | Suspect — the ORB leg was inflated until the 2026-08-16 swap | Rollup only, hidden in the UI |

## THE ML GATE ON PAPER (built 2026-08-16 — `api/paper_gate.py`)

Every ML result this project has produced lived in the optimize/validate path and **none of it
had ever been forward-tested** — `api/paper.py` called `run_backtest` with a plain params dict
and nothing else. That gap is now closed.

**What a gate is.** The strategy picks its trades exactly as always. A second model scores each
trade at the moment it fires and either refuses the weak ones (`cut`) or refuses them *and*
sizes the survivors by score (`hybrid`). The strategy file is never touched.

**Why it is safe to forward-test.** The model only ever trains on trades that had already
FINISHED before the current trade's entry bar. That discipline lives in
`augur_engine/ml_gate.py::gate_trades`; `paper_gate.py` deliberately does not reimplement it —
it calls that function with `threshold=0.0` (a pure scoring pass) and applies the cut-off and
size dial to the returned scores, which is byte-for-byte how `gate_validate` builds its own
candidate and hybrid rows.

**The one deviation, stated plainly.** `gate_validate` normalises hybrid sizes by the mean
weight over its pre-lockbox survivors. A forward test cannot compute that without averaging over
its own future, so `size_norm` is a **frozen constant** measured once by
`tools/paper_gate_calibrate.py` against the source run's own window. That tool reproduced each
source run exactly — ORB_H 1946 survivors / max size 1.78 vs #230's stored `kept_pre 1946 /
max_size 1.78`; NOISE_H 2206 / 1.80 vs #225's `2206 / 1.8`. Re-run it if base params, model or
cut-off ever change.

**Matched controls.** A gated leg alone answers nothing — the question is never "did the gate
make money" but "did it beat the same strategy with the gate off". So every gated leg is paired:
ORB +GATE reads against ORB (verified 2026-08-16 to be a bit-identical trade set; both legs now
load the same full history so it stays that way by construction), and NOISE-225 +GATE against
NOISE-225, which is emitted from the *same backtest* via `emit_ungated_as` at no extra cost.

### ORB +GATE — the evidence-backed one
Run #230's crowned gate is `rf@0.45`, chosen by the pre-registered net-dollars / 80%-MAR-floor
rule on **pre-lockbox data only**, and it HELD its one look at the lockbox (recovery 2.48 vs
2.31). Its hybrid row was then best of five on **both** halves: top pre-lockbox recovery (6.97)
*and* the best held-out year (PF 1.403 vs 1.311 ungated, $3,982 vs $3,229, drawdown −1,219 vs
−1,400). Best before and after the boundary is the pattern you want, and it is the only ML
variant in this project that has it.

> This also overturns, **for ORB only**, the older program-wide "no adoption anywhere" verdict —
> that was measured on the *leaky* ORB family, where the gate's apparent edge was the leak.

### NOISE-225 +GATE — a pre-registered forward TEST, not a crown
**Do not report this as a validated result.** Run #225's *actual* crowned gate was
`logistic@0.55` and it **FAILED** its lockbox outright (gated recovery 0.44 vs ungated 1.50).
The `tree` hybrid at the same floor posted by far the best held-out year (PF 1.240 vs 1.128,
$3,117 vs $2,286, drawdown −1,079 vs −1,521) — but its **pre-lockbox recovery (5.96) was the
worst of the five**, so the selection rule, which only ever sees pre-lockbox data, would never
have picked it. Its lockbox win is visible only in hindsight, and crowning it would be exactly
the lockbox-shopping `gate_validate` exists to prevent.

Forward-testing is the one legitimate way to settle a result like that: the claim is written
down *before* the data exists, and paper trading costs nothing but compute.

> **THE CLAIM, stated so it can fail:** from **2026-08-16** forward, NOISE-225 +GATE should beat
> NOISE-225 on recovery factor. If it does not, the pre-lockbox ranking was right and the
> lockbox row was noise.

**Known quirk worth watching:** a depth-3 tree produces very few distinct leaf probabilities, so
on recent trades its "size dial" has been a near-constant ~0.85× haircut rather than a real
per-trade dial. That is honest tree behaviour, not a bug — but it means this leg may end up
testing *"trade ~15% smaller and skip a few"* more than *"size by conviction"*.

### NOISE-243 +GATE — the crown's own hybrid, forward evidence ONLY (added 2026-08-24)

Added at the owner's ask: on run #243's report the HYBRID tab's risk/reward beats RAW
(the xgb tab he read: MAR 22.6 vs 15.03, Sharpe 1.42 vs 1.34, PF 1.44 vs 1.37, REDEPLOY
WF+LB $488k vs $349k), a pattern he sees across strategies. Two honesty notes, recorded
before a single forward trade exists:

1. **The leg runs `et`, not `xgb`.** Run #243's own `gate_validate.chosen` — the model the
   standing pre-registered net-dollars/80%-MAR-floor rule picked on PRE-lockbox data only —
   is **extra-trees at the 0.50 floor**, not the xgb tab the owner read. On the years the
   rule is allowed to see, xgb does not even clear ungated (recovery 12.16 vs 17.38) and its
   lockbox slice is the worst of the five (PF 1.016, $130). Picking xgb by eye off its
   report tab would be hindsight selection; the leg runs the doc's choice.
2. **The gate family is CLOSED for backtest adoption.** It failed its lockbox twice (#219,
   and the #225/#231 verdict), and run #243's own card carries the same verdict: "LOCKBOX
   FAILED — gate lost to ungated out-of-sample (pre-lockbox win was likely fit)". In-sample
   hybrid outperformance is exactly the pattern that failed before. Forward paper testing is
   the one legitimate new-evidence path left for gated NOISE — which is why this leg exists,
   and why it must never be crowned, adopted, or cited as validated off backtest numbers.

> **THE CLAIM, stated so it can fail:** from **2026-08-24** forward, NOISE-243 +GATE should
> beat its matched raw control NOISE-243 on recovery factor. If it does not, the lockbox
> verdict was right and the in-sample shine was fit.

Its control is exact: the NOISE-243 raw leg runs the identical file, params and full-history
window with the gate off. `size_norm`/`recycle_factor` frozen by
`tools/paper_gate_calibrate.py` on 2026-08-24 against run #243's own window.

**Cost:** the gated legs load full history so the gate is the model the validate crowned rather
than a 150-day cousin. ORB_H's rf walk is ~110s, NOISE_H's tree ~6s — about two minutes added to
the once-a-day EOD run.

## THE GATE IS NOW LIVE IN NINJATRADER (2026-08-16, owner-approved architecture)

The ML could not be ported into NinjaScript (a random forest is 100 trees), so it stays in
Python and **NinjaTrader asks it for permission** just before entering:

- **`api/gate_live.py`** — the "bouncer" service, its **own process** on 127.0.0.1:8392
  (deliberately NOT a runner thread: the runner saturates every core during optimizes, and a
  missed deadline silently un-gates a live entry). Autostarts at logon via
  `Startup\EdgeLogGate.vbs` → `C:\EdgeLog\_gate_server.bat`; log at `C:\EdgeLog\gate_live.log`.
- **Nightly artifact**: after each close (16:15 ET, self-scheduled) it re-fits the as-of-now
  model per gated leg — same features / model family / threshold / frozen size divisor as the
  paper leg, trained on every completed trade of that leg's own backtest (master + fresh tail).
  Fit takes ~2s per leg; artifacts in `C:\EdgeLog\gate_models\`.
- **`EdgeLogNOISE`** now calls `GET /gate/check?leg=NOISE_H_RF` at entry time (new params
  GateEnabled / GateUrl / GateTimeoutMs, group "ML GATE"). **Fail-open on both sides**: any
  error/timeout (300ms) → trade ungated at Qty, printed to the NT log. Historical bars never
  call the gate (the service only knows "now"). Measured warm latency: **50–65ms**.
- **NT NOISE also moved to the #231 crowned config** (44 / 0.75 / 1.5 / 1.75) at the same
  time — the gate model is trained on that config's trades, so gating the old hand-built
  config with it would have been nonsense. `tools/nt_config_reconcile.py` now maps
  EdgeLogNOISE ↔ the NOISE_H_RF leg (verified 4/4 OK).
- **Sizing granularity**: at Qty=1 on full NQ the hybrid's fractional sizes round to 1, so
  live it acts as pure keep/skip. The size dial becomes real by running Qty=10 on MNQ
  (10 micros = 1 NQ) — a chart/instrument change, not a code change.
- **Orders never move**: the service cannot place, resize, or cancel anything. Kill switch,
  circuit breaker, and the live-account hard-lock are untouched.
- **Watch out**: lookback 44 needs ~44 completed sessions of chart history. If the NOISE
  chart loads fewer days, it will simply never trade — silently. Verify the chart's
  "days to load" ≥ 70 if Monday shows no NOISE entries where the engine has one.
- **Known divergence, pre-existing**: `EdgeLogORBV2` still runs the old #125-era chase
  params while the engine's ORB leg moved to #230 — the reconcile now reports it. Aligning
  V2 (a different mechanism) to #230 is open work.

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

## Current NT state (as of 2026-08-13 ~12:10 ET)

**The previous version of this section said "nothing is enabled in NinjaTrader". That was
wrong from 2026-08-11 onward and nobody noticed until the Layer 3 reconcile was built and
started asking where the fills were coming from. Treat this section as something to verify,
not to trust.**

All three strategies are enabled on `DEMO7240108`, all on NQ 09-26:

| Strategy | Bars | Strategy pos | Acct pos | Sync | State |
|---|---|---|---|---|---|
| `EdgeLogNOISE` | 5 min | 1 L @ 30144.25 | 1 L | **True** | **Trading.** Realized $1,740 today |
| `EdgeLogENGUQ1m` | 1 min | 1 L @ 29730.25 | 1 L | False | Holding a stale position, placing nothing |
| `EdgeLogORBV2` | 5 min | flat | 1 L | False | Flat, placing nothing |

**NOISE ran the bar-of-day bug live from 2026-08-11 until the 11:20 ET recompile on
08-13.** Any demo P&L spanning that boundary mixes broken and fixed code — do not read it.

**Three strategies on one account cannot be kept straight, and this is NinjaTrader's own
position, not an opinion:** each strategy tracks its own virtual position but the ACCOUNT
nets them, so when one exits "its" contract it may sell another's. NinjaTrader's guidance is
separate accounts or one combined strategy. The Sync=False rows above are that collision
showing itself.

**Plan (agreed 2026-08-13):** NinjaTrader allows *unlimited* local simulation accounts
(Tools ▸ Options ▸ Multi Providers, restart, then Accounts tab ▸ right-click ▸ New
simulation account). Give ENGU-Q and ORB V2 one each; leave NOISE on the broker demo, which
has realistic broker fills. For LIVE later: separate live accounts, or fold the legs into a
single NinjaScript — the live analogue of the BOOK job type, which already pools legs and
scores them as one strategy.

**Do all of this while flat.** Compiling restarts every running strategy; NOISE survived a
mid-trade recompile on 08-13 with Sync intact, but an orphaned position with no stop is the
failure mode to avoid.

- Known V1 lessons already fixed in V2: orphaned protective stop after NT's session-close
  flatten; historical-replay trade marks confusing the chart; thin-vol scratch churn.

## TradingView layer — visual cross-check (added 2026-08-12)

Layout **PAPER EdgeLog** (`tradingview.com/chart/BTeSKT1C/`), owner's account. Purpose is
**price-action eyes + an independent execution engine**, not a second backtest of record.

| Pane | Symbol/TF | Script | Why it is a fair check |
|---|---|---|---|
| 1 | NQ1! · 5m · RTH · non-adjusted | `EDGELOG NOISE 1.0` (`pine/NOISE_1_0.pine`, written 2026-08-12) | NOISE decides at bar close and fills next open — exactly TradingView's `process_orders_on_close=false` model. Faithful by construction. |
| 2 | NQ1! · 1m · RTH | `ENGUQ_1M_1_0` (existing July port, already TV-reconciled) | Same close-decide / next-open-fill convention. |
| 3 | NQ1! · 5m | *(none)* | Plain price. **ORB deliberately excluded** — owner call 2026-08-12. |

**ORB is not on TradingView and should not be added.** V2's entire fix is reading volume
as it accumulates *inside* a forming bar; Pine cannot see that. Any ORB Pine script here
would be a different strategy wearing the name, which is how the original leak hid.

First TV run, NOISE, Aug 2025 → Aug 2026 (~1y is all TV serves at 5m):
net **+$37,081** · PF **1.205** · 196 trades · 37.8% win · max DD **$48,198**. Treat as a
smoke test that the rules execute, not as evidence — one year, one contract series, and
TV's continuous NQ is rolled differently from our no-adjust master.

Gotchas for the next session driving this:
- **Clipboard paste into the Pine Editor cannot be automated.** Ctrl+V via the extension,
  synthetic paste events, and `execCommand('insertText')` all fail or get mangled by
  Monaco's auto-indent (Pine is indentation-significant). Hand the paste to the owner.
- The Pine Editor mangles non-ASCII on the way in — keep ports ASCII-only or the strategy
  title renders as mojibake (cosmetic only).
- Panes 2 and 3 resist programmatic focus; ask the owner to click the target pane.
- The Strategy Tester panel would not open from any of its buttons; what worked was
  **dragging the divider just above the collapsed strip upward**. Export is the download
  icon on the "List of trades" tab → lands in Downloads → `reconcile.py --tv auto`.
- The engine's `--from` clips the master array *before* the strategy runs, so it eats the
  warm-up. Start the engine window where TradingView's data starts, not where its first
  trade is, or the engine sits out its first N sessions and the trade counts won't line up.

### Reconcile #1 — NOISE, engine vs TradingView (closed 2026-08-13) — **PASS**

`NOISE_1_0.py` NQ 5m RTH, `stop_mode=bandwidth stop_k=1.0`, cost 0.283 pts, window
2025-08-18 → 2026-07-16 (master ends there).

**Final state: engine 191 trades / TV 189 / 159 matched, and 157 of those 159 agree on the
exit bar TO THE MINUTE for $191 total.** That is the port verified against an engine that
shares no code with ours.

It took three rounds, and every round found a real defect that the summary statistics hid.

| Round | Matched | Exit bar identical | PnL gap on those | Defect found |
|---|---|---|---|---|
| 1 | 151 | 111 | $139 | 36 trades held overnight instead of flattening at 15:55 |
| 2 | 155 | 153 | $189 | 32 trades **entered at 16:05**, after our session closes |
| 3 | 159 | **157** | **$191** | — |

**Round 1 — the flatten never ran.** First hypothesis was that `close_all` fired but filled
late (`process_orders_on_close=false` defers a market order to the next bar's open). Adding
`immediately=true` changed the result by exactly nothing, and that null result was the
useful part: the real cause was that **`session.islastbar` never evaluates true on this
chart at all.** Proof was in the export's Signal column — 197 trades, zero `eod` exits.
Fixed with an explicit session-end test (`atClose` on a 16:00 ET `time_close`, OR'd with
both `session.islastbar` variants). It now produces ~56 `eod` exits.

**Round 2 — TradingView's RTH is longer than ours.** With the flatten working, 32 fresh
entries appeared at 16:05 losing $35,457: TV serves 16:05 and 16:10 bars inside "regular
hours" for NQ1! that `NOADJ_NQ_5m_RTH` does not have. Fixed by gating entries on
`inRTH = not na(time(timeframe.period, "0930-1600", "America/New_York"))`.

**What is left is data, not rules.** ~30 unmatched trades per side, scattered across all 10
months, no time-of-day or calendar clustering. Half of them are the *same* signal shifted
under 30 minutes, and 17 of 25 unmatched days appear on both sides — the signature of
marginal band breaks flipping because TradingView's rolled NQ1! continuous contract is not
our no-adjust master. That residual cannot be removed and should not be chased.

**The lesson worth keeping.** All three defects were silent. Nothing errored; the strategy
just quietly stopped obeying one of its rules while net, profit factor and trade count all
stayed plausible. Round 1's headline (+$37k, PF 1.205) looked fine with a quarter of the
trades breaking a hard rule. Only the trade-by-trade match caught any of it.

**Pine gotchas paid for here** (all in `pine/NOISE_1_0.pine`):
- `session.islastbar` can silently never fire. Verify with the Signal column, not the totals.
- `close_all` needs `immediately=true` under `process_orders_on_close=false`.
- TV's regular session for NQ1! extends past 16:00 ET.
- Pine will not continue an expression onto a line starting with `or` after a closing
  bracket — `Mismatched input 'end of line without line continuation'`. One line per boolean.

### ENGU-Q reconcile — BLOCKED, not attempted

Two independent blockers, both on our side:
1. **A 1-minute data hole that free sources cannot fill.** TradingView's ENGU-Q trades run
   2026-07-20 → 2026-08-05. `tools/refresh_noadj_yahoo.py` was run 2026-08-12 and extended
   every non-adj master to current — but Yahoo only serves **7 days** of 1m, so it appended
   a fresh tail from ~2026-08-06 and left the old series ending 2026-06-30 (ETH) /
   2026-07-16 (RTH). The gap is exactly the window TradingView covers, so the overlap is
   still zero. Confirmed by running it: engine 4 trades, TV 0, matched 0.
   The 5m masters ARE now current, which is why the NOISE reconcile worked.
   Paths forward: (a) wait — the NinjaTrader 1m capture (`nt_noadj_eth`, live since
   2026-08-05) and TV's rolling 24-day window will overlap on their own in a few weeks;
   (b) buy the 1m history. Do not re-run the Yahoo refresher expecting a different result.
2. **Session mismatch.** `ENGUQ_1M_1_0.py` is validated on **RTH**; chart 2 is currently on
   **ETH** with back-adjustment on, and its trade list shows 00:32 / 04:49 fills. Whatever
   that pane is testing, it is not the champion. Flip to RTH + B-ADJ off before exporting —
   the toggles at the bottom-right of the pane did not respond to programmatic clicks.

### Reconcile #2 - NOISE, engine vs NinjaTrader (2026-08-13) - PASS

`EdgeLogNOISE` in the Strategy Analyzer, NQ 5m, custom session template
`EDGELOG RTH 0930-1600`, merge policy **Merge Non Back Adjusted**, same window as
reconcile #1. Engine 191 trades / NT 192 / **184 matched, and all 184 agree on the exit
bar**. Entry-price gap 0.0 points at both ends of the window - the two are running on
byte-identical bars. Residual $1,737 on the matched set is mostly commission (the NT run
had Include commission off) plus NT rounding its stop to tick size. 7 unmatched each side,
scattered across ten months with no pattern.

Getting there took three fixes, each of which was silent:

| Fix | Symptom | Cause |
|---|---|---|
| Session template | 417 trades, exits at 17:00 ET | NT's built-in `CME US Index Futures RTH` ends 4:00 PM **Central** = 5:00 PM Eastern. Copy it, set end 3:00 PM, keep the holiday calendar. |
| Merge policy | prices +747 pts in Sep 2025, +282 by June | NQ was back-adjusted. `Tools > Instruments > NQ > Merge Non Back Adjusted`. A DECAYING price gap is the fingerprint. |
| **bar-of-day froze** | 322 trades, trading 151 days vs 108 | The in-position branch returned before `barOfDay++`, so bar-of-day stopped advancing the moment a trade opened and stayed stale for the rest of the session. Noise is smallest after the open, so a stale index gave too-small noise, too-narrow bands, way too many entries. **This was live on the demo account.** |

**Strategies now dump their own blotter.** Exporting by hand through Display > Trades >
right-click > Export produced the wrong file twice in one morning (wrong strategy once,
wrong timeframe once) and neither was visible until the CSV was parsed, because the grid
export records nothing about what was run. `tools/nt/EdgeLogNOISE.cs` now writes
`C:\EdgeLog
t_backtest\EdgeLogNOISE_<stamp>.csv` on `State.Terminated` with the
instrument, bars period, session template and every parameter in the header, and
`tools/reconcile_nt_dump.py` asserts on that header. Two timestamp offsets are handled
there: NT displays in the PC's zone (Arizona, no DST - so the shift to Eastern is 3h in
summer and 2h in winter, not a constant) and stamps bars at CLOSE while the engine stamps
at OPEN.

**NinjaTrader cannot be driven programmatically** - trading applications are restricted to
screenshots only, and that is not something the owner can grant away. Everything above is
built so the only manual steps are F5 and Run.

### Where NOISE stands after both reconciles

| | Engine | TradingView | NinjaTrader |
|---|---|---|---|
| Trades | 191 | 189 | 192 |
| Matched to engine | - | 159 | 184 |
| Exit bar identical | - | 157 | **184** |

Three independent engines, three implementations, no shared code. NOISE is verified.

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

## Chart layout + the fill-attribution constraint (2026-08-11)

**Use one chart per strategy — three charts, all NQ, one demo account:**

| Chart | Strategy | Why it needs its own |
|---|---|---|
| NQ 1-Minute RTH (≥30 days) | `EdgeLogENGUQ1m` | different timeframe — mandatory |
| NQ 5-Minute RTH (~20 days) | `EdgeLogORBV2` | needs Calculate=OnEachTick (watches intrabar volume) |
| NQ 5-Minute RTH (≥25 days) | `EdgeLogNOISE` | needs 14 prior sessions warm; keeps its trade marks separate |

ORB V2 and NOISE *could* technically share the 5-min chart (Calculate is per-strategy,
not per-chart) — separate is still better: clean trade marks, independent enable/disable,
and no confusion when debugging one leg.

**THE CONSTRAINT — fills carry no strategy name.** `C:\EdgeLog\fills.csv` columns are
`ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId` (written by
`tools/EdgeLogExport.cs`, header at its `Header` const). Three strategies on one account
+ one instrument produce fills that are **indistinguishable at the import layer**.
Separate charts do NOT fix this — it is account-level, not chart-level.

Two consequences and how we handle them:
1. **Attribution** — the daily reconcile must match fills to legs by **time + price**
   (which is exactly what `tools/reconcile.py` already does, with tz auto-offset and a
   tolerance window). Ambiguity only arises if two legs fire in the same second at the
   same price — rare, and detectable. *Cheap future upgrade:* add `ex.Order.Name` as a
   `Signal` column to `EdgeLogExport.cs` (each strategy already uses unique signal names:
   `EQ`/`EQx`, `V2`/`V2x`/`V2eod`, `NZ`/`NZexit`/`NZstop`) and teach `api/nt_sync.py` to
   read it. Touches the live import path that carries the owner's REAL trades — do it
   deliberately, not casually.
2. **Netted account P&L** — the broker account shows the NET of all three legs, so a long
   ENGU-Q and a short ORB V2 can read as flat. NinjaTrader tracks each strategy's own
   position independently, so the strategies themselves behave correctly; but **per-leg
   P&L must come from the reconcile / NT's per-strategy tracking, never from the account
   balance.**

## WHAT THE ENGU-Q L50 LEG STILL NEEDS (2026-08-18)

Run #249 was adopted by the owner ("lets go with the .50"). Layer by layer:

| Layer | What it is | State | What is missing |
|---|---|---|---|
| 1 · Shadow | `api/paper.py` runs the config against the masters nightly and logs signals. No orders, no money | **DONE** — leg `ENGUQ_L50` added, `tools/paper_smoke.py` PASS (13 trades, -$821 vs the #226 control's -$2,091 over the same window, entries one minute later, which is the limit filling) | Runner restart so the long-running process re-imports the module. **Deliberately deferred**: another session had a job running, and a restart orphans running jobs |
| 2 · NT demo | `EdgeLogENGUQ1m` places real demo orders on Sim101 | **CODE WRITTEN, NOT DEPLOYED.** `LimitAtr` param added (0 = old market-at-close behaviour, so the port stays backward compatible): rests a BUY limit `LimitAtr x ATR` below the signal close, derives the stop from the ACTUAL fill (closer to the engine than the market path, which anchors on the signal close), cancels after 10 unfilled bars, and skips management on the fill bar | Compile + deploy + an NT restart. NOT done on purpose: the owner is away, strategies are live, a headless build hot-reloads the bridge AddOn, and strategy types need a full NT restart anyway. **Owner call** |
| 3 · TradingView | Pine port for a visual cross-check | **NOT STARTED** | A Pine port of the ETH config *with* the limit entry. The existing ENGU-Q Pine is the RTH #149 port |
| 4 · Reconcile | Nightly engine-vs-broker parity | **BLOCKED, unchanged** | The 1-minute data hole (ETH masters end 2026-06-30, TradingView serves ~24 days) means engine and chart still do not overlap. Needs either the NT 1m capture to age in, or paid history |

The honest summary: **layer 1 is done and running, layer 2 is a deploy decision, layers 3 and 4 are blocked on things money or time fix, not on analysis.**

## Open items

1. Owner: enable the two strategies (above).
2. `reconcile.py --daily` once demo fills exist.
3. Decide the shadow ORB leg: still logs engine (look-ahead) numbers — either swap it to a
   V2-equivalent shadow (needs 10s-aware shadow path) or read its PAPER line as reference-only.
4. NQ masters end 2026-07-16 — refresh from the AddOn 10s feed (import path exists:
   `tools/import_nt_ohlc.py`); needed before any fresh engine-vs-chart comparison.
5. **RESOLVED 2026-08-11:** NOISE lockbox-spent contradiction settled — status is SPENT
   (read by full-window validates #202/#203 and the 2026-08-11 gate test), confirmatory-only
   from here; ES-transfer failure stands. `augur_strategies/NOISE_1_0.py` docstring and
   `BACKTESTING_STACK.md` are now consistent.
6. Blend baseline ($835k) flagged suspect until ORB is re-based on live-legal rules.

## Tooling index

`api/paper.py` (shadow engine + EOD hook) · `tools/paper_smoke.py` ·
`tools/orb_live_legal_variants.py` · `tools/orb_barclose_entry.py` ·
`tools/orb_session_trace.py` (bar-by-bar "when is what known") ·
`tools/orb_live_emulation_cost.py` · `tools/orb_volarm_10s.py` (10s intrabar reconcile) ·
`tools/enguq_trail_lag.py` · `tools/nt/EdgeLogORBV2.cs` · `tools/nt/EdgeLogENGUQ1m.cs` ·
`tools/nt/SIM101_SETUP.md` (account section superseded: use DEMO7240108)

# RESULTS ▸ GAUGE DASHBOARD — design spec (third report layout)

Owner brief (2026-07-21): make the first look at an auto-validate run read like a car
dashboard — every KPI a compact gauge with red/yellow/green zones, needle on the value,
percentage underneath; detail stays one tap away. This doc is the strategy the owner asked
for in point 7 (design first, then build), and the phone-readable pickup doc (point 6).

Status: **v63.8** — GAUGES β shipped (v62.4), audit fix (v62.5), owner-review round (v63.3–63.5:
enhancements/composites/equity-strip, then mercury-green fix + section reorder + Param
Performance rename + equity into §1), then **PILLS β (v63.8)** — a 4th layout. Toggle:
CLASSIC · FUNNEL β · GAUGES β · PILLS β.

**PILLS β (owner 2026-07-21):** same 5-section breakdown, but each 0-1 / $ metric is a
HORIZONTAL pill gauged to 100% (red/yellow/green zone bands + a value tick) instead of a
semicircle. Reuses the exact `_ggAll` defs / zones / hardcoded status colors as GAUGES β
(search `PILLS β` in index.html). Per owner, based on the CLASSIC view: the 1A-1D charts, the
1E matrix and the 1G/1H distributions are LEFT AS GRAPHS (rendered under Strategy Performance
via `_panelEquity` | `_panelMatrix`+`_panelRegime` | `_distTile`) — only the scalar KPIs
become pills. Performance / robustness pills are non-expandable (their detail is those §1
graphs); param / enhancement pills tap to expand their config / gate charts. No AT-A-GLANCE
composite in pills (kept classic-lean); easy to add if wanted.

**Owner review answers (2026-07-21) — now built:**
- **Verified it renders** on a real run (§7 item ticked).
- **Q1 → yes, a section:** ML-gate + ensemble now have their own **§5 ENHANCEMENTS** gauges
  (GATE EDGE / GATE % KEPT / ENSEMBLE LIFT). With the new AT-A-GLANCE section that makes 6
  sections total (glance + 4 categories + enhancements).
- **Q2 → yes:** a compact always-visible **CHAMPION EQUITY strip** sits at the very top.
- **Q5 → yes:** an **AT A GLANCE** section of composite 0–100 scores — one per category plus an
  OVERALL (each = mean of its gauges' green=1 / amber=0.5 / red status).
- **Q4 (win-rate breakeven band):** owner "idk where that is" → it's the WIN RATE gauge in §1;
  kept as-is (graded vs its own breakeven rate). Explained, no change.
- **Point 5 (no natural scale → raw number):** confirmed — every unbounded gauge (PF, recovery,
  $, counts) already shows the **raw number** as its readout; only the needle uses a scale, and
  none are faked into a percentage. This is now the documented rule (see §2).
- **#26 incremental reuse:** full hand-off spec written → `docs/INCREMENTAL_BACKTEST_REUSE.md`.

---

## 1. The four categories (owner point 1)

Every number an auto-validate run produces is sorted into the owner's four buckets:

Section order (owner, 2026-07-21): **Strategy Performance → Param Performance → Strategy
Robustness → Param Robustness → Enhancements** (param performance is 2nd, strategy robustness
3rd). "Param Influence" was renamed **Param Performance**. The 1A CHAMPION EQUITY chart leads
the Strategy Performance section. Gauge status colors are hardcoded (`#1d9e75`/`#f5c842`/
`#e24b4a` — the deploy-checklist tile colors) so they stay vivid on the desaturated themes
(Mercury/Mono/Obsidian) where `var(--green)` is a grey.

| # | Category | Question it answers | Header |
|---|----------|--------------------|--------|
| 1 | **Strategy performance** | does the champion config make money? | 🏁 STRATEGY PERFORMANCE |
| 2 | **Strategy robustness** | does the edge survive out-of-sample / luck checks? | 🛡 STRATEGY ROBUSTNESS |
| 3 | **Param performance (influence)** | which knobs actually drive the edge? | 🎛 PARAM INFLUENCE |
| 4 | **Param robustness** | is the winning config a plateau or a lucky spike? | ⛰ PARAM ROBUSTNESS |

Things that did NOT fit cleanly (owner asked to be told — the "etc" bucket):

- **ML-gate / ensemble enhancement results** — they are not the strategy's own performance
  (a bolt-on filter), and not robustness either. FUNNEL already calls this "Enhancements".
  Current call: keep them OUT of the gauge wall; they stay reachable as the expandable
  enhancement panels below it. Owner to confirm (§8 Q1).
- **Run metadata** (dates, master, cost model, trial count) — not a KPI; stays in the header.
- **Equity curve, parallel coords, KPI matrix, heatmaps, 3-D explorer, MAE/MFE, per-window
  tables** — charts, not gauges (owner point 2: unaffected). They are the DETAIL layer the
  gauges expand into.

## 2. Gauge anatomy (owner points 2, 3)

Prototype validated 2026-07-21 (semicircle math + zones + needle screenshot-checked):

- 180° semicircular arc, muted **zone bands** (red / yellow / green at ~30% tint) with dark
  **boundary ticks** — the small lines the owner described, marking where bad / concerning /
  acceptable start.
- **Needle** from the hub pointing at the value, colored by the zone it sits in (gauge
  status color), hub dot, thin (2.5px) — car-gauge look, iOS-glass friendly.
- **Value underneath** in the status color: percentages for everything that is naturally
  0–1 or 0–100 (owner point 2: 0–1 items become simple %), native units for $ / ratios /
  counts (a "62%" profit factor would lie — PF shows `1.62`, drawdown shows `$8.4k`).
  **Rule (owner, point 5): if a metric has no natural 0–1 scale, the readout is the RAW
  NUMBER, never a faked percentage.** The needle still uses an internal scale for position,
  but the number shown is always the real value (PF `1.62`, net `$41k`, trades `978`,
  recovery `4.9×`). Only genuinely bounded metrics (DSR, WFE, PBO, win rate, neighborhood…)
  render as `%`.
  One-line gray subnote under the value for context (e.g. `OOS/IS retention`, `BE 41%`).
- Label (uppercase, tiny) at the bottom; whole card is tappable → expands the detail panel.
- Colors are the app's theme tokens (`var(--green/--yellow/--red)`), NOT hardcoded hex, so
  all 10 themes recolor the gauges (fixes a gap the old heroGauge has).

**Three gauge types** (owner point 4 — zones computed per metric type):

| Type | Meaning | Example |
|------|---------|---------|
| `hb` higher-is-better | red → yellow → green | DSR, walk-forward eff, neighborhood % |
| `lb` lower-is-better | green → yellow → red | PBO, max drawdown vs net, MC P95 DD |
| `band` sweet-spot | red → yellow → green → yellow → red | win rate vs breakeven margin |

Position on the arc is a per-metric normalization (each gauge def declares its own scale +
zone edges); the DISPLAYED number is always the real metric. Zone edges reuse thresholds
already shipped elsewhere in the app (DSR 80/95, run-score 45/70, gate pass lines) so a
metric is never green in one view and yellow in another.

## 3. Per-metric gauge definitions

The single source of truth is the `_ggAll` defs array in `index.html` (search
`GAUGES β build`). The shipped v62.4 set (D = run doc, V = D.validate):

| Gauge | Cat | Source | Scale (arc) | Red / Yellow / Green | Shows |
|---|---|---|---|---|---|
| NET P&L | 1 | best config net (best_pnl_usd) | recovery (net÷maxDD) 0–6× | <1× / 1–3× / >3× (net ≤ 0 pins red) | $ + recovery subnote |
| PROFIT FACTOR | 1 | best_pf | 0–3 clamp | <1.15 / 1.15–1.4 / ≥1.4 | ratio |
| WIN RATE | 1 | wr vs breakeven wr (V total avg win/loss) | margin −15…+25 pts | below BE / BE to +8 / > +8 pts | % + BE subnote |
| EXPECTANCY | 1 | net ÷ trades vs round-trip cost | 0–4× cost | <1× / 1–2× / >2× cost | $/tr (absolute scale if no cost saved) |
| MAX DRAWDOWN | 1 | |best_dd| ÷ net | 0–120% of net | >70 / 35–70 / <35% | $ |
| TRADES | 1 | best_trades | 0–400 | <100 / 100–300 / >300 | count |
| VALIDATION GATES | 2 | V.n_pass / V.n_gates | 0–100% | <60 / 60–99 / 100% | n/n + verdict |
| DEFLATED SHARPE | 2 | V.dsr (or D.dsr.dsr) | 0–100% | <80 / 80–95 / ≥95% | % (same zones as the 1I card) |
| WALK-FWD EFF | 2 | V.wfe | 0–120% | <30 / 30–50 / ≥50% | % |
| WF FOLDS HELD | 2 | folds with OOS PF>1 (top10_results) | 0–100% | <50 / 50–75 / ≥75% | n/n |
| LOCKBOX | 2 | V.lockbox.pass + pnl | binary | fail / — / held | HELD/FAIL + reserved-slice $ |
| MC P95 DD | 2 | V.mc_p95 (or D.mc.p95) vs |best_dd| | ratio 0–3× | >2× / 1.4–2× / ≤1.4× | $ + ratio subnote |
| REGIME SPREAD | 2 | profitable regime buckets (vol/trend/dow/tod) | 0–100% | <40 / 40–70 / ≥70% | % + n/n |
| SIGNAL KNOBS | 3 | knob_screen entries beating the noise probe | 0–100% | <25 / 25–50 / ≥50% | n/n |
| TOP KNOB | 3 | strongest PPS in D.relationship | 0–1 | <0.15 / 0.15–0.35 / ≥0.35 | score + knob name |
| SURROGATE FIT | 3 | best bake-off model CV R² | 0–1 | <0.3 / 0.3–0.6 / ≥0.6 | % + model name |
| NEIGHBORHOOD | 4 | neighborhood.good / tot | 0–100% | <50 / 50–75 / ≥75% | n/n |
| PLATEAU PICK | 4 | plateau_pick.same_as_best (+ boundary flags) | categorical | differs-at-range-edge / differs / agrees | AGREE / DIFFERS |
| PBO | 4 | (V.)pbo.pbo | 0–100% | ≥50 / 30–50 / <30% (matches §2 verdict) | % |
| TRADES / KNOB | 4 | V.trades_per_param (or trades ÷ tuned knobs) | 0–60 | <10 / 10–30 / ≥30 | per-knob count |
| PARAM STABILITY | 4 | V.param_stability (engine field, not yet emitted) | 0–100% | <40 / 40–70 / ≥70% | % — **N/A until engine saves it** |
| GATE EDGE | 5 | ml_gate gated−ungated PF (or gate_validate earns-pre) | lift −0.2…+0.4 | worse / flat / better | ±PF or HELPS/NO |
| GATE % KEPT | 5 | ml_gate n_kept / n_total | 0–100%, sweet-spot band | ~100% or <30% yellow, mid green | % |
| ENSEMBLE LIFT | 5 | ensemble.improved + recovery_gain | improved? | no / — / improved | ±rec or IMPROVED/NO |

**AT A GLANCE composites (§ top):** OVERALL + one per category = mean of that category's
gauges scored green=1 / amber=0.5 / red=0.08, shown 0–100 (zones <45 / 45–70 / ≥70). Summary
only, not tappable; N/A when a category has no gauge with data.

Exact field fallbacks live in the code next to each def; a gauge with no data renders as a
dim `—` card (never a fake green), consistent with the n/a-tile convention the report already
uses — so grid/auto runs show their applicable gauges and N/A the validate-only ones without
moving the layout.

## 4. Layout & interaction (owner points 5, 7)

- **Third toggle**, not a separate tab: REPORT LAYOUT · CLASSIC | FUNNEL β | **GAUGES β**
  (`APREF.repLayout==='gauges'`, persisted like the others — owner said "your call": a
  third toggle keeps all three layouts one tap apart on the same run).
- Four category sections; each header carries a status roll-up (● counts of red/yellow/
  green in that section) so the wall reads top-down in one glance.
- **Tap a gauge → the matching full panel** (the SAME panels CLASSIC/FUNNEL render: equity,
  DSR card, neighborhood table, knob importance, plateau strip…) unfolds under that
  section, exactly like the FUNNEL trust-chip expander. Tap again to close. Nothing was
  deleted or recomputed — GAUGES β is a re-skin of the same data (flip back any time).
- Shipped fully gauge-first (owner point 5 taken literally): NO chart is visible until a
  gauge is tapped — the equity curve lives behind NET P&L / MAX DD / LOCKBOX / WF taps.
  (Owner Q2: bring back an always-visible compact equity strip on top?)

## 5. What is deliberately NOT a gauge

Equity / parallel coords / KPI matrix / heatmaps / distribution charts / candidate tables /
MAE-MFE / 2L overlays — the detail layer (owner point 2). The AI/steering summaries and
run-code block keep their current homes at the bottom of the report.

## 6. Misc backlog item logged (owner point 8)

**Incremental backtest reuse** — reuse matching prior computation when only the window or a
small part of the config changed, instead of full engine reruns. Filed as **ROADMAP §3
#26** with a concrete design sketch (trial-level result memoization keyed by
strategy-file hash + params + master id + window + costs; safe exact-hit reuse first,
window-extension deltas later). Bigger scope, separate build — nothing in the gauge work
depends on it.

## 7. Build checklist

- [x] Strategy doc (this file) — categories, zones, anatomy agreed with prototype
- [x] v62.4: gauge component + defs + GAUGES β toggle + 4 sections + tap-to-expand
      panels + header status roll-ups (screenshot-verified on a mock auto-validate doc)
- [x] Owner confirmed it renders on a real run (2026-07-21)
- [x] v63.3: §5 ENHANCEMENTS gauges (Q1), top CHAMPION EQUITY strip (Q2), AT A GLANCE
      composites (Q5), PARAM STABILITY N/A placeholder gauge, raw-number rule (point 5)
- [x] Grid/auto coverage — handled by the N/A-card design (owner point 7): applicable
      gauges render, validate-only ones show N/A, layout never moves
- [ ] Zone-edge tuning pass with the owner after a week of real use (§8 Q3) — still open
- [ ] PARAM STABILITY: wire real data once the engine emits `V.param_stability`
      (IS→OOS re-opt drift) — gauge slot already in place, shows N/A until then
- [ ] Composite-vs-per-header roll-up: shipped composites as a top AT-A-GLANCE section;
      owner Q5 also mused "maybe composite as well" — confirm this placement is what they meant

## 8. 📱 Owner pickup — answer whenever, not at PC

1. **Enhancements (ML gate / ensemble)**: keep off the gauge wall (current), or give them
   a 5th section of gauges (e.g. GATE EDGE $ / KEPT %)?
2. **Equity curve on the gauge view**: shipped pure-gauges (equity is behind the NET P&L
   tap). Want an always-visible compact equity strip back on top?
3. **Zone edges to sanity-check when results flow**: PF 1.15/1.4 · DD 35/70% of net ·
   trades 100/300 · WF eff 30/50 · neighborhood 50/75 · PBO 30/50 · recovery 1×/3× ·
   MC 1.4×/2×. Say the word and any edge moves (one-line changes in the defs array).
4. **WIN RATE as breakeven-margin band** (green = comfortably above the WR the avg
   win/loss requires, red = below it, extreme-high also flagged): keep, or plain
   higher-is-better?
5. **Roll-up dots in section headers** (● 4 green · 1 yellow · 1 red): enough, or do you
   want one composite 0–100 gauge per section too?

# TV SWEEP — challenger round 13 (TradingView top-boosts strategies)

**Owner directive (2026-07-17):** pull the most-boosted community strategies from TradingView
(the in-chart "Community scripts → Strategies" table, sorted by boosts), port them from Pine
Script to house Python plugins, and test/refine them one at a time — as thorough as the prior
challenger rounds — across **ES + NQ, 1m + 5m** (the deep-history masters). Anything promising
gets the full champion treatment so it can be compared apples-to-apples with **ORB 3.1** and
**ENGU-Q**.

*Plain language:* a **boost** is TradingView's upvote. **Pine Script** is TradingView's
charting language — these ports re-express each script's rules in the house engine
(`augur_strategies/*.py`), which is NOT a Pine runner. **Triage** = the cheap first screen on
2010→2025-06 data; the final year stays in the **lockbox** (sealed holdout, looked at once,
only on owner sign-off).

**Context going in (honest prior):** rounds 1–12 tested 24+ concept families / ~2,000 configs
— zero beat the champions; round 11 confirmed the same result is now published independently
(arXiv falsification series on MNQ). Most TV top scripts are 2015–2020-era indicator systems,
and several overlap families already dead in this library (REVERT, VWAP FADE, SUPERTREND).
This sweep tests the *published rule-sets as shipped* — the one thing prior rounds never did
verbatim — so the negative, if it comes, is definitive for this source too.

---

## 1. Pre-registration (fixed BEFORE any results were computed)

- **Window:** triage = 2010-06-07 → 2025-06-30, loaded with a hard cutoff (`date_to`), so
  lockbox bars (2025-06-30 → 2026-06-30) are never in memory during triage. Lockbox = one
  look per family, only on owner sign-off, same accounting as SWING/TTIBS.
- **Data:** `NOADJ_{NQ,ES}_{1m,5m}_RTH` masters. NQ 5m = the deciding dataset; the other three
  are breadth/transfer reads. (RTH = the 09:30–16:00 ET session.)
- **Costs:** 0.533 pts/round-trip on NQ, 0.363 on ES ($5.66 commission + 0.25-pt slippage at
  $20/$50 per point) — identical to every prior round.
- **Fills (TV-parity + house honesty):** signals evaluate on a bar's CLOSE; resulting market
  orders fill at the NEXT bar's OPEN. Pine stop-entry orders are honored as real stops: if
  already marketable → next open; if not → they fill AT the stop level only if the next bar
  trades through it, else they expire per the script's own cancel logic. No same-bar close
  fills anywhere (that mode inflated TTIBS ~21% and is banned from deploy decisions).
- **Multi-day holds** are allowed where the script holds overnight (most do) — but positions
  are FORCED FLAT at the close of the day before each detected quarterly roll seam, and no
  new fills that day (the ~77-pt NOADJ seam must never be "traded"). Unresolved end-of-data
  trades are dropped, never truncated.
- **Sizing:** 1 contract, fixed.
- **Protocol per strategy:** (1) run the PUBLISHED defaults verbatim (the "as-shipped" test);
  (2) a small bounded grid over the author's own knobs only (documented in the strategy's
  section before running); (3) gates below decide survive/dead. No invented indicators, no
  new knobs — that would be round 1–12 again, not a test of the published strategy.
- **Triage gates (NQ 5m, all must pass):**
  - **G-econ:** PF ≥ 1.25 AND MAR ≥ 8 (MAR = net ÷ max drawdown; the champions sit at 38.6
    (ORB) and ~7.2 net-DD (ENGU-Q) — below 8 a challenger can't matter at the book level).
  - **G1 sample:** n ≥ 300 trades.
  - **G3 regime:** post-2021 share of net ≤ 50% (kills the post-COVID-vol artifacts that
    took down DRIVE/NOISE/MIDDAY).
  - **G4 fill-artifact floor:** average loser ≥ 8 NQ pts (a 0.25-pt slippage model cannot
    support tighter; this closed 1m-ORB).
  - **G5 not-a-disguise:** |daily-PnL correlation| vs ORB #125 < 0.40; correlation vs the
    ENGU-Q deploy repro reported alongside (directional only — the ENGU-Q file repro defect
    from 2026-07-14 is still open).
  - **G6 concentration:** best single year ≤ 40% of net.
- **Survivors:** frozen walk-forward (6 folds, ≥ 4/6 OOS-positive), ES transfer with no
  re-fit (PF ≥ 1.2), trade bootstrap P(net ≤ 0) ≤ 0.01, Deflated Sharpe vs the grid size —
  then owner sign-off before any lockbox spend.
- **Champion yardsticks on the triage window:** ORB 3.1 #125 = n 3,815 / +$306,331 / PF 1.607
  / maxDD −$9.4k; ENGU-Q deploy (full history) = +$474.7k / net-DD 7.23; 1:1 blend = $835k,
  17-for-17 years, −$60.1k DD.

## 2. The series (pulled 2026-07-17, boosts from the owner's in-chart table)

| # | Boosts | Script (author) | Rules in one line | Prior-art overlap | Port file | Status |
|---|---|---|---|---|---|---|
| 1 | 46.7K | Bollinger + RSI, Double Strategy (ChartArt) | RSI(16) crosses 45/55 AND close re-crosses the 2σ BB(20) band → stop-and-reverse, no stops/exits | REVERT family (FAIL) — different trigger, tested verbatim anyway | `BBRSI_1_0.py` | ❌ DEAD (0/54 gate-pass; as-shipped −$171k NQ) |
| 2 | 30.4K | MACD + SMA 200 Strategy (ChartArt) | SMA-based MACD histogram zero-cross + macd>0 + close[26] vs SMA200 side filter → stop-and-reverse | fresh (regime-filtered momentum) | `MACD200_1_0.py` | ❌ DEAD (0/16; as-shipped ≈ flat, MAR 0.27) |
| 3 | 24.4K | SuperTrend STRATEGY (KivancOzbilgic) | ATR(10)×3.0 on hl2, flip on trend change, always-in | SUPERTREND 1.0/2.0 in library, "not strongly validated" → family verdict now measured | `SUPERTREND_3_0.py` (verbatim) | ❌ DEAD (0/24; best long-only MAR 4.8) |
| 4 | 17.6K | MACD Bull Crossover + RSI Oversold 5-ago, Long (Trebor_Namor) | long when MACD crosses signal AND RSI was <30 within 5 bars; exit on bear cross w/ hist>0 + RSI>70 5-ago; optional SL/TP | fresh (source protected on TV; author's own Python port on GitHub used) | `MACDRSI_1_0.py` | ❌ DEAD (0/16; MAR 1.36, 147-pt avg losers, edge pre-2021 only) |
| 5 | 16.6K | PMax Explorer STRATEGY & SCREENER (KivancOzbilgic) | "Profit Maximizer": MA (8 types) vs ATR trailing line, flip on cross | SuperTrend-on-MA family | `PMAX_1_0.py` | ❌ DEAD (0/24; best long-only MAR 6.3) |
| 6 | 14.2K | Hull Suite Strategy (DashTrader) | HMA(55) slope vs 2 bars ago; long-only default (long/flat), "all" = flip | fresh (HMA trend) | `HULL_1_0.py` | ❌ DEAD (0/24; best MAR 2.9) |
| 7 | 13.5K | Buy&Sell AO+Stoch+RSI+ATR (SerdarYILMAZ) | RSI+Stoch oversold + AO turns positive → long w/ ATR SL/TP (author labels it educational) | fresh (oscillator confluence) | `AOSTOCH_1_0.py` | ❌ DEAD (0/24; negative on ALL 4 datasets as shipped) |
| 8 | 10.9K | Golden Cross SMA 50/200, Long Only (ChartArt) | SMA50 crosses SMA200 → long; cross under → flat | fresh, but a daily-scale signal — expected G1 fail on intraday bars (few crosses) | `GOLDX_1_0.py` | ❌ DEAD (0/8; long = MAR 2.5 drift; daily-scale n=44) |
| 9 | 10.8K | Flawless Victory 15m BTC "ML" (Trebor_Namor) | BB(20,1σ) + RSI bounds long strategy, 2 param versions + optional SL/TP; hyper-fit to 1yr of BTC | BBRSI cousin (1σ band) | `FLAWLESS_1_0.py` | ❌ DEAD (0/16; v1 MAR 1.7, best cell 2.7) |
| 10 | 10.7K | BUY and SELL single EMA cross (Che_Trader) | EMA(10)/EMA(20) cross, always-in flip | the plainest momentum baseline | `EMAX_1_0.py` | ❌ DEAD (0/32; as-shipped −$98k NQ 5m, −$761k NQ 1m) |
| 11 | 10.3K | Ichimoku + Daily-Candle_X + HULL-MA_X + MacD (SeaSide420) | 4-indicator confluence flip (Ichimoku cloud + daily-candle cross + HMA cross + HMA-MACD) | fresh (confluence) | `ICHIHULL_1_0.py` | ❌ DEAD (0/18; honest port kills the repaint edge) |
| 12 | 9.8K | RSI Divergence Indicator strategy (eemani123) | RSI(9) bull/hidden-bull divergence → long (pyramiding 2); exit RSI>80 or bear div; optional trail | fresh (divergence) | `RSIDIV_1_0.py` | ❌ DEAD (0/16; MAR ≤ 3.3, −$158k DD as shipped) |
| — | 14.4K | 3Commas Bot (Bjorgum) | — | SKIPPED: bot-integration template, not a strategy (no rule-set to test) | — | n/a |
| — | 12.1K | Ultimate Strategy Template (Daveatt) | — | SKIPPED: strategy TEMPLATE (framework for other people's signals), no edge claim | — | n/a |

Sources: Pine pulled verbatim via each script page (open-source publications; #4 via the
author's GitHub after TV shows it protected). Local copies in the session scratchpad
(`tv_sweep/*.pine`); the ports below are the durable artifacts. Original licenses (MPL 2.0
unless stated) and TradingView House Rules respected — ports carry attribution headers.

---

## 3. Per-strategy record

### 13.1 BBRSI 1.0 — Bollinger + RSI Double (TV #1, 46.7K boosts)

- **Published rules (v1.0, Jan-2016, Pine v2):** RSI(16) with bands 45/55; BB(20, 2.0σ).
  LONG when RSI crosses ABOVE 45 and close crosses ABOVE the lower band on the same bar —
  entry via a buy-stop at the lower band. SHORT mirror at 55/upper band. No stop-loss, no
  target, no session logic: the opposite signal is the only exit (stop-and-reverse).
  Author's own caveats: "no money management"; later published a long-only v1.2.
- **Port notes:** Pine v2 `rsi()`/`sma()`/`stdev()` (Wilder RSI; population stdev) matched;
  stop-entry + next-bar cancel semantics implemented as real stop orders (see prereg);
  1-contract net position; roll-seam force-flat.
- **Grid (pre-registered):** published cell first; then author-knob grid
  `rsi_len {8,16,24} × rsi_band {40,45,50} × bb_mult {1.5,2.0,2.5} × direction {both,long}`
  (+ `entry_mode next_open` robustness read on the champion cell). Nothing else.
- **Results (2026-07-17): ❌ DEAD — 0 of 54 grid cells pass the pre-registered gates.**
  - Anchors first: ORB #125 reproduced EXACTLY on the triage window (n=3,815 /
    $306,331 / PF 1.607) so the correlation gate is certified; the ENGU-Q repro defect
    is still open (repro n=3,394 / $184.6k vs documented 2,048 / $474.7k) — its corr
    numbers stay directional-only, as flagged.
  - **As shipped (the 46.7K-boost config, both directions):** NQ 5m n=1,105, PF 0.878,
    **net −$171,358**, maxDD −$239,689. NQ 1m ≈ flat (+$22k / PF 1.01); ES 5m the only
    positive read (+$92.9k / PF 1.11 / MAR 1.17); ES 1m −$114.8k. Losses widen with
    time (NQ 5m: 2022 −$50.4k, 2024 −$57.9k, 2025H1 −$38.9k) — the strategy has aged
    badly; boosts ≠ edge, measured exactly.
  - **Best refined cell** (author knobs, long-only, RSI 16 / band 50 / BB 20×1.5σ):
    n=550, PF 1.556, net $327.5k, maxDD −$48.0k, **MAR 6.83** — passes every gate
    EXCEPT the MAR ≥ 8 economics bar. Runner-up (RSI 8 / band 50 / 2.0σ): MAR 7.42
    but n=184 (fails sample floor too). corr vs ORB ≈ −0.03…−0.06 (genuinely
    uncorrelated), corr vs ENGU-Q repro ≈ +0.06 (directional).
  - **Reading:** every surviving corner is LONG-ONLY — the short half of TradingView's
    most-boosted strategy is a straight money-loser on index futures. The long-only
    corner is yet another instance of the round-9 meta-finding (long-only buy-weakness
    is the only daily-scale structure that ever survives here), in the same MAR class
    as CALENDAR (2.2) → DRIVE (8.8) → TTIBS (12.3), and TTIBS — the best of that class
    — already spent its lockbox and FAILED. Per prereg: no gate-passing cell → family
    dead at triage; **lockbox NOT spent**, no WF run.
  - Artifacts: `scratchpad r13/r13_BBRSI_1_0_results.json` (54-cell grid + gate scan),
    `r13_triage.py` (driver, ORB-anchor-verified).

### 13.2 MACD200 1.0 — MACD + SMA 200 (TV #2, 30.4K boosts) — ❌ DEAD

- **Port notes:** the script's "MACD" is built from SIMPLE MAs (sma), not EMAs — ported
  verbatim, plus its `close[26] > SMA200` side-filter quirk and persistent stop-entry
  orders with the slowMA-vs-SMA200 cancel rule. Its 50%-equity intraday-loss halt is
  meaningless at fixed 1-contract scale — omitted, documented.
- **Results (2026-07-17): 0 of 16 grid cells pass.** As shipped (both directions):
  NQ 5m n=776, PF 1.026, +$30.9k over 15 yrs with −$115k maxDD (MAR 0.27) — noise.
  NQ 1m the best raw read (+$172k, PF 1.07, MAR 1.98) but 84.9% of net is post-2021.
  ES 5m literally $23 net. Best refined cell (long-only, SMA100): MAR 3.84, PF 1.37 —
  less than half the economics bar, and its own year-shape is 58.6% post-2021.
- **Reading:** the SMA-MACD flip trades ~40-130 pts of churn per round trip and has no
  timing edge beyond the index's upward drift; the long-only cut just rides drift with
  deep give-backs. Nothing here threatens any champion. Lockbox untouched.
- Artifacts: `r13_MACD200_1_0_results.json`.

### 13.10 EMAX 1.0 — single EMA cross (TV #10, 10.7K boosts) — ❌ DEAD

- **Results (2026-07-17): 0 of 32 valid grid cells pass.** As shipped (EMA 10/20 flip,
  both directions): NQ 5m n=12,399, PF 0.977, **−$97.8k**; NQ 1m n=64,301, **−$760.8k**
  (a fee-and-churn shredder — exactly what a 10/20 EMA cross on 1-minute bars should
  do at real costs). ES both timeframes negative as well.
- Best refined cell (EMA 20/100 long-only): MAR 7.82 / PF 1.27 / n=1,810 — under the
  MAR ≥ 8 bar, and structurally the same drift-riding long-only cut as BBRSI/MACD200's
  best corners (corr vs ORB 0.01 — unrelated to ORB, but also unrelated to any edge
  beyond long index drift).
- **Reading:** the plainest momentum baseline confirms the sweep's calibration: naive
  always-in crosses lose after honest costs; long-only versions converge to ~MAR 6-8
  drift capture. Lockbox untouched.
- Artifacts: `r13_EMAX_1_0_results.json`.

### 13.6 HULL 1.0 — Hull Suite Strategy (TV #6, 14.2K boosts) — ❌ DEAD

- **Port notes:** HMA/EHMA/THMA implemented exactly (WMA kernel verified against the
  textbook value in the smoke test); long-only default per the script's own
  `strategy.risk.allow_entry_in`; "all" = always-in flip. Internal-consistency check
  passed: flip-mode trade count = 2× long-only + 1, the exact structural relationship.
- **Results (2026-07-17): 0 of 24 grid cells pass.** As shipped (HMA 55 long-only):
  NQ 5m n=6,975, PF 1.043, +$100k over 15 yrs vs −$93k maxDD → MAR 1.08. On 1m the
  slope flips churn it to death (NQ −$258k, ES −$594k). Best refined cell (EHMA,
  length 89, long-only): MAR 2.89 / PF 1.11. Always-in "all" mode never beats its
  own long-only cut.
- **Reading:** a 55-bar MA slope on intraday bars flips far too often for a ~26-pt
  average loser to survive 0.533-pt costs; at length 180 it's just slow drift capture.
  The "Hull Suite" popularity is a chart-aesthetics phenomenon, not an edge. Lockbox
  untouched.
- Artifacts: `r13_HULL_1_0_results.json`.

### 13.8 GOLDX 1.0 — Golden Cross SMA 50/200 long (TV #8, 10.9K boosts) — ❌ DEAD

- **Results (2026-07-17): 0 of 8 valid grid cells pass.** As shipped on 5m bars
  (50/200-bar SMAs, long/flat): NQ n=861, PF 1.249, +$204.7k / −$83.5k maxDD →
  MAR 2.45; ES similar shape (MAR 2.6). Upscaled toward the daily-chart meaning of
  "Golden Cross" (975/3900 bars ≈ 50/200 days) the quality rises (PF 2.48) but the
  sample collapses to n=44 with 68.7% of net post-2021 — unusable, exactly the
  pre-registered expectation. Every both-direction variant is worse (short leg loses
  outright; 200/800-both is net-negative).
- **Reading:** the famous cross is long index drift with a slow filter — real as a
  fact about equities, useless as a futures leg at champion scale. Lockbox untouched.
- Artifacts: `r13_GOLDX_1_0_results.json`.

### 13.3 SUPERTREND 3.0 — SuperTrend STRATEGY verbatim (TV #3, 24.4K boosts) — ❌ DEAD

- **Port notes:** new file rather than reusing `SUPERTREND_1_0/2_0.py` — those are older
  loose adaptations (SMA-ATR, mult 3.5, EMA filter, non-house fills). 3.0 is the
  Kivanc script exactly: hl2 source, Wilder-RMA ATR(10)×3.0, ratcheted-band flip,
  always-in. Port cross-validated by an independent second implementation
  (0 mismatches over 28k bars) and a buy/sell signal-symmetry check.
- **Results (2026-07-17): 0 of 24 grid cells pass.** As shipped (both directions):
  NQ 5m n=7,404, PF 1.039, +$140k / −$76k maxDD → MAR 1.85; ES 5m **negative**
  (−$76k); both 1m feeds are churn shredders (NQ −$423k, ES −$721k). Best refined
  cell (ATR 20 × 3.0, long-only): MAR 4.84 / PF 1.15 — drift capture again.
- **Reading:** this measured verdict also SETTLES the library's old "SUPERTREND 1.0/2.0
  not strongly validated" line — the family's published form has no honest edge on
  ES/NQ intraday bars at real costs; its TV popularity rests on cosmetic trend
  painting and zero-cost backtests. Lockbox untouched.
- Artifacts: `r13_SUPERTREND_3_0_results.json`.

### 13.4 MACDRSI 1.0 — MACD cross + RSI-oversold-recently long (TV #4, 17.6K boosts) — ❌ DEAD

- **Port notes:** TV source is protected ("Closed by the author"); port built from the
  author's published rule description + their own GitHub Python (`macd_rsi.py`). The
  port agent proved the exit's "histogram above 0" clause is mathematically inert
  (0 of 2,224 crossunder bars excluded — the crossunder itself forces it), which is
  presumably why the author's own later Python dropped it. Defaults follow the TV
  artifact (lookback 5); the GitHub lookback 10 is a grid cell.
- **Results (2026-07-17): 0 of 16 grid cells pass.** As shipped (long-only): NQ 5m
  n=749, WR 67.2%, PF 1.198, +$143.7k vs **−$105.8k maxDD** → MAR 1.36. The 67% win
  rate is bought with stop-less dip-holding: average loser 147 pts (~$2,900). Both 1m
  feeds negative. Unusual failure shape for this sweep: the money is PRE-2021 (post-21
  share only 10.1%) — the dip-buy-without-stop trick worked in the QE decade and
  stopped. Best cell (rsi_os 35, long): MAR 1.91.
- **Reading:** a 71%-WR smoke on 3 cherry years dissolved over 15 — the exact
  overfit-to-era failure the round screens for. SL/TP overlays only shrink both sides.
  Lockbox untouched.
- Artifacts: `r13_MACDRSI_1_0_results.json`.

### 13.5 PMAX 1.0 — Profit Maximizer (TV #5, 16.6K boosts) — ❌ DEAD

- **Port notes:** all 8 published MA types implemented (incl. Kivanc's VAR/VIDYA with
  its hardcoded 9-bar CMO window — a source quirk kept verbatim); PMax recursion
  cross-checked bit-identical against an independent SuperTrend-on-hl2 reference at
  the degenerate MA=SMA(1) setting. Screener half of the script is display-only —
  omitted.
- **Results (2026-07-17): 0 of 24 grid cells pass.** As shipped (EMA 10, ATR 10×3.0,
  both): NQ 5m n=3,453, PF 1.072, +$175k / −$93k → MAR 1.88; ES 5m and both 1m feeds
  negative. Best refined (SMA 20 / mult 2.0 / long-only): MAR 6.29 / PF 1.22 — the
  same long-only drift shelf as every other trend flip in this sweep (corr vs ORB
  ≈ 0). VAR/EMA/SMA differences are cosmetic at 15-year scale.
- **Reading:** smoothing the price before the ATR trail (PMax's whole pitch vs
  SuperTrend) changes nothing that costs care about. Lockbox untouched.
- Artifacts: `r13_PMAX_1_0_results.json`.

### 13.9 FLAWLESS 1.0 — Flawless Victory (TV #9, 10.8K boosts) — ❌ DEAD

- **Port notes:** v1/v2/v3 all ported (v3's MFI na-guard is dead code in the source —
  ported as the literal bug, documented); v2/v3 percent brackets verified to fill at
  exactly −6.604%/+2.328% etc. with correct gap-through handling.
- **Results (2026-07-17): 0 of 16 grid cells pass.** As shipped (v1 long): NQ 5m
  n=2,152, WR 72.3%, PF 1.134, +$190k / −$110k → MAR 1.73; NQ 1m the sweep's best 1m
  read (+$225k, MAR 2.70) — still nowhere near any bar. High win rate, no stop, avg
  loser 118 pts: the same buy-the-dip-and-hold shape as MACDRSI. Best cell (v1,
  guard 50): MAR 2.71. The author's "hyper-optimized with machine learning on 1 year
  of BTC" params transfer to index futures exactly as well as the prereg predicted.
- Artifacts: `r13_FLAWLESS_1_0_results.json`.

### 13.11 ICHIHULL 1.0 — Ichimoku + Daily-Candle + Hull + MACD (TV #11, 10.3K boosts) — ❌ DEAD

- **Port notes (two documented honesty deviations):** the Pine's daily-close
  "confidence" input uses `security('D', close)` which REPAINTS in Pine v2 (intraday
  it reads the day's FINAL close = look-ahead) — our port uses only completed prior
  sessions. Its `calc_on_every_tick` same-bar fills became next-open fills. Both
  deviations make our numbers honest where the TV backtest is inflated.
- **Results (2026-07-17): 0 of 18 grid cells pass.** As shipped (both directions):
  NQ 5m n=2,491, PF 1.046, +$62.6k / −$92k → MAR 0.68, and the post-2021 share is
  151% (pre-2021 subtotal NEGATIVE). ES and 1m all negative. Best refined cell
  (long-only, dt 0.0025): MAR 5.83 but 62.4% post-2021 → G3 fail.
- **Reading:** with the repaint removed and honest fills applied, the 4-indicator
  confluence is a coin-flip with fees. A clean demonstration of why TV strategy-report
  numbers from v2-era scripts with `security()` calls cannot be trusted at face value.
- Artifacts: `r13_ICHIHULL_1_0_results.json`.

### 13.7 AOSTOCH 1.0 — AO+Stoch+RSI+ATR Buy&Sell (TV #7, 13.5K boosts) — ❌ DEAD

- **Port notes:** the port agent independently replayed all 792 smoke trades against a
  from-scratch re-derivation — 791/792 exact, the 1 difference root-caused to the
  roll-seam force-flat working as designed. Bracket fills (ATR stop/limit, stop-first
  pessimism, gap-through at open) verified against real gap cases.
- **Results (2026-07-17): 0 of 24 grid cells pass — the sweep's most decisive kill.**
  As shipped (1×ATR symmetric bracket, both directions): NEGATIVE on all four
  datasets — NQ 5m −$157.7k (PF 0.80), NQ 1m −$225.8k, ES 5m −$104.5k, ES 1m −$265.8k.
  A ~51% win rate on a symmetric 1:1 bracket is a coin flip, and the 0.533-pt fee
  eats it. Best refined cell (1:2 bracket, long-only): net +$3,955 over 15 years
  (MAR 0.11). Nothing else is even positive.
- **Reading:** the author's own disclaimer ("just for training, don't trade this")
  is the only TV strategy description in this sweep whose backtest claim we could
  fully confirm. 13.5K boosts anyway. Lockbox untouched.
- Artifacts: `r13_AOSTOCH_1_0_results.json`.

### 13.12 RSIDIV 1.0 — RSI Divergence strategy (TV #12, 9.8K boosts) — ❌ DEAD

- **Port notes:** pivot-confirmed divergences (confirmation 3 bars after the pivot, no
  look-ahead), pyramiding-2 with shared exits, hidden-bull included; the source's
  `atrMultiplier` input is dead code (never referenced) — ported literally. Two trades
  hand-traced through their pivot pairs (osc higher-low vs price lower-low, textbook).
- **Results (2026-07-17): 0 of 16 grid cells pass.** As shipped: NQ 5m n=3,588,
  WR 67.4%, PF 1.148, +$294.8k — against a **−$158.4k maxDD** (MAR 1.86); ES 1m
  negative. Best cells are the 5%-trailing-stop variants: net $593k but −$178k DD
  (MAR 3.33) on n=360 — month-long drift rides wearing a divergence costume. The
  stop-less published mode is the familiar high-WR/huge-loser shape (avg loser 85 pts).
- **Reading:** divergence timing adds nothing once fills are honest; the money comes
  from holding long NQ for weeks. Lockbox untouched.
- **Pickup (2026-07-18) — Auto-Validate + DD-fix probe:** ran the app's Auto-Validate
  (free-optimize · NQ 5m RTH · cost 0.533 · 200 trials · 12-mo lockbox · ES-transfer),
  saved as **run #163**. **Verdict: FAIL (5/7 gates)** — ❌ sample (14.5 trades/param)
  and ❌ PBO (0.60, "likely overfit selection"); passes plateau, WFE 1.74, consistency
  6/8, DSR 0.89, ES-transfer (+$23k · PF 2.85). The PnL-ranked optimizer chased an
  overfit corner (rsi 10 · lb 5/10 · PERC 12.5% stop · pyramid 4); in-sample PF 4.98;
  lockbox reads huge (+$542k · PF 8.96) but on only **12 trades** — a mirage. Contrast
  ENGU-Q #149 deploy: lockbox PF 1.39 on 142 trades (believable).
- **DD-fix probe (frozen OOS):** the shipped no-stop mode is the DD cause; an **ATR
  trailing stop** is the real DD lever. In-sample it looks great (as-shipped MAR 1.86 →
  ATR×4 pyr2 MAR ~5.6; DD −$158k → −$84k), but on the sealed holdout (2025-07→2026-07)
  ATR×4 pyr2 = **−$25.5k** (PF 0.94) — it LOSES, vs as-shipped +$28.4k. Only gentler
  ATR×3 pyr2 (+$12.9k · DD −$47k) and ATR×4 pyr1 (+$8.7k · DD −$57k) stay marginally
  green. **Reading:** the ATR stop's drawdown control generalizes, the underlying edge
  does not — the in-sample DD "fix" is a curve-fit. RSIDIV stays ❌ DEAD (confirms §4).
- Artifacts: `r13_RSIDIV_1_0_results.json`; `rsidiv_validate_result.json`,
  `rsidiv_dd_grid.py`, `rsidiv_frozen_oos.py` (scratchpad); Auto-Validate **run #163**.

---

## 4. ROUND-13 VERDICT (2026-07-17) — the sweep is complete: 0 of 12 survive triage

**Every testable strategy on TradingView's all-time most-boosted list is dead on
ES/NQ intraday data under honest fills and real costs.** ~250 pre-registered grid
cells + 4 published-config datasets per strategy; not one cell passed the gate set;
no family earned a walk-forward, and **all 12 lockboxes remain sealed** (nothing to
spend them on).

### 4.1 Comparison table

*"As shipped" = the published defaults on the deciding dataset (NQ 5m RTH,
2010-06-07 → 2025-06-30, 1 contract, 0.533 pts/RT costs included). MAR = net ÷ max
drawdown. "Best corner" = the top author-knob grid cell — long-only in every single
case. Grid = gate-passing cells / cells run.*

| # | Strategy (boosts) | Concept | As shipped — NQ 5m, 15 yr | Best honest corner | Grid | Why it died |
|---|---|---|---|---|---|---|
| 1 | Bollinger+RSI Double (46.7K) | BB(20,2σ) + RSI(16) reversal, no stops | PF 0.88 · **−$171k** · MAR −0.7 | MAR 6.8 · PF 1.56 (RSI 16, band 50, 1.5σ, long) | 0/54 | short side torches it; long corner = buy-weakness drift, under the MAR-8 bar |
| 2 | MACD+SMA200 (30.4K) | SMA-MACD zero-cross + SMA200 side filter | PF 1.03 · +$31k · MAR 0.3 | MAR 3.8 · PF 1.37 (SMA100, long) | 0/16 | no timing edge; 40–130 pts of churn per flip |
| 3 | SuperTrend (24.4K) | ATR(10)×3 trailing flip, always-in | PF 1.04 · +$140k · MAR 1.9 | MAR 4.8 · PF 1.15 (ATR 20×3.0, long) | 0/24 | whipsaw at real costs; ES + both 1m feeds negative — settles the SUPERTREND 1.0/2.0 question |
| 4 | MACD cross + RSI-oversold (17.6K) | long when MACD crosses up & RSI<30 recently | PF 1.20 · +$144k · MAR 1.4 | MAR 1.9 · PF 1.23 (RSI-os 35, long) | 0/16 | 67% WR bought with 147-pt stop-less losers; edge existed pre-2021 only |
| 5 | PMax (16.6K) | SuperTrend applied to a moving average | PF 1.07 · +$175k · MAR 1.9 | MAR 6.3 · PF 1.22 (SMA 20, mult 2.0, long) | 0/24 | smoothing the input changes nothing that costs care about |
| 6 | Hull Suite (14.2K) | HMA(55) slope, long/flat | PF 1.04 · +$100k · MAR 1.1 | MAR 2.9 · PF 1.11 (EHMA 89, long) | 0/24 | 55-bar slope flips far too often for ~26-pt losers |
| 7 | AO+Stoch+RSI (13.5K) | oscillator confluence + 1×ATR bracket | PF 0.80 · **−$158k** · MAR −0.9 | MAR 0.1 (+$4k / 15 yr) | 0/24 | negative on ALL FOUR datasets; a coin-flip bracket minus fees. Author's own "educational only" disclaimer = accurate |
| 8 | Golden Cross (10.9K) | SMA 50/200 cross, long/flat | PF 1.25 · +$205k · MAR 2.5 | MAR 4.3 · PF 2.48 but n=44 (daily-scale 975/3900) | 0/8 | best as-shipped of the list — still pure drift; the true daily-chart version has no sample |
| 9 | Flawless Victory (10.8K) | BB(1σ)+RSI long, "ML-tuned" on 1 yr of BTC | PF 1.13 · +$190k · MAR 1.7 | MAR 2.7 · PF 1.24 (guard 50) | 0/16 | 72% WR / 118-pt losers; BTC-fitted params don't transfer |
| 10 | EMA 10/20 cross (10.7K) | plain EMA flip | PF 0.98 · **−$98k** · MAR −0.7 (NQ 1m: −$761k) | **MAR 7.8** · PF 1.27 (EMA 20/100, long) — the sweep's best corner | 0/32 | fee shredder as shipped; even the best corner of 12 strategies misses the bar |
| 11 | Ichimoku+Hull+MACD (10.3K) | 4-indicator confluence | PF 1.05 · +$63k · MAR 0.7 (pre-2021 subtotal NEGATIVE) | MAR 5.8 but 62% post-2021 → regime fail | 0/18 | its TV fame is a `security()` repaint (look-ahead); the honest port is a coin-flip |
| 12 | RSI Divergence (9.8K) | RSI pivot divergences, long, pyramid 2 | PF 1.15 · +$295k · MAR 1.9 (maxDD −$158k) | MAR 3.3 (5% trail, n=360) | 0/16 | divergence timing adds nothing; the money is weeks-long drift rides |

**Yardsticks, same window & costs:** ORB 3.1 #125 = PF 1.61 · +$306k · maxDD **−$9.4k**
(MAR ≈ 33 pre-lockbox, 38.6 full-history) · ENGU-Q deploy = $474.7k full-history,
net-DD 7.2 · 1:1 blend = $835k, −$60.1k DD, 17-for-17 years. The best TV corner (7.8)
doesn't reach the book's WEAKER leg; ORB alone beats every as-shipped config on net
dollars with 1/9th to 1/25th of the drawdown.

### 4.2 KPI matrix (house run-report format)

**Table A — AS SHIPPED** (published defaults · NQ 5m RTH · 2010-06-07→2025-06-30 ·
1 contract · 0.533 pts/RT included). `$/tr` = net ÷ trades. On negative-net rows,
`p21%` reads as "share of the LOSS that is post-2021".

| # | Strategy | Trades | Win% | PF | Net | Max DD | MAR | $/tr | AvgLoss (pts) | p21% | Read |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BBRSI (BB+RSI Double) | 1,105 | 47% | 0.88 | **−$171.4k** | −$239.7k | −0.71 | −$155 | 120 | 96 | loses as shipped |
| 2 | MACD200 | 776 | 41% | 1.03 | +$30.9k | −$115.3k | 0.27 | +$40 | 128 | 65 | flat noise |
| 3 | SUPERTREND 3.0 | 7,404 | 36% | 1.04 | +$140.5k | −$75.9k | 1.85 | +$19 | 38 | 60 | churny drift |
| 4 | MACDRSI | 749 | 67% | 1.20 | +$143.7k | −$105.8k | 1.36 | +$192 | 147 | 10 | no-stop dip-hold, pre-21 edge |
| 5 | PMAX | 3,453 | 36% | 1.07 | +$175.3k | −$93.2k | 1.88 | +$51 | 55 | 33 | drift |
| 6 | HULL | 6,975 | 36% | 1.04 | +$100.2k | −$92.6k | 1.08 | +$14 | 26 | 47 | flat churn |
| 7 | AOSTOCH | 4,047 | 51% | 0.80 | **−$157.7k** | −$176.2k | −0.89 | −$39 | 20 | 52 | worst — negative on all 4 datasets |
| 8 | GOLDX (Golden Cross) | 861 | 41% | 1.25 | +$204.7k | −$83.5k | **2.45** | +$238 | 81 | 41 | best as-shipped — still drift |
| 9 | FLAWLESS | 2,152 | 72% | 1.13 | +$189.6k | −$109.7k | 1.73 | +$88 | 119 | 26 | no-stop dip-hold |
| 10 | EMAX (EMA 10/20) | 12,399 | 28% | 0.98 | **−$97.8k** | −$133.6k | −0.73 | −$8 | 23 | 47 | fee shredder (1m: −$761k) |
| 11 | ICHIHULL | 2,491 | 26% | 1.05 | +$62.6k | −$92.1k | 0.68 | +$25 | 37 | 151 | pre-2021 subtotal NEGATIVE |
| 12 | RSIDIV | 3,588 | 67% | 1.15 | +$294.8k | −$158.4k | 1.86 | +$82 | 85 | 42 | biggest net, 2nd-worst DD |

**Table B — BEST REFINED VERSION OF EACH STRATEGY** — same 12 strategies, same row
numbers as Table A. For each one: the single best cell from ITS OWN author-knob grid
(ranked by MAR; **long-only won in all 12 cases**). `Fails` = which pre-registered
gates that best version still fails (economics bar = MAR ≥ 8).

| # | Strategy | Best settings found | Trades | Win% | PF | Net | Max DD | MAR | p21% | corr ORB | Fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BBRSI | RSI 8 / band 50 / 2.0σ, long | 184 | 64% | 2.55 | $346.9k | −$46.8k | 7.42 | 48 | −0.03 | MAR, n<300 *(n=550 sibling: MAR 6.83, fails MAR only)* |
| 2 | MACD200 | 12/26 + SMA100, long | 512 | 48% | 1.37 | $234.5k | −$61.0k | 3.84 | 59 | +0.02 | MAR, regime |
| 3 | SUPERTREND 3.0 | ATR 20 × 3.0 RMA, long | 3,773 | 39% | 1.15 | $274.5k | −$56.7k | 4.84 | 50 | −0.04 | MAR |
| 4 | MACDRSI | RSI-os 35, lookback 5, long | 1,041 | 68% | 1.23 | $214.3k | −$112.4k | 1.91 | 19 | −0.01 | MAR |
| 5 | PMAX | SMA 20 × mult 2.0, long | 1,836 | 42% | 1.22 | $261.8k | −$41.6k | 6.29 | 35 | −0.01 | MAR |
| 6 | HULL | EHMA 89, long | 4,553 | 32% | 1.12 | $206.2k | −$71.3k | 2.89 | 28 | −0.03 | MAR |
| 7 | AOSTOCH | 1:2 ATR bracket, long | 1,282 | 40% | 1.01 | $4.0k | −$36.7k | 0.11 | n/a | −0.08 | everything economic |
| 8 | GOLDX | SMA 975/3900 (≈daily 50/200), long | 44 | 57% | 2.48 | $177.5k | −$41.3k | 4.30 | 69 | +0.01 | MAR, n, regime |
| 9 | FLAWLESS | v1, RSI guard 50 (long by design) | 849 | 75% | 1.24 | $109.6k | −$40.5k | 2.71 | 46 | −0.02 | MAR |
| 10 | EMAX | EMA 20/100, long | 1,810 | 31% | 1.27 | $292.9k | −$37.4k | **7.82** | 41 | +0.01 | MAR — the sweep's closest miss |
| 11 | ICHIHULL | keh 14, dt 0.0025, long | 1,174 | 34% | 1.35 | $193.0k | −$33.1k | 5.83 | 62 | 0.00 | MAR, regime |
| 12 | RSIDIV | RSI 5 + 5% trail (long by design) | 360 | 48% | 1.50 | $593.0k | −$178.0k | 3.33 | 45 | −0.03 | MAR (DD-heavy) |

**Table C — the book, for scale:**

| Leg | Trades | Win% | PF | Net | Max DD | MAR / net-DD | Status |
|---|---|---|---|---|---|---|---|
| ORB 3.1 #125 (16 yr) | 4,064 | 41% | 1.61 | +$360.6k | **−$9.4k** | **38.6** | deployable (WF+lockbox+ES all PASS); triage-window repro exact: 3,815 / +$306.3k / 1.607 |
| ENGU-Q deploy (16 yr, honest fills) | 2,048 | — | ~1.4 | +$474.7k | −$65.6k | 7.2 | deployed leg (file-repro defect still open) |
| 1:1 ORB×ENGU-Q blend (17 yr) | — | — | — | +$835.4k | −$60.1k | 13.9 | the book baseline — 17-for-17 years |

Cross-strategy findings (each visible in 3+ independent ports):

1. **As-shipped configs are flat-to-badly-negative.** The most-boosted script of all
   (BBRSI, 46.7K) loses −$171k on NQ 5m as published. Five of twelve are negative on
   the deciding dataset as shipped; none exceeds MAR 2.5. Boosts measure chart
   appeal, not edge — now measured, not asserted.
2. **The short side is a universal money-loser.** In every both-direction system the
   long-only cut dominates — the round-9 meta-finding (upward-drifting index; shorts
   only pay intraday via ORB) reproduced 8 more times.
3. **Every "best corner" converges to the same thing: long-only drift capture,**
   MAR ~3–8, PF 1.2–1.6, corr vs ORB ≈ 0 — below the MAR ≥ 8 relevance bar and far
   below ORB 3.1 (38.6). It's one shelf, rediscovered 12 times in 12 costumes.
4. **1-minute execution is strictly worse than 5-minute** for every family — fee and
   churn dominance, consistent with the round-2 fill-artifact wall.
5. **High win rate = stop-less dip-holding** (MACDRSI 67% WR / 147-pt avg losers;
   FLAWLESS 72% / 118 pts; RSIDIV 67% / 85 pts). The win rate is the drawdown.
6. **TV strategy-report numbers are structurally untrustworthy for v2-era scripts:**
   ICHIHULL's fame rests on a `security()` repaint (look-ahead) — removing it flips
   the backtest to a coin-flip. The one honest description in the list (AOSTOCH's
   "educational, don't trade this") was also the one claim we fully confirmed.

**Program consequence:** the TV top-boosts source joins the two web sweeps as fully
dispatched — that's now three exhausted public-strategy sources (owner shortlist,
web deep-dive ×2, TV community top list). Champions unchanged: **ORB 3.1 (MAR 38.6)
· ENGU-Q deploy · the 1:1 blend ($835k, 17-for-17 years, −$60.1k DD)**. Remaining
edge paths are unchanged from round 11: more instruments (data buy), the order-flow
program (~Oct 2026), or a new owner-originated idea.

*Ports (12 files, `augur_strategies/`): BBRSI, MACD200, SUPERTREND_3_0, MACDRSI,
PMAX, HULL, AOSTOCH, GOLDX, FLAWLESS, EMAX, ICHIHULL, RSIDIV — all `_1_0.py` (3_0 for
SuperTrend), all plugin-contract, roll-seam-guarded, honest-fill, smoke-tested, and
usable in AUGUR/EDGELOG grid sweeps at any time. Durable artifacts:
`tools/r13_triage.py` (the driver) + `tools/r13_results/*.json` (every grid cell +
gate scan, committed 2026-07-17).*

---

## 5. Individual pickup guide (for a future session)

Everything a cold-start session needs to take ONE of these further, without this
conversation.

**Ground rules (non-negotiable, they are the house discipline):**
1. **All 12 lockboxes are SEALED** (2025-06-30 → 2026-06-30 never loaded). One look
   per family, owner sign-off first. Load data with `date_to="2025-06-30"` until then.
2. Rerun the exact cell first: `python tools/r13_triage.py <FILE> "<grid preset>"`
   — the driver checks the ORB #125 anchor (n=3,815 / $306,331 / PF 1.607) and
   aborts on mismatch; a pickup must reproduce the JSON numbers exactly before any
   new work (deterministic engine, no seeds).
3. **No new knobs, no wider grids without a fresh pre-registration written into this
   file BEFORE running.** A near-miss is not a re-tune license (TTIBS/SWING precedent).
4. The full winning param dict for each strategy = the top-MAR row of
   `tools/r13_results/r13_<NAME>_results.json` (`grid`, sorted by `mar`).

**Stage-2 battery (the pre-registered menu for any pickup — run in this order, stop
at first FAIL):**
- **B0 drift baseline (NEW, mandatory):** compare vs "always-long, RTH only, 1
  contract, same window/costs" on MAR and PF. Rationale: every round-13 corner is
  long-only; if it can't beat brainless long exposure it is a worse version of
  nothing. Pre-registered bar: beat the baseline on BOTH metrics.
- **B1 plateau:** all first-neighbor cells ≥ 50% of the peak cell's MAR.
- **B2 frozen walk-forward:** 6 folds, ≥ 4/6 OOS-positive, WFE ≥ 0.5.
- **B3 ES transfer, no re-fit:** PF ≥ 1.2.
- **B4 stats:** trade bootstrap P(net ≤ 0) ≤ 0.01; Deflated Sharpe vs the family's
  full search size (count EVERY cell ever run on the family, incl. round 13's).
- **B5 owner sign-off → lockbox one-shot.** Pre-register the exact config + pass/fail
  conditions in this file before the look.

### Pickup cards (sorted by best-version MAR — pickup priority)

**Every number is IS / triage** (in-sample: full 2010-06-07→2025-06-30, NQ 5m, each
strategy's best long-only cell). **WF = not run and LB = sealed for all 12** — nothing
passed triage, so none earned a walk-forward and all 12 lockboxes
(2025-06-30→2026-06-30) are untouched. All fail the MAR ≥ 8 bar (ORB = 38.6); pick up
the top 3 only.

| # | Strategy · file | Type — mechanism (indicators) | Best cell (long-only) | IS PF | IS MAR | IS Net | IS MaxDD | n | Note |
|---|---|---|---|---|---|---|---|---|---|
| 1 🥇 | **EMAX** · `EMAX_1_0.py` | Trend — dual-MA crossover (EMA) | `ema_fast=20, ema_slow=100` | 1.27 | **7.82** | $292.9k | −$37.4k | 1,810 | closest miss; real plateau (5 long cells MAR 6.1–7.8) |
| 2 🥈 | **BBRSI** · `BBRSI_1_0.py` | Mean-rev — band + oscillator (Bollinger + RSI) | `rsi_len=16, rsi_band=50, bb_mult=1.5` | 1.56 | 6.83 | $327.5k | −$48.0k | 550 | only mean-rev candidate (diversifier); MAR-7.42 sibling fails n≥300 |
| 3 🥉 | **PMAX** · `PMAX_1_0.py` | Trend — ATR-trail on an MA (SuperTrend-on-MA) | `ma_type="SMA", ma_length=20, mult=2.0` | 1.22 | 6.29 | $261.8k | −$41.6k | 1,836 | best trend-flip; covers SUPERTREND + HULL |
| 4 | ICHIHULL · `ICHIHULL_1_0.py` | Trend/confluence — Ichimoku + Hull MA + MACD | `keh=14, dt=0.0025` | 1.35 | 5.83 | $193.0k | −$33.1k | 1,174 | regime-fail (62% post-2021) |
| 5 | SUPERTREND · `SUPERTREND_3_0.py` | Trend — ATR trailing-stop flip | `atr_period=20, mult=3.0` | 1.15 | 4.84 | $274.5k | −$56.7k | 3,773 | dominated by PMAX |
| 6 | GOLDX · `GOLDX_1_0.py` | Trend — SMA 50/200 golden cross | `sma_fast=975, sma_slow=3900` | 2.48 | 4.30 | $177.5k | −$41.3k | 44 | only 44 trades (sample floor) |
| 7 | MACD200 · `MACD200_1_0.py` | Momentum — MACD + SMA200 filter | `sma_len=100` | 1.37 | 3.84 | $234.5k | −$61.0k | 512 | dominated |
| 8 | RSIDIV · `RSIDIV_1_0.py` | Reversal — RSI divergence (oscillator) | `rsi_len=5, tp_rsi_level=75, sl_type="PERC"` | 1.50 | 3.33 | $593.0k | −$178.0k | 360 | huge DD (no fixed stop) |
| 9 | HULL · `HULL_1_0.py` | Trend — Hull MA slope | `mode="Ehma", length=89` | 1.12 | 2.89 | $206.2k | −$71.3k | 4,553 | dominated |
| 10 | FLAWLESS · `FLAWLESS_1_0.py` | Mean-rev — band + oscillator (Bollinger 1σ + RSI) | `version="v1", rsi_buy_guard=50` | 1.24 | 2.71 | $109.6k | −$40.5k | 849 | dip-hold, 118-pt losers |
| 11 | MACDRSI · `MACDRSI_1_0.py` | Pullback — MACD cross + RSI-oversold | `rsi_os=35, lookback=5` | 1.23 | 1.91 | $214.3k | −$112.4k | 1,041 | dip-hold, 147-pt losers |
| 12 | AOSTOCH · `AOSTOCH_1_0.py` | Mean-rev — osc confluence + ATR bracket (AO+Stoch+RSI) | `atr_stop_mult=1.0, atr_tp_mult=2.0` | 1.01 | 0.11 | $4.0k | −$36.7k | 1,282 | ≈$0 over 15 yr |

All best cells are `direction="long"`. Full param dict = top-MAR entry of
`tools/r13_results/r13_<NAME>_results.json`.

**Core-4 coverage:** the PUBLISHED defaults ran on ALL four core datasets (NQ/ES ×
1m/5m) — in each JSON's `published` block. The TUNED corners above are **NQ 5m only**
(the grid dataset); re-running them on ES + NQ 1m is a pickup step. As-shipped core-4
for the top 3 (net / MAR; note these are the published *both*-direction configs, hence
worse than the long-only corners above):

| Strategy (as shipped) | NQ 5m | NQ 1m | ES 5m | ES 1m |
|---|---|---|---|---|
| EMAX (EMA 10/20, both) | −$97.8k / −0.7 | −$760.8k / −0.9 | −$73.0k / −0.5 | −$1.32M / −1.0 |
| BBRSI (RSI 16/45/2σ, both) | −$171.4k / −0.7 | +$22.0k / 0.1 | +$92.9k / 1.2 | −$114.8k / −0.7 |
| PMAX (EMA 10, ATR 10×3, both) | +$175.3k / 1.9 | −$7.0k / −0.0 | −$16.7k / −0.3 | −$103.2k / −0.6 |

**Honest expected value, before you spend a session:** the best candidate here (7.82)
enters stage 2 WEAKER than TTIBS did (12.3) — and TTIBS passed 6/6 walk-forward folds
plus a clean ES transfer and still lost −$44k in its lockbox year. NOISE-2 (round 12)
passed 4 of 5 battery gates and died on ES transfer. Program base rate at this bar:
0-for-25 families. If the session budget is one evening, the higher-EV uses remain:
(1) **fix the ENGU-Q file-repro defect** (known bug, certifies the blend + every
ENGU-relative number — leads are in BACKTESTING_STACK.md 2026-07-14 entry);
(2) the **more-instruments data decision** (YM/RTY/CL/GC 5m history for the already-
validated ORB recipe); (3) let the order-flow dataset keep accumulating (~Oct 2026).
Picking up EMAX-20/100-long is legitimate research — just size the expectation.

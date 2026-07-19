# PARAM_LIBRARY — cross-strategy parameter reference

## What this is

A **parameter** (a "knob") is any dial a strategy exposes — a lookback length, a
stop distance, a filter threshold — that changes how it trades without changing
the underlying idea. This doc collects every knob tried anywhere in the EDGE-LOG
strategy library, in one place, so that when you (or Claude) sit down to build or
tweak a strategy you can ask **"has something like this already been tried, and
did it work?"** instead of re-discovering the same dead end twice.

It is organized as:
1. **Per-strategy tables** (this section) — every knob a specific strategy file
   exposes, in plain language, with the range that was actually tested, the value
   that won (the "champion"), and an honest verdict.
2. **§ TRANSFERABLE IDEAS** — knob *concepts* that showed up validated in one
   strategy family and could plausibly help another one that doesn't have them yet.
3. **§ BRAINSTORM (untested)** — ideas nobody has coded or run yet anywhere in
   this stack. Clearly separated from the tested material above it.

**Plain-language rule:** every technical term (IBS, R-multiple, breakeven, ATR,
MAR, PF, drawdown, walk-forward, lockbox…) is defined the first time it's used.
See the **Glossary** at the very bottom if you land mid-document.

**Evidence verdict labels used throughout:**
- **DRIVES PnL / DRIVES RISK-ADJUSTED RETURN** — swept and shown to matter, with a
  number attached.
- **WEAK** — some effect, but small, inconsistent, or not worth the added complexity.
- **DEAD** — tried and rejected; keeping it off/at its neutral value is the
  validated choice.
- **UNTESTED** (in this file: "(not verified in repo)") — the knob exists in the
  code but no dedicated before/after result was found in the tracked docs
  (`BACKTESTING_STACK.md`, `ORB.md`, `TV_SWEEP.md`) during this pass. That does not
  mean it's bad — it means nobody has reported a verdict on it yet.

**Context (from project memory):** the book's current baseline is the 1:1 blend of
**ORB** and **ENGU-Q** (~$835k over 17 years, 17-for-17 winning years, max drawdown
≈ −$60k). Any new leg or param change should be judged by whether it improves
*that* blend, not just its own standalone numbers.

## Changelog
- **2026-07-18** — created (project item #46). Sources: every `augur_strategies/*.py`
  file's `DEFAULT_PARAMS`/`PARAM_GRID_PRESETS`, `BACKTESTING_STACK.md`, `ORB.md`,
  `TV_SWEEP.md`, `tools/paper_forward.py`.

---

## 1. ORB family (Opening Range Breakout)

**Concept:** mark the high/low of the first few bars of the trading session (the
"opening range"), then trade the breakout when price clears that box. Files:
`ORB_1_0.py` → `ORB_2_0.py` → `ORB_3_0.py` (+ 10 single-knob research forks) →
`ORB_3_1.py`/`3_2`/`3_3`. **Two validated configs exist in parallel** and both
appear as "champion" below, so read the CHAMPION column carefully:
- **#125 — the deployable** (`ORB_3_1.py`, `or_bars=1 / Both / stop 0.75 / vol 1.25 /
  ride-to-close (no target) / flat EOD / 5-bar trailing stop`). Full history net
  $360,640, PF 1.61, max drawdown (**DD**, the worst peak-to-trough dollar loss the
  equity curve ever suffered) −$9,352, **MAR** (net PnL ÷ |DD| — the standard way to
  compare strategies on a risk-adjusted basis, since raw PnL rewards recklessness)
  **38.6**. Triple-validated: walk-forward (**WF** — tune on past data, test on the
  next unseen slice, roll forward; the standard "is this overfit?" check) 6/6 folds,
  **lockbox** (the most recent year+ of data, sealed and looked at exactly once)
  PASS, and it transfers to ES with no re-fit.
- **#137 — the "locked" research base** (`ORB_3_0.py`, `or_bars=1 / Both / stop 1.75 /
  target 4.5R / vol 1.25 / atr_filter 0.1`). Highest raw PnL ($567k) but 4× #125's
  drawdown. Nearly every single-knob research file below (`_BE`, `_BET`, `_CC`,
  `_ENS`, `_LATE`, `_MM`, `_PYR`, `_RE`) freezes every other knob to #137's values
  so it can isolate ONE new lever cleanly.

### 1A. Core entry / signal knobs

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `or_bars` | Length of the "opening range" box, in bars, that the breakout is measured against. | 1–24 bars | **1** (5 min) — both #125 and #137 | Set once and left alone in the deployables; shorter OR = more/earlier signals. |
| `trade_mode` | Which direction(s) to trade: Both / First-candle-direction / Long Only / Short Only. | all 4 options | **Both** (deploy) | The free PF-maximizing search (Auto-Validate) drifts to **Short Only** on its own (§4.12 of ORB.md) because shorts carry almost all the edge (see §1C long/short split) — pinned to Both in the deployable to avoid overfitting a hard direction cut; the asymmetry itself is handled as a **sizing tilt**, not a mode switch (see TRANSFERABLE IDEAS). |
| `vol_filter` | Require the breakout bar's volume ≥ X × the average bar volume so far this session — skips low-conviction "fake" pokes on thin volume. | 0–3.0× | **1.25–1.5×** | **DRIVES PnL.** Kept in every validated config; filters the exact failure mode ORB is most prone to (thin-volume false breaks). |
| `breakout_buf` | Require price to clear the range edge by an extra cushion (a fraction of the range's width) before it counts as a break, instead of triggering on the first touch. | 0–0.5× | **0.0 (off)** | Sits at 0 in every validated config found; no dedicated ablation result located — **(not verified in repo)**. |
| `atr_filter` (vol-regime filter) | Skip a session if its recent volatility (avg of the last 5 sessions' range) is below X × the trailing 60-session median range — i.e. skip unusually "quiet" days. | 0–1.5× | **0.0 (off)** | **DEAD.** Every setting > 0 *lowers* PnL, profit factor (**PF** — gross wins ÷ gross losses; >1 means the strategy makes money overall), AND drawdown gets *worse*, not better (§4.8, ORB.md). The 5-bar trailing stop already exits quiet-day chop fast — the regime filter and the trail are substitutes, not complements. |
| `close_confirm` / `entry_mode` | Enter the instant price *touches* the range edge (models a resting stop order) **vs.** wait for a bar to *close* beyond the edge first (skips "false wick" pokes that pierce through and reverse, at the cost of a worse fill on every real break). Modes tested: touch / close / close-then-next-open / close-then-limit-back-at-level. | 4 fill modes | **touch** | **DEAD as an alternative.** Every close-confirmed flavor loses 72–99% of the net PnL in both the in-sample and lockbox windows (§4.18). The damage is the *confirmation delay itself* (chasing the move by most of a bar wrecks the risk geometry), not the fill price — fill-at-close ≈ fill-at-next-open, both equally bad. A widely-cited reconcile-tool claim that close-based entries net +$30k more over 15 years turned out to be a fill-model artifact of a different config comparison, not real harvestable alpha. |

### 1B. Risk & exit-management knobs

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `stop_frac` | Stop distance from entry, as a multiple of the opening-range's width (how far price can go against you before you're out). | 0.5 (hard floor) – 2.0× | **0.75** (#125 deployable) / **1.75** (#137 research base) | **DRIVES PnL — and is an artifact trap.** The 0.5 floor is load-bearing: below it, the backtest's assumption of an exact stop-price fill inflates the reported PF, because real tight stops get whipsawed/gapped in ways the sim doesn't model. Run #121's 0.25 stop is the cautionary tale — its flashy $615k / PF 2.50 was partly a fill artifact; a safe 0.75 stop with the same ride-to-close still nets ~$407k, so the underlying edge is real, just the tight stop had inflated it. |
| `target_R` | Optional take-profit at a multiple of the initial risk (an **R-multiple**: 1R = the same dollar distance as your stop; a "2R winner" made twice what you had at risk). 0 = ride the position all the way to the session close instead of capping it. | 0–10R | **0 (ride to close)** for #125 / **4.5R** for #137 | The measured-move variant of this idea (`target_orw`, the same cap expressed in opening-range widths instead of R) **DEAD**: win rate climbs to 66% at a tight 1×OR target exactly as advertised, but every *shorter* target loses money on the lockbox — the wide/uncapped target is what actually wins (§4.22 item X4). |
| `flat_eod` | Always exit at the session's last bar — no overnight hold. | True (every validated config) | **True** | Overnight holding was tested directly (a separate ETH/overnight-hold study, §4.22): every hold variant loses risk-adjusted return vs flat-EOD — adds gap + weekend/roll risk without adding edge on ORB's specific entries. **Contrast:** this is the *opposite* finding from ENGU-Q, where overnight holding supplies ~47% of net PnL (§2) — the same knob concept, opposite verdicts, entry-dependent. |
| `skip_holidays` | Skip half-day / early-close sessions (Thanksgiving, Christmas Eve, etc), detected by unusually short session bar-counts (no calendar needed). | True/False | used in the #137 research line | General good-hygiene knob; no isolated before/after result located — **(not verified in repo)**. |
| `partial_exit_R` | Exit HALF the position early once it reaches this R-multiple, letting the other half keep running. | 0–8R | **0 (off)** in the primary deployable | **WEAK.** Lifts the realized win rate to 50–60% (psychologically nicer) but does **not** improve MAR — dropped from the final deploy on Occam's-razor grounds (§4.2). Still offered as an optional lever if you want the smoother-feeling equity curve. |
| `trail_bars` | Once running, trail the stop to the rolling N-bar low (long) / high (short) — the stop only ever tightens in your favor, never loosens. | 0–30 bars | **5** (plateau 3–8 all close) | **THE single biggest risk-adjusted lever found in the whole ORB program.** Roughly halves drawdown and doubles MAR vs. no trail, for about 25% less gross PnL — which you recover (and then some) by sizing up into the freed drawdown budget. A plateau (3/5/8 all score similarly), not a spike, so it's robust rather than curve-fit. |
| `be_after_R` (breakeven ratchet) | **Breakeven** = once a trade has moved far enough in your favor, move the stop up to your entry price so the trade can no longer turn into a loser. `be_after_R` is the R-multiple of unrealized profit that triggers this move. | 0–4R (0.1 steps) | **1.0R** (robust plateau 0.9–1.3R) | **DRIVES RISK-ADJUSTED RETURN.** Cuts drawdown ~33% on the #137 base, in *both* the in-sample window and the lockbox, for a trivial PnL cost — the single cheapest drawdown reduction found in the entire study (§4.13/4.14, runs #154/#156). Important trap: optimizing this knob by raw PnL (not MAR/DD) picks a hollow, barely-triggering high value (2.6R) that the gates correctly flag as WEAK — you must rank a drawdown lever by risk-adjusted return, not PnL. |
| `be_mode` (alternative breakeven **triggers**) | Instead of "arm breakeven at X×R", try: time-based (after N bars in the trade), ATR-based (after X × the session's average range), OR-width-based, or price-structure-based (first higher-low/lower-high). | 5 trigger families | **"R" (the plain R-multiple) — nothing beat it** | **DEAD as alternatives (item K, §4.15).** Time and price-structure triggers both lose in both windows. The OR-width trigger is mathematically *identical* to the R-multiple one here (because risk = stop_frac × OR-width, so arming at 1×risk = arming at a fixed ×OR-width) — not a genuinely new lever. The ATR trigger books more raw PnL but at a *worse* drawdown — the wrong tradeoff for a knob whose whole job is cutting drawdown. |
| `trail_atr` / `trail_activate_R` / `breakeven_R` (chandelier-trail research, `ORB_3_2.py`) | A volatility-scaled ("chandelier") trailing stop instead of the fixed N-bar trail; an optional delay before trailing starts; a breakeven ratchet (same concept as `be_after_R`, different file). | trail_atr 0–6×, activate 0–4R, breakeven 0–4R | **none beat the plain 5-bar trail** | **DEAD / textbook overfitting example.** The chandelier trail looks *best* in-sample (MAR 38.9, better than the simple trail's 32.8) but is *worse* out-of-sample (lockbox PF 1.45 vs. 1.63) — exactly the in-sample-vs-lockbox trap this whole library exists to catch (§4.5). Activation delay hurts (gives back more before locking in); the breakeven lever here is redundant with `be_after_R` already in the base. |

### 1C. Session-timing, multi-trade & portfolio-style knobs

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `entry_cutoff_bars` / `time_stop_bar` (`ORB_3_3.py`) | Only ENTER before a given time in the session, and/or force-EXIT if still open by a given time. | various session-bar cutoffs | **0 (off)** for the deployable | `time_stop_bar` is **DEAD** — every setting worsens results; the trailing stop already exits stalled trades. `entry_cutoff_bars` uncovered a genuinely **real quality signal**: morning breakouts carry roughly 2× the profit factor of all-day trading (first-hour PF 2.2 vs. all-day 1.6; **lockbox PF 3.5**, 6/6 WF folds). But it's a quantity-vs-quality tradeoff (fewer trades = less total $), so it is **not** deployed as a hard cutoff — instead it's applied as a **size tilt** (see TRANSFERABLE IDEAS): trade all day, just size the morning trades up. |
| `late_bar` / `late_stop_frac` (`ORB_3_0_LATE.py`) | Give entries that fire late in the session (after a given session-bar index) a *different* stop fraction than early entries. | late_bar 0–48 bars, late_stop 0.5–2.0× | **0 / off (uniform kill, 6/6 cells fail)** | **DEAD.** The late-break weakness (63% of trades fire late, at a thinner PF ~1.30) is already priced by the time-of-day size tilt above — resizing the stop doesn't fix it. |
| `lunch_trail` (`ORB_3_0_ENSL.py`) | Temporarily tighten the trailing stop's lookback specifically during the 12:00–13:59 ET lunch chop, then loosen back afterward. | 0 (off) – 5 bars | **0 / no real effect** | **DEAD / no-adopt.** A mechanical "pass" exists at one setting but it converges to the baseline behavior rather than showing a genuine effect (§4.23 item X13). |
| `reentry_mode` (`ORB_3_0_RE.py`) | After the first trade of the session stops out, allow ONE more entry: same-side re-break, opposite-side "flip", or immediate stop-and-reverse. | none / rebreak / flip / sar | **none** | **DEAD.** Every mode loses risk-adjusted return in both windows — whipsaw days don't pay for a second shot (§4.19 item Q). |
| `pyramid_at_R` + `trail_bars` (`ORB_3_0_PYR.py`) | Add a SECOND contract only once the trade proves itself by moving +X×R in your favor (vs. adding at entry). | 0.25–3.0R | **beaten by the at-entry ensemble in every variant tested** | **DEAD.** Worse in both windows than the at-entry 2-lot ensemble below — adding a lot late is "buying the extension" at a worse price with less room to trail (§4.20 item U). |
| Ensemble blend: `target_R` (lot A) + `trail_bars` (lot B) (`ORB_3_0_ENS.py`) | Run the SAME entry as a 2-contract book: one lot rides with the breakeven ratchet to a target, the other lot trails on an N-bar low/high with no cap. Blended 50/50 into one "trade" for reporting. | target_R 3–6, trail_bars 2–12 | **target 4.5R / trail 5** (target 4.0R/trail 12 sits on the same plateau) | **WIN — genuine diversification, not just smoothing.** Beats BOTH single legs on lockbox MAR (9.2 vs. ride-only 7.1 / trail-only 5.3) **and** has the lowest lockbox drawdown of the three (§4.16). The two legs' drawdowns don't coincide, so blending cuts tail risk below either leg while lifting risk-adjusted return above both. Confirmed to hold on an ES transfer test with no re-fit. Caveat: 2 contracts = 2× fees and margin. |
| Position **sizing overlay** (not a strategy param — an execution-layer rule in `augur_engine/sizing.py`) | Size each trade by three *independent*, separately-validated factors: risk-parity (bigger size when the stop is tighter, so every trade risks the same dollars), a time-of-day tilt (~2× size in the first hour), and a side tilt (~1.5× short / 0.5× long, since shorts carry the edge — see below), capped at 3× the average size. | — | rp × time-tilt × short-tilt, capped 3× | **WIN — three independent edges STACK.** Lifts lockbox MAR from 6.9 to **15.0 (+118%)**, PF 1.63→2.85, winning 5/6 WF folds, with **zero change to entries or exits** (§4.10/4.11). Confirmed on ES too (lockbox MAR 5.0→13.5, +170%). |
| Long/short split (diagnostic, not a param — but the single biggest structural finding) | Splitting trades by direction: | — | shorts carry the edge | **LONG PF 1.03 (deadweight) vs. SHORT PF 2.74** (§4.11) — holds on the lockbox and transfers to ES with no re-fit. Plausible mechanism: indices gap up overnight, so an intraday *long* break of the tiny opening range tends to buy the post-gap high and get faded, while *short* breaks catch sharp risk-off moves. **Lesson: "tilt, don't cut"** — a hard short-only book loses to a short-*tilted* book on MAR (some long exposure diversifies the drawdown path), same lesson as the time-of-day cutoff above. |

**Also tested and rejected on ORB** (kept here for completeness so nobody re-runs them): black-swan/VIX/regime skip filters (amputate the short edge that carries the book — no filter improves MAR in either window, §4.17); DD-throttle / equity-curve-gate sizing (re-risks exactly when a V-shaped recovery is happening, hurting the lockbox, §4.19 items N/O); failed-break fade as its own strategy (net-negative both windows — a failed break leads to chop, not a reversal you can monetize, §4.20 item R); relative-volume sizing, VWAP-side tilt, cross-market (ES/NQ) breadth confirmation, prior-day value-area context, and five more prior-day-structure lenses (all fail cleanly or map to the *same* long/short-context factor already captured by the side tilt, §4.22/4.23); 1-minute-granularity ORB (looks great gross but is provably more slippage-fragile than the 5-minute version once stress-tested, §4.21 item X); overnight holding (loses MAR at every setting vs. flat-EOD, §4.22).

---

## 2. ENGU-Q family (descending-trendline break)

**Concept:** a quant rebuild of the owner's discretionary "Engulfing" setup. On an
uptrend (price above a trend **EMA** — an exponential moving average, a smoothed
trend line that weights recent bars more heavily), wait for a green candle to close
above a *descending* trendline drawn across the recent highs (i.e. break the line
of lower-highs — the pullback is over), on a volume spike, with a decisive close.
Stop = the recent swing low; the position then trails. Three timeframe-specific
files (`ENGUQ_1M/5M/15M_1_0.py`) tune independently; `ENGUDQ_1M_1_0.py` is the exact
short-side mirror (ascending trendline over lows, broken downward by a red candle).
**NQ 1m is the champion (run #149).**

**⚠️ Reproducibility caveat (documented 2026-07-14, BACKTESTING_STACK.md):** run
#149's *exact* parameter values could not be rebuilt from the currently checked-in
`ENGUQ_1M_1_0.py` — two independent attempts landed at very different results
(n=3,618 / $276k / DD −$133k) vs. the documented champion (n=2,048 / $474.7k /
DD −$65.6k). This is an entry-logic drift bug, not a typo, and is flagged as
unresolved. **Treat the file's shipped defaults below as indicative of the tuned
neighborhood, not certified to be the literal #149 config.** `breakeven_R = 1.5` is
the one addition that IS independently confirmed on top of whatever #149's base is.

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE (shipped 1m default — see caveat above) | EVIDENCE VERDICT |
|---|---|---|---|---|
| `tl_len` | How many bars of highs (or lows, for the short mirror) the trendline is fit to. Longer = a smoother, slower-reacting line. | 1m: 15–80 · 5m: 10–60 · 15m: 8–50 | **34** (1m) / 25 (5m) / 20 (15m) | Tuned per-timeframe; no isolated with/without ablation located beyond the shipped defaults — **(not verified in repo)**. |
| `vol_mult` | Breakout candle's volume must exceed X × its 20-bar average (0 = off). Same "require conviction volume" idea as ORB's `vol_filter`. | 0–5× | **1.2** (1m) / 1.3 (5m, 15m) | Present in every validated config to date; no isolated ablation located — **(not verified in repo)**. |
| `stop_mult` | Initial stop as a fraction of the entry-to-swing-low (or high) distance. | 0.3–2.0× | **1.7** (1m) / 1.0 (5m, 15m) | Risk-sizing knob, tuned per-timeframe; no isolated ablation located. |
| `act_R` | Start trailing the stop only once the trade is this many R-multiples in profit (see ORB's glossary entry for R-multiple). | 0–3R | **1.0** (1m) / 1.5 (5m, 15m) | Paired with `trail_frac`; not separately ablated in the tracked docs. |
| `trail_frac` | Once trailing is active, how far (in R-multiples) below the running high the stop sits. | 0.5–4.0R | **2.5** (1m) / 1.5 (5m, 15m) | Same as above — tuned, not individually ablated. |
| `buf_atr` | Price must clear the trendline by X × **ATR** (Average True Range — a standard volatility yardstick: the average of each bar's high-low-vs-prior-close range) before the break counts — skips marginal grazes. | 0–1.0× ATR | **0.35** (1m) / 0.1 (5m, 15m) | Entry-quality filter; not separately ablated in the tracked docs. |
| `min_brk` | The close must clear the trendline by at least X × ATR — a "decisive break" filter, distinct from `buf_atr`. | 0–3.0× ATR | **0.7** (1m) / 0.0 = off (5m, 15m) | Not separately ablated in the tracked docs. |
| `ema_len` | Length of the trend-direction EMA filter (only take longs above it / shorts below it). | 20–400 | **30** (1m) / 200 (5m, 15m) | Core trend gate; not separately ablated in the tracked docs beyond the tuned defaults. |
| `atr_len` | Lookback for the ATR used above. | 5–50 | **47** (1m) / 14 (5m, 15m) | Not separately ablated. |
| `regime_len` | OPTIONAL extra gate: only go long when price is above its own N-**day** simple average (a slower, longer-run trend filter layered on top of the EMA). 0 = off. Only exposed on the 1m files. | 0–100 days | **0 (off)** | In-file comment claims "long (~20-50d) skips bears/chop and cuts drawdown; short whipsaws" — this is a qualitative code comment, not a cited run number — **(not verified in repo beyond the in-file comment)**. |
| `breakeven_R` | Move the stop to breakeven once profit reaches X R-multiples (0 = off). | 0–3R | **1.5** | **DRIVES RISK-ADJUSTED RETURN — the only trade-management fix that survived honest fills.** +$12.9k lockbox net, drawdown −7.5% vs. #149 alone. A full "Round 2" trade-management sweep tried several other fixes and **all of them failed**: scale-out/partial exits (DEAD, all 5 variants below baseline), an ATR chandelier trail (DEAD, trade count balloons 2.3–6× and deepens the drawdown), and a pyramid-add-at-trail-activation (sole other baseline-beater on raw PnL, +18% net, but the gain concentrates 82% in the top-10 trades and drawdown deepens — **PARKED as a sizing decision, not adopted as new edge**). Mechanism: each overnight position costs ~$265 in gap slippage on average, and every management "fix" tried just multiplied position count instead of reducing that per-trade cost. |
| Gap>2% skip (execution-layer, **not** a `DEFAULT_PARAMS` knob) | Skip taking a signal on a session whose RTH open gapped more than 2% (either direction) from the prior session's RTH close. | fixed at 2% | `GAP_PCT_RULE = 0.02` in `tools/paper_forward.py` | This is a **live paper-forward deployment safety rule**, not a backtested/optimized strategy parameter — it exists to protect the live/paper book from an extreme overnight gap, and is applied at the monitoring-tool layer, not inside `ENGUQ_1M_1_0.py` itself. |
| (context) Overnight holding | ENGU-Q holds positions overnight/multi-day; a companion diagnostic (ORB's Round-4 study, run on the ENGU-Q blotter) found overnight holding supplies **46.6% of all net PnL**, and weekend holds are net **+$115,945** over 573 boundaries. | — | — | Directly contradicts the instinct to "flatten overnight to reduce risk" — flattening would delete nearly half the strategy's edge. **Contrast with ORB**, where flat-EOD is the validated choice — the same knob concept, opposite verdict, entry-dependent (see TRANSFERABLE IDEAS). |

**5-minute sibling (`ENGUQ_5M_1_0.py`, run #146):** honest-fills-restated at
$81,821 net / PF 1.463 lockbox; the same `breakeven_R=1.5` fix helps here too
(full $546,186 / PF 1.672). **Survives as a strategy but is NOT a portfolio
diversifier** — combined with the 1m leg, drawdown is roughly additive (both legs
are long NQ simultaneously 87.9% of sessions) — adding 5m is a size decision, not
new edge, same class as the parked pyramid idea above.

---

## 3. TTIBS 1.0 (Turnaround-Tuesday / Internal-Bar-Strength mean reversion)

**Concept:** a DAILY-bar, long-only mean-reversion strategy. **IBS** ("Internal Bar
Strength") = `(close − low) ÷ (high − low)` — where the day's close landed inside
its own high-low range: near 0 means it closed right on the low (weak), near 1
means it closed right on the high (strong). TTIBS buys weak closes and waits for a
recovery. **Family status: CLOSED** — it passed pre-registered triage, walk-forward
(6/6 folds), and an ES transfer with no re-fit, but **failed its sealed 12-month
lockbox** (net −$44,320, PF 0.44, 2026-07-15) and is no longer a deploy candidate.
It remains useful precisely as **parameter evidence** — a rare case where a family
died at the very last gate instead of an early one, so its param sensitivities are
trustworthy up to that point.

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `trigger` | Which "weakness" signal fires the entry: `mon1pct` (a Monday selloff of a given size vs. the classic "Turnaround Tuesday" folklore), `mon_ibs` (Monday + a down day + IBS<0.5), or `ibs` (any day at all with a low enough IBS — no day-of-week gate). | 3 options | **`ibs`** | **DRIVES PnL.** In a later knob-screen (run #165 — see note below), `trigger` was one of the two strongest PnL drivers, scoring **+0.94** above a random noise-probe knob (a control knob wired to do nothing, used to tell "real driver" from "sweep noise"). |
| `mon_drop` | (only used by `trigger=mon1pct`) how big a Monday selloff, as a fraction of the prior close, counts as the classic setup. | 0–0.05 (0–5%), hard-capped at 0.10 | **0.01** (1%) | **Near-dead as a driver.** The same knob-screen scored `mon_drop` at only **+0.005** above the noise probe — barely distinguishable from a knob that does nothing. Consistent with the `ibs` trigger (which ignores Monday/day-of-week entirely) beating the Monday-specific triggers. |
| `ibs_entry` | (only used by `trigger=ibs`) the IBS threshold below which a day counts as "weak enough to buy." Capped at 0.5 by design — above that you'd be buying strength, a different strategy entirely. | 0.05–0.40 (hard cap 0.5) | **0.20** — the pre-registered round-7 triage champion, verified in `BACKTESTING_STACK.md` (passed all 6 gates through walk-forward + ES transfer; failed only the sealed lockbox). | **DRIVES PnL** (+0.34 margin per the knob-screen referenced below). The app-validate runs (#161–#165, close fills, 18-mo lockbox) converge on **0.4** instead — see the note below for why the two champions differ and which one binds. |
| `fill_mode` | Fill the entry at the signal day's own **close** (a documented look-ahead — you can't actually trade a price the instant you see it print) or at the **next** session's real opening print (`next_open`, the deploy-honest mode). | close / next_open | **`next_open`** is the deploy-honest, gate-deciding mode. | The known look-ahead haircut from using `close` fills is ~21.5% of the edge (measured directly). Separately, the referenced knob-screen scored `fill_mode` as one of the **weakest** PnL-ranking drivers (+0.012, barely above noise) — meaning which fill mode you pick barely changes which *other* knobs look good, even though it materially changes the raw dollar total. Two different measurements; both are worth knowing. |
| `exit_mode` | How the trade closes: `next_close` (exit at the very next close), `strength` (wait for a close above the prior day's high), or `ibs_exit` (wait until IBS > 0.8 — today closed strong again). | 3 options | **`ibs_exit`** — the only exit_mode/hold_cap combination that cleared every one of the 6 pre-registered gates. | **DRIVES PnL** — tied with `trigger` as the strongest driver in the referenced knob-screen (+0.80). |
| `hold_cap` | Force-exit after this many trading days if no exit signal has fired — a safety cap so a mean-reversion trade that isn't reverting doesn't turn into an accidental long-term hold. | 1–10 (hard cap 20) | **6** — described in `BACKTESTING_STACK.md` as "the one non-free knob": holding only 2 or 4 days makes the trade correlate up to 0.44 with the ENGU-Q champion (i.e. it's secretly re-trading the same few-day NQ dip-bounce ENGU-Q already owns) — only the full 6-day hold decorrelates it (corr 0.25). | **DRIVES PnL/robustness** (+0.41 in the referenced knob-screen). The app-validate runs converge on **7** (and the 2026-07-18 auto-expand pass widened the range to 15 and confirmed the curve tapers with an interior smoothed peak at 8) — see the note below for why round-7's 6 and the app runs' 7 coexist. `hold_cap`'s exact optimum is sensitive to fill mode/objective — treat the *concept* (a mid-single-digit-to-low-double-digit day cap, clearly > 4) as the durable finding, not any single number. |
| `ma200` | Optional regime gate: only enter when today's close is above its trailing 200-session simple average — a long-run uptrend filter layered on the daily mean-reversion signal. | True/False | Off in the primary round-7 champion cell, but **4 of 6 neighboring cells (ibs_entry 0.20/0.30 × ma200 on/off) all pass every gate** — a broad shelf, not a spike. | **DRIVES PnL** per the referenced knob-screen (+0.57) even though the primary champion ships with it off — both settings work in the robust neighborhood. |

**Note on the knob-screen citation above (source + the "two champions" reconciled):**
run #165 is an **app run** — it lives in the EDGELOG website's run history
(Results tab, run #165, TTIBS Auto-Validate, 2026-07-18), not in the repo's .md
files, which is why a repo-docs search does not find it. Its knob-screen margins
(trigger +0.94, exit_mode +0.80, ma200 +0.57, hold_cap +0.41, ibs_entry +0.34,
mon_drop +0.005, fill_mode +0.012) were read directly from that run's 2L panel
data on 2026-07-18. The apparent champion conflict is real and explained: the
app runs (#161/#162/#164/#165) validate with **close fills + an 18-month
lockbox** and converge on `ibs_entry 0.4 / hold_cap 7`; round-7 in
`BACKTESTING_STACK.md` validated with **next_open (deploy-honest) fills + the
sealed full-year lockbox** and its champion was `ibs_entry 0.20 / hold_cap 6` —
and that round-7 sealed-lockbox FAIL is the family's binding verdict. Different
fill assumptions + different lockbox windows → different optima. The durable
reading: the knob-screen margins (which knobs matter) transfer across both;
the exact champion values do not.

---

## 4. RSIDIV 1.0 (TradingView "RSI Divergence Indicator" port, #12 of round 13)

**Concept:** a verbatim port of a 9.8K-boost public TradingView script. RSI(9)
pivots are tracked; a "bullish divergence" is flagged when a new pivot low in price
comes with a *higher* low in the RSI (price made a new low but momentum didn't
confirm it — a classic reversal tell). Long-only, with **pyramiding** (the ability
to add a second stacked entry under the same signal) up to `max_pyramid` lots.
**Family status: DEAD.** 0 of 12 round-13 "most-boosted TradingView strategies"
survived triage on this data (`TV_SWEEP.md`) — RSIDIV nets the single largest raw
dollar figure of the 12 but also carries the 2nd-worst drawdown; its best refined
cell scores MAR 3.33, well below the ≥8 deploy bar. Lockbox never spent (killed
at triage).

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `rsi_len` | RSI lookback period (the momentum oscillator's own smoothing window). | 2–30 | **5** in the best refined cell (published default 9) | **Real driver, but not a robust one.** Moving from 9→5 produced the family's single biggest net PnL ($593.0k) — and its 2nd-worst drawdown (−$178.0k, MAR 3.33). A volatile cell, not a plateau. |
| `lb_left` / `lb_right` | How many bars to the left/right must confirm a candidate bar as a genuine local swing pivot (more bars = more certainty, more lag). `lb_right` also sets how many bars the signal is *delayed* — a pivot can't be confirmed until you've seen that many bars after it. | left 1–5, right 1–10 | published defaults 1 / 3 (unchanged in every tested config found) | **(not verified in repo)** — not swept away from the published default in the docs read. |
| `tp_rsi_level` | RSI level that triggers the take-profit exit (when no trailing stop is in use). | 70–95 | published default 80 (round-13 grid also tried 75) | **(not verified in repo)** — the only supporting note found is the original author's own anecdotal claim that 75 was a strong corner on a different symbol; not a house-run finding. |
| `range_lower` / `range_upper` | How many bars must separate two pivots for a divergence to "count" — too close together is noise, too far apart is unrelated. | lower 1–30, upper 20–150 | published defaults 5 / 60 | **(not verified in repo)** — untested away from the published defaults in the tracked docs. |
| `use_hidden_bull` | Include "hidden" bullish divergence (a trend-*continuation* signal — RSI makes a lower low but price makes a higher low) alongside the classic reversal divergence. | True/False | published default True (kept True throughout) | **(not verified in repo)** — untested in isolation. |
| `sl_type` / `stop_loss` / `atr_length` | `NONE` = exit only on the RSI take-profit or a bear divergence. `PERC`/`ATR` = a ratchet-up trailing stop that *replaces* that exit entirely. | NONE/PERC/ATR, stop_loss 1–20% | best refined cell uses a ~5% trailing stop | Swapping the exit mechanism materially changes the risk profile (drives both the family's best net AND its 2nd-worst drawdown) but still doesn't clear the deploy bar. |
| `max_pyramid` | How many stacked entries (added lots) the strategy can hold at once under one signal. | 1–4 (published default 2) | published default 2 | **(not verified in repo)** — untested away from the default. |

---

## 5. GAPFADE 1.0 (conditioned small-gap fade)

**Concept:** fade a modest overnight gap back toward yesterday's close — buy a
small gap-down, short a small gap-up — entered at the 09:30 opening print. Built
because the *naive* version of this idea (fade any gap-down, target the prior
close) is publicly documented as net-negative; GAPFADE conditions the entry on a
gap-size "band" plus a prior-day weakness/strength check. **Family status: DEAD**,
confirmed by **two independent replications** (2026-07-15) — killed at triage,
lockbox never touched.

| PARAM | PLAIN-LANGUAGE DEFINITION | TESTED RANGE | CHAMPION VALUE | EVIDENCE VERDICT |
|---|---|---|---|---|
| `band_min` / `band_max` | The gap-size "sweet spot," as a % of the prior close. Below `band_min` there's supposedly no real edge to harvest (too close to noise); above `band_max` it's more likely a genuine breakaway move than something that fades. | min 0.05–0.30%, max 0.30–1.00% | published-literature default 0.15–0.60% | **DEAD.** Every band tested nets to noise or fails a regime-concentration check; the best plateau found across 216 configs is only ~$1.8k/yr. |
| `conditioning` | An extra qualifying check on **yesterday's** bar: `none` (band membership only), `yest_ibs_aligned` (yesterday closed weak/strong, matching the fade thesis — see IBS definition in §3), or `outside_bar` (today's open lands outside yesterday's entire high-low range). | 3 options | none of the three clears the bar | **DEAD.** The "aligned" conditioning fixes one gate (regime concentration) but fails a different one (single-year concentration) — no cell threads both. |
| `target_mode` | Target the FULL gap-fill (back to yesterday's close) or only 75% of the way there. | full / partial_75 | not separately decisive | The family died on the band/conditioning/regime gates before `target_mode` differentiated a winner in the docs read — **(not verified in repo beyond that framing)**. |
| `stop_mult` | Stop distance as a multiple of the entry-to-target distance (1.0 = symmetric risk/reward). | 0.5–2.0× | — | **(not verified in repo)** — no isolated ablation located. |
| `time_exit` | Force-flat at 13:00 ET if nothing else has fired yet, vs. hold to the session close. | 1300 / close | — | **(not verified in repo)** — no isolated ablation located. |
| `trade_mode` (diagnostic only) | Both / Long Only / Short Only — the pre-registered triage grid deliberately fixes this at "Both" and never sweeps it as its own axis. | Both / Long / Short | fixed at Both by design | The real finding lives in the **side split**, not this knob: two independent replications **disagree** on which side carried the (already economically trivial) residue — one found shorts carrying 83% of net, the other found longs +$32.8k against shorts −$26k to −$33k. **Verdict: GAPFADE is best read as side-agnostic noise**, not a directional finding either way — a useful negative result for any future gap-fade attempt. |

---

## 6. Other strategies in the repo (lighter coverage)

These files exist in `augur_strategies/` but either failed early screening, are
legacy/superseded, or are research-only assets with a thinner evidence trail than
the five families above. Params are listed for brainstorming value; verdicts are
family-level (from `BACKTESTING_STACK.md`'s strategy-library table and, for the
TV round-13 ports, `TV_SWEEP.md`), not per-knob.

### 6A. TradingView "most-boosted strategies" round 13 — **0 of 12 survived**

All 12 are verbatim ports of the most-boosted public TradingView scripts,
triaged under house rules (`TV_SWEEP.md`). **Verdict for the whole batch:** every
family's best refined corner lands on the same "long-only drift" shelf (MAR 3–7.8,
below the ≥8 deploy bar) — boosts (TradingView popularity) are not evidence of
edge. All 12 lockboxes sealed, unspent.

| File | TV strategy (boosts) | Core knobs | Best refined MAR |
|---|---|---|---|
| `BBRSI_1_0.py` | Bollinger+RSI double reversal (46.7K) | RSI period, band %, BB σ-width | 7.42 (n<300, fails sample-size gate) |
| `MACD200_1_0.py` | MACD(SMA)+SMA200 stop-and-reverse (30.4K) | MACD fast/slow/signal, SMA200 side filter | 3.84 |
| `SUPERTREND_3_0.py` | SuperTrend verbatim flip (24.4K) | ATR period, ATR multiplier, Wilder-vs-SMA ATR | 4.8 (long-only) |
| `MACDRSI_1_0.py` | MACD cross + RSI-oversold-recently, long (17.6K) | MACD cross, RSI oversold lookback | 1.91 |
| `PMAX_1_0.py` | "Profit Maximizer" MA-vs-ATR trail flip (16.6K) | MA type/length, ATR multiplier | 6.29 |
| `HULL_1_0.py` | Hull Suite slope flip (14.2K) | Hull MA length, slope lookback | 2.89 |
| `AOSTOCH_1_0.py` | AO+Stoch+RSI+ATR confluence (13.5K) | oscillator thresholds, ATR bracket ratio | 0.11 (economically dead) |
| `GOLDX_1_0.py` | Golden Cross SMA 50/200, long (10.9K) | the two SMA lengths | 4.30 (n=44, too few crosses on intraday bars) |
| `FLAWLESS_1_0.py` | BB(1σ)+RSI long w/ optional brackets (10.8K) | BB σ, RSI guard level, optional SL/TP | 2.71 |
| `EMAX_1_0.py` | single EMA(10/20) cross, always-in (10.7K) | the two EMA lengths | **7.82 — the sweep's closest miss**, still below bar |
| `ICHIHULL_1_0.py` | Ichimoku+Hull+MACD 4-way confluence (10.3K) | Ichimoku/Hull/MACD lengths | 5.83 (its famous TV backtest is a `security()` repaint artifact — the honest port is a coin-flip) |
| `RSIDIV_1_0.py` | RSI divergence w/ pyramiding (9.8K) | see §4 above | 3.33 |

### 6B. Research / superseded strategies

| File | Concept (1 line) | Notable params | Status |
|---|---|---|---|
| `DRIVE_1_0.py` | First-hour momentum: direction = sign of the first hour's move, ride to close. | `dr_bars` (drive window), `thr` (drive-strength filter vs. trailing median), `stop_frac` (same 0.5 floor rationale as ORB), `gap_align` (require the overnight gap to agree with the drive direction — a "tilt, don't cut" candidate, PF 1.26 aligned vs. 1.08 opposed), `trail_bars` (found dead, same as ORB's own trail research at this granularity). | 🔬 Research only — real but thin edge (pre-lockbox $295k, PF 1.18), genuine diversifier vs. ORB (correlation 0.23), but **failed walk-forward** (only 3/6 folds OOS-positive, and the edge concentrates almost entirely in 2021-2025) and **failed the ES transfer**. Lockbox never spent (gates failed first). |
| `REPLAY_1_0.py` | Not a discovered strategy — replays a CSV of trades YOU actually took (timestamp + side) through the same validation machinery as everything else, to test "does my own discretion have measurable edge?" | `entries_file`, `entry_at` (fill point: this-bar-open / this-bar-close / next-bar-open), `default_stop_pts` / `default_target_pts` (mechanical management for rows without a logged exit). | Tooling, not a strategy verdict — used for the owner's discretionary→quant conversion project. |
| `REVERT_1_0` / `1_1` / `1_2` | Intraday mean reversion: fade a stretch away from a short EMA mean, gated by a daily up/down bias. 1.1 adds a regime filter; 1.2 adds a time-of-day window (only fade mid-session, skip the open/close). | `mean_len`, `ext_mult` (stretch trigger, × ATR), `bias_mode` (prior-close vs. session-open daily bias), `use_tod`/`tod_lo`/`tod_hi` (1.2's time-of-day gate), `trail_stop`. | FAIL (all three versions) per the 2026-06-20 screen. |
| `VWAP_FADE_1_0` / `2_0` | Fade a stretch away from the session VWAP back toward it. v2 adds a regime gate (fade *with* the higher-timeframe trend instead of blind two-sided fading, after v1's "edge" turned out to be almost entirely a long-biased accident). | `band_mult` (stretch trigger, × VWAP σ), `regime_mode` (with_trend / against_trend / off) + `regime_len`, `max_hold` (time-stop), `cooldown_bars` (post-loss cooldown). | FAIL (v1) / weak (v2) per the 2026-06-20 screen. |
| `SUPERTREND_1_0` / `2_0` | Older, looser ATR trend-following adaptations (SMA-of-true-range "ATR", non-house fill conventions) — NOT Pine ports, predate `SUPERTREND_3_0.py`. | ATR multiplier, EMA filter. | Owner's own prior note "not strongly validated" is now a **measured** verdict via the verbatim `SUPERTREND_3_0.py` port: no honest edge (0/24 cells) — settles the whole family. |
| `OVERNIGHT_HOLD_1_0.py` | Deliberately minimal-DOF strategy: hold ONLY the overnight session (RTH close → next RTH open), flat all day, to isolate the documented overnight risk-premium. | `trend_filter` (only hold in uptrends — validated in-file as raising Sharpe 0.61→0.74 and cutting the 2022 loss from −$35k to −$9k, though not cross-checked against the house gate battery), `trend_len`, `stop_pts`. | FAIL per the 2026-06-20 screen (family-level; the in-file trend-filter note above predates that screen and wasn't re-verified against it — **(not verified in repo beyond the in-file comment)**). |
| `GAINZ_RF_1_0.py` | A from-scratch random-forest classifier (RSI/trend/momentum features) predicting next-bar direction, trading only high-conviction signals with ATR-based TP/SL + a time-stop. | `probThreshold` (conviction gate on P(up)/P(down)), `atrMultTP`/`atrMultSL`, `maxHold`, `lookback` (rolling retraining window), `numTrees`, `signalCooldown`. | "In library; not a validated deploy candidate" per `BACKTESTING_STACK.md` — the existing example of a direct-forecasting (ML-predicts-price) strategy, a class the team has deprioritized (Carl McBride Ellis's own notebook on this approach is titled "LSTM = FAIL"). |
| `ENGU_1_1_20.py` … `ENGU_1_3_5.py` (8 files) | Legacy, pre-quant "engulfing reversal" strategies — several were AI-evolved (Claude/Grok) iterations that predate the ENGU-Q quant rebuild (§2). | daily-bias gates, gate-2-of-3 confluence, tight-consolidation filters (varies by version) | Mostly WEAK/FAIL per the 2026-06-20 screen; **1.3.4 is the least-bad (still WEAK)**. Superseded — see §2 (ENGU-Q) for the current, validated quant family. Not deep-dived here. |

---

## 7. TRANSFERABLE IDEAS — concepts that proved out in one family and might help another

Each entry: which strategy proved the concept, what it actually did there, and
which *other* families in this library look like plausible candidates (with a
reason, and any known reason it might NOT transfer).

1. **Breakeven ratchet (move stop to entry after +X R)** — proved on **ORB**
   (`be_after_R=1.0`, −33% drawdown at ~zero PnL cost, the cheapest drawdown fix
   found in the whole study) and independently on **ENGU-Q** (`breakeven_R=1.5`,
   the only trade-management fix that survived honest fills there). Two different
   families, same lever, same direction of result — a strong signal this concept
   generalizes. **Candidates it's missing from:** `DRIVE_1_0.py` (has a stop and a
   target but no breakeven ratchet — and DRIVE's exits are already modeled almost
   identically to ORB's, so this is a low-effort test), `REVERT_1_2.py` and
   `VWAP_FADE_2_0.py` (both have ATR-based stops/targets but no breakeven step),
   `GAINZ_RF_1_0.py` (has ATR TP/SL, no breakeven). **TTIBS has no stop-loss at
   all** in v1.0, so "breakeven" doesn't map directly — but a same-shaped idea
   ("once IBS recovers partway, tighten the max-hold") is a nearby untested
   variant (see §8).

2. **Time-stop / max-hold cap** — cuts both ways depending on the family, which
   is itself the useful lesson. On **TTIBS**, `hold_cap` is described as "the one
   non-free knob" — too short and the trade is secretly a disguised ENGU-Q clone;
   it MUST be long enough (≈6-7 days) to decorrelate. On **ORB**, the equivalent
   idea (`time_stop_bar`, force-exit by a fixed time of day) is flatly **DEAD** —
   the trailing stop already exits stalled trades faster and better. `GAINZ_RF`
   and `VWAP_FADE` both already ship a `maxHold`/`max_hold` knob (untested against
   ablation in the docs read). **Lesson for anything new:** a time-stop is worth
   trying when the strategy has NO other mechanism for cutting a stalled trade
   loose (TTIBS's daily bars, no trailing stop); it's redundant-to-harmful once a
   trailing stop already exists (ORB).

3. **Regime / trend filter (EMA or SMA gate)** — mixed evidence, context matters.
   **ENGU-Q**'s `ema_len` trend gate is core to the strategy (always on) and its
   optional `regime_len` (an even slower daily-SMA layer) is a documented (if
   anecdotal) drawdown-cutter. **VWAP FADE 2.0**'s entire redesign *was* adding a
   regime gate (`regime_mode="with_trend"`) after v1 turned out to be an
   accidental long-beta bet. On the other hand, **ORB**'s equivalent idea
   (`atr_filter`, a volatility-regime skip) is flatly **DEAD** on the deployable —
   because the trailing stop already handles the exact failure mode (quiet-day
   chop) the filter was meant to catch. **Candidates:** `REVERT` already has
   `bias_mode` (a regime-ish daily anchor) but the whole family still FAILs, so a
   *stronger* regime gate (an EMA slope filter, ENGU-Q-style) is untested there;
   `DRIVE_1_0.py` has no regime filter at all today.

4. **Session/time-of-day size tilt (not a hard filter)** — proved on **ORB**:
   morning breakouts carry ~2× the profit factor of all-day trading, but cutting
   the afternoon entirely *hurts* MAR (concentrates the whole risk budget into 31%
   of trades). The winning move was **sizing** morning trades up while still
   taking every trade — "tilt, don't cut." `REVERT_1_2.py` tried the opposite
   shape of this idea (a hard time-of-day *window*, `tod_lo`/`tod_hi`, only
   trading mid-session) — the family still FAILs overall, so it's unclear whether
   that specific gate helped or hurt in isolation — **(not verified in repo)**.
   **Candidate:** `GAPFADE`'s `time_exit` (1300 vs. close) is a time-of-day EXIT
   idea, not entry-sizing — the ORB lesson suggests a size-tilt version of any
   time-of-day observation is more likely to survive than a hard cutoff.

5. **Gap filters/fades** — consistently weak-to-dead as a source of EDGE across
   three independent tests: **GAPFADE**'s entire premise (trade the gap itself)
   died twice; **ORB**'s post-gap-stop conditioning was tested and found not
   significant (p=0.11); **DRIVE**'s `gap_align` is only a mild tilt candidate
   (PF 1.26 vs. 1.08), not adopted. **ENGU-Q**'s 2% gap skip is a *live risk
   control*, not a discovered edge — it exists to cap tail risk on an already-
   working strategy, not because gaps predict direction. **Takeaway for any new
   strategy:** don't expect a gap-based entry/filter to be the edge; a gap-based
   *risk cap* on an existing edge is the pattern that's actually worked.

6. **Stop-fraction floor (0.5× the reference range)** — proved on **ORB**
   (`stop_frac` floor) and explicitly re-used with the same rationale on **DRIVE**
   (`stop_frac`, same 0.5 floor, same "exact-stop-fill inflates PF" comment).
   **This is a general backtesting-engine caveat, not just a strategy finding:**
   any strategy whose stop is a fraction of a measured range (GAPFADE's
   `stop_mult`, ENGU-Q's `stop_mult`) should be checked for the same artifact
   before trusting a very tight setting's backtested PF.

7. **Risk-parity / drawdown-budget position sizing** (size ∝ 1/stop-distance,
   capped at 3× average) — proved on **ORB** as a modest, *generalizing* win
   (lockbox MAR +29%, drawdown roughly halved, survives 4/6 WF folds) —
   critically, unlike the chandelier-trail idea above, this one held up
   out-of-sample. It's a strategy-agnostic execution-layer idea (implemented in
   `augur_engine/sizing.py`) that could in principle apply to **any** strategy
   with a well-defined per-trade dollar risk — **ENGU-Q, DRIVE, GAPFADE** all
   qualify structurally; none of them have had this sizing overlay tested yet.

8. **Entry-strength / decisiveness thresholds** — ORB's `vol_filter` (breakout-bar
   volume ≥ X× average) and ENGU-Q's `vol_mult` + `min_brk` + `buf_atr` (volume
   spike + "decisive break" + "clear the line by enough ATR") are the same
   underlying idea — don't trade a marginal/low-conviction trigger — applied to
   two different signal types (a range break vs. a trendline break), and both
   ship with non-zero, tuned defaults. `GAINZ_RF`'s `probThreshold` (only act on
   high-confidence model predictions) is the same concept again, for an ML
   signal. **This pattern is worth adding to any new entry rule as a first-class
   knob from day one** — it keeps showing up as load-bearing even where a
   dedicated before/after ablation wasn't separately logged.

9. **Ensemble blend of two exit styles on the SAME entry** — proved on **ORB**
   (`ORB_3_0_ENS.py`: one lot rides-with-breakeven, one lot trails; blended 50/50)
   as genuine diversification (beats both legs on lockbox MAR + drawdown,
   confirmed to transfer to ES). **Untested on ENGU-Q or DRIVE**, both of which
   already have both a breakeven/target exit style AND a trailing-stop-flavored
   exit available as separate knobs — the ORB result suggests running both
   simultaneously (as a blended 2-lot book) could beat picking just one.

10. **Portfolio-level blending across different STRATEGIES** (not exit styles
    within one strategy) — the ORB × ENGU-Q 1:1 blend is the current book
    baseline (~$835k / 17-for-17 winning years / max DD ≈ −$60k, from project
    memory) precisely because the two families' daily PnL is close to
    uncorrelated. **DRIVE** is flagged in its own docs as "a genuine diversifier"
    (correlation 0.23 vs. ORB) despite failing walk-forward as a standalone
    strategy — worth a fresh look purely as a portfolio diversifier rather than a
    standalone deploy candidate, if a structural (not just era-specific) edge is
    ever re-confirmed for it.

11. **Long/short asymmetry as a SIZE tilt, not a hard direction filter** — proved
    on **ORB** (shorts PF 2.74 vs. longs PF 1.03; tilting size by side beats
    excluding a side outright — the same "tilt, don't cut" lesson as the
    time-of-day finding). **RSIDIV is long-only by design** (no short side to
    tilt); **GAPFADE, REVERT, and VWAP FADE** all already trade both sides — none
    of them have had a *directional size tilt* (as opposed to a hard direction
    filter) tested the way ORB's was.

12. **Pyramiding / adding to a winner** — tested and **rejected** on ORB twice:
    adding a 2nd lot at a fixed +R level (`pyramid_at_R`) loses to the at-entry
    ensemble in both windows; **RSIDIV** ships native pyramiding (`max_pyramid`,
    from its published TV source) but the whole family is dead on other grounds,
    so this specific knob was never cleanly tested in isolation there. **Lesson
    for any new strategy design:** based on ORB's evidence, splitting size at
    ENTRY (an ensemble) appears to beat adding size LATER (a pyramid) — worth
    defaulting to the ensemble shape rather than the pyramid shape when designing
    a new multi-lot idea.

13. **Post-loss cooldown** — **VWAP FADE 2.0** ships a `cooldown_bars` knob
    (untested in isolation in the docs read). Directly relevant counter-evidence
    exists on **ENGU-Q**: a dedicated study found losses are sequentially
    independent (a statistical test for "do losses cluster/predict more losses"
    came back p=0.53, i.e. no pattern) and expectancy after 3+ consecutive losses
    is actually the strategy's *best* ($381 vs. $232 unconditional) — leading to
    "all cooldown/stand-aside ideas DEAD" on that family. **Any new
    cooldown-after-loss idea should budget for this being a likely dead end**
    unless a fresh sequential-independence check says otherwise for that specific
    strategy.

---

## 8. BRAINSTORM — untested ideas (not yet tried anywhere in this stack)

Everything below is a genuine idea, not a re-statement of something already
swept. Flagged **UNTESTED** throughout — these are starting points for
discussion, not recommendations.

- **A TTIBS-style "partial recovery" time-stop.** TTIBS has no stop-loss at all
  and a fixed-day `hold_cap`. An untested variant: shorten the max hold once IBS
  has recovered PART of the way (e.g. above 0.5 but not yet the 0.8 exit
  threshold) — a soft version of ORB's breakeven idea, reshaped for a
  no-stop-loss daily strategy. **UNTESTED.**
- **Volatility-regime filters using VIX term structure, not just VIX level.**
  ORB's own backlog explicitly flags this as needing data not yet on hand ("Tier
  4: needs data we don't have yet" in `ORB.md` — VIX term structure, 0DTE gamma
  levels, TICK/ADD internals). **UNTESTED**, blocked on data.
  Note: a simple VIX-LEVEL filter *was* tried on ORB and found to not help
  (§4.17) — the term-structure version is a genuinely different, still-open
  question, not a re-run of that result.
- **Order-flow / bid-ask imbalance confirmation on the breakout bar.** Flagged
  as item "V" in `ORB.md`'s backlog — needs months of tick/delta data to
  forward-test; per project memory, real order-flow data access is expected
  ~October 2026. **UNTESTED**, deliberately deferred, not forgotten.
- **A shared, cross-strategy dollar-risk budget.** Today, ORB's sizing overlay
  (`augur_engine/sizing.py`) sizes ORB's own trades; ENGU-Q is sized separately.
  Nobody has built a single risk manager that caps *total* concurrent open risk
  across ORB + ENGU-Q + any future strategy at once (as opposed to each
  strategy independently risk-sizing itself and simply running side-by-side).
  **UNTESTED.**
- **Cross-strategy conditional gating** (as opposed to a static blend). The
  ORB↔ENGU-Q daily-PnL correlation has been measured multiple times (roughly
  −0.03 to +0.09 depending on the exact repro) but nobody has tried using ONE
  strategy's live state (e.g. "ENGU-Q is currently in its worst-20% drawdown
  bucket") as a conditional SIZE tilt on the OTHER strategy, the way ORB tilts
  its own size by time-of-day and side. **UNTESTED.**
- **A pre-entry "scale-in" (start small, add on confirmation), as the mirror
  image of the pyramid-at-+R idea that was tried and rejected.** The rejected
  ORB pyramid ADDED a winner after it had already proven itself; an untested
  alternative is to ENTER smaller and add on a *specific new confirmation signal*
  (not just "+R of open profit") — e.g. a second trendline break for ENGU-Q, or
  a second volume-confirmed push through the range for ORB. Different mechanism
  from the rejected pyramid, so the prior negative result doesn't necessarily
  carry over. **UNTESTED.**
- **Equity/account-size-aware position sizing (Kelly-fraction or similar).**
  Monte Carlo work exists on account-sizing questions ("what account size keeps
  P(losing 33% of the account) under X%") but no strategy file implements a
  Kelly-style or equity-scaling position-size PARAMETER — sizing today is either
  fixed-contract or the ORB-specific risk-parity overlay. **UNTESTED.**
- **An earnings/economic-calendar filter for the Webull stock/ETF side of the
  book.** The Webull integration (auto-import via the official OpenAPI) is new
  and none of the strategy files in `augur_strategies/` currently expose an
  earnings-date or macro-calendar-aware parameter (ORB's FOMC/CPI/NFP work was a
  *diagnostic* on futures, not a strategy knob, and found no actionable filter
  there anyway — see the ORB "also tested and rejected" list in §1). Whether an
  earnings blackout matters for equities specifically is a fresh, untested
  question. **UNTESTED.**
- **A unified "context-tilt" factor across families.** ORB's own research
  program converged on one repeated factor (responsive shorts against
  prior-day/overnight strength are the cream; longs chasing strength are dead
  weight) from five independent lenses — but a pre-registered attempt to turn
  that into an ex-ante sizing RULE failed its own bar (`ORB.md` §4.24). Whether
  the *same* context factor (fade-strength vs. chase-strength) shows up as a
  usable tilt on ENGU-Q, DRIVE, or GAPFADE has never been checked. **UNTESTED.**

---

## Glossary (plain language, alphabetical)

- **ATR (Average True Range)** — a standard volatility yardstick: the average,
  over some lookback, of each bar's true range (the largest of high-low,
  high-vs-prior-close, or low-vs-prior-close). Bigger ATR = a more volatile
  instrument/period.
- **Breakeven (ratchet)** — moving your stop-loss up to your entry price once a
  trade has moved far enough in your favor, so the worst case becomes "scratch,
  no loss" instead of a full stop-out.
- **DD (drawdown)** — the worst peak-to-trough dollar loss the equity curve ever
  experiences. Always quoted as a negative/loss number.
- **EMA / SMA** — Exponential / Simple Moving Average: a smoothed trend line. EMA
  weights recent bars more; SMA weights every bar in the window equally.
- **Gate (ML gate)** — a second model that scores each trade a strategy wants to
  take and skips the low-confidence ones. It never changes the strategy itself,
  only filters which of its signals get taken.
- **IBS (Internal Bar Strength)** — `(close − low) ÷ (high − low)`: where a bar's
  (usually a day's) close landed inside its own range. 0 = closed on the low
  (weak), 1 = closed on the high (strong).
- **Lockbox** — the most recent slice of history (often the last 12 months),
  sealed off and looked at exactly once, after every other decision is locked in,
  to check a result wasn't just curve-fit to everything else.
- **MAR (also written Calmar)** — net PnL ÷ |max drawdown|. The standard way to
  compare strategies on a risk-adjusted basis, since raw PnL rewards
  recklessness (a strategy that makes $1M by risking a $900k drawdown is not
  better than one that makes $400k on a $10k drawdown).
- **Noise-probe / permutation test** — a way to tell whether a knob genuinely
  drives performance or the sweep is just finding noise: wire in a "control" knob
  that's designed to do nothing, run the same search, and see whether the real
  knob scores meaningfully above that control.
- **Plateau vs. spike** — a plateau is a range of a knob's values that all score
  similarly well (robust — small changes in the value don't wreck the result); a
  spike is one narrow value that scores far better than its neighbors (fragile —
  usually a sign of curve-fitting/overfitting).
- **PF (profit factor)** — gross winning dollars ÷ gross losing dollars. Above 1.0
  means the strategy is net profitable; below 1.0 means it loses money overall.
- **Pyramiding** — adding one or more additional positions on top of an existing
  one under the same trade idea, rather than trading a single fixed size.
- **R-multiple** — a way of measuring a trade's result relative to what you risked
  on it. 1R = you gained/lost exactly the same dollar amount as your initial
  stop distance implied; "the trade hit 3R" means it made three times that.
- **RTH / ETH** — Regular Trading Hours (the official day-session window) vs.
  Extended Trading Hours (overnight/pre-market electronic session).
- **Session** — one trading day's worth of bars (for an RTH-only dataset, from
  the open print to the close print).
- **"Tilt, don't cut"** — a repeated lesson across this library: when you
  discover a sub-population of trades is better than another (mornings vs.
  afternoons, shorts vs. longs), the winning move is almost always to *size* the
  better bucket up while still trading the rest, not to delete the weaker bucket
  entirely — hard cuts repeatedly concentrated risk and hurt risk-adjusted
  return more than they helped.
- **Walk-forward (WF)** — a validation method: tune a strategy's knobs on a past
  window of data, test the result on the very next (still historical, but
  previously untouched) window, then roll both windows forward and repeat. A
  strategy that only wins on the window it was tuned on, and loses on the next
  one, is overfit.

---

## Sources read for this document

`augur_strategies/ORB_1_0.py`, `ORB_2_0.py`, `ORB_3_0.py`, `ORB_3_0_BE.py`,
`ORB_3_0_BEAV.py`, `ORB_3_0_BET.py`, `ORB_3_0_CC.py`, `ORB_3_0_ENS.py`,
`ORB_3_0_ENSL.py`, `ORB_3_0_LATE.py`, `ORB_3_0_MM.py`, `ORB_3_0_PYR.py`,
`ORB_3_0_RE.py`, `ORB_3_1.py`, `ORB_3_2.py`, `ORB_3_3.py`, `ORB_FADE_1_0.py`,
`ENGUQ_1M_1_0.py`, `ENGUQ_5M_1_0.py`, `ENGUQ_15M_1_0.py`, `ENGUDQ_1M_1_0.py`,
`TTIBS_1_0.py`, `RSIDIV_1_0.py`, `GAPFADE_1_0.py`, `DRIVE_1_0.py`,
`REPLAY_1_0.py`, `REVERT_1_2.py`, `VWAP_FADE_2_0.py`, `SUPERTREND_3_0.py`,
`GAINZ_RF_1_0.py`, `OVERNIGHT_HOLD_1_0.py`, plus `STRATEGY_NAME`/`DESCRIPTION`
scans of every remaining file in `augur_strategies/` — `BACKTESTING_STACK.md`
(full) — `ORB.md` (full) — `TV_SWEEP.md` (round-13 summary + per-strategy
sections) — `tools/paper_forward.py` (the ENGU-Q gap-skip rule).

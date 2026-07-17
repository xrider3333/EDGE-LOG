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
| 2 | 30.4K | MACD + SMA 200 Strategy (ChartArt) | SMA-based MACD histogram zero-cross + macd>0 + close[26] vs SMA200 side filter → stop-and-reverse | fresh (regime-filtered momentum) | `MACD200_1_0.py` | queued |
| 3 | 24.4K | SuperTrend STRATEGY (KivancOzbilgic) | ATR(10)×3.0 on hl2, flip on trend change, always-in | SUPERTREND 1.0/2.0 in library, "not strongly validated" | reuse + TV-exact config | queued |
| 4 | 17.6K | MACD Bull Crossover + RSI Oversold 5-ago, Long (Trebor_Namor) | long when MACD crosses signal AND RSI was <30 within 5 bars; exit on bear cross w/ hist>0 + RSI>70 5-ago; optional SL/TP | fresh (source protected on TV; author's own Python port on GitHub used) | `MACDRSI_1_0.py` | queued |
| 5 | 16.6K | PMax Explorer STRATEGY & SCREENER (KivancOzbilgic) | "Profit Maximizer": MA (8 types) vs ATR trailing line, flip on cross | SuperTrend-on-MA family | `PMAX_1_0.py` | queued |
| 6 | 14.2K | Hull Suite Strategy (DashTrader) | HMA(55) slope vs 2 bars ago; long-only default (long/flat), "all" = flip | fresh (HMA trend) | `HULL_1_0.py` | queued |
| 7 | 13.5K | Buy&Sell AO+Stoch+RSI+ATR (SerdarYILMAZ) | RSI+Stoch oversold + AO turns positive → long w/ ATR SL/TP (author labels it educational) | fresh (oscillator confluence) | `AOSTOCH_1_0.py` | queued |
| 8 | 10.9K | Golden Cross SMA 50/200, Long Only (ChartArt) | SMA50 crosses SMA200 → long; cross under → flat | fresh, but a daily-scale signal — expected G1 fail on intraday bars (few crosses) | `GOLDX_1_0.py` | queued |
| 9 | 10.8K | Flawless Victory 15m BTC "ML" (Trebor_Namor) | BB(20,1σ) + RSI bounds long strategy, 2 param versions + optional SL/TP; hyper-fit to 1yr of BTC | BBRSI cousin (1σ band) | `FLAWLESS_1_0.py` | queued |
| 10 | 10.7K | BUY and SELL single EMA cross (Che_Trader) | EMA(10)/EMA(20) cross, always-in flip | the plainest momentum baseline | `EMAX_1_0.py` | queued |
| 11 | 10.3K | Ichimoku + Daily-Candle_X + HULL-MA_X + MacD (SeaSide420) | 4-indicator confluence flip (Ichimoku cloud + daily-candle cross + HMA cross + HMA-MACD) | fresh (confluence) | `ICHIHULL_1_0.py` | queued |
| 12 | 9.8K | RSI Divergence Indicator strategy (eemani123) | RSI(5) bull/hidden-bull divergence → long (pyramiding 2); exit RSI>75 or bear div; optional ATR trail | fresh (divergence) | `RSIDIV_1_0.py` | queued |
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

*(sections 13.2+ appended as each strategy is tested)*

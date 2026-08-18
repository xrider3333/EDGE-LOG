# NOISE — wide-band intraday momentum envelope: lockbox findings & open questions

> Living handoff doc. **Last updated: 2026-08-17** (variant campaign session — see the
> "2026-08-17 — variant campaign" section: pre-registered entry-quality filters cleared
> the bar; knobs shipped in `NOISE_1_0.py`; 12-cell comparison GRID + full re-validate + first NOISE BOOK job queued;
> the "Campaign results table" subsection carries every config with IS/WF/LB dollar
> splits + drawdown, regenerable via tools/noise_campaign_table.py).
> Written to hand off to a parallel NOISE session. Everything here is read straight from
> the Firestore run doc for **auto-validate run #225 (NOISE-6)** — no re-derivation, no
> estimates. Field paths are given so anything below can be re-checked in one query.

---

## ⚠ READ FIRST — the lockbox metrics are ALREADY SAVED. No engine revamp needed.

**If a session is about to rebuild the engine to compute lockbox-only stats: stop.
The engine already computes and persists IS / WF / LB as separate slices. It is a
report-SURFACING gap, not a computation gap.**

Per-run Firestore doc — `users/{uid}/runs/{runId}`:

| Field path | What it holds |
|---|---|
| `validate.lockbox` | **lockbox-ONLY summary**: pf, pnl, dd, trades, sharpe, sortino, win_rate, avg_win, avg_loss, from, to, pass |
| `win_dist_lb` | per-trade P&L array, **lockbox slice** |
| `mae_mfe_lb` | per-trade MAE/MFE arrays, **lockbox slice** |
| `win_dist_wf` / `mae_mfe_wf` | same two, **walk-forward slice** |
| `validate.windows` | `{optimize: [from,to], lockbox: [from,to], lockbox_months}` |

So the LB slice can be rendered today by reading existing fields. Confirmed present and
populated on run #225 on 2026-08-15.

---

## Run #225 (NOISE-6) — verdict PASS

Window 2010-06-07 → **2026-08-12**. NQ 5m. cost_pts 0.533, multiplier 20.

**This run used a FRESH 18-month lockbox — `2025-02-11 → 2026-08-12` — not the spent
2025-06-30→2026-06-30 window.** That matters: the old NOISE lockbox was
confirmatory-only, and much of the caution written into `augur_strategies/NOISE_1_0.py`'s
docstring (dated 2026-08-08) predates this run and is stale as a result.

### Champion config (`best_params`)

```
lookback        = 44
band_mult_long  = 0.75
band_mult_short = 1.5      <- ASYMMETRIC
exit_mode       = 'vwap'
stop_mode       = 'bandwidth'
stop_k          = 1.75
side='Both', window='all_day', flat_eod=True, skip_holidays=False
```

### Headline numbers

| Scope | n | net | PF | DD |
|---|---|---|---|---|
| Full run (`best_*`) | 3,872 | $96,611 | 1.174 | −$16,827 |
| **Lockbox only** (`validate.lockbox`) | **424** | **$1,157** | **1.084** | **−$1,520** |

Checks: **7/7 pass** (wfe, transfer, sample, plateau, pbo, luck, consistency).
Walk-forward **8/8 folds held**, wfe 2.546 (best mode: anchored). DSR 0.998.
Causal test: "entry timing carries real signal" (99.7th pctile vs 1,000 nulls).

### `validate.lockbox`, verbatim

```json
{ "from": "2025-02-11", "to": "2026-08-12",
  "trades": 424, "pass": true,
  "pf": 1.0840, "pnl": 1157.30, "dd": 1520.60,
  "sharpe": 0.4277, "sortino": 0.8379,
  "win_rate": 37.26, "avg_win": 94.48, "avg_loss": 51.78 }
```

**Units are USD**, and it reconciles internally: 424 × 37.26% = 158 wins × $94.48 =
$14,928, minus 266 losses × $51.78 = $13,773 → **net $1,155**, matching `pnl` 1157.30.
That works out to **~$2.73/trade** over 18 months — a pass, but a thin one.

**Do not confuse slices.** A PF of ~1.24 seen elsewhere is **IS+WF combined**; the 1.084
above is **LB-only**. Both are correct. LB landing under IS+WF is the expected direction,
not a contradiction.

---

## ⚠ Config divergence — the crowned champion is NOT what PAPER is forward-testing

| | lookback | band long | band short | stop_k |
|---|---|---|---|---|
| **#225 champion** | 44 | 0.75 | 1.5 (asymmetric) | **1.75** |
| **PAPER leg, live now** | 14 | 1.5 | 1.5 (symmetric) | **1.0** |

Live config appears in **both** `api/paper.py` (`NOISE_FROZEN`, ~line 67) and the
NinjaScript `tools/nt/EdgeLogNOISE.cs` (defaults ~line 90) — engine and NT agree with
each other, but neither matches #225's crowned config.

Consequence for the "is the protective stop validated OOS?" question:

- The **bandwidth-stop concept** now HAS out-of-sample support — a bandwidth stop
  (k=1.75) is inside a config that passed a fresh 18-month lockbox.
- The **specific production config** (14 / 1.5 / 1.5 / k=1.0) is still the pre-lockbox
  2026-08-08 pick from the 25-variant exit sweep. #225's own search did not crown it.

Resolving this divergence is probably worth more than adding any new paper leg.

Side note: the param set hardcoded at `tools/gate_lookahead_audit.py:233`
(lookback=44, 0.75/1.5, stop_k=1.75) was previously flagged as an unexplained artifact.
It is not — **it is #225's champion.**

---

## Caveats to carry forward

1. **Lockbox edge is thin** — PF 1.084, ~$2.73/trade, sharpe 0.43. Passing, not strong.
2. **PBO 0.365** — the run's own label is *"some overfit risk"*
   (`validate.pbo`, 252 splits, 24 configs).
3. **ES-transfer: resolved — two different bars, not a contradiction.** #225 records
   transfer **PASS at PF 1.033** (`validate.transfer`: ES, 5,796 trades, pnl 709.51).
   `NOISE_1_0.py`'s docstring calls ES-transfer a **FAIL**. Both are correct, because
   they're measuring against different bars: `validate.transfer`'s `pass` field is the
   engine's generic, universal cross-instrument sanity check applied to every strategy
   (PF >= 1.0 and positive PnL, unchanged since 2026-06-20) — 1.033 clears it. NOISE
   also has its own stricter, pre-registered promotion bar of **PF >= 1.2**, set in the
   round-12 challenger writeup (see `BACKTESTING_STACK.md`, "C4 ES TRANSFER FAIL: PF
   1.123 < 1.2"). #225's PF 1.033 still fails that bar (same failing side as the
   original 1.123 < 1.2). Net: the promotion verdict is unchanged — NOISE has never
   cleared its own ES-transfer promotion requirement, even though it clears the
   engine's looser generic gate. ES-transfer is load-bearing for crowning; treat the
   1.2 bar, not the generic 1.0 gate, as the one that matters for promotion.
4. **VIF: 4 collinear features** (`dist_pdl_atr` 7.8, `dist_pdh_atr` 6.28, `range_pos`
   5.7, `dist_pdc_atr` 5.46) — flagged as drop candidates; the only non-passing flag.
5. **Adversarial**: AUC 0.607, "mild drift — a modestly different regime" (passes).

---

## ML gate — still closed

#225 agrees with the earlier pre-registered test (#219): `validate.flags.gate` reads
**"LOCKBOX FAILED — gate lost to ungated out-of-sample (pre-lockbox win was likely fit)"**
(chosen `logistic@55%`, `earns_pre: true`, `helped: false`). Two independent runs, same
conclusion. The gate/size-tilt family on NOISE stays closed unless something structural
changes.

---

## 2026-08-17 — variant campaign: entry-quality filters CLEAR the pre-registered bar

> Full pre-registration + round log below. Harness: `tools/noise_variant_research.py`
> (parity vs `NOISE_1_0.py` through the real engine proven exact to the cent).
> Knobs shipped in `NOISE_1_0.py` (all default OFF, smoke tests a-d PASS):
> `confirm_bars`, `daytype_mode`, `daytype_lo`, `daytype_hi`, `vol_skip_pct`.
> New preset: **"Filter (2026-08-17 winner vs champion)"** — champion core pinned,
> 12 cells incl. the exact champion cell. NOTE: the validate job type IGNORES presets
> (`run_validate` searches DEFAULT_PARAMS via the auto-sampler — #231's preset field was
> decorative too); the controlled 12-cell comparison therefore runs as a GRID job, and the
> re-validate's job is to see whether the filter knobs EARN the crown under #231's machinery.

**Method (mirrors the 2026-08-08 stop research):** adoption bar pre-registered BEFORE any
backtest; ALL selection on the PRE-LOCKBOX window **2010-06-07 → 2025-02-10** (run #231's
optimize window — the 2025-02-11→2026-08-12 lockbox is SPENT, read once, confirmatory,
after the pick). Bar: net ≥ champion · MAR ≥ champion · 2010-17 ≥ $0 · worst year not
worse · plateau across pre-declared neighbors · mechanism sanity. Baseline (#231 champion
44/0.75/1.5/vwap/bandwidth k1.75, selection window): **n=5,113 · $277,123 · PF 1.241 ·
DD $19,482 · MAR 14.22 · 2010-17 +$11,524 · worst 2010 −$2,278**.

**WINNER (pre-registered Occam combo rule): `confirm_bars=2` + `daytype_mode='skip_bot_short'`**
— wait for 2 consecutive closes outside the band before entering, and take no SHORT
entries the day after a close in the bottom 20% of the prior day's range (the program-wide
"shorts fail after weak closes" pattern, banked across 4+ families):
**n=4,010 · $332,699 (+20%) · PF 1.399 · DD $14,076 (−28%) · MAR 23.64 · 2010-17 +$22,262
· worst 2010 −$1,581 · only negative year = 2010.** Neighborhood = a plateau (daytype_lo
0.15/0.25, confirm 3, lookback 36/52, band_mult_long 0.5/1.0, band_mult_short 1.25/1.75,
stop_k 1.5/2.0 all stay $303–338k net, MAR 17–24.7).

**Round log (every cell judged against the bar above):**
- **A1 vol-conditional exit switch (exit_eod / exit_band × pct 70/80/90/95): DEAD, all 8**
  — the k1.75 stop already fixed the 2020 vwap-whipsaw (2020 = +$29.1k at baseline); the
  round-12 lead was real but is already harvested.
- **A2 skip high-vol days (`vol_skip_pct` 90/95/98): CLEARS on all 3 thresholds** (best
  90: $310,690 · MAR 16.32). Mechanism: baseline day-mean −$100 on top-decile-vol days vs
  +$142 elsewhere, day-clustered permutation p=0.001. Banked as a validated single — NOT
  in the shipped winner (combos with it failed the beat-best-component rule).
  skip LOW-vol days: dead (no plateau).
- **A3 tighten stop in high vol (×0.5/×0.75 @ pct 80/90): clears, small** — dominated by
  A2/B1/B4; not selected.
- **B1 entry confirmation (2 and 3 closes): CLEARS both** ($299.1k/$299.0k, MAR 16.5/17.6).
- **B2 time-decay exit (24/36/48 bars): DEAD** (net −$11k to −$34k vs baseline).
- **B3 asymmetric stop_k long/short: DEAD** (stop_k_long 1.25 cleared net+MAR but its only
  declared neighbor failed → no plateau → rejected per pre-reg).
- **B4 prior-day close-position filter: `skip_bot_short` CLEARS big** ($320,530 · MAR 17.27,
  best single); `skip_bot_all` also clears; both skip_top modes WORSE (long side is where
  the money is — consistent with the buy-weakness meta-finding).
- **B5 skip-after-loss: DEAD** ($116.7k, MAR 3.65 — as expected, banked).
- **D combos (pre-registered addendum + Occam rule "combo must beat its best component on
  net AND MAR"):** D3 confirm2+skip_bot_short WINS ($332.7k/23.64 > $320.5k/17.27);
  hi90 combos and the triple all failed the rule (the filters overlap on the same bad days).

**Confirmatory one-look (full window incl. SPENT lockbox — never used for selection):**
net $367,959 · PF 1.322. Lockbox slice (2025-02-11→2026-08-12): **+$35.3k, PF 1.11 —
positive but SMALLER than the baseline champion's same slice (+$58.9k)**. Carried honestly:
the filters gave back some 2025-26 profit; the pre-registered pre-lockbox bar is what was
met. Owner-visible arbiters queued (in order): (1) 12-cell comparison GRID (champion core
pinned, only filter knobs vary), (2) re-validate with #231's exact machinery/window (filter
knobs now in the search space), (3) the first-ever NOISE BOOK job (variant + ORB #230 crown).

**ES-transfer probe (local, selection window, same 0.533 costs):** the filters IMPROVE the
ES sibling too — PF 1.037 → 1.116, points PnL +135% (645 → 1,519 pts). Still below NOISE's
own PF ≥ 1.2 promotion bar, but the mechanism travels in the right direction (evidence
against NQ curve-fit; the queued validate records the official transfer numbers).

**Known-unknown flagged:** run #225/#231's headline n/net (e.g. 3,872 / $96,611) don't
match the raw-engine path on the same source/params (5,113 / $277,123 on the shorter
selection window; harness == `augur_engine.engine.run_backtest` exact) — the validate
pipeline's champion-metrics convention differs from the raw engine path. Run-to-run
comparisons inside the runner remain apples-to-apples; worth a separate reconciliation.

### Campaign results table — every config, with IS / WF / LB dollar splits

> Built 2026-08-17 by `tools/noise_campaign_table.py` (committed the same day). Run it to
> regenerate: `python tools/noise_campaign_table.py`. It refuses to print a table unless
> two reconciliation gates pass first (both PASS as of this writing — see "Reconciliation"
> below). Source PINNED: db_noadj_rth · NQ 5m rth · cost_pts 0.533 · multiplier 20.
> **MaxDD is printed POSITIVE.** Money to the dollar, PF/MAR to 2dp.

**Column conventions — read this before comparing anything.** Three stretches, all pinned to
run #231's saved `validate.windows`:

- **IS** and **WF** = one CONTINUOUS backtest over the optimize window **2010-06-07 →
  2025-02-10**, cut in two at **2016-04-29 13:50 ET** (last IS trade; first WF trade
  2016-05-02 13:50 ET). That instant is derived from #231's own crowned candidate — its
  `is_rng` holds 1,921 trades and its `wf_rng` holds 3,192 — i.e. the same cut the app's
  §1E MATRIX RAW tab makes with `_rawFrac`, just resolved to a calendar instant so every
  variant is cut at the SAME point in time instead of at its own trade-count fraction.
  **IS $ + WF $ = the optimize-window total, exactly.**
- **LB** = a FRESH backtest over **2025-02-11 → 2026-08-12** only. This is the engine's own
  lockbox convention — it burns the strategy's warm-up inside the lockbox window — and it is
  what reconciles to `validate.lockbox` (441 trades / 1814.2363 pts on #231).
- **TOTAL $, MaxDD, PF, net/DD (MAR) and trades** all describe one CONTINUOUS backtest
  **2010-06-07 → 2026-08-12**. That is the scope run #236's saved `points` carry and what
  #231's `validate.total_*` describes.
- **IS + WF + LB does NOT sum to TOTAL**, and that is not an error: the fresh LB pass drops
  the ~79 warm-up trades a continuous pass keeps. The continuous-run slice of the same
  lockbox dates DOES close the gap exactly (#231: $6,190 + $270,934 + $58,858 = $335,981).
  Both LB numbers are real; the table shows the `validate.lockbox`-compatible one.
- **Convention label per row:** rows marked **[H]** are computed by the harness (raw-engine
  path). Rows marked **[D]** are read verbatim from a saved validate/BOOK doc. Never mix the
  two inside one comparison without noticing which is which.

| # | Config/Run | what it is | IS $ | WF $ | LB $ | TOTAL $ | MaxDD $ | PF | net/DD (MAR) | trades | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **#231 (NOISE-7)** [H] | • CURRENT CHAMPION / campaign baseline<br>• lookback 44 · band 0.75/1.5 · vwap · bandwidth k1.75 · all filter knobs OFF | 6,190 | 270,934 | 36,285 | 335,981 | 32,794 | 1.22 | 10.25 | 5,633 | **PASS** — 7/7 checks, WF 8/8 folds, PBO 0.365 |
| 2 | **#236 cell 7 = D3 WINNER** [H] | • confirm_bars 2 + daytype skip_bot_short, champion core pinned<br>• the pre-registered Occam combo winner | 17,330 | 315,369 | 32,556 | 367,959 | 37,729 | 1.32 | 9.75 | 4,418 | **CLEARS the pre-registered bar** on the selection window (net +20%, MAR 23.64 vs 14.22) — but see caveat 3 |
| 3 | #236 cell 1 [H] | • confirm 1 / daytype off / no vol-skip<br>• = the champion cell, the grid's control | 6,190 | 270,934 | 36,285 | 335,981 | 32,794 | 1.22 | 10.25 | 5,633 | control cell |
| 4 | #236 cell 2 [H] | • confirm 1 / daytype off / vol-skip 90 | 13,168 | 297,522 | 40,328 | 372,285 | 23,698 | 1.35 | 15.71 | 4,732 | beats control on net, DD and MAR |
| 5 | #236 cell 3 [H] | • confirm 1 / skip_bot_short / no vol-skip<br>• **#236's own crowned best** ($388,181) | 16,654 | 303,876 | 40,120 | 388,181 | 31,191 | 1.29 | 12.45 | 5,214 | highest TOTAL $ in the grid |
| 6 | #236 cell 4 [H] | • confirm 1 / skip_bot_short / vol-skip 90 | 16,445 | 303,685 | 40,648 | 380,745 | 22,096 | 1.39 | 17.23 | 4,429 | beats control on every axis |
| 7 | #236 cell 5 [H] | • confirm 2 / daytype off / no vol-skip | 5,927 | 293,172 | 27,983 | 320,914 | 44,189 | 1.25 | 7.26 | 4,762 | worst TOTAL drawdown in the grid |
| 8 | #236 cell 6 [H] | • confirm 2 / daytype off / vol-skip 90 | 12,771 | 290,905 | 15,512 | 334,370 | 21,205 | 1.36 | 15.77 | 4,011 | thin LB |
| 9 | #236 cell 7 [H] | • confirm 2 / skip_bot_short / no vol-skip<br>• **THE WINNER** (same row as #2 above) | 17,330 | 315,369 | 32,556 | 367,959 | 37,729 | 1.32 | 9.75 | 4,418 | best selection-window MAR of the no-vol-skip cells |
| 10 | #236 cell 8 [H] | • confirm 2 / skip_bot_short / vol-skip 90 (the triple) | 18,367 | 298,690 | 20,084 | 349,773 | 19,433 | 1.42 | 18.00 | 3,757 | best PF + best TOTAL MAR; rejected by the Occam rule |
| 11 | #236 cell 9 [H] | • confirm 3 / daytype off / no vol-skip | 8,850 | 290,181 | 40,227 | 344,973 | 31,332 | 1.31 | 11.01 | 4,151 | — |
| 12 | #236 cell 10 [H] | • confirm 3 / daytype off / vol-skip 90 | 12,603 | 275,121 | 26,800 | 320,393 | 16,630 | 1.40 | 19.27 | 3,504 | smallest TOTAL drawdown in the grid |
| 13 | #236 cell 11 [H] | • confirm 3 / skip_bot_short / no vol-skip | 18,326 | 297,514 | 35,969 | 365,105 | 26,189 | 1.36 | 13.94 | 3,865 | — |
| 14 | #236 cell 12 [H] | • confirm 3 / skip_bot_short / vol-skip 90 | 17,564 | 276,566 | 22,541 | 321,560 | 17,762 | 1.43 | 18.10 | 3,292 | highest PF in the grid, lowest trade count |
| 15 | **#237 (NOISE-9)** [D] | • the re-validate with the filter knobs in the search space<br>• crowned config WANDERED off the champion core (lookback 64, band 0.5/1.5, stop fixed k1.25, vol_skip 89, daytype off) | 6,634 | 291,279 | 19,468 | 326,810 | 19,757 | 1.29 | 16.54 | 5,151 | **WEAK** — PBO 0.599 "likely overfit selection", 6/7 checks; the filters did NOT earn the crown |
| 16 | **#238 BOOK** [D] | • first-ever NOISE BOOK: the D3 variant + ORB230 pooled and scored as ONE strategy<br>• legs: NOISE $367,959 (4,418 tr) + ORB_3_4_C221 $348,129 (2,607 tr) | n/a — BOOK job emits no WF folds; pre-lockbox (IS+WF combined) = **547,244** / DD 27,385 / PF 1.29 / 6,370 tr | n/a — same reason | 168,845 | 716,089 | 39,809 | 1.29 | 17.99 | 7,025 | **PASS** — 7/8 slices held; LB PF 1.28 on 655 trades |
| 17 | A2 vol_skip 90 [H] | • skip the day after a top-decile-vol session<br>• = #236 cell 2 | 13,168 | 297,522 | 40,328 | 372,285 | 23,698 | 1.35 | 15.71 | 4,732 | **CLEARED** the bar — banked as a validated single |
| 18 | A2 vol_skip 95 [H] | • same, top-5% threshold | 11,470 | 291,493 | 52,580 | 375,262 | 28,873 | 1.30 | 13.00 | 5,159 | **CLEARED** |
| 19 | A2 vol_skip 98 [H] | • same, top-2% threshold | 12,321 | 296,734 | 61,018 | 384,690 | 22,334 | 1.29 | 17.22 | 5,347 | **CLEARED** — best LB of the whole campaign |
| 20 | B1 confirm_bars 2 [H] | • 2 consecutive closes outside the band before entering<br>• = #236 cell 5 | 5,927 | 293,172 | 27,983 | 320,914 | 44,189 | 1.25 | 7.26 | 4,762 | **CLEARED** |
| 21 | B1 confirm_bars 3 [H] | • 3 consecutive closes<br>• = #236 cell 9 | 8,850 | 290,181 | 40,227 | 344,973 | 31,332 | 1.31 | 11.01 | 4,151 | **CLEARED** |
| 22 | B4 skip_bot_short [H] | • no SHORTs after a bottom-20%-of-range close<br>• = #236 cell 3 | 16,654 | 303,876 | 40,120 | 388,181 | 31,191 | 1.29 | 12.45 | 5,214 | **CLEARED — best single component** |
| 23 | B4 skip_bot_all [H] | • no trades at all after a bottom-20% close | 9,033 | 299,750 | 49,470 | 366,855 | 29,041 | 1.34 | 12.63 | 4,404 | **CLEARED** |
| 24 | A3 stop ×0.75 @ vol pct 90 [H] | • tighten the protective stop on high-vol days | 6,738 | 276,395 | 38,326 | 339,503 | 29,432 | 1.22 | 11.54 | 5,654 | clears, small — dominated by A2/B1/B4, not selected |
| 25 | D1 confirm2 + vol_skip90 [H] | • combo; = #236 cell 6 | 12,771 | 290,905 | 15,512 | 334,370 | 21,205 | 1.36 | 15.77 | 4,011 | REJECTED — fails the beat-best-component rule |
| 26 | D2 skip_bot_short + vol_skip90 [H] | • combo; = #236 cell 4 | 16,445 | 303,685 | 40,648 | 380,745 | 22,096 | 1.39 | 17.23 | 4,429 | REJECTED — same rule |
| 27 | D4 triple (confirm2 + skip_bot_short + vs90) [H] | • all three filters; = #236 cell 8 | 18,367 | 298,690 | 20,084 | 349,773 | 19,433 | 1.42 | 18.00 | 3,757 | REJECTED — same rule (the filters overlap on the same bad days) |
| 28 | A1 vol-cond exit_eod @90 [H] | • hold to EOD on high-vol days — DEAD family rep | 6,380 | 268,242 | 33,873 | 325,154 | 39,301 | 1.21 | 8.27 | 5,326 | DEAD |
| 29 | A1 vol-cond exit_band @90 [H] | • band exit on high-vol days — DEAD family rep | 5,490 | 271,046 | 43,837 | 336,903 | 27,129 | 1.23 | 12.42 | 5,922 | DEAD |
| 30 | A2 skip LOW-vol days [H] | • the other tail of the vol filter | 9,839 | 240,965 | 50,081 | 315,848 | 32,794 | 1.22 | 9.63 | 5,082 | DEAD — no plateau |
| 31 | B2 time-decay exit 36 bars [H] | • flat after 36 bars in trade — DEAD family rep | 671 | 266,191 | 42,658 | 329,452 | 33,854 | 1.19 | 9.73 | 6,675 | DEAD |
| 32 | B3 asym stop_k_long 1.25 [H] | • separate stop_k per side — DEAD family rep | 6,605 | 289,944 | 29,787 | 346,468 | 28,768 | 1.23 | 12.04 | 5,694 | DEAD — cleared net+MAR but its declared neighbor failed → no plateau |
| 33 | B4 skip_top_long [H] | • no LONGs after a top-20% close | 9,745 | 216,728 | 25,507 | 280,710 | 34,882 | 1.22 | 8.05 | 4,527 | DEAD — long side is where the money is |
| 34 | B4 skip_top_all [H] | • no trades after a top-20% close | 9,168 | 156,775 | 35,340 | 221,607 | 33,185 | 1.20 | 6.68 | 4,087 | DEAD |
| 35 | B5 skip-after-loss [H] | • sit out the session after a losing session | −3,908 | 120,583 | 12,071 | 135,214 | 32,019 | 1.12 | 4.22 | 4,057 | DEAD — the only row with a losing IS stretch |
| 36 | #225 (NOISE-6) [D] | • REFERENCE: the prior NOISE run, SAME crowned config as #231, same windows<br>• earlier data vintage → different totals | 6,190 | 270,934 | 23,146 | 322,842 | 30,412 | 1.21 | 10.62 | 5,616 | PASS — superseded by #231 |
| 37 | #230 (ORB-crown) [D] | • REFERENCE: the ORB leg inside #238's BOOK<br>• DIFFERENT windows — optimize → 2025-08-12, 12-month lockbox 2025-08-13 → 2026-08-13 | n/a — run #230 saves no `is_rng`/`wf_rng`/`champion_cal`; pre-lockbox (IS+WF combined) = **283,554** / DD 35,474 / PF 1.25 / 2,429 tr | n/a — same reason | 64,575 | 348,129 | 35,474 | 1.26 | 9.81 | 2,607 | PASS — the standing ORB crown |

**Selection-window cross-reference** — the campaign's pre-registered bar was judged on the
optimize window ONLY (IS + WF, 2010-06-07 → 2025-02-10). These are the numbers quoted in the
round log above, restated so the two views can be told apart at a glance:

| Config | selection-window net $ | PF | MaxDD $ | net/DD (MAR) | trades |
|---|---|---|---|---|---|
| #231 champion (baseline) | 277,123 | 1.24 | 19,482 | 14.22 | 5,113 |
| **D3 WINNER confirm2 + skip_bot_short** | **332,699** | **1.40** | **14,076** | **23.64** | 4,010 |
| B4 skip_bot_short (best single) | 320,530 | 1.32 | 18,560 | 17.27 | 4,748 |
| A2 vol_skip 90 | 310,690 | 1.38 | 19,041 | 16.32 | 4,309 |
| A2 vol_skip 95 | 302,963 | 1.31 | 19,176 | 15.80 | 4,697 |
| A2 vol_skip 98 | 309,055 | 1.30 | 19,176 | 16.12 | 4,868 |
| B1 confirm 2 | 299,099 | 1.32 | 18,180 | 16.45 | 4,309 |
| B1 confirm 3 | 299,031 | 1.37 | 16,964 | 17.63 | 3,757 |
| B4 skip_bot_all | 308,783 | 1.38 | 15,934 | 19.38 | 3,991 |
| D4 triple (rejected) | 317,058 | 1.51 | 11,302 | 28.05 | 3,429 |
| B5 skip-after-loss (dead) | 116,674 | 1.14 | 31,947 | 3.65 | 3,680 |

**Reconciliation — what was checked, and what is still open.**

1. **Gate 1 (harness vs run #231's saved doc) — PASS, exact to 4 decimal places on all five
   stretches.** IS 1,921 tr / 309.4836 pts / DD 382.9997 · WF 3,192 / 13546.6818 / 974.1137 ·
   optimize 5,113 / 13856.1654 / 974.1137 · LB 441 / 1814.2363 / 1639.6985 · full 5,633 /
   16799.0415 / 1639.6985. IS + WF = the optimize total exactly; IS + WF + LB(continuous
   slice) = TOTAL exactly.
2. **Gate 2 (harness vs run #236's saved `points`) — PASS, all 12 GRID cells match** on both
   pnl and drawdown. That is an independent check of every computed row against a number the
   runner itself banked. A third, unplanned check also lands: #238's BOOK doc records its
   NOISE leg at $367,959.30 / 4,418 trades, which is the D3 row to the cent.
3. **The winner's lockbox is WORSE than the champion's, on both LB conventions.** D3 LB
   $32,556 vs #231's $36,285 (fresh-run convention), or $35,260 vs $58,858 (continuous-slice
   convention). The pre-registered bar was met on the pre-lockbox window, which is the honest
   claim; the 2025-26 give-back is real and already flagged in the round log above. Note also
   that D3's TOTAL drawdown is LARGER than the champion's ($37,729 vs $32,794) even though its
   selection-window drawdown is 28% smaller — the whole extra drawdown lives in the lockbox.
4. **The known-unknown from the round log is now pinned down precisely.** The mismatch is NOT
   in the IS/WF/LB machinery — every one of those saved fields reproduces exactly. It is
   confined to the `best_*` headline block (#231: `best_trades` 3,872 / `best_pnl_usd` $96,611
   / `best_dd_usd` −$16,827), which is the optimizer's champion-metrics scope, not the
   optimize window and not the full window. `validate.total_*` and the `is_rng`/`wf_rng`/
   `lockbox`/`cal` blocks are all on the raw-engine convention and agree with the harness.
   Everything in the table above therefore sits on ONE convention; only the `best_*` headline
   sits on the other, and it appears nowhere in this table.
5. **Two rows carry a genuinely uncomputable split, and it is labelled in the cell.** #238
   (BOOK) never emits walk-forward folds by design, so there is no IS/WF boundary to cut at —
   only pre-lockbox vs lockbox. #230 saves no `is_rng`/`wf_rng`/`champion_cal`, so its IS/WF
   boundary was never persisted; its config is an ORB strategy the NOISE harness cannot run,
   so it cannot be recomputed either. Both report the combined pre-lockbox figure instead.
6. **#237's row is [D], not [H], on purpose.** Its crowned config sets `skip_holidays=True`,
   a knob the campaign harness does not implement, so it cannot be recomputed — the saved
   `champion_cal` / `validate.lockbox` blocks are used verbatim. Its TOTAL PF is derived from
   `validate.total_win_rate` / `total_avg_win` / `total_avg_loss` (the same derivation
   reproduces #231's saved 1.2207 exactly, so the formula is verified).
7. **#230's windows are NOT the campaign's windows.** Its optimize window ends 2025-08-12 and
   its lockbox is 12 months (2025-08-13 → 2026-08-13), against NOISE's 18 months ending
   2025-02-10 / starting 2025-02-11. Its LB column is therefore not comparable to the NOISE
   rows. #238's BOOK doc uses a third boundary again (`lockbox_from` 2025-02-10).
8. **#225 vs #231 is a data-vintage difference, not a convention one.** Identical crowned
   config and identical windows, yet 5,616 vs 5,633 total trades and LB $23,146 vs $36,285.
   The harness reproduces #231, not #225, so #231 is the current-data truth and #225's row is
   kept only as a historical reference.

---

## Still genuinely untested (not dead ends — nobody has run these)

- **NOISE in a BOOK job.** BOOK (pool N legs, score as ONE strategy) exists since v71.42
  and has never had NOISE put through it. NOISE↔ORB correlation measured **0.21–0.25**
  (twice, rounds 10 and 12) — low enough to expect real diversification — but no blended
  backtest was ever actually run.
- **TRADE CONTEXT feature→PnL FDR scan on NOISE.** The engine (`augur_engine/context.py`)
  is generic and wired in; no NOISE-specific scan is recorded anywhere.
- ~~Vol-regime filter / vol-conditional exit~~ — RUN 2026-08-17 (campaign above): the
  exit-switch is dead (stop already harvests it); the vol-skip FILTER validated as a
  single (`vol_skip_pct=90`, banked).

---

## How to re-check any of the above

```python
import firebase_admin
from firebase_admin import credentials, firestore
firebase_admin.initialize_app(credentials.Certificate('serviceAccount.json'))
db = firestore.client()
uid = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'
x = db.collection('users').document(uid).collection('runs').document('225').get().to_dict()

x['validate']['lockbox']    # LB-only metrics
x['validate']['windows']    # optimize vs lockbox date ranges
x['validate']['checks']     # the 7 pass/fail gates
x['validate']['flags']      # gate / vif / adversarial verdicts
x['best_params']            # crowned config
x['win_dist_lb']            # per-trade LB P&L array
```

Run from the checkout root (needs `serviceAccount.json`). Set `PYTHONIOENCODING=utf-8` —
some verdict strings contain em-dashes that crash cp1252 stdout on Windows.
